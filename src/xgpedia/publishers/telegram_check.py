"""دروازهٔ ۳ — بررسی فقط-خواندنی سلامت پیکربندی تلگرام (NEXT_STEPS مرحلهٔ ۶).

پیش از اولین dry-run، سه خطای رایجِ روز صفر با getMe / getChat /
getChatMember پیدا می‌شوند (هیچ پیامی ارسال نمی‌شود):
  ۱) توکن غلط یا ناقص (401 از getMe)
  ۲) ربات ادمینِ کانال نیست (sendPhoto به کانال fail می‌شد)
  ۳) ادمینی که ربات را /start نکرده («chat not found» — همان هشدار D25)

خطوط خروجی عمداً انگلیسی‌اند (سیاست run.py: کنسول ویندوز فارسی را خراب نشان
می‌دهد)؛ معادل فارسی و راه‌حل هر خط در docs/GATE3_RUNBOOK.md هست.
fetch قابل‌تزریق است (همان الگوی transport مرحلهٔ ۲) پس تست‌ها بدون شبکه‌اند.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

# (method, params) -> پاسخ JSON تلگرام ({"ok": true/false, ...})
Fetch = Callable[[str, dict], Awaitable[dict]]


async def check_telegram(
    fetch: Fetch | None,
    *,
    token: str,
    channel_id: str,
    admin_ids: frozenset[int] | set[int],
) -> tuple[bool, list[str]]:
    """بررسی کامل؛ خروجی: (همه‌چیز-سبز؟، خطوط گزارش انگلیسی برای کنسول).

    fetch=None فقط وقتی معنا دارد که env ناقص باشد (قبل از هر تماس شبکه‌ای
    برمی‌گردیم)؛ وگرنه ValueError.
    """
    lines: list[str] = []
    fails = 0

    def ok(msg: str) -> None:
        lines.append(f"[OK]   {msg}")

    def fail(msg: str) -> None:
        nonlocal fails
        fails += 1
        lines.append(f"[FAIL] {msg}")

    def warn(msg: str) -> None:
        lines.append(f"[WARN] {msg}")

    # ── ۱. حضور env — بدون این‌ها تماس شبکه‌ای بی‌معنی است ──
    if not token:
        fail("TELEGRAM_BOT_TOKEN is empty - get one from @BotFather and put it in .env")
    if not channel_id:
        fail("TELEGRAM_CHANNEL_ID is empty - numeric id (-100...) or @username of the channel")
    if not admin_ids:
        fail("ADMIN_TELEGRAM_IDS is empty - your numeric user id(s), comma separated")
    if fails:
        lines.append("-> fill .env first (see .env.example); no network call was made")
        return False, lines
    if fetch is None:  # pragma: no cover — محافظ قرارداد داخلی
        raise ValueError("fetch is required when env vars are present")

    # ── ۲. توکن — getMe ──
    me = await fetch("getMe", {})
    if not me.get("ok"):
        fail(f"bot token rejected (getMe): {me.get('description', 'unknown error')}")
        return False, lines
    bot = me.get("result", {})
    bot_id = bot.get("id")
    ok(f"token valid - bot @{bot.get('username', '?')} (id={bot_id})")

    # ── ۳. کانال — getChat ──
    chat = await fetch("getChat", {"chat_id": channel_id})
    if not chat.get("ok"):
        fail(f"channel not found (getChat): {chat.get('description', '')} -"
             " the bot must be an admin of the channel for this to work")
        return False, lines
    chat_res = chat.get("result", {})
    ctype = chat_res.get("type", "?")
    if ctype == "channel":
        ok(f"channel: '{chat_res.get('title', '?')}' (type=channel, id={chat_res.get('id')})")
    else:
        warn(f"TELEGRAM_CHANNEL_ID is a {ctype}, not a channel - create a channel for public posting")

    # ── ۴. ادمین‌بودن ربات در کانال — getChatMember ──
    member = await fetch("getChatMember", {"chat_id": channel_id, "user_id": bot_id})
    if member.get("ok"):
        status = member.get("result", {}).get("status")
        if status == "administrator":
            ok("bot is an administrator of the channel (can post)")
        elif status == "member":
            fail("bot is only a member - channel settings -> Administrators -> Add admin")
        elif status in ("left", "kicked"):
            fail("bot is not in the channel at all - add it and promote to admin")
        else:
            warn(f"bot status in channel: {status}")
    else:
        fail(f"could not read bot status in channel: {member.get('description', '')}")

    # ── ۵. دسترسی به هر ادمین — getChat(admin) ──
    # ربات فقط به کاربری که با آن /start کرده دسترسی دارد؛ همین‌جا پیدا می‌شود
    reachable: list[int] = []
    for aid in sorted(admin_ids):
        r = await fetch("getChat", {"chat_id": aid})
        if r.get("ok"):
            reachable.append(aid)
            ok(f"admin {aid} is reachable by the bot")
        else:
            warn(f"admin {aid} not reachable ({r.get('description', '')}) -"
                 " open a private chat with the bot and send /start, then retry")
    if not reachable:
        fail("no admin has started the bot - review messages would reach nobody")
    elif len(reachable) < len(set(admin_ids)):
        warn("some admins will NOT get review messages (see above) until they /start the bot")

    all_ok = fails == 0
    if all_ok:
        lines.append("-> all green: next step is 'python run.py publish --post-id N --dry-run' (runbook step 4)")
    else:
        lines.append(f"-> {fails} red item(s) - fix them before the dry-run")
    return all_ok, lines


def make_http_fetch(token: str) -> Fetch:
    """fetch واقعی با httpx — همان الگوی پروایدرها؛ aiogram لازم نیست."""
    import httpx

    async def fetch(method: str, params: dict) -> dict:
        url = f"https://api.telegram.org/bot{token}/{method}"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=params)
            return resp.json()

    return fetch
