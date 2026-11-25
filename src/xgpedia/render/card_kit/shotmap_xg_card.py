"""کارت اسلایدی و ماژولار «نقشهٔ شوت و مومنتوم امید گل» (`Shot-Map & xG Timeline Studio — v0.38.0`).

۵ اسلاید استاندارد + ۶ ماژول کاملاً مستقل و قابل جداسازی/ترکیب:
  - `slide1`: نقشهٔ شوت + خط زمانی مومنتوم xG (`pitch_shotmap`, `xg_timeline`, `xg_summary`)
  - `slide2`: تمرکز روی نقشهٔ شوت و کیفیت موقعیت‌ها (`pitch_shotmap`, `xg_summary`, `editorial_verdict`)
  - `slide3`: مومنتوم امید گل و بزرگ‌ترین موقعیت‌ها (`xg_timeline`, `big_chances`, `editorial_verdict`)
  - `slide4`: آزمایشگاه مناطق شوت‌زنی و کارایی (`shot_zones`, `xg_summary`, `editorial_verdict`)
  - `slide5`: پروندهٔ کامل تحلیلی (`pitch_shotmap`, `big_chances`, `editorial_verdict`)

استانداردهای دائمی XGPedia:
  - ۱۰۰٪ آفلاین (فونت محلی Vazirmatn + JetBrains Mono + Space Grotesk، بدون CDN)
  - پالت Midnight Navy `#0D1730` + Signature Crimson `#E62E45` + Gold `#FBBF24`
  - فریم چهارگوشه قرمز یکپارچه (`pad_top=24/22/139`, `pad_bot=20/16/171`)
  - لوگوی واقعی باشگاه‌های انگلیس (`pl_badges_free`) و فوتر اکیداً تک‌خطی (`white-space:nowrap!important`)
  - رعایت اکید `null ≠ 0`.
"""
from __future__ import annotations

import math
from typing import Any

from src.xgpedia.providers.pl_badges_free import resolve_distinct_team_colors
from src.xgpedia.render.card_kit.helpers import ensure_dark_bg_contrast, esc, f2, fa
from src.xgpedia.render.cards import _brand_logo_data_uri
from src.xgpedia.render.studio_engine import build_embedded_font_css

SHOTMAP_FORMATS: dict[str, tuple[int, int]] = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}

# (slide_id, label_fa, subtitle_fa, default_module_ids)
SHOTMAP_SLIDES: list[tuple[str, str, str, list[str]]] = [
    ("slide1", "اسلاید ۱: نقشهٔ شوت + مومنتوم xG", "نقشهٔ شوت و xG", ["pitch_shotmap", "xg_timeline", "xg_summary"]),
    ("slide2", "اسلاید ۲: نقشهٔ شوت و آمار کیفیت", "نقشهٔ شوت", ["pitch_shotmap", "xg_summary", "editorial_verdict"]),
    ("slide3", "اسلاید ۳: مومنتوم xG و موقعیت‌های بزرگ", "مومنتوم امید گل", ["xg_timeline", "big_chances", "editorial_verdict"]),
    ("slide4", "اسلاید ۴: مناطق شوت‌زنی و کارایی", "مناطق شوت", ["shot_zones", "xg_summary", "editorial_verdict"]),
    ("slide5", "اسلاید ۵: پروندهٔ کامل تحلیلی", "تحلیل کامل شوت", ["pitch_shotmap", "big_chances", "editorial_verdict"]),
]


def _crest_html(team: dict[str, Any], size: int = 56) -> str:
    from src.xgpedia.providers.pl_badges_free import get_pl_badge_data_uri
    nm = str(team.get("name") or "")
    cd = str(team.get("code") or "FC")[:3].upper()
    uri = team.get("logoUrl") or get_pl_badge_data_uri(nm, tla_hint=cd, fetch_network=False)
    if uri:
        return (
            f'<div class="fc" style="width:{size}px;height:{size}px;flex-shrink:0;border-radius:50%;'
            f'background:rgba(7,13,29,.78);padding:{max(4, size // 11)}px;border:1.5px solid rgba(255,255,255,.18)">'
            f'<img src="{esc(uri)}" alt="{esc(cd)}" style="width:100%;height:100%;object-fit:contain;display:block"/></div>'
        )
    col = ensure_dark_bg_contrast(str(team.get("color") or "#E62E45"), min_ratio=4.2)
    return (
        f'<div class="fc fm" style="width:{size}px;height:{size}px;flex-shrink:0;border-radius:14px;'
        f'background:{col}28;border:2px solid {col}88;color:#fff;font-weight:900;font-size:{max(14, size // 3)}px">'
        f'{esc(cd)}</div>'
    )


def _team_colors(item: dict[str, Any]) -> tuple[str, str]:
    h = item.get("home") or {}
    a = item.get("away") or {}
    hc, ac = resolve_distinct_team_colors(str(h.get("color") or "#E62E45"), str(a.get("color") or "#38BDF8"))
    return ensure_dark_bg_contrast(hc, min_ratio=4.3), ensure_dark_bg_contrast(ac, min_ratio=4.3)


