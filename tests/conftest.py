"""تنظیمات مشترک pytest برای XGPedia:
- ایزوله‌سازی کامل توکن‌ها/نشست‌های X و Instagram در `tmp_path` (بدون نوشتن در ریشهٔ ریپو)
- تضمین وجود فیکسچر `data/samples/fact.json` از روی `tests/fixtures/fact.json` در checkout تمیز
- ایزوله‌سازی کامل حافظهٔ سلامت APIها (`api_health`) در حالت حافظه (بدون نوشتن روی دیسک)
- مسدودسازی درخواست‌های تصادفی شبکه (ویکی‌پدیا / RSS / FPL / LLM آنلاین / urllib خارجی)
  در تست‌های واحد تا کل مجموعهٔ تست‌ها سریع، یکدست و ۱۰۰٪ مستقل از اینترنت باشد.
"""
from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_FIXTURE_FACT = _REPO_ROOT / "tests" / "fixtures" / "fact.json"
_SAMPLE_FACT = _REPO_ROOT / "data" / "samples" / "fact.json"


@pytest.fixture(scope="session", autouse=True)
def _ensure_sample_fact_fixture():
    """در checkout تمیز که پوشهٔ data/ وجود ندارد، فیکسچر fact.json را از tests/fixtures/ کپی می‌کند."""
    created = False
    if not _SAMPLE_FACT.exists() and _FIXTURE_FACT.exists():
        _SAMPLE_FACT.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_FIXTURE_FACT, _SAMPLE_FACT)
        created = True
    yield
    if created and _SAMPLE_FACT.exists():
        try:
            _SAMPLE_FACT.unlink()
        except OSError:
            pass


@pytest.fixture(autouse=True)
def _block_accidental_live_http_and_llm(monkeypatch, tmp_path):
    # ۰) ایزوله‌سازی فایل‌های توکن واقعی کاربر (X / Instagram) درون tmp_path تا هرگز در ریشهٔ ریپو نشت نکنند
    try:
        from src.xgpedia.publishers import x_oauth, omnichannel
        monkeypatch.setattr(x_oauth, "X_TOKEN_STORE", tmp_path / "test_x_tokens.json")
        monkeypatch.setattr(omnichannel, "IG_SESSION_FILE", tmp_path / "test_ig_session.json")
    except Exception:
        pass

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

    # ۴) مسدودسازی httpx.post و urllib.request.urlopen خارجی
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


def require_chromium() -> None:
    """در صورت نصب‌نبودن باینری Chromium، تست رندر را تمیز skip می‌کند (به‌جای کرش در محیط تمیز)."""
    pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")
    try:
        with pw.sync_playwright() as p:
            exe = Path(p.chromium.executable_path)
            if not exe.exists():
                pytest.skip(f"Playwright Chromium binary not installed at {exe}")
    except Exception as exc:
        pytest.skip(f"Playwright Chromium unavailable: {exc}")
