"""لایهٔ ۶ — Rendering کارت پس‌از‌بازی (post_match).

منبع طراحی: استودیوی پس‌از‌بازی (post-match.html، تم «مجله تاکتیکی خاکی و برنز» /
Warm Terracotta) — عیناً همان markup/CSS در قالب Jinja پیاده شده، منتها:
  - همهٔ اعداد از fact_json آرشیوشدهٔ پست می‌آیند (result + match_stats ساختهٔ
    sync.build_match_facts(post_match=True))؛ رندرر هیچ عددی از خودش نمی‌سازد.
  - تنها مشتق‌های قطعی: احتمال‌های ۱X۲ و xPts از دو عدد xG خودِ بازی با
    Dixon-Coles (analytics/metrics.py) — همان فرمول استودیو.
  - رنگ‌ها فقط از brand.json (بخش postmatch_palette)؛ رنگ تیم‌ها از
    config/team_identities.json؛ هیچ هگز در قالب هاردکد نیست.
  - null≠0: متریک غایب → آن ردیف/ماژول اصلاً رندر نمی‌شود.
  - ماژول‌های بدون دادهٔ فعلی (MOTM، موج ۱۵دقیقه‌ای، گلزنان دقیقه‌دار) کدشان
    محفوظ است و با رسیدن provider فعال می‌شوند.
  - ارقام آماری لاتین با tabular-nums؛ تاریخ جلالی با ارقام فارسی (D16).
"""
from __future__ import annotations

import base64
import re
from pathlib import Path

from src.xgpedia.config import ROOT, load_brand, team_identity
from src.xgpedia.render.cards import (
    FORMATS,
    NO_DATA,
    _brand_avatar_data_uri,
    _contrast_text,
    _crest_html,
    _crosshairs,
    _font_faces,
    _trend_context,
    display_colors,
    fmt_fixed,
    fmt_stat,
    jalali_date,
    season_short,
)

BRAND_LOGO_DIR = ROOT / "brand" / "logo" / "svg"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

# رجیستری ماژول‌های کارت پس‌از‌بازی — عین MODULE_DEFS استودیو.
# can_half، default_span؛ ماژول بدون دادهٔ فعلی (motm/momentum) فقط رزرو است.
POST_MODULE_DEFS = [
    ("stats", False, "full"),
    ("trend10", True, "half"),
    ("story", True, "half"),
    ("shotquality", True, "half"),
    ("motm", True, "half"),
    ("momentum", True, "half"),
    ("verdict", False, "full"),
]

# ترتیب جذابیت ماژول‌های نیم‌عرض برای smart — روایت تحریریه هستهٔ کارت است؛
# بعد از آن نمودارهای داده‌محور به ترتیب «خفن‌بودن».
POST_SMART_PRIORITY = ["story", "trend10", "shotquality"]

# ظرفیت ماژول‌های نیم‌عرض در هر فرمت (تا grid بدون خانهٔ خالی/سرریز پر شود)
POST_HALF_CAPACITY = {"4:5": 2, "9:16": 4, "16:9": 2}

_POST_PALETTE_CACHE: dict | None = None


def _post_palette() -> dict:
    global _POST_PALETTE_CACHE
    if _POST_PALETTE_CACHE is None:
        _POST_PALETTE_CACHE = load_brand()["postmatch_palette"]
    return _POST_PALETTE_CACHE


def _brand_logo_uri_light(mono: bool = False) -> str | None:
    """SVG رسمی برند برای زمینهٔ روشن (خاکی) — همان الگوی data-URI نشان تیم‌ها.

    mono=False → logo.svg عیناً (XG سرمه‌ای + PEDIA قرمز — روی کرم خوانا).
    mono=True  → تک‌رنگ قهوه‌ای تیرهٔ متن تم: هر دو fill فایل رسمی به text_main.
    """
    src = BRAND_LOGO_DIR / "logo.svg"
    if not src.exists():
        return None
    svg = src.read_text(encoding="utf-8")
    if mono:
        ink = _post_palette()["text_main"]
        svg = re.sub(r'fill="#[0-9A-Fa-f]{6}"', f'fill="{ink}"', svg)
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def _readable_team_ink(hex_color: str, palette: dict) -> str:
    """رنگ خوانا برای اعداد/متن تیمی روی زمینهٔ روشن — عین getReadableTeamInk استودیو.

    رنگ خیلی روشن (سفید/زرد تیم‌ها) روی کرم ناخواناست → متن قهوه‌ای تیرهٔ تم.
    """
    from src.xgpedia.render.cards import _luminance

    if _luminance(hex_color) > 0.62:
        return palette["text_main"]
    return hex_color


