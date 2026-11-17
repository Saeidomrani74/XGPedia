"""لایهٔ ۶ — Rendering: کارت پیش‌بازی از draft_json + fact_json + brand.json + team_identities.

منبع طراحی: tools/matchday_studio.html (استودیو کارت — عیناً همانMarkup/CSS/SVG
در قالب Jinja پیاده شده). قواعد این ماژول:

  - رندرر هیچ عددی از خودش نمی‌سازد؛ همهٔ اعداد از fact_json می‌آیند. تنها استثنا
    احتمال‌های ۱X۲ و ماتریس پواسون است که به‌صورت قطعی از دو عدد xG همان فکت‌ها
    با مدل Dixon-Coles (analytics/metrics.py) مشتق می‌شوند — ورودی خارجی ندارد.
  - رنگ برند/پالت استودیو فقط از brand.json (بخش matchday_palette) تزریق می‌شود؛
    رنگ تیم‌ها از config/team_identities.json؛ قالب HTML هیچ هگز هاردکدی ندارد.
  - null یعنی «داده در دسترس نیست» — هرگز صفر یا خط تیره جایگزین نمی‌شود؛
    ماژولی که داده‌اش نیست اصلاً رندر نمی‌شود (کدش برای آینده محفوظ می‌ماند).
  - ارقام آماری لاتین با tabular-nums؛ تاریخ/ساعت جلالی با ارقام فارسی
    (سیاست numerals_policy برند — در استودیو دموی دستی همه ارقام فارسی بود).
  - فونت‌ها data URI داخل HTML تا خروجی خودبسنده باشد.
"""
from __future__ import annotations

import base64
import colorsys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.xgpedia.config import (
    ROOT,
    load_brand,
    team_crest_path,
    team_identity,
)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
FONTS_DIR = ROOT / "brand" / "fonts"
FONT_FILES = (  # (نام فایل woff2، خانوادهٔ CSS، وزن یا بازهٔ وزن)
    ("Vazirmatn-Regular.woff2", "Vazirmatn", 400),
    ("Vazirmatn-Medium.woff2", "Vazirmatn", 500),
    ("Vazirmatn-Bold.woff2", "Vazirmatn", 700),
    ("Vazirmatn-Black.woff2", "Vazirmatn", 800),
    ("JetBrainsMono-var.woff2", "JetBrains Mono", "100 800"),  # فونت متغیر لاتین mono
    ("SpaceGrotesk-var.woff2", "Space Grotesk", "300 700"),    # فونت متغیر لاتین display
)
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
TEHRAN = timezone(timedelta(hours=3, minutes=30))  # ایران ساعت تابستانی ندارد
NO_DATA = "داده در دسترس نیست"

COMPETITION_FA = {"Premier League": "لیگ برتر انگلیس"}
FORM_LABELS = {"W": "ب", "D": "م", "L": "ش"}  # برد/مساوی/باخت — دایره‌های فرم

# قالب‌های خروجی استودیو — کلید همان دکمه‌های tools/matchday_studio.html
FORMATS = {"4:5": (1080, 1350), "9:16": (1080, 1920), "16:9": (1920, 1080)}

# رجیستری ماژول‌ها — عین MODULE_DEFS استودیو: (id، نیم‌عرض ممکن، عرض پیش‌فرض)
MODULE_DEFS = [
    ("stats", False, "full"),
    ("radar", True, "half"),
    ("focus", True, "half"),
    ("watchout", True, "half"),
    ("keyduel", True, "half"),
    ("poisson", True, "half"),
    ("wave", True, "half"),
    ("trend10", True, "half"),
    ("signals", False, "full"),
]

# فاصلهٔ رنگی زیر این آستانه (ایوکلیدس RGB تا ۴۴۱) → رنگ میهمان «نزدیک» میزبان است
COLOR_NEAR_THRESHOLD = 72


# ─── ابزارهای نمایش عدد و تاریخ ───

def fa_digits(text: str | int) -> str:
    """تبدیل ارقام لاتین به فارسی — برای تاریخ/ساعت در متن فارسی."""
    return str(text).translate(FA_DIGITS)


def fmt_stat(value: float | int | None, decimals: int = 0) -> str | None:
    """عدد آماری با ارقام لاتین و ممیز لاتین — سیاست numerals_policy برند.

    None → None می‌ماند (null≠0؛ محل نمایش خودش «داده در دسترس نیست» را می‌نویسد).
    """
    if value is None:
        return None
    if decimals <= 0:
        return str(int(round(float(value))))
    s = f"{float(value):.{decimals}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def fmt_fixed(value: float | int | None, decimals: int) -> str | None:
    """عدد با اعشار ثابت — عین toFixed استودیو (۲.۰ → «2.00»، نه «2»).

    فقط در کارت استودیو برای نمایش استفاده می‌شود؛ fmt_stat (بدون صفرهای پایانی)
    برای ذخیره/متن تحریریه می‌ماند.
    """
    if value is None:
        return None
    return f"{float(value):.{decimals}f}"


