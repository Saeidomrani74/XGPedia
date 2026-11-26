"""تست‌های نسخهٔ 0.61.0: رفع ریشه‌ای تطبیق اینتر در FotMob، فعال‌سازی هر ۷ ماژول (از جمله efficiency/GK) و حذف کندی لیست بازی‌ها."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.xgpedia import db as db_mod
from src.xgpedia import today_workflow as tw
from src.xgpedia.core import api_health
from src.xgpedia.providers import espn_free as ef
from src.xgpedia.providers import xg_engine as xge
from src.xgpedia.render.card_kit.modules.post_modules import render_efficiency
from src.xgpedia.render.post_match_cards import build_post_match_context
from src.xgpedia.sync import build_match_facts, merge_post_match_details


def test_inter_milan_fotmob_slug_and_next_data_matching() -> None:
    pair = xge._extract_fotmob_slug_teams("/matches/inter-vs-vfb-stuttgart/2e4xyz#4900123")
    assert pair == ("inter", "vfb stuttgart")

    pu, sw = xge._match_fotmob_entries(
        [("inter", "vfb stuttgart", "/matches/inter-vs-vfb-stuttgart/2e4xyz#4900123")],
        "Internazionale",
        "VfB Stuttgart",
    )
    assert pu == "/matches/inter-vs-vfb-stuttgart/2e4xyz#4900123"
    assert sw is False

    pu2, sw2 = xge._match_fotmob_entries(
        [("vfb stuttgart", "inter", "/matches/vfb-stuttgart-vs-inter/2e4xyz#4900123")],
        "Inter Milan",
        "VfB Stuttgart",
    )
    assert pu2 == "/matches/vfb-stuttgart-vs-inter/2e4xyz#4900123"
    assert sw2 is True

    # استخراج از __NEXT_DATA__ صفحهٔ اصلی FotMob
    html_home = (
        '<html><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps({
            "props": {
                "pageProps": {
                    "leagues": [
                        {
                            "name": "Champions League",
                            "matches": [
                                {
                                    "home": {"name": "Inter"},
                                    "away": {"name": "VfB Stuttgart"},
                                    "pageUrl": "/matches/inter-vs-vfb-stuttgart/2e4xyz#4900123",
                                }
                            ],
                        }
                    ]
                }
            }
        })
        + "</script></html>"
    )
    entries = xge._extract_fotmob_matches_from_next_data(html_home)
    assert len(entries) == 1
    pu3, sw3 = xge._match_fotmob_entries(entries, "Internazionale", "VfB Stuttgart")
    assert pu3 == "/matches/inter-vs-vfb-stuttgart/2e4xyz#4900123"
    assert sw3 is False


def test_fotmob_real_schema_all_7_modules_and_efficiency(tmp_path: Path | None = None) -> None:
    """ساختار واقعی FotMob: usualPosition=0/positionId=11 برای دروازه‌بان، name به‌صورت dict، scoreStr و lineup.lineup."""
    payload = {
        "general": {
            "homeTeam": {"id": 8636, "name": "Inter"},
            "awayTeam": {"id": 10269, "name": "VfB Stuttgart"},
        },
        "header": {
            "teams": [{"id": 8636}, {"id": 10269}],
            "status": {"scoreStr": "2 - 1"},
        },
        "content": {
            "stats": {
                "Periods": {
                    "All": {
                        "stats": [
                            {
                                "title": "Top stats",
                                "stats": [
                                    {"key": "expected_goals", "title": "Expected goals (xG)", "stats": ["1.82", "1.14"]},
                                    {"key": "big_chance", "title": "Big chances", "stats": [3, 2]},
                                    {"key": "shots_inside_box", "title": "Shots inside box", "stats": [9, 6]},
                                    {"key": "ballPoss", "title": "Ball possession", "stats": [52, 48]},
                                    {"key": "total_shots", "title": "Total shots", "stats": [14, 10]},
                                    {"key": "shotsOnTarget", "title": "Shots on target", "stats": [6, 4]},
                                    {"key": "corners", "title": "Corners", "stats": [5, 4]},
                                    {"key": "keeper_saves", "title": "Keeper saves", "stats": [3, 4]},
                                ],
                            }
                        ]
                    }
                }
            },
            "shotmap": {
                "shots": [
                    {"teamId": 8636, "x": 94.0, "y": 33.0, "expectedGoals": 0.45, "eventType": "Goal", "playerName": "Lautaro Martínez", "min": 18},
                    {"teamId": 8636, "x": 90.0, "y": 36.0, "expectedGoals": 0.37, "eventType": "Goal", "playerName": "Marcus Thuram", "min": 67},
                    {"teamId": 10269, "x": 91.0, "y": 35.0, "expectedGoals": 0.41, "eventType": "Goal", "playerName": "Deniz Undav", "min": 52},
                    {"teamId": 10269, "x": 86.0, "y": 30.0, "expectedGoals": 0.19, "eventType": "AttemptSaved", "playerName": "Enzo Millot", "min": 79},
                ]
            },
            "momentum": {
                "main": {"data": [{"minute": m, "value": (18 if m % 3 else -14)} for m in range(1, 91)]}
            },
            "lineup": {
                "lineup": [
                    {
                        "players": [
                            [{"id": "101", "name": {"fullName": "Yann Sommer"}, "shirtNumber": 1, "positionId": 11, "usualPosition": 0, "performance": {"rating": 7.6}}],
                            [{"id": "102", "name": {"fullName": "Lautaro Martínez"}, "shirtNumber": 10, "positionId": 105, "usualPosition": 3, "performance": {"rating": 8.4}}],
                        ],
                    },
                    {
                        "players": [
                            [{"id": "201", "name": {"fullName": "Alexander Nübel"}, "shirtNumber": 33, "positionId": 11, "usualPosition": 0, "performance": {"rating": 7.4}}],
                            [{"id": "202", "name": {"fullName": "Deniz Undav"}, "shirtNumber": 26, "positionId": 105, "usualPosition": 3, "performance": {"rating": 7.8}}],
                        ],
                    },
                ]
            },
            "playerStats": {
                # فرض کنید saves در playerStats دروازه‌بان میزبان نیامده ولی keeper_saves تیم واقعی موجود است
                "101": {"stats": [{"title": "Top stats", "stats": {"Expected goals on target (xGOT) faced": {"key": "expected_goals_on_target_faced", "stat": {"value": 1.35}}}}]},
                "102": {"stats": [{"title": "Top stats", "stats": {"Goals": {"key": "goals", "stat": {"value": 1}}}}]},
                "201": {"stats": [{"title": "Top stats", "stats": {"Saves": {"key": "saves", "stat": {"value": 4}}, "Expected goals on target (xGOT) faced": {"key": "expected_goals_on_target_faced", "stat": {"value": 2.05}}}}]},
                "202": {"stats": [{"title": "Top stats", "stats": {"Goals": {"key": "goals", "stat": {"value": 1}}}}]},
            },
        },
    }

    parsed = xge.parse_fotmob_match_details(payload)
    assert parsed["home_xg"] == 1.82
    assert parsed["away_xg"] == 1.14
    assert parsed["home_gk"]["saves"] == 3
    assert parsed["home_gk"]["psxg"] == 1.35
    assert parsed["home_gk"]["ga"] == 1
    assert parsed["away_gk"]["saves"] == 4
    assert parsed["away_gk"]["psxg"] == 2.05
    assert parsed["away_gk"]["ga"] == 2
    assert len(parsed["top_players"]) == 4
    assert parsed["motm"]["rating"] == 8.4

    base_dir = tmp_path or Path(tempfile.mkdtemp(prefix="xgp_v61_"))
    test_db = base_dir / "v61_inter.db"
    ko = "2026-11-25T20:00:00Z"
    with patch.object(db_mod, "DATABASE_PATH", test_db):
        db_mod.init_db()
        with db_mod.db() as conn:
            conn.execute(
                "INSERT INTO fixtures (fixture_id, provider, competition, season, kickoff_utc, home_team, away_team, status, collected_at) VALUES ('espn:401915380', 'espn-public', 'UEFA Champions League', '2026-27', ?, 'Inter Milan', 'VfB Stuttgart', 'finished', ?)",
                (ko, ko),
            )
            conn.execute("INSERT INTO fixture_statistics (fixture_id, team, metric, value, provider, collected_at) VALUES ('espn:401915380', 'Inter Milan', 'goals', 2, 'espn-public', ?)", (ko,))
            conn.execute("INSERT INTO fixture_statistics (fixture_id, team, metric, value, provider, collected_at) VALUES ('espn:401915380', 'VfB Stuttgart', 'goals', 1, 'espn-public', ?)", (ko,))

        merge_post_match_details(
            "espn:401915380",
            {
                "xg_provider": "fotmob",
                "xg_enriched": True,
                "xg_enriched_v": 2,
                **{k: parsed[k] for k in ("home_shots", "away_shots", "home_inside_box", "away_inside_box", "momentum", "top_players", "motm", "home_gk", "away_gk")},
            },
            provider="fotmob",
            extra_stats={
                "Inter Milan": {
                    "expected_goals": parsed["home_xg"],
                    "big_chances": float(parsed["home_big_chances"]),
                    "possession": parsed["home_possession"],
                    "total_shots": parsed["home_total_shots"],
                    "shots_on_target": parsed["home_shots_on_target"],
                    "corner_kicks": parsed["home_corners"],
                },
                "VfB Stuttgart": {
                    "expected_goals": parsed["away_xg"],
                    "big_chances": float(parsed["away_big_chances"]),
                    "possession": parsed["away_possession"],
                    "total_shots": parsed["away_total_shots"],
                    "shots_on_target": parsed["away_shots_on_target"],
                    "corner_kicks": parsed["away_corners"],
                },
            },
        )
        facts = build_match_facts("espn:401915380", post_match=True)
        ctx = build_post_match_context({"title": "", "bullets": [], "caption": ""}, facts, fmt="4:5")
        for mod in ("xgrace", "shotmap", "momentum", "efficiency", "toprated", "motm", "stats"):
            assert ctx["has"][mod] is True, f"Module {mod} was NOT enabled!"
        eff_html = render_efficiency(ctx["studio_payload"])
        assert "دقت شوت" in eff_html and "دروازه‌بان" in eff_html


def test_null_not_zero_when_gk_saves_truly_missing() -> None:
    payload = {
        "general": {"homeTeam": {"id": 1}, "awayTeam": {"id": 2}},
        "header": {"teams": [{"id": 1, "score": 1}, {"id": 2, "score": 0}]},
        "content": {
            "stats": {"Periods": {"All": {"stats": [{"stats": [{"key": "expected_goals", "stats": ["1.10", "0.50"]}]}]}}},
            "lineup": {
                "homeTeam": {"starters": [{"id": "10", "name": "Keeper A", "usualPosition": 0}]},
                "awayTeam": {"starters": [{"id": "20", "name": "Keeper B", "usualPosition": 0}]},
            },
            "playerStats": {},
        },
    }
    parsed = xge.parse_fotmob_match_details(payload)
    assert "home_gk" not in parsed
    assert "away_gk" not in parsed


def test_espn_gk_saves_from_roster_stats_fallback() -> None:
    summary = {
        "header": {
            "id": "999",
            "competitions": [
                {
                    "date": "2026-11-25T20:00:00Z",
                    "competitors": [
                        {"homeAway": "home", "score": "2", "team": {"id": "1", "displayName": "Inter Milan"}},
                        {"homeAway": "away", "score": "1", "team": {"id": "2", "displayName": "VfB Stuttgart"}},
                    ],
                }
            ],
        },
        "boxscore": {"teams": []},
        "rosters": [
            {
                "team": {"id": "1"},
                "roster": [
                    {
                        "starter": True,
                        "position": {"abbreviation": "G"},
                        "athlete": {"shortName": "Y. Sommer"},
                        "stats": [{"name": "saves", "value": 4}],
                    }
                ],
            },
            {
                "team": {"id": "2"},
                "roster": [
                    {
                        "starter": True,
                        "position": {"abbreviation": "GK"},
                        "athlete": {"shortName": "A. Nübel"},
                        "stats": [{"name": "saves", "value": 3}],
                    }
                ],
            },
        ],
    }
    res = ef.parse_espn_finished_summary(summary, competition_name="UEFA Champions League", league_slug="uefa.champions")
    assert res is not None
    assert res["details"]["home_gk"]["saves"] == 4
    assert res["details"]["away_gk"]["saves"] == 3


def test_sofascore_403_circuit_breaker_stops_after_first_call() -> None:
    api_health.configure_health_store(persist=False, clear=True)
    calls: list[str] = []

    def _fake_get(url: str, **kwargs):
        calls.append(url)
        return 403, "Forbidden"

    with patch.object(xge, "_http_get_text", side_effect=_fake_get):
        r1 = xge.fetch_sofascore_match_xg("Inter Milan", "VfB Stuttgart", "2026-11-25")
        r2 = xge.fetch_sofascore_match_xg("Lille", "Bayern Munich", "2026-11-25")
    assert r1 is None and r2 is None
    assert len(calls) == 1, f"Expected 1 HTTP call before circuit breaker tripped, got {len(calls)}"
    assert api_health.is_cooling("xg:sofascore") is True


def test_sync_recent_finished_skips_slow_enrichment_by_default(tmp_path: Path | None = None) -> None:
    base_dir = tmp_path or Path(tempfile.mkdtemp(prefix="xgp_v61_sync_"))
    test_db = base_dir / "v61_sync.db"
    enrich_calls: list[str] = []
    with (
        patch.object(db_mod, "DATABASE_PATH", test_db),
        patch.object(tw, "enrich_post_match_fixture", side_effect=lambda fid, **kw: enrich_calls.append(fid) or {"fpl": False, "understat": False}),
        patch.object(tw, "list_recent_finished_fixtures", return_value=[]),
    ):
        # نباید به هیچ منبع Playwright یا enrich_post_match_fixture بخورد
        with (
            patch("src.xgpedia.providers.football_data_org.FootballDataOrg", side_effect=RuntimeError("skip")),
            patch("src.xgpedia.providers.espn_free.ESPNFreeProvider", side_effect=RuntimeError("skip")),
        ):
            res = tw.sync_recent_finished_matches()
    assert res["enriched"] == 0
    assert enrich_calls == []
