"""لایهٔ ۷/۸ — ربات تأیید/انتشار تلگرام (aiogram 3) — transport + polling.

منطق (کپشن، فلو، idempotency، لاگ‌ها) در telegram_publish.py است و اینجا فقط
انتقال واقعی aiogram + هندلرهای دکمه ساخته می‌شود؛ به همین دلیل تست‌های منطق
بدون توکن و شبکه سبز می‌مانند.

اجرا (long-running):  python -m src.xgpedia.publishers.telegram_bot
فلوی کامل: run.py publish --post-id N  →  پیام بازبینی برای ادمین‌ها با دکمه →
ادمین ✅ → کارت به TELEGRAM_CHANNEL_ID می‌رود → posts.status=published +
publishing_logs + moderation_logs. فقط ADMIN_TELEGRAM_IDS حق تصمیم دارند (D11).
"""
from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.xgpedia.config import ADMIN_TELEGRAM_IDS, TELEGRAM_BOT_TOKEN
from src.xgpedia.publishers import telegram_publish as tp

router = Router()
log = logging.getLogger("xgpedia.bot")


def validate_env() -> None:
    """خطای واضح قبل از هر تماس شبکه‌ای — بدون این‌ها ربات بی‌معنی است."""
    missing = [
        name for name, val in (
            ("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN),
            ("ADMIN_TELEGRAM_IDS", ADMIN_TELEGRAM_IDS),
        ) if not val
    ]
    if missing:
        raise SystemExit(f"[FAIL] missing env: {', '.join(missing)} - fill .env (see .env.example)")


class AiogramTransport:
    """پیاده‌سازی قرارداد TelegramTransport با aiogram — parse_mode=HTML و فقط PNG/JPEG."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send_photo(
        self, chat_id: int, photo: str, caption: str, reply_markup: dict | None = None
    ) -> tp.SentMessage:
        markup = None
        if reply_markup:  # dict ساده → markup واقعی aiogram
            markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(**btn) for btn in row]
                    for row in reply_markup["inline_keyboard"]
                ]
            )
        # مسیر محلی (C:\… در ویندوز، /home/… در لینوکس) باید با FSInputFile آپلود شود؛
        # رشتهٔ خالی به‌عنوان URL می‌رود و تلگرام «C:» را پورت تفسیر می‌کند
        # (Bad Request: invalid file HTTP URL / Wrong port number). فقط http(s) URL
        # یا file_id واقعی همان رشته می‌ماند.
        photo_obj: str | FSInputFile = photo
        if not photo.startswith(("http://", "https://")):
            photo_obj = FSInputFile(photo)
        msg: Message = await self._bot.send_photo(
            chat_id, photo=photo_obj, caption=caption, parse_mode="HTML", reply_markup=markup
        )
        return tp.SentMessage(chat_id=msg.chat.id, message_id=msg.message_id)

    async def edit_text(self, chat_id: int, message_id: int, text: str) -> None:
        try:
            await self._bot.edit_message_caption(
                chat_id, message_id, caption=text, parse_mode="HTML"
            )
        except TelegramBadRequest:
            pass  # پیام پیش از این ویرایش شده — ربات idempotent است


def make_transport(bot: Bot) -> AiogramTransport:
    return AiogramTransport(bot)


@router.callback_query(F.data.startswith(("approve:", "reject:", "edit:")))
async def on_decision(cb: CallbackQuery, bot: Bot) -> None:
    """دکمه‌های زیر پیام بازبینی — فقط ادمین؛ نتیجه در همان پیام ویرایش می‌شود."""
    if not tp.is_admin(cb.from_user.id):
        await cb.answer("شما مجاز به تصمیم‌گیری نیستید.", show_alert=True)
        return
    action, post_id = cb.data.split(":", 1)
    post_id = int(post_id)
    transport = make_transport(bot)
    try:
        if action == "approve":
            result = await tp.approve_and_publish(post_id, cb.from_user.id, transport)
            await transport.edit_text(
                cb.message.chat.id, cb.message.message_id,
                f"✅ منتشر شد — پیام کانال {result['message_id']}",
            )
            await cb.answer("منتشر شد.")
        elif action == "reject":
            await tp.reject_post(post_id, cb.from_user.id)
            await transport.edit_text(
                cb.message.chat.id, cb.message.message_id, "❌ رد شد — بازگشت به صف تحریریه."
            )
            await cb.answer("رد شد.")
        else:  # edit → بازگشت به draft برای بازنویسی
            await tp.back_to_draft(post_id, cb.from_user.id, action="edit")
            await transport.edit_text(
                cb.message.chat.id, cb.message.message_id, "✏️ به صف تحریریه بازگشت (draft)."
            )
            await cb.answer("بازگشت به صف.")
    except (ValueError, LookupError, PermissionError, FileNotFoundError) as e:
        await cb.answer(str(e)[:200], show_alert=True)
    log.info("moderation action=%s post=%s by=%s", action, post_id, cb.from_user.id)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    validate_env()
    bot = Bot(TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    @router.message(F.text == "/start")
    async def _start(m: Message) -> None:
        role = "ادمین" if tp.is_admin(m.from_user.id) else "کاربر"
        await m.answer(
            f"ربات انتشار XGPedia — {role}.\n"
            "پیش‌نویس‌ها با run.py publish برای شما می‌آیند؛ تأیید یعنی انتشار در کانال."
        )

    log.info("bot polling started - admins: %s", sorted(ADMIN_TELEGRAM_IDS))
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