def _parse_utc(iso: str) -> datetime:
    s = str(iso).strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def jalali_date(iso: str) -> str:
    """تاریخ جلالی فارسی — «یکشنبه ۱۷ آبان ۱۴۰۵» با ارقام فارسی."""
    import jdatetime

    dt = _parse_utc(iso)
    j = jdatetime.date.fromgregorian(date=dt.date())
    weekday = jdatetime.date.j_weekdays_fa[j.weekday()]
    return f"{weekday} {fa_digits(j.day)} {j.j_months_fa[j.month - 1]} {fa_digits(j.year)}"


def tehran_clock(iso: str) -> str | None:
    """ساعت کیک‌آف به وقت تهران با ارقام فارسی؛ None = ساعت در منبع نبود.

    CSV football-data.co.uk ساعت ندارد (فقط تاریخ) → None → کارت فقط تاریخ نشان می‌دهد.
    """
    dt = _parse_utc(iso)
    if (dt.hour, dt.minute, dt.second) == (0, 0, 0):
        return None
    return fa_digits(dt.astimezone(TEHRAN).strftime("%H:%M"))


def season_short(season: str) -> str:
    """«2026-27» → «26/27»؛ ورودی‌های دیگر دست‌نخورده برمی‌گردند."""
    parts = str(season).split("-")
    if len(parts) == 2 and len(parts[0]) == 4 and len(parts[1]) == 2:
        return f"{parts[0][2:]}/{parts[1]}"
    return str(season)


# ─── ابزارهای رنگ (port از getLuminance/getContrastText استودیو) ───

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
    """متن روی رنگ پُرشده — روشن یا تیره (port از getContrastText استودیو)."""
    return "#070D1D" if _luminance(hex_color) > 0.55 else "#F8FAFC"


def _color_distance(a: str, b: str) -> float:
    ra, ga, ba = _hex_to_rgb(a)
    rb, gb, bb = _hex_to_rgb(b)
    return (ra - rb) ** 2 + (ga - gb) ** 2 + (ba - bb) ** 2


def _color_dist_hsl(a: str, b: str) -> float:
    """فاصلهٔ Hue دو رنگ — برای دوتایی‌هایی که روشنایی‌شان فرق دارد ولی رنگ‌شان نزدیک است."""
    ra, ga, ba = _hex_to_rgb(a)
    rb, gb, bb = _hex_to_rgb(b)
    ha = colorsys.rgb_to_hls(ra / 255, ga / 255, ba / 255)[0]
    hb = colorsys.rgb_to_hls(rb / 255, gb / 255, bb / 255)[0]
    dh = abs(ha - hb)
    return min(dh, 1 - dh) * 360  # بر حسب درجه


def display_colors(
    home_ident: dict | None, away_ident: dict | None, fallback: str
) -> tuple[str, str]:
    """رنگ نمایشی دو تیم — سیاست team_identities.display_color_rule.

    میزبان همیشه رنگ اصلی رسمی. میهمان رنگ اصلی رسمی؛ فقط اگر با رنگ میزبان
    نزدیک بود (فاصلهٔ ایوکلیدس یا فاصلهٔ Hue زیر آستانه) رنگ ثانویه، و اگر آن هم
    نزدیک بود، رنگ ذخیرهٔ contrast (آبی‌آسمانی روشن) — تا دو تیم هرگز یک‌شکل نباشند.
    تیم بدون هویت → fallback بی‌طرف.
    """
    hc = (home_ident or {}).get("colors", {}).get("primary") or fallback
    ac = (away_ident or {}).get("colors", {}).get("primary") or fallback
    if _color_distance(hc, ac) >= COLOR_NEAR_THRESHOLD and _color_dist_hsl(hc, ac) >= 25:
        return hc, ac
    alt = (away_ident or {}).get("colors", {}).get("secondary") or fallback
    if _color_distance(hc, alt) >= COLOR_NEAR_THRESHOLD or _color_dist_hsl(hc, alt) >= 25:
        return hc, alt
    return hc, fallback


# ─── SVGهای استودیو (port از buildBrandLogoSVG/renderTeamCrest) ───

def _brand_lockup_svg(mono: bool = False) -> str:
    """لوگوی متنی استودیو (سپر XG + XGPedia + FOOTBALL ANALYTICS) — svg درون‌خطی، عین استودیو."""
    p = _palette()
    pedia_fill = "#FFFFFF" if mono else p["text_bright"]
    xg_fill = "#FFFFFF" if mono else p["accent_red"]
    shield_fill = "rgba(255,255,255,0.12)" if mono else p["navy_shield"]
    shield_stroke = "#FFFFFF" if mono else p["accent_red"]
    ring_stroke = "rgba(255,255,255,0.4)" if mono else "rgba(248,250,252,0.28)"
    sub_text_fill = "rgba(255,255,255,0.75)" if mono else p["text_slate"]
    return (
        '<div class="masthead-lockup" dir="ltr">'
        '<svg width="54" height="54" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">'
        f'<path d="M24 2.5L42 10.2V23.4C42 34.6 34.3 43 24 45.6C13.7 43 6 34.6 6 23.4V10.2L24 2.5Z" fill="{shield_fill}" stroke="{shield_stroke}" stroke-width="2.6"/>'
        f'<circle cx="24" cy="24" r="9.5" stroke="{ring_stroke}" stroke-width="1.5"/>'
        f'<line x1="24" y1="9" x2="24" y2="39" stroke="{ring_stroke}" stroke-width="1.2" stroke-dasharray="2.5 2.5"/>'
        f'<path d="M16.5 16.5L31.5 31.5M31.5 16.5L16.5 31.5" stroke="{xg_fill}" stroke-width="3.2" stroke-linecap="round"/>'
        f'<circle cx="24" cy="24" r="3" fill="{pedia_fill}"/>'
        "</svg>"
        '<div class="lockup-text">'
        f'<div class="lockup-brand"><span style="color: {xg_fill};">XG</span><span style="color: {pedia_fill};">Pedia</span></div>'
        f'<span class="lockup-sub" style="color: {sub_text_fill};">FOOTBALL ANALYTICS</span>'
        "</div></div>"
    )


