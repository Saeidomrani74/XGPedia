"""تست‌های نسخهٔ 0.19.0 — فعال‌سازی همهٔ ۷ ماژول پیش‌بازی از منابع رایگان + لوگوی واقعی + فاصلهٔ فوتر."""
from __future__ import annotations

from pathlib import Path

from src.xgpedia import db as db_mod
from src.xgpedia.providers.base import RawResponse
from src.xgpedia.providers.espn_free import (
    american_to_decimal_odds,
    parse_espn_timing_wave,
    parse_espn_upcoming,
)
from src.xgpedia.render.cards import render_preview_html
from src.xgpedia.sync import _team_enrichment_from_db, sync_espn_enrichments, sync_fdo_scorers


def test_espn_free_parses_odds_keyplayers_and_timing_wave():
    assert american_to_decimal_odds("+150") == 2.50
    assert american_to_decimal_odds("-120") == 1.83

    sample_upcoming = {
        "events": [{
            "date": "2026-11-22T16:30:00Z",
            "competitions": [{
                "date": "2026-11-22T16:30:00Z",
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": {"id": "364", "displayName": "Liverpool"},
                        "leaders": [{
                            "name": "goals",
                            "leaders": [{"displayValue": "9", "athlete": {"displayName": "Mohamed Salah", "position": {"abbreviation": "F"}}}],
                        }],
                    },
                    {
                        "homeAway": "away",
                        "team": {"id": "360", "displayName": "Manchester United"},
                        "leaders": [{
                            "name": "goals",
                            "leaders": [{"displayValue": "7", "athlete": {"displayName": "Bruno Fernandes", "position": {"abbreviation": "M"}}}],
                        }],
                    },
                ],
                "odds": [{
                    "homeTeamOdds": {"moneyLine": -110},
                    "awayTeamOdds": {"moneyLine": +260},
                    "drawOdds": {"moneyLine": +250},
                    "overUnder": 2.5,
                    "overOdds": -125,
                }],
            }],
        }]
    }
    parsed = parse_espn_upcoming(sample_upcoming)
    assert len(parsed["odds_rows"]) == 1
    assert parsed["odds_rows"][0]["home_team"] == "Liverpool"
    assert parsed["odds_rows"][0]["home_odds"] == 1.91
    assert parsed["key_players"]["Liverpool"]["name"] == "Mohamed Salah"
    assert parsed["key_players"]["Manchester United"]["name"] == "Bruno Fernandes"

    sample_hist = {
        "events": [
            {
                "competitions": [{
                    "status": {"type": {"state": "post"}},
                    "competitors": [{"team": {"id": "364", "displayName": "Liverpool"}}, {"team": {"id": "360", "displayName": "Manchester United"}}],
                    "details": [
                        {"scoringPlay": True, "team": {"id": "364"}, "clock": {"value": 600}},
                        {"scoringPlay": True, "team": {"id": "364"}, "clock": {"value": 4800}},
                        {"scoringPlay": True, "team": {"id": "360"}, "clock": {"value": 2400}},
                    ],
                }]
            },
            {
                "competitions": [{
                    "status": {"type": {"state": "post"}},
                    "competitors": [{"team": {"id": "364", "displayName": "Liverpool"}}, {"team": {"id": "360", "displayName": "Manchester United"}}],
                    "details": [
                        {"scoringPlay": True, "team": {"id": "364"}, "clock": {"value": 3000}},
                        {"scoringPlay": True, "team": {"id": "360"}, "clock": {"value": 5100}},
                    ],
                }]
            },
        ]
    }
    waves = parse_espn_timing_wave(sample_hist)
    assert "Liverpool" in waves and len(waves["Liverpool"]) == 6
    assert "Manchester United" in waves and len(waves["Manchester United"]) == 6


def test_sync_fdo_scorers_and_espn_enrichments_populate_kp_and_wave(tmp_path: Path, monkeypatch):
    db_file = tmp_path / "enr19.db"
    monkeypatch.setattr(db_mod, "DATABASE_PATH", db_file)
    db_mod.init_db()

    raw_sc = RawResponse.build(
        "football-data-org",
        "/competitions/PL/scorers",
        {"scorers": [{"team": {"id": 64, "name": "Liverpool FC"}, "player": {"name": "Mohamed Salah"}, "goals": 10, "assists": 6}]},
        200,
    )
    assert sync_fdo_scorers(raw_sc, season_start=2026)["key_players"] == 1

    es = sync_espn_enrichments({
        "odds_rows": [],
        "key_players": {"Manchester United": {"name": "Bruno Fernandes", "pos": "هافبک", "s1": "6 گل", "s2": "5 پاس گل"}},
        "wave_map": {"Liverpool": [0.22, 0.31, 0.40, 0.28, 0.35, 0.44]},
    }, season_start=2026)
    assert es["waves"] == 1

    with db_mod.db() as conn:
        enr = _team_enrichment_from_db(conn, "Liverpool", "2026-27")
    assert enr["kp"]["name"] == "Mohamed Salah"
    assert len(enr["wave"]) == 6


def test_card_uses_real_brand_logo_and_footer_bottom_margin():
    facts = {
        "fixture_id": "fdo:1",
        "competition": {"name": "Premier League", "season": "2026-27"},
        "kickoff_utc": "2026-11-22T16:30:00Z",
        "source": {"provider": "football-data-org", "collected_at": "2026-11-22T09:00:00Z"},
        "home": {"name_fa": "لیورپول", "name_en": "Liverpool", "xg_for_avg": {"value": 1.6, "n": 10}, "xg_against_avg": {"value": 0.9, "n": 10}},
        "away": {"name_fa": "منچستریونایتد", "name_en": "Manchester United", "xg_for_avg": {"value": 1.5, "n": 10}, "xg_against_avg": {"value": 1.1, "n": 10}},
    }
    html = render_preview_html({"title": "تست", "bullets": [], "caption": ""}, facts, fmt="4:5")
    assert 'class="bl-img"' in html
    assert "data:image/svg+xml;base64," in html
    assert "padding:20px 0 20px" in html