def get_shotmap_xg_modules(item: dict[str, Any], slide: str = "slide1") -> tuple[list[dict[str, Any]], list[str]]:
    shots = item.get("shots") or []
    h, a = item.get("home") or {}, item.get("away") or {}
    has_shots = len(shots) >= 2
    has_xg = (h.get("xg") is not None and a.get("xg") is not None) or has_shots
    has_verdict = bool(str(item.get("editorialVerdict") or "").strip())

    def_set = set(next((mids for sid, _, _, mids in SHOTMAP_SLIDES if sid == slide), SHOTMAP_SLIDES[0][3]))
    specs = [
        ("pitch_shotmap", "نقشهٔ شوت روی زمین فوتبال (Pitch Shot-Map)", has_shots),
        ("xg_timeline", "نمودار پلکانی مومنتوم امید گل (xG Race)", has_shots or has_xg),
        ("xg_summary", "نوار آمار کیفیت شوت و امید گل (xG Summary)", has_xg),
        ("big_chances", "فهرست بزرگ‌ترین موقعیت‌های بازی (Big Chances)", has_shots),
        ("shot_zones", "تفکیک مناطق شوت‌زنی (شش‌قدم / محوطه / بیرون)", has_shots),
        ("editorial_verdict", "جمع‌بندی تحریریه XGPedia", has_verdict),
    ]
    mods: list[dict[str, Any]] = []
    missing: list[str] = []
    for mid, title_fa, ok in specs:
        if ok:
            mods.append({"id": mid, "title_fa": title_fa, "enabled": mid in def_set, "can_half": False, "span": "full", "half": False})
        else:
            missing.append(title_fa)
    if mods and not any(m["enabled"] for m in mods):
        mods[0]["enabled"] = True
    return mods, missing


# ---------------------------------------------------------------------------
# ۶ ماژول مستقل و قابل جداسازی (Independent Extractable Module Renderers)
# ---------------------------------------------------------------------------

def render_mod_pitch_shotmap(item: dict[str, Any]) -> str:
    shots = item.get("shots") or []
    if not shots:
        return ""
    hc, ac = _team_colors(item)
    h, a = item.get("home") or {}, item.get("away") or {}
    w_s, h_s = 920.0, 440.0
    pad_x, pad_y = 26.0, 20.0
    pw, ph = w_s - 2 * pad_x, h_s - 2 * pad_y

    # شوت‌های میزبان روی دروازه راست (x اصلی 0..1)، شوت‌های میهمان روی دروازه چپ (1 - x)
    markers = []
    for sh in sorted(shots, key=lambda s: float(s.get("xg") or 0.0)):
        is_h = sh.get("team") == "h"
        col = hc if is_h else ac
        raw_x = max(0.02, min(0.99, float(sh.get("x") or 0.8)))
        raw_y = max(0.02, min(0.98, float(sh.get("y") or 0.5)))
        px = pad_x + (raw_x if is_h else (1.0 - raw_x)) * pw
        py = pad_y + raw_y * ph
        xg = max(0.02, float(sh.get("xg") or 0.05))
        rad = max(6.5, min(25.0, 4.5 + math.sqrt(xg) * 23.0))
        res = str(sh.get("result") or "")
        is_goal = res == "Goal"
        is_pen = str(sh.get("situation") or "") == "Penalty"
        is_on = res in ("SavedShot", "ShotOnPost")

        if is_goal:
            markers.append(
                f'<g><circle cx="{px:.1f}" cy="{py:.1f}" r="{rad + 6:.1f}" fill="{col}" fill-opacity=".28"/>'
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{rad:.1f}" fill="{col}" stroke="#FFFFFF" stroke-width="3"/>'
                f'<text x="{px:.1f}" y="{py + 4.5:.1f}" text-anchor="middle" fill="#FFFFFF" font-family="Space Grotesk,sans-serif" font-weight="900" font-size="{11 if is_pen else 12}">{"P" if is_pen else "★"}</text></g>'
            )
        elif is_on:
            markers.append(
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{rad:.1f}" fill="{col}" fill-opacity=".52" stroke="#F8FAFC" stroke-width="1.8"/>'
            )
        else:
            markers.append(
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{rad:.1f}" fill="{col}" fill-opacity=".18" stroke="{col}" stroke-opacity=".88" stroke-width="2" stroke-dasharray="3 2"/>'
            )

    cx, cy = w_s / 2.0, h_s / 2.0
    box_w, box_h = pw * 0.165, ph * 0.62
    six_w, six_h = pw * 0.055, ph * 0.28
    leg = (
        '<div class="sm-leg">'
        f'<span><i style="background:{hc};border:2px solid #fff"></i>{esc(h.get("name", ""))}</span>'
        f'<span><i style="background:{ac};border:2px solid #fff"></i>{esc(a.get("name", ""))}</span>'
        '<span>★ گل</span><span>P پنالتی</span><span>○ ازدست‌رفته</span></div>'
    )
    return (
        '<div class="xm" style="padding:14px 18px">'
        '<div class="mh"><div class="fi gap10"><span class="mh-bar" style="background:#E62E45"></span>'
        '<h3 class="mt">نقشهٔ شوت‌ها (اندازه دایره = مقدار xG)</h3></div>'
        f'{leg}</div>'
        f'<div class="fc" dir="ltr"><svg style="width:100%;height:auto;display:block" viewBox="0 0 {int(w_s)} {int(h_s)}" fill="none">'
        f'<rect x="{pad_x}" y="{pad_y}" width="{pw}" height="{ph}" rx="12" fill="#071326" stroke="#F8FAFC" stroke-opacity=".28" stroke-width="2"/>'
        f'<line x1="{cx:.1f}" y1="{pad_y}" x2="{cx:.1f}" y2="{pad_y + ph}" stroke="#F8FAFC" stroke-opacity=".20" stroke-width="1.8"/>'
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="54" stroke="#F8FAFC" stroke-opacity=".20" stroke-width="1.8"/>'
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3.5" fill="#F8FAFC" fill-opacity=".4"/>'
        # Left penalty box (Away attacks left goal)
        f'<rect x="{pad_x}" y="{cy - box_h/2:.1f}" width="{box_w:.1f}" height="{box_h:.1f}" stroke="#F8FAFC" stroke-opacity=".24" stroke-width="1.8"/>'
        f'<rect x="{pad_x}" y="{cy - six_h/2:.1f}" width="{six_w:.1f}" height="{six_h:.1f}" stroke="#F8FAFC" stroke-opacity=".22" stroke-width="1.5"/>'
        # Right penalty box (Home attacks right goal)
        f'<rect x="{pad_x + pw - box_w:.1f}" y="{cy - box_h/2:.1f}" width="{box_w:.1f}" height="{box_h:.1f}" stroke="#F8FAFC" stroke-opacity=".24" stroke-width="1.8"/>'
        f'<rect x="{pad_x + pw - six_w:.1f}" y="{cy - six_h/2:.1f}" width="{six_w:.1f}" height="{six_h:.1f}" stroke="#F8FAFC" stroke-opacity=".22" stroke-width="1.5"/>'
        # Attack direction labels
        f'<text x="{pad_x + 14:.0f}" y="{pad_y + 22:.0f}" fill="{ac}" font-family="Vazirmatn" font-weight="900" font-size="14">← حملات {esc(a.get("name", ""))}</text>'
        f'<text x="{pad_x + pw - 14:.0f}" y="{pad_y + 22:.0f}" text-anchor="end" fill="{hc}" font-family="Vazirmatn" font-weight="900" font-size="14">حملات {esc(h.get("name", ""))} →</text>'
        f'{"".join(markers)}</svg></div></div>'
    )


