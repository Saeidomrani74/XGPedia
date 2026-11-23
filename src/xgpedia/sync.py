"""لایهٔ همگام‌سازی — پرکردن پایگاه داده از دو provider (نسخهٔ ۸).

جریان:
  ۱) sync-results: CSV football-data.co.uk → جدول‌های fixtures + fixture_statistics
  ۲) fixtures: API football-data.org → بازی‌های پیش‌رو در fixtures
  ۳) build-facts: ساخت MatchFacts (JSON واقعیت‌ها) برای یک بازی از DB

قواعد حیاتی:
  - idempotency: کلید (fixture_id, team, metric, provider)؛ اجرای دوباره رکورد تکراری نمی‌سازد.
  - null≠0: ردیفی که CSV مقدار نداد، اصلاً درج نمی‌شود (نه با مقدار صفر).
  - provider تفکیک‌شده: هر متریک با نام provider خودش ذخیره می‌شود.
"""
from __future__ import annotations

from src.xgpedia.config import translate_coach_fa

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from src.xgpedia.config import (
    CURRENT_SEASON_START,
    PRIMARY_FIXTURES_PROVIDER,
    PRIMARY_STATS_PROVIDER,
    canonical_team_name,
    team_name_fa,
    team_venue,
    translate_coach_fa,
)
from src.xgpedia.db import db


def season_label(start_year: int) -> str:
    """برچسب فصل به سبک سند: ۲۰۲۶ (سال شروع) → «2026-27»."""
    return f"{start_year}-{str(start_year + 1)[2:]}"


def fixture_id_for_csv(row_date: str, home: str, away: str) -> str:
    """شناسهٔ پایدار مسابقهٔ CSV — از تاریخ و دو تیم؛ بدون وابستگی به provider ID."""
    return f"fdcouk:{row_date}:{home}:{away}"


# ─── ۱) sync-results: CSV → DB ───

