"""دریافت زنده و ۱۰۰٪ رایگان اخبار فوری و رسمی فوتبال (بدون نیاز به API Key).

منابع زنده و معتبر (مبتنی بر کتابخانه استاندارد پایتون `urllib.request` و `xml.etree.ElementTree`):
  1. ESPN Soccer Live News JSON API (`site.api.espn.com/apis/site/v2/sports/soccer/{league}/news`)
     — لیگ برتر انگلیس (`eng.1`)، لیگ قهرمانان اروپا (`uefa.champions`)، لالیگا (`esp.1`)
  2. BBC Sport Football RSS (`https://feeds.bbci.co.uk/sport/football/rss.xml`)
  3. The Guardian Football RSS (`https://www.theguardian.com/football/rss`)
  4. پریست‌های استودیویی آماده (`config/news_presets.json`)

قاعدهٔ طلایی `null ≠ 0`: برای اخبار زندهٔ RSS/ESPN هیچ آمار، نقل‌قول یا مبلغ انتقال جعلی ساخته نمی‌شود.
"""
from __future__ import annotations

import hashlib
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

log = logging.getLogger(__name__)

PRESETS_PATH = ROOT / "config" / "news_presets.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

ESPN_NEWS_FEEDS: list[tuple[str, str, str]] = [
    ("eng.1", "لیگ برتر انگلیس", "PREMIER LEAGUE | LIVE WIRE"),
    ("uefa.champions", "لیگ قهرمانان اروپا", "CHAMPIONS LEAGUE | LIVE WIRE"),
    ("esp.1", "لالیگا اسپانیا", "LA LIGA | LIVE WIRE"),
]

RSS_FEEDS: list[tuple[str, str, str, str]] = [
    ("BBC Sport", "https://feeds.bbci.co.uk/sport/football/rss.xml", "TIER 1", "BBC SPORT | FOOTBALL DESK"),
    ("The Guardian", "https://www.theguardian.com/football/rss", "TIER 1", "THE GUARDIAN | FOOTBALL"),
]

# کش ۱۵ دقیقه‌ای اخبار زنده
_NEWS_CACHE: dict[str, Any] = {"ts": 0.0, "items": []}
_CACHE_TTL_SEC = 900.0


def load_news_presets(path: Path | None = None) -> list[dict[str, Any]]:
    """بارگذاری ۵ پریست آماده استودیویی از `config/news_presets.json`."""
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
        log.warning("failed to load news_presets.json: %s", e)
        return []


def classify_news_mode(headline: str, lead: str = "") -> str:
    """تشخیص خودکار مود خبر (`breaking`, `official`, `transfer`, `exclusive`, `alert`) از متن واقعی خبر."""
    blob = f"{headline} {lead}".lower()
    if any(k in blob for k in (
        "injury", "injured", "ruled out", "hamstring", "acl", "surgery", "scan", "sidelined",
        "مصدوم", "همسترینگ", "جراحی", "پزشکی", "دور از میادین",
    )):
        return "alert"
    if any(k in blob for k in (
        "transfer", "signs ", "signed", "sign ", "loan", "bid", "here we go", "contract", "fee", "deal",
        "انتقال", "پیوست", "قرارداد", "تمدید", "بند فسخ",
    )):
        return "transfer"
    if any(k in blob for k in (
        "official", "confirmed", "confirm", "appoint", "sacked", "statement", "announce",
        "رسمی", "بیانیه", "تایید", "سرمربی جدید", "اخراج",
    )):
        return "official"
    if any(k in blob for k in ("exclusive", "اختصاصی")):
        return "exclusive"
    return "breaking"


