"""لایهٔ ۷/۸ — ربات ادمین و انتشار تلگرام XGPedia (aiogram 3) + زمان‌بند خودکار پس‌زمینه.

اجرا:  python run.py bot   یا   python -m src.xgpedia.publishers.telegram_bot

قابلیت‌های پنل ادمین (فقط ADMIN_TELEGRAM_IDS — D11):
  - دکمهٔ «🔄 دریافت بازی‌های امروز»: همگام‌سازی آمار فصل + دریافت بازی‌های شروع‌نشدهٔ امروز
  - نمایش لیست بازی‌های واجد شرایط امروز (با ساعت کیک‌آف تهران) + دلیل دقیق نبود داده برای بازی‌های غیرقابل‌تولید
  - انتخاب هر بازی → تولید خودکار فکت‌ها + متن روان LLM + رندر کارت PNG استودیویی → ارسال پیش‌نمایش کامل
  - تأیید و انتشار فوری در کانال (✅) یا زمان‌بندی انتشار خودکار در ساعت ۲۴ ساعته امروز (⏰ مثل 09:35)
  - حلقهٔ زمان‌بند پس‌زمینه (هر ۱۵ ثانیه) برای انتشار خودکار پست‌های زمان‌بندی‌شده و گزارش نتیجه/خطا به ادمین
"""
from __future__ import annotations

import asyncio
import html
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.xgpedia.config import ADMIN_TELEGRAM_IDS, TELEGRAM_BOT_TOKEN
from src.xgpedia.publishers import telegram_publish as tp
from src.xgpedia import today_workflow as tw

router = Router()
log = logging.getLogger("xgpedia.bot")

# وضعیت موقت انتظار برای ورود ساعت ۲۴ ساعته توسط ادمین: {admin_id: post_id}
_AWAITING_SCHEDULE_TIME: dict[int, int] = {}
# نگاشت کوتاه برای fixture_idهای بلند (محدودیت ۶۴ بایتی callback_data تلگرام)
_FIXTURE_ALIAS: dict[str, str] = {}


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
        self, chat_id: int | str, photo: str, caption: str, reply_markup: dict | None = None
    ) -> tp.SentMessage:
        markup = None
        if reply_markup:
            markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(**btn) for btn in row]
                    for row in reply_markup["inline_keyboard"]
                ]
            )
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
            try:
                await self._bot.edit_message_text(
                    text, chat_id=chat_id, message_id=message_id, parse_mode="HTML"
                )
            except TelegramBadRequest:
                pass


def make_transport(bot: Bot) -> AiogramTransport:
    return AiogramTransport(bot)


# ─── کیبوردها و قالب‌های پیام پنل ادمین ───

def _main_panel_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 دریافت بازی‌های امروز", callback_data="today:sync")],
            [InlineKeyboardButton(text="📋 لیست بازی‌های امروز", callback_data="today:list")],
            [InlineKeyboardButton(text="⏰ صف انتشار زمان‌بندی‌شده", callback_data="today:schedules")],
        ]
    )


def _cb_for_fixture(fixture_id: str) -> str:
    if len(fixture_id.encode("utf-8")) <= 50:
        return f"gen:{fixture_id}"
    key = f"k{len(_FIXTURE_ALIAS) + 1}"
    for k, v in _FIXTURE_ALIAS.items():
        if v == fixture_id:
            return f"gen:{k}"
    _FIXTURE_ALIAS[key] = fixture_id
    return f"gen:{key}"


def _resolve_fixture(token: str) -> str:
    return _FIXTURE_ALIAS.get(token, token)


