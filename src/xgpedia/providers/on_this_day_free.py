"""دریافت زنده و رایگان رویدادهای تاریخی فوتبال «در چنین روزی» (On This Day).

منابع ۱۰۰٪ رایگان، بدون نیاز به API Key و در دسترس از ایران:
  1. Wikimedia REST API فارسی (`fa.wikipedia.org/api/rest_v1/feed/onthisday/all/{MM}/{DD}`)
  2. Wikimedia REST API انگلیسی (`en.wikipedia.org/api/rest_v1/feed/onthisday/all/{MM}/{DD}`)
  3. آرشیو مستند محلی (`config/on_this_day_archive.json`) شامل لحظات کلاسیک با تله‌متری و بازسازی تاکتیکی.

قاعدهٔ طلایی `null ≠ 0`: برای رویدادهای زندهٔ ویکی‌پدیا هیچ نتیجه، تماشاگر یا مختصات تاکتیکی جعلی ساخته نمی‌شود.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import urllib.request

from src.xgpedia.config import ROOT as PROJECT_ROOT

log = logging.getLogger(__name__)

ARCHIVE_PATH = PROJECT_ROOT / "config" / "on_this_day_archive.json"
WIKI_USER_AGENT = "XGPediaBot/1.0 (https://t.me/XGPedia; football-analytics-archive)"

_EN_MONTHS = (
    "", "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
)
_FA_MONTHS_GREG = (
    "", "ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن",
    "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر",
)

# کلیدواژه‌های دقیق فوتبال (Association Football) به فارسی و انگلیسی
_FA_FOOTBALL_RE = re.compile(
    r"(فوتبال|جام جهانی|لیگ قهرمانان|فیفا|یوفا|توپ طلا|فوتبالیست|دروازه‌بان|"
    r"تیم ملی فوتبال|باشگاه فوتبال|پلی‌آف جام جهانی|لیگ برتر انگلیس|لالیگا|سری آ|بوندس‌لیگا)",
    re.IGNORECASE,
)
_EN_FOOTBALL_RE = re.compile(
    r"\b(association football|footballer|football player|football manager|football club|"
    r"fifa|uefa|world cup|champions league|premier league|la liga|serie a|bundesliga|"
    r"ballon d'or|fa cup|copa américa|copa america|europa league|soccer|"
    r"real madrid|barcelona|manchester united|liverpool f\.c\.|ac milan|bayern munich|"
    r"arsenal f\.c\.|chelsea f\.c\.|juventus|inter milan|paris saint-germain)\b",
    re.IGNORECASE,
)
# جلوگیری از خطای تشخیص فوتبال آمریکایی/راگبی/استرالیایی
_NON_SOCCER_EXCLUDE_RE = re.compile(
    r"\b(american football|nfl|super bowl|quarterback|touchdown|linebacker|ncaa football|"
    r"australian rules|afl|rugby|canadian football|cfl|gridiron|basketball|nba|tennis|cricket)\b|"
    r"(فوتبال آمریکایی|راگبی|بسکتبال|والیبال|تنیس|کریکت)",
    re.IGNORECASE,
)

# کش حافظه برای جلوگیری از درخواست تکراری در یک روز
_LIVE_CACHE: dict[tuple[int, int], list[dict[str, Any]]] = {}


def load_archive_presets(path: Path | None = None) -> list[dict[str, Any]]:
    """بارگذاری لحظات مستند از `config/on_this_day_archive.json`."""
    p = path or ARCHIVE_PATH
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        events = raw.get("events") if isinstance(raw, dict) else raw
        if not isinstance(events, list):
            return []
        out: list[dict[str, Any]] = []
        for ev in events:
            if isinstance(ev, dict) and ev.get("id"):
                item = dict(ev)
                item.setdefault("verified", True)
                item.setdefault("is_archive", True)
                out.append(item)
        return out
    except Exception as e:
        log.warning("failed to load on_this_day_archive.json: %s", e)
        return []


def _gregorian_to_jalali_str(year: int, month: int, day: int) -> str:
    """تبدیل تاریخ میلادی به شمسی (در صورت عدم دسترسی یا تاریخ خیلی قدیمی، معادل فارسی میلادی برمی‌گرداند)."""
    try:
        if 1925 <= year <= 2100:
            from src.xgpedia.render.cards import jalali_date
            iso = f"{year:04d}-{month:02d}-{day:02d}T12:00:00Z"
            j = jalali_date(iso)
            if j and any(ch in j for ch in "۰۱۲۳۴۵۶۷۸۹0123456789"):
                # حذف نام روز هفته در صورت وجود برای نمایش جمع‌وجور در کپسول تاریخ
                parts = j.split(" ", 1)
                if len(parts) == 2 and parts[0].endswith(("شنبه", "جمعه")):
                    return parts[1].strip()
                return j
    except Exception:
        pass
    m_fa = _FA_MONTHS_GREG[month] if 1 <= month <= 12 else str(month)
    return f"{day} {m_fa} {year}"


def _format_date_en(year: int, month: int, day: int) -> str:
    m_en = _EN_MONTHS[month] if 1 <= month <= 12 else f"{month:02d}"
    return f"{day:02d} {m_en} {year}"


def _is_football_item(text: str, pages: list[dict[str, Any]], lang: str) -> bool:
    blob_parts = [text or ""]
    for pg in (pages or [])[:3]:
        blob_parts.append(str(pg.get("description") or ""))
        blob_parts.append(str(pg.get("extract") or "")[:240])
        titles = pg.get("titles") or {}
        blob_parts.append(str(titles.get("normalized") or pg.get("title") or ""))
    blob = " ".join(blob_parts)
    if _NON_SOCCER_EXCLUDE_RE.search(blob):
        return False
    if lang == "fa":
        return bool(_FA_FOOTBALL_RE.search(blob) or _EN_FOOTBALL_RE.search(blob))
    return bool(_EN_FOOTBALL_RE.search(blob))


def parse_wikipedia_on_this_day_payload(
    payload: dict[str, Any],
    *,
    month: int,
    day: int,
    lang: str = "fa",
    max_items: int = 8,
) -> list[dict[str, Any]]:
    """استخراج و نرمال‌سازی رویدادهای واقعی فوتبال از خروجی Wikimedia REST API.

    بخش‌های `selected`, `events`, و `births` بررسی می‌شوند (اولویت با رویدادهای مسابقه‌ای و سپس زادروز اسطوره‌ها).
    هیچ عدد یا نتیجهٔ جعلی ساخته نمی‌شود (`null ≠ 0`).
    """
    if not isinstance(payload, dict):
        return []

    sections = [
        ("selected", "رویداد برگزیده تاریخ فوتبال", "SELECTED ARCHIVE"),
        ("events", "رویداد تاریخی فوتبال", "FOOTBALL HISTORY"),
    ]
    out: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    now_year = datetime.now(timezone.utc).year

    for sec_key, kicker_fa, league_en in sections:
        raw_list = payload.get(sec_key)
        if not isinstance(raw_list, list):
            continue
        for item in raw_list:
            if len(out) >= max_items:
                break
            if not isinstance(item, dict):
                continue
            year = item.get("year")
            text = str(item.get("text") or "").strip()
            pages = item.get("pages") if isinstance(item.get("pages"), list) else []
            if not text or not isinstance(year, int) or year < 1850 or year > now_year:
                continue
            if not _is_football_item(text, pages, lang):
                continue

            # کلید یکتا برای جلوگیری از تکرار بین selected و events
            primary_pg = pages[0] if pages else {}
            pg_title = str(
                (primary_pg.get("titles") or {}).get("normalized")
                or primary_pg.get("title")
                or ""
            ).strip()
            dedup_key = f"{year}:{(pg_title or text[:40]).lower()}"
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            extract = str(primary_pg.get("extract") or "").strip()
            wiki_url = str(
                ((primary_pg.get("content_urls") or {}).get("desktop") or {}).get("page")
                or ""
            ).strip()
            thumb_url = str((primary_pg.get("thumbnail") or {}).get("source") or "").strip() or None

            slug_hash = hashlib.sha1(f"{lang}:{month}:{day}:{year}:{text}".encode("utf-8")).hexdigest()[:8]
            ev_id = f"wiki_{lang}_{month:02d}{day:02d}_{year}_{slug_hash}"

            # عنوان کوتاه و خوانا
            if sec_key == "births":
                short_title = pg_title or text.split("،")[0].split(",")[0][:48]
                headline = f"زادروز {short_title}" if lang == "fa" else f"{short_title} ({year})"
            else:
                short_title = pg_title or text[:52].rstrip(" .،,")
                headline = short_title[:56]

            yrs_ago = max(1, now_year - year)
            body_text = extract[:340].rstrip() if len(extract) > len(text) + 20 else text
            if len(body_text) > 330:
                body_text = body_text[:327].rsplit(" ", 1)[0] + "…"

            date_fa = _gregorian_to_jalali_str(year, month, day)
            date_en = _format_date_en(year, month, day)

            # تنها اعداد ۱۰۰٪ مستند و محاسبه‌پذیر (سال و فاصلهٔ زمانی) — هیچ آمار جعلی نداریم
            verified_numbers = [
                {"val": str(year), "unit": "سال وقوع", "sub": f"ثبت‌شده در تاریخ {date_en}"},
                {"val": str(yrs_ago), "unit": "سال پیش", "sub": "فاصله تا امروز"},
            ]

            out.append({
                "id": ev_id,
                "verified": True,
                "is_live_wiki": True,
                "is_archive": False,
                "lang": lang,
                "category": sec_key,
                "month": month,
                "day": day,
                "year": year,
                "defaultBg": "spotlight" if sec_key == "births" else "stadium",
                "shortLabel": f"{headline[:26]} ({year})",
                "archiveCode": f"WIKI-{year}-{month:02d}{day:02d}",
                "dateFa": date_fa,
                "dateEn": date_en,
                "competition": kicker_fa,
                "leagueEn": league_en,
                "kicker": f"{kicker_fa} | ویکی‌پدیا ({'فارسی' if lang == 'fa' else 'انگلیسی'})",
                "stadium": "",
                "source": f"Wikipedia ({lang.upper()}) / XGPedia",
                "source_url": wiki_url or f"https://{lang}.wikipedia.org/api/rest_v1/feed/onthisday/all/{month:02d}/{day:02d}",
                "thumbnail_url": thumb_url,
                "title": headline,
                "subtitle": text[:210] + ("…" if len(text) > 210 else ""),
                "aggNote": "",
                # بدون دیتای مسابقه/تاکتیکی جعلی (null ≠ 0)
                "home": None,
                "away": None,
                "pulse": None,
                "goals": [],
                "replay": None,
                "numbers": verified_numbers,
                "story": {
                    "headline": f"روایت {date_fa}",
                    "body": body_text,
                    "tag": f"منبع مستند: ویکی‌پدیا ({lang.upper()})",
                },
                "quote": None,
                "legacy": None,
            })

    return out


def fetch_wikipedia_on_this_day(
    month: int,
    day: int,
    *,
    timeout: float = 10.0,
    force_refresh: bool = False,
) -> list[dict[str, Any]]:
    """دریافت زندهٔ رویدادهای فوتبال امروز از Wikimedia REST API (اول فارسی، سپس انگلیسی)."""
    key = (int(month), int(day))
    if not force_refresh and key in _LIVE_CACHE:
        return list(_LIVE_CACHE[key])

    headers = {
        "User-Agent": WIKI_USER_AGENT,
        "Accept": "application/json",
    }
    combined: list[dict[str, Any]] = []
    seen_years_titles: set[str] = set()

    for lang in ("fa", "en"):
        url = f"https://{lang}.wikipedia.org/api/rest_v1/feed/onthisday/all/{month:02d}/{day:02d}"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if getattr(resp, "status", 200) != 200:
                    log.info("wikimedia onthisday %s returned HTTP %s", lang, getattr(resp, "status", 0))
                    continue
                payload = json.loads(resp.read().decode("utf-8"))
            parsed = parse_wikipedia_on_this_day_payload(
                payload, month=month, day=day, lang=lang, max_items=6
            )
            for ev in parsed:
                sig = f"{ev['year']}:{ev['title'][:24].lower()}"
                if sig not in seen_years_titles:
                    seen_years_titles.add(sig)
                    combined.append(ev)
        except Exception as e:
            log.warning("wikimedia onthisday %s failed: %s", lang, e)

    _LIVE_CACHE[key] = combined
    return list(combined)


def list_on_this_day_events(
    month: int | None = None,
    day: int | None = None,
    *,
    include_live: bool = True,
    force_refresh: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    """برگرداندن دو فهرست تفکیک‌شده برای ربات تلگرام:
      - `today`: رویدادهای واقعی همین روز (آرشیو منطبق با امروز + ویکی‌پدیا فارسی/انگلیسی)
      - `archive`: لحظات مستند و کامل آرشیو شوریل (همیشه در دسترس با ۴ اسلاید کامل)
    """
    now = datetime.now(timezone.utc)
    m = int(month or now.month)
    d = int(day or now.day)

    archive_all = load_archive_presets()
    today_archive = [ev for ev in archive_all if ev.get("month") == m and ev.get("day") == d]
    live_wiki = (
        fetch_wikipedia_on_this_day(m, d, force_refresh=force_refresh)
        if include_live
        else []
    )
    return {
        "today": today_archive + live_wiki,
        "archive": archive_all,
    }


def get_on_this_day_event(
    event_id: str,
    *,
    month: int | None = None,
    day: int | None = None,
) -> dict[str, Any] | None:
    """یافتن رویداد بر اساس شناسه در آرشیو یا کش زنده."""
    for ev in load_archive_presets():
        if ev.get("id") == event_id:
            return ev
    for cached_list in _LIVE_CACHE.values():
        for ev in cached_list:
            if ev.get("id") == event_id:
                return ev
    if month and day:
        for ev in fetch_wikipedia_on_this_day(month, day):
            if ev.get("id") == event_id:
                return ev
    return None
