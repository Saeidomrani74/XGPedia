"""لایهٔ ۲ — Normalization: تبدیل payload خام به schema داخلی یکسان.

تحلیل (لایهٔ ۳) فقط از این لایه می‌خواند؛ هرگز از payload مستقیم.
قاعدهٔ حیاتی: null یعنی «داده موجود نیست»، صفر یعنی «مقدار واقعاً صفر است».
اگر API کرنر را نداد، «۰ کرنر» نمایش داده نمی‌شود.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class StatValue(BaseModel):
    """هر شاخص به‌همراه حجم نمونه و منبع — بدون این‌ها شاخص منتشر نمی‌شود."""

    value: float | None  # None = داده در دسترس نیست (هرگز 0 جایگزین نشود)
    n: int | None = None
    provider: str | None = None


class Last5(BaseModel):
    n: int
    points: int | None = None
    goals_for: int | None = None
    goals_against: int | None = None


class RecentForm(BaseModel):
    """ترتیب نتایج بازی‌های اخیر — برای دایره‌های فرم کارت استودیو (ب/م/ش)."""

    sequence: str  # قدیمی‌ترین به جدیدترین؛ فقط حروف W/D/L
    n: int


class MatchStats(BaseModel):
    """آمار همان یک بازی (نه میانگین فصل) — فقط برای بازی‌های پایان‌یافته.

    فیلدی که provider نداد None می‌ماند (null≠0)؛ رندرر ماژول/ردیفش را نمی‌سازد.
    """

    goals: StatValue | None = None
    expected_goals: StatValue | None = None
    total_shots: StatValue | None = None
    shots_on_target: StatValue | None = None
    corner_kicks: StatValue | None = None
    fouls: StatValue | None = None
    yellow_cards: StatValue | None = None
    red_cards: StatValue | None = None


class MatchResult(BaseModel):
    """نتیجهٔ نهایی — از متریک goals همان بازی؛ غایب = بازی هنوز تمام نشده."""

    home_goals: int | None = None
    away_goals: int | None = None


class TeamSide(BaseModel):
    name_fa: str
    name_en: str
    last5: Last5 | None = None
    xg_for_avg: StatValue | None = None   # اگر provider نداد → None بماند
    corners_avg: StatValue | None = None
    # ── فیلدهای اختیاری کارت استودیو (v10) — پست‌های آرشیوشدهٔ قدیمی بدون این‌ها هم parse می‌شوند ──
    xg_against_avg: StatValue | None = None  # میانگین xG حریفان در بازی‌های تیم (xGA)
    sot_avg: StatValue | None = None         # میانگین شوت در چارچوب
    xg_series: list[float] | None = None     # xG بازی‌به‌بازی، قدیمی‌ترین → جدیدترین (حداکثر ۱۰) — برای روند ۱۰ بازی
    recent_form: RecentForm | None = None    # توالی ب/م/ش — برای دایره‌های فرم
    # ── کارت پس‌از‌بازی (post_match) — آمار خودِ بازی ──
    match_stats: MatchStats | None = None
    # ── داده‌های تکمیلی رایگان (v0.14.0): رادار صدک لیگ + مهرهٔ کلیدی Understat ──
    radar: list[int] | None = None
    kp: dict[str, str] | None = None


class AvailabilityItem(BaseModel):
    player: str
    status: str  # confirmed_out | reported | probable | unknown
    source_url: str
    checked_at: str


class SourceInfo(BaseModel):
    provider: str
    collected_at: str
    payload_hash: str | None = None


class DataQuality(BaseModel):
    missing_fields: list[str] = Field(default_factory=list)
    live_latency_seconds: float | None = None


class MatchFacts(BaseModel):
    """«JSON واقعیت‌ها» — تنها ورودی مجاز برای LLM و رندرر.

    کلید یکتای idempotency: (fixture_id, post_type, target_platform, content_version)
    """

    fixture_id: str                    # قالب: "provider:12345"
    competition: dict[str, str]        # {name, season}
    kickoff_utc: datetime
    source: SourceInfo
    home: TeamSide
    away: TeamSide
    result: MatchResult | None = None  # فقط post_match بازی‌های پایان‌یافته
    availability: list[AvailabilityItem] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)
    data_quality: DataQuality = Field(default_factory=DataQuality)
    market_odds: dict[str, float] | None = None  # ضرایب واقعی بازار از football-data.co.uk/fixtures.csv

    @property
    def kickoff_tehran(self) -> str:
        """نمایش همیشه «به وقت تهران (UTC+3:30)» — ایران ساعت تابستانی ندارد."""
        offset_hours = 3 + 30 / 60
        local = self.kickoff_utc.timestamp() + offset_hours * 3600
        return datetime.fromtimestamp(local, tz=timezone.utc).strftime("%H:%M")


def normalize_statistics_api_football(raw_team_stats: list[dict[str, Any]]) -> dict[str, float | None]:
    """تبدیل آرایهٔ آمار API-Football به dict داخلی.

    مقادیر مثل "None"، رشتهٔ خالی یا درصدِ متنی → None (نه صفر).
    """
    out: dict[str, float | None] = {}
    for item in raw_team_stats:
        key = (item.get("type") or "").strip().lower().replace(" ", "_")
        val = item.get("value")
        if val is None or (isinstance(val, str) and val.strip() in {"", "None", "null"}):
            out[key] = None  # داده در دسترس نیست
            continue
        if isinstance(val, str) and val.endswith("%"):
            try:
                out[key] = float(val[:-1])
            except ValueError:
                out[key] = None
            continue
        try:
            out[key] = float(val)
        except (TypeError, ValueError):
            out[key] = None
    return out