def _crest_badge_svg(team: dict, side: str) -> str:
    """نشان انتزاعی یک‌دست تیم — عین renderTeamCrest استودیو (بدون لوگوی رسمی).

    تیم بدون فایل لوگو (brand/crests/{CODE}.svg|png) با همین نشانِ ساخته‌شده از
    رنگ اصلی/ثانویه + کد سه‌حرفی نمایش داده می‌شود — «طرح انتزاعی یک‌دست» خودِ استودیو.
    """
    p = team["primary"]
    s = team["secondary"]
    code = (team["code"] or "FC")[:3].upper()
    ink_color = _contrast_text(p)
    badge_pill_bg = "#0D1730" if _luminance(p) > 0.65 else "rgba(7, 13, 29, 0.55)"
    return (
        f'<svg width="178" height="178" viewBox="0 0 180 180" fill="none" xmlns="http://www.w3.org/2000/svg" style="filter: drop-shadow(0 16px 26px rgba(0,0,0,0.6));">'
        "<defs>"
        f'<linearGradient id="crestRim_{side}" x1="20" y1="15" x2="160" y2="165" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0%" stop-color="{s}" stop-opacity="0.95"/>'
        f'<stop offset="50%" stop-color="{p}" stop-opacity="0.9"/>'
        f'<stop offset="100%" stop-color="{s}" stop-opacity="0.7"/>'
        "</linearGradient>"
        f'<clipPath id="shieldClip_{side}">'
        '<path d="M90 16L150 40V88C150 128 124.5 156.5 90 166C55.5 156.5 30 128 30 88V40L90 16Z"/>'
        "</clipPath>"
        "</defs>"
        f'<path d="M90 12L154 38V88C154 130.5 127 160.5 90 170.5C53 160.5 26 130.5 26 88V38L90 12Z" fill="{p}" fill-opacity="0.22"/>'
        f'<g clip-path="url(#shieldClip_{side})">'
        f'<rect x="25" y="12" width="130" height="158" fill="{p}"/>'
        f'<path d="M25 112L155 56V84L25 140V112Z" fill="{s}" fill-opacity="0.28"/>'
        f'<path d="M90 16L150 40V58L90 34L30 58V40L90 16Z" fill="{s}" fill-opacity="0.9"/>'
        '<ellipse cx="90" cy="30" rx="65" ry="28" fill="#FFFFFF" fill-opacity="0.14"/>'
        "</g>"
        f'<path d="M90 16L150 40V88C150 128 124.5 156.5 90 166C55.5 156.5 30 128 30 88V40L90 16Z" stroke="url(#crestRim_{side})" stroke-width="4.5"/>'
        f'<path d="M90 23L143 44.5V87.5C143 123 120.5 148.5 90 157C59.5 148.5 37 123 37 87.5V44.5L90 23Z" stroke="{ink_color}" stroke-opacity="0.22" stroke-width="1.2"/>'
        f'<rect x="46" y="70" width="88" height="44" rx="12" fill="{badge_pill_bg}" stroke="{s}" stroke-opacity="0.45" stroke-width="1.5"/>'
        f'<text x="90" y="100" text-anchor="middle" fill="#F8FAFC" font-family="Space Grotesk, JetBrains Mono, sans-serif" font-weight="700" font-size="28" letter-spacing="2">{code}</text>'
        f'<circle cx="90" cy="134" r="4.5" fill="{ink_color}" fill-opacity="0.85"/>'
        "</svg>"
    )


def _crest_html(name_en: str, team: dict, side: str) -> str:
    """لوگوی واقعی (svg/png از brand/crests) اگر هست؛ وگرنه نشان انتزاعی استودیو."""
    path = team_crest_path(name_en)
    if path is not None:
        mime = "image/svg+xml" if path.suffix == ".svg" else "image/png"
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        return (
            f'<img src="data:{mime};base64,{b64}" alt="{team["name_fa"]}" '
            'class="crest-img" />'
        )
    return _crest_badge_svg(team, side)


# ─── هندسهٔ SVG ماژول‌های نموداری (port از استودیو) ───

