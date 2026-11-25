"""کارت «تولدت مبارک اسطوره» (XGPedia Birthday Studio — EDITION 2.0, Slide-Based Mode, D47).

ویژگی‌های اجباری رعایت‌شده:
  - ۱۰۰٪ آفلاین (فونت محلی Vazirmatn/JetBrains Mono/Space Grotesk + لوگوی واقعی SVG برند + بدون CDN)
  - حفظ کامل هر ۳ سبک طراحی مستقل (`poster` پیش‌فرض، `dossier`، `minimal`) × ۳ فرمت (`4:5`, `9:16`, `16:9`)
  - ۶ ماژول تحلیلی قابل انتخاب (`kpis`, `trophies`, `radar`, `timeline`, `quote`, `record`) با رعایت سخت‌گیرانهٔ `null ≠ 0`
  - هم‌ترازی دقیق چهارگوشهٔ قرمز و فاصلهٔ عمودی بالا (+4px) با استاندارد Post-Match (`rect 12px`, brackets `24..44`, `pad_top=24/22/139`)
  - نمایش عکس پرترهٔ واقعی بازیکن با حلقهٔ نورپردازی Rim-Light یا نشان کلکسیونی پیراهن SVG در نبود عکس
  - کنتراست خودکار WCAG >= 4.8، ترتیب امن `esc(fa(...))`، عدم استفاده از `•` کنار ارقام فارسی.
"""
from __future__ import annotations

import math
import re
from typing import Any

from src.xgpedia.render.card_kit.helpers import ensure_dark_bg_contrast, esc, fa
from src.xgpedia.render.cards import _brand_logo_data_uri
from src.xgpedia.render.studio_engine import build_embedded_font_css

BIRTHDAY_DEFAULT_MODE = "poster"

BIRTHDAY_FORMATS: dict[str, tuple[int, int]] = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}

BIRTHDAY_MODES: list[tuple[str, str, str]] = [
    ("poster", "پوستر اسطوره (Collector’s)", "POSTER"),
    ("dossier", "شناسنامه آماری (Dossier)", "DOSSIER"),
    ("minimal", "کاور مینی‌مال لوکس (Magazine)", "MAGAZINE"),
]

_RADAR_LABELS = ("تمام‌کنندگی", "خلاقیت", "دریبل", "هوش فضایی", "ایستگاهی", "بازی بزرگ")


def _rgba(hex_c: str, alpha: float) -> str:
    c = (hex_c or "#E62E45").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    n = int(c, 16) if len(c) == 6 else 0xE62E45
    return f"rgba({(n >> 16) & 255},{(n >> 8) & 255},{n & 255},{alpha})"


def _parse_int(val: Any) -> int:
    s = re.sub(r"[^\d]", "", str(val or ""))
    return int(s) if s else 0


def get_birthday_modules(item: dict[str, Any], mode: str = BIRTHDAY_DEFAULT_MODE) -> tuple[list[dict[str, Any]], list[str]]:
    """استخراج ماژول‌های دارای دیتای واقعی بازیکن برای انتخاب در ربات (قانون null ≠ 0)."""
    kpis = item.get("kpis") if isinstance(item.get("kpis"), dict) else None
    has_kpis = bool(kpis and (kpis.get("apps") is not None or kpis.get("goals") is not None))
    trophies = item.get("trophies") if isinstance(item.get("trophies"), list) else []
    has_trophies = len(trophies) > 0
    radar = item.get("radar") if isinstance(item.get("radar"), list) else []
    has_radar = len(radar) == 6
    timeline = item.get("timeline") if isinstance(item.get("timeline"), list) else []
    has_timeline = len(timeline) > 0
    quote = item.get("quote") if isinstance(item.get("quote"), dict) else None
    has_quote = bool(quote and quote.get("body"))
    record = item.get("record") if isinstance(item.get("record"), dict) else None
    has_record = bool(record and record.get("val") and record.get("title"))

    defaults_by_mode = {
        "poster": {"kpis", "trophies", "quote"},
        "dossier": {"kpis", "radar", "timeline"},
        "minimal": set(),
    }
    def_set = defaults_by_mode.get(mode, {"kpis", "trophies", "quote"})

    specs = [
        ("kpis", "کارنامه دوران حرفه‌ای (بازی/گل)", has_kpis, False),
        ("trophies", "ویترین افتخارات (Trophy Cabinet)", has_trophies, True),
        ("radar", "رادار DNA بازیکن (۶ محور)", has_radar, True),
        ("timeline", "مسیر افتخار و باشگاه‌ها", has_timeline, False),
        ("quote", "یادداشت تحریریه تولد", has_quote, True),
        ("record", "رکورد جاودانه (Milestone)", has_record, False),
    ]
    mods: list[dict[str, Any]] = []
    missing: list[str] = []
    for mid, title_fa, has_data, is_half in specs:
        if has_data:
            mods.append({"id": mid, "title_fa": title_fa, "enabled": mid in def_set, "half": is_half})
        else:
            missing.append(title_fa)
    # اگر هیچ ماژول پیش‌فرضی روشن نبود (مثلاً بازیکن زنده بدون trophy)، اولی‌های موجود را روشن کن
    if mods and not any(m["enabled"] for m in mods) and mode != "minimal":
        for m in mods[:3]:
            m["enabled"] = True
    return mods, missing


def _brand_logo_html() -> str:
    uri = _brand_logo_data_uri(mono=False)
    if uri:
        return f'<div class="bd-brand" dir="ltr"><img src="{uri}" alt="XGPedia" class="bd-brand-img"></div>'
    return '<div class="bd-brand" dir="ltr"><div class="fd bd-brand-txt"><span style="color:#E62E45">XG</span><span style="color:#F8FAFC">Pedia</span></div></div>'


