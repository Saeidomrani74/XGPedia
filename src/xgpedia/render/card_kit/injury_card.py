"""کارت ماژولار «آزمایشگاه مصدومیت» (XGPedia Injury Lab — D53) — بازسازی ۱:۱ آفلاین.

ویژگی‌های ۱:۱ حفظ‌شده از `studio_templates/injury_lab.html` + استاندارد ماژولار کامل XGPedia:
  - پس‌زمینه پزشکی اختصاصی با شبکه صلیب‌های قرمز، خط نوار قلب (ECG)، حلقه‌های رادار و فریم چهارگوشهٔ استاندارد
  - هدر کامل بازیکن (پرتره یا آواتار پیراهن برداری + سپر باشگاهی + نشان وضعیت `out`/`long`/`doubt`/`fit` + خط ECG + ۳ باکس ETA/بازگشت/شانس بازی بعد) یا هدر فشرده
  - ۷ ماژول کاملاً مستقل و قابل چینش با پشتیبانی نیم‌عرض (`½`) و تمام‌عرض (`۱`)، تغییر ترتیب و ۵ قالب نام‌گذاری‌شده:
    1. `anatomical`: اسکنر آناتومی بدن (۷ ناحیه: همسترینگ، زانو/ACL، مچ پا، کشاله، ساق/آشیل، شانه، سر) + مکانیسم آسیب
    2. `missed`: بازی‌های حساس پیش‌رو با نوار سختی ۵تایی و وضعیت غیبت
    3. `timeline`: نقشه راه ۵ مرحله‌ای ریکاوری (تشخیص و MRI ← بازگشت به زمین)
    4. `impact`: شوک آماری غیبت (نوارهای مقایسه‌ای با / بدون بازیکن)
    5. `replacements`: گزینه‌های جایگزین تاکتیکی با درصد تطابق
    6. `history`: سابقه مصدومیت ۳ فصل اخیر (نمودار ستونی روزهای دوری + ریسک عود)
    7. `verdict`: جمع‌بندی تحریریه XGPedia با واترمارک زمین
"""
from __future__ import annotations

from typing import Any

from src.xgpedia.render.card_kit.helpers import contrast_ink, esc, fa, luminance
from src.xgpedia.render.cards import _brand_logo_data_uri
from src.xgpedia.render.studio_engine import build_embedded_font_css

INJURY_DEFAULT_SLIDE = "slide1"
INJURY_DEFAULT_HEADER = "full"

INJURY_FORMATS: dict[str, tuple[int, int]] = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}

INJURY_ZONES: dict[str, dict[str, Any]] = {
    "head": {"x": 110, "y": 34, "lx": 176, "ly": 34, "fa": "سر / ضربه مغزی"},
    "shoulder": {"x": 78, "y": 92, "lx": 178, "ly": 84, "fa": "مفصل شانه راست"},
    "groin": {"x": 102, "y": 178, "lx": 178, "ly": 166, "fa": "عضله کشاله ران"},
    "hamstring": {"x": 93, "y": 214, "lx": 178, "ly": 206, "fa": "همسترینگ پای راست"},
    "acl": {"x": 94, "y": 248, "lx": 178, "ly": 244, "fa": "رباط صلیبی زانو"},
    "calf": {"x": 93, "y": 286, "lx": 178, "ly": 282, "fa": "ساق پا / تاندون آشیل"},
    "ankle": {"x": 93, "y": 316, "lx": 178, "ly": 312, "fa": "رباط مچ پای راست"},
}

INJURY_SEVERITIES: dict[str, dict[str, str]] = {
    "out": {"fa": "غیبت قطعی", "en": "RULED OUT", "color": "#F43F5E", "bg": "rgba(244,63,94,.16)", "bd": "rgba(244,63,94,.48)", "tx": "#FF8A9A"},
    "long": {"fa": "مصدومیت سنگین", "en": "LONG-TERM OUT", "color": "#EF4444", "bg": "rgba(239,68,68,.18)", "bd": "rgba(239,68,68,.52)", "tx": "#FCA5A5"},
    "doubt": {"fa": "مشکوک به بازی", "en": "50/50 DOUBTFUL", "color": "#F59E0B", "bg": "rgba(245,158,11,.16)", "bd": "rgba(251,191,36,.48)", "tx": "#FDE68A"},
    "fit": {"fa": "در آستانه بازگشت", "en": "BACK IN TRAINING", "color": "#10B981", "bg": "rgba(16,185,129,.16)", "bd": "rgba(52,211,153,.48)", "tx": "#6EE7B7"},
}

# (id, label_fa, header_mode, default_mods)
INJURY_SLIDES: list[tuple[str, str, str, list[str]]] = [
    ("slide1", "اسلاید ۱: خبر فوری و اسکن آناتومی (پیشنهادی)", "full", ["anatomical", "missed", "timeline"]),
    ("slide2", "اسلاید ۲: نقشه ریکاوری و شوک آماری", "compact", ["timeline", "impact"]),
    ("slide3", "اسلاید ۳: جایگزین‌ها و تحلیل تحریریه", "compact", ["replacements", "verdict"]),
    ("slide4", "اسلاید ۴: پرونده کامل پزشکی (خروجی جامع)", "full", ["anatomical", "missed", "impact", "history", "verdict"]),
]


