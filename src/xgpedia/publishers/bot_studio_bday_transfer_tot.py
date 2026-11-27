"""هندلرها و نماهای استودیویی «تولدت مبارک»، «رادار نقل‌وانتقالات» و «این یا اون؟» (استخراج‌شده از telegram_bot.py در v0.73.0)."""
from __future__ import annotations

import asyncio
import html
import json
import logging
from pathlib import Path
from typing import Any

from aiogram import Bot, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.xgpedia import today_workflow as tw
from src.xgpedia.db import PersistentStateDict
from src.xgpedia.publishers import telegram_publish as tp
from src.xgpedia.publishers.telegram_bot import (
    _safe_cb_answer,
    _send_post_preview,
    log,
    router,
)


# ─── پنل و کاستومایزر اسلایدی «تولدت مبارک اسطوره» (Birthday Studio D47 — صفحه‌بندی کامل) ───

_BDAY_STATE: Any = PersistentStateDict("bday_state", key_type=int)
_BDAY_ITEM_MAP: dict[str, dict[str, Any]] = {}
_BDAY_LAST_DATA: dict[str, list[dict[str, Any]]] = {"live": [], "presets": []}
_AWAITING_BIRTHDAY_SEARCH: set[int] = set()


def _format_birthday_list_message(
    data: dict[str, list[dict[str, Any]]],
    *,
    page: int = 1,
    page_size: int = 8,
    show_presets: bool = False,
) -> tuple[str, InlineKeyboardMarkup]:
    _BDAY_LAST_DATA["live"] = list(data.get("live") or [])
    _BDAY_LAST_DATA["presets"] = list(data.get("presets") or [])
    live_items = _BDAY_LAST_DATA["live"]
    presets = _BDAY_LAST_DATA["presets"]
    rows: list[list[InlineKeyboardButton]] = []

    if show_presets or not live_items:
        lines = [
            "🎂 <b>استودیو کارت تولد XGPedia — پریست‌های آماده اسطوره‌ها</b>",
            "حالت: <b>اسلایدی</b> (۳ سبک: پوستر اسطوره · شناسنامه آماری · کاور مینی‌مال × ۳ فرمت × ۶ ماژول)",
            "",
        ]
        if not live_items and not show_presets:
            lines.append("ℹ️ امروز لیست زنده از ویکی‌دیتا/ویکی‌پدیا دریافت نشد؛ می‌توانید از پریست‌ها یا جستجوی دلخواه استفاده کنید:")
            lines.append("")
        for it in presets:
            iid = str(it["id"])
            _BDAY_ITEM_MAP[iid] = it
            rows.append([InlineKeyboardButton(
                text=f"⭐ {it['nameFa']} ({it.get('age', '')} سالگی) — {it.get('club', '')}"[:54],
                callback_data=f"bday:open:{iid[:44]}",
            )])
        nav_top: list[InlineKeyboardButton] = [
            InlineKeyboardButton(text="🔍 جستجوی بازیکن دلخواه", callback_data="bday:search"),
        ]
        if live_items:
            nav_top.append(InlineKeyboardButton(text=f"🌍 تولدهای امروز ({len(live_items)})", callback_data="bday:list:1"))
        rows.append(nav_top)
        rows.append([
            InlineKeyboardButton(text="🔄 بروزرسانی تولدهای امروز", callback_data="bday:refresh"),
            InlineKeyboardButton(text="🎨 استودیو کارت‌ها", callback_data="nav:cards"),
        ])
        return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)

    total = len(live_items)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = min(total, start + page_size)

    lines = [
        f"🎂 <b>تولدهای امروز دنیای فوتبال (صفحه {page} از {total_pages} — مجموع {total} بازیکن)</b>",
        "منابع زنده: <b>Wikidata SPARQL + Wikimedia (EN/FA) + Wikipedia Infobox + TheSportsDB</b>",
        "روی هر بازیکن بزنید تا آمار واقعی، باشگاه‌ها، افتخارات و عکس او خودکار استخراج شود:",
    ]
    for idx, it in enumerate(live_items[start:end], start + 1):
        iid = str(it["id"])
        _BDAY_ITEM_MAP[iid] = it
        age_s = f" ({it['age']}س)" if it.get("age") else ""
        nat_s = f" · {it['nat']}" if it.get("nat") else ""
        lbl = f"{idx}. 🎂 {it.get('nameFa') or it.get('nameEn')}{age_s}{nat_s}"[:54]
        rows.append([InlineKeyboardButton(text=lbl, callback_data=f"bday:open:{iid[:44]}")])

    if total_pages > 1:
        nav_p: list[InlineKeyboardButton] = []
        if page > 1:
            nav_p.append(InlineKeyboardButton(text="⬅️ صفحه قبل", callback_data=f"bday:list:{page - 1}"))
        nav_p.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data=f"bday:list:{page}"))
        if page < total_pages:
            nav_p.append(InlineKeyboardButton(text="➡️ صفحه بعد", callback_data=f"bday:list:{page + 1}"))
        rows.append(nav_p)

    rows.append([
        InlineKeyboardButton(text="🔍 جستجوی بازیکن دلخواه", callback_data="bday:search"),
        InlineKeyboardButton(text="⭐ پریست‌های آماده (۵)", callback_data="bday:presets"),
    ])
    rows.append([
        InlineKeyboardButton(text="🔄 بروزرسانی زنده", callback_data="bday:refresh"),
        InlineKeyboardButton(text="🎨 استودیو کارت‌ها", callback_data="nav:cards"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def _render_birthday_customizer_view(st: dict[str, Any]) -> tuple[str, InlineKeyboardMarkup]:
    from src.xgpedia.render.card_kit.birthday_card import BIRTHDAY_FORMATS, BIRTHDAY_MODES

    it = st["item"]
    mode = st["mode"]
    fmt = st["fmt"]
    rim = st.get("rim_light", True)
    mods = st["modules"]
    missing = st.get("missing_modules") or []

    m_lbl = next((lbl for mid, lbl, _ in BIRTHDAY_MODES if mid == mode), mode)
    active_cnt = sum(1 for m in mods if m["enabled"])

    lines = [
        "🎂 <b>استودیو کارت تولد XGPedia — تنظیمات اسلاید</b>",
        f"👤 <b>{html.escape(str(it.get('nameFa') or it.get('nameEn') or ''))}</b>"
        + (f" ({it['age']} سالگی)" if it.get("age") else ""),
        f"🖼 سبک طراحی: <b>{html.escape(m_lbl)}</b> | 📐 فرمت: <b>{fmt}</b>",
        f"✨ هاله نور پرتره: <b>{'روشن' if rim else 'خاموش'}</b> | 🧩 ماژول‌های فعال: <b>{active_cnt} از {len(mods)}</b>",
    ]
    if missing:
        lines.append("ℹ️ ماژول‌های بدون دیتای ثبت‌شده (قانون null≠0): " + html.escape("، ".join(missing)))

    rows: list[list[InlineKeyboardButton]] = []
    # ۱) ۳ سبک طراحی
    rows.append([
        InlineKeyboardButton(
            text=("✅ " if mid == mode else "") + mlbl.split("(")[0].strip(),
            callback_data=f"bdayc:md:{mid}",
        )
        for mid, mlbl, _ in BIRTHDAY_MODES
    ])
    # ۲) ۳ فرمت
    rows.append([
        InlineKeyboardButton(text=("✅ " if f == fmt else "") + f, callback_data=f"bdayc:fmt:{f.replace(':', '_')}")
        for f in BIRTHDAY_FORMATS
    ])
    # ۳) هاله نور Rim-Light
    rows.append([
        InlineKeyboardButton(
            text=f"✨ هاله نور پرتره (Rim-Light): {'✅ روشن' if rim else '⬜ خاموش'}",
            callback_data="bdayc:rim",
        )
    ])
    # ۴) ماژول‌های دارای دیتای واقعی
    if mode != "minimal":
        for m in mods:
            icon = "✅" if m["enabled"] else "⬜"
            rows.append([InlineKeyboardButton(text=f"{icon} {m['title_fa']}", callback_data=f"bdayc:tog:{m['id']}")])

    rows.append([InlineKeyboardButton(text="🎨 ساخت کارت و کپشن نهایی", callback_data="bdayc:build")])
    rows.append([
        InlineKeyboardButton(text="🎂 لیست تولدهای امروز", callback_data="bday:list:1"),
        InlineKeyboardButton(text="🎨 استودیو کارت‌ها", callback_data="nav:cards"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("birthday"))
async def cmd_birthday(m: Message) -> None:
    if not tp.is_admin(m.from_user.id):
        await m.answer("دسترسی غیرمجاز.")
        return
    from src.xgpedia.providers.birthday_free import list_birthday_items
    status_msg = await m.answer("⏳ در حال دریافت تولدهای امروز فوتبالیست‌ها از Wikidata و Wikimedia...")
    data = await asyncio.to_thread(list_birthday_items, include_live=True)
    text, kb = _format_birthday_list_message(data, page=1)
    await status_msg.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("bday:list:"))
async def on_bday_list_page(cb: CallbackQuery) -> None:
    from src.xgpedia.providers.birthday_free import list_birthday_items
    try:
        page = int(cb.data.split(":")[2])
    except (IndexError, ValueError):
        page = 1
    if not _BDAY_LAST_DATA.get("live") and not _BDAY_LAST_DATA.get("presets"):
        await _safe_cb_answer(cb, "در حال دریافت تولدهای امروز...")
        wait_msg = await cb.message.answer("⏳ در حال دریافت تولدهای امروز فوتبالیست‌ها از Wikidata و Wikimedia...")
        data = await asyncio.to_thread(list_birthday_items, include_live=True)
        text, kb = _format_birthday_list_message(data, page=page)
        await wait_msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
        return
    await _safe_cb_answer(cb)
    text, kb = _format_birthday_list_message(_BDAY_LAST_DATA, page=page)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except TelegramBadRequest:
        await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "bday:refresh")
async def on_bday_refresh(cb: CallbackQuery) -> None:
    from src.xgpedia.providers.birthday_free import list_birthday_items
    await _safe_cb_answer(cb, "در حال بروزرسانی زنده تولدهای امروز...")
    wait_msg = await cb.message.answer("⏳ در حال دریافت زندهٔ تولدهای امروز از Wikidata + Wikimedia...")
    data = await asyncio.to_thread(list_birthday_items, include_live=True, force_refresh=True)
    text, kb = _format_birthday_list_message(data, page=1)
    await wait_msg.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "bday:presets")
async def on_bday_presets(cb: CallbackQuery) -> None:
    from src.xgpedia.providers.birthday_free import load_birthday_presets
    await _safe_cb_answer(cb)
    if not _BDAY_LAST_DATA.get("presets"):
        _BDAY_LAST_DATA["presets"] = load_birthday_presets()
    text, kb = _format_birthday_list_message(_BDAY_LAST_DATA, show_presets=True)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except TelegramBadRequest:
        await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "bday:search")
async def on_bday_search(cb: CallbackQuery) -> None:
    _AWAITING_BIRTHDAY_SEARCH.add(cb.from_user.id)
    await _safe_cb_answer(cb, "نام بازیکن را بفرستید.")
    await cb.message.answer(
        "🔍 <b>جستجوی بازیکن برای کارت تولد</b>\n"
        "نام بازیکن را به انگلیسی یا فارسی بنویسید (مثلاً <code>Sardar Azmoun</code> یا <code>علی دایی</code>) یا برای انصراف <code>لغو</code> بفرستید:",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("bday:open:"))
async def on_bday_open(cb: CallbackQuery) -> None:
    from src.xgpedia.providers.birthday_free import _enrich_from_thesportsdb, _enrich_from_wikipedia
    from src.xgpedia.render.card_kit.birthday_card import BIRTHDAY_DEFAULT_MODE, get_birthday_modules

    iid = cb.data.split(":", 2)[2]
    it = _BDAY_ITEM_MAP.get(iid)
    if not it:
        await _safe_cb_answer(cb, "بازیکن در کش نیست؛ لطفاً لیست را بروزرسانی کنید.", show_alert=True)
        return
    await _safe_cb_answer(cb, "در حال استخراج آمار و افتخارات واقعی...")
    wait_m = await cb.message.answer(
        f"⏳ در حال بررسی پروفایل <b>{html.escape(str(it.get('nameFa') or it.get('nameEn') or ''))}</b> در ویکی‌پدیا و TheSportsDB...",
        parse_mode="HTML",
    )
    enriched = dict(it)
    if not str(enriched.get("id") or "").startswith("preset_"):
        def _quick_enrich() -> dict[str, Any]:
            _enrich_from_wikipedia(enriched, timeout=6.0)
            _enrich_from_thesportsdb(enriched, timeout=6.0)
            return enriched
        try:
            enriched = await asyncio.wait_for(asyncio.to_thread(_quick_enrich), timeout=16.0)
        except Exception:
            pass
    # یادداشت تحریریه همیشه در مرحلهٔ ساخت با LLM تولید می‌شود پس quote را به‌عنوان ماژول قابل انتخاب نگه می‌داریم
    if not enriched.get("quote"):
        enriched["quote"] = {"title": "یادداشت تحریریه تولد", "body": "(در مرحلهٔ ساخت نهایی با هوش مصنوعی نگارش می‌شود)", "tag": "XGPedia"}
    mods, missing = get_birthday_modules(enriched, BIRTHDAY_DEFAULT_MODE)
    # برگرداندن quote به None اگر placeholder بود تا در مرحلهٔ ساخت واقعی با LLM نوشته شود
    if enriched["quote"]["body"].startswith("(در مرحلهٔ"):
        enriched["quote"] = None

    st = {
        "item": enriched,
        "mode": BIRTHDAY_DEFAULT_MODE,
        "fmt": "4:5",
        "rim_light": True,
        "modules": mods,
        "missing_modules": missing,
    }
    _BDAY_STATE[cb.from_user.id] = st
    text, markup = _render_birthday_customizer_view(st)
    await wait_m.edit_text(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "bday:back")
async def on_bday_back(cb: CallbackQuery) -> None:
    st = _BDAY_STATE.get(cb.from_user.id)
    if not st:
        await _safe_cb_answer(cb, "لطفاً دوباره بازیکن را انتخاب کنید.", show_alert=True)
        return
    await _safe_cb_answer(cb)
    text, markup = _render_birthday_customizer_view(st)
    await cb.message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("bdayc:"))
