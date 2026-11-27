"""رندرر ۱۰۰٪ آفلاین و ۱:۱ کارت اسلایدی «عدد روز» XGPedia (`Number of the Day Studio — 5-in-1`).

۵ اسلاید استاندارد مطابق دقیق `number of the day.html`:
  - `slide1`: وارونگی سوئیسی (Swiss Inversion / D&AD)
  - `slide2`: استادیوم ۳بعدی شبانه (Stadium Monument)
  - `slide3`: شکستن رکورد (انفجار شیشه — Shattered Glass)
  - `slide4`: گلیچ کروماتیک و شکاف (Chromatic Rift)
  - `slide5`: کلکسیونی فویل (سوئیسی-ژاپنی — Collector Foil)

استانداردهای دائمی XGPedia:
  - ۱۰۰٪ آفلاین (بدون CDN و بدون وابستگی به Canvas JS — پس‌زمینه‌ها با SVG وکتور دقیق رندر می‌شوند)
  - فریم چهارگوشه قرمز یکپارچه (`pad_top=24/22/139`, `pad_bot=20/16/171`)
  - فوتر تک‌خطی اجباری (`white-space:nowrap!important`)
  - کنتراست خوانا روی پس‌زمینه تیره (`ensure_dark_bg_contrast`)
"""
from __future__ import annotations

import math
from typing import Any

from src.xgpedia.render.card_kit.helpers import (
    with_sample_badge,
    _hex_to_rgb,
    ensure_dark_bg_contrast,
    esc,
    fa,
)
from src.xgpedia.render.cards import _brand_logo_data_uri
from src.xgpedia.render.studio_engine import build_embedded_font_css

NOD_FORMATS: dict[str, tuple[int, int]] = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}

NOD_SLIDES: list[tuple[str, str, str]] = [
    ("slide1", "وارونگی سوئیسی (D&AD)", "full"),
    ("slide2", "استادیوم ۳بعدی شبانه", "full"),
    ("slide3", "شکستن رکورد (شیشه)", "full"),
    ("slide4", "گلیچ کروماتیک و شکاف", "full"),
    ("slide5", "کلکسیونی فویل", "full"),
]

_SLIDE_TO_MODE: dict[str, tuple[str, str]] = {
    "slide1": ("gazette", "SWISS INVERSION"),
    "slide2": ("cathedral", "STADIUM MONUMENT"),
    "slide3": ("shatter", "SHATTERED GLASS"),
    "slide4": ("chromatic", "CHROMATIC RIFT"),
    "slide5": ("foil", "COLLECTOR FOIL"),
    "gazette": ("gazette", "SWISS INVERSION"),
    "cathedral": ("cathedral", "STADIUM MONUMENT"),
    "shatter": ("shatter", "SHATTERED GLASS"),
    "chromatic": ("chromatic", "CHROMATIC RIFT"),
    "foil": ("foil", "COLLECTOR FOIL"),
}

_MODULE_SPECS: list[tuple[str, str, bool]] = [
    ("kpis", "نوار ۳ شاخص آماری (KPI)", True),
    ("bench", "مقایسه با رکورد قبلی (Benchmark)", True),
    ("fx", "افکت پس‌زمینه و نورافکن", True),
]


def get_number_of_day_modules(item: dict[str, Any], slide: str = "slide1") -> tuple[list[dict[str, Any]], list[str]]:
    mods = [
        {"id": mid, "title_fa": title_fa, "enabled": def_on, "span": "full", "can_half": False}
        for mid, title_fa, def_on in _MODULE_SPECS
    ]
    return mods, []


def _brand_logo_img(height: int = 44) -> str:
    uri = _brand_logo_data_uri()
    if uri:
        return f'<img src="{uri}" alt="XGPedia" style="height:{height}px;width:auto;display:block;object-fit:contain;filter:drop-shadow(0 4px 12px rgba(0,0,0,.45))"/>'
    return (
        '<div style="display:flex;align-items:center;gap:10px" dir="ltr">'
        '<svg width="46" height="46" viewBox="0 0 48 48" fill="none">'
        '<path d="M24 2.5L42 10.2V23.4C42 34.6 34.3 43 24 45.6C13.7 43 6 34.6 6 23.4V10.2Z" fill="#152347" stroke="#E62E45" stroke-width="2.6"/>'
        '<path d="M16.5 16.5L31.5 31.5M31.5 16.5L16.5 31.5" stroke="#E62E45" stroke-width="3.2" stroke-linecap="round"/>'
        '</svg>'
        '<div style="font-weight:800;font-size:30px"><span style="color:#E62E45">XG</span><span style="color:#F8FAFC">Pedia</span></div>'
        '</div>'
    )


def _num_str(val: Any, font_style: str) -> str:
    return str(val) if font_style == "bebas" else fa(val)


def _font_metrics(font_style: str) -> tuple[str, int, str, float, float]:
    if font_style == "bebas":
        return "'Space Grotesk','JetBrains Mono',sans-serif", 800, "0.01em", 0.35, 1.15
    if font_style == "vazir":
        return "'Vazirmatn','Space Grotesk',sans-serif", 900, "-0.06em", 0.33, 1.0
    # default bold Persian display (Vazirmatn 900 fallback when Lalezar unavailable offline)
    return "'Lalezar','Vazirmatn',sans-serif", 900, "-0.02em", 0.32, 1.08


def _calc_font_size(raw: str, base: float, boost: float) -> int:
    mult_map = {1: 1.0, 2: 1.0, 3: 0.78, 4: 0.60}
    mult = mult_map.get(len(str(raw or "")), 0.48)
    return int(round(base * mult * boost))