def get_injury_modules(
    item: dict[str, Any], slide: str = INJURY_DEFAULT_SLIDE
) -> tuple[list[dict[str, Any]], list[str]]:
    """استخراج ۷ ماژول مستقل آزمایشگاه مصدومیت بر اساس دیتای واقعی (قانون null ≠ 0)."""
    inj = item.get("injury") or {}
    has_anat = bool(inj.get("zone") or inj.get("mechanism") or inj.get("diagnosis"))
    has_missed = bool(isinstance(item.get("fixtures"), list) and len(item["fixtures"]) > 0)
    has_timeline = inj.get("stage") is not None
    imp = item.get("impact") if isinstance(item.get("impact"), dict) else None
    has_impact = bool(imp and imp.get("rows"))
    has_reps = bool(isinstance(item.get("replacements"), list) and len(item["replacements"]) > 0)
    hist = item.get("history") if isinstance(item.get("history"), dict) else None
    has_hist = bool(hist and hist.get("seasons"))
    verd = item.get("verdict") if isinstance(item.get("verdict"), dict) else None
    has_verd = bool(verd and verd.get("body"))

    def_set = set(next((mids for sid, _, _, mids in INJURY_SLIDES if sid == slide), ["anatomical", "missed", "timeline"]))
    specs = [
        ("anatomical", "اسکنر آناتومی و تشخیص پزشکی", has_anat, True, "half"),
        ("missed", "بازی‌های حساس از دست‌رفته", has_missed, True, "half"),
        ("timeline", "نقشه راه ریکاوری و تاریخ بازگشت", has_timeline, False, "full"),
        ("impact", "شوک آماری غیبت (با / بدون بازیکن)", has_impact, False, "full"),
        ("replacements", "گزینه‌های جایگزین و سناریوی تاکتیکی", has_reps, True, "half"),
        ("history", "سابقه مصدومیت و ریسک عود مجدد", has_hist, True, "half"),
        ("verdict", "جمع‌بندی تحریریه XGPedia", has_verd, True, "half"),
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


def _brand_logo_html() -> str:
    uri = _brand_logo_data_uri(mono=False)
    if uri:
        return f'<div class="in-brand" dir="ltr"><img src="{uri}" alt="XGPedia" class="in-brand-img"></div>'
    return '<div class="in-brand" dir="ltr"><div class="fd in-brand-txt"><span style="color:#E62E45">XG</span><span style="color:#F8FAFC">Pedia</span></div></div>'


def _crest_svg(pl: dict[str, Any], size: int) -> str:
    from src.xgpedia.providers.pl_badges_free import get_pl_badge_data_uri
    _luri = pl.get("logoUrl") or get_pl_badge_data_uri(
        str(pl.get("club") or pl.get("team") or ""),
        tla_hint=str(pl.get("clubCode") or pl.get("code") or ""),
        fetch_network=False,
    )
    if _luri:
        return (
            f'<div style="width:{size}px;height:{size}px;flex-shrink:0;display:flex;align-items:center;justify-content:center;'
            f'border-radius:50%;background:rgba(7,13,29,.72);padding:{max(3, size // 11)}px;filter:drop-shadow(0 8px 16px rgba(0,0,0,.55))">'
            f'<img src="{esc(_luri)}" alt="{esc(pl.get("clubCode") or pl.get("club") or "")}" style="width:100%;height:100%;object-fit:contain;display:block"/></div>'
        )
    s = str(pl.get("color") or "#E62E45")
    a = str(pl.get("secondary") or "#FFFFFF")
    cd = esc(str(pl.get("clubCode") or "FC")[:3].upper())
    u = f"c_{cd}_{size}"
    d = "M90 16L150 40V88C150 128 124.5 156.5 90 166C55.5 156.5 30 128 30 88V40Z"
    pill_bg = "#0D1730" if luminance(s) > 0.65 else "rgba(7,13,29,0.62)"
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 180 180" fill="none" style="filter:drop-shadow(0 12px 22px rgba(0,0,0,.55));display:block">'
        f'<defs><linearGradient id="g{u}" x1="20" y1="15" x2="160" y2="165" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{a}" stop-opacity=".95"/><stop offset=".5" stop-color="{s}" stop-opacity=".92"/><stop offset="1" stop-color="{a}" stop-opacity=".72"/></linearGradient>'
        f'<clipPath id="cl{u}"><path d="{d}"/></clipPath></defs>'
        f'<path d="M90 12L154 38V88C154 130.5 127 160.5 90 170.5C53 160.5 26 130.5 26 88V38Z" fill="{s}" fill-opacity=".22"/>'
        f'<g clip-path="url(#cl{u})"><rect x="25" y="12" width="130" height="158" fill="{s}"/>'
        f'<path d="M25 112L155 56V84L25 140Z" fill="{a}" fill-opacity=".28"/>'
        f'<path d="M90 16L150 40V58L90 34L30 58V40Z" fill="{a}" fill-opacity=".90"/>'
        f'<ellipse cx="90" cy="30" rx="65" ry="28" fill="#fff" fill-opacity=".14"/></g>'
        f'<path d="{d}" stroke="url(#g{u})" stroke-width="5"/>'
        f'<rect x="42" y="68" width="96" height="48" rx="14" fill="{pill_bg}" stroke="{a}" stroke-opacity=".55" stroke-width="2"/>'
        f'<text x="90" y="102" text-anchor="middle" fill="#fff" font-family="Space Grotesk,JetBrains Mono,sans-serif" font-weight="800" font-size="32" letter-spacing="2">{cd}</text>'
        f'<circle cx="90" cy="136" r="5" fill="{contrast_ink(s)}" fill-opacity=".85"/></svg>'
    )


def _avatar_html(pl: dict[str, Any], sev: dict[str, str], size: int) -> str:
    photo = str(pl.get("photoUrl") or "").strip()
    col = str(pl.get("color") or "#E62E45")
    sec = str(pl.get("secondary") or "#FFFFFF")
    raw_num = pl.get("number")
    num = esc(str(raw_num)) if raw_num not in (None, "", "None") else ""
    cd = esc(str(pl.get("clubCode") or "FC")[:3].upper())
    if photo.startswith("data:image/"):
        return (
            f'<div class="in-avatar" style="width:{size}px;height:{size}px;border-color:{sev["color"]}88;background:radial-gradient(circle at 50% 25%,{col}55,#070D1D 82%)">'
            f'<img src="{photo}" alt="" style="width:100%;height:100%;object-fit:cover;object-position:top;display:block">'
            f'<div class="in-av-fade"></div>' + (f'<span class="fd in-av-num">#{fa(num)}</span>' if num else '') + '</div>'
        )
    return (
        f'<div class="in-avatar fc" style="width:{size}px;height:{size}px;border-color:{sev["color"]}80;background:radial-gradient(circle at 50% 22%,{col}4d,#081126 78%)">'
        f'<svg width="{size}" height="{size}" viewBox="0 0 180 180" fill="none">'
        f'<defs><linearGradient id="jg_{cd}" x1="90" y1="78" x2="90" y2="180" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{col}"/><stop offset="1" stop-color="#091124"/></linearGradient></defs>'
        f'<circle cx="90" cy="86" r="68" stroke="{sev["color"]}" stroke-opacity=".24" stroke-width="1.4" stroke-dasharray="4 6"/>'
        f'<text x="90" y="106" text-anchor="middle" fill="#fff" fill-opacity=".07" font-family="Space Grotesk,sans-serif" font-weight="800" font-size="96">{num}</text>'
        f'<path d="M26 180 C28 134 52 114 72 108 L90 120 L108 108 C128 114 152 134 154 180 Z" fill="url(#jg_{cd})" stroke="rgba(255,255,255,.2)" stroke-width="2"/>'
        f'<path d="M72 108 L90 124 L108 108" stroke="{sec}" stroke-width="3" fill="none" stroke-linejoin="round"/>'
        f'<rect x="79" y="88" width="22" height="24" rx="8" fill="#1E293B" stroke="rgba(255,255,255,.15)" stroke-width="1.5"/>'
        f'<path d="M64 60 C64 41 75 30 90 30 C105 30 116 41 116 60 C116 77 104 92 90 92 C76 92 64 77 64 60 Z" fill="#1E293B" stroke="rgba(255,255,255,.22)" stroke-width="2"/>'
        f'<path d="M65 56 C66 39 77 29 90 29 C104 29 115 39 115 54 C106 46 97 43 88 45 C77 47 70 51 65 56 Z" fill="#0F172A"/>'
        f'<text x="90" y="162" text-anchor="middle" fill="#fff" font-family="Space Grotesk,sans-serif" font-weight="800" font-size="34">{num}</text></svg>'
        f'<div class="fm in-av-code">{cd}</div></div>'
    )


