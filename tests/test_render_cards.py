"""آزمون‌های لایهٔ رندر — کارت استودیو از draft+fact+brand+identities، null≠0 و رندر واقعی.

اجرا:  python -m pytest tests/test_render_cards.py -v
پوشش:
  - تاریخ جلالی و ساعت تهران (کیک‌آف نیمه‌شب CSV → بدون ساعت؛ ساعت‌دار → نمایش)
  - ارقام آماری لاتین / ارقام فارسی برای تاریخ (سیاست numerals_policy برند)
  - fmt_stat (بدون صفر پایانی) و fmt_fixed (اعشار ثابت — عین toFixed استودیو)
  - null≠0: شاخص/ماژول غایب → رندر نمی‌شود؛ هرگز صفر یا خط تیره جایگزین نمی‌شود
  - رنگ فقط از brand.json (matchday_palette) + team_identities.json تزریق می‌شود
  - احتمال‌های ۱X۲ فقط از Dixon-Coles روی xG فکت‌ها مشتق می‌شوند
  - ماژول‌ها: smart فقط با داده روشن می‌شود؛ ماژول بی‌داده در HTML نیست
  - لوگوی رسمی برند data-URI در سرصفحه: دوبنگی (XG سفید + PEDIA قرمز) و مونو سفید؛ فاوآیکون آواتار
  - رندر واقعی Playwright → PNG/JPEG سالم و غیرخالی در هر سه فرمت
"""
from __future__ import annotations

import base64
import json
import re

import pytest

from src.xgpedia.config import load_brand, load_team_identities
from src.xgpedia.render.cards import (
    NO_DATA,
    build_preview_context,
    fa_digits,
    fmt_fixed,
    fmt_stat,
    jalali_date,
    render_preview_html,
    season_short,
    tehran_clock,
)

RENDER_DEPS = pytest.importorskip("jinja2", reason="render extras not installed")
pytest.importorskip("jdatetime", reason="render extras not installed")


def _facts(**overrides) -> dict:
    """فکت‌های نمونه — همان ساختار fact_json آرشیوشده در posts (با فیلدهای v10)."""
    base = {
        "fixture_id": "fdcouk:2026-11-08:Arsenal:Liverpool",
        "competition": {"name": "Premier League", "season": "2026-27"},
        "kickoff_utc": "2026-11-08T16:30:00Z",
        "source": {
            "provider": "football-data-co-uk",
            "collected_at": "2026-11-15T09:50:36Z",
            "payload_hash": "d598a5f681e1a9a4acf9dad9fb203b68da6f67e2d195678dbe99e95fbba14593",
        },
        "home": {
            "name_fa": "آرسنال", "name_en": "Arsenal",
            "last5": {"n": 5, "points": 13, "goals_for": 9, "goals_against": 3},
            "xg_for_avg": {"value": 1.53, "n": 9, "provider": "football-data-co-uk"},
            "corners_avg": {"value": 5.8, "n": 10, "provider": "football-data-co-uk"},
            "xg_against_avg": {"value": 0.71, "n": 9, "provider": "football-data-co-uk"},
            "sot_avg": {"value": 6.4, "n": 9, "provider": "football-data-co-uk"},
            "xg_series": [1.2, 1.9, 0.8, 2.1, 1.4, 1.7, 2.3, 1.1, 1.6, 1.53],
            "recent_form": {"sequence": "WWDWL", "n": 5},
        },
        "away": {
            "name_fa": "لیورپول", "name_en": "Liverpool",
            "last5": {"n": 5, "points": 13, "goals_for": 11, "goals_against": 4},
            "xg_for_avg": {"value": 1.4, "n": 9, "provider": "football-data-co-uk"},
            "corners_avg": {"value": 4.9, "n": 10, "provider": "football-data-co-uk"},
            "xg_against_avg": {"value": 0.82, "n": 9, "provider": "football-data-co-uk"},
            "sot_avg": {"value": 5.7, "n": 9, "provider": "football-data-co-uk"},
            "xg_series": [1.1, 1.6, 2.0, 1.3, 1.8, 1.2, 2.2, 1.5, 1.9, 1.4],
            "recent_form": {"sequence": "WWWDW", "n": 5},
        },
        "availability": [],
        "triggers": [],
        "data_quality": {"missing_fields": []},
    }
    base.update(overrides)
    return base


