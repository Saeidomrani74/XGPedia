"""آزمون‌های فیلدهای جدید فکت‌ها (v10) — helpers همگام‌سازی روی SQLite درون‌حافظه.

اجرا:  python -m pytest tests/test_sync_facts.py -v
پوشش:
  - xGA: میانگین xG حریفان از ردیف حریف در همان بازی
  - SOT: میانگین شوت در چارچوب
  - xg_series: سری بازی‌به‌بازی، قدیمی‌ترین → جدیدترین، سقف ۱۰
  - recent_form: توالی W/D/L از گل‌های بازی‌ها
  - سازگاری با فیلدهای جدید TeamSide در build واقعی (بدون داده → None، هرگز صفر)
"""
from __future__ import annotations

import sqlite3

import pytest

from src.xgpedia.sync import (
    _team_form_sequence,
    _team_sot_avg,
    _team_xg_series,
    _team_xga_avg,
)

SCHEMA = """
CREATE TABLE fixtures (
  fixture_id TEXT PRIMARY KEY, provider TEXT NOT NULL, competition TEXT NOT NULL,
  season TEXT NOT NULL, kickoff_utc TEXT NOT NULL, home_team TEXT NOT NULL,
  away_team TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'scheduled',
  raw_payload_hash TEXT, collected_at TEXT NOT NULL
);
CREATE TABLE fixture_statistics (
  fixture_id TEXT NOT NULL, team TEXT NOT NULL, metric TEXT NOT NULL,
  value REAL, n INTEGER, provider TEXT NOT NULL, collected_at TEXT NOT NULL,
  PRIMARY KEY (fixture_id, team, metric, provider)
);
"""


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    rows = [
        # (fixture_id, kickoff, home, away, stat: (team, metric, value))
        ("f1", "2026-08-10", "Arsenal", "Chelsea", [("Arsenal", "expected_goals", 1.5), ("Chelsea", "expected_goals", 1.0),
                                                     ("Arsenal", "shots_on_target", 6), ("Chelsea", "shots_on_target", 3),
                                                     ("Arsenal", "goals", 2), ("Chelsea", "goals", 1)]),
        ("f2", "2026-08-20", "Liverpool", "Arsenal", [("Liverpool", "expected_goals", 2.0), ("Arsenal", "expected_goals", 0.9),
                                                       ("Liverpool", "shots_on_target", 7), ("Arsenal", "shots_on_target", 4),
                                                       ("Liverpool", "goals", 2), ("Arsenal", "goals", 2)]),
        ("f3", "2026-09-01", "Arsenal", "Everton", [("Arsenal", "expected_goals", 1.8), ("Everton", "expected_goals", 0.5),
                                                     ("Arsenal", "shots_on_target", 8), ("Everton", "shots_on_target", 2),
                                                     ("Arsenal", "goals", 3), ("Everton", "goals", 0)]),
        ("f4", "2026-09-15", "Everton", "Arsenal", [("Everton", "expected_goals", 0.7), ("Arsenal", "expected_goals", 1.2),
                                                     ("Everton", "goals", 0), ("Arsenal", "goals", 1)]),
    ]
    for fid, kickoff, home, away, stats in rows:
        c.execute(
            "INSERT INTO fixtures VALUES (?,?,?,?,?,?,?,?,?,?)",
            (fid, "football-data-co-uk", "Premier League", "2026-27", kickoff, home, away,
             "finished", None, "2026-11-01T00:00:00Z"),
        )
        for team, metric, value in stats:
            c.execute(
                "INSERT INTO fixture_statistics VALUES (?,?,?,?,?,?,?)",
                (fid, team, metric, value, None, "football-data-co-uk", "2026-11-01T00:00:00Z"),
            )
    yield c
    c.close()


def test_xga_averages_opponent_xg(conn):
    """xGA آرسنال = میانگین xG حریفان در بازی‌هایش: (1.0 + 2.0 + 0.5 + 0.7) / 4 = 1.05."""
    xga = _team_xga_avg(conn, "Arsenal", "2026-10-01")
    assert xga["n"] == 4
    assert xga["avg"] == pytest.approx(1.05)


def test_sot_average(conn):
    sot = _team_sot_avg(conn, "Arsenal", "2026-10-01")
    assert sot["n"] == 3
    assert sot["avg"] == pytest.approx((6 + 4 + 8) / 3)


def test_xg_series_oldest_first(conn):
    series = _team_xg_series(conn, "Arsenal", "2026-10-01")
    assert series == [1.5, 0.9, 1.8, 1.2]


def test_xg_series_respects_limit(conn):
    series = _team_xg_series(conn, "Arsenal", "2026-10-01", limit=2)
    assert series == [1.8, 1.2]  # دو بازی آخر


def test_form_sequence_oldest_first(conn):
    """آرسنال: برد، مساوی، برد، برد → WDW... — قدیمی‌ترین اول."""
    form = _team_form_sequence(conn, "Arsenal", "2026-10-01")
    assert form == {"sequence": "WDWW", "n": 4}


def test_no_data_returns_none_not_zero(conn):
    """تیمی که هیچ بازی‌ای ندارد → None (null≠0)، هرگز صفر یا لیست خالی."""
    assert _team_xga_avg(conn, "Coventry", "2026-10-01") is None
    assert _team_sot_avg(conn, "Coventry", "2026-10-01") is None
    assert _team_xg_series(conn, "Coventry", "2026-10-01") is None
    assert _team_form_sequence(conn, "Coventry", "2026-10-01") is None


def test_future_matches_excluded(conn):
    """بازی‌های بعد از تاریخ مرجع در هیچ محاسبه‌ای نیستند."""
    assert _team_xga_avg(conn, "Arsenal", "2026-08-15")["n"] == 1  # فقط f1
    assert _team_form_sequence(conn, "Arsenal", "2026-08-15")["sequence"] == "W"


def test_build_match_facts_model_accepts_new_fields():
    """TeamSide جدید (v10) با فیلدهای اختیاری None هم parse می‌شود — سازگاری با پست‌های قدیمی."""
    from src.xgpedia.normalization.models import TeamSide

    old = {"name_fa": "آرسنال", "name_en": "Arsenal"}  # فکت آرشیوشدهٔ v9
    side = TeamSide(**old)
    assert side.xg_against_avg is None and side.recent_form is None
