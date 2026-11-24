"""آزمون‌های نسخهٔ 0.27.3 — چند کلید/اکانت API، توقف همگام تایم‌اوت (cancel_event)، و رفع خطای status در ترجمه اخبار."""
from __future__ import annotations

import threading

from src.xgpedia.editorial.llm_provider import (
    GEMINI_OPENAI_BASE,
    DraftOutput,
    LLMEndpoint,
    MultiProviderLLM,
    build_free_llm_chain_from_env,
    clear_llm_cooldowns,
)
from src.xgpedia.providers.breaking_news_free import translate_news_item_to_persian


def test_multikey_env_comma_and_numbered_and_single_key_compat(monkeypatch):
    for k in list(monkeypatch._setitem if hasattr(monkeypatch, "_setitem") else ()):
        pass
    for var in (
        "GEMINI_API_KEY", "GEMINI_API_KEY_1", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3",
        "GEMINI_MODEL_CHAIN", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL",
        "POLLINATIONS_API_KEY", "GITHUB_MODELS_TOKEN", "AXFORGE_API_KEY",
        "CEREBRAS_API_KEY", "SAMBANOVA_API_KEY", "GROQ_API_KEY", "GROQ_API_KEY_2",
        "OPENROUTER_API_KEY", "COHERE_API_KEY", "MISTRAL_API_KEY",
        "NVIDIA_API_KEY", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID_2", "CLOUDFLARE_API_TOKEN_2",
        "ZAI_API_KEY", "LLM7_API_KEY", "LLM_ENABLE_ANONYMOUS_FALLBACK",
    ):
        monkeypatch.delenv(var, raising=False)

    monkeypatch.setenv("LLM_ENABLE_ANONYMOUS_FALLBACK", "0")
    monkeypatch.setenv("GEMINI_MODEL_CHAIN", "gemini-4-hydrogen")
    monkeypatch.setenv("GEMINI_API_KEY", "gem_k1, gem_k2")
    monkeypatch.setenv("GEMINI_API_KEY_3", "gem_k3")
    monkeypatch.setenv("GROQ_API_KEY", "groq_single")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acc1")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok1")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID_2", "acc2")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN_2", "tok2")

    chain = build_free_llm_chain_from_env()
    gem_eps = [ep for ep in chain if ep.model == "gemini-4-hydrogen"]
    assert len(gem_eps) == 3
    assert [ep.api_key for ep in gem_eps] == ["gem_k1", "gem_k2", "gem_k3"]
    assert "[K1]" in gem_eps[0].label and "[K3]" in gem_eps[2].label

    # وقتی فقط یک کلید باشد، برچسب بدون [K1] باقی می‌ماند (سازگاری کامل)
    groq_eps = [ep for ep in chain if "Groq" in ep.label]
    assert len(groq_eps) == 3
    assert all("[K1]" not in ep.label for ep in groq_eps)

    # دو اکانت Cloudflare
    cf_eps = [ep for ep in chain if "Cloudflare AI" in ep.label]
    assert len(cf_eps) == 4  # 2 models × 2 accounts
    assert any("acc1" in ep.base_url for ep in cf_eps)
    assert any("acc2" in ep.base_url for ep in cf_eps)


def test_multikey_429_switches_to_second_key_and_404_skips_dead_model(monkeypatch):
    import httpx

    clear_llm_cooldowns()
    calls: list[tuple[str, str]] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        model = json["model"]
        auth = (headers or {}).get("Authorization", "")
        calls.append((model, auth))
        req = httpx.Request("POST", url)
        if model == "dead-model":
            return httpx.Response(404, request=req)
        if model == "good-model" and auth == "Bearer k1":
            return httpx.Response(429, request=req)
        return httpx.Response(
            200,
            request=req,
            json={
                "choices": [{
                    "message": {
                        "content": '{"status":"ok","title":"تیتر","bullets":["نکته ۱"],"caption":"متن","source_note":"","uncertainties":[]}'
                    }
                }]
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    eps = [
        LLMEndpoint("Dead [K1]", GEMINI_OPENAI_BASE, "dead-model", "k1"),
        LLMEndpoint("Dead [K2]", GEMINI_OPENAI_BASE, "dead-model", "k2"),
        LLMEndpoint("Good [K1]", GEMINI_OPENAI_BASE, "good-model", "k1"),
        LLMEndpoint("Good [K2]", GEMINI_OPENAI_BASE, "good-model", "k2"),
    ]
    router = MultiProviderLLM(eps, per_endpoint_attempts=1, start_index=1, cooldown_seconds=60, sleep=lambda _: None)
    out = router.generate("sys", {"fixture_id": "test"})
    assert isinstance(out, DraftOutput)
    assert router.last_used_label == "Good [K2]"
    # dead-model روی K1 خطای 404 داد، پس نباید روی K2 دوباره امتحان شود!
    assert calls == [
        ("dead-model", "Bearer k1"),
        ("good-model", "Bearer k1"),
        ("good-model", "Bearer k2"),
    ]
    clear_llm_cooldowns()


def test_cancel_event_stops_router_immediately(monkeypatch):
    import httpx

    clear_llm_cooldowns()
    ev = threading.Event()
    calls: list[str] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json["model"])
        ev.set()  # شبیه‌سازی اتمام تایم‌اوت ربات حین اولین درخواست
        req = httpx.Request("POST", url)
        return httpx.Response(429, request=req)

    monkeypatch.setattr(httpx, "post", fake_post)

    eps = [
        LLMEndpoint("M1", GEMINI_OPENAI_BASE, "m1", "k1"),
        LLMEndpoint("M2", GEMINI_OPENAI_BASE, "m2", "k2"),
        LLMEndpoint("M3", GEMINI_OPENAI_BASE, "m3", "k3"),
    ]
    router = MultiProviderLLM(eps, per_endpoint_attempts=1, start_index=1, cooldown_seconds=0, sleep=lambda _: None, cancel_event=ev)
    raised = False
    try:
        router.generate("sys", {"fixture_id": "test"})
    except TimeoutError:
        raised = True
    assert raised is True
    assert calls == ["m1"]  # هرگز سراغ m2 و m3 نرفت!


def test_translate_news_prompt_includes_required_status_ok_schema():
    seen_prompts: list[str] = []

    class _CaptureLLM:
        def __init__(self):
            self.cancel_event = None

        def generate(self, sys_prompt, payload):
            seen_prompts.append(sys_prompt)
            return DraftOutput.from_json(
                '{"status":"ok","title":"شروع سخت *پوچتینو* در اولدترافورد",'
                '"caption":"سرمربی جدید منچستریونایتد هفتهٔ پرتنشی را پشت سر گذاشت.",'
                '"bullets":["آغاز دشوار در لیگ برتر"],'
                '"source_note":"گزارش زنده BBC Sport","uncertainties":[]}'
            )

    ev = threading.Event()
    llm = _CaptureLLM()
    res = translate_news_item_to_persian(
        {
            "id": "bbc_1",
            "lang": "en",
            "headline": "Chaotic week, nightmare start for Pochettino",
            "lead": "Mauricio Pochettino's reign as Manchester United boss had a tough start.",
            "source": "BBC Sport",
        },
        llm_provider=llm,
        cancel_event=ev,
    )
    assert llm.cancel_event is ev
    assert seen_prompts and '"status": "ok"' in seen_prompts[0] and '"uncertainties"' in seen_prompts[0]
    assert res["lang"] == "fa"
    assert "پوچتینو" in res["headline"]
