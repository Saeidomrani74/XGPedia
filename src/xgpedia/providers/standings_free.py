"""تأمین دادهٔ چندمنبعی و ۱۰۰٪ واقعی برای کارت ماژولار «جدول رده‌بندی» (Standings Studio — D52).

منابع رایگان (بدون وابستگی به `requests`، منحصراً Association Football / Soccer):
  1. Football-Data.org v4 (`api.football-data.org/v4/competitions/{code}/standings` در صورت وجود کلید رایگان در `.env`)
     — جدول رسمی زنده به‌همراه فرم دقیق ۵ بازی اخیر (`W,D,W,W,L`)
  2. ESPN Soccer Public Standings API (`site.api.espn.com/apis/v2/sports/soccer/{slug}/standings`)
     — جدول زندهٔ رایگان بدون نیاز به کلید API برای EPL، لالیگا، سری آ، بوندسلیگا، لیگ ۱ و UCL
  3. Understat (`understat.com/league/{slug}/{season}`) — استخراج واقعی `xPTS`, `xG/90`, `xGA/90` (با timeout کوتاه ۴.۵s)
  4. پریست‌های آماده (`config/standings_presets.json`).

قانون اکید داده‌های واقعی (`null ≠ 0`):
  - هیچ عدد شبیه‌سازی‌شده یا جعلی (از جمله شبیه‌سازی مونت‌کارلو ۱۰K) برای احتمال قهرمانی/سقوط تولید نمی‌شود.
  - اگر دیتای `xPTS`/`xG`/`xGA` واقعی از Understat موجود نباشد، مقدار `None` باقی می‌ماند.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.xgpedia.config import ROOT

PRESETS_PATH = ROOT / "config" / "standings_presets.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

STANDINGS_LEAGUE_SPECS: list[dict[str, Any]] = [
    {
        "id": "live_epl",
        "espn_slug": "eng.1",
        "understat_slug": "EPL",
        "fd_code": "PL",
        "name": "لیگ برتر انگلیس",
        "leagueEn": "PREMIER LEAGUE",
        "total_games": 38,
        "zones": {"ucl": [1, 4], "uel": [5, 5], "uecl": [6, 6], "rel": [18, 20]},
        "zoneLabels": {"ucl": "لیگ قهرمانان اروپا", "uel": "لیگ اروپا", "uecl": "لیگ کنفرانس", "rel": "منطقه سقوط"},
    },
    {
        "id": "live_laliga",
        "espn_slug": "esp.1",
        "understat_slug": "La_liga",
        "fd_code": "PD",
        "name": "لالیگا اسپانیا",
        "leagueEn": "LALIGA EA SPORTS",
        "total_games": 38,
        "zones": {"ucl": [1, 4], "uel": [5, 5], "uecl": [6, 6], "rel": [18, 20]},
        "zoneLabels": {"ucl": "لیگ قهرمانان اروپا", "uel": "لیگ اروپا", "uecl": "لیگ کنفرانس", "rel": "منطقه سقوط"},
    },
    {
        "id": "live_seriea",
        "espn_slug": "ita.1",
        "understat_slug": "Serie_A",
        "fd_code": "SA",
        "name": "سری آ ایتالیا",
        "leagueEn": "SERIE A",
        "total_games": 38,
        "zones": {"ucl": [1, 4], "uel": [5, 5], "uecl": [6, 6], "rel": [18, 20]},
        "zoneLabels": {"ucl": "لیگ قهرمانان اروپا", "uel": "لیگ اروپا", "uecl": "لیگ کنفرانس", "rel": "منطقه سقوط"},
    },
    {
        "id": "live_bundesliga",
        "espn_slug": "ger.1",
        "understat_slug": "Bundesliga",
        "fd_code": "BL1",
        "name": "بوندسلیگا آلمان",
        "leagueEn": "BUNDESLIGA",
        "total_games": 34,
        "zones": {"ucl": [1, 4], "uel": [5, 5], "uecl": [6, 6], "rel": [16, 18]},
        "zoneLabels": {"ucl": "لیگ قهرمانان اروپا", "uel": "لیگ اروپا", "uecl": "لیگ کنفرانس", "rel": "پلی‌آف / سقوط"},
    },
    {
        "id": "live_ligue1",
        "espn_slug": "fra.1",
        "understat_slug": "Ligue_1",
        "fd_code": "FL1",
        "name": "لیگ یک فرانسه",
        "leagueEn": "LIGUE 1",
        "total_games": 34,
        "zones": {"ucl": [1, 3], "uel": [4, 5], "uecl": [6, 6], "rel": [16, 18]},
        "zoneLabels": {"ucl": "لیگ قهرمانان اروپا", "uel": "لیگ اروپا", "uecl": "لیگ کنفرانس", "rel": "پلی‌آف / سقوط"},
    },
    {
        "id": "live_ucl",
        "espn_slug": "uefa.champions",
        "understat_slug": None,
        "fd_code": "CL",
        "name": "لیگ قهرمانان اروپا",
        "leagueEn": "UEFA CHAMPIONS LEAGUE",
        "total_games": 8,
        "zones": {"ucl": [1, 8], "uel": [9, 16], "uecl": [17, 24], "rel": [25, 36]},
        "zoneLabels": {"ucl": "صعود مستقیم یک‌هشتم", "uel": "پلی‌آف (سید)", "uecl": "پلی‌آف (غیرسید)", "rel": "حذف از اروپا"},
    },
    {
        "id": "live_uel",
        "espn_slug": "uefa.europa",
        "understat_slug": None,
        "fd_code": "EL",
        "name": "لیگ اروپا",
        "leagueEn": "UEFA EUROPA LEAGUE",
        "total_games": 8,
        "zones": {"ucl": [1, 8], "uel": [9, 16], "uecl": [17, 24], "rel": [25, 36]},
        "zoneLabels": {"ucl": "صعود مستقیم یک‌هشتم", "uel": "پلی‌آف (سید)", "uecl": "پلی‌آف (غیرسید)", "rel": "حذف از اروپا"},
    },
]

_TEAM_FA_MAP: dict[str, tuple[str, str, str, str]] = {
    "arsenal": ("آرسنال", "ARS", "#EF0107", "#FFFFFF"),
    "man city": ("منچسترسیتی", "MCI", "#38BDF8", "#FFFFFF"),
    "man utd": ("منچستریونایتد", "MUN", "#DA291C", "#FBE122"),
    "spurs": ("تاتنهام", "TOT", "#E2E8F0", "#132257"),
    "nott'm forest": ("ناتینگهام فارست", "NFO", "#E53233", "#FFFFFF"),
    "wolves": ("ولورهمپتون", "WOL", "#FDB913", "#231F20"),
    "leicester": ("لسترسیتی", "LEI", "#003090", "#FDBE11"),
    "ipswich": ("ایپسویچ", "IPS", "#3A64A3", "#FFFFFF"),
    "southampton": ("ساوتهمپتون", "SOU", "#D71920", "#FFFFFF"),
    "leeds": ("لیدز یونایتد", "LEE", "#FFCD00", "#1D428A"),
    "burnley": ("برنلی", "BUR", "#6C1D45", "#99D6EA"),
    "sunderland": ("ساندرلند", "SUN", "#EB172B", "#FFFFFF"),
    "liverpool": ("لیورپول", "LIV", "#C8102E", "#F6EB61"),
    "manchester city": ("منچسترسیتی", "MCI", "#38BDF8", "#FFFFFF"),
    "chelsea": ("چلسی", "CHE", "#2563EB", "#FFFFFF"),
    "aston villa": ("استون ویلا", "AVL", "#95BFE5", "#670E36"),
    "newcastle united": ("نیوکاسل", "NEW", "#CBD5E1", "#0F172A"),
    "newcastle": ("نیوکاسل", "NEW", "#CBD5E1", "#0F172A"),
    "tottenham hotspur": ("تاتنهام", "TOT", "#E2E8F0", "#132257"),
    "tottenham": ("تاتنهام", "TOT", "#E2E8F0", "#132257"),
    "manchester united": ("منچستریونایتد", "MUN", "#DA291C", "#FBE122"),
    "brighton": ("برایتون", "BHA", "#0057B8", "#FFCD00"),
    "nottingham forest": ("ناتینگهام فارست", "NFO", "#E53233", "#FFFFFF"),
    "fulham": ("فولام", "FUL", "#F8FAFC", "#CC0000"),
    "bournemouth": ("بورنموث", "BOU", "#DA291C", "#000000"),
    "brentford": ("برنتفورد", "BRE", "#E30613", "#FFFFFF"),
    "crystal palace": ("کریستال پالاس", "CRY", "#1B458F", "#C4122E"),
    "west ham": ("وستهام", "WHU", "#7A263A", "#1BB1E7"),
    "everton": ("اورتون", "EVE", "#003399", "#FFFFFF"),
    "wolverhampton": ("ولورهمپتون", "WOL", "#FDB913", "#231F20"),
    "barcelona": ("بارسلونا", "BAR", "#E62E45", "#004D98"),
    "real madrid": ("رئال مادرید", "RMA", "#F59E0B", "#FFFFFF"),
    "atletico madrid": ("اتلتیکو مادرید", "ATM", "#DC2626", "#FFFFFF"),
    "villarreal": ("ویارئال", "VIL", "#FACC15", "#005187"),
    "athletic club": ("اتلتیک بیلبائو", "ATH", "#EF4444", "#FFFFFF"),
    "real betis": ("رئال بتیس", "BET", "#10B981", "#FFFFFF"),
    "real sociedad": ("رئال سوسیداد", "RSO", "#0EA5E9", "#FFFFFF"),
    "inter": ("اینتر میلان", "INT", "#1D4ED8", "#0F172A"),
    "napoli": ("ناپولی", "NAP", "#38BDF8", "#FFFFFF"),
    "atalanta": ("آتالانتا", "ATA", "#2563EB", "#000000"),
    "juventus": ("یوونتوس", "JUV", "#F8FAFC", "#0F172A"),
    "ac milan": ("آث میلان", "ACM", "#DC2626", "#111827"),
    "bayern munich": ("بایرن مونیخ", "BAY", "#DC2626", "#FFFFFF"),
    "bayer leverkusen": ("بایر لورکوزن", "LEV", "#E32221", "#111827"),
    "borussia dortmund": ("دورتموند", "BVB", "#FACC15", "#0F172A"),
    "paris saint-germain": ("پاری سن ژرمن", "PSG", "#1D4ED8", "#E62E45"),
    "marseille": ("مارسی", "OM", "#38BDF8", "#FFFFFF"),
    "monaco": ("موناکو", "MON", "#E62E45", "#FFFFFF"),
}

_LIVE_CACHE: dict[str, Any] = {"ts": 0.0, "items": []}
_CACHE_TTL_SEC = 600.0


def _http_get(url: str, headers: dict[str, str] | None = None, timeout: float = 7.0) -> str:
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json,text/html,*/*"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _resolve_team(raw_name: str, abbr: str = "", color: str = "") -> tuple[str, str, str, str]:
    low = (raw_name or "").strip().lower()
    for k, v in _TEAM_FA_MAP.items():
        if k == low or k in low:
            return v
    code = re.sub(r"[^A-Za-z]", "", abbr or raw_name or "FC").upper()[:3] or "FC"
    col = f"#{color.lstrip('#')}" if color and len(color.lstrip("#")) == 6 else "#38BDF8"
    return (raw_name or code, code, col, "#FFFFFF")


def load_standings_presets() -> list[dict[str, Any]]:
    if not PRESETS_PATH.exists():
        return []
    try:
        data = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        out: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            cp = dict(item)
            cp["is_preset"] = True
            cp["source"] = "نمونه استودیو • XGPedia Sample"
            out.append(cp)
        return out
    except Exception as _em_exc:
        from src.xgpedia.core.error_metrics import record_error as _rec_err
        _rec_err("provider.standings", _em_exc)
        return []


def fetch_understat_league_xg(understat_slug: str, season_year: int) -> dict[str, dict[str, float]]:
    """استخراج واقعی xPTS، xG/90 و xGA/90 از Understat با timeout کوتاه."""
    if not understat_slug:
        return {}
    url = f"https://understat.com/league/{understat_slug}/{season_year}"
    try:
        html_txt = _http_get(url, timeout=4.5)
        m = re.search(r"teamsData\s*=\s*JSON\.parse\('([^']+)'\)", html_txt)
        if not m:
            return {}
        decoded = m.group(1).encode("utf-8").decode("unicode_escape")
        data = json.loads(decoded)
        out: dict[str, dict[str, float]] = {}
        for _, tobj in (data.items() if isinstance(data, dict) else []):
            title = str(tobj.get("title") or "").strip().lower()
            hist = tobj.get("history") or []
            if not title or not hist:
                continue
            mp = len(hist)
            out[title] = {
                "xpts": round(sum(float(h.get("xpts") or 0.0) for h in hist), 1),
                "xg90": round(sum(float(h.get("xG") or 0.0) for h in hist) / mp, 2),
                "xga90": round(sum(float(h.get("xGA") or 0.0) for h in hist) / mp, 2),
                "form": [str(h.get("result") or "").upper() for h in hist[-5:] if str(h.get("result") or "").upper() in ("W", "D", "L")],
            }
        return out
    except Exception as _em_exc:
        from src.xgpedia.core.error_metrics import record_error as _rec_err
        _rec_err("provider.standings", _em_exc)
        return {}


def _match_understat(umap: dict[str, dict[str, Any]], raw_name: str) -> dict[str, Any] | None:
    low = raw_name.lower()
    if low in umap:
        return umap[low]
    for uk, uv in umap.items():
        if uk in low or low in uk:
            return uv
    return None


def parse_football_data_standings(
    payload: dict[str, Any],
    spec: dict[str, Any],
    *,
    understat_map: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """پارس جدول رسمی از Football-Data.org v4 (شامل فرم واقعی ۵ بازی)."""
    if not isinstance(payload, dict):
        return None
    standings = payload.get("standings") or []
    total_tbl = next((s for s in standings if isinstance(s, dict) and s.get("type") == "TOTAL"), standings[0] if standings else None)
    if not isinstance(total_tbl, dict):
        return None
    table = total_tbl.get("table") or []
    if not table:
        return None
    umap = understat_map or {}
    teams: list[dict[str, Any]] = []
    for row in table:
        if not isinstance(row, dict):
            continue
        tobj = row.get("team") or {}
        raw_name = str(tobj.get("shortName") or tobj.get("name") or "").strip()
        if not raw_name:
            continue
        t_fa, t_code, t_col, t_sec = _resolve_team(raw_name, str(tobj.get("tla") or ""))
        u_hit = _match_understat(umap, str(tobj.get("name") or raw_name))
        raw_form = re.sub(r"[^WDL]", "", str(row.get("form") or "").upper())[-5:]
        form = list(raw_form) if raw_form else (u_hit.get("form", []) if u_hit else [])
        teams.append({
            "rank": int(row.get("position") or len(teams) + 1),
            "name": t_fa,
            "code": t_code,
            "color": t_col,
            "sec": t_sec,
            "mp": int(row.get("playedGames") or 0),
            "w": int(row.get("won") or 0),
            "d": int(row.get("draw") or 0),
            "l": int(row.get("lost") or 0),
            "gf": int(row.get("goalsFor") or 0),
            "ga": int(row.get("goalsAgainst") or 0),
            "pts": int(row.get("points") or 0),
            "xpts": u_hit["xpts"] if u_hit else None,
            "xg90": u_hit["xg90"] if u_hit else None,
            "xga90": u_hit["xga90"] if u_hit else None,
            "mov": 0,
            "form": form,
            "titleP": None,
            "top4P": None,
            "relP": None,
            "fdr": [],
        })
    if not teams:
        return None
    max_mp = max((t["mp"] for t in teams), default=1)
    now = datetime.now(timezone.utc)
    season_yr = now.year if now.month >= 7 else now.year - 1
    season_str = f"{str(season_yr)[-2:]}/{str(season_yr + 1)[-2:]}"
    has_xg = any(t.get("xpts") is not None for t in teams)
    return {
        "id": spec["id"],
        "is_live": True,
        "name": spec["name"],
        "leagueEn": spec["leagueEn"],
        "season": season_str,
        "weekCode": f"W{max_mp}",
        "round": f"جدول رسمی • هفته {max_mp}",
        "date": now.strftime("%Y-%m-%d"),
        "subtitle": "جدول زنده و رسمی" + (" + داده‌های واقعی xG/xPTS" if has_xg else ""),
        "source": "Football-Data.org / Understat" if has_xg else "Football-Data.org",
        "source_url": "https://www.football-data.org/",
        "leaderTag": f"صدرنشین فعلی با {teams[0]['pts']} امتیاز از {teams[0]['mp']} بازی",
        "zones": spec["zones"],
        "zoneLabels": spec["zoneLabels"],
        "teams": teams,
    }


def parse_espn_standings(
    payload: dict[str, Any],
    spec: dict[str, Any],
    *,
    understat_map: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """پارس جدول زنده از ESPN Soccer Standings JSON بدون هیچ عدد شبیه‌سازی‌شده."""
    if not isinstance(payload, dict):
        return None
    entries: list[dict[str, Any]] = []
    children = payload.get("children") or []
    if children and isinstance(children[0], dict):
        entries = ((children[0].get("standings") or {}).get("entries")) or []
    if not entries and isinstance(payload.get("standings"), dict):
        entries = payload["standings"].get("entries") or []
    if not entries:
        return None

    umap = understat_map or {}
    teams: list[dict[str, Any]] = []
    for ent in entries:
        if not isinstance(ent, dict):
            continue
        tobj = ent.get("team") or {}
        raw_name = str(tobj.get("displayName") or tobj.get("name") or "").strip()
        if not raw_name:
            continue
        t_fa, t_code, t_col, t_sec = _resolve_team(
            raw_name, str(tobj.get("abbreviation") or ""), str(tobj.get("color") or "")
        )
        stats: dict[str, Any] = {}
        for st in ent.get("stats") or []:
            if isinstance(st, dict) and st.get("name"):
                stats[str(st["name"])] = st.get("value")
                if st.get("name") in ("form", "lastFive") or st.get("type") == "form":
                    stats["form_str"] = str(st.get("displayValue") or "")

        mp = int(stats.get("gamesPlayed") or 0)
        w = int(stats.get("wins") or 0)
        d = int(stats.get("ties") or stats.get("draws") or 0)
        l = int(stats.get("losses") or 0)
        gf = int(stats.get("pointsFor") or stats.get("goalsFor") or 0)
        ga = int(stats.get("pointsAgainst") or stats.get("goalsAgainst") or 0)
        pts = int(stats.get("points") or (w * 3 + d))
        u_hit = _match_understat(umap, raw_name)
        raw_form = re.sub(r"[^WDL]", "", str(stats.get("form_str") or "").upper())[-5:]
        form = list(raw_form) if raw_form else (u_hit.get("form", []) if u_hit else [])

        teams.append({
            "name": t_fa,
            "code": t_code,
            "color": t_col,
            "sec": t_sec,
            "mp": mp,
            "w": w,
            "d": d,
            "l": l,
            "gf": gf,
            "ga": ga,
            "pts": pts,
            "xpts": u_hit["xpts"] if u_hit else None,
            "xg90": u_hit["xg90"] if u_hit else None,
            "xga90": u_hit["xga90"] if u_hit else None,
            "mov": 0,
            "form": form,
            "titleP": None,
            "top4P": None,
            "relP": None,
            "fdr": [],
        })

    if not teams:
        return None
    teams.sort(key=lambda t: (t["pts"], t["gf"] - t["ga"], t["gf"]), reverse=True)
    for idx, t in enumerate(teams, 1):
        t["rank"] = idx

    max_mp = max((t["mp"] for t in teams), default=1)
    now = datetime.now(timezone.utc)
    season_yr = now.year if now.month >= 7 else now.year - 1
    season_str = f"{str(season_yr)[-2:]}/{str(season_yr + 1)[-2:]}"
    has_xg = any(t.get("xpts") is not None for t in teams)

    return {
        "id": spec["id"],
        "is_live": True,
        "name": spec["name"],
        "leagueEn": spec["leagueEn"],
        "season": season_str,
        "weekCode": f"W{max_mp}",
        "round": f"جدول زنده • هفته {max_mp}",
        "date": now.strftime("%Y-%m-%d"),
        "subtitle": "جدول زنده و رسمی" + (" + داده‌های واقعی xG/xPTS" if has_xg else ""),
        "source": "ESPN Soccer / Understat" if has_xg else "ESPN Soccer",
        "source_url": f"https://www.espn.com/soccer/table/_/league/{spec['espn_slug']}",
        "leaderTag": f"صدرنشین فعلی با {teams[0]['pts']} امتیاز از {teams[0]['mp']} بازی",
        "zones": spec["zones"],
        "zoneLabels": spec["zoneLabels"],
        "teams": teams,
    }




def fetch_fpl_premier_league_standings(
    spec: dict[str, Any],
    *,
    understat_map: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """ساخت جدول ۱۰۰٪ واقعی و لحظه‌ای لیگ برتر انگلیس از FPL Official API (بدون کلید و بدون محدودیت ۲۴ ساعته)."""
    try:
        boot = json.loads(_http_get("https://fantasy.premierleague.com/api/bootstrap-static/", timeout=9.0))
        fixtures = json.loads(_http_get("https://fantasy.premierleague.com/api/fixtures/", timeout=9.0))
    except Exception as _em_exc:
        from src.xgpedia.core.error_metrics import record_error as _rec_err
        _rec_err("provider.standings", _em_exc)
        return None
    if not isinstance(boot, dict) or not isinstance(fixtures, list):
        return None

    teams_raw = boot.get("teams") or []
    if not teams_raw:
        return None

    stats: dict[int, dict[str, Any]] = {}
    for tobj in teams_raw:
        if not isinstance(tobj, dict) or tobj.get("id") is None:
            continue
        tid = int(tobj["id"])
        raw_name = str(tobj.get("name") or "")
        short_code = str(tobj.get("short_name") or "")
        t_fa, t_code, t_col, t_sec = _resolve_team(raw_name, short_code)
        stats[tid] = {
            "raw_name": raw_name,
            "name": t_fa,
            "code": t_code,
            "color": t_col,
            "sec": t_sec,
            "mp": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "pts": 0,
            "results": [],  # list of (kickoff_str, 'W'|'D'|'L')
        }

    for fx in fixtures:
        if not isinstance(fx, dict) or not fx.get("finished"):
            continue
        ht, at = fx.get("team_h"), fx.get("team_a")
        hs, as_ = fx.get("team_h_score"), fx.get("team_a_score")
        if ht not in stats or at not in stats or hs is None or as_ is None:
            continue
        hs, as_ = int(hs), int(as_)
        ko = str(fx.get("kickoff_time") or "")
        sh, sa = stats[int(ht)], stats[int(at)]
        sh["mp"] += 1; sa["mp"] += 1
        sh["gf"] += hs; sh["ga"] += as_
        sa["gf"] += as_; sa["ga"] += hs
        if hs > as_:
            sh["w"] += 1; sh["pts"] += 3; sh["results"].append((ko, "W"))
            sa["l"] += 1; sa["results"].append((ko, "L"))
        elif hs < as_:
            sa["w"] += 1; sa["pts"] += 3; sa["results"].append((ko, "W"))
            sh["l"] += 1; sh["results"].append((ko, "L"))
        else:
            sh["d"] += 1; sh["pts"] += 1; sh["results"].append((ko, "D"))
            sa["d"] += 1; sa["pts"] += 1; sa["results"].append((ko, "D"))

    umap = understat_map or {}
    teams: list[dict[str, Any]] = []
    for rec in stats.values():
        rec["results"].sort(key=lambda x: x[0])
        form = [r for _, r in rec["results"][-5:]]
        u_hit = _match_understat(umap, rec["raw_name"])
        teams.append({
            "rank": 1,
            "name": rec["name"],
            "code": rec["code"],
            "color": rec["color"],
            "sec": rec["sec"],
            "mp": rec["mp"],
            "w": rec["w"],
            "d": rec["d"],
            "l": rec["l"],
            "gf": rec["gf"],
            "ga": rec["ga"],
            "pts": rec["pts"],
            "xpts": u_hit["xpts"] if u_hit else None,
            "xg90": u_hit["xg90"] if u_hit else None,
            "xga90": u_hit["xga90"] if u_hit else None,
            "mov": 0,
            "form": form,
            "titleP": None,
            "top4P": None,
            "relP": None,
            "fdr": [],
        })

    teams.sort(key=lambda t: (t["pts"], t["gf"] - t["ga"], t["gf"], t["name"]), reverse=True)
    for idx, t in enumerate(teams, 1):
        t["rank"] = idx

    max_mp = max((t["mp"] for t in teams), default=1)
    now = datetime.now(timezone.utc)
    season_yr = now.year if now.month >= 7 else now.year - 1
    season_str = f"{str(season_yr)[-2:]}/{str(season_yr + 1)[-2:]}"
    has_xg = any(t.get("xpts") is not None for t in teams)
    return {
        "id": spec["id"],
        "is_live": True,
        "name": spec["name"],
        "leagueEn": spec["leagueEn"],
        "season": season_str,
        "weekCode": f"W{max_mp}",
        "round": f"جدول رسمی زنده • هفته {max_mp}",
        "date": now.strftime("%Y-%m-%d"),
        "subtitle": "جدول لحظه‌ای و رسمی" + (" + داده‌های واقعی xG/xPTS" if has_xg else ""),
        "source": "Premier League / FPL Official" + (" & Understat" if has_xg else ""),
        "source_url": "https://fantasy.premierleague.com/",
        "leaderTag": f"صدرنشین فعلی با {teams[0]['pts']} امتیاز از {teams[0]['mp']} بازی",
        "zones": spec["zones"],
        "zoneLabels": spec["zoneLabels"],
        "teams": teams,
    }


def fetch_live_standings(force_refresh: bool = False) -> list[dict[str, Any]]:
    """دریافت موازی و سریع جدول‌های واقعی از Football-Data.org (در صورت وجود کلید) و ESPN Soccer + Understat."""
    now = time.time()
    if not force_refresh and _LIVE_CACHE["items"] and (now - _LIVE_CACHE["ts"]) < _CACHE_TTL_SEC:
        return list(_LIVE_CACHE["items"])

    dt = datetime.now(timezone.utc)
    season_yr = dt.year if dt.month >= 7 else dt.year - 1
    fd_key = (os.getenv("FOOTBALL_DATA_API_KEY") or "").strip()

    def _fetch_one(spec: dict[str, Any]) -> dict[str, Any] | None:
        umap = fetch_understat_league_xg(spec["understat_slug"], season_yr) if spec.get("understat_slug") else {}
        if fd_key and spec.get("fd_code"):
            try:
                fd_url = f"https://api.football-data.org/v4/competitions/{spec['fd_code']}/standings"
                payload = json.loads(_http_get(fd_url, headers={"X-Auth-Token": fd_key}, timeout=7.0))
                parsed = parse_football_data_standings(payload, spec, understat_map=umap)
                if parsed:
                    return parsed
            except Exception as _em_exc:
                from src.xgpedia.core.error_metrics import record_error as _rec_err
                _rec_err("provider.standings", _em_exc)
        if spec.get("espn_slug") == "eng.1":
            fpl_tbl = fetch_fpl_premier_league_standings(spec, understat_map=umap)
            if fpl_tbl:
                return fpl_tbl
        try:
            espn_url = f"https://site.api.espn.com/apis/v2/sports/soccer/{spec['espn_slug']}/standings"
            payload = json.loads(_http_get(espn_url, timeout=7.0))
            parsed = parse_espn_standings(payload, spec, understat_map=umap)
            if parsed:
                return parsed
        except Exception as _em_exc:
            from src.xgpedia.core.error_metrics import record_error as _rec_err
            _rec_err("provider.standings", _em_exc)
        # Fallbackهای رایگان تاییدشده از Open Football Hub (v0.36.0 — بدون نیاز به کلید)
        try:
            from src.xgpedia.providers.open_football_hub import (
                fetch_openligadb_bundesliga_standings,
                fetch_wc26_standings,
            )
            if spec.get("espn_slug") == "ger.1":
                bl = fetch_openligadb_bundesliga_standings(season=season_yr)
                if bl:
                    return bl
            elif spec.get("espn_slug") in ("esp.1", "eng.1"):
                wc = fetch_wc26_standings(league_slug=spec["espn_slug"], season=season_yr)
                if wc:
                    return wc
        except Exception as _em_exc:
            from src.xgpedia.core.error_metrics import record_error as _rec_err
            _rec_err("provider.standings", _em_exc)
        return None

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for res in ex.map(_fetch_one, STANDINGS_LEAGUE_SPECS):
            if res:
                results.append(res)

    _LIVE_CACHE["ts"] = now
    _LIVE_CACHE["items"] = results
    return list(results)


def list_standings_leagues(
    *, include_live: bool = True, force_refresh: bool = False
) -> dict[str, list[dict[str, Any]]]:
    presets = load_standings_presets()
    live = fetch_live_standings(force_refresh=force_refresh) if include_live else []
    return {"live": live, "presets": presets}


def enrich_standings_league(item: dict[str, Any], *, fetch_network: bool = True) -> dict[str, Any]:
    out = json.loads(json.dumps(item))
    teams = out.get("teams") or []
    teams.sort(key=lambda t: (t.get("pts") or 0, (t.get("gf") or 0) - (t.get("ga") or 0), t.get("gf") or 0), reverse=True)
    for idx, t in enumerate(teams, 1):
        t["rank"] = idx
    out["teams"] = teams
    return out
