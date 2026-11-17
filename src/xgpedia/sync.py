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
from datetime import datetime, timezone

from src.xgpedia.config import (
    CURRENT_SEASON_START,
    PRIMARY_FIXTURES_PROVIDER,
    PRIMARY_STATS_PROVIDER,
    team_name_fa,
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
            home = m["homeTeam"]["name"]
            away = m["awayTeam"]["name"]
            kickoff = m["utcDate"]  # ISO-8601 UTC
            existed = conn.execute(
                "SELECT 1 FROM fixtures WHERE fixture_id = ?", (fid,)
            ).fetchone()
            conn.execute(
                """
                INSERT INTO fixtures (fixture_id, provider, competition, season, kickoff_utc,
                                      home_team, away_team, status, raw_payload_hash, collected_at)
                VALUES (?, ?, 'Premier League', ?, ?, ?, ?, 'scheduled', ?, ?)
                ON CONFLICT(fixture_id) DO UPDATE SET
                  kickoff_utc=excluded.kickoff_utc, status='scheduled',
                  raw_payload_hash=excluded.raw_payload_hash, collected_at=excluded.collected_at
                """,
                (fid, PRIMARY_FIXTURES_PROVIDER, season, kickoff, home, away,
                 raw.payload_hash, now),
            )
            if not existed:
                inserted += 1
    return {"upcoming_new": inserted, "total_in_payload": len(raw.payload.get("matches", []))}


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


def _team_xg_series(conn: sqlite3.Connection, team: str, before_date: str, limit: int = 10) -> list[float] | None:
    """xG بازی‌به‌بازی تیم، قدیمی‌ترین → جدیدترین — دادهٔ ماژول «روند ۱۰ بازی اخیر»."""
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


def build_match_facts(fixture_id: str) -> dict:
    """ساخت «JSON واقعیت‌ها» برای یک بازی — تنها ورودی مجاز LLM و رندرر.

    خروجی dict مطابق schema MatchFacts (models.py)؛ آمادهٔ json.dumps با ensure_ascii=False.
    """
    from src.xgpedia.analytics.metrics import evaluate_triggers
    from src.xgpedia.normalization.models import (
        DataQuality,
        Last5,
        MatchFacts,
        RecentForm,
        SourceInfo,
        StatValue,
        TeamSide,
    )

    with db() as conn:
        fx = conn.execute("SELECT * FROM fixtures WHERE fixture_id = ?", (fixture_id,)).fetchone()
        if fx is None:
            raise KeyError(f"fixture {fixture_id} not found in DB - run sync-results first")

        kickoff = fx["kickoff_utc"]
        if kickoff.endswith("Z"):
            kickoff_dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
        else:
            kickoff_dt = datetime.fromisoformat(kickoff)

        def side(team: str) -> TeamSide:
            l5 = last5_from_db(conn, team, kickoff[:10])
            xg = _team_xg_avg(conn, team, kickoff[:10])
            corners = _team_corners_avg(conn, team, kickoff[:10])
            xga = _team_xga_avg(conn, team, kickoff[:10])
            sot = _team_sot_avg(conn, team, kickoff[:10])
            series = _team_xg_series(conn, team, kickoff[:10])
            form_seq = _team_form_sequence(conn, team, kickoff[:10])
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
            )

        home = side(fx["home_team"])
        away = side(fx["away_team"])

        missing = []
        if home.xg_for_avg is None:
            missing.append("home.xg_for_avg")
        if away.xg_for_avg is None:
            missing.append("away.xg_for_avg")
        if home.last5 is None or home.last5.n < 5:
            missing.append("home.last5")
        if away.last5 is None or away.last5.n < 5:
            missing.append("away.last5")

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
            data_quality=DataQuality(missing_fields=missing),
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
