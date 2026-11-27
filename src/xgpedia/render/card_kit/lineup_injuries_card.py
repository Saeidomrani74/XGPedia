"""رندرر ۱۰۰٪ آفلاین و ماژولار کارت ۵اسلایدی «ترکیب احتمالی و غایبان» (`lineup_injuries`).

۵ اسلاید استاندارد با هویت بصری یکپارچه XGPedia:
  - `slide1`: زمین تاکتیکی دو تیم (Dual Probable XI + درصد آمادگی)
  - `slide2`: تابلوی کامل مصدومان، محرومان و مشکوک‌ها (Absentees Board)
  - `slide3`: تمرکز کامل روی ترکیب احتمالی و غایبان میزبان (Home Focus)
  - `slide4`: تمرکز کامل روی ترکیب احتمالی و غایبان میهمان (Away Focus)
  - `slide5`: شاخص آمادگی دو تیم و دوئل‌های کلیدی ترکیب (Availability & Duels)
"""
from __future__ import annotations

from typing import Any

from src.xgpedia.render.card_kit.helpers import (
    with_sample_badge,
    _hex_to_rgb,
    ensure_dark_bg_contrast,
    esc,
    fa,
)
from src.xgpedia.render.cards import _brand_logo_data_uri
from src.xgpedia.render.studio_engine import build_embedded_font_css

LINEUP_FORMATS: dict[str, tuple[int, int]] = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}

LINEUP_SLIDES: list[tuple[str, str, str]] = [
    ("slide1", "زمین تاکتیکی دو تیم (XI)", "full"),
    ("slide2", "لیست غایبان و مصدومان", "full"),
    ("slide3", "ترکیب احتمالی میزبان", "full"),
    ("slide4", "ترکیب احتمالی میهمان", "full"),
    ("slide5", "آمادگی ترکیب و دوئل کلیدی", "full"),
]

_THEMES: dict[str, tuple[str, str]] = {
    "classic": ("#E62E45", "#38BDF8"),
    "pitch": ("#10B981", "#38BDF8"),
    "gold": ("#F59E0B", "#E62E45"),
}

_MODULE_SPECS: list[tuple[str, str, bool]] = [
    ("availability", "نوار درصد آمادگی دو تیم", True),
    ("verdict", "جمع‌بندی تحریریه تاکتیکی", True),
    ("grid", "بافت گرید تاکتیکی پس‌زمینه", True),
]


def get_lineup_injuries_modules(item: dict[str, Any], slide: str = "slide1") -> tuple[list[dict[str, Any]], list[str]]:
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


def _brand_logo_img(height: int = 44) -> str:
    uri = _brand_logo_data_uri()
    if uri:
        return f'<img src="{uri}" alt="XGPedia" style="height:{height}px;width:auto;display:block;object-fit:contain"/>'
    return '<div style="font-weight:900;font-size:30px" dir="ltr"><span style="color:#E62E45">XG</span><span style="color:#F8FAFC">Pedia</span></div>'


def _club_crest(code: str, club_name: str, color: str, size: int = 56) -> str:
    cd = (code or "PL").strip().upper()[:3]
    try:
        from src.xgpedia.providers.pl_badges_free import get_pl_badge_data_uri, lookup_pl_club
        info = lookup_pl_club(club_name or cd, tla_hint=cd)
        if info and info[4]:
            uri = get_pl_badge_data_uri(info[1], tla_hint=info[1], badge_code=info[4], size=100 if size >= 64 else 70, fetch_network=False)
            if uri:
                return (
                    f'<div style="width:{size}px;height:{size}px;border-radius:14px;background:rgba(15,23,42,.75);'
                    f'border:1px solid rgba(255,255,255,.18);padding:5px;display:flex;align-items:center;'
                    f'justify-content:center;flex-shrink:0">'
                    f'<img src="{uri}" alt="{esc(cd)}" style="width:100%;height:100%;object-fit:contain;display:block"/>'
                    f'</div>'
                )
    except Exception:
        pass
    c = ensure_dark_bg_contrast(color or "#E62E45", min_ratio=4.2)
    return (
        f'<div style="width:{size}px;height:{size}px;border-radius:14px;background:rgba(15,23,42,.88);'
        f'border:2px solid {c};display:flex;align-items:center;justify-content:center;'
        f'font-family:Space Grotesk,sans-serif;font-weight:800;font-size:{max(14, size // 3)}px;color:#fff;flex-shrink:0">'
        f'{esc(cd)}</div>'
    )


