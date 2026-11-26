"""ماژول ۲ پیش‌ازبازی: تقابل مهره‌های کلیدی (keyduel) — چیدمان افقی (تمام‌عرض) و فشرده عمودی (نیم‌عرض)."""
from __future__ import annotations

from typing import Any

from src.xgpedia.config import translate_player_fa
from src.xgpedia.render.card_kit.helpers import esc, fa, module_header


def render_keyduel(payload: dict[str, Any], span: str = "full", fmt: str = "4:5") -> str:
    m = payload["match"]
    h_kp = m["home"].get("kp")
    a_kp = m["away"].get("kp")
    if not (h_kp and a_kp):
        return ""
    hc, ac = m["home"]["color"], m["away"]["color"]
    is_half = span == "half"

    def card(kp: dict[str, str], col: str) -> str:
        return (
            f'<div class="kd-card" style="border-right:5px solid {col};">'
            f'<div class="kd-top">'
            f'<span class="kd-name">{esc(translate_player_fa(kp.get("name")) or kp["name"])}</span>'
            f'<span class="kd-pos">{esc(kp["pos"])}</span>'
            f'</div>'
            f'<div class="kd-stats">'
            f'<span class="kd-s1" style="color:{col}">{fa(esc(kp["s1"]))}</span>'
            f'<span class="kd-s2">{fa(esc(kp["s2"]))}</span>'
            f'</div></div>'
        )

    title = "مهره‌های کلیدی" if is_half else "تقابل مهره‌های کلیدی"
    span_cls = "mod-half" if is_half else "mod-full"
    body_cls = "kd-body kd-stack" if is_half else "kd-body kd-row"
    vs_html = "" if is_half else '<div class="kd-vs-wrap"><span class="kd-vs">VS</span></div>'

    return (
        f'<div class="xm {span_cls}">'
        f'{module_header(title, "<span class=mod-tag>KEY DUEL</span>", "#E62E45", is_half=is_half)}'
        f'<div class="{body_cls}">{card(h_kp, hc)}{vs_html}{card(a_kp, ac)}</div>'
        f'</div>'
    )
