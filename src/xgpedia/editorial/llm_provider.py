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

import hashlib
import json
import os
import re
import threading
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
    payload = facts if isinstance(facts, dict) else facts.model_dump(mode="json")
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


def _key_hash(api_key: str) -> str:
    """هش کوتاه کلید برای تفکیک کول‌داون و جلوگیری از تکرار بدون افشای کلید در لاگ."""
    k = (api_key or "").strip()
    if not k:
        return "anon"
    return hashlib.sha1(k.encode("utf-8")).hexdigest()[:10]


def _env_keys(var_name: str, extra_single: str = "") -> list[str]:
    """استخراج چند کلید API برای یک ارائه‌دهنده از .env.

    هر دو روش زیر پشتیبانی می‌شوند (و قابل ترکیب هستند):
      1) جداشده با کاما یا سمی‌کالن:  GEMINI_API_KEY=key1,key2,key3
      2) متغیرهای شماره‌دار:         GEMINI_API_KEY_2=key2  ...  GEMINI_API_KEY_20=key20
    """
    raw_items: list[str] = []
    primary = (os.environ.get(var_name) or "").strip()
    if primary:
        raw_items.extend(re.split(r"[,;\n]+", primary))
    for i in range(1, 21):
        val = (os.environ.get(f"{var_name}_{i}") or "").strip()
        if val:
            raw_items.extend(re.split(r"[,;\n]+", val))
    if extra_single and extra_single.strip():
        raw_items.extend(re.split(r"[,;\n]+", extra_single.strip()))

    seen_k: set[str] = set()
    out: list[str] = []
    for item in raw_items:
        tok = item.strip()
        if tok and tok not in seen_k:
            seen_k.add(tok)
            out.append(tok)
    return out


def _env_cloudflare_pairs() -> list[tuple[str, str]]:
    """استخراج یک یا چند جفت (CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN) با پشتیبانی از _2.._20 و کاما."""
    accs = _env_keys("CLOUDFLARE_ACCOUNT_ID")
    toks = _env_keys("CLOUDFLARE_API_TOKEN")
    if not accs or not toks:
        return []
    pairs: list[tuple[str, str]] = []
    seen_p: set[tuple[str, str]] = set()
    n = max(len(accs), len(toks))
    for i in range(n):
        acc = accs[i] if i < len(accs) else accs[0]
        tok = toks[i] if i < len(toks) else toks[0]
        if (acc, tok) not in seen_p:
            seen_p.add((acc, tok))
            pairs.append((acc, tok))
    return pairs


def _key_tag(k_idx: int, total: int) -> str:
    return f" [K{k_idx}]" if total > 1 else ""


