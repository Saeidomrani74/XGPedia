"""کارت ماژولار «کارت بازیکن FC27» (XGPedia Player Card Studio — FC27 Chrono-Telemetry Edition — D56) — بازسازی ۱:۱ آفلاین.

بازسازی دقیق و ۱:۱ از `studio_templates/player_fc27.html` با:
  - فریم چهارگوشه قرمز یکپارچه (`pad_top=24/22/139`, `pad_bot=20/16/171`, `header 12px 36px 8px`, `stage 8px 40px`, `footer 10px 44px 10px`)
  - پرتوهای نوری حجمی صحنه (`.stage-beam-l`, `.stage-beam-r`)، تایپوگرافی شبحی پشت کارت (`.giant-ghost-text`) و زمین تاکتیکی SVG
  - کارت ۲۰ضلعی FC27 (`544×780` با `clip-path` دقیق، بافت کربن، هاله رنگی، فویل هولوگرافیک، پایه مداری `.fc-pedestal` و قاب SVG دولایه با باله‌های کناری و نگین الماسی بالا)
  - ۶ اسکین کلکسیونی دقیق (`signature`, `persian` با اسطرلاب پارسی، `icon`, `tots`, `ucl`, `future`)
  - پرچم SVG ملیت‌ها + سپر سه‌بعدی باشگاه + ۲ نشان شش‌ضلعی `PlayStyle+` + ۶ کپسول آمار با ۵ LED درخشان + نشان سپر XGPedia در پایین کارت
  - ۳ چیدمان اصلی (`spotlight` شوی کرونو-تله‌متری با ۴ HUD کناری، `dossier` پرونده تحلیلی، `poster` پوستر کلکسیونی) + کنترل ماژولار مستقل (`fc_card`, `per90`, `index_form`, `radar`, `heatmap`, `verdict`) و قانون `null ≠ 0`.
"""
from __future__ import annotations

import math
from typing import Any

from src.xgpedia.providers.injury_free import transliterate_player_name_fa
from src.xgpedia.render.card_kit.helpers import esc, f1, f2, fa, luminance
from src.xgpedia.render.cards import _brand_logo_data_uri
from src.xgpedia.render.studio_engine import build_embedded_font_css


def _brand_xg_red_data_uri() -> str | None:
    """بارگذاری آفلاین فایل رسمی برند `brand/logo/svg/logo-xg-red.svg` به‌صورت Data URI."""
    import base64
    from src.xgpedia.config import ROOT
    svg_p = ROOT / "brand" / "logo" / "svg" / "logo-xg-red.svg"
    if svg_p.exists() and svg_p.stat().st_size > 100:
        try:
            return f"data:image/svg+xml;base64,{base64.b64encode(svg_p.read_bytes()).decode('ascii')}"
        except Exception:
            return None
    return None


FC27_FORMATS: dict[str, tuple[int, int]] = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}

# (id, label_fa, layout_mode, default_mods)
FC27_SLIDES: list[tuple[str, str, str, list[str]]] = [
    ("slide1", "حالت ۱: شوی کرونو-تله‌متری (پیشنهادی)", "spotlight", ["fc_card", "radar", "per90", "heatmap", "index_form", "verdict"]),
    ("slide2", "حالت ۲: پرونده تحلیلی کامل (رادار + هیت‌مپ)", "dossier", ["fc_card", "radar", "heatmap", "index_form", "verdict"]),
    ("slide3", "حالت ۳: پوستر کلکسیونی خالص (فوکوس کارت)", "poster", ["fc_card"]),
]


def _persian_astrolabe(cx: float, cy: float, r: float, c1: str, c2: str) -> str:
    def _sq(rad: float, rot: float) -> str:
        return " ".join(
            f"{cx + rad * math.cos(math.radians(i * 90 + rot)):.1f},{cy + rad * math.sin(math.radians(i * 90 + rot)):.1f}"
            for i in range(4)
        )
    ticks = "".join(
        f'<line x1="{cx + r * 1.06 * math.cos(math.radians(i * 10)):.1f}" y1="{cy + r * 1.06 * math.sin(math.radians(i * 10)):.1f}" '
        f'x2="{cx + r * (1.16 if i % 3 == 0 else 1.11) * math.cos(math.radians(i * 10)):.1f}" '
        f'y2="{cy + r * (1.16 if i % 3 == 0 else 1.11) * math.sin(math.radians(i * 10)):.1f}" '
        f'stroke="{c1 if i % 3 == 0 else c2}" stroke-opacity="{".65" if i % 3 == 0 else ".3"}" stroke-width="{"1.6" if i % 3 == 0 else "1"}"/>'
        for i in range(36)
    )
    return (
        '<g fill="none">'
        f'<circle cx="{cx}" cy="{cy}" r="{r * 1.18:.1f}" stroke="{c1}" stroke-opacity=".18" stroke-width="1"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{r * 1.02:.1f}" stroke="{c2}" stroke-opacity=".35" stroke-width="1.3" stroke-dasharray="6 5"/>'
        f'<polygon points="{_sq(r * 0.95, 0)}" stroke="{c1}" stroke-opacity=".34" stroke-width="1.4"/>'
        f'<polygon points="{_sq(r * 0.95, 45)}" stroke="{c2}" stroke-opacity=".38" stroke-width="1.4"/>'
        f'<polygon points="{_sq(r * 0.66, 22.5)}" stroke="{c1}" stroke-opacity=".22" stroke-width="1"/>'
        f'<polygon points="{_sq(r * 0.66, 67.5)}" stroke="{c1}" stroke-opacity=".22" stroke-width="1"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{r * 0.52:.1f}" stroke="{c1}" stroke-opacity=".25" stroke-width="1" stroke-dasharray="3 6"/>'
        f"{ticks}</g>"
    )


def _tier_motif(tid: str, b1: str, b2: str) -> str:
    if tid == "signature":
        return _persian_astrolabe(324, 244, 152, b1, b2)
    if tid == "persian":
        return _persian_astrolabe(324, 244, 162, "#FDE68A", "#22D3EE")
    if tid == "icon":
        rays = "".join(
            f'<line x1="{324 + math.cos(math.radians(i * 22.5)) * 58:.1f}" y1="{244 + math.sin(math.radians(i * 22.5)) * 58:.1f}" '
            f'x2="{324 + math.cos(math.radians(i * 22.5)) * 205:.1f}" y2="{244 + math.sin(math.radians(i * 22.5)) * 205:.1f}" '
            f'stroke-width="{"1.4" if i % 2 == 0 else ".8"}"/>'
            for i in range(16)
        )
        return f'<g opacity=".36" stroke="{b2}" fill="none">{rays}<circle cx="324" cy="244" r="134" stroke="{b1}" stroke-width="1.6"/><circle cx="324" cy="244" r="176" stroke-dasharray="4 7" stroke-width="1.2"/></g>'
    if tid == "tots":
        return (
            f'<g opacity=".38" stroke="{b2}" fill="none">'
            '<polygon points="324,78 468,160 468,324 324,406 180,324 180,160" stroke-width="1.8"/>'
            '<polygon points="324,108 440,174 440,310 324,376 208,310 208,174" stroke="#FACC15" stroke-width="1.4" stroke-dasharray="8 6"/>'
            f'<path d="M80 120 L215 255 L95 415 M475 110 L350 250 L482 412" stroke="{b1}" stroke-width="1.2" opacity=".55"/></g>'
        )
    if tid == "ucl":
        return (
            f'<g opacity=".40" stroke="{b1}" fill="none">'
            '<polygon points="324,84 358,188 468,188 380,252 414,356 324,292 234,356 268,252 180,188 290,188" stroke-width="1.6"/>'
            f'<circle cx="324" cy="236" r="158" stroke="{b2}" stroke-width="1.5" stroke-dasharray="5 7"/>'
            '<circle cx="324" cy="236" r="202" stroke="#38BDF8" stroke-width="1" opacity=".5"/></g>'
        )
    return (
        f'<g opacity=".38" stroke="{b2}" fill="none">'
        '<path d="M150 410 L308 92 M200 430 L358 112 M250 450 L408 132 M300 470 L458 152" stroke-width="1.6"/>'
        f'<circle cx="324" cy="240" r="150" stroke="{b1}" stroke-width="1.5" stroke-dasharray="10 6"/>'
        '<rect x="204" y="120" width="240" height="240" rx="28" transform="rotate(45 324 240)" stroke="#38BDF8" stroke-width="1.2" opacity=".6"/></g>'
    )


