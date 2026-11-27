"""شمارندهٔ ساختاریافتهٔ خطاهای مهارشده (Structured Error Metrics).

برای حفظ تاب‌آوری در بلوک‌های `except` و هم‌زمان دیداری‌سازی خطاها بدون کرش ربات.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import Counter, deque
from typing import Any

log = logging.getLogger(__name__)

_LOCK = threading.Lock()
_COUNTS: Counter[str] = Counter()
_RECENT: deque[dict[str, Any]] = deque(maxlen=100)


def record_error(scope: str, exc: BaseException | str, detail: str = "") -> None:
    """ثبت یک خطای مهارشده با دامنه، نوع استثنا و توضیح کوتاه."""
    exc_type = type(exc).__name__ if isinstance(exc, BaseException) else "Error"
    exc_msg = str(exc)[:180]
    key = f"{scope}:{exc_type}"
    entry = {
        "ts": time.time(),
        "scope": scope,
        "exc_type": exc_type,
        "message": exc_msg,
        "detail": detail[:120] if detail else "",
    }
    with _LOCK:
        _COUNTS[key] += 1
        _RECENT.append(entry)
    log.debug("suppressed error [%s] %s: %s", scope, exc_type, exc_msg)


def get_error_counts() -> dict[str, int]:
    """بازگرداندن دیکشنری تعداد خطاهای ثبت‌شده به تفکیک `scope:ExceptionType`."""
    with _LOCK:
        return dict(_COUNTS)


def get_recent_errors(limit: int = 20) -> list[dict[str, Any]]:
    """بازگرداندن آخرین خطاهای مهارشده برای مانیتورینگ یا دستور `/health`."""
    with _LOCK:
        items = list(_RECENT)
    return items[-max(1, limit):]


def reset_error_counts() -> None:
    """پاک‌سازی شمارنده (مناسب تست‌ها)."""
    with _LOCK:
        _COUNTS.clear()
        _RECENT.clear()
