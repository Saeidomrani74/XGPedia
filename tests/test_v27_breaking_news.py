"""تست‌های جامع نسخه v0.27.0 — کارت «خبر فوری و رسمی» (PRO WIRE v2 — حالت اسلایدی)."""
from __future__ import annotations

import json

from src.xgpedia.providers.breaking_news_free import (
    classify_news_mode,
    load_news_presets,
    parse_espn_news_payload,
    parse_rss_football_xml,
)
from src.xgpedia.publishers.telegram_publish import build_review_caption
from src.xgpedia.render.card_kit.news_card import (
    NEWS_DEFAULT_LAYOUT,
    NEWS_FORMATS,
    NEWS_LAYOUTS,
    NEWS_MODES,
    build_news_caption,
    get_news_layout_availability,
    get_news_slide_modules,
    render_news_html,
)


def test_news_presets_loaded_and_default_layout():
    assert NEWS_DEFAULT_LAYOUT == "cinematic"
    presets = load_news_presets()
    ids = {p["id"] for p in presets}
    assert {"breaking_saka", "official_arteta", "transfer_blockbuster", "wire_exclusive", "official_derby"}.issubset(ids)
    # پرونده انتقال فقط وقتی دیتای واقعی transfer موجود باشد فعال است
    saka = next(p for p in presets if p["id"] == "breaking_saka")
    arteta = next(p for p in presets if p["id"] == "official_arteta")
    assert get_news_layout_availability(saka)["dossier"] is True
    assert get_news_layout_availability(arteta)["dossier"] is False


