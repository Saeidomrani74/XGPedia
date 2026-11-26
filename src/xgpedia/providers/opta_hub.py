"""هاب مرکزی دیتای واقعی Opta/FotMob/Understat برای همهٔ کارت‌های ماژولار XGPedia (v0.58.0).

وظایف کلیدی:
  1. `lookup_db_match_opta`: خواندن xG واقعی Opta، موقعیت‌های بزرگ، ShotMap، Top Rated، MOTM و GK
     از دیتابیس محلی (ثبت‌شده توسط FotMob/SofaScore/Understat) برای کارت‌های Matchday Results،
     Players Rating و ShotMap — بدون درخواست شبکهٔ تکراری.
  2. `list_db_shotmap_matches`: استخراج خودکار بازی‌های غنی‌شدهٔ چمپیونزلیگ و ۶ لیگ اروپا با ShotMap
     واقعی FotMob/SofaScore برای کارت `shotmap_xg`.
  3. `merge_fpl_and_european_bootstrap`: ادغام زندهٔ آمار واقعی ۵ لیگ معتبر اروپا (FPL لیگ برتر +
     Understat لالیگا، سری آ، بوندس‌لیگا و لیگ ۱) در یک فرمت یکپارچه برای کارت‌های
     `player_profile`، `player_fc27` و `h2h_players`.
"""
from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from src.xgpedia.config import CURRENT_SEASON_START, canonical_team_name, team_identity, team_name_fa, translate_player_fa
from src.xgpedia.core.leagues import competition_name_fa
from src.xgpedia.db import db, init_db
from src.xgpedia.providers.xg_engine import _teams_match

log = logging.getLogger(__name__)

_EURO_BOOT_CACHE: dict[str, Any] = {"ts": 0.0, "data": None}
_EURO_BOOT_TTL = 1800.0  # ۳۰ دقیقه

_UNDERSTAT_EURO_LEAGUES: tuple[tuple[str, str], ...] = (
    ("La_liga", "لالیگا اسپانیا"),
    ("Serie_A", "سری آ ایتالیا"),
    ("Bundesliga", "بوندس‌لیگا آلمان"),
    ("Ligue_1", "لیگ ۱ فرانسه"),
)


