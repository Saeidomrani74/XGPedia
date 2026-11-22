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

import sqlite3
from contextlib import contextmanager

from src.xgpedia.config import DATABASE_PATH

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
  status TEXT NOT NULL DEFAULT 'scheduled',
  matchday INTEGER,
  raw_payload_hash TEXT,
  collected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fixture_statistics (
  fixture_id TEXT NOT NULL,
  team TEXT NOT NULL,
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

CREATE TABLE IF NOT EXISTS team_metadata (
  team TEXT NOT NULL,
  season TEXT NOT NULL,
  venue_en TEXT,
  coach_en TEXT,
  provider TEXT NOT NULL,
  collected_at TEXT NOT NULL,
  PRIMARY KEY (team, season, provider)
);

CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
CREATE INDEX IF NOT EXISTS idx_fixtures_kickoff ON fixtures(kickoff_utc);
CREATE INDEX IF NOT EXISTS idx_scheduled_status_time ON scheduled_publishes(status, scheduled_at_utc);
"""


@contextmanager
def db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
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


def _migrate(conn: sqlite3.Connection) -> None:
    """مهاجرت سبک و idempotent برای DBهای نسخه‌های قبل."""
    fx_cols = {r["name"] for r in conn.execute("PRAGMA table_info(fixtures)")}
    if "matchday" not in fx_cols:
        conn.execute("ALTER TABLE fixtures ADD COLUMN matchday INTEGER")
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(posts)")}
    if "draft_json" not in cols:
        conn.execute("ALTER TABLE posts ADD COLUMN draft_json TEXT")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduled_publishes (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          post_id INTEGER NOT NULL REFERENCES posts(post_id),
          scheduled_at_utc TEXT NOT NULL,
          scheduled_time_tehran TEXT NOT NULL,
          scheduled_by_admin INTEGER NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending',
          error_detail TEXT,
          created_at TEXT NOT NULL,
          executed_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fixture_odds (
          home_team TEXT NOT NULL,
          away_team TEXT NOT NULL,
          match_date TEXT NOT NULL,
          home_odds REAL,
          draw_odds REAL,
          away_odds REAL,
          over25_odds REAL,
          btts_odds REAL,
          provider TEXT NOT NULL,
          collected_at TEXT NOT NULL,
          PRIMARY KEY (home_team, away_team, match_date, provider)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS team_enrichments (
          team TEXT NOT NULL,
          season TEXT NOT NULL,
          key_player_json TEXT,
          ppda REAL,
          deep_passes REAL,
          provider TEXT NOT NULL,
          collected_at TEXT NOT NULL,
          PRIMARY KEY (team, season, provider)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_scheduled_status_time "
        "ON scheduled_publishes(status, scheduled_at_utc)"
    )


if __name__ == "__main__":
    init_db()
    print(f"OK - database initialized at {DATABASE_PATH}")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fixture_broadcasts (
          fixture_id TEXT PRIMARY KEY,
          channel_label TEXT NOT NULL,
          program_title TEXT,
          broadcast_time TEXT,
          tehran_date TEXT NOT NULL,
          collected_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_cache (
          source_key TEXT PRIMARY KEY,
          tehran_date TEXT NOT NULL,
          last_synced_at TEXT NOT NULL,
          summary TEXT
        )
        """
    )
    conn.execute("""
CREATE TABLE IF NOT EXISTS team_metadata (
  team TEXT NOT NULL,
  season TEXT NOT NULL,
  venue_en TEXT,
  coach_en TEXT,
  provider TEXT NOT NULL,
  collected_at TEXT NOT NULL,
  PRIMARY KEY (team, season, provider)
);
    """)
    enr_cols = {r["name"] for r in conn.execute("PRAGMA table_info(team_enrichments)")}
    if "wave_json" not in enr_cols:
        conn.execute("ALTER TABLE team_enrichments ADD COLUMN wave_json TEXT")
