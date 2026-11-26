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
POST_TYPE_FA = {"preview": "پیش‌بازی", "post_match": "پس از بازی", "number_of_day": "عدد روز", "on_this_day": "در چنین روزی", "breaking_news": "خبر فوری", "birthday": "تولد اسطوره", "transfer_radar": "رادار نقل‌وانتقالات", "this_or_that": "این یا اون", "players_rating": "نمرات بازیکنان", "standings": "جدول رده‌بندی", "injury_lab": "گزارش مصدومیت", "player_profile": "پروفایل بازیکن", "h2h_teams": "تقابل مستقیم تیم‌ها", "player_fc27": "کارت بازیکن FC27", "h2h_players": "مقایسه دو بازیکن", "top_scorers": "جدول گلزنان", "matchday_results": "نتایج بازی‌های روز", "quote": "نقل‌قول روز", "debate": "مناظره روز", "matchweek_wrapup": "خلاصه هفته و فرم", "shotmap_xg": "نقشه شوت و امید گل", "value_radar": "رادار ارزش بازار", "lineup_injuries": "ترکیب احتمالی و غایبان"}
HASHTAG_BY_TYPE = {
    "preview": "#پیش_بازی",
    "post_match": "#پس_از_بازی",
    "number_of_day": "#عدد_روز",
    "matchweek_wrapup": "#خلاصه_هفته",
    "shotmap_xg": "#نقشه_شوت",
    "value_radar": "#رادار_ارزش_بازار",
    "lineup_injuries": "#ترکیب_احتمالی",
    "on_this_day": "#در_چنین_روزی",
    "breaking_news": "#خبر_فوری",
    "birthday": "#تولدت_مبارک",
    "transfer_radar": "#نقل_و_انتقالات",
    "this_or_that": "#این_یا_اون",
    "players_rating": "#نمرات_بازیکنان",
    "standings": "#جدول_رده_بندی",
    "injury_lab": "#گزارش_پزشکی",
    "player_profile": "#پروفایل_بازیکن",
    "h2h_teams": "#تقابل_مستقیم",
    "player_fc27": "#کارت_FC27",
    "h2h_players": "#مقایسه_بازیکنان",
    "top_scorers": "#کفش_طلا",
    "matchday_results": "#نتایج_فوتبال",
    "quote": "#نقل_قول_فوتبالی",
    "debate": "#مناظره_فوتبالی",
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
    "espn soccer": ("ESPN Soccer", "https://www.espn.com/soccer/"),
    "espn": ("ESPN Soccer", "https://www.espn.com/soccer/"),
    "bbc sport": ("BBC Sport", "https://www.bbc.com/sport/football"),
    "the guardian": ("The Guardian", "https://www.theguardian.com/football"),
    "wikimedia": ("Wikipedia", "https://en.wikipedia.org"),
    "wikipedia": ("Wikipedia", "https://en.wikipedia.org"),
    "wikidata": ("Wikidata / Wikipedia", "https://www.wikidata.org"),
    "thesportsdb": ("TheSportsDB", "https://www.thesportsdb.com"),
    "sky sports": ("Sky Sports", "https://www.skysports.com/transfer-centre"),
    "caughtoffside": ("CaughtOffside", "https://www.caughtoffside.com/"),
    "90min": ("90min", "https://www.90min.com/"),
    "premier league / fpl official": ("Premier League FPL", "https://fantasy.premierleague.com/"),
    "premier league / opta fpl": ("Premier League Opta", "https://fantasy.premierleague.com/"),
    "fpl": ("Premier League FPL", "https://fantasy.premierleague.com/"),
}

