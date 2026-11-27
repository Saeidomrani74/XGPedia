"""ذخیره‌سازی MVP — SQLite + لایهٔ repository (مهاجرت‌پذیر به PostgreSQL).

گروه‌های جدول (بخش ۷ سند):
  دادهٔ فوتبال: competitions, seasons, teams, players, fixtures, match_events,
    lineups, fixture_statistics, player_statistics, injuries, availability_reports
  ردیابی منبع: data_sources, ingestion_runs, raw_payloads
  محتوا و انتشار: articles, posts, media_assets, publishing_logs, scheduled_publishes
  جامعه و ربات: bot_users, subscriptions, prediction_entries, leaderboards,
    moderation_logs, admin_actions
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
from contextlib import contextmanager

from src.xgpedia.config import DATABASE_PATH

_BOT_KV_STATE_DDL = """
CREATE TABLE IF NOT EXISTS bot_kv_state (
  namespace TEXT NOT NULL,
  state_key TEXT NOT NULL,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (namespace, state_key)
);
"""

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS fixtures (
  fixture_id TEXT PRIMARY KEY,            -- "provider:12345"
  provider TEXT NOT NULL,
  competition TEXT NOT NULL,
  season TEXT NOT NULL,
  kickoff_utc TEXT NOT NULL,
  home_team TEXT NOT NULL,
  away_team TEXT NOT NULL,
  home_team_code TEXT,
  away_team_code TEXT,
  status TEXT NOT NULL DEFAULT 'scheduled',
  matchday INTEGER,
  raw_payload_hash TEXT,
  collected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fixture_statistics (
  fixture_id TEXT NOT NULL,
  team TEXT NOT NULL,
  team_code TEXT,
  metric TEXT NOT NULL,                  -- total_shots, expected_goals, ...
  value REAL,                            -- NULL = داده در دسترس نیست (هرگز 0 جایگزین نشود)
  n INTEGER,
  provider TEXT NOT NULL,
  collected_at TEXT NOT NULL,
  PRIMARY KEY (fixture_id, team, metric, provider)
);

CREATE TABLE IF NOT EXISTS raw_payloads (
  payload_hash TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  endpoint TEXT NOT NULL,
  collected_at TEXT NOT NULL,
  file_path TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
  post_id INTEGER PRIMARY KEY AUTOINCREMENT,
  fixture_id TEXT NOT NULL,
  post_type TEXT NOT NULL,               -- preview | post_match | number_of_day | ...
  target_platform TEXT NOT NULL,         -- telegram | instagram | website | tiktok
  content_version INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'draft',  -- draft|validated|awaiting_approval|approved|scheduled|published|failed|corrected
  title TEXT, caption TEXT,
  draft_json TEXT,                       -- خروجی کامل مدل (bullets/source_note/uncertainties)
  fact_json TEXT,                        -- JSON واقعیت‌ها — منبع único تک‌نسخه
  created_at TEXT NOT NULL,
  UNIQUE (fixture_id, post_type, target_platform, content_version)  -- idempotency key
);

CREATE TABLE IF NOT EXISTS publishing_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id INTEGER NOT NULL REFERENCES posts(post_id),
  platform_message_id TEXT,
  permalink TEXT,
  published_at TEXT NOT NULL,
  result TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS moderation_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id INTEGER,
  admin_user_id INTEGER NOT NULL,
  action TEXT NOT NULL,                  -- approve | reject | edit | rebuild | schedule | cancel_schedule
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scheduled_publishes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id INTEGER NOT NULL REFERENCES posts(post_id),
  scheduled_at_utc TEXT NOT NULL,
  scheduled_time_tehran TEXT NOT NULL,   -- فرمت ۲۴ ساعته تهران مثل "09:35"
  scheduled_by_admin INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', -- pending | published | failed | cancelled
  error_detail TEXT,
  created_at TEXT NOT NULL,
  executed_at TEXT
);

CREATE TABLE IF NOT EXISTS fixture_odds (
  home_team TEXT NOT NULL,
  away_team TEXT NOT NULL,
  home_team_code TEXT,
  away_team_code TEXT,
  match_date TEXT NOT NULL,              -- YYYY-MM-DD
  home_odds REAL,
  draw_odds REAL,
  away_odds REAL,
  over25_odds REAL,
  btts_odds REAL,
  provider TEXT NOT NULL,
  collected_at TEXT NOT NULL,
  PRIMARY KEY (home_team, away_team, match_date, provider)
);

CREATE TABLE IF NOT EXISTS team_enrichments (
  team TEXT NOT NULL,
  team_code TEXT,
  season TEXT NOT NULL,
  key_player_json TEXT,                  -- {"name", "pos", "s1", "s2"}
  ppda REAL,
  deep_passes REAL,
  wave_json TEXT,
  provider TEXT NOT NULL,
  collected_at TEXT NOT NULL,
  PRIMARY KEY (team, season, provider)
);

CREATE TABLE IF NOT EXISTS fixture_broadcasts (
  fixture_id TEXT PRIMARY KEY,
  channel_label TEXT NOT NULL,           -- "پخش زنده: شبکه سه" | "پخش زنده: شبکه ورزش"
  program_title TEXT,
  broadcast_time TEXT,                   -- "HH:MM"
  tehran_date TEXT NOT NULL,
  collected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_cache (
  source_key TEXT PRIMARY KEY,           -- results | fixtures | odds | understat | broadcasts
  tehran_date TEXT NOT NULL,
  last_synced_at TEXT NOT NULL,
  summary TEXT
);

CREATE TABLE IF NOT EXISTS fixture_post_match (
  fixture_id TEXT PRIMARY KEY,
  details_json TEXT NOT NULL,
  provider TEXT NOT NULL,
  collected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS team_metadata (
  team TEXT NOT NULL,
  team_code TEXT,
  season TEXT NOT NULL,
  venue_en TEXT,
  coach_en TEXT,
  provider TEXT NOT NULL,
  collected_at TEXT NOT NULL,
  PRIMARY KEY (team, season, provider)
);

CREATE TABLE IF NOT EXISTS api_hydration_cache (
  cache_key TEXT PRIMARY KEY,
  namespace TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  fetched_at REAL NOT NULL,
  ttl_sec INTEGER NOT NULL,
  expires_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hydration_ns_exp ON api_hydration_cache(namespace, expires_at);

CREATE TABLE IF NOT EXISTS post_metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id INTEGER,
  card_type TEXT NOT NULL,
  tone TEXT,
  admin_decision TEXT NOT NULL,
  edit_count INTEGER NOT NULL DEFAULT 0,
  llm_provider TEXT,
  render_ms INTEGER,
  notes TEXT,
  recorded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_post_metrics_card_time ON post_metrics(card_type, recorded_at);



CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
CREATE INDEX IF NOT EXISTS idx_fixtures_kickoff ON fixtures(kickoff_utc);
CREATE INDEX IF NOT EXISTS idx_scheduled_status_time ON scheduled_publishes(status, scheduled_at_utc);
""" + _BOT_KV_STATE_DDL


