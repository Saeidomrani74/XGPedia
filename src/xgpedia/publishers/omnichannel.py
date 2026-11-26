"""فاز ۷ — موتور انتشار همزمان چندپلتفرمی (`Omnichannel Publishers`).

آداپتور استاندارد `PublisherAdapter` برای انتشار یک‌کلیکی همزمان در کنار تلگرام:
  1. **بله (Bale)** — API رسمی `https://tapi.bale.ai/bot{BALE_BOT_TOKEN}/sendPhoto|sendVideo`
  2. **ایتا (Eitaa)** — API رسمی ایتایار `https://eitaayar.ir/api/{EITAA_TOKEN}/sendFile`
  3. **ایکس (X / Twitter)** — API v2 `https://api.x.com/2/tweets` (با خلاصه‌سازی هوشمند ۲۸۰ کاراکتری)
  4. **اینستاگرام (Instagram Graph API)** — `https://graph.facebook.com/v21.0/{IG_USER_ID}/media`

قاعدهٔ ایمنی: هر پلتفرمی که کلیدش در `.env` تنظیم نشده باشد به‌طور خودکار رد می‌شود و خطای
یک پلتفرم فرعی هرگز انتشار اصلی در تلگرام را متوقف نمی‌کند.
"""
from __future__ import annotations

import asyncio
import html
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from src.xgpedia.core import api_health

log = logging.getLogger(__name__)


@dataclass
class PublishOutcome:
    platform: str
    label_fa: str
    ok: bool
    message_id: str = ""
    error: str = ""
    skipped: bool = False


class PublisherAdapter(Protocol):
    platform_id: str
    label_fa: str
    env_keys: tuple[str, ...]

    def is_configured(self) -> bool: ...

    async def publish_photo(self, image_path: Path, caption: str, *, title: str = "") -> PublishOutcome: ...

    async def publish_video(self, video_path: Path, caption: str, *, title: str = "") -> PublishOutcome: ...


def strip_html_for_plain(text: str) -> str:
    """تبدیل کپشن HTML تلگرام به متن سادهٔ تمیز برای پلتفرم‌هایی مثل بله/ایتا/ایکس/اینستاگرام."""
    s = re.sub(r"<br\s*/?>", "\n", str(text or ""), flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).strip()


def fit_tweet_text(text: str, max_len: int = 276) -> str:
    """تطبیق کپشن فارسی با سقف ۲۸۰ کاراکتر ایکس (X) با حفظ هشتگ اصلی."""
    plain = strip_html_for_plain(text)
    if len(plain) <= max_len:
        return plain
    cut = plain[: max_len - 1].rsplit(" ", 1)[0].rstrip(".,،؛:")
    return (cut or plain[: max_len - 1]) + "…"


class BaleAdapter:
    """آداپتور رسمی پیام‌رسان بله (Bale Bot API — همسان با Bot API تلگرام)."""

    platform_id = "bale"
    label_fa = "بله (Bale)"
    env_keys = ("BALE_BOT_TOKEN", "BALE_CHANNEL_ID")

    def is_configured(self) -> bool:
        return bool((os.getenv("BALE_BOT_TOKEN") or "").strip() and (os.getenv("BALE_CHANNEL_ID") or "").strip())

    async def _send_media(self, method: str, field: str, media_path: Path, caption: str) -> PublishOutcome:
        if not self.is_configured():
            return PublishOutcome(self.platform_id, self.label_fa, False, skipped=True, error="not_configured")
        token = (os.getenv("BALE_BOT_TOKEN") or "").strip()
        chat_id = (os.getenv("BALE_CHANNEL_ID") or "").strip()
        url = f"https://tapi.bale.ai/bot{token}/{method}"
        plain_cap = strip_html_for_plain(caption)[:1024]
        hk = "omni:bale"
        t0 = time.perf_counter()
        try:
            import httpx

            def _do() -> dict[str, Any]:
                with open(media_path, "rb") as fh:
                    resp = httpx.post(
                        url,
                        data={"chat_id": chat_id, "caption": plain_cap},
                        files={field: (media_path.name, fh)},
                        timeout=30.0,
                    )
                resp.raise_for_status()
                return resp.json()

            data = await asyncio.to_thread(_do)
            if data.get("ok"):
                mid = str(((data.get("result") or {}).get("message_id")) or "")
                api_health.record_success(hk, (time.perf_counter() - t0) * 1000.0)
                return PublishOutcome(self.platform_id, self.label_fa, True, message_id=mid)
            err = str(data.get("description") or "bale_api_error")
            api_health.record_failure(hk, err)
            return PublishOutcome(self.platform_id, self.label_fa, False, error=err)
        except Exception as e:
            api_health.record_failure(hk, f"{type(e).__name__}: {e}")
            return PublishOutcome(self.platform_id, self.label_fa, False, error=f"{type(e).__name__}: {e}")

    async def publish_photo(self, image_path: Path, caption: str, *, title: str = "") -> PublishOutcome:
        return await self._send_media("sendPhoto", "photo", image_path, caption)

    async def publish_video(self, video_path: Path, caption: str, *, title: str = "") -> PublishOutcome:
        return await self._send_media("sendVideo", "video", video_path, caption)


