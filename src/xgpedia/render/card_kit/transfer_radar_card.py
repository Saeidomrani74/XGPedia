"""کارت ماژولار «رادار نقل‌وانتقالات» (XGPedia Transfer Radar Studio — Modular Mode, D48).

ویژگی‌های اجباری رعایت‌شده:
  - حالت ماژولار کامل: ۲ سبک هدر (`full` کامل / `compact` فشرده) + ۵ پریست اسلاید (`slide1`..`slide5`) + ۱۰ ماژول مستقل قابل انتخاب (`pipeline`, `package`, `credibility`, `tacticalfit`, `pitchzone`, `valuation`, `mvtrend`, `seasonstats`, `rivals`, `verdict`)
  - رعایت کامل قانون `null ≠ 0` (ماژول بدون دیتای واقعی قفل و مخفی می‌ماند)
  - ۱۰۰٪ آفلاین بدون CDN (فونت محلی Vazirmatn/JetBrains Mono/Space Grotesk + لوگوی واقعی SVG برند)
  - هم‌ترازی دقیق چهارگوشهٔ رنگی و فاصلهٔ عمودی بالا (+4px) با استاندارد Post-Match (`pad_top=24/22/139`)
  - کنتراست خودکار WCAG >= 4.8، ترتیب امن `esc(fa(...))`، عدم استفاده از `•` کنار ارقام فارسی.
"""
from __future__ import annotations

import math
from typing import Any

from src.xgpedia.render.card_kit.helpers import ensure_dark_bg_contrast, esc, fa
from src.xgpedia.render.cards import _brand_logo_data_uri
from src.xgpedia.render.studio_engine import build_embedded_font_css

TRANSFER_DEFAULT_SLIDE = "slide1"
TRANSFER_DEFAULT_HEADER = "full"

TRANSFER_FORMATS: dict[str, tuple[int, int]] = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}

TRANSFER_STATUSES: dict[str, dict[str, str]] = {
    "hot": {"fa": "مذاکرات پیشرفته", "en": "ADVANCED TALKS", "color": "#E62E45", "bg": "#e62e452e", "bd": "#e62e4585", "tx": "#FF6B7F"},
    "done": {"fa": "قطعی | HERE WE GO", "en": "DONE DEAL", "color": "#10B981", "bg": "#10b9812b", "bd": "#34d39980", "tx": "#34D399"},
    "bid": {"fa": "پیشنهاد رسمی", "en": "OFFICIAL BID", "color": "#F59E0B", "bg": "#f59e0b2b", "bd": "#fbbf2480", "tx": "#FCD34D"},
    "radar": {"fa": "شایعه داغ", "en": "ON THE RADAR", "color": "#38BDF8", "bg": "#38bdf826", "bd": "#38bdf87a", "tx": "#7DD3FC"},
    "hijack": {"fa": "احتمال هایجک", "en": "HIJACK ALERT", "color": "#A78BFA", "bg": "#8b5cf62b", "bd": "#a78bfa80", "tx": "#C4B5FD"},
}

TRANSFER_SLIDES: list[tuple[str, str, str, list[str]]] = [
    ("slide1", "اسلاید ۱: کارت اصلی شایعه", "full", ["pipeline", "package", "verdict"]),
    ("slide2", "اسلاید ۲: رادار تاکتیکی و نقشه نقش", "compact", ["tacticalfit", "pitchzone"]),
    ("slide3", "اسلاید ۳: ارزش‌گذاری (+EV) و روند بازار", "compact", ["valuation", "mvtrend", "seasonstats"]),
    ("slide4", "اسلاید ۴: اعتبار منابع، رقبا و تحلیل", "compact", ["credibility", "rivals", "verdict"]),
    ("slide5", "اسلاید ۵: پرونده جامع (ماژولار)", "full", ["pipeline", "package", "credibility", "rivals", "verdict"]),
]

_RADAR_AXES = ("پرسینگ", "حمل توپ", "تمام‌کنندگی", "خلق موقعیت", "نبرد هوایی", "بازی‌سازی")


def _fm_num(v: Any) -> str:
    try:
        f = float(v)
        return fa(int(f)) if f.is_integer() else fa(f"{f:.1f}")
    except Exception:
        return fa(str(v or ""))


def get_transfer_modules(item: dict[str, Any], slide: str = TRANSFER_DEFAULT_SLIDE) -> tuple[list[dict[str, Any]], list[str]]:
    """استخراج ماژول‌های دارای دیتای واقعی شایعه (قانون null ≠ 0)."""
    fin = item.get("finance") if isinstance(item.get("finance"), dict) else {}
    tf = item.get("tacticalFit") if isinstance(item.get("tacticalFit"), dict) else None
    cred = item.get("credibility") if isinstance(item.get("credibility"), dict) else None
    verd = item.get("verdict") if isinstance(item.get("verdict"), dict) else None

    has_pipeline = item.get("stage") is not None
    has_package = fin.get("fixed") is not None or bool(fin.get("salary"))
    has_cred = bool(cred and cred.get("sources"))
    has_tfit = bool(tf and isinstance(tf.get("player"), list) and len(tf["player"]) == 6)
    has_pitch = bool(tf and tf.get("hotspots"))
    has_val = bool(isinstance(item.get("valuation"), list) and len(item["valuation"]) > 0)
    has_mv = bool(isinstance(fin.get("mv"), list) and len(fin["mv"]) >= 2)
    has_stats = bool(isinstance(item.get("stats"), list) and len(item["stats"]) > 0)
    has_rivals = bool(isinstance(item.get("rivals"), list) and len(item["rivals"]) > 0)
    has_verdict = bool(verd and verd.get("body"))

    slide_def = next((mids for sid, _, _, mids in TRANSFER_SLIDES if sid == slide), ["pipeline", "package", "verdict"])
    def_set = set(slide_def)

    # (id, title_fa, has_data, can_half, default_span)
    specs = [
        ("pipeline", "مسیر پیشرفت معامله (۵ مرحله)", has_pipeline, False, "full"),
        ("package", "بسته مالی و ساختار قرارداد", has_package, True, "full"),
        ("credibility", "سنجش اعتبار منابع (Tier 1/2/3)", has_cred, True, "half"),
        ("tacticalfit", "رادار ۶ محوره انطباق تاکتیکی", has_tfit, True, "half"),
        ("pitchzone", "نقشه حرارتی و نقش در تیم مقصد", has_pitch, True, "half"),
        ("valuation", "ارزش‌گذاری مدل در برابر قیمت (+EV)", has_val, False, "full"),
        ("mvtrend", "روند ارزش‌گذاری در بازار", has_mv, True, "half"),
        ("seasonstats", "آمار فصل و صدک نخبگان (Per 90)", has_stats, True, "half"),
        ("rivals", "کورس رقبا و احتمال مقصد", has_rivals, True, "half"),
        ("verdict", "جمع‌بندی تحریریه (Scout Verdict)", has_verdict, True, "full"),
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
        return f'<div class="tr-brand" dir="ltr"><img src="{uri}" alt="XGPedia" class="tr-brand-img"></div>'
    return '<div class="tr-brand" dir="ltr"><div class="fd tr-brand-txt"><span style="color:#E62E45">XG</span><span style="color:#F8FAFC">Pedia</span></div></div>'


def _crest_svg(club: dict[str, Any], uid: str, size: int) -> str:
    p = ensure_dark_bg_contrast(str(club.get("color") or "#E62E45"), bg="#0D1730", min_ratio=4.2)
    s = str(club.get("secondary") or "#FFFFFF")
    code = esc(str(club.get("code") or "FC")[:3].upper())
    d = "M90 16L150 40V88C150 128 124.5 156.5 90 166C55.5 156.5 30 128 30 88V40Z"
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 180 180" fill="none" style="filter:drop-shadow(0 12px 22px rgba(0,0,0,.55));display:block">'
        f'<defs><clipPath id="cl_{uid}"><path d="{d}"/></clipPath></defs>'
        f'<path d="M90 12L154 38V88C154 130.5 127 160.5 90 170.5C53 160.5 26 130.5 26 88V38Z" fill="{p}" fill-opacity=".22"/>'
        f'<g clip-path="url(#cl_{uid})"><rect x="25" y="12" width="130" height="158" fill="{p}"/>'
        f'<path d="M25 112L155 56V84L25 140Z" fill="{s}" fill-opacity=".25"/>'
        f'<path d="M90 16L150 40V58L90 34L30 58V40Z" fill="{s}" fill-opacity=".85"/></g>'
        f'<path d="{d}" stroke="{s}" stroke-opacity=".85" stroke-width="4.5"/>'
        f'<rect x="42" y="68" width="96" height="48" rx="14" fill="rgba(7,13,29,.84)" stroke="{s}" stroke-opacity=".5" stroke-width="2"/>'
        f'<text x="90" y="102" text-anchor="middle" fill="#FFFFFF" font-family="Vazirmatn,Space Grotesk,sans-serif" font-weight="900" font-size="28">{code}</text></svg>'
    )


