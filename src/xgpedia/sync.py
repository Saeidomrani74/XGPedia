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

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
    from src.xgpedia.normalization.models import TeamSide
    from src.xgpedia.providers.base import RawResponse


def season_label(start_year: int) -> str:
    """برچسب فصل به سبک سند: ۲۰۲۶ (سال شروع) → «2026-27»."""
    return f"{start_year}-{str(start_year + 1)[2:]}"


def fixture_id_for_csv(row_date: str, home: str, away: str) -> str:
    """شناسهٔ پایدار مسابقهٔ CSV — از تاریخ و دو تیم؛ بدون وابستگی به provider ID."""
    return f"fdcouk:{row_date}:{home}:{away}"


# ─── ۱) sync-results: CSV → DB ───

def sync_csv_results(rows, payload_hash: str, season_start: int = CURRENT_SEASON_START, *, competition: str = "Premier League") -> dict:
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
                VALUES (?, ?, ?, ?, ?, ?, ?, 'finished', ?, ?)
                ON CONFLICT(fixture_id) DO UPDATE SET
                  competition=excluded.competition,
                  status='finished', raw_payload_hash=excluded.raw_payload_hash,
                  collected_at=excluded.collected_at
                """,
                (fid, PRIMARY_STATS_PROVIDER, competition, season, r.date_utc, r.home_team, r.away_team,
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

def _fdo_competition_name(payload: dict[str, Any], fallback: str | None = None) -> str:
    from src.xgpedia.core.leagues import canonical_competition_name, league_by_code

    comp_obj = (payload or {}).get("competition") or {}
    if isinstance(comp_obj, dict):
        spec = league_by_code(comp_obj.get("code"))
        if spec:
            return spec.name_en
        if comp_obj.get("name"):
            return canonical_competition_name(comp_obj.get("name"))
    return canonical_competition_name(fallback, default="Premier League")


def sync_upcoming_fixtures(raw, season_start: int = CURRENT_SEASON_START, *, competition: str | None = None) -> dict:
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
                VALUES (?, ?, ?, ?, ?, ?, ?, 'scheduled', ?, ?, ?)
                ON CONFLICT(fixture_id) DO UPDATE SET
                  competition=excluded.competition,
                  home_team=excluded.home_team, away_team=excluded.away_team,
                  kickoff_utc=excluded.kickoff_utc, status='scheduled',
                  matchday=COALESCE(excluded.matchday, fixtures.matchday),
                  raw_payload_hash=excluded.raw_payload_hash, collected_at=excluded.collected_at
                """,
                (fid, PRIMARY_FIXTURES_PROVIDER, _fdo_competition_name(raw.payload, competition), season, kickoff, home, away,
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

_FALLBACK_GOAL_PROVIDERS = ("espn-public", "football-data-org", "fotmob", "sofascore")
_FALLBACK_REAL_XG_PROVIDERS = ("fotmob", "sofascore", "understat", "api-football")


def _query_team_goal_rows(conn: sqlite3.Connection, team: str, before_date: str, limit: int = 5) -> list:
    """خواندن نتایج واقعی اخیر یک تیم؛ اولویت با CSV اصلی و در نبود آن، ESPN/FDO/FotMob/SofaScore (بدون داده جعلی)."""
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
    if rows:
        return rows
    ph = ",".join("?" for _ in _FALLBACK_GOAL_PROVIDERS)
    raw = conn.execute(
        f"""
        SELECT kickoff_utc, home_team, away_team,
               MAX(CASE WHEN team=home_team THEN value END) AS hg,
               MAX(CASE WHEN team=away_team THEN value END) AS ag
        FROM fixtures f
        JOIN fixture_statistics s
          ON s.fixture_id = f.fixture_id AND s.metric = 'goals' AND s.provider IN ({ph})
        WHERE f.status = 'finished' AND f.kickoff_utc < ?
          AND (f.home_team = ? OR f.away_team = ?)
        GROUP BY substr(f.kickoff_utc, 1, 10), f.home_team, f.away_team
        ORDER BY f.kickoff_utc DESC
        LIMIT ?
        """,
        (*_FALLBACK_GOAL_PROVIDERS, before_date, team, team, limit),
    ).fetchall()
    return raw


def last5_from_db(conn: sqlite3.Connection, team: str, before_date: str) -> dict | None:
    """۵ بازی اخیر تیم قبل از تاریخ داده‌شده — برای فرم."""
    rows = _query_team_goal_rows(conn, team, before_date, limit=5)
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
        ph = ",".join("?" for _ in _FALLBACK_REAL_XG_PROVIDERS)
        rows = conn.execute(
            f"""
            SELECT s.value
            FROM fixture_statistics s
            JOIN fixtures f ON f.fixture_id = s.fixture_id
            WHERE s.metric = 'expected_goals' AND s.provider IN ({ph}) AND s.team = ?
              AND f.status = 'finished' AND f.kickoff_utc < ?
            GROUP BY substr(f.kickoff_utc, 1, 10), f.home_team, f.away_team
            ORDER BY f.kickoff_utc DESC
            LIMIT 10
            """,
            (*_FALLBACK_REAL_XG_PROVIDERS, team, before_date),
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
        ph = ",".join("?" for _ in _FALLBACK_GOAL_PROVIDERS)
        rows = conn.execute(
            f"""
            SELECT s.value
            FROM fixture_statistics s
            JOIN fixtures f ON f.fixture_id = s.fixture_id
            WHERE s.metric = 'corner_kicks' AND s.provider IN ({ph}) AND s.team = ?
              AND f.status = 'finished' AND f.kickoff_utc < ?
            GROUP BY substr(f.kickoff_utc, 1, 10), f.home_team, f.away_team
            ORDER BY f.kickoff_utc DESC
            LIMIT 10
            """,
            (*_FALLBACK_GOAL_PROVIDERS, team, before_date),
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
        ph = ",".join("?" for _ in _FALLBACK_REAL_XG_PROVIDERS)
        rows = conn.execute(
            f"""
            SELECT s.value
            FROM fixture_statistics s
            JOIN fixtures f ON f.fixture_id = s.fixture_id
            WHERE s.metric = 'expected_goals' AND s.provider IN ({ph})
              AND f.status = 'finished' AND f.kickoff_utc < ?
              AND s.team = CASE WHEN f.home_team = ? THEN f.away_team ELSE f.home_team END
              AND (f.home_team = ? OR f.away_team = ?)
            GROUP BY substr(f.kickoff_utc, 1, 10), f.home_team, f.away_team
            ORDER BY f.kickoff_utc DESC
            LIMIT 10
            """,
            (*_FALLBACK_REAL_XG_PROVIDERS, before_date, team, team, team),
        ).fetchall()
    if not rows:
        return None
    return {"n": len(rows), "avg": sum(r["value"] for r in rows) / len(rows)}


def _team_sot_avg(conn: sqlite3.Connection, team: str, before_date: str) -> dict | None:
    """میانگین شوت در چارچوب — CSV football-data.co.uk و در نبود آن، ESPN/FotMob/SofaScore."""
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
        ph = ",".join("?" for _ in _FALLBACK_GOAL_PROVIDERS)
        rows = conn.execute(
            f"""
            SELECT s.value
            FROM fixture_statistics s
            JOIN fixtures f ON f.fixture_id = s.fixture_id
            WHERE s.metric = 'shots_on_target' AND s.provider IN ({ph}) AND s.team = ?
              AND f.status = 'finished' AND f.kickoff_utc < ?
            GROUP BY substr(f.kickoff_utc, 1, 10), f.home_team, f.away_team
            ORDER BY f.kickoff_utc DESC
            LIMIT 10
            """,
            (*_FALLBACK_GOAL_PROVIDERS, team, before_date),
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
    rows = _query_team_goal_rows(conn, team, before_date, limit=limit)
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
    """آمار خودِ یک بازی برای یک تیم از همهٔ منابع معتبر با اولویت کیفیت و تطبیق هوشمند نام تیم."""
    from src.xgpedia.providers.xg_engine import _teams_match

    from src.xgpedia.core.source_chain import provider_priority_rank

    rows = conn.execute(
        """
        SELECT team, metric, value, provider, collected_at FROM fixture_statistics
        WHERE fixture_id = ? AND value IS NOT NULL
        ORDER BY collected_at DESC
        """,
        (fixture_id,),
    ).fetchall()
    rows = sorted(
        rows,
        key=lambda r: (provider_priority_rank(r["provider"], "match_xg_and_shotmap"), str(r["collected_at"] or "")),
        reverse=True,
    )
    t_canon = canonical_team_name(team)
    out: dict[str, float] = {}
    for r in rows:
        rt = str(r["team"] or "")
        if not (rt == team or rt == t_canon or canonical_team_name(rt) == t_canon or _teams_match(rt, t_canon)):
            continue
        if r["metric"] not in out:
            out[r["metric"]] = float(r["value"])
    return out


def _creative_match_descriptor(
    home_en: str,
    away_en: str,
    home: TeamSide,
    away: TeamSide,
    *,
    post_match: bool = False,
) -> str:
    """تولید صفت توصیفی جذاب، خلاقانه و متناسب با هویت و آمار واقعی هر بازی برای هدر کارت."""
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
    derby_lbl = next((lbl for teams_set, lbl in derbies if pair == teams_set), None)

    if post_match:
        hg = home.match_stats.goals.value if (home.match_stats and home.match_stats.goals and home.match_stats.goals.value is not None) else None
        ag = away.match_stats.goals.value if (away.match_stats and away.match_stats.goals and away.match_stats.goals.value is not None) else None
        hxg = home.match_stats.expected_goals.value if (home.match_stats and home.match_stats.expected_goals and home.match_stats.expected_goals.value is not None) else None
        axg = away.match_stats.expected_goals.value if (away.match_stats and away.match_stats.expected_goals and away.match_stats.expected_goals.value is not None) else None
        if hg is not None and ag is not None:
            hg_i, ag_i = int(round(hg)), int(round(ag))
            diff = abs(hg_i - ag_i)
            tot = hg_i + ag_i
            if derby_lbl:
                if diff >= 3:
                    return f"توفان در {derby_lbl}"
                if hg_i == ag_i:
                    return f"تساوی در {derby_lbl}"
                return f"برتری در {derby_lbl}"
            if diff >= 3:
                return "جشنواره گل و برد یک‌طرفه"
            if tot >= 5:
                return "نبرد پرگل و تماشایی"
            if hg_i == ag_i:
                return "شطرنج بدون گل" if tot == 0 else "تقسیم امتیاز در جدال پایاپای"
            if hxg is not None and axg is not None:
                if (hg_i > ag_i and hxg < axg - 0.35) or (ag_i > hg_i and axg < hxg - 0.35):
                    return "برد خلاف جریان امید گل"
                if diff >= 2 or abs(hxg - axg) >= 0.85:
                    return "برتری مقتدرانه در زمین و آمار"
            return "برد میلی‌متری در نبرد نزدیک"
        return f"گزارش {derby_lbl}" if derby_lbl else "گزارش آماری مسابقه"

    if derby_lbl:
        return derby_lbl

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
                    possession=sv("possession"),
                    big_chances=sv("big_chances"),
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
        out_dict = json.loads(facts.model_dump_json() if hasattr(facts, "model_dump_json") else facts.json())
        if post_match:
            try:
                pm_row = conn.execute(
                    "SELECT details_json FROM fixture_post_match WHERE fixture_id = ?",
                    (fixture_id,),
                ).fetchone()
                if pm_row and pm_row["details_json"]:
                    pm_det = json.loads(pm_row["details_json"])
                    if isinstance(pm_det, dict):
                        if pm_det.get("scorers_home"):
                            out_dict["home"]["scorersText"] = pm_det["scorers_home"]
                        if pm_det.get("scorers_away"):
                            out_dict["away"]["scorersText"] = pm_det["scorers_away"]
                        if pm_det.get("home_gk"):
                            out_dict["home"]["gk"] = pm_det["home_gk"]
                        if pm_det.get("away_gk"):
                            out_dict["away"]["gk"] = pm_det["away_gk"]
                        if pm_det.get("home_shots"):
                            out_dict["home"]["shotList"] = pm_det["home_shots"]
                        if pm_det.get("away_shots"):
                            out_dict["away"]["shotList"] = pm_det["away_shots"]
                        if pm_det.get("home_inside_box") is not None:
                            out_dict["home"]["insideBox"] = int(pm_det["home_inside_box"])
                        if pm_det.get("away_inside_box") is not None:
                            out_dict["away"]["insideBox"] = int(pm_det["away_inside_box"])
                        if pm_det.get("momentum"):
                            out_dict["momentum"] = pm_det["momentum"]
                        if pm_det.get("top_players"):
                            out_dict["topPlayers"] = pm_det["top_players"]
                        if pm_det.get("motm"):
                            out_dict["motm"] = pm_det["motm"]
            except Exception:
                pass
        return out_dict


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

# ─── Re-exports از sync_enrichments برای سازگاری ۱۰۰٪ با تمام callerها و تست‌ها ───
from src.xgpedia.sync_enrichments import (  # noqa: E402, F401
    _fixture_broadcast,
    _team_live_metadata,
    ensure_live_coaches_fresh,
    merge_post_match_details,
    sync_csv_waves,
    sync_espn_enrichments,
    sync_espn_finished_matches,
    sync_fdo_scorers,
    sync_finished_matches_from_fdo,
    sync_fpl_key_players,
    sync_irib_broadcasts,
    sync_live_coaches_for_teams,
    sync_team_metadata,
)