def _smooth_spline(points: list[tuple[float, float]], tension: float = 0.25) -> str:
    """مسیر منحنی نرم Cubic Bezier — عین buildSmoothSpline استودیو."""
    if not points:
        return ""
    if len(points) == 1:
        return f"M {points[0][0]} {points[0][1]}"
    d = f"M {points[0][0]:.1f} {points[0][1]:.1f}"
    for i in range(len(points) - 1):
        p0 = points[0] if i == 0 else points[i - 1]
        p1, p2 = points[i], points[i + 1]
        p3 = points[i + 2] if i + 2 < len(points) else points[i + 1]
        cp1x = p1[0] + (p2[0] - p0[0]) * tension
        cp1y = p1[1] + (p2[1] - p0[1]) * tension
        cp2x = p2[0] - (p3[0] - p1[0]) * tension
        cp2y = p2[1] - (p3[1] - p1[1]) * tension
        d += (
            f" C {cp1x:.1f} {cp1y:.1f}, {cp2x:.1f} {cp2y:.1f}, {p2[0]:.1f} {p2[1]:.1f}"
        )
    return d


def _radar_context(h_vals: list[float], a_vals: list[float], hc: str, ac: str) -> dict:
    """رادار ۶ محوره — عین ماژول radar استودیو (حلقه‌ها، چندضلعی‌ها، برچسب‌ها)."""
    labels = ["خلق موقعیت", "شدت پرس", "ایستگاهی", "صلابت دفاعی", "مالکیت مؤثر", "تهدید پاس"]
    vb_w, vb_h, cx, cy, r = 450, 276, 225, 138, 84

    def coords(vals):
        out = []
        for i, v in enumerate(vals):
            ang = (-90 + i * 60) * (3.141592653589793 / 180)
            rr = (max(15, min(100, v)) / 100) * r
            out.append((cx + rr * _cos(ang), cy + rr * _sin(ang)))
        return out

    def ring(scale):
        pts = []
        for i in range(6):
            ang = (-90 + i * 60) * (3.141592653589793 / 180)
            pts.append(f"{cx + r * scale * _cos(ang):.1f},{cy + r * scale * _sin(ang):.1f}")
        return " ".join(pts)

    h_coords, a_coords = coords(h_vals), coords(a_vals)
    label_specs = [
        (cx, 20, "middle"),
        (cx + r * 0.866 + 14, cy - r * 0.5 - 4, "start"),
        (cx + r * 0.866 + 14, cy + r * 0.5 - 2, "start"),
        (cx, cy + r + 21, "middle"),
        (cx - r * 0.866 - 14, cy + r * 0.5 - 2, "end"),
        (cx - r * 0.866 - 14, cy - r * 0.5 - 4, "end"),
    ]
    label_groups = []
    for i, (lbl, (x, y, anchor)) in enumerate(zip(labels, label_specs)):
        label_groups.append({
            "x": f"{x:.1f}", "y": f"{y:.1f}", "y2": f"{y + 17:.1f}", "anchor": anchor,
            "label": lbl, "hv": fmt_stat(h_vals[i]), "av": fmt_stat(a_vals[i]),
            "hc": hc, "ac": ac,
        })
    return {
        "rings": [ring(1.0), ring(0.75), ring(0.5), ring(0.25)],
        "axes": [
            f"{cx} {cy - r} {cx} {cy + r}",
            f"{cx + r * 0.866:.1f} {cy - r * 0.5:.1f} {cx - r * 0.866:.1f} {cy + r * 0.5:.1f}",
            f"{cx + r * 0.866:.1f} {cy + r * 0.5:.1f} {cx - r * 0.866:.1f} {cy - r * 0.5:.1f}",
        ],
        "away_poly": " ".join(f"{x:.1f},{y:.1f}" for x, y in a_coords),
        "home_poly": " ".join(f"{x:.1f},{y:.1f}" for x, y in h_coords),
        "home_dots": [{"x": f"{x:.1f}", "y": f"{y:.1f}"} for x, y in h_coords],
        "labels": label_groups,
        "vb_w": vb_w, "vb_h": vb_h,
    }


def _cos(a: float) -> float:
    import math

    return math.cos(a)


def _sin(a: float) -> float:
    import math

    return math.sin(a)


def _trend_context(h_series: list[float], a_series: list[float], is_half: bool, hc: str, ac: str) -> dict:
    """روند xG بازی‌به‌بازی — عین ماژول trend10 استودیو با طول سری‌های دلخواه."""
    w = 420 if is_half else 880
    h_, pad_x, pad_y = 135, 22, 14
    p_w, p_h = w - pad_x * 2, h_ - pad_y * 2
    max_y = max(*h_series, *a_series, 2.6)

    def to_pts(series):
        n = len(series)
        return [
            (pad_x + (i / (n - 1)) * p_w, pad_y + p_h - (v / max_y) * p_h)
            for i, v in enumerate(series)
        ]

    h_pts, a_pts = to_pts(h_series), to_pts(a_series)
    return {
        "w": w, "h": h_,
        "grid_top": f"{pad_x} {pad_y} {w - pad_x} {pad_y}",
        "grid_bottom": f"{pad_x} {pad_y + p_h} {w - pad_x} {pad_y + p_h}",
        "away_path": _smooth_spline(a_pts, 0.22),
        "home_path": _smooth_spline(h_pts, 0.22),
        "home_dots": [
            {"x": f"{x:.1f}", "y": f"{y:.1f}", "i": str(i + 1)}
            for i, (x, y) in enumerate(h_pts)
        ],
        "home_avg": fmt_fixed(sum(h_series) / len(h_series), 2),
        "away_avg": fmt_fixed(sum(a_series) / len(a_series), 2),
        "hc": hc, "ac": ac,
    }


