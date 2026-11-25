"""کارت ماژولار «جدول گلزنان / کفش طلا» (XGPedia Top Scorers Studio — D58) — بازسازی ۱:۱ آفلاین.

بازسازی دقیق و ۱:۱ از `studio_templates/top_scorers.html` با:
  - فریم چهارگوشه قرمز یکپارچه (`pad_top=24/22/139`, `pad_bot=20/16/171`, `header 12px 36px 8px`, `stage 8px 40px`, `footer 10px 44px 10px`)
  - پس‌زمینه کامل زمین تاکتیکی SVG (`tg`, `#pr`, `#hl`, `#c0..c4`, محوطه‌های جریمه، `#crh`, هاله طلایی/قرمز `#rf` و `#ag`, scanlines)
  - سپر سه‌بعدی SVG باشگاه‌ها (`_crest_svg`) + آواتار پیراهن سه‌بعدی SVG (`_jersey_avatar_svg` یا پرتره رسمی فصل جاری)
  - کارت صدرنشین کفش طلا (`.xh`) با شماره پیراهن واترمارک ۲۰۰px، نشان تاج (`gp`/`cp2`)، عدد گل با گرادیان طلایی (`.gt`) و ۳ کارت KPI
  - جدول گلزنان رتبه‌های ۲ تا ۸ با نوار افقی دوگانه (جریان بازی + هاشور پنالتی `.ps` + سوزن درخشان سفید `xG`) و برچسب کلینیکال (`dp`)
  - تمام ماژول‌های ۴ اسلاید (`leaderboard`, `insight`, `clinical_trio`, `duel`, `radar`, `matrix`, `trajectory`) به‌صورت کاملاً ماژولار و قابل چینش + مرتب‌سازی زنده (`goals`/`npg`/`xg`/`delta`/`g90`) + تم طلایی/کلاسیک + قانون `null ≠ 0`.
"""
from __future__ import annotations

import math
from typing import Any

from src.xgpedia.render.card_kit.helpers import contrast_ink, esc, f1, f2, fa, luminance, smooth_spline
from src.xgpedia.render.cards import _brand_logo_data_uri
from src.xgpedia.render.studio_engine import build_embedded_font_css

TOP_SCORERS_FORMATS: dict[str, tuple[int, int]] = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}

# (id, label_fa, subtitle_en, default_mods)
TOP_SCORERS_SLIDES: list[tuple[str, str, str, list[str]]] = [
    ("slide1", "اسلاید ۱: رقابت کفش طلا (کارت اصلی)", "GOLDEN BOOT RACE", ["leaderboard", "insight"]),
    ("slide2", "اسلاید ۲: دوئل صدرنشینان (H2H و رادار)", "STRIKER HEAD-TO-HEAD", ["duel", "radar"]),
    ("slide3", "اسلاید ۳: نقشه کلینیکال تمام‌کنندگی (G vs xG)", "CLINICAL FINISHING MATRIX", ["matrix"]),
    ("slide4", "اسلاید ۴: ریتم و مسیر کفش طلا (روند گلزنی)", "GOLDEN BOOT TRAJECTORY", ["trajectory", "insight"]),
]


def _p2(n: int) -> str:
    return fa(str(n).zfill(2))


def _sgn(v: float, dec: int = 1) -> str:
    s = f1(abs(v)) if dec == 1 else f2(abs(v))
    return f"+{fa(s)}" if v >= 0 else f"−{fa(s)}"


def _crown_svg(size: int = 18, color: str = "#FBBF24") -> str:
    return f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="{color}" style="flex-shrink:0"><path d="M3 18h18v2H3v-2zm0-2L1 7l5.5 3.5L12 3l5.5 7.5L23 7l-2 9H3z"/></svg>'


def _flame_svg(size: int = 15) -> str:
    return f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" style="flex-shrink:0"><path d="M12 2c.6 3.2-1.2 5.3-2.5 6.8C8 10.6 7 12.2 7 14.5a5 5 0 0 0 10 0c0-3.2-1.9-5.6-3-7-.2 1.4-.9 2.3-1.8 2.8.5-2.6.4-5.7-.2-8.3z" fill="#F97316" stroke="#FDE047" stroke-width="1.2"/></svg>'


def _crest_svg(p: dict[str, Any], size: int = 34, uid: str = "c") -> str:
    from src.xgpedia.providers.pl_badges_free import get_pl_badge_data_uri
    logo_uri = p.get("logoUrl") or get_pl_badge_data_uri(
        str(p.get("club") or ""), tla_hint=str(p.get("code") or ""), fetch_network=False
    )
    if logo_uri:
        return (
            f'<div style="width:{size}px;height:{size}px;flex-shrink:0;display:flex;align-items:center;justify-content:center;'
            f'border-radius:50%;background:rgba(255,255,255,.08);padding:{max(2, size//12)}px;filter:drop-shadow(0 4px 10px #00000080)">'
            f'<img src="{esc(logo_uri)}" style="width:100%;height:100%;object-fit:contain;display:block" alt="{esc(p.get("code",""))}"/></div>'
        )
    pr = esc(p.get("color") or "#E62E45")
    sc = esc(p.get("secondary") or "#FFFFFF")
    cd = esc(str(p.get("code") or "FC")[:3].upper())
    k = f"{uid}_{cd}_{size}"
    d = "M90 16L150 40V88C150 128 124.5 156.5 90 166C55.5 156.5 30 128 30 88V40Z"
    bg = "#0D1730" if luminance(p.get("color") or "#E62E45") > 0.62 else "#070d1da8"
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 180 180" fill="none" style="filter:drop-shadow(0 6px 12px #00000080);flex-shrink:0">'
        f'<defs><linearGradient id="g{k}" x1="20" y1="15" x2="160" y2="165" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{sc}" stop-opacity=".95"/><stop offset=".5" stop-color="{pr}" stop-opacity=".92"/>'
        f'<stop offset="1" stop-color="{sc}" stop-opacity=".72"/></linearGradient>'
        f'<clipPath id="cl{k}"><path d="{d}"/></clipPath></defs>'
        f'<path d="M90 12L154 38V88C154 130.5 127 160.5 90 170.5C53 160.5 26 130.5 26 88V38Z" fill="{pr}" fill-opacity=".22"/>'
        f'<g clip-path="url(#cl{k})"><rect x="25" y="12" width="130" height="158" fill="{pr}"/>'
        f'<path d="M25 112L155 56V84L25 140Z" fill="{sc}" fill-opacity=".28"/>'
        f'<path d="M90 16L150 40V58L90 34L30 58V40Z" fill="{sc}" fill-opacity=".88"/>'
        f'<ellipse cx="90" cy="30" rx="65" ry="26" fill="#fff" fill-opacity=".14"/></g>'
        f'<path d="{d}" stroke="url(#g{k})" stroke-width="5.5"/>'
        f'<rect x="38" y="66" width="104" height="50" rx="14" fill="{bg}" stroke="{sc}" stroke-opacity=".55" stroke-width="2.2"/>'
        f'<text x="90" y="102" text-anchor="middle" fill="#fff" font-family="Space Grotesk,JetBrains Mono,sans-serif" font-weight="800" font-size="34" letter-spacing="1.5">{cd}</text></svg>'
    )


