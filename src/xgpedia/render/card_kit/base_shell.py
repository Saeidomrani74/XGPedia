"""قالب پایهٔ یکپارچهٔ XGPedia بر اساس هویت بصری `Pre-Match.html`.

همهٔ کارت‌ها (پیش‌ازبازی، پس‌ازبازی و کارت‌های آینده) از همین پوستهٔ واحد استفاده می‌کنند:
  - پس‌زمینهٔ سرمه‌ای عمیق `#0D1730`، نور محیطی رنگ دو تیم، خطوط زمین SVG، صلیب گوشه‌ها و scanlines
  - سرصفحهٔ ۲ خطی کامل:
      خط ۱: نام لیگ + قرص قرمز هفته/عنوان مسابقه
      خط ۲: تاریخ و ساعت تهران + نام ورزشگاه + قرص سبز پخش زنده (در صورت وجود)
      سمت چپ: نشان رسمی XGPedia
  - بخش Hero (حالت کامل `full` یا فشرده `compact`) برای پیش‌ازبازی و پس‌ازبازی
  - گرید ۲ ستونه `#mg` با تضمین ریاضی عدم بریدگی SVG/متن و حذف نیم‌فضای خالی (orphan half-width)
  - پانویس یکپارچه با تگ لیگ/فصل/هفته + `@XGPedia` + منبع داده
  - ۱۰۰٪ خودبسنده با فونت‌های محلی `brand/fonts/` (بدون هیچ وابستگی به اینترنت یا CDN)
"""
from __future__ import annotations

from typing import Any

from src.xgpedia.render.card_kit.helpers import (
    contrast_ink,
    esc,
    f1,
    f2,
    fa,
    team_crest_svg_or_img,
)
from src.xgpedia.render.card_kit.modules import MODULE_REGISTRY, render_module_html
from src.xgpedia.render.studio_engine import FORMATS, build_embedded_font_css


