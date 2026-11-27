"""کارت «خبر فوری و رسمی» (XGPedia Breaking & Official News Studio — PRO WIRE v2) در حالت اسلایدی.

ویژگی‌های اجباری رعایت‌شده (تصمیم D46):
  - ۱۰۰٪ آفلاین و بدون هرگونه CDN خارجی (فونت محلی Vazirmatn/JetBrains Mono/Space Grotesk + لوگوی واقعی SVG برند + ۳ تصویر پس‌زمینه آفلاین)
  - حفظ کامل هر ۴ چیدمان/پوستر مستقل (`cinematic`, `magazine`, `wire`, `dossier`) × ۵ مود خبری (`breaking`, `official`, `transfer`, `exclusive`, `alert`) × ۴ فرمت (`4:5`, `9:16`, `1:1`, `16:9`) × ۵ حال‌وهوای تصویر (`cinema`, `crimson`, `navy`, `noir`, `raw`)
  - هم‌ترازی کامل چهارگوشهٔ قرمز و فاصلهٔ عمودی بالا (+4px) با استاندارد Post-Match (`rect 12px`, brackets `24..44`, `pad_top=24/22/139`, header `12px 36px 8px`, stage `8px 40px`, footer `10px 44px 10px`)
  - قابلیت روشن/خاموش کردن ماژول‌های داخلی هر اسلاید (`dock`, `seal`, `ticker`, `pitch`, `hl_box`) با رعایت `null ≠ 0`
  - کنتراست خودکار WCAG >= 4.8، ترتیب امن `esc(fa(...))`، عدم استفاده از `•` کنار ارقام فارسی.
"""
from __future__ import annotations

import base64
import re
from functools import lru_cache
from typing import Any

from src.xgpedia.config import ROOT
from src.xgpedia.render.card_kit.helpers import with_sample_badge, ensure_dark_bg_contrast, esc, fa
from src.xgpedia.render.cards import _brand_logo_data_uri
from src.xgpedia.render.studio_engine import build_embedded_font_css

NEWS_DEFAULT_LAYOUT = "cinematic"

NEWS_FORMATS: dict[str, tuple[int, int]] = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
}

NEWS_LAYOUTS: list[tuple[str, str, str]] = [
    ("cinematic", "پوستر ۱: کاور سینمایی", "CINEMATIC"),
    ("magazine", "پوستر ۲: پوستر مجله‌ای", "EDITORIAL"),
    ("wire", "پوستر ۳: تلگراف تاکتیکی", "DATA WIRE"),
    ("dossier", "پوستر ۴: پرونده انتقال", "TRANSFER"),
]

NEWS_MOODS: list[tuple[str, str]] = [
    ("cinema", "سینمایی"),
    ("crimson", "درام قرمز"),
    ("navy", "سرمه‌ای"),
    ("noir", "سیاه‌وسفید"),
    ("raw", "اصلی"),
]

NEWS_PHOTOS: list[tuple[str, str]] = [
    ("tunnel", "تونل ورزشگاه"),
    ("stadium", "ورزشگاه شبانه"),
    ("ball", "توپ و باران"),
]

NEWS_DEFAULT_TINT = "light"
NEWS_TINT_MODES: list[tuple[str, str]] = [
    ("light", "شفاف (فیلتر کم)"),
    ("strong", "دراماتیک (فیلتر زیاد)"),
]


def _rgba(hex_c: str, alpha: float) -> str:
    c = (hex_c or "#E62E45").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    n = int(c, 16) if len(c) == 6 else 0xE62E45
    return f"rgba({(n >> 16) & 255},{(n >> 8) & 255},{n & 255},{alpha})"


def _mk_mode(mid: str, fa_lbl: str, en_lbl: str, badge: str, color: str, hi: str, seal: str, ticker: str) -> dict[str, str]:
    return {
        "id": mid,
        "fa": fa_lbl,
        "en": en_lbl,
        "badge": badge,
        "color": color,
        "hi": hi,
        "soft": _rgba(color, 0.21),
        "bd": _rgba(hi, 0.64),
        "glow": _rgba(color, 0.40),
        "seal": seal,
        "ticker": ticker,
    }


NEWS_MODES: dict[str, dict[str, str]] = {
    "breaking": _mk_mode("breaking", "خبر فوری", "BREAKING NEWS", "فوری | BREAKING", "#E62E45", "#FF6B7F",
                         "XGPEDIA | BREAKING WIRE | LIVE DESK |",
                         "BREAKING NEWS  ///  XGPEDIA LIVE DESK  ///  URGENT UPDATE  ///  @XGPEDIA"),
    "official": _mk_mode("official", "اعلام رسمی", "OFFICIAL", "رسمی | OFFICIAL", "#10B981", "#34D399",
                         "XGPEDIA | OFFICIAL STATEMENT | VERIFIED |",
                         "OFFICIAL ANNOUNCEMENT  ///  CLUB CONFIRMED  ///  XGPEDIA VERIFIED  ///  @XGPEDIA"),
    "transfer": _mk_mode("transfer", "نقل‌وانتقالات", "HERE WE GO", "نقل‌وانتقال | TRANSFER", "#F59E0B", "#FBBF24",
                         "XGPEDIA | TRANSFER WIRE | DONE DEAL |",
                         "TRANSFER WINDOW  ///  DEAL CONFIRMED  ///  XGPEDIA MERCATO  ///  @XGPEDIA"),
    "exclusive": _mk_mode("exclusive", "اختصاصی", "EXCLUSIVE", "اختصاصی | EXCLUSIVE", "#38BDF8", "#7DD3FC",
                          "XGPEDIA | EXCLUSIVE REPORT | DATA DESK |",
                          "XGPEDIA EXCLUSIVE  ///  VERIFIED INTELLIGENCE  ///  TACTICAL DESK  ///  @XGPEDIA"),
    "alert": _mk_mode("alert", "هشدار پزشکی", "SQUAD ALERT", "پزشکی | MEDICAL ALERT", "#F97316", "#FB923C",
                      "XGPEDIA | MEDICAL REPORT | SQUAD IMPACT |",
                      "MEDICAL UPDATE  ///  SQUAD AVAILABILITY  ///  XGPEDIA FITNESS DESK  ///  @XGPEDIA"),
}

_TIER_LABELS: dict[str, tuple[int, str]] = {
    "OFFICIAL": (4, "تایید رسمی باشگاه"),
    "TIER 1": (4, "منبع درجه یک | TIER 1"),
    "TIER 2": (3, "منبع معتبر | TIER 2"),
    "EXCLUSIVE": (4, "اختصاصی XGPedia"),
}


@lru_cache(maxsize=6)
def _news_photo_data_uri(photo_id: str) -> str | None:
    if photo_id not in ("tunnel", "stadium", "ball"):
        photo_id = "tunnel"
    p = ROOT / "brand" / "backgrounds" / f"news_{photo_id}.webp"
    if not p.exists():
        return None
    return f"data:image/webp;base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"


def get_news_layout_availability(item: dict[str, Any]) -> dict[str, bool]:
    """تعیین در دسترس بودن هر ۴ پوستر برای خبر فعلی (dossier نیازمند دیتای واقعی انتقال است)."""
    tr = item.get("transfer")
    has_tr = bool(isinstance(tr, dict) and tr.get("from") and tr.get("to"))
    return {
        "cinematic": True,
        "magazine": True,
        "wire": True,
        "dossier": has_tr,
    }


