"""لایهٔ ۷/۸ — ربات ادمین و انتشار تلگرام XGPedia (aiogram 3) + کاستومایزر تعاملی + ویرایش متن + زمان‌بند خودکار.

اجرا:  python run.py bot   یا   python -m src.xgpedia.publishers.telegram_bot

قابلیت‌های پنل ادمین (فقط ADMIN_TELEGRAM_IDS — D11):
  - دریافت هوشمند بازی‌های امروز با کش دیتابیس (بدون مصرف اضافهٔ API در صورت موجودبودن داده)
    + دکمهٔ «⚡ به‌روزرسانی اجباری از API» و تشخیص خودکار پخش زنده از tv3.ir و varzeshtv.ir
  - پنل کاستومایزر تعاملی کارت (انتخاب ماژول‌های دارای دیتا، سوییچ نیم‌عرض/تمام‌عرض، فرمت، هدر، پخش)
  - تولید ناهمزمان کارت با گزارش مرحله‌به‌مرحله (رفع کامل هنگ Playwright روی ویندوز)
  - دکمه‌های «🔄 تولید مجدد متن» و «✏️ ویرایش متن با توضیح» روی پیش‌نمایش پست (بدون نیاز به رندر مجدد عکس)
  - انتشار فوری در کانال یا زمان‌بندی ۲۴ ساعته تهران (`HH:MM`)
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
from pathlib import Path
from typing import Any

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    BotCommand,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from src.xgpedia.config import ADMIN_TELEGRAM_IDS, TELEGRAM_BOT_TOKEN
from src.xgpedia.publishers import telegram_publish as tp
from src.xgpedia import today_workflow as tw
from src.xgpedia.render.card_kit.base_shell import validate_half_width_layout

from src.xgpedia.db import PersistentStateDict

router = Router()
log = logging.getLogger("xgpedia.bot")


class AdminOnlyMiddleware(BaseMiddleware):
    """گارد مرکزی ادمین روی تمام پیام‌ها و کالبک‌های روتر تا هیچ هندلر جدیدی بی‌محافظ نماند."""

    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        uid = getattr(user, "id", None) if user is not None else None
        if uid is None or not tp.is_admin(uid):
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer("شما مجاز نیستید.", show_alert=True)
                except Exception:
                    pass
            return None
        return await handler(event, data)


_ADMIN_GUARD_MW = AdminOnlyMiddleware()
router.message.middleware(_ADMIN_GUARD_MW)
router.callback_query.middleware(_ADMIN_GUARD_MW)

_AWAITING_SCHEDULE_TIME: Any = PersistentStateDict("awaiting_schedule_time", key_type=int)
_LAST_GENERATED_PREVIEW: dict[int, tw.PostGenerationResult] = {}
_AWAITING_EDIT_INSTRUCTION: Any = PersistentStateDict("awaiting_edit_instruction", key_type=int)
_FIXTURE_ALIAS: Any = PersistentStateDict("fixture_alias", key_type=str)
# وضعیت کاستومایزر کارت به ازای هر ادمین (ماندگار در SQLite): {admin_id: {...}}
_CUSTOMIZER_STATE: Any = PersistentStateDict("customizer_state", key_type=int)

BROADCAST_CYCLE: list[tuple[str, str]] = [
    ("پخش آنلاین", "پخش آنلاین"),
    ("پخش زنده: شبکه سه", "شبکه سه"),
    ("پخش زنده: شبکه ورزش", "شبکه ورزش"),
    ("", "بدون برچسب پخش"),
]


def _broadcast_index_for(label: str) -> int:
    s = (label or "").strip()
    for i, (val, _) in enumerate(BROADCAST_CYCLE):
        if val and val == s:
            return i
    if "ورزش" in s:
        return 2
    if "سه" in s:
        return 1
    return 0


async def _safe_cb_answer(
    cb: CallbackQuery, text: str | None = None, *, show_alert: bool = False
) -> None:
    """پاسخ امن به CallbackQuery — در صورت انقضای کوئری (query is too old) هندلر کرش نمی‌کند."""
    try:
        if text is None:
            await cb.answer(show_alert=show_alert)
        else:
            await cb.answer(text, show_alert=show_alert)
    except Exception as e:
        log.debug("cb.answer ignored (%s): %s", type(e).__name__, e)


def validate_env() -> None:
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

    async def send_video(self, chat_id: int | str, video: str, caption: str = "") -> tp.SentMessage:
        vid_obj: str | FSInputFile = video if str(video).startswith(("http://", "https://")) else FSInputFile(video)
        msg: Message = await self._bot.send_video(chat_id, video=vid_obj, caption=caption[:1024], parse_mode="HTML")
        return tp.SentMessage(chat_id=msg.chat.id, message_id=msg.message_id)

    async def send_poll(self, chat_id: int | str, question: str, options: list[str]) -> tp.SentMessage:
        msg: Message = await self._bot.send_poll(
            chat_id,
            question=str(question)[:300],
            options=[str(o)[:100] for o in options[:10]],
            is_anonymous=True,
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


def _persistent_reply_keyboard() -> ReplyKeyboardMarkup:
    """کیبورد جمع‌شونده و خلوت پایین چت — فقط هاب‌های اصلی + دسترسی سریع /start + بستن کیبورد."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎨 استودیو کارت‌ها"), KeyboardButton(text="📡 دیتای زنده")],
            [KeyboardButton(text="⚙️ صف و هوش مصنوعی"), KeyboardButton(text="🚀 /start")],
        ],
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
        input_field_placeholder="دستور یا بخش دلخواه را انتخاب کنید...",
    )


def _cards_studio_markup() -> InlineKeyboardMarkup:
    """کاتالوگ دسته‌بندی‌شدهٔ تمام کارت‌های XGPedia (مقیاس‌پذیر برای کارت‌های آینده)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📋 پیش‌ازبازی (امروز)", callback_data="today:list"),
                InlineKeyboardButton(text="🏁 پس‌ازبازی (۲۴س)", callback_data="post:list"),
            ],
            [
                InlineKeyboardButton(text="🕰 در چنین روزی", callback_data="otd:list"),
                InlineKeyboardButton(text="📰 خبر فوری و رسمی", callback_data="news:list"),
            ],
            [
                InlineKeyboardButton(text="🎂 تولدهای امروز (اسطوره‌ها)", callback_data="bday:list:1"),
                InlineKeyboardButton(text="🔍 جستجوی بازیکن (تولد)", callback_data="bday:search"),
            ],
            [
                InlineKeyboardButton(text="📡 رادار نقل‌وانتقالات (شایعات داغ)", callback_data="tr:list:1"),
                
            ],
            [
                InlineKeyboardButton(text="⚔️ این یا اون؟ (دوئل جدالی)", callback_data="tot:list:1"),
                InlineKeyboardButton(text="⚡ پیشنهاد جدالی تازه با AI", callback_data="tot:ai_new"),
            ],
            [
                InlineKeyboardButton(text="⭐️ نمرات بازیکنان", callback_data="pr:list:1"),
                InlineKeyboardButton(text="🏆 جدول رده‌بندی", callback_data="st:list:1"),
            ],
            [
                InlineKeyboardButton(text="🏥 آزمایشگاه مصدومیت", callback_data="inj:list:1"),
                InlineKeyboardButton(text="🧬 پروفایل فنی بازیکن", callback_data="pl:list:1"),
            ],
            [
                InlineKeyboardButton(text="⚔️ تقابل تیم‌ها (H2H)", callback_data="h2t:list:1"),
                InlineKeyboardButton(text="🃏 کارت FC27", callback_data="fc:list:1"),
            ],
            [
                InlineKeyboardButton(text="🆚 مقایسه بازیکنان", callback_data="h2p:list:1"),
                InlineKeyboardButton(text="👟 جدول گلزنان (کفش طلا)", callback_data="ts:list:1"),
            ],
            [
                InlineKeyboardButton(text="📊 نتایج بازی‌های روز", callback_data="mr:list:1"),
                InlineKeyboardButton(text="💬 نقل‌قول روز", callback_data="qt:list:1"),
            ],
            [
                InlineKeyboardButton(text="🔥 مناظره روز", callback_data="db:list:1"),
                InlineKeyboardButton(text="🔢 عدد روز", callback_data="nd:list:1"),
            ],
            [
                InlineKeyboardButton(text="📈 خلاصه هفته و فرم", callback_data="mw:list:1"),
                InlineKeyboardButton(text="🎯 نقشه شوت و xG", callback_data="sm:list:1"),
            ],
            [
                InlineKeyboardButton(text="💎 رادار ارزش بازار", callback_data="vr:list:1"),
                InlineKeyboardButton(text="📋 ترکیب و غایبان", callback_data="li:list:1"),
            ],
            [
                InlineKeyboardButton(text="📡 رفتن به مرکز دیتای زنده", callback_data="nav:sync"),
                InlineKeyboardButton(text="🏠 پنل اصلی", callback_data="nav:home"),
            ],
        ]
    )


def _sync_hub_markup() -> InlineKeyboardMarkup:
    """مرکز دریافت و همگام‌سازی دیتای زنده از APIها."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 دریافت هوشمند بازی‌های امروز (با کش)", callback_data="today:sync")],
            [InlineKeyboardButton(text="⚡ همگام‌سازی اجباری از APIها", callback_data="today:force_sync")],
            [InlineKeyboardButton(text="🏁 بروزرسانی نتایج پایان‌یافته (۲۴س)", callback_data="post:refresh")],
            [InlineKeyboardButton(text="🕰 بروزرسانی زندهٔ ویکی‌پدیا (در چنین روزی)", callback_data="otd:refresh")],
            [InlineKeyboardButton(text="📰 بروزرسانی اخبار زنده (ESPN/BBC)", callback_data="news:refresh")],
            [InlineKeyboardButton(text="🎂 بروزرسانی تولدهای امروز (Wikidata/Wiki)", callback_data="bday:refresh")],
            [InlineKeyboardButton(text="📡 بروزرسانی شایعات نقل‌وانتقالات (۵ منبع)", callback_data="tr:refresh")],
            [InlineKeyboardButton(text="⭐️ بروزرسانی نمرات مسابقات (ESPN)", callback_data="pr:refresh")],
            [InlineKeyboardButton(text="🏆 بروزرسانی جداول زنده (ESPN/Understat)", callback_data="st:refresh")],
            [InlineKeyboardButton(text="🏥 بروزرسانی مصدومیت‌ها (FPL/RSS)", callback_data="inj:refresh")],
            [InlineKeyboardButton(text="🧬 بروزرسانی پروفایل بازیکنان (FPL)", callback_data="pl:refresh")],
            [InlineKeyboardButton(text="📊 بروزرسانی نتایج ۲۴ ساعت اخیر (ESPN)", callback_data="mr:refresh")],
            [InlineKeyboardButton(text="👟 بروزرسانی جدول گلزنان زنده (FPL)", callback_data="ts:refresh")],
            [InlineKeyboardButton(text="⚔️ بروزرسانی تقابل مستقیم تیم‌ها (ESPN)", callback_data="h2t:refresh")],
            [InlineKeyboardButton(text="💬 جستجوی نقل‌قول‌های زنده (BBC/Guardian/ESPN)", callback_data="qt:refresh")],
            [InlineKeyboardButton(text="🔥 جستجوی مناظره‌های زنده (FPL/BBC/ESPN)", callback_data="db:refresh")],
            [InlineKeyboardButton(text="🔢 کشف اعداد روز زنده (FPL/BBC/Guardian)", callback_data="nd:refresh")],
            [
                InlineKeyboardButton(text="🎨 استودیو کارت‌ها", callback_data="nav:cards"),
                InlineKeyboardButton(text="🏠 پنل اصلی", callback_data="nav:home"),
            ],
        ]
    )


