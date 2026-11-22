"""تست‌های جامع نسخه v0.21.0:
- استخراج سرمربی زنده از Infobox ویکی‌پدیا + ترجمهٔ فارسی همیشه فعال (دیکشنری + آوانویسی خودکار)
- پارس اخبار مهم ۷ روز اخیر از RSS و پذیرش اعداد موجود در تیتر اخبار در validator
- شروع زنجیرهٔ LLM از مدل دلخواه (LLM_START_INDEX / SQLite setting) + کول‌داون خودکار 429/503
- سیگنال‌های ارزش متنوع (فقط +EV برتر تا ۳ مورد، افکت طلایی برای >= 8%، برچسب «ارزش منفی» برای < 0)
- اصلاح برچسب هفته‌های روند xG با جهت‌دهی RTL صحیح
- چیدمان ۲-ردیفهٔ دکمه‌های ماژول‌ها (نام کامل تمام‌عرض + ردیف کنترل فشرده) و منوی تنظیم مدل LLM در تلگرام
"""
from __future__ import annotations

from pathlib import Path

from src.xgpedia import db as db_mod
from src.xgpedia.config import translate_coach_fa
from src.xgpedia.editorial.llm_provider import (
    LLMEndpoint,
    MultiProviderLLM,
    clear_llm_cooldowns,
    get_llm_start_index,
    set_llm_start_index,
)
from src.xgpedia.editorial.validate import _input_numbers
from src.xgpedia.normalization.models import MatchFacts, SourceInfo, TeamSide
from src.xgpedia.providers.live_intel_free import parse_coach_from_wikitext, parse_rss_items
from src.xgpedia.publishers import telegram_bot as tb
from src.xgpedia.render.card_kit.modules.signals import render_signals
from src.xgpedia.render.card_kit.modules.trend10 import render_trend10
from src.xgpedia.render.cards import _build_real_signals


def test_parse_coach_from_wikitext_and_always_persian():
    wiki = """
{{Infobox football club
| clubname = Manchester United
| ground   = [[Old Trafford]]
| manager  = [[Mauricio Pochettino]]<ref name="bbc">BBC Sport</ref>
}}
"""
    coach = parse_coach_from_wikitext(wiki)
    assert coach == "Mauricio Pochettino"
    assert translate_coach_fa(coach) == "مائوریسیو پوچتینو"
    assert translate_coach_fa("Michael Carrick") == "مایکل کریک"
    # حتی یک نام کاملاً جدید خارج از دیکشنری هم نباید انگلیسی باقی بماند
    unknown_fa = translate_coach_fa("Marco Rossi")
    assert unknown_fa is not None
    assert any("\u0600" <= ch <= "\u06FF" for ch in unknown_fa)


def test_parse_rss_items_and_recent_news_validator_numbers():
    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>New manager takes charge for first match after 2-year break - BBC Sport</title>
    <link>https://www.bbc.com/sport/football/123</link>
    <pubDate>Sat, 21 Nov 2026 10:00:00 GMT</pubDate>
    <source>BBC Sport</source>
  </item>
