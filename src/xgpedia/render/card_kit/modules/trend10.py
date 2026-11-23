"""ماژول‌های نمودار خطی: روند xG در ۱۰ بازی اخیر (trend10) و موج زمانی ۱۵ دقیقه‌ای (wave) — با محور عمودی و برچسب هفته."""
from __future__ import annotations

import math
import re
from typing import Any

from src.xgpedia.render.card_kit.helpers import f1, f2, fa, module_header, smooth_spline, team_legend_html


def _extract_current_week(match_dict: dict[str, Any]) -> int | None:
    wc = str(match_dict.get("weekCode") or "").strip()
    m = re.search(r"(\d+)", wc)
    if m:
        return int(m.group(1))
    rd = str(match_dict.get("round") or "")
    m2 = re.search(r"(\d+)", rd.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")))
    return int(m2.group(1)) if m2 else None


def render_trend10(payload: dict[str, Any], span: str = "full", fmt: str = "4:5") -> str:
    m = payload["match"]
    h, a = m["home"], m["away"]
    hc, ac = h["color"], a["color"]
    s_h = h.get("last10")
    s_a = a.get("last10")
    if not (s_h and s_a and len(s_h) >= 2 and len(s_a) >= 2):
        return ""

    is_half = span == "half"
    vb_w, vb_h = (540, 260) if is_half else (900, 275)
    px_l = 66 if is_half else 84
    px_r = 22 if is_half else 28
    py_top = 36
    py_bot = 48 if is_half else 52
    p_w = vb_w - px_l - px_r
    p_h = vb_h - py_top - py_bot

    # مقیاس گرد و خوانا برای محور عمودی xG (مثلاً 0.0 تا 3.0 یا 3.5)
    raw_max = max(*s_h, *s_a, 2.0)
    y_max = max(2.0, math.ceil(raw_max * 2.0) / 2.0)
    y_ticks = [0.0, round(y_max / 3.0, 1), round(y_max * 2.0 / 3.0, 1), y_max]
    if y_max in (2.0, 3.0, 4.0):
        step = y_max / (2.0 if y_max == 2.0 else (3.0 if y_max == 3.0 else 4.0))
        y_ticks = [round(step * k, 1) for k in range(int(y_max / step) + 1)]

    def to_pts(arr: list[float]) -> list[tuple[float, float]]:
        n = len(arr)
        return [(px_l + (i / max(n - 1, 1)) * p_w, py_top + p_h - (v / y_max) * p_h) for i, v in enumerate(arr)]

    h_pts, a_pts = to_pts(s_h), to_pts(s_a)
    h_path = smooth_spline(h_pts, 0.22)
    a_path = smooth_spline(a_pts, 0.22)

    # محور عمودی، خطوط راهنمای افقی و برچسب اعداد محور عمودی + واحد xG
    y_fs = 20 if is_half else 23
    grid_lines = []
    y_labels = []
    for tv in y_ticks:
        yy = py_top + p_h - (tv / y_max) * p_h
        if tv > 0:
            grid_lines.append(
                f'<line x1="{px_l}" y1="{f1(yy)}" x2="{vb_w - px_r}" y2="{f1(yy)}" '
                f'stroke="rgba(255,255,255,0.12)" stroke-width="1.4" stroke-dasharray="6 6"/>'
            )
        y_labels.append(
            f'<line x1="{px_l - 6}" y1="{f1(yy)}" x2="{px_l}" y2="{f1(yy)}" stroke="rgba(255,255,255,0.42)" stroke-width="1.6"/>'
            f'<text x="{px_l - 10}" y="{f1(yy + 6)}" text-anchor="end" fill="#CBD5E1" '
            f'font-family="JetBrains Mono, Vazirmatn" font-weight="700" font-size="{y_fs}">{fa(f"{tv:.1f}")}</text>'
        )

    axes_svg = (
        f'<line x1="{px_l}" y1="{py_top - 4}" x2="{px_l}" y2="{py_top + p_h}" stroke="rgba(255,255,255,0.40)" stroke-width="1.8"/>'
        f'<line x1="{px_l}" y1="{py_top + p_h}" x2="{vb_w - px_r}" y2="{py_top + p_h}" stroke="rgba(255,255,255,0.40)" stroke-width="1.8"/>'
        f'<text x="{px_l - 8}" y="{py_top - 12}" text-anchor="end" fill="#94A3B8" '
        f'font-family="JetBrains Mono, Vazirmatn" font-weight="800" font-size="{y_fs}">xG</text>'
    )

    # برچسب محور افقی: فقط عدد صحیح شماره هفتهٔ واقعی (مثلاً ۲، ۳، ...، ۱۱ پیش از هفتهٔ ۱۲)
    cur_wk = _extract_current_week(m)
    n_pts = len(h_pts)
    if cur_wk is not None and cur_wk > 1:
        start_wk = cur_wk - n_pts
        x_tick_labels = [
            fa(start_wk + i) if (start_wk + i) >= 1 else fa(38 + start_wk + i)
            for i in range(n_pts)
        ]
    else:
        x_tick_labels = [fa(i + 1) for i in range(n_pts)]

    lbl_fs = 21 if is_half else 24
    dots_and_x = "".join(
        f'<circle cx="{f1(x)}" cy="{f1(y)}" r="{5 if is_half else 5.5}" fill="{hc}" stroke="#fff" stroke-width="2"/>'
        f'<line x1="{f1(x)}" y1="{py_top + p_h}" x2="{f1(x)}" y2="{py_top + p_h + 6}" stroke="rgba(255,255,255,0.35)" stroke-width="1.4"/>'
        f'<text x="{f1(x)}" y="{py_top + p_h + (27 if is_half else 30)}" text-anchor="middle" fill="#E2E8F0" '
        f'font-family="Vazirmatn" font-weight="800" font-size="{lbl_fs}">{x_tick_labels[i]}</text>'
        for i, (x, y) in enumerate(h_pts)
    )
    x_week_tag = (
        f'<text x="{px_l - 10}" y="{py_top + p_h + (27 if is_half else 30)}" text-anchor="end" fill="#94A3B8" '
        f'font-family="Vazirmatn" font-weight="800" font-size="{18 if is_half else 21}">هفته</text>'
    )
    x_caption_svg = x_week_tag
    a_dots = "".join(
        f'<circle cx="{f1(x)}" cy="{f1(y)}" r="{4 if is_half else 4.5}" fill="{ac}" stroke="#fff" stroke-width="1.6"/>'
        for x, y in a_pts
    )
    avg_h = fa(f2(sum(s_h) / len(s_h)))
    avg_a = fa(f2(sum(s_a) / len(s_a)))
    right = (
        f'<div class="avg-pills">'
        f'<span class="avg-pill" style="color:{hc}">{avg_h}</span>'
        f'<span class="avg-sep">/</span>'
        f'<span class="avg-pill" style="color:{ac}">{avg_a}</span>'
        f'</div>'
    )
    title = "روند xG اخیر" if is_half else "روند xG در ۱۰ بازی اخیر"
    span_cls = "mod-half" if is_half else "mod-full"

    return (
        f'<div class="xm {span_cls}">'
        f'{module_header(title, right, "#E62E45", is_half=is_half)}'
        f'<div class="mod-body-svg" dir="ltr">'
        f'<svg class="fit-svg" viewBox="0 0 {vb_w} {vb_h}" preserveAspectRatio="xMidYMid meet" fill="none">'
        f'{"".join(grid_lines)}{axes_svg}{"".join(y_labels)}'
        f'<path d="{a_path}" stroke="{ac}" stroke-width="4" fill="none" stroke-linecap="round"/>'
        f'<path d="{h_path}" stroke="{hc}" stroke-width="4.8" fill="none" stroke-linecap="round"/>'
        f'{a_dots}{dots_and_x}{x_caption_svg}'
        f'</svg></div></div>'
    )


def render_wave(payload: dict[str, Any], span: str = "full", fmt: str = "4:5") -> str:
    m = payload["match"]
    h, a = m["home"], m["away"]
    hc, ac = h["color"], a["color"]
    s_h = h.get("wave")
    s_a = a.get("wave")
    if not (s_h and s_a and len(s_h) == 6 and len(s_a) == 6):
        return ""

    is_half = span == "half"
    vb_w, vb_h = (520, 240) if is_half else (900, 250)
    px_l = 66 if is_half else 84
    px_r = 24 if is_half else 30
    py_top = 34
    py_bot = 48 if is_half else 52
    p_w, p_h = vb_w - px_l - px_r, vb_h - py_top - py_bot

    # مقیاس رند و خوانا برای محور عمودی xG (مثل ۰.۰، ۰.۲، ۰.۴، ۰.۶ یا ۰.۰، ۰.۵، ۱.۰)
    raw_max = max(*s_h, *s_a, 0.35)
    step = 0.2 if raw_max <= 0.8 else (0.5 if raw_max <= 2.0 else 1.0)
    n_steps = max(2, int(math.ceil(raw_max / step)))
    y_max = round(n_steps * step, 2)
    y_ticks = [round(step * k, 1) for k in range(n_steps + 1)]

    def to_pts(arr: list[float]) -> list[tuple[float, float]]:
        return [(px_l + (i / 5.0) * p_w, py_top + p_h - (v / y_max) * p_h) for i, v in enumerate(arr)]

    h_pts, a_pts = to_pts(s_h), to_pts(s_a)
    h_path = smooth_spline(h_pts, 0.25)
    a_path = smooth_spline(a_pts, 0.25)
    area = f"{h_path} L {f1(h_pts[-1][0])} {f1(py_top + p_h)} L {f1(h_pts[0][0])} {f1(py_top + p_h)} Z"

    y_fs = 19 if is_half else 22
    grid_lines = []
    y_labels = []
    for tv in y_ticks:
        yy = py_top + p_h - (tv / y_max) * p_h
        if tv > 0:
            grid_lines.append(
                f'<line x1="{px_l}" y1="{f1(yy)}" x2="{vb_w - px_r}" y2="{f1(yy)}" '
                f'stroke="rgba(255,255,255,0.12)" stroke-width="1.4" stroke-dasharray="6 6"/>'
            )
        y_labels.append(
            f'<line x1="{px_l - 6}" y1="{f1(yy)}" x2="{px_l}" y2="{f1(yy)}" stroke="rgba(255,255,255,0.42)" stroke-width="1.6"/>'
            f'<text x="{px_l - 10}" y="{f1(yy + 6)}" text-anchor="end" fill="#CBD5E1" '
            f'font-family="JetBrains Mono, Vazirmatn" font-weight="700" font-size="{y_fs}">{fa(f"{tv:.1f}")}</text>'
        )

    axes_svg = (
        f'<line x1="{px_l}" y1="{py_top - 4}" x2="{px_l}" y2="{py_top + p_h}" stroke="rgba(255,255,255,0.40)" stroke-width="1.8"/>'
        f'<line x1="{px_l}" y1="{py_top + p_h}" x2="{vb_w - px_r}" y2="{py_top + p_h}" stroke="rgba(255,255,255,0.40)" stroke-width="1.8"/>'
        f'<text x="{px_l - 8}" y="{py_top - 12}" text-anchor="end" fill="#94A3B8" '
        f'font-family="JetBrains Mono, Vazirmatn" font-weight="800" font-size="{y_fs}">xG</text>'
    )

    mins = ["۱۵'", "۳۰'", "۴۵'", "۶۰'", "۷۵'", "۹۰'"]
    lbl_fs = 22 if is_half else 25
    a_dots = "".join(f'<circle cx="{f1(x)}" cy="{f1(y)}" r="5" fill="{ac}" stroke="#fff" stroke-width="1.8"/>' for x, y in a_pts)
    h_dots = "".join(
        f'<circle cx="{f1(x)}" cy="{f1(y)}" r="6" fill="{hc}" stroke="#fff" stroke-width="2.2"/>'
        f'<line x1="{f1(x)}" y1="{py_top + p_h}" x2="{f1(x)}" y2="{py_top + p_h + 6}" stroke="rgba(255,255,255,0.35)" stroke-width="1.4"/>'
        f'<text x="{f1(x)}" y="{vb_h - 12}" text-anchor="middle" fill="#E2E8F0" font-family="Vazirmatn" font-weight="800" font-size="{lbl_fs}">{mins[i]}</text>'
        for i, (x, y) in enumerate(h_pts)
    )
    title = "موج ۱۵ دقیقه‌ای xG" if is_half else "موج زمانی امید گل (۱۵ دقیقه‌ای)"
    right = team_legend_html(h["name"], a["name"], hc, ac, is_half=is_half)
    span_cls = "mod-half" if is_half else "mod-full"

    return (
        f'<div class="xm {span_cls}">'
        f'{module_header(title, right, "#E62E45", is_half=is_half)}'
        f'<div class="mod-body-svg" dir="ltr">'
        f'<svg class="fit-svg" viewBox="0 0 {vb_w} {vb_h}" preserveAspectRatio="xMidYMid meet" fill="none">'
        f'<defs><linearGradient id="wg_{span}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{hc}" stop-opacity=".35"/><stop offset="1" stop-color="{hc}" stop-opacity="0"/></linearGradient></defs>'
        f'{"".join(grid_lines)}{axes_svg}{"".join(y_labels)}'
        f'<path d="{area}" fill="url(#wg_{span})"/>'
        f'<path d="{a_path}" stroke="{ac}" stroke-width="4" fill="none" stroke-linecap="round"/>'
        f'<path d="{h_path}" stroke="{hc}" stroke-width="4.8" fill="none" stroke-linecap="round"/>'
        f'{a_dots}{h_dots}'
        f'</svg></div></div>'
    )
