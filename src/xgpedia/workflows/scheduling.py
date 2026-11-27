"""زمان‌بندی انتشار پست‌ها به وقت تهران و اجرای خودکار صف انتشار (استخراج‌شده از today_workflow.py)."""
from __future__ import annotations


import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.xgpedia.config import CURRENT_SEASON_START, ROOT, team_name_fa
from src.xgpedia.db import db, init_db
from src.xgpedia.publishers import telegram_publish as tp

TEHRAN_TZ = timezone(timedelta(hours=3, minutes=30))
FA_TO_EN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")



def _tw():
    import src.xgpedia.today_workflow as tw_mod
    return tw_mod


def _now_utc(now_utc: datetime | None = None) -> datetime:
    return _tw()._now_utc(now_utc)


def _parse_utc(raw: str):
    return _tw()._parse_utc(raw)


def parse_today_tehran_time(
    time_str: str, now_utc: datetime | None = None
) -> tuple[str, str]:
    """پارس و اعتبارسنجی ساعت ۲۴ ساعته امروز به وقت تهران (مانند 09:35 یا ۰۹:۳۵).

    خروجی: `(scheduled_at_utc_iso, normalized_hhmm_tehran)`
    """
    cleaned = str(time_str or "").strip().translate(FA_TO_EN_DIGITS)
    m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", cleaned)
    if not m:
        raise ValueError(
            "فرمت ساعت نامعتبر است. لطفاً ساعت را با فرمت ۲۴ ساعته HH:MM وارد کنید (مثلاً 09:35 یا 21:15)."
        )
    hour, minute = int(m.group(1)), int(m.group(2))
    hhmm = f"{hour:02d}:{minute:02d}"

    now = _now_utc(now_utc)
    now_tehran = now.astimezone(TEHRAN_TZ)
    target_tehran = now_tehran.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target_tehran <= now_tehran + timedelta(seconds=10):
        raise ValueError(
            f"ساعت {hhmm} برای امروز گذشته است (ساعت فعلی تهران: {now_tehran.strftime('%H:%M')}). "
            "لطفاً ساعتی بعد از زمان فعلی امروز وارد کنید."
        )
    target_utc = target_tehran.astimezone(timezone.utc)
    return target_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), hhmm


