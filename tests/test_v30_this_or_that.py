"""آزمون‌های نسخهٔ 0.30.0 — استودیو اسلایدی «این یا اون؟» (D49): ۴ سبک × ۳ فرمت + پیشنهادهای جدالی + تولید با AI + هشتگ دائمی."""
from __future__ import annotations

import json
from types import SimpleNamespace

from src.xgpedia.providers.this_or_that_free import (
    generate_ai_debate_proposal,
    list_this_or_that_suggestions,
    load_this_or_that_presets,
)
from src.xgpedia.publishers import telegram_publish as tp
from src.xgpedia.render.card_kit.this_or_that_card import (
    TOT_DEFAULT_LAYOUT,
    TOT_FORMATS,
    TOT_LAYOUTS,
    build_this_or_that_caption,
    render_this_or_that_html,
)


def test_tot_presets_and_all_4_layouts_3_formats_render_offline():
    assert TOT_DEFAULT_LAYOUT == "diagonal"
    presets = load_this_or_that_presets()
    assert len(presets) >= 10
    saka_yamal = presets[0]
    for ly, _, _ in TOT_LAYOUTS:
        for fmt, (w, h) in TOT_FORMATS.items():
            html_out = render_this_or_that_html(saka_yamal, layout=ly, fmt=fmt)
            assert "cdn.tailwindcss.com" not in html_out
            assert "fonts.googleapis.com" not in html_out
            assert f"width:{w}px;height:{h}px" in html_out
            assert f"M24 44V24H44M{w - 24} 44V24H{w - 44}" in html_out
            assert "@XGPedia" in html_out


def test_tot_suggestions_and_ai_debate_generator_with_telegram_hashtags():
    sugs = list_this_or_that_suggestions(include_live_matches=False)
    assert len(sugs) >= 10

    class _FakeLLM:
        def generate(self, sys_p, payload):
            return SimpleNamespace(
                title="برای فینال آسیا کدام دروازه‌بان را انتخاب می‌کنی؟",
                caption="بیرانوند (A) یا عابدزاده (B)؟ انتخابت رو کامنت کن!",
                bullets=[
                    "A: علیرضا بیرانوند | مهار پنالتی و پرتاب دست | AB1 | مهار پنالتی، پرتاب بلند، تجربه جام جهانی",
                    "B: احمدرضا عابدزاده | عقاب آسیا و کاریزما | AA1 | واکنش انفجاری، رهبری، تاریخ‌ساز",
                    "STATS: واکنش روی خط:92:96 | مهار پنالتی:97:93 | کاریزما و رهبری:91:99",
                ],
                source_note="دوئل دروازه‌بان‌های ایران",
            )

    ai_item = generate_ai_debate_proposal(llm_provider=_FakeLLM())
    assert ai_item["a"]["name"] == "علیرضا بیرانوند"
    assert ai_item["b"]["name"] == "احمدرضا عابدزاده"
    assert len(ai_item["stats"]) == 3

    cap = build_this_or_that_caption(ai_item)
    post = {
        "post_id": 95,
        "post_type": "this_or_that",
        "content_version": 1,
        "title": "این یا اون؟ | علیرضا بیرانوند × احمدرضا عابدزاده",
        "caption": cap,
        "draft_json": json.dumps({"title": "این یا اون؟ | علیرضا بیرانوند × احمدرضا عابدزاده"}, ensure_ascii=False),
        "fact_json": json.dumps(ai_item, ensure_ascii=False),
    }
    full = tp.build_caption(post)
    assert full.startswith("<b>⚔️ این یا اون؟")
    assert "#XGPedia" in full and "#فوتبال" in full and "#این_یا_اون" in full and "#نظرسنجی_فوتبال" in full
    assert tp._utf16_len(tp.build_review_caption(post)) <= tp.CAPTION_LIMIT