def _admin_hub_markup() -> InlineKeyboardMarkup:
    """مرکز مدیریت صف انتشار، تنظیمات هوش مصنوعی و کنترل کیبورد."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏰ صف انتشار زمان‌بندی‌شده", callback_data="today:schedules")],
            [
                InlineKeyboardButton(text="⚙️ انتخاب مدل شروع AI", callback_data="llm:menu"),
                InlineKeyboardButton(text="🧠 وضعیت زنجیره AI", callback_data="nav:ai_status"),
            ],
            [
                InlineKeyboardButton(text="🩺 سلامت و یادگیری APIها", callback_data="api:health"),
                InlineKeyboardButton(text="🔄 ریست حافظه سلامت", callback_data="api:health_reset"),
            ],
            [
                InlineKeyboardButton(text="🌐 پلتفرم‌های انتشار", callback_data="omni:status"),
                InlineKeyboardButton(text="🏠 پنل اصلی", callback_data="nav:home"),
            ],
        ]
    )


def _main_panel_markup() -> InlineKeyboardMarkup:
    """پنل اینلاین خلوت و تمیز /start — دکمه «همه کارت‌ها» + دسترسی سریع به ابزارهای کلیدی."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎨 همهٔ کارت‌ها (استودیو)", callback_data="nav:cards")],
            [
                InlineKeyboardButton(text="🔄 سینک سریع امروز", callback_data="today:sync"),
                InlineKeyboardButton(text="📡 مرکز دیتای زنده", callback_data="nav:sync"),
            ],
            [
                InlineKeyboardButton(text="🩺 سلامت APIها", callback_data="api:health"),
                InlineKeyboardButton(text="⚙️ تنظیمات AI", callback_data="llm:menu"),
            ],
        ]
    )


def _preview_keyboard(post_id: int, fixture_id: str, post_type: str = "preview") -> dict[str, Any]:
    _MODULAR_PK = {
        "players_rating": ("pr", "⭐️ لیست مسابقات نمرات"),
        "standings": ("st", "🏆 لیست جداول لیگ‌ها"),
        "injury_lab": ("inj", "🏥 لیست پرونده‌های مصدومیت"),
        "player_profile": ("pl", "🧬 لیست پروفایل بازیکنان"),
        "h2h_teams": ("h2t", "⚔️ لیست تقابل تیم‌ها"),
        "player_fc27": ("fc", "🃏 لیست کارت‌های FC27"),
        "h2h_players": ("h2p", "🆚 لیست مقایسه بازیکنان"),
        "top_scorers": ("ts", "👟 لیست جدول گلزنان"),
        "matchday_results": ("mr", "📊 لیست نتایج ۲۴ ساعت اخیر"),
        "quote": ("qt", "💬 لیست نقل‌قول‌های روز"),
        "debate": ("db", "🔥 لیست مناظره‌های روز"),
        "number_of_day": ("nd", "🔢 لیست اعداد روز"),
        "matchweek_wrapup": ("mw", "📈 لیست خلاصهٔ هفته و فرم"),
        "shotmap_xg": ("sm", "🎯 لیست نقشهٔ شوت و امید گل"),
        "value_radar": ("vr", "💎 لیست رادار ارزش بازار (+EV)"),
        "lineup_injuries": ("li", "📋 لیست ترکیب احتمالی و غایبان"),
    }
    if post_type in _MODULAR_PK:
        _pf, _lbl = _MODULAR_PK[post_type]
        return {
            "inline_keyboard": [
                [
                    {"text": "✅ انتشار فوری در کانال", "callback_data": f"approve:{post_id}"},
                    {"text": "⏰ زمان‌بندی امروز (HH:MM)", "callback_data": f"sched:{post_id}"},
                ],
                [
                    {"text": "🎛 تغییر اسلاید/هدر/ماژول", "callback_data": f"{_pf}:back"},
                    {"text": "❌ رد", "callback_data": f"reject:{post_id}"},
                ],
                [
                    {"text": _lbl, "callback_data": f"{_pf}:list:1"},
                ],
            ]
        }
    if post_type == "this_or_that":
        return {
            "inline_keyboard": [
                [
                    {"text": "✅ انتشار فوری در کانال", "callback_data": f"approve:{post_id}"},
                    {"text": "⏰ زمان‌بندی امروز (HH:MM)", "callback_data": f"sched:{post_id}"},
                ],
                [
                    {"text": "🎛 تغییر اسلاید/فرمت/ماژول", "callback_data": "tot:back"},
                    {"text": "❌ رد", "callback_data": f"reject:{post_id}"},
                ],
                [
                    {"text": "⚔️ لیست پیشنهادهای این یا اون", "callback_data": "tot:list:1"},
                ],
            ]
        }
    if post_type == "transfer_radar":
        return {
            "inline_keyboard": [
                [
                    {"text": "✅ انتشار فوری در کانال", "callback_data": f"approve:{post_id}"},
                    {"text": "⏰ زمان‌بندی امروز (HH:MM)", "callback_data": f"sched:{post_id}"},
                ],
                [
                    {"text": "🎛 تغییر اسلاید/هدر/ماژول", "callback_data": "tr:back"},
                    {"text": "❌ رد", "callback_data": f"reject:{post_id}"},
                ],
                [
                    {"text": "📡 لیست شایعات داغ نقل‌وانتقال", "callback_data": "tr:list:1"},
                ],
            ]
        }
    if post_type == "birthday":
        return {
            "inline_keyboard": [
                [
                    {"text": "✅ انتشار فوری در کانال", "callback_data": f"approve:{post_id}"},
                    {"text": "⏰ زمان‌بندی امروز (HH:MM)", "callback_data": f"sched:{post_id}"},
                ],
                [
                    {"text": "🎛 تغییر سبک/فرمت/ماژول", "callback_data": "bday:back"},
                    {"text": "❌ رد", "callback_data": f"reject:{post_id}"},
                ],
                [
                    {"text": "🎂 لیست تولدهای امروز", "callback_data": "bday:list:1"},
                ],
            ]
        }
    if post_type == "breaking_news":
        return {
            "inline_keyboard": [
                [
                    {"text": "✅ انتشار فوری در کانال", "callback_data": f"approve:{post_id}"},
                    {"text": "⏰ زمان‌بندی امروز (HH:MM)", "callback_data": f"sched:{post_id}"},
                ],
                [
                    {"text": "🎛 تغییر اسلاید/مود/ماژول", "callback_data": "news:back"},
                    {"text": "❌ رد", "callback_data": f"reject:{post_id}"},
                ],
                [
                    {"text": "📰 لیست اخبار فوری و رسمی", "callback_data": "news:list"},
                ],
            ]
        }
    if post_type == "on_this_day":
        return {
            "inline_keyboard": [
                [
                    {"text": "✅ انتشار فوری در کانال", "callback_data": f"approve:{post_id}"},
                    {"text": "⏰ زمان‌بندی امروز (HH:MM)", "callback_data": f"sched:{post_id}"},
                ],
                [
                    {"text": "🎛 تغییر اسلاید/تم/ماژول", "callback_data": "otd:back"},
                    {"text": "❌ رد", "callback_data": f"reject:{post_id}"},
                ],
                [
                    {"text": "🕰 لیست رویدادهای در چنین روزی", "callback_data": "otd:list"},
                ],
            ]
        }
    is_post = post_type == "post_match"
    cust_prefix = "pcust" if is_post else "cust"
    back_lbl = "🏁 لیست بازی‌های پایان‌یافته" if is_post else "📋 لیست بازی‌های امروز"
    back_cb = "post:list" if is_post else "today:list"
    return {
        "inline_keyboard": [
            [
                {"text": "✅ انتشار فوری در کانال", "callback_data": f"approve:{post_id}"},
                {"text": "⏰ زمان‌بندی امروز (HH:MM)", "callback_data": f"sched:{post_id}"},
            ],
            [
                {"text": "🔄 تولید مجدد متن", "callback_data": f"regen_txt:{post_id}"},
                {"text": "✏️ ویرایش متن با توضیح", "callback_data": f"edit_txt:{post_id}"},
            ],
            [
                {"text": "🎛 ویرایش چیدمان کارت", "callback_data": _cb_for_fixture(cust_prefix, fixture_id)},
                {"text": "❌ رد", "callback_data": f"reject:{post_id}"},
            ],
            [
                {"text": back_lbl, "callback_data": back_cb},
            ],
        ]
    }


