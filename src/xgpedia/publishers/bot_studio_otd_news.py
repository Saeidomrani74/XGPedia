"""هندلرها و نماهای استودیویی «در چنین روزی» و «خبر فوری» (استخراج‌شده از telegram_bot.py در v0.73.0)."""
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


# ─── پنل و کاستومایزر اسلایدی «در چنین روزی» (On This Day — Showreel V2) ───

_OTD_STATE: Any = PersistentStateDict("otd_state", key_type=int)
_OTD_EVENT_MAP: dict[str, dict[str, Any]] = {}


def _format_otd_list_message(data: dict[str, list[dict[str, Any]]]) -> tuple[str, InlineKeyboardMarkup]:
    today_evs = data.get("today") or []
    archive_evs = data.get("archive") or []
    lines = [
        "🕰 <b>استودیو «در چنین روزی» (Showreel V2)</b>",
        "حالت: <b>اسلایدی</b> (۴ پوستر مستقل × ۳ تم × ۳ فرمت + انتخاب ماژول‌های داخلی)",
        "",
    ]
    rows: list[list[InlineKeyboardButton]] = []
    if today_evs:
        lines.append(f"🌍 <b>رویدادهای زندهٔ فوتبال امروز ({len(today_evs)} مورد از ویکی‌پدیا/آرشیو):</b>")
        for ev in today_evs[:6]:
            ev_id = str(ev["id"])
            _OTD_EVENT_MAP[ev_id] = ev
            lbl = f"🌍 {ev.get('year', '')} — {str(ev.get('title') or ev.get('shortLabel', ''))[:34]}"
            rows.append([InlineKeyboardButton(text=lbl, callback_data=f"otd:open:{ev_id[:44]}")])
        lines.append("")
    else:
        lines.append("ℹ️ امروز رویداد فوتبالی مستقیمی در فید ویکی‌پدیا ثبت نشده یا اتصال برقرار نبود؛ آرشیو ماندگار زیر همیشه آماده است:")
        lines.append("")

    lines.append(f"🏆 <b>آرشیو مستند شوریل ({len(archive_evs)} لحظه کامل با ۴ پوستر):</b>")
    for ev in archive_evs:
        ev_id = str(ev["id"])
        _OTD_EVENT_MAP[ev_id] = ev
        home = ev.get("home") or {}
        away = ev.get("away") or {}
        score_s = f" ({home.get('score')}-{away.get('score')})" if home and away else ""
        lbl = f"🏆 {ev.get('shortLabel') or ev.get('title')}{score_s}"
        rows.append([InlineKeyboardButton(text=lbl[:52], callback_data=f"otd:open:{ev_id[:44]}")])

    rows.append([
        InlineKeyboardButton(text="🔄 بروزرسانی زنده", callback_data="otd:refresh"),
        InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="nav:home"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def _render_otd_customizer_view(st: dict[str, Any]) -> tuple[str, InlineKeyboardMarkup]:
    from src.xgpedia.render.card_kit.on_this_day_card import (
        OTD_BG_MODES,
        OTD_SLIDES,
        OTD_THEMES,
        get_otd_slide_availability,
    )

    ev = st["event"]
    slide = st["slide"]
    theme = st["theme"]
    fmt = st["fmt"]
    bg_mode = st["bg_mode"]
    mods = st["modules"]
    missing = st.get("missing_modules") or []
    slide_avail = get_otd_slide_availability(ev)

    slide_lbl = next((lbl for sid, lbl, _ in OTD_SLIDES if sid == slide), slide)
    theme_lbl = OTD_THEMES.get(theme, OTD_THEMES["core"])["label_fa"]
    bg_lbl = next((lbl for bid, lbl in OTD_BG_MODES if bid == bg_mode), bg_mode)
    active_cnt = sum(1 for m in mods if m["enabled"])

    lines = [
        "🕰 <b>استودیو «در چنین روزی» — تنظیمات اسلاید</b>",
        f"📌 <b>{html.escape(str(ev.get('title') or ''))}</b> ({ev.get('year', '')})",
        f"📅 {html.escape(str(ev.get('dateFa') or ''))} | {html.escape(str(ev.get('competition') or ''))}",
        f"🖼 پوستر: <b>{html.escape(slide_lbl)}</b>",
        f"🎨 تم: <b>{html.escape(theme_lbl)}</b> | 📐 فرمت: <b>{fmt}</b> | 🌌 پس‌زمینه: <b>{html.escape(bg_lbl)}</b>",
        f"🧩 ماژول‌های فعال این اسلاید: <b>{active_cnt} از {len(mods)}</b>",
    ]
    if missing:
        lines.append("ℹ️ ماژول‌های بدون دیتا در این رویداد (null≠0): " + html.escape("، ".join(missing)))

    rows: list[list[InlineKeyboardButton]] = []
    s_row1: list[InlineKeyboardButton] = []
    s_row2: list[InlineKeyboardButton] = []
    for idx, (sid, slbl, _stag) in enumerate(OTD_SLIDES):
        ok = slide_avail.get(sid, True)
        mark = "✅ " if sid == slide else ("🔒 " if not ok else "")
        short_name = slbl.split(":", 1)[-1].strip()[:18]
        btn = InlineKeyboardButton(text=f"{mark}{short_name}", callback_data=f"otdc:sl:{sid}")
        (s_row1 if idx < 2 else s_row2).append(btn)
    rows.append(s_row1)
    rows.append(s_row2)

    rows.append([
        InlineKeyboardButton(
            text=("✅ " if tid == theme else "") + tcfg["label_fa"],
            callback_data=f"otdc:th:{tid}",
        )
        for tid, tcfg in OTD_THEMES.items()
    ])
    rows.append([
        InlineKeyboardButton(
            text=("✅ " if f == fmt else "") + f,
            callback_data=f"otdc:fmt:{f.replace(':', '_')}",
        )
        for f in ("4:5", "9:16", "16:9")
    ])
    rows.append([
        InlineKeyboardButton(
            text=("✅ " if bid == bg_mode else "") + blbl,
            callback_data=f"otdc:bg:{bid}",
        )
        for bid, blbl in OTD_BG_MODES
    ])
    for m in mods:
        icon = "✅" if m["enabled"] else "⬜"
        rows.append([
            InlineKeyboardButton(
                text=f"{icon} {m['title_fa']}",
                callback_data=f"otdc:tog:{m['id']}",
            )
        ])
    rows.append([InlineKeyboardButton(text="🎨 ساخت کارت و کپشن نهایی", callback_data="otdc:build")])
    rows.append([
        InlineKeyboardButton(text="🕰 لیست رویدادها", callback_data="otd:list"),
        InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="nav:home"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("onthisday"))
async def cmd_onthisday(m: Message) -> None:
    if not tp.is_admin(m.from_user.id):
        await m.answer("دسترسی غیرمجاز.")
        return
    from src.xgpedia.providers.on_this_day_free import list_on_this_day_events
    status_msg = await m.answer("⏳ در حال دریافت زندهٔ رویدادهای تاریخی فوتبال امروز (ویکی‌پدیا + آرشیو)...")
    data = await asyncio.to_thread(list_on_this_day_events, include_live=True)
    text, kb = _format_otd_list_message(data)
    await status_msg.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.in_({"otd:list", "otd:refresh"}))
async def on_otd_list(cb: CallbackQuery) -> None:
    from src.xgpedia.providers.on_this_day_free import list_on_this_day_events
    force = cb.data == "otd:refresh"
    await _safe_cb_answer(cb, "در حال دریافت رویدادهای در چنین روزی...")
    wait_msg = await cb.message.answer("⏳ در حال بارگذاری رویدادهای زندهٔ ویکی‌پدیا و آرشیو شوریل...")
    data = await asyncio.to_thread(list_on_this_day_events, include_live=True, force_refresh=force)
    text, kb = _format_otd_list_message(data)
    await wait_msg.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("otd:open:"))
async def on_otd_open(cb: CallbackQuery) -> None:
    from src.xgpedia.providers.on_this_day_free import get_on_this_day_event
    from src.xgpedia.render.card_kit.on_this_day_card import get_otd_slide_modules

    ev_id = cb.data.split(":", 2)[2]
    ev = _OTD_EVENT_MAP.get(ev_id) or await asyncio.to_thread(get_on_this_day_event, ev_id)
    if not ev:
        await _safe_cb_answer(cb, "رویداد یافت نشد؛ لطفاً لیست را بروزرسانی کنید.", show_alert=True)
        return
    await _safe_cb_answer(cb, "استودیو اسلاید باز شد.")
    mods, missing = get_otd_slide_modules(ev, "cover")
    st = {
        "event": ev,
        "slide": "cover",
        "theme": "core",
        "fmt": "4:5",
        "bg_mode": str(ev.get("defaultBg") or "stadium"),
        "modules": mods,
        "missing_modules": missing,
    }
    _OTD_STATE[cb.from_user.id] = st
    text, markup = _render_otd_customizer_view(st)
    await cb.message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "otd:back")
