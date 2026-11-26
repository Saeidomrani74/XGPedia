"""پرووایدر ۱۰۰٪ رایگان داده‌های زندهٔ سری آ ایتالیا (`ita.1` — Serie A) — بدون `requests`.

منابع رایگان و بدون کلید (با ثبت خودکار در موتور یادگیری `APIHealthRouter`):
  - جدول ۲۰تیمی سری آ: `site.api.espn.com/apis/v2/sports/soccer/ita.1/standings`
  - برنامه و نتایج زندهٔ سری آ: `site.api.espn.com/apis/site/v2/sports/soccer/ita.1/scoreboard`
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
from typing import Any

from src.xgpedia.core import api_health

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
_SA_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 300.0


def _espn_get_json(url: str, health_key: str, *, force_refresh: bool = False, timeout: float = 6.5) -> dict[str, Any] | None:
    now = time.time()
    if not force_refresh and url in _SA_CACHE and (now - _SA_CACHE[url][0]) < _CACHE_TTL:
        return _SA_CACHE[url][1]
    if api_health.is_cooling(health_key):
        return None
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read(900_000).decode("utf-8", errors="replace"))
        api_health.record_success(health_key, (time.perf_counter() - t0) * 1000.0)
        _SA_CACHE[url] = (now, data)
        return data
    except Exception as e:
        api_health.record_failure(health_key, f"{type(e).__name__}: {e}", base_cooldown=120.0)
        log.warning("SerieA ESPN fetch failed (%s): %s", health_key, e)
        return None


def _resolve_seriea_club(name_en: str, tla: str = "") -> tuple[str, str, str]:
    from src.xgpedia.providers.ucl_badges_free import lookup_ucl_club
    info = lookup_ucl_club(name_en, tla_hint=tla)
    if info:
        return str(info[0]), str(info[1]), str(info[2])
    return name_en, (tla or name_en[:3]).upper()[:3], "#38BDF8"


def fetch_seriea_standings(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    """دریافت جدول زندهٔ سری آ ایتالیا با نام فارسی، کد ۳حرفی، رنگ و آمار کامل."""
    url = "https://site.api.espn.com/apis/v2/sports/soccer/ita.1/standings"
    data = _espn_get_json(url, "seriea:standings", force_refresh=force_refresh)
    if not isinstance(data, dict):
        return []
    entries = []
    for ch in (data.get("children") or [data]):
        st = (ch.get("standings") or {}).get("entries") or []
        if st:
            entries = st
            break
    rows: list[dict[str, Any]] = []
    for idx, ent in enumerate(entries, 1):
        team = ent.get("team") or {}
        nm_en = str(team.get("displayName") or team.get("name") or "")
        tla_raw = str(team.get("abbreviation") or "")
        nm_fa, code, col = _resolve_seriea_club(nm_en, tla_raw)
        stats_map = {str(s.get("name") or ""): s.get("value") for s in (ent.get("stats") or []) if isinstance(s, dict)}
        pts = int(stats_map.get("points") or 0)
        mp = int(stats_map.get("gamesPlayed") or 0)
        won = int(stats_map.get("wins") or 0)
        drw = int(stats_map.get("ties") or 0)
        lst = int(stats_map.get("losses") or 0)
        gf = int(stats_map.get("pointsFor") or 0)
        ga = int(stats_map.get("pointsAgainst") or 0)
        gd = int(stats_map.get("pointDifferential") or (gf - ga))
        rank = int(stats_map.get("rank") or idx)
        rows.append({
            "rank": rank,
            "name": nm_fa,
            "name_en": nm_en,
            "code": code,
            "color": col,
            "played": mp,
            "won": won,
            "drawn": drw,
            "lost": lst,
            "gf": gf,
            "ga": ga,
            "gd": gd,
            "points": pts,
        })
    rows.sort(key=lambda r: (r["rank"], -r["points"], -r["gd"]))
    return rows


def fetch_seriea_scoreboard(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    """دریافت مسابقات زنده، اخیر و پیش‌رو سری آ ایتالیا از ESPN."""
    url = "https://site.api.espn.com/apis/site/v2/sports/soccer/ita.1/scoreboard"
    data = _espn_get_json(url, "seriea:scoreboard", force_refresh=force_refresh)
    if not isinstance(data, dict):
        return []
    matches: list[dict[str, Any]] = []
    for ev in (data.get("events") or []):
        comps = ev.get("competitions") or []
        if not comps:
            continue
        c0 = comps[0]
        competitors = c0.get("competitors") or []
        h_raw = next((x for x in competitors if x.get("homeAway") == "home"), None)
        a_raw = next((x for x in competitors if x.get("homeAway") == "away"), None)
        if not h_raw or not a_raw:
            continue
        ht = h_raw.get("team") or {}
        at = a_raw.get("team") or {}
        h_fa, h_cd, h_col = _resolve_seriea_club(str(ht.get("displayName") or ""), str(ht.get("abbreviation") or ""))
        a_fa, a_cd, a_col = _resolve_seriea_club(str(at.get("displayName") or ""), str(at.get("abbreviation") or ""))
        st_type = ((ev.get("status") or {}).get("type") or {})
        matches.append({
            "id": str(ev.get("id") or f"{h_cd}_{a_cd}"),
            "date": str(ev.get("date") or ""),
            "completed": bool(st_type.get("completed")),
            "status_desc": str(st_type.get("shortDetail") or st_type.get("description") or ""),
            "home": {"name": h_fa, "name_en": str(ht.get("displayName") or ""), "code": h_cd, "color": h_col, "score": int(h_raw.get("score") or 0)},
            "away": {"name": a_fa, "name_en": str(at.get("displayName") or ""), "code": a_cd, "color": a_col, "score": int(a_raw.get("score") or 0)},
        })
    return matches


def build_seriea_matchweek_wrapup(*, force_refresh: bool = False) -> dict[str, Any] | None:
    """ساخت نسخهٔ زندهٔ «خلاصهٔ هفته سری آ ایتالیا» برای کارت matchweek_wrapup."""
    rows = fetch_seriea_standings(force_refresh=force_refresh)
    if len(rows) < 6:
        return None
    top_att = max(rows, key=lambda r: (r["gf"], r["gd"]))
    top_def = min(rows, key=lambda r: (r["ga"], -r["points"]))
    leader = rows[0]
    form_rows = []
    for r in rows[:10]:
        mp = max(1, r["played"])
        ppg = round(r["points"] / mp, 2)
        form_rows.append({
            "rank": r["rank"],
            "name": r["name"],
            "code": r["code"],
            "color": r["color"],
            "points": r["points"],
            "played": r["played"],
            "gd": r["gd"],
            "gf": r["gf"],
            "ga": r["ga"],
            "form_pts": min(15, round(ppg * 5)),
            "ppg": ppg,
            "form_delta": 0,
        })
    return {
        "id": "live_mw_seriea",
        "is_live": True,
        "competition": "سری آ ایتالیا",
        "round": "خلاصهٔ هفتهٔ سری آ ایتالیا",
        "source": "ESPN Serie A / XGPedia",
        "editorialVerdict": (
            f"{leader['name']} با {leader['points']} امتیاز صدرنشین سری آ است؛ "
            f"{top_att['name']} با {top_att['gf']} گل زده زهردارترین حمله و {top_def['name']} با تنها {top_def['ga']} گل خورده بهترین خط دفاعی ایتالیا را در اختیار دارند."
        ),
        "bestAttack": {"team": top_att["name"], "code": top_att["code"], "val": f"{top_att['gf']} گل", "sub": f"در {top_att['played']} بازی"},
        "bestDefense": {"team": top_def["name"], "code": top_def["code"], "val": f"{top_def['ga']} گل خورده", "sub": f"تفاضل {top_def['gd']:+d}"},
        "rows": form_rows,
    }
