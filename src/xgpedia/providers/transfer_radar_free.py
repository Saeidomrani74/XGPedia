"""تأمین‌کنندهٔ چندمنبعی و رایگان شایعات نقل‌وانتقالات فوتبال (XGPedia Transfer Radar — D48).

اکوسیستم کاملاً رایگان (بدون کلید API و بدون requests — فقط stdlib urllib + XML):
  ۱) کشف خودکار شایعات داغ از ۵ فید مستقل فوتبال (منحصراً Soccer):
     - The Guardian Transfer Window RSS (Tier 1): https://www.theguardian.com/football/transfer-window/rss
     - BBC Sport Football RSS (Tier 1، فیلتر نقل‌وانتقالات): https://feeds.bbci.co.uk/sport/football/rss.xml
     - Sky Sports Football / Transfer Centre RSS (Tier 1-2): https://www.skysports.com/rss/0,20514,11095,00.xml
     - CaughtOffside Transfer Rumours RSS (Tier 2-3): https://www.caughtoffside.com/feed/
     - 90min Football Transfers RSS (Tier 2-3): https://www.90min.com/posts.rss
  ۲) موتور امتیازدهی داغ بودن شایعه (hotness_score: 0..100) برای رتبه‌بندی و آماده برای اتوماسیون آینده (`get_top_hot_transfer_rumors`).
  ۳) غنی‌سازی عمیق پس از انتخاب شایعه (`enrich_transfer_rumor`):
     - استخراج متن کامل خبر از لینک اصلی (`source_url`)
     - دریافت عکس و مشخصات واقعی بازیکن از Wikipedia + TheSportsDB (`strSport == "Soccer"`)
     - استخراج ساختاریافتهٔ وضعیت، درصد احتمال، مرحله ۱ تا ۵، مبلغ، باشگاه مبدأ/مقصد و جمع‌بندی تحریریه فارسی با LLM (قانون `null ≠ 0`).
"""
from __future__ import annotations

import hashlib
import html as _html
import json
import logging
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any

from src.xgpedia.config import ROOT

log = logging.getLogger(__name__)

TEHRAN_TZ = timezone(timedelta(hours=3, minutes=30))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# ۵ منبع رایگان مستقل منحصراً فوتبال (Soccer)
TRANSFER_FEEDS: list[tuple[str, str, int]] = [
    ("The Guardian", "https://www.theguardian.com/football/transfer-window/rss", 1),
    ("BBC Sport", "https://feeds.bbci.co.uk/sport/football/rss.xml", 1),
    ("Sky Sports", "https://www.skysports.com/rss/0,20514,11095,00.xml", 1),
    ("CaughtOffside", "https://www.caughtoffside.com/feed/", 2),
    ("90min", "https://www.90min.com/posts.rss", 2),
]

_TRANSFER_KW_RE = re.compile(
    r"\b(transfer|rumour|rumor|gossip|bid|offer|signing|sign|deal|agreed|agreement|"
    r"medical|release clause|loan|swap|target|interest|talks|contract|extension|join|"
    r"move to|linked with|hijack|here we go|done deal|window|fee|€\d+|£\d+)\b",
    re.IGNORECASE,
)

# حذف قطعی غیرفوتبال (قانون دائمی Soccer-only)
_NON_SOCCER_RE = re.compile(
    r"\b(nfl|nba|mlb|nhl|american football|rugby|cricket|tennis|f1|formula 1|boxing|ufc|golf|afl|cfl)\b",
    re.IGNORECASE,
)

_HOT_SIGNALS: list[tuple[str, int, str, int]] = [
    # (pattern, hotness_boost, status, stage)
    (r"\b(here we go|done deal|officially signs|completed|announced|confirmed)\b", 28, "done", 5),
    (r"\b(medical|agreement reached|agreed terms|personal terms|advanced talks|close to)\b", 22, "hot", 4),
    (r"\b(official bid|tabled|offer rejected|new bid|release clause|€\d+m|£\d+m)\b", 18, "bid", 3),
    (r"\b(hijack|gazump|race for|battle for)\b", 16, "hijack", 3),
    (r"\b(talks|approached|enquiry|interested|targeting|monitoring|radar)\b", 10, "radar", 2),
]