def render_mod_xg_timeline(item: dict[str, Any]) -> str:
    shots = item.get("shots") or []
    h, a = item.get("home") or {}, item.get("away") or {}
    if not shots and (h.get("xg") is None or a.get("xg") is None):
        return ""
    hc, ac = _team_colors(item)

    def _build_series(team_k: str, fallback_xg: float) -> list[tuple[int, float, bool]]:
        ts = sorted([s for s in shots if s.get("team") == team_k], key=lambda x: int(x.get("min") or 0))
        if not ts:
            return [(0, 0.0, False), (45, round(fallback_xg * 0.45, 2), False), (93, fallback_xg, False)]
        cur = 0.0
        pts = [(0, 0.0, False)]
        for s in ts:
            cur = round(cur + float(s.get("xg") or 0.0), 3)
            pts.append((min(95, max(1, int(s.get("min") or 45))), cur, s.get("result") == "Goal"))
        pts.append((95, cur, False))
        return pts

    sh = _build_series("h", float(h.get("xg") or 0.0))
    sa = _build_series("a", float(a.get("xg") or 0.0))
    h_tot = sh[-1][1]
    a_tot = sa[-1][1]
    ymax = max(h_tot, a_tot, 1.5) * 1.18

    w_s, h_s = 920.0, 210.0
    pl, pr, pt, pb = 48.0, 88.0, 22.0, 30.0
    pw, ph = w_s - pl - pr, h_s - pt - pb
    vx = lambda mn: pl + (min(95, mn) / 95.0) * pw
    vy = lambda v: pt + ph - (v / ymax) * ph

    def _step(ser: list[tuple[int, float, bool]]) -> str:
        d = f"M{vx(ser[0][0]):.1f} {vy(ser[0][1]):.1f}"
        for i in range(1, len(ser)):
            x = vx(ser[i][0])
            d += f" L{x:.1f} {vy(ser[i - 1][1]):.1f} L{x:.1f} {vy(ser[i][1]):.1f}"
        return d

    dh, da = _step(sh), _step(sa)
    fh = f"{dh} L{vx(95):.1f} {pt + ph:.1f} L{pl:.1f} {pt + ph:.1f} Z"
    fa_p = f"{da} L{vx(95):.1f} {pt + ph:.1f} L{pl:.1f} {pt + ph:.1f} Z"

    def _goal_pins(ser: list[tuple[int, float, bool]], col: str) -> str:
        return "".join(
            f'<g><circle cx="{vx(t):.1f}" cy="{vy(v):.1f}" r="9" fill="{col}" fill-opacity=".3"/>'
            f'<circle cx="{vx(t):.1f}" cy="{vy(v):.1f}" r="5.5" fill="{col}" stroke="#fff" stroke-width="2.2"/>'
            f'<text x="{vx(t):.1f}" y="{max(14.0, vy(v) - 11):.1f}" text-anchor="middle" fill="#fff" font-family="Vazirmatn" font-weight="900" font-size="13">{fa(t)}\'</text></g>'
            for t, v, is_g in ser if is_g
        )

    yh_e, ya_e = vy(h_tot), vy(a_tot)
    sep = (-10 if yh_e <= ya_e else 10) if abs(yh_e - ya_e) < 22 else 0

    return (
        '<div class="xm" style="padding:14px 18px">'
        '<div class="mh"><div class="fi gap10"><span class="mh-bar" style="background:#38BDF8"></span>'
        '<h3 class="mt">مومنتوم تجمعی امید گل (۰\' تا ۹۰\'+)</h3></div>'
        f'<div class="fi gap14" style="font-size:16.5px;font-weight:900">'
        f'<span style="color:{hc}">{esc(h.get("name", ""))} {fa(f2(h_tot))}</span>'
        f'<span style="color:{ac}">{esc(a.get("name", ""))} {fa(f2(a_tot))}</span></div></div>'
        f'<div class="fc" dir="ltr"><svg style="width:100%;height:auto;display:block" viewBox="0 0 {int(w_s)} {int(h_s)}" fill="none">'
        f'<defs><linearGradient id="smH" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{hc}" stop-opacity=".34"/><stop offset="1" stop-color="{hc}" stop-opacity="0"/></linearGradient>'
        f'<linearGradient id="smA" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{ac}" stop-opacity=".30"/><stop offset="1" stop-color="{ac}" stop-opacity="0"/></linearGradient></defs>'
        f'<g stroke="#ffffff18" stroke-dasharray="4 4"><line x1="{pl}" y1="{pt}" x2="{pl+pw}" y2="{pt}"/>'
        f'<line x1="{pl}" y1="{pt+ph/2:.1f}" x2="{pl+pw}" y2="{pt+ph/2:.1f}"/>'
        f'<line x1="{vx(45):.1f}" y1="{pt}" x2="{vx(45):.1f}" y2="{pt+ph}" stroke="#ffffff30"/></g>'
        f'<line x1="{pl}" y1="{pt+ph}" x2="{pl+pw}" y2="{pt+ph}" stroke="#ffffff38"/>'
        f'<text x="{pl-10:.0f}" y="{pt+5:.0f}" text-anchor="end" fill="#94A3B8" font-family="JetBrains Mono" font-size="13" font-weight="700">{ymax:.1f}</text>'
        f'<text x="{pl-10:.0f}" y="{pt+ph/2+5:.1f}" text-anchor="end" fill="#94A3B8" font-family="JetBrains Mono" font-size="13" font-weight="700">{ymax/2:.1f}</text>'
        f'<text x="{pl-10:.0f}" y="{pt+ph+4:.0f}" text-anchor="end" fill="#94A3B8" font-family="JetBrains Mono" font-size="13" font-weight="700">0</text>'
        f'<text x="{pl:.0f}" y="{h_s-6:.0f}" text-anchor="middle" fill="#CBD5E1" font-family="JetBrains Mono" font-size="13" font-weight="800">0\'</text>'
        f'<text x="{vx(45):.1f}" y="{h_s-6:.0f}" text-anchor="middle" fill="#F8FAFC" font-family="JetBrains Mono" font-size="13" font-weight="800">HT 45\'</text>'
        f'<text x="{pl+pw:.0f}" y="{h_s-6:.0f}" text-anchor="middle" fill="#CBD5E1" font-family="JetBrains Mono" font-size="13" font-weight="800">90\'+</text>'
        f'<path d="{fa_p}" fill="url(#smA)"/><path d="{fh}" fill="url(#smH)"/>'
        f'<path d="{da}" stroke="{ac}" stroke-width="3.2" fill="none" stroke-linejoin="round"/>'
        f'<path d="{dh}" stroke="{hc}" stroke-width="3.6" fill="none" stroke-linejoin="round"/>'
        f'<rect x="{pl+pw+10:.0f}" y="{yh_e+sep-12:.1f}" width="72" height="24" rx="7" fill="#070E20" stroke="{hc}" stroke-width="1.5"/>'
        f'<text x="{pl+pw+46:.0f}" y="{yh_e+sep+5:.1f}" text-anchor="middle" fill="{hc}" font-family="JetBrains Mono" font-weight="900" font-size="15">{h_tot:.2f}</text>'
        f'<rect x="{pl+pw+10:.0f}" y="{ya_e-sep-12:.1f}" width="72" height="24" rx="7" fill="#070E20" stroke="{ac}" stroke-width="1.5"/>'
        f'<text x="{pl+pw+46:.0f}" y="{ya_e-sep+5:.1f}" text-anchor="middle" fill="{ac}" font-family="JetBrains Mono" font-weight="900" font-size="15">{a_tot:.2f}</text>'
        f'{_goal_pins(sa, ac)}{_goal_pins(sh, hc)}</svg></div></div>'
    )


