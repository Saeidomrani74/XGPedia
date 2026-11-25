"""کارت ماژولار «تقابل مستقیم تیم‌ها» (XGPedia H2H Studio — Master Edition — D55) — بازسازی ۱:۱ آفلاین.

بازسازی دقیق و ۱:۱ از `studio_templates/h2h_teams.html` با:
  - فریم چهارگوشه قرمز یکپارچه (`pad_top=24/22/139`, `pad_bot=20/16/171`, `header 12px 36px 8px`, `stage 8px 40px`, `footer 10px 44px 10px`)
  - پس‌زمینه کامل زمین تاکتیکی SVG (`tg`, `#pr`, `#hl`, `#cc1..cc5`, محوطه‌های جریمه، `#crh`, `#hud-tel`, scanlines, `#beams`)
  - ۳ اتمسفر نوری (`cinematic`, `editorial`, `tactical`)
  - سپرهای سه‌بعدی SVG باشگاه‌ها (با ریتیکل مداری نقطه‌چین و پشتیبانی از لوگوی اختصاصی `logoUrl`)
  - کرونوگراف ۲۴۰ درجهٔ SVG تراز تاریخچه (۴۸ تیک، قوس‌های درخشان، الماس `H2H`) + نوار کپسولی براق ۳تکه (`pillBar`) + نوار آمار کلان (`hero-strip`)
  - تمام ۷ ماژول تخصصی با پشتیبانی کامل نیم‌عرض (`½`) و تمام‌عرض (`۱`)، ۵ اسلاید آماده (شامل Showreel فشرده `.dv`) و قانون `null ≠ 0`.
"""
from __future__ import annotations

import math
from typing import Any

from src.xgpedia.render.card_kit.helpers import contrast_ink, esc, f1, f2, fa, luminance, smooth_spline
from src.xgpedia.render.cards import _brand_logo_data_uri
from src.xgpedia.render.studio_engine import build_embedded_font_css

H2H_TEAMS_FORMATS: dict[str, tuple[int, int]] = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}

# (id, label_fa, header_mode, default_mods)
H2H_TEAMS_SLIDES: list[tuple[str, str, str, list[str]]] = [
    ("slide1", "اسلاید ۱: نمای کلی و تاریخچه (پیشنهادی)", "full", ["chronicle", "balance"]),
    ("slide2", "اسلاید ۲: موج برتری و دژ خانگی", "compact", ["momentum", "fortress"]),
    ("slide3", "اسلاید ۳: اسطوره‌ها و دقیقه انفجار", "compact", ["kings", "timing"]),
    ("slide4", "اسلاید ۴: DNA تقابل و تاریخچه", "compact", ["dna", "chronicle"]),
    ("slide5", "اسلاید ۵: پوستر جامع کامل (Showreel)", "full", ["chronicle", "balance", "fortress", "kings", "dna"]),
]


def _crest_svg(team: dict[str, Any], side: str, size: int = 150, reticle: bool = True) -> str:
    from src.xgpedia.providers.pl_badges_free import get_pl_badge_data_uri
    p = esc(team.get("color") or "#EF0107")
    logo_uri = team.get("logoUrl") or get_pl_badge_data_uri(
        str(team.get("name") or ""), tla_hint=str(team.get("code") or ""), fetch_network=False
    )
    if logo_uri:
        ret_svg = (
            f'<svg style="position:absolute;inset:0;width:100%;height:100%;pointer-events:none" viewBox="0 0 180 180" fill="none">'
            f'<circle cx="90" cy="90" r="85" stroke="{p}" stroke-opacity=".45" stroke-width="1.8" stroke-dasharray="10 6 3 6"/>'
            f'<circle cx="90" cy="90" r="76" stroke="#F8FAFC" stroke-opacity=".18"/></svg>'
            if reticle else ""
        )
        img_sz = round(size * 0.76)
        return (
            f'<div style="position:relative;width:{size}px;height:{size}px;display:flex;align-items:center;justify-content:center;flex-shrink:0">'
            f'{ret_svg}<img src="{esc(logo_uri)}" style="width:{img_sz}px;height:{img_sz}px;object-fit:contain;display:block;filter:drop-shadow(0 12px 24px {p}55) drop-shadow(0 6px 12px #0009)" alt="{esc(team.get("code",""))}"/></div>'
        )
    s = esc(team.get("secondary") or "#FFFFFF")
    cd = esc(str(team.get("code") or "FC")[:3].upper())
    u = f"{side}_{size}"
    d = "M90 16L150 40V88C150 128 124.5 156.5 90 166C55.5 156.5 30 128 30 88V40Z"
    ret_svg = (
        f'<circle cx="90" cy="92" r="85" stroke="{p}" stroke-opacity=".35" stroke-width="1.5" stroke-dasharray="10 6 3 6"/>'
        f'<circle cx="90" cy="92" r="76" stroke="#F8FAFC" stroke-opacity=".14"/>'
        f'<path d="M90 3V11M90 173V181M3 92H11M169 92H177" stroke="{p}" stroke-opacity=".65" stroke-width="2" stroke-linecap="round"/>'
        if reticle
        else ""
    )
    badge_bg = "#0D1730" if luminance(team.get("color") or "#EF0107") > 0.62 else "#060c1bc4"
    dot_fill = contrast_ink(team.get("color") or "#EF0107")
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 180 180" fill="none" '
        f'style="filter:drop-shadow(0 14px 28px {p}52) drop-shadow(0 8px 16px #000000a6);flex-shrink:0">'
        f'<defs><linearGradient id="g{u}" x1="20" y1="15" x2="160" y2="165" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{s}" stop-opacity=".98"/>'
        f'<stop offset=".48" stop-color="{p}" stop-opacity=".95"/>'
        f'<stop offset="1" stop-color="{s}" stop-opacity=".75"/></linearGradient>'
        f'<clipPath id="c{u}"><path d="{d}"/></clipPath></defs>'
        f"{ret_svg}"
        f'<path d="M90 10L156 37V88C156 132 128 162 90 172C52 162 24 132 24 88V37Z" fill="{p}" fill-opacity=".24"/>'
        f'<g clip-path="url(#c{u})">'
        f'<rect x="25" y="12" width="130" height="158" fill="{p}"/>'
        f'<path d="M25 114L155 54V84L25 144Z" fill="{s}" fill-opacity=".28"/>'
        f'<path d="M90 16L150 40V58L90 34L30 58V40Z" fill="{s}" fill-opacity=".92"/>'
        f'<ellipse cx="90" cy="26" rx="68" ry="28" fill="#fff" fill-opacity=".22"/></g>'
        f'<path d="{d}" stroke="url(#g{u})" stroke-width="5"/>'
        f'<rect x="42" y="68" width="96" height="48" rx="14" fill="{badge_bg}" stroke="{s}" stroke-opacity=".6" stroke-width="2"/>'
        f'<text x="90" y="102" text-anchor="middle" fill="#fff" font-family="Space Grotesk,JetBrains Mono,sans-serif" '
        f'font-weight="800" font-size="31" letter-spacing="2">{cd}</text>'
        f'<circle cx="90" cy="136" r="5" fill="{dot_fill}" fill-opacity=".92"/></svg>'
    )