async def on_bday_customizer_action(cb: CallbackQuery, bot: Bot) -> None:
    st = _BDAY_STATE.get(cb.from_user.id)
    if not st:
        await _safe_cb_answer(cb, "لطفاً دوباره بازیکن را انتخاب کنید.", show_alert=True)
        return

    parts = cb.data.split(":")
    action = parts[1]

    if action == "md":
        st["mode"] = parts[2] if parts[2] in ("poster", "dossier", "minimal") else "poster"
        await _safe_cb_answer(cb, f"سبک کارت روی {st['mode']} تنظیم شد.")
    elif action == "fmt":
        st["fmt"] = parts[2].replace("_", ":")
        await _safe_cb_answer(cb, f"فرمت روی {st['fmt']} تنظیم شد.")
    elif action == "rim":
        st["rim_light"] = not st.get("rim_light", True)
        await _safe_cb_answer(cb, "هاله نور: " + ("روشن" if st["rim_light"] else "خاموش"))
    elif action == "noop":
        await _safe_cb_answer(cb)
        return
    elif action == "mp":
        st["mod_page"] = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
        await _safe_cb_answer(cb)
    elif action == "tog":
        mid = parts[2]
        target = next((m for m in st["modules"] if m["id"] == mid), None)
        if target:
            target["enabled"] = not target["enabled"]
            st["slide"] = "custom"
            await _safe_cb_answer(cb, f"{target['title_fa']}: {'فعال' if target['enabled'] else 'غیرفعال'}")
    elif action == "sp":
        mid = parts[2]
        target = next((m for m in st["modules"] if m["id"] == mid), None)
        if target and target.get("can_half", False):
            target["span"] = "full" if target.get("span") == "half" else "half"
            target["half"] = target["span"] == "half"
            st["slide"] = "custom"
            await _safe_cb_answer(cb, "عرض: " + ("نیم‌عرض ½" if target["span"] == "half" else "تمام‌عرض ۱"))
    elif action in ("up", "dn"):
        mid = parts[2]
        mods_l = st["modules"]
        idx = next((i for i, m in enumerate(mods_l) if m["id"] == mid), -1)
        if action == "up" and idx > 0:
            mods_l[idx - 1], mods_l[idx] = mods_l[idx], mods_l[idx - 1]
            st["slide"] = "custom"
            await _safe_cb_answer(cb, "⬆️ یک ردیف بالا رفت.")
        elif action == "dn" and 0 <= idx < len(mods_l) - 1:
            mods_l[idx + 1], mods_l[idx] = mods_l[idx], mods_l[idx + 1]
            st["slide"] = "custom"
            await _safe_cb_answer(cb, "⬇️ یک ردیف پایین رفت.")
        else:
            await _safe_cb_answer(cb)
            return
    elif action == "tpl_save":
        _AWAITING_TEMPLATE_NAME[cb.from_user.id] = "transfer_radar"
        await _safe_cb_answer(cb, "نام قالب را بفرستید.")
        await cb.message.answer(
            "💾 <b>ذخیرهٔ چینش فعلی رادار نقل‌وانتقالات</b>\n"
            "یک نام کوتاه برای این قالب بنویسید (مثلاً <code>شایعه سریع</code> یا <code>تحلیل تاکتیکی</code>) یا برای انصراف <code>لغو</code> بفرستید:",
            parse_mode="HTML",
        )
        return
    elif action == "tpl_list":
        from src.xgpedia.layout_templates import MAX_SAVED_TEMPLATES, list_layout_templates
        tpls = list_layout_templates("transfer_radar")
        await _safe_cb_answer(cb)
        if not tpls:
            await cb.message.answer("📂 هنوز قالبی ذخیره نکرده‌اید. ابتدا روی «💾 ذخیره قالب» بزنید.")
            return
        t_rows = []
        for idx, tp_it in enumerate(tpls):
            t_rows.append([
                InlineKeyboardButton(text=f"📌 {tp_it['name']} ({tp_it.get('fmt', '4:5')})", callback_data=f"trc:tpl_use:{idx}"),
                InlineKeyboardButton(text="🗑", callback_data=f"trc:tpl_del:{idx}"),
            ])
        t_rows.append([InlineKeyboardButton(text="↩️ بازگشت به کاستومایزر", callback_data="trc:tpl_back")])
        await cb.message.edit_text(
            f"📂 <b>قالب‌های ذخیره‌شده رادار نقل‌وانتقالات ({len(tpls)} از {MAX_SAVED_TEMPLATES})</b>\nروی نام قالب بزنید تا فوری اعمال شود:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=t_rows),
        )
        return
    elif action == "tpl_use":
        from src.xgpedia.layout_templates import apply_template_to_modules, list_layout_templates
        tpls = list_layout_templates("transfer_radar")
        idx = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else -1
        if 0 <= idx < len(tpls):
            tpl = tpls[idx]
            st["fmt"] = tpl.get("fmt", st["fmt"])
            st["header_mode"] = tpl.get("header_mode", st["header_mode"])
            st["modules"] = apply_template_to_modules(st["modules"], tpl)
            st["slide"] = "custom"
            await _safe_cb_answer(cb, f"✅ قالب «{tpl['name']}» اعمال شد!")
        else:
            await _safe_cb_answer(cb, "قالب یافت نشد.", show_alert=True)
    elif action == "tpl_del":
        from src.xgpedia.layout_templates import delete_layout_template
        idx = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else -1
        delete_layout_template("transfer_radar", idx)
        await _safe_cb_answer(cb, "🗑 قالب حذف شد.")
    elif action == "tpl_back":
        await _safe_cb_answer(cb)
    elif action == "build":
        await _safe_cb_answer(cb, "در حال ساخت کارت تولد...")
        it = st["item"]
        wait_msg = await cb.message.answer(
            f"⏳ در حال ساخت کارت تولد <b>{html.escape(str(it.get('nameFa') or it.get('nameEn') or ''))}</b> ({st['mode']} | {st['fmt']})...",
            parse_mode="HTML",
        )

        async def _progress(msg_text: str) -> None:
            try:
                await wait_msg.edit_text(
                    f"{msg_text}\n🎂 <b>{html.escape(str(it.get('nameFa') or it.get('nameEn') or ''))}</b>",
                    parse_mode="HTML",
                )
            except TelegramBadRequest:
                pass

        enabled_ids = [m["id"] for m in st["modules"] if m["enabled"]]
        res = await tw.generate_birthday_post_async(
            it,
            mode=st["mode"],
            fmt=st["fmt"],
            rim_light=st.get("rim_light", True),
            enabled_modules=enabled_ids,
            progress_cb=_progress,
        )
        if not res.ok:
            await wait_msg.edit_text(html.escape(res.format_error_fa())[:3800], parse_mode="HTML")
            return
        await _send_post_preview(
            bot,
            cb.from_user.id,
            res,
            wait_msg,
            note=f"✅ کارت تولد آماده شد (پست #{res.post_id} | سبک {st['mode']} | {st['fmt']}).",
        )
        return

    text, markup = _render_birthday_customizer_view(st)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except TelegramBadRequest:
        pass