def render_mod_xg_summary(item: dict[str, Any]) -> str:
    shots = item.get("shots") or []
    h, a = item.get("home") or {}, item.get("away") or {}
    hc, ac = _team_colors(item)
    hs = [s for s in shots if s.get("team") == "h"]
    as_ = [s for s in shots if s.get("team") == "a"]

    h_xg = float(h.get("xg")) if h.get("xg") is not None else round(sum(float(s["xg"]) for s in hs), 2)
    a_xg = float(a.get("xg")) if a.get("xg") is not None else round(sum(float(s["xg"]) for s in as_), 2)
    h_np = h.get("npxg") if h.get("npxg") is not None else (round(sum(float(s["xg"]) for s in hs if s.get("situation") != "Penalty"), 2) if hs else None)
    a_np = a.get("npxg") if a.get("npxg") is not None else (round(sum(float(s["xg"]) for s in as_ if s.get("situation") != "Penalty"), 2) if as_ else None)
    h_bc = sum(1 for s in hs if float(s.get("xg") or 0) >= 0.30) if shots else None
    a_bc = sum(1 for s in as_ if float(s.get("xg") or 0) >= 0.30) if shots else None

    rows: list[tuple[str, str, str, float, float]] = [
        ("امید گل کل (xG)", fa(f2(h_xg)), fa(f2(a_xg)), h_xg, a_xg),
    ]
    if h_np is not None and a_np is not None:
        rows.append(("امید گل بدون پنالتی (npxG)", fa(f2(h_np)), fa(f2(a_np)), float(h_np), float(a_np)))
    if shots:
        rows.append(("تعداد شوت", fa(len(hs)), fa(len(as_)), float(len(hs)), float(len(as_))))
        rows.append(("موقعیت بزرگ (xG ≥ 0.30)", fa(h_bc), fa(a_bc), float(h_bc or 0), float(a_bc or 0)))

    html_rows = []
    for lbl, sv1, sv2, v1, v2 in rows:
        mx = max(v1, v2, 0.01)
        html_rows.append(
            '<div class="fcol gap6">'
            f'<div class="m-top"><span style="color:{hc};text-align:right">{sv1}</span>'
            f'<span style="color:#E2E8F0;font-size:17px;font-weight:800;text-align:center">{lbl}</span>'
            f'<span style="color:{ac};text-align:left">{sv2}</span></div>'
            '<div class="m-bars">'
            f'<div class="ct hs"><div class="ch" style="width:{v1 / mx * 100:.1f}%;background:{hc}"></div></div>'
            f'<div class="ct as"><div class="ca" style="width:{v2 / mx * 100:.1f}%;background:{ac}"></div></div>'
            '</div></div>'
        )
    return (
        '<div class="xe" style="gap:10px">'
        '<div class="mh" style="margin-bottom:4px"><div class="fi gap10"><span class="mh-bar" style="background:#FBBF24"></span>'
        '<h3 class="mt" style="font-size:22px">مقایسهٔ کیفیت موقعیت‌ها</h3></div></div>'
        f'<div class="fcol gap10">{"".join(html_rows)}</div></div>'
    )