def schedule_post_publish(
    post_id: int,
    time_hhmm: str,
    admin_user_id: int,
    *,
    now_utc: datetime | None = None,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    """ثبت زمان‌بندی انتشار خودکار یک پست برای ساعت مشخص‌شده در امروز (به وقت تهران)."""
    init_db()
    if not tp.is_admin(admin_user_id):
        raise PermissionError(f"کاربر {admin_user_id} در لیست ادمین‌ها نیست.")
    if tp.already_published(post_id):
        raise ValueError(f"پست #{post_id} قبلاً در کانال منتشر شده است.")

    post = tp.load_post(post_id)
    tp.find_card_image(post_id, post["content_version"], out_dir=out_dir)

    scheduled_at_utc, hhmm = parse_today_tehran_time(time_hhmm, now_utc=now_utc)
    now_iso = _now_utc(now_utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with db() as conn:
        # لغو زمان‌بندی قبلی همین پست در صورت وجود
        conn.execute(
            "UPDATE scheduled_publishes SET status = 'cancelled' "
            "WHERE post_id = ? AND status = 'pending'",
            (post_id,),
        )
        cur = conn.execute(
            """
            INSERT INTO scheduled_publishes
              (post_id, scheduled_at_utc, scheduled_time_tehran, scheduled_by_admin, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (post_id, scheduled_at_utc, hhmm, admin_user_id, now_iso),
        )
        sched_id = cur.lastrowid or 0
        conn.execute("UPDATE posts SET status = 'scheduled' WHERE post_id = ?", (post_id,))
        conn.execute(
            "INSERT INTO moderation_logs (post_id, admin_user_id, action, created_at) VALUES (?,?,?,?)",
            (post_id, admin_user_id, f"schedule:{hhmm}", now_iso),
        )

    return {
        "schedule_id": sched_id,
        "post_id": post_id,
        "scheduled_time_tehran": hhmm,
        "scheduled_at_utc": scheduled_at_utc,
    }


def cancel_scheduled_publish(schedule_id: int, admin_user_id: int) -> None:
    """لغو یک انتشار زمان‌بندی‌شدهٔ در انتظار."""
    init_db()
    if not tp.is_admin(admin_user_id):
        raise PermissionError(f"کاربر {admin_user_id} مجاز نیست.")
    with db() as conn:
        row = conn.execute(
            "SELECT post_id, status FROM scheduled_publishes WHERE id = ?", (schedule_id,)
        ).fetchone()
        if not row:
            raise LookupError(f"زمان‌بندی #{schedule_id} پیدا نشد.")
        if row["status"] != "pending":
            raise ValueError(f"زمان‌بندی #{schedule_id} در وضعیت '{row['status']}' است و قابل لغو نیست.")
        conn.execute("UPDATE scheduled_publishes SET status = 'cancelled' WHERE id = ?", (schedule_id,))
        conn.execute("UPDATE posts SET status = 'awaiting_approval' WHERE post_id = ?", (row["post_id"],))


def list_pending_schedules() -> list[dict[str, Any]]:
    """فهرست تمام پست‌های زمان‌بندی‌شدهٔ در انتظار انتشار."""
    init_db()
    with db() as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.post_id, s.scheduled_time_tehran, s.scheduled_at_utc,
                   s.scheduled_by_admin, p.title, p.fixture_id, p.post_type
            FROM scheduled_publishes s
            JOIN posts p ON p.post_id = s.post_id
            WHERE s.status = 'pending'
            ORDER BY s.scheduled_at_utc ASC
            """
        ).fetchall()
    return [dict(r) for r in rows]


async def run_due_scheduled_publishes(
    transport: tp.TelegramTransport,
    *,
    channel_id: str | int = "",
    now_utc: datetime | None = None,
    notify_fn: Callable[[int, str], Awaitable[None]] | None = None,
) -> list[dict[str, Any]]:
    """اجرای تمام زمان‌بندی‌هایی که زمان انتشارشان رسیده است (idempotent)."""
    init_db()
    now = _now_utc(now_utc)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    with db() as conn:
        due_rows = conn.execute(
            """
            SELECT id, post_id, scheduled_time_tehran, scheduled_by_admin
            FROM scheduled_publishes
            WHERE status = 'pending' AND scheduled_at_utc <= ?
            ORDER BY scheduled_at_utc ASC
            """,
            (now_iso,),
        ).fetchall()

    outcomes: list[dict[str, Any]] = []
    for row in due_rows:
        sid = row["id"]
        pid = row["post_id"]
        admin_id = row["scheduled_by_admin"]
        hhmm = row["scheduled_time_tehran"]
        try:
            res = await tp.approve_and_publish(pid, admin_id, transport, channel_id=channel_id)
            with db() as conn:
                conn.execute(
                    "UPDATE scheduled_publishes SET status='published', executed_at=? WHERE id=?",
                    (now_iso, sid),
                )
            outcomes.append({"schedule_id": sid, "post_id": pid, "ok": True, "message_id": res["message_id"]})
            if notify_fn:
                await notify_fn(
                    admin_id,
                    f"✅ انتشار زمان‌بندی‌شده ساعت {hhmm} با موفقیت انجام شد!\n"
                    f"پست #{pid} در کانال منتشر شد (شناسه پیام: {res['message_id']}).",
                )
        except Exception as e:
            err_msg = f"{type(e).__name__}: {e}"
            with db() as conn:
                conn.execute(
                    "UPDATE scheduled_publishes SET status='failed', error_detail=?, executed_at=? WHERE id=?",
                    (err_msg, now_iso, sid),
                )
            outcomes.append({"schedule_id": sid, "post_id": pid, "ok": False, "error": err_msg})
            if notify_fn:
                await notify_fn(
                    admin_id,
                    f"❌ خطا در انتشار زمان‌بندی‌شده ساعت {hhmm} برای پست #{pid}!\n"
                    f"علت دقیق: {err_msg}",
                )
    return outcomes