def _format_matches_message(
    matches: list[tw.TodayMatchInfo], header: str = ""
) -> tuple[str, InlineKeyboardMarkup]:
    lines: list[str] = []
    if header:
        lines.append(header)
        lines.append("")

    eligible = [m for m in matches if m.eligible]
    ineligible = [m for m in matches if not m.eligible]

    if not matches:
        lines.append("⚽ هیچ بازی شروع‌نشده‌ای برای امروز در دیتابیس ثبت نشده است.")
    else:
        if eligible:
            lines.append(f"🟢 <b>بازی‌های آماده برای تولید کارت پیش‌ازبازی ({len(eligible)} بازی):</b>")
            lines.append("روی هر بازی بزنید تا کارت + کپشن کامل تولید و ارسال شود:")
        else:
            lines.append("⚠️ هیچ‌کدام از بازی‌های امروز دادهٔ کافی برای تولید کارت ندارند.")

        if ineligible:
            lines.append("")
            lines.append(f"🔸 <b>بازی‌های بدون دادهٔ کافی ({len(ineligible)} بازی):</b>")
            for m in ineligible:
                lines.append(
                    f"• {html.escape(m.home_fa)} × {html.escape(m.away_fa)} ({m.kickoff_tehran})\n"
                    f"  علت: <i>{html.escape(m.ineligible_reason)}</i>"
                )

    rows: list[list[InlineKeyboardButton]] = []
    for m in eligible:
        badge = ""
        if m.existing_post_status == "published":
            badge = " ✅"
        elif m.scheduled_time:
            badge = f" ⏰{m.scheduled_time}"
        elif m.existing_post_id:
            badge = " 📝"
        btn_text = f"⚽ {m.home_fa} × {m.away_fa} | {m.kickoff_tehran}{badge}"
        rows.append([InlineKeyboardButton(text=btn_text, callback_data=_cb_for_fixture(m.fixture_id))])

    rows.append([
        InlineKeyboardButton(text="🔄 به‌روزرسانی از API", callback_data="today:sync"),
        InlineKeyboardButton(text="⏰ صف زمان‌بندی", callback_data="today:schedules"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


# ─── هندلرهای دستورها و پیام‌های متنی ───

@router.message(Command("start", "panel"))
async def on_start(m: Message) -> None:
    if tp.is_admin(m.from_user.id):
        _AWAITING_SCHEDULE_TIME.pop(m.from_user.id, None)
        await m.answer(
            "🎛 <b>پنل مدیریت و انتشار خودکار XGPedia</b>\n\n"
            "با دکمهٔ زیر دیتای بازی‌های شروع‌نشدهٔ امروز را دریافت کنید، بازی دلخواه را انتخاب کنید، "
            "کارت و کپشن را ببینید و فوری یا در ساعت دلخواه منتشر کنید.",
            parse_mode="HTML",
            reply_markup=_main_panel_markup(),
        )
    else:
        await m.answer("ربات انتشار XGPedia — فقط ادمین‌های مجاز به پنل مدیریت دسترسی دارند.")


@router.message(F.text)
async def on_any_text(m: Message) -> None:
    user_id = m.from_user.id
    if not tp.is_admin(user_id):
        await m.answer("این ربات دستور متنی ندارد؛ فقط برای ادمین‌های XGPedia فعال است.")
        return

    # اگر ادمین در حال وارد کردن ساعت انتشار ۲۴ ساعته است
    if user_id in _AWAITING_SCHEDULE_TIME:
        post_id = _AWAITING_SCHEDULE_TIME[user_id]
        raw_text = (m.text or "").strip()
        if raw_text in {"لغو", "انصراف", "/cancel", "cancel"}:
            _AWAITING_SCHEDULE_TIME.pop(user_id, None)
            await m.answer("❌ زمان‌بندی لغو شد.", reply_markup=_main_panel_markup())
            return
        try:
            res = tw.schedule_post_publish(post_id, raw_text, user_id)
            _AWAITING_SCHEDULE_TIME.pop(user_id, None)
            await m.answer(
                f"⏰ <b>زمان‌بندی با موفقیت ثبت شد!</b>\n"
                f"پست #{post_id} امروز ساعت <b>{res['scheduled_time_tehran']}</b> (به وقت تهران) "
                f"به‌صورت خودکار در کانال منتشر خواهد شد.",
                parse_mode="HTML",
                reply_markup=_main_panel_markup(),
            )
        except Exception as e:
            await m.answer(
                f"⚠️ <b>زمان‌بندی ثبت نشد:</b>\n{html.escape(str(e))}\n\n"
                "دوباره ساعت را به فرمت ۲۴ ساعته بفرستید (مثلاً <code>09:35</code> یا <code>21:15</code>) "
                "یا کلمهٔ <code>لغو</code> را ارسال کنید.",
                parse_mode="HTML",
            )
        return

    await m.answer(
        "برای مدیریت بازی‌های امروز و تأیید/انتشار پست‌ها از دکمه‌های پنل زیر استفاده کنید.\n"
        "(یا در ترمینال: python run.py publish --post-id <id>)",
        reply_markup=_main_panel_markup(),
    )


# ─── هندلرهای پنل خودکارسازی بازی‌های امروز ───

@router.callback_query(F.data == "today:sync")
async def on_today_sync(cb: CallbackQuery) -> None:
    if not tp.is_admin(cb.from_user.id):
        await cb.answer("شما مجاز نیستید.", show_alert=True)
        return
    await cb.answer("در حال دریافت دیتای بازی‌های امروز...")
    status_msg = await cb.message.answer(
        "⏳ در حال دریافت آمار فصل و لیست بازی‌های شروع‌نشدهٔ امروز و ثبت در دیتابیس..."
    )
    report = await asyncio.to_thread(tw.sync_today_matches)

    header_lines = [
        f"📅 <b>گزارش دریافت بازی‌های امروز ({report.tehran_date})</b>",
        f"{'✅' if report.sync_results_ok else '❌'} آمار فصل: {html.escape(report.sync_results_detail)}",
        f"{'✅' if report.sync_fixtures_ok else '❌'} بازی‌های پیش‌رو: {html.escape(report.sync_fixtures_detail)}",
        f"{'✅' if report.sync_odds_ok else '⚠️'} ضرایب بازار (+EV): {html.escape(report.sync_odds_detail)}",
        f"{'✅' if report.sync_understat_ok else '⚠️'} Understat (مهره کلیدی/PPDA): {html.escape(report.sync_understat_detail)}",
    ]
    if report.errors:
        header_lines.append("")
        header_lines.append("⚠️ <b>جزئیات خطاهای رخ‌داده:</b>")
        for err in report.errors:
            header_lines.append(f"• {html.escape(err)}")

    text, markup = _format_matches_message(report.matches, header="\n".join(header_lines))
    await status_msg.edit_text(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "today:list")
async def on_today_list(cb: CallbackQuery) -> None:
    if not tp.is_admin(cb.from_user.id):
        await cb.answer("شما مجاز نیستید.", show_alert=True)
        return
    await cb.answer()
    matches = await asyncio.to_thread(tw.list_today_matches)
    text, markup = _format_matches_message(
        matches, header="📋 <b>لیست بازی‌های شروع‌نشدهٔ امروز (آماده در دیتابیس)</b>"
    )
    await cb.message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "today:schedules")
async def on_today_schedules(cb: CallbackQuery) -> None:
    if not tp.is_admin(cb.from_user.id):
        await cb.answer("شما مجاز نیستید.", show_alert=True)
        return
    await cb.answer()
    items = await asyncio.to_thread(tw.list_pending_schedules)
    if not items:
        await cb.message.answer(
            "⏰ در حال حاضر هیچ پست زمان‌بندی‌شده‌ای در صف نیست.",
            reply_markup=_main_panel_markup(),
        )
        return
    lines = ["⏰ <b>صف انتشار زمان‌بندی‌شدهٔ امروز:</b>", ""]
    rows: list[list[InlineKeyboardButton]] = []
    for it in items:
        lines.append(
            f"• ساعت <b>{it['scheduled_time_tehran']}</b> — پست #{it['post_id']}: "
            f"{html.escape(it['title'] or it['fixture_id'])}"
        )
        rows.append([
            InlineKeyboardButton(
                text=f"❌ لغو زمان‌بندی #{it['id']} (ساعت {it['scheduled_time_tehran']})",
                callback_data=f"csched:{it['id']}",
            )
        ])
    rows.append([InlineKeyboardButton(text="📋 بازگشت به بازی‌های امروز", callback_data="today:list")])
    await cb.message.answer(
        "\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )


@router.callback_query(F.data.startswith("csched:"))
async def on_cancel_schedule(cb: CallbackQuery) -> None:
    if not tp.is_admin(cb.from_user.id):
        await cb.answer("شما مجاز نیستید.", show_alert=True)
        return
    sched_id = int(cb.data.split(":", 1)[1])
    try:
        tw.cancel_scheduled_publish(sched_id, cb.from_user.id)
        await cb.answer("زمان‌بندی لغو شد.")
        await cb.message.answer(
            f"✅ زمان‌بندی #{sched_id} لغو شد و پست به حالت آمادهٔ انتشار بازگشت.",
            reply_markup=_main_panel_markup(),
        )
    except Exception as e:
        await cb.answer(str(e)[:200], show_alert=True)


@router.callback_query(F.data.startswith("gen:"))
async def on_generate_match(cb: CallbackQuery, bot: Bot) -> None:
    if not tp.is_admin(cb.from_user.id):
        await cb.answer("شما مجاز نیستید.", show_alert=True)
        return
    fixture_id = _resolve_fixture(cb.data.split(":", 1)[1])
    await cb.answer("در حال ساخت پست کامل...")
    wait_msg = await cb.message.answer(
        f"⏳ در حال تولید فکت‌ها، متن تحریریه (LLM) و رندر کارت تصویری برای بازی <code>{html.escape(fixture_id)}</code>...",
        parse_mode="HTML",
    )

    res = await asyncio.to_thread(tw.generate_match_post, fixture_id)
    if not res.ok:
        retry_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 تلاش مجدد", callback_data=_cb_for_fixture(fixture_id))],
                [InlineKeyboardButton(text="📋 بازگشت به بازی‌های امروز", callback_data="today:list")],
            ]
        )
        await wait_msg.edit_text(
            html.escape(res.format_error_fa()), parse_mode="HTML", reply_markup=retry_kb
        )
        return

    try:
        post = tp.load_post(res.post_id)
        caption = tp.build_review_caption(post)
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ انتشار فوری در کانال", "callback_data": f"approve:{res.post_id}"},
                    {"text": "⏰ زمان‌بندی امروز (HH:MM)", "callback_data": f"sched:{res.post_id}"},
                ],
                [
                    {"text": "🔄 تولید مجدد", "callback_data": _cb_for_fixture(fixture_id)},
                    {"text": "❌ رد", "callback_data": f"reject:{res.post_id}"},
                ],
                [
                    {"text": "📋 لیست بازی‌های امروز", "callback_data": "today:list"},
                ],
            ]
        }
        transport = make_transport(bot)
        await transport.send_photo(cb.from_user.id, str(res.image_path), caption, reply_markup=keyboard)
        await wait_msg.edit_text(
            f"✅ پست کامل بازی ساخته شد (پست #{res.post_id} · نسخه {res.content_version}).\n"
            f"فایل کارت در <code>{html.escape(str(res.image_path.name))}</code> ذخیره شد.",
            parse_mode="HTML",
        )
    except Exception as e:
        await wait_msg.edit_text(
            f"❌ پست در سیستم ساخته شد (پست #{res.post_id}) اما در ارسال پیش‌نمایش به تلگرام خطا رخ داد:\n"
            f"{html.escape(type(e).__name__)}: {html.escape(str(e))}",
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("sched:"))
async def on_ask_schedule_time(cb: CallbackQuery) -> None:
    if not tp.is_admin(cb.from_user.id):
        await cb.answer("شما مجاز نیستید.", show_alert=True)
        return
    post_id = int(cb.data.split(":", 1)[1])
    _AWAITING_SCHEDULE_TIME[cb.from_user.id] = post_id
    await cb.answer("ساعت را در چت ارسال کنید.")
    await cb.message.answer(
        f"⏰ برای زمان‌بندی انتشار خودکار <b>پست #{post_id}</b> در امروز، ساعت را با فرمت ۲۴ ساعته "
        f"(به وقت تهران) ارسال کنید — مثلاً <code>09:35</code> یا <code>21:15</code>.\n"
        f"برای انصراف بنویسید: <code>لغو</code>",
        parse_mode="HTML",
    )


