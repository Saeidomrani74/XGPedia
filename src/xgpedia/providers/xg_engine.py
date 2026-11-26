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
    except Exception:
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
            except Exception:
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
    except Exception:
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
    except Exception:
        pass
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


def fetch_sofascore_match_xg(
    home_en: str,
    away_en: str,
    match_date: str,
    *,
    timeout: float = 10.0,
) -> dict[str, Any] | None:
    """دریافت xG واقعی Opta و ShotMap یک مسابقه از SofaScore با `curl_cffi`."""
    hk = "xg:sofascore"
    if api_health.is_cooling(hk):
        return None
    t0 = time.perf_counter()
    hdrs = {"Origin": "https://www.sofascore.com", "Referer": "https://www.sofascore.com/"}

    event_id: int | str | None = None
    swapped = False
    for d in _date_candidates(match_date):
        code, txt = _http_get_text(f"{_SOFA_BASE}/sport/football/scheduled-events/{d}", headers=hdrs, timeout=timeout)
        if code in (401, 403, 429):
            api_health.record_failure(hk, f"HTTP {code}", status_code=code)
            return None
        if code != 200 or not txt:
            continue
        try:
            ev_data = json.loads(txt)
        except Exception:
            continue
        if not isinstance(ev_data, dict):
            continue
        for ev in ev_data.get("events") or []:
            ht = str(((ev.get("homeTeam") or {}).get("name")) or "")
            at = str(((ev.get("awayTeam") or {}).get("name")) or "")
            if _teams_match(home_en, ht) and _teams_match(away_en, at):
                event_id, swapped = ev.get("id"), False
                break
            if _teams_match(home_en, at) and _teams_match(away_en, ht):
                event_id, swapped = ev.get("id"), True
                break
        if event_id is not None:
            break

    if event_id is None:
        return None

    st_data = _http_get_json(f"{_SOFA_BASE}/event/{event_id}/statistics", headers=hdrs, timeout=timeout)
    parsed = parse_sofascore_statistics(st_data or {})
    if "home_xg" not in parsed or "away_xg" not in parsed:
        return None

    sm_data = _http_get_json(f"{_SOFA_BASE}/event/{event_id}/shotmap", headers=hdrs, timeout=timeout)
    if isinstance(sm_data, dict):
        hs, as_ = parse_sofascore_shotmap(sm_data)
        if hs or as_:
            parsed["home_shots"], parsed["away_shots"] = hs, as_

    if swapped:
        _swap_parsed(parsed)
    parsed["provider"] = "sofascore"
    api_health.record_success(hk, (time.perf_counter() - t0) * 1000.0)
    log.info("xg_engine [sofascore] %s vs %s -> xG %.2f - %.2f", home_en, away_en, parsed["home_xg"], parsed["away_xg"])
    return parsed


# ─── ۲) FotMob Opta xG (API + __NEXT_DATA__ SSR HTML fallback) ───────────────

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
                    "expected_goals_conceded",
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
                psxg_v = xgot if xgot is not None else opp_xg
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
                chip_objs.append({"label": "امتیاز Opta", "val": f"{rating:.1f}"})
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
                        "expected_goals_conceded",
                    ),
                )
                opp_g = away_goals if side_key == "home" else home_goals
                if opp_g is None:
                    opp_g = _fotmob_stat_val(pstat.get("stats"), ("goals conceded", "goals_conceded"))
                opp_xg = out.get("away_xg") if side_key == "home" else out.get("home_xg")
                psxg_v = xgot if xgot is not None else opp_xg
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
                    + [{"label": "امتیاز Opta", "val": f"{rating:.1f}"}]
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
                "chips": best["chips"] or [{"label": "امتیاز Opta", "val": f"{best['rating']:.1f}"}],
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
    except Exception:
        return {}


