"""ماژول ۳ پیش‌ازبازی: سیگنال‌های ارزش بازار (+EV) صرفاً از ضرایب واقعی بازار."""
from __future__ import annotations

from typing import Any

from src.xgpedia.render.card_kit.helpers import esc, f1, f2, fa, module_header


def render_signals(payload: dict[str, Any], span: str = "full", fmt: str = "4:5") -> str:
    items = payload.get("signalsItems") or []
    if not items:
        return ""

    def bar(lbl: str, cls_lbl: str, k: str, pct: float) -> str:
        n = min(100.0, max(0.0, float(pct)))
        txt = f"{fa(f1(pct))}٪"
        in_bar = n >= 68.0
        inside = f'<span class="evv ei{k}">{txt}</span>' if in_bar else ""
        outside = "" if in_bar else f'<span class="evv eo{k}">{txt}</span>'
        return (
            f'<div class="ebr">'
            f'<span class="ebl {cls_lbl}">{lbl}</span>'
            f'<div class="ebt"><div class="ef{k}" style="width:{f1(n)}%">{inside}</div>{outside}</div>'
            f'</div>'
        )

    rows = []
    for it in items[:3]:
        ev_val = float(it["ev_pct"])
        ev_sign = "+" if ev_val >= 0 else "-"
        tc = str(it.get("tier_class") or ("eneg" if ev_val < 0 else "ed"))
        tl = str(it.get("tier_label") or ("ارزش منفی" if ev_val < 0 else "ارزشمند"))
        if ev_val < 0:
            tc = "eneg"
            tl = "ارزش منفی"
        is_gold = tc == "egold" or ev_val >= 8.0
        if is_gold:
            tc = "egold"
        row_cls = "er er-gold" if is_gold else ("er er-neg" if ev_val < 0 else "er")
        gold_crown = '<span class="gold-star">✦</span> ' if is_gold else ""
        rows.append(
            f'<div class="{row_cls}">'
            f'<div class="er-info">'
            f'<div class="et">{gold_crown}{esc(it["title"])}</div>'
            f'<div class="em">ضریب {fa(f2(it["odds"]))} · معادل {fa(f1(it["market_pct"]))}٪</div>'
            f'</div>'
            f'<div class="ebc">'
            f'{bar("احتمال مدل", "ebl-m", "m", it["model_pct"])}'
            f'{bar("احتمال بازار", "ebl-k", "k", it["market_pct"])}'
            f'</div>'
            f'<div class="epw {esc(tc)}">'
            f'<div dir="ltr" class="epb"><span>{ev_sign}{fa(f1(abs(ev_val)))}٪</span><span class="ept">EV</span></div>'
            f'<span class="eps">{esc(tl)}</span>'
            f'</div></div>'
        )

    return (
        f'<div class="xm mod-full">'
        f'{module_header("سیگنال‌های ارزش", "<span class=mod-tag dir=ltr>MODEL vs MARKET</span>", "#FBBF24", is_half=False)}'
        f'<div class="el">{"".join(rows)}</div>'
        f'</div>'
    )