_CLUB_HASHTAGS: list[tuple[tuple[str, ...], str]] = [
    (("منچستر یونایتد", "منچستریونایتد", "manchester united", "man utd"), "#منچستریونایتد"),
    (("منچستر سیتی", "منچسترسیتی", "manchester city", "man city"), "#منچسترسیتی"),
    (("لیورپول", "liverpool"), "#لیورپول"),
    (("آرسنال", "arsenal"), "#آرسنال"),
    (("چلسی", "chelsea"), "#چلسی"),
    (("تاتنهام", "tottenham", "spurs"), "#تاتنهام"),
    (("نیوکاسل", "newcastle"), "#نیوکاسل"),
    (("استون ویلا", "aston villa"), "#استون_ویلا"),
    (("رئال مادرید", "real madrid"), "#رئال_مادرید"),
    (("بارسلونا", "بارسا", "barcelona"), "#بارسلونا"),
    (("اتلتیکو مادرید", "اتلتیکو", "atletico"), "#اتلتیکو_مادرید"),
    (("بایرن مونیخ", "بایرن", "bayern"), "#بایرن_مونیخ"),
    (("دورتموند", "dortmund"), "#دورتموند"),
    (("پاری سن ژرمن", "پی‌اس‌جی", "psg", "paris saint-germain"), "#پاری_سن_ژرمن"),
    (("اینتر", "inter milan"), "#اینتر"),
    (("آث میلان", "میلان", "ac milan"), "#آث_میلان"),
    (("یوونتوس", "juventus"), "#یوونتوس"),
    (("ناپولی", "napoli"), "#ناپولی"),
    (("آژاکس", "ajax"), "#آژاکس"),
    (("ایران", "تیم ملی ایران", "iran"), "#تیم_ملی_ایران"),
    (("آرژانتین", "argentina"), "#آرژانتین"),
    (("برزیل", "brazil"), "#برزیل"),
    (("اسپانیا", "spain"), "#اسپانیا"),
    (("فرانسه", "france"), "#فرانسه"),
    (("انگلیس", "england"), "#انگلیس"),
    (("آلمان", "germany"), "#آلمان"),
    (("پرتغال", "portugal"), "#پرتغال"),
]

_COMP_HASHTAGS: list[tuple[tuple[str, ...], str]] = [
    (("لیگ برتر انگلیس", "لیگ برتر", "premier league", "eng.1", "pl"), "#لیگ_برتر_انگلیس"),
    (("لیگ قهرمانان", "champions league", "ucl", "uefa.champions", "cl"), "#لیگ_قهرمانان_اروپا"),
    (("لالیگا", "la liga", "esp.1", "pd"), "#لالیگا"),
    (("سری آ", "serie a", "ita.1", "sa"), "#سری_آ"),
    (("بوندسلیگا", "bundesliga", "ger.1", "bl1"), "#بوندسلیگا"),
    (("لیگ یک فرانسه", "ligue 1", "fra.1", "fl1"), "#لیگ_یک_فرانسه"),
    (("جام جهانی", "world cup"), "#جام_جهانی"),
    (("یورو", "euro 20", "uefa euro"), "#یورو"),
    (("لیگ اروپا", "europa league"), "#لیگ_اروپا"),
]

_NEWS_MODE_HASHTAGS: dict[str, str] = {
    "breaking": "#خبر_فوری",
    "official": "#اعلام_رسمی",
    "transfer": "#نقل_و_انتقالات",
    "exclusive": "#اختصاصی",
    "alert": "#گزارش_پزشکی",
}


def _slug_fa_hashtag(name: str) -> str:
    import re as _re
    s = _re.sub(r"[^\w\u0600-\u06ff\s]", "", str(name or "").strip())
    s = _re.sub(r"\s+", "_", s).strip("_")
    return f"#{s}" if len(s) >= 2 else ""


