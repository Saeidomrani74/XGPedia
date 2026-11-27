"""کارت ماژولار «جدول رده‌بندی» (XGPedia Standings Studio — D52) — بازسازی ۱:۱ آفلاین.

ویژگی‌های ۱:۱ حفظ‌شده از `studio_templates/table.html` + استاندارد ماژولار کامل XGPedia:
  - هدر تاج صدرنشینی (نشان صدرنشین، xG/xGA/xPTS، نوار مونت‌کارلو ۱۰K و ۳ مدعی) یا هدر فشرده ۴ شاخص کلیدی
  - ۵ ماژول کاملاً مستقل و قابل چینش:
    1. `table`: جدول رده‌بندی با ۳ لنز (`classic` + فرم ۵ بازی، `xpts` + نوار عدالت، `xg` + شانس سهمیه) و ۴ برش (`top6`/`top10`/`full`/`bottom`) + رنگ‌بندی دقیق سهمیه‌ها + Spotlight
    2. `justice`: کارت‌های کارآمدترین/خوش‌شانس‌ترین و بدشانس‌ترین تیم (PTS − xPTS)
    3. `quadrant`: نقشه قدرت تاکتیکی لیگ (نمودار SVG پراکندگی xG/90 در برابر xGA/90 با ۴ ناحیه و ۳ کارت زیرین)
    4. `title_race`: ماراتن قهرمانی و سهمیه UCL (۵ تیم اول با نوار دوتکه طلایی/آبی + ۳ بازی پیش‌رو FDR)
    5. `relegation`: منطقه قرمز و نبرد بقا (۵ تیم پایین با نوار احتمال سقوط و فرم ۳ بازی)
  - پشتیبانی کامل نیم‌عرض (`½`) / تمام‌عرض (`۱`)، تغییر ترتیب، ۵ قالب نام‌گذاری‌شده و `null ≠ 0`.
"""
from __future__ import annotations

from typing import Any

from src.xgpedia.render.card_kit.helpers import contrast_ink, esc, f1, f2, fa, is_sample_preset, luminance, sample_badge_html
from src.xgpedia.render.cards import _brand_logo_data_uri
from src.xgpedia.render.studio_engine import build_embedded_font_css

STANDINGS_DEFAULT_SLIDE = "slide1"
STANDINGS_DEFAULT_HEADER = "hero"

STANDINGS_FORMATS: dict[str, tuple[int, int]] = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}

# (id, label_fa, lens, slice, header_mode, default_mods)
STANDINGS_SLIDES: list[tuple[str, str, str, str, str, list[str]]] = [
    ("slide1", "اسلاید ۱: جدول اصلی + کورس صدر (پیشنهادی)", "classic", "top10", "hero", ["table"]),
    ("slide2", "اسلاید ۲: جدول عدالت آماری (PTS vs xPTS)", "xpts", "top10", "compact", ["table", "justice"]),
    ("slide3", "اسلاید ۳: نقشه قدرت لیگ (رادار xG / xGA)", "xg", "top10", "compact", ["quadrant"]),
    ("slide4", "اسلاید ۴: ماراتن قهرمانی و نبرد بقا", "classic", "top10", "compact", ["title_race", "relegation"]),
    ("slide5", "اسلاید ۵: جدول کامل لیگ (نسخه جامع)", "classic", "full", "compact", ["table"]),
]


def _sgn(v: int) -> str:
    return f"+{fa(v)}" if v > 0 else (f"−{fa(abs(v))}" if v < 0 else "۰")


def _sgn_f(v: float) -> str:
    return f"+{fa(f1(v))}" if v > 0.05 else (f"−{fa(f1(abs(v)))}" if v < -0.05 else "۰.۰")


def _get_zone(lg: dict[str, Any], rank: int) -> str:
    z = lg.get("zones") or {}
    for k in ("ucl", "uel", "uecl", "rel"):
        rng = z.get(k)
        if isinstance(rng, list) and len(rng) == 2 and rng[0] <= rank <= rng[1]:
            return k
    return "none"


