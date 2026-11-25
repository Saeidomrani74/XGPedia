"""ماژول اختصاصی ربات تلگرام برای ۴ کارت جدید XGPedia (v0.31.0 — D51 تا D54):
  1. `/ratings`   — نمرات بازیکنان (Players Rating Studio — D51)
  2. `/standings` — جدول رده‌بندی (Standings Studio — D52)
  3. `/injury`    — آزمایشگاه مصدومیت (Injury Lab — D53)
  4. `/player`    — پروفایل فنی بازیکن (Player Card Studio — D54)

تمام ۴ کارت از استاندارد کامل ماژولار پشتیبانی می‌کنند:
  - صفحه‌بندی اجباری لیست آیتم‌ها و ماژول‌ها (`⬅️ صفحه قبل / ➡️ صفحه بعد`)
  - روشن/خاموش تک‌تک ماژول‌ها (`✅/⬜`) + تغییر عرض (`½`/`۱`) + تغییر ترتیب (`⬆️/⬇️`) + پیش‌نمایش شماتیک
  - ذخیره و بارگذاری تا ۵ قالب نام‌گذاری‌شده در `layout_templates.py` برای هر کارت به‌صورت مستقل
"""
from __future__ import annotations

import asyncio
import html
import time
from typing import Any, Callable

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from src.xgpedia import today_workflow as tw
from src.xgpedia.layout_templates import (
    MAX_SAVED_TEMPLATES,
    apply_template_to_modules,
    delete_layout_template,
    list_layout_templates,
    save_layout_template,
)
from src.xgpedia.publishers import telegram_publish as tp

modular_router = Router()

# وضعیت مستقل هر کارت برای هر کاربر
MODULAR_STATES: dict[str, dict[int, dict[str, Any]]] = {
    "players_rating": {},
    "standings": {},
    "injury_lab": {},
    "player_profile": {},
    "h2h_teams": {},
    "player_fc27": {},
    "h2h_players": {},
    "top_scorers": {},
    "matchday_results": {},
    "quote": {},
    "debate": {},
    "number_of_day": {},
}
MODULAR_ITEMS_MAP: dict[str, dict[str, dict[str, Any]]] = {
    "players_rating": {},
    "standings": {},
    "injury_lab": {},
    "player_profile": {},
    "h2h_teams": {},
    "player_fc27": {},
    "h2h_players": {},
    "top_scorers": {},
    "matchday_results": {},
    "quote": {},
    "debate": {},
    "number_of_day": {},
}
MODULAR_PICKER_STATE: dict[tuple[str, int], dict[str, Any]] = {}

MODULAR_LAST_DATA: dict[str, dict[str, list[dict[str, Any]]]] = {
    "players_rating": {"live": [], "presets": []},
    "standings": {"live": [], "presets": []},
    "injury_lab": {"live": [], "presets": []},
    "player_profile": {"live": [], "presets": []},
    "h2h_teams": {"live": [], "presets": []},
    "player_fc27": {"live": [], "presets": []},
    "h2h_players": {"live": [], "presets": []},
    "top_scorers": {"live": [], "presets": []},
    "matchday_results": {"live": [], "presets": []},
    "quote": {"live": [], "presets": []},
    "debate": {"live": [], "presets": []},
    "number_of_day": {"live": [], "presets": []},
}

# نقشهٔ مشخصات ۴ کارت
CARD_SPECS: dict[str, dict[str, Any]] = {
    "players_rating": {
        "prefix": "pr",
        "cprefix": "prc",
        "icon": "⭐️",
        "title": "نمرات بازیکنان (Players Rating)",
        "cmd": "ratings",
        "list_hint": "مسابقه‌ای را برای ساخت کارت نمرات بازیکنان انتخاب کنید:",
        "default_hm": "full",
        "hm_labels": ("هدر کامل", "هدر فشرده"),
    },
    "standings": {
        "prefix": "st",
        "cprefix": "stc",
        "icon": "🏆",
        "title": "جدول رده‌بندی (Standings Studio)",
        "cmd": "standings",
        "list_hint": "لیگ مورد نظر را برای ساخت کارت جدول رده‌بندی انتخاب کنید:",
        "default_hm": "hero",
        "hm_labels": ("تاج صدرنشینی", "هدر فشرده"),
    },
    "injury_lab": {
        "prefix": "inj",
        "cprefix": "injc",
        "icon": "🏥",
        "title": "آزمایشگاه مصدومیت (Injury Lab)",
        "cmd": "injury",
        "list_hint": "پرونده مصدومیت مورد نظر را انتخاب کنید:",
        "default_hm": "full",
        "hm_labels": ("پروفایل کامل", "هدر فشرده"),
    },
    "player_profile": {
        "prefix": "pl",
        "cprefix": "plc",
        "icon": "🧬",
        "title": "پروفایل فنی بازیکن (Player Studio)",
        "cmd": "player",
        "list_hint": "بازیکن مورد نظر را برای ساخت کارت پروفایل فنی انتخاب کنید:",
        "default_hm": "full",
        "hm_labels": ("هدر سینمایی", "هدر فشرده"),
    },
    "h2h_teams": {
        "prefix": "h2t",
        "cprefix": "h2tc",
        "icon": "⚔️",
        "title": "تقابل مستقیم تیم‌ها (H2H Teams)",
        "cmd": "h2hteams",
        "list_hint": "تقابل دو تیم را برای ساخت کارت تاریخچه انتخاب کنید:",
        "default_hm": "full",
        "hm_labels": ("هدر کامل دو تیم", "هدر فشرده"),
    },
    "player_fc27": {
        "prefix": "fc",
        "cprefix": "fcc",
        "icon": "🃏",
        "title": "کارت بازیکن FC27 (Chrono Card)",
        "cmd": "fc27",
        "list_hint": "بازیکن مورد نظر را برای ساخت کارت FC27 انتخاب کنید:",
        "default_hm": "full",
        "hm_labels": ("کارت کامل", "فشرده"),
    },
    "h2h_players": {
        "prefix": "h2p",
        "cprefix": "h2pc",
        "icon": "🆚",
        "title": "مقایسه دو بازیکن (H2H Players)",
        "cmd": "h2hplayers",
        "list_hint": "دوئل دو بازیکن را برای ساخت کارت مقایسه انتخاب کنید:",
        "default_hm": "full",
        "hm_labels": ("استیج دوئل کامل", "هدر فشرده"),
    },
    "top_scorers": {
        "prefix": "ts",
        "cprefix": "tsc",
        "icon": "👟",
        "title": "جدول گلزنان / کفش طلا (Top Scorers)",
        "cmd": "scorers",
        "list_hint": "لیگ مورد نظر را برای ساخت کارت جدول گلزنان انتخاب کنید:",
        "default_hm": "full",
        "hm_labels": ("تاج کفش طلا", "هدر فشرده"),
    },
    "matchday_results": {
        "prefix": "mr",
        "cprefix": "mrc",
        "icon": "📊",
        "title": "نتایج بازی‌های روز (Matchday Results)",
        "cmd": "results",
        "list_hint": "نتایج بازی‌های روز را انتخاب کنید:",
        "default_hm": "full",
        "hm_labels": ("هدر آماری کامل", "هدر فشرده"),
    },
    "quote": {
        "prefix": "qt",
        "cprefix": "qtc",
        "icon": "💬",
        "title": "نقل‌قول روز (Quote Studio)",
        "cmd": "quote",
        "list_hint": "نقل‌قول‌های پیشنهادی زنده (مرتب‌شده بر اساس تناسب با کارت) را انتخاب کنید:",
        "default_hm": "full",
        "hm_labels": ("هدر کامل", "هدر فشرده"),
    },
    "debate": {
        "prefix": "db",
        "cprefix": "dbc",
        "icon": "🔥",
        "title": "مناظره روز (Debate Studio)",
        "cmd": "debate",
        "list_hint": "مناظره‌های پیشنهادی زنده (آماری FPL و سوژه‌های داغ روز) را انتخاب کنید:",
        "default_hm": "full",
        "hm_labels": ("هدر کامل", "هدر فشرده"),
    },
    "number_of_day": {
        "prefix": "nd",
        "cprefix": "ndc",
        "icon": "🔢",
        "title": "عدد روز (Number of the Day)",
        "cmd": "number",
        "list_hint": "اعداد شگفت‌انگیز و رکوردهای زنده پیشنهادی امروز را انتخاب کنید:",
        "default_hm": "full",
        "hm_labels": ("هدر کامل", "هدر فشرده"),
    },
}


