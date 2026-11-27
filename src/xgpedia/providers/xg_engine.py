"""موتور واقعی xG اپتا (FotMob HTTP/Playwright، Understat، پشتیبان اختیاری API-Football؛ SofaScore خاموش پیش‌فرض)."""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Callable
import json
from src.xgpedia.config import CURRENT_SEASON_START, canonical_team_name

from src.xgpedia.providers.xg_engine_common import (  # noqa: F401
    _FOTMOB_DAY_CACHE,
    _FOTMOB_DAY_CACHE_LOCK,
    _FOTMOB_DAY_CACHE_TTL,
    _FOTMOB_BASE,
    _SOFA_BASE,
    api_health,
    _date_candidates,
    _extract_fotmob_matches_from_next_data,
    _extract_fotmob_slug_teams,
    _http_get_json,
    _http_get_text,
    _match_fotmob_entries,
    _strip_accents_lower,
    _swap_parsed,
    _teams_match,
    _to_float,
    clear_fotmob_day_cache,
    log,
    parse_sofascore_shotmap,
    parse_sofascore_statistics,
)



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
        except Exception as _em_exc:
            from src.xgpedia.core.error_metrics import record_error as _rec_err
            _rec_err("provider.xg_engine", _em_exc)
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











from src.xgpedia.providers.xg_engine_fotmob import (  # noqa: E402, F401
    _fotmob_player_name,
    _fotmob_pos_fa,
    _fotmob_stat_val,
    parse_fotmob_match_details,
    parse_fotmob_next_data_html,
)
from src.xgpedia.providers.xg_engine_playwright import (  # noqa: E402, F401
    fetch_fotmob_via_playwright,
    fetch_sofascore_via_playwright,
)

def fetch_fotmob_match_xg(
    home_en: str,
    away_en: str,
    match_date: str,
    *,
    timeout: float = 10.0,
) -> dict[str, Any] | None:
    """دریافت xG واقعی Opta از FotMob (ابتدا کش پایدار SQLite، سپس API و صفحهٔ SSR `__NEXT_DATA__`)."""
    from src.xgpedia.core import hydration_cache as _hc
    _fm_ck = f"fotmob_post_match:{_strip_accents_lower(home_en)}:{_strip_accents_lower(away_en)}:{str(match_date or '')[:10]}"
    _fm_hit, _fm_val, _ = _hc.get_cached(_fm_ck)
    if _fm_hit and isinstance(_fm_val, dict) and _fm_val.get("home_xg") is not None:
        return _fm_val
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
        except Exception as _em_exc:
            from src.xgpedia.core.error_metrics import record_error as _rec_err
            _rec_err("provider.xg_engine", _em_exc)
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






# ─── ۴) آبشار یکپارچهٔ xG واقعی ─────────────────────────────────────────────

def is_sofascore_enabled() -> bool:
    """کنترل فعال/غیرفعال‌بودن SofaScore در زنجیرهٔ زنده (پیش‌فرض خاموش برای جلوگیری از 403 و افزایش سرعت).
    برای فعال‌سازی مجدد در آینده کافی است در .env مقدار XGPEDIA_ENABLE_SOFASCORE=1 تنظیم شود.
    """
    return os.environ.get("XGPEDIA_ENABLE_SOFASCORE", "0").strip().lower() in ("1", "true", "yes", "on")


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
    """دریافت xG واقعی Opta یک مسابقه: FotMob → FotMob Playwright → Understat → (اختیاری: SofaScore با XGPEDIA_ENABLE_SOFASCORE=1)."""
    # ۱) FotMob (HTTP API + __NEXT_DATA__)
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

    # ۲) FotMob از طریق مرورگر واقعی Playwright (رهگیری JSON رسمی Opta امضاشده توسط خود سایت)
    if allow_playwright:
        try:
            res = fetch_fotmob_via_playwright(home_en, away_en, match_date, timeout=max(22.0, timeout), diag=diag)
            if res and res.get("home_xg") is not None and res.get("away_xg") is not None:
                return res
        except Exception as e:
            api_health.record_failure("xg:fotmob-pw", f"{type(e).__name__}: {e}")
            if diag is not None:
                diag.append(f"fotmob-pw error: {type(e).__name__}: {e}")

    # ۳) Understat (۵ لیگ داخلی اروپا)
    try:
        from src.xgpedia.providers.understat import fetch_match_shots_understat

        us = fetch_match_shots_understat(
            home_en, away_en, match_date, season_start=season_start, timeout=timeout, competition=competition
        )
        if us and us.get("home_xg") is not None and us.get("away_xg") is not None:
            us["provider"] = "understat"
            return us
    except Exception as _em_exc:
        from src.xgpedia.core.error_metrics import record_error as _rec_err
        _rec_err("provider.xg_engine", _em_exc)

    # ۴) SofaScore (حفظ‌شده بدون حذف — فقط در صورت فعال‌سازی XGPEDIA_ENABLE_SOFASCORE=1 به‌عنوان آخرین پشتیبان)
    if is_sofascore_enabled():
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

        if allow_playwright and not api_health.is_cooling("xg:sofascore-pw"):
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
    elif diag is not None:
        diag.append("sofascore: skipped (XGPEDIA_ENABLE_SOFASCORE=0)")

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