def _fx_backdrop_svg(mode: str, w: int, h: int, ac: str, is16: bool, show_fx: bool) -> str:
    r, g, b = _hex_to_rgb(ac)
    cx = int(w * (0.31 if is16 else 0.50))
    cy = int(h * (0.50 if is16 else 0.42))
    op_glow = "0.18" if mode == "gazette" else "0.34"
    extra = ""
    if show_fx:
        if mode == "cathedral":
            h_y = int(h * (0.68 if is16 else 0.61))
            f_b = int(h * (0.96 if is16 else 0.84))
            f_y = int(h_y + (f_b - h_y) * 0.28)
            lx1, lx2 = (40, int(w * 0.62)) if is16 else (80, w - 80)
            lines = []
            for i in range(-8, 9):
                lines.append(f'<line x1="{cx + i * 68}" y1="{h_y}" x2="{cx + i * 240}" y2="{f_b + 80}" stroke="#F8FAFC" stroke-opacity=".14" stroke-width="1.5"/>')
            for j in range(7):
                t = (j / 6.0) ** 1.85
                yy = int(h_y + t * (f_b - h_y))
                lines.append(f'<line x1="0" y1="{yy}" x2="{w}" y2="{yy}" stroke="#F8FAFC" stroke-opacity="{0.06 + t * 0.16:.2f}" stroke-width="1.4"/>')
            extra = (
                f'<polygon points="{lx1},0 {cx - 240},{int(h * .85)} {cx + 400},{int(h * .85)}" fill="url(#bmW)"/>'
                f'<polygon points="{lx2},0 {cx - 400},{int(h * .85)} {cx + 240},{int(h * .85)}" fill="url(#bmA)"/>'
                f'<rect x="0" y="{h_y}" width="{w}" height="{f_b - h_y}" fill="url(#pgG)"/>'
                f'{"".join(lines)}'
                f'<ellipse cx="{cx}" cy="{f_y}" rx="{280 if is16 else 340}" ry="48" stroke="{ac}" stroke-opacity=".75" stroke-width="3" fill="none"/>'
                f'<ellipse cx="{cx}" cy="{f_y}" rx="{185 if is16 else 225}" ry="30" stroke="#FFFFFF" stroke-opacity=".45" stroke-width="1.8" fill="none"/>'
            )
        elif mode == "shatter":
            rays = []
            for i in range(28):
                ang = i / 28.0 * 2.0 * math.pi
                ln = 260 + (i % 4) * 160
                x2 = int(cx + math.cos(ang) * ln)
                y2 = int(cy + math.sin(ang) * ln)
                rays.append(f'<line x1="{cx}" y1="{cy}" x2="{x2}" y2="{y2}" stroke="{ac}" stroke-opacity=".30" stroke-width="{"1.2" if i % 3 else "2.8"}"/>')
            extra = "".join(rays)
        elif mode == "chromatic":
            extra = (
                f'<rect width="{w}" height="{h}" fill="url(#htP)" opacity=".35"/>'
            )
        elif mode == "foil":
            extra = '<rect width="{w}" height="{h}" fill="url(#foilGrid)"/>'.format(w=w, h=h)

    return (
        f'<svg class="abs-fill" style="z-index:0;width:100%;height:100%" viewBox="0 0 {w} {h}" fill="none">'
        f'<defs>'
        f'<linearGradient id="bgMain" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#050A18"/><stop offset="45%" stop-color="#0C1732"/><stop offset="100%" stop-color="#040814"/></linearGradient>'
        f'<radialGradient id="nbGlow" cx="{cx / w * 100:.1f}%" cy="{cy / h * 100:.1f}%" r="58%"><stop offset="0%" stop-color="rgba({r},{g},{b},{op_glow})"/><stop offset="48%" stop-color="rgba({r},{g},{b},.08)"/><stop offset="100%" stop-color="rgba(0,0,0,0)"/></radialGradient>'
        f'<linearGradient id="bmW" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="rgba(255,255,255,.22)"/><stop offset="100%" stop-color="rgba(255,255,255,0)"/></linearGradient>'
        f'<linearGradient id="bmA" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="rgba({r},{g},{b},.26)"/><stop offset="100%" stop-color="rgba({r},{g},{b},0)"/></linearGradient>'
        f'<linearGradient id="pgG" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="rgba({r},{g},{b},.16)"/><stop offset="40%" stop-color="rgba(16,185,129,.08)"/><stop offset="100%" stop-color="rgba(5,10,24,0)"/></linearGradient>'
        f'<pattern id="htP" width="20" height="20" patternUnits="userSpaceOnUse"><circle cx="10" cy="10" r="2.2" fill="{ac}"/></pattern>'
        f'<pattern id="foilGrid" width="60" height="60" patternUnits="userSpaceOnUse"><path d="M60 0H0V60" stroke="#F8FAFC" stroke-opacity=".06" stroke-width="1"/></pattern>'
        f'</defs>'
        f'<rect width="{w}" height="{h}" fill="url(#bgMain)"/>'
        f'<rect width="{w}" height="{h}" fill="url(#nbGlow)"/>'
        f'{extra}</svg>'
    )


