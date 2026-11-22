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
import logging
from typing import Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from src.xgpedia.config import ADMIN_TELEGRAM_IDS, TELEGRAM_BOT_TOKEN
from src.xgpedia.publishers import telegram_publish as tp
from src.xgpedia import today_workflow as tw
from src.xgpedia.render.card_kit.base_shell import validate_half_width_layout

router = Router()
log = logging.getLogger("xgpedia.bot")

_AWAITING_SCHEDULE_TIME: dict[int, int] = {}
_LAST_GENERATED_PREVIEW: dict[int, tw.PostGenerationResult] = {}
_AWAITING_EDIT_INSTRUCTION: dict[int, int] = {}
_FIXTURE_ALIAS: dict[str, str] = {}
# وضعیت کاستومایزر کارت به ازای هر ادمین: {admin_id: {...}}
_CUSTOMIZER_STATE: dict[int, dict[str, Any]] = {}

BROADCAST_CYCLE: list[tuple[str, str]] = [
    ("", "بدون برچسب پخش"),
    ("پخش زنده: شبکه سه", "شبکه سه"),
    ("پخش زنده: شبکه ورزش", "شبکه ورزش"),
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
    """کیبورد تاشو و دائمی پایین چت برای دسترسی سریع و یک‌لمسی ادمین در هر مرحله."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 بازی‌های امروز"), KeyboardButton(text="🔄 دریافت هوشمند")],
            [KeyboardButton(text="⚡ همگام‌سازی اجباری"), KeyboardButton(text="⏰ صف زمان‌بندی")],
            [KeyboardButton(text="🧠 وضعیت AI"), KeyboardButton(text="🏠 منوی اصلی")],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="از دکمه‌های پایین انتخاب کنید...",
    )


def _main_panel_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 دریافت بازی‌های امروز (هوشمند/کش)", callback_data="today:sync")],
            [InlineKeyboardButton(text="📋 لیست بازی‌های امروز", callback_data="today:list")],
            [
                InlineKeyboardButton(text="⚡ دریافت اجباری از API", callback_data="today:force_sync"),
                InlineKeyboardButton(text="⏰ صف زمان‌بندی", callback_data="today:schedules"),
            ],
            [
                InlineKeyboardButton(text="⚙️ تنظیم مدل شروع هوش مصنوعی (LLM)", callback_data="llm:menu"),
            ],
        ]
    )


def _preview_keyboard(post_id: int, fixture_id: str) -> dict[str, Any]:
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
                {"text": "🎛 ویرایش چیدمان کارت", "callback_data": _cb_for_fixture("cust", fixture_id)},
                {"text": "❌ رد", "callback_data": f"reject:{post_id}"},
            ],
            [
                {"text": "📋 لیست بازی‌های امروز", "callback_data": "today:list"},
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
        lines.append("⚽ هیچ بازی شروع‌نشده‌ای برای امروز در دیتابیس ثبت نشده است.")
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
        btn_text = f"⚽ {m.home_fa} × {m.away_fa} | {m.kickoff_tehran}{badge}"
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


def _short_mod_name(title_fa: str, max_len: int = 13) -> str:
    t = title_fa.strip()
    return t if len(t) <= max_len else t[: max_len - 1].rstrip() + "…"


def _build_layout_schematic(modules: list[dict[str, Any]]) -> tuple[str, list[str]]:
    """ساخت پیش‌نمایش شماتیک مکانی ماژول‌ها (ردیف‌به‌ردیف) + لیست خطاهای نیم‌عرض بدون جفت."""
    active = [m for m in modules if m.get("enabled", True)]
    errors = validate_half_width_layout(active)
    lines = ["┌─ 🏟 هدر + شانس برد ─┐"]
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
    schematic, layout_errors = _build_layout_schematic(mods)

    lines = [
        "🎛 <b>تنظیم و کاستومایز کارت پیش‌ازبازی</b>",
        f"⚽ <b>{html.escape(st['home_fa'])} × {html.escape(st['away_fa'])}</b>",
    ]
    meta_parts = [x for x in (st.get("round"), st.get("stadium")) if x]
    if meta_parts:
        lines.append("📍 " + html.escape(" • ".join(meta_parts)))
    lines.append(
        f"📐 فرمت: <b>{fmt}</b> | هدر: <b>{'کامل' if hm == 'full' else 'فشرده'}</b> | پخش: <b>{bc_lbl}</b>"
    )
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
            InlineKeyboardButton(
                text=f"هدر: {'کامل' if hm == 'full' else 'فشرده'} 🔁",
                callback_data="cz:hm",
            ),
            InlineKeyboardButton(
                text=f"پخش: {bc_lbl} 🔁",
                callback_data="cz:bc",
            ),
        ],
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

@router.message(Command("start", "panel"))
async def on_start(m: Message) -> None:
    if tp.is_admin(m.from_user.id):
        _AWAITING_SCHEDULE_TIME.pop(m.from_user.id, None)
        _AWAITING_EDIT_INSTRUCTION.pop(m.from_user.id, None)
        await m.answer(
            "🎛 <b>پنل مدیریت و انتشار خودکار XGPedia</b>\n\n"
            "با دکمهٔ زیر دیتای بازی‌های شروع‌نشدهٔ امروز را دریافت کنید (داده‌های موجود از کش دیتابیس خوانده می‌شوند)، "
            "ماژول‌ها و عرض هر ماژول را بچینید، متن را در صورت نیاز بازنویسی یا ویرایش کنید و فوری یا در ساعت دلخواه منتشر کنید.",
            parse_mode="HTML",
            reply_markup=_persistent_reply_keyboard(),
        )
        await m.answer("📌 میانبرهای سریع اینلاین:", reply_markup=_main_panel_markup())
    else:
        await m.answer("ربات انتشار XGPedia — فقط ادمین‌های مجاز به پنل مدیریت دسترسی دارند.")


@router.message(F.text)
async def on_any_text(m: Message, bot: Bot | None = None) -> None:
    user_id = m.from_user.id
    if not tp.is_admin(user_id):
        await m.answer("این ربات دستور متنی ندارد؛ فقط برای ادمین‌های XGPedia فعال است.")
        return

    raw_text = (m.text or "").strip()

    # ۰) دکمه‌های کیبورد تاشو/دائمی پایین صفحه
    if raw_text == "🏠 منوی اصلی":
        _AWAITING_SCHEDULE_TIME.pop(user_id, None)
        _AWAITING_EDIT_INSTRUCTION.pop(user_id, None)
        await m.answer(
            "🎛 <b>منوی اصلی XGPedia</b> — گزینهٔ دلخواه را انتخاب کنید:",
            parse_mode="HTML",
            reply_markup=_main_panel_markup(),
        )
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
            report = await asyncio.wait_for(asyncio.to_thread(tw.sync_today_matches, force=force_flag), timeout=90.0)
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
        from src.xgpedia.editorial.llm_provider import build_free_llm_chain_from_env
        from src.xgpedia.media.free_media import FreeImageRouter, FreeVideoRouter

        chain = build_free_llm_chain_from_env()
        top_llm = "\n".join(f"{i}. {html.escape(ep.label)}" for i, ep in enumerate(chain[:8], 1))
        imgs = " ← ".join(FreeImageRouter().available_providers())
        vids = " ← ".join(FreeVideoRouter().available_providers()) or "غیرفعال"
        await m.answer(
            f"🧠 <b>زنجیرهٔ فعال هوش مصنوعی ({len(chain)} مدل متن):</b>\n{top_llm}\n\n"
            f"🖼 <b>تصویر:</b> {html.escape(imgs)}\n🎬 <b>ویدیو:</b> {html.escape(vids)}",
            parse_mode="HTML",
            reply_markup=_main_panel_markup(),
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

async def _run_sync_flow(cb: CallbackQuery, *, force: bool) -> None:
    if not tp.is_admin(cb.from_user.id):
        await cb.answer("شما مجاز نیستید.", show_alert=True)
        return
    await cb.answer("در حال دریافت دیتای بازی‌های امروز...")
    mode_lbl = "اجباری از API" if force else "هوشمند (با استفاده از کش دیتابیس)"
    status_msg = await cb.message.answer(
        f"⏳ در حال بررسی بازی‌های امروز ({mode_lbl}) + جدول پخش شبکه سه و ورزش..."
    )
    try:
        report = await asyncio.wait_for(
            asyncio.to_thread(tw.sync_today_matches, force=force),
            timeout=90.0,
        )
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
    if not tp.is_admin(cb.from_user.id):
        await cb.answer("شما مجاز نیستید.", show_alert=True)
        return
    await cb.answer()
    await cb.message.answer(
        "🎛 <b>منوی اصلی XGPedia</b> — گزینهٔ دلخواه را انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=_main_panel_markup(),
    )




def _render_llm_settings_view() -> tuple[str, InlineKeyboardMarkup]:
    from src.xgpedia.editorial.llm_provider import (
        build_free_llm_chain_from_env,
        get_llm_start_index,
    )

    chain = build_free_llm_chain_from_env()
    cur = get_llm_start_index()
    lines = [
        "⚙️ <b>تنظیم مدل شروع هوش مصنوعی (LLM)</b>",
        f"نقطهٔ شروع فعلی: <b>#{cur}</b>",
        "",
        "اگر مدل‌های ابتدایی مدام 429/503 یا Timeout می‌دهند، روی مدل سالم بزنید تا تولید متن از همان‌جا شروع شود (مدل‌های قبلی فقط در صورت خطای همهٔ مدل‌ها به‌عنوان پشتیبان آخر امتحان می‌شوند):",
    ]
    rows: list[list[InlineKeyboardButton]] = []
    for i, ep in enumerate(chain[:12], 1):
        prefix = "✅ " if i == cur else ""
        rows.append([
            InlineKeyboardButton(
                text=f"{prefix}شروع از #{i}: {ep.label}",
                callback_data=f"llm:set:{i}",
            )
        ])
    rows.append([
        InlineKeyboardButton(text="🔄 پاک‌سازی کول‌داون خطاهای موقت", callback_data="llm:reset_cd"),
    ])
    rows.append([
        InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="nav:home"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "llm:menu")
async def on_llm_menu(cb: CallbackQuery) -> None:
    if not tp.is_admin(cb.from_user.id):
        await cb.answer("شما مجاز نیستید.", show_alert=True)
        return
    await cb.answer()
    text, markup = _render_llm_settings_view()
    await cb.message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("llm:set:"))
async def on_llm_set_start(cb: CallbackQuery) -> None:
    if not tp.is_admin(cb.from_user.id):
        await cb.answer("شما مجاز نیستید.", show_alert=True)
        return
    from src.xgpedia.editorial.llm_provider import clear_llm_cooldowns, set_llm_start_index

    idx = int(cb.data.split(":")[2])
    set_llm_start_index(idx)
    clear_llm_cooldowns()
    await cb.answer(f"✅ مدل شروع روی #{idx} تنظیم و ذخیره شد.")
    text, markup = _render_llm_settings_view()
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "llm:reset_cd")
async def on_llm_reset_cooldown(cb: CallbackQuery) -> None:
    if not tp.is_admin(cb.from_user.id):
        await cb.answer("شما مجاز نیستید.", show_alert=True)
        return
    from src.xgpedia.editorial.llm_provider import clear_llm_cooldowns

    clear_llm_cooldowns()
    await cb.answer("✅ کول‌داون موقت مدل‌ها پاک شد.")


@router.callback_query(F.data == "today:sync")
async def on_today_sync(cb: CallbackQuery) -> None:
    await _run_sync_flow(cb, force=False)


@router.callback_query(F.data == "today:force_sync")
async def on_today_force_sync(cb: CallbackQuery) -> None:
    await _run_sync_flow(cb, force=True)


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


# ─── هندلرهای پنل کاستومایز تعاملی کارت ───

@router.callback_query(F.data.startswith(("cust:", "gen:")))
async def on_open_customizer(cb: CallbackQuery) -> None:
    if not tp.is_admin(cb.from_user.id):
        await cb.answer("شما مجاز نیستید.", show_alert=True)
        return
    fixture_id = _resolve_fixture(cb.data.split(":", 1)[1])
    await cb.answer("در حال بارگذاری ماژول‌های موجود...")
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
    if not tp.is_admin(cb.from_user.id):
        await cb.answer("شما مجاز نیستید.", show_alert=True)
        return
    st = _CUSTOMIZER_STATE.get(cb.from_user.id)
    if not st:
        await cb.answer("لطفاً دوباره بازی را از لیست انتخاب کنید.", show_alert=True)
        return

    parts = cb.data.split(":")
    action = parts[1]

    if action == "noop":
        await cb.answer("این ماژول فقط تمام‌عرض است.")
        return
    if action == "noop_edge":
        await cb.answer("این ماژول در ابتدا یا انتهای لیست است.")
        return
    if action == "fmt":
        st["fmt"] = f"{parts[2]}:{parts[3]}"
        await cb.answer(f"فرمت روی {st['fmt']} تنظیم شد.")
    elif action == "hm":
        st["header_mode"] = "compact" if st["header_mode"] == "full" else "full"
        await cb.answer(f"هدر: {'کامل' if st['header_mode'] == 'full' else 'فشرده'}")
    elif action == "bc":
        st["broadcast_idx"] = (st["broadcast_idx"] + 1) % len(BROADCAST_CYCLE)
        await cb.answer(f"پخش: {BROADCAST_CYCLE[st['broadcast_idx']][1]}")
    elif action == "tog":
        mod_id = parts[2]
        target = next((m for m in st["modules"] if m["id"] == mod_id), None)
        if target:
            active_cnt = sum(1 for m in st["modules"] if m["enabled"])
            if target["enabled"] and active_cnt <= 1:
                await cb.answer("حداقل یک ماژول باید فعال بماند.", show_alert=True)
                return
            target["enabled"] = not target["enabled"]
            await cb.answer(f"{target['title_fa']}: {'فعال' if target['enabled'] else 'غیرفعال'}")
    elif action == "sp":
        mod_id = parts[2]
        target = next((m for m in st["modules"] if m["id"] == mod_id), None)
        if target and target["can_half"]:
            target["span"] = "half" if target["span"] == "full" else "full"
            target["enabled"] = True
            await cb.answer(f"{target['title_fa']}: {'نیم‌عرض ½' if target['span'] == 'half' else 'تمام‌عرض ۱'}")
    elif action == "up":
        mod_id = parts[2]
        mods_list = st["modules"]
        idx = next((i for i, m in enumerate(mods_list) if m["id"] == mod_id), -1)
        if idx > 0:
            mods_list[idx - 1], mods_list[idx] = mods_list[idx], mods_list[idx - 1]
            await cb.answer(f"⬆️ {mods_list[idx - 1]['title_fa']} یک ردیف بالا رفت.")
        else:
            await cb.answer("در بالاترین ردیف است.")
    elif action == "dn":
        mod_id = parts[2]
        mods_list = st["modules"]
        idx = next((i for i, m in enumerate(mods_list) if m["id"] == mod_id), -1)
        if 0 <= idx < len(mods_list) - 1:
            mods_list[idx + 1], mods_list[idx] = mods_list[idx], mods_list[idx + 1]
            await cb.answer(f"⬇️ {mods_list[idx + 1]['title_fa']} یک ردیف پایین رفت.")
        else:
            await cb.answer("در پایین‌ترین ردیف است.")
    elif action == "build":
        active_mods = [m for m in st["modules"] if m["enabled"]]
        layout_errors = validate_half_width_layout(active_mods)
        if layout_errors:
            await cb.answer("❌ " + layout_errors[0][:190], show_alert=True)
            return
        await cb.answer("در حال ساخت کارت و کپشن نهایی...")
        selected = [{"id": m["id"], "span": m["span"]} for m in active_mods]
        bc_val = BROADCAST_CYCLE[st["broadcast_idx"]][0]
        wait_msg = await cb.message.answer(
            f"⏳ (۱/۳) در حال استخراج داده‌ها و نگارش متن تحریریه (LLM) برای "
            f"<b>{html.escape(st['home_fa'])} × {html.escape(st['away_fa'])}</b>...",
            parse_mode="HTML",
        )

        async def _progress(msg_text: str) -> None:
            try:
                await wait_msg.edit_text(
                    f"{msg_text}\n⚽ <b>{html.escape(st['home_fa'])} × {html.escape(st['away_fa'])}</b>",
                    parse_mode="HTML",
                )
            except TelegramBadRequest:
                pass

        try:
            res = await tw.generate_match_post_async(
                st["fixture_id"],
                fmt=st["fmt"],
                header_mode=st["header_mode"],
                custom_modules=selected,
                broadcast_override=bc_val,
                progress_cb=_progress,
            )
        except Exception as e:
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

    # به‌روزرسانی آنی پیام کاستومایزر پس از هر تغییر دکمه
    text, markup = _render_customizer_view(st)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except TelegramBadRequest:
        pass


# ─── تولید مجدد متن و ویرایش متن با توضیح ادمین ───

@router.callback_query(F.data.startswith("resend_prev:"))
async def on_resend_preview(cb: CallbackQuery, bot: Bot) -> None:
    if not tp.is_admin(cb.from_user.id):
        await cb.answer("شما مجاز نیستید.", show_alert=True)
        return
    post_id = int(cb.data.split(":", 1)[1])
    await cb.answer("در حال ارسال مجدد پیش‌نمایش...")
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
    if not tp.is_admin(cb.from_user.id):
        await cb.answer("شما مجاز نیستید.", show_alert=True)
        return
    post_id = int(cb.data.split(":", 1)[1])
    await cb.answer("در حال تولید مجدد متن...")
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
    if not tp.is_admin(cb.from_user.id):
        await cb.answer("شما مجاز نیستید.", show_alert=True)
        return
    post_id = int(cb.data.split(":", 1)[1])
    _AWAITING_SCHEDULE_TIME.pop(cb.from_user.id, None)
    _AWAITING_EDIT_INSTRUCTION[cb.from_user.id] = post_id
    await cb.answer("توضیح ویرایش را در چت بنویسید.")
    await cb.message.answer(
        f"✏️ توضیح خود را برای ویرایش متن <b>پست #{post_id}</b> بفرستید.\n"
        f"مثلاً: <i>«تیتر را کوتاه‌تر و جذاب‌تر کن و بیشتر روی خط حمله لیورپول تمرکز کن»</i>\n"
        f"برای انصراف بنویسید: <code>لغو</code>",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("sched:"))
async def on_ask_schedule_time(cb: CallbackQuery) -> None:
    if not tp.is_admin(cb.from_user.id):
        await cb.answer("شما مجاز نیستید.", show_alert=True)
        return
    post_id = int(cb.data.split(":", 1)[1])
    _AWAITING_EDIT_INSTRUCTION.pop(cb.from_user.id, None)
    _AWAITING_SCHEDULE_TIME[cb.from_user.id] = post_id
    await cb.answer("ساعت را در چت ارسال کنید.")
    await cb.message.answer(
        f"⏰ برای زمان‌بندی انتشار خودکار <b>پست #{post_id}</b> در امروز، ساعت را با فرمت ۲۴ ساعته "
        f"(به وقت تهران) ارسال کنید — مثلاً <code>09:35</code> یا <code>21:15</code>.\n"
        f"برای انصراف بنویسید: <code>لغو</code>",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith(("approve:", "reject:", "edit:")))
async def on_decision(cb: CallbackQuery, bot: Bot) -> None:
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
