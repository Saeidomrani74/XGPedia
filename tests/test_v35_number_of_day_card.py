"""تست‌های کامل کارت اسلایدی عدد روز XGPedia (`v0.35.0 — Number of the Day Studio`)."""
from __future__ import annotations

from pathlib import Path


def test_nod_zero_requests_dependency() -> None:
    for p in (
        "src/xgpedia/providers/number_of_day_free.py",
        "src/xgpedia/render/card_kit/number_of_day_card.py",
    ):
        txt = Path(p).read_text(encoding="utf-8")
        assert "import requests" not in txt and "from requests" not in txt


def test_nod_presets_fpl_live_and_news_extractor() -> None:
    from src.xgpedia.providers.number_of_day_free import (
        build_fpl_live_numbers,
        extract_news_number_candidate,
        load_number_of_day_presets,
    )

    presets = load_number_of_day_presets()
    assert len(presets) == 5
    assert presets[0]["number"] == "91"

    mock_boot = {
        "events": [{"id": 12, "is_current": True}],
        "teams": [
            {"id": 1, "code": 3, "name": "Arsenal", "short_name": "ARS"},
            {"id": 2, "code": 14, "name": "Liverpool", "short_name": "LIV"},
            {"id": 3, "code": 43, "name": "Man City", "short_name": "MCI"},
        ],
        "elements": [
            {"id": 10, "code": 223094, "team": 3, "first_name": "Erling", "second_name": "Haaland", "web_name": "Haaland", "goals_scored": 11, "assists": 1, "expected_goals": "8.2", "expected_assists": "1.1", "creativity": "120", "minutes": 990},
            {"id": 20, "code": 118748, "team": 2, "first_name": "Mohamed", "second_name": "Salah", "web_name": "Salah", "goals_scored": 8, "assists": 6, "expected_goals": "7.1", "expected_assists": "4.8", "creativity": "410", "minutes": 980},
            {"id": 30, "code": 223340, "team": 1, "first_name": "Bukayo", "second_name": "Saka", "web_name": "Saka", "goals_scored": 5, "assists": 7, "expected_goals": "4.6", "expected_assists": "5.4", "creativity": "460", "minutes": 940},
        ],
    }
    mock_fx = [
        {"finished": True, "team_h": 1, "team_a": 2, "team_h_score": 2, "team_a_score": 0},
        {"finished": True, "team_h": 2, "team_a": 3, "team_h_score": 2, "team_a_score": 0},
        {"finished": True, "team_h": 1, "team_a": 3, "team_h_score": 3, "team_a_score": 0},
    ]
    live = build_fpl_live_numbers(boot=mock_boot, fixtures=mock_fx)
    assert len(live) >= 4
    ids = [x["id"] for x in live]
    assert any("topscorer" in i for i in ids)
    assert any("clinical" in i for i in ids)
    assert any("assists" in i for i in ids)
    assert any("attack" in i for i in ids)

    # News number extractor & Soccer-only filter
    n1 = extract_news_number_candidate(
        title="Arsenal extend unbeaten streak to 15 matches in Premier League",
        description="A remarkable run of 15 games without defeat.",
        source_name="BBC Sport",
    )
    assert n1 is not None and n1["number"] == "15"

    nfl = extract_news_number_candidate(
        title="Quarterback breaks NFL record with 50 touchdowns",
        description="Super Bowl milestone.",
        source_name="ESPN",
    )
    assert nfl is None


def test_nod_card_5_slides_3_formats_3_fonts_offline() -> None:
    from src.xgpedia.providers.number_of_day_free import load_number_of_day_presets
    from src.xgpedia.render.card_kit.number_of_day_card import (
        NOD_FORMATS,
        NOD_SLIDES,
        render_number_of_day_html,
    )

    assert len(NOD_SLIDES) == 5
    preset = dict(load_number_of_day_presets()[0])
    for sl, _, hm in NOD_SLIDES:
        assert hm == "full"
        for fmt in NOD_FORMATS:
            h = render_number_of_day_html(preset, slide=sl, header_mode=hm, fmt=fmt, theme="lalezar")
            assert "cdn.tailwindcss.com" not in h
            assert "fonts.googleapis.com" not in h
            assert "white-space:nowrap!important" in h
            assert 'stroke="#E62E45"' in h
            assert "@XGPedia" in h

    h_bebas = render_number_of_day_html(preset, slide="slide1", theme="bebas")
    assert ">91<" in h_bebas


def test_nod_bot_workflow_and_hashtags_wired() -> None:
    from src.xgpedia import today_workflow as tw
    from src.xgpedia.publishers import telegram_publish as tp

    assert hasattr(tw, "generate_number_of_day_post_async")
    assert "number_of_day" in tp.POST_TYPE_FA
    assert tp.HASHTAG_BY_TYPE.get("number_of_day") == "#عدد_روز"

    mb_txt = Path("src/xgpedia/publishers/modular_cards_bot.py").read_text(encoding="utf-8")
    assert '"number_of_day": {' in mb_txt and '"prefix": "nd"' in mb_txt and '"cmd": "number"' in mb_txt
    assert "generate_number_of_day_post_async" in mb_txt

    tb_txt = Path("src/xgpedia/publishers/telegram_bot.py").read_text(encoding="utf-8")
    assert "nd:list:1" in tb_txt and "nd:refresh" in tb_txt
    assert "(ماژولار)" not in tb_txt