def _portrait_or_emblem_html(item: dict[str, Any], size: int, *, rim_light: bool, uid: str) -> str:
    p_col = ensure_dark_bg_contrast(str(item.get("primary") or "#38BDF8"), bg="#0D1730", min_ratio=4.5)
    s_col = ensure_dark_bg_contrast(str(item.get("secondary") or "#F59E0B"), bg="#0D1730", min_ratio=4.5)
    jersey = item.get("jersey")
    j_disp = fa(jersey) if jersey not in (None, "", 0, "0") else "★"
    j_en = str(jersey) if jersey not in (None, "", 0, "0") else "XG"
    code = esc(str(item.get("code") or "XG")[:6])
    photo_uri = str(item.get("photoDataUri") or "").strip()

    if photo_uri.startswith("data:image/"):
        inner_sz = round(size * 0.84)
        rim_css = (
            f"filter:drop-shadow(0 0 24px {_rgba(p_col, 0.58)}) drop-shadow(0 0 12px {_rgba(s_col, 0.48)}) drop-shadow(0 16px 26px rgba(0,0,0,.75));"
            if rim_light else "filter:drop-shadow(0 16px 26px rgba(0,0,0,.75));"
        )
        return (
            f'<div class="bd-port-wrap" style="width:{size}px;height:{size}px;">'
            f'<svg class="bd-port-ring" viewBox="0 0 320 320" fill="none">'
            f'<defs><linearGradient id="orb_{uid}" x1="0" y1="0" x2="320" y2="320" gradientUnits="userSpaceOnUse">'
            f'<stop offset="0%" stop-color="#FDE68A"/><stop offset="50%" stop-color="{p_col}"/><stop offset="100%" stop-color="#E62E45"/>'
            f'</linearGradient></defs>'
            f'<circle cx="160" cy="160" r="150" stroke="url(#orb_{uid})" stroke-width="2.2" stroke-dasharray="6 8"/>'
            f'<circle cx="160" cy="160" r="134" stroke="{p_col}" stroke-opacity=".45" stroke-width="2.5"/></svg>'
            f'<div class="bd-port-circle" style="width:{inner_sz}px;height:{inner_sz}px;background:radial-gradient(circle at 50% 35%,{_rgba(p_col, 0.30)},#070F22 76%);box-shadow:0 20px 46px rgba(0,0,0,.65),inset 0 0 28px {_rgba(p_col, 0.32)};">'
            f'<img src="{photo_uri}" alt="" class="bd-port-img" style="{rim_css}"></div>'
            f'<div class="bd-port-badge" dir="ltr">'
            f'<span class="fm bd-port-num">#{esc(j_disp)}</span>'
            f'<span class="bd-dot-sm"></span>'
            f'<span class="fm bd-port-code">{code}</span></div></div>'
        )

    # نشان کلکسیونی پیراهن SVG (دقیقاً مطابق birthday.html)
    return (
        f'<div class="bd-port-wrap" style="width:{size}px;height:{size}px;">'
        f'<svg width="{size}" height="{size}" viewBox="0 0 320 320" fill="none" style="filter:drop-shadow(0 20px 36px rgba(0,0,0,.72))">'
        f'<defs>'
        f'<linearGradient id="r_{uid}" x1="20" y1="20" x2="300" y2="300" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0%" stop-color="#FEF3C7"/><stop offset="35%" stop-color="#FBBF24"/><stop offset="70%" stop-color="{p_col}"/><stop offset="100%" stop-color="#E62E45"/></linearGradient>'
        f'<linearGradient id="sh_{uid}" x1="60" y1="30" x2="260" y2="290" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0%" stop-color="#17274F"/><stop offset="55%" stop-color="#0B142C"/><stop offset="100%" stop-color="#060B18"/></linearGradient>'
        f'<linearGradient id="kt_{uid}" x1="90" y1="70" x2="230" y2="240" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0%" stop-color="{p_col}" stop-opacity=".95"/><stop offset="100%" stop-color="{s_col}" stop-opacity=".85"/></linearGradient>'
        f'<clipPath id="cl_{uid}"><path d="M160 32L254 68V154C254 222 212 268 160 286C108 268 66 222 66 154V68Z"/></clipPath>'
        f'</defs>'
        f'<circle cx="160" cy="160" r="150" stroke="url(#r_{uid})" stroke-opacity=".55" stroke-width="1.6" stroke-dasharray="5 7"/>'
        f'<circle cx="160" cy="160" r="136" stroke="#F8FAFC" stroke-opacity=".12" stroke-width="1"/>'
        f'<path d="M160 6V22M160 298V314M6 160H22M298 160H314" stroke="#FBBF24" stroke-opacity=".75" stroke-width="2" stroke-linecap="round"/>'
        f'<path d="M160 24L262 63V156C262 228 216 277 160 296C104 277 58 228 58 156V63Z" fill="{p_col}" fill-opacity=".16"/>'
        f'<g clip-path="url(#cl_{uid})"><rect x="55" y="25" width="210" height="270" fill="url(#sh_{uid})"/>'
        f'<path d="M55 185L265 85V130L55 230Z" fill="{p_col}" fill-opacity=".22"/>'
        f'<path d="M55 245L265 145V172L55 272Z" fill="{s_col}" fill-opacity=".18"/>'
        f'<path d="M126 78L94 96L76 136L104 148L114 126V232H206V126L216 148L244 136L226 96L194 78C185 90 135 90 126 78Z" fill="url(#kt_{uid})" fill-opacity=".22" stroke="{p_col}" stroke-opacity=".55" stroke-width="2"/>'
        f'<ellipse cx="160" cy="52" rx="105" ry="38" fill="#FFFFFF" fill-opacity=".08"/></g>'
        f'<path d="M160 32L254 68V154C254 222 212 268 160 286C108 268 66 222 66 154V68Z" stroke="url(#r_{uid})" stroke-width="4.2"/>'
        f'<path d="M160 41L245 74V152C245 214 207 256 160 274C113 256 75 214 75 152V74Z" stroke="#F8FAFC" stroke-opacity=".16" stroke-width="1.2"/>'
        f'<g fill="#FBBF24"><polygon points="160,52 162.5,58 169,58.5 164,62.5 165.5,69 160,65.5 154.5,69 156,62.5 151,58.5 157.5,58"/>'
        f'<polygon points="136,58 137.8,62.2 142.4,62.6 138.9,65.5 140,70 136,67.5 132,70 133.1,65.5 129.6,62.6 134.2,62.2" opacity=".82"/>'
        f'<polygon points="184,58 185.8,62.2 190.4,62.6 186.9,65.5 188,70 184,67.5 180,70 181.1,65.5 177.6,62.6 182.2,62.2" opacity=".82"/></g>'
        f'<text x="160" y="182" text-anchor="middle" fill="#FFFFFF" font-family="Space Grotesk,sans-serif" font-weight="800" font-size="92" letter-spacing="-3">{esc(j_en)}</text>'
        f'<rect x="104" y="206" width="112" height="36" rx="11" fill="#070E20" fill-opacity=".92" stroke="#FBBF24" stroke-opacity=".55" stroke-width="1.6"/>'
        f'<text x="160" y="230" text-anchor="middle" fill="#FDE68A" font-family="JetBrains Mono,monospace" font-weight="800" font-size="19" letter-spacing="2.5">{code}</text>'
        f'</svg></div>'
    )


def _mod_hdr(title: str, en: str, bar_col: str = "#E62E45") -> str:
    return (
        f'<div class="mh fbw"><div class="fi bd-gap-12">'
        f'<span class="bd-mbar" style="background:{bar_col}"></span>'
        f'<h3 class="mt">{esc(title)}</h3></div>'
        f'<span dir="ltr" class="fm bd-men">{esc(en)}</span></div>'
    )


def _trophy_icon_svg(icon: str) -> str:
    if icon == "ballon":
        return '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#FBBF24" stroke-width="2.1"><circle cx="12" cy="10" r="6"/><path d="M9 19h6m-3-3v3m-4 2h8"/><path d="M9.5 7.5l2.5 2.5 2.5-2.5" stroke-opacity=".7"/></svg>'
    if icon == "wc":
        return '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#FBBF24" stroke-width="2.1"><path d="M8 21h8m-4-4v4m-4-9c0 3 1.8 5 4 5s4-2 4-5V4H8v8z"/><circle cx="12" cy="7" r="2.5"/></svg>'
    if icon == "ucl":
        return '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#FDE68A" stroke-width="2.1"><path d="M7 4h10v6a5 5 0 0 1-10 0V4z"/><path d="M7 6H4v2a3 3 0 0 0 3 3m10-5h3v2a3 3 0 0 1-3 3"/><path d="M12 15v5m-4 1h8"/></svg>'
    return '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#38BDF8" stroke-width="2.1"><polygon points="12 2 15 8.5 22 9.3 17 14 18.2 21 12 17.7 5.8 21 7 14 2 9.3 9 8.5 12 2"/></svg>'


