"""کارت ماژولار «نمرات بازیکنان» (XGPedia Players Rating Studio — D51) — بازسازی ۱:۱ آفلاین.

ویژگی‌های ۱:۱ حفظ‌شده از `studio_templates/players_rating.html` + استاندارد ماژولار کامل XGPedia:
  - هدر مسابقه با سپرهای SVG باشگاهی، نتیجه با هاله نوری، xG (با قانون null ≠ 0)، گلزنان و سرمربیان (یا هدر فشرده)
  - زمین استادیوم وکتور با نورپردازی نورافکن‌های گوشه‌ای، ۱۲ نوار چمن، حلقه رادار و واترمارک XGPEDIA، خطوط پنالتی/کرنر،
    باکس میانگین نمره تیم روی زمین، هاله عملکرد و لینک‌های پاس نقطه‌چین، پیراهن وکتور (یا توکن دایره‌ای)،
    تاج و پرتوهای طلایی MOTM و بج‌های گل/پاس‌گل/کارت/تعویض
  - ۴ ماژول کاملاً مستقل و قابل چینش (`pitch`, `subs`, `ranking`, `verdict`) با پشتیبانی از نیم‌عرض (½) / تمام‌عرض (۱)،
    تغییر ترتیب، تغییر تم زمین (`turf`/`navy`/`gold`)، حالت زمین (`both`/`home`/`away`) و ۵ قالب ذخیره‌شده.
"""
from __future__ import annotations

import math
from typing import Any

from src.xgpedia.render.card_kit.helpers import with_sample_badge, contrast_ink, ensure_dark_bg_contrast, esc, f1, f2, fa, luminance
from src.xgpedia.render.cards import _brand_logo_data_uri
from src.xgpedia.render.studio_engine import build_embedded_font_css

RATINGS_DEFAULT_SLIDE = "slide1"
RATINGS_DEFAULT_HEADER = "full"

RATINGS_FORMATS: dict[str, tuple[int, int]] = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}

# (id, label_fa, pitch_mode, default_mods)
RATINGS_SLIDES: list[tuple[str, str, str, list[str]]] = [
    ("slide1", "اسلاید ۱: استادیوم ۲۲ بازیکن (پیشنهادی)", "both", ["pitch", "subs"]),
    ("slide2", "اسلاید ۲: زوم هنری تیم میزبان (۱۱ نفر)", "home", ["pitch", "subs"]),
    ("slide3", "اسلاید ۳: زوم هنری تیم میهمان (۱۱ نفر)", "away", ["pitch", "subs"]),
    ("slide4", "اسلاید ۴: جدول کامل نمرات و تحلیل تحریریه", "both", ["ranking", "verdict"]),
]

RATINGS_THEMES: dict[str, tuple[str, str, str, str]] = {
    "turf": ("چمن شبانه", "#082725", "#051921", "#072226"),
    "navy": ("سرمه‌ای XGP", "#0C1E42", "#07132B", "#0C1E42"),
    "gold": ("نئون طلایی", "#1A192A", "#0C1225", "#181828"),
}


def _rating_palette(r: float) -> dict[str, str]:
    if r >= 9.0:
        return {"bg": "#FBBF24", "bg2": "#FEF08A", "fg": "#070D1D", "glow": "#f59e0b"}
    if r >= 8.0:
        return {"bg": "#10B981", "bg2": "#6EE7B7", "fg": "#04140E", "glow": "#10b981"}
    if r >= 7.0:
        return {"bg": "#38BDF8", "bg2": "#BAE6FD", "fg": "#041222", "glow": "#0ea5e9"}
    if r >= 6.5:
        return {"bg": "#F59E0B", "bg2": "#FDE68A", "fg": "#0B0F1A", "glow": "#d97706"}
    return {"bg": "#F43F5E", "bg2": "#FDA4AF", "fg": "#FFFFFF", "glow": "#e11d48"}


def _avg_rating(players: list[dict[str, Any]]) -> float:
    vals = [float(p.get("rating") or 0) for p in players if p.get("rating") is not None]
    return sum(vals) / len(vals) if vals else 0.0


