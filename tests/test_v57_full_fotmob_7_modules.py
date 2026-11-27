"""تست‌های نسخهٔ 0.57.0: استخراج کامل هر ۷ ماژول پس‌ازبازی از FotMob (xG, ShotMap, Momentum, Top Rated, MOTM, GK, Stats)."""
from __future__ import annotations

from unittest.mock import patch

from src.xgpedia import db as db_mod
from src.xgpedia.providers import xg_engine as xge
from src.xgpedia.render.post_match_cards import build_post_match_context
from src.xgpedia.sync import build_match_facts, merge_post_match_details


def _sample_fotmob_payload() -> dict:
    return {
        "general": {
            "homeTeam": {"id": 8639, "name": "Lille"},
            "awayTeam": {"id": 9823, "name": "Bayern München"},
        },
        "header": {
            "teams": [
                {"id": 8639, "score": 2},
                {"id": 9823, "score": 1},
            ]
        },
        "content": {
            "stats": {
                "Periods": {
                    "All": {
                        "stats": [
                            {
                                "title": "Top stats",
                                "stats": [
                                    {"key": "expected_goals", "title": "Expected goals (xG)", "stats": ["1.94", "0.95"]},
                                    {"key": "big_chance", "title": "Big chances", "stats": [4, 2]},
                                    {"key": "shots_inside_box", "title": "Shots inside box", "stats": [10, 6]},
                                    {"key": "ballPoss", "title": "Ball possession", "stats": [44, 56]},
                                    {"key": "total_shots", "title": "Total shots", "stats": [13, 11]},
                                    {"key": "shotsOnTarget", "title": "Shots on target", "stats": [5, 4]},
                                    {"key": "corners", "title": "Corners", "stats": [5, 6]},
                                ],
                            }
                        ]
                    }
                }
            },
            "shotmap": {
                "shots": [
                    {"teamId": 8639, "x": 95.0, "y": 34.0, "expectedGoals": 0.42, "eventType": "Goal", "playerName": "Jonathan David", "min": 21},
                    {"teamId": 8639, "x": 89.0, "y": 28.0, "expectedGoals": 0.25, "eventType": "AttemptSaved", "playerName": "Edon Zhegrova", "min": 44},
                    {"teamId": 8639, "x": 92.0, "y": 36.0, "expectedGoals": 0.55, "eventType": "Goal", "playerName": "Jonathan David", "min": 78},
                    {"teamId": 9823, "x": 94.0, "y": 35.0, "expectedGoals": 0.38, "eventType": "Goal", "playerName": "Harry Kane", "min": 35},
                    {"teamId": 9823, "x": 85.0, "y": 40.0, "expectedGoals": 0.12, "eventType": "Miss", "playerName": "Jamal Musiala", "min": 61},
                ]
            },
            "momentum": {
                "main": {
                    "data": [{"minute": m, "value": (25 if m % 2 == 0 else -15)} for m in range(1, 91)]
                }
            },
            "lineup": {
                "homeTeam": {
                    "starters": [
                        {"id": "1", "name": "Lucas Chevalier", "shirtNumber": 30, "positionId": "GK", "performance": {"rating": 8.2}},
                        {"id": "2", "name": "Jonathan David", "shirtNumber": 9, "positionId": "FW", "performance": {"rating": 8.8}},
                    ]
                },
                "awayTeam": {
                    "starters": [
                        {"id": "3", "name": "Manuel Neuer", "shirtNumber": 1, "positionId": "GK", "performance": {"rating": 6.7}},
                        {"id": "4", "name": "Harry Kane", "shirtNumber": 9, "positionId": "FW", "performance": {"rating": 7.9}},
                    ]
                },
            },
            "playerStats": {
                "1": {"stats": [{"key": "saves", "stat": {"value": 3}}, {"key": "expected_goals_on_target_faced", "stat": {"value": 1.15}}]},
                "2": {"stats": [{"key": "goals", "stat": {"value": 2}}, {"key": "chances_created", "stat": {"value": 2}}]},
                "3": {"stats": [{"key": "saves", "stat": {"value": 3}}, {"key": "expected_goals_on_target_faced", "stat": {"value": 1.94}}]},
                "4": {"stats": [{"key": "goals", "stat": {"value": 1}}]},
            },
        },
    }


def test_fotmob_extracts_all_7_post_match_modules_end_to_end(tmp_path) -> None:
    parsed = xge.parse_fotmob_match_details(_sample_fotmob_payload())
    assert parsed["home_xg"] == 1.94
    assert parsed["away_xg"] == 0.95
    assert parsed["home_big_chances"] == 4
    assert len(parsed["home_shots"]) == 3
    assert len(parsed["away_shots"]) == 2
    assert len(parsed["momentum"]) == 18
    assert len(parsed["top_players"]) == 4
    assert parsed["motm"]["rating"] == 8.8
    assert parsed["home_gk"]["saves"] == 3
    assert parsed["away_gk"]["name"] == "نویر"

    # بررسی رندر و فعال شدن هم‌زمان تمام ۷ ماژول در build_post_match_context
    test_db = tmp_path / "v57_full.db"
    ko = "2026-11-25T20:00:00Z"
    with patch.object(db_mod, "DATABASE_PATH", test_db):
        db_mod.init_db()
        with db_mod.db() as conn:
            conn.execute(
                "INSERT INTO fixtures (fixture_id, provider, competition, season, kickoff_utc, home_team, away_team, status, collected_at) VALUES ('espn:401915377', 'espn-public', 'UEFA Champions League', '2026-27', ?, 'Lille', 'Bayern Munich', 'finished', ?)",
                (ko, ko),
            )
            conn.execute("INSERT INTO fixture_statistics (fixture_id, team, metric, value, provider, collected_at) VALUES ('espn:401915377', 'Lille', 'goals', 2, 'espn-public', ?)", (ko,))
            conn.execute("INSERT INTO fixture_statistics (fixture_id, team, metric, value, provider, collected_at) VALUES ('espn:401915377', 'Bayern Munich', 'goals', 1, 'espn-public', ?)", (ko,))

        merge_post_match_details(
            "espn:401915377",
            {k: parsed[k] for k in ("home_shots", "away_shots", "home_inside_box", "away_inside_box", "momentum", "top_players", "motm", "home_gk", "away_gk")},
            provider="fotmob",
            extra_stats={
                "Lille": {
                    "expected_goals": parsed["home_xg"],
                    "big_chances": float(parsed["home_big_chances"]),
                    "possession": parsed["home_possession"],
                    "total_shots": parsed["home_total_shots"],
                    "shots_on_target": parsed["home_shots_on_target"],
                },
                "Bayern Munich": {
                    "expected_goals": parsed["away_xg"],
                    "big_chances": float(parsed["away_big_chances"]),
                    "possession": parsed["away_possession"],
                    "total_shots": parsed["away_total_shots"],
                    "shots_on_target": parsed["away_shots_on_target"],
                },
            },
        )
        facts = build_match_facts("espn:401915377", post_match=True)
        ctx = build_post_match_context({"title": "", "bullets": [], "caption": ""}, facts, fmt="4:5")
        for mod in ("xgrace", "shotmap", "momentum", "efficiency", "toprated", "motm", "stats"):
            assert ctx["has"][mod] is True, f"Module {mod} was NOT enabled!"