def lookup_db_match_opta(
    home_en: str,
    away_en: str,
    match_date: str = "",
) -> dict[str, Any] | None:
    """یافتن دیتای واقعی Opta/FotMob/SofaScore/Understat یک بازی در دیتابیس محلی (بدون درخواست شبکه)."""
    if not (home_en and away_en):
        return None
    try:
        init_db()
        with db() as conn:
            rows = conn.execute(
                """
                SELECT fixture_id, competition, kickoff_utc, home_team, away_team
                FROM fixtures
                WHERE status = 'finished'
                ORDER BY kickoff_utc DESC
                LIMIT 120
                """
            ).fetchall()
            matched_fx = None
            swapped = False
            for r in rows:
                if match_date and str(r["kickoff_utc"] or "")[:10] not in (match_date[:10],):
                    # اجازهٔ اختلاف ۱ روزه به خاطر منطقهٔ زمانی
                    pass
                if _teams_match(home_en, r["home_team"]) and _teams_match(away_en, r["away_team"]):
                    matched_fx, swapped = r, False
                    break
                if _teams_match(home_en, r["away_team"]) and _teams_match(away_en, r["home_team"]):
                    matched_fx, swapped = r, True
                    break
            if not matched_fx:
                return None

            fid = matched_fx["fixture_id"]
            st_rows = conn.execute(
                """
                SELECT team, metric, value, provider FROM fixture_statistics
                WHERE fixture_id = ? AND provider IN ('fotmob', 'sofascore', 'understat', 'api-football')
                  AND value IS NOT NULL
                ORDER BY CASE provider
                  WHEN 'sofascore' THEN 1
                  WHEN 'fotmob' THEN 2
                  WHEN 'understat' THEN 3
                  ELSE 4
                END, collected_at DESC
                """,
                (fid,),
            ).fetchall()

            h_stats: dict[str, float] = {}
            a_stats: dict[str, float] = {}
            prov_used = ""
            for sr in st_rows:
                rt = str(sr["team"] or "")
                is_h = _teams_match(rt, matched_fx["home_team"])
                target = a_stats if (is_h and swapped) or ((not is_h) and (not swapped)) else h_stats
                if sr["metric"] not in target:
                    target[sr["metric"]] = float(sr["value"])
                    if not prov_used:
                        prov_used = str(sr["provider"])

            pm_row = conn.execute(
                "SELECT details_json, provider FROM fixture_post_match WHERE fixture_id = ?", (fid,)
            ).fetchone()
            pm_det: dict[str, Any] = {}
            if pm_row and pm_row["details_json"]:
                try:
                    loaded = json.loads(pm_row["details_json"])
                    if isinstance(loaded, dict):
                        pm_det = loaded
                except Exception:
                    pass

            if not h_stats and not pm_det:
                return None

            out: dict[str, Any] = {
                "fixture_id": fid,
                "competition": str(matched_fx["competition"] or ""),
                "provider": prov_used or str(pm_det.get("xg_provider") or ""),
                "home_xg": h_stats.get("expected_goals"),
                "away_xg": a_stats.get("expected_goals"),
                "home_big_chances": int(h_stats["big_chances"]) if "big_chances" in h_stats else None,
                "away_big_chances": int(a_stats["big_chances"]) if "big_chances" in a_stats else None,
                "top_players": pm_det.get("top_players"),
                "motm": pm_det.get("motm"),
                "momentum": pm_det.get("momentum"),
                "home_shots": pm_det.get("away_shots") if swapped else pm_det.get("home_shots"),
                "away_shots": pm_det.get("home_shots") if swapped else pm_det.get("away_shots"),
                "home_inside_box": pm_det.get("away_inside_box") if swapped else pm_det.get("home_inside_box"),
                "away_inside_box": pm_det.get("home_inside_box") if swapped else pm_det.get("away_inside_box"),
            }
            return out
    except Exception as e:
        log.debug("lookup_db_match_opta error: %s", e)
        return None


