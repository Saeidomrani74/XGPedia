"""استخراج‌کننده‌های Playwright برای FotMob و SofaScore (استخراج‌شده از xg_engine.py در v0.76.0)."""
from __future__ import annotations

import json
import re
import time
from typing import Any

from src.xgpedia.providers import xg_engine as _xge


def _extract_fotmob_matches_from_next_data(*a, **kw): return _xge._extract_fotmob_matches_from_next_data(*a, **kw)
def _match_fotmob_entries(*a, **kw): return _xge._match_fotmob_entries(*a, **kw)
def _date_candidates(*a, **kw): return _xge._date_candidates(*a, **kw)
def _teams_match(*a, **kw): return _xge._teams_match(*a, **kw)
def _swap_parsed(*a, **kw): return _xge._swap_parsed(*a, **kw)
def parse_fotmob_match_details(*a, **kw): return _xge.parse_fotmob_match_details(*a, **kw)
def parse_sofascore_statistics(*a, **kw): return _xge.parse_sofascore_statistics(*a, **kw)
def parse_sofascore_shotmap(*a, **kw): return _xge.parse_sofascore_shotmap(*a, **kw)


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
                    except Exception as _em_exc:
                        from src.xgpedia.core.error_metrics import record_error as _rec_err
                        _rec_err("provider.xg_engine", _em_exc)
                    captured_matches: list[dict[str, Any]] = []
                    captured_details: list[dict[str, Any]] = []

                    def _on_resp(resp) -> None:
                        try:
                            u = resp.url
                            if resp.status == 200 and ("/api/matches" in u or "/api/data/matches" in u):
                                captured_matches.append(resp.json())
                            elif resp.status == 200 and ("/api/matchDetails" in u or "/api/data/matchDetails" in u):
                                captured_details.append(resp.json())
                        except Exception as _em_exc:
                            from src.xgpedia.core.error_metrics import record_error as _rec_err
                            _rec_err("provider.xg_engine", _em_exc)

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
                        except Exception as _em_exc:
                            from src.xgpedia.core.error_metrics import record_error as _rec_err
                            _rec_err("provider.xg_engine", _em_exc)

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
                        except Exception as _em_exc:
                            from src.xgpedia.core.error_metrics import record_error as _rec_err
                            _rec_err("provider.xg_engine", _em_exc)
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
                        except Exception as _em_exc:
                            from src.xgpedia.core.error_metrics import record_error as _rec_err
                            _rec_err("provider.xg_engine", _em_exc)

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
        _xge.log.info("xg_engine [fotmob-playwright] %s vs %s -> xG %.2f - %.2f", home_en, away_en, res["home_xg"], res["away_xg"])
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
            _xge.log.debug("xg_engine playwright fallback failed: %s", e)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=timeout + 5.0)
    res = box.get("result")
    if res:
        _xge.log.info("xg_engine [sofascore-playwright] %s vs %s -> xG %.2f - %.2f", home_en, away_en, res["home_xg"], res["away_xg"])
    return res