def _jersey_avatar_svg(p: dict[str, Any], size: int = 128, is_leader: bool = True, theme: str = "gold", uid: str = "j") -> str:
    ac = ("#FBBF24" if theme == "gold" else "#E62E45") if is_leader else esc(p.get("color") or "#38BDF8")
    pr = esc(p.get("color") or "#38BDF8")
    sc = esc(p.get("secondary") or "#FFFFFF")
    if p.get("photoUrl"):
        return (
            f'<div style="width:{size}px;height:{size}px;border-radius:999px;padding:4px;'
            f'background:linear-gradient(135deg,{ac},{pr});box-shadow:0 0 28px {ac}55;flex-shrink:0">'
            f'<img src="{p["photoUrl"]}" alt="{esc(p.get("name", ""))}" '
            f'style="width:100%;height:100%;object-fit:cover;border-radius:999px;background:#091023"></div>'
        )
    num_txt = str(p.get("num")) if p.get("num") not in (None, "", 0) else str(p.get("code") or "9")[:2]
    k = f"{uid}_{esc(str(p.get('code') or 'FC'))}_{num_txt}_{size}"
    jp = "M56 48L72 41C77 50 103 50 108 41L124 48L152 72L136 96L124 88V166H56V88L44 96L28 72Z"
    top_ring = "#FEF08A" if (is_leader and theme == "gold") else ac
    ink = contrast_ink(p.get("color") or "#38BDF8")
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 180 180" fill="none" style="filter:drop-shadow(0 14px 24px #0000009e);flex-shrink:0">'
        f'<defs><radialGradient id="b{k}" cx="50%" cy="42%" r="55%">'
        f'<stop offset="0" stop-color="{pr}" stop-opacity=".42"/><stop offset=".7" stop-color="#091124" stop-opacity=".95"/>'
        f'<stop offset="1" stop-color="#050914"/></radialGradient>'
        f'<linearGradient id="r{k}" x1="0" y1="0" x2="180" y2="180" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{top_ring}"/><stop offset=".5" stop-color="{ac}"/><stop offset="1" stop-color="{pr}"/></linearGradient>'
        f'<linearGradient id="k{k}" x1="40" y1="30" x2="140" y2="160" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{pr}"/><stop offset="1" stop-color="{pr}" stop-opacity=".78"/></linearGradient>'
        f'<pattern id="m{k}" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(35)">'
        f'<line x1="0" y1="0" x2="0" y2="10" stroke="{sc}" stroke-opacity=".16" stroke-width="2"/></pattern>'
        f'<clipPath id="c{k}"><circle cx="90" cy="90" r="80"/></clipPath></defs>'
        f'<circle cx="90" cy="90" r="87" stroke="{ac}" stroke-opacity=".34" stroke-width="1.5" stroke-dasharray="5 5"/>'
        f'<circle cx="90" cy="90" r="81" fill="url(#b{k})" stroke="url(#r{k})" stroke-width="4"/>'
        f'<g clip-path="url(#c{k})"><circle cx="90" cy="145" r="52" stroke="#fff" stroke-opacity=".08" stroke-width="1.5"/>'
        f'<path d="{jp}" fill="url(#k{k})" stroke="{sc}" stroke-opacity=".65" stroke-width="2.5" stroke-linejoin="round"/>'
        f'<path d="{jp}" fill="url(#m{k})"/>'
        f'<path d="M28 72L44 96L50 92L35 67ZM152 72L136 96L130 92L145 67Z" fill="{sc}" fill-opacity=".85"/>'
        f'<path d="M72 41C78 54 102 54 108 41L103 40C98 48 82 48 77 40Z" fill="{sc}" fill-opacity=".92"/>'
        f'<text x="90" y="121" text-anchor="middle" fill="{ink}" font-family="Space Grotesk,JetBrains Mono,sans-serif" font-weight="800" font-size="48" letter-spacing="-1">{esc(num_txt)}</text>'
        f'<circle cx="109" cy="70" r="5" fill="{sc}" fill-opacity=".9"/></g></svg>'
    )


def _rank_players(data: dict[str, Any], sort_by: str = "goals") -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for raw in (data.get("players") or []):
        p = dict(raw)
        g = int(p.get("goals") or 0)
        pen = p.get("pen")
        xg = p.get("xg")
        mins = p.get("mins")
        shots = p.get("shots")
        sot = p.get("sot")
        m90 = (float(mins) / 90.0) if (mins and float(mins) > 0) else None
        p["npg"] = max(0, g - int(pen)) if pen is not None else g
        p["delta"] = round(g - float(xg), 2) if xg is not None else None
        p["g90"] = round(g / m90, 2) if m90 else None
        p["npxg90"] = round(max(0.0, float(xg) - (int(pen or 0) * 0.78)) / m90, 2) if (xg is not None and m90) else None
        p["sot90"] = round(float(sot) / m90, 2) if (sot is not None and m90) else None
        p["mpg"] = round(float(mins) / g) if (mins and g > 0) else None
        p["conv"] = round((g / float(shots)) * 100.0, 1) if (shots and float(shots) > 0) else None
        ranked.append(p)

    if sort_by == "npg":
        ranked.sort(key=lambda x: (x["npg"], x["goals"]), reverse=True)
    elif sort_by == "xg":
        ranked.sort(key=lambda x: (x["xg"] if x["xg"] is not None else -1.0, x["goals"]), reverse=True)
    elif sort_by == "delta":
        ranked.sort(key=lambda x: (x["delta"] if x["delta"] is not None else -99.0, x["goals"]), reverse=True)
    elif sort_by == "g90":
        ranked.sort(key=lambda x: (x["g90"] if x["g90"] is not None else -1.0, x["goals"]), reverse=True)
    else:
        ranked.sort(key=lambda x: (x["goals"], x["npg"], -(x.get("mins") or 99999)), reverse=True)
    return ranked


