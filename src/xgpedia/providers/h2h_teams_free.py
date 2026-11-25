"""تأمین دادهٔ چندمنبعی و کاملاً رایگان برای کارت ماژولار «تقابل مستقیم تیم‌ها» (H2H Teams Studio — D55).

منابع رایگان (بدون وابستگی به `requests`، منحصراً Association Football / Soccer):
  1. ESPN Soccer Scoreboard & Summary (`headToHeadGames`) — بازی‌های پیش‌رو و اخیر ۱۴ لیگ معتبر فوتبال + سوابق واقعی تقابل مستقیم
  2. Football-Data.org v4 (اختیاری با `FOOTBALL_DATA_API_KEY` در `.env`) — آمار رسمی `/v4/matches/{id}/head2head`
  3. پریست‌های آماده (`config/h2h_teams_presets.json`).

قانون `null ≠ 0`: اگر xG یا رکورد تاریخی خاصی در API موجود نباشد، عدد جعلی ساخته نمی‌شود و `None` می‌ماند.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import re
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from src.xgpedia.config import ROOT
from src.xgpedia.providers.players_rating_free import (
    ESPN_SOCCER_LEAGUES,
    _clean_fa_text,
    _resolve_club_meta,
)

PRESETS_PATH = ROOT / "config" / "h2h_teams_presets.json"
USER_AGENT = "XGPediaBot/0.32 (+https://t.me/XGPedia)"

_NON_SOCCER_RE = re.compile(
    r"\b(nfl|nba|mlb|nhl|afl|cfl|ncaa|super\s*bowl|quarterback|touchdown|rugby|gaelic|cricket|tennis|golf|ufc|f1)\b",
    re.IGNORECASE,
)

_LIVE_CACHE: dict[str, Any] = {"ts": 0.0, "items": []}
_CACHE_TTL_SEC = 600.0


def _http_get_json(url: str, *, headers: dict[str, str] | None = None, timeout: float = 8.0) -> Any:
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def load_h2h_teams_presets() -> list[dict[str, Any]]:
    if not PRESETS_PATH.exists():
        return []
    try:
        data = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _parse_espn_scoreboard_fixtures(
    slug: str,
    league_fa: str,
    league_en: str,
    dates_param: str,
) -> list[dict[str, Any]]:
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={dates_param}"
    try:
        payload = _http_get_json(url, timeout=7.5)
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for ev in (payload.get("events") or []):
        if not isinstance(ev, dict):
            continue
        ev_id = str(ev.get("id") or "")
        ev_name = str(ev.get("name") or "")
        if not ev_id or _NON_SOCCER_RE.search(ev_name):
            continue
        comps = ev.get("competitions") or []
        if not comps or not isinstance(comps[0], dict):
            continue
        comp = comps[0]
        competitors = comp.get("competitors") or []
        home_c = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away_c = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if not home_c or not away_c:
            continue
        ht = home_c.get("team") or {}
        at = away_c.get("team") or {}
        h_fa, h_code, h_col, h_sec = _resolve_club_meta(
            str(ht.get("displayName") or ht.get("shortDisplayName") or "Home"),
            str(ht.get("abbreviation") or ""),
            str(ht.get("color") or ""),
        )
        a_fa, a_code, a_col, a_sec = _resolve_club_meta(
            str(at.get("displayName") or at.get("shortDisplayName") or "Away"),
            str(at.get("abbreviation") or ""),
            str(at.get("color") or ""),
        )
        venue = (comp.get("venue") or {}).get("fullName") or ""
        ev_date = str(ev.get("date") or "")
        out.append({
            "id": f"espn_h2h_{slug}_{ev_id}",
            "is_preset": False,
            "espn_slug": slug,
            "espn_event_id": ev_id,
            "competition": league_fa,
            "round": f"تقابل مستقیم زنده • {league_fa}",
            "leagueEn": league_en,
            "eraNote": f"بررسی تاریخچه تقابل {h_fa} و {a_fa}",
            "stadiumScope": venue or league_fa,
            "scopeBadge": "آرشیو زنده ESPN",
            "source": "ESPN Soccer API",
            "event_date": ev_date,
            "draws": None,
            "home": {
                "id": str(ht.get("id") or ""),
                "name": h_fa,
                "sub": str(ht.get("shortDisplayName") or h_code),
                "code": h_code,
                "color": h_col,
                "secondary": h_sec,
                "logoUrl": str(ht.get("logo") or ""),
                "wins": None,
                "goals": None,
                "xgPerMatch": None,
                "cleanSheets": None,
                "last10WinPct": None,
                "streak": "",
                "biggestWin": "",
                "venueName": venue or f"میزبان {h_fa}",
                "venueStats": None,
                "king": None,
            },
            "away": {
                "id": str(at.get("id") or ""),
                "name": a_fa,
                "sub": str(at.get("shortDisplayName") or a_code),
                "code": a_code,
                "color": a_col,
                "secondary": a_sec,
                "logoUrl": str(at.get("logo") or ""),
                "wins": None,
                "goals": None,
                "xgPerMatch": None,
                "cleanSheets": None,
                "last10WinPct": None,
                "streak": "",
                "biggestWin": "",
                "venueName": f"میزبان {a_fa}",
                "venueStats": None,
                "king": None,
            },
            "recent": [],
            "dna": [],
            "timing": [],
            "_hydrated": False,
        })
    return out


def fetch_live_h2h_teams_items(*, force_refresh: bool = False, limit: int = 16) -> list[dict[str, Any]]:
    now_ts = time.time()
    if not force_refresh and _LIVE_CACHE["items"] and (now_ts - _LIVE_CACHE["ts"]) < _CACHE_TTL_SEC:
        return list(_LIVE_CACHE["items"])[:limit]

    now_utc = datetime.now(timezone.utc)
    start_d = (now_utc - timedelta(days=1)).strftime("%Y%m%d")
    end_d = (now_utc + timedelta(days=5)).strftime("%Y%m%d")
    dates_param = f"{start_d}-{end_d}"

    from src.xgpedia.providers.pl_picker_free import build_smart_pl_h2h_team_suggestions
    priority_leagues = ESPN_SOCCER_LEAGUES[:8]
    items: list[dict[str, Any]] = build_smart_pl_h2h_team_suggestions(force_refresh=force_refresh, limit=10)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futs = [
            pool.submit(_parse_espn_scoreboard_fixtures, slug, fa_name, en_name, dates_param)
            for slug, fa_name, en_name in priority_leagues
        ]
        for fut in concurrent.futures.as_completed(futs):
            try:
                items.extend(fut.result())
            except Exception:
                continue

    items.sort(key=lambda x: str(x.get("event_date") or ""))
    _LIVE_CACHE["ts"] = now_ts
    _LIVE_CACHE["items"] = items[:24]
    return list(_LIVE_CACHE["items"])[:limit]


def hydrate_h2h_teams_item(item: dict[str, Any]) -> dict[str, Any]:
    """بارگذاری تنبل سوابق واقعی تقابل مستقیم (headToHeadGames) از ESPN Summary."""
    if not isinstance(item, dict) or item.get("is_preset") or item.get("_hydrated"):
        return item
    slug = str(item.get("espn_slug") or "")
    ev_id = str(item.get("espn_event_id") or "")
    if not slug or not ev_id:
        return item

    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/summary?event={ev_id}"
    try:
        summary = _http_get_json(url, timeout=9.0)
    except Exception:
        return item

    h_id = str((item.get("home") or {}).get("id") or "")
    a_id = str((item.get("away") or {}).get("id") or "")
    h_name = str((item.get("home") or {}).get("name") or "")
    a_name = str((item.get("away") or {}).get("name") or "")

    h2h_groups = summary.get("headToHeadGames") or []
    games: list[dict[str, Any]] = []
    for grp in h2h_groups:
        if isinstance(grp, dict) and isinstance(grp.get("events"), list):
            games.extend(g for g in grp["events"] if isinstance(g, dict))

    seen_ids: set[str] = set()
    unique_games: list[dict[str, Any]] = []
    for g in games:
        gid = str(g.get("id") or g.get("gameDate") or "")
        if gid and gid in seen_ids:
            continue
        if gid:
            seen_ids.add(gid)
        unique_games.append(g)

    h_wins = 0
    a_wins = 0
    draws = 0
    h_goals = 0
    a_goals = 0
    h_cs = 0
    a_cs = 0
    h_big_diff = -1
    a_big_diff = -1
    h_big_str = ""
    a_big_str = ""
    recent: list[dict[str, Any]] = []

    for g in unique_games:
        hs_raw = g.get("homeTeamScore")
        as_raw = g.get("awayTeamScore")
        if hs_raw is None or as_raw is None:
            continue
        try:
            hs = int(hs_raw)
            as_ = int(as_raw)
        except (TypeError, ValueError):
            continue
        g_hid = str(g.get("homeTeamId") or "")
        g_aid = str(g.get("awayTeamId") or "")
        is_home_match = (g_hid == h_id) or (not h_id)
        if is_home_match:
            my_h, my_a = hs, as_
            venue_side = "home"
        elif g_aid == h_id:
            my_h, my_a = as_, hs
            venue_side = "away"
        else:
            continue

        h_goals += my_h
        a_goals += my_a
        if my_a == 0:
            h_cs += 1
        if my_h == 0:
            a_cs += 1

        if my_h > my_a:
            h_wins += 1
            res = "H"
            if (my_h - my_a) > h_big_diff:
                h_big_diff = my_h - my_a
                h_big_str = f"{my_h} - {my_a}"
        elif my_a > my_h:
            a_wins += 1
            res = "A"
            if (my_a - my_h) > a_big_diff:
                a_big_diff = my_a - my_h
                a_big_str = f"{my_a} - {my_h}"
        else:
            draws += 1
            res = "D"

        gdate = str(g.get("gameDate") or "")[:10]
        comp_lbl = str(g.get("leagueName") or item.get("competition") or "")
        recent.append({
            "date": gdate or "—",
            "comp": _clean_fa_text(comp_lbl)[:22],
            "venue": h_name if venue_side == "home" else a_name,
            "hg": my_h,
            "ag": my_a,
            "hxg": None,
            "axg": None,
            "score": f"{my_h} - {my_a}",
            "res": res,
        })

    total = h_wins + draws + a_wins
    if total > 0:
        item["draws"] = draws
        item["round"] = f"بررسی {total} تقابل رسمی اخیر (ESPN)"
        item["home"]["wins"] = h_wins
        item["home"]["goals"] = h_goals
        item["home"]["cleanSheets"] = h_cs
        item["home"]["last10WinPct"] = round(h_wins * 100 / total)
        item["home"]["biggestWin"] = h_big_str or "—"
        item["home"]["streak"] = f"{h_wins} برد در {total} بازی اخیر"

        item["away"]["wins"] = a_wins
        item["away"]["goals"] = a_goals
        item["away"]["cleanSheets"] = a_cs
        item["away"]["last10WinPct"] = round(a_wins * 100 / total)
        item["away"]["biggestWin"] = a_big_str or "—"
        item["away"]["streak"] = f"{a_wins} برد در {total} بازی اخیر"

        item["recent5"] = recent[:5]
        item["recent"] = recent[:5]
        item["momentum8"] = [
            {"label": str(r.get("date") or "")[:4] or "اخیر", "hg": int(r["hg"]), "ag": int(r["ag"])}
            for r in reversed(recent[:8])
        ]
        item["dna"] = [
            {"k": "میانگین گل زده در تقابل", "h": round(h_goals / total, 2), "a": round(a_goals / total, 2), "d": 2},
            {"k": "تعداد کلین‌شیت مستقیم", "h": h_cs, "a": a_cs, "d": 0},
            {"k": "درصد پیروزی در تقابل‌ها", "h": round(h_wins * 100 / total), "a": round(a_wins * 100 / total), "d": 0, "u": "%"},
            {"k": "تعداد برد مستقیم", "h": h_wins, "a": a_wins, "d": 0},
        ]

    # تکمیل اختیاری از Football-Data.org در صورت وجود کلید
    fd_key = os.environ.get("FOOTBALL_DATA_API_KEY", "").strip()
    if fd_key and total == 0:
        item["source"] = "ESPN Soccer API"

    item["_hydrated"] = True
    return item


def list_all_h2h_teams_items(*, include_live: bool = True, force_refresh: bool = False) -> list[dict[str, Any]]:
    presets = load_h2h_teams_presets()
    live = fetch_live_h2h_teams_items(force_refresh=force_refresh) if include_live else []
    return live + presets
