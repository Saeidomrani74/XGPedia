"""رندرر ۱۰۰٪ آفلاین و ۱:۱ کارت اسلایدی مناظره فوتبالی XGPedia (`Debate Studio — نسخه شوریل`).

۵ اسلاید استاندارد مطابق دقیق `debate.html`:
  - `slide1`: شکاف تاکتیکی (پوستر اصلی — THE RIFT)
  - `slide2`: رادار ۶ محوره و ضربه فنی (COURTROOM)
  - `slide3`: جلد مجله ادعای جنجالی (FRONT PAGE)
  - `slide4`: دوئل تمام‌صفحه رأی و تاج (THE VERDICT)
  - `slide5`: اتاق جنگ تاکتیکی (WAR ROOM)

استانداردهای دائمی XGPedia:
  - ۱۰۰٪ آفلاین (بدون CDN، فونت محلی Vazirmatn)
  - فریم چهارگوشه قرمز یکپارچه (`pad_top=24/22/139`, `pad_bot=20/16/171`)
  - فوتر تک‌خطی اجباری (`white-space:nowrap!important`)
  - لوگوی واقعی باشگاه‌های لیگ برتر (`pl_badges_free`) و رنگ‌های خوانا و متمایز (`ensure_dark_bg_contrast`)
"""
from __future__ import annotations

import math
from typing import Any

from src.xgpedia.render.card_kit.helpers import (
    with_sample_badge,
    contrast_ink,
    ensure_dark_bg_contrast,
    esc,
    fa,
)
from src.xgpedia.render.cards import _brand_logo_data_uri
from src.xgpedia.render.studio_engine import build_embedded_font_css

DEBATE_FORMATS: dict[str, tuple[int, int]] = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}

DEBATE_SLIDES: list[tuple[str, str, str]] = [
    ("slide1", "شکاف تاکتیکی (پوستر اصلی)", "full"),
    ("slide2", "رادار ۶ محوره و ضربه فنی", "full"),
    ("slide3", "جلد مجله ادعای جنجالی", "full"),
    ("slide4", "دوئل تمام‌صفحه رأی و تاج", "full"),
    ("slide5", "اتاق جنگ تاکتیکی", "full"),
]

_SLIDE_TO_LAYOUT: dict[str, str] = {
    "slide1": "clash",
    "slide2": "evidence",
    "slide3": "hottake",
    "slide4": "verdict",
    "slide5": "board",
    "clash": "clash",
    "evidence": "evidence",
    "hottake": "hottake",
    "verdict": "verdict",
    "board": "board",
}

_THEMES: dict[str, dict[str, str]] = {
    "classic": {"bg": "#0D1730", "accent": "#E62E45", "glow": "#e62e452b"},
    "pitch": {"bg": "#071122", "accent": "#10B981", "glow": "#10b98126"},
    "derby": {"bg": "#100A1C", "accent": "#F59E0B", "glow": "#f59e0b26"},
}

_MODULE_SPECS: list[tuple[str, str, bool]] = [
    ("pitch", "شکاف پلاسمای مورب و بافت زمین چمن", True),
    ("scan", "بافت اسکن‌لاین مانیتور پخش زنده", True),
    ("blindspot", "باکس چالش اصلی / نقطه کور", True),
    ("verdict", "نوار جمع‌بندی تحریریه XGPedia", True),
]


def get_debate_modules(item: dict[str, Any], slide: str = "slide1") -> tuple[list[dict[str, Any]], list[str]]:
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


def _hl_title(title: str, highlight: str | None) -> str:
    s = esc(title)
    hl = esc((highlight or "").strip())
    if not hl or hl not in s:
        return s
    i = s.index(hl)
    return f'{s[:i]}<span class="hl-slash">{hl}</span>{s[i + len(hl):]}'


def _side_badge(side: dict[str, Any], uid: str, size: int, color: str) -> str:
    sec = str(side.get("secondary") or "#FFFFFF")
    img = str(side.get("img") or "").strip()
    cd = str(side.get("code") or "XGP").strip().upper()[:3]
    sname = str(side.get("name") or "").strip()
    ent_type = str(side.get("entityType") or "").lower()
    is_team = ent_type == "team"
    try:
        from src.xgpedia.providers.pl_badges_free import get_pl_badge_data_uri, lookup_pl_club
        name_club_hit = lookup_pl_club(sname) if sname else None
        if name_club_hit is not None:
            is_team = True
    except Exception:
        name_club_hit = None

    # برای اشخاص (نه تیم‌ها): نمایش عکس پرتره دقیق
    if img and not is_team:
        return (
            f'<div style="position:relative;width:{size}px;height:{size}px;flex-shrink:0">'
            f'<div style="position:absolute;inset:-6px;border-radius:26px;border:1.5px dashed {color}88"></div>'
            f'<div style="width:100%;height:100%;border-radius:20px;padding:4px;background:linear-gradient(135deg,{color},{sec}66);'
            f'box-shadow:0 16px 34px -6px {color}77,0 12px 24px rgba(0,0,0,.55);overflow:hidden">'
            f'<img src="{img}" alt="{esc(sname)}" style="width:100%;height:100%;object-fit:cover;object-position:50% 18%;border-radius:16px;display:block"/>'
            f'</div></div>'
        )
    # لوگوی واقعی باشگاه لیگ برتر انگلیس (آفلاین از brand/crests یا کش رسمی)
    try:
        from src.xgpedia.providers.pl_badges_free import get_pl_badge_data_uri, lookup_pl_club
        info = name_club_hit or lookup_pl_club(cd, tla_hint=cd)
        if info and info[4]:
            uri = get_pl_badge_data_uri(info[1], tla_hint=info[1], badge_code=info[4], size=100 if size >= 70 else 70, fetch_network=False)
            if uri:
                return (
                    f'<div style="width:{size}px;height:{size}px;display:flex;align-items:center;justify-content:center;'
                    f'background:rgba(10,18,38,.78);border:2px solid {color}77;border-radius:20px;padding:7px;'
                    f'box-shadow:0 12px 26px {color}44;flex-shrink:0">'
                    f'<img src="{uri}" alt="{esc(cd)}" style="width:100%;height:100%;object-fit:contain;display:block"/>'
                    f'</div>'
                )
    except Exception:
        pass

    o = "M90 14L154 40V92C154 132 126 158 90 168C54 158 26 132 26 92V40Z"
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 180 180" fill="none" '
        f'style="filter:drop-shadow(0 14px 26px {color}55);flex-shrink:0">'
        f'<defs><linearGradient id="bg_{uid}" x1="20" y1="12" x2="160" y2="168" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{color}"/><stop offset=".7" stop-color="#0A152C"/><stop offset="1" stop-color="#040915"/></linearGradient>'
        f'<linearGradient id="bd_{uid}" x1="24" y1="16" x2="156" y2="164" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{sec}"/><stop offset=".5" stop-color="{color}"/><stop offset="1" stop-color="{sec}" stop-opacity=".55"/></linearGradient>'
        f'<clipPath id="cp_{uid}"><path d="{o}"/></clipPath></defs>'
        f'<circle cx="90" cy="90" r="84" stroke="{color}" stroke-opacity=".35" stroke-width="1.8" stroke-dasharray="5 7"/>'
        f'<path d="{o}" fill="{color}" fill-opacity=".28"/>'
        f'<g clip-path="url(#cp_{uid})"><rect x="20" y="10" width="140" height="162" fill="url(#bg_{uid})"/>'
        f'<path d="M18 124L162 54V82L18 152Z" fill="#fff" fill-opacity=".14"/>'
        f'<ellipse cx="90" cy="22" rx="68" ry="26" fill="#fff" fill-opacity=".20"/></g>'
        f'<path d="{o}" stroke="url(#bd_{uid})" stroke-width="5"/>'
        f'<rect x="40" y="66" width="100" height="48" rx="14" fill="#060c1ad9" stroke="{sec}" stroke-opacity=".6" stroke-width="2.2"/>'
        f'<text x="90" y="100" text-anchor="middle" fill="#fff" font-family="Space Grotesk,JetBrains Mono,sans-serif" font-weight="800" font-size="31" letter-spacing="2">{esc(cd)}</text>'
        f'<circle cx="90" cy="136" r="5.5" fill="{color}" stroke="#fff" stroke-width="2"/></svg>'
    )


