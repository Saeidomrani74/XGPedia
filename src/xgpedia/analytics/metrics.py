"""لایهٔ ۳ — Analytics: محاسبهٔ قطعی با کد؛ LLM هرگز اینجا نیست.

اصل: فرم، میانگین‌ها، اختلاف xG، per-90 و تریگرها مستقل از مدل محاسبه می‌شوند.
تریگر فقط «سوژه پیشنهاد» می‌دهد، نه نتیجه‌گیری.
"""
from __future__ import annotations

from src.xgpedia.config import load_thresholds
from src.xgpedia.normalization.models import MatchFacts, StatValue, TeamSide


def form_points(last5) -> tuple[int, int] | None:
    """امتیاز ۵ بازی اخیر؛ n<5 → None چون پنجره توصیفی ناقص است."""
    if last5 is None or last5.n < 5 or last5.points is None:
        return None
    return last5.points, last5.n


def avg(values: list[float | None]) -> float | None:
    """میانگین فقط روی مقادیر موجود — Noneها حذف می‌شوند، صفر فرض نمی‌شوند."""
    real = [v for v in values if v is not None]
    return sum(real) / len(real) if real else None


def per90(value: float | None, minutes: float | None) -> float | None:
    """نرخ ۹۰ دقیقه‌ای فقط با دقایق معتبر — دقایق صفر/ناموجود = None."""
    if value is None or minutes is None or minutes <= 0:
        return None
    return round(value / minutes * 90, 3)


def xg_diff(home: TeamSide, away: TeamSide) -> float | None:
    """اختلاف xG — فقط وقتی هر دو طرف مقدار معتبر از «یک» provider دارند."""
    if home.xg_for_avg is None or away.xg_for_avg is None:
        return None
    if home.xg_for_avg.value is None or away.xg_for_avg.value is None:
        return None
    if home.xg_for_avg.provider != away.xg_for_avg.provider:
        return None  # مدل‌های متفاوت xG هرگز ادغام نمی‌شوند
    return round(home.xg_for_avg.value - away.xg_for_avg.value, 2)


def evaluate_triggers(match: MatchFacts) -> list[str]:
    """تریگرهای محتوایی با thresholds.json — مقادیر اولیه، با دادهٔ تاریخی کالیبره شوند."""
    th = load_thresholds()
    out: list[str] = []

    d = xg_diff(match.home, match.away)
    if d is not None and abs(d) >= th["xg_gap_abs"]:
        out.append("xg_gap_large" if d > 0 else "xg_gap_large_away")

    for side_name, side in (("home", match.home), ("away", match.away)):
        if side.xg_for_avg is not None and side.xg_for_avg.value is not None:
            if side.xg_for_avg.n is not None and side.xg_for_avg.n < th["min_sample_n"]:
                out.append(f"{side_name}_small_sample")

    return out


def stat_or_none(v: StatValue | None, min_n: int = 5) -> float | None:
    """شاخص با نمونهٔ کوچک‌تر از حد → None (یا در UI با هشدار «نمونهٔ کوچک»)."""
    if v is None or v.value is None:
        return None
    if v.n is not None and v.n < min_n:
        return None
    return v.value
