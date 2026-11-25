"""لوگوهای رسمی باشگاه‌های لیگ برتر انگلیس (Premier League Official Badges) و تضمین کنتراست رنگ تیم‌ها.

منبع ۱۰۰٪ رایگان و بدون کلید API:
  - `https://resources.premierleague.com/premierleague/badges/70/t{team_code}.png`
  - ذخیره کش روی دیسک (`output/.badge_cache/`) و تبدیل به `data:image/png;base64,...` برای رندر ۱۰۰٪ آفلاین در Playwright.
"""
from __future__ import annotations

import base64
import math
import urllib.request
from pathlib import Path
from typing import Any

from src.xgpedia.config import ROOT

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
BADGE_CACHE_DIR = ROOT / "output" / ".badge_cache"

# نقشه جامع باشگاه‌های لیگ برتر انگلیس:
# key -> (name_fa, tla, primary_hex, secondary_hex, pl_badge_code)
PL_CLUBS_MASTER: dict[str, tuple[str, str, str, str, int]] = {
    "arsenal": ("آرسنال", "ARS", "#EF0107", "#FFFFFF", 3),
    "aston villa": ("استون ویلا", "AVL", "#95BFE5", "#670E36", 7),
    "bournemouth": ("بورنموث", "BOU", "#DA291C", "#111827", 91),
    "afc bournemouth": ("بورنموث", "BOU", "#DA291C", "#111827", 91),
    "brentford": ("برنتفورد", "BRE", "#E30613", "#FFFFFF", 94),
    "brighton": ("برایتون", "BHA", "#0057B8", "#FFCD00", 36),
    "brighton & hove albion": ("برایتون", "BHA", "#0057B8", "#FFCD00", 36),
    "burnley": ("برنلی", "BUR", "#6C1D45", "#99D6EA", 90),
    "chelsea": ("چلسی", "CHE", "#2563EB", "#FFFFFF", 8),
    "crystal palace": ("کریستال پالاس", "CRY", "#1B458F", "#C4122E", 31),
    "everton": ("اورتون", "EVE", "#2563EB", "#FFFFFF", 11),
    "fulham": ("فولام", "FUL", "#F8FAFC", "#CC0000", 54),
    "ipswich": ("ایپسویچ", "IPS", "#3A64A3", "#FFFFFF", 40),
    "ipswich town": ("ایپسویچ", "IPS", "#3A64A3", "#FFFFFF", 40),
    "leeds": ("لیدز یونایتد", "LEE", "#FACC15", "#1D428A", 2),
    "leeds united": ("لیدز یونایتد", "LEE", "#FACC15", "#1D428A", 2),
    "leicester": ("لسترسیتی", "LEI", "#0053A0", "#FDBE11", 13),
    "leicester city": ("لسترسیتی", "LEI", "#0053A0", "#FDBE11", 13),
    "liverpool": ("لیورپول", "LIV", "#C8102E", "#F6EB61", 14),
    "man city": ("منچسترسیتی", "MCI", "#38BDF8", "#FFFFFF", 43),
    "manchester city": ("منچسترسیتی", "MCI", "#38BDF8", "#FFFFFF", 43),
    "man utd": ("منچستریونایتد", "MUN", "#DA291C", "#FBE122", 1),
    "manchester united": ("منچستریونایتد", "MUN", "#DA291C", "#FBE122", 1),
    "newcastle": ("نیوکاسل", "NEW", "#CBD5E1", "#0F172A", 4),
    "newcastle united": ("نیوکاسل", "NEW", "#CBD5E1", "#0F172A", 4),
    "nott'm forest": ("ناتینگهام فارست", "NFO", "#E53233", "#FFFFFF", 17),
    "nottingham forest": ("ناتینگهام فارست", "NFO", "#E53233", "#FFFFFF", 17),
    "southampton": ("ساوتهمپتون", "SOU", "#D71920", "#FFFFFF", 20),
    "spurs": ("تاتنهام", "TOT", "#E2E8F0", "#132257", 6),
    "tottenham": ("تاتنهام", "TOT", "#E2E8F0", "#132257", 6),
    "tottenham hotspur": ("تاتنهام", "TOT", "#E2E8F0", "#132257", 6),
    "sunderland": ("ساندرلند", "SUN", "#EB172B", "#FFFFFF", 56),
    "west ham": ("وستهام", "WHU", "#9F1239", "#38BDF8", 21),
    "west ham united": ("وستهام", "WHU", "#9F1239", "#38BDF8", 21),
    "wolves": ("ولورهمپتون", "WOL", "#FDB913", "#231F20", 39),
    "wolverhampton": ("ولورهمپتون", "WOL", "#FDB913", "#231F20", 39),
    "wolverhampton wanderers": ("ولورهمپتون", "WOL", "#FDB913", "#231F20", 39),
}