def _clean_html_text(raw: str) -> str:
    s = re.sub(r"<[^>]+>", " ", str(raw or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s




def _format_pub_jalali(raw_date: str) -> str:
    """تبدیل تاریخ ISO یا RFC-2822 خبر به تاریخ شمسی خوانا (به‌جای Sun, 22 Nov 2026)."""
    s = str(raw_date or "").strip()
    if not s:
        return "خبر زنده"
    try:
        from email.utils import parsedate_to_datetime
        from src.xgpedia.render.cards import jalali_date
        dt = None
        if "T" in s and s[:4].isdigit():
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        else:
            dt = parsedate_to_datetime(s)
        if dt is not None:
            j = jalali_date(dt.astimezone(timezone.utc).isoformat())
            if j:
                parts = j.split(" ", 1)
                if len(parts) == 2 and parts[0].endswith(("شنبه", "جمعه")):
                    return parts[1].strip()
                return j
    except Exception:
        pass
    return "خبر زنده"


def upgrade_news_image_url(url: str | None) -> str | None:
    """ارتقای خودکار آدرس تامبنیل‌های ریز (مثل 240px بی‌بی‌سی) به نسخهٔ HD (1024px+)."""
    u = str(url or "").strip()
    if not u.startswith(("http://", "https://")):
        return None
    # BBC iChef CDN: /240/ یا /320/ یا /480/ -> /1024/
    u = re.sub(r"(ichef\.bbci\.co\.uk/[^/]+/[^/]+/)\d+/", r"\g<1>1024/", u)
    u = re.sub(r"(ichef\.bbci\.co\.uk/news/)\d+/", r"\g<1>1024/", u)
    # Guardian CDN: width=140/460 -> width=1200
    if "i.guim.co.uk" in u:
        u = re.sub(r"([?&])width=\d+", r"\g<1>width=1200", u)
    # ESPN combiner: w=300 -> w=1200
    if "espncdn.com" in u:
        u = re.sub(r"([?&])w=\d+", r"\g<1>w=1200", u)
    return u


def _probe_image_width(raw: bytes) -> int:
    """تشخیص سریع عرض پیکسلی JPEG/PNG/WebP بدون نیاز به Pillow."""
    import struct
    if len(raw) < 32:
        return 0
    # PNG
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">I", raw[16:20])[0]
    # WebP (VP8X / VP8 / VP8L)
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        chunk = raw[12:16]
        if chunk == b"VP8X" and len(raw) >= 30:
            return 1 + int.from_bytes(raw[24:27], "little")
        if chunk == b"VP8 " and len(raw) >= 30:
            return struct.unpack("<H", raw[26:28])[0] & 0x3FFF
    # JPEG SOF0/SOF2
    if raw[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(raw):
            if raw[i] != 0xFF:
                i += 1
                continue
            marker = raw[i + 1]
            if marker in (0xC0, 0xC1, 0xC2):
                return struct.unpack(">H", raw[i + 7:i + 9])[0]
            if marker in (0xD8, 0xD9, 0x01) or (0xD0 <= marker <= 0xD7):
                i += 2
            else:
                seg_len = struct.unpack(">H", raw[i + 2:i + 4])[0]
                i += 2 + max(2, seg_len)
    return 0


def fetch_og_image_url(article_url: str | None, *, timeout: float = 6.0) -> str | None:
    """استخراج تصویر باکیفیت og:image از صفحهٔ اصلی خبر در صورت ریز بودن تامبنیل RSS."""
    u = str(article_url or "").strip()
    if not u.startswith(("http://", "https://")):
        return None
    try:
        req = urllib.request.Request(u, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            head_html = resp.read(65536).decode("utf-8", errors="ignore")
        m = re.search(
            r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)["\']',
            head_html,
            re.IGNORECASE,
        )
        if not m:
            m = re.search(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\']',
                head_html,
                re.IGNORECASE,
            )
        if m:
            return upgrade_news_image_url(m.group(1).replace("&amp;", "&"))
    except Exception:
        pass
    return None


def parse_espn_news_payload(
    payload: dict[str, Any],
    *,
    comp_fa: str = "فوتبال اروپا",
    footer_tag: str = "ESPN SOCCER | LIVE WIRE",
    max_items: int = 5,
) -> list[dict[str, Any]]:
    """استخراج اخبار واقعی فوتبال از خروجی JSON اندپوینت ESPN Soccer News (با رعایت null ≠ 0)."""
    articles = payload.get("articles") if isinstance(payload, dict) else None
    if not isinstance(articles, list):
        return []

    out: list[dict[str, Any]] = []
    for art in articles:
        if len(out) >= max_items:
            break
        if not isinstance(art, dict):
            continue
        headline = _clean_html_text(art.get("headline") or "")
        if not headline:
            continue
        lead = _clean_html_text(art.get("description") or "")
        mode = classify_news_mode(headline, lead)
        published = str(art.get("published") or "")[:16].replace("T", " ")
        web_url = str(((art.get("links") or {}).get("web") or {}).get("href") or "").strip()
        images = art.get("images") if isinstance(art.get("images"), list) else []
        img_url = str((images[0] or {}).get("url") or "").strip() if images and isinstance(images[0], dict) else None

        slug = hashlib.sha1(f"espn:{headline}".encode("utf-8")).hexdigest()[:8]
        out.append({
            "id": f"espn_{slug}",
            "is_live": True,
            "is_preset": False,
            "lang": "en",
            "title": headline[:72],
            "sub": f"ESPN | {comp_fa}",
            "mode": mode,
            "layout": "cinematic",
            "dock": "none",
            "comp": comp_fa,
            "time": _format_pub_jalali(published),
            "kicker": f"گزارش زنده ESPN | {comp_fa}",
            "headline": headline,
            "lead": lead[:260] + ("…" if len(lead) > 260 else ""),
            "photoId": "tunnel" if mode in ("breaking", "alert") else "stadium",
            "photoUrl": upgrade_news_image_url(img_url),
            "mood": "crimson" if mode == "breaking" else ("navy" if mode == "official" else "cinema"),
            "fy": 32,
            "fz": 105,
            "customColor": None,
            # اصل null ≠ 0: آمار، نقل‌قول و پل انتقال ساختگی اضافه نمی‌شود
            "stats": [],
            "quote": "",
            "qauthor": "",
            "transfer": None,
            "bullets": [],
            "source": "ESPN Soccer",
            "source_url": web_url or "https://www.espn.com/soccer/",
            "tier": "TIER 1",
            "footerTag": footer_tag,
        })
    return out


def parse_rss_football_xml(
    xml_bytes: bytes | str,
    *,
    source_name: str = "BBC Sport",
    tier: str = "TIER 1",
    footer_tag: str = "FOOTBALL LIVE WIRE",
    max_items: int = 5,
) -> list[dict[str, Any]]:
    """پارس ایمن RSS 2.0 اخبار فوتبال (BBC Sport / The Guardian) بدون ساخت دیتای جعلی."""
    try:
        root = ET.fromstring(xml_bytes if isinstance(xml_bytes, (bytes, bytearray)) else xml_bytes.encode("utf-8"))
    except Exception as e:
        log.warning("rss xml parse failed for %s: %s", source_name, e)
        return []

    out: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        if len(out) >= max_items:
            break
        headline = _clean_html_text(item.findtext("title") or "")
        if not headline:
            continue
        lead = _clean_html_text(item.findtext("description") or "")
        link = _clean_html_text(item.findtext("link") or "")
        pub_date = _clean_html_text(item.findtext("pubDate") or "")
        mode = classify_news_mode(headline, lead)

        # استخراج تصویر بندانگشتی در صورت وجود در RSS (media:thumbnail / enclosure)
        img_url: str | None = None
        for child in item:
            tag_low = child.tag.lower()
            if tag_low.endswith("thumbnail") or tag_low.endswith("content") or tag_low == "enclosure":
                u = child.attrib.get("url")
                if u and str(u).startswith("http"):
                    img_url = str(u)
                    break

        slug = hashlib.sha1(f"{source_name}:{headline}".encode("utf-8")).hexdigest()[:8]
        out.append({
            "id": f"rss_{slug}",
            "is_live": True,
            "is_preset": False,
            "lang": "en",
            "title": headline[:72],
            "sub": f"{source_name} | خبر زنده",
            "mode": mode,
            "layout": "cinematic",
            "dock": "none",
            "comp": "فوتبال اروپا",
            "time": _format_pub_jalali(pub_date),
            "kicker": f"گزارش زنده {source_name}",
            "headline": headline,
            "lead": lead[:260] + ("…" if len(lead) > 260 else ""),
            "photoId": "stadium",
            "photoUrl": upgrade_news_image_url(img_url),
            "mood": "crimson" if mode == "breaking" else "cinema",
            "fy": 35,
            "fz": 105,
            "customColor": None,
            "stats": [],
            "quote": "",
            "qauthor": "",
            "transfer": None,
            "bullets": [],
            "source": source_name,
            "source_url": link,
            "tier": tier,
            "footerTag": footer_tag,
        })
    return out


def fetch_live_breaking_news(*, timeout: float = 10.0, force_refresh: bool = False) -> list[dict[str, Any]]:
    """دریافت زندهٔ اخبار فوتبال از ESPN + BBC Sport + The Guardian با کش ۱۵ دقیقه‌ای."""
    now = time.time()
    if not force_refresh and _NEWS_CACHE["items"] and (now - _NEWS_CACHE["ts"] < _CACHE_TTL_SEC):
        return list(_NEWS_CACHE["items"])

    headers = {"User-Agent": USER_AGENT, "Accept": "application/json, application/xml, text/xml, */*", "Accept-Language": "en-US,en;q=0.9", "Referer": "https://www.espn.com/"}
    combined: list[dict[str, Any]] = []
    seen_titles: set[str] = set()

    # ۱) ESPN Soccer JSON API (دارای عکس باکیفیت و لیگ مشخص)
    for league_code, comp_fa, ftag in ESPN_NEWS_FEEDS:
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_code}/news?limit=4"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if getattr(resp, "status", 200) != 200:
                    continue
                payload = json.loads(resp.read().decode("utf-8"))
                for ev in parse_espn_news_payload(payload, comp_fa=comp_fa, footer_tag=ftag, max_items=3):
                    sig = ev["headline"][:36].lower()
                    if sig not in seen_titles:
                        seen_titles.add(sig)
                        combined.append(ev)
        except Exception as e:
            log.warning("espn news fetch failed (%s): %s", league_code, e)

    # ۲) BBC Sport & The Guardian Football RSS
    for src_name, rss_url, tier, ftag in RSS_FEEDS:
        try:
            req = urllib.request.Request(rss_url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if getattr(resp, "status", 200) != 200:
                    continue
                raw_xml = resp.read()
                for ev in parse_rss_football_xml(raw_xml, source_name=src_name, tier=tier, footer_tag=ftag, max_items=4):
                    sig = ev["headline"][:36].lower()
                    if sig not in seen_titles:
                        seen_titles.add(sig)
                        combined.append(ev)
        except Exception as e:
            log.warning("rss fetch failed (%s): %s", src_name, e)

    _NEWS_CACHE["ts"] = now
    _NEWS_CACHE["items"] = combined
    return list(combined)


def list_breaking_news_items(*, include_live: bool = True, force_refresh: bool = False) -> dict[str, list[dict[str, Any]]]:
    """برگرداندن اخبار زندهٔ امروز + پریست‌های استودیویی آماده برای ربات تلگرام."""
    live = fetch_live_breaking_news(force_refresh=force_refresh) if include_live else []
    presets = load_news_presets()
    return {"live": live, "presets": presets}


def get_breaking_news_item(item_id: str) -> dict[str, Any] | None:
    for p in load_news_presets():
        if p.get("id") == item_id:
            return p
    for it in _NEWS_CACHE.get("items") or []:
        if it.get("id") == item_id:
            return it
    return None


def fetch_image_data_uri(
    url: str | None,
    *,
    source_url: str | None = None,
    min_width: int = 640,
    timeout: float = 8.0,
) -> str | None:
    """دانلود عکس باکیفیت (HD) واقعی خبر و تبدیل به Data URI آفلاین (رد کردن تامبنیل‌های بی‌کیفیت)."""
    import base64

    candidates: list[str] = []
    up = upgrade_news_image_url(url)
    if up:
        candidates.append(up)
    orig = str(url or "").strip()
    if orig.startswith(("http://", "https://")) and orig not in candidates:
        candidates.append(orig)
    if source_url:
        og = fetch_og_image_url(source_url, timeout=6.0)
        if og and og not in candidates:
            candidates.append(og)

    best_uri: str | None = None
    best_w = 0
    best_bytes = 0
    hdrs = {"User-Agent": USER_AGENT, "Accept": "image/*,*/*;q=0.8"}
    if source_url and str(source_url).startswith(("http://", "https://")):
        hdrs["Referer"] = str(source_url)

    for cand in candidates:
        try:
            req = urllib.request.Request(cand, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if getattr(resp, "status", 200) != 200:
                    continue
                raw = resp.read(5 * 1024 * 1024)
                if len(raw) < 2048:
                    continue
                pw = _probe_image_width(raw)
                ctype = str(resp.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip().lower()
                if not ctype.startswith("image/"):
                    ctype = "image/jpeg"
                uri = f"data:{ctype};base64,{base64.b64encode(raw).decode('ascii')}"
                if pw >= min_width or (pw == 0 and len(raw) >= 25_000):
                    return uri
                if pw > best_w or (pw == 0 and len(raw) > best_bytes):
                    best_w = pw
                    best_bytes = len(raw)
                    best_uri = uri
        except Exception as e:
            log.warning("news photo download skipped (%s): %s", cand[:70], e)
    # اگر عرض عکس >= 500px یا حجم فایل >= 25KB بود از عکس واقعی خبر استفاده کن
    return best_uri if (best_w >= 500 or best_bytes >= 25_000) else None


def _looks_mostly_english(text: str) -> bool:
    ascii_letters = sum(1 for ch in text if "a" <= ch.lower() <= "z")
    fa_letters = sum(1 for ch in text if "\u0600" <= ch <= "\u06ff")
    return ascii_letters > fa_letters


def _fetch_article_excerpt(url: str | None, timeout: float = 5.0, max_chars: int = 1600) -> str:
    """استخراج پاراگراف‌های واقعی متن خبر از لینک اصلی (برای نوشتن گزارش کامل و غیرتکراری)."""
    if not url or not str(url).startswith(("http://", "https://")):
        return ""
    try:
        req = urllib.request.Request(
            str(url),
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            page = resp.read(220_000).decode("utf-8", errors="ignore")
        paras = re.findall(r"<p[^>]*>(.*?)</p>", page, flags=re.IGNORECASE | re.DOTALL)
        chunks: list[str] = []
        total = 0
        skip_kw = ("cookie", "subscribe", "sign up", "privacy policy", "all rights reserved", "javascript")
        for raw_p in paras:
            txt = _clean_text(raw_p)
            low = txt.lower()
            if len(txt) < 48 or any(k in low for k in skip_kw):
                continue
            chunks.append(txt)
            total += len(txt)
            if total >= max_chars or len(chunks) >= 6:
                break
        return "\n".join(chunks)[:max_chars]
    except Exception:
        return ""


def _short_card_lead(full_text: str, max_chars: int = 165) -> str:
    """استخراج لید کوتاه ۱ تا ۲ جمله‌ای برای روی کارت (تا متن کارت بیرون نزند و کپشن مفصل بماند)."""
    txt = str(full_text or "").strip()
    if not txt:
        return ""
    first_para = txt.split("\n")[0].strip()
    if len(first_para) <= max_chars:
        return first_para
    # برش روی پایان جمله در صورت امکان
    for sep in (". ", "؟ ", "! ", "؛ "):
        idx = first_para.find(sep)
        if 45 <= idx <= max_chars - 1:
            return first_para[: idx + 1].strip()
    return first_para[: max_chars - 1].rsplit(" ", 1)[0].strip() + "…"


def _dedupe_bullets_against_text(bullets: list[str], body_text: str) -> list[str]:
    """حذف بولت‌هایی که عیناً یا با همپوشانی بالای واژگان، جملات لید/متن را تکرار کرده‌اند."""
    body_words = set(re.findall(r"[\w\u0600-\u06ff]{3,}", (body_text or "").lower()))
    kept: list[str] = []
    seen_sets: list[set[str]] = []
    for b in bullets:
        b_clean = str(b).strip().lstrip("-•* ").strip()
        if len(b_clean) < 12:
            continue
        bw = set(re.findall(r"[\w\u0600-\u06ff]{3,}", b_clean.lower()))
        if not bw:
            continue
        # اگر بیش از ۷۲٪ کلمات بولت عیناً داخل متن بود، تکراری است
        if body_words and (len(bw & body_words) / len(bw)) >= 0.72:
            continue
        # جلوگیری از تکرار بین خود بولت‌ها
        if any((len(bw & prev) / max(1, min(len(bw), len(prev)))) >= 0.65 for prev in seen_sets):
            continue
        seen_sets.append(bw)
        kept.append(b_clean)
    return kept[:3]


def translate_news_item_to_persian(
    item: dict[str, Any],
    *,
    llm_provider: Any = None,
    cancel_event: Any = None,
) -> dict[str, Any]:
    """ترجمهٔ روان، مفصل و ژورنالیستی تیتر، گزارش خبری، کیکر و نکات غیرتکراری به فارسی با LLM."""
    out = dict(item)
    if out.get("lang") == "fa" and not _looks_mostly_english(str(out.get("headline") or "")):
        return out

    headline_en = str(out.get("headline") or out.get("title") or "").strip()
    lead_en = str(out.get("lead") or "").strip()
    if not headline_en:
        return out

    article_excerpt = str(out.get("article_excerpt") or "").strip()
    if not article_excerpt and out.get("source_url"):
        article_excerpt = _fetch_article_excerpt(out.get("source_url"))

    try:
        if llm_provider is None:
            from src.xgpedia.editorial.llm_provider import build_default_llm
            llm_provider = build_default_llm()
        if cancel_event is not None and hasattr(llm_provider, "cancel_event"):
            llm_provider.cancel_event = cancel_event

        sys_prompt = (
            "تو سردبیر ارشد تحریریه فوتبال XGPedia هستی. بر اساس تیتر، لید و متن خبر زیر، یک گزارش خبری فارسی روان، جذاب، کامل و ژورنالیستی بنویس.\n"
            "قوانین اجباری:\n"
            "1) خروجی را فقط به‌صورت یک شیء JSON معتبر با دقیقاً همین کلیدها برگردان (بدون هیچ کلید اضافی):\n"
            '{"status": "ok", "title": "...", "caption": "...", "bullets": ["...", "..."], "source_note": "...", "uncertainties": []}\n'
            "- مقدار `status` حتماً باید دقیقاً `\"ok\"` باشد.\n"
            "- `title`: تیتر کوتاه و تیترپسند فارسی (حداکثر ۶۵ کاراکتر)؛ مهم‌ترین نام تیم یا بازیکن را بین دو ستاره مثل *منچستریونایتد* قرار بده.\n"
            "- `caption`: گزارش خبری کامل و خوانا در ۲ پاراگراف (مجموعاً ۳۲۰ تا ۴۶۰ کاراکتر با خط خالی بین پاراگراف‌ها؛ هرگز از ستاره `*` در متن caption استفاده نکن). پاراگراف اول لید کوبنده و کوتاه (حداکثر ۲ جمله برای روی کارت)، پاراگراف دوم شرح جزئیات و پیامدهای خبر بر اساس متن ارسالی.\n"
            "- `bullets`: ۲ تا ۳ نکتهٔ کلیدی کوتاه و کاملاً مجزا که هرکدام زاویهٔ متفاوتی از خبر را بگویند و هرگز جملات `caption` را تکرار یا بازنویسی نکنند.\n"
            "- `source_note`: روتیتر/کیکر کوتاه ۳ تا ۵ کلمه (مثلاً «تحلیل ESPN فوتبال» یا «گزارش زنده BBC Sport»).\n"
            "- `uncertainties`: آرایهٔ خالی `[]`.\n"
            "2) نام بازیکنان، مربیان و تیم‌ها را به رسم‌الخط استاندارد فوتبال فارسی بنویس.\n"
            "3) هرگز عدد، آمار، مبلغ یا نقل‌قول جعلی که در متن انگلیسی نیست اضافه نکن."
        )
        payload: dict[str, Any] = {
            "headline": headline_en,
            "lead": lead_en,
            "competition": out.get("comp") or "",
            "source": out.get("source") or "",
            "mode": out.get("mode") or "breaking",
        }
        if article_excerpt:
            payload["article_excerpt"] = article_excerpt

        draft = llm_provider.generate(sys_prompt, payload)
        if getattr(draft, "title", None):
            fa_hl = str(draft.title).strip()
            out["headline"] = fa_hl
            out["title"] = fa_hl.replace("*", "")[:72]
        full_body = ""
        if getattr(draft, "caption", None):
            full_body = re.sub(r"\*([^*\n]+)\*", r"\1", str(draft.caption).strip()).replace("*", "")
            out["body_fa"] = full_body
            out["lead"] = _short_card_lead(full_body, max_chars=165)
        if getattr(draft, "source_note", None):
            sn = str(draft.source_note).strip()
            if sn and len(sn) <= 75 and "http" not in sn.lower():
                out["kicker"] = sn
        raw_bullets = [str(b).strip() for b in (getattr(draft, "bullets", None) or []) if str(b).strip()]
        deduped_bullets = _dedupe_bullets_against_text(raw_bullets, full_body)
        if deduped_bullets and not out.get("bullets"):
            out["bullets"] = deduped_bullets
        out["lang"] = "fa"
    except Exception as e:
        log.warning("news LLM Persian translation fallback (%s): %s", out.get("id"), e)

    return out
