"""تست‌های نسخهٔ 0.54.0: موتور واقعی xG (SofaScore/FotMob Opta)، حذف فرمول جعلی، تبدیل & به و، و نام کوتاه اتلتیکو."""
from __future__ import annotations

from unittest.mock import patch

from src.xgpedia.config import card_short_team_name_fa, translate_coach_fa
from src.xgpedia.providers import espn_free as ef
from src.xgpedia.providers import xg_engine as xge


def test_coach_ampersand_replaced_with_persian_va() -> None:
    assert translate_coach_fa("Bjarte Lunde Aarsheim & Morten Jensen") == "بجارته لونده آرشایم و مورتن جنسن" or (
        " و " in (translate_coach_fa("Bjarte Lunde Aarsheim & Morten Jensen") or "")
        and "&" not in (translate_coach_fa("Bjarte Lunde Aarsheim & Morten Jensen") or "")
    )
    assert translate_coach_fa("بجارته لونده آرشایم & مورتن جنسن") == "بجارته لونده آرشایم و مورتن جنسن"


def test_atletico_short_name_is_atletico_not_madrid() -> None:
    assert card_short_team_name_fa("Atlético Madrid", "اتلتیکو مادرید") == "اتلتیکو"
    assert card_short_team_name_fa("Club Atlético de Madrid", "اتلتیکو مادرید") == "اتلتیکو"
    assert card_short_team_name_fa("Atletico Madrid", "اتلتیکو مادرید") == "اتلتیکو"
    assert card_short_team_name_fa("Real Madrid", "رئال مادرید") == "رئال مادرید"
    assert card_short_team_name_fa("Athletic Club", "اتلتیک بیلبائو") == "بیلبائو"


def test_espn_does_not_fabricate_fake_xg_from_shots() -> None:
    summary = {
        "header": {
            "id": "575408",
            "competitions": [
                {
                    "date": "2026-11-25T20:00:00Z",
                    "competitors": [
                        {"homeAway": "home", "score": "2", "team": {"displayName": "Atletico Madrid"}},
                        {"homeAway": "away", "score": "0", "team": {"displayName": "Viking FK"}},
                    ],
                }
            ],
        },
        "boxscore": {
            "teams": [
                {
                    "team": {"displayName": "Atletico Madrid"},
                    "statistics": [
                        {"name": "totalShots", "displayValue": "20"},
                        {"name": "shotsOnTarget", "displayValue": "9"},
                    ],
                },
                {
                    "team": {"displayName": "Viking FK"},
                    "statistics": [
                        {"name": "totalShots", "displayValue": "9"},
                        {"name": "shotsOnTarget", "displayValue": "1"},
                    ],
                },
            ]
        },
        "keyEvents": [],
    }
    parsed = ef.parse_espn_finished_summary(summary)
    assert parsed is not None
    # هرگز نباید 3.45 یا 0.79 ساختگی تولید شود
    assert "expected_goals" not in parsed["home_stats"]
    assert "expected_goals" not in parsed["away_stats"]


def test_sofascore_and_fotmob_real_opta_xg_parsers() -> None:
    assert xge._teams_match("Atlético Madrid", "Atlético Madrid") is True
    assert xge._teams_match("Atletico Madrid", "Real Madrid") is False
    assert xge._teams_match("Viking FK", "Viking") is True

    sofa_stats = {
        "statistics": [
            {
                "period": "ALL",
                "groups": [
                    {
                        "groupName": "Match overview",
                        "statisticsItems": [
                            {"key": "expectedGoals", "name": "Expected goals", "homeValue": 1.92, "awayValue": 0.62},
                            {"key": "bigChanceCreated", "name": "Big chances", "homeValue": 3, "awayValue": 1},
                            {"key": "totalShotsInsideBox", "name": "Shots inside box", "homeValue": 14, "awayValue": 5},
                        ],
                    }
                ],
            }
        ]
    }
    s_parsed = xge.parse_sofascore_statistics(sofa_stats)
    assert s_parsed["home_xg"] == 1.92
    assert s_parsed["away_xg"] == 0.62
    assert s_parsed["home_big_chances"] == 3
    assert s_parsed["away_inside_box"] == 5

    fotmob_det = {
        "content": {
            "stats": {
                "Periods": {
                    "All": {
                        "stats": [
                            {
                                "title": "Top stats",
                                "stats": [
                                    {"key": "expected_goals", "title": "Expected goals (xG)", "stats": ["1.92", "0.62"]},
                                    {"key": "big_chance", "title": "Big chances", "stats": [3, 1]},
                                ],
                            }
                        ]
                    }
                }
            }
        }
    }
    f_parsed = xge.parse_fotmob_match_details(fotmob_det)
    assert f_parsed["home_xg"] == 1.92
    assert f_parsed["away_xg"] == 0.62

    # تست آبشار: SofaScore در دسترس نباشد -> خودکار به FotMob می‌رود
    with (
        patch.object(xge, "fetch_sofascore_match_xg", return_value=None),
        patch.object(xge, "fetch_fotmob_match_xg", return_value={"home_xg": 1.92, "away_xg": 0.62, "provider": "fotmob"}),
    ):
        res = xge.fetch_real_match_xg("Atletico Madrid", "Viking FK", "2026-11-25", competition="UEFA Champions League")
        assert res is not None
        assert res["provider"] == "fotmob"
        assert res["home_xg"] == 1.92
        assert res["away_xg"] == 0.62


def test_fotmob_next_data_ssr_html_and_lille_bayern_match() -> None:
    import json
    assert xge._teams_match("LOSC Lille", "Lille") is True
    assert xge._teams_match("FC Bayern München", "Bayern Munich") is True

    next_payload = {
        "props": {
            "pageProps": {
                "content": {
                    "stats": {
                        "Periods": {
                            "All": {
                                "stats": [
                                    {
                                        "title": "Top stats",
                                        "stats": [
                                            {"key": "expected_goals", "title": "Expected goals (xG)", "stats": ["1.94", "0.95"]},
                                        ],
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        }
    }
    html = f'<html><head></head><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(next_payload)}</script></body></html>'
    parsed = xge.parse_fotmob_next_data_html(html)
    assert parsed["home_xg"] == 1.94
    assert parsed["away_xg"] == 0.95
