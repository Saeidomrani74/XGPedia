"""تست‌های نسخهٔ 0.55.0: اصلاح کامل نام ۱۴۰ تیم، حذف تکرار بازی‌ها و فارسی‌سازی دقیق بازیکنان و دروازه‌بان‌ها."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from src.xgpedia.config import canonical_team_name, team_name_fa, translate_player_fa
from src.xgpedia import db as db_mod
from src.xgpedia import today_workflow as tw


def test_corrected_persian_team_names_and_fdo_aliases() -> None:
    assert team_name_fa("Paris Saint-Germain") == "پاریس سن‌ژرمن"
    assert team_name_fa("Paris Saint-Germain FC") == "پاریس سن‌ژرمن"
    assert team_name_fa("Viking FK") == "وایکینگ"
    assert team_name_fa("Viking") == "وایکینگ"
    assert team_name_fa("SK Slavia Praha") == "اسلاویا پراگ"
    assert team_name_fa("Slavia Prague") == "اسلاویا پراگ"
    assert team_name_fa("FC Internazionale Milano") == "اینتر میلان"
    assert team_name_fa("Club Atlético de Madrid") == "اتلتیکو مادرید"
    assert team_name_fa("FC Shakhtar Donetsk") == "شاختار دونتسک"
    assert team_name_fa("Fenerbahçe SK") == "فنرباغچه"
    assert team_name_fa("Borussia Dortmund") == "بوروسیا دورتموند"
    assert team_name_fa("FC Augsburg") == "آوگسبورگ"

    # نام canonical یکتا برای هر دو منبع FDO و ESPN
    assert canonical_team_name("FC Internazionale Milano") == "Inter Milan"
    assert canonical_team_name("Club Atlético de Madrid") == "Atletico Madrid"
    assert canonical_team_name("SK Slavia Praha") == "Slavia Prague"
    assert canonical_team_name("Fenerbahçe SK") == "Fenerbahce"
    assert canonical_team_name("Viking") == "Viking FK"


def test_persian_player_and_goalkeeper_names_clean_without_single_letter_initial() -> None:
    assert translate_player_fa("J. Oblak") == "اوبلاک"
    assert translate_player_fa("L. Belko") == "بلکو"
    assert translate_player_fa("S. Pokatilov") == "پوکاتیلوف"
    assert translate_player_fa("J. García") == "گارسیا"
    assert translate_player_fa("Kylian Mbappé") == "کیلیان امباپه"
    assert translate_player_fa("Alexander Sørloth") == "الکساندر سورلوت"
    assert translate_player_fa("Julián Álvarez") == "خولیان آلوارز"


def test_list_recent_finished_fixtures_deduplicates_fdo_and_espn_name_variants(tmp_path) -> None:
    test_db = tmp_path / "dedup_v55.db"
    now = datetime(2026, 11, 26, 10, 0, tzinfo=timezone.utc)
    ko = (now - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

    with patch.object(db_mod, "DATABASE_PATH", test_db):
        db_mod.init_db()
        with db_mod.db() as conn:
            # ثبت تکراری دقیقاً شبیه DB واقعی کاربر (یک رکورد FDO بدون آمار و یک رکورد ESPN با آمار)
            conn.execute(
                "INSERT INTO fixtures (fixture_id, provider, competition, season, kickoff_utc, home_team, away_team, status, collected_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'finished', ?)",
                ("fdo:1", "football-data-org", "UEFA Champions League", "2026-27", ko, "FC Internazionale Milano", "VfB Stuttgart 1893", ko),
            )
            conn.execute(
                "INSERT INTO fixtures (fixture_id, provider, competition, season, kickoff_utc, home_team, away_team, status, collected_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'finished', ?)",
                ("espn:1", "espn-public", "UEFA Champions League", "2026-27", ko, "Inter Milan", "VfB Stuttgart", ko),
            )
            for fid, h, a in (("fdo:1", "FC Internazionale Milano", "VfB Stuttgart 1893"), ("espn:1", "Inter Milan", "VfB Stuttgart")):
                conn.execute("INSERT INTO fixture_statistics (fixture_id, team, metric, value, provider, collected_at) VALUES (?, ?, 'goals', 2, 'espn-public', ?)", (fid, h, ko))
                conn.execute("INSERT INTO fixture_statistics (fixture_id, team, metric, value, provider, collected_at) VALUES (?, ?, 'goals', 0, 'espn-public', ?)", (fid, a, ko))
            # رکورد ESPN آمار بیشتری دارد پس باید همان انتخاب شود
            conn.execute("INSERT INTO fixture_statistics (fixture_id, team, metric, value, provider, collected_at) VALUES ('espn:1', 'Inter Milan', 'total_shots', 14, 'espn-public', ?)", (ko,))

        items = tw.list_recent_finished_fixtures(now_utc=now, hours=24.0)
        assert len(items) == 1
        assert items[0].fixture_id == "espn:1"
        assert items[0].home_fa == "اینتر میلان"


def test_match_metrics_recovers_legacy_team_names_in_db(tmp_path) -> None:
    from src.xgpedia.sync import build_match_facts

    test_db = tmp_path / "legacy_team_stats.db"
    ko = "2026-11-25T20:00:00Z"
    with patch.object(db_mod, "DATABASE_PATH", test_db):
        db_mod.init_db()
        with db_mod.db() as conn:
            conn.execute(
                "INSERT INTO fixtures (fixture_id, provider, competition, season, kickoff_utc, home_team, away_team, status, collected_at) VALUES ('espn:99', 'espn-public', 'UEFA Champions League', '2026-27', ?, 'Internazionale', 'Stuttgart', 'finished', ?)",
                (ko, ko),
            )
            for tm_n, met, val in (
                ("Internazionale", "goals", 2.0),
                ("Internazionale", "possession", 57.0),
                ("Internazionale", "total_shots", 16.0),
                ("Internazionale", "shots_on_target", 6.0),
                ("Stuttgart", "goals", 0.0),
                ("Stuttgart", "possession", 43.0),
                ("Stuttgart", "total_shots", 8.0),
                ("Stuttgart", "shots_on_target", 2.0),
            ):
                conn.execute(
                    "INSERT INTO fixture_statistics (fixture_id, team, metric, value, provider, collected_at) VALUES ('espn:99', ?, ?, ?, 'espn-public', ?)",
                    (tm_n, met, val, ko),
                )
        facts = build_match_facts("espn:99", post_match=True)
        assert facts["result"]["home_goals"] == 2
        assert facts["result"]["away_goals"] == 0
        assert facts["home"]["match_stats"]["total_shots"]["value"] == 16.0
        assert facts["away"]["match_stats"]["possession"]["value"] == 43.0
