"""موتور یادگیری و مسیریابی هوشمند APIها و مدل‌های هوش مصنوعی (`APIHealthRouter`).

کارکرد:
  - ثبت پایدار (در `data/api_health.json`) نرخ موفقیت، میانگین زمان پاسخ (EMA latency)،
    خطاهای متوالی و زمان کول‌داون هر API / فید / مدل LLM در سطح کل پروژه.
  - امتیازدهی پویا (۰ تا ۱۰۰) با ترکیب نرخ موفقیت (Bayesian smoothing) و سرعت پاسخ،
    تا APIها و مدل‌های سریع‌تر و سالم‌تر همیشه در اولویت اول قرار بگیرند و منابع
    محدودشده (429 / 404 / 5xx / Timeout) تا پایان کول‌داون خودکار رد شوند.
  - ۱۰۰٪ بدون وابستگی خارجی (فقط stdlib)، thread-safe و ایمن برای تست‌های آفلاین.
"""
from __future__ import annotations

import json
import math
import threading
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

from src.xgpedia.config import ROOT

T = TypeVar("T")

DEFAULT_HEALTH_PATH = ROOT / "data" / "api_health.json"
_LOCK = threading.RLock()
_STATE: dict[str, dict[str, Any]] = {}
_LOADED_PATH: Path | None = None
_PERSIST_ENABLED: bool = True


def configure_health_store(*, path: Path | None = None, persist: bool = True, clear: bool = False) -> None:
    """تنظیم مسیر فایل ذخیره یا حالت فقط-حافظه (مناسب تست‌های واحد)."""
    global _LOADED_PATH, _PERSIST_ENABLED
    with _LOCK:
        _PERSIST_ENABLED = persist
        if clear:
            _STATE.clear()
        if path is not None:
            _LOADED_PATH = path
            if persist and path.exists():
                _load_locked(path)
        elif persist:
            _LOADED_PATH = DEFAULT_HEALTH_PATH


def _ensure_loaded_locked() -> None:
    global _LOADED_PATH
    if _LOADED_PATH is not None or not _PERSIST_ENABLED:
        return
    _LOADED_PATH = DEFAULT_HEALTH_PATH
    if _LOADED_PATH.exists():
        _load_locked(_LOADED_PATH)


def _load_locked(path: Path) -> None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            _STATE.clear()
            for k, v in raw.items():
                if isinstance(k, str) and isinstance(v, dict):
                    _STATE[k] = dict(v)
    except Exception as _em_exc:
        from src.xgpedia.core.error_metrics import record_error as _rec_err
        _rec_err('core.api_health', _em_exc)


def _save_locked() -> None:
    if not _PERSIST_ENABLED:
        return
    target = _LOADED_PATH or DEFAULT_HEALTH_PATH
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(_STATE, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)
    except Exception as _em_exc:
        from src.xgpedia.core.error_metrics import record_error as _rec_err
        _rec_err('core.api_health', _em_exc)


def record_success(key: str, latency_ms: float = 400.0) -> None:
    """ثبت پاسخ موفق یک API یا مدل LLM و به‌روزرسانی میانگین زمان پاسخ (EMA)."""
    k = str(key or "").strip()
    if not k:
        return
    now = time.time()
    lat = max(10.0, min(60_000.0, float(latency_ms or 400.0)))
    with _LOCK:
        _ensure_loaded_locked()
        rec = _STATE.get(k) or {
            "ok": 0, "fail": 0, "streak_fail": 0,
            "avg_ms": lat, "cooldown_until": 0.0,
            "last_ok": 0.0, "last_err": "",
        }
        rec["ok"] = int(rec.get("ok", 0)) + 1
        rec["streak_fail"] = 0
        rec["cooldown_until"] = 0.0
        rec["last_ok"] = round(now, 1)
        prev_ms = float(rec.get("avg_ms") or lat)
        rec["avg_ms"] = round(prev_ms * 0.7 + lat * 0.3, 1)
        _STATE[k] = rec
        _save_locked()


