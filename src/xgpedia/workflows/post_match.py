"""همگام‌سازی و غنی‌سازی بازی‌های پایان‌یافته برای کارت‌های پس‌ازبازی (استخراج‌شده از today_workflow.py)."""
from __future__ import annotations


import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.xgpedia.config import CURRENT_SEASON_START, ROOT, team_name_fa
from src.xgpedia.db import db, init_db
from src.xgpedia.publishers import telegram_publish as tp

TEHRAN_TZ = timezone(timedelta(hours=3, minutes=30))
FA_TO_EN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")



def _tw():
    import src.xgpedia.today_workflow as tw_mod
    return tw_mod


def _now_utc(now_utc: datetime | None = None) -> datetime:
    return _tw()._now_utc(now_utc)


def _parse_utc(raw: str):
    return _tw()._parse_utc(raw)


def _diagnose_exception(exc: Exception) -> str:
    return _tw()._diagnose_exception(exc)


@dataclass
class RecentFinishedMatchInfo:
    fixture_id: str
    home_en: str
    away_en: str
    home_fa: str
    away_fa: str
    home_goals: int
    away_goals: int
    kickoff_utc: str
    kickoff_tehran: str
    elapsed_fa: str
    finished_seconds_ago: float
    existing_post_id: int | None = None
    existing_post_status: str | None = None
    competition: str = "Premier League"


def _format_elapsed_fa(seconds: float) -> str:
    sec = max(1, int(seconds))
    if sec < 60:
        return "لحظاتی پیش"
    mins = sec // 60
    if mins < 60:
        return f"{mins} دقیقه پیش"
    hrs = mins // 60
    rem_m = mins % 60
    if rem_m >= 15 and hrs < 6:
        return f"{hrs} ساعت و {rem_m} دقیقه پیش"
    return f"{hrs} ساعت پیش"


def sync_recent_finished_matches(
    *, now_utc: datetime | None = None, hours: float = 24.0, enrich_optaxg: bool = False
) -> dict[str, Any]:
    """دریافت زندهٔ بازی‌های پایان‌یافته از ۱ ثانیه تا ۲۴ ساعت پیش از ESPN (/summary) + football-data.org."""
    from src.xgpedia.providers.espn_free import ESPNFreeProvider
    from src.xgpedia.sync import sync_espn_finished_matches, sync_finished_matches_from_fdo

    init_db()
    now = _now_utc(now_utc)
    fdo_saved = 0
    espn_saved = 0
    espn_stats = 0
    errors: list[str] = []

    # ۱) football-data.org (بازی‌های FINISHED ۲ روز اخیر برای همهٔ ۶ لیگ معتبر اروپا)
    try:
        from src.xgpedia.core.leagues import EUROPEAN_LEAGUES
        from src.xgpedia.providers.football_data_org import FootballDataOrg

        fdo = FootballDataOrg()
        try:
            for lg in EUROPEAN_LEAGUES:
                try:
                    raw_fin = fdo.played_fixtures(days_back=2, season_start=CURRENT_SEASON_START, competition=lg.code)
                    fdo_saved += sync_finished_matches_from_fdo(
                        raw_fin, season_start=CURRENT_SEASON_START, competition=lg.name_en
                    ).get("finished_saved", 0)
                except Exception:
                    continue
        finally:
            fdo.close()
    except Exception as e:
        errors.append(f"FDO: {type(e).__name__}")

    # ۲) ESPN Public /summary (آمار واقعی لحظه‌ای، گلزنان، مومنتوم ۵ دقیقه‌ای و دروازه‌بان بلافاصله پس از سوت پایان)
    try:
        espn = ESPNFreeProvider(timeout=12.0)
        try:
            finished_rows = espn.fetch_recent_finished_matches(now_utc=now, hours=hours)
        finally:
            espn.close()
        if finished_rows:
            s_res = sync_espn_finished_matches(finished_rows, season_start=CURRENT_SEASON_START)
            espn_saved = s_res.get("finished_saved", 0)
            espn_stats = s_res.get("stats_rows", 0)
    except Exception as e:
        errors.append(f"ESPN: {type(e).__name__}")

    # ۳) غنی‌سازی سنگین Opta/Playwright دیگر در صفحهٔ لیست اجرا نمی‌شود تا دریافت لیست در چند ثانیه تمام شود؛
    #    در صورت نیاز صریح (`enrich_optaxg=True`) یا هنگام بازکردن کارت هر بازی (`get_match_card_options`) انجام می‌شود.
    enriched_cnt = 0
    if enrich_optaxg:
        try:
            recent = _tw().list_recent_finished_fixtures(now_utc=now, hours=hours)
            for item in recent[:8]:
                er = enrich_post_match_fixture(item.fixture_id)
                if er.get("fpl") or er.get("understat"):
                    enriched_cnt += 1
        except Exception:
            pass

    return {
        "fdo_saved": fdo_saved,
        "espn_saved": espn_saved,
        "espn_stats": espn_stats,
        "enriched": enriched_cnt,
        "errors": errors,
    }


