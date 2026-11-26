"""تست‌های نسخهٔ 0.64.0: منابع واقعی لیگ اروپا (۱۱ لیگ CSV + تاریخچه فصل ESPN + fallback چندمنبعی + نگاشت دقیق تیم‌ها)."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from src.xgpedia import db as db_mod
from src.xgpedia import today_workflow as tw
from src.xgpedia.config import canonical_team_name, team_name_fa
from src.xgpedia.providers.espn_free import parse_espn_scoreboard_finished
from src.xgpedia.providers.football_data_couk import ALL_EUROPEAN_CSV_LEAGUES, FootballDataCoUk
from src.xgpedia.sync import build_match_facts, sync_espn_finished_matches


def test_europa_league_espn_and_csv_team_aliases() -> None:
    expected = {
        "Celta": ("Celta Vigo", "سلتاویگو"),
        "Sociedad": ("Real Sociedad", "رئال سوسیداد"),
        "Union St.-Gilloise": ("Union Saint-Gilloise", "یونیون سنت ژیلواز"),
        "St. Gilloise": ("Union Saint-Gilloise", "یونیون سنت ژیلواز"),
        "Stade Rennais": ("Rennes", "رن"),
        "RB Salzburg": ("Red Bull Salzburg", "ردبول سالزبورگ"),
        "FC Salzburg": ("Red Bull Salzburg", "ردبول سالزبورگ"),
        "Hapoel Be'er": ("Hapoel Be'er Sheva", "هاپوئل بئرشبع"),
        "Nijmegen": ("NEC Nijmegen", "ان.ای.سی نایمخن"),
        "Alkmaar": ("AZ Alkmaar", "آلکمار"),
        "Leverkusen": ("Bayer Leverkusen", "بایر لورکوزن"),
        "Milan": ("AC Milan", "آث میلان"),
    }
    for raw, (exp_canon, exp_fa) in expected.items():
        c = canonical_team_name(raw)
        assert c == exp_canon, f"{raw!r} -> {c!r} (expected {exp_canon!r})"
        assert team_name_fa(c) == exp_fa


def test_all_11_european_csv_leagues_and_canonical_parsing() -> None:
    codes = {c for c, _ in ALL_EUROPEAN_CSV_LEAGUES}
    assert codes == {"E0", "SP1", "I1", "D1", "F1", "P1", "N1", "B1", "T1", "G1", "SC0"}

    sample_csv = (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,HS,AS,HST,AST,HC,AC,HF,AF,HY,AY,HR,AR\n"
        "SP1,08/11/2026,Celta,Sociedad,2,1,13,10,5,4,6,3,11,12,2,1,0,0\n"
    )
    fdc = FootballDataCoUk()
    try:
        rows = fdc.parse_season(sample_csv)
    finally:
        fdc.close()
    assert len(rows) == 1
    assert rows[0].home_team == "Celta Vigo"
    assert rows[0].away_team == "Real Sociedad"


def test_espn_uel_season_history_enables_non_top5_europa_league_preview(tmp_path: Path | None = None) -> None:
    scoreboard_payload = {
        "events": [
            {
                "id": "700001",
                "date": "2026-10-22T19:00Z",
                "competitions": [
                    {
                        "date": "2026-10-22T19:00Z",
                        "status": {"type": {"completed": True, "state": "post"}},
                        "competitors": [
                            {
                                "homeAway": "home",
                                "score": "2",
                                "team": {"displayName": "Ferencváros"},
                                "statistics": [
                                    {"name": "shotsOnTarget", "displayValue": "6"},
                                    {"name": "wonCorners", "displayValue": "7"},
                                ],
                            },
                            {
                                "homeAway": "away",
                                "score": "1",
                                "team": {"displayName": "Viktoria Plzeň"},
                                "statistics": [
                                    {"name": "shotsOnTarget", "displayValue": "3"},
                                    {"name": "wonCorners", "displayValue": "4"},
                                ],
                            },
                        ],
                    }
                ],
            },
            {
                "id": "700002",
                "date": "2026-11-05T19:00Z",
                "competitions": [
                    {
                        "date": "2026-11-05T19:00Z",
                        "status": {"type": {"completed": True, "state": "post"}},
                        "competitors": [
                            {
                                "homeAway": "home",
                                "score": "2",
                                "team": {"displayName": "Sturm Graz"},
                                "statistics": [
                                    {"name": "shotsOnTarget", "displayValue": "4"},
                                    {"name": "wonCorners", "displayValue": "5"},
                                ],
                            },
                            {
                                "homeAway": "away",
                                "score": "3",
                                "team": {"displayName": "Celje"},
                                "statistics": [
                                    {"name": "shotsOnTarget", "displayValue": "5"},
                                    {"name": "wonCorners", "displayValue": "6"},
                                ],
                            },
                        ],
                    }
                ],
            },
        ]
    }
    parsed = parse_espn_scoreboard_finished(scoreboard_payload, competition_name="UEFA Europa League", league_slug="uefa.europa")
    assert len(parsed) == 2

    base_dir = tmp_path or Path(tempfile.mkdtemp(prefix="xgp_v64_"))
    test_db = base_dir / "v64_uel.db"
    with patch.object(db_mod, "DATABASE_PATH", test_db):
        db_mod.init_db()
        sync_espn_finished_matches(parsed, season_start=2026)
        with db_mod.db() as conn:
            conn.execute(
                "INSERT INTO fixtures (fixture_id, provider, competition, season, kickoff_utc, home_team, away_team, status, collected_at) "
                "VALUES ('espn:700099', 'espn-public', 'UEFA Europa League', '2026-27', '2026-11-26T20:00:00Z', 'Ferencvaros', 'NK Celje', 'scheduled', '2026-11-26T10:00:00Z')"
            )
        facts = build_match_facts("espn:700099", post_match=False)
        assert facts["home"]["last5"] is not None
        assert facts["away"]["last5"] is not None
        assert facts["home"]["sot_avg"]["value"] == 6.0
        assert facts["away"]["sot_avg"]["value"] == 5.0
        assert facts["home"]["corners_avg"]["value"] == 7.0
        assert facts["away"]["corners_avg"]["value"] == 6.0
        # قانون null ≠ 0: چون xG واقعی در scoreboard نیست باید None بماند
        assert facts["home"]["xg_for_avg"] is None
        assert facts["away"]["xg_for_avg"] is None

        ok, reason = tw._check_match_eligibility("espn:700099")
        assert ok is True, f"Expected eligible Europa League match, got: {reason}"