def _waveform_svg(heat: int, ca: str, cb: str, w: int = 250, h: int = 28) -> str:
    d = max(0.45, min(1.0, (int(heat or 90)) / 100.0))
    vals = [.22,.35,.5,.3,.72,.92,.55,.84,1,.65,.48,.96,.78,.42,.88,1,.68,.52,.9,.74,.4,.82,.62,.45,.34,.5,.28,.18]
    step = w / len(vals)
    bars = []
    for idx, v in enumerate(vals):
        bh = max(4.0, v * d * (h - 4))
        y = (h - bh) / 2.0
        col = ca if idx < 14 else cb
        bars.append(f'<rect x="{idx * step + 1.5:.1f}" y="{y:.1f}" width="{max(2.0, step - 3.0):.1f}" height="{bh:.1f}" rx="3" fill="{col}" fill-opacity="{0.45 + 0.55 * v:.2f}"/>')
    return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" fill="none" style="flex-shrink:0">{"".join(bars)}</svg>'


def _heat_gauge_svg(heat: int, w: int = 210, h: int = 115) -> str:
    val = max(0, min(100, int(heat or 88)))
    ang = (val / 100.0 * 180.0 - 180.0) * math.pi / 180.0
    nx, ny = 120.0 + 68.0 * math.cos(ang), 104.0 + 68.0 * math.sin(ang)
    arc = 80.0 * math.pi
    dash = val / 100.0 * arc
    lbl = "انفجاری و داغ" if val >= 90 else ("جنجالی" if val >= 75 else "متعادل")
    ticks = []
    for k in range(11):
        a = (18 * k - 180) * math.pi / 180.0
        ticks.append(
            f'<line x1="{120 + 88 * math.cos(a):.1f}" y1="{104 + 88 * math.sin(a):.1f}" '
            f'x2="{120 + 94 * math.cos(a):.1f}" y2="{104 + 94 * math.sin(a):.1f}" stroke="#ffffff40" stroke-width="2" stroke-linecap="round"/>'
        )
    return (
        f'<svg width="{w}" height="{h}" viewBox="0 0 240 132" fill="none" style="flex-shrink:0">'
        f'<defs><linearGradient id="hg2" x1="40" y1="104" x2="200" y2="104" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="#38BDF8"/><stop offset=".5" stop-color="#F59E0B"/><stop offset="1" stop-color="#E62E45"/></linearGradient></defs>'
        f'{"".join(ticks)}'
        f'<path d="M 40 104 A 80 80 0 0 1 200 104" stroke="#ffffff1a" stroke-width="14" stroke-linecap="round"/>'
        f'<path d="M 40 104 A 80 80 0 0 1 200 104" stroke="url(#hg2)" stroke-width="14" stroke-linecap="round" stroke-dasharray="{dash:.1f} {arc:.1f}"/>'
        f'<line x1="120" y1="104" x2="{nx:.1f}" y2="{ny:.1f}" stroke="#FFFFFF" stroke-width="4" stroke-linecap="round"/>'
        f'<circle cx="120" cy="104" r="8" fill="#E62E45" stroke="#fff" stroke-width="3"/>'
        f'<text x="120" y="76" text-anchor="middle" fill="#FFFFFF" font-family="Vazirmatn,sans-serif" font-weight="900" font-size="30">{fa(val)}°</text>'
        f'<text x="120" y="126" text-anchor="middle" fill="#FBBF24" font-family="Vazirmatn,sans-serif" font-weight="800" font-size="15">{lbl}</text></svg>'
    )


def _radar_svg(item: dict[str, Any], ca: str, cb: str, compact: bool = False) -> str:
    labels = list(item.get("radarLabels") or ["تأثیر", "شدت", "ساختار", "هیجان", "ثبات", "میراث"])[:6]
    ra = list(item.get("radarA") or [90, 85, 92, 84, 94, 90])[:6]
    rb = list(item.get("radarB") or [86, 94, 85, 93, 84, 88])[:6]
    while len(labels) < 6:
        labels.append("شاخص")
    while len(ra) < 6:
        ra.append(80)
    while len(rb) < 6:
        rb.append(80)
    cx, cy, rad = 450.0, 225.0, 132.0

    def _pts(arr: list[Any]) -> list[tuple[float, float]]:
        out = []
        for idx, v in enumerate(arr):
            ang = (60 * idx - 90) * math.pi / 180.0
            r = max(18.0, min(100.0, float(v))) / 100.0 * rad
            out.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
        return out

    pa, pb = _pts(ra), _pts(rb)
    rings = []
    for f in (1.0, 0.75, 0.5, 0.25):
        pts_s = " ".join(
            f"{cx + rad * f * math.cos((60 * i - 90) * math.pi / 180.0):.1f},{cy + rad * f * math.sin((60 * i - 90) * math.pi / 180.0):.1f}"
            for i in range(6)
        )
        rings.append(f'<polygon points="{pts_s}" fill="{"#060d1e66" if f == 1.0 else "none"}"/>')

    pos = [
        (cx, 32, "middle"),
        (cx + 150, 149, "start"),
        (cx + 150, 287, "start"),
        (cx, 395, "middle"),
        (cx - 150, 287, "end"),
        (cx - 150, 149, "end"),
    ]
    lbl_svg = "".join(
        f'<g style="direction:ltr">'
        f'<text x="{pos[i][0]:.1f}" y="{pos[i][1]:.1f}" text-anchor="{pos[i][2]}" direction="ltr" unicode-bidi="isolate" fill="#F8FAFC" font-family="Vazirmatn,sans-serif" font-weight="800" font-size="25">{esc(labels[i])}</text>'
        f'<text x="{pos[i][0]:.1f}" y="{pos[i][1] + 32:.1f}" text-anchor="{pos[i][2]}" direction="ltr" unicode-bidi="isolate" font-family="Vazirmatn,sans-serif" font-weight="900" font-size="23">'
        f'<tspan fill="{ca}">{fa(int(round(float(ra[i]))))}</tspan><tspan fill="#94A3B8"> / </tspan><tspan fill="{cb}">{fa(int(round(float(rb[i]))))}</tspan></text></g>'
        for i in range(6)
    )
    dots_b = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5.5" fill="{cb}" stroke="#fff" stroke-width="2.2"/>' for x, y in pb)
    dots_a = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{ca}" stroke="#fff" stroke-width="2.2"/>' for x, y in pa)
    max_h = 415 if compact else 460
    return (
        f'<div dir="ltr" style="direction:ltr;width:100%;display:flex;align-items:center;justify-content:center">'
        f'<svg style="width:100%;height:auto;max-height:{max_h}px" viewBox="0 0 900 445" fill="none" dir="ltr">'
        f'<defs><radialGradient id="radGlow" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="{ca}" stop-opacity=".12"/><stop offset="1" stop-color="#0D1730" stop-opacity="0"/></radialGradient></defs>'
        f'<circle cx="450" cy="225" r="146" fill="url(#radGlow)"/>'
        f'<g stroke="#ffffff26" stroke-width="1.6">{"".join(rings)}'
        f'<line x1="450" y1="93" x2="450" y2="357"/><line x1="564.3" y1="159" x2="335.7" y2="291"/><line x1="564.3" y1="291" x2="335.7" y2="159"/></g>'
        f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pb)}" fill="{cb}" fill-opacity=".26" stroke="{cb}" stroke-width="4" stroke-linejoin="round"/>'
        f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pa)}" fill="{ca}" fill-opacity=".30" stroke="{ca}" stroke-width="4.4" stroke-linejoin="round"/>'
        f'{dots_b}{dots_a}{lbl_svg}</svg></div>'
    )


