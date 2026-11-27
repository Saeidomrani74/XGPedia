"""کارت ماژولار «مقایسه دو بازیکن» (Head-to-Head Players Studio — D57) — بازسازی ۱:۱ و ۱۰۰٪ آفلاین.

تطابق کامل گرافیکی با `studio_templates/h2h_players.html` (Showreel v2):
  - پس‌زمینهٔ تاکتیکی با شبکه `54×54`، خط میانی نقطه‌چین، ۳ دایره هم‌مرکز، هالهٔ دوگانهٔ رنگ دو بازیکن و فریم چهارگوشهٔ قرمز استاندارد
  - هدر کامل (استیج ۱۲ ستونه با پیراهن SVG برداری یا عکس بازیکن + حلقه امتیاز `XGP` + شماره شبح‌وار + لوزی چرخان `VS` + `DUEL EDGE`) و هدر فشرده (`.cribbon` با نوار برتری آماری)
  - ۸ ماژول مستقل (روشن/خاموش، نیم‌عرض/تمام‌عرض، تغییر ترتیب، ۵ اسلاید و ذخیره تا ۵ قالب):
      1. `vitals`: میدان نبرد آمارهای کلیدی (تله‌متری سگمنت‌دار + حلقه‌های صدک SVG + دلتا)
      2. `radar`: رادار-پیتزای ۸ محوره صدک‌محور + قوس‌های بیرونی برنده + ۲ برگ برنده
      3. `dna`: اثر انگشت تاکتیکی ۴ محوره (Tactical DNA Blueprint با توکن شماره پیراهن)
      4. `pitch`: آزمایشگاه تاکتیکی زمین ۱۸ منطقه‌ای + Zone 14 + هیت‌زون + بردار نفوذ + شوت‌ها
      5. `finishing`: آزمایشگاه تمام‌کنندگی (کاکپیت ۲۴۰ درجه + ماتریس ۲۴ نقطه‌ای شوت + G-xG)
      6. `trend`: روند فرم در ۱۰ بازی اخیر (Sparkline منحنی + نشان ★ اوج فرم)
      7. `impact`: پرونده اسکاوت و ارزش بازار (Scout Dossier)
      8. `archetype`: حکم تاکتیکی XGPedia (Editorial Magazine Spread)
  - ۱۰۰٪ آفلاین (فونت‌های محلی + لوگوی SVG واقعی) + فواصل عمودی یکسان چهارگوشه قرمز + فوتر اکیداً تک‌خطی + `null ≠ 0`.
"""
from __future__ import annotations

import math
from typing import Any

from src.xgpedia.render.card_kit.helpers import with_sample_badge, esc
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


H2H_PLAYERS_FORMATS: dict[str, tuple[int, int]] = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}

H2H_PLAYERS_SLIDES: list[tuple[str, str, str, list[str]]] = [
    ("slide1", "اسلاید ۱: کارت اصلی دوئل (پیشنهادی)", "full", ["vitals", "archetype"]),
    ("slide2", "اسلاید ۲: رادار-پیتزای ۸ محوره و DNA تاکتیکی", "compact", ["radar", "dna"]),
    ("slide3", "اسلاید ۳: آزمایشگاه زمین و تمام‌کنندگی", "compact", ["pitch", "finishing"]),
    ("slide4", "اسلاید ۴: روند ۱۰ بازی و پرونده اسکاوت", "compact", ["trend", "impact"]),
    ("slide5", "اسلاید ۵: نسخه جامع اینفوگرافیک", "full", ["vitals", "radar", "dna", "finishing", "impact", "archetype"]),
]

H2H_PLAYERS_MODULE_DEFS: list[tuple[str, str, bool]] = [
    ("vitals", "میدان نبرد آمارهای کلیدی (تله‌متری + صدک)", False),
    ("radar", "رادار-پیتزای ۸ محوره صدک‌محور", True),
    ("dna", "اثر انگشت تاکتیکی (DNA سبک بازی)", True),
    ("pitch", "آزمایشگاه تاکتیکی زمین (۱۸ منطقه + شوت)", True),
    ("finishing", "آزمایشگاه تمام‌کنندگی (کاکپیت ۲۴۰°)", True),
    ("trend", "روند فرم در ۱۰ بازی اخیر (Sparkline)", True),
    ("impact", "پرونده اسکاوت و ارزش بازار", True),
    ("archetype", "حکم تاکتیکی XGPedia", False),
]

RADAR_LABELS = ["گلزنی", "خلق موقعیت", "دریبل و حمل", "پاس پیش‌رونده", "تهدید (xT)", "شدت پرس", "نبردها", "بازی‌سازی"]
DNA_AXES = [
    ("بازی‌ساز عمقی", "تمام‌کننده محوطه", "PLAYMAKER", "FINISHER"),
    ("دریبل‌زن خطی", "پاسور ترکیبی", "CARRIER", "COMBINATION"),
    ("ذخیره انرژی", "پرسینگ بالا", "CONSERVE", "HIGH PRESS"),
    ("توپ‌گیری در پا", "فرار در عمق", "TO FEET", "IN BEHIND"),
]


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



def _ensure_readable_color(hex_col: str) -> str:
    """روشن‌سازی رنگ‌های تیره (مثل آبی تیره اورتون) برای خوانایی کامل روی پس‌زمینه تیره."""
    if _lum(hex_col) >= 0.24:
        return hex_col
    c = (hex_col or "#38BDF8").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        n = int(c[:6], 16)
        r = min(255, int(((n >> 16) & 255) * 0.52 + 128))
        g = min(255, int(((n >> 8) & 255) * 0.52 + 128))
        b = min(255, int((n & 255) * 0.52 + 128))
        return f"#{r:02X}{g:02X}{b:02X}"
    except ValueError:
        return "#38BDF8"


def _ctr(hex_col: str) -> str:
    return "#070D1D" if _lum(hex_col) > 0.56 else "#FFFFFF"


def _f1(v: Any) -> str:
    try:
        return f"{float(v):.1f}"
    except (TypeError, ValueError):
        return "0.0"


def _f2(v: Any) -> str:
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _fa(v: Any) -> str:
    return str(v).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _norm_player(raw: dict[str, Any] | None, fallback_col: str) -> dict[str, Any]:
    p = dict(raw or {})
    stats = p.get("stats") or []
    if not stats:
        # Derive 6 real stats from available FPL/Opta fields if stats list absent
        xg90 = float(p.get("xg90") or p.get("xg") or 0.0)
        xa90 = float(p.get("xa90") or p.get("xa") or 0.0)
        goals = float(p.get("goals") or 0.0)
        assists = float(p.get("assists") or 0.0)
        mins = max(90.0, float(p.get("mins") or p.get("minutes") or 900.0))
        g90 = round(goals * 90.0 / mins, 2)
        a90 = round(assists * 90.0 / mins, 2)
        ict = float(p.get("ict") or 0.0)
        stats = [
            {"k": "امید گل (xG / 90)", "v": round(xg90, 2), "d": 2, "p": min(99, max(20, int(45 + xg90 * 68)))},
            {"k": "امید پاس گل (xA / 90)", "v": round(xa90, 2), "d": 2, "p": min(99, max(20, int(45 + xa90 * 110)))},
            {"k": "گل در ۹۰ دقیقه", "v": g90, "d": 2, "p": min(99, max(20, int(40 + g90 * 70)))},
            {"k": "پاس گل در ۹۰ دقیقه", "v": a90, "d": 2, "p": min(99, max(20, int(40 + a90 * 110)))},
            {"k": "مجموع گل فصل", "v": goals, "d": 0, "p": min(99, max(20, int(35 + goals * 3.5)))},
            {"k": "شاخص اثرگذاری (ICT)", "v": round(ict, 1), "d": 1, "p": min(99, max(20, int(40 + ict * 0.45)))},
        ]
    p["stats"] = stats
    from src.xgpedia.providers.injury_free import transliterate_player_name_fa
    p["name"] = transliterate_player_name_fa(str(p.get("name") or "بازیکن"))
    p["en"] = str(p.get("en") or p["name"]).upper()
    p["club"] = str(p.get("club") or "باشگاه")
    p["clubCode"] = str(p.get("clubCode") or p.get("code") or "XGP")[:3].upper()
    num_raw = p.get("number")
    p["number"] = str(num_raw) if num_raw not in (None, "", "None") else "—"
    p["pos"] = str(p.get("pos") or "بازیکن")
    _rt_map = {
        "CHANNEL STRIKER": "مهاجم تمام‌کننده و فضای عمق",
        "CREATIVE PLAYMAKER": "بازی‌ساز خلاق و طراح هجومی",
        "BALL-PLAYING DEFENDER": "مدافع بازی‌ساز و مستحکم",
        "SWEEPER KEEPER": "دروازه‌بان مدرن و بازی‌ساز",
        "PLAYMAKER": "بازی‌ساز خلاق میانه میدان",
    }
    _raw_rt = str(p.get("roleTag") or p["pos"]).strip()
    p["roleTag"] = _rt_map.get(_raw_rt.upper(), p["pos"] if _raw_rt.isascii() else _raw_rt)
    p["age"] = p.get("age") if p.get("age") not in (None, "") else "—"
    p["height"] = str(p.get("height") or "—")
    p["foot"] = str(p.get("foot") or "—")
    p["value"] = str(p.get("value") or "—")
    p["mins"] = int(p.get("mins") or p.get("minutes") or 0)
    p["minShare"] = int(p.get("minShare") or 85)
    p["xgp"] = float(p.get("xgp") or p.get("rating") or 8.2)
    p["color"] = str(p.get("color") or fallback_col)
    p["secondary"] = str(p.get("secondary") or "#FFFFFF")
    p["goals"] = int(p.get("goals") or 0)
    p["xgTotal"] = float(p.get("xgTotal") if p.get("xgTotal") is not None else p.get("xg") or 0.0)
    p["shots"] = int(p.get("shots") or max(1, p["goals"] * 4))
    p["bigChanceConv"] = int(p.get("bigChanceConv") or min(95, max(25, int(45 + (p["goals"] - p["xgTotal"]) * 6))))
    p["xgPerShot"] = float(p.get("xgPerShot") or (p["xgTotal"] / max(1, p["shots"])))
    if not p.get("radar") or len(p.get("radar")) < 8:
        base_r = [int(s.get("p") or 70) for s in stats[:6]]
        while len(base_r) < 8:
            base_r.append(min(96, max(50, int(p["xgp"] * 10 - 4))))
        p["radar"] = base_r[:8]
    if not p.get("dna") or len(p.get("dna")) < 4:
        p["dna"] = [65, 55, 62, 68]
    if not p.get("trend") or len(p.get("trend")) < 4:
        base_t = p["xgp"]
        p["trend"] = [round(max(6.2, min(9.8, base_t + d)), 1) for d in (-0.4, 0.1, -0.2, 0.3, 0.0, 0.2, -0.1, 0.4, -0.2, 0.0)]
    p["strength"] = str(p.get("strength") or f"مشارکت مستمر در فاز هجومی {p['club']} با شاخص XGP {_fa(_f1(p['xgp']))}")
    _raw_edge = str(p.get("edgeTag") or "").strip()
    if not _raw_edge or _raw_edge == p["pos"] or _raw_edge.isascii():
        _st = p["stats"]
        _best_st = max(_st, key=lambda x: float(x.get("p") or 0), default={"k": "اثرگذاری هجومی"})
        _k = str(_best_st.get("k") or "اثرگذاری هجومی").split("(")[0].strip()
        _raw_edge = f"برتری در {_k} و جریان بازی"
    p["edgeTag"] = _raw_edge
    return p