def get_news_slide_modules(item: dict[str, Any], layout: str) -> tuple[list[dict[str, Any]], list[str]]:
    """ماژول‌های قابل انتخاب داخل هر اسلاید خبر (فقط ماژول‌های دارای دیتا فعال می‌شوند)."""
    stats = item.get("stats") or []
    quote = str(item.get("quote") or "").strip()
    tr = item.get("transfer")
    bullets = [b for b in (item.get("bullets") or []) if str(b).strip()]

    has_stats = isinstance(stats, list) and len(stats) >= 1
    has_quote = bool(quote)
    has_tr = isinstance(tr, dict) and bool(tr.get("from") and tr.get("to"))
    has_bullets = len(bullets) >= 1

    mods: list[dict[str, Any]] = [
        {"id": "seal", "title_fa": "مُهر تایید دایره‌ای (SVG Seal)", "enabled": True},
        {"id": "ticker", "title_fa": "نوار تیکر خبری زنده", "enabled": True},
        {"id": "pitch", "title_fa": "نقشه زمین و رادار XGPedia", "enabled": True},
        {"id": "hl_box", "title_fa": "هایلایت باکس‌دار کلمات *ستاره‌دار*", "enabled": False},
    ]
    missing: list[str] = []

    pref_dock = str(item.get("dock") or "none")
    dock_specs = [
        ("dock_stats", "۳ کارت آماری پایین", has_stats, pref_dock == "stats"),
        ("dock_quote", "نقل‌قول رسمی پایین", has_quote, pref_dock == "quote"),
        ("dock_transfer", "پل انتقال باشگاه‌ها", has_tr, pref_dock == "transfer"),
        ("dock_bullets", "نکات کلیدی پایین", has_bullets, pref_dock == "bullets"),
    ]
    for mid, title_fa, has_data, default_on in dock_specs:
        if has_data:
            mods.append({"id": mid, "title_fa": title_fa, "enabled": default_on})
        else:
            missing.append(title_fa)
    return mods, missing


def _format_headline_html(raw: str, hl_box: bool) -> str:
    """تبدیل *کلمه* به هایلایت رنگی یا باکس‌دار با رعایت ترتیب امن esc(fa(...))."""
    safe = esc(fa(raw or ""))
    cls = "hl-box" if hl_box else "hl-mark"
    return re.sub(r"\*([^*]+)\*", rf'<span class="{cls}">\1</span>', safe)


def _shield_svg(code: str, color: str, size: int, uid: str) -> str:
    p = ensure_dark_bg_contrast(color or "#E62E45", bg="#0D1730", min_ratio=4.2)
    cd = esc((code or "FC")[:4].upper())
    d = "M90 16L150 40V88C150 128 124.5 156.5 90 166C55.5 156.5 30 128 30 88V40Z"
    fs = 26 if len(cd) > 3 else 31
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 180 180" fill="none" style="filter:drop-shadow(0 10px 20px rgba(0,0,0,.55));display:block;">'
        f'<defs><clipPath id="cl_{uid}"><path d="{d}"/></clipPath></defs>'
        f'<path d="M90 12L154 38V88C154 130.5 127 160.5 90 170.5C53 160.5 26 130.5 26 88V38Z" fill="{p}" fill-opacity=".22"/>'
        f'<g clip-path="url(#cl_{uid})"><rect x="25" y="12" width="130" height="158" fill="{p}"/>'
        f'<path d="M25 112L155 56V84L25 140Z" fill="#fff" fill-opacity=".24"/>'
        f'<path d="M90 16L150 40V58L90 34L30 58V40Z" fill="#fff" fill-opacity=".86"/></g>'
        f'<path d="{d}" stroke="#fff" stroke-opacity=".82" stroke-width="4.5"/>'
        f'<rect x="38" y="66" width="104" height="50" rx="14" fill="rgba(7,13,29,.82)" stroke="#fff" stroke-opacity=".45" stroke-width="2"/>'
        f'<text x="90" y="101" text-anchor="middle" fill="#fff" font-family="Space Grotesk,JetBrains Mono,sans-serif" font-weight="800" font-size="{fs}" letter-spacing="1.5">{cd}</text></svg>'
    )


