"""تست‌های نسخه v0.40.0 — کارت ۵اسلایدی «ترکیب احتمالی و غایبان» (`lineup_injuries`)."""
from __future__ import annotations

from pathlib import Path

from src.xgpedia.providers.lineup_injuries_free import (
    build_lineup_injuries_from_fpl,
    load_lineup_injuries_presets,
)
from src.xgpedia.publishers import telegram_publish as tp
from src.xgpedia.render.card_kit.lineup_injuries_card import (
    LINEUP_FORMATS,
    LINEUP_SLIDES,
    get_lineup_injuries_modules,
    render_lineup_injuries_html,
)


def test_lineup_injuries_presets_render_all_five_slides_and_formats_offline() -> None:
    presets = load_lineup_injuries_presets()
    assert len(presets) >= 2
    it = presets[0]
    mods, missing = get_lineup_injuries_modules(it, "slide1")
    assert len(mods) == 3
    assert not missing

    for sid, _, _ in LINEUP_SLIDES:
        for fmt in LINEUP_FORMATS:
            html = render_lineup_injuries_html(it, slide=sid, fmt=fmt, theme="classic", modules=mods)
            assert "<!DOCTYPE html>" in html
            assert "https://cdn." not in html
            assert "https://fonts.googleapis.com" not in html
            assert "@XGPedia" in html
            assert "آرسنال" in html


def test_build_lineup_injuries_from_fpl_live_data() -> None:
    def _mk_squad(tid: int, prefix: str) -> list[dict]:
        squad = [
            {"web_name": f"{prefix}GK", "team": tid, "element_type": 1, "minutes": 900, "status": "a", "chance_of_playing_next_round": 100, "expected_goal_involvements": "0.0"},
        ]
        for i in range(4):
            squad.append({"web_name": f"{prefix}D{i}", "team": tid, "element_type": 2, "minutes": 850 - i * 20, "status": "a", "chance_of_playing_next_round": 100, "expected_goal_involvements": "0.5"})
        for i in range(4):
            squad.append({"web_name": f"{prefix}M{i}", "team": tid, "element_type": 3, "minutes": 820 - i * 15, "status": "a", "chance_of_playing_next_round": 100 if i != 3 else 75, "expected_goal_involvements": "3.2"})
        for i in range(2):
            squad.append({"web_name": f"{prefix}F{i}", "team": tid, "element_type": 4, "minutes": 800 - i * 30, "status": "a", "chance_of_playing_next_round": 100, "expected_goal_involvements": "5.5"})
        # یک بازیکن مصدوم (۰٪)
        squad.append({"web_name": f"{prefix}Inj", "team": tid, "element_type": 2, "minutes": 400, "status": "i", "chance_of_playing_next_round": 0, "expected_goal_involvements": "0.2"})
        return squad

    boot = {
        "teams": [
            {"id": 1, "short_name": "ARS", "name": "Arsenal"},
            {"id": 2, "short_name": "LIV", "name": "Liverpool"},
        ],
        "elements": _mk_squad(1, "A") + _mk_squad(2, "L"),
    }
    fixtures = [
        {"id": 101, "event": 15, "finished": False, "team_h": 1, "team_a": 2, "kickoff_time": "2026-12-06T16:30:00Z"},
    ]
    items = build_lineup_injuries_from_fpl(boot, fixtures)
    assert len(items) == 1
    it = items[0]
    assert it["is_live"] is True
    assert len(it["home"]["lineup"]) == 11
    assert len(it["away"]["lineup"]) == 11
    assert any(ab["chance"] == 0 for ab in it["home"]["absentees"])
    assert len(it["key_duels"]) >= 2


def test_lineup_injuries_bot_and_publish_wiring() -> None:
    assert "lineup_injuries" in tp.POST_TYPE_FA
    assert tp.HASHTAG_BY_TYPE["lineup_injuries"] == "#ترکیب_احتمالی"
    mb_src = Path("src/xgpedia/publishers/modular_cards_bot.py").read_text(encoding="utf-8")
    assert '"lineup_injuries": {' in mb_src
    assert '"cmd": "lineup"' in mb_src
    assert '"list_hint":' in mb_src