def _fix_orphan_spans(mods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """تضمین ریاضی نبود نیم‌فضای خالی: هر ماژول نیم‌عرض بدون جفت، خودکار تمام‌عرض می‌شود."""
    enabled = []
    for m in mods:
        if not m.get("enabled"):
            continue
        spec = MODULE_REGISTRY.get(m["id"])
        if spec is None:
            continue
        span = "half" if (m.get("span") == "half" and spec.can_half) else "full"
        enabled.append({"id": m["id"], "enabled": True, "span": span})
    i = 0
    while i < len(enabled):
        if enabled[i]["span"] == "half":
            if i + 1 < len(enabled) and enabled[i + 1]["span"] == "half":
                i += 2
                continue
            enabled[i]["span"] = "full"
        i += 1
    return enabled


def _prob_capsule(m: dict[str, Any], hc: str, ac: str, compact: bool = False) -> str:
    ph, pd, pa = int(m.get("probHome") or 0), int(m.get("probDraw") or 0), int(m.get("probAway") or 0)
    mn = 12 if compact else 11
    return (
        f'<div class="pc{" pcc" if compact else ""}">'
        f'<div class="ps" style="width:{ph}%;background:{hc};color:{contrast_ink(hc)}">{fa(ph) + "٪" if ph >= mn else ""}</div>'
        f'<div class="ps" style="width:{pd}%;background:#475569;color:#fff">{fa(pd) + "٪" if pd >= mn else ""}</div>'
        f'<div class="ps" style="width:{pa}%;background:{ac};color:{contrast_ink(ac)}">{fa(pa) + "٪" if pa >= mn else ""}</div>'
        f'</div>'
    )


def _render_pre_hero(payload: dict[str, Any], fmt: str, header_mode: str) -> str:
    m = payload["match"]
    h, a = m["home"], m["away"]
    hc, ac = h["color"], a["color"]
    has_probs = bool(payload.get("hasProbs"))
    h_xg, a_xg = float(h.get("xg") or 0), float(a.get("xg") or 0)
    ph, pd, pa = int(m.get("probHome") or 0), int(m.get("probDraw") or 0), int(m.get("probAway") or 0)

    if header_mode == "compact":
        sz = 64 if fmt == "16:9" else 74
        xg_box = (
            f'<div class="hxc-xg"><span style="color:{hc}">{fa(f2(h_xg))}</span>'
            f'<span class="hxc-xgl fm">xG</span><span style="color:{ac}">{fa(f2(a_xg))}</span></div>'
            if has_probs
            else ""
        )
        cap_html = _prob_capsule(m, hc, ac, compact=True) if has_probs else ""
        return (
            f'<div class="hero-compact">'
            f'<div class="hc-grid">'
            f'<div class="hc-side">{team_crest_svg_or_img(h, "h", sz)}<div class="hc-meta"><div class="hc-name">{esc(h["name"])}</div><div class="hc-role" style="color:{hc}">میزبان</div></div></div>'
            f'<div class="hc-mid"><div class="hc-vs fd">VS</div>{xg_box}</div>'
            f'<div class="hc-side hc-away"><div class="hc-meta hc-meta-l"><div class="hc-name">{esc(a["name"])}</div><div class="hc-role" style="color:{ac}">میهمان</div></div>{team_crest_svg_or_img(a, "a", sz)}</div>'
            f'</div>{cap_html}</div>'
        )

    is_wide = fmt == "16:9"
    cs = 132 if is_wide else 148

    def form_html(arr: list[str], dr: str) -> str:
        if not arr:
            return ""
        dots = "".join(
            f'<span class="fdt f{c if c in "WDL" else "D"}{" fl" if i == len(arr) - 1 else ""}">{c if c in "WDL" else "D"}</span>'
            for i, c in enumerate(arr[-5:])
        )
        return f'<div dir="{dr}" class="form-row">{dots}</div>'

    def team_col(tm: dict[str, Any], side: str, dr: str) -> str:
        sub = f'<p class="team-sub">{esc(tm.get("sub"))}</p>' if tm.get("sub") else ""
        return (
            f'<div class="team-col">'
            f'<div class="crest-wrap">{team_crest_svg_or_img(tm, side, cs)}</div>'
            f'<div class="team-name">{esc(tm["name"])}</div>'
            f'{sub}{form_html(tm.get("form") or [], dr)}'
            f'</div>'
        )

    xh = ph * 0.03 + pd * 0.01
    xa = pa * 0.03 + pd * 0.01
    xg_hub = (
        f'<div class="hx-box">'
        f'<div class="hx-top"><span class="hx-val" style="color:{hc}">{fa(f2(h_xg))}</span>'
        f'<div class="hx-mid"><span class="hx-lbl fm">xG</span><span class="hx-tot fm">{fa(f2(h_xg + a_xg))}</span></div>'
        f'<span class="hx-val" style="color:{ac}">{fa(f2(a_xg))}</span></div>'
        f'<div class="hx-bot"><span class="hx-xp">{fa(f2(xh))}</span><span class="hx-xpl fm">xPts</span><span class="hx-xp">{fa(f2(xa))}</span></div>'
        f'</div>'
        if has_probs
        else ""
    )

    odds_block = ""
    if has_probs:
        od = lambda p: fa(f2(100.0 / max(1, p)))
        odds_block = (
            f'<div class="prob-wrap">{_prob_capsule(m, hc, ac, compact=False)}'
            f'<div class="odds-row">'
            f'<div class="odd-item"><span class="odd-lbl">ضریب منصفانه میزبان</span><span class="odd-val" style="color:{hc}">{od(ph)}</span></div>'
            f'<div class="odd-item"><span class="odd-lbl">مساوی</span><span class="odd-val">{od(pd)}</span></div>'
            f'<div class="odd-item"><span class="odd-lbl">ضریب منصفانه میهمان</span><span class="odd-val" style="color:{ac}">{od(pa)}</span></div>'
            f'</div></div>'
        )

    return (
        f'<div class="hero-full">'
        f'<div class="hero-grid">'
        f'{team_col(h, "h", "rtl")}'
        f'<div class="vs-col">'
        f'<div class="vs-stack"><div class="vt"></div><div class="vs-gem"><div class="vs-sq"></div><span class="vs-txt fd">VS</span></div><div class="vb"></div></div>'
        f'{xg_hub}'
        f'</div>'
        f'{team_col(a, "a", "ltr")}'
        f'</div>{odds_block}</div>'
    )


def _render_post_hero(payload: dict[str, Any], fmt: str, header_mode: str) -> str:
    m = payload["match"]
    h, a = m["home"], m["away"]
    hc, ac = h["color"], a["color"]
    has_probs = bool(payload.get("hasProbs"))
    h_xg, a_xg = float(h.get("xg") or 0), float(a.get("xg") or 0)
    sh, sa_ = int(m.get("scoreHome") or 0), int(m.get("scoreAway") or 0)
    ph, pd, pa = int(m.get("probHome") or 0), int(m.get("probDraw") or 0), int(m.get("probAway") or 0)

    if header_mode == "compact":
        sz = 64 if fmt == "16:9" else 74
        cap_html = _prob_capsule(m, hc, ac, compact=True) if has_probs else ""
        return (
            f'<div class="hero-compact">'
            f'<div class="hc-grid">'
            f'<div class="hc-side">{team_crest_svg_or_img(h, "h", sz)}<div class="hc-meta"><div class="hc-name">{esc(h["name"])}</div><div class="hc-role" style="color:{hc}">میزبان</div></div></div>'
            f'<div class="hc-mid"><div class="pm-cscore"><span>{fa(sh)}</span><span class="pm-colon">:</span><span>{fa(sa_)}</span></div>'
            f'{"<div class=hxc-xg><span style=color:" + hc + ">" + fa(f2(h_xg)) + "</span><span class=hxc-xgl>xG</span><span style=color:" + ac + ">" + fa(f2(a_xg)) + "</span></div>" if has_probs else ""}</div>'
            f'<div class="hc-side hc-away"><div class="hc-meta hc-meta-l"><div class="hc-name">{esc(a["name"])}</div><div class="hc-role" style="color:{ac}">میهمان</div></div>{team_crest_svg_or_img(a, "a", sz)}</div>'
            f'</div>{cap_html}</div>'
        )

    is_wide = fmt == "16:9"
    cs = 124 if is_wide else 142
    xh = ph * 0.03 + pd * 0.01
    xa = pa * 0.03 + pd * 0.01

    def team_col(tm: dict[str, Any], side: str, score: int) -> str:
        sub = f'<p class="team-sub">{esc(tm.get("sub"))}</p>' if tm.get("sub") else ""
        sc_txt = (tm.get("scorersText") or "").strip()
        sc_pill = f'<div class="sc-pill">⚽ {fa(esc(sc_txt))}</div>' if sc_txt else ("<div class=sc-empty>بدون گل زده</div>" if score == 0 else "")
        return (
            f'<div class="team-col">'
            f'<div class="crest-wrap">{team_crest_svg_or_img(tm, side, cs)}</div>'
            f'<div class="team-name">{esc(tm["name"])}</div>'
            f'{sub}{sc_pill}</div>'
        )

    xg_hub = (
        f'<div class="hx-box">'
        f'<div class="hx-top"><span class="hx-val" style="color:{hc}">{fa(f2(h_xg))}</span>'
        f'<div class="hx-mid"><span class="hx-lbl fm">xG</span><span class="hx-tot fm">{fa(f2(h_xg + a_xg))}</span></div>'
        f'<span class="hx-val" style="color:{ac}">{fa(f2(a_xg))}</span></div>'
        f'<div class="hx-bot"><span class="hx-xp">{fa(f2(xh))}</span><span class="hx-xpl fm">xPts</span><span class="hx-xp">{fa(f2(xa))}</span></div>'
        f'</div>'
        if has_probs
        else ""
    )

    cap_block = ""
    if has_probs:
        dh, da = sh - h_xg, sa_ - a_xg
        df = h_xg - a_xg
        if sh == sa_:
            vt = "تساوی عادلانه آماری" if abs(df) < 0.35 else ("تساوی با برتری xG میزبان" if df > 0 else "تساوی با برتری xG میهمان")
        elif sh > sa_:
            vt = "برتری شایسته میزبان" if df >= 0.45 else ("برد کلینیکال میزبان" if df >= -0.25 else "برد خلاف جریان xG")
        else:
            vt = "برتری شایسته میهمان" if df <= -0.45 else ("برد کلینیکال میهمان" if df <= 0.25 else "برد خلاف جریان xG")
        ep = lambda v: f'<span dir="ltr" class="ep-pill{" ep-pos" if v >= 0 else " ep-neg"}">{"+" if v >= 0 else "-"}{fa(f2(abs(v)))}</span>'
        cap_block = (
            f'<div class="prob-wrap">{_prob_capsule(m, hc, ac, compact=False)}'
            f'<div class="odds-row">'
            f'<div class="odd-item"><span class="odd-lbl">بهره‌وری گل</span>{ep(dh)}</div>'
            f'<div class="verdict-pill">● {vt}</div>'
            f'<div class="odd-item"><span class="odd-lbl">بهره‌وری گل</span>{ep(da)}</div>'
            f'</div></div>'
        )

    return (
        f'<div class="hero-full">'
        f'<div class="hero-grid">'
        f'{team_col(h, "h", sh)}'
        f'<div class="vs-col">'
        f'<div class="pm-score-row">'
        f'<div class="pm-sc"><span class="pm-sc-num">{fa(sh)}</span><span class="pm-sc-bar" style="background:{hc}"></span></div>'
        f'<div class="pm-dots"><i></i><i class="pm-dot2"></i></div>'
        f'<div class="pm-sc"><span class="pm-sc-num">{fa(sa_)}</span><span class="pm-sc-bar" style="background:{ac}"></span></div>'
        f'</div>{xg_hub}</div>'
        f'{team_col(a, "a", sa_)}'
        f'</div>{cap_block}</div>'
    )


def _unified_css(w: int, h: int, fmt: str) -> str:
    pad_top, pad_bot = (135, 171) if fmt == "9:16" else ((18, 16) if fmt == "16:9" else (20, 20))
    is_wide = fmt == "16:9"
    return f"""
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{w}px;height:{h}px;overflow:hidden;background:#0D1730;color:#F8FAFC;
  font-family:'Vazirmatn',system-ui,sans-serif;font-feature-settings:"tnum";font-variant-numeric:tabular-nums}}
.fm{{font-family:'JetBrains Mono','Space Grotesk',monospace}}
.fd{{font-family:'Space Grotesk',sans-serif}}
#ea{{position:relative;width:{w}px;height:{h}px;background:#0D1730;overflow:hidden;
  display:flex;flex-direction:column;justify-content:space-between;padding:{pad_top}px 0 {pad_bot}px}}
.bg-layer{{position:absolute;inset:0;pointer-events:none;z-index:0}}
.scanlines{{position:absolute;inset:0;pointer-events:none;z-index:0;
  background:repeating-linear-gradient(to bottom,rgba(255,255,255,0.015) 0 1px,transparent 1px 4px)}}

/* ─── Header (2-Line Full Identity) ─── */
#cm{{position:relative;z-index:10;padding:8px 44px 8px;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-shrink:0}}
.hd-right{{display:flex;flex-direction:column;align-items:flex-start;gap:10px;min-width:0;flex:1}}
.hd-line1,.hd-line2{{display:flex;align-items:center;flex-wrap:wrap;gap:12px}}
.pill-league{{display:inline-flex;align-items:center;gap:10px;padding:6px 20px;border-radius:999px;
  background:rgba(21,35,71,0.92);border:1.5px solid rgba(255,255,255,0.18);font-size:24px;font-weight:900;color:#F8FAFC}}
.pill-round{{display:inline-flex;align-items:center;padding:6px 20px;border-radius:999px;
  background:rgba(230,46,69,0.18);border:1.5px solid rgba(230,46,69,0.52);color:#FF6B7F;font-size:22px;font-weight:800}}
.hd-line2{{font-size:21px;font-weight:700;color:#F1F5F9}}
.hd-sep{{color:#64748B}}
.hd-stadium{{display:inline-flex;align-items:center;gap:8px;color:#FFFFFF}}
.pill-bcast{{display:inline-flex;align-items:center;gap:8px;padding:3px 14px;border-radius:999px;
  background:rgba(16,185,129,0.18);border:1.5px solid rgba(16,185,129,0.46);color:#34D399;font-size:19px;font-weight:800}}
#bl{{display:flex;align-items:center;gap:12px;flex-shrink:0}}
.bl-img{{height:58px;width:auto;display:block;object-fit:contain;filter:drop-shadow(0 4px 12px rgba(0,0,0,0.35))}}
.bl-word{{font-size:34px;font-weight:800;line-height:1;letter-spacing:-0.02em}}

/* ─── Body Layout ─── */
#cmb{{position:relative;z-index:10;flex:1 1 0%;min-height:0;overflow:hidden;
  padding:8px 40px;{"display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:28px;align-items:stretch;" if is_wide else "display:flex;flex-direction:column;gap:14px;"}}}
#hs{{{"grid-column:span 5;display:flex;flex-direction:column;justify-content:center;border-left:1px solid rgba(255,255,255,0.12);padding-left:24px;min-width:0;" if is_wide else "flex-shrink:0;"}}}
#mg{{{"grid-column:span 7;" if is_wide else "flex:1 1 0%;"}min-height:0;min-width:0;display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));grid-auto-rows:minmax(0,1fr);gap:14px;overflow:hidden}}

/* ─── Hero (Full & Compact) ─── */
.hero-full{{display:flex;flex-direction:column;gap:14px}}
.hero-grid{{display:grid;grid-template-columns:4fr 3fr 4fr;align-items:center;gap:8px}}
.team-col{{display:flex;flex-direction:column;align-items:center;text-align:center;min-width:0}}
.crest-wrap{{margin-bottom:8px;display:flex;align-items:center;justify-content:center}}
.team-name{{font-size:{40 if is_wide else 46}px;font-weight:900;color:#fff;line-height:1.08;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.team-sub{{font-size:19px;font-weight:700;color:#CBD5E1;margin-top:4px;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.form-row{{display:flex;align-items:center;gap:7px;margin-top:10px}}
.fdt{{width:{38 if is_wide else 44}px;height:{30 if is_wide else 34}px;border-radius:10px;display:inline-flex;align-items:center;justify-content:center;
  font-family:'Space Grotesk','JetBrains Mono',sans-serif;font-size:{16 if is_wide else 18}px;font-weight:800;border:1.5px solid transparent}}
.fdt.fl{{border-width:2.5px}}
.fW{{background:rgba(16,185,129,0.15);color:#34D399;border-color:rgba(46,211,140,0.28)}}.fW.fl{{border-color:#34D399;box-shadow:0 0 12px rgba(52,211,153,0.35)}}
.fD{{background:rgba(245,158,11,0.16);color:#F5B041;border-color:rgba(245,166,35,0.3)}}.fD.fl{{border-color:#FBBF24;color:#FBBF24}}
.fL{{background:rgba(230,46,69,0.17);color:#F43F5E;border-color:rgba(244,63,94,0.3)}}.fL.fl{{border-color:#F43F5E}}

.vs-col{{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px}}
.vs-stack{{display:flex;flex-direction:column;align-items:center}}
.vt,.vb{{width:2px;height:38px}}.vt{{background:linear-gradient(to bottom,transparent,#E62E45)}}.vb{{background:linear-gradient(to top,transparent,#E62E45)}}
.vs-gem{{position:relative;display:flex;align-items:center;justify-content:center}}
.vs-sq{{width:76px;height:76px;border-radius:20px;transform:rotate(45deg);background:#E62E45;border:2px solid rgba(255,255,255,0.3);box-shadow:0 0 36px rgba(230,46,69,0.55)}}
.vs-txt{{position:absolute;font-size:32px;font-weight:800;color:#fff}}

.hx-box{{width:100%;padding:12px 14px;border-radius:20px;background:rgba(9,18,38,0.92);border:1.5px solid rgba(255,255,255,0.14);
  display:flex;flex-direction:column;align-items:center;gap:8px;box-shadow:0 12px 26px rgba(0,0,0,0.45)}}
.hx-top{{display:flex;align-items:center;justify-content:center;gap:12px;width:100%}}
.hx-val{{font-size:30px;font-weight:900;line-height:1}}
.hx-mid{{display:flex;flex-direction:column;align-items:center;line-height:1}}
.hx-lbl{{font-size:12px;font-weight:800;color:#94A3B8;margin-bottom:2px}}.hx-tot{{font-size:16px;font-weight:900;color:#6EE7B7}}
.hx-bot{{width:100%;padding-top:8px;border-top:1px solid rgba(255,255,255,0.12);display:flex;align-items:center;justify-content:center;gap:12px}}
.hx-xp{{font-size:18px;font-weight:900;color:#fff}}.hx-xpl{{font-size:14px;font-weight:800;color:#94A3B8}}

.prob-wrap{{display:flex;flex-direction:column;gap:8px}}
.pc{{width:100%;height:{46 if is_wide else 50}px;border-radius:999px;overflow:hidden;display:flex;background:rgba(15,23,42,0.92);border:2px solid rgba(255,255,255,0.18)}}
.pc.pcc{{height:34px;border-width:1.5px}}.pc.pcc .ps{{font-size:18px}}
.ps{{height:100%;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:{22 if is_wide else 25}px;white-space:nowrap}}
.odds-row{{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:0 4px}}
.odd-item{{display:flex;align-items:center;gap:8px;white-space:nowrap}}
.odd-lbl{{font-size:{16 if is_wide else 19}px;font-weight:700;color:#CBD5E1}}
.odd-val{{font-size:{20 if is_wide else 23}px;font-weight:900;color:#fff}}

/* Compact Hero */
.hero-compact{{border-radius:22px;background:rgba(11,22,47,0.92);border:1.5px solid rgba(255,255,255,0.15);padding:14px 22px;display:flex;flex-direction:column;gap:12px}}
.hc-grid{{display:grid;grid-template-columns:4fr 3fr 4fr;align-items:center;gap:12px}}
.hc-side{{display:flex;align-items:center;gap:14px;min-width:0}}.hc-away{{justify-content:flex-end}}
.hc-meta{{min-width:0}}.hc-meta-l{{text-align:left}}
.hc-name{{font-size:30px;font-weight:900;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.hc-role{{font-size:18px;font-weight:700}}
.hc-mid{{display:flex;flex-direction:column;align-items:center;gap:6px}}
.hc-vs{{padding:4px 16px;border-radius:999px;background:#E62E45;color:#fff;font-size:18px;font-weight:800}}
.hxc-xg{{display:flex;align-items:center;gap:10px;padding:4px 14px;border-radius:14px;background:#060D1E;border:1px solid rgba(255,255,255,0.14);font-size:24px;font-weight:900}}
.hxc-xgl{{font-size:15px;color:#94A3B8;font-weight:800}}

/* Post-Match Hero additions */
.pm-score-row{{display:flex;align-items:center;justify-content:center;gap:18px}}
.pm-sc{{display:flex;flex-direction:column;align-items:center}}
.pm-sc-num{{font-size:{92 if is_wide else 112}px;font-weight:900;line-height:0.86;color:#fff}}
.pm-sc-bar{{width:48px;height:7px;border-radius:99px;margin-top:8px}}
.pm-dots{{display:flex;flex-direction:column;gap:12px;padding-bottom:10px}}
.pm-dots i{{width:12px;height:12px;border-radius:99px;background:#E62E45;display:block}}.pm-dots .pm-dot2{{background:rgba(255,255,255,0.4)}}
.pm-cscore{{font-size:44px;font-weight:900;color:#fff;display:flex;align-items:center;gap:10px;line-height:1}}
.pm-colon{{color:#E62E45}}
.sc-pill{{margin-top:8px;padding:4px 12px;border-radius:10px;background:rgba(15,23,42,0.88);border:1px solid rgba(255,255,255,0.12);font-size:15px;font-weight:800;color:#F1F5F9;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.sc-empty{{margin-top:6px;font-size:14px;color:#94A3B8;font-weight:600}}
.ep-pill{{padding:2px 10px;border-radius:10px;font-size:18px;font-weight:900;border:1px solid}}
.ep-pos{{background:rgba(16,185,129,0.16);border-color:rgba(52,211,153,0.45);color:#34D399}}
.ep-neg{{background:rgba(244,63,94,0.16);border-color:rgba(251,113,133,0.45);color:#FB7185}}
.verdict-pill{{padding:4px 14px;border-radius:999px;background:rgba(56,189,248,0.15);border:1px solid rgba(56,189,248,0.45);color:#7DD3FC;font-size:17px;font-weight:900;white-space:nowrap}}

/* ─── Module Cards (Unified Full & Half Width — ZERO Clipping) ─── */
.xm{{position:relative;border-radius:22px;background:linear-gradient(165deg,rgba(16,29,59,0.88),rgba(9,16,35,0.96));
  border:1.5px solid rgba(248,250,252,0.15);padding:14px 22px 16px;
  display:flex;flex-direction:column;min-height:0;min-width:0;overflow:hidden;
  box-shadow:0 14px 34px -10px rgba(0,0,0,0.58),inset 0 1px 0 rgba(255,255,255,0.09)}}
.mod-full{{grid-column:1 / -1}}
.mod-half{{grid-column:span 1;padding:12px 16px 14px;border-radius:18px}}
.mh{{display:flex;align-items:center;justify-content:space-between;gap:10px;padding-bottom:8px;margin-bottom:8px;
  border-bottom:1px solid rgba(255,255,255,0.12);flex-shrink:0}}
.mh-left{{display:flex;align-items:center;gap:10px;min-width:0}}
.mh-bar{{width:7px;height:24px;border-radius:99px;flex-shrink:0}}
.mh-title{{font-size:25px;font-weight:900;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.mh-half .mh-title{{font-size:19px}}.mh-half .mh-bar{{width:6px;height:19px}}
.mh-right{{flex-shrink:0}}
.mod-tag{{font-family:'JetBrains Mono','Space Grotesk',monospace;font-size:15px;font-weight:800;color:#CBD5E1;
  background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);padding:2px 9px;border-radius:7px}}
.mh-half .mod-tag{{font-size:12px;padding:1px 6px}}
.mod-legend{{display:flex;align-items:center;gap:14px;font-size:18px;font-weight:800;color:#F1F5F9}}
.mod-legend-half{{gap:8px;font-size:13px}}
.leg-item{{display:inline-flex;align-items:center;gap:6px;white-space:nowrap}}
.leg-dot{{width:12px;height:12px;border-radius:99px;display:inline-block;flex-shrink:0}}
.mod-legend-half .leg-dot{{width:9px;height:9px}}

/* SVG Container: STRICT aspect-ratio fit — NEVER clips top/bottom/sides */
.mod-body-svg{{flex:1 1 0%;min-height:0;width:100%;display:flex;align-items:center;justify-content:center;overflow:hidden}}
.fit-svg{{width:100%;height:100%;max-width:100%;max-height:100%;display:block}}
.avg-pills{{display:flex;align-items:center;gap:8px;font-size:20px;font-weight:900}}
.mod-half .avg-pills{{font-size:15px;gap:5px}}
.avg-pill{{padding:2px 10px;border-radius:9px;background:rgba(255,255,255,0.07)}}.avg-sep{{color:#64748B}}

/* Stats Module */
.st-list{{flex:1 1 0%;min-height:0;display:flex;flex-direction:column;justify-content:center;gap:12px}}
.mod-half .st-list{{gap:9px}}
.st-row{{display:flex;flex-direction:column;gap:6px}}
.st-vals{{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:8px}}
.st-num{{font-size:28px;font-weight:900;line-height:1}}.st-h{{text-align:right}}.st-a{{text-align:left}}
.st-lbl{{font-size:20px;font-weight:800;color:#F1F5F9;text-align:center;white-space:nowrap}}
.mod-half .st-num{{font-size:20px}}.mod-half .st-lbl{{font-size:14px}}
.st-bars{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
.ct{{height:12px;background:rgba(255,255,255,0.1);overflow:hidden;display:flex;align-items:center}}
.mod-half .ct{{height:9px}}
.ct.hs{{justify-content:flex-end;border-radius:0 99px 99px 0}}.ch{{height:100%;border-radius:0 99px 99px 0}}
.ct.as{{justify-content:flex-start;border-radius:99px 0 0 99px}}.ca{{height:100%;border-radius:99px 0 0 99px}}

/* Key Duel Module */
.kd-body{{flex:1 1 0%;min-height:0;display:flex;align-items:center;justify-content:center;gap:12px}}
.kd-row{{display:grid;grid-template-columns:5fr 1fr 5fr;align-items:stretch;width:100%}}
.kd-stack{{flex-direction:column;align-items:stretch;gap:8px}}
.kd-card{{padding:14px 18px;border-radius:18px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.14);
  display:flex;flex-direction:column;justify-content:space-between;gap:10px;min-width:0}}
.mod-half .kd-card{{padding:10px 12px;border-radius:14px;gap:6px}}
.kd-top{{display:flex;align-items:center;justify-content:space-between;gap:8px}}
.kd-name{{font-size:24px;font-weight:900;color:#fff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.kd-pos{{font-size:17px;font-weight:700;padding:3px 10px;border-radius:10px;background:rgba(255,255,255,0.11);color:#F1F5F9;flex-shrink:0}}
.kd-stats{{padding-top:8px;border-top:1px solid rgba(255,255,255,0.12);display:flex;align-items:center;justify-content:space-between;gap:8px}}
.kd-s1{{font-size:22px;font-weight:900}}.kd-s2{{font-size:19px;font-weight:700;color:#E2E8F0}}
.mod-half .kd-name{{font-size:18px}}.mod-half .kd-pos{{font-size:13px;padding:2px 7px}}
.mod-half .kd-s1{{font-size:16px}}.mod-half .kd-s2{{font-size:14px}}
.kd-vs-wrap{{display:flex;align-items:center;justify-content:center}}
.kd-vs{{width:50px;height:50px;border-radius:14px;background:rgba(230,46,69,0.24);border:2px solid rgba(230,46,69,0.6);
  display:flex;align-items:center;justify-content:center;font-family:'Space Grotesk',sans-serif;font-size:20px;font-weight:800;color:#FF6B7F}}

/* Poisson Matrix Module */
.pm-wrap{{flex:1 1 0%;min-height:0;display:flex;flex-direction:column;gap:8px}}
.pm-tops{{display:flex;gap:8px;flex-shrink:0}}
.pm-top{{flex:1;padding:6px 12px;border-radius:12px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.14);
  display:flex;align-items:center;justify-content:space-between;gap:6px}}
.pm-top-1{{background:rgba(16,185,129,0.2);border-color:rgba(52,211,153,0.5)}}
.pm-top-sc{{font-size:22px;font-weight:900;color:#fff}}.pm-top-pc{{font-size:18px;font-weight:800;color:#6EE7B7}}
.mod-half .pm-top-sc{{font-size:17px}}.mod-half .pm-top-pc{{font-size:14px}}
.pm-grid{{flex:1 1 0%;min-height:0;display:grid;grid-template-columns:repeat(6,minmax(0,1fr));grid-template-rows:repeat(6,minmax(0,1fr));gap:5px}}
.pm-hdr{{display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:900}}
.pm-corner{{font-size:13px;color:#CBD5E1}}
.pm-cell{{display:flex;align-items:center;justify-content:center;border-radius:9px;border:1px solid rgba(255,255,255,0.12);
  font-size:17px;font-weight:900;color:#fff;white-space:nowrap}}
.mod-half .pm-hdr{{font-size:14px}}.mod-half .pm-corner{{font-size:10px}}.mod-half .pm-cell{{font-size:13px;border-radius:7px}}

/* Signals (+EV) Module — فشرده، خوانا و بدون بریدگی */
.el{{flex:1 1 0%;min-height:0;display:flex;flex-direction:column;justify-content:center;gap:6px}}
.er{{display:grid;grid-template-columns:minmax(0,.95fr) minmax(0,1.45fr) auto;align-items:center;gap:10px;
  padding:6px 12px;border-radius:12px;background:rgba(22,27,46,0.86);border:1px solid rgba(255,255,255,0.1)}}
.er-info{{min-width:0;text-align:right}}
.et{{font-size:16px;font-weight:900;line-height:1.2;color:#F8FAFC;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.em{{font-size:12px;font-weight:600;color:#94A3B8;margin-top:1px;white-space:nowrap}}
.ebc{{display:flex;flex-direction:column;gap:4px;min-width:0}}
.ebr{{display:flex;align-items:center;gap:7px}}
.ebl{{width:76px;font-size:11px;font-weight:700;text-align:right;flex-shrink:0;white-space:nowrap}}
.ebl-m{{color:#CBD5E1}}.ebl-k{{color:#94A3B8}}
.ebt{{flex:1;height:13px;border-radius:99px;background:#262B3D;overflow:hidden;direction:ltr;display:flex;align-items:center}}
.efm,.efk{{height:100%;border-radius:99px;display:flex;align-items:center;justify-content:flex-end;flex-shrink:0}}
.efm{{background:linear-gradient(90deg,#2EB7EB,#40C8F5)}}.efk{{background:#696F7D}}
.evv{{font-size:10.5px;font-weight:900;white-space:nowrap}}.eim{{color:#04111F;padding-right:5px}}.eom{{color:#7DD3FC;padding-left:5px}}
.eik{{color:#fff;padding-right:5px}}.eok{{color:#CBD5E1;padding-left:5px}}
.epw{{display:flex;flex-direction:column;align-items:center;min-width:106px;flex-shrink:0}}
.epb{{width:100%;padding:3px 8px;border-radius:8px;display:inline-flex;align-items:baseline;justify-content:center;gap:4px;
  font-size:16px;font-weight:900;border:1.5px solid var(--ebd);background:var(--eb);color:var(--ec)}}
.ept{{font-family:'Space Grotesk',sans-serif;font-size:.70em;font-weight:800}}.eps{{font-size:11px;font-weight:800;margin-top:2px;color:var(--ec)}}
.eh{{--eb:rgba(16,185,129,0.17);--ebd:rgba(52,211,153,0.48);--ec:#34D399}}
.ed{{--eb:rgba(56,189,248,0.16);--ebd:rgba(56,189,248,0.46);--ec:#38BDF8}}
.ew{{--eb:rgba(245,158,11,0.16);--ebd:rgba(251,191,36,0.46);--ec:#FBBF24}}
.en{{--eb:rgba(139,92,246,0.16);--ebd:rgba(167,139,250,0.42);--ec:#A78BFA}}
.eneg{{--eb:rgba(244,63,94,0.16);--ebd:rgba(251,113,133,0.48);--ec:#FB7185}}
.er-neg{{border-color:rgba(251,113,133,0.28);background:rgba(38,18,28,0.72)}}
.er-gold{{position:relative;border:1.5px solid rgba(251,191,36,0.78);background:linear-gradient(135deg,rgba(245,158,11,0.20) 0%,rgba(22,27,46,0.92) 52%,rgba(253,224,71,0.16) 100%);box-shadow:0 0 24px rgba(245,158,11,0.24),inset 0 0 18px rgba(253,224,71,0.10)}}
.er-gold .et{{color:#FEF08A;text-shadow:0 0 12px rgba(251,191,36,0.35)}}
.gold-star{{color:#FBBF24;filter:drop-shadow(0 0 6px rgba(251,191,36,0.8))}}
.egold{{--eb:linear-gradient(135deg,rgba(245,158,11,0.34),rgba(253,224,71,0.22));--ebd:#FBBF24;--ec:#FDE047}}
.egold .epb{{box-shadow:0 0 14px rgba(251,191,36,0.36);text-shadow:0 0 8px rgba(253,224,71,0.4)}}

/* Post-Match Extra Modules */
.ef-wrap{{flex:1 1 0%;min-height:0;display:flex;flex-direction:column;justify-content:center;gap:10px}}
.ef-box{{padding:10px 14px;border-radius:14px;background:rgba(11,13,19,0.85);border:1px solid rgba(255,255,255,0.09);display:flex;flex-direction:column;gap:8px}}
.ef-hd{{font-size:15px;font-weight:800;color:#CBD5E1}}.ef-grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}.ef-stack{{grid-template-columns:1fr;gap:8px}}
.ef-row{{display:flex;flex-direction:column;gap:4px}}.ef-top{{display:flex;justify-content:space-between;align-items:center;font-size:16px;font-weight:800}}
.ef-nm{{display:inline-flex;align-items:center;gap:6px}}.ef-nm i{{width:8px;height:8px;border-radius:99px;display:inline-block}}.ef-nm small{{color:#94A3B8;font-weight:600}}
.ef-track{{height:9px;border-radius:99px;background:rgba(255,255,255,0.09);overflow:hidden}}.ef-fill{{height:100%;border-radius:99px}}
.tr-list{{flex:1 1 0%;min-height:0;display:flex;flex-direction:column;justify-content:center;gap:7px}}
.tr-row{{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:7px 12px;border-radius:11px;background:rgba(13,15,22,0.82);border:1px solid rgba(255,255,255,0.09)}}
.tr-l,.tr-r{{display:flex;align-items:center;gap:8px;min-width:0}}.tr-rk{{width:24px;height:24px;border-radius:6px;background:#181B25;display:inline-flex;align-items:center;justify-content:center;font-size:13px;font-weight:900;color:#CBD5E1}}
.tr-rk1{{color:#FBBF24}}.tr-bar{{width:5px;height:18px;border-radius:99px}}.tr-nm{{font-size:17px;font-weight:900;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.tr-st{{font-size:14px;color:#CBD5E1;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:220px}}
.mod-half .tr-st{{max-width:110px;font-size:12px}}.tr-rt{{padding:2px 8px;border-radius:7px;background:rgba(16,185,129,0.16);border:1px solid rgba(52,211,153,0.45);color:#34D399;font-size:16px;font-weight:900}}
.tr-rt1{{background:rgba(245,158,11,0.2);border-color:rgba(251,191,36,0.65);color:#FBBF24}}
.mt-wrap{{flex:1 1 0%;min-height:0;display:flex;flex-direction:column;justify-content:space-between;gap:10px}}
.mt-top{{display:flex;align-items:center;justify-content:space-between;gap:12px}}.mt-team{{display:inline-flex;align-items:center;gap:6px;font-size:14px;font-weight:800;color:#CBD5E1}}.mt-team i{{width:9px;height:9px;border-radius:99px;display:inline-block}}
.mt-name{{font-size:26px;font-weight:900;color:#fff}}.mt-pos{{font-size:15px;color:#CBD5E1;font-weight:700}}
.mt-badge{{padding:8px 14px;border-radius:14px;background:rgba(245,158,11,0.15);border:2px solid rgba(251,191,36,0.7);display:flex;flex-direction:column;align-items:center;color:#FCD34D;font-size:24px;font-weight:900}}
.mt-badge small{{font-size:10px;letter-spacing:0.08em}}.mt-chips{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}}
.mt-chip{{padding:8px;border-radius:12px;background:rgba(12,14,21,0.85);border:1px solid rgba(255,255,255,0.09);text-align:center}}.mt-cl{{font-size:12px;color:#94A3B8;font-weight:700}}.mt-cv{{font-size:16px;font-weight:900;color:#fff;margin-top:2px}}
.mt-ru{{display:flex;justify-content:space-between;align-items:center;padding-top:8px;border-top:1px solid rgba(255,255,255,0.1);font-size:15px;color:#CBD5E1}}.mt-ru-rt{{padding:2px 8px;border-radius:7px;background:#161923;color:#7DD3FC;font-weight:900}}

/* ─── Unified Footer ─── */
#cf{{position:relative;z-index:10;padding:10px 44px 10px;flex-shrink:0}}
.cf-line{{border-top:1px solid rgba(255,255,255,0.14);margin-bottom:10px}}
.cf-row{{display:flex;align-items:center;justify-content:space-between;gap:16px}}
.cf-left{{display:flex;align-items:center;gap:10px;min-width:0}}
.cf-dot{{width:11px;height:11px;border-radius:99px;background:#E62E45;flex-shrink:0}}
.cf-tag{{font-size:18px;font-weight:800;letter-spacing:0.12em;text-transform:uppercase;color:#F1F5F9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.cf-right{{display:flex;align-items:center;gap:12px;flex-shrink:0}}
.cf-handle{{font-size:20px;font-weight:800;color:#fff}}.cf-sep{{color:#64748B;font-size:18px}}.cf-src{{font-size:17px;font-weight:600;color:#CBD5E1}}
"""



def validate_half_width_layout(modules: list[dict[str, Any]]) -> list[str]:
    """بررسی سخت‌گیرانهٔ جفت‌بودن ماژول‌های نیم‌عرض — اگر نیم‌عرضی جلویش خالی باشد خطای دقیق برمی‌گرداند."""
    active = [m for m in modules if m.get("enabled", True)]
    errors: list[str] = []
    i = 0
    while i < len(active):
        cur = active[i]
        if cur.get("span") == "half":
            if i + 1 < len(active) and active[i + 1].get("span") == "half":
                i += 2
                continue
            title = cur.get("title_fa") or cur.get("id") or "ماژول"
            errors.append(
                f"ماژول نیم‌عرض «{title}» جلویش خالی است — باید کنار آن یک ماژول نیم‌عرض دیگر قرار بدهی یا عرض آن را روی «تمام‌عرض ۱» بگذاری."
            )
        i += 1
    return errors


def render_unified_card_html(payload: dict[str, Any]) -> str:
    """تولید HTML نهایی و یکپارچهٔ هر کارت (پیش‌ازبازی یا پس‌ازبازی) از پوستهٔ واحد + ماژول‌های مجزا."""
    fmt = payload.get("fmt", "4:5")
    w, h = FORMATS.get(fmt, FORMATS["4:5"])
    header_mode = payload.get("headerMode", "full")
    card_type = payload.get("cardType", "preview")
    m = payload["match"]
    hc, ac = m["home"]["color"], m["away"]["color"]

    # هدر ۲ خطی کامل (همهٔ فیلدها در صورت وجود واقعی نمایش داده می‌شوند)
    round_pill = f'<span class="pill-round">{fa(esc(m.get("round")))}</span>' if m.get("round") else ""
    date_txt = payload.get("dateLineOverride") or (
        f'{fa(m.get("day", ""))} • {fa(m.get("time", ""))}' if (m.get("day") and m.get("time")) else fa(m.get("date") or m.get("day") or "")
    )
    line2_parts: list[str] = []
    if date_txt:
        line2_parts.append(f'<span>{esc(date_txt)}</span>')
    if m.get("stadium"):
        if line2_parts:
            line2_parts.append('<span class="hd-sep">•</span>')
        line2_parts.append(
            '<span class="hd-stadium">'
            '<svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="#E62E45" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
            '<ellipse cx="12" cy="8" rx="9" ry="3.5"/><path d="M3 8v6c0 1.93 4.03 3.5 9 3.5s9-1.57 9-3.5V8M7 11.2v5.8M12 11.5v6M17 11.2v5.8M6 4.8V3M18 4.8V3"/></svg>'
            f'<span>{esc(m["stadium"])}</span></span>'
        )
    if card_type == "post_match":
        line2_parts.append('<span class="pill-bcast">● پایان بازی</span>')
    elif m.get("broadcast"):
        line2_parts.append(f'<span class="pill-bcast">{esc(m["broadcast"])}</span>')

    # Hero
    hero_html = (
        _render_post_hero(payload, fmt, header_mode)
        if card_type == "post_match"
        else _render_pre_hero(payload, fmt, header_mode)
    )

    # ماژول‌ها (با تضمین عدم وجود نیم‌فضای خالی)
    final_mods = _fix_orphan_spans(payload.get("modules") or [])
    mods_html = "".join(render_module_html(mod["id"], payload, span=mod["span"], fmt=fmt) for mod in final_mods)

    # تگ پانویس (بدون هیچ مقدار جعلی W9)
    tag_parts = [
        (m.get("leagueEn") or "FOOTBALL").strip().upper(),
        (m.get("season") or "").strip().upper(),
        (m.get("weekCode") or "").strip().upper(),
    ]
    kind_lbl = "POST-MATCH" if card_type == "post_match" else "PRE-MATCH"
    micro_tag = " ".join(p for p in tag_parts if p) + f" • {kind_lbl}"

    # پس‌زمینه SVG دقیق مطابق Pre-Match.html
    rx, rx1, rx2, by1, by2 = w - 147, w - 24, w - 44, h - 24, h - 44
    cx = w // 2
    ambient = (
        f"radial-gradient(circle at 86% 32%,{hc}38,transparent 48%),"
        f"radial-gradient(circle at 14% 32%,{ac}38,transparent 48%),"
        f"radial-gradient(circle at 50% 36%,rgba(230,46,69,0.14),transparent 52%)"
    )

    logo_uri = str(payload.get("brandLogoUri") or "").strip()
    if logo_uri:
        brand_logo_html = f'<img src="{logo_uri}" alt="XGPedia" class="bl-img" />'
    else:
        brand_logo_html = '<div class="bl-word fd"><span style="color:#E62E45">XG</span><span style="color:#F8FAFC">Pedia</span></div>'

    font_css = build_embedded_font_css()
    css = _unified_css(w, h, fmt)

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<title>XGPedia Card</title>
<style id="xgpedia-fonts">{font_css}</style>
<style id="xgpedia-unified">{css}</style>
</head>
<body>
<div id="ea" dir="rtl">
  <div class="bg-layer" style="background:{ambient};"></div>
  <svg class="bg-layer" width="{w}" height="{h}" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid slice" fill="none">
    <defs>
      <pattern id="tg" width="54" height="54" patternUnits="userSpaceOnUse"><path d="M54 0H0v54" stroke="#F8FAFC" stroke-opacity=".055"/></pattern>
      <radialGradient id="rf" cx="50%" cy="30%" r="44%"><stop offset="0" stop-color="#E62E45" stop-opacity=".22"/><stop offset=".55" stop-color="#E62E45" stop-opacity=".06"/><stop offset="1" stop-color="#E62E45" stop-opacity="0"/></radialGradient>
    </defs>
    <rect width="100%" height="100%" fill="url(#tg)"/>
    <rect x="12" y="12" width="{w - 24}" height="{h - 24}" rx="18" stroke="#F8FAFC" stroke-opacity=".11" stroke-width="1.5"/>
    <g stroke="#F8FAFC" stroke-opacity=".09" stroke-width="1.5"><line x1="{cx}" y1="12" x2="{cx}" y2="{h - 12}" stroke-dasharray="8 8"/><circle cx="{cx}" cy="315" r="145"/></g>
    <g stroke="#F8FAFC" stroke-opacity=".07" stroke-width="1.5"><rect x="12" y="145" width="135" height="360"/><path d="M147 245A95 95 0 0 1 147 405"/><rect x="{rx}" y="145" width="135" height="360"/><path d="M{rx} 245A95 95 0 0 0 {rx} 405"/></g>
    <circle cx="{cx}" cy="315" r="245" fill="url(#rf)"/>
    <circle cx="{cx}" cy="315" r="215" stroke="#E62E45" stroke-opacity=".18" stroke-width="1.2" stroke-dasharray="4 6"/>
    <circle cx="{cx}" cy="315" r="295" stroke="#F8FAFC" stroke-opacity=".07"/>
    <circle cx="{cx}" cy="315" r="375" stroke="#F8FAFC" stroke-opacity=".045"/>
    <path d="M24 44V24H44M{rx1} 44V24H{rx2}M24 {by2}V{by1}H44M{rx1} {by2}V{by1}H{rx2}" stroke="#E62E45" stroke-opacity=".55" stroke-width="2"/>
  </svg>
  <div class="scanlines"></div>

  <header id="cm">
    <div class="hd-right">
      <div class="hd-line1">
        <div class="pill-league">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#E62E45" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M8 21h8m-4-4v4m-5-17h10v5a5 5 0 01-10 0V4zM5 6H3v2a3 3 0 003 3h1m12-5h2v2a3 3 0 01-3 3h-1"/></svg>
          <span>{esc(m.get("competition", "لیگ برتر انگلیس"))}</span>
        </div>
        {round_pill}
      </div>
      <div class="hd-line2">{"".join(line2_parts)}</div>
    </div>
    <div id="bl" dir="ltr">{brand_logo_html}</div>
  </header>

  <div id="cmb">
    <section id="hs">{hero_html}</section>
    <section id="mg">{mods_html}</section>
  </div>

  <footer id="cf">
    <div class="cf-line"></div>
    <div class="cf-row">
      <div class="cf-left"><span class="cf-dot"></span><span dir="ltr" class="cf-tag fm">{esc(micro_tag)}</span></div>
      <div class="cf-right fm" dir="ltr"><span class="cf-handle">@XGPedia</span></div>
    </div>
  </footer>
</div>
</body>
</html>"""