def get_h2h_players_modules(item: dict[str, Any], slide: str = "slide1") -> tuple[list[dict[str, Any]], list[str]]:
    sl_def = next((s for s in H2H_PLAYERS_SLIDES if s[0] == slide), H2H_PLAYERS_SLIDES[0])
    active = set(sl_def[3])
    mods: list[dict[str, Any]] = []
    for mid, title, can_half in H2H_PLAYERS_MODULE_DEFS:
        mods.append({
            "id": mid,
            "title_fa": title,
            "enabled": mid in active,
            "can_half": can_half,
            "span": "half" if (slide == "slide5" and can_half) else "full",
            "half": slide == "slide5" and can_half,
        })
    return mods, []


def _jersey_svg(p: dict[str, Any], uid: str, sz: int) -> str:
    c1 = p["color"]
    c2 = p["secondary"]
    num = esc(p["number"] if p["number"] != "—" else "10")
    code = esc(p["clubCode"])
    txt_c = _ctr(c1)
    return (
        f'<svg width="{sz}" height="{sz}" viewBox="0 0 220 220" fill="none" style="filter:drop-shadow(0 18px 30px #0000009e)">'
        f'<defs>'
        f'<linearGradient id="jg_{uid}" x1="30" y1="20" x2="190" y2="210" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="#090F20"/></linearGradient>'
        f'<linearGradient id="jrim_{uid}" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{c2}" stop-opacity=".95"/><stop offset=".5" stop-color="{c1}" stop-opacity=".6"/>'
        f'<stop offset="1" stop-color="#ffffff" stop-opacity=".2"/></linearGradient>'
        f'<clipPath id="jclip_{uid}"><path d="M68 28 L88 22 C96 34 124 34 132 22 L152 28 L200 64 L180 104 L158 92 L162 200 L58 200 L62 92 L40 104 L20 64 Z"/></clipPath>'
        f'</defs>'
        f'<circle cx="110" cy="112" r="88" fill="{c1}" fill-opacity=".16"/>'
        f'<g clip-path="url(#jclip_{uid})">'
        f'<rect x="16" y="16" width="188" height="190" fill="url(#jg_{uid})"/>'
        f'<path d="M16 146 L204 56 L204 82 L16 172 Z" fill="{c2}" fill-opacity=".16"/>'
        f'<path d="M16 184 L204 94 L204 108 L16 198 Z" fill="{c2}" fill-opacity=".10"/>'
        f'<rect x="88" y="20" width="44" height="184" fill="#ffffff" fill-opacity=".06"/>'
        f'<path d="M22 60 L44 106 L34 112 L14 66 Z" fill="{c2}" fill-opacity=".85"/>'
        f'<path d="M198 60 L176 106 L186 112 L206 66 Z" fill="{c2}" fill-opacity=".85"/>'
        f'<path d="M84 20 C96 42 124 42 136 20 L144 26 C128 52 92 52 76 26 Z" fill="{c2}" fill-opacity=".92"/>'
        f'<ellipse cx="110" cy="34" rx="76" ry="30" fill="#ffffff" fill-opacity=".14"/></g>'
        f'<path d="M68 28 L88 22 C96 34 124 34 132 22 L152 28 L200 64 L180 104 L158 92 L162 200 L58 200 L62 92 L40 104 L20 64 Z" stroke="url(#jrim_{uid})" stroke-width="3.5" stroke-linejoin="round"/>'
        f'<rect x="122" y="60" width="30" height="20" rx="6" fill="#060C1CE6" stroke="{c2}" stroke-opacity=".65" stroke-width="1.5"/>'
        f'<text x="137" y="74" text-anchor="middle" fill="#F8FAFC" font-family="Space Grotesk,JetBrains Mono,sans-serif" font-weight="800" font-size="10" letter-spacing="1">{code}</text>'
        f'<circle cx="78" cy="70" r="8" fill="#060C1CC0" stroke="{c2}" stroke-opacity=".45" stroke-width="1.2"/>'
        f'<path d="M74 66 L82 74 M82 66 L74 74" stroke="#E62E45" stroke-width="2" stroke-linecap="round"/>'
        f'<text x="110" y="156" text-anchor="middle" fill="{txt_c}" fill-opacity=".96" font-family="Space Grotesk,sans-serif" font-weight="800" font-size="68" letter-spacing="-2" style="filter:drop-shadow(0 6px 12px #00000080)">{num}</text>'
        f'<line x1="64" y1="192" x2="156" y2="192" stroke="{c2}" stroke-opacity=".45" stroke-width="2.5" stroke-linecap="round"/></svg>'
    )


def _rating_ring(val: float, color: str, size: int = 74) -> str:
    num = max(0.0, min(10.0, float(val or 8.0)))
    r = 30.0
    circ = 2.0 * math.pi * r
    dash = (num / 10.0) * circ
    return (
        f'<div class="xgp-badge" style="width:{size}px;height:{size}px;border:1.5px solid {color}55;flex-shrink:0">'
        f'<svg width="{size}" height="{size}" viewBox="0 0 72 72" style="position:absolute;inset:0;transform:rotate(-90deg)">'
        f'<circle cx="36" cy="36" r="30" fill="none" stroke="#ffffff18" stroke-width="5"/>'
        f'<circle cx="36" cy="36" r="30" fill="none" stroke="{color}" stroke-width="5.5" stroke-linecap="round" '
        f'stroke-dasharray="{dash:.1f} {circ:.1f}" style="filter:drop-shadow(0 0 6px {color})"/></svg>'
        f'<div class="fcol" style="align-items:center;line-height:1;position:relative;z-index:2">'
        f'<span style="font-weight:900;color:#fff;font-size:{round(size*0.34)}px">{_fa(_f1(num))}</span>'
        f'<span class="fm" style="font-weight:800;color:#94A3B8;font-size:{round(size*0.13)}px;margin-top:2px">XGP</span>'
        f'</div></div>'
    )


def _pct_ring(pct: Any, col: str, active: bool) -> str:
    v = max(1, min(99, int(float(pct or 50))))
    r = 11.0
    circ = 2.0 * math.pi * r
    dash = (v / 100.0) * circ
    sc = col if active else "#64748B"
    filt = f"filter:drop-shadow(0 0 4px {col})" if active else ""
    tc = "#FFFFFF" if active else "#94A3B8"
    return (
        f'<div class="fc" style="position:relative;width:28px;height:28px;flex-shrink:0">'
        f'<svg width="28" height="28" viewBox="0 0 28 28" style="position:absolute;inset:0;transform:rotate(-90deg)">'
        f'<circle cx="14" cy="14" r="11" fill="#050b18" stroke="#ffffff18" stroke-width="2.4"/>'
        f'<circle cx="14" cy="14" r="11" fill="none" stroke="{sc}" stroke-width="2.6" stroke-linecap="round" '
        f'stroke-dasharray="{dash:.1f} {circ:.1f}" style="{filt}"/></svg>'
        f'<span class="fm" style="position:relative;z-index:2;font-weight:800;font-size:9.5px;line-height:1;color:{tc}">{v}</span></div>'
    )


def _mh(title: str, right_html: str, bar_col: str = "#E62E45") -> str:
    return (
        f'<div class="mh fbw">'
        f'<div class="fi" style="gap:10px;min-width:0">'
        f'<span style="width:8px;height:22px;border-radius:99px;background:{bar_col};flex-shrink:0"></span>'
        f'<h3 class="mt">{esc(title)}</h3></div>{right_html}</div>'
    )


def _legend(p1: dict[str, Any], p2: dict[str, Any]) -> str:
    return (
        f'<div class="fi" style="gap:14px;font-size:15px;font-weight:800;flex-shrink:0">'
        f'<span class="fi" style="gap:7px"><span style="width:12px;height:12px;border-radius:50%;background:{p1["color"]};box-shadow:0 0 10px {p1["color"]}"></span>{esc(p1["name"])}</span>'
        f'<span class="fi" style="gap:7px"><span style="width:12px;height:12px;border-radius:50%;background:{p2["color"]};box-shadow:0 0 10px {p2["color"]}"></span>{esc(p2["name"])}</span>'
        f'</div>'
    )