_BY_TLA: dict[str, tuple[str, str, str, str, int]] = {v[1]: v for v in PL_CLUBS_MASTER.values()}
_BY_FA: dict[str, tuple[str, str, str, str, int]] = {v[0]: v for v in PL_CLUBS_MASTER.values()}
_MEM_CACHE: dict[int, str] = {}


def lookup_pl_club(name_or_tla: str, tla_hint: str = "") -> tuple[str, str, str, str, int] | None:
    s = str(name_or_tla or "").strip()
    if s in _BY_FA:
        return _BY_FA[s]
    low = s.lower()
    if low in PL_CLUBS_MASTER:
        return PL_CLUBS_MASTER[low]
    t = str(tla_hint or "").strip().upper()
    if t in _BY_TLA:
        return _BY_TLA[t]
    for k, v in PL_CLUBS_MASTER.items():
        if k in low or low in k:
            return v
    return None


def get_pl_badge_data_uri(name_or_tla: str, *, tla_hint: str = "", badge_code: int | None = None, fetch_network: bool = True) -> str | None:
    """دریافت لوگوی رسمی باشگاه لیگ برتر به‌صورت data URI (با کش حافظه و دیسک)."""
    code = badge_code
    if code is None:
        hit = lookup_pl_club(name_or_tla, tla_hint)
        if hit:
            code = hit[4]
    if not code:
        return None
    if code in _MEM_CACHE:
        return _MEM_CACHE[code]

    try:
        BADGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_f = BADGE_CACHE_DIR / f"pl_t{code}.png"
        if cache_f.exists() and cache_f.stat().st_size > 500:
            raw = cache_f.read_bytes()
            uri = f"data:image/png;base64,{base64.b64encode(raw).decode('ascii')}"
            _MEM_CACHE[code] = uri
            return uri
        if not fetch_network:
            return None
        for sz in ("100", "70"):
            url = f"https://resources.premierleague.com/premierleague/badges/{sz}/t{code}.png"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    raw = resp.read()
                if len(raw) > 500 and raw[:4] == b"\x89PNG":
                    cache_f.write_bytes(raw)
                    uri = f"data:image/png;base64,{base64.b64encode(raw).decode('ascii')}"
                    _MEM_CACHE[code] = uri
                    return uri
            except Exception:
                continue
    except Exception:
        pass
    return None


def _hex_to_rgb(hex_col: str) -> tuple[int, int, int]:
    c = (hex_col or "#38BDF8").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        n = int(c[:6], 16)
        return ((n >> 16) & 255, (n >> 8) & 255, n & 255)
    except ValueError:
        return (56, 189, 248)


def resolve_distinct_team_colors(home_hex: str, away_hex: str) -> tuple[str, str]:
    """تضمین تمایز و کنتراست واضح میان رنگ دو تیم روی پس‌زمینه تیره XGPedia."""
    hc = home_hex or "#E62E45"
    ac = away_hex or "#38BDF8"
    r1, g1, b1 = _hex_to_rgb(hc)
    r2, g2, b2 = _hex_to_rgb(ac)
    dist = math.sqrt((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2)
    if dist >= 125.0:
        return hc, ac
    # Pick a high-contrast complementary palette color far from home_hex
    candidates = ("#38BDF8", "#F59E0B", "#10B981", "#E62E45", "#A855F7", "#F8FAFC")
    best_c = ac
    best_d = dist
    for cand in candidates:
        rc, gc, bc = _hex_to_rgb(cand)
        d = math.sqrt((r1 - rc) ** 2 + (g1 - gc) ** 2 + (b1 - bc) ** 2)
        if d > best_d:
            best_d = d
            best_c = cand
    return hc, best_c