def get_standings_modules(
    lg: dict[str, Any], slide: str = STANDINGS_DEFAULT_SLIDE
) -> tuple[list[dict[str, Any]], list[str]]:
    """استخراج ۵ ماژول مستقل جدول رده‌بندی بر اساس دیتای واقعی موجود (قانون null ≠ 0)."""
    teams = lg.get("teams") or []
    has_table = len(teams) >= 2
    has_xpts = any(t.get("xpts") is not None for t in teams)
    has_xg = any(t.get("xg90") is not None and t.get("xga90") is not None for t in teams)
    has_odds = any((t.get("titleP") or 0) > 0 or (t.get("top4P") or 0) > 0 for t in teams)
    has_rel = len(teams) >= 5 and any((t.get("relP") or 0) > 0 for t in teams[-5:])

    sl_def = next((mids for sid, _, _, _, _, mids in STANDINGS_SLIDES if sid == slide), ["table"])
    def_set = set(sl_def)

    specs = [
        ("table", "جدول رده‌بندی لیگ (کلاسیک / xPTS / xG)", has_table, False, "full"),
        ("justice", "کارت‌های عدالت آماری (خوش‌شانس و بدشانس)", has_xpts, True, "full"),
        ("quadrant", "نقشه قدرت تاکتیکی لیگ (xG/90 vs xGA/90)", has_xg, False, "full"),
        ("title_race", "ماراتن قهرمانی و سهمیه لیگ قهرمانان", has_odds, True, "full"),
        ("relegation", "منطقه قرمز و نبرد بقا (Relegation Risk)", has_rel, True, "full"),
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
        return f'<div class="st-brand" dir="ltr"><img src="{uri}" alt="XGPedia" class="st-brand-img"></div>'
    return '<div class="st-brand" dir="ltr"><div class="fd st-brand-txt"><span style="color:#E62E45">XG</span><span style="color:#F8FAFC">Pedia</span></div></div>'


def _crest_svg(t: dict[str, Any], sz: int, uid: str) -> str:
    from src.xgpedia.providers.pl_badges_free import get_pl_badge_data_uri
    _luri = t.get("logoUrl") or get_pl_badge_data_uri(
        str(t.get("name") or t.get("team") or ""),
        tla_hint=str(t.get("code") or ""),
        fetch_network=False,
    )
    if _luri:
        return (
            f'<div style="width:{sz}px;height:{sz}px;flex-shrink:0;display:flex;align-items:center;justify-content:center;'
            f'border-radius:50%;background:rgba(7,13,29,.65);padding:{max(2, sz // 12)}px;filter:drop-shadow(0 4px 10px rgba(0,0,0,.5))">'
            f'<img src="{esc(_luri)}" alt="{esc(t.get("code") or "")}" style="width:100%;height:100%;object-fit:contain;display:block"/></div>'
        )
    p = str(t.get("color") or "#E62E45")
    s = str(t.get("sec") or t.get("secondary") or "#FFFFFF")
    cd = esc(str(t.get("code") or "FC")[:3].upper())
    d = "M90 16L150 40V88C150 128 124.5 156.5 90 166C55.5 156.5 30 128 30 88V40Z"
    pill_bg = "#091226" if luminance(p) > 0.62 else "rgba(6,12,28,0.66)"
    sw = 8 if sz <= 40 else 5.5
    fsz = 44 if sz <= 36 else 34
    return (
        f'<svg width="{sz}" height="{sz}" viewBox="0 0 180 180" fill="none" style="filter:drop-shadow(0 6px 12px rgba(0,0,0,.5));flex-shrink:0;display:block">'
        f'<defs><linearGradient id="g_{uid}" x1="20" y1="15" x2="160" y2="165" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{s}" stop-opacity=".95"/><stop offset=".5" stop-color="{p}" stop-opacity=".95"/><stop offset="1" stop-color="{s}" stop-opacity=".75"/></linearGradient>'
        f'<clipPath id="cl_{uid}"><path d="{d}"/></clipPath></defs>'
        f'<g clip-path="url(#cl_{uid})"><rect x="25" y="12" width="130" height="158" fill="{p}"/>'
        f'<path d="M25 112L155 56V84L25 140Z" fill="{s}" fill-opacity=".28"/>'
        f'<path d="M90 16L150 40V58L90 34L30 58V40Z" fill="{s}" fill-opacity=".88"/>'
        f'<ellipse cx="90" cy="30" rx="65" ry="26" fill="#fff" fill-opacity=".16"/></g>'
        f'<path d="{d}" stroke="url(#g_{uid})" stroke-width="{sw}"/>'
        f'<rect x="34" y="64" width="112" height="52" rx="14" fill="{pill_bg}" stroke="{s}" stroke-opacity=".55" stroke-width="2.5"/>'
        f'<text x="90" y="102" text-anchor="middle" fill="#fff" font-family="Space Grotesk,JetBrains Mono,sans-serif" font-weight="800" font-size="{fsz}" letter-spacing="1.5">{cd}</text></svg>'
    )


def _mod_hdr(title: str, right_html: str, bar_col: str = "#E62E45") -> str:
    return (
        f'<div class="mh fbw"><div class="fi st-g10">'
        f'<span class="st-mbar" style="background:{bar_col}"></span>'
        f'<h3 class="mt">{esc(title)}</h3></div><div>{right_html}</div></div>'
    )


def _form_strip(form: list[str], dense: bool = False) -> str:
    if not form:
        return '<span class="fm" style="color:#64748B">—</span>'
    dots = []
    for idx, ch in enumerate(form):
        fl = " fl" if idx == len(form) - 1 else ""
        dots.append(f'<span class="fdot f{esc(ch)}{fl}">{esc(ch)}</span>')
    return f'<div dir="rtl" class="fi fc {"st-g4" if dense else "st-g6"}">{"".join(dots)}</div>'


def _render_hero(lg: dict[str, Any], header_mode: str, is_wide: bool) -> str:
    teams = lg.get("teams") or []
    if len(teams) < 3:
        return ""
    t1, t2, t3 = teams[0], teams[1], teams[2]
    xg_teams = [t for t in teams if t.get("xg90") is not None and t.get("xga90") is not None]
    xpts_teams = [t for t in teams if t.get("xpts") is not None]
    best_atk = max(xg_teams, key=lambda t: float(t["xg90"])) if xg_teams else max(teams, key=lambda t: int(t.get("gf") or 0))
    best_def = min(xg_teams, key=lambda t: float(t["xga90"])) if xg_teams else min(teams, key=lambda t: int(t.get("ga") or 0))
    lk = sorted(xpts_teams, key=lambda t: float(t["pts"]) - float(t["xpts"]), reverse=True) if xpts_teams else teams
    m_o, m_u = lk[0], lk[-1]

    if header_mode == "compact":
        def _kpi(lbl: str, t: dict[str, Any], val: str, vc: str, ac: str) -> str:
            return (
                f'<div class="st-ckpi" style="border-right:3.5px solid {ac}">'
                + _crest_svg(t, 34, "ck_" + str(t.get("code", "")) + "_" + str(len(lbl)))
                + f'<div class="st-minw-0"><div class="st-ckpi-lbl">{esc(lbl)}</div>'
                f'<div class="fbw st-g6"><span class="st-ckpi-nm">{esc(t.get("name", ""))}</span>'
                f'<span dir="ltr" class="fm st-ckpi-v" style="color:{vc}">{esc(val)}</span></div></div></div>'
            )

        v_atk = fa(f2(best_atk["xg90"])) if best_atk.get("xg90") is not None else f"{fa(best_atk.get('gf', 0))} گل"
        v_def = fa(f2(best_def["xga90"])) if best_def.get("xga90") is not None else f"{fa(best_def.get('ga', 0))} خورده"
        v_o = _sgn_f(float(m_o["pts"]) - float(m_o["xpts"])) if m_o.get("xpts") is not None else f"{fa(m_o.get('pts', 0))} امت"
        v_u = _sgn_f(float(m_u["pts"]) - float(m_u["xpts"])) if m_u.get("xpts") is not None else f"{fa(m_u.get('pts', 0))} امت"
        return (
            f'<div class="st-ckpi-grid" style="grid-template-columns:repeat({2 if is_wide else 4},1fr)">'
            f'{_kpi("بهترین حمله", best_atk, v_atk, "#6EE7B7", "#10B981")}'
            f'{_kpi("بهترین دفاع", best_def, v_def, "#7DD3FC", "#38BDF8")}'
            f'{_kpi("بیشترین بازدهی", m_o, v_o, "#FCD34D", "#F59E0B")}'
            f'{_kpi("بدشانس‌ترین تیم", m_u, v_u, "#FF7A8C", "#E62E45")}</div>'
        )

    def _cc(t: dict[str, Any], idx: int) -> str:
        pts_v = int(t.get("pts") or 0)
        mp_v = max(1, int(t.get("mp") or 1))
        ppg = pts_v / mp_v
        gd_v = int(t.get("gf") or 0) - int(t.get("ga") or 0)
        return (
            f'<div class="st-cc" style="border-color:{"rgba(255,255,255,.22)" if idx == 0 else "rgba(255,255,255,.1)"}">'
            f'<div class="fbw st-g4"><div class="fi st-g6 st-minw-0"><span class="st-cc-dot" style="background:{t.get("color", "#E62E45")}"></span>'
            f'<span class="st-cc-nm">{esc(t.get("name", ""))}</span></div>'
            f'<span class="fm st-cc-p" style="color:{"#FCD34D" if idx == 0 else "#CBD5E1"}">{fa(pts_v)} امت</span></div>'
            f'<div class="fbw st-cc-row"><span>امتیاز/بازی</span><span class="fm" style="color:#fff;font-weight:900">{fa(f2(ppg))}</span></div>'
            f'<div class="fbw st-cc-row st-cc-sep"><span>تفاضل گل</span><span dir="ltr" class="fm" style="color:#6EE7B7;font-weight:900">{_sgn(gd_v)}</span></div></div>'
        )

    pills = []
    if t1.get("xg90") is not None:
        pills.append(f'<span class="st-hpill st-hp-g">xG <b class="fm">{fa(f2(t1["xg90"]))}</b></span>')
    if t1.get("xga90") is not None:
        pills.append(f'<span class="st-hpill st-hp-b">xGA <b class="fm">{fa(f2(t1["xga90"]))}</b></span>')
    if t1.get("xpts") is not None:
        pills.append(f'<span class="st-hpill st-hp-w">xPTS <b class="fm">{fa(f1(t1["xpts"]))}</b></span>')
    if not pills:
        pills.append(f'<span class="st-hpill st-hp-g">امتیاز <b class="fm">{fa(t1.get("pts", 0))}</b></span>')
        pills.append(f'<span class="st-hpill st-hp-b">تفاضل <b class="fm">{_sgn(int(t1.get("gf", 0)) - int(t1.get("ga", 0)))}</b></span>')

    tot_pts3 = max(1, int(t1.get("pts") or 0) + int(t2.get("pts") or 0) + int(t3.get("pts") or 0))
    w1_p = round(int(t1.get("pts") or 0) * 100.0 / tot_pts3, 1)
    w2_p = round(int(t2.get("pts") or 0) * 100.0 / tot_pts3, 1)
    w3_p = max(0.0, round(100.0 - w1_p - w2_p, 1))

    return (
        f'<div class="xe st-hero" style="border-color:{t1.get("color", "#E62E45")}48">'
        f'<div class="st-hero-glow" style="background:radial-gradient(circle,{t1.get("color", "#E62E45")}38,transparent 68%)"></div>'
        f'<div class="st-hero-top" style="grid-template-columns:{"1fr" if is_wide else "1fr 1fr"}">'
        f'<div class="fi st-g14 st-minw-0">{_crest_svg(t1, 78 if is_wide else 84, "hero")}'
        f'<div class="st-minw-0"><h1 class="st-hero-name">{esc(t1.get("name", ""))}</h1>'
        f'<p class="st-hero-tag">{esc(fa(lg.get("leaderTag", "")))}</p>'
        f'<div class="fi st-g8" style="margin-top:10px">{"".join(pills)}</div></div></div>'
        f'<div class="st-mc-box"><div class="fbw"><span class="st-mc-title"><span class="st-dot-red"></span>کورس واقعی ۳ تیم صدر جدول</span>'
        f'<span dir="ltr" class="fm st-mc-sub">LIVE TOP 3</span></div>'
        '<div class="tpc">'
        + f'<div class="tps" style="width:{w1_p}%;background:{t1.get("color", "#E62E45")};color:{contrast_ink(str(t1.get("color", "#E62E45")))}">{esc(t1.get("code", ""))} {fa(t1.get("pts", 0))}</div>'
        + f'<div class="tps" style="width:{w2_p}%;background:{t2.get("color", "#38BDF8")};color:{contrast_ink(str(t2.get("color", "#38BDF8")))}">{esc(t2.get("code", ""))} {fa(t2.get("pts", 0))}</div>'
        + f'<div class="tps" style="width:{w3_p}%;background:{t3.get("color", "#F59E0B")};color:{contrast_ink(str(t3.get("color", "#F59E0B")))}">{esc(t3.get("code", ""))} {fa(t3.get("pts", 0))}</div>'
        + f'</div><div class="st-cc-grid">{_cc(t1, 0)}{_cc(t2, 1)}{_cc(t3, 2)}</div></div></div></div>'
    )


def _render_table_module(
    lg: dict[str, Any],
    *,
    lens: str,
    table_slice: str,
    spotlight: str | None,
    show_mov: bool,
    show_leg: bool,
    span_cls: str,
) -> str:
    all_t = lg.get("teams") or []
    if table_slice == "top6":
        teams = all_t[:6]
    elif table_slice == "top10":
        teams = all_t[:10]
    elif table_slice == "bottom":
        teams = all_t[-min(8, len(all_t)):]
    else:
        teams = all_t

    dn = len(teams) > 10
    if lens == "classic":
        cols = "58px minmax(0,1.75fr) 46px 104px 66px 132px 68px" if dn else "68px minmax(0,1.8fr) 54px 118px 74px 176px 84px"
        hdrs = '<span class="tc">رتبه</span><span class="tr pr2">باشگاه</span><span class="tc">بازی</span><span class="tc">ب · م · ش</span><span class="tc">تفاضل</span><span class="tc">فرم ۵ بازی</span><span class="tc">امتیاز</span>'
    elif lens == "xpts":
        cols = "56px minmax(0,1.65fr) 58px 66px minmax(110px,1.25fr) 74px" if dn else "66px minmax(0,1.65fr) 68px 76px minmax(150px,1.35fr) 92px"
        hdrs = '<span class="tc">رتبه</span><span class="tr pr2">باشگاه</span><span class="tc">امتیاز</span><span class="tc">xPTS</span><span class="tc">شاخص عدالت آماری</span><span class="tc">اختلاف</span>'
    else:
        cols = "56px minmax(0,1.6fr) 64px 64px 70px 84px 66px" if dn else "66px minmax(0,1.65fr) 74px 74px 80px 106px 80px"
        hdrs = '<span class="tc">رتبه</span><span class="tr pr2">باشگاه</span><span class="tc">xG/90</span><span class="tc">xGA/90</span><span class="tc">xGD</span><span class="tc">شانس سهمیه</span><span class="tc">امتیاز</span>'

    rows_html = []
    for t in teams:
        rk = int(t.get("rank") or 1)
        gd = int(t.get("gf") or 0) - int(t.get("ga") or 0)
        z = _get_zone(lg, rk)
        ld = rk == 1
        sp = bool(spotlight and str(t.get("code", "")).upper() == spotlight.upper())
        mv = int(t.get("mov") or 0)
        mv_h = ""
        if show_mov:
            if mv > 0:
                mv_h = f'<span class="fm" style="color:#34D399;font-size:{11 if dn else 13}px;font-weight:800">▲{fa(mv)}</span>'
            elif mv < 0:
                mv_h = f'<span class="fm" style="color:#FB7185;font-size:{11 if dn else 13}px;font-weight:800">▼{fa(abs(mv))}</span>'
            else:
                mv_h = f'<span class="fm" style="color:#64748B;font-size:{11 if dn else 13}px">•</span>'

        rc = f'<div class="fi fc st-g4"><span class="fm" style="font-weight:900;font-size:{18 if dn else 22}px;color:{"#FCD34D" if ld else "#FFF"}">{fa(rk)}</span>{mv_h}</div>'
        cc = f'<div class="fi st-g10 st-minw-0">{_crest_svg(t, 28 if dn else 36, f"r{rk}")}<span style="font-size:{17 if dn else 21}px;font-weight:900;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(t.get("name", ""))}</span></div>'

        if lens == "classic":
            gc = "st-gd-pos" if gd > 0 else ("st-gd-neg" if gd < 0 else "st-gd-zero")
            cells = (
                f'{rc}{cc}'
                f'<div class="tc" style="font-weight:800;font-size:{16 if dn else 19}px;color:#CBD5E1">{fa(t.get("mp", 0))}</div>'
                f'<div class="tc" style="font-weight:700;font-size:{14 if dn else 17}px;white-space:nowrap"><span style="color:#6EE7B7">{fa(t.get("w", 0))}</span> · <span style="color:#FCD34D">{fa(t.get("d", 0))}</span> · <span style="color:#FB7185">{fa(t.get("l", 0))}</span></div>'
                f'<div class="fc"><span dir="ltr" class="st-gd {gc}" style="font-size:{14 if dn else 17}px">{_sgn(gd)}</span></div>'
                f'<div>{_form_strip(t.get("form") or [], dn)}</div>'
                f'<div class="fc"><span style="font-size:{20 if dn else 25}px;font-weight:900;color:{"#FCD34D" if ld else "#FFF"}">{fa(t.get("pts", 0))}</span></div>'
            )
        elif lens == "xpts":
            xpts = t.get("xpts")
            if xpts is None:
                cells = f'{rc}{cc}<div class="tc" style="font-weight:900">{fa(t.get("pts", 0))}</div><div class="tc">—</div><div class="tc">—</div><div class="tc">—</div>'
            else:
                df = float(t.get("pts") or 0) - float(xpts)
                pc = min(48.0, abs(df) / 5.5 * 48.0)
                pos = df >= 0
                dc = "#34D399" if pos else "#FB7185"
                bar_s = f"left:50%;width:{f1(pc)}%" if pos else f"right:50%;width:{f1(pc)}%"
                pl = "st-gd-pos" if pos else "st-gd-neg"
                cells = (
                    f'{rc}{cc}'
                    f'<div class="tc" style="font-weight:900;font-size:{18 if dn else 22}px">{fa(t.get("pts", 0))}</div>'
                    f'<div class="tc" style="font-weight:800;font-size:{16 if dn else 19}px;color:#7DD3FC">{fa(f1(xpts))}</div>'
                    f'<div style="padding:0 8px"><div class="dtrack"><div class="dmid"></div><div class="dfill" style="{bar_s};background:{dc}"></div></div></div>'
                    f'<div class="fc"><span dir="ltr" class="st-gd {pl}" style="font-size:{14 if dn else 17}px">{_sgn_f(df)}</span></div>'
                )
        else:
            xg90, xga90 = t.get("xg90"), t.get("xga90")
            xd = (float(xg90) - float(xga90)) if (xg90 is not None and xga90 is not None) else None
            xc = "#6EE7B7" if (xd is not None and xd >= 0.4) else ("#FB7185" if (xd is not None and xd <= -0.3) else "#E2E8F0")
            t4p, rlp = float(t.get("top4P") or 0), float(t.get("relP") or 0)
            pv = f"{fa(f1(t4p))}٪" if t4p > 0 else (f"سقوط {fa(round(rlp))}٪" if rlp > 10 else "—")
            cells = (
                f'{rc}{cc}'
                f'<div class="tc" style="font-weight:800;color:#6EE7B7;font-size:{15 if dn else 18}px">{fa(f2(xg90)) if xg90 is not None else "—"}</div>'
                f'<div class="tc" style="font-weight:800;color:#7DD3FC;font-size:{15 if dn else 18}px">{fa(f2(xga90)) if xga90 is not None else "—"}</div>'
                f'<div dir="ltr" class="tc" style="font-weight:900;color:{xc};font-size:{15 if dn else 18}px">{_sgn_f(xd) if xd is not None else "—"}</div>'
                f'<div class="fc"><span class="st-gd st-gd-zero" style="font-size:{12 if dn else 14}px">{pv}</span></div>'
                f'<div class="tc" style="font-weight:900;font-size:{19 if dn else 23}px;color:{"#FCD34D" if ld else "#FFF"}">{fa(t.get("pts", 0))}</div>'
            )
        rcls = f"srow {'row-' + z if z != 'none' else ''} {'lead' if ld else ''} {'spot' if sp else ''}"
        rows_html.append(f'<div class="{rcls}" style="grid-template-columns:{cols};padding:{"5px 6px" if dn else "9px 8px"};--sc:{t.get("color", "#E62E45")}"><span class="zbar z-{z}"></span>{cells}</div>')

    zl = lg.get("zoneLabels") or {}
    leg = ""
    if show_leg:
        leg = (
            f'<div class="st-legend"><div class="fi st-g14">'
            f'<span class="fi st-g6"><span class="st-zdot" style="background:#2563EB"></span>{esc(zl.get("ucl", "سهمیه اول"))}</span>'
            f'<span class="fi st-g6"><span class="st-zdot" style="background:#F97316"></span>{esc(zl.get("uel", "سهمیه دوم"))}</span>'
            f'<span class="fi st-g6"><span class="st-zdot" style="background:#10B981"></span>{esc(zl.get("uecl", "سهمیه سوم"))}</span>'
            f'<span class="fi st-g6"><span class="st-zdot" style="background:#E62E45"></span>{esc(zl.get("rel", "منطقه سقوط"))}</span>'
            f'</div><span class="fm" style="font-size:12px;color:#94A3B8" dir="ltr">{"Δ = PTS − xPTS" if lens == "xpts" else "SORTED BY PTS · GD · GF"}</span></div>'
        )
    tt = "جدول عدالت آماری (PTS در برابر xPTS)" if lens == "xpts" else ("جدول قدرت فنی و شانس سهمیه" if lens == "xg" else "جدول رده‌بندی لیگ")
    tg = "EXPECTED POINTS JUSTICE" if lens == "xpts" else ("XG POWER & ODDS" if lens == "xg" else "LIVE STANDINGS")
    return (
        f'<div class="xm st-grow {"dense" if dn else ""} {span_cls}">'
        + _mod_hdr(tt, f'<span dir="ltr" class="fm st-sub-tag">{tg}</span>', "#38BDF8" if lens == "xpts" else "#E62E45")
        + f'<div class="st-thdr" style="grid-template-columns:{cols}">{hdrs}</div>'
        f'<div class="st-rows" style="gap:{"4px" if dn else "6px"}">{"".join(rows_html)}</div>{leg}</div>'
    )


def _render_justice_module(lg: dict[str, Any], span_cls: str) -> str:
    teams = [t for t in (lg.get("teams") or []) if t.get("xpts") is not None]
    if len(teams) < 2:
        return ""
    sr = sorted(teams, key=lambda t: float(t["pts"]) - float(t["xpts"]), reverse=True)

    def _card(t: dict[str, Any], lbl: str, ac: str, ds: str) -> str:
        df = float(t["pts"]) - float(t["xpts"])
        return (
            f'<div class="xe st-jcard" style="border-right:6px solid {ac}">'
            f'<div class="fbw"><span class="st-jbadge" style="color:{ac};border-color:{ac}66;background:{ac}22">{esc(lbl)}</span>'
            f'<span dir="ltr" class="fm" style="font-size:22px;font-weight:900;color:{ac}">{_sgn_f(df)} PTS</span></div>'
            + '<div class="fi st-g12" style="margin:6px 0">' + _crest_svg(t, 48, "jc_" + str(t.get("code", "")))
            + f'<div><div style="font-size:23px;font-weight:900;color:#fff">{esc(t.get("name", ""))}</div>'
            f'<div style="font-size:15px;font-weight:700;color:#CBD5E1">واقعی: {fa(t["pts"])} امتیاز · مورد انتظار: {fa(f1(t["xpts"]))} xPTS</div></div></div>'
            f'<p style="font-size:14.5px;font-weight:600;color:#CBD5E1;line-height:1.45">{esc(ds)}</p></div>'
        )

    return (
        f'<div class="st-jgrid {span_cls}">'
        + _card(sr[0], "کارآمدترین / خوش‌شانس‌ترین", "#34D399", "بیشترین امتیازگیری فراتر از کیفیت موقعیت‌های خلق‌شده و دریافتی در فصل جاری.")
        + _card(sr[-1], "بدشانس‌ترین تیم جدول", "#FB7185", "کیفیت بازی و موقعیت‌سازی بهتر از رتبه فعلی؛ پتانسیل بالای صعود در هفته‌های آینده.")
        + "</div>"
    )


def _render_quadrant_module(lg: dict[str, Any], spotlight: str | None, span_cls: str) -> str:
    teams = [t for t in (lg.get("teams") or []) if t.get("xg90") is not None and t.get("xga90") is not None]
    if len(teams) < 4:
        return ""
    xv = [float(t["xg90"]) for t in teams]
    yv = [float(t["xga90"]) for t in teams]
    avg_x = sum(xv) / len(xv)
    avg_y = sum(yv) / len(yv)
    lo_x, hi_x = max(0.2, min(xv) - 0.15), max(xv) + 0.15
    lo_y, hi_y = max(0.2, min(yv) - 0.15), max(yv) + 0.15
    W, H, pL, pR, pT, pB = 940, 560, 74, 46, 48, 64
    pW, pH = W - pL - pR, H - pT - pB
    tx = lambda v: pL + (v - lo_x) / max(0.1, hi_x - lo_x) * pW
    ty = lambda v: pT + (v - lo_y) / max(0.1, hi_y - lo_y) * pH
    ax, ay = tx(avg_x), ty(avg_y)

    pts_svg = []
    for t in teams:
        x, y = tx(float(t["xg90"])), ty(float(t["xga90"]))
        sp = bool(spotlight and str(t.get("code", "")).upper() == spotlight.upper())
        r = 13 if sp else (11 if int(t.get("rank", 99)) <= 3 else 8.5)
        col = str(t.get("color") or "#E62E45")
        cd = esc(str(t.get("code") or "")[:3])
        pts_svg.append(
            f'<g>'
            + (f'<circle cx="{f1(x)}" cy="{f1(y)}" r="{r + 8}" fill="{col}" fill-opacity=".22"/>' if (sp or int(t.get("rank", 99)) <= 3) else "")
            + f'<circle cx="{f1(x)}" cy="{f1(y)}" r="{r}" fill="{col}" stroke="#fff" stroke-width="{3 if sp else 2}"/>'
            f'<rect x="{f1(x - 22)}" y="{f1(y - 31)}" width="44" height="19" rx="6" fill="{"#E62E45" if sp else "#091226e6"}" stroke="{"#fff" if sp else col}" stroke-opacity=".85" stroke-width="1.2"/>'
            f'<text x="{f1(x)}" y="{f1(y - 17)}" text-anchor="middle" fill="#fff" font-family="Space Grotesk,JetBrains Mono" font-size="11.5" font-weight="800">{cd}</text></g>'
        )

    b_a = max(teams, key=lambda t: float(t["xg90"]))
    b_d = min(teams, key=lambda t: float(t["xga90"]))
    b_x = max(teams, key=lambda t: float(t["xg90"]) - float(t["xga90"]))

    def _hc(t: dict[str, Any], uid: str, lbl: str, val: str, vc: str) -> str:
        return (
            f'<div class="st-qcard">{_crest_svg(t, 40, uid)}<div class="st-minw-0">'
            f'<div style="font-size:13px;font-weight:700;color:#94A3B8">{esc(lbl)}</div>'
            f'<div style="font-size:18px;font-weight:900;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(t.get("name", ""))}</div>'
            f'<div dir="ltr" class="fm" style="font-size:15px;font-weight:800;color:{vc};text-align:right">{esc(val)}</div></div></div>'
        )

    return (
        f'<div class="xe st-grow {span_cls}">'
        + _mod_hdr("نقشه قدرت تاکتیکی لیگ (حمله در برابر دفاع)", '<span dir="ltr" class="fm" style="font-size:15px;font-weight:800;color:#6EE7B7">xG/90 vs xGA/90 QUADRANT</span>', "#34D399")
        + f'<div class="fc st-grow" dir="ltr"><svg style="width:100%;height:100%;max-height:580px" viewBox="0 0 {W} {H}" fill="none">'
        f'<defs><linearGradient id="qE" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#10B981" stop-opacity=".16"/><stop offset="1" stop-color="#10B981" stop-opacity=".02"/></linearGradient>'
        f'<linearGradient id="qD" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#E62E45" stop-opacity=".17"/><stop offset="1" stop-color="#E62E45" stop-opacity=".02"/></linearGradient></defs>'
        f'<rect x="{f1(ax)}" y="{pT}" width="{f1(W - pR - ax)}" height="{f1(ay - pT)}" fill="url(#qE)" rx="8"/>'
        f'<rect x="{pL}" y="{f1(ay)}" width="{f1(ax - pL)}" height="{f1(H - pB - ay)}" fill="url(#qD)" rx="8"/>'
        f'<rect x="{pL}" y="{pT}" width="{pW}" height="{pH}" rx="12" stroke="rgba(255,255,255,0.14)" stroke-width="1.5" fill="rgba(6,13,30,0.4)"/>'
        f'<line x1="{f1(ax)}" y1="{pT}" x2="{f1(ax)}" y2="{H - pB}" stroke="#F8FAFC" stroke-opacity=".35" stroke-width="1.8" stroke-dasharray="6 6"/>'
        f'<line x1="{pL}" y1="{f1(ay)}" x2="{W - pR}" y2="{f1(ay)}" stroke="#F8FAFC" stroke-opacity=".35" stroke-width="1.8" stroke-dasharray="6 6"/>'
        f'<g font-family="Vazirmatn" font-weight="800" font-size="16">'
        f'<rect x="{W - pR - 175}" y="{pT + 12}" width="163" height="30" rx="15" fill="rgba(16,185,129,.16)" stroke="rgba(52,211,153,.4)"/><text x="{W - pR - 93}" y="{pT + 32}" text-anchor="middle" fill="#34D399">مدعیان بی‌رقیب ★</text>'
        f'<rect x="{pL + 12}" y="{pT + 12}" width="176" height="30" rx="15" fill="rgba(56,189,248,.14)" stroke="rgba(56,189,248,.35)"/><text x="{pL + 100}" y="{pT + 32}" text-anchor="middle" fill="#7DD3FC">منظم دفاعی · کم‌موقعیت</text>'
        f'<rect x="{W - pR - 185}" y="{H - pB - 42}" width="173" height="30" rx="15" fill="rgba(245,158,11,.14)" stroke="rgba(251,191,36,.35)"/><text x="{W - pR - 98}" y="{H - pB - 22}" text-anchor="middle" fill="#FBBF24">تهاجمی · دفاع آسیب‌پذیر</text>'
        f'<rect x="{pL + 12}" y="{H - pB - 42}" width="136" height="30" rx="15" fill="rgba(230,46,69,.16)" stroke="rgba(251,113,133,.4)"/><text x="{pL + 80}" y="{H - pB - 22}" text-anchor="middle" fill="#FF7A8C">منطقه بحران ⚠</text></g>'
        f'<text x="{pL + pW / 2}" y="{H - 12}" text-anchor="middle" fill="#E2E8F0" font-family="Vazirmatn" font-size="17" font-weight="800">قدرت حمله: امید گل تولیدی در ۹۰ دقیقه (xG/90) ⟶</text>'
        f'<text x="20" y="{pT + pH / 2}" text-anchor="middle" fill="#E2E8F0" font-family="Vazirmatn" font-size="17" font-weight="800" transform="rotate(-90 20 {pT + pH / 2})">صلابت دفاعی: امید گل دریافتی کمتر (xGA/90) ⟶</text>'
        f'{"".join(pts_svg)}</svg></div>'
        '<div class="st-qfoot">'
        + _hc(b_a, "qa1", "خطرناک‌ترین حمله", fa(f2(b_a["xg90"])) + " xG/90", "#6EE7B7")
        + _hc(b_d, "qa2", "مستحکم‌ترین دفاع", fa(f2(b_d["xga90"])) + " xGA/90", "#7DD3FC")
        + _hc(b_x, "qa3", "بهترین تفاضل امید گل", _sgn_f(float(b_x["xg90"]) - float(b_x["xga90"])) + " xGD/90", "#FCD34D") + '</div></div>'
    )


def _render_title_race_module(lg: dict[str, Any], span_cls: str) -> str:
    t5 = (lg.get("teams") or [])[:5]
    rows = []
    for idx, t in enumerate(t5):
        w1 = min(100.0, max(0.0, float(t.get("titleP") or 0)))
        w2 = max(0.0, min(100.0 - w1, float(t.get("top4P") or 0) - w1))
        fdr_html = "".join(
            f'<span class="fm st-fdr st-fdr-{d}">{esc(opp)}</span>'
            for opp, d in (t.get("fdr") or [])[:3]
        ) or '<span class="fm" style="color:#64748B">—</span>'
        is_first = idx == 0
        rows.append(
            f'<div class="srow st-race-row" style="grid-template-columns:42px minmax(0,1.35fr) minmax(0,1.65fr) 150px;border-color:{"rgba(245,196,81,.45)" if is_first else "rgba(59,130,246,.28)"}">'
            f'<span class="zbar" style="background:{"#F5C451" if is_first else "#3B82F6"}"></span>'
            f'<span class="fm tc" style="font-size:21px;font-weight:900;color:{"#F5C451" if is_first else "#BFDBFE"}">{fa(t.get("rank", idx + 1))}</span>'
            f'<div class="fi st-g10 st-minw-0">{_crest_svg(t, 34, f"tr{idx}")}<div class="st-minw-0"><div style="font-size:19px;font-weight:900;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(t.get("name", ""))}</div>'
            f'<div style="font-size:13px;font-weight:700;color:#94A3B8">{fa(t.get("pts", 0))} امتیاز · تفاضل {_sgn(int(t.get("gf", 0)) - int(t.get("ga", 0)))}</div></div></div>'
            f'<div class="fcol st-g6"><div class="fbw" style="font-size:13px;font-weight:800"><span style="color:#F5C451">قهرمانی {fa(f1(w1))}٪</span><span style="color:#93C5FD">سهمیه {fa(f1(float(t.get("top4P") or 0)))}٪</span></div>'
            f'<div class="st-rbar"><div style="width:{f1(w1)}%;background:linear-gradient(90deg,#D97706,#F5C451)"></div><div style="width:{f1(w2)}%;background:linear-gradient(90deg,#1D4ED8,#3B82F6)"></div></div></div>'
            f'<div class="fcol" style="align-items:flex-end;gap:4px"><span style="font-size:11px;font-weight:700;color:#94A3B8">۳ بازی پیش‌رو</span><div dir="ltr" class="fi st-g4">{fdr_html}</div></div></div>'
        )
    return (
        f'<div class="xe st-grow {span_cls}" style="border-color:rgba(59,130,246,.32)">'
        + _mod_hdr("ماراتن قهرمانی و سهمیه لیگ قهرمانان", '<div class="fi st-g12" style="font-size:13px;font-weight:800"><span style="color:#F5C451">● قهرمانی</span><span style="color:#93C5FD">● سهمیه UCL</span></div>', "#F5C451")
        + f'<div class="fcol st-g8 st-grow" style="justify-content:center">{"".join(rows)}</div></div>'
    )


def _render_relegation_module(lg: dict[str, Any], span_cls: str) -> str:
    teams = lg.get("teams") or []
    b5 = teams[-5:]
    rel_start = int((lg.get("zones") or {}).get("rel", [18, 20])[0])
    safe_idx = max(0, min(len(teams) - 1, rel_start - 2))
    safe_pts = int(teams[safe_idx].get("pts") or 12) if teams else 12
    rows = []
    for idx, t in enumerate(b5):
        gp = int(t.get("pts") or 0) - safe_pts
        ir = _get_zone(lg, int(t.get("rank") or 20)) == "rel"
        rw = min(100.0, max(6.0, float(t.get("relP") or 0)))
        rows.append(
            f'<div class="srow st-race-row" style="grid-template-columns:42px minmax(0,1.4fr) minmax(0,1.45fr) 114px;border-color:{"rgba(244,63,94,.42)" if ir else "rgba(148,163,184,.22)"}">'
            f'<span class="zbar" style="background:{"#E11D48" if ir else "#64748B"}"></span>'
            f'<span class="fm tc" style="font-size:20px;font-weight:900;color:{"#FB7185" if ir else "#CBD5E1"}">{fa(t.get("rank", ""))}</span>'
            f'<div class="fi st-g10 st-minw-0">{_crest_svg(t, 34, f"br{idx}")}<div class="st-minw-0"><div style="font-size:19px;font-weight:900;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(t.get("name", ""))}</div>'
            f'<div style="font-size:13px;font-weight:700;color:{"#FECDD3" if ir else "#94A3B8"}">{fa(t.get("pts", 0))} امتیاز · {"در حاشیه امن" if gp >= 0 else f"{fa(abs(gp))} امتیاز تا بقا"}</div></div></div>'
            f'<div class="fcol st-g6"><div class="fbw" style="font-size:13px;font-weight:800"><span style="color:#CBD5E1">احتمال سقوط</span><span style="color:{"#FB7185" if ir else "#E2E8F0"}">{fa(f1(float(t.get("relP") or 0)))}٪</span></div>'
            f'<div class="st-rbar"><div style="width:{f1(rw)}%;background:{"linear-gradient(90deg,#9F1239,#F43F5E)" if ir else "linear-gradient(90deg,#475569,#94A3B8)"}"></div></div></div>'
            f'<div class="fc">{_form_strip((t.get("form") or [])[-3:], True)}</div></div>'
        )
    return (
        f'<div class="xm st-grow {span_cls}" style="background:linear-gradient(165deg,#180e24eb,#090d1cf7);border-color:rgba(244,63,94,.32)">'
        + _mod_hdr("منطقه قرمز و نبرد بقا", '<span dir="ltr" class="fm" style="font-size:14px;font-weight:800;color:#FB7185">RELEGATION RISK</span>', "#E11D48")
        + f'<div class="fcol st-g8 st-grow" style="justify-content:center">{"".join(rows)}</div></div>'
    )


def render_standings_html(
    lg: dict[str, Any],
    *,
    slide: str = STANDINGS_DEFAULT_SLIDE,
    header_mode: str | None = None,
    fmt: str = "4:5",
    lens: str | None = None,
    table_slice: str | None = None,
    spotlight: str | None = None,
    show_mov: bool = True,
    show_leg: bool = True,
    enabled_modules: list[str] | None = None,
    custom_modules: list[dict[str, Any]] | None = None,
) -> str:
    """تولید HTML کامل و ۱۰۰٪ آفلاین کارت ماژولار جدول رده‌بندی (D52)."""
    w, h = STANDINGS_FORMATS.get(fmt, STANDINGS_FORMATS["4:5"])
    is_wide = fmt == "16:9"
    is_story = fmt == "9:16"
    sl_meta = next((s for s in STANDINGS_SLIDES if s[0] == slide), STANDINGS_SLIDES[0])
    eff_lens = lens or sl_meta[2]
    eff_slice = table_slice or sl_meta[3]
    eff_hm = header_mode or sl_meta[4]

    if custom_modules is not None:
        mods = [dict(m) for m in custom_modules if m.get("enabled")]
    else:
        all_mods, _ = get_standings_modules(lg, slide)
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
            spans.append("st-span-full")
        else:
            half_run += 1
            nxt_half = (idx + 1 < len(mods)) and (mods[idx + 1].get("span") == "half") and mods[idx + 1].get("can_half", False)
            if not nxt_half and half_run % 2 == 1:
                half_run = 0
                spans.append("st-span-full")
            else:
                spans.append("st-span-half")

    mods_html = ""
    for m, sc in zip(mods, spans):
        mid = m["id"]
        if mid == "table":
            mods_html += _render_table_module(lg, lens=eff_lens, table_slice=eff_slice, spotlight=spotlight, show_mov=show_mov, show_leg=show_leg, span_cls=sc)
        elif mid == "justice":
            mods_html += _render_justice_module(lg, sc)
        elif mid == "quadrant":
            mods_html += _render_quadrant_module(lg, spotlight, sc)
        elif mid == "title_race":
            mods_html += _render_title_race_module(lg, sc)
        elif mid == "relegation":
            mods_html += _render_relegation_module(lg, sc)

    hero_html = _render_hero(lg, eff_hm, is_wide)
    teams = lg.get("teams") or []
    t1_col = str(teams[0].get("color") or "#E62E45") if teams else "#E62E45"
    t2_col = str(teams[1].get("color") or "#38BDF8") if len(teams) > 1 else "#38BDF8"
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
.tc{{text-align:center}}.tr{{text-align:right}}.pr2{{padding-right:8px}}
.st-g4{{gap:4px}}.st-g6{{gap:6px}}.st-g8{{gap:8px}}.st-g10{{gap:10px}}.st-g12{{gap:12px}}.st-g14{{gap:14px}}.st-minw-0{{min-width:0;flex:1}}.st-grow{{flex:1;min-height:0}}
.st-canvas{{position:relative;width:{w}px;height:{h}px;background:#0D1730;overflow:hidden;display:flex;flex-direction:column;justify-content:space-between;padding:{pad_top} 0 {pad_bot}}}
.st-ambient{{position:absolute;inset:0;pointer-events:none;z-index:0;background:radial-gradient(circle at 84% 22%,{t1_col}36,transparent 46%),radial-gradient(circle at 16% 76%,{t2_col}24,transparent 48%),radial-gradient(circle at 50% 44%,#e62e451e,transparent 54%)}}
.st-bg-svg{{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0}}
.st-scan{{position:absolute;inset:0;pointer-events:none;z-index:0;background:repeating-linear-gradient(to bottom,rgba(255,255,255,.016) 0 1px,transparent 1px 4px)}}
.st-header{{position:relative;z-index:10;padding:12px 36px 8px;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-shrink:0}}
.st-comp-pill{{padding:6px 20px;border-radius:999px;font-size:23px;font-weight:900;display:flex;align-items:center;gap:10px;border:1px solid rgba(255,255,255,.18);background:rgba(21,35,71,.9);color:#F8FAFC}}
.st-round-pill{{padding:6px 18px;border-radius:999px;font-size:20px;font-weight:800;border:1px solid rgba(230,46,69,.5);background:rgba(230,46,69,.18);color:#FF6B7F}}
.st-season-pill{{padding:6px 16px;border-radius:999px;font-size:18px;font-weight:800;border:1px solid rgba(52,211,153,.45);background:rgba(16,185,129,.18);color:#6EE7B7}}
.st-sub-meta{{display:flex;align-items:center;gap:10px;font-size:18px;font-weight:700;color:#CBD5E1;margin-top:6px}}
.st-brand-img{{height:48px;width:auto;display:block}}.st-brand-txt{{font-size:33px;font-weight:800;line-height:1}}
.st-stage-v{{position:relative;z-index:10;flex:1;padding:8px 40px;display:flex;flex-direction:column;gap:12px;overflow:hidden;min-height:0}}
.st-stage-w{{position:relative;z-index:10;flex:1;padding:8px 40px;display:grid;grid-template-columns:5fr 7fr;gap:20px;align-items:stretch;overflow:hidden;min-height:0}}
.st-mods-grid{{flex:1;display:grid;grid-template-columns:1fr 1fr;gap:12px;min-height:0;overflow:hidden;align-content:stretch}}
.st-span-full{{grid-column:1 / -1;min-width:0}}.st-span-half{{grid-column:span 1;min-width:0}}
.xm,.xe{{position:relative;border-radius:24px;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 16px 40px -10px rgba(0,0,0,.58),inset 0 1px 0 rgba(255,255,255,.1)}}
.xm{{background:linear-gradient(170deg,#0f1c38e8,#070e1ff7);border:1px solid rgba(248,250,252,.12);padding:16px 22px}}
.xe{{background:linear-gradient(155deg,#122040ee,#080f22f8);border:1px solid rgba(127,166,232,.22);padding:16px 22px}}
.dense{{padding:12px 16px}}
.mh{{padding-bottom:8px;margin-bottom:8px;border-bottom:1px solid rgba(255,255,255,.12);flex-shrink:0}}.st-mbar{{width:8px;height:24px;border-radius:99px;display:inline-block}}.mt{{font-size:23px;font-weight:900;color:#fff}}.st-sub-tag{{font-size:15px;font-weight:800;color:#94A3B8;letter-spacing:.08em}}
.st-hero{{background:linear-gradient(135deg,#132245f2 0%,#0a1329f7 58%,#1a1126f2 100%);flex-shrink:0}}.st-hero-glow{{position:absolute;right:-40px;top:-40px;width:210px;height:210px;border-radius:999px;pointer-events:none}}
.st-hero-top{{position:relative;z-index:10;display:grid;gap:18px;align-items:center}}.st-hero-name{{font-size:35px;font-weight:900;color:#fff;line-height:1.08}}.st-hero-tag{{font-size:15px;font-weight:700;color:#CBD5E1;margin-top:4px}}
.st-hpill{{padding:4px 12px;border-radius:12px;font-size:14px;font-weight:800}}.st-hp-g{{background:rgba(16,185,129,.12);border:1px solid rgba(52,211,153,.3);color:#6EE7B7}}.st-hp-b{{background:rgba(14,165,233,.12);border:1px solid rgba(56,189,248,.3);color:#7DD3FC}}.st-hp-w{{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);color:#E2E8F0}}
.st-mc-box{{display:flex;flex-direction:column;gap:8px;background:rgba(7,14,32,.82);border:1px solid rgba(255,255,255,.12);border-radius:16px;padding:12px 16px}}
.st-mc-title{{font-size:14px;font-weight:900;color:#F1F5F9;display:flex;align-items:center;gap:8px}}.st-mc-sub{{font-size:11px;font-weight:800;color:#94A3B8;letter-spacing:.08em}}
.tpc{{width:100%;height:28px;border-radius:999px;overflow:hidden;display:flex;background:#070d1deb;border:1.5px solid rgba(255,255,255,.15)}}.tps{{height:100%;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:13px;white-space:nowrap}}
.st-cc-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}}.st-cc{{border-radius:12px;background:rgba(11,21,43,.9);border:1px solid rgba(255,255,255,.1);padding:7px 10px;display:flex;flex-direction:column;gap:4px}}
.st-cc-dot{{width:10px;height:10px;border-radius:99px;flex-shrink:0}}.st-cc-nm{{font-size:13px;font-weight:900;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.st-cc-p{{font-size:12px;font-weight:900}}
.st-cc-row{{font-size:11.5px;font-weight:700;color:#94A3B8}}.st-cc-sep{{padding-top:4px;border-top:1px solid rgba(255,255,255,.1)}}
.st-ckpi-grid{{display:grid;gap:10px;flex-shrink:0}}.st-ckpi{{border-radius:16px;background:rgba(9,19,41,.9);border:1px solid rgba(255,255,255,.12);padding:10px 14px;display:flex;align-items:center;gap:10px;min-width:0}}
.st-ckpi-lbl{{font-size:11.5px;font-weight:700;color:#94A3B8}}.st-ckpi-nm{{font-size:15px;font-weight:900;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.st-ckpi-v{{font-size:14px;font-weight:900}}
.st-thdr{{display:grid;align-items:center;padding:0 8px 6px;font-size:14px;font-weight:800;color:#94A3B8;flex-shrink:0}}
.st-rows{{flex:1;display:flex;flex-direction:column;min-height:0;overflow:hidden;justify-content:flex-start}}
.srow{{position:relative;display:grid;align-items:center;border-radius:14px;background:linear-gradient(270deg,#0f1c38d4,#0a1328e6);border:1px solid rgba(255,255,255,.07);overflow:hidden}}
.srow.row-ucl{{background:linear-gradient(270deg,rgba(37,99,235,.22) 0%,rgba(15,28,58,.9) 36%,rgba(10,19,40,.94) 100%);border-color:rgba(59,130,246,.32)}}
.srow.row-uel{{background:linear-gradient(270deg,rgba(249,115,22,.22) 0%,rgba(18,26,52,.9) 36%,rgba(10,19,40,.94) 100%);border-color:rgba(251,146,60,.32)}}
.srow.row-uecl{{background:linear-gradient(270deg,rgba(16,185,129,.2) 0%,rgba(13,30,52,.9) 36%,rgba(10,19,40,.94) 100%);border-color:rgba(52,211,153,.32)}}
.srow.row-rel{{background:linear-gradient(270deg,rgba(230,46,69,.24) 0%,rgba(26,16,38,.9) 36%,rgba(12,18,36,.94) 100%);border-color:rgba(244,63,94,.36)}}
.srow.lead{{background:linear-gradient(270deg,rgba(37,99,235,.28) 0%,rgba(18,32,66,.95) 45%,rgba(14,22,46,.95) 100%);border-color:rgba(96,165,250,.48)}}
.srow.spot{{border:1.5px solid var(--sc,#E62E45);box-shadow:0 0 24px -6px var(--sc,#E62E45)}}
.zbar{{position:absolute;right:0;top:4px;bottom:4px;width:5px;border-radius:99px}}.z-ucl{{background:#2563EB}}.z-uel{{background:#F97316}}.z-uecl{{background:#10B981}}.z-rel{{background:#E62E45}}.z-none{{background:rgba(71,85,105,.35)}}
.st-gd{{padding:2px 10px;border-radius:8px;border:1px solid;font-weight:900}}.st-gd-pos{{color:#6EE7B7;background:rgba(16,185,129,.15);border-color:rgba(52,211,153,.35)}}.st-gd-neg{{color:#FB7185;background:rgba(230,46,69,.18);border-color:rgba(230,46,69,.4)}}.st-gd-zero{{color:#CBD5E1;background:rgba(255,255,255,.06);border-color:rgba(255,255,255,.12)}}
.fdot{{width:28px;height:24px;border-radius:7px;display:inline-flex;align-items:center;justify-content:center;font-family:'Space Grotesk',sans-serif;font-size:13px;font-weight:800;border:1.5px solid transparent}}
.fdot.fW{{background:rgba(16,185,129,.15);color:#34D399;border-color:rgba(46,211,140,.3)}}.fdot.fD{{background:rgba(245,158,11,.15);color:#FBBF24;border-color:rgba(245,166,35,.3)}}.fdot.fL{{background:rgba(230,46,69,.17);color:#FB7185;border-color:rgba(244,63,94,.3)}}.fdot.fl{{border-width:2.5px;transform:scale(1.06)}}.fdot.fW.fl{{border-color:#34D399;box-shadow:0 0 12px rgba(52,211,153,.55)}}.fdot.fD.fl{{border-color:#FBBF24;color:#FBBF24;box-shadow:0 0 12px rgba(251,191,36,.50)}}.fdot.fL.fl{{border-color:#F43F5E;box-shadow:0 0 12px rgba(244,63,94,.55)}}
.dense .fdot{{width:21px;height:18px;border-radius:5px;font-size:10.5px}}
.dtrack{{position:relative;height:14px;border-radius:99px;background:rgba(7,13,29,.7);border:1px solid rgba(255,255,255,.08);overflow:hidden}}.dmid{{position:absolute;left:50%;top:0;bottom:0;width:1.5px;background:rgba(255,255,255,.22);z-index:2}}.dfill{{position:absolute;top:1px;bottom:1px;border-radius:99px}}
.st-legend{{padding-top:10px;margin-top:8px;border-top:1px solid rgba(255,255,255,.12);display:flex;align-items:center;justify-content:space-between;font-size:13.5px;font-weight:700;color:#CBD5E1;flex-shrink:0}}
.st-zdot{{width:11px;height:11px;border-radius:99px;display:inline-block}}
.st-jgrid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;flex-shrink:0}}.st-jcard{{justify-content:space-between;gap:8px}}.st-jbadge{{padding:2px 12px;border-radius:99px;border:1px solid;font-size:14px;font-weight:800}}
.st-qfoot{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:8px;padding-top:10px;border-top:1px solid rgba(255,255,255,.12);flex-shrink:0}}
.st-qcard{{padding:10px 12px;border-radius:16px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);display:flex;align-items:center;gap:10px}}
.st-race-row{{padding:9px 12px;gap:12px}}.st-rbar{{height:12px;border-radius:99px;background:#060C1D;border:1px solid rgba(255,255,255,.12);overflow:hidden;display:flex}}
.st-fdr{{padding:2px 7px;border-radius:6px;border:1px solid;font-size:11.5px;font-weight:800}}.st-fdr-3{{background:rgba(230,46,69,.22);border-color:rgba(244,63,94,.55);color:#FDA4AF}}.st-fdr-2{{background:rgba(251,191,36,.18);border-color:rgba(251,191,36,.45);color:#FDE68A}}.st-fdr-1{{background:rgba(16,185,129,.18);border-color:rgba(52,211,153,.45);color:#6EE7B7}}
.st-dot-red{{width:10px;height:10px;border-radius:99px;background:#E62E45;display:inline-block;flex-shrink:0}}
.st-footer{{position:relative;z-index:10;padding:10px 44px 10px;flex-shrink:0}}.st-foot-line{{border-top:1px solid rgba(255,255,255,.12);margin-bottom:8px}}
.st-foot-tag{{font-size:18px;font-weight:800;letter-spacing:.14em;color:#F1F5F9;text-transform:uppercase}}.st-foot-h{{font-size:20px;font-weight:800;color:#fff}}.st-foot-s{{font-size:17px;font-weight:600;color:#CBD5E1}}

footer, footer .fbw, footer .cf-row, footer .fi, footer .cf-left, footer .cf-right, .xg-footer, .foot-row, .card-footer{{flex-wrap:nowrap!important;white-space:nowrap!important;min-width:0!important;}}
footer span, footer div, .pl-foot-tag, .pl-foot-s, .in-foot-tag, .pr-foot-tag, .st-foot-tag, .cf-tag{{white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;min-width:0!important;}}
</style>
</head>
<body>
<div class="st-canvas">
  <div class="st-ambient"></div>
  <svg class="st-bg-svg" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid slice" fill="none">
    <defs>
      <pattern id="tg" width="54" height="54" patternUnits="userSpaceOnUse"><path d="M54 0H0v54" stroke="#F8FAFC" stroke-opacity=".05"/></pattern>
      <radialGradient id="rf" cx="50%" cy="22%" r="46%"><stop offset="0" stop-color="#E62E45" stop-opacity=".22"/><stop offset=".55" stop-color="#E62E45" stop-opacity=".05"/><stop offset="1" stop-color="#E62E45" stop-opacity="0"/></radialGradient>
    </defs>
    <rect width="100%" height="100%" fill="url(#tg)"/>
    <rect x="12" y="12" width="{w - 24}" height="{h - 24}" rx="18" stroke="#F8FAFC" stroke-opacity=".11" stroke-width="1.5"/>
    <g stroke="#F8FAFC" stroke-opacity=".08" stroke-width="1.5"><line x1="{w / 2}" y1="12" x2="{w / 2}" y2="{h - 12}" stroke-dasharray="8 8"/><circle cx="{w / 2}" cy="240" r="145"/></g>
    <circle cx="{w / 2}" cy="240" r="260" fill="url(#rf)"/>
    <circle cx="{w / 2}" cy="240" r="215" stroke="#E62E45" stroke-opacity=".17" stroke-width="1.2" stroke-dasharray="4 6"/>
    <path d="{crh_d}" stroke="#E62E45" stroke-opacity=".6" stroke-width="2.2"/>
  </svg>
  <div class="st-scan"></div>
  <header class="st-header">
    <div class="fcol">
      <div class="fi st-g10">
        <div class="st-comp-pill">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#E62E45" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M8 21h8m-4-4v4m-5-17h10v5a5 5 0 01-10 0V4zM5 6H3v2a3 3 0 003 3h1m12-5h2v2a3 3 0 01-3 3h-1"/></svg>
          <span>{esc(lg.get("name", "جدول رده‌بندی"))}</span>
        </div>
        <span class="st-round-pill">{esc(fa(lg.get("round", "")))}</span>
        <span class="st-season-pill">{f"تمرکز: {esc(spotlight)}" if spotlight else f"فصل {esc(fa(lg.get('season', '26/27')))}"}</span>
        {sample_badge_html(lg)}
      </div>
      <div class="st-sub-meta"><span>{esc(fa(lg.get("date", "")))}</span><span>•</span><span>{esc(fa(lg.get("subtitle", "")))}</span></div>
    </div>
    {_brand_logo_html()}
  </header>
  <main class="{'st-stage-w' if is_wide else 'st-stage-v'}">
    {f'<section class="fcol st-g12">{hero_html}</section><section class="st-mods-grid">{mods_html}</section>' if is_wide else f'{hero_html}<section class="st-mods-grid">{mods_html}</section>'}
  </main>
  <footer class="st-footer">
    <div class="st-foot-line"></div>
    <div class="fbw">
      <div class="fi st-g10"><span class="st-dot-red"></span><span dir="ltr" class="fm st-foot-tag">{esc(lg.get("leagueEn", "LEAGUE"))} {esc(lg.get("season", "26/27"))} {esc(lg.get("weekCode", ""))} • STANDINGS</span></div>
      <div class="fi st-g10 fm" dir="ltr"><span class="st-foot-h">@XGPedia</span><span style="color:#64748B">|</span><span class="st-foot-s">{esc("نمونه استودیو • XGPedia Sample" if is_sample_preset(lg) else lg.get("source", "XGPedia Model"))}</span></div>
    </div>
  </footer>
</div>
</body>
</html>"""


def build_standings_caption(lg: dict[str, Any]) -> str:
    """تولید کپشن فارسی تمیز برای کارت جدول رده‌بندی."""
    teams = lg.get("teams") or []
    parts = [f"🏆 <b>جدول رده‌بندی {esc(lg.get('name', ''))} ({fa(lg.get('round', ''))})</b>"]
    if len(teams) >= 3:
        top3 = " | ".join(f"{fa(t['rank'])}. {t['name']} ({fa(t['pts'])} امتیاز)" for t in teams[:3])
        parts.append(f"🥇 ۳ تیم برتر: {top3}")
    if lg.get("leaderTag"):
        parts.append(f"📌 {fa(str(lg['leaderTag']))}")
    return "\n\n".join(parts)