TIERS: dict[str, dict[str, str]] = {
    "signature": {
        "id": "signature", "name": "طلایی ویژه XGPedia", "tag": "TOTW • SIGNATURE",
        "bg": "linear-gradient(156deg,#1B2A52 0%,#091126 42%,#280B1C 76%,#050914 100%)",
        "b1": "#FDE68A", "b2": "#E62E45", "b3": "#F59E0B",
        "glow": "#E62E45", "sec": "#F59E0B", "accent": "#FBBF24", "foil": "rgba(251,191,36,.55)",
        "mm": "#FEF08A", "mb": "#E62E45", "pbg": "#f59e0b29", "pbd": "#fbbf247a", "ptxt": "#FDE68A",
    },
    "persian": {
        "id": "persian", "name": "فیروزه و طلای پارسی", "tag": "PERSIAN EDITION • 1/1",
        "bg": "linear-gradient(156deg,#083549 0%,#091A34 44%,#0C2D3F 76%,#040B18 100%)",
        "b1": "#67E8F9", "b2": "#F59E0B", "b3": "#06B6D4",
        "glow": "#06B6D4", "sec": "#F59E0B", "accent": "#22D3EE", "foil": "rgba(103,232,249,.58)",
        "mm": "#CFFAFE", "mb": "#F59E0B", "pbg": "#06b6d42b", "pbd": "#67e8f97a", "ptxt": "#A5F3FC",
    },
    "icon": {
        "id": "icon", "name": "آیکون اسطوره‌ای", "tag": "FC27 ICON • LEGEND",
        "bg": "linear-gradient(156deg,#2F291D 0%,#121520 44%,#241F16 78%,#080A11 100%)",
        "b1": "#FFFBEB", "b2": "#E5C37A", "b3": "#B48636",
        "glow": "#E5C37A", "sec": "#F8FAFC", "accent": "#FDE68A", "foil": "rgba(254,243,199,.60)",
        "mm": "#FEF3C7", "mb": "#C89742", "pbg": "#fef3c726", "pbd": "#fde68a7a", "ptxt": "#FEF3C7",
    },
    "tots": {
        "id": "tots", "name": "تیم منتخب فصل", "tag": "TEAM OF THE SEASON",
        "bg": "linear-gradient(156deg,#0B3364 0%,#071532 45%,#0E2658 78%,#040A19 100%)",
        "b1": "#BAE6FD", "b2": "#38BDF8", "b3": "#FACC15",
        "glow": "#38BDF8", "sec": "#FACC15", "accent": "#0EA5E9", "foil": "rgba(56,189,248,.60)",
        "mm": "#E0F2FE", "mb": "#38BDF8", "pbg": "#38bdf826", "pbd": "#38bdf87a", "ptxt": "#7DD3FC",
    },
    "ucl": {
        "id": "ucl", "name": "شب‌های اروپا", "tag": "CHAMPIONS LEAGUE",
        "bg": "linear-gradient(156deg,#2D1260 0%,#0E1030 45%,#2E0E46 78%,#07081B 100%)",
        "b1": "#F0ABFC", "b2": "#A855F7", "b3": "#38BDF8",
        "glow": "#A855F7", "sec": "#EC4899", "accent": "#C084FC", "foil": "rgba(240,171,252,.58)",
        "mm": "#F5D0FE", "mb": "#A855F7", "pbg": "#a855f72b", "pbd": "#c084fc7a", "ptxt": "#E9D5FF",
    },
    "future": {
        "id": "future", "name": "پدیده و ستاره آینده", "tag": "FUTURE STAR • PRODIGY",
        "bg": "linear-gradient(156deg,#083B37 0%,#071828 45%,#0C3032 78%,#040D18 100%)",
        "b1": "#A7F3D0", "b2": "#10B981", "b3": "#38BDF8",
        "glow": "#10B981", "sec": "#34D399", "accent": "#2DD4BF", "foil": "rgba(52,211,153,.58)",
        "mm": "#D1FAE5", "mb": "#10B981", "pbg": "#10b98129", "pbd": "#34d3997a", "ptxt": "#6EE7B7",
    },
}


_POS_FA_FC27 = {
    "ST": "مهاجم", "CF": "مهاجم", "FW": "مهاجم", "FWD": "مهاجم",
    "RW": "وینگر راست", "LW": "وینگر چپ", "W": "وینگر",
    "CAM": "هافبک هجومی", "CM": "هافبک", "CDM": "هافبک دفاعی", "MID": "هافبک",
    "CB": "مدافع مرکزی", "RB": "مدافع راست", "LB": "مدافع چپ", "DEF": "مدافع",
    "GK": "دروازه‌بان",
}


def _clean_role_fa(role_raw: str) -> str:
    import re as _re
    s = str(role_raw or "ستاره تیم").strip()
    s = _re.sub(r"\s*[•·\-]?\s*[A-Za-z][A-Za-z0-9\s\-]*\+*\s*$", "", s).strip()
    return (s + " ++") if s else "ستاره تیم ++"

PLAYSTYLES: dict[str, tuple[str, str]] = {
    "finesse": ("کات‌دار+", '<path d="M5 17C8 8 15 6 19 6M19 6l-4-2.5M19 6l-2.5 4" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'),
    "technical": ("تکنیکی+", '<circle cx="12" cy="12" r="7" stroke="currentColor" stroke-width="2.1"/><path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="1.8" stroke-dasharray="2 2"/>'),
    "rapid": ("انفجاری+", '<path d="M13 2L4 14h7l-1 8 10-12h-7l0-8z" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round"/>'),
    "powershot": ("شوت موشکی+", '<circle cx="15" cy="12" r="5" stroke="currentColor" stroke-width="2.2"/><path d="M3 9h5M2 12h6M3 15h5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>'),
    "incisive": ("پاس برنده+", '<path d="M4 19L19 5M19 5h-7M19 5v7" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"/>'),
    "quickstep": ("شتاب لحظه‌ای+", '<path d="M4 17l5-5 3 3 8-8M15 7h5v5" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"/>'),
    "trivela": ("بیرون پا+", '<path d="M6 18c0-7 5-12 12-12M14 6h4v4" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"/>'),
    "acrobatic": ("آکروباتیک+", '<path d="M12 3l2.6 5.5L20 9.3l-4 4 .9 5.7-4.9-2.7-4.9 2.7.9-5.7-4-4 5.4-.8z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>'),
}

FLAGS: dict[str, str] = {
    "IR": '<rect width="36" height="8" fill="#239F40"/><rect y="8" width="36" height="8" fill="#FFFFFF"/><rect y="16" width="36" height="8" fill="#DA0000"/><circle cx="18" cy="12" r="2.6" fill="#DA0000"/>',
    "ENG": '<rect width="36" height="24" fill="#FFFFFF"/><rect x="15" width="6" height="24" fill="#CE1124"/><rect y="9" width="36" height="6" fill="#CE1124"/>',
    "ESP": '<rect width="36" height="6" fill="#AA151B"/><rect y="6" width="36" height="12" fill="#F1BF00"/><rect y="18" width="36" height="6" fill="#AA151B"/><rect x="9" y="9" width="4" height="6" rx="1" fill="#AA151B"/>',
    "UZB": '<rect width="36" height="7.5" fill="#0099B5"/><rect y="7.5" width="36" height="1" fill="#CE1126"/><rect y="8.5" width="36" height="7" fill="#FFFFFF"/><rect y="15.5" width="36" height="1" fill="#CE1126"/><rect y="16.5" width="36" height="7.5" fill="#1EB53A"/><circle cx="7" cy="4" r="2.2" fill="#FFFFFF"/>',
    "POR": '<rect width="14" height="24" fill="#006600"/><rect x="14" width="22" height="24" fill="#FF0000"/><circle cx="14" cy="12" r="4.2" fill="#FFCC00" stroke="#006600" stroke-width="1"/>',
    "FRA": '<rect width="12" height="24" fill="#002395"/><rect x="12" width="12" height="24" fill="#FFFFFF"/><rect x="24" width="12" height="24" fill="#ED2939"/>',
    "BRA": '<rect width="36" height="24" fill="#009C3B"/><polygon points="18,3 33,12 18,21 3,12" fill="#FFDF00"/><circle cx="18" cy="12" r="4.5" fill="#002776"/>',
    "ARG": '<rect width="36" height="8" fill="#74ACDF"/><rect y="8" width="36" height="8" fill="#FFFFFF"/><rect y="16" width="36" height="8" fill="#74ACDF"/><circle cx="18" cy="12" r="2.6" fill="#F6B40E"/>',
}