def _build_relevant_hashtags(post: dict, facts: dict, draft: dict) -> str:
    """ساخت خودکار هشتگ‌های متناسب با نوع کارت، لیگ و تیم‌های مرتبط (قانون دائمی برای همهٔ کارت‌ها)."""
    tags: list[str] = []

    def _add(t: str) -> None:
        t = (t or "").strip()
        if t and t.startswith("#") and t not in tags:
            tags.append(t)

    _add("#XGPedia")
    _add("#فوتبال")

    ptype = str(post.get("post_type") or "").strip()
    base_tag = HASHTAG_BY_TYPE.get(ptype, "")
    if base_tag:
        _add(base_tag)
    if ptype == "post_match":
        _add("#تحلیل_آماری")
    elif ptype == "on_this_day":
        _add("#در_چنین_روزی")
        _add("#تاریخ_فوتبال")
    elif ptype == "breaking_news":
        mode_k = str(draft.get("mode") or (facts.get("mode") if isinstance(facts, dict) else "") or "breaking").lower()
        _add(_NEWS_MODE_HASHTAGS.get(mode_k, "#خبر_فوری"))
    elif ptype == "birthday":
        _add("#تولد_اسطوره")
        if isinstance(facts, dict):
            if facts.get("nameFa"):
                _add(_slug_fa_hashtag(str(facts["nameFa"])))
            if facts.get("club"):
                _add(_slug_fa_hashtag(str(facts["club"])))
    elif ptype == "transfer_radar":
        _add("#رادار_نقل_و_انتقالات")
        if isinstance(facts, dict):
            pl = facts.get("player") if isinstance(facts.get("player"), dict) else {}
            if pl.get("name"):
                _add(_slug_fa_hashtag(str(pl["name"])))
            for side in ("to", "from"):
                co = facts.get(side) if isinstance(facts.get(side), dict) else {}
                if co.get("name"):
                    _add(_slug_fa_hashtag(str(co["name"])))
    elif ptype == "this_or_that":
        _add("#نظرسنجی_فوتبال")
        if isinstance(facts, dict):
            for side in ("a", "b"):
                so = facts.get(side) if isinstance(facts.get(side), dict) else {}
                if so.get("name"):
                    _add(_slug_fa_hashtag(str(so["name"])))
    elif ptype == "players_rating":
        _add("#تحلیل_آماری")
        if isinstance(facts, dict):
            for side in ("home", "away"):
                so = facts.get(side) if isinstance(facts.get(side), dict) else {}
                if so.get("name"):
                    _add(_slug_fa_hashtag(str(so["name"])))
    elif ptype == "standings":
        _add("#جدول_لیگ")
        if isinstance(facts, dict) and facts.get("name"):
            _add(_slug_fa_hashtag(str(facts["name"])))
    elif ptype == "injury_lab":
        _add("#مصدومیت")
        if isinstance(facts, dict):
            pl = facts.get("player") if isinstance(facts.get("player"), dict) else {}
            if pl.get("name"):
                _add(_slug_fa_hashtag(str(pl["name"])))
            if pl.get("club"):
                _add(_slug_fa_hashtag(str(pl["club"])))
    elif ptype == "player_profile":
        _add("#آنالیز_بازیکن")
        if isinstance(facts, dict):
            if facts.get("name"):
                _add(_slug_fa_hashtag(str(facts["name"])))
            if facts.get("club"):
                _add(_slug_fa_hashtag(str(facts["club"])))
    elif ptype == "h2h_teams":
        _add("#تاریخچه_تقابل")
        if isinstance(facts, dict):
            for side in ("home", "away"):
                so = facts.get(side) if isinstance(facts.get(side), dict) else {}
                if so.get("name"):
                    _add(_slug_fa_hashtag(str(so["name"])))
    elif ptype == "player_fc27":
        _add("#کارت_بازیکن")
        if isinstance(facts, dict):
            if facts.get("name"):
                _add(_slug_fa_hashtag(str(facts["name"])))
            if facts.get("club"):
                _add(_slug_fa_hashtag(str(facts["club"])))
    elif ptype == "h2h_players":
        _add("#دوئل_بازیکنان")
        if isinstance(facts, dict):
            for side in ("p1", "p2"):
                so = facts.get(side) if isinstance(facts.get(side), dict) else {}
                if so.get("name"):
                    _add(_slug_fa_hashtag(str(so["name"])))
    elif ptype == "top_scorers":
        _add("#جدول_گلزنان")
        if isinstance(facts, dict) and facts.get("competition"):
            _add(_slug_fa_hashtag(str(facts["competition"])))
    elif ptype == "matchday_results":
        _add("#نتایج_۲۴_ساعت")
        if isinstance(facts, dict) and facts.get("competition"):
            _add(_slug_fa_hashtag(str(facts["competition"])))
    elif ptype == "quote":
        _add("#نقل_قول_روز")
        if isinstance(facts, dict):
            if facts.get("speaker"):
                _add(_slug_fa_hashtag(str(facts["speaker"])))
            if facts.get("competition"):
                _add(_slug_fa_hashtag(str(facts["competition"])))
    elif ptype == "debate":
        _add("#مناظره_روز")
        if isinstance(facts, dict):
            for sk in ("sideA", "sideB"):
                so = facts.get(sk) if isinstance(facts.get(sk), dict) else {}
                if so.get("name"):
                    _add(_slug_fa_hashtag(str(so["name"])))
    elif ptype == "number_of_day":
        _add("#آمار_فوتبال")
        if isinstance(facts, dict) and facts.get("subject"):
            _add(_slug_fa_hashtag(str(facts["subject"])))
    elif ptype == "matchweek_wrapup":
        _add("#فرم_تیم_ها")
        _add("#امید_گل")
    elif ptype == "shotmap_xg":
        _add("#مومنتوم_امید_گل")
        _add("#امید_گل")
    elif ptype == "value_radar":
        _add("#شکار_نقل_و_انتقالات")
        _add("#امید_گل")
    elif ptype == "lineup_injuries":
        _add("#غایبان_مسابقه")
        _add("#لیگ_برتر_انگلیس")

    # استخراج تیم‌ها از facts ساختاریافته (پیش‌بازی / پس‌ازبازی)
    if isinstance(facts, dict):
        for side in ("home", "away"):
            so = facts.get(side)
            if isinstance(so, dict) and so.get("name_fa"):
                _add(_slug_fa_hashtag(str(so["name_fa"])))

    # جستجوی لیگ و باشگاه‌ها در متن عنوان، کپشن و متادیتا
    blob = " ".join([
        str(post.get("title") or ""),
        str(post.get("caption") or ""),
        str(facts.get("comp") or "") if isinstance(facts, dict) else "",
        str((facts.get("competition") or {}).get("name_fa") or "") if isinstance(facts, dict) and isinstance(facts.get("competition"), dict) else "",
        str((facts.get("competition") or {}).get("code") or "") if isinstance(facts, dict) and isinstance(facts.get("competition"), dict) else "",
    ]).lower()

    for kws, htag in _COMP_HASHTAGS:
        if any(kw in blob for kw in kws):
            _add(htag)
            break

    for kws, htag in _CLUB_HASHTAGS:
        if any(kw in blob for kw in kws):
            _add(htag)
        if len(tags) >= 7:
            break

    return " ".join(tags[:7])