def _chrono_svg(hw: int, dr: int, aw: int, hc: str, ac: str) -> str:
    tot = max(1, hw + dr + aw)
    cx, cy, r_arc, r_tick = 160.0, 148.0, 108.0, 126.0
    s0, e0, span, gap = -30.0, 210.0, 240.0, 5.5
    usable = span - gap * 2
    a_h = (hw / tot) * usable
    a_d = (dr / tot) * usable

    def _arc(s: float, e: float, r: float) -> str:
        if e - s <= 0.6:
            return ""
        rs, re_ = math.radians(s), math.radians(e)
        x0, y0 = cx + r * math.cos(rs), cy - r * math.sin(rs)
        x1, y1 = cx + r * math.cos(re_), cy - r * math.sin(re_)
        lg = 1 if (e - s) > 180 else 0
        return f"M {x0:.1f} {y0:.1f} A {r:.1f} {r:.1f} 0 {lg} 0 {x1:.1f} {y1:.1f}"

    s1, e1 = s0, s0 + a_h
    s2, e2 = e1 + gap, e1 + gap + a_d
    s3 = e2 + gap

    ticks = []
    for i in range(49):
        rad = math.radians(s0 + (i / 48.0) * span)
        mj = (i % 6 == 0)
        r1 = r_tick + (0 if mj else 3.5)
        r2 = r_tick + (12 if mj else 8)
        ticks.append(
            f'<line x1="{cx + r1 * math.cos(rad):.1f}" y1="{cy - r1 * math.sin(rad):.1f}" '
            f'x2="{cx + r2 * math.cos(rad):.1f}" y2="{cy - r2 * math.sin(rad):.1f}" '
            f'stroke="#F8FAFC" stroke-opacity="{".52" if mj else ".18"}" stroke-width="{"2.2" if mj else "1.2"}" stroke-linecap="round"/>'
        )

    p_bg = _arc(s0, e0, r_arc)
    p_h = _arc(s1, e1, r_arc)
    p_d = _arc(s2, e2, r_arc)
    p_a = _arc(s3, e0, r_arc)

    return (
        '<svg viewBox="0 0 320 248" class="hero-gauge-svg" fill="none">'
        '<defs><filter id="cgGlow" x="-25%" y="-25%" width="150%" height="150%">'
        '<feGaussianBlur stdDeviation="4.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>'
        f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="88" fill="#060D1E" fill-opacity=".75" stroke="#ffffff14" stroke-width="1.5"/>'
        f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="78" stroke="#E62E45" stroke-opacity=".22" stroke-dasharray="3 5"/>'
        f'{"".join(ticks)}'
        f'<path d="{p_bg}" stroke="#ffffff14" stroke-width="18" stroke-linecap="round"/>'
        + (f'<path d="{p_h}" stroke="{hc}" stroke-width="18" stroke-linecap="round" filter="url(#cgGlow)"/>' if p_h else "")
        + (f'<path d="{p_d}" stroke="#94A3B8" stroke-width="15" stroke-linecap="round"/>' if p_d else "")
        + (f'<path d="{p_a}" stroke="{ac}" stroke-width="18" stroke-linecap="round" filter="url(#cgGlow)"/>' if p_a else "")
        + f'<text x="{cx:.0f}" y="{cy + 6:.0f}" text-anchor="middle" fill="#fff" font-family="Vazirmatn" font-weight="900" font-size="54">{fa(tot)}</text>'
        + f'<text x="{cx:.0f}" y="{cy + 34:.0f}" text-anchor="middle" fill="#CBD5E1" font-family="Vazirmatn" font-weight="800" font-size="17">مجموع تقابل‌ها</text>'
        + f'<g transform="translate({cx:.0f},216)">'
        + '<line x1="-68" y1="0" x2="-34" y2="0" stroke="#E62E45" stroke-opacity=".55" stroke-width="1.8"/>'
        + '<line x1="34" y1="0" x2="68" y2="0" stroke="#E62E45" stroke-opacity=".55" stroke-width="1.8"/>'
        + '<rect x="-26" y="-26" width="52" height="52" rx="12" transform="rotate(45)" fill="#E62E45" stroke="#ffffff55" stroke-width="2" filter="url(#cgGlow)"/>'
        + '<text x="0" y="7" text-anchor="middle" fill="#fff" font-family="Space Grotesk" font-weight="800" font-size="21" letter-spacing="1">H2H</text>'
        + "</g></svg>"
    )


def _pill_bar(ph: float, pd: float, pa: float, hc: str, ac: str, compact: bool = False) -> str:
    mn = 12 if compact else 10
    cls = "pc pcc" if compact else "pc"
    h_txt = f"{fa(round(ph))}٪" if ph >= mn else ""
    d_txt = f"{fa(round(pd))}٪" if pd >= mn else ""
    a_txt = f"{fa(round(pa))}٪" if pa >= mn else ""
    return (
        f'<div class="{cls}">'
        f'<div class="ps" style="width:{f1(ph)}%;background:{hc};color:{contrast_ink(hc)}">{h_txt}</div>'
        '<div class="ps-sep"></div>'
        f'<div class="ps" style="width:{f1(pd)}%;background:#475569;color:#F8FAFC">{d_txt}</div>'
        '<div class="ps-sep"></div>'
        f'<div class="ps" style="width:{f1(pa)}%;background:{ac};color:{contrast_ink(ac)}">{a_txt}</div>'
        "</div>"
    )


def _mod_header(title: str, right_html: str, bar_color: str = "#E62E45") -> str:
    return (
        '<div class="mh">'
        f'<div class="mh-left"><span class="mh-bar" style="background:{bar_color};box-shadow:0 0 12px {bar_color}"></span>'
        f'<h3 class="mt">{esc(title)}</h3></div>'
        f'<div class="mh-sub">{right_html}</div>'
        "</div>"
    )


def get_h2h_teams_modules(data: dict[str, Any], slide: str = "slide1") -> tuple[list[dict[str, Any]], list[str]]:
    home = data.get("home") or {}
    away = data.get("away") or {}
    has_chronicle = bool(data.get("recent5") or data.get("recent"))
    has_balance = home.get("goals") is not None and away.get("goals") is not None
    has_momentum = len(data.get("momentum8") or []) >= 2
    has_fortress = isinstance(home.get("venueStats"), dict) and isinstance(away.get("venueStats"), dict)
    has_kings = isinstance(home.get("king"), dict) and isinstance(away.get("king"), dict)
    has_dna = isinstance(data.get("dna"), dict) and bool(data.get("dna"))
    has_timing = isinstance(data.get("timing"), dict) and bool((data.get("timing") or {}).get("home"))

    sl_def = next((mids for sid, _, _, mids in H2H_TEAMS_SLIDES if sid == slide), ["chronicle", "balance"])
    def_set = set(sl_def)
    is_showreel = slide == "slide5"

    specs = [
        ("chronicle", "نوار سینمایی ۵ تقابل اخیر (Chronicle)", has_chronicle, False, "full"),
        ("balance", "ترازوی نبرد و بزرگ‌ترین بردها (Balance)", has_balance, True, "half" if is_showreel else "full"),
        ("momentum", "موج نوسان برتری (Momentum Wave)", has_momentum, False, "full"),
        ("fortress", "دژ خانگی و تفکیک میزبانی (Fortress)", has_fortress, True, "half" if is_showreel else "full"),
        ("kings", "پادشاهان و آقای‌گل‌های تقابل (Kings)", has_kings, True, "half" if is_showreel else "full"),
        ("dna", "امضای آماری و DNA تقابل (Fixture DNA)", has_dna, True, "half" if is_showreel else "full"),
        ("timing", "نقشه دقیقه انفجار گل‌ها (Goal Timing)", has_timing, True, "full"),
    ]
    mods: list[dict[str, Any]] = []
    missing: list[str] = []
    for mid, title_fa, has_d, can_half, def_span in specs:
        if has_d:
            mods.append({
                "id": mid,
                "title_fa": title_fa,
                "enabled": mid in def_set,
                "can_half": can_half,
                "span": def_span,
                "half": def_span == "half",
            })
        else:
            missing.append(title_fa)
    if mods and not any(m["enabled"] for m in mods):
        mods[0]["enabled"] = True
    return mods, missing


