"""لایهٔ ۶ — Rendering: HTML/CSS به PNG/JPEG با Playwright.

چرا HTML؟ چون متن فارسی از HTML رندر می‌شود، مشکل اتصال حروف و bidi که در
Pillow/Matplotlib/FFmpeg به reshaper نیاز دارد به‌طور طبیعی حل است.
خروجی: PNG برای تلگرام/سایت، JPEG برای اینستاگرام (الزام API)، MP4 برای ویدیو.

در نسخهٔ v0.72.0 یک استخر مرورگر Chromium مشترک (Browser Reuse) اضافه شده است
تا رندرهای متوالی (مثل کاروسل‌ها) بدون راه‌اندازی مجدد Chromium اجرا شوند.
"""
from __future__ import annotations

import asyncio
import atexit
import pathlib
import threading
import weakref
from typing import Any, Literal

from playwright.async_api import async_playwright

Format = Literal["png", "jpeg"]

# استخر مرورگر به ازای هر Event Loop (ایمن برای async و جلوگیری از راه‌اندازی تکراری Chromium)
_LOOP_STATE: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, Any]] = weakref.WeakKeyDictionary()

def _get_loop_state() -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    state = _LOOP_STATE.get(loop)
    if state is None:
        state = {"lock": asyncio.Lock(), "pw": None, "browser": None}
        _LOOP_STATE[loop] = state
    return state


async def _get_shared_browser(timeout_ms: int = 25_000) -> Any:
    """دریافت یا راه‌اندازی نمونهٔ مشترک Chromium روی Event Loop فعلی."""
    state = _get_loop_state()
    async with state["lock"]:
        browser = state.get("browser")
        if browser is not None:
            try:
                if browser.is_connected():
                    return browser
            except Exception:
                pass
            # اتصال قطع شده؛ پاک‌سازی ایمن و راه‌اندازی مجدد
            await _close_state_unlocked(state)

        pw = await async_playwright().start()
        try:
            browser = await pw.chromium.launch(timeout=timeout_ms)
        except Exception:
            try:
                await pw.stop()
            except Exception:
                pass
            raise
        state["pw"] = pw
        state["browser"] = browser
        return browser


async def _close_state_unlocked(state: dict[str, Any]) -> None:
    browser = state.get("browser")
    pw = state.get("pw")
    state["browser"] = None
    state["pw"] = None
    if browser is not None:
        try:
            await browser.close()
        except Exception:
            pass
    if pw is not None:
        try:
            await pw.stop()
        except Exception:
            pass


async def close_browser_pool() -> None:
    """بستن تمیز مرورگر مشترک روی Event Loop فعلی."""
    loop = asyncio.get_running_loop()
    state = _LOOP_STATE.get(loop)
    if state is None:
        return
    async with state["lock"]:
        await _close_state_unlocked(state)


async def render(
    html_path: str,
    out_path: str,
    w: int = 1080,
    h: int = 1350,
    fmt: Format = "png",
    timeout_ms: int = 25_000,
) -> None:
    """رندر یک قالب HTML استودیویی به تصویر با استفادهٔ مجدد از Chromium و کانتکست ایزوله."""
    browser = await _get_shared_browser(timeout_ms=timeout_ms)
    ctx = await browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
    try:
        pg = await ctx.new_page()
        await pg.goto(
            pathlib.Path(html_path).resolve().as_uri(),
            wait_until="domcontentloaded",
            timeout=timeout_ms,
        )
        try:
            await pg.wait_for_load_state("networkidle", timeout=3000)
        except Exception:
            pass  # قالب یکپارچه ۱۰۰٪ آفلاین است و نیازی به CDN ندارد
        try:
            await asyncio.wait_for(pg.evaluate("document.fonts.ready"), timeout=5.0)
        except Exception:
            pass
        await pg.wait_for_timeout(120)
        kw = {"type": "jpeg", "quality": 90} if fmt == "jpeg" else {"type": "png"}
        await pg.screenshot(path=out_path, timeout=timeout_ms, **kw)
    finally:
        await ctx.close()


def render_sync(html_path: str, out_path: str, w: int = 1080, h: int = 1350, fmt: Format = "png") -> None:
    """رندر همزمان یک کارت با بستن تضمینی استخر مرورگر روی رشتهٔ فعلی (بدون deadlock روی ویندوز)."""
    async def _oneshot() -> None:
        try:
            await render(html_path, out_path, w, h, fmt)
        finally:
            await close_browser_pool()

    asyncio.run(asyncio.wait_for(_oneshot(), timeout=45.0))