def _stat_color(v: int) -> str:
    return "#34D399" if v >= 90 else ("#38BDF8" if v >= 82 else ("#FBBF24" if v >= 72 else "#F43F5E"))


def _club_crest(p: dict[str, Any], size: int = 48) -> str:
    from src.xgpedia.providers.pl_badges_free import get_pl_badge_data_uri
    _luri = p.get("logoUrl") or get_pl_badge_data_uri(str(p.get("club") or ""), tla_hint=str(p.get("code") or ""), fetch_network=False)
    if _luri:
        return (
            f'<div style="width:{size}px;height:{size}px;display:flex;align-items:center;justify-content:center;'
            f'border-radius:50%;background:rgba(7,13,29,.78);padding:4px;filter:drop-shadow(0 6px 12px #00000080)">'
            f'<img src="{esc(_luri)}" style="width:100%;height:100%;object-fit:contain;display:block" alt="{esc(p.get("code",""))}"/></div>'
        )
    c1 = esc(p.get("color") or "#E62E45")
    c2 = esc(p.get("secondary") or "#FFFFFF")
    cd = esc(str(p.get("code") or "XGP")[:3].upper())
    uid = f"cc_{size}_{cd}"
    d = "M90 16L150 40V88C150 128 124.5 156.5 90 166C55.5 156.5 30 128 30 88V40Z"
    bg = "#0D1730" if luminance(p.get("color") or "#E62E45") > 0.65 else "#070d1dc4"
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 180 180" fill="none" style="filter:drop-shadow(0 8px 16px rgba(0,0,0,.65));flex-shrink:0">'
        f'<defs><linearGradient id="g{uid}" x1="20" y1="15" x2="160" y2="165" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{c2}" stop-opacity=".95"/><stop offset=".5" stop-color="{c1}" stop-opacity=".95"/><stop offset="1" stop-color="{c2}" stop-opacity=".75"/></linearGradient>'
        f'<clipPath id="cl{uid}"><path d="{d}"/></clipPath></defs>'
        f'<path d="M90 12L154 38V88C154 130.5 127 160.5 90 170.5C53 160.5 26 130.5 26 88V38Z" fill="{c1}" fill-opacity=".28"/>'
        f'<g clip-path="url(#cl{uid})"><rect x="25" y="12" width="130" height="158" fill="{c1}"/>'
        f'<path d="M25 112L155 56V84L25 140Z" fill="{c2}" fill-opacity=".28"/>'
        f'<path d="M90 16L150 40V58L90 34L30 58V40Z" fill="{c2}" fill-opacity=".9"/></g>'
        f'<path d="{d}" stroke="url(#g{uid})" stroke-width="5.5"/>'
        f'<rect x="40" y="68" width="100" height="46" rx="13" fill="{bg}" stroke="{c2}" stroke-opacity=".58" stroke-width="2"/>'
        f'<text x="90" y="101" text-anchor="middle" fill="#fff" font-family="Space Grotesk,JetBrains Mono,sans-serif" font-weight="800" font-size="31" letter-spacing="2">{cd}</text></svg>'
    )


def _flag_svg(code: str, w: int = 42, h: int = 27) -> str:
    inner = FLAGS.get((code or "ENG").upper(), FLAGS["ENG"])
    return f'<svg width="{w}" height="{h}" viewBox="0 0 36 24" style="border-radius:6px;border:1px solid rgba(255,255,255,.3);flex-shrink:0">{inner}</svg>'