def _render_hero(data: dict[str, Any], header_mode: str, fmt: str, is_dense: bool) -> str:
    h, a = data["home"], data["away"]
    hc, ac = esc(h.get("color") or "#EF0107"), esc(a.get("color") or "#38BDF8")
    hw, dr, aw = int(h.get("wins") or 0), int(data.get("draws") or 0), int(a.get("wins") or 0)
    tot = max(1, hw + dr + aw)
    ph, pd, pa = hw / tot * 100.0, dr / tot * 100.0, aw / tot * 100.0
    hg_tot, ag_tot = int(h.get("goals") or 0), int(a.get("goals") or 0)
    avg_g = (hg_tot + ag_tot) / tot

    if header_mode == "compact":
        return (
            '<div class="hero-compact">'
            '<div class="hc-grid">'
            f'<div class="hc-side">{_crest_svg(h, "h", 74, False)}'
            f'<div class="min-w-0"><div class="hc-name">{esc(h["name"])}</div>'
            f'<div class="hc-sub" style="color:{hc}">{fa(hw)} برد • {fa(hg_tot)} گل زده</div></div></div>'
            f'<div class="hc-mid"><div class="hc-tag">H2H • {fa(tot)}</div>'
            f'<div class="hc-wdw"><span style="color:{hc}">{fa(hw)}</span>'
            f'<span class="hc-dr">{fa(dr)}</span><span style="color:{ac}">{fa(aw)}</span></div></div>'
            f'<div class="hc-side away"><div class="min-w-0"><div class="hc-name">{esc(a["name"])}</div>'
            f'<div class="hc-sub" style="color:{ac}">{fa(aw)} برد • {fa(ag_tot)} گل زده</div></div>'
            f'{_crest_svg(a, "a", 74, False)}</div>'
            f'</div>{_pill_bar(ph, pd, pa, hc, ac, True)}</div>'
        )

    c_sz = 112 if is_dense else (128 if fmt == "16:9" else 146)

    def _side_col(tm: dict[str, Any], sd: str, col: str, wins: int) -> str:
        st_col = "#FEF08A" if luminance(col) > 0.62 else "#F8FAFC"
        return (
            '<div class="hero-col">'
            f'<div class="fc" style="margin-bottom:6px">{_crest_svg(tm, sd, c_sz, True)}</div>'
            f'<h2 class="hero-name">{esc(tm["name"])}</h2>'
            f'<p class="hero-sub">{esc(tm.get("sub") or "")}</p>'
            f'<div class="hero-win-box" style="border-color:{col}66;box-shadow:0 8px 24px -8px {col}55,inset 0 1px 0 #ffffff1a">'
            f'<span class="hero-win-num" style="color:{col}">{fa(wins)}</span>'
            '<span class="hero-win-lbl">پیروزی</span></div>'
            f'<div class="hero-streak" style="background:{col}1c;border-color:{col}52;color:{st_col}">{esc(tm.get("streak") or "رقیب سنتی")}</div>'
            "</div>"
        )

    return (
        '<div class="hero-full">'
        '<div class="hf-grid">'
        f'{_side_col(h, "h", hc, hw)}'
        f'<div class="hero-mid">{_chrono_svg(hw, dr, aw, hc, ac)}</div>'
        f'{_side_col(a, "a", ac, aw)}'
        "</div>"
        '<div class="hf-bars">'
        f'{_pill_bar(ph, pd, pa, hc, ac, False)}'
        '<div class="hero-strip">'
        f'<div class="hs-side"><span class="hero-strip-val" style="color:{hc}">{fa(hg_tot)}</span>'
        '<span class="hero-strip-lbl">گل زده</span><span class="hs-dot">•</span>'
        f'<span class="hero-strip-val w">{fa(h.get("cleanSheets", 0))}</span><span class="hero-strip-lbl dim">کلین‌شیت</span></div>'
        f'<div class="hs-mid"><span>میانگین گل: <b>{fa(f2(avg_g))}</b></span></div>'
        f'<div class="hs-side away"><span class="hero-strip-lbl dim">کلین‌شیت</span>'
        f'<span class="hero-strip-val w">{fa(a.get("cleanSheets", 0))}</span><span class="hs-dot">•</span>'
        f'<span class="hero-strip-lbl">گل زده</span><span class="hero-strip-val" style="color:{ac}">{fa(ag_tot)}</span></div>'
        "</div></div></div>"
    )


def _render_chronicle(data: dict[str, Any]) -> str:
    h, a = data["home"], data["away"]
    hc, ac = esc(h.get("color") or "#EF0107"), esc(a.get("color") or "#38BDF8")
    rec = (data.get("recent5") or data.get("recent") or [])[:5]
    cards = []
    for i, g in enumerate(rec):
        hg = int(g.get("hg") if g.get("hg") is not None else 0)
        ag = int(g.get("ag") if g.get("ag") is not None else 0)
        wc = hc if hg > ag else (ac if ag > hg else "#94A3B8")
        lt = (i == 0)
        bdr = "border:2px solid #E62E45;box-shadow:0 0 24px -6px rgba(230,46,69,.55)" if lt else f"border:1.5px solid #ffffff1c;border-top:3.5px solid {wc}"
        top_lbl = '<span class="tl-latest">آخرین تقابل</span>' if lt else f'<span class="tl-meta">{esc(g.get("date") or "—")}</span>'
        hxg, axg = g.get("hxg"), g.get("axg")
        if hxg is not None and axg is not None:
            tx = max(0.1, float(hxg) + float(axg))
            hp = float(hxg) / tx * 100.0
            xg_html = (
                f'<div class="tl-xgbar" dir="ltr"><div style="width:{f1(hp)}%;background:{hc}"></div>'
                f'<div style="width:{f1(100 - hp)}%;background:{ac}"></div></div>'
                f'<div class="tl-xg fm" dir="ltr">xG {fa(f1(hxg))} - {fa(f1(axg))}</div>'
            )
        else:
            xg_html = ""
        cards.append(
            f'<div class="tl-card" style="{bdr}">'
            f"{top_lbl}"
            f'<div class="tl-comp">{esc(g.get("comp") or "")}</div>'
            f'<div class="tl-score" dir="ltr" style="background:{wc}26;border-color:{wc}88">{fa(hg)} - {fa(ag)}</div>'
            f'<div class="tl-bot">{xg_html}'
            f'<div class="tl-venue"><span class="tl-dot" style="background:{wc}"></span><span>{esc(g.get("venue") or "")}</span></div>'
            "</div></div>"
        )
    return (
        '<div class="xm">'
        + _mod_header("نوار سینمایی ۵ تقابل اخیر", "<span class=fm>RECENT 5 CHRONICLE</span>", "#E62E45")
        + '<div class="tl-wrap">'
        f'<div class="tl-line" style="background:linear-gradient(90deg,{ac},#E62E45,{hc})"></div>'
        f'<div class="tl-grid">{"".join(cards)}</div></div></div>'
    )


def _render_balance(data: dict[str, Any]) -> str:
    h, a = data["home"], data["away"]
    hc, ac = esc(h.get("color") or "#EF0107"), esc(a.get("color") or "#38BDF8")
    rows_spec = [("مجموع گل‌های زده", h.get("goals"), a.get("goals"), 0, "")]
    if h.get("xgPerMatch") is not None and a.get("xgPerMatch") is not None:
        rows_spec.append(("میانگین xG در تقابل", h.get("xgPerMatch"), a.get("xgPerMatch"), 2, ""))
    if h.get("cleanSheets") is not None and a.get("cleanSheets") is not None:
        rows_spec.append(("کلین‌شیت (بسته نگه داشتن دروازه)", h.get("cleanSheets"), a.get("cleanSheets"), 0, ""))
    if h.get("last10WinPct") is not None and a.get("last10WinPct") is not None:
        rows_spec.append(("درصد برد در ۱۰ بازی اخیر", h.get("last10WinPct"), a.get("last10WinPct"), 0, "٪"))

    rows_html = []
    for lbl, hv, av, dec, unit in rows_spec:
        hf, af = float(hv or 0), float(av or 0)
        mx = max(hf, af, 0.01)
        hs = f"{fa(f2(hf) if dec == 2 else round(hf))}{unit}"
        as_ = f"{fa(f2(af) if dec == 2 else round(af))}{unit}"
        rows_html.append(
            '<div class="bal-item">'
            f'<div class="bal-top"><span class="bal-val r" style="color:{hc}">{hs}</span>'
            f'<span class="bal-lbl">{lbl}</span>'
            f'<span class="bal-val l" style="color:{ac}">{as_}</span></div>'
            '<div class="bal-bars">'
            f'<div class="ct hs"><div class="ch" style="width:{f1(hf / mx * 100)}%;background:{hc}"></div></div>'
            f'<div class="ct as"><div class="ca" style="width:{f1(af / mx * 100)}%;background:{ac}"></div></div>'
            "</div></div>"
        )
    bw_h, bw_a = h.get("biggestWin") or "—", a.get("biggestWin") or "—"
    return (
        '<div class="xm">'
        + _mod_header("ترازوی نبرد و تفاضل قدرت", "<span class=fm>POWER BALANCE</span>", "#E62E45")
        + f'<div class="bal-list">{"".join(rows_html)}</div>'
        '<div class="bal-foot">'
        f'<div class="bal-big" style="background:{hc}18;border-color:{hc}4a;border-right:4.5px solid {hc}">'
        f'<span class="bb-k">بزرگ‌ترین برد {esc(h["name"])}</span><span class="bb-v">{fa(esc(bw_h))}</span></div>'
        f'<div class="bal-big" style="background:{ac}18;border-color:{ac}4a;border-left:4.5px solid {ac}">'
        f'<span class="bb-v">{fa(esc(bw_a))}</span><span class="bb-k">بزرگ‌ترین برد {esc(a["name"])}</span></div>'
        "</div></div>"
    )


