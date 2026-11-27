"""کارت اسلایدی «این یا اون؟» (XGPedia This or That Studio — Showreel Edition, D49) — بازسازی ۱:۱ دقیق.

ویژگی‌های ۱:۱ حفظ‌شده از This or that.html + استانداردهای XGPedia:
  - هر ۴ موتور گرافیکی مستقل: `diagonal` (برش مورب با اعداد واترمارک ۲۲۰px، خطوط موازی خط‌چین و لوزی یا/OR)، `split` (دوئل مجله‌ای)، `cards` (کارت کلکسیونی فویل سه‌بعدی با زاویه ۱.۶°)، `rapid` (چالش ۵ مرحله‌ای استوری)
  - جزئیات کامل گرافیکی: پیراهن SVG با هایلایت شاین/سرآستین/نشان سینه، سپر SVG با گرادینت متالیک و نور بالا، دایره‌های رادار و خط میانی پس‌زمینه، آیکون پیام در کادر CTA
  - ۱۰۰٪ آفلاین بدون CDN + هم‌ترازی دقیق چهارگوشهٔ قرمز و فاصله عمودی بالا (+4px) با استاندارد Post-Match.
"""
from __future__ import annotations

from typing import Any

from src.xgpedia.render.card_kit.helpers import with_sample_badge, ensure_dark_bg_contrast, esc, fa
from src.xgpedia.render.cards import _brand_logo_data_uri
from src.xgpedia.render.studio_engine import build_embedded_font_css

TOT_DEFAULT_LAYOUT = "diagonal"

TOT_FORMATS: dict[str, tuple[int, int]] = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}

TOT_LAYOUTS: list[tuple[str, str, str]] = [
    ("diagonal", "برش مورب (Showreel)", "CLASH"),
    ("split", "دوئل مجله‌ای (Split)", "SPLIT"),
    ("cards", "کارت کلکسیونی (Foil)", "FOIL"),
    ("rapid", "چالش ۵ مرحله‌ای (Rapid)", "5× RAPID"),
]

_DEFAULT_ROUNDS = [
    {"cat": "فلسفه بازی", "a": "تیکی‌تاکای خالص", "b": "گگن‌پرسینگِ بی‌امان", "cA": "#38BDF8", "cB": "#E62E45"},
    {"cat": "جادوی هافبک", "a": "پاس عمقی دبروینه", "b": "خارج پای مودریچ", "cA": "#06B6D4", "cB": "#F59E0B"},
    {"cat": "هیجان سکوها", "a": "آزادیِ پر در دربی", "b": "آنفیلد در شب اروپا", "cA": "#10B981", "cB": "#EF0107"},
    {"cat": "لحظه جاودان", "a": "گل دقیقه ۹۰+۴", "b": "مهار پنالتی فینال", "cA": "#A855F7", "cB": "#3B82F6"},
    {"cat": "قهرمان تاریخ", "a": "فصل بی‌شکست لیگ", "b": "قهرمانی لیگ قهرمانان", "cA": "#F59E0B", "cB": "#E62E45"},
]


def _lum(hex_c: str) -> float:
    c = (hex_c or "#E62E45").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    n = int(c, 16) if len(c) == 6 else 0xE62E45
    vals = []
    for ch in ((n >> 16) & 255, (n >> 8) & 255, n & 255):
        v = ch / 255.0
        vals.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    return vals[0] * 0.2126 + vals[1] * 0.7152 + vals[2] * 0.0722


def _ctr(hex_c: str) -> str:
    return "#070D1D" if _lum(hex_c) > 0.56 else "#FFFFFF"


def get_tot_modules(item: dict[str, Any]) -> list[dict[str, Any]]:
    has_stats = bool(isinstance(item.get("stats"), list) and len(item["stats"]) > 0)
    return [
        {"id": "stats", "title_fa": "نوار مقایسه شاخص‌های کلیدی (۳ شاخص)", "enabled": has_stats},
        {"id": "poll", "title_fa": "نوار درصد رأی مخاطبان (Poll Split)", "enabled": False},
        {"id": "cta", "title_fa": "کادر دعوت به کامنت (CTA)", "enabled": True},
        {"id": "tags", "title_fa": "تگ‌های سبک بازی و ویژگی‌ها", "enabled": True},
        {"id": "sticker", "title_fa": "کادر استیکر نظرسنجی (مخصوص 9:16)", "enabled": False},
        {"id": "foil", "title_fa": "افکت براق هولوگرافیک (Foil)", "enabled": True},
    ]


def _brand_logo_html() -> str:
    uri = _brand_logo_data_uri(mono=False)
    if uri:
        return f'<div class="tt-brand" dir="ltr"><img src="{uri}" alt="XGPedia" class="tt-brand-img"></div>'
    return '<div class="tt-brand" dir="ltr"><div class="fd tt-brand-txt"><span style="color:#E62E45">XG</span><span style="color:#F8FAFC">Pedia</span></div></div>'