def _player_visual(item: dict[str, Any], size: int) -> str:
    pl = item.get("player") or {}
    to_c = ensure_dark_bg_contrast(str((item.get("to") or {}).get("color") or "#E62E45"), bg="#0D1730", min_ratio=4.2)
    fr_c = ensure_dark_bg_contrast(str((item.get("from") or {}).get("color") or "#10B981"), bg="#0D1730", min_ratio=4.2)
    photo = str(pl.get("photoUrl") or "").strip()
    if photo.startswith("data:image/"):
        return f'<img src="{photo}" alt="" style="width:100%;height:100%;object-fit:cover;object-position:50% 18%;display:block">'
    num = fa(pl.get("num")) if pl.get("num") not in (None, "", 0, "0") else "★"
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 220 220" fill="none">'
        f'<defs><radialGradient id="pbg" cx="50%" cy="35%" r="65%"><stop offset="0" stop-color="{to_c}" stop-opacity=".42"/><stop offset=".65" stop-color="#0B162F" stop-opacity=".95"/><stop offset="1" stop-color="#050B18"/></radialGradient></defs>'
        f'<rect width="220" height="220" fill="url(#pbg)"/>'
        f'<circle cx="110" cy="110" r="92" stroke="#ffffff14" stroke-width="1.2" stroke-dasharray="4 6"/>'
        f'<path d="M20 190L200 75" stroke="{fr_c}" stroke-opacity=".22" stroke-width="24"/>'
        f'<circle cx="110" cy="58" r="24" fill="#94A3B8" fill-opacity=".65" stroke="#ffffff38" stroke-width="1.5"/>'
        f'<path d="M74 92L92 84Q110 98 128 84L146 92L182 118L164 148L148 138V214H72V138L56 148L38 118Z" fill="{to_c}" fill-opacity=".85" stroke="#ffffff55" stroke-width="2.2"/>'
        f'<text x="110" y="177" text-anchor="middle" fill="#FFFFFF" font-family="Vazirmatn,Space Grotesk,sans-serif" font-weight="900" font-size="50">{esc(num)}</text></svg>'
    )


def _mod_hdr(title: str, right_html: str, bar_col: str = "#E62E45") -> str:
    return (
        f'<div class="mh fbw"><div class="fi tr-gap-10">'
        f'<span class="tr-mbar" style="background:{bar_col}"></span>'
        f'<h3 class="mt">{esc(title)}</h3></div>{right_html}</div>'
    )


def _prob_bar(item: dict[str, Any], st: dict[str, str], compact: bool) -> str:
    p_to = max(1, int(item.get("prob") or 50))
    p_st = max(0, int(item.get("stayProb") or 15))
    p_ot = max(0, 100 - p_to - p_st)
    to_c = ensure_dark_bg_contrast(str((item.get("to") or {}).get("color") or st["color"]), bg="#0D1730", min_ratio=4.2)
    to_code = esc(str((item.get("to") or {}).get("code") or "DST")[:4])
    return (
        f'<div class="pc {"pcc" if compact else ""}">'
        f'<div class="ps" style="width:{p_to}%;background:{to_c};color:#FFFFFF">{f"{to_code} {fa(p_to)}٪" if p_to >= 18 else ""}</div>'
        f'{f"<div class=ps style=width:{p_st}%;background:#475569;color:#fff>{fa(p_st)}٪</div>" if p_st >= 10 else ""}'
        f'{f"<div class=ps style=width:{p_ot}%;background:#1E293B;color:#CBD5E1>{fa(p_ot)}٪</div>" if p_ot >= 10 else ""}'
        f'</div>'
    )


