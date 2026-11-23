"""ماژول‌های پس‌ازبازی در هویت بصری یکپارچه (xgrace، shotmap، momentum، efficiency، toprated، motm)."""
from __future__ import annotations

import math
from typing import Any

from src.xgpedia.render.card_kit.helpers import contrast_ink, esc, f1, f2, fa, module_header, team_legend_html


def _signed_fa(v: float) -> str:
    return f"{'+' if v >= 0 else '-'}{fa(f2(abs(v)))}"


def render_xgrace(payload: dict[str, Any], span: str = "full", fmt: str = "4:5") -> str:
    m = payload["match"]
    h, a = m["home"], m["away"]
    h_shots, a_shots = h.get("shotList") or [], a.get("shotList") or []
    if not (h_shots and a_shots):
        return ""
    hc, ac = h["color"], a["color"]
    is_half = span == "half"

    def build(ls: list, total_xg: float):
        s = sorted(ls, key=lambda x: x[5])
        raw_sum = sum(float(i[2]) for i in s) or 1.0
        k = (float(total_xg) or 0.05) / raw_sum
        pts = [(0.0, 0.0)]
        goals = []
        cur = 0.0
        for it in s:
            mn = min(91.0, max(1.0, float(it[5])))
            pts.append((mn, cur))
            cur += float(it[2]) * k
            pts.append((mn, cur))
            if it[3] == "goal":
                goals.append((mn, cur, str(it[4])))
        pts.append((92.0, cur))
        return pts, goals, cur

    h_pts, h_gs, h_t = build(h_shots, float(h.get("xg") or 0))
    a_pts, a_gs, a_t = build(a_shots, float(a.get("xg") or 0))
    max_y = max(2.2, math.ceil(2.0 * (max(h_t, a_t) + 0.35)) / 2.0)

    vb_w, vb_h = (560, 260) if is_half else (920, 250)
    left, right_pad, top, bot = 56, 88, 26, 42
    p_w, p_h = vb_w - left - right_pad, vb_h - top - bot
    fx = lambda v: left + (v / 92.0) * p_w
    fy = lambda v: top + p_h - (v / max_y) * p_h
    to_d = lambda pts: " ".join(f"{'L' if i else 'M'}{f1(fx(x))} {f1(fy(y))}" for i, (x, y) in enumerate(pts))
    hp, ap = to_d(h_pts), to_d(a_pts)
    base_y = f1(top + p_h)
    h_area = f"{hp} L{f1(fx(92))} {base_y} L{f1(left)} {base_y} Z"
    a_area = f"{ap} L{f1(fx(92))} {base_y} L{f1(left)} {base_y} Z"

    step = 1.0 if max_y > 3.0 else 0.5
    grid = []
    v = 0.0
    while v <= max_y + 0.01:
        y = fy(v)
        grid.append(
            f'<line x1="{left}" y1="{f1(y)}" x2="{f1(left + p_w)}" y2="{f1(y)}" stroke="rgba(255,255,255,{0.2 if v == 0 else 0.08})" stroke-width="{1.6 if v == 0 else 1.2}" {"" if v == 0 else "stroke-dasharray=5,6"}/>'
            f'<text x="{left - 8}" y="{f1(y + 5)}" text-anchor="end" fill="#CBD5E1" font-weight="800" font-size="21">{fa(f1(v))}</text>'
        )
        v += step

    xticks = "".join(
        f'<text x="{f1(fx(t))}" y="{vb_h - 10}" text-anchor="middle" fill="{"#FF6B7F" if t == 45 else "#94A3B8"}" font-weight="800" font-size="21">{fa(t)}\'</text>'
        for t in (0, 15, 30, 45, 60, 75, 90)
    )
    def goal_marks(gs, c):
        return "".join(
            f'<circle cx="{f1(fx(mn))}" cy="{f1(fy(val))}" r="6" fill="{c}" stroke="#fff" stroke-width="2.2"/>'
            for mn, val, _pl in gs
        )

    hy, ay = fy(h_t), fy(a_t)
    if abs(hy - ay) < 26:
        hy, ay = (hy - 13, ay + 13) if hy <= ay else (hy + 13, ay - 13)
    bx = left + p_w + 8
    badges = (
        f'<rect x="{f1(bx)}" y="{f1(hy - 13)}" width="74" height="28" rx="8" fill="{hc}"/>'
        f'<text x="{f1(bx + 37)}" y="{f1(hy + 6)}" text-anchor="middle" fill="{contrast_ink(hc)}" font-weight="900" font-size="22">{fa(f2(h["xg"]))}</text>'
        f'<rect x="{f1(bx)}" y="{f1(ay - 13)}" width="74" height="28" rx="8" fill="{ac}"/>'
        f'<text x="{f1(bx + 37)}" y="{f1(ay + 6)}" text-anchor="middle" fill="{contrast_ink(ac)}" font-weight="900" font-size="22">{fa(f2(a["xg"]))}</text>'
    )

    title = "جریان امید گل" if is_half else "نمودار جریان امید گل (xG Race)"
    right = team_legend_html(h["name"], a["name"], hc, ac, is_half=is_half)
    return (
        f'<div class="xm {"mod-half" if is_half else "mod-full"}">'
        f'{module_header(title, right, "#E62E45", is_half=is_half)}'
        f'<div class="mod-body-svg" dir="ltr">'
        f'<svg class="fit-svg" viewBox="0 0 {vb_w} {vb_h}" preserveAspectRatio="xMidYMid meet" fill="none" font-family="Vazirmatn">'
        f'{"".join(grid)}'
        f'<line x1="{f1(fx(45))}" y1="{top}" x2="{f1(fx(45))}" y2="{base_y}" stroke="#E62E45" stroke-opacity=".6" stroke-width="1.6" stroke-dasharray="5 5"/>'
        f'<path d="{a_area}" fill="{ac}" fill-opacity=".12"/><path d="{h_area}" fill="{hc}" fill-opacity=".18"/>'
        f'<path d="{ap}" stroke="{ac}" stroke-width="3.6"/><path d="{hp}" stroke="{hc}" stroke-width="4.2"/>'
        f'{goal_marks(a_gs, ac)}{goal_marks(h_gs, hc)}{badges}{xticks}'
        f'</svg></div></div>'
    )


