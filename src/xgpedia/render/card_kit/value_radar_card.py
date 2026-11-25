"""رندرر ۱۰۰٪ آفلاین و ماژولار کارت ۵اسلایدی «رادار ارزش بازار و شکار نقل‌وانتقالات (+EV)».

۵ اسلاید استاندارد با هویت بصری یکپارچه XGPedia:
  - `slide1`: نمودار پراکندگی ارزش در برابر قیمت (Value Scatter + منطقه شکار +EV)
  - `slide2`: تابلوی شکارهای طلایی (+EV Leaderboard با لوگوی واقعی باشگاه‌ها)
  - `slide3`: دوئل شکار ارزان در برابر ستارهٔ گران‌قیمت (Bargain vs. Premium)
  - `slide4`: جواهرهای کم‌مالکیت و بیش‌عملکردها (Hidden Gems & Finishing Delta)
  - `slide5`: پروندهٔ اسکاتینگ شکار برتر هفته (Scout Dossier #1)
"""
from __future__ import annotations

from typing import Any

from src.xgpedia.render.card_kit.helpers import (
    _hex_to_rgb,
    ensure_dark_bg_contrast,
    esc,
    fa,
)
from src.xgpedia.render.cards import _brand_logo_data_uri
from src.xgpedia.render.studio_engine import build_embedded_font_css

VALUE_RADAR_FORMATS: dict[str, tuple[int, int]] = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}

VALUE_RADAR_SLIDES: list[tuple[str, str, str]] = [
    ("slide1", "نمودار ارزش در برابر قیمت (+EV)", "full"),
    ("slide2", "تابلوی شکارهای طلایی (+EV)", "full"),
    ("slide3", "شکار ارزان در برابر ستاره گران", "full"),
    ("slide4", "کم‌مالکیت‌ها و دلتای گلزنی", "full"),
    ("slide5", "پروندهٔ شکار برتر هفته (#1)", "full"),
]

_THEMES: dict[str, tuple[str, str]] = {
    "classic": ("#E62E45", "#10B981"),
    "emerald": ("#10B981", "#38BDF8"),
    "gold": ("#F59E0B", "#10B981"),
    "scout": ("#38BDF8", "#E62E45"),
}

_MODULE_SPECS: list[tuple[str, str, bool]] = [
    ("kpis", "نوار ۳ شاخص خلاصه بازار", True),
    ("verdict", "جمع‌بندی تحریریه اسکاتینگ", True),
    ("grid", "بافت گرید تاکتیکی پس‌زمینه", True),
]


def get_value_radar_modules(item: dict[str, Any], slide: str = "slide1") -> tuple[list[dict[str, Any]], list[str]]:
    mods: list[dict[str, Any]] = []
    missing: list[str] = []
    has_verdict = bool(str(item.get("editorial_verdict") or "").strip())
    for mid, title_fa, def_on in _MODULE_SPECS:
        if mid == "verdict" and not has_verdict:
            missing.append("جمع‌بندی تحریریه (متن ندارد)")
            mods.append({"id": mid, "title_fa": title_fa, "enabled": False, "span": "full", "can_half": False})
        else:
            mods.append({"id": mid, "title_fa": title_fa, "enabled": def_on, "span": "full", "can_half": False})
    return mods, missing


def _f1(v: Any) -> str:
    return fa(f"{float(v or 0):.1f}")


def _f2(v: Any) -> str:
    return fa(f"{float(v or 0):.2f}")


def _fs1(v: Any) -> str:
    return fa(f"{float(v or 0):+.1f}")


def _brand_logo_img(height: int = 44) -> str:
    uri = _brand_logo_data_uri()
    if uri:
        return f'<img src="{uri}" alt="XGPedia" style="height:{height}px;width:auto;display:block;object-fit:contain"/>'
    return '<div style="font-weight:900;font-size:30px" dir="ltr"><span style="color:#E62E45">XG</span><span style="color:#F8FAFC">Pedia</span></div>'


def _club_crest(code: str, club_name: str, color: str, size: int = 44) -> str:
    cd = (code or "PL").strip().upper()[:3]
    try:
        from src.xgpedia.providers.pl_badges_free import get_pl_badge_data_uri, lookup_pl_club
        info = lookup_pl_club(club_name or cd, tla_hint=cd)
        if info and info[4]:
            uri = get_pl_badge_data_uri(info[1], tla_hint=info[1], badge_code=info[4], size=70, fetch_network=False)
            if uri:
                return (
                    f'<div style="width:{size}px;height:{size}px;border-radius:12px;background:rgba(15,23,42,.72);'
                    f'border:1px solid rgba(255,255,255,.16);padding:4px;display:flex;align-items:center;'
                    f'justify-content:center;flex-shrink:0">'
                    f'<img src="{uri}" alt="{esc(cd)}" style="width:100%;height:100%;object-fit:contain;display:block"/>'
                    f'</div>'
                )
    except Exception:
        pass
    c = ensure_dark_bg_contrast(color or "#E62E45", min_ratio=4.2)
    return (
        f'<div style="width:{size}px;height:{size}px;border-radius:12px;background:rgba(15,23,42,.85);'
        f'border:1.5px solid {c};display:flex;align-items:center;justify-content:center;'
        f'font-family:Space Grotesk,sans-serif;font-weight:800;font-size:{max(12, size // 3)}px;color:#fff;flex-shrink:0">'
        f'{esc(cd)}</div>'
    )