class EitaaAdapter:
    """آداپتور رسمی پیام‌رسان ایتا از طریق سرویس ایتایار (`eitaayar.ir/api`)."""

    platform_id = "eitaa"
    label_fa = "ایتا (Eitaa)"
    env_keys = ("EITAA_TOKEN", "EITAA_CHAT_ID")

    def is_configured(self) -> bool:
        return bool((os.getenv("EITAA_TOKEN") or "").strip() and (os.getenv("EITAA_CHAT_ID") or "").strip())

    async def _send_file(self, media_path: Path, caption: str, title: str = "") -> PublishOutcome:
        if not self.is_configured():
            return PublishOutcome(self.platform_id, self.label_fa, False, skipped=True, error="not_configured")
        token = (os.getenv("EITAA_TOKEN") or "").strip()
        chat_id = (os.getenv("EITAA_CHAT_ID") or "").strip()
        url = f"https://eitaayar.ir/api/{token}/sendFile"
        plain_cap = strip_html_for_plain(caption)[:2000]
        hk = "omni:eitaa"
        t0 = time.perf_counter()
        try:
            import httpx

            def _do() -> dict[str, Any]:
                with open(media_path, "rb") as fh:
                    resp = httpx.post(
                        url,
                        data={"chat_id": chat_id, "caption": plain_cap, "title": title or media_path.name},
                        files={"file": (media_path.name, fh)},
                        timeout=35.0,
                    )
                resp.raise_for_status()
                return resp.json()

            data = await asyncio.to_thread(_do)
            if data.get("ok"):
                mid = str(((data.get("result") or {}).get("message_id")) or "")
                api_health.record_success(hk, (time.perf_counter() - t0) * 1000.0)
                return PublishOutcome(self.platform_id, self.label_fa, True, message_id=mid)
            err = str(data.get("description") or "eitaa_api_error")
            api_health.record_failure(hk, err)
            return PublishOutcome(self.platform_id, self.label_fa, False, error=err)
        except Exception as e:
            api_health.record_failure(hk, f"{type(e).__name__}: {e}")
            return PublishOutcome(self.platform_id, self.label_fa, False, error=f"{type(e).__name__}: {e}")

    async def publish_photo(self, image_path: Path, caption: str, *, title: str = "") -> PublishOutcome:
        return await self._send_file(image_path, caption, title=title)

    async def publish_video(self, video_path: Path, caption: str, *, title: str = "") -> PublishOutcome:
        return await self._send_file(video_path, caption, title=title)


class XTwitterAdapter:
    """آداپتور انتشار خودکار در ایکس (X / Twitter API v2)."""

    platform_id = "x"
    label_fa = "ایکس (X)"
    env_keys = ("X_USER_ACCESS_TOKEN",)

    def is_configured(self) -> bool:
        return bool((os.getenv("X_USER_ACCESS_TOKEN") or "").strip())

    async def _post_tweet(self, caption: str) -> PublishOutcome:
        if not self.is_configured():
            return PublishOutcome(self.platform_id, self.label_fa, False, skipped=True, error="not_configured")
        token = (os.getenv("X_USER_ACCESS_TOKEN") or "").strip()
        text = fit_tweet_text(caption)
        hk = "omni:x"
        t0 = time.perf_counter()
        try:
            import httpx

            def _do() -> dict[str, Any]:
                resp = httpx.post(
                    "https://api.x.com/2/tweets",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json={"text": text},
                    timeout=20.0,
                )
                resp.raise_for_status()
                return resp.json()

            data = await asyncio.to_thread(_do)
            tid = str(((data.get("data") or {}).get("id")) or "")
            if tid:
                api_health.record_success(hk, (time.perf_counter() - t0) * 1000.0)
                return PublishOutcome(self.platform_id, self.label_fa, True, message_id=tid)
            return PublishOutcome(self.platform_id, self.label_fa, False, error=str(data)[:160])
        except Exception as e:
            api_health.record_failure(hk, f"{type(e).__name__}: {e}")
            return PublishOutcome(self.platform_id, self.label_fa, False, error=f"{type(e).__name__}: {e}")

    async def publish_photo(self, image_path: Path, caption: str, *, title: str = "") -> PublishOutcome:
        return await self._post_tweet(caption)

    async def publish_video(self, video_path: Path, caption: str, *, title: str = "") -> PublishOutcome:
        return await self._post_tweet(caption)