def _render_module(mod: dict[str, Any], item: dict[str, Any], *, is_wide: bool) -> str:
    mid = mod["id"]
    p_col = ensure_dark_bg_contrast(str(item.get("primary") or "#38BDF8"), bg="#0D1730", min_ratio=4.5)
    span_cls = (
        ("bd-span-2" if mid in ("kpis", "timeline", "record") else "bd-span-1")
        if is_wide else ("mf" if mod.get("half") else "bd-w-full")
    )

    if mid == "kpis":
        kpis = item.get("kpis") or {}
        apps_v = kpis.get("apps")
        goals_v = kpis.get("goals")
        assists_v = kpis.get("assists")
        p90_v = kpis.get("p90")
        apps_n, goals_n, ast_n = _parse_int(apps_v), _parse_int(goals_v), _parse_int(assists_v)
        g_per = f"{goals_n / apps_n:.2f}" if (apps_n > 0 and goals_v is not None) else None
        ga_total = goals_n + ast_n if (goals_v is not None and assists_v is not None) else None

        cards_data = []
        if apps_v is not None:
            cards_data.append(("بازی رسمی", str(apps_v), "کل دوران حرفه‌ای", 4, "#94A3B8", "rgba(148,163,184,.16)", False))
        if goals_v is not None:
            sub = f"{fa(g_per)} گل در هر بازی" if g_per else "گل‌های رسمی ثبت‌شده"
            cards_data.append(("گل زده", str(goals_v), sub, 5, "#FBBF24", "rgba(251,191,36,.24)", True))
        if assists_v is not None:
            cards_data.append(("پاس گل", str(assists_v), "خلق و ارسال نهایی", 4, p_col, _rgba(p_col, 0.22), False))
        if p90_v is not None:
            cards_data.append(("مشارکت در ۹۰ دقیقه", str(p90_v), "نرخ اثرگذاری G+A", 5, "#34D399", "rgba(52,211,153,.20)", False))
        if not cards_data:
            return ""
        ga_badge = (
            f'<span class="bd-ga-pill">{esc(fa(f"{ga_total:,}"))} مشارکت گل</span>'
            if ga_total else ""
        )
        grid_cols = len(cards_data)
        cards_html = "".join(
            f'<div class="kpi-card {"kpi-gold" if gold else ""}" style="background:radial-gradient(circle at 18% 12%,{glow},rgba(7,14,32,.92) 72%);">'
            f'<div class="kpi-top-bar" style="background:{"linear-gradient(90deg,#F59E0B,#FEF3C7,#E62E45)" if gold else col}"></div>'
            f'<div class="fbw bd-gap-8"><span class="kpi-l" style="color:{"#FDE68A" if gold else "#CBD5E1"}">{esc(lbl)}</span></div>'
            f'<div class="kpi-v {"gold-text" if gold else ""}">{esc(fa(val))}</div>'
            f'<div class="kpi-sub">{esc(sub)}</div>'
            f'<div class="kpi-bars">'
            + "".join(
                f'<span class="kpi-b" style="background:{("linear-gradient(90deg,#F59E0B,#FDE68A)" if gold else col) if idx < bars else "rgba(255,255,255,.12)"}"></span>'
                for idx in range(5)
            )
            + '</div></div>'
            for lbl, val, sub, bars, col, glow, gold in cards_data
        )
        return (
            f'<div class="xm {span_cls}">'
            f'<div class="mh fbw"><div class="fi bd-gap-12">'
            f'<span class="bd-mbar" style="background:linear-gradient(to bottom,#FCD34D,#E62E45)"></span>'
            f'<h3 class="mt">کارنامه دوران حرفه‌ای</h3></div>'
            f'<div class="fi bd-gap-8">{ga_badge}<span dir="ltr" class="fm bd-men">CAREER</span></div></div>'
            f'<div class="bd-kpi-grid" style="grid-template-columns:repeat({grid_cols},minmax(0,1fr))">{cards_html}</div></div>'
        )

    if mid == "trophies":
        trophies = (item.get("trophies") or [])[:4]
        if not trophies:
            return ""
        items_html = "".join(
            f'<div class="bd-tr-card"><div class="fi bd-gap-12 bd-minw-0">'
            f'<div class="bd-tr-ico">{_trophy_icon_svg(str(tr.get("icon") or "cup"))}</div>'
            f'<span class="bd-tr-lbl">{esc(fa(tr.get("label") or ""))}</span></div>'
            f'<span class="bd-tr-cnt gold-text">{esc(fa(tr.get("count") or ""))}</span></div>'
            for tr in trophies
        )
        return f'<div class="xm {span_cls}">{_mod_hdr("ویترین افتخارات", "TROPHY CABINET", "#FBBF24")}<div class="bd-tr-grid">{items_html}</div></div>'

    if mid == "radar":
        vals = item.get("radar") or []
        if len(vals) != 6:
            return ""
        cx, cy, rad = 320.0, 175.0, 104.0
        pts = []
        for idx, v in enumerate(vals):
            ang = math.radians(60 * idx - 90)
            rr = max(20.0, min(100.0, float(v))) / 100.0 * rad
            pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
        poly_pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)

        def _ring(scale: float) -> str:
            return " ".join(
                f"{cx + rad * scale * math.cos(math.radians(60 * i - 90)):.1f},{cy + rad * scale * math.sin(math.radians(60 * i - 90)):.1f}"
                for i in range(6)
            )

        h = 0.866 * rad + 22
        lbl_pos = (
            (cx, 32.0, "middle"),
            (cx + h, cy - 0.5 * rad + 2, "start"),
            (cx + h, cy + 0.5 * rad + 6, "start"),
            (cx, cy + rad + 32, "middle"),
            (cx - h, cy + 0.5 * rad + 6, "end"),
            (cx - h, cy - 0.5 * rad + 2, "end"),
        )
        rings_svg = "".join(f'<polygon points="{_ring(sc)}"/>' for sc in (1.0, 0.75, 0.5, 0.25))
        dots_svg = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#FBBF24" stroke="#fff" stroke-width="2"/>' for x, y in pts)
        lbls_svg = "".join(
            f'<g><text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anc}" fill="#F8FAFC" font-family="Vazirmatn" font-weight="800" font-size="20">{esc(lbl)}</text>'
            f'<text x="{lx:.1f}" y="{ly + 24:.1f}" text-anchor="{anc}" fill="#FBBF24" font-family="Vazirmatn" font-weight="900" font-size="18">{esc(fa(vals[i]))}</text></g>'
            for i, (lbl, (lx, ly, anc)) in enumerate(zip(_RADAR_LABELS, lbl_pos))
        )
        return (
            f'<div class="xm {span_cls}">{_mod_hdr("رادار DNA بازیکن", "PLAYER DNA", "#E62E45")}'
            f'<div class="bd-radar-wrap" dir="ltr"><svg class="rs" viewBox="0 0 640 350" fill="none">'
            f'<g stroke="#ffffff26" stroke-width="1.4">{rings_svg}'
            f'<line x1="{cx}" y1="{cy - rad}" x2="{cx}" y2="{cy + rad}"/>'
            f'<line x1="{cx + 0.866 * rad:.1f}" y1="{cy - 0.5 * rad:.1f}" x2="{cx - 0.866 * rad:.1f}" y2="{cy + 0.5 * rad:.1f}"/>'
            f'<line x1="{cx + 0.866 * rad:.1f}" y1="{cy + 0.5 * rad:.1f}" x2="{cx - 0.866 * rad:.1f}" y2="{cy - 0.5 * rad:.1f}"/></g>'
            f'<polygon points="{poly_pts}" fill="{p_col}" fill-opacity=".28" stroke="{p_col}" stroke-width="3.6"/>'
            f'{dots_svg}{lbls_svg}</svg></div></div>'
        )

    if mid == "timeline":
        tl = (item.get("timeline") or [])[:4]
        if not tl:
            return ""
        n = len(tl)
        nodes = []
        for idx, st in enumerate(tl):
            c_st = ensure_dark_bg_contrast(str(st.get("color") or "#38BDF8"), bg="#0D1730", min_ratio=4.2)
            is_last = idx == n - 1
            prev_line = (
                f'<div class="bd-tl-line-r" style="background:linear-gradient(to left,{tl[idx - 1].get("color", "#38BDF8")},{c_st})"></div>'
                if idx > 0 else ""
            )
            next_line = (
                f'<div class="bd-tl-line-l" style="background:linear-gradient(to left,{c_st},{tl[idx + 1].get("color", "#38BDF8")})"></div>'
                if not is_last else '<div class="bd-tl-dash"></div>'
            )
            glow = f"0 0 18px {_rgba(c_st, 0.72)},0 0 0 4px rgba(251,191,36,.18)" if is_last else "0 6px 14px rgba(0,0,0,.55)"
            nodes.append(
                f'<div class="bd-tl-col">'
                f'<div class="bd-tl-track">{prev_line}{next_line}'
                f'<div class="bd-tl-dot" style="border-color:{c_st};box-shadow:{glow}"><span style="background:{c_st}"></span></div></div>'
                f'<div class="bd-tl-box {"bd-tl-last" if is_last else ""}">'
                f'<div class="bd-tl-club">{esc(fa(st.get("club") or ""))}</div>'
                f'<div dir="ltr" class="fm bd-tl-yrs">{esc(fa(st.get("years") or ""))}</div>'
                f'<div class="bd-tl-tag">{esc(fa(st.get("tag") or ""))}</div></div></div>'
            )
        return (
            f'<div class="xm {span_cls}">{_mod_hdr("مسیر افتخار و باشگاه‌ها", "CAREER JOURNEY", "#38BDF8")}'
            f'<div class="bd-tl-grid" style="grid-template-columns:repeat({n},minmax(0,1fr))">{"".join(nodes)}</div></div>'
        )

    if mid == "quote":
        q = item.get("quote") or {}
        if not q.get("body"):
            return ""
        return (
            f'<div class="xe {span_cls}">'
            f'{_mod_hdr("یادداشت تحریریه XGPedia", "EDITORIAL TRIBUTE", "#FBBF24")}'
            f'<h4 class="bd-q-title">{esc(fa(q.get("title") or ""))}</h4>'
            f'<p class="bd-q-body">{esc(fa(q.get("body") or ""))}</p>'
            f'<div class="bd-q-foot"><span class="bd-q-dot"></span><span>{esc(fa(q.get("tag") or "پروندهٔ ویژه تولد XGPedia"))}</span></div></div>'
        )

    if mid == "record":
        rec = item.get("record") or {}
        if not (rec.get("val") and rec.get("title")):
            return ""
        return (
            f'<div class="xe {span_cls} bd-rec-bg"><div class="fbw bd-gap-16 bd-my-auto">'
            f'<div class="fcol bd-gap-6 bd-minw-0">'
            f'<div class="fi bd-gap-10"><span class="bd-mbar-sm" style="background:#FBBF24"></span>'
            f'<span dir="ltr" class="fm bd-rec-kicker">OPTA MILESTONE</span></div>'
            f'<h4 class="bd-rec-title">{esc(fa(rec.get("title") or ""))}</h4>'
            f'<p class="bd-rec-desc">{esc(fa(rec.get("desc") or ""))}</p></div>'
            f'<div class="bd-rec-pill"><div dir="ltr" class="fd bd-rec-val gold-crimson-text">{esc(fa(rec.get("val") or ""))}</div>'
            f'<div dir="ltr" class="fm bd-rec-unit">{esc(rec.get("unit") or "")}</div></div></div></div>'
        )
    return ""