def record_failure(
    key: str,
    error: str = "",
    *,
    status_code: int | None = None,
    base_cooldown: float = 90.0,
) -> float:
    """ثبت خطای API/مدل و محاسبهٔ کول‌داون تصاعدی (exponential backoff)."""
    k = str(key or "").strip()
    if not k:
        return 0.0
    now = time.time()
    err_s = str(error or "")[:140]
    with _LOCK:
        _ensure_loaded_locked()
        rec = _STATE.get(k) or {
            "ok": 0, "fail": 0, "streak_fail": 0,
            "avg_ms": 2000.0, "cooldown_until": 0.0,
            "last_ok": 0.0, "last_err": "",
        }
        rec["fail"] = int(rec.get("fail", 0)) + 1
        streak = int(rec.get("streak_fail", 0)) + 1
        rec["streak_fail"] = streak
        rec["last_err"] = err_s

        # کول‌داون هوشمند بر اساس نوع خطا و تعداد خطای متوالی
        if status_code in (401, 403, 404) or any(tok in err_s for tok in ("404", "401", "403")):
            cd = 1800.0  # ۳۰ دقیقه برای کلید نامعتبر یا مدل حذف‌شده
        elif status_code == 429 or "429" in err_s:
            cd = min(1800.0, max(base_cooldown, 180.0) * (2 ** min(streak - 1, 3)))
        else:
            cd = min(1200.0, base_cooldown * (2 ** min(streak - 1, 4)))

        rec["cooldown_until"] = round(now + cd, 1)
        _STATE[k] = rec
        _save_locked()
        return cd


def is_cooling(key: str, *, now: float | None = None) -> bool:
    """آیا این API/مدل هم‌اکنون در دورهٔ استراحت (کول‌داون) است؟"""
    k = str(key or "").strip()
    if not k:
        return False
    t = time.time() if now is None else now
    with _LOCK:
        _ensure_loaded_locked()
        rec = _STATE.get(k)
        if not rec:
            return False
        return float(rec.get("cooldown_until") or 0.0) > t


def health_score(key: str, *, now: float | None = None) -> float:
    """محاسبهٔ امتیاز سلامت و سرعت (۰ تا ۱۰۰) برای اولویت‌بندی هوشمند."""
    k = str(key or "").strip()
    if not k:
        return 50.0
    t = time.time() if now is None else now
    with _LOCK:
        _ensure_loaded_locked()
        rec = _STATE.get(k)
        if not rec:
            return 72.0  # امتیاز خنثی-مثبت برای منبع تازه جهت کشف اولیه
        ok = int(rec.get("ok", 0))
        fail = int(rec.get("fail", 0))
        streak = int(rec.get("streak_fail", 0))
        avg_ms = max(50.0, float(rec.get("avg_ms") or 1200.0))
        cooling = float(rec.get("cooldown_until") or 0.0) > t

        # نرخ موفقیت با هموارسازی بیزی (Bayesian prior: 2 موفق از 2.5)
        rate = (ok + 2.0) / (ok + fail + 2.5)
        rate_pts = rate * 70.0
        # امتیاز سرعت (۰ تا ۳۰): زیر ۵۰۰ms نزدیک ۳۰، بالای ۶۰۰۰ms نزدیک ۲
        speed_pts = 30.0 / (1.0 + math.log1p(avg_ms / 400.0))
        penalty = min(35.0, streak * 10.0) + (40.0 if cooling else 0.0)
        return round(max(0.0, min(100.0, rate_pts + speed_pts - penalty)), 2)


def rank_items(items: list[T], key_fn: Callable[[T], str], *, skip_cooling: bool = False) -> list[T]:
    """مرتب‌سازی فهرست APIها/فیدها/مدل‌ها بر اساس امتیاز یادگرفته‌شده (سالم‌ترین و سریع‌ترین در ابتدا)."""
    now = time.time()
    healthy: list[tuple[float, int, T]] = []
    cooling: list[tuple[float, int, T]] = []
    for idx, it in enumerate(items):
        k = key_fn(it)
        sc = health_score(k, now=now)
        if is_cooling(k, now=now):
            cooling.append((sc, idx, it))
        else:
            healthy.append((sc, idx, it))
    healthy.sort(key=lambda x: (-x[0], x[1]))
    cooling.sort(key=lambda x: (-x[0], x[1]))
    if skip_cooling and healthy:
        return [x[2] for x in healthy]
    return [x[2] for x in healthy] + [x[2] for x in cooling]


