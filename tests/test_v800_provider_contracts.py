"""تست‌های قرارداد (Contract Tests) با فیکسچرهای ضبط‌شده برای ۵ ارائه‌دهندهٔ کلیدی (v0.80.0).

هدف: اگر ساختار JSON هر ارائه‌دهنده بالادستی (FotMob، Understat، FPL، ESPN، Football-Data.org)
تغییر کند یا قاعدهٔ `null ≠ 0` / `PSxG ≠ xGC` شکسته شود، تست با صدای بلند شکست بخورد.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "contracts"


def _load(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def test_contract_fotmob_match_details_7_modules():
    from src.xgpedia.providers.xg_engine_fotmob import parse_fotmob_match_details

    parsed = parse_fotmob_match_details(_load("fotmob_match_details.json"))
    assert parsed["home_xg"] == 2.15
    assert parsed["away_xg"] == 0.88
    assert parsed["home_big_chances"] == 4
    assert len(parsed["home_shots"]) == 2
    assert len(parsed["away_shots"]) == 1
    assert len(parsed["momentum"]) >= 4
    assert parsed["home_gk"]["psxg"] == 0.94
    assert parsed["away_gk"]["psxg"] == 2.02
    assert parsed["motm"]["rating"] == 8.7
    assert all("Opta" not in str(ch.get("label", "")) for ch in parsed["motm"]["chips"])


def test_contract_understat_match_shots():
    from src.xgpedia.providers.understat import parse_understat_match_shots

    parsed = parse_understat_match_shots(_load("understat_shots.json"))
    assert parsed is not None
    assert round(parsed["home_xg"], 2) == 0.84
    assert round(parsed["away_xg"], 2) == 0.31
    assert parsed["home_inside_box"] == 2
    assert parsed["away_inside_box"] == 1
    assert len(parsed["home_shots"]) == 2
    assert len(parsed["away_shots"]) == 1


def test_contract_fpl_live_match_respects_null_and_xgc():
    from src.xgpedia.providers.fpl_free import parse_fpl_match_post_details

    fx_data = _load("fpl_live_match.json")
    parsed = parse_fpl_match_post_details(
        fx_data["bootstrap"],
        fx_data["fixtures"],
        fx_data["live_gw"],
        "Arsenal",
        "Chelsea",
        "2026-11-26",
    )
    assert parsed is not None
    assert parsed["motm"]["name"] == "Saka"
    assert parsed["home_gk"]["psxg"] is None
    assert parsed["home_gk"]["xgc"] == 0.91
    assert parsed["away_gk"]["psxg"] is None
    assert parsed["away_gk"]["xgc"] == 1.85


def test_contract_espn_finished_summary_no_fake_psxg():
    from src.xgpedia.providers.espn_free import parse_espn_finished_summary

    parsed = parse_espn_finished_summary(
        _load("espn_summary.json"),
        competition_name="Premier League",
        league_slug="eng.1",
    )
    assert parsed is not None
    assert parsed["home_team"] == "Arsenal"
    assert parsed["away_team"] == "Chelsea"
    assert parsed["home_goals"] == 2 and parsed["away_goals"] == 1
    assert parsed["home_stats"]["possession"] == 61.0
    gk_home = (parsed.get("details") or {}).get("home_gk")
    if gk_home:
        assert gk_home.get("psxg") is None


def test_contract_fdo_upcoming_fixtures_populates_team_codes():
    from src.xgpedia import db as db_mod
    from src.xgpedia.sync import sync_upcoming_fixtures

    payload = _load("fdo_fixtures.json")
    raw = SimpleNamespace(payload=payload, payload_hash="contract_fdo_hash_001")
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "fdo_contract.db"
        with patch.object(db_mod, "DATABASE_PATH", db_path):
            db_mod.init_db()
            res = sync_upcoming_fixtures(raw, season_start=2026)
            assert res["upcoming_new"] == 1
            with db_mod.db() as conn:
                row = conn.execute(
                    "SELECT home_team, away_team, home_team_code, away_team_code FROM fixtures WHERE fixture_id='fdo:555001'"
                ).fetchone()
            assert row["home_team"] == "Arsenal"
            assert row["away_team"] == "Chelsea"
            assert row["home_team_code"] == "ARS"
            assert row["away_team_code"] == "CHE"