class InstagramAdapter:
    """آداپتور رسمی اینستاگرام از طریق Meta Graph API (نیازمند URL عمومی فایل در IG_PUBLIC_MEDIA_BASE_URL)."""

    platform_id = "instagram"
    label_fa = "اینستاگرام (Instagram)"
    env_keys = ("IG_ACCESS_TOKEN", "IG_USER_ID", "IG_PUBLIC_MEDIA_BASE_URL")

    def is_configured(self) -> bool:
        return all((os.getenv(k) or "").strip() for k in self.env_keys)

    async def _publish_ig(self, media_path: Path, caption: str, *, is_video: bool) -> PublishOutcome:
        if not self.is_configured():
            return PublishOutcome(self.platform_id, self.label_fa, False, skipped=True, error="not_configured")
        token = (os.getenv("IG_ACCESS_TOKEN") or "").strip()
        uid = (os.getenv("IG_USER_ID") or "").strip()
        base = (os.getenv("IG_PUBLIC_MEDIA_BASE_URL") or "").strip().rstrip("/")
        public_url = f"{base}/{media_path.name}"
        plain_cap = strip_html_for_plain(caption)[:2200]
        hk = "omni:instagram"
        t0 = time.perf_counter()
        try:
            import httpx

            def _do() -> str:
                payload: dict[str, Any] = {"caption": plain_cap, "access_token": token}
                if is_video:
                    payload["media_type"] = "REELS"
                    payload["video_url"] = public_url
                else:
                    payload["image_url"] = public_url
                r1 = httpx.post(f"https://graph.facebook.com/v21.0/{uid}/media", data=payload, timeout=30.0)
                r1.raise_for_status()
                creation_id = r1.json().get("id")
                if not creation_id:
                    raise RuntimeError(f"missing creation_id: {r1.text[:120]}")
                r2 = httpx.post(
                    f"https://graph.facebook.com/v21.0/{uid}/media_publish",
                    data={"creation_id": creation_id, "access_token": token},
                    timeout=30.0,
                )
                r2.raise_for_status()
                return str(r2.json().get("id") or creation_id)

            mid = await asyncio.to_thread(_do)
            api_health.record_success(hk, (time.perf_counter() - t0) * 1000.0)
            return PublishOutcome(self.platform_id, self.label_fa, True, message_id=mid)
        except Exception as e:
            api_health.record_failure(hk, f"{type(e).__name__}: {e}")
            return PublishOutcome(self.platform_id, self.label_fa, False, error=f"{type(e).__name__}: {e}")

    async def publish_photo(self, image_path: Path, caption: str, *, title: str = "") -> PublishOutcome:
        return await self._publish_ig(image_path, caption, is_video=False)

    async def publish_video(self, video_path: Path, caption: str, *, title: str = "") -> PublishOutcome:
        return await self._publish_ig(video_path, caption, is_video=True)


ALL_ADAPTERS: tuple[PublisherAdapter, ...] = (
    BaleAdapter(),
    EitaaAdapter(),
    XTwitterAdapter(),
    InstagramAdapter(),
)


def list_configured_adapters(platforms: list[str] | None = None) -> list[PublisherAdapter]:
    allowed = {p.lower() for p in platforms} if platforms else None
    out: list[PublisherAdapter] = []
    for ad in ALL_ADAPTERS:
        if allowed is not None and ad.platform_id not in allowed:
            continue
        if ad.is_configured():
            out.append(ad)
    return out


async def broadcast_photo(
    image_path: Path | str,
    caption: str,
    *,
    title: str = "",
    platforms: list[str] | None = None,
) -> list[PublishOutcome]:
    """انتشار همزمان تصویر در تمام پلتفرم‌های پیکربندی‌شده در `.env`."""
    adapters = list_configured_adapters(platforms)
    if not adapters:
        return []
    p = Path(image_path)
    tasks = [ad.publish_photo(p, caption, title=title) for ad in adapters]
    return list(await asyncio.gather(*tasks))


async def broadcast_video(
    video_path: Path | str,
    caption: str,
    *,
    title: str = "",
    platforms: list[str] | None = None,
) -> list[PublishOutcome]:
    """انتشار همزمان ویدیو ریلز (MP4) در تمام پلتفرم‌های پیکربندی‌شده در `.env`."""
    adapters = list_configured_adapters(platforms)
    if not adapters:
        return []
    p = Path(video_path)
    tasks = [ad.publish_video(p, caption, title=title) for ad in adapters]
    return list(await asyncio.gather(*tasks))


def format_omnichannel_status_fa() -> str:
    """گزارش وضعیت پلتفرم‌های انتشار همزمان و کلیدهای `.env` مورد نیاز هر پلتفرم."""
    lines = ["🌐 <b>وضعیت انتشار همزمان چندپلتفرمی (Omnichannel)</b>", "", "🟢 <b>تلگرام (Telegram)</b> — کانال اصلی فعال"]
    for ad in ALL_ADAPTERS:
        if ad.is_configured():
            lines.append(f"🟢 <b>{ad.label_fa}</b> — فعال (انتشار همزمان خودکار)")
        else:
            keys_str = ", ".join(f"<code>{k}</code>" for k in ad.env_keys)
            lines.append(f"⚪️ <b>{ad.label_fa}</b> — غیرفعال (نیاز به {keys_str} در <code>.env</code>)")
    lines.append("")
    lines.append("💡 هر پلتفرمی که کلیدهایش را در فایل <code>.env</code> اضافه کنید، هنگام زدن دکمهٔ «✅ انتشار فوری» به‌صورت همزمان کنار تلگرام منتشر می‌شود.")
    return "\n".join(lines)