# ─── پنل و کاستومایزر ماژولار «رادار نقل‌وانتقالات» (Transfer Radar D48 — صفحه‌بندی کامل) ───

_TR_STATE: Any = PersistentStateDict("tr_state", key_type=int)
_TR_ITEM_MAP: dict[str, dict[str, Any]] = {}
_TR_LAST_DATA: dict[str, list[dict[str, Any]]] = {"live": [], "presets": []}
_AWAITING_TEMPLATE_NAME: Any = PersistentStateDict("awaiting_template_name", key_type=int)


def _format_transfer_list_message(
    data: dict[str, list[dict[str, Any]]],
    *,
    page: int = 1,
    page_size: int = 6,
    show_presets: bool = False,
) -> tuple[str, InlineKeyboardMarkup]:
    _TR_LAST_DATA["live"] = list(data.get("live") or [])
    _TR_LAST_DATA["presets"] = list(data.get("presets") or [])
    live_items = _TR_LAST_DATA["live"]
    presets = _TR_LAST_DATA["presets"]
    rows: list[list[InlineKeyboardButton]] = []

    if show_presets or not live_items:
        lines = [
            "📡 <b>رادار نقل‌وانتقالات XGPedia — پریست‌های آماده (حالت ماژولار)</b>",
            "۵ اسلاید آماده + ۲ سبک هدر (کامل/فشرده) + ۱۰ ماژول تحلیلی مستقل",
            "",
        ]
        if not live_items and not show_presets:
            lines.append("ℹ️ شایعهٔ زنده‌ای دریافت نشد؛ پریست‌های آماده در دسترس‌اند:")
            lines.append("")
        for it in presets:
            iid = str(it["id"])
            _TR_ITEM_MAP[iid] = it
            pl = (it.get("player") or {}).get("name", iid)
            to_n = (it.get("to") or {}).get("name", "")
            rows.append([InlineKeyboardButton(
                text=f"⭐ {pl} ← {to_n} ({it.get('prob', 70)}٪)"[:54],
                callback_data=f"tr:open:{iid[:44]}",
            )])
        if live_items:
            rows.append([InlineKeyboardButton(text=f"🔥 شایعات زنده امروز ({len(live_items)})", callback_data="tr:list:1")])
        rows.append([
            InlineKeyboardButton(text="🔄 بروزرسانی شایعات زنده", callback_data="tr:refresh"),
            InlineKeyboardButton(text="🎨 استودیو کارت‌ها", callback_data="nav:cards"),
        ])
        return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)

    total = len(live_items)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = min(total, start + page_size)

    lines = [
        f"📡 <b>رادار نقل‌وانتقالات — شایعات داغ امروز (صفحه {page} از {total_pages} | مجموع {total} شایعه)</b>",
        "منابع رایگان (Soccer): <b>Guardian + BBC Sport + Sky Sports + CaughtOffside + 90min</b>",
        "شایعه را انتخاب کنید تا اطلاعات کامل، عکس بازیکن و تحلیل فارسی استخراج شود:",
    ]
    for idx, it in enumerate(live_items[start:end], start + 1):
        iid = str(it["id"])
        _TR_ITEM_MAP[iid] = it
        hot = int(it.get("hotness") or 60)
        fire = "🔥" if hot >= 75 else "📡"
        src_s = str(it.get("source") or "Live")[:10]
        ttl = str(it.get("headline_en") or it.get("title") or "")[:32]
        rows.append([InlineKeyboardButton(text=f"{idx}. {fire}{hot} [{src_s}] {ttl}"[:56], callback_data=f"tr:open:{iid[:44]}")])

    if total_pages > 1:
        nav_p: list[InlineKeyboardButton] = []
        if page > 1:
            nav_p.append(InlineKeyboardButton(text="⬅️ صفحه قبل", callback_data=f"tr:list:{page - 1}"))
        nav_p.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data=f"tr:list:{page}"))
        if page < total_pages:
            nav_p.append(InlineKeyboardButton(text="➡️ صفحه بعد", callback_data=f"tr:list:{page + 1}"))
        rows.append(nav_p)

    rows.append([
        InlineKeyboardButton(text="⭐ پریست‌های آماده (۴)", callback_data="tr:presets"),
        InlineKeyboardButton(text="🔄 بروزرسانی زنده", callback_data="tr:refresh"),
    ])
    rows.append([InlineKeyboardButton(text="🎨 استودیو کارت‌ها", callback_data="nav:cards")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def _build_transfer_schematic(mods: list[dict[str, Any]]) -> str:
    """پیش‌نمایش متنی ترتیب و عرض ماژول‌های فعال رادار نقل‌وانتقالات."""
    active = [m for m in mods if m.get("enabled")]
    if not active:
        return "[ هیچ ماژولی فعال نیست ]"
    rows: list[str] = []
    i = 0
    while i < len(active):
        m = active[i]
        short = m["title_fa"].split("(")[0].strip()[:18]
        if m.get("span") == "half":
            if i + 1 < len(active) and active[i + 1].get("span") == "half":
                s2 = active[i + 1]["title_fa"].split("(")[0].strip()[:18]
                rows.append(f"[ ½ {short} ] [ ½ {s2} ]")
                i += 2
                continue
            rows.append(f"[ ½ {short} (خودکار تمام‌عرض) ]")
        else:
            rows.append(f"[  ۱  {short}  ]")
        i += 1
    return "\n".join(rows)


def _render_transfer_customizer_view(st: dict[str, Any]) -> tuple[str, InlineKeyboardMarkup]:
    from src.xgpedia.layout_templates import MAX_SAVED_TEMPLATES, list_layout_templates
    from src.xgpedia.render.card_kit.transfer_radar_card import (
        TRANSFER_FORMATS,
        TRANSFER_SLIDES,
        TRANSFER_STATUSES,
    )

    it = st["item"]
    slide = st["slide"]
    hm = st["header_mode"]
    fmt = st["fmt"]
    mods = st["modules"]
    missing = st.get("missing_modules") or []
    mpage = max(1, int(st.get("mod_page", 1)))
    page_size = 5
    total_mods = len(mods)
    total_mpages = max(1, (total_mods + page_size - 1) // page_size)
    mpage = min(mpage, total_mpages)
    st["mod_page"] = mpage
    m_start = (mpage - 1) * page_size
    m_end = min(total_mods, m_start + page_size)

    st_meta = TRANSFER_STATUSES.get(str(it.get("status") or "radar").lower(), TRANSFER_STATUSES["radar"])
    pl_name = str((it.get("player") or {}).get("name") or it.get("title") or "")
    to_name = str((it.get("to") or {}).get("name") or "")
    active_cnt = sum(1 for m in mods if m["enabled"])
    schematic = _build_transfer_schematic(mods)
    tpl_cnt = len(list_layout_templates("transfer_radar"))

    lines = [
        "📡 <b>رادار نقل‌وانتقالات — استودیو ماژولار</b>",
        f"👤 <b>{html.escape(pl_name)}</b>" + (f" ← <b>{html.escape(to_name)}</b>" if to_name else ""),
        f"🚨 وضعیت: <b>{html.escape(st_meta['fa'])} ({it.get('prob', 50)}٪)</b> | 📐 فرمت: <b>{fmt}</b>",
        f"🧩 هدر: <b>{'کامل (رادار+مدالیون)' if hm == 'full' else 'فشرده'}</b> | ماژول فعال: <b>{active_cnt} از {total_mods}</b>",
        "",
        "🗺 <b>چیدمان و ترتیب فعلی کارت:</b>",
        f"<pre>{html.escape(schematic)}</pre>",
    ]
    if missing:
        lines.append("ℹ️ بدون دیتای ثبت‌شده (null≠0): " + html.escape("، ".join(missing[:5])))
    lines.append("نام = روشن/خاموش | ½ یا ۱ = عرض | ⬆️⬇️ = ترتیب:")

    rows: list[list[InlineKeyboardButton]] = []
    # ۱) ۵ پریست اسلاید (۲ ردیف)
    rows.append([
        InlineKeyboardButton(text=("✅ " if sid == slide else "") + f"اسلاید {i}", callback_data=f"trc:sl:{sid}")
        for i, (sid, _, _, _) in enumerate(TRANSFER_SLIDES[:3], 1)
    ])
    rows.append([
        InlineKeyboardButton(text=("✅ " if sid == slide else "") + f"اسلاید {i}", callback_data=f"trc:sl:{sid}")
        for i, (sid, _, _, _) in enumerate(TRANSFER_SLIDES[3:], 4)
    ])
    # ۲) سبک هدر + ۳ فرمت
    rows.append([
        InlineKeyboardButton(text=("✅ " if hm == "full" else "") + "هدر کامل", callback_data="trc:hm:full"),
        InlineKeyboardButton(text=("✅ " if hm == "compact" else "") + "هدر فشرده", callback_data="trc:hm:compact"),
    ])
    rows.append([
        InlineKeyboardButton(text=("✅ " if f == fmt else "") + f, callback_data=f"trc:fmt:{f.replace(':', '_')}")
        for f in TRANSFER_FORMATS
    ])
    # ۳) کنترل‌های دقیق ماژولار (مشابه Pre-Match: روشن/خاموش + عرض ½/۱ + ترتیب ⬆️⬇️، صفحه‌بندی ۵تایی)
    for g_idx in range(m_start, m_end):
        m = mods[g_idx]
        mark = "✅" if m["enabled"] else "⬜"
        sp_badge = "½" if m.get("span") == "half" else "۱"
        rows.append([
            InlineKeyboardButton(
                text=f"{mark} {m['title_fa']}  [{sp_badge}]",
                callback_data=f"trc:tog:{m['id']}",
            )
        ])
        ctrl: list[InlineKeyboardButton] = []
        if m.get("can_half", False):
            w_lbl = "عرض: نیم‌عرض ½ 🔁" if m.get("span") == "half" else "عرض: تمام‌عرض ۱ 🔁"
            ctrl.append(InlineKeyboardButton(text=w_lbl, callback_data=f"trc:sp:{m['id']}"))
        else:
            ctrl.append(InlineKeyboardButton(text="🔒 تمام‌عرض", callback_data="trc:noop"))
        ctrl.append(InlineKeyboardButton(
            text="⬆️ بالا" if g_idx > 0 else "·",
            callback_data=f"trc:up:{m['id']}" if g_idx > 0 else "trc:noop",
        ))
        ctrl.append(InlineKeyboardButton(
            text="⬇️ پایین" if g_idx < total_mods - 1 else "·",
            callback_data=f"trc:dn:{m['id']}" if g_idx < total_mods - 1 else "trc:noop",
        ))
        rows.append(ctrl)

    if total_mpages > 1:
        p_nav: list[InlineKeyboardButton] = []
        if mpage > 1:
            p_nav.append(InlineKeyboardButton(text="⬅️ ماژول‌های قبل", callback_data=f"trc:mp:{mpage - 1}"))
        p_nav.append(InlineKeyboardButton(text=f"🧩 صفحه {mpage}/{total_mpages}", callback_data="trc:noop"))
        if mpage < total_mpages:
            p_nav.append(InlineKeyboardButton(text="➡️ ماژول‌های بعد", callback_data=f"trc:mp:{mpage + 1}"))
        rows.append(p_nav)

    # ۴) ذخیره و بازیابی تا ۵ قالب نام‌گذاری‌شده
    rows.append([
        InlineKeyboardButton(text=f"💾 ذخیره قالب ({tpl_cnt}/{MAX_SAVED_TEMPLATES})", callback_data="trc:tpl_save"),
        InlineKeyboardButton(text=f"📂 قالب‌های من ({tpl_cnt}/{MAX_SAVED_TEMPLATES})", callback_data="trc:tpl_list"),
    ])
    rows.append([InlineKeyboardButton(text="🎨 ساخت کارت و کپشن نهایی", callback_data="trc:build")])
    rows.append([
        InlineKeyboardButton(text="📡 لیست شایعات", callback_data="tr:list:1"),
        InlineKeyboardButton(text="🎨 استودیو کارت‌ها", callback_data="nav:cards"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("transfers"))
async def cmd_transfers(m: Message) -> None:
    if not tp.is_admin(m.from_user.id):
        await m.answer("دسترسی غیرمجاز.")
        return
    from src.xgpedia.providers.transfer_radar_free import list_transfer_items
    status_msg = await m.answer("⏳ در حال رصد داغ‌ترین شایعات نقل‌وانتقالات فوتبال (۵ منبع رایگان)...")
    data = await asyncio.to_thread(list_transfer_items, include_live=True)
    text, kb = _format_transfer_list_message(data, page=1)
    await status_msg.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("tr:list:"))
async def on_tr_list_page(cb: CallbackQuery) -> None:
    from src.xgpedia.providers.transfer_radar_free import list_transfer_items
    try:
        page = int(cb.data.split(":")[2])
    except (IndexError, ValueError):
        page = 1
    if not _TR_LAST_DATA.get("live") and not _TR_LAST_DATA.get("presets"):
        await _safe_cb_answer(cb, "در حال دریافت شایعات زنده...")
        wait_msg = await cb.message.answer("⏳ در حال رصد داغ‌ترین شایعات نقل‌وانتقالات فوتبال (۵ منبع رایگان)...")
        data = await asyncio.to_thread(list_transfer_items, include_live=True)
        text, kb = _format_transfer_list_message(data, page=page)
        await wait_msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
        return
    await _safe_cb_answer(cb)
    text, kb = _format_transfer_list_message(_TR_LAST_DATA, page=page)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except TelegramBadRequest:
        await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "tr:refresh")
async def on_tr_refresh(cb: CallbackQuery) -> None:
    from src.xgpedia.providers.transfer_radar_free import list_transfer_items
    await _safe_cb_answer(cb, "در حال بروزرسانی شایعات زنده...")
    wait_msg = await cb.message.answer("⏳ در حال دریافت زندهٔ شایعات نقل‌وانتقالات از ۵ فید فوتبال...")
    data = await asyncio.to_thread(list_transfer_items, include_live=True, force_refresh=True)
    text, kb = _format_transfer_list_message(data, page=1)
    await wait_msg.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "tr:presets")
async def on_tr_presets(cb: CallbackQuery) -> None:
    from src.xgpedia.providers.transfer_radar_free import load_transfer_presets
    await _safe_cb_answer(cb)
    if not _TR_LAST_DATA.get("presets"):
        _TR_LAST_DATA["presets"] = load_transfer_presets()
    text, kb = _format_transfer_list_message(_TR_LAST_DATA, show_presets=True)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except TelegramBadRequest:
        await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("tr:open:"))
async def on_tr_open(cb: CallbackQuery) -> None:
    from src.xgpedia.render.card_kit.transfer_radar_card import (
        TRANSFER_DEFAULT_HEADER,
        TRANSFER_DEFAULT_SLIDE,
        get_transfer_modules,
    )
    iid = cb.data.split(":", 2)[2]
    it = _TR_ITEM_MAP.get(iid)
    if not it:
        await _safe_cb_answer(cb, "شایعه در کش نیست؛ لطفاً لیست را بروزرسانی کنید.", show_alert=True)
        return
    await _safe_cb_answer(cb, "کاستومایزر ماژولار باز شد.")
    # اگر شایعه زنده است، verdict در مرحله ساخت با LLM تکمیل می‌شود پس آن را قابل انتخاب نشان می‌دهیم
    preview_it = dict(it)
    if not preview_it.get("verdict"):
        preview_it["verdict"] = {"title": "تحلیل تحریریه", "body": "(در مرحله ساخت نهایی تکمیل می‌شود)", "tag": "XGPedia"}
    mods, missing = get_transfer_modules(preview_it, TRANSFER_DEFAULT_SLIDE)
    st = {
        "item": it,
        "slide": TRANSFER_DEFAULT_SLIDE,
        "header_mode": TRANSFER_DEFAULT_HEADER,
        "fmt": "4:5",
        "modules": mods,
        "missing_modules": missing,
    }
    _TR_STATE[cb.from_user.id] = st
    text, markup = _render_transfer_customizer_view(st)
    await cb.message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "tr:back")