def _glow_color(hex_color: str, min_lightness: float = 0.52) -> str:
    """رنگ درخشش محیطی تیم — رنگ‌های تیره (مثل سرمه‌ای چلسی) روی زمینه روشن/تیره
    محو دیده می‌شوند؛ روشنایی به حداقل داده‌شده کشیده می‌شود، فام و اشباع عین تیم.

    مشتق قطعی از خود رنگ تیم — هیچ رنگی هاردکد نیست (قاعدهٔ brand.json).
    """
    import colorsys

    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = max(l, min_lightness)
    r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
    return f"#{round(r2 * 255):02X}{round(g2 * 255):02X}{round(b2 * 255):02X}"


def _select_post_modules(version: str, has: dict[str, bool], fmt: str = "4:5") -> list[dict]:
    """انتخاب ماژول‌ها — smart داده‌محور و فضاآگاه؛ v1/v2/v3 عین استودیو.

    smart: stats همیشه (اگر ردیف دارد)؛ نیم‌عرض‌های موجود به ترتیب جذابیت تا
    ظرفیت فرمت (تا فضا پر شود ولی سرریز نکند)؛ verdict در انتها.
    """
    if version == "smart":
        preset: list[tuple[str, str]] = []
        if has.get("stats"):
            preset.append(("stats", "full"))
        avail = [m for m in POST_SMART_PRIORITY if has.get(m)]
        cap = POST_HALF_CAPACITY.get(fmt, 2)
        preset += [(m, "half") for m in avail[:cap]]
        if has.get("verdict"):
            preset.append(("verdict", "full"))
    else:
        presets = {
            "v1": [("stats", "full"), ("trend10", "half"), ("story", "half"), ("verdict", "full")],
            "v2": [("stats", "full"), ("trend10", "half"), ("shotquality", "half"), ("verdict", "full")],
            "v3": [("stats", "full"), ("story", "half"), ("shotquality", "half"), ("verdict", "full")],
        }
        preset = presets.get(version, presets["v1"])
    selected = [
        {"id": mod_id, "enabled": has.get(mod_id, False), "span": span}
        for mod_id, _can_half, default_span in POST_MODULE_DEFS
        for span in [next((s for m, s in preset if m == mod_id), default_span)]
        if any(m == mod_id for m, _s in preset)
    ]
    # نیم‌عرض یتیم (بدون جفت در همان ردیف grid) تمام‌عرض می‌شود تا خانهٔ خالی نماند
    enabled_halves = [m for m in selected if m["enabled"] and m["span"] == "half"]
    if len(enabled_halves) % 2 == 1:
        enabled_halves[-1]["span"] = "full"
    return selected


def _side_stats(facts_side: dict) -> dict[str, float | None]:
    """متریک‌های خودِ بازی یک طرف — {metric: value}؛ غایب → کلید نیست."""
    ms = facts_side.get("match_stats") or {}
    out = {}
    for key, node in ms.items():
        if isinstance(node, dict) and node.get("value") is not None:
            out[key] = float(node["value"])
    return out


def _comp_rows(hs: dict, as_: dict, palette: dict, h_ink: str, a_ink: str) -> list[dict]:
    """ردیف‌های ماژول آمار — فقط متریک‌هایی که هر دو طرف مقدار دارند (مقایسهٔ نیمه‌خالی گمراه‌کننده است)."""
    rows = []
    for label, metric, dec, suffix, sub_metric in (
        ("امید گل واقعی (xG)", "expected_goals", 2, "", None),
        ("شوت کل (در چارچوب)", "total_shots", 0, "", "shots_on_target"),
        ("کرنر", "corner_kicks", 0, "", None),
        ("خطا", "fouls", 0, "", None),
        ("کارت زرد", "yellow_cards", 0, "", None),
        ("کارت قرمز", "red_cards", 0, "", None),
    ):
        hv, av = hs.get(metric), as_.get(metric)
        if hv is None or av is None:
            continue
        max_v = max(hv, av, 0.01)
        sub_h = sub_a = ""
        if sub_metric and hs.get(sub_metric) is not None and as_.get(sub_metric) is not None:
            sub_h = f"({fmt_stat(hs[sub_metric])})"
            sub_a = f"({fmt_stat(as_[sub_metric])})"
        rows.append({
            "label": label,
            "h": fmt_fixed(hv, dec) + suffix, "a": fmt_fixed(av, dec) + suffix,
            "h_pct": f"{hv / max_v * 100:.1f}", "a_pct": f"{av / max_v * 100:.1f}",
            "sub_h": sub_h, "sub_a": sub_a,
            "h_ink": h_ink, "a_ink": a_ink,
        })
    return rows


