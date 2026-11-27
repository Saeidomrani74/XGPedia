"""پیکربندی مرکزی پروژه — همهٔ مسیرها و قواعد ثابت از اینجا خوانده می‌شوند.

اصل معماری: هیچ فایل کدی رنگ، آستانه یا مسیر را هاردکد نمی‌کند؛
همه‌چیز از config/ و brand/ می‌آید تا تعویض تصمیم فقط یک فایل JSON باشد.

نسخهٔ ۸: منبع اصلی داده football-data.co.uk (xG) + football-data.org (بازی/جدول) است.
API-Football فقط fallback پولی می‌ماند (تصمیم D4 بازنگری‌شده).
"""
from __future__ import annotations

import json
import re
import os
from datetime import date
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]

# بارگذاری .env از ریشهٔ پکیج — قبل از هر خواندن os.environ (توکن‌ها و مسیر DB).
# مسیر anchor است تا اجرای run.py از هر پوشه‌ای، همیشه همان .env ریشه را پیدا کند.
# متغیرهایی که از قبل در env هستند override نمی‌شوند (رفتار پیش‌فرض dotenv).
load_dotenv(ROOT / ".env")

CONFIG_DIR = ROOT / "config"
BRAND_FILE = ROOT / "brand" / "brand.json"
THRESHOLDS_FILE = CONFIG_DIR / "thresholds.json"
GLOSSARY_FILE = CONFIG_DIR / "glossary_fa.json"
TEAM_MAPPING_FILE = CONFIG_DIR / "team_mapping.json"
TEAM_IDENTITIES_FILE = CONFIG_DIR / "team_identities.json"
TEAM_VENUES_FILE = CONFIG_DIR / "team_venues.json"
CRESTS_DIR = ROOT / "brand" / "crests"  # brand/crests/{CODE}.svg|png — لوگوی واقعی تیم‌ها (tools/fetch_crests.py)
STUDIO_TEMPLATES_DIR = Path(os.environ.get("XGPEDIA_STUDIO_TEMPLATES_DIR", ROOT / "studio_templates"))
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", ROOT / "data" / "dev.sqlite"))
RAW_PAYLOAD_DIR = Path(os.environ.get("RAW_PAYLOAD_DIR", ROOT / "data" / "raw"))

# لایهٔ انتشار تلگرام (مرحلهٔ ۲ NEXT_STEPS) — خالی = غیرفعال؛ پیام خطای واضح در run.py publish
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")
TELEGRAM_GROUP_ID = os.environ.get("TELEGRAM_GROUP_ID", "")
ADMIN_TELEGRAM_IDS = frozenset(
    int(x) for x in os.environ.get("ADMIN_TELEGRAM_IDS", "").split(",") if x.strip()
)

DISPLAY_TZ = "Asia/Tehran"  # ذخیره همیشه UTC؛ نمایش «به وقت تهران (UTC+3:30)»

# فصل جاری — «سال شروع» فصل (قرارداد هر دو provider: CSV با mmz4281/<YY><YY+1>/
# و API v4 با ?season=<سال شروع>). فصل انگلیس از ۱ اوت شروع می‌شود، پس پیش از آن
# هنوز فصل قبلِ در جریان است. محاسبهٔ خودکار تا وقتی دادهٔ جدید فصل تازه منتشر
# نشده ممکن است به فصلِ بدون داده اشاره کند — برای این حالت XGPEDIA_SEASON_START
# در .env قابل override است (مثلاً =2026 در هفته‌های اول اوت).
_OVERR = os.environ.get("XGPEDIA_SEASON_START")
if _OVERR:
    CURRENT_SEASON_START = int(_OVERR)
else:
    _today = date.today()
    CURRENT_SEASON_START = _today.year if _today.month >= 8 else _today.year - 1

# providerهای فعال به ترتیب اولویت — منبع xG همیشه یکی است (قاعدهٔ D5)
PRIMARY_STATS_PROVIDER = "football-data-co-uk"   # xG + شوت + کرنر مسابقه
PRIMARY_FIXTURES_PROVIDER = "football-data-org"  # بازی‌های پیش‌رو + جدول


