"""کارت اسلایدی و ماژولار «خلاصهٔ هفته + فرم در برابر جدول» (`Matchweek Wrap-up & Form vs. Table Studio — v0.37.0`).

۵ اسلاید استاندارد + ۶ ماژول کاملاً مستقل و قابل جداسازی/ترکیب:
  - `slide1`: خلاصهٔ جامع هفته (`awards_trio`, `form_vs_table`, `editorial_verdict`)
  - `slide2`: رتبه‌بندی قدرت فرم ۵ بازی در برابر جدول (`form_vs_table`, `editorial_verdict`)
  - `slide3`: رادار بیش‌عملکردها و بدشانس‌ترین تیم‌ها (`xg_overunder`, `editorial_verdict`)
  - `slide4`: بهترین خط حمله و دژ دفاعی (`awards_trio`, `attack_defense`, `editorial_verdict`)
  - `slide5`: تیم منتخب هفته روی زمین تاکتیکی (`totw_pitch`, `editorial_verdict`)

استانداردهای دائمی XGPedia:
  - ۱۰۰٪ آفلاین (فونت محلی Vazirmatn + JetBrains Mono + Space Grotesk، بدون CDN)
  - پالت Midnight Navy `#0D1730` + Signature Crimson `#E62E45` + Gold `#FBBF24`
  - فریم چهارگوشه قرمز یکپارچه (`pad_top=24/22/139`, `pad_bot=20/16/171`)
  - لوگوی واقعی باشگاه‌های انگلیس (`pl_badges_free`) و فوتر اکیداً تک‌خطی (`white-space:nowrap!important`)
  - رعایت اکید `null ≠ 0` (ماژول‌های بدون دیتای واقعی خودکار مخفی می‌شوند).
"""
from __future__ import annotations

from typing import Any

from src.xgpedia.render.card_kit.helpers import with_sample_badge, ensure_dark_bg_contrast, esc, f1, fa
from src.xgpedia.render.cards import _brand_logo_data_uri
from src.xgpedia.render.studio_engine import build_embedded_font_css

WRAPUP_FORMATS: dict[str, tuple[int, int]] = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}

# (slide_id, label_fa, subtitle_fa, default_module_ids)
WRAPUP_SLIDES: list[tuple[str, str, str, list[str]]] = [
    ("slide1", "اسلاید ۱: خلاصهٔ جامع هفته", "خلاصهٔ هفته", ["awards_trio", "form_vs_table", "editorial_verdict"]),
    ("slide2", "اسلاید ۲: فرم ۵ بازی در برابر جدول", "قدرت فرم", ["form_vs_table", "editorial_verdict"]),
    ("slide3", "اسلاید ۳: بیش‌عملکردها و بدشانس‌ها (G − xG)", "آزمایشگاه xG", ["xg_overunder", "editorial_verdict"]),
    ("slide4", "اسلاید ۴: بهترین خط حمله و دژ دفاعی", "برترین‌های تیمی", ["awards_trio", "attack_defense", "editorial_verdict"]),
    ("slide5", "اسلاید ۵: تیم منتخب هفته (XI)", "تیم منتخب هفته", ["totw_pitch", "editorial_verdict"]),
]


def _club_crest_html(name: str, code: str, color: str, size: int = 40) -> str:
    """لوگوی واقعی باشگاه (آفلاین از `brand/crests/` یا کش لیگ برتر) با پشتیبان نشان رنگی."""
    from src.xgpedia.providers.pl_badges_free import get_pl_badge_data_uri
    uri = get_pl_badge_data_uri(name, tla_hint=code, fetch_network=False)
    if uri:
        return (
            f'<div class="fc" style="width:{size}px;height:{size}px;flex-shrink:0;border-radius:50%;'
            f'background:rgba(7,13,29,.76);padding:{max(3, size // 11)}px;border:1.5px solid rgba(255,255,255,.16)">'
            f'<img src="{esc(uri)}" alt="{esc(code)}" style="width:100%;height:100%;object-fit:contain;display:block"/></div>'
        )
    c = ensure_dark_bg_contrast(color or "#E62E45", min_ratio=4.2)
    return (
        f'<div class="fc fm" style="width:{size}px;height:{size}px;flex-shrink:0;border-radius:12px;'
        f'background:{c}26;border:1.5px solid {c}88;color:#fff;font-weight:900;font-size:{max(12, size // 3)}px">'
        f'{esc(str(code or "FC")[:3].upper())}</div>'
    )