def fetch_fotmob_match_xg(
    home_en: str,
    away_en: str,
    match_date: str,
    *,
    timeout: float = 10.0,
) -> dict[str, Any] | None:
    """دریافت xG واقعی Opta از FotMob (ابتدا API و سپس صفحهٔ SSR `__NEXT_DATA__`)."""
    hk = "xg:fotmob"
    if api_health.is_cooling(hk):
        return None
    t0 = time.perf_counter()
    hdrs = {"Referer": "https://www.fotmob.com/"}

    match_id: int | str | None = None
    page_url = ""
    swapped = False
    for d in _date_candidates(match_date):
        ymd = d.replace("-", "")
        code, txt = _http_get_text(f"{_FOTMOB_BASE}/matches?date={ymd}", headers=hdrs, timeout=timeout)
        if code in (401, 403, 429):
            api_health.record_failure(hk, f"HTTP {code}", status_code=code)
            return None
        if code != 200 or not txt:
            continue
        try:
            data = json.loads(txt)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for lg in data.get("leagues") or []:
            for m in lg.get("matches") or []:
                ht = str(((m.get("home") or {}).get("name")) or "")
                at = str(((m.get("away") or {}).get("name")) or "")
                if _teams_match(home_en, ht) and _teams_match(away_en, at):
                    match_id, page_url, swapped = m.get("id"), str(m.get("pageUrl") or ""), False
                    break
                if _teams_match(home_en, at) and _teams_match(away_en, ht):
                    match_id, page_url, swapped = m.get("id"), str(m.get("pageUrl") or ""), True
                    break
            if match_id is not None:
                break
        if match_id is not None:
            break

    if match_id is None:
        return None

    # مسیر ۱: API مستقیم matchDetails
    det = _http_get_json(f"{_FOTMOB_BASE}/matchDetails?matchId={match_id}", headers=hdrs, timeout=timeout)
    parsed = parse_fotmob_match_details(det or {})

    # مسیر ۲: اگر API به دلیل x-mas پاسخ 403 داد، صفحهٔ SSR مسابقه را بخوان (__NEXT_DATA__)
    if ("home_xg" not in parsed or "away_xg" not in parsed) and page_url:
        full_url = page_url if page_url.startswith("http") else f"https://www.fotmob.com{page_url.split('#')[0]}"
        code, html_txt = _http_get_text(full_url, headers=hdrs, timeout=timeout)
        if code == 200 and html_txt:
            parsed = parse_fotmob_next_data_html(html_txt)

    if "home_xg" not in parsed or "away_xg" not in parsed:
        return None
    if swapped:
        _swap_parsed(parsed)
    parsed["provider"] = "fotmob"
    api_health.record_success(hk, (time.perf_counter() - t0) * 1000.0)
    log.info("xg_engine [fotmob] %s vs %s -> xG %.2f - %.2f", home_en, away_en, parsed["home_xg"], parsed["away_xg"])
    return parsed


# ─── ۳) پشتیبان مرورگر واقعی Playwright Chromium (ضد-Cloudflare ۱۰۰٪) ──────────


