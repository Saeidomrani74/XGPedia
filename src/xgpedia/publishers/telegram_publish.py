"""لایهٔ انتشار تلگرام — منطق خالص انتشار/تأیید، جدا از aiogram (NEXT_STEPS مرحلهٔ ۲).

چرا جداسازی: همهٔ قواعد (کپشن ایمن، فلو تأیید، idempotency) باید بدون توکن و بدون
شبکه تست‌شوند؛ transport واقعی aiogram در telegram_bot.py است و در تست‌ها FakeTransport
تزریق می‌شود.

فلوی وضعیت پست (D25):
  draft/validated ── submit ──▶ awaiting_approval ── approve(ادمین) ──▶ published
                                        │                                   ▲
                                        ├── reject ──▶ failed               │
                                        └── edit/rebuild ──▶ draft          │
  idempotency: اگر publishing_logs رکورد result='ok' برای پست داشته باشد،
  ارسال مجدد رد می‌شود (execution دوبارهٔ همان job پست تکراری نمی‌سازد).

همهٔ پیام‌های ترمینال انگلیسی/ASCII است (کنسول ویندوز RTL را خراب نشان می‌دهد)؛
متن پیام‌های تلگرام فارسی است.
"""
from __future__ import annotations

import html
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from src.xgpedia.config import ADMIN_TELEGRAM_IDS, ROOT, TELEGRAM_CHANNEL_ID
from src.xgpedia.db import db

# وضعیت‌های مجاز برای شروع فلوی انتشار — پست published قبلاً کارش تمام است
SUBMITTABLE_STATUSES = {"draft", "validated", "awaiting_approval"}
POST_TYPE_FA = {"preview": "پیش‌بازی", "post_match": "پس از بازی", "number_of_day": "عدد روز"}
HASHTAG_BY_TYPE = {
    "preview": "#پیش_بازی",
    "post_match": "#پس_از_بازی",
    "number_of_day": "#عدد_روز",
}


@dataclass
class SentMessage:
    """نتیجهٔ یک ارسال موفق — message_id برای رد و بدل و لاگ idempotency."""
    chat_id: int
    message_id: int


class TelegramTransport(Protocol):
    """قرارداد انتقال — aiogram واقعی یا Fake تست؛ فقط همین دو متد لازم است."""

    async def send_photo(
        self, chat_id: int, photo: str, caption: str, reply_markup: dict | None = None
    ) -> SentMessage: ...

    async def edit_text(self, chat_id: int, message_id: int, text: str) -> None: ...


def _now() -> str:
    return datetime.now(UTC).isoformat()


def is_admin(user_id: int) -> bool:
    """فقط ADMIN_TELEGRAM_IDS حق تصمیم دارند (D11) — سایر کاربران reply_markup نمی‌بینند."""
    return user_id in ADMIN_TELEGRAM_IDS



_SOURCE_LINKS: dict[str, tuple[str, str]] = {
    "football-data-org": ("Football-Data.org", "https://www.football-data.org"),
    "football-data.org": ("Football-Data.org", "https://www.football-data.org"),
    "football-data-co-uk": ("Football-Data.co.uk", "https://www.football-data.co.uk"),
    "football-data.co.uk": ("Football-Data.co.uk", "https://www.football-data.co.uk"),
    "understat": ("Understat", "https://understat.com"),
    "api-football": ("API-Football", "https://www.api-football.com"),
}


def _format_source_html(raw_source: str, facts: dict) -> str:
    """تبدیل نام منبع به هایپرلینک تمیز تلگرام بدون تاریخ جمع‌آوری و بدون hash."""
    prov = str((facts.get("source") or {}).get("provider") or "").strip().lower()
    raw_low = (raw_source or "").lower()
    for key, (label, url) in _SOURCE_LINKS.items():
        if key == prov or key in raw_low:
            return f'<i>منبع: <a href="{url}">{label}</a></i>'
    if prov:
        return f"<i>منبع: {html.escape(prov)}</i>"
    # حذف بخش‌های «جمع‌آوری ...» و «hash ...» در صورت نبود provider
    cleaned = (raw_source or "").split("·")[0].replace("منبع داده:", "").strip()
    return f"<i>منبع: {html.escape(cleaned)}</i>" if cleaned else ""


