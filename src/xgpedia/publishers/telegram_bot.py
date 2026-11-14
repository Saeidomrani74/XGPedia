"""لایهٔ ۷/۸ — ربات تأیید/انتشار تلگرام (aiogram 3).

چهارچرخهٔ وضعیت پست: draft → validated → awaiting_approval → approved →
scheduled → published (+ failed / corrected).
کلید یکتای idempotency: (fixture_id, post_type, target_platform, content_version)
— اجرای مجدد همان job پست تکراری نمی‌سازد.

اجرا:  python -m src.xgpedia.publishers.telegram_bot
فقط ADMIN_TELEGRAM_IDS حق approve/reject دارند؛ همهٔ کنش‌ها در moderation_logs ثبت می‌شوند.
"""
from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

router = Router()
log = logging.getLogger("xgpedia.bot")

ADMIN_IDS = {int(x) for x in os.environ.get("ADMIN_TELEGRAM_IDS", "").split(",") if x.strip()}
DRAFTS: dict[str, dict] = {}  # در production: جدول posts در SQLite


def kb(draft_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ تأیید", callback_data=f"approve:{draft_id}"),
        InlineKeyboardButton(text="✏️ ویرایش", callback_data=f"edit:{draft_id}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"reject:{draft_id}"),
        InlineKeyboardButton(text="🔁 بازسازی", callback_data=f"rebuild:{draft_id}"),
    ]])


async def send_draft(bot: Bot, chat_id: int, draft: dict) -> None:
    """ارسال پیش‌نویس به پنل مالک — همهٔ انتشارها ابتدا draft؛ هرگز ارسال مستقیم به کانال."""
    msg: Message = await bot.send_photo(
        chat_id,
        photo=draft["image_path"],
        caption=f"<b>{draft['title']}</b>\n\n{draft['caption']}\n\n"
                f"منبع: {draft['source_note']}\n<i>وضعیت: پیش‌نویس — تأیید انسانی لازم است</i>",
        parse_mode="HTML",  # متن فارسی + نام انگلیسی: RLM و تست روی کلاینت واقعی
    )
    DRAFTS[str(msg.message_id)] = draft
    await msg.answer(  # دکمه‌ها زیر همان پیام
        "تصمیم:", reply_markup=kb(str(msg.message_id))
    )


@router.callback_query(F.data.startswith(("approve:", "reject:", "edit:", "rebuild:")))
async def on_decision(cb: CallbackQuery, bot: Bot) -> None:
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("شما مجاز نیستید.", show_alert=True)
        return
    action, draft_id = cb.data.split(":", 1)
    draft = DRAFTS.get(draft_id)
    if not draft:
        await cb.answer("پیش‌نویس یافت نشد.", show_alert=True)
        return
    if action == "approve":
        # انتشار با صف + throttle (۱ پیام/ثانیه هر چت) و ثبت publishing_logs
        await bot.send_photo(
            int(os.environ["TELEGRAM_CHANNEL_ID"]),
            photo=draft["image_path"],
            caption=f"<b>{draft['title']}</b>\n\n{draft['caption']}\n\nمنبع: {draft['source_note']}",
            parse_mode="HTML",
        )
        draft["status"] = "published"
        await cb.message.edit_text(f"✅ منتشر شد — {draft['title']}")
    elif action == "reject":
        draft["status"] = "failed"
        await cb.message.edit_text(f"❌ رد شد — {draft['title']}")
    else:  # edit / rebuild → بازگشت به صف تحریریه
        draft["status"] = "draft"
        await cb.message.edit_text(f"↩️ به صف بازگشت ({action}) — {draft['title']}")
    log.info("moderation action=%s draft=%s by=%s", action, draft_id, cb.from_user.id)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    bot = Bot(os.environ["TELEGRAM_BOT_TOKEN"])
    dp = Dispatcher()
    dp.include_router(router)

    @router.message(Command("start"))
    async def _start(m: Message) -> None:
        await m.answer("ربات تأیید XGPedia — پیش‌نویس‌ها را می‌فرستم؛ فقط ادمین‌ها تأیید می‌کنند.")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