def build_post_match_context(
    draft: dict,
    facts: dict,
    brand: dict | None = None,
    layout: str = "smart",
    fmt: str = "4:5",
    brand_mono: bool = False,
) -> dict:
    """context کامل کارت پس‌از‌بازی از draft + fact(post_match) + brand.

    همهٔ اعداد از fact_json (result/match_stats/xg_series)؛ متن‌ها از draft_json؛
    رنگ تم از brand.json (postmatch_palette)؛ رنگ تیم‌ها از team_identities.json.
    """
    from src.xgpedia.analytics.metrics import dixon_coles_matrix, expected_points

    b = brand or load_brand()
    t = dict(b["postmatch_palette"])
    home_f, away_f = facts.get("home", {}), facts.get("away", {})

    home_ident = team_identity(home_f.get("name_en", ""))
    away_ident = team_identity(away_f.get("name_en", ""))
    hc, ac = display_colors(home_ident, away_ident, t["verdict_sky"])

    def side_ctx(f: dict, ident: dict | None, color: str, key: str) -> dict:
        ink = _readable_team_ink(color, t)
        ctx = {
            "name_fa": f.get("name_fa", ""),
            "name_en": f.get("name_en", ""),
            "code": (ident or {}).get("code") or (f.get("name_en") or "FC")[:3].upper(),
            "color": color,
            "ink": ink,
            "scorers": None,  # دادهٔ گلزنان در provider فعلی نیست — با رسیدن، فعال می‌شود
        }
        ctx["crest_html"] = _crest_html(f.get("name_en", ""), {
            "name_fa": ctx["name_fa"], "code": ctx["code"], "name_en": ctx["name_en"],
            "primary": (ident or {}).get("colors", {}).get("primary") or color,
            "secondary": (ident or {}).get("colors", {}).get("secondary") or t["text_main"],
        }, key)
        return ctx

    home = side_ctx(home_f, home_ident, hc, "home")
    away = side_ctx(away_f, away_ident, ac, "away")

    # ── نتیجه + آمار خودِ بازی ──
    result = facts.get("result") or {}
    hs, as_ = _side_stats(home_f), _side_stats(away_f)
    hg = result.get("home_goals")
    ag = result.get("away_goals")
    hxg, axg = hs.get("expected_goals"), as_.get("expected_goals")

    # ── احتمال‌های ۱X۲ و xPts از xG خودِ بازی (Dixon-Coles — همان فرمول استودیو) ──
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

    def finish_delta(goals: float | None, xg: float | None) -> str | None:
        if goals is None or xg is None:
            return None
        d = goals - xg
        return f"{'+' if d >= 0 else ''}{fmt_fixed(d, 2)}"

    hero = {
        "xg_home": fmt_fixed(hxg, 2), "xg_away": fmt_fixed(axg, 2),
        "xg_total": fmt_fixed((hxg or 0) + (axg or 0), 2) if hxg is not None and axg is not None else None,
        "xpts_home": xpts_h, "xpts_away": xpts_a,
        "delta_home": finish_delta(hg, hxg), "delta_away": finish_delta(ag, axg),
    }
    capsule = None
    if probs:
        capsule = [
            {"id": "home", "pct": probs["home"], "bg": hc, "color": _contrast_text(hc)},
            {"id": "draw", "pct": probs["draw"], "bg": t["draw_grey"], "color": "#F8FAFC"},
            {"id": "away", "pct": probs["away"], "bg": ac, "color": _contrast_text(ac)},
        ]

    # ── هندسهٔ بوم (خطوط زمین/پیرامون عین استودیو) + نور محیطی قوی‌تر رنگ تیم‌ها ──
    w, hgt = FORMATS.get(fmt, FORMATS["4:5"])
    inset = 12
    ambient_alpha = t["ambient_alpha"]
    # درخشش محیطی از رنگ «قابل‌دید»ٔ تیم — رنگ تیره (سرمه‌ای) روی کرم محو می‌شود
    glow_h, glow_a = _glow_color(hc), _glow_color(ac)
    pitch = {
        "w": w, "h": hgt,
        "perimeter": f"{inset} {inset} {w - inset * 2} {hgt - inset * 2}",
        "halfway": f"{w // 2} {inset} {w // 2} {hgt - inset}",
        "left_box": "12 125 145 340",
        "right_box": f"{w - inset - 145} 125 145 340",
        "center_circle_cy": 295,
        "crosshairs": _crosshairs(w, hgt, inset),
        "ambient": (
            f"radial-gradient(circle at 86% 28%, {glow_h}{ambient_alpha} 0%, transparent 52%),"
            f"radial-gradient(circle at 14% 28%, {glow_a}{ambient_alpha} 0%, transparent 52%)"
        ),
    }
    score_size = {"4:5": 128, "9:16": 138, "16:9": 106}.get(fmt, 128)

    # ── ماژول‌ها ──
    stats_rows = _comp_rows(hs, as_, t, home["ink"], away["ink"])

    bullets = [x for x in draft.get("bullets", []) if x]
    story = None
    if draft.get("title"):
        story = {"title": draft["title"], "body_lines": bullets[:3], "tag": None}
        if not bullets and draft.get("caption"):
            story["body_lines"] = [draft["caption"]]

    trend_ctx = None
    h_series, a_series = home_f.get("xg_series"), away_f.get("xg_series")
    if h_series and a_series and len(h_series) >= 2 and len(a_series) >= 2:
        trend_ctx = _trend_context([float(x) for x in h_series], [float(x) for x in a_series],
                                   True, hc, ac)

    shot_rows = []
    if hs.get("total_shots") is not None and as_.get("total_shots") is not None:
        items = [
            ("شوت کل", fmt_stat(hs["total_shots"]), fmt_stat(as_["total_shots"])),
            ("شوت در چارچوب", fmt_stat(hs.get("shots_on_target")), fmt_stat(as_.get("shots_on_target"))),
        ]
        if hxg is not None and axg is not None:
            items.append((
                "کیفیت هر شوت (xG / Shot)",
                fmt_fixed(hxg / max(1, hs["total_shots"]), 2),
                fmt_fixed(axg / max(1, as_["total_shots"]), 2),
            ))
        shot_rows = [
            {"label": lbl, "h": hval, "a": aval, "h_ink": home["ink"], "a_ink": away["ink"]}
            for lbl, hval, aval in items if hval is not None and aval is not None
        ]

    verdict = None
    if hxg is not None and axg is not None and hg is not None and ag is not None:
        gap = abs(hxg - axg)
        if gap < 0.35:
            fair_title, fair_desc = "تساوی عادلانه آماری", "تعادل نزدیک موقعیت‌های دو تیم"
        elif hxg > axg:
            fair_title = f"برتری کیفی {home['name_fa']}"
            fair_desc = f"اختلاف {fmt_fixed(gap, 2)} امید گل"
        else:
            fair_title = f"برتری کیفی {away['name_fa']}"
            fair_desc = f"اختلاف {fmt_fixed(gap, 2)} امید گل"
        dh, da = hg - hxg, ag - axg
        best_name = home["name_fa"] if dh >= da else away["name_fa"]
        best_delta = max(dh, da)
        tempo = "بازی باز و پرتهاجم" if (hxg + axg) >= 3.0 else "نبرد تاکتیکی و فشرده"
        total_shots_n = None
        if hs.get("total_shots") is not None and as_.get("total_shots") is not None:
            total_shots_n = fmt_stat(hs["total_shots"] + as_["total_shots"])
        verdict = {
            "fair_title": fair_title, "fair_desc": fair_desc,
            "fair_value": f"{fmt_fixed(hxg, 1)}-{fmt_fixed(axg, 1)}",
            "fin_best": best_name,
            "fin_value": f"{'+' if best_delta >= 0 else ''}{fmt_fixed(best_delta, 2)}",
            "tempo": tempo, "tempo_value": total_shots_n, "tempo_label": "مجموع شوت دو تیم",
        }

    has = {
        "stats": bool(stats_rows),
        "story": story is not None,
        "trend10": trend_ctx is not None,
        "shotquality": bool(shot_rows),
        "motm": False,      # دادهٔ بازیکن در provider فعلی نیست — رزرو
        "momentum": False,  # دیتای رویدادی — فاز بعدی
        "verdict": verdict is not None,
    }
    modules = _select_post_modules(layout, has, fmt)

    # ── هدر و پانویس ──
    comp_en = facts.get("competition", {}).get("name", "")
    season = facts.get("competition", {}).get("season", "")
    comp_fa = {"Premier League": "لیگ برتر انگلیس"}.get(comp_en, comp_en)
    kickoff = facts.get("kickoff_utc", "")
    prov = facts.get("source", {}).get("provider", "")
    micro_tag = " ".join(x for x in (
        (comp_en or "FOOTBALL").upper(),
        season_short(season) if season else "",
    ) if x) + " // POST - MATCH"

    logo_uri = _brand_logo_uri_light(brand_mono)
    brand_lockup_html = (
        f'<div class="brand-logo-lockup" dir="ltr"><img src="{logo_uri}" alt="XGPedia" class="brand-logo-img" /></div>'
        if logo_uri
        else ""
    )

    return {
        "t": t,
        "fonts": _font_faces(),
        "brand_name": b.get("brand", "XGPedia"),
        "brand_lockup_html": brand_lockup_html,
        "brand_mono": brand_mono,
        "brand_favicon_uri": _brand_avatar_data_uri(),
        "handle": "@xgpedia",
        "domain": (b.get("handles", {}).get("domain") or ["xgpedia.com"])[0],
        "na_label": NO_DATA,
        "format": {"key": fmt, "w": w, "h": hgt, "is_wide": fmt == "16:9", "is_tall": fmt == "9:16"},
        "pitch": pitch,
        "score_size": score_size,
        "competition_fa": comp_fa,
        "round_fa": "گزارش آماری پس از بازی",
        "stadium": facts.get("stadium"),
        "broadcast": "پایان بازی",
        "day": jalali_date(kickoff) if kickoff else "",
        "home": home,
        "away": away,
        "score": {"home": hg, "away": ag},
        "hero": hero,
        "capsule": capsule,
        "modules": modules,
        "module_data": {
            "stats": {"rows": stats_rows},
            "story": story,
            "trend10": trend_ctx,
            "shotquality": {"rows": shot_rows},
            "verdict": verdict,
        },
        "micro_tag": micro_tag,
        "source_label": f"منبع: {prov}" if prov else "",
    }