def render_birthday_html(
    item: dict[str, Any],
    *,
    mode: str = BIRTHDAY_DEFAULT_MODE,
    fmt: str = "4:5",
    rim_light: bool = True,
    enabled_modules: list[str] | None = None,
) -> str:
    """تولید HTML کامل و ۱۰۰٪ آفلاین برای کارت تولد (پوستر اسطوره / شناسنامه آماری / کاور مینی‌مال)."""
    mode = mode if mode in ("poster", "dossier", "minimal") else BIRTHDAY_DEFAULT_MODE
    w, h = BIRTHDAY_FORMATS.get(fmt, BIRTHDAY_FORMATS["4:5"])
    is_story = fmt == "9:16"
    is_wide = fmt == "16:9"
    is_minimal = mode == "minimal"

    # هم‌ترازی دقیق با استاندارد Post-Match + ۴ پیکسل فاصلهٔ عمودی بالا
    pad_top, pad_bot = (139, 171) if is_story else ((22, 16) if is_wide else (24, 20))

    avail_mods, _ = get_birthday_modules(item, mode)
    if enabled_modules is not None:
        en_set = set(enabled_modules)
        active_mods = [m for m in avail_mods if m["id"] in en_set]
    else:
        active_mods = [m for m in avail_mods if m["enabled"]]

    dense = (not is_minimal) and ((fmt == "4:5" and len(active_mods) > 3) or (fmt != "4:5" and len(active_mods) > 4))

    p_col = ensure_dark_bg_contrast(str(item.get("primary") or "#38BDF8"), bg="#0D1730", min_ratio=4.5)
    s_col = ensure_dark_bg_contrast(str(item.get("secondary") or "#F59E0B"), bg="#0D1730", min_ratio=4.5)

    name_fa = esc(fa(item.get("nameFa") or item.get("nameEn") or "ستاره فوتبال"))
    name_en = esc(str(item.get("nameEn") or "").upper())
    surname_en = esc(str(item.get("surnameEn") or "LEGEND").upper())
    epithet = esc(fa(item.get("epithet") or "ستارهٔ دنیای فوتبال"))
    age_fa = esc(fa(item.get("age") or "—"))
    birth_yr = esc(str(item.get("birthYear") or ""))
    date_fa = esc(fa(item.get("dateFa") or ""))
    date_en = esc(str(item.get("dateEn") or ""))
    club = esc(fa(item.get("club") or "—"))
    nat = esc(fa(item.get("nat") or "—"))
    pos = esc(fa(item.get("pos") or "—"))
    jersey_fa = esc(fa(item.get("jersey"))) if item.get("jersey") not in (None, "", 0, "0") else ""
    source_txt = esc(str(item.get("source") or "Wikipedia / TheSportsDB"))

    # بخش Hero بر اساس سبک طراحی
    if mode == "poster":
        p_sz = 250 if is_wide else (305 if is_story else 260)
        age_sz = 180 if is_wide else (230 if is_story else 204)
        hero_html = (
            f'<div class="bd-hero-poster">'
            f'<div dir="ltr" class="fd bd-wm-surname" style="font-size:{118 if is_wide else 148}px">{surname_en}</div>'
            f'<div class="bd-poster-grid {"bd-poster-wide" if is_wide else ""}">'
            f'<div class="bd-poster-txt {"bd-txt-center" if is_wide else ""}">'
            f'<div class="bd-age-row">'
            f'<span class="bd-age-num gold-crimson-text" style="font-size:{age_sz}px">{age_fa}</span>'
            f'<div class="fcol"><span class="bd-age-fa">ساله شد</span>'
            f'<span dir="ltr" class="fm bd-age-en">YEARS OLD</span></div></div>'
            f'<h1 class="bd-name-h1" style="font-size:{50 if is_wide else 56}px">{name_fa}</h1>'
            f'<p class="bd-epithet">{epithet}</p>'
            f'<div class="fi bd-pills-wrap {"bd-jc-center" if is_wide else ""}">'
            f'<span class="bd-chip"><span class="bd-cdot" style="background:{p_col}"></span>{club}</span>'
            f'<span class="bd-chip">{nat}</span>'
            f'<span class="bd-chip bd-chip-gold">{pos}</span></div></div>'
            f'<div class="fc">{_portrait_or_emblem_html(item, p_sz, rim_light=rim_light, uid="pos")}</div>'
            f'</div></div>'
        )
    elif mode == "dossier":
        p_sz = 186 if is_wide else 194
        meta_cells = [
            ("تولد شمسی", date_fa or "—"),
            ("تولد میلادی", date_en or "—"),
            ("باشگاه", club),
            ("پست تخصصی", pos),
            ("شماره پیراهن", f"#{jersey_fa}" if jersey_fa else "—"),
            ("ملیت", nat),
        ]
        cells_html = "".join(
            f'<div class="bd-dos-cell"><div class="bd-dos-k">{esc(k)}</div><div class="bd-dos-v">{v}</div></div>'
            for k, v in meta_cells
        )
        hero_html = (
            f'<div class="bd-hero-dossier">'
            f'<div class="fbw bd-gap-16">'
            f'<div class="fi bd-gap-16 bd-minw-0">{_portrait_or_emblem_html(item, p_sz, rim_light=rim_light, uid="dos")}'
            f'<div class="fcol bd-gap-6 bd-minw-0">'
            f'<div class="fi bd-gap-8" dir="ltr"><span class="fm bd-dos-badge">PLAYER DOSSIER</span>'
            f'<span class="fm bd-dos-en">{name_en}</span></div>'
            f'<h1 class="bd-name-h1" style="font-size:{42 if is_wide else 46}px">{name_fa}</h1>'
            f'<p class="bd-epithet" style="font-size:19px">{epithet}</p></div></div>'
            f'<div class="bd-dos-age"><span dir="ltr" class="fm bd-dos-age-lbl">NEW AGE</span>'
            f'<span class="bd-dos-age-num gold-text">{age_fa}</span>'
            f'<span dir="ltr" class="fm bd-dos-est">EST. {birth_yr}</span></div></div>'
            f'<div class="bd-dos-grid" style="grid-template-columns:repeat({3 if is_wide else 6},minmax(0,1fr))">{cells_html}</div></div>'
        )
    else:  # minimal cover
        p_sz = 250 if is_wide else (350 if is_story else 300)
        bg_age_sz = 230 if is_wide else (320 if is_story else 270)
        q_body = esc(fa((item.get("quote") or {}).get("body") or epithet))
        rec = item.get("record") if isinstance(item.get("record"), dict) else None
        rec_box = (
            f'<div class="bd-min-rec"><div style="text-align:right">'
            f'<div class="bd-min-rt">{esc(fa(rec.get("title") or ""))}</div>'
            f'<div class="bd-min-rd">{esc(fa(rec.get("desc") or ""))}</div></div>'
            f'<div class="bd-min-rv"><div dir="ltr" class="fd bd-min-rvn gold-crimson-text">{esc(fa(rec.get("val") or ""))}</div>'
            f'<div dir="ltr" class="fm bd-min-rvu">{esc(rec.get("unit") or "")}</div></div></div>'
            if (rec and rec.get("val") and rec.get("title")) else ""
        )
        hero_html = (
            f'<div class="bd-hero-minimal" style="background:radial-gradient(circle at 50% 34%,{_rgba(p_col, 0.26)},rgba(9,16,35,.96) 62%),linear-gradient(180deg,#0E1B39,#060B18)">'
            f'<div class="bd-min-bg-age" style="font-size:{bg_age_sz}px">{age_fa}</div>'
            f'<div class="fi bd-gap-12 bd-z10" dir="ltr"><span class="bd-min-line"></span>'
            f'<span class="fm bd-min-kicker">COLLECTOR’S COVER // {birth_yr}</span><span class="bd-min-line-r"></span></div>'
            f'<div class="bd-z10">{_portrait_or_emblem_html(item, p_sz, rim_light=rim_light, uid="min")}</div>'
            f'<div class="fcol bd-ai-center bd-gap-8 bd-z10" style="max-width:820px">'
            f'<div class="fi bd-gap-10"><span class="gold-pill bd-min-pill">{age_fa} سالگی مبارک</span>'
            f'<span class="bd-min-club">{club} | {nat}</span></div>'
            f'<h1 class="bd-name-h1" style="font-size:{54 if is_wide else 68}px">{name_fa}</h1>'
            f'<div dir="ltr" class="fm bd-min-en">{name_en}</div>'
            f'<p class="bd-min-quote">«{q_body}»</p></div>{rec_box}</div>'
        )

    mods_html = "" if is_minimal else "".join(_render_module(m, item, is_wide=is_wide) for m in active_mods)

    # مختصات دقیق چهارگوشهٔ قرمز هم‌تراز با Post-Match (24..44)
    cx_bg = round(w * 0.74) if is_wide else round(w / 2)
    cy_bg = round(h / 2) if is_wide else round(h * 0.27)
    crh_d = (
        f"M24 44V24H44M{w - 24} 44V24H{w - 44}"
        f"M24 {h - 44}V{h - 24}H44M{w - 24} {h - 44}V{h - 24}H{w - 44}"
    )
    amb_bg = (
        f"radial-gradient(circle at {'76% 45%' if is_wide else '22% 24%'},{_rgba(p_col, 0.28)},transparent 48%),"
        f"radial-gradient(circle at {'24% 65%' if is_wide else '82% 28%'},{_rgba(s_col, 0.22)},transparent 46%),"
        f"radial-gradient(circle at 50% 88%,rgba(230,46,69,.16),transparent 52%)"
    )

    date_pill_txt = f"{date_fa} | {date_en}" if (date_fa and date_en) else (date_fa or date_en or "تولد امروز")
    submeta_parts = [p for p in (club if club != "—" else "", nat if nat != "—" else "", f"شماره {jersey_fa}" if jersey_fa else "") if p]
    submeta_txt = " | ".join(submeta_parts)

    stage_cls = "bd-stage-min" if is_minimal else ("bd-stage-wide" if is_wide else "bd-stage-vert")

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<title>{name_fa} — XGPedia Birthday</title>
<style>
{build_embedded_font_css()}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{w}px;height:{h}px;overflow:hidden;background:#0D1730;color:#F8FAFC;
  font-family:'Vazirmatn',system-ui,sans-serif;font-feature-settings:"tnum";font-variant-numeric:tabular-nums}}
