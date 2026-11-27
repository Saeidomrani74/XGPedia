"""ماژول غنی‌سازی، پخش زنده، سرمربیان و جزئیات پس‌ازبازی (استخراج‌شده از sync.py در v0.73.0).

تمام توابع همچنان از طریق `src.xgpedia.sync` نیز re-export می‌شوند تا سازگاری ۱۰۰٪ حفظ شود.
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

if TYPE_CHECKING:
    from src.xgpedia.normalization.models import TeamSide
    from src.xgpedia.providers.base import RawResponse


def _sync_db():
    """فراخوانی db() از طریق ماژول sync تا monkeypatch تست‌ها روی sync.db کاملاً حفظ شود."""
    import src.xgpedia.sync as _sync_mod

    return _sync_mod.db()


def _fdo_competition_name(comp_code: str) -> str:
    import src.xgpedia.sync as _sync_mod
    return _sync_mod._fdo_competition_name(comp_code)


def sync_upcoming_odds(*args, **kwargs):
    import src.xgpedia.sync as _sync_mod
    return _sync_mod.sync_upcoming_odds(*args, **kwargs)


def season_label(start_year: int) -> str:
    return f"{start_year}-{str(start_year + 1)[2:]}"


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
    with _sync_db() as conn:
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
    with _sync_db() as conn:
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
    with _sync_db() as conn:
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
    with _sync_db() as conn:
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
    upcoming_saved = 0
    up_rows = data.get("upcoming_fixtures") or []
    if up_rows:
        with _sync_db() as conn:
            for m in up_rows:
                h_c = canonical_team_name(m.get("home_team") or "")
                a_c = canonical_team_name(m.get("away_team") or "")
                ko = str(m.get("kickoff_utc") or "")
                eid = str(m.get("event_id") or "")
                comp_name = str(m.get("competition") or "Premier League")
                if not (h_c and a_c and ko and eid):
                    continue
                ko_day = ko[:10]
                dup = conn.execute(
                    """
                    SELECT fixture_id FROM fixtures
                    WHERE home_team = ? AND away_team = ?
                      AND substr(kickoff_utc, 1, 10) >= date(?, '-1 day')
                      AND substr(kickoff_utc, 1, 10) <= date(?, '+1 day')
                    LIMIT 1
                    """,
                    (h_c, a_c, ko_day, ko_day),
                ).fetchone()
                if dup:
                    continue
                fid = f"espn:{eid}"
                conn.execute(
                    """
                    INSERT INTO fixtures
                      (fixture_id, provider, competition, season, kickoff_utc, home_team, away_team,
                       status, raw_payload_hash, collected_at)
                    VALUES (?, 'espn-public', ?, ?, ?, ?, ?, 'scheduled', NULL, ?)
                    ON CONFLICT(fixture_id) DO UPDATE SET
                      competition=excluded.competition,
                      kickoff_utc=excluded.kickoff_utc,
                      collected_at=excluded.collected_at
                    """,
                    (fid, comp_name, season_label, ko, h_c, a_c, now),
                )
                upcoming_saved += 1
    return {
        "odds_saved": odds_saved,
        "key_players": len(kp_map),
        "waves": len(wave_map),
        "upcoming_saved": upcoming_saved,
    }


def sync_fpl_key_players(kp_map: dict[str, dict[str, str]], season_start: int = CURRENT_SEASON_START) -> dict[str, int]:
    """ذخیرهٔ مهرهٔ کلیدی رسمی FPL (Opta xG+xA) برای همهٔ ۲۰ تیم لیگ برتر."""
    season = season_label(season_start)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _sync_db() as conn:
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
    with _sync_db() as conn:
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
    with _sync_db() as conn:
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

    with _sync_db() as conn:
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
        with _sync_db() as conn:
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


def sync_finished_matches_from_fdo(raw: RawResponse, season_start: int = CURRENT_SEASON_START, *, competition: str | None = None) -> dict[str, int]:
    """ذخیرهٔ بازی‌های پایان‌یافتهٔ ۲۴-۴۸ ساعت اخیر از football-data.org (وضعیت FINISHED + نتیجهٔ نهایی)."""
    matches = (raw.payload or {}).get("matches") or []
    s_label = f"{season_start}-{str(season_start + 1)[-2:]}"
    saved = 0
    with _sync_db() as conn:
        for m in matches:
            if str(m.get("status") or "").upper() != "FINISHED":
                continue
            mid = m.get("id")
            h_obj = m.get("homeTeam") or {}
            a_obj = m.get("awayTeam") or {}
            h_raw = h_obj.get("name") or h_obj.get("shortName")
            a_raw = a_obj.get("name") or a_obj.get("shortName")
            if not (mid and h_raw and a_raw):
                continue
            h_canon = canonical_team_name(h_raw, h_obj.get("id"))
            a_canon = canonical_team_name(a_raw, a_obj.get("id"))
            try:
                from src.xgpedia.providers.dynamic_crests import register_team_logo
                if h_obj.get("crest"):
                    register_team_logo(h_canon, str(h_obj["crest"]))
                if a_obj.get("crest"):
                    register_team_logo(a_canon, str(a_obj["crest"]))
            except Exception:
                pass
            ft = (m.get("score") or {}).get("fullTime") or {}
            hg, ag = ft.get("home"), ft.get("away")
            if hg is None or ag is None:
                continue
            fid = f"fdo:{mid}"
            ko = str(m.get("utcDate") or "")
            md = m.get("matchday")
            conn.execute(
                """
                INSERT INTO fixtures
                  (fixture_id, provider, competition, season, kickoff_utc, home_team, away_team,
                   status, matchday, raw_payload_hash, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'finished', ?, ?, ?)
                ON CONFLICT(fixture_id) DO UPDATE SET
                  competition=excluded.competition,
                  status='finished',
                  matchday=COALESCE(excluded.matchday, fixtures.matchday),
                  collected_at=excluded.collected_at
                """,
                (fid, raw.provider, _fdo_competition_name(raw.payload, competition), s_label, ko, h_canon, a_canon, md, raw.payload_hash, raw.collected_at),
            )
            for tm_g, g_val in ((h_canon, hg), (a_canon, ag)):
                conn.execute(
                    """
                    INSERT INTO fixture_statistics
                      (fixture_id, team, metric, value, n, provider, collected_at)
                    VALUES (?, ?, 'goals', ?, NULL, ?, ?)
                    ON CONFLICT(fixture_id, team, metric, provider) DO UPDATE SET
                      value=excluded.value,
                      collected_at=excluded.collected_at
                    """,
                    (fid, tm_g, float(g_val), raw.provider, raw.collected_at),
                )
            saved += 1
    return {"finished_saved": saved}


def sync_espn_finished_matches(
    matches: list[dict[str, Any]], *, season_start: int = CURRENT_SEASON_START
) -> dict[str, int]:
    """ذخیرهٔ بازی‌های پایان‌یافتهٔ ۲۴ ساعت اخیر از ESPN + آمار واقعی مسابقه + جزئیات پس‌ازبازی (گلزنان/مومنتوم/دروازه‌بان)."""
    from src.xgpedia.db import init_db

    init_db()
    s_label = f"{season_start}-{str(season_start + 1)[-2:]}"
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    saved = 0
    stats_rows = 0

    with _sync_db() as conn:
        for m in matches or []:
            h_canon = canonical_team_name(m["home_team"])
            a_canon = canonical_team_name(m["away_team"])
            ko = str(m.get("kickoff_utc") or "")
            ko_day = ko[:10]
            hg = int(m["home_goals"])
            ag = int(m["away_goals"])

            # اگر همین بازی قبلاً از football-data.org در fixtures ثبت شده (حتی با اختلاف نام مثل Atlético/Atletico یا Viking/Viking FK)، روی همان fixture_id ادغام می‌کنیم
            existing = None
            if ko_day:
                existing = conn.execute(
                    """
                    SELECT fixture_id FROM fixtures
                    WHERE home_team = ? AND away_team = ?
                      AND substr(kickoff_utc, 1, 10) >= date(?, '-1 day')
                      AND substr(kickoff_utc, 1, 10) <= date(?, '+1 day')
                    ORDER BY CASE provider WHEN 'football-data-org' THEN 1 ELSE 2 END
                    LIMIT 1
                    """,
                    (h_canon, a_canon, ko_day, ko_day),
                ).fetchone()
                if not existing:
                    from src.xgpedia.providers.xg_engine import _teams_match
                    cands = conn.execute(
                        """
                        SELECT fixture_id, home_team, away_team FROM fixtures
                        WHERE substr(kickoff_utc, 1, 10) >= date(?, '-1 day')
                          AND substr(kickoff_utc, 1, 10) <= date(?, '+1 day')
                        ORDER BY CASE provider WHEN 'football-data-org' THEN 1 ELSE 2 END
                        """,
                        (ko_day, ko_day),
                    ).fetchall()
                    for c_row in cands:
                        if _teams_match(h_canon, c_row["home_team"]) and _teams_match(a_canon, c_row["away_team"]):
                            existing = c_row
                            # برای آمارهای fixture_statistics از نام دقیق ثبت‌شده در fixtures استفاده می‌کنیم
                            h_canon = c_row["home_team"]
                            a_canon = c_row["away_team"]
                            break

            if existing:
                fid = existing["fixture_id"]
                conn.execute(
                    "UPDATE fixtures SET status='finished', collected_at=? WHERE fixture_id=?",
                    (now_iso, fid),
                )
            else:
                fid = f"espn:{m.get('event_id') or f'{ko_day}:{h_canon}:{a_canon}'}"
                comp_name = str(m.get("competition") or "Premier League")
                conn.execute(
                    """
                    INSERT INTO fixtures
                      (fixture_id, provider, competition, season, kickoff_utc, home_team, away_team,
                       status, raw_payload_hash, collected_at)
                    VALUES (?, 'espn-public', ?, ?, ?, ?, ?, 'finished', NULL, ?)
                    ON CONFLICT(fixture_id) DO UPDATE SET
                      competition=excluded.competition,
                      status='finished',
                      collected_at=excluded.collected_at
                    """,
                    (fid, comp_name, s_label, ko, h_canon, a_canon, now_iso),
                )

            # ذخیرهٔ آمار واقعی مسابقه در fixture_statistics
            for side_team, st_dict, g_val in (
                (h_canon, m.get("home_stats") or {}, hg),
                (a_canon, m.get("away_stats") or {}, ag),
            ):
                all_m = dict(st_dict)
                all_m["goals"] = float(g_val)
                # پاک‌سازی xG تقریبی قدیمی (قبل از v0.54.0) اگر ESPN خودش expectedGoals واقعی نداد
                if "expected_goals" not in all_m:
                    conn.execute(
                        "DELETE FROM fixture_statistics WHERE fixture_id=? AND team=? AND metric='expected_goals' AND provider='espn-public'",
                        (fid, side_team),
                    )
                for metric, val in all_m.items():
                    if val is None or metric == "saves":
                        continue
                    conn.execute(
                        """
                        INSERT INTO fixture_statistics
                          (fixture_id, team, metric, value, n, provider, collected_at)
                        VALUES (?, ?, ?, ?, NULL, 'espn-public', ?)
                        ON CONFLICT(fixture_id, team, metric, provider) DO UPDATE SET
                          value=excluded.value,
                          collected_at=excluded.collected_at
                        """,
                        (fid, side_team, metric, float(val), now_iso),
                    )
                    stats_rows += 1

            # ادغام امن جزئیات ESPN با حفظ داده‌های غنی‌شدهٔ قبلی (FotMob/SofaScore ShotMap, TopRated, MOTM)
            existing_pm = conn.execute(
                "SELECT details_json FROM fixture_post_match WHERE fixture_id = ?", (fid,)
            ).fetchone()
            merged_det: dict[str, Any] = {}
            if existing_pm and existing_pm["details_json"]:
                try:
                    loaded_pm = json.loads(existing_pm["details_json"])
                    if isinstance(loaded_pm, dict):
                        merged_det.update(loaded_pm)
                except Exception:
                    pass
            for k_d, v_d in (m.get("details") or {}).items():
                if v_d is not None and v_d != "" and (k_d not in merged_det or not merged_det[k_d]):
                    merged_det[k_d] = v_d
            merged_det["synced_at_utc"] = now_iso
            conn.execute(
                """
                INSERT INTO fixture_post_match (fixture_id, details_json, provider, collected_at)
                VALUES (?, ?, 'espn-public', ?)
                ON CONFLICT(fixture_id) DO UPDATE SET
                  details_json=excluded.details_json,
                  collected_at=excluded.collected_at
                """,
                (fid, json.dumps(merged_det, ensure_ascii=False), now_iso),
            )
            saved += 1

    return {"finished_saved": saved, "stats_rows": stats_rows}


def merge_post_match_details(
    fixture_id: str,
    patch: dict[str, Any],
    *,
    provider: str,
    extra_stats: dict[str, dict[str, float]] | None = None,
) -> bool:
    """ادغام امن جزئیات تکمیلی پس‌ازبازی (Understat شوت/xG، FPL امتیاز/MOTM/GK) بدون پاک‌کردن داده‌های ESPN."""
    from src.xgpedia.db import init_db

    init_db()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _sync_db() as conn:
        row = conn.execute(
            "SELECT details_json FROM fixture_post_match WHERE fixture_id = ?",
            (fixture_id,),
        ).fetchone()
        existing: dict[str, Any] = {}
        if row and row["details_json"]:
            try:
                loaded = json.loads(row["details_json"])
                if isinstance(loaded, dict):
                    existing = loaded
            except Exception:
                existing = {}
        changed = False
        for k, v in (patch or {}).items():
            if v is not None and v != "" and v != []:
                existing[k] = v
                changed = True
        if changed:
            conn.execute(
                """
                INSERT INTO fixture_post_match (fixture_id, details_json, provider, collected_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(fixture_id) DO UPDATE SET
                  details_json=excluded.details_json,
                  collected_at=excluded.collected_at
                """,
                (fixture_id, json.dumps(existing, ensure_ascii=False), provider, now_iso),
            )
        for team_canon, metrics in (extra_stats or {}).items():
            for met, val in (metrics or {}).items():
                if val is None:
                    continue
                conn.execute(
                    """
                    INSERT INTO fixture_statistics
                      (fixture_id, team, metric, value, n, provider, collected_at)
                    VALUES (?, ?, ?, ?, 1, ?, ?)
                    ON CONFLICT(fixture_id, team, metric, provider) DO UPDATE SET
                      value=excluded.value,
                      collected_at=excluded.collected_at
                    """,
                    (fixture_id, canonical_team_name(team_canon), met, float(val), provider, now_iso),
                )
                changed = True
    return changed