def _draft(**overrides) -> dict:
    base = {
        "status": "ok",
        "title": "نبرد صدرنشینان در امارات",
        "bullets": [
            "فرم اخیر (n=5): آرسنال ۱۳ امتیاز و لیورپول ۱۳ امتیاز.",
            "میانگین امید گل (xG) در n=9 بازی: آرسنال 1.53 و لیورپول 1.4.",
        ],
        "caption": "پیش‌بازی لیگ برتر انگلیس",
        "source_note": "منبع داده: football-data-co-uk · جمع‌آوری 2026-11-15 09:50 (UTC)",
        "uncertainties": [],
    }
    base.update(overrides)
    return base


# ─── تاریخ جلالی و ساعت تهران ───

def test_jalali_date_with_fa_digits():
    assert jalali_date("2026-11-08T00:00:00") == "یک‌شنبه ۱۷ آبان ۱۴۰۵"


def test_jalali_date_saturday_mapping():
    assert jalali_date("2026-11-07T15:00:00Z").startswith("شنبه")


def test_tehran_clock_midnight_csv_has_no_time():
    """CSV ساعت ندارد (00:00:00) → None → کارت فقط تاریخ نشان می‌دهد."""
    assert tehran_clock("2026-11-08T00:00:00") is None


def test_tehran_clock_afternoon_kickoff():
    assert tehran_clock("2026-11-08T16:30:00Z") == "۲۰:۰۰"


def test_fa_digits_only_for_dates():
    assert fa_digits(1405) == "۱۴۰۵"


# ─── سیاست ارقام ───

def test_fmt_stat_latin_digits_and_dot():
    assert fmt_stat(1.53, 2) == "1.53"
    assert fmt_stat(11, 0) == "11"
    assert fmt_stat(5.8, 1) == "5.8"


def test_fmt_stat_none_stays_none():
    """null≠0 — مقدار غایب None می‌ماند؛ تبدیل به صفر ممنوع."""
    assert fmt_stat(None, 2) is None


def test_fmt_fixed_keeps_trailing_zeros():
    """عین toFixed استودیو: 2.0 → «2.00»."""
    assert fmt_fixed(2.0, 2) == "2.00"
    assert fmt_fixed(None, 2) is None


def test_season_short():
    assert season_short("2026-27") == "26/27"
    assert season_short("odd-input") == "odd-input"


# ─── context: احتمال‌ها فقط از Dixon-Coles روی xG فکت‌ها ───

def test_context_probabilities_derived_from_xg():
    ctx = build_preview_context(_draft(), _facts())
    probs = ctx["hero"]["probs"]
    assert probs is not None
    assert probs["home"] + probs["draw"] + probs["away"] == 100
    assert all(p >= 5 for p in probs.values())


def test_context_no_xg_no_probs_no_capsule():
    """xG غایب → نه احتمال، نه کپسول، نه ضریب — و هیچ 0 جعلی در کارت."""
    facts = _facts()
    facts["home"]["xg_for_avg"] = None
    ctx = build_preview_context(_draft(), facts)
    assert ctx["hero"]["probs"] is None
    assert ctx["hero"]["capsule"] is None
    assert ctx["hero"]["odds"] is None
    html = render_preview_html(_draft(), facts)
    assert '<div class="prob-capsule">' not in html  # CSS کلاسش هست؛ DOM نباشد
    assert '<div class="odds-row">' not in html


def test_context_hero_xg_values_latin_fixed():
    ctx = build_preview_context(_draft(), _facts())
    assert ctx["hero"]["xg_home"] == "1.53"
    assert ctx["hero"]["xg_away"] == "1.40"
    assert ctx["hero"]["xg_total"] == "2.93"


def test_context_stats_rows_only_when_both_sides_have_data():
    ctx = build_preview_context(_draft(), _facts())
    rows = ctx["module_data"]["stats"]["rows"]
    assert [r["label"] for r in rows] == [
        "امید گل تولیدی (xG / 90)",
        "امید گل دریافتی (xGA / 90)",
        "شوت در چارچوب (SOT / 90)",
    ]
    facts = _facts()
    facts["away"]["sot_avg"] = None  # یک طرف غایب → ردیف مقایسهٔ نیمه‌خالی رسم نمی‌شود
    rows2 = build_preview_context(_draft(), facts)["module_data"]["stats"]["rows"]
    assert len(rows2) == 2


