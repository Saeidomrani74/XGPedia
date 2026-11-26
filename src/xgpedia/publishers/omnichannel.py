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
    """آداپتور انتشار خودکار در ایکس (X / Twitter API v2) با تمدید خودکار Access/Refresh Token."""

    platform_id = "x"
    label_fa = "ایکس (X)"
    env_keys = ("X_CLIENT_ID", "X_CLIENT_SECRET")

    def is_configured(self) -> bool:
        from src.xgpedia.publishers.x_oauth import is_x_oauth_configured
        return is_x_oauth_configured()

    async def _post_tweet(self, caption: str) -> PublishOutcome:
        if not self.is_configured():
            return PublishOutcome(self.platform_id, self.label_fa, False, skipped=True, error="not_configured")
        from src.xgpedia.publishers.x_oauth import get_valid_x_access_token
        text = fit_tweet_text(caption)
        hk = "omni:x"
        t0 = time.perf_counter()
        try:
            import httpx

            def _do() -> dict[str, Any]:
                token = get_valid_x_access_token()
                resp = httpx.post(
                    "https://api.x.com/2/tweets",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json={"text": text},
                    timeout=20.0,
                )
                # اگر توکن منقضی شده بود (401)، یک‌بار خودکار رفرش کن و دوباره بفرست
                if resp.status_code == 401:
                    token = get_valid_x_access_token(force_refresh=True)
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


IG_SESSION_FILE = Path("data") / "ig_session.json"


def _ensure_jpeg_for_ig(image_path: Path) -> Path:
    """تبدیل PNG به JPEG باکیفیت (اینستاگرام در آپلود مستقیم فقط JPEG می‌پذیرد)."""
    if image_path.suffix.lower() in (".jpg", ".jpeg"):
        return image_path
    out_jpg = image_path.with_suffix(".ig.jpg")
    try:
        from PIL import Image
        with Image.open(image_path) as im:
            im.convert("RGB").save(out_jpg, format="JPEG", quality=93, optimize=True)
        return out_jpg
    except Exception:
        return image_path