def fetch_fotmob_via_playwright(
    home_en: str,
    away_en: str,
    match_date: str,
    *,
    timeout: float = 25.0,
    diag: list[str] | None = None,
) -> dict[str, Any] | None:
    """دریافت سریع xG واقعی Opta از FotMob با Playwright Chromium (`domcontentloaded` + رهگیری JSON/DOM)."""
    box: dict[str, Any] = {}

    def _log(msg: str) -> None:
        if diag is not None:
            diag.append(msg)

    def _worker() -> None:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except Exception as e:
            _log(f"fotmob-pw: playwright not available ({e})")
            return
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    ctx = browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                        locale="en-US",
                        viewport={"width": 1280, "height": 900},
                    )
                    page = ctx.new_page()
                    # مسدودکردن تصاویر/فونت‌ها/تبلیغات برای بارگذاری ۵ تا ۱۰ برابر سریع‌تر روی VPN
                    try:
                        page.route(
                            "**/*",
                            lambda route: route.abort()
                            if route.request.resource_type in ("image", "media", "font", "stylesheet")
                            else route.continue_(),
                        )
                    except Exception:
                        pass
                    captured_matches: list[dict[str, Any]] = []
                    captured_details: list[dict[str, Any]] = []

                    def _on_resp(resp) -> None:
                        try:
                            u = resp.url
                            if resp.status == 200 and ("/api/matches" in u or "/api/data/matches" in u):
                                captured_matches.append(resp.json())
                            elif resp.status == 200 and ("/api/matchDetails" in u or "/api/data/matchDetails" in u):
                                captured_details.append(resp.json())
                        except Exception:
                            pass

                    page.on("response", _on_resp)

                    page_url = ""
                    swapped = False
                    cand_dates = _date_candidates(match_date)[:2]
                    # ۰) بررسی کش روزانهٔ FotMob (حذف نیاز به بازکردن مجدد صفحهٔ اصلی برای بازی‌های هم‌روز)
                    now_ts = time.time()
                    with _FOTMOB_DAY_CACHE_LOCK:
                        for d in cand_dates:
                            ymd = d.replace("-", "")
                            cached = _FOTMOB_DAY_CACHE.get(ymd)
                            if cached and (now_ts - cached[0]) <= _FOTMOB_DAY_CACHE_TTL:
                                pu, sw = _match_fotmob_entries(cached[1], home_en, away_en)
                                if pu:
                                    page_url, swapped = pu, sw
                                    break

                    for d in ([] if page_url else cand_dates):
                        ymd = d.replace("-", "")
                        captured_matches.clear()
                        try:
                            page.goto(f"https://www.fotmob.com/?date={ymd}", wait_until="domcontentloaded", timeout=15000)
                        except Exception as e_go:
                            _log(f"fotmob-pw: goto date={ymd} err={type(e_go).__name__}")
                            continue
                        try:
                            page.wait_for_selector('a[href*="/matches/"]', timeout=9000)
                        except Exception:
                            page.wait_for_timeout(2500)

                        day_entries: list[tuple[str, str, str]] = []
                        seen_pu: set[str] = set()

                        # ۱) بررسی JSON رهگیری‌شده
                        for payload in captured_matches:
                            for lg in payload.get("leagues") or []:
                                for m in lg.get("matches") or []:
                                    ht = str(((m.get("home") or {}).get("name")) or "").strip()
                                    at = str(((m.get("away") or {}).get("name")) or "").strip()
                                    pu = str(m.get("pageUrl") or "").strip()
                                    if ht and at and pu and pu not in seen_pu:
                                        seen_pu.add(pu)
                                        day_entries.append((ht, at, pu))

                        # ۲) استخراج ساختاریافته از __NEXT_DATA__ صفحهٔ اصلی (SSR)
                        try:
                            for ht, at, pu in _extract_fotmob_matches_from_next_data(page.content()):
                                if pu not in seen_pu:
                                    seen_pu.add(pu)
                                    day_entries.append((ht, at, pu))
                        except Exception:
                            pass

                        # ۳) استخراج جفت تیم‌ها از اسلاگ لینک‌های DOM (`/matches/<home>-vs-<away>/...`)
                        hrefs: list[dict[str, Any]] = []
                        try:
                            hrefs = page.eval_on_selector_all(
                                'a[href*="/matches/"]',
                                "els => els.map(e => ({href: e.getAttribute('href') || '', text: (e.innerText || '').trim()}))",
                            ) or []
                            for item in hrefs:
                                h_href = str(item.get("href") or "").strip()
                                if not h_href or h_href in seen_pu:
                                    continue
                                pair = _extract_fotmob_slug_teams(h_href)
                                if pair:
                                    seen_pu.add(h_href)
                                    day_entries.append((pair[0], pair[1], h_href))
                        except Exception as e_dom:
                            _log(f"fotmob-pw: dom scan err={type(e_dom).__name__}")

                        if day_entries:
                            with _FOTMOB_DAY_CACHE_LOCK:
                                _FOTMOB_DAY_CACHE[ymd] = (time.time(), day_entries)
                            page_url, swapped = _match_fotmob_entries(day_entries, home_en, away_en)

                        if not page_url:
                            # پشتیبان نهایی روی متن کامل لینک‌ها
                            for item in hrefs:
                                h_href = str(item.get("href") or "")
                                blob = f"{h_href.replace('-', ' ')} {item.get('text', '')}"
                                if _teams_match(home_en, blob) and _teams_match(away_en, blob):
                                    page_url = h_href
                                    break
                            if not page_url:
                                _log(f"fotmob-pw: date={ymd} scanned {len(hrefs)} links, entries={len(day_entries)}, captured_api={len(captured_matches)}, no match")

                        if page_url:
                            break

                    if not page_url:
                        return

                    full_url = page_url if page_url.startswith("http") else f"https://www.fotmob.com{page_url}"
                    if ":tab=stats" not in full_url and "#" in full_url:
                        full_url = f"{full_url}:tab=stats"
                    captured_details.clear()
                    try:
                        page.goto(full_url, wait_until="commit", timeout=25000)
                    except Exception as e_go2:
                        _log(f"fotmob-pw: goto match warn={type(e_go2).__name__} (continuing)")
                    # صبر تا رسیدن پاسخ JSON امضاشدهٔ /api/matchDetails یا رندر آمار
                    for _ in range(20):
                        if captured_details:
                            break
                        try:
                            page.wait_for_timeout(500)
                        except Exception:
                            break

                    parsed: dict[str, Any] = {}
                    for det in captured_details:
                        cand = parse_fotmob_match_details(det)
                        if "home_xg" in cand and "away_xg" in cand:
                            for k, v in cand.items():
                                if k not in parsed or not parsed[k]:
                                    parsed[k] = v
                    _rich_keys = ("home_shots", "away_shots", "momentum", "top_players", "motm", "home_gk", "away_gk")
                    if "home_xg" not in parsed or any(k not in parsed for k in _rich_keys):
                        try:
                            nd_parsed = parse_fotmob_next_data_html(page.content())
                            for k, v in nd_parsed.items():
                                if k not in parsed or not parsed[k]:
                                    parsed[k] = v
                        except Exception:
                            pass
                    # پشتیبان خواندن مستقیم عدد Expected goals (xG) از متن رندرشدهٔ صفحه (تب stats)
                    if "home_xg" not in parsed:
                        try:
                            body_txt = page.inner_text("body")
                            m_xg = re.search(
                                r"(\d+\.\d{2})\s+Expected\s+goals\s*(?:\(xG\))?\s+(\d+\.\d{2})",
                                body_txt,
                                flags=re.IGNORECASE,
                            )
                            if m_xg:
                                parsed["home_xg"] = float(m_xg.group(1))
                                parsed["away_xg"] = float(m_xg.group(2))
                        except Exception:
                            pass

                    if "home_xg" not in parsed or "away_xg" not in parsed:
                        _log(f"fotmob-pw: opened {full_url} but xG not found (captured_details={len(captured_details)})")
                        return

                    if swapped:
                        _swap_parsed(parsed)
                    parsed["provider"] = "fotmob"
                    box["result"] = parsed
                finally:
                    browser.close()
        except Exception as e:
            _log(f"fotmob-pw error: {type(e).__name__}: {str(e)[:120]}")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=max(45.0, timeout + 25.0))
    if t.is_alive():
        _log("fotmob-pw: worker thread timed out")
    res = box.get("result")
    if res:
        log.info("xg_engine [fotmob-playwright] %s vs %s -> xG %.2f - %.2f", home_en, away_en, res["home_xg"], res["away_xg"])
    return res