def _stat_edges(p1: dict[str, Any], p2: dict[str, Any]) -> tuple[int, int]:
    w1 = w2 = 0
    s2_list = p2["stats"]
    for i, s1 in enumerate(p1["stats"]):
        v1 = float(s1.get("v") or 0.0)
        v2 = float((s2_list[i] if i < len(s2_list) else {}).get("v") or 0.0)
        if v1 > v2:
            w1 += 1
        elif v2 > v1:
            w2 += 1
    return w1, w2


def _build_hero(p1: dict[str, Any], p2: dict[str, Any], header_mode: str, is_dense: bool, is_wide: bool) -> str:
    c1, c2 = p1["color"], p2["color"]
    w1, w2 = _stat_edges(p1, p2)
    tot = max(1, w1 + w2)
    pct1 = max(18, min(82, round((w1 / tot) * 100)))
    pct2 = 100 - pct1

    if header_mode == "compact":
        def _cside(p: dict[str, Any], uid: str, rev: bool) -> str:
            if p.get("photoUrl"):
                av = f'<div style="width:72px;height:72px;border-radius:16px;overflow:hidden;border:2px solid {p["color"]}88;background:#060D1E;flex-shrink:0"><img src="{esc(p["photoUrl"])}" style="width:100%;height:100%;object-fit:cover"/></div>'
            else:
                av = f'<div style="flex-shrink:0">{_jersey_svg(p, "c_" + uid, 74)}</div>'
            jc = "justify-content:flex-end;text-align:left" if rev else ""
            info = (
                f'<div style="min-width:0;{("text-align:left" if rev else "")}">'
                f'<div class="fd" dir="ltr" style="font-size:11px;font-weight:800;letter-spacing:.18em;color:#94A3B8">{esc(p["en"])}</div>'
                f'<div style="font-size:26px;font-weight:900;color:#fff;line-height:1.1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(p["name"])}</div>'
                f'<div class="fi" style="gap:7px;margin-top:2px;font-size:15px;font-weight:700;color:{p["color"]};{jc}">'
                f'<span>{esc(p["club"])}</span><span style="color:#64748B">•</span><span class="fm">#{esc(p["number"])}</span></div></div>'
            )
            inner = (info + av) if rev else (av + info)
            return f'<div class="fi" style="grid-column:span 4;gap:12px;min-width:0;{jc}">{inner}</div>'

        return (
            f'<div class="cribbon" style="padding:14px 22px;display:flex;flex-direction:column;gap:12px">'
            f'<div style="position:absolute;inset:0;pointer-events:none;background:radial-gradient(circle at 90% 50%,{c1}2b,transparent 42%),radial-gradient(circle at 10% 50%,{c2}2b,transparent 42%)"></div>'
            f'<div style="position:absolute;top:0;right:0;bottom:0;width:6px;background:{c1}"></div>'
            f'<div style="position:absolute;top:0;left:0;bottom:0;width:6px;background:{c2}"></div>'
            f'<div style="display:grid;grid-template-columns:repeat(11,1fr);align-items:center;gap:12px;position:relative;z-index:2">'
            f'{_cside(p1, "p1", False)}'
            f'<div class="fcol" style="grid-column:span 3;align-items:center;justify-content:center;gap:6px">'
            f'<div class="fi" style="gap:8px">{_rating_ring(p1["xgp"], c1, 54)}'
            f'<div class="fd" style="padding:5px 12px;border-radius:12px;background:#E62E45;color:#fff;font-weight:800;font-size:17px;box-shadow:0 6px 18px #e62e4577;border:1px solid #ffffff44">VS</div>'
            f'{_rating_ring(p2["xgp"], c2, 54)}</div>'
            f'<span class="fm" style="font-size:10.5px;font-weight:800;letter-spacing:.18em;color:#94A3B8">XGP INDEX DUEL</span></div>'
            f'{_cside(p2, "p2", True)}</div>'
            f'<div class="pc" style="position:relative;z-index:2">'
            f'<div class="ps" style="width:{pct1}%;background:linear-gradient(90deg,{c1}cc,{c1});color:{_ctr(c1)}">{_fa(w1)} برتری آماری</div>'
            f'<div class="ps" style="width:{pct2}%;background:linear-gradient(90deg,{c2},{c2}cc);color:{_ctr(c2)}">{_fa(w2)} برتری آماری</div>'
            f'</div></div>'
        )

    j_sz = 108 if is_dense else (142 if is_wide else 130)
    r_sz = 56 if is_dense else (66 if is_wide else 72)
    name_sz = 25 if is_dense else (32 if is_wide else 36)
    gnum_sz = 102 if is_dense else (140 if is_wide else 168)
    lead1 = p1["xgp"] >= p2["xgp"]

    def _pcard(p: dict[str, Any], uid: str, is_right: bool, is_lead: bool) -> str:
        if p.get("photoUrl"):
            vis = f'<div class="fc" style="position:relative;width:100%;height:{j_sz}px;overflow:hidden"><img src="{esc(p["photoUrl"])}" class="pstage-cutout" style="height:100%;width:auto;object-fit:contain;filter:drop-shadow(0 16px 26px #000000b0)"/></div>'
        else:
            vis = f'<div class="fc" style="position:relative;width:100%;height:{j_sz}px">{_jersey_svg(p, "h_" + uid, j_sz)}</div>'
        top_badge = ""
        gpos = "left:12px" if is_right else "right:12px"
        aura_x = "80%" if is_right else "20%"
        pad = "11px" if is_dense else "15px"
        role_html = "" if is_dense else f'<div style="font-size:15px;font-weight:700;margin-top:3px;color:{p["color"]}">{esc(p["roleTag"])}</div>'
        return (
            f'<div class="pstage fcol" style="grid-column:span 5;justify-content:space-between;padding:{pad};border-top:3.5px solid {p["color"]}">'
            f'<div style="position:absolute;inset:0;pointer-events:none;background:radial-gradient(circle at {aura_x} 25%,{p["color"]}38,transparent 62%)"></div>'
            + (f'<div class="ghost-num" style="font-size:{gnum_sz}px;{gpos}">{esc(p["number"].zfill(2))}</div>' if str(p["number"]).isdigit() else "")
            + f'<div class="fbw" style="position:relative;z-index:2;align-items:flex-start;gap:8px">'
            f'<div class="fcol" style="align-items:flex-start;gap:4px">'
            f'<div class="fi" style="gap:6px"><span style="padding:2px 11px;border-radius:8px;font-size:14.5px;font-weight:800;border:1px solid {p["color"]}66;background:{p["color"]}24;color:{p["color"]}">{esc(p["club"])}</span>{top_badge}</div>'
            f'<span style="font-size:14px;font-weight:700;color:#CBD5E1">{esc(p["pos"])}{(" • #" + _fa(p["number"])) if str(p["number"]).isdigit() else ""}</span></div>'
            f'{_rating_ring(p["xgp"], p["color"], r_sz)}</div>'
            f'<div style="position:relative;z-index:2;margin:2px 0">{vis}</div>'
            f'<div style="position:relative;z-index:2;text-align:center">'
            f'<div class="fd" dir="ltr" style="font-weight:800;letter-spacing:.2em;color:#94A3B8cc;font-size:13px;margin-bottom:2px">{esc(p["en"])}</div>'
            f'<h2 style="margin:0;font-size:{name_sz}px;font-weight:900;color:#fff;line-height:1.05">{esc(p["name"])}</h2>'
            f'{role_html}'
            f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:8px;padding-top:8px;border-top:1px solid rgba(255,255,255,.12)">'
            f'<div style="border-radius:10px;background:rgba(255,255,255,.04);padding:4px"><div style="font-size:11px;font-weight:700;color:#94A3B8">سن</div><div style="font-size:15px;font-weight:900;color:#fff">{_fa(p["age"])}</div></div>'
            f'<div style="border-radius:10px;background:rgba(255,255,255,.04);padding:4px"><div style="font-size:11px;font-weight:700;color:#94A3B8">پای تخصصی</div><div style="font-size:15px;font-weight:900;color:#fff">{esc(p["foot"])}</div></div>'
            f'<div style="border-radius:10px;background:rgba(255,255,255,.04);padding:4px"><div style="font-size:11px;font-weight:700;color:#94A3B8">ارزش بازار</div><div class="fm" dir="ltr" style="font-size:15px;font-weight:900;color:{p["color"]}">{esc(p["value"])}</div></div>'
            f'</div></div></div>'
        )

    dia_sz = 54 if is_dense else 70
    vs_fs = 22 if is_dense else 28
    return (
        f'<div style="display:grid;grid-template-columns:repeat(12,1fr);align-items:stretch;gap:12px">'
        f'{_pcard(p1, "p1", True, lead1)}'
        f'<div class="fcol" style="grid-column:span 2;align-items:center;justify-content:center;gap:12px;padding:0 4px">'
        f'<div style="width:2px;flex:1;max-height:70px;background:linear-gradient(to bottom,transparent,#E62E45)"></div>'
        f'<div class="fc" style="position:relative;margin:4px 0">'
        f'<div style="position:absolute;width:92px;height:92px;border-radius:50%;border:1px dashed #e62e4559"></div>'
        f'<div style="width:{dia_sz}px;height:{dia_sz}px;border-radius:18px;transform:rotate(45deg);background:#E62E45;box-shadow:0 0 40px rgba(230,46,69,.65);border:2px solid rgba(255,255,255,.35)"></div>'
        f'<span class="fd" style="position:absolute;font-weight:800;font-size:{vs_fs}px;color:#fff">VS</span></div>'
        f'<div style="width:2px;flex:1;max-height:70px;background:linear-gradient(to top,transparent,#E62E45)"></div>'
        f'<div style="width:100%;padding:8px 6px;border-radius:16px;background:rgba(7,15,34,.95);border:1px solid rgba(255,255,255,.15);text-align:center;box-shadow:0 10px 24px #0008">'
        f'<div style="font-size:12px;font-weight:900;color:#CBD5E1">برتری در تقابل</div>'
        f'<div class="fc" style="gap:6px;margin-top:4px">'
        f'<span style="font-size:21px;font-weight:900;line-height:1;color:{c1}">{_fa(w1)}</span>'
        f'<span style="color:#64748B;font-weight:700;font-size:15px">:</span>'
        f'<span style="font-size:21px;font-weight:900;line-height:1;color:{c2}">{_fa(w2)}</span></div></div></div>'
        f'{_pcard(p2, "p2", False, not lead1)}</div>'
    )


