"""تنظیمات مشترک pytest برای XGPedia:
- جلوگیری از درخواست‌های تصادفی شبکه (ویکی‌پدیا / RSS) در تست‌های واحد تا اجرای تست‌ها
  هم سریع (چند ثانیه) و هم ۱۰۰٪ پایدار و بدون وابستگی به اینترنت باشد.
  تست‌هایی که خودشان `monkeypatch` روی این توابع می‌زنند، دقیقاً مثل قبل رفتار دلخواه خود را تست می‌کنند.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _block_accidental_live_intel_http(monkeypatch):
    from src.xgpedia.providers import live_intel_free as lif

    monkeypatch.setattr(lif, "fetch_live_coach_wikipedia", lambda team, **kw: (None, None))
    monkeypatch.setattr(lif, "fetch_match_breaking_news", lambda h, a, **kw: [])
