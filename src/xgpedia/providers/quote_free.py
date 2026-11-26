"""موتور جستجوی زنده و پیشنهاد نقل‌قول‌های مهم فوتبال (۱۰۰٪ رایگان، بدون `requests`).

منابع زنده و معتبر فوتبال (Association Football / Soccer ONLY):
  1. BBC Sport Football RSS (`https://feeds.bbci.co.uk/sport/football/rss.xml`)
  2. The Guardian Football RSS (`https://www.theguardian.com/football/rss`)
  3. Sky Sports Football RSS (`https://www.skysports.com/rss/12040`)
  4. ESPN Soccer Live News API (`eng.1`, `uefa.champions`, `esp.1`)
  5. پریست‌های آماده (`config/quote_presets.json`) فقط از طریق دکمهٔ فرعی پریست‌ها

قابلیت‌ها:
  - استخراج خودکار نقل‌قول‌های مستقیم و مهم از تیترها، خلاصه‌ها و پاراگراف‌های واقعی خبر
  - امتیازدهی هوشمند تناسب نقل‌قول با قالب کارت (`fit_score`) و پیشنهاد بهترین نقل‌قول‌های روز
  - تشخیص گوینده (سرمربی/بازیکن)، باشگاه، کد ۳ حرفی، رنگ و لوگوی رسمی لیگ برتر (`pl_badges_free`)
  - جفت‌سازی خودکار دو نقل‌قول زنده برای اسلاید ۵ (`دوئل نقل‌قول VS`)
  - افزودن داده‌های واقعی زنده از FPL (در صورت وجود؛ با رعایت کامل `null ≠ 0`)
  - ترجمه و هایلایت خودکار `*کلمه کلیدی*` در مرحلهٔ hydrate
"""
from __future__ import annotations

import base64
import hashlib
import html as _html
import json
import logging
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.xgpedia.config import ROOT
from src.xgpedia.providers.breaking_news_free import (
    _format_pub_jalali,
    _looks_mostly_english,
    upgrade_news_image_url,
)

log = logging.getLogger(__name__)

PRESETS_PATH = ROOT / "config" / "quote_presets.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

RSS_QUOTE_FEEDS: list[tuple[str, str, str]] = [
    ("BBC Sport", "https://feeds.bbci.co.uk/sport/football/rss.xml", "BBC SPORT • FOOTBALL QUOTE"),
    ("The Guardian", "https://www.theguardian.com/football/rss", "THE GUARDIAN • FOOTBALL QUOTE"),
    ("Sky Sports", "https://www.skysports.com/rss/12040", "SKY SPORTS • FOOTBALL QUOTE"),
]

ESPN_QUOTE_FEEDS: list[tuple[str, str, str]] = [
    ("eng.1", "لیگ برتر انگلیس", "PREMIER LEAGUE • LIVE QUOTE"),
    ("uefa.champions", "لیگ قهرمانان اروپا", "CHAMPIONS LEAGUE • LIVE QUOTE"),
    ("uefa.europa", "لیگ اروپا", "EUROPA LEAGUE • LIVE QUOTE"),
    ("esp.1", "لالیگا اسپانیا", "LALIGA • LIVE QUOTE"),
]

_NON_SOCCER_BLOCK = (
    "nfl", "nba", "mlb", "nhl", "cricket", "rugby", "tennis", "wimbledon",
    "formula 1", "f1 ", "ufc", "boxing", "golf", "snooker", "darts", "cycling",
    "super bowl", "quarterback", "touchdown", "innings", "wicket",
)

