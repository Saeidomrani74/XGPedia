"""منابع زنده و ۱۰۰٪ رایگان اطلاعاتی مسابقه (بدون نیاز به کلید API):

1) استخراج زندهٔ نام سرمربی فعلی تیم‌ها از ویکی‌پدیای انگلیسی (به‌روزرسانی لحظه‌ای پس از هر
   اخراج یا استخدام، حتی وقتی football-data.org هنوز به‌روز نشده) + دریافت نام فارسی رسمی
   سرمربی از ویکی‌پدیای فارسی (langlinks).
2) دریافت اخبار تازه و مهم دو تیم (۷ روز اخیر) از Google News RSS و BBC Sport RSS برای
   تزریق هوشمند و مستند به کپشن تحریریه (تغییر سرمربی، اولین بازی مربی جدید، مصدومیت، محرومیت).
"""
from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from src.xgpedia.config import canonical_team_name, translate_coach_fa

WIKI_API_EN = "https://en.wikipedia.org/w/api.php"
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
BBC_FOOTBALL_RSS = "https://feeds.bbci.co.uk/sport/football/rss.xml"

# نگاشت نام canonical تیم‌های لیگ برتر (و تیم‌های اخیر چمپیونشیپ) به عنوان دقیق مقالهٔ ویکی‌پدیای انگلیسی
TEAM_WIKI_TITLES: dict[str, str] = {
    "Arsenal": "Arsenal F.C.",
    "Aston Villa": "Aston Villa F.C.",
    "Bournemouth": "AFC Bournemouth",
    "Brentford": "Brentford F.C.",
    "Brighton": "Brighton & Hove Albion F.C.",
    "Burnley": "Burnley F.C.",
    "Chelsea": "Chelsea F.C.",
    "Coventry": "Coventry City F.C.",
    "Crystal Palace": "Crystal Palace F.C.",
    "Everton": "Everton F.C.",
    "Fulham": "Fulham F.C.",
    "Hull": "Hull City A.F.C.",
    "Ipswich": "Ipswich Town F.C.",
    "Leeds": "Leeds United F.C.",
    "Leicester": "Leicester City F.C.",
    "Liverpool": "Liverpool F.C.",
    "Manchester City": "Manchester City F.C.",
    "Manchester United": "Manchester United F.C.",
    "Newcastle": "Newcastle United F.C.",
    "Nottingham Forest": "Nottingham Forest F.C.",
    "Southampton": "Southampton F.C.",
    "Sunderland": "Sunderland A.F.C.",
    "Tottenham": "Tottenham Hotspur F.C.",
    "West Ham": "West Ham United F.C.",
    "Wolverhampton": "Wolverhampton Wanderers F.C.",
}

_HIGH_SIGNAL_NEWS_KEYWORDS = (
    "manager", "head coach", "coach", "sacked", "fired", "appointed", "appoints",
    "takes charge", "first game", "first match", "debut", "interim", "caretaker",
    "injury", "injured", "ruled out", "suspended", "ban", "returns", "blow", "boost",
    "derby", "relegation", "title", "streak", "unbeaten",
)


