"""تست‌های رگرسیون نسخهٔ تثبیت نهایی v0.80.0 (هر ۶ مورد بخش الف)."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def test_v800_no_circular_import_between_xg_engine_and_playwright():
    pw_src = (ROOT / "src" / "xgpedia" / "providers" / "xg_engine_playwright.py").read_text(encoding="utf-8")
    assert "import xg_engine as" not in pw_src
    assert "from src.xgpedia.providers import xg_engine " not in pw_src
    assert "xg_engine_common" in pw_src

    from src.xgpedia.providers import xg_engine, xg_engine_common, xg_engine_playwright

    assert xg_engine._teams_match is xg_engine_common._teams_match
    assert xg_engine._FOTMOB_DAY_CACHE is xg_engine_common._FOTMOB_DAY_CACHE
    assert xg_engine.fetch_fotmob_via_playwright is xg_engine_playwright.fetch_fotmob_via_playwright


def test_v800_db_backup_before_migration():
    import sqlite3
    from src.xgpedia import db as db_mod

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "legacy.sqlite"
        # ایجاد یک DB قدیمی با user_version=2
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE fixtures (fixture_id TEXT PRIMARY KEY, provider TEXT, competition TEXT, season TEXT, kickoff_utc TEXT, home_team TEXT, away_team TEXT, status TEXT, collected_at TEXT)")
        conn.execute("CREATE TABLE posts (post_id INTEGER PRIMARY KEY, post_type TEXT, fixture_id TEXT, status TEXT, content_version INTEGER, text_fa TEXT, caption_fa TEXT, created_at TEXT)")
        conn.execute("PRAGMA user_version = 2")
        conn.commit()
        conn.close()

        with patch.object(db_mod, "DATABASE_PATH", db_path):
            db_mod.init_db()
            backups = list((Path(td) / "backups").glob("legacy_pre_v*_from_v2_*.sqlite"))
            assert len(backups) == 1 and backups[0].stat().st_size > 0
            with db_mod.db() as c2:
                assert db_mod.get_schema_version(c2) == db_mod.SCHEMA_VERSION


def test_v800_metrics_learner_and_auto_publish_candidates():
    from src.xgpedia import db as db_mod
    from src.xgpedia.core.metrics_learner import format_metrics_report_fa, summarize_post_metrics

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "metrics.sqlite"
        with patch.object(db_mod, "DATABASE_PATH", db_path):
            db_mod.init_db()
            for i in range(10):
                db_mod.record_post_metric("pre_match", "approved", post_id=i + 1, tone="analytical", edit_count=0)
            db_mod.record_post_metric("breaking_news", "rejected", post_id=99, tone="fan_light", edit_count=2)

            summary = summarize_post_metrics(min_samples=10, auto_threshold=0.95)
            assert summary["total"] == 11
            assert summary["by_card"]["pre_match"]["auto_ready"] is True
            assert "pre_match" in summary["auto_publish_candidates"]
            assert "breaking_news" not in summary["auto_publish_candidates"]
            report = format_metrics_report_fa(summary)
            assert "pre_match" in report and "آماده خودکارسازی" in report


def test_v800_visual_qa_includes_9x16_16x9_and_sample_badge():
    from src.xgpedia.render.visual_qa import build_flagship_card_htmls

    htmls = build_flagship_card_htmls()
    assert "pre_match_story_9x16" in htmls
    assert "standings_wide_16x9" in htmls
    assert "نمونه • SAMPLE" in htmls["standings_wide_16x9"]


def test_v800_telegram_bot_registers_metrics_command():
    bot_src = (ROOT / "src" / "xgpedia" / "publishers" / "telegram_bot.py").read_text(encoding="utf-8")
    assert 'Command("metrics")' in bot_src
    assert "format_metrics_report_fa" in bot_src