def _format_source_html(raw_source: str, facts: dict) -> str:
    """تبدیل نام منبع به هایپرلینک تمیز تلگرام (با اولویت source_url دقیق خبر/سند)."""
    src_obj = facts.get("source") if isinstance(facts, dict) else None
    src_url = ""
    if isinstance(facts, dict):
        for uk in ("source_url", "url", "article_url"):
            cand = str(facts.get(uk) or "").strip()
            if cand.startswith(("http://", "https://")):
                src_url = cand
                break
    if isinstance(src_obj, dict):
        prov = str(src_obj.get("provider") or "").strip()
        if not src_url:
            cand = str(src_obj.get("url") or "").strip()
            if cand.startswith(("http://", "https://")):
                src_url = cand
    elif isinstance(src_obj, str):
        prov = src_obj.strip()
    else:
        prov = ""

    prov_low = prov.lower()
    raw_low = (raw_source or "").lower()
    cleaned = (raw_source or "").split("·")[0].replace("منبع داده:", "").strip()
    label = prov or cleaned

    if src_url and label:
        safe_u = html.escape(src_url, quote=True)
        return f'<i>منبع: <a href="{safe_u}">{html.escape(label)}</a></i>'

    for key, (known_lbl, known_url) in _SOURCE_LINKS.items():
        if key == prov_low or key in raw_low or key in prov_low:
            return f'<i>منبع: <a href="{known_url}">{known_lbl}</a></i>'

    if label:
        return f"<i>منبع: {html.escape(label)}</i>"
    return ""


def _strip_duplicate_headline(raw_cap: str, title_raw: str) -> str:
    """حذف خط اول تکراری کپشن اگر دقیقاً همان تیتر پست باشد."""
    lines = raw_cap.splitlines()
    if not lines:
        return raw_cap
    first = lines[0].strip().lstrip("📰🚨⚡✅🎙️ ").strip()
    t_norm = title_raw.strip().lstrip("📰🚨⚡✅🎙️ ").strip()
    if t_norm and (first == t_norm or first.startswith(t_norm[:35]) or t_norm.startswith(first[:35])):
        rest = "\n".join(lines[1:]).lstrip()
        return rest
    return raw_cap