async def on_otd_back(cb: CallbackQuery) -> None:
    st = _OTD_STATE.get(cb.from_user.id)
    if not st:
        await _safe_cb_answer(cb, "لطفاً دوباره رویداد را از لیست انتخاب کنید.", show_alert=True)
        return
    await _safe_cb_answer(cb, "بازگشت به استودیو اسلاید")
    text, markup = _render_otd_customizer_view(st)
    await cb.message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("otdc:"))
async def on_otd_customizer_action(cb: CallbackQuery, bot: Bot) -> None:
    st = _OTD_STATE.get(cb.from_user.id)
    if not st:
        await _safe_cb_answer(cb, "لطفاً دوباره رویداد را از لیست انتخاب کنید.", show_alert=True)
        return

    from src.xgpedia.render.card_kit.on_this_day_card import (
        get_otd_slide_availability,
        get_otd_slide_modules,
    )

    parts = cb.data.split(":")
    action = parts[1]

    if action == "sl":
        sid = parts[2]
        avail = get_otd_slide_availability(st["event"])
        if not avail.get(sid, False):
            await _safe_cb_answer(
                cb,
                "این رویداد دیتای تله‌متری/مختصات زمین ندارد (قانون null≠0). پوسترهای دیگر قابل استفاده‌اند.",
                show_alert=True,
            )
            return
        st["slide"] = sid
        mods, missing = get_otd_slide_modules(st["event"], sid)
        st["modules"] = mods
        st["missing_modules"] = missing
        await _safe_cb_answer(cb, f"پوستر روی {sid} تنظیم شد.")
    elif action == "th":
        st["theme"] = parts[2]
        await _safe_cb_answer(cb, f"تم روی {st['theme']} تنظیم شد.")
    elif action == "fmt":
        st["fmt"] = parts[2].replace("_", ":")
        await _safe_cb_answer(cb, f"فرمت روی {st['fmt']} تنظیم شد.")
    elif action == "bg":
        st["bg_mode"] = parts[2]
        await _safe_cb_answer(cb, f"پس‌زمینه روی {st['bg_mode']} تنظیم شد.")
    elif action == "tog":
        mid = parts[2]
        target = next((m for m in st["modules"] if m["id"] == mid), None)
        if target:
            active_cnt = sum(1 for m in st["modules"] if m["enabled"])
            if target["enabled"] and active_cnt <= 1:
                await _safe_cb_answer(cb, "حداقل یک ماژول در اسلاید باید فعال بماند.", show_alert=True)
                return
            target["enabled"] = not target["enabled"]
            await _safe_cb_answer(cb, f"{target['title_fa']}: {'فعال' if target['enabled'] else 'غیرفعال'}")
    elif action == "build":
        await _safe_cb_answer(cb, "در حال ساخت پوستر «در چنین روزی»...")
        ev = st["event"]
        wait_msg = await cb.message.answer(
            f"⏳ در حال ساخت پوستر <b>{html.escape(str(ev.get('title') or ''))}</b> ({st['slide']} | {st['fmt']})...",
            parse_mode="HTML",
        )

        async def _progress(msg_text: str) -> None:
            try:
                await wait_msg.edit_text(
                    f"{msg_text}\n🕰 <b>{html.escape(str(ev.get('title') or ''))}</b>",
                    parse_mode="HTML",
                )
            except TelegramBadRequest:
                pass

        enabled_ids = [m["id"] for m in st["modules"] if m["enabled"]]
        res = await tw.generate_on_this_day_post_async(
            ev,
            slide=st["slide"],
            theme=st["theme"],
            fmt=st["fmt"],
            bg_mode=st["bg_mode"],
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
            note=f"✅ پوستر «در چنین روزی» ساخته شد (پست #{res.post_id} | اسلاید {st['slide']} | تم {st['theme']} | {st['fmt']}).",
        )
        return

    text, markup = _render_otd_customizer_view(st)
    for _attempt in range(3):
        try:
            await cb.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
            break
        except TelegramBadRequest:
            break
        except Exception as e:
            if _attempt == 2:
                log.warning("otd customizer edit_text failed: %s", e)
            else:
                await asyncio.sleep(1.0)