def render_shotmap(payload: dict[str, Any], span: str = "full", fmt: str = "4:5") -> str:
    m = payload["match"]
    h, a = m["home"], m["away"]
    h_shots, a_shots = h.get("shotList") or [], a.get("shotList") or []
    if not (h_shots and a_shots):
        return ""
    hc, ac = h["color"], a["color"]
    is_half = span == "half"

    def dots(ls, c, is_home: bool) -> str:
        out = []
        for x, y, xg, tp, *_ in ls:
            px = f1(22 + ((x if is_home else 100 - x) / 100.0) * 676)
            py = f1(30 + (y / 100.0) * 299)
            r = 5.5 + 16.0 * math.sqrt(max(0.02, float(xg)))
            if tp == "goal":
                out.append(f'<circle cx="{px}" cy="{py}" r="{f1(r)}" fill="{c}" stroke="#fff" stroke-width="2.6"/>')
            elif tp == "sot":
                out.append(f'<circle cx="{px}" cy="{py}" r="{f1(r)}" stroke="{c}" stroke-width="2.6"/>')
            else:
                out.append(f'<circle cx="{px}" cy="{py}" r="{f1(r)}" fill="{c}" fill-opacity=".24" stroke="{c}" stroke-opacity=".6" stroke-width="1.4"/>')
        return "".join(out)

    title = "نقشه شوت" if is_half else "نقشه شوت و کیفیت موقعیت‌ها"
    return (
        f'<div class="xm {"mod-half" if is_half else "mod-full"}">'
        f'{module_header(title, "<span class=mod-tag>SHOT MAP</span>", "#E62E45", is_half=is_half)}'
        f'<div class="mod-body-svg" dir="ltr">'
        f'<svg class="fit-svg" viewBox="0 0 720 345" preserveAspectRatio="xMidYMid meet" fill="none" font-family="Vazirmatn">'
        f'<text x="191" y="19" text-anchor="middle" fill="{ac}" font-weight="900" font-size="24">← {esc(a["name"])} ({fa(a["shots"])})</text>'
        f'<text x="529" y="19" text-anchor="middle" fill="{hc}" font-weight="900" font-size="24">{esc(h["name"])} ({fa(h["shots"])}) →</text>'
        f'<rect x="22" y="30" width="676" height="299" rx="12" fill="#0A1328" stroke="rgba(248,250,252,.22)" stroke-width="2"/>'
        f'<g stroke="rgba(248,250,252,.17)" stroke-width="1.8">'
        f'<line x1="360" y1="30" x2="360" y2="329"/><circle cx="360" cy="179.5" r="46"/>'
        f'<rect x="22" y="93.5" width="110" height="172"/><rect x="588" y="93.5" width="110" height="172"/></g>'
        f'{dots(a_shots, ac, False)}{dots(h_shots, hc, True)}'
        f'</svg></div></div>'
    )