def _mod_vitals(p1: dict[str, Any], p2: dict[str, Any], cls: str) -> str:
    c1, c2 = p1["color"], p2["color"]
    rows = []
    for i, s1 in enumerate(p1["stats"][:6]):
        s2 = p2["stats"][i] if i < len(p2["stats"]) else {"v": 0, "d": s1.get("d", 2), "p": 50}
        v1, v2 = float(s1.get("v") or 0.0), float(s2.get("v") or 0.0)
        mx = max(v1, v2, 0.01)
        win1, win2 = v1 > v2, v2 > v1
        d = int(s1.get("d", 2))
        diff = abs(v1 - v2)
        win_col = c1 if win1 else (c2 if win2 else "#94A3B8")
        aura = f"linear-gradient(270deg,{c1}1f,transparent 48%)" if win1 else (f"linear-gradient(90deg,{c2}1f,transparent 48%)" if win2 else "none")
        arrow = "▸" if win1 else ("◂" if win2 else "=")
        fmt_s = lambda val: _fa(f"{val:.{d}f}")
        rows.append(
            f'<div class="vcap" style="background-image:{aura}">'
            f'<div style="display:grid;grid-template-columns:repeat(12,1fr);align-items:center;gap:6px;margin-bottom:4px">'
            f'<div class="fi" style="grid-column:span 4;gap:8px">{_pct_ring(s1.get("p", 50), c1, win1)}'
            f'<span style="font-size:20px;font-weight:900;line-height:1;color:{c1 if win1 else "#CBD5E1"}">{fmt_s(v1)}</span></div>'
            f'<div class="fc" style="grid-column:span 4;min-width:0"><span style="font-size:15px;font-weight:800;color:#F1F5F9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(s1.get("k", ""))}</span></div>'
            f'<div class="fi" style="grid-column:span 4;justify-content:flex-end;gap:8px">'
            f'<span style="font-size:20px;font-weight:900;line-height:1;color:{c2 if win2 else "#CBD5E1"}">{fmt_s(v2)}</span>'
            f'{_pct_ring(s2.get("p", 50), c2, win2)}</div></div>'
            f'<div style="display:grid;grid-template-columns:repeat(11,1fr);align-items:center;gap:8px">'
            f'<div class="vtrack hs" style="grid-column:span 5"><div class="vfill" style="width:{(v1/mx)*100:.1f}%;background:linear-gradient(270deg,{c1},{c1 if win1 else c1+"77"});box-shadow:{"0 0 12px "+c1+"77" if win1 else "none"}"><div class="vseg"></div></div></div>'
            f'<div class="fc" style="grid-column:span 1"><span class="vdelta" dir="ltr" style="color:{win_col};border-color:{win_col}55;background:{win_col}18">{arrow}{fmt_s(diff)}</span></div>'
            f'<div class="vtrack as" style="grid-column:span 5"><div class="vfill" style="width:{(v2/mx)*100:.1f}%;background:linear-gradient(90deg,{c2},{c2 if win2 else c2+"77"});box-shadow:{"0 0 12px "+c2+"77" if win2 else "none"}"><div class="vseg"></div></div></div>'
            f'</div></div>'
        )
    right = '<span class="fm" style="font-size:13.5px;font-weight:800;color:#CBD5E1;padding:3px 10px;border-radius:8px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1)">PER 90 • PERCENTILE RINGS</span>'
    return f'<div class="xm {cls}">{_mh("میدان نبرد آمارهای کلیدی (در ۹۰ دقیقه)", right)}<div class="fcol" style="flex:1;justify-content:space-between;gap:5px">{"".join(rows)}</div></div>'


def _mod_radar(p1: dict[str, Any], p2: dict[str, Any], cls: str) -> str:
    c1, c2 = p1["color"], p2["color"]
    v1, v2 = [int(x) for x in p1["radar"][:8]], [int(x) for x in p2["radar"][:8]]
    cx, cy, R, R_out = 460.0, 235.0, 148.0, 166.0

    def _pts(vals: list[int]) -> list[tuple[float, float]]:
        out = []
        for i, v in enumerate(vals):
            a = math.radians(i * 45 - 90)
            r = max(16, min(100, v)) / 100.0 * R
            out.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        return out

    def _ring(k: float) -> str:
        return " ".join(f"{cx + R*k*math.cos(math.radians(i*45-90)):.1f},{cy + R*k*math.sin(math.radians(i*45-90)):.1f}" for i in range(8))

    a1, a2 = _pts(v1), _pts(v2)
    poly1 = " ".join(f"{x:.1f},{y:.1f}" for x, y in a1)
    poly2 = " ".join(f"{x:.1f},{y:.1f}" for x, y in a2)

    outer_arcs = []
    for i in range(8):
        col = c1 if v1[i] >= v2[i] else c2
        a_s, a_e = math.radians(i * 45 - 90 - 17), math.radians(i * 45 - 90 + 17)
        x1, y1 = cx + R_out * math.cos(a_s), cy + R_out * math.sin(a_s)
        x2, y2 = cx + R_out * math.cos(a_e), cy + R_out * math.sin(a_e)
        outer_arcs.append(f'<path d="M{x1:.1f} {y1:.1f} A{R_out} {R_out} 0 0 1 {x2:.1f} {y2:.1f}" stroke="{col}" stroke-width="5" stroke-linecap="round" opacity=".9" style="filter:drop-shadow(0 0 6px {col})"/>')

    ticks = []
    for i in range(32):
        a = math.radians(i * 11.25 - 90)
        r1, r2 = R + 6, R + (14 if i % 4 == 0 else 9)
        ticks.append(f'<line x1="{cx+r1*math.cos(a):.1f}" y1="{cy+r1*math.sin(a):.1f}" x2="{cx+r2*math.cos(a):.1f}" y2="{cy+r2*math.sin(a):.1f}" stroke="#ffffff33" stroke-width="{1.8 if i%4==0 else 1}"/>')

    axes = "".join(f'<line x1="{cx}" y1="{cy}" x2="{cx+R*math.cos(math.radians(i*45-90)):.1f}" y2="{cy+R*math.sin(math.radians(i*45-90)):.1f}"/>' for i in range(8))
    labels = []
    for i, lb in enumerate(RADAR_LABELS):
        a = math.radians(i * 45 - 90)
        lr = R_out + 34
        x, y = cx + lr * math.cos(a), cy + lr * math.sin(a)
        anc = "middle" if abs(math.cos(a)) < 0.2 else ("start" if math.cos(a) > 0 else "end")
        dy = 14 if math.sin(a) > 0.7 else (-12 if math.sin(a) < -0.7 else 2)
        w1 = v1[i] >= v2[i]
        labels.append(
            f'<g><text x="{x:.1f}" y="{y+dy:.1f}" text-anchor="{anc}" fill="#F8FAFC" font-family="Vazirmatn" font-weight="800" font-size="19">{lb}</text>'
            f'<text x="{x:.1f}" y="{y+dy+23:.1f}" text-anchor="{anc}" font-family="Vazirmatn" font-weight="900" font-size="18">'
            f'<tspan fill="{c1}" opacity="{"1" if w1 else ".65"}">{_fa(v1[i])}</tspan><tspan fill="#475569"> / </tspan>'
            f'<tspan fill="{c2}" opacity="{"1" if not w1 else ".65"}">{_fa(v2[i])}</tspan></text></g>'
        )

    idx1 = max(range(8), key=lambda i: v1[i] - v2[i])
    idx2 = max(range(8), key=lambda i: v2[i] - v1[i])
    d1, d2 = max(0, v1[idx1] - v2[idx1]), max(0, v2[idx2] - v1[idx2])
    dots2 = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{c2}" stroke="#fff" stroke-width="2"/>' for x, y in a2)
    dots1 = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5.5" fill="{c1}" stroke="#fff" stroke-width="2"/>' for x, y in a1)
    rings_svg = "".join(f'<polygon points="{_ring(k)}" fill="{"#ffffff05" if k==0.5 else "none"}"/>' for k in (1.0, 0.75, 0.5, 0.25))

    return (
        f'<div class="xm {cls}">{_mh("رادار-پیتزای ۸ محوره صدک‌محور", _legend(p1, p2))}'
        f'<div class="fc" style="flex:1;min-height:0" dir="ltr"><svg style="width:100%;height:auto;max-height:365px" viewBox="0 0 920 470" fill="none">'
        f'<defs><radialGradient id="rg1"><stop offset="0" stop-color="{c1}" stop-opacity=".12"/><stop offset="1" stop-color="{c1}" stop-opacity=".38"/></radialGradient>'
        f'<radialGradient id="rg2"><stop offset="0" stop-color="{c2}" stop-opacity=".10"/><stop offset="1" stop-color="{c2}" stop-opacity=".32"/></radialGradient></defs>'
        f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="#050b18" fill-opacity=".75"/>'
        f'<g stroke="#ffffff1f" stroke-width="1.3">{rings_svg}{axes}</g>'
        f'{"".join(ticks)}{"".join(outer_arcs)}'
        f'<polygon points="{poly2}" fill="url(#rg2)" stroke="{c2}" stroke-width="3.6" style="filter:drop-shadow(0 0 10px {c2}66)"/>'
        f'<polygon points="{poly1}" fill="url(#rg1)" stroke="{c1}" stroke-width="4" style="filter:drop-shadow(0 0 10px {c1}66)"/>'
        f'{dots2}{dots1}{"".join(labels)}</svg></div>'
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;padding-top:8px;border-top:1px solid rgba(255,255,255,.1)">'
        f'<div class="fbw" style="border-radius:12px;padding:7px 12px;background:#060D1E;border:1px solid rgba(255,255,255,.1);border-right:4px solid {c1}"><span style="font-size:13.5px;font-weight:700;color:#CBD5E1">برگ برنده {esc(p1["name"])}:</span><span style="font-size:14.5px;font-weight:900;color:{c1}">{RADAR_LABELS[idx1]} (+{_fa(d1)})</span></div>'
        f'<div class="fbw" style="border-radius:12px;padding:7px 12px;background:#060D1E;border:1px solid rgba(255,255,255,.1);border-right:4px solid {c2}"><span style="font-size:13.5px;font-weight:700;color:#CBD5E1">برگ برنده {esc(p2["name"])}:</span><span style="font-size:14.5px;font-weight:900;color:{c2}">{RADAR_LABELS[idx2]} (+{_fa(d2)})</span></div>'
        f'</div></div>'
    )