def get_matchweek_wrapup_modules(item: dict[str, Any], slide: str = "slide1") -> tuple[list[dict[str, Any]], list[str]]:
    """فهرست ماژول‌های مستقل کارت خلاصهٔ هفته (هر ماژول قابل فعال/غیرفعال و ترکیب مجزا است)."""
    awards = item.get("awards") or {}
    has_awards = bool(awards.get("bestAttack") or awards.get("bestDefense"))
    has_form = len(item.get("formVsTable") or []) >= 2
    has_ou = bool((item.get("overperformers") or []) or (item.get("underperformers") or []))
    has_att_def = bool(awards.get("bestAttack") and awards.get("bestDefense"))
    has_totw = len(item.get("totw") or []) >= 4
    has_verdict = bool(str(item.get("editorialVerdict") or "").strip())

    def_set = set(next((mids for sid, _, _, mids in WRAPUP_SLIDES if sid == slide), WRAPUP_SLIDES[0][3]))
    specs = [
        ("awards_trio", "تالار ۳ عنوان برتر هفته (حمله، بدشانس، دفاع)", has_awards),
        ("form_vs_table", "جدول قدرت فرم ۵ بازی در برابر جایگاه", has_form),
        ("xg_overunder", "رادار بیش‌عملکردها و بدشانس‌ها (G − xG)", has_ou),
        ("attack_defense", "مقایسهٔ برترین خط حمله و دژ دفاعی", has_att_def),
        ("totw_pitch", "تیم منتخب هفته روی زمین تاکتیکی (XI)", has_totw),
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
# ماژول‌های مستقل و قابل جداسازی (Independent Extractable Module Renderers)
# ---------------------------------------------------------------------------

def render_mod_awards_trio(item: dict[str, Any]) -> str:
    awards = item.get("awards") or {}
    cards: list[str] = []
    defs = [
        ("bestAttack", "🔥 بهترین خط حمله", "#FBBF24"),
        ("unluckiest", "⚡ بدشانس‌ترین تیم (G−xG)", "#FB7185"),
        ("bestDefense", "🛡 دژ دفاعی لیگ", "#34D399"),
    ]
    for key, label, col in defs:
        a = awards.get(key)
        if not isinstance(a, dict) or not a.get("name"):
            continue
        cards.append(
            f'<div class="aw-card" style="border-top:4px solid {col}">'
            f'<div class="aw-lbl" style="color:{col}">{label}</div>'
            f'<div class="fi gap10" style="margin-top:8px">'
            f'{_club_crest_html(str(a.get("name") or ""), str(a.get("code") or ""), str(a.get("color") or col), 48)}'
            f'<div class="min0"><div class="aw-name trunc">{esc(a.get("name", ""))}</div>'
            f'<div class="aw-val" style="color:{col}">{fa(esc(a.get("val", "")))}</div></div></div>'
            f'<div class="aw-sub">{fa(esc(a.get("sub", "")))}</div></div>'
        )
    if not cards:
        return ""
    return f'<div class="aw-grid" style="grid-template-columns:repeat({len(cards)},minmax(0,1fr))">{"".join(cards)}</div>'


def render_mod_form_vs_table(item: dict[str, Any]) -> str:
    rows = (item.get("formVsTable") or [])[:6]
    if not rows:
        return ""
    body = []
    for r in rows:
        t_rk = int(r.get("tableRank") or 0)
        f_rk = int(r.get("formRank") or t_rk)
        delta = t_rk - f_rk  # مثبت یعنی فرم بهتر از جایگاه جدول (صعودی)
        if delta > 0:
            d_badge = f'<span class="rk-d up">▲ +{fa(delta)}</span>'
        elif delta < 0:
            d_badge = f'<span class="rk-d dn">▼ −{fa(abs(delta))}</span>'
        else:
            d_badge = '<span class="rk-d eq">● ثابت</span>'

        dots = "".join(
            f'<span class="fdot fd-{str(ch).lower()}">{esc(ch)}</span>'
            for ch in (r.get("form") or [])[-5:]
        )
        fpts = r.get("formPts")
        pts_txt = f"{fa(fpts)} امتیاز فرم" if fpts is not None else f"{fa(r.get('pts', 0))} امتیاز"
        body.append(
            '<div class="ft-row">'
            f'<div class="fc"><span class="ft-rk fm">#{fa(f_rk)}</span></div>'
            f'<div class="fi gap10 min0">{_club_crest_html(str(r.get("name") or ""), str(r.get("code") or ""), str(r.get("color") or ""), 40)}'
            f'<div class="min0"><div class="ft-name trunc">{esc(r.get("name", ""))}</div>'
            f'<div class="ft-sub">جایگاه جدول: <b>#{fa(t_rk)}</b> ({fa(r.get("pts", 0))} امتیاز)</div></div></div>'
            f'<div class="ft-dots" dir="ltr">{dots}</div>'
            f'<div class="ft-end"><span class="ft-fpts">{pts_txt}</span>{d_badge}</div>'
            '</div>'
        )
    return (
        '<div class="xm" style="flex:1">'
        '<div class="mh"><div class="fi gap10"><span class="mh-bar" style="background:#E62E45"></span>'
        '<h3 class="mt">رتبه‌بندی قدرت فرم (۵ بازی اخیر) در برابر جدول</h3></div>'
        '<span class="mh-tag">مقایسه فرم و رتبه</span></div>'
        f'<div class="ft-list">{"".join(body)}</div></div>'
    )


def render_mod_xg_overunder(item: dict[str, Any]) -> str:
    over = (item.get("overperformers") or [])[:3]
    under = (item.get("underperformers") or [])[:3]
    if not over and not under:
        return ""
    mx = max([abs(float(x.get("delta") or 0.0)) for x in (over + under)] or [1.0])

    def _col_rows(arr: list[dict[str, Any]], is_pos: bool) -> str:
        col = "#34D399" if is_pos else "#FB7185"
        out = []
        for x in arr:
            d_v = float(x.get("delta") or 0.0)
            w_pct = max(18.0, min(100.0, abs(d_v) / max(0.5, mx) * 100.0))
            sgn = f"+{fa(f1(d_v))}" if d_v >= 0 else f"−{fa(f1(abs(d_v)))}"
            out.append(
                '<div class="ou-row">'
                f'<div class="fbw gap8"><div class="fi gap10 min0">'
                f'{_club_crest_html(str(x.get("name") or ""), str(x.get("code") or ""), str(x.get("color") or col), 38)}'
                f'<div class="min0"><div class="ou-name trunc">{esc(x.get("name", ""))}</div>'
                f'<div class="ou-sub">{fa(x.get("goals", 0))} گل از {fa(f1(x.get("xg", 0)))} xG</div></div></div>'
                f'<span class="ou-delta fm" dir="ltr" style="color:{col};border-color:{col}55;background:{col}1c">{sgn}</span></div>'
                f'<div class="ou-track"><div class="ou-fill" style="width:{w_pct:.1f}%;background:{col}"></div></div></div>'
            )
        return "".join(out)

    return (
        '<div class="ou-grid">'
        '<div class="xm" style="border-top:4px solid #34D399">'
        '<div class="mh"><div class="fi gap8"><span class="mh-bar" style="background:#34D399"></span>'
        '<h3 class="mt" style="font-size:22px">کلینیکال و فراتر از انتظار</h3></div></div>'
        f'<div class="fcol gap12 flex1 justify-center">{_col_rows(over, True)}</div></div>'
        '<div class="xm" style="border-top:4px solid #FB7185">'
        '<div class="mh"><div class="fi gap8"><span class="mh-bar" style="background:#FB7185"></span>'
        '<h3 class="mt" style="font-size:22px">بدشانس‌ترین‌ها (کمتر از xG)</h3></div></div>'
        f'<div class="fcol gap12 flex1 justify-center">{_col_rows(under, False)}</div></div>'
        '</div>'
    )


def render_mod_attack_defense(item: dict[str, Any]) -> str:
    awards = item.get("awards") or {}
    att = awards.get("bestAttack")
    dfn = awards.get("bestDefense")
    if not (isinstance(att, dict) and isinstance(dfn, dict)):
        return ""
    return (
        '<div class="ad-grid">'
        f'<div class="xe" style="border-right:5px solid #FBBF24;gap:12px">'
        f'<div class="aw-lbl" style="color:#FBBF24">🔥 آتشین‌ترین خط حمله</div>'
        f'<div class="fi gap14">{_club_crest_html(str(att.get("name") or ""), str(att.get("code") or ""), str(att.get("color") or "#FBBF24"), 68)}'
        f'<div class="min0"><div style="font-size:30px;font-weight:900;color:#fff">{esc(att.get("name", ""))}</div>'
        f'<div style="font-size:26px;font-weight:900;color:#FDE047;margin-top:2px">{fa(esc(att.get("val", "")))}</div></div></div>'
        f'<div style="font-size:18px;font-weight:700;color:#E2E8F0">{fa(esc(att.get("sub", "")))}</div></div>'
        f'<div class="xe" style="border-right:5px solid #34D399;gap:12px">'
        f'<div class="aw-lbl" style="color:#34D399">🛡 مستحکم‌ترین خط دفاع</div>'
        f'<div class="fi gap14">{_club_crest_html(str(dfn.get("name") or ""), str(dfn.get("code") or ""), str(dfn.get("color") or "#34D399"), 68)}'
        f'<div class="min0"><div style="font-size:30px;font-weight:900;color:#fff">{esc(dfn.get("name", ""))}</div>'
        f'<div style="font-size:26px;font-weight:900;color:#6EE7B7;margin-top:2px">{fa(esc(dfn.get("val", "")))}</div></div></div>'
        f'<div style="font-size:18px;font-weight:700;color:#E2E8F0">{fa(esc(dfn.get("sub", "")))}</div></div>'
        '</div>'
    )


def render_mod_totw_pitch(item: dict[str, Any]) -> str:
    totw = item.get("totw") or []
    if len(totw) < 4:
        return ""
    lines = [
        ("FWD", [p for p in totw if p.get("pos") == "FWD"][:3]),
        ("MID", [p for p in totw if p.get("pos") == "MID"][:4]),
        ("DEF", [p for p in totw if p.get("pos") == "DEF"][:4]),
        ("GK", [p for p in totw if p.get("pos") == "GK"][:1]),
    ]
    rows_html = []
    for _pos, pls in lines:
        if not pls:
            continue
        chips = []
        for pl in pls:
            col = ensure_dark_bg_contrast(str(pl.get("color") or "#38BDF8"), min_ratio=4.0)
            chips.append(
                f'<div class="xi-node" style="border-color:{col}88">'
                f'<div class="fi gap8" style="justify-content:center">'
                f'{_club_crest_html("", str(pl.get("clubCode") or ""), col, 30)}'
                f'<span class="xi-pts" style="background:{col};color:#070D1D">{fa(pl.get("pts", ""))}</span></div>'
                f'<div class="xi-name trunc">{esc(pl.get("name", ""))}</div>'
                f'<div class="xi-stat trunc">{fa(esc(pl.get("stat", "")))}</div></div>'
            )
        rows_html.append(f'<div class="xi-line">{"".join(chips)}</div>')

    return (
        '<div class="xm xi-pitch" style="flex:1">'
        '<div class="mh"><div class="fi gap10"><span class="mh-bar" style="background:#FBBF24"></span>'
        '<h3 class="mt">تیم منتخب هفته (برترین امتیاز فنی)</h3></div>'
        '<span class="mh-tag" style="color:#FDE047">تیم منتخب XI</span></div>'
        f'<div class="xi-board">{"".join(rows_html)}</div></div>'
    )


def render_mod_editorial_verdict(item: dict[str, Any]) -> str:
    txt = str(item.get("editorialVerdict") or "").strip()
    if not txt:
        return ""
    return (
        '<div class="xe verd-box">'
        '<div class="fi gap8" style="font-size:19px;font-weight:900;color:#FCD34D">'
        '<span>✦ جمع‌بندی تحریریه XGPedia</span></div>'
        f'<p class="verd-txt">{fa(esc(txt))}</p></div>'
    )


@with_sample_badge
def render_matchweek_wrapup_html(
    item: dict[str, Any],
    *,
    slide: str = "slide1",
    header_mode: str = "full",
    fmt: str = "4:5",
    theme: str = "classic",
    modules: list[dict[str, Any]] | None = None,
) -> str:
    """رندر ۱۰۰٪ آفلاین کارت اسلایدی و ماژولار «خلاصهٔ هفته + فرم در برابر جدول»."""
    w, h_px = WRAPUP_FORMATS.get(fmt, (1080, 1350))
    is_story = fmt == "9:16"
    is_wide = fmt == "16:9"
    pad_top, pad_bot = (139, 171) if is_story else ((22, 16) if is_wide else (24, 20))

    if modules is None:
        modules, _ = get_matchweek_wrapup_modules(item, slide)
    active = [m for m in modules if m.get("enabled")]

    render_map = {
        "awards_trio": render_mod_awards_trio,
        "form_vs_table": render_mod_form_vs_table,
        "xg_overunder": render_mod_xg_overunder,
        "attack_defense": render_mod_attack_defense,
        "totw_pitch": render_mod_totw_pitch,
        "editorial_verdict": render_mod_editorial_verdict,
    }
    blocks = []
    for m in active:
        fn = render_map.get(str(m.get("id") or ""))
        if fn:
            html_b = fn(item)
            if html_b:
                blocks.append(html_b)

    acc = "#FBBF24" if theme == "gold" else ("#38BDF8" if theme == "ucl" else "#E62E45")
    bg_hex = "#071122" if theme == "ucl" else "#0D1730"
    logo_uri = _brand_logo_data_uri()
    logo_html = (
        f'<img src="{logo_uri}" alt="XGPedia" style="height:44px;width:auto;display:block;flex-shrink:0"/>'
        if logo_uri
        else '<span class="fd" style="font-size:28px;font-weight:900"><span style="color:#E62E45">XG</span><span>Pedia</span></span>'
    )
    sl_lbl = next((sub for sid, _, sub, _ in WRAPUP_SLIDES if sid == slide), "خلاصهٔ هفته")
    comp_txt = esc(item.get("competition") or "لیگ برتر انگلیس")
    rnd_txt = fa(esc(item.get("round") or "خلاصهٔ هفته و قدرت فرم"))
    src_txt = esc(item.get("source") or "XGPedia")
    hdr_sub = "" if header_mode == "compact" else f'<div class="hdr-sub">{rnd_txt}</div>'

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl"><head><meta charset="UTF-8"><style>
{build_embedded_font_css()}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:{w}px;height:{h_px}px;overflow:hidden;background:{bg_hex};color:#F8FAFC;font-family:'Vazirmatn',sans-serif;font-feature-settings:"tnum";font-variant-numeric:tabular-nums}}
.fm{{font-family:'JetBrains Mono','Space Grotesk',monospace}} .fd{{font-family:'Space Grotesk','Vazirmatn',sans-serif}}
.fi{{display:flex;align-items:center}} .fc{{display:flex;align-items:center;justify-content:center}} .fbw{{display:flex;align-items:center;justify-content:space-between}} .fcol{{display:flex;flex-direction:column}}
.flex1{{flex:1}} .min0{{min-width:0;min-height:0}} .justify-center{{justify-content:center}}
.gap8{{gap:8px}} .gap10{{gap:10px}} .gap12{{gap:12px}} .gap14{{gap:14px}}
.trunc{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
#ea{{position:relative;width:{w}px;height:{h_px}px;background:{bg_hex};display:flex;flex-direction:column;justify-content:space-between;padding:{pad_top}px 0 {pad_bot}px 0;overflow:hidden}}
.bg-svg{{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0}}
.hdr{{position:relative;z-index:5;display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 36px 8px;flex-shrink:0}}
.hdr-pill{{display:inline-flex;align-items:center;gap:10px;padding:6px 18px;border-radius:999px;background:#152347eb;border:1.5px solid #ffffff30;font-size:22px;font-weight:900;color:#F8FAFC}}
.hdr-tag{{padding:5px 15px;border-radius:999px;background:{acc}2b;border:1.5px solid {acc}88;color:#fff;font-size:18px;font-weight:800}}
.hdr-sub{{font-size:19px;font-weight:700;color:#CBD5E1;margin-top:6px}}
.stage{{position:relative;z-index:5;flex:1;padding:8px 40px;display:flex;flex-direction:column;justify-content:space-between;gap:14px;overflow:hidden;min-height:0}}
.xm,.xe{{position:relative;border-radius:22px;padding:16px 20px;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;box-shadow:0 14px 36px -10px rgba(0,0,0,.62),inset 0 1px 0 rgba(255,255,255,.10)}}
.xm{{background:linear-gradient(165deg,#101d3be3,#091023f5);border:1.5px solid rgba(248,250,252,.15)}}
.xe{{background:linear-gradient(155deg,#122040ef,#081022f8);border:1.5px solid rgba(127,166,232,.28)}}
.mh{{display:flex;align-items:center;justify-content:space-between;gap:10px;padding-bottom:9px;margin-bottom:10px;border-bottom:1px solid rgba(255,255,255,.14);flex-shrink:0}}
.mh-bar{{width:7px;height:24px;border-radius:99px}}
.mt{{font-size:24px;font-weight:900;color:#fff}}
.mh-tag{{font-size:16px;font-weight:800;color:#CBD5E1}}
.aw-grid{{display:grid;gap:12px;flex-shrink:0}}
.aw-card{{border-radius:18px;padding:14px 16px;background:linear-gradient(160deg,#122142eb,#081024f6);border:1px solid rgba(255,255,255,.14)}}
.aw-lbl{{font-size:16px;font-weight:900}}
.aw-name{{font-size:23px;font-weight:900;color:#fff;line-height:1.15}}
.aw-val{{font-size:22px;font-weight:900;margin-top:2px}}
.aw-sub{{font-size:15.5px;font-weight:700;color:#CBD5E1;margin-top:8px}}
.ft-list{{display:flex;flex-direction:column;gap:8px;flex:1;justify-content:space-between}}
.ft-row{{display:grid;grid-template-columns:46px minmax(220px,1.3fr) auto 176px;align-items:center;gap:10px;padding:9px 14px;border-radius:14px;background:rgba(7,14,32,.86);border:1px solid rgba(255,255,255,.12)}}
.ft-rk{{width:38px;height:38px;border-radius:10px;background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.18);display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:900;color:#fff}}
.ft-name{{font-size:22px;font-weight:900;color:#fff;line-height:1.15}}
.ft-sub{{font-size:15.5px;font-weight:700;color:#CBD5E1;margin-top:2px}}
.ft-sub b{{color:#fff}}
.ft-dots{{display:flex;align-items:center;gap:5px}}
.fdot{{width:28px;height:28px;border-radius:8px;display:inline-flex;align-items:center;justify-content:center;font-family:'Space Grotesk',sans-serif;font-size:14px;font-weight:900}}
.fd-w{{background:rgba(16,185,129,.26);border:1px solid #34D399;color:#6EE7B7}}
.fd-d{{background:rgba(245,158,11,.24);border:1px solid #FBBF24;color:#FDE68A}}
.fd-l{{background:rgba(244,63,94,.24);border:1px solid #FB7185;color:#FDA4AF}}
.ft-end{{display:flex;flex-direction:column;align-items:flex-end;gap:4px}}
.ft-fpts{{font-size:16.5px;font-weight:900;color:#F8FAFC}}
.rk-d{{padding:2px 10px;border-radius:999px;font-size:14.5px;font-weight:900}}
.rk-d.up{{background:rgba(16,185,129,.22);color:#6EE7B7;border:1px solid rgba(52,211,153,.45)}}
.rk-d.dn{{background:rgba(244,63,94,.22);color:#FDA4AF;border:1px solid rgba(251,113,133,.45)}}
.rk-d.eq{{background:rgba(255,255,255,.10);color:#CBD5E1}}
.ou-grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;flex:1;min-height:0}}
.ou-row{{display:flex;flex-direction:column;gap:8px;padding:12px 14px;border-radius:14px;background:rgba(6,12,28,.85);border:1px solid rgba(255,255,255,.10)}}
.ou-name{{font-size:21px;font-weight:900;color:#fff}}
.ou-sub{{font-size:15.5px;font-weight:700;color:#CBD5E1;margin-top:2px}}
.ou-delta{{padding:4px 10px;border-radius:10px;border:1px solid;font-size:19px;font-weight:900;flex-shrink:0}}
.ou-track{{height:9px;border-radius:99px;background:rgba(255,255,255,.10);overflow:hidden}}
.ou-fill{{height:100%;border-radius:99px}}
.ad-grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;flex:1}}
.xi-pitch{{background:radial-gradient(circle at 50% 45%,rgba(16,185,129,.16),rgba(7,15,34,.96) 72%)!important}}
.xi-board{{flex:1;display:flex;flex-direction:column;justify-content:space-around;gap:10px;padding:6px 0}}
.xi-line{{display:flex;align-items:center;justify-content:center;gap:12px}}
.xi-node{{flex:1;max-width:225px;border-radius:14px;padding:10px 12px;background:rgba(7,14,32,.92);border:1.5px solid;text-align:center}}
.xi-pts{{padding:2px 9px;border-radius:8px;font-size:16px;font-weight:900}}
.xi-name{{font-size:19px;font-weight:900;color:#fff;margin-top:6px}}
.xi-stat{{font-size:14.5px;font-weight:700;color:#CBD5E1;margin-top:2px}}
.verd-box{{border-right:5px solid {acc};gap:6px;flex-shrink:0}}
.verd-txt{{font-size:20px;font-weight:700;color:#F8FAFC;line-height:1.55}}
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
      <pattern id="mwGrid" width="54" height="54" patternUnits="userSpaceOnUse"><path d="M54 0H0v54" stroke="#F8FAFC" stroke-opacity=".05"/></pattern>
      <radialGradient id="mwGlow" cx="50%" cy="22%" r="55%"><stop offset="0" stop-color="{acc}" stop-opacity=".22"/><stop offset="1" stop-color="{acc}" stop-opacity="0"/></radialGradient>
    </defs>
    <rect width="100%" height="100%" fill="url(#mwGrid)"/>
    <rect width="100%" height="100%" fill="url(#mwGlow)"/>
    <rect x="12" y="12" width="{w - 24}" height="{h_px - 24}" rx="18" stroke="#F8FAFC" stroke-opacity=".12" stroke-width="1.5"/>
    <path d="M24 44V24H44M{w - 24} 44V24H{w - 44}M24 {h_px - 44}V{h_px - 24}H44M{w - 24} {h_px - 44}V{h_px - 24}H{w - 44}" stroke="#E62E45" stroke-width="2.4" stroke-linecap="square"/>
  </svg>
  <header class="hdr">
    <div class="min0">
      <div class="fi gap10" style="flex-wrap:wrap">
        <span class="hdr-pill">📊 {comp_txt}</span>
        <span class="hdr-tag">{esc(sl_lbl)}</span>
      </div>
      {hdr_sub}
    </div>
    {logo_html}
  </header>
  <main class="stage">{"".join(blocks)}</main>
  <footer class="ftr">
    <div class="ftr-l"><span class="ftr-dot"></span><span class="ftr-tk">{comp_txt} • {esc(sl_lbl)} • XGPedia</span></div>
    <div class="ftr-r fm" dir="ltr"><b>@XGPedia</b><span>|</span><span>{src_txt}</span></div>
  </footer>
</div></body></html>"""