def _extract_video_thumbnail_ffmpeg(video_path: Path) -> Path | None:
    """استخراج تامبنیل JPEG از فریم قهرمان ویدیو (ثانیه ۲.۵) با FFmpeg برای آپلود ریلز اینستاگرام بدون نیاز به MoviePy."""
    import subprocess
    from src.xgpedia.media.video_pipeline import find_ffmpeg

    thumb_p = video_path.with_suffix(".jpg")
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return thumb_p if thumb_p.exists() else None
    for ss in ("2.5", "0.5"):
        try:
            proc = subprocess.run(
                [ffmpeg, "-y", "-ss", ss, "-i", str(video_path), "-vframes", "1", "-q:v", "2", str(thumb_p)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20.0,
            )
            if proc.returncode == 0 and thumb_p.exists() and thumb_p.stat().st_size > 1000:
                return thumb_p
        except Exception:
            continue
    return thumb_p if thumb_p.exists() else None


_MODERN_IG_DEVICE = {
    "app_version": "361.0.0.46.88",
    "android_version": 34,
    "android_release": "14",
    "dpi": "420dpi",
    "resolution": "1080x2400",
    "manufacturer": "Google",
    "device": "shiba",
    "model": "Pixel 8",
    "cpu": "tensor",
    "version_code": "676531961",
}


def _build_ig_client() -> Any:
    try:
        from instagrapi import Client
    except ImportError as exc:
        raise RuntimeError("برای اتصال مستقیم اینستاگرام ابتدا دستور `pip install instagrapi` را اجرا کنید.") from exc

    cl = Client()
    proxy = (os.getenv("IG_PROXY_URL") or "").strip()
    if proxy:
        cl.set_proxy(proxy)
    try:
        cl.set_device(_MODERN_IG_DEVICE)
    except Exception:
        pass
    if IG_SESSION_FILE.exists():
        try:
            cl.load_settings(str(IG_SESSION_FILE))
        except Exception:
            pass
    return cl


def _authenticate_ig_client(cl: Any) -> str:
    """ورود ایمن به اینستاگرام: اولویت ۱ با IG_SESSIONID (بدون خطای ClientNeedsUpgradeError)، اولویت ۲ با نام کاربری/رمز."""
    sess_id = (os.getenv("IG_SESSIONID") or "").strip()
    user = (os.getenv("IG_USERNAME") or "").strip()
    pwd = (os.getenv("IG_PASSWORD") or "").strip()

    if sess_id:
        import urllib.parse
        cl.login_by_sessionid(urllib.parse.unquote(sess_id))
        IG_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        cl.dump_settings(str(IG_SESSION_FILE))
        try:
            return str(getattr(cl.account_info(), "username", "") or user or "instagram")
        except Exception:
            return user or "instagram"

    if user and pwd:
        try:
            cl.login(user, pwd)
        except Exception as exc:
            if "ClientNeedsUpgradeError" in type(exc).__name__ or "out of date" in str(exc).lower():
                raise RuntimeError(
                    "اینستاگرام ورود با رمز را به دلیل نسخهٔ اپ مسدود کرد. "
                    "راه‌حل قطعی (۱۵ ثانیه): در مرورگر وارد instagram.com شو ← F12 ← تب Application ← Cookies ← "
                    "مقدار کوکی `sessionid` را کپی و در `.env` به‌صورت `IG_SESSIONID=...` بگذار و دوباره `python run.py ig-auth` بزن."
                ) from exc
            raise
        IG_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        cl.dump_settings(str(IG_SESSION_FILE))
        return user
    raise RuntimeError("مقدار IG_SESSIONID (پیشنهادی) یا IG_USERNAME/IG_PASSWORD در فایل .env تنظیم نشده است.")


def run_interactive_ig_login() -> dict[str, Any]:
    """ورود یک‌باره به اینستاگرام (با IG_SESSIONID یا رمز) و ذخیرهٔ نشست در data/ig_session.json."""
    cl = _build_ig_client()
    uname = _authenticate_ig_client(cl)
    print(f"[OK] Instagram session verified & saved to {IG_SESSION_FILE} (@{uname})")
    return {"ok": True, "username": uname, "session": str(IG_SESSION_FILE)}


class InstagramAdapter:
    """آداپتور هوشمند اینستاگرام با ۳ روش (بدون وابستگی اجباری به Meta for Developers):
      1. مستقیم با `instagrapi` (IG_USERNAME + IG_PASSWORD — آپلود مستقیم عکس ۴:۵ و ریلز ۹:۱۶ از سیستم)
      2. رسمی Meta Graph API (IG_ACCESS_TOKEN + IG_USER_ID + IG_PUBLIC_MEDIA_BASE_URL)
      3. وب‌هوک Make.com / n8n (IG_WEBHOOK_URL)
    """

    platform_id = "instagram"
    label_fa = "اینستاگرام (Instagram)"
    env_keys = ("IG_SESSIONID",)

    def _mode(self) -> str:
        if (os.getenv("IG_ACCESS_TOKEN") or "").strip() and (os.getenv("IG_USER_ID") or "").strip() and (os.getenv("IG_PUBLIC_MEDIA_BASE_URL") or "").strip():
            return "graph"
        if (os.getenv("IG_SESSIONID") or "").strip() or ((os.getenv("IG_USERNAME") or "").strip() and (os.getenv("IG_PASSWORD") or "").strip()):
            return "direct"
        if (os.getenv("IG_WEBHOOK_URL") or "").strip():
            return "webhook"
        return ""

    def is_configured(self) -> bool:
        return bool(self._mode())

    async def _publish_ig(self, media_path: Path, caption: str, *, is_video: bool) -> PublishOutcome:
        mode = self._mode()
        if not mode:
            return PublishOutcome(self.platform_id, self.label_fa, False, skipped=True, error="not_configured")
        plain_cap = strip_html_for_plain(caption)[:2200]
        hk = "omni:instagram"
        t0 = time.perf_counter()
        try:
            if mode == "direct":
                def _do_direct() -> str:
                    cl = _build_ig_client()
                    _authenticate_ig_client(cl)
                    if is_video:
                        thumb_p = _extract_video_thumbnail_ffmpeg(media_path)
                        if thumb_p:
                            media = cl.clip_upload(str(media_path), caption=plain_cap, thumbnail=str(thumb_p))
                        else:
                            media = cl.clip_upload(str(media_path), caption=plain_cap)
                    else:
                        jpg_p = _ensure_jpeg_for_ig(media_path)
                        media = cl.photo_upload(str(jpg_p), caption=plain_cap)
                    return str(getattr(media, "pk", "") or getattr(media, "id", "ok"))

                mid = await asyncio.to_thread(_do_direct)
                api_health.record_success(hk, (time.perf_counter() - t0) * 1000.0)
                return PublishOutcome(self.platform_id, self.label_fa, True, message_id=mid)

            if mode == "webhook":
                import httpx

                def _do_hook() -> str:
                    url = (os.getenv("IG_WEBHOOK_URL") or "").strip()
                    with open(media_path, "rb") as fh:
                        r = httpx.post(
                            url,
                            data={"caption": plain_cap, "media_type": "REELS" if is_video else "IMAGE"},
                            files={"file": (media_path.name, fh)},
                            timeout=40.0,
                        )
                    r.raise_for_status()
                    return str(r.status_code)

                mid = await asyncio.to_thread(_do_hook)
                api_health.record_success(hk, (time.perf_counter() - t0) * 1000.0)
                return PublishOutcome(self.platform_id, self.label_fa, True, message_id=mid)

            # mode == "graph"
            import httpx
            token = (os.getenv("IG_ACCESS_TOKEN") or "").strip()
            uid = (os.getenv("IG_USER_ID") or "").strip()
            base = (os.getenv("IG_PUBLIC_MEDIA_BASE_URL") or "").strip().rstrip("/")
            public_url = f"{base}/{media_path.name}"

            def _do_graph() -> str:
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

            mid = await asyncio.to_thread(_do_graph)
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


def verify_omnichannel_connections(*, timeout: float = 10.0) -> list[dict[str, Any]]:
    """تست اتصال واقعی و بدون ارسال پست برای تمام پلتفرم‌های پیکربندی‌شده در `.env`."""
    import httpx

    results: list[dict[str, Any]] = []
    for ad in ALL_ADAPTERS:
        if not ad.is_configured():
            results.append({
                "platform": ad.platform_id,
                "label_fa": ad.label_fa,
                "configured": False,
                "ok": False,
                "detail": "کلیدها در .env تنظیم نشده‌اند",
            })
            continue
        try:
            if ad.platform_id == "bale":
                tok = (os.getenv("BALE_BOT_TOKEN") or "").strip()
                r = httpx.get(f"https://tapi.bale.ai/bot{tok}/getMe", timeout=timeout)
                r.raise_for_status()
                j = r.json()
                ok = bool(j.get("ok"))
                uname = ((j.get("result") or {}).get("username")) or ""
                detail = f"متصل شد (@{uname})" if ok else str(j.get("description") or "error")
            elif ad.platform_id == "eitaa":
                tok = (os.getenv("EITAA_TOKEN") or "").strip()
                r = httpx.get(f"https://eitaayar.ir/api/{tok}/getMe", timeout=timeout)
                r.raise_for_status()
                j = r.json()
                ok = bool(j.get("ok"))
                detail = "توکن ایتایار معتبر و متصل است" if ok else str(j.get("description") or "error")
            elif ad.platform_id == "x":
                from src.xgpedia.publishers.x_oauth import get_valid_x_access_token
                tok = get_valid_x_access_token()
                r = httpx.get("https://api.x.com/2/users/me", headers={"Authorization": f"Bearer {tok}"}, timeout=timeout)
                if r.status_code == 401:
                    tok = get_valid_x_access_token(force_refresh=True)
                    r = httpx.get("https://api.x.com/2/users/me", headers={"Authorization": f"Bearer {tok}"}, timeout=timeout)
                r.raise_for_status()
                j = r.json()
                uname = ((j.get("data") or {}).get("username")) or ""
                ok = bool(uname)
                detail = f"متصل شد (@{uname})" if ok else str(j)[:120]
            else:  # instagram (direct / webhook / graph)
                ig_mode = ad._mode() if hasattr(ad, "_mode") else "graph"
                if ig_mode == "direct":
                    uname = (os.getenv("IG_USERNAME") or "").strip()
                    has_sess = IG_SESSION_FILE.exists()
                    try:
                        import instagrapi  # noqa: F401
                        ok = True
                        detail = f"حالت مستقیم instagrapi آماده (@{uname} | session={'موجود' if has_sess else 'نیاز به run.py ig-auth'})"
                    except ImportError:
                        ok = False
                        detail = "کتابخانه instagrapi نصب نیست (اجرا کنید: pip install instagrapi)"
                elif ig_mode == "webhook":
                    ok = True
                    detail = "حالت Webhook (Make.com/n8n) فعال است"
                else:
                    tok = (os.getenv("IG_ACCESS_TOKEN") or "").strip()
                    uid = (os.getenv("IG_USER_ID") or "").strip()
                    r = httpx.get(f"https://graph.facebook.com/v21.0/{uid}", params={"fields": "id,username", "access_token": tok}, timeout=timeout)
                    r.raise_for_status()
                    j = r.json()
                    uname = j.get("username") or j.get("id") or ""
                    ok = bool(uname)
                    detail = f"متصل شد (@{uname})" if ok else str(j)[:120]
            results.append({"platform": ad.platform_id, "label_fa": ad.label_fa, "configured": True, "ok": ok, "detail": detail})
        except Exception as e:
            results.append({"platform": ad.platform_id, "label_fa": ad.label_fa, "configured": True, "ok": False, "detail": f"{type(e).__name__}: {e}"})
    return results