SCHEMA_VERSION = 5


def get_schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row else 0


@contextmanager
def db():
    conn = sqlite3.connect(DATABASE_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


def backup_database(db_path: Path | None = None, *, reason: str = "manual") -> Path | None:
    """پشتیبان‌گیری امن (WAL-safe) از فایل SQLite پیش از مهاجرت یا به‌صورت دستی (v0.80.0)."""
    src_path = Path(db_path) if db_path is not None else DATABASE_PATH
    if not src_path.exists() or src_path.stat().st_size == 0:
        return None
    from datetime import datetime, timezone

    backup_dir = src_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_reason = "".join(c if (c.isalnum() or c in "-_") else "_" for c in reason)[:32] or "backup"
    dst_path = backup_dir / f"{src_path.stem}_{safe_reason}_{ts}.sqlite"
    src_conn = sqlite3.connect(str(src_path), timeout=30.0)
    dst_conn = sqlite3.connect(str(dst_path), timeout=30.0)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()
    return dst_path


def _migrate(conn: sqlite3.Connection) -> None:
    """مهاجرت سبک و idempotent برای DBهای نسخه‌های قبل (با مرجع یگانهٔ SCHEMA و بکاپ خودکار)."""
    cur_ver = get_schema_version(conn)
    if 0 < cur_ver < SCHEMA_VERSION and DATABASE_PATH.exists():
        try:
            backup_database(DATABASE_PATH, reason=f"pre_v{SCHEMA_VERSION}_from_v{cur_ver}")
        except Exception:
            pass
    # تضمین وجود تمام جدول‌ها و ایندکس‌ها از روی تعریف یگانهٔ SCHEMA
    conn.executescript(SCHEMA)

    fx_cols = {r["name"] for r in conn.execute("PRAGMA table_info(fixtures)")}
    if "matchday" not in fx_cols:
        conn.execute("ALTER TABLE fixtures ADD COLUMN matchday INTEGER")
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(posts)")}
    if "draft_json" not in cols:
        conn.execute("ALTER TABLE posts ADD COLUMN draft_json TEXT")
    enr_cols = {r["name"] for r in conn.execute("PRAGMA table_info(team_enrichments)")}
    if "wave_json" not in enr_cols:
        conn.execute("ALTER TABLE team_enrichments ADD COLUMN wave_json TEXT")

    # مهاجرت غیرمخرب v0.76.0: افزودن ستون‌های کد استاندارد سه‌حرفی تیم (team_code) بدون حذف هیچ ردیف قدیمی
    _tc_alters = (
        ("fixtures", "home_team_code"),
        ("fixtures", "away_team_code"),
        ("fixture_statistics", "team_code"),
        ("fixture_odds", "home_team_code"),
        ("fixture_odds", "away_team_code"),
        ("team_enrichments", "team_code"),
        ("team_metadata", "team_code"),
    )
    for _tbl, _col in _tc_alters:
        _tcols = {r["name"] for r in conn.execute(f"PRAGMA table_info({_tbl})")}
        if _tcols and _col not in _tcols:
            conn.execute(f"ALTER TABLE {_tbl} ADD COLUMN {_col} TEXT")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_fixtures_team_codes ON fixtures(home_team_code, away_team_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fstats_team_code ON fixture_statistics(team_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_enr_team_code ON team_enrichments(team_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_meta_team_code ON team_metadata(team_code)")
    if get_schema_version(conn) < 4:
        backfill_team_codes(conn)
    if get_schema_version(conn) < SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")



class PersistentStateDict:
    """دیکشنری سبک با پشتوانهٔ SQLite برای ماندگاری وضعیت‌های تعاملی ربات پس از ری‌استارت (OPS-03)."""

    def __init__(self, namespace: str, *, key_type: type = int) -> None:
        self._ns = namespace
        self._key_type = key_type
        self._mem: dict = {}
        self._loaded = False

    def _to_key(self, raw: str):
        if self._key_type is int:
            try:
                return int(raw)
            except (TypeError, ValueError):
                return raw
        return str(raw)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            if not DATABASE_PATH.exists():
                return
            import json as _json
            with db() as conn:
                rows = conn.execute(
                    "SELECT state_key, value_json FROM bot_kv_state WHERE namespace = ?",
                    (self._ns,),
                ).fetchall()
            for r in rows:
                try:
                    self._mem[self._to_key(r["state_key"])] = _json.loads(r["value_json"])
                except Exception:
                    pass
        except Exception:
            pass

    def _persist_set(self, key, value) -> None:
        try:
            import json as _json
            from datetime import datetime, timezone
            payload = _json.dumps(value, ensure_ascii=False, default=str)
            now = datetime.now(timezone.utc).isoformat()
            DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with db() as conn:
                conn.execute(_BOT_KV_STATE_DDL)
                conn.execute(
                    "INSERT OR REPLACE INTO bot_kv_state (namespace, state_key, value_json, updated_at) VALUES (?, ?, ?, ?)",
                    (self._ns, str(key), payload, now),
                )
        except Exception:
            pass

    def _persist_del(self, key) -> None:
        try:
            if not DATABASE_PATH.exists():
                return
            with db() as conn:
                conn.execute(
                    "DELETE FROM bot_kv_state WHERE namespace = ? AND state_key = ?",
                    (self._ns, str(key)),
                )
        except Exception:
            pass

    def __getitem__(self, key):
        self._ensure_loaded()
        return self._mem[key]

    def __setitem__(self, key, value) -> None:
        self._ensure_loaded()
        self._mem[key] = value
        self._persist_set(key, value)

    def __delitem__(self, key) -> None:
        self._ensure_loaded()
        del self._mem[key]
        self._persist_del(key)

    def __contains__(self, key) -> bool:
        self._ensure_loaded()
        return key in self._mem

    def __len__(self) -> int:
        self._ensure_loaded()
        return len(self._mem)

    def __iter__(self):
        self._ensure_loaded()
        return iter(self._mem)

    def get(self, key, default=None):
        self._ensure_loaded()
        return self._mem.get(key, default)

    def pop(self, key, *args):
        self._ensure_loaded()
        existed = key in self._mem
        val = self._mem.pop(key, *args)
        if existed:
            self._persist_del(key)
        return val

    def clear(self) -> None:
        self._ensure_loaded()
        self._mem.clear()
        try:
            if DATABASE_PATH.exists():
                with db() as conn:
                    conn.execute("DELETE FROM bot_kv_state WHERE namespace = ?", (self._ns,))
        except Exception:
            pass

    def items(self):
        self._ensure_loaded()
        return self._mem.items()

    def keys(self):
        self._ensure_loaded()
        return self._mem.keys()

    def values(self):
        self._ensure_loaded()
        return self._mem.values()



def record_post_metric(
    card_type: str,
    admin_decision: str,
    *,
    post_id: int | None = None,
    tone: str | None = None,
    edit_count: int = 0,
    llm_provider: str | None = None,
    render_ms: int | None = None,
    notes: str | None = None,
) -> int:
    """ثبت متریک تصمیم ادمین و خروجی پست برای تحلیل کیفیت و یادگیری تدریجی ترجیحات."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO post_metrics
              (post_id, card_type, tone, admin_decision, edit_count, llm_provider, render_ms, notes, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (post_id, card_type, tone, admin_decision, int(edit_count or 0), llm_provider, render_ms, notes, now),
        )
        return int(cur.lastrowid or 0)


def get_post_metrics_summary(days: int = 30) -> dict:
    """خلاصهٔ آماری تصمیم‌های ادمین (نرخ تایید به تفکیک نوع کارت و لحن در بازهٔ اخیر)."""
    from datetime import datetime, timedelta, timezone

    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, days))).isoformat()
    by_decision: dict[str, int] = {}
    by_card: dict[str, dict[str, int | float]] = {}
    total = 0
    total_edits = 0
    with db() as conn:
        rows = conn.execute(
            "SELECT card_type, admin_decision, edit_count FROM post_metrics WHERE recorded_at >= ?",
            (cutoff,),
        ).fetchall()
    for r in rows:
        total += 1
        dec = str(r["admin_decision"] or "unknown")
        ct = str(r["card_type"] or "unknown")
        ed = int(r["edit_count"] or 0)
        total_edits += ed
        by_decision[dec] = by_decision.get(dec, 0) + 1
        bucket = by_card.setdefault(ct, {"approved": 0, "rejected": 0, "edited": 0, "total": 0})
        bucket["total"] = int(bucket["total"]) + 1
        if dec in ("approved", "rejected", "edited"):
            bucket[dec] = int(bucket[dec]) + 1
    for ct, b in by_card.items():
        denom = int(b["approved"]) + int(b["rejected"])
        b["approval_rate"] = round((int(b["approved"]) * 100.0 / denom), 1) if denom > 0 else 0.0
    return {
        "days": days,
        "total": total,
        "total_edits": total_edits,
        "by_decision": by_decision,
        "by_card_type": by_card,
    }



from functools import lru_cache as _lru_cache


@_lru_cache(maxsize=2048)
def resolve_team_code(raw_team: str | None) -> str | None:
    """نگاشت کش‌شدهٔ نام تیم به کد سه‌حرفی استاندارد (مثلاً ARS، RMA، NEW)."""
    if not raw_team:
        return None
    try:
        from src.xgpedia.config import canonical_team_name, team_identity
        canon = canonical_team_name(str(raw_team))
        ident = team_identity(canon) or team_identity(str(raw_team))
        if ident and ident.get("code"):
            return str(ident["code"]).upper()
    except Exception:
        return None
    return None


def backfill_team_codes(conn: sqlite3.Connection) -> int:
    """پرکردن سریع، دسته‌ای (DISTINCT) و بدون افت دادهٔ ستون‌های team_code روی ردیف‌های موجود."""
    updated = 0
    for tbl, h_col, a_col in (
        ("fixtures", "home_team", "away_team"),
        ("fixture_odds", "home_team", "away_team"),
    ):
        for col, code_col in ((h_col, "home_team_code"), (a_col, "away_team_code")):
            distinct_teams = [
                r[0]
                for r in conn.execute(f"SELECT DISTINCT {col} FROM {tbl} WHERE {code_col} IS NULL AND {col} IS NOT NULL")
            ]
            for raw in distinct_teams:
                code = resolve_team_code(raw)
                if code:
                    cur = conn.execute(
                        f"UPDATE {tbl} SET {code_col} = ? WHERE {col} = ? AND {code_col} IS NULL",
                        (code, raw),
                    )
                    updated += int(cur.rowcount or 0)
    for tbl in ("fixture_statistics", "team_enrichments", "team_metadata"):
        distinct_teams = [
            r[0]
            for r in conn.execute(f"SELECT DISTINCT team FROM {tbl} WHERE team_code IS NULL AND team IS NOT NULL")
        ]
        for raw in distinct_teams:
            code = resolve_team_code(raw)
            if code:
                cur = conn.execute(
                    f"UPDATE {tbl} SET team_code = ? WHERE team = ? AND team_code IS NULL",
                    (code, raw),
                )
                updated += int(cur.rowcount or 0)
    return updated

if __name__ == "__main__":
    import sys as _sys
    init_db()
    if "--migrate-teams" in _sys.argv:
        with db() as _c:
            _n = backfill_team_codes(_c)
        print(f"OK - migrated team_code on {_n} rows at {DATABASE_PATH} (schema v{SCHEMA_VERSION})")
    else:
        print(f"OK - database initialized at {DATABASE_PATH} (schema v{SCHEMA_VERSION})")