def _body_scanner_svg(zone_key: str, color: str, compact: bool) -> str:
    z = INJURY_ZONES.get(zone_key, INJURY_ZONES["hamstring"])
    mh = 215 if compact else 255
    return (
        f'<svg viewBox="0 0 278 340" style="width:100%;height:auto;max-height:{mh}px;display:block" fill="none">'
        f'<defs><radialGradient id="injGlow" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="{color}" stop-opacity=".85"/><stop offset=".45" stop-color="{color}" stop-opacity=".28"/><stop offset="1" stop-color="{color}" stop-opacity="0"/></radialGradient>'
        f'<linearGradient id="bodyGrad" x1="110" y1="20" x2="110" y2="330" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#38BDF8" stop-opacity=".24"/><stop offset=".5" stop-color="#94A3B8" stop-opacity=".16"/><stop offset="1" stop-color="#38BDF8" stop-opacity=".22"/></linearGradient></defs>'
        f'<g stroke="#94A3B8" stroke-opacity=".14" stroke-width="1">'
        f'<line x1="20" y1="85" x2="200" y2="85" stroke-dasharray="3 5"/><line x1="20" y1="170" x2="200" y2="170" stroke-dasharray="3 5"/>'
        f'<line x1="20" y1="255" x2="200" y2="255" stroke-dasharray="3 5"/><line x1="110" y1="12" x2="110" y2="332" stroke-dasharray="4 6"/></g>'
        f'<g stroke="#7DD3FC" stroke-opacity=".55" stroke-width="1.8" fill="url(#bodyGrad)">'
        f'<ellipse cx="110" cy="36" rx="17" ry="21"/>'
        f'<path d="M98 58 L122 58 L126 70 L152 80 C158 83 160 92 158 102 L149 162 L139 162 L144 106 L136 104 L132 168 L135 190 L85 190 L88 168 L84 104 L76 106 L81 162 L71 162 L62 102 C60 92 62 83 68 80 L94 70 Z"/>'
        f'<path d="M85 190 L107 190 L105 248 L102 316 L84 318 L86 248 Z"/>'
        f'<path d="M113 190 L135 190 L134 248 L136 318 L118 316 L115 248 Z"/></g>'
        f'<g fill="#E2E8F0" fill-opacity=".45"><circle cx="78" cy="92" r="3"/><circle cx="142" cy="92" r="3"/><circle cx="110" cy="116" r="2.5"/><circle cx="110" cy="154" r="2.5"/><circle cx="94" cy="248" r="3.2"/><circle cx="126" cy="248" r="3.2"/><circle cx="93" cy="316" r="2.8"/><circle cx="127" cy="316" r="2.8"/></g>'
        f'<circle cx="{z["x"]}" cy="{z["y"]}" r="36" fill="url(#injGlow)"/>'
        f'<circle cx="{z["x"]}" cy="{z["y"]}" r="22" stroke="{color}" stroke-width="1.6" stroke-dasharray="4 4"/>'
        f'<circle cx="{z["x"]}" cy="{z["y"]}" r="11" stroke="{color}" stroke-width="2.4" fill="{color}" fill-opacity=".28"/>'
        f'<circle cx="{z["x"]}" cy="{z["y"]}" r="4.2" fill="#fff"/>'
        f'<path d="M{z["x"] + 12} {z["y"]} L{z["lx"] - 26} {z["ly"]} L{z["lx"]} {z["ly"]}" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<circle cx="{z["lx"]}" cy="{z["ly"]}" r="3.5" fill="{color}"/>'
        f'<line x1="22" y1="{z["y"]}" x2="{z["x"] - 16}" y2="{z["y"]}" stroke="{color}" stroke-opacity=".45" stroke-width="1.2" stroke-dasharray="3 4"/>'
        f'<rect x="{z["lx"] + 5}" y="{z["ly"] - 15}" width="84" height="30" rx="8" fill="#070D1D" stroke="{color}" stroke-width="1.6"/>'
        f'<text x="{z["lx"] + 47}" y="{z["ly"] + 4}" text-anchor="middle" fill="#fff" font-family="JetBrains Mono,sans-serif" font-weight="800" font-size="11.5">{esc(zone_key.upper())}</text></svg>'
    )


def _mod_hdr(title: str, right_html: str, bar_col: str = "#E62E45") -> str:
    return (
        f'<div class="mh fbw"><div class="fi in-g10">'
        f'<span class="in-mbar" style="background:{bar_col}"></span>'
        f'<h3 class="mt">{esc(title)}</h3></div><div>{right_html}</div></div>'
    )


