"""پارسر کامل جزئیات و ۷ ماژول Opta در FotMob (استخراج‌شده از xg_engine.py در v0.76.0)."""
from __future__ import annotations

import json
import re
from typing import Any

from src.xgpedia.config import translate_player_fa
from src.xgpedia.providers.xg_engine import _to_float


def _fotmob_pos_fa(raw_pos: Any, *, usual_position: Any = None) -> str:
    # در FotMob: usualPosition -> 0=دروازه‌بان، 1=مدافع، 2=هافبک، 3=مهاجم | positionId -> 11=دروازه‌بان
    if usual_position is not None and str(usual_position).strip() != "":
        up = str(usual_position).strip().lower()
        if up in ("0", "gk", "keeper", "goalkeeper"):
            return "دروازه‌بان"
        if up in ("1", "def", "defender"):
            return "مدافع"
        if up in ("2", "mid", "midfielder"):
            return "هافبک"
        if up in ("3", "att", "attacker", "fw", "forward"):
            return "مهاجم"
    s = str(raw_pos if raw_pos is not None else "").strip().lower()
    if s in ("0", "11", "gk", "goalkeeper", "keeper"):
        return "دروازه‌بان"
    if s in ("1",) or any(k in s for k in ("def", "back", "cb", "lb", "rb", "lwb", "rwb")):
        return "مدافع"
    if s in ("2",) or any(k in s for k in ("mid", "cm", "dm", "am", "cdm", "cam", "lm", "rm")):
        return "هافبک"
    return "مهاجم"


def _fotmob_player_name(pl: dict[str, Any]) -> str:
    """استخراج ایمن نام بازیکن از آبجکت بازیکن FotMob (پشتیبانی از str و dict)."""
    nm = pl.get("name")
    if isinstance(nm, dict):
        full = str(nm.get("fullName") or "").strip()
        if full:
            return full
        first = str(nm.get("firstName") or "").strip()
        last = str(nm.get("lastName") or "").strip()
        joined = f"{first} {last}".strip()
        if joined:
            return joined
    elif isinstance(nm, str) and nm.strip():
        return nm.strip()
    for k in ("shortName", "fullName"):
        v = pl.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    first = str(pl.get("firstName") or "").strip()
    last = str(pl.get("lastName") or "").strip()
    return f"{first} {last}".strip()


def _fotmob_stat_val(stats_list: Any, keys: tuple[str, ...]) -> float | None:
    if isinstance(stats_list, dict):
        for k, v in stats_list.items():
            if str(k).strip().lower() in keys:
                if isinstance(v, dict):
                    v = (v.get("stat") or {}).get("value") if isinstance(v.get("stat"), dict) else v.get("value")
                fv = _to_float(v)
                if fv is not None:
                    return fv
        for v in stats_list.values():
            if isinstance(v, (dict, list)):
                found = _fotmob_stat_val(v, keys)
                if found is not None:
                    return found
    elif isinstance(stats_list, list):
        for item in stats_list:
            if isinstance(item, dict):
                k = str(item.get("key") or item.get("title") or "").strip().lower()
                if k in keys:
                    st = item.get("stat") if isinstance(item.get("stat"), dict) else item
                    fv = _to_float(st.get("value"))
                    if fv is not None:
                        return fv
                for sub in item.values():
                    if isinstance(sub, (dict, list)):
                        found = _fotmob_stat_val(sub, keys)
                        if found is not None:
                            return found
    return None