</channel></rss>"""
    items = parse_rss_items(rss, "Manchester United", default_source="Google News")
    assert len(items) == 1
    assert items[0]["source"] == "BBC Sport"
    assert not items[0]["title"].endswith("- BBC Sport")

    mf = MatchFacts(
        fixture_id="fdo:1",
        competition={"name": "Premier League", "season": "2026-27"},
        kickoff_utc="2026-11-22T15:00:00Z",
        source=SourceInfo(provider="football-data-org", collected_at="2026-11-22T10:00:00Z"),
        home=TeamSide(name_fa="منچستر یونایتد", name_en="Manchester United"),
        away=TeamSide(name_fa="چلسی", name_en="Chelsea"),
        recent_news=items,
    )
    nums = _input_numbers(mf)
    assert 2.0 in nums


def test_llm_start_index_persistence_and_ordering(tmp_path, monkeypatch):
    db_path = tmp_path / "llm_start.db"
    monkeypatch.setattr(db_mod, "DATABASE_PATH", db_path)
    db_mod.init_db()
    clear_llm_cooldowns()

    assert get_llm_start_index() == 1
    set_llm_start_index(4)
    assert get_llm_start_index() == 4

    eps = [
        LLMEndpoint(label=f"M{i}", base_url="https://example.com/v1", model=f"m{i}", api_key="k")
        for i in range(1, 6)
    ]
    router = MultiProviderLLM(eps)
    ordered_indices = [idx for idx, _ in router._ordered_endpoints()]
    # شروع مستقیم از #4 -> #5 و سپس مدل‌های قبلی فقط در انتها به‌عنوان پشتیبان اضطراری
    assert ordered_indices == [4, 5, 1, 2, 3]


def test_signals_variety_positive_only_golden_and_negative_label():
    facts = {
        "market_odds": {
            "home": 2.40,
            "draw": 3.50,
            "away": 3.20,
            "over25": 2.10,
            "under25": 1.80,
            "btts": 1.95,
        }
    }
    probs = {"home": 50, "draw": 25, "away": 25}
    dc = {"pH": 0.50, "pD": 0.25, "pA": 0.25, "pO25": 0.58, "pBTTS": 0.56}
    sigs = _build_real_signals(facts, probs, dc, "آرسنال", "چلسی")
    assert 1 <= len(sigs) <= 3
    # همهٔ سیگنال‌های انتخابی باید مثبت باشند و نزولی مرتب شده باشند
    assert all(s["ev_pct"] > 0 for s in sigs)
    assert sigs == sorted(sigs, key=lambda x: -x["ev_pct"])
    # بیشترین سیگنال (برد آرسنال: 0.50 * 2.40 - 1 = +20%) باید کلاس طلایی egold بگیرد
    assert sigs[0]["tier_class"] == "egold"
    assert "بسیار ارزشمند" in sigs[0]["tier_label"]

    html_gold = render_signals({"signalsItems": sigs})
    assert "er-gold" in html_gold
    assert "gold-star" in html_gold

    # تست صریح برچسب «ارزش منفی» برای مقدار منفی (هرگز «ارزش جزئی» نشود)
    html_neg = render_signals({
        "signalsItems": [{
            "title": "تساوی",
            "odds": 3.2,
            "model_pct": 25.0,
            "market_pct": 31.2,
            "ev_pct": -12.0,
            "tier_class": "en",
            "tier_label": "ارزش جزئی",
        }]
    })
    assert "ارزش منفی" in html_neg
    assert "ارزش جزئی" not in html_neg


def test_trend10_week_labels_and_rtl_direction():
    payload = {
        "match": {
            "weekCode": "W12",
            "round": "هفته ۱۲ • پیش‌بازی آماری",
            "home": {"name": "آرسنال", "color": "#EF4444", "last10": [1.2, 1.5, 1.8, 2.0, 1.4, 1.6, 2.1, 1.9, 1.7, 2.3]},
            "away": {"name": "چلسی", "color": "#38BDF8", "last10": [1.0, 1.1, 1.3, 1.5, 1.2, 1.4, 1.6, 1.3, 1.5, 1.8]},
        }
    }
    html = render_trend10(payload, span="full")
    # ۱۰ بازی قبل از هفته ۱۲ = هفته ۲ تا هفته ۱۱
    assert ">۲<" in html
    assert ">۱۱<" in html
    assert "هـ۲" not in html
    assert "قدیمی‌تر" not in html


def test_customizer_wide_name_row_and_llm_menu():
    st = {
        "fixture_id": "fdo:99",
        "home_fa": "آرسنال",
        "away_fa": "چلسی",
        "round": "هفته ۱۲",
        "stadium": "امارات",
        "fmt": "4:5",
        "header_mode": "full",
        "broadcast_idx": 0,
        "modules": [
            {"id": "radar", "title_fa": "رادار ۶ محوره تاکتیکی", "span": "full", "can_half": True, "enabled": True},
            {"id": "trend10", "title_fa": "روند xG در ۱۰ بازی اخیر", "span": "full", "can_half": True, "enabled": True},
        ],
        "missing_modules": [],
    }
    _, markup = tb._render_customizer_view(st)
    # ردیف نام ماژول باید تک‌دکمه‌ای (تمام‌عرض) باشد و ردیف کنترل زیر آن ۳ دکمه‌ای باشد
    name_rows = [row for row in markup.inline_keyboard if len(row) == 1 and row[0].callback_data.startswith("cz:tog:")]
    assert len(name_rows) == 2
    assert "رادار ۶ محوره تاکتیکی" in name_rows[0][0].text

    panel = tb._main_panel_markup()
    cbs = [b.callback_data for r in panel.inline_keyboard for b in r]
    assert "llm:menu" in cbs