def _scatter_svg(players: list[dict[str, Any]], avg_p: float, avg_x: float, w_svg: int = 960, h_svg: int = 580) -> str:
    """نمودار پراکندگی هوشمند با محور X شکسته (Broken Axis //) برای فاصله‌های بزرگ قیمت + ضدهم‌پوشانی برچسب‌ها."""
    if not players:
        return ""
    pts = players[:8]
    prices = sorted(float(p.get("price") or 5.0) for p in pts)
    xgis = [float(p.get("xgi90") or 0.0) for p in pts]

    # تشخیص خودکار شکاف بزرگ روی محور قیمت (مثلاً ۵-۷ میلیون در برابر ۱۵ میلیون هالند)
    break_idx = -1
    max_gap = 0.0
    total_span = max(0.5, prices[-1] - prices[0])
    for i in range(len(prices) - 1):
        g = prices[i + 1] - prices[i]
        if g > max_gap:
            max_gap = g
            break_idx = i
    use_broken_x = (len(prices) >= 3) and (max_gap >= 2.4) and (max_gap / total_span >= 0.36)

    ml, mr, mt, mb = 88, 34, 46, 68
    pw = w_svg - ml - mr
    ph = h_svg - mt - mb

    # زوم هوشمند محور Y برای استفاده کامل از ارتفاع نمودار
    min_y = max(0.0, round(min(xgis) - 0.10, 2))
    if min_y < 0.12:
        min_y = 0.0
    max_y = max(round(max(xgis) * 1.14, 2), min_y + 0.35)

    def sy(val: float) -> float:
        return mt + ph - ((val - min_y) / max(0.1, max_y - min_y)) * ph

    if use_broken_x:
        low_min = max(3.8, round(prices[0] - 0.4, 1))
        low_max = round(prices[break_idx] + 0.5, 1)
        hi_min = round(prices[break_idx + 1] - 0.8, 1)
        hi_max = round(prices[-1] + 0.8, 1)
        left_w = pw * 0.72
        gap_w = pw * 0.09
        right_w = pw - left_w - gap_w
        gap_x0 = ml + left_w
        gap_x1 = gap_x0 + gap_w

        def sx(val: float) -> float:
            if val <= low_max:
                return ml + ((val - low_min) / max(0.4, low_max - low_min)) * left_w
            return gap_x1 + ((val - hi_min) / max(0.6, hi_max - hi_min)) * right_w

        x_ticks = [
            (low_min + (low_max - low_min) * (i / 3.0)) for i in range(4)
        ] + [round(prices[-1], 1)]
    else:
        min_p = max(3.5, round(prices[0] - 0.6, 1))
        max_p = round(prices[-1] + 0.8, 1)
        gap_x0 = gap_x1 = 0.0

        def sx(val: float) -> float:
            return ml + ((val - min_p) / max(0.5, max_p - min_p)) * pw

        x_ticks = [min_p + (max_p - min_p) * (i / 4.0) for i in range(5)]

    # خط تعادل ارزش منصفانه (Fair Value) در بخش اصلی
    slope = avg_x / max(avg_p, 4.0)
    if use_broken_x:
        y_l0 = min(max_y, max(min_y, slope * low_min))
        y_l1 = min(max_y, max(min_y, slope * low_max))
        y_r1 = min(max_y, max(min_y, slope * hi_max))
        poly_ev = f"{ml},{mt} {gap_x0:.1f},{mt} {gap_x0:.1f},{sy(y_l1):.1f} {ml},{sy(y_l0):.1f}"
        fair_line = (
            f'<line x1="{ml}" y1="{sy(y_l0):.1f}" x2="{gap_x0:.1f}" y2="{sy(y_l1):.1f}" stroke="#10B981" stroke-width="3" stroke-dasharray="8 6" opacity=".88"/>'
            f'<line x1="{gap_x1:.1f}" y1="{sy(min(max_y, max(min_y, slope * hi_min))):.1f}" x2="{ml+pw}" y2="{sy(y_r1):.1f}" stroke="#10B981" stroke-width="2.5" stroke-dasharray="8 6" opacity=".65"/>'
        )
        break_band = (
            f'<rect x="{gap_x0:.1f}" y="{mt}" width="{gap_w:.1f}" height="{ph}" fill="rgba(13,23,48,.82)"/>'
            f'<line x1="{gap_x0:.1f}" y1="{mt}" x2="{gap_x0:.1f}" y2="{mt+ph}" stroke="#64748B" stroke-width="2" stroke-dasharray="5 6"/>'
            f'<line x1="{gap_x1:.1f}" y1="{mt}" x2="{gap_x1:.1f}" y2="{mt+ph}" stroke="#64748B" stroke-width="2" stroke-dasharray="5 6"/>'
            f'<text x="{(gap_x0+gap_x1)/2:.1f}" y="{mt+ph/2-8:.1f}" text-anchor="middle" fill="#94A3B8" font-family="Space Grotesk,sans-serif" font-size="22" font-weight="900">⋯ // ⋯</text>'
            f'<text x="{(gap_x0+gap_x1)/2:.1f}" y="{mt+ph/2+18:.1f}" text-anchor="middle" fill="#94A3B8" font-family="Vazirmatn,sans-serif" font-size="14" font-weight="800">فاصله قیمت</text>'
        )
    else:
        y_l0 = min(max_y, max(min_y, slope * min_p))
        y_l1 = min(max_y, max(min_y, slope * max_p))
        poly_ev = f"{ml},{mt} {ml+pw},{mt} {ml+pw},{sy(y_l1):.1f} {ml},{sy(y_l0):.1f}"
        fair_line = f'<line x1="{ml}" y1="{sy(y_l0):.1f}" x2="{ml+pw}" y2="{sy(y_l1):.1f}" stroke="#10B981" stroke-width="3" stroke-dasharray="8 6" opacity=".88"/>'
        break_band = ""

    # خطوط گرید و برچسب محورها (درشت و خوانا)
    grid_lines = []
    for i in range(5):
        gv = min_y + (max_y - min_y) * (i / 4.0)
        gy = sy(gv)
        grid_lines.append(
            f'<line x1="{ml}" y1="{gy:.1f}" x2="{ml+pw}" y2="{gy:.1f}" stroke="rgba(255,255,255,.09)" stroke-dasharray="4 6"/>'
            f'<text x="{ml-14}" y="{gy+6:.1f}" text-anchor="end" fill="#CBD5E1" font-family="Space Grotesk,sans-serif" font-size="18" font-weight="800">{gv:.2f}</text>'
        )
    for pv in x_ticks:
        gx = sx(pv)
        grid_lines.append(
            f'<line x1="{gx:.1f}" y1="{mt}" x2="{gx:.1f}" y2="{mt+ph}" stroke="rgba(255,255,255,.08)" stroke-dasharray="4 6"/>'
            f'<text x="{gx:.1f}" y="{mt+ph+30}" text-anchor="middle" fill="#CBD5E1" font-family="Space Grotesk,sans-serif" font-size="18" font-weight="800">£{pv:.1f}M</text>'
        )

    # محاسبه موقعیت نقطه‌ها و رفع خودکار هم‌پوشانی برچسب‌ها (2D Repulsion Solver)
    nodes = []
    for idx, p in enumerate(pts):
        px = sx(float(p.get("price") or 5.0))
        py = sy(float(p.get("xgi90") or 0.0))
        is_top = idx < 3
        col = "#10B981" if is_top else ensure_dark_bg_contrast(str(p.get("color") or "#38BDF8"), min_ratio=4.6)
        rad = 16 if idx == 0 else (13 if is_top else 10)
        lbl = str(p.get("name") or "")[:15]
        # شروع برچسب کمی بالا یا پایین نقطه
        ly = py - (rad + 14) if (idx % 2 == 0) else py + (rad + 22)
        lx = px
        nodes.append({"idx": idx, "px": px, "py": py, "lx": lx, "ly": ly, "rad": rad, "col": col, "lbl": lbl, "is_top": is_top, "ev": float(p.get("ev_score") or 0)})

    # ۵۰ تکرار دفع برچسب‌های نزدیک به هم تا هیچ دو اسمی روی هم نیفتند
    min_dx, min_dy = 112.0, 34.0
    for _ in range(50):
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                a, b = nodes[i], nodes[j]
                dx = b["lx"] - a["lx"]
                dy = b["ly"] - a["ly"]
                if abs(dx) < min_dx and abs(dy) < min_dy:
                    push_y = (min_dy - abs(dy)) * 0.55
                    if dy >= 0:
                        a["ly"] -= push_y
                        b["ly"] += push_y
                    else:
                        a["ly"] += push_y
                        b["ly"] -= push_y
                    if abs(dx) < 55:
                        push_x = 12.0
                        if dx >= 0:
                            a["lx"] -= push_x
                            b["lx"] += push_x
                        else:
                            a["lx"] += push_x
                            b["lx"] -= push_x
        for nd in nodes:
            nd["lx"] = max(ml + 58, min(ml + pw - 58, nd["lx"]))
            nd["ly"] = max(mt + 36, min(mt + ph - 18, nd["ly"]))

    dots = []
    for nd in nodes:
        px, py, lx, ly = nd["px"], nd["py"], nd["lx"], nd["ly"]
        rad, col = nd["rad"], nd["col"]
        # اگر برچسب برای جلوگیری از هم‌پوشانی جابه‌جا شده، خط راهنمای ظریف رسم کن
        dist = ((lx - px) ** 2 + (ly - py) ** 2) ** 0.5
        if dist > rad + 22:
            dots.append(f'<line x1="{px:.1f}" y1="{py:.1f}" x2="{lx:.1f}" y2="{ly-6:.1f}" stroke="rgba(226,232,240,.38)" stroke-width="1.5"/>')
        dots.append(
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{rad+7}" fill="{col}" fill-opacity=".20"/>'
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{rad}" fill="{col}" stroke="#0D1730" stroke-width="2.5"/>'
        )
        bw = max(76, len(nd["lbl"]) * 11 + 22)
        dots.append(
            f'<rect x="{lx - bw/2:.1f}" y="{ly - 20:.1f}" width="{bw:.1f}" height="26" rx="8" fill="rgba(7,13,29,.88)" stroke="{"rgba(52,211,153,.65)" if nd["idx"] == 0 else "rgba(255,255,255,.16)"}"/>'
            f'<text x="{lx:.1f}" y="{ly - 2:.1f}" text-anchor="middle" fill="{"#34D399" if nd["idx"] == 0 else "#F8FAFC"}" font-family="Vazirmatn,sans-serif" font-size="{18 if nd["is_top"] else 16}" font-weight="900">{esc(nd["lbl"])}</text>'
        )

    return (
        f'<svg viewBox="0 0 {w_svg} {h_svg}" width="100%" height="100%" direction="ltr" style="display:block;direction:ltr">'
        f'<defs><linearGradient id="evZone" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="#10B981" stop-opacity=".24"/>'
        f'<stop offset="100%" stop-color="#10B981" stop-opacity=".02"/></linearGradient></defs>'
        f'<polygon points="{poly_ev}" fill="url(#evZone)"/>'
        f'{"".join(grid_lines)}'
        f'{fair_line}'
        f'{break_band}'
        f'<text x="{ml+18}" y="{mt+26}" text-anchor="start" fill="#34D399" font-family="Vazirmatn,sans-serif" font-size="19" font-weight="900">منطقهٔ شکار طلایی (+EV — زیرقیمت بازار)</text>'
        f'<text x="{ml+pw-16}" y="{mt+ph-14}" text-anchor="end" fill="#FB7185" font-family="Vazirmatn,sans-serif" font-size="17" font-weight="800" opacity=".90">منطقهٔ گران‌قیمت</text>'
        f'{"".join(dots)}'
        f'<text x="{ml+pw/2:.1f}" y="{h_svg-8}" text-anchor="middle" fill="#E2E8F0" font-family="Vazirmatn,sans-serif" font-size="19" font-weight="900">قیمت بازار (£ میلیون پوند)</text>'
        f'<text x="24" y="{mt+ph/2:.1f}" text-anchor="middle" fill="#E2E8F0" font-family="Vazirmatn,sans-serif" font-size="19" font-weight="900" transform="rotate(-90 24 {mt+ph/2:.1f})">خروجی امید گل + پاس گل (xGI / 90)</text>'
        f'</svg>'
    )


