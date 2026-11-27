"""تأمین دادهٔ چندمنبعی و کاملاً رایگان برای کارت ماژولار «آزمایشگاه مصدومیت» (Injury Lab — D53).

منابع رایگان (بدون وابستگی به `requests`، منحصراً Association Football / Soccer):
  1. FPL Official Bootstrap & Fixtures API (`fantasy.premierleague.com/api/bootstrap-static/` + `fixtures/`)
     — وضعیت واقعی مصدومیت، شانس بازی بعد، ۴ بازی واقعی پیش‌رو با FDR، جایگزین‌های هم‌پست،
       و **عکس رسمی فصل جاری لیگ برتر** (`resources.premierleague.com/premierleague/photos/players/250x250/p{code}.png`)
  2. TheSportsDB (`strSport == "Soccer"`) — شماره پیراهن واقعی (`strNumber`) و عکس Cutout فصل جاری
  3. فیدهای RSS رایگان فوتبال (ESPN Soccer، BBC Sport Football، The Guardian Football) — منحصراً Soccer
  4. پریست‌های آماده (`config/injury_presets.json`) + غنی‌سازی فارسی LLM (`cancel_event`).

قانون `null ≠ 0`: هرگز شماره پیراهن جعلی (`id % 99`) تولید نمی‌شود؛ اگر شماره واقعی در دسترس نباشد `None` می‌ماند.
"""
from __future__ import annotations

import base64
import json
import re
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.xgpedia.config import ROOT

PRESETS_PATH = ROOT / "config" / "injury_presets.json"
USER_AGENT = "XGPediaBot/0.31 (+https://t.me/XGPedia)"

FPL_BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_FIXTURES_URL = "https://fantasy.premierleague.com/api/fixtures/?future=1"
PL_PHOTO_URLS = (
    "https://resources.premierleague.com/premierleague/photos/players/250x250/p{code}.png",
    "https://resources.premierleague.com/premierleague/photos/players/110x140/p{code}.png",
)

INJURY_RSS_FEEDS: list[tuple[str, str]] = [
    ("BBC Sport", "https://feeds.bbci.co.uk/sport/football/rss.xml"),
    ("The Guardian", "https://www.theguardian.com/football/rss"),
    ("ESPN Soccer", "https://www.espn.com/espn/rss/soccer/news"),
]

_NON_SOCCER_RE = re.compile(
    r"\b(nfl|nba|mlb|nhl|afl|cfl|ncaa|super\s*bowl|quarterback|touchdown|rugby|gaelic|cricket|tennis|golf|ufc|f1|boxing)\b",
    re.IGNORECASE,
)
_INJURY_KW_RE = re.compile(
    r"\b(injur\w*|hamstring|acl|cruciate|knee|ankle|groin|calf|achilles|shoulder|concussion|ruled out|sidelined|surgery|fitness|doubt|scan|mri|thigh|muscle|fracture)\b",
    re.IGNORECASE,
)
_CYRILLIC_CJK_RE = re.compile(r"[\u0400-\u04FF\u3040-\u30FF\u4E00-\u9FFF\uAC00-\uD7AF]+")

_FPL_CLUBS: dict[str, tuple[str, str, str, str]] = {
    "Arsenal": ("آرسنال", "ARS", "#EF0107", "#FFFFFF"),
    "Liverpool": ("لیورپول", "LIV", "#C8102E", "#F6EB61"),
    "Man City": ("منچسترسیتی", "MCI", "#38BDF8", "#1C2C5B"),
    "Chelsea": ("چلسی", "CHE", "#2563EB", "#FFFFFF"),
    "Man Utd": ("منچستریونایتد", "MUN", "#DA291C", "#FBE122"),
    "Spurs": ("تاتنهام", "TOT", "#E2E8F0", "#132257"),
    "Newcastle": ("نیوکاسل", "NEW", "#CBD5E1", "#0F172A"),
    "Aston Villa": ("استون ویلا", "AVL", "#95BFE5", "#670E36"),
    "Brighton": ("برایتون", "BHA", "#0057B8", "#FFCD00"),
    "Nott'm Forest": ("ناتینگهام فارست", "NFO", "#E53233", "#FFFFFF"),
    "West Ham": ("وستهام", "WHU", "#7A263A", "#1BB1E7"),
    "Fulham": ("فولام", "FUL", "#F8FAFC", "#CC0000"),
    "Everton": ("اورتون", "EVE", "#003399", "#FFFFFF"),
    "Brentford": ("برنتفورد", "BRE", "#E30613", "#FFFFFF"),
    "Crystal Palace": ("کریستال پالاس", "CRY", "#1B458F", "#C4122E"),
    "Bournemouth": ("بورنموث", "BOU", "#DA291C", "#000000"),
    "Wolves": ("ولورهمپتون", "WOL", "#FDB913", "#231F20"),
    "Leicester": ("لسترسیتی", "LEI", "#003090", "#FDBE11"),
    "Ipswich": ("ایپسویچ", "IPS", "#3A64A3", "#FFFFFF"),
    "Southampton": ("ساوتهمپتون", "SOU", "#D71920", "#FFFFFF"),
}