def _clean_caption_stars(text: str) -> str:
    """حذف ستاره‌های مارک‌داون (*واژه*) از متن کپشن تلگرام تا خروجی تمیز و خوانا باشد."""
    import re as _re
    return _re.sub(r"\*([^*\n]+)\*", r"\1", text or "").replace("*", "")


def _trim_at_sentence(text: str, max_chars: int) -> str:
    """برش تمیز متن روی پایان پاراگراف یا جملهٔ کامل — هرگز وسط کلمه یا جمله نصف نمی‌شود."""
    txt = (text or "").strip()
    if max_chars <= 0:
        return ""
    if len(txt) <= max_chars:
        return txt
    cand = txt[:max_chars]
    # اولویت ۱: پایان یک پاراگراف کامل
    p_idx = cand.rfind("\n\n")
    if p_idx >= int(max_chars * 0.45):
        return cand[:p_idx].rstrip()
    # اولویت ۲: پایان یک جملهٔ کامل (. ؟ !)
    best_s = -1
    for sep in (".", "؟", "!", "؛"):
        idx = cand.rfind(sep)
        if idx > best_s:
            best_s = idx
    if best_s >= int(max_chars * 0.45):
        return cand[: best_s + 1].rstrip()
    # اولویت ۳: پایان خط یا آخرین کلمهٔ کامل + «…»
    nl_idx = cand.rfind("\n")
    if nl_idx >= int(max_chars * 0.55):
        return cand[:nl_idx].rstrip()
    return cand.rsplit(" ", 1)[0].rstrip(" ،؛,:") + "…"


def build_caption(post: dict) -> str:
    """کپشن HTML تلگرام از پست آرشیوشده — همهٔ متن LLM با escape ایمن می‌شود.

    ساختار: تیتر بولد (یک‌بار) + کپشن کامل بدون برش وسط جمله + منبع هایپرلینک + هشتگ‌های متناسب.
    """
    draft = json.loads(post["draft_json"] or "{}")
    title_raw = _clean_caption_stars((post["title"] or draft.get("title") or "").strip())
    title = html.escape(title_raw)
    raw_cap = (post["caption"] or draft.get("caption") or "").strip()
    ptype = post.get("post_type") or ""
    if ptype in ("on_this_day", "breaking_news", "birthday", "transfer_radar", "this_or_that"):
        import re as _re
        raw_cap = _re.sub(r"</?(?:b|i|code)>", "", raw_cap)
        raw_cap = _clean_caption_stars(raw_cap)
    if ptype == "breaking_news":
        raw_cap = _strip_duplicate_headline(raw_cap, title_raw)
    facts = json.loads(post.get("fact_json") or "{}") if isinstance(post, dict) else {}

    if ptype == "breaking_news":
        t_disp = title if title.startswith("📰") else f"📰 {title}"
        title_block = f"<b>{t_disp}</b>"
    elif ptype == "birthday":
        t_disp = title if title.startswith("🎂") else f"🎂 {title}"
        title_block = f"<b>{t_disp}</b>"
    elif ptype == "transfer_radar":
        t_disp = title if title.startswith("📡") else f"📡 {title}"
        title_block = f"<b>{t_disp}</b>"
    elif ptype == "this_or_that":
        t_disp = title if title.startswith("⚔️") else f"⚔️ {title}"
        title_block = f"<b>{t_disp}</b>"
    else:
        title_block = f"<b>{title}</b>"

    src_html = _format_source_html(draft.get("source_note") or "", facts)
    tags = _build_relevant_hashtags(post, facts, draft)

    # برای خبر فوری، طول بدنه را دقیق طوری تنظیم می‌کنیم که همراه با هدر بازبینی، منبع هایپرلینک و هشتگ‌ها
    # همیشه زیر سقف ۱۰۲۴ تلگرام بماند و هرگز وارد برش خام وسط کلمه نشود
    if ptype in ("breaking_news", "birthday", "transfer_radar", "this_or_that") and raw_cap:
        overhead = _utf16_len(title_block) + _utf16_len(src_html) + _utf16_len(tags) + 140  # +140 برای هدر بازبینی و فواصل
        body_budget = max(240, CAPTION_LIMIT - overhead)
        if _utf16_len(html.escape(raw_cap)) > body_budget:
            raw_cap = _trim_at_sentence(raw_cap, body_budget)

    caption = html.escape(raw_cap)
    parts = [title_block]
    if caption:
        parts.append(caption)
    if ptype in ("preview", "pre_match"):
        w_lines = []
        hf, af = facts.get("home") or {}, facts.get("away") or {}
        if hf.get("watchout"):
            w_lines.append(f"• {html.escape(str(hf.get('name_fa', 'میزبان')))}: {html.escape(str(hf['watchout']))}")
        if af.get("watchout"):
            w_lines.append(f"• {html.escape(str(af.get('name_fa', 'میهمان')))}: {html.escape(str(af['watchout']))}")
        if w_lines:
            parts.append("⚠️ <b>باید حواسشون بهش باشه:</b>\n" + "\n".join(w_lines))
    elif ptype == "post_match":
        bullets = [html.escape(str(b).strip()) for b in (draft.get("bullets") or []) if str(b).strip()]
        if bullets:
            parts.append("🎯 <b>روایت آماری و گره تاکتیکی بازی:</b>\n" + "\n".join(f"• {b}" for b in bullets))
    if src_html:
        parts.append(src_html)
    if tags:
        parts.append(tags)
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


