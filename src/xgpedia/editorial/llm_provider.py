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
        d = json.loads(raw)
        unknown = set(d) - {"status", "title", "bullets", "caption", "source_note", "uncertainties"}
        if unknown:
            raise ValueError(f"کلیدهای غیرمجاز در خروجی مدل: {unknown}")
        if d.get("status") not in {"ok", "insufficient_data"}:
            raise ValueError("status نامعتبر")
        return cls(
            status=d["status"],
            title=d["title"],
            bullets=list(d.get("bullets", []))[:3],
            caption=d.get("caption", "")[:700],
            source_note=d.get("source_note", ""),
            uncertainties=list(d.get("uncertainties", [])),
        )


class OpenAICompatibleLLM:
    """کلاینت عمومی سازگار با OpenAI — پشت همان interface؛ قابل تعویض با یک خط env."""

    name = "openai_compatible"

    def __init__(self) -> None:
        self.base_url = os.environ["LLM_BASE_URL"].rstrip("/")
        self.api_key = os.environ["LLM_API_KEY"]
        self.model = os.environ["LLM_MODEL"]

    def generate(self, system_prompt: str, facts: MatchFacts) -> DraftOutput:
        import httpx

        # فقط فیلدهای مجاز به مدل می‌روند — payload خام هرگز ارسال نمی‌شود
        payload = facts.model_dump(mode="json")
        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        return DraftOutput.from_json(resp.json()["choices"][0]["message"]["content"])


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