# نقشهٔ چهره‌های شاخص فوتبال (سرمربیان و ستارگان) برای تشخیص دقیق گوینده، سمت فارسی، باشگاه و رنگ
# (english_key) -> (persian_name, role_fa, club_code, color, competition_fa, watermark)
SPEAKER_DB: dict[str, tuple[str, str, str, str, str, str]] = {
    "mikel arteta": ("میکل آرتتا", "سرمربی آرسنال", "ARS", "#EF0107", "لیگ برتر انگلیس", "CONTROL"),
    "arteta": ("میکل آرتتا", "سرمربی آرسنال", "ARS", "#EF0107", "لیگ برتر انگلیس", "CONTROL"),
    "pep guardiola": ("پپ گواردیولا", "سرمربی منچسترسیتی", "MCI", "#6CABDD", "لیگ برتر انگلیس", "SPACE"),
    "guardiola": ("پپ گواردیولا", "سرمربی منچسترسیتی", "MCI", "#6CABDD", "لیگ برتر انگلیس", "SPACE"),
    "arne slot": ("آرنه اسلوت", "سرمربی لیورپول", "LIV", "#C8102E", "لیگ برتر انگلیس", "INTENSITY"),
    "slot": ("آرنه اسلوت", "سرمربی لیورپول", "LIV", "#C8102E", "لیگ برتر انگلیس", "INTENSITY"),
    "ruben amorim": ("روبن آموریم", "سرمربی منچستریونایتد", "MUN", "#DA291C", "لیگ برتر انگلیس", "SYSTEM"),
    "amorim": ("روبن آموریم", "سرمربی منچستریونایتد", "MUN", "#DA291C", "لیگ برتر انگلیس", "SYSTEM"),
    "enzo maresca": ("انزو مارسکا", "سرمربی چلسی", "CHE", "#38BDF8", "لیگ برتر انگلیس", "PROCESS"),
    "maresca": ("انزو مارسکا", "سرمربی چلسی", "CHE", "#38BDF8", "لیگ برتر انگلیس", "PROCESS"),
    "ange postecoglou": ("آنج پوستکوگلو", "سرمربی تاتنهام", "TOT", "#CBD5E1", "لیگ برتر انگلیس", "ATTACK"),
    "postecoglou": ("آنج پوستکوگلو", "سرمربی تاتنهام", "TOT", "#CBD5E1", "لیگ برتر انگلیس", "ATTACK"),
    "unai emery": ("اونای امری", "سرمربی استون ویلا", "AVL", "#A855F7", "لیگ برتر انگلیس", "TACTICS"),
    "emery": ("اونای امری", "سرمربی استون ویلا", "AVL", "#A855F7", "لیگ برتر انگلیس", "TACTICS"),
    "eddie howe": ("ادی هاو", "سرمربی نیوکاسل", "NEW", "#E2E8F0", "لیگ برتر انگلیس", "PRESS"),
    "thomas frank": ("توماس فرانک", "سرمربی لیگ برتر", "BRE", "#E30613", "لیگ برتر انگلیس", "FOCUS"),
    "oliver glasner": ("الیور گلاسنر", "سرمربی کریستال پالاس", "CRY", "#3B82F6", "لیگ برتر انگلیس", "TRANSITION"),
    "andoni iraola": ("آندونی ایرائولا", "سرمربی بورنموث", "BOU", "#DA291C", "لیگ برتر انگلیس", "PRESS"),
    "nuno espirito santo": ("نونو اسپیریتو سانتو", "سرمربی لیگ برتر", "NFO", "#E53233", "لیگ برتر انگلیس", "COUNTER"),
    "david moyes": ("دیوید مویس", "سرمربی اورتون", "EVE", "#38BDF8", "لیگ برتر انگلیس", "GRIT"),
    "thomas tuchel": ("توماس توخل", "سرمربی تیم ملی انگلیس", "ENG", "#E62E45", "تیم ملی انگلیس", "VISION"),
    "tuchel": ("توماس توخل", "سرمربی تیم ملی انگلیس", "ENG", "#E62E45", "تیم ملی انگلیس", "VISION"),
    "carlo ancelotti": ("کارلو آنچلوتی", "سرمربی فوتبال اروپا", "RMA", "#F59E0B", "لالیگا اسپانیا", "GLORY"),
    "ancelotti": ("کارلو آنچلوتی", "سرمربی فوتبال اروپا", "RMA", "#F59E0B", "لالیگا اسپانیا", "GLORY"),
    "xabi alonso": ("ژابی آلونسو", "سرمربی رئال مادرید", "RMA", "#F59E0B", "لالیگا اسپانیا", "CONTROL"),
    "hansi flick": ("هانسی فلیک", "سرمربی بارسلونا", "BAR", "#E62E45", "لالیگا اسپانیا", "HIGHLINE"),
    "flick": ("هانسی فلیک", "سرمربی بارسلونا", "BAR", "#E62E45", "لالیگا اسپانیا", "HIGHLINE"),
    "diego simeone": ("دیگو سیمئونه", "سرمربی اتلتیکو مادرید", "ATM", "#E62E45", "لالیگا اسپانیا", "FIGHT"),
    "simeone": ("دیگو سیمئونه", "سرمربی اتلتیکو مادرید", "ATM", "#E62E45", "لالیگا اسپانیا", "FIGHT"),
    "luis enrique": ("لوئیس انریکه", "سرمربی پاری‌سن‌ژرمن", "PSG", "#38BDF8", "لیگ قهرمانان اروپا", "TEMPO"),
    "vincent kompany": ("ونسان کمپانی", "سرمربی بایرن مونیخ", "BAY", "#DC052D", "بوندس‌لیگا آلمان", "DOMINATE"),
    "simone inzaghi": ("سیمونه اینزاگی", "سرمربی فوتبال اروپا", "INT", "#3B82F6", "سری آ ایتالیا", "BALANCE"),
    "antonio conte": ("آنتونیو کونته", "سرمربی ناپولی", "NAP", "#38BDF8", "سری آ ایتالیا", "MENTALITY"),
    "mauricio pochettino": ("مائوریسیو پوچتینو", "سرمربی فوتبال", "XGP", "#38BDF8", "فوتبال جهان", "PRESS"),
    "pochettino": ("مائوریسیو پوچتینو", "سرمربی فوتبال", "XGP", "#38BDF8", "فوتبال جهان", "PRESS"),
    "jurgen klopp": ("یورگن کلوپ", "سرمربی و مدیر فوتبال", "LIV", "#C8102E", "فوتبال اروپا", "METAL"),
    "klopp": ("یورگن کلوپ", "سرمربی و مدیر فوتبال", "LIV", "#C8102E", "فوتبال اروپا", "METAL"),
    "jose mourinho": ("ژوزه مورینیو", "سرمربی فوتبال اروپا", "XGP", "#F59E0B", "فوتبال اروپا", "SPECIAL"),
    "mourinho": ("ژوزه مورینیو", "سرمربی فوتبال اروپا", "XGP", "#F59E0B", "فوتبال اروپا", "SPECIAL"),
    # Players
    "erling haaland": ("ارلینگ هالند", "مهاجم منچسترسیتی", "MCI", "#6CABDD", "لیگ برتر انگلیس", "HUNGER"),
    "haaland": ("ارلینگ هالند", "مهاجم منچسترسیتی", "MCI", "#6CABDD", "لیگ برتر انگلیس", "HUNGER"),
    "mohamed salah": ("محمد صلاح", "ستاره لیورپول", "LIV", "#C8102E", "لیگ برتر انگلیس", "KING"),
    "salah": ("محمد صلاح", "ستاره لیورپول", "LIV", "#C8102E", "لیگ برتر انگلیس", "KING"),
    "bukayo saka": ("بوکایو ساکا", "وینگر آرسنال", "ARS", "#EF0107", "لیگ برتر انگلیس", "STARBOY"),
    "saka": ("بوکایو ساکا", "وینگر آرسنال", "ARS", "#EF0107", "لیگ برتر انگلیس", "STARBOY"),
    "cole palmer": ("کول پالمر", "ستاره چلسی", "CHE", "#38BDF8", "لیگ برتر انگلیس", "COLD"),
    "palmer": ("کول پالمر", "ستاره چلسی", "CHE", "#38BDF8", "لیگ برتر انگلیس", "COLD"),
    "bruno fernandes": ("برونو فرناندش", "کاپیتان منچستریونایتد", "MUN", "#DA291C", "لیگ برتر انگلیس", "LEADER"),
    "martin odegaard": ("مارتین اودگارد", "کاپیتان آرسنال", "ARS", "#EF0107", "لیگ برتر انگلیس", "VISION"),
    "virgil van dijk": ("ویرجیل فن دایک", "کاپیتان لیورپول", "LIV", "#C8102E", "لیگ برتر انگلیس", "WALL"),
    "van dijk": ("ویرجیل فن دایک", "کاپیتان لیورپول", "LIV", "#C8102E", "لیگ برتر انگلیس", "WALL"),
    "declan rice": ("دکلان رایس", "هافبک آرسنال", "ARS", "#EF0107", "لیگ برتر انگلیس", "ENGINE"),
    "alexander isak": ("الکساندر ایساک", "مهاجم لیگ برتر", "LIV", "#C8102E", "لیگ برتر انگلیس", "CLINICAL"),
    "rodri": ("رودری", "هافبک منچسترسیتی", "MCI", "#6CABDD", "لیگ برتر انگلیس", "BRAIN"),
    "phil foden": ("فیل فودن", "ستاره منچسترسیتی", "MCI", "#6CABDD", "لیگ برتر انگلیس", "MAGIC"),
    "kylian mbappe": ("کیلیان امباپه", "مهاجم رئال مادرید", "RMA", "#F59E0B", "لالیگا اسپانیا", "SPEED"),
    "mbappe": ("کیلیان امباپه", "مهاجم رئال مادرید", "RMA", "#F59E0B", "لالیگا اسپانیا", "SPEED"),
    "vinicius": ("وینیسیوس جونیور", "وینگر رئال مادرید", "RMA", "#F59E0B", "لالیگا اسپانیا", "FLAIR"),
    "jude bellingham": ("جود بلینگام", "هافبک رئال مادرید", "RMA", "#F59E0B", "لالیگا اسپانیا", "CLUTCH"),
    "bellingham": ("جود بلینگام", "هافبک رئال مادرید", "RMA", "#F59E0B", "لالیگا اسپانیا", "CLUTCH"),
    "lamine yamal": ("لامین یامال", "پدیده بارسلونا", "BAR", "#E62E45", "لالیگا اسپانیا", "FUTURE"),
    "harry kane": ("هری کین", "مهاجم بایرن مونیخ", "BAY", "#DC052D", "بوندس‌لیگا آلمان", "FINISHER"),
    "kane": ("هری کین", "مهاجم بایرن مونیخ", "BAY", "#DC052D", "بوندس‌لیگا آلمان", "FINISHER"),
    "lionel messi": ("لیونل مسی", "اسطوره فوتبال جهان", "ARG", "#38BDF8", "فوتبال جهان", "GOAT"),
    "cristiano ronaldo": ("کریستیانو رونالدو", "اسطوره فوتبال جهان", "POR", "#F59E0B", "فوتبال جهان", "MENTALITY"),
    "mehdi taremi": ("مهدی طارمی", "مهاجم تیم ملی ایران", "IRN", "#10B981", "فوتبال اروپا", "STRIKER"),
}

