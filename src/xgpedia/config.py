"""پیکربندی مرکزی پروژه — همهٔ مسیرها و قواعد ثابت از اینجا خوانده می‌شوند.

اصل معماری: هیچ فایل کدی رنگ، آستانه یا مسیر را هاردکد نمی‌کند؛
همه‌چیز از config/ و brand/ می‌آید تا تعویض تصمیم فقط یک فایل JSON باشد.

نسخهٔ ۸: منبع اصلی داده football-data.co.uk (xG) + football-data.org (بازی/جدول) است.
API-Football فقط fallback پولی می‌ماند (تصمیم D4 بازنگری‌شده).
"""
from __future__ import annotations

import json
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


def canonical_team_name(raw_name: str, fdo_id: int | None = None) -> str:
    """تبدیل نام خام هر provider (مثل 'Liverpool FC' یا 'Hull City AFC') به نام canonical در team_mapping.json."""
    if not raw_name:
        return raw_name
    cleaned = raw_name.strip()
    m = load_team_mapping()
    all_teams = {}
    all_teams.update(m.get("relegated_2025_26", {}))
    all_teams.update(m.get("teams", {}))

    low = cleaned.lower()
    for canonical, info in all_teams.items():
        if canonical.lower() == low or str(info.get("csv_short", "")).lower() == low:
            return canonical

    norm = low
    for prefix in ("afc ", "fc "):
        if norm.startswith(prefix):
            norm = norm[len(prefix):].strip()
    for suffix in (" & hove albion fc", " & hove albion", " hotspur fc", " hotspur", " afc", " fc"):
        if norm.endswith(suffix):
            norm = norm[:-len(suffix)].strip()

    for canonical, info in all_teams.items():
        if canonical.lower() == norm or str(info.get("csv_short", "")).lower() == norm:
            return canonical

    for suffix in (" united", " city", " town", " albion", " wanderers"):
        if norm.endswith(suffix):
            cand = norm[:-len(suffix)].strip()
            for canonical in all_teams:
                if canonical.lower() == cand:
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
    for team in g.get("teams", []):
        if name_en in (team["name_en"], team["id"], *team.get("aliases", [])):
            return team["name_fa"]
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
    """ترجمهٔ فارسی نام سرمربیِ دریافت‌شدهٔ زنده از API (دیکشنری دقیق → ویکی‌پدیا/آوانویسی خودکار)."""
    name = str(coach_en or "").strip()
    if not name:
        return None
    if any("\u0600" <= ch <= "\u06FF" for ch in name):
        return name
    mapping = load_team_venues().get("coach_translations_fa", {})
    if name in mapping:
        return mapping[name]
    low = name.lower()
    for k, v in mapping.items():
        if k.lower() == low:
            return v
    return _transliterate_latin_to_fa(name) if allow_transliterate else name