def render_post_match_html(
    draft: dict,
    facts: dict,
    layout: str = "smart",
    fmt: str = "4:5",
    brand_mono: bool = False,
) -> str:
    """پر کردن قالب پس‌از‌بازی و برگرداندن HTML کامل (خودبسنده — فونت جاسازی‌شده)."""
    from jinja2 import Environment, FileSystemLoader

    env = Environment(autoescape=True, loader=FileSystemLoader(str(TEMPLATES_DIR)))
    ctx = build_post_match_context(draft, facts, layout=layout, fmt=fmt, brand_mono=brand_mono)
    return env.get_template("post_match.html.j2").render(**ctx)


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
) -> tuple[Path, Path, Path]:
    """رندر کامل پست پس‌از‌بازی: HTML میانی + تصویر نهایی + کپشن آمادهٔ انتشار."""
    from src.xgpedia.render.render_png import render_sync

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    w, hgt = FORMATS.get(fmt, FORMATS["4:5"])
    stem = f"post_{post_id}_v{version}_post_match"
    html_path = out / f"{stem}_{w}x{hgt}.html"
    html_path.write_text(
        render_post_match_html(draft, facts, layout=layout, fmt=fmt, brand_mono=brand_mono),
        encoding="utf-8",
    )

    img_fmt = "jpeg" if platform == "instagram" else "png"
    img_path = out / f"{stem}_{w}x{hgt}.{img_fmt}"
    render_sync(str(html_path), str(img_path), w, hgt, img_fmt)

    caption = (draft.get("caption") or "").strip()
    cap_path = out / f"post_{post_id}_v{version}_caption.txt"
    cap_path.write_text(caption + "\n\n#پس_از_بازی", encoding="utf-8")

    return html_path, img_path, cap_path