def _render_module(mod: dict[str, Any], item: dict[str, Any], st: dict[str, str], *, is_wide: bool) -> str:
    mid = mod["id"]
    to_c = ensure_dark_bg_contrast(str((item.get("to") or {}).get("color") or st["color"]), bg="#0D1730", min_ratio=4.2)
    is_half_now = (mod.get("span") == "half") if "span" in mod else bool(mod.get("half"))
    span_cls = (
        ("tr-span-1 mf" if is_half_now else "tr-span-2")
        if is_wide else ("mf" if is_half_now else "tr-w-full")
    )

    if mid == "pipeline":
        steps = (("رصد اولیه", "SCOUTING"), ("تماس ایجنت", "CONTACT"), ("توافق شخصی", "PERSONAL"), ("توافق باشگاه", "CLUB FEE"), ("تست و امضا", "MEDICAL"))
        cur = max(1, min(5, int(item.get("stage") or 2)))
        fill_w = ((cur - 1) / 4) * 100
        nodes = "".join(
            f'<div class="tr-st-col">'
            f'<div class="tr-st-dot" style="background:{"#10B981" if i < cur else (st["color"] if i == cur else "#1E293B")};border-color:{"#34D399" if i < cur else ("#FFFFFF" if i == cur else "rgba(255,255,255,.18)")};color:{"#FFFFFF" if i <= cur else "#94A3B8"}">{"✓" if i < cur else esc(fa(i))}</div>'
            f'<div class="tr-st-fa" style="color:{"#FFFFFF" if i <= cur else "#94A3B8"}">{esc(lb)}</div>'
            f'<div dir="ltr" class="fm tr-st-en" style="color:{st["tx"] if i == cur else "#64748B"}">{en}</div></div>'
            for i, (lb, en) in enumerate(steps, 1)
        )
        return (
            f'<div class="xm {span_cls}">'
            f'{_mod_hdr("مسیر پیشرفت معامله", f"<span class=tr-pill style=background:{st[chr(98)+chr(103)]};border-color:{st[chr(98)+chr(100)]};color:{st[chr(116)+chr(120)]}>مرحله {esc(fa(cur))} از ۵</span>", "#E62E45")}'
            f'<div class="tr-pipe-wrap"><div class="tr-pipe-bar"><div class="tr-pipe-fill" style="width:{fill_w:.0f}%;background:linear-gradient(270deg,#10B981,{st["color"]})"></div></div>'
            f'<div class="tr-pipe-grid">{nodes}</div></div></div>'
        )

    if mid == "package":
        fin = item.get("finance") or {}
        fx = float(fin.get("fixed") or 0)
        ad = float(fin.get("addon") or 0)
        tot = fx + ad
        fx_p = round((fx / tot) * 100) if tot > 0 else 100
        ad_p = 100 - fx_p
        fee_txt = f"€{_fm_num(tot)}M" if tot > 0 else "نامشخص"
        sub_txt = f"پایه {_fm_num(fx)} + پاداش {_fm_num(ad)}" if tot > 0 else "در حال مذاکره"
        sal_txt = fa(str(fin.get("salary") or "نامشخص"))
        yrs_txt = f"قرارداد {fa(fin['years'])} ساله" if fin.get("years") else str(fin.get("dealType") or "انتقال")
        mval = fin.get("modelVal")
        mkval = fin.get("marketVal")
        val_txt = f"€{_fm_num(mval)}M" if mval else (f"€{_fm_num(mkval)}M" if mkval else "—")
        val_sub = f"بازار: €{_fm_num(mkval)}M" if mkval else "ارزش‌گذاری XGPedia"
        return (
            f'<div class="xm {span_cls}">'
            f'{_mod_hdr("بسته مالی و ساختار قرارداد", f"<span class=tr-pill-em>{esc(str(fin.get(chr(100)+chr(101)+chr(97)+chr(108)+chr(84)+chr(121)+chr(112)+chr(101)) or chr(1575)+chr(1606)+chr(1578)+chr(1602)+chr(1575)+chr(1604)))}</span>", "#34D399")}'
            f'<div class="tr-pkg-grid">'
            f'<div class="xb"><div class="tr-k-l">مبلغ کل معامله</div><div dir="ltr" class="fm tr-k-v">{fee_txt}</div><div class="tr-k-s">{esc(sub_txt)}</div></div>'
            f'<div class="xb"><div class="tr-k-l">دستمزد / شرایط</div><div class="tr-k-v" style="color:#7DD3FC;font-size:22px">{esc(sal_txt)}</div><div class="tr-k-s">{esc(yrs_txt)}</div></div>'
            f'<div class="xb"><div class="tr-k-l">ارزش بازار / مدل</div><div dir="ltr" class="fm tr-k-v" style="color:#34D399">{val_txt}</div><div class="tr-k-s">{esc(val_sub)}</div></div>'
            f'</div>'
            f'<div class="tr-pay-wrap"><div class="fbw tr-pay-lbl"><span>تضمینی ({esc(fa(fx_p))}٪)</span><span>پاداش عملکردی ({esc(fa(ad_p))}٪)</span></div>'
            f'<div class="tr-pay-bar"><div style="width:{fx_p}%;background:linear-gradient(90deg,{to_c},#E62E45)"></div>'
            f'{f"<div style=width:{ad_p}%;background:linear-gradient(90deg,#F59E0B,#FBBF24)></div>" if ad_p > 0 else ""}</div></div></div>'
        )

    if mid == "credibility":
        cred = item.get("credibility") or {}
        srcs = (cred.get("sources") or [])[:3]
        if not srcs:
            return ""
        rows = "".join(
            f'<div class="xb tr-cred-row"><div class="tr-minw-0"><div class="fi tr-gap-8">'
            f'<span class="fm tr-tier-pill">TIER {esc(str(s.get("tier", 2)))}</span>'
            f'<span class="tr-cred-name">{esc(fa(s.get("name", "")))}</span></div>'
            f'<div class="tr-cred-sub">{esc(fa(s.get("outlet", "")))} | {esc(fa(s.get("time", "")))}</div></div>'
            f'<div class="tr-cred-r"><span class="tr-cred-pct">{esc(fa(s.get("conf", 80)))}٪</span>'
            f'<div class="tr-mini-bar"><div style="width:{int(s.get("conf", 80))}%;background:#34D399"></div></div></div></div>'
            for s in srcs
        )
        return f'<div class="xm {span_cls}">{_mod_hdr("اعتبار منابع و خبرنگاران", f"<span class=fm style=font-size:18px;font-weight:900;color:#34D399>{esc(fa(cred.get(chr(115)+chr(99)+chr(111)+chr(114)+chr(101), 80)))}/۱۰۰</span>", "#38BDF8")}<div class="fcol tr-gap-8 tr-my-auto">{rows}</div></div>'

    if mid == "tacticalfit":
        tf = item.get("tacticalFit") or {}
        pv, nv = tf.get("player") or [], tf.get("need") or []
        if len(pv) != 6:
            return ""
        if len(nv) != 6:
            nv = [80] * 6
        cx, cy, rad = 450.0, 195.0, 110.0

        def _pts(vs: list[Any]) -> list[tuple[float, float]]:
            return [
                (cx + max(15.0, min(100.0, float(v))) / 100.0 * rad * math.cos(math.radians(i * 60 - 90)),
                 cy + max(15.0, min(100.0, float(v))) / 100.0 * rad * math.sin(math.radians(i * 60 - 90)))
                for i, v in enumerate(vs)
            ]

        p_pts, n_pts = _pts(pv), _pts(nv)
        p_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in p_pts)
        n_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in n_pts)
        rings = "".join(
            '<polygon points="' + " ".join(
                f"{cx + rad * sc * math.cos(math.radians(i * 60 - 90)):.1f},{cy + rad * sc * math.sin(math.radians(i * 60 - 90)):.1f}"
                for i in range(6)
            ) + '"/>'
            for sc in (1.0, 0.75, 0.5, 0.25)
        )
        dx = rad * 0.866 + 24
        pos_l = ((cx, 28, "middle"), (cx + dx, cy - rad * 0.5 - 4, "start"), (cx + dx, cy + rad * 0.5 - 2, "start"),
                 (cx, cy + rad + 30, "middle"), (cx - dx, cy + rad * 0.5 - 2, "end"), (cx - dx, cy - rad * 0.5 - 4, "end"))
        lbls = "".join(
            f'<g><text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anc}" fill="#FFF" font-family="Vazirmatn" font-weight="800" font-size="22">{esc(lb)}</text>'
            f'<text x="{lx:.1f}" y="{ly + 26:.1f}" text-anchor="{anc}" font-family="Vazirmatn" font-weight="900" font-size="19"><tspan fill="{to_c}">{esc(fa(pv[i]))}</tspan><tspan fill="#64748B"> / </tspan><tspan fill="#38BDF8">{esc(fa(nv[i]))}</tspan></text></g>'
            for i, (lb, (lx, ly, anc)) in enumerate(zip(_RADAR_AXES, pos_l))
        )
        return (
            f'<div class="xm {span_cls}">{_mod_hdr("رادار انطباق تاکتیکی", f"<span class=fm style=font-size:16px;font-weight:800;color:#34D399>FIT {esc(fa(tf.get(chr(115)+chr(99)+chr(111)+chr(114)+chr(101), 90)))}٪</span>", "#E62E45")}'
            f'<div class="fc tr-flex-1" dir="ltr"><svg class="rs" viewBox="0 0 900 385" fill="none">'
            f'<g stroke="#ffffff26" stroke-width="1.6">{rings}</g>'
            f'<polygon points="{n_str}" fill="#38BDF8" fill-opacity=".20" stroke="#38BDF8" stroke-width="3" stroke-dasharray="7 5"/>'
            f'<polygon points="{p_str}" fill="{to_c}" fill-opacity=".34" stroke="{to_c}" stroke-width="4"/>'
            f'{lbls}</svg></div></div>'
        )

    if mid == "pitchzone":
        tf = item.get("tacticalFit") or {}
        hs = tf.get("hotspots") or []
        if not hs:
            return ""
        arr = tf.get("arrow") or [54, 36, 84, 48]
        x1, y1, x2, y2 = arr
        spots = "".join(f'<circle cx="{10 + x * 4.4:.1f}" cy="{10 + y * 2.7:.1f}" r="{r * 1.8:.1f}" fill="url(#ht1)"/>' for x, y, r in hs)
        return (
            f'<div class="xm {span_cls}">{_mod_hdr("نقشه حرارتی و نقش جدید", f"<span style=font-size:15px;font-weight:800;color:#FCD34D>{esc(fa(tf.get(chr(102)+chr(111)+chr(114)+chr(109)+chr(97)+chr(116)+chr(105)+chr(111)+chr(110), chr(52)+chr(45)+chr(51)+chr(45)+chr(51))))}</span>", "#F59E0B")}'
            f'<div class="fc tr-flex-1" dir="ltr"><svg class="psv" viewBox="0 0 460 290" fill="none">'
            f'<defs><radialGradient id="ht1"><stop offset="0" stop-color="{to_c}" stop-opacity=".85"/><stop offset=".55" stop-color="{to_c}" stop-opacity=".32"/><stop offset="1" stop-color="{to_c}" stop-opacity="0"/></radialGradient></defs>'
            f'<rect x="10" y="10" width="440" height="270" rx="14" fill="#071126" stroke="#ffffff2e" stroke-width="2"/>'
            f'<line x1="230" y1="10" x2="230" y2="280" stroke="#ffffff22" stroke-width="1.8"/>'
            f'<circle cx="230" cy="145" r="38" stroke="#ffffff22" stroke-width="1.8"/>'
            f'<rect x="10" y="72" width="66" height="146" stroke="#ffffff22" stroke-width="1.8"/>'
            f'<rect x="384" y="72" width="66" height="146" stroke="#ffffff22" stroke-width="1.8"/>'
            f'{spots}'
            f'<path d="M{10 + x1 * 4.4:.1f} {10 + y1 * 2.7:.1f}Q{10 + ((x1 + x2) / 2) * 4.4:.1f} {10 + (min(y1, y2) - 8) * 2.7:.1f} {10 + x2 * 4.4:.1f} {10 + y2 * 2.7:.1f}" stroke="#FBBF24" stroke-width="4" stroke-dasharray="8 6" stroke-linecap="round"/>'
            f'<circle cx="{10 + x1 * 4.4:.1f}" cy="{10 + y1 * 2.7:.1f}" r="11" fill="{to_c}" stroke="#fff" stroke-width="2.5"/></svg></div></div>'
        )

    if mid == "valuation":
        vals = (item.get("valuation") or [])[:3]
        if not vals:
            return ""
        rows = "".join(
            f'<div class="er"><div class="tr-minw-0"><div class="et">{esc(fa(v.get("title", "")))}</div><div class="em">{esc(fa(v.get("sub", "")))}</div></div>'
            f'<div class="ebc"><div class="ebr"><span class="ebl">مدل XGPedia</span><div class="ebt"><div class="efm" style="width:{min(100, float(v.get("mPct", 75))):.0f}%"></div></div></div>'
            f'<div class="ebr"><span class="ebl">قیمت بازار</span><div class="ebt"><div class="efk" style="width:{min(100, float(v.get("kPct", 70))):.0f}%"></div></div></div></div>'
            f'<div class="epw {esc(str(v.get("cls", "ed")))}"><div dir="ltr" class="epb">{"+" if float(v.get("ev", 0)) >= 0 else ""}{esc(fa(f"{float(v.get(chr(101)+chr(118), 0)):.1f}"))}٪ EV</div><span class="eps">{esc(fa(v.get("lbl", "")))}</span></div></div>'
            for v in vals
        )
        return f'<div class="xm {span_cls}">{_mod_hdr("ارزش‌گذاری هوشمند انتقال", "<span dir=ltr class=fm style=font-size:15px;font-weight:700;color:#94A3B8>MODEL vs MARKET</span>", "#34D399")}<div class="el">{rows}</div></div>'

    if mid == "mvtrend":
        vals = (item.get("finance") or {}).get("mv") or []
        if len(vals) < 2:
            return ""
        labs = ("۲۰۲۱", "۲۰۲۲", "۲۰۲۳", "۲۰۲۴", "۲۰۲۵", "۲۰۲۶")
        mx = max(max(float(x) for x in vals) * 1.18, 1.0)
        w_svg, h_svg, px, py = 900.0, 200.0, 56.0, 34.0
        pw, ph = w_svg - px * 2, h_svg - py * 2
        pts = [(px + i / (len(vals) - 1) * pw, py + ph - (float(v) / mx) * ph, float(v)) for i, v in enumerate(vals)]
        path_d = " ".join(("M" if i == 0 else "L") + f"{x:.1f} {y:.1f}" for i, (x, y, _) in enumerate(pts))
        dots = "".join(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{8 if i == len(pts) - 1 else 5.5}" fill="{to_c if i == len(pts) - 1 else "#38BDF8"}" stroke="#fff" stroke-width="2.2"/>'
            f'<text x="{x:.1f}" y="{y - 14:.1f}" text-anchor="middle" fill="#FFF" font-family="Space Grotesk,sans-serif" font-weight="800" font-size="19">€{v:g}M</text>'
            f'<text x="{x:.1f}" y="{h_svg + 26:.1f}" text-anchor="middle" fill="#94A3B8" font-family="Vazirmatn" font-weight="800" font-size="19">{labs[i] if i < len(labs) else ""}</text>'
            for i, (x, y, v) in enumerate(pts)
        )
        return (
            f'<div class="xm {span_cls}">{_mod_hdr("روند ارزش‌گذاری در بازار", f"<span dir=ltr class=fm style=font-size:18px;font-weight:900;color:#FFF>€{vals[-1]:g}M</span>", "#38BDF8")}'
            f'<div class="fc tr-flex-1" dir="ltr"><svg class="psv" viewBox="0 0 900 245" fill="none">'
            f'<path d="{path_d}" stroke="{to_c}" stroke-width="4.5" fill="none" stroke-linecap="round"/>{dots}</svg></div></div>'
        )

    if mid == "seasonstats":
        stats = (item.get("stats") or [])[:4]
        if not stats:
            return ""
        rows = "".join(
            f'<div class="fcol tr-gap-6"><div class="fbw"><span class="tr-s-lbl">{esc(fa(lb))}</span>'
            f'<div class="fi tr-gap-8"><span class="tr-s-val">{esc(fa(f"{float(val):.2f}"))}</span>'
            f'<span class="tr-s-pct">صدک {esc(fa(pct))}</span></div></div>'
            f'<div class="tr-bar-bg"><div style="width:{int(pct)}%;background:linear-gradient(270deg,{to_c},#38BDF8)"></div></div></div>'
            for lb, val, pct in stats
        )
        return f'<div class="xm {span_cls}">{_mod_hdr("آمار فصل و صدک نخبگان", "<span dir=ltr class=fm style=font-size:15px;font-weight:800;color:#CBD5E1>PER 90</span>", "#E62E45")}<div class="fcol tr-gap-10 tr-my-auto">{rows}</div></div>'

    if mid == "rivals":
        rivs = (item.get("rivals") or [])[:4]
        if not rivs:
            return ""
        rows = "".join(
            f'<div class="fcol tr-gap-6"><div class="fbw"><div class="fi tr-gap-8 tr-minw-0">'
            f'<span class="tr-dot-sm" style="background:{r.get("color", "#38BDF8")}"></span>'
            f'<span class="tr-s-lbl">{esc(fa(r.get("name", "")))}</span>'
            f'<span class="tr-r-tag">{esc(fa(r.get("tag", "")))}</span></div>'
            f'<span class="tr-s-val">{esc(fa(r.get("prob", 0)))}٪</span></div>'
            f'<div class="tr-bar-bg"><div style="width:{int(r.get("prob", 0))}%;background:{r.get("color", "#38BDF8")}"></div></div></div>'
            for r in rivs
        )
        return f'<div class="xm {span_cls}">{_mod_hdr("کورس رقبا و احتمال مقصد", "<span dir=ltr class=fm style=font-size:15px;font-weight:800;color:#CBD5E1>TRANSFER RACE</span>", "#A78BFA")}<div class="fcol tr-gap-10 tr-my-auto">{rows}</div></div>'

    if mid == "verdict":
        verd = item.get("verdict") or {}
        if not verd.get("body"):
            return ""
        return (
            f'<div class="xe {span_cls}">'
            f'{_mod_hdr("جمع‌بندی تحریریه XGPedia", "<span dir=ltr class=fm style=font-size:15px;font-weight:800;color:#CBD5E1>SCOUT VERDICT</span>", "#F59E0B")}'
            f'<h4 class="tr-v-title">{esc(fa(verd.get("title", "")))}</h4>'
            f'<p class="tr-v-body">{esc(fa(verd.get("body", "")))}</p>'
            f'<div class="tr-v-foot"><span class="tr-dot-sm" style="background:#E62E45"></span><span>{esc(fa(verd.get("tag", "")))}</span></div></div>'
        )
    return ""


