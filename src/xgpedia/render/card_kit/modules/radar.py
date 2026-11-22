"""ماژول ۱ پیش‌ازبازی: رادار ۶ محوره تاکتیکی — بهینه‌شده برای تمام‌عرض و نیم‌عرض بدون هیچ بریدگی."""
from __future__ import annotations

import math
from typing import Any

from src.xgpedia.render.card_kit.helpers import f1, fa, module_header, team_legend_html

LABELS = ["خلق موقعیت", "شدت پرس", "ایستگاهی", "صلابت دفاعی", "مالکیت مؤثر", "تهدید پاس"]


def render_radar(payload: dict[str, Any], span: str = "full", fmt: str = "4:5") -> str:
    m = payload["match"]
    h, a = m["home"], m["away"]
    hc, ac = h["color"], a["color"]
    hv = h.get("radar")
    av = a.get("radar")
    if not (hv and av and len(hv) == 6 and len(av) == 6):
        return ""

    is_half = span == "half"
    # فاصلهٔ متوازن و نزدیک به شش‌ضلعی (به‌ویژه رأس بالا) همراه با فونت خواناتر و بزرگ‌تر
    if is_half:
        vb_w, vb_h, cx, cy, R = 560, 420, 280, 214, 112
        dx = R * 0.866 + 14
        lbl_fs, val_fs = 23, 21
        val_dy = 26
        top_y = cy - R - 40
        bot_y = cy + R + 26
    else:
        vb_w, vb_h, cx, cy, R = 900, 420, 450, 214, 122
        dx = R * 0.866 + 16
        lbl_fs, val_fs = 27, 25
        val_dy = 30
        top_y = cy - R - 44
        bot_y = cy + R + 28

    def pts(vals: list[float]) -> list[tuple[float, float]]:
        out = []
        for i, v in enumerate(vals):
            ang = math.radians(i * 60 - 90)
            rr = max(15.0, min(100.0, float(v))) / 100.0 * R
            out.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
        return out

    def ring(k: float) -> str:
        return " ".join(
            f"{f1(cx + R * k * math.cos(math.radians(i * 60 - 90)))},{f1(cy + R * k * math.sin(math.radians(i * 60 - 90)))}"
            for i in range(6)
        )

    h_pts, a_pts = pts(hv), pts(av)
    h_poly = " ".join(f"{f1(x)},{f1(y)}" for x, y in h_pts)
    a_poly = " ".join(f"{f1(x)},{f1(y)}" for x, y in a_pts)

    specs = [
        (cx, top_y, "middle"),
        (cx + dx, cy - R * 0.5 - 6, "start"),
        (cx + dx, cy + R * 0.5 - 4, "start"),
        (cx, bot_y, "middle"),
        (cx - dx, cy + R * 0.5 - 4, "end"),
        (cx - dx, cy - R * 0.5 - 6, "end"),
    ]
    labels_svg = "".join(
        f'<g>'
        f'<text x="{f1(x)}" y="{f1(y)}" text-anchor="{an}" fill="#F8FAFC" font-family="Vazirmatn" font-weight="800" font-size="{lbl_fs}">{lbl}</text>'
        f'<text x="{f1(x)}" y="{f1(y + val_dy)}" text-anchor="{an}" font-family="Vazirmatn" font-weight="900" font-size="{val_fs}">'
        f'<tspan fill="{hc}">{fa(int(round(hv[i])))}</tspan><tspan fill="#94A3B8"> / </tspan><tspan fill="{ac}">{fa(int(round(av[i])))}</tspan>'
        f'</text></g>'
        for i, (lbl, (x, y, an)) in enumerate(zip(LABELS, specs))
    )
    a_dots = "".join(f'<circle cx="{f1(x)}" cy="{f1(y)}" r="4.5" fill="{ac}" stroke="#fff" stroke-width="1.8"/>' for x, y in a_pts)
    h_dots = "".join(f'<circle cx="{f1(x)}" cy="{f1(y)}" r="5.5" fill="{hc}" stroke="#fff" stroke-width="2"/>' for x, y in h_pts)

    rings = "".join(f'<polygon points="{ring(k)}"/>' for k in (1.0, 0.75, 0.5, 0.25))
    axes = (
        f'<line x1="{cx}" y1="{f1(cy - R)}" x2="{cx}" y2="{f1(cy + R)}"/>'
        f'<line x1="{f1(cx + R * 0.866)}" y1="{f1(cy - R * 0.5)}" x2="{f1(cx - R * 0.866)}" y2="{f1(cy + R * 0.5)}"/>'
        f'<line x1="{f1(cx + R * 0.866)}" y1="{f1(cy + R * 0.5)}" x2="{f1(cx - R * 0.866)}" y2="{f1(cy - R * 0.5)}"/>'
    )

    title = "رادار تاکتیکی" if is_half else "رادار ۶ محوره تاکتیکی"
    right = team_legend_html(h["name"], a["name"], hc, ac, is_half=is_half)
    span_cls = "mod-half" if is_half else "mod-full"

    return (
        f'<div class="xm {span_cls}">'
        f'{module_header(title, right, "#E62E45", is_half=is_half)}'
        f'<div class="mod-body-svg" dir="ltr">'
        f'<svg class="fit-svg" viewBox="0 0 {vb_w} {vb_h}" preserveAspectRatio="xMidYMid meet" fill="none">'
        f'<g stroke="rgba(255,255,255,0.16)" stroke-width="1.6">{rings}{axes}</g>'
        f'<polygon points="{a_poly}" fill="{ac}" fill-opacity=".24" stroke="{ac}" stroke-width="3.6"/>'
        f'<polygon points="{h_poly}" fill="{hc}" fill-opacity=".30" stroke="{hc}" stroke-width="4"/>'
        f'{a_dots}{h_dots}{labels_svg}'
        f'</svg></div></div>'
    )
