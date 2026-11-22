"""لایهٔ ۴ — Editorial: interface عمومی LLMProvider + روتر پشتیبان چندارائه‌دهندهٔ رایگان (v0.17.0).

قواعد (بخش ۸ سند):
  - مدل زبانی فقط متن می‌نویسد؛ عدد، نام، شناسهٔ منبع و timestamp همیشه از کد.
  - ترتیب اولویت پیش‌فرض Gemini:
      1) gemini-4-hydrogen
      2) gemini-4-neon
      3) gemini-3.8-flash
      + پشتیبان‌های Gemini: gemini-3.6-flash → gemini-3.5-flash-lite → gemini-2.5-flash
  - پشتیبان‌های رایگان با کیفیت فارسی بالا (در صورت تنظیم کلید در .env):
      Groq (qwen/qwen3.8-27b) → OpenRouter (gemma-4-31b-it:free) → Cohere (Aya/Command A)
      → Mistral AI → NVIDIA NIM → Cloudflare Workers AI → Z.ai (GLM-4.7-Flash)
  - پشتیبان‌های اضطراری بدون نیاز به کلید (OVHcloud Qwen3.5-397B، Kilo Code، LLM7.io)
    تا خطای 429/503 هرگز تولید پست را متوقف نکند.
"""
from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from src.xgpedia.normalization.models import MatchFacts

GEMINI_OPENAI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"

# ترتیب اولویت دقیق درخواستی کاربر + پشتیبان‌های رایگان Gemini
DEFAULT_GEMINI_CHAIN: tuple[str, ...] = (
    "gemini-4-hydrogen",
    "gemini-4-neon",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
)


class LLMProvider(Protocol):
    def generate(self, system_prompt: str, user_payload: dict) -> "DraftOutput": ...


@dataclass
class DraftOutput:
    """خروجی مجاز مدل — فقط این کلیدها؛ validator هر چیز دیگر را رد می‌کند."""

    status: str                      # "ok" | "insufficient_data"
    title: str
    bullets: list[str]               # حداکثر ۳؛ هر یک: یک عدد + n
    caption: str                    # حداکثر ۷۰۰ کاراکتر
    source_note: str
    uncertainties: list[str]

    @classmethod
    def from_json(cls, raw: str) -> "DraftOutput":
        cleaned = _strip_code_fence(raw)
        d = json.loads(cleaned)
        if not isinstance(d, dict):
            raise ValueError("model output is not a JSON object")
        unknown = set(d) - {"status", "title", "bullets", "caption", "source_note", "uncertainties"}
        if unknown:
            raise ValueError(f"unexpected keys in model output: {unknown}")
        if d.get("status") not in {"ok", "insufficient_data"}:
            raise ValueError("invalid status value")
        return cls(
            status=d["status"],
            title=d["title"],
            bullets=list(d.get("bullets", []))[:3],
            caption=d.get("caption", "")[:700],
            source_note=d.get("source_note", ""),
            uncertainties=list(d.get("uncertainties", [])),
        )