_CLUB_KEYWORDS: list[tuple[str, str, str, str, str]] = [
    ("arsenal", "آرسنال", "ARS", "#EF0107", "لیگ برتر انگلیس"),
    ("liverpool", "لیورپول", "LIV", "#C8102E", "لیگ برتر انگلیس"),
    ("manchester city", "منچسترسیتی", "MCI", "#6CABDD", "لیگ برتر انگلیس"),
    ("man city", "منچسترسیتی", "MCI", "#6CABDD", "لیگ برتر انگلیس"),
    ("manchester united", "منچستریونایتد", "MUN", "#DA291C", "لیگ برتر انگلیس"),
    ("man utd", "منچستریونایتد", "MUN", "#DA291C", "لیگ برتر انگلیس"),
    ("chelsea", "چلسی", "CHE", "#38BDF8", "لیگ برتر انگلیس"),
    ("tottenham", "تاتنهام", "TOT", "#CBD5E1", "لیگ برتر انگلیس"),
    ("spurs", "تاتنهام", "TOT", "#CBD5E1", "لیگ برتر انگلیس"),
    ("newcastle", "نیوکاسل", "NEW", "#E2E8F0", "لیگ برتر انگلیس"),
    ("aston villa", "استون ویلا", "AVL", "#A855F7", "لیگ برتر انگلیس"),
    ("everton", "اورتون", "EVE", "#38BDF8", "لیگ برتر انگلیس"),
    ("brentford", "برنتفورد", "BRE", "#E30613", "لیگ برتر انگلیس"),
    ("brighton", "برایتون", "BHA", "#38BDF8", "لیگ برتر انگلیس"),
    ("west ham", "وستهام", "WHU", "#C084FC", "لیگ برتر انگلیس"),
    ("crystal palace", "کریستال پالاس", "CRY", "#3B82F6", "لیگ برتر انگلیس"),
    ("bournemouth", "بورنموث", "BOU", "#DA291C", "لیگ برتر انگلیس"),
    ("fulham", "فولام", "FUL", "#E2E8F0", "لیگ برتر انگلیس"),
    ("nottingham forest", "ناتینگهام فارست", "NFO", "#E53233", "لیگ برتر انگلیس"),
    ("real madrid", "رئال مادرید", "RMA", "#F59E0B", "لالیگا اسپانیا"),
    ("barcelona", "بارسلونا", "BAR", "#E62E45", "لالیگا اسپانیا"),
    ("atletico madrid", "اتلتیکو مادرید", "ATM", "#E62E45", "لالیگا اسپانیا"),
    ("bayern munich", "بایرن مونیخ", "BAY", "#DC052D", "بوندس‌لیگا آلمان"),
    ("paris saint-germain", "پاری‌سن‌ژرمن", "PSG", "#38BDF8", "لیگ قهرمانان اروپا"),
    ("psg", "پاری‌سن‌ژرمن", "PSG", "#38BDF8", "لیگ قهرمانان اروپا"),
    ("inter milan", "اینتر میلان", "INT", "#3B82F6", "سری آ ایتالیا"),
    ("ac milan", "آث میلان", "MIL", "#E62E45", "سری آ ایتالیا"),
    ("juventus", "یوونتوس", "JUV", "#E2E8F0", "سری آ ایتالیا"),
]

_QUOTE_VERBS = (
    "says", "said", "insists", "admits", "warns", "believes", "claims",
    "reveals", "vows", "praises", "backs", "hails", "slams", "urges",
    "explains", "reacts", "tells", "confident", "furious", "proud",
)

_HIGHLIGHT_WORDS_EN = (
    "title", "champions", "trophy", "derby", "mentality", "character", "belief",
    "pressure", "winning", "victory", "goals", "tactics", "control", "rhythm",
    "fans", "fight", "proud", "impossible", "dream", "focus", "intensity",
    "quality", "mistakes", "deserve", "top", "best", "history", "future",
)

_QUOTE_CACHE: dict[str, Any] = {"ts": 0.0, "items": []}
_CACHE_TTL_SEC = 900.0


def load_quote_presets(path: Path | None = None) -> list[dict[str, Any]]:
    """بارگذاری ۵ پریست استودیویی از `config/quote_presets.json`."""
    p = path or PRESETS_PATH
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        items = raw.get("presets") if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            return []
        return [dict(it) for it in items if isinstance(it, dict) and it.get("id")]
    except Exception as e:
        log.warning("failed to load quote_presets.json: %s", e)
        return []


def _clean_text(raw: str) -> str:
    s = _html.unescape(str(raw or ""))
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _is_soccer_only(title: str, desc: str) -> bool:
    blob = f" {title} {desc} ".lower()
    return not any(b in blob for b in _NON_SOCCER_BLOCK)


def _auto_highlight_quote(text: str) -> str:
    """افزودن خودکار `*کلمه کلیدی*` به ۱ تا ۲ عبارت اثرگذار نقل‌قول برای افکت ادیتوریال."""
    s = str(text or "").strip()
    if not s or "*" in s:
        return s
    # اگر فارسی است، روی کلمات تاکتیکی/احساسی کلیدی هایلایت بزن
    fa_kw = [
        "قهرمانی", "شخصیت تیم", "امید گل", "پرس از بالا", "مالکیت", "ضدحمله",
        "نتیجه نهایی", "دربی", "هواداران", "ذهنیت برنده", "فشار مسابقه",
        "کیفیت فنی", "ریتم بازی", "یک‌سوم هجومی", "فرصت گل", "پیروزی", "هدف ما",
    ]
    hits = 0
    for kw in fa_kw:
        if kw in s and hits < 2:
            s = s.replace(kw, f"*{kw}*", 1)
            hits += 1
    if hits > 0:
        return s
    # انگلیسی: هایلایت حداکثر ۲ عبارت کلیدی
    for kw in _HIGHLIGHT_WORDS_EN:
        m = re.search(rf"\b({re.escape(kw)}(?:\s+[a-z]+)?)\b", s, flags=re.IGNORECASE)
        if m and hits < 2:
            span = m.group(1)
            s = s[: m.start(1)] + f"*{span}*" + s[m.end(1) :]
            hits += 1
    return s


