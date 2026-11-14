"""پیکربندی مرکزی پروژه — همهٔ مسیرها و قواعد ثابت از اینجا خوانده می‌شوند.

اصل معماری: هیچ فایل کدی رنگ، آستانه یا مسیر را هاردکد نمی‌کند؛
همه‌چیز از config/ و brand/ می‌آید تا تعویض تصمیم فقط یک فایل JSON باشد.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
BRAND_FILE = ROOT / "brand" / "brand.json"
THRESHOLDS_FILE = CONFIG_DIR / "thresholds.json"
GLOSSARY_FILE = CONFIG_DIR / "glossary_fa.json"
DATABASE_PATH = ROOT / "data" / "dev.sqlite"
RAW_PAYLOAD_DIR = ROOT / "data" / "raw"

DISPLAY_TZ = "Asia/Tehran"  # ذخیره همیشه UTC؛ نمایش «به وقت تهران (UTC+3:30)»


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


def team_name_fa(name_en: str) -> str:
    """نام فارسی یکدست تیم از واژه‌نامه؛ اگر نبود، همان ورودی برمی‌گردد.

    قاعدهٔ تحریریه: نام تیم/بازیکن خارج از واژه‌نامه از سوی validator رد می‌شود.
    """
    g = load_glossary()
    for team in g.get("teams", []):
        if name_en in (team["name_en"], team["id"], *team.get("aliases", [])):
            return team["name_fa"]
    return name_en
