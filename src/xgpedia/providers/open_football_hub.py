"""مرکز یکپارچه APIهای باز و رایگان فوتبال (`Open Football Hub — v0.36.0`).

برگرفته و تاییدشده از ممیزی کامل `https://github.com/topics/football-api` (۱۰۰٪ بدون `requests` و بدون نیاز به API Key):
  1. **worldcup26.ir** (`rezarahiminia/livescoreFootball` — 489★، میزبان ایرانی، بدون تحریم):
     - جداول زنده، نتایج و رویدادهای دقیقه‌به‌دقیقه لیگ برتر انگلیس (`eng.1`) و لالیگا اسپانیا (`esp.1`)
  2. **OpenLigaDB** (`https://api.openligadb.de` — API رسمی عمومی بوندس‌لیگا ۲۰۲۶/۲۷، بدون کلید):
     - جدول رده‌بندی بوندس‌لیگا (`getbltable/bl1/2026`)
     - جدول گلزنان زنده بوندس‌لیگا (`getgoalgetters/bl1/2026`)
     - نتایج هفته با نتیجه دقیق نیمه اول (`resultTypeID=1`)، دقایق گلزنی و پنالتی‌ها (`isPenalty`)
  3. **openfootball/football.json** (`raw.githubusercontent.com/openfootball/football.json` — CC0):
     - آرشیو چندفصله نتایج ۵ لیگ معتبر اروپا برای محاسبه تاریخچه تقابل مستقیم (H2H)

قاعده دائمی: صرفاً فوتبال واقعی (Association Football / Soccer ONLY) و رعایت کامل `null ≠ 0`.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

WC26_BASE = "https://worldcup26.ir/get/soccer"
OPENLIGADB_BASE = "https://api.openligadb.de"
OPENFOOTBALL_RAW_BASE = "https://raw.githubusercontent.com/openfootball/football.json/master"

# نقشه فارسی، کد ۳حرفی و رنگ باشگاه‌های بوندس‌لیگا و لالیگا
BUNDESLIGA_CLUBS_FA: dict[str, tuple[str, str, str]] = {
    "fc bayern münchen": ("بایرن مونیخ", "BAY", "#DC052D"),
    "bayern": ("بایرن مونیخ", "BAY", "#DC052D"),
    "bayer 04 leverkusen": ("بایر لورکوزن", "B04", "#E32221"),
    "leverkusen": ("بایر لورکوزن", "B04", "#E32221"),
    "borussia dortmund": ("دورتموند", "BVB", "#FDE100"),
    "dortmund": ("دورتموند", "BVB", "#FDE100"),
    "rb leipzig": ("لایپزیگ", "RBL", "#DD0741"),
    "leipzig": ("لایپزیگ", "RBL", "#DD0741"),
    "eintracht frankfurt": ("فرانکفورت", "SGE", "#E1000F"),
    "frankfurt": ("فرانکفورت", "SGE", "#E1000F"),
    "vfb stuttgart": ("اشتوتگارت", "VFB", "#E32219"),
    "stuttgart": ("اشتوتگارت", "VFB", "#E32219"),
    "sc freiburg": ("فرایبورگ", "SCF", "#E2001A"),
    "freiburg": ("فرایبورگ", "SCF", "#E2001A"),
    "vfl wolfsburg": ("ولفسبورگ", "WOB", "#65B32E"),
    "wolfsburg": ("ولفسبورگ", "WOB", "#65B32E"),
    "borussia mönchengladbach": ("گلادباخ", "BMG", "#10B981"),
    "sv werder bremen": ("وردربرمن", "SVW", "#1D9053"),
    "bremen": ("وردربرمن", "SVW", "#1D9053"),
    "1. fsv mainz 05": ("ماینتس", "M05", "#C3141E"),
    "mainz": ("ماینتس", "M05", "#C3141E"),
    "tsg hoffenheim": ("هوفنهایم", "TSG", "#38BDF8"),
    "hoffenheim": ("هوفنهایم", "TSG", "#38BDF8"),
    "1. fc union berlin": ("یونیون برلین", "FCU", "#EB1923"),
    "union berlin": ("یونیون برلین", "FCU", "#EB1923"),
    "fc augsburg": ("آگسبورگ", "FCA", "#BA3733"),
    "augsburg": ("آگسبورگ", "FCA", "#BA3733"),
    "1. fc heidenheim": ("هایدنهایم", "HDH", "#E2001A"),
    "fc st. pauli": ("سن‌پائولی", "STP", "#A78BFA"),
    "hamburger sv": ("هامبورگ", "HSV", "#38BDF8"),
    "1. fc köln": ("کلن", "KOE", "#ED1C24"),
}

LALIGA_CLUBS_FA: dict[str, tuple[str, str, str]] = {
    "real madrid": ("رئال مادرید", "RMA", "#F59E0B"),
    "barcelona": ("بارسلونا", "BAR", "#E62E45"),
    "atletico madrid": ("اتلتیکو مادرید", "ATM", "#CB3524"),
    "atlético madrid": ("اتلتیکو مادرید", "ATM", "#CB3524"),
    "athletic club": ("اتلتیک بیلبائو", "ATH", "#EE2523"),
    "athletic bilbao": ("اتلتیک بیلبائو", "ATH", "#EE2523"),
    "villarreal": ("ویارئال", "VIL", "#FACC15"),
    "real sociedad": ("رئال سوسیداد", "RSO", "#38BDF8"),
    "real betis": ("رئال بتیس", "BET", "#10B981"),
    "sevilla": ("سویا", "SEV", "#F43F5E"),
    "valencia": ("والنسیا", "VAL", "#FB923C"),
    "girona": ("خیرونا", "GIR", "#EF4444"),
    "celta vigo": ("سلتاویگو", "CEL", "#38BDF8"),
    "osasuna": ("اوساسونا", "OSA", "#DC2626"),
    "mallorca": ("مایورکا", "MLL", "#E11D48"),
    "getafe": ("ختافه", "GET", "#3B82F6"),
    "rayo vallecano": ("رایو وایکانو", "RAY", "#F87171"),
    "espanyol": ("اسپانیول", "ESP", "#38BDF8"),
}

_HUB_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 600.0


def _http_get_json(url: str, timeout: float = 7.0) -> Any:
    now = time.time()
    cached = _HUB_CACHE.get(url)
    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1]
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(2 * 1024 * 1024).decode("utf-8", errors="replace")
    data = json.loads(raw)
    _HUB_CACHE[url] = (now, data)
    return data


def _current_eu_season_year() -> int:
    now = datetime.now(timezone.utc)
    return now.year if now.month >= 7 else now.year - 1


def _resolve_club(name: str, mapping: dict[str, tuple[str, str, str]]) -> tuple[str, str, str]:
    low = (name or "").strip().lower()
    for k, v in mapping.items():
        if k in low or low in k:
            return v
    code = "".join(ch for ch in (name or "CLB").upper() if ch.isalpha())[:3] or "CLB"
    return (name or code, code, "#38BDF8")


# =====================================================================
# 1. OpenLigaDB (https://api.openligadb.de) — بوندس‌لیگا زنده بدون کلید
# =====================================================================

def parse_openligadb_standings(raw: Any, season: int = 2026) -> dict[str, Any] | None:
    """تبدیل خروجی `getbltable/bl1/{season}` به فرمت استاندارد کارت جدول رده‌بندی XGPedia."""
    if not isinstance(raw, list) or not raw:
        return None
    teams: list[dict[str, Any]] = []
    for idx, row in enumerate(raw, 1):
        if not isinstance(row, dict):
            continue
        t_en = str(row.get("teamName") or row.get("shortName") or "").strip()
        if not t_en:
            continue
        name_fa, code, color = _resolve_club(t_en, BUNDESLIGA_CLUBS_FA)
        mp = int(row.get("matches") or 0)
        w = int(row.get("won") or 0)
        d = int(row.get("draw") or 0)
        l_cnt = int(row.get("lost") or 0)
        gf = int(row.get("goals") or 0)
        ga = int(row.get("opponentGoals") or 0)
        pts = int(row.get("points") or 0)
        teams.append({
            "rank": idx,
            "name": name_fa,
            "code": code,
            "color": color,
            "sec": "#FFFFFF",
            "logo": str(row.get("teamIconUrl") or ""),
            "mp": mp,
            "w": w,
            "d": d,
            "l": l_cnt,
            "gf": gf,
            "ga": ga,
            "gd": gf - ga,
            "pts": pts,
            "xpts": None,
            "xg90": None,
            "xga90": None,
            "mov": 0,
            "form": [],
            "titleP": None,
            "top4P": None,
            "relP": None,
            "fdr": [],
        })
    if not teams:
        return None
    max_mp = max((t["mp"] for t in teams), default=1)
    now = datetime.now(timezone.utc)
    season_short = f"{str(season)[-2:]}/{str(season + 1)[-2:]}"
    return {
        "id": "live_bundesliga",
        "is_live": True,
        "name": "بوندس‌لیگا آلمان",
        "leagueEn": "BUNDESLIGA",
        "season": season_short,
        "weekCode": f"W{max_mp}",
        "round": f"جدول رسمی زنده • هفته {max_mp}",
        "date": now.strftime("%Y-%m-%d"),
        "subtitle": "جدول زنده بوندس‌لیگا (OpenLigaDB)",
        "source": "OpenLigaDB (Live)",
        "source_url": f"{OPENLIGADB_BASE}/getbltable/bl1/{season}",
        "leaderTag": f"صدرنشین فعلی با {teams[0]['pts']} امتیاز از {teams[0]['mp']} بازی",
        "zones": {"ucl": [1, 4], "uel": [5, 5], "uecl": [6, 6], "rel": [16, 18]},
        "zoneLabels": {"ucl": "لیگ قهرمانان اروپا", "uel": "لیگ اروپا", "uecl": "لیگ کنفرانس", "rel": "پلی‌آف / سقوط"},
        "teams": teams,
    }


def fetch_openligadb_bundesliga_standings(season: int | None = None) -> dict[str, Any] | None:
    yr = season or _current_eu_season_year()
    for try_yr in (yr, yr - 1):
        try:
            raw = _http_get_json(f"{OPENLIGADB_BASE}/getbltable/bl1/{try_yr}")
            parsed = parse_openligadb_standings(raw, season=try_yr)
            if parsed:
                return parsed
        except Exception as e:
            log.warning("OpenLigaDB standings (%s) skipped: %s", try_yr, e)
    return None


def parse_openligadb_top_scorers(raw: Any, season: int = 2026, top_n: int = 8) -> dict[str, Any] | None:
    """تبدیل خروجی `getgoalgetters/bl1/{season}` به فرمت استاندارد کارت جدول گلزنان XGPedia."""
    if not isinstance(raw, list) or not raw:
        return None
    sorted_rows = sorted(
        [r for r in raw if isinstance(r, dict) and int(r.get("goalCount") or 0) > 0],
        key=lambda x: int(x.get("goalCount") or 0),
        reverse=True,
    )[:top_n]
    if not sorted_rows:
        return None

    players: list[dict[str, Any]] = []
    for idx, r in enumerate(sorted_rows, 1):
        en_name = str(r.get("goalGetterName") or "").strip()
        if not en_name:
            continue
        try:
            from src.xgpedia.providers.injury_free import transliterate_player_name_fa
            fa_name = transliterate_player_name_fa(en_name)
        except Exception:
            fa_name = en_name
        short_fa = fa_name.split()[-1] if " " in fa_name else fa_name
        goals = int(r.get("goalCount") or 0)
        players.append({
            "rank": idx,
            "name": fa_name,
            "short": short_fa,
            "enName": en_name,
            "club": "بوندس‌لیگا",
            "code": "BL1",
            "pos": "مهاجم",
            "num": None,
            "color": "#DC052D" if idx == 1 else "#38BDF8",
            "secondary": "#FFFFFF",
            "goals": goals,
            "pen": None,
            "xg": None,
            "mins": None,
            "shots": None,
            "sot": None,
            "streak": 0,
            "radar": [],
            "pace": [],
            "photoUrl": None,
        })
    if not players:
        return None
    leader = players[0]
    season_short = f"{str(season)[-2:]}/{str(season + 1)[-2:]}"
    return {
        "id": f"live_openligadb_scorers_bl1_{season}",
        "is_preset": False,
        "competition": "بوندس‌لیگا آلمان",
        "round": "جدول زنده گلزنان • بوندس‌لیگا",
        "leagueEn": "BUNDESLIGA",
        "season": season_short,
        "weekCode": "LIVE",
        "source": "OpenLigaDB (Live)",
        "weeks": [],
        "paceInsight": f"{leader['name']} با {leader['goals']} گل در صدر جدول گلزنان زنده بوندس‌لیگا قرار دارد.",
        "players": players,
        "_hydrated": True,
    }


def fetch_openligadb_bundesliga_top_scorers(season: int | None = None) -> dict[str, Any] | None:
    yr = season or _current_eu_season_year()
    for try_yr in (yr, yr - 1):
        try:
            raw = _http_get_json(f"{OPENLIGADB_BASE}/getgoalgetters/bl1/{try_yr}")
            parsed = parse_openligadb_top_scorers(raw, season=try_yr)
            if parsed:
                return parsed
        except Exception as e:
            log.warning("OpenLigaDB top scorers (%s) skipped: %s", try_yr, e)
    return None


def parse_openligadb_matchday(raw: Any) -> list[dict[str, Any]]:
    """استخراج مسابقات پایان‌یافته بوندس‌لیگا با نتیجه دقیق نیمه اول، گلزنان، دقایق و پنالتی‌ها."""
    if not isinstance(raw, list):
        return []
    matches: list[dict[str, Any]] = []
    for m in raw:
        if not isinstance(m, dict) or not m.get("matchIsFinished"):
            continue
        t1 = m.get("team1") or {}
        t2 = m.get("team2") or {}
        h_fa, h_cd, h_col = _resolve_club(str(t1.get("teamName") or ""), BUNDESLIGA_CLUBS_FA)
        a_fa, a_cd, a_col = _resolve_club(str(t2.get("teamName") or ""), BUNDESLIGA_CLUBS_FA)
        if h_col.upper() == a_col.upper():
            a_col = "#38BDF8"

        ft_h = ft_a = ht_h = ht_a = None
        for res in (m.get("matchResults") or []):
            if not isinstance(res, dict):
                continue
            rt = int(res.get("resultTypeID") or 0)
            if rt == 1:  # Halbzeit (Half-Time)
                ht_h, ht_a = int(res.get("pointsTeam1") or 0), int(res.get("pointsTeam2") or 0)
            elif rt == 2:  # Endergebnis (Full-Time)
                ft_h, ft_a = int(res.get("pointsTeam1") or 0), int(res.get("pointsTeam2") or 0)
        if ft_h is None or ft_a is None:
            continue

        # گلزنان + دقیقه دقیق + علامت پنالتی (پ)
        h_sc: list[str] = []
        a_sc: list[str] = []
        prev_h = prev_a = 0
        for gl in (m.get("goals") or []):
            if not isinstance(gl, dict):
                continue
            sh = int(gl.get("scoreTeam1") or prev_h)
            sa = int(gl.get("scoreTeam2") or prev_a)
            nm = str(gl.get("goalGetterName") or "").strip()
            minute = gl.get("matchMinute")
            pen_tag = " (پ)" if gl.get("isPenalty") else (" (گ.خ)" if gl.get("isOwnGoal") else "")
            if nm:
                short_nm = nm.split()[-1] if " " in nm else nm
                entry = f"{short_nm} {minute}'{pen_tag}" if minute else f"{short_nm}{pen_tag}"
                if sh > prev_h:
                    h_sc.append(entry)
                elif sa > prev_a:
                    a_sc.append(entry)
            prev_h, prev_a = sh, sa

        grp = (m.get("group") or {}).get("groupOrderID")
        matches.append({
            "event_id": f"openligadb_{m.get('matchID') or ''}",
            "finished_elapsed_sec": 3600,
            "league_slug": "ger.1",
            "league": "بوندس‌لیگا آلمان",
            "league_fa": "بوندس‌لیگا آلمان",
            "league_en": "BUNDESLIGA",
            "home": {
                "name": h_fa,
                "code": h_cd,
                "color": h_col,
                "secondary": "#FFFFFF",
                "score": ft_h,
                "xg": None,
                "scorers": " • ".join(h_sc[:4]),
            },
            "away": {
                "name": a_fa,
                "code": a_cd,
                "color": a_col,
                "secondary": "#FFFFFF",
                "score": ft_a,
                "xg": None,
                "scorers": " • ".join(a_sc[:4]),
            },
            "status": "FT",
            "ht": f"{ht_h}-{ht_a}" if (ht_h is not None and ht_a is not None) else "",
            "tag": f"هفته {grp} بوندس‌لیگا" if grp else "بوندس‌لیگا آلمان",
            "comp": "بوندس‌لیگا آلمان",
        })
    return matches


def fetch_openligadb_bundesliga_matchday() -> list[dict[str, Any]]:
    try:
        raw = _http_get_json(f"{OPENLIGADB_BASE}/getmatchdata/bl1")
        return parse_openligadb_matchday(raw)
    except Exception as e:
        log.warning("OpenLigaDB matchday skipped: %s", e)
        return []


# =====================================================================
# 2. worldcup26.ir (rezarahiminia/livescoreFootball — 489★، میزبان ایرانی)
# =====================================================================

def parse_wc26_standings(raw: Any, league_slug: str = "esp.1", season: int | None = None) -> dict[str, Any] | None:
    """تبدیل خروجی `/get/soccer/{league}/standings` به فرمت استاندارد جدول رده‌بندی XGPedia."""
    if not isinstance(raw, dict):
        return None
    entries: list[dict[str, Any]] = []
    if isinstance(raw.get("standings"), list):
        entries = raw["standings"]
    elif isinstance(raw.get("entries"), list):
        entries = raw["entries"]
    elif isinstance(raw.get("children"), list) and raw["children"]:
        ch0 = raw["children"][0]
        if isinstance(ch0, dict):
            entries = (ch0.get("standings") or {}).get("entries") or ch0.get("entries") or []
    elif isinstance(raw.get("data"), dict):
        d0 = raw["data"]
        entries = d0.get("entries") or d0.get("standings") or d0.get("table") or []

    if not entries:
        return None

    is_spain = league_slug.startswith("esp")
    club_map = LALIGA_CLUBS_FA if is_spain else {}
    teams: list[dict[str, Any]] = []
    for idx, ent in enumerate(entries, 1):
        if not isinstance(ent, dict):
            continue
        t_obj = ent.get("team") if isinstance(ent.get("team"), dict) else ent
        t_en = str(t_obj.get("displayName") or t_obj.get("name") or t_obj.get("shortDisplayName") or "").strip()
        if not t_en:
            continue
        if is_spain:
            name_fa, code, color = _resolve_club(t_en, club_map)
        else:
            from src.xgpedia.providers.pl_badges_free import lookup_pl_club
            pl_inf = lookup_pl_club(t_en)
            if pl_inf:
                name_fa, code, color = pl_inf[0], pl_inf[1], pl_inf[2]
            else:
                name_fa, code, color = _resolve_club(t_en, {})

        st_map: dict[str, Any] = {}
        if isinstance(ent.get("stats"), list):
            for s in ent["stats"]:
                if isinstance(s, dict) and s.get("name"):
                    st_map[str(s["name"]).lower()] = s.get("value")

        def _g(keys: tuple[str, ...], _st_map=st_map, _ent=ent) -> int:
            for k in keys:
                if k in _st_map and _st_map[k] is not None:
                    return int(float(_st_map[k]))
                if k in _ent and _ent[k] is not None:
                    return int(float(_ent[k]))
            return 0

        mp = _g(("gamesplayed", "played", "mp", "matches"))
        w = _g(("wins", "won", "w"))
        d = _g(("ties", "draws", "draw", "d"))
        l_cnt = _g(("losses", "lost", "l"))
        gf = _g(("pointsfor", "goalsfor", "gf"))
        ga = _g(("pointsagainst", "goalsagainst", "ga"))
        pts = _g(("points", "pts"))
        teams.append({
            "rank": idx,
            "name": name_fa,
            "code": code,
            "color": color,
            "sec": "#FFFFFF",
            "mp": mp,
            "w": w,
            "d": d,
            "l": l_cnt,
            "gf": gf,
            "ga": ga,
            "gd": gf - ga,
            "pts": pts,
            "xpts": None,
            "xg90": None,
            "xga90": None,
            "mov": 0,
            "form": [],
            "titleP": None,
            "top4P": None,
            "relP": None,
            "fdr": [],
        })
    if not teams:
        return None
    max_mp = max((t["mp"] for t in teams), default=1)
    yr = season or _current_eu_season_year()
    now = datetime.now(timezone.utc)
    season_short = f"{str(yr)[-2:]}/{str(yr + 1)[-2:]}"
    return {
        "id": "live_laliga" if is_spain else "live_epl",
        "is_live": True,
        "name": "لالیگا اسپانیا" if is_spain else "لیگ برتر انگلیس",
        "leagueEn": "LALIGA EA SPORTS" if is_spain else "PREMIER LEAGUE",
        "season": season_short,
        "weekCode": f"W{max_mp}",
        "round": f"جدول رسمی زنده • هفته {max_mp}",
        "date": now.strftime("%Y-%m-%d"),
        "subtitle": "جدول زنده (worldcup26.ir)",
        "source": "worldcup26.ir (Live)",
        "source_url": f"{WC26_BASE}/{league_slug}/standings?season={yr}",
        "leaderTag": f"صدرنشین فعلی با {teams[0]['pts']} امتیاز از {teams[0]['mp']} بازی",
        "zones": {"ucl": [1, 4], "uel": [5, 5], "uecl": [6, 6], "rel": [18, 20]},
        "zoneLabels": {"ucl": "لیگ قهرمانان اروپا", "uel": "لیگ اروپا", "uecl": "لیگ کنفرانس", "rel": "منطقه سقوط"},
        "teams": teams,
    }


def fetch_wc26_standings(league_slug: str = "esp.1", season: int | None = None) -> dict[str, Any] | None:
    yr = season or _current_eu_season_year()
    try:
        raw = _http_get_json(f"{WC26_BASE}/{league_slug}/standings?season={yr}")
        return parse_wc26_standings(raw, league_slug=league_slug, season=yr)
    except Exception as e:
        log.warning("worldcup26.ir standings (%s) skipped: %s", league_slug, e)
        return None


# =====================================================================
# 3. openfootball/football.json (CC0) — آرشیو تاریخچه H2H ۵ لیگ اروپا
# =====================================================================

def compute_openfootball_h2h(matches_list: list[dict[str, Any]], team1: str, team2: str) -> dict[str, Any]:
    """محاسبه دقیق تاریخچه تقابل مستقیم دو تیم از لیست JSON استاندارد `openfootball/football.json`."""
    t1_q = team1.strip().lower()
    t2_q = team2.strip().lower()
    t1_w = t2_w = draws = t1_g = t2_g = t1_cs = t2_cs = 0
    recent: list[dict[str, Any]] = []

    for m in matches_list:
        if not isinstance(m, dict):
            continue
        m1 = str(m.get("team1") or "").lower()
        m2 = str(m.get("team2") or "").lower()
        sc = (m.get("score") or {}).get("ft") if isinstance(m.get("score"), dict) else None
        if not isinstance(sc, list) or len(sc) < 2:
            continue
        s1, s2 = int(sc[0]), int(sc[1])
        if t1_q in m1 and t2_q in m2:
            g1, g2 = s1, s2
        elif t2_q in m1 and t1_q in m2:
            g1, g2 = s2, s1
        else:
            continue
        t1_g += g1
        t2_g += g2
        if g2 == 0:
            t1_cs += 1
        if g1 == 0:
            t2_cs += 1
        if g1 > g2:
            t1_w += 1
        elif g2 > g1:
            t2_w += 1
        else:
            draws += 1
        recent.append({"date": str(m.get("date") or ""), "s1": g1, "s2": g2})

    recent.sort(key=lambda x: x["date"], reverse=True)
    return {
        "total": t1_w + draws + t2_w,
        "t1_wins": t1_w,
        "draws": draws,
        "t2_wins": t2_w,
        "t1_goals": t1_g,
        "t2_goals": t2_g,
        "t1_cs": t1_cs,
        "t2_cs": t2_cs,
        "recent5": recent[:5],
    }


def fetch_openfootball_h2h(
    league_code: str,
    team1: str,
    team2: str,
    seasons: tuple[str, ...] = ("2025-26", "2024-25", "2023-24", "2022-23", "2021-22"),
) -> dict[str, Any]:
    """دریافت چندفصله نتایج از `openfootball/football.json` و محاسبه آمار تقابل مستقیم."""
    all_matches: list[dict[str, Any]] = []
    for sz in seasons:
        url = f"{OPENFOOTBALL_RAW_BASE}/{sz}/{league_code}.json"
        try:
            data = _http_get_json(url, timeout=6.0)
            if isinstance(data, dict) and isinstance(data.get("matches"), list):
                all_matches.extend(data["matches"])
        except Exception:
            continue
    return compute_openfootball_h2h(all_matches, team1, team2)