def _render_momentum(data: dict[str, Any]) -> str:
    h, a = data["home"], data["away"]
    hc, ac = esc(h.get("color") or "#EF0107"), esc(a.get("color") or "#38BDF8")
    arr = (data.get("momentum8") or [])[:8]
    diffs = [int(g.get("hg") or 0) - int(g.get("ag") or 0) for g in arr]
    mx = max([3] + [abs(d) for d in diffs])
    w_svg, h_svg, px, py = 900.0, 225.0, 54.0, 38.0
    my = h_svg / 2.0
    pw, hh = w_svg - px * 2, my - py
    pts = [
        (px + (i / max(1, len(arr) - 1) * pw if len(arr) > 1 else pw / 2.0), my - (d / mx) * hh)
        for i, d in enumerate(diffs)
    ]
    cv = smooth_spline(pts, 0.22)
    ap = f"{cv} L {pts[-1][0]:.1f} {my:.1f} L {pts[0][0]:.1f} {my:.1f} Z"
    nodes = []
    for (x, y), d, g in zip(pts, diffs, arr):
        col = hc if d > 0 else (ac if d < 0 else "#FBBF24")
        ly = y - 24 if d >= 0 else y + 26
        nodes.append(
            f'<g><line x1="{x:.1f}" y1="{my:.1f}" x2="{x:.1f}" y2="{y:.1f}" stroke="{col}" stroke-opacity=".35" stroke-width="1.5"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{col}" stroke="#fff" stroke-width="2.4"/>'
            f'<rect x="{x - 24:.1f}" y="{ly - 15:.1f}" width="48" height="22" rx="7" fill="#070E20" stroke="{col}" stroke-opacity=".7" stroke-width="1.4"/>'
            f'<text x="{x:.1f}" y="{ly + 1:.1f}" text-anchor="middle" fill="#fff" font-family="Vazirmatn" font-weight="900" font-size="15">{fa(g.get("hg", 0))}-{fa(g.get("ag", 0))}</text>'
            f'<text x="{x:.1f}" y="{h_svg + 24:.1f}" text-anchor="middle" fill="#CBD5E1" font-family="Vazirmatn" font-weight="700" font-size="17">{esc(g.get("label") or "")}</text></g>'
        )
    leg = (
        f'<div class="mom-leg"><span><i style="background:{hc}"></i>برتری {esc(h["name"])}</span>'
        f'<span><i style="background:{ac}"></i>برتری {esc(a["name"])}</span></div>'
    )
    return (
        '<div class="xm">'
        + _mod_header("موج نوسان برتری در ۸ تقابل اخیر", leg, "#E62E45")
        + f'<div class="fc" dir="ltr"><svg class="mom-svg" viewBox="0 0 {int(w_svg)} {int(h_svg + 38)}" fill="none">'
        f'<defs><linearGradient id="mUp" x1="0" y1="{py:.0f}" x2="0" y2="{my:.0f}" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{hc}" stop-opacity=".68"/><stop offset="1" stop-color="{hc}" stop-opacity=".06"/></linearGradient>'
        f'<linearGradient id="mDn" x1="0" y1="{my:.0f}" x2="0" y2="{h_svg - py:.0f}" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{ac}" stop-opacity=".06"/><stop offset="1" stop-color="{ac}" stop-opacity=".68"/></linearGradient>'
        f'<clipPath id="cpUp"><rect x="0" y="0" width="{int(w_svg)}" height="{my:.1f}"/></clipPath>'
        f'<clipPath id="cpDn"><rect x="0" y="{my:.1f}" width="{int(w_svg)}" height="{h_svg - my:.1f}"/></clipPath></defs>'
        f'<line x1="{px:.0f}" y1="{py:.0f}" x2="{w_svg - px:.0f}" y2="{py:.0f}" stroke="#ffffff14" stroke-dasharray="5 5"/>'
        f'<line x1="{px:.0f}" y1="{h_svg - py:.0f}" x2="{w_svg - px:.0f}" y2="{h_svg - py:.0f}" stroke="#ffffff14" stroke-dasharray="5 5"/>'
        f'<line x1="{px - 16:.0f}" y1="{my:.1f}" x2="{w_svg - px + 16:.0f}" y2="{my:.1f}" stroke="#E2E8F0" stroke-opacity=".55" stroke-width="2" stroke-dasharray="6 4"/>'
        f'<text x="{px - 24:.0f}" y="{my + 5:.1f}" text-anchor="end" fill="#94A3B8" font-family="Space Grotesk" font-weight="800" font-size="16">0</text>'
        f'<path d="{ap}" fill="url(#mUp)" clip-path="url(#cpUp)"/>'
        f'<path d="{ap}" fill="url(#mDn)" clip-path="url(#cpDn)"/>'
        f'<path d="{cv}" stroke="{hc}" stroke-width="4.5" fill="none" stroke-linecap="round" clip-path="url(#cpUp)"/>'
        f'<path d="{cv}" stroke="{ac}" stroke-width="4.5" fill="none" stroke-linecap="round" clip-path="url(#cpDn)"/>'
        f'{"".join(nodes)}</svg></div></div>'
    )


def _render_fortress(data: dict[str, Any]) -> str:
    h, a = data["home"], data["away"]
    hc, ac = esc(h.get("color") or "#EF0107"), esc(a.get("color") or "#38BDF8")
    circ = 2 * math.pi * 24

    def _vc(tm: dict[str, Any], op: dict[str, Any], col: str, ocol: str) -> str:
        v = tm.get("venueStats") or {}
        w, d, l = int(v.get("w") or 0), int(v.get("d") or 0), int(v.get("l") or 0)
        tot = max(1, w + d + l)
        pw, pd, pl = w / tot * 100.0, d / tot * 100.0, l / tot * 100.0
        gf, ga = float(v.get("gf") or 0), float(v.get("ga") or 0)
        return (
            f'<div class="fort-card" style="border-top:4px solid {col}">'
            '<div class="fc-top"><div class="min-w-0">'
            f'<div class="fort-title">{esc(tm.get("venueName") or tm["name"])}</div>'
            f'<div class="fort-sub">میزبانی {esc(tm["name"])} • {fa(tot)} بازی</div></div>'
            '<div class="ring-box"><svg viewBox="0 0 60 60" style="transform:rotate(-90deg)">'
            '<circle cx="30" cy="30" r="24" stroke="#ffffff1a" stroke-width="5" fill="none"/>'
            f'<circle cx="30" cy="30" r="24" stroke="{col}" stroke-width="5" stroke-linecap="round" fill="none" stroke-dasharray="{circ * min(1.0, pw / 100.0):.1f} {circ:.1f}"/>'
            f'</svg><span>{fa(round(pw))}٪</span></div></div>'
            '<div class="fort-mid">'
            f'<div class="fort-bar"><div style="width:{f1(pw)}%;background:{col}"></div>'
            f'<div style="width:{f1(pd)}%;background:#64748B"></div>'
            f'<div style="width:{f1(pl)}%;background:{ocol}"></div></div>'
            f'<div class="fort-wdl"><span style="color:{col}">{fa(w)} برد {esc(tm["code"])}</span>'
            f'<span class="d">{fa(d)} تساوی</span>'
            f'<span style="color:{ocol}">{fa(l)} برد {esc(op["code"])}</span></div></div>'
            f'<div class="fort-foot"><span>میانگین گل در این ورزشگاه:</span><b class="fm">{fa(f2(gf + ga))}</b></div>'
            "</div>"
        )

    return (
        '<div class="xm">'
        + _mod_header("دژ خانگی و تفکیک میزبانی", "<span class=fm>VENUE FORTRESS</span>", "#38BDF8")
        + f'<div class="two-col">{_vc(h, a, hc, ac)}{_vc(a, h, ac, hc)}</div></div>'
    )