def test_espn_and_rss_parsers_respect_null_ne_zero():
    espn_payload = {
        "articles": [
            {
                "headline": "Arsenal star ruled out with hamstring injury ahead of Liverpool clash",
                "description": "Scans confirm a two-week absence for the winger.",
                "published": "2026-11-23T10:15:00Z",
                "links": {"web": {"href": "https://www.espn.com/soccer/story/_/id/12345"}},
                "images": [{"url": "https://a.espncdn.com/photo/sample.jpg"}],
            }
        ]
    }
    parsed = parse_espn_news_payload(espn_payload, comp_fa="لیگ برتر انگلیس")
    assert len(parsed) == 1
    assert parsed[0]["mode"] == "alert"
    assert parsed[0]["stats"] == []
    assert parsed[0]["transfer"] is None
    assert parsed[0]["dock"] == "none"

    rss_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><title>BBC Sport Football</title>
      <item>
        <title>Real Madrid sign midfielder on five-year contract deal</title>
        <description>The club confirmed the transfer after medical tests.</description>
        <link>https://www.bbc.co.uk/sport/football/999</link>
        <pubDate>Mon, 23 Nov 2026 09:00:00 GMT</pubDate>
      </item>
    </channel></rss>"""
    rss_items = parse_rss_football_xml(rss_xml, source_name="BBC Sport")
    assert len(rss_items) == 1
    assert rss_items[0]["mode"] == "transfer"
    assert rss_items[0]["source"] == "BBC Sport"
    assert rss_items[0]["stats"] == []


def test_all_4_layouts_5_modes_4_formats_offline_and_postmatch_frame():
    presets = load_news_presets()
    musiala = next(p for p in presets if p["id"] == "transfer_blockbuster")

    for layout_id, _, _ in NEWS_LAYOUTS:
        for mode_id in NEWS_MODES:
            for fmt in NEWS_FORMATS:
                html_out = render_news_html(
                    musiala, layout=layout_id, mode=mode_id, fmt=fmt
                )
                # ۱۰۰٪ آفلاین (بدون CDN)
                assert "fonts.googleapis.com" not in html_out
                assert "cdn.tailwindcss.com" not in html_out
                assert "html2canvas" not in html_out
                # هم‌ترازی دقیق چهارگوشهٔ قرمز Post-Match + فاصلهٔ عمودی بالا (+4px)
                assert "M24 44V24H44" in html_out
                assert "padding:12px 36px 8px" in html_out
                assert "flex-wrap:nowrap" in html_out
                # عدم خرابی entity های فارسی
                assert "&#x۲" not in html_out and "&#x۳" not in html_out
                assert "@XGPedia" in html_out


def test_news_module_toggles_and_telegram_review_caption():
    presets = load_news_presets()
    saka = next(p for p in presets if p["id"] == "breaking_saka")
    mods, _ = get_news_slide_modules(saka, "cinematic")
    assert any(m["id"] == "seal" for m in mods)

    html_no_ticker = render_news_html(
        saka, layout="cinematic", enabled_modules=["dock_stats", "pitch"]
    )
    assert '<div class="nw-ticker">' not in html_no_ticker
    assert "sealPath" not in html_no_ticker

    cap = build_news_caption(saka)
    assert "بوکایو ساکا" in cap and "<b>" not in cap
    fake_post = {
        "post_id": 99,
        "post_type": "breaking_news",
        "content_version": 1,
        "title": "خبر فوری | مصدومیت ساکا",
        "caption": cap,
        "draft_json": json.dumps({"title": "مصدومیت ساکا"}),
        "fact_json": json.dumps(saka, ensure_ascii=False),
    }
    rev = build_review_caption(fake_post)
    assert "بوکایو ساکا" in rev and "The Athletic" in rev


def test_news_persian_translation_and_real_photo_data_uri():
    from types import SimpleNamespace
    from src.xgpedia.providers.breaking_news_free import translate_news_item_to_persian

    class _FakeLLM:
        def generate(self, system_prompt, user_payload):
            return SimpleNamespace(
                title="فوری؛ مصدومیت *بوکایو ساکا* پیش از بازی لیورپول",
                caption="بوکایو ساکا به‌دلیل کشیدگی همسترینگ دیدار حساس آرسنال مقابل لیورپول را از دست داد.",
                bullets=["غیبت قطعی در نبرد صدر جدول", "نگرانی کادر پزشکی آرسنال"],
                source_note="گزارش فوری از کمپ آرسنال",
            )

    en_item = {
        "id": "espn_test1",
        "lang": "en",
        "mode": "alert",
        "layout": "cinematic",
        "comp": "لیگ برتر انگلیس",
        "time": "زنده",
        "kicker": "گزارش زنده ESPN",
        "headline": "Arsenal star Bukayo Saka ruled out of Liverpool clash",
        "lead": "The winger suffered a hamstring issue.",
        "photoId": "tunnel",
        "photoDataUri": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
        "source": "ESPN Soccer",
        "tier": "TIER 1",
        "footerTag": "PREMIER LEAGUE | LIVE WIRE",
    }
    fa_item = translate_news_item_to_persian(en_item, llm_provider=_FakeLLM())
    assert fa_item["lang"] == "fa"
    assert "بوکایو ساکا" in fa_item["headline"]
    assert "همسترینگ" in fa_item["lead"]
    html_out = render_news_html(fa_item, layout="cinematic", fmt="4:5")
    assert "data:image/png;base64," in html_out
    assert "بوکایو ساکا" in html_out


def test_bbc_hd_upgrade_jalali_date_and_llm_dict_payload():
    from src.xgpedia.editorial.llm_provider import _build_messages
    from src.xgpedia.providers.breaking_news_free import _format_pub_jalali, upgrade_news_image_url

    # 1) _build_messages must accept plain dict (root cause of English news staying untranslated!)
    msgs = _build_messages("sys", {"headline": "Test news"})
    assert len(msgs) == 2 and "Test news" in msgs[1]["content"]

    # 2) BBC 240px thumbnail must upgrade to 1024px HD
    u = "https://ichef.bbci.co.uk/ace/standard/240/cpsprodpb/1234/live/abc.jpg"
    assert "/1024/" in (upgrade_news_image_url(u) or "")

    # 3) RSS English date converts cleanly to Persian Jalali
    j = _format_pub_jalali("Sun, 22 Nov 2026 19:00:00 GMT")
    assert "Sun" not in j and "Nov" not in j