async def _safe_answer(cb: CallbackQuery, text: str = "", show_alert: bool = False) -> None:
    try:
        await cb.answer(text, show_alert=show_alert)
    except Exception:
        pass


def build_schematic(mods: list[dict[str, Any]]) -> str:
    """پیش‌نمایش متنی ترتیب و عرض ماژول‌های فعال."""
    active = [m for m in mods if m.get("enabled")]
    if not active:
        return "[ هیچ ماژولی فعال نیست ]"
    rows: list[str] = []
    i = 0
    while i < len(active):
        m = active[i]
        short = m["title_fa"].split("(")[0].strip()[:18]
        if m.get("span") == "half" and m.get("can_half", False):
            if i + 1 < len(active) and active[i + 1].get("span") == "half" and active[i + 1].get("can_half", False):
                s2 = active[i + 1]["title_fa"].split("(")[0].strip()[:18]
                rows.append(f"[ ½ {short} ] [ ½ {s2} ]")
                i += 2
                continue
            rows.append(f"[ ½ {short} (تمام‌عرض خودکار) ]")
        else:
            rows.append(f"[  ۱  {short}  ]")
        i += 1
    return "\n".join(rows)


def _item_label(card_kind: str, it: dict[str, Any]) -> str:
    if card_kind == "players_rating":
        h = (it.get("home") or {}).get("name", "")
        a = (it.get("away") or {}).get("name", "")
        ago_s = it.get("finished_elapsed_sec")
        ago_txt = f" • {max(1, int(ago_s) // 3600)}س قبل" if ago_s is not None and int(ago_s) >= 3600 else (f" • {max(1, int(ago_s) // 60)}د قبل" if ago_s is not None else "")
        return f"{h} {it.get('homeGoals', 0)}-{it.get('awayGoals', 0)} {a} ({it.get('competition', '')}){ago_txt}"
    if card_kind == "standings":
        return f"{it.get('name', '')} — {it.get('round', '')}"
    if card_kind == "injury_lab":
        pl = it.get("player") or {}
        inj = it.get("injury") or {}
        return f"{pl.get('name', '')} ({pl.get('club', '')}) • {inj.get('eta', '')}"
    if card_kind == "h2h_teams":
        h = (it.get("home") or {}).get("name", "")
        a = (it.get("away") or {}).get("name", "")
        return f"{h} مقابل {a} ({it.get('competition', '')})"
    if card_kind == "player_fc27":
        return f"{it.get('name', '')} ({it.get('club', '')}) • OVR {it.get('ovr', '')}"
    if card_kind == "h2h_players":
        p1 = (it.get("p1") or {}).get("name", "")
        p2 = (it.get("p2") or {}).get("name", "")
        return f"{p1} 🆚 {p2} ({it.get('competition', '')})"
    if card_kind == "top_scorers":
        return f"{it.get('competition', '')} — {it.get('round', '')}"
    if card_kind == "matchday_results":
        cnt = len(it.get("matches") or [])
        return f"{it.get('competition', '')} ({cnt} بازی)"
    if card_kind == "quote":
        sp = str(it.get("speaker") or "نقل‌قول")
        fit = it.get("fit_score")
        fit_s = f" • امتیاز {fit}" if fit else ""
        q_short = str(it.get("quote") or "").replace("*", "")[:36]
        return f"{sp}: «{q_short}…»{fit_s}"
    if card_kind == "debate":
        a = (it.get("sideA") or {}).get("name", "")
        b = (it.get("sideB") or {}).get("name", "")
        ht = it.get("heat")
        ht_s = f" • {ht}°" if ht else ""
        return f"{a} × {b} ({it.get('category', '')}){ht_s}"
    if card_kind == "number_of_day":
        num = f"{it.get('number', '')}{it.get('suffix', '')}"
        return f"[{num}] {it.get('subject', '')} — {it.get('unit', '')}"
    return f"{it.get('name', '')} ({it.get('club', '')}) • XG {it.get('ovr', '')}"