@lru_cache(maxsize=1)
def load_brand() -> dict:
    with open(BRAND_FILE, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_thresholds() -> dict:
    with open(THRESHOLDS_FILE, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_glossary() -> dict:
    with open(GLOSSARY_FILE, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_team_mapping() -> dict:
    """نگاشت نام تیم‌ها بین سه منبع + فارسی — config/team_mapping.json."""
    with open(TEAM_MAPPING_FILE, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_team_identities() -> dict:
    """هویت بصری تیم‌ها (کد + رنگ اصلی/ثانویه) — config/team_identities.json.

    کلید همان canonical (نام کامل استاندارد) در team_mapping.json است؛ اگر تیمی
    اینجا نبود، رندرر fallback بی‌طرف خودش را به‌کار می‌برد — هرگز exception نمی‌دهد.
    """
    with open(TEAM_IDENTITIES_FILE, encoding="utf-8") as f:
        return json.load(f)


def _ascii_fold(text: str) -> str:
    import unicodedata
    tr = str.maketrans({"ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D", "ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE"})
    s = unicodedata.normalize("NFKD", str(text or "").translate(tr))
    return "".join(ch for ch in s if not unicodedata.combining(ch)).strip().lower()


def canonical_team_name(raw_name: str, fdo_id: int | None = None) -> str:
    """تبدیل نام خام هر provider (FDO/ESPN/SofaScore/CSV) به نام canonical یکتا در team_mapping.json."""
    if not raw_name:
        return raw_name
    cleaned = raw_name.strip()
    m = load_team_mapping()
    all_teams = {}
    all_teams.update(m.get("relegated_2025_26", {}))
    all_teams.update(m.get("teams", {}))

    low = cleaned.lower()
    fold = _ascii_fold(cleaned)

    # ۱) تطبیق دقیق با نام canonical، csv_short و aliases (با و بدون اعراب لاتین)
    for canonical, info in all_teams.items():
        if canonical.lower() == low or _ascii_fold(canonical) == fold:
            return canonical
        cs = str(info.get("csv_short", "") or "")
        if cs and (cs.lower() == low or _ascii_fold(cs) == fold):
            return canonical
        for al in info.get("aliases") or []:
            al_s = str(al or "")
            if al_s and (al_s.lower() == low or _ascii_fold(al_s) == fold):
                return canonical

    # ۲) حذف پیشوند/پسوندهای رایج باشگاهی (FC, FK, CF, SK, SC, AC, ...)
    norm = fold
    for prefix in ("afc ", "fc ", "fk ", "sk ", "sc ", "ac ", "as ", "rc ", "rcd ", "cd ", "ud ", "ca ", "sv ", "vfb ", "vfl ", "ssc ", "us ", "ogc ", "club "):
        if norm.startswith(prefix):
            norm = norm[len(prefix):].strip()
    for suffix in (" & hove albion fc", " & hove albion", " hotspur fc", " hotspur", " afc", " fc", " fk", " cf", " sk", " sc", " kv", " 1909", " 1893", " 1846"):
        if norm.endswith(suffix):
            norm = norm[:-len(suffix)].strip()

    for canonical, info in all_teams.items():
        if _ascii_fold(canonical) == norm or _ascii_fold(str(info.get("csv_short", "") or "")) == norm:
            return canonical
        for al in info.get("aliases") or []:
            if _ascii_fold(str(al or "")) == norm:
                return canonical

    for suffix in (" united", " city", " town", " albion", " wanderers"):
        if norm.endswith(suffix):
            cand = norm[:-len(suffix)].strip()
            for canonical in all_teams:
                if _ascii_fold(canonical) == cand:
                    return canonical

    if fdo_id is not None:
        matches = [c for c, info in all_teams.items() if info.get("fdo_id") == fdo_id]
        if len(matches) == 1:
            return matches[0]

    return cleaned


def team_identity(name_en: str) -> dict | None:
    """هویت یک تیم ({code, colors, crest})؛ با پشتیبانی از نام خام provider و معادل‌های Hull/Hull City."""
    teams = load_team_identities().get("teams", {})
    if name_en in teams:
        return teams[name_en]
    canon = canonical_team_name(name_en)
    if canon in teams:
        return teams[canon]
    canon_low = canon.lower()
    for k, v in teams.items():
        if k.lower().startswith(canon_low + " ") or canon_low.startswith(k.lower() + " "):
            return v
    return None


def team_crest_path(name_en: str) -> Path | None:
    """مسیر لوگوی واقعی تیم اگر دانلود شده باشد (svg اول، بعد png)؛ وگرنه None."""
    ident = team_identity(name_en)
    if ident is None:
        return None
    for ext in (".svg", ".png"):
        p = CRESTS_DIR / f"{ident['code']}{ext}"
        if p.exists():
            return p
    return None


def canonical_from_csv(csv_name: str) -> str:
    """نام کوتاه CSV → نام canonical؛ اگر نگاشت نبود، همان ورودی (قابل شناسایی در لاگ)."""
    m = load_team_mapping()
    for canonical, t in m.get("teams", {}).items():
        if t.get("csv_short") == csv_name:
            return canonical
    for canonical, t in m.get("relegated_2025_26", {}).items():
        if t.get("csv_short") == csv_name:
            return canonical
    return csv_name


def team_name_fa(name_en: str) -> str:
    """نام فارسی یکدست تیم از نگاشت/واژه‌نامه (حتی برای نام خام مثل Liverpool FC).

    قاعدهٔ تحریریه: نام تیم/بازیکن خارج از واژه‌نامه از سوی validator رد می‌شود.
    """
    m = load_team_mapping()
    canon = canonical_team_name(name_en)
    for group in ("teams", "relegated_2025_26"):
        for canonical, t in m.get(group, {}).items():
            if canon == canonical or name_en in (canonical, t.get("csv_short", ""), *t.get("aliases", [])):
                return t["name_fa"]
    g = load_glossary()
    low_en = (name_en or "").strip().lower()
    low_cn = (canon or "").strip().lower()
    for team in g.get("teams", []):
        cands = [team["name_en"], team["id"], *team.get("aliases", [])]
        if name_en in cands or canon in cands or low_en in (c.lower() for c in cands) or low_cn in (c.lower() for c in cands):
            return team["name_fa"]
    # پشتیبان هوشمند آوانویسی فارسی برای باشگاه‌های جدید اروپایی تا نام انگلیسی روی کارت نیاید
    cleaned = re.sub(r"\b(?:F\.?C\.?|F\.?K\.?|C\.?F\.?|S\.?C\.?|A\.?C\.?|S\.?K\.?|B\.?K\.?|N\.?K\.?|P\.?F\.?K\.?)\b", "", name_en or "", flags=re.IGNORECASE).strip()
    if cleaned and any("a" <= ch.lower() <= "z" for ch in cleaned):
        try:
            fa_auto = translate_player_fa(cleaned)
            if fa_auto and fa_auto != cleaned:
                return fa_auto
        except Exception:
            pass
    return name_en


@lru_cache(maxsize=1)
def load_team_venues() -> dict:
    """ورزشگاه خانگی و سرمربی تیم‌ها از config/team_venues.json."""
    if not TEAM_VENUES_FILE.exists():
        return {"teams": {}}
    with open(TEAM_VENUES_FILE, encoding="utf-8") as f:
        return json.load(f)


def team_venue(name_en: str) -> dict:
    """برگرداندن {stadium_fa, coach_fa} برای یک تیم (با نگاشت خودکار نام خام)."""
    teams = load_team_venues().get("teams", {})
    canon = canonical_team_name(name_en)
    return teams.get(canon) or teams.get(name_en) or {}

def _transliterate_latin_to_fa(name: str) -> str:
    """آوانویسی سبک نام‌های لاتین به فارسی (پشتیبان اضطراری تا هرگز نام سرمربی انگلیسی روی کارت نماند)."""
    import unicodedata

    # اگر از قبل فارسی است، دست نزن
    if any("\u0600" <= ch <= "\u06FF" for ch in name):
        return name
    norm = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
    digraphs = [
        ("tsch", "چ"), ("sch", "ش"), ("sh", "ش"), ("ch", "چ"), ("th", "ت"),
        ("ph", "ف"), ("gh", "گ"), ("kh", "خ"), ("zh", "ژ"), ("ck", "ک"),
        ("qu", "کو"), ("ee", "ی"), ("oo", "و"), ("ou", "و"), ("au", "او"),
        ("ai", "ای"), ("ei", "ای"), ("ie", "ی"), ("ea", "ی"), ("ia", "یا"),
    ]
    chars = {
        "a": "ا", "b": "ب", "c": "ک", "d": "د", "e": "ه", "f": "ف", "g": "گ",
        "h": "ه", "i": "ی", "j": "ج", "k": "ک", "l": "ل", "m": "م", "n": "ن",
        "o": "و", "p": "پ", "q": "ک", "r": "ر", "s": "س", "t": "ت", "u": "و",
        "v": "و", "w": "و", "x": "کس", "y": "ی", "z": "ز",
    }
    words_out: list[str] = []
    for word in norm.split():
        w = word.lower().strip(".,'-")
        if not w:
            continue
        out: list[str] = []
        i = 0
        while i < len(w):
            matched = False
            for dg, fa_v in digraphs:
                if w.startswith(dg, i):
                    out.append(fa_v)
                    i += len(dg)
                    matched = True
                    break
            if matched:
                continue
            ch = w[i]
            if i == 0 and ch == "a":
                out.append("آ")
            elif i == 0 and ch in ("e", "i", "o", "u"):
                out.append("ا" if ch == "e" else ("ای" if ch == "i" else "او"))
            elif ch == "e" and i < len(w) - 1:
                pass  # مصوت کوتاه میانی حذف می‌شود تا شکل فارسی طبیعی‌تر باشد
            else:
                out.append(chars.get(ch, ""))
            i += 1
        words_out.append("".join(out) or word)
    return " ".join(words_out)


def translate_coach_fa(coach_en: str | None, *, allow_transliterate: bool = True) -> str | None:
    """ترجمهٔ فارسی نام سرمربیِ دریافت‌شدهٔ زنده از API (دیکشنری دقیق → ویکی‌پدیا/آوانویسی خودکار + تبدیل `&` به `و`)."""
    name = str(coach_en or "").strip()
    if not name:
        return None
    if "&" in name or re.search(r"\s+and\s+", name, flags=re.IGNORECASE):
        parts = [p.strip() for p in re.split(r"\s*(?:&|\band\b)\s*", name, flags=re.IGNORECASE) if p.strip()]
        if len(parts) >= 2:
            tr_parts = [translate_coach_fa(p, allow_transliterate=allow_transliterate) or p for p in parts]
            return " و ".join(tr_parts)
    if any("\u0600" <= ch <= "\u06FF" for ch in name):
        return re.sub(r"\s*&\s*", " و ", name)
    mapping = load_team_venues().get("coach_translations_fa", {})
    if name in mapping:
        return mapping[name]
    low = name.lower()
    for k, v in mapping.items():
        if k.lower() == low:
            return v
    return _transliterate_latin_to_fa(name) if allow_transliterate else name


_PLAYER_NAMES_FA: dict[str, str] = {
    "salah": "صلاح", "mohamed salah": "محمد صلاح",
    "wirtz": "ویرتز", "florian wirtz": "فلوریان ویرتز",
    "szoboszlai": "سوبوسلای", "dominik szoboszlai": "سوبوسلای",
    "ngumoha": "انگوموها", "rio ngumoha": "انگوموها",
    "diaz": "دیاز", "luis diaz": "لوئیس دیاز", "luis díaz": "لوئیس دیاز",
    "gakpo": "گاکپو", "cody gakpo": "کودی گاکپو",
    "nunez": "نونیز", "darwin nunez": "نونیز",
    "jota": "ژوتا", "diogo jota": "دیوگو ژوتا",
    "mac allister": "مک‌آلیستر", "van dijk": "فن دایک",
    "haaland": "هالند", "erling haaland": "ارلینگ هالند",
    "foden": "فودن", "phil foden": "فیل فودن",
    "saka": "ساکا", "bukayo saka": "بوکایو ساکا",
    "odegaard": "اودگارد", "martin odegaard": "اودگارد",
    "havertz": "هاورتز", "palmer": "پالمر", "cole palmer": "کول پالمر",
    "fernandes": "فرناندز", "bruno fernandes": "برونو فرناندز", "b.fernandes": "برونو فرناندز",
    "bruno borges fernandes": "برونو فرناندز",
    "rashford": "رشفورد", "hojlund": "هویلوند", "garnacho": "گارناچو",
    "isak": "ایساک", "alexander isak": "ایساک", "gordon": "گوردون",
    "son": "سون", "heung-min son": "سون", "maddison": "مدیسون", "solanke": "سولانکه",
    "watkins": "واتکینز", "rogers": "راجرز", "bowen": "بوون", "cunha": "کونیا",
    "mbeumo": "امبومو", "wissa": "ویسا", "wood": "وود", "mitoma": "میتوما",
    "munoz": "مونیوز", "víctor muñoz": "ویکتور مونیوز", "victor munoz": "ویکتور مونیوز",
    "muñoz": "مونیوز", "ekitike": "اکیتیکه", "frimpong": "فریمپونگ", "kerkez": "کرکز",
    "alisson": "آلیسون", "a.becker": "آلیسون", "lammens": "لامنس", "onana": "اونانا",
    "raya": "رایا", "vicario": "ویکاریو", "pope": "پوپ", "pickford": "پیکفورد",
    # ستاره‌ها و دروازه‌بان‌های ۶ لیگ معتبر اروپا و چمپیونزلیگ
    "oblak": "اوبلاک", "jan oblak": "یان اوبلاک",
    "sorloth": "سورلوت", "alexander sorloth": "الکساندر سورلوت",
    "alvarez": "آلوارز", "julian alvarez": "خولیان آلوارز",
    "griezmann": "گریزمان", "antoine griezmann": "آنتوان گریزمان",
    "mbappe": "امباپه", "kylian mbappe": "کیلیان امباپه",
    "vinicius": "وینیسیوس", "vinicius junior": "وینیسیوس جونیور",
    "bellingham": "بلینگام", "jude bellingham": "جود بلینگام",
    "rodrygo": "رودریگو", "valverde": "والورده", "courtois": "کورتوا",
    "yamal": "یامال", "lamine yamal": "لامین یامال",
    "raphinha": "رافینیا", "lewandowski": "لواندوفسکی", "pedri": "پدری", "olmo": "اولمو",
    "garcia": "گارسیا", "joan garcia": "خوان گارسیا", "ter stegen": "تراشتگن", "szczesny": "شزنی",
    "kane": "کین", "harry kane": "هری کین", "musiala": "موسیالا", "olise": "اولیسه",
    "neuer": "نویر", "kimmich": "کیمیش", "sane": "سانه",
    "lautaro": "لائوتارو", "martinez": "مارتینز", "thuram": "تورام", "barella": "بارلا",
    "calhanoglu": "چالهان‌اوغلو", "sommer": "زومر", "bastoni": "باستونی",
    "leao": "لیائو", "pulisic": "پولیسیچ", "maignan": "منیان",
    "vlahovic": "ولاهوویچ", "yildiz": "ییلدیز", "lukaku": "لوکاکو", "mctominay": "مک‌تامینی",
    "dembele": "دمبله", "barcola": "بارکولا", "kvaratskhelia": "کواراتسخلیا",
    "vitinha": "ویتینیا", "hakimi": "حکیمی", "donnarumma": "دوناروما", "chevalier": "شوالیه",
    "gyokeres": "گیوکرش", "suarez": "سوارز", "luis suarez": "لوئیس سوارز",
    "osimhen": "اوسیمن", "icardi": "ایکاردی", "guirassy": "گیراسی", "adeyemi": "آدیمی",
    "jesus": "ژسوس", "gabriel jesus": "گابریل ژسوس",
    "pokatilov": "پوکاتیلوف", "belko": "بلکو", "kobel": "کوبل", "di gregorio": "دی گرگوریو",
    "trubin": "تروبین", "costa": "کاستا", "diogo costa": "دیوگو کاستا",
    "mignolet": "مینیوله", "riznyk": "ریزنیک", "livakovic": "لیواکوویچ",
    "luiz junior": "لوییز جونیور", "luiz jr": "لوییز جونیور",
    "vini jr": "وینیسیوس جونیور", "vinicius jr": "وینیسیوس جونیور",
    "ayoze perez": "آیوزه پرز", "pape gueye": "پاپه گویه",
    "tajon buchanan": "بوچانان", "buchanan": "بوچانان",
    # ستاره‌ها و دروازه‌بان‌های لیگ اروپا (UEFA Europa League)
    "vangelis pavlidis": "پاولیدیس", "pavlidis": "پاولیدیس",
    "angel di maria": "دی‌ماریا", "di maria": "دی‌ماریا",
    "mikel oyarzabal": "اویارزابال", "oyarzabal": "اویارزابال",
    "takefusa kubo": "کوبو", "kubo": "کوبو",
    "alex remiro": "رمیرو", "remiro": "رمیرو",
    "iago aspas": "آسپاس", "aspas": "آسپاس",
    "mason greenwood": "گرین‌وود", "greenwood": "گرین‌وود",
    "geronimo rulli": "رولی", "rulli": "رولی",
    "alexandre lacazette": "لاکازت", "lacazette": "لاکازت",
    "rayan cherki": "شرکی", "cherki": "شرکی",
    "jean-philippe mateta": "ماتتا", "mateta": "ماتتا",
    "eberechi eze": "ازه", "eze": "ازه",
    "dean henderson": "دین هندرسون",
    "evanilson": "اوانیلسون", "justin kluivert": "کلایورت", "kluivert": "کلایورت",
    "oliver baumann": "بائومان", "baumann": "بائومان",
    "andrej kramaric": "کراماریچ", "kramaric": "کراماریچ",
    "ciro immobile": "ایموبیله", "immobile": "ایموبیله",
    "rafa silva": "رافا سیلوا",
    "ayoub el kaabi": "ال‌کعبی", "el kaabi": "ال‌کعبی",
    "konstantinos tzolakis": "تزولاکیس", "tzolakis": "تزولاکیس",
    "daizen maeda": "مائدا", "maeda": "مائدا",
    "kasper schmeichel": "اشمایکل", "schmeichel": "اشمایکل",
    "barnabas varga": "وارگا", "varga": "وارگا",
    "denes dibusz": "دیبوش", "dibusz": "دیبوش",
    "martin baturina": "باتورینا", "baturina": "باتورینا",
    "bruno petkovic": "پتکوویچ", "petkovic": "پتکوویچ",
    "kasper dolberg": "دولبرگ", "dolberg": "دولبرگ",
    "mikael ishak": "اسحاق", "ishak": "اسحاق",
    "bartosz mrozek": "مروژک", "mrozek": "مروژک",
    "jesus imaz": "ایماز", "imaz": "ایماز",
    "afimico pululu": "پولولو", "pululu": "پولولو",
    "stevan jovetic": "یووتیچ", "jovetic": "یووتیچ",
    "koki ogawa": "اوگاوا", "ogawa": "اوگاوا",
}

# پسوندهای نسلی/عمومی که هرگز به‌تنهایی نام‌خانوادگی یکتا محسوب نمی‌شوند
_NON_SURNAME_SUFFIXES: set[str] = {
    "junior", "jr", "sr", "senior", "filho", "neto", "ii", "iii",
    "de", "da", "do", "dos", "das", "del", "van", "von", "al", "el",
}


def translate_player_fa(name: str | None) -> str:
    """تبدیل دقیق نام بازیکن/گلزن/دروازه‌بان به فارسی روان از طریق سرویس واحد هویت نام‌ها (v0.77.0)."""
    from src.xgpedia.core.identity_service import resolve_player_name_fa

    return resolve_player_name_fa(name)

def format_scorers_fa(raw_scorers: str | None) -> str:
    """تبدیل رشتهٔ گلزنان (مثلاً `Wirtz 12′, Salah 64′`) به فارسی روان (`ویرتز ۱۲′، صلاح ۶۴′`)."""
    import re as _re

    s = str(raw_scorers or "").strip()
    if not s:
        return ""
    items = [x.strip() for x in _re.split(r"[،,]+", s) if x.strip()]
    out: list[str] = []
    for it in items:
        # جدا کردن نام بازیکن از دقیقه (مثلاً "Víctor Muñoz 82′" یا "Son 15'")
        m = _re.match(r"^(.+?)\s+(\d+(?:\+\d+)?\s*[′']?)$", it)
        if m:
            nm_fa = translate_player_fa(m.group(1))
            min_s = m.group(2).replace("'", "′")
            if not min_s.endswith("′"):
                min_s += "′"
            out.append(f"{nm_fa} {min_s}")
        else:
            out.append(translate_player_fa(it))
    return "، ".join(out)


# نام کوتاه و مصطلح تیم‌ها برای جلوگیری از برش با «...» در هدر کارت‌های گرافیکی
CARD_SHORT_TEAM_NAMES_FA: dict[str, str] = {
    "Borussia Monchengladbach": "گلادباخ",
    "Eintracht Frankfurt": "فرانکفورت",
    "PSV Eindhoven": "آیندهوون",
    "Sporting CP": "اسپورتینگ",
    "Nottingham Forest": "ناتینگهام",
    "Borussia Dortmund": "دورتموند",
    "Atletico Madrid": "اتلتیکو",
    "Athletic Club": "بیلبائو",
    "Red Bull Salzburg": "سالزبورگ",
    "Crystal Palace": "پالاس",
    "RB Leipzig": "لایپزیگ",
    "Shakhtar Donetsk": "شاختار",
    "Bayer Leverkusen": "لورکوزن",
    "Olympique Marseille": "مارسی",
    "Olympique Lyon": "لیون",
    "Real Sociedad": "سوسیداد",
    "Wolverhampton": "ولوز",
    "Sheffield United": "شفیلد",
    "West Ham United": "وستهم",
    "West Ham": "وستهم",
    "Newcastle United": "نیوکاسل",
    "Tottenham Hotspur": "تاتنهام",
    "Brighton & Hove Albion": "برایتون",
    "Red Star Belgrade": "ستاره سرخ",
    "Slovan Bratislava": "اسلووان",
    "Sturm Graz": "اشتورم گراتس",
    "Union Saint-Gilloise": "سنت ژیلواز",
    "Sabah FK": "صباح باکو",
    "Viktoria Plzen": "ویکتوریا پلژن",
    "Jagiellonia Bialystok": "یاگیلونیا",
    "AC Omonia": "اومونیا",
    "Hapoel Be'er Sheva": "بئرشبع",
    "NEC Nijmegen": "نایمخن",
    "OFI Crete": "او.اف.آی",
    "Levski Sofia": "لفسکی",
    "Ararat-Armenia": "آرارات",
}


CARD_SHORT_TEAM_NAMES_BY_FA: dict[str, str] = {
    "اتلتیکو مادرید": "اتلتیکو",
    "پاریس سن‌ژرمن": "پاریس سن‌ژرمن",
    "اتلتیک بیلبائو": "بیلبائو",
    "بروسیا دورتموند": "دورتموند",
    "بوروسیا دورتموند": "دورتموند",
    "بروسیا مونشن‌گلادباخ": "گلادباخ",
    "بوروسیا مونشن‌گلادباخ": "گلادباخ",
    "آینتراخت فرانکفورت": "فرانکفورت",
    "اسپورتینگ لیسبون": "اسپورتینگ",
    "ناتینگهام فارست": "ناتینگهام",
    "پی‌اس‌وی آیندهوون": "آیندهوون",
    "ردبول سالزبورگ": "سالزبورگ",
    "کریستال پالاس": "پالاس",
    "آر بی لایپزیگ": "لایپزیگ",
    "شاختار دونتسک": "شاختار",
    "یونیون سنت ژیلواز": "سنت ژیلواز",
    "اسلووان براتیسلاوا": "اسلووان",
    "المپیک مارسی": "مارسی",
    "المپیک لیون": "لیون",
    "بایر لورکوزن": "لورکوزن",
    "رئال سوسیداد": "سوسیداد",
}


def card_short_team_name_fa(name_en: str, name_fa: str = "", max_chars: int = 13) -> str:
    """برگرداندن نام کوتاه و مصطلح فارسی تیم برای هدر کارت (به‌جای برش با سه‌نقطه)."""
    import unicodedata

    canon = canonical_team_name(name_en) if name_en else ""
    canon_ascii = "".join(
        ch for ch in unicodedata.normalize("NFKD", canon) if not unicodedata.combining(ch)
    ).strip()
    fa = (name_fa or (team_name_fa(name_en) if name_en else "")).strip()
    if fa in CARD_SHORT_TEAM_NAMES_BY_FA:
        return CARD_SHORT_TEAM_NAMES_BY_FA[fa]
    if canon in CARD_SHORT_TEAM_NAMES_FA:
        return CARD_SHORT_TEAM_NAMES_FA[canon]
    if canon_ascii in CARD_SHORT_TEAM_NAMES_FA:
        return CARD_SHORT_TEAM_NAMES_FA[canon_ascii]
    if len(fa) <= max_chars:
        return fa
    parts = fa.split()
    if len(parts) >= 2:
        if parts[0] in ("بروسیا", "بوروسیا", "آینتراخت", "المپیک", "آر", "ردبول", "بایر", "اتلتیک"):
            cand = parts[-1]
        else:
            cand = parts[0]
        if 3 <= len(cand) <= max_chars:
            return cand
    return fa
