"""لایهٔ ۱ — Ingestion: دریافت از provider و ذخیرهٔ payload خام.

قواعد غیرقابل‌مذاکرهٔ این لایه (بخش ۶ سند):
  ۱) پاسخ خام provider پیش از هر پردازشی ذخیره می‌شود (در حد مجوز ToS) + sha256.
  ۲) timestamp جمع‌آوری، timestamp رویداد، نام provider و زمان آخرین
     به‌روزرسانی جدا ذخره می‌شوند — هر عدد تا payload خام ردیابی‌پذیر است.
  ۳) timeout، retry با backoff و احترام به rate limit؛ اما تکرار job
     نباید رکورد تکراری بسازد (idempotency در لایهٔ repository).
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.xgpedia.config import RAW_PAYLOAD_DIR


@dataclass
class RateLimitBudget:
    """بودجهٔ درخواست روزانه — مصرف واقعی لاگ شود (قاعدهٔ کمتر از ۸۰٪ سهمیه)."""

    daily_limit: int = 100  # پلن رایگان API-Football
    used: int = 0
    events: list[str] = field(default_factory=list)

    def spend(self, n: int, why: str) -> None:
        if self.used + n > int(self.daily_limit * 0.8):
            raise RuntimeError(
                f"هشدار سهمیه: مصرف {self.used + n} از {self.daily_limit} "
                f"(سقف ۸۰٪) — کار «{why}» متوقف شد"
            )
        self.used += n
        self.events.append(f"{time.strftime('%H:%M:%S')} {why} -{n}")


@dataclass
class RawResponse:
    """پاسخ خام به‌همراه provenance — پایهٔ هر ردیابی بعدی."""

    provider: str
    endpoint: str
    payload: dict[str, Any]
    collected_at: str  # ISO-8601 UTC
    payload_hash: str
    http_status: int = 200

    @classmethod
    def build(
        cls, provider: str, endpoint: str, payload: dict[str, Any], http_status: int = 200
    ) -> "RawResponse":
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return cls(
            provider=provider,
            endpoint=endpoint,
            payload=payload,
            collected_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            payload_hash=hashlib.sha256(raw).hexdigest(),
            http_status=http_status,
        )

    def save(self) -> Path:
        """ذخیرهٔ خام در data/raw/<provider>/<YYYY-MM-DD>/<hash>.json — در حد مجوز ToS."""
        day = self.collected_at[:10]
        out_dir = RAW_PAYLOAD_DIR / self.provider / day
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{self.payload_hash}.json"
        if not out_file.exists():  # idempotent: hash یکسان = بازنویسی نکن
            out_file.write_text(
                json.dumps(
                    {
                        "provider": self.provider,
                        "endpoint": self.endpoint,
                        "collected_at": self.collected_at,
                        "payload_hash": self.payload_hash,
                        "payload": self.payload,
                    },
                    ensure_ascii=False,
                    indent=1,
                ),
                encoding="utf-8",
            )
        return out_file


class ProviderError(RuntimeError):
    """خطای provider — با backoff یک بار retry؛ شکست دوم = draft دستی، نه سکوت."""


def with_backoff(fn, attempts: int = 2, base_delay: float = 2.0):
    """Retry با backoff نمایی + jitter — فقط برای خطای گذرا (5xx / timeout)."""
    import random

    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except ProviderError:
            if attempt == attempts:
                raise
            time.sleep(base_delay * attempt + random.uniform(0, 1))
    raise ProviderError("unreachable")