def build_caption(post: dict) -> str:
    """کپشن HTML تلگرام از پست آرشیوشده — همهٔ متن LLM با escape ایمن می‌شود.

    ساختار: تیتر بولد + کپشن + منبع + هشتگ نوع پست (همان caption.txt رندر).
    """
    draft = json.loads(post["draft_json"] or "{}")
    title = html.escape((post["title"] or draft.get("title") or "").strip())
    caption = html.escape((post["caption"] or draft.get("caption") or "").strip())
    source = html.escape((draft.get("source_note") or "").strip())
    tag = HASHTAG_BY_TYPE.get(post["post_type"], "")
    parts = [f"<b>{title}</b>"]
    if caption:
        parts.append(caption)
    facts = json.loads(post.get("fact_json") or "{}") if isinstance(post, dict) else {}
    if post["post_type"] in ("preview", "pre_match"):
        w_lines = []
        hf, af = facts.get("home") or {}, facts.get("away") or {}
        if hf.get("watchout"):
            w_lines.append(f"• {html.escape(str(hf.get('name_fa', 'میزبان')))}: {html.escape(str(hf['watchout']))}")
        if af.get("watchout"):
            w_lines.append(f"• {html.escape(str(af.get('name_fa', 'میهمان')))}: {html.escape(str(af['watchout']))}")
        if w_lines:
            parts.append("⚠️ <b>باید حواسشون بهش باشه:</b>\n" + "\n".join(w_lines))
    elif post["post_type"] == "post_match":
        bullets = [html.escape(str(b).strip()) for b in (draft.get("bullets") or []) if str(b).strip()]
        if bullets:
            parts.append("🎯 <b>روایت آماری و گره تاکتیکی بازی:</b>\n" + "\n".join(f"• {b}" for b in bullets))
    src_html = _format_source_html(draft.get("source_note") or "", facts)
    if src_html:
        parts.append(src_html)
    if tag:
        parts.append(tag)
    return "\n\n".join(parts)


def build_review_caption(post: dict) -> str:
    """کپشن پیام بازبینی برای ادمین — همان کپشن انتشار + برچسب وضعیت و پست.

    fit_caption تضمین می‌کند سر از سقف ۱۰۲۴ کپشن عکس تلگرام نزند
    (`MEDIA_CAPTION_TOO_LONG` کل ارسال را می‌انداخت).
    """
    head = (
        f"🟠 پیش‌نویس {POST_TYPE_FA.get(post['post_type'], post['post_type'])} — "
        f"post #{post['post_id']} · v{post['content_version']}\n"
        f"وضعیت: <i>نیازمند تأیید انسانی</i>"
    )
    return fit_caption(head, post)


def build_dry_run_caption(post: dict) -> str:
    """کپشن پیش‌نمایش dry-run — بدون دکمه است و راهنمای رسیدن به پیام بازبینی دارد.

    (تجربهٔ واقعی: کاربر پیش‌نمایش بدون دکمه را می‌دید و دنبال دکمهٔ تأیید می‌گشت.)
    """
    head = (
        "🧪 DRY-RUN (ارسال آزمایشی — چیزی در کانال منتشر نمی‌شود)\n"
        "این پیش‌نمایش عمداً دکمه ندارد. برای پیام بازبینی با دکمهٔ تأیید:\n"
        f"python run.py publish --post-id {post['post_id']}   (بدون --dry-run)"
    )
    return fit_caption(head, post)


# سقف کپشن عکس در Bot API — بر حسب واحد UTF-16 (ایموجی ۲ واحد است)
CAPTION_LIMIT = 1024


def _utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def _plain_body(post: dict) -> str:
    """متن خام کپشن بدون هیچ تگ HTML — فقط برای مسیر برش سرریز.

    برش وسط HTML تگِ باز رها می‌کند و کل پارس کپشن خطا می‌دهد؛ متن escape شده
    دیگر < > & ندارد، پس هر جای آن قابل برش است.
    """
    draft = json.loads(post["draft_json"] or "{}")
    parts = [
        (post["title"] or draft.get("title") or "").strip(),
        (post["caption"] or draft.get("caption") or "").strip(),
        (draft.get("source_note") or "").split("·")[0].strip(),
        HASHTAG_BY_TYPE.get(post["post_type"], ""),
    ]
    return "\n\n".join(p for p in parts if p)