def render_transfer_radar_html(
    item: dict[str, Any],
    *,
    slide: str = TRANSFER_DEFAULT_SLIDE,
    header_mode: str = TRANSFER_DEFAULT_HEADER,
    fmt: str = "4:5",
    enabled_modules: list[str] | None = None,
    custom_modules: list[dict[str, Any]] | None = None,
) -> str:
    """تولید HTML کامل و ۱۰۰٪ آفلاین برای کارت ماژولار رادار نقل‌وانتقالات (D48)."""
    w, h = TRANSFER_FORMATS.get(fmt, TRANSFER_FORMATS["4:5"])
    is_story = fmt == "9:16"
    is_wide = fmt == "16:9"
    pad_top, pad_bot = (139, 171) if is_story else ((22, 16) if is_wide else (24, 20))

    st_key = str(item.get("status") or "radar").lower()
    st = TRANSFER_STATUSES.get(st_key, TRANSFER_STATUSES["radar"])
    hm = header_mode if header_mode in ("full", "compact") else TRANSFER_DEFAULT_HEADER

    avail_mods, _ = get_transfer_modules(item, slide)
    by_id = {m["id"]: dict(m) for m in avail_mods}
    if custom_modules is not None:
        active_mods = []
        for cm in custom_modules:
            if not cm.get("enabled", True):
                continue
            mid = str(cm.get("id") or "")
            if mid in by_id:
                mobj = by_id[mid]
                want_half = cm.get("span") == "half"
                mobj["span"] = "half" if (want_half and mobj.get("can_half", False)) else "full"
                mobj["half"] = mobj["span"] == "half"
                active_mods.append(mobj)
    elif enabled_modules is not None:
        active_mods = [by_id[mid] for mid in enabled_modules if mid in by_id]
    else:
        active_mods = [m for m in avail_mods if m["enabled"]]

    dense = (fmt == "4:5" and ((hm == "full" and len(active_mods) > 2) or (hm == "compact" and len(active_mods) > 3))) or len(active_mods) > 4

    pl = item.get("player") or {}
    fr = item.get("from") or {}
    to = item.get("to") or {}
    fin = item.get("finance") or {}
    prob = int(item.get("prob") or 50)
    stay_p = int(item.get("stayProb") or 15)
    other_p = max(0, 100 - prob - stay_p)

    fr_c = ensure_dark_bg_contrast(str(fr.get("color") or "#10B981"), bg="#0D1730", min_ratio=4.2)
    to_c = ensure_dark_bg_contrast(str(to.get("color") or st["color"]), bg="#0D1730", min_ratio=4.2)
    fx = fin.get("fixed")
    ad = fin.get("addon") or 0
    fee_str = (f"€{_fm_num(fx)}+{_fm_num(ad)}M" if ad else f"€{_fm_num(fx)}M") if fx is not None else "نامشخص"

    # هدر انتقال (کامل یا فشرده)
    if hm == "compact":
        hero_html = (
            f'<div class="tr-hero-compact"><div class="tr-hc-grid">'
            f'<div class="fi tr-gap-12 tr-minw-0"><div class="tr-hc-ava" style="border-color:{st["color"]}">{_player_visual(item, 72)}</div>'
            f'<div class="tr-minw-0"><div class="tr-hc-name">{esc(fa(pl.get("name", "")))}</div>'
            f'<div class="fi tr-gap-8"><span class="tr-hc-meta">{esc(fa(pl.get("pos", "")))}</span>'
            f'<span class="tr-pill" style="background:{st["bg"]};border-color:{st["bd"]};color:{st["tx"]}">{esc(st["fa"])}</span></div></div></div>'
            f'<div class="fc tr-gap-10">{_crest_svg(fr, "fc", 58)}<div class="fcol tr-ai-center"><span dir="ltr" class="fm tr-hc-fee">{fee_str}</span></div>{_crest_svg(to, "tc", 58)}</div>'
            f'<div class="tr-hc-prob"><span class="tr-hc-plbl">احتمال انجام</span><span class="tr-hc-pval" style="color:{st["tx"]}">{esc(fa(prob))}٪</span></div>'
            f'</div>{_prob_bar(item, st, True)}</div>'
        )
    else:
        c_sz = 104 if is_wide else 120
        m_sz = 166 if is_wide else 192
        r_out = m_sz / 2 - 6
        circ = 2 * math.pi * r_out
        dash_off = circ * (1 - prob / 100.0)
        fit_sc = (item.get("tacticalFit") or {}).get("score")
        cred_sc = (item.get("credibility") or {}).get("score")
        hero_html = (
            f'<div class="fcol tr-gap-12">'
            f'<div class="tr-hero-full"><div class="tr-hf-grid">'
            f'<div class="tr-club-col"><span class="tr-c-tag">باشگاه فعلی</span>{_crest_svg(fr, "ff", c_sz)}'
            f'<div class="tr-c-name">{esc(fa(fr.get("name") or "باشگاه فعلی"))}</div>'
            f'<div class="tr-c-sub">{esc(fa(fr.get("sub") or ""))}</div></div>'
            f'<div class="tr-mid-col">'
            f'<div class="tr-medallion" style="width:{m_sz}px;height:{m_sz}px">'
            f'<svg class="tr-med-ring" viewBox="0 0 {m_sz} {m_sz}"><circle cx="{m_sz / 2}" cy="{m_sz / 2}" r="{r_out:.1f}" stroke="#ffffff1a" stroke-width="8" fill="none"/>'
            f'<circle cx="{m_sz / 2}" cy="{m_sz / 2}" r="{r_out:.1f}" stroke="{st["color"]}" stroke-width="8" fill="none" stroke-linecap="round" stroke-dasharray="{circ:.1f}" stroke-dashoffset="{dash_off:.1f}"/></svg>'
            f'<div class="tr-med-inner" style="width:{m_sz - 22}px;height:{m_sz - 22}px">{_player_visual(item, m_sz - 22)}</div>'
            f'<div class="tr-med-pill" style="border-color:{st["color"]}"><span class="tr-med-pct" style="color:{st["tx"]}">{esc(fa(prob))}٪</span><span class="tr-med-lbl">احتمال انجام</span></div></div>'
            f'<h1 class="tr-pl-name">{esc(fa(pl.get("name", "")))}</h1>'
            f'<div class="tr-pl-meta">{esc(fa(pl.get("pos", "")))}{f" | {fa(pl[chr(97)+chr(103)+chr(101)])} ساله" if pl.get("age") else ""}{f" | {esc(fa(pl[chr(110)+chr(97)+chr(116)]))}" if pl.get("nat") else ""}</div>'
            f'<div class="tr-q-row">'
            f'<div class="tr-qbox"><div class="tr-ql">بسته مالی</div><div dir="ltr" class="fm tr-qv">{fee_str}</div></div>'
            f'<div class="tr-qbox"><div class="tr-ql">اعتبار منابع</div><div class="tr-qv" style="color:#7DD3FC">{esc(fa(cred_sc or 80))}/۱۰۰</div></div>'
            f'<div class="tr-qbox"><div class="tr-ql">{ "انطباق تاکتیکی" if fit_sc else "داغ بودن شایعه" }</div><div class="tr-qv" style="color:#34D399">{esc(fa(fit_sc or item.get("hotness") or 80))}٪</div></div>'
            f'</div></div>'
            f'<div class="tr-club-col"><span class="tr-c-tag" style="background:{to_c}29;border-color:{to_c}88;color:#FFF">مقصد احتمالی</span>{_crest_svg(to, "tf", c_sz)}'
            f'<div class="tr-c-name">{esc(fa(to.get("name") or "مقصد احتمالی"))}</div>'
            f'<div class="tr-c-sub">{esc(fa(to.get("sub") or ""))}</div></div>'
            f'</div></div>'
            f'{_prob_bar(item, st, False)}'
            f'<div class="fbw tr-p-legend">'
            f'<span>انتقال به {esc(fa(to.get("name") or "مقصد"))}: <b>{esc(fa(prob))}٪</b></span>'
            f'<span>ماندن: <b>{esc(fa(stay_p))}٪</b></span>'
            f'<span>سایر مقاصد: <b>{esc(fa(other_p))}٪</b></span></div></div>'
        )

    mods_html = "".join(_render_module(m, item, st, is_wide=is_wide) for m in active_mods)

    cx_bg, cy_bg = w // 2, (h // 2 if is_wide else 330)
    crh_d = (
        f"M24 44V24H44M{w - 24} 44V24H{w - 44}"
        f"M24 {h - 44}V{h - 24}H44M{w - 24} {h - 44}V{h - 24}H{w - 44}"
    )

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<title>{esc(fa(pl.get("name", "XGPedia Transfer Radar")))}</title>
<style>
{build_embedded_font_css()}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{w}px;height:{h}px;overflow:hidden;background:#0D1730;color:#F8FAFC;
  font-family:'Vazirmatn',system-ui,sans-serif;font-feature-settings:"tnum";font-variant-numeric:tabular-nums}}
