"""تست‌های جامع نسخه v0.26.0 — کارت «در چنین روزی» (On This Day Showreel V2)."""
from __future__ import annotations

import re

from src.xgpedia.providers.on_this_day_free import (
    load_archive_presets,
    parse_wikipedia_on_this_day_payload,
)
from src.xgpedia.render.card_kit.on_this_day_card import (
    OTD_SLIDES,
    OTD_THEMES,
    build_on_this_day_caption,
    get_otd_slide_availability,
    get_otd_slide_modules,
    render_on_this_day_html,
)


def test_archive_presets_loaded_and_verified():
    presets = load_archive_presets()
    ids = {p["id"] for p in presets}
    assert {"melbourne97", "istanbul05", "azteca86", "remontada17"}.issubset(ids)
    for p in presets:
        assert p["verified"] is True
        assert p["home"]["name"] and p["away"]["name"]
        assert p["replay"]["title"]
        avail = get_otd_slide_availability(p)
        assert all(avail.values()), f"Archive preset {p['id']} must support all 4 slides"


def test_wikipedia_on_this_day_parser_filters_football_and_respects_null_ne_zero():
    sample_payload = {
        "events": [
            {
                "year": 1998,
                "text": "تیم ملی فوتبال فرانسه با پیروزی در فینال جام جهانی فوتبال ۱۹۹۸ قهرمان جهان شد.",
                "pages": [
                    {
                        "titles": {"normalized": "جام جهانی فوتبال ۱۹۹۸"},
                        "extract": "جام جهانی فوتبال ۱۹۹۸ شانزدهمین دوره رقابت‌های جام جهانی فیفا به میزبانی فرانسه بود.",
                        "content_urls": {"desktop": {"page": "https://fa.wikipedia.org/wiki/1998_FIFA_World_Cup"}},
                    }
                ],
            },
            {
                "year": 2002,
                "text": "The New England Patriots won Super Bowl XXXVI in American football NFL.",
                "pages": [{"titles": {"normalized": "Super Bowl XXXVI"}, "description": "NFL championship"}],
            },
            {
                "year": 1969,
                "text": "آپولو ۱۱ روی ماه فرود آمد.",
                "pages": [{"titles": {"normalized": "آپولو ۱۱"}, "description": "ماموریت فضایی"}],
            },
        ],
        "births": [
            {
                "year": 1987,
                "text": "لیونل مسی، فوتبالیست آرژانتینی و برنده توپ طلا",
                "pages": [{"titles": {"normalized": "لیونل مسی"}, "description": "فوتبالیست آرژانتینی"}],
            }
        ],
    }
    parsed = parse_wikipedia_on_this_day_payload(sample_payload, month=7, day=12, lang="fa")
    # فقط وقایع تاریخی پذیرفته می‌شوند و تولدها (births) حذف می‌گردند
    assert len(parsed) == 1
    titles = [e["title"] for e in parsed]
    assert any("جام جهانی" in t for t in titles)
    assert not any("لیونل مسی" in t for t in titles)
    # اصل null ≠ 0: رویدادهای زنده بدون اسکوربرد/مختصات تاکتیکی جعلی
    for ev in parsed:
        assert ev["home"] is None
        assert ev["away"] is None
        assert ev["replay"] is None
        avail = get_otd_slide_availability(ev)
        assert avail["cover"] is True
        assert avail["tactical"] is False


def test_all_4_slides_3_themes_3_formats_render_offline_and_clean():
    presets = load_archive_presets()
    mel = next(p for p in presets if p["id"] == "melbourne97")

    for slide_id, _, _ in OTD_SLIDES:
        for theme_id in OTD_THEMES:
            for fmt in ("4:5", "9:16", "16:9"):
                html_out = render_on_this_day_html(
                    mel, slide=slide_id, theme=theme_id, fmt=fmt
                )
                # ۱۰۰٪ آفلاین (بدون CDN)
                assert "fonts.googleapis.com" not in html_out
                assert "cdn.tailwindcss.com" not in html_out
                # هدر قفل‌شده در ۲ خط
                assert "flex-wrap:nowrap" in html_out
                # عدم خرابی entity های فارسی (esc(fa(...)))
                assert "&#x۲" not in html_out and "&#x۳" not in html_out
                # برند XGPedia و تراز چهارگوشه هم‌تراز با Post-Match (M24 44V24H44)
                assert "@XGPedia" in html_out
                assert "M24 44V24H44" in html_out
                assert '<span class="otd-diamond"></span>' not in html_out
                if slide_id == "cover":
                    assert "otd-h1-art" in html_out
                    assert "otd-title-motif" in html_out
                if slide_id == "tactical":
                    assert 'viewBox="0 0 900 588"' in html_out
                    assert 'width="840" height="544"' in html_out


def test_per_slide_module_toggle_and_live_event_render():
    presets = load_archive_presets()
    mel = next(p for p in presets if p["id"] == "melbourne97")
    mods, missing = get_otd_slide_modules(mel, "cover")
    assert len(mods) == 5
    assert missing == []

    # خاموش کردن ماژول pulse و goals
    html_no_pulse = render_on_this_day_html(
        mel, slide="cover", enabled_modules=["scoreboard", "story", "numbers"]
    )
    assert "DRAMA PULSE" not in html_no_pulse
    assert "حماسه ملبورن" in html_no_pulse

    # رندر رویداد زندهٔ ویکی‌پدیا (بدون اسکوربرد) بدون هیچ خطا یا 0-0 جعلی
    wiki_ev = {
        "id": "wiki_fa_test",
        "year": 1998,
        "dateFa": "۲۱ تیر ۱۳۷۷",
        "dateEn": "12 JUL 1998",
        "competition": "رویداد تاریخی فوتبال",
        "leagueEn": "FOOTBALL HISTORY",
        "kicker": "رویداد تاریخی فوتبال | ویکی‌پدیا (فارسی)",
        "stadium": "",
        "source": "Wikipedia (FA) / XGPedia",
        "title": "جام جهانی فوتبال ۱۹۹۸",
        "subtitle": "تیم ملی فوتبال فرانسه قهرمان جام جهانی شد.",
        "home": None,
        "away": None,
        "pulse": None,
        "goals": [],
        "replay": None,
        "numbers": [{"val": "1998", "unit": "سال وقوع", "sub": "ثبت‌شده در تاریخ"}],
        "story": {"headline": "روایت ۲۱ تیر ۱۳۷۷", "body": "قهرمانی تاریخی فرانسه در استاده دو فرانس.", "tag": "منبع مستند: ویکی‌پدیا"},
        "quote": None,
        "legacy": None,
    }
    for sl in ("cover", "collector", "editorial"):
        h = render_on_this_day_html(wiki_ev, slide=sl, fmt="4:5")
        assert "جام جهانی فوتبال" in h
        assert '<div class="score-prism otd-score-box">' not in h

    cap = build_on_this_day_caption(mel, slide="cover")
    assert "استرالیا" in cap and "<b>" not in cap

    # تست رگرسیون خطای post #48 در telegram_publish (facts["source"] به‌صورت str)
    import json
    from src.xgpedia.publishers.telegram_publish import build_review_caption
    fake_post = {
        "post_id": 48,
        "post_type": "on_this_day",
        "content_version": 1,
        "title": "در چنین روزی | حماسه ملبورن (1997)",
        "caption": cap,
        "draft_json": json.dumps({"title": "حماسه ملبورن"}),
        "fact_json": json.dumps(mel, ensure_ascii=False),
    }
    rev = build_review_caption(fake_post)
    assert "حماسه ملبورن" in rev and "FIFA Archive" in rev