def parse_fotmob_match_details(payload: dict[str, Any]) -> dict[str, Any]:
    """استخراج کامل هر ۷ ماژول پس‌ازبازی از پاسخ `/api/matchDetails` یا `__NEXT_DATA__` فوت‌موب:
    xG واقعی Opta، ShotMap دقیقه‌به‌دقیقه، داخل محوطه، موج فشار، Top Rated، MOTM و دروازه‌بان‌ها.
    """
    if not isinstance(payload, dict):
        return {}
    root = payload
    if "props" in root and isinstance(root["props"], dict):
        root = root["props"].get("pageProps") or root
    content = root.get("content") if isinstance(root, dict) else None
    if not isinstance(content, dict):
        return {}
    general = root.get("general") if isinstance(root.get("general"), dict) else {}
    header = root.get("header") if isinstance(root.get("header"), dict) else {}

    home_id = (general.get("homeTeam") or {}).get("id")
    away_id = (general.get("awayTeam") or {}).get("id")
    header_teams = header.get("teams") if isinstance(header.get("teams"), list) else []
    home_goals = _to_float(header_teams[0].get("score")) if len(header_teams) >= 2 and isinstance(header_teams[0], dict) else None
    away_goals = _to_float(header_teams[1].get("score")) if len(header_teams) >= 2 and isinstance(header_teams[1], dict) else None
    if (home_goals is None or away_goals is None) and isinstance(header.get("status"), dict):
        score_str = str((header.get("status") or {}).get("scoreStr") or "")
        m_sc = re.search(r"(\d+)\s*[-–:]\s*(\d+)", score_str)
        if m_sc:
            home_goals = float(m_sc.group(1))
            away_goals = float(m_sc.group(2))
    if home_id is None and len(header_teams) >= 2:
        home_id = header_teams[0].get("id")
        away_id = header_teams[1].get("id")

    # ── ۱) آمار کلی تیم‌ها (xG, Big Chances, Inside Box, Possession, Shots, SOT, Corners) ──
    stats_obj = content.get("stats") or {}
    periods = stats_obj.get("Periods") if isinstance(stats_obj, dict) else None
    all_stats = (periods.get("All") or {}).get("stats") if isinstance(periods, dict) else None
    if not isinstance(all_stats, list):
        all_stats = stats_obj.get("E") if isinstance(stats_obj.get("E"), list) else []

    out: dict[str, Any] = {}
    for grp in all_stats:
        if not isinstance(grp, dict):
            continue
        for item in grp.get("stats") or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip().lower()
            title = str(item.get("title") or "").strip().lower()
            vals = item.get("stats")
            if not isinstance(vals, list) or len(vals) < 2:
                continue
            hv, av = _to_float(vals[0]), _to_float(vals[1])
            if key == "expected_goals" or title in ("expected goals (xg)", "expected goals"):
                if hv is not None and av is not None:
                    out["home_xg"], out["away_xg"] = hv, av
            elif key == "big_chance" or title == "big chances":
                if hv is not None and av is not None:
                    out["home_big_chances"], out["away_big_chances"] = int(round(hv)), int(round(av))
            elif key == "shots_inside_box" or title == "shots inside box":
                if hv is not None and av is not None:
                    out["home_inside_box"], out["away_inside_box"] = int(round(hv)), int(round(av))
            elif key in ("ballposs", "ballposses", "possession") or "possession" in title:
                if hv is not None and av is not None:
                    out["home_possession"], out["away_possession"] = hv, av
            elif key == "total_shots" or title == "total shots":
                if hv is not None and av is not None:
                    out["home_total_shots"], out["away_total_shots"] = hv, av
            elif key in ("shotsontarget", "shots_on_target") or title == "shots on target":
                if hv is not None and av is not None:
                    out["home_shots_on_target"], out["away_shots_on_target"] = hv, av
            elif key == "corners" or title == "corners":
                if hv is not None and av is not None:
                    out["home_corners"], out["away_corners"] = hv, av
            elif key in ("keeper_saves", "saves", "goalkeeper_saves") or title in ("keeper saves", "saves", "goalkeeper saves"):
                if hv is not None and av is not None:
                    out["home_saves"], out["away_saves"] = hv, av

    # ── ۲) ShotMap دقیقه‌به‌دقیقه (برای xgrace و shotmap) ──
    sm_obj = content.get("shotmap") if isinstance(content.get("shotmap"), dict) else {}
    raw_shots = sm_obj.get("shots") if isinstance(sm_obj.get("shots"), list) else []
    if raw_shots and home_id is not None:
        h_shots: list[list[Any]] = []
        a_shots: list[list[Any]] = []
        h_box = 0
        a_box = 0
        for sh in raw_shots:
            if not isinstance(sh, dict):
                continue
            xg_s = _to_float(sh.get("expectedGoals"))
            if xg_s is None:
                xg_s = 0.0
            rx = _to_float(sh.get("x"))
            ry = _to_float(sh.get("y"))
            # FotMob pitch: 105×68 -> نرمال به 100×100
            x_n = round(max(0.0, min(100.0, (rx / 105.0) * 100.0)), 1) if rx is not None else 88.0
            y_n = round(max(0.0, min(100.0, (ry / 68.0) * 100.0)), 1) if ry is not None else 50.0
            ev_t = str(sh.get("eventType") or "").strip().lower()
            if ev_t == "goal":
                stype = "goal"
            elif ev_t in ("attemptsaved", "post") or sh.get("isOnTarget"):
                stype = "sot"
            else:
                stype = "miss"
            p_fa = translate_player_fa(str(sh.get("playerName") or ""))
            minute = int(sh.get("min") or 0)
            entry = [x_n, y_n, round(xg_s, 3), stype, p_fa, minute]
            is_in_box = (x_n >= 84.0 and 20.0 <= y_n <= 80.0)
            if str(sh.get("teamId")) == str(home_id):
                h_shots.append(entry)
                if is_in_box:
                    h_box += 1
            else:
                a_shots.append(entry)
                if is_in_box:
                    a_box += 1
        h_shots.sort(key=lambda r: r[5])
        a_shots.sort(key=lambda r: r[5])
        if h_shots and a_shots:
            out["home_shots"] = h_shots
            out["away_shots"] = a_shots
            out.setdefault("home_inside_box", h_box)
            out.setdefault("away_inside_box", a_box)

    # ── ۳) موج فشار ۵ دقیقه‌ای (Momentum: 18 سطل) ──
    mom_obj = content.get("momentum") if isinstance(content.get("momentum"), dict) else {}
    mom_main = (mom_obj.get("main") or {}).get("data") if isinstance(mom_obj.get("main"), dict) else None
    if isinstance(mom_main, list) and len(mom_main) >= 10:
        buckets = [0.0] * 18
        counts = [0] * 18
        for pt in mom_main:
            if not isinstance(pt, dict):
                continue
            mn = _to_float(pt.get("minute"))
            val = _to_float(pt.get("value"))
            if mn is None or val is None:
                continue
            b_idx = max(0, min(17, int(mn - 1) // 5))
            buckets[b_idx] += val
            counts[b_idx] += 1
        out["momentum"] = [
            round(buckets[i] / counts[i], 1) if counts[i] else 0.0 for i in range(18)
        ]

    # ── ۴) برترین‌های زمین (Top Rated)، ستاره زمین (MOTM) و دروازه‌بان‌ها (GK) ──
    player_stats = content.get("playerStats") if isinstance(content.get("playerStats"), dict) else {}
    lineup = content.get("lineup") if isinstance(content.get("lineup"), dict) else {}
    rated_players: list[dict[str, Any]] = []
    gk_by_side: dict[str, dict[str, Any]] = {}

    def _collect_from_lineup_side(team_obj: Any, side_key: str) -> None:
        if not isinstance(team_obj, dict):
            return
        pool: list[dict[str, Any]] = []
        for k_list in ("starters", "subs", "bench", "players"):
            arr = team_obj.get(k_list)
            if isinstance(arr, list):
                for item in arr:
                    if isinstance(item, dict):
                        pool.append(item)
                    elif isinstance(item, list):
                        pool.extend(x for x in item if isinstance(x, dict))
        for pl in pool:
            pid = str(pl.get("id") or "")
            raw_nm = _fotmob_player_name(pl)
            if not raw_nm:
                continue
            p_fa = translate_player_fa(raw_nm)
            perf = pl.get("performance") if isinstance(pl.get("performance"), dict) else {}
            rating = _to_float(perf.get("rating"))
            if rating is None:
                rating = _to_float((pl.get("rating") or {}).get("num") if isinstance(pl.get("rating"), dict) else pl.get("rating"))
            pstat = player_stats.get(pid) if pid and isinstance(player_stats.get(pid), dict) else {}
            if rating is None and pstat:
                rating = _fotmob_stat_val(pstat.get("stats"), ("fotmob rating", "rating_title", "rating"))

            shirt = int(_to_float(pl.get("shirtNumber") or pl.get("shirt")) or 0)
            pos_str = _fotmob_pos_fa(
                pl.get("positionId") if pl.get("positionId") is not None else pl.get("role"),
                usual_position=pl.get("usualPosition") if pl.get("usualPosition") is not None else pstat.get("usualPosition"),
            )
            goals = int(_fotmob_stat_val(pstat.get("stats"), ("goals",)) or 0)
            assists = int(_fotmob_stat_val(pstat.get("stats"), ("assists",)) or 0)
            key_passes = int(_fotmob_stat_val(pstat.get("stats"), ("chances created", "key passes", "chances_created")) or 0)
            xg_p = _fotmob_stat_val(pstat.get("stats"), ("expected goals (xg)", "expected_goals"))
            saves = _fotmob_stat_val(pstat.get("stats"), ("saves", "keeper_saves", "goalkeeper_saves"))
            xgot = _fotmob_stat_val(
                pstat.get("stats"),
                (
                    "expected goals on target (xgot) faced",
                    "expected goals on target faced",
                    "expected_goals_on_target_faced",
                    "xgot faced",
                ),
            )
            goals_conc = _fotmob_stat_val(pstat.get("stats"), ("goals conceded", "goals_conceded"))

            # ثبت دروازه‌بان اصلی هر تیم (با تکیه بر آمار واقعی بازیکن یا آمار واقعی مهار تیم در FotMob)
            is_gk = bool(
                pos_str == "دروازه‌بان"
                or pl.get("isGoalkeeper")
                or pstat.get("isGoalkeeper")
                or str(pl.get("role") or "").strip().lower() == "keeper"
            )
            if (is_gk or saves is not None) and side_key not in gk_by_side:
                eff_saves = saves
                if eff_saves is None and is_gk:
                    eff_saves = out.get("home_saves") if side_key == "home" else out.get("away_saves")
                opp_g = away_goals if side_key == "home" else home_goals
                if opp_g is None and goals_conc is not None:
                    opp_g = goals_conc
                opp_xg = out.get("away_xg") if side_key == "home" else out.get("home_xg")
                psxg_v = xgot
                if eff_saves is not None and psxg_v is not None:
                    gk_by_side[side_key] = {
                        "name": p_fa,
                        "saves": int(round(eff_saves)),
                        "psxg": round(float(psxg_v), 2),
                        "ga": int(round(opp_g)) if opp_g is not None else None,
                    }

            if rating is not None and rating > 0:
                stat_parts: list[str] = []
                if goals:
                    stat_parts.append(f"{goals} گل")
                if assists:
                    stat_parts.append(f"{assists} پاس گل")
                if key_passes and len(stat_parts) < 2:
                    stat_parts.append(f"{key_passes} موقعیت")
                if xg_p is not None and xg_p >= 0.2 and len(stat_parts) < 2:
                    stat_parts.append(f"{xg_p:.2f} xG")
                if saves is not None and saves >= 1 and not stat_parts:
                    stat_parts.append(f"{int(round(saves))} مهار")
                stat_lbl = " • ".join(stat_parts) if stat_parts else f"امتیاز {rating:.1f}"
                chip_objs: list[dict[str, str]] = []
                if goals:
                    chip_objs.append({"label": "گل", "val": str(goals)})
                if assists:
                    chip_objs.append({"label": "پاس گل", "val": str(assists)})
                if key_passes and len(chip_objs) < 2:
                    chip_objs.append({"label": "موقعیت", "val": str(key_passes)})
                if xg_p is not None and xg_p >= 0.2 and len(chip_objs) < 2:
                    chip_objs.append({"label": "xG", "val": f"{xg_p:.2f}"})
                if saves is not None and saves >= 1 and not chip_objs:
                    chip_objs.append({"label": "مهار", "val": str(int(round(saves)))})
                chip_objs.append({"label": "امتیاز FotMob", "val": f"{rating:.1f}"})
                rated_players.append({
                    "name": p_fa,
                    "side": side_key,
                    "stat": stat_lbl,
                    "rating": round(rating, 1),
                    "pos": pos_str,
                    "number": shirt,
                    "chips": chip_objs[:3],
                })

    home_lu = lineup.get("homeTeam")
    away_lu = lineup.get("awayTeam")
    if (not home_lu or not away_lu) and isinstance(lineup.get("lineup"), list) and len(lineup["lineup"]) >= 2:
        lu_list = lineup["lineup"]
        home_lu = home_lu or (lu_list[0] if isinstance(lu_list[0], dict) else None)
        away_lu = away_lu or (lu_list[1] if isinstance(lu_list[1], dict) else None)
    _collect_from_lineup_side(home_lu, "home")
    _collect_from_lineup_side(away_lu, "away")

    # اگر دروازه‌بان از lineup استخراج نشد اما در playerStats وجود داشت
    if (len(gk_by_side) < 2) and player_stats and home_id is not None:
        for pid, pstat in player_stats.items():
            if not isinstance(pstat, dict):
                continue
            raw_nm = _fotmob_player_name(pstat)
            if not raw_nm:
                continue
            side_key = "home" if str(pstat.get("teamId")) == str(home_id) else "away"
            if side_key in gk_by_side:
                continue
            pos_str = _fotmob_pos_fa(pstat.get("positionId"), usual_position=pstat.get("usualPosition"))
            saves = _fotmob_stat_val(pstat.get("stats"), ("saves", "keeper_saves", "goalkeeper_saves"))
            is_gk = bool(pos_str == "دروازه‌بان" or pstat.get("isGoalkeeper"))
            if is_gk or saves is not None:
                eff_saves = saves if saves is not None else (out.get("home_saves") if side_key == "home" else out.get("away_saves"))
                xgot = _fotmob_stat_val(
                    pstat.get("stats"),
                    (
                        "expected goals on target (xgot) faced",
                        "expected goals on target faced",
                        "expected_goals_on_target_faced",
                        "xgot faced",
                        ),
                )
                opp_g = away_goals if side_key == "home" else home_goals
                if opp_g is None:
                    opp_g = _fotmob_stat_val(pstat.get("stats"), ("goals conceded", "goals_conceded"))
                opp_xg = out.get("away_xg") if side_key == "home" else out.get("home_xg")
                psxg_v = xgot
                if eff_saves is not None and psxg_v is not None:
                    gk_by_side[side_key] = {
                        "name": translate_player_fa(raw_nm),
                        "saves": int(round(eff_saves)),
                        "psxg": round(float(psxg_v), 2),
                        "ga": int(round(opp_g)) if opp_g is not None else None,
                    }

    # اگر lineup خالی بود اما playerStats مستقیم وجود داشت
    if not rated_players and player_stats and home_id is not None:
        for pid, pstat in player_stats.items():
            if not isinstance(pstat, dict):
                continue
            raw_nm = str(pstat.get("name") or "").strip()
            if not raw_nm:
                continue
            rating = _fotmob_stat_val(pstat.get("stats"), ("fotmob rating", "rating_title", "rating"))
            if rating is None or rating <= 0:
                continue
            side_key = "home" if str(pstat.get("teamId")) == str(home_id) else "away"
            goals = int(_fotmob_stat_val(pstat.get("stats"), ("goals",)) or 0)
            assists = int(_fotmob_stat_val(pstat.get("stats"), ("assists",)) or 0)
            stat_parts = ([f"{goals} گل"] if goals else []) + ([f"{assists} پاس گل"] if assists else [])
            rated_players.append({
                "name": translate_player_fa(raw_nm),
                "side": side_key,
                "stat": " • ".join(stat_parts) if stat_parts else f"امتیاز {rating:.1f}",
                "rating": round(rating, 1),
                "pos": _fotmob_pos_fa(pstat.get("positionId"), usual_position=pstat.get("usualPosition")),
                "number": int(_to_float(pstat.get("shirtNumber")) or 0),
                "chips": (
                    ([{"label": "گل", "val": str(goals)}] if goals else [])
                    + ([{"label": "پاس گل", "val": str(assists)}] if assists else [])
                    + [{"label": "امتیاز FotMob", "val": f"{rating:.1f}"}]
                )[:3],
            })

    if gk_by_side.get("home"):
        out["home_gk"] = gk_by_side["home"]
    if gk_by_side.get("away"):
        out["away_gk"] = gk_by_side["away"]

    if rated_players:
        rated_players.sort(key=lambda r: r["rating"], reverse=True)
        out["top_players"] = [
            {"name": r["name"], "side": r["side"], "stat": r["stat"], "rating": r["rating"]}
            for r in rated_players[:5]
        ]
        if len(rated_players) >= 2:
            best = rated_players[0]
            runner = next((r for r in rated_players[1:] if r["side"] != best["side"]), rated_players[1])
            out["motm"] = {
                "side": best["side"],
                "name": best["name"],
                "pos": best["pos"],
                "number": best["number"],
                "rating": best["rating"],
                "chips": best["chips"] or [{"label": "امتیاز FotMob", "val": f"{best['rating']:.1f}"}],
                "runnerUp": {
                    "side": runner["side"],
                    "name": runner["name"],
                    "stat": runner["stat"],
                    "rating": runner["rating"],
                },
            }

    return out


def parse_fotmob_next_data_html(html_text: str) -> dict[str, Any]:
    """استخراج JSON رسمی `__NEXT_DATA__` از صفحهٔ HTML مسابقه در FotMob (بدون نیاز به هدر `x-mas`)."""
    m = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html_text or "", flags=re.DOTALL)
    if not m:
        return {}
    try:
        return parse_fotmob_match_details(json.loads(m.group(1)))
    except Exception as _em_exc:
        from src.xgpedia.core.error_metrics import record_error as _rec_err
        _rec_err("provider.xg_engine", _em_exc)
        return {}
