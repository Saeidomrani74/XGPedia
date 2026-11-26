"""منابع زنده و ۱۰۰٪ رایگان اطلاعاتی مسابقه (بدون نیاز به کلید API):

1) استخراج زندهٔ نام سرمربی فعلی تیم‌ها از ویکی‌پدیای انگلیسی (با پارس مقاوم چندخطی Infobox)
   + پشتیبان ساختاری Wikidata (`P286` head coach) برای زمانی که الگوی ویکی‌پدیا تغییر کند
   + دریافت نام فارسی رسمی سرمربی از ویکی‌پدیای فارسی (langlinks / Wikidata fa label).
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
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
BBC_FOOTBALL_RSS = "https://feeds.bbci.co.uk/sport/football/rss.xml"

# نگاشت نام canonical تیم‌های لیگ برتر (و تیم‌های اخیر چمپیونشیپ) به عنوان دقیق مقالهٔ ویکی‌پدیای انگلیسی
TEAM_WIKI_TITLES: dict[str, str] = {
    # Premier League & English clubs
    "Arsenal": "Arsenal F.C.",
    "Aston Villa": "Aston Villa F.C.",
    "Bournemouth": "AFC Bournemouth",
    "Brentford": "Brentford F.C.",
    "Brighton": "Brighton & Hove Albion F.C.",
    "Burnley": "Burnley F.C.",
    "Chelsea": "Chelsea F.C.",
    "Coventry": "Coventry City F.C.",
    "Coventry City": "Coventry City F.C.",
    "Crystal Palace": "Crystal Palace F.C.",
    "Everton": "Everton F.C.",
    "Fulham": "Fulham F.C.",
    "Hull": "Hull City A.F.C.",
    "Hull City": "Hull City A.F.C.",
    "Ipswich": "Ipswich Town F.C.",
    "Ipswich Town": "Ipswich Town F.C.",
    "Leeds": "Leeds United F.C.",
    "Leeds United": "Leeds United F.C.",
    "Leicester": "Leicester City F.C.",
    "Liverpool": "Liverpool F.C.",
    "Manchester City": "Manchester City F.C.",
    "Manchester United": "Manchester United F.C.",
    "Newcastle": "Newcastle United F.C.",
    "Newcastle United": "Newcastle United F.C.",
    "Nottingham Forest": "Nottingham Forest F.C.",
    "Southampton": "Southampton F.C.",
    "Sunderland": "Sunderland A.F.C.",
    "Tottenham": "Tottenham Hotspur F.C.",
    "West Ham": "West Ham United F.C.",
    "Wolverhampton": "Wolverhampton Wanderers F.C.",
    # La Liga
    "Real Madrid": "Real Madrid CF",
    "Barcelona": "FC Barcelona",
    "Atletico Madrid": "Atlético Madrid",
    "Girona": "Girona FC",
    "Athletic Club": "Athletic Bilbao",
    "Villarreal": "Villarreal CF",
    "Real Sociedad": "Real Sociedad",
    "Real Betis": "Real Betis",
    "Sevilla": "Sevilla FC",
    "Valencia": "Valencia CF",
    "Osasuna": "CA Osasuna",
    "Celta Vigo": "RC Celta de Vigo",
    "Rayo Vallecano": "Rayo Vallecano",
    "Mallorca": "RCD Mallorca",
    "Getafe": "Getafe CF",
    "Alaves": "Deportivo Alavés",
    "Espanyol": "RCD Espanyol",
    "Las Palmas": "UD Las Palmas",
    "Real Valladolid": "Real Valladolid",
    "Leganes": "CD Leganés",
    # Bundesliga
    "Bayern Munich": "FC Bayern Munich",
    "Borussia Dortmund": "Borussia Dortmund",
    "Bayer Leverkusen": "Bayer 04 Leverkusen",
    "RB Leipzig": "RB Leipzig",
    "VfB Stuttgart": "VfB Stuttgart",
    "Eintracht Frankfurt": "Eintracht Frankfurt",
    "SC Freiburg": "SC Freiburg",
    "Borussia Monchengladbach": "Borussia Mönchengladbach",
    "Werder Bremen": "SV Werder Bremen",
    "VfL Wolfsburg": "VfL Wolfsburg",
    "Mainz 05": "1. FSV Mainz 05",
    "FC Augsburg": "FC Augsburg",
    "Union Berlin": "1. FC Union Berlin",
    "TSG Hoffenheim": "TSG 1899 Hoffenheim",
    "FC Heidenheim": "1. FC Heidenheim",
    "FC St. Pauli": "FC St. Pauli",
    "Holstein Kiel": "Holstein Kiel",
    "VfL Bochum": "VfL Bochum",
    # Serie A
    "Inter Milan": "Inter Milan",
    "AC Milan": "AC Milan",
    "Juventus": "Juventus FC",
    "Atalanta": "Atalanta BC",
    "Napoli": "SSC Napoli",
    "Bologna": "Bologna FC 1909",
    "AS Roma": "AS Roma",
    "Lazio": "SS Lazio",
    "Fiorentina": "ACF Fiorentina",
    "Torino": "Torino FC",
    "Udinese": "Udinese Calcio",
    "Genoa": "Genoa CFC",
    "Cagliari": "Cagliari Calcio",
    "Hellas Verona": "Hellas Verona FC",
    "Empoli": "Empoli FC",
    "Lecce": "US Lecce",
    "Parma": "Parma Calcio 1913",
    "Como": "Como 1907",
    "Monza": "AC Monza",
    "Venezia": "Venezia FC",
    # Ligue 1
    "Paris Saint-Germain": "Paris Saint-Germain F.C.",
    "AS Monaco": "AS Monaco FC",
    "Lille": "Lille OSC",
    "Brest": "Stade Brestois 29",
    "Marseille": "Olympique de Marseille",
    "Lyon": "Olympique Lyonnais",
    "Nice": "OGC Nice",
    "Lens": "RC Lens",
    "Rennes": "Stade Rennais F.C.",
    "Strasbourg": "RC Strasbourg Alsace",
    "Reims": "Stade de Reims",
    "Toulouse": "Toulouse FC",
    "Auxerre": "AJ Auxerre",
    "Nantes": "FC Nantes",
    "Angers": "Angers SCO",
    "Saint-Etienne": "AS Saint-Étienne",
    "Le Havre": "Le Havre AC",
    "Montpellier": "Montpellier HSC",
    # UCL European Clubs
    "Benfica": "S.L. Benfica",
    "Sporting CP": "Sporting CP",
    "FC Porto": "FC Porto",
    "PSV Eindhoven": "PSV Eindhoven",
    "Feyenoord": "Feyenoord",
    "Ajax": "AFC Ajax",
    "Celtic": "Celtic F.C.",
    "Club Brugge": "Club Brugge KV",
    "Shakhtar Donetsk": "FC Shakhtar Donetsk",
    "Red Bull Salzburg": "FC Red Bull Salzburg",
    "Galatasaray": "Galatasaray S.K. (football)",
    "Sabah FK": "Sabah FC",
    "Qarabag": "Qarabağ FK",
    "Olympiacos": "Olympiacos F.C.",
    "PAOK": "PAOK FC",
    "Panathinaikos": "Panathinaikos F.C.",
    "Fenerbahce": "Fenerbahçe S.K. (football)",
    "Besiktas": "Beşiktaş J.K.",
    "Slavia Prague": "SK Slavia Prague",
    "Sparta Prague": "AC Sparta Prague",
    "Viktoria Plzen": "FC Viktoria Plzeň",
    "Bodo/Glimt": "FK Bodø/Glimt",
    "FC Copenhagen": "F.C. Copenhagen",
    "Midtjylland": "FC Midtjylland",
    "Young Boys": "BSC Young Boys",
    "FC Basel": "FC Basel",
    "Union Saint-Gilloise": "Royale Union Saint-Gilloise",
    "Anderlecht": "R.S.C. Anderlecht",
    "Genk": "K.R.C. Genk",
    "Dinamo Zagreb": "GNK Dinamo Zagreb",
    "Red Star Belgrade": "Red Star Belgrade",
    "Rangers": "Rangers F.C.",
    "Sturm Graz": "SK Sturm Graz",
    "Slovan Bratislava": "ŠK Slovan Bratislava",
    "Ferencvaros": "Ferencvárosi TC",
    "Dynamo Kyiv": "FC Dynamo Kyiv",
    "Pafos": "Pafos FC",
    "Kairat": "FC Kairat",
    "FCSB": "FCSB",
    "Malmo FF": "Malmö FF",
    "SC Braga": "S.C. Braga",
    "AZ Alkmaar": "AZ Alkmaar",
    "FC Twente": "FC Twente",
    "Viking FK": "Viking FK",
    "Lech Poznan": "Lech Poznań",
    "NK Celje": "NK Celje",
    "Jagiellonia Bialystok": "Jagiellonia Białystok",
    "AC Omonia": "AC Omonia",
    "SCU Torreense": "S.C.U. Torreense",
    "Hapoel Be'er Sheva": "Hapoel Be'er Sheva F.C.",
    "NEC Nijmegen": "NEC Nijmegen",
    "OFI Crete": "OFI Crete F.C.",
    "Lillestrom SK": "Lillestrøm SK",
    "Levski Sofia": "PFC Levski Sofia",
    "Ararat-Armenia": "FC Ararat-Armenia",
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
    # برش در محل تگ‌های بازماندهٔ چندخطی مثل <ref name="..."> یا <br> یا کامنت باز
    s = re.split(r"<ref\b|<br\b|<!--", s, maxsplit=1, flags=re.IGNORECASE)[0]
    s = re.sub(r"<!--.*?-->", "", s, flags=re.DOTALL)
    # حفظ متن نمایشی لینک [[Target|Label]] -> Label و [[Target]] -> Target
    s = re.sub(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", r"\1", s)
    # حذف قالب‌های کوچک مثل {{nowrap|...}} با حفظ محتوا یا حذف {{flagicon|...}}
    s = re.sub(
        r"\{\{(?:nowrap|sortname)\|([^}|]+)(?:\|([^}]+))?\}\}",
        lambda m: f"{m.group(1)} {m.group(2) or ''}".strip(),
        s,
        flags=re.IGNORECASE,
    )
    # حذف قالب‌های تو در تو یا باقی‌مانده (مثل {{flagicon|ARG}} یا {{cite... باز)
    for _ in range(3):
        prev = s
        s = re.sub(r"\{\{[^{}]*\}\}", "", s)
        if s == prev:
            break
    s = s.split("{{")[0]
    # حذف برچسب‌های موقت مثل (interim) یا (caretaker)
    s = re.sub(r"\((?:interim|caretaker|acting|head coach|manager)[^)]*\)", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip(" \t\r\n,;-•|")
    return s


def parse_coach_from_wikitext(wikitext: str) -> str | None:
    """استخراج نام سرمربی فعلی از بخش Infobox ویکی‌پدیا (مقاوم به ref چندخطی و مقدار در خط بعد)."""
    if not wikitext:
        return None
    # اول همهٔ refها و کامنت‌های چندخطی را در کل متن پاک می‌کنیم تا خط فیلد manager خراب نشود
    stripped = re.sub(r"<!--.*?-->", "", wikitext, flags=re.DOTALL)
    stripped = re.sub(r"<ref[^>]*>.*?</ref>", "", stripped, flags=re.IGNORECASE | re.DOTALL)
    stripped = re.sub(r"<ref[^/>]*/>", "", stripped, flags=re.IGNORECASE)

    # تمرکز روی بلوک Infobox در صورت وجود تا فیلدهای مشابه بیرون از Infobox اشتباهاً خوانده نشوند
    ib_idx = stripped.lower().find("{{infobox")
    search_text = stripped[ib_idx:] if ib_idx != -1 else stripped

    lines = search_text.splitlines()
    field_re = re.compile(r"^\|\s*(?:manager|head[\s_]*coach|coach)\s*=\s*(.*)$", flags=re.IGNORECASE)
    for idx, line in enumerate(lines):
        m = field_re.match(line)
        if not m:
            continue
        raw_val = m.group(1).strip()
        if not raw_val:
            # گاهی مقدار در خط بعدی قرار می‌گیرد
            for nxt in lines[idx + 1 : idx + 4]:
                nxt_s = nxt.strip()
                if not nxt_s:
                    continue
                if nxt_s.startswith("|") or nxt_s.startswith("}}"):
                    break
                raw_val = nxt_s
                break
        cleaned = _clean_wikitext_value(raw_val)
        if cleaned and cleaned.lower() not in {"vacant", "tba", "tbd", "none", "n/a", "unknown"}:
            if 3 <= len(cleaned) <= 50:
                return cleaned
    return None


def parse_coach_qid_from_wikidata_claims(claims: dict[str, Any]) -> str | None:
    """استخراج شناسهٔ Wikidata (`Q...`) سرمربی فعلی از ویژگی `P286` (head coach)."""
    p286 = claims.get("P286") or []
    if not isinstance(p286, list) or not p286:
        return None

    def _extract_qid(stmt: dict[str, Any]) -> str | None:
        dv = ((stmt.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(dv, dict) and isinstance(dv.get("id"), str):
            return dv["id"]
        return None

    # اولویت ۱: ردیف preferred بدون تاریخ پایان (P582)
    for stmt in p286:
        if stmt.get("rank") == "preferred" and "P582" not in (stmt.get("qualifiers") or {}):
            qid = _extract_qid(stmt)
            if qid:
                return qid
    # اولویت ۲: هر ردیف غیر-deprecated بدون تاریخ پایان (P582) — جدیدترین (معمولاً آخرین در لیست یا بیشترین P580)
    active: list[tuple[str, str]] = []
    for stmt in p286:
        if stmt.get("rank") == "deprecated":
            continue
        quals = stmt.get("qualifiers") or {}
        if "P582" in quals:
            continue
        qid = _extract_qid(stmt)
        if not qid:
            continue
        start_time = ""
        p580 = quals.get("P580") or []
        if p580 and isinstance(p580, list):
            tval = ((p580[0].get("datavalue") or {}).get("value") or {})
            if isinstance(tval, dict):
                start_time = str(tval.get("time") or "")
        active.append((start_time, qid))
    if active:
        active.sort(key=lambda x: x[0])
        return active[-1][1]
    return None


def _fetch_coach_from_wikidata(
    client: httpx.Client, club_qid: str
) -> tuple[str | None, str | None]:
    """پشتیبان ساختاری: خواندن سرمربی فعلی (`P286`) و برچسب انگلیسی+فارسی از Wikidata."""
    try:
        r = client.get(
            WIKIDATA_API,
            params={
                "action": "wbgetentities",
                "ids": club_qid,
                "props": "claims",
                "format": "json",
            },
        )
        if r.status_code != 200:
            return None, None
        entity = ((r.json().get("entities") or {}).get(club_qid) or {})
        coach_qid = parse_coach_qid_from_wikidata_claims(entity.get("claims") or {})
        if not coach_qid:
            return None, None
        r2 = client.get(
            WIKIDATA_API,
            params={
                "action": "wbgetentities",
                "ids": coach_qid,
                "props": "labels",
                "languages": "en|fa",
                "format": "json",
            },
        )
        if r2.status_code != 200:
            return None, None
        labels = (((r2.json().get("entities") or {}).get(coach_qid) or {}).get("labels") or {})
        coach_en = ((labels.get("en") or {}).get("value") or "").strip() or None
        coach_fa = ((labels.get("fa") or {}).get("value") or "").strip() or None
        if not coach_en and not coach_fa:
            return None, None
        if coach_en:
            local_fa = translate_coach_fa(coach_en, allow_transliterate=False)
            if local_fa and local_fa != coach_en:
                coach_fa = local_fa
        return coach_en, (coach_fa or translate_coach_fa(coach_en))
    except Exception:
        return None, None


def fetch_live_coach_wikipedia(team_en: str, *, timeout: float = 10.0) -> tuple[str | None, str | None]:
    """دریافت زندهٔ `(coach_en, coach_fa)` برای یک تیم از ویکی‌پدیای انگلیسی + پشتیبان Wikidata.

    اگر مقالهٔ فارسی سرمربی وجود داشته باشد نام فارسی رسمی آن برگردانده می‌شود؛
    در غیر این صورت `translate_coach_fa(coach_en)` (دیکشنری + آوانویسی خودکار) استفاده می‌شود.
    """
    canon = canonical_team_name(team_en)
    candidates: list[str] = []
    for cand in (TEAM_WIKI_TITLES.get(canon), TEAM_WIKI_TITLES.get(team_en), canon, f"{canon} F.C."):
        if cand and cand not in candidates:
            candidates.append(cand)
    headers = {"User-Agent": "XGPediaBot/0.24 (https://xgpedia.local; football-analytics)"}

    def _query_title(client: httpx.Client, title: str) -> tuple[str, str | None]:
        r = client.get(
            WIKI_API_EN,
            params={
                "action": "query",
                "prop": "revisions|pageprops",
                "rvprop": "content",
                "rvslots": "main",
                "rvsection": "0",
                "ppprop": "wikibase_item",
                "redirects": "1",
                "format": "json",
                "titles": title,
            },
        )
        r.raise_for_status()
        pages = (r.json().get("query") or {}).get("pages") or {}
        for p in pages.values():
            if "missing" in p:
                continue
            wt = ""
            revs = p.get("revisions") or []
            if revs:
                slots = revs[0].get("slots") or {}
                wt = (slots.get("main") or {}).get("*") or revs[0].get("*") or ""
            pp = p.get("pageprops") or {}
            qid = pp.get("wikibase_item") if isinstance(pp.get("wikibase_item"), str) else None
            if wt or qid:
                return wt, qid
        return "", None

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            wikitext = ""
            club_qid: str | None = None
            for cand in candidates:
                wt, qid = _query_title(client, cand)
                if wt or qid:
                    wikitext, club_qid = wt, qid
                    break
            # پشتیبان هوشمند opensearch اگر عنوان دقیق باشگاه در جدول نبود
            if not wikitext and not club_qid:
                try:
                    rs = client.get(
                        WIKI_API_EN,
                        params={"action": "opensearch", "search": f"{canon} football club", "limit": "2", "format": "json"},
                    )
                    if rs.status_code == 200:
                        arr = rs.json()
                        if isinstance(arr, list) and len(arr) >= 2 and arr[1]:
                            wikitext, club_qid = _query_title(client, str(arr[1][0]))
                except Exception:
                    pass

            coach_en = parse_coach_from_wikitext(wikitext)
            if not coach_en:
                if club_qid:
                    return _fetch_coach_from_wikidata(client, club_qid)
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