def _cb_for_fixture(prefix: str, fixture_id: str) -> str:
    if len(fixture_id.encode("utf-8")) <= 48:
        return f"{prefix}:{fixture_id}"
    for k, v in _FIXTURE_ALIAS.items():
        if v == fixture_id:
            return f"{prefix}:{k}"
    key = f"k{len(_FIXTURE_ALIAS) + 1}"
    _FIXTURE_ALIAS[key] = fixture_id
    return f"{prefix}:{key}"


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
        lines.append("⚽ هیچ بازی شروع‌نشده‌ای برای امروز در ۶ لیگ معتبر اروپا ثبت نشده است.")
    else:
        if eligible:
            lines.append(f"🟢 <b>بازی‌های آماده برای تولید کارت پیش‌ازبازی ({len(eligible)} بازی):</b>")
            lines.append("روی هر بازی بزنید تا ماژول‌ها و چیدمان کارت را انتخاب کنید:")
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
        from src.xgpedia.core.leagues import competition_badge_fa
        lg_b = competition_badge_fa(m.competition)
        btn_text = f"{lg_b} | {m.home_fa} × {m.away_fa} ({m.kickoff_tehran}){badge}"
        rows.append([InlineKeyboardButton(text=btn_text, callback_data=_cb_for_fixture("cust", m.fixture_id))])

    rows.append([
        InlineKeyboardButton(text="🔄 به‌روزرسانی هوشمند", callback_data="today:sync"),
        InlineKeyboardButton(text="⚡ اجباری از API", callback_data="today:force_sync"),
    ])
    rows.append([
        InlineKeyboardButton(text="⏰ صف زمان‌بندی", callback_data="today:schedules"),
        InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="nav:home"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)




def _format_finished_matches_message(
    matches: list[tw.RecentFinishedMatchInfo], header: str = ""
) -> tuple[str, InlineKeyboardMarkup]:
    lines: list[str] = []
    if header:
        lines.append(header)
        lines.append("")
    if not matches:
        lines.append("ℹ️ در ۲۴ ساعت گذشته (از ۱ ثانیه پیش تا ۲۴ ساعت پیش) هیچ بازی پایان‌یافته‌ای در ۶ لیگ معتبر اروپا ثبت نشده است.")
    else:
        lines.append(f"🏁 <b>بازی‌های پایان‌یافتهٔ ۲۴ ساعت اخیر ({len(matches)} بازی):</b>")
        lines.append("روی هر بازی بزنید تا ماژول‌ها و چیدمان کارت پس‌ازبازی را انتخاب کنید:")

    rows: list[list[InlineKeyboardButton]] = []
    for m in matches:
        badge = ""
        if m.existing_post_status == "published":
            badge = " ✅"
        elif m.existing_post_id:
            badge = " 📝"
        from src.xgpedia.core.leagues import competition_badge_fa
        lg_b = competition_badge_fa(getattr(m, "competition", "Premier League"))
        btn_text = f"{lg_b} | {m.home_fa} {m.home_goals}-{m.away_goals} {m.away_fa} ({m.elapsed_fa}){badge}"
        rows.append([InlineKeyboardButton(text=btn_text, callback_data=_cb_for_fixture("pcust", m.fixture_id))])

    rows.append([
        InlineKeyboardButton(text="🔄 بررسی مجدد نتایج ۲۴س اخیر", callback_data="post:refresh"),
        InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="nav:home"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def _short_mod_name(title_fa: str, max_len: int = 13) -> str:
    t = title_fa.strip()
    return t if len(t) <= max_len else t[: max_len - 1].rstrip() + "…"


def _build_layout_schematic(modules: list[dict[str, Any]], *, post_type: str = "preview") -> tuple[str, list[str]]:
    """ساخت پیش‌نمایش شماتیک مکانی ماژول‌ها (ردیف‌به‌ردیف) + لیست خطاهای نیم‌عرض بدون جفت."""
    active = [m for m in modules if m.get("enabled", True)]
    errors = validate_half_width_layout(active)
    hdr_lbl = "🏟 هدر + نتیجه نهایی" if post_type == "post_match" else "🏟 هدر + شانس برد"
    lines = [f"┌─ {hdr_lbl} ─┐"]
    i = 0
    row_no = 1
    while i < len(active):
        cur = active[i]
        cur_name = _short_mod_name(cur.get("title_fa") or cur.get("id") or "ماژول", 14)
        if cur.get("span") == "half":
            if i + 1 < len(active) and active[i + 1].get("span") == "half":
                nxt = active[i + 1]
                nxt_name = _short_mod_name(nxt.get("title_fa") or nxt.get("id") or "ماژول", 14)
                lines.append(f"│{row_no}. [{cur_name}] │ [{nxt_name}]│")
                i += 2
                row_no += 1
                continue
            lines.append(f"│{row_no}. [{cur_name}] │ [⚠️ جای خالی!]│")
            i += 1
            row_no += 1
            continue
        lines.append(f"│{row_no}. [ ══ {cur_name} (تمام‌عرض) ══ ]│")
        i += 1
        row_no += 1
    lines.append("└─ @XGPedia ───────────┘")
    return "\n".join(lines), errors


def _render_customizer_view(st: dict[str, Any]) -> tuple[str, InlineKeyboardMarkup]:
    """ساخت متن و کیبورد تعاملی پنل کاستومایز کارت برای یک بازی (با پیش‌نمایش شماتیک و جابه‌جایی عمودی)."""
    fmt = st["fmt"]
    hm = st["header_mode"]
    bc_idx = st["broadcast_idx"]
    _, bc_lbl = BROADCAST_CYCLE[bc_idx]
    mods = st["modules"]
    active_cnt = sum(1 for m in mods if m["enabled"])
    post_type = st.get("post_type", "preview")
    is_post = post_type == "post_match"
    schematic, layout_errors = _build_layout_schematic(mods, post_type=post_type)

    lines = [
        "🏁 <b>تنظیم و کاستومایز کارت پس‌ازبازی</b>" if is_post else "🎛 <b>تنظیم و کاستومایز کارت پیش‌ازبازی</b>",
        f"⚽ <b>{html.escape(st['home_fa'])} × {html.escape(st['away_fa'])}</b>",
    ]
    meta_parts = [x for x in (st.get("round"), st.get("stadium")) if x]
    if meta_parts:
        lines.append("📍 " + html.escape(" • ".join(meta_parts)))
    if is_post:
        lines.append(f"📐 فرمت: <b>{fmt}</b> | هدر: <b>{'کامل' if hm == 'full' else 'فشرده'}</b> | وضعیت: <b>● پایان بازی</b>")
    else:
        lines.append(f"📐 فرمت: <b>{fmt}</b> | هدر: <b>{'کامل' if hm == 'full' else 'فشرده'}</b> | پخش: <b>{bc_lbl}</b>")
    lines.append(f"🧩 ماژول‌های فعال: <b>{active_cnt}</b> از {len(mods)} ماژول دارای دیتای واقعی")
    if st.get("missing_modules"):
        lines.append("ℹ️ ماژول‌های بدون دیتا در DB: " + html.escape("، ".join(st["missing_modules"])))
    lines.append("")
    lines.append("🗺 <b>پیش‌نمایش مکانی چیدمان کارت:</b>")
    lines.append(f"<pre>{html.escape(schematic)}</pre>")
    if layout_errors:
        lines.append("⚠️ <b>خطای چیدمان نیم‌عرض:</b>")
        for err in layout_errors:
            lines.append("• " + html.escape(err))
    lines.append("")
    lines.append("نام = روشن/خاموش | ۱ یا ½ = عرض | ⬆️⬇️ = جابه‌جایی عمودی:")

    kb_rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text=f"{'✅ ' if fmt == '4:5' else ''}پست 4:5", callback_data="cz:fmt:4:5"),
            InlineKeyboardButton(text=f"{'✅ ' if fmt == '9:16' else ''}استوری 9:16", callback_data="cz:fmt:9:16"),
            InlineKeyboardButton(text=f"{'✅ ' if fmt == '16:9' else ''}بنر 16:9", callback_data="cz:fmt:16:9"),
        ],
        [
            InlineKeyboardButton(text=f"{'✅ ' if st.get('tone', 'analytical') == 'analytical' else ''}📊 تحلیلی", callback_data="cz:tone:analytical"),
            InlineKeyboardButton(text=f"{'✅ ' if st.get('tone') == 'fan_light' else ''}⚡ لایت", callback_data="cz:tone:fan_light"),
            InlineKeyboardButton(text=f"{'✅ ' if st.get('tone') == 'x_thread' else ''}🧵 توییت X", callback_data="cz:tone:x_thread"),
            InlineKeyboardButton(text=f"{'✅ ' if st.get('tone') == 'reels_script' else ''}🎬 ریلز", callback_data="cz:tone:reels_script"),
        ],
        (
            [InlineKeyboardButton(text=f"هدر: {'کامل' if hm == 'full' else 'فشرده'} 🔁", callback_data="cz:hm")]
            if is_post
            else [
                InlineKeyboardButton(text=f"هدر: {'کامل' if hm == 'full' else 'فشرده'} 🔁", callback_data="cz:hm"),
                InlineKeyboardButton(text=f"پخش: {bc_lbl} 🔁", callback_data="cz:bc"),
            ]
        ),
    ]

    total_mods = len(mods)
    for idx, m in enumerate(mods):
        mark = "✅" if m["enabled"] else "⬜"
        span_badge = "½" if m["span"] == "half" else "۱"
        # ردیف اول تمام‌عرض برای نام کامل ماژول (بدون بریده‌شدن متن)
        kb_rows.append([
            InlineKeyboardButton(
                text=f"{mark} {m['title_fa']}  [{span_badge}]",
                callback_data=f"cz:tog:{m['id']}",
            )
        ])
        # ردیف دوم فشرده برای کنترل عرض و جابه‌جایی عمودی
        ctrl_row: list[InlineKeyboardButton] = []
        if m["can_half"]:
            w_lbl = "عرض: نیم‌عرض ½ 🔁" if m["span"] == "half" else "عرض: تمام‌عرض ۱ 🔁"
            ctrl_row.append(InlineKeyboardButton(text=w_lbl, callback_data=f"cz:sp:{m['id']}"))
        else:
            ctrl_row.append(InlineKeyboardButton(text="🔒 تمام‌عرض", callback_data="cz:noop"))
        ctrl_row.append(
            InlineKeyboardButton(
                text="⬆️ بالا" if idx > 0 else "·",
                callback_data=f"cz:up:{m['id']}" if idx > 0 else "cz:noop_edge",
            )
        )
        ctrl_row.append(
            InlineKeyboardButton(
                text="⬇️ پایین" if idx < total_mods - 1 else "·",
                callback_data=f"cz:dn:{m['id']}" if idx < total_mods - 1 else "cz:noop_edge",
            )
        )
        kb_rows.append(ctrl_row)

    from src.xgpedia.layout_templates import MAX_SAVED_TEMPLATES, list_layout_templates
    tpl_kind = "post_match" if is_post else "pre_match"
    tpl_cnt = len(list_layout_templates(tpl_kind))
    kb_rows.append([
        InlineKeyboardButton(text=f"💾 ذخیره قالب ({tpl_cnt}/{MAX_SAVED_TEMPLATES})", callback_data="cz:tpl_save"),
        InlineKeyboardButton(text=f"📂 قالب‌های من ({tpl_cnt}/{MAX_SAVED_TEMPLATES})", callback_data="cz:tpl_list"),
    ])
    build_lbl = "⚠️ رفع جای خالی نیم‌عرض برای ساخت" if layout_errors else "🎨 ساخت کارت و کپشن نهایی"
    kb_rows.append([
        InlineKeyboardButton(text=build_lbl, callback_data="cz:build"),
    ])
    kb_rows.append([
        InlineKeyboardButton(text="📋 بازگشت به بازی‌های امروز", callback_data="today:list"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=kb_rows)


def _find_rendered_image_for_post(post_id: int, res: tw.PostGenerationResult | None = None) -> Path | None:
    from pathlib import Path
    from src.xgpedia.config import ROOT

    if res and res.image_path and Path(res.image_path).exists():
        return Path(res.image_path)
    out_dir = ROOT / "output"
    if out_dir.exists():
        matches = sorted(
            out_dir.glob(f"*post_{post_id}_*.png"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if matches:
            return matches[0]
        matches2 = sorted(
            out_dir.glob(f"*{post_id}*.png"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if matches2:
            return matches2[0]
    return None


async def _send_post_preview(
    bot: Bot,
    admin_id: int,
    res: tw.PostGenerationResult,
    wait_msg: Message,
    note: str = "",
) -> None:
    _LAST_GENERATED_PREVIEW[res.post_id] = res
    last_err: Exception | None = None
    try:
        post = tp.load_post(res.post_id)
        caption = tp.build_review_caption(post)
        keyboard = _preview_keyboard(res.post_id, res.fixture_id)
        transport = make_transport(bot)
        img_path = _find_rendered_image_for_post(res.post_id, res)

        for attempt in range(1, 4):
            try:
                if img_path and img_path.exists():
                    await transport.send_photo(admin_id, str(img_path), caption, reply_markup=keyboard)
                else:
                    markup = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(**btn) for btn in row]
                            for row in keyboard["inline_keyboard"]
                        ]
                    )
                    await bot.send_message(admin_id, caption, parse_mode="HTML", reply_markup=markup)
                last_err = None
                break
            except Exception as e_send:
                last_err = e_send
                log.warning("send preview attempt %d/3 failed for post %s: %s", attempt, res.post_id, e_send)
                if attempt < 3:
                    await asyncio.sleep(2.0 * attempt)

        if last_err is not None:
            raise last_err

        done_txt = note or f"✅ پست کامل آماده شد (پست #{res.post_id} · نسخه {res.content_version})."
        try:
            await wait_msg.edit_text(done_txt, parse_mode="HTML")
        except TelegramBadRequest:
            pass
    except Exception as e:
        log.exception("failed sending preview for post %s", res.post_id)
        retry_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"🔁 ارسال مجدد پیش‌نمایش (پست #{res.post_id})", callback_data=f"resend_prev:{res.post_id}")],
                [InlineKeyboardButton(text="📋 لیست بازی‌های امروز", callback_data="today:list")],
            ]
        )
        try:
            await wait_msg.edit_text(
                f"❌ پست ساخته شد (#{res.post_id}) اما در ارسال پیش‌نمایش به تلگرام خطا رخ داد:\n"
                f"{html.escape(type(e).__name__)}: {html.escape(str(e)[:400])}\n\n"
                f"نیازی به ساخت مجدد نیست؛ روی دکمهٔ زیر بزنید تا فقط همین پست دوباره ارسال شود:",
                parse_mode="HTML",
                reply_markup=retry_kb,
            )
        except Exception:
            pass


# ─── هندلرهای دستورها و پیام‌های متنی ───