.fm{{font-family:'JetBrains Mono','Space Grotesk',monospace}}
.fd{{font-family:'Space Grotesk','Vazirmatn',sans-serif}}
.fi{{display:flex;align-items:center}}
.fc{{display:flex;align-items:center;justify-content:center}}
.fbw{{display:flex;align-items:center;justify-content:space-between}}
.fcol{{display:flex;flex-direction:column}}
.bd-minw-0{{min-width:0}}.bd-z10{{position:relative;z-index:10}}.bd-my-auto{{margin:auto 0}}.bd-ai-center{{align-items:center}}.bd-jc-center{{justify-content:center}}
.bd-gap-6{{gap:6px}}.bd-gap-8{{gap:8px}}.bd-gap-10{{gap:10px}}.bd-gap-12{{gap:12px}}.bd-gap-16{{gap:16px}}

.gold-text{{background:linear-gradient(135deg,#FEF3C7 0%,#FBBF24 42%,#F59E0B 72%,#FDE68A 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.gold-crimson-text{{background:linear-gradient(135deg,#FEF3C7 0%,#FBBF24 38%,#F59E0B 62%,#E62E45 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.gold-pill{{background:linear-gradient(135deg,rgba(251,191,36,.22),rgba(245,158,11,.08));border:1.5px solid rgba(251,191,36,.48);color:#FDE68A;box-shadow:0 6px 20px rgba(245,158,11,.15),inset 0 1px 0 rgba(254,243,199,.25)}}

.bd-canvas{{position:relative;width:{w}px;height:{h}px;overflow:hidden;background:#0D1730;
  display:flex;flex-direction:column;justify-content:space-between;padding:{pad_top}px 0 {pad_bot}px}}
.bd-ambient{{position:absolute;inset:0;pointer-events:none;z-index:0;background:{amb_bg}}}
.bd-frame-svg{{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0}}
.bd-scanlines{{position:absolute;inset:0;pointer-events:none;z-index:0;background:repeating-linear-gradient(to bottom,#ffffff04 0 1px,#0000 1px 4px)}}

/* Header: هم‌تراز دقیق با استاندارد Post-Match (+4px بالا) */
.bd-header{{position:relative;z-index:10;padding:12px 36px 8px;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-shrink:0}}
.bd-hdr-badge{{padding:6px 20px;border-radius:999px;font-size:21px;font-weight:900;display:inline-flex;align-items:center;gap:10px;white-space:nowrap}}
.bd-date-pill{{padding:6px 16px;border-radius:999px;font-size:18.5px;font-weight:800;background:#e62e4526;border:1px solid #e62e4575;color:#FF7B8D;white-space:nowrap}}
.bd-submeta{{font-size:17.5px;font-weight:700;color:#E2E8F0;margin-top:6px}}
.bd-brand{{display:flex;align-items:center;flex-shrink:0}}
.bd-brand-img{{height:48px;width:auto;display:block;filter:drop-shadow(0 6px 14px rgba(0,0,0,.45))}}
.bd-brand-txt{{font-size:32px;font-weight:800;line-height:1}}

/* Stage */
.bd-stage-vert{{position:relative;z-index:10;flex:1;padding:8px 40px;display:flex;flex-direction:column;justify-content:space-between;gap:{12 if dense else 16}px;min-height:0;overflow:hidden}}
.bd-stage-wide{{position:relative;z-index:10;flex:1;padding:8px 40px;display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:24px;align-items:stretch;min-height:0;overflow:hidden}}
.bd-stage-min{{position:relative;z-index:10;flex:1;padding:8px 40px;display:flex;flex-direction:column;min-height:0;overflow:hidden}}
.bd-wide-hero{{grid-column:span 5;display:flex;flex-direction:column;justify-content:center;min-height:0}}
.bd-wide-mods{{grid-column:span 7;display:grid;grid-template-columns:1fr 1fr;grid-auto-rows:1fr;gap:14px;min-height:0;overflow:hidden}}
.bd-mods-vert{{flex:1;display:grid;grid-template-columns:1fr 1fr;grid-auto-rows:1fr;gap:{12 if dense else 16}px;min-height:0;overflow:hidden}}

/* Portrait / Shield */
.bd-port-wrap{{position:relative;display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.bd-port-ring{{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}}
.bd-port-circle{{position:relative;border-radius:999px;overflow:hidden;border:3px solid rgba(251,191,36,.58)}}
.bd-port-img{{width:100%;height:100%;object-fit:cover;object-position:50% 18%;display:block}}
.bd-port-badge{{position:absolute;bottom:-6px;left:50%;transform:translateX(-50%);padding:4px 16px;border-radius:999px;
  background:rgba(9,18,38,.95);border:1.5px solid rgba(251,191,36,.62);display:flex;align-items:center;gap:8px;box-shadow:0 8px 20px rgba(0,0,0,.6)}}
.bd-port-num{{font-size:17px;font-weight:900;color:#FCD34D}}
.bd-dot-sm{{width:6px;height:6px;border-radius:999px;background:#E62E45}}
.bd-port-code{{font-size:14.5px;font-weight:800;color:#E2E8F0}}

/* Heroes */
.bd-hero-poster{{position:relative;border-radius:26px;overflow:hidden;border:1.5px solid rgba(255,255,255,.15);padding:20px 26px;
  background:linear-gradient(140deg,rgba(16,29,59,.92),rgba(8,14,31,.96));box-shadow:0 22px 54px -14px rgba(0,0,0,.78),inset 0 1px 0 rgba(255,255,255,.16)}}
.bd-wm-surname{{position:absolute;bottom:-18px;left:16px;font-weight:800;text-transform:uppercase;line-height:1;color:transparent;-webkit-text-stroke:1.5px rgba(248,250,252,.07);pointer-events:none}}
.bd-poster-grid{{position:relative;z-index:10;display:grid;grid-template-columns:7fr 5fr;gap:18px;align-items:center}}
.bd-poster-wide{{grid-template-columns:1fr;text-align:center}}
.bd-poster-txt{{display:flex;flex-direction:column;align-items:flex-start;gap:6px;min-width:0}}
.bd-txt-center{{align-items:center}}
.bd-age-row{{display:flex;align-items:baseline;gap:14px}}
.bd-age-num{{font-weight:900;line-height:.86;filter:drop-shadow(0 12px 26px rgba(245,158,11,.28))}}
.bd-age-fa{{font-size:26px;font-weight:900;color:#FCD34D;line-height:1.1}}
.bd-age-en{{font-size:15px;font-weight:700;color:#94A3B8;letter-spacing:.18em}}
.bd-name-h1{{font-weight:900;color:#FFFFFF;line-height:1.08;letter-spacing:-0.015em}}
.bd-epithet{{font-size:21px;font-weight:700;color:#CBD5E1;margin-top:2px}}
.bd-pills-wrap{{flex-wrap:wrap;gap:9px;margin-top:8px}}
.bd-chip{{padding:6px 14px;border-radius:12px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.16);font-size:18px;font-weight:800;color:#F8FAFC;display:inline-flex;align-items:center;gap:8px}}
.bd-chip-gold{{color:#FDE68A}}
.bd-cdot{{width:10px;height:10px;border-radius:999px;flex-shrink:0}}

.bd-hero-dossier{{position:relative;border-radius:24px;overflow:hidden;border:1.5px solid rgba(255,255,255,.15);padding:18px 22px;display:flex;flex-direction:column;gap:14px;
  background:linear-gradient(155deg,rgba(15,28,58,.94),rgba(8,14,30,.97));box-shadow:0 18px 46px -12px rgba(0,0,0,.75)}}
.bd-dos-badge{{padding:3px 10px;border-radius:6px;background:rgba(251,191,36,.18);border:1px solid rgba(251,191,36,.45);font-size:13.5px;font-weight:800;color:#FCD34D}}
.bd-dos-en{{font-size:14.5px;font-weight:700;color:#94A3B8}}
.bd-dos-age{{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:10px 22px;border-radius:18px;background:rgba(7,14,32,.90);border:1.5px solid rgba(251,191,36,.42);flex-shrink:0}}
.bd-dos-age-lbl{{font-size:12.5px;font-weight:800;color:#FCD34D;letter-spacing:.18em}}
.bd-dos-age-num{{font-size:78px;font-weight:900;line-height:.92;margin:2px 0}}
.bd-dos-est{{font-size:13.5px;font-weight:700;color:#94A3B8}}
.bd-dos-grid{{display:grid;gap:8px;padding-top:12px;border-top:1px solid rgba(255,255,255,.12)}}
.bd-dos-cell{{border-radius:12px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.10);padding:8px 10px;text-align:center}}
.bd-dos-k{{font-size:13px;font-weight:700;color:#94A3B8;margin-bottom:2px}}
.bd-dos-v{{font-size:15.5px;font-weight:900;color:#FFFFFF;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}

.bd-hero-minimal{{position:relative;flex:1;border-radius:28px;overflow:hidden;border:1.5px solid rgba(251,191,36,.32);padding:28px 34px;
  display:flex;flex-direction:column;justify-content:space-between;align-items:center;text-align:center;box-shadow:0 28px 70px -12px rgba(0,0,0,.85)}}
.bd-min-bg-age{{position:absolute;top:18px;left:0;right:0;text-align:center;font-weight:900;line-height:1;color:transparent;-webkit-text-stroke:2.5px rgba(251,191,36,.24);pointer-events:none}}
.bd-min-line{{height:1.5px;width:56px;background:linear-gradient(to right,transparent,#FBBF24)}}
.bd-min-line-r{{height:1.5px;width:56px;background:linear-gradient(to left,transparent,#FBBF24)}}
.bd-min-kicker{{font-size:16.5px;font-weight:800;letter-spacing:.26em;color:#FCD34D}}
.bd-min-pill{{padding:5px 18px;border-radius:999px;font-size:21px;font-weight:900}}
.bd-min-club{{padding:5px 16px;border-radius:999px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.16);font-size:19px;font-weight:800;color:#F1F5F9}}
.bd-min-en{{font-size:19px;font-weight:800;letter-spacing:.28em;color:#94A3B8}}
.bd-min-quote{{font-size:22px;font-weight:600;color:rgba(254,243,199,.92);line-height:1.60;margin-top:4px}}
.bd-min-rec{{position:relative;z-index:10;width:100%;max-width:780px;border-radius:18px;background:rgba(7,14,32,.86);border:1.5px solid rgba(251,191,36,.38);padding:14px 22px;display:flex;align-items:center;justify-content:space-between;gap:16px}}
.bd-min-rt{{font-size:20px;font-weight:900;color:#FCD34D}}
.bd-min-rd{{font-size:16.5px;font-weight:700;color:#CBD5E1;margin-top:2px}}
.bd-min-rv{{text-align:left;flex-shrink:0;border-right:1px solid rgba(255,255,255,.14);padding-right:18px}}
.bd-min-rvn{{font-size:44px;font-weight:800;line-height:1}}
.bd-min-rvu{{font-size:12px;font-weight:800;color:#94A3B8;letter-spacing:.14em;margin-top:3px}}

/* Modules */
.xm,.xe{{position:relative;border-radius:{18 if dense else 22}px;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;
  padding:{'12px 18px' if dense else '16px 22px'};box-shadow:0 14px 36px -10px rgba(0,0,0,.55),inset 0 1px 0 rgba(255,255,255,.10)}}
.xm{{background:linear-gradient(165deg,rgba(16,29,59,.88),rgba(9,16,35,.95));border:1.5px solid rgba(248,250,252,.15)}}
.xe{{background:linear-gradient(155deg,rgba(18,31,61,.92),rgba(9,15,32,.97));border:1.5px solid rgba(251,191,36,.28)}}
.bd-w-full,.bd-span-2,.mf:last-child:nth-child(odd){{grid-column:1/-1}}
.mf,.bd-span-1{{grid-column:span 1;min-width:0}}
.mh{{padding-bottom:{7 if dense else 10}px;margin-bottom:{8 if dense else 10}px;border-bottom:1px solid rgba(255,255,255,.12)}}
.bd-mbar{{width:7px;height:24px;border-radius:99px;flex-shrink:0}}
.bd-mbar-sm{{width:6px;height:20px;border-radius:99px;flex-shrink:0}}
.mt{{font-size:{21 if dense else 24}px;font-weight:900;color:#FFFFFF;line-height:1}}
.bd-men{{font-size:15px;font-weight:800;color:#94A3B8;letter-spacing:.08em;text-transform:uppercase}}

.bd-ga-pill{{padding:4px 12px;border-radius:10px;background:rgba(251,191,36,.15);border:1px solid rgba(251,191,36,.40);color:#FDE68A;font-size:14.5px;font-weight:800;white-space:nowrap}}
.bd-kpi-grid{{display:grid;gap:12px;margin:auto 0}}
.kpi-card{{position:relative;border-radius:16px;padding:{'10px 12px' if dense else '13px 15px'};border:1px solid rgba(255,255,255,.14);display:flex;flex-direction:column;justify-content:space-between;gap:6px;overflow:hidden}}
.kpi-gold{{border-color:rgba(251,191,36,.52)}}
.kpi-top-bar{{position:absolute;top:0;left:0;right:0;height:3px}}
.kpi-l{{font-size:{14 if dense else 15.5}px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.kpi-v{{font-size:{29 if dense else 34}px;font-weight:900;line-height:1.15;color:#FFFFFF}}
.kpi-sub{{font-size:{12 if dense else 13}px;font-weight:700;color:#94A3B8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.kpi-bars{{display:grid;grid-template-columns:repeat(5,1fr);gap:4px}}
.kpi-b{{height:5px;border-radius:99px}}

.bd-tr-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:auto 0}}
.bd-tr-card{{border-radius:15px;padding:10px 14px;background:rgba(255,255,255,.045);border:1px solid rgba(251,191,36,.25);display:flex;align-items:center;justify-content:space-between;gap:10px}}
.bd-tr-ico{{width:40px;height:40px;border-radius:11px;background:rgba(245,158,11,.14);border:1px solid rgba(251,191,36,.35);display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.bd-tr-lbl{{font-size:17px;font-weight:800;color:#F1F5F9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.bd-tr-cnt{{font-size:28px;font-weight:900;line-height:1;flex-shrink:0}}

.bd-radar-wrap{{flex:1;display:flex;align-items:center;justify-content:center;min-height:0}}
.rs{{width:100%;height:auto;max-height:{215 if (dense or is_wide) else 255}px}}

.bd-tl-grid{{display:grid;gap:12px;margin:auto 0}}
.bd-tl-col{{display:flex;flex-direction:column;align-items:center;text-align:center;gap:8px;min-width:0}}
.bd-tl-track{{position:relative;width:100%;height:34px;display:flex;align-items:center;justify-content:center}}
.bd-tl-line-r{{position:absolute;top:50%;transform:translateY(-50%);height:3px;left:50%;right:-8px;opacity:.85}}
.bd-tl-line-l{{position:absolute;top:50%;transform:translateY(-50%);height:3px;right:50%;left:-8px;opacity:.85}}
.bd-tl-dash{{position:absolute;top:50%;transform:translateY(-50%);border-top:3px dashed rgba(251,191,36,.75);right:50%;left:6px}}
.bd-tl-dot{{position:relative;z-index:10;width:28px;height:28px;border-radius:999px;background:#091226;border:3px solid;display:flex;align-items:center;justify-content:center}}
.bd-tl-dot span{{width:9px;height:9px;border-radius:999px}}
.bd-tl-box{{width:100%;border-radius:14px;background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.12);padding:9px 10px}}
.bd-tl-last{{border-color:rgba(251,191,36,.42)}}
.bd-tl-club{{font-size:18px;font-weight:900;color:#FFFFFF;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.bd-tl-yrs{{font-size:13.5px;font-weight:700;color:#94A3B8;margin-top:2px}}
.bd-tl-tag{{margin-top:5px;display:inline-block;padding:2px 8px;border-radius:8px;font-size:13px;font-weight:800;background:rgba(255,255,255,.08);color:#FDE68A;max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}

.bd-q-title{{font-size:{22 if dense else 24}px;font-weight:900;color:#FCD34D;line-height:1.3;margin-bottom:4px}}
.bd-q-body{{font-size:{18.5 if dense else 20}px;font-weight:600;color:#F1F5F9;line-height:1.58}}
.bd-q-foot{{padding-top:8px;margin-top:8px;border-top:1px solid rgba(255,255,255,.12);display:flex;align-items:center;gap:8px;font-size:15.5px;font-weight:800;color:#E2E8F0}}
.bd-q-dot{{width:9px;height:9px;border-radius:999px;background:#FBBF24;flex-shrink:0}}

.bd-rec-bg{{background:linear-gradient(135deg,rgba(230,46,69,.16),rgba(12,22,46,.96) 55%,rgba(245,158,11,.14))}}
.bd-rec-kicker{{font-size:14.5px;font-weight:800;color:#FCD34D;letter-spacing:.16em}}
.bd-rec-title{{font-size:25px;font-weight:900;color:#FFFFFF;line-height:1.2}}
.bd-rec-desc{{font-size:18.5px;font-weight:600;color:#E2E8F0;line-height:1.45}}
.bd-rec-pill{{padding:10px 20px;border-radius:16px;background:rgba(7,14,32,.90);border:1.5px solid rgba(251,191,36,.45);text-align:center;flex-shrink:0}}
.bd-rec-val{{font-size:48px;font-weight:800;line-height:1}}
.bd-rec-unit{{font-size:12.5px;font-weight:800;color:#94A3B8;letter-spacing:.14em;margin-top:4px}}

/* Footer: هم‌تراز دقیق با استاندارد Post-Match */
.bd-footer{{position:relative;z-index:10;padding:10px 44px 10px;flex-shrink:0}}
.bd-footer-line{{border-top:1px solid rgba(255,255,255,.14);margin-bottom:8px}}
.bd-foot-dot{{width:11px;height:11px;border-radius:999px;background:#E62E45;box-shadow:0 0 10px #E62E45;flex-shrink:0}}
.bd-foot-tag{{font-size:16.5px;font-weight:800;letter-spacing:.14em;color:#F1F5F9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.bd-foot-handle{{font-size:19.5px;font-weight:800;color:#FFFFFF}}
.bd-foot-src{{font-size:16.5px;font-weight:600;color:#CBD5E1}}
.bd-sep{{color:#64748B}}

footer, footer .fbw, footer .cf-row, footer .fi, footer .cf-left, footer .cf-right, .xg-footer, .foot-row, .card-footer{{flex-wrap:nowrap!important;white-space:nowrap!important;min-width:0!important;}}
footer span, footer div, .pl-foot-tag, .pl-foot-s, .in-foot-tag, .pr-foot-tag, .st-foot-tag, .cf-tag{{white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;min-width:0!important;}}
</style>
</head>
<body>
<div class="bd-canvas" dir="rtl">
  <div class="bd-ambient"></div>
  <svg class="bd-frame-svg" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid slice" fill="none">
    <defs>
      <pattern id="tg" width="54" height="54" patternUnits="userSpaceOnUse"><path d="M54 0H0v54" stroke="#F8FAFC" stroke-opacity=".055"/></pattern>
      <radialGradient id="rf" cx="50%" cy="28%" r="48%">
        <stop offset="0" stop-color="#F59E0B" stop-opacity=".18"/><stop offset=".45" stop-color="#E62E45" stop-opacity=".12"/><stop offset="1" stop-color="#E62E45" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="goldArc" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#FDE68A" stop-opacity=".55"/><stop offset="50%" stop-color="#F59E0B" stop-opacity=".18"/><stop offset="100%" stop-color="#E62E45" stop-opacity=".45"/>
      </linearGradient>
    </defs>
    <rect width="100%" height="100%" fill="url(#tg)"/>
    <rect x="12" y="12" width="{w - 24}" height="{h - 24}" rx="18" stroke="#F8FAFC" stroke-opacity=".11" stroke-width="1.5"/>
    <g stroke="#F8FAFC" stroke-opacity=".08" stroke-width="1.5">
      <line x1="{w // 2}" y1="12" x2="{w // 2}" y2="{h - 12}" stroke-dasharray="8 8"/>
      <circle cx="{cx_bg}" cy="{cy_bg}" r="155"/>
    </g>
    <circle cx="{cx_bg}" cy="{cy_bg}" r="280" fill="url(#rf)"/>
    <circle cx="{cx_bg}" cy="{cy_bg}" r="230" stroke="url(#goldArc)" stroke-width="1.4" stroke-dasharray="5 7"/>
    <circle cx="{cx_bg}" cy="{cy_bg}" r="320" stroke="#F8FAFC" stroke-opacity=".07"/>
    <path d="{crh_d}" stroke="#E62E45" stroke-opacity=".65" stroke-width="2.2"/>
  </svg>
  <div class="bd-scanlines"></div>
  <header class="bd-header">
    <div class="fcol bd-minw-0">
      <div class="fi bd-gap-10">
        <div class="bd-hdr-badge gold-pill">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#FBBF24" stroke-width="2.4"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
          <span>تولدت مبارک اسطوره</span>
        </div>
        <span class="bd-date-pill">{date_pill_txt}</span>
      </div>
      {f'<div class="bd-submeta">{submeta_txt}</div>' if submeta_txt else ''}
    </div>
    {_brand_logo_html()}
  </header>
  <main class="{stage_cls}">
    {f'<section class="bd-wide-hero">{hero_html}</section><section class="bd-wide-mods">{mods_html}</section>' if (is_wide and not is_minimal) else (hero_html if is_minimal else f'<section>{hero_html}</section><section class="bd-mods-vert">{mods_html}</section>')}
  </main>
  <footer class="bd-footer">
    <div class="bd-footer-line"></div>
    <div class="fbw bd-gap-12">
      <div class="fi bd-gap-10 bd-minw-0">
        <span class="bd-foot-dot"></span>
        <span dir="ltr" class="fm bd-foot-tag">BIRTHDAY EDITION // {name_en} // {esc(str(item.get("age") or ""))} YEARS</span>
      </div>
      <div class="fi bd-gap-10 fm" dir="ltr">
        <span class="bd-foot-handle">@XGPedia</span>
        <span class="bd-sep">|</span>
        <span class="bd-foot-src">{source_txt}</span>
      </div>
    </div>
  </footer>
</div>
</body>
</html>"""


def build_birthday_caption(item: dict[str, Any]) -> str:
    """تولید کپشن فارسی کامل و غیرتکراری برای کارت تولد (تیتر یک‌بار در telegram_publish بولد می‌شود)."""
    name_fa = fa(str(item.get("nameFa") or item.get("nameEn") or ""))
    age = item.get("age")
    q = item.get("quote") if isinstance(item.get("quote"), dict) else {}
    q_body = fa(str(q.get("body") or "").strip())
    rec = item.get("record") if isinstance(item.get("record"), dict) else None
    kpis = item.get("kpis") if isinstance(item.get("kpis"), dict) else None

    parts: list[str] = []
    if q_body:
        parts.append(q_body)
    stat_bits = []
    if kpis and kpis.get("apps"):
        stat_bits.append(f"{fa(kpis['apps'])} بازی رسمی")
    if kpis and kpis.get("goals"):
        stat_bits.append(f"{fa(kpis['goals'])} گل")
    if kpis and kpis.get("assists"):
        stat_bits.append(f"{fa(kpis['assists'])} پاس گل")
    if stat_bits:
        parts.append("📊 کارنامهٔ ثبت‌شده: " + " | ".join(stat_bits))
    if rec and rec.get("title") and rec.get("desc"):
        parts.append(f"🏆 {fa(rec['title'])}: {fa(rec['desc'])}")
    if not parts:
        parts.append(f"تولد {fa(age)} سالگی {name_fa} مبارک!" if age else f"تولد {name_fa} مبارک!")
    return "\n\n".join(parts)