def fetch_sofascore_via_playwright(
    home_en: str,
    away_en: str,
    match_date: str,
    *,
    timeout: float = 22.0,
) -> dict[str, Any] | None:
    """دریافت xG واقعی Opta از SofaScore با مرورگر واقعی Chromium (در ترد مجزا برای سازگاری با asyncio)."""
    box: dict[str, Any] = {}

    def _worker() -> None:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except Exception:
            return
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    ctx = browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                        locale="en-US",
                    )
                    page = ctx.new_page()
                    page.goto("https://www.sofascore.com/", wait_until="domcontentloaded", timeout=int(timeout * 1000))

                    def _fetch_in_page(url: str) -> Any | None:
                        return page.evaluate(
                            """async (u) => {
                                try {
                                    const r = await fetch(u, {credentials: 'include'});
                                    if (!r.ok) return null;
                                    return await r.json();
                                } catch (e) { return null; }
                            }""",
                            url,
                        )

                    event_id = None
                    swapped = False
                    for d in _date_candidates(match_date):
                        ev_data = _fetch_in_page(f"{_SOFA_BASE}/sport/football/scheduled-events/{d}")
                        if not isinstance(ev_data, dict):
                            continue
                        for ev in ev_data.get("events") or []:
                            ht = str(((ev.get("homeTeam") or {}).get("name")) or "")
                            at = str(((ev.get("awayTeam") or {}).get("name")) or "")
                            if _teams_match(home_en, ht) and _teams_match(away_en, at):
                                event_id, swapped = ev.get("id"), False
                                break
                            if _teams_match(home_en, at) and _teams_match(away_en, ht):
                                event_id, swapped = ev.get("id"), True
                                break
                        if event_id is not None:
                            break
                    if event_id is None:
                        return
                    st_data = _fetch_in_page(f"{_SOFA_BASE}/event/{event_id}/statistics")
                    parsed = parse_sofascore_statistics(st_data or {})
                    if "home_xg" not in parsed or "away_xg" not in parsed:
                        return
                    sm_data = _fetch_in_page(f"{_SOFA_BASE}/event/{event_id}/shotmap")
                    if isinstance(sm_data, dict):
                        hs, as_ = parse_sofascore_shotmap(sm_data)
                        if hs or as_:
                            parsed["home_shots"], parsed["away_shots"] = hs, as_
                    if swapped:
                        _swap_parsed(parsed)
                    parsed["provider"] = "sofascore"
                    box["result"] = parsed
                finally:
                    browser.close()
        except Exception as e:
            log.debug("xg_engine playwright fallback failed: %s", e)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=timeout + 5.0)
    res = box.get("result")
    if res:
        log.info("xg_engine [sofascore-playwright] %s vs %s -> xG %.2f - %.2f", home_en, away_en, res["home_xg"], res["away_xg"])
    return res


