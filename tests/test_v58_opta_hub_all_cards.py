"""تست‌های نسخهٔ 0.58.0: اتصال هاب مرکزی Opta/Understat به همهٔ کارت‌های ماژولار پروژه."""
from __future__ import annotations

from unittest.mock import patch

from src.xgpedia import db as db_mod
from src.xgpedia.providers import (
    h2h_players_free as h2p,
    matchday_results_free as mdr,
    opta_hub as hub,
    player_fc27_free as pfc,
    player_profile_free as ppf,
)
from src.xgpedia.sync import merge_post_match_details


def test_matchday_results_and_shotmap_use_db_fotmob_opta_for_ucl(tmp_path) -> None:
    test_db = tmp_path / "v58_opta_hub.db"
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
            {
                "xg_provider": "fotmob",
                "home_shots": [[92.0, 48.0, 0.45, "goal", "دیوید", 21]],
                "away_shots": [[88.0, 52.0, 0.32, "goal", "کین", 35]],
                "home_inside_box": 8,
                "away_inside_box": 5,
            },
            provider="fotmob",
            extra_stats={
                "Lille": {"expected_goals": 1.94, "big_chances": 4.0},
                "Bayern Munich": {"expected_goals": 0.95, "big_chances": 2.0},
            },
        )

        # ۱) Matchday Results باید xG واقعی Opta چمپیونزلیگ را از opta_hub بگیرد
        matches = [
            {
                "league_slug": "uefa.champions",
                "home": {"name_en": "Lille", "name": "لیل", "score": 2, "xg": None},
                "away": {"name_en": "Bayern Munich", "name": "بایرن مونیخ", "score": 1, "xg": None},
            }
        ]
        mdr.enrich_matches_with_real_xg(matches, understat_cache={})
        assert matches[0]["home"]["xg"] == 1.94
        assert matches[0]["away"]["xg"] == 0.95

        # ۲) ShotMap کارت باید بازی چمپیونزلیگ را با شوت‌ها و xG واقعی Opta برگرداند
        sm_items = hub.list_db_shotmap_matches(limit=5)
        assert len(sm_items) == 1
        assert sm_items[0]["competition"] == "لیگ قهرمانان اروپا"
        assert sm_items[0]["home"]["xg"] == 1.94
        assert sm_items[0]["away"]["xg"] == 0.95
        assert len(sm_items[0]["shots"]) == 2


def test_merged_european_bootstrap_powers_profile_fc27_and_h2h_players() -> None:
    fake_fpl = {
        "teams": [{"id": 1, "name": "Arsenal", "short_name": "ARS"}],
        "elements": [
            {
                "id": 10, "web_name": "Saka", "first_name": "Bukayo", "second_name": "Saka",
                "team": 1, "element_type": 3, "minutes": 900, "goals_scored": 6, "assists": 7,
                "expected_goals": "5.20", "expected_assists": "4.80",
                "expected_goals_per_90": 0.52, "expected_assists_per_90": 0.48,
                "ict_index": "120.0", "creativity": "400.0", "threat": "350.0", "influence": "300.0",
                "bps": 280, "total_points": 82, "now_cost": 102,
            }
        ],
    }
    fake_euro = {
        "teams": [
            {"id": 201, "name": "Real Madrid", "short_name": "RMA", "league_fa": "لالیگا اسپانیا"},
            {"id": 202, "name": "Bayern Munich", "short_name": "BAY", "league_fa": "بوندس‌لیگا آلمان"},
        ],
        "elements": [
            {
                "id": 200001, "web_name": "Mbappe", "first_name": "Kylian", "second_name": "Mbappe",
                "team": 201, "element_type": 4, "minutes": 900, "goals_scored": 11, "assists": 4,
                "expected_goals": "9.40", "expected_assists": "3.10",
                "expected_goals_per_90": 0.94, "expected_assists_per_90": 0.31,
                "ict_index": "165.0", "creativity": "290.0", "threat": "520.0", "influence": "410.0",
                "bps": 340, "total_points": 96, "now_cost": 120, "league_fa": "لالیگا اسپانیا", "source": "Understat",
            },
            {
                "id": 200002, "web_name": "Kane", "first_name": "Harry", "second_name": "Kane",
                "team": 202, "element_type": 4, "minutes": 900, "goals_scored": 13, "assists": 5,
                "expected_goals": "10.80", "expected_assists": "3.50",
                "expected_goals_per_90": 1.08, "expected_assists_per_90": 0.35,
                "ict_index": "180.0", "creativity": "310.0", "threat": "560.0", "influence": "450.0",
                "bps": 380, "total_points": 105, "now_cost": 125, "league_fa": "بوندس‌لیگا آلمان", "source": "Understat",
            },
        ],
    }

    with patch.object(hub, "fetch_understat_european_bootstrap", return_value=fake_euro):
        merged = hub.merge_fpl_and_european_bootstrap(fake_fpl)
    assert len(merged["elements"]) == 3
    assert len(merged["teams"]) == 3

    prof_items = ppf.parse_fpl_top_players(merged, limit=10)
    assert len(prof_items) == 3

    fc_items = pfc.parse_fpl_fc27_players(merged, limit=10)
    assert len(fc_items) == 3

    h2h_items = h2p.parse_fpl_h2h_duels(merged, limit=5)
    assert len(h2h_items) >= 1
