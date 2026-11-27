"""رندرر ۱۰۰٪ آفلاین و ۱:۱ کارت اسلایدی نقل‌قول XGPedia (`Quote Studio — Editorial Edition`).

۵ اسلاید استاندارد مطابق دقیق `quote.html`:
  - `slide1`: ادیتوریال سینمایی (Spotlight) — پرتره تمام‌صفحه + ویگنت سینمایی + نقل‌قول بزرگ + نوار آمار
  - `slide2`: جلد مجله دوتایی (Magazine) — قاب عکس مجله‌ای + کارت نقل‌قول با نوار رنگی + نوار آمار
  - `slide3`: تایپوگرافی تاکتیکی (Tactical) — پس‌زمینه زمین تاکتیکی + هدر نقل‌قول + آواتار دایره‌ای + نوار آمار
  - `slide4`: پوستر کنتراست (Poster) — پس‌زمینه هالفتون + باکس آیکون + کارت گوینده + نوار آمار
  - `slide5`: دوئل نقل‌قول (Quote Duel VS) — دو کارت هم‌عرض + نشان الماسی VS وسط + نوار آمار مقایسه‌ای

استانداردهای دائمی XGPedia:
  - ۱۰۰٪ آفلاین (بدون CDN، فونت محلی Vazirmatn)
  - فریم چهارگوشه قرمز یکپارچه (`pad_top=24/22/139`, `pad_bot=20/16/171`)
  - فوتر تک‌خطی اجباری (`white-space:nowrap!important`)
  - لوگوی واقعی باشگاه‌های لیگ برتر (`pl_badges_free`) و رنگ‌های خوانا با کنتراست استاندارد (`ensure_dark_bg_contrast`)
"""
from __future__ import annotations

import re
from typing import Any

from src.xgpedia.render.card_kit.helpers import (
    with_sample_badge,
    _hex_to_rgb,
    ensure_dark_bg_contrast,
    esc,
    fa,
    luminance,
)
from src.xgpedia.render.cards import _brand_logo_data_uri
from src.xgpedia.render.studio_engine import build_embedded_font_css

QUOTE_FORMATS: dict[str, tuple[int, int]] = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}

QUOTE_SLIDES: list[tuple[str, str, str]] = [
    ("slide1", "ادیتوریال سینمایی", "full"),
    ("slide2", "جلد مجله دوتایی", "full"),
    ("slide3", "تایپوگرافی تاکتیکی", "full"),
    ("slide4", "پوستر کنتراست", "full"),
    ("slide5", "دوئل نقل‌قول (VS)", "full"),
]

_SLIDE_TO_LAYOUT: dict[str, str] = {
    "slide1": "spotlight",
    "slide2": "magazine",
    "slide3": "tactical",
    "slide4": "poster",
    "slide5": "duel",
    "spotlight": "spotlight",
    "magazine": "magazine",
    "tactical": "tactical",
    "poster": "poster",
    "duel": "duel",
}

_MODULE_SPECS: list[tuple[str, str, bool]] = [
    ("stats", "نوار بررسی آماری XGPedia (۳ شاخص)", True),
    ("watermark", "واترمارک تایپوگرافی پس‌زمینه", True),
    ("grid", "خطوط زمین تاکتیکی و رادار", True),
    ("grain", "بافت فیلم و چاپ مجله‌ای", True),
    ("scan", "اسکن‌لاین ظریف پخش زنده", True),
]


def get_quote_modules(item: dict[str, Any], slide: str = "slide1") -> tuple[list[dict[str, Any]], list[str]]:
    """فهرست ماژول‌های لایه‌ای کارت نقل‌قول برای پنل کاستومایزر تلگرام."""
    has_stats = bool([s for s in (item.get("stats") or []) if isinstance(s, dict) and (s.get("label") or s.get("val"))])
    mods: list[dict[str, Any]] = []
    missing: list[str] = []
    for mid, title_fa, def_on in _MODULE_SPECS:
        if mid == "stats" and not has_stats and not item.get("is_live"):
            missing.append("نوار بررسی آماری (دیتای زنده ندارد)")
            mods.append({"id": mid, "title_fa": title_fa, "enabled": False, "span": "full", "can_half": False})
        else:
            mods.append({"id": mid, "title_fa": title_fa, "enabled": def_on, "span": "full", "can_half": False})
    return mods, missing


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
        '<div style="font-weight:800;font-size:30px;letter-spacing:-.02em"><span style="color:#E62E45">XG</span><span style="color:#F8FAFC">Pedia</span></div>'
        '</div>'
    )


def _rgb_str(hex_color: str) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    return f"{r},{g},{b}"


