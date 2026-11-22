"""ماژول ۷ پیش‌ازبازی: ماتریس احتمال دقیق نتیجه پواسون ۵×۵ (poisson) — نیم‌عرض و تمام‌عرض."""
from __future__ import annotations

from typing import Any

from src.xgpedia.render.card_kit.helpers import dixon_coles_5x5, esc, f1, f2, fa, module_header


def render_poisson(payload: dict[str, Any], span: str = "full", fmt: str = "4:5") -> str:
    if not payload.get("hasProbs"):
        return ""
    m = payload["match"]
    h_xg = float(m["home"].get("xg") or 0)
    a_xg = float(m["away"].get("xg") or 0)
    if h_xg <= 0 or a_xg <= 0:
        return ""

    hc, ac = m["home"]["color"], m["away"]["color"]
    h_code = esc(m["home"].get("code") or "HOM")
    a_code = esc(m["away"].get("code") or "AWY")
    is_half = span == "half"

    mat = dixon_coles_5x5(h_xg, a_xg)
    tops: list[tuple[str, float]] = []
    cells: list[str] = [f'<div class="pm-hdr pm-corner fm">{h_code}\\{a_code}</div>']
    for a in range(5):
        cells.append(f'<div class="pm-hdr" style="color:{ac}">{fa(a)}</div>')
    for h in range(5):
        cells.append(f'<div class="pm-hdr" style="color:{hc}">{fa(h)}</div>')
        for a in range(5):
            pct = mat[h][a] * 100.0
            op = f2(min(0.82, 0.12 + (pct / 13.0) * 0.68))
            rgb = "230,46,69" if h > a else ("100,116,139" if h == a else "56,189,248")
            tops.append((f"{fa(h)} - {fa(a)}", pct))
            cells.append(
                f'<div class="pm-cell" style="background:rgba({rgb},{op});">{fa(f1(pct))}٪</div>'
            )

    tops.sort(key=lambda x: -x[1])
    top_n = 2 if is_half else 3
    top_pills = "".join(
        f'<div class="pm-top{" pm-top-1" if i == 0 else ""}">'
        f'<span class="pm-top-sc">{sc}</span>'
        f'<span class="pm-top-pc">{fa(f1(p))}٪</span>'
        f'</div>'
        for i, (sc, p) in enumerate(tops[:top_n])
    )

    title = "ماتریس پواسون ۵×۵" if is_half else "ماتریس احتمال دقیق نتیجه (پواسون)"
    span_cls = "mod-half" if is_half else "mod-full"

    return (
        f'<div class="xm {span_cls}">'
        f'{module_header(title, "<span class=mod-tag>POISSON 5×5</span>", "#E62E45", is_half=is_half)}'
        f'<div class="pm-wrap">'
        f'<div class="pm-tops">{top_pills}</div>'
        f'<div class="pm-grid">{"".join(cells)}</div>'
        f'</div></div>'
    )
