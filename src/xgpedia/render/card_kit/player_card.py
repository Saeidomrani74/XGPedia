"""کارت ماژولار «پروفایل فنی بازیکن» (XGPedia Player Card Studio — D54) — بازسازی ۱:۱ آفلاین.

ویژگی‌های ۱:۱ حفظ‌شده از `studio_templates/player_profile.html` + استاندارد ماژولار کامل XGPedia:
  - ۳ هویت بصری: `classic` (کلاسیک XG)، `gold` (ویژه MOTM طلایی)، `blueprint` (تاکتیکی آبی)
  - هدر سینمایی کامل (پرتره بازیکن با ماسک نرم، واترمارک شماره توخالی و نام خانوادگی، هاله رنگی، سپر باشگاه،
    چیپ‌های سن/قد/پا/ارزش، آمار کلیدی فصل، مینی‌زمین نقش و حلقه امتیاز ۱۰۰px XG Index) یا هدر فشرده
  - ۹ ماژول کاملاً مستقل و قابل چینش با پشتیبانی نیم‌عرض (`½`) و تمام‌عرض (`۱`)، تغییر ترتیب و ۵ قالب نام‌گذاری‌شده:
    1. `kpi`: نوار ۴ شاخص کلیدی در ۹۰ دقیقه (KPI Bento Strip)
    2. `percentiles`: صدک عملکرد ۰ تا ۹۹ نسبت به هم‌پستی‌ها
    3. `scout`: گزارش دیده‌بان و DNA تاکتیکی (نقاط قوت + نقطه بهبود)
    4. `radar`: رادار ۶ محوره پروفایل بازیکن در برابر میانگین لیگ (SVG)
    5. `pitchmap`: نقشه شوت xG و مناطق حرارتی در نیمه هجومی (SVG)
    6. `form`: موج فرم و امتیاز ۶ بازی اخیر با منحنی نرم و گرادینت رنگی (SVG)
    7. `xgchain`: سهم در زنجیره گل و خلق شوت (xGChain / xGBuildup)
    8. `duels`: ۴ حلقه پیشرفت مالکیت، دریبل و دوئل‌ها (SVG)
    9. `similar`: شباهت آماری بازیکنان (DNA Match با حلقه درصد و نوار)
"""
from __future__ import annotations

import math
from typing import Any

from src.xgpedia.render.card_kit.helpers import with_sample_badge, contrast_ink, esc, f1, f2, fa, luminance, smooth_spline
from src.xgpedia.render.cards import _brand_logo_data_uri
from src.xgpedia.render.studio_engine import build_embedded_font_css

PLAYER_DEFAULT_SLIDE = "slide1"
PLAYER_DEFAULT_HEADER = "full"

PLAYER_FORMATS: dict[str, tuple[int, int]] = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}

PLAYER_THEMES: dict[str, dict[str, str]] = {
    "classic": {"fa": "کلاسیک XG", "bg": "#0D1730", "accent": ""},
    "gold": {"fa": "ویژه MOTM", "bg": "#12101A", "accent": "#FBBF24"},
    "blueprint": {"fa": "تاکتیکی", "bg": "#071321", "accent": "#38BDF8"},
}

# (id, label_fa, header_mode, default_mods)
PLAYER_SLIDES: list[tuple[str, str, str, list[str]]] = [
    ("slide1", "اسلاید ۱: کارت پروفایل اصلی (پیشنهادی)", "full", ["kpi", "percentiles", "scout"]),
    ("slide2", "اسلاید ۲: رادار تاکتیکی و نقشه شوت xG", "compact", ["radar", "pitchmap"]),
    ("slide3", "اسلاید ۳: موج فرم و زنجیره تهدید (xGChain)", "compact", ["form", "xgchain"]),
    ("slide4", "اسلاید ۴: دوئل‌ها و شباهت آماری (DNA)", "compact", ["duels", "similar"]),
    ("slide5", "اسلاید ۵: نسخه جامع پوستر (ویترین کامل)", "full", ["kpi", "percentiles", "scout", "radar", "pitchmap"]),
]


def _pct_color(v: float) -> tuple[str, str]:
    if v >= 85:
        return "#10B981", "#34D399"
    if v >= 65:
        return "#0EA5E9", "#38BDF8"
    if v >= 45:
        return "#F59E0B", "#FBBF24"
    return "#E62E45", "#FB7185"


def _rat_col(v: float) -> tuple[str, str]:
    if v >= 9.0:
        return "#10B981", "#34D399"
    if v >= 8.5:
        return "#0EA5E9", "#38BDF8"
    if v >= 8.0:
        return "#F59E0B", "#FBBF24"
    if v >= 7.0:
        return "#F97316", "#FB923C"
    return "#E62E45", "#FB7185"


def _sim_col(v: float) -> tuple[str, str, str]:
    if v >= 92:
        return "#10B981", "#34D399", "تطابق نخبه"
    if v >= 88:
        return "#0EA5E9", "#38BDF8", "شباهت بالا"
    if v >= 84:
        return "#8B5CF6", "#A78BFA", "هم‌سبک"
    return "#F59E0B", "#FBBF24", "الگوی نزدیک"


