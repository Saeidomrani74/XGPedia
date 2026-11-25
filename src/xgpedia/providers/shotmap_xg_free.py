"""پرووایدر زنده و ۱۰۰٪ رایگان «نقشهٔ شوت و مومنتوم امید گل» (`Shot-Map & xG Timeline Studio — v0.38.0`).

منبع زنده و واقعی (صرفاً فوتبال واقعی، بدون `requests`، رعایت اکید `null ≠ 0`):
  - **Understat Public Data** (`understat.com/league/{EPL|La_liga|Serie_A|Bundesliga|Ligue_1}/{season}` + `understat.com/match/{id}`):
    - استخراج لیست آخرین بازی‌های پایان‌یافته ۵ لیگ معتبر اروپا همراه با `xG` واقعی دو تیم
    - استخراج مختصات دقیق تمام شوت‌ها (`X`, `Y`, `xG`, `minute`, `result`, `situation`, `player`) در مرحلهٔ `hydrate_shotmap_xg_item` با کش دیسک
  - **پریست‌های آماده (`config/shotmap_xg_presets.json`)** فقط از دکمهٔ پریست‌ها.
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.xgpedia.config import ROOT
from src.xgpedia.providers.pl_badges_free import resolve_distinct_team_colors
from src.xgpedia.providers.players_rating_free import _resolve_club_meta

log = logging.getLogger(__name__)

PRESETS_PATH = ROOT / "config" / "shotmap_xg_presets.json"
SHOTMAP_CACHE_DIR = ROOT / "output" / ".shotmap_cache"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

_LEAGUES: list[tuple[str, str, str]] = [
    ("EPL", "لیگ برتر انگلیس", "PREMIER LEAGUE"),
    ("La_liga", "لالیگا اسپانیا", "LALIGA"),
    ("Serie_A", "سری آ ایتالیا", "SERIE A"),
    ("Bundesliga", "بوندس‌لیگا آلمان", "BUNDESLIGA"),
    ("Ligue_1", "لیگ یک فرانسه", "LIGUE 1"),
]

_LIST_CACHE: dict[str, Any] = {"ts": 0.0, "items": []}
_CACHE_TTL = 600.0


def load_shotmap_xg_presets(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or PRESETS_PATH
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        items = raw.get("presets") if isinstance(raw, dict) else raw
        return [dict(x) for x in items if isinstance(x, dict) and x.get("id")] if isinstance(items, list) else []
    except Exception as e:
        log.warning("failed to load shotmap_xg_presets.json: %s", e)
        return []


def _fa_player(name: str) -> str:
    try:
        from src.xgpedia.providers.injury_free import transliterate_player_name_fa
        return transliterate_player_name_fa(name)
    except Exception:
        return name


def _http_get_text(url: str, timeout: float = 7.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _extract_understat_var(html_txt: str, var_name: str) -> Any | None:
    m = re.search(rf"{re.escape(var_name)}\s*=\s*JSON\.parse\('([^']+)'\)", html_txt)
    if not m:
        return None
    try:
        return json.loads(m.group(1).encode("utf-8").decode("unicode_escape"))
    except Exception:
        return None


def parse_understat_shots_payload(shots_data: dict[str, Any]) -> list[dict[str, Any]]:
    """پارس ساختار استاندارد `shotsData` از Understat به لیست یکدست شوت‌ها (با نام فارسی بازیکنان)."""
    if not isinstance(shots_data, dict):
        return []
    out: list[dict[str, Any]] = []
    for side_k in ("h", "a"):
        for sh in (shots_data.get(side_k) or []):
            if not isinstance(sh, dict):
                continue
            try:
                x_v = max(0.02, min(0.99, float(sh.get("X") or 0.5)))
                y_v = max(0.02, min(0.98, float(sh.get("Y") or 0.5)))
                xg_v = max(0.0, round(float(sh.get("xG") or 0.0), 3))
                mn_v = max(1, min(98, int(sh.get("minute") or 45)))
            except (TypeError, ValueError):
                continue
            res = str(sh.get("result") or "MissedShots").strip()
            sit = str(sh.get("situation") or "OpenPlay").strip()
            pl = _fa_player(str(sh.get("player") or "بازیکن"))
            out.append({
                "team": side_k,
                "min": mn_v,
                "x": round(x_v, 3),
                "y": round(y_v, 3),
                "xg": xg_v,
                "result": res,
                "situation": sit,
                "player": pl,
            })
    out.sort(key=lambda s: (s["min"], -s["xg"]))
    return out


def _build_editorial_verdict(home: dict[str, Any], away: dict[str, Any], shots: list[dict[str, Any]]) -> str:
    hn, an = str(home.get("name") or "میزبان"), str(away.get("name") or "میهمان")
    hs, as_ = int(home.get("score") or 0), int(away.get("score") or 0)
    hxg, axg = home.get("xg"), away.get("xg")
    if hxg is None or axg is None:
        return f"تقابل {hn} ({hs}-{as_}) {an} با ثبت {len(shots)} شوت رسمی در نقشهٔ تاکتیکی XGPedia."
    hxg, axg = float(hxg), float(axg)
    diff_g = hs - as_
    diff_x = hxg - axg
    if (diff_g > 0 and diff_x < -0.35) or (diff_g < 0 and diff_x > 0.35):
        winner = hn if diff_g > 0 else an
        loser = an if diff_g > 0 else hn
        return f"سرقت آماری! {winner} با وجود امید گل کمتر برابر {loser} ({hxg:.2f} مقابل {axg:.2f} xG) به پیروزی رسید."
    if abs(diff_x) < 0.25:
        return f"نبرد نزدیک و پایاپای تاکتیکی بین {hn} ({hxg:.2f} xG) و {an} ({axg:.2f} xG) در کل ۹۰ دقیقه."
    dom = hn if diff_x > 0 else an
    return f"{dom} با خلق کیفیت موقعیت بالاتر ({hxg:.2f} مقابل {axg:.2f} xG) جریان تهاجمی مسابقه را در اختیار داشت."


def fetch_understat_match_shots(match_id: str, *, timeout: float = 7.0) -> list[dict[str, Any]]:
    """دریافت و کش محلی شوت‌های واقعی یک مسابقه از Understat (`shotsData`)."""
    mid = str(match_id or "").strip()
    if not mid:
        return []
    try:
        SHOTMAP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cf = SHOTMAP_CACHE_DIR / f"u_{mid}.json"
        if cf.exists() and cf.stat().st_size > 80:
            return json.loads(cf.read_text(encoding="utf-8"))
        html_txt = _http_get_text(f"https://understat.com/match/{mid}", timeout=timeout)
        raw_shots = _extract_understat_var(html_txt, "shotsData")
        parsed = parse_understat_shots_payload(raw_shots)
        if parsed:
            cf.write_text(json.dumps(parsed, ensure_ascii=False), encoding="utf-8")
        return parsed
    except Exception as e:
        log.warning("Understat match shots failed (%s): %s", mid, e)
        return []


def fetch_live_shotmap_xg_items(*, force_refresh: bool = False, max_items: int = 12) -> list[dict[str, Any]]:
    """فهرست آخرین مسابقات پایان‌یافته ۵ لیگ معتبر اروپا با xG واقعی از Understat."""
    now_ts = time.time()
    if not force_refresh and _LIST_CACHE["items"] and (now_ts - _LIST_CACHE["ts"]) < _CACHE_TTL:
        return [dict(x) for x in _LIST_CACHE["items"]]

    now = datetime.now(timezone.utc)
    cur_yr = now.year if now.month >= 7 else now.year - 1
    out: list[dict[str, Any]] = []

    for u_slug, lg_fa, lg_en in _LEAGUES:
        dates = None
        for yr in (cur_yr, cur_yr - 1):
            try:
                html_txt = _http_get_text(f"https://understat.com/league/{u_slug}/{yr}", timeout=6.5)
                d = _extract_understat_var(html_txt, "datesData")
                if isinstance(d, list) and any(isinstance(x, dict) and x.get("isResult") for x in d):
                    dates = d
                    break
            except Exception:
                continue
        if not dates:
            continue
        finished = [d for d in dates if isinstance(d, dict) and d.get("isResult")]
        for d in reversed(finished[-4:]):
            mid = str(d.get("id") or "").strip()
            if not mid:
                continue
            ht_raw = str((d.get("h") or {}).get("title") or "")
            at_raw = str((d.get("a") or {}).get("title") or "")
            h_fa, h_cd, h_col, _ = _resolve_club_meta(ht_raw, str((d.get("h") or {}).get("short_title") or ""))
            a_fa, a_cd, a_col, _ = _resolve_club_meta(at_raw, str((d.get("a") or {}).get("short_title") or ""))
            h_col, a_col = resolve_distinct_team_colors(h_col, a_col)
            g = d.get("goals") or {}
            xg = d.get("xG") or {}
            try:
                hs, as_ = int(g.get("h") or 0), int(g.get("a") or 0)
                hxg = round(float(xg["h"]), 2) if xg.get("h") is not None else None
                axg = round(float(xg["a"]), 2) if xg.get("a") is not None else None
            except (TypeError, ValueError):
                continue
            dt_s = str(d.get("datetime") or "")[:10]
            h_obj = {"name": h_fa, "code": h_cd, "color": h_col, "score": hs, "xg": hxg, "npxg": None}
            a_obj = {"name": a_fa, "code": a_cd, "color": a_col, "score": as_, "xg": axg, "npxg": None}
            out.append({
                "id": f"live_sm_{mid}",
                "understat_match_id": mid,
                "is_live": True,
                "competition": lg_fa,
                "leagueEn": lg_en,
                "round": f"{lg_fa} • {dt_s}",
                "date": dt_s,
                "source": "Understat Live",
                "home": h_obj,
                "away": a_obj,
                "shots": [],
                "editorialVerdict": _build_editorial_verdict(h_obj, a_obj, []),
                "_hydrated": False,
            })

    out.sort(key=lambda m: str(m.get("date") or ""), reverse=True)
    out = out[:max_items]
    if out:
        _LIST_CACHE["ts"] = now_ts
        _LIST_CACHE["items"] = [dict(x) for x in out]
    return out


def hydrate_shotmap_xg_item(item: dict[str, Any]) -> dict[str, Any]:
    """تکمیل تنبل مختصات دقیق شوت‌ها (`shotsData`) و محاسبه `npxG` پیش از رندر آفلاین."""
    out = json.loads(json.dumps(item, ensure_ascii=False))
    if out.get("shots") or not out.get("understat_match_id"):
        return out
    shots = fetch_understat_match_shots(str(out["understat_match_id"]))
    if shots:
        out["shots"] = shots
        h_s = [s for s in shots if s.get("team") == "h"]
        a_s = [s for s in shots if s.get("team") == "a"]
        out["home"]["xg"] = round(sum(float(s["xg"]) for s in h_s), 2)
        out["away"]["xg"] = round(sum(float(s["xg"]) for s in a_s), 2)
        out["home"]["npxg"] = round(sum(float(s["xg"]) for s in h_s if s.get("situation") != "Penalty"), 2)
        out["away"]["npxg"] = round(sum(float(s["xg"]) for s in a_s if s.get("situation") != "Penalty"), 2)
        out["editorialVerdict"] = _build_editorial_verdict(out["home"], out["away"], shots)
    out["_hydrated"] = True
    return out


def list_all_shotmap_xg_items(*, include_live: bool = True, force_refresh: bool = False) -> dict[str, list[dict[str, Any]]]:
    presets = load_shotmap_xg_presets()
    live = fetch_live_shotmap_xg_items(force_refresh=force_refresh) if include_live else []
    return {"live": live, "presets": presets}
