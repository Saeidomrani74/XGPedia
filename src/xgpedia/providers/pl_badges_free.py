"""لوگوهای رسمی باشگاه‌های لیگ برتر انگلیس (Premier League Official Badges) و تضمین کنتراست رنگ تیم‌ها.

منبع ۱۰۰٪ رایگان و بدون کلید API:
  1. کش دیسک (`output/.badge_cache/pl_t{code}.png`) و دانلود از `resources.premierleague.com`
  2. پشتیبان ۱۰۰٪ آفلاین و محلی از `brand/crests/{TLA}.svg` (به‌صورت `data:image/svg+xml;base64,...`)
     تا لوگوهای باشگاه‌های انگلیسی در هر حالتی (حتی بدون اینترنت یا کش) واقعی و برداری باشند.
"""
from __future__ import annotations

import base64
import math
import urllib.request
from pathlib import Path

from src.xgpedia.config import ROOT

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
BADGE_CACHE_DIR = ROOT / "output" / ".badge_cache"
LOCAL_CRESTS_DIR = ROOT / "brand" / "crests"

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
    "coventry": ("کاونتری سیتی", "COV", "#58B9E7", "#FFFFFF", 9),
    "hull": ("هال سیتی", "HUL", "#F5A12D", "#111111", 88),
    "wolves": ("ولورهمپتون", "WOL", "#FDB913", "#231F20", 39),
    "wolverhampton": ("ولورهمپتون", "WOL", "#FDB913", "#231F20", 39),
    "wolverhampton wanderers": ("ولورهمپتون", "WOL", "#FDB913", "#231F20", 39),
}

_BY_TLA: dict[str, tuple[str, str, str, str, int]] = {v[1]: v for v in PL_CLUBS_MASTER.values()}
_BY_FA: dict[str, tuple[str, str, str, str, int]] = {v[0]: v for v in PL_CLUBS_MASTER.values()}
_BY_CODE: dict[int, tuple[str, str, str, str, int]] = {v[4]: v for v in PL_CLUBS_MASTER.values()}
_MEM_CACHE: dict[str, str] = {}


def lookup_pl_club(name_or_tla: str | int, tla_hint: str = "") -> tuple[str, str, str, str, int] | None:
    if isinstance(name_or_tla, int):
        return _BY_CODE.get(name_or_tla)
    s = str(name_or_tla or "").strip()
    if s.isdigit() and int(s) in _BY_CODE:
        return _BY_CODE[int(s)]
    if s in _BY_FA:
        return _BY_FA[s]
    s_up = s.upper()
    if s_up in _BY_TLA:
        return _BY_TLA[s_up]
    low = s.lower()
    if low in PL_CLUBS_MASTER:
        return PL_CLUBS_MASTER[low]
    t = str(tla_hint or "").strip().upper()
    if t in _BY_TLA:
        return _BY_TLA[t]
    if low:
        for k, v in PL_CLUBS_MASTER.items():
            if k in low or (len(low) >= 4 and low in k):
                return v
    # پل خودکار به باشگاه‌های لیگ قهرمانان اروپا (UEFA Champions League)
    try:
        from src.xgpedia.providers.ucl_badges_free import lookup_ucl_club
        u = lookup_ucl_club(s, tla_hint=tla_hint)
        if u:
            return u
    except Exception:
        pass
    return None


def _load_local_crest_svg_uri(tla: str) -> str | None:
    """بارگذاری لوگوی برداری واقعی باشگاه از پوشه محلی `brand/crests/{TLA}.svg` (۱۰۰٪ آفلاین)."""
    t = str(tla or "").strip().upper()[:3]
    if not t:
        return None
    for ext, mime in ((".svg", "image/svg+xml"), (".png", "image/png")):
        crest_path = LOCAL_CRESTS_DIR / f"{t}{ext}"
        if crest_path.exists() and crest_path.stat().st_size > 100:
            try:
                raw = crest_path.read_bytes()
                return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
            except Exception:
                continue
    return None


def get_pl_badge_data_uri(
    name_or_tla: str | int,
    *,
    tla_hint: str = "",
    badge_code: int | None = None,
    size: int | None = None,
    fetch_network: bool = True,
) -> str | None:
    """دریافت لوگوی رسمی باشگاه لیگ برتر به‌صورت data URI (کش حافظه + دیسک + SVG محلی `brand/crests/`)."""
    code = badge_code
    tla = str(tla_hint or "").strip().upper()[:3]
    hit = lookup_pl_club(name_or_tla, tla_hint)
    # اگر باشگاه متعلق به چمپیونزلیگ (غیرانگلیسی) بود، مستقیم از پرووایدر رسمی UCL برگردان
    if hit and hit[1] not in _BY_TLA:
        try:
            from src.xgpedia.providers.ucl_badges_free import get_ucl_badge_data_uri
            u_uri = get_ucl_badge_data_uri(hit[1], tla_hint=hit[1], espn_id=hit[4], fetch_network=fetch_network)
            if u_uri:
                return u_uri
        except Exception:
            pass
    if hit:
        if code is None:
            code = hit[4]
        if not tla:
            tla = hit[1]
    elif code is not None and code in _BY_CODE and not tla:
        tla = _BY_CODE[code][1]
    elif not tla and isinstance(name_or_tla, str) and len(name_or_tla.strip()) == 3:
        tla = name_or_tla.strip().upper()

    cache_key = f"c{code}" if code else f"t{tla}"
    if cache_key in _MEM_CACHE:
        return _MEM_CACHE[cache_key]

    # ۱) بررسی کش دیسک PNG رسمی لیگ برتر
    if code:
        try:
            BADGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_f = BADGE_CACHE_DIR / f"pl_t{code}.png"
            if cache_f.exists() and cache_f.stat().st_size > 500:
                raw = cache_f.read_bytes()
                uri = f"data:image/png;base64,{base64.b64encode(raw).decode('ascii')}"
                _MEM_CACHE[cache_key] = uri
                return uri
        except Exception:
            pass

    # ۲) بررسی لوگوی محلی برداری واقعی در `brand/crests/{TLA}.svg` (۱۰۰٪ آفلاین و سریع)
    local_svg = _load_local_crest_svg_uri(tla)
    if local_svg and not fetch_network:
        _MEM_CACHE[cache_key] = local_svg
        return local_svg

    # ۳) دانلود آنلاین PNG رسمی لیگ برتر در صورت مجاز بودن شبکه
    if code and fetch_network:
        sz_order = ("100", "70") if (size is None or size >= 70) else ("70", "100")
        for sz in sz_order:
            url = f"https://resources.premierleague.com/premierleague/badges/{sz}/t{code}.png"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    raw = resp.read()
                if len(raw) > 500 and raw[:4] == b"\x89PNG":
                    try:
                        BADGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                        (BADGE_CACHE_DIR / f"pl_t{code}.png").write_bytes(raw)
                    except Exception:
                        pass
                    uri = f"data:image/png;base64,{base64.b64encode(raw).decode('ascii')}"
                    _MEM_CACHE[cache_key] = uri
                    return uri
            except Exception:
                continue

    # ۴) پشتیبان نهایی: لوگوی برداری محلی واقعی (`brand/crests/{TLA}.svg`)
    if local_svg:
        _MEM_CACHE[cache_key] = local_svg
        return local_svg
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
