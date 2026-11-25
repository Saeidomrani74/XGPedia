"""تست‌های جامع نسخه v0.37.0:
  1. رفع باگ تاریخچه تقابل تیم‌ها (H2H Teams): نمایش تاریخچه چندفصله (football-data.co.uk E0.csv + openfootball + Understat) به جای تک‌بازی فصل جاری
  2. کارت اسلایدی و ماژولار «خلاصهٔ هفته + فرم در برابر جدول» (`Matchweek Wrap-up & Form vs. Table Studio`) در ۵ اسلاید و ۳ فرمت
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def test_v37_zero_requests_dependency() -> None:
    for p in (
        "src/xgpedia/providers/pl_picker_free.py",
        "src/xgpedia/providers/matchweek_wrapup_free.py",
        "src/xgpedia/render/card_kit/matchweek_wrapup_card.py",
    ):
        txt = Path(p).read_text(encoding="utf-8")
        assert "import requests" not in txt and "from requests" not in txt


def test_v37_h2h_teams_merges_multi_season_historical_results() -> None:
    from src.xgpedia.providers import pl_picker_free as ppf

    mock_boot = {
        "events": [{"id": 12, "deadline_time": "2026-08-15T17:30:00Z"}],
        "teams": [
            {"id": 1, "code": 3, "name": "Arsenal", "short_name": "ARS"},
            {"id": 5, "code": 36, "name": "Brighton", "short_name": "BHA"},
        ],
        "elements": [],
    }
    mock_fx = [
        {"finished": True, "team_h": 5, "team_a": 1, "team_h_score": 3, "team_a_score": 0, "kickoff_time": "2026-10-18T14:00:00Z"},
    ]
    # تاریخچه چندفصله شبیه‌سازی‌شده از E0.csv (آرسنال × برایتون)
    mock_csv_hist = [
        {"date": "2025-01-04", "year": "2025", "comp": "لیگ برتر", "t1_is_home": False, "hg": 1, "ag": 1, "hxg": None, "axg": None},
        {"date": "2024-08-31", "year": "2024", "comp": "لیگ برتر", "t1_is_home": True, "hg": 1, "ag": 1, "hxg": None, "axg": None},
        {"date": "2024-04-06", "year": "2024", "comp": "لیگ برتر", "t1_is_home": False, "hg": 3, "ag": 0, "hxg": None, "axg": None},
        {"date": "2023-12-17", "year": "2023", "comp": "لیگ برتر", "t1_is_home": True, "hg": 2, "ag": 0, "hxg": None, "axg": None},
        {"date": "2023-05-14", "year": "2023", "comp": "لیگ برتر", "t1_is_home": True, "hg": 0, "ag": 3, "hxg": None, "axg": None},
    ]
    with (
        patch.object(ppf, "_collect_multi_season_pl_h2h", return_value=[]),
        patch.object(ppf, "_collect_football_data_couk_pl_h2h", return_value=mock_csv_hist),
    ):
        item = ppf.build_pl_h2h_teams_item(1, 5, boot=mock_boot, fixtures=mock_fx)
        assert item is not None
        tot = item["home"]["wins"] + item["draws"] + item["away"]["wins"]
        # باید کل ۶ تقابل (۵ تاریخی + ۱ فصل جاری) ثبت شده باشد نه فقط ۱ بازی!
        assert tot == 6
        assert item["home"]["wins"] == 2 and item["draws"] == 2 and item["away"]["wins"] == 2
        assert len(item["recent5"]) == 5


def test_v37_matchweek_wrapup_provider_fpl_live_and_presets() -> None:
    from src.xgpedia.providers.matchweek_wrapup_free import (
        build_fpl_matchweek_wrapup,
        load_matchweek_wrapup_presets,
    )

    presets = load_matchweek_wrapup_presets()
    assert len(presets) >= 2

    mock_boot = {
        "events": [{"id": 12, "is_current": True}],
        "teams": [
            {"id": 1, "code": 3, "name": "Arsenal", "short_name": "ARS"},
            {"id": 2, "code": 14, "name": "Liverpool", "short_name": "LIV"},
            {"id": 3, "code": 43, "name": "Man City", "short_name": "MCI"},
            {"id": 4, "code": 8, "name": "Chelsea", "short_name": "CHE"},
        ],
        "elements": [
            {"id": 101, "team": 1, "element_type": 1, "web_name": "Raya", "expected_goals": "0.0"},
            {"id": 102, "team": 1, "element_type": 2, "web_name": "Gabriel", "expected_goals": "1.2"},
            {"id": 103, "team": 2, "element_type": 3, "web_name": "Salah", "expected_goals": "3.1"},
            {"id": 104, "team": 3, "element_type": 4, "web_name": "Haaland", "expected_goals": "4.8"},
            {"id": 105, "team": 4, "element_type": 3, "web_name": "Palmer", "expected_goals": "3.9"},
        ],
    }
    mock_fx = [
        {"finished": True, "team_h": 1, "team_a": 2, "team_h_score": 3, "team_a_score": 1, "kickoff_time": "2026-10-01T14:00:00Z"},
        {"finished": True, "team_h": 3, "team_a": 4, "team_h_score": 2, "team_a_score": 0, "kickoff_time": "2026-10-01T16:00:00Z"},
        {"finished": True, "team_h": 1, "team_a": 3, "team_h_score": 2, "team_a_score": 0, "kickoff_time": "2026-10-08T14:00:00Z"},
        {"finished": True, "team_h": 2, "team_a": 4, "team_h_score": 2, "team_a_score": 1, "kickoff_time": "2026-10-08T16:00:00Z"},
    ]
    mock_live = {
        "elements": [
            {"id": 101, "stats": {"minutes": 90, "total_points": 9, "clean_sheets": 1, "saves": 4, "bps": 32}},
            {"id": 102, "stats": {"minutes": 90, "total_points": 12, "goals_scored": 1, "clean_sheets": 1, "bps": 40}},
            {"id": 103, "stats": {"minutes": 90, "total_points": 14, "goals_scored": 2, "assists": 1, "bps": 46}},
            {"id": 104, "stats": {"minutes": 90, "total_points": 11, "goals_scored": 2, "bps": 39}},
        ]
    }
    wrap = build_fpl_matchweek_wrapup(boot=mock_boot, fixtures=mock_fx, gw_live=mock_live)
    assert wrap is not None
    assert wrap["awards"]["bestAttack"]["code"] == "ARS"
    assert len(wrap["formVsTable"]) == 4
    assert len(wrap["totw"]) == 4


def test_v37_matchweek_wrapup_card_5_slides_3_formats_offline_and_null_guard() -> None:
    from src.xgpedia.providers.matchweek_wrapup_free import load_matchweek_wrapup_presets
    from src.xgpedia.render.card_kit.matchweek_wrapup_card import (
        WRAPUP_FORMATS,
        WRAPUP_SLIDES,
        get_matchweek_wrapup_modules,
        render_matchweek_wrapup_html,
    )

    assert len(WRAPUP_SLIDES) == 5
    preset = dict(load_matchweek_wrapup_presets()[0])
    for sl, _, _, _ in WRAPUP_SLIDES:
        for fmt in WRAPUP_FORMATS:
            h = render_matchweek_wrapup_html(preset, slide=sl, fmt=fmt, theme="classic")
            assert "cdn.tailwindcss.com" not in h
            assert "fonts.googleapis.com" not in h
            assert "white-space:nowrap!important" in h
            assert 'stroke="#E62E45"' in h
            assert "@XGPedia" in h
            assert "data:image/" in h  # لوگوی واقعی باشگاه‌های انگلیس

    # قانون null != 0: اگر تیم منتخب هفته خالی باشد، ماژول totw_pitch حذف می‌شود
    no_totw = dict(preset, totw=[])
    mods, miss = get_matchweek_wrapup_modules(no_totw, "slide5")
    assert all(m["id"] != "totw_pitch" for m in mods)
    assert any("تیم منتخب" in m for m in miss)


def test_v37_matchweek_wrapup_bot_and_hashtags_wired() -> None:
    from src.xgpedia import today_workflow as tw
    from src.xgpedia.publishers import telegram_publish as tp

    assert hasattr(tw, "generate_matchweek_wrapup_post_async")
    assert "matchweek_wrapup" in tp.POST_TYPE_FA
    assert tp.HASHTAG_BY_TYPE.get("matchweek_wrapup") == "#خلاصه_هفته"

    mb_txt = Path("src/xgpedia/publishers/modular_cards_bot.py").read_text(encoding="utf-8")
    assert '"matchweek_wrapup": {' in mb_txt and '"prefix": "mw"' in mb_txt and '"cmd": "wrapup"' in mb_txt
    assert "generate_matchweek_wrapup_post_async" in mb_txt

    tb_txt = Path("src/xgpedia/publishers/telegram_bot.py").read_text(encoding="utf-8")
    assert "mw:list:1" in tb_txt