def list_recent_finished_fixtures(
    *, now_utc: datetime | None = None, hours: float = 24.0
) -> list[RecentFinishedMatchInfo]:
    """فهرست بازی‌های پایان‌یافته دقیقاً در بازهٔ ۱ ثانیه پیش تا `hours` ساعت پیش (جدیدترین اول)."""
    init_db()
    now = _now_utc(now_utc)
    min_ko = (now - timedelta(hours=hours + 3.0)).strftime("%Y-%m-%dT%H:%M:%SZ")

    with db() as conn:
        rows = conn.execute(
            """
            SELECT fixture_id, provider, competition, kickoff_utc, home_team, away_team
            FROM fixtures
            WHERE status = 'finished'
              AND kickoff_utc >= ?
            ORDER BY (SELECT COUNT(*) FROM fixture_statistics fs WHERE fs.fixture_id = fixtures.fixture_id) DESC, kickoff_utc DESC
            """,
            (min_ko,),
        ).fetchall()

        out: list[RecentFinishedMatchInfo] = []
        from src.xgpedia.config import canonical_team_name
        from src.xgpedia.providers.xg_engine import _teams_match

        seen_matches: list[tuple[str, str, str]] = []
        for r in rows:
            ko_raw = str(r["kickoff_utc"] or "")
            try:
                ko_dt = datetime.fromisoformat(ko_raw.replace("Z", "+00:00"))
                if ko_dt.tzinfo is None:
                    ko_dt = ko_dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue

            # برآورد لحظهٔ سوت پایان: کیک‌آف + ۱۱۵ دقیقه (اگر بازی تازه تمام شده و هنوز < 115m از کیک‌آف گذشته، حداقل ۱ ثانیه)
            est_end = ko_dt + timedelta(minutes=115)
            if ko_dt > now:
                continue
            elapsed_sec = (now - est_end).total_seconds()
            if elapsed_sec < 1.0:
                # بازی واقعاً status='finished' است و همین لحظه (مثلاً در دقیقه ۹۴) تمام شده
                if (now - ko_dt).total_seconds() >= 90 * 60:
                    elapsed_sec = 1.0
                else:
                    continue
            if elapsed_sec > hours * 3600.0:
                continue

            h_c = canonical_team_name(r["home_team"])
            a_c = canonical_team_name(r["away_team"])
            day_s = ko_raw[:10]
            is_dup = any(
                sd == day_s and _teams_match(h_c, sh) and _teams_match(a_c, sa)
                for sh, sa, sd in seen_matches
            )
            if is_dup:
                continue
            seen_matches.append((h_c, a_c, day_s))

            post_row = conn.execute(
                """
                SELECT post_id, status FROM posts
                WHERE fixture_id = ? AND post_type = 'post_match'
                ORDER BY post_id DESC LIMIT 1
                """,
                (r["fixture_id"],),
            ).fetchone()

            hg_row = conn.execute(
                "SELECT value FROM fixture_statistics WHERE fixture_id=? AND team=? AND metric='goals' ORDER BY collected_at DESC LIMIT 1",
                (r["fixture_id"], r["home_team"]),
            ).fetchone()
            ag_row = conn.execute(
                "SELECT value FROM fixture_statistics WHERE fixture_id=? AND team=? AND metric='goals' ORDER BY collected_at DESC LIMIT 1",
                (r["fixture_id"], r["away_team"]),
            ).fetchone()
            if not (hg_row and ag_row and hg_row["value"] is not None and ag_row["value"] is not None):
                continue

            out.append(
                RecentFinishedMatchInfo(
                    fixture_id=r["fixture_id"],
                    home_en=r["home_team"],
                    away_en=r["away_team"],
                    home_fa=team_name_fa(r["home_team"]),
                    away_fa=team_name_fa(r["away_team"]),
                    home_goals=int(round(float(hg_row["value"]))),
                    away_goals=int(round(float(ag_row["value"]))),
                    kickoff_utc=ko_raw,
                    kickoff_tehran=ko_dt.astimezone(TEHRAN_TZ).strftime("%H:%M"),
                    elapsed_fa=_format_elapsed_fa(elapsed_sec),
                    finished_seconds_ago=elapsed_sec,
                    existing_post_id=post_row["post_id"] if post_row else None,
                    existing_post_status=post_row["status"] if post_row else None,
                    competition=str(r["competition"] or "Premier League"),
                )
            )

    out.sort(key=lambda x: x.finished_seconds_ago)
    return out


