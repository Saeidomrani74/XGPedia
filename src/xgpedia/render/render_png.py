"""لایهٔ ۶ — Rendering: HTML/CSS به PNG/JPEG با Playwright.

چرا HTML؟ چون متن فارسی از HTML رندر می‌شود، مشکل اتصال حروف و bidi که در
Pillow/Matplotlib/FFmpeg به reshaper نیاز دارد به‌طور طبیعی حل است.
خروجی: PNG برای تلگرام/سایت، JPEG برای اینستاگرام (الزام API)، MP4 برای ویدیو.
"""
from __future__ import annotations

import pathlib
from typing import Literal

from playwright.async_api import async_playwright

Format = Literal["png", "jpeg"]


async def render(html_path: str, out_path: str, w: int = 1080, h: int = 1350, fmt: Format = "png") -> None:
    """رندر یک قالب HTML به تصویر — از نسخهٔ ۲ سند؛ با انتظار بارگذاری فونت.

    قواعد: رنگ و فونت فقط از brand.json؛ متن/عدد/نمودار فقط در لایهٔ HTML/SVG؛
    پس‌زمینه از کتابخانهٔ ثابت ۱۰-۲۰ تایی.
    """
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        await pg.goto(pathlib.Path(html_path).resolve().as_uri())
        await pg.evaluate("document.fonts.ready")  # پیش از اسکرین‌شات فونت‌ها آماده شوند
        kw = {"type": "jpeg", "quality": 90} if fmt == "jpeg" else {"type": "png"}
        await pg.screenshot(path=out_path, **kw)
        await b.close()


def render_sync(html_path: str, out_path: str, w: int = 1080, h: int = 1350, fmt: Format = "png") -> None:
    import asyncio

    asyncio.run(render(html_path, out_path, w, h, fmt))