def _mod_dna(p1: dict[str, Any], p2: dict[str, Any], cls: str) -> str:
    c1, c2 = p1["color"], p2["color"]
    d1, d2 = p1["dna"], p2["dna"]
    rows = []
    for i, (left_l, right_l, left_en, right_en) in enumerate(DNA_AXES):
        x1 = max(8, min(92, int(d1[i] if i < len(d1) else 50)))
        x2 = max(8, min(92, int(d2[i] if i < len(d2) else 50)))
        lo, hi = min(x1, x2), max(x1, x2)
        gap = hi - lo
        grad = f"{c1}, {c2}" if x1 <= x2 else f"{c2}, {c1}"
        rows.append(
            f'<div class="dna-card"><div class="fbw" style="gap:8px;margin-bottom:10px">'
            f'<div class="fi" style="gap:7px"><span style="width:8px;height:8px;border-radius:2px;transform:rotate(45deg);background:#FBBF24"></span><span style="font-size:16px;font-weight:900;color:#fff">{right_l}</span><span class="fm" style="font-size:10px;font-weight:700;color:#64748B">{right_en}</span></div>'
            f'<span style="padding:2px 10px;border-radius:99px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);font-size:12px;font-weight:800;color:#CBD5E1">تفاوت سبک: {_fa(gap)}٪</span>'
            f'<div class="fi" style="gap:7px"><span class="fm" style="font-size:10px;font-weight:700;color:#64748B">{left_en}</span><span style="font-size:16px;font-weight:900;color:#fff">{left_l}</span><span style="width:8px;height:8px;border-radius:2px;transform:rotate(45deg);background:#38BDF8"></span></div></div>'
            f'<div class="dna-track" dir="ltr"><div class="dna-ticks"></div>'
            f'<div class="dna-bridge" style="left:{lo}%;width:{max(1,gap)}%;background:linear-gradient(90deg,{grad})"></div>'
            f'<div class="dna-token" style="left:{x2}%;background:{c2};color:{_ctr(c2)}">{esc(p2["number"])}</div>'
            f'<div class="dna-token" style="left:{x1}%;background:{c1};color:{_ctr(c1)}">{esc(p1["number"])}</div>'
            f'</div></div>'
        )
    return f'<div class="xe {cls}">{_mh("اثر انگشت تاکتیکی (DNA سبک بازی)", _legend(p1, p2), "#FBBF24")}<div class="fcol" style="flex:1;justify-content:space-evenly;gap:9px">{"".join(rows)}</div></div>'


def _mod_pitch(p1: dict[str, Any], p2: dict[str, Any], cls: str) -> str:
    c1, c2 = p1["color"], p2["color"]
    z1 = p1.get("zones") or [{"x": 78, "y": 26, "r": 20}, {"x": 85, "y": 40, "r": 16}]
    z2 = p2.get("zones") or [{"x": 74, "y": 76, "r": 20}, {"x": 82, "y": 64, "r": 16}]
    defs = "".join(
        f'<radialGradient id="hz_{uid}_{i}"><stop offset="0" stop-color="{col}" stop-opacity=".48"/><stop offset=".5" stop-color="{col}" stop-opacity=".18"/><stop offset="1" stop-color="{col}" stop-opacity="0"/></radialGradient>'
        for uid, zs, col in (("p1", z1, c1), ("p2", z2, c2)) for i, _ in enumerate(zs)
    )
    zones_svg = "".join(
        f'<g><circle cx="{z["x"]*8:.1f}" cy="{z["y"]*4.4:.1f}" r="{z["r"]*3.4:.1f}" fill="url(#hz_{uid}_{i})"/><circle cx="{z["x"]*8:.1f}" cy="{z["y"]*4.4:.1f}" r="{z["r"]*2.0:.1f}" fill="none" stroke="{col}" stroke-opacity=".35" stroke-width="1.3" stroke-dasharray="4 4"/></g>'
        for uid, zs, col in (("p1", z1, c1), ("p2", z2, c2)) for i, z in enumerate(zs)
    )
    shots_svg = ""
    for sh, col in ((p1.get("shotsMap") or [], c1), (p2.get("shotsMap") or [], c2)):
        for pt in sh:
            x, y, xg, goal = pt[0], pt[1], pt[2], pt[3]
            r = 6.5 + float(xg or 0.15) * 20
            if goal:
                shots_svg += f'<g><circle cx="{x*8:.1f}" cy="{y*4.4:.1f}" r="{r+4.5:.1f}" fill="none" stroke="{col}" stroke-opacity=".55" stroke-width="1.8"/><circle cx="{x*8:.1f}" cy="{y*4.4:.1f}" r="{r:.1f}" fill="{col}" stroke="#fff" stroke-width="2.4"/></g>'
            else:
                shots_svg += f'<circle cx="{x*8:.1f}" cy="{y*4.4:.1f}" r="{r:.1f}" fill="{col}" fill-opacity=".22" stroke="{col}" stroke-width="2.4"/>'
    v1 = esc(p1.get("vector") or "M 430 96 Q 570 84 676 164")
    v2 = esc(p2.get("vector") or "M 415 352 Q 560 364 672 276")
    return (
        f'<div class="xm {cls}">{_mh("آزمایشگاه تاکتیکی زمین (مناطق نفوذ و شوت)", _legend(p1, p2))}'
        f'<div class="fc" style="flex:1;min-height:0" dir="ltr"><svg style="width:100%;height:auto;max-height:335px" viewBox="0 0 820 440" fill="none">'
        f'<defs>{defs}'
        f'<marker id="arr1" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse"><path d="M0 1L10 5L0 9Z" fill="{c1}"/></marker>'
        f'<marker id="arr2" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse"><path d="M0 1L10 5L0 9Z" fill="{c2}"/></marker></defs>'
        f'<rect x="12" y="12" width="776" height="416" rx="14" fill="#061022" stroke="#ffffff33" stroke-width="2"/>'
        f'<g stroke="#ffffff14" stroke-width="1.2" stroke-dasharray="5 5"><line x1="12" y1="100" x2="788" y2="100"/><line x1="12" y1="156" x2="788" y2="156"/><line x1="12" y1="284" x2="788" y2="284"/><line x1="12" y1="340" x2="788" y2="340"/><line x1="268" y1="12" x2="268" y2="428"/><line x1="532" y1="12" x2="532" y2="428"/></g>'
        f'<rect x="532" y="156" width="136" height="128" fill="#E62E45" fill-opacity=".05" stroke="#E62E45" stroke-opacity=".24" stroke-dasharray="3 3"/>'
        f'<text x="600" y="224" text-anchor="middle" fill="#E62E45" fill-opacity=".38" font-family="JetBrains Mono" font-size="13" font-weight="800">ZONE 14</text>'
        f'<line x1="400" y1="12" x2="400" y2="428" stroke="#ffffff28" stroke-width="1.8"/><circle cx="400" cy="220" r="64" stroke="#ffffff28" stroke-width="1.8"/>'
        f'<rect x="668" y="100" width="120" height="240" stroke="#ffffff3d" stroke-width="2.2"/><rect x="742" y="156" width="46" height="128" stroke="#ffffff33" stroke-width="1.8"/>'
        f'<rect x="788" y="182" width="18" height="76" rx="3" fill="#ffffff12" stroke="#ffffff66" stroke-width="2"/>'
        f'{zones_svg}<path d="{v1}" stroke="{c1}" stroke-width="3.6" stroke-dasharray="9 6" fill="none" marker-end="url(#arr1)"/>'
        f'<path d="{v2}" stroke="{c2}" stroke-width="3.6" stroke-dasharray="9 6" fill="none" marker-end="url(#arr2)"/>{shots_svg}'
        f'<text x="400" y="410" text-anchor="middle" fill="#94A3B8" font-family="Space Grotesk,JetBrains Mono" font-size="12" font-weight="800" letter-spacing="2.5">HALF-SPACES • CARRY VECTORS • ATTACK →</text></svg></div></div>'
    )