_BIG_CLUBS = (
    "arsenal", "liverpool", "manchester united", "man utd", "manchester city", "man city",
    "chelsea", "tottenham", "real madrid", "barcelona", "atletico", "bayern", "dortmund",
    "psg", "paris saint-germain", "inter", "milan", "juventus", "napoli", "newcastle",
    "aston villa", "al-nassr", "al-hilal",
)

_RUMOR_CACHE: dict[str, Any] = {"ts": 0.0, "items": []}
_CACHE_TTL_SEC = 600.0  # ۱۰ دقیقه


def _clean_txt(raw: str | None) -> str:
    s = _html.unescape(str(raw or ""))
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_transfer_presets() -> list[dict[str, Any]]:
    p = ROOT / "config" / "transfer_presets.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("failed loading transfer_presets.json: %s", e)
        return []


def compute_rumor_hotness(title: str, desc: str, *, tier: int = 2) -> tuple[int, str, int]:
    """محاسبه امتیاز داغ بودن شایعه (0..100)، وضعیت اولیه (status) و مرحله مذاکرات (1..5)."""
    blob = f"{title} {desc}"
    low = blob.lower()
    score = 54 if tier == 1 else (44 if tier == 2 else 34)
    status = "radar"
    stage = 2

    for pat, boost, st, stg in _HOT_SIGNALS:
        if re.search(pat, low):
            score += boost
            status = st
            stage = stg
            break

    club_hits = sum(1 for c in _BIG_CLUBS if c in low)
    score += min(18, club_hits * 9)
    if re.search(r"[€£]\s*\d+", blob):
        score += 7

    return min(99, max(20, score)), status, stage


def parse_transfer_rss_xml(
    raw_xml: bytes,
    *,
    source_name: str,
    tier: int = 2,
    require_transfer_kw: bool = True,
    max_items: int = 8,
) -> list[dict[str, Any]]:
    """پارس ایمن RSS شایعات نقل‌وانتقالات فوتبال (با فیلتر سخت‌گیرانه Soccer-only)."""
    out: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(raw_xml)
    except Exception:
        return out

    items = root.findall(".//item")
    for item in items:
        title = _clean_txt(item.findtext("title"))
        desc = _clean_txt(item.findtext("description"))
        link = _clean_txt(item.findtext("link"))
        if not title:
            continue
        blob = f"{title} {desc}"
        if _NON_SOCCER_RE.search(blob):
            continue
        if require_transfer_kw and not _TRANSFER_KW_RE.search(blob):
            continue

        hotness, status, stage = compute_rumor_hotness(title, desc, tier=tier)
        hid = hashlib.sha1(f"tr:{source_name}:{title[:48]}".encode("utf-8")).hexdigest()[:10]
        # استخراج مبلغ احتمالی از متن
        m_fee = re.search(r"[€£]\s*(\d+(?:\.\d+)?)\s*m", blob, re.IGNORECASE)
        fixed_val = float(m_fee.group(1)) if m_fee else None

        prob_est = 88 if status == "done" else (74 if status == "hot" else (62 if status == "bid" else (55 if status == "hijack" else 42)))
        out.append({
            "id": f"tr_{hid}",
            "headline_en": title,
            "lead_en": desc[:420],
            "title": title[:80],
            "window": "پنجره نقل‌وانتقالات فوتبال",
            "windowEn": "TRANSFER RADAR LIVE",
            "dealCode": f"TR-{hid[:4].upper()}",
            "updated": "رصد زنده امروز",
            "tierBadge": f"TIER {tier} | {'منبع معتبر' if tier == 1 else 'در حال رصد'}",
            "source": source_name,
            "source_url": link,
            "tier": tier,
            "hotness": hotness,
            "status": status,
            "prob": prob_est,
            "stayProb": max(5, round((100 - prob_est) * 0.55)),
            "stage": stage,
            "lang": "en",
            "player": {
                "name": title[:38],
                "nameEn": "",
                "pos": "",
                "age": None,
                "nat": "",
                "flag": "",
                "num": None,
                "contractUntil": "",
            },
            "from": {"name": "", "sub": "", "code": "FRM", "color": "#10B981", "secondary": "#FFFFFF"},
            "to": {"name": "", "sub": "", "code": "DST", "color": "#E62E45", "secondary": "#FFFFFF"},
            "finance": {
                "fixed": fixed_val,
                "addon": 0.0 if fixed_val is not None else None,
                "salary": None,
                "years": None,
                "marketVal": None,
                "modelVal": None,
                "dealType": "شایعه نقل‌وانتقال",
                "mv": None,
            },
            "tacticalFit": None,
            "credibility": {
                "score": 88 if tier == 1 else 72,
                "sources": [{"name": source_name, "outlet": source_name, "tier": tier, "conf": 88 if tier == 1 else 72, "time": "امروز"}],
            },
            "stats": None,
            "valuation": None,
            "rivals": [],
            "verdict": None,
        })
        if len(out) >= max_items:
            break
    return out


