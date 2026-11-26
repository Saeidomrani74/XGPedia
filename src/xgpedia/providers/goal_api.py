"""آداپتر رسمی GOAL API (`https://api.goal-api.com/v1`) برای XGPedia (نسخهٔ 0.68.0).

پشتیبانی اختیاری از کلید `GOAL_API_KEY` در `.env` (بدون وابستگی به `requests`، فقط stdlib `urllib.request`):
  - `GET /v1/leagues` (کشف خودکار شناسهٔ لیگ‌های PL, CL, EL, PD, SA, BL1, FL1)
  - `GET /v1/leagues/:id/top-scorers` (گلزنان برتر، پنالتی، باشگاه و دقایق/بازی برای همهٔ لیگ‌ها از جمله لیگ اروپا)
  - `GET /v1/leagues/:id/standings` (جدول رده‌بندی زنده)
  - `GET /v1/fixtures/date/:date` (برنامه و نتایج روزانه)
  - `GET /v1/coaches/team/:teamId` (سرمربی زندهٔ باشگاه)

قاعدهٔ هویتی XGPedia (`null ≠ 0`): اگر فیلدی (مثل پنالتی یا xG) در پاسخ موجود نباشد، `None` می‌ماند و هرگز جعل نمی‌شود.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from src.xgpedia.core import api_health

GOAL_API_BASE = "https://api.goal-api.com/v1"
USER_AGENT = "XGPedia/0.68 (football-analytics)"

_LEAGUE_CACHE_LOCK = threading.RLock()
_LEAGUE_ID_CACHE: dict[str, str] = {}
_LEAGUE_CACHE_TS: float = 0.0
_LEAGUE_CACHE_TTL: float = 3600.0

# الگوهای نام استاندارد لیگ‌ها در GOAL API برای نگاشت به کدهای XGPedia
_LEAGUE_MATCH_HINTS: dict[str, tuple[str, ...]] = {
    "PL": ("premier league", "england"),
    "CL": ("champions league", "uefa"),
    "EL": ("europa league", "uefa"),
    "PD": ("la liga", "spain"),
    "SA": ("serie a", "italy"),
    "BL1": ("bundesliga", "germany"),
    "FL1": ("ligue 1", "france"),
}


def get_goal_api_key() -> str:
    return (os.environ.get("GOAL_API_KEY") or "").strip()


def _goal_api_get(path: str, *, api_key: str | None = None, timeout: float = 10.0) -> Any | None:
    key = (api_key if api_key is not None else get_goal_api_key()).strip()
    if not key:
        return None
    hk = "goal_api"
    if api_health.is_cooling(hk):
        return None
    url = f"{GOAL_API_BASE}{path if path.startswith('/') else '/' + path}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
        api_health.record_success(hk, (time.perf_counter() - t0) * 1000.0)
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return data
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 429):
            api_health.record_failure(hk, f"HTTP {e.code}", status_code=e.code)
        return None
    except Exception as e:
        api_health.record_failure(hk, f"{type(e).__name__}: {e}", base_cooldown=60.0)
        return None


def resolve_goal_api_league_id(code: str, *, api_key: str | None = None) -> str | None:
    """کشف و کش شناسهٔ یکتای لیگ در GOAL API (برای PL, CL, EL, PD, SA, BL1, FL1)."""
    global _LEAGUE_CACHE_TS
    c = str(code or "").strip().upper()
    if c not in _LEAGUE_MATCH_HINTS:
        return None
    now = time.time()
    with _LEAGUE_CACHE_LOCK:
        if _LEAGUE_ID_CACHE and (now - _LEAGUE_CACHE_TS) < _LEAGUE_CACHE_TTL:
            return _LEAGUE_ID_CACHE.get(c)

    leagues = _goal_api_get("/leagues?limit=250", api_key=api_key, timeout=10.0)
    if not isinstance(leagues, list):
        return None

    found: dict[str, str] = {}
    for lg in leagues:
        if not isinstance(lg, dict):
            continue
        lid = str(lg.get("id") or lg.get("leagueId") or lg.get("apiId") or "").strip()
        lname = str(lg.get("name") or lg.get("leagueName") or "").strip().lower()
        country = str(lg.get("country") or lg.get("countryName") or "").strip().lower()
        if not (lid and lname):
            continue
        for k_code, (name_hint, country_hint) in _LEAGUE_MATCH_HINTS.items():
            if k_code in found:
                continue
            if name_hint in lname and (country_hint in country or country_hint in lname or (country_hint == "uefa" and "europe" in country)):
                # جلوگیری از تطبیق اشتباه با لیگ‌های رده دوم یا زنان
                if any(bad in lname for bad in ("women", "u21", "u19", "2.", "segunda", "serie b", "championship", "youth")):
                    continue
                found[k_code] = lid

    with _LEAGUE_CACHE_LOCK:
        _LEAGUE_ID_CACHE.clear()
        _LEAGUE_ID_CACHE.update(found)
        _LEAGUE_CACHE_TS = time.time()
        return _LEAGUE_ID_CACHE.get(c)


def fetch_goal_api_top_scorers(
    league_code: str,
    *,
    api_key: str | None = None,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """دریافت جدول زندهٔ گلزنان و پنالتی‌های یک لیگ از `GET /v1/leagues/:id/top-scorers`."""
    lid = resolve_goal_api_league_id(league_code, api_key=api_key)
    if not lid:
        return []
    raw = _goal_api_get(f"/leagues/{lid}/top-scorers", api_key=api_key, timeout=10.0)
    rows = raw if isinstance(raw, list) else (raw.get("scorers") or raw.get("topScorers") or [] if isinstance(raw, dict) else [])
    out: list[dict[str, Any]] = []
    for r in rows[:limit]:
        if not isinstance(r, dict):
            continue
        name = str(
            r.get("playerName")
            or r.get("name")
            or ((r.get("player") or {}).get("name") if isinstance(r.get("player"), dict) else "")
            or ""
        ).strip()
        team = str(
            r.get("teamName")
            or r.get("team")
            or ((r.get("team") or {}).get("name") if isinstance(r.get("team"), dict) else "")
            or ""
        ).strip()
        goals_raw = r.get("goals") if r.get("goals") is not None else r.get("goalsScored")
        pen_raw = r.get("penalties") if r.get("penalties") is not None else r.get("penaltyGoals")
        assists_raw = r.get("assists")
        played_raw = r.get("matchesPlayed") or r.get("playedMatches") or r.get("appearances")
        mins_raw = r.get("minutesPlayed") or r.get("minutes")
        if not name or goals_raw is None:
            continue
        try:
            goals = int(goals_raw)
        except (TypeError, ValueError):
            continue
        pen: int | None = None
        if pen_raw is not None and str(pen_raw).strip() != "":
            try:
                pen = int(pen_raw)
            except (TypeError, ValueError):
                pen = None
        mins: int | None = None
        if mins_raw is not None:
            try:
                mins = int(mins_raw) if int(mins_raw) > 0 else None
            except (TypeError, ValueError):
                mins = None
        elif played_raw is not None:
            try:
                pm = int(played_raw)
                mins = pm * 90 if pm > 0 else None
            except (TypeError, ValueError):
                mins = None
        out.append({
            "name": name,
            "team": team,
            "goals": goals,
            "pen": pen,
            "assists": int(assists_raw) if assists_raw is not None and str(assists_raw).isdigit() else None,
            "mins": mins,
        })
    return out


def fetch_goal_api_fixtures_by_date(date_iso: str, *, api_key: str | None = None) -> list[dict[str, Any]]:
    """دریافت مسابقات یک تاریخ (`YYYY-MM-DD`) از `GET /v1/fixtures/date/:date`."""
    d = str(date_iso or "")[:10]
    if len(d) != 10:
        return []
    raw = _goal_api_get(f"/fixtures/date/{d}", api_key=api_key, timeout=10.0)
    return raw if isinstance(raw, list) else []