def get_top_scorers_modules(data: dict[str, Any], slide: str = "slide1") -> tuple[list[dict[str, Any]], list[str]]:
    players = data.get("players") or []
    has_lb = len(players) >= 2
    has_insight = bool(data.get("paceInsight"))
    has_xg = sum(1 for p in players if p.get("xg") is not None) >= 3
    has_duel = len(players) >= 2
    has_radar = len(players) >= 2 and len(players[0].get("radar") or []) >= 6 and len(players[1].get("radar") or []) >= 6
    has_traj = len(data.get("weeks") or []) >= 2 and sum(1 for p in players[:4] if bool(p.get("pace"))) >= 2

    sl_def = next((mids for sid, _, _, mids in TOP_SCORERS_SLIDES if sid == slide), ["leaderboard", "insight"])
    def_set = set(sl_def)
    specs = [
        ("leaderboard", "جدول گلزنان و مقایسه با امید گل (Leaderboard)", has_lb, False, "full"),
        ("insight", "نبض رقابت کفش طلا (Pace Insight)", has_insight, True, "full"),
        ("clinical_trio", "کارت ۳ برتر xG و نرخ گل (Clinical Trio)", has_xg, True, "full"),
        ("duel", "دوئل صدرنشینان + مقایسه فنی (H2H Duel)", has_duel, False, "full"),
        ("radar", "رادار ۶محوره پروفایل مهاجم (Striker Radar)", has_radar, False, "full"),
        ("matrix", "نقشه کلینیکال تمام‌کنندگی (G vs xG Matrix)", has_xg, False, "full"),
        ("trajectory", "مسیر و ریتم کفش طلا (8-Week Trajectory)", has_traj, False, "full"),
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


def _mod_head(title: str, right_html: str, bar_color: str = "#FBBF24") -> str:
    return (
        '<div class="mh">'
        f'<div class="mh-left"><span class="mh-bar" style="background:{bar_color}"></span>'
        f'<h3 class="mt">{esc(title)}</h3></div>'
        f'<div class="mh-sub">{right_html}</div></div>'
    )


def _delta_pill(delta: float | None) -> str:
    if delta is None:
        return '<span class="dp neu">—</span>'
    cls = "dp pos" if delta >= 0 else "dp neg"
    return f'<span dir="ltr" class="{cls}">{_sgn(delta, 1)}</span>'


def _render_leader_hero(L: dict[str, Any], theme: str, sort_by: str, fmt: str) -> str:
    gd = (theme == "gold")
    ac = "#FBBF24" if gd else "#E62E45"
    bc = "gp" if gd else "cp2"
    nc = "gt" if gd else "wtxt"
    titles = {
        "goals": "صدرنشین جدول گلزنان",
        "npg": "برترین گلزن بدون پنالتی",
        "xg": "بالاترین امید گل (xG)",
        "delta": "کلینیکال‌ترین تمام‌کننده",
        "g90": "بیشترین نرخ گل در ۹۰ دقیقه",
    }
    st = titles.get(sort_by, titles["goals"])
    num_wm = str(L.get("num") or "09").zfill(2)
    b9 = (fmt == "9:16")

    xg_s = fa(f1(L["xg"])) if L.get("xg") is not None else "—"
    dl_s = _sgn(L["delta"], 1) if L.get("delta") is not None else "—"
    dl_col = "#6EE7B7" if (L.get("delta") or 0) >= 0 else "#FDA4AF"
    g90_s = fa(f2(L["g90"])) if L.get("g90") is not None else "—"
    pen_pill = f'<span class="lh-pill">پنالتی <b>{fa(L["pen"])}</b></span>' if L.get("pen") is not None else ""
    conv_pill = f'<span class="lh-pill em">تبدیل <b>{fa(f1(L["conv"]))}٪</b></span>' if L.get("conv") is not None else ""
    streak_pill = f'<span class="lh-hot">{_flame_svg(14)} فرم داغ</span>' if L.get("streak") else ""

    return (
        f'<div class="xh{"" if gd else " cl"}">'
        f'<div class="xh-wm fd" style="color:{ac}">{esc(num_wm)}</div>'
        f'<div class="xh-glow" style="background:radial-gradient(circle,{esc(L.get("color") or ac)}3b,transparent 70%)"></div>'
        '<div class="xh-top">'
        f'<div class="xh-left">{_jersey_avatar_svg(L, 142 if b9 else 118, True, theme, "h1")}'
        '<div class="xh-info">'
        f'<div class="xh-badges"><span class="xh-crown {bc}">{_crown_svg(16, "#FBBF24" if gd else "#FF6B7F")}<span>{st}</span></span>'
        f'<span class="xh-pos">{esc(L.get("pos") or "مهاجم")}</span></div>'
        f'<h1 class="xh-name">{esc(L["name"])}</h1>'
        f'<div class="xh-club">{_crest_svg(L, 32, "hc1")}<span>{esc(L["club"])}</span>{streak_pill}</div>'
        "</div></div>"
        '<div class="xh-right">'
        f'<div class="xh-goals-row"><span class="xh-goals {nc}">{fa(L["goals"])}</span>'
        '<div class="xh-glbl"><b>گل</b><span class=fm>GOALS</span></div></div>'
        f'<div class="xh-subpills">{pen_pill}{conv_pill}</div>'
        "</div></div>"
        '<div class="xh-kpis">'
        f'<div class="xh-kpi sky"><span>امید گل (xG)</span><b style="color:#7DD3FC">{xg_s}</b></div>'
        f'<div class="xh-kpi"><span>کلینیکال</span><b dir="ltr" style="color:{dl_col}">{dl_s}</b></div>'
        f'<div class="xh-kpi"><span>نرخ در ۹۰’</span><b style="color:#FCD34D">{g90_s}</b></div>'
        "</div></div>"
    )


def _render_leaderboard(P: list[dict[str, Any]], theme: str, show_pen: bool = True, row_count: int = 8) -> str:
    gd = (theme == "gold")
    rs = P[1:row_count]
    mx = max([max(p["goals"], float(p["xg"] or 0)) for p in P[:row_count]] or [1.0]) * 1.08
    rows_html = []
    for idx, p in enumerate(rs, 2):
        col = esc(p.get("color") or "#E62E45")
        rk_cls = "r2" if idx == 2 else ("r3" if idx == 3 else "rn")
        pen_v = int(p["pen"]) if (show_pen and p.get("pen") is not None) else 0
        npg_v = max(0, p["goals"] - pen_v)
        np_pct = (npg_v / mx) * 100.0
        pp_pct = (pen_v / mx) * 100.0
        xg_needle = ""
        if p.get("xg") is not None:
            xp = min(98.5, max(2.0, (float(p["xg"]) / mx) * 100.0))
            xg_needle = f'<div class="xg-needle" style="left:{xp:.1f}%"></div>'
        g90_txt = f" • {fa(f2(p['g90']))} در ۹۰’" if p.get("g90") is not None else ""
        xg_sub = f'xG {fa(f1(p["xg"]))}' if p.get("xg") is not None else "—"
        pen_bar = f'<div class="bar-pen ps" style="width:{pp_pct:.1f}%;background-color:{col}66"></div>' if pp_pct > 0 else ""
        rows_html.append(
            '<div class="lr">'
            f'<span class="lr-strip" style="background:{col}"></span>'
            f'<div class="fc"><span class="rk-b fm {rk_cls}">{_p2(idx)}</span></div>'
            f'<div class="lr-pl">{_crest_svg(p, 42, f"r{idx}")}'
            f'<div class="min-w-0"><div class="lr-name"><span>{esc(p["name"])}</span>{_flame_svg(13) if p.get("streak") else ""}</div>'
            f'<div class="lr-club">{esc(p["club"])}{g90_txt}' + (f' <span class="lr-pen">({fa(pen_v)} پنالتی)</span>' if (show_pen and p.get("pen") is not None and pen_v > 0) else '') + '</div></div></div>'
            '<div class="lr-bar-wrap" dir="ltr">'
            f'<div class="lr-track"><div class="bar-npg" style="width:{np_pct:.1f}%;background:linear-gradient(90deg,{col}cc,{col});box-shadow:0 0 10px {col}55"></div>{pen_bar}</div>'
            f"{xg_needle}</div>"
            f'<div class="lr-end"><div class="lr-g"><b>{fa(p["goals"])}</b><span class=fm>{xg_sub}</span></div>{_delta_pill(p.get("delta"))}</div>'
            "</div>"
        )

    leg = (
        '<div class="lb-leg">'
        '<span><i class="sw-npg"></i>جریان بازی</span>'
        + ('<span><i class="sw-pen ps"></i>پنالتی</span>' if show_pen else "")
        + '<span><i class="sw-xg"></i>امید گل (xG)</span></div>'
    )
    return (
        '<div class="xm lb-card">'
        + _mod_head("جدول برترین گلزنان و مقایسه با امید گل", leg, "#FBBF24" if gd else "#E62E45")
        + f'<div class="lr-list">{"".join(rows_html)}</div></div>'
    )


def _render_insight(data: dict[str, Any], P: list[dict[str, Any]], theme: str) -> str:
    ac = "#FBBF24" if theme == "gold" else "#E62E45"
    t8 = P[:8]
    tg = sum(p["goals"] for p in t8)
    has_pen = any(p.get("pen") is not None for p in t8)
    tp_sum = sum(int(p.get("pen") or 0) for p in t8)
    clin_pool = [p for p in t8 if p.get("delta") is not None]
    best_c = max(clin_pool, key=lambda x: x["delta"]) if clin_pool else None

    pills = [f'<span class="in-p">مجموع {fa(len(t8))} نفر: <b>{fa(tg)} گل</b></span>']
    if has_pen and tg > 0:
        pills.append(f'<span class="in-p gold">سهم پنالتی: <b>{fa(round(tp_sum / tg * 100))}٪</b></span>')
    if best_c:
        pills.append(f'<span class="in-p em">کلینیکال: <b>{esc(best_c.get("short") or best_c["name"])} ({_sgn(best_c["delta"], 1)})</b></span>')

    return (
        f'<div class="xe ins-card" style="border-right:5px solid {ac}">'
        '<div class="ins-top">'
        f'<div class="ins-title"><span class="ins-bar" style="background:{ac}"></span><span>نبض رقابت کفش طلا</span></div>'
        f'<div class="ins-pills">{"".join(pills)}</div></div>'
        f'<p class="ins-txt">{esc(data.get("paceInsight") or "")}</p></div>'
    )


def _render_clinical_trio(P: list[dict[str, Any]]) -> str:
    t8 = [p for p in P[:8] if p.get("xg") is not None]
    if not t8:
        return ""
    bc = max(t8, key=lambda x: x["delta"] if x["delta"] is not None else -99)
    bx = max(t8, key=lambda x: float(x["xg"] or 0))
    bg = max(t8, key=lambda x: float(x["g90"] or 0))

    def _card(t: str, tag: str, pl: dict[str, Any], val: str, col: str) -> str:
        return (
            f'<div class="tri-box" style="border-right:4px solid {col}">'
            f'<div class="tri-top"><span>{t}</span><b class="fm" style="color:{col}">{tag}</b></div>'
            f'<div class="tri-bot"><div class="tri-pl">{_crest_svg(pl, 26, f"t{tag}")}<span>{esc(pl.get("short") or pl["name"])}</span></div>'
            f'<b dir="ltr" class="tri-v" style="color:{col}">{val}</b></div></div>'
        )

    return (
        '<div class="xe"><div class="tri-grid">'
        f'{_card("کلینیکال‌ترین", "G−xG", bc, _sgn(bc["delta"], 1), "#34D399")}'
        f'{_card("بالاترین امید گل", "TOP xG", bx, fa(f1(bx["xg"])), "#38BDF8")}'
        f'{_card("بیشترین نرخ ۹۰’", "G/90", bg, fa(f2(bg["g90"] or 0)), "#FBBF24")}'
        "</div></div>"
    )


def _render_duel(P: list[dict[str, Any]], theme: str) -> str:
    p1, p2 = P[0], P[1]
    c1, c2 = esc(p1.get("color") or "#38BDF8"), esc(p2.get("color") or "#EF0107")

    def _pc(p: dict[str, Any], ld: bool, uid: str) -> str:
        xg_s = f'xG {fa(f1(p["xg"]))}' if p.get("xg") is not None else ""
        return (
            '<div class="duel-p">'
            f'<div class="dp-av">{_jersey_avatar_svg(p, 126, ld, theme, uid)}'
            f'<div class="dp-cr">{_crest_svg(p, 40, "c" + uid)}</div></div>'
            f'<div class="dp-name">{esc(p["name"])}</div>'
            f'<div class="dp-sub">{esc(p["club"])} • {esc(p.get("pos") or "")}</div>'
            f'<div class="dp-pills"><span>{fa(p["goals"])} گل</span>'
            + (f'<span class="sky">{xg_s}</span>' if xg_s else "")
            + "</div></div>"
        )

    mpg1 = f"{fa(p1['mpg'])}'" if p1.get("mpg") else "—"
    mpg2 = f"{fa(p2['mpg'])}'" if p2.get("mpg") else "—"
    metrics = []
    if p1.get("g90") is not None and p2.get("g90") is not None:
        metrics.append(("گل در ۹۰ دقیقه (G/90)", p1["g90"], p2["g90"], 2, ""))
    if p1.get("npxg90") is not None and p2.get("npxg90") is not None:
        metrics.append(("امید گل بدون پنالتی (npxG/90)", p1["npxg90"], p2["npxg90"], 2, ""))
    if p1.get("sot90") is not None and p2.get("sot90") is not None:
        metrics.append(("شوت در چارچوب (SOT/90)", p1["sot90"], p2["sot90"], 2, ""))
    if p1.get("conv") is not None and p2.get("conv") is not None:
        metrics.append(("نرخ تبدیل شوت (%)", p1["conv"], p2["conv"], 1, "٪"))

    bars = []
    for lbl, v1, v2, dec, sf in metrics:
        mx = max(float(v1), float(v2), 0.01)
        s1 = f"{fa(f2(v1) if dec == 2 else f1(v1))}{sf}"
        s2 = f"{fa(f2(v2) if dec == 2 else f1(v2))}{sf}"
        bars.append(
            '<div class="dm-row">'
            f'<div class="dm-top"><span style="color:{c1}">{s1}</span><span class="k">{lbl}</span><span style="color:{c2}">{s2}</span></div>'
            '<div class="dm-bars">'
            f'<div class="ct hs"><div class="ch" style="width:{v1 / mx * 100:.1f}%;background:{c1}"></div></div>'
            f'<div class="ct as"><div class="ca" style="width:{v2 / mx * 100:.1f}%;background:{c2}"></div></div>'
            "</div></div>"
        )

    return (
        '<div class="xm">'
        + _mod_head("دوئل صدرنشینان و مقایسه فنی", "<span class=fm>STRIKER HEAD-TO-HEAD</span>", "#E62E45")
        + '<div class="duel-top">'
        f'{_pc(p1, True, "d1")}'
        '<div class="duel-mid"><div class="vs-dm"><span class="fd">VS</span></div>'
        '<div class="mpg-box"><div class="mpg-k">دقیقه به ازای هر گل</div>'
        f'<div class="mpg-v"><b style="color:{c1}">{mpg1}</b><span>/</span><b style="color:{c2}">{mpg2}</b></div></div></div>'
        f'{_pc(p2, False, "d2")}'
        f'</div><div class="dm-list">{"".join(bars)}</div></div>'
    )


def _render_radar(P: list[dict[str, Any]]) -> str:
    p1, p2 = P[0], P[1]
    c1, c2 = esc(p1.get("color") or "#38BDF8"), esc(p2.get("color") or "#EF0107")
    r1 = [max(18, min(100, float(v))) for v in (p1.get("radar") or [])[:6]]
    r2 = [max(18, min(100, float(v))) for v in (p2.get("radar") or [])[:6]]
    labels = ["تمام‌کنندگی", "حضور در محوطه", "ضربه سر", "شوت از راه دور", "خونسردی", "مشارکت گل"]
    cx, cy, r_max = 450.0, 200.0, 118.0
    dx = r_max * 0.866 + 28.0

    def _pts(arr: list[float]) -> list[tuple[float, float]]:
        return [
            (cx + (v / 100.0) * r_max * math.cos(math.radians(i * 60 - 90)),
             cy + (v / 100.0) * r_max * math.sin(math.radians(i * 60 - 90)))
            for i, v in enumerate(arr)
        ]

    q1, q2 = _pts(r1), _pts(r2)
    rings = "".join(
        '<polygon points="' + " ".join(
            f"{cx + r_max * k * math.cos(math.radians(i * 60 - 90)):.1f},{cy + r_max * k * math.sin(math.radians(i * 60 - 90)):.1f}"
            for i in range(6)
        ) + '"/>'
        for k in (1.0, 0.75, 0.5, 0.25)
    )
    sp = [
        (cx, 30.0, "middle"),
        (cx + dx, cy - r_max * 0.5 - 6, "start"),
        (cx + dx, cy + r_max * 0.5 - 2, "start"),
        (cx, cy + r_max + 32, "middle"),
        (cx - dx, cy + r_max * 0.5 - 2, "end"),
        (cx - dx, cy - r_max * 0.5 - 6, "end"),
    ]
    lbls = "".join(
        f'<g><text x="{x:.1f}" y="{y:.1f}" text-anchor="{anc}" fill="#F8FAFC" font-family="Vazirmatn" font-weight="800" font-size="22">{labels[i]}</text>'
        f'<text x="{x:.1f}" y="{y + 27:.1f}" text-anchor="{anc}" font-family="Vazirmatn" font-weight="900" font-size="20">'
        f'<tspan fill="{c1}">{fa(int(r1[i]))}</tspan><tspan fill="#64748B"> / </tspan><tspan fill="{c2}">{fa(int(r2[i]))}</tspan></text></g>'
        for i, (x, y, anc) in enumerate(sp)
    )
    dots1 = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{c1}" stroke="#fff" stroke-width="2"/>' for x, y in q1)
    dots2 = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{c2}" stroke="#fff" stroke-width="2"/>' for x, y in q2)
    leg = f'<div class="rad-leg"><span><i style="background:{c1}"></i>{esc(p1.get("short") or p1["name"])}</span><span><i style="background:{c2}"></i>{esc(p2.get("short") or p2["name"])}</span></div>'
    return (
        '<div class="xe">'
        + _mod_head("رادار ۶ محوره پروفایل مهاجم", leg, "#FBBF24")
        + '<div class="fc" dir="ltr"><svg style="width:100%;max-height:345px;height:auto" viewBox="0 0 900 400" fill="none">'
        f'<g stroke="#ffffff26" stroke-width="1.6">{rings}'
        f'<line x1="{cx:.0f}" y1="{cy - r_max:.1f}" x2="{cx:.0f}" y2="{cy + r_max:.1f}"/>'
        f'<line x1="{cx + r_max * 0.866:.1f}" y1="{cy - r_max * 0.5:.1f}" x2="{cx - r_max * 0.866:.1f}" y2="{cy + r_max * 0.5:.1f}"/>'
        f'<line x1="{cx + r_max * 0.866:.1f}" y1="{cy + r_max * 0.5:.1f}" x2="{cx - r_max * 0.866:.1f}" y2="{cy - r_max * 0.5:.1f}"/></g>'
        f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in q2)}" fill="{c2}" fill-opacity=".24" stroke="{c2}" stroke-width="3.6"/>'
        f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in q1)}" fill="{c1}" fill-opacity=".3" stroke="{c1}" stroke-width="4.2"/>'
        f'{dots2}{dots1}{lbls}</svg></div></div>'
    )