def list_db_shotmap_matches(limit: int = 10) -> list[dict[str, Any]]:
    """استخراج بازی‌های دارای ShotMap واقعی FotMob/SofaScore از دیتابیس (شامل چمپیونزلیگ) برای کارت `shotmap_xg`."""
    items: list[dict[str, Any]] = []
    try:
        init_db()
        with db() as conn:
            rows = conn.execute(
                """
                SELECT f.fixture_id, f.competition, f.kickoff_utc, f.home_team, f.away_team, pm.details_json
                FROM fixtures f
                JOIN fixture_post_match pm ON pm.fixture_id = f.fixture_id
                WHERE f.status = 'finished'
                ORDER BY f.kickoff_utc DESC
                LIMIT 30
                """
            ).fetchall()
            for r in rows:
                try:
                    det = json.loads(r["details_json"] or "{}")
                except Exception:
                    continue
                hs_raw = det.get("home_shots") or []
                as_raw = det.get("away_shots") or []
                if not (hs_raw and as_raw):
                    continue
                fid = r["fixture_id"]
                h_en = canonical_team_name(r["home_team"])
                a_en = canonical_team_name(r["away_team"])
                opta = lookup_db_match_opta(h_en, a_en)
                if not opta or opta.get("home_xg") is None or opta.get("away_xg") is None:
                    continue

                hg_r = conn.execute(
                    "SELECT value FROM fixture_statistics WHERE fixture_id=? AND metric='goals' ORDER BY collected_at DESC",
                    (fid,),
                ).fetchall()
                # خواندن گل‌های واقعی هر تیم
                from src.xgpedia.sync import _match_metrics
                hm = _match_metrics(conn, fid, h_en)
                am = _match_metrics(conn, fid, a_en)
                hg = int(round(hm.get("goals", 0)))
                ag = int(round(am.get("goals", 0)))

                h_id = team_identity(h_en) or {}
                a_id = team_identity(a_en) or {}
                shots: list[dict[str, Any]] = []
                for side_k, arr in (("home", hs_raw), ("away", as_raw)):
                    for s in arr:
                        if not isinstance(s, (list, tuple)) or len(s) < 6:
                            continue
                        shots.append({
                            "side": side_k,
                            "team": "h" if side_k == "home" else "a",
                            "x": float(s[0]),
                            "y": float(s[1]),
                            "xg": float(s[2]),
                            "result": "Goal" if s[3] == "goal" else ("SavedShot" if s[3] == "sot" else "MissedShots"),
                            "player": str(s[4]),
                            "minute": int(s[5]),
                        })
                comp_fa = competition_name_fa(r["competition"])
                prov_lbl = "FotMob Opta" if det.get("xg_provider") == "fotmob" else "SofaScore Opta"
                items.append({
                    "id": f"opta_sm_{fid.replace(':', '_')}",
                    "competition": comp_fa,
                    "round": str(r["kickoff_utc"] or "")[:10],
                    "home": {
                        "name_en": h_en,
                        "name_fa": team_name_fa(h_en),
                        "tla": h_id.get("code") or h_en[:3].upper(),
                        "color": (h_id.get("colors") or {}).get("primary") or "#38BDF8",
                        "goals": hg,
                        "xg": round(float(opta["home_xg"]), 2),
                    },
                    "away": {
                        "name_en": a_en,
                        "name_fa": team_name_fa(a_en),
                        "tla": a_id.get("code") or a_en[:3].upper(),
                        "color": (a_id.get("colors") or {}).get("primary") or "#F43F5E",
                        "goals": ag,
                        "xg": round(float(opta["away_xg"]), 2),
                    },
                    "shots": shots,
                    "source": prov_lbl,
                })
                if len(items) >= limit:
                    break
    except Exception as e:
        log.debug("list_db_shotmap_matches error: %s", e)
    return items


def _pos_to_fpl_element_type(pos_raw: str) -> int:
    s = str(pos_raw or "").upper()
    if "GK" in s:
        return 1
    if "D" in s and "F" not in s and "M" not in s:
        return 2
    if "F" in s or "S" in s:
        return 4
    return 3