def _seal_svg(pal: dict[str, str], size: int = 144) -> str:
    return (
        f'<svg dir="ltr" width="{size}" height="{size}" viewBox="0 0 160 160" fill="none" style="filter:drop-shadow(0 10px 24px rgba(0,0,0,.62));display:block;">'
        f'<defs><path id="sealPath" d="M80,80 m-56,0 a56,56 0 1,1 112,0 a56,56 0 1,1 -112,0"/></defs>'
        f'<circle cx="80" cy="80" r="74" fill="#070D1D" fill-opacity=".88" stroke="{pal["color"]}" stroke-width="2.5"/>'
        f'<circle cx="80" cy="80" r="68" stroke="{pal["hi"]}" stroke-opacity=".4" stroke-width="1.2" stroke-dasharray="4 4"/>'
        f'<circle cx="80" cy="80" r="40" fill="{pal["soft"]}" stroke="{pal["bd"]}" stroke-width="1.8"/>'
        f'<text fill="#F8FAFC" font-family="Space Grotesk,JetBrains Mono,sans-serif" font-size="11.2" font-weight="800" letter-spacing="2.0" direction="ltr" unicode-bidi="bidi-override">'
        f'<textPath href="#sealPath" startOffset="2%">{esc(pal["seal"])}</textPath></text>'
        f'<path d="M68 80l8 8 17-18" stroke="{pal["hi"]}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )


def _tier_badge(tier: str, pal: dict[str, str], compact: bool) -> str:
    bars, lbl = _TIER_LABELS.get(tier, (4, tier or "TIER 1"))
    bar_html = "".join(
        f'<span style="width:5px;height:{7 + i * 3}px;border-radius:3px;background:{pal["hi"] if i <= bars else "rgba(255,255,255,.18)"}"></span>'
        for i in range(1, 5)
    )
    return (
        f'<div class="nw-tier" style="border-color:{pal["bd"]}">'
        f'<div class="fi nw-tier-bars" dir="ltr">{bar_html}</div>'
        f'<span class="nw-tier-lbl" style="font-size:{16 if compact else 18}px">{esc(lbl)}</span>'
        f'</div>'
    )


def _transfer_bridge(tr: dict[str, Any], pal: dict[str, str], is_sq: bool, solid: bool, uid: str) -> str:
    sz = 66 if is_sq else (80 if solid else 76)
    fc = ensure_dark_bg_contrast(str(tr.get("fromColor") or "#64748B"), bg="#0D1730", min_ratio=4.5)
    tc = ensure_dark_bg_contrast(str(tr.get("toColor") or pal["color"]), bg="#0D1730", min_ratio=4.5)
    fee_style = (
        f"background:{pal['color']};color:#070D1D"
        if solid else f"background:{pal['soft']};border:1.5px solid {pal['bd']};color:{pal['hi']}"
    )
    box_style = (
        f"border-color:{pal['bd']};background:linear-gradient(135deg,rgba(16,29,59,.94),rgba(7,13,29,.96))"
        if solid else ""
    )
    return (
        f'<div class="xm nw-tx-box" style="{box_style}">'
        f'<div class="nw-tx-grid">'
        f'<div class="nw-tx-side">{_shield_svg(str(tr.get("fromCode") or "FRM"), fc, sz, uid + "f")}'
        f'<div class="nw-minw-0"><div class="nw-tx-sub">{"از باشگاه" if solid else "باشگاه مبدأ"}</div>'
        f'<div class="nw-tx-name" style="font-size:{22 if is_sq else 26}px">{esc(fa(tr.get("from", "")))}</div></div></div>'
        f'<div class="nw-tx-mid">'
        f'<span class="nw-tx-fee" style="{fee_style}">{esc(fa(tr.get("fee", "")))}</span>'
        f'<div class="nw-tx-arrow" dir="ltr">'
        f'<span class="nw-tx-line" style="background:linear-gradient(90deg,{fc},{tc})"></span>'
        f'<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{pal["hi"]}" stroke-width="2.9" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>'
        f'</div>'
        f'<span class="nw-tx-contract">{esc(fa(tr.get("contract", "")))}</span></div>'
        f'<div class="nw-tx-side nw-tx-right">'
        f'<div class="nw-minw-0" style="text-align:left"><div class="nw-tx-sub" style="color:{pal["hi"]}">{"به باشگاه" if solid else "باشگاه مقصد"}</div>'
        f'<div class="nw-tx-name" style="font-size:{22 if is_sq else 26}px">{esc(fa(tr.get("to", "")))}</div></div>'
        f'{_shield_svg(str(tr.get("toCode") or "DST"), tc, sz, uid + "t")}</div>'
        f'</div></div>'
    )


def _render_dock(item: dict[str, Any], enabled: set[str], pal: dict[str, str], is_wide: bool, is_sq: bool) -> str:
    # انتخاب اولین داک فعال و دارای دیتا
    if "dock_stats" in enabled and item.get("stats"):
        stats = [s for s in (item.get("stats") or []) if isinstance(s, dict)][:3]
        cards = "".join(
            f'<div class="xm nw-stat-card" style="border-top:3px solid {pal["color"] if i == 0 else "rgba(255,255,255,.18)"}">'
            f'<div class="fbw nw-gap-8"><span class="nw-stat-lbl">{esc(fa(st.get("l", "")))}</span>'
            f'<span class="fm nw-stat-idx">0{i + 1}</span></div>'
            f'<div class="nw-stat-val" style="font-size:{24 if is_sq else (26 if is_wide else 28)}px;color:{pal["hi"] if i == 0 else "#FFFFFF"}">{esc(fa(st.get("v", "")))}</div>'
            f'</div>'
            for i, st in enumerate(stats)
        )
        return f'<div class="nw-grid-{len(stats)} nw-gap-14">{cards}</div>'

    if "dock_quote" in enabled and item.get("quote"):
        return (
            f'<div class="xe nw-quote-card" style="border-right:6px solid {pal["color"]}">'
            f'<div class="fi nw-quote-inner">'
            f'<span class="fd nw-quote-mark" style="color:{pal["color"]}">“</span>'
            f'<div class="nw-flex-1 nw-minw-0">'
            f'<p class="nw-quote-txt" style="font-size:{21 if is_sq else 23}px">{esc(fa(item.get("quote", "")))}</p>'
            f'<div class="fi nw-gap-10 nw-mt-10"><span class="nw-quote-bar" style="background:{pal["hi"]}"></span>'
            f'<span class="nw-quote-author" style="color:{pal["hi"]}">{esc(fa(item.get("qauthor", "")))}</span></div>'
            f'</div></div></div>'
        )

    if "dock_transfer" in enabled and isinstance(item.get("transfer"), dict):
        return _transfer_bridge(item["transfer"], pal, is_sq, False, "dk")

    if "dock_bullets" in enabled and item.get("bullets"):
        buls = [str(b).strip() for b in (item.get("bullets") or []) if str(b).strip()][:3]
        rows = "".join(
            f'<div class="fi nw-bul-row">'
            f'<span class="nw-bul-num fm" style="background:{pal["soft"]};border-color:{pal["bd"]};color:{pal["hi"]}">{esc(fa(i + 1))}</span>'
            f'<p class="nw-bul-txt" style="font-size:{19.5 if is_sq else 21.5}px">{esc(fa(b))}</p>'
            f'</div>'
            for i, b in enumerate(buls)
        )
        return f'<div class="xe nw-bul-card">{rows}</div>'

    return ""


def _brand_logo_html() -> str:
    uri = _brand_logo_data_uri(mono=False)
    if uri:
        return f'<div class="nw-brand" dir="ltr"><img src="{uri}" alt="XGPedia" class="nw-brand-img"></div>'
    return '<div class="nw-brand" dir="ltr"><div class="fd nw-brand-txt"><span style="color:#E62E45">XG</span><span style="color:#F8FAFC">Pedia</span></div></div>'


@with_sample_badge
def render_news_html(
    item: dict[str, Any],
    *,
    layout: str = NEWS_DEFAULT_LAYOUT,
    mode: str | None = None,
    fmt: str = "4:5",
    mood: str | None = None,
    photo_id: str | None = None,
    tint_mode: str | None = None,
    enabled_modules: list[str] | None = None,
) -> str:
    """تولید HTML کامل و ۱۰۰٪ آفلاین برای کارت خبر فوری و رسمی (PRO WIRE v2)."""
    layout = layout if layout in ("cinematic", "magazine", "wire", "dossier") else NEWS_DEFAULT_LAYOUT
    eff_mode = mode if mode in NEWS_MODES else str(item.get("mode") or "breaking")
    base_pal = dict(NEWS_MODES.get(eff_mode, NEWS_MODES["breaking"]))
    custom_c = item.get("customColor")
    if custom_c:
        vis_c = ensure_dark_bg_contrast(str(custom_c), bg="#0D1730", min_ratio=4.8)
        base_pal.update({
            "color": vis_c, "hi": vis_c,
            "soft": _rgba(vis_c, 0.22), "bd": _rgba(vis_c, 0.65), "glow": _rgba(vis_c, 0.42),
        })
    else:
        base_pal["hi"] = ensure_dark_bg_contrast(base_pal["hi"], bg="#0D1730", min_ratio=4.8)
    pal = base_pal

    w, h = NEWS_FORMATS.get(fmt, NEWS_FORMATS["4:5"])
    is_story = fmt == "9:16"
    is_wide = fmt == "16:9"
    is_sq = fmt == "1:1"

    # هم‌ترازی دقیق با استاندارد Post-Match + افزایش ۴ پیکسلی فاصله عمودی بالا
    pad_top, pad_bot = (139, 171) if is_story else ((22, 16) if is_wide else (24, 20))

    avail_mods, _ = get_news_slide_modules(item, layout)
    if enabled_modules is not None:
        enabled = set(enabled_modules)
    else:
        enabled = {m["id"] for m in avail_mods if m["enabled"]}

    show_seal = "seal" in enabled
    show_ticker = "ticker" in enabled
    show_pitch = "pitch" in enabled
    hl_box = "hl_box" in enabled

    eff_mood = mood if mood in dict(NEWS_MOODS) else str(item.get("mood") or "cinema")
    eff_tint = tint_mode if tint_mode in ("light", "strong") else str(item.get("tint_mode") or NEWS_DEFAULT_TINT)
    is_light_tint = eff_tint == "light"
    cin_glow_color = _rgba(pal["color"], 0.10) if is_light_tint else pal["glow"]
    cin_fade_css = (
        "linear-gradient(to bottom,rgba(13,23,48,.52) 0%,rgba(13,23,48,.03) 20%,rgba(13,23,48,.08) 58%,rgba(13,23,48,.76) 84%,#0D1730 98%,#0D1730 100%)"
        if is_light_tint else
        "linear-gradient(to bottom,rgba(13,23,48,.82) 0%,rgba(13,23,48,.12) 32%,rgba(13,23,48,.58) 68%,#0D1730 92%,#0D1730 100%)"
    )
    photo_grad_w_css = (
        "linear-gradient(to top,rgba(13,23,48,.72) 0%,rgba(13,23,48,.04) 45%,rgba(13,23,48,.22) 100%)"
        if is_light_tint else
        "linear-gradient(to top,#0D1730 0%,rgba(13,23,48,.18) 45%,rgba(13,23,48,.45) 100%)"
    )
    photo_grad_b_css = (
        "linear-gradient(to top,rgba(13,23,48,.66) 0%,rgba(13,23,48,.03) 52%,rgba(13,23,48,.18) 100%)"
        if is_light_tint else
        "linear-gradient(to top,rgba(13,23,48,.90) 0%,rgba(13,23,48,.10) 55%,rgba(13,23,48,.35) 100%)"
    )
    cinema_filter_css = "contrast(1.06) saturate(1.03) brightness(1.01)" if is_light_tint else "contrast(1.12) saturate(.92) brightness(.94)"
    eff_photo_id = photo_id if photo_id in dict(NEWS_PHOTOS) else str(item.get("photoId") or "tunnel")
    real_photo = str(item.get("photoDataUri") or "").strip()
    if not real_photo:
        raw_u = str(item.get("photoUrl") or "").strip()
        if raw_u.startswith("data:image/"):
            real_photo = raw_u
    photo_uri = real_photo or _news_photo_data_uri(eff_photo_id) or ""
    fy = int(item.get("fy") if item.get("fy") is not None else 35)
    fz = int(item.get("fz") if item.get("fz") is not None else 105)
    img_style = "object-position:50% 22%;" if real_photo else f"object-position:50% {fy}%;transform:scale({fz / 100:.2f})"

    hl_html = _format_headline_html(str(item.get("headline") or item.get("title") or ""), hl_box)
    lead_html = esc(fa(item.get("lead") or ""))
    kicker_html = esc(fa(item.get("kicker") or ""))
    tier_str = str(item.get("tier") or "TIER 1")
    dock_html = _render_dock(item, enabled, pal, is_wide, is_sq)

    # اگر layout == dossier بود ولی دیتای انتقال نداشت، به cinematic برمی‌گردد (اصل null ≠ 0)
    tr_data = item.get("transfer") if isinstance(item.get("transfer"), dict) else None
    if layout == "dossier" and not (tr_data and tr_data.get("from") and tr_data.get("to")):
        layout = "cinematic"

    if layout == "cinematic":
        h_sz = 52 if is_wide else (46 if is_sq else (60 if is_story else 54))
        l_sz = 21 if is_wide else (20 if is_sq else (25 if is_story else 22.5))
        if is_wide:
            body_html = (
                f'<div class="nw-wide-grid">'
                f'<div class="nw-col-7 fcol nw-justify-between nw-gap-16 nw-minw-0">'
                f'<div class="fcol nw-gap-14 nw-my-auto">'
                f'<div class="fi nw-gap-12"><span class="nw-kicker-bar" style="background:{pal["color"]}"></span>'
                f'<span class="nw-kicker-txt" style="color:{pal["hi"]}">{kicker_html}</span></div>'
                f'<h1 class="nw-h1" style="font-size:{h_sz}px">{hl_html}</h1>'
                f'<p class="nw-lead" style="font-size:{l_sz}px">{lead_html}</p>'
                f'</div>{dock_html}</div>'
                f'<div class="nw-col-5 nw-photo-card">'
                f'<img src="{photo_uri}" alt="" class="nw-photo-fill photo-mood-{eff_mood}" style="{img_style}">'
                f'<div class="nw-photo-grad-w"></div>'
                f'<div class="nw-abs-tl">{_tier_badge(tier_str, pal, True)}</div>'
                f'{f"<div class=nw-abs-bl>{_seal_svg(pal, 132)}</div>" if show_seal else ""}'
                f'</div></div>'
            )
        else:
            ph_h = "53%" if is_story else ("50%" if is_sq else "54%")
            body_html = (
                f'<div class="nw-cin-bg" style="height:{ph_h}">'
                f'<img src="{photo_uri}" alt="" class="nw-photo-fill photo-mood-{eff_mood}" style="{img_style}">'
                f'<div class="nw-cin-fade"></div>'
                f'<div class="nw-cin-glow" style="background:radial-gradient(circle at 80% 30%,{cin_glow_color},transparent 58%)"></div>'
                f'</div>'
                f'<div class="nw-cin-stage">'
                f'<div class="fbw nw-align-end nw-gap-14">'
                f'<div class="fcol nw-align-start nw-gap-10">{_tier_badge(tier_str, pal, is_sq)}'
                f'<div class="fi nw-gap-10"><span class="nw-kicker-bar-sm" style="background:{pal["color"]}"></span>'
                f'<span class="nw-kicker-txt" style="font-size:{19.5 if is_sq else 22}px;color:{pal["hi"]}">{kicker_html}</span></div></div>'
                f'{f"<div class=nw-shrink-0>{_seal_svg(pal, 120 if is_sq else 140)}</div>" if show_seal else ""}'
                f'</div>'
                f'<div class="fcol nw-gap-10">'
                f'<h1 class="nw-h1" style="font-size:{h_sz}px">{hl_html}</h1>'
                f'<p class="nw-lead" style="font-size:{l_sz}px">{lead_html}</p>'
                f'</div>{dock_html}</div>'
            )
    elif layout == "magazine":
        h_sz = 48 if is_wide else (42 if is_sq else (56 if is_story else 48))
        wm = esc(pal["en"])
        if is_wide:
            body_html = (
                f'<div class="nw-wide-grid">'
                f'<div class="nw-col-5 nw-mag-wphoto">'
                f'<div class="nw-photo-card nw-mag-frame" style="border-color:{pal["bd"]}">'
                f'<img src="{photo_uri}" alt="" class="nw-photo-fill photo-mood-{eff_mood}" style="{img_style}">'
                f'<div class="nw-photo-grad-b"></div>'
                f'<div class="nw-mag-bot fbw">{_tier_badge(tier_str, pal, True)}<span class="fm nw-mag-iss">XGP-MAG // 26</span></div>'
                f'</div>'
                f'{f"<div class=nw-mag-seal-w>{_seal_svg(pal, 122)}</div>" if show_seal else ""}'
                f'</div>'
                f'<div class="nw-col-7 fcol nw-justify-between nw-gap-14 nw-minw-0">'
                f'<div class="nw-rel">'
                f'<div class="fd nw-wm-w" style="color:{pal["hi"]}" dir="ltr">{wm}</div>'
                f'<div class="nw-rel nw-z10 fcol nw-gap-10">'
                f'<div class="fi nw-gap-10"><span class="fm nw-ed-pill" style="background:{pal["color"]}">EDITORIAL</span>'
                f'<span class="nw-kicker-txt" style="color:{pal["hi"]}">{kicker_html}</span></div>'
                f'<h1 class="nw-h1" style="font-size:{h_sz}px">{hl_html}</h1>'
                f'<p class="nw-lead" style="font-size:20.5px">{lead_html}</p>'
                f'</div></div>{dock_html}</div></div>'
            )
        else:
            img_h = 520 if is_story else (300 if is_sq else 400)
            body_html = (
                f'<div class="nw-mag-stage">'
                f'<div class="nw-rel nw-pt-14">'
                f'<div class="fd nw-wm-v" style="font-size:{136 if is_sq else 160}px;color:{pal["hi"]}" dir="ltr">{wm}</div>'
                f'<div class="nw-photo-card nw-mag-frame nw-z10" style="height:{img_h}px;border-color:{pal["bd"]}">'
                f'<img src="{photo_uri}" alt="" class="nw-photo-fill photo-mood-{eff_mood}" style="{img_style}">'
                f'<div class="nw-photo-grad-b"></div>'
                f'<div class="nw-mag-spine"><span class="fm nw-mag-spine-txt">XGPEDIA DISPATCH // {wm}</span></div>'
                f'<div class="nw-mag-bot-v fbw">{_tier_badge(tier_str, pal, is_sq)}'
                f'<span class="fm nw-iss-pill" dir="ltr">ISSUE #26-27</span></div>'
                f'</div>'
                f'{f"<div class=nw-mag-seal-v>{_seal_svg(pal, 118 if is_sq else 138)}</div>" if show_seal else ""}'
                f'</div>'
                f'<div class="fcol nw-gap-10 nw-pt-6">'
                f'<div class="fi nw-gap-10"><span class="nw-vbar" style="background:{pal["color"]}"></span>'
                f'<span class="nw-kicker-txt" style="font-size:{19.5 if is_sq else 21.5}px;color:{pal["hi"]}">{kicker_html}</span></div>'
                f'<h1 class="nw-h1" style="font-size:{h_sz}px">{hl_html}</h1>'
                f'<p class="nw-lead" style="font-size:{19.5 if is_sq else 21.5}px">{lead_html}</p>'
                f'</div>{dock_html}</div>'
            )
    elif layout == "wire":
        h_sz = 56 if is_wide else (50 if is_sq else (64 if is_story else 58))
        l_sz = 23 if is_wide else (21.5 if is_sq else (26 if is_story else 24))
        body_html = (
            f'<div class="nw-wire-stage">'
            f'<div class="nw-wire-banner" style="background:linear-gradient(135deg,{pal["soft"]},rgba(9,16,35,.92));border-color:{pal["bd"]}">'
            f'<div class="nw-hazard"></div>'
            f'<div class="nw-wire-in fbw nw-gap-14">'
            f'<div class="fi nw-gap-14 nw-minw-0">'
            f'<div class="nw-bolt-box" style="background:{pal["color"]};box-shadow:0 0 24px {pal["glow"]}">'
            f'<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>'
            f'</div>'
            f'<div class="nw-minw-0"><div class="fm nw-wire-sub" style="color:{pal["hi"]}" dir="ltr">{esc(pal["en"])} // DISPATCH</div>'
            f'<div class="nw-wire-kicker">{kicker_html}</div></div>'
            f'</div>{_tier_badge(tier_str, pal, is_sq)}</div></div>'
            f'<div class="nw-wire-mid">'
            f'<div class="fd nw-wire-wm" style="font-size:{180 if is_wide else 142}px;color:{pal["hi"]}" dir="ltr">{esc(pal["en"])}</div>'
            f'<div class="fbw nw-align-start nw-gap-20 nw-rel nw-z10">'
            f'<h1 class="nw-h1 nw-flex-1" style="font-size:{h_sz}px">{hl_html}</h1>'
            f'{f"<div class=nw-shrink-0>{_seal_svg(pal, 122 if is_sq else 144)}</div>" if show_seal else ""}'
            f'</div>'
            f'<div class="nw-wire-lead" style="border-color:{pal["color"]}">'
            f'<p class="nw-lead" style="font-size:{l_sz}px">{lead_html}</p></div>'
            f'</div>{dock_html}</div>'
        )
    else:  # dossier
        h_sz = 46 if is_wide else (40 if is_sq else (52 if is_story else 46))
        br_html = _transfer_bridge(tr_data or {}, pal, is_sq, True, "dos")
        extra_dock = "" if "dock_transfer" in enabled else dock_html
        if is_wide:
            body_html = (
                f'<div class="nw-wide-grid">'
                f'<div class="nw-col-5 nw-photo-card nw-mag-frame" style="border-color:{pal["bd"]}">'
                f'<img src="{photo_uri}" alt="" class="nw-photo-fill photo-mood-{eff_mood}" style="{img_style}">'
                f'<div class="nw-photo-grad-b"></div>'
                f'<div class="nw-abs-tl">{_tier_badge(tier_str, pal, True)}</div>'
                f'{f"<div class=nw-abs-bl>{_seal_svg(pal, 126)}</div>" if show_seal else ""}'
                f'</div>'
                f'<div class="nw-col-7 fcol nw-justify-between nw-gap-14 nw-minw-0">'
                f'<div class="fcol nw-gap-10">'
                f'<div class="fi nw-gap-10"><span class="nw-kicker-bar-sm" style="background:{pal["color"]}"></span>'
                f'<span class="nw-kicker-txt" style="color:{pal["hi"]}">{kicker_html}</span></div>'
                f'<h1 class="nw-h1" style="font-size:{h_sz}px">{hl_html}</h1>'
                f'<p class="nw-lead" style="font-size:20.5px">{lead_html}</p>'
                f'</div>{br_html}{extra_dock}</div></div>'
            )
        else:
            img_h = 460 if is_story else (280 if is_sq else 370)
            body_html = (
                f'<div class="nw-mag-stage">'
                f'<div class="nw-photo-card nw-mag-frame" style="height:{img_h}px;border-color:{pal["bd"]}">'
                f'<img src="{photo_uri}" alt="" class="nw-photo-fill photo-mood-{eff_mood}" style="{img_style}">'
                f'<div class="nw-photo-grad-b"></div>'
                f'<div class="nw-abs-tr">{_tier_badge(tier_str, pal, is_sq)}</div>'
                f'{f"<div class=nw-abs-bl>{_seal_svg(pal, 114 if is_sq else 134)}</div>" if show_seal else ""}'
                f'<div class="nw-dos-cap"><div class="fm nw-dos-tag" style="color:{pal["hi"]}" dir="ltr">TRANSFER DOSSIER</div>'
                f'<div class="nw-dos-kicker">{kicker_html}</div></div>'
                f'</div>{br_html}'
                f'<div class="fcol nw-gap-8">'
                f'<h1 class="nw-h1" style="font-size:{h_sz}px">{hl_html}</h1>'
                f'<p class="nw-lead" style="font-size:{19 if is_sq else 21}px">{lead_html}</p>'
                f'</div>{extra_dock}</div>'
            )

    ticker_html = (
        f'<div class="nw-ticker">'
        f'<div class="fbw nw-gap-16 fm nw-ticker-txt" dir="ltr" style="color:{pal["hi"]}">'
        f'<span>● {esc(pal["ticker"])}</span><span style="opacity:.65">{esc(tier_str)}</span></div></div>'
        if show_ticker else ""
    )

    # مختصات دقیق چهارگوشهٔ قرمز هم‌تراز با Post-Match (base_shell.py: 24px تا 44px)
    rx, cy, py_box = w - 147, int(h * 0.36), int(h * 0.15)
    crh_d = (
        f"M24 44V24H44M{w - 24} 44V24H{w - 44}"
        f"M24 {h - 44}V{h - 24}H44M{w - 24} {h - 44}V{h - 24}H{w - 44}"
    )
    pitch_lines = (
        f'<g stroke="#F8FAFC" stroke-opacity=".08" stroke-width="1.5">'
        f'<line x1="{w // 2}" y1="12" x2="{w // 2}" y2="{h - 12}" stroke-dasharray="8 8"/>'
        f'<circle cx="{w // 2}" cy="{cy}" r="155"/></g>'
        f'<g stroke="#F8FAFC" stroke-opacity=".06" stroke-width="1.5">'
        f'<rect x="12" y="{py_box}" width="135" height="360"/><rect x="{rx}" y="{py_box}" width="135" height="360"/></g>'
        f'<circle cx="{w // 2}" cy="{cy}" r="255" fill="url(#rf)"/>'
        f'<circle cx="{w // 2}" cy="{cy}" r="225" stroke="{pal["color"]}" stroke-opacity=".22" stroke-width="1.4" stroke-dasharray="5 7"/>'
        f'<circle cx="{w // 2}" cy="{cy}" r="315" stroke="#F8FAFC" stroke-opacity=".06"/>'
        if show_pitch else ""
    )

    if layout == "dossier" and tr_data:
        amb = (
            f"radial-gradient(circle at 86% 26%,{_rgba(str(tr_data.get('fromColor') or pal['color']), 0.32)},transparent 48%),"
            f"radial-gradient(circle at 14% 26%,{_rgba(str(tr_data.get('toColor') or pal['color']), 0.32)},transparent 48%),"
            f"radial-gradient(circle at 50% 82%,{pal['soft']},transparent 55%)"
        )
    else:
        amb = (
            f"radial-gradient(circle at 84% 24%,{pal['glow']},transparent 50%),"
            f"radial-gradient(circle at 14% 78%,rgba(56,189,248,.16),transparent 46%),"
            f"radial-gradient(circle at 50% 45%,{pal['soft']},transparent 58%)"
        )

    footer_tag = esc(str(item.get("footerTag") or "XGPEDIA | BREAKING DESK").upper())
    source_txt = esc(str(item.get("source") or "XGPedia Desk"))

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<title>{esc(item.get("title", "XGPedia Breaking News"))}</title>
<style>
{build_embedded_font_css()}
:root{{
  --ac:{pal["color"]};
  --ac-hi:{pal["hi"]};
  --ac-soft:{pal["soft"]};
  --ac-bd:{pal["bd"]};
  --ac-glow:{pal["glow"]};
}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{w}px;height:{h}px;overflow:hidden;background:#0D1730;color:#F8FAFC;
  font-family:'Vazirmatn',system-ui,sans-serif;font-feature-settings:"tnum";font-variant-numeric:tabular-nums}}
