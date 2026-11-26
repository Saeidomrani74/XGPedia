"""تست‌های نسخهٔ 0.68.0: تکمیل جدول گلزنان (توکن FDO، پنالتی واقعی، xG، لوگوی باشگاه‌های اروپا، رفع بریدگی ردیف ۸) و GOAL API."""
from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

from src.xgpedia.providers import goal_api as ga
from src.xgpedia.providers import top_scorers_free as tsf
from src.xgpedia.render.card_kit import top_scorers_card as tsc


def test_fdo_token_reads_standard_football_data_org_token() -> None:
    with patch.dict(os.environ, {"FOOTBALL_DATA_ORG_TOKEN": "tok_real_123", "FOOTBALL_DATA_API_KEY": ""}, clear=False):
        assert tsf._get_fdo_token() == "tok_real_123"


def test_build_league_scorer_entry_has_persian_name_real_club_crest_penalties_and_xg() -> None:
    u_map = {
        "harry kane": {"goals": 14, "pen": 4, "xg": 11.2, "mins": 990, "shots": 42},
    }
    p = tsf._build_league_scorer_entry(
        "Harry Kane", "FC Bayern München", "FCB", 14, 4, 900, "Offence", understat_map=u_map
    )
    assert p["name"] == "هری کین"
    assert p["club"] == "بایرن مونیخ"
    assert p["club_en"] == "Bayern Munich"
    assert p["code"] == "BAY"
    assert p["logoUrl"] is not None and p["logoUrl"].startswith("data:")
    assert p["pen"] == 4
    assert p["xg"] == 11.2
    assert p["mins"] == 990
    assert p["shots"] == 42

    # null ≠ 0 وقتی Understat و FDO مقدار پنالتی/xG ندادند
    p_none = tsf._build_league_scorer_entry("Test Striker", "RB Leipzig", "RBL", 5, None, None, "Offence", understat_map={})
    assert p_none["pen"] is None
    assert p_none["xg"] is None


def test_goal_api_league_resolution_and_top_scorers_parsing() -> None:
    ga._LEAGUE_ID_CACHE.clear()
    ga._LEAGUE_CACHE_TS = 0.0

    leagues_payload = {
        "success": True,
        "data": [
            {"id": "152", "name": "Premier League", "country": "England"},
            {"id": "175", "name": "Bundesliga", "country": "Germany"},
            {"id": "4", "name": "UEFA Europa League", "country": "Europe"},
        ],
    }
    scorers_payload = {
        "success": True,
        "data": [
            {"playerName": "Harry Kane", "teamName": "Bayern Munich", "goals": 14, "penalties": 4, "minutesPlayed": 990},
            {"playerName": "Patrik Schick", "teamName": "Bayer Leverkusen", "goals": 9, "penalties": 1, "matchesPlayed": 10},
        ],
    }

    def _fake_urlopen(req, timeout=10.0):
        m = MagicMock()
        u = req.full_url
        if "/leagues?" in u:
            m.read.return_value = json.dumps(leagues_payload).encode("utf-8")
        else:
            m.read.return_value = json.dumps(scorers_payload).encode("utf-8")
        m.__enter__.return_value = m
        return m

    with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
        assert ga.resolve_goal_api_league_id("BL1", api_key="gapi_test") == "175"
        assert ga.resolve_goal_api_league_id("EL", api_key="gapi_test") == "4"
        rows = ga.fetch_goal_api_top_scorers("BL1", api_key="gapi_test")
    assert len(rows) == 2
    assert rows[0]["name"] == "Harry Kane" and rows[0]["pen"] == 4 and rows[0]["mins"] == 990
    assert rows[1]["name"] == "Patrik Schick" and rows[1]["pen"] == 1 and rows[1]["mins"] == 900


def test_top_scorers_card_uses_european_crest_and_prevents_row8_clipping() -> None:
    crest_html = tsc._crest_svg({"club": "بایرن مونیخ", "club_en": "Bayern Munich", "code": "BAY", "color": "#DC052D", "secondary": "#FFFFFF"})
    assert "<img " in crest_html and "data:" in crest_html
    src = open("src/xgpedia/render/card_kit/top_scorers_card.py", encoding="utf-8").read()
    assert "padding:5px 12px" in src
    assert "min-height:0" in src