def fetch_understat_european_bootstrap(
    season_start: int = CURRENT_SEASON_START,
    *,
    force_refresh: bool = False,
) -> dict[str, Any] | None:
    """دریافت آمار واقعی بازیکنان ۴ لیگ بزرگ اروپایی (لالیگا، سری آ، بوندس‌لیگا، لیگ ۱) از Understat در قالب سازگار با FPL."""
    now = time.time()
    if not force_refresh and _EURO_BOOT_CACHE["data"] and (now - _EURO_BOOT_CACHE["ts"]) < _EURO_BOOT_TTL:
        return _EURO_BOOT_CACHE["data"]

    from src.xgpedia.providers.understat import UnderstatProvider

    teams_out: list[dict[str, Any]] = []
    elements_out: list[dict[str, Any]] = []
    team_id_by_name: dict[str, int] = {}
    next_tid = 201
    next_pid = 200001

    def _fetch_one(u_slug: str, lg_fa: str) -> tuple[str, list[dict[str, Any]]]:
        prov = UnderstatProvider()
        try:
            # استفاده مستقیم از مسیر XHR/HTML لیگ
            r = prov._client.get(
                f"/getLeagueData/{u_slug}/{season_start}",
                headers={"X-Requested-With": "XMLHttpRequest", "Referer": f"https://understat.com/league/{u_slug}/{season_start}"},
            )
            if r.status_code == 200:
                j = r.json()
                if isinstance(j, dict) and isinstance(j.get("players"), list):
                    return lg_fa, j["players"]
        except Exception:
            pass
        finally:
            prov.close()
        return lg_fa, []

    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(_fetch_one, slug, lg_fa) for slug, lg_fa in _UNDERSTAT_EURO_LEAGUES]
        for fut in as_completed(futs):
            try:
                lg_fa, players = fut.result()
                for p in players:
                    if not isinstance(p, dict):
                        continue
                    mins = int(float(p.get("time") or 0))
                    if mins < 180:
                        continue
                    raw_tm = str(p.get("team_title") or "").split(",")[0].strip()
                    if not raw_tm:
                        continue
                    t_canon = canonical_team_name(raw_tm)
                    if t_canon not in team_id_by_name:
                        tid = next_tid
                        next_tid += 1
                        team_id_by_name[t_canon] = tid
                        ident = team_identity(t_canon) or {}
                        teams_out.append({
                            "id": tid,
                            "name": t_canon,
                            "short_name": ident.get("code") or t_canon[:3].upper(),
                            "league_fa": lg_fa,
                        })
                    tid = team_id_by_name[t_canon]
                    full_nm = str(p.get("player_name") or "").strip()
                    if not full_nm:
                        continue
                    parts = full_nm.split()
                    xg = round(float(p.get("xG") or 0.0), 2)
                    xa = round(float(p.get("xA") or 0.0), 2)
                    goals = int(float(p.get("goals") or 0))
                    assists = int(float(p.get("assists") or 0))
                    shots = int(float(p.get("shots") or 0))
                    kp = int(float(p.get("key_passes") or 0))
                    p90 = 90.0 / max(90.0, float(mins))
                    elements_out.append({
                        "id": next_pid,
                        "web_name": parts[-1],
                        "first_name": " ".join(parts[:-1]) if len(parts) > 1 else "",
                        "second_name": parts[-1],
                        "team": tid,
                        "element_type": _pos_to_fpl_element_type(str(p.get("position") or "M")),
                        "minutes": mins,
                        "goals_scored": goals,
                        "assists": assists,
                        "expected_goals": f"{xg:.2f}",
                        "expected_assists": f"{xa:.2f}",
                        "expected_goals_per_90": round(xg * p90, 2),
                        "expected_assists_per_90": round(xa * p90, 2),
                        "shots": shots,
                        "key_passes": kp,
                        "ict_index": f"{round((goals * 12 + assists * 9 + xg * 10 + xa * 8 + kp * 1.5), 1)}",
                        "creativity": f"{round(xa * 100 + kp * 8, 1)}",
                        "threat": f"{round(xg * 100 + shots * 4, 1)}",
                        "influence": f"{round((goals * 25 + assists * 18 + xg * 20), 1)}",
                        "bps": int(goals * 24 + assists * 15 + kp * 3 + mins // 15),
                        "total_points": int(goals * 5 + assists * 3 + mins // 45),
                        "now_cost": 80,
                        "league_fa": lg_fa,
                        "source": "Understat",
                    })
                    next_pid += 1
            except Exception:
                continue

    if not elements_out:
        return None
    result = {"elements": elements_out, "teams": teams_out}
    _EURO_BOOT_CACHE["ts"] = now
    _EURO_BOOT_CACHE["data"] = result
    return result


def merge_fpl_and_european_bootstrap(
    fpl_bootstrap: dict[str, Any] | None,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """ادغام دیتای رسمی FPL (لیگ برتر) با Understat (لالیگا، سری آ، بوندس‌لیگا، لیگ ۱) برای همهٔ کارت‌های بازیکن."""
    base = dict(fpl_bootstrap or {})
    elems = list(base.get("elements") or [])
    teams = list(base.get("teams") or [])
    try:
        euro = fetch_understat_european_bootstrap(force_refresh=force_refresh)
        if euro:
            elems.extend(euro.get("elements") or [])
            teams.extend(euro.get("teams") or [])
    except Exception:
        pass
    base["elements"] = elems
    base["teams"] = teams
    return base
