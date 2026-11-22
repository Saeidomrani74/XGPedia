"""ماژول مقایسه شاخص‌های فنی (پیش‌ازبازی: stats / پس‌ازبازی: post_stats) — نیم‌عرض و تمام‌عرض."""
from __future__ import annotations

from typing import Any

from src.xgpedia.render.card_kit.helpers import esc, fa, module_header


def render_stats(payload: dict[str, Any], span: str = "full", fmt: str = "4:5") -> str:
    rows = payload.get("statsRows") or []
    if not rows:
        return ""
    m = payload["match"]
    hc, ac = m["home"]["color"], m["away"]["color"]
    is_half = span == "half"
    is_post = payload.get("cardType") == "post_match"

    # در نیم‌عرض یا فرمت 16:9، حداکثر ۳ ردیف تا ارتفاع هیچ‌وقت سرریز نکند
    cap = 3 if (is_half or fmt == "16:9") else 4
    vis_rows = rows[:cap]

    rows_html = []
    for r in vis_rows:
        rows_html.append(
            f'<div class="st-row">'
            f'<div class="st-vals">'
            f'<span class="st-num st-h" style="color:{hc}">{fa(esc(r["h"]))}</span>'
            f'<span class="st-lbl">{esc(r["label"])}</span>'
            f'<span class="st-num st-a" style="color:{ac}">{fa(esc(r["a"]))}</span>'
            f'</div>'
            f'<div class="st-bars">'
            f'<div class="ct hs"><div class="ch" style="width:{r["h_pct"]}%;background:{hc}"></div></div>'
            f'<div class="ct as"><div class="ca" style="width:{r["a_pct"]}%;background:{ac}"></div></div>'
            f'</div></div>'
        )

    title = (
        ("آمار مسابقه" if is_half else "آمار کلیدی مسابقه (۹۰ دقیقه)")
        if is_post
        else ("مقایسه فنی" if is_half else "مقایسه شاخص‌های کلیدی (در ۹۰ دقیقه)")
    )
    tag = "MATCH STATS" if is_post else "PER 90"
    span_cls = "mod-half" if is_half else "mod-full"

    return (
        f'<div class="xm {span_cls}">'
        f'{module_header(title, f"<span class=mod-tag>{tag}</span>", "#E62E45", is_half=is_half)}'
        f'<div class="st-list">{"".join(rows_html)}</div>'
        f'</div>'
    )