def render_momentum(payload: dict[str, Any], span: str = "full", fmt: str = "4:5") -> str:
    m = payload["match"]
    arr = m.get("momentum") or []
    if not arr:
        return ""
    hc, ac = m["home"]["color"], m["away"]["color"]
    is_half = span == "half"
    mx = max(68.0, *(abs(float(v)) for v in arr))
    step = 712.0 / len(arr)
    bw = 0.68 * step
    bars_list = []
    for i, v in enumerate(arr):
        fv = float(v)
        bx = f1(24 + i * step + (step - bw) / 2)
        if abs(fv) < 0.05:
            # بازهٔ خنثی بدون فشار — تیک ظریف خاکستری (نه ستون قرمز جعلی!)
            bars_list.append(
                f'<rect x="{bx}" y="152" width="{f1(bw)}" height="4" rx="2" fill="rgba(148,163,184,0.32)"/>'
            )
        else:
            bh = max(10.0, abs(fv) / mx * 102.0)
            by = 154.0 - bh if fv > 0 else 154.0
            col = hc if fv > 0 else ac
            bars_list.append(
                f'<rect x="{bx}" y="{f1(by)}" width="{f1(bw)}" height="{f1(bh)}" rx="4" fill="{col}" fill-opacity=".90"/>'
            )
    bars = "".join(bars_list)
    xticks = "".join(
        f'<text x="{f1(24 + t / 90.0 * 712)}" y="298" text-anchor="middle" fill="{"#FBBF24" if t == 45 else "#94A3B8"}" font-weight="800" font-size="21">{fa(t)}\'</text>'
        for t in (0, 15, 30, 45, 60, 75, 90)
    )
    title = "موج فشار" if is_half else "موج فشار و برتری حملات (۵ دقیقه‌ای)"
    return (
        f'<div class="xm {"mod-half" if is_half else "mod-full"}">'
        f'{module_header(title, "<span class=mod-tag>MOMENTUM</span>", "#38BDF8", is_half=is_half)}'
        f'<div class="mod-body-svg" dir="ltr">'
        f'<svg class="fit-svg" viewBox="0 0 760 310" preserveAspectRatio="xMidYMid meet" fill="none" font-family="Vazirmatn">'
        f'<text x="24" y="22" fill="{hc}" font-weight="900" font-size="24">▲ {esc(m["home"]["name"])}</text>'
        f'<text x="736" y="22" text-anchor="end" fill="{ac}" font-weight="900" font-size="24">▼ {esc(m["away"]["name"])}</text>'
        f'<line x1="380" y1="36" x2="380" y2="272" stroke="#FBBF24" stroke-opacity=".5" stroke-width="1.6" stroke-dasharray="5 5"/>'
        f'{bars}<line x1="24" y1="154" x2="736" y2="154" stroke="#F8FAFC" stroke-opacity=".45" stroke-width="2"/>{xticks}'
        f'</svg></div></div>'
    )


def render_efficiency(payload: dict[str, Any], span: str = "full", fmt: str = "4:5") -> str:
    m = payload["match"]
    h, a = m["home"], m["away"]
    h_gk, a_gk = h.get("gk") or {}, a.get("gk") or {}
    if not (h_gk.get("name") and a_gk.get("name")):
        return ""
    hc, ac = h["color"], a["color"]
    is_half = span == "half"
    # حذف «بهره‌وری گل (G−xG)» به‌دلیل تکرار در هیرو → جایگزینی با «دقت شوت در چارچوب (٪)»
    h_sh, h_sot = int(h.get("shots") or 0), int(h.get("sot") or 0)
    a_sh, a_sot = int(a.get("shots") or 0), int(a.get("sot") or 0)
    h_acc = round((h_sot / h_sh) * 100.0) if h_sh > 0 else 0
    a_acc = round((a_sot / a_sh) * 100.0) if a_sh > 0 else 0
    gh = float(h_gk["psxg"]) - float(h_gk["ga"])
    ga = float(a_gk["psxg"]) - float(a_gk["ga"])
    mg = max(1.2, abs(gh), abs(ga))

    def row_pct(nm: str, sub: str, pct: int, c: str) -> str:
        w = min(100, max(8, pct))
        return (
            f'<div class="ef-row"><div class="ef-top">'
            f'<span class="ef-nm"><i style="background:{c}"></i>{esc(nm)} <small>{esc(sub)}</small></span>'
            f'<span dir="ltr" class="ef-val" style="color:{c}">{fa(pct)}٪</span></div>'
            f'<div class="ef-track" dir="ltr"><div class="ef-fill" style="width:{w}%;background:{c}"></div></div></div>'
        )

    def row_signed(nm: str, sub: str, v: float, mx: float, c: str) -> str:
        col = "#34D399" if v >= 0 else "#FB7185"
        w = min(100, max(10, round(abs(v) / mx * 100)))
        return (
            f'<div class="ef-row"><div class="ef-top">'
            f'<span class="ef-nm"><i style="background:{c}"></i>{esc(nm)} <small>{esc(sub)}</small></span>'
            f'<span dir="ltr" class="ef-val" style="color:{col}">{_signed_fa(v)}</span></div>'
            f'<div class="ef-track" dir="ltr"><div class="ef-fill" style="width:{w}%;background:{col}"></div></div></div>'
        )

    title = "دقت ضربه و دروازه‌بان" if is_half else "دقت شوت‌زنی و عملکرد دروازه‌بان‌ها"
    return (
        f'<div class="xm {"mod-half" if is_half else "mod-full"}">'
        f'{module_header(title, "<span class=mod-tag>ACCURACY & GK</span>", "#10B981", is_half=is_half)}'
        f'<div class="ef-wrap">'
        f'<div class="ef-box"><div class="ef-hd">{"دقت شوت در چارچوب" if is_half else "دقت شوت‌زنی (در چارچوب / کل شوت)"}</div><div class="ef-grid{" ef-stack" if is_half else ""}">'
        f'{row_pct(h["name"], f"({fa(h_sot)}/{fa(h_sh)})", h_acc, hc)}{row_pct(a["name"], f"({fa(a_sot)}/{fa(a_sh)})", a_acc, ac)}</div></div>'
        f'<div class="ef-box"><div class="ef-hd">{"دروازه‌بان (PSxG−GA)" if is_half else "نجات گل دروازه‌بان (PSxG − GA)"}</div><div class="ef-grid{" ef-stack" if is_half else ""}">'
        f'{row_signed(h_gk["name"], "(" + fa(h_gk["saves"]) + " مهار)", gh, mg, hc)}{row_signed(a_gk["name"], "(" + fa(a_gk["saves"]) + " مهار)", ga, mg, ac)}</div></div>'
        f'</div></div>'
    )