@with_sample_badge
def render_debate_html(
    item: dict[str, Any],
    *,
    slide: str = "slide1",
    header_mode: str = "full",
    fmt: str = "4:5",
    theme: str = "classic",
    modules: list[dict[str, Any]] | None = None,
) -> str:
    """رندر HTML ۱۰۰٪ آفلاین و ۱:۱ مطابق `debate.html` در ۵ اسلاید و ۳ فرمت."""
    w, h = DEBATE_FORMATS.get(fmt, DEBATE_FORMATS["4:5"])
    is16, is9 = fmt == "16:9", fmt == "9:16"
    layout = _SLIDE_TO_LAYOUT.get(slide, "clash")
    th = _THEMES.get(theme, _THEMES["classic"])

    mod_map = {m["id"]: bool(m.get("enabled", True)) for m in (modules or []) if isinstance(m, dict) and m.get("id")}
    show_pitch = mod_map.get("pitch", True)
    show_scan = mod_map.get("scan", True)
    show_blind = mod_map.get("blindspot", True)
    show_verdict = mod_map.get("verdict", True)

    sa = dict(item.get("sideA") or {})
    sb = dict(item.get("sideB") or {})
    ca = ensure_dark_bg_contrast(str(sa.get("color") or "#38BDF8"), min_ratio=4.6)
    cb = ensure_dark_bg_contrast(str(sb.get("color") or "#E62E45"), min_ratio=4.6)
    if ca.lower() == cb.lower():
        cb = "#E62E45" if ca.upper() != "#E62E45" else "#F59E0B"

    heat = int(item.get("heat") or 90)
    vote_a = max(10, min(90, int(item.get("voteA") or 52)))
    vote_b = 100 - vote_a
    title_html = _hl_title(str(item.get("title") or ""), item.get("highlight"))
    verdict_txt = esc(item.get("verdict") or "")
    hottake_txt = esc(item.get("hotTake") or item.get("verdict") or "")

    # رندر ۵ اسلاید دقیقاً مطابق debate.html
    if layout == "clash":
        max_args = 2 if is16 else 3

        def _plate(side: dict[str, Any], uid: str, col: str, idx: int) -> str:
            cls = "plate-a" if idx == 0 else "plate-b"
            pct = vote_a if idx == 0 else vote_b
            bar_w = max(45, min(98, pct + 32))
            args_html = "".join(
                f'<div class="arg-row"><span class="arg-num" style="background:{col}24;color:{col};border:1.5px solid {col}66">۰{fa(k + 1)}</span>'
                f'<span class="arg-txt" style="font-size:{18.5 if is16 else 20.5}px">{esc(a)}</span></div>'
                for k, a in enumerate((side.get("args") or [])[:max_args])
            )
            blind_html = (
                f'<div class="blind-box amber-tape"><div class="blind-t">⚡ چالش اصلی:</div>'
                f'<div class="blind-b">{esc(side.get("blindspot", ""))}</div></div>'
                if (show_blind and not is16 and side.get("blindspot")) else ""
            )
            top_grad = f"{col},{col}20" if idx == 0 else f"{col}20,{col}"
            wm_side = "left:12px" if idx == 0 else "right:12px"
            pad_side = "padding-left:28px" if idx == 0 else "padding-right:28px"
            return (
                f'<div class="{cls} plate-box" style="border:1.5px solid {col}66;background:linear-gradient(160deg,{col}26 0%,#0b152df2 34%,#060d1df7 100%)">'
                f'<div class="plate-wm fd" style="{wm_side};color:{col}">{esc(str(side.get("code") or "XGP")[:3].upper())}</div>'
                f'<div class="plate-top" style="background:linear-gradient(90deg,{top_grad})"></div>'
                f'<div class="fcol gap14 rel-z">'
                f'<div class="fi gap14" style="{pad_side}">{_side_badge(side, uid, 76 if is16 else 88, col)}'
                f'<div class="min0">'
                f'<h2 class="plate-name" style="font-size:{29 if is16 else 34}px">{esc(side.get("name", ""))}</h2>'
                f'<div class="plate-sub">{esc(str(side.get("sub") or "").replace("جبهه اول • ", "").replace("جبهه دوم • ", "").replace("جبهه موافق • ", "").replace("جبهه مخالف • ", "").replace("جبهه منتقد • ", ""))}</div></div></div>'
                f'<div class="thesis-box" style="border-right:5px solid {col}">'
                f'<span class="thesis-q fd" style="color:{col}">“</span>'
                f'<p style="font-size:{19.5 if is16 else 21.5}px;font-weight:900;color:#fff;line-height:1.46;position:relative;z-index:2">{esc(side.get("thesis", ""))}</p></div>'
                f'<div class="fcol gap10">{args_html}</div></div>'
                f'<div class="fcol gap12 rel-z" style="padding-top:8px">{blind_html}'
                + (
                    f'<div class="plate-stat"><div class="min0"><div style="font-size:14px;font-weight:700;color:#94A3B8">{esc(side.get("statLabel", ""))}</div>'
                    f'<div style="font-size:21px;font-weight:900;color:{col}">{fa(esc(side.get("statVal", "")))}</div></div>'
                    f'<div class="stat-track"><div class="stat-fill" style="width:{bar_w}%;background:linear-gradient(90deg,{col}88,{col});box-shadow:0 0 12px {col}"></div></div>'
                    f'</div>'
                    if (
                        str(side.get("statLabel") or "").strip()
                        and str(side.get("statVal") or "").strip()
                        and str(side.get("statLabel") or "").strip() not in {"شاخص داغی بحث", "شاخص واکنش هواداران"}
                        and str(side.get("statVal") or "").strip() != "بحث داغ روز"
                    )
                    else ""
                )
                + '</div></div>'
            )

        vs_badge = (
            '<div class="vs-clash"><div class="vs-ring-1"></div><div class="vs-ring-2"></div>'
            '<div class="vs-diamond"><span class="vs-lbl fd">VS</span></div></div>'
        )
        if is16:
            verd_16 = (
                f'<div class="xe" style="padding:16px 20px;gap:6px"><div style="font-size:15px;font-weight:800;color:#FCD34D">✦ جمع‌بندی تحریریه XGPedia</div>'
                f'<p style="font-size:18px;font-weight:700;color:#F1F5F9;line-height:1.5">{verdict_txt}</p></div>'
                if show_verdict else ""
            )
            body_html = (
                f'<div class="clash-16">'
                f'<div class="clash-16-l"><div class="fcol gap14"><div class="fi gap12"><span class="rift-tag fm">THE RIFT</span>{_waveform_svg(heat, ca, cb, 190, 28)}</div>'
                f'<h1 style="font-size:41px;font-weight:900;color:#fff;line-height:1.28">{title_html}</h1>'
                f'<p style="font-size:18.5px;font-weight:600;color:#CBD5E1;line-height:1.52">{hottake_txt}</p></div>{verd_16}</div>'
                f'<div class="clash-16-r">{_plate(sa, "ha", ca, 0)}{_plate(sb, "hb", cb, 1)}{vs_badge}</div></div>'
            )
        else:
            verd_9 = (
                f'<div class="xe fbw gap16" style="padding:16px 24px;flex-direction:row!important;flex-shrink:0">'
                f'<div class="fcol gap6 min0"><div style="font-size:18px;font-weight:800;color:#FCD34D">✦ جمع‌بندی تحریریه XGPedia</div>'
                f'<p style="font-size:21px;font-weight:700;color:#F1F5F9;line-height:1.5">{verdict_txt}</p></div>'
                f'{_heat_gauge_svg(heat, 186, 106)}</div>'
                if (is9 and show_verdict) else ""
            )
            body_html = (
                f'<div class="fcol flex1 min0 gap16">'
                f'<div class="fcol items-center text-center gap10" style="flex-shrink:0;padding:0 8px">'
                f'<div class="fi gap12"><span class="hline" style="background:linear-gradient(90deg,transparent,{ca})"></span>'
                f'{_waveform_svg(heat, ca, cb, 250, 28)}'
                f'<span class="hline" style="background:linear-gradient(270deg,transparent,{cb})"></span></div>'
                f'<h1 style="font-size:{50 if is9 else 44}px;font-weight:900;color:#fff;line-height:1.28">{title_html}</h1></div>'
                f'<div class="clash-grid">{_plate(sa, "ha", ca, 0)}{_plate(sb, "hb", cb, 1)}{vs_badge}</div>'
                f'{verd_9}</div>'
            )
    elif layout == "evidence":
        hdr_bar = (
            f'<div class="xm" style="padding:14px 24px;flex-shrink:0"><div class="ev-hdr">'
            f'<div class="fi gap12 min0">{_side_badge(sa, "ca", 64, ca)}<div class="min0">'
            f'<div class="ev-name">{esc(sa.get("name", ""))}</div><div class="ev-sub" style="color:{ca}">{esc(sa.get("sub", ""))}</div></div></div>'
            f'<div class="fcol items-center text-center"><span class="radar-pill fd">RADAR DUEL</span>'
            f'<span style="font-size:15px;font-weight:700;color:#94A3B8;margin-top:4px">مقایسه ۶ محوره</span></div>'
            f'<div class="fi gap12 min0" style="justify-content:flex-end;text-align:left"><div class="min0">'
            f'<div class="ev-name">{esc(sb.get("name", ""))}</div><div class="ev-sub" style="color:{cb}">{esc(sb.get("sub", ""))}</div></div>'
            f'{_side_badge(sb, "cb", 64, cb)}</div></div></div>'
        )
        def _ko_card(side: dict[str, Any], col: str) -> str:
            return (
                f'<div class="ko-card" style="border-right:6px solid {col}">'
                f'<div class="fbw"><span style="font-size:20px;font-weight:900;color:{col}">ضربه فنی علیه {esc(side.get("name", ""))}</span>'
                f'<span class="ko-tag amber-tape fm">KNOCKOUT</span></div>'
                f'<p style="font-size:19.5px;font-weight:600;color:#F1F5F9;line-height:1.48">{esc(side.get("blindspot", ""))}</p></div>'
            )
        if is16:
            body_html = (
                f'<div class="fcol flex1 min0 gap16">{hdr_bar}<div class="ev-16">'
                f'<div class="xm" style="padding:20px"><div class="sec-h"><div class="fi gap10"><span class="bar-red"></span>'
                f'<h3 class="sec-t">رادار ۶ محوره مناظره</h3></div><span class="fm" style="font-size:15px;font-weight:800;color:#94A3B8">XGPEDIA MODEL</span></div>'
                f'<div class="flex1 fc">{_radar_svg(item, ca, cb, False)}</div></div>'
                f'<div class="xe" style="padding:20px;gap:14px"><div class="sec-h"><div class="fi gap10"><span class="bar-amb"></span>'
                f'<h3 class="sec-t">نقطه کور هر طرف</h3></div><span class="fm" style="font-size:14.5px;font-weight:800;color:#FCD34D">COUNTER-PUNCH</span></div>'
                f'<div class="fcol flex1 justify-center gap14">{_ko_card(sa, ca)}{_ko_card(sb, cb)}</div></div></div></div>'
            )
        else:
            ko_cols = "1fr" if is9 else "1fr 1fr"
            body_html = (
                f'<div class="fcol flex1 min0 gap16">{hdr_bar}'
                f'<div class="xm flex1 min0" style="padding:20px"><div class="sec-h">'
                f'<div class="fi gap10"><span class="bar-red"></span><h3 class="sec-t">رادار ۶ محوره مقایسه قدرت استدلال</h3></div>'
                f'<div class="fi gap16" style="font-size:18px;font-weight:800">'
                f'<span class="fi gap8"><span class="pdot" style="background:{ca}"></span>{esc(sa.get("name", ""))}</span>'
                f'<span class="fi gap8"><span class="pdot" style="background:{cb}"></span>{esc(sb.get("name", ""))}</span></div></div>'
                f'<div class="flex1 fc min0">{_radar_svg(item, ca, cb, not is9)}</div></div>'
                f'<div class="xe" style="padding:20px;gap:14px;flex-shrink:0"><div class="sec-h">'
                f'<div class="fi gap10"><span class="bar-amb"></span><h3 class="sec-t">قوی‌ترین ضربه فنی علیه هر طرف</h3></div>'
                f'<span class="fm" style="font-size:15px;font-weight:800;color:#FCD34D">BLINDSPOTS</span></div>'
                f'<div style="display:grid;grid-template-columns:{ko_cols};gap:16px">{_ko_card(sa, ca)}{_ko_card(sb, cb)}</div></div></div>'
            )
    elif layout == "hottake":
        body_html = (
            f'<div class="fcol flex1 min0"><div class="xm flex1 ht-box">'
            f'<div class="ht-wm fd ghost-stroke">HOT TAKE</div>'
            f'<div class="fbw gap16 rel-z">'
            f'<div class="fcol gap10"><div class="fi gap12"><span class="ht-pill">ادعای جنجالی</span>'
            f'<span class="fm" style="font-size:17px;font-weight:800;color:#CBD5E1;letter-spacing:.12em">FRONT PAGE EDITION</span></div>'
            f'{_waveform_svg(heat, ca, cb, 220, 26)}</div>'
            f'<div class="ht-gauge">{_heat_gauge_svg(heat, 185 if is16 else 210, 102 if is16 else 116)}</div></div>'
            f'<div class="fcol gap18 rel-z" style="margin:auto 0;padding:8px 0">'
            f'<h1 style="font-size:{38 if is16 else (48 if is9 else 43)}px;font-weight:900;color:#fff;line-height:1.28">{title_html}</h1>'
            f'<div class="chamfer ht-quote"><p style="font-size:{22 if is16 else 25.5}px;font-weight:700;color:#F1F5F9;line-height:1.62">«{hottake_txt}»</p></div></div>'
            f'<div class="ht-camps rel-z">'
            f'<div class="ht-camp" style="border-right:5px solid {ca}"><div style="font-size:17px;font-weight:900;color:{ca};margin-bottom:4px">اردوگاه {esc(sa.get("name", ""))}:</div>'
            f'<div style="font-size:18.5px;font-weight:600;color:#E2E8F0;line-height:1.45">{esc(sa.get("thesis", ""))}</div></div>'
            f'<div class="ht-camp" style="border-right:5px solid {cb}"><div style="font-size:17px;font-weight:900;color:{cb};margin-bottom:4px">اردوگاه {esc(sb.get("name", ""))}:</div>'
            f'<div style="font-size:18.5px;font-weight:600;color:#E2E8F0;line-height:1.45">{esc(sb.get("thesis", ""))}</div></div>'
            f'</div></div></div>'
        )
    elif layout == "verdict":
        def _vote_card(pct: int, col: str, side: dict[str, Any], uid: str, opt_fa: str, lead: bool) -> str:
            circ = 2.0 * math.pi * 72.0
            off = circ * (1.0 - pct / 100.0)
            cls = "plate-a" if opt_fa == "۱" else "plate-b"
            lead_tag = '<span class="lead-pill">👑 پیشتاز آرا</span>' if lead else '<span class="fm" style="font-size:15px;font-weight:700;color:#94A3B8">CHALLENGER</span>'
            return (
                f'<div class="{cls} vote-card" style="border:2px solid {col}70;background:linear-gradient(170deg,{col}28 0%,#091328f2 45%,#050b18f8 100%)">'
                f'<div class="fbw" style="width:100%"><span class="opt-pill" style="background:{col}28;color:{col};border:1px solid {col}66">گزینه {opt_fa}</span>{lead_tag}</div>'
                f'<div class="fc" style="position:relative;margin:4px 0">'
                f'<svg width="176" height="176" viewBox="0 0 176 176" style="transform:rotate(-90deg)">'
                f'<circle cx="88" cy="88" r="72" stroke="#ffffff18" stroke-width="14" fill="none"/>'
                f'<circle cx="88" cy="88" r="72" stroke="{col}" stroke-width="14" fill="none" stroke-linecap="round" stroke-dasharray="{circ:.1f}" stroke-dashoffset="{off:.1f}" style="filter:drop-shadow(0 0 10px {col})"/></svg>'
                f'<div class="fcol items-center" style="position:absolute"><span style="font-size:44px;font-weight:900;color:#fff;line-height:1">{fa(pct)}٪</span>'
                f'<span style="font-size:15px;font-weight:700;color:#CBD5E1;margin-top:4px">آرای مخاطبان</span></div></div>'
                f'<div class="fi gap12 justify-center">{_side_badge(side, uid, 62, col)}'
                f'<div style="text-align:right"><h2 style="font-size:29px;font-weight:900;color:#fff;line-height:1.2">{esc(side.get("name", ""))}</h2>'
                f'<div style="font-size:16.5px;font-weight:700;color:{col}">{esc(side.get("sub", ""))}</div></div></div>'
                f'<p style="font-size:18px;font-weight:600;color:#E2E8F0;line-height:1.45">{esc(side.get("thesis", ""))}</p>'
                f'<div class="vote-stat" style="background:{col};color:{contrast_ink(col)}">{fa(esc(side.get("statVal", "")))}</div></div>'
            )

        body_html = (
            f'<div class="fcol flex1 min0 gap16">'
            f'<div class="fcol items-center text-center gap8" style="flex-shrink:0">'
            f'<span class="court-pill">دادگاه مخاطبان XGPedia • {fa(esc(item.get("voteTotal") or "نظرسنجی زنده"))}</span>'
            f'<h1 style="font-size:{38 if is16 else 43}px;font-weight:900;color:#fff;line-height:1.26">{title_html}</h1></div>'
            f'<div class="vote-grid">{_vote_card(vote_a, ca, sa, "va", "۱", vote_a >= vote_b)}{_vote_card(vote_b, cb, sb, "vb", "۲", vote_b > vote_a)}</div>'
            f'<div class="xe fbw gap16" style="padding:16px 24px;flex-direction:row!important;flex-shrink:0">'
            f'<div class="fcol gap6 min0"><div class="fi gap8" style="font-size:18px;font-weight:800;color:#FCD34D"><span class="pdot" style="background:#FBBF24"></span><span>مهر جمع‌بندی تحریریه XGPedia</span></div>'
            f'<p style="font-size:{19 if is16 else 20.5}px;font-weight:700;color:#F1F5F9;line-height:1.5">{verdict_txt}</p></div>'
            f'<div class="cta-btn">رأی تو چیه؟ ↓</div></div></div>'
        )
    else:
        # board / WAR ROOM
        def _mini_side(side: dict[str, Any], uid: str, col: str) -> str:
            a_rows = "".join(
                f'<div class="fi gap8" style="align-items:flex-start;font-size:18px;font-weight:600;color:#E2E8F0;line-height:1.42">'
                f'<span style="font-weight:900;color:{col}">۰{fa(k + 1)}</span><span>{esc(a)}</span></div>'
                for k, a in enumerate((side.get("args") or [])[:2])
            )
            return (
                f'<div class="xm" style="padding:20px;gap:12px;border-right:5px solid {col};flex:1">'
                f'<div class="fi gap12">{_side_badge(side, uid, 64, col)}<div class="min0">'
                f'<div style="font-size:24px;font-weight:900;color:#fff" class="trunc">{esc(side.get("name", ""))}</div>'
                f'<div style="font-size:15.5px;font-weight:700;color:{col}" class="trunc">{esc(side.get("sub", ""))} • {fa(esc(side.get("statVal", "")))}</div></div></div>'
                f'<div class="fcol gap8">{a_rows}</div></div>'
            )
        m_rows = "".join(
            f'<div class="fcol gap6"><div class="m-top"><span style="color:{ca};text-align:right">{fa(int(m.get("a", 50)))}</span>'
            f'<span style="color:#E2E8F0;font-size:16px;font-weight:800;text-align:center" class="trunc">{esc(m.get("label", ""))}</span>'
            f'<span style="color:{cb};text-align:left">{fa(int(m.get("b", 50)))}</span></div>'
            f'<div class="m-bars"><div class="ct hs"><div class="ch" style="width:{max(5, min(100, int(m.get("a", 50))))}%;background:{ca}"></div></div>'
            f'<div class="ct as"><div class="ca" style="width:{max(5, min(100, int(m.get("b", 50))))}%;background:{cb}"></div></div></div></div>'
            for m in (item.get("metrics") or [])[:4]
        )
        b_grid = "board-16" if is16 else "board-v"
        body_html = (
            f'<div class="fcol flex1 min0 gap16">'
            f'<div class="xm fbw gap18" style="padding:16px 24px;flex-direction:row!important;flex-shrink:0">'
            f'<div class="fcol gap8 min0"><div class="fi gap12"><span class="rift-tag fm">WAR ROOM</span>{_waveform_svg(heat, ca, cb, 170, 24)}</div>'
            f'<h1 style="font-size:{30 if is16 else 34}px;font-weight:900;color:#fff;line-height:1.26">{title_html}</h1></div>'
            f'{_heat_gauge_svg(heat, 175, 98)}</div>'
            f'<div class="{b_grid}">{_mini_side(sa, "ba", ca)}{_mini_side(sb, "bb", cb)}'
            f'<div class="xe board-tel"><div class="sec-h"><span style="font-size:21px;font-weight:900;color:#fff">ترازوی شواهد و حکم تحریریه</span>'
            f'<span class="fm" style="font-size:14.5px;font-weight:800;color:#FCD34D">TELEMETRY</span></div>'
            f'<div class="fcol gap12" style="margin:auto 0">{m_rows}</div>'
            f'<div style="padding-top:10px;border-top:1px solid rgba(255,255,255,.12);font-size:18px;font-weight:700;color:#FDE68A;line-height:1.45">✦ {verdict_txt}</div>'
            f'</div></div></div>'
        )

    pad_top = 139 if is9 else (24 if is16 else 22)
    pad_bot = 171 if is9 else (20 if is16 else 16)
    rx1, rx2, by1, by2 = w - 24, w - 44, h - 24, h - 44

    cat_txt = esc(item.get("category") or "مناظره فوتبالی")
    ep_txt = fa(esc(item.get("episode") or "مناظره زنده"))
    tag_txt = esc(str(item.get("tag") or "XGPEDIA DEBATE").upper())
    src_txt = esc(item.get("source") or "DEBATE ROOM")
    sa_cd = esc(str(sa.get("code") or "A")[:3].upper())
    sb_cd = esc(str(sb.get("code") or "B")[:3].upper())

    pitch_svg = (
        f'<rect width="100%" height="100%" fill="url(#tg)"/>'
        f'<rect x="12" y="12" width="{w - 24}" height="{h - 24}" rx="18" stroke="#F8FAFC" stroke-opacity=".12" stroke-width="1.5"/>'
        f'<g stroke="#F8FAFC" stroke-opacity=".08" stroke-width="1.5">'
        f'<line x1="{w // 2}" y1="12" x2="{w // 2}" y2="{h - 12}" stroke-dasharray="8 8"/>'
        f'<circle cx="{w // 2}" cy="{int(h * 0.40)}" r="185"/><circle cx="{w // 2}" cy="{int(h * 0.40)}" r="300" stroke-opacity=".05" stroke-dasharray="4 8"/></g>'
        f'<path d="M{int(w * .57)} 12 L{int(w * .53)} {int(h * .25)} L{int(w * .55)} {int(h * .28)} L{w // 2} {int(h * .40)} L{int(w * .45)} {int(h * .53)} L{int(w * .47)} {int(h * .56)} L{int(w * .43)} {h - 12}" stroke="url(#riftCore)" stroke-width="3" stroke-opacity=".62"/>'
        f'<circle cx="{w // 2}" cy="{int(h * 0.40)}" r="310" fill="url(#rf)"/>'
        if show_pitch else ""
    )
    scan_div = '<div class="abs-fill scanl"></div>' if show_scan else ""
    ep_pill = "" if header_mode == "compact" else f'<span class="ep-pill">{ep_txt}</span>'

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8"/>
<style>
{build_embedded_font_css()}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{w}px;height:{h}px;overflow:hidden;background:{th['bg']};color:#F8FAFC;font-family:'Vazirmatn',system-ui,-apple-system,sans-serif;font-feature-settings:"tnum";font-variant-numeric:tabular-nums}}
.fm{{font-family:'JetBrains Mono','Space Grotesk',monospace}}
.fd{{font-family:'Space Grotesk','Vazirmatn',sans-serif}}
.fi{{display:flex;align-items:center}}
.fc{{display:flex;align-items:center;justify-content:center}}
.fbw{{display:flex;align-items:center;justify-content:space-between}}
.fcol{{display:flex;flex-direction:column}}
.flex1{{flex:1}}
.min0{{min-width:0;min-height:0}}
.rel-z{{position:relative;z-index:10}}
.items-center{{align-items:center}}.justify-center{{justify-content:center}}.text-center{{text-align:center}}
.gap6{{gap:6px}}.gap8{{gap:8px}}.gap10{{gap:10px}}.gap12{{gap:12px}}.gap14{{gap:14px}}.gap16{{gap:16px}}.gap18{{gap:18px}}
.trunc{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.abs-fill{{position:absolute;inset:0;pointer-events:none}}
.scanl{{z-index:1;background:repeating-linear-gradient(to bottom,#ffffff05 0 1px,#0000 1px 4px)}}
.ghost-stroke{{-webkit-text-stroke:2px rgba(248,250,252,.11);color:transparent}}
.amber-tape{{background:repeating-linear-gradient(-45deg,#f59e0b22 0 7px,#0000 7px 14px)}}
.chamfer{{clip-path:polygon(16px 0,100% 0,100% calc(100% - 16px),calc(100% - 16px) 100%,0 100%,0 16px)}}
.hl-slash{{position:relative;display:inline-block;padding:0 14px 3px;color:#fff;z-index:1}}
.hl-slash::before{{content:"";position:absolute;inset:4px -2px 2px;background:linear-gradient(95deg,#E62E45,#ff4d64);transform:skewX(-10deg);border-radius:8px;z-index:-1;box-shadow:0 6px 24px #e62e4578}}
#ea{{position:relative;width:{w}px;height:{h}px;padding:{pad_top}px 0 {pad_bot}px;background:{th['bg']};display:flex;flex-direction:column;justify-content:space-between;overflow:hidden}}
.xm,.xe{{position:relative;border-radius:24px;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden}}
.xm{{background:linear-gradient(165deg,#101e3de8,#081022f7);border:1.5px solid #f8fafc24;box-shadow:0 18px 44px -12px #000000a6,inset 0 1px 0 #ffffff1c}}
.xe{{background:linear-gradient(155deg,#132245ee,#070e1ff8);border:1.5px solid #7fa6e842;box-shadow:0 18px 44px -12px #000000a6,inset 0 1px 0 #ffffff22}}
.plate-a{{position:relative;border-radius:26px;clip-path:polygon(0 0,100% 0,100% 100%,28px 100%,0 calc(100% - 28px));display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;box-shadow:0 24px 56px -12px #000000b8}}
.plate-b{{position:relative;border-radius:26px;clip-path:polygon(0 0,calc(100% - 28px) 0,100% 28px,100% 100%,0 100%);display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;box-shadow:0 24px 56px -12px #000000b8}}
.hdr{{position:relative;z-index:10;padding:12px 36px 8px;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-shrink:0}}
.cat-pill{{display:inline-flex;align-items:center;gap:10px;padding:6px 20px;border-radius:999px;background:#152347eb;border:1.5px solid #ffffff30;font-size:21px;font-weight:900;color:#F8FAFC}}
.ep-pill{{padding:6px 16px;border-radius:999px;background:#e62e452e;border:1.5px solid #e62e4585;color:#FF7A8C;font-size:19px;font-weight:800}}
.pdot{{width:11px;height:11px;border-radius:999px;flex-shrink:0}}
.stage{{position:relative;z-index:10;flex:1;padding:8px 40px;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;min-height:0}}
.hline{{height:2px;width:56px;border-radius:99px}}
.clash-grid{{position:relative;display:grid;grid-template-columns:1fr 1fr;gap:24px;flex:1;min-height:0}}
.clash-16{{display:grid;grid-template-columns:4fr 8fr;gap:24px;flex:1;min-height:0;align-items:stretch}}
.clash-16-l{{display:flex;flex-direction:column;justify-content:space-between;gap:16px;border-left:1px solid rgba(255,255,255,.14);padding-left:24px}}
.clash-16-r{{position:relative;display:grid;grid-template-columns:1fr 1fr;gap:24px;min-height:0}}
.plate-box{{flex:1;padding:24px;gap:16px}}
.plate-wm{{position:absolute;bottom:-28px;font-weight:800;font-size:145px;line-height:1;opacity:.06;pointer-events:none}}
.plate-top{{position:absolute;top:0;left:0;right:0;height:5px}}
.side-pill{{padding:2px 10px;border-radius:6px;font-size:13.5px;font-weight:900}}
.plate-name{{font-weight:900;color:#fff;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.plate-sub{{font-size:16.5px;font-weight:700;color:#CBD5E1;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.thesis-box{{position:relative;padding:15px 16px;border-radius:16px;background:rgba(5,11,24,.85);border:1px solid rgba(255,255,255,.14);overflow:hidden}}
.thesis-q{{position:absolute;top:4px;left:12px;font-weight:800;font-size:44px;line-height:1;opacity:.16}}
.arg-row{{display:flex;align-items:flex-start;gap:12px}}
.arg-num{{width:32px;height:32px;border-radius:11px;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:2px;font-size:15px;font-weight:900}}
.arg-txt{{font-weight:600;color:#F1F5F9;line-height:1.48}}
.blind-box{{padding:10px 14px;border-radius:16px;border:1px solid rgba(251,191,36,.32)}}
.blind-t{{font-size:13.5px;font-weight:900;color:#FCD34D;margin-bottom:2px}}
.blind-b{{font-size:16px;font-weight:600;color:#E2E8F0;line-height:1.4}}
.plate-stat{{padding-top:12px;border-top:1px solid rgba(255,255,255,.12);display:flex;align-items:center;justify-content:space-between;gap:10px}}
.stat-track{{width:108px;height:10px;border-radius:99px;background:rgba(255,255,255,.10);overflow:hidden;flex-shrink:0}}
.stat-fill{{height:100%;border-radius:99px}}
.vs-clash{{position:absolute;left:50%;top:72px;transform:translate(-50%,-50%);z-index:20;display:flex;align-items:center;justify-content:center;pointer-events:none}}
.vs-ring-1{{position:absolute;width:114px;height:114px;border-radius:999px;border:1px dashed rgba(255,255,255,.30)}}
.vs-ring-2{{position:absolute;width:92px;height:92px;border-radius:999px;background:rgba(13,23,48,.82);border:1px solid rgba(255,255,255,.20)}}
.vs-diamond{{width:72px;height:72px;border-radius:20px;transform:rotate(45deg);background:linear-gradient(135deg,#ff465e,#b8192e);border:2px solid rgba(255,255,255,.65);box-shadow:0 0 48px rgba(230,46,69,.95);display:flex;align-items:center;justify-content:center}}
.vs-lbl{{transform:rotate(-45deg);font-weight:800;font-size:28px;color:#fff}}
.rift-tag{{padding:4px 12px;border-radius:8px;background:#E62E45;color:#fff;font-size:14px;font-weight:800;letter-spacing:.08em}}
.ev-hdr{{display:grid;grid-template-columns:4fr 3fr 4fr;align-items:center;gap:12px}}
.ev-name{{font-size:26px;font-weight:900;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.ev-sub{{font-size:16.5px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.radar-pill{{padding:4px 16px;border-radius:999px;background:#E62E45;color:#fff;font-weight:800;font-size:17px;box-shadow:0 8px 20px rgba(230,46,69,.4)}}
.ev-16{{display:grid;grid-template-columns:7fr 5fr;gap:20px;flex:1;min-height:0}}
.sec-h{{display:flex;align-items:center;justify-content:space-between;padding-bottom:10px;border-bottom:1px solid rgba(255,255,255,.12)}}
.sec-t{{font-size:25px;font-weight:900;color:#fff}}
.bar-red{{width:8px;height:28px;border-radius:99px;background:#E62E45}}
.bar-amb{{width:8px;height:28px;border-radius:99px;background:#FBBF24}}
.ko-card{{padding:16px;border-radius:16px;background:rgba(7,14,31,.90);border:1px solid rgba(255,255,255,.14);display:flex;flex-direction:column;gap:8px}}
.ko-tag{{padding:2px 10px;border-radius:6px;border:1px solid rgba(251,191,36,.42);color:#FCD34D;font-size:13px;font-weight:800}}
.ht-box{{padding:28px;border:2px solid #e62e4578!important;background:linear-gradient(148deg,#182850ee 0%,#091228f7 58%,#1c0c1ef7 100%)!important}}
.ht-wm{{position:absolute;bottom:140px;right:24px;font-weight:800;font-size:136px;line-height:1;opacity:.55;pointer-events:none}}
.ht-pill{{padding:6px 16px;border-radius:12px;background:#E62E45;color:#fff;font-size:19px;font-weight:900;transform:skewX(-6deg);box-shadow:0 8px 24px rgba(230,46,69,.5)}}
.ht-gauge{{padding:6px 12px;border-radius:16px;background:rgba(7,15,34,.90);border:1px solid rgba(255,255,255,.12)}}
.ht-quote{{padding:22px 24px;background:rgba(5,11,24,.90);border:1px solid rgba(255,255,255,.15);border-right:6px solid #E62E45}}
.ht-camps{{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding-top:14px;border-top:1px solid rgba(255,255,255,.12)}}
.ht-camp{{padding:16px;border-radius:16px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12)}}
.court-pill{{display:inline-flex;align-items:center;padding:4px 18px;border-radius:999px;background:rgba(230,46,69,.20);border:1px solid rgba(230,46,69,.55);color:#FF7A8C;font-size:18px;font-weight:800}}
.vote-grid{{display:grid;grid-template-columns:1fr 1fr;gap:24px;flex:1;min-height:0}}
.vote-card{{padding:22px;align-items:center;text-align:center;gap:12px}}
.opt-pill{{padding:4px 14px;border-radius:12px;font-size:17px;font-weight:900}}
.lead-pill{{padding:4px 12px;border-radius:999px;background:rgba(251,191,36,.20);border:1px solid rgba(251,191,36,.60);color:#FCD34D;font-size:15.5px;font-weight:900}}
.vote-stat{{width:100%;padding:10px 14px;border-radius:16px;font-weight:900;font-size:19.5px;box-shadow:0 8px 20px rgba(0,0,0,.35)}}
.cta-btn{{padding:12px 20px;border-radius:16px;background:#E62E45;color:#fff;font-size:19px;font-weight:900;flex-shrink:0;box-shadow:0 8px 24px rgba(230,46,69,.45)}}
.board-v{{display:grid;grid-template-columns:1fr 1fr;gap:16px;flex:1;min-height:0}}
.board-v .board-tel{{grid-column:span 2;padding:20px;gap:12px}}
.board-16{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;flex:1;min-height:0}}
.board-16 .board-tel{{padding:20px;gap:12px}}
.m-top{{display:grid;grid-template-columns:1fr 2fr 1fr;font-size:18px;font-weight:900;align-items:center}}
.m-bars{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
.ct{{height:10px;background:#ffffff1a;overflow:hidden;display:flex;align-items:center}}
.ct.hs{{justify-content:flex-end;border-radius:0 99px 99px 0}}
.ct.as{{justify-content:flex-start;border-radius:99px 0 0 99px}}
.ch{{height:100%;border-radius:0 99px 99px 0}}.ca{{height:100%;border-radius:99px 0 0 99px}}
.ftr{{position:relative;z-index:10;padding:10px 44px 10px;border-top:1px solid rgba(255,255,255,.14);display:flex;align-items:center;justify-content:space-between;gap:16px;flex-shrink:0;flex-wrap:nowrap!important;white-space:nowrap!important;overflow:hidden!important}}
.ftr-l{{display:flex;align-items:center;gap:10px;min-width:0;overflow:hidden;white-space:nowrap!important;text-overflow:ellipsis!important}}
.ftr-dot{{width:11px;height:11px;border-radius:999px;background:#E62E45;box-shadow:0 0 10px #E62E45;flex-shrink:0}}
.ftr-tk{{font-size:17px;font-weight:800;letter-spacing:.12em;color:#F1F5F9;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}}
.ftr-r{{display:flex;align-items:center;gap:10px;flex-shrink:0;white-space:nowrap!important}}
.ftr-brand{{font-size:19px;font-weight:800;color:#FFFFFF}}
.ftr-src{{font-size:16px;font-weight:600;color:#CBD5E1}}
</style>
</head>
<body>
<div id="ea">
  <div class="abs-fill" style="z-index:0;background:radial-gradient(circle at 84% 34%,{ca}3d,transparent 48%),radial-gradient(circle at 16% 34%,{cb}3d,transparent 48%),radial-gradient(circle at 50% 42%,{th['glow']},transparent 54%)"></div>
  <div class="abs-fill" style="z-index:0;overflow:hidden">
    <div class="fd ghost-stroke" style="position:absolute;top:-44px;right:-28px;font-weight:800;font-size:225px;line-height:1;opacity:.6">{sa_cd}</div>
    <div class="fd ghost-stroke" style="position:absolute;bottom:-38px;left:-28px;font-weight:800;font-size:225px;line-height:1;opacity:.6">{sb_cd}</div>
  </div>
  <svg class="abs-fill" style="z-index:0;width:100%;height:100%" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid slice" fill="none">
    <defs>
      <pattern id="tg" width="54" height="54" patternUnits="userSpaceOnUse"><path d="M54 0H0v54" stroke="#F8FAFC" stroke-opacity=".048"/></pattern>
      <radialGradient id="rf" cx="50%" cy="38%" r="48%"><stop offset="0" stop-color="#E62E45" stop-opacity=".26"/><stop offset=".55" stop-color="#E62E45" stop-opacity=".06"/><stop offset="1" stop-color="#E62E45" stop-opacity="0"/></radialGradient>
      <linearGradient id="riftCore" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#38BDF8" stop-opacity="0"/><stop offset=".28" stop-color="#38BDF8" stop-opacity=".7"/><stop offset=".5" stop-color="#FFFFFF" stop-opacity=".95"/><stop offset=".72" stop-color="#E62E45" stop-opacity=".7"/><stop offset="1" stop-color="#E62E45" stop-opacity="0"/></linearGradient>
    </defs>
    {pitch_svg}
    <path d="M24 44V24H44M{rx1} 44V24H{rx2}M24 {by2}V{by1}H44M{rx1} {by2}V{by1}H{rx2}" stroke="#E62E45" stroke-opacity=".70" stroke-width="2.4"/>
  </svg>
  {scan_div}
  <header class="hdr">
    <div class="fi gap10 min0" style="flex-wrap:wrap">
      <div class="cat-pill"><span class="pdot" style="background:#E62E45;box-shadow:0 0 12px #E62E45"></span><span>{cat_txt}</span></div>
      {ep_pill}
    </div>
    <div style="flex-shrink:0">{_brand_logo_img(44)}</div>
  </header>
  <main class="stage">{body_html}</main>
  <footer class="ftr">
    <div class="ftr-l"><span class="ftr-dot"></span><span class="ftr-tk fm" dir="ltr">{tag_txt}</span></div>
    <div class="ftr-r fm" dir="ltr"><span class="ftr-brand">@XGPedia</span><span style="color:#64748B">|</span><span class="ftr-src">{src_txt}</span></div>
  </footer>
</div>
</body>
</html>"""
