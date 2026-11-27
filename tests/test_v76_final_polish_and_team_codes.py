"""تست‌های نسخه v0.76.0 — شکستن xg_engine، مهاجرت بدون افت داده team_code در SQLite، پاک‌سازی is_admin و موج ۳ error_metrics."""
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_xg_engine_modular_split_and_reexports(monkeypatch) -> None:
    """xg_engine پس از شکستن باید تمام توابع کلیدی را re-export کند و SofaScore پیش‌فرض خاموش بماند."""
    from src.xgpedia.providers import xg_engine as xge
    from src.xgpedia.providers import xg_engine_fotmob as xgf
    from src.xgpedia.providers import xg_engine_playwright as xgp

    assert xge.parse_fotmob_match_details is xgf.parse_fotmob_match_details
    assert xge.parse_fotmob_next_data_html is xgf.parse_fotmob_next_data_html
    assert xge.fetch_fotmob_via_playwright is xgp.fetch_fotmob_via_playwright
    assert xge.fetch_sofascore_via_playwright is xgp.fetch_sofascore_via_playwright

    monkeypatch.delenv("XGPEDIA_ENABLE_SOFASCORE", raising=False)
    assert xge.is_sofascore_enabled() is False


def test_sqlite_team_code_migration_zero_data_loss(tmp_path, monkeypatch) -> None:
    """مهاجرت team_code روی دیتابیس موجود باید بدون حذف هیچ ردیفی کد سه‌حرفی استاندارد را پر کند."""
    from src.xgpedia import db as db_mod

    test_db = tmp_path / "legacy_v3.sqlite"
    monkeypatch.setattr(db_mod, "DATABASE_PATH", test_db)
    db_mod.init_db()

    # درج داده‌هایی با نام‌های متغیر و بدون team_code
    with db_mod.db() as conn:
        conn.execute(
            "INSERT INTO fixtures (fixture_id, provider, competition, season, kickoff_utc, home_team, away_team, status, collected_at) "
            "VALUES ('fx:1', 'test', 'PL', '2026-27', '2026-11-28T15:00:00Z', 'Newcastle', 'Arsenal', 'scheduled', '2026-11-27T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO team_metadata (team, season, venue_en, coach_en, provider, collected_at) "
            "VALUES ('Real Madrid CF', '2026-27', 'Bernabeu', 'Coach', 'test', '2026-11-27T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO fixture_odds (home_team, away_team, match_date, home_odds, provider, collected_at) "
            "VALUES ('Hull', 'Leeds', '2026-11-28', 2.1, 'test', '2026-11-27T00:00:00Z')"
        )
        updated = db_mod.backfill_team_codes(conn)
        assert updated >= 3

        fx = conn.execute("SELECT home_team, away_team, home_team_code, away_team_code FROM fixtures WHERE fixture_id='fx:1'").fetchone()
        assert fx["home_team"] == "Newcastle"
        assert fx["home_team_code"] == "NEW"
        assert fx["away_team_code"] == "ARS"

        tm = conn.execute("SELECT team, team_code FROM team_metadata WHERE team='Real Madrid CF'").fetchone()
        assert tm["team_code"] == "RMA"

        od = conn.execute("SELECT home_team_code, away_team_code FROM fixture_odds WHERE match_date='2026-11-28'").fetchone()
        assert od["home_team_code"] == "HUL"
        assert od["away_team_code"] == "LEE"
        assert db_mod.get_schema_version(conn) >= 4


def test_telegram_bot_cleaned_redundant_is_admin_and_kept_middleware() -> None:
    """چک‌های تکراری is_admin در telegram_bot.py باید پاک شده و AdminOnlyMiddleware فعال باشد."""
    tb_src = (ROOT / "src" / "xgpedia" / "publishers" / "telegram_bot.py").read_text(encoding="utf-8")
    assert "class AdminOnlyMiddleware(BaseMiddleware):" in tb_src
    assert tb_src.count("is_admin(") <= 10


def test_wave3_secondary_providers_wired_to_error_metrics() -> None:
    """پروایدرهای موج ۳ نیز باید خطاهای مهارشده را در error_metrics ثبت کنند."""
    for rel in (
        "src/xgpedia/providers/number_of_day_free.py",
        "src/xgpedia/providers/matchday_results_free.py",
        "src/xgpedia/providers/standings_free.py",
        "src/xgpedia/providers/injury_free.py",
        "src/xgpedia/providers/lineup_injuries_free.py",
        "src/xgpedia/providers/transfer_radar_free.py",
        "src/xgpedia/providers/birthday_free.py",
        "src/xgpedia/providers/quote_free.py",
    ):
        txt = (ROOT / rel).read_text(encoding="utf-8")
        assert "error_metrics" in txt, f"error_metrics missing in {rel}"
