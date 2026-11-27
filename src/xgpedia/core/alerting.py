"""کانال هشدار/گزارش خطا و بررسی آمادگی ۷ روزهٔ دروازهٔ ۳ (Gate 3) — v0.80.3."""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from src.xgpedia import db as db_mod
from src.xgpedia.config import (
    ADMIN_TELEGRAM_IDS,
    ALERT_TELEGRAM_CHAT_ID,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHANNEL_ID,
)
from src.xgpedia.core.error_metrics import get_error_counts


def resolve_alert_chat_id() -> str | int | None:
    """مقصد پیام‌های هشدار: اول `ALERT_TELEGRAM_CHAT_ID`، در صورت نبود اولین شناسهٔ `ADMIN_TELEGRAM_IDS`."""
    if ALERT_TELEGRAM_CHAT_ID:
        return ALERT_TELEGRAM_CHAT_ID
    if ADMIN_TELEGRAM_IDS:
        return min(ADMIN_TELEGRAM_IDS)
    return None


def collect_gate3_health(*, days: int = 7) -> dict[str, Any]:
    """جمع‌آوری وضعیت واقعی دروازهٔ ۳ (آمار انتشار ۷ روز اخیر، خطاها، توکن‌ها و کانال هشدار)."""
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    published_days: set[str] = set()
    published_total = 0
    failed_publishes = 0
    duplicate_attempts_blocked = 0

    try:
        with db_mod.db() as conn:
            rows = conn.execute(
                """
                SELECT published_at, result
                FROM publishing_logs
                WHERE published_at >= ?
                ORDER BY published_at DESC
                """,
                (cutoff,),
            ).fetchall()
            for r in rows:
                res_s = str(r["result"] or "").lower()
                if res_s in ("ok", "published", "success") or res_s.startswith("ok"):
                    published_total += 1
                    day = str(r["published_at"] or "")[:10]
                    if day:
                        published_days.add(day)
                else:
                    failed_publishes += 1
                    if "duplicate" in res_s:
                        duplicate_attempts_blocked += 1
    except Exception:
        pass

    err_counts = get_error_counts()
    total_runtime_errors = sum(err_counts.values())

    return {
        "window_days": days,
        "published_total": published_total,
        "published_unique_days": len(published_days),
        "published_days": sorted(published_days),
        "gate3_7day_passed": len(published_days) >= 7 and failed_publishes == 0,
        "failed_publishes": failed_publishes,
        "duplicate_attempts_blocked": duplicate_attempts_blocked,
        "runtime_errors_total": total_runtime_errors,
        "runtime_errors_by_module": err_counts,
        "env_checks": {
            "FOOTBALL_DATA_ORG_TOKEN": bool(os.environ.get("FOOTBALL_DATA_ORG_TOKEN", "").strip()),
            "TELEGRAM_BOT_TOKEN": bool(TELEGRAM_BOT_TOKEN),
            "TELEGRAM_CHANNEL_ID": bool(TELEGRAM_CHANNEL_ID),
            "ALERT_TARGET": resolve_alert_chat_id() is not None,
        },
        "alert_target": resolve_alert_chat_id(),
    }


def format_gate3_report_ascii(health: dict[str, Any] | None = None) -> str:
    """گزارش خوانای کنسول ویندوز (ASCII) برای دستور `python run.py gate3-check`."""
    h = health if health is not None else collect_gate3_health()
    ec = h["env_checks"]
    lines = [
        "=== XGPedia Gate 3 (7-Day Trial) & Alert Readiness ===",
        f"  Tokens: FDO={'OK' if ec['FOOTBALL_DATA_ORG_TOKEN'] else 'MISSING'} | "
        f"TG_BOT={'OK' if ec['TELEGRAM_BOT_TOKEN'] else 'MISSING'} | "
        f"TG_CHANNEL={'OK' if ec['TELEGRAM_CHANNEL_ID'] else 'MISSING'} | "
        f"ALERT_TARGET={'OK' if ec['ALERT_TARGET'] else 'MISSING'}",
        f"  Alert Chat Target : {h['alert_target'] or 'NOT CONFIGURED'}",
        f"  Published (last {h['window_days']}d): {h['published_total']} posts across {h['published_unique_days']}/7 unique days",
        f"  Failed Publishes  : {h['failed_publishes']}",
        f"  Runtime Errors    : {h['runtime_errors_total']} ({len(h['runtime_errors_by_module'])} modules)",
        f"  Gate 3 Verdict    : {'PASSED (7/7 days clean)' if h['gate3_7day_passed'] else 'IN PROGRESS'}",
    ]
    return "\n".join(lines)


def format_alert_digest_fa(health: dict[str, Any] | None = None) -> str:
    """گزارش فارسی آماده ارسال به کانال هشدار/ادمین تلگرام."""
    h = health if health is not None else collect_gate3_health()
    errs = h["runtime_errors_by_module"]
    status_icon = "✅" if (h["failed_publishes"] == 0 and h["runtime_errors_total"] == 0) else "⚠️"
    lines = [
        f"{status_icon} <b>گزارش وضعیت و هشدار XGPedia (دروازهٔ ۳)</b>",
        f"• انتشار ۷ روز اخیر: <b>{h['published_total']}</b> پست در <b>{h['published_unique_days']}/۷</b> روز",
        f"• خطای انتشار: <b>{h['failed_publishes']}</b> | خطای خاموش ثبت‌شده: <b>{h['runtime_errors_total']}</b>",
    ]
    if errs:
        top = sorted(errs.items(), key=lambda kv: -kv[1])[:5]
        lines.append("• پرتکرارترین خطاها: " + "، ".join(f"<code>{k}</code> ({v})" for k, v in top))
    return "\n".join(lines)


async def send_alert_digest_telegram(
    *,
    send_fn: Callable[[str | int, str], Awaitable[Any]] | None = None,
    dry_run: bool = False,
    max_retries: int = 3,
    backoff_sec: float = 0.5,
) -> dict[str, Any]:
    """ارسال گزارش هشدار به کانال `ALERT_TELEGRAM_CHAT_ID` (یا ادمین) با retry خودکار روی خطاهای گذرا."""
    chat_id = resolve_alert_chat_id()
    if chat_id is None:
        raise ValueError("Neither ALERT_TELEGRAM_CHAT_ID nor ADMIN_TELEGRAM_IDS is configured.")

    text = format_alert_digest_fa()
    if dry_run:
        return {"sent": False, "dry_run": True, "chat_id": chat_id, "attempts": 0, "text": text}

    if send_fn is None:
        if not TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN is not configured.")
        import httpx

        async def _default_send(cid: str | int, body: str) -> dict[str, Any]:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json={"chat_id": cid, "text": body, "parse_mode": "HTML"})
                resp.raise_for_status()
                return resp.json()

        send_fn = _default_send

    last_exc: Exception | None = None
    for attempt in range(1, max(1, max_retries) + 1):
        try:
            res = await send_fn(chat_id, text)
            return {"sent": True, "dry_run": False, "chat_id": chat_id, "attempts": attempt, "result": res}
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries and backoff_sec > 0:
                await asyncio.sleep(backoff_sec * attempt)
    assert last_exc is not None
    raise last_exc
