"""آزمون‌های منابع دادهٔ رایگان v0.14.0:
  1) ضرایب واقعی بازار (+EV) از fixtures.csv رایگان football-data.co.uk
  2) مهره‌های کلیدی، PPDA و نقشه شوت / xG Race از Understat
  3) رادار ۶ محوره تاکتیکی با محاسبهٔ صدک واقعی بین تیم‌های لیگ در DB
"""
from __future__ import annotations

import json
from pathlib import Path

from src.xgpedia import db as db_mod
from src.xgpedia.providers.football_data_couk import FootballDataCoUk
from src.xgpedia.providers.understat import (
    _decode_embedded_json,
    parse_league_key_players,
    parse_league_team_ppda,
    parse_match_shots,
)
from src.xgpedia.render.cards import build_preview_context
from src.xgpedia.sync import (
    build_match_facts,
    sync_understat_league,
    sync_upcoming_odds,
)


def _setup_db(tmp_path: Path, monkeypatch) -> None:
    db_file = tmp_path / "enrich.sqlite"
    monkeypatch.setattr(db_mod, "DATABASE_PATH", db_file)
    db_mod.init_db()


def test_parse_upcoming_odds_from_fixtures_csv():
    csv_text = (
        "Div,Date,Time,HomeTeam,AwayTeam,B365H,B365D,B365A,AvgH,AvgD,AvgA,Avg>2.5\n"
        "E0,22/11/2026,16:30,Liverpool,Man United,1.85,3.70,4.10,1.88,3.75,4.05,1.72\n"
        "E0,22/11/2026,14:00,Hull,Brighton,3.60,3.40,2.05,3.55,3.42,2.08,1.90\n"
        "D1,22/11/2026,14:30,Bayern Munich,Dortmund,1.50,4.50,5.50,1.52,4.40,5.40,1.45\n"
    )
    api = FootballDataCoUk()
    try:
        rows = api.parse_upcoming_odds(csv_text)
    finally:
        api.close()
    assert len(rows) == 2  # فقط لیگ برتر انگلیس E0
    assert rows[0]["home_team"] == "Liverpool"
    assert rows[0]["away_team"] == "Manchester United"
    assert rows[0]["home_odds"] == 1.88
    assert rows[0]["over25_odds"] == 1.72
    assert rows[1]["home_team"] == "Hull"
    assert rows[1]["away_team"] == "Brighton"


def test_understat_parsers_key_players_ppda_and_shots():
    sample_players = [
        {"player_name": "Mohamed Salah", "team_title": "Liverpool", "position": "F M", "time": "900", "xG": "6.5", "xA": "4.2", "key_passes": "28"},
        {"player_name": "Darwin Nunez", "team_title": "Liverpool", "position": "F", "time": "450", "xG": "2.1", "xA": "0.5", "key_passes": "6"},
        {"player_name": "Bruno Fernandes", "team_title": "Manchester United", "position": "M", "time": "900", "xG": "4.0", "xA": "5.1", "key_passes": "34"},
    ]
    kps = parse_league_key_players(sample_players)
    assert kps["Liverpool"]["name"] == "Mohamed Salah"
    assert kps["Liverpool"]["pos"] == "مهاجم"
    assert "xG+xA" in kps["Liverpool"]["s1"]
    assert "پاس کلیدی" in kps["Liverpool"]["s2"]
    assert kps["Manchester United"]["name"] == "Bruno Fernandes"

    sample_teams = {
        "87": {"title": "Liverpool", "history": [{"ppda": {"att": 160, "def": 20}, "deep": 11}]},
        "89": {"title": "Manchester United", "history": [{"ppda": {"att": 220, "def": 20}, "deep": 7}]},
    }
    tm = parse_league_team_ppda(sample_teams)
    assert tm["Liverpool"]["ppda"] == 8.0
    assert tm["Liverpool"]["deep"] == 11.0
    assert tm["Manchester United"]["ppda"] == 11.0

    shots = parse_match_shots({
        "h": [{"X": "0.88", "Y": "0.51", "xG": "0.42", "result": "Goal", "player": "Salah", "minute": "23"}],
        "a": [{"X": "0.75", "Y": "0.40", "xG": "0.09", "result": "SavedShot", "player": "Bruno", "minute": "61"}],
    })
    assert shots["home_inside_box"] == 1
    assert shots["home_shots"][0] == [88.0, 51.0, 0.42, "goal", "Salah", 23]
    assert shots["away_shots"][0][3] == "sot"

    # تست decode json جاسازی‌شده
    raw = json.dumps([{"a": 1}]).encode("unicode_escape").decode("ascii")
    html = f"<script>var playersData = JSON.parse('{raw}');</script>"
    assert _decode_embedded_json(html, "playersData") == [{"a": 1}]