def build_free_llm_chain_from_env() -> list[LLMEndpoint]:
    """ساخت لیست اولویت‌بندی‌شدهٔ مدل‌ها و ارائه‌دهندگان رایگان از روی .env (با پشتیبانی چند کلید / چند اکانت).

    ترتیب اولویت:
      1) زنجیرهٔ Gemini (ابتدا gemini-4-hydrogen، سپس gemini-4-neon، سپس gemini-3.8-flash و پشتیبان‌های Flash)
      2) ارائه‌دهندهٔ اصلی دلخواه کاربر در LLM_BASE_URL (اگر غیر از Gemini باشد)
      3) پشتیبان‌های رایگان باکیفیت برای فارسی (در صورت تنظیم کلید یا چند کلید در .env):
         Pollinations → GitHub Models → AxForge → Cerebras → SambaNova → Groq → OpenRouter
         → Cohere → Mistral → NVIDIA NIM → Cloudflare → Z.ai
      4) پشتیبان‌های اضطراری بدون نیاز به کلید (OVHcloud Qwen3.5-397B، Kilo Code، LLM7.io)
    """
    chain: list[LLMEndpoint] = []
    seen: set[tuple[str, str, str]] = set()

    def _add(ep: LLMEndpoint) -> None:
        key = (ep.base_url.rstrip("/"), ep.model, _key_hash(ep.api_key))
        if key not in seen:
            seen.add(key)
            chain.append(ep)

    def _add_provider_models(
        provider_name: str,
        base_url: str,
        models: tuple[str, ...] | list[str],
        keys: list[str],
        *,
        supports_json_mode: bool = True,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        total_k = len(keys)
        if total_k == 0:
            return
        for m in models:
            for k_idx, k_val in enumerate(keys, 1):
                _add(LLMEndpoint(
                    label=f"{provider_name}{_key_tag(k_idx, total_k)} ({m})",
                    base_url=base_url,
                    model=m,
                    api_key=k_val,
                    supports_json_mode=supports_json_mode,
                    extra_headers=dict(extra_headers or {}),
                ))

    llm_base = (os.environ.get("LLM_BASE_URL") or "").strip().rstrip("/")
    llm_key = (os.environ.get("LLM_API_KEY") or "").strip()
    llm_model = (os.environ.get("LLM_MODEL") or "").strip()

    # ۱) کلید(های) Gemini (یا از GEMINI_API_KEY / GEMINI_API_KEY_2..20 یا از LLM_API_KEY وقتی base_url گوگل باشد)
    extra_gem = llm_key if (llm_key and "generativelanguage.googleapis.com" in llm_base) else ""
    gemini_keys = _env_keys("GEMINI_API_KEY", extra_single=extra_gem)

    if gemini_keys:
        raw_models = (os.environ.get("GEMINI_MODEL_CHAIN") or "").strip()
        if raw_models:
            g_models = [m.strip() for m in raw_models.split(",") if m.strip()]
        else:
            g_models = list(DEFAULT_GEMINI_CHAIN)
        if llm_model and "generativelanguage.googleapis.com" in llm_base and llm_model not in g_models:
            g_models.append(llm_model)
        _add_provider_models("Google Gemini", GEMINI_OPENAI_BASE, g_models, gemini_keys)

    # ۲) اگر کاربر یک LLM_BASE_URL غیر از Gemini تنظیم کرده (مثلاً DeepSeek/OpenAI/Ollama)
    if llm_base and llm_model and "generativelanguage.googleapis.com" not in llm_base:
        prim_keys = _env_keys("LLM_API_KEY") or [""]
        total_p = len(prim_keys)
        for k_idx, pk in enumerate(prim_keys, 1):
            _add(LLMEndpoint(
                label=f"Primary{_key_tag(k_idx, total_p)} ({llm_model})",
                base_url=llm_base,
                model=llm_model,
                api_key=pk,
                require_auth=bool(pk),
            ))

    # ۳) پشتیبان‌های رایگان با کلید API (به‌ترتیب کیفیت فارسی + سقف رایگان بالا؛ با پشتیبانی چند کلید برای هر سرویس)
    _add_provider_models(
        "Pollinations",
        "https://gen.pollinations.ai/v1",
        ("openai", "mistral", "gemini-3-flash"),
        _env_keys("POLLINATIONS_API_KEY"),
        supports_json_mode=False,
    )

    _add_provider_models(
        "GitHub Models",
        "https://models.github.ai/inference",
        ("meta/Llama-3.3-70B-Instruct", "cohere/cohere-command-a", "deepseek/DeepSeek-V3-0324"),
        _env_keys("GITHUB_MODELS_TOKEN"),
        supports_json_mode=False,
    )

    _add_provider_models(
        "AxForge EU",
        "https://api.axforge.ai/v1",
        ("qwen3.8-27b", "glm-5.3-flash"),
        _env_keys("AXFORGE_API_KEY"),
    )

    _add_provider_models(
        "Cerebras",
        "https://api.cerebras.ai/v1",
        ("qwen-3-32b", "llama-3.3-70b"),
        _env_keys("CEREBRAS_API_KEY"),
    )

    _add_provider_models(
        "SambaNova",
        "https://api.sambanova.ai/v1",
        ("Meta-Llama-3.3-70B-Instruct", "Qwen2.5-72B-Instruct"),
        _env_keys("SAMBANOVA_API_KEY"),
    )

    _add_provider_models(
        "Groq",
        "https://api.groq.com/openai/v1",
        ("qwen/qwen3.8-27b", "openai/gpt-oss-120b", "llama-3.3-70b-versatile"),
        _env_keys("GROQ_API_KEY"),
    )

    _add_provider_models(
        "OpenRouter",
        "https://openrouter.ai/api/v1",
        (
            "google/gemma-4-31b-it:free",
            "google/gemma-4-26b-a4b-it:free",
            "nvidia/nemotron-3-ultra-550b-a55b:free",
            "openrouter/free",
        ),
        _env_keys("OPENROUTER_API_KEY"),
        supports_json_mode=False,
        extra_headers={"HTTP-Referer": "https://xgpedia.local", "X-Title": "XGPedia"},
    )

    _add_provider_models(
        "Cohere",
        "https://api.cohere.ai/compatibility/v1",
        ("command-a-03-2025", "c4ai-aya-expanse-32b"),
        _env_keys("COHERE_API_KEY"),
        supports_json_mode=False,
    )

    _add_provider_models(
        "Mistral",
        "https://api.mistral.ai/v1",
        ("mistral-medium-3-5-128b", "mistral-small-latest"),
        _env_keys("MISTRAL_API_KEY"),
    )

    _add_provider_models(
        "NVIDIA NIM",
        "https://integrate.api.nvidia.com/v1",
        ("z-ai/glm-5.3-flash", "nvidia/nemotron-3-ultra-550b-a55b"),
        _env_keys("NVIDIA_API_KEY"),
        supports_json_mode=False,
    )

    cf_pairs = _env_cloudflare_pairs()
    if cf_pairs:
        total_cf = len(cf_pairs)
        for cfm in ("@cf/google/gemma-4-26b-a4b-it", "@cf/meta/llama-3.3-70b-instruct-fp8-fast"):
            for k_idx, (cf_acc, cf_tok) in enumerate(cf_pairs, 1):
                cf_base = f"https://api.cloudflare.com/client/v4/accounts/{cf_acc}/ai/v1"
                _add(LLMEndpoint(
                    label=f"Cloudflare AI{_key_tag(k_idx, total_cf)} ({cfm})",
                    base_url=cf_base,
                    model=cfm,
                    api_key=cf_tok,
                    supports_json_mode=False,
                ))

    _add_provider_models(
        "Z.ai",
        "https://api.z.ai/api/paas/v4",
        ("glm-4.7-flash",),
        _env_keys("ZAI_API_KEY"),
        supports_json_mode=False,
    )

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
        llm7_keys = _env_keys("LLM7_API_KEY") or [""]
        total_l7 = len(llm7_keys)
        for k_idx, l7k in enumerate(llm7_keys, 1):
            _add(LLMEndpoint(
                label=f"LLM7.io Free{_key_tag(k_idx, total_l7)} (gpt-oss:20b)",
                base_url="https://api.llm7.io/v1",
                model="gpt-oss:20b",
                api_key=l7k,
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


# کش موقت حافظه‌ای برای عبور فوری از کلیدها/مدل‌هایی که اخیراً 429/503/404/Timeout داده‌اند
# کلید تاپل: (base_url, model, key_hash) برای خطای مخصوص هر کلید، و (base_url, model, "*") برای خطای 404 سراسری مدل
_ENDPOINT_COOLDOWN_UNTIL: dict[tuple[str, str, str], float] = {}
_LLM_START_CACHE_KEY = "setting:llm_start_index"


def get_endpoint_cooldown_remaining(ep: LLMEndpoint) -> int:
    """زمان باقی‌ماندهٔ کول‌داون یک endpoint به ثانیه (۰ یعنی آماده و سالم)."""
    now = time.monotonic()
    b = ep.base_url.rstrip("/")
    k_spec = (b, ep.model, _key_hash(ep.api_key))
    k_wide = (b, ep.model, "*")
    rem = max(
        _ENDPOINT_COOLDOWN_UNTIL.get(k_spec, 0.0) - now,
        _ENDPOINT_COOLDOWN_UNTIL.get(k_wide, 0.0) - now,
    )
    return int(rem) if rem > 0 else 0


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
    """پاک‌سازی کش موقت خطاهای 429/503/404 مدل‌ها و کلیدها."""
    _ENDPOINT_COOLDOWN_UNTIL.clear()


class MultiProviderLLM:
    """روتر هوشمند چندمدلی/چندکلیدی با سوییچ سریع روی 429/503/timeout/403 و توقف آنی در صورت لغو."""

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
        cancel_event: threading.Event | None = None,
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
        self.cancel_event: threading.Event | None = cancel_event
        self.last_used_label: str = ""

    def _ordered_endpoints(self) -> list[tuple[int, LLMEndpoint]]:
        """ترتیب اجرای مدل‌ها از روی start_index (کلیدها/مدل‌های در کول‌داون به انتها می‌روند)."""
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
            b = ep.base_url.rstrip("/")
            k_spec = (b, ep.model, _key_hash(ep.api_key))
            k_wide = (b, ep.model, "*")
            if _ENDPOINT_COOLDOWN_UNTIL.get(k_spec, 0.0) > now or _ENDPOINT_COOLDOWN_UNTIL.get(k_wide, 0.0) > now:
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
        cancel_event: threading.Event | None = None,
    ) -> DraftOutput:
        ev = cancel_event if cancel_event is not None else self.cancel_event
        errors: list[str] = []
        dead_models_this_run: set[tuple[str, str]] = set()

        for idx, ep in self._ordered_endpoints():
            if ev is not None and ev.is_set():
                print("[llm-router] cancelled by timeout/caller - stopping model switch loop")
                raise TimeoutError("درخواست تولید متن به دلیل اتمام زمان مجاز متوقف شد.")

            b = ep.base_url.rstrip("/")
            if (b, ep.model) in dead_models_this_run:
                continue

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
            k_spec = (b, ep.model, _key_hash(ep.api_key))
            k_wide = (b, ep.model, "*")
            try:
                out = client.generate(
                    system_prompt,
                    facts,
                    repair_feedback=repair_feedback,
                    previous_raw=previous_raw,
                    edit_instruction=edit_instruction,
                    current_draft_json=current_draft_json,
                )
                if ev is not None and ev.is_set():
                    print("[llm-router] cancelled right after response - discarding late output")
                    raise TimeoutError("درخواست تولید متن به دلیل اتمام زمان مجاز متوقف شد.")
                _ENDPOINT_COOLDOWN_UNTIL.pop(k_spec, None)
                _ENDPOINT_COOLDOWN_UNTIL.pop(k_wide, None)
                self.last_used_label = ep.label
                print(f"[llm-router] success via #{idx} {ep.label}")
                return out
            except TimeoutError:
                if ev is not None and ev.is_set():
                    raise
                short_err = "TimeoutError: request timed out"
                if self.cooldown_seconds > 0:
                    _ENDPOINT_COOLDOWN_UNTIL[k_spec] = time.monotonic() + self.cooldown_seconds
                errors.append(f"{ep.label} -> {short_err}")
                print(f"[llm-router] #{idx} {ep.label} failed ({short_err}) - switching to next")
                continue
            except Exception as e:
                if ev is not None and ev.is_set():
                    print("[llm-router] cancelled during failover - stopping immediately")
                    raise TimeoutError("درخواست تولید متن به دلیل اتمام زمان مجاز متوقف شد.") from e
                short_err = f"{type(e).__name__}: {str(e)[:120]}"
                if self.cooldown_seconds > 0:
                    if "404" in short_err:
                        # مدل روی این سرور وجود ندارد — همهٔ کلیدهای این مدل برای ۳۰ دقیقه رد شوند
                        _ENDPOINT_COOLDOWN_UNTIL[k_wide] = time.monotonic() + max(self.cooldown_seconds, 1800.0)
                        dead_models_this_run.add((b, ep.model))
                    elif any(tok in short_err for tok in ("429", "503", "Timeout", "502", "504", "402", "401", "403")):
                        # خطای مخصوص همین کلید/اکانت — بلافاصله کلید بعدی همین سرویس امتحان می‌شود
                        _ENDPOINT_COOLDOWN_UNTIL[k_spec] = time.monotonic() + self.cooldown_seconds
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


def generate_text(
    prompt: str,
    *,
    max_tokens: int = 240,
    system_prompt: str | None = None,
    cancel_event: threading.Event | None = None,
) -> str | None:
    """تولید یا ترجمه سریع متن آزاد (غیرJSON) با استفاده از همان زنجیرهٔ رایگان LLM پروژه."""
    p_txt = str(prompt or "").strip()
    if not p_txt:
        return None
    sys_msg = system_prompt or (
        "تو مترجم و دبیر تحریریه ورزشی فارسی هستی. دقیق، روان و کوتاه به فارسی بنویس و فقط پاسخ نهایی را برگردان."
    )
    messages = [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": p_txt},
    ]
    chain = build_free_llm_chain_from_env()
    if not chain:
        try:
            client = OpenAICompatibleLLM(supports_json_mode=False, max_attempts=1, timeout=18.0)
            out = client._chat(messages)
            return out.strip() if out else None
        except Exception:
            return None

    now = time.monotonic()
    start_idx = get_llm_start_index(len(chain))
    ordered = list(enumerate(chain))[start_idx:] + list(enumerate(chain))[:start_idx]
    for _idx, ep in ordered:
        if cancel_event is not None and cancel_event.is_set():
            return None
        b = ep.base_url.rstrip("/")
        k_spec = (b, ep.model, _key_hash(ep.api_key))
        k_wide = (b, ep.model, "*")
        if _ENDPOINT_COOLDOWN_UNTIL.get(k_spec, 0.0) > now or _ENDPOINT_COOLDOWN_UNTIL.get(k_wide, 0.0) > now:
            continue
        try:
            client = OpenAICompatibleLLM(
                max_attempts=1,
                backoff_seconds=0.0,
                base_url=ep.base_url,
                api_key=ep.api_key,
                model=ep.model,
                require_auth=ep.require_auth,
                extra_headers=ep.extra_headers,
                supports_json_mode=False,
                timeout=18.0,
            )
            out = client._chat(messages)
            if out and out.strip():
                _ENDPOINT_COOLDOWN_UNTIL.pop(k_spec, None)
                return out.strip()
        except Exception as e:
            short_err = f"{type(e).__name__}: {str(e)[:120]}"
            if "404" in short_err:
                _ENDPOINT_COOLDOWN_UNTIL[k_wide] = time.monotonic() + 1800.0
            elif any(tok in short_err for tok in ("429", "503", "Timeout", "502", "504", "402", "401", "403")):
                _ENDPOINT_COOLDOWN_UNTIL[k_spec] = time.monotonic() + 900.0
            continue
    return None