def _jersey_svg(side: dict[str, Any], uid: str, size: int) -> str:
    """پیراهن تاکتیکی SVG دقیقاً مطابق This or that.html (با شاین، سرآستین، دو نوار مورب و نشان سینه)."""
    p = ensure_dark_bg_contrast(str(side.get("color") or "#E62E45"), bg="#0D1730", min_ratio=4.2)
    c2 = str(side.get("secondary") or "#FFFFFF")
    num = esc(str(side.get("num") or "10")[:3])
    jp = "M74 28C84 40 136 40 146 28L178 44L204 92L170 112L158 92V194C158 199 154 202 149 202H71C66 202 62 199 62 194V92L50 112L16 92L42 44L74 28Z"
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 220 220" fill="none" style="filter:drop-shadow(0 18px 28px rgba(0,0,0,.6));display:block">'
        f'<defs>'
        f'<linearGradient id="b_{uid}" x1="30" y1="20" x2="190" y2="205" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{p}"/><stop offset="1" stop-color="{p}" stop-opacity=".72"/></linearGradient>'
        f'<linearGradient id="s_{uid}" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="#fff" stop-opacity=".28"/><stop offset=".45" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".34"/></linearGradient>'
        f'<clipPath id="c_{uid}"><path d="{jp}"/></clipPath></defs>'
        f'<g clip-path="url(#c_{uid})"><path d="{jp}" fill="url(#b_{uid})"/>'
        f'<path d="M35 160L195 35V62L35 187Z" fill="{c2}" fill-opacity=".16"/>'
        f'<path d="M35 198L195 73V88L35 213Z" fill="{c2}" fill-opacity=".10"/>'
        f'<rect x="62" y="186" width="96" height="16" fill="{c2}" fill-opacity=".26"/>'
        f'<path d="M16 86L52 106L47 115L11 95ZM204 86L168 106L173 115L209 95Z" fill="{c2}" fill-opacity=".82"/>'
        f'<rect width="220" height="220" fill="url(#s_{uid})"/></g>'
        f'<path d="{jp}" stroke="{c2}" stroke-opacity=".65" stroke-width="3.2" stroke-linejoin="round"/>'
        f'<path d="M76 28C87 46 133 46 144 28" stroke="{c2}" stroke-width="5.5" stroke-linecap="round"/>'
        f'<circle cx="136" cy="70" r="8" fill="{c2}" fill-opacity=".88"/>'
        f'<text x="110" y="148" text-anchor="middle" fill="{_ctr(p)}" font-family="Space Grotesk,JetBrains Mono,sans-serif" font-weight="800" font-size="66" letter-spacing="-2">{num}</text></svg>'
    )


def _crest_svg(side: dict[str, Any], uid: str, size: int) -> str:
    """سپر باشگاهی SVG دقیقاً مطابق This or that.html (با گرادینت متالیک دور سپر، نور بالا و نقطه پایین)."""
    p = ensure_dark_bg_contrast(str(side.get("color") or "#E62E45"), bg="#0D1730", min_ratio=4.2)
    c2 = str(side.get("secondary") or "#FFFFFF")
    cd = esc(str(side.get("code") or "XGP")[:4].upper())
    cp = "M90 16L150 40V88C150 128 124.5 156.5 90 166C55.5 156.5 30 128 30 88V40Z"
    box_fill = "#0D1730" if _lum(p) > 0.65 else "#070d1da8"
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 180 180" fill="none" style="filter:drop-shadow(0 16px 26px rgba(0,0,0,.6));display:block">'
        f'<defs><linearGradient id="g_{uid}" x1="20" y1="15" x2="160" y2="165" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{c2}" stop-opacity=".95"/><stop offset=".5" stop-color="{p}" stop-opacity=".92"/><stop offset="1" stop-color="{c2}" stop-opacity=".75"/></linearGradient>'
        f'<clipPath id="cc_{uid}"><path d="{cp}"/></clipPath></defs>'
        f'<path d="M90 12L154 38V88C154 130.5 127 160.5 90 170.5C53 160.5 26 130.5 26 88V38Z" fill="{p}" fill-opacity=".22"/>'
        f'<g clip-path="url(#cc_{uid})"><rect x="25" y="12" width="130" height="158" fill="{p}"/>'
        f'<path d="M25 112L155 56V84L25 140Z" fill="{c2}" fill-opacity=".28"/>'
        f'<path d="M90 16L150 40V58L90 34L30 58V40Z" fill="{c2}" fill-opacity=".90"/>'
        f'<ellipse cx="90" cy="30" rx="65" ry="28" fill="#fff" fill-opacity=".16"/></g>'
        f'<path d="{cp}" stroke="url(#g_{uid})" stroke-width="5"/>'
        f'<rect x="38" y="68" width="104" height="48" rx="14" fill="{box_fill}" stroke="{c2}" stroke-opacity=".55" stroke-width="2"/>'
        f'<text x="90" y="101" text-anchor="middle" fill="#FFFFFF" font-family="Space Grotesk,JetBrains Mono,Vazirmatn,sans-serif" font-weight="800" font-size="{26 if len(cd) > 3 else 31}" letter-spacing="1.5">{cd}</text>'
        f'<circle cx="90" cy="136" r="5" fill="{_ctr(p)}" fill-opacity=".85"/></svg>'
    )


def _side_visual(side: dict[str, Any], uid: str, size: int) -> str:
    if side.get("art") == "photo" and str(side.get("photo") or "").startswith("data:image/"):
        col = ensure_dark_bg_contrast(str(side.get("color") or "#E62E45"), bg="#0D1730", min_ratio=4.2)
        return (
            f'<div style="position:relative;width:{size}px;height:{size}px;border-radius:28px;overflow:hidden;border:2px solid {col}99;box-shadow:0 18px 36px rgba(0,0,0,.6),0 0 32px {col}40">'
            f'<img src="{side["photo"]}" alt="" style="width:100%;height:100%;object-fit:cover;object-position:50% 18%;display:block">'
            f'<div class="ov" style="background:linear-gradient(to top,{col}55,transparent 45%)"></div></div>'
        )
    return _crest_svg(side, uid, size) if side.get("art") == "crest" else _jersey_svg(side, uid, size)


def _tags_html(side: dict[str, Any], show: bool, compact: bool) -> str:
    if not show or not side.get("tags"):
        return ""
    col = ensure_dark_bg_contrast(str(side.get("color") or "#E62E45"), bg="#0D1730", min_ratio=4.2)
    pills = "".join(
        f'<span class="tt-tag {"tt-tag-sm" if compact else ""}" style="background:{col}22;border-color:{col}66">{esc(fa(t))}</span>'
        for t in (side.get("tags") or [])[:3]
    )
    return f'<div class="tt-tags">{pills}</div>'


