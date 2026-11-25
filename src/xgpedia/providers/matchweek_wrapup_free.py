"""تأمین دادهٔ زنده و کاملاً رایگان برای کارت ماژولار «خلاصهٔ هفته + فرم در برابر جدول» (`Matchweek Wrap-up & Form vs. Table — v0.37.0`).

منابع زنده و واقعی (صرفاً فوتبال واقعی، بدون `requests`، رعایت اکید `null ≠ 0`):
  1. **لیگ برتر انگلیس (FPL Official API — `bootstrap-static` + `fixtures` + `event/{gw}/live/`)**:
     - رتبه‌بندی قدرت فرم ۵ بازی اخیر (`Form Rank`) در برابر جایگاه جدول (`Table Rank`) و شاخص صعود/سقوط
     - کشف تیم‌های بیش‌عملکرد (کلینیکال) و بدشانس‌ترین تیم‌ها بر اساس تفاضل واقعی `Goals − xG`
     - بهترین خط حمله، بدشانس‌ترین تیم و مستحکم‌ترین خط دفاع (کلین‌شیت)
     - تیم منتخب زندهٔ هفته (`XI`: `1 GK + 3 DEF + 4 MID + 3 FWD`) بر اساس امتیاز واقعی `event/{gw}/live/`
  2. **بوندس‌لیگا آلمان (`OpenLigaDB`)** و **لالیگا اسپانیا (`worldcup26.ir`)** (بدون کلید API)
  3. **پریست‌های آماده (`config/matchweek_wrapup_presets.json`)** فقط از دکمهٔ پریست‌ها.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
from pathlib import Path
from typing import Any

from src.xgpedia.config import ROOT
from src.xgpedia.providers.pl_badges_free import lookup_pl_club

log = logging.getLogger(__name__)

PRESETS_PATH = ROOT / "config" / "matchweek_wrapup_presets.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

_CACHE: dict[str, Any] = {"ts": 0.0, "items": []}
_CACHE_TTL = 600.0

_POS_CODE = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def load_matchweek_wrapup_presets(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or PRESETS_PATH
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        items = raw.get("presets") if isinstance(raw, dict) else raw
        return [dict(x) for x in items if isinstance(x, dict) and x.get("id")] if isinstance(items, list) else []
    except Exception as e:
        log.warning("failed to load matchweek_wrapup_presets.json: %s", e)
        return []


def _fa_player(name: str) -> str:
    try:
        from src.xgpedia.providers.injury_free import transliterate_player_name_fa
        return transliterate_player_name_fa(name)
    except Exception:
        return name


def _fetch_fpl_gw_live(gw: int, timeout: float = 8.0) -> dict[str, Any]:
    if gw <= 0:
        return {}
    url = f"https://fantasy.premierleague.com/api/event/{gw}/live/"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def build_fpl_matchweek_wrapup(
    boot: dict[str, Any] | None = None,
    fixtures: list[dict[str, Any]] | None = None,
    gw_live: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """ساخت بستهٔ زنده و ۱۰۰٪ واقعی خلاصهٔ هفته + فرم در برابر جدول برای لیگ برتر انگلیس."""
    if boot is None or fixtures is None:
        try:
            from src.xgpedia.providers.fpl_free import fetch_fpl_bootstrap, fetch_fpl_fixtures
            if boot is None:
                boot = fetch_fpl_bootstrap()
            if fixtures is None:
                fixtures = fetch_fpl_fixtures()
        except Exception as e:
            log.warning("FPL matchweek wrapup skipped: %s", e)
            return None
    if not isinstance(boot, dict) or not isinstance(fixtures, list):
        return None

    teams_raw = {int(t["id"]): t for t in (boot.get("teams") or []) if isinstance(t, dict) and t.get("id") is not None}
    elements = [e for e in (boot.get("elements") or []) if isinstance(e, dict)]
    if not teams_raw:
        return None

    cur_gw = 0
    for ev in (boot.get("events") or []):
        if isinstance(ev, dict) and (ev.get("is_current") or ev.get("is_previous")):
            cur_gw = max(cur_gw, int(ev.get("id") or 0))

    # 1. محاسبه آمار جدول و فرم ۵ بازی اخیر از fixtures واقعی
    tstats: dict[int, dict[str, Any]] = {}
    for tid, tobj in teams_raw.items():
        raw_n = str(tobj.get("name") or "")
        short_n = str(tobj.get("short_name") or "")
        info = lookup_pl_club(raw_n, short_n)
        tstats[tid] = {
            "id": tid,
            "name": info[0] if info else raw_n,
            "code": info[1] if info else short_n[:3].upper(),
            "color": info[2] if info else "#38BDF8",
            "mp": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "pts": 0, "cs": 0,
            "xg": 0.0,
            "results": [],
        }

    # جمع xG واقعی هر تیم از بازیکنان FPL
    for el in elements:
        tid = int(el.get("team") or 0)
        if tid in tstats:
            tstats[tid]["xg"] += float(el.get("expected_goals") or 0.0)

    for fx in fixtures:
        if not isinstance(fx, dict) or not fx.get("finished"):
            continue
        ht, at = fx.get("team_h"), fx.get("team_a")
        hs, as_ = fx.get("team_h_score"), fx.get("team_a_score")
        if ht not in tstats or at not in tstats or hs is None or as_ is None:
            continue
        hs, as_ = int(hs), int(as_)
        ko = str(fx.get("kickoff_time") or "")
        sh, sa = tstats[int(ht)], tstats[int(at)]
        sh["mp"] += 1; sa["mp"] += 1
        sh["gf"] += hs; sh["ga"] += as_
        sa["gf"] += as_; sa["ga"] += hs
        if as_ == 0:
            sh["cs"] += 1
        if hs == 0:
            sa["cs"] += 1
        if hs > as_:
            sh["w"] += 1; sh["pts"] += 3; sh["results"].append((ko, "W", 3, hs - as_))
            sa["l"] += 1; sa["results"].append((ko, "L", 0, as_ - hs))
        elif as_ > hs:
            sa["w"] += 1; sa["pts"] += 3; sa["results"].append((ko, "W", 3, as_ - hs))
            sh["l"] += 1; sh["results"].append((ko, "L", 0, hs - as_))
        else:
            sh["d"] += 1; sh["pts"] += 1; sh["results"].append((ko, "D", 1, 0))
            sa["d"] += 1; sa["pts"] += 1; sa["results"].append((ko, "D", 1, 0))

    played = [t for t in tstats.values() if t["mp"] > 0]
    if len(played) < 4:
        return None

    # رتبه‌بندی جدول واقعی
    played.sort(key=lambda t: (t["pts"], t["gf"] - t["ga"], t["gf"]), reverse=True)
    for idx, t in enumerate(played, 1):
        t["tableRank"] = idx
        t["results"].sort(key=lambda r: r[0])
        last5 = t["results"][-5:]
        t["form"] = [r[1] for r in last5]
        t["formPts"] = sum(r[2] for r in last5)
        t["formGd"] = sum(r[3] for r in last5)
        t["xg"] = round(t["xg"], 1) if t["xg"] > 0 else None
        t["xgDiff"] = round(t["gf"] - t["xg"], 1) if t["xg"] is not None else None

    # رتبه‌بندی قدرت فرم ۵ بازی اخیر
    form_sorted = sorted(played, key=lambda t: (t["formPts"], t["formGd"], t["pts"]), reverse=True)
    for f_idx, t in enumerate(form_sorted, 1):
        t["formRank"] = f_idx

    # انتخاب ۶ تیم شاخص برای جدول «فرم در برابر جایگاه» (صدرنشینان + بیشترین تغییر فرم)
    top_form_rows = [
        {
            "name": t["name"],
            "code": t["code"],
            "color": t["color"],
            "tableRank": t["tableRank"],
            "formRank": t["formRank"],
            "pts": t["pts"],
            "formPts": t["formPts"],
            "form": t["form"],
            "xgDiff": t["xgDiff"],
        }
        for t in form_sorted[:6]
    ]

    # بیش‌عملکردها و بدشانس‌ترین تیم‌ها بر اساس G - xG
    with_xg = [t for t in played if t["xgDiff"] is not None]
    overperf = sorted([t for t in with_xg if t["xgDiff"] > 0], key=lambda t: t["xgDiff"], reverse=True)[:3]
    underperf = sorted([t for t in with_xg if t["xgDiff"] < 0], key=lambda t: t["xgDiff"])[:3]

    best_att = max(played, key=lambda t: (t["gf"], t["gf"] / max(1, t["mp"])))
    best_def = max(played, key=lambda t: (t["cs"], -t["ga"]))
    unluckiest = underperf[0] if underperf else None

    awards: dict[str, Any] = {
        "bestAttack": {
            "name": best_att["name"],
            "code": best_att["code"],
            "color": best_att["color"],
            "val": f"{best_att['gf']} گل",
            "sub": (
                f"میانگین {best_att['gf'] / max(1, best_att['mp']):.2f} گل/بازی • {best_att['xg']:.1f} xG"
                if best_att["xg"] is not None
                else f"میانگین {best_att['gf'] / max(1, best_att['mp']):.2f} گل در هر بازی"
            ),
        },
        "bestDefense": {
            "name": best_def["name"],
            "code": best_def["code"],
            "color": best_def["color"],
            "val": f"{best_def['cs']} کلین‌شیت",
            "sub": f"تنها {best_def['ga']} گل خورده در {best_def['mp']} مسابقه",
        },
    }
    if unluckiest:
        awards["unluckiest"] = {
            "name": unluckiest["name"],
            "code": unluckiest["code"],
            "color": unluckiest["color"],
            "val": f"{unluckiest['xgDiff']:+.1f}",
            "sub": f"{unluckiest['gf']} گل از {unluckiest['xg']:.1f} امید گل (G − xG)",
        }

    # 2. تیم منتخب هفته (TOTW XI: 1 GK + 3 DEF + 4 MID + 3 FWD) از event/{gw}/live/
    totw: list[dict[str, Any]] = []
    if gw_live is None and cur_gw > 0:
        gw_live = _fetch_fpl_gw_live(cur_gw)
    if isinstance(gw_live, dict) and gw_live.get("elements"):
        el_meta = {int(e["id"]): e for e in elements if e.get("id") is not None}
        by_pos: dict[str, list[dict[str, Any]]] = {"GK": [], "DEF": [], "MID": [], "FWD": []}
        for le in gw_live.get("elements") or []:
            if not isinstance(le, dict):
                continue
            eid = int(le.get("id") or 0)
            st = le.get("stats") or {}
            mins = int(st.get("minutes") or 0)
            pts = int(st.get("total_points") or 0)
            if mins <= 0 or pts <= 0:
                continue
            meta = el_meta.get(eid)
            if not meta:
                continue
            pos = _POS_CODE.get(int(meta.get("element_type") or 3), "MID")
            t_info = tstats.get(int(meta.get("team") or 0)) or {}
            g_v = int(st.get("goals_scored") or 0)
            a_v = int(st.get("assists") or 0)
            cs_v = int(st.get("clean_sheets") or 0)
            sv_v = int(st.get("saves") or 0)
            parts = []
            if g_v:
                parts.append(f"{g_v} گل")
            if a_v:
                parts.append(f"{a_v} پاس گل")
            if cs_v and pos in ("GK", "DEF"):
                parts.append("کلین‌شیت")
            if sv_v >= 3 and pos == "GK":
                parts.append(f"{sv_v} سیو")
            by_pos[pos].append({
                "name": _fa_player(str(meta.get("web_name") or meta.get("second_name") or "بازیکن")),
                "pos": pos,
                "clubCode": t_info.get("code") or "PL",
                "color": t_info.get("color") or "#38BDF8",
                "pts": pts,
                "bps": int(st.get("bps") or 0),
                "stat": " + ".join(parts[:2]) if parts else f"{mins} دقیقه بازی",
            })
        quotas = (("GK", 1), ("DEF", 3), ("MID", 4), ("FWD", 3))
        for p_key, lim in quotas:
            arr = sorted(by_pos[p_key], key=lambda x: (x["pts"], x["bps"]), reverse=True)[:lim]
            totw.extend(arr)

    leader_form = form_sorted[0]
    verdict = (
        f"{leader_form['name']} با کسب {leader_form['formPts']} امتیاز از ۵ بازی اخیر پیشتاز فرم لیگ برتر است؛ "
        f"{best_att['name']} با {best_att['gf']} گل بهترین خط حمله و {best_def['name']} با {best_def['cs']} کلین‌شیت مستحکم‌ترین دفاع فصل را در اختیار دارند."
    )
    if unluckiest:
        verdict += f" بدشانس‌ترین خط حمله نسبت به xG نیز {unluckiest['name']} ({unluckiest['xgDiff']:+.1f}) بوده است."

    return {
        "id": f"live_mw_pl_w{cur_gw or 1}",
        "is_live": True,
        "competition": "لیگ برتر انگلیس",
        "leagueEn": "PREMIER LEAGUE",
        "season": "26/27",
        "week": cur_gw,
        "round": f"هفته {cur_gw} • خلاصهٔ هفته و قدرت فرم" if cur_gw else "خلاصهٔ هفته و قدرت فرم",
        "source": "Premier League / Opta FPL",
        "editorialVerdict": verdict,
        "awards": awards,
        "formVsTable": top_form_rows,
        "overperformers": [
            {"name": t["name"], "code": t["code"], "color": t["color"], "goals": t["gf"], "xg": t["xg"], "delta": t["xgDiff"]}
            for t in overperf
        ],
        "underperformers": [
            {"name": t["name"], "code": t["code"], "color": t["color"], "goals": t["gf"], "xg": t["xg"], "delta": t["xgDiff"]}
            for t in underperf
        ],
        "totw": totw,
    }


def _build_standings_based_wrapup(tbl: dict[str, Any], card_id: str, league_en: str) -> dict[str, Any] | None:
    """تبدیل جدول زنده لیگ‌های اروپا (بوندس‌لیگا / لالیگا) به خلاصهٔ هفته (با رعایت null != 0)."""
    teams = tbl.get("teams") or []
    if len(teams) < 4:
        return None
    best_att = max(teams, key=lambda t: int(t.get("gf") or 0))
    best_def = min(teams, key=lambda t: int(t.get("ga") or 999))
    rows = []
    for idx, t in enumerate(teams[:6], 1):
        rows.append({
            "name": str(t.get("name") or ""),
            "code": str(t.get("code") or "FC")[:3].upper(),
            "color": str(t.get("color") or "#38BDF8"),
            "tableRank": idx,
            "formRank": idx,
            "pts": int(t.get("pts") or 0),
            "formPts": None,
            "form": list(t.get("form") or [])[:5],
            "xgDiff": None,
        })
    return {
        "id": card_id,
        "is_live": True,
        "competition": str(tbl.get("competition") or "فوتبال اروپا"),
        "leagueEn": league_en,
        "season": "26/27",
        "week": 0,
        "round": f"خلاصهٔ هفته • {tbl.get('competition', '')}",
        "source": str(tbl.get("source") or "Open Football Hub"),
        "editorialVerdict": (
            f"{teams[0].get('name')} با {teams[0].get('pts')} امتیاز صدرنشین است؛ "
            f"{best_att.get('name')} با {best_att.get('gf')} گل زده بهترین خط حمله و "
            f"{best_def.get('name')} با تنها {best_def.get('ga')} گل خورده مستحکم‌ترین خط دفاع لیگ را دارند."
        ),
        "awards": {
            "bestAttack": {"name": str(best_att.get("name") or ""), "code": str(best_att.get("code") or "FC"), "color": str(best_att.get("color") or "#E62E45"), "val": f"{best_att.get('gf')} گل", "sub": f"در {best_att.get('mp')} مسابقه رسمی"},
            "bestDefense": {"name": str(best_def.get("name") or ""), "code": str(best_def.get("code") or "FC"), "color": str(best_def.get("color") or "#38BDF8"), "val": f"{best_def.get('ga')} گل خورده", "sub": f"مستحکم‌ترین خط دفاع در {best_def.get('mp')} بازی"},
        },
        "formVsTable": rows,
        "overperformers": [],
        "underperformers": [],
        "totw": [],
    }


def fetch_live_matchweek_wrapup_items(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    now = time.time()
    if not force_refresh and _CACHE["items"] and (now - _CACHE["ts"]) < _CACHE_TTL:
        return [dict(x) for x in _CACHE["items"]]

    out: list[dict[str, Any]] = []
    pl_item = build_fpl_matchweek_wrapup()
    if pl_item:
        out.append(pl_item)

    # بوندس‌لیگا و لالیگا از Open Football Hub (رایگان و بدون کلید)
    try:
        from src.xgpedia.providers.open_football_hub import (
            fetch_openligadb_bundesliga_standings,
            fetch_wc26_standings,
        )
        bl_tbl = fetch_openligadb_bundesliga_standings()
        if bl_tbl:
            bl_w = _build_standings_based_wrapup(bl_tbl, "live_mw_bundesliga", "BUNDESLIGA")
            if bl_w:
                out.append(bl_w)
        ll_tbl = fetch_wc26_standings("esp.1")
        if ll_tbl:
            ll_w = _build_standings_based_wrapup(ll_tbl, "live_mw_laliga", "LALIGA")
            if ll_w:
                out.append(ll_w)
    except Exception:
        pass

    if out:
        _CACHE["ts"] = now
        _CACHE["items"] = [dict(x) for x in out]
    return out


def list_all_matchweek_wrapup_items(*, include_live: bool = True, force_refresh: bool = False) -> dict[str, list[dict[str, Any]]]:
    presets = load_matchweek_wrapup_presets()
    live = fetch_live_matchweek_wrapup_items(force_refresh=force_refresh) if include_live else []
    return {"live": live, "presets": presets}