def _wave_context(h_wave: list[float], a_wave: list[float], is_half: bool, hc: str, ac: str) -> dict:
    """موج زمانی xG (بازه‌های ۱۵ دقیقه‌ای) — عین ماژول wave استودیو.

    داده‌اش هنوز در fact_json نیست (فاز بعدی: دیتای رویدادی) — کد محفوظ مانده.
    """
    mins = ["15'", "30'", "45'", "60'", "75'", "90'"]
    w = 420 if is_half else 880
    h_, pad_x, pad_y = 135, 26, 14
    p_w, p_h = w - pad_x * 2, h_ - pad_y * 2
    max_v = max(*h_wave, *a_wave, 0.48)

    def to_pts(arr):
        return [
            (pad_x + (i / 5) * p_w, pad_y + p_h - (v / max_v) * p_h)
            for i, v in enumerate(arr)
        ]

    h_pts, a_pts = to_pts(h_wave), to_pts(a_wave)
    home_path = _smooth_spline(h_pts, 0.25)
    away_path = _smooth_spline(a_pts, 0.25)
    return {
        "w": w, "h": h_,
        "area_path": (
            f"{home_path} L {h_pts[5][0]:.1f} {pad_y + p_h} L {h_pts[0][0]:.1f} {pad_y + p_h} Z"
        ),
        "away_path": away_path,
        "home_path": home_path,
        "dots": [
            {"x": f"{x:.1f}", "y": f"{y:.1f}", "m": mins[i]}
            for i, (x, y) in enumerate(h_pts)
        ],
        "grid": [
            f"{pad_x} {pad_y} {w - pad_x} {pad_y}",
            f"{pad_x} {pad_y + p_h / 2:.1f} {w - pad_x} {pad_y + p_h / 2:.1f}",
            f"{pad_x} {pad_y + p_h} {w - pad_x} {pad_y + p_h}",
        ],
        "hc": hc, "ac": ac,
    }


def _poisson_context(matrix: list[list[float]]) -> dict:
    """ماتریس ۵×۵ احتمال نتیجه — عین ماژول poisson استودیو (رنگ سلول‌ها همان فرمول)."""
    p = _palette()
    cells: list[dict] = []
    tops: list[tuple[str, float]] = []
    for h in range(5):
        for a in range(5):
            pct = matrix[h][a] * 100
            if h > a:
                base = "230,46,69"
            elif h == a:
                base = "100,116,139"
            else:
                base = "56,189,248"
            op = min(0.75, 0.08 + (pct / 13) * 0.65)
            cells.append({
                "h": h, "a": a,
                "score": f"{h}-{a}",
                "pct": fmt_stat(round(pct, 1), 1),
                "bg": f"rgba({base},{op:.2f})",
            })
            tops.append((f"{h}-{a}", pct))
    tops.sort(key=lambda x: -x[1])
    top3 = " • ".join(f"{score} ({fmt_stat(round(pct, 1), 1)}٪)" for score, pct in tops[:3])
    return {
        "cells": cells,
        "top3": top3,
        "col_hc": p["accent_red"],
        "col_ac": p["sky_bright"],
    }


# ─── پالت و فونت ───

_PALETTE_CACHE: dict | None = None


def _palette() -> dict:
    global _PALETTE_CACHE
    if _PALETTE_CACHE is None:
        _PALETTE_CACHE = load_brand()["matchday_palette"]
    return _PALETTE_CACHE


def _font_faces() -> list[dict]:
    """فونت‌های woff2 به‌صورت data URI — خروجی HTML خودبسنده می‌شود."""
    faces = []
    for name, family, weight in FONT_FILES:
        p = FONTS_DIR / name
        if not p.exists():
            raise FileNotFoundError(
                f"brand/fonts/{name} not found - re-extract the kit or run the font "
                "download step (see README: fonts must sit in brand/fonts/)"
            )
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        faces.append({"family": family, "weight": weight, "data": f"data:font/woff2;base64,{b64}"})
    return faces


# ─── تیم‌ها ───