def render_mod_big_chances(item: dict[str, Any]) -> str:
    shots = item.get("shots") or []
    if not shots:
        return ""
    hc, ac = _team_colors(item)
    h, a = item.get("home") or {}, item.get("away") or {}
    top_ch = sorted(shots, key=lambda s: float(s.get("xg") or 0.0), reverse=True)[:5]
    res_map = {"Goal": ("⚽ گل", "#34D399"), "SavedShot": ("🧤 مهار شد", "#38BDF8"), "ShotOnPost": ("💥 تیرک دروازه", "#FBBF24"), "MissedShots": ("✖ بیرون رفت", "#FB7185"), "BlockedShot": ("🛡 بلاک شد", "#94A3B8")}
    rows = []
    for s in top_ch:
        is_h = s.get("team") == "h"
        col = hc if is_h else ac
        t_nm = str((h if is_h else a).get("name") or "")
        r_lbl, r_col = res_map.get(str(s.get("result") or ""), ("شوت", "#CBD5E1"))
        pen_t = " • پنالتی" if s.get("situation") == "Penalty" else ""
        rows.append(
            f'<div class="bc-row" style="border-right:4px solid {col}">'
            f'<span class="bc-min fm">{fa(s.get("min", 0))}\'</span>'
            f'<div class="min0 flex1"><div class="bc-pl trunc">{esc(s.get("player", ""))} <span style="font-size:15px;color:#94A3B8">({esc(t_nm)}{pen_t})</span></div></div>'
            f'<span class="bc-res" style="color:{r_col};border-color:{r_col}55;background:{r_col}1c">{r_lbl}</span>'
            f'<span class="bc-xg fm" style="color:{col}">{fa(f2(float(s.get("xg") or 0)))} xG</span></div>'
        )
    return (
        '<div class="xm" style="flex:1">'
        '<div class="mh"><div class="fi gap10"><span class="mh-bar" style="background:#FBBF24"></span>'
        '<h3 class="mt">بزرگ‌ترین موقعیت‌های مسابقه</h3></div>'
        '<span class="mh-tag">بر اساس xG</span></div>'
        f'<div class="fcol gap8 flex1 justify-center">{"".join(rows)}</div></div>'
    )