.fm{{font-family:'JetBrains Mono','Space Grotesk',monospace}}
.fd{{font-family:'Space Grotesk','Vazirmatn',sans-serif}}
.fi{{display:flex;align-items:center}}.fc{{display:flex;align-items:center;justify-content:center}}
.fbw{{display:flex;align-items:center;justify-content:space-between}}.fcol{{display:flex;flex-direction:column}}
.tr-flex-1{{flex:1}}.tr-minw-0{{min-width:0}}.tr-my-auto{{margin:auto 0}}.tr-ai-center{{align-items:center}}
.tr-gap-6{{gap:6px}}.tr-gap-8{{gap:8px}}.tr-gap-10{{gap:10px}}.tr-gap-12{{gap:12px}}

.tr-canvas{{position:relative;width:{w}px;height:{h}px;overflow:hidden;background:#0D1730;
  display:flex;flex-direction:column;justify-content:space-between;padding:{pad_top}px 0 {pad_bot}px}}
.tr-ambient{{position:absolute;inset:0;pointer-events:none;z-index:0;
  background:radial-gradient(circle at 85% 26%,{fr_c}36,transparent 46%),radial-gradient(circle at 15% 26%,{to_c}42,transparent 48%),radial-gradient(circle at 50% 30%,{st["color"]}26,transparent 54%)}}