def render_toprated(payload: dict[str, Any], span: str = "full", fmt: str = "4:5") -> str:
    m = payload["match"]
    pls = m.get("topPlayers") or []
    if not pls:
        return ""
    is_half = span == "half"
    rows = []
    for idx, p in enumerate(pls[:5], 1):
        tm = m["away"] if p["side"] == "away" else m["home"]
        rows.append(
            f'<div class="tr-row">'
            f'<div class="tr-l"><span class="tr-rk{" tr-rk1" if idx == 1 else ""}">{fa(idx)}</span>'
            f'<span class="tr-bar" style="background:{tm["color"]}"></span>'
            f'<span class="tr-nm">{esc(p["name"])}</span></div>'
            f'<div class="tr-r"><span class="tr-st">{fa(esc(p["stat"]))}</span>'
            f'<span class="tr-rt{" tr-rt1" if idx == 1 else ""}">{fa(f1(p["rating"]))}</span></div></div>'
        )
    title = "برترین‌های زمین" if is_half else "برترین‌های زمین (Top Rated)"
    return (
        f'<div class="xm {"mod-half" if is_half else "mod-full"}">'
        f'{module_header(title, "<span class=mod-tag>TOP RATED</span>", "#F59E0B", is_half=is_half)}'
        f'<div class="tr-list">{"".join(rows)}</div></div>'
    )


def render_motm(payload: dict[str, Any], span: str = "full", fmt: str = "4:5") -> str:
    m = payload["match"]
    mt = m.get("motm") or {}
    if not mt.get("name"):
        return ""
    tm = m["away"] if mt.get("side") == "away" else m["home"]
    ru = mt.get("runnerUp") or {}
    rt = m["away"] if ru.get("side") == "away" else m["home"]
    is_half = span == "half"
    chips = "".join(
        f'<div class="mt-chip"><div class="mt-cl">{esc(c["label"])}</div><div class="mt-cv">{fa(esc(c["val"]))}</div></div>'
        for c in (mt.get("chips") or [])[:3]
    )
    title = "ستاره زمین (MOTM)"
    return (
        f'<div class="xm {"mod-half" if is_half else "mod-full"}">'
        f'{module_header(title, "<span class=mod-tag>MAN OF THE MATCH</span>", "#F59E0B", is_half=is_half)}'
        f'<div class="mt-wrap">'
        f'<div class="mt-top"><div class="mt-info">'
        f'<span class="mt-team"><i style="background:{tm["color"]}"></i>{esc(tm["name"])}</span>'
        f'<div class="mt-name">{esc(mt["name"])}</div><div class="mt-pos">{esc(mt["pos"])}</div></div>'
        f'<div class="mt-badge"><span>★ {fa(f1(mt["rating"]))}</span><small>MOTM</small></div></div>'
        f'<div class="mt-chips">{chips}</div>'
        f'<div class="mt-ru"><span>برترین بازیکن حریف: <b>{esc(ru.get("name", ""))}</b></span>'
        f'<span class="mt-ru-rt">{fa(f1(ru.get("rating", 0)))}</span></div>'
        f'</div></div>'
    )