def format_card_list_message(
    card_kind: str,
    data: dict[str, list[dict[str, Any]]],
    *,
    page: int = 1,
    show_presets: bool = False,
    page_size: int = 6,
) -> tuple[str, InlineKeyboardMarkup]:
    """ساخت لیست صفحه‌بندی‌شده آیتم‌های زنده یا پریست برای هر یک از ۴ کارت."""
    spec = CARD_SPECS[card_kind]
    pref = spec["prefix"]
    MODULAR_LAST_DATA[card_kind] = data
    live = data.get("live") or []
    presets = data.get("presets") or []
    for it in live + presets:
        iid = str(it.get("id") or "")
        if iid:
            MODULAR_ITEMS_MAP[card_kind][iid] = it

    pool = presets if show_presets else live
    mode_lbl = "پریست‌های آماده" if show_presets else "دیتای زنده (رایگان)"
    total = len(pool)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    chunk = pool[start : start + page_size]

    lines = [
        f"{spec['icon']} <b>{html.escape(spec['title'])}</b>",
        f"📂 نمایش: <b>{mode_lbl}</b> | صفحه <b>{page}/{total_pages}</b> ({total} مورد)",
        (
            (
                "⚠️ در بازه زمانی زنده (۱ ثانیه تا ۲۴ ساعت قبل) موردی یافت نشد. روی «🔄 بروزرسانی زنده» بزنید یا «⭐ پریست‌های آماده» را انتخاب کنید."
                if card_kind in {"players_rating", "matchday_results"}
                else "⚠️ در حال حاضر دیتای زنده‌ای دریافت نشد. روی «🔄 بروزرسانی زنده» بزنید یا «⭐ پریست‌های آماده» را انتخاب کنید."
            )
            if (not show_presets and total == 0)
            else spec["list_hint"]
        ),
    ]
    rows: list[list[InlineKeyboardButton]] = []
    for idx, it in enumerate(chunk, start + 1):
        iid = str(it.get("id") or f"it_{idx}")
        MODULAR_ITEMS_MAP[card_kind][iid] = it
        lbl = _item_label(card_kind, it)[:58]
        rows.append([InlineKeyboardButton(text=f"{idx}. {lbl}", callback_data=f"{pref}:open:{iid}")])

    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 1:
            nav.append(InlineKeyboardButton(text="⬅️ صفحه قبل", callback_data=f"{pref}:list:{page - 1}"))
        nav.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data=f"{pref}:noop"))
        if page < total_pages:
            nav.append(InlineKeyboardButton(text="➡️ صفحه بعد", callback_data=f"{pref}:list:{page + 1}"))
        rows.append(nav)

    rows.append([
        InlineKeyboardButton(text="🔄 بروزرسانی زنده", callback_data=f"{pref}:refresh"),
        InlineKeyboardButton(text="⭐ پریست‌های آماده" if not show_presets else "📡 دیتای زنده", callback_data=f"{pref}:{'list:1' if show_presets else 'presets'}"),
    ])
    if card_kind in {"h2h_teams", "h2h_players", "player_fc27", "player_profile"}:
        pick_lbl = (
            "🎯 انتخاب دستی ۲ تیم (لیگ ← تیم ۱ ← تیم ۲)"
            if card_kind == "h2h_teams"
            else (
                "🎯 انتخاب دستی ۲ بازیکن (لیگ ← تیم ← بازیکن)"
                if card_kind == "h2h_players"
                else "🎯 انتخاب دستی بازیکن (لیگ ← تیم ← بازیکن)"
            )
        )
        rows.append([InlineKeyboardButton(text=pick_lbl, callback_data=f"{pref}:pick:league")])
    rows.append([InlineKeyboardButton(text="🎨 استودیو کارت‌ها", callback_data="nav:cards")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def _get_slides_and_modules(card_kind: str, item: dict[str, Any], slide: str) -> tuple[list[tuple], list[dict[str, Any]], list[str]]:
    preview_it = dict(item)
    if card_kind == "players_rating":
        from src.xgpedia.render.card_kit.players_rating_card import RATINGS_SLIDES, get_players_rating_modules
        if not preview_it.get("verdict"):
            preview_it["verdict"] = {"title": "تحلیل", "body": "(در مرحله ساخت تکمیل می‌شود)", "tag": "XGPedia"}
        mods, miss = get_players_rating_modules(preview_it, slide)
        return RATINGS_SLIDES, mods, miss
    if card_kind == "standings":
        from src.xgpedia.render.card_kit.standings_card import STANDINGS_SLIDES, get_standings_modules
        mods, miss = get_standings_modules(preview_it, slide)
        return STANDINGS_SLIDES, mods, miss
    if card_kind == "injury_lab":
        from src.xgpedia.render.card_kit.injury_card import INJURY_SLIDES, get_injury_modules
        if not preview_it.get("verdict"):
            preview_it["verdict"] = {"title": "تحلیل", "body": "(در مرحله ساخت تکمیل می‌شود)", "tag": "XGPedia"}
        mods, miss = get_injury_modules(preview_it, slide)
        return INJURY_SLIDES, mods, miss
    if card_kind == "h2h_teams":
        from src.xgpedia.render.card_kit.h2h_teams_card import H2H_TEAMS_SLIDES, get_h2h_teams_modules
        mods, miss = get_h2h_teams_modules(preview_it, slide)
        return H2H_TEAMS_SLIDES, mods, miss
    if card_kind == "player_fc27":
        from src.xgpedia.render.card_kit.player_fc27_card import FC27_SLIDES, get_player_fc27_modules
        mods, miss = get_player_fc27_modules(preview_it, slide)
        return FC27_SLIDES, mods, miss
    if card_kind == "h2h_players":
        from src.xgpedia.render.card_kit.h2h_players_card import H2H_PLAYERS_SLIDES, get_h2h_players_modules
        mods, miss = get_h2h_players_modules(preview_it, slide)
        return H2H_PLAYERS_SLIDES, mods, miss
    if card_kind == "top_scorers":
        from src.xgpedia.render.card_kit.top_scorers_card import TOP_SCORERS_SLIDES, get_top_scorers_modules
        mods, miss = get_top_scorers_modules(preview_it, slide)
        return TOP_SCORERS_SLIDES, mods, miss
    if card_kind == "matchday_results":
        from src.xgpedia.render.card_kit.matchday_results_card import MATCHDAY_RESULTS_SLIDES, get_matchday_results_modules
        mods, miss = get_matchday_results_modules(preview_it, slide)
        return MATCHDAY_RESULTS_SLIDES, mods, miss
    if card_kind == "quote":
        from src.xgpedia.render.card_kit.quote_card import QUOTE_SLIDES, get_quote_modules
        mods, miss = get_quote_modules(preview_it, slide)
        return QUOTE_SLIDES, mods, miss
    if card_kind == "debate":
        from src.xgpedia.render.card_kit.debate_card import DEBATE_SLIDES, get_debate_modules
        mods, miss = get_debate_modules(preview_it, slide)
        return DEBATE_SLIDES, mods, miss
    if card_kind == "number_of_day":
        from src.xgpedia.render.card_kit.number_of_day_card import NOD_SLIDES, get_number_of_day_modules
        mods, miss = get_number_of_day_modules(preview_it, slide)
        return NOD_SLIDES, mods, miss
    from src.xgpedia.render.card_kit.player_card import PLAYER_SLIDES, get_player_modules
    if not preview_it.get("scout"):
        preview_it["scout"] = {"title": "گزارش دیده‌بان", "body": "(در مرحله ساخت تکمیل می‌شود)", "strengths": [], "watchout": "", "tag": "XGPedia"}
    mods, miss = get_player_modules(preview_it, slide)
    return PLAYER_SLIDES, mods, miss


def render_modular_customizer_view(card_kind: str, st: dict[str, Any]) -> tuple[str, InlineKeyboardMarkup]:
    """رندر پنل کاستومایزر ماژولار کامل (روشن/خاموش + عرض ½/۱ + ترتیب ⬆️/⬇️ + ۵ قالب ذخیره‌شده)."""
    spec = CARD_SPECS[card_kind]
    pref = spec["prefix"]
    cpref = spec["cprefix"]
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

    slides_meta, _, _ = _get_slides_and_modules(card_kind, it, slide)
    active_cnt = sum(1 for m in mods if m["enabled"])
    schematic = build_schematic(mods)
    tpl_cnt = len(list_layout_templates(card_kind))

    extra_info = ""
    if card_kind == "players_rating":
        extra_info = f"🏟 زمین: <b>{st.get('pitch_mode', 'both')}</b> | 🎨 تم: <b>{st.get('theme', 'turf')}</b>"
    elif card_kind == "standings":
        extra_info = f"🔎 لنز: <b>{st.get('lens', 'classic')}</b> | برش: <b>{st.get('table_slice', 'top10')}</b>"
    elif card_kind == "injury_lab":
        extra_info = f"🚨 وضعیت: <b>{st.get('severity', (it.get('injury') or {}).get('severity', 'out'))}</b>"
    elif card_kind == "player_profile":
        extra_info = f"🎨 استایل: <b>{st.get('theme', 'classic')}</b>"
    elif card_kind == "h2h_teams":
        extra_info = f"🎭 اتمسفر: <b>{st.get('theme', 'cinematic')}</b>"
    elif card_kind == "top_scorers":
        extra_info = f"🎨 تم: <b>{st.get('theme', 'gold')}</b> | 🔢 مرتب‌سازی: <b>{st.get('sort_by', 'goals')}</b>"
    elif card_kind == "player_fc27":
        extra_info = f"🃏 پوسته کارت: <b>{st.get('theme') or it.get('skin', 'signature')}</b>"
    elif card_kind == "matchday_results":
        extra_info = f"🎨 تم گرافیکی: <b>{st.get('theme', 'classic')}</b>"
    elif card_kind == "quote":
        extra_info = f"✨ هایلایت: <b>{st.get('hl_style', 'underline')}</b> | 🎬 نور: <b>{st.get('grade', 'cinematic')}</b>"
    elif card_kind == "debate":
        extra_info = f"🎨 اتمسفر بصری: <b>{st.get('theme', 'classic')}</b>"
    elif card_kind == "number_of_day":
        extra_info = f"🔠 فونت عدد: <b>{st.get('theme', 'lalezar')}</b>"

    lines = [
        f"{spec['icon']} <b>{html.escape(spec['title'])}</b>",
        f"📌 <b>{html.escape(_item_label(card_kind, it))}</b>",
        f"📐 فرمت: <b>{fmt}</b> | 🧩 هدر: <b>{hm}</b> | ماژول فعال: <b>{active_cnt} از {total_mods}</b>",
        extra_info,
        "",
        "🗺 <b>چیدمان و ترتیب فعلی کارت:</b>",
        f"<pre>{html.escape(schematic)}</pre>",
    ]
    if missing:
        lines.append("ℹ️ بدون دیتای ثبت‌شده (null≠0): " + html.escape("، ".join(missing[:5])))
    lines.append("نام = روشن/خاموش | ½ یا ۱ = عرض | ⬆️⬇️ = ترتیب:")

    rows: list[list[InlineKeyboardButton]] = []
    # ۱) پریست‌های اسلاید
    s_btns = [
        InlineKeyboardButton(text=("✅ " if s[0] == slide else "") + f"اسلاید {i}", callback_data=f"{cpref}:sl:{s[0]}")
        for i, s in enumerate(slides_meta, 1)
    ]
    rows.append(s_btns[:3])
    if len(s_btns) > 3:
        rows.append(s_btns[3:])

    # ۲) هدر و فرمت
    hm_full_val = "hero" if card_kind == "standings" else "full"
    lbl_full, lbl_cmp = spec["hm_labels"]
    rows.append([
        InlineKeyboardButton(text=("✅ " if hm == hm_full_val else "") + lbl_full, callback_data=f"{cpref}:hm:{hm_full_val}"),
        InlineKeyboardButton(text=("✅ " if hm == "compact" else "") + lbl_cmp, callback_data=f"{cpref}:hm:compact"),
    ])
    rows.append([
        InlineKeyboardButton(text=("✅ " if f == fmt else "") + f, callback_data=f"{cpref}:fmt:{f.replace(':', '_')}")
        for f in ("4:5", "9:16", "16:9")
    ])

    # ۲.۵) کنترل‌های اختصاصی هر کارت
    if card_kind == "players_rating":
        pm = st.get("pitch_mode", "both")
        th = st.get("theme", "turf")
        rows.append([
            InlineKeyboardButton(text=("✅ " if pm == k else "") + lbl, callback_data=f"{cpref}:opt:pm:{k}")
            for k, lbl in (("both", "۲۲ نفر"), ("home", "میزبان"), ("away", "میهمان"))
        ])
        rows.append([
            InlineKeyboardButton(text=("✅ " if th == k else "") + lbl, callback_data=f"{cpref}:opt:th:{k}")
            for k, lbl in (("turf", "چمن"), ("navy", "سرمه‌ای"), ("gold", "طلایی"))
        ])
    elif card_kind == "standings":
        ln = st.get("lens", "classic")
        slc = st.get("table_slice", "top10")
        rows.append([
            InlineKeyboardButton(text=("✅ " if ln == k else "") + lbl, callback_data=f"{cpref}:opt:ln:{k}")
            for k, lbl in (("classic", "کلاسیک"), ("xpts", "عدالت xPTS"), ("xg", "xG و شانس"))
        ])
        rows.append([
            InlineKeyboardButton(text=("✅ " if slc == k else "") + lbl, callback_data=f"{cpref}:opt:slc:{k}")
            for k, lbl in (("top6", "۶ برتر"), ("top10", "۱۰ برتر"), ("full", "کل لیگ"), ("bottom", "سقوط"))
        ])
    elif card_kind == "injury_lab":
        sv = st.get("severity", (it.get("injury") or {}).get("severity", "out"))
        rows.append([
            InlineKeyboardButton(text=("✅ " if sv == k else "") + lbl, callback_data=f"{cpref}:opt:sv:{k}")
            for k, lbl in (("out", "غیبت"), ("long", "سنگین"), ("doubt", "مشکوک"), ("fit", "بازگشت"))
        ])
    elif card_kind == "player_profile":
        th = st.get("theme", "classic")
        rows.append([
            InlineKeyboardButton(text=("✅ " if th == k else "") + lbl, callback_data=f"{cpref}:opt:th:{k}")
            for k, lbl in (("classic", "کلاسیک XG"), ("gold", "ویژه MOTM"), ("blueprint", "تاکتیکی"))
        ])
    elif card_kind == "player_fc27":
        th = st.get("theme") or it.get("skin", "signature")
        rows.append([
            InlineKeyboardButton(text=("✅ " if th == k else "") + lbl, callback_data=f"{cpref}:opt:th:{k}")
            for k, lbl in (("signature", "Signature"), ("persian", "Persian 1/1"), ("icon", "Icon"))
        ])
        rows.append([
            InlineKeyboardButton(text=("✅ " if th == k else "") + lbl, callback_data=f"{cpref}:opt:th:{k}")
            for k, lbl in (("tots", "TOTS"), ("ucl", "UCL Night"), ("future", "Future Star"))
        ])
    elif card_kind == "matchday_results":
        th = st.get("theme", "classic")
        rows.append([
            InlineKeyboardButton(text=("✅ " if th == k else "") + lbl, callback_data=f"{cpref}:opt:th:{k}")
            for k, lbl in (("classic", "کلاسیک"), ("ucl", "لیگ قهرمانان"), ("gold", "طلایی"))
        ])
    elif card_kind == "quote":
        hl_v = st.get("hl_style", "underline")
        gr_v = st.get("grade", "cinematic")
        rows.append([
            InlineKeyboardButton(text=("✅ " if hl_v == k else "") + lbl, callback_data=f"{cpref}:opt:hl:{k}")
            for k, lbl in (("underline", "خط نئونی"), ("pill", "ماژیک مجله‌ای"), ("accent", "نور رنگی"))
        ])
        rows.append([
            InlineKeyboardButton(text=("✅ " if gr_v == k else "") + lbl, callback_data=f"{cpref}:opt:gr:{k}")
            for k, lbl in (("cinematic", "سینمایی"), ("duotone", "دوتُن"), ("rim", "نور حاشیه"), ("natural", "طبیعی"))
        ])
    elif card_kind == "debate":
        th = st.get("theme", "classic")
        rows.append([
            InlineKeyboardButton(text=("✅ " if th == k else "") + lbl, callback_data=f"{cpref}:opt:th:{k}")
            for k, lbl in (("classic", "کلاسیک XG"), ("pitch", "شب استادیوم"), ("derby", "دربی آتشین"))
        ])
    elif card_kind == "number_of_day":
        th = st.get("theme", "lalezar")
        rows.append([
            InlineKeyboardButton(text=("✅ " if th == k else "") + lbl, callback_data=f"{cpref}:opt:th:{k}")
            for k, lbl in (("lalezar", "لاله‌زار (۹۱)"), ("vazir", "وزیرمتن (۹۱)"), ("bebas", "BEBAS (91)"))
        ])

    # ۳) کنترل‌های ماژولار (روشن/خاموش + عرض ½/۱ + ترتیب ⬆️/⬇️)
    for g_idx in range(m_start, m_end):
        m = mods[g_idx]
        mark = "✅" if m["enabled"] else "⬜"
        sp_badge = "½" if (m.get("span") == "half" and m.get("can_half", False)) else "۱"
        rows.append([InlineKeyboardButton(text=f"{mark} {m['title_fa']}  [{sp_badge}]", callback_data=f"{cpref}:tog:{m['id']}")])
        ctrl: list[InlineKeyboardButton] = []
        if m.get("can_half", False):
            w_lbl = "عرض: نیم‌عرض ½ 🔁" if m.get("span") == "half" else "عرض: تمام‌عرض ۱ 🔁"
            ctrl.append(InlineKeyboardButton(text=w_lbl, callback_data=f"{cpref}:sp:{m['id']}"))
        else:
            ctrl.append(InlineKeyboardButton(text="🔒 تمام‌عرض", callback_data=f"{cpref}:noop"))
        ctrl.append(InlineKeyboardButton(text="⬆️ بالا" if g_idx > 0 else "·", callback_data=f"{cpref}:up:{m['id']}" if g_idx > 0 else f"{cpref}:noop"))
        ctrl.append(InlineKeyboardButton(text="⬇️ پایین" if g_idx < total_mods - 1 else "·", callback_data=f"{cpref}:dn:{m['id']}" if g_idx < total_mods - 1 else f"{cpref}:noop"))
        rows.append(ctrl)

    if total_mpages > 1:
        p_nav: list[InlineKeyboardButton] = []
        if mpage > 1:
            p_nav.append(InlineKeyboardButton(text="⬅️ ماژول‌های قبل", callback_data=f"{cpref}:mp:{mpage - 1}"))
        p_nav.append(InlineKeyboardButton(text=f"🧩 صفحه {mpage}/{total_mpages}", callback_data=f"{cpref}:noop"))
        if mpage < total_mpages:
            p_nav.append(InlineKeyboardButton(text="➡️ ماژول‌های بعد", callback_data=f"{cpref}:mp:{mpage + 1}"))
        rows.append(p_nav)

    # ۴) ۵ قالب نام‌گذاری‌شده
    rows.append([
        InlineKeyboardButton(text=f"💾 ذخیره قالب ({tpl_cnt}/{MAX_SAVED_TEMPLATES})", callback_data=f"{cpref}:tpl_save"),
        InlineKeyboardButton(text=f"📂 قالب‌های من ({tpl_cnt}/{MAX_SAVED_TEMPLATES})", callback_data=f"{cpref}:tpl_list"),
    ])
    rows.append([InlineKeyboardButton(text="🎨 ساخت کارت و کپشن نهایی", callback_data=f"{cpref}:build")])
    rows.append([
        InlineKeyboardButton(text=f"{spec['icon']} بازگشت به لیست", callback_data=f"{pref}:list:1"),
        InlineKeyboardButton(text="🎨 استودیو کارت‌ها", callback_data="nav:cards"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def _fetch_provider_data(card_kind: str, *, include_live: bool = True, force_refresh: bool = False) -> dict[str, list[dict[str, Any]]]:
    if card_kind == "players_rating":
        from src.xgpedia.providers.players_rating_free import list_players_rating_items
        return list_players_rating_items(include_live=include_live, force_refresh=force_refresh)
    if card_kind == "standings":
        from src.xgpedia.providers.standings_free import list_standings_leagues
        return list_standings_leagues(include_live=include_live, force_refresh=force_refresh)
    if card_kind == "injury_lab":
        from src.xgpedia.providers.injury_free import list_injury_items
        return list_injury_items(include_live=include_live, force_refresh=force_refresh)
    if card_kind == "h2h_teams":
        from src.xgpedia.providers.h2h_teams_free import fetch_live_h2h_teams_items, load_h2h_teams_presets
        return {"live": fetch_live_h2h_teams_items(force_refresh=force_refresh) if include_live else [], "presets": load_h2h_teams_presets()}
    if card_kind == "player_fc27":
        from src.xgpedia.providers.player_fc27_free import fetch_live_player_fc27_items, load_player_fc27_presets
        return {"live": fetch_live_player_fc27_items(force_refresh=force_refresh) if include_live else [], "presets": load_player_fc27_presets()}
    if card_kind == "h2h_players":
        from src.xgpedia.providers.h2h_players_free import fetch_live_h2h_players_items, load_h2h_players_presets
        return {"live": fetch_live_h2h_players_items(force_refresh=force_refresh) if include_live else [], "presets": load_h2h_players_presets()}
    if card_kind == "top_scorers":
        from src.xgpedia.providers.top_scorers_free import fetch_live_top_scorers_items, load_top_scorers_presets
        return {"live": fetch_live_top_scorers_items(force_refresh=force_refresh) if include_live else [], "presets": load_top_scorers_presets()}
    if card_kind == "matchday_results":
        from src.xgpedia.providers.matchday_results_free import fetch_live_matchday_results_items, load_matchday_results_presets
        return {"live": fetch_live_matchday_results_items(force_refresh=force_refresh) if include_live else [], "presets": load_matchday_results_presets()}
    if card_kind == "quote":
        from src.xgpedia.providers.quote_free import fetch_live_quote_items, load_quote_presets
        return {"live": fetch_live_quote_items(force_refresh=force_refresh) if include_live else [], "presets": load_quote_presets()}
    if card_kind == "debate":
        from src.xgpedia.providers.debate_free import fetch_live_debate_items, load_debate_presets
        return {"live": fetch_live_debate_items(force_refresh=force_refresh) if include_live else [], "presets": load_debate_presets()}
    if card_kind == "number_of_day":
        from src.xgpedia.providers.number_of_day_free import fetch_live_number_of_day_items, load_number_of_day_presets
        return {"live": fetch_live_number_of_day_items(force_refresh=force_refresh) if include_live else [], "presets": load_number_of_day_presets()}
    from src.xgpedia.providers.player_profile_free import list_player_profile_items
    return list_player_profile_items(include_live=include_live, force_refresh=force_refresh)


def _register_card_handlers(card_kind: str) -> None:
    spec = CARD_SPECS[card_kind]
    pref = spec["prefix"]
    cpref = spec["cprefix"]
    cmd_name = spec["cmd"]

    @modular_router.message(Command(cmd_name))
    async def _cmd_open(m: Message) -> None:
        if not tp.is_admin(m.from_user.id):
            await m.answer("دسترسی غیرمجاز.")
            return
        wait = await m.answer(f"⏳ در حال دریافت دیتای زنده {spec['title']}...")
        data = await asyncio.to_thread(_fetch_provider_data, card_kind, include_live=True)
        text, kb = format_card_list_message(card_kind, data, page=1)
        await wait.edit_text(text, parse_mode="HTML", reply_markup=kb)

    @modular_router.callback_query(F.data.startswith(f"{pref}:list:"))
    async def _on_list(cb: CallbackQuery) -> None:
        if not tp.is_admin(cb.from_user.id):
            await _safe_answer(cb, "شما مجاز نیستید.", show_alert=True)
            return
        try:
            page = int(cb.data.split(":")[2])
        except Exception:
            page = 1
        cached = MODULAR_LAST_DATA[card_kind]
        if not cached.get("live") and not cached.get("presets"):
            await _safe_answer(cb, "در حال دریافت داده‌ها...")
            wait = await cb.message.answer(f"⏳ در حال دریافت دیتای زنده {spec['title']}...")
            data = await asyncio.to_thread(_fetch_provider_data, card_kind, include_live=True)
            text, kb = format_card_list_message(card_kind, data, page=page)
            await wait.edit_text(text, parse_mode="HTML", reply_markup=kb)
            return
        await _safe_answer(cb)
        text, kb = format_card_list_message(card_kind, cached, page=page)
        try:
            await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except TelegramBadRequest:
            await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)

    @modular_router.callback_query(F.data == f"{pref}:refresh")
    async def _on_refresh(cb: CallbackQuery) -> None:
        if not tp.is_admin(cb.from_user.id):
            await _safe_answer(cb, "شما مجاز نیستید.", show_alert=True)
            return
        await _safe_answer(cb, "در حال بروزرسانی زنده...")
        wait = await cb.message.answer(f"⏳ در حال دریافت زنده {spec['title']}...")
        data = await asyncio.to_thread(_fetch_provider_data, card_kind, include_live=True, force_refresh=True)
        text, kb = format_card_list_message(card_kind, data, page=1)
        await wait.edit_text(text, parse_mode="HTML", reply_markup=kb)

    @modular_router.callback_query(F.data == f"{pref}:presets")
    async def _on_presets(cb: CallbackQuery) -> None:
        if not tp.is_admin(cb.from_user.id):
            await _safe_answer(cb, "شما مجاز نیستید.", show_alert=True)
            return
        await _safe_answer(cb)
        cached = MODULAR_LAST_DATA[card_kind]
        if not cached.get("presets"):
            cached = await asyncio.to_thread(_fetch_provider_data, card_kind, include_live=False)
        text, kb = format_card_list_message(card_kind, cached, page=1, show_presets=True)
        try:
            await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except TelegramBadRequest:
            await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)


    @modular_router.callback_query(F.data.startswith(f"{pref}:pick:"))
    async def _on_manual_picker(cb: CallbackQuery) -> None:
        if not tp.is_admin(cb.from_user.id):
            await _safe_answer(cb, "شما مجاز نیستید.", show_alert=True)
            return
        try:
            from src.xgpedia.providers.pl_picker_free import (
                build_pl_fc27_item,
                build_pl_h2h_players_item,
                build_pl_h2h_teams_item,
                build_pl_profile_item,
                list_pl_team_players,
                list_pl_teams,
            )
            parts = cb.data.split(":")
            step = parts[2] if len(parts) > 2 else "league"
            pstate = MODULAR_PICKER_STATE.setdefault((card_kind, cb.from_user.id), {})

            async def _open_built_item(built: dict[str, Any] | None) -> None:
                if not built:
                    await _safe_answer(cb, "امکان ساخت آیتم برای این انتخاب وجود نداشت.", show_alert=True)
                    return
                iid = str(built.get("id") or f"pick_{int(time.time())}")
                MODULAR_ITEMS_MAP[card_kind][iid] = built
                slide_def = "slide1"
                _, mods, miss = _get_slides_and_modules(card_kind, built, slide_def)
                st_new: dict[str, Any] = {
                    "item": built, "slide": slide_def, "header_mode": spec["default_hm"],
                    "fmt": "4:5", "modules": mods, "missing_modules": miss, "mod_page": 1,
                }
                if card_kind == "player_profile":
                    st_new["theme"] = "classic"
                elif card_kind == "player_fc27":
                    st_new["theme"] = str(built.get("skin") or "signature")
                elif card_kind == "h2h_teams":
                    st_new["theme"] = "classic"
                MODULAR_STATES[card_kind][cb.from_user.id] = st_new
                text_c, kb_c = render_modular_customizer_view(card_kind, st_new)
                await cb.message.edit_text(text_c, parse_mode="HTML", reply_markup=kb_c)

            if step == "league":
                pstate.clear()
                await _safe_answer(cb)
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏴󠁧󠁢󠁥󠁮󠁧󠁿 لیگ برتر انگلیس (Premier League)", callback_data=f"{pref}:pick:t1:1")],
                    [InlineKeyboardButton(text="↩️ بازگشت به لیست", callback_data=f"{pref}:list:1")],
                ])
                await cb.message.edit_text(
                    f"{spec['icon']} <b>انتخاب دستی — مرحله ۱: انتخاب لیگ</b>\nدر حال حاضر لیگ برتر انگلیس با دیتای رسمی زنده فعال است:",
                    parse_mode="HTML",
                    reply_markup=kb,
                )
                return

            if step in ("t1", "t2", "p2t"):
                page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1
                await _safe_answer(cb, "در حال بارگذاری تیم‌های لیگ برتر...")
                teams = await asyncio.to_thread(list_pl_teams)
                if not teams:
                    await cb.message.edit_text("⚠️ لیست تیم‌های لیگ برتر دریافت نشد. لطفاً دوباره تلاش کنید.")
                    return
                if step == "t2" and pstate.get("t1_id"):
                    teams = [t for t in teams if t["id"] != pstate["t1_id"]]
                psize = 8
                tpages = max(1, (len(teams) + psize - 1) // psize)
                page = max(1, min(page, tpages))
                chunk = teams[(page - 1) * psize : page * psize]
                next_act = "sel_t1" if step == "t1" else ("sel_t2" if step == "t2" else "p2")
                rows_k: list[list[InlineKeyboardButton]] = []
                for idx in range(0, len(chunk), 2):
                    row_b = []
                    for t in chunk[idx : idx + 2]:
                        cb_next = f"{pref}:pick:{next_act}:{t['id']}" if next_act != "p2" else f"{pref}:pick:p2:{t['id']}:1"
                        row_b.append(InlineKeyboardButton(text=f"#{t['rank']} {t['name']}", callback_data=cb_next))
                    rows_k.append(row_b)
                nav = []
                if page > 1:
                    nav.append(InlineKeyboardButton(text="⬅️ قبل", callback_data=f"{pref}:pick:{step}:{page - 1}"))
                nav.append(InlineKeyboardButton(text=f"{page}/{tpages}", callback_data=f"{pref}:noop"))
                if page < tpages:
                    nav.append(InlineKeyboardButton(text="➡️ بعد", callback_data=f"{pref}:pick:{step}:{page + 1}"))
                rows_k.append(nav)
                rows_k.append([InlineKeyboardButton(text="↩️ بازگشت", callback_data=f"{pref}:pick:league")])
                hdr = (
                    "تیم اول را انتخاب کنید:" if step == "t1"
                    else ("تیم دوم را انتخاب کنید:" if step == "t2" else "تیمِ بازیکن دوم را انتخاب کنید:")
                )
                await cb.message.edit_text(
                    f"{spec['icon']} <b>لیگ برتر انگلیس — {hdr}</b> (صفحه {page}/{tpages})",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows_k),
                )
                return

            if step == "sel_t1":
                tid = int(parts[3])
                pstate["t1_id"] = tid
                if card_kind == "h2h_teams":
                    await _safe_answer(cb, "تیم اول انتخاب شد؛ حالا تیم دوم را انتخاب کنید.")
                    # Redirect to t2 page 1
                    teams = await asyncio.to_thread(list_pl_teams)
                    teams = [t for t in teams if t["id"] != tid]
                    psize = 8
                    tpages = max(1, (len(teams) + psize - 1) // psize)
                    chunk = teams[:psize]
                    rows_k = [
                        [InlineKeyboardButton(text=f"#{t['rank']} {t['name']}", callback_data=f"{pref}:pick:sel_t2:{t['id']}") for t in chunk[i:i+2]]
                        for i in range(0, len(chunk), 2)
                    ]
                    if tpages > 1:
                        rows_k.append([
                            InlineKeyboardButton(text=f"1/{tpages}", callback_data=f"{pref}:noop"),
                            InlineKeyboardButton(text="➡️ بعد", callback_data=f"{pref}:pick:t2:2"),
                        ])
                    rows_k.append([InlineKeyboardButton(text="↩️ تغییر تیم اول", callback_data=f"{pref}:pick:t1:1")])
                    await cb.message.edit_text(
                        f"{spec['icon']} <b>لیگ برتر انگلیس — تیم دوم را انتخاب کنید:</b> (صفحه 1/{tpages})",
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows_k),
                    )
                    return
                # For player cards (h2h_players, player_fc27, player_profile): list players of team tid
                await _safe_answer(cb, "در حال بارگذاری بازیکنان تیم...")
                players = await asyncio.to_thread(list_pl_team_players, tid)
                psize = 8
                tpages = max(1, (len(players) + psize - 1) // psize)
                chunk = players[:psize]
                rows_k = [
                    [InlineKeyboardButton(text=f"{p['web_name']} ({p['pos']} • {p['goals']}G/{p['assists']}A)", callback_data=f"{pref}:pick:sel_p1:{p['id']}")]
                    for p in chunk
                ]
                if tpages > 1:
                    rows_k.append([
                        InlineKeyboardButton(text=f"1/{tpages}", callback_data=f"{pref}:noop"),
                        InlineKeyboardButton(text="➡️ بعد", callback_data=f"{pref}:pick:p1:{tid}:2"),
                    ])
                rows_k.append([InlineKeyboardButton(text="↩️ تغییر تیم", callback_data=f"{pref}:pick:t1:1")])
                lbl_p = "بازیکن اول را انتخاب کنید:" if card_kind == "h2h_players" else "بازیکن مورد نظر را انتخاب کنید:"
                await cb.message.edit_text(
                    f"{spec['icon']} <b>{lbl_p}</b> (صفحه 1/{tpages})",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows_k),
                )
                return

            if step == "sel_t2":
                t2_id = int(parts[3])
                t1_id = int(pstate.get("t1_id") or 0)
                await _safe_answer(cb, "در حال ساخت تقابل مستقیم دو تیم...")
                built = await asyncio.to_thread(build_pl_h2h_teams_item, t1_id, t2_id)
                await _open_built_item(built)
                return

            if step in ("p1", "p2"):
                tid = int(parts[3])
                page = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 1
                await _safe_answer(cb)
                players = await asyncio.to_thread(list_pl_team_players, tid)
                if step == "p2" and pstate.get("p1_id"):
                    players = [p for p in players if p["id"] != pstate["p1_id"]]
                psize = 8
                tpages = max(1, (len(players) + psize - 1) // psize)
                page = max(1, min(page, tpages))
                chunk = players[(page - 1) * psize : page * psize]
                sel_act = "sel_p1" if step == "p1" else "sel_p2"
                rows_k = [
                    [InlineKeyboardButton(text=f"{p['web_name']} ({p['pos']} • {p['goals']}G/{p['assists']}A)", callback_data=f"{pref}:pick:{sel_act}:{p['id']}")]
                    for p in chunk
                ]
                nav = []
                if page > 1:
                    nav.append(InlineKeyboardButton(text="⬅️ قبل", callback_data=f"{pref}:pick:{step}:{tid}:{page - 1}"))
                nav.append(InlineKeyboardButton(text=f"{page}/{tpages}", callback_data=f"{pref}:noop"))
                if page < tpages:
                    nav.append(InlineKeyboardButton(text="➡️ بعد", callback_data=f"{pref}:pick:{step}:{tid}:{page + 1}"))
                rows_k.append(nav)
                rows_k.append([InlineKeyboardButton(text="↩️ تغییر تیم", callback_data=f"{pref}:pick:{'t1' if step == 'p1' else 'p2t'}:1")])
                lbl_p = "بازیکن دوم را انتخاب کنید:" if step == "p2" else ("بازیکن اول را انتخاب کنید:" if card_kind == "h2h_players" else "بازیکن مورد نظر را انتخاب کنید:")
                await cb.message.edit_text(
                    f"{spec['icon']} <b>{lbl_p}</b> (صفحه {page}/{tpages})",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows_k),
                )
                return

            if step == "sel_p1":
                pid = int(parts[3])
                pstate["p1_id"] = pid
                if card_kind == "h2h_players":
                    await _safe_answer(cb, "بازیکن اول انتخاب شد؛ تیمِ بازیکن دوم را انتخاب کنید.")
                    teams = await asyncio.to_thread(list_pl_teams)
                    psize = 8
                    tpages = max(1, (len(teams) + psize - 1) // psize)
                    chunk = teams[:psize]
                    rows_k = [
                        [InlineKeyboardButton(text=f"#{t['rank']} {t['name']}", callback_data=f"{pref}:pick:p2:{t['id']}:1") for t in chunk[i:i+2]]
                        for i in range(0, len(chunk), 2)
                    ]
                    if tpages > 1:
                        rows_k.append([
                            InlineKeyboardButton(text=f"1/{tpages}", callback_data=f"{pref}:noop"),
                            InlineKeyboardButton(text="➡️ بعد", callback_data=f"{pref}:pick:p2t:2"),
                        ])
                    rows_k.append([InlineKeyboardButton(text="↩️ بازگشت", callback_data=f"{pref}:pick:league")])
                    await cb.message.edit_text(
                        f"{spec['icon']} <b>لیگ برتر انگلیس — تیمِ بازیکن دوم را انتخاب کنید:</b> (صفحه 1/{tpages})",
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows_k),
                    )
                    return
                await _safe_answer(cb, "در حال ساخت کارت بازیکن...")
                built = await asyncio.to_thread(build_pl_fc27_item if card_kind == "player_fc27" else build_pl_profile_item, pid)
                await _open_built_item(built)
                return

            if step == "sel_p2":
                p2_id = int(parts[3])
                p1_id = int(pstate.get("p1_id") or 0)
                await _safe_answer(cb, "در حال ساخت دوئل آماری دو بازیکن...")
                built = await asyncio.to_thread(build_pl_h2h_players_item, p1_id, p2_id)
                await _open_built_item(built)
                return
        except Exception as exc:
            await _safe_answer(cb, "خطا در انتخاب دستی.", show_alert=True)
            try:
                await cb.message.answer(f"❌ خطا در انتخابگر دستی: <code>{html.escape(type(exc).__name__)}: {html.escape(str(exc)[:250])}</code>", parse_mode="HTML")
            except Exception:
                pass


    @modular_router.callback_query(F.data.startswith(f"{pref}:open:"))
    async def _on_open(cb: CallbackQuery) -> None:
        if not tp.is_admin(cb.from_user.id):
            await _safe_answer(cb, "شما مجاز نیستید.", show_alert=True)
            return
        iid = cb.data.split(":", 2)[2]
        it = MODULAR_ITEMS_MAP[card_kind].get(iid)
        if not it:
            await _safe_answer(cb, "آیتم در کش نیست؛ لطفاً لیست را بروزرسانی کنید.", show_alert=True)
            return
        await _safe_answer(cb, "در حال باز کردن استودیو...")
        if card_kind == "players_rating" and it.get("needs_summary_fetch"):
            from src.xgpedia.providers.players_rating_free import hydrate_players_rating_match
            it = await asyncio.to_thread(hydrate_players_rating_match, it)
            MODULAR_ITEMS_MAP[card_kind][iid] = it
        elif card_kind == "h2h_teams" and not it.get("is_preset") and not it.get("_hydrated"):
            from src.xgpedia.providers.h2h_teams_free import hydrate_h2h_teams_item
            it = await asyncio.to_thread(hydrate_h2h_teams_item, it)
            MODULAR_ITEMS_MAP[card_kind][iid] = it
        elif card_kind == "player_fc27" and not it.get("is_preset") and not it.get("_hydrated"):
            from src.xgpedia.providers.player_fc27_free import hydrate_player_fc27_item
            it = await asyncio.to_thread(hydrate_player_fc27_item, it)
            MODULAR_ITEMS_MAP[card_kind][iid] = it
        elif card_kind == "h2h_players" and not it.get("is_preset") and not it.get("_hydrated"):
            from src.xgpedia.providers.h2h_players_free import hydrate_h2h_players_item
            it = await asyncio.to_thread(hydrate_h2h_players_item, it)
            MODULAR_ITEMS_MAP[card_kind][iid] = it
        elif card_kind == "top_scorers" and not it.get("is_preset") and not it.get("_hydrated"):
            from src.xgpedia.providers.top_scorers_free import hydrate_top_scorers_item
            it = await asyncio.to_thread(hydrate_top_scorers_item, it)
            MODULAR_ITEMS_MAP[card_kind][iid] = it
        _, mods, miss = _get_slides_and_modules(card_kind, it, "slide1")
        st: dict[str, Any] = {
            "item": it,
            "slide": "slide1",
            "header_mode": spec["default_hm"],
            "fmt": "4:5",
            "modules": mods,
            "missing_modules": miss,
            "mod_page": 1,
        }
        if card_kind == "players_rating":
            st.update({"pitch_mode": "both", "theme": "turf", "kit_mode": True, "fx_mode": True})
        elif card_kind == "standings":
            st.update({"lens": "classic", "table_slice": "top10", "spotlight": None})
        elif card_kind == "injury_lab":
            st["severity"] = (it.get("injury") or {}).get("severity", "out")
        elif card_kind == "player_profile":
            st["theme"] = "classic"
        elif card_kind == "player_fc27":
            st["theme"] = str(it.get("skin") or "signature")
        elif card_kind == "matchday_results":
            st["theme"] = "classic"
        elif card_kind == "quote":
            st["hl_style"] = str(it.get("hlStyle") or "underline")
            st["grade"] = str(it.get("grade") or "cinematic")
        elif card_kind == "debate":
            st["theme"] = "classic"
        elif card_kind == "number_of_day":
            st["theme"] = "lalezar"
        MODULAR_STATES[card_kind][cb.from_user.id] = st
        text, kb = render_modular_customizer_view(card_kind, st)
        await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)

    @modular_router.callback_query(F.data == f"{pref}:back")
    async def _on_back(cb: CallbackQuery) -> None:
        if not tp.is_admin(cb.from_user.id):
            await _safe_answer(cb, "شما مجاز نیستید.", show_alert=True)
            return
        st = MODULAR_STATES[card_kind].get(cb.from_user.id)
        if not st:
            await _safe_answer(cb, "لطفاً دوباره از لیست انتخاب کنید.", show_alert=True)
            return
        await _safe_answer(cb)
        text, kb = render_modular_customizer_view(card_kind, st)
        await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)

    @modular_router.callback_query(F.data.startswith(f"{cpref}:"))
    async def _on_customizer(cb: CallbackQuery, bot: Bot) -> None:
        if not tp.is_admin(cb.from_user.id):
            await _safe_answer(cb, "شما مجاز نیستید.", show_alert=True)
            return
        st = MODULAR_STATES[card_kind].get(cb.from_user.id)
        if not st:
            await _safe_answer(cb, "وضعیت منقضی شده است؛ دوباره از لیست انتخاب کنید.", show_alert=True)
            return
        parts = cb.data.split(":")
        action = parts[1] if len(parts) > 1 else "noop"
        if action == "noop":
            await _safe_answer(cb)
            return

        if action == "sl":
            sid = parts[2]
            st["slide"] = sid
            slides_meta, mods, miss = _get_slides_and_modules(card_kind, st["item"], sid)
            st["modules"], st["missing_modules"] = mods, miss
            sm = next((x for x in slides_meta if x[0] == sid), None)
            if sm:
                if card_kind == "players_rating":
                    st["pitch_mode"] = sm[2]
                elif card_kind == "standings":
                    st["lens"], st["table_slice"], st["header_mode"] = sm[2], sm[3], sm[4]
                elif card_kind in {"injury_lab", "player_profile", "h2h_teams"} and isinstance(sm[2], str):
                    st["header_mode"] = sm[2]
            await _safe_answer(cb, f"اسلاید روی {sid} تنظیم شد.")
        elif action == "hm":
            st["header_mode"] = parts[2]
            await _safe_answer(cb, "سبک هدر تغییر کرد.")
        elif action == "fmt":
            st["fmt"] = parts[2].replace("_", ":")
            await _safe_answer(cb, f"فرمت روی {st['fmt']} تنظیم شد.")
        elif action == "opt" and len(parts) >= 4:
            k, v = parts[2], parts[3]
            key_map = {"pm": "pitch_mode", "th": "theme", "ln": "lens", "slc": "table_slice", "sv": "severity", "sr": "sort_by", "hl": "hl_style", "gr": "grade"}
            if k in key_map:
                st[key_map[k]] = v
            await _safe_answer(cb, "تنظیم اعمال شد.")
        elif action == "tog":
            mid = parts[2]
            t = next((m for m in st["modules"] if m["id"] == mid), None)
            if t:
                if t["enabled"] and sum(1 for m in st["modules"] if m["enabled"]) <= 1:
                    await _safe_answer(cb, "حداقل یک ماژول باید فعال بماند.", show_alert=True)
                    return
                t["enabled"] = not t["enabled"]
                st["slide"] = "custom"
                await _safe_answer(cb, f"{t['title_fa']}: {'فعال' if t['enabled'] else 'غیرفعال'}")
        elif action == "sp":
            mid = parts[2]
            t = next((m for m in st["modules"] if m["id"] == mid), None)
            if t and t.get("can_half", False):
                t["span"] = "full" if t.get("span") == "half" else "half"
                t["half"] = t["span"] == "half"
                st["slide"] = "custom"
                await _safe_answer(cb, f"عرض ماژول: {'نیم‌عرض ½' if t['span'] == 'half' else 'تمام‌عرض ۱'}")
        elif action in ("up", "dn"):
            mid = parts[2]
            ml = st["modules"]
            idx = next((i for i, m in enumerate(ml) if m["id"] == mid), -1)
            if action == "up" and idx > 0:
                ml[idx - 1], ml[idx] = ml[idx], ml[idx - 1]
                st["slide"] = "custom"
                await _safe_answer(cb, "⬆️ یک ردیف بالا رفت.")
            elif action == "dn" and 0 <= idx < len(ml) - 1:
                ml[idx + 1], ml[idx] = ml[idx], ml[idx + 1]
                st["slide"] = "custom"
                await _safe_answer(cb, "⬇️ یک ردیف پایین رفت.")
            else:
                await _safe_answer(cb)
                return
        elif action == "mp":
            st["mod_page"] = max(1, int(parts[2])) if len(parts) > 2 and parts[2].isdigit() else 1
            await _safe_answer(cb)
        elif action == "tpl_save":
            from src.xgpedia.publishers import telegram_bot as tb
            tb._AWAITING_TEMPLATE_NAME[cb.from_user.id] = card_kind
            await _safe_answer(cb, "نام قالب را بفرستید.")
            await cb.message.answer(
                f"💾 <b>ذخیرهٔ چینش فعلی {html.escape(spec['title'])}</b>\n"
                "یک نام کوتاه برای این قالب بنویسید یا برای انصراف <code>لغو</code> بفرستید:",
                parse_mode="HTML",
            )
            return
        elif action == "tpl_list":
            tpls = list_layout_templates(card_kind)
            await _safe_answer(cb)
            if not tpls:
                await cb.message.answer("📂 هنوز قالبی ذخیره نکرده‌اید. ابتدا روی «💾 ذخیره قالب» بزنید.")
                return
            t_rows = [
                [
                    InlineKeyboardButton(text=f"📌 {tp_it['name']} ({tp_it.get('fmt', '4:5')})", callback_data=f"{cpref}:tpl_use:{idx}"),
                    InlineKeyboardButton(text="🗑", callback_data=f"{cpref}:tpl_del:{idx}"),
                ]
                for idx, tp_it in enumerate(tpls)
            ]
            t_rows.append([InlineKeyboardButton(text="↩️ بازگشت به کاستومایزر", callback_data=f"{cpref}:tpl_back")])
            await cb.message.edit_text(
                f"📂 <b>قالب‌های ذخیره‌شده {html.escape(spec['title'])} ({len(tpls)} از {MAX_SAVED_TEMPLATES})</b>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=t_rows),
            )
            return
        elif action == "tpl_use":
            tpls = list_layout_templates(card_kind)
            idx = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else -1
            if 0 <= idx < len(tpls):
                tpl = tpls[idx]
                st["fmt"] = tpl.get("fmt", st["fmt"])
                st["header_mode"] = tpl.get("header_mode", st["header_mode"])
                st["modules"] = apply_template_to_modules(st["modules"], tpl)
                st["slide"] = "custom"
                await _safe_answer(cb, f"✅ قالب «{tpl['name']}» اعمال شد!")
            else:
                await _safe_answer(cb, "قالب یافت نشد.", show_alert=True)
        elif action == "tpl_del":
            idx = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else -1
            delete_layout_template(card_kind, idx)
            await _safe_answer(cb, "🗑 قالب حذف شد.")
        elif action == "tpl_back":
            await _safe_answer(cb)
        elif action == "build":
            from src.xgpedia.publishers import telegram_bot as tb
            await _safe_answer(cb, f"در حال ساخت کارت {spec['title']}...")
            lbl = _item_label(card_kind, st["item"])[:65]
            wait_msg = await cb.message.answer(f"⏳ در حال ساخت کارت {spec['icon']} <b>{html.escape(lbl)}</b> ({st['slide']} | {st['fmt']})...", parse_mode="HTML")

            async def _progress(msg_text: str) -> None:
                try:
                    await wait_msg.edit_text(f"{msg_text}\n{spec['icon']} <b>{html.escape(lbl)}</b>", parse_mode="HTML")
                except TelegramBadRequest:
                    pass

            enabled_ids = [m["id"] for m in st["modules"] if m["enabled"]]
            try:
                if card_kind == "players_rating":
                    res = await tw.generate_players_rating_post_async(
                        st["item"], slide=st["slide"], header_mode=st["header_mode"], fmt=st["fmt"],
                        pitch_mode=st.get("pitch_mode"), theme=st.get("theme", "turf"),
                        kit_mode=st.get("kit_mode", True), fx_mode=st.get("fx_mode", True),
                        enabled_modules=enabled_ids, custom_modules=st["modules"], progress_cb=_progress,
                    )
                elif card_kind == "standings":
                    res = await tw.generate_standings_post_async(
                        st["item"], slide=st["slide"], header_mode=st["header_mode"], fmt=st["fmt"],
                        lens=st.get("lens"), table_slice=st.get("table_slice"), spotlight=st.get("spotlight"),
                        enabled_modules=enabled_ids, custom_modules=st["modules"], progress_cb=_progress,
                    )
                elif card_kind == "injury_lab":
                    res = await tw.generate_injury_post_async(
                        st["item"], slide=st["slide"], header_mode=st["header_mode"], fmt=st["fmt"],
                        severity_override=st.get("severity"),
                        enabled_modules=enabled_ids, custom_modules=st["modules"], progress_cb=_progress,
                    )
                elif card_kind == "h2h_teams":
                    res = await tw.generate_h2h_teams_post_async(
                        st["item"], slide=st["slide"], header_mode=st["header_mode"], fmt=st["fmt"],
                        theme=st.get("theme", "classic"), custom_modules=st["modules"], progress_cb=_progress,
                    )
                elif card_kind == "player_fc27":
                    res = await tw.generate_player_fc27_post_async(
                        st["item"], slide=st["slide"], header_mode=st["header_mode"], fmt=st["fmt"],
                        theme=st.get("theme"), custom_modules=st["modules"], progress_cb=_progress,
                    )
                elif card_kind == "h2h_players":
                    res = await tw.generate_h2h_players_post_async(
                        st["item"], slide=st["slide"], header_mode=st["header_mode"], fmt=st["fmt"],
                        theme=st.get("theme", "classic"), custom_modules=st["modules"], progress_cb=_progress,
                    )
                elif card_kind == "top_scorers":
                    res = await tw.generate_top_scorers_post_async(
                        st["item"], slide=st["slide"], header_mode=st["header_mode"], fmt=st["fmt"],
                        theme=st.get("theme", "gold"), sort_by=st.get("sort_by", "goals"),
                        custom_modules=st["modules"], progress_cb=_progress,
                    )
                elif card_kind == "matchday_results":
                    res = await tw.generate_matchday_results_post_async(
                        st["item"], slide=st["slide"], header_mode=st["header_mode"], fmt=st["fmt"],
                        theme=st.get("theme", "classic"), custom_modules=st["modules"], progress_cb=_progress,
                    )
                elif card_kind == "quote":
                    res = await tw.generate_quote_post_async(
                        st["item"], slide=st["slide"], header_mode=st["header_mode"], fmt=st["fmt"],
                        hl_style=st.get("hl_style", "underline"), grade=st.get("grade", "cinematic"),
                        custom_modules=st["modules"], progress_cb=_progress,
                    )
                elif card_kind == "debate":
                    res = await tw.generate_debate_post_async(
                        st["item"], slide=st["slide"], header_mode=st["header_mode"], fmt=st["fmt"],
                        theme=st.get("theme", "classic"), custom_modules=st["modules"], progress_cb=_progress,
                    )
                elif card_kind == "number_of_day":
                    res = await tw.generate_number_of_day_post_async(
                        st["item"], slide=st["slide"], header_mode=st["header_mode"], fmt=st["fmt"],
                        theme=st.get("theme", "lalezar"), custom_modules=st["modules"], progress_cb=_progress,
                    )
                else:
                    res = await tw.generate_player_profile_post_async(
                        st["item"], slide=st["slide"], header_mode=st["header_mode"], fmt=st["fmt"],
                        theme=st.get("theme", "classic"),
                        enabled_modules=enabled_ids, custom_modules=st["modules"], progress_cb=_progress,
                    )

            except Exception as exc:
                await wait_msg.edit_text(f"❌ خطا در ساخت کارت {spec['title']}:\n<code>{html.escape(type(exc).__name__)}: {html.escape(str(exc)[:300])}</code>", parse_mode="HTML")
                return
            if not res.ok:
                await wait_msg.edit_text(html.escape(res.format_error_fa())[:3800], parse_mode="HTML")
                return
            await tb._send_post_preview(
                bot, cb.from_user.id, res, wait_msg,
                note=f"✅ کارت {spec['title']} آماده شد (پست #{res.post_id} | {st['slide']} | {st['fmt']}).",
            )
            return

        text, kb = render_modular_customizer_view(card_kind, st)
        try:
            await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except TelegramBadRequest:
            pass


for _ck in CARD_SPECS:
    _register_card_handlers(_ck)
