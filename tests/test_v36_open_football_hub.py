"""تست‌های واحد برای مرکز یکپارچه Open Football Hub (v0.36.0) و اسکریپت ممیزی زنده."""
from __future__ import annotations

from pathlib import Path

from src.xgpedia.providers.open_football_hub import (
    compute_openfootball_h2h,
    parse_openligadb_matchday,
    parse_openligadb_standings,
    parse_openligadb_top_scorers,
    parse_wc26_standings,
)


def test_v36_openligadb_standings_and_scorers():
    raw_tbl = [
        {
            "teamName": "FC Bayern München",
            "shortName": "Bayern",
            "teamIconUrl": "https://example.org/bayern.png",
            "matches": 11,
            "won": 9,
            "draw": 2,
            "lost": 0,
            "goals": 36,
            "opponentGoals": 8,
            "points": 29,
        },
        {
            "teamName": "Borussia Dortmund",
            "shortName": "BVB",
            "matches": 11,
            "won": 7,
            "draw": 2,
            "lost": 2,
            "goals": 24,
            "opponentGoals": 14,
            "points": 23,
        },
    ]
    tbl = parse_openligadb_standings(raw_tbl, season=2026)
    assert tbl is not None
    assert tbl["id"] == "live_bundesliga"
    assert tbl["source"] == "OpenLigaDB (Live)"
    assert tbl["teams"][0]["name"] == "بایرن مونیخ"
    assert tbl["teams"][0]["mp"] == 11
    assert tbl["teams"][0]["pts"] == 29
    assert tbl["teams"][0]["xpts"] is None  # null != 0

    raw_sc = [
        {"goalGetterName": "Harry Kane", "goalCount": 14},
        {"goalGetterName": "Omar Marmoush", "goalCount": 11},
        {"goalGetterName": "Zero Scorer", "goalCount": 0},
    ]
    sc = parse_openligadb_top_scorers(raw_sc, season=2026)
    assert sc is not None
    assert sc["competition"] == "بوندس‌لیگا آلمان"
    assert len(sc["players"]) == 2
    assert sc["players"][0]["goals"] == 14
    assert sc["players"][0]["xg"] is None  # null != 0


def test_v36_openligadb_matchday_ht_and_penalties():
    raw_md = [
        {
            "matchID": 77001,
            "matchIsFinished": True,
            "group": {"groupOrderID": 11},
            "team1": {"teamName": "FC Bayern München"},
            "team2": {"teamName": "Borussia Dortmund"},
            "matchResults": [
                {"resultTypeID": 1, "pointsTeam1": 1, "pointsTeam2": 0},
                {"resultTypeID": 2, "pointsTeam1": 2, "pointsTeam2": 1},
            ],
            "goals": [
                {"scoreTeam1": 1, "scoreTeam2": 0, "goalGetterName": "Harry Kane", "matchMinute": 23, "isPenalty": True, "isOwnGoal": False},
                {"scoreTeam1": 1, "scoreTeam2": 1, "goalGetterName": "Serhou Guirassy", "matchMinute": 58, "isPenalty": False, "isOwnGoal": False},
                {"scoreTeam1": 2, "scoreTeam2": 1, "goalGetterName": "Jamal Musiala", "matchMinute": 81, "isPenalty": False, "isOwnGoal": False},
            ],
        }
    ]
    ms = parse_openligadb_matchday(raw_md)
    assert len(ms) == 1
    m = ms[0]
    assert m["ht"] == "1-0"
    assert m["home"]["score"] == 2 and m["away"]["score"] == 1
    assert "(پ)" in m["home"]["scorers"]
    assert "23'" in m["home"]["scorers"]
    assert "58'" in m["away"]["scorers"]
    assert m["home"]["xg"] is None  # null != 0


def test_v36_wc26_standings_and_openfootball_h2h():
    wc_raw = {
        "children": [
            {
                "standings": {
                    "entries": [
                        {
                            "team": {"displayName": "Real Madrid"},
                            "stats": [
                                {"name": "gamesPlayed", "value": 13},
                                {"name": "wins", "value": 10},
                                {"name": "ties", "value": 2},
                                {"name": "losses", "value": 1},
                                {"name": "pointsFor", "value": 29},
                                {"name": "pointsAgainst", "value": 10},
                                {"name": "points", "value": 32},
                            ],
                        },
                        {
                            "team": {"displayName": "Barcelona"},
                            "stats": [
                                {"name": "gamesPlayed", "value": 13},
                                {"name": "wins", "value": 9},
                                {"name": "ties", "value": 2},
                                {"name": "losses", "value": 2},
                                {"name": "pointsFor", "value": 31},
                                {"name": "pointsAgainst", "value": 14},
                                {"name": "points", "value": 29},
                            ],
                        },
                    ]
                }
            }
        ]
    }
    tbl = parse_wc26_standings(wc_raw, league_slug="esp.1", season=2026)
    assert tbl is not None
    assert tbl["id"] == "live_laliga"
    assert tbl["source"] == "worldcup26.ir (Live)"
    assert tbl["teams"][0]["name"] == "رئال مادرید"
    assert tbl["teams"][0]["pts"] == 32
    assert tbl["teams"][1]["name"] == "بارسلونا"

    sample_matches = [
        {"date": "2024-10-26", "team1": "Real Madrid", "team2": "FC Barcelona", "score": {"ft": [0, 4]}},
        {"date": "2024-04-21", "team1": "Real Madrid", "team2": "FC Barcelona", "score": {"ft": [3, 2]}},
        {"date": "2023-10-28", "team1": "FC Barcelona", "team2": "Real Madrid", "score": {"ft": [1, 2]}},
    ]
    h2h = compute_openfootball_h2h(sample_matches, "Real Madrid", "Barcelona")
    assert h2h["total"] == 3
    assert h2h["t1_wins"] == 2
    assert h2h["t2_wins"] == 1
    assert h2h["draws"] == 0
    assert h2h["t1_goals"] == 5 and h2h["t2_goals"] == 7
    assert h2h["t2_cs"] == 1


def test_v36_wiring_zero_requests_and_audit_script():
    root = Path(__file__).resolve().parents[1]
    hub_src = (root / "src/xgpedia/providers/open_football_hub.py").read_text(encoding="utf-8")
    assert "import requests" not in hub_src
    assert "from requests" not in hub_src

    st_src = (root / "src/xgpedia/providers/standings_free.py").read_text(encoding="utf-8")
    assert "fetch_openligadb_bundesliga_standings" in st_src
    assert "fetch_wc26_standings" in st_src

    ts_src = (root / "src/xgpedia/providers/top_scorers_free.py").read_text(encoding="utf-8")
    assert "fetch_openligadb_bundesliga_top_scorers" in ts_src

    md_src = (root / "src/xgpedia/providers/matchday_results_free.py").read_text(encoding="utf-8")
    assert "fetch_openligadb_bundesliga_matchday" in md_src

    audit_src = (root / "scripts/audit_football_apis.py").read_text(encoding="utf-8")
    assert "worldcup26.ir" in audit_src
    assert "api.openligadb.de" in audit_src
    assert "openfootball/football.json" in audit_src
    assert "import requests" not in audit_src
