"""تست‌های جامع رفع ایرادات ۵ کارت (نسخه v0.36.1):
  1. عدد روز: فارسی‌سازی کامل، حذف عبارات کلیشه‌ای و حذف KPIهای عدد شاخص/وضعیت داده/منبع
  2. مناظره روز: لوگوی واقعی برای تیم‌ها (نه عکس اشتباه)، حذف SIDE/جبهه و حذف شاخص داغی بحث/واکنش هواداران
  3. نقل‌قول روز: ترجمه و هدر فارسی (اصلاح مسیر llm_provider) + لوگوی واقعی باشگاه‌های انگلیس
  4. نتایج روز: لوگوی واقعی باشگاه‌های انگلیس + دریافت و نمایش xG واقعی تیم‌ها و زهر گلزنی
  5. گلزنان: دریافت و نمایش آمار واقعی پنالتی‌ها + افزایش سایز و خوانایی فونت‌ها
"""
from __future__ import annotations

from pathlib import Path


def test_v361_pl_badges_offline_crests_and_tla_lookup() -> None:
    from src.xgpedia.providers.pl_badges_free import get_pl_badge_data_uri, lookup_pl_club

    for tla in ("ARS", "MCI", "MUN", "LIV", "CHE", "TOT", "AVL", "BHA", "NEW", "NFO"):
        hit = lookup_pl_club(tla)
        assert hit is not None and hit[1] == tla, f"Failed TLA lookup for {tla}"
        uri = get_pl_badge_data_uri(tla, tla_hint=tla, fetch_network=False)
        assert uri and uri.startswith("data:image/"), f"Expected real offline crest for {tla}"


def test_v361_number_of_day_persian_and_clean_labels() -> None:
    from src.xgpedia.providers.number_of_day_free import (
        extract_news_number_candidate,
        hydrate_number_of_day_item,
    )
    from src.xgpedia.render.card_kit.number_of_day_card import render_number_of_day_html

    cand = extract_news_number_candidate(
        title="Arsenal extend unbeaten streak to 15 matches in Premier League",
        description="A remarkable run of 15 games without defeat for Arsenal.",
        source_name="BBC Sport",
    )
    assert cand is not None
    assert cand["unit"] != "آمار برگزیده روز فوتبال"
    assert cand["pinText"] == ""
    assert cand["kpis"] == []

    hyd = hydrate_number_of_day_item(cand)
    html = render_number_of_day_html(hyd, slide="slide1", fmt="4:5")
    for banned in (
        "آمار برگزیده روز فوتبال",
        "عدد داغ در رسانه‌های معتبر اروپا",
        "عدد داغ در رسانه های معتبر اروپا",
        "عدد شاخص",
        "وضعیت داده",
        "HERO METRIC",
        "NUMBER OF THE DAY",
        "ISSUE #",
    ):
        assert banned not in html, f"Banned text found in number_of_day card: {banned}"
    # تیتر و متن نهایی نباید انگلیسی خام باقی بماند
    assert "Arsenal extend unbeaten streak" not in html


def test_v361_debate_team_logos_and_removed_labels() -> None:
    from src.xgpedia.providers.debate_free import extract_news_debate_candidate, hydrate_debate_item
    from src.xgpedia.render.card_kit.debate_card import render_debate_html

    clash = extract_news_debate_candidate(
        title="Arsenal vs Liverpool: Who is better equipped for the Premier League title race?",
        description="Comparing Arsenal and Liverpool ahead of the big clash.",
        source_name="BBC Sport",
        image_url="https://ichef.bbci.co.uk/news/1024/cpsprodpb/wrong_team_photo.jpg",
    )
    assert clash is not None
    # برای تیم‌ها نباید عکس خبری اشتباه ست شود
    assert clash["sideA"]["img"] is None and clash["sideA"]["entityType"] == "team"
    assert clash["sideB"]["img"] is None and clash["sideB"]["entityType"] == "team"
    assert clash["sideA"]["statLabel"] == "" and clash["sideB"]["statLabel"] == ""

    hyd = hydrate_debate_item(clash)
    html = render_debate_html(hyd, slide="slide1", fmt="4:5")
    for banned in ("SIDE 01", "SIDE 02", "جبهه اول", "جبهه دوم", "شاخص داغی بحث", "شاخص واکنش هواداران", "بحث داغ روز"):
        assert banned not in html, f"Banned label found in debate card: {banned}"
    # لوگوی واقعی باشگاه‌های انگلیس باید رندر شده باشد
    assert "data:image/" in html

    # بررسی اصلاح مسیر llm_provider
    df_src = Path("src/xgpedia/providers/debate_free.py").read_text(encoding="utf-8")
    assert "src.xgpedia.llm.client" not in df_src
    assert "src.xgpedia.editorial.llm_provider" in df_src


