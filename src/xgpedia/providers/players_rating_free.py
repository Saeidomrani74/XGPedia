"""تأمین دادهٔ چندمنبعی و کاملاً رایگان برای کارت ماژولار «نمرات بازیکنان» (Players Rating Studio — D51).

منابع رایگان (بدون وابستگی به `requests`، منحصراً Association Football / Soccer):
  1. ESPN Soccer Public Scoreboard & Summary API (`site.api.espn.com/apis/site/v2/sports/soccer/{league}/...`)
     — جستجوی سریع و دقیق بازی‌های پایان‌یافته از **۱ ثانیه قبل تا ۲۴ ساعت قبل** در ۱۴ لیگ و تورنمنت معتبر فوتبال؛
       دریافت لیست مسابقات به‌صورت سبک (فقط Scoreboard) و دریافت جزئیات کامل ۱۱ نفره، تعویضی‌ها و نمرات هنگام باز کردن مسابقه
  2. پریست‌های آماده (`config/players_rating_presets.json`)
  3. غنی‌سازی اختیاری جمع‌بندی تحریریه فارسی (`verdict`) با LLM چندکلیدی (`cancel_event`).

قانون `null ≠ 0`: هرگاه xG یا ترکیب/نمرهٔ واقعی موجود نباشد، عدد جعلی ساخته نمی‌شود و `None` باقی می‌ماند.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.xgpedia.config import ROOT

PRESETS_PATH = ROOT / "config" / "players_rating_presets.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

ESPN_SOCCER_LEAGUES: list[tuple[str, str, str]] = [
    ("eng.1", "لیگ برتر انگلیس", "PREMIER LEAGUE"),
    ("esp.1", "لالیگا اسپانیا", "LALIGA"),
    ("ita.1", "سری آ ایتالیا", "SERIE A"),
    ("ger.1", "بوندسلیگا آلمان", "BUNDESLIGA"),
    ("fra.1", "لیگ یک فرانسه", "LIGUE 1"),
    ("uefa.champions", "لیگ قهرمانان اروپا", "CHAMPIONS LEAGUE"),
    ("uefa.europa", "لیگ اروپا", "EUROPA LEAGUE"),
    ("uefa.europa.conf", "لیگ کنفرانس اروپا", "CONFERENCE LEAGUE"),
    ("eng.2", "چمپیونشیپ انگلیس", "CHAMPIONSHIP"),
    ("ned.1", "اردیویسه هلند", "EREDIVISIE"),
    ("por.1", "لیگ برتر پرتغال", "PRIMEIRA LIGA"),
    ("ksa.1", "لیگ حرفه‌ای عربستان", "SAUDI PRO LEAGUE"),
    ("usa.1", "لیگ MLS", "MLS"),
    ("afc.champions", "لیگ نخبگان آسیا", "AFC CHAMPIONS LEAGUE"),
]

_NON_SOCCER_RE = re.compile(
    r"\b(nfl|nba|mlb|nhl|afl|cfl|ncaa|super\s*bowl|quarterback|touchdown|rugby|gaelic|cricket|tennis|golf|ufc|f1)\b",
    re.IGNORECASE,
)
_CYRILLIC_CJK_RE = re.compile(r"[\u0400-\u04FF\u3040-\u30FF\u4E00-\u9FFF\uAC00-\uD7AF]+")

_CLUB_COLORS: dict[str, tuple[str, str, str, str]] = {
    "arsenal": ("آرسنال", "ARS", "#EF0107", "#FFFFFF"),
    "liverpool": ("لیورپول", "LIV", "#C8102E", "#F6EB61"),
    "manchester city": ("منچسترسیتی", "MCI", "#38BDF8", "#FFFFFF"),
    "man city": ("منچسترسیتی", "MCI", "#38BDF8", "#FFFFFF"),
    "chelsea": ("چلسی", "CHE", "#2563EB", "#FFFFFF"),
    "manchester united": ("منچستریونایتد", "MUN", "#DA291C", "#FBE122"),
    "man utd": ("منچستریونایتد", "MUN", "#DA291C", "#FBE122"),
    "tottenham": ("تاتنهام", "TOT", "#E2E8F0", "#132257"),
    "tottenham hotspur": ("تاتنهام", "TOT", "#E2E8F0", "#132257"),
    "newcastle": ("نیوکاسل", "NEW", "#CBD5E1", "#0F172A"),
    "newcastle united": ("نیوکاسل", "NEW", "#CBD5E1", "#0F172A"),
    "aston villa": ("استون ویلا", "AVL", "#95BFE5", "#670E36"),
    "brighton": ("برایتون", "BHA", "#38BDF8", "#FFCD00"),
    "real madrid": ("رئال مادرید", "RMA", "#F59E0B", "#FFFFFF"),
    "barcelona": ("بارسلونا", "BAR", "#E62E45", "#004D98"),
    "atletico madrid": ("اتلتیکو مادرید", "ATM", "#DC2626", "#FFFFFF"),
    "bayern munich": ("بایرن مونیخ", "BAY", "#DC2626", "#FFFFFF"),
    "borussia dortmund": ("دورتموند", "BVB", "#FACC15", "#0F172A"),
    "bayer leverkusen": ("بایر لورکوزن", "LEV", "#E32221", "#111827"),
    "inter milan": ("اینتر میلان", "INT", "#2563EB", "#0F172A"),
    "internazionale": ("اینتر میلان", "INT", "#2563EB", "#0F172A"),
    "ac milan": ("آث میلان", "ACM", "#DC2626", "#111827"),
    "juventus": ("یوونتوس", "JUV", "#F8FAFC", "#0F172A"),
    "napoli": ("ناپولی", "NAP", "#38BDF8", "#FFFFFF"),
    "paris saint-germain": ("پاری سن ژرمن", "PSG", "#2563EB", "#E62E45"),
    "persepolis": ("پرسپولیس", "PRS", "#E62E45", "#FFFFFF"),
    "esteghlal": ("استقلال", "EST", "#3B82F6", "#FFFFFF"),
    "sepahan": ("سپاهان", "SEP", "#F59E0B", "#111827"),
    "tractor": ("تراکتور", "TRA", "#DC2626", "#FFFFFF"),
}

_LIVE_CACHE: dict[str, Any] = {"ts": 0.0, "items": []}
_CACHE_TTL_SEC = 180.0


def _clean_fa_text(text: str) -> str:
    s = _CYRILLIC_CJK_RE.sub("", str(text or ""))
    s = s.replace("*", "").replace("`", "")
    return re.sub(r"\s+", " ", s).strip()


def _http_get_json(url: str, timeout: float = 8.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _resolve_club_meta(raw_name: str, raw_abbr: str = "", raw_color: str = "") -> tuple[str, str, str, str]:
    low = (raw_name or "").strip().lower()
    for k, meta in _CLUB_COLORS.items():
        if k == low or k in low:
            return meta
    code = re.sub(r"[^A-Za-z]", "", raw_abbr or raw_name or "FC").upper()[:3] or "FC"
    col = f"#{raw_color.lstrip('#')}" if raw_color and len(raw_color.lstrip("#")) == 6 else "#38BDF8"
    return (raw_name or code, code, col, "#FFFFFF")


def _pos_to_line_code(pos_abbr: str) -> tuple[str, int]:
    p = (pos_abbr or "CM").upper().strip()
    if p in ("G", "GK"):
        return "GK", 0
    if p in ("D", "DF", "CB", "RB", "LB", "RWB", "LWB", "CD", "SW"):
        return (p if len(p) >= 2 else "CB"), 1
    if p in ("M", "MF", "CM", "CDM", "CAM", "RM", "LM", "DM", "AM", "RCM", "LCM"):
        return (p if len(p) >= 2 else "CM"), 2
    return (p if len(p) >= 2 else "ST"), 3


def _assign_cols(players: list[dict[str, Any]]) -> None:
    by_line: dict[int, list[dict[str, Any]]] = {0: [], 1: [], 2: [], 3: []}
    for pl in players:
        by_line.setdefault(int(pl.get("line", 2)), []).append(pl)
    for group in by_line.values():
        n = len(group)
        if n == 1:
            group[0]["col"] = 0.5
        elif n > 1:
            for idx, pl in enumerate(group):
                pl["col"] = round(0.14 + (0.72 * idx / (n - 1)), 2)


def _derive_rating_from_events(
    *,
    is_winner: bool,
    is_draw: bool,
    goals: int,
    assists: int,
    yc: int,
    rc: int,
    conceded: int,
    line: int,
    bps: float | None = None,
) -> float:
    if bps is not None:
        raw = 5.6 + (float(bps) / 11.2) + (0.25 if goals > 0 else 0.0) + (0.15 if assists > 0 else 0.0)
        return round(min(9.9, max(4.8, raw)), 1)
    base = 6.9 if is_winner else (6.6 if is_draw else 6.2)
    base += goals * 0.95 + assists * 0.65
    if line in (0, 1) and conceded == 0:
        base += 0.45
    elif line in (0, 1) and conceded >= 3:
        base -= 0.55
    base -= yc * 0.25 + rc * 1.15
    return round(min(9.7, max(4.8, base)), 1)


def _parse_iso_utc(dt_str: str) -> datetime | None:
    s = (dt_str or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def is_finished_within_24h(kickoff_iso: str, *, now_utc: datetime | None = None) -> tuple[bool, float]:
    """بررسی دقیق اینکه مسابقه بین ۱ ثانیه تا ۲۴ ساعت قبل به اتمام رسیده باشد.

    زمان پایان مسابقه ≈ زمان شروع + ۱۱۵ دقیقه (۹۰ دقیقه + ۱۵ نیمه + ۱۰ وقت اضافه).
    اگر بازی در وضعیت `post` باشد و `1s <= (now - finish_est) <= 86400s` (یا بازی تازه تمام شده و `now >= kickoff` و `finish_est >= now - 86400s`)
    معتبر است.
    """
    now = now_utc or datetime.now(timezone.utc)
    ko = _parse_iso_utc(kickoff_iso)
    if ko is None:
        return False, -1.0
    if now < ko:
        return False, -1.0
    est_end = ko + timedelta(minutes=115)
    # اگر بازی زودتر از ۱۱۵ دقیقه (مثلاً ۱۰۵ دقیقه) سوت پایان خورده و state=='post' است:
    if est_end > now:
        est_end = now - timedelta(seconds=1)
    elapsed = (now - est_end).total_seconds()
    return (1.0 <= elapsed <= 86400.0), elapsed


def load_players_rating_presets() -> list[dict[str, Any]]:
    if not PRESETS_PATH.exists():
        return []
    try:
        data = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def parse_espn_scoreboard_finished_24h(
    payload: dict[str, Any],
    *,
    league_slug: str,
    league_fa: str,
    league_en: str,
    now_utc: datetime | None = None,
) -> list[dict[str, Any]]:
    """استخراج سریع مسابقات پایان‌یافته بین ۱ ثانیه تا ۲۴ ساعت قبل از Scoreboard ESPN."""
    if not isinstance(payload, dict):
        return []
    out: list[dict[str, Any]] = []
    now = now_utc or datetime.now(timezone.utc)
    for ev in payload.get("events") or []:
        if not isinstance(ev, dict):
            continue
        comps = ev.get("competitions") or []
        if not comps or not isinstance(comps[0], dict):
            continue
        comp = comps[0]
        st_type = (comp.get("status") or {}).get("type") or (ev.get("status") or {}).get("type") or {}
        if str(st_type.get("state") or "").lower() != "post" and not st_type.get("completed"):
            continue
        ko_str = str(comp.get("date") or ev.get("date") or "")
        ok_24h, elapsed = is_finished_within_24h(ko_str, now_utc=now)
        if not ok_24h:
            continue
        competitors = [c for c in (comp.get("competitors") or []) if isinstance(c, dict)]
        home_c = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away_c = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if not (home_c and away_c):
            continue
        h_raw = home_c.get("team") or {}
        a_raw = away_c.get("team") or {}
        h_en = str(h_raw.get("displayName") or h_raw.get("name") or "")
        a_en = str(a_raw.get("displayName") or a_raw.get("name") or "")
        if _NON_SOCCER_RE.search(f"{h_en} {a_en} {league_en}"):
            continue
        try:
            hg = int(home_c.get("score") or 0)
            ag = int(away_c.get("score") or 0)
        except (TypeError, ValueError):
            continue
        h_fa, h_code, h_col, h_sec = _resolve_club_meta(h_en, str(h_raw.get("abbreviation") or ""), str(h_raw.get("color") or ""))
        a_fa, a_code, a_col, a_sec = _resolve_club_meta(a_en, str(a_raw.get("abbreviation") or ""), str(a_raw.get("color") or ""))
        if h_col.upper() == a_col.upper():
            a_col = "#38BDF8"
        ev_id = str(ev.get("id") or "")
        if not ev_id:
            continue
        out.append({
            "id": f"espn_{league_slug}_{ev_id}",
            "is_live": True,
            "needs_summary_fetch": True,
            "espn_slug": league_slug,
            "espn_event_id": ev_id,
            "finished_elapsed_sec": int(elapsed),
            "competition": league_fa,
            "round": "پایان مسابقه (۲۴ ساعت اخیر)",
            "leagueEn": league_en,
            "season": "26/27",
            "weekCode": "FT",
            "stadium": str(((comp.get("venue") or {}).get("fullName")) or "ورزشگاه مسابقه"),
            "statusTag": "پایان مسابقه • FT",
            "source": "ESPN Soccer / XGPedia Rating Engine",
            "source_url": f"https://www.espn.com/soccer/match/_/gameId/{ev_id}",
            "homeGoals": hg,
            "awayGoals": ag,
            "homeXg": None,
            "awayXg": None,
            "homeScorers": "—",
            "awayScorers": "—",
            "home": {"name": h_fa, "code": h_code, "color": h_col, "secondary": h_sec, "formation": "4-3-3", "coach": "", "links": [], "xi": [], "subs": []},
            "away": {"name": a_fa, "code": a_code, "color": a_col, "secondary": a_sec, "formation": "4-3-3", "coach": "", "links": [], "xi": [], "subs": []},
            "verdict": None,
        })
    return out


def parse_espn_match_summary(
    summary: dict[str, Any],
    *,
    league_slug: str,
    league_fa: str,
    league_en: str,
    event_id: str,
) -> dict[str, Any] | None:
    """پارس ترکیب ۱۱ نفره، تعویضی‌ها، رخدادها و نمرات واقعی از ESPN Soccer Summary JSON."""
    if not isinstance(summary, dict):
        return None
    header = summary.get("header") or {}
    comps = header.get("competitions") or []
    if not comps or not isinstance(comps[0], dict):
        return None
    comp = comps[0]
    competitors = [c for c in (comp.get("competitors") or []) if isinstance(c, dict)]
    home_c = next((c for c in competitors if c.get("homeAway") == "home"), None)
    away_c = next((c for c in competitors if c.get("homeAway") == "away"), None)
    if not (home_c and away_c):
        return None

    h_team_raw = home_c.get("team") or {}
    a_team_raw = away_c.get("team") or {}
    h_name_en = str(h_team_raw.get("displayName") or h_team_raw.get("name") or "")
    a_name_en = str(a_team_raw.get("displayName") or a_team_raw.get("name") or "")
    if _NON_SOCCER_RE.search(f"{h_name_en} {a_name_en} {league_en}"):
        return None

    try:
        hg = int(home_c.get("score") or 0)
        ag = int(away_c.get("score") or 0)
    except (TypeError, ValueError):
        return None

    h_fa, h_code, h_col, h_sec = _resolve_club_meta(h_name_en, str(h_team_raw.get("abbreviation") or ""), str(h_team_raw.get("color") or ""))
    a_fa, a_code, a_col, a_sec = _resolve_club_meta(a_name_en, str(a_team_raw.get("abbreviation") or ""), str(a_team_raw.get("color") or ""))
    if h_col.upper() == a_col.upper():
        a_col = "#38BDF8"

    rosters = summary.get("rosters") or []
    if len(rosters) < 2:
        return None

    def _parse_side(roster_obj: dict[str, Any], is_home: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, list[str]]:
        xi: list[dict[str, Any]] = []
        subs: list[dict[str, Any]] = []
        scorers: list[str] = []
        formation = str(roster_obj.get("formation") or "4-3-3")
        is_win = (hg > ag) if is_home else (ag > hg)
        is_draw = hg == ag
        conceded = ag if is_home else hg

        for entry in roster_obj.get("roster") or []:
            if not isinstance(entry, dict):
                continue
            ath = entry.get("athlete") or {}
            name = str(ath.get("shortName") or ath.get("displayName") or "").strip()
            if not name:
                continue
            try:
                num = int(entry.get("jersey") or ath.get("jersey") or 0) or 1
            except (TypeError, ValueError):
                num = 1
            pos_raw = str((entry.get("position") or {}).get("abbreviation") or "CM")
            pos_code, line = _pos_to_line_code(pos_raw)
            starter = bool(entry.get("starter"))
            subbed_out = bool(entry.get("subbedOut"))
            subbed_in = bool(entry.get("subbedIn"))

            goals = assists = yc = rc = 0
            sub_min = ""
            for play in entry.get("plays") or []:
                if not isinstance(play, dict):
                    continue
                clk = str((play.get("clock") or {}).get("displayValue") or "")
                if play.get("scoringPlay") or "goal" in str((play.get("type") or {}).get("text") or "").lower():
                    goals += 1
                    scorers.append(f"{name} {clk}".strip())
                if play.get("yellowCard"):
                    yc = 1
                if play.get("redCard"):
                    rc = 1
                if play.get("substitution") and clk:
                    sub_min = clk

            for st in entry.get("stats") or []:
                if not isinstance(st, dict):
                    continue
                sname = str(st.get("name") or "").lower()
                try:
                    sval = int(float(st.get("value") or 0))
                except (TypeError, ValueError):
                    sval = 0
                if sname == "totalgoals" and sval > goals:
                    goals = sval
                elif sname == "goalassists" and sval > assists:
                    assists = sval
                elif sname == "yellowcards" and sval > 0:
                    yc = 1
                elif sname == "redcards" and sval > 0:
                    rc = 1

            rating = _derive_rating_from_events(
                is_winner=is_win, is_draw=is_draw, goals=goals, assists=assists,
                yc=yc, rc=rc, conceded=conceded, line=line,
            )
            if starter:
                xi.append({
                    "name": name, "num": num, "pos": pos_code, "line": line, "col": 0.5,
                    "rating": rating, "g": goals, "a": assists, "yc": yc, "rc": rc,
                    "sub": 1 if subbed_out else 0, "motm": 0,
                })
            elif subbed_in:
                subs.append({"name": name, "num": num, "min": sub_min or "۷۰'", "rating": rating, "g": goals, "a": assists})
        _assign_cols(xi)
        return xi[:11], subs[:4], formation, scorers

    h_roster = next((r for r in rosters if r.get("homeAway") == "home"), rosters[0])
    a_roster = next((r for r in rosters if r.get("homeAway") == "away"), rosters[1])
    h_xi, h_subs, h_form, h_scorers = _parse_side(h_roster, True)
    a_xi, a_subs, a_form, a_scorers = _parse_side(a_roster, False)
    if len(h_xi) < 7 or len(a_xi) < 7:
        return None

    all_xi = h_xi + a_xi
    best_p = max(all_xi, key=lambda x: (x["rating"], x["g"], x["a"]))
    best_p["motm"] = 1

    venue = str(((summary.get("gameInfo") or {}).get("venue") or {}).get("fullName") or "ورزشگاه مسابقه")
    season_yr = str((header.get("season") or {}).get("year") or "2026")
    week_txt = str(header.get("week") or "")

    return {
        "id": f"espn_{league_slug}_{event_id}",
        "is_live": True,
        "needs_summary_fetch": False,
        "espn_slug": league_slug,
        "espn_event_id": event_id,
        "competition": league_fa,
        "round": f"هفته {week_txt} • نمرات بازیکنان" if week_txt else "نمرات بازیکنان مسابقه",
        "leagueEn": league_en,
        "season": f"{season_yr[-2:]}/{int(season_yr[-2:]) + 1}" if season_yr.isdigit() else "26/27",
        "weekCode": f"W{week_txt}" if week_txt else "FT",
        "stadium": venue,
        "statusTag": "پایان مسابقه • FT",
        "source": "ESPN Soccer / XGPedia Rating Engine",
        "source_url": f"https://www.espn.com/soccer/match/_/gameId/{event_id}",
        "homeGoals": hg,
        "awayGoals": ag,
        "homeXg": None,
        "awayXg": None,
        "homeScorers": " • ".join(h_scorers[:4]) if h_scorers else "—",
        "awayScorers": " • ".join(a_scorers[:4]) if a_scorers else "—",
        "home": {"name": h_fa, "code": h_code, "color": h_col, "secondary": h_sec, "formation": h_form, "coach": "", "links": [[5, 8], [5, 6], [6, 2]] if len(h_xi) >= 9 else [], "xi": h_xi, "subs": h_subs},
        "away": {"name": a_fa, "code": a_code, "color": a_col, "secondary": a_sec, "formation": a_form, "coach": "", "links": [[5, 7], [3, 5]] if len(a_xi) >= 8 else [], "xi": a_xi, "subs": a_subs},
        "verdict": None,
    }


def fetch_live_rated_matches(force_refresh: bool = False) -> list[dict[str, Any]]:
    """جستجوی سریع و موازی همهٔ بازی‌های پایان‌یافته بین ۱ ثانیه تا ۲۴ ساعت قبل از ۱۴ لیگ فوتبال."""
    now_ts = time.time()
    if not force_refresh and _LIVE_CACHE["items"] and (now_ts - _LIVE_CACHE["ts"]) < _CACHE_TTL_SEC:
        return list(_LIVE_CACHE["items"])

    now_utc = datetime.now(timezone.utc)
    start_d = (now_utc - timedelta(days=2)).strftime("%Y%m%d")
    end_d = (now_utc + timedelta(days=1)).strftime("%Y%m%d")

    from concurrent.futures import ThreadPoolExecutor

    def _fetch_one(spec: tuple[str, str, str]) -> list[dict[str, Any]]:
        slug, lg_fa, lg_en = spec
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={start_d}-{end_d}"
            sb = _http_get_json(url, timeout=10.0)
            return parse_espn_scoreboard_finished_24h(sb, league_slug=slug, league_fa=lg_fa, league_en=lg_en, now_utc=now_utc)
        except Exception:
            return []

    seen_ids: set[str] = set()
    results: list[dict[str, Any]] = _fetch_fpl_finished_24h_rated_matches(now_utc)
    seen_pairs = {(m['home']['code'], m['away']['code'], m.get('homeGoals'), m.get('awayGoals')) for m in results}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for batch in ex.map(_fetch_one, ESPN_SOCCER_LEAGUES):
            for m in batch:
                eid = str(m.get("espn_event_id") or m.get("id") or "")
                if eid and eid not in seen_ids:
                    seen_ids.add(eid)
                    pk = (m['home']['code'], m['away']['code'], m.get('homeGoals'), m.get('awayGoals'))
            if pk not in seen_pairs:
                seen_pairs.add(pk)
                results.append(m)

    # تکمیل از فید جامع تمام لیگ‌های فوتبال ESPN در صورت کم بودن نتایج
    if len(results) < 4:
        try:
            all_url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={start_d}-{end_d}"
            all_sb = _http_get_json(all_url, timeout=10.0)
            for m in parse_espn_scoreboard_finished_24h(all_sb, league_slug="all", league_fa="فوتبال جهان", league_en="WORLD FOOTBALL", now_utc=now_utc):
                eid = str(m.get("espn_event_id") or m.get("id") or "")
                if eid and eid not in seen_ids:
                    seen_ids.add(eid)
                    pk = (m['home']['code'], m['away']['code'], m.get('homeGoals'), m.get('awayGoals'))
            if pk not in seen_pairs:
                seen_pairs.add(pk)
                results.append(m)
        except Exception:
            pass

    results.sort(key=lambda m: int(m.get("finished_elapsed_sec") or 0))
    _LIVE_CACHE["ts"] = now_ts
    _LIVE_CACHE["items"] = results
    return list(results)




def _fpl_bps_to_rating(bps: int, goals: int, assists: int, clean_sheet: bool, yellows: int, reds: int, minutes: int) -> float:
    """تبدیل دقیق شاخص Opta BPS و آمار واقعی بازی به نمره ۶.۰ تا ۹.۹."""
    if minutes <= 0:
        return 6.0
    base = 6.0 + (bps / 15.0)
    base += goals * 0.45 + assists * 0.30 + (0.20 if clean_sheet and minutes >= 60 else 0.0)
    base -= yellows * 0.25 + reds * 1.4
    return round(max(4.5, min(9.8, base)), 1)


def _fetch_fpl_finished_24h_rated_matches(now_utc: datetime) -> list[dict[str, Any]]:
    """استخراج مسابقات پایان‌یافته ۲۴ ساعت اخیر لیگ برتر انگلیس از FPL Official API برای کارت نمرات بازیکنان."""
    try:
        boot = _http_get_json("https://fantasy.premierleague.com/api/bootstrap-static/", timeout=9.0)
        fixtures = _http_get_json("https://fantasy.premierleague.com/api/fixtures/", timeout=9.0)
    except Exception:
        return []
    if not isinstance(boot, dict) or not isinstance(fixtures, list):
        return []

    teams_by_id = {int(t["id"]): t for t in (boot.get("teams") or []) if isinstance(t, dict) and t.get("id") is not None}
    players_by_id = {int(e["id"]): e for e in (boot.get("elements") or []) if isinstance(e, dict) and e.get("id") is not None}
    out: list[dict[str, Any]] = []
    for fx in fixtures:
        if not isinstance(fx, dict) or not fx.get("finished"):
            continue
        ko_str = str(fx.get("kickoff_time") or "")
        ok_24h, elapsed = is_finished_within_24h(ko_str, now_utc=now_utc)
        if not ok_24h:
            continue
        ht, at = fx.get("team_h"), fx.get("team_a")
        hs, as_ = fx.get("team_h_score"), fx.get("team_a_score")
        if ht not in teams_by_id or at not in teams_by_id or hs is None or as_ is None:
            continue
        hs, as_ = int(hs), int(as_)
        h_obj, a_obj = teams_by_id[int(ht)], teams_by_id[int(at)]
        h_fa, h_code, h_col, h_sec = _resolve_club_meta(str(h_obj.get("name") or ""), str(h_obj.get("short_name") or ""))
        a_fa, a_code, a_col, a_sec = _resolve_club_meta(str(a_obj.get("name") or ""), str(a_obj.get("short_name") or ""))
        if h_col.upper() == a_col.upper():
            a_col = "#38BDF8"

        h_sc, a_sc = [], []
        for stat in fx.get("stats") or []:
            if isinstance(stat, dict) and stat.get("identifier") == "goals_scored":
                for e in stat.get("h") or []:
                    p = players_by_id.get(int(e.get("element") or 0)) or {}
                    h_sc.append(str(p.get("web_name") or ""))
                for e in stat.get("a") or []:
                    p = players_by_id.get(int(e.get("element") or 0)) or {}
                    a_sc.append(str(p.get("web_name") or ""))

        gw = int(fx.get("event") or 1)
        out.append({
            "id": f"fpl_pr_{fx.get('id')}",
            "is_live": True,
            "needs_summary_fetch": True,
            "provider": "fpl",
            "fpl_fixture_id": int(fx.get("id") or 0),
            "fpl_event": gw,
            "fpl_team_h": int(ht),
            "fpl_team_a": int(at),
            "finished_elapsed_sec": int(elapsed),
            "competition": "لیگ برتر انگلیس",
            "round": f"هفته {gw} • پایان مسابقه (۲۴ ساعت اخیر)",
            "leagueEn": "PREMIER LEAGUE",
            "season": "26/27",
            "weekCode": f"GW{gw}",
            "stadium": "لیگ برتر انگلیس",
            "statusTag": "پایان مسابقه • FT",
            "source": "Premier League / Opta FPL",
            "source_url": "https://fantasy.premierleague.com/",
            "homeGoals": hs,
            "awayGoals": as_,
            "homeXg": None,
            "awayXg": None,
            "homeScorers": "، ".join([x for x in h_sc if x]) or "—",
            "awayScorers": "، ".join([x for x in a_sc if x]) or "—",
            "home": {"name": h_fa, "code": h_code, "color": h_col, "secondary": h_sec, "formation": "4-3-3", "coach": "", "links": [], "xi": [], "subs": []},
            "away": {"name": a_fa, "code": a_code, "color": a_col, "secondary": a_sec, "formation": "4-3-3", "coach": "", "links": [], "xi": [], "subs": []},
            "verdict": None,
        })
    return out


def hydrate_fpl_match_ratings(item: dict[str, Any]) -> dict[str, Any]:
    """استخراج ترکیب ۱۱ نفره، تعویضی‌ها، xG واقعی تیم‌ها و نمرات Opta BPS از FPL Live Event API."""
    gw = item.get("fpl_event")
    ht = item.get("fpl_team_h")
    at = item.get("fpl_team_a")
    fx_id = item.get("fpl_fixture_id")
    if not (gw and ht and at):
        return item
    try:
        boot = _http_get_json("https://fantasy.premierleague.com/api/bootstrap-static/", timeout=9.0)
        live = _http_get_json(f"https://fantasy.premierleague.com/api/event/{int(gw)}/live/", timeout=9.0)
    except Exception:
        return item
    if not isinstance(boot, dict) or not isinstance(live, dict):
        return item

    el_meta = {int(e["id"]): e for e in (boot.get("elements") or []) if isinstance(e, dict) and e.get("id") is not None}
    pos_code_map = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}

    def _build_team_squad(team_id: int, is_home: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float]:
        played = []
        tot_xg = 0.0
        for le in live.get("elements") or []:
            if not isinstance(le, dict):
                continue
            eid = int(le.get("id") or 0)
            meta = el_meta.get(eid)
            if not meta or int(meta.get("team") or 0) != int(team_id):
                continue
            # Check if element played in this specific fixture (when explain is present)
            explains = le.get("explain") or []
            if fx_id and explains:
                if not any(int(ex.get("fixture") or 0) == int(fx_id) for ex in explains if isinstance(ex, dict)):
                    continue
            st = le.get("stats") or {}
            mins = int(st.get("minutes") or 0)
            if mins <= 0:
                continue
            bps = int(st.get("bps") or 0)
            goals = int(st.get("goals_scored") or 0)
            assists = int(st.get("assists") or 0)
            cs = bool(st.get("clean_sheets"))
            yc = int(st.get("yellow_cards") or 0)
            rc = int(st.get("red_cards") or 0)
            xg_v = float(st.get("expected_goals") or 0.0)
            tot_xg += xg_v
            rating = _fpl_bps_to_rating(bps, goals, assists, cs, yc, rc, mins)
            pos_id = int(meta.get("element_type") or 3)
            ev_list = (["G"] * goals) + (["A"] * assists) + (["YC"] * yc) + (["RC"] * rc)
            played.append({
                "name": str(meta.get("web_name") or meta.get("second_name") or ""),
                "num": str(meta.get("squad_number") or "") if meta.get("squad_number") else "",
                "pos": pos_code_map.get(pos_id, "MID"),
                "pos_id": pos_id,
                "mins": mins,
                "rating": rating,
                "events": ev_list,
                "goals": goals,
                "assists": assists,
                "xg": round(xg_v, 2),
                "bps": bps,
            })

        played.sort(key=lambda p: (p["mins"], p["bps"]), reverse=True)
        starters = played[:11]
        subs = played[11:16]

        # Assign clean tactical (x, y) pitch coordinates by position line
        by_pos: dict[int, list[dict[str, Any]]] = {1: [], 2: [], 3: [], 4: []}
        for p in starters:
            by_pos[p["pos_id"]].append(p)
        line_y = {1: 88, 2: 70, 3: 48, 4: 26} if is_home else {1: 12, 2: 30, 3: 52, 4: 74}
        xi_out = []
        for pid_line in (1, 2, 3, 4):
            grp = by_pos[pid_line]
            n = len(grp)
            for idx, p in enumerate(grp):
                x = 50 if n == 1 else int(16 + (68.0 * idx / max(1, n - 1)))
                xi_out.append({
                    "name": p["name"], "num": p["num"], "pos": p["pos"],
                    "rating": p["rating"], "x": x, "y": line_y[pid_line],
                    "events": p["events"], "mins": p["mins"],
                })
        subs_out = [
            {"name": p["name"], "pos": p["pos"], "rating": p["rating"], "mins": p["mins"], "events": p["events"]}
            for p in subs
        ]
        form_str = f"{len(by_pos[2])}-{len(by_pos[3])}-{len(by_pos[4])}" if len(starters) >= 10 else "4-3-3"
        return xi_out, subs_out, round(tot_xg, 2), form_str

    h_xi, h_subs, h_xg, h_form = _build_team_squad(int(ht), True)
    a_xi, a_subs, a_xg, a_form = _build_team_squad(int(at), False)
    out = json.loads(json.dumps(item))
    out["needs_summary_fetch"] = False
    if h_xi:
        out["home"]["xi"] = h_xi
        out["home"]["subs"] = h_subs
        out["home"]["formation"] = h_form
    if a_xi:
        out["away"]["xi"] = a_xi
        out["away"]["subs"] = a_subs
        out["away"]["formation"] = a_form
    if h_xg > 0 or a_xg > 0:
        out["homeXg"] = h_xg
        out["awayXg"] = a_xg
    return out


def hydrate_players_rating_match(item: dict[str, Any]) -> dict[str, Any]:
    """دریافت ترکیب ۱۱ نفره، تعویضی‌ها و نمرات واقعی هنگام انتخاب مسابقه در ربات."""
    if not item.get("needs_summary_fetch"):
        return item
    if item.get("provider") == "fpl":
        return hydrate_fpl_match_ratings(item)
    slug = str(item.get("espn_slug") or "")
    ev_id = str(item.get("espn_event_id") or "")
    if not (slug and ev_id):
        return item
    try:
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/summary?event={ev_id}"
        summary = _http_get_json(url, timeout=8.0)
        parsed = parse_espn_match_summary(
            summary,
            league_slug=slug,
            league_fa=str(item.get("competition") or "فوتبال"),
            league_en=str(item.get("leagueEn") or "FOOTBALL"),
            event_id=ev_id,
        )
        if parsed:
            return parsed
    except Exception:
        pass
    return item


def list_players_rating_items(
    *, include_live: bool = True, force_refresh: bool = False
) -> dict[str, list[dict[str, Any]]]:
    presets = load_players_rating_presets()
    live = fetch_live_rated_matches(force_refresh=force_refresh) if include_live else []
    return {"live": live, "presets": presets}


def enrich_players_rating_match(
    item: dict[str, Any],
    *,
    cancel_event: threading.Event | None = None,
    fetch_network: bool = True,
) -> dict[str, Any]:
    """تکمیل ترکیب واقعی (در صورت نیاز) و جمع‌بندی تحریریه فارسی با LLM (قانون null ≠ 0)."""
    base = hydrate_players_rating_match(item) if (fetch_network and item.get("needs_summary_fetch")) else item
    out = json.loads(json.dumps(base))
    if out.get("verdict") and (out["verdict"] or {}).get("body"):
        return out

    h = out.get("home") or {}
    a = out.get("away") or {}
    h_xi = h.get("xi") or []
    a_xi = a.get("xi") or []
    motm = max(h_xi + a_xi, key=lambda x: float(x.get("rating") or 0), default={})

    if fetch_network:
        try:
            from src.xgpedia.editorial.llm_provider import generate_text

            prompt = (
                "به‌عنوان سردبیر تحلیل فوتبال XGPedia، برای مسابقه زیر یک جمع‌بندی کوتاه فارسی در قالب JSON دقیق بنویس.\n"
                f"مسابقه: {h.get('name')} {out.get('homeGoals')}-{out.get('awayGoals')} {a.get('name')} ({out.get('competition')})\n"
                f"بهترین بازیکن زمین: {motm.get('name', '—')} با نمره {motm.get('rating', '—')}\n"
                f"گلزنان میزبان: {out.get('homeScorers', '—')} | گلزنان میهمان: {out.get('awayScorers', '—')}\n"
                'فقط JSON خالص با کلیدهای {"title": "تیتر کوتاه زیر ۵۵ کاراکتر", "body": "تحلیل دو جمله‌ای دقیق فارسی بدون ستاره و بدون حروف غیرفارسی", "tag": "برچسب کوتاه پایانی"}'
            )
            raw = generate_text(prompt, max_tokens=260, cancel_event=cancel_event)
            if raw:
                m = re.search(r"\{[\s\S]*\}", raw)
                if m:
                    parsed = json.loads(m.group(0))
                    if parsed.get("title") and parsed.get("body"):
                        out["verdict"] = {
                            "title": _clean_fa_text(parsed["title"])[:90],
                            "body": _clean_fa_text(parsed["body"])[:260],
                            "tag": _clean_fa_text(parsed.get("tag") or f"ستاره زمین: {motm.get('name', '')}")[:90],
                        }
                        return out
        except Exception:
            pass

    out["verdict"] = {
        "title": f"برتری آماری در نبرد {h.get('name', '')} و {a.get('name', '')}",
        "body": (
            f"در تقابل {h.get('name', '')} و {a.get('name', '')} با نتیجه {out.get('homeGoals', 0)}-{out.get('awayGoals', 0)}، "
            f"{motm.get('name', 'ستاره میدان')} با نمره {motm.get('rating', '—')} بالاترین اثرگذاری فنی را در زمین ثبت کرد."
        ),
        "tag": f"ستاره زمین (MOTM): {motm.get('name', '—')} ({motm.get('rating', '—')})",
    }
    return out
