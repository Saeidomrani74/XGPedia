"""تست‌های کامل کارت اسلایدی مناظره فوتبالی XGPedia (`v0.34.0 — Debate Studio`)."""
from __future__ import annotations

from pathlib import Path


def test_debate_zero_requests_dependency() -> None:
    for p in (
        "src/xgpedia/providers/debate_free.py",
        "src/xgpedia/render/card_kit/debate_card.py",
    ):
        txt = Path(p).read_text(encoding="utf-8")
        assert "import requests" not in txt and "from requests" not in txt


def test_debate_presets_fpl_live_and_news_extractor() -> None:
    from src.xgpedia.providers.debate_free import (
        build_fpl_live_debates,
        extract_news_debate_candidate,
        load_debate_presets,
    )

    presets = load_debate_presets()
    assert len(presets) == 5

    # 1. Live quantitative FPL debates (Golden Boot + Title Race + Playmaker)
    mock_boot = {
        "events": [{"id": 12, "is_current": True}],
        "teams": [
            {"id": 1, "code": 3, "name": "Arsenal", "short_name": "ARS"},
            {"id": 2, "code": 14, "name": "Liverpool", "short_name": "LIV"},
            {"id": 3, "code": 43, "name": "Man City", "short_name": "MCI"},
        ],
        "elements": [
            {"id": 10, "code": 223094, "team": 3, "first_name": "Erling", "second_name": "Haaland", "goals_scored": 11, "assists": 1, "expected_goals": "9.4", "expected_assists": "1.2", "threat": "610", "creativity": "120", "influence": "490", "bps": 340, "minutes": 990},
            {"id": 20, "code": 118748, "team": 2, "first_name": "Mohamed", "second_name": "Salah", "goals_scored": 9, "assists": 6, "expected_goals": "7.8", "expected_assists": "4.9", "threat": "520", "creativity": "410", "influence": "470", "bps": 330, "minutes": 980},
            {"id": 30, "code": 223340, "team": 1, "first_name": "Bukayo", "second_name": "Saka", "goals_scored": 5, "assists": 7, "expected_goals": "4.6", "expected_assists": "5.4", "threat": "400", "creativity": "460", "influence": "420", "bps": 310, "minutes": 940},
        ],
    }
    mock_fx = [
        {"finished": True, "team_h": 1, "team_a": 2, "team_h_score": 2, "team_a_score": 1},
        {"finished": True, "team_h": 2, "team_a": 3, "team_h_score": 2, "team_a_score": 0},
        {"finished": True, "team_h": 1, "team_a": 3, "team_h_score": 1, "team_a_score": 1},
    ]
    live_db = build_fpl_live_debates(boot=mock_boot, fixtures=mock_fx)
    assert len(live_db) == 3
    ids = [d["id"] for d in live_db]
    assert any("goldenboot" in i for i in ids)
    assert any("titlerace" in i for i in ids)
    assert any("playmaker" in i for i in ids)
    gb = next(d for d in live_db if "goldenboot" in d["id"])
    assert gb["sideA"]["name"] == "ارلینگ هالند" and gb["sideB"]["name"] == "محمد صلاح"
    assert len(gb["radarA"]) == 6 and len(gb["metrics"]) == 4

    # 2. Live news debate extractor (clash + VAR + Soccer-only guard)
    clash = extract_news_debate_candidate(
        title="Arsenal vs Liverpool: Who is better equipped for the Premier League title race?",
        description="Comparing Mikel Arteta and Arne Slot ahead of a decisive weekend.",
        source_name="BBC Sport",
    )
    assert clash is not None and clash["sideA"]["code"] == "ARS" and clash["sideB"]["code"] == "LIV"

    var_db = extract_news_debate_candidate(
        title="VAR controversy after late penalty decision sparks referee debate",
        description="Should Premier League referees change how VAR reviews penalties?",
        source_name="The Guardian",
    )
    assert var_db is not None and var_db["sideA"]["code"] == "PRO" and var_db["sideB"]["code"] == "CON"

    nba = extract_news_debate_candidate(
        title="NBA debate: Who is better in the playoffs?",
        description="Basketball analysts argue over MVP race.",
        source_name="ESPN",
    )
    assert nba is None


def test_debate_card_5_slides_3_formats_3_themes_offline() -> None:
    from src.xgpedia.providers.debate_free import load_debate_presets
    from src.xgpedia.render.card_kit.debate_card import (
        DEBATE_FORMATS,
        DEBATE_SLIDES,
        render_debate_html,
    )

    assert len(DEBATE_SLIDES) == 5
    preset = dict(load_debate_presets()[0])
    for sl, _, hm in DEBATE_SLIDES:
        assert hm == "full"
        for fmt in DEBATE_FORMATS:
            h = render_debate_html(preset, slide=sl, header_mode=hm, fmt=fmt, theme="classic")
            assert "cdn.tailwindcss.com" not in h
            assert "fonts.googleapis.com" not in h
            assert "html2canvas" not in h
            assert "white-space:nowrap!important" in h
            assert 'stroke="#E62E45"' in h
            assert "@XGPedia" in h

    # Theme check
    h_pitch = render_debate_html(preset, slide="slide1", theme="pitch")
    h_derby = render_debate_html(preset, slide="slide3", theme="derby")
    assert "#071122" in h_pitch
    assert "#100A1C" in h_derby and "HOT TAKE" in h_derby


def test_debate_bot_workflow_and_hashtags_wired() -> None:
    from src.xgpedia import today_workflow as tw
    from src.xgpedia.publishers import telegram_publish as tp

    assert hasattr(tw, "generate_debate_post_async")
    assert "debate" in tp.POST_TYPE_FA
    assert tp.HASHTAG_BY_TYPE.get("debate") == "#مناظره_فوتبالی"

    mb_txt = Path("src/xgpedia/publishers/modular_cards_bot.py").read_text(encoding="utf-8")
    assert '"debate": {' in mb_txt and '"prefix": "db"' in mb_txt and '"cmd": "debate"' in mb_txt
    assert "generate_debate_post_async" in mb_txt

    tb_txt = Path("src/xgpedia/publishers/telegram_bot.py").read_text(encoding="utf-8")
    assert "db:list:1" in tb_txt and "db:refresh" in tb_txt
    assert "(ماژولار)" not in tb_txt