async def _send_home_dashboard(m: Message, *, with_keyboard: bool = True) -> None:
    _AWAITING_SCHEDULE_TIME.pop(m.from_user.id, None)
    _AWAITING_EDIT_INSTRUCTION.pop(m.from_user.id, None)
    if with_keyboard:
        for _attempt in range(2):
            try:
                await m.answer(
                    "🎛 <b>داشبورد XGPedia فعال شد</b>\n"
                    "از کیبورد پایین برای جابه‌جایی سریع بین بخش‌ها استفاده کنید.",
                    parse_mode="HTML",
                    reply_markup=_persistent_reply_keyboard(),
                )
                break
            except Exception as _net_err:
                if _attempt == 0 and ('Network' in type(_net_err).__name__ or 'Connection' in str(_net_err)):
                    await asyncio.sleep(1.5)
                    continue
                log.warning('telegram home send failed: %s', _net_err)
                break
    await m.answer(
        "⚡ <b>پنل مدیریت XGPedia</b> — بخش مورد نظر را انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=_main_panel_markup(),
    )


@router.message(Command("start", "panel"))
async def on_start(m: Message) -> None:
    if tp.is_admin(m.from_user.id):
        await _send_home_dashboard(m, with_keyboard=True)
    else:
        await m.answer("ربات انتشار XGPedia — فقط ادمین‌های مجاز به پنل مدیریت دسترسی دارند.")


@router.message(Command("cards"))
async def cmd_cards(m: Message) -> None:
    if not tp.is_admin(m.from_user.id):
        await m.answer("دسترسی غیرمجاز.")
        return
    await m.answer(
        "🎨 <b>استودیو کارت‌های XGPedia</b>\n\n"
        "⚽ <b>کارت‌های مسابقه:</b> پیش‌ازبازی · پس‌ازبازی (۲۴س)\n"
        "🕰 <b>تاریخ و تحریریه:</b> در چنین روزی (وقایع تاریخی)\n\n"
        "کارت مورد نظر را انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=_cards_studio_markup(),
    )


@router.message(F.text)
async def on_any_text(m: Message, bot: Bot | None = None) -> None:
    user_id = m.from_user.id
    if not tp.is_admin(user_id):
        await m.answer("این ربات دستور متنی ندارد؛ فقط برای ادمین‌های XGPedia فعال است.")
        return

    raw_text = (m.text or "").strip()

    # ۰) دکمه‌های کیبورد جمع‌شوندهٔ پایین صفحه (همیشه در اولویت، حتی در حالت انتظار متن)
    if raw_text in {"🚀 /start", "/start", "🏠 منوی اصلی"}:
        await _send_home_dashboard(m, with_keyboard=True)
        return
    if raw_text == "🎨 استودیو کارت‌ها":
        _AWAITING_SCHEDULE_TIME.pop(user_id, None)
        _AWAITING_EDIT_INSTRUCTION.pop(user_id, None)
        await m.answer(
            "🎨 <b>استودیو کارت‌های XGPedia</b>\n\n"
            "⚽ <b>کارت‌های مسابقه:</b> پیش‌ازبازی · پس‌ازبازی (۲۴س)\n"
            "🕰 <b>تاریخ و تحریریه:</b> در چنین روزی (وقایع تاریخی)\n\n"
            "کارت مورد نظر را انتخاب کنید:",
            parse_mode="HTML",
            reply_markup=_cards_studio_markup(),
        )
        return
    if raw_text == "📡 دیتای زنده":
        _AWAITING_SCHEDULE_TIME.pop(user_id, None)
        _AWAITING_EDIT_INSTRUCTION.pop(user_id, None)
        await m.answer(
            "📡 <b>مرکز دیتای زنده و همگام‌سازی</b>\n"
            "نوع بروزرسانی را انتخاب کنید:",
            parse_mode="HTML",
            reply_markup=_sync_hub_markup(),
        )
        return
    if raw_text == "⚙️ صف و هوش مصنوعی":
        _AWAITING_SCHEDULE_TIME.pop(user_id, None)
        _AWAITING_EDIT_INSTRUCTION.pop(user_id, None)
        await m.answer(
            "⚙️ <b>مدیریت صف انتشار و هوش مصنوعی</b>\n"
            "بخش مورد نظر را انتخاب کنید:",
            parse_mode="HTML",
            reply_markup=_admin_hub_markup(),
        )
        return
    if raw_text == "__legacy_home__":
        _AWAITING_SCHEDULE_TIME.pop(user_id, None)
        _AWAITING_EDIT_INSTRUCTION.pop(user_id, None)
        await m.answer(
            "🎛 <b>منوی اصلی XGPedia</b> — گزینهٔ دلخواه را انتخاب کنید:",
            parse_mode="HTML",
            reply_markup=_main_panel_markup(),
        )
        return
    if raw_text == "🏁 پس‌ازبازی (۲۴س)":
        status_msg = await m.answer("⏳ در حال دریافت زندهٔ بازی‌های پایان‌یافتهٔ ۲۴ ساعت اخیر (ESPN + FDO)...")
        s_info = await asyncio.to_thread(tw.sync_recent_finished_matches)
        matches = await asyncio.to_thread(tw.list_recent_finished_fixtures)
        hdr = f"🏁 <b>گزارش بازی‌های پایان‌یافته (۱ ثانیه تا ۲۴ ساعت پیش)</b>\n✅ ESPN: {s_info['espn_saved']} بازی ({s_info['espn_stats']} آمار) | FDO: {s_info['fdo_saved']} بازی"
        text, kb = _format_finished_matches_message(matches, header=hdr)
        await status_msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
        return
    if raw_text == "🕰 در چنین روزی":
        from src.xgpedia.providers.on_this_day_free import list_on_this_day_events
        status_msg = await m.answer("⏳ در حال دریافت زندهٔ رویدادهای تاریخی فوتبال امروز (ویکی‌پدیا فارسی/انگلیسی + آرشیو)...")
        data = await asyncio.to_thread(list_on_this_day_events, include_live=True)
        text, kb = _format_otd_list_message(data)
        await status_msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
        return
    if raw_text == "📋 بازی‌های امروز":
        matches = await asyncio.to_thread(tw.list_today_matches)
        text, markup = _format_matches_message(
            matches, header="📋 <b>لیست بازی‌های شروع‌نشدهٔ امروز (آماده در دیتابیس)</b>"
        )
        await m.answer(text, parse_mode="HTML", reply_markup=markup)
        return
    if raw_text in {"🔄 دریافت هوشمند", "⚡ همگام‌سازی اجباری"}:
        force_flag = raw_text == "⚡ همگام‌سازی اجباری"
        mode_lbl = "اجباری از API" if force_flag else "هوشمند (با کش دیتابیس)"
        status_msg = await m.answer(f"⏳ در حال بررسی بازی‌های امروز ({mode_lbl}) + ESPN/Understat + پخش زنده...")
        try:
            report = await _run_sync_with_heartbeat(status_msg, mode_lbl, force=force_flag, timeout_sec=240.0)
        except asyncio.TimeoutError:
            await status_msg.edit_text(
                "⏳ همگام‌سازی بیش از ۴ دقیقه طول کشید و ممکن است هنوز در پس‌زمینه در حال تکمیل باشد؛ چند لحظه بعد «📋 بازی‌های امروز» را بزنید.",
                parse_mode="HTML",
            )
            return
        except Exception as e:
            await status_msg.edit_text(f"❌ خطا در همگام‌سازی:\n{html.escape(type(e).__name__)}: {html.escape(str(e)[:400])}", parse_mode="HTML")
            return
        header_lines = [
            f"📅 <b>گزارش دریافت بازی‌های امروز ({report.tehran_date})</b>",
            f"{'✅' if report.sync_results_ok else '❌'} آمار فصل: {html.escape(report.sync_results_detail)}",
            f"{'✅' if report.sync_fixtures_ok else '❌'} بازی‌های پیش‌رو: {html.escape(report.sync_fixtures_detail)}",
            f"{'✅' if report.sync_odds_ok else '⚠️'} ضرایب بازار (+EV): {html.escape(report.sync_odds_detail)}",
            f"{'✅' if report.sync_understat_ok else '⚠️'} ماژول‌های تکمیلی (ESPN/Understat): {html.escape(report.sync_understat_detail)}",
            f"{'✅' if report.sync_broadcasts_ok else '⚠️'} پخش زنده (شبکه سه/ورزش): {html.escape(report.sync_broadcasts_detail)}",
        ]
        text, markup = _format_matches_message(report.matches, header="\n".join(header_lines))
        await status_msg.edit_text(text[:4000], parse_mode="HTML", reply_markup=markup)
        return
    if raw_text == "⏰ صف زمان‌بندی":
        items = await asyncio.to_thread(tw.list_pending_schedules)
        if not items:
            await m.answer("⏰ هیچ پست زمان‌بندی‌شده‌ای در صف نیست.", reply_markup=_main_panel_markup())
            return
        lines = ["⏰ <b>صف انتشار زمان‌بندی‌شدهٔ امروز:</b>", ""]
        rows = []
        for it in items:
            lines.append(f"• ساعت <b>{it['scheduled_time_tehran']}</b> — پست #{it['post_id']}: {html.escape(it['title'] or it['fixture_id'])}")
            rows.append([InlineKeyboardButton(text=f"❌ لغو زمان‌بندی #{it['id']} ({it['scheduled_time_tehran']})", callback_data=f"csched:{it['id']}")])
        rows.append([InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="nav:home")])
        await m.answer("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        return
    if raw_text == "🧠 وضعیت AI":
        text, markup = _render_ai_status_view(page=1)
        await m.answer(text, parse_mode="HTML", reply_markup=markup)
        return

    # ۰-الف) حالت ذخیرهٔ نام قالب سفارشی (تا ۵ قالب برای هر کارت ماژولار)
    if user_id in _AWAITING_TEMPLATE_NAME:
        card_kind = _AWAITING_TEMPLATE_NAME.pop(user_id)
        if raw_text in {"لغو", "انصراف", "/cancel", "cancel"}:
            await m.answer("❌ ذخیرهٔ قالب لغو شد.", reply_markup=_main_panel_markup())
            return
        from src.xgpedia.layout_templates import save_layout_template
        try:
            if card_kind in {"players_rating", "standings", "injury_lab", "player_profile", "h2h_teams", "player_fc27", "h2h_players", "top_scorers", "matchday_results", "quote", "debate", "number_of_day", "matchweek_wrapup", "shotmap_xg", "value_radar", "lineup_injuries"}:
                from src.xgpedia.publishers.modular_cards_bot import (
                    MODULAR_STATES,
                    render_modular_customizer_view,
                )
                st_m = MODULAR_STATES.get(card_kind, {}).get(user_id)
                if not st_m:
                    await m.answer("❌ وضعیت کاستومایزر منقضی شده است؛ دوباره از لیست باز کنید.")
                    return
                saved = save_layout_template(
                    card_kind,
                    raw_text,
                    fmt=st_m["fmt"],
                    header_mode=st_m["header_mode"],
                    modules=st_m["modules"],
                )
                text, markup = render_modular_customizer_view(card_kind, st_m)
                await m.answer(
                    f"✅ قالب <b>«{html.escape(saved['name'])}»</b> با موفقیت ذخیره شد!\n\n{text}",
                    parse_mode="HTML",
                    reply_markup=markup,
                )
                return
            elif card_kind == "transfer_radar":
                st_tr = _TR_STATE.get(user_id)
                if not st_tr:
                    await m.answer("❌ وضعیت کاستومایزر منقضی شده است؛ دوباره شایعه را باز کنید.")
                    return
                saved = save_layout_template(
                    "transfer_radar",
                    raw_text,
                    fmt=st_tr["fmt"],
                    header_mode=st_tr["header_mode"],
                    modules=st_tr["modules"],
                )
                text, markup = _render_transfer_customizer_view(st_tr)
                await m.answer(
                    f"✅ قالب <b>«{html.escape(saved['name'])}»</b> با موفقیت ذخیره شد!\n\n{text}",
                    parse_mode="HTML",
                    reply_markup=markup,
                )
                return
            else:
                st_cz = _CUSTOMIZER_STATE.get(user_id)
                if not st_cz:
                    await m.answer("❌ وضعیت کاستومایزر منقضی شده است؛ دوباره بازی را باز کنید.")
                    return
                saved = save_layout_template(
                    card_kind,
                    raw_text,
                    fmt=st_cz["fmt"],
                    header_mode=st_cz["header_mode"],
                    modules=st_cz["modules"],
                )
                text, markup = _render_customizer_view(st_cz)
                await m.answer(
                    f"✅ قالب <b>«{html.escape(saved['name'])}»</b> با موفقیت ذخیره شد!\n\n{text}",
                    parse_mode="HTML",
                    reply_markup=markup,
                )
                return
        except Exception as e:
            await m.answer(f"⚠️ ذخیرهٔ قالب انجام نشد:\n{html.escape(str(e))}", parse_mode="HTML")
            return

    # ۰) حالت جستجوی نام فوتبالیست برای کارت تولد
    if user_id in _AWAITING_BIRTHDAY_SEARCH:
        _AWAITING_BIRTHDAY_SEARCH.discard(user_id)
        if raw_text in {"لغو", "انصراف", "/cancel", "cancel"}:
            await m.answer("❌ جستجوی بازیکن لغو شد.", reply_markup=_main_panel_markup())
            return
        from src.xgpedia.providers.birthday_free import search_footballer_by_name
        wait_s = await m.answer(f"🔍 در حال جستجوی «{html.escape(raw_text)}» در TheSportsDB و ویکی‌پدیا...")
        found = await asyncio.to_thread(search_footballer_by_name, raw_text)
        if not found:
            await wait_s.edit_text(
                f"❌ بازیکنی با نام «{html.escape(raw_text)}» پیدا نشد. نام انگلیسی یا فارسی دقیق‌تر را امتحان کنید.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔍 جستجوی مجدد", callback_data="bday:search")],
                    [InlineKeyboardButton(text="🎂 لیست تولدهای امروز", callback_data="bday:list:1")],
                ]),
            )
            return
        rows_s: list[list[InlineKeyboardButton]] = []
        for pl in found[:8]:
            pid = str(pl["id"])
            _BDAY_ITEM_MAP[pid] = pl
            age_s = f" ({pl['age']}س)" if pl.get("age") else ""
            club_s = f" — {pl['club']}" if pl.get("club") else ""
            rows_s.append([InlineKeyboardButton(text=f"🎂 {pl['nameFa']}{age_s}{club_s}"[:54], callback_data=f"bday:open:{pid[:44]}")])
        rows_s.append([
            InlineKeyboardButton(text="🔍 جستجوی جدید", callback_data="bday:search"),
            InlineKeyboardButton(text="🎂 تولدهای امروز", callback_data="bday:list:1"),
        ])
        await wait_s.edit_text(
            f"🔍 <b>نتایج جستجو برای «{html.escape(raw_text)}» ({len(found)} مورد):</b>\nبازیکن مورد نظر را انتخاب کنید تا آمار و عکس واقعی او استخراج شود:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows_s),
        )
        return

    # ۱) حالت دریافت توضیح ویرایش متن از ادمین
    if user_id in _AWAITING_EDIT_INSTRUCTION:
        post_id = _AWAITING_EDIT_INSTRUCTION.pop(user_id)
        if raw_text in {"لغو", "انصراف", "/cancel", "cancel"}:
            await m.answer("❌ ویرایش متن لغو شد.", reply_markup=_main_panel_markup())
            return
        wait_msg = await m.answer(
            f"⏳ در حال ویرایش متن <b>پست #{post_id}</b> طبق توضیح شما...",
            parse_mode="HTML",
        )
        try:
            res = await asyncio.wait_for(
                asyncio.to_thread(tw.regenerate_or_edit_post_text, post_id, instruction=raw_text),
                timeout=120.0,
            )
        except Exception as e:
            await wait_msg.edit_text(
                f"❌ خطا در ویرایش متن پست #{post_id}:\n{html.escape(type(e).__name__)}: {html.escape(str(e)[:400])}",
                parse_mode="HTML",
            )
            return
        if not res.ok:
            await wait_msg.edit_text(html.escape(res.format_error_fa())[:3800], parse_mode="HTML")
            return
        await _send_post_preview(
            bot or m.bot, user_id, res, wait_msg,
            note=f"✅ متن پست #{post_id} طبق توضیح شما ویرایش شد (کارت تصویری بدون تغییر حفظ شد).",
        )
        return

    # ۲) حالت دریافت ساعت زمان‌بندی ۲۴ ساعته تهران
    if user_id in _AWAITING_SCHEDULE_TIME:
        post_id = _AWAITING_SCHEDULE_TIME[user_id]
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


