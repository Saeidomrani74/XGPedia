"""تولیدکننده‌های SVG، نقشهٔ زمین و تایپوگرافی هنری کارت «در چنین روزی» (استخراج‌شده در v0.75.0)."""
from __future__ import annotations
import base64
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from src.xgpedia.config import ROOT as PROJECT_ROOT
from src.xgpedia.render.card_kit.helpers import (
    contrast_ink,
    ensure_dark_bg_contrast,
    esc,
    fa,
    luminance,
    resolve_visible_team_colors,
    team_crest_svg_or_img,
)
from src.xgpedia.render.cards import _brand_logo_data_uri
from src.xgpedia.render.studio_engine import FORMATS, build_embedded_font_css


def _build_pulse_svg(ev: dict[str, Any], hc: str, ac: str, accent: str, width: int = 880, height: int = 104) -> str:
    vals = [float(v) for v in (ev.get("pulse") or [])]
    if len(vals) < 2:
        return ""
    pad_x, pad_y = 24.0, 16.0
    pw, ph = width - pad_x * 2, height - pad_y * 2
    pts = [
        (pad_x + (i / (len(vals) - 1)) * pw, pad_y + ph - (max(0.0, min(100.0, v)) / 100.0) * ph)
        for i, v in enumerate(vals)
    ]
    d_parts = [f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"]
    for i in range(1, len(pts)):
        px, py = pts[i - 1]
        x, y = pts[i]
        cx = (px + x) / 2.0
        d_parts.append(f"C{cx:.1f} {py:.1f}, {cx:.1f} {y:.1f}, {x:.1f} {y:.1f}")
    d = " ".join(d_parts)
    area = f"{d} L{pts[-1][0]:.1f} {height - 4} L{pts[0][0]:.1f} {height - 4} Z"

    goals = ev.get("goals") or []
    max_min = max([95] + [int(g.get("min") or 0) for g in goals if isinstance(g, dict)])
    pins: list[str] = []
    for g in goals:
        if not isinstance(g, dict):
            continue
        gmin = int(g.get("min") or 0)
        gx = pad_x + (min(max_min, gmin) / max_min) * pw
        idx = min(len(pts) - 1, int(round((gmin / max_min) * (len(pts) - 1))))
        gy = pts[idx][1]
        col = hc if g.get("side") == "home" else ac
        is_key = bool(g.get("key"))
        halo = f'<circle cx="{gx:.1f}" cy="{gy:.1f}" r="12" fill="{col}" fill-opacity=".28"/>' if is_key else ""
        pins.append(
            f'<g>'
            f'<line x1="{gx:.1f}" y1="{gy:.1f}" x2="{gx:.1f}" y2="{height - 4}" '
            f'stroke="{col}" stroke-opacity=".48" stroke-dasharray="3 3" stroke-width="1.5"/>'
            f'{halo}'
            f'<circle cx="{gx:.1f}" cy="{gy:.1f}" r="{6 if is_key else 4.5}" fill="{col}" stroke="#FFFFFF" stroke-width="2"/>'
            f'</g>'
        )

    return (
        f'<svg class="otd-svg-full" viewBox="0 0 {width} {height}" fill="none" dir="ltr">'
        f'<defs><linearGradient id="pulseFill" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{accent}" stop-opacity=".42"/>'
        f'<stop offset="1" stop-color="{accent}" stop-opacity="0"/>'
        f'</linearGradient></defs>'
        f'<line x1="{pad_x}" y1="{height - 4}" x2="{width - pad_x}" y2="{height - 4}" stroke="rgba(255,255,255,.16)" stroke-width="1.5"/>'
        f'<line x1="{width / 2:.1f}" y1="8" x2="{width / 2:.1f}" y2="{height - 4}" stroke="rgba(255,255,255,.14)" stroke-dasharray="4 4" stroke-width="1.2"/>'
        f'<path d="{area}" fill="url(#pulseFill)"/>'
        f'<path d="{d}" stroke="{accent}" stroke-width="3.5" stroke-linecap="round" style="filter:drop-shadow(0 0 8px {accent})"/>'
        f'{"".join(pins)}'
        f'</svg>'
    )


def _map_pitch_xy(x: float, y: float) -> tuple[float, float]:
    """نگاشت خطی مختصات قدیم (844×292) به زمین واقعی فیفا ۱۰۵×۶۸ متر (840×544)."""
    nx = 24.0 + (float(x) - 20.0) * (840.0 / 844.0)
    ny = 22.0 + (float(y) - 14.0) * (544.0 / 292.0)
    return nx, ny


def _remap_svg_path_to_real_pitch(path_d: str) -> str:
    """تبدیل خودکار مسیرهای SVG (M/L/Q/C) از مختصات قدیم به نسبت واقعی ۱۰۵×۶۸ متر."""
    import re as _re
    tokens = _re.findall(r"[A-Za-z]|-?\d+(?:\.\d+)?", path_d or "")
    out: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.isalpha():
            out.append(tok)
            i += 1
        elif i + 1 < len(tokens) and not tokens[i + 1].isalpha():
            nx, ny = _map_pitch_xy(float(tok), float(tokens[i + 1]))
            out.append(f"{nx:.1f} {ny:.1f}")
            i += 2
        else:
            out.append(tok)
            i += 1
    return " ".join(out)


def _build_pitch_svg(ev: dict[str, Any], canvas_bg: str, max_h: int = 560) -> str:
    """رندر زمین فوتبال تاکتیکی با نسبت واقعی استاندارد فیفا (۱۰۵×۶۸ متر = 1.544:1)."""
    r = ev.get("replay")
    if not isinstance(r, dict):
        return ""
    r_col = ensure_dark_bg_contrast(str(r.get("color") or "#E62E45"), bg=canvas_bg, min_ratio=4.8)
    r_sec = ensure_dark_bg_contrast(str(r.get("secondary") or "#F59E0B"), bg=canvas_bg, min_ratio=4.8)

    passes_parts: list[str] = []
    for p in (r.get("passes") or []):
        x1, y1 = _map_pitch_xy(p["x1"], p["y1"])
        x2, y2 = _map_pitch_xy(p["x2"], p["y2"])
        passes_parts.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="#FDE047" stroke-width="{4.8 if p.get("type") == "through" else 3.4}" '
            f'stroke-dasharray="{"12 7" if p.get("type") == "through" else "5 6"}" '
            f'stroke-linecap="round" marker-end="url(#arrGold)"/>'
        )
    passes_svg = "".join(passes_parts)

    def_parts: list[str] = []
    for d in (r.get("defenders") or []):
        dx, dy = _map_pitch_xy(d["x"], d["y"])
        def_parts.append(
            f'<g><circle cx="{dx:.1f}" cy="{dy:.1f}" r="14" fill="#070D1D" stroke="{r_sec}" stroke-width="2.8"/>'
            f'<path d="M{dx - 5:.1f} {dy - 5:.1f}L{dx + 5:.1f} {dy + 5:.1f}'
            f'M{dx + 5:.1f} {dy - 5:.1f}L{dx - 5:.1f} {dy + 5:.1f}" stroke="{r_sec}" stroke-width="2.4" stroke-linecap="round"/></g>'
        )
    def_svg = "".join(def_parts)

    node_parts: list[str] = []
    for n in (r.get("nodes") or []):
        nx, ny = _map_pitch_xy(n["x"], n["y"])
        is_main = bool(n.get("main"))
        halo = (
            f'<circle cx="{nx:.1f}" cy="{ny:.1f}" r="32" fill="{r_col}" fill-opacity=".26"/>'
            f'<circle cx="{nx:.1f}" cy="{ny:.1f}" r="44" stroke="{r_col}" stroke-opacity=".35" stroke-dasharray="5 5" stroke-width="1.6"/>'
            if is_main else ""
        )
        lbl_x = max(84.0, min(816.0, nx))
        lbl_y = max(58.0, ny - 54.0)
        node_parts.append(
            f'<g>{halo}'
            f'<circle cx="{nx:.1f}" cy="{ny:.1f}" r="{20 if is_main else 16}" fill="{r_col if is_main else "#1E293B"}" stroke="#FFFFFF" stroke-width="2.8"/>'
            f'<text x="{nx:.1f}" y="{ny + 6:.1f}" text-anchor="middle" fill="#FFFFFF" font-family="Space Grotesk,sans-serif" font-weight="800" font-size="{17 if is_main else 14}">{esc(n.get("num", ""))}</text>'
            f'<rect x="{lbl_x - 76:.1f}" y="{lbl_y:.1f}" width="152" height="30" rx="9" fill="#050A18" fill-opacity=".94" stroke="rgba(255,255,255,.28)"/>'
            f'<text x="{lbl_x:.1f}" y="{lbl_y + 20.5:.1f}" text-anchor="middle" fill="#F8FAFC" font-family="Vazirmatn,sans-serif" font-weight="800" font-size="16">{esc(fa(n.get("name", "")))}</text>'
            f'</g>'
        )

    run_d = _remap_svg_path_to_real_pitch(r["run"]) if r.get("run") else ""
    run_path = (
        f'<path d="{esc(run_d)}" stroke="{r_col}" stroke-width="6.0" stroke-linecap="round" fill="none" '
        f'style="filter:drop-shadow(0 0 12px {r_col})"/>'
        if run_d else ""
    )
    shot = r.get("shot")
    shot_svg = ""
    if isinstance(shot, dict):
        sx1, sy1 = _map_pitch_xy(shot["x1"], shot["y1"])
        sx2, sy2 = _map_pitch_xy(shot["x2"], shot["y2"])
        shot_svg = (
            f'<line x1="{sx1:.1f}" y1="{sy1:.1f}" x2="{sx2:.1f}" y2="{sy2:.1f}" '
            f'stroke="#FFFFFF" stroke-width="5.0" stroke-linecap="round" marker-end="url(#arrShot)"/>'
        )

    # ابعاد زمین واقعی فیفا: 105m × 68m با مقیاس 8px/m => 840×544 داخل viewBox 900×588
    # محوطه جریمه: 16.5m×40.32m => 132×322 | محوطه ۶ قدم: 5.5m×18.32m => 44×146 | دایره مرکزی: r=9.15m => 73 | دروازه: 7.32m => 58
    return (
        f'<svg class="otd-svg-full" style="max-height:{max_h}px" viewBox="0 0 900 588" fill="none" dir="ltr">'
        f'<defs><linearGradient id="pGrad" x1="0" y1="0" x2="900" y2="588" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="rgba(11,22,48,.88)"/><stop offset="1" stop-color="rgba(5,10,24,.94)"/>'
        f'</linearGradient>'
        f'<marker id="arrGold" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M 0 1 L 10 5 L 0 9 z" fill="#FDE047"/></marker>'
        f'<marker id="arrShot" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M 0 1 L 10 5 L 0 9 z" fill="#FFFFFF"/></marker></defs>'
        f'<rect x="24" y="22" width="840" height="544" rx="16" fill="url(#pGrad)" stroke="rgba(248,250,252,.28)" stroke-width="2.2"/>'
        f'<g fill="#F8FAFC" fill-opacity=".03">'
        f'<rect x="108" y="24" width="84" height="540"/><rect x="276" y="24" width="84" height="540"/>'
        f'<rect x="444" y="24" width="84" height="540"/><rect x="612" y="24" width="84" height="540"/>'
        f'<rect x="780" y="24" width="84" height="540"/></g>'
        f'<g stroke="rgba(248,250,252,.24)" stroke-width="2.0">'
        f'<line x1="444" y1="22" x2="444" y2="566"/><circle cx="444" cy="294" r="73"/>'
        f'<circle cx="444" cy="294" r="4.5" fill="rgba(248,250,252,.45)"/>'
        f'<rect x="24" y="133" width="132" height="322"/><rect x="24" y="221" width="44" height="146"/>'
        f'<circle cx="112" cy="294" r="3.5" fill="rgba(248,250,252,.45)"/>'
        f'<path d="M156 236A73 73 0 0 1 156 352"/>'
        f'<rect x="732" y="133" width="132" height="322"/><rect x="820" y="221" width="44" height="146"/>'
        f'<circle cx="776" cy="294" r="3.5" fill="rgba(248,250,252,.45)"/>'
        f'<path d="M732 236A73 73 0 0 0 732 352"/>'
        f'<rect x="864" y="265" width="18" height="58" rx="3" fill="{r_col}" fill-opacity=".30" stroke="{r_col}" stroke-width="2.6"/>'
        f'</g>{passes_svg}{run_path}{shot_svg}{def_svg}{"".join(node_parts)}</svg>'
    )