def fit_caption(head: str, post: dict, limit: int = CAPTION_LIMIT) -> str:
    """head + کپشن پست، تضمین‌شده زیر سقف تلگرام.

    جا شود → همان کپشن HTML کامل؛ سرریز کند → متن بدون تگ برش‌خورده با «…».
    """
    base = build_caption(post)
    prefix = f"{head}\n\n" if head else ""
    if _utf16_len(prefix) + _utf16_len(base) <= limit:
        return prefix + base
    body = html.escape(_plain_body(post))
    budget = limit - _utf16_len(prefix) - 1  # ۱ برای «…»
    if _utf16_len(body) > budget:
        body = body[: max(budget - 2, 0)].rstrip() + "…"
    return prefix + body


def find_card_image(post_id: int, version: int, out_dir: Path | None = None) -> Path:
    """آخرین کارت رندرشدهٔ پست — render-post پیش از publish باید اجرا شده باشد."""
    out = Path(out_dir) if out_dir else ROOT / "output"
    files = [
        p
        for pattern in (f"post_{post_id}_v{version}_*.png", f"post_{post_id}_v{version}_*.jpeg")
        for p in out.glob(pattern)
        if p.is_file()
    ]
    if not files:
        raise FileNotFoundError(
            f"no rendered card for post {post_id} v{version} in {out} - run: "
            f"python run.py render-post --post-id {post_id}"
        )
    return max(files, key=lambda p: p.stat().st_mtime)


def already_published(post_id: int) -> dict | None:
    """رکورد انتشار موفق قبلی — هست؟ پس ارسال مجدد ممنوع (idempotency)."""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM publishing_logs WHERE post_id=? AND result='ok' ORDER BY id DESC",
            (post_id,),
        ).fetchone()
    return dict(row) if row else None


def load_post(post_id: int) -> dict:
    with db() as conn:
        row = conn.execute("SELECT * FROM posts WHERE post_id=?", (post_id,)).fetchone()
    if not row:
        raise LookupError(f"post {post_id} not found - see: python run.py list-posts")
    return dict(row)


def _set_status(post_id: int, status: str) -> None:
    with db() as conn:
        conn.execute("UPDATE posts SET status=? WHERE post_id=?", (status, post_id))


def _log_moderation(post_id: int, admin_user_id: int, action: str) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO moderation_logs (post_id, admin_user_id, action, created_at) VALUES (?,?,?,?)",
            (post_id, admin_user_id, action, _now()),
        )


async def submit_for_approval(
    post_id: int, transport: TelegramTransport, admin_ids: frozenset[int] | set[int]
) -> list[SentMessage]:
    """ارسال کارت + کپشن به چت هر ادمین با دکمهٔ تأیید/رد → awaiting_approval.

    پست باید render شده باشد؛ هیچ ارسالی به کانال انجام نمی‌شود (هرگز ارسال مستقیم — D11).
    """
    post = load_post(post_id)
    if already_published(post_id):
        raise ValueError(f"post {post_id} already published (idempotency)")
    if post["status"] not in SUBMITTABLE_STATUSES:
        raise ValueError(f"post {post_id} status '{post['status']}' is not submittable")
    if not admin_ids:
        raise ValueError("ADMIN_TELEGRAM_IDS is empty - no reviewer to send to")

    image = find_card_image(post_id, post["content_version"])
    caption = build_review_caption(post)
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ تأیید و انتشار", "callback_data": f"approve:{post_id}"},
            {"text": "❌ رد", "callback_data": f"reject:{post_id}"},
            {"text": "✏️ ویرایش", "callback_data": f"edit:{post_id}"},
        ]]
    }
    # تحویل per-ادمین: یک چتِ خراب (مثلاً شناسهٔ ربات به‌اشتباه در ADMIN_TELEGRAM_IDS،
    # یا کاربری که ربات را start نکرده «chat not found») نباید کل صف را از بین ببرد
    sent: list[SentMessage] = []
    for aid in sorted(admin_ids):
        try:
            sent.append(await transport.send_photo(aid, str(image), caption, reply_markup=keyboard))
        except Exception as e:  # noqa: BLE001 — فقط هشدار؛ بقیهٔ ادمین‌ها پیام می‌گیرند
            print(f"WARN - review not delivered to admin {aid}: {type(e).__name__}: {e}")
    if not sent:
        raise ValueError("review could not be delivered to any admin - check ADMIN_TELEGRAM_IDS"
                         " (human user ids who started the bot, not the bot id itself)")
    _set_status(post_id, "awaiting_approval")
    return sent