def get_players_rating_modules(
    item: dict[str, Any], slide: str = RATINGS_DEFAULT_SLIDE
) -> tuple[list[dict[str, Any]], list[str]]:
    """استخراج تمام ماژول‌های دارای دیتای واقعی کارت نمرات بازیکنان (قانون null ≠ 0)."""
    h = item.get("home") or {}
    a = item.get("away") or {}
    has_pitch = bool(h.get("xi") and a.get("xi"))
    has_subs = bool(h.get("subs") or a.get("subs"))
    has_ranking = bool(h.get("xi") or a.get("xi"))
    verd = item.get("verdict") if isinstance(item.get("verdict"), dict) else None
    has_verdict = bool(verd and verd.get("body"))

    def_mods = set(next((mids for sid, _, _, mids in RATINGS_SLIDES if sid == slide), ["pitch", "subs"]))
    specs = [
        ("pitch", "زمین استادیوم و نمرات (Tactical XI)", has_pitch, False, "full"),
        ("subs", "نوار بازیکنان تعویضی (Bench)", has_subs, True, "full"),
        ("ranking", "جدول رده‌بندی کامل ۲۲ بازیکن", has_ranking, True, "full"),
        ("verdict", "جمع‌بندی تحریریه XGPedia", has_verdict, True, "full"),
    ]
    mods: list[dict[str, Any]] = []
    missing: list[str] = []
    for mid, title_fa, has_d, can_half, def_span in specs:
        if has_d:
            mods.append({
                "id": mid,
                "title_fa": title_fa,
                "enabled": mid in def_mods,
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
        return f'<div class="pr-brand" dir="ltr"><img src="{uri}" alt="XGPedia" class="pr-brand-img"></div>'
    return '<div class="pr-brand" dir="ltr"><div class="fd pr-brand-txt"><span style="color:#E62E45">XG</span><span style="color:#F8FAFC">Pedia</span></div></div>'


def _crest_svg(team: dict[str, Any], uid: str, size: int) -> str:
    p = str(team.get("color") or "#EF0107")
    s = str(team.get("secondary") or "#FFFFFF")
    cd = esc(str(team.get("code") or "FC")[:3].upper())
    d = "M90 16L150 40V88C150 128 124.5 156.5 90 166C55.5 156.5 30 128 30 88V40Z"
    pill_bg = "#0D1730" if luminance(p) > 0.65 else "rgba(7,13,29,0.66)"
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 180 180" fill="none" style="filter:drop-shadow(0 10px 20px rgba(0,0,0,.6));display:block">'
        f'<defs><linearGradient id="g_{uid}" x1="20" y1="15" x2="160" y2="165" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{s}" stop-opacity=".95"/><stop offset=".5" stop-color="{p}" stop-opacity=".92"/>'
        f'<stop offset="1" stop-color="{s}" stop-opacity=".72"/></linearGradient>'
        f'<clipPath id="cl_{uid}"><path d="{d}"/></clipPath></defs>'
        f'<path d="M90 12L154 38V88C154 130.5 127 160.5 90 170.5C53 160.5 26 130.5 26 88V38Z" fill="{p}" fill-opacity=".22"/>'
        f'<g clip-path="url(#cl_{uid})"><rect x="25" y="12" width="130" height="158" fill="{p}"/>'
        f'<path d="M25 112L155 56V84L25 140Z" fill="{s}" fill-opacity=".28"/>'
        f'<path d="M90 16L150 40V58L90 34L30 58V40Z" fill="{s}" fill-opacity=".90"/>'
        f'<ellipse cx="90" cy="30" rx="65" ry="28" fill="#fff" fill-opacity=".14"/></g>'
        f'<path d="{d}" stroke="url(#g_{uid})" stroke-width="5"/>'
        f'<rect x="42" y="68" width="96" height="48" rx="14" fill="{pill_bg}" stroke="{s}" stroke-opacity=".55" stroke-width="2"/>'
        f'<text x="90" y="102" text-anchor="middle" fill="#FFFFFF" font-family="Space Grotesk,JetBrains Mono,sans-serif" font-weight="800" font-size="32" letter-spacing="2">{cd}</text>'
        f'<circle cx="90" cy="136" r="5" fill="{contrast_ink(p)}" fill-opacity=".85"/></svg>'
    )


def _mod_hdr(title: str, right_html: str, bar_col: str = "#E62E45") -> str:
    return (
        f'<div class="mh fbw"><div class="fi pr-g10">'
        f'<span class="pr-mbar" style="background:{bar_col}"></span>'
        f'<h3 class="mt">{esc(title)}</h3></div>{right_html}</div>'
    )


def _avg_badge_svg(team: dict[str, Any], avg_val: float, x: float, y: float, align_right: bool) -> str:
    pal = _rating_palette(avg_val)
    w = 206
    tx = x - w if align_right else x
    rx_num = 42 if align_right else 164
    lx = 82 if align_right else 124
    dx = 188 if align_right else 18
    anc = "end" if align_right else "start"
    bar_x = 200 if align_right else 1
    col = str(team.get("color") or "#E62E45")
    return (
        f'<g transform="translate({f1(tx)},{f1(y)})" style="filter:drop-shadow(0 12px 24px rgba(0,0,0,0.72))">'
        f'<rect width="206" height="64" rx="15" fill="rgba(5,11,26,0.9)" stroke="{col}" stroke-opacity=".46" stroke-width="1.4"/>'
        f'<rect x="{bar_x}" y="11" width="5" height="42" rx="2.5" fill="{col}"/>'
        f'<line x1="{lx}" y1="12" x2="{lx}" y2="52" stroke="rgba(255,255,255,0.12)" stroke-width="1.2"/>'
        f'<text x="{rx_num}" y="43" text-anchor="middle" fill="{pal["bg"]}" font-family="Vazirmatn,Space Grotesk,sans-serif" font-weight="900" font-size="33">{esc(fa(f1(avg_val)))}</text>'
        f'<text x="{dx}" y="27" text-anchor="{anc}" fill="#FFFFFF" font-family="Space Grotesk,sans-serif" font-weight="800" font-size="14" letter-spacing="0.8">{esc(team.get("code", ""))} • {esc(team.get("formation", ""))}</text>'
        f'<text x="{dx}" y="48" text-anchor="{anc}" fill="#94A3B8" font-family="Vazirmatn,sans-serif" font-weight="700" font-size="13">میانگین تیم</text>'
        f'</g>'
    )


def _player_node_svg(
    pl: dict[str, Any],
    cx: float,
    cy: float,
    color: str,
    secondary: str,
    *,
    is_zoom: bool,
    kit_mode: bool,
    fx_mode: bool,
) -> str:
    rat = float(pl.get("rating") or 6.5)
    pal = _rating_palette(rat)
    sc = 1.38 if is_zoom else 1.06
    is_motm = bool(pl.get("motm"))
    g_cnt = int(pl.get("g") or 0)
    a_cnt = int(pl.get("a") or 0)
    yc = bool(pl.get("yc"))
    rc = bool(pl.get("rc"))
    sub = bool(pl.get("sub"))
    name = str(pl.get("name") or "")
    num = str(pl.get("num") or "")
    pos = str(pl.get("pos") or "")

    aura = f'<ellipse cx="{f1(cx)}" cy="{f1(cy + 25 * sc)}" rx="{f1(22 * sc)}" ry="{f1(6.5 * sc)}" fill="#000" fill-opacity=".55"/>'
    if is_motm:
        rays = []
        for idx in range(12):
            ang = idx * 30 * math.pi / 180.0
            r1 = 33 * sc
            r2 = (44 if idx % 2 == 0 else 39) * sc
            rays.append(
                f'<line x1="{f1(cx + r1 * math.cos(ang))}" y1="{f1(cy + r1 * math.sin(ang))}" '
                f'x2="{f1(cx + r2 * math.cos(ang))}" y2="{f1(cy + r2 * math.sin(ang))}" '
                f'stroke="#FBBF24" stroke-opacity=".6" stroke-width="1.6" stroke-linecap="round"/>'
            )
        aura += (
            f'<circle cx="{f1(cx)}" cy="{f1(cy)}" r="{f1(50 * sc)}" fill="url(#motmGlow)"/>'
            + "".join(rays)
            + f'<circle cx="{f1(cx)}" cy="{f1(cy)}" r="{f1(31 * sc)}" fill="none" stroke="#FDE68A" stroke-width="2" stroke-dasharray="6 4"/>'
            f'<g transform="translate({f1(cx)},{f1(cy - 36 * sc)})">'
            f'<path d="M-11,4 L-8,-6 L-3,0 L0,-8 L3,0 L8,-6 L11,4 Z" fill="#FBBF24" stroke="#050B1A" stroke-width="1.2" stroke-linejoin="round"/></g>'
        )
    elif fx_mode and rat >= 8.2:
        aura += f'<circle cx="{f1(cx)}" cy="{f1(cy)}" r="{f1(36 * sc)}" fill="{pal["bg"]}" fill-opacity=".16"/>'

    kit_c = "#182438" if int(pl.get("line") or 0) == 0 else color
    trim_c = "#34D399" if int(pl.get("line") or 0) == 0 else secondary
    ink = contrast_ink(kit_c)

    if kit_mode:
        body = (
            f'<g transform="translate({f1(cx)},{f1(cy)}) scale({sc})" style="filter:drop-shadow(0 10px 16px rgba(0,0,0,0.78))">'
            f'<path d="M-12,-22 L-6,-24 C-3,-18 3,-18 6,-24 L12,-22 L27,-11 L21,3 L15,-1 L15,22 C15,24 13,25 11,25 L-11,25 C-13,25 -15,24 -15,22 L-15,-1 L-21,3 L-27,-11 Z" fill="{kit_c}" stroke="rgba(255,255,255,0.28)" stroke-width="1.4" stroke-linejoin="round"/>'
            f'<path d="M-15,-1 L-21,3 L-27,-11 L-12,-22 L-10,-15 Z" fill="{trim_c}" fill-opacity=".32"/>'
            f'<path d="M15,-1 L21,3 L27,-11 L12,-22 L10,-15 Z" fill="{trim_c}" fill-opacity=".32"/>'
            f'<path d="M-12,-22 L12,-22 L15,0 L-15,0 Z" fill="#ffffff" fill-opacity=".07"/>'
            f'<path d="M-6,-24 C-3,-17 3,-17 6,-24" fill="none" stroke="{trim_c}" stroke-width="2.8" stroke-linecap="round"/>'
            f'<text x="0" y="10" text-anchor="middle" fill="{ink}" font-family="Space Grotesk,JetBrains Mono,sans-serif" font-weight="800" font-size="18.5" letter-spacing="-0.5">{esc(num)}</text></g>'
        )
    else:
        body = (
            f'<g style="filter:drop-shadow(0 10px 16px rgba(0,0,0,0.78))">'
            f'<circle cx="{f1(cx)}" cy="{f1(cy)}" r="{f1(22 * sc)}" fill="#081229" stroke="{kit_c}" stroke-width="{f1(3.5 * sc)}"/>'
            f'<circle cx="{f1(cx)}" cy="{f1(cy)}" r="{f1(17 * sc)}" fill="{kit_c}" fill-opacity=".26"/>'
            f'<text x="{f1(cx)}" y="{f1(cy + 6.5 * sc)}" text-anchor="middle" fill="#FFFFFF" font-family="Space Grotesk,JetBrains Mono,sans-serif" font-weight="800" font-size="{f1(18 * sc)}">{esc(num)}</text></g>'
        )

    pw = 56 if is_zoom else 46
    ph = 26 if is_zoom else 22
    px = cx + (16 if is_zoom else 12)
    py = cy - (35 if is_zoom else 28)

    badges = ""
    bx = cx - (33 if is_zoom else 27)
    by = cy - (20 if is_zoom else 16)
    if g_cnt > 0:
        br = 11.5 if is_zoom else 9.5
        badges += (
            f'<g transform="translate({f1(bx)},{f1(by)})"><circle r="{br}" fill="#050C1C" stroke="#34D399" stroke-width="1.8"/>'
            f'<text y="{4.5 if is_zoom else 3.5}" text-anchor="middle" fill="#34D399" font-size="{12 if is_zoom else 10}">⚽</text>'
            + (f'<circle cx="9.5" cy="-8.5" r="6.5" fill="#10B981"/><text x="9.5" y="-5" text-anchor="middle" fill="#04140E" font-family="Space Grotesk" font-size="9" font-weight="900">{g_cnt}</text>' if g_cnt > 1 else "")
            + "</g>"
        )
        by += 23 if is_zoom else 19
    if a_cnt > 0:
        br = 11.5 if is_zoom else 9.5
        badges += (
            f'<g transform="translate({f1(bx)},{f1(by)})"><circle r="{br}" fill="#050C1C" stroke="#38BDF8" stroke-width="1.8"/>'
            f'<text y="{4 if is_zoom else 3.2}" text-anchor="middle" fill="#38BDF8" font-family="Space Grotesk" font-size="{10.5 if is_zoom else 9}" font-weight="900">A{a_cnt if a_cnt > 1 else ""}</text></g>'
        )
    if yc:
        badges += f'<rect x="{f1(cx + 20 * sc)}" y="{f1(cy + 8 * sc)}" width="{10 if is_zoom else 8.5}" height="{14 if is_zoom else 11.5}" rx="2" fill="#FBBF24" stroke="#050C1C" stroke-width="1.4" transform="rotate(8 {f1(cx + 24 * sc)} {f1(cy + 13 * sc)})"/>'
    if rc:
        badges += f'<rect x="{f1(cx + 20 * sc)}" y="{f1(cy + 8 * sc)}" width="{10 if is_zoom else 8.5}" height="{14 if is_zoom else 11.5}" rx="2" fill="#F43F5E" stroke="#050C1C" stroke-width="1.4" transform="rotate(8 {f1(cx + 24 * sc)} {f1(cy + 13 * sc)})"/>'
    if sub:
        badges += (
            f'<circle cx="{f1(cx - 22 * sc)}" cy="{f1(cy + 16 * sc)}" r="{9 if is_zoom else 7.5}" fill="#070D1D" stroke="#94A3B8" stroke-width="1.4"/>'
            f'<text x="{f1(cx - 22 * sc)}" y="{f1(cy + 19.5 * sc)}" text-anchor="middle" fill="#CBD5E1" font-size="{10 if is_zoom else 8.5}" font-weight="900">⇄</text>'
        )

    nw = max(118 if is_zoom else 92, len(name) * (11 if is_zoom else 8.8) + 22)
    nh = 29 if is_zoom else 23
    ny = cy + (36 if is_zoom else 28)
    pill_fill = "url(#goldPill)" if is_motm else pal["bg"]

    return (
        f'<g>{aura}{body}'
        f'<rect x="{f1(px)}" y="{f1(py)}" width="{pw}" height="{ph}" rx="{ph / 2}" fill="{pill_fill}" stroke="#050C1C" stroke-width="2"/>'
        f'<text x="{f1(px + pw / 2)}" y="{f1(py + 0.72 * ph)}" text-anchor="middle" fill="{pal["fg"]}" font-family="Vazirmatn,Space Grotesk,sans-serif" font-weight="900" font-size="{17.5 if is_zoom else 14.5}">{esc(fa(f1(rat)))}</text>'
        f'{badges}'
        f'<rect x="{f1(cx - nw / 2)}" y="{f1(ny)}" width="{f1(nw)}" height="{nh}" rx="7.5" fill="rgba(4,10,24,0.92)" stroke="{"rgba(251,191,36,0.75)" if is_motm else "rgba(255,255,255,0.16)"}" stroke-width="1.2"/>'
        f'<text x="{f1(cx)}" y="{f1(ny + 0.71 * nh)}" text-anchor="middle" fill="{"#FDE68A" if is_motm else "#F8FAFC"}" font-family="Vazirmatn,sans-serif" font-weight="800" font-size="{17 if is_zoom else 14}">{esc(name)}</text>'
        + (f'<text x="{f1(cx)}" y="{f1(ny + nh + 15)}" text-anchor="middle" fill="#94A3B8" font-family="Space Grotesk,monospace" font-weight="700" font-size="12">{esc(pos)}</text>' if is_zoom else "")
        + "</g>"
    )


def _render_hero(item: dict[str, Any], header_mode: str, is_wide: bool) -> str:
    h = item.get("home") or {}
    a = item.get("away") or {}
    hc = ensure_dark_bg_contrast(str(h.get("color") or "#EF0107"), bg="#0D1730", min_ratio=4.2)
    ac = ensure_dark_bg_contrast(str(a.get("color") or "#38BDF8"), bg="#0D1730", min_ratio=4.2)
    hg = fa(item.get("homeGoals", 0))
    ag = fa(item.get("awayGoals", 0))
    hxg = fa(f2(item["homeXg"])) if item.get("homeXg") is not None else "—"
    axg = fa(f2(item["awayXg"])) if item.get("awayXg") is not None else "—"

    if header_mode == "compact":
        return (
            f'<div class="score-hero pr-hero-compact">'
            f'<div class="fi pr-g10">{_crest_svg(h, "hc", 46)}<span class="pr-c-name">{esc(h.get("name", ""))}</span></div>'
            f'<div class="pr-c-score"><span style="color:{hc}">{hg}</span><span class="pr-dash">–</span><span style="color:{ac}">{ag}</span></div>'
            f'<div class="fi pr-g10"><span class="pr-c-name">{esc(a.get("name", ""))}</span>{_crest_svg(a, "ac", 46)}</div>'
            f'</div>'
        )

    csz = 70 if is_wide else 78
    xg_row = (
        f'<div class="pr-xg-row fm"><span style="color:{hc}">{hxg}</span><span class="pr-xg-lbl">xG</span><span style="color:{ac}">{axg}</span></div>'
        if (item.get("homeXg") is not None or item.get("awayXg") is not None)
        else ""
    )
    return (
        f'<div class="score-hero">'
        f'<div class="pr-dot-overlay"></div>'
        f'<div class="pr-hero-grad" style="background:linear-gradient(100deg,{hc}2c 0%,transparent 36%,transparent 64%,{ac}2c 100%)"></div>'
        f'<div class="pr-hero-bar" style="background:linear-gradient(90deg,{ac},#E62E45,{hc})"></div>'
        f'<div class="pr-hero-grid">'
        f'<div class="pr-side pr-side-r">{_crest_svg(h, "h", csz)}<div class="pr-minw-0"><div class="pr-tname">{esc(h.get("name", ""))}</div>'
        f'<div class="pr-scorers">{esc(fa(item.get("homeScorers") or "—"))}</div>'
        + (f'<div class="pr-coach">{esc(h.get("coach"))}</div>' if h.get("coach") else "") + '</div></div>'
        f'<div class="pr-center"><div class="pr-score-box">'
        f'<span class="pr-score-num" style="color:{hc};text-shadow:0 0 26px {hc}77">{hg}</span>'
        f'<span class="pr-dash">–</span>'
        f'<span class="pr-score-num" style="color:{ac};text-shadow:0 0 26px {ac}77">{ag}</span>'
        f'</div>{xg_row}</div>'
        f'<div class="pr-side pr-side-l"><div class="pr-minw-0 pr-tl"><div class="pr-tname">{esc(a.get("name", ""))}</div>'
        f'<div class="pr-scorers">{esc(fa(item.get("awayScorers") or "—"))}</div>'
        + (f'<div class="pr-coach">{esc(a.get("coach"))}</div>' if a.get("coach") else "") + f'</div>{_crest_svg(a, "a", csz)}</div>'
        f'</div></div>'
    )


def _render_pitch_module(
    item: dict[str, Any],
    *,
    pitch_mode: str,
    theme: str,
    kit_mode: bool,
    fx_mode: bool,
    span_cls: str,
) -> str:
    h = item.get("home") or {}
    a = item.get("away") or {}
    hc = str(h.get("color") or "#EF0107")
    ac = str(a.get("color") or "#38BDF8")
    is_both = pitch_mode == "both"
    W = 980
    H = 836 if is_both else 700
    pad_x, pad_y = 20, 18
    pw, ph = W - 2 * pad_x, H - 2 * pad_y
    _, t0, t1, t2 = RATINGS_THEMES.get(theme, RATINGS_THEMES["turf"])

    def _coords(xi: list[dict[str, Any]], ys: list[int], mirror: bool) -> list[dict[str, Any]]:
        res = []
        mx = 84 if is_both else 104
        for pl in xi:
            col_v = float(pl.get("col", 0.5))
            x = pad_x + mx + ((1.0 - col_v) if mirror else col_v) * (pw - 2 * mx)
            ln = max(0, min(3, int(pl.get("line", 2))))
            res.append({"x": x, "y": ys[ln], "p": pl})
        return res

    def _links_svg(pts: list[dict[str, Any]], links: list[list[int]], col: str) -> str:
        if not fx_mode or not links:
            return ""
        out = []
        for pair in links:
            if len(pair) != 2:
                continue
            i1, i2 = int(pair[0]), int(pair[1])
            if 0 <= i1 < len(pts) and 0 <= i2 < len(pts):
                p1, p2 = pts[i1], pts[i2]
                mx = (p1["x"] + p2["x"]) / 2.0
                my = (p1["y"] + p2["y"]) / 2.0 - 16.0
                out.append(
                    f'<path d="M{f1(p1["x"])} {f1(p1["y"])} Q{f1(mx)} {f1(my)} {f1(p2["x"])} {f1(p2["y"])}" '
                    f'stroke="{col}" stroke-opacity=".38" stroke-width="2.6" stroke-dasharray="7 5" fill="none"/>'
                )
        return "".join(out)

    def _heat_svg(pts: list[dict[str, Any]], col: str) -> str:
        if not fx_mode:
            return ""
        out = []
        for pt in pts:
            rat = float(pt["p"].get("rating") or 0)
            if rat >= 8.0:
                is_m = bool(pt["p"].get("motm"))
                r = 105 if is_m else (82 if rat >= 8.5 else 62)
                c_fill = "#FBBF24" if is_m else col
                op = ".24" if is_m else ".14"
                out.append(f'<circle cx="{f1(pt["x"])}" cy="{f1(pt["y"])}" r="{r}" fill="{c_fill}" fill-opacity="{op}" filter="url(#softBlur)"/>')
        return "".join(out)

    nodes_html, heat_html, links_html, badges_html = "", "", "", ""
    if is_both:
        c_h = _coords(h.get("xi") or [], [72, 168, 270, 366], False)
        c_a = _coords(a.get("xi") or [], [764, 668, 566, 470], True)
        heat_html = _heat_svg(c_h, hc) + _heat_svg(c_a, ac)
        links_html = _links_svg(c_h, h.get("links") or [], hc) + _links_svg(c_a, a.get("links") or [], ac)
        nodes_html = "".join(
            _player_node_svg(pt["p"], pt["x"], pt["y"], hc, str(h.get("secondary") or "#FFF"), is_zoom=False, kit_mode=kit_mode, fx_mode=fx_mode)
            for pt in c_h
        ) + "".join(
            _player_node_svg(pt["p"], pt["x"], pt["y"], ac, str(a.get("secondary") or "#FFF"), is_zoom=False, kit_mode=kit_mode, fx_mode=fx_mode)
            for pt in c_a
        )
        badges_html = _avg_badge_svg(h, _avg_rating(h.get("xi") or []), pad_x + 16, pad_y + 14, False) + _avg_badge_svg(
            a, _avg_rating(a.get("xi") or []), W - pad_x - 16, H - pad_y - 76, True
        )
        fc_tl, fc_br = hc, ac
    else:
        side = h if pitch_mode == "home" else a
        scol = hc if pitch_mode == "home" else ac
        pts = _coords(side.get("xi") or [], [598, 452, 290, 128], False)
        heat_html = _heat_svg(pts, scol)
        links_html = _links_svg(pts, side.get("links") or [], scol)
        nodes_html = "".join(
            _player_node_svg(pt["p"], pt["x"], pt["y"], scol, str(side.get("secondary") or "#FFF"), is_zoom=True, kit_mode=kit_mode, fx_mode=fx_mode)
            for pt in pts
        )
        badges_html = _avg_badge_svg(side, _avg_rating(side.get("xi") or []), pad_x + 18, pad_y + 16, False)
        fc_tl = fc_br = scol

    stripes = "".join(
        f'<rect x="{pad_x}" y="{f1(pad_y + idx * ph / 12.0)}" width="{pw}" height="{f1(ph / 12.0)}" fill="#ffffff" fill-opacity=".028"/>'
        for idx in range(0, 12, 2)
    )

    return (
        f'<div class="pitch-shell {span_cls}" dir="ltr">'
        f'<svg class="pr-pitch-svg" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet" fill="none">'
        f'<defs>'
        f'<linearGradient id="pitchBase" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="{t0}"/><stop offset="50%" stop-color="{t1}"/><stop offset="100%" stop-color="{t2}"/></linearGradient>'
        f'<linearGradient id="goldPill" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#FEF08A"/><stop offset="100%" stop-color="#F59E0B"/></linearGradient>'
        f'<radialGradient id="floodTL" cx="8%" cy="4%" r="60%"><stop offset="0%" stop-color="{fc_tl}" stop-opacity=".30"/><stop offset="100%" stop-color="{fc_tl}" stop-opacity="0"/></radialGradient>'
        f'<radialGradient id="floodBR" cx="92%" cy="96%" r="60%"><stop offset="0%" stop-color="{fc_br}" stop-opacity=".30"/><stop offset="100%" stop-color="{fc_br}" stop-opacity="0"/></radialGradient>'
        f'<linearGradient id="midBeam" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="{fc_tl}" stop-opacity=".55"/><stop offset="50%" stop-color="#ffffff" stop-opacity=".35"/><stop offset="100%" stop-color="{fc_br}" stop-opacity=".55"/></linearGradient>'
        f'<radialGradient id="motmGlow" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="#FBBF24" stop-opacity=".58"/><stop offset="52%" stop-color="#F59E0B" stop-opacity=".20"/><stop offset="100%" stop-color="#F59E0B" stop-opacity="0"/></radialGradient>'
        f'<filter id="softBlur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="18"/></filter>'
        f'</defs>'
        f'<rect x="{pad_x}" y="{pad_y}" width="{pw}" height="{ph}" rx="20" fill="url(#pitchBase)" stroke="rgba(255,255,255,0.18)" stroke-width="2"/>'
        f'<rect x="{pad_x}" y="{pad_y}" width="{pw}" height="{ph}" rx="20" fill="url(#floodTL)"/>'
        f'<rect x="{pad_x}" y="{pad_y}" width="{pw}" height="{ph}" rx="20" fill="url(#floodBR)"/>'
        f'{stripes}'
        f'<circle cx="{W / 2}" cy="{H / 2}" r="145" stroke="#ffffff" stroke-opacity=".045" stroke-width="1.2" stroke-dasharray="4 6"/>'
        f'<text x="{W / 2}" y="{H / 2 + 16}" text-anchor="middle" fill="#ffffff" fill-opacity=".042" font-family="Space Grotesk" font-weight="800" font-size="52" letter-spacing="10">XGPEDIA</text>'
        f'<g stroke="rgba(255,255,255,0.17)" stroke-width="1.8">'
        f'<line x1="{pad_x}" y1="{H / 2}" x2="{W - pad_x}" y2="{H / 2}" stroke="url(#midBeam)" stroke-width="2.2"/>'
        f'<circle cx="{W / 2}" cy="{H / 2}" r="76"/><circle cx="{W / 2}" cy="{H / 2}" r="5" fill="rgba(255,255,255,0.4)"/>'
        f'<rect x="{W / 2 - 190}" y="{pad_y}" width="380" height="122"/><rect x="{W / 2 - 86}" y="{pad_y}" width="172" height="46"/>'
        f'<path d="M{W / 2 - 64} {pad_y + 122} A72 72 0 0 0 {W / 2 + 64} {pad_y + 122}"/>'
        f'<rect x="{W / 2 - 190}" y="{H - pad_y - 122}" width="380" height="122"/><rect x="{W / 2 - 86}" y="{H - pad_y - 46}" width="172" height="46"/>'
        f'<path d="M{W / 2 - 64} {H - pad_y - 122} A72 72 0 0 1 {W / 2 + 64} {H - pad_y - 122}"/>'
        f'<path d="M{pad_x + 20} {pad_y} A20 20 0 0 1 {pad_x} {pad_y + 20}"/>'
        f'<path d="M{W - pad_x - 20} {pad_y} A20 20 0 0 0 {W - pad_x} {pad_y + 20}"/>'
        f'<path d="M{pad_x + 20} {H - pad_y} A20 20 0 0 0 {pad_x} {H - pad_y - 20}"/>'
        f'<path d="M{W - pad_x - 20} {H - pad_y} A20 20 0 0 1 {W - pad_x} {H - pad_y - 20}"/>'
        f'</g>{badges_html}{heat_html}{links_html}{nodes_html}</svg></div>'
    )


def _render_subs_module(item: dict[str, Any], pitch_mode: str, span_cls: str) -> str:
    h = item.get("home") or {}
    a = item.get("away") or {}
    hc = ensure_dark_bg_contrast(str(h.get("color") or "#EF0107"), bg="#0D1730", min_ratio=4.2)
    ac = ensure_dark_bg_contrast(str(a.get("color") or "#38BDF8"), bg="#0D1730", min_ratio=4.2)
    show_h = pitch_mode in ("both", "home") and bool(h.get("subs"))
    show_a = pitch_mode in ("both", "away") and bool(a.get("subs"))

    def _box(team: dict[str, Any], col: str) -> str:
        cards = []
        for s in (team.get("subs") or [])[:3]:
            pal = _rating_palette(float(s.get("rating") or 6.5))
            cards.append(
                f'<div class="pr-sub-item"><div class="pr-minw-0"><div class="pr-sub-name">{esc(s.get("name", ""))}</div>'
                f'<div class="pr-sub-meta"><span>⇄ {esc(fa(s.get("min", "")))}</span>'
                f'{"<span style=color:#6EE7B7>⚽</span>" if s.get("g") else ""}'
                f'{"<span style=color:#7DD3FC>A</span>" if s.get("a") else ""}</div></div>'
                f'<span class="pr-sub-rat" style="background:{pal["bg"]};color:{pal["fg"]}">{esc(fa(f1(float(s.get("rating") or 6.5))))}</span></div>'
            )
        return (
            f'<div class="pr-sub-box" style="border-right:4px solid {col}">'
            f'<div class="pr-sub-hdr" style="color:{col}">تعویضی‌های {esc(team.get("name", ""))}</div>'
            f'<div class="pr-sub-grid">{"".join(cards)}</div></div>'
        )

    inner = (_box(h, hc) if show_h else "") + (_box(a, ac) if show_a else "")
    return f'<div class="pr-subs-wrap {span_cls}">{inner}</div>'


def _render_ranking_module(item: dict[str, Any], span_cls: str) -> str:
    h = item.get("home") or {}
    a = item.get("away") or {}
    hc = ensure_dark_bg_contrast(str(h.get("color") or "#EF0107"), bg="#0D1730", min_ratio=4.2)
    ac = ensure_dark_bg_contrast(str(a.get("color") or "#38BDF8"), bg="#0D1730", min_ratio=4.2)

    def _col(team: dict[str, Any], col: str) -> str:
        xi = sorted(team.get("xi") or [], key=lambda p: float(p.get("rating") or 0), reverse=True)
        rows = []
        for pl in xi:
            rat = float(pl.get("rating") or 6.5)
            pal = _rating_palette(rat)
            g_b = f'<span style="color:#6EE7B7;font-size:12.5px">⚽{fa(pl["g"]) if int(pl["g"]) > 1 else ""}</span>' if pl.get("g") else ""
            a_b = f'<span style="color:#7DD3FC;font-size:12.5px">A{fa(pl["a"]) if int(pl["a"]) > 1 else ""}</span>' if pl.get("a") else ""
            m_b = '<span style="color:#FBBF24;font-size:14px">★</span>' if pl.get("motm") else ""
            rows.append(
                f'<div class="pr-rk-row"><div class="fi pr-g8 pr-minw-0">'
                f'<span class="fm pr-rk-num">#{esc(pl.get("num", ""))}</span>'
                f'<span class="pr-rk-name">{esc(pl.get("name", ""))}</span>'
                f'<span class="fm pr-rk-pos">{esc(pl.get("pos", ""))}</span>{m_b}{g_b}{a_b}</div>'
                f'<span class="pr-rk-pill" style="background:{pal["bg"]};color:{pal["fg"]}">{esc(fa(f1(rat)))}</span></div>'
            )
        return (
            f'<div class="pr-rk-col"><div class="fbw pr-rk-hdr">'
            f'<span class="pr-rk-team" style="color:{col}">{esc(team.get("name", ""))}</span>'
            f'<span class="fm pr-rk-avg">AVG {esc(fa(f1(_avg_rating(xi))))}</span></div>{"".join(rows)}</div>'
        )

    return (
        f'<div class="xm pr-grow {span_cls}">'
        + _mod_hdr("رده‌بندی کامل نمرات بازیکنان", '<span class="fm pr-sub-tag">FULL SQUAD RATINGS</span>', "#34D399")
        + f'<div class="pr-rk-grid">{_col(h, hc)}{_col(a, ac)}</div></div>'
    )


def _render_verdict_module(item: dict[str, Any], span_cls: str) -> str:
    v = item.get("verdict") if isinstance(item.get("verdict"), dict) else {}
    return (
        f'<div class="xe pr-shrink {span_cls}">'
        f'<svg class="pr-verd-wm" viewBox="0 0 240 160" fill="none" stroke="#DCE6F8" stroke-width="2.5">'
        f'<rect x="2" y="2" width="236" height="156" rx="8"/><line x1="120" y1="2" x2="120" y2="158"/><circle cx="120" cy="80" r="32"/></svg>'
        f'<div class="pr-verd-in"><div>'
        + _mod_hdr("جمع‌بندی تحریریه XGPedia", '<span class="fm pr-verd-tag-top">POST-MATCH LENS</span>', "#F59E0B")
        + f'<h4 class="pr-verd-title">{esc(fa(v.get("title", "")))}</h4>'
        f'<p class="pr-verd-body">{esc(fa(v.get("body", "")))}</p></div>'
        f'<div class="pr-verd-foot"><span class="pr-dot-red"></span><span>{esc(fa(v.get("tag", "")))}</span></div>'
        f'</div></div>'
    )


@with_sample_badge
def render_players_rating_html(
    item: dict[str, Any],
    *,
    slide: str = RATINGS_DEFAULT_SLIDE,
    header_mode: str = RATINGS_DEFAULT_HEADER,
    fmt: str = "4:5",
    pitch_mode: str | None = None,
    theme: str = "turf",
    kit_mode: bool = True,
    fx_mode: bool = True,
    enabled_modules: list[str] | None = None,
    custom_modules: list[dict[str, Any]] | None = None,
) -> str:
    """تولید HTML کامل و ۱۰۰٪ آفلاین کارت ماژولار نمرات بازیکنان (D51)."""
    w, h = RATINGS_FORMATS.get(fmt, RATINGS_FORMATS["4:5"])
    is_wide = fmt == "16:9"
    is_story = fmt == "9:16"
    sl_meta = next((s for s in RATINGS_SLIDES if s[0] == slide), RATINGS_SLIDES[0])
    pm = pitch_mode or sl_meta[2]

    if custom_modules is not None:
        mods = [dict(m) for m in custom_modules if m.get("enabled")]
    else:
        all_mods, _ = get_players_rating_modules(item, slide)
        if enabled_modules is not None:
            eset = set(enabled_modules)
            mods = [m for m in all_mods if m["id"] in eset]
        else:
            mods = [m for m in all_mods if m["enabled"]]

    # رفع نصفه‌ماندن ماژول نیم‌عرض فرد
    spans: list[str] = []
    half_run = 0
    for idx, m in enumerate(mods):
        if m.get("span") != "half" or not m.get("can_half", False):
            half_run = 0
            spans.append("pr-span-full")
        else:
            half_run += 1
            nxt_half = (idx + 1 < len(mods)) and (mods[idx + 1].get("span") == "half") and mods[idx + 1].get("can_half", False)
            if not nxt_half and half_run % 2 == 1:
                half_run = 0
                spans.append("pr-span-full")
            else:
                spans.append("pr-span-half")

    mods_html = ""
    for m, sc in zip(mods, spans):
        mid = m["id"]
        if mid == "pitch":
            mods_html += _render_pitch_module(item, pitch_mode=pm, theme=theme, kit_mode=kit_mode, fx_mode=fx_mode, span_cls=sc)
        elif mid == "subs":
            mods_html += _render_subs_module(item, pm, sc)
        elif mid == "ranking":
            mods_html += _render_ranking_module(item, sc)
        elif mid == "verdict":
            mods_html += _render_verdict_module(item, sc)

    hero_html = _render_hero(item, header_mode, is_wide)
    hm_team = item.get("home") or {}
    aw_team = item.get("away") or {}
    hc = str(hm_team.get("color") or "#EF0107")
    ac = str(aw_team.get("color") or "#38BDF8")
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
.pr-canvas{{position:relative;width:{w}px;height:{h}px;background:#0D1730;overflow:hidden;display:flex;flex-direction:column;justify-content:space-between;padding:{pad_top} 0 {pad_bot}}}
.pr-ambient{{position:absolute;inset:0;pointer-events:none;z-index:0;background:radial-gradient(circle at 86% 20%,{hc}3c,transparent 46%),radial-gradient(circle at 14% 20%,{ac}3c,transparent 46%),radial-gradient(circle at 50% 62%,{"#f59e0b22" if theme == "gold" else "#e62e451c"},transparent 55%)}}
.pr-bg-svg{{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0}}
.pr-scan{{position:absolute;inset:0;pointer-events:none;z-index:0;background:repeating-linear-gradient(to bottom,rgba(255,255,255,.015) 0 1px,transparent 1px 4px)}}
.pr-header{{position:relative;z-index:10;padding:12px 36px 8px;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-shrink:0}}
.pr-comp-pill{{padding:4px 16px;border-radius:999px;font-size:21px;font-weight:900;display:flex;align-items:center;gap:8px;border:1px solid rgba(255,255,255,.18);background:rgba(21,35,71,.9);color:#F8FAFC}}
.pr-round-pill{{padding:4px 16px;border-radius:999px;font-size:19px;font-weight:800;border:1px solid rgba(230,46,69,.5);background:rgba(230,46,69,.18);color:#FF6B7F}}
.pr-meta-row{{display:flex;align-items:center;gap:10px;font-size:18px;font-weight:700;color:#E2E8F0;margin-top:6px}}
.pr-status-pill{{padding:2px 12px;border-radius:999px;background:rgba(16,185,129,.2);border:1px solid rgba(16,185,129,.45);color:#34D399;font-size:16px;font-weight:800}}
.pr-brand-img{{height:46px;width:auto;display:block}}.pr-brand-txt{{font-size:32px;font-weight:800;line-height:1}}
.pr-stage-v{{position:relative;z-index:10;flex:1;padding:8px 40px;display:flex;flex-direction:column;justify-content:space-between;gap:10px;overflow:hidden;min-height:0}}
.pr-stage-w{{position:relative;z-index:10;flex:1;padding:8px 40px;display:grid;grid-template-columns:5fr 7fr;gap:24px;align-items:stretch;overflow:hidden;min-height:0}}
.pr-mods-grid{{flex:1;display:grid;grid-template-columns:1fr 1fr;gap:10px;min-height:0;overflow:hidden;align-content:stretch}}
.pr-span-full{{grid-column:1 / -1;min-width:0}}.pr-span-half{{grid-column:span 1;min-width:0}}
.score-hero{{position:relative;border-radius:24px;background:linear-gradient(160deg,#112145ee 0%,#081126fa 56%,#050a17fc 100%);border:1.5px solid rgba(255,255,255,.15);overflow:hidden;padding:16px 24px;box-shadow:0 22px 54px -12px rgba(0,0,0,.77),inset 0 1px 0 rgba(255,255,255,.16);flex-shrink:0}}
.pr-hero-compact{{display:flex;align-items:center;justify-content:space-between;padding:10px 22px}}
.pr-c-name{{font-size:24px;font-weight:900;color:#fff}}.pr-c-score{{display:flex;align-items:center;gap:14px;font-size:36px;font-weight:900;padding:4px 18px;border-radius:14px;background:rgba(4,9,24,.9);border:1px solid rgba(255,255,255,.18)}}
.pr-dot-overlay{{position:absolute;inset:0;background-image:radial-gradient(rgba(255,255,255,.06) 1px,transparent 1px);background-size:20px 20px;opacity:.35;pointer-events:none}}
.pr-hero-grad{{position:absolute;inset:0;pointer-events:none}}.pr-hero-bar{{position:absolute;bottom:0;left:0;right:0;height:2px;opacity:.8}}
.pr-hero-grid{{position:relative;z-index:10;display:grid;grid-template-columns:4fr 3fr 4fr;align-items:center;gap:8px}}
.pr-side{{display:flex;align-items:center;gap:14px;min-width:0}}.pr-side-l{{justify-content:flex-end}}.pr-tl{{text-align:left}}.pr-minw-0{{min-width:0;flex:1}}
.pr-tname{{font-size:{"29px" if is_wide else "35px"};font-weight:900;color:#fff;line-height:1.05;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.pr-scorers{{font-size:15.5px;font-weight:700;color:#E2E8F0;margin-top:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.pr-coach{{font-size:14px;font-weight:700;color:#94A3B8;margin-top:3px}}
.pr-center{{display:flex;flex-direction:column;align-items:center;justify-content:center}}
.pr-score-box{{padding:8px 24px;border-radius:16px;background:rgba(4,9,24,.95);border:1px solid rgba(255,255,255,.2);display:flex;align-items:center;gap:16px;box-shadow:0 18px 40px rgba(0,0,0,.6)}}
.pr-score-num{{font-size:{"44px" if is_wide else "52px"};font-weight:900;line-height:1}}.pr-dash{{font-size:28px;font-weight:900;color:#64748B;line-height:1}}
.pr-xg-row{{display:flex;align-items:center;gap:10px;margin-top:6px;font-size:15px;font-weight:800;color:#CBD5E1}}.pr-xg-lbl{{color:#64748B}}
.pitch-shell{{position:relative;border-radius:26px;background:linear-gradient(175deg,#09162df2,#050b18fa);border:1.5px solid rgba(255,255,255,.15);overflow:hidden;display:flex;align-items:center;justify-content:center;min-height:0;box-shadow:0 26px 64px -14px rgba(0,0,0,.85),inset 0 1px 0 rgba(255,255,255,.16)}}
.pr-pitch-svg{{width:100%;height:100%;max-height:100%;display:block}}
.pr-subs-wrap{{display:flex;gap:12px;flex-shrink:0}}
.pr-sub-box{{flex:1;min-width:0;padding:10px 14px;border-radius:16px;background:rgba(7,17,38,.9);border:1px solid rgba(255,255,255,.12)}}
.pr-sub-hdr{{font-size:15.5px;font-weight:900;margin-bottom:6px}}.pr-sub-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}}
.pr-sub-item{{border-radius:12px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);padding:6px 10px;display:flex;align-items:center;justify-content:space-between;gap:6px;min-width:0}}
.pr-sub-name{{font-size:15px;font-weight:900;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.pr-sub-meta{{font-size:12px;font-weight:700;color:#94A3B8;display:flex;gap:4px}}
.pr-sub-rat{{padding:2px 8px;border-radius:8px;font-size:15px;font-weight:900;flex-shrink:0}}
.xm,.xe{{position:relative;border-radius:24px;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;box-shadow:0 20px 50px -12px rgba(0,0,0,.7),inset 0 1px 0 rgba(255,255,255,.12)}}
.xm{{background:linear-gradient(165deg,#0f1d3de0,#070f22f7);border:1.5px solid rgba(248,250,252,.14);padding:14px 20px}}
.xe{{background:linear-gradient(155deg,#13244aeb,#081022fa);border:1.5px solid rgba(127,166,232,.27);padding:18px 24px}}
.mh{{padding-bottom:8px;margin-bottom:10px;border-bottom:1px solid rgba(255,255,255,.12)}}.pr-mbar{{width:8px;height:24px;border-radius:99px;display:inline-block}}.mt{{font-size:23px;font-weight:900;color:#fff}}
.pr-g8{{gap:8px}}.pr-g10{{gap:10px}}.pr-sub-tag{{font-size:16px;font-weight:800;color:#CBD5E1}}
.pr-rk-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;flex:1;align-content:start}}.pr-rk-col{{display:flex;flex-direction:column;gap:6px;min-width:0}}
.pr-rk-hdr{{padding:0 8px 6px;border-bottom:1px solid rgba(255,255,255,.12)}}.pr-rk-team{{font-size:19px;font-weight:900}}.pr-rk-avg{{font-size:15px;font-weight:700;color:#CBD5E1}}
.pr-rk-row{{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:6px 12px;border-radius:12px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08)}}
.pr-rk-num{{font-size:13px;font-weight:700;color:#94A3B8;width:26px;text-align:center;flex-shrink:0}}.pr-rk-name{{font-size:17px;font-weight:800;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.pr-rk-pos{{font-size:12px;font-weight:700;color:#94A3B8;flex-shrink:0}}.pr-rk-pill{{padding:2px 10px;border-radius:8px;font-size:16px;font-weight:900;flex-shrink:0}}
.pr-verd-wm{{position:absolute;left:20px;bottom:16px;width:144px;opacity:.08;pointer-events:none}}.pr-verd-in{{position:relative;z-index:10;display:flex;flex-direction:column;justify-content:space-between;gap:10px}}
.pr-verd-tag-top{{font-size:17px;font-weight:800;color:#FCD34D}}.pr-verd-title{{font-size:24px;font-weight:900;color:#FCD34D;line-height:1.35;margin-bottom:6px}}.pr-verd-body{{font-size:20px;line-height:1.55;color:#F1F5F9;font-weight:600}}
.pr-verd-foot{{padding-top:10px;border-top:1px solid rgba(255,255,255,.12);display:flex;align-items:center;gap:8px;font-size:17px;font-weight:800;color:#fff}}.pr-dot-red{{width:10px;height:10px;border-radius:99px;background:#E62E45;flex-shrink:0}}
.pr-footer{{position:relative;z-index:10;padding:10px 44px 10px;flex-shrink:0}}.pr-foot-line{{border-top:1px solid rgba(255,255,255,.12);margin-bottom:8px}}
.pr-foot-tag{{font-size:17px;font-weight:800;letter-spacing:.14em;color:#F1F5F9;text-transform:uppercase}}.pr-foot-h{{font-size:19px;font-weight:800;color:#fff}}.pr-foot-s{{font-size:16px;font-weight:600;color:#CBD5E1}}

footer, footer .fbw, footer .cf-row, footer .fi, footer .cf-left, footer .cf-right, .xg-footer, .foot-row, .card-footer{{flex-wrap:nowrap!important;white-space:nowrap!important;min-width:0!important;}}
footer span, footer div, .pl-foot-tag, .pl-foot-s, .in-foot-tag, .pr-foot-tag, .st-foot-tag, .cf-tag{{white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;min-width:0!important;}}
</style>
</head>
<body>
<div class="pr-canvas">
  <div class="pr-ambient"></div>
  <svg class="pr-bg-svg" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid slice" fill="none">
    <defs>
      <pattern id="tg" width="54" height="54" patternUnits="userSpaceOnUse"><path d="M54 0H0v54" stroke="#F8FAFC" stroke-opacity=".042"/></pattern>
      <radialGradient id="rf" cx="50%" cy="20%" r="48%"><stop offset="0" stop-color="#E62E45" stop-opacity=".22"/><stop offset=".55" stop-color="#E62E45" stop-opacity=".05"/><stop offset="1" stop-color="#E62E45" stop-opacity="0"/></radialGradient>
    </defs>
    <rect width="100%" height="100%" fill="url(#tg)"/>
    <rect x="12" y="12" width="{w - 24}" height="{h - 24}" rx="18" stroke="#F8FAFC" stroke-opacity=".11" stroke-width="1.5"/>
    <line x1="{w / 2}" y1="12" x2="{w / 2}" y2="{h - 12}" stroke="#F8FAFC" stroke-opacity=".06" stroke-width="1.5" stroke-dasharray="8 8"/>
    <circle cx="{w / 2}" cy="220" r="260" fill="url(#rf)"/>
    <path d="{crh_d}" stroke="#E62E45" stroke-opacity=".62" stroke-width="2.4"/>
  </svg>
  <div class="pr-scan"></div>
  <header class="pr-header">
    <div class="fcol">
      <div class="fi pr-g10">
        <div class="pr-comp-pill">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#E62E45" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M8 21h8m-4-4v4m-5-17h10v5a5 5 0 01-10 0V4zM5 6H3v2a3 3 0 003 3h1m12-5h2v2a3 3 0 01-3 3h-1"/></svg>
          <span>{esc(item.get("competition", "مسابقه فوتبال"))}</span>
        </div>
        <span class="pr-round-pill">{esc(fa(item.get("round", "نمرات بازیکنان")))}</span>
      </div>
      <div class="pr-meta-row">
        <span>🏟 {esc(item.get("stadium", ""))}</span>
        <span class="pr-status-pill">{esc(item.get("statusTag", "پایان مسابقه"))}</span>
      </div>
    </div>
    {_brand_logo_html()}
  </header>
  <main class="{'pr-stage-w' if is_wide else 'pr-stage-v'}">
    {f'<section class="fcol" style="justify-content:center;gap:12px">{hero_html}</section><section class="pr-mods-grid">{mods_html}</section>' if is_wide else f'{hero_html}<section class="pr-mods-grid">{mods_html}</section>'}
  </main>
  <footer class="pr-footer">
    <div class="pr-foot-line"></div>
    <div class="fbw">
      <div class="fi pr-g10"><span class="pr-dot-red"></span><span dir="ltr" class="fm pr-foot-tag">{esc(item.get("leagueEn", "FOOTBALL"))} {esc(item.get("season", "26/27"))} {esc(item.get("weekCode", ""))} • PLAYERS RATING</span></div>
      <div class="fi pr-g10 fm" dir="ltr"><span class="pr-foot-h">@XGPedia</span><span style="color:#64748B">|</span><span class="pr-foot-s">{esc(item.get("source", "XGPedia Rating Engine"))}</span></div>
    </div>
  </footer>
</div>
</body>
</html>"""


def build_players_rating_caption(item: dict[str, Any]) -> str:
    """تولید کپشن فارسی تمیز و غیرتکراری برای کارت نمرات بازیکنان."""
    h = item.get("home") or {}
    a = item.get("away") or {}
    all_xi = (h.get("xi") or []) + (a.get("xi") or [])
    motm = max(all_xi, key=lambda p: (int(p.get("motm") or 0), float(p.get("rating") or 0)), default={})
    v = item.get("verdict") if isinstance(item.get("verdict"), dict) else {}

    parts = [
        f"⚽️ <b>نمرات بازیکنان | {esc(h.get('name', ''))} {fa(item.get('homeGoals', 0))}–{fa(item.get('awayGoals', 0))} {esc(a.get('name', ''))}</b>"
    ]
    if motm.get("name"):
        parts.append(f"⭐️ ستاره زمین (MOTM): {fa(motm['name'])} با نمره {fa(f1(float(motm.get('rating') or 0)))} از ۱۰")
    if item.get("homeXg") is not None and item.get("awayXg") is not None:
        parts.append(f"📊 امید گل (xG): {fa(f2(item['homeXg']))} در برابر {fa(f2(item['awayXg']))}")
    if v.get("body"):
        parts.append(fa(str(v["body"]).strip()))
    return "\n\n".join(parts)