def _mod_finishing(p1: dict[str, Any], p2: dict[str, Any], cls: str) -> str:
    def _cockpit(p: dict[str, Any]) -> str:
        col = p["color"]
        diff = p["goals"] - p["xgTotal"]
        sign = "+" if diff >= 0 else ""
        pct = max(0, min(100, int(p["bigChanceConv"])))
        r, cx, cy = 62.0, 95.0, 86.0
        sx, sy = cx + r * math.cos(math.radians(150)), cy + r * math.sin(math.radians(150))
        ex, ey = cx + r * math.cos(math.radians(390)), cy + r * math.sin(math.radians(390))
        tot_arc = (240.0 / 360.0) * 2.0 * math.pi * r
        dash = (pct / 100.0) * tot_arc
        g_dots = max(1, min(24, round((p["goals"] / max(1, p["shots"])) * 24 * 2.2)))
        dots = "".join(
            f'<span style="width:9px;height:9px;border-radius:50%;background:{col if i<g_dots else "rgba(255,255,255,.12)"};box-shadow:{"0 0 6px "+col if i<g_dots else "none"}"></span>'
            for i in range(24)
        )
        d_bg, d_bd, d_tx = ("#10b98122", "#34d39955", "#34D399") if diff >= 0 else ("#f43f5e22", "#fb718555", "#FB7185")
        return (
            f'<div class="dossier fcol" style="padding:14px;justify-content:space-between;gap:9px;border-top:3px solid {col}">'
            f'<div class="fbw" style="gap:8px"><div style="min-width:0"><div style="font-size:20px;font-weight:900;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(p["name"])}</div>'
            f'<div class="fm" style="font-size:11px;font-weight:700;color:#94A3B8">{_fa(p["shots"])} شوت کل فصل</div></div>'
            f'<span class="fm" dir="ltr" style="padding:4px 9px;border-radius:10px;font-size:14px;font-weight:900;background:{d_bg};border:1px solid {d_bd};color:{d_tx}">{sign}{_fa(_f1(diff))} G-xG</span></div>'
            f'<div class="fc" style="position:relative;width:190px;height:136px;margin:0 auto" dir="ltr">'
            f'<svg width="190" height="136" viewBox="0 0 190 136">'
            f'<path d="M{sx:.1f} {sy:.1f} A{r:.0f} {r:.0f} 0 1 1 {ex:.1f} {ey:.1f}" fill="none" stroke="#ffffff14" stroke-width="14" stroke-linecap="round"/>'
            f'<path d="M{sx:.1f} {sy:.1f} A{r:.0f} {r:.0f} 0 1 1 {ex:.1f} {ey:.1f}" fill="none" stroke="{col}" stroke-width="14" stroke-linecap="round" stroke-dasharray="{dash:.1f} {tot_arc*2:.1f}" style="filter:drop-shadow(0 0 10px {col}99)"/></svg>'
            f'<div class="fcol" style="position:absolute;inset:0;align-items:center;justify-content:center;padding-top:12px;line-height:1">'
            f'<span style="font-size:34px;font-weight:900;color:#fff">{_fa(pct)}٪</span>'
            f'<span style="font-size:11.5px;font-weight:800;color:#94A3B8;margin-top:4px">تبدیل موقعیت جدی</span></div></div>'
            f'<div style="padding:7px 9px;border-radius:11px;background:#050B18;border:1px solid rgba(255,255,255,.1)">'
            f'<div class="fbw" style="font-size:11px;font-weight:700;color:#94A3B8;margin-bottom:5px"><span>ماتریس دقت ضربات</span><span style="color:{col}">{_fa(round((p["goals"]/max(1,p["shots"]))*100))}٪ نرخ گل</span></div>'
            f'<div class="fi" style="flex-wrap:wrap;gap:4px;justify-content:center">{dots}</div></div>'
            f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;padding-top:8px;border-top:1px solid rgba(255,255,255,.1);text-align:center">'
            f'<div style="border-radius:10px;background:rgba(255,255,255,.04);padding:5px"><div style="font-size:11px;color:#94A3B8;font-weight:700">گل</div><div style="font-size:19px;font-weight:900;color:{col}">{_fa(p["goals"])}</div></div>'
            f'<div style="border-radius:10px;background:rgba(255,255,255,.04);padding:5px"><div style="font-size:11px;color:#94A3B8;font-weight:700">مجموع xG</div><div style="font-size:19px;font-weight:900;color:#fff">{_fa(_f1(p["xgTotal"]))}</div></div>'
            f'<div style="border-radius:10px;background:rgba(255,255,255,.04);padding:5px"><div style="font-size:11px;color:#94A3B8;font-weight:700">xG / شوت</div><div style="font-size:19px;font-weight:900;color:#6EE7B7">{_fa(_f2(p["xgPerShot"]))}</div></div>'
            f'</div></div>'
        )
    return (
        f'<div class="xm {cls}">{_mh("آزمایشگاه تمام‌کنندگی (Goals vs xG)", "<span class=fm style=font-size:15px;font-weight:800;color:#6EE7B7>CLINICAL LAB</span>", "#34D399")}'
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:auto 0">{_cockpit(p1)}{_cockpit(p2)}</div></div>'
    )


def _mod_trend(p1: dict[str, Any], p2: dict[str, Any], cls: str) -> str:
    c1, c2 = p1["color"], p2["color"]
    s1, s2 = [float(x) for x in p1["trend"][:10]], [float(x) for x in p2["trend"][:10]]
    mn, mx = min(min(s1), min(s2), 7.2) - 0.35, max(max(s1), max(s2), 9.8) + 0.35
    W, H, px, py = 900.0, 210.0, 44.0, 28.0
    pW, pH = W - px * 2, H - py * 2

    def _pts(arr: list[float]) -> list[tuple[float, float, float]]:
        n = max(1, len(arr) - 1)
        return [(px + (i / n) * pW, py + pH - ((v - mn) / max(0.1, mx - mn)) * pH, v) for i, v in enumerate(arr)]

    def _path(pts: list[tuple[float, float, float]]) -> str:
        return " ".join((f"M{x:.1f} {y:.1f}" if i == 0 else f"L{x:.1f} {y:.1f}") for i, (x, y, _) in enumerate(pts))

    pts1, pts2 = _pts(s1), _pts(s2)
    d1, d2 = _path(pts1), _path(pts2)
    avg1 = _fa(_f2(sum(s1) / len(s1)))
    avg2 = _fa(_f2(sum(s2) / len(s2)))
    pk1 = max(pts1, key=lambda t: t[2])
    pk2 = max(pts2, key=lambda t: t[2])
    right = (
        f'<div class="fi" style="gap:10px;font-size:19px;font-weight:900">'
        f'<span style="padding:2px 10px;border-radius:10px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.1);color:{c1}">{avg1}</span>'
        f'<span style="color:#64748B">/</span>'
        f'<span style="padding:2px 10px;border-radius:10px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.1);color:{c2}">{avg2}</span></div>'
    )
    dots2 = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{c2}" stroke="#fff" stroke-width="1.8"/>' for x, y, _ in pts2)
    dots1 = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{c1}" stroke="#fff" stroke-width="2"/>'
        f'<text x="{x:.1f}" y="{H+30:.0f}" text-anchor="middle" fill="#CBD5E1" font-family="Vazirmatn" font-weight="800" font-size="18">بازی {_fa(i+1)}</text>'
        for i, (x, y, _) in enumerate(pts1)
    )
    return (
        f'<div class="xm {cls}">{_mh("روند فرم در ۱۰ بازی اخیر (امتیاز XGP)", right)}'
        f'<div class="fi" style="flex:1" dir="ltr"><svg style="width:100%;height:auto;max-height:250px" viewBox="0 0 {W:.0f} {H+46:.0f}" fill="none">'
        f'<defs><linearGradient id="tg1" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{c1}" stop-opacity=".34"/><stop offset="1" stop-color="{c1}" stop-opacity="0"/></linearGradient>'
        f'<linearGradient id="tg2" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{c2}" stop-opacity=".18"/><stop offset="1" stop-color="{c2}" stop-opacity="0"/></linearGradient></defs>'
        f'<g stroke="#ffffff18" stroke-width="1.4" stroke-dasharray="6 6"><line x1="{px}" y1="{py}" x2="{W-px}" y2="{py}"/><line x1="{px}" y1="{py+pH/2}" x2="{W-px}" y2="{py+pH/2}"/><line x1="{px}" y1="{py+pH}" x2="{W-px}" y2="{py+pH}"/></g>'
        f'<path d="{d2} L {pts2[-1][0]:.1f} {py+pH:.1f} L {pts2[0][0]:.1f} {py+pH:.1f} Z" fill="url(#tg2)"/>'
        f'<path d="{d1} L {pts1[-1][0]:.1f} {py+pH:.1f} L {pts1[0][0]:.1f} {py+pH:.1f} Z" fill="url(#tg1)"/>'
        f'<path d="{d2}" stroke="{c2}" stroke-width="4.2" fill="none" stroke-linecap="round"/><path d="{d1}" stroke="{c1}" stroke-width="4.8" fill="none" stroke-linecap="round"/>'
        f'{dots2}{dots1}'
        f'<g transform="translate({pk1[0]:.1f},{max(16.0,pk1[1]-22):.1f})"><rect x="-26" y="-13" width="52" height="22" rx="8" fill="#060D1E" stroke="{c1}" stroke-width="1.6"/><text x="0" y="3" text-anchor="middle" fill="{c1}" font-family="Space Grotesk" font-weight="800" font-size="13">★ {_f1(pk1[2])}</text></g>'
        f'<g transform="translate({pk2[0]:.1f},{max(16.0,pk2[1]-22):.1f})"><rect x="-26" y="-13" width="52" height="22" rx="8" fill="#060D1E" stroke="{c2}" stroke-width="1.6"/><text x="0" y="3" text-anchor="middle" fill="{c2}" font-family="Space Grotesk" font-weight="800" font-size="13">★ {_f1(pk2[2])}</text></g>'
        f'</svg></div></div>'
    )