.fm{{font-family:'JetBrains Mono','Space Grotesk',monospace}}
.fd{{font-family:'Space Grotesk','Vazirmatn',sans-serif}}
.fi{{display:flex;align-items:center}}
.fbw{{display:flex;align-items:center;justify-content:space-between}}
.fcol{{display:flex;flex-direction:column}}
.nw-flex-1{{flex:1}}.nw-minw-0{{min-width:0}}.nw-shrink-0{{flex-shrink:0}}.nw-rel{{position:relative}}.nw-z10{{z-index:10}}
.nw-my-auto{{margin-top:auto;margin-bottom:auto}}.nw-mt-10{{margin-top:10px}}.nw-pt-14{{padding-top:14px}}.nw-pt-6{{padding-top:6px}}
.nw-align-end{{align-items:flex-end}}.nw-align-start{{align-items:flex-start}}.nw-justify-between{{justify-content:space-between}}
.nw-gap-8{{gap:8px}}.nw-gap-10{{gap:10px}}.nw-gap-12{{gap:12px}}.nw-gap-14{{gap:14px}}.nw-gap-16{{gap:16px}}.nw-gap-20{{gap:20px}}
.nw-grid-1{{display:grid;grid-template-columns:1fr}}.nw-grid-2{{display:grid;grid-template-columns:1fr 1fr}}.nw-grid-3{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr))}}

