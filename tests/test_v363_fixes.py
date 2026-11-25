"""تست‌های واحد هات‌فیکس v0.36.3:
  1. افزودن `fetch_fpl_bootstrap` و `fetch_fpl_fixtures` به `fpl_free.py` (رفع خطای عدد روز/مناظره/نقل‌قول)
  2. افزودن `generate_text` به `llm_provider.py` (فعال‌سازی ترجمه واقعی فارسی در تمام کارت‌ها)
  3. ارتقای کیفیت عکس Sky Sports (`365dm.com`) و نسبت تصویر ثابت `16:10` / `4:3` در کارت نقل‌قول روز
  4. دریافت xG از ESPN/Understat + نمایش تعداد گل‌ها در «نبض دقایق گل» و خوانایی فونت‌های تابلوی نتایج
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def test_v363_fpl_free_exports_and_llm_generate_text() -> None:
    from src.xgpedia.editorial import llm_provider
    from src.xgpedia.providers import fpl_free

    assert callable(getattr(fpl_free, "fetch_fpl_bootstrap", None))
    assert callable(getattr(fpl_free, "fetch_fpl_fixtures", None))
    assert callable(getattr(llm_provider, "generate_text", None))


def test_v363_number_of_day_rich_fpl_and_no_clipped_archive() -> None:
    from src.xgpedia.providers.number_of_day_free import build_fpl_live_numbers
    from src.xgpedia.render.card_kit.number_of_day_card import render_number_of_day_html

    mock_boot = {
        "events": [{"id": 12, "is_current": True}],
        "teams": [
            {"id": 1, "code": 3, "name": "Arsenal", "short_name": "ARS"},
            {"id": 2, "code": 14, "name": "Liverpool", "short_name": "LIV"},
            {"id": 3, "code": 43, "name": "Man City", "short_name": "MCI"},
        ],
        "elements": [
            {"id": 10, "code": 223094, "team": 3, "first_name": "Erling", "second_name": "Haaland", "web_name": "Haaland", "goals_scored": 13, "assists": 2, "expected_goals": "9.4", "expected_assists": "1.2", "creativity": "120", "minutes": 990},
            {"id": 20, "code": 118748, "team": 2, "first_name": "Mohamed", "second_name": "Salah", "web_name": "Salah", "goals_scored": 9, "assists": 8, "expected_goals": "7.5", "expected_assists": "5.2", "creativity": "430", "minutes": 980},
        ],
    }
    items = build_fpl_live_numbers(boot=mock_boot, fixtures=[])
    assert any("live_nod_ga_" in x["id"] for x in items)
    html = render_number_of_day_html(items[0], slide="slide1", fmt="4:5")
    assert "آرشیو XGPedia" not in html


def test_v363_quote_hd_sky_sports_and_fixed_aspect_ratio() -> None:
    from src.xgpedia.providers.breaking_news_free import upgrade_news_image_url
    from src.xgpedia.providers.quote_free import load_quote_presets
    from src.xgpedia.render.card_kit.quote_card import render_quote_html

    sky_up = upgrade_news_image_url("https://e0.365dm.com/26/11/384x216/skysports-haaland_12345.jpg")
    assert sky_up and "/1600x900/" in sky_up

    preset = dict(load_quote_presets()[0])
    preset["photoSrc"] = "data:image/png;base64,iVBORw0KGgo="
    preset["photoSrc2"] = "data:image/png;base64,iVBORw0KGgo="

    h_spot = render_quote_html(preset, slide="slide1", fmt="4:5")
    assert "aspect-ratio:4/3" in h_spot
    assert "transform:scale(" not in h_spot

    h_mag = render_quote_html(preset, slide="slide2", fmt="4:5")
    assert "aspect-ratio:4/3" in h_mag

    h_duel = render_quote_html(preset, slide="slide5", fmt="4:5")
    assert "aspect-ratio:4/3" in h_duel


def test_v363_matchday_results_espn_xg_pulse_counts_and_readable_fonts() -> None:
    from src.xgpedia.providers.matchday_results_free import (
        _infer_understat_league,
        _pack_matchday_card,
        parse_espn_finished_24h_matches,
    )
    from src.xgpedia.render.card_kit.matchday_results_card import render_matchday_results_html

    assert _infer_understat_league({"league_slug": "all", "league": "لیگ برتر انگلیس"}) == "EPL"

    now = datetime(2026, 11, 25, 10, 0, 0, tzinfo=timezone.utc)
    ko = (now - timedelta(hours=6)).isoformat().replace("+00:00", "Z")
    payload = {
        "events": [
            {
                "id": "e99",
                "name": "Arsenal vs Chelsea",
                "date": ko,
                "competitions": [{
                    "status": {"type": {"completed": True, "shortDetail": "FT"}},
                    "competitors": [
                        {"homeAway": "home", "score": "2", "statistics": [{"name": "expectedGoals", "displayValue": "2.34"}], "team": {"id": "1", "displayName": "Arsenal", "abbreviation": "ARS", "color": "EF0107"}},
                        {"homeAway": "away", "score": "1", "statistics": [{"name": "expectedGoals", "displayValue": "0.91"}], "team": {"id": "2", "displayName": "Chelsea", "abbreviation": "CHE", "color": "2563EB"}},
                    ],
                    "details": [
                        {"scoringPlay": True, "clock": {"displayValue": "18'"}, "team": {"id": "1"}, "athletesInvolved": [{"shortName": "Saka"}]},
                        {"scoringPlay": True, "clock": {"displayValue": "67'"}, "team": {"id": "1"}, "athletesInvolved": [{"shortName": "Havertz"}]},
                        {"scoringPlay": True, "clock": {"displayValue": "84'"}, "team": {"id": "2"}, "athletesInvolved": [{"shortName": "Palmer"}]},
                    ],
                }],
            }
        ]
    }
    ms = parse_espn_finished_24h_matches(payload, slug="eng.1", league_fa="لیگ برتر انگلیس", league_en="PREMIER LEAGUE", now_utc=now)
    assert len(ms) == 1
    assert ms[0]["home"]["xg"] == 2.34 and ms[0]["away"]["xg"] == 0.91

    card = _pack_matchday_card("t_xg_pulse", "لیگ برتر انگلیس", "PREMIER LEAGUE", "نتایج", ms)
    html = render_matchday_results_html(card, slide="slide1", fmt="4:5")
    assert "۲.۳۴" in html and "۰.۹۱" in html
    assert "font-size:12.5px;font-weight:900;line-height:1" in html  # اعداد تعداد گل روی میله‌های نبض دقایق گل
    assert "font-size:20px;font-weight:800;color:#F8FAFC" in html  # فونت درشت و خوانای متن تحلیلی