def _brand_header_logo(accent: str) -> str:
    uri = _brand_logo_data_uri(mono=False)
    if uri:
        return (
            f'<div class="otd-brand" dir="ltr">'
            f'<img src="{uri}" alt="XGPedia" class="otd-brand-img">'
            f'</div>'
        )
    return (
        f'<div class="otd-brand" dir="ltr">'
        f'<div class="fd otd-brand-txt"><span style="color:{accent}">XG</span><span style="color:#F8FAFC">Pedia</span></div>'
        f'</div>'
    )


def _build_event_title_art(
    ev: dict[str, Any],
    accent: str,
    is_banner: bool,
    is_story: bool,
) -> str:
    """طراحی خلاقانه و اختصاصی تیتر مقاله با فونت درشت و المان‌های الهام‌گرفته از خود رویداد."""
    ev_id = str(ev.get("id") or "").lower()
    blob = " ".join([
        ev_id,
        str(ev.get("title") or ""),
        str(ev.get("competition") or ""),
        str(ev.get("kicker") or ""),
        str(ev.get("subtitle") or ""),
    ]).lower()

    title_txt = esc(fa(ev.get("title", "")))
    sub_txt = esc(fa(ev.get("subtitle", "")))
    h1_sz = 72 if is_banner else (94 if is_story else 86)
    sub_sz = 20 if is_banner else 23

    # انتخاب المان بصری و طیف رنگی اختصاصی بر اساس ماهیت اتفاق
    if "melbourne" in ev_id or "ملبورن" in blob:
        # حماسه ملبورن: الگوی تور دروازه پاره + جرقه صعود ۴ دقیقه‌ای (۷۱ تا ۷۵)
        grad = "linear-gradient(180deg,#FFFFFF 0%,#FDE68A 58%,#F59E0B 100%)"
        motif_svg = (
            '<svg class="otd-title-motif" viewBox="0 0 680 120" fill="none">'
            '<g stroke="rgba(255,255,255,.16)" stroke-width="1.3">'
            '<path d="M40 16L130 104M80 16L170 104M120 16L195 92M160 16L215 72"/>'
            '<path d="M130 16L40 104M170 16L80 104M200 22L120 104"/>'
            '<path d="M510 16L600 104M550 16L640 104M590 16L640 66"/>'
            '<path d="M640 16L550 104M600 16L510 104M560 16L485 90"/>'
            '</g>'
            '<path d="M210 60L258 44L246 64L290 54" stroke="#FDE047" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" opacity=".85"/>'
            '<path d="M470 60L422 44L434 64L390 54" stroke="#E62E45" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" opacity=".85"/>'
            '</svg>'
        )
        accent_ornament = (
            '<div class="otd-ornament-row">'
            '<span class="otd-orn-line"></span>'
            '<span class="otd-orn-pill" style="border-color:rgba(250,204,21,.55);color:#FDE047">⚡ ۷۱′ تا ۷۵′ | بلیت فرانسه ۹۸</span>'
            '<span class="otd-orn-line"></span>'
            '</div>'
        )
    elif "istanbul" in ev_id or "استانبول" in blob:
        # معجزه استانبول: ۵ ستاره جام اروپا و موج بازگشت ۶ دقیقه‌ای
        grad = "linear-gradient(180deg,#FFFFFF 0%,#FCA5A5 58%,#E62E45 100%)"
        motif_svg = (
            '<svg class="otd-title-motif" viewBox="0 0 680 120" fill="none">'
            '<g fill="#FDE047" fill-opacity=".28">'
            '<circle cx="110" cy="60" r="5"/><circle cx="138" cy="40" r="4"/><circle cx="138" cy="80" r="4"/>'
            '<circle cx="570" cy="60" r="5"/><circle cx="542" cy="40" r="4"/><circle cx="542" cy="80" r="4"/>'
            '</g>'
            '<path d="M60 88Q170 18 265 60" stroke="#38BDF8" stroke-opacity=".35" stroke-width="2.5" stroke-dasharray="6 6"/>'
            '<path d="M620 88Q510 18 415 60" stroke="#E62E45" stroke-opacity=".40" stroke-width="2.5" stroke-dasharray="6 6"/>'
            '</svg>'
        )
        accent_ornament = (
            '<div class="otd-ornament-row">'
            '<span class="otd-orn-line"></span>'
            '<span class="otd-orn-pill" style="border-color:rgba(56,189,248,.55);color:#7DD3FC">★★★★★ طوفان ۶ دقیقه‌ای آتاتورک</span>'
            '<span class="otd-orn-line"></span>'
            '</div>'
        )
    elif "azteca" in ev_id or "آزتکا" in blob or "مارادونا" in blob:
        # آزتکا ۸۶: مسیر مارپیچ دریبل ۶۰ متری + تاج خورشیدی آزتک + هاله شماره ۱۰
        grad = "linear-gradient(180deg,#FFFFFF 0%,#BAE6FD 56%,#38BDF8 100%)"
        motif_svg = (
            '<svg class="otd-title-motif" viewBox="0 0 680 120" fill="none">'
            '<path d="M40 88C110 24 165 102 245 48" stroke="#38BDF8" stroke-opacity=".42" stroke-width="3.4" stroke-linecap="round"/>'
            '<path d="M640 88C570 24 515 102 435 48" stroke="#FDE047" stroke-opacity=".42" stroke-width="3.4" stroke-linecap="round"/>'
            '<circle cx="340" cy="60" r="46" stroke="rgba(250,204,21,.22)" stroke-width="2" stroke-dasharray="5 6"/>'
            '</svg>'
        )
        accent_ornament = (
            '<div class="otd-ornament-row">'
            '<span class="otd-orn-line"></span>'
            '<span class="otd-orn-pill" style="border-color:rgba(56,189,248,.55);color:#BAE6FD">👑 شماره ۱۰ | ۶۰ متر تا جاودانگی</span>'
            '<span class="otd-orn-line"></span>'
            '</div>'
        )
    elif "remontada" in ev_id or "رمونتادا" in blob:
        # لا رمونتادا: امواج لرزه‌ای نوکمپ و تایمر انفجاری ۹۰+۵
        grad = "linear-gradient(180deg,#FFFFFF 0%,#FDA4AF 52%,#E62E45 100%)"
        motif_svg = (
            '<svg class="otd-title-motif" viewBox="0 0 680 120" fill="none">'
            '<polyline points="40,60 95,60 118,22 142,96 164,42 184,60 245,60" stroke="#E62E45" stroke-opacity=".45" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
            '<polyline points="640,60 585,60 562,22 538,96 516,42 496,60 435,60" stroke="#38BDF8" stroke-opacity=".45" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
            '</svg>'
        )
        accent_ornament = (
            '<div class="otd-ornament-row">'
            '<span class="otd-orn-line"></span>'
            '<span class="otd-orn-pill" style="border-color:rgba(230,46,69,.6);color:#FDA4AF">⏱ ۹۰+۵′ | زلزله در نوکمپ</span>'
            '<span class="otd-orn-line"></span>'
            '</div>'
        )
    elif any(k in blob for k in ("جام جهانی", "world cup", "قهرمان", "فینال", "final", "ucl", "لیگ قهرمانان")):
        # المان داینامیک جام و شاخه زیتون طلایی برای فینال‌ها و جام جهانی
        grad = "linear-gradient(180deg,#FFFFFF 0%,#FEF08A 62%,#EAB308 100%)"
        motif_svg = (
            '<svg class="otd-title-motif" viewBox="0 0 680 120" fill="none">'
            '<path d="M120 92Q75 60 120 28M146 84Q112 60 146 36" stroke="#FDE047" stroke-opacity=".34" stroke-width="2.6" stroke-linecap="round"/>'
            '<path d="M560 92Q605 60 560 28M534 84Q568 60 534 36" stroke="#FDE047" stroke-opacity=".34" stroke-width="2.6" stroke-linecap="round"/>'
            '</svg>'
        )
        accent_ornament = (
            '<div class="otd-ornament-row">'
            '<span class="otd-orn-line"></span>'
            f'<span class="otd-orn-pill" style="border-color:rgba(250,204,21,.5);color:#FDE047">🏆 برگ زرین تاریخ فوتبال</span>'
            '<span class="otd-orn-line"></span>'
            '</div>'
        )
    else:
        # المان داینامیک آرشیوی و خطوط حرکتی برای سایر وقایع تاریخی زنده
        grad = f"linear-gradient(180deg,#FFFFFF 0%,#E2E8F0 68%,{accent} 100%)"
        motif_svg = (
            '<svg class="otd-title-motif" viewBox="0 0 680 120" fill="none">'
            f'<line x1="65" y1="60" x2="210" y2="60" stroke="{accent}" stroke-opacity=".36" stroke-width="2.4" stroke-dasharray="8 6"/>'
            f'<line x1="470" y1="60" x2="615" y2="60" stroke="{accent}" stroke-opacity=".36" stroke-width="2.4" stroke-dasharray="8 6"/>'
            '</svg>'
        )
        accent_ornament = (
            '<div class="otd-ornament-row">'
            '<span class="otd-orn-line"></span>'
            '<span class="otd-orn-pill">✦ روایت مستند تاریخ فوتبال</span>'
            '<span class="otd-orn-line"></span>'
            '</div>'
        )

    return (
        f'<div class="otd-headline-wrap">'
        f'<div class="otd-h1-stage">'
        f'{motif_svg}'
        f'<h1 class="otd-h1-art" style="font-size:{h1_sz}px;background:{grad};-webkit-background-clip:text;background-clip:text;color:transparent">{title_txt}</h1>'
        f'</div>'
        f'{accent_ornament}'
        f'<p class="otd-sub" style="font-size:{sub_sz}px">{sub_txt}</p>'
        f'</div>'
    )