def sync_csv_results(rows, payload_hash: str, season_start: int = CURRENT_SEASON_START) -> dict:
    """درج ردیف‌های نرمال‌شدهٔ CSV در DB — idempotent.

    rows: خروجی FootballDataCoUk.parse_season (لیست CsvMatchRow)
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    season = season_label(season_start)
    stats_pairs = [
        # (متریک سمت خانگی, متریک سمت میهمانی, کلید داخلی)
        ("total_shots", "total_shots_away", "total_shots"),
        ("shots_on_target", "shots_on_target_away", "shots_on_target"),
        ("corner_kicks", "corner_kicks_away", "corner_kicks"),
        ("fouls", "fouls_away", "fouls"),
        ("yellow_cards", "yellow_cards_away", "yellow_cards"),
        ("red_cards", "red_cards_away", "red_cards"),
    ]
    inserted_fx = updated_fx = inserted_stats = 0

    with db() as conn:
        for r in rows:
            fid = fixture_id_for_csv(r.date_utc, r.home_team, r.away_team)
            existed = conn.execute(
                "SELECT 1 FROM fixtures WHERE fixture_id = ?", (fid,)
            ).fetchone()
            conn.execute(
                """
                INSERT INTO fixtures (fixture_id, provider, competition, season, kickoff_utc,
                                      home_team, away_team, status, raw_payload_hash, collected_at)
                VALUES (?, ?, 'Premier League', ?, ?, ?, ?, 'finished', ?, ?)
                ON CONFLICT(fixture_id) DO UPDATE SET
                  status='finished', raw_payload_hash=excluded.raw_payload_hash,
                  collected_at=excluded.collected_at
                """,
                (fid, PRIMARY_STATS_PROVIDER, season, r.date_utc, r.home_team, r.away_team,
                 payload_hash, now),
            )
            if existed:
                updated_fx += 1
            else:
                inserted_fx += 1

            # آمار: هر سوی هر متریک فقط با مقدار موجود (None → درج نمی‌شود)
            def upsert_stat(team: str, metric: str, value: float | None) -> None:
                nonlocal inserted_stats
                if value is None:
                    return  # قاعدهٔ null≠0
                stat_existed = conn.execute(
                    "SELECT 1 FROM fixture_statistics WHERE fixture_id=? AND team=? AND metric=? AND provider=?",
                    (fid, team, metric, PRIMARY_STATS_PROVIDER),
                ).fetchone()
                conn.execute(
                    """
                    INSERT INTO fixture_statistics (fixture_id, team, metric, value, provider, collected_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(fixture_id, team, metric, provider) DO UPDATE SET
                      value=excluded.value, collected_at=excluded.collected_at
                    """,
                    (fid, team, metric, value, PRIMARY_STATS_PROVIDER, now),
                )
                if not stat_existed:
                    inserted_stats += 1

            for home_col, away_col, key in stats_pairs:
                upsert_stat(r.home_team, key, r.stats.get(home_col))
                upsert_stat(r.away_team, key, r.stats.get(away_col))

            upsert_stat(r.home_team, "expected_goals", r.home_xg)
            upsert_stat(r.away_team, "expected_goals", r.away_xg)
            upsert_stat(r.home_team, "goals", float(r.home_goals))
            upsert_stat(r.away_team, "goals", float(r.away_goals))

    return {"fixtures_new": inserted_fx, "fixtures_updated": updated_fx, "stats_rows": inserted_stats}


# ─── ۲) fixtures از football-data.org → DB ───

def sync_upcoming_fixtures(raw, season_start: int = CURRENT_SEASON_START) -> dict:
    """بازی‌های پیش‌رو از API v4 → جدول fixtures — idempotent."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    season = season_label(season_start)
    inserted = 0
    with db() as conn:
        for m in raw.payload.get("matches", []):
            fid = f"fdo:{m['id']}"
            home = canonical_team_name(m["homeTeam"]["name"], m["homeTeam"].get("id"))
            away = canonical_team_name(m["awayTeam"]["name"], m["awayTeam"].get("id"))
            kickoff = m["utcDate"]  # ISO-8601 UTC
            matchday = m.get("matchday")
            existed = conn.execute(
                "SELECT 1 FROM fixtures WHERE fixture_id = ?", (fid,)
            ).fetchone()
            conn.execute(
                """
                INSERT INTO fixtures (fixture_id, provider, competition, season, kickoff_utc,
                                      home_team, away_team, status, matchday, raw_payload_hash, collected_at)
                VALUES (?, ?, 'Premier League', ?, ?, ?, ?, 'scheduled', ?, ?, ?)
                ON CONFLICT(fixture_id) DO UPDATE SET
                  home_team=excluded.home_team, away_team=excluded.away_team,
                  kickoff_utc=excluded.kickoff_utc, status='scheduled',
                  matchday=COALESCE(excluded.matchday, fixtures.matchday),
                  raw_payload_hash=excluded.raw_payload_hash, collected_at=excluded.collected_at
                """,
                (fid, PRIMARY_FIXTURES_PROVIDER, season, kickoff, home, away,
                 int(matchday) if matchday is not None else None, raw.payload_hash, now),
            )
            if not existed:
                inserted += 1
    return {"upcoming_new": inserted, "total_in_payload": len(raw.payload.get("matches", []))}


# ─── ۲ب) همگام‌سازی ضرایب رایگان بازار + داده‌های Understat (v0.14.0) ───

def sync_upcoming_odds(odds_rows: list[dict], provider: str = PRIMARY_STATS_PROVIDER) -> dict:
    """ذخیرهٔ ضرایب واقعی بازی‌های پیش‌رو در جدول fixture_odds (idempotent)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    saved = 0
    with db() as conn:
        for r in odds_rows:
            conn.execute(
                """
                INSERT INTO fixture_odds
                  (home_team, away_team, match_date, home_odds, draw_odds, away_odds, over25_odds, btts_odds, provider, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(home_team, away_team, match_date, provider) DO UPDATE SET
                  home_odds=excluded.home_odds, draw_odds=excluded.draw_odds,
                  away_odds=excluded.away_odds, over25_odds=excluded.over25_odds,
                  btts_odds=excluded.btts_odds, collected_at=excluded.collected_at
                """,
                (
                    r["home_team"], r["away_team"], r["match_date"],
                    r.get("home_odds"), r.get("draw_odds"), r.get("away_odds"),
                    r.get("over25_odds"), r.get("btts_odds"), provider, now,
                ),
            )
            saved += 1
    return {"odds_saved": saved}


def sync_understat_league(league_data: dict, season_start: int = CURRENT_SEASON_START) -> dict:
    """ذخیرهٔ مهره‌های کلیدی و PPDA/Deep تیم‌ها از Understat در team_enrichments (idempotent)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    season = season_label(season_start)
    key_players = league_data.get("key_players") or {}
    team_metrics = league_data.get("team_metrics") or {}
    teams = sorted(set(key_players) | set(team_metrics))
    saved = 0
    with db() as conn:
        for team in teams:
            kp = key_players.get(team)
            tm = team_metrics.get(team) or {}
            conn.execute(
                """
                INSERT INTO team_enrichments
                  (team, season, key_player_json, ppda, deep_passes, provider, collected_at)
                VALUES (?, ?, ?, ?, ?, 'understat', ?)
                ON CONFLICT(team, season, provider) DO UPDATE SET
                  key_player_json=COALESCE(excluded.key_player_json, team_enrichments.key_player_json),
                  ppda=COALESCE(excluded.ppda, team_enrichments.ppda),
                  deep_passes=COALESCE(excluded.deep_passes, team_enrichments.deep_passes),
                  collected_at=excluded.collected_at
                """,
                (
                    team, season,
                    json.dumps(kp, ensure_ascii=False) if kp else None,
                    tm.get("ppda"), tm.get("deep"), now,
                ),
            )
            saved += 1
    return {"teams_enriched": saved, "key_players": len(key_players)}


def _team_enrichment_from_db(conn: sqlite3.Connection, team: str, season: str) -> dict:
    """خواندن مهرهٔ کلیدی، PPDA/Deep و موج زمانی ۱۵ دقیقه‌ای از همهٔ منابع رایگان ذخیره‌شده."""
    try:
        rows = conn.execute(
            """
            SELECT key_player_json, ppda, deep_passes, wave_json, provider
            FROM team_enrichments
            WHERE team = ? AND season = ?
            ORDER BY CASE provider WHEN 'understat' THEN 1 WHEN 'fpl-official' THEN 2 WHEN 'football-data-org' THEN 3 WHEN 'espn-public' THEN 4 ELSE 5 END, collected_at DESC
            """,
            (team, season),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    if not rows:
        return {}
    out: dict = {}
    for row in rows:
        if "kp" not in out and row["key_player_json"]:
            try:
                out["kp"] = json.loads(row["key_player_json"])
            except Exception:
                pass
        if "ppda" not in out and row["ppda"] is not None:
            out["ppda"] = float(row["ppda"])
        if "deep" not in out and row["deep_passes"] is not None:
            out["deep"] = float(row["deep_passes"])
        if "wave" not in out and row["wave_json"]:
            try:
                wv = json.loads(row["wave_json"])
                if isinstance(wv, list) and len(wv) == 6:
                    out["wave"] = [float(x) for x in wv]
            except Exception:
                pass
    return out


def _fixture_odds_from_db(conn: sqlite3.Connection, home: str, away: str, match_date: str) -> dict[str, float] | None:
    """خواندن ضرایب واقعی بازار برای بازی از جدول fixture_odds (در صورت وجود)."""
    try:
        row = conn.execute(
            """
            SELECT home_odds, draw_odds, away_odds, over25_odds, btts_odds
            FROM fixture_odds
            WHERE home_team = ? AND away_team = ? AND ABS(julianday(match_date) - julianday(?)) <= 2
            ORDER BY collected_at DESC LIMIT 1
            """,
            (home, away, match_date[:10]),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if not row:
        return None
    out: dict[str, float] = {}
    for col, key in (
        ("home_odds", "home"), ("draw_odds", "draw"), ("away_odds", "away"),
        ("over25_odds", "over25"), ("btts_odds", "btts"),
    ):
        if row[col] is not None and float(row[col]) > 1.0:
            out[key] = float(row[col])
    return out or None


def _compute_league_radar_percentiles(
    conn: sqlite3.Connection, before_date: str, season: str
) -> dict[str, list[int]]:
    """محاسبهٔ رادار ۶ محوره تاکتیکی بر اساس صدک واقعی بین تیم‌های لیگ در DB.

    ۶ محور مطابق استودیو:
      0: خلق موقعیت (xG تولیدی در هر بازی)
      1: شدت پرس (معکوس PPDA از Understat؛ یا معکوس شوت دریافتی از DB)
      2: ایستگاهی (کرنر در هر بازی)
      3: صلابت دفاعی (معکوس xGA دریافتی در هر بازی)
      4: مالکیت مؤثر (سهم شوت یا پاس عمقی Understat)
      5: تهدید پاس / ضربه (شوت در چارچوب در هر بازی)
    برای اعتبار آماری حداقل ۶ تیم با بازی تمام‌شده در DB لازم است؛ وگرنه {} برمی‌گردد.
    """
    rows = conn.execute(
        """
        SELECT s.team, s.metric, AVG(s.value) AS avg_val
        FROM fixture_statistics s
        JOIN fixtures f ON f.fixture_id = s.fixture_id
        WHERE f.status = 'finished' AND f.kickoff_utc < ? AND s.provider = ?
          AND s.metric IN ('expected_goals', 'total_shots', 'shots_on_target', 'corner_kicks')
        GROUP BY s.team, s.metric
        """,
        (before_date, PRIMARY_STATS_PROVIDER),
    ).fetchall()
    team_for: dict[str, dict[str, float]] = {}
    for r in rows:
        team_for.setdefault(r["team"], {})[r["metric"]] = float(r["avg_val"])

    # آمار حریفان (xGA و شوت دریافتی)
    against_rows = conn.execute(
        """
        SELECT
          CASE WHEN f.home_team = s.team THEN f.away_team ELSE f.home_team END AS defending_team,
          s.metric,
          AVG(s.value) AS avg_val
        FROM fixture_statistics s
        JOIN fixtures f ON f.fixture_id = s.fixture_id
        WHERE f.status = 'finished' AND f.kickoff_utc < ? AND s.provider = ?
          AND s.metric IN ('expected_goals', 'total_shots')
        GROUP BY defending_team, s.metric
        """,
        (before_date, PRIMARY_STATS_PROVIDER),
    ).fetchall()
    team_against: dict[str, dict[str, float]] = {}
    for r in against_rows:
        team_against.setdefault(r["defending_team"], {})[r["metric"]] = float(r["avg_val"])

    # داده‌های اختیاری Understat (PPDA و deep)
    enrich_map: dict[str, dict[str, float]] = {}
    try:
        for r in conn.execute(
            "SELECT team, ppda, deep_passes FROM team_enrichments WHERE season = ?", (season,)
        ).fetchall():
            enrich_map[r["team"]] = {"ppda": r["ppda"], "deep": r["deep_passes"]}
    except sqlite3.OperationalError:
        pass

    valid_teams = [
        t for t, d in team_for.items()
        if all(k in d for k in ("expected_goals", "total_shots", "shots_on_target", "corner_kicks"))
        and "expected_goals" in team_against.get(t, {})
        and "total_shots" in team_against.get(t, {})
    ]
    if len(valid_teams) < 6:
        return {}

    use_ppda = all(enrich_map.get(t, {}).get("ppda") for t in valid_teams)
    use_deep = all(enrich_map.get(t, {}).get("deep") is not None for t in valid_teams)

    raw_axes: dict[str, list[float]] = {}
    for t in valid_teams:
        tf = team_for[t]
        ta = team_against[t]
        ax0 = tf["expected_goals"]
        ax1 = -float(enrich_map[t]["ppda"]) if use_ppda else -ta["total_shots"]
        ax2 = tf["corner_kicks"]
        ax3 = -ta["expected_goals"]
        ax4 = (
            float(enrich_map[t]["deep"])
            if use_deep
            else tf["total_shots"] / max(tf["total_shots"] + ta["total_shots"], 0.1)
        )
        ax5 = tf["shots_on_target"]
        raw_axes[t] = [ax0, ax1, ax2, ax3, ax4, ax5]

    n = len(valid_teams)
    radar_by_team: dict[str, list[int]] = {t: [0] * 6 for t in valid_teams}
    for axis in range(6):
        ordered = sorted(valid_teams, key=lambda t: raw_axes[t][axis])
        for rank, t in enumerate(ordered):
            pct = round(25 + (rank / max(n - 1, 1)) * 74)  # بازهٔ خوانا و واقعی ۲۵ تا ۹۹
            radar_by_team[t][axis] = int(pct)
    return radar_by_team

# ─── ۳) ساخت MatchFacts از DB ───

def last5_from_db(conn: sqlite3.Connection, team: str, before_date: str) -> dict | None:
    """۵ بازی اخیر تیم قبل از تاریخ داده‌شده — برای فرم."""
    rows = conn.execute(
        """
        SELECT kickoff_utc, home_team, away_team,
               MAX(CASE WHEN team=home_team THEN value END) AS hg,
               MAX(CASE WHEN team=away_team THEN value END) AS ag
        FROM fixtures f
        JOIN fixture_statistics s
          ON s.fixture_id = f.fixture_id AND s.metric = 'goals' AND s.provider = ?
        WHERE f.status = 'finished' AND f.kickoff_utc < ?
          AND (f.home_team = ? OR f.away_team = ?)
        GROUP BY f.fixture_id
        ORDER BY f.kickoff_utc DESC
        LIMIT 5
        """,
        (PRIMARY_STATS_PROVIDER, before_date, team, team),
    ).fetchall()
    if not rows:
        return None
    points = 0
    gf = ga = 0
    for row in rows:
        home_goals, away_goals = row["hg"], row["ag"]
        if home_goals is None or away_goals is None:
            continue
        is_home = row["home_team"] == team
        my, opp = (home_goals, away_goals) if is_home else (away_goals, home_goals)
        gf += my
        ga += opp
        points += 3 if my > opp else (1 if my == opp else 0)
    return {"n": len(rows), "points": points, "goals_for": gf, "goals_against": ga}


def _team_xg_avg(conn: sqlite3.Connection, team: str, before_date: str) -> dict | None:
    """میانگین xG تیم در بازی‌های خانگی+میهمانی — یک provider واحد."""
    rows = conn.execute(
        """
        SELECT s.value
        FROM fixture_statistics s
        JOIN fixtures f ON f.fixture_id = s.fixture_id
        WHERE s.metric = 'expected_goals' AND s.provider = ? AND s.team = ?
          AND f.status = 'finished' AND f.kickoff_utc < ?
        ORDER BY f.kickoff_utc DESC
        LIMIT 10
        """,
        (PRIMARY_STATS_PROVIDER, team, before_date),
    ).fetchall()
    if not rows:
        return None
    return {"n": len(rows), "avg": sum(r["value"] for r in rows) / len(rows)}


def _team_corners_avg(conn: sqlite3.Connection, team: str, before_date: str) -> dict | None:
    rows = conn.execute(
        """
        SELECT s.value
        FROM fixture_statistics s
        JOIN fixtures f ON f.fixture_id = s.fixture_id
        WHERE s.metric = 'corner_kicks' AND s.provider = ? AND s.team = ?
          AND f.status = 'finished' AND f.kickoff_utc < ?
        ORDER BY f.kickoff_utc DESC
        LIMIT 10
        """,
        (PRIMARY_STATS_PROVIDER, team, before_date),
    ).fetchall()
    if not rows:
        return None
    return {"n": len(rows), "avg": sum(r["value"] for r in rows) / len(rows)}


def _team_xga_avg(conn: sqlite3.Connection, team: str, before_date: str) -> dict | None:
    """میانگین xG حریفان در بازی‌های تیم (xGA) — از ردیف xG حریف در همان بازی، همان provider."""
    rows = conn.execute(
        """
        SELECT s.value
        FROM fixture_statistics s
        JOIN fixtures f ON f.fixture_id = s.fixture_id
        WHERE s.metric = 'expected_goals' AND s.provider = ?
          AND f.status = 'finished' AND f.kickoff_utc < ?
          AND s.team = CASE WHEN f.home_team = ? THEN f.away_team ELSE f.home_team END
          AND (f.home_team = ? OR f.away_team = ?)
        ORDER BY f.kickoff_utc DESC
        LIMIT 10
        """,
        (PRIMARY_STATS_PROVIDER, before_date, team, team, team),
    ).fetchall()
    if not rows:
        return None
    return {"n": len(rows), "avg": sum(r["value"] for r in rows) / len(rows)}


def _team_sot_avg(conn: sqlite3.Connection, team: str, before_date: str) -> dict | None:
    """میانگین شوت در چارچوب — CSV football-data.co.uk ستون HST/AST."""
    rows = conn.execute(
        """
        SELECT s.value
        FROM fixture_statistics s
        JOIN fixtures f ON f.fixture_id = s.fixture_id
        WHERE s.metric = 'shots_on_target' AND s.provider = ? AND s.team = ?
          AND f.status = 'finished' AND f.kickoff_utc < ?
        ORDER BY f.kickoff_utc DESC
        LIMIT 10
        """,
        (PRIMARY_STATS_PROVIDER, team, before_date),
    ).fetchall()
    if not rows:
        return None
    return {"n": len(rows), "avg": sum(r["value"] for r in rows) / len(rows)}


def _team_xg_series(
    conn: sqlite3.Connection, team: str, before_date: str, limit: int = 10, season: str | None = None
) -> list[float] | None:
    """xG بازی‌به‌بازی تیم در فصل جاری (قدیمی‌ترین → جدیدترین) — دادهٔ ماژول «روند ۱۰ بازی اخیر»."""
    rows = []
    if season:
        rows = conn.execute(
            """
            SELECT s.value
            FROM fixture_statistics s
            JOIN fixtures f ON f.fixture_id = s.fixture_id
            WHERE s.metric = 'expected_goals' AND s.provider = ? AND s.team = ?
              AND f.status = 'finished' AND f.season = ? AND f.kickoff_utc < ?
            ORDER BY f.kickoff_utc DESC
            LIMIT ?
            """,
            (PRIMARY_STATS_PROVIDER, team, season, before_date, limit),
        ).fetchall()
    if len(rows) < 2:
        rows = conn.execute(
            """
            SELECT s.value
            FROM fixture_statistics s
            JOIN fixtures f ON f.fixture_id = s.fixture_id
            WHERE s.metric = 'expected_goals' AND s.provider = ? AND s.team = ?
              AND f.status = 'finished' AND f.kickoff_utc < ?
            ORDER BY f.kickoff_utc DESC
            LIMIT ?
            """,
            (PRIMARY_STATS_PROVIDER, team, before_date, limit),
        ).fetchall()
    if not rows:
        return None
    return [round(r["value"], 2) for r in reversed(rows)]


def _team_form_sequence(conn: sqlite3.Connection, team: str, before_date: str, limit: int = 5) -> dict | None:
    """توالی ب/م/ش آخرین بازی‌ها (W/D/L؛ قدیمی‌ترین → جدیدترین) — دایره‌های فرم کارت."""
    rows = conn.execute(
        """
        SELECT kickoff_utc, home_team, away_team,
               MAX(CASE WHEN team=home_team THEN value END) AS hg,
               MAX(CASE WHEN team=away_team THEN value END) AS ag
        FROM fixtures f
        JOIN fixture_statistics s
          ON s.fixture_id = f.fixture_id AND s.metric = 'goals' AND s.provider = ?
        WHERE f.status = 'finished' AND f.kickoff_utc < ?
          AND (f.home_team = ? OR f.away_team = ?)
        GROUP BY f.fixture_id
        ORDER BY f.kickoff_utc DESC
        LIMIT ?
        """,
        (PRIMARY_STATS_PROVIDER, before_date, team, team, limit),
    ).fetchall()
    if not rows:
        return None
    letters = []
    for row in reversed(rows):
        hg, ag = row["hg"], row["ag"]
        if hg is None or ag is None:
            continue
        is_home = row["home_team"] == team
        my, opp = (hg, ag) if is_home else (ag, hg)
        letters.append("W" if my > opp else ("D" if my == opp else "L"))
    if not letters:
        return None
    return {"sequence": "".join(letters), "n": len(letters)}


def _match_metrics(conn: sqlite3.Connection, fixture_id: str, team: str) -> dict[str, float]:
    """آمار خودِ یک بازی برای یک تیم — {metric: value}؛ ردیف NULL اصلاً برنمی‌گردد."""
    rows = conn.execute(
        """
        SELECT metric, value FROM fixture_statistics
        WHERE fixture_id = ? AND team = ? AND provider = ? AND value IS NOT NULL
        """,
        (fixture_id, team, PRIMARY_STATS_PROVIDER),
    ).fetchall()
    return {r["metric"]: float(r["value"]) for r in rows}


def _creative_match_descriptor(
    home_en: str,
    away_en: str,
    home: TeamSide,
    away: TeamSide,
    *,
    post_match: bool = False,
) -> str:
    """تولید صفت توصیفی جذاب، خلاقانه و متناسب با هویت و آمار واقعی هر بازی برای هدر کارت."""
    if post_match:
        return "کالبدشکافی پس از بازی"

    pair = {canonical_team_name(home_en), canonical_team_name(away_en)}
    derbies: list[tuple[set[str], str]] = [
        ({"Arsenal", "Tottenham"}, "دربی شمال لندن"),
        ({"Manchester City", "Manchester United"}, "دربی منچستر"),
        ({"Liverpool", "Manchester United"}, "کلاسیکوی انگلیس"),
        ({"Liverpool", "Everton"}, "دربی مرسی‌ساید"),
        ({"Arsenal", "Chelsea"}, "دربی بزرگ لندن"),
        ({"Chelsea", "Tottenham"}, "دربی داغ لندن"),
        ({"Newcastle", "Sunderland"}, "دربی تاین-ویر"),
        ({"Manchester United", "Leeds"}, "دربی رزها"),
        ({"Liverpool", "Manchester City"}, "نبرد غول‌های لیگ"),
        ({"Arsenal", "Manchester City"}, "دوئل مدعیان قهرمانی"),
        ({"Arsenal", "Liverpool"}, "تقابل صدرنشینان"),
    ]
    for teams_set, lbl in derbies:
        if pair == teams_set:
            return lbl

    big6 = {"Arsenal", "Manchester City", "Liverpool", "Chelsea", "Manchester United", "Tottenham"}
    if len(pair & big6) == 2:
        return "نبرد سنگین‌وزن‌ها"

    h_xg = home.xg_for_avg.value if (home.xg_for_avg and home.xg_for_avg.value is not None) else None
    a_xg = away.xg_for_avg.value if (away.xg_for_avg and away.xg_for_avg.value is not None) else None
    h_pts = home.last5.points if (home.last5 and home.last5.points is not None) else None
    a_pts = away.last5.points if (away.last5 and away.last5.points is not None) else None

    if h_xg is not None and a_xg is not None:
        if h_xg >= 1.65 and a_xg >= 1.65:
            return "نبرد دو خط حمله آتشین"
        if h_xg <= 1.20 and a_xg <= 1.20:
            return "شطرنج تاکتیکی و بسته"
        if abs(h_xg - a_xg) <= 0.20:
            if h_pts is not None and a_pts is not None and h_pts >= 9 and a_pts >= 9:
                return "دوئل میلیمتری آماده‌ها"
            return "دوئل پایاپای تاکتیکی"
        if h_xg - a_xg >= 0.55:
            return "آزمون سخت در خانه حریف"
        if a_xg - h_xg >= 0.55:
            return "تهدید جدی میهمان"

    if h_pts is not None and a_pts is not None:
        if h_pts >= 10 and a_pts >= 10:
            return "تقابل دو تیم آماده"
        if h_pts <= 5 and a_pts <= 5:
            return "جدال حساس خروج از بحران"

    return "نبرد تاکتیکی هفته"


def build_match_facts(fixture_id: str, post_match: bool = False) -> dict:
    """ساخت «JSON واقعیت‌ها» برای یک بازی — تنها ورودی مجاز LLM و رندرر.

    post_match=True فقط برای بازی‌های پایان‌یافته: نتیجه + آمار خودِ بازی (match_stats)
    و روند/form شامل همین بازی. خروجی dict مطابق schema MatchFacts (models.py).
    """
    from src.xgpedia.analytics.metrics import evaluate_triggers
    from src.xgpedia.normalization.models import (
        DataQuality,
        Last5,
        MatchFacts,
        MatchResult,
        MatchStats,
        RecentForm,
        SourceInfo,
        StatValue,
        TeamSide,
    )

    with db() as conn:
        fx = conn.execute("SELECT * FROM fixtures WHERE fixture_id = ?", (fixture_id,)).fetchone()
        if fx is None:
            raise KeyError(f"fixture {fixture_id} not found in DB - run sync-results first")
        if post_match and fx["status"] != "finished":
            raise ValueError(
                f"fixture {fixture_id} is '{fx['status']}' - post_match facts need a finished match"
            )

        kickoff = fx["kickoff_utc"]
        if kickoff.endswith("Z"):
            kickoff_dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
        else:
            kickoff_dt = datetime.fromisoformat(kickoff)

        # روند/فرم: پیش‌بازی تا قبل از بازی؛ پس‌از‌بازی شامل خودِ بازی (روز بعدِ کیک‌آف)
        series_before = (
            (kickoff_dt + timedelta(days=1)).date().isoformat() if post_match else kickoff[:10]
        )

        def side(team: str) -> TeamSide:
            l5 = last5_from_db(conn, team, kickoff[:10])
            xg = _team_xg_avg(conn, team, kickoff[:10])
            corners = _team_corners_avg(conn, team, kickoff[:10])
            xga = _team_xga_avg(conn, team, kickoff[:10])
            sot = _team_sot_avg(conn, team, kickoff[:10])
            series = _team_xg_series(conn, team, series_before, season=fx['season'])
            form_seq = _team_form_sequence(conn, team, series_before)
            match_stats = None
            if post_match:
                mm = _match_metrics(conn, fixture_id, team)
                sv = lambda k: StatValue(value=mm[k], n=1, provider=PRIMARY_STATS_PROVIDER) if k in mm else None  # noqa: E731
                match_stats = MatchStats(
                    goals=sv("goals"),
                    expected_goals=sv("expected_goals"),
                    total_shots=sv("total_shots"),
                    shots_on_target=sv("shots_on_target"),
                    corner_kicks=sv("corner_kicks"),
                    fouls=sv("fouls"),
                    yellow_cards=sv("yellow_cards"),
                    red_cards=sv("red_cards"),
                )
            return TeamSide(
                name_fa=team_name_fa(team),
                name_en=team,
                last5=Last5(**l5) if l5 else None,
                xg_for_avg=StatValue(
                    value=round(xg["avg"], 2), n=xg["n"], provider=PRIMARY_STATS_PROVIDER
                ) if xg else None,
                corners_avg=StatValue(
                    value=round(corners["avg"], 1), n=corners["n"], provider=PRIMARY_STATS_PROVIDER
                ) if corners else None,
                xg_against_avg=StatValue(
                    value=round(xga["avg"], 2), n=xga["n"], provider=PRIMARY_STATS_PROVIDER
                ) if xga else None,
                sot_avg=StatValue(
                    value=round(sot["avg"], 1), n=sot["n"], provider=PRIMARY_STATS_PROVIDER
                ) if sot else None,
                xg_series=series,
                recent_form=RecentForm(**form_seq) if form_seq else None,
                match_stats=match_stats,
            )

        radar_map = _compute_league_radar_percentiles(conn, kickoff[:10], fx["season"]) if not post_match else {}
        home_canon = canonical_team_name(fx["home_team"])
        away_canon = canonical_team_name(fx["away_team"])
        home = side(home_canon)
        away = side(away_canon)
        if not post_match:
            if home_canon in radar_map and away_canon in radar_map:
                home.radar = radar_map[home_canon]
                away.radar = radar_map[away_canon]
            h_enr = _team_enrichment_from_db(conn, home_canon, fx["season"])
            a_enr = _team_enrichment_from_db(conn, away_canon, fx["season"])
            if h_enr.get("kp"):
                home.kp = h_enr["kp"]
            if a_enr.get("kp"):
                away.kp = a_enr["kp"]
            if h_enr.get("wave"):
                home.wave = h_enr["wave"]
            if a_enr.get("wave"):
                away.wave = a_enr["wave"]
        market_odds = _fixture_odds_from_db(conn, home_canon, away_canon, kickoff[:10]) if not post_match else None

        result = None
        if post_match:
            hg = home.match_stats.goals.value if home.match_stats and home.match_stats.goals else None
            ag = away.match_stats.goals.value if away.match_stats and away.match_stats.goals else None
            result = MatchResult(home_goals=int(hg) if hg is not None else None,
                                 away_goals=int(ag) if ag is not None else None)

        missing = []
        if home.xg_for_avg is None:
            missing.append("home.xg_for_avg")
        if away.xg_for_avg is None:
            missing.append("away.xg_for_avg")
        if home.last5 is None or home.last5.n < 5:
            missing.append("home.last5")
        if away.last5 is None or away.last5.n < 5:
            missing.append("away.last5")
        if post_match:
            if home.match_stats is None or home.match_stats.expected_goals is None:
                missing.append("home.match_stats.expected_goals")
            if away.match_stats is None or away.match_stats.expected_goals is None:
                missing.append("away.match_stats.expected_goals")

        fx_matchday = fx["matchday"] if "matchday" in fx.keys() else None
        if fx_matchday is None:
            # برآورد شماره هفته از تعداد بازی‌های تمام‌شدهٔ تیم میزبان + ۱ (وقتی matchday در DB نبود)
            cnt_row = conn.execute(
                "SELECT COUNT(*) AS c FROM fixtures WHERE status='finished' AND season=? AND (home_team=? OR away_team=?)",
                (fx["season"], home_canon, home_canon),
            ).fetchone()
            if cnt_row and cnt_row["c"] > 0:
                fx_matchday = int(cnt_row["c"]) + (0 if post_match else 1)
        h_meta = _team_live_metadata(conn, home_canon, fx["season"])
        a_meta = _team_live_metadata(conn, away_canon, fx["season"])
        h_venue = team_venue(home_canon)
        stadium_fa = h_venue.get("stadium_fa") or (h_meta.get("venue_en") if h_meta else None) or None
        # سرمربی فقط از دادهٔ زندهٔ API (team_metadata) می‌آید — هرگز نام ثابت/قدیمی هاردکد نمایش داده نمی‌شود
        if h_meta and h_meta.get("coach_en"):
            home.sub = translate_coach_fa(h_meta["coach_en"])
        if a_meta and a_meta.get("coach_en"):
            away.sub = translate_coach_fa(a_meta["coach_en"])
        desc_tag = _creative_match_descriptor(fx["home_team"], fx["away_team"], home, away, post_match=post_match)
        round_label = f"هفته {fx_matchday} • {desc_tag}" if fx_matchday else desc_tag

        facts = MatchFacts(
            fixture_id=fixture_id,
            competition={"name": fx["competition"], "season": fx["season"]},
            kickoff_utc=kickoff_dt,
            source=SourceInfo(
                provider=fx["provider"],
                collected_at=fx["collected_at"],
                payload_hash=fx["raw_payload_hash"],
            ),
            home=home,
            away=away,
            result=result,
            data_quality=DataQuality(missing_fields=missing),
            market_odds=market_odds,
            matchday=fx_matchday,
            round=round_label,
            stadium=stadium_fa,
            broadcast=_fixture_broadcast(conn, fixture_id) or "پخش آنلاین",
        )
        facts.triggers = evaluate_triggers(facts)
        return json.loads(facts.model_dump_json())


def data_freshness() -> dict:
    """تازگی داده — برای پایش cron: آخرین بازی ثبت‌شده چند روز پیش بوده؟"""
    with db() as conn:
        row = conn.execute(
            """
            SELECT MAX(kickoff_utc) AS last_match, COUNT(*) AS total_finished
            FROM fixtures WHERE status = 'finished'
            """
        ).fetchone()
        total_stats = conn.execute("SELECT COUNT(*) AS c FROM fixture_statistics").fetchone()["c"]
        total_xg = conn.execute(
            "SELECT COUNT(*) AS c FROM fixture_statistics WHERE metric = 'expected_goals'"
        ).fetchone()["c"]
    last = row["last_match"] or "-"
    return {
        "last_finished_match": last,
        "total_finished": row["total_finished"],
        "total_stat_rows": total_stats,
        "total_xg_rows": total_xg,
    }


def _fixture_broadcast(conn: sqlite3.Connection, fixture_id: str) -> str | None:
    try:
        row = conn.execute(
            "SELECT channel_label FROM fixture_broadcasts WHERE fixture_id = ?",
            (fixture_id,),
        ).fetchone()
        return row["channel_label"] if row and row["channel_label"] else None
    except sqlite3.OperationalError:
        return None


def sync_irib_broadcasts(
    programs: list[Any],
    fixtures: list[dict[str, Any]],
    *,
    tehran_date: str,
) -> dict[str, int]:
    """تطبیق جدول پخش شبکه سه و ورزش با بازی‌های امروز و ذخیره در fixture_broadcasts."""
    from src.xgpedia.providers.irib_conductor import match_fixture_broadcast

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    matched = 0
    with db() as conn:
        for fx in fixtures:
            prog = match_fixture_broadcast(
                programs,
                fx["home_en"],
                fx["away_en"],
                home_fa=fx.get("home_fa") or "",
                away_fa=fx.get("away_fa") or "",
                kickoff_tehran=fx.get("kickoff_tehran") or "",
            )
            if prog is None:
                continue
            conn.execute(
                """
                INSERT INTO fixture_broadcasts
                  (fixture_id, channel_label, program_title, broadcast_time, tehran_date, collected_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(fixture_id) DO UPDATE SET
                  channel_label=excluded.channel_label,
                  program_title=excluded.program_title,
                  broadcast_time=excluded.broadcast_time,
                  tehran_date=excluded.tehran_date,
                  collected_at=excluded.collected_at
                """,
                (fx["fixture_id"], prog.channel_label, prog.title, prog.start_time, tehran_date, now),
            )
            matched += 1
    return {"matched": matched, "programs_checked": len(programs)}

def _team_live_metadata(conn: sqlite3.Connection, team: str, season: str) -> dict[str, str | None] | None:
    """خواندن سرمربی و ورزشگاه تیم با اولویت سرمربی زندهٔ ویکی‌پدیا و ادغام ورزشگاه از football-data.org."""
    try:
        rows = conn.execute(
            """
            SELECT venue_en, coach_en, provider FROM team_metadata
            WHERE team = ? AND season = ?
            ORDER BY CASE provider WHEN 'wikipedia-live' THEN 1 ELSE 2 END, collected_at DESC
            """,
            (team, season),
        ).fetchall()
        if not rows:
            rows = conn.execute(
                """
                SELECT venue_en, coach_en, provider FROM team_metadata
                WHERE team = ?
                ORDER BY CASE provider WHEN 'wikipedia-live' THEN 1 ELSE 2 END, collected_at DESC
                """,
                (team,),
            ).fetchall()
        if not rows:
            return None
        venue_en = next((r["venue_en"] for r in rows if r["venue_en"]), None)
        coach_en = next((r["coach_en"] for r in rows if r["coach_en"]), None)
        return {"venue_en": venue_en, "coach_en": coach_en}
    except sqlite3.OperationalError:
        return None


def sync_team_metadata(raw: RawResponse, season_start: int = CURRENT_SEASON_START) -> dict[str, int]:
    """ذخیرهٔ زندهٔ سرمربی و ورزشگاه تیم‌های فصل از پاسخ /v4/competitions/PL/teams."""
    season_label = f"{season_start}-{str(season_start + 1)[-2:]}"
    teams = raw.payload.get("teams") or []
    saved = 0
    with db() as conn:
        for t in teams:
            raw_name = t.get("name") or t.get("shortName")
            if not raw_name:
                continue
            canon = canonical_team_name(raw_name, t.get("id"))
            venue_en = (t.get("venue") or "").strip() or None
            coach_obj = t.get("coach") or {}
            coach_en = (coach_obj.get("name") or "").strip() or None
            if not venue_en and not coach_en:
                continue
            conn.execute(
                """
                INSERT INTO team_metadata (team, season, venue_en, coach_en, provider, collected_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(team, season, provider) DO UPDATE SET
                  venue_en=COALESCE(excluded.venue_en, team_metadata.venue_en),
                  coach_en=COALESCE(excluded.coach_en, team_metadata.coach_en),
                  collected_at=excluded.collected_at
                """,
                (canon, season_label, venue_en, coach_en, raw.provider, raw.collected_at),
            )
            saved += 1
    return {"teams_saved": saved, "total_in_payload": len(teams)}

def sync_fdo_scorers(raw: RawResponse, season_start: int = CURRENT_SEASON_START) -> dict[str, int]:
    """ذخیرهٔ مهرهٔ کلیدی (برترین گلزن/پاسور) هر تیم از /v4/competitions/PL/scorers."""
    season_label = f"{season_start}-{str(season_start + 1)[-2:]}"
    scorers = raw.payload.get("scorers") or []
    best_by_team: dict[str, dict[str, str]] = {}
    for item in scorers:
        team_obj = item.get("team") or {}
        t_raw = team_obj.get("name") or team_obj.get("shortName")
        if not t_raw:
            continue
        t_canon = canonical_team_name(t_raw, team_obj.get("id"))
        if t_canon in best_by_team:
            continue
        player = item.get("player") or {}
        pname = str(player.get("name") or "").strip()
        if not pname:
            continue
        goals = item.get("goals") or 0
        assists = item.get("assists")
        played = item.get("playedMatches")
        s1 = f"{goals} گل"
        s2 = f"{assists} پاس گل" if assists is not None else (f"{played} بازی" if played else "گلزن برتر")
        best_by_team[t_canon] = {
            "name": pname,
            "pos": "مهاجم / گلزن",
            "s1": s1,
            "s2": s2,
        }
    with db() as conn:
        for team, kp in best_by_team.items():
            conn.execute(
                """
                INSERT INTO team_enrichments (team, season, key_player_json, provider, collected_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(team, season, provider) DO UPDATE SET
                  key_player_json=excluded.key_player_json,
                  collected_at=excluded.collected_at
                """,
                (team, season_label, json.dumps(kp, ensure_ascii=False), raw.provider, raw.collected_at),
            )
    return {"key_players": len(best_by_team)}


def sync_espn_enrichments(data: dict[str, Any], season_start: int = CURRENT_SEASON_START) -> dict[str, int]:
    """ذخیرهٔ ضرایب زنده (+EV)، مهرهٔ کلیدی (keyduel) و موج ۱۵ دقیقه‌ای (wave) از ESPN رایگان."""
    season_label = f"{season_start}-{str(season_start + 1)[-2:]}"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    odds_saved = 0
    if data.get("odds_rows"):
        odds_saved = sync_upcoming_odds(data["odds_rows"], provider="espn-public")["odds_saved"]

    kp_map = data.get("key_players") or {}
    wave_map = data.get("wave_map") or {}
    all_teams = set(kp_map) | set(wave_map)
    with db() as conn:
        for team in all_teams:
            kp_json = json.dumps(kp_map[team], ensure_ascii=False) if team in kp_map else None
            wave_json = json.dumps(wave_map[team]) if team in wave_map else None
            conn.execute(
                """
                INSERT INTO team_enrichments (team, season, key_player_json, wave_json, provider, collected_at)
                VALUES (?, ?, ?, ?, 'espn-public', ?)
                ON CONFLICT(team, season, provider) DO UPDATE SET
                  key_player_json=COALESCE(excluded.key_player_json, team_enrichments.key_player_json),
                  wave_json=COALESCE(excluded.wave_json, team_enrichments.wave_json),
                  collected_at=excluded.collected_at
                """,
                (team, season_label, kp_json, wave_json, now),
            )
    return {"odds_saved": odds_saved, "key_players": len(kp_map), "waves": len(wave_map)}

def sync_fpl_key_players(kp_map: dict[str, dict[str, str]], season_start: int = CURRENT_SEASON_START) -> dict[str, int]:
    """ذخیرهٔ مهرهٔ کلیدی رسمی FPL (Opta xG+xA) برای همهٔ ۲۰ تیم لیگ برتر."""
    season = season_label(season_start)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with db() as conn:
        for team, kp in (kp_map or {}).items():
            conn.execute(
                """
                INSERT INTO team_enrichments (team, season, key_player_json, provider, collected_at)
                VALUES (?, ?, ?, 'fpl-official', ?)
                ON CONFLICT(team, season, provider) DO UPDATE SET
                  key_player_json=excluded.key_player_json,
                  collected_at=excluded.collected_at
                """,
                (team, season, json.dumps(kp, ensure_ascii=False), now),
            )
    return {"key_players": len(kp_map or {})}


def sync_csv_waves(wave_map: dict[str, list[float]], season_start: int = CURRENT_SEASON_START) -> dict[str, int]:
    """ذخیرهٔ موج زمانی ۱۵ دقیقه‌ای محاسبه‌شده از تفکیک واقعی نیمه اول/دوم E0.csv."""
    season = season_label(season_start)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with db() as conn:
        for team, wv in (wave_map or {}).items():
            if not (isinstance(wv, list) and len(wv) == 6):
                continue
            conn.execute(
                """
                INSERT INTO team_enrichments (team, season, wave_json, provider, collected_at)
                VALUES (?, ?, ?, 'football-data-co-uk', ?)
                ON CONFLICT(team, season, provider) DO UPDATE SET
                  wave_json=excluded.wave_json,
                  collected_at=excluded.collected_at
                """,
                (team, season, json.dumps(wv), now),
            )
    return {"waves": len(wave_map or {})}


def sync_live_coaches_for_teams(
    teams: list[str], *, season_start: int = CURRENT_SEASON_START, timeout: float = 8.0
) -> dict[str, int]:
    """به‌روزرسانی زندهٔ سرمربی تیم‌ها از ویکی‌پدیای انگلیسی+فارسی برای پوشش تغییرات لحظه‌ای (اخراج/استخدام)."""
    from src.xgpedia.db import init_db
    from src.xgpedia.providers.live_intel_free import fetch_live_coach_wikipedia

    init_db()
    season_label = f"{season_start}-{str(season_start + 1)[-2:]}"
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    updated = 0
    seen: set[str] = set()
    with db() as conn:
        for raw_t in teams:
            canon = canonical_team_name(raw_t)
            if not canon or canon in seen:
                continue
            seen.add(canon)
            coach_en, coach_fa = fetch_live_coach_wikipedia(canon)
            best_coach = coach_fa or coach_en
            if not best_coach:
                continue
            conn.execute(
                """
                INSERT INTO team_metadata (team, season, venue_en, coach_en, provider, collected_at)
                VALUES (?, ?, NULL, ?, 'wikipedia-live', ?)
                ON CONFLICT(team, season, provider) DO UPDATE SET
                  coach_en=excluded.coach_en,
                  collected_at=excluded.collected_at
                """,
                (canon, season_label, best_coach, now_iso),
            )
            updated += 1
    return {"coaches_updated": updated}


def ensure_live_coaches_fresh(
    teams: list[str],
    *,
    season_start: int = CURRENT_SEASON_START,
    max_age_hours: float = 4.0,
    timeout: float = 6.0,
) -> dict[str, Any]:
    """تضمین به‌روز بودن سرمربی زنده (`wikipedia-live`) برای تیم‌های یک مسابقه پیش از ساخت کارت و کپشن.

    اگر برای تیمی رکورد `wikipedia-live` وجود نداشته باشد یا قدیمی‌تر از `max_age_hours` باشد،
    همان‌لحظه زنده از ویکی‌پدیا/ویکی‌دیتا به‌روزرسانی می‌شود.
    خروجی: `{"coaches_updated": int, "coaches_fa": {canon_team: coach_fa}}`
    """
    from src.xgpedia.db import init_db

    init_db()
    s_label = f"{season_start}-{str(season_start + 1)[-2:]}"
    now = datetime.now(timezone.utc)
    stale_teams: list[str] = []
    coaches_fa: dict[str, str] = {}
    seen: set[str] = set()

    with db() as conn:
        for raw_t in teams:
            canon = canonical_team_name(raw_t)
            if not canon or canon in seen:
                continue
            seen.add(canon)
            row = conn.execute(
                """
                SELECT coach_en, collected_at FROM team_metadata
                WHERE team = ? AND season = ? AND provider = 'wikipedia-live'
                LIMIT 1
                """,
                (canon, s_label),
            ).fetchone()
            is_fresh = False
            if row and row["coach_en"] and row["collected_at"]:
                try:
                    dt = datetime.fromisoformat(str(row["collected_at"]).replace("Z", "+00:00"))
                    if (now - dt).total_seconds() <= max_age_hours * 3600.0:
                        is_fresh = True
                        fa_name = translate_coach_fa(row["coach_en"])
                        if fa_name:
                            coaches_fa[canon] = fa_name
                except Exception:
                    is_fresh = False
            if not is_fresh:
                stale_teams.append(canon)

    updated = 0
    if stale_teams:
        res = sync_live_coaches_for_teams(stale_teams, season_start=season_start, timeout=timeout)
        updated = res.get("coaches_updated", 0)
        with db() as conn:
            for canon in stale_teams:
                row = conn.execute(
                    """
                    SELECT coach_en FROM team_metadata
                    WHERE team = ? AND season = ? AND provider = 'wikipedia-live'
                    LIMIT 1
                    """,
                    (canon, s_label),
                ).fetchone()
                if row and row["coach_en"]:
                    fa_name = translate_coach_fa(row["coach_en"])
                    if fa_name:
                        coaches_fa[canon] = fa_name

    return {"coaches_updated": updated, "coaches_fa": coaches_fa}