def render_mod_shot_zones(item: dict[str, Any]) -> str:
    shots = item.get("shots") or []
    if not shots:
        return ""
    hc, ac = _team_colors(item)
    def _zone(s: dict[str, Any]) -> str:
        x = float(s.get("x") or 0.8)
        y = float(s.get("y") or 0.5)
        if x >= 0.94 and 0.36 <= y <= 0.64:
            return "six"
        if x >= 0.83 and 0.21 <= y <= 0.79:
            return "box"
        return "out"

    counts = {"h": {"six": 0, "box": 0, "out": 0}, "a": {"six": 0, "box": 0, "out": 0}}
    for s in shots:
        tk = "h" if s.get("team") == "h" else "a"
        counts[tk][_zone(s)] += 1

    zdefs = [("six", "محوطه شش‌قدم (خطرناک‌ترین)"), ("box", "داخل محوطه جریمه"), ("out", "شوت از بیرون محوطه")]
    rows = []
    for zk, zlbl in zdefs:
        v1, v2 = counts["h"][zk], counts["a"][zk]
        mx = max(v1, v2, 1)
        rows.append(
            '<div class="fcol gap6">'
            f'<div class="m-top"><span style="color:{hc};text-align:right">{fa(v1)} شوت</span>'
            f'<span style="color:#E2E8F0;font-size:17.5px;font-weight:800;text-align:center">{zlbl}</span>'
            f'<span style="color:{ac};text-align:left">{fa(v2)} شوت</span></div>'
            '<div class="m-bars">'
            f'<div class="ct hs"><div class="ch" style="width:{v1 / mx * 100:.1f}%;background:{hc}"></div></div>'
            f'<div class="ct as"><div class="ca" style="width:{v2 / mx * 100:.1f}%;background:{ac}"></div></div>'
            '</div></div>'
        )
    return (
        '<div class="xm" style="flex:1">'
        '<div class="mh"><div class="fi gap10"><span class="mh-bar" style="background:#34D399"></span>'
        '<h3 class="mt">تفکیک مناطق شوت‌زنی</h3></div></div>'
        f'<div class="fcol gap14 flex1 justify-center">{"".join(rows)}</div></div>'
    )


def render_mod_editorial_verdict(item: dict[str, Any]) -> str:
    txt = str(item.get("editorialVerdict") or "").strip()
    if not txt:
        return ""
    return (
        '<div class="xe verd-box">'
        '<div style="font-size:19px;font-weight:900;color:#FCD34D">✦ جمع‌بندی تحریریه XGPedia</div>'
        f'<p class="verd-txt">{fa(esc(txt))}</p></div>'
    )