# ─── هندلرهای دریافت و لیست بازی‌های امروز ───


async def _run_sync_with_heartbeat(status_msg: Message, mode_lbl: str, *, force: bool, timeout_sec: float = 240.0):
    """اجرای sync_today_matches در ترد پس‌زمینه همراه با به‌روزرسانی زندهٔ زمان سپری‌شده تا پیام تایم‌اوت کاذب نمایش داده نشود."""
    import time as _time
    task = asyncio.create_task(asyncio.to_thread(tw.sync_today_matches, force=force))
    t0 = _time.monotonic()
    while True:
        elapsed = _time.monotonic() - t0
        remaining = timeout_sec - elapsed
        if remaining <= 0:
            raise asyncio.TimeoutError(f"sync exceeded {int(timeout_sec)}s")
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=min(20.0, remaining))
        except asyncio.TimeoutError:
            sec = int(_time.monotonic() - t0)
            try:
                await status_msg.edit_text(
                    f"⏳ همچنان در حال دریافت بازی‌های امروز ({mode_lbl})... ({sec} ثانیه گذشته)",
                )
            except Exception:
                pass


async def _run_sync_flow(cb: CallbackQuery, *, force: bool) -> None:
    await _safe_cb_answer(cb, "در حال دریافت دیتای بازی‌های امروز...")
    mode_lbl = "اجباری از API" if force else "هوشمند (با استفاده از کش دیتابیس)"
    status_msg = await cb.message.answer(
        f"⏳ در حال بررسی بازی‌های امروز ({mode_lbl}) + جدول پخش شبکه سه و ورزش..."
    )
    try:
        report = await _run_sync_with_heartbeat(status_msg, mode_lbl, force=force, timeout_sec=240.0)
    except asyncio.TimeoutError:
        await status_msg.edit_text(
            "⏳ همگام‌سازی بیش از ۴ دقیقه طول کشید و ممکن است هنوز در پس‌زمینه در حال تکمیل باشد؛ چند لحظه بعد «📋 بازی‌های امروز» را بزنید.",
            parse_mode="HTML",
        )
        return
    except Exception as e:
        await status_msg.edit_text(
            f"❌ خطا در همگام‌سازی بازی‌های امروز:\n{html.escape(type(e).__name__)}: {html.escape(str(e)[:400])}",
            parse_mode="HTML",
        )
        return

    header_lines = [
        f"📅 <b>گزارش دریافت بازی‌های امروز ({report.tehran_date})</b>",
        f"{'✅' if report.sync_results_ok else '❌'} آمار فصل: {html.escape(report.sync_results_detail)}",
        f"{'✅' if report.sync_fixtures_ok else '❌'} بازی‌های پیش‌رو: {html.escape(report.sync_fixtures_detail)}",
        f"{'✅' if report.sync_odds_ok else '⚠️'} ضرایب بازار (+EV): {html.escape(report.sync_odds_detail)}",
        f"{'✅' if report.sync_understat_ok else '⚠️'} Understat (مهره کلیدی/PPDA): {html.escape(report.sync_understat_detail)}",
        f"{'✅' if report.sync_broadcasts_ok else '⚠️'} پخش زنده (شبکه سه/ورزش): {html.escape(report.sync_broadcasts_detail)}",
    ]
    if report.errors:
        header_lines.append("")
        header_lines.append("⚠️ <b>جزئیات خطاهای رخ‌داده:</b>")
        for err in report.errors:
            header_lines.append(f"• {html.escape(err)}")

    text, markup = _format_matches_message(report.matches, header="\n".join(header_lines))
    await status_msg.edit_text(text[:4000], parse_mode="HTML", reply_markup=markup)



@router.callback_query(F.data == "nav:home")
async def on_nav_home(cb: CallbackQuery) -> None:
    await _safe_cb_answer(cb)
    await cb.message.answer(
        "⚡ <b>پنل اصلی XGPedia</b> — کارت یا اقدام سریع را انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=_main_panel_markup(),
    )


@router.callback_query(F.data == "nav:cards")
async def on_nav_cards(cb: CallbackQuery) -> None:
    await _safe_cb_answer(cb)
    await cb.message.answer(
        "🎨 <b>استودیو کارت‌های XGPedia</b>\n\n"
        "⚽ <b>کارت‌های مسابقه:</b> پیش‌ازبازی · پس‌ازبازی (۲۴س)\n"
        "🕰 <b>تاریخ و تحریریه:</b> در چنین روزی (وقایع تاریخی)",
        parse_mode="HTML",
        reply_markup=_cards_studio_markup(),
    )


@router.callback_query(F.data == "nav:sync")
async def on_nav_sync(cb: CallbackQuery) -> None:
    await _safe_cb_answer(cb)
    await cb.message.answer(
        "📡 <b>مرکز دیتای زنده و همگام‌سازی</b>\nنوع بروزرسانی را انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=_sync_hub_markup(),
    )


@router.callback_query(F.data == "nav:show_kb")
async def on_nav_show_kb(cb: CallbackQuery) -> None:
    await _safe_cb_answer(cb, "کیبورد پایین باز شد.")
    await cb.message.answer(
        "⌨️ کیبورد پایین دوباره فعال شد.",
        reply_markup=_persistent_reply_keyboard(),
    )


def _render_ai_status_view(page: int = 1, page_size: int = 12) -> tuple[str, InlineKeyboardMarkup]:
    from src.xgpedia.editorial.llm_provider import (
        build_free_llm_chain_from_env,
        get_endpoint_cooldown_remaining,
        get_llm_start_index,
    )
    from src.xgpedia.media.free_media import FreeImageRouter, FreeVideoRouter

    chain = build_free_llm_chain_from_env()
    cur = get_llm_start_index()
    total = len(chain)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = min(total, start + page_size)

    model_lines: list[str] = []
    for i, ep in enumerate(chain[start:end], start + 1):
        star = "⭐ " if i == cur else ""
        cd_sec = get_endpoint_cooldown_remaining(ep)
        cd_badge = f" ⏳({cd_sec // 60 + 1}د)" if cd_sec > 0 else ""
        model_lines.append(f"{i}. {star}{html.escape(ep.label)}{cd_badge}")

    imgs = " ← ".join(FreeImageRouter().available_providers())
    vids = " ← ".join(FreeVideoRouter().available_providers()) or "غیرفعال"

    text = (
        f"🧠 <b>زنجیرهٔ فعال هوش مصنوعی ({total} مدل متن — صفحه {page} از {total_pages}):</b>\n"
        f"نقطهٔ شروع فعلی: <b>#{cur}</b>\n\n"
        + "\n".join(model_lines)
        + f"\n\n🖼 <b>تصویر:</b> {html.escape(imgs)}\n🎬 <b>ویدیو:</b> {html.escape(vids)}"
    )

    rows: list[list[InlineKeyboardButton]] = []
    if total_pages > 1:
        nav_row: list[InlineKeyboardButton] = []
        if page > 1:
            nav_row.append(InlineKeyboardButton(text="⬅️ صفحه قبل", callback_data=f"nav:ai_status:{page - 1}"))
        nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data=f"nav:ai_status:{page}"))
        if page < total_pages:
            nav_row.append(InlineKeyboardButton(text="➡️ صفحه بعد", callback_data=f"nav:ai_status:{page + 1}"))
        rows.append(nav_row)
    rows.append([
        InlineKeyboardButton(text="⚙️ انتخاب مدل شروع", callback_data="llm:menu"),
        InlineKeyboardButton(text="🔄 پاک‌سازی کول‌داون", callback_data="llm:reset_cd"),
    ])
    rows.append([
        InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="nav:home"),
    ])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "nav:ai_status")