def reset_health(prefix: str | None = None) -> int:
    """پاک‌سازی حافظهٔ سلامت (کل یا یک گروه خاص مثل llm: یا feed:)."""
    with _LOCK:
        _ensure_loaded_locked()
        if not prefix:
            n = len(_STATE)
            _STATE.clear()
            _save_locked()
            try:
                from src.xgpedia.core.error_metrics import reset_error_counts
                reset_error_counts()
            except Exception as _em_exc:
                from src.xgpedia.core.error_metrics import record_error as _rec_err
                _rec_err('core.api_health', _em_exc)
            return n
        keys = [k for k in list(_STATE.keys()) if k.startswith(prefix)]
        for k in keys:
            _STATE.pop(k, None)
        _save_locked()
        return len(keys)


def get_health_snapshot() -> dict[str, dict[str, Any]]:
    with _LOCK:
        _ensure_loaded_locked()
        return {k: dict(v) for k, v in _STATE.items()}


def format_health_report_fa(max_rows: int = 12) -> str:
    """گزارش خوانای فارسی از وضعیت یادگیری و سلامت APIها و مدل‌های AI برای ربات تلگرام."""
    snap = get_health_snapshot()
    if not snap:
        return (
            "🩺 <b>گزارش یادگیری و سلامت APIها</b>\n\n"
            "هنوز درخواستی ثبت نشده است. به‌محض استفاده از ربات، سیستم به‌صورت خودکار "
            "سریع‌ترین و سالم‌ترین APIها و مدل‌های AI را یاد می‌گیرد و در اولویت قرار می‌دهد."
        )
    now = time.time()
    ranked = sorted(snap.items(), key=lambda kv: health_score(kv[0], now=now), reverse=True)
    lines = ["🩺 <b>گزارش یادگیری و سلامت APIها و مدل‌های AI</b>", ""]
    for k, rec in ranked[:max_rows]:
        sc = health_score(k, now=now)
        ok = int(rec.get("ok", 0))
        fail = int(rec.get("fail", 0))
        ms = int(rec.get("avg_ms") or 0)
        cool_left = max(0, int(float(rec.get("cooldown_until") or 0.0) - now))
        icon = "🔴" if cool_left > 0 else ("🟢" if sc >= 70 else "🟡")
        cd_txt = f" | ⏳ کول‌داون {cool_left // 60}د" if cool_left > 0 else ""
        short_k = k if len(k) <= 44 else k[:41] + "..."
        lines.append(f"{icon} <code>{short_k}</code>\n   امتیاز: <b>{sc:.0f}</b> | ✅ {ok} / ❌ {fail} | ⚡ {ms}ms{cd_txt}")
    try:
        from src.xgpedia.core.error_metrics import get_error_counts
        ec = get_error_counts()
        if ec:
            lines.append("")
            lines.append("⚠️ <b>خطاهای مهارشده (Error Metrics):</b>")
            for ek, cnt in sorted(ec.items(), key=lambda kv: kv[1], reverse=True)[:8]:
                lines.append(f"• <code>{ek}</code>: <b>{cnt}</b>")
    except Exception as _em_exc:
        from src.xgpedia.core.error_metrics import record_error as _rec_err
        _rec_err('core.api_health', _em_exc)
    try:
        from src.xgpedia.core.hydration_cache import get_cache_stats
        cs = get_cache_stats()
        if cs.get("total", 0) > 0:
            lines.append("")
            lines.append(f"🗄 <b>کش پایدار SQLite:</b> {cs['fresh']}/{cs['total']} کلید تازه")
    except Exception as _em_exc:
        from src.xgpedia.core.error_metrics import record_error as _rec_err
        _rec_err('core.api_health', _em_exc)
    return "\n".join(lines)
