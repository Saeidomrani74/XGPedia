"""کش پایدار SQLite با TTL هوشمند، Stale-While-Revalidate (SWR) و کنترل سقف درخواست (v0.78.0).

طراحی برای پاسخ‌گویی آنی ربات تلگرام بدون پرشدن سقف درخواست APIها:
  - دادهٔ تازه (`now < expires_at`): پاسخ زیر ۱ میلی‌ثانیه از SQLite بدون هیچ تماس شبکه‌ای.
  - دادهٔ نیمه‌تازه (`expires_at <= now < expires_at + stale_grace_sec`): بازگرداندن فوری مقدار کش‌شده
    به کاربر + نوسازی خودکار و بدون تکرار در پس‌زمینه (Stale-While-Revalidate).
  - نگهبان نرخ (`_RateBudget`): حداقل فاصله و سقف ساعتی اختصاصی برای هر ارائه‌دهنده تا هرگز 429 نخوریم.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from typing import Any, Callable

log = logging.getLogger(__name__)

# TTL پیش‌فرض هوشمند بر پایهٔ ماهیت هر داده (ثانیه)
DEFAULT_TTLS: dict[str, int] = {
    "fpl_bootstrap": 6 * 3600,          # ۶ ساعت
    "fpl_element_summary": 6 * 3600,    # ۶ ساعت (مشترک بین Top Scorers و FC27)
    "understat_league_xhr": 12 * 3600,  # ۱۲ ساعت (آمار فصلی فقط پس از بازی‌ها تغییر می‌کند)
    "fotmob_day_matches": 30 * 60,      # ۳۰ دقیقه
    "fotmob_post_match": 7 * 86400,     # ۷ روز (آمار Opta بازی تمام‌شده تغییر نمی‌کند)
}

# بودجهٔ نرخ محافظه‌کارانه به ازای هر ارائه‌دهنده: (min_interval_sec, max_per_hour)
DEFAULT_RATE_BUDGETS: dict[str, tuple[float, int]] = {
    "fpl_bootstrap": (60.0, 12),
    "fpl_element_summary": (1.5, 120),
    "understat_league_xhr": (4.0, 30),
    "fotmob_day_matches": (5.0, 40),
    "fotmob_post_match": (3.0, 60),
}

_BUDGET_LOCK = threading.Lock()
_RECENT_CALLS: dict[str, deque[float]] = {}
_INFLIGHT_LOCK = threading.Lock()
_INFLIGHT_KEYS: set[str] = set()


def can_spend_budget(namespace: str, *, now: float | None = None) -> bool:
    """بررسی اینکه آیا ارسال درخواست جدید در این namespace در سقف مجاز ساعتی/فاصله‌ای است یا نه."""
    min_gap, max_hr = DEFAULT_RATE_BUDGETS.get(namespace, (1.0, 120))
    ts = time.time() if now is None else now
    with _BUDGET_LOCK:
        dq = _RECENT_CALLS.setdefault(namespace, deque())
        cutoff = ts - 3600.0
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= max_hr:
            return False
        if dq and (ts - dq[-1]) < min_gap:
            return False
        return True


def record_budget_spend(namespace: str, *, now: float | None = None) -> None:
    ts = time.time() if now is None else now
    with _BUDGET_LOCK:
        dq = _RECENT_CALLS.setdefault(namespace, deque())
        cutoff = ts - 3600.0
        while dq and dq[0] < cutoff:
            dq.popleft()
        dq.append(ts)


def reset_rate_budgets() -> None:
    with _BUDGET_LOCK:
        _RECENT_CALLS.clear()


def _ensure_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS api_hydration_cache (
          cache_key TEXT PRIMARY KEY,
          namespace TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          fetched_at REAL NOT NULL,
          ttl_sec INTEGER NOT NULL,
          expires_at REAL NOT NULL
        )
        """
    )