async def on_nav_ai_status(cb: CallbackQuery) -> None:
    await _safe_cb_answer(cb)
    text, markup = _render_ai_status_view(page=1)
    await cb.message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("nav:ai_status:"))
async def on_nav_ai_status_page(cb: CallbackQuery) -> None:
    await _safe_cb_answer(cb)
    try:
        page = int(cb.data.split(":")[2])
    except (IndexError, ValueError):
        page = 1
    text, markup = _render_ai_status_view(page=page)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except TelegramBadRequest:
        pass


def _render_llm_settings_view(page: int = 1, page_size: int = 10) -> tuple[str, InlineKeyboardMarkup]:
    from src.xgpedia.editorial.llm_provider import (
        build_free_llm_chain_from_env,
        get_endpoint_cooldown_remaining,
        get_llm_start_index,
    )

    chain = build_free_llm_chain_from_env()
    cur = get_llm_start_index()
    total = len(chain)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = min(total, start + page_size)

    lines = [
        f"⚙️ <b>تنظیم مدل شروع هوش مصنوعی (LLM) — صفحه {page} از {total_pages}</b>",
        f"نقطهٔ شروع فعلی: <b>#{cur}</b> | مجموع مدل‌ها و کلیدهای فعال: <b>{total}</b>",
        "",
        "اگر مدل‌های ابتدایی مدام 429/503 یا Timeout می‌دهند، روی مدل سالم بزنید تا تولید متن از همان‌جا شروع شود (مدل‌های قبلی فقط در صورت خطای همهٔ مدل‌ها به‌عنوان پشتیبان آخر امتحان می‌شوند):",
    ]
    rows: list[list[InlineKeyboardButton]] = []
    for i, ep in enumerate(chain[start:end], start + 1):
        prefix = "✅ " if i == cur else ""
        cd_sec = get_endpoint_cooldown_remaining(ep)
        suffix = " ⏳" if cd_sec > 0 else ""
        rows.append([
            InlineKeyboardButton(
                text=f"{prefix}#{i}: {ep.label}{suffix}",
                callback_data=f"llm:set:{i}:{page}",
            )
        ])
    if total_pages > 1:
        nav_row: list[InlineKeyboardButton] = []
        if page > 1:
            nav_row.append(InlineKeyboardButton(text="⬅️ صفحه قبل", callback_data=f"llm:page:{page - 1}"))
        nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data=f"llm:page:{page}"))
        if page < total_pages:
            nav_row.append(InlineKeyboardButton(text="➡️ صفحه بعد", callback_data=f"llm:page:{page + 1}"))
        rows.append(nav_row)
    rows.append([
        InlineKeyboardButton(text="🔄 پاک‌سازی کول‌داون خطاهای موقت", callback_data="llm:reset_cd"),
    ])
    rows.append([
        InlineKeyboardButton(text="🧠 وضعیت کامل AI", callback_data="nav:ai_status"),
        InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="nav:home"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "llm:menu")
async def on_llm_menu(cb: CallbackQuery) -> None:
    await _safe_cb_answer(cb)
    text, markup = _render_llm_settings_view(page=1)
    await cb.message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("llm:page:"))
async def on_llm_page(cb: CallbackQuery) -> None:
    await _safe_cb_answer(cb)
    try:
        page = int(cb.data.split(":")[2])
    except (IndexError, ValueError):
        page = 1
    text, markup = _render_llm_settings_view(page=page)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("llm:set:"))
async def on_llm_set_start(cb: CallbackQuery) -> None:
    from src.xgpedia.editorial.llm_provider import clear_llm_cooldowns, set_llm_start_index

    parts = cb.data.split(":")
    idx = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else max(1, (idx - 1) // 10 + 1)
    set_llm_start_index(idx)
    clear_llm_cooldowns()
    await _safe_cb_answer(cb, f"✅ مدل شروع روی #{idx} تنظیم و ذخیره شد.")
    text, markup = _render_llm_settings_view(page=page)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "llm:reset_cd")
async def on_llm_reset_cooldown(cb: CallbackQuery) -> None:
    from src.xgpedia.editorial.llm_provider import clear_llm_cooldowns

    clear_llm_cooldowns()
    await _safe_cb_answer(cb, "✅ کول‌داون موقت مدل‌ها پاک شد.")


@router.callback_query(F.data == "today:sync")
async def on_today_sync(cb: CallbackQuery) -> None:
    await _run_sync_flow(cb, force=False)


@router.callback_query(F.data == "today:force_sync")
async def on_today_force_sync(cb: CallbackQuery) -> None:
    await _run_sync_flow(cb, force=True)


@router.callback_query(F.data == "today:list")
async def on_today_list(cb: CallbackQuery) -> None:
    await _safe_cb_answer(cb)
    matches = await asyncio.to_thread(tw.list_today_matches)
    text, markup = _format_matches_message(
        matches, header="📋 <b>لیست بازی‌های شروع‌نشدهٔ امروز (آماده در دیتابیس)</b>"
    )
    await cb.message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "today:schedules")
async def on_today_schedules(cb: CallbackQuery) -> None:
    await _safe_cb_answer(cb)
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
    sched_id = int(cb.data.split(":", 1)[1])
    try:
        tw.cancel_scheduled_publish(sched_id, cb.from_user.id)
        await _safe_cb_answer(cb, "زمان‌بندی لغو شد.")
        await cb.message.answer(
            f"✅ زمان‌بندی #{sched_id} لغو شد و پست به حالت آمادهٔ انتشار بازگشت.",
            reply_markup=_main_panel_markup(),
        )
    except Exception as e:
        await _safe_cb_answer(cb, str(e)[:200], show_alert=True)


# ─── هندلرهای پنل کاستومایز تعاملی کارت ───

@router.message(Command("postmatch"))
async def cmd_postmatch(m: Message) -> None:
    if not tp.is_admin(m.from_user.id):
        await m.answer("دسترسی غیرمجاز.")
        return
    status_msg = await m.answer("⏳ در حال دریافت زندهٔ بازی‌های پایان‌یافتهٔ ۲۴ ساعت اخیر...")
    s_info = await asyncio.to_thread(tw.sync_recent_finished_matches)
    matches = await asyncio.to_thread(tw.list_recent_finished_fixtures)
    hdr = f"🏁 <b>بازی‌های پایان‌یافته (۱ ثانیه تا ۲۴ ساعت پیش)</b>\n✅ ESPN: {s_info['espn_saved']} بازی ({s_info['espn_stats']} آمار) | FDO: {s_info['fdo_saved']} بازی"
    text, kb = _format_finished_matches_message(matches, header=hdr)
    await status_msg.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.in_({"post:list", "post:refresh"}))
async def on_post_match_list(cb: CallbackQuery) -> None:
    await _safe_cb_answer(cb, "در حال دریافت نتایج پایان‌یافتهٔ ۲۴ ساعت اخیر...")
    wait_msg = await cb.message.answer("⏳ در حال دریافت زندهٔ بازی‌های پایان‌یافتهٔ ۲۴ ساعت اخیر (ESPN + FDO)...")
    s_info = await asyncio.to_thread(tw.sync_recent_finished_matches)
    matches = await asyncio.to_thread(tw.list_recent_finished_fixtures)
    hdr = f"🏁 <b>بازی‌های پایان‌یافته (۱ ثانیه تا ۲۴ ساعت پیش)</b>\n✅ ESPN: {s_info['espn_saved']} بازی ({s_info['espn_stats']} آمار) | FDO: {s_info['fdo_saved']} بازی"
    text, kb = _format_finished_matches_message(matches, header=hdr)
    await wait_msg.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("pcust:"))
async def on_open_post_customizer(cb: CallbackQuery) -> None:
    fixture_id = _resolve_fixture(cb.data.split(":", 1)[1])
    await _safe_cb_answer(cb, "در حال بارگذاری ماژول‌های پس‌ازبازی...")
    try:
        opts = await asyncio.to_thread(tw.get_match_card_options, fixture_id, post_type="post_match")
    except Exception as e:
        await cb.message.answer(
            f"❌ خطا در خواندن اطلاعات پس‌ازبازی:\n{html.escape(type(e).__name__)}: {html.escape(str(e))}",
            parse_mode="HTML",
        )
        return

    st = {
        "fixture_id": fixture_id,
        "post_type": "post_match",
        "home_fa": opts["home_fa"],
        "away_fa": opts["away_fa"],
        "round": opts["round"],
        "stadium": opts["stadium"],
        "fmt": "4:5",
        "header_mode": "full",
        "broadcast_idx": 0,
        "modules": opts["available_modules"],
        "missing_modules": opts.get("missing_modules") or [],
    }
    _CUSTOMIZER_STATE[cb.from_user.id] = st
    text, markup = _render_customizer_view(st)
    await cb.message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith(("cust:", "gen:")))
async def on_open_customizer(cb: CallbackQuery) -> None:
    fixture_id = _resolve_fixture(cb.data.split(":", 1)[1])
    await _safe_cb_answer(cb, "در حال بارگذاری ماژول‌های موجود...")
    try:
        opts = await asyncio.to_thread(tw.get_match_card_options, fixture_id)
    except Exception as e:
        await cb.message.answer(
            f"❌ خطا در خواندن اطلاعات بازی:\n{html.escape(type(e).__name__)}: {html.escape(str(e))}",
            parse_mode="HTML",
        )
        return

    st = {
        "fixture_id": fixture_id,
        "home_fa": opts["home_fa"],
        "away_fa": opts["away_fa"],
        "round": opts["round"],
        "stadium": opts["stadium"],
        "fmt": "4:5",
        "header_mode": "full",
        "broadcast_idx": _broadcast_index_for(opts.get("broadcast") or ""),
        "modules": opts["available_modules"],
        "missing_modules": opts.get("missing_modules") or [],
    }
    _CUSTOMIZER_STATE[cb.from_user.id] = st
    text, markup = _render_customizer_view(st)
    await cb.message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("cz:"))
