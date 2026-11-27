"""سرویس واحد هویت نام‌ها (Unified Identity Service — v0.77.0).

تجمیع مرکزی تمام نگاشت‌های نام بازیکنان (`glossary_fa.json`، `config._PLAYER_NAMES_FA`،
`injury_free._PLAYER_FA_MAP`) و هویت باشگاه‌ها (۱۵۱ باشگاه متقارن) با کش LRU و ممیزی یکتایی
تا هیچ تناقض نوشتاری میان کارت‌های مختلف XGPedia تکرار نشود.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Any

_NON_SURNAME_SUFFIXES = frozenset({
    "junior", "jr", "senior", "sr", "filho", "neto", "ii", "iii",
})


def _fold(text: str | None) -> str:
    tr = str.maketrans({
        "ø": "o", "Ø": "o", "ð": "d", "Ð": "d", "þ": "th", "Þ": "th",
        "ł": "l", "Ł": "l", "đ": "d", "Đ": "d", "ß": "ss",
        "æ": "ae", "Æ": "ae", "œ": "oe", "Œ": "oe",
    })
    s = unicodedata.normalize("NFKD", str(text or "").translate(tr))
    return "".join(ch for ch in s if not unicodedata.combining(ch)).strip().lower()


@lru_cache(maxsize=1)
def get_unified_player_map() -> dict[str, str]:
    """ادغام یکپارچهٔ هر ۳ منبع نام بازیکنان با اولویت:
      1. `config/glossary_fa.json` (مرجع اصلی بازبینی‌شده)
      2. `src.xgpedia.config._PLAYER_NAMES_FA`
      3. `src.xgpedia.providers.injury_free._PLAYER_FA_MAP`
    """
    from src.xgpedia import config as cfg

    merged: dict[str, str] = {}

    # لایهٔ ۳ (پایه): injury_free._PLAYER_FA_MAP
    try:
        from src.xgpedia.providers import injury_free as inj
        for k, v in getattr(inj, "_PLAYER_FA_MAP", {}).items():
            fk = _fold(k)
            fv = str(v or "").strip()
            if fk and fv:
                merged[fk] = fv
    except Exception:
        pass

    # لایهٔ ۲ (میانی): config._PLAYER_NAMES_FA
    for k, v in getattr(cfg, "_PLAYER_NAMES_FA", {}).items():
        fk = _fold(k)
        fv = str(v or "").strip()
        if fk and fv:
            merged[fk] = fv

    # لایهٔ ۱ (مرجع یگانه — بالاترین اولویت): config/glossary_fa.json
    init_candidates: dict[str, set[str]] = {}
    try:
        glossary_players = cfg.load_glossary().get("players", [])
    except Exception:
        glossary_players = []

    for p in glossary_players:
        fa_n = str(p.get("name_fa") or "").strip()
        en_raw = str(p.get("name_en") or "").strip()
        if not (fa_n and en_raw):
            continue
        fk = _fold(en_raw)
        if fk:
            merged[fk] = fa_n
            parts = fk.split()
            if len(parts) >= 2 and parts[-1] not in _NON_SURNAME_SUFFIXES:
                init_key = f"{parts[0][0]}.{parts[-1]}"
                init_candidates.setdefault(init_key, set()).add(fa_n)
        for al in p.get("aliases") or []:
            fa_al = _fold(str(al or ""))
            if fa_al and not any("\u0600" <= ch <= "\u06FF" for ch in fa_al):
                merged.setdefault(fa_al, fa_n)

    # فقط فرم‌های مخفف یکتا (مثل b.fernandes) را بدون تداخل اضافه کن
    for ik, fa_set in init_candidates.items():
        if len(fa_set) == 1:
            merged.setdefault(ik, next(iter(fa_set)))

    return merged


@lru_cache(maxsize=4096)
def resolve_player_name_fa(name: str | None) -> str:
    """ترجمهٔ یکدست و کش‌شدهٔ (LRU) نام بازیکن از انگلیسی به فارسی روی هر ۳ منبع."""
    s = str(name or "").strip()
    if not s:
        return ""
    if any("\u0600" <= ch <= "\u06FF" for ch in s):
        return s

    umap = get_unified_player_map()
    fold_full = _fold(s)

    # ۱) تطبیق دقیق نام کامل
    if fold_full in umap:
        return umap[fold_full]

    # ۲) فرم مخفف حرف اول با یا بدون فاصله (مثل B.Fernandes یا J. Oblak)
    m_init = re.match(r"^([A-Za-zÀ-ÿ])\.\s*(.+)$", s)
    if m_init:
        first_initial = _fold(m_init.group(1))
        s_clean = m_init.group(2).strip()
        fold_clean = _fold(s_clean)
        compact_init = f"{first_initial}.{fold_clean}"
        if compact_init in umap:
            return umap[compact_init]
        if fold_clean not in _NON_SURNAME_SUFFIXES and fold_clean in umap:
            return umap[fold_clean]
    else:
        s_clean = s
        fold_clean = fold_full

    # ۳) نام‌های سه‌کلمه‌ای یا بیشتر (First + Last)
    parts = fold_clean.split()
    if len(parts) >= 3:
        first_last = f"{parts[0]} {parts[-1]}"
        if first_last in umap:
            return umap[first_last]

    # ۴) تطبیق نام‌خانوادگی تک‌کلمه‌ای (فقط اگر پسوند عمومی نباشد و خودش نام کامل بازیکن دیگری نباشد)
    if len(parts) > 1 and parts[-1] not in _NON_SURNAME_SUFFIXES and parts[-1] in umap:
        cand_fa = umap[parts[-1]]
        if " " not in cand_fa.strip():
            return cand_fa

    # ۵) آوانویسی تمیز فارسی (بدون چسبیدن حرف اول مخفف)
    from src.xgpedia.config import _transliterate_latin_to_fa

    raw_words = s_clean.split()
    if len(raw_words) >= 2 and _fold(raw_words[-1]) in _NON_SURNAME_SUFFIXES:
        target = " ".join(raw_words[-2:])
    elif len(raw_words) >= 2 and len(s_clean) > 12:
        target = raw_words[-1]
    else:
        target = s_clean
    return _transliterate_latin_to_fa(target)


@lru_cache(maxsize=1024)
def resolve_team_identity(raw_name: str, fdo_id: int | None = None) -> dict[str, Any]:
    """سرویس واحد هویت باشگاه با کش LRU (نام استاندارد، کد سه‌حرفی، نام فارسی، ورزشگاه، رنگ و لوگو)."""
    from src.xgpedia import config as cfg

    canon = cfg.canonical_team_name(raw_name, fdo_id=fdo_id)
    ident = cfg.team_identity(canon) or {}
    venue = cfg.team_venue(canon) or {}
    crest = cfg.team_crest_path(canon)
    return {
        "raw": raw_name,
        "canonical": canon,
        "code": ident.get("code"),
        "name_fa": cfg.team_name_fa(canon),
        "stadium_fa": venue.get("stadium_fa"),
        "coach_fa": venue.get("coach_fa"),
        "colors": ident.get("colors") or {},
        "crest_path": str(crest) if crest else None,
    }


def clear_identity_caches() -> None:
    """پاک‌سازی کش‌های LRU (مناسب تست‌ها یا بارگذاری مجدد پیکربندی)."""
    get_unified_player_map.cache_clear()
    resolve_player_name_fa.cache_clear()
    resolve_team_identity.cache_clear()


def audit_identity_consistency() -> dict[str, Any]:
    """ممیزی خودکار یکتایی و تقارن ۱:۱ باشگاه‌ها و بازیکنان در کل سیستم."""
    from src.xgpedia import config as cfg

    gl = cfg.load_glossary()
    ti = cfg.load_team_identities().get("teams", {})
    tm = cfg.load_team_mapping().get("teams", {})
    tv = cfg.load_team_venues().get("teams", {})

    g_codes = [t["id"] for t in gl.get("teams", [])]
    i_codes = [v["code"] for v in ti.values()]
    win_reserved = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}

    umap = get_unified_player_map()
    return {
        "clubs_count": len(ti),
        "clubs_symmetric_1to1": set(ti.keys()) == set(tm.keys()) == set(tv.keys()) and set(g_codes) == set(i_codes),
        "duplicate_club_codes": len(i_codes) != len(set(i_codes)),
        "windows_reserved_codes": sorted(set(i_codes) & win_reserved),
        "unified_player_entries": len(umap),
    }