def _pick_badge(pick: str, k: str) -> str:
    if pick != k:
        return ""
    pos = "left:16px" if k == "a" else "right:16px"
    return (
        f'<div class="tt-pick-badge" style="{pos}">'
        f'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'
        f'<span>انتخاب من</span></div>'
    )


def _pick_cls(pick: str, k: str) -> str:
    if pick == k:
        return "pick-glow"
    return "pick-dim" if pick in ("a", "b") else ""


@with_sample_badge
def render_this_or_that_html(
    item: dict[str, Any],
    *,
    layout: str | None = None,
    fmt: str = "4:5",
    pick: str = "none",
    enabled_modules: list[str] | None = None,
) -> str:
    """تولید HTML کامل، ۱۰۰٪ آفلاین و ۱:۱ مطابق This or that.html برای هر ۴ موتور گرافیکی."""
    ly = layout if layout in ("diagonal", "split", "cards", "rapid") else str(item.get("layout") or TOT_DEFAULT_LAYOUT)
    w, h = TOT_FORMATS.get(fmt, TOT_FORMATS["4:5"])
    is_story = fmt == "9:16"
    is_wide = fmt == "16:9"
    pad_top, pad_bot = (139, 171) if is_story else ((22, 16) if is_wide else (24, 20))

    if enabled_modules is not None:
        mods = set(enabled_modules)
    else:
        mods = {m["id"] for m in get_tot_modules(item) if m["enabled"]}

    a = dict(item.get("a") or {})
    b = dict(item.get("b") or {})
    ca = ensure_dark_bg_contrast(str(a.get("color") or "#EF0107"), bg="#0D1730", min_ratio=4.2)
    cb = ensure_dark_bg_contrast(str(b.get("color") or "#38BDF8"), bg="#0D1730", min_ratio=4.2)
    a["color"], b["color"] = ca, cb

    compact = is_wide or ("stats" in mods and "poll" in mods)
    stats_list = item.get("stats") or []

    # ۱) نوار مقایسه شاخص‌های کلیدی
    stats_html = ""
    if "stats" in mods and stats_list and ly != "rapid":
        rows = "".join(
            f'<div class="tt-st-row"><div class="tt-st-top">'
            f'<span class="tt-st-num" style="color:{ca};font-size:{22 if compact else 26}px">{esc(fa(r.get("a", 85)))}</span>'
            f'<span class="tt-st-lbl" style="font-size:{17 if compact else 20}px">{esc(fa(r.get("l", "")))}</span>'
            f'<span class="tt-st-num tt-tl" style="color:{cb};font-size:{22 if compact else 26}px">{esc(fa(r.get("b", 85)))}</span></div>'
            f'<div class="tt-st-bars">'
            f'<div class="ct hs"><div class="ch" style="width:{int(r.get("a", 85))}%;background:{ca}"></div></div>'
            f'<div class="ct as"><div class="ca" style="width:{int(r.get("b", 85))}%;background:{cb}"></div></div>'
            f'</div></div>'
            for r in stats_list[:3]
        )
        stats_html = (
            f'<div class="xm tt-box {"tt-box-cp" if compact else ""}">'
            f'<div class="fbw tt-bh"><div class="fi tt-gap-10"><span class="tt-mbar"></span>'
            f'<span class="tt-bt" style="font-size:{21 if compact else 24}px">مقایسه شاخص‌های کلیدی</span></div>'
            f'<span dir="ltr" class="fm tt-ben">HEAD-TO-HEAD INDEX</span></div>'
            f'<div class="fcol {"tt-gap-8" if compact else "tt-gap-12"}">{rows}</div></div>'
        )

    # ۲) نوار درصد آرای مخاطبان
    poll_html = ""
    if "poll" in mods and ly != "rapid":
        pa = max(10, min(90, int(item.get("pollA") or 50)))
        pb = 100 - pa
        poll_html = (
            f'<div class="xm tt-box {"tt-box-cp" if compact else ""}">'
            f'<div class="fbw" style="margin-bottom:8px"><span class="fi tt-gap-8 tt-bt" style="font-size:19px"><span style="width:10px;height:10px;border-radius:999px;background:#34D399;display:inline-block"></span>رأی مخاطبان XGPedia</span>'
            f'<span dir="ltr" class="fm tt-ben">COMMUNITY SPLIT</span></div>'
            f'<div class="pc" style="height:{40 if compact else 46}px">'
            f'<div class="ps" style="width:{pa}%;background:{ca};color:{_ctr(ca)};font-size:{20 if compact else 23}px">{esc(str(a.get("code", "A")))} | {esc(fa(pa))}٪</div>'
            f'<div class="ps" style="width:{pb}%;background:{cb};color:{_ctr(cb)};font-size:{20 if compact else 23}px">{esc(fa(pb))}٪ | {esc(str(b.get("code", "B")))}</div>'
            f'</div></div>'
        )

    # ۳) کادر CTA با آیکون پیام اصلی یا استیکر استوری
    cta_html = ""
    cta_txt = esc(fa(item.get("cta") or "انتخاب تو کدومه؟ A یا B رو کامنت کن و دلیلت رو بنویس"))
    if is_story and "sticker" in mods:
        cta_html = (
            f'<div class="tt-sticker"><span class="tt-st-pill">محل قرارگیری استیکر نظرسنجی اینستاگرام (Poll Sticker)</span>'
            f'<span class="tt-cta-t">{cta_txt}</span></div>'
        )
    elif "cta" in mods:
        cta_html = (
            f'<div class="xe tt-cta {"tt-cta-cp" if compact else ""}">'
            f'<div class="fi tt-gap-12" style="min-width:0">'
            f'<span class="tt-cta-ico"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#FF7B8D" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg></span>'
            f'<span class="tt-cta-t" style="font-size:{19 if compact else 22}px">{cta_txt}</span></div>'
            f'<div class="fi tt-gap-8" dir="ltr" style="flex-shrink:0"><span class="fd tt-ab" style="background:{ca};color:{_ctr(ca)}">A</span>'
            f'<span style="color:#94A3B8;font-weight:900;font-size:16px">/</span>'
            f'<span class="fd tt-ab" style="background:{cb};color:{_ctr(cb)}">B</span></div></div>'
        )

    rail_html = (poll_html + cta_html) if ly == "cards" else (stats_html + poll_html + cta_html)

    # ۴ موتور گرافیکی ۱:۱
    if ly == "diagonal":
        vsz = 185 if is_wide else (230 if is_story else 205)

        def _dcol(s: dict[str, Any], k: str) -> str:
            lb = f'<span class="fd tt-opt-pill" style="background:{s["color"]};color:{_ctr(s["color"])}">{k.upper()}</span>'
            rt = f'<span class="fm tt-rat-pill">{esc(fa(s.get("rating", 92)))} XGP</span>'
            return (
                f'<div class="tt-dcol {_pick_cls(pick, k)}">{_pick_badge(pick, k)}'
                f'<div class="fi tt-gap-8" style="margin-bottom:12px">{lb + rt if k == "a" else rt + lb}</div>'
                f'<div style="margin:4px 0">{_side_visual(s, "d" + k, vsz)}</div>'
                f'<h2 class="tt-sname" style="font-size:{40 if is_wide else 46}px">{esc(fa(s.get("name", "")))}</h2>'
                f'<p class="tt-ssub" style="font-size:{18 if is_wide else 21}px">{esc(fa(s.get("sub", "")))}</p>'
                f'{_tags_html(s, "tags" in mods, is_wide)}</div>'
            )

        wm_a = esc(str(a.get("num") or a.get("code") or "A"))
        wm_b = esc(str(b.get("num") or b.get("code") or "B"))
        main_html = (
            f'<div class="tt-diag-arena">'
            f'<div class="ov diag-a" style="background:radial-gradient(circle at 78% 35%,{ca}42,transparent 62%),linear-gradient(150deg,{ca}22,#081024 72%)"></div>'
            f'<div class="ov diag-b" style="background:radial-gradient(circle at 22% 65%,{cb}42,transparent 62%),linear-gradient(330deg,{cb}22,#081024 72%)"></div>'
            f'<div class="fd tt-wm-a" style="color:{ca}">{wm_a}</div>'
            f'<div class="fd tt-wm-b" style="color:{cb}">{wm_b}</div>'
            f'<svg class="ov tt-svg-full" style="z-index:10" viewBox="0 0 1000 700" preserveAspectRatio="none">'
            f'<line x1="580" y1="0" x2="420" y2="700" stroke="#E62E45" stroke-width="5" stroke-opacity=".92"/>'
            f'<line x1="580" y1="0" x2="420" y2="700" stroke="#FF7B8D" stroke-width="14" stroke-opacity=".20"/>'
            f'<line x1="596" y1="0" x2="436" y2="700" stroke="#fff" stroke-width="1.2" stroke-opacity=".20" stroke-dasharray="10 10"/>'
            f'<line x1="564" y1="0" x2="404" y2="700" stroke="#fff" stroke-width="1.2" stroke-opacity=".20" stroke-dasharray="10 10"/></svg>'
            f'<div class="tt-2col">{_dcol(a, "a")}{_dcol(b, "b")}</div>'
            f'<div class="tt-or-center"><div class="tt-or-ring"></div><div class="tt-or-dia"></div>'
            f'<div class="tt-or-txt"><span class="tt-or-fa">یا</span><span class="fd tt-or-en">OR</span></div></div></div>'
        )
    elif ly == "split":
        vsz = 170 if is_wide else (215 if is_story else 190)

        def _scard(s: dict[str, Any], k: str) -> str:
            return (
                f'<div class="xm foil tt-scard {_pick_cls(pick, k)}" style="border-top:6px solid {s["color"]};background:radial-gradient(circle at 50% 18%,{s["color"]}30,transparent 62%),linear-gradient(165deg,#101d3be6,#080f22f7)">'
                f'{_pick_badge(pick, k)}'
                f'<div class="fbw"><span class="fd tt-opt-pill" style="background:{s["color"]};color:{_ctr(s["color"])}">{k.upper()}</span>'
                f'<span class="fm tt-code-s">{esc(str(s.get("code", "")))} #{esc(str(s.get("num", "")))}</span>'
                f'<span class="fm tt-rat-pill">{esc(fa(s.get("rating", 92)))}</span></div>'
                f'<div class="fcol tt-ai-center tt-my-auto" style="padding:10px 0">{_side_visual(s, "s" + k, vsz)}'
                f'<h2 class="tt-sname" style="font-size:{36 if is_wide else 42}px">{esc(fa(s.get("name", "")))}</h2>'
                f'<p class="tt-ssub" style="font-size:{18 if is_wide else 20}px">{esc(fa(s.get("sub", "")))}</p>{_tags_html(s, "tags" in mods, True)}</div>'
                f'<div class="tt-sfoot"><span>شاخص XGPedia</span><span style="color:{s["color"]};font-size:22px;font-weight:900">{esc(fa(s.get("rating", 92)))} / ۱۰۰</span></div></div>'
            )

        main_html = (
            f'<div class="tt-split-wrap">{_scard(a, "a")}{_scard(b, "b")}'
            f'<div class="tt-or-center"><div class="tt-or-circ"><span style="font-size:28px;font-weight:900">یا</span><span class="fm" style="font-size:11px;color:#FF7B8D">OR</span></div></div></div>'
        )
    elif ly == "cards":
        vsz = 165 if is_wide else (210 if is_story else 185)

        def _fcard(s: dict[str, Any], k: str, rot: float) -> str:
            mini_st = "".join(
                f'<div class="tt-fc-st"><div style="color:{s["color"]};font-size:24px;font-weight:900;line-height:1">{esc(fa(r.get(k, 90)))}</div>'
                f'<div class="tt-fc-sl">{esc(fa(str(r.get("l", "")).split()[0]))}</div></div>'
                for r in stats_list[:3]
            )
            return (
                f'<div class="foil tt-fcard-out {_pick_cls(pick, k)}" style="transform:rotate({rot}deg);background:linear-gradient(145deg,{s["color"]},#ffffff40 48%,{s.get("secondary") or s["color"]});box-shadow:0 26px 60px -14px rgba(0,0,0,.86),0 0 40px {s["color"]}38">'
                f'<div class="tt-fcard-in" style="background:radial-gradient(circle at 50% 24%,{s["color"]}38,transparent 60%),#091228">'
                f'{_pick_badge(pick, k)}'
                f'<div class="fbw" style="align-items:flex-start"><div class="tt-fc-rat"><span class="fd" style="font-size:38px;font-weight:900;color:{s["color"]};line-height:1">{esc(fa(s.get("rating", 92)))}</span>'
                f'<span class="fm" style="font-size:13px;color:#CBD5E1;margin-top:2px">{esc(str(s.get("code", "")))}</span></div>'
                f'<div class="fcol" style="align-items:flex-end"><span class="fd tt-opt-pill" style="background:{s["color"]};color:{_ctr(s["color"])}">OPTION {k.upper()}</span>'
                f'<span class="fm" style="font-size:15px;font-weight:700;color:#94A3B8;margin-top:4px">#{esc(str(s.get("num", "")))}</span></div></div>'
                f'<div class="fcol tt-ai-center tt-my-auto">{_side_visual(s, "f" + k, vsz)}'
                f'<h2 class="tt-sname" style="font-size:{34 if is_wide else 40}px">{esc(fa(s.get("name", "")))}</h2>'
                f'<p class="tt-ssub" style="font-size:18px">{esc(fa(s.get("sub", "")))}</p></div>'
                f'<div class="tt-fc-grid">{mini_st}</div></div></div>'
            )

        main_html = (
            f'<div class="tt-cards-wrap"><div class="tt-cards-grid">{_fcard(a, "a", 1.6)}{_fcard(b, "b", -1.6)}</div>'
            f'<div class="tt-or-center"><div class="tt-cards-pill"><span style="font-size:30px;font-weight:900">این یا اون؟</span>'
            f'<span class="fm" style="font-size:12px;letter-spacing:.22em;margin-top:3px">THIS OR THAT</span></div></div></div>'
        )
    else:  # rapid 5 rounds
        rds = item.get("rounds") or _DEFAULT_ROUNDS
        r_html = "".join(
            f'<div class="xm tt-rrow"><div class="fbw"><div class="fi tt-gap-8">'
            f'<span class="fm tt-ridx">{esc(fa(f"0{i}"))}</span>'
            f'<span class="tt-rcat" style="font-size:{17 if is_wide else 20}px">{esc(fa(r.get("cat", "")))}</span></div>'
            f'<span dir="ltr" class="fm" style="font-size:14px;font-weight:700;color:#94A3B8">ROUND {i}</span></div>'
            f'<div class="fi tt-gap-12">'
            f'<div class="tt-rhalf" style="background:{r.get("cA", "#E62E45")}18;border-color:{r.get("cA", "#E62E45")}66"><div class="fi tt-gap-10" style="min-width:0"><span class="fd tt-ab" style="background:{r.get("cA", "#E62E45")};color:{_ctr(r.get("cA", "#E62E45"))}">A</span><span class="tt-rtxt" style="font-size:{22 if is_wide else (28 if is_story else 26)}px">{esc(fa(r.get("a", "")))}</span></div><span class="tt-rchk"></span></div>'
            f'<span class="tt-rya">یا</span>'
            f'<div class="tt-rhalf" style="background:{r.get("cB", "#38BDF8")}18;border-color:{r.get("cB", "#38BDF8")}66"><div class="fi tt-gap-10" style="min-width:0"><span class="fd tt-ab" style="background:{r.get("cB", "#38BDF8")};color:{_ctr(r.get("cB", "#38BDF8"))}">B</span><span class="tt-rtxt" style="font-size:{22 if is_wide else (28 if is_story else 26)}px">{esc(fa(r.get("b", "")))}</span></div><span class="tt-rchk"></span></div>'
            f'</div></div>'
            for i, r in enumerate(rds[:5], 1)
        )
        main_html = f'<div class="fcol tt-flex-1 tt-jc-center {"tt-gap-8" if is_wide else "tt-gap-12"}">{r_html}</div>'
        rail_html = cta_html

    if is_wide and rail_html and ly != "rapid":
        cols = "8fr 4fr" if ly == "cards" else "7fr 5fr"
        stage_body = f'<div class="tt-wide-grid" style="grid-template-columns:{cols}"><div class="tt-w-main">{main_html}</div><div class="tt-w-rail">{rail_html}</div></div>'
    else:
        stage_body = main_html + rail_html

    cy_bg = round(h * 0.45)
    crh_d = (
        f"M24 44V24H44M{w - 24} 44V24H{w - 44}"
        f"M24 {h - 44}V{h - 24}H44M{w - 24} {h - 44}V{h - 24}H{w - 44}"
    )

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<title>{esc(fa(item.get("label", "XGPedia This or That")))}</title>
<style>
{build_embedded_font_css()}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{w}px;height:{h}px;overflow:hidden;background:#0D1730;color:#F8FAFC;
  font-family:'Vazirmatn',system-ui,sans-serif;font-feature-settings:"tnum";font-variant-numeric:tabular-nums}}