_DANGLING_EN_END = {
    "to", "of", "in", "on", "at", "for", "with", "by", "from", "and", "or", "but",
    "the", "a", "an", "that", "who", "which", "as", "is", "are", "was", "were",
    "their", "his", "her", "its", "my", "our", "your", "into", "about", "after",
}
_DANGLING_FA_END = {
    "به", "از", "در", "با", "برای", "که", "و", "تا", "یا", "را", "بر", "این", "آن", "یک", "اگر", "روی", "توی",
}


def _is_incomplete_fragment(text: str) -> bool:
    """تشخیص جملات ناقص/بریده (انگلیسی یا فارسی) که به حرف اضافه یا پسوند آپاستروف ختم/شروع می‌شوند."""
    s = str(text or "").replace("*", "").strip(" \"'«».,;:!?-–—")
    if len(s) < 12:
        return True
    if re.match(r"^(?:t|s|re|ve|ll|d|m)\s+", s):
        return True
    words = s.split()
    if not words:
        return True
    last_w = words[-1].lower().strip(".,;:!?\"'«»")
    if last_w in _DANGLING_EN_END or last_w in _DANGLING_FA_END:
        return True
    return False


def _detect_speaker_and_club(title: str, desc: str) -> dict[str, str]:
    blob = f"{title} {desc}".lower()
    # 1. ابتدا استخراج دقیق گوینده از الگوی «Name: ...» یا «Name says/insists/...» (پیش از جستجوی آزاد)
    sp_raw = ""
    m1 = re.match(r"^([A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+){0,2})\s*[:\-–]", title.strip())
    if m1:
        sp_raw = m1.group(1).strip()
    else:
        m2 = re.search(
            r"\b([A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+){1,2})\s+(?:" + "|".join(_QUOTE_VERBS) + r")\b",
            f"{title}. {desc}",
        )
        if m2:
            sp_raw = m2.group(1).strip()

    if sp_raw:
        sp_low = sp_raw.lower()
        for key in sorted(SPEAKER_DB.keys(), key=len, reverse=True):
            if key == sp_low or re.search(rf"\b{re.escape(key)}\b", sp_low):
                sp_fa, role_fa, code, col, comp_fa, wm = SPEAKER_DB[key]
                if code == "XGP":
                    best_pos = 10**9
                    best_club = None
                    for ck, cfa, ccode, ccol, ccomp in _CLUB_KEYWORDS:
                        pos = blob.find(ck)
                        if 0 <= pos < best_pos:
                            best_pos = pos
                            best_club = (cfa, ccode, ccol, ccomp)
                    if best_club:
                        cfa, code, col, comp_fa = best_club
                        if "فوتبال" in role_fa:
                            role_fa = f"سرمربی • {cfa}"
                return {
                    "speaker": sp_fa,
                    "speaker_en": key.title(),
                    "role": role_fa,
                    "clubCode": code,
                    "color": col,
                    "competition": comp_fa,
                    "watermark": wm,
                    "known_star": "1",
                }

    # 2. اگر گوینده صریح استخراج نشد، جستجوی نام در تیتر/متن با حذف عبارات «under/about/against/than <Name>»
    clean_for_match = re.sub(r"\b(?:under|against|about|than|like|with|from)\s+[A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+)?", "", f"{title}. {desc}")
    clean_low = clean_for_match.lower()
    if not sp_raw:
        for key in sorted(SPEAKER_DB.keys(), key=len, reverse=True):
            if re.search(rf"\b{re.escape(key)}\b", clean_low):
                sp_fa, role_fa, code, col, comp_fa, wm = SPEAKER_DB[key]
                if code == "XGP":
                    best_pos = 10**9
                    best_club = None
                    for ck, cfa, ccode, ccol, ccomp in _CLUB_KEYWORDS:
                        pos = blob.find(ck)
                        if 0 <= pos < best_pos:
                            best_pos = pos
                            best_club = (cfa, ccode, ccol, ccomp)
                    if best_club:
                        cfa, code, col, comp_fa = best_club
                        if "فوتبال" in role_fa:
                            role_fa = f"سرمربی • {cfa}"
                return {
                    "speaker": sp_fa,
                    "speaker_en": key.title(),
                    "role": role_fa,
                    "clubCode": code,
                    "color": col,
                    "competition": comp_fa,
                    "watermark": wm,
                    "known_star": "1",
                }

    # 3. Club detection
    club_fa, club_code, col, comp_fa = "فوتبال اروپا", "XGP", "#E62E45", "فوتبال جهان"
    for ck, cfa, ccode, ccol, ccomp in _CLUB_KEYWORDS:
        if ck in blob:
            club_fa, club_code, col, comp_fa = cfa, ccode, ccol, ccomp
            break

    if sp_raw and sp_raw.lower() not in {"premier league", "champions league", "bbc sport", "sky sports", "the guardian", "manchester united", "manchester city", "real madrid"}:
        try:
            from src.xgpedia.providers.injury_free import transliterate_player_name_fa
            sp_fa = transliterate_player_name_fa(sp_raw)
        except Exception:
            sp_fa = sp_raw
        role = f"اظهارنظر رسمی • {club_fa}"
    else:
        sp_fa = f"چهره شاخص {club_fa}" if club_fa != "فوتبال اروپا" else "نقل‌قول روز فوتبال"
        role = f"گزارش رسانه‌ای • {club_fa}"

    return {
        "speaker": sp_fa,
        "speaker_en": sp_raw or "",
        "role": role,
        "clubCode": club_code,
        "color": col,
        "competition": comp_fa,
        "watermark": "VOICE" if club_code == "XGP" else club_code,
        "known_star": "0",
    }