def get_player_modules(
    p: dict[str, Any], slide: str = PLAYER_DEFAULT_SLIDE
) -> tuple[list[dict[str, Any]], list[str]]:
    """استخراج ۹ ماژول مستقل پروفایل بازیکن بر اساس دیتای واقعی موجود (قانون null ≠ 0)."""
    has_kpi = bool(isinstance(p.get("kpis"), list) and len(p["kpis"]) >= 2)
    has_pct = bool(isinstance(p.get("percentiles"), list) and len(p["percentiles"]) >= 2)
    sc = p.get("scout") if isinstance(p.get("scout"), dict) else None
    has_scout = bool(sc and sc.get("body"))
    has_radar = bool(isinstance(p.get("radarPlayer"), list) and len(p["radarPlayer"]) == 6)
    has_pmap = bool(isinstance(p.get("shots"), list) and len(p["shots"]) > 0)
    has_form = bool(isinstance(p.get("form"), list) and len(p["form"]) >= 2)
    xc = p.get("xgChain") if isinstance(p.get("xgChain"), dict) else None
    has_xc = bool(xc and xc.get("parts"))
    has_duels = bool(isinstance(p.get("duels"), list) and len(p["duels"]) >= 2)
    has_sim = bool(isinstance(p.get("similar"), list) and len(p["similar"]) >= 1)

    def_set = set(next((mids for sid, _, _, mids in PLAYER_SLIDES if sid == slide), ["kpi", "percentiles", "scout"]))
    specs = [
        ("kpi", "نوار شاخص‌های کلیدی (KPI Bento Strip)", has_kpi, False, "full"),
        ("percentiles", "صدک عملکرد در سطح لیگ (Percentile Bars)", has_pct, True, "half"),
        ("scout", "گزارش دیده‌بان و DNA تاکتیکی (Scouting Lens)", has_scout, True, "half"),
        ("radar", "رادار ۶ محوره پروفایل بازیکن", has_radar, True, "full"),
        ("pitchmap", "نقشه شوت xG و مناطق حرارتی (Pitch Map)", has_pmap, True, "full"),
        ("form", "موج فرم و امتیاز ۶ بازی اخیر", has_form, True, "full"),
        ("xgchain", "سهم در زنجیره گل و خلق شوت (xGChain)", has_xc, False, "full"),
        ("duels", "حلقه‌های مالکیت، دریبل و دوئل‌ها", has_duels, True, "full"),
        ("similar", "شباهت آماری بازیکنان (DNA Match)", has_sim, True, "full"),
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
        for m in mods[:2]:
            m["enabled"] = True
    return mods, missing


def _brand_logo_html() -> str:
    uri = _brand_logo_data_uri(mono=False)
    if uri:
        return f'<div class="pl-brand" dir="ltr"><img src="{uri}" alt="XGPedia" class="pl-brand-img"></div>'
    return '<div class="pl-brand" dir="ltr"><div class="fd pl-brand-txt"><span style="color:#E62E45">XG</span><span style="color:#F8FAFC">Pedia</span></div></div>'


def _crest_svg(p: dict[str, Any], sz: int) -> str:
    from src.xgpedia.providers.pl_badges_free import get_pl_badge_data_uri
    _luri = p.get("logoUrl") or get_pl_badge_data_uri(
        str(p.get("club") or p.get("team") or ""),
        tla_hint=str(p.get("code") or p.get("clubCode") or ""),
        fetch_network=False,
    )
    if _luri:
        return (
            f'<div style="width:{sz}px;height:{sz}px;flex-shrink:0;display:flex;align-items:center;justify-content:center;'
            f'border-radius:50%;background:rgba(7,13,29,.72);padding:{max(3, sz // 11)}px;filter:drop-shadow(0 8px 16px rgba(0,0,0,.5))">'
            f'<img src="{esc(_luri)}" alt="{esc(p.get("code") or "")}" style="width:100%;height:100%;object-fit:contain;display:block"/></div>'
        )
    c1 = str(p.get("color") or "#EF0107")
    c2 = str(p.get("secondary") or "#FFFFFF")
    cd = esc(str(p.get("code") or "FC")[:3].upper())
    u = f"c_{cd}_{sz}"
    d = "M90 16L150 40V88C150 128 124.5 156.5 90 166C55.5 156.5 30 128 30 88V40Z"
    pill_bg = "#0D1730" if luminance(c1) > 0.65 else "rgba(7,13,29,0.66)"
    return (
        f'<svg width="{sz}" height="{sz}" viewBox="0 0 180 180" fill="none" style="filter:drop-shadow(0 8px 16px rgba(0,0,0,.5));display:block;flex-shrink:0">'
        f'<defs><linearGradient id="g{u}" x1="20" y1="15" x2="160" y2="165" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{c2}" stop-opacity=".95"/><stop offset=".5" stop-color="{c1}" stop-opacity=".92"/><stop offset="1" stop-color="{c2}" stop-opacity=".75"/></linearGradient>'
        f'<clipPath id="cl{u}"><path d="{d}"/></clipPath></defs>'
        f'<path d="M90 12L154 38V88C154 130.5 127 160.5 90 170.5C53 160.5 26 130.5 26 88V38Z" fill="{c1}" fill-opacity=".22"/>'
        f'<g clip-path="url(#cl{u})"><rect x="25" y="12" width="130" height="158" fill="{c1}"/>'
        f'<path d="M25 112L155 56V84L25 140Z" fill="{c2}" fill-opacity=".28"/>'
        f'<path d="M90 16L150 40V58L90 34L30 58V40Z" fill="{c2}" fill-opacity=".90"/>'
        f'<ellipse cx="90" cy="30" rx="65" ry="28" fill="#fff" fill-opacity=".14"/></g>'
        f'<path d="{d}" stroke="url(#g{u})" stroke-width="5"/>'
        f'<rect x="42" y="68" width="96" height="48" rx="14" fill="{pill_bg}" stroke="{c2}" stroke-opacity=".55" stroke-width="2"/>'
        f'<text x="90" y="102" text-anchor="middle" fill="#fff" font-family="Space Grotesk,JetBrains Mono,sans-serif" font-weight="800" font-size="32" letter-spacing="2">{cd}</text></svg>'
    )


def _mini_pitch_svg(zones: list[dict[str, Any]], accent: str) -> str:
    blobs = "".join(
        f'<circle cx="{float(z.get("x", 75)) * 1.4:.1f}" cy="{float(z.get("y", 40)) * 0.86:.1f}" r="{float(z.get("r", 18)) * 0.85:.1f}" fill="{accent}" fill-opacity="{float(z.get("p", 0.7)) * 0.45:.2f}"/>'
        f'<circle cx="{float(z.get("x", 75)) * 1.4:.1f}" cy="{float(z.get("y", 40)) * 0.86:.1f}" r="{float(z.get("r", 18)) * 0.32:.1f}" fill="{accent}" stroke="#fff" stroke-width="1.5"/>'
        for z in (zones or [])
    )
    return (
        f'<svg width="136" height="82" viewBox="0 0 140 86" fill="none" style="flex-shrink:0;display:block">'
        f'<rect x="2" y="2" width="136" height="82" rx="10" fill="#071124" stroke="rgba(255,255,255,.16)" stroke-width="1.5"/>'
        f'<line x1="70" y1="2" x2="70" y2="84" stroke="rgba(255,255,255,.12)" stroke-width="1.2" stroke-dasharray="3 3"/>'
        f'<circle cx="70" cy="43" r="14" stroke="rgba(255,255,255,.12)" stroke-width="1.2"/>'
        f'<rect x="2" y="21" width="20" height="44" stroke="rgba(255,255,255,.12)" stroke-width="1.2"/>'
        f'<rect x="118" y="21" width="20" height="44" stroke="rgba(255,255,255,.12)" stroke-width="1.2"/>'
        f'{blobs}<path d="M126 78L132 74L126 70" stroke="#94A3B8" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )


def _portrait_or_jersey(p: dict[str, Any], accent: str, cls: str) -> str:
    port = str(p.get("portrait") or "").strip()
    if port.startswith("data:image/"):
        zm = float(p.get("imgZoom") or 1.0)
        iy = int(p.get("imgY") or 0)
        return f'<img src="{port}" alt="{esc(p.get("name", ""))}" class="{cls}" style="transform:scale({zm}) translateY({iy}px)">'
    col = str(p.get("color") or accent)
    num = esc(str(p.get("number"))) if p.get("number") not in (None, "", "None") else ""
    return (
        f'<svg viewBox="0 0 260 320" fill="none" style="width:86%;height:88%;display:block">'
        f'<circle cx="130" cy="84" r="38" fill="#1E293B" stroke="rgba(255,255,255,.22)" stroke-width="2"/>'
        f'<path d="M40 315 C46 218 82 180 108 170 L130 190 L152 170 C178 180 214 218 220 315 Z" fill="{col}" stroke="rgba(255,255,255,.3)" stroke-width="2.5"/>'
        f'<text x="130" y="268" text-anchor="middle" fill="{contrast_ink(col)}" font-family="Space Grotesk" font-weight="800" font-size="68">{num}</text></svg>'
    )


def _mod_hdr(title: str, right_html: str, bar_col: str, theme: str) -> str:
    if theme == "gold" and bar_col == "#E62E45":
        bar_col = "#FBBF24"
    elif theme == "blueprint" and bar_col == "#E62E45":
        bar_col = "#38BDF8"
    return (
        f'<div class="mh fbw"><div class="fi pl-g10">'
        f'<span class="pl-mbar" style="background:{bar_col}"></span>'
        f'<h3 class="mt">{esc(title)}</h3></div><div>{right_html}</div></div>'
    )


def _render_hero(p: dict[str, Any], theme: str, header_mode: str, is_wide: bool, is_dense: bool) -> str:
    c = str(p.get("color") or "#E62E45")
    accent = PLAYER_THEMES.get(theme, PLAYER_THEMES["classic"])["accent"] or c
    ovr = min(10.0, max(1.0, float(p.get("ovr") or 8.5)))
    circ = 2 * math.pi * 44
    dash_off = circ - (ovr / 10.0) * circ
    xgi90 = float(p.get("xgPer90") or 0) + float(p.get("xaPer90") or 0)

    if header_mode == "compact":
        return (
            f'<div class="hero-stage pl-hero-compact" style="background:linear-gradient(115deg,#0B162Ff2 0%,{c}26 60%,#091226f5 100%)">'
            f'<div class="fi pl-g14 pl-minw-0">'
            f'<div class="pl-hc-av" style="border-color:{accent}88">{_portrait_or_jersey(p, accent, "pl-hc-img")}</div>'
            f'<div class="pl-minw-0"><div class="fi pl-g10">' + (f'<span class="fm pl-hc-num" style="background:{accent}">{fa(p.get("number"))}#</span>' if p.get("number") not in (None, "", "None") else '') + ''
            f'<h1 class="pl-hc-name">{esc(p.get("name", ""))}</h1><span class="pl-hc-pos">{esc(p.get("pos", ""))}</span></div>'
            f'<div class="fi pl-g10" style="margin-top:6px;font-size:18px;font-weight:700;color:#CBD5E1">{_crest_svg(p, 26)}<b style="color:#fff">{esc(p.get("club", ""))}</b><span>•</span><span class="fm">{esc(p.get("roleEn", ""))}</span></div></div></div>'
            f'<div class="fi pl-g12" style="flex-shrink:0">'
            f'<div class="pl-hc-stats"><div><b>{fa(p.get("goals", 0))}</b><small>گل</small></div><div class="pl-sep"></div><div><b>{fa(p.get("assists", 0))}</b><small>پاس گل</small></div><div class="pl-sep"></div><div><b style="color:{accent}">{fa(f2(xgi90))}</b><small class="fm">xG+xA</small></div></div>'
            f'<div class="pl-hc-idx" style="border-color:{accent}aa"><div>{fa(f1(ovr))}</div><small class="fm" style="color:{accent}">XG INDEX</small></div></div></div>'
        )

    bio_chips = []
    if p.get("age") is not None:
        bio_chips.append(f'<span class="pl-bio-chip">سن: <b>{fa(p["age"])}</b></span>')
    if p.get("height"):
        bio_chips.append(f'<span class="pl-bio-chip">قد: <b class="fm">{esc(fa(p["height"]))}</b></span>')
    if p.get("foot"):
        bio_chips.append(f'<span class="pl-bio-chip">پای تخصصی: <b>{esc(p["foot"])}</b></span>')
    if p.get("value"):
        bio_chips.append(f'<span class="pl-bio-chip">ارزش: <b class="fm" dir="ltr" style="color:#6EE7B7;unicode-bidi:isolate">{esc(fa(p["value"]))}</b></span>')

    h_px = 345 if is_dense else (560 if is_wide else 440)
    raw_num = p.get("number")
    num_pad = str(raw_num).zfill(2) if raw_num not in (None, "", "None") else ""
    return (
        f'<div class="hero-stage" style="height:{h_px}px;background:linear-gradient(125deg,#112042 0%,#091329 54%,#060C1B 100%)">'
        f'<div class="pl-abs-fill" style="background:radial-gradient(circle at 22% 48%,{accent}48,transparent 52%),radial-gradient(circle at 82% 20%,{c}26,transparent 46%)"></div>'
        f'<div class="pl-abs-fill foil-sweep"></div>'
        f'<div class="fd outline-text pl-wm-num">{esc(num_pad)}</div>'
        f'<div class="fd pl-wm-sur" dir="ltr">{esc(p.get("surname") or p.get("enName", ""))}</div>'
        f'<div class="pl-port-wrap portrait-wrap-mask"><div class="pl-port-glow" style="background:{accent}"></div>{_portrait_or_jersey(p, accent, "pl-port-img portrait-mask")}</div>'
        f'<div class="pl-hero-right">'
        f'<div class="fi pl-g12">{_crest_svg(p, 52 if is_dense else 64)}<div class="pl-minw-0">'
        f'<div class="fi pl-g8"><span class="pl-pos-pill" style="background:{accent}2e;border-color:{accent}88">{esc(p.get("pos", ""))} • {esc(p.get("posCode", ""))}</span>'
        f'<span class="fm pl-role-pill">{esc(p.get("roleEn", ""))}</span></div>'
        f'<div class="pl-club-line"><span>{esc(p.get("club", ""))}</span> · <span style="color:#CBD5E1;font-weight:700">{esc(fa(p.get("apps", "")))}</span></div></div></div>'
        f'<div><div class="fi pl-g10"><span class="fm pl-en-name" style="color:{accent}">{esc(p.get("enName", ""))}</span><span class="pl-en-line" style="background:{accent}"></span></div>'
        f'<h1 class="pl-fa-name" style="font-size:{42 if is_dense else 52}px">{esc(p.get("name", ""))}</h1>'
        f'<div class="fi pl-g8" style="flex-wrap:wrap;margin-top:10px">{"".join(bio_chips)}</div></div>'
        f'<div class="fi pl-g12"><div class="pl-headline-box">'
        f'<div class="pl-hl-cell pl-hl-sep"><b>{fa(p.get("goals", 0))}</b><small>گل فصل</small></div>'
        f'<div class="pl-hl-cell pl-hl-sep"><b>{fa(p.get("assists", 0))}</b><small>پاس گل</small></div>'
        f'<div class="pl-hl-cell"><b style="color:{accent}">{fa(f2(xgi90))}</b><small class="fm">xG+xA/90</small></div></div>'
        + ("" if is_dense else f'<div class="pl-mpitch-box">{_mini_pitch_svg(p.get("pitchZones") or [], accent)}</div>')
        + f'</div></div>'
        f'<div class="pl-ovr-float"><div class="pl-ovr-ring"><svg width="106" height="106" viewBox="0 0 100 100" style="transform:rotate(-90deg)"><circle cx="50" cy="50" r="44" fill="none" stroke="rgba(255,255,255,.1)" stroke-width="6.5"/><circle cx="50" cy="50" r="44" fill="none" stroke="{accent}" stroke-width="7" stroke-linecap="round" stroke-dasharray="{f1(circ)}" stroke-dashoffset="{f1(dash_off)}"/></svg>'
        f'<div class="pl-ovr-in"><b>{fa(f1(ovr))}</b><small class="fm">XG INDEX</small></div></div>'
        f'<div class="pl-grade-tag" style="border-color:{accent}aa">رتبه <b style="color:{accent}">{esc(p.get("grade", "A"))}</b> • صدک {fa(p.get("pctOverall", 90))}</div></div></div>'
    )


@with_sample_badge
def render_player_html(
    p: dict[str, Any],
    *,
    slide: str = PLAYER_DEFAULT_SLIDE,
    header_mode: str | None = None,
    fmt: str = "4:5",
    theme: str = "classic",
    enabled_modules: list[str] | None = None,
    custom_modules: list[dict[str, Any]] | None = None,
) -> str:
    """تولید HTML کامل و ۱۰۰٪ آفلاین کارت ماژولار پروفایل فنی بازیکن (D54)."""
    w, h = PLAYER_FORMATS.get(fmt, PLAYER_FORMATS["4:5"])
    is_wide = fmt == "16:9"
    is_story = fmt == "9:16"
    is_dense = slide == "slide5"
    sl_meta = next((s for s in PLAYER_SLIDES if s[0] == slide), PLAYER_SLIDES[0])
    eff_hm = header_mode or sl_meta[2]
    th_meta = PLAYER_THEMES.get(theme, PLAYER_THEMES["classic"])
    accent = th_meta["accent"] or str(p.get("color") or "#E62E45")

    if custom_modules is not None:
        mods = [dict(m) for m in custom_modules if m.get("enabled")]
    else:
        all_mods, _ = get_player_modules(p, slide)
        if enabled_modules is not None:
            eset = set(enabled_modules)
            mods = [m for m in all_mods if m["id"] in eset]
        else:
            mods = [m for m in all_mods if m["enabled"]]

    spans: list[str] = []
    half_run = 0
    for idx, m in enumerate(mods):
        if m.get("span") != "half" or not m.get("can_half", False):
            half_run = 0
            spans.append("pl-span-full")
        else:
            half_run += 1
            nxt_half = (idx + 1 < len(mods)) and (mods[idx + 1].get("span") == "half") and mods[idx + 1].get("can_half", False)
            if not nxt_half and half_run % 2 == 1:
                half_run = 0
                spans.append("pl-span-full")
            else:
                spans.append("pl-span-half")

    mods_html = ""
    for m, sc in zip(mods, spans):
        mid = m["id"]
        if mid == "kpi":
            cards = "".join(
                f'<div class="pl-kcard"><div class="pl-kbar" style="background:{k.get("accent", "#E62E45")}"></div>'
                f'<div class="fbw"><span class="pl-klbl">{esc(k.get("label", ""))}</span><span class="pl-kdel">{esc(fa(k.get("delta", "")))}</span></div>'
                f'<div><div class="pl-kval">{esc(fa(k.get("val", "")))}</div><div class="fm pl-ksub">{esc(k.get("sub", ""))}</div></div>'
                f'<div class="pl-ktrack"><div style="width:{int(k.get("pct", 80))}%;background:{k.get("accent", "#E62E45")};height:100%"></div></div></div>'
                for k in (p.get("kpis") or [])[:4]
            )
            mods_html += f'<div class="xm {sc}">' + _mod_hdr("شاخص‌های کلیدی عملکرد (در ۹۰ دقیقه)", '<span dir="ltr" class="fm pl-sub-tag">PER 90 · VS PEERS</span>', "#E62E45", theme) + f'<div class="pl-kgrid">{cards}</div></div>'

        elif mid == "percentiles":
            rows = []
            for it in (p.get("percentiles") or [])[:6]:
                pv = int(it.get("pct") or 50)
                c1, c2 = _pct_color(pv)
                rows.append(
                    f'<div class="fcol pl-g5"><div class="fbw" style="font-size:18px"><span style="font-weight:800;color:#F1F5F9">{esc(it.get("label", ""))}</span>'
                    f'<div class="fi pl-g8"><span style="font-weight:900;color:#CBD5E1">{esc(fa(it.get("val", "")))}</span>'
                    f'<span class="pl-ppill" style="background:{c1}2b;color:{c2};border-color:{c1}66">{fa(pv)}</span></div></div>'
                    f'<div class="pct-track"><div class="pct-mid"></div><div class="pct-fill" style="width:{pv}%;background:linear-gradient(90deg,{c1},{c2})"></div></div></div>'
                )
            mods_html += f'<div class="xm {sc}">' + _mod_hdr("صدک عملکرد نسبت به هم‌پستی‌ها", '<span dir="ltr" class="fm pl-sub-tag">PERCENTILE 0–99</span>', "#34D399", theme) + f'<div class="fcol pl-g10" style="flex:1;justify-content:center">{"".join(rows)}</div></div>'

        elif mid == "scout":
            sv = p.get("scout") if isinstance(p.get("scout"), dict) else {}
            chips = "".join(f'<span class="pl-schip">✓ {esc(s)}</span>' for s in (sv.get("strengths") or [])[:3])
            mods_html += (
                f'<div class="xe {sc}">'
                f'<svg class="pl-sc-wm" viewBox="0 0 240 160" fill="none" stroke="#DCE6F8" stroke-width="2.5"><rect x="2" y="2" width="236" height="156" rx="8"/><line x1="120" y1="2" x2="120" y2="158"/><circle cx="120" cy="80" r="32"/></svg>'
                f'<div class="fcol" style="position:relative;z-index:10;justify-content:space-between;gap:10px;flex:1"><div>'
                + _mod_hdr("گزارش دیده‌بان و DNA تاکتیکی", '<span dir="ltr" class="fm" style="font-size:15px;font-weight:800;color:#FCD34D">SCOUTING LENS</span>', "#FBBF24", theme)
                + f'<h4 style="font-size:22px;font-weight:900;color:#FCD34D;line-height:1.35;margin-bottom:6px">{esc(fa(sv.get("title", "")))}</h4>'
                f'<p style="font-size:18.5px;line-height:1.55;color:#F1F5F9;font-weight:600">{esc(fa(sv.get("body", "")))}</p></div>'
                f'<div class="fcol pl-g8"><div class="fi pl-g6" style="flex-wrap:wrap">{chips}</div>'
                f'<div class="pl-watch"><b>نقطه بهبود:</b> {esc(fa(sv.get("watchout", "—")))}</div></div>'
                f'<div class="pl-sc-foot"><span class="pl-dot-red"></span><span>{esc(fa(sv.get("tag", "")))}</span></div></div></div>'
            )

        elif mid == "radar":
            lbs = p.get("radarLabels") or ["۱", "۲", "۳", "۴", "۵", "۶"]
            p_v = [float(x) for x in (p.get("radarPlayer") or [75] * 6)]
            a_v = [float(x) for x in (p.get("radarAvg") or [60] * 6)]
            cx, cy, R = 420.0, 195.0, 112.0
            dx = R * 0.866 + 24.0

            def _pts(vs: list[float]) -> list[tuple[float, float]]:
                out = []
                for idx_r, v in enumerate(vs[:6]):
                    ang = (idx_r * 60 - 90) * math.pi / 180.0
                    rad = max(15.0, min(100.0, v)) / 100.0 * R
                    out.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
                return out

            def _ring(k: float) -> str:
                return " ".join(f"{f1(cx + R * k * math.cos((i * 60 - 90) * math.pi / 180.0))},{f1(cy + R * k * math.sin((i * 60 - 90) * math.pi / 180.0))}" for i in range(6))

            pc, ac_pts = _pts(p_v), _pts(a_v)
            p_poly = " ".join(f"{f1(x)},{f1(y)}" for x, y in pc)
            a_poly = " ".join(f"{f1(x)},{f1(y)}" for x, y in ac_pts)
            lbl_pos = [(cx, 26, "middle"), (cx + dx, cy - R * 0.5 - 6, "start"), (cx + dx, cy + R * 0.5 - 2, "start"), (cx, cy + R + 30, "middle"), (cx - dx, cy + R * 0.5 - 2, "end"), (cx - dx, cy - R * 0.5 - 6, "end")]
            lbl_svg = "".join(
                f'<g><text x="{f1(x)}" y="{f1(y)}" text-anchor="{an}" fill="#fff" font-family="Vazirmatn" font-weight="800" font-size="22">{esc(lbs[i])}</text>'
                f'<text x="{f1(x)}" y="{f1(y + 28)}" text-anchor="{an}" font-family="Vazirmatn" font-weight="900" font-size="20"><tspan fill="{accent}">{fa(int(p_v[i]))}</tspan><tspan fill="#64748B"> / {fa(int(a_v[i]))}</tspan></text></g>'
                for i, (x, y, an) in enumerate(lbl_pos)
            )
            dots = "".join(f'<circle cx="{f1(x)}" cy="{f1(y)}" r="5.5" fill="{accent}" stroke="#fff" stroke-width="2.2"/>' for x, y in pc)
            leg = f'<div class="fi pl-g10" style="font-size:15px;font-weight:800"><span style="color:{accent}">● {esc(p.get("name", ""))}</span><span style="color:#94A3B8">● میانگین لیگ</span></div>'
            mods_html += (
                f'<div class="xm {sc}">'
                + _mod_hdr("رادار ۶ محوره پروفایل بازیکن", leg, "#E62E45", theme)
                + f'<div class="fc" style="flex:1" dir="ltr"><svg style="width:100%;height:auto;max-height:290px" viewBox="0 0 840 385" fill="none">'
                + '<g stroke="rgba(255,255,255,.15)" stroke-width="1.5">' + "".join(f'<polygon points="{_ring(k)}"/>' for k in (1, 0.75, 0.5, 0.25))
                + f'<line x1="{cx}" y1="{cy - R}" x2="{cx}" y2="{cy + R}"/><line x1="{cx + R * 0.866:.1f}" y1="{cy - R * 0.5:.1f}" x2="{cx - R * 0.866:.1f}" y2="{cy + R * 0.5:.1f}"/><line x1="{cx + R * 0.866:.1f}" y1="{cy + R * 0.5:.1f}" x2="{cx - R * 0.866:.1f}" y2="{cy - R * 0.5:.1f}"/></g>'
                f'<polygon points="{a_poly}" fill="#94A3B8" fill-opacity=".14" stroke="#94A3B8" stroke-width="2.5" stroke-dasharray="6 5"/>'
                f'<polygon points="{p_poly}" fill="{accent}" fill-opacity=".32" stroke="{accent}" stroke-width="4"/>{dots}{lbl_svg}</svg></div></div>'
            )

        elif mid == "pitchmap":
            shots = p.get("shots") or []
            tot_xg = sum(float(sh.get("xg") or 0) for sh in shots)
            g_cnt = sum(1 for sh in shots if sh.get("r") == "G")
            heat_svg = "".join(
                f'<ellipse cx="{float(z.get("x", 80)) * 5.2 - 220:.1f}" cy="{float(z.get("y", 30)) * 3.1:.1f}" rx="{float(z.get("rx", 15)) * 3.2:.1f}" ry="{float(z.get("ry", 14)) * 2.8:.1f}" fill="url(#hmG)" opacity="{z.get("o", 0.4)}"/>'
                for z in (p.get("heatZones") or [])
            )
            shot_svg = []
            for sh in shots:
                sx = float(sh.get("x", 80)) * 5.2 - 220
                sy = float(sh.get("y", 40)) * 3.1
                rad = max(6.0, min(18.0, 5.0 + float(sh.get("xg") or 0.1) * 26.0))
                if sh.get("r") == "G":
                    shot_svg.append(f'<circle cx="{f1(sx)}" cy="{f1(sy)}" r="{f1(rad)}" fill="#10B981" fill-opacity=".88" stroke="#fff" stroke-width="2.2"/>')
                elif sh.get("r") == "OT":
                    shot_svg.append(f'<circle cx="{f1(sx)}" cy="{f1(sy)}" r="{f1(rad)}" fill="{accent}" fill-opacity=".35" stroke="{accent}" stroke-width="2.4"/>')
                else:
                    shot_svg.append(f'<circle cx="{f1(sx)}" cy="{f1(sy)}" r="{f1(rad)}" fill="#64748B" fill-opacity=".28" stroke="#94A3B8" stroke-width="1.6"/>')
            mods_html += (
                f'<div class="xm {sc}">'
                + _mod_hdr("نقشه شوت xG و مناطق اثرگذاری", f'<span style="font-size:16px;font-weight:900;color:#6EE7B7">{fa(g_cnt)} گل از {fa(f2(tot_xg))} xG</span>', "#34D399", theme)
                + f'<div class="fc" style="flex:1" dir="ltr"><svg style="width:100%;height:auto;max-height:265px" viewBox="0 0 320 310" fill="none">'
                f'<defs><radialGradient id="hmG" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="{accent}" stop-opacity=".9"/><stop offset="1" stop-color="{accent}" stop-opacity="0"/></radialGradient></defs>'
                f'<rect x="8" y="8" width="304" height="294" rx="14" fill="#071326" stroke="rgba(255,255,255,.15)" stroke-width="1.8"/>'
                f'<g stroke="rgba(255,255,255,.13)" stroke-width="1.5"><line x1="8" y1="155" x2="312" y2="155" stroke-dasharray="5 5" opacity=".45"/><rect x="196" y="48" width="116" height="214"/><rect x="266" y="96" width="46" height="118"/><path d="M196 112 A48 48 0 0 0 196 198"/><circle cx="242" cy="155" r="3" fill="rgba(255,255,255,.27)"/><rect x="308" y="124" width="6" height="62" rx="2" fill="#E62E45" fill-opacity=".7" stroke="#fff" stroke-width="1.2"/></g>'
                f'{heat_svg}{"".join(shot_svg)}</svg></div>'
                f'<div class="fbw pl-pm-leg"><span style="color:#6EE7B7">● گل</span><span style="color:{accent}">● در چارچوب</span><span style="color:#94A3B8">● خارج چارچوب</span><span>اندازه دایره = xG</span></div></div>'
            )

        elif mid == "form":
            fm = p.get("form") or []
            vals = [float(x.get("rat") or 7.0) for x in fm]
            avg = sum(vals) / len(vals) if vals else 7.5
            ac1, ac2 = _rat_col(avg)
            W, H, px, py = 860.0, 194.0, 52.0, 40.0
            pW, pH = W - px * 2, H - py - 22.0
            pts = []
            for i, f_it in enumerate(fm):
                r_v = max(6.2, min(10.0, float(f_it.get("rat") or 7.0)))
                x = px + (i / max(1, len(fm) - 1)) * pW
                y = py + pH - ((r_v - 6.2) / (10.0 - 6.2)) * pH
                pts.append((x, y, f_it, _rat_col(r_v)))
            curve = smooth_spline([(x, y) for x, y, _, _ in pts], 0.24)
            stops = "".join(f'<stop offset="{f1(i / max(1, len(pts) - 1) * 100)}%" stop-color="{c2}"/>' for i, (_, _, _, (_, c2)) in enumerate(pts))
            nodes = "".join(
                f'<g><circle cx="{f1(x)}" cy="{f1(y)}" r="14" fill="{c2}" fill-opacity=".22"/><circle cx="{f1(x)}" cy="{f1(y)}" r="7.5" fill="{c1}" stroke="#fff" stroke-width="2.5"/>'
                f'<rect x="{f1(x - 25)}" y="{f1(y - 38)}" width="50" height="25" rx="8" fill="#060D1E" stroke="{c1}" stroke-width="1.6"/>'
                f'<text x="{f1(x)}" y="{f1(y - 20)}" text-anchor="middle" fill="{c2}" font-family="Vazirmatn" font-weight="900" font-size="18">{fa(f1(float(it.get("rat") or 7)))}</text>'
                + (f'<text x="{f1(x)}" y="{f1(y + 28)}" text-anchor="middle" fill="{c2}" font-family="Space Grotesk" font-weight="800" font-size="15">{(str(it["g"]) + "G ") if it.get("g") else ""}{(str(it["a"]) + "A") if it.get("a") else ""}</text>' if (it.get("g") or it.get("a")) else "")
                + f'<rect x="{f1(x - 31)}" y="{H + 6:.0f}" width="62" height="32" rx="10" fill="#071022" stroke="{c1}88" stroke-width="1.6"/><rect x="{f1(x - 16)}" y="{H + 35:.0f}" width="32" height="3" rx="1.5" fill="{c2}"/>'
                f'<text x="{f1(x)}" y="{H + 27:.0f}" text-anchor="middle" fill="#F1F5F9" font-family="Space Grotesk,JetBrains Mono" font-weight="800" font-size="16">{esc(it.get("opp", ""))}</text></g>'
                for x, y, it, (c1, c2) in pts
            )
            mods_html += (
                f'<div class="xm {sc}">'
                + _mod_hdr("موج فرم و امتیاز ۶ بازی اخیر", f'<span class="pl-ppill" style="background:{ac1}28;border-color:{ac1}66;color:{ac2};font-size:18px">میانگین {fa(f2(avg))}</span>', "#34D399", theme)
                + f'<div class="fc" style="flex:1" dir="ltr"><svg style="width:100%;height:auto;max-height:240px" viewBox="0 0 {W:.0f} {H + 48:.0f}" fill="none">'
                f'<defs><linearGradient id="fwG" x1="0%" y1="0%" x2="100%" y2="0%">{stops}</linearGradient>'
                f'<linearGradient id="fwM" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#fff" stop-opacity=".42"/><stop offset="100%" stop-color="#fff" stop-opacity="0"/></linearGradient>'
                f'<mask id="fwK"><rect x="0" y="0" width="{W:.0f}" height="{H:.0f}" fill="url(#fwM)"/></mask></defs>'
                f'<g stroke="rgba(255,255,255,.1)" stroke-width="1.4" stroke-dasharray="6 6"><line x1="{px}" y1="{py}" x2="{W - px}" y2="{py}"/><line x1="{px}" y1="{py + pH * 0.5}" x2="{W - px}" y2="{py + pH * 0.5}"/><line x1="{px}" y1="{py + pH}" x2="{W - px}" y2="{py + pH}"/></g>'
                f'<path d="{curve} L {pts[-1][0]:.1f} {py + pH:.1f} L {pts[0][0]:.1f} {py + pH:.1f} Z" fill="url(#fwG)" mask="url(#fwK)"/>'
                f'<path d="{curve}" stroke="url(#fwG)" stroke-width="5.5" stroke-linecap="round" fill="none"/>{nodes}</svg></div></div>'
            )

        elif mid == "xgchain":
            xc = p.get("xgChain") or {}
            parts = xc.get("parts") or []
            segs = "".join(f'<div class="ps" style="width:{int(s.get("p", 0))}%;background:{s.get("c", "#38BDF8")};color:{contrast_ink(str(s.get("c", "#38BDF8")))}">{fa(s.get("p", 0)) + "٪" if int(s.get("p", 0)) >= 12 else ""}</div>' for s in parts)
            pills = "".join(f'<div class="pl-xcpill"><span class="pl-xcdot" style="background:{s.get("c", "#38BDF8")}"></span><span>{esc(s.get("l", ""))}</span><b style="margin-right:auto">{fa(s.get("p", 0))}٪</b></div>' for s in parts)
            mods_html += (
                f'<div class="xm {sc}">'
                + _mod_hdr("سهم در زنجیره گل و خلق شوت (xGChain)", f'<div class="fi pl-g8" style="font-size:16px;font-weight:900"><span style="color:#7DD3FC">xGChain: {fa(f2(xc.get("chain", 0)))}</span><span style="color:#FCD34D">xGBuildup: {fa(f2(xc.get("buildup", 0)))}</span></div>', "#38BDF8", theme)
                + f'<div class="fcol pl-g10" style="margin:auto 0"><div class="pc">{segs}</div><div class="pl-xcgrid">{pills}</div></div></div>'
            )

        elif mid == "duels":
            r_rad = 34.0
            circ = 2 * math.pi * r_rad
            dcards = "".join(
                f'<div class="pl-dcard"><div class="pl-dring"><svg width="76" height="76" viewBox="0 0 80 80" style="transform:rotate(-90deg)"><circle cx="40" cy="40" r="34" fill="none" stroke="rgba(255,255,255,.1)" stroke-width="7"/><circle cx="40" cy="40" r="34" fill="none" stroke="{d.get("color", "#38BDF8")}" stroke-width="7" stroke-linecap="round" stroke-dasharray="{f1(circ)}" stroke-dashoffset="{f1(circ - (float(d.get("val", 50)) / 100.0) * circ)}"/></svg><span class="pl-dval">{fa(d.get("val", 0))}٪</span></div>'
                f'<div><div style="font-size:18px;font-weight:900;color:#fff">{esc(d.get("label", ""))}</div><div style="font-size:13.5px;font-weight:700;color:{d.get("color", "#38BDF8")};margin-top:4px">بالاتر از میانگین</div></div></div>'
                for d in (p.get("duels") or [])[:4]
            )
            mods_html += f'<div class="xm {sc}">' + _mod_hdr("مالکیت، دریبل و دوئل‌ها", '<span dir="ltr" class="fm pl-sub-tag">SUCCESS RATES</span>', "#38BDF8", theme) + f'<div class="pl-dgrid">{dcards}</div></div>'

        elif mid == "similar":
            rr = 24.0
            cc = 2 * math.pi * rr
            scards = []
            for idx_s, sp in enumerate((p.get("similar") or [])[:3], 1):
                sv = int(sp.get("sim") or 85)
                c1, c2, tl = _sim_col(sv)
                off = cc - (sv / 100.0) * cc
                scards.append(
                    f'<div class="pl-sim-card" style="background:linear-gradient(100deg,{c1}1f 0%,#071022f0 44%,#060d1ef7 100%);border-color:{c1}59;border-right:5px solid {c2}">'
                    f'<div class="fi pl-g10 pl-minw-0"><div class="pl-sim-rk" style="background:{c1}22;border-color:{c1}66"><span class="fm" style="font-size:11px;color:{c2}">#{fa(idx_s)}</span><span class="fm" style="font-size:13.5px;color:#fff">{esc(sp.get("club", ""))}</span></div>'
                    f'<div class="pl-minw-0"><div class="fi pl-g8"><span style="font-size:20px;font-weight:900;color:#fff">{esc(sp.get("name", ""))}</span><span class="pl-sim-tl" style="background:{c1}26;color:{c2};border-color:{c1}55">{tl}</span></div>'
                    f'<div style="font-size:14.5px;font-weight:700;color:#CBD5E1;margin-top:2px">{esc(sp.get("trait", ""))}</div>'
                    f'<div class="pl-ktrack" style="margin-top:6px"><div style="width:{sv}%;height:100%;background:linear-gradient(90deg,{c1},{c2})"></div></div></div></div>'
                    f'<div class="pl-sring"><svg width="60" height="60" viewBox="0 0 60 60" style="transform:rotate(-90deg)"><circle cx="30" cy="30" r="24" fill="#050b18" stroke="rgba(255,255,255,.1)" stroke-width="5.5"/><circle cx="30" cy="30" r="24" fill="none" stroke="{c2}" stroke-width="5.5" stroke-linecap="round" stroke-dasharray="{f1(cc)}" stroke-dashoffset="{f1(off)}"/></svg><span class="pl-sval" style="color:{c2}">{fa(sv)}٪</span></div></div>'
                )
            mods_html += f'<div class="xm {sc}">' + _mod_hdr("شباهت آماری بازیکنان (DNA Match)", '<span dir="ltr" class="fm pl-sub-tag">COSINE SIMILARITY</span>', "#A78BFA", theme) + f'<div class="fcol pl-g10" style="margin:auto 0">{"".join(scards)}</div></div>'

    hero_html = _render_hero(p, theme, eff_hm, is_wide, is_dense)
    pad_top = "139px" if is_story else ("22px" if is_wide else "24px")
    pad_bot = "171px" if is_story else ("16px" if is_wide else "20px")
    crh_d = f"M24 44V24H44M{w - 24} 44V24H{w - 44}M24 {h - 44}V{h - 24}H44M{w - 24} {h - 44}V{h - 24}H{w - 44}"
    font_css = build_embedded_font_css()

    _pnum = p.get("number")
    foot_num_tag = f" · #{esc(_pnum)}" if _pnum not in (None, "", "None") else ""
    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<style>
{font_css}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:{w}px;height:{h}px;overflow:hidden;font-family:'Vazirmatn',system-ui,sans-serif;background:{th_meta["bg"]};color:#F8FAFC;font-feature-settings:"tnum";font-variant-numeric:tabular-nums}}
.fm{{font-family:'JetBrains Mono','Space Grotesk',monospace}}.fd{{font-family:'Space Grotesk',sans-serif}}
.fi{{display:flex;align-items:center}}.fc{{display:flex;align-items:center;justify-content:center}}.fbw{{display:flex;align-items:center;justify-content:space-between}}.fcol{{display:flex;flex-direction:column}}
.pl-g5{{gap:5px}}.pl-g6{{gap:6px}}.pl-g8{{gap:8px}}.pl-g10{{gap:10px}}.pl-g12{{gap:12px}}.pl-g14{{gap:14px}}.pl-minw-0{{min-width:0;flex:1}}
.pl-canvas{{position:relative;width:{w}px;height:{h}px;background:{th_meta["bg"]};overflow:hidden;display:flex;flex-direction:column;justify-content:space-between;padding:{pad_top} 0 {pad_bot}}}
.pl-ambient{{position:absolute;inset:0;pointer-events:none;z-index:0;background:radial-gradient(circle at 20% 28%,{accent}38,transparent 48%),radial-gradient(circle at 86% 24%,{p.get("color", "#E62E45")}28,transparent 46%),radial-gradient(circle at 50% 85%,#e62e451e,transparent 55%)}}
.pl-bg-svg{{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0}}
.pl-scan{{position:absolute;inset:0;pointer-events:none;z-index:0;background:repeating-linear-gradient(to bottom,rgba(255,255,255,.016) 0 1px,transparent 1px 4px)}}
.pl-header{{position:relative;z-index:10;padding:12px 36px 8px;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-shrink:0}}
.pl-comp-pill{{padding:5px 16px;border-radius:999px;font-size:22px;font-weight:900;display:flex;align-items:center;gap:8px;border:1px solid rgba(255,255,255,.18);background:rgba(21,35,71,.9);color:#F8FAFC}}
.pl-round-pill{{padding:5px 16px;border-radius:999px;font-size:19px;font-weight:800;border:1px solid rgba(230,46,69,.5);background:rgba(230,46,69,.18);color:#FF6B7F}}
.pl-badge-pill{{padding:4px 14px;border-radius:999px;font-size:18px;font-weight:800;border:1px solid rgba(52,211,153,.45);background:rgba(16,185,129,.2);color:#34D399}}
.pl-brand-img{{height:48px;width:auto;display:block}}.pl-brand-txt{{font-size:34px;font-weight:800;line-height:1}}
.pl-stage-v{{position:relative;z-index:10;flex:1;padding:8px 40px;display:flex;flex-direction:column;gap:14px;overflow:hidden;min-height:0}}
.pl-stage-w{{position:relative;z-index:10;flex:1;padding:8px 40px;display:grid;grid-template-columns:5fr 7fr;gap:24px;align-items:stretch;overflow:hidden;min-height:0}}
.pl-mods-grid{{flex:1;display:grid;grid-template-columns:1fr 1fr;gap:12px;min-height:0;overflow:hidden;align-content:stretch}}
.pl-span-full{{grid-column:1 / -1;min-width:0}}.pl-span-half{{grid-column:span 1;min-width:0}}
.hero-stage{{position:relative;border-radius:28px;overflow:hidden;border:1.5px solid rgba(255,255,255,.14);box-shadow:0 22px 56px -14px rgba(0,0,0,.72);flex-shrink:0}}
.pl-abs-fill{{position:absolute;inset:0;pointer-events:none}}.foil-sweep{{background:linear-gradient(118deg,transparent 25%,rgba(255,255,255,.06) 44%,rgba(251,191,36,.11) 50%,rgba(255,255,255,.04) 56%,transparent 75%)}}
.outline-text{{-webkit-text-stroke:1.5px rgba(255,255,255,.14);color:transparent}}.pl-wm-num{{position:absolute;bottom:-22px;right:20px;font-size:210px;font-weight:800;line-height:1;pointer-events:none}}
.pl-wm-sur{{position:absolute;top:12px;left:24px;font-size:84px;font-weight:800;line-height:1;color:rgba(255,255,255,.045);letter-spacing:.06em;pointer-events:none}}
.pl-port-wrap{{position:absolute;left:0;top:0;bottom:0;width:47%;display:flex;align-items:flex-end;justify-content:center;overflow:hidden;pointer-events:none}}
.portrait-wrap-mask{{-webkit-mask-image:linear-gradient(to right,#000 0%,#000 68%,transparent 100%);mask-image:linear-gradient(to right,#000 0%,#000 68%,transparent 100%)}}
.portrait-mask{{-webkit-mask-image:linear-gradient(to bottom,#000 0%,#000 76%,transparent 100%);mask-image:linear-gradient(to bottom,#000 0%,#000 76%,transparent 100%)}}
.pl-port-glow{{position:absolute;bottom:16px;left:50%;transform:translateX(-50%);width:320px;height:320px;border-radius:999px;filter:blur(48px);opacity:.42}}
.pl-port-img{{position:relative;z-index:10;height:105%;width:100%;object-fit:cover;object-position:top}}
.pl-hero-right{{position:relative;z-index:20;height:100%;width:62%;padding:18px 26px 18px 16px;display:flex;flex-direction:column;justify-content:space-between}}
.pl-pos-pill{{padding:4px 14px;border-radius:999px;font-size:17px;font-weight:900;color:#fff;border:1px solid}}.pl-role-pill{{padding:4px 12px;border-radius:999px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.15);font-size:15px;font-weight:800;color:#E2E8F0}}
.pl-club-line{{font-size:20px;font-weight:800;color:#E2E8F0;margin-top:5px}}.pl-en-name{{font-size:17px;font-weight:800;letter-spacing:.18em}}.pl-en-line{{height:2px;width:40px;border-radius:99px;display:inline-block}}
.pl-fa-name{{font-weight:900;color:#fff;line-height:1.06;margin-top:4px;text-shadow:0 6px 18px rgba(0,0,0,.65)}}
.pl-bio-chip{{padding:4px 12px;border-radius:12px;background:rgba(7,16,34,.9);border:1px solid rgba(255,255,255,.14);font-size:17px;font-weight:700;color:#CBD5E1}}.pl-bio-chip b{{color:#fff}}
.pl-headline-box{{flex:1;display:grid;grid-template-columns:repeat(3,1fr);border-radius:16px;background:rgba(6,13,30,.9);border:1px solid rgba(255,255,255,.14);padding:10px 12px}}
.pl-hl-cell{{text-align:center}}.pl-hl-cell b{{display:block;font-size:28px;font-weight:900;color:#fff;line-height:1}}.pl-hl-cell small{{display:block;font-size:13px;font-weight:700;color:#94A3B8;margin-top:4px}}.pl-hl-sep{{border-left:1px solid rgba(255,255,255,.1)}}
.pl-mpitch-box{{border-radius:16px;background:rgba(6,13,30,.9);border:1px solid rgba(255,255,255,.14);padding:6px}}
.pl-ovr-float{{position:absolute;top:18px;left:18px;z-index:20;display:flex;flex-direction:column;align-items:center}}
.pl-ovr-ring{{position:relative;width:106px;height:106px;border-radius:999px;background:rgba(6,13,30,.92);display:flex;align-items:center;justify-content:center;box-shadow:0 12px 32px rgba(0,0,0,.75)}}
.pl-ovr-in{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center}}.pl-ovr-in b{{font-size:36px;font-weight:900;color:#fff;line-height:1}}.pl-ovr-in small{{font-size:11px;font-weight:800;color:#CBD5E1;letter-spacing:.1em;margin-top:2px}}
.pl-grade-tag{{margin-top:8px;padding:4px 14px;border-radius:999px;background:rgba(7,16,34,.95);border:1px solid;font-size:14.5px;font-weight:900;color:#fff}}
.pl-hero-compact{{padding:12px 22px;display:flex;align-items:center;justify-content:space-between;gap:16px}}.pl-hc-av{{width:78px;height:78px;border-radius:16px;overflow:hidden;border:2px solid;background:#060D1E;flex-shrink:0}}
.pl-hc-img{{width:100%;height:100%;object-fit:cover;object-position:top}}.pl-hc-num{{padding:2px 10px;border-radius:8px;font-size:17px;font-weight:800;color:#fff}}.pl-hc-name{{font-size:32px;font-weight:900;color:#fff;line-height:1}}.pl-hc-pos{{padding:2px 12px;border-radius:999px;background:rgba(255,255,255,.1);font-size:16px;font-weight:700;color:#E2E8F0}}
.pl-hc-stats{{display:flex;align-items:center;gap:12px;padding:8px 16px;border-radius:16px;background:rgba(6,13,30,.85);border:1px solid rgba(255,255,255,.12);text-align:center}}.pl-hc-stats b{{display:block;font-size:24px;font-weight:900;color:#fff;line-height:1}}.pl-hc-stats small{{font-size:12px;color:#94A3B8}}.pl-sep{{width:1px;height:30px;background:rgba(255,255,255,.12)}}
.pl-hc-idx{{padding:8px 16px;border-radius:16px;border:2px solid;background:linear-gradient(145deg,#0B152C,#050B19);text-align:center}}.pl-hc-idx div{{font-size:32px;font-weight:900;color:#fff;line-height:1}}.pl-hc-idx small{{font-size:11px;font-weight:800}}
.xm,.xe{{position:relative;border-radius:24px;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;box-shadow:0 14px 36px -10px rgba(0,0,0,.55),inset 0 1px 0 rgba(255,255,255,.1)}}
.xm{{background:linear-gradient(165deg,#101d3be0,#080f22f5);border:1.5px solid rgba(248,250,252,.14);padding:14px 20px}}
.xe{{background:linear-gradient(155deg,#132142eb,#090f20f7);border:1.5px solid rgba(127,166,232,.25);padding:16px 22px}}
.mh{{padding-bottom:8px;margin-bottom:10px;border-bottom:1px solid rgba(255,255,255,.12)}}.pl-mbar{{width:8px;height:24px;border-radius:99px;display:inline-block}}.mt{{font-size:23px;font-weight:900;color:#fff}}.pl-sub-tag{{font-size:15px;font-weight:800;color:#94A3B8}}
.pl-kgrid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}.pl-kcard{{position:relative;border-radius:16px;background:rgba(7,16,34,.9);border:1px solid rgba(255,255,255,.12);padding:12px;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden}}
.pl-kbar{{position:absolute;top:0;left:0;right:0;height:3.5px}}.pl-klbl{{font-size:15px;font-weight:800;color:#CBD5E1}}.pl-kdel{{padding:2px 8px;border-radius:8px;font-size:13px;font-weight:900;background:rgba(16,185,129,.15);color:#6EE7B7}}
.pl-kval{{font-size:32px;font-weight:900;color:#fff;line-height:1;margin-top:6px}}.pl-ksub{{font-size:12px;font-weight:700;color:#94A3B8;margin-top:4px}}.pl-ktrack{{height:6px;width:100%;border-radius:99px;background:rgba(255,255,255,.1);overflow:hidden;margin-top:8px}}
.pct-track{{height:14px;border-radius:99px;background:rgba(255,255,255,.08);position:relative;overflow:hidden}}.pct-mid{{position:absolute;top:0;bottom:0;left:50%;width:1.5px;background:rgba(255,255,255,.25);z-index:2}}.pct-fill{{height:100%;border-radius:99px}}
.pl-ppill{{min-width:42px;text-align:center;padding:2px 8px;border-radius:8px;font-size:15px;font-weight:900;border:1px solid}}
.pl-sc-wm{{position:absolute;left:16px;bottom:16px;width:140px;opacity:.07;pointer-events:none}}.pl-schip{{padding:4px 12px;border-radius:10px;background:rgba(16,185,129,.15);border:1px solid rgba(52,211,153,.35);color:#A7F3D0;font-size:15px;font-weight:800}}
.pl-watch{{padding:6px 12px;border-radius:10px;background:rgba(245,158,11,.12);border:1px solid rgba(251,191,36,.3);color:#FDE68A;font-size:15px;font-weight:700}}.pl-sc-foot{{padding-top:8px;border-top:1px solid rgba(255,255,255,.12);display:flex;align-items:center;gap:8px;font-size:16px;font-weight:800;color:#E2E8F0}}
.pl-pm-leg{{padding-top:6px;border-top:1px solid rgba(255,255,255,.1);font-size:14px;font-weight:700;color:#CBD5E1}}
.pc{{width:100%;height:40px;border-radius:999px;overflow:hidden;display:flex;background:#0f172aeb;border:1.5px solid rgba(255,255,255,.16)}}.ps{{height:100%;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:17px}}
.pl-xcgrid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}.pl-xcpill{{display:flex;align-items:center;gap:8px;padding:8px 12px;border-radius:12px;background:rgba(7,16,34,.85);border:1px solid rgba(255,255,255,.1);font-size:15px;font-weight:700}}.pl-xcdot{{width:11px;height:11px;border-radius:99px;flex-shrink:0}}
.pl-dgrid{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:auto 0}}.pl-dcard{{display:flex;align-items:center;gap:14px;padding:12px;border-radius:16px;background:rgba(7,16,34,.85);border:1px solid rgba(255,255,255,.12)}}
.pl-dring{{position:relative;width:76px;height:76px;display:flex;align-items:center;justify-content:center;flex-shrink:0}}.pl-dval{{position:absolute;font-size:20px;font-weight:900;color:#fff}}
.pl-sim-card{{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 14px;border-radius:16px;border:1px solid}}.pl-sim-rk{{width:48px;height:48px;border-radius:12px;border:1px solid;display:flex;flex-direction:column;align-items:center;justify-content:center;flex-shrink:0}}
.pl-sim-tl{{padding:2px 8px;border-radius:6px;border:1px solid;font-size:12.5px;font-weight:800}}.pl-sring{{position:relative;width:60px;height:60px;display:flex;align-items:center;justify-content:center;flex-shrink:0}}.pl-sval{{position:absolute;font-size:16px;font-weight:900}}
.pl-dot-red{{width:10px;height:10px;border-radius:99px;background:#E62E45;display:inline-block;flex-shrink:0}}
.pl-footer{{position:relative;z-index:10;padding:10px 44px 10px;flex-shrink:0}}.pl-foot-line{{border-top:1px solid rgba(255,255,255,.12);margin-bottom:8px}}
.pl-foot-tag{{font-size:18px;font-weight:800;letter-spacing:.14em;color:#F1F5F9;text-transform:uppercase}}.pl-foot-h{{font-size:20px;font-weight:800;color:#fff}}.pl-foot-s{{font-size:17px;font-weight:600;color:#CBD5E1}}

footer, footer .fbw, footer .cf-row, footer .fi, footer .cf-left, footer .cf-right, .xg-footer, .foot-row, .card-footer{{flex-wrap:nowrap!important;white-space:nowrap!important;min-width:0!important;}}
footer span, footer div, .pl-foot-tag, .pl-foot-s, .in-foot-tag, .pr-foot-tag, .st-foot-tag, .cf-tag{{white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;min-width:0!important;}}
</style>
</head>
<body>
<div class="pl-canvas">
  <div class="pl-ambient"></div>
  <svg class="pl-bg-svg" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid slice" fill="none">
    <defs>
      <pattern id="tg" width="54" height="54" patternUnits="userSpaceOnUse"><path d="M54 0H0v54" stroke="#F8FAFC" stroke-opacity=".052"/></pattern>
      <radialGradient id="rf" cx="50%" cy="24%" r="48%"><stop offset="0" stop-color="#E62E45" stop-opacity=".22"/><stop offset=".55" stop-color="#E62E45" stop-opacity=".05"/><stop offset="1" stop-color="#E62E45" stop-opacity="0"/></radialGradient>
    </defs>
    <rect width="100%" height="100%" fill="url(#tg)"/>
    <rect x="12" y="12" width="{w - 24}" height="{h - 24}" rx="18" stroke="#F8FAFC" stroke-opacity=".11" stroke-width="1.5"/>
    <g stroke="#F8FAFC" stroke-opacity=".085" stroke-width="1.5"><line x1="{w / 2}" y1="12" x2="{w / 2}" y2="{h - 12}" stroke-dasharray="8 8"/><circle cx="{w / 2}" cy="290" r="155"/></g>
    <circle cx="{w / 2}" cy="290" r="260" fill="url(#rf)"/><circle cx="{w / 2}" cy="290" r="220" stroke="#E62E45" stroke-opacity=".16" stroke-width="1.2" stroke-dasharray="4 6"/>
    <path d="{crh_d}" stroke="#E62E45" stroke-opacity=".6" stroke-width="2.2"/>
  </svg>
  <div class="pl-scan"></div>
  <header class="pl-header">
    <div class="fi pl-g10">
      <div class="pl-comp-pill">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#E62E45" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
        <span>{esc(p.get("competition", "پروفایل بازیکن"))}</span>
      </div>
      <span class="pl-round-pill">{esc(fa(p.get("round", "")))}</span>
      <span class="pl-badge-pill">{esc(fa(p.get("badge", "")))}</span>
    </div>
    {_brand_logo_html()}
  </header>
  <main class="{'pl-stage-w' if is_wide else 'pl-stage-v'}">
    {f'<section class="fcol" style="justify-content:center">{hero_html}</section><section class="pl-mods-grid">{mods_html}</section>' if is_wide else f'{hero_html}<section class="pl-mods-grid">{mods_html}</section>'}
  </main>
  <footer class="pl-footer">
    <div class="pl-foot-line"></div>
    <div class="fbw">
      <div class="fi pl-g10"><span class="pl-dot-red"></span><span dir="ltr" class="fm pl-foot-tag">{esc(str(p.get("leagueEn", "PREMIER LEAGUE")).upper())} {esc(p.get("season", "26/27"))} • PLAYER PROFILE{foot_num_tag}</span></div>
      <div class="fi pl-g10 fm" dir="ltr"><span class="pl-foot-h">@XGPedia</span><span style="color:#64748B">|</span><span class="pl-foot-s">{esc(p.get("source", "XGPedia Index"))}</span></div>
    </div>
  </footer>
</div>
</body>
</html>"""


def build_player_caption(p: dict[str, Any]) -> str:
    """تولید کپشن فارسی تمیز برای کارت پروفایل فنی بازیکن."""
    sc = p.get("scout") if isinstance(p.get("scout"), dict) else {}
    xgi = float(p.get("xgPer90") or 0) + float(p.get("xaPer90") or 0)
    parts = [
        f"⭐️ <b>پروفایل فنی بازیکن | {esc(p.get('name', ''))} ({esc(p.get('club', ''))})</b>",
        f"📊 شاخص XGPedia: {fa(f1(float(p.get('ovr') or 8.0)))} ({p.get('grade', 'A')}) | {fa(p.get('goals', 0))} گل و {fa(p.get('assists', 0))} پاس گل | xG+xA/90: {fa(f2(xgi))}",
    ]
    if sc.get("body"):
        parts.append(fa(str(sc["body"]).strip()))
    return "\n\n".join(parts)