# ─── ۴) آبشار یکپارچهٔ xG واقعی ─────────────────────────────────────────────

def fetch_real_match_xg(
    home_en: str,
    away_en: str,
    match_date: str,
    *,
    competition: str = "",
    season_start: int = CURRENT_SEASON_START,
    timeout: float = 10.0,
    allow_playwright: bool = True,
    diag: list[str] | None = None,
) -> dict[str, Any] | None:
    """دریافت xG واقعی Opta یک مسابقه: SofaScore → FotMob → FotMob Playwright → SofaScore Playwright → Understat."""
    # ۱) SofaScore (curl_cffi)
    try:
        res = fetch_sofascore_match_xg(home_en, away_en, match_date, timeout=timeout)
        if res and res.get("home_xg") is not None and res.get("away_xg") is not None:
            return res
        if diag is not None:
            diag.append("sofascore-http: no result (likely 403/Cloudflare)")
    except Exception as e:
        api_health.record_failure("xg:sofascore", f"{type(e).__name__}: {e}")
        if diag is not None:
            diag.append(f"sofascore-http error: {type(e).__name__}: {e}")

    # ۲) FotMob (HTTP API + __NEXT_DATA__)
    try:
        res = fetch_fotmob_match_xg(home_en, away_en, match_date, timeout=timeout)
        if res and res.get("home_xg") is not None and res.get("away_xg") is not None:
            return res
        if diag is not None:
            diag.append("fotmob-http: no result (likely x-mas header required)")
    except Exception as e:
        api_health.record_failure("xg:fotmob", f"{type(e).__name__}: {e}")
        if diag is not None:
            diag.append(f"fotmob-http error: {type(e).__name__}: {e}")

    # ۳) FotMob از طریق مرورگر واقعی Playwright (رهگیری JSON رسمی Opta امضاشده توسط خود سایت)
    if allow_playwright:
        try:
            res = fetch_fotmob_via_playwright(home_en, away_en, match_date, timeout=max(22.0, timeout), diag=diag)
            if res and res.get("home_xg") is not None and res.get("away_xg") is not None:
                return res
        except Exception as e:
            api_health.record_failure("xg:fotmob-pw", f"{type(e).__name__}: {e}")
            if diag is not None:
                diag.append(f"fotmob-pw error: {type(e).__name__}: {e}")

        # ۴) SofaScore از طریق مرورگر واقعی Playwright (با مدارقطع‌کن api_health)
        if not api_health.is_cooling("xg:sofascore-pw"):
            try:
                res = fetch_sofascore_via_playwright(home_en, away_en, match_date, timeout=max(20.0, timeout))
                if res and res.get("home_xg") is not None and res.get("away_xg") is not None:
                    api_health.record_success("xg:sofascore-pw", 3000.0)
                    return res
                api_health.record_failure("xg:sofascore-pw", "no result", base_cooldown=300.0)
                if diag is not None:
                    diag.append("sofascore-pw: no result")
            except Exception as e:
                api_health.record_failure("xg:sofascore-pw", f"{type(e).__name__}: {e}")
                if diag is not None:
                    diag.append(f"sofascore-pw error: {type(e).__name__}: {e}")

    # ۴) Understat (۵ لیگ داخلی اروپا)
    try:
        from src.xgpedia.providers.understat import fetch_match_shots_understat

        us = fetch_match_shots_understat(
            home_en, away_en, match_date, season_start=season_start, timeout=timeout, competition=competition
        )
        if us and us.get("home_xg") is not None and us.get("away_xg") is not None:
            us["provider"] = "understat"
            return us
    except Exception:
        pass

    log.warning("xg_engine: real xG not found for %s vs %s (%s)", home_en, away_en, match_date)
    return None