def fetch_live_transfer_rumors(*, force_refresh: bool = False, timeout: float = 8.0) -> list[dict[str, Any]]:
    """دریافت و رتبه‌بندی داغ‌ترین شایعات نقل‌وانتقالات از ۵ فید رایگان مستقل."""
    now = time.monotonic()
    if not force_refresh and _RUMOR_CACHE["items"] and (now - _RUMOR_CACHE["ts"]) < _CACHE_TTL_SEC:
        return list(_RUMOR_CACHE["items"])

    headers = {"User-Agent": USER_AGENT, "Accept": "application/rss+xml,application/xml,text/xml,*/*"}
    combined: list[dict[str, Any]] = []
    seen: set[str] = set()

    for src_name, url, tier in TRANSFER_FEEDS:
        req_kw = "transfer-window" not in url  # فید اختصاصی Transfer Window گاردین نیازی به فیلتر کلمه ندارد
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if getattr(resp, "status", 200) != 200:
                    continue
                raw = resp.read()
                for it in parse_transfer_rss_xml(raw, source_name=src_name, tier=tier, require_transfer_kw=req_kw, max_items=7):
                    sig = re.sub(r"[^a-z0-9]", "", it["headline_en"].lower())[:32]
                    if sig and sig not in seen:
                        seen.add(sig)
                        combined.append(it)
        except Exception as e:
            log.warning("transfer feed failed (%s): %s", src_name, e)

    # مرتب‌سازی نزولی بر اساس امتیاز داغ بودن (hotness)
    combined.sort(key=lambda x: int(x.get("hotness") or 0), reverse=True)
    _RUMOR_CACHE["ts"] = now
    _RUMOR_CACHE["items"] = combined
    return list(combined)


def get_top_hot_transfer_rumors(*, min_hotness: int = 72, limit: int = 5) -> list[dict[str, Any]]:
    """آماده برای اتوماسیون آینده: انتخاب خودکار صرفاً شایعات داغ با امتیاز بالای min_hotness."""
    items = fetch_live_transfer_rumors(force_refresh=False)
    return [it for it in items if int(it.get("hotness") or 0) >= min_hotness][:limit]


def list_transfer_items(*, include_live: bool = True, force_refresh: bool = False) -> dict[str, list[dict[str, Any]]]:
    live = fetch_live_transfer_rumors(force_refresh=force_refresh) if include_live else []
    presets = load_transfer_presets()
    return {"live": live, "presets": presets}