def get_player_fc27_modules(data: dict[str, Any], slide: str = "slide1") -> tuple[list[dict[str, Any]], list[str]]:
    has_card = isinstance(data.get("stats"), dict) and data.get("ovr") is not None
    has_p90 = isinstance(data.get("p90"), dict) and any(v is not None for v in (data.get("p90") or {}).values())
    has_form = bool(data.get("form")) or data.get("xgpIndex") is not None
    has_radar = isinstance(data.get("radar"), list) and len(data.get("radar") or []) >= 6
    has_heat = isinstance(data.get("heat"), list) and len(data.get("heat") or []) > 0
    has_verdict = bool(data.get("verdictBody") or data.get("verdictTitle"))

    sl_def = next((mids for sid, _, _, mids in FC27_SLIDES if sid == slide), ["fc_card", "radar", "per90", "heatmap", "index_form", "verdict"])
    def_set = set(sl_def)
    specs = [
        ("fc_card", "کارت ۲۰ضلعی FC27 و ۶ ویژگی LED", has_card, False, "full"),
        ("radar", "رادار صدکی ۶ محوره (HUD)", has_radar, True, "half"),
        ("per90", "تله‌متری در ۹۰ دقیقه (xG/xA/xT/SCA)", has_p90, True, "half"),
        ("heatmap", "نقشه حرارتی مناطق فعالیت", has_heat, True, "half"),
        ("index_form", "شاخص XGPedia و روند فرم ۵ بازی", has_form, True, "half"),
        ("verdict", "لنز تاکتیکی XGPedia (Scouting DNA)", has_verdict, True, "full"),
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


def _render_fc27_shield(p: dict[str, Any], t: dict[str, str], scale: float = 0.90) -> str:
    uid = f"fc_{t['id']}"
    st = p.get("stats") or {}
    stat_meta = [("pac", "PAC", "سرعت"), ("sho", "SHO", "شوت"), ("pas", "PAS", "پاس"),
                 ("dri", "DRI", "دریبل"), ("def", "DEF", "دفاع"), ("phy", "PHY", "فیزیک")]
    caps = []
    for k, en, lbl in stat_meta:
        val = max(1, min(99, int(st.get(k) or 75)))
        col = _stat_color(val)
        lit = min(5, max(1, math.ceil((val - 35) / 12.0)))
        leds = "".join(
            f'<div class="led-seg" style="{f"background:{col};box-shadow:0 0 6px {col}" if idx < lit else ""}"></div>'
            for idx in range(5)
        )
        caps.append(
            '<div class="stat-cap">'
            f'<span class="sc-en fd">{en}</span>'
            f'<span class="sc-val">{fa(val)}</span>'
            f'<div class="led-row">{leds}</div>'
            f'<span class="sc-fa">{lbl}</span></div>'
        )

    ps_keys = list(p.get("ps") or ["finesse", "technical"])[:2]
    ps_html = ""
    for pk in ps_keys:
        pname, psvg = PLAYSTYLES.get(str(pk).lower(), PLAYSTYLES["finesse"])
        ps_html += (
            '<div class="ps-item">'
            f'<div class="fc-ps-hex" style="background:linear-gradient(155deg,{t["b1"]},{t["b2"]});padding:2px">'
            f'<div class="fc-ps-hex inner" style="color:{t["b1"]}"><svg width="20" height="20" viewBox="0 0 24 24" fill="none">{psvg}</svg></div></div>'
            f'<span class="ps-lbl" dir="rtl">{pname}</span></div>'
        )

    img_src = p.get("img") or p.get("photoUrl") or ""
    num_str = str(p.get("num") or 7).zfill(2) if p.get("num") not in (None, "", 0) else ""
    img_z = float(p.get("imgZoom") or 1.06)
    img_x = int(p.get("imgX") or 0)
    img_y = int(p.get("imgY") or 6)
    portrait_html = (
        f'<img src="{img_src}" alt="{esc(p.get("name", ""))}" class="fc-portrait" style="transform:translate({img_x}px,{img_y}px) scale({img_z})"/>'
        if img_src
        else ""
    )
    meta_line = f'<span class="fm">{esc(p.get("en") or "")}</span>'
    if p.get("num") not in (None, "", 0):
        meta_line += f'<span class="op">•</span><span class="fm" style="color:{t["b1"]}">#{p["num"]}</span>'
    if p.get("foot"):
        meta_line += f'<span class="op">•</span><span dir="rtl" class="foot">{esc(p["foot"])}</span>'

    cstyle = f"--c-bg:{t['bg']};--c-glow:{t['glow']};--c-sec:{t['sec']};--c-accent:{t['accent']};--c-foil:{t['foil']};--c-metal-mid:{t['mm']};--c-metal-bot:{t['mb']}"
    w_box, h_box = round(544 * scale), round(780 * scale)

    return (
        f'<div class="fc-stage" style="width:{w_box}px;height:{h_box}px">'
        f'<div style="transform:scale({scale});transform-origin:center center;position:relative">'
        f'<div class="fc-back-halo" style="{cstyle}"></div>'
        f'<svg class="fc-pedestal" viewBox="0 0 548 90" fill="none">'
        f'<defs><radialGradient id="ped_{uid}" cx="50%" cy="50%" r="50%">'
        f'<stop offset="0%" stop-color="{t["glow"]}" stop-opacity=".72"/><stop offset="55%" stop-color="{t["b1"]}" stop-opacity=".22"/><stop offset="100%" stop-color="{t["glow"]}" stop-opacity="0"/></radialGradient></defs>'
        f'<ellipse cx="274" cy="50" rx="246" ry="28" fill="url(#ped_{uid})"/>'
        f'<ellipse cx="274" cy="50" rx="212" ry="18" stroke="{t["b1"]}" stroke-opacity=".46" stroke-width="1.5" stroke-dasharray="10 8"/>'
        f'<ellipse cx="274" cy="50" rx="146" ry="10" stroke="{t["b2"]}" stroke-opacity=".72" stroke-width="2"/></svg>'
        f'<div class="fc-card" style="{cstyle}" dir="ltr">'
        '<div class="fc-shell">'
        '<div class="fc-carbon"></div><div class="fc-aura"></div>'
        '<div class="fc-motif-layer"><svg viewBox="0 0 544 780" width="544" height="780" fill="none">'
        f'{_tier_motif(t["id"], t["b1"], t["b2"])}'
        f'<g fill="{t["b1"]}"><circle cx="192" cy="126" r="2.4" opacity=".8"/><circle cx="456" cy="166" r="2.8" opacity=".7"/>'
        '<circle cx="474" cy="316" r="2" opacity=".55"/><circle cx="174" cy="360" r="2.4" opacity=".65"/></g>'
        f'<line x1="164" y1="62" x2="164" y2="495" stroke="{t["b1"]}" stroke-opacity=".24" stroke-width="1.2"/></svg>'
        + (f'<div class="fc-wm-num fd" style="color:{t["b1"]}">{esc(num_str)}</div>' if num_str else "")
        + "</div>"
        f'<div class="fc-portrait-wrap">{portrait_html}</div>'
        '<div class="fc-bot-fade"></div>'
        '<div class="fc-left-col">'
        f'<div class="fc-ovr-text fd">{int(p.get("ovr") or 85)}</div>'
        f'<div class="fc-pos-row" dir="rtl"><span>{esc(_POS_FA_FC27.get(str(p.get("pos") or "ST").upper(), str(p.get("pos") or "مهاجم")))}</span><small style="color:{t["b1"]}">++</small></div>'
        f'<div class="fc-div" style="background:linear-gradient(90deg,transparent,{t["b1"]},transparent)"></div>'
        f'<div class="fc-badges">{_flag_svg(str(p.get("nat") or "ENG"))}{_club_crest(p, 48)}</div>'
        f'<div class="ps-list">{ps_html}</div></div>'
        '<div class="fc-name-block">'
        f'<div class="fc-role-row"><i style="background:linear-gradient(to left,{t["b1"]},transparent)"></i>'
        f'<span style="border-color:{t["b1"]}65;color:{t["b1"]}" dir="rtl">{esc(_clean_role_fa(p.get("role") or ""))}</span>'
        f'<i style="background:linear-gradient(to right,{t["b1"]},transparent)"></i></div>'
        f'<h2 class="fc-pl-name" dir="rtl">{esc(transliterate_player_name_fa(str(p.get("name") or "")))}</h2>'
        f'<div class="fc-pl-meta">{meta_line}</div>'
        f'<div class="fc-stats-dock"><div class="fc-stats-grid">{"".join(caps)}</div></div></div>'
        '<div class="fc-apex">'
        f'<svg width="320" height="106" viewBox="0 0 320 106" fill="none">'
        f'<defs><linearGradient id="apx_{uid}" x1="0" y1="0" x2="320" y2="0" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0%" stop-color="{t["b1"]}" stop-opacity="0"/><stop offset="25%" stop-color="{t["b1"]}" stop-opacity=".85"/>'
        f'<stop offset="50%" stop-color="{t["b2"]}" stop-opacity="1"/><stop offset="75%" stop-color="{t["b1"]}" stop-opacity=".85"/>'
        f'<stop offset="100%" stop-color="{t["b1"]}" stop-opacity="0"/></linearGradient></defs>'
        f'<path d="M22 14 L118 14 L160 36 L202 14 L298 14" stroke="url(#apx_{uid})" stroke-width="1.6"/>'
        f'<path d="M98 62 L160 92 L222 62" stroke="url(#apx_{uid})" stroke-width="1.6"/>'
        f'<path d="M160 16 L186 27 V46 C186 62 175 74 160 79 C145 74 134 62 134 46 V27 Z" fill="#070D1D" stroke="{t["b1"]}" stroke-width="2"/>'
        + (
            f'<image href="{_xg_red_uri}" x="140" y="28" width="40" height="40" preserveAspectRatio="xMidYMid meet"/>'
            if (_xg_red_uri := _brand_xg_red_data_uri())
            else '<rect x="145" y="33" width="30" height="30" rx="6" fill="#E62E45"/><text x="160" y="53" text-anchor="middle" fill="#FFFFFF" font-family="Space Grotesk,sans-serif" font-weight="900" font-size="14.5" letter-spacing="-0.4">XG</text>'
        )
        + '<text x="122" y="38" text-anchor="end" fill="#CBD5E1" font-family="JetBrains Mono,monospace" font-size="9.5" font-weight="800" letter-spacing="1.2">XGPEDIA</text>'
        f'<text x="198" y="38" text-anchor="start" fill="{t["b1"]}" font-family="JetBrains Mono,monospace" font-size="9.5" font-weight="800" letter-spacing="1.4">{esc(p.get("season") or "26/27")}</text>'
        "</svg></div>"
        '<div class="fc-sheen"></div></div>'
        f'<svg class="fc-frame-svg" viewBox="0 0 544 780" fill="none">'
        f'<defs><linearGradient id="fr_{uid}" x1="0" y1="0" x2="544" y2="780" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0%" stop-color="{t["b1"]}"/><stop offset="30%" stop-color="{t["b2"]}"/><stop offset="66%" stop-color="{t["b3"]}"/><stop offset="100%" stop-color="{t["b1"]}"/></linearGradient>'
        f'<linearGradient id="fr2_{uid}" x1="544" y1="0" x2="0" y2="780" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0%" stop-color="{t["b1"]}" stop-opacity=".9"/><stop offset="50%" stop-color="{t["b2"]}" stop-opacity=".42"/><stop offset="100%" stop-color="{t["b1"]}" stop-opacity=".9"/></linearGradient></defs>'
        f'<path d="M7 154 L20 136 V302 L7 284 Z" fill="url(#fr_{uid})" opacity=".96"/>'
        f'<path d="M537 154 L524 136 V302 L537 284 Z" fill="url(#fr_{uid})" opacity=".96"/>'
        f'<path d="M12 318 L20 326 V422 L12 414 Z" fill="{t["b1"]}" opacity=".68"/>'
        f'<path d="M532 318 L524 326 V422 L532 414 Z" fill="{t["b1"]}" opacity=".68"/>'
        f'<path d="M14 548 L20 554 V624 L14 618 Z" fill="{t["b2"]}" opacity=".85"/>'
        f'<path d="M530 548 L524 554 V624 L530 618 Z" fill="{t["b2"]}" opacity=".85"/>'
        f'<path d="M272 6 L307 33 L343 33 L362 48 L465 48 L512 92 L524 134 L524 629 L480 688 L405 732 L272 772 L139 732 L64 688 L20 629 L20 134 L32 92 L79 48 L182 48 L201 33 L237 33 Z" stroke="url(#fr_{uid})" stroke-width="5.2" stroke-linejoin="round"/>'
        f'<path d="M272 19 L302 43 L338 43 L356 58 L458 58 L501 99 L512 139 L512 623 L471 678 L398 720 L272 758 L146 720 L73 678 L32 623 L32 139 L43 99 L86 58 L188 58 L206 43 L242 43 Z" stroke="url(#fr2_{uid})" stroke-width="1.5" stroke-linejoin="round"/>'
        f'<polygon points="272,2 287,20 272,38 257,20" fill="#070D1D" stroke="{t["b1"]}" stroke-width="2.6"/>'
        f'<polygon points="272,10 279,20 272,30 265,20" fill="{t["b2"]}"/>'
        f'<path d="M236 741 L272 758 L308 741" stroke="{t["b1"]}" stroke-width="2.8" stroke-linecap="round"/>'
        f'<polygon points="272,764 278,772 272,780 266,772" fill="{t["b1"]}"/></svg>'
        "</div></div></div>"
    )


def _mini_radar_hud(p: dict[str, Any], t: dict[str, str]) -> str:
    vs = [max(20, min(100, float(v))) for v in (p.get("radar") or [88, 86, 84, 85, 80, 88])[:6]]
    lb = ["دریبل", "شوت", "پاس", "گلزنی", "پرس", "اثر"]
    cx, cy, r_m = 130.0, 112.0, 62.0
    pts = [(cx + (v / 100.0) * r_m * math.cos(math.radians(i * 60 - 90)), cy + (v / 100.0) * r_m * math.sin(math.radians(i * 60 - 90))) for i, v in enumerate(vs)]
    rings = "".join('<polygon points="' + " ".join(f"{cx + r_m * k * math.cos(math.radians(i * 60 - 90)):.1f},{cy + r_m * k * math.sin(math.radians(i * 60 - 90)):.1f}" for i in range(6)) + '"/>' for k in (1.0, 0.75, 0.5, 0.25))
    pos_l = [(cx, 24, "middle"), (cx + r_m * 0.95 + 10, cy - r_m * 0.44, "start"), (cx + r_m * 0.95 + 10, cy + r_m * 0.55, "start"), (cx, cy + r_m + 24, "middle"), (cx - r_m * 0.95 - 10, cy + r_m * 0.55, "end"), (cx - r_m * 0.95 - 10, cy - r_m * 0.44, "end")]
    lbls = "".join(f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{a}" fill="#F8FAFC" font-family="Vazirmatn" font-weight="800" font-size="12.5">{lb[i]}</text>' for i, (x, y, a) in enumerate(pos_l))
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.6" fill="{t["b1"]}" stroke="#070D1D" stroke-width="1.8"/>' for x, y in pts)
    return (
        '<div class="hud-box"><div class="hud-h"><span>رادار صدکی ۶ محوره</span>'
        f'<b class="fm" style="color:{t["b1"]}">PCT</b></div>'
        f'<div dir="ltr"><svg style="width:100%;max-height:185px" viewBox="0 0 260 224" fill="none">'
        f'<g stroke="#ffffff28" stroke-width="1.2">{rings}</g>'
        f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" fill="{t["glow"]}" fill-opacity=".3" stroke="{t["b1"]}" stroke-width="2.5"/>'
        f"{dots}{lbls}</svg></div></div>"
    )


def _mini_per90_hud(p: dict[str, Any], t: dict[str, str]) -> str:
    p90 = p.get("p90") or {}
    items = [
        ("xG", f2(p90["xg"]) if p90.get("xg") is not None else "—", "#E62E45"),
        ("xA", f2(p90["xa"]) if p90.get("xa") is not None else "—", "#38BDF8"),
        ("xT", f2(p90["xt"]) if p90.get("xt") is not None else "—", "#34D399"),
        ("SCA", f1(p90["sca"]) if p90.get("sca") is not None else "—", t["b1"]),
    ]
    cells = "".join(f'<div class="p90-c"><span class="fm">{k}</span><b class="fd" style="color:{c}">{v}</b></div>' for k, v, c in items)
    return (
        '<div class="hud-box"><div class="hud-h"><span>تله‌متری در ۹۰ دقیقه</span><b class="fm dim">PER 90</b></div>'
        f'<div class="p90-2x2" dir="ltr">{cells}</div></div>'
    )


def _mini_heatmap_hud(p: dict[str, Any], t: dict[str, str]) -> str:
    heat = p.get("heat") or []
    defs = "".join(
        f'<radialGradient id="hmm_{i}"><stop offset="0%" stop-color="{"#FDE047" if i == 0 else "#E62E45"}" stop-opacity=".95"/>'
        f'<stop offset="45%" stop-color="#E62E45" stop-opacity=".55"/><stop offset="100%" stop-color="{t["glow"]}" stop-opacity="0"/></radialGradient>'
        for i in range(len(heat))
    )
    blobs = "".join(f'<circle cx="{pt[0] * 3.6:.1f}" cy="{pt[1] * 2.2:.1f}" r="{pt[2] * 1.55:.1f}" fill="url(#hmm_{i})" opacity=".88"/>' for i, pt in enumerate(heat) if isinstance(pt, (list, tuple)) and len(pt) >= 3)
    return (
        '<div class="hud-box"><div class="hud-h"><span>نقشه حرارتی</span><b class="fm gold">HEATMAP</b></div>'
        f'<div dir="ltr"><svg class="hm-svg" viewBox="0 0 360 220" fill="none"><defs>{defs}</defs>'
        '<rect width="360" height="220" fill="#0A1A2B"/>'
        '<g stroke="#ffffff26" stroke-width="1.5"><rect x="10" y="10" width="340" height="200" rx="6"/>'
        '<line x1="180" y1="10" x2="180" y2="210"/><circle cx="180" cy="110" r="32"/>'
        '<rect x="10" y="55" width="48" height="110"/><rect x="302" y="55" width="48" height="110"/></g>'
        f"{blobs}</svg></div></div>"
    )


def _mini_sparkline_hud(p: dict[str, Any], t: dict[str, str]) -> str:
    vals = [float(v) for v in (p.get("form") or [])[-5:]]
    if not vals:
        idx_v = p.get("xgpIndex")
        return (
            '<div class="hud-box"><div class="hud-h"><span>شاخص XGPedia</span><b class="fm em">INDEX</b></div>'
            f'<div style="text-align:center;padding:18px 0"><b class="fd" style="font-size:38px;color:{t["b1"]}">{f1(idx_v) if idx_v is not None else "—"}</b></div></div>'
        )
    avg = sum(vals) / len(vals)
    pts = []
    step = 192.0 / max(1, len(vals) - 1)
    for i, v in enumerate(vals):
        col = "#34D399" if v >= 8.5 else ("#38BDF8" if v >= 7.8 else "#FBBF24")
        x = 24.0 + i * step
        y = 84.0 - ((max(6.8, min(10.0, v)) - 6.8) / 3.2) * 50.0
        pts.append((x, y, v, col))
    path = " ".join(f"{'L' if i else 'M'}{x:.1f} {y:.1f}" for i, (x, y, _, _) in enumerate(pts))
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{"5.2" if i == len(pts) - 1 else "4"}" fill="{col}" stroke="#070D1D" stroke-width="2"/>'
        f'<rect x="{x - 17:.1f}" y="{y - 26:.1f}" width="34" height="17" rx="5" fill="#070D1D" stroke="{col}" stroke-opacity=".6"/>'
        f'<text x="{x:.1f}" y="{y - 14:.1f}" text-anchor="middle" fill="{col}" font-family="Space Grotesk" font-size="11.5" font-weight="800">{f1(v)}</text>'
        for i, (x, y, v, col) in enumerate(pts)
    )
    return (
        '<div class="hud-box"><div class="hud-h"><span>روند فرم ۵ بازی</span>'
        f'<span class="avg-pill fd">AVG {f1(avg)}</span></div>'
        f'<svg viewBox="0 0 240 104" style="width:100%;height:auto" fill="none" dir="ltr">'
        f'<defs><linearGradient id="spg_{t["id"]}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="{t["b1"]}" stop-opacity=".32"/><stop offset="100%" stop-color="{t["b1"]}" stop-opacity="0"/></linearGradient></defs>'
        '<g stroke="#ffffff14" stroke-dasharray="4 4"><line x1="12" y1="34" x2="228" y2="34"/><line x1="12" y1="62" x2="228" y2="62"/><line x1="12" y1="90" x2="228" y2="90"/></g>'
        f'<path d="{path} L {pts[-1][0]:.1f} 94 L {pts[0][0]:.1f} 94 Z" fill="url(#spg_{t["id"]})"/>'
        f'<path d="{path}" stroke="{t["b1"]}" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/>'
        f"{dots}</svg></div>"
    )


def _render_verdict(p: dict[str, Any]) -> str:
    tag = p.get("verdictTag") or p.get("stars") or ""
    return (
        '<div class="xe verd-card">'
        '<div class="mh"><div class="mh-left"><span class="mh-bar"></span><h3 class="mt">لنز تاکتیکی XGPedia</h3></div>'
        '<span class="fm dim" style="font-size:13px">SCOUTING DNA</span></div>'
        f'<h4 class="verd-t">{esc(p.get("verdictTitle") or "")}</h4>'
        f'<p class="verd-b">{esc(p.get("verdictBody") or "")}</p>'
        + (f'<div class="verd-tag"><i class="rdot"></i><span>{esc(tag)}</span></div>' if tag else "")
        + "</div>"
    )


def render_player_fc27_html(
    data: dict[str, Any],
    *,
    fmt: str = "4:5",
    header_mode: str = "full",
    theme: str | None = None,
    slide: str = "slide1",
    modules: list[dict[str, Any]] | None = None,
) -> str:
    w, h_px = FC27_FORMATS.get(fmt, (1080, 1350))
    is_story = fmt == "9:16"
    is_wide = fmt == "16:9"
    # استاندارد یکپارچه فریم چهارگوشه قرمز XGPedia
    pad_top, pad_bot = (139, 171) if is_story else ((22, 16) if is_wide else (24, 20))

    skin_key = theme if (theme in TIERS) else str(data.get("tier") or "signature")
    t = TIERS.get(skin_key, TIERS["signature"])
    if modules is None:
        modules, _ = get_player_fc27_modules(data, slide)
    enabled_set = {m["id"] for m in modules if m.get("enabled")}
    layout = next((lm for sid, _, lm, _ in FC27_SLIDES if sid == slide), "spotlight")

    last_en = str(data.get("en") or "XGPEDIA").strip().split()[-1]
    num_s = str(data.get("num")).zfill(2) if data.get("num") not in (None, "", 0) else "27"

    if layout == "poster" or enabled_set == {"fc_card"}:
        sc = 1.00 if is_wide else (1.36 if is_story else 1.15)
        p90 = data.get("p90") or {}
        form = data.get("form") or []
        avg_f = fa(f1(sum(form) / len(form))) if form else "—"
        xgxa = fa(f2(float(p90.get("xg") or 0) + float(p90.get("xa") or 0))) if (p90.get("xg") is not None) else "—"
        xt_s = fa(f2(p90["xt"])) if p90.get("xt") is not None else "—"
        val_s = esc(data.get("val") or data.get("club") or "—")
        kpis = "".join(
            f'<div class="kpi-tile"><span>{l}</span><b style="color:{c}">{v}</b></div>'
            for l, v, c in [("میانگین ۵ بازی", avg_f, t["b1"]), ("مجموع xG+xA", xgxa, "#34D399"), ("تهدید پاس (xT)", xt_s, "#38BDF8"), ("باشگاه / مشخصات", val_s, "#F8FAFC")]
        )
        body_html = (
            '<div class="poster-wrap">'
            f'<div class="giant-ghost-text" style="top:14%;font-size:210px;color:transparent;-webkit-text-stroke:2px {t["b1"]};opacity:.13">{esc(last_en)}</div>'
            f'<div class="giant-ghost-text" style="bottom:18%;font-size:160px;color:{t["glow"]};opacity:.09">FC27 • #{esc(num_s)}</div>'
            f'<div style="position:relative;z-index:5">{_render_fc27_shield(data, t, sc)}</div></div>'
            f'<div class="kpi-4">{kpis}</div>'
        )
    else:
        left_huds = []
        right_huds = []
        if "radar" in enabled_set:
            left_huds.append(_mini_radar_hud(data, t))
        if "per90" in enabled_set:
            left_huds.append(_mini_per90_hud(data, t))
        if "heatmap" in enabled_set and data.get("heat"):
            right_huds.append(_mini_heatmap_hud(data, t))
        if "index_form" in enabled_set:
            right_huds.append(_mini_sparkline_hud(data, t))
        sc = 0.88 if not is_story else 1.05
        verdict_html = _render_verdict(data) if ("verdict" in enabled_set and (data.get("verdictBody") or data.get("verdictTitle"))) else ""
        body_html = (
            '<div class="spot-main">'
            f'<div class="giant-ghost-text" style="top:4%;font-size:200px;color:transparent;-webkit-text-stroke:2px {t["b1"]};opacity:.13">{esc(last_en)}</div>'
            f'<div class="giant-ghost-text" style="bottom:8%;font-size:120px;color:{t["glow"]};opacity:.09">XGPEDIA • #{esc(num_s)}</div>'
            '<div class="spot-grid">'
            f'<div class="hud-col">{"".join(left_huds)}</div>'
            f'<div class="fc">{_render_fc27_shield(data, t, sc)}</div>'
            f'<div class="hud-col">{"".join(right_huds)}</div>'
            f'</div></div>{verdict_html}'
        )

    cx, cy, rx = w // 2, round(h_px * 0.43), w - 147
    pitch_svg = (
        f'<svg class="bg-svg" viewBox="0 0 {w} {h_px}" preserveAspectRatio="xMidYMid slice" fill="none">'
        '<defs><pattern id="tg" width="54" height="54" patternUnits="userSpaceOnUse"><path d="M54 0H0v54" stroke="#F8FAFC" stroke-opacity=".05"/></pattern>'
        '<radialGradient id="rf" cx="50%" cy="42%" r="48%"><stop offset="0" stop-color="#E62E45" stop-opacity=".26"/>'
        '<stop offset=".55" stop-color="#E62E45" stop-opacity=".07"/><stop offset="1" stop-color="#E62E45" stop-opacity="0"/></radialGradient></defs>'
        '<rect width="100%" height="100%" fill="url(#tg)"/>'
        f'<rect x="12" y="12" width="{w - 24}" height="{h_px - 24}" rx="18" stroke="#F8FAFC" stroke-opacity=".12" stroke-width="1.5"/>'
        f'<g stroke="#F8FAFC" stroke-opacity=".08" stroke-width="1.5"><line x1="{cx}" y1="12" x2="{cx}" y2="{h_px - 12}" stroke-dasharray="8 8"/>'
        f'<circle cx="{cx}" cy="{cy}" r="185"/></g>'
        f'<circle cx="{cx}" cy="{cy}" r="340" fill="url(#rf)"/>'
        f'<circle cx="{cx}" cy="{cy}" r="300" stroke="#E62E45" stroke-opacity=".22" stroke-width="1.3" stroke-dasharray="5 7"/>'
        f'<circle cx="{cx}" cy="{cy}" r="410" stroke="#F8FAFC" stroke-opacity=".06"/>'
        f'<path d="M24 44V24H44M{w - 24} 44V24H{w - 44}M24 {h_px - 44}V{h_px - 24}H44M{w - 24} {h_px - 44}V{h_px - 24}H{w - 44}" '
        'stroke="#E62E45" stroke-width="2.4" stroke-linecap="round"/></svg>'
    )
    ag_bg = (
        f"radial-gradient(circle at 50% 42%,{t['glow']}4c,transparent 54%),"
        f"radial-gradient(circle at 86% 22%,{esc(data.get('color') or '#E62E45')}38,transparent 46%),"
        f"radial-gradient(circle at 14% 72%,{t['sec']}34,transparent 46%)"
    )
    sub_num = f' • شماره {fa(data["num"])}' if data.get("num") not in (None, "", 0) else ""
    trophy = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#E62E45" stroke-width="2.4"><path d="M8 21h8m-4-4v4m-5-17h10v5a5 5 0 01-10 0V4zM5 6H3v2a3 3 0 003 3h1m12-5h2v2a3 3 0 01-3 3h-1"/></svg>'
    logo_uri = _brand_logo_data_uri()
    font_css = build_embedded_font_css()

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl"><head><meta charset="UTF-8"><style>
{font_css}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:{w}px;height:{h_px}px;overflow:hidden;background:#081022;color:#F8FAFC;font-family:'Vazirmatn',sans-serif;font-feature-settings:"tnum";font-variant-numeric:tabular-nums;}}
.fm{{font-family:'JetBrains Mono','Space Grotesk',monospace;}} .fd{{font-family:'Space Grotesk',sans-serif;}}
.fc{{display:flex;align-items:center;justify-content:center;}}
#ea{{position:relative;width:{w}px;height:{h_px}px;background:#081022;display:flex;flex-direction:column;justify-content:space-between;padding:{pad_top}px 0 {pad_bot}px 0;overflow:hidden;}}
.ag,.bg-svg,.scanlines{{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0;}}
.scanlines{{background:repeating-linear-gradient(to bottom,#ffffff05 0 1px,#0000 1px 4px);}}
.stage-beam-l,.stage-beam-r{{position:absolute;top:-140px;width:580px;height:1020px;pointer-events:none;z-index:1;filter:blur(46px);opacity:.28;mix-blend-mode:screen;}}
.stage-beam-l{{left:-140px;transform:rotate(25deg);background:linear-gradient(180deg,{t["glow"]} 0%,transparent 74%);}}
.stage-beam-r{{right:-140px;transform:rotate(-25deg);background:linear-gradient(180deg,{t["sec"]} 0%,transparent 74%);}}
.giant-ghost-text{{position:absolute;left:50%;transform:translateX(-50%);font-family:'Space Grotesk',sans-serif;font-weight:800;line-height:.84;letter-spacing:.06em;text-transform:uppercase;white-space:nowrap;pointer-events:none;z-index:2;}}
.hdr{{position:relative;z-index:10;display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 36px 8px;flex-shrink:0;}}
.hdr-pills{{display:flex;align-items:center;flex-wrap:wrap;gap:8px;}}
.c-pill{{display:inline-flex;align-items:center;gap:8px;padding:5px 15px;border-radius:999px;font-size:19px;font-weight:900;background:#152347e6;border:1px solid #ffffff2e;color:#F8FAFC;}}
.c-pill.red{{background:#e62e452e;border-color:#e62e4580;color:#FF6B7F;font-size:17px;font-weight:800;}}
.c-pill.tier{{background:{t["pbg"]};border-color:{t["pbd"]};color:{t["ptxt"]};font-size:15px;font-weight:800;}}
.hdr-sub{{font-size:16px;font-weight:700;color:#E2E8F0;margin-top:4px;}}
.hdr-logo{{height:42px;width:auto;}}
.stage{{position:relative;z-index:10;flex:1;padding:8px 40px;display:flex;flex-direction:column;justify-content:space-between;gap:10px;overflow:hidden;min-height:0;}}
.spot-main,.poster-wrap{{position:relative;flex:1;display:flex;align-items:center;justify-content:center;width:100%;min-height:0;}}
.spot-grid{{position:relative;z-index:5;width:100%;display:grid;grid-template-columns:255px 1fr 255px;align-items:center;gap:12px;}}
.hud-col{{display:flex;flex-direction:column;gap:12px;}}
.hud-box{{border-radius:18px;background:linear-gradient(155deg,rgba(15,27,56,.90),rgba(6,11,24,.95));border:1.5px solid rgba(255,255,255,.14);box-shadow:0 16px 36px rgba(0,0,0,.68),inset 0 1px 0 rgba(255,255,255,.16);padding:12px 14px;}}
.hud-h{{display:flex;align-items:center;justify-content:space-between;font-size:12px;font-weight:900;color:#FFF;margin-bottom:8px;}}
.hud-h .dim{{color:#94A3B8;font-size:10px;}} .hud-h .gold{{color:#FCD34D;font-size:10px;}} .hud-h .em{{color:#6EE7B7;font-size:10px;}}
.avg-pill{{padding:2px 8px;border-radius:8px;background:rgba(16,185,129,0.16);border:1px solid rgba(52,211,153,0.38);font-size:12.5px;font-weight:800;color:#6EE7B7;}}
.p90-2x2{{display:grid;grid-template-columns:1fr 1fr;gap:8px;}}
.p90-c{{padding:8px 6px;border-radius:12px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.1);text-align:center;}}
.p90-c span{{display:block;font-size:10px;font-weight:700;color:#94A3B8;}} .p90-c b{{font-size:22px;font-weight:800;line-height:1.15;}}
.hm-svg{{width:100%;max-height:135px;border-radius:11px;border:1px solid rgba(255,255,255,.14);}}
.fc-stage{{position:relative;display:flex;align-items:center;justify-content:center;}}
.fc-card{{position:relative;width:544px;height:780px;}}
.fc-back-halo{{position:absolute;inset:-28px;border-radius:50%;background:radial-gradient(ellipse 70% 64% at 50% 42%,var(--c-glow) 0%,var(--c-sec) 28%,transparent 70%);filter:blur(46px);opacity:.52;z-index:0;}}
.fc-pedestal{{position:absolute;bottom:-30px;left:50%;transform:translateX(-50%);width:548px;height:90px;z-index:1;}}
.fc-shell{{position:absolute;inset:0;z-index:5;overflow:hidden;clip-path:polygon(50% 0.8%,56.5% 4.2%,63% 4.2%,66.5% 6.2%,85.5% 6.2%,94.2% 11.8%,96.4% 17.2%,96.4% 80.6%,88.2% 88.2%,74.5% 93.8%,50% 99.0%,25.5% 93.8%,11.8% 88.2%,3.6% 80.6%,3.6% 17.2%,5.8% 11.8%,14.5% 6.2%,33.5% 6.2%,37% 4.2%,43.5% 4.2%);background:var(--c-bg);box-shadow:0 44px 90px -14px rgba(0,0,0,.96);}}
.fc-carbon{{position:absolute;inset:0;opacity:.40;background-image:radial-gradient(rgba(255,255,255,.20) 1px,transparent 1px),repeating-linear-gradient(120deg,rgba(255,255,255,.045) 0 1px,transparent 1px 16px),repeating-linear-gradient(60deg,rgba(255,255,255,.045) 0 1px,transparent 1px 16px);background-size:18px 18px,32px 32px,32px 32px;}}
.fc-aura{{position:absolute;inset:0;background:radial-gradient(circle at 60% 34%,var(--c-glow) 0%,transparent 54%),radial-gradient(circle at 20% 18%,var(--c-sec) 0%,transparent 44%),radial-gradient(ellipse 88% 40% at 50% 96%,var(--c-accent) 0%,transparent 54%);opacity:.60;}}
.fc-motif-layer{{position:absolute;inset:0;overflow:hidden;}}
.fc-wm-num{{position:absolute;top:34px;right:24px;font-size:255px;font-weight:800;line-height:1;opacity:.075;}}
.fc-portrait-wrap{{position:absolute;top:72px;right:20px;width:376px;height:412px;z-index:12;overflow:hidden;}}
.fc-portrait{{width:100%;height:100%;object-fit:contain;object-position:bottom center;-webkit-mask-image:radial-gradient(ellipse 73% 70% at 52% 40%,#000 48%,rgba(0,0,0,.84) 68%,transparent 94%),linear-gradient(to bottom,#000 60%,transparent 96%);-webkit-mask-composite:source-in;filter:contrast(1.1) saturate(1.14) drop-shadow(0 20px 32px rgba(0,0,0,.82));}}
.fc-bot-fade{{position:absolute;left:0;right:0;bottom:0;height:420px;z-index:15;background:linear-gradient(to top,#050914 0%,#070D1D 56%,rgba(7,13,29,.88) 78%,transparent 100%);}}
.fc-left-col{{position:absolute;top:86px;left:46px;width:114px;z-index:20;display:flex;flex-direction:column;align-items:center;text-align:center;gap:6px;}}
.fc-ovr-text{{font-size:86px;font-weight:800;line-height:.84;background:linear-gradient(180deg,#FFFFFF 0%,var(--c-metal-mid) 52%,var(--c-metal-bot) 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;filter:drop-shadow(0 5px 14px rgba(0,0,0,.9));}}
.fc-pos-row{{font-size:26px;font-weight:800;letter-spacing:.14em;color:#FFF;display:flex;align-items:center;gap:2px;margin-top:4px;}}
.fc-pos-row small{{font-size:14px;}}
.fc-div{{width:56px;height:1.5px;margin:3px 0;}}
.fc-badges{{display:flex;align-items:center;gap:8px;}}
.ps-list{{display:flex;align-items:center;gap:10px;margin-top:6px;}}
.ps-item{{display:flex;flex-direction:column;align-items:center;}}
.fc-ps-hex{{width:46px;height:52px;clip-path:polygon(50% 0%,100% 25%,100% 75%,50% 100%,0% 75%,0% 25%);display:flex;align-items:center;justify-content:center;}}
.fc-ps-hex.inner{{width:100%;height:100%;background:#081022;}}
.ps-lbl{{font-size:9px;font-weight:800;color:#E2E8F0;margin-top:2px;white-space:nowrap;}}
.fc-name-block{{position:absolute;left:50px;right:50px;bottom:158px;z-index:20;display:flex;flex-direction:column;align-items:center;}}
.fc-role-row{{width:100%;display:flex;align-items:center;gap:10px;margin-bottom:6px;}}
.fc-role-row i{{flex:1;height:1.5px;}}
.fc-role-row span{{padding:2px 14px;border-radius:999px;background:rgba(9,18,40,.94);border:1px solid;font-size:11px;font-weight:800;white-space:nowrap;}}
.fc-pl-name{{font-size:38px;font-weight:900;color:#FFF;line-height:1.06;text-align:center;text-shadow:0 6px 22px rgba(0,0,0,.92);}}
.fc-pl-meta{{display:flex;align-items:center;gap:8px;margin:4px 0 10px;font-size:11.5px;font-weight:700;color:#CBD5E1;}}
.fc-pl-meta .op{{opacity:.4;}} .fc-pl-meta .foot{{color:#F1F5F9;font-weight:800;}}
.fc-stats-dock{{width:100%;padding:8px;border-radius:16px;background:rgba(5,10,23,.88);border:1px solid rgba(255,255,255,.15);}}
.fc-stats-grid{{display:grid;grid-template-columns:repeat(6,1fr);gap:6px;}}
.stat-cap{{background:linear-gradient(180deg,rgba(18,32,66,.94),rgba(7,13,29,.98));border:1px solid rgba(255,255,255,.16);border-radius:12px;padding:7px 3px 6px;display:flex;flex-direction:column;align-items:center;gap:4px;}}
.sc-en{{font-size:11px;font-weight:800;letter-spacing:.12em;color:#CBD5E1;}}
.sc-val{{font-size:29px;font-weight:800;color:#FFF;line-height:1;}}
.led-row{{display:grid;grid-template-columns:repeat(5,1fr);gap:2px;width:100%;padding:0 3px;}}
.led-seg{{height:4px;border-radius:2px;background:rgba(255,255,255,.12);}}
.sc-fa{{font-size:10.5px;font-weight:700;color:#CBD5E1;}}
.fc-apex{{position:absolute;bottom:32px;left:50%;transform:translateX(-50%);z-index:20;}}
.fc-sheen{{position:absolute;inset:-46%;z-index:22;background:linear-gradient(115deg,transparent 24%,rgba(255,255,255,.04) 37%,rgba(255,255,255,.30) 45%,var(--c-foil) 49%,rgba(56,189,248,.22) 53%,transparent 69%);transform:translateX(-24%) rotate(9deg);mix-blend-mode:screen;opacity:.55;}}
.fc-frame-svg{{position:absolute;inset:0;width:100%;height:100%;z-index:26;filter:drop-shadow(0 12px 26px rgba(0,0,0,.75));}}
.xe{{border-radius:22px;background:linear-gradient(155deg,#132142eb,#070d1ef7);border:1.5px solid #7fa6e842;padding:14px 20px;flex-shrink:0;}}
.mh{{display:flex;align-items:center;justify-content:space-between;padding-bottom:7px;margin-bottom:8px;border-bottom:1px solid #ffffff1f;}}
.mh-left{{display:flex;align-items:center;gap:9px;}}
.mh-bar{{width:7px;height:20px;border-radius:99px;background:#E62E45;}}
.mt{{font-size:19px;font-weight:900;color:#FFF;}}
.verd-t{{font-size:20px;font-weight:900;color:#FCD34D;margin-bottom:4px;}}
.verd-b{{font-size:16px;font-weight:600;color:#F1F5F9;line-height:1.5;}}
.verd-tag{{margin-top:8px;padding-top:8px;border-top:1px solid #ffffff1f;display:flex;align-items:center;gap:8px;font-size:14px;font-weight:800;color:#F1F5F9;}}
.rdot{{width:9px;height:9px;border-radius:99px;background:#E62E45;display:inline-block;}}
.kpi-4{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;flex-shrink:0;}}
.kpi-tile{{border-radius:16px;background:linear-gradient(165deg,#101d3be0,#080f22f5);border:1.5px solid #f8fafc24;padding:12px 10px;text-align:center;}}
.kpi-tile span{{display:block;font-size:13px;font-weight:700;color:#94A3B8;}}
.kpi-tile b{{display:block;font-size:21px;font-weight:900;margin-top:4px;}}
.ftr{{position:relative;z-index:10;padding:10px 44px 10px;border-top:1px solid #ffffff1f;display:flex;align-items:center;justify-content:space-between;font-size:15px;color:#CBD5E1;flex-shrink:0;}}
.ftr-left{{display:flex;align-items:center;gap:9px;}} .ftr-dot{{width:10px;height:10px;border-radius:99px;background:#E62E45;}}
.ftr-tag{{font-size:15px;font-weight:800;letter-spacing:.12em;color:#F1F5F9;}}
.ftr-right{{display:flex;align-items:center;gap:10px;}} .ftr-right b{{color:#FFF;font-size:17px;}}

footer, footer .fbw, footer .cf-row, footer .fi, footer .cf-left, footer .cf-right, .xg-footer, .foot-row, .card-footer{{flex-wrap:nowrap!important;white-space:nowrap!important;min-width:0!important;}}
footer span, footer div, .pl-foot-tag, .pl-foot-s, .in-foot-tag, .pr-foot-tag, .st-foot-tag, .cf-tag{{white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;min-width:0!important;}}
</style></head><body>
<div id="ea">
  <div class="ag" style="background:{ag_bg}"></div>
  <div class="stage-beam-l"></div><div class="stage-beam-r"></div>
  {pitch_svg}
  <div class="scanlines"></div>
  <header class="hdr">
    <div>
      <div class="hdr-pills">
        <span class="c-pill">{trophy}<span>{esc(data.get("competition") or "فوتبال")}</span></span>
        <span class="c-pill red">{esc(data.get("badge") or "کارت ستاره FC27")}</span>
        <span class="c-pill tier fm">{esc(t["tag"])}</span>
      </div>
      <div class="hdr-sub">{esc(data.get("club") or "")}{sub_num} • {esc(_clean_role_fa(data.get("role") or ""))}</div>
    </div>
    <img class="hdr-logo" src="{logo_uri}" alt="XGPedia"/>
  </header>
  <main class="stage">{body_html}</main>
  <footer class="ftr">
    <div class="ftr-left"><span class="ftr-dot"></span><span class="ftr-tag fm" dir="ltr">{esc(str(data.get("leagueEn") or "XGPEDIA").upper())} {esc(data.get("season") or "26/27")} • FC27 CHRONO CARD</span></div>
    <div class="ftr-right fm" dir="ltr"><b>@XGPedia</b><span>|</span><span>{esc(data.get("source") or "Opta / XGPedia")}</span></div>
  </footer>
</div></body></html>"""