# ─── پنل و کاستومایزر اسلایدی «خبر فوری و رسمی» (PRO WIRE v2) ───

_NEWS_STATE: Any = PersistentStateDict("news_state", key_type=int)
_NEWS_ITEM_MAP: dict[str, dict[str, Any]] = {}


_NEWS_LAST_DATA: dict[str, list[dict[str, Any]]] = {"live": [], "presets": []}


def _format_news_list_message(data: dict[str, list[dict[str, Any]]], *, page: int = 1, page_size: int = 6) -> tuple[str, InlineKeyboardMarkup]:
    _NEWS_LAST_DATA["live"] = list(data.get("live") or [])
    _NEWS_LAST_DATA["presets"] = list(data.get("presets") or [])
    live_items = _NEWS_LAST_DATA["live"]
    presets = _NEWS_LAST_DATA["presets"]
    total_live = len(live_items)
    total_pages = max(1, (total_live + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = min(total_live, start + page_size)

    lines = [
        f"📰 <b>استودیو «خبر فوری و رسمی» (PRO WIRE v2 — صفحه {page} از {total_pages})</b>",
        "حالت: <b>اسلایدی</b> (۴ پوستر مستقل × ۵ مود خبری × ۴ فرمت + انتخاب ماژول‌های داخلی)",
        "",
    ]
    rows: list[list[InlineKeyboardButton]] = []
    if live_items:
        lines.append(f"🌍 <b>اخبار زندهٔ فوتبال (ESPN + BBC Sport + Guardian — {total_live} خبر):</b>")
        for it in live_items[start:end]:
            iid = str(it["id"])
            _NEWS_ITEM_MAP[iid] = it
            lbl = f"🌍 [{it.get('source', 'Live')[:10]}] {str(it.get('title') or '')[:34]}"
            rows.append([InlineKeyboardButton(text=lbl, callback_data=f"news:open:{iid[:44]}")])
        if total_pages > 1:
            nav_r: list[InlineKeyboardButton] = []
            if page > 1:
                nav_r.append(InlineKeyboardButton(text="⬅️ اخبار قبل", callback_data=f"news:page:{page - 1}"))
            nav_r.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data=f"news:page:{page}"))
            if page < total_pages:
                nav_r.append(InlineKeyboardButton(text="➡️ اخبار بعد", callback_data=f"news:page:{page + 1}"))
            rows.append(nav_r)
        lines.append("")
    else:
        lines.append("ℹ️ خبر زنده‌ای دریافت نشد؛ پریست‌های استودیویی زیر همیشه آماده هستند:")
        lines.append("")

    lines.append(f"⚡ <b>پریست‌های آماده استودیو ({len(presets)} قالب کامل):</b>")
    for it in presets:
        iid = str(it["id"])
        _NEWS_ITEM_MAP[iid] = it
        lbl = f"⚡ {str(it.get('title') or iid)[:48]}"
        rows.append([InlineKeyboardButton(text=lbl, callback_data=f"news:open:{iid[:44]}")])

    rows.append([
        InlineKeyboardButton(text="🔄 بروزرسانی اخبار زنده", callback_data="news:refresh"),
        InlineKeyboardButton(text="🎨 استودیو کارت‌ها", callback_data="nav:cards"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def _render_news_customizer_view(st: dict[str, Any]) -> tuple[str, InlineKeyboardMarkup]:
    from src.xgpedia.render.card_kit.news_card import (
        NEWS_FORMATS,
        NEWS_LAYOUTS,
        NEWS_DEFAULT_TINT,
        NEWS_MODES,
        NEWS_MOODS,
        NEWS_TINT_MODES,
        get_news_layout_availability,
    )

    it = st["item"]
    layout = st["layout"]
    mode = st["mode"]
    fmt = st["fmt"]
    mood = st["mood"]
    tint = st.get("tint", NEWS_DEFAULT_TINT)
    mods = st["modules"]
    missing = st.get("missing_modules") or []
    avail = get_news_layout_availability(it)

    ly_lbl = next((lbl for lid, lbl, _ in NEWS_LAYOUTS if lid == layout), layout)
    m_lbl = NEWS_MODES.get(mode, NEWS_MODES["breaking"])["fa"]
    md_lbl = next((lbl for mid, lbl in NEWS_MOODS if mid == mood), mood)
    tint_lbl = next((lbl for tid, lbl in NEWS_TINT_MODES if tid == tint), tint)
    active_cnt = sum(1 for m in mods if m["enabled"])

    lines = [
        "📰 <b>استودیو «خبر فوری و رسمی» — تنظیمات اسلاید</b>",
        f"📌 <b>{html.escape(str(it.get('title') or it.get('headline', ''))[:85])}</b>",
        f"🖼 پوستر: <b>{html.escape(ly_lbl)}</b>",
        f"🚨 مود: <b>{html.escape(m_lbl)}</b> | 📐 فرمت: <b>{fmt}</b>",
        f"🎞 رنگ‌پردازی: <b>{html.escape(md_lbl)}</b> | 🎨 فیلتر تصویر: <b>{html.escape(tint_lbl)}</b>",
        f"🧩 ماژول‌های فعال: <b>{active_cnt} از {len(mods)}</b>",
    ]
    if missing:
        lines.append("ℹ️ ماژول‌های بدون دیتا (null≠0): " + html.escape("، ".join(missing)))

    rows: list[list[InlineKeyboardButton]] = []
    # ۱) ۴ پوستر مستقل
    r1, r2 = [], []
    for idx, (lid, llbl, _en) in enumerate(NEWS_LAYOUTS):
        ok = avail.get(lid, True)
        mark = "✅ " if lid == layout else ("🔒 " if not ok else "")
        short_n = llbl.split(":", 1)[-1].strip()[:18]
        (r1 if idx < 2 else r2).append(InlineKeyboardButton(text=f"{mark}{short_n}", callback_data=f"newsc:ly:{lid}"))
    rows.extend([r1, r2])

    # ۲) ۵ مود خبری (۲ ردیف)
    m_items = list(NEWS_MODES.items())
    rows.append([
        InlineKeyboardButton(text=("✅ " if mid == mode else "") + mcfg["fa"], callback_data=f"newsc:md:{mid}")
        for mid, mcfg in m_items[:3]
    ])
    rows.append([
        InlineKeyboardButton(text=("✅ " if mid == mode else "") + mcfg["fa"], callback_data=f"newsc:md:{mid}")
        for mid, mcfg in m_items[3:]
    ])

    # ۳) ۴ فرمت
    rows.append([
        InlineKeyboardButton(text=("✅ " if f == fmt else "") + f, callback_data=f"newsc:fmt:{f.replace(':', '_')}")
        for f in NEWS_FORMATS
    ])

    # ۴) شدت فیلتر رنگ روی تصویر (پیش‌فرض: شفاف / کم) + رنگ‌پردازی عکس
    rows.append([
        InlineKeyboardButton(text=("✅ " if tid == tint else "") + f"🎨 {tlbl}", callback_data=f"newsc:tint:{tid}")
        for tid, tlbl in NEWS_TINT_MODES
    ])
    rows.append([
        InlineKeyboardButton(text=("✅ " if mid == mood else "") + mlbl, callback_data=f"newsc:mood:{mid}")
        for mid, mlbl in NEWS_MOODS[:4]
    ])

    # ۵) ماژول‌های داخلی قابل انتخاب
    for m in mods:
        icon = "✅" if m["enabled"] else "⬜"
        rows.append([InlineKeyboardButton(text=f"{icon} {m['title_fa']}", callback_data=f"newsc:tog:{m['id']}")])

    rows.append([InlineKeyboardButton(text="🎨 ساخت کارت و کپشن نهایی", callback_data="newsc:build")])
    rows.append([
        InlineKeyboardButton(text="📰 لیست اخبار", callback_data="news:list"),
        InlineKeyboardButton(text="🎨 استودیو کارت‌ها", callback_data="nav:cards"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("news"))
async def cmd_news(m: Message) -> None:
    if not tp.is_admin(m.from_user.id):
        await m.answer("دسترسی غیرمجاز.")
        return
    from src.xgpedia.providers.breaking_news_free import list_breaking_news_items
    status_msg = await m.answer("⏳ در حال دریافت زندهٔ اخبار فوری فوتبال (ESPN + BBC Sport + Guardian)...")
    data = await asyncio.to_thread(list_breaking_news_items, include_live=True)
    text, kb = _format_news_list_message(data)
    await status_msg.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.in_({"news:list", "news:refresh"}))
async def on_news_list(cb: CallbackQuery) -> None:
    from src.xgpedia.providers.breaking_news_free import list_breaking_news_items
    force = cb.data == "news:refresh"
    await _safe_cb_answer(cb, "در حال دریافت اخبار فوری و رسمی...")
    wait_msg = await cb.message.answer("⏳ در حال دریافت زندهٔ اخبار فوری فوتبال (ESPN + BBC Sport + Guardian)...")
    data = await asyncio.to_thread(list_breaking_news_items, include_live=True, force_refresh=force)
    text, kb = _format_news_list_message(data)
    await wait_msg.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("news:open:"))
async def on_news_open(cb: CallbackQuery) -> None:
    from src.xgpedia.providers.breaking_news_free import get_breaking_news_item
    from src.xgpedia.render.card_kit.news_card import NEWS_DEFAULT_LAYOUT, get_news_slide_modules

    iid = cb.data.split(":", 2)[2]
    it = _NEWS_ITEM_MAP.get(iid) or await asyncio.to_thread(get_breaking_news_item, iid)
    if not it:
        await _safe_cb_answer(cb, "خبر یافت نشد؛ لطفاً لیست را بروزرسانی کنید.", show_alert=True)
        return
    await _safe_cb_answer(cb, "استودیو خبر باز شد.")
    def_ly = str(it.get("layout") or NEWS_DEFAULT_LAYOUT)
    mods, missing = get_news_slide_modules(it, def_ly)
    st = {
        "item": it,
        "layout": def_ly,
        "mode": str(it.get("mode") or "breaking"),
        "fmt": "4:5",
        "mood": str(it.get("mood") or "cinema"),
        "tint": str(it.get("tint_mode") or "light"),
        "photo_id": str(it.get("photoId") or "tunnel"),
        "modules": mods,
        "missing_modules": missing,
    }
    _NEWS_STATE[cb.from_user.id] = st
    text, markup = _render_news_customizer_view(st)
    await cb.message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "news:back")
async def on_news_back(cb: CallbackQuery) -> None:
    st = _NEWS_STATE.get(cb.from_user.id)
    if not st:
        await _safe_cb_answer(cb, "لطفاً دوباره خبر را از لیست انتخاب کنید.", show_alert=True)
        return
    await _safe_cb_answer(cb, "بازگشت به استودیو خبر")
    text, markup = _render_news_customizer_view(st)
    await cb.message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("newsc:"))
async def on_news_customizer_action(cb: CallbackQuery, bot: Bot) -> None:
    st = _NEWS_STATE.get(cb.from_user.id)
    if not st:
        await _safe_cb_answer(cb, "لطفاً دوباره خبر را از لیست انتخاب کنید.", show_alert=True)
        return

    from src.xgpedia.render.card_kit.news_card import get_news_layout_availability

    parts = cb.data.split(":")
    action = parts[1]

    if action == "ly":
        lid = parts[2]
        if not get_news_layout_availability(st["item"]).get(lid, True):
            await _safe_cb_answer(
                cb,
                "این خبر دیتای ساختاریافتهٔ انتقال ندارد (قانون null≠0). پوسترهای دیگر قابل استفاده‌اند.",
                show_alert=True,
            )
            return
        st["layout"] = lid
        await _safe_cb_answer(cb, f"پوستر روی {lid} تنظیم شد.")
    elif action == "md":
        st["mode"] = parts[2]
        await _safe_cb_answer(cb, f"مود خبر روی {st['mode']} تنظیم شد.")
    elif action == "fmt":
        st["fmt"] = parts[2].replace("_", ":")
        await _safe_cb_answer(cb, f"فرمت روی {st['fmt']} تنظیم شد.")
    elif action == "mood":
        st["mood"] = parts[2]
        await _safe_cb_answer(cb, f"رنگ‌پردازی تصویر روی {st['mood']} تنظیم شد.")
    elif action == "tint":
        st["tint"] = parts[2] if parts[2] in ("light", "strong") else "light"
        await _safe_cb_answer(cb, "فیلتر تصویر: " + ("شفاف (کم)" if st["tint"] == "light" else "دراماتیک (زیاد)"))
    elif action == "tog":
        mid = parts[2]
        target = next((m for m in st["modules"] if m["id"] == mid), None)
        if target:
            # فقط یک داک پایین هم‌زمان روشن باشد
            if mid.startswith("dock_") and not target["enabled"]:
                for other in st["modules"]:
                    if other["id"].startswith("dock_") and other["id"] != mid:
                        other["enabled"] = False
            target["enabled"] = not target["enabled"]
            await _safe_cb_answer(cb, f"{target['title_fa']}: {'فعال' if target['enabled'] else 'غیرفعال'}")
    elif action == "build":
        await _safe_cb_answer(cb, "در حال ساخت پوستر خبر فوری...")
        it = st["item"]
        wait_msg = await cb.message.answer(
            f"⏳ در حال ساخت پوستر خبری <b>{html.escape(str(it.get('title') or ''))[:70]}</b> ({st['layout']} | {st['fmt']})...",
            parse_mode="HTML",
        )

        async def _progress(msg_text: str) -> None:
            try:
                await wait_msg.edit_text(
                    f"{msg_text}\n📰 <b>{html.escape(str(it.get('title') or ''))[:70]}</b>",
                    parse_mode="HTML",
                )
            except TelegramBadRequest:
                pass

        enabled_ids = [m["id"] for m in st["modules"] if m["enabled"]]
        res = await tw.generate_news_post_async(
            it,
            layout=st["layout"],
            mode=st["mode"],
            fmt=st["fmt"],
            mood=st["mood"],
            photo_id=st["photo_id"],
            tint_mode=st.get("tint", "light"),
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
            note=f"✅ پوستر خبر آماده شد (پست #{res.post_id} | اسلاید {st['layout']} | مود {st['mode']} | {st['fmt']}).",
        )
        return

    text, markup = _render_news_customizer_view(st)
    for _attempt in range(3):
        try:
            await cb.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
            break
        except TelegramBadRequest:
            break
        except Exception as e:
            if _attempt == 2:
                log.warning("news customizer edit_text failed: %s", e)
            else:
                await asyncio.sleep(1.0)


@router.callback_query(F.data.startswith("news:page:"))
async def on_news_page(cb: CallbackQuery) -> None:
    await _safe_cb_answer(cb)
    try:
        page = int(cb.data.split(":")[2])
    except (IndexError, ValueError):
        page = 1
    text, kb = _format_news_list_message(_NEWS_LAST_DATA, page=page)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except TelegramBadRequest:
        pass