def _team_side_ctx(side: dict, ident: dict | None, display_color: str, side_key: str) -> dict:
    """هویت کامل یک طرف کارت از فکت‌ها + فایل هویت تیم."""
    p = _palette()
    colors = (ident or {}).get("colors") or {}
    form_seq = side.get("recent_form") or {}
    form = [f for f in str(form_seq.get("sequence", "")) if f in FORM_LABELS]
    series = side.get("xg_series")
    series = [float(x) for x in series] if series and len(series) >= 2 else None
    return {
        "name_fa": side.get("name_fa", ""),
        "name_en": side.get("name_en", ""),
        "code": (ident or {}).get("code") or (side.get("name_en") or "FC")[:3].upper(),
        "primary": colors.get("primary") or display_color,
        "secondary": colors.get("secondary") or p["text_bright"],
        "color": display_color,  # رنگ نمایشی در میله‌ها/کپسول/رادار
        "form": form,
        "form_dots": [{"f": f, "label": FORM_LABELS[f]} for f in form],
        "xg": (side.get("xg_for_avg") or {}).get("value"),
        "xga": (side.get("xg_against_avg") or {}).get("value"),
        "sot": (side.get("sot_avg") or {}).get("value"),
        "corners": (side.get("corners_avg") or {}).get("value"),
        "xg_series": series,
        "sub": None,        # مربی/جملهٔ توضیحی — منبعی ندارد؛ فاز بعدی (دادهٔ تیم)
        "kp": None,         # مهرهٔ کلیدی — فاز بعدی (پک آمار بازیکن)
        "watchout": None,   # هشدار اختصاصی تیم — فاز بعدی
        "radar": None,      # صدک‌های شش‌محوره — فاز بعدی (پک دادهٔ صدک)
        "wave": None,       # xG بازه‌ای ۱۵ دقیقه — فاز بعدی (دیتای رویدادی)
        "_side": side_key,
    }


# ─── ماژول‌ها: انتخاب نسخه (port از applyVersion استودیو) ───

def _select_modules(version: str, has: dict[str, bool]) -> list[dict]:
    """نسخهٔ چیدمان — smart داده‌محور است؛ بقیه نسخه‌های ثابت استودیو.

    ماژولی که داده‌اش در fact_json نیست در هیچ نسخه‌ای روشن نمی‌شود (کدش در
    قالب محفوظ است تا وقتی داده‌اش خریداری/تولید شد فقط داده اضافه شود).
    """
    presets = {
        "v1": [("stats", "full"), ("radar", "half"), ("focus", "half"), ("keyduel", "full")],
        "v2": [("stats", "full"), ("poisson", "half"), ("wave", "half"), ("signals", "full")],
        "v3": [("stats", "full"), ("trend10", "half"), ("watchout", "half"), ("keyduel", "full")],
    }
    if version == "smart":
        preset = [("stats", "full")]
        for mod in ("radar", "focus", "keyduel", "watchout"):
            if has.get(mod):
                preset.append((mod, "half"))
        preset.append(("signals", "full"))
    else:
        preset = presets.get(version, presets["v1"])
    selected = [
        {"id": mod_id, "enabled": has.get(mod_id, False), "span": span}
        for mod_id, _can_half, default_span in MODULE_DEFS
        for span in [next((s for m, s in preset if m == mod_id), default_span)]
        if any(m == mod_id for m, _s in preset)
    ]
    # نیم‌عرضِ یتیم (بدون جفت در همان ردیف grid) تمام‌عرض می‌شود تا خانهٔ خالی نماند
    enabled_halves = [m for m in selected if m["enabled"] and m["span"] == "half"]
    if len(enabled_halves) % 2 == 1:
        enabled_halves[-1]["span"] = "full"
    return selected


# ─── ساخت context کارت ───