def test_context_team_colors_from_identities():
    """رنگ میزبان/میهمان از team_identities.json — و دو تیم هرگز یک‌رنگ نیستند."""
    idents = load_team_identities()["teams"]
    ctx = build_preview_context(_draft(), _facts())
    assert ctx["home"]["color"] == idents["Arsenal"]["colors"]["primary"]  # #EF0107
    # لیورپول قرمزِ نزدیک آرسنال است → رنگ نمایشی ثانویه (طلایی)
    assert ctx["away"]["color"] == idents["Liverpool"]["colors"]["secondary"]  # #F6EB61


def test_context_team_codes_from_identities():
    ctx = build_preview_context(_draft(), _facts())
    assert ctx["home"]["code"] == "ARS"
    assert ctx["away"]["code"] == "LIV"


def test_context_crest_uses_real_svg_when_available():
    """لوگوی svg واقعی → img با data URI؛ بدون فایل → نشان انتزاعی یک‌دست استودیو."""
    from src.xgpedia.config import team_crest_path

    ctx = build_preview_context(_draft(), _facts())
    if team_crest_path("Arsenal") is not None:  # tools/fetch_crests.py اجرا شده باشد
        assert ctx["home"]["crest_html"].startswith('<img src="data:image/svg+xml;base64,')
    else:
        assert ctx["home"]["crest_html"].startswith("<svg")

    # تیم بدون فایل لوگو → نشان انتزاعی استودیو با کد سه‌حرفی
    facts = _facts()
    facts["away"] = {
        "name_fa": "رئال مادرید", "name_en": "Real Madrid",
        "xg_for_avg": {"value": 1.1, "n": 9, "provider": "football-data-co-uk"},
    }
    ctx2 = build_preview_context(_draft(), facts)
    assert ctx2["away"]["crest_html"].startswith("<svg")
    assert ">REA<" in ctx2["away"]["crest_html"]


def test_context_form_dots_from_recent_form():
    ctx = build_preview_context(_draft(), _facts())
    assert [d["f"] for d in ctx["home"]["form_dots"]] == ["W", "W", "D", "W", "L"]
    assert [d["label"] for d in ctx["home"]["form_dots"]] == ["ب", "ب", "م", "ب", "ش"]


def test_context_trend10_from_xg_series():
    ctx = build_preview_context(_draft(), _facts())
    trend = ctx["module_data"]["trend10"]
    assert trend is not None
    assert trend["home_avg"] == "1.56"  # میانگین سری آرسنال
    assert len(trend["home_dots"]) == 10


def test_context_signals_from_poisson_and_corners():
    ctx = build_preview_context(_draft(), _facts())
    cards = ctx["module_data"]["signals"]["cards"]
    assert [c["tone"] for c in cards] == ["emerald", "sky", "amber"]
    # بدون دادهٔ ضریب بوک‌میکر، badge EV ساخته نمی‌شود (قاعدهٔ عدم جعل)
    assert all(c["badge"] is None for c in cards)


# ─── ماژول‌ها: smart فقط با داده ───

def test_smart_modules_enabled_set():
    """smart فضاآگاه: با دادهٔ کامل، نمودارهای داده‌محور (poisson/trend10) هم انتخاب می‌شوند."""
    ctx = build_preview_context(_draft(), _facts())
    ids = [m["id"] for m in ctx["modules"] if m["enabled"]]
    # ترتیب رجیستری MODULE_DEFS: stats, focus, poisson, trend10, signals (سمت چپ news)
    assert ids == ["stats", "focus", "poisson", "trend10", "signals"]


def test_smart_fills_space_and_respects_capacity():
    """ظرفیت فرمت: 16:9 دو نیم‌عرض می‌گیرد؛ 9:16 تا شش — پرکردن فضا بدون سرریز."""
    ctx_wide = build_preview_context(_draft(), _facts(), fmt="16:9")
    halves_wide = [m for m in ctx_wide["modules"] if m["enabled"] and m["span"] == "half"]
    assert len(halves_wide) == 2  # poisson + trend10 (خفن‌ترین‌ها اول)
    ids_wide = [m["id"] for m in ctx_wide["modules"] if m["enabled"]]
    assert "poisson" in ids_wide and "trend10" in ids_wide