# ─── هندلر دکمه‌های تأیید/رد/ویرایش پست ───

@router.callback_query(F.data.startswith(("approve:", "reject:", "edit:")))
async def on_decision(cb: CallbackQuery, bot: Bot) -> None:
    """دکمه‌های زیر پیام بازبینی — فقط ادمین؛ نتیجه در همان پیام ویرایش می‌شود."""
    if not tp.is_admin(cb.from_user.id):
        await cb.answer("شما مجاز به تصمیم‌گیری نیستید.", show_alert=True)
        return
    action, post_id_s = cb.data.split(":", 1)
    post_id = int(post_id_s)
    transport = make_transport(bot)
    try:
        if action == "approve":
            result = await tp.approve_and_publish(post_id, cb.from_user.id, transport)
            await transport.edit_text(
                cb.message.chat.id, cb.message.message_id,
                f"✅ منتشر شد — پیام کانال {result['message_id']}",
            )
            await cb.answer("منتشر شد.")
            await cb.message.answer(
                "پست با موفقیت در کانال منتشر شد. برای انتخاب بازی بعدی امروز:",
                reply_markup=_main_panel_markup(),
            )
        elif action == "reject":
            await tp.reject_post(post_id, cb.from_user.id)
            await transport.edit_text(
                cb.message.chat.id, cb.message.message_id, "❌ رد شد — بازگشت به صف تحریریه."
            )
            await cb.answer("رد شد.")
        else:
            await tp.back_to_draft(post_id, cb.from_user.id, action="edit")
            await transport.edit_text(
                cb.message.chat.id, cb.message.message_id, "✏️ به صف تحریریه بازگشت (draft)."
            )
            await cb.answer("بازگشت به صف.")
    except Exception as e:
        await cb.answer(f"خطا: {str(e)[:180]}", show_alert=True)
    log.info("moderation action=%s post=%s by=%s", action, post_id, cb.from_user.id)


# ─── حلقهٔ زمان‌بند پس‌زمینه برای انتشار خودکار پست‌های زمان‌بندی‌شده ───

async def _scheduler_loop(bot: Bot, interval_seconds: int = 15) -> None:
    transport = make_transport(bot)

    async def _notify(admin_id: int, text: str) -> None:
        try:
            await bot.send_message(admin_id, text)
        except Exception as exc:
            log.warning("failed to notify admin %s: %s", admin_id, exc)

    log.info("background publish scheduler started (every %ss)", interval_seconds)
    while True:
        try:
            outcomes = await tw.run_due_scheduled_publishes(transport, notify_fn=_notify)
            for out in outcomes:
                log.info("scheduled publish outcome: %s", out)
        except Exception as exc:
            log.exception("scheduler loop error: %s", exc)
        await asyncio.sleep(interval_seconds)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    validate_env()
    bot = Bot(TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    sched_task = asyncio.create_task(_scheduler_loop(bot))
    log.info("bot polling started - admins: %s", sorted(ADMIN_TELEGRAM_IDS))
    try:
        await dp.start_polling(bot)
    finally:
        sched_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
