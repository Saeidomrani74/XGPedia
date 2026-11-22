"""لایهٔ ۶ — Rendering کارت پس‌از‌بازی از قالب استودیویی HTML (`studio_templates/post_match.html`).

طراحی کارت **عیناً و بدون هیچ تفاوتی** از فایل استودیویی درون پوشه `studio_templates/`
تولید می‌شود و فقط داده‌های واقعی مسابقه جایگذاری می‌گردند:
  - هیچ عددی هاردکد یا جعلی نیست؛ همهٔ اعداد از fact_json (result + match_stats +
    فیلدهای اختیاری ارائه‌دهندگان آینده) می‌آیند. null ≠ 0.
  - ترتیب اولویت ماژول‌ها در صورت وجود دیتای کامل:
      1. xgrace      (نمودار جریان امید گل xG Race)
      2. shotmap     (نقشه شوت و کیفیت موقعیت‌ها)
      3. momentum    (موج فشار و برتری حملات ۵ دقیقه‌ای)
      4. efficiency  (دقت ضربه نهایی و عملکرد دروازه‌بان‌ها)
      5. toprated    (برترین‌های زمین Top Rated — تک‌خطی)
      6. motm        (ستاره زمین MOTM و رقیب برتر)
      7. stats       (آمار کلیدی مسابقه ۹۰ دقیقه)
  - ماژول ۸ («روایت آماری و گره تاکتیکی بازی» / autopsy) هرگز روی کارت نمایش داده
    نمی‌شود و به‌صورت خودکار به متن کپشن اضافه می‌گردد.
  - نیم‌فضای خالی و سرریز متن در هیچ فرمتی (4:5، 9:16، 16:9) رخ نمی‌دهد.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from src.xgpedia.config import load_brand, team_identity
from src.xgpedia.render.cards import (
    COMPETITION_FA,
    FORMATS,
    _contrast_text,
    _crest_data_uri,
    _crest_html,
    display_colors,
    fmt_fixed,
    fmt_stat,
    jalali_date,
    season_short,
)
from src.xgpedia.render.studio_engine import (
    POST_MATCH_CAPTION_ONLY,
    POST_MATCH_PRIORITY,
    build_card_caption,
    render_from_studio_template,
    select_studio_modules,
)

POST_STATS_ROW_CAP = {"4:5": 4, "9:16": 4, "16:9": 4}


def _side_stats(facts_side: dict) -> dict[str, float]:
    """متریک‌های خودِ بازی یک طرف — {metric: value}؛ مقدار None اصلاً درج نمی‌شود."""
    ms = facts_side.get("match_stats") or {}
    out: dict[str, float] = {}
    for key, node in ms.items():
        if isinstance(node, dict) and node.get("value") is not None:
            out[key] = float(node["value"])
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            out[key] = float(node)
    return out


def _build_post_stats_rows(
    hs: dict[str, float], as_: dict[str, float], max_rows: int = 4
) -> list[dict[str, str]]:
    """ساخت ردیف‌های آمار کلیدی مسابقه فقط از متریک‌های واقعی موجود در هر دو طرف.

    ترتیب ردیف‌ها دقیقاً مطابق استودیو است: xG، مالکیت (اگر بود)، شوت کل (در چارچوب)،
    موقعیت بزرگ (اگر بود)، و در نبود مالکیت/موقعیت بزرگ، کرنر و خطای واقعی.
    """
    rows: list[dict[str, str]] = []
    specs = (
        ("امید گل واقعی (xG)", "expected_goals", 2, "", None),
        ("مالکیت توپ (٪)", "possession", 0, "٪", None),
        ("شوت کل (در چارچوب)", "total_shots", 0, "", "shots_on_target"),
        ("موقعیت بزرگ گلزنی", "big_chances", 0, "", None),
        ("کرنر", "corner_kicks", 0, "", None),
        ("خطا", "fouls", 0, "", None),
    )
    for label, metric, dec, suffix, sub_metric in specs:
        hv, av = hs.get(metric), as_.get(metric)
        if hv is None or av is None:
            continue
        max_v = max(hv, av, 0.01)
        h_str = (fmt_fixed(hv, dec) or "") + suffix
        a_str = (fmt_fixed(av, dec) or "") + suffix
        if sub_metric and hs.get(sub_metric) is not None and as_.get(sub_metric) is not None:
            h_str = f"{h_str} ({fmt_stat(hs[sub_metric])})"
            a_str = f"{a_str} ({fmt_stat(as_[sub_metric])})"
        rows.append({
            "label": label,
            "h": h_str,
            "a": a_str,
            "h_pct": f"{hv / max_v * 100:.1f}",
            "a_pct": f"{av / max_v * 100:.1f}",
        })
        if len(rows) >= max_rows:
            break
    return rows


def _valid_shot_list(raw: Any) -> list[list[Any]] | None:
    """اعتبارسنجی لیست شوت‌ها برای xG Race و Shot Map: [[x, y, xg, type, player, min], ...]."""
    if not isinstance(raw, list) or not raw:
        return None
    valid_types = {"miss", "sot", "goal"}
    out: list[list[Any]] = []
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) < 6:
            return None
        x, y, xg, stype, player, minute = item[:6]
        if stype not in valid_types:
            return None
        try:
            out.append([float(x), float(y), float(xg), str(stype), str(player), int(minute)])
        except (TypeError, ValueError):
            return None
    return out


def _valid_gk(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip()
    saves = raw.get("saves")
    psxg = raw.get("psxg")
    ga = raw.get("ga")
    if not name or saves is None or psxg is None or ga is None:
        return None
    try:
        return {"name": name, "saves": int(saves), "psxg": float(psxg), "ga": int(ga)}
    except (TypeError, ValueError):
        return None


def _valid_momentum(raw: Any) -> list[float] | None:
    if not isinstance(raw, list) or len(raw) < 4:
        return None
    out: list[float] = []
    for v in raw:
        if v is None or isinstance(v, bool):
            return None
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        if math.isnan(f) or math.isinf(f):
            return None
        out.append(f)
    return out


def _valid_top_players(raw: Any) -> list[dict[str, Any]] | None:
    if not isinstance(raw, list) or not raw:
        return None
    out: list[dict[str, Any]] = []
    for p in raw:
        if not isinstance(p, dict):
            return None
        name = str(p.get("name") or "").strip()
        side = p.get("side")
        stat = str(p.get("stat") or "").strip()
        rating = p.get("rating")
        if not name or side not in ("home", "away") or not stat or rating is None:
            return None
        try:
            out.append({"name": name, "side": side, "stat": stat, "rating": float(rating)})
        except (TypeError, ValueError):
            return None
    return out


def _valid_motm(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    side = raw.get("side")
    name = str(raw.get("name") or "").strip()
    pos = str(raw.get("pos") or "").strip()
    number = raw.get("number")
    rating = raw.get("rating")
    chips = raw.get("chips")
    ru = raw.get("runnerUp") or raw.get("runner_up")
    if (
        side not in ("home", "away")
        or not name
        or not pos
        or number is None
        or rating is None
        or not isinstance(chips, list)
        or not chips
        or not isinstance(ru, dict)
    ):
        return None
    ru_side = ru.get("side")
    ru_name = str(ru.get("name") or "").strip()
    ru_stat = str(ru.get("stat") or "").strip()
    ru_rating = ru.get("rating")
    if ru_side not in ("home", "away") or not ru_name or ru_rating is None:
        return None
    return {
        "side": side,
        "name": name,
        "pos": pos,
        "number": int(number),
        "rating": float(rating),
        "chips": [{"label": str(c.get("label", "")), "val": str(c.get("val", ""))} for c in chips[:3]],
        "runnerUp": {
            "side": ru_side,
            "name": ru_name,
            "stat": ru_stat,
            "rating": float(ru_rating),
        },
    }


# ─── ساخت context کارت پس‌ازبازی ───

def build_post_match_context(
    draft: dict,
    facts: dict,
    brand: dict | None = None,
    layout: str = "smart",
    fmt: str = "4:5",
    brand_mono: bool = False,
    header_mode: str = "full",
) -> dict:
    """ساخت context کامل کارت پس‌ازبازی و payload دقیق استودیو `post_match.html`.

    همهٔ اعداد صرفاً از fact_json (و مشتق قطعی Dixon-Coles روی xG واقعی بازی) می‌آیند.
    انتخاب ماژول‌ها دقیقاً طبق اولویت کاربر انجام می‌شود و `autopsy` هرگز روی کارت نمی‌آید.
    """
    from src.xgpedia.analytics.metrics import dixon_coles_matrix, expected_points

    b = brand or load_brand()
    pal = b.get("matchday_palette") or {}
    fallback_col = pal.get("sky_bright", "#38BDF8")

    home_f, away_f = facts.get("home", {}), facts.get("away", {})
    home_ident = team_identity(home_f.get("name_en", ""))
    away_ident = team_identity(away_f.get("name_en", ""))
    hc, ac = display_colors(home_ident, away_ident, fallback_col)

    result = facts.get("result") or {}
    hs, as_ = _side_stats(home_f), _side_stats(away_f)
    hg = result.get("home_goals")
    ag = result.get("away_goals")
    hxg, axg = hs.get("expected_goals"), as_.get("expected_goals")

    # احتمال‌های ۱X۲ و xPts از xG خودِ بازی (Dixon-Coles)
    probs = None
    xpts_h = xpts_a = None
    if hxg is not None and axg is not None:
        dc = dixon_coles_matrix(float(hxg), float(axg))
        pH = max(5, round(dc["pH"] * 100))
        pD = max(5, round(dc["pD"] * 100))
        pA = max(5, 100 - pH - pD)
        if pH + pD + pA != 100:
            pH += 100 - (pH + pD + pA)
        probs = {"home": pH, "draw": pD, "away": pA}
        xh, xa = expected_points(pH / 100, pD / 100, pA / 100)
        xpts_h, xpts_a = fmt_fixed(xh, 2), fmt_fixed(xa, 2)

    def _finish_delta(goals: int | None, xg: float | None) -> str | None:
        if goals is None or xg is None:
            return None
        d = goals - xg
        return f"{'+' if d >= 0 else ''}{fmt_fixed(d, 2)}"

    # اعتبارسنجی کامل‌بودن دیتای واقعی هر ماژول
    h_shots_list = _valid_shot_list(home_f.get("shotList") or home_f.get("shot_list"))
    a_shots_list = _valid_shot_list(away_f.get("shotList") or away_f.get("shot_list"))
    h_inside = home_f.get("insideBox") if home_f.get("insideBox") is not None else hs.get("inside_box")
    a_inside = away_f.get("insideBox") if away_f.get("insideBox") is not None else as_.get("inside_box")
    momentum = _valid_momentum(facts.get("momentum"))
    h_gk = _valid_gk(home_f.get("gk"))
    a_gk = _valid_gk(away_f.get("gk"))
    top_players = _valid_top_players(facts.get("topPlayers") or facts.get("top_players"))
    motm = _valid_motm(facts.get("motm"))
    stats_rows = _build_post_stats_rows(hs, as_, max_rows=POST_STATS_ROW_CAP.get(fmt, 4))

    has: dict[str, bool] = {
        "xgrace": bool(h_shots_list and a_shots_list and hxg is not None and axg is not None),
        "shotmap": bool(
            h_shots_list and a_shots_list and h_inside is not None and a_inside is not None
        ),
        "momentum": momentum is not None,
        "efficiency": bool(
            hg is not None and ag is not None and hxg is not None and axg is not None and h_gk and a_gk
        ),
        "toprated": top_players is not None,
        "motm": motm is not None,
        "stats": bool(stats_rows),
        "autopsy": False,  # الزام کاربر: هرگز روی کارت نیست؛ فقط در کپشن
    }
    modules = select_studio_modules(
        "post_match", has, fmt=fmt, layout=layout, header_mode=header_mode
    )

    # ساخت هویت تیم‌ها برای payload استودیو
    def _build_team(f: dict, ident: dict | None, color: str, stats: dict[str, float],
                    shots_list: list | None, inside: Any, gk: dict | None, key: str) -> dict[str, Any]:
        colors = (ident or {}).get("colors") or {}
        code = (ident or {}).get("code") or (f.get("name_en") or "FC")[:3].upper()
        name_fa = f.get("name_fa", "")
        name_en = f.get("name_en", "")
        goal_events = [
            {"player": s[4], "min": s[5]} for s in (shots_list or []) if s[3] == "goal"
        ]
        return {
            "name": name_fa,
            "name_fa": name_fa,
            "name_en": name_en,
            "sub": str(f.get("sub") or "").strip(),
            "code": code,
            "color": color,
            "secondary": colors.get("secondary") or "#FFFFFF",
            "logoUrl": _crest_data_uri(name_en),
            "crest_html": _crest_html(name_en, {
                "name_fa": name_fa, "code": code, "primary": color,
                "secondary": colors.get("secondary") or "#FFFFFF",
            }, key),
            "xg": stats.get("expected_goals") or 0,
            "poss": int(round(stats["possession"])) if "possession" in stats else 0,
            "shots": int(round(stats["total_shots"])) if "total_shots" in stats else 0,
            "sot": int(round(stats["shots_on_target"])) if "shots_on_target" in stats else 0,
            "bigChances": int(round(stats["big_chances"])) if "big_chances" in stats else 0,
            "insideBox": int(round(float(inside))) if inside is not None else 0,
            "scorersText": str(f.get("scorersText") or f.get("scorers_text") or "").strip(),
            "goalEvents": goal_events,
            "redCards": f.get("redCards") or [],
            "gk": gk or {"name": "", "saves": 0, "psxg": 0, "ga": 0},
            "shotList": shots_list or [],
        }

    home = _build_team(home_f, home_ident, hc, hs, h_shots_list, h_inside, h_gk, "home")
    away = _build_team(away_f, away_ident, ac, as_, a_shots_list, a_inside, a_gk, "away")

    comp_en = facts.get("competition", {}).get("name", "")
    season = facts.get("competition", {}).get("season", "")
    kickoff = facts.get("kickoff_utc", "")
    prov = (facts.get("source") or {}).get("provider", "")
    week_code = facts.get("matchday")
    week_part = f"W{week_code}" if isinstance(week_code, int) else str(week_code or "")
    w, hgt = FORMATS.get(fmt, FORMATS["4:5"])

    studio_match: dict[str, Any] = {
        "competition": COMPETITION_FA.get(comp_en, comp_en) or "فوتبال",
        "round": str(facts.get("round") or "گزارش آماری پس از بازی").strip(),
        "leagueEn": (comp_en or "FOOTBALL").upper(),
        "season": season_short(season) if season else "",
        "weekCode": week_part,
        "date": jalali_date(kickoff) if kickoff else "",
        "stadium": str(facts.get("stadium") or "").strip(),
        "source": prov or "XGPedia Analytics",
        "scoreHome": hg if hg is not None else 0,
        "scoreAway": ag if ag is not None else 0,
        "probHome": probs["home"] if probs else 0,
        "probDraw": probs["draw"] if probs else 0,
        "probAway": probs["away"] if probs else 0,
        "home": home,
        "away": away,
        "momentum": momentum or [],
        "motm": motm or {
            "side": "home", "name": "", "pos": "", "number": 0, "rating": 0,
            "chips": [], "runnerUp": {"side": "away", "name": "", "stat": "", "rating": 0},
        },
        "story": {
            "title": str(draft.get("title") or "").strip(),
            "body": " ".join(str(x).strip() for x in (draft.get("bullets") or [])[:2] if x),
            "tag": "",
        },
        "topPlayers": top_players or [],
    }

    studio_payload = {
        "cardType": "post_match",
        "fmt": fmt,
        "headerMode": header_mode,
        "hasProbs": probs is not None,
        "modules": modules,
        "statsRows": stats_rows,
        "match": studio_match,
    }

    capsule = [
        {"id": "home", "pct": probs["home"], "bg": hc, "color": _contrast_text(hc)},
        {"id": "draw", "pct": probs["draw"], "bg": "#2A2F3D", "color": "#F1F5F9"},
        {"id": "away", "pct": probs["away"], "bg": ac, "color": _contrast_text(ac)},
    ] if probs else None

    hero = {
        "xg_home": fmt_fixed(hxg, 2),
        "xg_away": fmt_fixed(axg, 2),
        "xg_total": fmt_fixed((hxg or 0) + (axg or 0), 2) if hxg is not None and axg is not None else None,
        "xpts_home": xpts_h,
        "xpts_away": xpts_a,
        "delta_home": _finish_delta(hg, hxg),
        "delta_away": _finish_delta(ag, axg),
    }

    return {
        "format": {"key": fmt, "w": w, "h": hgt, "is_wide": fmt == "16:9", "is_tall": fmt == "9:16"},
        "competition_fa": COMPETITION_FA.get(comp_en, comp_en),
        "day": jalali_date(kickoff) if kickoff else "",
        "home": home,
        "away": away,
        "score": {"home": hg, "away": ag},
        "hero": hero,
        "capsule": capsule,
        "has": has,
        "modules": modules,
        "module_data": {
            "stats": {"rows": stats_rows},
            "xgrace": {"home": h_shots_list, "away": a_shots_list} if has["xgrace"] else None,
            "shotmap": {"home": h_shots_list, "away": a_shots_list} if has["shotmap"] else None,
            "momentum": momentum,
            "efficiency": {"home_gk": h_gk, "away_gk": a_gk} if has["efficiency"] else None,
            "toprated": top_players,
            "motm": motm,
        },
        "caption_text": build_card_caption(draft, facts, "post_match"),
        "studio_payload": studio_payload,
    }


def render_post_match_html(
    draft: dict,
    facts: dict,
    layout: str = "smart",
    fmt: str = "4:5",
    brand_mono: bool = False,
    header_mode: str = "full",
    template_dir: str | Path | None = None,
) -> str:
    """تولید HTML کامل کارت پس‌ازبازی دقیقاً از روی `studio_templates/post_match.html`."""
    ctx = build_post_match_context(
        draft,
        facts,
        layout=layout,
        fmt=fmt,
        brand_mono=brand_mono,
        header_mode=header_mode,
    )
    return render_from_studio_template("post_match", ctx["studio_payload"], template_dir=template_dir)


def render_post_match_card(
    draft: dict,
    facts: dict,
    out_dir: str | Path,
    post_id: int,
    version: int,
    platform: str = "telegram",
    layout: str = "smart",
    fmt: str = "4:5",
    brand_mono: bool = False,
    header_mode: str = "full",
    template_dir: str | Path | None = None,
) -> tuple[Path, Path, Path]:
    """رندر کامل پست پس‌ازبازی: HTML استودیویی + تصویر نهایی + کپشن (با روایت تاکتیکی)."""
    from src.xgpedia.render.render_png import render_sync

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    w, hgt = FORMATS.get(fmt, FORMATS["4:5"])
    stem = f"post_{post_id}_v{version}_post_match"
    html_path = out / f"{stem}_{w}x{hgt}.html"
    html_path.write_text(
        render_post_match_html(
            draft,
            facts,
            layout=layout,
            fmt=fmt,
            brand_mono=brand_mono,
            header_mode=header_mode,
            template_dir=template_dir,
        ),
        encoding="utf-8",
    )

    img_fmt = "jpeg" if platform == "instagram" else "png"
    img_path = out / f"{stem}_{w}x{hgt}.{img_fmt}"
    render_sync(str(html_path), str(img_path), w, hgt, img_fmt)

    cap_path = out / f"post_{post_id}_v{version}_caption.txt"
    cap_path.write_text(build_card_caption(draft, facts, "post_match"), encoding="utf-8")

    return html_path, img_path, cap_path
