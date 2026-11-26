"""ابزار گزارش‌دهی زنده و پیوستهٔ پیشرفت عملیات در ربات تلگرام (ضد فریز و ضد محدودیت Flood).

هر زمان عملیات طولانی (رندر موشن‌گرافیک، تماس LLM، دانلود آمار زنده یا رندر Playwright)
در حال اجرا باشد، این کلاس:
  - نوار پیشرفت گرافیکی `[████░░░░░░] ۴۰٪` + زمان سپری‌شده (`۱۲ ثانیه`) را نمایش می‌دهد.
  - پیام وضعیت را حداکثر هر ۲.۵ ثانیه یک‌بار ویرایش می‌کند تا هم مخاطب همیشه از زنده بودن روند
    مطلع باشد و هم تلگرام خطای FloodWait ندهد.
  - در عملیات بدون پیشرفت درصدی (مثل انتظار برای پاسخ LLM)، هر ۵ ثانیه زمان سپری‌شده را
    به‌صورت خودکار به‌روزرسانی می‌کند تا هرگز حس هنگ کردن ایجاد نشود.
"""
from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable


def progress_bar(done: int, total: int, width: int = 10) -> str:
    if total <= 0:
        return "░" * width
    ratio = max(0.0, min(1.0, done / float(total)))
    filled = int(round(ratio * width))
    return "█" * filled + "░" * (width - filled)


class LiveProgressReporter:
    """مدیریت آپدیت زندهٔ پیام وضعیت تلگرام با throttle و تیکر خودکار زمان."""

    def __init__(
        self,
        edit_fn: Callable[[str], Awaitable[None]],
        *,
        min_interval_sec: float = 2.5,
        heartbeat_sec: float = 5.0,
    ) -> None:
        self._edit_fn = edit_fn
        self._min_interval = min_interval_sec
        self._heartbeat_sec = heartbeat_sec
        self._start_ts = time.monotonic()
        self._last_edit_ts = 0.0
        self._last_text = ""
        self._current_stage = "⏳ در حال پردازش..."
        self._hb_task: asyncio.Task | None = None

    def elapsed_sec(self) -> int:
        return int(time.monotonic() - self._start_ts)

    async def update(self, stage_text: str, *, force: bool = False) -> None:
        self._current_stage = stage_text
        now = time.monotonic()
        if not force and (now - self._last_edit_ts) < self._min_interval:
            return
        full = f"{stage_text}\n⏱ زمان سپری‌شده: {self.elapsed_sec()} ثانیه"
        if full == self._last_text:
            return
        self._last_edit_ts = now
        self._last_text = full
        try:
            await self._edit_fn(full)
        except Exception:
            pass

    def start_heartbeat(self) -> None:
        if self._hb_task is None or self._hb_task.done():
            self._hb_task = asyncio.create_task(self._heartbeat_loop())

    async def stop_heartbeat(self) -> None:
        if self._hb_task and not self._hb_task.done():
            self._hb_task.cancel()
            try:
                await self._hb_task
            except (asyncio.CancelledError, Exception):
                pass
        self._hb_task = None

    async def _heartbeat_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._heartbeat_sec)
                if (time.monotonic() - self._last_edit_ts) >= self._heartbeat_sec:
                    await self.update(self._current_stage, force=True)
        except asyncio.CancelledError:
            return
