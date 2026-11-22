"""لایهٔ ۶ — Rendering: کارت پیش‌بازی از قالب استودیویی HTML (`studio_templates/pre_match.html`).

طراحی کارت **عیناً و بدون هیچ تفاوتی** از فایل استودیویی درون پوشه `studio_templates/`
تولید می‌شود و فقط داده‌های واقعی مسابقه جایگذاری می‌گردند:
  - هیچ عددی هاردکد یا جعلی نیست؛ همهٔ اعداد از fact_json (و مشتق قطعی Dixon-Coles
    روی xG واقعی) می‌آیند. null ≠ 0.
  - ترتیب اولویت ماژول‌ها در صورت وجود دیتای کامل:
      1. radar    (رادار ۶ محوره تاکتیکی)
      2. keyduel  (تقابل مهره‌های کلیدی)
      3. signals  (سیگنال‌های آماری و ارزش بازار +EV — فقط با ضریب واقعی بازار)
      4. wave     (موج زمانی امید گل ۱۵ دقیقه‌ای)
      5. trend10  (روند امید گل در ۱۰ بازی اخیر)
      6. stats    (مقایسه شاخص‌های فنی xG / xGA / SOT)
      7. poisson  (ماتریس احتمال دقیق نتیجه پواسون ۵×۵)
  - ماژول ۸ («باید حواسشون بهش باشه» / watchout) هرگز روی کارت نمایش داده نمی‌شود
    و به‌صورت خودکار به متن کپشن اضافه می‌گردد.
  - نیم‌فضای خالی و سرریز متن در هیچ فرمتی (4:5، 9:16، 16:9) رخ نمی‌دهد.
"""
from __future__ import annotations

import base64
import colorsys
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.xgpedia.config import (
    ROOT,
    load_brand,
    team_crest_path,
    team_identity,
)
from src.xgpedia.render.studio_engine import (
    FORMATS,
    PRE_MATCH_CAPTION_ONLY,
    PRE_MATCH_PRIORITY,
    STUDIO_TEMPLATES_DIR,
    build_card_caption,
    render_from_studio_template,
    select_studio_modules,
)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
FONTS_DIR = ROOT / "brand" / "fonts"
BRAND_LOGO_DIR = ROOT / "brand" / "logo" / "svg"
FONT_FILES = (
    ("Vazirmatn-Regular.woff2", "Vazirmatn", 400),
    ("Vazirmatn-Medium.woff2", "Vazirmatn", 500),
    ("Vazirmatn-Bold.woff2", "Vazirmatn", 700),
    ("Vazirmatn-Black.woff2", "Vazirmatn", 800),
    ("JetBrainsMono-var.woff2", "JetBrains Mono", "100 800"),
    ("SpaceGrotesk-var.woff2", "Space Grotesk", "300 700"),
)
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
TEHRAN = timezone(timedelta(hours=3, minutes=30))
NO_DATA = "داده در دسترس نیست"

COMPETITION_FA = {"Premier League": "لیگ برتر انگلیس"}
FORM_LABELS = {"W": "ب", "D": "م", "L": "ش"}

MODULE_DEFS = [
    ("radar", True, "full"),
    ("keyduel", True, "full"),
    ("signals", False, "full"),
    ("wave", True, "full"),
    ("trend10", True, "full"),
    ("stats", False, "full"),
    ("poisson", True, "full"),
    ("watchout", True, "full"),
    ("focus", True, "full"),
]

COLOR_NEAR_THRESHOLD = 72


# ─── ابزارهای نمایش عدد و تاریخ ───

def fa_digits(text: str | int) -> str:
    """تبدیل ارقام لاتین به فارسی — برای تاریخ/ساعت در متن فارسی."""
    return str(text).translate(FA_DIGITS)