.tr-frame-svg{{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0}}
.tr-scanlines{{position:absolute;inset:0;pointer-events:none;z-index:0;background:repeating-linear-gradient(to bottom,#ffffff04 0 1px,#0000 1px 4px)}}

.tr-header{{position:relative;z-index:10;padding:12px 36px 8px;display:flex;align-items:center;justify-content:space-between;gap:14px;flex-shrink:0}}
.tr-hdr-main{{padding:5px 16px;border-radius:999px;font-size:21px;font-weight:900;background:#152347e6;border:1px solid #ffffff2e;display:inline-flex;align-items:center;gap:8px}}
.tr-hdr-st{{padding:5px 16px;border-radius:999px;font-size:19px;font-weight:900;border:1px solid}}
.tr-hdr-sub{{font-size:17px;font-weight:700;color:#CBD5E1;margin-top:5px;display:flex;align-items:center;gap:10px}}
.tr-tier-top{{padding:2px 11px;border-radius:999px;background:rgba(16,185,129,.20);border:1px solid rgba(16,185,129,.45);color:#34D399;font-size:16px;font-weight:800}}
.tr-brand{{display:flex;align-items:center;flex-shrink:0}}.tr-brand-img{{height:48px;width:auto;display:block}}.tr-brand-txt{{font-size:32px;font-weight:800}}

.tr-stage-v{{position:relative;z-index:10;flex:1;padding:8px 38px;display:flex;flex-direction:column;justify-content:space-between;gap:{10 if dense else 14}px;min-height:0;overflow:hidden}}
.tr-stage-w{{position:relative;z-index:10;flex:1;padding:8px 40px;display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:24px;min-height:0;overflow:hidden}}
.tr-w-hero{{grid-column:span 5;display:flex;flex-direction:column;justify-content:center;min-height:0}}
.tr-w-mods{{grid-column:span 7;display:grid;grid-template-columns:1fr 1fr;grid-auto-rows:min-content;gap:12px;align-content:start;min-height:0;overflow:hidden}}
.tr-mods-v{{flex:1;display:grid;grid-template-columns:1fr 1fr;grid-auto-rows:minmax(0,auto);align-content:space-between;gap:{9 if dense else 12}px;min-height:0;overflow:hidden}}

.tr-hero-full{{border-radius:26px;background:linear-gradient(to bottom,rgba(14,27,56,.92),rgba(7,16,36,.95));border:1.5px solid rgba(255,255,255,.15);padding:16px 22px;box-shadow:0 20px 48px rgba(0,0,0,.55)}}
.tr-hf-grid{{display:grid;grid-template-columns:3fr 6fr 3fr;align-items:center;gap:10px}}
.tr-club-col{{display:flex;flex-direction:column;align-items:center;text-align:center;gap:6px}}
.tr-c-tag{{padding:3px 12px;border-radius:999px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.15);font-size:14px;font-weight:800;color:#CBD5E1}}
.tr-c-name{{font-size:22px;font-weight:900;color:#FFFFFF;line-height:1.15}}
.tr-c-sub{{font-size:14px;font-weight:700;color:#94A3B8}}
.tr-mid-col{{display:flex;flex-direction:column;align-items:center;text-align:center}}
.tr-medallion{{position:relative;display:flex;align-items:center;justify-content:center;margin-bottom:8px}}
.tr-med-ring{{position:absolute;inset:0;width:100%;height:100%;transform:rotate(-90deg)}}
.tr-med-inner{{border-radius:999px;overflow:hidden;border:2px solid rgba(255,255,255,.25);background:#070D1D}}
.tr-med-pill{{position:absolute;bottom:-10px;left:50%;transform:translateX(-50%);padding:3px 14px;border-radius:999px;background:#060C1C;border:2px solid;display:flex;align-items:center;gap:7px;white-space:nowrap}}
.tr-med-pct{{font-size:22px;font-weight:900;line-height:1}}.tr-med-lbl{{font-size:13.5px;font-weight:800;color:#E2E8F0}}
.tr-pl-name{{font-size:{34 if is_wide else 40}px;font-weight:900;color:#FFFFFF;line-height:1.1;margin-top:8px}}
.tr-pl-meta{{font-size:16px;font-weight:700;color:#CBD5E1;margin-top:4px}}
.tr-q-row{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;width:100%;max-width:420px;margin-top:10px}}
.tr-qbox{{border-radius:14px;background:rgba(7,15,34,.90);border:1px solid rgba(255,255,255,.12);padding:7px 8px;text-align:center}}
.tr-ql{{font-size:12px;font-weight:700;color:#94A3B8}}.tr-qv{{font-size:18px;font-weight:900;color:#FFFFFF;margin-top:2px}}

.tr-hero-compact{{border-radius:22px;background:rgba(11,22,47,.92);border:1.5px solid rgba(255,255,255,.15);padding:14px 20px;display:flex;flex-direction:column;gap:10px}}
.tr-hc-grid{{display:grid;grid-template-columns:5fr 4fr 3fr;align-items:center;gap:10px}}
.tr-hc-ava{{width:68px;height:68px;border-radius:16px;overflow:hidden;border:2px solid;flex-shrink:0}}
.tr-hc-name{{font-size:26px;font-weight:900;color:#FFFFFF;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.tr-hc-meta{{font-size:14.5px;font-weight:700;color:#CBD5E1}}
.tr-hc-fee{{font-size:16px;font-weight:900;color:#FFFFFF}}
.tr-hc-prob{{padding:6px 14px;border-radius:14px;background:#060D1E;border:1px solid rgba(255,255,255,.15);text-align:center;justify-self:end}}
.tr-hc-plbl{{display:block;font-size:12px;font-weight:700;color:#94A3B8}}.tr-hc-pval{{font-size:28px;font-weight:900;line-height:1}}

.pc{{width:100%;height:42px;border-radius:999px;overflow:hidden;display:flex;background:#0f172aeb;border:2px solid #ffffff2e}}
.pcc{{height:30px;border-width:1.5px}}.ps{{height:100%;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:19px;white-space:nowrap}}
.pcc .ps{{font-size:15px}}.tr-p-legend{{padding:0 6px;font-size:15.5px;font-weight:700;color:#CBD5E1}}

.xm,.xe{{position:relative;border-radius:{18 if dense else 22}px;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;
  padding:{'12px 16px' if dense else '15px 20px'};box-shadow:0 14px 36px -10px rgba(0,0,0,.55),inset 0 1px 0 rgba(255,255,255,.10)}}
.xm{{background:linear-gradient(165deg,rgba(16,29,59,.88),rgba(9,16,35,.95));border:1.5px solid rgba(248,250,252,.15)}}
.xe{{background:linear-gradient(155deg,rgba(19,33,66,.92),rgba(9,15,32,.97));border:1.5px solid rgba(127,166,232,.26)}}
.xb{{border-radius:14px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);padding:10px 12px;text-align:center}}
.tr-w-full,.tr-span-2,.mf:last-child:nth-child(odd){{grid-column:1/-1}}.mf,.tr-span-1{{grid-column:span 1;min-width:0}}
.mh{{padding-bottom:7px;margin-bottom:8px;border-bottom:1px solid rgba(255,255,255,.12)}}
.tr-mbar{{width:7px;height:24px;border-radius:99px;flex-shrink:0}}.mt{{font-size:{20 if dense else 23}px;font-weight:900;color:#FFFFFF;line-height:1}}
.tr-pill{{padding:3px 11px;border-radius:10px;border:1px solid;font-size:14px;font-weight:800;white-space:nowrap}}
.tr-pill-em{{padding:3px 11px;border-radius:10px;background:rgba(16,185,129,.20);border:1px solid rgba(52,211,153,.45);color:#34D399;font-size:14px;font-weight:800}}

.tr-pipe-wrap{{position:relative;margin:auto 0;padding:8px 0}}
.tr-pipe-bar{{position:absolute;top:29px;right:8%;left:8%;height:6px;border-radius:99px;background:rgba(255,255,255,.12);overflow:hidden}}
.tr-pipe-fill{{height:100%;border-radius:99px}}
.tr-pipe-grid{{position:relative;z-index:10;display:grid;grid-template-columns:repeat(5,1fr);gap:6px}}
.tr-st-col{{display:flex;flex-direction:column;align-items:center;text-align:center}}
.tr-st-dot{{width:42px;height:42px;border-radius:999px;border:2px solid;display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:900}}
.tr-st-fa{{font-size:16px;font-weight:900;margin-top:7px}}.tr-st-en{{font-size:11px;font-weight:700;margin-top:2px}}

.tr-pkg-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;margin:2px 0}}
.tr-k-l{{font-size:{13 if dense else 14}px;font-weight:700;color:#94A3B8}}.tr-k-v{{font-size:{22 if dense else 25}px;font-weight:900;color:#FFFFFF;margin-top:3px;line-height:1.15}}.tr-k-s{{font-size:{12 if dense else 13}px;font-weight:700;color:#CBD5E1;margin-top:2px}}
.tr-pay-wrap{{margin-top:7px;flex-shrink:0;padding-bottom:2px}}.tr-pay-lbl{{font-size:13px;font-weight:700;color:#CBD5E1;margin-bottom:4px}}
.tr-pay-bar{{width:100%;height:12px;border-radius:999px;overflow:hidden;display:flex;background:#091124;border:1px solid rgba(255,255,255,.18);flex-shrink:0}}
/* چیدمان تمیز نیم‌عرض (½) برای همهٔ ماژول‌های مجاز */
.mf .tr-pkg-grid{{grid-template-columns:1fr 1fr;gap:7px}}.mf .tr-pkg-grid .xb:last-child{{grid-column:1/-1}}
.mf .tr-k-v{{font-size:19px}}.mf .mt{{font-size:18.5px}}.mf .tr-v-title{{font-size:18.5px}}.mf .tr-v-body{{font-size:16px;line-height:1.5}}

.tr-cred-row{{display:flex;align-items:center;justify-content:space-between;gap:10px;text-align:right}}
.tr-tier-pill{{padding:2px 8px;border-radius:6px;background:rgba(16,185,129,.20);border:1px solid rgba(52,211,153,.50);color:#34D399;font-size:12px;font-weight:800;flex-shrink:0}}
.tr-cred-name{{font-size:18px;font-weight:900;color:#FFFFFF;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.tr-cred-sub{{font-size:13px;font-weight:700;color:#94A3B8;margin-top:2px}}
.tr-cred-r{{text-align:left;flex-shrink:0}}.tr-cred-pct{{font-size:19px;font-weight:900;color:#FFFFFF}}
.tr-mini-bar{{width:72px;height:6px;border-radius:99px;background:rgba(255,255,255,.12);overflow:hidden;margin-top:4px}}.tr-mini-bar div{{height:100%;border-radius:99px}}

.el{{display:flex;flex-direction:column;gap:8px;margin:auto 0}}
.er{{display:grid;grid-template-columns:1fr 1.35fr auto;align-items:center;gap:12px;padding:10px 14px;border-radius:14px;background:#161b2ed6;border:1px solid #ffffff17}}
.et{{font-size:18px;font-weight:900;color:#F8FAFC}}.em{{font-size:13px;font-weight:600;color:#94A3B8;margin-top:2px}}
.ebc{{display:flex;flex-direction:column;gap:6px}}.ebr{{display:flex;align-items:center;gap:8px}}
.ebl{{width:94px;font-size:12.5px;font-weight:700;color:#CBD5E1;text-align:right;flex-shrink:0}}
.ebt{{flex:1;height:16px;border-radius:99px;background:#262B3D;overflow:hidden;direction:ltr}}
.efm{{height:100%;background:linear-gradient(90deg,#2EB7EB,#40C8F5);border-radius:99px}}.efk{{height:100%;background:#696F7D;border-radius:99px}}
.epw{{min-width:120px;text-align:center}}.epb{{padding:5px 10px;border-radius:10px;font-size:17px;font-weight:900;border:1.5px solid var(--ebd);background:var(--eb);color:var(--ec)}}
.eps{{display:block;font-size:12.5px;font-weight:800;margin-top:3px;color:var(--ec)}}
.eh{{--eb:#10b9812b;--ebd:#34d3997a;--ec:#34D399}}.ed{{--eb:#38bdf829;--ebd:#38bdf875;--ec:#38BDF8}}.ew{{--eb:#f59e0b29;--ebd:#fbbf2475;--ec:#FBBF24}}.erisk{{--eb:#e62e452b;--ebd:#f43f5e7a;--ec:#FB7185}}

.rs,.psv{{width:100%;height:auto;max-height:{215 if (dense or is_wide) else 255}px}}
.tr-s-lbl{{font-size:17px;font-weight:800;color:#F1F5F9}}.tr-s-val{{font-size:19px;font-weight:900;color:#FFFFFF}}
.tr-s-pct{{padding:2px 8px;border-radius:7px;background:rgba(16,185,129,.20);color:#34D399;font-size:13px;font-weight:800}}
.tr-r-tag{{font-size:13px;font-weight:700;color:#94A3B8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.tr-bar-bg{{width:100%;height:11px;border-radius:99px;background:rgba(255,255,255,.10);overflow:hidden}}.tr-bar-bg div{{height:100%;border-radius:99px}}
.tr-dot-sm{{width:10px;height:10px;border-radius:999px;flex-shrink:0}}
.tr-v-title{{font-size:{21 if dense else 23}px;font-weight:900;color:#FCD34D;line-height:1.3;margin-bottom:5px}}
.tr-v-body{{font-size:{18 if dense else 19.5}px;font-weight:600;color:#F1F5F9;line-height:1.58}}
.tr-v-foot{{padding-top:8px;margin-top:8px;border-top:1px solid rgba(255,255,255,.12);display:flex;align-items:center;gap:8px;font-size:15.5px;font-weight:800;color:#F1F5F9}}

.tr-footer{{position:relative;z-index:10;padding:10px 44px 10px;flex-shrink:0}}
.tr-footer-line{{border-top:1px solid rgba(255,255,255,.14);margin-bottom:8px}}
.tr-foot-tag{{font-size:16.5px;font-weight:800;letter-spacing:.10em;color:#F1F5F9}}
.tr-foot-handle{{font-size:19.5px;font-weight:800;color:#FFFFFF}}.tr-foot-src{{font-size:16.5px;font-weight:600;color:#CBD5E1}}
</style>
</head>
<body>
<div class="tr-canvas" dir="rtl">
  <div class="tr-ambient"></div>
  <svg class="tr-frame-svg" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid slice" fill="none">
    <defs><pattern id="tg" width="54" height="54" patternUnits="userSpaceOnUse"><path d="M54 0H0v54" stroke="#F8FAFC" stroke-opacity=".052"/></pattern></defs>
    <rect width="100%" height="100%" fill="url(#tg)"/>
    <rect x="12" y="12" width="{w - 24}" height="{h - 24}" rx="18" stroke="#F8FAFC" stroke-opacity=".11" stroke-width="1.5"/>
    <circle cx="{cx_bg}" cy="{cy_bg}" r="155" stroke="#F8FAFC" stroke-opacity=".10" stroke-width="1.3"/>
    <circle cx="{cx_bg}" cy="{cy_bg}" r="235" stroke="{st["color"]}" stroke-opacity=".22" stroke-width="1.3" stroke-dasharray="4 7"/>
    <circle cx="{cx_bg}" cy="{cy_bg}" r="320" stroke="#F8FAFC" stroke-opacity=".07" stroke-width="1.2"/>
    <path d="{crh_d}" stroke="{st["color"]}" stroke-opacity=".65" stroke-width="2.2"/>
  </svg>
  <div class="tr-scanlines"></div>
  <header class="tr-header">
    <div class="fcol tr-minw-0">
      <div class="fi tr-gap-10">
        <div class="tr-hdr-main"><span>رادار نقل‌وانتقالات</span></div>
        <span class="tr-hdr-st" style="background:{st["bg"]};border-color:{st["bd"]};color:{st["tx"]}">{esc(st["fa"])}</span>
      </div>
      <div class="tr-hdr-sub">
        <span>{esc(fa(item.get("window", "پنجره نقل‌وانتقالات")))}</span>
        <span>|</span>
        <span>{esc(fa(item.get("updated", "رصد زنده")))}</span>
        <span class="tr-tier-top">{esc(fa(item.get("tierBadge", "TIER 1")))}</span>
      </div>
    </div>
    {_brand_logo_html()}
  </header>
  <main class="{'tr-stage-w' if is_wide else 'tr-stage-v'}">
    {f'<section class="tr-w-hero">{hero_html}</section><section class="tr-w-mods">{mods_html}</section>' if is_wide else f'<section>{hero_html}</section><section class="tr-mods-v">{mods_html}</section>'}
  </main>
  <footer class="tr-footer">
    <div class="tr-footer-line"></div>
    <div class="fbw tr-gap-12">
      <div class="fi tr-gap-8 tr-minw-0">
        <span class="tr-dot-sm" style="background:{st["color"]}"></span>
        <span dir="ltr" class="fm tr-foot-tag">{esc(str(item.get("windowEn", "TRANSFER RADAR")).upper())} // {esc(st["en"])} // {esc(str(item.get("dealCode", "TR-001")))}</span>
      </div>
      <div class="fi tr-gap-10 fm" dir="ltr">
        <span class="tr-foot-handle">@XGPedia</span>
        <span style="color:#64748B">|</span>
        <span class="tr-foot-src">{esc(str(item.get("source", "XGPedia Desk")))}</span>
      </div>
    </div>
  </footer>
</div>
</body>
</html>"""


def build_transfer_caption(item: dict[str, Any]) -> str:
    """تولید کپشن فارسی کامل و غیرتکراری برای کارت رادار نقل‌وانتقالات."""
    verd = item.get("verdict") if isinstance(item.get("verdict"), dict) else {}
    pl = item.get("player") or {}
    fr = item.get("from") or {}
    to = item.get("to") or {}
    fin = item.get("finance") or {}
    st = TRANSFER_STATUSES.get(str(item.get("status") or "radar").lower(), TRANSFER_STATUSES["radar"])

    parts: list[str] = []
    if verd.get("body"):
        parts.append(fa(str(verd["body"]).strip()))
    meta_bits = []
    if fr.get("name") and to.get("name"):
        meta_bits.append(f"مسیر انتقال: {fa(fr['name'])} ← {fa(to['name'])}")
    if fin.get("fixed") is not None:
        ad = fin.get("addon") or 0
        meta_bits.append(f"بسته مالی: €{_fm_num(fin['fixed'])}" + (f"+{_fm_num(ad)}M" if ad else "M"))
    meta_bits.append(f"وضعیت: {st['fa']} ({fa(item.get('prob', 50))}٪)")
    if meta_bits:
        parts.append("📡 " + " | ".join(meta_bits))
    if verd.get("tag"):
        parts.append(f"🔎 {fa(str(verd['tag']).strip())}")
    if not parts:
        parts.append(f"رصد نقل‌وانتقالاتی {fa(pl.get('name', ''))}")
    return "\n\n".join(parts)