def render_value_radar_html(
    item: dict[str, Any],
    *,
    slide: str = "slide1",
    header_mode: str = "full",
    fmt: str = "4:5",
    theme: str = "classic",
    modules: list[dict[str, Any]] | None = None,
) -> str:
    """تولید HTML ۱۰۰٪ آفلاین کارت ۵اسلایدی رادار ارزش بازار و شکار نقل‌وانتقالات."""
    w, h = VALUE_RADAR_FORMATS.get(fmt, VALUE_RADAR_FORMATS["4:5"])
    is16 = fmt == "16:9"
    is9 = fmt == "9:16"
    accent, accent2 = _THEMES.get(theme, _THEMES["classic"])
    r1, g1, b1 = _hex_to_rgb(accent)
    r2, g2, b2 = _hex_to_rgb(accent2)

    if modules is None:
        modules, _ = get_value_radar_modules(item, slide)
    mod_map = {m["id"]: bool(m.get("enabled", True)) for m in modules if isinstance(m, dict) and m.get("id")}
    show_kpis = mod_map.get("kpis", True)
    show_verdict = mod_map.get("verdict", True)
    show_grid = mod_map.get("grid", True)

    players = [p for p in (item.get("players") or []) if isinstance(p, dict)]
    ranked = sorted(players, key=lambda x: float(x.get("ev_score") or 0), reverse=True)
    top1 = ranked[0] if ranked else {}
    prem = item.get("premium_benchmark") if isinstance(item.get("premium_benchmark"), dict) else (max(players, key=lambda x: float(x.get("price") or 0)) if players else {})
    avg_p = float(item.get("avg_price") or 6.8)
    avg_x = float(item.get("avg_xgi90") or 0.45)

    title = esc(str(item.get("title") or "رادار ارزش بازار و شکار نقل‌وانتقالات"))
    comp = esc(str(item.get("competition") or "لیگ برتر انگلیس"))
    season = esc(str(item.get("season") or "فصل جاری"))
    slice_lbl = esc(str(item.get("slice_label") or "بازیکنان هجومی"))
    src = esc(str(item.get("source") or "Opta FPL / XGPedia"))
    verdict = esc(str(item.get("editorial_verdict") or ""))

    pad_top = 139 if is9 else (24 if is16 else 22)
    pad_bot = 171 if is9 else (20 if is16 else 16)
    pad_x = 46 if is16 else 38

    slide_title = dict((s[0], s[1]) for s in VALUE_RADAR_SLIDES).get(slide, "رادار ارزش بازار")

    # بدنهٔ ۵ اسلاید
    if slide == "slide1":
        top3_cards = "".join(
            f'<div class="kpi-box">'
            f'<div class="fi gap10">{_club_crest(str(p.get("club_code") or ""), str(p.get("club") or ""), str(p.get("color") or accent2), 42)}'
            f'<div style="min-width:0"><div class="kpi-nm">{esc(p.get("name", ""))}</div>'
            f'<div class="kpi-sub">{esc(p.get("club", ""))} • £{_f1(p.get("price"))}M</div></div></div>'
            f'<div class="kpi-ev">+{_f1(p.get("ev_score"))}</div>'
            f'</div>'
            for p in ranked[:3]
        )
        kpi_row = f'<div class="kpi-grid">{top3_cards}</div>' if (show_kpis and ranked) else ""
        body_html = (
            f'<div class="card-panel flex1" style="padding:18px 20px">'
            f'<div class="sec-hdr"><span>نمودار پراکندگی ارزش در برابر قیمت (xGI/90 vs £M)</span><span class="badge-ev">برش: {slice_lbl}</span></div>'
            f'<div style="flex:1;min-height:0;display:flex;align-items:center">{_scatter_svg(players, avg_p, avg_x, 960 if not is16 else 1120, 580 if not is16 else 440)}</div>'
            f'</div>'
            f'{kpi_row}'
        )
    elif slide == "slide2":
        max_ev = max((float(p.get("ev_score") or 1.0) for p in ranked[:6]), default=12.0)
        rows_html = []
        for idx, p in enumerate(ranked[:6], 1):
            ev = float(p.get("ev_score") or 0.0)
            pct = min(100, max(18, round((ev / max(max_ev, 1.0)) * 100)))
            rows_html.append(
                f'<div class="lb-row">'
                f'<div class="lb-rank">#{fa(str(idx))}</div>'
                f'{_club_crest(str(p.get("club_code") or ""), str(p.get("club") or ""), str(p.get("color") or accent2), 48)}'
                f'<div style="flex:1;min-width:0">'
                f'<div class="lb-nm">{esc(p.get("name", ""))} <span class="pos-tag">{esc(p.get("pos_fa", ""))}</span></div>'
                f'<div class="lb-sub">{esc(p.get("club", ""))} • {fa(str(p.get("goals", 0)))} گل و {fa(str(p.get("assists", 0)))} پاس گل</div>'
                f'<div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:linear-gradient(90deg,{accent2},{accent})"></div></div>'
                f'</div>'
                f'<div class="lb-stat"><div class="lb-val">£{_f1(p.get("price"))}M</div><div class="lb-lbl">قیمت</div></div>'
                f'<div class="lb-stat"><div class="lb-val">{_f2(p.get("xgi90"))}</div><div class="lb-lbl">xGI/90</div></div>'
                f'<div class="lb-stat"><div class="lb-ev">+{_f1(ev)}</div><div class="lb-lbl">شاخص +EV</div></div>'
                f'</div>'
            )
        body_html = (
            f'<div class="card-panel flex1">'
            f'<div class="sec-hdr"><span>۶ شکار برتر بازار از نظر بازدهی به ازای هر میلیون پوند</span><span class="badge-ev">رتبه‌بندی زنده +EV</span></div>'
            f'<div class="fcol gap12 flex1" style="justify-content:center">{"".join(rows_html)}</div>'
            f'</div>'
        )
    elif slide == "slide3":
        save_m = max(0.0, float(prem.get("price") or 0) - float(top1.get("price") or 0))
        metrics = [
            ("قیمت بازار (£M)", f"£{float(top1.get('price') or 0):.1f}M", f"£{float(prem.get('price') or 0):.1f}M"),
            ("خروجی امید گل+پاس (xGI/90)", f"{float(top1.get('xgi90') or 0):.2f}", f"{float(prem.get('xgi90') or 0):.2f}"),
            ("شاخص ارزش (+EV)", f"+{float(top1.get('ev_score') or 0):.1f}", f"+{float(prem.get('ev_score') or 0):.1f}"),
            ("گل + پاس گل فصل", f"{int(top1.get('goals') or 0) + int(top1.get('assists') or 0)}", f"{int(prem.get('goals') or 0) + int(prem.get('assists') or 0)}"),
            ("درصد مالکیت", f"{float(top1.get('ownership') or 0):.1f}%", f"{float(prem.get('ownership') or 0):.1f}%"),
        ]
        m_rows = "".join(
            f'<div class="cmp-row">'
            f'<div class="cmp-v good">{fa(v1)}</div>'
            f'<div class="cmp-lbl">{lbl}</div>'
            f'<div class="cmp-v prem">{fa(v2)}</div>'
            f'</div>'
            for lbl, v1, v2 in metrics
        )
        body_html = (
            f'<div class="card-panel flex1">'
            f'<div class="sec-hdr"><span>دوئل ارزش بازار: شکار طلایی در برابر ستارهٔ گران‌قیمت</span><span class="badge-ev">صرفه‌جویی £{_f1(save_m)}M</span></div>'
            f'<div class="vs-head">'
            f'<div class="vs-side"><div class="vs-tag good-bg">شکار #۱ (+EV)</div>'
            f'{_club_crest(str(top1.get("club_code") or ""), str(top1.get("club") or ""), str(top1.get("color") or accent2), 74)}'
            f'<div class="vs-nm">{esc(top1.get("name", ""))}</div><div class="vs-cl">{esc(top1.get("club", ""))}</div></div>'
            f'<div class="vs-mid">VS</div>'
            f'<div class="vs-side"><div class="vs-tag prem-bg">معیار گران‌قیمت</div>'
            f'{_club_crest(str(prem.get("club_code") or ""), str(prem.get("club") or ""), str(prem.get("color") or accent), 74)}'
            f'<div class="vs-nm">{esc(prem.get("name", ""))}</div><div class="vs-cl">{esc(prem.get("club", ""))}</div></div>'
            f'</div>'
            f'<div class="fcol gap12 flex1" style="justify-content:center;margin-top:10px">{m_rows}</div>'
            f'</div>'
        )
    elif slide == "slide4":
        diffs = sorted([p for p in players if float(p.get("ownership") or 100) < 15.0], key=lambda x: float(x.get("ev_score") or 0), reverse=True)[:4]
        if not diffs:
            diffs = ranked[:4]
        deltas = sorted(players, key=lambda x: float(x.get("delta") or 0), reverse=True)[:4]
        d_html = "".join(
            f'<div class="mini-row">'
            f'{_club_crest(str(p.get("club_code") or ""), str(p.get("club") or ""), str(p.get("color") or accent2), 40)}'
            f'<div style="flex:1"><div class="mini-nm">{esc(p.get("name", ""))}</div><div class="mini-sub">{esc(p.get("club", ""))} • £{_f1(p.get("price"))}M</div></div>'
            f'<div class="mini-pill">{_f1(p.get("ownership"))}% مالکیت</div>'
            f'</div>'
            for p in diffs
        )
        f_html = "".join(
            f'<div class="mini-row">'
            f'{_club_crest(str(p.get("club_code") or ""), str(p.get("club") or ""), str(p.get("color") or accent), 40)}'
            f'<div style="flex:1"><div class="mini-nm">{esc(p.get("name", ""))}</div><div class="mini-sub">واقعی: {fa(str(int(p.get("goals") or 0)+int(p.get("assists") or 0)))} | xGI: {_f1(p.get("xgi"))}</div></div>'
            f'<div class="mini-pill" style="color:{("#34D399" if float(p.get("delta") or 0) >= 0 else "#F87171")}">{_fs1(p.get("delta"))}</div>'
            f'</div>'
            for p in deltas
        )
        body_html = (
            f'<div class="dual-grid flex1">'
            f'<div class="card-panel"><div class="sec-hdr"><span>جواهرهای کم‌مالکیت (Differentials)</span><span class="badge-ev">زیررادار</span></div>'
            f'<div class="fcol gap12 flex1" style="justify-content:center">{d_html}</div></div>'
            f'<div class="card-panel"><div class="sec-hdr"><span>بیش‌عملکردها نسبت به امید گل (G+A − xGI)</span><span class="badge-ev">دلتای گلزنی</span></div>'
            f'<div class="fcol gap12 flex1" style="justify-content:center">{f_html}</div></div>'
            f'</div>'
        )
    else:  # slide5: Scout Dossier #1
        stats6 = [
            ("شاخص ارزش (+EV)", f"+{float(top1.get('ev_score') or 0):.1f}"),
            ("قیمت بازار", f"£{float(top1.get('price') or 0):.1f}M"),
            ("امید گل+پاس / ۹۰", f"{float(top1.get('xgi90') or 0):.2f}"),
            ("امید گل / ۹۰", f"{float(top1.get('xg90') or 0):.2f}"),
            ("امید پاس گل / ۹۰", f"{float(top1.get('xa90') or 0):.2f}"),
            ("درصد مالکیت", f"{float(top1.get('ownership') or 0):.1f}%"),
        ]
        s_grid = "".join(
            f'<div class="dos-cell"><div class="dos-val">{fa(v)}</div><div class="dos-lbl">{k}</div></div>'
            for k, v in stats6
        )
        body_html = (
            f'<div class="card-panel flex1" style="justify-content:space-between">'
            f'<div class="sec-hdr"><span>پروندهٔ اسکاتینگ شکار برتر هفته (#1)</span><span class="badge-ev">{esc(top1.get("ev_tier", "شکار طلایی +EV"))}</span></div>'
            f'<div class="dos-hero">'
            f'{_club_crest(str(top1.get("club_code") or ""), str(top1.get("club") or ""), str(top1.get("color") or accent2), 112)}'
            f'<div><div class="dos-nm">{esc(top1.get("name", ""))}</div>'
            f'<div class="dos-sub">{esc(top1.get("club", ""))} • {esc(top1.get("pos_fa", ""))} • {fa(str(top1.get("minutes", 0)))} دقیقه بازی</div>'
            f'<div class="dos-ga">{fa(str(top1.get("goals", 0)))} گل و {fa(str(top1.get("assists", 0)))} پاس گل (مجموع xGI: {_f1(top1.get("xgi"))})</div></div>'
            f'</div>'
            f'<div class="dos-grid">{s_grid}</div>'
            f'</div>'
        )

    verdict_html = (
        f'<div class="verdict-bar"><span class="v-dot"></span><span>{verdict}</span></div>'
        if (show_verdict and verdict) else ""
    )

    grid_css = (
        "background-image:linear-gradient(rgba(255,255,255,.03) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.03) 1px,transparent 1px);background-size:48px 48px;"
        if show_grid else ""
    )

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8"/>
<style>
{build_embedded_font_css()}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:{w}px;height:{h}px;overflow:hidden;background:#0D1730;color:#F8FAFC;font-family:'Vazirmatn',sans-serif}}
.stage{{position:relative;width:{w}px;height:{h}px;background:#0D1730;overflow:hidden;display:flex;flex-direction:column;padding:{pad_top}px {pad_x}px {pad_bot}px {pad_x}px;gap:16px;{grid_css}}}
.glow{{position:absolute;inset:0;pointer-events:none;background:radial-gradient(circle at 86% 18%,rgba({r2}, {g2}, {b2}, .22),transparent 48%),radial-gradient(circle at 14% 84%,rgba({r1}, {g1}, {b1}, .22),transparent 48%)}}
.frame{{position:absolute;inset:12px;pointer-events:none;border:1px solid rgba(255,255,255,.08);border-radius:16px}}.crn{{position:absolute;width:28px;height:28px;pointer-events:none;z-index:5}}.c-tl{{top:14px;left:14px;border-top:3.5px solid #E62E45;border-left:3.5px solid #E62E45;border-top-left-radius:8px}}.c-tr{{top:14px;right:14px;border-top:3.5px solid #E62E45;border-right:3.5px solid #E62E45;border-top-right-radius:8px}}.c-bl{{bottom:14px;left:14px;border-bottom:3.5px solid #E62E45;border-left:3.5px solid #E62E45;border-bottom-left-radius:8px}}.c-br{{bottom:14px;right:14px;border-bottom:3.5px solid #E62E45;border-right:3.5px solid #E62E45;border-bottom-right-radius:8px}}
.z2{{position:relative;z-index:2}}
.hdr{{display:flex;align-items:center;justify-content:space-between;gap:16px}}
.hdr-r{{display:flex;flex-direction:column;gap:4px}}
.pill{{display:inline-flex;align-items:center;gap:8px;padding:6px 16px;border-radius:999px;background:rgba(15,23,42,.82);border:1px solid rgba({r2},{g2},{b2},.45);font-size:17px;font-weight:800;color:#E2E8F0;width:fit-content}}
.ttl{{font-size:{38 if not is16 else 34}px;font-weight:900;color:#fff;line-height:1.25}}
.sub{{font-size:20px;font-weight:600;color:#94A3B8}}
.flex1{{flex:1;min-height:0}}
.fcol{{display:flex;flex-direction:column}}
.fi{{display:flex;align-items:center}}
.gap10{{gap:10px}}.gap12{{gap:12px}}
.card-panel{{background:rgba(15,23,42,.74);border:1px solid rgba(255,255,255,.12);border-radius:22px;padding:22px 24px;display:flex;flex-direction:column;gap:14px}}
.sec-hdr{{display:flex;align-items:center;justify-content:space-between;font-size:23px;font-weight:900;color:#F8FAFC;border-bottom:1px solid rgba(255,255,255,.1);padding-bottom:10px}}
.badge-ev{{font-size:15px;font-weight:800;color:#34D399;background:rgba(16,185,129,.14);border:1px solid rgba(16,185,129,.4);padding:4px 12px;border-radius:999px}}
.kpi-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}}
.kpi-box{{background:rgba(15,23,42,.82);border:1px solid rgba(16,185,129,.35);border-radius:18px;padding:14px 16px;display:flex;align-items:center;justify-content:space-between;gap:10px}}
.kpi-nm{{font-size:22px;font-weight:900;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.kpi-sub{{font-size:16px;font-weight:700;color:#94A3B8}}
.kpi-ev{{font-family:'Space Grotesk','Vazirmatn',sans-serif;font-size:28px;font-weight:900;color:#34D399;flex-shrink:0}}
.lb-row{{display:flex;align-items:center;gap:14px;padding:12px 16px;border-radius:16px;background:rgba(13,23,48,.76);border:1px solid rgba(255,255,255,.09)}}
.lb-rank{{font-family:'Space Grotesk',sans-serif;font-size:22px;font-weight:900;color:#34D399;width:40px;text-align:center}}
.lb-nm{{font-size:21px;font-weight:900;color:#fff;display:flex;align-items:center;gap:8px}}
.pos-tag{{font-size:13px;font-weight:800;color:#CBD5E1;background:rgba(255,255,255,.1);padding:2px 8px;border-radius:6px}}
.lb-sub{{font-size:15px;font-weight:600;color:#94A3B8;margin-top:2px}}
.bar-track{{height:7px;border-radius:99px;background:rgba(255,255,255,.08);margin-top:6px;overflow:hidden}}
.bar-fill{{height:100%;border-radius:99px}}
.lb-stat{{text-align:center;min-width:86px}}
.lb-val{{font-family:'Space Grotesk','Vazirmatn',sans-serif;font-size:21px;font-weight:900;color:#F8FAFC}}
.lb-ev{{font-family:'Space Grotesk','Vazirmatn',sans-serif;font-size:23px;font-weight:900;color:#34D399}}
.lb-lbl{{font-size:13px;font-weight:700;color:#94A3B8}}
.vs-head{{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:16px;padding:10px 0}}
.vs-side{{display:flex;flex-direction:column;align-items:center;gap:8px;text-align:center}}
.vs-tag{{font-size:14px;font-weight:900;padding:4px 12px;border-radius:999px}}
.good-bg{{background:rgba(16,185,129,.2);color:#34D399;border:1px solid rgba(16,185,129,.45)}}
.prem-bg{{background:rgba(230,46,69,.2);color:#FB7185;border:1px solid rgba(230,46,69,.45)}}
.vs-nm{{font-size:25px;font-weight:900;color:#fff}}
.vs-cl{{font-size:16px;font-weight:700;color:#94A3B8}}
.vs-mid{{width:58px;height:58px;border-radius:16px;background:linear-gradient(135deg,{accent},{accent2});display:flex;align-items:center;justify-content:center;font-family:'Space Grotesk',sans-serif;font-size:22px;font-weight:900;color:#fff}}
.cmp-row{{display:grid;grid-template-columns:1fr 1.4fr 1fr;align-items:center;padding:14px 18px;border-radius:14px;background:rgba(13,23,48,.78);border:1px solid rgba(255,255,255,.08)}}
.cmp-v{{font-family:'Space Grotesk','Vazirmatn',sans-serif;font-size:24px;font-weight:900;text-align:center}}
.cmp-v.good{{color:#34D399}}.cmp-v.prem{{color:#F8FAFC}}
.cmp-lbl{{text-align:center;font-size:18px;font-weight:800;color:#CBD5E1}}
.dual-grid{{display:grid;grid-template-columns:{("1fr 1fr" if is16 else "1fr")};gap:16px}}
.mini-row{{display:flex;align-items:center;gap:12px;padding:10px 14px;border-radius:14px;background:rgba(13,23,48,.76);border:1px solid rgba(255,255,255,.08)}}
.mini-nm{{font-size:19px;font-weight:900;color:#fff}}
.mini-sub{{font-size:14px;font-weight:600;color:#94A3B8}}
.mini-pill{{font-size:16px;font-weight:900;color:#38BDF8;background:rgba(56,189,248,.12);padding:5px 12px;border-radius:999px;white-space:nowrap}}
.dos-hero{{display:flex;align-items:center;gap:24px;padding:18px 22px;border-radius:20px;background:linear-gradient(135deg,rgba(16,185,129,.16),rgba(15,23,42,.85));border:1px solid rgba(16,185,129,.35)}}
.dos-nm{{font-size:36px;font-weight:900;color:#fff}}
.dos-sub{{font-size:19px;font-weight:700;color:#CBD5E1;margin-top:4px}}
.dos-ga{{font-size:18px;font-weight:800;color:#34D399;margin-top:6px}}
.dos-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}}
.dos-cell{{background:rgba(13,23,48,.82);border:1px solid rgba(255,255,255,.1);border-radius:18px;padding:20px 14px;text-align:center}}
.dos-val{{font-family:'Space Grotesk','Vazirmatn',sans-serif;font-size:32px;font-weight:900;color:#34D399}}
.dos-lbl{{font-size:16px;font-weight:700;color:#CBD5E1;margin-top:6px}}
.verdict-bar{{display:flex;align-items:center;gap:12px;padding:14px 20px;border-radius:16px;background:rgba(15,23,42,.85);border:1px solid rgba({r2},{g2},{b2},.38);font-size:20px;font-weight:700;color:#E2E8F0;line-height:1.55}}
.v-dot{{width:10px;height:10px;border-radius:99px;background:{accent2};flex-shrink:0;box-shadow:0 0 12px {accent2}}}
.ftr{{display:flex;align-items:center;justify-content:space-between;border-top:1px solid rgba(255,255,255,.12);padding-top:10px;font-size:18px;font-weight:700;color:#94A3B8;white-space:nowrap!important}}
.ftr-l{{font-family:'Space Grotesk',sans-serif;color:#E2E8F0;white-space:nowrap!important}}
</style>
</head>
<body>
<div class="stage">
  <div class="glow"></div>
  <div class="frame"></div>
  <div class="crn c-tl"></div><div class="crn c-tr"></div><div class="crn c-bl"></div><div class="crn c-br"></div>
  <div class="hdr z2">
    <div class="hdr-r">
      <div class="pill"><span style="width:9px;height:9px;border-radius:99px;background:{accent2}"></span><span>رادار ارزش بازار • {comp}</span></div>
      <div class="ttl">{title}</div>
      <div class="sub">{slide_title} • {season}</div>
    </div>
    {_brand_logo_img(46)}
  </div>
  <div class="fcol gap12 flex1 z2">
    {body_html}
    {verdict_html}
  </div>
  <div class="ftr z2">
    <span>{comp} • رادار ارزش بازار (+EV)</span>
    <span class="ftr-l" dir="ltr">@XGPedia | {src}</span>
  </div>
</div>
</body>
</html>"""