.nw-canvas{{
  position:relative;width:{w}px;height:{h}px;overflow:hidden;background:#0D1730;
  display:flex;flex-direction:column;justify-content:space-between;
  padding:{pad_top}px 0 {pad_bot}px;
}}
.nw-ambient{{position:absolute;inset:0;pointer-events:none;z-index:0;background:{amb}}}
.nw-frame-svg{{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0}}
.nw-scanlines{{position:absolute;inset:0;pointer-events:none;z-index:10;background:repeating-linear-gradient(to bottom,#ffffff04 0 1px,#0000 1px 4px)}}

/* Header: هم‌تراز با Post-Match + 4px فاصله عمودی بالا، قفل‌شده در یک ردیف تمیز */
.nw-header{{position:relative;z-index:20;padding:12px 36px 8px;display:flex;align-items:center;justify-content:space-between;gap:14px;flex-shrink:0}}
.nw-hdr-pills{{display:flex;align-items:center;flex-wrap:nowrap;gap:10px;min-width:0;overflow:hidden}}
.nw-mode-pill{{padding:5px 18px;border-radius:999px;font-size:20px;font-weight:900;display:inline-flex;align-items:center;gap:9px;
  color:#FFFFFF;background:var(--ac);box-shadow:0 8px 26px -4px var(--ac-glow);flex-shrink:0;white-space:nowrap}}
.nw-pulse-dot{{width:11px;height:11px;border-radius:999px;background:#FFFFFF;box-shadow:0 0 0 4px var(--ac-soft),0 0 14px var(--ac);flex-shrink:0}}
.nw-comp-pill{{padding:5px 15px;border-radius:999px;font-size:18.5px;font-weight:800;color:#F1F5F9;
  background:rgba(15,26,54,.86);border:1px solid rgba(255,255,255,.22);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.nw-time-pill{{padding:5px 14px;border-radius:999px;font-size:17.5px;font-weight:700;color:#E2E8F0;
  background:rgba(7,13,29,.78);border:1px solid rgba(255,255,255,.16);white-space:nowrap;flex-shrink:0}}
.nw-brand{{display:flex;align-items:center;flex-shrink:0}}
.nw-brand-img{{height:48px;width:auto;display:block;filter:drop-shadow(0 6px 14px rgba(0,0,0,.45))}}
.nw-brand-txt{{font-size:32px;font-weight:800;line-height:1}}

/* Stage, Ticker & Footer */
.nw-stage{{position:relative;z-index:10;flex:1;padding:8px 40px;display:flex;flex-direction:column;justify-content:space-between;min-height:0;overflow:hidden}}
.nw-ticker{{position:relative;z-index:20;padding:8px 40px;flex-shrink:0;overflow:hidden;
  background:linear-gradient(90deg,var(--ac-soft),rgba(13,23,48,.92) 30%,rgba(13,23,48,.92) 70%,var(--ac-soft));
  border-top:1px solid var(--ac-bd);border-bottom:1px solid var(--ac-bd)}}
.nw-ticker-txt{{font-size:15.5px;font-weight:800;letter-spacing:.14em;white-space:nowrap}}
.nw-footer{{position:relative;z-index:20;padding:10px 44px 10px;flex-shrink:0}}
.nw-footer-line{{border-top:1px solid rgba(255,255,255,.15);margin-bottom:8px}}
.nw-foot-dot{{width:11px;height:11px;border-radius:999px;background:var(--ac);box-shadow:0 0 12px var(--ac);flex-shrink:0}}
.nw-foot-tag{{font-size:16.5px;font-weight:800;letter-spacing:.12em;color:#E2E8F0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.nw-foot-handle{{font-size:19px;font-weight:800;color:#FFFFFF}}
.nw-foot-src{{font-size:16px;font-weight:600;color:#CBD5E1}}
.nw-sep{{color:#64748B}}

/* Surfaces & Highlights */
.xm,.xe{{position:relative;border-radius:22px;overflow:hidden;box-shadow:0 16px 38px -12px rgba(0,0,0,.62),inset 0 1px 0 rgba(255,255,255,.10)}}
.xm{{background:linear-gradient(165deg,rgba(16,29,59,.90),rgba(9,16,35,.96));border:1.5px solid rgba(248,250,252,.15)}}
.xe{{background:linear-gradient(155deg,rgba(18,31,61,.93),rgba(9,15,32,.97));border:1.5px solid rgba(127,166,232,.24)}}
.hl-mark{{color:var(--ac-hi);text-shadow:0 0 28px var(--ac-glow)}}
.hl-box{{display:inline-block;padding:0 14px 4px;margin:0 3px;border-radius:14px;background:var(--ac-soft);border:1.5px solid var(--ac-bd);color:#FFFFFF}}
.photo-mood-cinema{{filter:{cinema_filter_css}}}
.photo-mood-crimson{{filter:contrast(1.18) saturate(.75) brightness(.88) sepia(.14) hue-rotate(-14deg)}}
.photo-mood-navy{{filter:contrast(1.14) saturate(.78) brightness(.90) hue-rotate(12deg)}}
.photo-mood-noir{{filter:grayscale(1) contrast(1.26) brightness(.92)}}
.photo-mood-raw{{filter:contrast(1.04) saturate(1.04)}}
.nw-photo-fill{{width:100%;height:100%;object-fit:cover;display:block}}
.nw-photo-card{{position:relative;border-radius:26px;overflow:hidden;border:1.5px solid rgba(255,255,255,.20);box-shadow:0 22px 54px -14px rgba(0,0,0,.85)}}
.nw-photo-grad-w{{position:absolute;inset:0;background:{photo_grad_w_css}}}
.nw-photo-grad-b{{position:absolute;inset:0;background:{photo_grad_b_css}}}
.nw-abs-tl{{position:absolute;top:16px;left:16px;z-index:10}}
.nw-abs-tr{{position:absolute;top:16px;right:16px;z-index:10}}
.nw-abs-bl{{position:absolute;bottom:16px;left:16px;z-index:10}}

/* Tier Badge */
.nw-tier{{display:inline-flex;align-items:center;gap:10px;padding:6px 14px;border-radius:999px;background:rgba(7,13,29,.86);border:1px solid}}
.nw-tier-bars{{align-items:flex-end;gap:4px}}
.nw-tier-lbl{{font-weight:800;color:#FFFFFF;white-space:nowrap}}

/* Typography */
.nw-kicker-bar{{width:38px;height:6px;border-radius:99px;flex-shrink:0}}
.nw-kicker-bar-sm{{width:30px;height:6px;border-radius:99px;flex-shrink:0}}
.nw-kicker-txt{{font-size:21px;font-weight:800}}
.nw-h1{{font-weight:900;color:#FFFFFF;line-height:1.18;letter-spacing:-0.015em;text-shadow:0 8px 28px rgba(0,0,0,.65)}}
.nw-lead{{font-weight:600;color:#E2E8F0;line-height:1.60}}

/* Cinematic */
.nw-cin-bg{{position:absolute;top:0;left:0;right:0;z-index:0;overflow:hidden}}
.nw-cin-fade{{position:absolute;inset:0;background:{cin_fade_css}}}
.nw-cin-glow{{position:absolute;inset:0}}
.nw-cin-stage{{position:relative;z-index:10;flex:1;display:flex;flex-direction:column;justify-content:flex-end;gap:16px;min-height:0}}
.nw-wide-grid{{flex:1;display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:28px;align-items:stretch;min-height:0}}
.nw-col-7{{grid-column:span 7}}.nw-col-5{{grid-column:span 5}}

/* Magazine */
.nw-mag-stage{{flex:1;display:flex;flex-direction:column;justify-content:space-between;gap:14px;min-height:0}}
.nw-mag-frame{{border-width:2px}}
.nw-mag-wphoto{{position:relative;height:100%;display:flex;flex-direction:column;justify-content:center}}
.nw-mag-bot{{position:absolute;bottom:16px;left:16px;right:16px;z-index:10}}
.nw-mag-bot-v{{position:absolute;bottom:16px;left:18px;right:54px;z-index:10}}
.nw-mag-iss{{font-size:14px;font-weight:800;color:rgba(255,255,255,.82)}}
.nw-iss-pill{{padding:4px 14px;border-radius:999px;background:rgba(7,13,29,.86);border:1px solid rgba(255,255,255,.18);font-size:14.5px;font-weight:800;color:#E2E8F0}}
.nw-mag-seal-w{{position:absolute;top:-14px;left:-14px;z-index:20}}
.nw-mag-seal-v{{position:absolute;bottom:-28px;left:22px;z-index:20}}
.nw-mag-spine{{position:absolute;top:0;bottom:0;right:0;width:38px;background:rgba(7,13,29,.84);border-left:1px solid rgba(255,255,255,.15);display:flex;align-items:center;justify-content:center}}
.nw-mag-spine-txt{{font-size:12.5px;font-weight:800;letter-spacing:.24em;color:#CBD5E1;text-transform:uppercase;white-space:nowrap;writing-mode:vertical-rl;transform:rotate(180deg)}}
.nw-wm-w{{font-size:108px;font-weight:900;text-transform:uppercase;line-height:1;opacity:.09;margin-bottom:-28px;pointer-events:none}}
.nw-wm-v{{position:absolute;top:-22px;left:0;right:0;text-align:center;font-weight:900;text-transform:uppercase;line-height:1;opacity:.09;white-space:nowrap;overflow:hidden;pointer-events:none}}
.nw-ed-pill{{padding:4px 12px;border-radius:8px;font-size:14px;font-weight:900;color:#FFFFFF}}
.nw-vbar{{width:9px;height:28px;border-radius:99px;flex-shrink:0}}

/* Wire */
.nw-wire-stage{{flex:1;display:flex;flex-direction:column;justify-content:space-between;gap:18px;min-height:0}}
.nw-wire-banner{{border-radius:22px;overflow:hidden;border:1.5px solid}}
.nw-hazard{{height:10px;width:100%;background:repeating-linear-gradient(-45deg,var(--ac) 0 10px,transparent 10px 20px)}}
.nw-wire-in{{padding:14px 22px}}
.nw-bolt-box{{width:48px;height:48px;border-radius:15px;display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.nw-wire-sub{{font-size:14.5px;font-weight:800;letter-spacing:.16em;text-transform:uppercase}}
.nw-wire-kicker{{font-size:21px;font-weight:900;color:#FFFFFF}}
.nw-wire-mid{{position:relative;margin:auto 0;padding:8px 0;display:flex;flex-direction:column;gap:18px}}
.nw-wire-wm{{position:absolute;left:-8px;top:-36px;font-weight:900;text-transform:uppercase;line-height:1;opacity:.06;pointer-events:none}}
.nw-wire-lead{{position:relative;z-index:10;padding-right:20px;border-right:4px solid}}

/* Dossier */
.nw-dos-cap{{position:absolute;bottom:16px;right:20px;max-width:68%;z-index:10}}
.nw-dos-tag{{font-size:14px;font-weight:800;letter-spacing:.18em;text-transform:uppercase}}
.nw-dos-kicker{{font-size:21px;font-weight:900;color:#FFFFFF}}

/* Docks */
.nw-stat-card{{padding:16px 18px;display:flex;flex-direction:column;justify-content:space-between;gap:8px}}
.nw-stat-lbl{{font-size:16px;font-weight:700;color:#CBD5E1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.nw-stat-idx{{font-size:12px;font-weight:800;opacity:.55}}
.nw-stat-val{{font-weight:900;line-height:1.18}}
.nw-quote-card{{padding:18px 22px}}
.nw-quote-inner{{align-items:flex-start;gap:14px}}
.nw-quote-mark{{font-size:62px;font-weight:900;line-height:1;opacity:.65;margin-top:-8px;flex-shrink:0}}
.nw-quote-txt{{font-weight:700;color:#F8FAFC;line-height:1.55}}
.nw-quote-bar{{width:24px;height:2px;border-radius:99px}}
.nw-quote-author{{font-size:17.5px;font-weight:800}}
.nw-bul-card{{padding:16px 22px;display:flex;flex-direction:column;gap:10px}}
.nw-bul-row{{align-items:flex-start;gap:12px}}
.nw-bul-num{{width:28px;height:28px;border-radius:8px;border:1px solid;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:900;flex-shrink:0;margin-top:2px}}
.nw-bul-txt{{font-weight:700;color:#F1F5F9;line-height:1.45}}
.nw-tx-box{{padding:16px 22px}}
.nw-tx-grid{{display:grid;grid-template-columns:4fr 3fr 4fr;align-items:center;gap:12px}}
.nw-tx-side{{display:flex;align-items:center;gap:12px;min-width:0}}
.nw-tx-right{{justify-content:flex-end}}
.nw-tx-sub{{font-size:14px;font-weight:700;color:#94A3B8}}
.nw-tx-name{{font-weight:900;color:#FFFFFF;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.nw-tx-mid{{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px}}
.nw-tx-fee{{padding:4px 14px;border-radius:999px;font-size:15.5px;font-weight:900;white-space:nowrap}}
.nw-tx-arrow{{width:100%;display:flex;align-items:center;gap:4px}}
.nw-tx-line{{height:3px;flex:1;border-radius:99px}}
.nw-tx-contract{{font-size:15px;font-weight:800;color:#E2E8F0;white-space:nowrap}}

footer, footer .fbw, footer .cf-row, footer .fi, footer .cf-left, footer .cf-right, .xg-footer, .foot-row, .card-footer{{flex-wrap:nowrap!important;white-space:nowrap!important;min-width:0!important;}}
footer span, footer div, .pl-foot-tag, .pl-foot-s, .in-foot-tag, .pr-foot-tag, .st-foot-tag, .cf-tag{{white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;min-width:0!important;}}
</style>
</head>
<body>
<div class="nw-canvas" dir="rtl">
  <div class="nw-ambient"></div>
  <svg class="nw-frame-svg" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid slice" fill="none">
    <defs>
      <pattern id="tg" width="54" height="54" patternUnits="userSpaceOnUse"><path d="M54 0H0v54" stroke="#F8FAFC" stroke-opacity=".052"/></pattern>
      <radialGradient id="rf" cx="50%" cy="32%" r="48%">
        <stop offset="0" stop-color="{pal["color"]}" stop-opacity=".22"/>
        <stop offset=".55" stop-color="{pal["color"]}" stop-opacity=".05"/>
        <stop offset="1" stop-color="{pal["color"]}" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect width="100%" height="100%" fill="url(#tg)"/>
    <rect x="12" y="12" width="{w - 24}" height="{h - 24}" rx="18" stroke="#F8FAFC" stroke-opacity=".12" stroke-width="1.5"/>
    {pitch_lines}
    <path d="{crh_d}" stroke="{pal["color"]}" stroke-opacity=".62" stroke-width="2.2"/>
  </svg>
  <div class="nw-scanlines"></div>
  <header class="nw-header">
    <div class="nw-hdr-pills">
      <div class="nw-mode-pill"><span class="nw-pulse-dot"></span><span>{esc(pal["badge"])}</span></div>
      <div class="nw-comp-pill">{esc(fa(item.get("comp", "")))}</div>
      <div class="nw-time-pill">{esc(fa(item.get("time", "")))}</div>
    </div>
    {_brand_logo_html()}
  </header>
  <main class="nw-stage">{body_html}</main>
  {ticker_html}
  <footer class="nw-footer">
    <div class="nw-footer-line"></div>
    <div class="fbw nw-gap-14">
      <div class="fi nw-gap-10 nw-minw-0">
        <span class="nw-foot-dot"></span>
        <span dir="ltr" class="fm nw-foot-tag">{footer_tag}</span>
      </div>
      <div class="fi nw-gap-10 fm nw-shrink-0" dir="ltr">
        <span class="nw-foot-handle">@XGPedia</span>
        <span class="nw-sep">|</span>
        <span class="nw-foot-src">{source_txt}</span>
      </div>
    </div>
  </footer>
</div>
</body>
</html>"""


def build_news_caption(item: dict[str, Any], *, mode: str | None = None) -> str:
    """تولید کپشن مفصل و غیرتکراری فارسی برای پست خبر (در telegram_publish تیتر تکراری به‌صورت خودکار حذف می‌شود)."""
    eff_mode = mode if mode in NEWS_MODES else str(item.get("mode") or "breaking")
    m_fa = NEWS_MODES.get(eff_mode, NEWS_MODES["breaking"])["fa"]
    headline = fa(str(item.get("headline") or item.get("title") or "").replace("*", ""))
    body = fa(str(item.get("body_fa") or item.get("lead") or "").strip())
    bullets = [fa(str(b).strip()) for b in (item.get("bullets") or []) if str(b).strip()]
    quote = fa(str(item.get("quote") or "").strip())
    qauthor = fa(str(item.get("qauthor") or "").strip())

    parts: list[str] = [f"📰 {m_fa} | {headline}"]
    if body:
        parts.append(body)
    if bullets:
        parts.append("\n".join(f"• {b}" for b in bullets[:3]))
    if quote:
        parts.append(f"💬 {quote}" + (f" — {qauthor}" if qauthor else ""))
    return "\n\n".join(parts)