@with_sample_badge
def render_number_of_day_html(
    item: dict[str, Any],
    *,
    slide: str = "slide1",
    header_mode: str = "full",
    fmt: str = "4:5",
    theme: str = "lalezar",
    modules: list[dict[str, Any]] | None = None,
) -> str:
    """تولید HTML ۱۰۰٪ آفلاین و ۱:۱ مطابق `number of the day.html` در ۵ اسلاید و ۳ فرمت."""
    w, h = NOD_FORMATS.get(fmt, NOD_FORMATS["4:5"])
    is16, is9 = fmt == "16:9", fmt == "9:16"
    mode, mode_en = _SLIDE_TO_MODE.get(slide, _SLIDE_TO_MODE.get(str(item.get("mode") or "gazette"), ("gazette", "SWISS INVERSION")))

    mod_map = {m["id"]: bool(m.get("enabled", True)) for m in (modules or []) if isinstance(m, dict) and m.get("id")}
    show_kpis = mod_map.get("kpis", True)
    show_bench = mod_map.get("bench", True)
    show_fx = mod_map.get("fx", True)

    font_style = theme if theme in {"lalezar", "vazir", "bebas"} else "lalezar"
    ff, fw, fls, y_off, boost = _font_metrics(font_style)

    raw_ac = str(item.get("accent") or "#E62E45")
    ac = ensure_dark_bg_contrast(raw_ac, min_ratio=4.5)

    raw_num = f"{item.get('number') or '91'}{item.get('suffix') or ''}"
    tx = esc(_num_str(raw_num, font_style))
    old_tx = esc(_num_str(item.get("benchVal") if item.get("benchVal") is not None else "", font_style))

    def _tx_el(x: float, y: float, sz: int, attrs: str, s: str = tx) -> str:
        return (
            f'<text x="{x:.0f}" y="{y:.0f}" text-anchor="middle" font-family="{ff}" '
            f'font-weight="{fw}" font-size="{sz}" letter-spacing="{fls}" {attrs}>{s}</text>'
        )

    _banned_kpi_labels = {"عدد شاخص", "وضعیت داده", "منبع"}
    _banned_phrases = {"آمار برگزیده روز فوتبال", "عدد داغ در رسانه‌های معتبر اروپا", "عدد داغ در رسانه های معتبر اروپا"}
    kpis = [
        k for k in (item.get("kpis") or [])
        if isinstance(k, (list, tuple)) and len(k) >= 2 and str(k[1]).strip() not in _banned_kpi_labels
    ][:3]

    def _kpi_bar(compact: bool) -> str:
        if not show_kpis or not kpis:
            return ""
        v_sz = 38 if compact else 46
        l_sz = 16 if compact else 18
        cells = "".join(
            f'<div class="kpi-cell"><div style="font-size:{v_sz}px;font-weight:900;line-height:1;color:{ac if i == 0 else "#FFFFFF"}">{esc(_num_str(v, font_style))}</div>'
            f'<div style="font-size:{l_sz}px;font-weight:700;color:#CBD5E1;margin-top:6px">{esc(lbl)}</div></div>'
            for i, (v, lbl) in enumerate(kpis)
        )
        return f'<div class="kpi-bar" style="padding:{"12px 0" if compact else "14px 0"}">{cells}</div>'

    _raw_unit = str(item.get("unit") or "").strip()
    _raw_pin = str(item.get("pinText") or "").strip()
    _raw_delta = str(item.get("deltaLabel") or "").strip()
    unit_txt = esc("" if _raw_unit in _banned_phrases else _raw_unit)
    pin_txt = esc("" if _raw_pin in _banned_phrases else _raw_pin)
    hl_txt = esc(item.get("headline") or "")
    body_txt = esc(item.get("body") or "")
    sub_txt = esc(item.get("subject") or "فوتبال")
    sub_en = esc(str(item.get("subjectEn") or item.get("subjectCode") or "XGPEDIA").upper())
    sub_code = esc(str(item.get("subjectCode") or "XGP").upper())
    bench_lbl = esc(item.get("benchLabel") or "رکورد قبلی")
    delta_txt = esc("" if _raw_delta in _banned_phrases else (_raw_delta or ("" if _raw_pin in _banned_phrases else _raw_pin)))
    _raw_rib = str(item.get("ribbonText") or "").strip()
    _rib_ascii = sum(1 for c in _raw_rib if "a" <= c.lower() <= "z")
    _rib_fa = sum(1 for c in _raw_rib if "\u0600" <= c <= "\u06ff")
    _rib_fallback = _raw_unit or "آمار ویژه"
    ribbon_txt = esc(f"عدد روز فوتبال • {_rib_fallback}" if (not _raw_rib or _rib_ascii > _rib_fa) else _raw_rib)
    issue_txt = esc(str(item.get("issue") or "001"))
    unit_badge_html = f'<span class="u-box" style="background:{ac}">{unit_txt}</span>' if unit_txt else ""
    pin_badge_html = f'<span class="pin-w">{pin_txt}</span>' if pin_txt else ""
    pin_a_html = f'<span class="pill-a" style="background:{ac}">{pin_txt}</span>' if pin_txt else ""
    pin_b_html = f'<span class="pill-b" style="border-color:{ac}90">{pin_txt}</span>' if pin_txt else ""
    delta_a_html = f'<span class="pill-a" style="background:{ac}">{delta_txt}</span>' if delta_txt else ""
    delta_b_html = f'<span class="pill-b" style="align-self:flex-start;border-color:{ac}">{delta_txt}</span>' if delta_txt else ""

    if mode == "gazette":
        cx = w * (0.27 if is16 else 0.52)
        cy = h * (0.52 if is16 else (0.44 if is9 else 0.45))
        fs = _calc_font_size(raw_num, 640 if is16 else (820 if is9 else 750), boost)
        y_t = cy + fs * y_off
        gx = round(w * (0.28 if is16 else 0.54))
        rb = round(w * 0.50) if is16 else (w - 44)
        g1 = round(h * 0.16)
        g2 = round(h * (0.84 if is16 else (0.62 if is9 else 0.65)))
        w_y = round(cy - 65)
        art_svg = (
            f'<svg class="abs-fill" style="z-index:1;width:100%;height:100%" viewBox="0 0 {w} {h}" fill="none" dir="ltr">'
            f'<defs>'
            f'<clipPath id="qC"><rect x="{gx}" y="{g1}" width="{rb - gx}" height="{g2 - g1}"/></clipPath>'
            f'<clipPath id="qW"><rect x="44" y="{w_y}" width="{gx - 44}" height="145"/></clipPath>'
            f'<clipPath id="qR"><path fill-rule="evenodd" d="M0 0H{w}V{h}H0ZM{gx} {g1}H{rb}V{g2}H{gx}ZM44 {w_y}H{gx}V{w_y + 145}H44Z"/></clipPath>'
            f'<pattern id="gD" width="12" height="12" patternUnits="userSpaceOnUse"><circle cx="6" cy="6" r="1.5" fill="#070D1D" fill-opacity=".22"/></pattern>'
            f'</defs>'
            f'<rect x="{gx}" y="{g1}" width="{rb - gx}" height="{g2 - g1}" fill="{ac}"/>'
            f'<rect x="{gx}" y="{g1}" width="{rb - gx}" height="{g2 - g1}" fill="url(#gD)"/>'
            f'<rect x="44" y="{w_y}" width="{gx - 44}" height="145" fill="#F8FAFC"/>'
            f'<g stroke="#F8FAFC" stroke-opacity=".22" stroke-width="1.5">'
            f'<line x1="{gx}" y1="108" x2="{gx}" y2="{h - 86}"/><line x1="44" y1="{g1}" x2="{rb}" y2="{g1}"/>'
            f'<line x1="44" y1="{g2}" x2="{rb}" y2="{g2}"/><line x1="44" y1="108" x2="44" y2="{h - 86}"/><line x1="{rb}" y1="108" x2="{rb}" y2="{h - 86}"/></g>'
            f'<text x="{gx + (rb - gx) // 2}" y="{g1 + 30}" text-anchor="middle" font-family="Vazirmatn,sans-serif" font-weight="800" font-size="16" fill="#FFF" fill-opacity=".92">آمار شاخص</text>'
            + (f'<text x="{(44 + gx) // 2}" y="{g1 + 30}" text-anchor="middle" font-family="Vazirmatn,sans-serif" font-weight="700" font-size="15" fill="#94A3B8">رکورد قبلی: {old_tx}</text>' if old_tx else '')
            + ''
            + '<g clip-path="url(#qR)">' + _tx_el(cx + 12, y_t + 12, fs, f'fill="none" stroke="{ac}" stroke-opacity=".55" stroke-width="3"') + _tx_el(cx, y_t, fs, 'fill="#F8FAFC"') + '</g>'
            + '<g clip-path="url(#qC)">' + _tx_el(cx, y_t, fs, 'fill="#070D1D"') + _tx_el(cx, y_t, fs, 'fill="none" stroke="#FFF" stroke-width="3.5"') + '</g>'
            + '<g clip-path="url(#qW)">' + _tx_el(cx, y_t, fs, f'fill="{ac}"') + '</g></svg>'
        )
        kpi_rows = "".join(
            f'<div class="gz-kpi"><span style="font-size:18px;font-weight:700;color:#CBD5E1">{esc(lbl)}</span>'
            f'<span style="font-size:{40 if is9 else 35}px;font-weight:900;line-height:1;color:{ac if i == 0 else "#FFF"}">{esc(_num_str(v, font_style))}</span></div>'
            for i, (v, lbl) in enumerate(kpis)
        ) if show_kpis else ""
        if is16:
            kpi_16 = "".join(
                f'<div><div style="font-size:40px;font-weight:900;line-height:1;color:{ac if i == 0 else "#FFF"}">{esc(_num_str(v, font_style))}</div>'
                f'<div style="font-size:17px;font-weight:700;color:#CBD5E1;margin-top:4px">{esc(lbl)}</div></div>'
                for i, (v, lbl) in enumerate(kpis)
            ) if show_kpis else ""
            body_html = (
                f'<div class="grid-2-16"><div class="fcol justify-center gap18">'
                f'<div class="fi gap10" style="flex-wrap:wrap">{unit_badge_html}{pin_badge_html}</div>'
                f'<h1 style="font-size:44px;font-weight:900;line-height:1.18;color:#fff">{hl_txt}</h1>'
                f'<p style="font-size:21px;line-height:1.58;color:#E2E8F0;font-weight:600">{body_txt}</p>'
                f'<div class="grid-3-div">{kpi_16}</div></div><div></div></div>'
            )
        else:
            body_html = (
                f'<div class="fcol flex1 justify-end" style="padding-bottom:10px">'
                f'<div class="gz-bot"><div class="fcol gap12">'
                f'<div class="fi gap10" style="flex-wrap:wrap">{unit_badge_html}{pin_badge_html}</div>'
                f'<h1 style="font-size:{42 if is9 else 36}px;font-weight:900;line-height:1.18;color:#fff">{hl_txt}</h1>'
                f'<p style="font-size:{21.5 if is9 else 19}px;line-height:1.55;color:#E2E8F0;font-weight:600">{body_txt}</p></div>'
                f'<div class="gz-kpis">{kpi_rows}</div></div></div>'
            )
    elif mode == "cathedral":
        cx = w * (0.31 if is16 else 0.50)
        cy = h * (0.50 if is16 else 0.42)
        fs = _calc_font_size(raw_num, 620 if is16 else (720 if is9 else 660), boost)
        y_t = cy + fs * y_off
        ex = "".join(
            _tx_el(cx, y_t + (14 - i) * 2.6, fs, f'fill="{"#030712" if i < 4 else ("#162447" if i < 9 else ac)}" fill-opacity="{0.35 + i * 0.045:.2f}"')
            for i in range(14)
        )
        old_g = _tx_el(cx, y_t - 95, round(fs * 0.72), 'fill="none" stroke="#FFF" stroke-opacity=".11" stroke-width="2.5" stroke-dasharray="10 8"', old_tx) if (show_bench and old_tx) else ""
        art_svg = (
            f'<svg class="abs-fill" style="z-index:1;width:100%;height:100%" viewBox="0 0 {w} {h}" fill="none" dir="ltr">'
            f'<defs><linearGradient id="cF" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0%" stop-color="#FFF"/><stop offset="28%" stop-color="#F8FAFC"/><stop offset="52%" stop-color="#CBD5E1"/>'
            f'<stop offset="56%" stop-color="#FFF"/><stop offset="82%" stop-color="#E2E8F0"/><stop offset="100%" stop-color="{ac}"/></linearGradient></defs>'
            f'{old_g}<circle cx="{cx:.0f}" cy="{cy - 10:.0f}" r="{min(w, h) * 0.34:.0f}" stroke="{ac}" stroke-opacity=".38" stroke-width="3"/>'
            f'<circle cx="{cx:.0f}" cy="{cy - 10:.0f}" r="{min(w, h) * 0.38:.0f}" stroke="#FFF" stroke-opacity=".10" stroke-width="1.5" stroke-dasharray="4 10"/>'
            + f'{ex}' + _tx_el(cx, y_t, fs, 'fill="url(#cF)"') + _tx_el(cx, y_t, fs, 'fill="none" stroke="#FFF" stroke-opacity=".95" stroke-width="3"') + '</svg>'
        )
        if is16:
            body_html = (
                f'<div class="grid-2-16"><div class="fcol justify-center gap18">'
                f'<div class="fi gap12">{pin_a_html}<span style="font-size:19px;font-weight:800;color:#CBD5E1">{sub_txt}</span></div>'
                f'<h1 style="font-size:44px;font-weight:900;line-height:1.18;color:#fff">{hl_txt}</h1>'
                f'<p style="font-size:21px;line-height:1.6;color:#E2E8F0;font-weight:600;border-right:4px solid {ac};padding-right:18px">{body_txt}</p>'
                f'{_kpi_bar(True)}</div><div class="fcol justify-end items-center" style="padding-bottom:18px">'
                f'<div class="unit-pill" style="border-color:{ac}"><span class="pdot" style="background:{ac}"></span><span>{unit_txt}</span></div></div></div>'
            )
        else:
            body_html = (
                f'<div class="fcol flex1 justify-between" style="padding-bottom:10px">'
                f'<div class="fbw" style="padding-top:8px">{pin_b_html}'
                f'<span style="font-size:19px;font-weight:800;color:#CBD5E1">{sub_txt}</span></div>'
                + ('<div class="fcol gap14">' + (f'<div class="fc"><div class="unit-grad" style="background:linear-gradient(135deg,{ac},#0B1633)">{unit_txt}</div></div>' if unit_txt else ''))
                + f'<h1 style="font-size:{44 if is9 else 38}px;font-weight:900;line-height:1.18;color:#fff;text-align:center">{hl_txt}</h1>'
                f'<p style="font-size:{22 if is9 else 20}px;line-height:1.55;color:#E2E8F0;font-weight:600;text-align:center;max-width:880px;margin:0 auto">{body_txt}</p>'
                f'{_kpi_bar(not is9)}</div></div>'
            )
    elif mode == "shatter":
        cx = w * (0.27 if is16 else 0.50)
        cy = h * (0.49 if is16 else (0.41 if is9 else 0.39))
        fs = _calc_font_size(raw_num, 600 if is16 else (700 if is9 else 640), boost)
        y_t = cy + fs * y_off
        crk = "".join(
            f'<polyline points="{cx:.0f},{cy:.0f} {cx + math.cos(i / 16 * 6.283) * (80 + i % 3 * 35):.0f},{cy + math.sin(i / 16 * 6.283) * (80 + i % 3 * 35):.0f} '
            f'{cx + math.cos(i / 16 * 6.283 + .08) * (250 + i % 4 * 75):.0f},{cy + math.sin(i / 16 * 6.283 + .08) * (250 + i % 4 * 75):.0f} '
            f'{cx + math.cos(i / 16 * 6.283 - .05) * (440 + i % 3 * 90):.0f},{cy + math.sin(i / 16 * 6.283 - .05) * (440 + i % 3 * 90):.0f}" '
            f'stroke="{"#FFF" if i % 3 else ac}" stroke-opacity="{".28" if i % 3 else ".65"}" stroke-width="{"1.4" if i % 3 else "2.6"}" fill="none"/>'
            for i in range(16)
        )
        shd = "".join(
            f'<polygon points="0,{-(16 + i % 4 * 14)} {(16 + i % 4 * 14) * .7:.0f},{(16 + i % 4 * 14) * .4:.0f} {-(16 + i % 4 * 14) * .6:.0f},{(16 + i % 4 * 14) * .8:.0f}" '
            f'transform="translate({cx + math.cos(i / 22 * 6.283) * (195 + i % 5 * 58):.0f},{cy + math.sin(i / 22 * 6.283) * (195 + i % 5 * 58):.0f}) rotate({i * 47 % 360})" '
            f'fill="{"#FFF" if i % 3 else ac}" fill-opacity="{".20" if i % 3 else ".36"}" stroke="#FFF" stroke-opacity=".55" stroke-width="1.3"/>'
            for i in range(22)
        )
        old_g = (
            f'<g opacity=".22" transform="translate({cx - 170:.0f},{cy - 150:.0f}) rotate(-12)">'
            + _tx_el(0, 0, round(fs * 0.42), 'fill="none" stroke="#FFF" stroke-width="2.5"', old_tx) +
            f'<line x1="-110" y1="-45" x2="110" y2="-45" stroke="{ac}" stroke-width="6"/></g>'
            if (show_bench and old_tx) else ""
        )
        art_svg = (
            f'<svg class="abs-fill" style="z-index:1;width:100%;height:100%" viewBox="0 0 {w} {h}" fill="none" dir="ltr">'
            f'<defs><linearGradient id="sF" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#FFF"/><stop offset="45%" stop-color="#F8FAFC"/><stop offset="100%" stop-color="{ac}"/></linearGradient></defs>'
            + f'{old_g}{crk}{shd}' + _tx_el(cx + 16, y_t + 18, fs, 'fill="#02050D" fill-opacity=".88"') +
            _tx_el(cx, y_t, fs, 'fill="url(#sF)"') + _tx_el(cx, y_t, fs, 'fill="none" stroke="#FFF" stroke-width="3.5"') + '</svg>'
        )
        bench_span = f'<span style="font-size:19px;font-weight:700;color:#CBD5E1">{bench_lbl}: <b style="color:#fff;text-decoration:line-through;text-decoration-color:{ac}">{old_tx}</b></span>' if (show_bench and old_tx) else ""
        if is16:
            body_html = (
                f'<div class="grid-2-16"><div class="fcol justify-center gap18">'
                f'{delta_b_html}'
                f'<h1 style="font-size:44px;font-weight:900;line-height:1.18;color:#fff">{hl_txt}</h1>'
                f'<p style="font-size:21px;line-height:1.58;color:#E2E8F0;font-weight:600">{body_txt}</p>'
                f'{_kpi_bar(True)}</div><div class="fcol justify-end items-center" style="padding-bottom:18px">'
                f'<span class="u-box" style="background:{ac};border-radius:16px">{unit_txt}</span></div></div>'
            )
        else:
            body_html = (
                f'<div class="fcol flex1 justify-between" style="padding-bottom:10px">'
                f'<div style="display:flex;justify-content:flex-end;padding-top:8px">{delta_a_html}</div>'
                f'<div class="fcol gap14">'
                f'<div class="fbw" style="border-bottom:1px solid rgba(255,255,255,.15);padding-bottom:10px"><span style="font-size:27px;font-weight:900;color:#fff">{unit_txt}</span>{bench_span}</div>'
                + f'<h1 style="font-size:{44 if is9 else 38}px;font-weight:900;line-height:1.18;color:#fff">{hl_txt}</h1>'
                f'<p style="font-size:{22 if is9 else 20}px;line-height:1.55;color:#E2E8F0;font-weight:600">{body_txt}</p>'
                f'{_kpi_bar(not is9)}</div></div>'
            )
    elif mode == "chromatic":
        cx = w * (0.27 if is16 else 0.50)
        cy = h * (0.50 if is16 else (0.41 if is9 else 0.39))
        fs = _calc_font_size(raw_num, 590 if is16 else (700 if is9 else 630), boost)
        y_t = cy + fs * y_off
        y1, y2 = cy - 95, cy + 35
        wl = "".join(
            f'<text x="{w // 2}" y="{180 + i * 135}" text-anchor="middle" font-family="Space Grotesk,sans-serif" font-weight="800" font-size="88" letter-spacing="8" fill="none" stroke="#FFF" stroke-opacity=".06" stroke-width="1.5">{esc((f"{sub_en} • {raw_num} • ") * 3)}</text>'
            for i in range(6)
        )
        art_svg = (
            f'<svg class="abs-fill" style="z-index:1;width:100%;height:100%" viewBox="0 0 {w} {h}" fill="none" dir="ltr">'
            f'<defs>'
            f'<clipPath id="c1"><polygon points="0,0 {w},0 {w},{y1 - 55:.0f} 0,{y1 + 55:.0f}"/></clipPath>'
            f'<clipPath id="c2"><polygon points="0,{y1 + 55:.0f} {w},{y1 - 55:.0f} {w},{y2 - 55:.0f} 0,{y2 + 55:.0f}"/></clipPath>'
            f'<clipPath id="c3"><polygon points="0,{y2 + 55:.0f} {w},{y2 - 55:.0f} {w},{h} 0,{h}"/></clipPath></defs>'
            + f'{wl}' + _tx_el(cx - 16, y_t, fs, 'fill="#00F0FF" fill-opacity=".45"') +
            _tx_el(cx + 16, y_t, fs, f'fill="{ac}" fill-opacity=".62"') +
            '<g clip-path="url(#c1)" transform="translate(18,-10)">' + _tx_el(cx, y_t, fs, 'fill="#FFF"') + '</g>'
            + '<g clip-path="url(#c2)" transform="translate(-22,0)">' + _tx_el(cx, y_t, fs, 'fill="#F8FAFC"') + _tx_el(cx, y_t, fs, f'fill="none" stroke="{ac}" stroke-width="4"') + '</g>'
            + '<g clip-path="url(#c3)" transform="translate(14,12)">' + _tx_el(cx, y_t, fs, 'fill="#E2E8F0"') + '</g>'
            + f'<line x1="0" y1="{y1 + 55:.0f}" x2="{w}" y2="{y1 - 55:.0f}" stroke="{ac}" stroke-width="4"/>'
            f'<line x1="0" y1="{y2 + 55:.0f}" x2="{w}" y2="{y2 - 55:.0f}" stroke="#00F0FF" stroke-opacity=".85" stroke-width="2.5"/>'
            f'<g transform="translate({cx:.0f},{y2 - 2:.0f}) rotate(-6.2)"><rect x="-390" y="-24" width="780" height="48" fill="{ac}"/>'
            f'<text x="0" y="9" text-anchor="middle" font-family="Vazirmatn,sans-serif" font-weight="900" font-size="22" fill="#FFF">{ribbon_txt}</text></g></svg>'
        )
        if is16:
            body_html = (
                f'<div class="grid-2-16"><div class="fcol justify-center gap18">'
                f'{pin_a_html}'
                f'<h1 style="font-size:44px;font-weight:900;line-height:1.18;color:#fff">{hl_txt}</h1>'
                f'<p style="font-size:21px;line-height:1.58;color:#E2E8F0;font-weight:600">{body_txt}</p>'
                f'{_kpi_bar(True)}</div><div class="fcol justify-end items-center" style="padding-bottom:18px">'
                f'<span class="pin-w" style="font-size:25px;padding:8px 22px">{unit_txt}</span></div></div>'
            )
        else:
            body_html = (
                f'<div class="fcol flex1 justify-between" style="padding-bottom:10px">'
                f'<div style="display:flex;justify-content:flex-start;padding-top:8px">{pin_badge_html}</div>'
                f'<div class="fcol gap14">'
                f'<div class="fi gap12">{unit_badge_html}<span style="font-size:22px;font-weight:900;color:#fff">{sub_txt}</span></div>'
                + f'<h1 style="font-size:{44 if is9 else 38}px;font-weight:900;line-height:1.18;color:#fff">{hl_txt}</h1>'
                f'<p style="font-size:{22 if is9 else 20}px;line-height:1.55;color:#E2E8F0;font-weight:600">{body_txt}</p>'
                f'{_kpi_bar(not is9)}</div></div>'
            )
    else:
        # foil
        n_x = w * (0.25 if is16 else 0.76)
        n_y = h * (0.56 if is16 else 0.53)
        fs = _calc_font_size(raw_num, 660 if is16 else (820 if is9 else 740), boost)
        d_x = round(w * 0.50)
        s_x = round(w * 0.43) if is16 else (w - 132)
        s_y = 205 if is16 else 235
        b_x = 56 if is16 else (w - 224)
        bars = "".join(
            f'<rect x="{b_x + i * 9}" y="{h - 126}" width="{bw}" height="30" fill="#F8FAFC" fill-opacity=".35"/>'
            for i, bw in enumerate([4, 2, 6, 2, 3, 5, 2, 4, 2, 6, 3, 2, 5, 3, 4, 2, 6, 2, 3, 4])
        )
        art_svg = (
            f'<svg class="abs-fill" style="z-index:1;width:100%;height:100%" viewBox="0 0 {w} {h}" fill="none" dir="ltr">'
            f'<defs>'
            f'<linearGradient id="fG" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#FFF"/><stop offset="28%" stop-color="#FDE68A"/><stop offset="55%" stop-color="{ac}"/><stop offset="82%" stop-color="#38BDF8"/><stop offset="100%" stop-color="#FFF"/></linearGradient>'
            f'<pattern id="fS" width="8" height="8" patternUnits="userSpaceOnUse"><line x1="0" y1="0" x2="8" y2="0" stroke="#000" stroke-opacity=".22" stroke-width="2"/></pattern>'
            f'<clipPath id="fH"><rect x="{0 if is16 else d_x}" y="0" width="{d_x if is16 else w - d_x}" height="{h}"/></clipPath>'
            f'<path id="fA" d="M {s_x} {s_y} m -54,0 a 54,54 0 1,1 108,0 a 54,54 0 1,1 -108,0"/></defs>'
            f'<line x1="{d_x}" y1="108" x2="{d_x}" y2="{h - 88}" stroke="{ac}" stroke-opacity=".6" stroke-width="2"/>'
            + '<g clip-path="url(#fH)">' + _tx_el(n_x, n_y - 88, fs, 'fill="none" stroke="#FFF" stroke-opacity=".14" stroke-width="2.5"') +
            _tx_el(n_x, n_y + fs * .26, fs, 'fill="url(#fG)"') + _tx_el(n_x, n_y + fs * .26, fs, 'fill="url(#fS)"') +
            _tx_el(n_x, n_y + fs * .26, fs, 'fill="none" stroke="#FFF" stroke-opacity=".88" stroke-width="3"') + '</g>'
            + f'<g><circle cx="{s_x}" cy="{s_y}" r="68" fill="#060C1C" fill-opacity=".94" stroke="url(#fG)" stroke-width="2.8"/>'
            f'<circle cx="{s_x}" cy="{s_y}" r="40" fill="none" stroke="#FFF" stroke-opacity=".25" stroke-width="1.4" stroke-dasharray="3 4"/>'
            f'<text font-family="Space Grotesk,JetBrains Mono,sans-serif" font-weight="800" font-size="11" letter-spacing="2.3" fill="#F8FAFC"><textPath href="#fA" startOffset="0%">★ XGPEDIA COLLECTOR ★ ARCHIVE EDITION </textPath></text>'
            f'<text x="{s_x}" y="{s_y + 8}" text-anchor="middle" font-family="JetBrains Mono,monospace" font-weight="800" font-size="22" fill="{ac}">#{issue_txt}</text></g>{bars}</svg>'
        )
        hv = max(1.0, float(item.get("heroNumVal") or 91))
        _raw_bv = item.get("benchVal")
        bv = max(1.0, float(_raw_bv)) if _raw_bv is not None else 0.0
        mx = max(hv, bv, 1.0)
        bench_block = (
            f'<div class="foil-bench">'
            f'<div class="fbw" style="font-size:16px;font-weight:800"><span style="color:#CBD5E1">در برابر رکورد</span><span style="color:{ac}">{delta_txt}</span></div>'
            f'<div class="fbw" style="font-size:18px;font-weight:900"><span>{sub_txt}</span><span style="color:{ac}">{tx}</span></div>'
            f'<div class="fbar"><div class="fbar-f" style="width:{hv / mx * 100:.1f}%;background:{ac}"></div></div>'
            f'<div class="fbw" style="font-size:15px;font-weight:700;color:#94A3B8"><span>{bench_lbl}</span><span>{old_tx}</span></div>'
            f'<div class="fbar" style="height:10px"><div class="fbar-f" style="width:{bv / mx * 100:.1f}%;background:#94A3B8"></div></div></div>'
            if (show_bench and _raw_bv is not None and old_tx) else ""
        )
        foil_kpis = (
            '<div class="foil-kpis">' + "".join(
                f'<div class="foil-k"><div style="font-size:29px;font-weight:900;line-height:1;color:{ac if i == 0 else "#FFF"}">{esc(_num_str(v, font_style))}</div>'
                f'<div style="font-size:13.5px;font-weight:700;color:#CBD5E1;margin-top:6px" class="trunc">{esc(lbl)}</div></div>'
                for i, (v, lbl) in enumerate(kpis)
            ) + '</div>'
        ) if (show_kpis and kpis) else ""
        col_html = (
            f'<div class="fcol justify-between" style="height:100%;padding:16px 0;gap:14px">'
            f'<div class="fcol gap12"><div style="font-size:18px;font-weight:800;color:#94A3B8">{sub_txt}</div>'
            + (f'<span class="u-box" style="align-self:flex-start;background:{ac};border-radius:10px;font-size:20px">{unit_txt}</span>' if unit_txt else '')
            + f'<h1 style="font-size:{40 if (is9 or is16) else 34}px;font-weight:900;line-height:1.2;color:#fff">{hl_txt}</h1>'
            f'<p style="font-size:{21 if (is9 or is16) else 18.5}px;line-height:1.55;color:#E2E8F0;font-weight:600">{body_txt}</p></div>'
            f'{bench_block}{foil_kpis}</div>'
        )
        body_html = f'<div class="grid-2-16"><div>{col_html}</div><div></div></div>' if is16 else f'<div class="grid-2-16"><div></div><div>{col_html}</div></div>'

    pad_top = 139 if is9 else (24 if is16 else 22)
    pad_bot = 171 if is9 else (20 if is16 else 16)
    rx1, rx2, by1, by2 = w - 24, w - 44, h - 24, h - 44
    cat_txt = esc(item.get("category") or "عدد روز فوتبال")
    date_txt = fa(esc(item.get("date") or "فصل جاری"))
    src_txt = esc(item.get("source") or "XGPedia")
    mode_fa_map = {"gazette": "تحلیل سوئیسی", "cathedral": "یادمان آماری", "shatter": "رکوردشکنی", "chromatic": "گلیچ آماری", "foil": "نسخه کلکسیونی"}
    _mfa = mode_fa_map.get(mode, "آمار ویژه")
    ticker_txt = f"عدد روز XGPedia • {_mfa} • شماره {fa(issue_txt)}"
    hdr_sub = "" if header_mode == "compact" else f'<div class="hdr-sub"><span style="color:#fff">{sub_txt}</span><span style="color:#64748B">•</span><span>{date_txt}</span></div>'

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8"/>
<style>
{build_embedded_font_css()}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{w}px;height:{h}px;overflow:hidden;background:#081024;color:#F8FAFC;font-family:'Vazirmatn',system-ui,-apple-system,sans-serif;font-feature-settings:"tnum";font-variant-numeric:tabular-nums}}
.fm{{font-family:'JetBrains Mono','Space Grotesk',monospace}}
.fd{{font-family:'Space Grotesk','Vazirmatn',sans-serif}}
.fi{{display:flex;align-items:center}}.fc{{display:flex;align-items:center;justify-content:center}}.fbw{{display:flex;align-items:center;justify-content:space-between}}.fcol{{display:flex;flex-direction:column}}
.flex1{{flex:1}}.justify-end{{justify-content:flex-end}}.justify-center{{justify-content:center}}.justify-between{{justify-content:space-between}}.items-center{{align-items:center}}
.gap10{{gap:10px}}.gap12{{gap:12px}}.gap14{{gap:14px}}.gap18{{gap:18px}}
.trunc{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.abs-fill{{position:absolute;inset:0;pointer-events:none}}
#ea{{position:relative;width:{w}px;height:{h}px;padding:{pad_top}px 0 {pad_bot}px;background:#081024;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden}}
.hdr{{position:relative;z-index:10;padding:12px 36px 8px;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-shrink:0}}
.hdr-pill{{display:inline-flex;align-items:center;gap:10px;padding:6px 20px;border-radius:999px;background:#070E1Fe0;border:1.5px solid #ffffff30;font-size:20px;font-weight:900;color:#F8FAFC}}
.iss-pill{{padding:6px 16px;border-radius:999px;border:1.5px solid {ac}85;background:{ac}28;font-size:18px;font-weight:800;color:#F8FAFC}}
.hdr-sub{{display:flex;align-items:center;gap:10px;font-size:19px;font-weight:700;color:#CBD5E1;margin-top:6px}}
.pdot{{width:11px;height:11px;border-radius:999px;flex-shrink:0}}
.stage{{position:relative;z-index:10;flex:1;padding:8px 40px;display:flex;flex-direction:column;overflow:hidden;min-height:0}}
.u-box{{display:inline-flex;padding:5px 18px;font-weight:900;font-size:23px;color:#fff}}
.pin-w{{display:inline-flex;padding:5px 16px;background:#FFFFFF;color:#070D1D;font-weight:900;font-size:18px}}
.pill-a{{display:inline-flex;padding:6px 20px;border-radius:999px;font-weight:900;font-size:18.5px;color:#fff}}
.pill-b{{display:inline-flex;padding:6px 18px;border-radius:999px;background:rgba(6,13,30,.90);border:1.5px solid;font-weight:800;font-size:18.5px;color:#fff}}
.unit-pill{{display:inline-flex;align-items:center;gap:12px;padding:8px 24px;border-radius:16px;background:rgba(5,11,24,.90);border:2px solid;font-size:25px;font-weight:900;color:#fff}}
.unit-grad{{padding:8px 28px;border-radius:16px;font-weight:900;font-size:27px;color:#fff;border:1px solid rgba(255,255,255,.25)}}
.kpi-bar{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));border-top:1px solid rgba(255,255,255,.18);border-bottom:1px solid rgba(255,255,255,.18);background:rgba(6,12,28,.75)}}
.kpi-cell{{padding:0 12px;text-align:center;border-left:1px solid rgba(255,255,255,.15)}}
.kpi-cell:last-child{{border-left:none}}
.grid-2-16{{display:grid;grid-template-columns:1fr 1fr;gap:30px;height:100%;align-items:center}}
.grid-3-div{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;border-top:1px solid rgba(255,255,255,.20);padding-top:16px}}
.gz-bot{{display:grid;grid-template-columns:7fr 5fr;gap:24px;align-items:end;padding-top:16px}}
.gz-kpis{{display:flex;flex-direction:column;border-right:1px solid rgba(255,255,255,.20);padding-right:20px}}
.gz-kpi{{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 0;border-bottom:1px solid rgba(255,255,255,.16)}}
.gz-kpi:last-child{{border-bottom:none}}
.foil-bench{{display:flex;flex-direction:column;gap:8px;padding:14px 0;border-top:1px solid rgba(255,255,255,.16);border-bottom:1px solid rgba(255,255,255,.16)}}
.fbar{{height:12px;border-radius:999px;background:rgba(255,255,255,.10);overflow:hidden}}
.fbar-f{{height:100%;border-radius:999px}}
.foil-kpis{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}}
.foil-k{{border-radius:12px;padding:10px;background:rgba(6,12,28,.88);border:1px solid rgba(255,255,255,.14);text-align:center}}
.ftr{{position:relative;z-index:10;padding:10px 44px 10px;border-top:1px solid rgba(255,255,255,.16);display:flex;align-items:center;justify-content:space-between;gap:16px;flex-shrink:0;flex-wrap:nowrap!important;white-space:nowrap!important;overflow:hidden!important}}
.ftr-l{{display:flex;align-items:center;gap:10px;min-width:0;overflow:hidden;white-space:nowrap!important;text-overflow:ellipsis!important}}
.ftr-dot{{width:11px;height:11px;border-radius:999px;background:{ac};flex-shrink:0}}
.ftr-tk{{font-size:17px;font-weight:800;letter-spacing:.12em;color:#F1F5F9;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}}
.ftr-r{{display:flex;align-items:center;gap:10px;flex-shrink:0;white-space:nowrap!important}}
.ftr-brand{{font-size:19px;font-weight:800;color:#FFFFFF}}
.ftr-src{{font-size:16px;font-weight:600;color:#CBD5E1}}
</style>
</head>
<body>
<div id="ea">
  {_fx_backdrop_svg(mode, w, h, ac, is16, show_fx)}
  {art_svg}
  <svg class="abs-fill" style="z-index:2;width:100%;height:100%" viewBox="0 0 {w} {h}" fill="none" dir="ltr">
    <rect x="14" y="14" width="{w - 28}" height="{h - 28}" rx="18" stroke="#F8FAFC" stroke-opacity=".14" stroke-width="1.5"/>
    <path d="M24 44V24H44M{rx1} 44V24H{rx2}M24 {by2}V{by1}H44M{rx1} {by2}V{by1}H{rx2}" stroke="#E62E45" stroke-opacity=".78" stroke-width="2.6"/>
  </svg>
  <header class="hdr">
    <div>
      <div class="fi gap10" style="flex-wrap:wrap">
        <div class="hdr-pill"><span class="pdot" style="background:{ac}"></span><span>عدد روز</span><span style="color:#94A3B8">•</span><span>{cat_txt}</span></div>
        <span class="iss-pill">شماره {fa(issue_txt)}</span>
      </div>
      {hdr_sub}
    </div>
    <div style="flex-shrink:0">{_brand_logo_img(44)}</div>
  </header>
  <main class="stage">{body_html}</main>
  <footer class="ftr">
    <div class="ftr-l"><span class="ftr-dot"></span><span class="ftr-tk">{ticker_txt}</span></div>
    <div class="ftr-r fm" dir="ltr"><span class="ftr-brand">@XGPedia</span><span style="color:#64748B">|</span><span class="ftr-src">{src_txt}</span></div>
  </footer>
</div>
</body>
</html>"""