def _dual_pitch_svg(home: dict[str, Any], away: dict[str, Any], w_svg: int = 940, h_svg: int = 760) -> str:
    hc = ensure_dark_bg_contrast(str(home.get("color") or "#E62E45"), min_ratio=4.5)
    ac = ensure_dark_bg_contrast(str(away.get("color") or "#38BDF8"), min_ratio=4.5)
    if ac.lower() == hc.lower():
        ac = "#38BDF8" if hc.upper() != "#38BDF8" else "#F59E0B"

    pad = 24
    pw = w_svg - pad * 2
    ph = h_svg - pad * 2

    def _nodes(players: list[dict[str, Any]], col: str) -> str:
        out = []
        for p in players[:11]:
            px = pad + (float(p.get("x") or 50) / 100.0) * pw
            py = pad + (float(p.get("y") or 50) / 100.0) * ph
            ch = int(p.get("chance") if p.get("chance") is not None else 100)
            nm = esc(str(p.get("name") or "")[:14])
            pos = esc(str(p.get("pos") or ""))
            ring = "#F59E0B" if ch < 100 else "#F8FAFC"
            badge = (
                f'<rect x="{px+12:.1f}" y="{py-26:.1f}" width="38" height="18" rx="6" fill="#F59E0B"/>'
                f'<text x="{px+31:.1f}" y="{py-13:.1f}" text-anchor="middle" fill="#0D1730" font-family="Vazirmatn,sans-serif" font-size="11" font-weight="900">{fa(str(ch))}٪</text>'
                if ch < 100 else ""
            )
            out.append(
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="22" fill="{col}" fill-opacity=".24"/>'
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="16" fill="{col}" stroke="{ring}" stroke-width="2.5"/>'
                f'<text x="{px:.1f}" y="{py+4:.1f}" text-anchor="middle" fill="#0D1730" font-family="Space Grotesk,sans-serif" font-size="10" font-weight="900">{pos}</text>'
                f'<rect x="{px-48:.1f}" y="{py+19:.1f}" width="96" height="22" rx="7" fill="rgba(7,13,29,.88)" stroke="rgba(255,255,255,.15)"/>'
                f'<text x="{px:.1f}" y="{py+34:.1f}" text-anchor="middle" fill="#F8FAFC" font-family="Vazirmatn,sans-serif" font-size="13" font-weight="800">{nm}</text>'
                f'{badge}'
            )
        return "".join(out)

    return (
        f'<svg viewBox="0 0 {w_svg} {h_svg}" width="100%" height="100%" style="display:block">'
        f'<defs><linearGradient id="pitchBg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="#0E2A38"/><stop offset="50%" stop-color="#0C2232"/><stop offset="100%" stop-color="#0E2A38"/>'
        f'</linearGradient></defs>'
        f'<rect x="{pad}" y="{pad}" width="{pw}" height="{ph}" rx="18" fill="url(#pitchBg)" stroke="rgba(255,255,255,.22)" stroke-width="2.5"/>'
        f'<line x1="{pad}" y1="{h_svg/2:.1f}" x2="{w_svg-pad}" y2="{h_svg/2:.1f}" stroke="rgba(255,255,255,.22)" stroke-width="2"/>'
        f'<circle cx="{w_svg/2:.1f}" cy="{h_svg/2:.1f}" r="64" fill="none" stroke="rgba(255,255,255,.20)" stroke-width="2"/>'
        f'<rect x="{w_svg/2-150:.1f}" y="{pad}" width="300" height="96" fill="none" stroke="rgba(255,255,255,.18)" stroke-width="2"/>'
        f'<rect x="{w_svg/2-150:.1f}" y="{h_svg-pad-96:.1f}" width="300" height="96" fill="none" stroke="rgba(255,255,255,.18)" stroke-width="2"/>'
        f'{_nodes(home.get("lineup") or [], hc)}'
        f'{_nodes(away.get("lineup") or [], ac)}'
        f'</svg>'
    )