def extract_quote_candidate(
    *,
    title: str,
    description: str,
    source_name: str,
    source_url: str = "",
    pub_date: str = "",
    image_url: str | None = None,
    ticker: str = "XGPEDIA • LIVE QUOTE",
    default_comp: str | None = None,
) -> dict[str, Any] | None:
    """استخراج و امتیازدهی یک نقل‌قول واقعی فوتبال و سنجش تناسب آن با قالب کارت."""
    t = _clean_text(title)
    d = _clean_text(description)
    if not t or not _is_soccer_only(t, d):
        return None

    combined = f"{t} — {d}" if d else t
    # 1. استخراج نقل‌قول مستقیم داخل گیومه («...» / "..." / “...” / ‘...’ / '...')
    # هر بخش (تیتر و توضیح) جداگانه بررسی می‌شود و آپاستروف داخل کلمات (didn't / side's) هرگز به‌عنوان گیومه تلقی نمی‌شود.
    quote_txt = ""
    is_direct_quote = False
    _segments = [seg for seg in (t, d) if seg]
    patterns = [
        r'["“«]([^"”»]{24,240})["”»]',
        r"(?<![A-Za-z0-9])['‘]([^'’\n]{24,220})['’](?![A-Za-z0-9])",
    ]
    for pat in patterns:
        cands: list[str] = []
        for seg in _segments:
            for m_txt in re.findall(pat, seg):
                cleaned = m_txt.strip(" -–—:;.,")
                # جلوگیری از بریدگی پسوند آپاستروف یا جملات ناقص منتهی به حرف اضافه
                if _is_incomplete_fragment(cleaned):
                    continue
                if len(cleaned) >= 22:
                    cands.append(cleaned)
        if cands:
            best = max(cands, key=lambda x: min(len(x), 150))
            quote_txt = best
            is_direct_quote = True
            break

    # 2. اگر گیومه مستقیم نداشت ولی تیتر الگوی نقل‌قول («Speaker: ...» یا فعل نقل‌قول) دارد
    if not quote_txt:
        low_comb = combined.lower()
        has_verb = any(re.search(rf"\b{v}\b", low_comb) for v in _QUOTE_VERBS)
        has_colon = ":" in t and len(t.split(":", 1)[1].strip()) >= 22
        if not (has_verb or has_colon):
            return None
        if has_colon:
            quote_txt = t.split(":", 1)[1].strip()
        elif len(d) >= 35 and len(d) <= 220:
            quote_txt = d
        else:
            quote_txt = t

    if _is_incomplete_fragment(quote_txt):
        # اگر عبارت استخراج‌شده ناقص بود، جمله کامل description یا title را جایگزین کن
        if d and not _is_incomplete_fragment(d) and len(d) <= 240:
            quote_txt = d
        elif t and not _is_incomplete_fragment(t) and len(t) <= 220:
            quote_txt = t
        else:
            return None
    if len(quote_txt) < 22 or len(quote_txt) > 260:
        return None

    meta = _detect_speaker_and_club(t, d)
    # امتیاز تناسب با قالب کارت نقل‌قول (۰ تا ۱۰۰)
    score = 0
    if is_direct_quote:
        score += 34
    if 40 <= len(quote_txt) <= 175:
        score += 24
    elif 24 <= len(quote_txt) <= 220:
        score += 12
    if meta["known_star"] == "1":
        score += 22
    elif meta["speaker_en"]:
        score += 10
    if image_url:
        score += 10
    if any(k in quote_txt.lower() for k in _HIGHLIGHT_WORDS_EN):
        score += 10

    # فقط نقل‌قول‌های واقعاً مناسب کارت (حداقل امتیاز ۴۰) پیشنهاد شوند
    if score < 40:
        return None

    hid = hashlib.sha1(f"{source_name}|{t}|{quote_txt[:40]}".encode("utf-8", errors="ignore")).hexdigest()[:10]
    comp = default_comp or meta["competition"]
    jdate = _format_pub_jalali(pub_date)
    # انتخاب چیدمان پیشنهادی متناسب با طول نقل‌قول و وجود عکس
    if len(quote_txt) <= 95 and image_url:
        rec_layout = "spotlight"
    elif image_url:
        rec_layout = "magazine"
    else:
        rec_layout = "tactical"

    return {
        "id": f"live_qt_{hid}",
        "is_live": True,
        "fit_score": score,
        "recommended_layout": rec_layout,
        "layout": rec_layout,
        "speaker": meta["speaker"],
        "speaker_en": meta["speaker_en"],
        "role": meta["role"],
        "clubCode": meta["clubCode"],
        "color": meta["color"],
        "secondary": "#FFFFFF",
        "hlStyle": "underline",
        "fontSize": 46 if len(quote_txt) <= 130 else 40,
        "grade": "cinematic",
        "photoZoom": 108,
        "photoY": 18,
        "vignette": 64,
        "photoSrc": upgrade_news_image_url(image_url) or (image_url or ""),
        "photoSrc_raw": str(image_url or ""),
        "competition": comp,
        "context": "نقل‌قول زنده رسانه‌ای",
        "date": jdate,
        "match": t[:72],
        "quote": _auto_highlight_quote(quote_txt),
        "quote_raw_en": quote_txt,
        "context_title": t,
        "context_desc": d,
        "watermark": meta["watermark"],
        "ticker": ticker,
        "source": source_name,
        "source_url": source_url,
        "stats": [],
    }


def _fetch_rss_quotes(source_name: str, url: str, ticker: str, timeout: float = 6.5) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml,application/xml,text/xml"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(500_000)
        root = ET.fromstring(raw)
        items = root.findall(".//item")
        for it in items[:28]:
            title = (it.findtext("title") or "").strip()
            desc = (it.findtext("description") or "").strip()
            link = (it.findtext("link") or "").strip()
            pub = (it.findtext("pubDate") or "").strip()
            img = None
            best_w = -1
            for child in it:
                tag = child.tag.lower()
                if tag.endswith("thumbnail") or tag.endswith("content") or tag == "enclosure":
                    u = child.attrib.get("url")
                    if u and u.startswith("http"):
                        try:
                            w_attr = int(child.attrib.get("width") or 0)
                        except (TypeError, ValueError):
                            w_attr = 0
                        if w_attr > best_w or img is None:
                            best_w = w_attr
                            img = u
            cand = extract_quote_candidate(
                title=title,
                description=desc,
                source_name=source_name,
                source_url=link,
                pub_date=pub,
                image_url=img,
                ticker=ticker,
            )
            if cand:
                out.append(cand)
    except Exception as e:
        log.warning("RSS quote feed failed (%s): %s", source_name, e)
    return out


def _fetch_espn_quotes(league_slug: str, comp_fa: str, ticker: str, timeout: float = 6.5) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_slug}/news?limit=20"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read(500_000).decode("utf-8", errors="replace"))
        for art in (data.get("articles") or [])[:20]:
            if not isinstance(art, dict):
                continue
            title = str(art.get("headline") or "").strip()
            desc = str(art.get("description") or "").strip()
            pub = str(art.get("published") or "").strip()
            links = art.get("links") or {}
            link = str(((links.get("web") or {}).get("href")) or "") if isinstance(links, dict) else ""
            imgs = art.get("images") or []
            img = str(imgs[0].get("url") or "") if (isinstance(imgs, list) and imgs and isinstance(imgs[0], dict)) else None
            cand = extract_quote_candidate(
                title=title,
                description=desc,
                source_name="ESPN Soccer",
                source_url=link,
                pub_date=pub,
                image_url=img,
                ticker=ticker,
                default_comp=comp_fa,
            )
            if cand:
                out.append(cand)
    except Exception as e:
        log.warning("ESPN quote feed failed (%s): %s", league_slug, e)
    return out