def enrich_transfer_rumor(
    item: dict[str, Any],
    *,
    llm_provider: Any = None,
    cancel_event: Any = None,
    fetch_network: bool = True,
) -> dict[str, Any]:
    """غنی‌سازی عمیق یک شایعه پس از انتخاب: متن کامل خبر + استخراج ساختاریافته فارسی با LLM + عکس و بیوی واقعی بازیکن."""
    out = json.loads(json.dumps(item, ensure_ascii=False))
    if str(out.get("id") or "").startswith("preset_"):
        return out

    excerpt = ""
    if fetch_network and out.get("source_url"):
        try:
            from src.xgpedia.providers.breaking_news_free import _fetch_article_excerpt
            excerpt = _fetch_article_excerpt(out.get("source_url"), timeout=5.0, max_chars=1600)
        except Exception:
            pass

    # ۱) استخراج ساختاریافتهٔ شایعه و جمع‌بندی تحریریه فارسی با LLM (مبتنی بر متن واقعی خبر)
    try:
        if llm_provider is None:
            from src.xgpedia.editorial.llm_provider import build_default_llm
            llm_provider = build_default_llm()
        if cancel_event is not None and hasattr(llm_provider, "cancel_event"):
            llm_provider.cancel_event = cancel_event

        sys_prompt = (
            "تو سردبیر ارشد نقل‌وانتقالات فوتبال XGPedia هستی. بر اساس تیتر و متن خبر زیر، اطلاعات شایعه را به فارسی دقیق و ژورنالیستی استخراج کن.\n"
            "قوانین اجباری:\n"
            "1) خروجی را فقط به‌صورت یک شیء JSON معتبر با دقیقاً همین کلیدها برگردان:\n"
            '{"status": "ok", "title": "...", "caption": "...", "bullets": ["...", "...", "..."], "source_note": "...", "uncertainties": []}\n'
            "- `status`: حتماً `\"ok\"` باشد.\n"
            "- `title`: تیتر تحلیل اختصاصی (حداکثر ۵۵ کاراکتر، بدون ستاره `*`).\n"
            "- `caption`: تحلیل خبری و فنی این انتقال به فارسی روان در ۲ پاراگراف (۲۶۰ تا ۴۲۰ کاراکتر، بدون ستاره `*`).\n"
            "- `bullets`: دقیقاً ۳ خط با فرمت مشخص:\n"
            "  خط ۱: `PLAYER: <نام فارسی بازیکن> | <نام انگلیسی بازیکن> | <پست کوتاه فارسی>`\n"
            "  خط ۲: `CLUBS: <باشگاه فعلی فارسی> | <باشگاه مقصد فارسی> | <مبلغ میلیون یورو فقط عدد یا null> | <وضعیت: hot/done/bid/radar/hijack> | <احتمال عدد بین 25 تا 95>`\n"
            "  خط ۳: یک نکتهٔ کلیدی کوتاه (حداکثر ۸۵ کاراکتر) دربارهٔ وضعیت مذاکره یا شرط اصلی انتقال.\n"
            "- `source_note`: نام منبع اصلی خبر.\n"
            "- `uncertainties`: آرایهٔ خالی `[]`.\n"
            "2) هرگز مبلغ یا آماری که در متن نیست اختراع نکن؛ اگر مبلغی در متن نیست جای مبلغ بنویس `null`."
        )
        draft = llm_provider.generate(
            sys_prompt,
            {
                "headline": out.get("headline_en") or out.get("title") or "",
                "lead": out.get("lead_en") or "",
                "article_excerpt": excerpt,
                "source": out.get("source") or "",
            },
        )
        clean = lambda s: re.sub(r"\*([^*]+)\*", r"\1", str(s or "")).replace("*", "").strip()
        v_title = clean(getattr(draft, "title", ""))
        v_body = clean(getattr(draft, "caption", ""))
        buls = [clean(b) for b in (getattr(draft, "bullets", None) or []) if clean(b)]

        v_tag = "رصد زندهٔ تحریریه XGPedia بر اساس آخرین گزارش‌های معتبر"
        for b in buls:
            if b.upper().startswith("PLAYER:"):
                parts = [x.strip() for x in b.split(":", 1)[1].split("|")]
                if len(parts) >= 1 and parts[0]:
                    out["player"]["name"] = parts[0]
                if len(parts) >= 2 and parts[1]:
                    out["player"]["nameEn"] = parts[1].upper()
                if len(parts) >= 3 and parts[2]:
                    out["player"]["pos"] = parts[2]
            elif b.upper().startswith("CLUBS:"):
                parts = [x.strip() for x in b.split(":", 1)[1].split("|")]
                if len(parts) >= 1 and parts[0]:
                    out["from"]["name"] = parts[0]
                    out["from"]["code"] = parts[0][:3].upper()
                if len(parts) >= 2 and parts[1]:
                    out["to"]["name"] = parts[1]
                    out["to"]["code"] = parts[1][:3].upper()
                if len(parts) >= 3 and parts[2].lower() != "null":
                    m_num = re.search(r"\d+(?:\.\d+)?", parts[2])
                    if m_num:
                        out["finance"]["fixed"] = float(m_num.group(0))
                        out["finance"]["addon"] = 0.0
                if len(parts) >= 4 and parts[3].lower() in ("hot", "done", "bid", "radar", "hijack"):
                    out["status"] = parts[3].lower()
                if len(parts) >= 5:
                    m_p = re.search(r"\d+", parts[4])
                    if m_p:
                        pr = max(20, min(96, int(m_p.group(0))))
                        out["prob"] = pr
                        out["stayProb"] = max(4, round((100 - pr) * 0.55))
            else:
                v_tag = b[:95]

        out["verdict"] = {
            "title": v_title or out["player"]["name"],
            "body": v_body or out.get("lead_en") or "",
            "tag": v_tag,
        }
        if out["to"]["name"]:
            out["rivals"] = [
                {"name": out["to"]["name"], "prob": out["prob"], "color": out["to"]["color"], "tag": "گزینه اصلی در گزارش"},
                {"name": f"ماندن در {out['from']['name'] or 'باشگاه فعلی'}", "prob": out["stayProb"], "color": "#64748B", "tag": "ادامه قرارداد فعلی"},
            ]
        out["lang"] = "fa"
    except Exception as e:
        log.warning("transfer LLM enrichment fallback (%s): %s", out.get("id"), e)
        if not out.get("verdict"):
            out["verdict"] = {
                "title": out.get("headline_en") or "شایعه نقل‌وانتقالاتی",
                "body": out.get("lead_en") or "",
                "tag": f"منبع: {out.get('source', 'Live Desk')}",
            }

    # ۲) غنی‌سازی عکس و مشخصات واقعی بازیکن از Wikipedia + TheSportsDB (منحصراً Soccer)
    en_name = str(out.get("player", {}).get("nameEn") or "").strip()
    if fetch_network and en_name and len(en_name) >= 3:
        try:
            from src.xgpedia.providers.birthday_free import (
                _enrich_from_thesportsdb,
                _enrich_from_wikipedia,
                fetch_player_photo_data_uri,
            )
            stub = {"wikiTitleEn": en_name, "nameEn": en_name}
            _enrich_from_wikipedia(stub, timeout=5.0)
            _enrich_from_thesportsdb(stub, timeout=5.0)
            if stub.get("age") and not out["player"].get("age"):
                out["player"]["age"] = stub["age"]
            if stub.get("nat") and not out["player"].get("nat"):
                out["player"]["nat"] = stub["nat"]
            if stub.get("jersey") and not out["player"].get("num"):
                out["player"]["num"] = stub["jersey"]
            if stub.get("club") and not out["from"].get("name"):
                out["from"]["name"] = stub["club"]
            if stub.get("photoUrl"):
                uri = fetch_player_photo_data_uri(stub["photoUrl"], timeout=6.0)
                if uri:
                    out["player"]["photoUrl"] = uri
        except Exception as e:
            log.info("transfer player bio/photo enrichment skipped (%s): %s", en_name, e)

    return out