def render_shotmap_xg_html(
    item: dict[str, Any],
    *,
    slide: str = "slide1",
    header_mode: str = "full",
    fmt: str = "4:5",
    theme: str = "classic",
    modules: list[dict[str, Any]] | None = None,
) -> str:
    """رندر ۱۰۰٪ آفلاین کارت اسلایدی و ماژولار «نقشهٔ شوت و مومنتوم امید گل»."""
    w, h_px = SHOTMAP_FORMATS.get(fmt, (1080, 1350))
    is_story = fmt == "9:16"
    is_wide = fmt == "16:9"
    pad_top, pad_bot = (139, 171) if is_story else ((22, 16) if is_wide else (24, 20))

    if modules is None:
        modules, _ = get_shotmap_xg_modules(item, slide)
    active = [m for m in modules if m.get("enabled")]

    render_map = {
        "pitch_shotmap": render_mod_pitch_shotmap,
        "xg_timeline": render_mod_xg_timeline,
        "xg_summary": render_mod_xg_summary,
        "big_chances": render_mod_big_chances,
        "shot_zones": render_mod_shot_zones,
        "editorial_verdict": render_mod_editorial_verdict,
    }
    blocks = []
    for m in active:
        fn = render_map.get(str(m.get("id") or ""))
        if fn:
            hb = fn(item)
            if hb:
                blocks.append(hb)

    h, a = item.get("home") or {}, item.get("away") or {}
    hc, ac = _team_colors(item)
    acc = "#FBBF24" if theme == "gold" else ("#10B981" if theme == "pitch" else "#E62E45")
    bg_hex = "#071122" if theme == "pitch" else "#0D1730"
    logo_uri = _brand_logo_data_uri()
    logo_html = (
        f'<img src="{logo_uri}" alt="XGPedia" style="height:44px;width:auto;display:block;flex-shrink:0"/>'
        if logo_uri
        else '<span class="fd" style="font-size:28px;font-weight:900"><span style="color:#E62E45">XG</span><span>Pedia</span></span>'
    )
    sl_lbl = next((sub for sid, _, sub, _ in SHOTMAP_SLIDES if sid == slide), "نقشهٔ شوت و xG")
    comp_txt = esc(item.get("competition") or "فوتبال اروپا")
    rnd_txt = fa(esc(item.get("round") or ""))
    src_txt = esc(item.get("source") or "Understat / XGPedia")

    hxg_s = f"{fa(f2(float(h['xg'])))} xG" if h.get("xg") is not None else ""
    axg_s = f"{fa(f2(float(a['xg'])))} xG" if a.get("xg") is not None else ""
    score_bar = (
        ""
        if header_mode == "compact"
        else (
            '<div class="score-hero">'
            f'<div class="fi gap12 min0">{_crest_html(h, 58)}'
            f'<div class="min0"><div class="sh-name trunc">{esc(h.get("name", ""))}</div>'
            f'<div class="sh-xg fm" style="color:{hc}">{hxg_s}</div></div></div>'
            f'<div class="sh-mid"><span class="sh-sc">{fa(h.get("score", 0))}</span><span class="sh-dash">—</span><span class="sh-sc">{fa(a.get("score", 0))}</span></div>'
            f'<div class="fi gap12 min0" style="justify-content:flex-end;text-align:left">'
            f'<div class="min0"><div class="sh-name trunc">{esc(a.get("name", ""))}</div>'
            f'<div class="sh-xg fm" style="color:{ac}">{axg_s}</div></div>'
            f'{_crest_html(a, 58)}</div></div>'
        )
    )

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl"><head><meta charset="UTF-8"><style>
{build_embedded_font_css()}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:{w}px;height:{h_px}px;overflow:hidden;background:{bg_hex};color:#F8FAFC;font-family:'Vazirmatn',sans-serif;font-feature-settings:"tnum";font-variant-numeric:tabular-nums}}
.fm{{font-family:'JetBrains Mono','Space Grotesk',monospace}} .fd{{font-family:'Space Grotesk','Vazirmatn',sans-serif}}
.fi{{display:flex;align-items:center}} .fc{{display:flex;align-items:center;justify-content:center}} .fbw{{display:flex;align-items:center;justify-content:space-between}} .fcol{{display:flex;flex-direction:column}}
.flex1{{flex:1}} .min0{{min-width:0;min-height:0}} .justify-center{{justify-content:center}}
.gap6{{gap:6px}} .gap8{{gap:8px}} .gap10{{gap:10px}} .gap12{{gap:12px}} .gap14{{gap:14px}}
.trunc{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
#ea{{position:relative;width:{w}px;height:{h_px}px;background:{bg_hex};display:flex;flex-direction:column;justify-content:space-between;padding:{pad_top}px 0 {pad_bot}px 0;overflow:hidden}}
.bg-svg{{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0}}
.hdr{{position:relative;z-index:5;display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 36px 8px;flex-shrink:0}}
.hdr-pill{{display:inline-flex;align-items:center;gap:10px;padding:6px 18px;border-radius:999px;background:#152347eb;border:1.5px solid #ffffff30;font-size:21px;font-weight:900;color:#F8FAFC}}
.hdr-tag{{padding:5px 15px;border-radius:999px;background:{acc}2b;border:1.5px solid {acc}88;color:#fff;font-size:17px;font-weight:800}}
.hdr-sub{{font-size:17px;font-weight:700;color:#CBD5E1;margin-top:4px}}
.stage{{position:relative;z-index:5;flex:1;padding:8px 40px;display:flex;flex-direction:column;justify-content:space-between;gap:12px;overflow:hidden;min-height:0}}
.score-hero{{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:14px;padding:12px 20px;border-radius:20px;background:linear-gradient(155deg,#132449f2,#070e20f8);border:1.5px solid rgba(255,255,255,.16);flex-shrink:0}}
.sh-name{{font-size:27px;font-weight:900;color:#fff;line-height:1.15}}
.sh-xg{{font-size:18px;font-weight:900;margin-top:2px}}
.sh-mid{{display:flex;align-items:center;gap:12px;padding:6px 20px;border-radius:16px;background:rgba(230,46,69,.18);border:1.5px solid rgba(230,46,69,.55)}}
.sh-sc{{font-size:44px;font-weight:900;color:#fff;line-height:1}}
.sh-dash{{font-size:22px;font-weight:900;color:#E62E45}}
.xm,.xe{{position:relative;border-radius:22px;padding:14px 18px;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;box-shadow:0 14px 36px -10px rgba(0,0,0,.62),inset 0 1px 0 rgba(255,255,255,.10)}}
.xm{{background:linear-gradient(165deg,#101d3be3,#091023f5);border:1.5px solid rgba(248,250,252,.15)}}
.xe{{background:linear-gradient(155deg,#122040ef,#081022f8);border:1.5px solid rgba(127,166,232,.28)}}
.mh{{display:flex;align-items:center;justify-content:space-between;gap:10px;padding-bottom:8px;margin-bottom:8px;border-bottom:1px solid rgba(255,255,255,.14);flex-shrink:0}}
.mh-bar{{width:7px;height:22px;border-radius:99px}}
.mt{{font-size:23px;font-weight:900;color:#fff}}
.mh-tag{{font-size:15.5px;font-weight:800;color:#CBD5E1}}
.sm-leg{{display:flex;align-items:center;gap:12px;font-size:14.5px;font-weight:800;color:#E2E8F0;flex-wrap:wrap}}
.sm-leg span{{display:inline-flex;align-items:center;gap:5px}}
.sm-leg i{{width:12px;height:12px;border-radius:999px;display:inline-block}}
.m-top{{display:grid;grid-template-columns:1fr 2fr 1fr;font-size:19px;font-weight:900;align-items:center}}
.m-bars{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
.ct{{height:11px;background:#ffffff1a;overflow:hidden;display:flex;align-items:center}}
.ct.hs{{justify-content:flex-end;border-radius:0 99px 99px 0}} .ct.as{{justify-content:flex-start;border-radius:99px 0 0 99px}}
.ch{{height:100%;border-radius:0 99px 99px 0}} .ca{{height:100%;border-radius:99px 0 0 99px}}
.bc-row{{display:flex;align-items:center;gap:12px;padding:10px 14px;border-radius:14px;background:rgba(7,14,32,.88);border:1px solid rgba(255,255,255,.11)}}
.bc-min{{width:44px;text-align:center;font-size:17px;font-weight:900;color:#CBD5E1;flex-shrink:0}}
.bc-pl{{font-size:19px;font-weight:900;color:#fff}}
.bc-res{{padding:3px 10px;border-radius:9px;border:1px solid;font-size:14.5px;font-weight:900;flex-shrink:0}}
.bc-xg{{font-size:19px;font-weight:900;flex-shrink:0}}
.verd-box{{border-right:5px solid {acc};gap:6px;flex-shrink:0}}
.verd-txt{{font-size:19.5px;font-weight:700;color:#F8FAFC;line-height:1.55}}
.ftr{{position:relative;z-index:5;padding:10px 44px 10px;border-top:1px solid rgba(255,255,255,.15);display:flex;align-items:center;justify-content:space-between;gap:14px;flex-shrink:0;flex-wrap:nowrap!important;white-space:nowrap!important;overflow:hidden!important}}
.ftr-l{{display:flex;align-items:center;gap:10px;min-width:0;overflow:hidden;white-space:nowrap!important;text-overflow:ellipsis!important}}
.ftr-dot{{width:10px;height:10px;border-radius:999px;background:{acc};flex-shrink:0}}
.ftr-tk{{font-size:17px;font-weight:800;color:#F1F5F9;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}}
.ftr-r{{display:flex;align-items:center;gap:10px;flex-shrink:0;white-space:nowrap!important;font-size:17px;color:#CBD5E1}}
.ftr-r b{{color:#fff;font-size:19px}}
</style></head><body>
<div id="ea">
  <svg class="bg-svg" viewBox="0 0 {w} {h_px}" preserveAspectRatio="xMidYMid slice" fill="none">
    <defs>
      <pattern id="smGrid" width="54" height="54" patternUnits="userSpaceOnUse"><path d="M54 0H0v54" stroke="#F8FAFC" stroke-opacity=".05"/></pattern>
      <radialGradient id="smGlow" cx="50%" cy="24%" r="55%"><stop offset="0" stop-color="{acc}" stop-opacity=".22"/><stop offset="1" stop-color="{acc}" stop-opacity="0"/></radialGradient>
    </defs>
    <rect width="100%" height="100%" fill="url(#smGrid)"/>
    <rect width="100%" height="100%" fill="url(#smGlow)"/>
    <rect x="12" y="12" width="{w - 24}" height="{h_px - 24}" rx="18" stroke="#F8FAFC" stroke-opacity=".12" stroke-width="1.5"/>
    <path d="M24 44V24H44M{w - 24} 44V24H{w - 44}M24 {h_px - 44}V{h_px - 24}H44M{w - 24} {h_px - 44}V{h_px - 24}H{w - 44}" stroke="#E62E45" stroke-width="2.4" stroke-linecap="square"/>
  </svg>
  <header class="hdr">
    <div class="min0">
      <div class="fi gap10" style="flex-wrap:wrap">
        <span class="hdr-pill">🎯 {comp_txt}</span>
        <span class="hdr-tag">{esc(sl_lbl)}</span>
      </div>
      {"" if header_mode == "compact" else f'<div class="hdr-sub">{rnd_txt}</div>'}
    </div>
    {logo_html}
  </header>
  <main class="stage">
    {score_bar}
    {"".join(blocks)}
  </main>
  <footer class="ftr">
    <div class="ftr-l"><span class="ftr-dot"></span><span class="ftr-tk">{comp_txt} • {esc(sl_lbl)} • XGPedia</span></div>
    <div class="ftr-r fm" dir="ltr"><b>@XGPedia</b><span>|</span><span>{src_txt}</span></div>
  </footer>
</div></body></html>"""