def pair_duel_quotes(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """جفت‌سازی خودکار دو نقل‌قول زنده از باشگاه/گوینده متفاوت برای اسلاید ۵ (دوئل VS)."""
    if len(items) < 2:
        return items
    for i, it in enumerate(items):
        if it.get("quote2") and it.get("speaker2"):
            continue
        partner = None
        for j, cand in enumerate(items):
            if i == j:
                continue
            if cand.get("clubCode") != it.get("clubCode") and cand.get("speaker") != it.get("speaker"):
                partner = cand
                break
        if partner is None:
            partner = items[(i + 1) % len(items)]
        c2 = partner.get("color") or "#38BDF8"
        if str(c2).lower() == str(it.get("color") or "").lower():
            c2 = "#38BDF8" if str(c2).upper() != "#38BDF8" else "#F59E0B"
        it["speaker2"] = partner.get("speaker") or "گوینده دوم"
        it["role2"] = partner.get("role") or "واکنش رسانه‌ای"
        it["clubCode2"] = partner.get("clubCode") or "XGP"
        it["color2"] = c2
        it["quote2"] = partner.get("quote") or ""
        it["photoSrc2"] = partner.get("photoSrc") or ""
    return items


def fetch_live_quote_items(*, force_refresh: bool = False, max_items: int = 10) -> list[dict[str, Any]]:
    """جستجوی زنده و پیشنهاد برترین نقل‌قول‌های واقعی فوتبال متناسب با قالب کارت."""
    now = time.time()
    if not force_refresh and _QUOTE_CACHE["items"] and (now - _QUOTE_CACHE["ts"]) < _CACHE_TTL_SEC:
        return [dict(x) for x in _QUOTE_CACHE["items"]]

    from src.xgpedia.core import api_health

    raw_items: list[dict[str, Any]] = []
    for src_name, url, ticker in api_health.rank_items(list(RSS_QUOTE_FEEDS), lambda x: f"quote_rss:{x[0]}", skip_cooling=True):
        _t0 = time.perf_counter()
        got = _fetch_rss_quotes(src_name, url, ticker)
        if got:
            api_health.record_success(f"quote_rss:{src_name}", (time.perf_counter() - _t0) * 1000.0)
            raw_items.extend(got)
        else:
            api_health.record_failure(f"quote_rss:{src_name}", "empty_or_failed", base_cooldown=120.0)
    for slug, comp_fa, ticker in api_health.rank_items(list(ESPN_QUOTE_FEEDS), lambda x: f"quote_espn:{x[0]}", skip_cooling=True):
        _t0 = time.perf_counter()
        got = _fetch_espn_quotes(slug, comp_fa, ticker)
        if got:
            api_health.record_success(f"quote_espn:{slug}", (time.perf_counter() - _t0) * 1000.0)
            raw_items.extend(got)
        else:
            api_health.record_failure(f"quote_espn:{slug}", "empty_or_failed", base_cooldown=120.0)

    # حذف موارد تکراری بر اساس متن نقل‌قول
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for it in sorted(raw_items, key=lambda x: int(x.get("fit_score") or 0), reverse=True):
        key = re.sub(r"[^a-z0-9\u0600-\u06ff]+", "", str(it.get("quote_raw_en") or it.get("quote") or "").lower())[:48]
        if not key or key in seen:
            continue
        seen.add(key)
        uniq.append(it)
        if len(uniq) >= max_items:
            break

    pair_duel_quotes(uniq)
    if uniq:
        _QUOTE_CACHE["ts"] = now
        _QUOTE_CACHE["items"] = [dict(x) for x in uniq]
    return uniq


def list_all_quote_items(*, include_live: bool = True, force_refresh: bool = False) -> dict[str, list[dict[str, Any]]]:
    """برگرداندن جداگانه لیست زنده و پریست‌ها (بدون قاطی کردن پریست در دیتای زنده)."""
    presets = load_quote_presets()
    live = fetch_live_quote_items(force_refresh=force_refresh) if include_live else []
    return {"live": live, "presets": presets}


def _download_image_data_uri(url: str | None, timeout: float = 6.0) -> str:
    u = str(url or "").strip()
    if not u:
        return ""
    if u.startswith("data:image/"):
        return u
    if not u.startswith(("http://", "https://")):
        return ""
    try:
        req = urllib.request.Request(u, headers={"User-Agent": USER_AGENT, "Accept": "image/*,*/*;q=0.8"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(4 * 1024 * 1024)
            if len(raw) < 1500:
                return ""
            ctype = str(resp.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip().lower()
            if not ctype.startswith("image/"):
                ctype = "image/jpeg"
            return f"data:{ctype};base64,{base64.b64encode(raw).decode('ascii')}"
    except Exception:
        return ""


_CLUB_CODE_TO_LEAGUE_HINT: dict[str, tuple[str, str]] = {
    "RMA": ("esp.1", "real madrid"),
    "BAR": ("esp.1", "barcelona"),
    "ATM": ("esp.1", "atletico"),
    "BAY": ("ger.1", "bayern"),
    "BVB": ("ger.1", "dortmund"),
    "LEV": ("ger.1", "leverkusen"),
    "INT": ("ita.1", "inter"),
    "MIL": ("ita.1", "milan"),
    "JUV": ("ita.1", "juventus"),
    "NAP": ("ita.1", "napoli"),
    "PSG": ("fra.1", "paris"),
}


def _attach_real_fpl_stats(item: dict[str, Any]) -> None:
    """افزودن ۳ شاخص آماری واقعی زنده از FPL یا جدول رسمی لیگ‌های معتبر (با رعایت دقیق null ≠ 0)."""
    if item.get("stats"):
        return
    sp_en = str(item.get("speaker_en") or "").lower().strip()
    code = str(item.get("clubCode") or "").upper().strip()

    # 1. لیگ برتر انگلیس (FPL bootstrap — بازیکن یا سرمربی/باشگاه)
    try:
        from src.xgpedia.providers.fpl_free import fetch_fpl_bootstrap
        boot = fetch_fpl_bootstrap()
        if isinstance(boot, dict):
            if sp_en:
                for el in (boot.get("elements") or []):
                    full = f"{el.get('first_name', '')} {el.get('second_name', '')}".lower().strip()
                    web = str(el.get("web_name") or "").lower().strip()
                    if sp_en == full or (len(sp_en) >= 4 and (sp_en in full or sp_en == web)):
                        xg = float(el.get("expected_goals") or 0.0)
                        goals = int(el.get("goals_scored") or 0)
                        assists = int(el.get("assists") or 0)
                        mins = int(el.get("minutes") or 0)
                        if mins > 0:
                            stat2 = {"label": "پاس گل فصل", "val": str(assists)} if (goals == 0 and assists > 0) else {"label": "گل فصل", "val": str(goals)}
                            item["stats"] = [
                                {"label": "امید گل (xG)", "val": f"{xg:.2f}"},
                                stat2,
                                {"label": "دقایق بازی", "val": str(mins)},
                            ]
                            if not item.get("photoSrc") and el.get("code"):
                                item["photoSrc"] = f"https://resources.premierleague.com/premierleague/photos/players/250x250/p{el['code']}.png"
                            return
            if code and len(code) == 3:
                team_obj = next((t for t in (boot.get("teams") or []) if str(t.get("short_name") or "").upper() == code), None)
                if team_obj:
                    tid = team_obj.get("id")
                    t_els = [e for e in (boot.get("elements") or []) if e.get("team") == tid]
                    t_goals = sum(int(e.get("goals_scored") or 0) for e in t_els)
                    t_xg = sum(float(e.get("expected_goals") or 0.0) for e in t_els)
                    t_cs = max((int(e.get("clean_sheets") or 0) for e in t_els), default=0)
                    if t_goals > 0 or t_xg > 0:
                        item["stats"] = [
                            {"label": "گل زده فصل", "val": str(t_goals)},
                            {"label": "امید گل تیم", "val": f"{t_xg:.1f}"},
                            {"label": "کلین‌شیت", "val": str(t_cs)},
                        ]
                        return
    except Exception:
        pass

    # 2. باشگاه‌های سایر لیگ‌های معتبر اروپا (لالیگا، بوندسلیگا، سری‌آ، لیگ ۱) از جدول زنده ESPN/OpenLigaDB
    if code in _CLUB_CODE_TO_LEAGUE_HINT:
        lg_slug, kw = _CLUB_CODE_TO_LEAGUE_HINT[code]
        try:
            rows = []
            if lg_slug == "ger.1":
                from src.xgpedia.providers.open_football_hub import fetch_openligadb_bundesliga_standings
                rows = fetch_openligadb_bundesliga_standings() or []
            else:
                from src.xgpedia.providers.open_football_hub import fetch_wc26_standings
                rows = fetch_wc26_standings(lg_slug) or []
            for r in rows:
                nm = str(r.get("team") or r.get("team_name") or r.get("name") or "").lower()
                if kw in nm:
                    rank = r.get("rank") or r.get("position")
                    pts = r.get("points")
                    gf = r.get("goals_for") or r.get("gf") or r.get("goals")
                    gd = r.get("goal_diff") or r.get("gd")
                    stats_out: list[dict[str, str]] = []
                    if rank is not None:
                        stats_out.append({"label": "رتبه لیگ", "val": f"#{rank}"})
                    if pts is not None:
                        stats_out.append({"label": "امتیاز فصل", "val": str(pts)})
                    if gf is not None:
                        stats_out.append({"label": "گل زده", "val": str(gf)})
                    elif gd is not None:
                        stats_out.append({"label": "تفاضل گل", "val": f"{int(gd):+d}" if str(gd).lstrip("+-").isdigit() else str(gd)})
                    if len(stats_out) >= 2:
                        item["stats"] = stats_out[:3]
                        return
        except Exception:
            pass


def _try_translate_quote_and_header_fa(
    text: str,
    *,
    speaker_fa: str = "",
    competition: str = "",
    context_title: str = "",
    context_desc: str = "",
) -> tuple[str, str]:
    """ترجمه یک‌مرحله‌ای و کامل فارسی نقل‌قول + هدر کوتاه در یک تماس LLM (با جلوگیری از جملات ناقص/بریده)."""
    raw = str(text or "").strip()
    if not raw or not _looks_mostly_english(raw):
        return raw, ""
    clean_raw = raw.replace("*", "").strip()
    try:
        from src.xgpedia.editorial.llm_provider import build_default_llm
        llm = build_default_llm()
        sys_prompt = (
            "تو مترجم و سردبیر ارشد تحریریه فوتبال XGPedia هستی. نقل‌قول انگلیسی زیر را به فارسی روان، دقیق و مجله‌ای ترجمه کن.\n"
            "قوانین اجباری:\n"
            "1) خروجی را فقط به‌صورت یک شیء JSON معتبر با همین کلیدها برگردان:\n"
            '{"status": "ok", "title": "...", "caption": "...", "bullets": [], "source_note": "XGPedia", "uncertainties": []}\n'
            "- `caption`: یک جملهٔ کامل، تمام‌شده و خوانای فارسی برای روی کارت (۴۵ تا ۱۶۰ کاراکتر)؛ دقیقاً ۱ تا ۲ عبارت کلیدی را بین *ستاره* بگذار. هرگز جمله را نیمه‌کاره یا منتهی به حرف اضافه (مثل «به»، «از»، «در»، «که») رها نکن.\n"
            "- `title`: تیتر کوتاه ۴ تا ۷ کلمه‌ای فارسی برای هدر بالای کارت (بدون ستاره و کامل).\n"
            "2) اگر متن نقل‌قول کمی کوتاه بود، از فیلدهای context_title و context_desc برای تکمیل دقیق مفهوم استفاده کن، ولی هیچ آمار یا ادعای جدیدی نساز."
        )
        payload = {
            "quote_en": clean_raw,
            "speaker": speaker_fa,
            "competition": competition,
            "context_title": context_title,
            "context_desc": context_desc,
        }
        draft = llm.generate(sys_prompt, payload)
        cand_q = str(getattr(draft, "caption", "") or "").strip().strip("\"'«»")
        cand_h = str(getattr(draft, "title", "") or "").strip().strip("\"'«»").replace("*", "")
        if cand_q and not _looks_mostly_english(cand_q) and not _is_incomplete_fragment(cand_q):
            return _auto_highlight_quote(cand_q), (cand_h if (cand_h and not _looks_mostly_english(cand_h)) else "")
    except Exception as e:
        log.warning("quote LLM structured translation fallback: %s", e)

    try:
        from src.xgpedia.editorial.llm_provider import generate_text
        prompt = (
            "نقل‌قول فوتبالی زیر را به یک جملهٔ کامل و روان فارسی ترجمه کن (هرگز نیمه‌کاره یا منتهی به حرف اضافه نباشد). "
            "دقیقاً ۱ تا ۲ عبارت کلیدی را بین *ستاره* بگذار. فقط خود جمله را برگردان:\n"
            f"{clean_raw}"
        )
        res = generate_text(prompt, max_tokens=180)
        if res and not _looks_mostly_english(res) and not _is_incomplete_fragment(res):
            return _auto_highlight_quote(res.strip().strip("\"'«»")), ""
    except Exception:
        pass
    return _auto_highlight_quote(raw), ""


def _try_translate_quote_fa(text: str, *, speaker_fa: str = "", competition: str = "") -> str:
    q_fa, _ = _try_translate_quote_and_header_fa(text, speaker_fa=speaker_fa, competition=competition)
    return q_fa


def _try_translate_header_fa(text: str, fallback: str) -> str:
    raw = str(text or "").strip()
    if not raw or not _looks_mostly_english(raw):
        return raw or fallback
    try:
        from src.xgpedia.editorial.llm_provider import build_default_llm
        llm = build_default_llm()
        sys_prompt = (
            "تیتر کوتاه فوتبالی زیر را به فارسی روان (حداکثر ۷ کلمه) برای هدر کارت نقل‌قول ترجمه کن.\n"
            'خروجی فقط JSON معتبر: {"status": "ok", "title": "...", "caption": "...", "bullets": [], "source_note": "", "uncertainties": []}'
        )
        draft = llm.generate(sys_prompt, {"headline_en": raw})
        cand = str(getattr(draft, "title", "") or getattr(draft, "caption", "") or "").strip().strip("\"'«»").replace("*", "")
        if cand and 5 <= len(cand) <= 72 and not _looks_mostly_english(cand):
            return cand
    except Exception:
        pass
    try:
        from src.xgpedia.editorial.llm_provider import generate_text
        prompt = (
            "تیتر کوتاه زیر را برای هدر کارت نقل‌قول فوتبال به فارسی روان (حداکثر ۸ کلمه) ترجمه کن. "
            "فقط خود عبارت فارسی را برگردان:\n"
            f"{raw}"
        )
        res = generate_text(prompt, max_tokens=60)
        if res and len(res.strip()) >= 6 and not _looks_mostly_english(res):
            return res.strip().strip("\"'«»")
    except Exception:
        pass
    return fallback


def _fetch_og_image_from_article(url: str, timeout: float = 5.5) -> str:
    u = str(url or "").strip()
    if not u.startswith(("http://", "https://")):
        return ""
    try:
        req = urllib.request.Request(u, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_html = resp.read(260_000).decode("utf-8", errors="replace")
        for pat in (
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image(?::src)?["\']',
        ):
            m = re.search(pat, raw_html, flags=re.IGNORECASE)
            if m:
                found = _html.unescape(m.group(1).strip())
                if found.startswith(("http://", "https://")):
                    return found
    except Exception:
        pass
    return ""


def _fetch_wikipedia_portrait(person_en: str, timeout: float = 5.0) -> str:
    nm = str(person_en or "").strip()
    if not nm or len(nm) < 4:
        return ""
    try:
        import urllib.parse
        slug = urllib.parse.quote(nm.replace(" ", "_"))
        req = urllib.request.Request(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}",
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        th = (data.get("originalimage") or data.get("thumbnail") or {}).get("source")
        return str(th or "")
    except Exception:
        return ""


def _resolve_photo_data_uri(photo_url: str, raw_url: str, source_url: str, speaker_en: str) -> str:
    """دریافت مطمئن تصویر باکیفیت به‌صورت data URI با زنجیره پشتیبان (og:image HD ← لینک اصلی ← ویکی‌پدیا)."""
    p = _html.unescape(str(photo_url or "").strip())
    r = _html.unescape(str(raw_url or "").strip())
    if p.startswith("data:image/"):
        return p

    # اگر تصویر تامبنیل ریز گاردین باشد، ابتدا og:image باکیفیت (۱۲۰۰px با امضای معتبر) را از صفحه مقاله بگیر
    is_small_guim = "i.guim.co.uk" in p and bool(re.search(r"[?&]width=(?:140|300|460)(?:&|$)", p))
    candidates: list[str] = []
    if is_small_guim and source_url:
        og = _fetch_og_image_from_article(source_url)
        if og:
            candidates.append(og)
    if p:
        candidates.append(p)
    if r and r != p:
        candidates.append(r)

    tried: set[str] = set()
    for cand_u in candidates:
        if not cand_u or cand_u in tried:
            continue
        tried.add(cand_u)
        uri = _download_image_data_uri(cand_u)
        if uri:
            return uri

    # پشتیبان اول: استخراج og:image / twitter:image از صفحه خبر
    if source_url and not is_small_guim:
        og = _fetch_og_image_from_article(source_url)
        if og and og not in tried:
            uri = _download_image_data_uri(og)
            if uri:
                return uri

    # پشتیبان دوم: پرتره ویکی‌پدیا گوینده
    if speaker_en:
        wk_u = _fetch_wikipedia_portrait(speaker_en)
        if wk_u:
            uri = _download_image_data_uri(wk_u)
            if uri:
                return uri
    return ""


def hydrate_quote_item(item: dict[str, Any]) -> dict[str, Any]:
    """تکمیل نهایی آیتم نقل‌قول پیش از رندر آفلاین (عکس base64، آمار واقعی FPL، ترجمه فارسی و لوگوی رسمی)."""
    out = dict(item)
    # ۱) ترجمه یک‌مرحله‌ای فارسی نقل‌قول + هدر در یک تماس LLM (سریع‌تر و کامل‌تر)
    hdr_fa = ""
    if out.get("quote"):
        q_fa, hdr_fa = _try_translate_quote_and_header_fa(
            str(out["quote"]),
            speaker_fa=str(out.get("speaker") or ""),
            competition=str(out.get("competition") or ""),
            context_title=str(out.get("context_title") or ""),
            context_desc=str(out.get("context_desc") or ""),
        )
        out["quote"] = q_fa
    if out.get("match") and _looks_mostly_english(str(out["match"])):
        fb_match = f"{out.get('competition') or 'فوتبال جهان'} • {out.get('context') or 'گفت‌وگوی ویژه'}"
        out["match"] = hdr_fa if (hdr_fa and len(hdr_fa) >= 6) else _try_translate_header_fa(str(out["match"]), fb_match)
    if out.get("ticker") and _looks_mostly_english(str(out["ticker"])):
        out["ticker"] = f"{out.get('competition') or 'فوتبال جهان'} • نقل‌قول روز"
    # ۲) اتصال آمار واقعی FPL / لیگ‌های اروپا در صورت خالی بودن stats (null ≠ 0)
    _attach_real_fpl_stats(out)
    # ۳) بازیابی مطمئن عکس باکیفیت و تبدیل به base64 (با حفظ لینک امضادار گاردین + پشتیبان og:image و ویکی‌پدیا)
    out["photoSrc"] = _resolve_photo_data_uri(
        str(out.get("photoSrc") or ""),
        str(out.get("photoSrc_raw") or ""),
        str(out.get("source_url") or ""),
        str(out.get("speaker_en") or ""),
    )
    if out.get("photoSrc2") and str(out["photoSrc2"]).startswith(("http://", "https://")):
        uri2 = _download_image_data_uri(str(out["photoSrc2"]))
        out["photoSrc2"] = uri2 or ""
    return out