def _clean_wikitext_value(raw: str) -> str:
    """پاک‌سازی مقدار فیلد Infobox ویکی‌پدیا (حذف ref، لینک [[A|B]]، قالب‌ها و پرانتزهای اضافه)."""
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", raw, flags=re.IGNORECASE | re.DOTALL)
    s = re.sub(r"<ref[^/>]*/>", "", s, flags=re.IGNORECASE)
    s = re.sub(r"<!--.*?-->", "", s, flags=re.DOTALL)
    # حفظ متن نمایشی لینک [[Target|Label]] -> Label و [[Target]] -> Target
    s = re.sub(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", r"\1", s)
    # حذف قالب‌های کوچک مثل {{nowrap|...}} با حفظ محتوا یا حذف {{flagicon|...}}
    s = re.sub(r"\{\{(?:nowrap|sortname)\|([^}|]+)(?:\|([^}]+))?\}\}", lambda m: f"{m.group(1)} {m.group(2) or ''}".strip(), s, flags=re.IGNORECASE)
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    # حذف برچسب‌های موقت مثل (interim) یا (caretaker)
    s = re.sub(r"\((?:interim|caretaker|head coach|manager)[^)]*\)", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip(" \t\r\n,;-•|")
    return s


def parse_coach_from_wikitext(wikitext: str) -> str | None:
    """استخراج نام سرمربی فعلی از بخش Infobox ویکی‌پدیا."""
    if not wikitext:
        return None
    for pat in (
        r"^\|\s*(?:manager|head\s*coach|coach)\s*=\s*(.+)$",
    ):
        m = re.search(pat, wikitext, flags=re.IGNORECASE | re.MULTILINE)
        if m:
            cleaned = _clean_wikitext_value(m.group(1))
            if cleaned and cleaned.lower() not in {"vacant", "tba", "tbd", "none", "n/a"}:
                # فقط بخش اول اگر خط یا کاما چندتایی داشت
                cleaned = cleaned.split("<br")[0].strip()
                if 3 <= len(cleaned) <= 50:
                    return cleaned
    return None


def fetch_live_coach_wikipedia(team_en: str, *, timeout: float = 10.0) -> tuple[str | None, str | None]:
    """دریافت زندهٔ `(coach_en, coach_fa)` برای یک تیم از ویکی‌پدیای انگلیسی + فارسی.

    اگر مقالهٔ فارسی سرمربی وجود داشته باشد نام فارسی رسمی آن برگردانده می‌شود؛
    در غیر این صورت `translate_coach_fa(coach_en)` (دیکشنری + آوانویسی خودکار) استفاده می‌شود.
    """
    canon = canonical_team_name(team_en)
    wiki_title = TEAM_WIKI_TITLES.get(canon) or f"{canon} F.C."
    headers = {"User-Agent": "XGPediaBot/0.21 (https://xgpedia.local; football-analytics)"}

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            r = client.get(
                WIKI_API_EN,
                params={
                    "action": "query",
                    "prop": "revisions",
                    "rvprop": "content",
                    "rvslots": "main",
                    "rvsection": "0",
                    "redirects": "1",
                    "format": "json",
                    "titles": wiki_title,
                },
            )
            r.raise_for_status()
            pages = (r.json().get("query") or {}).get("pages") or {}
            wikitext = ""
            for p in pages.values():
                revs = p.get("revisions") or []
                if revs:
                    slots = revs[0].get("slots") or {}
                    wikitext = (slots.get("main") or {}).get("*") or revs[0].get("*") or ""
                    break

            coach_en = parse_coach_from_wikitext(wikitext)
            if not coach_en:
                return None, None

            # بررسی اینکه آیا در دیکشنری محلی ترجمهٔ دقیق دارد
            local_fa = translate_coach_fa(coach_en, allow_transliterate=False)
            if local_fa and local_fa != coach_en:
                return coach_en, local_fa

            # اگر در دیکشنری نبود، نام رسمی فارسی را از langlinks ویکی‌پدیا می‌گیریم
            coach_fa: str | None = None
            try:
                r2 = client.get(
                    WIKI_API_EN,
                    params={
                        "action": "query",
                        "prop": "langlinks",
                        "lllang": "fa",
                        "redirects": "1",
                        "format": "json",
                        "titles": coach_en,
                    },
                )
                if r2.status_code == 200:
                    p2 = (r2.json().get("query") or {}).get("pages") or {}
                    for page in p2.values():
                        lls = page.get("langlinks") or []
                        if lls:
                            fa_title = str(lls[0].get("*") or "").strip()
                            # حذف پرانتز ابهام‌زدایی ویکی‌پدیا مثل «(مربی فوتبال)»
                            fa_title = re.sub(r"\s*\([^)]*\)\s*$", "", fa_title).strip()
                            if fa_title:
                                coach_fa = fa_title
                                break
            except Exception:
                pass

            return coach_en, (coach_fa or translate_coach_fa(coach_en))
    except Exception:
        return None, None


def _score_headline(title: str, team_en: str) -> int:
    tl = title.lower()
    score = 0
    if team_en.lower() in tl:
        score += 3
    for kw in _HIGH_SIGNAL_NEWS_KEYWORDS:
        if kw in tl:
            score += 4
    return score


def parse_rss_items(xml_text: str, team_en: str, default_source: str = "") -> list[dict[str, str]]:
    """پارس استاندارد خوراک RSS و استخراج تیتر، منبع، تاریخ و لینک."""
    items: list[dict[str, str]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items

    for node in root.findall(".//item"):
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        pub = (node.findtext("pubDate") or "").strip()
        src_el = node.find("source")
        source = (src_el.text or "").strip() if src_el is not None and src_el.text else default_source
        if not title:
            continue
        # حذف پسوند « - Source» از انتهای تیترهای Google News
        if source and title.endswith(f" - {source}"):
            title = title[: -(len(source) + 3)].strip()
        items.append({
            "team": team_en,
            "title": title,
            "source": source or default_source or "News",
            "published_at": pub,
            "url": link,
        })
    return items


def fetch_match_breaking_news(
    home_en: str,
    away_en: str,
    *,
    max_items: int = 6,
    timeout: float = 8.0,
) -> list[dict[str, str]]:
    """دریافت اخبار تازه و مهم ۷ روز اخیر دو تیم از Google News RSS + BBC Sport RSS (کاملاً رایگان)."""
    h_canon = canonical_team_name(home_en)
    a_canon = canonical_team_name(away_en)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"}
    collected: list[tuple[int, dict[str, str]]] = []
    seen_titles: set[str] = set()

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            for team in (h_canon, a_canon):
                q = urllib.parse.quote_plus(f'"{team}" (manager OR coach OR sacked OR appointed OR injury OR debut OR suspended) when:7d')
                url = f"{GOOGLE_NEWS_RSS}?q={q}&hl=en-GB&gl=GB&ceid=GB:en"
                try:
                    r = client.get(url)
                    if r.status_code == 200 and r.text:
                        for it in parse_rss_items(r.text, team, default_source="Google News")[:8]:
                            key = re.sub(r"\W+", "", it["title"].lower())[:48]
                            if key and key not in seen_titles:
                                seen_titles.add(key)
                                collected.append((_score_headline(it["title"], team), it))
                except Exception:
                    pass

            # پشتیبان رایگان BBC Sport Football RSS
            try:
                rb = client.get(BBC_FOOTBALL_RSS)
                if rb.status_code == 200 and rb.text:
                    for team in (h_canon, a_canon):
                        t_low = team.lower()
                        for it in parse_rss_items(rb.text, team, default_source="BBC Sport"):
                            if t_low in it["title"].lower():
                                key = re.sub(r"\W+", "", it["title"].lower())[:48]
                                if key and key not in seen_titles:
                                    seen_titles.add(key)
                                    collected.append((_score_headline(it["title"], team) + 2, it))
            except Exception:
                pass
    except Exception:
        return []

    collected.sort(key=lambda x: -x[0])
    # تعادل بین میزبان و میهمان (حداکثر ۳ خبر از هر تیم)
    out: list[dict[str, str]] = []
    counts: dict[str, int] = {h_canon: 0, a_canon: 0}
    per_team = max(2, max_items // 2)
    for _, it in collected:
        tm = it["team"]
        if counts.get(tm, 0) < per_team:
            out.append(it)
            counts[tm] = counts.get(tm, 0) + 1
        if len(out) >= max_items:
            break
    return out