def _strip_code_fence(raw: str) -> str:
    """حذف ```json ... ``` و متن اضافهٔ بیرون آبجکت JSON."""
    t = raw.strip()
    if t.startswith("```"):
        first_nl = t.find("\n")
        if first_nl != -1:
            t = t[first_nl + 1:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    t = t.strip()
    if not t.startswith("{"):
        start = t.find("{")
        end = t.rfind("}")
        if start != -1 and end != -1 and end > start:
            t = t[start:end + 1]
    return t.strip()


TRANSIENT_STATUS = frozenset({429, 500, 502, 503, 504})
# کدهایی که در روتر چندمدلی باعث سوییچ فوری به مدل/ارائه‌دهندهٔ بعدی می‌شوند
FAILOVER_STATUS = frozenset({400, 401, 402, 403, 404, 429, 500, 502, 503, 504})


def _env_number(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    try:
        return float(raw)
    except ValueError:
        return default


def _build_messages(
    system_prompt: str,
    facts: MatchFacts,
    repair_feedback: str = "",
    previous_raw: str = "",
    edit_instruction: str = "",
    current_draft_json: str = "",
) -> list[dict]:
    payload = facts.model_dump(mode="json")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    if edit_instruction:
        if current_draft_json:
            messages.append({"role": "assistant", "content": current_draft_json})
        messages.append({
            "role": "user",
            "content": (
                "نسخهٔ فعلی متن تحریریه را طبق دستور سردبیر بازنویسی کن. "
                "همهٔ اعداد و نام تیم‌ها باید دقیقاً مطابق JSON واقعیت‌ها بمانند "
                "و خروجی فقط یک JSON معتبر با کلیدهای مجاز باشد.\n"
                f"دستور ویرایش سردبیر: {edit_instruction}"
            ),
        })
    if repair_feedback:
        messages.append({"role": "assistant", "content": previous_raw or "{}"})
        messages.append({"role": "user", "content": REPAIR_PREFIX + repair_feedback})
    return messages


class OpenAICompatibleLLM:
    """کلاینت عمومی سازگار با OpenAI — پشت همان interface؛ قابل تعویض با یک خط env."""

    name = "openai_compatible"

    def __init__(
        self,
        max_attempts: int | None = None,
        backoff_seconds: float | None = None,
        sleep: Callable[[float], None] | None = None,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        require_auth: bool = True,
        extra_headers: dict[str, str] | None = None,
        supports_json_mode: bool = True,
        timeout: float = 45.0,
    ) -> None:
        if base_url is None or model is None or (require_auth and api_key is None):
            missing = [
                k for k, v in (
                    ("LLM_BASE_URL", base_url or os.environ.get("LLM_BASE_URL")),
                    ("LLM_API_KEY", api_key if not require_auth else (api_key or os.environ.get("LLM_API_KEY"))),
                    ("LLM_MODEL", model or os.environ.get("LLM_MODEL")),
                ) if (k != "LLM_API_KEY" or require_auth) and not v
            ]
            if missing:
                raise RuntimeError(
                    f"missing env: {', '.join(missing)} - set them in .env "
                    f"(see .env.example); this adapter needs an OpenAI-compatible API key"
                )
        self.base_url = (base_url or os.environ["LLM_BASE_URL"]).rstrip("/")
        self.api_key = (api_key if api_key is not None else os.environ.get("LLM_API_KEY", "")).strip()
        self.model = (model or os.environ["LLM_MODEL"]).strip()
        self.require_auth = require_auth
        self.extra_headers = dict(extra_headers or {})
        self.supports_json_mode = supports_json_mode
        self.timeout = timeout
        self.max_attempts = max(1, int(
            max_attempts if max_attempts is not None else _env_number("LLM_MAX_ATTEMPTS", 3)
        ))
        self.backoff_seconds = max(0.0, float(
            backoff_seconds if backoff_seconds is not None
            else _env_number("LLM_BACKOFF_SECONDS", 5.0)
        ))
        self._sleep = sleep or time.sleep

    def generate(
        self, system_prompt: str, facts: MatchFacts, repair_feedback: str = "",
        previous_raw: str = "", edit_instruction: str = "", current_draft_json: str = "",
    ) -> DraftOutput:
        messages = _build_messages(
            system_prompt, facts,
            repair_feedback=repair_feedback,
            previous_raw=previous_raw,
            edit_instruction=edit_instruction,
            current_draft_json=current_draft_json,
        )
        return DraftOutput.from_json(self._chat(messages))

    def _chat(self, messages: list[dict]) -> str:
        import httpx

        headers = dict(self.extra_headers)
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        body: dict = {"model": self.model, "messages": messages}
        if self.supports_json_mode:
            body["response_format"] = {"type": "json_object"}

        for attempt in range(1, self.max_attempts + 1):
            is_last = attempt == self.max_attempts
            try:
                resp = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=body,
                    timeout=self.timeout,
                )
            except httpx.TransportError as e:
                if is_last:
                    raise
                reason = type(e).__name__
            else:
                if resp.status_code not in TRANSIENT_STATUS:
                    resp.raise_for_status()
                    return resp.json()["choices"][0]["message"]["content"]
                if is_last:
                    resp.raise_for_status()
                reason = f"HTTP {resp.status_code}"
            wait = self.backoff_seconds * (2 ** (attempt - 1))
            print(
                f"[llm] transient error ({reason})"
                f" - retry {attempt + 1}/{self.max_attempts} in {wait:.0f}s"
            )
            self._sleep(wait)
        raise AssertionError("unreachable - last attempt always returns or raises")


@dataclass
class LLMEndpoint:
    """مشخصات یک نقطهٔ اتصال در زنجیرهٔ پشتیبان چندارائه‌دهنده."""

    label: str
    base_url: str
    model: str
    api_key: str = ""
    require_auth: bool = True
    supports_json_mode: bool = True
    extra_headers: dict[str, str] = field(default_factory=dict)


def build_free_llm_chain_from_env() -> list[LLMEndpoint]:
    """ساخت لیست اولویت‌بندی‌شدهٔ مدل‌ها و ارائه‌دهندگان رایگان از روی .env.

    ترتیب اولویت:
      1) زنجیرهٔ Gemini (ابتدا gemini-4-hydrogen، سپس gemini-4-neon، سپس gemini-3.8-flash و پشتیبان‌های Flash)
      2) ارائه‌دهندهٔ اصلی دلخواه کاربر در LLM_BASE_URL (اگر غیر از Gemini باشد)
      3) پشتیبان‌های رایگان باکیفیت برای فارسی (در صورت تنظیم کلید در .env):
         Groq → OpenRouter → Cohere → Mistral → NVIDIA NIM → Cloudflare → Z.ai
      4) پشتیبان‌های اضطراری بدون نیاز به کلید (OVHcloud Qwen3.5-397B، Kilo Code، LLM7.io)
    """
    chain: list[LLMEndpoint] = []
    seen: set[tuple[str, str]] = set()

    def _add(ep: LLMEndpoint) -> None:
        key = (ep.base_url.rstrip("/"), ep.model)
        if key not in seen:
            seen.add(key)
            chain.append(ep)

    llm_base = (os.environ.get("LLM_BASE_URL") or "").strip().rstrip("/")
    llm_key = (os.environ.get("LLM_API_KEY") or "").strip()
    llm_model = (os.environ.get("LLM_MODEL") or "").strip()

    # ۱) کلید Gemini (یا از GEMINI_API_KEY یا از LLM_API_KEY وقتی base_url مربوط به Google باشد)
    gemini_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not gemini_key and llm_key and "generativelanguage.googleapis.com" in llm_base:
        gemini_key = llm_key

    if gemini_key:
        raw_models = (os.environ.get("GEMINI_MODEL_CHAIN") or "").strip()
        if raw_models:
            g_models = [m.strip() for m in raw_models.split(",") if m.strip()]
        else:
            g_models = list(DEFAULT_GEMINI_CHAIN)
        # اگر کاربر در LLM_MODEL مدل دیگری روی Gemini گذاشته، پس از اولویت اصلی اضافه شود
        if llm_model and "generativelanguage.googleapis.com" in llm_base and llm_model not in g_models:
            g_models.append(llm_model)
        g_base = GEMINI_OPENAI_BASE
        for gm in g_models:
            _add(LLMEndpoint(label=f"Google Gemini ({gm})", base_url=g_base, model=gm, api_key=gemini_key))

    # ۲) اگر کاربر یک LLM_BASE_URL غیر از Gemini تنظیم کرده (مثلاً DeepSeek/OpenAI/Ollama)
    if llm_base and llm_model and "generativelanguage.googleapis.com" not in llm_base:
        _add(LLMEndpoint(
            label=f"Primary ({llm_model})",
            base_url=llm_base,
            model=llm_model,
            api_key=llm_key,
            require_auth=bool(llm_key),
        ))

    # ۳) پشتیبان‌های رایگان با کلید API (به‌ترتیب کیفیت فارسی + سقف رایگان بالا)
    polli_key = (os.environ.get("POLLINATIONS_API_KEY") or "").strip()
    if polli_key:
        for pm in ("openai", "mistral", "gemini-3-flash"):
            _add(LLMEndpoint(
                label=f"Pollinations ({pm})",
                base_url="https://gen.pollinations.ai/v1",
                model=pm,
                api_key=polli_key,
                supports_json_mode=False,
            ))

    gh_tok = (os.environ.get("GITHUB_MODELS_TOKEN") or "").strip()
    if gh_tok:
        for ghm in ("meta/Llama-3.3-70B-Instruct", "cohere/cohere-command-a", "deepseek/DeepSeek-V3-0324"):
            _add(LLMEndpoint(
                label=f"GitHub Models ({ghm})",
                base_url="https://models.github.ai/inference",
                model=ghm,
                api_key=gh_tok,
                supports_json_mode=False,
            ))

    ax_key = (os.environ.get("AXFORGE_API_KEY") or "").strip()
    if ax_key:
        for axm in ("qwen3.8-27b", "glm-5.3-flash"):
            _add(LLMEndpoint(
                label=f"AxForge EU ({axm})",
                base_url="https://api.axforge.ai/v1",
                model=axm,
                api_key=ax_key,
            ))

    cer_key = (os.environ.get("CEREBRAS_API_KEY") or "").strip()
    if cer_key:
        for cm in ("qwen-3-32b", "llama-3.3-70b"):
            _add(LLMEndpoint(
                label=f"Cerebras ({cm})",
                base_url="https://api.cerebras.ai/v1",
                model=cm,
                api_key=cer_key,
            ))

    samba_key = (os.environ.get("SAMBANOVA_API_KEY") or "").strip()
    if samba_key:
        for sm in ("Meta-Llama-3.3-70B-Instruct", "Qwen2.5-72B-Instruct"):
            _add(LLMEndpoint(
                label=f"SambaNova ({sm})",
                base_url="https://api.sambanova.ai/v1",
                model=sm,
                api_key=samba_key,
            ))

    groq_key = (os.environ.get("GROQ_API_KEY") or "").strip()
    if groq_key:
        for gm in ("qwen/qwen3.8-27b", "openai/gpt-oss-120b", "llama-3.3-70b-versatile"):
            _add(LLMEndpoint(
                label=f"Groq ({gm})",
                base_url="https://api.groq.com/openai/v1",
                model=gm,
                api_key=groq_key,
            ))

    or_key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if or_key:
        or_headers = {"HTTP-Referer": "https://xgpedia.local", "X-Title": "XGPedia"}
        for om in (
            "google/gemma-4-31b-it:free",
            "google/gemma-4-26b-a4b-it:free",
            "nvidia/nemotron-3-ultra-550b-a55b:free",
            "openrouter/free",
        ):
            _add(LLMEndpoint(
                label=f"OpenRouter ({om})",
                base_url="https://openrouter.ai/api/v1",
                model=om,
                api_key=or_key,
                extra_headers=or_headers,
                supports_json_mode=False,
            ))

    cohere_key = (os.environ.get("COHERE_API_KEY") or "").strip()
    if cohere_key:
        for cm in ("command-a-03-2025", "c4ai-aya-expanse-32b"):
            _add(LLMEndpoint(
                label=f"Cohere ({cm})",
                base_url="https://api.cohere.ai/compatibility/v1",
                model=cm,
                api_key=cohere_key,
                supports_json_mode=False,
            ))

    mistral_key = (os.environ.get("MISTRAL_API_KEY") or "").strip()
    if mistral_key:
        for mm in ("mistral-medium-3-5-128b", "mistral-small-latest"):
            _add(LLMEndpoint(
                label=f"Mistral ({mm})",
                base_url="https://api.mistral.ai/v1",
                model=mm,
                api_key=mistral_key,
            ))

    nvidia_key = (os.environ.get("NVIDIA_API_KEY") or "").strip()
    if nvidia_key:
        for nm in ("z-ai/glm-5.3-flash", "nvidia/nemotron-3-ultra-550b-a55b"):
            _add(LLMEndpoint(
                label=f"NVIDIA NIM ({nm})",
                base_url="https://integrate.api.nvidia.com/v1",
                model=nm,
                api_key=nvidia_key,
                supports_json_mode=False,
            ))

    cf_acc = (os.environ.get("CLOUDFLARE_ACCOUNT_ID") or "").strip()
    cf_tok = (os.environ.get("CLOUDFLARE_API_TOKEN") or "").strip()
    if cf_acc and cf_tok:
        cf_base = f"https://api.cloudflare.com/client/v4/accounts/{cf_acc}/ai/v1"
        for cfm in ("@cf/google/gemma-4-26b-a4b-it", "@cf/meta/llama-3.3-70b-instruct-fp8-fast"):
            _add(LLMEndpoint(
                label=f"Cloudflare AI ({cfm})",
                base_url=cf_base,
                model=cfm,
                api_key=cf_tok,
                supports_json_mode=False,
            ))

    zai_key = (os.environ.get("ZAI_API_KEY") or "").strip()
    if zai_key:
        _add(LLMEndpoint(
            label="Z.ai (glm-4.7-flash)",
            base_url="https://api.z.ai/api/paas/v4",
            model="glm-4.7-flash",
            api_key=zai_key,
            supports_json_mode=False,
        ))

    # ۴) پشتیبان‌های اضطراری بدون نیاز به کلید/ثبت‌نام (قابل غیرفعال‌سازی با LLM_ENABLE_ANONYMOUS_FALLBACK=0)
    anon_flag = (os.environ.get("LLM_ENABLE_ANONYMOUS_FALLBACK", "1") or "1").strip().lower()
    if anon_flag not in {"0", "false", "no", "off"}:
        _add(LLMEndpoint(
            label="OVHcloud Free (Qwen3.5-397B-A17B)",
            base_url="https://oai.endpoints.kepler.ai.cloud.ovh.net/v1",
            model="Qwen3.5-397B-A17B",
            api_key="",
            require_auth=False,
            supports_json_mode=False,
        ))
        _add(LLMEndpoint(
            label="OVHcloud Free (Qwen3.8-27B)",
            base_url="https://oai.endpoints.kepler.ai.cloud.ovh.net/v1",
            model="Qwen3.8-27B",
            api_key="",
            require_auth=False,
            supports_json_mode=False,
        ))
        _add(LLMEndpoint(
            label="Kilo Code Free (kilo-auto/free)",
            base_url="https://api.kilo.ai/api/gateway",
            model="kilo-auto/free",
            api_key="",
            require_auth=False,
            supports_json_mode=False,
        ))
        llm7_tok = (os.environ.get("LLM7_API_KEY") or "").strip()
        _add(LLMEndpoint(
            label="LLM7.io Free (gpt-oss:20b)",
            base_url="https://api.llm7.io/v1",
            model="gpt-oss:20b",
            api_key=llm7_tok,
            require_auth=False,
            supports_json_mode=False,
        ))

    skip_raw = (os.environ.get("LLM_SKIP_MODELS") or "").strip()
    if skip_raw:
        skip_set = {m.strip().lower() for m in skip_raw.split(",") if m.strip()}
        filtered = [ep for ep in chain if ep.model.lower() not in skip_set]
        if filtered:
            chain = filtered

    return chain


# کش موقت حافظه‌ای برای عبور فوری از مدل‌هایی که اخیراً 429/503/Timeout داده‌اند (پیش‌فرض ۱۵ دقیقه)
_ENDPOINT_COOLDOWN_UNTIL: dict[tuple[str, str], float] = {}
_LLM_START_CACHE_KEY = "setting:llm_start_index"


def get_llm_start_index() -> int:
    """شمارهٔ مدل شروع زنجیرهٔ LLM (۱-مبنا) — ابتدا از تنظیمات دیتابیس، سپس LLM_START_INDEX در .env."""
    try:
        from src.xgpedia.db import db, init_db
        init_db()
        with db() as conn:
            row = conn.execute(
                "SELECT summary FROM sync_cache WHERE source_key = ?",
                (_LLM_START_CACHE_KEY,),
            ).fetchone()
            if row and row["summary"]:
                val = int(str(row["summary"]).strip())
                if val >= 1:
                    return val
    except Exception:
        pass
    raw = (os.environ.get("LLM_START_INDEX") or "1").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 1


def set_llm_start_index(index_1based: int) -> int:
    """ذخیرهٔ دائمی شمارهٔ مدل شروع زنجیرهٔ LLM در دیتابیس (بدون نیاز به ویرایش دستی .env)."""
    val = max(1, int(index_1based))
    from datetime import datetime, timezone
    from src.xgpedia.db import db, init_db

    init_db()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with db() as conn:
        conn.execute(
            """
            INSERT INTO sync_cache (source_key, tehran_date, last_synced_at, summary)
            VALUES (?, 'global', ?, ?)
            ON CONFLICT(source_key) DO UPDATE SET
              last_synced_at=excluded.last_synced_at,
              summary=excluded.summary
            """,
            (_LLM_START_CACHE_KEY, now_iso, str(val)),
        )
    return val


def clear_llm_cooldowns() -> None:
    """پاک‌سازی کش موقت خطاهای 429/503 مدل‌ها."""
    _ENDPOINT_COOLDOWN_UNTIL.clear()


class MultiProviderLLM:
    """روتر هوشمند چندمدلی/چندارائه‌دهنده با سوییچ سریع روی 429/503/timeout/403."""

    name = "multi_provider_router"

    def __init__(
        self,
        endpoints: list[LLMEndpoint] | None = None,
        *,
        per_endpoint_attempts: int = 1,
        backoff_seconds: float = 2.0,
        timeout: float | None = None,
        start_index: int | None = None,
        cooldown_seconds: float | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.endpoints = list(endpoints) if endpoints is not None else build_free_llm_chain_from_env()
        if not self.endpoints:
            raise RuntimeError(
                "No LLM provider configured - set GEMINI_API_KEY or GROQ_API_KEY or LLM_API_KEY in .env"
            )
        self.per_endpoint_attempts = max(1, per_endpoint_attempts)
        self.backoff_seconds = backoff_seconds
        self.timeout = float(timeout) if timeout is not None else _env_number("LLM_TIMEOUT_SECONDS", 22.0)
        self.start_index = start_index
        self.cooldown_seconds = (
            float(cooldown_seconds)
            if cooldown_seconds is not None
            else _env_number("LLM_COOLDOWN_SECONDS", 900.0)
        )
        self._sleep = sleep or time.sleep
        self.last_used_label: str = ""

    def _ordered_endpoints(self) -> list[tuple[int, LLMEndpoint]]:
        """ترتیب اجرای مدل‌ها از روی start_index (مدل‌های قبل از start_index فقط در انتها به‌عنوان پشتیبان اضطراری می‌آیند)."""
        start_1 = self.start_index if self.start_index is not None else get_llm_start_index()
        n = len(self.endpoints)
        s_idx = min(max(1, start_1), n) - 1
        indexed = list(enumerate(self.endpoints, 1))
        primary_slice = indexed[s_idx:]
        earlier_slice = indexed[:s_idx]
        now = time.monotonic()
        healthy: list[tuple[int, LLMEndpoint]] = []
        cooling: list[tuple[int, LLMEndpoint]] = []
        for idx, ep in primary_slice:
            key = (ep.base_url.rstrip("/"), ep.model)
            if _ENDPOINT_COOLDOWN_UNTIL.get(key, 0.0) > now:
                cooling.append((idx, ep))
            else:
                healthy.append((idx, ep))
        return healthy + cooling + earlier_slice

    def generate(
        self,
        system_prompt: str,
        facts: MatchFacts,
        repair_feedback: str = "",
        previous_raw: str = "",
        edit_instruction: str = "",
        current_draft_json: str = "",
    ) -> DraftOutput:
        errors: list[str] = []
        for idx, ep in self._ordered_endpoints():
            client = OpenAICompatibleLLM(
                max_attempts=self.per_endpoint_attempts,
                backoff_seconds=self.backoff_seconds,
                sleep=self._sleep,
                base_url=ep.base_url,
                api_key=ep.api_key,
                model=ep.model,
                require_auth=ep.require_auth,
                extra_headers=ep.extra_headers,
                supports_json_mode=ep.supports_json_mode,
                timeout=self.timeout,
            )
            key = (ep.base_url.rstrip("/"), ep.model)
            try:
                out = client.generate(
                    system_prompt,
                    facts,
                    repair_feedback=repair_feedback,
                    previous_raw=previous_raw,
                    edit_instruction=edit_instruction,
                    current_draft_json=current_draft_json,
                )
                _ENDPOINT_COOLDOWN_UNTIL.pop(key, None)
                self.last_used_label = ep.label
                print(f"[llm-router] success via #{idx} {ep.label}")
                return out
            except Exception as e:
                short_err = f"{type(e).__name__}: {str(e)[:120]}"
                if self.cooldown_seconds > 0 and any(
                    tok in short_err for tok in ("429", "503", "Timeout", "502", "504")
                ):
                    _ENDPOINT_COOLDOWN_UNTIL[key] = time.monotonic() + self.cooldown_seconds
                errors.append(f"{ep.label} -> {short_err}")
                print(f"[llm-router] #{idx} {ep.label} failed ({short_err}) - switching to next")
                continue

        raise RuntimeError(
            "همهٔ مدل‌ها و ارائه‌دهندگان زنجیرهٔ LLM ناموفق بودند:\n" + "\n".join(f"• {x}" for x in errors[:8])
        )


def build_default_llm() -> LLMProvider:
    """ساخت روتر پیش‌فرض از .env (در صورت وجود کلید یا پشتیبان رایگان، MultiProviderLLM برمی‌گرداند)."""
    chain = build_free_llm_chain_from_env()
    if chain:
        return MultiProviderLLM(chain)
    return OpenAICompatibleLLM()


REPAIR_PREFIX = (
    "پیش‌نویس قبلی توسط validator رد شد. پیش‌نویس ردشده بالا است. "
    "خطاهای validator عیناً:\n"
)


class FallbackChain:
    """provider اصلی + fallback — شکست ساختاری/schema از دومی، خطای شبکه retry یک‌بار."""

    def __init__(self, primary: LLMProvider, secondary: LLMProvider) -> None:
        self.primary = primary
        self.secondary = secondary

    def generate(self, system_prompt: str, facts: MatchFacts) -> DraftOutput:
        try:
            return self.primary.generate(system_prompt, facts)
        except Exception:
            return self.secondary.generate(system_prompt, facts)