async def on_tr_back(cb: CallbackQuery) -> None:
    st = _TR_STATE.get(cb.from_user.id)
    if not st:
        await _safe_cb_answer(cb, "لطفاً دوباره شایعه را انتخاب کنید.", show_alert=True)
        return
    await _safe_cb_answer(cb)
    text, markup = _render_transfer_customizer_view(st)
    await cb.message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("trc:"))
async def on_tr_customizer_action(cb: CallbackQuery, bot: Bot) -> None:
    st = _TR_STATE.get(cb.from_user.id)
    if not st:
        await _safe_cb_answer(cb, "لطفاً دوباره شایعه را انتخاب کنید.", show_alert=True)
        return
    from src.xgpedia.render.card_kit.transfer_radar_card import TRANSFER_SLIDES, get_transfer_modules

    parts = cb.data.split(":")
    action = parts[1]

    if action == "sl":
        sid = parts[2]
        st["slide"] = sid
        sl_info = next((x for x in TRANSFER_SLIDES if x[0] == sid), None)
        if sl_info:
            st["header_mode"] = sl_info[2]
            preview_it = dict(st["item"])
            if not preview_it.get("verdict"):
                preview_it["verdict"] = {"title": "تحلیل", "body": "x", "tag": "x"}
            st["modules"], st["missing_modules"] = get_transfer_modules(preview_it, sid)
        await _safe_cb_answer(cb, f"اسلاید روی {sid} تنظیم شد.")
    elif action == "hm":
        st["header_mode"] = parts[2] if parts[2] in ("full", "compact") else "full"
        await _safe_cb_answer(cb, "سبک هدر تغییر کرد.")
    elif action == "fmt":
        st["fmt"] = parts[2].replace("_", ":")
        await _safe_cb_answer(cb, f"فرمت روی {st['fmt']} تنظیم شد.")
    elif action == "tog":
        mid = parts[2]
        target = next((m for m in st["modules"] if m["id"] == mid), None)
        if target:
            target["enabled"] = not target["enabled"]
            await _safe_cb_answer(cb, f"{target['title_fa']}: {'فعال' if target['enabled'] else 'غیرفعال'}")
    elif action == "build":
        await _safe_cb_answer(cb, "در حال ساخت کارت رادار نقل‌وانتقالات...")
        it = st["item"]
        lbl = str((it.get("player") or {}).get("name") or it.get("title") or "")[:65]
        wait_msg = await cb.message.answer(
            f"⏳ در حال ساخت کارت رادار نقل‌وانتقالات <b>{html.escape(lbl)}</b> ({st['slide']} | {st['fmt']})...",
            parse_mode="HTML",
        )

        async def _progress(msg_text: str) -> None:
            try:
                await wait_msg.edit_text(f"{msg_text}\n📡 <b>{html.escape(lbl)}</b>", parse_mode="HTML")
            except TelegramBadRequest:
                pass

        enabled_ids = [m["id"] for m in st["modules"] if m["enabled"]]
        res = await tw.generate_transfer_post_async(
            it,
            slide=st["slide"],
            header_mode=st["header_mode"],
            fmt=st["fmt"],
            enabled_modules=enabled_ids,
            custom_modules=st["modules"],
            progress_cb=_progress,
        )
        if not res.ok:
            await wait_msg.edit_text(html.escape(res.format_error_fa())[:3800], parse_mode="HTML")
            return
        await _send_post_preview(
            bot,
            cb.from_user.id,
            res,
            wait_msg,
            note=f"✅ کارت رادار نقل‌وانتقالات آماده شد (پست #{res.post_id} | {st['slide']} | {st['fmt']}).",
        )
        return

    text, markup = _render_transfer_customizer_view(st)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except TelegramBadRequest:
        pass