def _mod_impact(p1: dict[str, Any], p2: dict[str, Any], cls: str) -> str:
    def _dos(p: dict[str, Any]) -> str:
        col = p["color"]
        return (
            f'<div class="dossier fcol" style="padding:14px;justify-content:space-between;gap:10px;border-right:5px solid {col}">'
            f'<div class="fbw" style="gap:8px"><div class="fi" style="gap:10px;min-width:0">'
            f'<span class="fc fd" style="width:40px;height:40px;border-radius:12px;font-weight:800;font-size:17px;flex-shrink:0;background:{col}24;border:1.5px solid {col}66;color:{col}">{esc(p["number"])}</span>'
            f'<div style="min-width:0"><div style="font-size:20px;font-weight:900;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(p["name"])}</div>'
            f'<div style="font-size:13px;font-weight:700;color:{col}">{esc(p["roleTag"])}</div></div></div>'
            f'<div style="text-align:left;flex-shrink:0"><div class="fm" dir="ltr" style="font-size:17px;font-weight:900;color:#fff">{esc(p["value"])}</div><div style="font-size:11px;font-weight:700;color:#94A3B8">ارزش بازار</div></div></div>'
            f'<div class="fi" style="padding:8px 11px;border-radius:11px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.1);gap:8px">'
            f'<svg width="17" height="17" viewBox="0 0 24 24" fill="{col}" style="flex-shrink:0"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>'
            f'<p style="margin:0;font-size:14.5px;color:#F1F5F9;font-weight:700;line-height:1.4">{esc(p["strength"])}</p></div>'
            f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">'
            f'<div style="border-radius:10px;background:#050B18;border:1px solid rgba(255,255,255,.1);padding:6px;text-align:center"><div style="font-size:11px;font-weight:700;color:#94A3B8">دقایق بازی</div><div style="font-size:15.5px;font-weight:900;color:#fff">{_fa(p["mins"])}\'</div></div>'
            f'<div style="border-radius:10px;background:#050B18;border:1px solid rgba(255,255,255,.1);padding:6px;text-align:center"><div style="font-size:11px;font-weight:700;color:#94A3B8">سهم حضور</div><div style="font-size:15.5px;font-weight:900;color:{col}">{_fa(p["minShare"])}٪</div></div>'
            f'<div style="border-radius:10px;background:#050B18;border:1px solid rgba(255,255,255,.1);padding:6px;text-align:center"><div style="font-size:11px;font-weight:700;color:#94A3B8">قد / پا</div><div style="font-size:14px;font-weight:900;color:#E2E8F0">{_fa(p["height"].replace(" سانتی‌متر",""))} • {esc(p["foot"])}</div></div>'
            f'</div></div>'
        )
    return f'<div class="xe {cls}">{_mh("پرونده اسکاوت و ارزش بازار", "<span class=fm style=font-size:15px;font-weight:800;color:#7DD3FC>SCOUT DOSSIER</span>", "#38BDF8")}<div class="fcol" style="gap:12px;margin:auto 0">{_dos(p1)}{_dos(p2)}</div></div>'


def _mod_archetype(p1: dict[str, Any], p2: dict[str, Any], item: dict[str, Any], cls: str) -> str:
    c1, c2 = p1["color"], p2["color"]
    v = item.get("verdict") or {}
    v_title = str(v.get("title") or f"دوئل فنی {p1['name']} در برابر {p2['name']}")
    v_body = str(v.get("body") or f"{p1['name']} با شاخص XGP {_fa(_f1(p1['xgp']))} و {p2['name']} با شاخص {_fa(_f1(p2['xgp']))} دو سبک مکمل و اثرگذار در فصل جاری ارائه داده‌اند.")
    right = '<span class="fm" style="font-size:14px;font-weight:800;color:#FCD34D;padding:3px 10px;border-radius:8px;background:#fbbf241a;border:1px solid #fbbf244d">EDITORIAL VERDICT</span>'
    return (
        f'<div class="xe {cls}">'
        f'<div class="fd" style="position:absolute;left:20px;top:-12px;font-weight:800;font-size:140px;line-height:1;color:rgba(230,46,69,.08);pointer-events:none">“</div>'
        f'<div class="fcol" style="position:relative;z-index:2;flex:1;justify-content:space-between;gap:8px">'
        f'{_mh("حکم تاکتیکی XGPedia", right)}'
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">'
        f'<div class="fi" style="padding:6px 11px;border-radius:11px;background:rgba(6,13,30,.9);border:1px solid rgba(255,255,255,.12);border-right:4px solid {c1};gap:8px">'
        f'<span style="width:9px;height:9px;border-radius:50%;background:{c1};box-shadow:0 0 8px {c1};flex-shrink:0"></span>'
        f'<span style="font-size:14px;font-weight:800;color:#E2E8F0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis"><strong style="color:{c1}">{esc(p1["name"])}:</strong> {esc(p1["edgeTag"])}</span></div>'
        f'<div class="fi" style="padding:6px 11px;border-radius:11px;background:rgba(6,13,30,.9);border:1px solid rgba(255,255,255,.12);border-right:4px solid {c2};gap:8px">'
        f'<span style="width:9px;height:9px;border-radius:50%;background:{c2};box-shadow:0 0 8px {c2};flex-shrink:0"></span>'
        f'<span style="font-size:14px;font-weight:800;color:#E2E8F0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis"><strong style="color:{c2}">{esc(p2["name"])}:</strong> {esc(p2["edgeTag"])}</span></div></div>'
        f'<h4 style="margin:2px 0;font-size:20px;font-weight:900;color:#FCD34D;line-height:1.3">{esc(v_title)}</h4>'
        f'<p style="margin:0;font-size:16px;line-height:1.48;color:#F1F5F9;font-weight:600">{esc(v_body)}</p></div></div>'
    )