def fmt_stat(value: float | int | None, decimals: int = 0) -> str | None:
    """عدد آماری با ارقام لاتین و ممیز لاتین — null≠0."""
    if value is None:
        return None
    if decimals <= 0:
        return str(int(round(float(value))))
    s = f"{float(value):.{decimals}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def fmt_fixed(value: float | int | None, decimals: int) -> str | None:
    """عدد با اعشار ثابت — عین toFixed استودیو."""
    if value is None:
        return None
    return f"{float(value):.{decimals}f}"


def _parse_utc(iso: str) -> datetime:
    s = str(iso).strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """تبدیل قطعی میلادی به جلالی (fallback خالص پایتون در صورت نبود jdatetime)."""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        355666
        + (365 * gy)
        + ((gy2 + 3) // 4)
        - ((gy2 + 99) // 100)
        + ((gy2 + 399) // 400)
        + gd
        + g_d_m[gm - 1]
    )
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def jalali_date(iso: str) -> str:
    """تاریخ جلالی فارسی — «یک‌شنبه ۱۷ آبان ۱۴۰۵» با ارقام فارسی."""
    dt = _parse_utc(iso)
    try:
        import jdatetime

        j = jdatetime.date.fromgregorian(date=dt.date())
        weekday = jdatetime.date.j_weekdays_fa[j.weekday()]
        return f"{weekday} {fa_digits(j.day)} {j.j_months_fa[j.month - 1]} {fa_digits(j.year)}"
    except ImportError:
        jy, jm, jd = _gregorian_to_jalali(dt.year, dt.month, dt.day)
        # Python weekday(): Mon=0..Sun=6 -> Jalali Sat=0..Fri=6
        weekdays_fa = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه", "شنبه", "یک‌شنبه"]
        months_fa = [
            "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
            "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
        ]
        return f"{weekdays_fa[dt.weekday()]} {fa_digits(jd)} {months_fa[jm - 1]} {fa_digits(jy)}"


def tehran_clock(iso: str) -> str | None:
    """ساعت کیک‌آف به وقت تهران با ارقام فارسی؛ None = ساعت در منبع نبود."""
    dt = _parse_utc(iso)
    if (dt.hour, dt.minute, dt.second) == (0, 0, 0):
        return None
    return fa_digits(dt.astimezone(TEHRAN).strftime("%H:%M"))


def season_short(season: str) -> str:
    """«2026-27» → «26/27»."""
    parts = str(season).split("-")
    if len(parts) == 2 and len(parts[0]) == 4 and len(parts[1]) == 2:
        return f"{parts[0][2:]}/{parts[1]}"
    return str(season)


# ─── ابزارهای رنگ ───

def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    clean = (hex_color or "#E62E45").lstrip("#")
    if len(clean) == 3:
        clean = "".join(c + c for c in clean)
    num = int(clean, 16) if clean else 0
    return (num >> 16) & 255, (num >> 8) & 255, num & 255


def _luminance(hex_color: str) -> float:
    r, g, b = _hex_to_rgb(hex_color)
    vals = []
    for v in (r, g, b):
        v /= 255
        vals.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    return vals[0] * 0.2126 + vals[1] * 0.7152 + vals[2] * 0.0722


def _contrast_text(hex_color: str) -> str:
    return "#070D1D" if _luminance(hex_color) > 0.55 else "#F8FAFC"


def _color_distance(a: str, b: str) -> float:
    ra, ga, ba = _hex_to_rgb(a)
    rb, gb, bb = _hex_to_rgb(b)
    return (ra - rb) ** 2 + (ga - gb) ** 2 + (ba - bb) ** 2


def _color_dist_hsl(a: str, b: str) -> float:
    ra, ga, ba = _hex_to_rgb(a)
    rb, gb, bb = _hex_to_rgb(b)
    ha = colorsys.rgb_to_hls(ra / 255, ga / 255, ba / 255)[0]
    hb = colorsys.rgb_to_hls(rb / 255, gb / 255, bb / 255)[0]
    dh = abs(ha - hb)
    return min(dh, 1 - dh) * 360


def _glow_color(hex_color: str, min_lightness: float = 0.3) -> str:
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if l < min_lightness:
        l = min_lightness
    r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
    return "#{:02X}{:02X}{:02X}".format(round(r2 * 255), round(g2 * 255), round(b2 * 255))


def display_colors(
    home_ident: dict | None, away_ident: dict | None, fallback: str
) -> tuple[str, str]:
    """رنگ نمایشی دو تیم از team_identities.json با تضمین تفکیک رنگی."""
    hc = (home_ident or {}).get("colors", {}).get("primary") or fallback
    ac = (away_ident or {}).get("colors", {}).get("primary") or fallback
    if _color_distance(hc, ac) >= COLOR_NEAR_THRESHOLD and _color_dist_hsl(hc, ac) >= 25:
        return hc, ac
    alt = (away_ident or {}).get("colors", {}).get("secondary") or fallback
    if _color_distance(hc, alt) >= COLOR_NEAR_THRESHOLD or _color_dist_hsl(hc, alt) >= 25:
        return hc, alt
    return hc, fallback


# ─── نشان تیم‌ها و دارایی‌های برند ───

def _brand_logo_data_uri(mono: bool = False) -> str | None:
    src = BRAND_LOGO_DIR / ("logo-white.svg" if mono else "logo.svg")
    if not src.exists():
        return None
    svg = src.read_text(encoding="utf-8")
    if not mono:
        first_fill = re.search(r'fill="#[0-9A-Fa-f]{6}"', svg)
        if first_fill:
            svg = svg.replace(first_fill.group(0), 'fill="#FFFFFF"', 1)
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def _brand_avatar_data_uri() -> str | None:
    src = BRAND_LOGO_DIR / "logo-xg-white.svg"
    if not src.exists():
        return None
    b64 = base64.b64encode(src.read_bytes()).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def _brand_lockup_svg(mono: bool = False) -> str:
    uri = _brand_logo_data_uri(mono)
    if uri is not None:
        return (
            '<div class="brand-logo-lockup" dir="ltr">'
            f'<img src="{uri}" alt="XGPedia" class="brand-logo-img" />'
            "</div>"
        )
    return ""


def _crest_data_uri(name_en: str) -> str | None:
    """data URI لوگوی واقعی تیم از brand/crests/{CODE}.svg|png برای فیلد logoUrl استودیو."""
    path = team_crest_path(name_en)
    if path is None:
        return None
    mime = "image/svg+xml" if path.suffix == ".svg" else "image/png"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _crest_html(name_en: str, team: dict, side: str) -> str:
    uri = _crest_data_uri(name_en)
    if uri is not None:
        return f'<img src="{uri}" alt="{team["name_fa"]}" class="crest-img" />'
    code = (team.get("code") or "FC")[:3].upper()
    return f'<svg viewBox="0 0 180 180"><text x="90" y="102">{code}</text></svg>'


# ─── ابزارهای کمکی نمودار و پالت (حفظ سازگاری) ───

_PALETTE_CACHE: dict | None = None


def _palette() -> dict:
    global _PALETTE_CACHE
    if _PALETTE_CACHE is None:
        _PALETTE_CACHE = load_brand()["matchday_palette"]
    return _PALETTE_CACHE


def _ensure_palette_cached(b: dict) -> None:
    global _PALETTE_CACHE
    _PALETTE_CACHE = b["matchday_palette"]


def _font_faces() -> list[dict]:
    faces = []
    for name, family, weight in FONT_FILES:
        p = FONTS_DIR / name
        if not p.exists():
            raise FileNotFoundError(
                f"brand/fonts/{name} not found - fonts must sit in brand/fonts/"
            )
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        faces.append({"family": family, "weight": weight, "data": f"data:font/woff2;base64,{b64}"})
    return faces


def _crosshairs(w: int, h: int, inset: int) -> str:
    c1, c2 = inset + 12, inset + 32
    rx1, rx2 = w - c1, w - c2
    by1, by2 = h - c1, h - c2
    return (
        f"M{c1} {c2}V{c1}H{c2}M{rx1} {c2}V{c1}H{rx2}"
        f"M{c1} {by2}V{by1}H{c2}M{rx1} {by2}V{by1}H{rx2}"
    )


def _trend_context(
    h_series: list[float], a_series: list[float], is_half: bool, hc: str, ac: str, vh: int = 190
) -> dict:
    return {
        "h": vh,
        "home_avg": fmt_fixed(sum(h_series) / len(h_series), 2),
        "away_avg": fmt_fixed(sum(a_series) / len(a_series), 2),
        "home_dots": [{"i": str(i + 1), "v": v} for i, v in enumerate(h_series)],
        "hc": hc,
        "ac": ac,
    }


def _poisson_context(matrix: list[list[float]]) -> dict:
    tops: list[tuple[str, float]] = []
    cells: list[dict] = []
    for h in range(5):
        for a in range(5):
            pct = matrix[h][a] * 100
            cells.append({"h": h, "a": a, "score": f"{h}-{a}", "pct": fmt_stat(round(pct, 1), 1)})
            tops.append((f"{h}-{a}", pct))
    tops.sort(key=lambda x: -x[1])
    top3 = " • ".join(f"{s} ({fmt_stat(round(p, 1), 1)}٪)" for s, p in tops[:3])
    return {"cells": cells, "top3": top3}


# ─── اعتبارسنجی کامل‌بودن دیتای واقعی هر ماژول ───

def _valid_num_list(val: Any, exact_len: int | None = None, min_len: int = 2) -> list[float] | None:
    if not isinstance(val, list):
        return None
    if exact_len is not None and len(val) != exact_len:
        return None
    if exact_len is None and len(val) < min_len:
        return None
    out: list[float] = []
    for item in val:
        if item is None or isinstance(item, bool):
            return None
        try:
            f = float(item)
        except (TypeError, ValueError):
            return None
        if math.isnan(f) or math.isinf(f):
            return None
        out.append(f)
    return out


def _valid_key_player(kp: Any) -> dict[str, str] | None:
    if not isinstance(kp, dict):
        return None
    name = str(kp.get("name") or "").strip()
    pos = str(kp.get("pos") or "").strip()
    s1 = str(kp.get("s1") or "").strip()
    s2 = str(kp.get("s2") or "").strip()
    if not (name and pos and s1 and s2):
        return None
    return {"name": name, "pos": pos, "s1": s1, "s2": s2}


def _build_real_signals(
    facts: dict, probs: dict | None, dc: dict | None, home_name: str, away_name: str
) -> list[dict[str, Any]]:
    """ساخت سیگنال‌های ارزش (+EV) صرفاً از ضرایب واقعی بازار در facts['market_odds'].

    بدون ضرایب واقعی بازار، هیچ سیگنال جعلی یا شبیه‌سازی‌شده‌ای تولید نمی‌شود.
    """
    odds_data = facts.get("market_odds")
    if not isinstance(odds_data, dict) or not probs or not dc:
        return []

    def tier(ev_pct: float) -> tuple[str, str]:
        if ev_pct >= 8:
            return "eh", "بسیار ارزشمند"
        if ev_pct >= 5:
            return "ed", "ارزشمند"
        if ev_pct >= 2.5:
            return "ew", "ارزش متوسط"
        return "en", "ارزش جزئی"

    candidates: list[tuple[str, float, Any]] = []
    if probs["home"] >= probs["away"]:
        candidates.append((f"برد {home_name}", probs["home"] / 100.0, odds_data.get("home")))
    else:
        candidates.append((f"برد {away_name}", probs["away"] / 100.0, odds_data.get("away")))
    candidates.append(("بیش از ۲.۵ گل", float(dc["pO25"]), odds_data.get("over25")))
    candidates.append(("گلزنی هر دو تیم", float(dc["pBTTS"]), odds_data.get("btts")))

    items: list[dict[str, Any]] = []
    for title, model_p, raw_odd in candidates:
        if raw_odd is None:
            continue
        try:
            odd = float(raw_odd)
        except (TypeError, ValueError):
            continue
        if odd <= 1.0:
            continue
        market_p = 1.0 / odd
        ev_pct = (model_p * odd - 1.0) * 100.0
        tc, tl = tier(ev_pct)
        items.append({
            "title": title,
            "odds": round(odd, 2),
            "model_pct": round(model_p * 100.0, 1),
            "market_pct": round(market_p * 100.0, 1),
            "ev_pct": round(ev_pct, 1),
            "tier_class": tc,
            "tier_label": tl,
        })
    return items


def _team_side_ctx(side: dict, ident: dict | None, display_color: str, side_key: str) -> dict:
    """هویت کامل یک طرف کارت از فکت‌ها + team_identities.json (بدون هیچ دیتای هاردکد)."""
    p = _palette()
    colors = (ident or {}).get("colors") or {}
    form_seq = side.get("recent_form") or {}
    form = [f for f in str(form_seq.get("sequence", "")) if f in FORM_LABELS]
    series = _valid_num_list(side.get("xg_series"), min_len=2)
    radar = _valid_num_list(side.get("radar"), exact_len=6)
    wave = _valid_num_list(side.get("wave"), exact_len=6)
    kp = _valid_key_player(side.get("kp") or side.get("key_player"))

    def _val(key: str) -> float | None:
        node = side.get(key)
        if isinstance(node, dict):
            v = node.get("value")
            return float(v) if v is not None else None
        if isinstance(node, (int, float)) and not isinstance(node, bool):
            return float(node)
        return None

    return {
        "name_fa": side.get("name_fa", ""),
        "name_en": side.get("name_en", ""),
        "code": (ident or {}).get("code") or (side.get("name_en") or "FC")[:3].upper(),
        "primary": colors.get("primary") or display_color,
        "secondary": colors.get("secondary") or p["text_bright"],
        "color": display_color,
        "form": form,
        "form_dots": [{"f": f, "label": FORM_LABELS[f]} for f in form],
        "xg": _val("xg_for_avg"),
        "xga": _val("xg_against_avg"),
        "sot": _val("sot_avg"),
        "corners": _val("corners_avg"),
        "xg_series": series,
        "sub": str(side.get("sub") or "").strip(),
        "kp": kp,
        "watchout": str(side.get("watchout") or "").strip() or None,
        "radar": radar,
        "wave": wave,
        "logoUrl": _crest_data_uri(side.get("name_en", "")),
        "_side": side_key,
    }



def _select_modules(version: str, has: dict[str, bool], fmt: str = "4:5") -> list[dict]:
    """انتخاب ماژول‌های کارت پیش‌ازبازی مطابق اولویت تعریف‌شده و ظرفیت فرمت."""
    return select_studio_modules("preview", has, fmt=fmt, layout=version)

# ─── ساخت context کارت پیش‌ازبازی ───

def build_preview_context(
    draft: dict,
    facts: dict,
    post_type: str = "preview",
    brand: dict | None = None,
    layout: str = "smart",
    fmt: str = "4:5",
    brand_mono: bool = False,
    header_mode: str = "full",
) -> dict:
    """ساخت context کامل کارت پیش‌ازبازی و payload دقیق استودیو `pre_match.html`.

    همهٔ اعداد صرفاً از fact_json (و مشتق قطعی Dixon-Coles روی xG واقعی) می‌آیند.
    انتخاب ماژول‌ها دقیقاً طبق اولویت کاربر انجام می‌شود و `watchout` هرگز روی کارت نمی‌آید.
    """
    from src.xgpedia.analytics.metrics import dixon_coles_matrix, expected_points

    b = brand or load_brand()
    p = b["matchday_palette"]
    _ensure_palette_cached(b)
    home_f, away_f = facts.get("home", {}), facts.get("away", {})

    home_ident = team_identity(home_f.get("name_en", ""))
    away_ident = team_identity(away_f.get("name_en", ""))
    hc, ac = display_colors(home_ident, away_ident, p["sky_bright"])

    home = _team_side_ctx(home_f, home_ident, hc, "home")
    away = _team_side_ctx(away_f, away_ident, ac, "away")
    home["crest_html"] = _crest_html(home_f.get("name_en", ""), home, "home")
    away["crest_html"] = _crest_html(away_f.get("name_en", ""), away, "away")

    # احتمال‌های ۱X۲ — مشتق قطعی Dixon-Coles از دو عدد xG واقعی
    probs: dict | None = None
    dc: dict | None = None
    if home["xg"] is not None and away["xg"] is not None:
        dc = dixon_coles_matrix(float(home["xg"]), float(away["xg"]))
        pH = max(5, round(dc["pH"] * 100))
        pD = max(5, round(dc["pD"] * 100))
        pA = max(5, 100 - pH - pD)
        if pH + pD + pA != 100:
            pH += 100 - (pH + pD + pA)
        probs = {"home": pH, "draw": pD, "away": pA}

    # ردیف‌های واقعی stats (فقط شاخص‌هایی که هر دو تیم مقدار دارند)
    stat_rows = []
    for label, key, dec in (
        ("امید گل تولیدی (xG)", "xg", 2),
        ("امید گل دریافتی (xGA)", "xga", 2),
        ("شوت در چارچوب (SOT)", "sot", 1),
    ):
        hv, av = home[key], away[key]
        if hv is None or av is None:
            continue
        max_v = max(hv, av, 0.01)
        stat_rows.append({
            "label": label,
            "h": fmt_fixed(hv, dec),
            "a": fmt_fixed(av, dec),
            "h_pct": f"{hv / max_v * 100:.1f}",
            "a_pct": f"{av / max_v * 100:.1f}",
        })

    # بررسی کامل‌بودن دیتای واقعی هر ماژول
    signals_items = _build_real_signals(facts, probs, dc, home["name_fa"], away["name_fa"])
    trend_ctx = (
        _trend_context(home["xg_series"], away["xg_series"], False, hc, ac, vh=190)
        if (home["xg_series"] and away["xg_series"])
        else None
    )
    poisson_ctx = _poisson_context(dc["matrix"]) if dc else None

    has: dict[str, bool] = {
        "radar": bool(home["radar"] and away["radar"]),
        "keyduel": bool(home["kp"] and away["kp"]),
        "signals": bool(signals_items),
        "wave": bool(home["wave"] and away["wave"]),
        "trend10": trend_ctx is not None,
        "stats": bool(stat_rows),
        "poisson": poisson_ctx is not None,
        "watchout": False,  # الزام کاربر: هرگز روی کارت نیست؛ فقط در کپشن
    }
    modules = select_studio_modules(
        "preview", has, fmt=fmt, layout=layout, header_mode=header_mode
    )

    # هدر و متادیتا (صرفاً از دیتای واقعی؛ بدون هاردکد)
    comp_en = facts.get("competition", {}).get("name", "")
    season = facts.get("competition", {}).get("season", "")
    kickoff = facts.get("kickoff_utc", "")
    date_line = jalali_date(kickoff) if kickoff else ""
    clock = tehran_clock(kickoff) if kickoff else None
    date_display = f"{date_line} • {clock}" if (date_line and clock) else date_line

    week_code = facts.get("matchday")
    week_part = f"W{week_code}" if isinstance(week_code, int) else str(week_code or "")
    prov = (facts.get("source") or {}).get("provider", "")

    w, hgt = FORMATS.get(fmt, FORMATS["4:5"])

    # payload دقیق مطابق ساختار S.m در studio_templates/pre_match.html
    studio_match: dict[str, Any] = {
        "competition": COMPETITION_FA.get(comp_en, comp_en) or "فوتبال",
        "round": str(facts.get("round") or "").strip(),
        "leagueEn": (comp_en or "FOOTBALL").upper(),
        "season": season_short(season) if season else "",
        "weekCode": week_part,
        "day": date_line,
        "time": clock or "",
        "stadium": str(facts.get("stadium") or "").strip(),
        "broadcast": str(facts.get("broadcast") or "").strip(),
        "source": prov or "XGPedia Analytics",
        "probHome": probs["home"] if probs else 0,
        "probDraw": probs["draw"] if probs else 0,
        "probAway": probs["away"] if probs else 0,
        "home": {
            "name": home["name_fa"],
            "sub": home["sub"],
            "code": home["code"],
            "color": home["color"],
            "secondary": home["secondary"],
            "logoUrl": home["logoUrl"],
            "form": home["form"],
            "xg": home["xg"] if home["xg"] is not None else 0,
            "xga": home["xga"] if home["xga"] is not None else 0,
            "sot": home["sot"] if home["sot"] is not None else 0,
            "radar": home["radar"],
            "last10": home["xg_series"],
            "wave": home["wave"],
            "kp": home["kp"],
            "watchout": home["watchout"] or "",
        },
        "away": {
            "name": away["name_fa"],
            "sub": away["sub"],
            "code": away["code"],
            "color": away["color"],
            "secondary": away["secondary"],
            "logoUrl": away["logoUrl"],
            "form": away["form"],
            "xg": away["xg"] if away["xg"] is not None else 0,
            "xga": away["xga"] if away["xga"] is not None else 0,
            "sot": away["sot"] if away["sot"] is not None else 0,
            "radar": away["radar"],
            "last10": away["xg_series"],
            "wave": away["wave"],
            "kp": away["kp"],
            "watchout": away["watchout"] or "",
        },
        "focus": {
            "title": str(draft.get("title") or "").strip(),
            "body": " ".join(str(x).strip() for x in (draft.get("bullets") or [])[:2] if x),
            "tag": f"منبع: {prov}" if prov else "",
        },
    }

    studio_payload = {
        "cardType": "preview",
        "fmt": fmt,
        "headerMode": header_mode,
        "hasProbs": probs is not None,
        "dateLineOverride": date_display,
        "modules": modules,
        "statsRows": stat_rows,
        "signalsItems": signals_items,
        "match": studio_match,
    }

    hero = {
        "xg_home": fmt_fixed(home["xg"], 2),
        "xg_away": fmt_fixed(away["xg"], 2),
        "xg_total": fmt_fixed((home["xg"] or 0) + (away["xg"] or 0), 2)
        if home["xg"] is not None and away["xg"] is not None else None,
        "probs": probs,
        "xpts_home": fmt_fixed(
            expected_points(probs["home"] / 100, probs["draw"] / 100, probs["away"] / 100)[0], 2
        ) if probs else None,
        "xpts_away": fmt_fixed(
            expected_points(probs["home"] / 100, probs["draw"] / 100, probs["away"] / 100)[1], 2
        ) if probs else None,
        "capsule": [
            {"id": "home", "pct": probs["home"], "bg": hc, "color": _contrast_text(hc)},
            {"id": "draw", "pct": probs["draw"], "bg": p["draw_grey"], "color": p["text_bright"]},
            {"id": "away", "pct": probs["away"], "bg": ac, "color": _contrast_text(ac)},
        ] if probs else None,
        "odds": {
            "home": fmt_fixed(round(100 / max(1, probs["home"]), 2), 2),
            "draw": fmt_fixed(round(100 / max(1, probs["draw"]), 2), 2),
            "away": fmt_fixed(round(100 / max(1, probs["away"]), 2), 2),
        } if probs else None,
    }

    return {
        "palette": p,
        "brand_name": b.get("brand", "XGPedia"),
        "brand_lockup_html": _brand_lockup_svg(brand_mono),
        "brand_mono": brand_mono,
        "brand_favicon_uri": _brand_avatar_data_uri(),
        "handle": "@XGPedia",
        "format": {"key": fmt, "w": w, "h": hgt, "is_wide": fmt == "16:9", "is_tall": fmt == "9:16"},
        "competition_fa": COMPETITION_FA.get(comp_en, comp_en),
        "day": date_line,
        "time": clock,
        "home": home,
        "away": away,
        "hero": hero,
        "has": has,
        "modules": modules,
        "module_data": {
            "stats": {"rows": stat_rows},
            "radar": {"home": home["radar"], "away": away["radar"]} if has["radar"] else None,
            "keyduel": {"home": home["kp"], "away": away["kp"]} if has["keyduel"] else None,
            "signals": {"items": signals_items} if has["signals"] else None,
            "wave": {"home": home["wave"], "away": away["wave"]} if has["wave"] else None,
            "trend10": trend_ctx,
            "poisson": poisson_ctx,
        },
        "caption_text": build_card_caption(draft, facts, post_type),
        "studio_payload": studio_payload,
    }


# ─── رندر ───

def render_preview_html(
    draft: dict,
    facts: dict,
    post_type: str = "preview",
    layout: str = "smart",
    fmt: str = "4:5",
    brand_mono: bool = False,
    header_mode: str = "full",
    template_dir: str | Path | None = None,
) -> str:
    """تولید HTML کامل کارت پیش‌ازبازی دقیقاً از روی `studio_templates/pre_match.html`."""
    ctx = build_preview_context(
        draft,
        facts,
        post_type=post_type,
        layout=layout,
        fmt=fmt,
        brand_mono=brand_mono,
        header_mode=header_mode,
    )
    return render_from_studio_template("preview", ctx["studio_payload"], template_dir=template_dir)


def render_preview_card(
    draft: dict,
    facts: dict,
    out_dir: str | Path,
    post_id: int,
    version: int,
    platform: str = "telegram",
    post_type: str = "preview",
    layout: str = "smart",
    fmt: str = "4:5",
    brand_mono: bool = False,
    header_mode: str = "full",
    template_dir: str | Path | None = None,
) -> tuple[Path, Path, Path]:
    """رندر کامل یک پست: HTML استودیویی + تصویر نهایی + کپشن (با متن watchout/autopsy)."""
    from src.xgpedia.render.render_png import render_sync

    if post_type == "post_match":
        from src.xgpedia.render.post_match_cards import render_post_match_card

        return render_post_match_card(
            draft,
            facts,
            out_dir,
            post_id,
            version,
            platform=platform,
            layout=layout,
            fmt=fmt,
            brand_mono=brand_mono,
            header_mode=header_mode,
            template_dir=template_dir,
        )

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    w, hgt = FORMATS.get(fmt, FORMATS["4:5"])
    stem = f"post_{post_id}_v{version}_{post_type}"
    html_path = out / f"{stem}_{w}x{hgt}.html"
    html_path.write_text(
        render_preview_html(
            draft,
            facts,
            post_type=post_type,
            layout=layout,
            fmt=fmt,
            brand_mono=brand_mono,
            header_mode=header_mode,
            template_dir=template_dir,
        ),
        encoding="utf-8",
    )

    img_fmt = "jpeg" if platform == "instagram" else "png"
    img_path = out / f"{stem}_{w}x{hgt}.{img_fmt}"
    render_sync(str(html_path), str(img_path), w, hgt, img_fmt)

    cap_path = out / f"post_{post_id}_v{version}_caption.txt"
    cap_path.write_text(build_card_caption(draft, facts, post_type), encoding="utf-8")

    return html_path, img_path, cap_path


HASHTAG_BY_TYPE = {
    "preview": "#پیش_بازی",
    "post_match": "#پس_از_بازی",
    "number_of_day": "#عدد_روز",
}
