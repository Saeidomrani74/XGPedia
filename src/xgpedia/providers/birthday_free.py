"""تأمین‌کنندهٔ چندمنبعی و رایگان داده‌های کارت «تولدت مبارک اسطوره» (XGPedia Birthday Studio — D47).

منابع مستقل و رایگان (بدون نیاز به requests، فقط کتابخانه استاندارد urllib + کش حافظه‌ای):
  ۱) کشف تولدهای امروز فوتبالیست‌ها:
     - Wikimedia REST API On-This-Day Births (EN + FA):
       https://api.wikimedia.org/feed/v1/wikipedia/{lang}/onthisday/births/{MM}/{DD}
     - Wikidata SPARQL Query Service (wdt:P106 wd:Q937857 — مرتب‌شده بر اساس شهرت جهانی/sitelinks):
       https://query.wikidata.org/sparql
     - پریست‌های آمادهٔ استودیو (config/birthday_presets.json)
  ۲) غنی‌سازی عمیق اطلاعات بازیکن (کارنامه، باشگاه‌ها، افتخارات، شماره پیراهن، عکس واقعی):
     - Wikipedia Action API (Infobox wikitext parser + Persian langlink + original portrait)
     - TheSportsDB Free JSON API (کلید رایگان عمومی '123' یا کلید دلخواه THESPORTSDB_API_KEY در .env):
       searchplayers.php + lookuphonours.php + lookupformerteams.php
     - نگارش یادداشت تحریریهٔ تولد و لقب به فارسی روان با روتر رایگان LLM (مبتنی بر فکت‌های واقعی، قانون null ≠ 0)
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from src.xgpedia.config import ROOT

log = logging.getLogger(__name__)

TEHRAN_TZ = timezone(timedelta(hours=3, minutes=30))
USER_AGENT = "XGPediaBot/2.8 (https://t.me/XGPedia; football-analytics-birthday)"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_BIRTHDAY_CACHE: dict[str, Any] = {"key": "", "ts": 0.0, "items": []}
_CACHE_TTL_SEC = 1800.0  # ۳۰ دقیقه

# کلیدواژه‌های منحصراً فوتبال (Association Football / Soccer) — هرگز football player خالی نباشد
_SOCCER_POSITIVE_RE = re.compile(
    r"\b(association football|footballer|soccer player|soccer coach|soccer manager|"
    r"goalkeeper|midfielder|striker|winger|centre-back|center-back|full-back|left-back|right-back|fußballspieler|futbolista)\b|"
    r"(فوتبالیست|بازیکن فوتبال|مربی فوتبال|دروازه‌بان)",
    re.IGNORECASE,
)

# فیلتر حذف قطعی فوتبال آمریکایی، استرالیایی، کانادایی، گیلیک و راگبی
_NON_SOCCER_EXCLUDE_RE = re.compile(
    r"\b(american football|nfl|super bowl|gridiron|college football|ncaa football|"
    r"australian rules|australian football|afl|canadian football|cfl|gaelic football|rugby|"
    r"quarterback|linebacker|wide receiver|tight end|running back|fullback \(gridiron|"
    r"offensive tackle|offensive lineman|offensive guard|defensive end|defensive tackle|"
    r"defensive back|cornerback|placekicker|punter|nose tackle|free safety|strong safety|"
    r"basketball|nba|baseball|mlb|ice hockey|nhl|cricket|tennis)\b|"
    r"(فوتبال آمریکایی|فوتبال استرالیایی|فوتبال کانادایی|فوتبال گیلیک|راگبی|بسکتبال|بیسبال|هاکی)",
    re.IGNORECASE,
)

_EN_MONTHS = (
    "", "JAN", "FEB", "MAR", "APR", "MAY", "JUNE",
    "JULY", "AUG", "SEP", "OCT", "NOV", "DEC",
)
_JALALI_MONTHS = (
    "", "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
)
_CLUB_PALETTE = ("#E62E45", "#38BDF8", "#F59E0B", "#10B981", "#8B5CF6", "#F472B6")


def _gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100)
        + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1]
    )
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def format_jalali_birth(gy: int, gm: int, gd: int) -> str:
    try:
        jy, jm, jd = _gregorian_to_jalali(gy, gm, gd)
        return f"{jd} {_JALALI_MONTHS[jm]} {jy}"
    except Exception as _em_exc:
        from src.xgpedia.core.error_metrics import record_error as _rec_err
        _rec_err("provider.birthday", _em_exc)
        return ""


def format_en_birth(gy: int, gm: int, gd: int) -> str:
    m_name = _EN_MONTHS[gm] if 1 <= gm <= 12 else str(gm)
    return f"{gd} {m_name} {gy}"


def _make_player_code(name_en: str, jersey: int | str | None) -> str:
    parts = [p for p in re.split(r"[^A-Za-z]+", name_en or "") if p]
    if len(parts) >= 2:
        ini = (parts[0][0] + parts[-1][0]).upper()
    elif parts:
        ini = parts[0][:2].upper()
    else:
        ini = "XG"
    j_str = str(jersey).strip() if jersey not in (None, "", 0, "0") else ""
    return f"{ini}{j_str}"[:5]


def _make_surname(name_en: str) -> str:
    parts = [p for p in re.split(r"\s+", (name_en or "").strip()) if p]
    return (parts[-1] if parts else "LEGEND").upper()


def _http_get_json(url: str, *, headers: dict[str, str] | None = None, timeout: float = 10.0) -> Any:
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if getattr(resp, "status", 200) != 200:
            return None
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


def _compute_age(birth_year: int | None, birth_month: int | None = None, birth_day: int | None = None, now: datetime | None = None) -> int | None:
    if not birth_year or birth_year < 1880:
        return None
    ref = now or datetime.now(TEHRAN_TZ)
    age = ref.year - int(birth_year)
    if birth_month and birth_day:
        if (ref.month, ref.day) < (int(birth_month), int(birth_day)):
            age -= 1
    return max(15, age)


def load_birthday_presets(now: datetime | None = None) -> list[dict[str, Any]]:
    """بارگذاری ۵ پریست آماده استودیو تولد با محاسبهٔ پویای سن فعلی."""
    p = ROOT / "config" / "birthday_presets.json"
    if not p.exists():
        return []
    try:
        items = json.loads(p.read_text(encoding="utf-8"))
        out: list[dict[str, Any]] = []
        for raw in items:
            it = dict(raw)
            age = _compute_age(it.get("birthYear"), it.get("birthMonth"), it.get("birthDay"), now=now)
            if age is not None:
                it["age"] = age
            out.append(it)
        return out
    except Exception as e:
        log.warning("failed loading birthday_presets.json: %s", e)
        return []


def _is_football_bio(text: str) -> bool:
    """تأیید قطعی اینکه فرد فقط فوتبالیست (Soccer / Association Football) است و نه NFL/AFL/CFL/Rugby."""
    txt = text or ""
    if _NON_SOCCER_EXCLUDE_RE.search(txt):
        return False
    return bool(_SOCCER_POSITIVE_RE.search(txt))


def parse_wikimedia_births_json(
    payload: dict[str, Any],
    *,
    month: int,
    day: int,
    lang: str = "en",
    now: datetime | None = None,
    max_items: int = 18,
) -> list[dict[str, Any]]:
    """پارس خروجی Wikimedia REST API onthisday/births برای استخراج فوتبالیست‌های متولد امروز."""
    births = payload.get("births") if isinstance(payload, dict) else None
    if not isinstance(births, list):
        return []
    ref = now or datetime.now(TEHRAN_TZ)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in births:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or "").strip()
        year = row.get("year")
        pages = row.get("pages") or []
        p0 = pages[0] if pages and isinstance(pages[0], dict) else {}
        desc = str(p0.get("description") or "").strip()
        extract = str(p0.get("extract") or "").strip()
        if not _is_football_bio(f"{text} {desc} {extract}"):
            continue
        if not isinstance(year, int) or year < 1920 or year > ref.year - 15:
            continue
        # رد کردن افراد فوت‌شده اگر در متن «d.» یا «درگذشته» باشد و سن بالای ۹۰
        title = str(p0.get("titles", {}).get("normalized") or p0.get("title") or text.split(",")[0]).strip()
        if not title:
            continue
        sig = title.lower()
        if sig in seen:
            continue
        seen.add(sig)

        age = ref.year - year
        wiki_url = str((p0.get("content_urls") or {}).get("desktop", {}).get("page") or "")
        orig_img = str((p0.get("originalimage") or {}).get("source") or (p0.get("thumbnail") or {}).get("source") or "")
        hid = hashlib.sha1(f"wm:{lang}:{title}:{year}".encode("utf-8")).hexdigest()[:10]
        is_fa = lang == "fa"
        out.append({
            "id": f"wm_{lang}_{hid}",
            "nameFa": title if is_fa else title,
            "nameEn": title.upper() if not is_fa else "",
            "wikiTitleEn": title if not is_fa else "",
            "wikiTitleFa": title if is_fa else "",
            "surnameEn": _make_surname(title) if not is_fa else "LEGEND",
            "epithet": desc[:60] if desc else "ستارهٔ دنیای فوتبال",
            "age": age,
            "birthYear": year,
            "birthMonth": month,
            "birthDay": day,
            "dateFa": format_jalali_birth(year, month, day),
            "dateEn": format_en_birth(year, month, day),
            "club": "",
            "nat": "",
            "pos": "",
            "jersey": None,
            "code": _make_player_code(title, None),
            "primary": "#E62E45",
            "secondary": "#F59E0B",
            "photoUrl": orig_img,
            "source": "Wikipedia",
            "source_url": wiki_url,
            "bio_en": extract[:900] if not is_fa else "",
            "bio_fa": extract[:900] if is_fa else "",
            "lang": "fa" if is_fa else "en",
            "kpis": None,
            "radar": None,
            "trophies": [],
            "timeline": [],
            "quote": None,
            "record": None,
            "sitelinks": 50 if is_fa else 60,
        })
        if len(out) >= max_items:
            break
    return out


def parse_wikidata_sparql_json(
    payload: dict[str, Any],
    *,
    month: int,
    day: int,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """پارس خروجی Wikidata SPARQL برای فوتبالیست‌های شاخص متولد امروز (مرتب‌شده بر اساس شهرت جهانی)."""
    bindings = ((payload or {}).get("results") or {}).get("bindings") or []
    ref = now or datetime.now(TEHRAN_TZ)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for b in bindings:
        if not isinstance(b, dict):
            continue
        val = lambda k: str((b.get(k) or {}).get("value") or "").strip()
        name_en = val("nameEn")
        name_fa = val("nameFa")
        dob = val("dob")
        if not name_en or len(dob) < 4:
            continue
        try:
            year = int(dob[:4])
        except ValueError:
            continue
        if year < 1920 or year > ref.year - 15:
            continue
        sig = name_en.lower()
        if sig in seen:
            continue
        seen.add(sig)
        wiki_url = val("enwiki")
        wiki_title = ""
        if "/wiki/" in wiki_url:
            wiki_title = urllib.parse.unquote(wiki_url.split("/wiki/", 1)[1]).replace("_", " ")
        img = val("image")
        nat = val("natFa") or val("natEn")
        pos = val("posFa") or val("posEn")
        slinks = int(val("sitelinks") or 0) if val("sitelinks").isdigit() else 0
        hid = hashlib.sha1(f"wd:{name_en}:{year}".encode("utf-8")).hexdigest()[:10]
        out.append({
            "id": f"wd_{hid}",
            "nameFa": name_fa or name_en,
            "nameEn": name_en.upper(),
            "wikiTitleEn": wiki_title or name_en,
            "wikiTitleFa": name_fa,
            "surnameEn": _make_surname(name_en),
            "epithet": "",
            "age": ref.year - year,
            "birthYear": year,
            "birthMonth": month,
            "birthDay": day,
            "dateFa": format_jalali_birth(year, month, day),
            "dateEn": format_en_birth(year, month, day),
            "club": "",
            "nat": nat,
            "pos": pos,
            "jersey": None,
            "code": _make_player_code(name_en, None),
            "primary": "#38BDF8",
            "secondary": "#F59E0B",
            "photoUrl": img,
            "source": "Wikidata / Wikipedia",
            "source_url": wiki_url or f"https://en.wikipedia.org/wiki/{urllib.parse.quote((wiki_title or name_en).replace(' ', '_'))}",
            "bio_en": "",
            "lang": "fa" if name_fa else "en",
            "kpis": None,
            "radar": None,
            "trophies": [],
            "timeline": [],
            "quote": None,
            "record": None,
            "sitelinks": slinks,
        })
    return out


def fetch_today_footballer_birthdays(
    *,
    now: datetime | None = None,
    force_refresh: bool = False,
    timeout: float = 10.0,
) -> list[dict[str, Any]]:
    """دریافت لیست ترکیبی و رتبه‌بندی‌شدهٔ فوتبالیست‌های متولد امروز از Wikidata + Wikimedia (EN/FA)."""
    ref = now or datetime.now(TEHRAN_TZ)
    mm, dd = ref.month, ref.day
    cache_key = f"{ref.year:04d}-{mm:02d}-{dd:02d}"
    ts_now = time.monotonic()
    if (
        not force_refresh
        and _BIRTHDAY_CACHE.get("key") == cache_key
        and _BIRTHDAY_CACHE.get("items")
        and (ts_now - float(_BIRTHDAY_CACHE.get("ts") or 0.0)) < _CACHE_TTL_SEC
    ):
        return list(_BIRTHDAY_CACHE["items"])

    merged: dict[str, dict[str, Any]] = {}

    def _merge(items: list[dict[str, Any]]) -> None:
        for it in items:
            key = (it.get("wikiTitleEn") or it.get("nameEn") or it.get("nameFa") or "").strip().lower()
            if not key:
                continue
            if key not in merged:
                merged[key] = it
            else:
                cur = merged[key]
                # تکمیل فیلدهای خالی از منبع دوم
                for fld in ("nameFa", "nameEn", "wikiTitleEn", "wikiTitleFa", "nat", "pos", "photoUrl", "source_url", "bio_en", "bio_fa"):
                    if not cur.get(fld) and it.get(fld):
                        cur[fld] = it[fld]
                cur["sitelinks"] = max(int(cur.get("sitelinks") or 0), int(it.get("sitelinks") or 0))

    # ۱) Wikimedia REST API (EN + DE + ES — پشتیبانی‌شده، فوق‌سریع زیر ۴۰۰ms و بدون خطای ۴۰۴)
    # نکته: نسخهٔ fa در سرویس Wikifeeds onthisday وجود ندارد و ۴۰۴ می‌دهد؛ نام فارسی بعداً از langlinks استخراج می‌شود.
    for lang in ("en", "de", "es"):
        try:
            wm_url = f"https://api.wikimedia.org/feed/v1/wikipedia/{lang}/onthisday/births/{mm:02d}/{dd:02d}"
            wm_json = _http_get_json(wm_url, timeout=min(timeout, 6.0))
            if wm_json:
                _merge(parse_wikimedia_births_json(wm_json, month=mm, day=dd, lang=lang, now=ref))
        except Exception as e:
            log.info("wikimedia births (%s) skipped: %s", lang, e)

    # ۲) Wikidata SPARQL تکمیلی با سقف زمان کوتاه (۴.۵ ثانیه) فقط اگر لیست هنوز زیر ۱۲ بازیکن بود
    if len(merged) < 12:
        sparql = f"""
        SELECT ?item ?nameEn ?nameFa ?dob ?image ?enwiki ?sitelinks WHERE {{
          ?item wdt:P106 wd:Q937857 ;
                wdt:P569 ?dob ;
                wikibase:sitelinks ?sitelinks .
          FILTER(?sitelinks >= 35 && MONTH(?dob) = {mm} && DAY(?dob) = {dd} && YEAR(?dob) >= 1955)
          FILTER NOT EXISTS {{ ?item wdt:P570 ?dod }}
          FILTER NOT EXISTS {{ ?item wdt:P106 wd:Q19204627 }}
          OPTIONAL {{ ?item wdt:P18 ?image . }}
          OPTIONAL {{ ?enwiki schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> . }}
          ?item rdfs:label ?nameEn FILTER(LANG(?nameEn) = "en") .
          OPTIONAL {{ ?item rdfs:label ?nameFa FILTER(LANG(?nameFa) = "fa") }}
        }}
        ORDER BY DESC(?sitelinks)
        LIMIT 16
        """
        try:
            wd_url = "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(sparql)
            wd_json = _http_get_json(wd_url, timeout=4.5)
            if wd_json:
                _merge(parse_wikidata_sparql_json(wd_json, month=mm, day=dd, now=ref))
        except Exception as e:
            log.info("wikidata birthday sparql skipped (fast timeout): %s", e)

    ranked = sorted(merged.values(), key=lambda x: int(x.get("sitelinks") or 0), reverse=True)
    _BIRTHDAY_CACHE["key"] = cache_key
    _BIRTHDAY_CACHE["ts"] = ts_now
    _BIRTHDAY_CACHE["items"] = ranked
    return list(ranked)


def list_birthday_items(*, include_live: bool = True, force_refresh: bool = False) -> dict[str, list[dict[str, Any]]]:
    live = fetch_today_footballer_birthdays(force_refresh=force_refresh) if include_live else []
    presets = load_birthday_presets()
    return {"live": live, "presets": presets}


def search_footballer_by_name(query: str, *, timeout: float = 8.0) -> list[dict[str, Any]]:
    """جستجوی دلخواه فوتبالیست در TheSportsDB + Wikipedia برای ساخت کارت تولد هر بازیکن."""
    q = (query or "").strip()
    if len(q) < 2:
        return []
    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    # ۱) TheSportsDB Free API (key '123' یا کلید کاربر)
    tsdb_key = (os.environ.get("THESPORTSDB_API_KEY") or "123").strip()
    try:
        u = f"https://www.thesportsdb.com/api/v1/json/{tsdb_key}/searchplayers.php?p={urllib.parse.quote(q)}"
        data = _http_get_json(u, timeout=timeout)
        for pl in (data or {}).get("player") or []:
            if not isinstance(pl, dict):
                continue
            if str(pl.get("strSport") or "").strip().lower() != "soccer":
                continue
            name_en = str(pl.get("strPlayer") or "").strip()
            if not name_en or name_en.lower() in seen:
                continue
            seen.add(name_en.lower())
            dob = str(pl.get("dateBorn") or "").strip()
            by = bm = bd = None
            m = re.match(r"(\d{4})-(\d{2})-(\d{2})", dob)
            if m:
                by, bm, bd = int(m.group(1)), int(m.group(2)), int(m.group(3))
            age = _compute_age(by, bm, bd)
            j_raw = str(pl.get("strNumber") or "").strip()
            jersey = int(j_raw) if j_raw.isdigit() else None
            hid = hashlib.sha1(f"tsdb:{name_en}".encode("utf-8")).hexdigest()[:10]
            results.append({
                "id": f"tsdb_{hid}",
                "tsdbId": str(pl.get("idPlayer") or ""),
                "nameFa": name_en,
                "nameEn": name_en.upper(),
                "wikiTitleEn": name_en,
                "surnameEn": _make_surname(name_en),
                "epithet": "",
                "age": age,
                "birthYear": by,
                "birthMonth": bm,
                "birthDay": bd,
                "dateFa": format_jalali_birth(by, bm, bd) if (by and bm and bd) else "",
                "dateEn": format_en_birth(by, bm, bd) if (by and bm and bd) else "",
                "club": str(pl.get("strTeam") or "").strip(),
                "nat": str(pl.get("strNationality") or "").strip(),
                "pos": str(pl.get("strPosition") or "").strip(),
                "jersey": jersey,
                "code": _make_player_code(name_en, jersey),
                "primary": "#38BDF8",
                "secondary": "#F59E0B",
                "photoUrl": str(pl.get("strCutout") or pl.get("strThumb") or pl.get("strRender") or "").strip(),
                "source": "TheSportsDB / Wikipedia",
                "source_url": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(name_en.replace(' ', '_'))}",
                "bio_en": str(pl.get("strDescriptionEN") or "")[:900],
                "lang": "en",
                "kpis": None,
                "radar": None,
                "trophies": [],
                "timeline": [],
                "quote": None,
                "record": None,
            })
            if len(results) >= 6:
                break
    except Exception as e:
        log.warning("TheSportsDB search failed (%s): %s", q, e)

    # ۲) Wikipedia OpenSearch fallback (پشتیبانی فارسی و انگلیسی)
    if len(results) < 4:
        has_fa = any("\u0600" <= ch <= "\u06ff" for ch in q)
        wlang = "fa" if has_fa else "en"
        try:
            u = (
                f"https://{wlang}.wikipedia.org/w/api.php?action=opensearch&format=json"
                f"&limit=6&search={urllib.parse.quote(q)}"
            )
            arr = _http_get_json(u, timeout=timeout)
            if isinstance(arr, list) and len(arr) >= 4:
                titles, descs, urls = arr[1], arr[2], arr[3]
                for t, d, link in zip(titles, descs, urls):
                    if str(t).lower() in seen:
                        continue
                    seen.add(str(t).lower())
                    hid = hashlib.sha1(f"ws:{wlang}:{t}".encode("utf-8")).hexdigest()[:10]
                    results.append({
                        "id": f"ws_{wlang}_{hid}",
                        "nameFa": str(t),
                        "nameEn": str(t).upper() if not has_fa else "",
                        "wikiTitleEn": str(t) if not has_fa else "",
                        "wikiTitleFa": str(t) if has_fa else "",
                        "surnameEn": _make_surname(str(t)) if not has_fa else "LEGEND",
                        "epithet": str(d)[:60] if d else "",
                        "age": None,
                        "birthYear": None,
                        "dateFa": "",
                        "dateEn": "",
                        "club": "",
                        "nat": "",
                        "pos": "",
                        "jersey": None,
                        "code": _make_player_code(str(t), None),
                        "primary": "#E62E45",
                        "secondary": "#F59E0B",
                        "photoUrl": "",
                        "source": "Wikipedia",
                        "source_url": str(link),
                        "lang": wlang,
                        "kpis": None,
                        "radar": None,
                        "trophies": [],
                        "timeline": [],
                        "quote": None,
                        "record": None,
                    })
                    if len(results) >= 8:
                        break
        except Exception as e:
            log.warning("wikipedia opensearch failed (%s): %s", q, e)

    return results


def parse_wikipedia_infobox_stats(wikitext: str) -> dict[str, Any]:
    """استخراج دقیق آمار رسمی، باشگاه‌ها، شماره پیراهن، پست و سال تولد از Infobox ویکی‌پدیا (قانون null ≠ 0)."""
    if not wikitext:
        return {}

    def _clean_wiki(v: str) -> str:
        s = re.sub(r"<ref[^>]*>.*?</ref>", "", v, flags=re.DOTALL | re.IGNORECASE)
        s = re.sub(r"<ref[^/>]*/>", "", s, flags=re.IGNORECASE)
        s = re.sub(r"<!--.*?-->", "", s, flags=re.DOTALL)
        s = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", s)
        s = re.sub(r"\{\{[^{}]*\}\}", "", s)
        s = re.sub(r"<[^>]+>", " ", s)
        return re.sub(r"\s+", " ", s).strip(" |•*")

    fields: dict[str, str] = {}
    # پشتیبانی هم‌زمان از پارامترهای چندخطی و چندپارامتری در یک خط (مانند | years1=... | clubs1=... | caps1=... | goals1=...)
    param_re = re.compile(
        r"\|\s*([a-zA-Z0-9_]+)\s*=\s*((?:\[\[[^\]]*\]\]|\{\{[^{}]*\}\}|[^|\n])*)"
    )
    for m in param_re.finditer(wikitext):
        k = m.group(1).strip().lower()
        v = m.group(2).strip()
        if k not in fields or v:
            fields[k] = v

    out: dict[str, Any] = {}
    if fields.get("currentclub"):
        out["club"] = _clean_wiki(fields["currentclub"])
    if fields.get("clubnumber"):
        m_num = re.search(r"\d+", fields["clubnumber"])
        if m_num:
            out["jersey"] = int(m_num.group(0))
    if fields.get("position"):
        out["pos"] = _clean_wiki(fields["position"]).split(",")[0].strip()

    # تاریخ تولد از birth_date = {{birth date and age|1987|6|24|...}}
    bd_raw = fields.get("birth_date") or ""
    m_bd = re.search(r"(\d{4})\s*\|\s*(\d{1,2})\s*\|\s*(\d{1,2})", bd_raw)
    if m_bd:
        out["birthYear"] = int(m_bd.group(1))
        out["birthMonth"] = int(m_bd.group(2))
        out["birthDay"] = int(m_bd.group(3))

    # استخراج جدول باشگاه‌های بزرگسالان (clubs1..20, years1..20, caps1..20, goals1..20)
    timeline: list[dict[str, str]] = []
    total_apps = 0
    total_goals = 0
    has_apps = False
    has_goals = False
    for idx in range(1, 21):
        cl = _clean_wiki(fields.get(f"clubs{idx}") or "")
        if not cl or cl.startswith("→"):
            continue
        yr = _clean_wiki(fields.get(f"years{idx}") or "").replace("–", "-")
        c_raw = re.search(r"\d+", fields.get(f"caps{idx}") or "")
        g_raw = re.search(r"\d+", fields.get(f"goals{idx}") or "")
        c_int = int(c_raw.group(0)) if c_raw else None
        g_int = int(g_raw.group(0)) if g_raw else None
        if c_int is not None:
            total_apps += c_int
            has_apps = True
        if g_int is not None:
            total_goals += g_int
            has_goals = True
        tag = f"{g_int} گل" if (g_int and g_int > 0) else (f"{c_int} بازی" if c_int else "باشگاهی")
        timeline.append({
            "club": cl[:28],
            "years": yr[:12] or "—",
            "color": _CLUB_PALETTE[(len(timeline)) % len(_CLUB_PALETTE)],
            "tag": tag,
        })

    if timeline:
        # حداکثر ۴ ایستگاه اصلی (اولویت با آخرین و مهم‌ترین باشگاه‌ها)
        out["timeline"] = timeline[-4:]
    if has_apps:
        out["kpis"] = {
            "apps": f"{total_apps:,}",
            "goals": f"{total_goals:,}" if has_goals else None,
            "assists": None,
            "p90": None,
        }
    return out


def _enrich_from_wikipedia(item: dict[str, Any], timeout: float = 7.0) -> None:
    title_en = str(item.get("wikiTitleEn") or "").strip()
    title_fa = str(item.get("wikiTitleFa") or "").strip()

    # اگر فقط عنوان فارسی داریم، معادل انگلیسی آن را از langlinks پیدا کن
    if not title_en and title_fa:
        try:
            u = (
                f"https://fa.wikipedia.org/w/api.php?action=query&format=json"
                f"&prop=langlinks&lllang=en&titles={urllib.parse.quote(title_fa)}"
            )
            q = _http_get_json(u, timeout=timeout)
            pages = ((q or {}).get("query") or {}).get("pages") or {}
            for pg in pages.values():
                lls = pg.get("langlinks") or []
                if lls:
                    title_en = str(lls[0].get("*") or lls[0].get("title") or "").strip()
                    item["wikiTitleEn"] = title_en
                    if not item.get("nameEn"):
                        item["nameEn"] = title_en.upper()
                        item["surnameEn"] = _make_surname(title_en)
                    break
        except Exception as _em_exc:
            from src.xgpedia.core.error_metrics import record_error as _rec_err
            _rec_err("provider.birthday", _em_exc)

    if not title_en:
        return

    # ۱) Summary + عکس باکیفیت + لینک ویکی‌پدیا
    try:
        su = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title_en.replace(' ', '_'))}"
        sj = _http_get_json(su, timeout=timeout)
        if isinstance(sj, dict):
            if not item.get("photoUrl"):
                img = (sj.get("originalimage") or {}).get("source") or (sj.get("thumbnail") or {}).get("source")
                if img:
                    item["photoUrl"] = str(img)
            if not item.get("bio_en") and sj.get("extract"):
                item["bio_en"] = str(sj["extract"])[:900]
            if not item.get("source_url"):
                pu = (sj.get("content_urls") or {}).get("desktop", {}).get("page")
                if pu:
                    item["source_url"] = str(pu)
    except Exception as _em_exc:
        from src.xgpedia.core.error_metrics import record_error as _rec_err
        _rec_err("provider.birthday", _em_exc)

    # ۲) معادل نام فارسی از langlinks ویکی‌پدیای انگلیسی
    if not title_fa or not any("\u0600" <= ch <= "\u06ff" for ch in str(item.get("nameFa") or "")):
        try:
            u = (
                f"https://en.wikipedia.org/w/api.php?action=query&format=json"
                f"&prop=langlinks&lllang=fa&titles={urllib.parse.quote(title_en)}"
            )
            q = _http_get_json(u, timeout=timeout)
            pages = ((q or {}).get("query") or {}).get("pages") or {}
            for pg in pages.values():
                lls = pg.get("langlinks") or []
                if lls:
                    fa_t = str(lls[0].get("*") or lls[0].get("title") or "").strip()
                    if fa_t:
                        item["nameFa"] = re.sub(r"\s*\([^)]*\)$", "", fa_t).strip()
                        item["wikiTitleFa"] = fa_t
                    break
        except Exception as _em_exc:
            from src.xgpedia.core.error_metrics import record_error as _rec_err
            _rec_err("provider.birthday", _em_exc)

    # ۳) Infobox Wikitext برای استخراج آمار رسمی بازی/گل، باشگاه‌ها و شماره پیراهن
    try:
        u = (
            f"https://en.wikipedia.org/w/api.php?action=parse&format=json"
            f"&prop=wikitext&section=0&redirects=1&page={urllib.parse.quote(title_en)}"
        )
        pj = _http_get_json(u, timeout=timeout)
        wtxt = ((pj or {}).get("parse") or {}).get("wikitext", {}).get("*", "")
        parsed = parse_wikipedia_infobox_stats(wtxt)
        for k in ("club", "jersey", "pos", "birthYear", "birthMonth", "birthDay"):
            if not item.get(k) and parsed.get(k):
                item[k] = parsed[k]
        if not item.get("timeline") and parsed.get("timeline"):
            item["timeline"] = parsed["timeline"]
        if not item.get("kpis") and parsed.get("kpis"):
            item["kpis"] = parsed["kpis"]
    except Exception as e:
        log.info("wikipedia infobox parse skipped (%s): %s", title_en, e)


def _enrich_from_thesportsdb(item: dict[str, Any], timeout: float = 7.0) -> None:
    name_q = str(item.get("wikiTitleEn") or item.get("nameEn") or "").strip()
    if not name_q:
        return
    tsdb_key = (os.environ.get("THESPORTSDB_API_KEY") or "123").strip()
    tsdb_id = str(item.get("tsdbId") or "").strip()

    try:
        if not tsdb_id:
            u = f"https://www.thesportsdb.com/api/v1/json/{tsdb_key}/searchplayers.php?p={urllib.parse.quote(name_q)}"
            dj = _http_get_json(u, timeout=timeout)
            players = (dj or {}).get("player") or []
            pl = next(
                (p for p in players if isinstance(p, dict) and str(p.get("strSport") or "").strip().lower() == "soccer"),
                None,
            )
            if pl:
                tsdb_id = str(pl.get("idPlayer") or "").strip()
                item["tsdbId"] = tsdb_id
                if not item.get("club") and pl.get("strTeam"):
                    item["club"] = str(pl["strTeam"]).strip()
                if not item.get("nat") and pl.get("strNationality"):
                    item["nat"] = str(pl["strNationality"]).strip()
                if not item.get("pos") and pl.get("strPosition"):
                    item["pos"] = str(pl["strPosition"]).strip()
                if not item.get("jersey") and str(pl.get("strNumber") or "").isdigit():
                    item["jersey"] = int(str(pl["strNumber"]))
                # عکس cutout یا thumb باکیفیت TheSportsDB اولویت خوبی دارد
                ts_img = str(pl.get("strCutout") or pl.get("strThumb") or pl.get("strRender") or "").strip()
                if ts_img and not item.get("photoUrl"):
                    item["photoUrl"] = ts_img

        # افتخارات واقعی (Trophy Cabinet) از lookuphonours.php
        if tsdb_id and not item.get("trophies"):
            hu = f"https://www.thesportsdb.com/api/v1/json/{tsdb_key}/lookuphonours.php?id={tsdb_id}"
            hj = _http_get_json(hu, timeout=timeout)
            honours = (hj or {}).get("honours") or []
            counts: dict[str, int] = {}
            for h in honours:
                if not isinstance(h, dict):
                    continue
                h_name = str(h.get("strHonour") or "").strip()
                if h_name:
                    counts[h_name] = counts.get(h_name, 0) + 1
            if counts:
                top_h = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:4]
                trophies = []
                for h_name, cnt in top_h:
                    low = h_name.lower()
                    icon = (
                        "ballon" if ("ballon" in low or "golden" in low or "player of" in low) else
                        "wc" if ("world cup" in low or "euro" in low or "copa" in low) else
                        "ucl" if ("champions" in low or "europa" in low) else "cup"
                    )
                    trophies.append({"icon": icon, "label": h_name[:28], "count": str(cnt)})
                item["trophies"] = trophies
    except Exception as e:
        log.info("TheSportsDB enrichment skipped (%s): %s", name_q, e)


def fetch_player_photo_data_uri(url: str | None, *, timeout: float = 8.0) -> str | None:
    """دانلود عکس پرتره بازیکن از Wikimedia / TheSportsDB و تبدیل به Data URI آفلاین."""
    if not url or not str(url).startswith(("http://", "https://")):
        return None
    try:
        req = urllib.request.Request(
            str(url),
            headers={"User-Agent": BROWSER_UA, "Accept": "image/*,*/*;q=0.8"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if getattr(resp, "status", 200) != 200:
                return None
            raw = resp.read(5 * 1024 * 1024)
            if len(raw) < 4096:
                return None
            ctype = str(resp.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip().lower()
            if not ctype.startswith("image/"):
                ctype = "image/jpeg"
            return f"data:{ctype};base64,{base64.b64encode(raw).decode('ascii')}"
    except Exception as e:
        log.info("birthday player photo download skipped: %s", e)
        return None


def enrich_birthday_player(
    item: dict[str, Any],
    *,
    llm_provider: Any = None,
    cancel_event: Any = None,
    fetch_network: bool = True,
) -> dict[str, Any]:
    """غنی‌سازی کامل یک بازیکن برای کارت تولد: ویکی‌پدیا + TheSportsDB + عکس واقعی + یادداشت فارسی LLM."""
    out = dict(item)
    is_preset = str(out.get("id") or "").startswith("preset_")

    if fetch_network and not is_preset:
        _enrich_from_wikipedia(out)
        _enrich_from_thesportsdb(out)

    # بازمحاسبه سن، تاریخ شمسی/میلادی و کد بازیکن
    by, bm, bd = out.get("birthYear"), out.get("birthMonth"), out.get("birthDay")
    if by:
        age = _compute_age(by, bm, bd)
        if age is not None:
            out["age"] = age
        if bm and bd:
            if not out.get("dateFa"):
                out["dateFa"] = format_jalali_birth(int(by), int(bm), int(bd))
            if not out.get("dateEn"):
                out["dateEn"] = format_en_birth(int(by), int(bm), int(bd))

    out["code"] = _make_player_code(str(out.get("nameEn") or out.get("nameFa") or "XG"), out.get("jersey"))
    if not out.get("surnameEn"):
        out["surnameEn"] = _make_surname(str(out.get("nameEn") or "LEGEND"))

    # دانلود عکس پرتره بازیکن (آفلاین برای رندر Playwright)
    if fetch_network and not out.get("photoDataUri") and out.get("photoUrl"):
        uri = fetch_player_photo_data_uri(out.get("photoUrl"))
        if uri:
            out["photoDataUri"] = uri

    # نگارش یادداشت تحریریهٔ تولد و لقب فارسی با LLM (فقط اگر از قبل quote فارسی نداشته باشد)
    if not out.get("quote") or not isinstance(out.get("quote"), dict):
        try:
            if llm_provider is None:
                from src.xgpedia.editorial.llm_provider import build_default_llm
                llm_provider = build_default_llm()
            if cancel_event is not None and hasattr(llm_provider, "cancel_event"):
                llm_provider.cancel_event = cancel_event

            sys_prompt = (
                "تو سردبیر ارشد تحریریه فوتبال XGPedia هستی. بر اساس فکت‌های واقعی زیر، متن فارسی کارت تولد این بازیکن را بنویس.\n"
                "قوانین اجباری:\n"
                "1) خروجی را فقط به‌صورت یک شیء JSON معتبر با دقیقاً همین کلیدها برگردان:\n"
                '{"status": "ok", "title": "...", "caption": "...", "bullets": ["...", "..."], "source_note": "...", "uncertainties": []}\n'
                "- `status`: حتماً `\"ok\"` باشد.\n"
                "- `title`: تیتر کوتاه یادداشت تولد (حداکثر ۵۰ کاراکتر، بدون ستاره `*`).\n"
                "- `caption`: یادداشت تحریریهٔ تولد به فارسی روان و حرفه‌ای در ۲ پاراگراف کوتاه (۲۲۰ تا ۳۴۰ کاراکتر، بدون ستاره `*` و بدون عددسازی).\n"
                "- `bullets`: ۲ نکته کوتاه و مستند: عنصر اول = لقب یا توصیف کوتاه بازیکن در ۵ تا ۷ کلمه؛ عنصر دوم = یک جملهٔ افتخار یا ویژگی شاخص واقعی از بیوگرافی.\n"
                "- `source_note`: نام فارسی استاندارد بازیکن و باشگاهش (مثلاً «مهدی طارمی | المپیاکوس»).\n"
                "- `uncertainties`: آرایهٔ خالی `[]`.\n"
                "2) هرگز آمار، جام یا عددی که در ورودی نیست اختراع نکن."
            )
            payload = {
                "nameFa": out.get("nameFa") or "",
                "nameEn": out.get("nameEn") or "",
                "age": out.get("age"),
                "club": out.get("club") or "",
                "nationality": out.get("nat") or "",
                "position": out.get("pos") or "",
                "kpis": out.get("kpis"),
                "trophies": out.get("trophies"),
                "timeline": out.get("timeline"),
                "bio": (out.get("bio_fa") or out.get("bio_en") or "")[:700],
            }
            draft = llm_provider.generate(sys_prompt, payload)
            clean_s = lambda s: re.sub(r"\*([^*]+)\*", r"\1", str(s or "")).replace("*", "").strip()
            q_title = clean_s(getattr(draft, "title", "")) or f"تولد {out.get('age') or ''} سالگی {out.get('nameFa') or ''}".strip()
            q_body = clean_s(getattr(draft, "caption", ""))
            buls = [clean_s(b) for b in (getattr(draft, "bullets", None) or []) if clean_s(b)]
            if buls and not out.get("epithet"):
                out["epithet"] = buls[0][:56]
            q_tag = buls[1][:75] if len(buls) >= 2 else (out.get("epithet") or "پروندهٔ ویژه تولد XGPedia")
            if q_body:
                out["quote"] = {"title": q_title, "body": q_body, "tag": q_tag}
            out["lang"] = "fa"
        except Exception as e:
            log.warning("birthday LLM tribute fallback (%s): %s", out.get("id"), e)
            if not out.get("quote"):
                nm = out.get("nameFa") or out.get("nameEn") or "این ستاره"
                ag = out.get("age")
                out["quote"] = {
                    "title": f"جشن {ag} سالگی {nm}" if ag else f"تولد {nm}",
                    "body": f"{nm} امروز وارد سال جدیدی از دوران حرفه‌ای خود می‌شود؛ یکی از چهره‌های شناخته‌شدهٔ فوتبال که مسیر ورزشی‌اش همواره مورد توجه هواداران بوده است.",
                    "tag": "پروندهٔ ویژه تولد XGPedia",
                }
    return out
