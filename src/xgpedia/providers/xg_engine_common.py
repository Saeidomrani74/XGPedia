"""موتور یکپارچهٔ دریافت xG واقعی (استاندارد Opta) و ShotMap برای همهٔ رقابت‌های فوتبال اروپا (v0.56.0).

سلسله‌مراتب منابع واقعی (بدون هیچ فرمول تقریبی یا جعلی):
  1. **SofaScore Opta API** (با `curl_cffi` Chrome TLS impersonation) — پوشش ۵۰۰+ رقابت شامل چمپیونزلیگ و ۵ لیگ اروپا.
  2. **FotMob Opta API + پارس صفحهٔ `__NEXT_DATA__`** — عبور از محدودیت هدر `x-mas` با استخراج مستقیم JSON رسمی Opta از صفحهٔ مسابقه.
  3. **SofaScore از طریق مرورگر واقعی Playwright Chromium** — پشتیبان ضد-Cloudflare روی ویندوز در یک ترد مجزا (سازگار با event loop بات تلگرام).
  4. **Understat** — xG و ShotMap واقعی برای ۵ لیگ داخلی اروپا (PL, La Liga, Serie A, Bundesliga, Ligue 1).
  5. **API-Football** (در صورت تنظیم `API_FOOTBALL_KEY` در `.env` — ۱۰۰ درخواست رایگان روزانه).

قاعدهٔ هویتی XGPedia (`null ≠ 0`): اگر هیچ منبع واقعی برای یک بازی xG نداده باشد، `None` برگردانده می‌شود و
هرگز عدد ساختگی از تعداد شوت تولید نمی‌شود.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import unicodedata
from datetime import datetime, timedelta
from typing import Any

from src.xgpedia.config import CURRENT_SEASON_START, canonical_team_name, translate_player_fa
from src.xgpedia.core import api_health

log = logging.getLogger(__name__)

_SOFA_BASE = "https://api.sofascore.com/api/v1"
_FOTMOB_BASE = "https://www.fotmob.com/api"

# کش حافظه‌ای لیست مسابقات روزانهٔ FotMob (۱۵ دقیقه) برای حذف تکرار بازکردن صفحهٔ اصلی در Playwright
_FOTMOB_DAY_CACHE_LOCK = threading.RLock()
_FOTMOB_DAY_CACHE: dict[str, tuple[float, list[tuple[str, str, str]]]] = {}
_FOTMOB_DAY_CACHE_TTL = 900.0


def clear_fotmob_day_cache() -> None:
    """پاک‌سازی کش روزانهٔ FotMob (برای تست‌های واحد یا همگام‌سازی اجباری)."""
    with _FOTMOB_DAY_CACHE_LOCK:
        _FOTMOB_DAY_CACHE.clear()


def _extract_fotmob_slug_teams(href: str) -> tuple[str, str] | None:
    """استخراج نام دو تیم از اسلاگ لینک FotMob (مثلاً `/matches/inter-vs-vfb-stuttgart/2e4xyz#123`)."""
    m = re.search(r"/matches/([^/?#]+)", str(href or ""))
    if not m:
        return None
    slug = m.group(1)
    if "-vs-" not in slug:
        return None
    left, right = slug.split("-vs-", 1)
    ht = left.replace("-", " ").strip()
    at = right.replace("-", " ").strip()
    return (ht, at) if (ht and at) else None


def _extract_fotmob_matches_from_next_data(html_text: str) -> list[tuple[str, str, str]]:
    """استخراج فهرست ساختاریافتهٔ `(home_name, away_name, page_url)` از `__NEXT_DATA__` صفحهٔ اصلی FotMob."""
    m = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html_text or "", flags=re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except Exception as _em_exc:
        from src.xgpedia.core.error_metrics import record_error as _rec_err
        _rec_err("provider.xg_engine", _em_exc)
        return []
    entries: list[tuple[str, str, str]] = []
    seen_urls: set[str] = set()

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            leagues = node.get("leagues")
            if isinstance(leagues, list):
                for lg in leagues:
                    if not isinstance(lg, dict):
                        continue
                    for mt in lg.get("matches") or []:
                        if not isinstance(mt, dict):
                            continue
                        ht = str(((mt.get("home") or {}).get("name")) or "").strip()
                        at = str(((mt.get("away") or {}).get("name")) or "").strip()
                        pu = str(mt.get("pageUrl") or "").strip()
                        if ht and at and pu and pu not in seen_urls:
                            seen_urls.add(pu)
                            entries.append((ht, at, pu))
            for v in node.values():
                if isinstance(v, (dict, list)):
                    _walk(v)
        elif isinstance(node, list):
            for it in node:
                if isinstance(it, (dict, list)):
                    _walk(it)

    _walk(data)
    return entries


def _match_fotmob_entries(
    entries: list[tuple[str, str, str]], home_en: str, away_en: str
) -> tuple[str, bool]:
    """تطبیق دو تیم روی فهرست ساختاریافتهٔ `(home, away, pageUrl)` با تشخیص دقیق جابه‌جایی میزبان/میهمان."""
    for ht, at, pu in entries:
        if _teams_match(home_en, ht) and _teams_match(away_en, at):
            return pu, False
        if _teams_match(home_en, at) and _teams_match(away_en, ht):
            return pu, True
    return "", False


def _strip_accents_lower(text: str) -> str:
    tr = str.maketrans({"ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D", "ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE"})
    s = unicodedata.normalize("NFKD", str(text or "").translate(tr))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\b(?:fc|fk|cf|sc|ac|sk|bk|nk|pfk|afc|cfc|ssc|ud|cd|rcd|ca|us|as|ogc|rc|sv|vfl|vfb|tsg|fsv|rb|losc|club|de)\b", " ", s.lower())
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def _teams_match(name_a: str, name_b: str) -> bool:
    """تطبیق هوشمند نام تیم‌ها بین ESPN/FDO و SofaScore/FotMob (با حذف اعراب و پسوندها)."""
    if not (name_a and name_b):
        return False
    ca = _strip_accents_lower(canonical_team_name(name_a))
    cb = _strip_accents_lower(canonical_team_name(name_b))
    ra = _strip_accents_lower(name_a)
    rb = _strip_accents_lower(name_b)
    if ca and cb and (ca == cb or ca in cb or cb in ca):
        return True
    if ra and rb and (ra == rb or ra in rb or rb in ra):
        return True
    ta = {t for t in (ca + " " + ra).split() if len(t) >= 3}
    tb = {t for t in (cb + " " + rb).split() if len(t) >= 3}
    if not (ta and tb):
        return False
    common = ta & tb
    generic = {"madrid", "milan", "united", "city", "real", "sporting", "inter", "athletic", "olympique", "stade", "dinamo"}
    strong = common - generic
    return bool(strong) or (len(common) >= 2)


def _http_get_text(url: str, *, headers: dict[str, str] | None = None, timeout: float = 10.0) -> tuple[int, str]:
    """درخواست GET با اولویت `curl_cffi` (Chrome TLS) و پشتیبان `httpx`؛ خروجی: (status_code, text)."""
    hdrs = {
        "Accept": "application/json, text/html, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        **(headers or {}),
    }
    try:
        from curl_cffi import requests as cffi_req  # type: ignore

        for imp in ("chrome131", "chrome124", "chrome120"):
            try:
                r = cffi_req.get(url, headers=hdrs, impersonate=imp, timeout=timeout)
                if r.status_code == 200:
                    return 200, r.text
                if r.status_code in (403, 429):
                    continue
                return r.status_code, r.text
            except Exception as _em_exc:
                from src.xgpedia.core.error_metrics import record_error as _rec_err
                _rec_err("provider.xg_engine", _em_exc)
                continue
    except ImportError:
        pass

    try:
        import httpx

        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            r = client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Safari/537.36", **hdrs},
            )
            return r.status_code, r.text
    except Exception as e:
        log.debug("xg_engine http error for %s: %s", url, e)
        return 0, ""


def _http_get_json(url: str, *, headers: dict[str, str] | None = None, timeout: float = 10.0) -> Any | None:
    code, txt = _http_get_text(url, headers=headers, timeout=timeout)
    if code != 200 or not txt:
        if code:
            log.debug("xg_engine HTTP %s for %s", code, url)
        return None
    try:
        return json.loads(txt)
    except Exception as _em_exc:
        from src.xgpedia.core.error_metrics import record_error as _rec_err
        _rec_err("provider.xg_engine", _em_exc)
        return None


def _to_float(val: Any) -> float | None:
    if val is None or isinstance(val, bool):
        return None
    try:
        return round(float(str(val).replace("%", "").strip()), 2)
    except (TypeError, ValueError):
        return None


def _date_candidates(match_date: str) -> list[str]:
    dates = [match_date[:10]]
    try:
        dt = datetime.strptime(match_date[:10], "%Y-%m-%d")
        dates.append((dt - timedelta(days=1)).strftime("%Y-%m-%d"))
        dates.append((dt + timedelta(days=1)).strftime("%Y-%m-%d"))
    except Exception as _em_exc:
        from src.xgpedia.core.error_metrics import record_error as _rec_err
        _rec_err("provider.xg_engine", _em_exc)
    return dates


# ─── ۱) SofaScore Opta xG & ShotMap ──────────────────────────────────────────

def parse_sofascore_statistics(payload: dict[str, Any]) -> dict[str, Any]:
    """استخراج xG واقعی Opta، موقعیت‌های بزرگ، شوت، مالکیت و کرنر از `/event/{id}/statistics`."""
    stats_groups = payload.get("statistics") if isinstance(payload, dict) else None
    if not isinstance(stats_groups, list):
        return {}
    all_period = next((p for p in stats_groups if str(p.get("period") or "").upper() == "ALL"), None)
    if not all_period and stats_groups:
        all_period = stats_groups[0]
    if not isinstance(all_period, dict):
        return {}

    out: dict[str, Any] = {}
    for grp in all_period.get("groups") or []:
        for item in grp.get("statisticsItems") or []:
            key = str(item.get("key") or "").strip().lower()
            name = str(item.get("name") or "").strip().lower()
            hv = _to_float(item.get("homeValue") if item.get("homeValue") is not None else item.get("home"))
            av = _to_float(item.get("awayValue") if item.get("awayValue") is not None else item.get("away"))
            if key == "expectedgoals" or name == "expected goals":
                if hv is not None and av is not None:
                    out["home_xg"] = hv
                    out["away_xg"] = av
            elif key in ("bigchancecreated", "bigchances") or name == "big chances":
                if hv is not None and av is not None:
                    out["home_big_chances"] = int(round(hv))
                    out["away_big_chances"] = int(round(av))
            elif key == "totalshotsinsidebox" or name == "shots inside box":
                if hv is not None and av is not None:
                    out["home_inside_box"] = int(round(hv))
                    out["away_inside_box"] = int(round(av))
            elif key == "goalsprevented" or name == "goals prevented":
                if hv is not None and av is not None:
                    out["home_goals_prevented"] = hv
                    out["away_goals_prevented"] = av
            elif key == "ballpossession" or name == "ball possession":
                if hv is not None and av is not None:
                    out["home_possession"] = hv
                    out["away_possession"] = av
            elif key == "totalshotsongoal" or name == "total shots":
                if hv is not None and av is not None:
                    out["home_total_shots"] = hv
                    out["away_total_shots"] = av
            elif key == "shotsongoal" or name == "shots on target":
                if hv is not None and av is not None:
                    out["home_shots_on_target"] = hv
                    out["away_shots_on_target"] = av
            elif key == "cornerkicks" or name == "corner kicks":
                if hv is not None and av is not None:
                    out["home_corners"] = hv
                    out["away_corners"] = av
    return out


def parse_sofascore_shotmap(payload: dict[str, Any]) -> tuple[list[list[Any]], list[list[Any]]]:
    """تبدیل shotmap سوفااسکور به فرمت استاندارد کارت XGPedia: `[x, y, xg, outcome, player_fa, minute]`."""
    shots = payload.get("shotmap") if isinstance(payload, dict) else None
    if not isinstance(shots, list):
        return [], []
    h_list: list[list[Any]] = []
    a_list: list[list[Any]] = []
    for sh in shots:
        if not isinstance(sh, dict):
            continue
        xg = _to_float(sh.get("xg"))
        if xg is None:
            continue
        coords = sh.get("playerCoordinates") or {}
        rx = _to_float(coords.get("x"))
        ry = _to_float(coords.get("y"))
        x_norm = round(max(0.0, min(100.0, 100.0 - rx)), 1) if rx is not None else 88.0
        y_norm = round(max(0.0, min(100.0, ry)), 1) if ry is not None else 50.0
        stype = str(sh.get("shotType") or "").lower()
        outcome = "goal" if stype == "goal" else ("sot" if stype in ("save", "post") else "miss")
        p_raw = str((sh.get("player") or {}).get("shortName") or (sh.get("player") or {}).get("name") or "")
        p_fa = translate_player_fa(p_raw) if p_raw else ""
        minute = int(sh.get("time") or 0)
        entry = [x_norm, y_norm, round(xg, 3), outcome, p_fa, minute]
        if sh.get("isHome"):
            h_list.append(entry)
        else:
            a_list.append(entry)
    h_list.sort(key=lambda r: r[5])
    a_list.sort(key=lambda r: r[5])
    return h_list, a_list


def _swap_parsed(parsed: dict[str, Any]) -> None:
    for hk, ak in (
        ("home_xg", "away_xg"),
        ("home_big_chances", "away_big_chances"),
        ("home_inside_box", "away_inside_box"),
        ("home_possession", "away_possession"),
        ("home_total_shots", "away_total_shots"),
        ("home_shots_on_target", "away_shots_on_target"),
        ("home_corners", "away_corners"),
        ("home_shots", "away_shots"),
        ("home_gk", "away_gk"),
    ):
        if hk in parsed and ak in parsed:
            parsed[hk], parsed[ak] = parsed[ak], parsed[hk]
    if isinstance(parsed.get("momentum"), list):
        parsed["momentum"] = [round(-float(v), 2) for v in parsed["momentum"]]
    if isinstance(parsed.get("top_players"), list):
        for tp in parsed["top_players"]:
            if isinstance(tp, dict) and tp.get("side") in ("home", "away"):
                tp["side"] = "away" if tp["side"] == "home" else "home"
    if isinstance(parsed.get("motm"), dict):
        m = parsed["motm"]
        if m.get("side") in ("home", "away"):
            m["side"] = "away" if m["side"] == "home" else "home"
        ru = m.get("runnerUp")
        if isinstance(ru, dict) and ru.get("side") in ("home", "away"):
            ru["side"] = "away" if ru["side"] == "home" else "home"
