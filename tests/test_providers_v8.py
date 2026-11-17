"""آزمون‌های واحد — قواعد حیاتی providerهای نسخهٔ ۸.

اجرا:  python -m pytest tests/ -v
قواعد تحت پوشش:
  - نگاشت نام تیم CSV → canonical («Man City» → «Manchester City»)
  - تاریخ dd/mm/yyyy → ISO
  - ردیف بدون نتیجه (آینده) رد می‌شود
  - ستون xG خالی → None (null≠0)
  - idempotency: اجرای دوبارهٔ sync رکورد تکراری نمی‌سازد
"""
from __future__ import annotations

import sqlite3

import pytest

from src.xgpedia.providers.football_data_couk import FootballDataCoUk
from src.xgpedia.sync import fixture_id_for_csv, season_label

# نمونهٔ کوچک CSV با همان ستون‌های واقعی فایل E0 (۲۶ ستون؛ xG ردیف ۲ خالی)
SAMPLE_CSV = """Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,Referee,HxG,AxG,HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR
E0,14/11/2026,20:00,Arsenal,Man City,2,1,H,1,0,H,M Oliver,2.10,0.95,15,8,7,3,9,11,6,4,1,2,0,0
E0,15/11/2026,16:30,Man United,Nott'm Forest,0,2,A,0,1,A,A Taylor,,,12,10,4,6,10,13,5,7,2,1,0,0,0
E0,22/11/2026,,Liverpool,Chelsea,,,H,,,,,,,,,,,,,,,,
"""


@pytest.fixture()
def parsed():
    api = FootballDataCoUk.__new__(FootballDataCoUk)  # بدون شبکه — فقط parse
    return api.parse_season(SAMPLE_CSV)


def test_team_name_mapping(parsed):
    """«Man City» و «Nott'm Forest» باید به نام canonical نگاشت شوند."""
    assert parsed[0].home_team == "Arsenal"
    assert parsed[0].away_team == "Manchester City"
    assert parsed[1].home_team == "Manchester United"
    assert parsed[1].away_team == "Nottingham Forest"


def test_date_normalization(parsed):
    """تاریخ dd/mm/yyyy انگلیسی → ISO yyyy-mm-dd."""
    assert parsed[0].date_utc == "2026-11-14"
    assert parsed[1].date_utc == "2026-11-15"


def test_future_row_without_score_is_dropped(parsed):
    """ردیف بی‌نتیجه (بازی آینده) در نتایج نیست — داده نیست."""
    assert len(parsed) == 2


def test_xg_empty_is_none_not_zero(parsed):
    """ستون xG خالی → None؛ هرگز 0 (قاعدهٔ null≠0)."""
    assert parsed[1].home_xg is None
    assert parsed[1].away_xg is None
    assert parsed[0].home_xg == 2.10
    assert parsed[0].away_xg == 0.95


def test_stats_parsed(parsed):
    assert parsed[0].stats["total_shots"] == 15.0
    assert parsed[0].stats["total_shots_away"] == 8.0
    assert parsed[0].stats["corner_kicks"] == 6.0
    assert parsed[1].stats["shots_on_target"] == 4.0


def test_season_label():
    assert season_label(2026) == "2026-27"
    assert season_label(2025) == "2025-26"


def test_season_csv_mapping_is_start_year():
    """قرارداد فصل: کلید SEASON_CSV «سال شروع» است — 2026 → پوشهٔ 2627 (فصل ۲۰۲۶–۲۰۲۷).

    این آزمون برای باگ 404 نوشته شد: کیت قبلاً 2027 می‌فرستاد (سال پایان) و
    API football-data.org برای فصل هنوز-موجود-نشده 404 می‌داد.
    """
    from src.xgpedia.providers.football_data_couk import SEASON_CSV

    assert SEASON_CSV[2026] == "2627"
    assert SEASON_CSV[2025] == "2526"


def test_current_season_auto_computed():
    """CURRENT_SEASON_START باید «سال شروع» فصل جاری باشد (قبل از اوت = فصل قبل)."""
    from datetime import date

    from src.xgpedia.config import CURRENT_SEASON_START

    today = date.today()
    expected = today.year if today.month >= 8 else today.year - 1
    assert CURRENT_SEASON_START == expected
    assert season_label(CURRENT_SEASON_START) == f"{expected}-{str(expected + 1)[2:]}"


def test_fixture_id_stable():
    """شناسهٔ fixture از تاریخ و تیم‌ها پایدار است — مبنای idempotency."""
    a = fixture_id_for_csv("2026-11-14", "Arsenal", "Manchester City")
    b = fixture_id_for_csv("2026-11-14", "Arsenal", "Manchester City")
    c = fixture_id_for_csv("2026-11-15", "Arsenal", "Manchester City")
    assert a == b
    assert a != c


def test_sync_idempotent(tmp_path, monkeypatch, parsed):
    """اجرای دوبارهٔ sync_csv_results نباید رکورد آماری تازه بسازد."""
    from src.xgpedia import sync as sync_mod

    monkeypatch.setattr(sync_mod, "db", _tmp_db_factory(tmp_path))
    s1 = sync_mod.sync_csv_results(parsed, "hash1", season_start=2026)
    s2 = sync_mod.sync_csv_results(parsed, "hash1", season_start=2026)
    assert s1["fixtures_new"] == 2
    assert s2["fixtures_new"] == 0  # دوباره → جدید نیست
    assert s2["fixtures_updated"] == 2  # به‌روزرسانی همان‌ها
    assert s2["stats_rows"] == 0  # رکورد آماری تازه ساخته نشد


def _tmp_db_factory(tmp_path):
    from contextlib import contextmanager

    from src.xgpedia.db import SCHEMA

    db_path = tmp_path / "test.sqlite"
    _conn = sqlite3.connect(db_path)
    _conn.row_factory = sqlite3.Row
    _conn.executescript(SCHEMA)
    _conn.commit()

    @contextmanager
    def db():
        try:
            yield _conn
            _conn.commit()
        finally:
            pass

    return db