def test_smart_with_minimal_data_still_fills():
    """کمترین داده: بدون سری و بدون xG — stats + focus + signals حاضرند و یتیم تمام‌عرض می‌شود."""
    facts = _facts()
    for side in ("home", "away"):
        facts[side]["xg_series"] = None
        facts[side]["xg_for_avg"] = None
    ctx = build_preview_context(_draft(), facts)
    ids = [m["id"] for m in ctx["modules"] if m["enabled"]]
    assert ids == ["stats", "focus", "signals"]
    focus = next(m for m in ctx["modules"] if m["id"] == "focus")
    assert focus["span"] == "full"  # نیم‌عرض یتیم → تمام‌عرض تا خانهٔ خالی نماند


def test_modules_without_data_absent_from_html():
    """ماژول بی‌داده (رادار/مهرهٔ کلیدی/هشدار/موج) در HTML کارت نیست — فقط کدش محفوظ است."""
    html = render_preview_html(_draft(), _facts())
    assert "رادار ۶ محوره تاکتیکی" not in html
    assert "تقابل مهره‌های کلیدی" not in html
    assert "موج زمانی امید گل" not in html
    assert "باید حواسشون بهش باشه" not in html


def test_layout_v2_adds_poisson_when_xg_available():
    html = render_preview_html(_draft(), _facts(), layout="v2")
    assert "ماتریس احتمال دقیق نتیجه" in html
    assert "مدل پواسون ۵×۵" in html
    # ردیف‌های ماتریس: ارقام لاتین «0-0»
    assert ">0-0<" in html


# ─── برند: رنگ/فونت فقط از brand.json و identities ───

def test_palette_comes_from_brand_json():
    brand = load_brand()
    ctx = build_preview_context(_draft(), _facts())
    assert ctx["palette"] == brand["matchday_palette"]


def test_html_style_has_no_hardcoded_brand_hex():
    """داخل <style> فقط متغیرهای پالت — هیچ هگز برندی هاردکد نیست."""
    html = render_preview_html(_draft(), _facts())
    style_part = html.split("<style>")[1].split("</style>")[0]
    hexes = set(re.findall(r"#[0-9A-Fa-f]{6}\b", style_part))
    allowed = set(load_brand()["matchday_palette"].values())
    allowed |= set(load_brand()["colors"].values())  # paper/ink و سایر رنگ‌های پایهٔ برند
    idents = load_team_identities()["teams"]
    for t in ("Arsenal", "Liverpool"):  # متغیرهای --home-color/--away-color از identities تزریق می‌شوند
        allowed |= set(idents[t]["colors"].values())
    allowed |= {load_team_identities()["contrast_fallback_color"]}
    assert hexes <= allowed, f"hardcoded colors outside palette: {hexes - allowed}"


def test_fonts_embedded_as_data_uri():
    html = render_preview_html(_draft(), _facts())
    assert "data:font/woff2;base64," in html
    assert html.count("@font-face") == 6  # ۴ وزن Vazirmatn + JetBrains Mono + Space Grotesk
    assert "font-family: 'Space Grotesk'" in html
    assert "font-family: 'JetBrains Mono'" in html


def test_latin_handle_isolated_in_footer():
    """هندل/دامنه لاتین در پانویس RTL جدا ایزوله می‌شوند (dir=ltr)."""
    html = render_preview_html(_draft(), _facts())
    assert '<div class="footer-right">' in html
    assert "@xgpedia" in html


def test_identity_codes_match_glossary():
    """کد هر تیم در team_identities باید با glossary_fa.json یکی باشد."""
    glossary = json.load(open("config/glossary_fa.json", encoding="utf-8"))
    g_ids = {t["id"] for t in glossary["teams"]}
    i_codes = {t["code"] for t in load_team_identities()["teams"].values()}
    assert i_codes == g_ids


# ─── فرمت‌های استودیو ───

def test_formats_change_artboard_dimensions():
    for fmt, (w, h) in (("4:5", (1080, 1350)), ("9:16", (1080, 1920)), ("16:9", (1920, 1080))):
        html = render_preview_html(_draft(), _facts(), fmt=fmt)
        assert f"width: {w}px; height: {h}px;" in html
    html169 = render_preview_html(_draft(), _facts(), fmt="16:9")
    assert 'class="fmt-169"' in html169


# ─── رندر واقعی Playwright (smoke) ───