def build_auto_poll(post: dict) -> dict | None:
    """ساخت خودکار نظرسنجی تعاملی (Poll) زیر پست‌های پیش‌بازی، مناظره، این یا اون و ترکیب احتمالی."""
    ptype = str(post.get("post_type") or "").strip()
    try:
        facts = json.loads(post.get("fact_json") or "{}")
    except Exception:
        facts = {}
    if not isinstance(facts, dict):
        facts = {}

    if ptype in {"preview", "lineup_injuries"}:
        h = (facts.get("home") or {}).get("name_fa") or (facts.get("home") or {}).get("name") or ""
        a = (facts.get("away") or {}).get("name_fa") or (facts.get("away") or {}).get("name") or ""
        if h and a:
            q = f"📊 پیش‌بینی شما از تقابل {h} × {a} چیست؟"
            return {"question": q[:280], "options": [f"برد {h}"[:95], "تساوی", f"برد {a}"[:95]]}
    elif ptype == "debate":
        sa = (facts.get("sideA") or {}).get("name") or ""
        sb = (facts.get("sideB") or {}).get("name") or ""
        ttl = str(facts.get("title") or post.get("title") or "مناظره روز XGPedia").strip()
        if sa and sb:
            q = f"🔥 {ttl} — رأی شما با کدام طرف است؟"
            return {"question": q[:280], "options": [str(sa)[:95], str(sb)[:95], "هر دو / بستگی دارد"]}
    elif ptype == "this_or_that":
        sa = (facts.get("a") or {}).get("name") or ""
        sb = (facts.get("b") or {}).get("name") or ""
        if sa and sb:
            q = f"⚡ انتخاب شما در دوئل {sa} یا {sb} کدام است؟"
            return {"question": q[:280], "options": [str(sa)[:95], str(sb)[:95]]}
    return None


async def approve_and_publish(
    post_id: int, admin_user_id: int, transport: TelegramTransport,
    channel_id: str | int = "",
    *,
    send_poll: bool = True,
    cross_post: bool = True,
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
    poll_sent = False
    if send_poll and hasattr(transport, "send_poll"):
        poll_spec = build_auto_poll(post)
        if poll_spec:
            try:
                await transport.send_poll(chat_target, poll_spec["question"], poll_spec["options"])
                poll_sent = True
            except Exception:
                poll_sent = False
    omni_results: list[dict] = []
    if cross_post:
        try:
            from src.xgpedia.publishers.omnichannel import broadcast_photo
            outs = await broadcast_photo(image, fit_caption("", post), title=str(post.get("title") or ""))
            omni_results = [{"platform": o.platform, "label_fa": o.label_fa, "ok": o.ok, "error": o.error} for o in outs]
        except Exception:
            omni_results = []
    return {"chat_id": msg.chat_id, "message_id": msg.message_id, "poll_sent": poll_sent, "omnichannel": omni_results}


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