def test_v361_quote_persian_headers_and_real_pl_logos() -> None:
    from src.xgpedia.providers.quote_free import extract_quote_candidate, hydrate_quote_item
    from src.xgpedia.render.card_kit.quote_card import render_quote_html

    cand = extract_quote_candidate(
        title='Mikel Arteta: "We showed real mentality and belief to control the title race"',
        description="Arsenal boss Mikel Arteta spoke after the Premier League win.",
        source_name="BBC Sport",
        pub_date="Tue, 24 Nov 2026 14:00:00 GMT",
    )
    assert cand is not None
    hyd = hydrate_quote_item(cand)
    html = render_quote_html(hyd, slide="slide1", fmt="4:5")
    for eng_hdr in ("EDITORIAL SPOTLIGHT", "QUOTE // 01", "EDITORIAL COVER", "TACTICAL VOICE", "XGPEDIA DATA"):
        assert eng_hdr not in html
    assert "Mikel Arteta:" not in html
    assert "data:image/" in html  # لوگوی واقعی آرسنال

    qf_src = Path("src/xgpedia/providers/quote_free.py").read_text(encoding="utf-8")
    assert "src.xgpedia.llm.client" not in qf_src
    assert "src.xgpedia.editorial.llm_provider" in qf_src


def test_v361_matchday_results_real_logos_and_xg_enrichment() -> None:
    from src.xgpedia.providers.matchday_results_free import (
        _pack_matchday_card,
        enrich_matches_with_real_xg,
    )
    from src.xgpedia.render.card_kit.matchday_results_card import render_matchday_results_html

    matches = [
        {
            "event_id": "m1",
            "league_slug": "eng.1",
            "league": "لیگ برتر انگلیس",
            "home": {"name": "آرسنال", "name_en": "Arsenal", "code": "ARS", "color": "#EF0107", "secondary": "#FFFFFF", "score": 2, "xg": None, "scorers": "ساکا 22'"},
            "away": {"name": "لیورپول", "name_en": "Liverpool", "code": "LIV", "color": "#C8102E", "secondary": "#FFFFFF", "score": 1, "xg": None, "scorers": "صلاح 64'"},
            "status": "FT",
            "ht": "1-0",
            "tag": "لیگ برتر انگلیس",
        }
    ]
    fake_understat = {
        "EPL": [
            {
                "isResult": True,
                "h": {"title": "Arsenal"},
                "a": {"title": "Liverpool"},
                "goals": {"h": "2", "a": "1"},
                "xG": {"h": "2.15", "a": "1.10"},
            }
        ]
    }
    enrich_matches_with_real_xg(matches, understat_cache=fake_understat)
    assert matches[0]["home"]["xg"] == 2.15
    assert matches[0]["away"]["xg"] == 1.10

    card = _pack_matchday_card("test_xg", "لیگ برتر انگلیس", "PREMIER LEAGUE", "نتایج", matches)
    html = render_matchday_results_html(card, slide="slide1", fmt="4:5")
    assert "data:image/" in html  # لوگوی واقعی آرسنال و لیورپول
    assert "۲.۱۵" in html and "۱.۱۰" in html
    assert "EFF" in html and "— xG" not in html  # زهر گلزنی روز با xG واقعی محاسبه شده


def test_v361_top_scorers_penalties_wired_and_readable_fonts() -> None:
    from src.xgpedia.providers.top_scorers_free import parse_fpl_top_scorers
    from src.xgpedia.render.card_kit.top_scorers_card import render_top_scorers_html

    tsf_src = Path("src/xgpedia/providers/top_scorers_free.py").read_text(encoding="utf-8")
    assert "_fetch_epl_penalties_and_shots_map(bootstrap)" in tsf_src
    assert "understat_map=pen_map" in tsf_src
    assert "import requests" not in tsf_src and "from requests" not in tsf_src

    mock_boot = {
        "events": [{"id": 12, "is_current": True}],
        "teams": [
            {"id": 1, "code": 43, "name": "Man City", "short_name": "MCI"},
            {"id": 2, "code": 14, "name": "Liverpool", "short_name": "LIV"},
        ],
        "elements": [
            {"id": 10, "code": 223094, "team": 1, "element_type": 4, "first_name": "Erling", "second_name": "Haaland", "web_name": "Haaland", "goals_scored": 14, "assists": 2, "expected_goals": "11.5", "threat": "620", "creativity": "110", "influence": "510", "bps": 390, "minutes": 990},
            {"id": 20, "code": 118748, "team": 2, "element_type": 3, "first_name": "Mohamed", "second_name": "Salah", "web_name": "Salah", "goals_scored": 11, "assists": 7, "expected_goals": "9.1", "threat": "540", "creativity": "430", "influence": "480", "bps": 350, "minutes": 980},
        ],
    }
    pen_map = {
        "erling haaland": {"goals": 14, "pen": 3, "shots": 48},
        "mohamed salah": {"goals": 11, "pen": 4, "shots": 39},
    }
    parsed = parse_fpl_top_scorers(mock_boot, top_n=8, understat_map=pen_map)
    assert parsed is not None
    assert parsed["players"][0]["pen"] == 3
    assert parsed["players"][1]["pen"] == 4

    html = render_top_scorers_html(parsed, slide="slide1", fmt="4:5")
    assert "پنالتی" in html
    assert "۴ پنالتی" in html  # نمایش مستقیم پنالتی در ردیف جدول
    assert "font-size:26px" in html  # فونت درشت و خوانا برای نام بازیکنان
    assert "font-size:33px" in html  # فونت درشت و خوانا برای عدد گل