def _club_badge_or_crest(code: str, primary: str, secondary: str, size: int, uid: str) -> str:
    """نمایش لوگوی رسمی باشگاه لیگ برتر (در صورت تطبیق) و در غیر این صورت سپر SVG باکیفیت."""
    cd = (code or "XGP").strip().upper()[:3]
    try:
        from src.xgpedia.providers.pl_badges_free import get_pl_badge_data_uri, lookup_pl_club
        info = lookup_pl_club(cd, tla_hint=cd)
        if info and info[4]:
            uri = get_pl_badge_data_uri(info[1], tla_hint=info[1], badge_code=info[4], size=100 if size >= 70 else 70, fetch_network=False)
            if uri:
                return (
                    f'<div style="width:{size}px;height:{size}px;display:flex;align-items:center;justify-content:center;'
                    f'background:rgba(15,23,42,.55);border:1.5px solid rgba(255,255,255,.18);border-radius:18px;padding:6px;'
                    f'box-shadow:0 10px 22px rgba(0,0,0,.55);flex-shrink:0">'
                    f'<img src="{uri}" alt="{esc(cd)}" style="width:100%;height:100%;object-fit:contain;display:block"/>'
                    f'</div>'
                )
    except Exception:
        pass

    if cd == "XGP":
        try:
            import base64 as _b64
            from src.xgpedia.config import ROOT as _ROOT
            _svg_p = _ROOT / "brand" / "logo" / "svg" / "logo-xg-red.svg"
            if _svg_p.exists():
                _b64_uri = "data:image/svg+xml;base64," + _b64.b64encode(_svg_p.read_bytes()).decode("ascii")
                return (
                    f'<div style="width:{size}px;height:{size}px;display:flex;align-items:center;justify-content:center;'
                    f'background:rgba(15,23,42,.72);border:1.5px solid rgba(230,46,69,.42);border-radius:18px;padding:10px;'
                    f'box-shadow:0 10px 22px rgba(0,0,0,.55);flex-shrink:0">'
                    f'<img src="{_b64_uri}" alt="XGPedia" style="width:100%;height:100%;object-fit:contain;display:block"/>'
                    f'</div>'
                )
        except Exception:
            pass

    p = primary or "#E62E45"
    s = secondary or "#FFFFFF"
    d = "M90 16L150 40V88C150 128 124.5 156.5 90 166C55.5 156.5 30 128 30 88V40Z"
    box_bg = "#0D1730" if luminance(p) > 0.65 else "#070d1dc4"
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 180 180" fill="none" '
        f'style="filter:drop-shadow(0 8px 18px rgba(0,0,0,.55));flex-shrink:0">'
        f'<defs><linearGradient id="g{uid}" x1="20" y1="15" x2="160" y2="165" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{s}" stop-opacity=".95"/><stop offset=".5" stop-color="{p}" stop-opacity=".92"/>'
        f'<stop offset="1" stop-color="{s}" stop-opacity=".75"/></linearGradient>'
        f'<clipPath id="c{uid}"><path d="{d}"/></clipPath></defs>'
        f'<path d="M90 12L154 38V88C154 130.5 127 160.5 90 170.5C53 160.5 26 130.5 26 88V38Z" fill="{p}" fill-opacity=".22"/>'
        f'<g clip-path="url(#c{uid})"><rect x="25" y="12" width="130" height="158" fill="{p}"/>'
        f'<path d="M25 112L155 56V84L25 140Z" fill="{s}" fill-opacity=".25"/>'
        f'<path d="M90 16L150 40V58L90 34L30 58V40Z" fill="{s}" fill-opacity=".88"/></g>'
        f'<path d="{d}" stroke="url(#g{uid})" stroke-width="5.5"/>'
        f'<rect x="40" y="68" width="100" height="48" rx="14" fill="{box_bg}" stroke="{s}" stroke-opacity=".55" stroke-width="2"/>'
        f'<text x="90" y="102" text-anchor="middle" fill="#fff" font-family="Space Grotesk,JetBrains Mono,sans-serif" '
        f'font-weight="800" font-size="31" letter-spacing="2">{esc(cd)}</text></svg>'
    )


def _quote_glyph(col: str, sz: int = 80) -> str:
    h = round(sz * 0.72)
    return (
        f'<svg width="{sz}" height="{h}" viewBox="0 0 100 72" fill="none" style="flex-shrink:0">'
        f'<path d="M40 6L12 36L40 66H21L0 43.5V28.5L21 6H40Z" fill="{col}"/>'
        f'<path d="M88 6L60 36L88 66H69L48 43.5V28.5L69 6H88Z" fill="{col}" fill-opacity=".42"/>'
        f'</svg>'
    )


def _fmt_quote_html(raw: str, style: str, col: str) -> str:
    rgb = _rgb_str(col)
    bright = ensure_dark_bg_contrast(col, min_ratio=5.0)
    vars_css = (
        f"--hl-bg:rgba({rgb},.42);--hl-pill:rgba({rgb},.26);"
        f"--hl-solid:{bright};--hl-text:{bright};--hl-glow:rgba({rgb},.55)"
    )
    cls = "qhl-pill" if style == "pill" else ("qhl-accent" if style == "accent" else "qhl-underline")
    safe = esc(raw).replace("\n", "<br>")
    return re.sub(r"\*([^*]+)\*", lambda m: f'<span class="{cls}" style="{vars_css}">{m.group(1)}</span>', safe)


def _stats_bar_html(item: dict[str, Any], col: str, show_stats: bool, compact: bool) -> str:
    if not show_stats:
        return ""
    items = [s for s in (item.get("stats") or []) if isinstance(s, dict) and (s.get("label") or s.get("val"))][:3]
    if not items:
        return ""
    rgb = _rgb_str(col)
    pad = "14px 20px" if compact else "16px 26px"
    t_sz = 18 if compact else 21
    v_sz = 25 if compact else 30
    l_sz = 14 if compact else 15.5
    cells = "".join(
        f'<div class="st-cell">'
        f'<div class="st-val" style="font-size:{v_sz}px">{fa(esc(st.get("val", "")))}</div>'
        f'<div class="st-lbl" style="font-size:{l_sz}px">{esc(st.get("label", ""))}</div>'
        f'</div>'
        for st in items
    )
    return (
        f'<div class="xm st-bar" style="padding:{pad};border-color:rgba({rgb},.40)">'
        f'<div class="st-head">'
        f'<span class="st-dot" style="background:{col};box-shadow:0 0 14px {col}"></span>'
        f'<div><div class="st-title" style="font-size:{t_sz}px">بررسی آماری</div>'
        f'<div class="st-sub">آمار زنده XGPedia</div></div>'
        f'</div>'
        f'<div class="st-grid" style="grid-template-columns:repeat({len(items)},minmax(0,1fr))">{cells}</div>'
        f'</div>'
    )


def _speaker_block_html(item: dict[str, Any], col: str, compact: bool, with_avatar: bool = False) -> str:
    rgb = _rgb_str(col)
    photo = str(item.get("photoSrc") or "").strip()
    py = int(item.get("photoY") or 18)
    sp = esc(item.get("speaker") or "گوینده")
    rl = esc(item.get("role") or "")
    cd = str(item.get("clubCode") or "XGP")
    sec = str(item.get("secondary") or "#FFFFFF")
    if with_avatar and photo:
        av_sz = 78 if compact else 94
        lead = (
            f'<div style="padding:4px;border-radius:999px;background:linear-gradient(135deg,{col},#E62E45);flex-shrink:0">'
            f'<img src="{photo}" alt="{sp}" style="width:{av_sz}px;height:{av_sz}px;border-radius:999px;object-fit:cover;object-position:50% {py}%;display:block"/>'
            f'</div>'
        )
    else:
        bar_h = 62 if compact else 74
        lead = f'<div style="width:8px;height:{bar_h}px;border-radius:99px;background:linear-gradient(180deg,{col},#E62E45);box-shadow:0 0 22px rgba({rgb},.6);flex-shrink:0"></div>'
    name_sz = 30 if compact else 36
    role_sz = 19 if compact else 22
    crest_sz = 68 if compact else 82
    return (
        f'<div class="sp-row">'
        f'<div class="sp-left">{lead}'
        f'<div class="sp-meta"><div class="sp-name" style="font-size:{name_sz}px">{sp}</div>'
        f'<div class="sp-role" style="font-size:{role_sz}px">{rl}</div></div></div>'
        f'{_club_badge_or_crest(cd, col, sec, crest_sz, "sp1")}'
        f'</div>'
    )