def _single_team_pitch_svg(team: dict[str, Any], *, is_home: bool, w_svg: int = 920, h_svg: int = 560) -> str:
    col = ensure_dark_bg_contrast(str(team.get("color") or "#E62E45"), min_ratio=4.5)
    pad = 24
    pw = w_svg - pad * 2
    ph = h_svg - pad * 2
    nodes = []
    for p in (team.get("lineup") or [])[:11]:
        px = pad + (float(p.get("x") or 50) / 100.0) * pw
        # نگاشت y نیمه‌زمین به تمام ارتفاع باکس تک‌تیم
        raw_y = float(p.get("y") or 25)
        norm_y = (raw_y / 52.0) if is_home else ((100.0 - raw_y) / 52.0)
        py = pad + max(0.10, min(0.86, norm_y)) * ph
        ch = int(p.get("chance") if p.get("chance") is not None else 100)
        nm = esc(str(p.get("name") or "")[:16])
        pos = esc(str(p.get("pos") or ""))
        ring = "#F59E0B" if ch < 100 else "#F8FAFC"
        nodes.append(
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="26" fill="{col}" fill-opacity=".24"/>'
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="19" fill="{col}" stroke="{ring}" stroke-width="3"/>'
            f'<text x="{px:.1f}" y="{py+5:.1f}" text-anchor="middle" fill="#0D1730" font-family="Space Grotesk,sans-serif" font-size="11" font-weight="900">{pos}</text>'
            f'<rect x="{px-56:.1f}" y="{py+22:.1f}" width="112" height="26" rx="8" fill="rgba(7,13,29,.90)" stroke="rgba(255,255,255,.18)"/>'
            f'<text x="{px:.1f}" y="{py+40:.1f}" text-anchor="middle" fill="#F8FAFC" font-family="Vazirmatn,sans-serif" font-size="15" font-weight="800">{nm}</text>'
        )
    return (
        f'<svg viewBox="0 0 {w_svg} {h_svg}" width="100%" height="100%" style="display:block">'
        f'<rect x="{pad}" y="{pad}" width="{pw}" height="{ph}" rx="18" fill="#0E2636" stroke="rgba(255,255,255,.22)" stroke-width="2.5"/>'
        f'<rect x="{w_svg/2-160:.1f}" y="{pad}" width="320" height="100" fill="none" stroke="rgba(255,255,255,.18)" stroke-width="2"/>'
        f'<circle cx="{w_svg/2:.1f}" cy="{h_svg-pad:.1f}" r="80" fill="none" stroke="rgba(255,255,255,.18)" stroke-width="2"/>'
        f'{"".join(nodes)}'
        f'</svg>'
    )


def _absentees_list_html(absentees: list[dict[str, Any]], max_items: int = 6) -> str:
    if not absentees:
        return '<div class="empty-ok">✅ هیچ بازیکن مصدوم یا محرومی ثبت نشده است.</div>'
    rows = []
    for ab in absentees[:max_items]:
        ch = int(ab.get("chance") if ab.get("chance") is not None else 0)
        if ch == 0:
            pill_cls = "st-out"
        elif ch <= 50:
            pill_cls = "st-mid"
        else:
            pill_cls = "st-likely"
        mins = int(ab.get("minutes") or 0)
        rows.append(
            f'<div class="ab-row">'
            f'<div><div class="ab-nm">{esc(ab.get("name", ""))}</div>'
            f'<div class="ab-sub">{esc(ab.get("pos_fa", ""))} • {fa(str(mins))} دقیقه فصل</div></div>'
            f'<span class="ab-pill {pill_cls}">{esc(ab.get("status_fa", "غایب"))}</span>'
            f'</div>'
        )
    return "".join(rows)


