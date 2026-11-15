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
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", ROOT / "data" / "dev.sqlite"))
RAW_PAYLOAD_DIR = Path(os.environ.get("RAW_PAYLOAD_DIR", ROOT / "data" / "raw"))

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
    """نام فارسی یکدست تیم از نگاشت/واژه‌نامه؛ اگر نبود، همان ورودی برمی‌گردد.

    قاعدهٔ تحریریه: نام تیم/بازیکن خارج از واژه‌نامه از سوی validator رد می‌شود.
    """
    m = load_team_mapping()
    for canonical, t in m.get("teams", {}).items():
        if name_en in (canonical, t.get("csv_short", ""), *t.get("aliases", [])):
            return t["name_fa"]
    g = load_glossary()
    for team in g.get("teams", []):
        if name_en in (team["name_en"], team["id"], *team.get("aliases", [])):
            return team["name_fa"]
    return name_en
