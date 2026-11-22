"""آزمون‌های نسخهٔ 0.17.0 — زنجیرهٔ پشتیبان چندارائه‌دهندهٔ رایگان LLM، تصویر و ویدیو."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from src.xgpedia.editorial.llm_provider import (
    DEFAULT_GEMINI_CHAIN,
    GEMINI_OPENAI_BASE,
    DraftOutput,
    LLMEndpoint,
    MultiProviderLLM,
    build_free_llm_chain_from_env,
)
from src.xgpedia.media.free_media import FreeImageRouter, FreeVideoRouter


def test_default_gemini_priority_order():
    assert DEFAULT_GEMINI_CHAIN[:3] == (
        "gemini-4-hydrogen",
        "gemini-4-neon",
        "gemini-3.8-flash",
    )


def test_build_free_llm_chain_from_env_priority_and_backups(monkeypatch):
    for k in (
        "GEMINI_API_KEY", "GEMINI_MODEL_CHAIN", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL",
        "POLLINATIONS_API_KEY", "GITHUB_MODELS_TOKEN", "AXFORGE_API_KEY", "CEREBRAS_API_KEY", "SAMBANOVA_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "COHERE_API_KEY", "MISTRAL_API_KEY",
        "NVIDIA_API_KEY", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "ZAI_API_KEY",
        "LLM7_API_KEY", "LLM_ENABLE_ANONYMOUS_FALLBACK",
    ):
        monkeypatch.delenv(k, raising=False)

    monkeypatch.setenv("GEMINI_API_KEY", "fake-gem-key")
    monkeypatch.setenv("GROQ_API_KEY", "fake-groq-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-or-key")
    monkeypatch.setenv("COHERE_API_KEY", "fake-coh-key")

    chain = build_free_llm_chain_from_env()
    models = [ep.model for ep in chain]

    # ترتیب دقیق ۳ اولویت اول کاربر روی آدرس رسمی OpenAI-compatible گوگل
    assert models[0] == "gemini-4-hydrogen"
    assert models[1] == "gemini-4-neon"
    assert models[2] == "gemini-3.8-flash"
    assert chain[0].base_url == GEMINI_OPENAI_BASE

    # پشتیبان‌های فارسی‌دان رایگان و پشتیبان‌های بدون کلید در ادامهٔ زنجیره
    assert "qwen/qwen3.8-27b" in models
    assert "google/gemma-4-31b-it:free" in models
    assert "c4ai-aya-expanse-32b" in models
    assert "Qwen3.5-397B-A17B" in models
    assert models.index("gemini-3.8-flash") < models.index("qwen/qwen3.8-27b")
    assert models.index("qwen/qwen3.8-27b") < models.index("Qwen3.5-397B-A17B")


def test_multi_provider_router_fails_over_on_429_and_503(monkeypatch):
    import httpx

    calls: list[str] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        model = json["model"]
        calls.append(model)
        req = httpx.Request("POST", url)
        if model == "gemini-4-hydrogen":
            return httpx.Response(429, request=req)
        if model == "gemini-4-neon":
            return httpx.Response(503, request=req)
        return httpx.Response(
            200,
            request=req,
            json={
                "choices": [{
                    "message": {
                        "content": '{"status":"ok","title":"تیتر تست","bullets":["نکته ۱"],"caption":"کپشن تست","source_note":"","uncertainties":[]}'
                    }
                }]
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    endpoints = [
        LLMEndpoint("G1", GEMINI_OPENAI_BASE, "gemini-4-hydrogen", "k"),
        LLMEndpoint("G2", GEMINI_OPENAI_BASE, "gemini-4-neon", "k"),
        LLMEndpoint("G3", GEMINI_OPENAI_BASE, "gemini-3.8-flash", "k"),
    ]
    router = MultiProviderLLM(endpoints, per_endpoint_attempts=1, start_index=1, cooldown_seconds=0, sleep=lambda _: None)

    class _FakeFacts:
        def model_dump(self, mode="json"):
            return {"fixture_id": "test:1"}

    out = router.generate("sys", _FakeFacts())
    assert isinstance(out, DraftOutput)
    assert out.title == "تیتر تست"
    assert calls == ["gemini-4-hydrogen", "gemini-4-neon", "gemini-3.8-flash"]
    assert router.last_used_label == "G3"


def test_free_media_routers_available_providers(monkeypatch):
    for k in ("POLLINATIONS_API_KEY", "NVIDIA_API_KEY", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "REPLICATE_API_TOKEN", "TOGETHER_API_KEY", "STABILITY_API_KEY", "HF_TOKEN"):
        monkeypatch.delenv(k, raising=False)

    img_r = FreeImageRouter()
    # حتی بدون هیچ کلیدی، Pollinations FLUX همیشه فعال است
    assert img_r.available_providers() == ["pollinations_flux"]

    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acc")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    monkeypatch.setenv("REPLICATE_API_TOKEN", "rep")
    assert img_r.available_providers() == ["cloudflare_flux", "replicate_flux", "pollinations_flux"]

    vid_r = FreeVideoRouter()
    assert "replicate_wan" in vid_r.available_providers()


def test_pollinations_and_github_models_wired_across_text_image_video(monkeypatch):
    for k in (
        "GEMINI_API_KEY", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL",
        "POLLINATIONS_API_KEY", "GITHUB_MODELS_TOKEN", "AXFORGE_API_KEY",
        "NVIDIA_API_KEY", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN",
        "REPLICATE_API_TOKEN", "STABILITY_API_KEY", "HF_TOKEN",
    ):
        monkeypatch.delenv(k, raising=False)

    monkeypatch.setenv("POLLINATIONS_API_KEY", "pk_test")
    monkeypatch.setenv("GITHUB_MODELS_TOKEN", "ghp_test")
    monkeypatch.setenv("AXFORGE_API_KEY", "ax_test")
    monkeypatch.setenv("NVIDIA_API_KEY", "nv_test")

    chain = build_free_llm_chain_from_env()
    labels = [ep.label for ep in chain]
    assert any("Pollinations" in x for x in labels)
    assert any("GitHub Models" in x for x in labels)
    assert any("AxForge EU" in x for x in labels)

    img_provs = FreeImageRouter().available_providers()
    assert img_provs[0] == "pollinations_auth_flux"
    assert "nvidia_nim_flux" in img_provs

    vid_provs = FreeVideoRouter().available_providers()
    assert vid_provs[0] == "pollinations_video"
