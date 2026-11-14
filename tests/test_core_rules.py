"""آزمون‌های واحد — قواعد حیاتی لایهٔ Normalization و Analytics.

قاعده: n<5، null≠0، مخرج per-90، تفکیک provider در xG.
اجرا:  python -m pytest tests/ -v
"""
from __future__ import annotations

import pytest

from src.xgpedia.analytics.metrics import avg, per90, xg_diff
from src.xgpedia.normalization.models import Last5, StatValue, TeamSide
from src.xgpedia.normalization.models import normalize_statistics_api_football


def test_null_is_not_zero():
    """null یعنی ناموجود؛ هرگز به صفر تبدیل نمی‌شود."""
    stats = normalize_statistics_api_football([{"type": "Corner Kicks", "value": None}])
    assert stats["corner_kicks"] is None
    assert stats["corner_kicks"] != 0


def test_percent_string():
    stats = normalize_statistics_api_football([{"type": "Ball Possession", "value": "61%"}])
    assert stats["ball_possession"] == 61.0


def test_avg_ignores_none():
    assert avg([1.0, None, 3.0]) == 2.0
    assert avg([None, None]) is None


def test_per90_requires_valid_minutes():
    assert per90(None, 900) is None      # مقدار ناموجود → None
    assert per90(5.0, None) is None      # دقایق ناموجود → None
    assert per90(5.0, 0) is None         # تقسیم بر صفر ممنوع
    assert per90(9.0, 900) == pytest.approx(0.9)


def test_xg_never_mixes_providers():
    """xG دو provider در یک مقایسه ادغام نمی‌شود مگر مدل‌ها harmonize باشند."""
    home = TeamSide(name_fa="آ", name_en="A", xg_for_avg=StatValue(value=1.8, n=5, provider="p1"))
    away = TeamSide(name_fa="ب", name_en="B", xg_for_avg=StatValue(value=1.2, n=5, provider="p2"))
    assert xg_diff(home, away) is None   # provider متفاوت → مقایسه ممنوع


def test_small_sample_last5():
    assert Last5(n=4, points=9).n == 4   # پنجرهٔ توصیفی ناقص — در لایهٔ تحلیل None می‌شود