def build_preview_context(
    draft: dict,
    facts: dict,
    post_type: str = "preview",
    brand: dict | None = None,
    layout: str = "smart",
    fmt: str = "4:5",
) -> dict:
    """context کامل قالب استودیو از draft + fact + brand + team_identities.

    همهٔ اعداد از fact_json می‌آیند؛ متن‌ها از draft_json؛ رنگ برند از brand.json؛
    رنگ/کد تیم از team_identities.json. layout: smart | v1 | v2 | v3.
    fmt: 4:5 | 9:16 | 16:9 (ابعاد و هندسهٔ چیدمان).
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

    # ── احتمال‌های ۱X۲ — مشتق قطعی Dixon-Coles از دو عدد xG فکت‌ها ──
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

    # ── هندسهٔ بوم و پس‌زمینهٔ محیطی ──
    w, hgt = FORMATS.get(fmt, FORMATS["4:5"])
    inset = 12
    pitch = {
        "w": w, "h": hgt,
        "perimeter": f"{inset} {inset} {w - inset * 2} {hgt - inset * 2}",
        "halfway": f"{w // 2} {inset} {w // 2} {hgt - inset}",
        "right_box_x": w - inset - 135,
        "right_arc": f"M{w - inset - 135} 245 A 95 95 0 0 0 {w - inset - 135} 405",
        "crosshairs": _crosshairs(w, hgt, inset),
        "ambient": (
            f"radial-gradient(circle at 86% 32%, {hc}38 0%, transparent 48%),"
            f"radial-gradient(circle at 14% 32%, {ac}38 0%, transparent 48%),"
            f"radial-gradient(circle at 50% 36%, rgba(230, 46, 69, 0.14) 0%, transparent 52%)"
        ),
    }

    # ── ردیف‌های ماژول مقایسه — فقط وقتی هر دو طرف مقدار دارند (مقایسهٔ نیمه‌خالی گمراه‌کننده است) ──
    stat_rows = []
    for label, hkey, akey, dec in (
        ("امید گل تولیدی (xG / 90)", "xg", "xg", 2),
        ("امید گل دریافتی (xGA / 90)", "xga", "xga", 2),
        ("شوت در چارچوب (SOT / 90)", "sot", "sot", 1),
    ):
        hv, av = home[hkey], away[akey]
        if hv is None or av is None:
            continue
        max_v = max(hv, av, 0.01)
        stat_rows.append({
            "label": label,
            "h": fmt_fixed(hv, dec), "a": fmt_fixed(av, dec),
            "h_pct": f"{hv / max_v * 100:.1f}", "a_pct": f"{av / max_v * 100:.1f}",
        })

    # ── ماژول نقطهٔ تمرکز — از متن تحریریه (draft) ──
    bullets = [x for x in draft.get("bullets", []) if x]
    prov = facts.get("source", {}).get("provider", "")
    focus = None
    if draft.get("title") and bullets:
        focus = {
            "title": draft["title"],
            "body_lines": bullets[:3],
            "tag": f"داده: {prov}" if prov else "",
        }

    # ── ماژول‌های نموداری با داده ──
    radar_ctx = None
    if home["radar"] and away["radar"]:
        radar_ctx = _radar_context(home["radar"], away["radar"], hc, ac)
    trend_ctx = None
    if home["xg_series"] and away["xg_series"]:
        trend_ctx = _trend_context(home["xg_series"], away["xg_series"], True, hc, ac)
    wave_ctx = None
    if home["wave"] and away["wave"]:
        wave_ctx = _wave_context(home["wave"], away["wave"], True, hc, ac)
    poisson_ctx = _poisson_context(dc["matrix"]) if dc else None

    # ── ماژول سیگنال‌ها — فقط احتمال‌های مشتق‌شده؛ badge EV فقط با دادهٔ ضریب (فاز بعدی) ──
    signal_cards = []
    if probs:
        signal_cards.append({
            "tone": "emerald",
            "badge": None,
            "title": "گل بالای ۲.۵",
            "desc": "نرخ بالای خلق xG",
            "value": fmt_fixed(round(dc["pO25"] * 100, 1), 1),
        })
        signal_cards.append({
            "tone": "sky",
            "badge": None,
            "title": "گلزنی هر دو تیم",
            "desc": "تهدید هجومی دوطرفه",
            "value": fmt_fixed(round(dc["pBTTS"] * 100, 1), 1),
        })
    if home["corners"] is not None:
        signal_cards.append({
            "tone": "amber",
            "badge": None,
            "title": "کرنر میزبان",
            "desc": "میانگین کرنر در بازی‌های اخیر",
            "value": fmt_fixed(home["corners"], 1),
        })
    signals_ctx = {"cards": signal_cards} if signal_cards else None

    has = {
        "stats": bool(stat_rows),
        "radar": radar_ctx is not None,
        "focus": focus is not None,
        "watchout": bool(home["watchout"] and away["watchout"]),
        "keyduel": bool(home["kp"] and away["kp"]),
        "poisson": poisson_ctx is not None,
        "wave": wave_ctx is not None,
        "trend10": trend_ctx is not None,
        "signals": signals_ctx is not None,
    }
    modules = _select_modules(layout, has)

    # ── هدر و پانویس ──
    comp_en = facts.get("competition", {}).get("name", "")
    season = facts.get("competition", {}).get("season", "")
    kickoff = facts.get("kickoff_utc", "")
    date_line = jalali_date(kickoff) if kickoff else ""
    clock = tehran_clock(kickoff)

    week_code = facts.get("matchday")
    week_part = f"W{week_code}" if isinstance(week_code, int) else (week_code or "")
    micro_tag = " ".join(
        x for x in (
            (comp_en or "FOOTBALL").upper(),
            season_short(season) if season else "",
            week_part,
        ) if x
    ) + " // PRE - MATCH"

    n_xg = ((home_f.get("xg_for_avg") or {}).get("n"))
    stat_n = f"n={n_xg}" if n_xg is not None else None

    # مهرهٔ کلیدی هر طرف + هشدارها — در fact_json نیستند؛ فاز بعدی ماژولار فعال می‌شوند

    hero = {
        "xg_home": fmt_fixed(home["xg"], 2),
        "xg_away": fmt_fixed(away["xg"], 2),
        "xg_total": fmt_fixed((home["xg"] or 0) + (away["xg"] or 0), 2)
        if home["xg"] is not None and away["xg"] is not None else None,
        "probs": probs,
        "xpts_home": fmt_fixed(expected_points(probs["home"] / 100, probs["draw"] / 100, probs["away"] / 100)[0], 2) if probs else None,
        "xpts_away": fmt_fixed(expected_points(probs["home"] / 100, probs["draw"] / 100, probs["away"] / 100)[1], 2) if probs else None,
        "capsule": None,
        "odds": None,
    }
    if probs:
        hero["capsule"] = [
            {"id": "home", "pct": probs["home"], "bg": hc, "color": _contrast_text(hc)},
            {"id": "draw", "pct": probs["draw"], "bg": p["draw_grey"], "color": p["text_bright"]},
            {"id": "away", "pct": probs["away"], "bg": ac, "color": _contrast_text(ac)},
        ]
        hero["odds"] = {
            "home": fmt_fixed(round(100 / max(1, probs["home"]), 2), 2),
            "draw": fmt_fixed(round(100 / max(1, probs["draw"]), 2), 2),
            "away": fmt_fixed(round(100 / max(1, probs["away"]), 2), 2),
            # لنگر ضریب مساوی زیر مرکز پارهٔ مساوی کپسول — عین استودیو
            "draw_anchor_pct": f"{min(73, max(27, probs['home'] + probs['draw'] / 2)):.1f}",
        }

    return {
        "palette": p,
        "fonts": _font_faces(),
        "brand_name": b.get("brand", "XGPedia"),
        "brand_lockup_html": _brand_lockup_svg(False),
        "handle": "@xgpedia",
        "domain": (b.get("handles", {}).get("domain") or ["xgpedia.com"])[0],
        "na_label": NO_DATA,
        "format": {"key": fmt, "w": w, "h": hgt, "is_wide": fmt == "16:9", "is_tall": fmt == "9:16"},
        "pitch": pitch,
        "competition_fa": COMPETITION_FA.get(comp_en, comp_en),
        "round": facts.get("round"),
        "stadium": facts.get("stadium"),
        "broadcast": facts.get("broadcast"),
        "day": date_line,
        "time": clock,
        "micro_tag": micro_tag,
        "source_label": f"منبع: {prov}" if prov else "",
        "stat_n": stat_n,
        "home": home,
        "away": away,
        "hero": hero,
        "modules": modules,
        "module_data": {
            "stats": {"rows": stat_rows, "n": stat_n},
            "radar": radar_ctx,
            "focus": focus,
            "watchout": {"home_text": home["watchout"], "away_text": away["watchout"]} if has["watchout"] else None,
            "keyduel": {"home": home["kp"], "away": away["kp"]} if has["keyduel"] else None,
            "poisson": poisson_ctx,
            "wave": wave_ctx,
            "trend10": trend_ctx,
            "signals": signals_ctx,
        },
    }


def _crosshairs(w: int, h: int, inset: int) -> str:
    """چهار صلیب کالیبراسیون گوشه‌ها — عین فرمول استودیو."""
    c1, c2 = inset + 12, inset + 32
    rx1, rx2 = w - c1, w - c2
    by1, by2 = h - c1, h - c2
    return (
        f"M{c1} {c2}V{c1}H{c2}M{rx1} {c2}V{c1}H{rx2}"
        f"M{c1} {by2}V{by1}H{c2}M{rx1} {by2}V{by1}H{rx2}"
    )


def _ensure_palette_cached(b: dict) -> None:
    """وقتی brand از بیرون تزریق می‌شود (تست‌ها)، کش پالت هم‌گام شود."""
    global _PALETTE_CACHE
    _PALETTE_CACHE = b["matchday_palette"]


# ─── رندر ───

def render_preview_html(
    draft: dict,
    facts: dict,
    post_type: str = "preview",
    layout: str = "smart",
    fmt: str = "4:5",
) -> str:
    """پر کردن قالب استودیو و برگرداندن HTML کامل (خودبسنده — فونت جاسازی‌شده)."""
    from jinja2 import Environment, FileSystemLoader

    env = Environment(autoescape=True, loader=FileSystemLoader(str(TEMPLATES_DIR)))
    ctx = build_preview_context(draft, facts, post_type=post_type, layout=layout, fmt=fmt)
    return env.get_template("match_preview.html.j2").render(**ctx)


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
) -> tuple[Path, Path, Path]:
    """رندر کامل یک پست: HTML میانی + تصویر نهایی + فایل کپشن آمادهٔ انتشار.

    قالب‌های تصویر (همان سه دکمهٔ استودیو): 4:5 → 1080×1350 پیش‌فرض؛
    9:16 → 1080×1920 استوری؛ 16:9 → 1920×1080 بنر.
    تلگرام/سایت PNG؛ اینستاگرام JPEG (الزام API).
    """
    from src.xgpedia.render.render_png import render_sync

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    w, hgt = FORMATS.get(fmt, FORMATS["4:5"])
    stem = f"post_{post_id}_v{version}_{post_type}"
    html_path = out / f"{stem}_{w}x{hgt}.html"
    html_path.write_text(
        render_preview_html(draft, facts, post_type=post_type, layout=layout, fmt=fmt),
        encoding="utf-8",
    )

    img_fmt = "jpeg" if platform == "instagram" else "png"
    img_path = out / f"{stem}_{w}x{hgt}.{img_fmt}"
    render_sync(str(html_path), str(img_path), w, hgt, img_fmt)

    caption = (draft.get("caption") or "").strip()
    tag = HASHTAG_BY_TYPE.get(post_type)
    cap_path = out / f"post_{post_id}_v{version}_caption.txt"
    cap_path.write_text(caption + (f"\n\n{tag}" if tag else ""), encoding="utf-8")

    return html_path, img_path, cap_path


HASHTAG_BY_TYPE = {
    "preview": "#پیش_بازی",
    "post_match": "#پس_از_بازی",
    "number_of_day": "#عدد_روز",
}
