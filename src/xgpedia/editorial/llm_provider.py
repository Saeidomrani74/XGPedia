"""لایهٔ ۴ — Editorial: interface عمومی LLMProvider — مدل قابل تعویض در یک خط config.

قواعد (بخش ۸ سند):
  - مدل زبانی فقط متن می‌نویسد؛ عدد، نام، شناسهٔ منبع و timestamp همیشه از کد.
  - یک provider اصلی + یک fallback.
  - انتخاب نهایی فقط پس از benchmark فارسی روی ۲۰ مسابقهٔ واقعی.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol

from src.xgpedia.normalization.models import MatchFacts


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
    """حذف ```json ... ``` اگر مدل قالب را فنس کرد — JSON خالص لازم است."""
    t = raw.strip()
    if t.startswith("```"):
        first_nl = t.find("\n")
        if first_nl != -1:
            t = t[first_nl + 1:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


class OpenAICompatibleLLM:
    """کلاینت عمومی سازگار با OpenAI — پشت همان interface؛ قابل تعویض با یک خط env.

    فراخوانی: LLM_BASE_URL / LLM_API_KEY / LLM_MODEL در .env (یا هر سرویس
    سازگار با OpenAI Chat Completions: OpenAI، DeepSeek، OpenRouter، z-ai و ...).
    retry دوم با feedback validator انجام می‌شود — generate را با آرگومان اختیاری
    repair_feedback صدا بزنید تا خطاها را ببیند و اصلاح کند.
    """

    name = "openai_compatible"

    def __init__(self) -> None:
        missing = [k for k in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL") if not os.environ.get(k)]
        if missing:
            raise RuntimeError(
                f"missing env: {', '.join(missing)} - set them in .env "
                f"(see .env.example); this adapter needs an OpenAI-compatible API key"
            )
        self.base_url = os.environ["LLM_BASE_URL"].rstrip("/")
        self.api_key = os.environ["LLM_API_KEY"]
        self.model = os.environ["LLM_MODEL"]

    def generate(
        self, system_prompt: str, facts: MatchFacts, repair_feedback: str = "",
        previous_raw: str = "",
    ) -> DraftOutput:
        import httpx

        # فقط فیلدهای مجاز به مدل می‌روند — payload خام هرگز ارسال نمی‌شود
        payload = facts.model_dump(mode="json")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        if repair_feedback:
            # الگوی اصلاح: پیش‌نویس ردشده + خطاهای validator عیناً برمی‌گردند
            messages.append({"role": "assistant", "content": previous_raw or "{}"})
            messages.append({"role": "user", "content": REPAIR_PREFIX + repair_feedback})
        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "response_format": {"type": "json_object"},
                "messages": messages,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        return DraftOutput.from_json(resp.json()["choices"][0]["message"]["content"])


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
