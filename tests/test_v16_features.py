"""آزمون‌های نسخهٔ 0.16.0 — جدول پخش صداوسیما، کش هوشمند دیتابیس، و تولید مجدد/ویرایش متن."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.xgpedia import db as db_mod
from src.xgpedia import today_workflow as tw
from src.xgpedia.providers.irib_conductor import (
    match_fixture_broadcast,
    normalize_fa,
    parse_conductor_html,
)

SAMPLE_VARZESH_HTML = """
<html><body><table>
  <tr><td>12:04</td><td>مسابقات خاطره انگیز (فوتبال/لیورپول-منچستریونایتد)</td><td>01:14:01</td></tr>
  <tr><td>20:00</td><td>لذت فوتبال/زنده (نیمه اول/لیور\u200d\u200dپول-منچستریونایتد)</td><td>00:48:00</td></tr>
  <tr><td>23:30</td><td>لذت فوتبال/زنده (نیمه اول/ختافه -اتلتیکومادرید)</td><td>00:29:59</td></tr>
</table></body></html>
"""


def test_irib_conductor_parses_zwj_and_skips_replays():
    assert normalize_fa("لیور\u200d\u200dپول") == "لیورپول"
    progs = parse_conductor_html(SAMPLE_VARZESH_HTML, "varzesh", "پخش زنده: شبکه ورزش")
    assert len(progs) == 3

    matched = match_fixture_broadcast(
        progs,
        "Liverpool",
        "Manchester United",
        home_fa="لیورپول",
        away_fa="منچستریونایتد",
        kickoff_tehran="20:00",
    )
    assert matched is not None
    assert matched.channel_label == "پخش زنده: شبکه ورزش"
    assert matched.start_time == "20:00"
    assert matched.is_live is True

    # بازی‌ای که در جدول نیست نباید تطبیق غلط بدهد
    none_match = match_fixture_broadcast(
        progs, "Hull", "Brighton", home_fa="هال سیتی", away_fa="برایتون", kickoff_tehran="17:30"
    )
    assert none_match is None


def test_sync_cache_prevents_redundant_api_calls(tmp_path: Path, monkeypatch):
    db_file = tmp_path / "cache.db"
    monkeypatch.setattr(db_mod, "DATABASE_PATH", db_file)
    db_mod.init_db()

    # درج یک بازی تمام‌شده و یک بازی پیش‌رو تا کش معتبر باشد
    with db_mod.db() as conn:
        conn.execute(
            "INSERT INTO fixtures (fixture_id, provider, competition, season, kickoff_utc, home_team, away_team, status, raw_payload_hash, collected_at) "
            "VALUES ('f1','football-data-co-uk','Premier League','2026-27','2026-11-10','Liverpool','Arsenal','finished',NULL,'2026-11-22T06:00:00Z')"
        )
        conn.execute(
            "INSERT INTO fixtures (fixture_id, provider, competition, season, kickoff_utc, home_team, away_team, status, raw_payload_hash, collected_at) "
            "VALUES ('f2','football-data-org','Premier League','2026-27','2026-11-22T16:30:00Z','Liverpool','Manchester United','scheduled',NULL,'2026-11-22T06:00:00Z')"
        )

    now = datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc)
    tehran_date = "2026-11-22"
    tw._save_sync_cache("results", tehran_date, now, "100 بازی بررسی شد")
    tw._save_sync_cache("fixtures", tehran_date, now, "3 بازی پیش‌رو")

    # ۱ ساعت بعد: کش معتبر است و نیازی به API نیست
    hit = tw._cache_fresh_summary("results", tehran_date, 6.0, datetime(2026, 11, 22, 11, 0, tzinfo=timezone.utc))
    assert hit is not None and "کش دیتابیس" in hit

    # ۸ ساعت بعد: TTL منقضی شده
    miss = tw._cache_fresh_summary("results", tehran_date, 6.0, datetime(2026, 11, 22, 18, 30, tzinfo=timezone.utc))
    assert miss is None


def test_broadcast_index_detection_for_customizer():
    import pytest

    pytest.importorskip("aiogram", reason="publish extras not installed")
    from src.xgpedia.publishers import telegram_bot as tb

    assert tb._broadcast_index_for("پخش زنده: شبکه ورزش") == 2
    assert tb._broadcast_index_for("پخش زنده: شبکه سه") == 1
    assert tb._broadcast_index_for("") == 0
