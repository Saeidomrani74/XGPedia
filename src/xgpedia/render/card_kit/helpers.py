"""ابزارهای مشترک معماری ماژولار کارت‌های XGPedia (`card_kit`)."""
from __future__ import annotations

import functools

import html
import math
from typing import Any

FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa(val: Any) -> str:
    """تبدیل ارقام به فارسی با حفظ امن HTML."""
    return str(val).translate(FA_DIGITS)


def esc(val: Any) -> str:
    return html.escape(str(val or ""))


def f1(v: float) -> str:
    return f"{float(v):.1f}"


def f2(v: float) -> str:
    return f"{float(v):.2f}"


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    c = (h or "#E62E45").lstrip("#")
    if len(c) == 3:
        c = "".join(x + x for x in c)
    n = int(c, 16) if len(c) == 6 else 0
    return (n >> 16) & 255, (n >> 8) & 255, n & 255


def luminance(h: str) -> float:
    r, g, b = _hex_to_rgb(h)
    a = [(v / 255) / 12.92 if (v / 255) <= 0.03928 else (((v / 255) + 0.055) / 1.055) ** 2.4 for v in (r, g, b)]
    return a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722


def contrast_ink(h: str) -> str:
    return "#070D1D" if luminance(h) > 0.55 else "#FFFFFF"

def wcag_contrast(h1: str, h2: str) -> float:
    """نسبت کنتراست استاندارد WCAG 2.1 بین دو رنگ hex (محدوده ۱ تا ۲۱)."""
    l1, l2 = luminance(h1), luminance(h2)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{max(0, min(255, r)):02X}{max(0, min(255, g)):02X}{max(0, min(255, b)):02X}"


def _color_distance(h1: str, h2: str) -> float:
    r1, g1, b1 = _hex_to_rgb(h1)
    r2, g2, b2 = _hex_to_rgb(h2)
    return math.sqrt((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2)


def ensure_dark_bg_contrast(
    hex_color: str,
    *,
    bg: str = "#0D1730",
    min_ratio: float = 4.8,
    secondary: str | None = None,
) -> str:
    """تضمین خوانایی رنگ تیم روی پس‌زمینهٔ سرمه‌ای تیره (`#0D1730`) با حفظ هویت رنگی باشگاه.

    - اگر کنتراست رنگ اصلی کافی باشد (`>= min_ratio`)، عیناً حفظ می‌شود.
    - برای رنگ‌های مشکی/خاکستری خیلی تیره (مثل نیوکاسل `#241F20`)، از نقره‌ای-سفید خوانا (`#E2E8F0`) یا رنگ دوم روشن استفاده می‌شود.
    - برای رنگ‌های رنگی تیره (مثل تاتنهام `#132257`، چلسی `#034694`، اورتون `#003399`، استون‌ویلا `#670E36`)،
      فام (Hue) اصلی باشگاه دقیقاً حفظ شده و صرفاً روشنایی (Lightness) در فضای HSL تا رسیدن به کنتراست WCAG AA بالا برده می‌شود.
    """
    import colorsys

    col = (hex_color or "#38BDF8").strip()
    if not col.startswith("#"):
        col = f"#{col}"
    if wcag_contrast(col, bg) >= min_ratio:
        return col.upper()

    r, g, b = _hex_to_rgb(col)
    h, l_val, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)

    # رنگ‌های خنثی/مشکی (مثل نیوکاسل): استفاده از رنگ دوم روشن یا نقره‌ای روشن خوانا
    if s < 0.16 and l_val < 0.28:
        if secondary and wcag_contrast(secondary, bg) >= min_ratio:
            return secondary.upper()
        return "#E2E8F0"

    # حفظ دقیق Hue باشگاه + اشباع زنده + جست‌وجوی دودویی Lightness تا رسیدن به min_ratio
    target_s = max(s, 0.74)
    lo, hi = max(l_val, 0.30), 0.92
    best = col.upper()
    for _ in range(18):
        mid = (lo + hi) / 2.0
        rr, gg, bb = colorsys.hls_to_rgb(h, mid, target_s)
        cand = _rgb_to_hex(int(round(rr * 255)), int(round(gg * 255)), int(round(bb * 255)))
        if wcag_contrast(cand, bg) >= min_ratio:
            best = cand
            hi = mid
        else:
            lo = mid
    return best


