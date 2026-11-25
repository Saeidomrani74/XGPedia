"""کارت «نتایج بازی‌های روز» (Matchday Results Studio — D59) — بازسازی ۱:۱ مطابق `matchday results.html` و ۱۰۰٪ آفلاین.

ویژگی‌های ۱:۱:
  - پس‌زمینه `#0A1329` + دو پرتو نوری قطری (`flL`/`flR`) + شبکه `54×54` + خطوط پرسپکتیو + نوار درخشان بالایی + واترمارک غول‌پیکر حاشیه‌دار + هاله دوگانه رنگ تیم‌های نبرد شاخص
  - هدر دقیق: نام لیگ(ها) یا «روز شلوغ فوتبال» (بیش از ۲ لیگ) + نشان «تابلوی نتایج» + تاریخ شمسی + تیتر توصیفی روز + گیج دایره‌ای «زهر گلزنی روز» (`EFF%`, گل, `xG`) کنار لوگوی XGPedia
  - نبرد شاخص روز با حاشیه گرادیان رنگ دو تیم، اسکوربورد درخشان قرمز، نتیجه نیمه اول، نمودار پلکانی `CUMULATIVE xG RACE (0' — 90')` با پین دقایق گل و ردیف گلزنان
  - گرید بنتو ۲ ستونه **بدون تکرار بازی شاخص** با جداکننده لیگ، حاشیه رنگی هر کارت مطابق رنگ دو تیم، نوار xG، تایم‌لاین ۹۰ دقیقه‌ای پین گل‌ها و ردیف گلزنان
  - داک تله‌متری ۳بخشی پایین کارت (`⭐ ستاره روز` با نشان شش‌ضلعی، `راندمان کل روز` و `نبض دقایق گل`)
  - ۱۰۰٪ آفلاین + فواصل عمودی یکسان چهارگوشه قرمز + فوتر اکیداً تک‌خطی + `null ≠ 0`.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

from src.xgpedia.providers.pl_badges_free import resolve_distinct_team_colors
from src.xgpedia.render.card_kit.helpers import esc
from src.xgpedia.render.cards import _brand_logo_data_uri
from src.xgpedia.render.studio_engine import build_embedded_font_css

def _mirror_corners_html(w: int, h: int) -> str:
    return (
        f'<svg class="xg-mirror" style="position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:20" viewBox="0 0 {w} {h}" fill="none">'
        f'<path d="M24 44V24H44M{w-24} 44V24H{w-44}M24 {h-44}V{h-24}H44M{w-24} {h-44}V{h-24}H{w-44}" stroke="#E62E45" stroke-opacity=".78" stroke-width="2.4" stroke-linecap="square"/></svg>'
    )


def _brand_logo_img(height: int = 44) -> str:
    uri = _brand_logo_data_uri()
    if uri:
        return f'<img src="{uri}" style="height:{height}px;width:auto;display:block;flex-shrink:0" alt="XGPedia"/>'
    return '<span class="fd" style="font-weight:800;font-size:28px"><span style="color:#E62E45">XG</span><span style="color:#F8FAFC">Pedia</span></span>'


MATCHDAY_RESULTS_FORMATS: dict[str, tuple[int, int]] = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}

MATCHDAY_RESULTS_SLIDES: list[tuple[str, str, str, list[str]]] = [
    ("slide1", "اسلاید ۱: بنتو ادیتوریال + نمودار پلکانی xG", "editorial", ["featured", "bento_grid", "footer_dock"]),
    ("slide2", "اسلاید ۲: ستون نتایج پخش زنده", "scoreboard", ["scoreboard", "footer_dock"]),
    ("slide3", "اسلاید ۳: آزمایشگاه xG و سرقت آماری", "xglens", ["xg_divergence", "heist_card", "scoreboard"]),
    ("slide4", "اسلاید ۴: تالار ستارگان + نبض دقایق گل", "awards", ["awards", "timing_pulse", "bento_grid"]),
    ("slide5", "اسلاید ۵: جلد مجله‌ای وایرال", "poster", ["featured", "scoreboard", "footer_dock"]),
]

MATCHDAY_RESULTS_MODULE_DEFS: list[tuple[str, str, bool]] = [
    ("featured", "نبرد شاخص روز + نمودار پلکانی xG", False),
    ("bento_grid", "گرید بنتو ۲ ستونه نتایج (بدون تکرار شاخص)", False),
    ("scoreboard", "ستون نتایج پخش زنده (Broadcast Rows)", False),
    ("xg_divergence", "نمودار دمبل شکاف گل و xG", False),
    ("heist_card", "پرونده سرقت آماری روز (xG Heist)", False),
    ("awards", "تالار ستارگان روز (۳ کارت افتخار)", False),
    ("timing_pulse", "نبض زمانی گل‌های روز (۱۵ دقیقه‌ای)", False),
    ("footer_dock", "داک تله‌متری (ستاره روز + راندمان + نبض)", False),
]


def _fa(v: Any) -> str:
    return str(v).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _en_digits(s: str) -> str:
    return str(s or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))


def _lum(hex_col: str) -> float:
    c = (hex_col or "#E62E45").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        n = int(c[:6], 16)
    except ValueError:
        return 0.2
    rgb = [(n >> 16) & 255, (n >> 8) & 255, n & 255]
    a = [(v / 255.0) / 12.92 if (v / 255.0) <= 0.03928 else (((v / 255.0) + 0.055) / 1.055) ** 2.4 for v in rgb]
    return 0.2126 * a[0] + 0.7152 * a[1] + 0.0722 * a[2]


def _ctr(hex_col: str) -> str:
    return "#070D1D" if _lum(hex_col) > 0.55 else "#FFFFFF"


def _bright(hex_col: str) -> str:
    if _lum(hex_col) >= 0.19:
        return hex_col
    c = (hex_col or "#E62E45").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        n = int(c[:6], 16)
    except ValueError:
        return "#38BDF8"
    r = min(255, round(0.48 * ((n >> 16) & 255) + 132.6))
    g = min(255, round(0.48 * ((n >> 8) & 255) + 132.6))
    b = min(255, round(0.48 * (n & 255) + 132.6))
    return f"rgb({r},{g},{b})"


def _accent(theme: str) -> str:
    return "#38BDF8" if theme == "ucl" else ("#F59E0B" if theme == "gold" else "#E62E45")


def _extract_minutes(scorers_str: str, goals_list: list[dict[str, Any]] | None, team_flag: str) -> list[int]:
    mins: list[int] = []
    if scorers_str:
        s = _en_digits(scorers_str)
        for m in re.finditer(r"(\d{1,2})(?:\+(\d{1,2}))?\s*['’′]", s):
            base = int(m.group(1))
            extra = int(m.group(2)) if m.group(2) else 0
            mins.append(min(94, max(1, base + min(4, extra))))
    if not mins and goals_list:
        for g in goals_list:
            if isinstance(g, dict) and g.get("team") == team_flag and g.get("min") is not None:
                mins.append(min(94, max(1, int(g["min"]))))
    return sorted(mins)


def _format_scorers(side: dict[str, Any], goals_list: list[dict[str, Any]] | None, team_flag: str) -> str:
    raw = str(side.get("scorers") or "").strip()
    if raw:
        return _fa(raw)
    if goals_list:
        parts = []
        for g in goals_list:
            if isinstance(g, dict) and g.get("team") == team_flag:
                nm = str(g.get("scorer") or "").strip()
                mn = g.get("min")
                if nm:
                    parts.append(f"{nm} {_fa(mn)}'" if mn is not None else nm)
        return " • ".join(parts)
    return ""


def _crest_svg(team: dict[str, Any], uid: str, sz: int) -> str:
    from src.xgpedia.providers.pl_badges_free import get_pl_badge_data_uri
    logo_uri = team.get("logoUrl") or get_pl_badge_data_uri(
        str(team.get("name") or ""), tla_hint=str(team.get("code") or ""), fetch_network=False
    )
    if logo_uri:
        return (
            f'<div class="fc" style="width:{sz}px;height:{sz}px;flex-shrink:0;border-radius:50%;'
            f'background:radial-gradient(circle,rgba(255,255,255,.12),rgba(6,13,30,.72));'
            f'padding:{max(5, sz//11)}px;filter:drop-shadow(0 8px 16px #000000a6)">'
            f'<img src="{esc(logo_uri)}" style="width:100%;height:100%;object-fit:contain;display:block" alt="{esc(team.get("code",""))}"/></div>'
        )
    c1 = str(team.get("color") or "#E62E45")
    c2 = str(team.get("secondary") or team.get("color2") or "#FFFFFF")
    code = esc(str(team.get("code") or "FC")[:3].upper())
    path = "M90 16L150 40V88C150 128 124.5 156.5 90 166C55.5 156.5 30 128 30 88V40Z"
    pill_bg = "#0D1730" if _lum(c1) > 0.65 else "#070d1dc4"
    return (
        f'<svg width="{sz}" height="{sz}" viewBox="0 0 180 180" fill="none" style="filter:drop-shadow(0 10px 18px #000000a6);flex-shrink:0">'
        f'<defs><linearGradient id="g_{uid}" x1="20" y1="15" x2="160" y2="165" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{c2}" stop-opacity=".95"/><stop offset=".5" stop-color="{c1}" stop-opacity=".92"/>'
        f'<stop offset="1" stop-color="{c2}" stop-opacity=".7"/></linearGradient>'
        f'<clipPath id="c_{uid}"><path d="{path}"/></clipPath></defs>'
        f'<path d="M90 12L154 38V88C154 130.5 127 160.5 90 170.5C53 160.5 26 130.5 26 88V38Z" fill="{c1}" fill-opacity=".26"/>'
        f'<g clip-path="url(#c_{uid})"><rect x="25" y="12" width="130" height="158" fill="{c1}"/>'
        f'<path d="M25 112L155 56V84L25 140Z" fill="{c2}" fill-opacity=".28"/>'
        f'<path d="M90 16L150 40V58L90 34L30 58V40Z" fill="{c2}" fill-opacity=".92"/>'
        f'<ellipse cx="90" cy="30" rx="65" ry="28" fill="#fff" fill-opacity=".15"/></g>'
        f'<path d="{path}" stroke="url(#g_{uid})" stroke-width="5.5"/>'
        f'<rect x="40" y="66" width="100" height="50" rx="14" fill="{pill_bg}" stroke="{c2}" stroke-opacity=".58" stroke-width="2"/>'
        f'<text x="90" y="102" text-anchor="middle" fill="#fff" font-family="Space Grotesk,JetBrains Mono,sans-serif" font-weight="800" font-size="33" letter-spacing="1.5">{code}</text>'
        f'<circle cx="90" cy="138" r="5" fill="{_ctr(c1)}" fill-opacity=".88"/></svg>'
    )


def _verdict(m: dict[str, Any]) -> tuple[str, str, str, bool]:
    hs = int((m.get("home") or {}).get("score") or 0)
    as_ = int((m.get("away") or {}).get("score") or 0)
    hxg = (m.get("home") or {}).get("xg")
    axg = (m.get("away") or {}).get("xg")
    diff = hs - as_
    tot = hs + as_
    if hxg is not None and axg is not None:
        hxg, axg = float(hxg), float(axg)
        xd = hxg - axg
        xt = hxg + axg
        if (diff > 0 and xd < -0.35) or (diff < 0 and xd > 0.35):
            return ("vb-heist", "سرقت آماری", "⚡", True)
        if tot >= 4 and xt >= 3.2:
            return ("vb-thriller", "آتش‌بازی", "🔥", False)
        if (diff > 0 and hs - hxg >= 0.75) or (diff < 0 and as_ - axg >= 0.75):
            return ("vb-clinical", "کلینیکال", "🎯", False)
        if diff == 0 and tot <= 1 and xt <= 2.2:
            return ("vb-cagey", "قفل تاکتیکی", "🛡", False)
        if diff == 0:
            return ("vb-fair", "تساوی عادلانه", "⚖", False)
        return ("vb-deserved", "برد شایسته", "✓", False)
    if tot >= 4:
        return ("vb-thriller", "آتش‌بازی", "🔥", False)
    if abs(diff) >= 3:
        return ("vb-clinical", "کلینیکال", "🎯", False)
    if diff == 0:
        return ("vb-fair", "تساوی", "⚖", False)
    return ("vb-deserved", "برد شایسته", "✓", False)


def _goal_timeline_svg(m: dict[str, Any]) -> str:
    h_mins = _extract_minutes(str((m.get("home") or {}).get("scorers") or ""), m.get("goals"), "h")
    a_mins = _extract_minutes(str((m.get("away") or {}).get("scorers") or ""), m.get("goals"), "a")
    hc, ac = resolve_distinct_team_colors(str((m.get("home") or {}).get("color") or "#E62E45"), str((m.get("away") or {}).get("color") or "#38BDF8"))
    px = lambda mn: 10.0 + (min(93, mn) / 93.0) * 220.0
    hd = "".join(f'<circle cx="{px(mn):.1f}" cy="5.5" r="3.6" fill="{hc}" stroke="#fff" stroke-width="1.2"/>' for mn in h_mins)
    ad = "".join(f'<circle cx="{px(mn):.1f}" cy="16.5" r="3.6" fill="{ac}" stroke="#fff" stroke-width="1.2"/>' for mn in a_mins)
    return (
        '<svg style="width:100%;height:20px;display:block" viewBox="0 0 240 22" fill="none" dir="ltr">'
        '<line x1="10" y1="11" x2="230" y2="11" stroke="#ffffff26" stroke-width="1.5" stroke-linecap="round"/>'
        '<line x1="120" y1="6" x2="120" y2="16" stroke="#ffffff38" stroke-width="1.2"/>'
        '<circle cx="10" cy="11" r="2" fill="#64748B"/><circle cx="230" cy="11" r="2" fill="#64748B"/>'
        f'{hd}{ad}</svg>'
    )


def _step_xg_chart(m: dict[str, Any], compact: bool) -> str:
    h_xg = (m.get("home") or {}).get("xg")
    a_xg = (m.get("away") or {}).get("xg")
    if h_xg is None or a_xg is None:
        return ""
    h_xg, a_xg = float(h_xg), float(a_xg)
    h_mins = _extract_minutes(str((m.get("home") or {}).get("scorers") or ""), m.get("goals"), "h")
    a_mins = _extract_minutes(str((m.get("away") or {}).get("scorers") or ""), m.get("goals"), "a")

    def _series(tot_xg: float, gmins: list[int], offset: int) -> list[tuple[int, float, bool]]:
        gcnt: dict[int, int] = {}
        for mn in gmins:
            gcnt[mn] = gcnt.get(mn, 0) + 1
        pts_t = sorted(set(gmins + [min(91, t + offset) for t in (11, 27, 36, 48, 62, 74, 86)]))
        weights = [(t, 0.42 * gcnt.get(t, 0) + 0.14, t in gcnt) for t in pts_t]
        wsum = sum(w for _, w, _ in weights) or 1.0
        cur = 0.0
        out = [(0, 0.0, False)]
        for t, w, is_g in weights:
            cur = min(tot_xg, cur + (w / wsum) * tot_xg)
            out.append((t, cur, is_g))
        out.append((93, tot_xg, False))
        return out

    s_h = _series(h_xg, h_mins, 0)
    s_a = _series(a_xg, a_mins, 3)
    ymax = 1.16 * max(h_xg, a_xg, 1.8)
    H = 122 if compact else 140
    top = 20.0
    ph = H - top - 24.0
    vx = lambda mn: 38.0 + (min(93, mn) / 93.0) * 748.0
    vy = lambda val: top + ph - (val / ymax) * ph

    def _step_path(ser: list[tuple[int, float, bool]]) -> str:
        d = f"M{vx(ser[0][0]):.1f} {vy(ser[0][1]):.1f}"
        for i in range(1, len(ser)):
            x = vx(ser[i][0])
            y_prev = vy(ser[i - 1][1])
            y_cur = vy(ser[i][1])
            d += f" L{x:.1f} {y_prev:.1f} L{x:.1f} {y_cur:.1f}"
        return d

    ph_d = _step_path(s_h)
    pa_d = _step_path(s_a)
    fh_d = f"{ph_d} L{vx(93):.1f} {top+ph:.1f} L38.0 {top+ph:.1f} Z"
    fa_d = f"{pa_d} L{vx(93):.1f} {top+ph:.1f} L38.0 {top+ph:.1f} Z"

    hc, ac = resolve_distinct_team_colors(str((m.get("home") or {}).get("color") or "#E62E45"), str((m.get("away") or {}).get("color") or "#38BDF8"))
    hcode = esc(str((m.get("home") or {}).get("code") or "HOM"))
    acode = esc(str((m.get("away") or {}).get("code") or "AWY"))

    def _pins(ser: list[tuple[int, float, bool]], col: str, txt_col: str) -> str:
        return "".join(
            f'<g><circle cx="{vx(t):.1f}" cy="{vy(v):.1f}" r="9" fill="{col}" fill-opacity=".28"/>'
            f'<circle cx="{vx(t):.1f}" cy="{vy(v):.1f}" r="5.2" fill="{col}" stroke="#fff" stroke-width="2"/>'
            f'<text x="{vx(t):.1f}" y="{max(13.0, vy(v)-11):.1f}" text-anchor="middle" fill="{txt_col}" font-family="Vazirmatn" font-weight="900" font-size="11.5">{_fa(t)}\'</text></g>'
            for t, v, is_g in ser if is_g
        )

    yh_end, ya_end = vy(h_xg), vy(a_xg)
    sep = (-8 if yh_end <= ya_end else 8) if abs(yh_end - ya_end) < 18 else 0
    return (
        f'<div style="border-radius:16px;background:rgba(10,19,41,.34);backdrop-filter:blur(6px);border:1px solid rgba(255,255,255,.15);padding:8px 14px;overflow:hidden">'
        f'<div class="fbw fm" style="font-size:11px;font-weight:800;color:#94A3B8;margin-bottom:2px" dir="ltr">'
        f'<span style="letter-spacing:.1em;color:#E2E8F0">CUMULATIVE xG RACE (0\' — 90\')</span>'
        f'<div class="fi" style="gap:12px">'
        f'<span class="fi" style="gap:6px"><span style="width:9px;height:9px;border-radius:50%;background:{hc}"></span><span style="color:{_bright(hc)}">{hcode} {h_xg:.2f}</span></span>'
        f'<span class="fi" style="gap:6px"><span style="width:9px;height:9px;border-radius:50%;background:{ac}"></span><span style="color:{_bright(ac)}">{acode} {a_xg:.2f}</span></span>'
        f'</div></div>'
        f'<svg style="width:100%;height:auto;display:block" viewBox="0 0 880 {H}" fill="none" dir="ltr">'
        f'<defs><linearGradient id="stepH" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{hc}" stop-opacity=".38"/><stop offset="1" stop-color="{hc}" stop-opacity=".02"/></linearGradient>'
        f'<linearGradient id="stepA" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{ac}" stop-opacity=".32"/><stop offset="1" stop-color="{ac}" stop-opacity=".02"/></linearGradient></defs>'
        f'<g stroke="#ffffff14" stroke-dasharray="4 4"><line x1="38" y1="20" x2="786" y2="20"/><line x1="38" y1="{top+ph/2:.1f}" x2="786" y2="{top+ph/2:.1f}"/><line x1="412" y1="20" x2="412" y2="{top+ph:.1f}" stroke="#ffffff26"/></g>'
        f'<line x1="38" y1="{top+ph:.1f}" x2="786" y2="{top+ph:.1f}" stroke="#ffffff30"/>'
        f'<text x="30" y="24" text-anchor="end" fill="#64748B" font-family="JetBrains Mono" font-size="10.5" font-weight="700">{ymax:.1f}</text>'
        f'<text x="30" y="{top+ph/2+4:.1f}" text-anchor="end" fill="#64748B" font-family="JetBrains Mono" font-size="10.5" font-weight="700">{ymax/2:.1f}</text>'
        f'<text x="30" y="{top+ph+3:.1f}" text-anchor="end" fill="#64748B" font-family="JetBrains Mono" font-size="10.5" font-weight="700">0</text>'
        f'<text x="38" y="{H-5}" text-anchor="middle" fill="#94A3B8" font-family="JetBrains Mono" font-size="11" font-weight="700">0\'</text>'
        f'<text x="412" y="{H-5}" text-anchor="middle" fill="#E2E8F0" font-family="JetBrains Mono" font-size="11" font-weight="800">HT 45\'</text>'
        f'<text x="786" y="{H-5}" text-anchor="middle" fill="#94A3B8" font-family="JetBrains Mono" font-size="11" font-weight="700">90\'+</text>'
        f'<path d="{fa_d}" fill="url(#stepA)"/><path d="{fh_d}" fill="url(#stepH)"/>'
        f'<path d="{pa_d}" stroke="{ac}" stroke-width="2.8" fill="none" stroke-linejoin="round"/>'
        f'<path d="{ph_d}" stroke="{hc}" stroke-width="3.2" fill="none" stroke-linejoin="round"/>'
        f'<g><rect x="798" y="{yh_end+sep-10:.1f}" width="66" height="20" rx="6" fill="#070E20" stroke="{hc}" stroke-opacity=".75" stroke-width="1.2"/><text x="831" y="{yh_end+sep+4:.1f}" text-anchor="middle" fill="{_bright(hc)}" font-family="JetBrains Mono" font-weight="800" font-size="13.5">{h_xg:.2f}</text></g>'
        f'<g><rect x="798" y="{ya_end-sep-10:.1f}" width="66" height="20" rx="6" fill="#070E20" stroke="{ac}" stroke-opacity=".75" stroke-width="1.2"/><text x="831" y="{ya_end-sep+4:.1f}" text-anchor="middle" fill="{_bright(ac)}" font-family="JetBrains Mono" font-weight="800" font-size="13.5">{a_xg:.2f}</text></g>'
        f'{_pins(s_a, ac, _bright(ac))}{_pins(s_h, hc, "#FFFFFF")}</svg></div>'
    )


def _compute_stats(matches: list[dict[str, Any]]) -> dict[str, Any]:
    tot_g = 0
    tot_xg = 0.0
    has_xg = False
    bins = [0, 0, 0, 0, 0, 0]
    heist_m = matches[0] if matches else None
    heist_score = -99.0
    thriller_m = matches[0] if matches else None
    thriller_score = -1.0

    for m in matches:
        h = m.get("home") or {}
        a = m.get("away") or {}
        hs, as_ = int(h.get("score") or 0), int(a.get("score") or 0)
        tot_g += hs + as_
        hxg, axg = h.get("xg"), a.get("xg")
        if hxg is not None and axg is not None:
            has_xg = True
            hxg, axg = float(hxg), float(axg)
            tot_xg += hxg + axg
            if hxg + axg > thriller_score:
                thriller_score = hxg + axg
                thriller_m = m
            gd, xd = hs - as_, hxg - axg
            sc = (abs(xd) + 0.2 * abs(gd)) if (gd * xd < 0) else -0.1 * abs(gd - xd)
            if sc > heist_score:
                heist_score = sc
                heist_m = m
        elif hs + as_ > thriller_score:
            thriller_score = float(hs + as_)
            thriller_m = m
        for mn in _extract_minutes(str(h.get("scorers") or ""), m.get("goals"), "h") + _extract_minutes(str(a.get("scorers") or ""), m.get("goals"), "a"):
            bins[min(5, max(0, (mn - 1) // 15))] += 1

    eff_pct = round((tot_g / tot_xg) * 100) if (has_xg and tot_xg > 0.01) else None
    return {
        "totalGoals": tot_g,
        "totalXg": round(tot_xg, 2) if has_xg else None,
        "effPct": eff_pct,
        "effDelta": (tot_g - tot_xg) if has_xg else 0.0,
        "bins": bins,
        "heistMatch": heist_m,
        "thrillerMatch": thriller_m,
    }


def _header_gauge(st: dict[str, Any]) -> str:
    tot_g = st["totalGoals"]
    tot_xg = st["totalXg"]
    eff = st["effPct"]
    if eff is not None and tot_xg is not None:
        frac = min(1.0, max(0.0, eff / 200.0))
        circ = 2.0 * math.pi * 24.0
        dash = frac * circ
        col = "#34D399" if st["effDelta"] >= 0 else "#FF7B8C"
        ring_val = f"{_fa(eff)}٪"
        ring_sub = "EFF"
        xg_line = f'<span class="fm" style="font-size:11.5px;font-weight:800;color:{col}" dir="ltr">{_fa(f"{tot_xg:.1f}")} xG</span>'
    else:
        circ = 2.0 * math.pi * 24.0
        dash = circ * 0.72
        col = "#38BDF8"
        ring_val = f"{_fa(tot_g)}"
        ring_sub = "GOALS"
        xg_line = '<span class="fm" style="font-size:11px;font-weight:800;color:#94A3B8" dir="ltr">— xG</span>'

    return (
        f'<div class="hdr-gauge fi" style="gap:10px;padding:6px 12px;border-radius:16px;background:rgba(7,14,32,.9);border:1px solid rgba(255,255,255,.15)">'
        f'<div class="fc" style="position:relative;width:54px;height:54px;flex-shrink:0" dir="ltr">'
        f'<svg width="54" height="54" viewBox="0 0 60 60" fill="none">'
        f'<circle cx="30" cy="30" r="24" stroke="#ffffff18" stroke-width="5"/>'
        f'<circle cx="30" cy="30" r="24" stroke="{col}" stroke-width="5" stroke-linecap="round" stroke-dasharray="{dash:.1f} {circ:.1f}" transform="rotate(-90 30 30)"/></svg>'
        f'<div class="fcol" style="position:absolute;inset:0;align-items:center;justify-content:center">'
        f'<span style="font-size:13.5px;font-weight:900;line-height:1;color:#fff">{ring_val}</span>'
        f'<span class="fm" style="font-size:8px;font-weight:700;color:#94A3B8;margin-top:2px">{ring_sub}</span></div></div>'
        f'<div class="fcol" style="text-align:right;line-height:1.15">'
        f'<span style="font-size:11.5px;font-weight:800;color:#94A3B8">زهر گلزنی روز</span>'
        f'<span style="font-size:17px;font-weight:900;color:#fff;margin-top:2px">{_fa(tot_g)} <span style="font-size:11.5px;font-weight:700;color:#94A3B8">گل</span></span>'
        f'{xg_line}</div></div>'
    )


def _featured_hero(m: dict[str, Any], theme: str, compact: bool) -> str:
    h, a = m.get("home") or {}, m.get("away") or {}
    hc, ac = resolve_distinct_team_colors(str(h.get("color") or "#E62E45"), str(a.get("color") or "#38BDF8"))
    hs, as_ = int(h.get("score") or 0), int(a.get("score") or 0)
    hxg, axg = h.get("xg"), a.get("xg")
    v_cls, v_lbl, v_ico, _ = _verdict(m)
    acc = _accent(theme)
    c_sz = 80 if compact else 92
    name_fs = 34 if compact else 38
    sc_fs = 56 if compact else 64
    h_sc = _format_scorers(h, m.get("goals"), "h")
    a_sc = _format_scorers(a, m.get("goals"), "a")
    ht_raw = m.get("ht") or (f"{h.get('ht')}-{a.get('ht')}" if h.get("ht") is not None and a.get("ht") is not None else None)
    ht_html = f'<span style="font-size:12.5px;font-weight:700;color:#94A3B8;margin-top:4px">نیمه اول: {_fa(ht_raw)}</span>' if ht_raw else ""
    hxg_html = f'<div class="fi" style="gap:6px;margin-top:4px"><span style="width:9px;height:9px;border-radius:50%;background:{hc}"></span><span class="fm" style="font-size:21px;font-weight:800;color:{_bright(hc)}">{_fa(f"{float(hxg):.2f}")} xG</span></div>' if hxg is not None else ""
    axg_html = f'<div class="fi" style="justify-content:flex-end;gap:6px;margin-top:4px"><span class="fm" style="font-size:21px;font-weight:800;color:{_bright(ac)}">{_fa(f"{float(axg):.2f}")} xG</span><span style="width:9px;height:9px;border-radius:50%;background:{ac}"></span></div>' if axg is not None else ""
    chart_html = _step_xg_chart(m, compact)
    scorers_html = (
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;padding-top:6px;border-top:1px solid rgba(255,255,255,.1);font-size:17.5px;font-weight:800">'
        f'<div style="text-align:right;color:#F1F5F9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{"⚽ " + esc(h_sc) if h_sc else "<span style=color:#64748B>—</span>"}</div>'
        f'<div style="text-align:left;color:#F1F5F9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(a_sc) + " ⚽" if a_sc else "<span style=color:#64748B>—</span>"}</div></div>'
        if (h_sc or a_sc) else ""
    )

    return (
        f'<div class="xe" style="padding:16px 22px;flex-shrink:0;border-color:{acc}90;background:linear-gradient(155deg,#13254df6,#060c1dfa)">'
        f'<div style="position:absolute;inset:0;pointer-events:none;background:linear-gradient(110deg,{ac}2e 0%,transparent 43%,transparent 57%,{hc}32 100%)"></div>'
        f'<div style="position:absolute;right:-8px;top:-16px;font-size:165px;font-weight:900;line-height:1;opacity:.06;color:{hc};pointer-events:none">{_fa(hs)}</div>'
        f'<div style="position:absolute;left:-8px;top:-16px;font-size:165px;font-weight:900;line-height:1;opacity:.06;color:{ac};pointer-events:none">{_fa(as_)}</div>'
        f'<div style="position:absolute;top:0;left:0;right:0;height:4.5px;background:linear-gradient(270deg,{hc} 0%,{hc} {max(14, min(86, round(float(hxg)/(float(hxg)+float(axg))*100))) if (hxg is not None and axg is not None and (float(hxg)+float(axg))>0.01) else 50}%,{ac} {max(14, min(86, round(float(hxg)/(float(hxg)+float(axg))*100))) if (hxg is not None and axg is not None and (float(hxg)+float(axg))>0.01) else 50}%,{ac} 100%)"></div>'
        f'<div class="fcol" style="position:relative;z-index:2;gap:10px">'
        f'<div class="fbw" style="gap:8px"><div class="fi" style="gap:8px;min-width:0">'
        f'<span style="padding:3px 12px;border-radius:99px;background:#E62E45;color:#fff;font-size:13px;font-weight:900;box-shadow:0 6px 18px #e62e4577;flex-shrink:0">★ نبرد شاخص روز</span>'
        f'<span style="font-size:17.5px;font-weight:800;color:#E2E8F0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(m.get("tag") or m.get("comp") or "")}</span></div>'
        f'<div class="fi" style="gap:8px;flex-shrink:0"><span class="vb-badge {v_cls}" style="padding:4px 11px;font-size:13px"><span>{v_ico}</span><span>{v_lbl}</span></span>'
        f'<span class="fm" style="padding:3px 9px;border-radius:8px;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.15);font-size:13px;font-weight:800;color:#fff">{esc(m.get("status") or "FT")}</span></div></div>'
        f'<div style="display:grid;grid-template-columns:repeat(11,1fr);align-items:center;gap:12px">'
        f'<div class="fi" style="grid-column:span 4;gap:14px;min-width:0;opacity:{"0.75" if as_>hs else "1"}">'
        f'<div class="fc" style="position:relative;flex-shrink:0"><div style="position:absolute;inset:-7px;border-radius:50%;border:1px dashed {hc};opacity:.42"></div>{_crest_svg(h, "hero_h", c_sz)}</div>'
        f'<div style="min-width:0"><div style="font-size:{name_fs}px;font-weight:900;color:#fff;line-height:1.15;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(h.get("name", ""))}</div>{hxg_html}</div></div>'
        f'<div class="fcol" style="grid-column:span 3;align-items:center;justify-content:center">'
        f'<div class="scb-hi fc" style="border-radius:22px;padding:7px 20px;gap:16px;min-width:186px">'
        f'<span style="font-size:{sc_fs}px;font-weight:900;line-height:1;color:{"#fff" if hs>=as_ else "#CBD5E1"}">{_fa(hs)}</span>'
        f'<span style="font-size:26px;font-weight:900;color:#E62E45;line-height:1">—</span>'
        f'<span style="font-size:{sc_fs}px;font-weight:900;line-height:1;color:{"#fff" if as_>=hs else "#CBD5E1"}">{_fa(as_)}</span></div>{ht_html}</div>'
        f'<div class="fi" style="grid-column:span 4;justify-content:flex-end;text-align:left;gap:14px;min-width:0;opacity:{"0.75" if hs>as_ else "1"}">'
        f'<div style="min-width:0"><div style="font-size:{name_fs}px;font-weight:900;color:#fff;line-height:1.15;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(a.get("name", ""))}</div>{axg_html}</div>'
        f'<div class="fc" style="position:relative;flex-shrink:0"><div style="position:absolute;inset:-7px;border-radius:50%;border:1px dashed {ac};opacity:.42"></div>{_crest_svg(a, "hero_a", c_sz)}</div></div></div>'
        f'{chart_html}{scorers_html}</div></div>'
    )


def _league_divider(league_name: str, accent_col: str, col_span: bool) -> str:
    cs = "grid-column:span 2;" if col_span else ""
    return (
        f'<div class="fi" style="{cs}gap:10px;padding:2px 4px;flex-shrink:0">'
        f'<div class="fi" style="gap:7px;padding:4px 12px;border-radius:99px;background:rgba(9,19,43,.95);border:1px solid rgba(255,255,255,.15);border-right:3.5px solid {accent_col};flex-shrink:0">'
        f'<span style="width:7px;height:7px;border-radius:50%;background:{accent_col};box-shadow:0 0 8px {accent_col}"></span>'
        f'<span style="font-size:13px;font-weight:900;color:#fff;line-height:1">{esc(league_name)}</span></div>'
        f'<div style="flex:1;height:1px;background:linear-gradient(90deg,transparent,{accent_col}66,#ffffff1f)"></div></div>'
    )


def _bento_card(m: dict[str, Any], idx: int, tall: bool) -> str:
    h, a = m.get("home") or {}, m.get("away") or {}
    hc, ac = resolve_distinct_team_colors(str(h.get("color") or "#E62E45"), str(a.get("color") or "#38BDF8"))
    hs, as_ = int(h.get("score") or 0), int(a.get("score") or 0)
    hxg, axg = h.get("xg"), a.get("xg")
    v_cls, v_lbl, v_ico, is_shock = _verdict(m)
    win_col = hc if hs > as_ else (ac if as_ > hs else "#64748B")
    c_sz = 58 if tall else 52
    sc_fs = 42 if tall else 36
    ht_raw = m.get("ht") or (f"{h.get('ht')}-{a.get('ht')}" if h.get("ht") is not None and a.get("ht") is not None else None)
    ht_badge = f'<span class="fm" style="font-size:12px;font-weight:800;color:#94A3B8">HT {_fa(ht_raw)}</span>' if ht_raw else '<span class="fm" style="font-size:11.5px;font-weight:800;color:#64748B">FULL-TIME</span>'
    top_bar = (
        '<div class="_warnstripe" style="position:absolute;top:0;left:0;right:0;height:5px;border-bottom:1px solid rgba(230,46,69,.6)"></div>'
        if is_shock else
        f'<div style="position:absolute;top:0;left:0;right:0;height:4px;background:linear-gradient(270deg,{hc} 0%,{hc} {max(14, min(86, round(float(hxg)/(float(hxg)+float(axg))*100))) if (hxg is not None and axg is not None and (float(hxg)+float(axg))>0.01) else 50}%,{ac} {max(14, min(86, round(float(hxg)/(float(hxg)+float(axg))*100))) if (hxg is not None and axg is not None and (float(hxg)+float(axg))>0.01) else 50}%,{ac} 100%)"></div>'
    )
    hxg_s = f'<span class="fm" style="font-size:13px;font-weight:800;color:{_bright(hc)}">{_fa(f"{float(hxg):.2f}")} xG</span>' if hxg is not None else ""
    axg_s = f'<span class="fm" style="font-size:13px;font-weight:800;color:{_bright(ac)}">{_fa(f"{float(axg):.2f}")} xG</span>' if axg is not None else ""
    xg_bar = ""
    if hxg is not None and axg is not None:
        mx = max(float(hxg), float(axg), 0.1)
        xg_bar = (
            f'<div style="position:relative;display:grid;grid-template-columns:1fr 1fr;gap:4px;width:100%;align-items:center">'
            f'<div class="xmt hs" style="height:7px"><div class="xmf" style="width:{float(hxg)/mx*100:.1f}%;background:{hc}"></div></div>'
            f'<div class="xmt as" style="height:7px"><div class="xmf" style="width:{float(axg)/mx*100:.1f}%;background:{ac}"></div></div>'
            f'<span style="position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:2px;height:11px;background:rgba(255,255,255,.8);border-radius:99px"></span></div>'
        )
    h_sc = _format_scorers(h, m.get("goals"), "h")
    a_sc = _format_scorers(a, m.get("goals"), "a")
    sc_row = (
        f'<div class="fbw" style="gap:8px;font-size:14.5px;font-weight:700;color:#CBD5E1">'
        f'<span style="text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{"⚽ " + esc(h_sc) if h_sc else "—"}</span>'
        f'<span style="text-align:left;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(a_sc) + " ⚽" if a_sc else "—"}</span></div>'
    )
    aura_pos = "92% 18%" if hs > as_ else ("8% 18%" if as_ > hs else "50% 10%")
    return (
        f'<div class="bc {"bc-shock" if is_shock else ""}" style="padding:14px;gap:8px;border-right:3px solid {hc}66;border-left:3px solid {ac}66">'
        f'<div style="position:absolute;inset:0;pointer-events:none;background:radial-gradient(circle at {aura_pos},{"#e62e4538" if is_shock else win_col+"2e"},transparent 62%)"></div>'
        f'{top_bar}'
        f'<div class="fbw" style="position:relative;z-index:2;gap:8px">'
        f'<span class="vb-badge {v_cls}" style="padding:3px 10px;font-size:12px"><span>{v_ico}</span><span>{"شوک آماری روز" if is_shock else v_lbl}</span></span>{ht_badge}</div>'
        f'<div style="position:relative;z-index:2;display:grid;grid-template-columns:repeat(11,1fr);align-items:center;gap:6px">'
        f'<div class="fcol" style="grid-column:span 4;align-items:center;text-align:center;gap:4px;min-width:0;opacity:{"0.72" if as_>hs else "1"}">'
        f'{_crest_svg(h, f"bc{idx}h", c_sz)}'
        f'<div style="font-size:21px;font-weight:900;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;width:100%">{esc(h.get("name", ""))}</div>{hxg_s}</div>'
        f'<div class="fcol" style="grid-column:span 3;align-items:center;justify-content:center">'
        f'<div class="scb fc" style="border-radius:15px;padding:6px 10px;gap:9px;width:100%">'
        f'<span style="font-size:{sc_fs}px;font-weight:900;line-height:1;color:{"#fff" if hs>=as_ else "#CBD5E1"}">{_fa(hs)}</span>'
        f'<span style="font-size:19px;font-weight:900;color:#E62E45">—</span>'
        f'<span style="font-size:{sc_fs}px;font-weight:900;line-height:1;color:{"#fff" if as_>=hs else "#CBD5E1"}">{_fa(as_)}</span></div></div>'
        f'<div class="fcol" style="grid-column:span 4;align-items:center;text-align:center;gap:4px;min-width:0;opacity:{"0.72" if hs>as_ else "1"}">'
        f'{_crest_svg(a, f"bc{idx}a", c_sz)}'
        f'<div style="font-size:21px;font-weight:900;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;width:100%">{esc(a.get("name", ""))}</div>{axg_s}</div></div>'
        f'<div class="fcol" style="position:relative;z-index:2;gap:5px;padding-top:6px;border-top:1px solid rgba(255,255,255,.1)">'
        f'{xg_bar}{_goal_timeline_svg(m)}{sc_row}</div></div>'
    )


def _scoreboard_rows(matches: list[dict[str, Any]], comp_fallback: str, theme: str, compact: bool) -> str:
    acc = _accent(theme)
    parts = [_league_divider(comp_fallback, acc, False)]
    for idx, m in enumerate(matches[:6]):
        h, a = m.get("home") or {}, m.get("away") or {}
        hc, ac = resolve_distinct_team_colors(str(h.get("color") or "#E62E45"), str(a.get("color") or "#38BDF8"))
        hs, as_ = int(h.get("score") or 0), int(a.get("score") or 0)
        hxg, axg = h.get("xg"), a.get("xg")
        v_cls, v_lbl, v_ico, _ = _verdict(m)
        h_sc = _format_scorers(h, m.get("goals"), "h")
        a_sc = _format_scorers(a, m.get("goals"), "a")
        hxg_r = f'<div class="fm" style="font-size:13.5px;font-weight:800;color:{_bright(hc)}">{_fa(f"{float(hxg):.2f}")} xG</div>' if hxg is not None else ""
        axg_r = f'<div class="fm" style="font-size:13.5px;font-weight:800;color:{_bright(ac)}">xG {_fa(f"{float(axg):.2f}")}</div>' if axg is not None else ""
        parts.append(
            f'<div class="mr fcol" style="flex:1;padding:{"9px 18px" if compact else "11px 20px"};justify-content:center;gap:6px;border-right:5px solid {hc if hs>=as_ else hc+"55"};border-left:5px solid {ac if as_>=hs else ac+"55"}">'
            f'<div style="position:relative;z-index:2;display:grid;grid-template-columns:repeat(11,1fr);align-items:center;gap:8px">'
            f'<div class="fi" style="grid-column:span 4;gap:10px;min-width:0">{_crest_svg(h, f"r{idx}h", 48 if compact else 56)}'
            f'<div style="min-width:0"><div style="font-size:{22 if compact else 25}px;font-weight:900;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(h.get("name",""))}</div>{hxg_r}</div></div>'
            f'<div class="fcol" style="grid-column:span 3;align-items:center;gap:4px">'
            f'<div class="scb fc" style="border-radius:15px;padding:4px 16px;gap:12px;min-width:134px">'
            f'<span style="font-size:{30 if compact else 35}px;font-weight:900;color:#fff">{_fa(hs)}</span>'
            f'<span style="font-size:18px;font-weight:900;color:#E62E45">—</span>'
            f'<span style="font-size:{30 if compact else 35}px;font-weight:900;color:#fff">{_fa(as_)}</span></div>'
            f'<div style="width:100%;max-width:200px">{_goal_timeline_svg(m)}</div></div>'
            f'<div class="fi" style="grid-column:span 4;justify-content:flex-end;text-align:left;gap:10px;min-width:0">'
            f'<div style="min-width:0"><div style="font-size:{22 if compact else 25}px;font-weight:900;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(a.get("name",""))}</div>{axg_r}</div>'
            f'{_crest_svg(a, f"r{idx}a", 48 if compact else 56)}</div></div>'
            f'<div style="display:grid;grid-template-columns:repeat(11,1fr);align-items:center;gap:8px;padding-top:4px;border-top:1px solid rgba(255,255,255,.1);font-size:13px;font-weight:700;color:#E2E8F0">'
            f'<div style="grid-column:span 4;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{"⚽ "+esc(h_sc) if h_sc else ""}</div>'
            f'<div class="fc" style="grid-column:span 3"><span class="vb-badge {v_cls}" style="padding:2px 9px;font-size:11.5px">{v_ico} {v_lbl}</span></div>'
            f'<div style="grid-column:span 4;text-align:left;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(a_sc)+" ⚽" if a_sc else ""}</div></div></div>'
        )
    return "".join(parts)


def _timing_pulse_card(bins: list[int]) -> str:
    labels = ["۰-۱۵'", "۱۵-۳۰'", "۳۰-۴۵'", "۴۵-۶۰'", "۶۰-۷۵'", "۷۵-۹۰+'"]
    mx = max(max(bins), 3)
    peak = max(bins)
    step = 892.0 / 6.0
    bars = []
    for idx, val in enumerate(bins):
        cx = 34.0 + step * idx + step / 2.0
        bh = max(8.0, (val / mx) * 96.0)
        y = 124.0 - bh
        is_pk = val == peak and val > 0
        bars.append(
            f'<g><rect x="{cx-33:.1f}" y="{y:.1f}" width="66" height="{bh:.1f}" rx="10" '
            f'fill="{"url(#pkBar)" if is_pk else "url(#nmBar)"}" stroke="{"#FF8A9A" if is_pk else "#38BDF8"}" stroke-opacity=".5"/>'
            f'<text x="{cx:.1f}" y="{y-8:.1f}" text-anchor="middle" fill="{"#FF8A9A" if is_pk else "#E2E8F0"}" font-family="Vazirmatn" font-weight="900" font-size="18">{_fa(val)}</text>'
            f'<text x="{cx:.1f}" y="146" text-anchor="middle" fill="#CBD5E1" font-family="Vazirmatn" font-weight="800" font-size="15">{labels[idx]}</text></g>'
        )
    return (
        f'<div class="xm" style="flex-shrink:0;padding:12px 20px">'
        f'<div class="fbw" style="padding-bottom:8px;margin-bottom:4px;border-bottom:1px solid rgba(255,255,255,.1)">'
        f'<div class="fi" style="gap:9px"><span style="width:7px;height:22px;border-radius:99px;background:#E62E45"></span>'
        f'<h3 style="font-size:19px;font-weight:900;color:#fff">نبض زمانی گل‌های روز (توزیع ۱۵ دقیقه‌ای)</h3></div>'
        f'<span class="fm" style="font-size:12.5px;font-weight:800;color:#94A3B8">GOAL TIMING PULSE</span></div>'
        f'<div dir="ltr"><svg style="width:100%;height:auto" viewBox="0 0 960 156" fill="none">'
        f'<defs><linearGradient id="pkBar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FF5E72"/><stop offset="1" stop-color="#E62E45" stop-opacity=".35"/></linearGradient>'
        f'<linearGradient id="nmBar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#38BDF8" stop-opacity=".85"/><stop offset="1" stop-color="#0284C7" stop-opacity=".2"/></linearGradient></defs>'
        f'<line x1="34" y1="124" x2="926" y2="124" stroke="#ffffff26"/>{"".join(bars)}</svg></div></div>'
    )


def _footer_dock(item: dict[str, Any], st: dict[str, Any]) -> str:
    motm = item.get("motm")
    if not isinstance(motm, dict) or not motm.get("name"):
        # Check if any match has motm
        for m in item.get("matches") or []:
            if isinstance(m.get("motm"), dict) and m["motm"].get("name"):
                motm = m["motm"]
                break
    bins = st["bins"]
    bmax = max(max(bins), 1)
    mini_bars = "".join(
        f'<div class="fcol" style="flex:1;align-items:center;justify-content:flex-end;height:100%">'
        + (
            f'<div style="width:100%;border-radius:5px 5px 0 0;height:{max(22, round(b/bmax*100))}%;background:{"#E62E45" if b==bmax else "#38BDF8"};opacity:{"1" if b==bmax else ".78"}"></div>'
            if b > 0 else ""
        )
        + '</div>'
        for b in bins
    )
    tot_xg_v = st["totalXg"]
    xg_txt = (f"{_fa(st['totalGoals'])}G / {_fa(f'{tot_xg_v:.1f}')} xG") if tot_xg_v is not None else f"{_fa(st['totalGoals'])} گل رسمی"
    ed_note = str(item.get("editorialNote") or f"ثبت {_fa(st['totalGoals'])} گل در مسابقات رسمی روز با رصد زنده XGPedia.")

    if isinstance(motm, dict) and motm.get("name"):
        motm_html = (
            f'<div class="fi" style="grid-column:span 5;border-radius:16px;background:rgba(9,19,42,.95);border:1px solid rgba(251,191,36,.35);padding:10px 14px;gap:11px;position:relative;overflow:hidden">'
            f'<div style="position:absolute;right:0;top:0;bottom:0;width:4px;background:#FBBF24"></div>'
            f'<div class="fc" style="position:relative;width:46px;height:50px;flex-shrink:0">'
            f'<svg width="46" height="50" viewBox="0 0 48 52" fill="none"><polygon points="24,2 45,14 45,38 24,50 3,38 3,14" fill="#F59E0B28" stroke="#FBBF24" stroke-width="2.2"/></svg>'
            f'<span style="position:absolute;font-size:16px;font-weight:900;color:#FDE68A">{_fa(motm.get("rating", "8.8"))}</span></div>'
            f'<div style="min-width:0"><div style="font-size:11.5px;font-weight:800;color:#FCD34D">⭐ ستاره روز • {esc(motm.get("team", ""))}</div>'
            f'<div style="font-size:23px;font-weight:900;color:#fff;line-height:1.15;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(motm.get("name", ""))}</div>'
            f'<div style="font-size:14.5px;font-weight:700;color:#CBD5E1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{_fa(motm.get("stat", ""))}</div></div></div>'
        )
        mid_span = 4
    else:
        motm_html = ""
        mid_span = 9

    return (
        f'<div style="display:grid;grid-template-columns:repeat(12,1fr);gap:11px;flex-shrink:0">'
        f'{motm_html}'
        f'<div class="fcol" style="grid-column:span {mid_span};border-radius:16px;background:rgba(9,19,42,.95);border:1px solid rgba(255,255,255,.14);padding:10px 14px;justify-content:center;gap:4px">'
        f'<div class="fbw" style="font-size:11.5px;font-weight:800;color:#94A3B8"><span>راندمان کل روز</span><span class="fm" style="color:#6EE7B7" dir="ltr">{xg_txt}</span></div>'
        f'<div style="font-size:17.5px;font-weight:800;color:#F1F5F9;line-height:1.35">{esc(ed_note)}</div></div>'
        f'<div class="fcol" style="grid-column:span 3;border-radius:16px;background:rgba(9,19,42,.95);border:1px solid rgba(255,255,255,.14);padding:10px 13px;justify-content:space-between">'
        f'<div class="fbw" style="font-size:11px;font-weight:800;color:#94A3B8"><span>نبض دقایق گل</span><span class="fm" style="color:#FF7B8C">0\'–90\'</span></div>'
        f'<div class="fi" style="align-items:flex-end;gap:5px;height:38px;margin-top:4px;border-bottom:1px solid rgba(255,255,255,.18)" dir="ltr">{mini_bars}</div><div class="fbw fm" style="font-size:10px;font-weight:800;color:#94A3B8;margin-top:3px" dir="ltr"><span>0</span><span>15</span><span>30</span><span>45</span><span>60</span><span>75</span><span>90</span></div></div></div>'
    )


def get_matchday_results_modules(item: dict[str, Any], slide: str = "slide1") -> tuple[list[dict[str, Any]], list[str]]:
    sl_def = next((s for s in MATCHDAY_RESULTS_SLIDES if s[0] == slide), MATCHDAY_RESULTS_SLIDES[0])
    active = set(sl_def[3])
    matches = item.get("matches") or []
    has_xg = any((m.get("home") or {}).get("xg") is not None and (m.get("away") or {}).get("xg") is not None for m in matches)
    mods: list[dict[str, Any]] = []
    missing: list[str] = []
    for mid, title, can_half in MATCHDAY_RESULTS_MODULE_DEFS:
        if not has_xg and mid in ("xg_divergence", "heist_card"):
            missing.append(title)
            continue
        mods.append({"id": mid, "title_fa": title, "enabled": mid in active, "can_half": can_half, "span": "full", "half": False})
    return mods, missing


def render_matchday_results_html(
    item: dict[str, Any],
    *,
    slide: str = "slide1",
    header_mode: str = "full",
    fmt: str = "4:5",
    theme: str = "classic",
    modules: list[dict[str, Any]] | None = None,
) -> str:
    w, h = MATCHDAY_RESULTS_FORMATS.get(fmt, (1080, 1350))
    is_story = fmt == "9:16"
    is_wide = fmt == "16:9"
    pad_top, pad_bot = (139, 171) if is_story else ((22, 16) if is_wide else (24, 20))

    matches = list(item.get("matches") or [])
    feat_idx = min(int(item.get("featuredIdx") or 0), max(0, len(matches) - 1))
    featured = matches[feat_idx] if matches else None
    other_matches = [m for idx, m in enumerate(matches) if idx != feat_idx]
    st = _compute_stats(matches)

    acc = _accent(theme)
    bg_col = "#061026" if theme == "ucl" else ("#0C1222" if theme == "gold" else "#0A1329")
    fh_col = str((featured.get("home") or {}).get("color") or "#E62E45") if featured else "#E62E45"
    fa_col = str((featured.get("away") or {}).get("color") or "#38BDF8") if featured else "#38BDF8"
    aura_bg = (
        f"radial-gradient(circle at 86% 24%,{fh_col}38,transparent 46%),"
        f"radial-gradient(circle at 14% 24%,{fa_col}34,transparent 46%),"
        f"radial-gradient(circle at 50% 72%,{acc}22,transparent 56%)"
    )

    # Exact header copy per user rules
    comp_txt = str(item.get("competition") or "لیگ برتر انگلیس")
    round_txt = str(item.get("round") or "تابلوی نتایج")
    day_txt = str(item.get("day") or item.get("dateFa") or "")
    if not day_txt or "بازی" in day_txt:
        from src.xgpedia.providers.matchday_results_free import gregorian_to_jalali_fa
        day_txt = gregorian_to_jalali_fa(datetime.now(timezone.utc))
    title_txt = str(item.get("title") or "نتایج بازی‌های روز")
    wm_txt = str(item.get("wmText") or item.get("watermark") or "MATCHDAY")
    league_en = str(item.get("leagueEn") or "XGPEDIA").upper()
    source = str(item.get("source") or "Premier League / Opta FPL")

    if modules is None:
        modules, _ = get_matchday_results_modules(item, slide)
    enabled = [m["id"] for m in modules if m.get("enabled")]

    body_parts: list[str] = []
    if "featured" in enabled and featured:
        body_parts.append(_featured_hero(featured, theme, not is_story))

    if "bento_grid" in enabled:
        if other_matches:
            # Group remaining matches (NEVER duplicating featured!)
            div_lg = str((other_matches[0].get("league") or other_matches[0].get("comp") or comp_txt))
            cards_html = _league_divider(div_lg, acc, True) + "".join(_bento_card(m, i, is_story) for i, m in enumerate(other_matches[:4]))
            body_parts.append(f'<div style="flex:1;display:grid;grid-template-columns:1fr 1fr;gap:11px;align-content:start;min-height:0">{cards_html}</div>')
        elif matches:
            # Single match in 24h: do NOT repeat it and do NOT add extra Goal Timing Pulse module
            pass

    if "scoreboard" in enabled and matches:
        body_parts.append(f'<div class="fcol" style="flex:1;justify-content:space-between;gap:9px;min-height:0">{_scoreboard_rows(matches, comp_txt, theme, not is_story)}</div>')

    if "timing_pulse" in enabled and "bento_grid" not in enabled:
        body_parts.append(_timing_pulse_card(st["bins"]))

    if "footer_dock" in enabled:
        body_parts.append(_footer_dock(item, st))

    logo_svg = _brand_logo_img(44)
    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<style>
{build_embedded_font_css()}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:{w}px;height:{h}px;overflow:hidden;font-family:'Vazirmatn',sans-serif;background:{bg_col};color:#F8FAFC;font-feature-settings:"tnum";font-variant-numeric:tabular-nums}}
.fm{{font-family:'JetBrains Mono','Space Grotesk',monospace}}.fd{{font-family:'Space Grotesk',sans-serif}}
.fi{{display:flex;align-items:center}}.fc{{display:flex;align-items:center;justify-content:center}}.fbw{{display:flex;align-items:center;justify-content:space-between}}.fcol{{display:flex;flex-direction:column}}
.card{{position:relative;width:{w}px;height:{h}px;padding:{pad_top}px 0 {pad_bot}px 0;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;background:{bg_col}}}
.aura{{position:absolute;inset:0;pointer-events:none;z-index:0;background:{aura_bg}}}
.dots{{position:absolute;inset:0;pointer-events:none;z-index:0;background-image:radial-gradient(#ffffff0f 1px,transparent 1px);background-size:18px 18px;opacity:.55}}
.scan{{position:absolute;inset:0;pointer-events:none;z-index:0;background:repeating-linear-gradient(to bottom,#ffffff04 0 1px,#0000 1px 4px)}}
.wm-bg{{position:absolute;top:52px;left:50%;transform:translateX(-50%);pointer-events:none;z-index:0;font-family:'Space Grotesk',sans-serif;font-weight:800;font-size:176px;line-height:1;letter-spacing:-.05em;-webkit-text-stroke:1.8px rgba(248,250,252,.12);color:transparent;white-space:nowrap}}
._warnstripe{{background:repeating-linear-gradient(-45deg,#e62e4533 0 8px,#e62e450a 8px 16px)}}
header{{position:relative;z-index:10;padding:12px 36px 8px;flex-shrink:0}}
.stage{{position:relative;z-index:10;flex:1;padding:8px 40px;display:flex;flex-direction:column;justify-content:space-between;gap:10px;min-height:0;overflow:hidden}}
footer{{position:relative;z-index:10;padding:10px 44px 10px;flex-shrink:0}}
.xm,.xe{{position:relative;border-radius:22px;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;box-shadow:0 20px 50px -14px #000000c4,inset 0 1px 0 #ffffff22}}
.xm{{background:linear-gradient(162deg,#111f40ed,#070e20fa);border:1.5px solid #f8fafc24}}
.xe{{background:linear-gradient(148deg,#152752f2,#070e20fc);border:1.5px solid #7fa6e847}}
.bc{{position:relative;border-radius:20px;background:linear-gradient(160deg,#111f40eb,#060d1ef9);border:1.5px solid #ffffff20;box-shadow:0 18px 42px -12px #000000c4,inset 0 1px 0 #ffffff1c;overflow:hidden;display:flex;flex-direction:column;justify-content:space-between}}
.bc-shock{{border-color:#e62e459e;box-shadow:0 18px 46px -10px #e62e4540}}
.mr{{position:relative;border-radius:18px;background:linear-gradient(162deg,#101e3de8,#070e1ff7);border:1.5px solid #ffffff1c;overflow:hidden}}
.scb{{position:relative;background:linear-gradient(180deg,#050b18 0%,#0b162e 100%);border:1.5px solid #ffffff2b;box-shadow:inset 0 4px 14px #000000b8}}
.scb-hi{{position:relative;background:linear-gradient(180deg,#0f1c3a 0%,#050a16 100%);border:2px solid #e62e45ba;box-shadow:inset 0 4px 18px #000000cc,0 0 42px -4px #e62e4575}}
.xmt{{height:7px;background:#ffffff14;overflow:hidden;display:flex;align-items:center}}.xmt.hs{{justify-content:flex-end;border-radius:0 99px 99px 0}}.xmt.as{{justify-content:flex-start;border-radius:99px 0 0 99px}}
.xmf{{height:100%}}.xmt.hs .xmf{{border-radius:0 99px 99px 0}}.xmt.as .xmf{{border-radius:99px 0 0 99px}}
.vb-badge{{display:inline-flex;align-items:center;gap:5px;border-radius:999px;font-weight:800;white-space:nowrap;line-height:1;border:1px solid transparent}}
.vb-deserved{{background:#10b98126;border-color:#34d39975;color:#34D399}}.vb-heist{{background:#e62e4538;border-color:#ff6b7fa6;color:#FF8596}}
.vb-clinical{{background:#f59e0b28;border-color:#fbbf2480;color:#FCD34D}}.vb-thriller{{background:#8b5cf62d;border-color:#a78bfa85;color:#C4B5FD}}
.vb-fair{{background:#38bdf826;border-color:#38bdf875;color:#7DD3FC}}.vb-cagey{{background:#64748b2d;border-color:#94a3b866;color:#CBD5E1}}
footer,footer .fbw,footer .fi{{flex-wrap:nowrap!important;white-space:nowrap!important;min-width:0!important}}
footer span,footer div{{white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;min-width:0!important}}
</style>
</head>
<body>
<div class="card">
  <div class="aura"></div>
  <div class="dots"></div>
  <div class="wm-bg" dir="ltr">{esc(wm_txt)}</div>
  <svg style="position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0" viewBox="0 0 {w} {h}" fill="none">
    <defs>
      <pattern id="tg" width="54" height="54" patternUnits="userSpaceOnUse"><path d="M54 0H0v54" stroke="#F8FAFC" stroke-opacity=".042"/></pattern>
      <radialGradient id="rf" cx="50%" cy="24%" r="48%"><stop offset="0" stop-color="#E62E45" stop-opacity=".28"/><stop offset=".52" stop-color="#E62E45" stop-opacity=".07"/><stop offset="1" stop-color="#E62E45" stop-opacity="0"/></radialGradient>
      <linearGradient id="beamL" x1="0" y1="0" x2=".45" y2=".55"><stop offset="0" stop-color="#38BDF8" stop-opacity=".22"/><stop offset="1" stop-color="#38BDF8" stop-opacity="0"/></linearGradient>
      <linearGradient id="beamR" x1="1" y1="0" x2=".55" y2=".55"><stop offset="0" stop-color="#E62E45" stop-opacity=".26"/><stop offset="1" stop-color="#E62E45" stop-opacity="0"/></linearGradient>
      <linearGradient id="topBeam" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#E62E45" stop-opacity="0"/><stop offset=".5" stop-color="#E62E45" stop-opacity=".95"/><stop offset="1" stop-color="#E62E45" stop-opacity="0"/></linearGradient>
    </defs>
    <rect width="100%" height="100%" fill="url(#tg)"/>
    <polygon points="0,0 380,0 640,680 0,460" fill="url(#beamL)"/>
    <polygon points="{w},0 {w-380},0 {w-640},680 {w},460" fill="url(#beamR)"/>
    <rect x="0" y="0" width="{w}" height="4" fill="url(#topBeam)"/>
    <rect x="12" y="12" width="{w-24}" height="{h-24}" rx="18" stroke="#F8FAFC" stroke-opacity=".11" stroke-width="1.5"/>
    <g stroke="#F8FAFC" stroke-opacity=".075" stroke-width="1.5"><line x1="{w/2:.0f}" y1="12" x2="{w/2:.0f}" y2="{h-12}" stroke-dasharray="8 8"/><circle cx="{w/2:.0f}" cy="275" r="155"/></g>
    <circle cx="{w/2:.0f}" cy="275" r="250" fill="url(#rf)"/>
    <circle cx="{w/2:.0f}" cy="275" r="220" stroke="#E62E45" stroke-opacity=".24" stroke-width="1.3" stroke-dasharray="4 6"/>
  </svg>
  <div class="scan"></div>
  {_mirror_corners_html(w, h)}
  <header class="fbw" style="gap:14px">
    <div class="fcol" style="align-items:flex-start;gap:7px;min-width:0">
      <div class="fi" style="gap:8px;flex-wrap:wrap">
        <div class="fi" style="padding:4px 14px;border-radius:999px;font-size:17.5px;font-weight:900;gap:7px;border:1px solid rgba(255,255,255,.22);background:rgba(21,35,71,.92);color:#F8FAFC">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#E62E45" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M8 21h8m-4-4v4m-5-17h10v5a5 5 0 01-10 0V4zM5 6H3v2a3 3 0 003 3h1m12-5h2v2a3 3 0 01-3 3h-1"/></svg>
          <span>{esc(comp_txt)}</span>
        </div>
        <span style="padding:4px 13px;border-radius:999px;font-size:16px;font-weight:800;border:1px solid rgba(230,46,69,.55);background:rgba(230,46,69,.2);color:#FF7B8C">{esc(_fa(round_txt))}</span>
        <span style="padding:4px 12px;border-radius:999px;font-size:15.5px;font-weight:700;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.14);color:#E2E8F0">{esc(_fa(day_txt))}</span>
      </div>
      <div class="fi" style="gap:10px;min-width:0">
        <span style="width:9px;height:36px;border-radius:99px;background:#E62E45;box-shadow:0 0 18px #E62E45;flex-shrink:0"></span>
        <h1 style="font-size:36px;font-weight:900;color:#fff;line-height:1.05;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(_fa(title_txt))}</h1>
      </div>
    </div>
    <div class="fi" style="gap:12px;flex-shrink:0">
      {_header_gauge(st)}
      <div class="fcol" style="align-items:flex-end;padding-right:12px;border-right:1px solid rgba(255,255,255,.14);flex-shrink:0" dir="ltr">
        {logo_svg}
        <span class="fm" style="font-size:10.5px;font-weight:800;letter-spacing:.22em;color:#94A3B8;margin-top:4px">MATCHDAY PULSE</span>
      </div>
    </div>
  </header>
  <main class="stage">{"".join(body_parts)}</main>
  <footer>
    <div style="border-top:1px solid rgba(255,255,255,.14);margin-bottom:8px"></div>
    <div class="fbw" style="gap:14px">
      <div class="fi" style="gap:9px;min-width:0"><span style="width:10px;height:10px;border-radius:50%;background:#E62E45;box-shadow:0 0 10px #E62E45;flex-shrink:0"></span><span dir="ltr" class="fm" style="font-size:15.5px;font-weight:800;letter-spacing:.14em;color:#F1F5F9">{esc(league_en)} • MATCHDAY RESULTS</span></div>
      <div class="fi fm" style="gap:10px;flex-shrink:0" dir="ltr"><span style="font-size:18px;font-weight:800;color:#fff">@XGPedia</span><span style="color:#64748B">|</span><span style="font-size:15px;font-weight:600;color:#CBD5E1">{esc(source)}</span></div>
    </div>
  </footer>
</div>
</body>
</html>"""