def _render_kings(data: dict[str, Any]) -> str:
    h, a = data["home"], data["away"]
    hc, ac = esc(h.get("color") or "#EF0107"), esc(a.get("color") or "#38BDF8")

    def _kc(tm: dict[str, Any], col: str) -> str:
        k = tm.get("king") or {}
        return (
            f'<div class="sc-card" style="border-right:6px solid {col}">'
            f'<div class="sc-hatch" style="background:repeating-linear-gradient(45deg,{col} 0 8px,transparent 8px 18px)"></div>'
            f'<span class="sc-wm fd" style="color:{col}">{esc(str(k.get("num") or "9"))}</span>'
            '<div class="sc-top"><div class="min-w-0">'
            f'<div class="sc-name">{esc(k.get("name") or "—")}</div>'
            f'<span class="sc-era">{esc(k.get("era") or tm["name"])}</span></div>'
            f'<div class="sc-gbox" style="background:{col}24;border-color:{col}75">'
            f'<div class="sc-goals" style="color:{col}">{fa(k.get("goals", 0))}</div>'
            '<div class="sc-glbl">گل در H2H</div></div></div>'
            '<div class="sc-pills">'
            f'<span>{fa(k.get("assists", 0))} پاس گل</span>'
            f'<span class="gold">هر {fa(k.get("mpg", 0))} دقیقه یک گل</span>'
            "</div></div>"
        )

    crown = '<svg width="26" height="26" viewBox="0 0 24 24" fill="#FBBF24"><path d="M5 16L3 5l5.5 5L12 4l3.5 6L21 5l-2 11H5zm14 3c0 .6-.4 1-1 1H6c-.6 0-1-.4-1-1v-1h14v1z"/></svg>'
    return (
        '<div class="xm">'
        + _mod_header("پادشاهان و آقای‌گل‌های تقابل", "<span class='fm gold'>RIVALRY KINGS</span>", "#F59E0B")
        + f'<div class="kings-grid">{_kc(h, hc)}'
        f'<div class="kings-vs">{crown}<span class="vs-sq fd">VS</span></div>'
        f'{_kc(a, ac)}</div></div>'
    )


def _render_dna(data: dict[str, Any]) -> str:
    d = data.get("dna") or {}
    circ = 2 * math.pi * 24

    def _ring(pct: float, col: str, val_s: str, lbl: str) -> str:
        frac = min(1.0, max(0.06, pct / 100.0))
        return (
            '<div class="dna-tile"><div class="dna-ring">'
            '<svg viewBox="0 0 60 60" style="transform:rotate(-90deg)">'
            '<circle cx="30" cy="30" r="24" stroke="#ffffff18" stroke-width="5" fill="none"/>'
            f'<circle cx="30" cy="30" r="24" stroke="{col}" stroke-width="5.2" stroke-linecap="round" fill="none" '
            f'stroke-dasharray="{circ * frac:.1f} {circ:.1f}" style="filter:drop-shadow(0 0 6px {col}88)"/>'
            f'</svg><span class="dna-val">{val_s}</span></div>'
            f'<span class="dna-lbl">{lbl}</span></div>'
        )

    avg_g = float(d.get("avgGoals") or 0)
    btts = int(d.get("btts") or 0)
    o25 = int(d.get("over25") or 0)
    cards = float(d.get("cards") or 0)
    rings = (
        _ring(min(100, avg_g / 4.5 * 100), "#34D399", fa(f2(avg_g)), "میانگین گل")
        + _ring(btts, "#38BDF8", f"{fa(btts)}٪", "گلزنی هر دو تیم")
        + _ring(o25, "#FBBF24", f"{fa(o25)}٪", "بالای ۲.۵ گل")
        + _ring(min(100, cards / 7.0 * 100), "#F43F5E", fa(f1(cards)), "شاخص کارت")
    )
    return (
        '<div class="xe">'
        + _mod_header("امضای آماری و DNA تقابل", "<span class='fm em'>FIXTURE DNA</span>", "#34D399")
        + '<div class="dna-body">'
        f'<div class="dna-rings">{rings}</div>'
        '<div class="dna-ed">'
        '<span class="ed-pill">جمع‌بندی تحریریه XGPedia</span>'
        f'<h4 class="dna-ed-t">{esc(d.get("headline") or "")}</h4>'
        f'<p class="dna-ed-b">{esc(d.get("body") or "")}</p>'
        "</div></div></div>"
    )


def _render_timing(data: dict[str, Any]) -> str:
    h, a = data["home"], data["away"]
    hc, ac = esc(h.get("color") or "#EF0107"), esc(a.get("color") or "#38BDF8")
    raw = data.get("timing") or {}
    t_h = raw.get("home") or [0] * 6
    t_a = raw.get("away") or [0] * 6
    labels = ["۰-۱۵'", "۱۶-۳۰'", "۳۱-۴۵'", "۴۶-۶۰'", "۶۱-۷۵'", "۷۶-۹۰+'"]
    tots = [int(t_h[i]) + int(t_a[i]) for i in range(min(6, len(t_h), len(t_a)))]
    mx = max([1] + tots)
    hi = tots.index(max(tots)) if tots else 0

    cols = []
    for i, lbl in enumerate(labels[:len(tots)]):
        hv, av = int(t_h[i]), int(t_a[i])
        hot = (i == hi)
        cls = "tm-col hot" if hot else "tm-col"
        hh = max(10.0, hv / mx * 100.0)
        ah = max(10.0, av / mx * 100.0)
        cols.append(
            f'<div class="{cls}">'
            f'<div class="tm-val">{fa(hv + av)} گل</div>'
            '<div class="tm-bar-wrap">'
            f'<div class="tm-b" style="height:{hh:.1f}%;background:{hc};box-shadow:0 0 12px {hc}66"></div>'
            f'<div class="tm-b" style="height:{ah:.1f}%;background:{ac};box-shadow:0 0 12px {ac}66"></div>'
            f'</div><div class="tm-lbl fm" dir="ltr">{lbl}</div></div>'
        )
    peak_badge = f'<span class="tm-peak">پرتنش‌ترین بازه: {labels[hi]}</span>'
    return (
        '<div class="xm">'
        + _mod_header("نقشه دقیقه انفجار گل‌ها", peak_badge, "#F43F5E")
        + f'<div class="tm-grid">{"".join(cols)}</div></div>'
    )