def test_render_real_png(tmp_path):
    pytest.importorskip("playwright", reason="playwright not installed")
    from src.xgpedia.render.cards import render_preview_card

    html_path, img_path, cap_path = render_preview_card(
        _draft(), _facts(), out_dir=tmp_path, post_id=1, version=1, platform="telegram"
    )
    assert img_path.exists() and img_path.stat().st_size > 50_000  # PNG واقعی، نه خالی
    assert cap_path.read_text(encoding="utf-8").endswith("#پیش_بازی")
    assert html_path.name == "post_1_v1_preview_1080x1350.html"

    try:
        from PIL import Image
    except ImportError:
        return  # Pillow اختیاری است — راستی‌آزمایی ابعاد فقط اگر نصب بود

    with Image.open(img_path) as im:
        assert im.size == (1080, 1350)
        g = im.convert("L")
        h = g.histogram()
        non_white = 1 - h[255] / sum(h)
        assert non_white > 0.5  # کارت تیره است — نباید سفید/خالی باشد


def test_render_real_story_format(tmp_path):
    pytest.importorskip("playwright", reason="playwright not installed")
    from src.xgpedia.render.cards import render_preview_card

    _html, img_path, _cap = render_preview_card(
        _draft(), _facts(), out_dir=tmp_path, post_id=2, version=1,
        platform="telegram", fmt="9:16",
    )
    assert img_path.name == "post_2_v1_preview_1080x1920.png"
    try:
        from PIL import Image
    except ImportError:
        return
    with Image.open(img_path) as im:
        assert im.size == (1080, 1920)


# ─── مرحلهٔ ۱: لوگوی رسمی برند در سرصفحه (data-URI) + فاوآیکون آواتار ───


def _decoded_brand_svg(lockup_html: str) -> str:
    m = re.search(r'src="data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)"', lockup_html)
    assert m, "official brand logo must be embedded as a data-URI <img>"
    return base64.b64decode(m.group(1)).decode("utf-8")


def test_official_brand_logo_embedded_duotone():
    """حالت پیش‌فرض: SVG رسمی برند به‌صورت data-URI — نسخهٔ معکوس رسمی (XG سفید + PEDIA قرمز)."""
    from src.xgpedia.config import ROOT

    ctx = build_preview_context(_draft(), _facts())
    assert ctx["brand_mono"] is False
    svg = _decoded_brand_svg(ctx["brand_lockup_html"])
    src = (ROOT / "brand" / "logo" / "svg" / "logo.svg").read_text(encoding="utf-8")
    first_fill = re.search(r'fill="#[0-9A-Fa-f]{6}"', src).group(0)
    # فقط fillِ نخستِ فایل رسمی (سرمه‌ای XG) سفید شده؛ بقیهٔ فایل عین رسمی است
    assert svg == src.replace(first_fill, 'fill="#FFFFFF"', 1)
    assert 'class="brand-logo-img"' in ctx["brand_lockup_html"]
    assert 'alt="XGPedia"' in ctx["brand_lockup_html"]


def test_official_brand_logo_mono_variant():
    """حالت مونو (brand_mono=True): فایل رسمی تک‌رنگ سفید عیناً و بدون هیچ بازرنگی."""
    from src.xgpedia.config import ROOT

    ctx = build_preview_context(_draft(), _facts(), brand_mono=True)
    assert ctx["brand_mono"] is True
    svg = _decoded_brand_svg(ctx["brand_lockup_html"])
    src = (ROOT / "brand" / "logo" / "svg" / "logo-white.svg").read_text(encoding="utf-8")
    assert svg == src


def test_avatar_favicon_wired_into_head():
    """آواتار مربعی رسمی (logo-xg-white.svg) به‌صورت فاوآیکون در head خروجی نهایی."""
    from src.xgpedia.config import ROOT

    ctx = build_preview_context(_draft(), _facts())
    assert ctx["brand_favicon_uri"].startswith("data:image/svg+xml;base64,")
    avatar_src = (ROOT / "brand" / "logo" / "svg" / "logo-xg-white.svg").read_bytes()
    assert base64.b64encode(avatar_src).decode("ascii") in ctx["brand_favicon_uri"]

    html = render_preview_html(_draft(), _facts())
    assert 'rel="icon"' in html and 'type="image/svg+xml"' in html
    assert "brand-logo-img" in html  # لوگوی رسمی در سرصفحهٔ خروجی نهایی


def test_brand_lockup_falls_back_to_studio_without_files(tmp_path, monkeypatch):
    """بدون فایل‌های رسمی برند → نشان بازسازی استودیو (رفتار قبلی حفظ می‌شود)."""
    from src.xgpedia.render import cards as rc

    monkeypatch.setattr(rc, "BRAND_LOGO_DIR", tmp_path)
    assert rc._brand_lockup_svg().startswith('<div class="masthead-lockup"')
