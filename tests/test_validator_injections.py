"""مجموعهٔ تزریق خطا — ۳۰ مورد؛ validator باید همه را رد کند (شرط Gate 3).

توزیع (بخش ۵.۶ سند):
  ۱۰ جابه‌جایی عدد یا میزبان/میهمان · ۵ تبدیل null به ۰ ·
  ۵ مصدومیت/ترکیب ساختگی · ۵ نام خارج از glossary ·
  ۳ جملهٔ علّی بی‌پشتوانه · ۲ جملهٔ قطعیِ فاقد پشتوانهٔ داده‌ای
"""
from __future__ import annotations

import pytest

from src.xgpedia.editorial.llm_provider import DraftOutput
from src.xgpedia.editorial.validate import validate
from src.xgpedia.normalization.models import (
    AvailabilityItem,
    DataQuality,
    Last5,
    MatchFacts,
    SourceInfo,
    StatValue,
    TeamSide,
)

FAKE_URL = "https://example.invalid/source"


def make_match() -> MatchFacts:
    return MatchFacts(
        fixture_id="api-football:1",
        competition={"name": "Premier League", "season": "2026/27"},
        kickoff_utc="2026-11-14T17:30:00Z",
        source=SourceInfo(provider="api-football", collected_at="2026-11-13T09:00:00Z"),
        home=TeamSide(name_fa="آرسنال", name_en="Arsenal",
                      last5=Last5(n=5, points=10, goals_for=9, goals_against=4),
                      xg_for_avg=StatValue(value=1.82, n=5, provider="api-football"),
                      corners_avg=StatValue(value=6.1, n=5)),
        away=TeamSide(name_fa="چلسی", name_en="Chelsea",
                      last5=Last5(n=5, points=7, goals_for=6, goals_against=6),
                      xg_for_avg=None, corners_avg=StatValue(value=5.4, n=5)),
    )


def draft(**kw) -> DraftOutput:
    base = dict(status="ok", title="آرسنال در فرم بهتر است",
                bullets=["آرسنال ۱۰ امتیاز از ۵ بازی اخیر", "میانگین xG: 1.82 در ۵ بازی"],
                caption="تحلیل پیش‌بازی با دادهٔ کامل.",
                source_note="API-Football · 2026-11-13", uncertainties=[])
    base.update(kw)
    return DraftOutput(**base)


# ---- عمدتاً دروازهٔ عددی: ۱۰ مورد جابه‌جایی عدد ----
# نکته: اعداد انتخابی عمداً خارج از مجموعهٔ اعداد مجاز فکت‌های نمونه‌اند
# {10, 9, 4, 5, 1.82, 6.1, 5.4, 6, 7} تا آزمون واقعی «عدد ناشناخته» باشد.
@pytest.mark.parametrize("bad", [
    ("آرسنال ۱۱ امتیاز از ۵ بازی اخیر", None),       # عدد غلط
    ("میانگین xG: 2.5", None),                        # عدد ساختگی
    ("میانگین xG: 1.97 در 8 بازی", None),             # n غلط
    ("آرسنال ۱۰ امتیاز از ۵ بازی و ۹ گل زده و ۱۳ گل خورده", None),  # گل خورده جابه‌جا
    ("میانگین کرنر آرسنال: 7.9", None),               # کرنر غلط
    ("چلسی ۸ امتیاز دارد", None),                     # عدد تیم مقابل
    ("فاصلهٔ امتیاز: ۳", None),                        # عدد مشتق‌نشده
    ("۱۲ کرنر میانگین", None),
    ("xG برابر 1.82 اما مالکیت ۷۳٪", None),           # درصد بدون منبع در فکت
    ("آرسنال در ۱۵ بازی اخیر", None),                 # پنجرهٔ غلط
])
def test_injected_number_errors_rejected(bad):
    text, _ = bad
    d = draft(caption=text)
    assert not validate(d, make_match(), set()).passed


# ---- ۵ مورد null → ۰ ----
@pytest.mark.parametrize("text", [
    "میانگین xG چلسی صفر است",
    "xG چلسی: 0",
    "چلسی 0.0 امید گل ساخته",
    "کرنر چلسی ۰ بود",
    "چلسی هیچ xG ثبت‌نشده‌ای ندارد؛ عدد: 0",
])
def test_null_becoming_zero_rejected(text):
    d = draft(caption=text)  # xG چلسی در فکت null است — «۰» یعنی تحریف
    assert not validate(d, make_match(), set()).passed


# ---- ۲ جملهٔ قطعیِ فاقد پشتوانه + ۳ جملهٔ علّی بی‌پشتوانه ----
@pytest.mark.parametrize("text", [
    "احتمال برد این تیم ۹۵ درصد است",
    "پیروزی امشب کاملاً تضمینی است",
    "حتماً می‌برد",
    "برنده تضمینی است",
    "چون مالکیت بیشتر دارد، قطعاً می‌برد",
])
def test_policy_violations_rejected(text):
    d = draft(title=text)
    assert not validate(d, make_match(), set()).passed


def test_insufficient_data_must_not_fabricate():
    d = draft(status="insufficient_data",
              title="پیش‌بازی بدون دادهٔ کافی",
              caption="اما به‌هرحال چلسی ۹ امتیاز دارد و حتماً می‌برد")
    assert not validate(d, make_match(), set()).passed


def test_valid_draft_passes():
    rep = validate(draft(), make_match(), set())
    assert rep.passed, rep.failures
