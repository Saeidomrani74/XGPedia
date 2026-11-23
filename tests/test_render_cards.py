"""آزمون‌های لایهٔ رندر پیش‌ازبازی — موتور قالب استودیویی (`studio_templates/pre_match.html`).

اجرا:  python -m pytest tests/test_render_cards.py -v
پوشش:
  - تاریخ جلالی و ساعت تهران
  - سیاست ارقام و null≠0 (هیچ دیتای جعلی/هاردکد تولید نمی‌شود)
  - احتمال‌های ۱X۲ فقط از Dixon-Coles روی xG فکت‌ها
  - ترتیب اولویت ماژول‌های پیش‌ازبازی (radar → keyduel → signals → wave → trend10 → stats → poisson)
  - انتقال «باید حواسشون بهش باشه» (watchout) به کپشن و عدم نمایش آن روی کارت
  - سازوکار پوشهٔ قالب‌های استودیویی (`studio_templates/`) و رندر عینی بدون تغییر طراحی
  - جلوگیری از نیم‌فضای خالی (zero orphan half-width) و خودبسندگی فونت/CSS
  - رندر واقعی Playwright (در صورت نصب)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.xgpedia.config import load_brand, load_team_identities
from src.xgpedia.render.cards import (
    build_preview_context,
    fa_digits,
    fmt_fixed,
    fmt_stat,
    jalali_date,
    render_preview_html,
    season_short,
    tehran_clock,
)
from src.xgpedia.render.studio_engine import (
    PRE_MATCH_CAPTION_ONLY,
    PRE_MATCH_PRIORITY,
    STUDIO_TEMPLATES_DIR,
    build_card_caption,
    select_studio_modules,
)


def _facts(**overrides) -> dict:
    """فکت‌های واقعی نمونه مطابق خروجی football-data.co.uk."""
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
    assert fmt_stat(None, 2) is None


def test_fmt_fixed_keeps_trailing_zeros():
    assert fmt_fixed(2.0, 2) == "2.00"
    assert fmt_fixed(None, 2) is None


def test_season_short():
    assert season_short("2026-27") == "26/27"
    assert season_short("odd-input") == "odd-input"


# ─── context و null≠0 ───

def test_context_probabilities_derived_from_xg():
    ctx = build_preview_context(_draft(), _facts())
    probs = ctx["hero"]["probs"]
    assert probs is not None
    assert probs["home"] + probs["draw"] + probs["away"] == 100
    assert all(p >= 5 for p in probs.values())


def test_context_no_xg_no_probs_no_capsule():
    facts = _facts()
    facts["home"]["xg_for_avg"] = None
    ctx = build_preview_context(_draft(), facts)
    assert ctx["hero"]["probs"] is None
    assert ctx["hero"]["capsule"] is None
    assert ctx["studio_payload"]["hasProbs"] is False


def test_context_hero_xg_values_latin_fixed():
    ctx = build_preview_context(_draft(), _facts())
    assert ctx["hero"]["xg_home"] == "1.53"
    assert ctx["hero"]["xg_away"] == "1.40"
    assert ctx["hero"]["xg_total"] == "2.93"


def test_context_stats_rows_only_when_both_sides_have_data():
    ctx = build_preview_context(_draft(), _facts())
    rows = ctx["module_data"]["stats"]["rows"]
    assert [r["label"] for r in rows] == [
        "امید گل تولیدی (xG)",
        "امید گل دریافتی (xGA)",
        "شوت در چارچوب (SOT)",
    ]
    facts = _facts()
    facts["away"]["sot_avg"] = None
    rows2 = build_preview_context(_draft(), facts)["module_data"]["stats"]["rows"]
    assert len(rows2) == 2


def test_context_team_colors_and_codes_from_identities():
    idents = load_team_identities()["teams"]
    ctx = build_preview_context(_draft(), _facts())
    assert ctx["home"]["color"] == idents["Arsenal"]["colors"]["primary"]
    assert ctx["away"]["color"] == idents["Liverpool"]["colors"]["secondary"]
    assert ctx["home"]["code"] == "ARS"
    assert ctx["away"]["code"] == "LIV"


def test_context_form_dots_from_recent_form():
    ctx = build_preview_context(_draft(), _facts())
    assert [d["f"] for d in ctx["home"]["form_dots"]] == ["W", "W", "D", "W", "L"]
    assert [d["label"] for d in ctx["home"]["form_dots"]] == ["ب", "ب", "م", "ب", "ش"]


def test_signals_disabled_without_real_market_odds():
    """بدون ضرایب واقعی بازار در facts['market_odds']، ماژول +EV نباید فعال شود."""
    ctx = build_preview_context(_draft(), _facts())
    assert ctx["has"]["signals"] is False
    assert ctx["module_data"]["signals"] is None


def test_signals_enabled_only_with_real_market_odds():
    facts = _facts(market_odds={"home": 2.40, "away": 3.10, "over25": 1.95, "btts": 1.85})
    ctx = build_preview_context(_draft(), facts)
    assert ctx["has"]["signals"] is True
    assert len(ctx["studio_payload"]["signalsItems"]) == 3


# ─── ترتیب اولویت ماژول‌های پیش‌ازبازی و انتقال watchout به کپشن ───

def test_pre_match_priority_order_constant():
    assert PRE_MATCH_PRIORITY == [
        "radar", "keyduel", "signals", "wave", "trend10", "stats", "poisson",
    ]
    assert PRE_MATCH_CAPTION_ONLY == {"watchout"}


def test_smart_modules_follow_user_priority_with_current_real_data():
    """با دیتای واقعی فعلی (trend10 + stats + poisson)، اولویت کاربر رعایت می‌شود."""
    ctx45 = build_preview_context(_draft(), _facts(), fmt="4:5")
    assert [m["id"] for m in ctx45["modules"] if m["enabled"]] == ["trend10", "stats"]
    assert all(m["span"] == "full" for m in ctx45["modules"])

    ctx916 = build_preview_context(_draft(), _facts(), fmt="9:16")
    assert [m["id"] for m in ctx916["modules"] if m["enabled"]] == ["trend10", "stats", "poisson"]

    ctx169 = build_preview_context(_draft(), _facts(), fmt="16:9")
    assert [m["id"] for m in ctx169["modules"] if m["enabled"]] == ["trend10", "stats"]


def test_smart_modules_full_priority_when_all_data_available():
    """وقتی همهٔ داده‌ها موجود باشد، اولویت ۱ تا ۷ دقیقاً رعایت می‌شود."""
    facts = _facts(market_odds={"home": 2.45, "away": 3.0, "over25": 1.90, "btts": 1.80})
    facts["home"]["radar"] = [90, 88, 92, 91, 89, 93]
    facts["away"]["radar"] = [86, 85, 80, 84, 88, 90]
    facts["home"]["kp"] = {"name": "ساکا", "pos": "وینگر", "s1": "0.85", "s2": "3.2 پاس"}
    facts["away"]["kp"] = {"name": "صلاح", "pos": "وینگر", "s1": "0.95", "s2": "3.0 پاس"}
    facts["home"]["wave"] = [0.2, 0.3, 0.4, 0.3, 0.4, 0.3]
    facts["away"]["wave"] = [0.2, 0.25, 0.3, 0.35, 0.3, 0.25]

    ctx45 = build_preview_context(_draft(), facts, fmt="4:5")
    assert [(m["id"], m["span"]) for m in ctx45["modules"]] == [
        ("radar", "half"), ("trend10", "half"), ("signals", "full")
    ]

    ctx916 = build_preview_context(_draft(), facts, fmt="9:16")
    assert [(m["id"], m["span"]) for m in ctx916["modules"]] == [
        ("radar", "half"), ("trend10", "half"), ("signals", "full")
    ]


def test_watchout_never_on_card_and_always_in_caption():
    """متن «باید حواسشون بهش باشه» روی کارت نمی‌آید و در کپشن قرار می‌گیرد."""
    facts = _facts()
    facts["home"]["watchout"] = "ضدحملات سریع حریف از جناح راست"
    facts["away"]["watchout"] = "ضربات کرنر کات‌دار میزبان"
    ctx = build_preview_context(_draft(), facts)
    assert ctx["has"]["watchout"] is False
    assert "watchout" not in [m["id"] for m in ctx["modules"]]
    assert "باید حواسشون بهش باشه" in ctx["caption_text"]
    assert "ضدحملات سریع حریف از جناح راست" in ctx["caption_text"]
    assert "ضربات کرنر کات‌دار میزبان" in ctx["caption_text"]
    assert ctx["caption_text"].endswith("#پیش_بازی")


def test_zero_orphan_half_width_modules():
    """هیچ ماژول نیم‌عرض یتیمی که نیم‌فضای خالی بسازد نباید تولید شود."""
    mods = select_studio_modules("preview", {"radar": True, "stats": True}, fmt="4:5", layout="v1")
    assert all(m["span"] == "full" for m in mods)


# ─── سازوکار پوشه studio_templates/ و خروجی HTML خودبسنده ───

def test_studio_template_folder_exists_and_renders_exact_design():
    assert (STUDIO_TEMPLATES_DIR / "pre_match.html").exists()
    html = render_preview_html(_draft(), _facts(), fmt="4:5")
    assert 'id="xgpedia-unified"' in html
    assert "data:font/woff2;base64," in html
    assert "width:1080px;height:1350px;" in html
    # لینک‌های خارجی CDN حذف شده‌اند تا رندر ۱۰۰٪ خودبسنده و بدون وابستگی شبکه باشد
    assert "cdn.tailwindcss.com" not in html
    assert "fonts.googleapis.com" not in html


def test_custom_studio_template_dir_drop_in(tmp_path: Path):
    """قرار دادن فایل pre_match.html در پوشهٔ دلخواه دقیقاً از روی همان فایل رندر می‌کند."""
    src = (STUDIO_TEMPLATES_DIR / "pre_match.html").read_text(encoding="utf-8")
    custom_marker = "<!-- CUSTOM_USER_STUDIO_TEMPLATE_V2 -->"
    (tmp_path / "pre_match.html").write_text(custom_marker + "\n" + src, encoding="utf-8")
    html = render_preview_html(_draft(), _facts(), template_dir=tmp_path)
    assert custom_marker in html


def test_formats_change_artboard_dimensions():
    for fmt, (w, h) in (("4:5", (1080, 1350)), ("9:16", (1080, 1920)), ("16:9", (1920, 1080))):
        html = render_preview_html(_draft(), _facts(), fmt=fmt)
        assert f"width:{w}px;height:{h}px;" in html


def test_identity_codes_match_glossary():
    glossary = json.load(open("config/glossary_fa.json", encoding="utf-8"))
    g_ids = {t["id"] for t in glossary["teams"]}
    i_codes = {t["code"] for t in load_team_identities()["teams"].values()}
    assert i_codes == g_ids


# ─── رندر واقعی Playwright (در صورت نصب) ───

def test_render_real_png(tmp_path):
    pytest.importorskip("playwright", reason="playwright not installed")
    from src.xgpedia.render.cards import render_preview_card

    html_path, img_path, cap_path = render_preview_card(
        _draft(), _facts(), out_dir=tmp_path, post_id=1, version=1, platform="telegram"
    )
    assert img_path.exists() and img_path.stat().st_size > 50_000
    assert cap_path.read_text(encoding="utf-8").endswith("#پیش_بازی")
    assert html_path.name == "post_1_v1_preview_1080x1350.html"