def _render_hero(item: dict[str, Any], sev: dict[str, str], header_mode: str, is_wide: bool) -> str:
    pl = item.get("player") or {}
    inj = item.get("injury") or {}
    prob = max(0, min(100, int(inj.get("nextProb") or 0)))

    if header_mode == "compact":
        return (
            f'<div class="in-hero-compact" style="border-right:6px solid {sev["color"]}">'
            f'<div class="fi in-g14 in-minw-0">{_crest_svg(pl, 68)}'
            f'<div class="in-minw-0"><div class="fi in-g10"><h2 class="in-hc-name">{esc(pl.get("name", ""))}</h2>'
            f'' + (f'<span class="fm in-hc-num">#{fa(pl.get("number"))}</span>' if pl.get("number") not in (None, "", "None") else '') + '</div>'
            f'<div class="in-hc-sub">{esc(pl.get("club", ""))} • {esc(fa(inj.get("diagnosis", "")))}</div></div></div>'
            f'<div class="fcol" style="align-items:flex-end;gap:6px;flex-shrink:0">'
            f'<span class="in-sev-pill" style="background:{sev["bg"]};border-color:{sev["bd"]};color:#fff">{esc(sev["fa"])}</span>'
            f'<span style="font-size:16px;font-weight:800;color:#CBD5E1">بازگشت: <b style="color:#fff">{esc(fa(inj.get("eta", "—")))}</b></span></div></div>'
        )

    col = str(pl.get("color") or "#E62E45")
    av_sz = 158 if is_wide else 178
    return (
        f'<div class="in-hero-full" style="background:linear-gradient(135deg,#112042eb 0%,#081024f5 62%,{col}2b 100%)">'
        f'' + (f'<div class="fd in-hero-wm" style="color:{col}">{esc(pl.get("number"))}</div>' if pl.get("number") not in (None, "", "None") else '') + ''
        f'<div class="in-hero-grid">'
        f'<div class="fc" style="position:relative">{_avatar_html(pl, sev, av_sz)}<div style="position:absolute;bottom:-6px;right:4px">{_crest_svg(pl, 66)}</div></div>'
        f'<div class="fcol" style="gap:12px;min-width:0">'
        f'<div class="fbw"><div class="fi in-g8 in-sev-big" style="background:{sev["bg"]};border-color:{sev["bd"]}"><span class="in-dot" style="background:{sev["color"]}"></span><span>{esc(sev["fa"])}</span><span class="fm" style="font-size:14px;opacity:.85">{esc(sev["en"])}</span></div>'
        f'<span class="fm in-grade-pill">{esc(inj.get("grade", "MEDICAL"))}</span></div>'
        f'<div><h1 class="in-h-name">{esc(pl.get("name", ""))}</h1><div class="in-h-club"><span>{esc(pl.get("club", ""))}</span> · <span>{esc(pl.get("pos", ""))}</span></div></div>'
        f'<div class="in-diag-box"><div class="in-minw-0"><div style="font-size:13.5px;font-weight:700;color:#94A3B8">تشخیص کادر پزشکی</div>'
        f'<div class="in-diag-txt">{esc(fa(inj.get("diagnosis", "—")))}</div></div>'
        f'<svg width="92" height="34" viewBox="0 0 230 48" fill="none" style="flex-shrink:0"><path d="M0 24 H34 L46 24 L56 6 L68 42 L78 16 L88 24 H136 L146 24 L154 11 L164 36 L172 20 L180 24 H230" stroke="{sev["color"]}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/></svg></div>'
        f'<div class="in-kpi3">'
        f'<div class="in-kbox"><div class="in-klbl">مدت دوری</div><div class="in-kval">{esc(fa(inj.get("eta", "—")))}</div></div>'
        f'<div class="in-kbox"><div class="in-klbl">بازگشت تخمینی</div><div class="in-kval" style="color:#7DD3FC">{esc(fa(inj.get("returnDate", "—")))}</div></div>'
        f'<div class="in-kbox"><div class="in-klbl">شانس بازی بعد</div><div class="fi in-g8" style="margin-top:2px"><span class="in-kval" style="color:{sev["color"]}">{fa(prob)}٪</span><div class="in-pbar"><div style="width:{prob}%;background:{sev["color"]};height:100%"></div></div></div></div>'
        f'</div></div></div></div>'
    )