# ─── پنل و کاستومایزر اسلایدی «این یا اون؟» (This or That Showreel — D49) ───

_TOT_STATE: Any = PersistentStateDict("tot_state", key_type=int)
_TOT_ITEM_MAP: dict[str, dict[str, Any]] = {}
_TOT_LAST_LIST: list[dict[str, Any]] = []


def _format_tot_list_message(items: list[dict[str, Any]], *, page: int = 1, page_size: int = 6) -> tuple[str, InlineKeyboardMarkup]:
    _TOT_LAST_LIST.clear()
    _TOT_LAST_LIST.extend(items)
    total = len(items)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = min(total, start + page_size)

    lines = [
        f"⚔️ <b>استودیو «این یا اون؟» — پیشنهادهای داغ و جدال‌انگیز (صفحه {page} از {total_pages})</b>",
        "حالت: <b>اسلایدی</b> (۴ سبک: برش مورب · دوئل مجله‌ای · کارت کلکسیونی · چالش ۵تایی × ۳ فرمت)",
        "یکی از دوئل‌های حساس زیر را انتخاب کن یا با AI پیشنهاد تازه بساز:",
    ]
    rows: list[list[InlineKeyboardButton]] = []
    for idx, it in enumerate(items[start:end], start + 1):
        iid = str(it["id"])
        _TOT_ITEM_MAP[iid] = it
        lbl = f"{idx}. ⚔️ {it.get('label', iid)} — {it.get('sub', '')}"[:56]
        rows.append([InlineKeyboardButton(text=lbl, callback_data=f"tot:open:{iid[:44]}")])

    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 1:
            nav.append(InlineKeyboardButton(text="⬅️ صفحه قبل", callback_data=f"tot:list:{page - 1}"))
        nav.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data=f"tot:list:{page}"))
        if page < total_pages:
            nav.append(InlineKeyboardButton(text="➡️ صفحه بعد", callback_data=f"tot:list:{page + 1}"))
        rows.append(nav)

    rows.append([
        InlineKeyboardButton(text="⚡ پیشنهاد جدالی تازه با AI", callback_data="tot:ai_new"),
        InlineKeyboardButton(text="🎨 استودیو کارت‌ها", callback_data="nav:cards"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def _render_tot_customizer_view(st: dict[str, Any]) -> tuple[str, InlineKeyboardMarkup]:
    from src.xgpedia.render.card_kit.this_or_that_card import TOT_FORMATS, TOT_LAYOUTS

    it = st["item"]
    ly = st["layout"]
    fmt = st["fmt"]
    pick = st.get("pick", "none")
    mods = st["modules"]
    ly_lbl = next((lbl for lid, lbl, _ in TOT_LAYOUTS if lid == ly), ly)
    active_cnt = sum(1 for m in mods if m["enabled"])

    lines = [
        "⚔️ <b>استودیو «این یا اون؟» — تنظیمات اسلاید</b>",
        f"🔥 <b>{html.escape(str(it.get('label') or ''))}</b>",
        f"❓ {html.escape(str(it.get('question') or '')[:95])}",
        f"🖼 سبک: <b>{html.escape(ly_lbl)}</b> | 📐 فرمت: <b>{fmt}</b> | 🏅 انتخاب: <b>{pick.upper()}</b>",
        f"🧩 ماژول‌های فعال: <b>{active_cnt} از {len(mods)}</b>",
    ]
    rows: list[list[InlineKeyboardButton]] = []
    # ۱) ۴ موتور گرافیکی (۲ ردیف)
    rows.append([
        InlineKeyboardButton(text=("✅ " if lid == ly else "") + llbl.split("(")[0].strip(), callback_data=f"totc:ly:{lid}")
        for lid, llbl, _ in TOT_LAYOUTS[:2]
    ])
    rows.append([
        InlineKeyboardButton(text=("✅ " if lid == ly else "") + llbl.split("(")[0].strip(), callback_data=f"totc:ly:{lid}")
        for lid, llbl, _ in TOT_LAYOUTS[2:]
    ])
    # ۲) ۳ فرمت
    rows.append([
        InlineKeyboardButton(text=("✅ " if f == fmt else "") + f, callback_data=f"totc:fmt:{f.replace(':', '_')}")
        for f in TOT_FORMATS
    ])
    # ۳) انتخاب برنده + جابجایی A و B
    rows.append([
        InlineKeyboardButton(text=("✅ " if pick == "none" else "") + "بدون انتخاب", callback_data="totc:pk:none"),
        InlineKeyboardButton(text=("✅ " if pick == "a" else "") + "برنده A", callback_data="totc:pk:a"),
        InlineKeyboardButton(text=("✅ " if pick == "b" else "") + "برنده B", callback_data="totc:pk:b"),
        InlineKeyboardButton(text="⇄ جابجایی", callback_data="totc:swap"),
    ])
    # ۴) ماژول‌های داخلی
    for i in range(0, len(mods), 2):
        r_m = []
        for m in mods[i : i + 2]:
            icon = "✅" if m["enabled"] else "⬜"
            r_m.append(InlineKeyboardButton(text=f"{icon} {m['title_fa'].split('(')[0].strip()[:22]}", callback_data=f"totc:tog:{m['id']}"))
        rows.append(r_m)

    rows.append([InlineKeyboardButton(text="🎨 ساخت کارت و کپشن نهایی", callback_data="totc:build")])
    rows.append([
        InlineKeyboardButton(text="⚔️ لیست پیشنهادها", callback_data="tot:list:1"),
        InlineKeyboardButton(text="🎨 استودیو کارت‌ها", callback_data="nav:cards"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("thisorthat"))
async def cmd_thisorthat(m: Message) -> None:
    if not tp.is_admin(m.from_user.id):
        await m.answer("دسترسی غیرمجاز.")
        return
    from src.xgpedia.providers.this_or_that_free import list_this_or_that_suggestions
    items = await asyncio.to_thread(list_this_or_that_suggestions, include_live_matches=True)
    text, kb = _format_tot_list_message(items, page=1)
    await m.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("tot:list:"))
async def on_tot_list_page(cb: CallbackQuery) -> None:
    from src.xgpedia.providers.this_or_that_free import list_this_or_that_suggestions
    try:
        page = int(cb.data.split(":")[2])
    except (IndexError, ValueError):
        page = 1
    await _safe_cb_answer(cb)
    items = _TOT_LAST_LIST if _TOT_LAST_LIST else await asyncio.to_thread(list_this_or_that_suggestions, include_live_matches=True)
    text, kb = _format_tot_list_message(list(items), page=page)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except TelegramBadRequest:
        await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "tot:ai_new")
async def on_tot_ai_new(cb: CallbackQuery) -> None:
    import threading
    from src.xgpedia.providers.this_or_that_free import generate_ai_debate_proposal
    from src.xgpedia.render.card_kit.this_or_that_card import TOT_DEFAULT_LAYOUT, get_tot_modules

    await _safe_cb_answer(cb, "در حال طراحی دوئل جدالی جدید با AI...")
    wait_m = await cb.message.answer("⏳ در حال خلق یک پیشنهاد جدال‌انگیز و جذاب «این یا اون؟» با هوش مصنوعی...")
    ev = threading.Event()
    try:
        item = await asyncio.wait_for(asyncio.to_thread(generate_ai_debate_proposal, cancel_event=ev), timeout=90.0)
    except Exception as e:
        ev.set()
        await wait_m.edit_text(f"❌ خطا در تولید پیشنهاد AI:\n{html.escape(type(e).__name__)}: {html.escape(str(e)[:250])}", parse_mode="HTML")
        return
    finally:
        ev.set()

    _TOT_ITEM_MAP[item["id"]] = item
    st = {
        "item": item,
        "layout": str(item.get("layout") or TOT_DEFAULT_LAYOUT),
        "fmt": "4:5",
        "pick": "none",
        "modules": get_tot_modules(item),
    }
    _TOT_STATE[cb.from_user.id] = st
    text, markup = _render_tot_customizer_view(st)
    await wait_m.edit_text(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("tot:open:"))
async def on_tot_open(cb: CallbackQuery) -> None:
    from src.xgpedia.render.card_kit.this_or_that_card import TOT_DEFAULT_LAYOUT, get_tot_modules

    iid = cb.data.split(":", 2)[2]
    it = _TOT_ITEM_MAP.get(iid)
    if not it:
        await _safe_cb_answer(cb, "پیشنهاد یافت نشد؛ لطفاً لیست را دوباره باز کنید.", show_alert=True)
        return
    await _safe_cb_answer(cb)
    st = {
        "item": json.loads(json.dumps(it, ensure_ascii=False)),
        "layout": str(it.get("layout") or TOT_DEFAULT_LAYOUT),
        "fmt": "4:5",
        "pick": "none",
        "modules": get_tot_modules(it),
    }
    _TOT_STATE[cb.from_user.id] = st
    text, markup = _render_tot_customizer_view(st)
    await cb.message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "tot:back")
async def on_tot_back(cb: CallbackQuery) -> None:
    st = _TOT_STATE.get(cb.from_user.id)
    if not st:
        await _safe_cb_answer(cb, "لطفاً دوباره یک دوئل انتخاب کنید.", show_alert=True)
        return
    await _safe_cb_answer(cb)
    text, markup = _render_tot_customizer_view(st)
    await cb.message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("totc:"))
async def on_tot_customizer_action(cb: CallbackQuery, bot: Bot) -> None:
    st = _TOT_STATE.get(cb.from_user.id)
    if not st:
        await _safe_cb_answer(cb, "لطفاً دوباره یک دوئل انتخاب کنید.", show_alert=True)
        return
    parts = cb.data.split(":")
    action = parts[1]

    if action == "ly":
        st["layout"] = parts[2] if parts[2] in ("diagonal", "split", "cards", "rapid") else "diagonal"
        await _safe_cb_answer(cb, f"سبک روی {st['layout']} تنظیم شد.")
    elif action == "fmt":
        st["fmt"] = parts[2].replace("_", ":")
        await _safe_cb_answer(cb, f"فرمت روی {st['fmt']} تنظیم شد.")
    elif action == "pk":
        st["pick"] = parts[2] if parts[2] in ("none", "a", "b") else "none"
        await _safe_cb_answer(cb, f"انتخاب: {st['pick'].upper()}")
    elif action == "swap":
        it = st["item"]
        it["a"], it["b"] = it.get("b"), it.get("a")
        it["pollA"] = 100 - int(it.get("pollA") or 50)
        for r in it.get("stats") or []:
            r["a"], r["b"] = r.get("b"), r.get("a")
        st["pick"] = "b" if st["pick"] == "a" else ("a" if st["pick"] == "b" else "none")
        await _safe_cb_answer(cb, "⇄ طرف A و B جابجا شدند.")
    elif action == "tog":
        mid = parts[2]
        target = next((m for m in st["modules"] if m["id"] == mid), None)
        if target:
            target["enabled"] = not target["enabled"]
            await _safe_cb_answer(cb, f"{target['title_fa']}: {'فعال' if target['enabled'] else 'غیرفعال'}")
    elif action == "build":
        await _safe_cb_answer(cb, "در حال ساخت کارت این یا اون...")
        it = st["item"]
        wait_msg = await cb.message.answer(
            f"⏳ در حال ساخت کارت <b>{html.escape(str(it.get('label') or ''))}</b> ({st['layout']} | {st['fmt']})...",
            parse_mode="HTML",
        )

        async def _progress(msg_text: str) -> None:
            try:
                await wait_msg.edit_text(f"{msg_text}\n⚔️ <b>{html.escape(str(it.get('label') or ''))}</b>", parse_mode="HTML")
            except TelegramBadRequest:
                pass

        enabled_ids = [m["id"] for m in st["modules"] if m["enabled"]]
        res = await tw.generate_this_or_that_post_async(
            it,
            layout=st["layout"],
            fmt=st["fmt"],
            pick=st.get("pick", "none"),
            enabled_modules=enabled_ids,
            progress_cb=_progress,
        )
        if not res.ok:
            await wait_msg.edit_text(html.escape(res.format_error_fa())[:3800], parse_mode="HTML")
            return
        await _send_post_preview(
            bot,
            cb.from_user.id,
            res,
            wait_msg,
            note=f"✅ کارت «این یا اون؟» آماده شد (پست #{res.post_id} | {st['layout']} | {st['fmt']}).",
        )
        return

    text, markup = _render_tot_customizer_view(st)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except TelegramBadRequest:
        pass
