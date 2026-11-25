"""تنظیمات مشترک pytest برای XGPedia:
- جلوگیری از درخواست‌های تصادفی شبکه (ویکی‌پدیا / RSS / FPL / LLM آنلاین) در تست‌های واحد تا اجرای
  کل مجموعهٔ تست‌ها بسیار سریع و ۱۰۰٪ پایدار و مستقل از اینترنت باشد.
  تست‌هایی که خودشان `monkeypatch` روی `httpx.post` یا توابع provider می‌زنند، دقیقاً مثل قبل رفتار دلخواه خود را تست می‌کنند.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _block_accidental_live_http_and_llm(monkeypatch):
    from src.xgpedia.providers import live_intel_free as lif

    monkeypatch.setattr(lif, "fetch_live_coach_wikipedia", lambda team, **kw: (None, None))
    monkeypatch.setattr(lif, "fetch_match_breaking_news", lambda h, a, **kw: [])

    # جلوگیری از فراخوانی‌های تصادفی FPL / تصاویر آنلاین / LLM در تست‌های واحد
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

    # مسدودسازی httpx.post زنده (به‌جای OpenAICompatibleLLM._chat) تا تست‌هایی که httpx.post را موک می‌کنند ۱۰۰٪ پاس شوند
    try:
        import httpx

        def _offline_httpx_post(*a, **kw):
            raise RuntimeError("Live httpx.post disabled in unit tests")

        monkeypatch.setattr(httpx, "post", _offline_httpx_post)
    except Exception:
        pass