async def on_customizer_action(cb: CallbackQuery, bot: Bot) -> None:
    st = _CUSTOMIZER_STATE.get(cb.from_user.id)
    if not st:
        await _safe_cb_answer(cb, "لطفاً دوباره بازی را از لیست انتخاب کنید.", show_alert=True)
        return

    parts = cb.data.split(":")
    action = parts[1]

    if action == "noop":
        await _safe_cb_answer(cb, "این ماژول فقط تمام‌عرض است.")
        return
    if action == "noop_edge":
        await _safe_cb_answer(cb, "این ماژول در ابتدا یا انتهای لیست است.")
        return
    if action == "fmt":
        st["fmt"] = f"{parts[2]}:{parts[3]}"
        await _safe_cb_answer(cb, f"فرمت روی {st['fmt']} تنظیم شد.")
    elif action == "tone" and len(parts) >= 3:
        from src.xgpedia.editorial.narrative import EDITORIAL_TONES, normalize_tone
        tk = normalize_tone(parts[2])
        st["tone"] = tk
        await _safe_cb_answer(cb, f"لحن متن: {EDITORIAL_TONES[tk]['label_fa']}")
    elif action == "hm":
        st["header_mode"] = "compact" if st["header_mode"] == "full" else "full"
        await _safe_cb_answer(cb, f"هدر: {'کامل' if st['header_mode'] == 'full' else 'فشرده'}")
    elif action == "bc":
        st["broadcast_idx"] = (st["broadcast_idx"] + 1) % len(BROADCAST_CYCLE)
        await _safe_cb_answer(cb, f"پخش: {BROADCAST_CYCLE[st['broadcast_idx']][1]}")
    elif action == "tpl_save":
        tpl_kind = "post_match" if st.get("post_type") == "post_match" else "pre_match"
        _AWAITING_TEMPLATE_NAME[cb.from_user.id] = tpl_kind
        await _safe_cb_answer(cb, "نام قالب را بفرستید.")
        await cb.message.answer(
            "💾 <b>ذخیرهٔ چینش فعلی به‌عنوان قالب آماده</b>\n"
            "یک نام کوتاه برای این قالب بنویسید (مثلاً <code>چینش تاکتیکی من</code>) یا برای انصراف <code>لغو</code> بفرستید:",
            parse_mode="HTML",
        )
        return
    elif action == "tpl_list":
        from src.xgpedia.layout_templates import MAX_SAVED_TEMPLATES, list_layout_templates
        tpl_kind = "post_match" if st.get("post_type") == "post_match" else "pre_match"
        tpls = list_layout_templates(tpl_kind)
        await _safe_cb_answer(cb)
        if not tpls:
            await cb.message.answer("📂 هنوز قالبی ذخیره نکرده‌اید. روی «💾 ذخیره قالب» بزنید تا چینش فعلی ذخیره شود.")
            return
        t_rows = []
        for idx, tp_it in enumerate(tpls):
            t_rows.append([
                InlineKeyboardButton(text=f"📌 {tp_it['name']} ({tp_it.get('fmt', '4:5')})", callback_data=f"cz:tpl_use:{idx}"),
                InlineKeyboardButton(text="🗑", callback_data=f"cz:tpl_del:{idx}"),
            ])
        t_rows.append([InlineKeyboardButton(text="↩️ بازگشت به کاستومایزر", callback_data="cz:tpl_back")])
        await cb.message.edit_text(
            f"📂 <b>قالب‌های ذخیره‌شده ({len(tpls)} از {MAX_SAVED_TEMPLATES})</b>\nروی نام قالب بزنید تا فوری اعمال شود:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=t_rows),
        )
        return
    elif action == "tpl_use":
        from src.xgpedia.layout_templates import apply_template_to_modules, list_layout_templates
        tpl_kind = "post_match" if st.get("post_type") == "post_match" else "pre_match"
        tpls = list_layout_templates(tpl_kind)
        idx = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else -1
        if 0 <= idx < len(tpls):
            tpl = tpls[idx]
            st["fmt"] = tpl.get("fmt", st["fmt"])
            st["header_mode"] = tpl.get("header_mode", st["header_mode"])
            st["modules"] = apply_template_to_modules(st["modules"], tpl)
            await _safe_cb_answer(cb, f"✅ قالب «{tpl['name']}» اعمال شد!")
        else:
            await _safe_cb_answer(cb, "قالب یافت نشد.", show_alert=True)
    elif action == "tpl_del":
        from src.xgpedia.layout_templates import delete_layout_template
        tpl_kind = "post_match" if st.get("post_type") == "post_match" else "pre_match"
        idx = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else -1
        delete_layout_template(tpl_kind, idx)
        await _safe_cb_answer(cb, "🗑 قالب حذف شد.")
    elif action == "tpl_back":
        await _safe_cb_answer(cb)
    elif action == "tog":
        mod_id = parts[2]
        target = next((m for m in st["modules"] if m["id"] == mod_id), None)
        if target:
            active_cnt = sum(1 for m in st["modules"] if m["enabled"])
            if target["enabled"] and active_cnt <= 1:
                await _safe_cb_answer(cb, "حداقل یک ماژول باید فعال بماند.", show_alert=True)
                return
            target["enabled"] = not target["enabled"]
            await _safe_cb_answer(cb, f"{target['title_fa']}: {'فعال' if target['enabled'] else 'غیرفعال'}")
    elif action == "sp":
        mod_id = parts[2]
        target = next((m for m in st["modules"] if m["id"] == mod_id), None)
        if target and target["can_half"]:
            target["span"] = "half" if target["span"] == "full" else "full"
            target["enabled"] = True
            await _safe_cb_answer(cb, f"{target['title_fa']}: {'نیم‌عرض ½' if target['span'] == 'half' else 'تمام‌عرض ۱'}")
    elif action == "up":
        mod_id = parts[2]
        mods_list = st["modules"]
        idx = next((i for i, m in enumerate(mods_list) if m["id"] == mod_id), -1)
        if idx > 0:
            mods_list[idx - 1], mods_list[idx] = mods_list[idx], mods_list[idx - 1]
            await _safe_cb_answer(cb, f"⬆️ {mods_list[idx - 1]['title_fa']} یک ردیف بالا رفت.")
        else:
            await _safe_cb_answer(cb, "در بالاترین ردیف است.")
    elif action == "dn":
        mod_id = parts[2]
        mods_list = st["modules"]
        idx = next((i for i, m in enumerate(mods_list) if m["id"] == mod_id), -1)
        if 0 <= idx < len(mods_list) - 1:
            mods_list[idx + 1], mods_list[idx] = mods_list[idx], mods_list[idx + 1]
            await _safe_cb_answer(cb, f"⬇️ {mods_list[idx + 1]['title_fa']} یک ردیف پایین رفت.")
        else:
            await _safe_cb_answer(cb, "در پایین‌ترین ردیف است.")
    elif action == "build":
        active_mods = [m for m in st["modules"] if m["enabled"]]
        layout_errors = validate_half_width_layout(active_mods)
        if layout_errors:
            await _safe_cb_answer(cb, "❌ " + layout_errors[0][:190], show_alert=True)
            return
        await _safe_cb_answer(cb, "در حال ساخت کارت و کپشن نهایی...")
        selected = [{"id": m["id"], "span": m["span"]} for m in active_mods]
        post_type = st.get("post_type", "preview")
        bc_val = None if post_type == "post_match" else BROADCAST_CYCLE[st["broadcast_idx"]][0]
        wait_msg = await cb.message.answer(
            f"⏳ (۱/۳) در حال استخراج داده‌ها و نگارش متن تحریریه (LLM) برای "
            f"<b>{html.escape(st['home_fa'])} × {html.escape(st['away_fa'])}</b>...",
            parse_mode="HTML",
        )

        from src.xgpedia.publishers.progress_utils import LiveProgressReporter
        match_lbl = f"{st['home_fa']} × {st['away_fa']}"
        async def _raw_tb_edit(full_txt: str) -> None:
            await wait_msg.edit_text(f"{full_txt}\n⚽ <b>{html.escape(match_lbl)}</b>", parse_mode="HTML")
        _tb_rep = LiveProgressReporter(_raw_tb_edit, min_interval_sec=2.0, heartbeat_sec=5.0)
        _tb_rep.start_heartbeat()
        async def _progress(msg_text: str) -> None:
            await _tb_rep.update(msg_text)

        try:
            res = await tw.generate_match_post_async(
                st["fixture_id"],
                post_type=post_type,
                fmt=st["fmt"],
                header_mode=st["header_mode"],
                custom_modules=selected,
                broadcast_override=bc_val,
                tone=st.get("tone", "analytical"),
                progress_cb=_progress,
            )
        except Exception as e:
            await _tb_rep.stop_heartbeat()
            log.exception("unexpected error in cz:build")
            retry_kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🎛 بازگشت به تنظیمات کارت", callback_data=_cb_for_fixture("cust", st["fixture_id"]))],
                    [InlineKeyboardButton(text="📋 بازگشت به بازی‌های امروز", callback_data="today:list")],
                ]
            )
            await wait_msg.edit_text(
                f"❌ خطای غیرمنتظره در ساخت پست:\n{html.escape(type(e).__name__)}: {html.escape(str(e)[:500])}",
                parse_mode="HTML",
                reply_markup=retry_kb,
            )
            return

        if not res.ok:
            retry_kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🎛 بازگشت به تنظیمات کارت", callback_data=_cb_for_fixture("cust", st["fixture_id"]))],
                    [InlineKeyboardButton(text="📋 بازگشت به بازی‌های امروز", callback_data="today:list")],
                ]
            )
            await wait_msg.edit_text(
                html.escape(res.format_error_fa())[:3800], parse_mode="HTML", reply_markup=retry_kb
            )
            return

        await _progress("⏳ (۳/۳) کارت آماده شد! در حال ارسال پیش‌نمایش به تلگرام...")
        await _send_post_preview(
            bot,
            cb.from_user.id,
            res,
            wait_msg,
            note=f"✅ پست کامل ساخته شد (پست #{res.post_id} · نسخه {res.content_version} · فرمت {st['fmt']}).",
        )
        return

    # به‌روزرسانی آنی پیام کاستومایزر پس از هر تغییر دکمه (با تلاش مجدد در قطعی لحظه‌ای VPN/شبکه)
    text, markup = _render_customizer_view(st)
    for _attempt in range(3):
        try:
            await cb.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
            break
        except TelegramBadRequest:
            break
        except Exception as e:
            if _attempt == 2:
                log.warning("customizer edit_text failed after retries: %s", e)
            else:
                await asyncio.sleep(1.0)


# ─── تولید مجدد متن و ویرایش متن با توضیح ادمین ───

@router.callback_query(F.data.startswith("resend_prev:"))
async def on_resend_preview(cb: CallbackQuery, bot: Bot) -> None:
    post_id = int(cb.data.split(":", 1)[1])
    await _safe_cb_answer(cb, "در حال ارسال مجدد پیش‌نمایش...")
    cached = _LAST_GENERATED_PREVIEW.get(post_id)
    if cached is None:
        try:
            post = tp.load_post(post_id)
        except Exception as e:
            await cb.message.answer(f"❌ پست #{post_id} در دیتابیس پیدا نشد: {html.escape(str(e))}", parse_mode="HTML")
            return
        cached = tw.PostGenerationResult(
            ok=True,
            fixture_id=post.get("fixture_id") or "",
            post_id=post_id,
            content_version=int(post.get("content_version") or 1),
            image_path=_find_rendered_image_for_post(post_id),
        )
    wait_msg = await cb.message.answer(
        f"🔁 در حال ارسال مجدد <b>پست #{post_id}</b> به تلگرام (بدون ساخت مجدد)...",
        parse_mode="HTML",
    )
    await _send_post_preview(
        bot,
        cb.from_user.id,
        cached,
        wait_msg,
        note=f"✅ پیش‌نمایش پست #{post_id} با موفقیت ارسال مجدد شد.",
    )


