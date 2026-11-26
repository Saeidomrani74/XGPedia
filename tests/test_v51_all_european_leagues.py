"""تست‌های پوشش کامل ۶ لیگ معتبر اروپا (نسخهٔ 0.51.0)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from src.xgpedia.core.leagues import (
    DOMESTIC_LEAGUES,
    EUROPEAN_ESPN_SLUGS,
    EUROPEAN_FDO_CODES,
    EUROPEAN_LEAGUES,
    canonical_competition_name,
    competition_badge_fa,
    competition_name_fa,
    league_by_code,
    league_by_espn_slug,
    league_by_name,
)
from src.xgpedia.providers import (
    breaking_news_free as bnf,
    debate_free as df,
    espn_free as ef,
    football_data_couk as couk,
    football_data_org as fdo,
)
from src.xgpedia.render import cards as rcards


def test_central_six_leagues_registry() -> None:
    assert len(EUROPEAN_LEAGUES) == 7
    assert set(EUROPEAN_FDO_CODES) == {"PL", "CL", "EL", "PD", "SA", "BL1", "FL1"}
    assert set(EUROPEAN_ESPN_SLUGS) == {"eng.1", "uefa.champions", "uefa.europa", "esp.1", "ita.1", "ger.1", "fra.1"}
    assert len(DOMESTIC_LEAGUES) == 5
    assert league_by_code("CL").name_en == "UEFA Champions League"
    assert league_by_espn_slug("esp.1").name_fa == "لالیگا اسپانیا"
    assert league_by_name("Primera Division").code == "PD"
    assert canonical_competition_name("Primera Division") == "La Liga"
    assert competition_name_fa("UEFA Champions League") == "لیگ قهرمانان اروپا"
    assert "چمپیونزلیگ" in competition_badge_fa("UEFA Champions League")
    assert "بوندس‌لیگا" in competition_badge_fa("Bundesliga")


def test_espn_urls_and_multileague_finished_matches() -> None:
    assert "uefa.champions" in ef.espn_scoreboard_url("uefa.champions")
    assert "esp.1" in ef.espn_summary_url("esp.1")

    now = datetime(2026, 11, 26, 10, 0, tzinfo=timezone.utc)
    ko_recent = (now - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

    fake_sb = {
        "events": [
            {
                "id": "99001",
                "date": ko_recent,
                "competitions": [
                    {
                        "date": ko_recent,
                        "status": {"type": {"state": "post"}},
                        "competitors": [
                            {"homeAway": "home", "score": "2", "team": {"displayName": "Real Madrid"}},
                            {"homeAway": "away", "score": "1", "team": {"displayName": "Bayern Munich"}},
                        ],
                    }
                ],
            }
        ]
    }
    fake_sum = {
        "header": {
            "id": "99001",
            "competitions": fake_sb["events"][0]["competitions"],
        },
        "boxscore": {"teams": []},
        "keyEvents": [],
    }

    called_urls: list[str] = []

    class _Resp:
        def __init__(self, payload: dict, status_code: int = 200):
            self._p = payload
            self.status_code = status_code

        def json(self) -> dict:
            return self._p

    def _fake_get(url: str, params=None):
        called_urls.append(url)
        if "uefa.champions/scoreboard" in url:
            return _Resp(fake_sb)
        if "uefa.champions/summary" in url:
            return _Resp(fake_sum)
        return _Resp({"events": []})

    prov = ef.ESPNFreeProvider(timeout=5.0)
    try:
        with patch.object(prov._client, "get", side_effect=_fake_get):
            rows = prov.fetch_recent_finished_matches(now_utc=now, hours=24.0)
    finally:
        prov.close()

    # باید همهٔ ۶ لیگ بررسی شده باشند
    for slug in EUROPEAN_ESPN_SLUGS:
        assert any(f"soccer/{slug}/scoreboard" in u for u in called_urls), f"missing {slug}"
    assert len(rows) == 1
    assert rows[0]["competition"] == "UEFA Champions League"
    assert rows[0]["league_slug"] == "uefa.champions"
    assert rows[0]["home_goals"] == 2
    assert rows[0]["away_goals"] == 1


def test_espn_upcoming_extracts_fixtures_with_competition() -> None:
    payload = {
        "events": [
            {
                "id": "88001",
                "date": "2026-11-26T20:00:00Z",
                "competitions": [
                    {
                        "date": "2026-11-26T20:00:00Z",
                        "status": {"type": {"state": "pre"}},
                        "competitors": [
                            {"homeAway": "home", "team": {"displayName": "Barcelona"}},
                            {"homeAway": "away", "team": {"displayName": "Atletico Madrid"}},
                        ],
                    }
                ],
            }
        ]
    }
    parsed = ef.parse_espn_upcoming(payload, competition_name="La Liga", league_slug="esp.1")
    assert len(parsed["upcoming_fixtures"]) == 1
    fx = parsed["upcoming_fixtures"][0]
    assert fx["competition"] == "La Liga"
    assert fx["league_slug"] == "esp.1"
    assert fx["event_id"] == "88001"


def test_fdo_couk_news_debate_and_render_cover_all_six_leagues() -> None:
    assert set(fdo.EUROPEAN_FDO_CODES) == {"PL", "CL", "EL", "PD", "SA", "BL1", "FL1"}
    assert set(couk.EUROPEAN_CSV_CODES) == {"E0", "SP1", "I1", "D1", "F1"}

    bn_slugs = {slug for slug, _, _ in bnf.ESPN_NEWS_FEEDS}
    db_slugs = {slug for slug, _ in df._DEBATE_ESPN_FEEDS}
    assert set(EUROPEAN_ESPN_SLUGS).issubset(bn_slugs)
    assert set(EUROPEAN_ESPN_SLUGS).issubset(db_slugs)

    for lg in EUROPEAN_LEAGUES:
        assert lg.name_en in rcards.COMPETITION_FA, f"missing {lg.name_en} in render/cards.py"


def test_couk_parse_upcoming_odds_accepts_all_five_domestic_leagues() -> None:
    csv_txt = (
        "Div,Date,HomeTeam,AwayTeam,AvgH,AvgD,AvgA,Avg>2.5,Avg<2.5\n"
        "SP1,26/11/2026,Real Madrid,Barcelona,2.10,3.40,3.20,1.75,2.05\n"
        "I1,26/11/2026,Inter,Milan,1.95,3.50,3.80,1.80,2.00\n"
        "D1,26/11/2026,Bayern Munich,Dortmund,1.60,4.20,5.00,1.50,2.50\n"
        "F1,26/11/2026,Paris SG,Marseille,1.55,4.10,5.50,1.65,2.20\n"
        "E0,26/11/2026,Arsenal,Chelsea,1.85,3.60,4.10,1.85,1.95\n"
        "E1,26/11/2026,Leeds,Sunderland,1.90,3.40,4.00,1.90,1.90\n"
    )
    prov = couk.FootballDataCoUk()
    try:
        rows = prov.parse_upcoming_odds(csv_txt)
    finally:
        prov.close()
    assert len(rows) == 5  # E1 (Championship) excluded, all 5 top leagues included


def test_sync_and_list_multileague_finished_matches(tmp_path) -> None:
    import src.xgpedia.db as db_mod
    from src.xgpedia import sync as sync_mod
    from src.xgpedia import today_workflow as tw

    test_db = tmp_path / "test_v51.db"
    now = datetime(2026, 11, 26, 10, 0, tzinfo=timezone.utc)
    ko = (now - timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")

    with patch.object(db_mod, "DATABASE_PATH", test_db):
        db_mod.init_db()
        res = sync_mod.sync_espn_finished_matches(
            [
                {
                    "event_id": "ucl_1",
                    "competition": "UEFA Champions League",
                    "league_slug": "uefa.champions",
                    "home_team": "Real Madrid",
                    "away_team": "Bayern Munich",
                    "kickoff_utc": ko,
                    "home_goals": 3,
                    "away_goals": 2,
                    "home_stats": {"possession": 54.0, "total_shots": 16.0},
                    "away_stats": {"possession": 46.0, "total_shots": 11.0},
                    "details": {"scorers_home": "Mbappe 22'"},
                }
            ]
        )
        assert res["finished_saved"] == 1
        finished = tw.list_recent_finished_fixtures(now_utc=now, hours=24.0)
        assert len(finished) == 1
        assert finished[0].competition == "UEFA Champions League"
        assert finished[0].home_goals == 3
        assert finished[0].away_goals == 2
