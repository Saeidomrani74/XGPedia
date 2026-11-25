"""تست‌های نسخه v0.39.0 — کارت ۵اسلایدی «رادار ارزش بازار و شکار نقل‌وانتقالات (+EV)»."""
from __future__ import annotations

from pathlib import Path

from src.xgpedia.providers.value_radar_free import (
    build_value_radar_editions_from_bootstrap,
    load_value_radar_presets,
)
from src.xgpedia.publishers import telegram_publish as tp
from src.xgpedia.render.card_kit.value_radar_card import (
    VALUE_RADAR_FORMATS,
    VALUE_RADAR_SLIDES,
    get_value_radar_modules,
    render_value_radar_html,
)


def test_value_radar_presets_load_and_render_all_five_slides_and_formats() -> None:
    presets = load_value_radar_presets()
    assert len(presets) >= 2
    it = presets[0]
    mods, missing = get_value_radar_modules(it, "slide1")
    assert len(mods) == 3
    assert not missing

    for sid, _, _ in VALUE_RADAR_SLIDES:
        for fmt in VALUE_RADAR_FORMATS:
            html = render_value_radar_html(it, slide=sid, fmt=fmt, theme="classic", modules=mods)
            assert "<!DOCTYPE html>" in html
            assert "https://cdn." not in html
            assert "https://fonts.googleapis.com" not in html
            assert "@XGPedia" in html
            assert "data:image/svg+xml;base64," in html  # لوگوی واقعی باشگاه‌های لیگ برتر


def test_build_value_radar_editions_from_live_fpl_bootstrap() -> None:
    fake_boot = {
        "teams": [
            {"id": 1, "short_name": "ARS", "name": "Arsenal"},
            {"id": 2, "short_name": "AVL", "name": "Aston Villa"},
            {"id": 3, "short_name": "MCI", "name": "Man City"},
            {"id": 4, "short_name": "BOU", "name": "Bournemouth"},
        ],
        "elements": [
            {"first_name": "Morgan", "second_name": "Rogers", "web_name": "Rogers", "team": 2, "element_type": 3, "now_cost": 55, "minutes": 900, "goals_scored": 5, "assists": 4, "expected_goals": "4.2", "expected_assists": "3.0", "expected_goal_involvements": "7.2", "clean_sheets": 3, "selected_by_percent": "6.4"},
            {"first_name": "Antoine", "second_name": "Semenyo", "web_name": "Semenyo", "team": 4, "element_type": 3, "now_cost": 57, "minutes": 900, "goals_scored": 6, "assists": 2, "expected_goals": "5.0", "expected_assists": "2.0", "expected_goal_involvements": "7.0", "clean_sheets": 2, "selected_by_percent": "5.1"},
            {"first_name": "Erling", "second_name": "Haaland", "web_name": "Haaland", "team": 3, "element_type": 4, "now_cost": 150, "minutes": 900, "goals_scored": 10, "assists": 1, "expected_goals": "9.0", "expected_assists": "1.0", "expected_goal_involvements": "10.0", "clean_sheets": 4, "selected_by_percent": "62.0"},
            {"first_name": "Bukayo", "second_name": "Saka", "web_name": "Saka", "team": 1, "element_type": 3, "now_cost": 100, "minutes": 900, "goals_scored": 6, "assists": 6, "expected_goals": "4.5", "expected_assists": "4.5", "expected_goal_involvements": "9.0", "clean_sheets": 5, "selected_by_percent": "35.0"},
            {"first_name": "Ollie", "second_name": "Watkins", "web_name": "Watkins", "team": 2, "element_type": 4, "now_cost": 88, "minutes": 900, "goals_scored": 7, "assists": 2, "expected_goals": "6.5", "expected_assists": "1.5", "expected_goal_involvements": "8.0", "clean_sheets": 3, "selected_by_percent": "20.0"},
            {"first_name": "Evanilson", "second_name": "Lima", "web_name": "Evanilson", "team": 4, "element_type": 4, "now_cost": 60, "minutes": 900, "goals_scored": 5, "assists": 2, "expected_goals": "5.4", "expected_assists": "1.0", "expected_goal_involvements": "6.4", "clean_sheets": 2, "selected_by_percent": "4.0"},
            {"first_name": "Kai", "second_name": "Havertz", "web_name": "Havertz", "team": 1, "element_type": 4, "now_cost": 80, "minutes": 900, "goals_scored": 6, "assists": 2, "expected_goals": "5.8", "expected_assists": "1.4", "expected_goal_involvements": "7.2", "clean_sheets": 5, "selected_by_percent": "14.0"},
            {"first_name": "Low", "second_name": "Minutes", "web_name": "Bench", "team": 1, "element_type": 3, "now_cost": 45, "minutes": 40, "goals_scored": 1, "assists": 0, "expected_goals": "0.5", "expected_assists": "0.0", "expected_goal_involvements": "0.5", "clean_sheets": 0, "selected_by_percent": "0.5"},
        ],
    }
    editions = build_value_radar_editions_from_bootstrap(fake_boot, min_minutes=270)
    assert len(editions) >= 2
    all_ed = next(e for e in editions if e["id"] == "live_vr_pl_all")
    assert all_ed["is_live"] is True
    # بازیکن کم‌دقیقه (۴۰ دقیقه) نباید وارد لیست شود
    assert all(p["name_en"] != "Low Minutes" for p in all_ed["players"])
    # مورگان راجرز (£5.5M, xGI/90=0.72 -> EV=13.1) باید رتبه ۱ باشد و هالند معیار گران‌قیمت باشد
    assert all_ed["players"][0]["name_en"] == "Morgan Rogers"
    assert all_ed["premium_benchmark"]["name_en"] == "Erling Haaland"


def test_value_radar_publish_and_bot_spec_wiring() -> None:
    assert "value_radar" in tp.POST_TYPE_FA
    assert tp.HASHTAG_BY_TYPE["value_radar"] == "#رادار_ارزش_بازار"
    mb_src = Path("src/xgpedia/publishers/modular_cards_bot.py").read_text(encoding="utf-8")
    assert '"value_radar": {' in mb_src
    assert '"list_hint":' in mb_src
    assert '"cmd": "value"' in mb_src
