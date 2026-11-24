"""آزمون‌های نسخهٔ 0.27.4 — حذف تکرار تیتر خبر، منبع هایپرلینک، فیلتر تصویر شفاف (پیش‌فرض)، متن مفصل غیرتکراری و هشتگ دائمی زیر همهٔ کارت‌ها."""
from __future__ import annotations

import json
from types import SimpleNamespace

from src.xgpedia.providers.breaking_news_free import (
    _dedupe_bullets_against_text,
    _short_card_lead,
    translate_news_item_to_persian,
)
from src.xgpedia.publishers import telegram_publish as tp
from src.xgpedia.render.card_kit.news_card import (
    NEWS_DEFAULT_TINT,
    build_news_caption,
    render_news_html,
)


def test_breaking_news_no_duplicate_title_hyperlink_source_and_hashtags():
    item = {
        "id": "espn_1",
        "mode": "breaking",
        "comp": "لیگ برتر انگلیس",
        "source": "ESPN Soccer",
        "source_url": "https://www.espn.com/soccer/story/_/id/12345/man-utd-anfield",
        "headline": "برلی رویه *منچستر یونایتد* را پس از فروپاشی در آنفیلد زیر سؤال برد",
        "body_fa": (
            "کریگ برلی تحلیل‌گر باسابقهٔ ESPN در واکنش به شکست سنگین منچستریونایتد در آنفیلد، "
            "ضعف ذهنی و از هم پاشیدگی ساختار دفاعی این تیم را نگران‌کننده‌ترین نشانهٔ فصل جدید دانست.\n\n"
            "به گفتهٔ او، شیاطین سرخ پس از دریافت گل اول کنترل میانهٔ میدان را کاملاً از دست دادند و نتوانستند واکنش تاکتیکی نشان دهند."
        ),
        "bullets": ["آمار پایین نبردهای میانهٔ میدان در نیمهٔ دوم"],
    }
    cap_body = build_news_caption(item, mode="breaking")
    post = {
        "post_id": 61,
        "post_type": "breaking_news",
        "content_version": 1,
        "title": "خبر فوری | برلی رویه منچستر یونایتد را پس از فروپاشی در آنفیلد زیر سؤال برد",
        "caption": cap_body,
        "draft_json": json.dumps({"title": "برلی رویه منچستر یونایتد", "mode": "breaking"}, ensure_ascii=False),
        "fact_json": json.dumps(item, ensure_ascii=False),
    }
    full = tp.build_caption(post)
    # تیتر دقیقاً یک‌بار و با 📰
    assert full.startswith("<b>📰 خبر فوری |")
    assert full.count("برلی رویه منچستر یونایتد") == 1
    # منبع به صورت هایپرلینک دقیق خبر
    assert '<a href="https://www.espn.com/soccer/story/_/id/12345/man-utd-anfield">ESPN Soccer</a>' in full
    # هشتگ‌های متناسب در انتهای کپشن
    assert "#XGPedia" in full
    assert "#خبر_فوری" in full
    assert "#منچستریونایتد" in full
    assert "#لیگ_برتر_انگلیس" in full


def test_hashtags_present_on_all_card_types():
    for ptype, expected_tag in (
        ("preview", "#پیش_بازی"),
        ("post_match", "#پس_از_بازی"),
        ("on_this_day", "#در_چنین_روزی"),
        ("breaking_news", "#خبر_فوری"),
    ):
        post = {
            "post_id": 70,
            "post_type": ptype,
            "content_version": 1,
            "title": "آرسنال برابر لیورپول در لیگ برتر",
            "caption": "گزارش تحلیلی مسابقه.",
            "draft_json": json.dumps({"title": "آرسنال برابر لیورپول", "source_note": "ESPN"}, ensure_ascii=False),
            "fact_json": json.dumps({"source": "ESPN Soccer"}, ensure_ascii=False),
        }
        out = tp.build_caption(post)
        assert "#XGPedia" in out and "#فوتبال" in out and expected_tag in out
        assert "#آرسنال" in out and "#لیورپول" in out


def test_news_card_default_light_tint_vs_strong_tint():
    assert NEWS_DEFAULT_TINT == "light"
    item = {
        "id": "t1",
        "mode": "breaking",
        "headline": "تیتر *تست* خبر",
        "lead": "لید کوتاه خبر.",
        "source": "BBC Sport",
        "comp": "لیگ برتر",
    }
    html_light = render_news_html(item, layout="cinematic")
    html_strong = render_news_html(item, layout="cinematic", tint_mode="strong")
    assert "rgba(13,23,48,.03) 20%" in html_light
    assert "rgba(13,23,48,.82) 0%" in html_strong
    assert html_light != html_strong


def test_rich_persian_body_and_non_repetitive_bullets():
    long_body = (
        "کریگ برلی تحلیل‌گر ESPN هشدار داد که مهم‌ترین چالش منچستریونایتد در فصل جدید، شکنندگی ذهنی بازیکنان در بازی‌های بزرگ خارج از خانه است.\n\n"
        "در دیدار آنفیلد مقابل لیورپول، خط میانی یونایتد پس از دقیقه ۳۰ عملاً از جریان مسابقه خارج شد و فشار پرس حریف باعث خطاهای پیاپی در خروج از دفاع گردید."
    )

    class _RichLLM:
        def generate(self, sys_prompt, payload):
            return SimpleNamespace(
                title="انتقاد تند برلی از ذهنیت *منچستریونایتد*",
                caption=long_body,
                bullets=[
                    "کریگ برلی هشدار داد مهم‌ترین چالش منچستریونایتد شکنندگی ذهنی بازیکنان در بازی‌های بزرگ است",  # تکراری -> باید حذف شود
                    "کادر فنی برای بازی هفته آینده احتمالاً تغییراتی در زوج خط میانی اعمال می‌کند",  # مجزا -> باید حفظ شود
                ],
                source_note="تحلیل ESPN فوتبال",
            )

    res = translate_news_item_to_persian(
        {"id": "x1", "lang": "en", "headline": "Burley slams Man Utd", "lead": "Short lead.", "source": "ESPN Soccer"},
        llm_provider=_RichLLM(),
    )
    assert res["body_fa"] == long_body
    assert len(res["lead"]) <= 165
    assert len(res["bullets"]) == 1
    assert "زوج خط میانی" in res["bullets"][0]
    assert len(_short_card_lead(long_body, 165)) <= 165
    assert len(_dedupe_bullets_against_text(["نکته تکراری کامل", "زاویه تاکتیکی جدید در خط دفاعی"], "نکته تکراری کامل")) == 1