def resolve_visible_team_colors(
    home: dict[str, Any],
    away: dict[str, Any],
    *,
    bg: str = "#0D1730",
    min_ratio: float = 4.8,
) -> tuple[str, str]:
    """محاسبهٔ جفت رنگ خوانا و متمایز برای میزبان و میهمان روی پس‌زمینهٔ تیره."""
    hc = ensure_dark_bg_contrast(
        str(home.get("color") or "#E62E45"),
        bg=bg,
        min_ratio=min_ratio,
        secondary=home.get("secondary"),
    )
    ac = ensure_dark_bg_contrast(
        str(away.get("color") or "#38BDF8"),
        bg=bg,
        min_ratio=min_ratio,
        secondary=away.get("secondary"),
    )
    # جلوگیری از نزدیک‌بودن بیش‌ازحد دو رنگ پس از روشن‌سازی (مثلاً دو تیم آبی یا دو تیم سفید/نقره‌ای)
    if _color_distance(hc, ac) < 95.0:
        sec = away.get("secondary")
        if sec:
            sec_vis = ensure_dark_bg_contrast(str(sec), bg=bg, min_ratio=min_ratio)
            if _color_distance(hc, sec_vis) >= 95.0:
                ac = sec_vis
        if _color_distance(hc, ac) < 95.0:
            for fb in ("#38BDF8", "#FBBF24", "#34D399", "#F472B6"):
                if _color_distance(hc, fb) >= 110.0:
                    ac = fb
                    break
    return hc, ac


def smooth_spline(pts: list[tuple[float, float]], tension: float = 0.25) -> str:
    """منحنی نرم Cubic Bezier برای نمودارهای روند و موج."""
    if not pts:
        return ""
    if len(pts) == 1:
        return f"M{f1(pts[0][0])} {f1(pts[0][1])}"
    parts = [f"M{f1(pts[0][0])} {f1(pts[0][1])}"]
    for i in range(1, len(pts)):
        p0 = pts[i - 2] if i >= 2 else pts[0]
        p1 = pts[i - 1]
        p2 = pts[i]
        p3 = pts[i + 1] if i + 1 < len(pts) else p2
        c1x = p1[0] + (p2[0] - p0[0]) * tension
        c1y = p1[1] + (p2[1] - p0[1]) * tension
        c2x = p2[0] - (p3[0] - p1[0]) * tension
        c2y = p2[1] - (p3[1] - p1[1]) * tension
        parts.append(f"C{f1(c1x)} {f1(c1y)},{f1(c2x)} {f1(c2y)},{f1(p2[0])} {f1(p2[1])}")
    return " ".join(parts)


def team_crest_svg_or_img(team: dict[str, Any], side: str, size: int) -> str:
    """لوگوی واقعی تیم (data-URI) یا سپر انتزاعی استودیو با رنگ رسمی تیم."""
    ds = "filter:drop-shadow(0 12px 22px rgba(0,0,0,0.55))"
    logo = team.get("logoUrl")
    if logo:
        return (
            f'<img src="{logo}" alt="{esc(team.get("name", ""))}" '
            f'style="width:{size}px;height:{size}px;object-fit:contain;{ds};display:block;">'
        )
    p = team.get("color") or "#EF0107"
    s = team.get("secondary") or "#FFFFFF"
    cd = esc((team.get("code") or "FC")[:3].upper())
    u = f"{side}_{size}"
    d = "M90 16L150 40V88C150 128 124.5 156.5 90 166C55.5 156.5 30 128 30 88V40Z"
    pill_bg = "#0D1730" if luminance(p) > 0.65 else "rgba(7,13,29,0.62)"
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 180 180" fill="none" style="{ds};display:block;">'
        f'<defs><linearGradient id="g{u}" x1="20" y1="15" x2="160" y2="165" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{s}" stop-opacity=".95"/><stop offset=".5" stop-color="{p}" stop-opacity=".92"/>'
        f'<stop offset="1" stop-color="{s}" stop-opacity=".72"/></linearGradient>'
        f'<clipPath id="c{u}"><path d="{d}"/></clipPath></defs>'
        f'<path d="M90 12L154 38V88C154 130.5 127 160.5 90 170.5C53 160.5 26 130.5 26 88V38Z" fill="{p}" fill-opacity=".22"/>'
        f'<g clip-path="url(#c{u})"><rect x="25" y="12" width="130" height="158" fill="{p}"/>'
        f'<path d="M25 112L155 56V84L25 140Z" fill="{s}" fill-opacity=".28"/>'
        f'<path d="M90 16L150 40V58L90 34L30 58V40Z" fill="{s}" fill-opacity=".9"/>'
        f'<ellipse cx="90" cy="30" rx="65" ry="28" fill="#fff" fill-opacity=".14"/></g>'
        f'<path d="{d}" stroke="url(#g{u})" stroke-width="5"/>'
        f'<rect x="42" y="68" width="96" height="48" rx="14" fill="{pill_bg}" stroke="{s}" stroke-opacity=".52" stroke-width="2"/>'
        f'<text x="90" y="102" text-anchor="middle" fill="#fff" font-family="Space Grotesk,JetBrains Mono,sans-serif" font-weight="800" font-size="32" letter-spacing="2">{cd}</text>'
        f'<circle cx="90" cy="136" r="5" fill="{contrast_ink(p)}" fill-opacity=".85"/></svg>'
    )