def render_injury_html(
    item: dict[str, Any],
    *,
    slide: str = INJURY_DEFAULT_SLIDE,
    header_mode: str | None = None,
    fmt: str = "4:5",
    severity_override: str | None = None,
    enabled_modules: list[str] | None = None,
    custom_modules: list[dict[str, Any]] | None = None,
) -> str:
    """تولید HTML کامل و ۱۰۰٪ آفلاین کارت ماژولار آزمایشگاه مصدومیت (D53)."""
    w, h = INJURY_FORMATS.get(fmt, INJURY_FORMATS["4:5"])
    is_wide = fmt == "16:9"
    is_story = fmt == "9:16"
    sl_meta = next((s for s in INJURY_SLIDES if s[0] == slide), INJURY_SLIDES[0])
    eff_hm = header_mode or sl_meta[2]

    pl = item.get("player") or {}
    inj = item.get("injury") or {}
    sev_k = (severity_override or str(inj.get("severity") or "out")).lower()
    sev = INJURY_SEVERITIES.get(sev_k, INJURY_SEVERITIES["out"])

    if custom_modules is not None:
        mods = [dict(m) for m in custom_modules if m.get("enabled")]
    else:
        all_mods, _ = get_injury_modules(item, slide)
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
            spans.append("in-span-full")
        else:
            half_run += 1
            nxt_half = (idx + 1 < len(mods)) and (mods[idx + 1].get("span") == "half") and mods[idx + 1].get("can_half", False)
            if not nxt_half and half_run % 2 == 1:
                half_run = 0
                spans.append("in-span-full")
            else:
                spans.append("in-span-half")

    mods_html = ""
    for m, sc in zip(mods, spans):
        mid = m["id"]
        is_half = sc == "in-span-half"
        if mid == "anatomical":
            mods_html += (
                f'<div class="xm {sc}">'
                + _mod_hdr("اسکنر آناتومی مصدومیت", '<span class="fm" style="font-size:15px;font-weight:800;color:#7DD3FC">BIOMECHANICAL SCAN</span>', "#38BDF8")
                + f'<div class="in-anat-grid" style="grid-template-columns:{"1fr" if is_half else "5fr 7fr"}">'
                f'<div class="fc" dir="ltr">{_body_scanner_svg(str(inj.get("zone") or "hamstring"), sev["color"], is_half)}</div>'
                f'<div class="in-mech-box" style="border-right:4px solid {sev["color"]}"><div style="font-size:14px;font-weight:700;color:#FCD34D;margin-bottom:4px">مکانیسم آسیب‌دیدگی</div>'
                f'<p style="font-size:17px;font-weight:600;color:#E2E8F0;line-height:1.45">{esc(fa(inj.get("mechanism") or inj.get("diagnosis") or "—"))}</p></div></div></div>'
            )
        elif mid == "missed":
            fxs = item.get("fixtures") or []
            avg_d = sum(float(fx.get("diff") or 3) for fx in fxs) / len(fxs) if fxs else 0.0
            rows = []
            for fx in fxs[:4]:
                st_t = str(fx.get("status") or "")
                is_out = "غایب" in st_t
                is_ok = "آماده" in st_t or "بازگشت" in st_t
                b_cls = "in-fx-out" if is_out else ("in-fx-ok" if is_ok else "in-fx-dbt")
                pips = "".join(f'<span class="in-pip {"on" if i < int(fx.get("diff") or 3) else ""}"></span>' for i in range(5))
                rows.append(
                    f'<div class="in-fx-row"><div class="fi in-g10 in-minw-0"><div class="fd in-fx-code">{esc(fx.get("code", "FC"))}</div>'
                    f'<div class="in-minw-0"><div class="in-fx-opp">{esc(fx.get("opp", ""))}</div>'
                    f'<div class="in-fx-sub">{esc(fx.get("comp", ""))} • {esc(fx.get("loc", ""))} • {esc(fa(fx.get("date", "")))}</div></div></div>'
                    f'<div class="fcol" style="align-items:flex-end;gap:4px;flex-shrink:0"><span class="in-fx-st {b_cls}">{esc(fa("غایب" if is_out else st_t))}</span><div class="fi in-g3">{pips}</div></div></div>'
                )
            mods_html += (
                f'<div class="xm {sc}">'
                + _mod_hdr("بازی‌های حساس پیش‌رو", f'<span style="font-size:15px;font-weight:800;color:#FCD34D">سختی {fa(f"{avg_d:.1f}")}/۵</span>', "#E62E45")
                + f'<div class="fcol in-g8">{"".join(rows)}</div></div>'
            )
        elif mid == "timeline":
            steps = [("۱", "تشخیص و MRI"), ("۲", "استراحت و درمان"), ("۳", "فیزیوتراپی"), ("۴", "تمرین انفرادی"), ("۵", "بازگشت به زمین")]
            st_n = max(1, min(5, int(inj.get("stage") or 2)))
            pct = (st_n - 1) / 4.0 * 100.0
            nodes = []
            for idx_s, (num_fa, lbl_fa) in enumerate(steps, 1):
                cls = "st-done" if idx_s < st_n else ("st-now" if idx_s == st_n else "")
                tx_c = "#fff" if idx_s == st_n else ("#6EE7B7" if idx_s < st_n else "#94A3B8")
                nodes.append(
                    f'<div class="st-node {cls}"><div class="st-dot" style="{"background:" + sev["color"] + ";border-color:#fff;color:#fff" if idx_s == st_n else ""}">{"✓" if idx_s < st_n else num_fa}</div>'
                    f'<div style="font-size:15px;font-weight:800;margin-top:8px;color:{tx_c}">{lbl_fa}</div></div>'
                )
            mods_html += (
                f'<div class="xm {sc}">'
                + _mod_hdr("نقشه راه ریکاوری و بازگشت", f'<span class="fm" style="font-size:16px;font-weight:800;color:#6EE7B7">STAGE {st_n}/5</span>', "#34D399")
                + f'<div class="in-tl-wrap"><div class="in-tl-track"><div style="width:{pct:.1f}%;height:100%;background:linear-gradient(90deg,#10B981,{sev["color"]})"></div></div>'
                f'<div class="fbw" style="position:relative">{"".join(nodes)}</div></div></div>'
            )
        elif mid == "impact":
            imp = item.get("impact") or {}
            irows = []
            for r in imp.get("rows") or []:
                wv, wov = float(r.get("w") or 0), float(r.get("wo") or 0)
                mx = max(wv, wov, 0.01)
                d_dec = int(r.get("d") or 0)
                unit = str(r.get("unit") or "")
                irows.append(
                    f'<div class="fcol in-g6"><div class="in-imp-top"><span style="color:#6EE7B7;font-size:26px;font-weight:900">{fa(f"{wv:.{d_dec}f}")}{unit}</span>'
                    f'<span style="color:#F1F5F9;font-size:18px;font-weight:800;text-align:center">{esc(r.get("label", ""))}</span>'
                    f'<span style="color:#FB7185;font-size:26px;font-weight:900;text-align:left">{fa(f"{wov:.{d_dec}f}")}{unit}</span></div>'
                    f'<div class="in-imp-bars"><div class="in-bar-r"><div style="width:{wv / mx * 100:.1f}%;height:100%;background:linear-gradient(to left,#34D399,#14B8A6);border-radius:0 99px 99px 0"></div></div>'
                    f'<div class="in-bar-l"><div style="width:{wov / mx * 100:.1f}%;height:100%;background:linear-gradient(to right,#F43F5E,#F87171);border-radius:99px 0 0 99px"></div></div></div></div>'
                )
            mods_html += (
                f'<div class="xm {sc}">'
                + _mod_hdr("شوک آماری غیبت", f'<div class="fi in-g12" style="font-size:15px;font-weight:800"><span style="color:#6EE7B7">● {esc(imp.get("withLbl", "با بازیکن"))}</span><span style="color:#FB7185">● {esc(imp.get("withoutLbl", "بدون بازیکن"))}</span></div>', "#E62E45")
                + f'<div class="fcol in-g12">{"".join(irows)}'
                f'<div class="in-imp-foot"><span class="in-dot" style="background:#FBBF24"></span><span>{esc(fa(imp.get("dropTag", "")))}</span></div></div></div>'
            )
        elif mid == "replacements":
            reps = item.get("replacements") or []
            rcards = []
            for rp in reps[:2]:
                rc = str(rp.get("color") or "#38BDF8")
                fit_v = max(0, min(100, int(rp.get("fit") or 75)))
                rcards.append(
                    f'<div class="in-rep-card" style="border-right:5px solid {rc}">'
                    f'<div class="fbw"><div><div style="font-size:22px;font-weight:900;color:#fff">{esc(rp.get("name", ""))}</div><div style="font-size:15px;font-weight:700;color:#94A3B8">{esc(rp.get("role", ""))}</div></div>'
                    f'<div style="text-align:left"><span class="in-rep-fit" style="color:{rc}">تطابق {fa(fit_v)}٪</span><div style="font-size:14px;font-weight:800;color:#CBD5E1;margin-top:4px">{esc(fa(rp.get("stat", "")))}</div></div></div>'
                    f'<div class="in-pbar" style="height:8px"><div style="width:{fit_v}%;background:{rc};height:100%"></div></div>'
                    f'<div style="font-size:16px;font-weight:600;color:#E2E8F0">{esc(fa(rp.get("note", "")))}</div></div>'
                )
            mods_html += (
                f'<div class="xm {sc}">'
                + _mod_hdr("گزینه‌های جایگزین تاکتیکی", '<span class="fm" style="font-size:15px;font-weight:800;color:#C4B5FD">SQUAD DEPTH</span>', "#A78BFA")
                + f'<div class="fcol in-g10">{"".join(rcards)}</div></div>'
            )
        elif mid == "history":
            hist = item.get("history") or {}
            seasons = hist.get("seasons") or []
            mx_d = max([int(s.get("days") or 0) for s in seasons] + [30])
            bars = []
            for s in seasons[:3]:
                dy = int(s.get("days") or 0)
                bh = max(18, round(dy / mx_d * 90))
                bars.append(
                    f'<div class="in-hcol"><span style="font-size:20px;font-weight:900;color:#fff">{fa(dy)} <small style="font-size:12px;color:#94A3B8">روز</small></span>'
                    f'<div class="in-hbar-wrap"><div style="width:36px;height:{bh}px;border-radius:10px 10px 0 0;background:linear-gradient(to top,rgba(230,46,69,.26),#E62E45)"></div></div>'
                    f'<span class="fm" style="font-size:14px;font-weight:800;color:#CBD5E1">{esc(s.get("yr", ""))}</span></div>'
                )
            rk_v = inj.get("reinjuryRisk")
            rk_txt = f"{inj.get('reinjuryLabel', '')} ({fa(rk_v)}٪)" if rk_v is not None else "—"
            rk_col = "#F43F5E" if (rk_v or 0) >= 55 else ("#F59E0B" if (rk_v or 0) >= 35 else "#10B981")
            mods_html += (
                f'<div class="xm {sc}">'
                + _mod_hdr("سابقه مصدومیت و ریسک عود", '<span class="fm" style="font-size:15px;font-weight:800;color:#CBD5E1">3-SEASON LOG</span>', "#FBBF24")
                + f'<div class="in-hgrid">{"".join(bars)}</div>'
                f'<div class="in-hfoot"><div><div style="font-size:14px;font-weight:700;color:#94A3B8">ریسک عود مجدد</div><div style="font-size:20px;font-weight:900;color:{rk_col}">{esc(fa(rk_txt))}</div></div>'
                f'<div style="text-align:left"><div style="font-size:14px;font-weight:700;color:#94A3B8">کل ۳ فصل اخیر</div><div style="font-size:19px;font-weight:900;color:#fff">{fa(hist.get("totalDays", 0))} روز • {fa(hist.get("missedGames", 0))} بازی</div></div></div></div>'
            )
        elif mid == "verdict":
            v = item.get("verdict") if isinstance(item.get("verdict"), dict) else {}
            mods_html += (
                f'<div class="xe {sc}">'
                f'<svg class="in-verd-wm" viewBox="0 0 240 160" fill="none" stroke="#DCE6F8" stroke-width="2.5"><rect x="2" y="2" width="236" height="156" rx="8"/><line x1="120" y1="2" x2="120" y2="158"/><circle cx="120" cy="80" r="32"/></svg>'
                f'<div class="fcol" style="position:relative;z-index:10;justify-content:space-between;gap:10px;flex:1"><div>'
                + _mod_hdr("جمع‌بندی تحریریه XGPedia", '<span class="fm" style="font-size:15px;font-weight:800;color:#FCD34D">TACTICAL VERDICT</span>', "#FBBF24")
                + f'<h4 style="font-size:23px;font-weight:900;color:#FCD34D;line-height:1.35;margin-bottom:6px">{esc(fa(v.get("title", "")))}</h4>'
                f'<p style="font-size:19px;line-height:1.58;color:#F1F5F9;font-weight:600">{esc(fa(v.get("body", "")))}</p></div>'
                f'<div class="in-verd-foot"><span class="in-dot" style="background:{sev["color"]}"></span><span>{esc(fa(v.get("tag", "")))}</span></div></div></div>'
            )

    hero_html = _render_hero(item, sev, eff_hm, is_wide)
    pad_top = "139px" if is_story else ("22px" if is_wide else "24px")
    pad_bot = "171px" if is_story else ("16px" if is_wide else "20px")
    crh_d = f"M24 44V24H44M{w - 24} 44V24H{w - 44}M24 {h - 44}V{h - 24}H44M{w - 24} {h - 44}V{h - 24}H{w - 44}"
    font_css = build_embedded_font_css()

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<style>
{font_css}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:{w}px;height:{h}px;overflow:hidden;font-family:'Vazirmatn',system-ui,sans-serif;background:#0D1730;color:#F8FAFC;font-feature-settings:"tnum";font-variant-numeric:tabular-nums}}
.fm{{font-family:'JetBrains Mono','Space Grotesk',monospace}}.fd{{font-family:'Space Grotesk',sans-serif}}
.fi{{display:flex;align-items:center}}.fc{{display:flex;align-items:center;justify-content:center}}.fbw{{display:flex;align-items:center;justify-content:space-between}}.fcol{{display:flex;flex-direction:column}}
.in-g3{{gap:3px}}.in-g6{{gap:6px}}.in-g8{{gap:8px}}.in-g10{{gap:10px}}.in-g12{{gap:12px}}.in-g14{{gap:14px}}.in-minw-0{{min-width:0;flex:1}}
.in-canvas{{position:relative;width:{w}px;height:{h}px;background:#0D1730;overflow:hidden;display:flex;flex-direction:column;justify-content:space-between;padding:{pad_top} 0 {pad_bot}}}
.in-ambient{{position:absolute;inset:0;pointer-events:none;z-index:0;background:radial-gradient(circle at 82% 24%,{pl.get("color", "#E62E45")}38,transparent 48%),radial-gradient(circle at 18% 26%,{sev["color"]}30,transparent 48%)}}
.in-bg-svg{{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0}}
.in-scan{{position:absolute;inset:0;pointer-events:none;z-index:0;background:repeating-linear-gradient(to bottom,rgba(255,255,255,.016) 0 1px,transparent 1px 4px)}}
.in-header{{position:relative;z-index:10;padding:12px 36px 8px;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-shrink:0}}
.in-comp-pill{{padding:6px 16px;border-radius:999px;font-size:21px;font-weight:900;display:flex;align-items:center;gap:10px;border:1px solid rgba(255,255,255,.18);background:rgba(21,35,71,.9);color:#F8FAFC}}
.in-bul-pill{{padding:6px 16px;border-radius:999px;font-size:20px;font-weight:800;border:1px solid {sev["bd"]};background:{sev["bg"]};color:{sev["tx"]}}}
.in-meta-row{{display:flex;align-items:center;gap:10px;font-size:18px;font-weight:700;color:#CBD5E1;margin-top:6px}}
.in-code-pill{{padding:2px 12px;border-radius:999px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.15);color:#E2E8F0;font-size:16px;font-weight:800}}
.in-brand-img{{height:48px;width:auto;display:block}}.in-brand-txt{{font-size:34px;font-weight:800;line-height:1}}
.in-stage-v{{position:relative;z-index:10;flex:1;padding:8px 40px;display:flex;flex-direction:column;gap:14px;overflow:hidden;min-height:0}}
.in-stage-w{{position:relative;z-index:10;flex:1;padding:8px 40px;display:grid;grid-template-columns:5fr 7fr;gap:24px;align-items:stretch;overflow:hidden;min-height:0}}
.in-mods-grid{{flex:1;display:grid;grid-template-columns:1fr 1fr;gap:12px;min-height:0;overflow:hidden;align-content:start}}
.in-span-full{{grid-column:1 / -1;min-width:0}}.in-span-half{{grid-column:span 1;min-width:0}}
.in-hero-full{{position:relative;border-radius:28px;overflow:hidden;border:1px solid rgba(255,255,255,.16);padding:20px 24px;box-shadow:0 22px 54px -12px rgba(0,0,0,.75);flex-shrink:0}}
.in-hero-wm{{position:absolute;left:-24px;bottom:-36px;font-size:200px;font-weight:800;line-height:1;opacity:.06;pointer-events:none}}
.in-hero-grid{{position:relative;z-index:10;display:grid;grid-template-columns:4fr 8fr;align-items:center;gap:18px}}
.in-avatar{{position:relative;border-radius:26px;overflow:hidden;border:2px solid;box-shadow:0 18px 40px rgba(0,0,0,.6);flex-shrink:0}}
.in-av-fade{{position:absolute;inset:auto 0 0 0;height:33%;background:linear-gradient(to top,#070D1D,transparent)}}.in-av-num{{position:absolute;bottom:8px;right:12px;font-size:28px;font-weight:900;color:#fff}}
.in-av-code{{position:absolute;top:10px;left:10px;padding:2px 8px;border-radius:8px;background:rgba(4,8,20,.85);border:1px solid rgba(255,255,255,.15);font-size:13px;font-weight:800;color:#fff}}
.in-sev-big{{padding:4px 14px;border-radius:999px;border:1px solid;font-size:17px;font-weight:900;color:#fff}}.in-grade-pill{{padding:4px 12px;border-radius:12px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14);font-size:16px;font-weight:800;color:#E2E8F0}}
.in-h-name{{font-size:{"42px" if is_wide else "48px"};font-weight:900;color:#fff;line-height:1.08}}.in-h-club{{font-size:20px;font-weight:800;color:#CBD5E1;margin-top:4px}}
.in-diag-box{{border-radius:16px;padding:10px 16px;background:rgba(5,11,26,.85);border:1px solid rgba(255,255,255,.12);display:flex;align-items:center;justify-content:space-between;gap:12px}}
.in-diag-txt{{font-size:21px;font-weight:900;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.in-kpi3{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}.in-kbox{{border-radius:16px;padding:10px 14px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12)}}
.in-klbl{{font-size:13.5px;font-weight:700;color:#94A3B8}}.in-kval{{font-size:21px;font-weight:900;color:#fff;margin-top:2px}}
.in-pbar{{flex:1;height:8px;border-radius:99px;background:rgba(255,255,255,.14);overflow:hidden}}
.in-hero-compact{{border-radius:24px;background:rgba(11,22,47,.92);border:1px solid rgba(255,255,255,.15);padding:14px 22px;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-shrink:0}}
.in-hc-name{{font-size:30px;font-weight:900;color:#fff}}.in-hc-num{{padding:2px 10px;border-radius:8px;background:rgba(255,255,255,.1);font-size:17px;font-weight:800;color:#E2E8F0}}.in-hc-sub{{font-size:18px;font-weight:700;color:#CBD5E1;margin-top:2px}}
.in-sev-pill{{padding:5px 16px;border-radius:12px;font-size:18px;font-weight:900;border:1px solid}}
.xm,.xe{{position:relative;border-radius:24px;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;box-shadow:0 16px 38px -10px rgba(0,0,0,.58),inset 0 1px 0 rgba(255,255,255,.1)}}
.xm{{background:linear-gradient(165deg,#101d3bde,#081022f5);border:1.5px solid rgba(248,250,252,.14);padding:14px 20px}}
.xe{{background:linear-gradient(155deg,#142142ed,#080f20fa);border:1.5px solid rgba(127,166,232,.26);padding:16px 22px}}
.mh{{padding-bottom:8px;margin-bottom:10px;border-bottom:1px solid rgba(255,255,255,.12)}}.in-mbar{{width:8px;height:24px;border-radius:99px;display:inline-block}}.mt{{font-size:23px;font-weight:900;color:#fff}}
.in-anat-grid{{display:grid;gap:12px;align-items:center;flex:1}}.in-mech-box{{padding:12px;border-radius:16px;background:rgba(7,14,33,.9);border:1px solid rgba(255,255,255,.1)}}
.in-fx-row{{border-radius:14px;padding:8px 12px;background:rgba(19,28,51,.9);border:1px solid rgba(255,255,255,.12);display:flex;align-items:center;justify-content:space-between;gap:10px}}
.in-fx-code{{width:38px;height:38px;border-radius:10px;background:#081024;border:1px solid rgba(255,255,255,.15);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:14px;color:#fff;flex-shrink:0}}
.in-fx-opp{{font-size:18px;font-weight:900;color:#fff}}.in-fx-sub{{font-size:13px;font-weight:700;color:#94A3B8;margin-top:2px}}
.in-fx-st{{padding:2px 10px;border-radius:8px;border:1px solid;font-size:13.5px;font-weight:900}}.in-fx-out{{background:rgba(230,46,69,.22);border-color:rgba(230,46,69,.6);color:#FF8A9A}}.in-fx-ok{{background:rgba(16,185,129,.2);border-color:rgba(52,211,153,.55);color:#6EE7B7}}.in-fx-dbt{{background:rgba(245,158,11,.2);border-color:rgba(251,191,36,.55);color:#FCD34D}}
.in-pip{{width:8px;height:8px;border-radius:2px;background:rgba(255,255,255,.15);display:inline-block}}.in-pip.on{{background:#E62E45}}
.in-tl-wrap{{position:relative;padding:8px 12px}}.in-tl-track{{position:absolute;top:24px;left:10%;right:10%;height:4px;background:rgba(255,255,255,.12);border-radius:99px;overflow:hidden}}
.st-node{{position:relative;z-index:2;display:flex;flex-direction:column;align-items:center;text-align:center;flex:1}}
.st-dot{{width:34px;height:34px;border-radius:99px;display:flex;align-items:center;justify-content:center;border:2px solid #334155;background:#0B1328;font-weight:900;font-size:15px;color:#64748B}}
.st-done .st-dot{{background:#10B981;border-color:#6EE7B7;color:#04111F}}
.in-imp-top{{display:grid;grid-template-columns:1fr 1.4fr 1fr;align-items:center}}.in-imp-bars{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
.in-bar-r{{height:13px;background:rgba(255,255,255,.1);border-radius:0 99px 99px 0;overflow:hidden;display:flex;justify-content:flex-end}}.in-bar-l{{height:13px;background:rgba(255,255,255,.1);border-radius:99px 0 0 99px;overflow:hidden;display:flex;justify-content:flex-start}}
.in-imp-foot{{padding-top:8px;border-top:1px solid rgba(255,255,255,.1);display:flex;align-items:center;gap:8px;font-size:16px;font-weight:800;color:#FCD34D}}
.in-rep-card{{padding:14px;border-radius:16px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);display:flex;flex-direction:column;gap:8px}}
.in-rep-fit{{padding:3px 12px;border-radius:10px;background:rgba(255,255,255,.1);font-size:17px;font-weight:900}}
.in-hgrid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;align-items:end;padding-top:6px}}
.in-hcol{{display:flex;flex-direction:column;align-items:center;gap:6px;background:#0A1328;border-radius:16px;padding:10px;border:1px solid rgba(255,255,255,.1)}}
.in-hbar-wrap{{width:100%;height:92px;display:flex;align-items:flex-end;justify-content:center}}
.in-hfoot{{margin-top:10px;border-radius:16px;padding:12px 14px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);display:flex;align-items:center;justify-content:space-between}}
.in-verd-wm{{position:absolute;left:20px;bottom:16px;width:160px;opacity:.08;pointer-events:none}}.in-verd-foot{{padding-top:10px;border-top:1px solid rgba(255,255,255,.12);display:flex;align-items:center;gap:8px;font-size:17px;font-weight:800;color:#F1F5F9}}
.in-dot{{width:10px;height:10px;border-radius:99px;display:inline-block;flex-shrink:0}}
.in-footer{{position:relative;z-index:10;padding:10px 44px 10px;flex-shrink:0}}.in-foot-line{{border-top:1px solid rgba(255,255,255,.12);margin-bottom:8px}}
.in-foot-tag{{font-size:18px;font-weight:800;letter-spacing:.14em;color:#F1F5F9;text-transform:uppercase}}.in-foot-h{{font-size:20px;font-weight:800;color:#fff}}.in-foot-s{{font-size:17px;font-weight:600;color:#CBD5E1}}

footer, footer .fbw, footer .cf-row, footer .fi, footer .cf-left, footer .cf-right, .xg-footer, .foot-row, .card-footer{{flex-wrap:nowrap!important;white-space:nowrap!important;min-width:0!important;}}
footer span, footer div, .pl-foot-tag, .pl-foot-s, .in-foot-tag, .pr-foot-tag, .st-foot-tag, .cf-tag{{white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;min-width:0!important;}}
</style>
</head>
<body>
<div class="in-canvas">
  <div class="in-ambient"></div>
  <svg class="in-bg-svg" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid slice" fill="none">
    <defs>
      <pattern id="tg" width="54" height="54" patternUnits="userSpaceOnUse"><path d="M54 0H0v54" stroke="#F8FAFC" stroke-opacity=".052"/></pattern>
      <pattern id="mgp" width="108" height="108" patternUnits="userSpaceOnUse"><path d="M54 48v12M48 54h12" stroke="#E62E45" stroke-opacity=".14" stroke-width="1"/></pattern>
      <radialGradient id="rf" cx="50%" cy="24%" r="46%"><stop offset="0" stop-color="#E62E45" stop-opacity=".22"/><stop offset=".55" stop-color="#E62E45" stop-opacity=".06"/><stop offset="1" stop-color="#E62E45" stop-opacity="0"/></radialGradient>
    </defs>
    <rect width="100%" height="100%" fill="url(#tg)"/><rect width="100%" height="100%" fill="url(#mgp)"/>
    <rect x="12" y="12" width="{w - 24}" height="{h - 24}" rx="18" stroke="#F8FAFC" stroke-opacity=".11" stroke-width="1.5"/>
    <g stroke="#F8FAFC" stroke-opacity=".08" stroke-width="1.5"><line x1="{w / 2}" y1="12" x2="{w / 2}" y2="{h - 12}" stroke-dasharray="8 8"/><circle cx="{w / 2}" cy="290" r="165"/><circle cx="{w / 2}" cy="290" r="280" stroke-opacity=".05"/></g>
    <path d="M12 290 H310 L335 290 L352 246 L372 334 L392 272 L408 290 H670 L692 290 L708 258 L724 318 L740 282 L755 290 H{w - 12}" stroke="#E62E45" stroke-opacity=".16" stroke-width="2" stroke-linejoin="round"/>
    <circle cx="{w / 2}" cy="290" r="245" fill="url(#rf)"/>
    <circle cx="{w / 2}" cy="290" r="215" stroke="#E62E45" stroke-opacity=".18" stroke-width="1.2" stroke-dasharray="4 6"/>
    <path d="{crh_d}" stroke="#E62E45" stroke-opacity=".6" stroke-width="2.2"/>
  </svg>
  <div class="in-scan"></div>
  <header class="in-header">
    <div class="fcol">
      <div class="fi in-g10">
        <div class="in-comp-pill">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#E62E45" stroke-width="2.6" stroke-linecap="round"><path d="M12 4v16M4 12h16"/><rect x="3" y="3" width="18" height="18" rx="4" stroke-opacity=".45" stroke-width="1.6"/></svg>
          <span>{esc(item.get("competition", "گزارش پزشکی"))}</span>
        </div>
        <span class="in-bul-pill">{esc(item.get("bulletin", "بولتن پزشکی"))}</span>
      </div>
      <div class="in-meta-row"><span>{esc(fa(item.get("date", "")))}</span><span>•</span><span style="color:#fff">{esc(fa(item.get("updated", "")))}</span><span class="fm in-code-pill">{esc(item.get("codeId", "MED-XG"))}</span></div>
    </div>
    {_brand_logo_html()}
  </header>
  <main class="{'in-stage-w' if is_wide else 'in-stage-v'}">
    {f'<section class="fcol" style="justify-content:center">{hero_html}</section><section class="in-mods-grid">{mods_html}</section>' if is_wide else f'{hero_html}<section class="in-mods-grid">{mods_html}</section>'}
  </main>
  <footer class="in-footer">
    <div class="in-foot-line"></div>
    <div class="fbw">
      <div class="fi in-g10"><span class="in-dot" style="background:{sev["color"]}"></span><span dir="ltr" class="fm in-foot-tag">{esc(str(item.get("leagueEn", "FOOTBALL")).upper())} {esc(item.get("season", "26/27"))} • INJURY LAB</span></div>
      <div class="fi in-g10 fm" dir="ltr"><span class="in-foot-h">@XGPedia</span><span style="color:#64748B">|</span><span class="in-foot-s">{esc(item.get("source", "XGPedia Lab"))}</span></div>
    </div>
  </footer>
</div>
</body>
</html>"""


def build_injury_caption(item: dict[str, Any]) -> str:
    """تولید کپشن فارسی تمیز برای کارت آزمایشگاه مصدومیت."""
    pl = item.get("player") or {}
    inj = item.get("injury") or {}
    sev = INJURY_SEVERITIES.get(str(inj.get("severity") or "out").lower(), INJURY_SEVERITIES["out"])
    v = item.get("verdict") if isinstance(item.get("verdict"), dict) else {}
    parts = [
        f"🏥 <b>گزارش پزشکی | {esc(pl.get('name', ''))} ({esc(pl.get('club', ''))})</b>",
        f"🚨 وضعیت: {sev['fa']} | تشخیص: {fa(inj.get('diagnosis', '—'))} | مدت دوری: {fa(inj.get('eta', '—'))}",
    ]
    if v.get("body"):
        parts.append(fa(str(v["body"]).strip()))
    return "\n\n".join(parts)
