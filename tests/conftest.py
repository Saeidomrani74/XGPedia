"""تنظیمات مشترک pytest برای XGPedia:
- ایزوله‌سازی کامل حافظهٔ سلامت APIها (`api_health`) در حالت حافظه (بدون نوشتن روی دیسک)
- مسدودسازی درخواست‌های تصادفی شبکه (ویکی‌پدیا / RSS / FPL / LLM آنلاین / urllib خارجی)
  در تست‌های واحد تا کل مجموعهٔ تست‌ها سریع، یکدست و ۱۰۰٪ مستقل از اینترنت باشد.
  تست‌هایی که خودشان `monkeypatch` روی `httpx.post`، `urllib.request.urlopen` یا توابع provider
  می‌زنند، دقیقاً مثل قبل رفتار دلخواه خود را تست می‌کنند.
"""
from __future__ import annotations

import urllib.request
import pytest


@pytest.fixture(autouse=True)
def _block_accidental_live_http_and_llm(monkeypatch):
    # ۱) ایزوله‌سازی حافظهٔ سلامت APIها برای هر تست
    try:
        from src.xgpedia.core import api_health
        api_health.configure_health_store(persist=False, clear=True)
    except Exception:
        pass

    # ۲) مسدودسازی ویکی‌پدیا/اخبار تصادفی
    from src.xgpedia.providers import live_intel_free as lif
    monkeypatch.setattr(lif, "fetch_live_coach_wikipedia", lambda team, **kw: (None, None))
    monkeypatch.setattr(lif, "fetch_match_breaking_news", lambda h, a, **kw: [])

    # ۳) مسدودسازی FPL / تصاویر آنلاین / generate_text تصادفی
    try:
        from src.xgpedia.providers import fpl_free
        monkeypatch.setattr(fpl_free, "fetch_fpl_bootstrap", lambda *a, **kw: None)
        monkeypatch.setattr(fpl_free, "fetch_fpl_fixtures", lambda *a, **kw: [])
    except Exception:
        pass

    try:
        from src.xgpedia.providers import quote_free
        monkeypatch.setattr(quote_free, "_download_image_data_uri", lambda *a, **kw: "")
        monkeypatch.setattr(quote_free, "_fetch_og_image_from_article", lambda *a, **kw: "")
        monkeypatch.setattr(quote_free, "_fetch_wikipedia_portrait", lambda *a, **kw: "")
    except Exception:
        pass

    try:
        from src.xgpedia.providers import debate_free
        monkeypatch.setattr(debate_free, "_download_image_data_uri", lambda *a, **kw: "")
        monkeypatch.setattr(debate_free, "_fetch_wikipedia_portrait", lambda *a, **kw: "")
    except Exception:
        pass

    try:
        from src.xgpedia.editorial import llm_provider
        monkeypatch.setattr(llm_provider, "generate_text", lambda *a, **kw: "")
    except Exception:
        pass

    # ۴) مسدودسازی httpx.post و urllib.request.urlopen خارجی (تست‌هایی که خودشان موک می‌کنند بی‌تداخل کار می‌کنند)
    try:
        import httpx

        def _offline_httpx_post(*a, **kw):
            raise RuntimeError("Live httpx.post disabled in unit tests")

        monkeypatch.setattr(httpx, "post", _offline_httpx_post)
    except Exception:
        pass

    _orig_urlopen = urllib.request.urlopen

    def _offline_urlopen(url, *a, **kw):
        u = url.full_url if hasattr(url, "full_url") else str(url)
        if u.startswith(("file://", "http://127.0.0.1", "http://localhost")):
            return _orig_urlopen(url, *a, **kw)
        raise RuntimeError(f"Live external urllib disabled in unit tests: {u[:80]}")

    monkeypatch.setattr(urllib.request, "urlopen", _offline_urlopen)