def get_cached(
    cache_key: str,
    *,
    allow_stale_sec: int = 0,
    now: float | None = None,
) -> tuple[bool, Any, bool]:
    """خواندن از کش SQLite.

    خروجی: `(hit, value, is_stale)`
    """
    from src.xgpedia import db as db_mod

    ts = time.time() if now is None else now
    try:
        if not db_mod.DATABASE_PATH.exists():
            return False, None, False
        with db_mod.db() as conn:
            _ensure_table(conn)
            row = conn.execute(
                "SELECT payload_json, expires_at FROM api_hydration_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        if not row:
            return False, None, False
        exp = float(row["expires_at"])
        if ts <= exp:
            return True, json.loads(row["payload_json"]), False
        if allow_stale_sec > 0 and ts <= exp + allow_stale_sec:
            return True, json.loads(row["payload_json"]), True
        return False, None, False
    except Exception:
        return False, None, False


def set_cached(
    cache_key: str,
    namespace: str,
    value: Any,
    *,
    ttl_sec: int | None = None,
    now: float | None = None,
) -> bool:
    """ذخیرهٔ پایدار یک نتیجهٔ هیدراتاسیون در SQLite با TTL هوشمند."""
    from src.xgpedia import db as db_mod

    ttl = int(ttl_sec if ttl_sec is not None else DEFAULT_TTLS.get(namespace, 3600))
    ts = time.time() if now is None else now
    try:
        payload = json.dumps(value, ensure_ascii=False)
        db_mod.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with db_mod.db() as conn:
            _ensure_table(conn)
            conn.execute(
                """
                INSERT OR REPLACE INTO api_hydration_cache
                  (cache_key, namespace, payload_json, fetched_at, ttl_sec, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (cache_key, namespace, payload, ts, ttl, ts + ttl),
            )
        return True
    except Exception as exc:
        log.debug("hydration_cache set failed for %s: %s", cache_key, exc)
        return False


def _schedule_bg_refresh(
    cache_key: str,
    namespace: str,
    fetcher: Callable[[], Any],
    ttl_sec: int | None,
) -> None:
    with _INFLIGHT_LOCK:
        if cache_key in _INFLIGHT_KEYS:
            return
        _INFLIGHT_KEYS.add(cache_key)

    def _worker() -> None:
        try:
            if not can_spend_budget(namespace):
                return
            record_budget_spend(namespace)
            fresh = fetcher()
            if fresh is not None and fresh != {} and fresh != []:
                set_cached(cache_key, namespace, fresh, ttl_sec=ttl_sec)
        except Exception as exc:
            from src.xgpedia.core.error_metrics import record_error
            record_error(f"hydration_swr.{namespace}", exc)
        finally:
            with _INFLIGHT_LOCK:
                _INFLIGHT_KEYS.discard(cache_key)

    threading.Thread(target=_worker, name=f"swr-{namespace}", daemon=True).start()


def get_or_fetch(
    cache_key: str,
    namespace: str,
    fetcher: Callable[[], Any],
    *,
    ttl_sec: int | None = None,
    stale_grace_sec: int = 3600,
    allow_swr: bool = True,
) -> Any:
    """الگوی Stale-While-Revalidate: پاسخ آنی از کش SQLite + نوسازی آرام در پس‌زمینه."""
    hit, val, is_stale = get_cached(cache_key, allow_stale_sec=stale_grace_sec if allow_swr else 0)
    if hit and not is_stale:
        return val
    if hit and is_stale:
        _schedule_bg_refresh(cache_key, namespace, fetcher, ttl_sec)
        return val

    # Cold miss: دریافت همزمان و ذخیره در SQLite
    record_budget_spend(namespace)
    fresh = fetcher()
    if fresh is not None and fresh != {} and fresh != []:
        set_cached(cache_key, namespace, fresh, ttl_sec=ttl_sec)
    return fresh


def is_fresh(cache_key: str, *, lead_sec: int = 0, now: float | None = None) -> bool:
    """آیا کلید در کش موجود است و حداقل `lead_sec` ثانیه دیگر معتبر می‌ماند؟"""
    from src.xgpedia import db as db_mod

    ts = time.time() if now is None else now
    try:
        if not db_mod.DATABASE_PATH.exists():
            return False
        with db_mod.db() as conn:
            _ensure_table(conn)
            row = conn.execute(
                "SELECT expires_at FROM api_hydration_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        return bool(row and float(row["expires_at"]) > (ts + lead_sec))
    except Exception:
        return False


def purge_expired(older_than_sec: int = 14 * 86400, *, now: float | None = None) -> int:
    """پاک‌سازی ردیف‌های منقضی‌شدهٔ قدیمی‌تر از `older_than_sec` برای سبک‌ماندن SQLite."""
    from src.xgpedia import db as db_mod

    ts = time.time() if now is None else now
    cutoff = ts - max(0, older_than_sec)
    try:
        if not db_mod.DATABASE_PATH.exists():
            return 0
        with db_mod.db() as conn:
            _ensure_table(conn)
            cur = conn.execute("DELETE FROM api_hydration_cache WHERE expires_at < ?", (cutoff,))
            return int(cur.rowcount or 0)
    except Exception:
        return 0


def get_cache_stats(*, now: float | None = None) -> dict[str, Any]:
    """آمار خلاصهٔ کش پایدار SQLite برای نمایش در دستور `/health`."""
    from src.xgpedia import db as db_mod

    ts = time.time() if now is None else now
    try:
        if not db_mod.DATABASE_PATH.exists():
            return {"total": 0, "fresh": 0, "by_namespace": {}}
        with db_mod.db() as conn:
            _ensure_table(conn)
            rows = conn.execute("SELECT namespace, expires_at FROM api_hydration_cache").fetchall()
        by_ns: dict[str, int] = {}
        fresh = 0
        for r in rows:
            ns = str(r["namespace"])
            by_ns[ns] = by_ns.get(ns, 0) + 1
            if float(r["expires_at"]) >= ts:
                fresh += 1
        return {"total": len(rows), "fresh": fresh, "by_namespace": by_ns}
    except Exception:
        return {"total": 0, "fresh": 0, "by_namespace": {}}