def test_full_free_enrichment_unlocks_radar_keyduel_and_signals(tmp_path, monkeypatch):
    """با ۶+ تیم در DB + Understat + ضرایب fixtures.csv، اولویت‌های ۱ و ۲ و ۳ کارت پیش‌ازبازی خودکار روشن می‌شوند."""
    _setup_db(tmp_path, monkeypatch)
    teams = ["Liverpool", "Manchester United", "Arsenal", "Chelsea", "Brighton", "Hull"]
    with db_mod.db() as conn:
        for i in range(0, len(teams), 2):
            h, a = teams[i], teams[i + 1]
            fid = f"fdcouk:2026-11-0{i + 1}:{h}:{a}"
            conn.execute(
                "INSERT INTO fixtures (fixture_id, provider, competition, season, kickoff_utc, home_team, away_team, status, raw_payload_hash, collected_at) VALUES (?, 'football-data-co-uk', 'Premier League', '2026-27', ?, ?, ?, 'finished', NULL, '2026-11-20T00:00:00Z')",
                (fid, f"2026-11-0{i + 1}", h, a),
            )
            for t, xg, sh, sot, cor, g in [
                (h, 1.8 - i * 0.1, 15 - i, 6 - i * 0.5, 7 - i * 0.5, 2),
                (a, 1.1 + i * 0.1, 10 + i, 4 + i * 0.3, 4 + i * 0.5, 1),
            ]:
                for met, val in [
                    ("expected_goals", xg), ("total_shots", sh),
                    ("shots_on_target", sot), ("corner_kicks", cor), ("goals", g),
                ]:
                    conn.execute(
                        "INSERT INTO fixture_statistics VALUES (?,?,?,?,NULL,'football-data-co-uk','2026-11-20T00:00:00Z')",
                        (fid, t, met, val),
                    )
        # بازی پیش‌رو امروز با نام خام football-data.org
        conn.execute(
            "INSERT INTO fixtures (fixture_id, provider, competition, season, kickoff_utc, home_team, away_team, status, raw_payload_hash, collected_at) VALUES ('fdo:999', 'football-data-org', 'Premier League', '2026-27', '2026-11-22T16:30:00Z', 'Liverpool FC', 'Manchester United FC', 'scheduled', NULL, '2026-11-22T07:00:00Z')"
        )

    sync_upcoming_odds([{
        "home_team": "Liverpool", "away_team": "Manchester United", "match_date": "2026-11-22",
        "home_odds": 1.95, "draw_odds": 3.60, "away_odds": 3.80, "over25_odds": 1.85,
    }])
    sync_understat_league({
        "key_players": {
            "Liverpool": {"name": "محمد صلاح", "pos": "مهاجم", "s1": "1.05 xG+xA", "s2": "3.1 پاس کلیدی"},
            "Manchester United": {"name": "برونو فرناندز", "pos": "هافبک", "s1": "0.88 xG+xA", "s2": "3.6 پاس کلیدی"},
        },
        "team_metrics": {
            "Liverpool": {"ppda": 8.1, "deep": 10.5},
            "Manchester United": {"ppda": 11.4, "deep": 7.2},
        },
    })

    facts = build_match_facts("fdo:999", post_match=False)
    assert len(facts["home"]["radar"]) == 6
    assert len(facts["away"]["radar"]) == 6
    assert facts["home"]["kp"]["name"] == "محمد صلاح"
    assert facts["away"]["kp"]["name"] == "برونو فرناندز"
    assert facts["market_odds"]["home"] == 1.95

    draft = {"title": "نبرد بزرگ آنفیلد", "bullets": ["نکته"], "caption": "پیش‌بازی لیورپول و منچستریونایتد."}
    ctx45 = build_preview_context(draft, facts, fmt="4:5")
    assert ctx45["has"]["radar"] and ctx45["has"]["keyduel"] and ctx45["has"]["signals"]
    assert [m["id"] for m in ctx45["modules"]] == ["radar", "signals"]
    ctx916 = build_preview_context(draft, facts, fmt="9:16")
    assert [m["id"] for m in ctx916["modules"]] == ["radar", "signals"]