def _render_matrix(P: list[dict[str, Any]]) -> str:
    ls = [p for p in P[:8] if p.get("xg") is not None]
    r0 = max(0, math.floor(min(min(p["xg"], p["goals"]) for p in ls) - 1))
    r1 = math.ceil(max(max(p["xg"], p["goals"]) for p in ls) + 1)
    sp0 = max(4, r1 - r0)
    st = 1 if sp0 <= 6 else (2 if sp0 <= 12 else (3 if sp0 <= 18 else (4 if sp0 <= 24 else 5)))
    mn, mx = (r0 // st) * st, math.ceil(r1 / st) * st
    spn = max(st, mx - mn)
    w_s, h_s, pl, pr, pt, pb = 960.0, 560.0, 78.0, 46.0, 40.0, 68.0
    pw, ph = w_s - pl - pr, h_s - pt - pb
    tx = lambda v: pl + (v - mn) / spn * pw
    ty = lambda v: pt + ph - (v - mn) / spn * ph
    ticks = list(range(mn, mx + 1, st))

    nodes = []
    for i, p in enumerate(ls):
        x, y = tx(float(p["xg"])), ty(float(p["goals"]))
        rad = 24 if i == 0 else 20
        ly = y - rad - 14
        if ly < pt + 24:
            ly = y + rad + 24
        nodes.append({"p": p, "i": i, "x": x, "y": y, "r": rad, "lx": x, "ly": ly})
    for _ in range(18):
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                a, b = nodes[i], nodes[j]
                if abs(a["lx"] - b["lx"]) < 105 and abs(a["ly"] - b["ly"]) < 34:
                    push = (34 - abs(a["ly"] - b["ly"])) * 0.55
                    if a["ly"] <= b["ly"]:
                        a["ly"] -= push
                        b["ly"] += push
                    else:
                        a["ly"] += push
                        b["ly"] -= push
            nodes[i]["lx"] = max(pl + 60, min(w_s - pr - 60, nodes[i]["lx"]))
            nodes[i]["ly"] = max(pt + 24, min(h_s - pb - 14, nodes[i]["ly"]))

    grid_l = "".join(
        f'<line x1="{tx(t):.1f}" y1="{pt:.0f}" x2="{tx(t):.1f}" y2="{h_s - pb:.0f}"/>'
        f'<line x1="{pl:.0f}" y1="{ty(t):.1f}" x2="{w_s - pr:.0f}" y2="{ty(t):.1f}"/>'
        for t in ticks
    )
    tick_t = "".join(
        f'<text x="{tx(t):.1f}" y="{h_s - pb + 28:.0f}" text-anchor="middle" fill="#94A3B8" font-family="Vazirmatn" font-weight="800" font-size="19">{fa(t)}</text>'
        f'<text x="{pl - 16:.0f}" y="{ty(t) + 7:.1f}" text-anchor="end" fill="#94A3B8" font-family="Vazirmatn" font-weight="800" font-size="19">{fa(t)}</text>'
        for t in ticks
    )
    pts_svg = "".join(
        f'<g><line x1="{n["x"]:.1f}" y1="{n["y"]:.1f}" x2="{n["lx"]:.1f}" y2="{n["ly"]:.1f}" stroke="{esc(n["p"].get("color") or "#F59E0B")}" stroke-opacity=".45" stroke-width="1.5" stroke-dasharray="3 3"/>'
        f'<circle cx="{n["x"]:.1f}" cy="{n["y"]:.1f}" r="{n["r"] + 7}" fill="{esc(n["p"].get("color") or "#F59E0B")}" fill-opacity=".22"/>'
        f'<circle cx="{n["x"]:.1f}" cy="{n["y"]:.1f}" r="{n["r"]}" fill="{esc(n["p"].get("color") or "#F59E0B")}" stroke="{"#FBBF24" if n["i"] == 0 else "#fff"}" stroke-width="{"3.5" if n["i"] == 0 else "2.5"}"/>'
        f'<text x="{n["x"]:.1f}" y="{n["y"] + 7:.1f}" text-anchor="middle" fill="{contrast_ink(n["p"].get("color") or "#F59E0B")}" font-family="Space Grotesk" font-weight="800" font-size="{20 if n["i"] == 0 else 16}">{esc(str(n["p"].get("num") or n["i"] + 1))}</text>'
        f'<rect x="{n["lx"] - 56:.1f}" y="{n["ly"] - 16:.1f}" width="112" height="28" rx="9" fill="#070E20" fill-opacity=".92" stroke="{esc(n["p"].get("color") or "#F59E0B")}" stroke-opacity=".65" stroke-width="1.4"/>'
        f'<text x="{n["lx"]:.1f}" y="{n["ly"] + 4:.1f}" text-anchor="middle" fill="#F8FAFC" font-family="Vazirmatn" font-weight="800" font-size="15">{esc(n["p"].get("short") or n["p"]["name"][:10])}</text></g>'
        for n in nodes
    )
    return (
        '<div class="xm" style="flex:1">'
        + _mod_head("نقشه کلینیکال تمام‌کنندگی (گل زده در برابر امید گل)", "<span class='fm em'>GOALS vs xG MATRIX</span>", "#34D399")
        + f'<div class="fc" dir="ltr" style="flex:1"><svg style="width:100%;height:auto;max-height:540px" viewBox="0 0 {int(w_s)} {int(h_s)}" fill="none">'
        '<defs><linearGradient id="cz" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#10B981" stop-opacity=".17"/><stop offset="1" stop-color="#10B981" stop-opacity=".02"/></linearGradient>'
        '<linearGradient id="uz" x1="1" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#F43F5E" stop-opacity=".16"/><stop offset="1" stop-color="#F43F5E" stop-opacity=".02"/></linearGradient></defs>'
        f'<polygon points="{pl:.0f},{pt:.0f} {w_s - pr:.0f},{pt:.0f} {pl:.0f},{h_s - pb:.0f}" fill="url(#cz)"/>'
        f'<polygon points="{w_s - pr:.0f},{pt:.0f} {w_s - pr:.0f},{h_s - pb:.0f} {pl:.0f},{h_s - pb:.0f}" fill="url(#uz)"/>'
        f'<g stroke="#ffffff17" stroke-width="1.4" stroke-dasharray="5 5">{grid_l}</g>'
        f'<rect x="{pl:.0f}" y="{pt:.0f}" width="{pw:.0f}" height="{ph:.0f}" rx="12" stroke="#ffffff26" stroke-width="1.8"/>'
        f'<line x1="{pl:.0f}" y1="{h_s - pb:.0f}" x2="{w_s - pr:.0f}" y2="{pt:.0f}" stroke="#F8FAFC" stroke-opacity=".55" stroke-width="2.4" stroke-dasharray="10 8"/>'
        f'<rect x="{pl + 16:.0f}" y="{pt + 14:.0f}" width="305" height="36" rx="10" fill="#06221b" fill-opacity=".86" stroke="#34D399" stroke-opacity=".45"/>'
        f'<text x="{pl + 168:.0f}" y="{pt + 38:.0f}" text-anchor="middle" fill="#34D399" font-family="Vazirmatn" font-weight="800" font-size="16">تمام‌کنندگی فراتر از انتظار • CLINICAL</text>'
        f'<rect x="{w_s - pr - 296:.0f}" y="{h_s - pb - 50:.0f}" width="284" height="36" rx="10" fill="#280b14" fill-opacity=".86" stroke="#F43F5E" stroke-opacity=".45"/>'
        f'<text x="{w_s - pr - 154:.0f}" y="{h_s - pb - 26:.0f}" text-anchor="middle" fill="#FDA4AF" font-family="Vazirmatn" font-weight="800" font-size="16">کمتر از انتظار • UNDERPERFORMING</text>'
        f'{tick_t}<text x="{pl + pw / 2:.0f}" y="{h_s - 10:.0f}" text-anchor="middle" fill="#38BDF8" font-family="Vazirmatn" font-weight="900" font-size="20">امید گل تولیدی (xG)</text>'
        f'<text x="24" y="{pt + ph / 2:.0f}" text-anchor="middle" fill="#F8FAFC" font-family="Vazirmatn" font-weight="900" font-size="20" transform="rotate(-90 24 {pt + ph / 2:.0f})">تعداد گل زده (Goals)</text>'
        f'{pts_svg}</svg></div></div>'
    )


def _render_trajectory(data: dict[str, Any], P: list[dict[str, Any]]) -> str:
    t4 = [p for p in P[:4] if p.get("pace")]
    wks = data.get("weeks") or [str(i + 1) for i in range(8)]
    wl = len(wks)
    w_s, h_s, pl, pr, pt, pb = 940.0, 410.0, 62.0, 172.0, 28.0, 78.0
    pw, ph = w_s - pl - pr, h_s - pt - pb

    def _pad_pace(p: dict[str, Any]) -> list[float]:
        arr = [float(x) for x in p["pace"]]
        return [arr[min(i, len(arr) - 1)] for i in range(wl)]

    all_v = [v for p in t4 for v in _pad_pace(p)]
    r0 = max(0, math.floor(min(all_v) - 1))
    r1 = math.ceil(max(all_v) + 1)
    sp0 = max(4, r1 - r0)
    ys = 1 if sp0 <= 6 else (2 if sp0 <= 12 else (3 if sp0 <= 18 else 4))
    mn, mx = (r0 // ys) * ys, math.ceil(r1 / ys) * ys
    spn = max(ys, mx - mn)

    series = []
    for i, p in enumerate(t4):
        pts = [(pl + j / max(1, wl - 1) * pw, pt + ph - (v - mn) / spn * ph) for j, v in enumerate(_pad_pace(p))]
        series.append({"p": p, "i": i, "pts": pts, "d": smooth_spline(pts, 0.24), "ex": pts[-1][0], "ey": pts[-1][1], "ly": pts[-1][1]})
    series.sort(key=lambda s: s["ly"])
    for i in range(1, len(series)):
        if series[i]["ly"] - series[i - 1]["ly"] < 38:
            series[i]["ly"] = series[i - 1]["ly"] + 38
    for i in range(len(series) - 1, -1, -1):
        if series[i]["ly"] > pt + ph - 12:
            series[i]["ly"] = pt + ph - 12
        if i and series[i]["ly"] - series[i - 1]["ly"] < 36:
            series[i - 1]["ly"] = series[i]["ly"] - 36
    series.sort(key=lambda s: -s["i"])
    l1 = next((s for s in series if s["i"] == 0), series[-1])

    y_svg = "".join(
        f'<line x1="{pl:.0f}" y1="{pt + ph - (v - mn) / spn * ph:.1f}" x2="{w_s - pr:.0f}" y2="{pt + ph - (v - mn) / spn * ph:.1f}" stroke="#ffffff1a" stroke-width="1.4" stroke-dasharray="5 5"/>'
        f'<text x="{pl - 14:.0f}" y="{pt + ph - (v - mn) / spn * ph + 6:.1f}" text-anchor="end" fill="#94A3B8" font-family="Vazirmatn" font-weight="800" font-size="18">{fa(v)}</text>'
        for v in range(mn, mx + 1, ys)
    )
    x_svg = "".join(
        f'<line x1="{pl + i / max(1, wl - 1) * pw:.1f}" y1="{pt:.0f}" x2="{pl + i / max(1, wl - 1) * pw:.1f}" y2="{pt + ph:.0f}" stroke="#ffffff0d" stroke-width="1.2"/>'
        f'<text x="{pl + i / max(1, wl - 1) * pw:.1f}" y="{pt + ph + 28:.0f}" text-anchor="middle" fill="#E2E8F0" font-family="Vazirmatn" font-weight="900" font-size="19">{fa(w)}</text>'
        for i, w in enumerate(wks)
    )
    ser_svg = "".join(
        f'<g><path d="{s["d"]}" stroke="{esc(s["p"].get("color") or "#F59E0B")}" stroke-width="{"5.2" if s["i"] == 0 else "3.8"}" fill="none" stroke-linecap="round"/>'
        + "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{"4.8" if s["i"] == 0 else "3.6"}" fill="{esc(s["p"].get("color") or "#F59E0B")}" stroke="#0D1730" stroke-width="1.6"/>' for x, y in s["pts"][:-1])
        + f'<circle cx="{s["ex"]:.1f}" cy="{s["ey"]:.1f}" r="{"10" if s["i"] == 0 else "7.5"}" fill="{esc(s["p"].get("color") or "#F59E0B")}" stroke="#fff" stroke-width="2.5"/>'
        + f'<line x1="{s["ex"] + 10:.1f}" y1="{s["ey"]:.1f}" x2="{s["ex"] + 24:.1f}" y2="{s["ly"]:.1f}" stroke="{esc(s["p"].get("color") or "#F59E0B")}" stroke-opacity=".6" stroke-width="1.6"/>'
        + f'<rect x="{s["ex"] + 24:.1f}" y="{s["ly"] - 16:.1f}" width="136" height="32" rx="10" fill="#091124" stroke="{esc(s["p"].get("color") or "#F59E0B")}" stroke-width="1.6"/>'
        + f'<text x="{s["ex"] + 92:.1f}" y="{s["ly"] + 5:.1f}" text-anchor="middle" fill="#fff" font-family="Vazirmatn" font-weight="900" font-size="15">{esc(s["p"].get("short") or s["p"]["name"][:8])} ({fa(s["p"]["goals"])})</text></g>'
        for s in series
    )
    return (
        '<div class="xm" style="flex:1">'
        + _mod_head("مسیر و ریتم رقابت کفش طلا (۸ هفته اخیر)", "<span class='fm gold'>GOLDEN BOOT RACE</span>", "#FBBF24")
        + f'<div class="fc" dir="ltr" style="flex:1"><svg style="width:100%;height:auto;max-height:400px" viewBox="0 0 {int(w_s)} {int(h_s)}" fill="none">'
        f'<defs><linearGradient id="la" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{esc(t4[0].get("color") or "#38BDF8")}" stop-opacity=".3"/><stop offset="1" stop-color="{esc(t4[0].get("color") or "#38BDF8")}" stop-opacity="0"/></linearGradient></defs>'
        f'{y_svg}{x_svg}<line x1="{pl:.0f}" y1="{pt + ph:.0f}" x2="{w_s - pr:.0f}" y2="{pt + ph:.0f}" stroke="#ffffff33" stroke-width="1.8"/>'
        f'<rect x="{pl + pw / 2 - 104:.0f}" y="{h_s - 32:.0f}" width="208" height="28" rx="14" fill="#091124" stroke="#FBBF24" stroke-opacity=".42" stroke-width="1.4"/>'
        f'<text x="{pl + pw / 2:.0f}" y="{h_s - 12:.0f}" text-anchor="middle" fill="#FDE68A" font-family="Vazirmatn" font-weight="800" font-size="15">شماره هفته رقابت‌ها</text>'
        f'<path d="{l1["d"]} L {l1["ex"]:.1f} {pt + ph:.0f} L {pl:.0f} {pt + ph:.0f} Z" fill="url(#la)"/>'
        f'{ser_svg}</svg></div></div>'
    )


def render_top_scorers_html(
    data: dict[str, Any],
    *,
    fmt: str = "4:5",
    header_mode: str = "full",
    theme: str = "gold",
    slide: str = "slide1",
    sort_by: str = "goals",
    show_pen: bool = True,
    modules: list[dict[str, Any]] | None = None,
) -> str:
    w, h_px = TOP_SCORERS_FORMATS.get(fmt, (1080, 1350))
    is_story = fmt == "9:16"
    is_wide = fmt == "16:9"
    # استاندارد یکپارچه فریم چهارگوشه قرمز XGPedia
    pad_top, pad_bot = (139, 171) if is_story else ((22, 16) if is_wide else (24, 20))

    P = _rank_players(data, sort_by=sort_by)
    if modules is None:
        modules, _ = get_top_scorers_modules(data, slide)
    active = [m for m in modules if m.get("enabled")]
    th = "classic" if theme == "classic" else "gold"
    tc = "#FBBF24" if th == "gold" else "#E62E45"
    lead = P[0] if P else {}

    show_hero = (header_mode != "compact") and bool(lead) and any(m["id"] == "leaderboard" for m in active)
    hero_html = _render_leader_hero(lead, th, sort_by, fmt) if show_hero else ""

    blocks = []
    for m in active:
        mid = m["id"]
        if mid == "leaderboard":
            inner = _render_leaderboard(P, th, show_pen=show_pen)
        elif mid == "insight":
            inner = _render_insight(data, P, th)
        elif mid == "clinical_trio":
            inner = _render_clinical_trio(P)
        elif mid == "duel" and len(P) >= 2:
            inner = _render_duel(P, th)
        elif mid == "radar" and len(P) >= 2:
            inner = _render_radar(P)
        elif mid == "matrix":
            inner = _render_matrix(P)
        elif mid == "trajectory":
            inner = _render_trajectory(data, P)
        else:
            continue
        if inner:
            cls = "mf" if (m.get("span") == "half" and m.get("can_half", False)) else "w-full"
            blocks.append(f'<div class="mod-slot {cls}">{inner}</div>')

    cx, rx = w // 2, w - 147
    pitch_svg = (
        f'<svg class="bg-svg" viewBox="0 0 {w} {h_px}" preserveAspectRatio="xMidYMid slice" fill="none">'
        '<defs><pattern id="tg" width="54" height="54" patternUnits="userSpaceOnUse"><path d="M54 0H0v54" stroke="#F8FAFC" stroke-opacity=".055"/></pattern>'
        f'<radialGradient id="rf" cx="50%" cy="28%" r="44%"><stop offset="0" stop-color="{tc}" stop-opacity=".2"/>'
        '<stop offset=".55" stop-color="#E62E45" stop-opacity=".07"/><stop offset="1" stop-color="#E62E45" stop-opacity="0"/></radialGradient></defs>'
        '<rect width="100%" height="100%" fill="url(#tg)"/>'
        f'<rect x="12" y="12" width="{w - 24}" height="{h_px - 24}" rx="18" stroke="#F8FAFC" stroke-opacity=".11" stroke-width="1.5"/>'
        f'<g stroke="#F8FAFC" stroke-opacity=".09" stroke-width="1.5"><line x1="{cx}" y1="12" x2="{cx}" y2="{h_px - 12}" stroke-dasharray="8 8"/>'
        f'<circle cx="{cx}" cy="315" r="145"/></g>'
        f'<g stroke="#F8FAFC" stroke-opacity=".07" stroke-width="1.5"><rect x="12" y="145" width="135" height="360"/>'
        f'<path d="M147 245A95 95 0 0 1 147 405"/><rect x="{rx}" y="145" width="135" height="360"/>'
        f'<path d="M{rx} 245A95 95 0 0 0 {rx} 405"/></g>'
        f'<circle cx="{cx}" cy="315" r="250" fill="url(#rf)"/>'
        f'<circle cx="{cx}" cy="315" r="215" stroke="#E62E45" stroke-opacity=".18" stroke-width="1.2" stroke-dasharray="4 6"/>'
        f'<circle cx="{cx}" cy="315" r="295" stroke="#F8FAFC" stroke-opacity=".07"/>'
        f'<circle cx="{cx}" cy="315" r="375" stroke="#F8FAFC" stroke-opacity=".045"/>'
        f'<path d="M24 44V24H44M{w - 24} 44V24H{w - 44}M24 {h_px - 44}V{h_px - 24}H44M{w - 24} {h_px - 44}V{h_px - 24}H{w - 44}" '
        'stroke="#E62E45" stroke-width="2.2" stroke-linecap="round"/></svg>'
    )
    ag_bg = (
        f"radial-gradient(circle at 82% 24%,{esc(lead.get('color') or '#38BDF8')}36,transparent 48%),"
        f"radial-gradient(circle at 18% 26%,{tc}28,transparent 46%),"
        "radial-gradient(circle at 50% 80%,#e62e4518,transparent 52%)"
    )
    sl_en = next((en for sid, _, en, _ in TOP_SCORERS_SLIDES if sid == slide), "GOLDEN BOOT RACE")
    trophy = '<svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="#FBBF24" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M8 21h8m-4-4v4m-5-17h10v5a5 5 0 01-10 0V4zM5 6H3v2a3 3 0 003 3h1m12-5h2v2a3 3 0 01-3 3h-1"/></svg>'
    logo_uri = _brand_logo_data_uri()
    font_css = build_embedded_font_css()

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl"><head><meta charset="UTF-8"><style>
{font_css}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:{w}px;height:{h_px}px;overflow:hidden;background:#0D1730;color:#F8FAFC;font-family:'Vazirmatn',sans-serif;font-feature-settings:"tnum";font-variant-numeric:tabular-nums;}}
.fm{{font-family:'JetBrains Mono','Space Grotesk',monospace;}} .fd{{font-family:'Space Grotesk',sans-serif;}}
.fc{{display:flex;align-items:center;justify-content:center;}} .min-w-0{{min-width:0;}}
#ea{{position:relative;width:{w}px;height:{h_px}px;background:#0D1730;display:flex;flex-direction:column;justify-content:space-between;padding:{pad_top}px 0 {pad_bot}px 0;overflow:hidden;}}
.ag,.bg-svg,.scanlines{{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0;}}
.scanlines{{background:repeating-linear-gradient(to bottom,#ffffff04 0 1px,#0000 1px 4px);}}
.hdr{{position:relative;z-index:5;display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 36px 8px;flex-shrink:0;}}
.hdr-pills{{display:flex;align-items:center;flex-wrap:wrap;gap:9px;}}
.c-pill{{display:inline-flex;align-items:center;gap:8px;padding:6px 16px;border-radius:999px;font-size:23px;font-weight:900;background:#152347e6;border:1px solid #ffffff2e;color:#F8FAFC;}}
.c-pill.red{{background:#e62e452e;border-color:#e62e4580;color:#FF6B7F;font-size:20px;font-weight:800;}}
.hdr-sub{{font-size:20px;font-weight:800;color:#E2E8F0;margin-top:5px;}}
.hdr-logo{{height:42px;width:auto;}}
.stage{{position:relative;z-index:5;flex:1;padding:8px 40px;display:flex;flex-direction:column;justify-content:space-between;gap:12px;overflow:hidden;min-height:0;}}
.xh{{position:relative;border-radius:24px;overflow:hidden;padding:16px 22px;background:linear-gradient(145deg,#152344eb,#091024f5 62%,#161c34f0);border:1.5px solid #fbbf2461;box-shadow:0 20px 48px -12px #000000b3,0 0 36px -10px #fbbf242e,inset 0 1px 0 #fde68a47;flex-shrink:0;}}
.xh.cl{{border-color:#e62e457a;box-shadow:0 20px 48px -12px #000000b3,0 0 36px -10px #e62e4538;}}
.xh-wm{{position:absolute;left:16px;top:-22px;font-size:185px;font-weight:900;line-height:1;opacity:.06;pointer-events:none;}}
.xh-glow{{position:absolute;right:-50px;top:-50px;width:260px;height:260px;border-radius:999px;pointer-events:none;}}
.xh-top{{position:relative;z-index:2;display:flex;align-items:center;justify-content:space-between;gap:16px;}}
.xh-left{{display:flex;align-items:center;gap:16px;min-width:0;flex:1;}}
.xh-info{{display:flex;flex-direction:column;gap:5px;min-width:0;}}
.xh-badges{{display:flex;align-items:center;gap:8px;flex-wrap:wrap;}}
.xh-crown{{display:inline-flex;align-items:center;gap:6px;padding:5px 14px;border-radius:999px;font-size:17.5px;font-weight:900;}}
.gp{{background:linear-gradient(135deg,#fde68a38,#f59e0b24);border:1.5px solid #fbbf2485;color:#FDE68A;}}
.cp2{{background:linear-gradient(135deg,#e62e4547,#e62e4524);border:1.5px solid #ff6b7f8c;color:#FF8596;}}
.xh-pos{{padding:4px 12px;border-radius:999px;background:#ffffff1a;font-size:16px;font-weight:800;color:#E2E8F0;}}
.xh-name{{font-size:44px;font-weight:900;color:#FFF;line-height:1.1;}}
.xh-club{{display:flex;align-items:center;gap:9px;font-size:24px;font-weight:800;color:#E2E8F0;}}
.lh-hot{{display:inline-flex;align-items:center;gap:4px;padding:2px 9px;border-radius:999px;background:rgba(249,115,22,0.2);border:1px solid rgba(251,146,60,0.45);color:#FDBA74;font-size:13px;font-weight:800;}}
.xh-right{{display:flex;flex-direction:column;align-items:flex-end;gap:6px;flex-shrink:0;}}
.xh-goals-row{{display:flex;align-items:baseline;gap:8px;}}
.xh-goals{{font-size:74px;font-weight:900;line-height:.88;}}
.gt{{background:linear-gradient(135deg,#FEF08A 0%,#FBBF24 45%,#D97706 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}}
.wtxt{{color:#FFF;}}
.xh-glbl b{{display:block;font-size:23px;color:#FFF;line-height:1;}} .xh-glbl span{{font-size:12px;color:#94A3B8;font-weight:700;}}
.xh-subpills{{display:flex;gap:6px;}}
.lh-pill{{padding:4px 12px;border-radius:10px;background:#ffffff16;border:1px solid #ffffff2a;font-size:16.5px;font-weight:800;color:#CBD5E1;}}
.lh-pill b{{color:#FFF;}} .lh-pill.em{{background:rgba(16,185,129,0.16);border-color:rgba(52,211,153,0.38);color:#6EE7B7;}}
.xh-kpis{{position:relative;z-index:2;display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:12px;padding-top:11px;border-top:1px solid #ffffff1f;}}
.xh-kpi{{border-radius:14px;background:#060C1Dd9;border:1px solid #ffffff1f;padding:7px 14px;display:flex;align-items:center;justify-content:space-between;}}
.xh-kpi.sky{{border-color:rgba(56,189,248,0.3);}}
.xh-kpi span{{font-size:19px;font-weight:800;color:#E2E8F0;}} .xh-kpi b{{font-size:28px;font-weight:900;}}
.mods-grid{{flex:1;min-height:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;align-content:stretch;}}
.mod-slot{{display:flex;min-width:0;min-height:0;}} .w-full{{grid-column:1 / -1;}} .mf{{grid-column:span 1;}}
.xm,.xe{{position:relative;flex:1;border-radius:22px;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;box-shadow:0 14px 36px -10px #0000008c,inset 0 1px 0 #ffffff17;padding:14px 20px;}}
.xm{{background:linear-gradient(165deg,#101d3bdb,#091023f2);border:1.5px solid #f8fafc24;}}
.xe{{background:linear-gradient(155deg,#121f3deb,#090f20f7);border:1.5px solid #7fa6e83d;}}
.mh{{display:flex;align-items:center;justify-content:space-between;gap:10px;padding-bottom:8px;margin-bottom:9px;border-bottom:1px solid #ffffff1f;flex-shrink:0;}}
.mh-left{{display:flex;align-items:center;gap:9px;}}
.mh-bar{{width:7px;height:22px;border-radius:99px;}}
.mt{{font-size:26px;font-weight:900;color:#FFF;}}
.mh-sub{{font-size:16.5px;font-weight:800;color:#E2E8F0;}} .mh-sub .gold{{color:#FCD34D;}} .mh-sub .em{{color:#6EE7B7;}}
.lb-leg{{display:flex;align-items:center;gap:12px;font-size:17px;font-weight:800;color:#E2E8F0;}}
.lb-leg span{{display:inline-flex;align-items:center;gap:5px;}}
.sw-npg{{width:12px;height:8px;border-radius:2px;background:#E62E45;display:inline-block;}}
.sw-pen{{width:12px;height:8px;border-radius:2px;background:#64748b99;border:1px solid #ffffff4d;display:inline-block;}}
.sw-xg{{width:3px;height:13px;border-radius:99px;background:#fff;box-shadow:0 0 8px #38BDF8;display:inline-block;}}
.ps{{background-image:repeating-linear-gradient(-45deg,#ffffff52 0 4px,#ffffff0f 4px 8px);}}
.lr-list{{display:flex;flex-direction:column;gap:6px;flex:1;justify-content:space-between;}}
.lr{{position:relative;display:grid;grid-template-columns:42px minmax(235px,1.22fr) minmax(0,1.25fr) 172px;align-items:center;gap:10px;padding:8px 13px;border-radius:13px;background:linear-gradient(135deg,#16213ed6,#0b1224eb);border:1px solid #ffffff1c;overflow:hidden;}}
.lr-strip{{position:absolute;right:0;top:5px;bottom:5px;width:4px;border-radius:99px 0 0 99px;}}
.rk-b{{width:34px;height:34px;border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:900;}}
.r2{{background:linear-gradient(145deg,#E2E8F0,#94A3B8);color:#091023;}}
.r3{{background:linear-gradient(145deg,#FDBA74,#C2410C);color:#091023;}}
.rn{{background:#ffffff14;border:1px solid #ffffff29;color:#CBD5E1;}}
.lr-pl{{display:flex;align-items:center;gap:9px;min-width:0;}}
.lr-name{{display:flex;align-items:center;gap:6px;font-size:26px;font-weight:900;color:#FFF;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.lr-club{{font-size:18px;font-weight:700;color:#CBD5E1;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.lr-pen{{color:#FDE047;font-weight:800;font-size:16px;}}
.lr-bar-wrap{{position:relative;height:13px;width:100%;border-radius:99px;background:#060C1E;border:1px solid #ffffff1a;display:flex;align-items:center;}}
.lr-track{{height:100%;width:100%;border-radius:99px;overflow:hidden;display:flex;}}
.bar-npg,.bar-pen{{height:100%;}} .bar-pen{{border-left:1px solid #ffffff66;}}
.xg-needle{{position:absolute;top:-3.5px;bottom:-3.5px;width:3px;border-radius:99px;background:#FFF;box-shadow:0 0 9px #38BDF8,0 0 4px #FFF;z-index:5;}}
.lr-end{{display:flex;align-items:center;justify-content:flex-end;gap:8px;}}
.lr-g{{display:flex;flex-direction:column;align-items:flex-end;line-height:1;}}
.lr-g b{{font-size:33px;font-weight:900;color:#FFF;}}
.lr-g span{{font-size:17px;font-weight:800;color:#7DD3FC;margin-top:3px;}}
.dp{{padding:6px 11px;border-radius:10px;border:1px solid;font-size:20px;font-weight:900;line-height:1;}}
.dp.pos{{background:rgba(16,185,129,0.2);border-color:rgba(52,211,153,0.5);color:#6EE7B7;}}
.dp.neg{{background:rgba(244,63,94,0.2);border-color:rgba(251,113,133,0.5);color:#FDA4AF;}}
.dp.neu{{background:#ffffff12;border-color:#ffffff24;color:#94A3B8;}}
.ins-top{{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:7px;}}
.ins-title{{display:flex;align-items:center;gap:8px;font-size:24px;font-weight:900;color:#FCD34D;}}
.ins-bar{{width:7px;height:18px;border-radius:99px;}}
.ins-pills{{display:flex;gap:6px;flex-wrap:wrap;}}
.in-p{{padding:4px 12px;border-radius:9px;background:#ffffff16;border:1px solid #ffffff24;font-size:17px;font-weight:800;color:#F1F5F9;}}
.in-p.gold{{background:rgba(245,158,11,0.16);border-color:rgba(251,191,36,0.38);color:#FCD34D;}}
.in-p.em{{background:rgba(16,185,129,0.16);border-color:rgba(52,211,153,0.38);color:#6EE7B7;}}
.ins-txt{{font-size:22px;font-weight:700;color:#F8FAFC;line-height:1.55;margin-top:8px;}}
.tri-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;}}
.tri-box{{border-radius:14px;background:#070E20d9;border:1px solid #ffffff1f;padding:10px 13px;display:flex;flex-direction:column;gap:6px;}}
.tri-top{{display:flex;justify-content:space-between;font-size:16px;font-weight:800;color:#CBD5E1;}}
.tri-bot{{display:flex;align-items:center;justify-content:space-between;gap:6px;}}
.tri-pl{{display:flex;align-items:center;gap:7px;font-size:20px;font-weight:900;color:#FFF;}}
.tri-v{{font-size:25px;font-weight:900;}}
.duel-top{{display:grid;grid-template-columns:4fr 3fr 4fr;align-items:center;gap:10px;margin-bottom:14px;}}
.duel-p{{display:flex;flex-direction:column;align-items:center;text-align:center;}}
.dp-av{{position:relative;margin-bottom:6px;}}
.dp-cr{{position:absolute;bottom:-6px;left:-6px;}}
.dp-name{{font-size:27px;font-weight:900;color:#FFF;}}
.dp-sub{{font-size:18px;font-weight:700;color:#E2E8F0;margin-top:3px;}}
.dp-pills{{display:flex;gap:6px;margin-top:7px;}}
.dp-pills span{{padding:4px 12px;border-radius:10px;background:#ffffff1f;font-size:18px;font-weight:900;}}
.dp-pills span.sky{{background:rgba(14,165,233,0.18);border:1px solid rgba(56,189,248,0.4);color:#7DD3FC;}}
.duel-mid{{display:flex;flex-direction:column;align-items:center;gap:12px;}}
.vs-dm{{width:64px;height:64px;border-radius:18px;transform:rotate(45deg);background:#E62E45;border:2px solid #ffffff4d;box-shadow:0 0 32px #e62e458c;display:flex;align-items:center;justify-content:center;}}
.vs-dm span{{transform:rotate(-45deg);font-size:26px;font-weight:800;color:#FFF;}}
.mpg-box{{width:100%;border-radius:14px;background:#070E20;border:1px solid #ffffff1f;padding:7px 10px;text-align:center;}}
.mpg-k{{font-size:15px;font-weight:800;color:#CBD5E1;}}
.mpg-v{{display:flex;justify-content:center;gap:10px;font-size:21px;font-weight:900;margin-top:2px;}}
.dm-list{{display:flex;flex-direction:column;gap:10px;}}
.dm-top{{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;font-size:22px;font-weight:900;margin-bottom:4px;}}
.dm-top span:last-child{{text-align:left;}} .dm-top .k{{font-size:18.5px;color:#F1F5F9;font-weight:800;text-align:center;}}
.dm-bars{{display:grid;grid-template-columns:1fr 1fr;gap:8px;}}
.ct{{height:13px;background:#ffffff1a;overflow:hidden;display:flex;align-items:center;}}
.ct.hs,.ch{{border-radius:0 99px 99px 0;}} .ct.as,.ca{{border-radius:99px 0 0 99px;}}
.ct.hs{{justify-content:flex-end;}} .ct.as{{justify-content:flex-start;}} .ch,.ca{{height:100%;}}
.rad-leg{{display:flex;gap:14px;font-size:15px;font-weight:800;}}
.rad-leg span{{display:inline-flex;align-items:center;gap:6px;}} .rad-leg i{{width:10px;height:10px;border-radius:99px;display:inline-block;}}
.ftr{{position:relative;z-index:5;padding:10px 44px 10px;border-top:1px solid #ffffff1f;display:flex;align-items:center;justify-content:space-between;font-size:15px;color:#CBD5E1;flex-shrink:0;}}
.ftr-left{{display:flex;align-items:center;gap:9px;}}
.ftr-dot{{width:10px;height:10px;border-radius:99px;background:#E62E45;}}
.ftr-tag{{font-size:17px;font-weight:800;letter-spacing:.10em;color:#F1F5F9;}}
.ftr-right{{display:flex;align-items:center;gap:10px;}} .ftr-right b{{color:#FFF;font-size:19px;}}

footer, footer .fbw, footer .cf-row, footer .fi, footer .cf-left, footer .cf-right, .xg-footer, .foot-row, .card-footer{{flex-wrap:nowrap!important;white-space:nowrap!important;min-width:0!important;}}
footer span, footer div, .pl-foot-tag, .pl-foot-s, .in-foot-tag, .pr-foot-tag, .st-foot-tag, .cf-tag{{white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;min-width:0!important;}}
</style></head><body>
<div id="ea">
  <div class="ag" style="background:{ag_bg}"></div>
  {pitch_svg}
  <div class="scanlines"></div>
  <header class="hdr">
    <div>
      <div class="hdr-pills">
        <span class="c-pill">{trophy}<span>{esc(data.get("competition") or "کفش طلا")}</span></span>
        <span class="c-pill red">{fa(esc(data.get("round") or "رقابت کفش طلا"))}</span>
      </div>
      <div class="hdr-sub">فصل {fa(esc(data.get("season") or "26/27"))}</div>
    </div>
    <img class="hdr-logo" src="{logo_uri}" alt="XGPedia"/>
  </header>
  <main class="stage">
    {hero_html}
    <section class="mods-grid">{"".join(blocks)}</section>
  </main>
  <footer class="ftr">
    <div class="ftr-left"><span class="ftr-dot"></span><span class="ftr-tag fm" dir="ltr">{esc(str(data.get("leagueEn") or "TOP SCORERS").upper())} {esc(data.get("season") or "26/27")} {esc(data.get("weekCode") or "LIVE")} • {sl_en}</span></div>
    <div class="ftr-right fm" dir="ltr"><b>@XGPedia</b><span>|</span><span>{esc(data.get("source") or "Opta / FPL")}</span></div>
  </footer>
</div></body></html>"""
