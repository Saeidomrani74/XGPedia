"""D30 — retry خطای گذرا در OpenAICompatibleLLM (بدون شبکه).

سناریوی واقعی که این را ضروری کرد (2026-11-21، ویندوز کاربر):
daily → ۵۰۳ و ReadTimeout سرویس LLM → هر دو fixture آن روز FAIL می‌شد؛
حالا هر فراخوانی تا max_attempts با backoff نمایی خودش را تلاش می‌کند و فقط
شکست پایدار (یا خطای گذرا پس از آخرین تلاش) بالا می‌رود تا daily ایزولاهش کند.
"""
import json
from pathlib import Path

import httpx
import pytest

from src.xgpedia.editorial.llm_provider import OpenAICompatibleLLM
from src.xgpedia.normalization.models import MatchFacts

GOOD_CONTENT = json.dumps(
    {
        "status": "ok",
        "title": "تیتر آزمایشی",
        "bullets": [],
        "caption": "متن کپشن",
        "source_note": "",
        "uncertainties": [],
    },
    ensure_ascii=False,
)


class _Resp:
    """پاسخ ساختگی httpx — فقط آنچه _chat لازم دارد."""

    def __init__(self, status_code: int, content: str = GOOD_CONTENT) -> None:
        self.status_code = status_code
        self._content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"Server error '{self.status_code}'", request=None, response=None
            )

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


def _flaky(monkeypatch, calls):
    """httpx.post ساختگی که پاسخ‌ها/خطاهای داده‌شده را یکی‌یکی مصرف می‌کند."""
    seq = iter(calls)

    def fake_post(*args, **kwargs):
        item = next(seq)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(httpx, "post", fake_post)


def _provider(**kwargs):
    sleeps: list[float] = []
    llm = OpenAICompatibleLLM(backoff_seconds=5.0, sleep=sleeps.append, **kwargs)
    return llm, sleeps


@pytest.fixture
def llm_env(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")


def test_readtimeout_then_success(llm_env, monkeypatch):
    """تایم‌اوت روی تلاش ۱ → یک بار backoff → موفقیت (سناریوی واقعی کاربر)."""
    _flaky(monkeypatch, [httpx.ReadTimeout("The read operation timed out"), _Resp(200)])
    llm, sleeps = _provider()
    assert llm._chat([{"role": "user", "content": "x"}]) == GOOD_CONTENT
    assert sleeps == [5.0]


def test_503_then_success(llm_env, monkeypatch):
    """۵۰۳ روی تلاش ۱ → یک بار backoff → موفقیت."""
    _flaky(monkeypatch, [_Resp(503), _Resp(200)])
    llm, sleeps = _provider()
    assert llm._chat([{"role": "user", "content": "x"}]) == GOOD_CONTENT
    assert sleeps == [5.0]


def test_timeout_gives_up_after_max_attempts(llm_env, monkeypatch):
    """تایم‌اوت پایدار → پس از ۳ تلاش همان خطا بالا می‌رود (backoff نمایی 5s، 10s)."""
    _flaky(monkeypatch, [httpx.ReadTimeout("The read operation timed out")] * 3)
    llm, sleeps = _provider(max_attempts=3)
    with pytest.raises(httpx.ReadTimeout):
        llm._chat([{"role": "user", "content": "x"}])
    assert sleeps == [5.0, 10.0]


def test_503_on_last_attempt_raises_http_status(llm_env, monkeypatch):
    """۵۰۳ روی آخرین تلاش → HTTPStatusError (نه حلقهٔ بی‌نهایت، نه پنهان‌کاری)."""
    _flaky(monkeypatch, [_Resp(503), _Resp(503)])
    llm, sleeps = _provider(max_attempts=2)
    with pytest.raises(httpx.HTTPStatusError):
        llm._chat([{"role": "user", "content": "x"}])
    assert sleeps == [5.0]


def test_client_error_no_retry(llm_env, monkeypatch):
    """خطای پایدار ۴xx → بدون retry همان‌جا raise."""
    calls = [_Resp(401)]
    _flaky(monkeypatch, calls + [_Resp(200)])  # اگر نادرست retry کند، تست fail می‌شود
    llm, sleeps = _provider()
    with pytest.raises(httpx.HTTPStatusError):
        llm._chat([{"role": "user", "content": "x"}])
    assert sleeps == []


def test_generate_full_path_with_retry(llm_env, monkeypatch):
    """مسیر کامل generate (parse هم می‌شود) — تایم‌اوت اول، موفقیت دوم."""
    _flaky(monkeypatch, [httpx.ReadTimeout("The read operation timed out"), _Resp(200)])
    llm, sleeps = _provider()
    facts = MatchFacts.model_validate(
        json.loads((Path("data/samples/fact.json")).read_text(encoding="utf-8"))
    )
    draft = llm.generate("SYSTEM", facts)
    assert draft.title == "تیتر آزمایشی"
    assert sleeps == [5.0]


def test_env_overrides_defaults(llm_env, monkeypatch):
    """LLM_MAX_ATTEMPTS / LLM_BACKOFF_SECONDS از env خوانده می‌شوند (تنظیم بدون کد)."""
    monkeypatch.setenv("LLM_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("LLM_BACKOFF_SECONDS", "7")
    llm = OpenAICompatibleLLM(sleep=lambda s: None)
    assert llm.max_attempts == 2
    assert llm.backoff_seconds == 7.0
    monkeypatch.setenv("LLM_MAX_ATTEMPTS", "not-a-number")  # مقدار خراب → پیش‌فرض
    llm2 = OpenAICompatibleLLM(sleep=lambda s: None)
    assert llm2.max_attempts == 3