@with_sample_badge
def render_lineup_injuries_html(
    item: dict[str, Any],
    *,
    slide: str = "slide1",
    header_mode: str = "full",
    fmt: str = "4:5",
    theme: str = "classic",
    modules: list[dict[str, Any]] | None = None,
) -> str:
    """تولید HTML ۱۰۰٪ آفلاین کارت ۵اسلایدی ترکیب احتمالی و غایبان."""
    w, h = LINEUP_FORMATS.get(fmt, LINEUP_FORMATS["4:5"])
    is16 = fmt == "16:9"
    is9 = fmt == "9:16"
    accent, accent2 = _THEMES.get(theme, _THEMES["classic"])
    r1, g1, b1 = _hex_to_rgb(accent)
    r2, g2, b2 = _hex_to_rgb(accent2)

    if modules is None:
        modules, _ = get_lineup_injuries_modules(item, slide)
    mod_map = {m["id"]: bool(m.get("enabled", True)) for m in modules if isinstance(m, dict) and m.get("id")}
    show_avail = mod_map.get("availability", True)
    show_verdict = mod_map.get("verdict", True)
    show_grid = mod_map.get("grid", True)

    home = item.get("home") or {}
    away = item.get("away") or {}
    comp = esc(str(item.get("competition") or "لیگ برتر انگلیس"))
    rnd = esc(str(item.get("round") or "هفته پیش‌رو"))
    ko = esc(str(item.get("kickoff_fa") or ""))
    src = esc(str(item.get("source") or "Opta FPL / XGPedia"))
    verdict = esc(str(item.get("editorial_verdict") or ""))

    h_nm = esc(str(home.get("name") or "میزبان"))
    a_nm = esc(str(away.get("name") or "میهمان"))
    h_form = fa(str(home.get("formation") or "4-3-3"))
    a_form = fa(str(away.get("formation") or "4-2-3-1"))
    h_av = int(home.get("availability_pct") or 85)
    a_av = int(away.get("availability_pct") or 85)

    pad_top = 139 if is9 else (24 if is16 else 22)
    pad_bot = 171 if is9 else (20 if is16 else 16)
    pad_x = 44 if is16 else 36

    avail_strip = (
        f'<div class="avail-strip">'
        f'<div class="av-side">{_club_crest(str(home.get("code") or ""), h_nm, str(home.get("color") or accent), 44)}'
        f'<div><div class="av-nm">{h_nm} ({h_form})</div><div class="av-sub">آمادگی ترکیب: <b style="color:#34D399">{fa(str(h_av))}٪</b></div></div></div>'
        f'<div class="av-vs">VS</div>'
        f'<div class="av-side" style="justify-content:flex-end;text-align:left">'
        f'<div><div class="av-nm">{a_nm} ({a_form})</div><div class="av-sub">آمادگی ترکیب: <b style="color:#38BDF8">{fa(str(a_av))}٪</b></div></div>'
        f'{_club_crest(str(away.get("code") or ""), a_nm, str(away.get("color") or accent2), 44)}</div>'
        f'</div>'
        if show_avail else ""
    )

    if slide == "slide1":
        body_html = (
            f'{avail_strip}'
            f'<div class="card-panel flex1" style="padding:14px">'
            f'{_dual_pitch_svg(home, away, 940 if not is16 else 1200, 740 if not is16 else 560)}'
            f'</div>'
        )
    elif slide == "slide2":
        body_html = (
            f'{avail_strip}'
            f'<div class="dual-grid flex1">'
            f'<div class="card-panel"><div class="sec-hdr"><span>غایبان و مشکوک‌های {h_nm}</span><span class="cnt-pill">{fa(str(len(home.get("absentees") or [])))} نفر</span></div>'
            f'<div class="fcol gap10 flex1">{_absentees_list_html(home.get("absentees") or [], 6)}</div></div>'
            f'<div class="card-panel"><div class="sec-hdr"><span>غایبان و مشکوک‌های {a_nm}</span><span class="cnt-pill">{fa(str(len(away.get("absentees") or [])))} نفر</span></div>'
            f'<div class="fcol gap10 flex1">{_absentees_list_html(away.get("absentees") or [], 6)}</div></div>'
            f'</div>'
        )
    elif slide in ("slide3", "slide4"):
        is_h = slide == "slide3"
        t_obj = home if is_h else away
        t_nm = h_nm if is_h else a_nm
        t_fm = h_form if is_h else a_form
        body_html = (
            f'<div class="card-panel flex1" style="padding:18px">'
            f'<div class="sec-hdr"><div class="fi gap12">{_club_crest(str(t_obj.get("code") or ""), t_nm, str(t_obj.get("color") or accent), 48)}'
            f'<span>ترکیب احتمالی {t_nm} (چیدمان {t_fm})</span></div><span class="cnt-pill">آمادگی {fa(str(int(t_obj.get("availability_pct") or 85)))}٪</span></div>'
            f'<div style="flex:1;min-height:0">{_single_team_pitch_svg(t_obj, is_home=is_h, w_svg=920, h_svg=520)}</div>'
            f'</div>'
            f'<div class="card-panel" style="padding:16px 20px">'
            f'<div class="sec-hdr" style="font-size:18px"><span>مصدومان و مشکوک‌های {t_nm}</span><span class="cnt-pill">{fa(str(len(t_obj.get("absentees") or [])))} نفر</span></div>'
            f'<div class="ab-grid">{_absentees_list_html(t_obj.get("absentees") or [], 4)}</div>'
            f'</div>'
        )
    else:  # slide5: Availability & Key Duels
        duels = [d for d in (item.get("key_duels") or []) if isinstance(d, dict)][:3]
        d_rows = "".join(
            f'<div class="duel-row">'
            f'<div class="duel-p">{esc(d.get("home_p", ""))}</div>'
            f'<div class="duel-mid">{esc(d.get("title", "دوئل کلیدی"))}</div>'
            f'<div class="duel-p">{esc(d.get("away_p", ""))}</div>'
            f'</div>'
            for d in duels
        )
        body_html = (
            f'<div class="card-panel">'
            f'<div class="sec-hdr"><span>شاخص آمادگی ترکیب (وزن‌دهی بر اساس دقایق فصل)</span><span class="cnt-pill">مقایسه سلامت</span></div>'
            f'<div class="bar-cmp">'
            f'<div class="bar-lbl"><span>{h_nm}</span><b style="color:#34D399">{fa(str(h_av))}٪</b></div>'
            f'<div class="bar-tr"><div class="bar-fl" style="width:{h_av}%;background:linear-gradient(90deg,#10B981,#34D399)"></div></div>'
            f'<div class="bar-lbl" style="margin-top:14px"><span>{a_nm}</span><b style="color:#38BDF8">{fa(str(a_av))}٪</b></div>'
            f'<div class="bar-tr"><div class="bar-fl" style="width:{a_av}%;background:linear-gradient(90deg,#0EA5E9,#38BDF8)"></div></div>'
            f'</div>'
            f'</div>'
            f'<div class="card-panel flex1">'
            f'<div class="sec-hdr"><span>دوئل‌های کلیدی داخل ترکیب احتمالی</span><span class="cnt-pill">کلید تاکتیکی</span></div>'
            f'<div class="fcol gap12 flex1" style="justify-content:center">{d_rows or "<div class=empty-ok>اطلاعات دوئل ثبت نشده است.</div>"}</div>'
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
    slide_lbl = dict((s[0], s[1]) for s in LINEUP_SLIDES).get(slide, "ترکیب احتمالی")

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8"/>
<style>
{build_embedded_font_css()}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:{w}px;height:{h}px;overflow:hidden;background:#0D1730;color:#F8FAFC;font-family:'Vazirmatn',sans-serif}}
.stage{{position:relative;width:{w}px;height:{h}px;background:#0D1730;overflow:hidden;display:flex;flex-direction:column;padding:{pad_top}px {pad_x}px {pad_bot}px {pad_x}px;gap:14px;{grid_css}}}
.glow{{position:absolute;inset:0;pointer-events:none;background:radial-gradient(circle at 86% 18%,rgba({r1},{g1},{b1},.22),transparent 48%),radial-gradient(circle at 14% 84%,rgba({r2},{g2},{b2},.22),transparent 48%)}}
.frame{{position:absolute;inset:12px;pointer-events:none;border:1px solid rgba(255,255,255,.08);border-radius:16px}}.crn{{position:absolute;width:28px;height:28px;pointer-events:none;z-index:5}}.c-tl{{top:14px;left:14px;border-top:3.5px solid #E62E45;border-left:3.5px solid #E62E45;border-top-left-radius:8px}}.c-tr{{top:14px;right:14px;border-top:3.5px solid #E62E45;border-right:3.5px solid #E62E45;border-top-right-radius:8px}}.c-bl{{bottom:14px;left:14px;border-bottom:3.5px solid #E62E45;border-left:3.5px solid #E62E45;border-bottom-left-radius:8px}}.c-br{{bottom:14px;right:14px;border-bottom:3.5px solid #E62E45;border-right:3.5px solid #E62E45;border-bottom-right-radius:8px}}
.z2{{position:relative;z-index:2}}
.hdr{{display:flex;align-items:center;justify-content:space-between;gap:16px}}
.hdr-r{{display:flex;flex-direction:column;gap:4px}}
.pill{{display:inline-flex;align-items:center;gap:8px;padding:5px 15px;border-radius:999px;background:rgba(15,23,42,.85);border:1px solid rgba({r1},{g1},{b1},.45);font-size:16px;font-weight:800;color:#E2E8F0;width:fit-content}}
.ttl{{font-size:36px;font-weight:900;color:#fff;line-height:1.25}}
.sub{{font-size:19px;font-weight:700;color:#94A3B8}}
.flex1{{flex:1;min-height:0}}
.fcol{{display:flex;flex-direction:column}}
.fi{{display:flex;align-items:center}}
.gap10{{gap:10px}}.gap12{{gap:12px}}
.avail-strip{{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:12px;background:rgba(15,23,42,.82);border:1px solid rgba(255,255,255,.12);border-radius:18px;padding:12px 18px}}
.av-side{{display:flex;align-items:center;gap:12px}}
.av-nm{{font-size:20px;font-weight:900;color:#fff}}
.av-sub{{font-size:15px;font-weight:700;color:#94A3B8}}
.av-vs{{font-family:'Space Grotesk',sans-serif;font-size:19px;font-weight:900;color:#E62E45;background:rgba(230,46,69,.14);padding:6px 14px;border-radius:10px}}
.card-panel{{background:rgba(15,23,42,.74);border:1px solid rgba(255,255,255,.12);border-radius:20px;padding:18px 20px;display:flex;flex-direction:column;gap:12px}}
.sec-hdr{{display:flex;align-items:center;justify-content:space-between;font-size:20px;font-weight:900;color:#F8FAFC;border-bottom:1px solid rgba(255,255,255,.1);padding-bottom:10px}}
.cnt-pill{{font-size:15px;font-weight:800;color:#38BDF8;background:rgba(56,189,248,.14);border:1px solid rgba(56,189,248,.38);padding:4px 12px;border-radius:999px}}
.dual-grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
.ab-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.ab-row{{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:11px 14px;border-radius:14px;background:rgba(13,23,48,.82);border:1px solid rgba(255,255,255,.08)}}
.ab-nm{{font-size:19px;font-weight:900;color:#fff}}
.ab-sub{{font-size:14px;font-weight:600;color:#94A3B8}}
.ab-pill{{font-size:14px;font-weight:900;padding:5px 12px;border-radius:999px;white-space:nowrap}}
.st-out{{background:rgba(239,68,68,.2);color:#FCA5A5;border:1px solid rgba(239,68,68,.45)}}
.st-mid{{background:rgba(245,158,11,.2);color:#FCD34D;border:1px solid rgba(245,158,11,.45)}}
.st-likely{{background:rgba(16,185,129,.2);color:#6EE7B7;border:1px solid rgba(16,185,129,.45)}}
.empty-ok{{padding:18px;text-align:center;font-size:18px;font-weight:800;color:#34D399;background:rgba(16,185,129,.1);border-radius:14px}}
.bar-lbl{{display:flex;justify-content:space-between;font-size:20px;font-weight:900;margin-bottom:6px}}
.bar-tr{{height:16px;border-radius:999px;background:rgba(255,255,255,.1);overflow:hidden}}
.bar-fl{{height:100%;border-radius:999px}}
.duel-row{{display:grid;grid-template-columns:1fr 1.3fr 1fr;align-items:center;padding:16px 18px;border-radius:16px;background:rgba(13,23,48,.82);border:1px solid rgba(255,255,255,.1)}}
.duel-p{{font-size:21px;font-weight:900;color:#fff;text-align:center}}
.duel-mid{{font-size:16px;font-weight:800;color:#38BDF8;text-align:center;background:rgba(56,189,248,.12);padding:6px 12px;border-radius:999px}}
.verdict-bar{{display:flex;align-items:center;gap:12px;padding:13px 18px;border-radius:16px;background:rgba(15,23,42,.86);border:1px solid rgba({r1},{g1},{b1},.38);font-size:16.5px;font-weight:700;color:#E2E8F0;line-height:1.5}}
.v-dot{{width:10px;height:10px;border-radius:99px;background:{accent};flex-shrink:0}}
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
      <div class="pill"><span style="width:9px;height:9px;border-radius:99px;background:{accent}"></span><span>ترکیب احتمالی و غایبان • {comp}</span></div>
      <div class="ttl">{h_nm} × {a_nm}</div>
      <div class="sub">{slide_lbl} • {rnd}{(" • " + ko) if ko else ""}</div>
    </div>
    {_brand_logo_img(46)}
  </div>
  <div class="fcol gap12 flex1 z2">
    {body_html}
    {verdict_html}
  </div>
  <div class="ftr z2">
    <span>{comp} • ترکیب احتمالی و غایبان</span>
    <span class="ftr-l" dir="ltr">@XGPedia | {src}</span>
  </div>
</div>
</body>
</html>"""