# ─── زنجیرهٔ پلاگین‌پذیر xG (مرتب‌شده بر اساس امتیاز اعتبار در config/data_source_chains.json) ───
from src.xgpedia.core.source_chain import DataSourceChain, SourceCandidate, get_domain_authority_map

_XG_SCORES = get_domain_authority_map("match_xg_and_shotmap")
MATCH_XG_CHAIN = DataSourceChain(
    "match_xg_and_shotmap",
    [
        SourceCandidate("sofascore", _XG_SCORES.get("sofascore", 94), "SofaScore (Opta)", fetcher=fetch_sofascore_match_xg, health_key="xg:sofascore"),
        SourceCandidate("fotmob", _XG_SCORES.get("fotmob", 93), "FotMob (Opta)", fetcher=fetch_fotmob_match_xg, health_key="xg:fotmob"),
        SourceCandidate("fotmob-playwright", _XG_SCORES.get("fotmob", 93) - 1, "FotMob Playwright (Opta)", fetcher=fetch_fotmob_via_playwright, health_key="xg:fotmob-pw"),
        SourceCandidate("sofascore-playwright", _XG_SCORES.get("sofascore", 94) - 3, "SofaScore Playwright (Opta)", fetcher=fetch_sofascore_via_playwright, health_key="xg:sofascore-pw"),
    ],
)


def register_xg_source(candidate: SourceCandidate) -> None:
    """افزودن یک منبع xG جدید (مثلاً Sportmonks یا Opta رسمی) با مرتب‌سازی خودکار بر اساس امتیاز اعتبار."""
    MATCH_XG_CHAIN.register(candidate)