.fm{{font-family:'JetBrains Mono','Space Grotesk',monospace}}.fd{{font-family:'Space Grotesk','Vazirmatn',sans-serif}}
.fi{{display:flex;align-items:center}}.fc{{display:flex;align-items:center;justify-content:center}}
.fbw{{display:flex;align-items:center;justify-content:space-between}}.fcol{{display:flex;flex-direction:column}}
.ov{{position:absolute;inset:0;pointer-events:none}}.tt-svg-full{{width:100%;height:100%}}
.tt-flex-1{{flex:1}}.tt-my-auto{{margin:auto 0}}.tt-ai-center{{align-items:center}}.tt-jc-center{{justify-content:center}}
.tt-gap-8{{gap:8px}}.tt-gap-10{{gap:10px}}.tt-gap-12{{gap:12px}}.tt-tl{{text-align:left}}

.tt-canvas{{position:relative;width:{w}px;height:{h}px;overflow:hidden;background:#0D1730;
  display:flex;flex-direction:column;justify-content:space-between;padding:{pad_top}px 0 {pad_bot}px}}
.tt-ambient{{background:radial-gradient(circle at 84% 34%,{ca}38,transparent 50%),radial-gradient(circle at 16% 62%,{cb}38,transparent 50%),radial-gradient(circle at 50% 44%,#e62e4526,transparent 54%)}}
.tt-scanlines{{background:repeating-linear-gradient(to bottom,#ffffff04 0 1px,#0000 1px 4px)}}
.tt-halftone{{background-image:radial-gradient(#f8fafc12 1px,transparent 1px);background-size:18px 18px}}
.xm,.xe{{position:relative;border-radius:24px;box-shadow:0 16px 38px -10px rgba(0,0,0,.58),inset 0 1px 0 rgba(255,255,255,.10);overflow:hidden}}
.xm{{background:linear-gradient(165deg,#101d3be0,#091023f5);border:1.5px solid #f8fafc24}}
.xe{{background:linear-gradient(155deg,#121f3deb,#090f20f7);border:1.5px solid #e62e4555}}
.foil{{position:relative;overflow:hidden}}
{'' if 'foil' not in mods else '.foil::after{content:"";position:absolute;inset:-40%;background:linear-gradient(115deg,transparent 36%,#ffffff17 46%,#ffffff2e 50%,#ffffff0f 54%,transparent 64%);pointer-events:none}'}

.tt-header{{position:relative;z-index:10;padding:12px 36px 8px;display:flex;align-items:center;justify-content:space-between;gap:14px;flex-shrink:0}}
.tt-cat-pill{{padding:5px 16px;border-radius:999px;font-size:21px;font-weight:900;background:#152347e6;border:1px solid #ffffff2e;display:inline-flex;align-items:center;gap:10px}}
.tt-ed-pill{{padding:5px 16px;border-radius:999px;font-size:19px;font-weight:800;background:#e62e452e;border:1px solid #e62e4580;color:#FF7B8D}}
.tt-q{{font-size:{30 if is_wide else 34}px;font-weight:900;color:#FFFFFF;line-height:1.18;margin-top:6px}}
.tt-dot{{width:12px;height:12px;border-radius:999px;background:#E62E45;box-shadow:0 0 12px #E62E45;flex-shrink:0}}
.tt-brand{{display:flex;align-items:center;flex-shrink:0}}.tt-brand-img{{height:48px;width:auto;display:block}}.tt-brand-txt{{font-size:34px;font-weight:800}}

.tt-stage{{position:relative;z-index:10;flex:1;padding:8px 40px;display:flex;flex-direction:column;justify-content:space-between;gap:15px;min-height:0;overflow:hidden}}
.tt-wide-grid{{flex:1;display:grid;gap:20px;min-height:0}}
.tt-w-main{{display:flex;flex-direction:column;min-height:0}}.tt-w-rail{{display:flex;flex-direction:column;justify-content:space-between;gap:12px;min-height:0}}

.tt-diag-arena{{position:relative;flex:1;min-height:0;border-radius:28px;overflow:hidden;border:1.5px solid rgba(255,255,255,.18);background:#081024;box-shadow:0 24px 56px rgba(0,0,0,.62)}}
.diag-a{{clip-path:polygon(100% 0,100% 100%,42% 100%,58% 0)}}.diag-b{{clip-path:polygon(0 0,58% 0,42% 100%,0 100%)}}
.tt-wm-a{{position:absolute;right:30px;top:12px;font-weight:900;font-size:220px;line-height:1;opacity:.06;pointer-events:none}}
.tt-wm-b{{position:absolute;left:30px;bottom:6px;font-weight:900;font-size:220px;line-height:1;opacity:.06;pointer-events:none}}
.tt-2col{{position:relative;z-index:10;width:100%;height:100%;display:grid;grid-template-columns:1fr 1fr}}
.tt-dcol{{position:relative;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:24px 30px}}
.tt-opt-pill{{padding:4px 14px;border-radius:12px;font-size:20px;font-weight:900}}
.tt-rat-pill{{padding:4px 14px;border-radius:12px;background:rgba(0,0,0,.45);border:1px solid rgba(255,255,255,.16);font-size:18px;font-weight:800;color:#E2E8F0}}
.tt-sname{{font-weight:900;color:#FFFFFF;line-height:1.08;margin-top:12px;text-shadow:0 8px 22px rgba(0,0,0,.65)}}
.tt-ssub{{font-weight:700;color:#E2E8F0;margin-top:6px;max-width:380px}}
.tt-tags{{display:flex;flex-wrap:wrap;justify-content:center;gap:8px;margin-top:12px}}
.tt-tag{{padding:6px 14px;border-radius:999px;border:1px solid;font-size:18px;font-weight:800;color:#F8FAFC;white-space:nowrap}}
.tt-tag-sm{{padding:4px 12px;font-size:16px}}

.tt-or-center{{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);z-index:20;display:flex;align-items:center;justify-content:center;pointer-events:none}}
.tt-or-ring{{position:absolute;width:144px;height:144px;border-radius:999px;border:1.5px dashed rgba(230,46,69,.55)}}
.tt-or-dia{{width:104px;height:104px;border-radius:26px;transform:rotate(45deg);background:linear-gradient(135deg,#E62E45,#A8162B);border:2px solid rgba(255,255,255,.42);box-shadow:0 0 50px rgba(230,46,69,.75)}}
.tt-or-txt{{position:absolute;display:flex;flex-direction:column;align-items:center;line-height:1}}
.tt-or-fa{{font-size:36px;font-weight:900;color:#FFFFFF}}.tt-or-en{{font-size:14px;font-weight:800;letter-spacing:.20em;color:rgba(255,255,255,.88);margin-top:2px}}

.tt-split-wrap{{position:relative;flex:1;min-height:0;display:grid;grid-template-columns:1fr 1fr;gap:20px}}
.tt-scard{{padding:22px;display:flex;flex-direction:column;justify-content:space-between;text-align:center}}
.tt-code-s{{font-size:18px;font-weight:800;color:#CBD5E1}}
.tt-sfoot{{padding-top:12px;border-top:1px solid rgba(255,255,255,.12);display:flex;align-items:center;justify-content:space-between;font-size:16px;font-weight:800;color:#CBD5E1}}
.tt-or-circ{{width:82px;height:82px;border-radius:999px;background:#070D1D;border:3px solid #E62E45;box-shadow:0 0 32px rgba(230,46,69,.65);display:flex;flex-direction:column;align-items:center;justify-content:center;line-height:1}}

.tt-cards-wrap{{position:relative;flex:1;min-height:0;display:flex;align-items:center;justify-content:center;padding:12px}}
.tt-cards-grid{{width:100%;height:100%;display:grid;grid-template-columns:1fr 1fr;gap:30px;align-items:stretch}}
.tt-fcard-out{{border-radius:30px;padding:6px;display:flex;flex-direction:column}}
.tt-fcard-in{{position:relative;flex:1;border-radius:25px;padding:20px;display:flex;flex-direction:column;justify-content:space-between;text-align:center;overflow:hidden}}
.tt-fc-rat{{display:flex;flex-direction:column;align-items:center;padding:8px 14px;border-radius:16px;background:rgba(0,0,0,.45);border:1px solid rgba(255,255,255,.15)}}
.tt-fc-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;padding-top:12px;border-top:1px solid rgba(255,255,255,.14)}}
.tt-fc-st{{border-radius:12px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.10);padding:8px 4px;text-align:center}}
.tt-fc-sl{{font-size:13px;font-weight:700;color:#CBD5E1;margin-top:3px}}
.tt-cards-pill{{padding:12px 24px;border-radius:16px;background:#E62E45;border:2px solid rgba(255,255,255,.42);box-shadow:0 0 45px rgba(230,46,69,.85);display:flex;flex-direction:column;align-items:center;line-height:1}}

.tt-rrow{{padding:12px 20px;display:flex;flex-direction:column;gap:8px}}
.tt-ridx{{padding:2px 10px;border-radius:8px;background:#e62e452e;border:1px solid #e62e4566;color:#FF7B8D;font-size:15px;font-weight:800}}
.tt-rcat{{font-weight:800;color:#E2E8F0}}
.tt-rhalf{{flex:1;border-radius:16px;padding:13px 18px;border:2px solid;display:flex;align-items:center;justify-content:space-between;gap:12px;min-width:0}}
.tt-rtxt{{font-weight:900;color:#FFFFFF;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.tt-rchk{{width:30px;height:30px;border-radius:999px;border:2px solid rgba(255,255,255,.25);flex-shrink:0}}
.tt-rya{{width:44px;height:44px;border-radius:12px;background:#070D1D;border:1px solid rgba(255,255,255,.20);display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:900;color:#FF6B7F;flex-shrink:0}}

.tt-box{{padding:16px 24px;flex-shrink:0}}.tt-box-cp{{padding:12px 18px}}
.tt-bh{{padding-bottom:10px;margin-bottom:12px;border-bottom:1px solid rgba(255,255,255,.12)}}
.tt-mbar{{width:8px;height:24px;border-radius:99px;background:#E62E45}}.tt-bt{{font-weight:900;color:#FFFFFF}}
.tt-ben{{font-size:16px;font-weight:800;color:#94A3B8}}
.tt-st-row{{display:flex;flex-direction:column;gap:6px}}
.tt-st-top{{display:grid;grid-template-columns:1fr 2fr 1fr;align-items:center}}
.tt-st-num{{font-weight:900;line-height:1}}.tt-st-lbl{{text-align:center;font-weight:800;color:#F1F5F9}}
.tt-st-bars{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
.ct{{height:13px;background:#ffffff1a;overflow:hidden;display:flex;align-items:center}}
.ct.hs,.ch{{border-radius:0 99px 99px 0}}.ct.as,.ca{{border-radius:99px 0 0 99px}}.ct.hs{{justify-content:flex-end}}.ct.as{{justify-content:flex-start}}.ch,.ca{{height:100%}}

.pc{{width:100%;border-radius:999px;overflow:hidden;display:flex;background:#0f172aeb;border:2px solid #ffffff2e;box-shadow:inset 0 2px 8px rgba(0,0,0,.45)}}
.ps{{height:100%;display:flex;align-items:center;justify-content:center;font-weight:900;white-space:nowrap}}

.tt-cta{{padding:14px 24px;display:flex;align-items:center;justify-content:space-between;gap:14px;flex-shrink:0}}.tt-cta-cp{{padding:10px 18px}}
.tt-cta-ico{{width:40px;height:40px;border-radius:12px;background:#e62e4538;border:1px solid #e62e4590;display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.tt-cta-t{{font-weight:900;color:#F1F5F9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.tt-ab{{padding:4px 14px;border-radius:12px;font-size:18px;font-weight:900}}
.tt-sticker{{border-radius:24px;border:2px dashed rgba(255,107,127,.60);background:rgba(9,18,38,.76);padding:18px 24px;display:flex;flex-direction:column;align-items:center;gap:8px;flex-shrink:0}}
.tt-st-pill{{padding:4px 16px;border-radius:999px;background:#e62e4538;border:1px solid #e62e4580;color:#FF8A9A;font-size:18px;font-weight:900}}

.pick-glow{{box-shadow:0 0 0 3px #10B981,0 0 36px rgba(16,185,129,.45)}}.pick-dim{{opacity:.52;filter:saturate(.65)}}
.tt-pick-badge{{position:absolute;top:16px;z-index:20;padding:6px 16px;border-radius:999px;background:#10B981;color:#03130E;font-size:18px;font-weight:900;display:flex;align-items:center;gap:6px;box-shadow:0 0 24px rgba(16,185,129,.65)}}

.tt-footer{{position:relative;z-index:10;padding:10px 44px 10px;flex-shrink:0}}
.tt-footer-line{{border-top:1px solid rgba(255,255,255,.14);margin-bottom:8px}}
.tt-foot-tag{{font-size:17.5px;font-weight:800;letter-spacing:.14em;color:#E2E8F0}}
.tt-foot-handle{{font-size:20px;font-weight:800;color:#FFFFFF}}.tt-foot-end{{font-size:17px;font-weight:800;color:#FF7B8D}}

footer, footer .fbw, footer .cf-row, footer .fi, footer .cf-left, footer .cf-right, .xg-footer, .foot-row, .card-footer{{flex-wrap:nowrap!important;white-space:nowrap!important;min-width:0!important;}}
footer span, footer div, .pl-foot-tag, .pl-foot-s, .in-foot-tag, .pr-foot-tag, .st-foot-tag, .cf-tag{{white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;min-width:0!important;}}
</style>
</head>
<body>
<div class="tt-canvas" dir="rtl">
  <div class="ov tt-ambient"></div>
  <div class="ov tt-halftone"></div>
  <svg class="ov tt-svg-full" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid slice" fill="none">
    <defs>
      <pattern id="tg" width="54" height="54" patternUnits="userSpaceOnUse"><path d="M54 0H0v54" stroke="#F8FAFC" stroke-opacity=".05"/></pattern>
      <radialGradient id="rf" cx="50%" cy="42%" r="46%">
        <stop offset="0" stop-color="#E62E45" stop-opacity=".24"/><stop offset=".55" stop-color="#E62E45" stop-opacity=".06"/><stop offset="1" stop-color="#E62E45" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect width="100%" height="100%" fill="url(#tg)"/>
    <rect x="12" y="12" width="{w - 24}" height="{h - 24}" rx="18" stroke="#F8FAFC" stroke-opacity=".11" stroke-width="1.5"/>
    <g stroke="#F8FAFC" stroke-opacity=".08" stroke-width="1.5">
      <line x1="{w // 2}" y1="12" x2="{w // 2}" y2="{h - 12}" stroke-dasharray="8 8"/>
      <circle cx="{w // 2}" cy="{cy_bg}" r="165"/>
      <circle cx="{w // 2}" cy="{cy_bg}" r="280" stroke-opacity=".05"/>
    </g>
    <circle cx="{w // 2}" cy="{cy_bg}" r="240" fill="url(#rf)"/>
    <circle cx="{w // 2}" cy="{cy_bg}" r="205" stroke="#E62E45" stroke-opacity=".20" stroke-width="1.3" stroke-dasharray="5 7"/>
    <path d="{crh_d}" stroke="#E62E45" stroke-opacity=".65" stroke-width="2.4"/>
  </svg>
  <div class="ov tt-scanlines"></div>
  <header class="tt-header">
    <div class="fcol" style="min-width:0">
      <div class="fi tt-gap-10">
        <div class="tt-cat-pill"><span class="tt-dot"></span><span>{esc(fa(item.get("category", "این یا اون؟")))}</span></div>
        <span dir="ltr" class="fm tt-ed-pill">{esc(str(item.get("edition", "TOT // #01")))}</span>
      </div>
      <h1 class="tt-q">{esc(fa(item.get("question", "انتخاب تو کدام است؟")))}</h1>
    </div>
    {_brand_logo_html()}
  </header>
  <main class="tt-stage">{stage_body}</main>
  <footer class="tt-footer">
    <div class="tt-footer-line"></div>
    <div class="fbw tt-gap-12">
      <div class="fi tt-gap-10"><span class="tt-dot"></span><span dir="ltr" class="fm tt-foot-tag">{esc(str(item.get("footer", "XGPEDIA THIS OR THAT")).upper())}</span></div>
      <div class="fi tt-gap-10 fm" dir="ltr">
        <span class="tt-foot-handle">@XGPedia</span><span style="color:#64748B">|</span><span class="tt-foot-end">THIS OR THAT</span>
      </div>
    </div>
  </footer>
</div>
</body>
</html>"""


def build_this_or_that_caption(item: dict[str, Any]) -> str:
    """تولید کپشن فارسی جدال‌انگیز و آمادهٔ کامنت‌گیری برای کارت این یا اون."""
    a = item.get("a") or {}
    b = item.get("b") or {}
    q = fa(str(item.get("question") or "").strip())
    cta = fa(str(item.get("cta") or "انتخاب تو کدومه؟ A یا B رو کامنت کن!").strip())
    parts: list[str] = []
    if q:
        parts.append(f"❓ {q}")
    if a.get("name") and b.get("name") and item.get("layout") != "rapid":
        parts.append(
            f"🅰️ {fa(a['name'])} — {fa(a.get('sub', ''))}\n"
            f"🅱️ {fa(b['name'])} — {fa(b.get('sub', ''))}"
        )
    parts.append(f"💬 {cta}")
    return "\n\n".join(parts)
