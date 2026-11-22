"""ابزارهای مشترک معماری ماژولار کارت‌های XGPedia (`card_kit`)."""
from __future__ import annotations

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
    return (
        f'<div class="mh{" mh-half" if is_half else ""}">'
        f'<div class="mh-left">'
        f'<span class="mh-bar" style="background:{accent};"></span>'
        f'<h3 class="mh-title">{esc(title)}</h3>'
        f'</div>'
        f'<div class="mh-right">{right_html}</div>'
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