@with_sample_badge
def render_h2h_players_html(
    item: dict[str, Any],
    *,
    slide: str = "slide1",
    header_mode: str = "full",
    fmt: str = "4:5",
    theme: str = "classic",
    modules: list[dict[str, Any]] | None = None,
) -> str:
    w, h = H2H_PLAYERS_FORMATS.get(fmt, (1080, 1350))
    is_story = fmt == "9:16"
    is_wide = fmt == "16:9"
    pad_top, pad_bot = (139, 171) if is_story else ((22, 16) if is_wide else (24, 20))

    p1 = _norm_player(item.get("p1"), "#E62E45")
    p2 = _norm_player(item.get("p2"), "#38BDF8")
    from src.xgpedia.providers.pl_badges_free import resolve_distinct_team_colors
    p1["color"], p2["color"] = resolve_distinct_team_colors(_ensure_readable_color(p1["color"]), _ensure_readable_color(p2["color"]))
    p1["color"], p2["color"] = _ensure_readable_color(p1["color"]), _ensure_readable_color(p2["color"])

    if modules is None:
        modules, _ = get_h2h_players_modules(item, slide)
    active_mods = [m for m in modules if m.get("enabled")]
    if not active_mods:
        active_mods = [{"id": "vitals", "span": "full", "enabled": True}]
    is_dense = slide == "slide5" or len(active_mods) >= 4

    mood_bg = "#09102B" if theme == "ucl" else ("#111322" if theme == "gold" else "#0D1730")
    mid_glow = "#f59e0b26" if theme == "gold" else ("#6366f12b" if theme == "ucl" else "#e62e4526")
    aura_bg = (
        f"radial-gradient(circle at 86% 28%,{p1['color']}3d,transparent 48%),"
        f"radial-gradient(circle at 14% 28%,{p2['color']}3d,transparent 48%),"
        f"radial-gradient(circle at 50% 34%,{mid_glow},transparent 54%)"
    )

    hero_html = _build_hero(p1, p2, header_mode, is_dense, is_wide)
    mod_parts: list[str] = []
    for m in active_mods:
        mid = m["id"]
        cls = "mf" if (m.get("span") == "half" and not is_wide) else "w-full"
        if mid == "vitals":
            mod_parts.append(_mod_vitals(p1, p2, cls))
        elif mid == "radar":
            mod_parts.append(_mod_radar(p1, p2, cls))
        elif mid == "dna":
            mod_parts.append(_mod_dna(p1, p2, cls))
        elif mid == "pitch":
            mod_parts.append(_mod_pitch(p1, p2, cls))
        elif mid == "finishing":
            mod_parts.append(_mod_finishing(p1, p2, cls))
        elif mid == "trend":
            mod_parts.append(_mod_trend(p1, p2, cls))
        elif mid == "impact":
            mod_parts.append(_mod_impact(p1, p2, cls))
        elif mid == "archetype":
            mod_parts.append(_mod_archetype(p1, p2, item, cls))

    logo_svg = _brand_logo_img(44)
    comp = str(item.get("competition") or "لیگ برتر انگلیس")
    rnd = _fa(item.get("round") or "مقایسه مستقیم بازیکنان")
    ctx = _fa(item.get("context") or "مقایسه عملکرد فصل جاری")
    league_en = str(item.get("leagueEn") or "PREMIER LEAGUE").upper()
    season = str(item.get("season") or "26/27")
    tag_code = str(item.get("tagCode") or "H2H").upper()
    foot_tag = f"{league_en} {season} {tag_code} • HEAD-TO-HEAD"
    source = str(item.get("source") or "Opta / FPL")

    body_layout = (
        f'<div class="stage" style="display:grid;grid-template-columns:repeat(12,1fr);gap:20px;align-items:stretch">'
        f'<section style="grid-column:span 5;display:flex;flex-direction:column;justify-content:center;border-left:1px solid rgba(255,255,255,.12);padding-left:18px">{hero_html}</section>'
        f'<section id="mg" style="grid-column:span 7;display:grid;grid-template-columns:1fr 1fr;gap:12px;align-content:start">{"".join(mod_parts)}</section></div>'
        if is_wide else
        f'<div class="stage fcol" style="justify-content:space-between;gap:12px">'
        f'<section style="flex-shrink:0">{hero_html}</section>'
        f'<section id="mg" style="flex:1;display:grid;grid-template-columns:1fr 1fr;gap:12px;min-height:0">{"".join(mod_parts)}</section></div>'
    )

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<style>
{build_embedded_font_css()}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:{w}px;height:{h}px;overflow:hidden;font-family:'Vazirmatn',sans-serif;background:{mood_bg};color:#F8FAFC;font-feature-settings:"tnum";font-variant-numeric:tabular-nums}}
.fm{{font-family:'JetBrains Mono','Space Grotesk',monospace}}.fd{{font-family:'Space Grotesk',sans-serif}}
.fi{{display:flex;align-items:center}}.fc{{display:flex;align-items:center;justify-content:center}}.fbw{{display:flex;align-items:center;justify-content:space-between}}.fcol{{display:flex;flex-direction:column}}
.card{{position:relative;width:{w}px;height:{h}px;padding:{pad_top}px 0 {pad_bot}px 0;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;background:{mood_bg}}}
.aura{{position:absolute;inset:0;pointer-events:none;z-index:0;background:{aura_bg}}}
.noise{{position:absolute;inset:0;pointer-events:none;z-index:0;background-image:radial-gradient(#ffffff0d 1px,transparent 0);background-size:18px 18px;opacity:.45}}
.scan{{position:absolute;inset:0;pointer-events:none;z-index:0;background:repeating-linear-gradient(to bottom,#ffffff04 0 1px,#0000 1px 4px)}}
header{{position:relative;z-index:10;padding:12px 36px 8px;flex-shrink:0}}
.stage{{position:relative;z-index:10;flex:1;padding:8px 40px;min-height:0;overflow:hidden}}
footer{{position:relative;z-index:10;padding:10px 44px 10px;flex-shrink:0}}
.xm,.xe{{position:relative;border-radius:22px;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;box-shadow:0 18px 44px -12px #000000a6,inset 0 1px 0 #ffffff1c}}
.xm{{background:linear-gradient(165deg,#101d3be8,#070e1ef7);border:1.5px solid #f8fafc24;padding:13px 18px}}
.xe{{background:linear-gradient(155deg,#132347eb,#070e1ffa);border:1.5px solid #7fa6e842;padding:13px 18px}}
.mh{{padding-bottom:7px;margin-bottom:8px;border-bottom:1px solid rgba(255,255,255,.12);flex-shrink:0}}
.mt{{font-size:21px;font-weight:900;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
#mg .w-full,#mg .mf:last-child:nth-child(odd){{grid-column:1/-1}}
#mg .mf{{grid-column:span 1;min-width:0}}
.pstage{{position:relative;border-radius:24px;overflow:hidden;background:linear-gradient(170deg,#122042e8,#070e1ff7);border:1.5px solid #ffffff26;box-shadow:0 22px 50px -14px #000000a6,inset 0 1px 0 #ffffff26}}
.pstage-cutout{{mask-image:linear-gradient(to bottom,#000 66%,transparent 100%);-webkit-mask-image:linear-gradient(to bottom,#000 66%,transparent 100%)}}
.ghost-num{{position:absolute;top:-10px;font-family:'Space Grotesk',sans-serif;font-weight:800;line-height:.85;letter-spacing:-.05em;pointer-events:none;-webkit-text-stroke:2px rgba(255,255,255,.26);color:rgba(255,255,255,.04);opacity:.85;z-index:1}}
.xgp-badge{{position:relative;display:inline-flex;align-items:center;justify-content:center;border-radius:999px;background:#060c1ce8;box-shadow:0 8px 24px #00000085}}
.vcap{{position:relative;border-radius:13px;padding:4px 12px 5px;background:#060d1ed9;border:1px solid #ffffff16}}
.vtrack{{position:relative;height:9px;background:#0d172e;border:1px solid #ffffff14;overflow:hidden;display:flex;align-items:center}}
.vtrack.hs{{justify-content:flex-end;border-radius:0 99px 99px 0}}.vtrack.as{{justify-content:flex-start;border-radius:99px 0 0 99px}}
.vfill{{position:relative;height:100%}}.vtrack.hs .vfill{{border-radius:0 99px 99px 0}}.vtrack.as .vfill{{border-radius:99px 0 0 99px}}
.vseg{{position:absolute;inset:0;background:repeating-linear-gradient(90deg,transparent 0 12px,#060d1e99 12px 14px)}}
.vdelta{{font-family:'JetBrains Mono',monospace;font-size:11.5px;font-weight:800;padding:2px 7px;border-radius:8px;border:1px solid #ffffff1a;line-height:1.15;white-space:nowrap}}
.dna-card{{position:relative;border-radius:16px;padding:11px 15px 13px;background:#060d1ed9;border:1px solid #ffffff16}}
.dna-track{{position:relative;height:15px;border-radius:99px;background:#0b152b;border:1px solid #ffffff1f}}
.dna-ticks{{position:absolute;inset:0;background:repeating-linear-gradient(90deg,transparent 0 calc(10% - 1px),#ffffff18 calc(10% - 1px) 10%);border-radius:99px}}
.dna-bridge{{position:absolute;top:3px;bottom:3px;border-radius:99px;opacity:.55}}
.dna-token{{position:absolute;top:50%;transform:translate(-50%,-50%);width:28px;height:28px;border-radius:9px;border:2px solid #fff;display:flex;align-items:center;justify-content:center;font-family:'Space Grotesk',sans-serif;font-size:12px;font-weight:800;box-shadow:0 6px 14px #000000a6;z-index:2}}
.cribbon{{position:relative;border-radius:24px;overflow:hidden;background:linear-gradient(135deg,#0d1b38f5,#070e1ffa);border:1.5px solid #ffffff22;box-shadow:0 18px 42px -12px #000000b3}}
.pc{{width:100%;height:32px;border-radius:999px;overflow:hidden;display:flex;background:#050b19;border:1.5px solid #ffffff26}}
.ps{{height:100%;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:15px;white-space:nowrap}}
.dossier{{position:relative;border-radius:18px;overflow:hidden;background:linear-gradient(160deg,#0c1833eb,#060c1cf5);border:1.5px solid #ffffff1c}}
footer,footer .fbw,footer .fi{{flex-wrap:nowrap!important;white-space:nowrap!important;min-width:0!important}}
footer span,footer div{{white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;min-width:0!important}}
</style>
</head>
<body>
<div class="card">
  <div class="aura"></div>
  <div class="noise"></div>
  <svg style="position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0" viewBox="0 0 {w} {h}" fill="none">
    <defs>
      <pattern id="tg" width="54" height="54" patternUnits="userSpaceOnUse"><path d="M54 0H0v54" stroke="#F8FAFC" stroke-opacity=".05"/></pattern>
      <radialGradient id="rf" cx="50%" cy="29%" r="44%"><stop offset="0" stop-color="#E62E45" stop-opacity=".24"/><stop offset=".55" stop-color="#E62E45" stop-opacity=".07"/><stop offset="1" stop-color="#E62E45" stop-opacity="0"/></radialGradient>
      <linearGradient id="splitLine" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#E62E45" stop-opacity="0"/><stop offset=".28" stop-color="#E62E45" stop-opacity=".5"/><stop offset=".55" stop-color="#F8FAFC" stop-opacity=".14"/><stop offset="1" stop-color="#F8FAFC" stop-opacity="0"/></linearGradient>
    </defs>
    <rect width="100%" height="100%" fill="url(#tg)"/>
    <rect x="14" y="14" width="{w-28}" height="{h-28}" rx="20" stroke="#F8FAFC" stroke-opacity=".11" stroke-width="1.5"/>
    <line x1="{w/2:.0f}" y1="14" x2="{w/2:.0f}" y2="{h-14}" stroke="url(#splitLine)" stroke-width="2" stroke-dasharray="7 7"/>
    <circle cx="{w/2:.0f}" cy="{h/2 if is_wide else 340:.0f}" r="155" stroke="#F8FAFC" stroke-opacity=".09" stroke-width="1.5"/>
    <circle cx="{w/2:.0f}" cy="{h/2 if is_wide else 340:.0f}" r="235" stroke="#E62E45" stroke-opacity=".18" stroke-width="1.2" stroke-dasharray="4 7"/>
    <circle cx="{w/2:.0f}" cy="{h/2 if is_wide else 340:.0f}" r="330" stroke="#F8FAFC" stroke-opacity=".06"/>
    <circle cx="{w/2:.0f}" cy="{h/2 if is_wide else 340:.0f}" r="260" fill="url(#rf)"/>
  </svg>
  <div class="scan"></div>
  {_mirror_corners_html(w, h)}
  <header class="fbw" style="gap:16px">
    <div class="fcol" style="align-items:flex-start;gap:6px;min-width:0">
      <div class="fi" style="gap:10px;flex-wrap:wrap">
        <div class="fi" style="padding:5px 18px;border-radius:999px;font-size:20px;font-weight:900;gap:9px;border:1px solid rgba(255,255,255,.2);background:rgba(21,35,71,.9);color:#F8FAFC">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#E62E45" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M8 21h8m-4-4v4m-5-17h10v5a5 5 0 01-10 0V4zM5 6H3v2a3 3 0 003 3h1m12-5h2v2a3 3 0 01-3 3h-1"/></svg>
          <span>{esc(comp)}</span>
        </div>
        <span style="padding:5px 18px;border-radius:999px;font-size:18px;font-weight:800;border:1px solid rgba(230,46,69,.55);background:rgba(230,46,69,.18);color:#FF6B7F">{esc(rnd)}</span>
      </div>
      <div style="font-size:17px;font-weight:700;color:#E2E8F0">{esc(ctx)}</div>
    </div>
    <div class="fi" style="flex-shrink:0" dir="ltr">
      {logo_svg}
    </div>
  </header>
  {body_layout}
  <footer>
    <div style="border-top:1px solid rgba(255,255,255,.12);margin-bottom:8px"></div>
    <div class="fbw" style="gap:14px">
      <div class="fi" style="gap:9px;min-width:0"><span style="width:10px;height:10px;border-radius:50%;background:#E62E45;box-shadow:0 0 10px #E62E45;flex-shrink:0"></span><span dir="ltr" class="fm" style="font-size:16px;font-weight:800;letter-spacing:.12em;color:#F1F5F9">{esc(foot_tag)}</span></div>
      <div class="fi fm" style="gap:10px;flex-shrink:0" dir="ltr"><span style="font-size:18px;font-weight:800;color:#fff">@XGPedia</span><span style="color:#64748B">|</span><span style="font-size:15px;font-weight:600;color:#CBD5E1">{esc(source)}</span></div>
    </div>
  </footer>
</div>
</body>
</html>"""