def _quote_dir_attr(text: str) -> str:
    ascii_n = sum(1 for c in text if "a" <= c.lower() <= "z")
    fa_n = sum(1 for c in text if "\u0600" <= c <= "\u06ff")
    return 'dir="ltr" style="text-align:left;' if ascii_n > fa_n * 1.4 else 'dir="rtl" style="text-align:right;'


@with_sample_badge
def render_quote_html(
    item: dict[str, Any],
    *,
    slide: str = "slide1",
    header_mode: str = "full",
    fmt: str = "4:5",
    theme: str | None = None,
    hl_style: str | None = None,
    grade: str | None = None,
    modules: list[dict[str, Any]] | None = None,
) -> str:
    """تولید HTML ۱۰۰٪ آفلاین و ۱:۱ مطابق `quote.html` در ۵ اسلاید و ۳ فرمت."""
    w, h = QUOTE_FORMATS.get(fmt, QUOTE_FORMATS["4:5"])
    is16 = fmt == "16:9"
    is9 = fmt == "9:16"
    layout = _SLIDE_TO_LAYOUT.get(slide, str(item.get("layout") or "spotlight"))
    if layout not in {"spotlight", "magazine", "tactical", "poster", "duel"}:
        layout = "spotlight"

    # تنظیمات ماژول‌ها
    mod_map = {m["id"]: bool(m.get("enabled", True)) for m in (modules or []) if isinstance(m, dict) and m.get("id")}
    show_stats = mod_map.get("stats", True)
    show_wm = mod_map.get("watermark", True)
    show_grid = mod_map.get("grid", True)
    show_grain = mod_map.get("grain", True)
    show_scan = mod_map.get("scan", True)

    raw_col = str(item.get("color") or "#E62E45")
    col = ensure_dark_bg_contrast(raw_col, min_ratio=4.6)
    rgb = _rgb_str(col)

    raw_col2 = str(item.get("color2") or "#38BDF8")
    col2 = ensure_dark_bg_contrast(raw_col2, min_ratio=4.6)
    if col2.lower() == col.lower():
        col2 = "#38BDF8" if col.upper() != "#38BDF8" else "#F59E0B"
    rgb2 = _rgb_str(col2)

    hl = hl_style or str(item.get("hlStyle") or "underline")
    gr = grade or str(item.get("grade") or "cinematic")
    if theme in {"underline", "pill", "accent"}:
        hl = theme
    elif theme in {"cinematic", "duotone", "rim", "natural"}:
        gr = theme

    photo = str(item.get("photoSrc") or "").strip()
    photo2 = str(item.get("photoSrc2") or "").strip()
    pz = int(item.get("photoZoom") or 108)
    py = int(item.get("photoY") or 18)
    vig = int(item.get("vignette") or 64) / 100.0

    quote_raw = str(item.get("quote") or "")
    q_len = len(re.sub(r"\*", "", quote_raw))
    base_fs = int(item.get("fontSize") or (48 if q_len <= 120 else (42 if q_len <= 170 else 36)))
    fs = round(base_fs * (0.90 if is16 else (1.04 if is9 else 0.98)))
    q_html = _fmt_quote_html(quote_raw, hl, col)
    q_dir_prefix = _quote_dir_attr(quote_raw)

    # پس‌زمینه نور محیطی
    if layout == "duel":
        ag_bg = (
            f"radial-gradient(circle at 88% 36%,rgba({rgb},.44),transparent 50%),"
            f"radial-gradient(circle at 12% 36%,rgba({rgb2},.44),transparent 50%),"
            f"radial-gradient(circle at 50% 42%,rgba(230,46,69,.24),transparent 44%)"
        )
    else:
        ag_bg = (
            f"radial-gradient(circle at 84% 24%,rgba({rgb},.36),transparent 52%),"
            f"radial-gradient(circle at 16% 78%,rgba(230,46,69,.22),transparent 50%),"
            f"radial-gradient(circle at 50% 44%,rgba(16,29,59,.50),transparent 65%)"
        )

    pad_top = 139 if is9 else (24 if is16 else 22)
    pad_bot = 171 if is9 else (20 if is16 else 16)
    # لایه عکس پس‌زمینه (فقط spotlight و poster — نسبت ثابت 16:10 بدون کشیدگی)
    bg_photo_html = ""
    if photo and layout in {"spotlight", "poster"}:
        duo_div = (
            f'<div class="abs-fill" style="background:linear-gradient(135deg,rgba({rgb},.58),rgba(13,23,48,.78));mix-blend-mode:color"></div>'
            if gr == "duotone" else ""
        )
        rim_div = (
            f'<div class="abs-fill" style="background:radial-gradient(circle at 22% 28%,rgba({rgb},.42),transparent 48%),'
            f'radial-gradient(circle at 80% 24%,rgba(56,189,248,.28),transparent 46%);mix-blend-mode:screen"></div>'
            if gr == "rim" else ""
        )
        if layout == "spotlight":
            if is16:
                bg_photo_html = (
                    f'<div class="abs-fill z1" style="display:flex;align-items:center;justify-content:flex-end">'
                    f'<div style="position:relative;width:54%;aspect-ratio:16/10;max-height:100%;overflow:hidden">'
                    f'<img src="{photo}" alt="" class="full-img grade-{gr}" style="object-position:50% {py}%"/>'
                    f'{duo_div}{rim_div}'
                    f'<div class="abs-fill" style="background:linear-gradient(90deg,#0D1730 0%,rgba(13,23,48,.55) 28%,transparent 65%,rgba(13,23,48,.45) 100%)"></div>'
                    f'<div class="abs-fill" style="background:linear-gradient(180deg,rgba(13,23,48,.75) 0%,transparent 22%,transparent 75%,#0D1730 100%)"></div>'
                    f'</div></div>'
                )
            else:
                ar_v = "4/3" if is9 else "16/10"
                bg_photo_html = (
                    f'<div class="abs-fill z1">'
                    f'<div style="position:absolute;top:0;left:0;right:0;width:100%;aspect-ratio:{ar_v};overflow:hidden">'
                    f'<img src="{photo}" alt="" class="full-img grade-{gr}" style="object-position:50% {py}%"/>'
                    f'{duo_div}{rim_div}'
                    f'<div class="abs-fill" style="background:linear-gradient(90deg,rgba(13,23,48,.90) 0%,rgba(13,23,48,.18) 12%,transparent 24%,transparent 76%,rgba(13,23,48,.18) 88%,rgba(13,23,48,.90) 100%)"></div>'
                    f'<div class="abs-fill" style="background:linear-gradient(180deg,rgba(13,23,48,.78) 0%,rgba(13,23,48,.10) 18%,rgba(13,23,48,.14) 50%,rgba(13,23,48,.84) 82%,#0D1730 100%)"></div>'
                    f'</div></div>'
                )
        else:
            ar_v = "4/3" if is9 else "16/10"
            bg_photo_html = (
                f'<div class="abs-fill z1">'
                f'<div style="position:absolute;top:0;left:0;right:0;width:100%;aspect-ratio:{ar_v};overflow:hidden">'
                f'<img src="{photo}" alt="" class="full-img grade-{gr}" style="object-position:50% {py}%;opacity:.56"/>'
                f'{duo_div}<div class="abs-fill halftone"></div>'
                f'<div class="abs-fill" style="background:linear-gradient(90deg,rgba(13,23,48,.90) 0%,transparent 22%,transparent 78%,rgba(13,23,48,.90) 100%)"></div>'
                f'<div class="abs-fill" style="background:linear-gradient(180deg,rgba(13,23,48,.82) 0%,rgba({rgb},.16) 44%,rgba(13,23,48,.86) 82%,#0D1730 100%)"></div>'
                f'</div></div>'
            )

    # واترمارک تایپوگرافی پس‌زمینه
    wm_html = ""
    wm_txt = str(item.get("watermark") or "").strip().upper()
    if show_wm and wm_txt:
        wm_sz = 205 if is16 else (235 if is9 else 190)
        wm_top = ("8%" if is16 else "15%") if layout == "spotlight" else ("26%" if layout == "tactical" else "11%")
        wm_html = (
            f'<div class="wm-stroke" style="top:{wm_top};font-size:{wm_sz}px;'
            f'text-shadow:0 0 60px rgba({rgb},.18)">{esc(wm_txt)}</div>'
        )

    # بدنهٔ ۵ اسلاید
    stats_html = _stats_bar_html(item, col, show_stats, compact=(is16 or layout in {"magazine", "poster", "duel"}))
    _raw_match = str(item.get("match") or item.get("context") or "").strip()
    _m_en = sum(1 for c in _raw_match if "a" <= c.lower() <= "z")
    _m_fa = sum(1 for c in _raw_match if "\u0600" <= c <= "\u06ff")
    if _m_en >= 10 and _m_en > _m_fa * 1.4:
        _raw_match = str(item.get("context") or "گفت‌وگوی ویژه")
    match_txt = esc(_raw_match)

    if layout == "spotlight":
        if is16:
            body_html = (
                f'<div class="spot-16">'
                f'<div class="spot-16-main">'
                f'<div class="q-accent-row">{_quote_glyph(col, 74)}<div class="q-line" style="background:linear-gradient(270deg,{col},transparent)"></div></div>'
                f'<blockquote class="q-txt" {q_dir_prefix}font-size:{fs}px;line-height:1.42;text-shadow:0 10px 34px rgba(0,0,0,.65)">{q_html}</blockquote>'
                f'<div class="sp-sep">{_speaker_block_html(item, col, True, False)}</div>'
                f'{stats_html}</div>'
                f'<div class="spot-16-side"><div class="spot-pill"><span class="pdot" style="background:{col};box-shadow:0 0 12px {col}"></span>'
                f'<span>نقل‌قول ویژه</span></div></div></div>'
            )
        else:
            body_html = (
                f'<div class="spot-v">'
                f'<div class="fcol gap20">'
                f'<div class="q-accent-row">{_quote_glyph(col, 84)}'
                f'<div class="q-line-sm" style="background:linear-gradient(270deg,{col},transparent)"></div>'
                f'<span class="q-tag">نقل‌قول روز</span></div>'
                f'<blockquote class="q-txt" {q_dir_prefix}font-size:{fs}px;line-height:1.46;text-shadow:0 12px 38px rgba(0,0,0,.72)">{q_html}</blockquote>'
                f'</div>'
                f'<div class="sp-sep">{_speaker_block_html(item, col, False, False)}</div>'
                f'{stats_html}</div>'
            )
    elif layout == "magazine":
        duo_div = (
            f'<div class="abs-fill" style="background:linear-gradient(135deg,rgba({rgb},.55),rgba(13,23,48,.75));mix-blend-mode:color"></div>'
            if gr == "duotone" else ""
        )
        if photo:
            pframe = (
                f'<div class="mag-photo" style="border-color:rgba({rgb},.55);box-shadow:0 24px 60px -12px rgba(0,0,0,.85),0 0 40px -12px rgba({rgb},.35)">'
                f'<img src="{photo}" alt="{esc(item.get("speaker", ""))}" class="full-img grade-{gr}" style="object-position:50% {py}%"/>'
                f'{duo_div}'
                f'<div class="abs-fill" style="background:linear-gradient(180deg,rgba(13,23,48,.12) 0%,transparent 48%,rgba(13,23,48,.90) 100%)"></div>'
                f'<div class="mag-corner" style="border-color:{col}"></div>'
                f'<div class="mag-cap"><div><div class="mag-sp">{esc(item.get("speaker", ""))}</div>'
                f'<div class="mag-rl">{esc(item.get("role", ""))}</div></div>'
                f'{_club_badge_or_crest(str(item.get("clubCode") or "XGP"), col, str(item.get("secondary") or "#FFFFFF"), 68, "mg1")}</div></div>'
            )
        else:
            pframe = (
                f'<div class="xe mag-nophoto" style="border-color:rgba({rgb},.5)">'
                f'{_club_badge_or_crest(str(item.get("clubCode") or "XGP"), col, str(item.get("secondary") or "#FFFFFF"), 126, "mg0")}'
                f'<div class="mag-sp" style="font-size:34px">{esc(item.get("speaker", ""))}</div>'
                f'<div class="mag-rl" style="font-size:20px">{esc(item.get("role", ""))}</div></div>'
            )
        qcard = (
            f'<div class="xe mag-qcard" style="border-right:7px solid {col}">'
            f'<div class="fbw">{_quote_glyph(col, 68)}<span class="q-tag">جلد مجله</span></div>'
            f'<blockquote class="q-txt" {q_dir_prefix}font-size:{fs}px;line-height:1.45;margin:auto 0">{q_html}</blockquote>'
            f'<div class="mag-foot"><span class="pdot" style="background:{col}"></span><span class="trunc">{match_txt}</span></div>'
            f'</div>'
        )
        if is16:
            body_html = f'<div class="mag-16"><div class="mag-16-l">{pframe}</div><div class="mag-16-r">{qcard}{stats_html}</div></div>'
        else:
            ph_pct = "46%" if is9 else "44%"
            body_html = f'<div class="fcol gap18 flex1 min0"><div style="height:{ph_pct};min-height:0">{pframe}</div>{qcard}{stats_html}</div>'
    elif layout == "tactical":
        body_html = (
            f'<div class="fcol gap20 flex1 min0" style="padding:{"6px 0" if is16 else "14px 0"}">'
            f'<div class="xe tac-card" style="padding:{"34px" if is16 else "38px"};border-color:rgba({rgb},.48)">'
            f'<svg class="tac-pitch" viewBox="0 0 240 160" fill="none" stroke="#DCE6F8" stroke-width="2.5">'
            f'<rect x="2" y="2" width="236" height="156" rx="8"/><line x1="120" y1="2" x2="120" y2="158"/><circle cx="120" cy="80" r="34"/></svg>'
            f'<div class="tac-hdr"><div class="fi gap14">'
            f'<span style="width:10px;height:36px;border-radius:99px;background:{col};box-shadow:0 0 18px {col}"></span>'
            f'<div><div style="font-size:24px;font-weight:900;color:#fff">نقل‌قول برگزیده</div>'
            f'<div style="font-size:15px;font-weight:700;color:#94A3B8">صدای تاکتیکی • XGPedia</div></div>'
            f'</div>{_quote_glyph(col, 66)}</div>'
            f'<blockquote class="q-txt" {q_dir_prefix}font-size:{round(fs * 1.05)}px;line-height:1.48;margin:auto 0;position:relative;z-index:2">{q_html}</blockquote>'
            f'<div class="sp-sep" style="position:relative;z-index:2">{_speaker_block_html(item, col, is16, True)}</div>'
            f'</div>{stats_html}</div>'
        )
    elif layout == "duel":
        sp2 = str(item.get("speaker2") or "گوینده دوم")
        rl2 = str(item.get("role2") or "واکنش رسانه‌ای")
        cd2 = str(item.get("clubCode2") or "XGP")
        q2_raw = str(item.get("quote2") or "در *لحظات حساس* فوتبال، جزئیات کوچک سرنوشت مسابقه را رقم می‌زنند.")
        q2_html = _fmt_quote_html(q2_raw, hl, col2)
        q2_dir_prefix = _quote_dir_attr(q2_raw)
        d_fs = max(29, round(base_fs * 0.80)) if is16 else (max(28, round(base_fs * 0.78)) if is9 else max(24, round(base_fs * 0.66)))
        ph_h = "44%" if is16 else ("41%" if is9 else "39%")

        def _duel_card(idx: int, qh: str, qdp: str, sp: str, rl: str, cd: str, c: str, rb: str, ph: str) -> str:
            is_r = idx == 1
            cd_up = esc((cd or "XGP").strip().upper()[:3])
            duo = (
                f'<div class="abs-fill" style="background:linear-gradient(135deg,rgba({rb},.55),rgba(13,23,48,.74));mix-blend-mode:color"></div>'
                if gr == "duotone" else ""
            )
            media = (
                f'<img src="{ph}" alt="{esc(sp)}" class="full-img grade-{gr}" style="object-position:50% {py}%"/>'
                f'{duo}'
                f'<div class="abs-fill" style="background:linear-gradient(180deg,rgba(9,16,35,.08) 0%,rgba(9,16,35,.22) 50%,rgba(9,16,35,.92) 100%)"></div>'
                f'<div class="abs-fill" style="background:radial-gradient(circle at {"80%" if is_r else "20%"} 18%,rgba({rb},.42),transparent 58%)"></div>'
                if ph else
                f'<div class="fc" style="width:100%;height:100%;background:radial-gradient(circle at 50% 45%,rgba({rb},.30),rgba(9,16,35,.96) 72%)">'
                f'{_club_badge_or_crest(cd, c, "#FFFFFF", 112 if is16 else 92, f"dc{idx}")}</div>'
            )
            corner_pos = "right:14px" if is_r else "left:14px"
            wm_pos = "left:-10px" if is_r else "right:-10px"
            return (
                f'<article class="xe duel-card" style="border-color:rgba({rb},.46);box-shadow:0 26px 56px -14px rgba(0,0,0,.92),0 0 38px -18px rgba({rb},.50),inset 0 1px 0 rgba(255,255,255,.2)">'
                f'<div class="duel-top-bar" style="background:{c};box-shadow:0 0 20px {c}"></div>'
                f'<div class="duel-wm" style="{wm_pos};font-size:{136 if is16 else 112}px;-webkit-text-stroke:1.5px rgba({rb},.18)">{cd_up}</div>'
                f'<div class="duel-media" style="aspect-ratio:4/3;width:calc(100% - 28px)">{media}'
                f'<div style="position:absolute;top:14px;{corner_pos};z-index:10">{_club_badge_or_crest(cd, c, "#FFFFFF", 62 if is16 else 54, f"dcr{idx}")}</div>'
                f'<div class="duel-media-line" style="background:linear-gradient(90deg,transparent,{c},transparent)"></div></div>'
                f'<div class="duel-body">'
                f'<div class="fcol gap12" style="margin:auto 0">'
                f'<div class="fi gap12">{_quote_glyph(c, 50 if is16 else 40)}'
                f'<div class="q-line" style="height:2px;background:linear-gradient(270deg,{c},rgba(255,255,255,.08))"></div>'
                f'<span class="pdot" style="background:{c};box-shadow:0 0 10px {c}"></span></div>'
                f'<blockquote class="q-txt" {qdp}font-size:{d_fs}px;line-height:1.48;text-shadow:0 8px 24px rgba(0,0,0,.68)">{qh}</blockquote>'
                f'</div>'
                f'<div class="duel-sp" style="border-right:4px solid {c}">'
                f'<div class="min0"><div class="duel-sp-n" style="font-size:{24 if is16 else 21}px">{esc(sp)}</div>'
                f'<div class="duel-sp-r" style="font-size:{15.5 if is16 else 14}px">{esc(rl)}</div></div>'
                f'<div class="duel-cd fm" dir="ltr" style="color:{c}">{cd_up}</div>'
                f'</div></div></article>'
            )

        vs_top = "45%" if is16 else ("42%" if is9 else "40%")
        body_html = (
            f'<div class="fcol gap16 flex1 min0" style="padding:4px 0">'
            f'<div class="duel-grid" style="gap:{42 if is16 else 30}px">'
            f'{_duel_card(1, q_html, q_dir_prefix, str(item.get("speaker") or ""), str(item.get("role") or ""), str(item.get("clubCode") or "XGP"), col, rgb, photo)}'
            f'{_duel_card(2, q2_html, q2_dir_prefix, sp2, rl2, cd2, col2, rgb2, photo2)}'
            f'<div class="duel-divider" style="background:linear-gradient(180deg,transparent,rgba({rgb},.55) 28%,#E62E45 50%,rgba({rgb2},.55) 72%,transparent)"></div>'
            f'<div class="vs-wrap" style="top:{vs_top}">'
            f'<div class="vs-outer"><div class="vs-inner"></div></div>'
            f'<span class="vs-txt fd">VS</span></div>'
            f'</div>{stats_html}</div>'
        )
    else:
        # poster
        body_html = (
            f'<div class="fcol gap20 flex1 min0" style="padding:8px 0">'
            f'<div class="fcol flex1 justify-center gap22" style="padding:0 14px">'
            f'<div class="fi gap16">'
            f'<div class="poster-box" style="background:rgba({rgb},.24);border-color:{col}">{_quote_glyph("#FFFFFF", 40)}</div>'
            f'<div class="q-line" style="height:2px;background:linear-gradient(270deg,{col},rgba(255,255,255,.15))"></div>'
            f'</div>'
            f'<blockquote class="q-txt" {q_dir_prefix}font-size:{round(fs * 1.04)}px;line-height:1.45;text-shadow:0 14px 40px rgba(0,0,0,.80)">{q_html}</blockquote>'
            f'</div>'
            f'<div class="xm" style="padding:20px 26px;border-right:8px solid {col}">{_speaker_block_html(item, col, is16, True)}</div>'
            f'{stats_html}</div>'
        )


    rx1, rx2, by1, by2 = w - 24, w - 44, h - 24, h - 44

    comp_txt = esc(item.get("competition") or "فوتبال جهان")
    date_txt = fa(esc(item.get("date") or "نقل‌قول زنده"))
    _raw_tk = str(item.get("ticker") or "").strip()
    _tk_en = sum(1 for c in _raw_tk if "a" <= c.lower() <= "z")
    _tk_fa = sum(1 for c in _raw_tk if "\u0600" <= c <= "\u06ff")
    _comp_fb = item.get("competition") or "فوتبال جهان"
    ticker_txt = esc(f"{_comp_fb} • نقل‌قول روز" if (not _raw_tk or _tk_en > _tk_fa) else _raw_tk)
    src_txt = esc(item.get("source") or "XGPedia")
    hdr_sub = (
        ""
        if header_mode == "compact"
        else f'<div class="hdr-meta"><span>{date_txt}</span><span class="sep">•</span><span class="hdr-match">{match_txt}</span></div>'
    )

    grid_svg = (
        f'<g id="fgrid"><rect width="100%" height="100%" fill="url(#tg)"/>'
        f'<rect x="12" y="12" width="{w - 24}" height="{h - 24}" rx="18" stroke="#F8FAFC" stroke-opacity=".12" stroke-width="1.5"/>'
        f'<g stroke="#F8FAFC" stroke-opacity=".08" stroke-width="1.5">'
        f'<line x1="{w // 2}" y1="12" x2="{w // 2}" y2="{h - 12}" stroke-dasharray="8 8"/>'
        f'<circle cx="{w // 2}" cy="{int(h * 0.34)}" r="155"/></g>'
        f'<circle cx="{w // 2}" cy="{int(h * 0.34)}" r="245" fill="url(#rf)"/>'
        f'<circle cx="{w // 2}" cy="{int(h * 0.34)}" r="225" stroke="#E62E45" stroke-opacity=".18" stroke-width="1.2" stroke-dasharray="4 6"/>'
        f'<circle cx="{w // 2}" cy="{int(h * 0.34)}" r="320" stroke="#F8FAFC" stroke-opacity=".06"/></g>'
        if show_grid else ""
    )
    scan_div = '<div class="abs-fill scanl"></div>' if show_scan else ""
    grain_div = '<div class="abs-fill grain"></div>' if show_grain else ""

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8"/>
<style>
{build_embedded_font_css()}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{w}px;height:{h}px;overflow:hidden;background:#0D1730;color:#F8FAFC;font-family:'Vazirmatn',system-ui,-apple-system,sans-serif;font-feature-settings:"tnum";font-variant-numeric:tabular-nums}}
.fm{{font-family:'JetBrains Mono','Space Grotesk',monospace}}
.fd{{font-family:'Space Grotesk','Vazirmatn',sans-serif}}
.fi{{display:flex;align-items:center}}
.fc{{display:flex;align-items:center;justify-content:center}}
.fbw{{display:flex;align-items:center;justify-content:space-between}}
.fcol{{display:flex;flex-direction:column}}
.flex1{{flex:1}}
.min0{{min-width:0;min-height:0}}
.justify-center{{justify-content:center}}
.gap12{{gap:12px}}.gap14{{gap:14px}}.gap16{{gap:16px}}.gap18{{gap:18px}}.gap20{{gap:20px}}.gap22{{gap:22px}}
.trunc{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.abs-fill{{position:absolute;inset:0;pointer-events:none}}
.z1{{z-index:1;overflow:hidden}}
.full-img{{width:100%;height:100%;object-fit:cover;display:block}}
.grade-cinematic{{filter:contrast(1.12) saturate(.92) brightness(.96)}}
.grade-duotone{{filter:grayscale(1) contrast(1.22) brightness(.90)}}
.grade-rim{{filter:contrast(1.16) saturate(1.10) brightness(.94)}}
.grade-natural{{filter:contrast(1.04) saturate(1.02)}}
.scanl{{z-index:4;background:repeating-linear-gradient(to bottom,#ffffff04 0 1px,#0000 1px 4px)}}
.grain{{z-index:4;background-image:radial-gradient(rgba(255,255,255,.07) 1px,transparent 0);background-size:6px 6px;mix-blend-mode:overlay;opacity:.55}}
.halftone{{background-image:radial-gradient(rgba(255,255,255,.16) 1.1px,transparent 0);background-size:10px 10px;opacity:.22}}
#ea{{position:relative;width:{w}px;height:{h}px;padding:{pad_top}px 0 {pad_bot}px;background:#0D1730;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden}}
.wm-stroke{{position:absolute;left:50%;transform:translateX(-50%);z-index:3;font-family:'Space Grotesk',sans-serif;font-weight:800;letter-spacing:.06em;line-height:.85;color:transparent;-webkit-text-stroke:2px rgba(248,250,252,.11);text-transform:uppercase;white-space:nowrap;pointer-events:none}}
.hdr{{position:relative;z-index:10;padding:12px 36px 8px;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-shrink:0}}
.hdr-pill{{display:inline-flex;align-items:center;gap:10px;padding:6px 20px;border-radius:999px;background:#152347e6;border:1.5px solid #ffffff33;font-size:22px;font-weight:900;color:#F8FAFC}}
.hdr-meta{{display:flex;align-items:center;gap:10px;font-size:19px;font-weight:700;color:#E2E8F0;margin-top:8px;max-width:740px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.hdr-meta .sep{{color:#94A3B8}}
.hdr-match{{color:#FFFFFF;overflow:hidden;text-overflow:ellipsis}}
.stage{{position:relative;z-index:10;flex:1;padding:8px 40px;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;min-height:0}}
.xm,.xe{{position:relative;border-radius:24px;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;box-shadow:0 16px 40px -10px rgba(0,0,0,.62),inset 0 1px 0 rgba(255,255,255,.11)}}
.xm{{background:linear-gradient(165deg,#101d3be0,#091023f5);border:1.5px solid rgba(248,250,252,.15)}}
.xe{{background:linear-gradient(155deg,#121f3ded,#090f20fa);border:1.5px solid rgba(127,166,232,.26)}}
.qhl-underline{{position:relative;display:inline;color:#fff;padding-bottom:2px;background-image:linear-gradient(180deg,transparent 64%,var(--hl-bg) 64%,var(--hl-bg) 96%,transparent 96%);box-decoration-break:clone;-webkit-box-decoration-break:clone;border-radius:4px}}
.qhl-pill{{display:inline;color:#fff;background:var(--hl-pill);border-bottom:3px solid var(--hl-solid);padding:2px 12px 4px;border-radius:10px;box-decoration-break:clone;-webkit-box-decoration-break:clone}}
.qhl-accent{{color:var(--hl-text);text-shadow:0 0 28px var(--hl-glow)}}
.q-txt{{font-weight:900;color:#FFFFFF;letter-spacing:-.01em;word-break:break-word}}
.q-accent-row{{display:flex;align-items:center;gap:16px}}
.q-line{{height:3px;flex:1;border-radius:99px}}
.q-line-sm{{height:3px;width:180px;border-radius:99px}}
.q-tag{{margin-right:auto;padding:4px 16px;border-radius:999px;background:rgba(7,13,29,.78);border:1px solid rgba(255,255,255,.16);font-size:15px;font-weight:800;letter-spacing:.10em;color:#E2E8F0}}
.pdot{{width:10px;height:10px;border-radius:999px;flex-shrink:0}}
.spot-v{{flex:1;display:flex;flex-direction:column;justify-content:flex-end;gap:22px;min-height:0;padding-bottom:6px}}
.spot-16{{flex:1;display:grid;grid-template-columns:7fr 5fr;gap:30px;align-items:end;min-height:0;padding-bottom:6px}}
.spot-16-main{{display:flex;flex-direction:column;justify-content:flex-end;gap:20px;height:100%}}
.spot-16-side{{display:flex;justify-content:flex-end;align-items:flex-end;padding-bottom:8px}}
.spot-pill{{display:inline-flex;align-items:center;gap:12px;padding:10px 20px;border-radius:16px;background:rgba(7,13,29,.82);border:1px solid rgba(255,255,255,.16);font-size:16px;font-weight:800;letter-spacing:.12em;color:#E2E8F0}}
.sp-sep{{padding-top:18px;border-top:1px solid rgba(255,255,255,.16)}}
.sp-row{{display:flex;align-items:center;justify-content:space-between;gap:16px}}
.sp-left{{display:flex;align-items:center;gap:16px;min-width:0}}
.sp-meta{{min-width:0}}
.sp-name{{font-weight:900;color:#FFFFFF;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.sp-role{{font-weight:700;color:#CBD5E1;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.st-bar{{flex-shrink:0;flex-direction:row!important;align-items:center;justify-content:space-between;gap:18px}}
.st-head{{display:flex;align-items:center;gap:10px;flex-shrink:0}}
.st-dot{{width:8px;height:28px;border-radius:99px}}
.st-title{{font-weight:900;color:#FFFFFF;line-height:1.15}}
.st-sub{{font-size:12px;font-weight:700;color:#94A3B8;letter-spacing:.08em}}
.st-grid{{flex:1;display:grid;gap:12px}}
.st-cell{{border-radius:16px;background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.11);padding:10px 12px;text-align:center}}
.st-val{{font-weight:900;color:#FFFFFF;line-height:1.1}}
.st-lbl{{font-weight:700;color:#CBD5E1;margin-top:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.mag-photo{{position:relative;border-radius:26px;overflow:hidden;border:2px solid rgba(255,255,255,.25);width:100%;aspect-ratio:4/3;max-height:100%}}
.mag-nophoto{{height:100%;padding:28px;align-items:center;justify-content:center;text-align:center;gap:14px}}
.mag-corner{{position:absolute;top:16px;left:16px;width:28px;height:28px;border-top:3px solid;border-left:3px solid;border-top-left-radius:8px}}
.mag-cap{{position:absolute;bottom:16px;right:18px;left:18px;display:flex;align-items:flex-end;justify-content:space-between;gap:12px}}
.mag-sp{{font-size:28px;font-weight:900;color:#fff;line-height:1.2}}
.mag-rl{{font-size:18px;font-weight:700;color:#E2E8F0;margin-top:2px}}
.mag-qcard{{flex:1;padding:24px 28px;gap:14px;min-height:0}}
.mag-foot{{display:flex;align-items:center;gap:10px;padding-top:12px;border-top:1px solid rgba(255,255,255,.12);font-size:18px;font-weight:800;color:#CBD5E1}}
.mag-16{{flex:1;display:grid;grid-template-columns:5fr 7fr;gap:26px;min-height:0}}
.mag-16-l{{min-height:0}}.mag-16-r{{display:flex;flex-direction:column;justify-content:space-between;gap:18px;min-height:0}}
.tac-card{{flex:1;gap:22px;position:relative;overflow:hidden}}
.tac-pitch{{position:absolute;left:24px;bottom:24px;width:250px;height:auto;opacity:.08;pointer-events:none}}
.tac-hdr{{position:relative;z-index:2;display:flex;align-items:center;justify-content:space-between;padding-bottom:16px;border-bottom:1px solid rgba(255,255,255,.12)}}
.poster-box{{width:64px;height:64px;border-radius:16px;border:2px solid;display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.duel-grid{{position:relative;flex:1;display:grid;grid-template-columns:1fr 1fr;align-items:stretch;min-height:0}}
.duel-card{{border-radius:28px;background:linear-gradient(168deg,rgba(19,32,64,.94) 0%,rgba(10,17,36,.97) 58%,rgba(7,12,26,.99) 100%);min-width:0;min-height:0}}
.duel-top-bar{{position:absolute;top:0;left:40px;right:40px;height:3.5px;border-bottom-left-radius:99px;border-bottom-right-radius:99px;z-index:20}}
.duel-wm{{position:absolute;bottom:-18px;font-family:'Space Grotesk',sans-serif;font-weight:800;line-height:1;color:transparent;letter-spacing:.04em;pointer-events:none}}
.duel-media{{position:relative;margin:14px 14px 0;border-radius:20px;overflow:hidden;flex-shrink:0;border:1px solid rgba(255,255,255,.14);background:#081024}}
.duel-media-line{{position:absolute;bottom:10px;left:16px;right:16px;height:2px;border-radius:99px;opacity:.82}}
.duel-body{{position:relative;z-index:10;flex:1;display:flex;flex-direction:column;justify-content:space-between;padding:16px 20px 18px;min-height:0}}
.duel-sp{{margin-top:12px;border-radius:16px;background:rgba(7,14,32,.86);border:1px solid rgba(255,255,255,.12);padding:10px 14px;display:flex;align-items:center;justify-content:space-between;gap:10px}}
.duel-sp-n{{font-weight:900;color:#FFFFFF;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.duel-sp-r{{font-weight:700;color:#CBD5E1;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.duel-cd{{padding:4px 10px;border-radius:10px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);font-size:14px;font-weight:800;flex-shrink:0}}
.duel-divider{{position:absolute;top:24px;bottom:24px;left:50%;transform:translateX(-50%);width:1.5px;z-index:20;pointer-events:none}}
.vs-wrap{{position:absolute;left:50%;transform:translate(-50%,-50%);z-index:30;display:flex;align-items:center;justify-content:center}}
.vs-outer{{width:76px;height:76px;border-radius:22px;transform:rotate(45deg);background:#070D1D;border:2px solid rgba(255,255,255,.26);display:flex;align-items:center;justify-content:center;box-shadow:0 0 44px rgba(230,46,69,.65),0 12px 28px rgba(0,0,0,.85)}}
.vs-inner{{width:58px;height:58px;border-radius:15px;background:#E62E45;border:2px solid rgba(255,255,255,.42)}}
.vs-txt{{position:absolute;font-weight:800;font-size:27px;color:#FFFFFF;letter-spacing:-.02em}}
.ftr{{position:relative;z-index:10;padding:10px 44px 10px;border-top:1px solid rgba(255,255,255,.15);display:flex;align-items:center;justify-content:space-between;gap:16px;flex-shrink:0;flex-wrap:nowrap!important;white-space:nowrap!important;overflow:hidden!important}}
.ftr-l{{display:flex;align-items:center;gap:10px;min-width:0;overflow:hidden;white-space:nowrap!important;text-overflow:ellipsis!important}}
.ftr-dot{{width:11px;height:11px;border-radius:999px;background:#E62E45;box-shadow:0 0 12px #E62E45;flex-shrink:0}}
.ftr-tk{{font-size:17px;font-weight:800;letter-spacing:.12em;color:#F1F5F9;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}}
.ftr-r{{display:flex;align-items:center;gap:10px;flex-shrink:0;white-space:nowrap!important}}
.ftr-brand{{font-size:19px;font-weight:800;color:#FFFFFF}}
.ftr-src{{font-size:16px;font-weight:600;color:#CBD5E1}}
</style>
</head>
<body>
<div id="ea">
  <div class="abs-fill" style="z-index:0;background:{ag_bg}"></div>
  {bg_photo_html}
  <svg class="abs-fill" style="z-index:2;width:100%;height:100%" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid slice" fill="none">
    <defs>
      <pattern id="tg" width="54" height="54" patternUnits="userSpaceOnUse"><path d="M54 0H0v54" stroke="#F8FAFC" stroke-opacity=".055"/></pattern>
      <radialGradient id="rf" cx="50%" cy="30%" r="46%">
        <stop offset="0" stop-color="#E62E45" stop-opacity=".22"/>
        <stop offset=".55" stop-color="#E62E45" stop-opacity=".06"/>
        <stop offset="1" stop-color="#E62E45" stop-opacity="0"/>
      </radialGradient>
    </defs>
    {grid_svg}
    <path d="M24 44V24H44M{rx1} 44V24H{rx2}M24 {by2}V{by1}H44M{rx1} {by2}V{by1}H{rx2}" stroke="#E62E45" stroke-opacity=".68" stroke-width="2.4"/>
  </svg>
  {wm_html}
  {scan_div}
  {grain_div}
  <header class="hdr">
    <div class="min0">
      <div class="hdr-pill">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#E62E45" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        <span>{comp_txt}</span>
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
