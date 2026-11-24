"""مدیریت قالب‌های نام‌گذاری‌شدهٔ ذخیره‌شده توسط کاربر (حداکثر ۵ قالب برای هر نوع کارت ماژولار).

قالب‌ها در جدول موجود `sync_cache` دیتابیس SQLite ذخیره می‌شوند (بدون نیاز به migration جدید)
و شامل نام قالب، فرمت (`4:5`/`9:16`/`16:9`)، سبک هدر (`full`/`compact`) و لیست مرتب‌شدهٔ
ماژول‌ها (`id`, `enabled`, `span`: `full`/`half`) هستند.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from src.xgpedia.db import db, init_db

MAX_SAVED_TEMPLATES = 5


def _cache_key(card_type: str) -> str:
    clean = "".join(ch for ch in (card_type or "default").lower() if ch.isalnum() or ch == "_")
    return f"layout_templates:{clean}"


def list_layout_templates(card_type: str) -> list[dict[str, Any]]:
    """دریافت لیست قالب‌های ذخیره‌شدهٔ کاربر برای یک نوع کارت (حداکثر ۵ قالب)."""
    init_db()
    with db() as conn:
        row = conn.execute(
            "SELECT summary FROM sync_cache WHERE source_key = ?",
            (_cache_key(card_type),),
        ).fetchone()
    if not row or not row["summary"]:
        return []
    try:
        data = json.loads(str(row["summary"]))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_templates(card_type: str, items: list[dict[str, Any]]) -> None:
    init_db()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = json.dumps(items[:MAX_SAVED_TEMPLATES], ensure_ascii=False)
    with db() as conn:
        conn.execute(
            """
            INSERT INTO sync_cache (source_key, tehran_date, last_synced_at, summary)
            VALUES (?, 'global', ?, ?)
            ON CONFLICT(source_key) DO UPDATE SET
              last_synced_at=excluded.last_synced_at,
              summary=excluded.summary
            """,
            (_cache_key(card_type), now_iso, payload),
        )


def save_layout_template(
    card_type: str,
    name: str,
    *,
    fmt: str,
    header_mode: str,
    modules: list[dict[str, Any]],
    max_slots: int = MAX_SAVED_TEMPLATES,
) -> dict[str, Any]:
    """ذخیره یا به‌روزرسانی یک قالب نام‌گذاری‌شده (تا سقف max_slots=5)."""
    clean_name = " ".join(str(name or "").split()).strip()[:36]
    if not clean_name:
        raise ValueError("نام قالب نمی‌تواند خالی باشد.")

    compact_mods = [
        {
            "id": str(m.get("id") or ""),
            "enabled": bool(m.get("enabled", True)),
            "span": "half" if m.get("span") == "half" else "full",
        }
        for m in (modules or [])
        if m.get("id")
    ]
    entry = {
        "name": clean_name,
        "fmt": str(fmt or "4:5"),
        "header_mode": "compact" if header_mode == "compact" else "full",
        "modules": compact_mods,
        "saved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    existing = list_layout_templates(card_type)
    # اگر قالبی با همین نام وجود داشت، به‌روزرسانی شود
    for i, item in enumerate(existing):
        if str(item.get("name") or "").strip().lower() == clean_name.lower():
            existing[i] = entry
            _write_templates(card_type, existing)
            return entry

    if len(existing) >= max_slots:
        raise ValueError(
            f"سقف {max_slots} قالب ذخیره‌شده پر شده است. ابتدا یکی از قالب‌های قبلی را حذف کنید یا با همان نام ذخیره کنید."
        )
    existing.append(entry)
    _write_templates(card_type, existing)
    return entry


def delete_layout_template(card_type: str, index_0based: int) -> bool:
    """حذف قالب ذخیره‌شده بر اساس اندیس (۰-مبنا)."""
    existing = list_layout_templates(card_type)
    if 0 <= index_0based < len(existing):
        existing.pop(index_0based)
        _write_templates(card_type, existing)
        return True
    return False


def apply_template_to_modules(
    current_modules: list[dict[str, Any]],
    template: dict[str, Any],
) -> list[dict[str, Any]]:
    """اعمال ترتیب، فعال/غیرفعال بودن و عرض (۱/½) یک قالب ذخیره‌شده روی ماژول‌های دارای دیتای کارت فعلی."""
    by_id = {str(m["id"]): dict(m) for m in current_modules}
    ordered: list[dict[str, Any]] = []
    used: set[str] = set()

    for tm in template.get("modules") or []:
        mid = str(tm.get("id") or "")
        if mid in by_id:
            mod = by_id[mid]
            mod["enabled"] = bool(tm.get("enabled", True))
            want_half = tm.get("span") == "half"
            mod["span"] = "half" if (want_half and mod.get("can_half", False)) else "full"
            ordered.append(mod)
            used.add(mid)

    # ماژول‌های جدید یا غایب در قالب در انتها به‌صورت خاموش اضافه می‌شوند
    for m in current_modules:
        if str(m["id"]) not in used:
            mc = dict(m)
            mc["enabled"] = False
            ordered.append(mc)

    # تضمین حداقل یک ماژول فعال
    if ordered and not any(m["enabled"] for m in ordered):
        ordered[0]["enabled"] = True
    return ordered