def render_h2h_teams_html(
    data: dict[str, Any],
    *,
    fmt: str = "4:5",
    header_mode: str = "full",
    theme: str = "cinematic",
    slide: str = "slide1",
    modules: list[dict[str, Any]] | None = None,
) -> str:
    w, h_px = H2H_TEAMS_FORMATS.get(fmt, (1080, 1350))
    is_story = fmt == "9:16"
    is_wide = fmt == "16:9"
    # استاندارد یکپارچه فریم چهارگوشه قرمز XGPedia
    pad_top, pad_bot = (139, 171) if is_story else ((22, 16) if is_wide else (24, 20))

    if modules is None:
        modules, _ = get_h2h_teams_modules(data, slide)
    active = [m for m in modules if m.get("enabled")]
    is_dense = (slide == "slide5") or len(active) >= 4
    atm = theme if theme in ("cinematic", "editorial", "tactical") else "cinematic"

    home = data.get("home") or {}
    away = data.get("away") or {}
    hc = esc(home.get("color") or "#EF0107")
    ac = esc(away.get("color") or "#38BDF8")

    renderers = {
        "chronicle": _render_chronicle,
        "balance": _render_balance,
        "momentum": _render_momentum,
        "fortress": _render_fortress,
        "kings": _render_kings,
        "dna": _render_dna,
        "timing": _render_timing,
    }
    blocks = []
    for m in active:
        fn = renderers.get(m["id"])
        if not fn:
            continue
        is_half = m.get("span") == "half" and m.get("can_half", False)
        cls = "mf" if is_half else "w-full"
        blocks.append(f'<div class="mod-slot {cls}">{fn(data)}</div>')

    cx = w // 2
    rx = w - 146
    pitch_svg = (
        f'<svg id="fs" class="bg-svg" viewBox="0 0 {w} {h_px}" preserveAspectRatio="xMidYMid slice" fill="none">'
        '<defs><pattern id="tg" width="54" height="54" patternUnits="userSpaceOnUse"><path d="M54 0H0v54" stroke="#F8FAFC" stroke-opacity=".055"/></pattern>'
        '<radialGradient id="rf" cx="50%" cy="24%" r="42%"><stop offset="0" stop-color="#E62E45" stop-opacity=".26"/>'
        '<stop offset=".55" stop-color="#E62E45" stop-opacity=".07"/><stop offset="1" stop-color="#E62E45" stop-opacity="0"/></radialGradient></defs>'
        '<rect width="100%" height="100%" fill="url(#tg)"/>'
        f'<rect x="12" y="12" width="{w - 24}" height="{h_px - 24}" rx="18" stroke="#F8FAFC" stroke-opacity=".12" stroke-width="1.5"/>'
        f'<g stroke="#F8FAFC" stroke-opacity=".09" stroke-width="1.5"><line x1="{cx}" y1="12" x2="{cx}" y2="{h_px - 12}" stroke-dasharray="8 8"/>'
        f'<circle cx="{cx}" cy="300" r="145"/></g>'
        f'<g stroke="#F8FAFC" stroke-opacity=".075" stroke-width="1.5"><rect x="12" y="140" width="132" height="340"/>'
        f'<path d="M144 238A92 92 0 0 1 144 382"/><rect x="{rx}" y="140" width="132" height="340"/>'
        f'<path d="M{rx} 238A92 92 0 0 0 {rx} 382"/></g>'
        f'<circle cx="{cx}" cy="300" r="245" fill="url(#rf)"/>'
        f'<circle cx="{cx}" cy="300" r="208" stroke="#E62E45" stroke-opacity=".22" stroke-width="1.3" stroke-dasharray="4 6"/>'
        f'<circle cx="{cx}" cy="300" r="292" stroke="#F8FAFC" stroke-opacity=".07"/>'
        f'<circle cx="{cx}" cy="300" r="380" stroke="#F8FAFC" stroke-opacity=".04"/>'
        f'<path d="M24 44V24H44M{w - 24} 44V24H{w - 44}M24 {h_px - 44}V{h_px - 24}H44M{w - 24} {h_px - 44}V{h_px - 24}H{w - 44}" '
        'stroke="#E62E45" stroke-width="2.4" stroke-linecap="round"/>'
        '<g id="hud-tel" font-family="JetBrains Mono,monospace" font-size="11" font-weight="700" fill="#94A3B8" letter-spacing="1.6">'
        f'<text x="56" y="34">XGPEDIA • H2H ENGINE v2.0</text>'
        f'<text x="{w - 56}" y="34" text-anchor="end">SYS.OPTICS // ACTIVE</text></g></svg>'
    )
    beams_bg = (
        f"linear-gradient(125deg,{hc}2e 0%,transparent 44%),"
        f"linear-gradient(235deg,{ac}2e 0%,transparent 44%),"
        f"radial-gradient(circle at 86% 24%,{hc}42,transparent 46%),"
        f"radial-gradient(circle at 14% 24%,{ac}42,transparent 46%),"
        "radial-gradient(circle at 50% 26%,#e62e452e,transparent 48%)"
    )

    logo_uri = _brand_logo_data_uri()
    font_css = build_embedded_font_css()
    hero_html = _render_hero(data, header_mode, fmt, is_dense)
    trophy_svg = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#E62E45" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M8 21h8m-4-4v4m-5-17h10v5a5 5 0 01-10 0V4zM5 6H3v2a3 3 0 003 3h1m12-5h2v2a3 3 0 01-3 3h-1"/></svg>'
    stad_svg = '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#E62E45" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="8" rx="9" ry="3.5"/><path d="M3 8v6c0 1.93 4.03 3.5 9 3.5s9-1.57 9-3.5V8M7 11.2v5.8M12 11.5v6M17 11.2v5.8"/></svg>'

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl"><head><meta charset="UTF-8"><style>
{font_css}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:{w}px;height:{h_px}px;overflow:hidden;background:#0D1730;color:#F8FAFC;font-family:'Vazirmatn',sans-serif;font-feature-settings:"tnum";font-variant-numeric:tabular-nums;}}
.fm{{font-family:'JetBrains Mono','Space Grotesk',monospace;}}
.fd{{font-family:'Space Grotesk',sans-serif;}}
.fc{{display:flex;align-items:center;justify-content:center;}}
.min-w-0{{min-width:0;}}
#ea{{position:relative;width:{w}px;height:{h_px}px;background:#0D1730;display:flex;flex-direction:column;justify-content:space-between;padding:{pad_top}px 0 {pad_bot}px 0;overflow:hidden;}}
#ea.atm-editorial{{background:#091124;}}
#ea.atm-editorial #beams{{opacity:.38;}} #ea.atm-editorial #fs{{opacity:.48;}}
#ea.atm-tactical{{background:#071224;}} #ea.atm-tactical .xm,#ea.atm-tactical .xe{{border-color:#38bdf83d;}}
#beams,.bg-svg,.scanlines{{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0;}}
.scanlines{{background:repeating-linear-gradient(to bottom,#ffffff04 0 1px,#0000 1px 4px);}}
.hdr{{position:relative;z-index:5;display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 36px 8px;flex-shrink:0;}}
.hdr-info{{display:flex;flex-direction:column;gap:6px;min-width:0;}}
.hdr-pills{{display:flex;align-items:center;flex-wrap:wrap;gap:8px;}}
.c-pill{{display:inline-flex;align-items:center;gap:8px;padding:5px 15px;border-radius:999px;font-size:19px;font-weight:900;background:#152347eb;border:1px solid #ffffff30;color:#F8FAFC;}}
.c-pill.red{{background:#e62e452e;border-color:#e62e458c;color:#FF7084;font-size:17px;font-weight:800;}}
.c-meta{{display:flex;align-items:center;flex-wrap:wrap;gap:10px;font-size:16px;font-weight:700;color:#E2E8F0;}}
.c-meta .stad{{display:inline-flex;align-items:center;gap:5px;color:#FFF;}}
.c-meta .scope{{padding:2px 11px;border-radius:999px;background:rgba(56,189,248,0.18);border:1px solid rgba(56,189,248,0.45);color:#7DD3FC;font-size:14px;font-weight:800;}}
.hdr-logo{{height:42px;width:auto;flex-shrink:0;}}
.stage{{position:relative;z-index:5;flex:1;padding:8px 40px;display:flex;flex-direction:column;justify-content:space-between;gap:12px;overflow:hidden;min-height:0;}}
.stage.wide{{display:grid;grid-template-columns:5fr 7fr;gap:22px;align-items:stretch;}}
.hero-full{{display:flex;flex-direction:column;gap:10px;flex-shrink:0;}}
.hf-grid{{display:grid;grid-template-columns:4fr 3fr 4fr;align-items:center;gap:8px;}}
.hero-col{{display:flex;flex-direction:column;align-items:center;text-align:center;min-width:0;}}
.hero-name{{font-size:38px;font-weight:900;color:#FFF;line-height:1.08;}}
.hero-sub{{font-size:15px;font-weight:700;color:#CBD5E1;margin-top:3px;}}
.hero-win-box{{margin-top:8px;padding:5px 16px;border-radius:14px;background:#071024e6;border:1px solid;display:inline-flex;align-items:baseline;gap:7px;}}
.hero-win-num{{font-size:30px;font-weight:900;line-height:1;}}
.hero-win-lbl{{font-size:15px;font-weight:800;color:#E2E8F0;}}
.hero-streak{{margin-top:6px;padding:2px 12px;border-radius:999px;border:1px solid;font-size:12.5px;font-weight:800;max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.hero-mid{{display:flex;align-items:center;justify-content:center;}}
.hero-gauge-svg{{width:100%;max-width:270px;height:auto;overflow:visible;}}
.hf-bars{{display:flex;flex-direction:column;gap:8px;}}
.pc{{width:100%;height:42px;border-radius:999px;overflow:hidden;display:flex;background:#070e1feb;border:2px solid #ffffff2e;box-shadow:inset 0 2px 10px #0000008c,0 10px 24px -8px #000000a0;}}
.pcc{{height:32px;border-width:1.5px;}} .pcc .ps{{font-size:16px;}}
.ps{{height:100%;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:21px;white-space:nowrap;position:relative;overflow:hidden;}}
.ps::after{{content:"";position:absolute;inset:0;background:linear-gradient(180deg,#ffffff30 0%,transparent 48%,#00000024 100%);}}
.ps-sep{{width:2px;height:100%;background:#030711bf;flex-shrink:0;z-index:2;}}
.hero-strip{{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;padding:7px 18px;border-radius:14px;background:#071024eb;border:1px solid #ffffff24;}}
.hs-side{{display:flex;align-items:center;gap:9px;}}
.hs-side.away{{justify-content:flex-end;}}
.hero-strip-val{{font-size:21px;font-weight:900;line-height:1;}} .hero-strip-val.w{{color:#FFF;font-size:19px;}}
.hero-strip-lbl{{font-size:14px;font-weight:700;color:#CBD5E1;}} .hero-strip-lbl.dim{{color:#94A3B8;font-size:13px;}}
.hs-dot{{color:#475569;}}
.hs-mid span{{padding:3px 12px;border-radius:999px;background:#ffffff14;border:1px solid #ffffff24;font-size:14px;font-weight:800;color:#E2E8F0;}}
.hs-mid b{{color:#FCD34D;}}
.hero-compact{{border-radius:22px;background:#0B162Feb;border:1px solid #ffffff29;padding:12px 20px;display:flex;flex-direction:column;gap:10px;}}
.hc-grid{{display:grid;grid-template-columns:4fr 3fr 4fr;align-items:center;gap:10px;}}
.hc-side{{display:flex;align-items:center;gap:12px;min-width:0;}}
.hc-side.away{{justify-content:flex-end;text-align:left;}}
.hc-name{{font-size:25px;font-weight:900;color:#FFF;line-height:1.15;}}
.hc-sub{{font-size:15px;font-weight:800;}}
.hc-mid{{display:flex;flex-direction:column;align-items:center;gap:5px;}}
.hc-tag{{padding:3px 14px;border-radius:999px;background:#E62E45;color:#FFF;font-family:'Space Grotesk',sans-serif;font-weight:800;font-size:14px;}}
.hc-wdw{{display:flex;align-items:center;gap:12px;padding:4px 14px;border-radius:12px;background:#050B1A;border:1px solid #ffffff24;font-size:25px;font-weight:900;}}
.hc-dr{{color:#94A3B8;font-size:20px;}}
.mods-grid{{flex:1;min-height:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;align-content:stretch;}}
.mod-slot{{display:flex;min-width:0;min-height:0;}}
.w-full{{grid-column:1 / -1;}}
.mf{{grid-column:span 1;}}
.xm,.xe{{position:relative;flex:1;border-radius:22px;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;box-shadow:0 18px 42px -12px #000000a6,inset 0 1px 0 #ffffff24;padding:14px 20px 16px;}}
.xm{{background:linear-gradient(160deg,#101d3be6,#070d1df5);border:1.5px solid #f8fafc24;}}
.xe{{background:linear-gradient(155deg,#142244eb,#080e1ff7);border:1.5px solid #7fa6e842;}}
.mh{{display:flex;align-items:center;justify-content:space-between;gap:10px;padding-bottom:8px;margin-bottom:10px;border-bottom:1px solid #ffffff1f;flex-shrink:0;}}
.mh-left{{display:flex;align-items:center;gap:10px;min-width:0;}}
.mh-bar{{width:7px;height:24px;border-radius:99px;flex-shrink:0;}}
.mt{{font-size:22px;font-weight:900;color:#FFF;}}
.mh-sub{{font-size:14px;font-weight:800;color:#CBD5E1;flex-shrink:0;}}
.mh-sub .gold{{color:#FCD34D;}} .mh-sub .em{{color:#6EE7B7;}}
.tl-wrap{{position:relative;flex:1;display:flex;align-items:center;}}
.tl-line{{position:absolute;left:24px;right:24px;top:50%;height:3px;border-radius:99px;opacity:.45;}}
.tl-grid{{position:relative;z-index:2;display:grid;grid-template-columns:repeat(5,1fr);gap:10px;width:100%;align-items:stretch;}}
.tl-card{{border-radius:16px;background:#091226f2;padding:10px 8px;display:flex;flex-direction:column;align-items:center;justify-content:space-between;gap:6px;text-align:center;}}
.tl-latest{{padding:2px 9px;border-radius:999px;background:#E62E45;color:#FFF;font-size:11px;font-weight:900;}}
.tl-meta{{font-size:11.5px;font-weight:700;color:#94A3B8;}}
.tl-comp{{padding:2px 7px;border-radius:6px;background:#ffffff14;color:#E2E8F0;font-size:11.5px;font-weight:700;}}
.tl-score{{padding:5px 12px;border-radius:12px;border:1px solid;font-size:24px;font-weight:900;color:#FFF;line-height:1;}}
.tl-bot{{width:100%;display:flex;flex-direction:column;gap:5px;}}
.tl-xgbar{{height:6px;width:100%;border-radius:99px;overflow:hidden;display:flex;background:#ffffff1a;}}
.tl-xg{{font-size:12px;font-weight:800;color:#E2E8F0;}}
.tl-venue{{display:flex;align-items:center;justify-content:center;gap:5px;font-size:11.5px;font-weight:700;color:#94A3B8;}}
.tl-dot{{width:7px;height:7px;border-radius:99px;flex-shrink:0;}}
.bal-list{{flex:1;display:flex;flex-direction:column;justify-content:center;gap:9px;}}
.bal-top{{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;margin-bottom:4px;}}
.bal-val{{font-size:23px;font-weight:900;line-height:1;}} .bal-val.r{{text-align:right;}} .bal-val.l{{text-align:left;}}
.bal-lbl{{font-size:16px;font-weight:800;color:#F1F5F9;text-align:center;padding:0 8px;}}
.bal-bars{{display:grid;grid-template-columns:1fr 1fr;gap:8px;}}
.ct{{height:13px;background:#ffffff14;overflow:hidden;display:flex;align-items:center;position:relative;}}
.ct.hs,.ch{{border-radius:0 99px 99px 0;}} .ct.as,.ca{{border-radius:99px 0 0 99px;}}
.ct.hs{{justify-content:flex-end;}} .ct.as{{justify-content:flex-start;}}
.ch,.ca{{height:100%;position:relative;}}
.ch::after,.ca::after{{content:"";position:absolute;top:0;bottom:0;width:6px;background:#fff;opacity:.88;box-shadow:0 0 10px #fff;border-radius:99px;}}
.ch::after{{left:0;}} .ca::after{{right:0;}}
.bal-foot{{margin-top:10px;padding-top:10px;border-top:1px solid #ffffff1f;display:grid;grid-template-columns:1fr 1fr;gap:10px;}}
.bal-big{{padding:7px 12px;border-radius:12px;border:1px solid;display:flex;align-items:center;justify-content:space-between;gap:8px;}}
.bb-k{{font-size:12.5px;font-weight:700;color:#CBD5E1;}} .bb-v{{font-size:14.5px;font-weight:900;color:#FFF;}}
.mom-leg{{display:flex;gap:14px;font-size:14px;font-weight:800;}}
.mom-leg span{{display:inline-flex;align-items:center;gap:6px;}}
.mom-leg i{{width:10px;height:10px;border-radius:99px;display:inline-block;}}
.mom-svg{{width:100%;max-height:230px;height:auto;}}
.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:12px;flex:1;align-items:stretch;}}
.fort-card{{border-radius:16px;background:#091226eb;border:1px solid #ffffff24;padding:13px 15px;display:flex;flex-direction:column;justify-content:space-between;gap:10px;}}
.fc-top{{display:flex;align-items:center;justify-content:space-between;gap:8px;}}
.fort-title{{font-size:18px;font-weight:900;color:#FFF;}}
.fort-sub{{font-size:13px;font-weight:700;color:#94A3B8;margin-top:2px;}}
.ring-box{{position:relative;width:54px;height:54px;display:flex;align-items:center;justify-content:center;flex-shrink:0;}}
.ring-box svg{{width:100%;height:100%;}}
.ring-box span{{position:absolute;font-size:14px;font-weight:900;color:#FFF;}}
.fort-bar{{height:12px;border-radius:99px;overflow:hidden;display:flex;background:#ffffff1a;border:1px solid #ffffff24;}}
.fort-wdl{{display:flex;justify-content:space-between;font-size:12.5px;font-weight:800;margin-top:6px;}}
.fort-wdl .d{{color:#94A3B8;}}
.fort-foot{{padding-top:8px;border-top:1px solid #ffffff1a;display:flex;justify-content:space-between;font-size:13.5px;font-weight:700;color:#E2E8F0;}}
.kings-grid{{display:grid;grid-template-columns:5fr 1fr 5fr;gap:10px;align-items:stretch;flex:1;}}
.sc-card{{position:relative;overflow:hidden;border-radius:20px;background:#0A1328e6;border:1px solid #ffffff29;padding:14px 16px;display:flex;flex-direction:column;justify-content:space-between;gap:10px;}}
.sc-hatch{{position:absolute;left:-28px;top:-28px;width:120px;height:120px;transform:rotate(12deg);opacity:.12;pointer-events:none;}}
.sc-wm{{position:absolute;left:12px;bottom:-6px;font-size:86px;font-weight:900;line-height:1;opacity:.07;pointer-events:none;}}
.sc-top{{position:relative;z-index:2;display:flex;align-items:flex-start;justify-content:space-between;gap:8px;}}
.sc-name{{font-size:21px;font-weight:900;color:#FFF;}}
.sc-era{{display:inline-block;margin-top:4px;padding:2px 9px;border-radius:8px;background:#ffffff1a;font-size:12.5px;font-weight:700;color:#E2E8F0;}}
.sc-gbox{{text-align:center;padding:5px 11px;border-radius:14px;border:1px solid;flex-shrink:0;}}
.sc-goals{{font-size:28px;font-weight:900;line-height:1;}}
.sc-glbl{{font-size:10.5px;font-weight:800;color:#F1F5F9;margin-top:2px;}}
.sc-pills{{position:relative;z-index:2;padding-top:9px;border-top:1px solid #ffffff1f;display:flex;flex-wrap:wrap;gap:6px;}}
.sc-pills span{{padding:3px 9px;border-radius:10px;background:#ffffff14;border:1px solid #ffffff1f;font-size:12.5px;font-weight:800;color:#F1F5F9;}}
.sc-pills span.gold{{color:#FCD34D;}}
.kings-vs{{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;}}
.vs-sq{{width:44px;height:44px;border-radius:14px;background:linear-gradient(135deg,#E62E45,#F59E0B);border:2px solid #ffffff66;display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:800;color:#FFF;}}
.dna-body{{flex:1;display:flex;flex-direction:column;justify-content:space-between;gap:10px;}}
.dna-rings{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;}}
.dna-tile{{border-radius:14px;background:#091226eb;border:1px solid #ffffff24;padding:8px 6px;display:flex;flex-direction:column;align-items:center;gap:5px;text-align:center;}}
.dna-ring{{position:relative;width:54px;height:54px;display:flex;align-items:center;justify-content:center;}}
.dna-ring svg{{width:100%;height:100%;}}
.dna-val{{position:absolute;font-size:14.5px;font-weight:900;color:#FFF;}}
.dna-lbl{{font-size:12px;font-weight:800;color:#CBD5E1;}}
.dna-ed{{border-radius:14px;background:#070E20e6;border:1px solid #ffffff24;border-right:5px solid #E62E45;padding:10px 14px;}}
.ed-pill{{display:inline-block;padding:2px 8px;border-radius:6px;background:#e62e4540;border:1px solid #e62e458c;color:#FF7084;font-size:11px;font-weight:900;margin-bottom:4px;}}
.dna-ed-t{{font-size:18px;font-weight:900;color:#FCD34D;margin-bottom:3px;}}
.dna-ed-b{{font-size:14.5px;font-weight:600;color:#F1F5F9;line-height:1.52;}}
.tm-peak{{padding:3px 11px;border-radius:999px;background:#e62e4538;border:1px solid #e62e458c;color:#FF7084;font-size:13px;font-weight:800;}}
.tm-grid{{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;flex:1;align-items:stretch;}}
.tm-col{{display:flex;flex-direction:column;align-items:center;justify-content:flex-end;gap:5px;border-radius:14px;padding:7px;background:#ffffff08;border:1px solid #ffffff1a;}}
.tm-col.hot{{background:#e62e4529;border-color:#e62e45a6;box-shadow:0 0 20px -6px rgba(230,46,69,.5);}}
.tm-val{{font-size:13.5px;font-weight:900;color:#E2E8F0;}} .tm-col.hot .tm-val{{color:#FF7084;}}
.tm-bar-wrap{{width:100%;height:105px;display:flex;align-items:flex-end;justify-content:center;gap:5px;}}
.tm-b{{width:15px;border-radius:6px 6px 2px 2px;}}
.tm-lbl{{font-size:12.5px;font-weight:800;color:#94A3B8;}} .tm-col.hot .tm-lbl{{color:#FFF;}}
#ea.dv .hero-name{{font-size:28px;}} #ea.dv .hero-gauge-svg{{max-width:205px;}} #ea.dv .xm,#ea.dv .xe{{padding:9px 13px;border-radius:15px;}}
#ea.dv .mt{{font-size:16px;}} #ea.dv .tl-score{{font-size:18px;}} #ea.dv .bal-val{{font-size:17px;}} #ea.dv .pc{{height:32px;}} #ea.dv .ps{{font-size:15px;}}
.ftr{{position:relative;z-index:5;padding:10px 44px 10px;border-top:1px solid #ffffff24;display:flex;align-items:center;justify-content:space-between;font-size:15px;color:#CBD5E1;flex-shrink:0;}}
.ftr-left{{display:flex;align-items:center;gap:9px;}}
.ftr-dot{{width:10px;height:10px;border-radius:99px;background:#E62E45;box-shadow:0 0 10px #E62E45;}}
.ftr-tag{{font-size:15px;font-weight:800;letter-spacing:.12em;color:#F1F5F9;}}
.ftr-right{{display:flex;align-items:center;gap:10px;}}
.ftr-right b{{color:#FFF;font-size:17px;}}

footer, footer .fbw, footer .cf-row, footer .fi, footer .cf-left, footer .cf-right, .xg-footer, .foot-row, .card-footer{{flex-wrap:nowrap!important;white-space:nowrap!important;min-width:0!important;}}
footer span, footer div, .pl-foot-tag, .pl-foot-s, .in-foot-tag, .pr-foot-tag, .st-foot-tag, .cf-tag{{white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;min-width:0!important;}}
</style></head><body>
<div id="ea" class="atm-{atm}{' dv' if is_dense else ''}">
  <div id="beams" style="background:{beams_bg}"></div>
  {pitch_svg}
  <div class="scanlines"></div>
  <header class="hdr">
    <div class="hdr-info">
      <div class="hdr-pills">
        <span class="c-pill">{trophy_svg}<span>{esc(data.get("competition") or "فوتبال")}</span></span>
        <span class="c-pill red">{fa(esc(data.get("round") or "تقابل مستقیم"))}</span>
      </div>
      <div class="c-meta">
        <span>{fa(esc(data.get("eraNote") or ""))}</span>
        <span style="color:#64748B">•</span>
        <span class="stad">{stad_svg}<span>{esc(data.get("stadiumScope") or "")}</span></span>
        <span class="scope">{esc(data.get("scopeBadge") or "تمامی رقابت‌ها")}</span>
      </div>
    </div>
    <img class="hdr-logo" src="{logo_uri}" alt="XGPedia"/>
  </header>
  <main class="stage{' wide' if is_wide else ''}">
    {hero_html}
    <section class="mods-grid">{"".join(blocks)}</section>
  </main>
  <footer class="ftr">
    <div class="ftr-left"><span class="ftr-dot"></span><span class="ftr-tag fm" dir="ltr">HEAD-TO-HEAD ARCHIVE • {esc(str(data.get("leagueEn") or "FOOTBALL").upper())} • ALL-TIME</span></div>
    <div class="ftr-right fm" dir="ltr"><b>@XGPedia</b><span>|</span><span>{esc(data.get("source") or "Opta / XGPedia Archive")}</span></div>
  </footer>
</div></body></html>"""