def module_header(title: str, right_html: str = "", accent: str = "#E62E45", is_half: bool = False) -> str:
    """سرصفحهٔ یکپارچهٔ هر ماژول با پشتیبانی از حالت نیم‌عرض و تمام‌عرض."""
    right_block = f'<div class="mh-right">{right_html}</div>' if right_html else ""
    return (
        f'<div class="mh{" mh-half" if is_half else ""}">'
        f'<div class="mh-left">'
        f'<span class="mh-bar" style="background:{accent};"></span>'
        f'<h3 class="mh-title">{esc(title)}</h3>'
        f'</div>'
        f'{right_block}'
        f'</div>'
    )


def team_legend_html(home_name: str, away_name: str, hc: str, ac: str, is_half: bool = False) -> str:
    cls = "mod-legend mod-legend-half" if is_half else "mod-legend"
    return (
        f'<div class="{cls}">'
        f'<span class="leg-item"><span class="leg-dot" style="background:{hc}"></span>{esc(home_name)}</span>'
        f'<span class="leg-item"><span class="leg-dot" style="background:{ac}"></span>{esc(away_name)}</span>'
        f'</div>'
    )


def dixon_coles_5x5(lh: float, la: float) -> list[list[float]]:
    """ماتریس احتمال نتیجه پواسون/Dixon-Coles ۵×۵ (قطعی، بدون ورودی خارجی)."""
    facts = [1, 1, 2, 6, 24, 120, 720]
    mat: list[list[float]] = []
    for h in range(5):
        row: list[float] = []
        for a in range(5):
            tau = (
                1 + lh * la * 0.07 if (h == 0 and a == 0)
                else 1 - lh * 0.07 if (h == 0 and a == 1)
                else 1 - la * 0.07 if (h == 1 and a == 0)
                else 1.07 if (h == 1 and a == 1)
                else 1.0
            )
            p = max(0.0, (lh ** h * math.exp(-lh) / facts[h]) * (la ** a * math.exp(-la) / facts[a]) * tau)
            row.append(p)
        mat.append(row)
    return mat


def is_sample_preset(item: dict[str, Any] | None) -> bool:
    """تشخیص آیتم پریست/نمونه برای نمایش برچسب آشکار «نمونه / SAMPLE» روی کارت."""
    if not isinstance(item, dict):
        return False
    if item.get("is_preset") is True or item.get("is_sample") is True:
        return True
    item_id = str(item.get("id") or "").strip().lower()
    return item_id.startswith("preset_") or item_id.startswith("sample_")


def sample_badge_html(item: dict[str, Any] | None) -> str:
    """برچسب گرافیکی خوانا و غیرقابل‌اغماض برای کارت‌های پریست/نمونه."""
    if not is_sample_preset(item):
        return ""
    return (
        '<span class="xg-sample-pill" '
        'style="display:inline-flex;align-items:center;gap:6px;padding:5px 14px;border-radius:999px;'
        'font-size:16px;font-weight:900;background:rgba(245,158,11,.22);'
        'border:1.5px solid rgba(251,191,36,.75);color:#FDE68A;letter-spacing:.03em">'
        'نمونه • SAMPLE</span>'
    )


def inject_sample_badge_html(html: str, item: dict[str, Any] | None) -> str:
    """درج برچسب آشکار «نمونه استودیو • SAMPLE» در HTML هر کارت هنگام رندر آیتم پریست/نمونه."""
    if not html or not is_sample_preset(item) or "xg-sample-pill" in html:
        return html
    pill = (
        '<div class="xg-sample-pill" dir="rtl" '
        'style="position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:9999;'
        'display:inline-flex;align-items:center;gap:6px;padding:5px 16px;border-radius:999px;'
        "font-family:'Vazirmatn',system-ui,sans-serif;font-size:15px;font-weight:900;"
        'background:rgba(15,23,42,.92);border:1.5px solid rgba(251,191,36,.85);color:#FDE68A;'
        'box-shadow:0 8px 24px rgba(0,0,0,.45);letter-spacing:.03em;pointer-events:none">'
        'نمونه استودیو • SAMPLE</div>'
    )
    if "</body>" in html:
        return html.replace("</body>", f"{pill}\n</body>", 1)
    return html + pill


def with_sample_badge(fn):
    """دکوراتور یکپارچه برای تزریق خودکار نشان «نمونه • SAMPLE» روی خروجی تمام کارت‌های استودیو."""
    @functools.wraps(fn)
    def _wrapped(*args, **kwargs):
        html = fn(*args, **kwargs)
        item = args[0] if args else next(iter(kwargs.values()), None)
        return inject_sample_badge_html(html, item if isinstance(item, dict) else None)
    return _wrapped