@router.callback_query(F.data.startswith("regen_txt:"))
async def on_regen_text(cb: CallbackQuery, bot: Bot) -> None:
    post_id = int(cb.data.split(":", 1)[1])
    await _safe_cb_answer(cb, "در حال تولید مجدد متن...")
    wait_msg = await cb.message.answer(
        f"⏳ در حال تولید مجدد متن تحریریه (LLM) برای <b>پست #{post_id}</b>...",
        parse_mode="HTML",
    )
    try:
        res = await asyncio.wait_for(
            asyncio.to_thread(tw.regenerate_or_edit_post_text, post_id),
            timeout=120.0,
        )
    except Exception as e:
        await wait_msg.edit_text(
            f"❌ خطا در تولید مجدد متن:\n{html.escape(type(e).__name__)}: {html.escape(str(e)[:400])}",
            parse_mode="HTML",
        )
        return
    if not res.ok:
        await wait_msg.edit_text(html.escape(res.format_error_fa())[:3800], parse_mode="HTML")
        return
    await _send_post_preview(
        bot, cb.from_user.id, res, wait_msg,
        note=f"✅ متن جدید برای پست #{post_id} تولید شد (کارت تصویری بدون تغییر حفظ شد).",
    )


@router.callback_query(F.data.startswith("edit_txt:"))
async def on_ask_edit_text(cb: CallbackQuery) -> None:
    post_id = int(cb.data.split(":", 1)[1])
    _AWAITING_SCHEDULE_TIME.pop(cb.from_user.id, None)
    _AWAITING_EDIT_INSTRUCTION[cb.from_user.id] = post_id
    await _safe_cb_answer(cb, "توضیح ویرایش را در چت بنویسید.")
    await cb.message.answer(
        f"✏️ توضیح خود را برای ویرایش متن <b>پست #{post_id}</b> بفرستید.\n"
        f"مثلاً: <i>«تیتر را کوتاه‌تر و جذاب‌تر کن و بیشتر روی خط حمله لیورپول تمرکز کن»</i>\n"
        f"برای انصراف بنویسید: <code>لغو</code>",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("sched:"))
async def on_ask_schedule_time(cb: CallbackQuery) -> None:
    post_id = int(cb.data.split(":", 1)[1])
    _AWAITING_EDIT_INSTRUCTION.pop(cb.from_user.id, None)
    _AWAITING_SCHEDULE_TIME[cb.from_user.id] = post_id
    await _safe_cb_answer(cb, "ساعت را در چت ارسال کنید.")
    await cb.message.answer(
        f"⏰ برای زمان‌بندی انتشار خودکار <b>پست #{post_id}</b> در امروز، ساعت را با فرمت ۲۴ ساعته "
        f"(به وقت تهران) ارسال کنید — مثلاً <code>09:35</code> یا <code>21:15</code>.\n"
        f"برای انصراف بنویسید: <code>لغو</code>",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith(("approve:", "reject:", "edit:")))
async def on_decision(cb: CallbackQuery, bot: Bot) -> None:
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
            await _safe_cb_answer(cb, "منتشر شد.")
            await cb.message.answer(
                "پست با موفقیت در کانال منتشر شد. برای انتخاب بازی بعدی امروز:",
                reply_markup=_main_panel_markup(),
            )
        elif action == "reject":
            await tp.reject_post(post_id, cb.from_user.id)
            await transport.edit_text(
                cb.message.chat.id, cb.message.message_id, "❌ رد شد — بازگشت به صف تحریریه."
            )
            await _safe_cb_answer(cb, "رد شد.")
        else:
            await tp.back_to_draft(post_id, cb.from_user.id, action="edit")
            await transport.edit_text(
                cb.message.chat.id, cb.message.message_id, "✏️ به صف تحریریه بازگشت (draft)."
            )
            await _safe_cb_answer(cb, "بازگشت به صف.")
    except Exception as e:
        await _safe_cb_answer(cb, f"خطا: {str(e)[:180]}", show_alert=True)
    try:
        from src.xgpedia.db import record_post_metric
        _dec_map = {"approve": "approved", "reject": "rejected", "edit": "edited"}
        record_post_metric("match_post", _dec_map.get(action, action), post_id=post_id)
    except Exception:
        pass
    log.info("moderation action=%s post=%s by=%s", action, post_id, cb.from_user.id)


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




# ─── ثبت و re-export هندلرهای استودیویی (OTD, News, Birthday, Transfer, This-or-That) ───
from src.xgpedia.publishers.bot_studio_otd_news import (  # noqa: E402, F401
    _NEWS_ITEM_MAP,
    _NEWS_LAST_DATA,
    _NEWS_STATE,
    _OTD_EVENT_MAP,
    _OTD_STATE,
    _format_news_list_message,
    _format_otd_list_message,
    _render_news_customizer_view,
    _render_otd_customizer_view,
    cmd_news,
    cmd_onthisday,
    on_news_back,
    on_news_customizer_action,
    on_news_list,
    on_news_open,
    on_news_page,
    on_otd_back,
    on_otd_customizer_action,
    on_otd_list,
    on_otd_open,
)
from src.xgpedia.publishers.bot_studio_bday_transfer_tot import (  # noqa: E402, F401
    _AWAITING_BIRTHDAY_SEARCH,
    _AWAITING_TEMPLATE_NAME,
    _BDAY_ITEM_MAP,
    _BDAY_LAST_DATA,
    _BDAY_STATE,
    _TOT_ITEM_MAP,
    _TOT_LAST_LIST,
    _TOT_STATE,
    _TR_ITEM_MAP,
    _TR_LAST_DATA,
    _TR_STATE,
    _build_transfer_schematic,
    _format_birthday_list_message,
    _format_tot_list_message,
    _format_transfer_list_message,
    _render_birthday_customizer_view,
    _render_tot_customizer_view,
    _render_transfer_customizer_view,
    cmd_birthday,
    cmd_thisorthat,
    cmd_transfers,
    on_bday_back,
    on_bday_customizer_action,
    on_bday_list_page,
    on_bday_open,
    on_bday_presets,
    on_bday_refresh,
    on_bday_search,
    on_tot_ai_new,
    on_tot_back,
    on_tot_customizer_action,
    on_tot_list_page,
    on_tot_open,
    on_tr_back,
    on_tr_customizer_action,
    on_tr_list_page,
    on_tr_open,
    on_tr_presets,
    on_tr_refresh,
)

@router.message(Command("health"))
async def cmd_api_health(m: Message) -> None:
    from src.xgpedia.core.api_health import format_health_report_fa
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔄 ریست حافظه سلامت", callback_data="api:health_reset"),
        InlineKeyboardButton(text="🏠 پنل اصلی", callback_data="nav:home"),
    ]])
    await m.answer(format_health_report_fa(), parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "api:health")
async def on_api_health(cb: CallbackQuery) -> None:
    from src.xgpedia.core.api_health import format_health_report_fa
    await _safe_cb_answer(cb)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔄 ریست حافظه سلامت", callback_data="api:health_reset"),
        InlineKeyboardButton(text="🏠 پنل اصلی", callback_data="nav:home"),
    ]])
    await cb.message.answer(format_health_report_fa(), parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "api:health_reset")
async def on_api_health_reset(cb: CallbackQuery) -> None:
    from src.xgpedia.core.api_health import reset_health
    n = reset_health()
    await _safe_cb_answer(cb, f"حافظه سلامت پاک شد ({n} مورد).", show_alert=True)


@router.message(Command("platforms"))
async def cmd_omnichannel_status(m: Message) -> None:
    from src.xgpedia.publishers.omnichannel import format_omnichannel_status_fa
    await m.answer(format_omnichannel_status_fa(), parse_mode="HTML")


@router.callback_query(F.data == "omni:status")
async def on_omnichannel_status(cb: CallbackQuery) -> None:
    from src.xgpedia.publishers.omnichannel import format_omnichannel_status_fa
    await _safe_cb_answer(cb)
    await cb.message.answer(format_omnichannel_status_fa(), parse_mode="HTML")


async def main() -> None:
    import os
    from aiogram.client.session.aiohttp import AiohttpSession

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    validate_env()
    proxy_url = (os.getenv("TELEGRAM_PROXY_URL") or "").strip() or None
    session = AiohttpSession(proxy=proxy_url) if proxy_url else AiohttpSession()
    if proxy_url:
        log.info("using TELEGRAM_PROXY_URL=%s", proxy_url)
    bot = Bot(TELEGRAM_BOT_TOKEN, session=session)
    dp = Dispatcher()
    from src.xgpedia.publishers.modular_cards_bot import modular_router
    dp.include_router(modular_router)
    dp.include_router(router)
    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="🏠 خانه و باز کردن کیبورد پایین"),
            BotCommand(command="cards", description="🎨 استودیو کارت‌ها (پیش‌بازی، پس‌ازبازی، در چنین روزی)"),
            BotCommand(command="postmatch", description="🏁 کارت‌های پس‌ازبازی (۲۴ ساعت اخیر)"),
            BotCommand(command="onthisday", description="🕰 در چنین روزی (وقایع تاریخی فوتبال)"),
            BotCommand(command="news", description="📰 خبر فوری و رسمی (PRO WIRE v2)"),
            BotCommand(command="birthday", description="🎂 تولدهای امروز فوتبالیست‌ها (Birthday Studio)"),
            BotCommand(command="transfers", description="📡 رادار نقل‌وانتقالات (شایعات داغ)"),
            BotCommand(command="thisorthat", description="⚔️ این یا اون؟ (دوئل‌های جدالی و نظرسنجی)"),
            BotCommand(command="ratings", description="⭐️ نمرات بازیکنان (Players Rating)"),
            BotCommand(command="standings", description="🏆 جدول رده‌بندی (Standings)"),
            BotCommand(command="injury", description="🏥 آزمایشگاه مصدومیت (Injury Lab)"),
            BotCommand(command="player", description="🧬 پروفایل فنی بازیکن (Player Studio)"),
            BotCommand(command="h2hteams", description="⚔️ تقابل مستقیم تیم‌ها (H2H)"),
            BotCommand(command="fc27", description="🃏 کارت بازیکن FC27"),
            BotCommand(command="h2hplayers", description="🆚 مقایسه دو بازیکن (H2H)"),
            BotCommand(command="scorers", description="👟 جدول گلزنان / کفش طلا"),
            BotCommand(command="results", description="📊 نتایج بازی‌های روز"),
            BotCommand(command="wrapup", description="📈 خلاصهٔ هفته + فرم در برابر جدول"),
            BotCommand(command="shotmap", description="🎯 نقشهٔ شوت و مومنتوم امید گل"),
            BotCommand(command="value", description="💎 رادار ارزش بازار و شکار (+EV)"),
            BotCommand(command="lineup", description="📋 ترکیب احتمالی و غایبان"),
            BotCommand(command="health", description="🩺 گزارش سلامت و یادگیری هوشمند APIها"),
            BotCommand(command="platforms", description="🌐 وضعیت انتشار همزمان (بله، ایتا، ایکس، اینستاگرام)"),
        ])
    except Exception as _cmd_exc:
        log.warning("set_my_commands skipped: %s", _cmd_exc)

    async def _notify_admins(msg_text: str) -> None:
        for aid in sorted(ADMIN_TELEGRAM_IDS):
            try:
                await asyncio.wait_for(bot.send_message(aid, msg_text), timeout=4.0)
            except Exception:
                pass

    from src.xgpedia.core.background_warmer import background_warmer_loop
    sched_task = asyncio.create_task(_scheduler_loop(bot))
    warmer_task = asyncio.create_task(background_warmer_loop())
    log.info("bot polling started - admins: %s", sorted(ADMIN_TELEGRAM_IDS))
    await _notify_admins("🟢 ربات XGPedia آنلاین شد و آمادهٔ دریافت دستور است.")
    try:
        await dp.start_polling(bot)
    except (KeyboardInterrupt, asyncio.CancelledError):
        log.info("bot polling interrupted by user (Ctrl+C)")
    finally:
        sched_task.cancel()
        warmer_task.cancel()
        try:
            await _notify_admins("🔴 ربات XGPedia متوقف شد (آفلاین). برای فعال‌سازی مجدد، python run.py bot را اجرا کنید.")
        except Exception:
            pass
        try:
            await bot.session.close()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