async def approve_and_publish(
    post_id: int, admin_user_id: int, transport: TelegramTransport,
    channel_id: str | int = "",
) -> dict:
    """تأیید ادمین → ارسال کارت به کانال → published + ثبت دو لاگ.

    idempotency: انتشار موفق قبلی → ValueError؛ رکورد publishing_logs با
    platform_message_id برای پیوند به پیام کانال ذخیره می‌شود.
    """
    if not is_admin(admin_user_id):
        raise PermissionError(f"user {admin_user_id} is not in ADMIN_TELEGRAM_IDS")
    if already_published(post_id):
        raise ValueError(f"post {post_id} already published (idempotency)")

    post = load_post(post_id)
    if post["status"] not in {"awaiting_approval", "scheduled"}:
        raise ValueError(f"post {post_id} status '{post['status']}' - submit it first")
    channel = channel_id or TELEGRAM_CHANNEL_ID
    if not channel:
        raise ValueError("TELEGRAM_CHANNEL_ID is empty - set it in .env")

    image = find_card_image(post_id, post["content_version"])
    chat_target = int(channel) if str(channel).lstrip("-").isdigit() else str(channel)
    # fit_caption با head خالی = همان build_caption، مگر آنکه از سقف رد شود
    msg = await transport.send_photo(chat_target, str(image), fit_caption("", post))
    with db() as conn:
        conn.execute(
            "INSERT INTO publishing_logs (post_id, platform_message_id, permalink, published_at, result)"
            " VALUES (?,?,?,?,?)",
            (post_id, f"{msg.chat_id}:{msg.message_id}", "", _now(), "ok"),
        )
    _set_status(post_id, "published")
    _log_moderation(post_id, admin_user_id, "approve")
    return {"chat_id": msg.chat_id, "message_id": msg.message_id}


async def reject_post(post_id: int, admin_user_id: int, reason: str = "") -> None:
    """رد ادمین → failed + لاگ تصمیم."""
    if not is_admin(admin_user_id):
        raise PermissionError(f"user {admin_user_id} is not in ADMIN_TELEGRAM_IDS")
    load_post(post_id)
    _set_status(post_id, "failed")
    _log_moderation(post_id, admin_user_id, "reject" + (f":{reason}" if reason else ""))


async def back_to_draft(post_id: int, admin_user_id: int, action: str = "edit") -> None:
    """ویرایش/بازسازی → بازگشت به صف تحریریه (draft) + لاگ."""
    if not is_admin(admin_user_id):
        raise PermissionError(f"user {admin_user_id} is not in ADMIN_TELEGRAM_IDS")
    load_post(post_id)
    _set_status(post_id, "draft")
    _log_moderation(post_id, admin_user_id, action)


async def publish_cli(post_id: int, dry_run: bool = False) -> int:
    """دروازهٔ CLI — بدون aiogram نمی‌تواند کار کند؛ transport واقعی از اینجا ساخته می‌شود.

    dry-run (NEXT_STEPS ۲.۴): کارت + کپشن فقط برای اولین ادمین می‌رود، بدون دکمه،
    بدون انتشار و بدون تغییر وضعیت؛ publishing_logs با result='dry_run' ثبت می‌شود.
    ارسال واقعی: پست به چت همهٔ ادمین‌ها با دکمهٔ تأیید می‌رود (انتشار با تأیید انسانی).
    """
    from src.xgpedia.publishers.telegram_bot import make_transport, validate_env

    validate_env()
    from aiogram import Bot

    from src.xgpedia.config import TELEGRAM_BOT_TOKEN

    async def _run() -> int:
        async with Bot(TELEGRAM_BOT_TOKEN) as bot:
            transport = make_transport(bot)
            if dry_run:
                post = load_post(post_id)
                image = find_card_image(post_id, post["content_version"])
                caption = build_dry_run_caption(post)
                admin = min(ADMIN_TELEGRAM_IDS)
                msg = await transport.send_photo(admin, str(image), caption)
                with db() as conn:
                    conn.execute(
                        "INSERT INTO publishing_logs (post_id, platform_message_id, permalink,"
                        " published_at, result) VALUES (?,?,?,?,?)",
                        (post_id, f"{msg.chat_id}:{msg.message_id}", "", _now(), "dry_run"),
                    )
                print(f"OK - dry-run sent to admin {admin} (message {msg.message_id}) - nothing published")
                return 0
            sent = await submit_for_approval(post_id, transport, set(ADMIN_TELEGRAM_IDS))
            for s in sent:
                print(f"OK - review request sent: chat {s.chat_id} message {s.message_id}")
            print(f"OK - post {post_id} is awaiting approval - admins approve via bot buttons")
            return 0

    return await _run()