_FPL_POS_FA = {1: "دروازه‌بان", 2: "مدافع", 3: "هافبک", 4: "مهاجم"}

_LIVE_CACHE: dict[str, Any] = {"ts": 0.0, "items": []}
_CACHE_TTL_SEC = 600.0


def _clean_fa_text(text: str) -> str:
    s = _CYRILLIC_CJK_RE.sub("", str(text or ""))
    s = s.replace("*", "").replace("`", "")
    return re.sub(r"\s+", " ", s).strip()


def _http_get_bytes(url: str, timeout: float = 8.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _http_get_json(url: str, timeout: float = 8.0) -> Any:
    return json.loads(_http_get_bytes(url, timeout=timeout).decode("utf-8", errors="replace"))


def _download_image_data_uri(url: str, timeout: float = 6.0) -> str | None:
    try:
        raw = _http_get_bytes(url, timeout=timeout)
        if len(raw) < 1200:
            return None
        mime = "image/png" if url.lower().endswith(".png") or raw[:4] == b"\x89PNG" else "image/jpeg"
        return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
    except Exception as _em_exc:
        from src.xgpedia.core.error_metrics import record_error as _rec_err
        _rec_err("provider.injury", _em_exc)
        return None


def fetch_current_player_media_and_number(
    player_name: str, *, fpl_code: int | str | None = None
) -> dict[str, Any]:
    """دریافت عکس رسمی فصل جاری (PL Official PNG ← TheSportsDB Soccer Cutout) و شماره پیراهن واقعی."""
    out: dict[str, Any] = {"photoUrl": None, "number": None}
    # ۱) عکس رسمی فصل جاری لیگ برتر انگلیس (بالاترین کیفیت و جدیدترین کیت)
    if fpl_code:
        code_clean = re.sub(r"\D", "", str(fpl_code))
        if code_clean:
            for tpl in PL_PHOTO_URLS:
                uri = _download_image_data_uri(tpl.format(code=code_clean), timeout=5.0)
                if uri:
                    out["photoUrl"] = uri
                    break
    # ۲) TheSportsDB (منحصراً Soccer) برای شماره پیراهن واقعی و عکس Cutout جدید
    if player_name and len(player_name) >= 3:
        try:
            q = urllib.parse.quote(player_name.strip())
            data = _http_get_json(f"https://www.thesportsdb.com/api/v1/json/3/searchplayers.php?p={q}", timeout=5.5)
            for pl in data.get("player") or []:
                if not isinstance(pl, dict):
                    continue
                if str(pl.get("strSport") or "").strip().lower() != "soccer":
                    continue
                num_raw = str(pl.get("strNumber") or "").strip()
                if num_raw.isdigit() and 1 <= int(num_raw) <= 99:
                    out["number"] = num_raw
                if not out["photoUrl"]:
                    for img_k in ("strCutout", "strRender", "strThumb"):
                        u = str(pl.get(img_k) or "").strip()
                        if u.startswith("http"):
                            uri = _download_image_data_uri(u, timeout=5.5)
                            if uri:
                                out["photoUrl"] = uri
                                break
                break
        except Exception as _em_exc:
            from src.xgpedia.core.error_metrics import record_error as _rec_err
            _rec_err("provider.injury", _em_exc)
    return out


def detect_injury_zone(news_text: str) -> str:
    t = (news_text or "").lower()
    if any(k in t for k in ("acl", "cruciate", "knee", "meniscus", "patella")):
        return "acl"
    if any(k in t for k in ("hamstring", "thigh", "quad")):
        return "hamstring"
    if any(k in t for k in ("ankle", "foot", "toe", "metatarsal")):
        return "ankle"
    if any(k in t for k in ("groin", "hip", "adductor", "pelvis", "abdomen")):
        return "groin"
    if any(k in t for k in ("calf", "achilles", "shin", "soleus")):
        return "calf"
    if any(k in t for k in ("shoulder", "collarbone", "arm", "wrist", "hand", "rib", "back")):
        return "shoulder"
    if any(k in t for k in ("head", "concussion", "face", "jaw", "eye")):
        return "head"
    return "hamstring"


def load_injury_presets() -> list[dict[str, Any]]:
    if not PRESETS_PATH.exists():
        return []
    try:
        data = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as _em_exc:
        from src.xgpedia.core.error_metrics import record_error as _rec_err
        _rec_err("provider.injury", _em_exc)
        return []




_PLAYER_FA_MAP: dict[str, str] = {
    "bukayo saka": "بوکایو ساکا", "martin odegaard": "مارتین اودگارد", "martin ødegaard": "مارتین اودگارد",
    "erling haaland": "ارلینگ هالند", "mohamed salah": "محمد صلاح", "cole palmer": "کول پالمر",
    "phil foden": "فیل فودن", "rodri": "رودری", "rodrigo hernandez": "رودری",
    "kevin de bruyne": "کوین دی‌بروینه", "declan rice": "دکلان رایس", "william saliba": "ویلیام سالیبا",
    "gabriel magalhaes": "گابریل ماگالائس", "gabriel": "گابریل", "alisson becker": "آلیسون بکر",
    "alisson": "آلیسون بکر", "virgil van dijk": "ویرجیل فن دایک", "trent alexander-arnold": "ترنت الکساندر-آرنولد",
    "diogo jota": "دیوگو ژوتا", "luis diaz": "لوئیس دیاز", "darwin nunez": "داروین نونیز",
    "alexis mac allister": "الکسیس مک‌آلیستر", "dominik szoboszlai": "دومینیک سوبوسلای",
    "bruno fernandes": "برونو فرناندز",
    "bruno borges fernandes": "برونو فرناندز",
    "b.fernandes": "برونو فرناندز",
    "b. fernandes": "برونو فرناندز",
    "a.becker": "آلیسون بکر",
    "e.martinez": "امیلیانو مارتینز",
    "l.martinez": "لیساندرو مارتینز",
    "g.jesus": "گابریل ژسوس",
    "g.martinelli": "گابریل مارتینلی",
    "gabriel martinelli": "گابریل مارتینلی",
    "b.silva": "برناردو سیلوا",
    "r.dias": "روبن دیاس",
    "m.salah": "محمد صلاح",
    "c.palmer": "کول پالمر",
    "e.haaland": "ارلینگ هالند",
    "a.isak": "الکساندر ایساک",
    "b.saka": "بوکایو ساکا",
    "p.foden": "فیل فودن",
    "d.rice": "دکلان رایس",
    "m.odegaard": "مارتین اودگارد",
    "d.szoboszlai": "دومینیک سوبوسلای",
    "l.diaz": "لوئیس دیاز",
    "d.nunez": "داروین نونیز",
    "j.pedro": "ژائو پدرو",
    "m.cunha": "ماتئوس کونیا",
    "b.mbeumo": "برایان امبومو",
    "m.rashford": "مارکوس رشفورد",
    "m.kudus": "محمد کودوس",
    "m.rogers": "مورگان راجرز",
    "j.bowen": "جرد بوون",
    "o.watkins": "اولی واتکینز",
    "n.jackson": "نیکلاس جکسون",
    "c.gakpo": "کودی گاکپو",
    "cody gakpo": "کودی گاکپو",
    "r.hojlund": "راسموس هویلوند",
    "a.garnacho": "آلخاندرو گارناچو",
    "e.fernandez": "انزو فرناندز",
    "m.caicedo": "مویسس کایسدو",
    "p.neto": "پدرو نتو",
    "j.gvardiol": "یوشکو گواردیول",
    "j.doku": "جرمی دوکو",
    "a.gordon": "آنتونی گوردون",
    "k.mitoma": "کائورو میتوما",
    "d.solanke": "دومینیک سولانکه",
    "j.maddison": "جیمز مدیسون",
    "k.mainoo": "کوبی ماینو",
    "t.barry": "تیرنو بری",
    "v.gyokeres": "ویکتور گیوکرش",
    "f.wirtz": "فلوریان ویرتز",
    "r.cherki": "رایان شرکی",
    "h.ekitike": "هوگو اکیتیکه",
    "o.marmoush": "عمر مرموش",
    "a.semenyo": "آنتوان سمنیو",
    "s.tonali": "ساندرو تونالی",
    "r.calafiori": "ریکاردو کالافیوری",
    "j.timber": "یورین تیمبر",
    "w.saliba": "ویلیام سالیبا",
    "g.magalhaes": "گابریل ماگالائس",
    "j.pickford": "جردن پیکفورد",
    "n.pope": "نیک پوپ",
    "d.raya": "داوید رایا", "marcus rashford": "مارکوس رشفورد", "kobbie mainoo": "کوبی ماینو",
    "rasmus hojlund": "راسموس هویلوند", "lisandro martinez": "لیساندرو مارتینز", "luke shaw": "لوک شاو",
    "leny yoro": "لنی یورو", "mason mount": "میسون مانت", "alejandro garnacho": "آلخاندرو گارناچو",
    "heung-min son": "سون هیونگ‌مین", "son heung-min": "سون هیونگ‌مین", "james maddison": "جیمز مدیسون",
    "cristian romero": "کریستین رومرو", "micky van de ven": "میکی فن ده فن", "dominic solanke": "دومینیک سولانکه",
    "alexander isak": "الکساندر ایساک", "anthony gordon": "آنتونی گوردون", "bruno guimaraes": "برونو گیمارش",
    "sandro tonali": "ساندرو تونالی", "sven botman": "سون بوتمن", "nick pope": "نیک پوپ",
    "ollie watkins": "اولی واتکینز", "emiliano martinez": "امیلیانو مارتینز", "morgan rogers": "مورگان راجرز",
    "reece james": "ریس جیمز", "nicolas jackson": "نیکلاس جکسون", "enzo fernandez": "انزو فرناندز",
    "moises caicedo": "مویسس کایسدو", "pedro neto": "پدرو نتو", "wesley fofana": "وسلی فوفانا",
    "kai havertz": "کای هاورتز", "gabriel jesus": "گابریل ژسوس", "ben white": "بن وایت",
    "riccardo calafiori": "ریکاردو کالافیوری", "jurrien timber": "یورین تیمبر", "david raya": "داوید رایا",
    "jeremy doku": "جرمی دوکو", "jack grealish": "جک گریلیش", "john stones": "جان استونز",
    "ruben dias": "روبن دیاس", "nathan ake": "ناتان آکه", "josko gvardiol": "یوشکو گواردیول",
    "mateo kovacic": "متئو کواچیچ", "bernardo silva": "برناردو سیلوا", "savinho": "ساوینیو",
    "bryan mbeumo": "برایان امبومو", "yoane wissa": "یوان ویسا", "matheus cunha": "ماتئوس کونیا",
    "jarrod bowen": "جرد بوون", "mohammed kudus": "محمد کودوس", "lucas paqueta": "لوکاس پاکتا",
    "chris wood": "کریس وود", "morgan gibbs-white": "مورگان گیبز-وایت", "eberechi eze": "ابرچی ازه",
    "jean-philippe mateta": "ژان فیلیپ ماتتا", "joao pedro": "ژائو پدرو", "kaoru mitoma": "کائورو میتوما",
    "danny welbeck": "دنی ولبک", "jordan pickford": "جردن پیکفورد", "jarrad branthwaite": "جرد برنتویت",
    "viktor gyokeres": "ویکتور گیوکرش", "florian wirtz": "فلوریان ویرتز", "hugo ekitike": "هوگو اکیتیکه",
    "benjamin sesko": "بنجامین ششکو", "rayan cherki": "رایان شرکی", "tijjani reijnders": "تیجانی ریندرز",
    "omar marmoush": "عمر مرموش", "antoine semenyo": "آنتوان سمنیو", "liam delap": "لیام دلاپ",
    "evanilson": "اوانیلسون", "francisco evanilson": "اوانیلسون", "thierno barry": "تیرنو بری",
    "barry": "تیرنو بری", "cherki": "رایان شرکی", "haaland": "ارلینگ هالند", "isak": "الکساندر ایساک",
    "jackson": "نیکلاس جکسون", "rogers": "مورگان راجرز", "salah": "محمد صلاح", "palmer": "کول پالمر",
    "saka": "بوکایو ساکا", "watkins": "اولی واتکینز", "mbeumo": "برایان امبومو", "wissa": "یوان ویسا",
    "cunha": "ماتئوس کونیا", "wood": "کریس وود", "bowen": "جرد بوون", "solanke": "دومینیک سولانکه",
    "havertz": "کای هاورتز", "foden": "فیل فودن", "mateta": "ژان فیلیپ ماتتا", "welbeck": "دنی ولبک",
    "delap": "لیام دلاپ", "semenyo": "آنتوان سمنیو", "marmoush": "عمر مرموش", "gyokeres": "ویکتور گیوکرش",
    "ekitike": "هوگو اکیتیکه", "sesko": "بنجامین ششکو", "wirtz": "فلوریان ویرتز",
}

_MONTH_FA_MAP = {
    "jan": "ژانویه", "feb": "فوریه", "mar": "مارس", "apr": "آوریل",
    "may": "مه", "jun": "ژوئن", "jul": "ژوئیه", "aug": "اوت",
    "sep": "سپتامبر", "oct": "اکتبر", "nov": "نوامبر", "dec": "دسامبر",
}

_PHONETIC_DIGRAPHS = [
    ("sch", "ش"), ("sh", "ش"), ("ch", "چ"), ("th", "ت"), ("ph", "ف"),
    ("gh", "گ"), ("ck", "ک"), ("qu", "کو"), ("oo", "و"), ("ee", "ی"),
    ("ea", "ی"), ("ou", "و"), ("ai", "ای"), ("ey", "ی"), ("ie", "ی"),
    ("ll", "ل"), ("ss", "س"), ("tt", "ت"), ("rr", "ر"), ("nn", "ن"),
    ("mm", "م"), ("dd", "د"), ("bb", "ب"), ("pp", "پ"), ("ff", "ف"),
    ("gg", "گ"), ("cc", "ک"), ("zz", "ز"),
]
_PHONETIC_CHARS = {
    "a": "ا", "b": "ب", "c": "ک", "d": "د", "e": "ه", "f": "ف", "g": "گ",
    "h": "ه", "i": "ی", "j": "ج", "k": "ک", "l": "ل", "m": "م", "n": "ن",
    "o": "و", "p": "پ", "q": "ک", "r": "ر", "s": "س", "t": "ت", "u": "و",
    "v": "و", "w": "و", "x": "کس", "y": "ی", "z": "ز",
}


_GLOSSARY_PLAYERS_CACHE: dict[str, str] | None = None


def _get_glossary_player_index() -> dict[str, str]:
    global _GLOSSARY_PLAYERS_CACHE
    if _GLOSSARY_PLAYERS_CACHE is not None:
        return _GLOSSARY_PLAYERS_CACHE
    import unicodedata
    idx: dict[str, str] = {}
    try:
        from src.xgpedia.config import load_glossary
        for p in (load_glossary().get("players") or []):
            en = str(p.get("name_en") or "").strip().lower()
            fa_n = str(p.get("name_fa") or "").strip()
            if not en or not fa_n:
                continue
            norm_en = "".join(c for c in unicodedata.normalize("NFKD", en) if not unicodedata.combining(c))
            idx[norm_en] = fa_n
            words = norm_en.split()
            if len(words) >= 2:
                # فرم اول+آخر (مثلاً Bruno Borges Fernandes -> bruno fernandes)
                short_full = f"{words[0]} {words[-1]}"
                idx.setdefault(short_full, fa_n)
                # فرم مخفف حرف اول (مثلاً b.fernandes و b. fernandes)
                init_key = f"{words[0][0]}.{words[-1]}"
                if init_key in idx and idx[init_key] != fa_n:
                    idx[init_key] = ""  # مبهم — تداخل هویت
                else:
                    idx[init_key] = fa_n
    except Exception as _em_exc:
        from src.xgpedia.core.error_metrics import record_error as _rec_err
        _rec_err("provider.injury", _em_exc)
    _GLOSSARY_PLAYERS_CACHE = {k: v for k, v in idx.items() if v}
    return _GLOSSARY_PLAYERS_CACHE


def transliterate_player_name_fa(name: str) -> str:
    """ترجمه یا آوانگاری تمیز نام بازیکن فوتبال از انگلیسی به فارسی از طریق سرویس واحد هویت نام‌ها (v0.77.0)."""
    from src.xgpedia.core.identity_service import resolve_player_name_fa

    res = resolve_player_name_fa(name)
    return res or "بازیکن"


def translate_injury_diagnosis_fa(news: str) -> tuple[str, str]:
    """ترجمه کامل تشخیص مصدومیت و تاریخ بازگشت FPL/ESPN به فارسی روان."""
    raw = str(news or "").strip()
    if not raw:
        return "آسیب‌دیدگی نامشخص", "نامشخص (بررسی پزشکی)"
    if re.search(r"[؀-ۿ]", raw):
        return raw, "نامشخص"

    low = raw.lower()
    # Extract return date
    ret_fa = "نامشخص (بررسی پزشکی)"
    m_ret = re.search(r"(?:expected back|until)\s+(\d{1,2})\s+([a-z]{3,9})", low)
    if m_ret:
        day, mon = m_ret.group(1), m_ret.group(2)[:3]
        ret_fa = f"{day} {_MONTH_FA_MAP.get(mon, mon)}"
    elif "unknown return date" in low:
        ret_fa = "نامشخص (بررسی پزشکی)"
    elif "season" in low:
        ret_fa = "پایان فصل"

    # Translate diagnosis
    patterns = [
        ("acl", "پارگی رباط صلیبی (ACL)"),
        ("cruciate", "آسیب رباط صلیبی زانو"),
        ("hamstring", "مصدومیت عضله همسترینگ"),
        ("knee", "آسیب‌دیدگی زانو"),
        ("ankle", "مصدومیت مچ پا"),
        ("calf", "مصدومیت ساق پا"),
        ("achilles", "آسیب تاندون آشیل"),
        ("thigh", "مصدومیت عضله ران"),
        ("groin", "مصدومیت کشاله ران"),
        ("hip", "آسیب‌دیدگی لگن"),
        ("shoulder", "مصدومیت شانه"),
        ("back", "آسیب‌دیدگی کمر"),
        ("foot", "مصدومیت کف و پنجه پا"),
        ("toe", "مصدومیت انگشت پا"),
        ("head", "آسیب‌دیدگی سر"),
        ("concussion", "ضربه مغزی (پروتکل پزشکی)"),
        ("muscle", "مصدومیت عضلانی"),
        ("knock", "ضرب‌خوردگی و کوفتگی"),
        ("illness", "بیماری و ناخوشی"),
        ("virus", "بیماری ویروسی"),
        ("suspended", "محرومیت انضباطی"),
        ("red card", "محرومیت به‌دلیل کارت قرمز"),
        ("five yellow", "محرومیت ۵ کارته"),
        ("lack of match fitness", "عدم آمادگی کامل بدنی"),
        ("personal reasons", "دلایل شخصی"),
        ("surgery", "دوران نقاهت پس از جراحی"),
        ("fracture", "شکستگی استخوان"),
        ("rib", "آسیب‌دیدگی دنده"),
        ("wrist", "مصدومیت مچ دست"),
        ("hand", "آسیب‌دیدگی دست"),
    ]
    diag_fa = "آسیب‌دیدگی پزشکی"
    for kw, fa in patterns:
        if kw in low:
            diag_fa = fa
            break

    # Extract percentage chance if present in news
    m_pct = re.search(r"(\d{2})%\s+chance", low)
    if m_pct:
        diag_fa = f"{diag_fa} ({m_pct.group(1)}٪ شانس بازی)"
    elif ret_fa not in ("نامشخص (بررسی پزشکی)", "نامشخص"):
        diag_fa = f"{diag_fa} • بازگشت احتمالی {ret_fa}"
    return diag_fa, ret_fa


def parse_fpl_injuries(
    bootstrap: dict[str, Any],
    fixtures: list[dict[str, Any]] | None = None,
    *,
    limit: int = 18,
) -> list[dict[str, Any]]:
    """استخراج لیست مصدومان واقعی لیگ برتر از FPL Official (بدون شماره پیراهن جعلی)."""
    if not isinstance(bootstrap, dict):
        return []
    teams_by_id: dict[int, dict[str, Any]] = {
        int(t["id"]): t for t in (bootstrap.get("teams") or []) if isinstance(t, dict) and t.get("id") is not None
    }
    elements = [e for e in (bootstrap.get("elements") or []) if isinstance(e, dict)]

    team_next_fix: dict[int, list[dict[str, Any]]] = {}
    for fx in fixtures or []:
        if not isinstance(fx, dict) or fx.get("finished"):
            continue
        ht, at = fx.get("team_h"), fx.get("team_a")
        ko = str(fx.get("kickoff_time") or "")[:10]
        if ht in teams_by_id and at in teams_by_id:
            h_obj, a_obj = teams_by_id[int(ht)], teams_by_id[int(at)]
            h_meta = _FPL_CLUBS.get(str(h_obj.get("name")), (str(h_obj.get("name")), str(h_obj.get("short_name", "FC")), "#38BDF8", "#FFFFFF"))
            a_meta = _FPL_CLUBS.get(str(a_obj.get("name")), (str(a_obj.get("name")), str(a_obj.get("short_name", "FC")), "#38BDF8", "#FFFFFF"))
            team_next_fix.setdefault(int(ht), []).append({"opp": a_meta[0], "code": a_meta[1], "comp": "لیگ برتر", "loc": "میزبان", "date": ko or "هفته پیش‌رو", "diff": int(fx.get("team_h_difficulty") or 3)})
            team_next_fix.setdefault(int(at), []).append({"opp": h_meta[0], "code": h_meta[1], "comp": "لیگ برتر", "loc": "میهمان", "date": ko or "هفته پیش‌رو", "diff": int(fx.get("team_a_difficulty") or 3)})

    fit_by_team_pos: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for el in elements:
        if el.get("status") == "a" and int(el.get("minutes") or 0) >= 90:
            fit_by_team_pos.setdefault((int(el.get("team") or 0), int(el.get("element_type") or 3)), []).append(el)
    for key in fit_by_team_pos:
        fit_by_team_pos[key].sort(key=lambda x: float(x.get("expected_goal_involvements") or 0) + float(x.get("minutes") or 0) / 900.0, reverse=True)

    injured = []
    for el in elements:
        st = str(el.get("status") or "a").lower()
        news = str(el.get("news") or "").strip()
        if st not in ("i", "d") or not news or _NON_SOCCER_RE.search(news):
            continue
        injured.append((float(el.get("selected_by_percent") or 0.0), el))

    injured.sort(key=lambda x: x[0], reverse=True)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    results: list[dict[str, Any]] = []

    for _, el in injured[:limit]:
        tid = int(el.get("team") or 0)
        pos_id = int(el.get("element_type") or 3)
        tobj = teams_by_id.get(tid) or {}
        t_raw = str(tobj.get("name") or "Club")
        c_fa, c_code, c_col, c_sec = _FPL_CLUBS.get(t_raw, (t_raw, str(tobj.get("short_name") or "FC")[:3].upper(), "#E62E45", "#FFFFFF"))
        news = str(el.get("news") or "").strip()
        chance = el.get("chance_of_playing_next_round")
        prob = int(chance) if chance is not None else (0 if el.get("status") == "i" else 50)
        zone = detect_injury_zone(news)

        is_long = zone == "acl" or "season" in news.lower() or "surgery" in news.lower() or "months" in news.lower()
        if prob >= 75:
            sev, stage, bulletin = "fit", 4, "در آستانه بازگشت • FPL"
        elif prob >= 25 or el.get("status") == "d":
            sev, stage, bulletin = "doubt", 3, "مشکوک به بازی • تست نهایی"
        elif is_long:
            sev, stage, bulletin = "long", 1, "هشدار بحرانی • مصدومیت سنگین"
        else:
            sev, stage, bulletin = "out", 2, "بولتن پزشکی • غیبت قطعی"

        diag_fa, ret_date = translate_injury_diagnosis_fa(news)
        eta_lbl = "بلندمدت" if is_long else ("نامشخص" if "نامشخص" in ret_date else f"تا {ret_date}")

        full_en = f"{el.get('first_name', '')} {el.get('second_name', '')}".strip() or str(el.get("web_name") or "")
        full_fa = transliterate_player_name_fa(full_en)
        # هرگز id % 99 به‌عنوان شماره پیراهن استفاده نشود (null ≠ 0)
        sq_num = el.get("squad_number")
        real_num = str(sq_num) if (sq_num is not None and str(sq_num).isdigit() and 1 <= int(sq_num) <= 99) else None
        fpl_code = el.get("code") or (str(el.get("photo") or "").split(".")[0] or None)

        next_fx = []
        for fx in (team_next_fix.get(tid) or [])[:4]:
            fx_copy = dict(fx)
            fx_copy["status"] = "غایب قطعی" if prob <= 25 else (f"مشکوک {prob}٪" if prob < 75 else "احتمال بازگشت")
            next_fx.append(fx_copy)

        reps = []
        rep_colors = ("#38BDF8", "#A78BFA")
        for r_idx, rep_el in enumerate((fit_by_team_pos.get((tid, pos_id)) or [])[:2]):
            mins = max(1, int(rep_el.get("minutes") or 1))
            xgi90 = float(rep_el.get("expected_goal_involvements") or 0.0) * 90.0 / mins
            fit_score = min(92, max(68, int(72 + xgi90 * 24)))
            reps.append({
                "name": transliterate_player_name_fa(str(rep_el.get("web_name") or rep_el.get("second_name") or "")),
                "role": f"{_FPL_POS_FA.get(pos_id, 'بازیکن')} آماده {c_fa}",
                "fit": fit_score,
                "stat": f"{xgi90:.2f} xG+xA/90" if xgi90 > 0 else f"{mins} دقیقه بازی",
                "note": f"{int(rep_el.get('goals_scored') or 0)} گل و {int(rep_el.get('assists') or 0)} پاس گل در فصل جاری",
                "color": rep_colors[r_idx % len(rep_colors)],
            })

        results.append({
            "id": f"fpl_inj_{el.get('id')}",
            "fpl_code": fpl_code,
            "is_live": True,
            "competition": "گزارش پزشکی لیگ برتر انگلیس",
            "leagueEn": "PREMIER LEAGUE",
            "season": "26/27",
            "bulletin": bulletin,
            "date": now_str,
            "updated": "آپدیت زنده FPL",
            "source": "Premier League / FPL Official",
            "source_url": "https://fantasy.premierleague.com/",
            "codeId": f"MED-{c_code}-{real_num or 'PL'}",
            "player": {
                "name": full_fa,
                "en": full_en.upper(),
                "pos": _FPL_POS_FA.get(pos_id, "بازیکن"),
                "number": real_num,
                "club": c_fa,
                "clubCode": c_code,
                "color": c_col,
                "secondary": c_sec,
                "photoUrl": None,
            },
            "injury": {
                "severity": sev,
                "zone": zone,
                "diagnosis": diag_fa,
                "grade": "OFFICIAL" if sev in ("out", "long") else "FITNESS TEST",
                "mechanism": diag_fa,
                "eta": eta_lbl,
                "returnDate": ret_date,
                "stage": stage,
                "nextProb": prob,
                "reinjuryRisk": None,
                "reinjuryLabel": None,
            },
            "fixtures": next_fx,
            "impact": None,
            "replacements": reps or None,
            "history": None,
            "verdict": None,
        })
    return results


def fetch_injury_rss_alerts(limit: int = 8) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for src_name, url in INJURY_RSS_FEEDS:
        if len(alerts) >= limit:
            break
        try:
            raw = _http_get_bytes(url, timeout=7.0)
            root = ET.fromstring(raw)
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                desc = re.sub(r"<[^>]+>", " ", (item.findtext("description") or "")).strip()
                link = (item.findtext("link") or "").strip()
                blob = f"{title} {desc}"
                if not title or title.lower() in seen or _NON_SOCCER_RE.search(blob) or not _INJURY_KW_RE.search(blob):
                    continue
                seen.add(title.lower())
                zone = detect_injury_zone(blob)
                alerts.append({
                    "id": f"rss_inj_{abs(hash(title)) % 1000000}",
                    "is_live": True,
                    "competition": "گزارش پزشکی فوتبال اروپا",
                    "leagueEn": "FOOTBALL MEDICAL WIRE",
                    "season": "26/27",
                    "bulletin": f"خبر فوری پزشکی • {src_name}",
                    "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "updated": "رصد زنده RSS",
                    "source": src_name,
                    "source_url": link,
                    "codeId": "MED-WIRE",
                    "player": {"name": title[:48], "en": title[:40].upper(), "pos": "فوتبال اروپا", "number": None, "club": src_name, "clubCode": "XGP", "color": "#E62E45", "secondary": "#FFFFFF", "photoUrl": None},
                    "injury": {"severity": "long" if zone == "acl" else "out", "zone": zone, "diagnosis": title[:95], "grade": "WIRE ALERT", "mechanism": (desc or title)[:180], "eta": "بررسی پزشکی", "returnDate": "نامشخص", "stage": 1, "nextProb": 10, "reinjuryRisk": None, "reinjuryLabel": None},
                    "fixtures": None, "impact": None, "replacements": None, "history": None, "verdict": None,
                })
                if len(alerts) >= limit:
                    break
        except Exception as _em_exc:
            from src.xgpedia.core.error_metrics import record_error as _rec_err
            _rec_err("provider.injury", _em_exc)
            continue
    return alerts


def fetch_live_injuries(force_refresh: bool = False) -> list[dict[str, Any]]:
    now = time.time()
    if not force_refresh and _LIVE_CACHE["items"] and (now - _LIVE_CACHE["ts"]) < _CACHE_TTL_SEC:
        return list(_LIVE_CACHE["items"])
    items: list[dict[str, Any]] = []
    try:
        bs = _http_get_json(FPL_BOOTSTRAP_URL, timeout=8.0)
        try:
            fxs = _http_get_json(FPL_FIXTURES_URL, timeout=8.0)
        except Exception:
            fxs = []
        items.extend(parse_fpl_injuries(bs, fxs, limit=16))
    except Exception as _em_exc:
        from src.xgpedia.core.error_metrics import record_error as _rec_err
        _rec_err("provider.injury", _em_exc)
    try:
        items.extend(fetch_injury_rss_alerts(limit=6))
    except Exception as _em_exc:
        from src.xgpedia.core.error_metrics import record_error as _rec_err
        _rec_err("provider.injury", _em_exc)
    _LIVE_CACHE["ts"] = now
    _LIVE_CACHE["items"] = items
    return list(items)


def list_injury_items(
    *, include_live: bool = True, force_refresh: bool = False
) -> dict[str, list[dict[str, Any]]]:
    presets = load_injury_presets()
    live = fetch_live_injuries(force_refresh=force_refresh) if include_live else []
    return {"live": live, "presets": presets}


def enrich_injury_item(
    item: dict[str, Any],
    *,
    cancel_event: threading.Event | None = None,
    fetch_network: bool = True,
) -> dict[str, Any]:
    """دریافت عکس رسمی فصل جاری + شماره پیراهن واقعی از PL/TheSportsDB و ترجمه فارسی با LLM."""
    out = json.loads(json.dumps(item))
    pl = out.get("player") or {}
    inj = out.get("injury") or {}

    if fetch_network and not out.get("is_preset"):
        media = fetch_current_player_media_and_number(
            str(pl.get("name") or ""), fpl_code=out.get("fpl_code")
        )
        if media.get("photoUrl") and not pl.get("photoUrl"):
            pl["photoUrl"] = media["photoUrl"]
        if media.get("number") and not pl.get("number"):
            pl["number"] = media["number"]
            if pl.get("clubCode"):
                out["codeId"] = f"MED-{pl['clubCode']}-{media['number']}"

    if out.get("verdict") and (out["verdict"] or {}).get("body") and out.get("is_preset"):
        return out

    if fetch_network and (not out.get("verdict") or not (out["verdict"] or {}).get("body")):
        try:
            from src.xgpedia.editorial.llm_provider import generate_text

            prompt = (
                "به‌عنوان تحریریه پزشکی-فنی فوتبال XGPedia، گزارش زیر را به فارسی ژورنالیستی دقیق تبدیل کن.\n"
                f"بازیکن: {pl.get('name')} ({pl.get('club')})\n"
                f"گزارش انگلیسی/اولیه: {inj.get('diagnosis')}\n"
                f"احتمال حضور بازی بعد: {inj.get('nextProb')}%\n"
                'فقط JSON خالص با کلیدهای {"name_fa": "نام فارسی بازیکن", "diagnosis_fa": "تشخیص کوتاه فارسی", '
                '"mechanism_fa": "شرح کوتاه مکانیسم یا وضعیت مصدومیت", "verdict_title": "تیتر تحریریه", '
                '"verdict_body": "تحلیل دو جمله‌ای فارسی بدون ستاره و بدون حروف غیرفارسی", "verdict_tag": "برچسب پایانی"}'
            )
            raw = generate_text(prompt, max_tokens=320, cancel_event=cancel_event)
            if raw:
                m = re.search(r"\{[\s\S]*\}", raw)
                if m:
                    parsed = json.loads(m.group(0))
                    if parsed.get("name_fa") and not out.get("is_preset"):
                        pl["name"] = _clean_fa_text(parsed["name_fa"])[:42]
                    if parsed.get("diagnosis_fa"):
                        inj["diagnosis"] = _clean_fa_text(parsed["diagnosis_fa"])[:110]
                    if parsed.get("mechanism_fa"):
                        inj["mechanism"] = _clean_fa_text(parsed["mechanism_fa"])[:180]
                    if parsed.get("verdict_title") and parsed.get("verdict_body"):
                        out["verdict"] = {
                            "title": _clean_fa_text(parsed["verdict_title"])[:90],
                            "body": _clean_fa_text(parsed["verdict_body"])[:260],
                            "tag": _clean_fa_text(parsed.get("verdict_tag") or "پایش پزشکی XGPedia")[:90],
                        }
                        return out
        except Exception as _em_exc:
            from src.xgpedia.core.error_metrics import record_error as _rec_err
            _rec_err("provider.injury", _em_exc)

    if not out.get("verdict"):
        out["verdict"] = {
            "title": f"وضعیت پزشکی {pl.get('name', '')} در {pl.get('club', '')}",
            "body": f"بر اساس آخرین گزارش رسمی، وضعیت {pl.get('name', '')} به‌صورت «{inj.get('diagnosis', 'در حال ارزیابی')}» ثبت شده و شانس حضور او در بازی پیش‌رو {inj.get('nextProb', 0)} درصد برآورد می‌شود.",
            "tag": f"گزارش رسمی {out.get('source', 'XGPedia Medical Desk')}",
        }
    return out
