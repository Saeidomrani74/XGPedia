"""لایهٔ ۶ — Rendering: HTML/CSS به PNG/JPEG با Playwright.

چرا HTML؟ چون متن فارسی از HTML رندر می‌شود، مشکل اتصال حروف و bidi که در
Pillow/Matplotlib/FFmpeg به reshaper نیاز دارد به‌طور طبیعی حل است.
خروجی: PNG برای تلگرام/سایت، JPEG برای اینستاگرام (الزام API)، MP4 برای ویدیو.
"""
from __future__ import annotations

import asyncio
import pathlib
from typing import Literal

from playwright.async_api import async_playwright

Format = Literal["png", "jpeg"]


async def render(
    html_path: str,
    out_path: str,
    w: int = 1080,
    h: int = 1350,
    fmt: Format = "png",
    timeout_ms: int = 25_000,
) -> None:
    """رندر یک قالب HTML استودیویی به تصویر با timeout صریح و بستن تضمینی مرورگر."""
    async with async_playwright() as p:
        b = await p.chromium.launch(timeout=timeout_ms)
        try:
            pg = await b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
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
            await b.close()


def render_sync(html_path: str, out_path: str, w: int = 1080, h: int = 1350, fmt: Format = "png") -> None:
    asyncio.run(asyncio.wait_for(render(html_path, out_path, w, h, fmt), timeout=45.0))