def enrich_post_match_fixture(
    fixture_id: str, *, allow_playwright: bool = True, force: bool = False
) -> dict[str, bool]:
    """تکمیل خودکار دیتای پس‌ازبازی یک مسابقه از منابع رایگان FPL Official و موتور Opta (`xg_engine`) با کش دیتابیس."""
    from src.xgpedia.providers.fpl_free import FPLFreeProvider
    from src.xgpedia.sync import merge_post_match_details

    init_db()
    with db() as conn:
        fx = conn.execute(
            "SELECT home_team, away_team, kickoff_utc, competition FROM fixtures WHERE fixture_id = ?",
            (fixture_id,),
        ).fetchone()
        if not fx:
            return {"fpl": False, "understat": False}
        if not force:
            pm_row = conn.execute(
                "SELECT details_json FROM fixture_post_match WHERE fixture_id = ?",
                (fixture_id,),
            ).fetchone()
            has_xg_row = conn.execute(
                "SELECT 1 FROM fixture_statistics WHERE fixture_id=? AND metric='expected_goals' AND provider IN ('sofascore','fotmob','understat','api-football') LIMIT 1",
                (fixture_id,),
            ).fetchone()
            if pm_row and pm_row["details_json"] and has_xg_row:
                try:
                    _d = json.loads(pm_row["details_json"])
                    if int(_d.get("xg_enriched_v") or 0) >= 3 and _d.get("home_gk") and _d.get("away_gk") and _d.get("top_players"):
                        return {"fpl": False, "understat": False, "cached": True}
                except Exception:
                    pass

    h_en, a_en = fx["home_team"], fx["away_team"]
    m_date = str(fx["kickoff_utc"] or "")[:10]
    comp = str(fx["competition"] or "Premier League")
    fpl_ok = False
    us_ok = False

    # ۱) FPL Official Live GW -> فقط برای مسابقات لیگ برتر انگلیس
    if comp.lower() in ("premier league", "pl", "epl", "eng.1"):
        try:
            fpl = FPLFreeProvider(timeout=12.0)
            try:
                fpl_det = fpl.fetch_match_post_details(h_en, a_en, m_date)
            finally:
                fpl.close()
            if fpl_det:
                fpl_ok = merge_post_match_details(fixture_id, fpl_det, provider="fpl-official")
        except Exception:
            pass

    # ۲) موتور xG واقعی (SofaScore Opta → FotMob Opta → Understat) برای همهٔ ۶ لیگ + چمپیونزلیگ
    try:
        from src.xgpedia.providers.xg_engine import fetch_real_match_xg

        # پاک‌سازی هر xG تقریبی قدیمی espn-public پیش از ثبت xG واقعی Opta
        with db() as _c_purge:
            _c_purge.execute(
                "DELETE FROM fixture_statistics WHERE fixture_id=? AND metric='expected_goals' AND provider='espn-public'",
                (fixture_id,),
            )
        xg_det = fetch_real_match_xg(
            h_en,
            a_en,
            m_date,
            competition=comp,
            season_start=CURRENT_SEASON_START,
            timeout=12.0,
            allow_playwright=allow_playwright,
        )
        if xg_det:
            xg_prov = str(xg_det.get("provider") or "sofascore")
            extra_st: dict[str, dict[str, float]] = {}
            if xg_det.get("home_xg") is not None:
                extra_st.setdefault(h_en, {})["expected_goals"] = float(xg_det["home_xg"])
            if xg_det.get("away_xg") is not None:
                extra_st.setdefault(a_en, {})["expected_goals"] = float(xg_det["away_xg"])
            if xg_det.get("home_big_chances") is not None:
                extra_st.setdefault(h_en, {})["big_chances"] = float(xg_det["home_big_chances"])
            if xg_det.get("away_big_chances") is not None:
                extra_st.setdefault(a_en, {})["big_chances"] = float(xg_det["away_big_chances"])
            for _src_k, _dst_k, _tm in (
                ("home_possession", "possession", h_en),
                ("away_possession", "possession", a_en),
                ("home_total_shots", "total_shots", h_en),
                ("away_total_shots", "total_shots", a_en),
                ("home_shots_on_target", "shots_on_target", h_en),
                ("away_shots_on_target", "shots_on_target", a_en),
                ("home_corners", "corner_kicks", h_en),
                ("away_corners", "corner_kicks", a_en),
            ):
                if xg_det.get(_src_k) is not None:
                    extra_st.setdefault(_tm, {})[_dst_k] = float(xg_det[_src_k])
            patch_det: dict[str, Any] = {"xg_provider": xg_prov, "xg_enriched": True, "xg_enriched_v": 3}
            for k in (
                "home_shots",
                "away_shots",
                "home_inside_box",
                "away_inside_box",
                "momentum",
                "top_players",
                "motm",
                "home_gk",
                "away_gk",
            ):
                if xg_det.get(k) is not None:
                    patch_det[k] = xg_det[k]
            us_ok = merge_post_match_details(
                fixture_id,
                patch_det,
                provider=xg_prov,
                extra_stats=extra_st,
            )
    except Exception:
        pass

    return {"fpl": fpl_ok, "understat": us_ok}
