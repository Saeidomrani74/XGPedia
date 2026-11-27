"""تولیدکننده‌های ناهمزمان کارت‌های استودیویی و ماژولار (استخراج‌شده از today_workflow.py)."""
from __future__ import annotations


import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.xgpedia.config import CURRENT_SEASON_START, ROOT, team_name_fa
from src.xgpedia.db import db, init_db
from src.xgpedia.publishers import telegram_publish as tp

TEHRAN_TZ = timezone(timedelta(hours=3, minutes=30))
FA_TO_EN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")



from src.xgpedia.today_workflow import PostGenerationResult, _diagnose_exception, _now_utc



async def generate_on_this_day_post_async(
    event: dict[str, Any],
    *,
    slide: str = "cover",
    theme: str = "core",
    fmt: str = "4:5",
    bg_mode: str | None = None,
    enabled_modules: list[str] | None = None,
    platform: str = "telegram",
    out_dir: Path | None = None,
    progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    """تولید ناهمزمان کارت «در چنین روزی» (Showreel V2) با رندر Playwright و ثبت در جدول posts."""
    import asyncio
    from src.xgpedia.render.card_kit.on_this_day_card import (
        build_on_this_day_caption,
        render_on_this_day_html,
    )
    from src.xgpedia.render.render_png import render as render_png_async
    from src.xgpedia.render.studio_engine import FORMATS

    init_db()
    ev_id = str(event.get("id") or "otd_custom")
    fixture_key = f"otd:{ev_id}:{slide}"

    if progress_cb:
        await progress_cb(f"⏳ (۱/۳) در حال آماده‌سازی کپشن مستند و قالب {slide} ({fmt})...")

    try:
        caption_text = build_on_this_day_caption(event, slide=slide)
        title = f"در چنین روزی | {event.get('title') or ev_id} ({event.get('year') or ''})"
        now_iso = datetime.now(timezone.utc).isoformat()
        with db() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(content_version), 0) AS mv FROM posts "
                "WHERE fixture_id = ? AND post_type = 'on_this_day' AND target_platform = ?",
                (fixture_key, platform),
            ).fetchone()
            ver = int(row["mv"] if row else 0) + 1
            cur = conn.execute(
                """INSERT INTO posts
                   (fixture_id, post_type, target_platform, content_version, status, title, caption, draft_json, fact_json, created_at)
                   VALUES (?, 'on_this_day', ?, ?, 'draft', ?, ?, ?, ?, ?)""",
                (
                    fixture_key,
                    platform,
                    ver,
                    title,
                    caption_text,
                    json.dumps(
                        {
                            "title": title,
                            "slide": slide,
                            "theme": theme,
                            "fmt": fmt,
                            "bg_mode": bg_mode,
                            "enabled_modules": enabled_modules,
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(event, ensure_ascii=False),
                    now_iso,
                ),
            )
            post_id = int(cur.lastrowid)
    except Exception as e:
        title_err, detail = _diagnose_exception("editorial", e)
        return PostGenerationResult(
            ok=False, fixture_id=fixture_key, failed_stage="editorial",
            error_title=title_err, error_detail=detail,
        )

    if progress_cb:
        await progress_cb(f"⏳ (۲/۳) در حال رندر پوستر «در چنین روزی» ({fmt})...")

    try:
        target_out = Path(out_dir or (ROOT / "output"))
        target_out.mkdir(parents=True, exist_ok=True)
        w, hgt = FORMATS.get(fmt, FORMATS["4:5"])
        stem = f"post_{post_id}_v{ver}_on_this_day_{slide}"
        html_path = target_out / f"{stem}_{w}x{hgt}.html"
        html_str = render_on_this_day_html(
            event,
            slide=slide,
            theme=theme,
            fmt=fmt,
            bg_mode=bg_mode,
            enabled_modules=enabled_modules,
        )
        html_path.write_text(html_str, encoding="utf-8")

        img_fmt = "jpeg" if platform == "instagram" else "png"
        img_path = target_out / f"{stem}_{w}x{hgt}.{img_fmt}"
        await asyncio.wait_for(
            render_png_async(str(html_path), str(img_path), w, hgt, img_fmt),
            timeout=45.0,
        )

        cap_path = target_out / f"post_{post_id}_v{ver}_caption.txt"
        cap_path.write_text(caption_text, encoding="utf-8")

        with db() as conn:
            conn.execute(
                "UPDATE posts SET status = 'awaiting_approval' WHERE post_id = ?",
                (post_id,),
            )

        return PostGenerationResult(
            ok=True,
            fixture_id=fixture_key,
            post_id=post_id,
            content_version=ver,
            title=title,
            image_path=img_path,
            html_path=html_path,
            caption_path=cap_path,
        )
    except Exception as e:
        title_err, detail = _diagnose_exception("render", e)
        return PostGenerationResult(
            ok=False, fixture_id=fixture_key, post_id=post_id,
            failed_stage="render", error_title=title_err, error_detail=detail,
        )


async def generate_news_post_async(
    item: dict[str, Any],
    *,
    layout: str = "cinematic",
    mode: str | None = None,
    fmt: str = "4:5",
    mood: str | None = None,
    photo_id: str | None = None,
    tint_mode: str = "light",
    enabled_modules: list[str] | None = None,
    platform: str = "telegram",
    out_dir: Path | None = None,
    progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    """تولید ناهمزمان کارت «خبر فوری و رسمی» (PRO WIRE v2) با رندر Playwright و ثبت در جدول posts."""
    import asyncio
    from src.xgpedia.render.card_kit.news_card import (
        NEWS_FORMATS,
        NEWS_MODES,
        build_news_caption,
        render_news_html,
    )
    from src.xgpedia.render.render_png import render as render_png_async

    init_db()
    item_id = str(item.get("id") or "news_custom")
    eff_mode = mode if mode in NEWS_MODES else str(item.get("mode") or "breaking")
    fixture_key = f"news:{item_id}:{layout}"

    if progress_cb:
        await progress_cb(f"⏳ (۱/۳) در حال ترجمهٔ ژورنالیستی خبر به فارسی و دریافت تصویر واقعی خبر ({fmt})...")

    try:
        from src.xgpedia.providers.breaking_news_free import (
            fetch_image_data_uri,
            translate_news_item_to_persian,
        )

        import threading

        cancel_ev = threading.Event()

        def _prepare_item() -> dict[str, Any]:
            enriched = translate_news_item_to_persian(item, cancel_event=cancel_ev)
            if cancel_ev.is_set():
                raise TimeoutError("زمان آماده‌سازی خبر به پایان رسید.")
            if not enriched.get("photoDataUri") and (enriched.get("photoUrl") or enriched.get("source_url")):
                data_uri = fetch_image_data_uri(enriched.get("photoUrl"), source_url=enriched.get("source_url"))
                if data_uri:
                    enriched["photoDataUri"] = data_uri
            return enriched

        try:
            item = await asyncio.wait_for(asyncio.to_thread(_prepare_item), timeout=110.0)
        finally:
            cancel_ev.set()
        caption_text = build_news_caption(item, mode=eff_mode)
        m_fa = NEWS_MODES.get(eff_mode, NEWS_MODES["breaking"])["fa"]
        clean_hl = str(item.get("headline") or item.get("title") or item_id).replace("*", "")
        title = f"{m_fa} | {clean_hl[:90]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        with db() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(content_version), 0) AS mv FROM posts "
                "WHERE fixture_id = ? AND post_type = 'breaking_news' AND target_platform = ?",
                (fixture_key, platform),
            ).fetchone()
            ver = int(row["mv"] if row else 0) + 1
            cur = conn.execute(
                """INSERT INTO posts
                   (fixture_id, post_type, target_platform, content_version, status, title, caption, draft_json, fact_json, created_at)
                   VALUES (?, 'breaking_news', ?, ?, 'draft', ?, ?, ?, ?, ?)""",
                (
                    fixture_key,
                    platform,
                    ver,
                    title,
                    caption_text,
                    json.dumps(
                        {
                            "title": title,
                            "layout": layout,
                            "mode": eff_mode,
                            "fmt": fmt,
                            "mood": mood,
                            "photo_id": photo_id,
                            "tint_mode": tint_mode,
                            "enabled_modules": enabled_modules,
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(item, ensure_ascii=False),
                    now_iso,
                ),
            )
            post_id = int(cur.lastrowid)
    except Exception as e:
        title_err, detail = _diagnose_exception("editorial", e)
        return PostGenerationResult(
            ok=False, fixture_id=fixture_key, failed_stage="editorial",
            error_title=title_err, error_detail=detail,
        )

    if progress_cb:
        await progress_cb(f"⏳ (۲/۳) در حال رندر پوستر خبری ({fmt})...")

    try:
        target_out = Path(out_dir or (ROOT / "output"))
        target_out.mkdir(parents=True, exist_ok=True)
        w, hgt = NEWS_FORMATS.get(fmt, NEWS_FORMATS["4:5"])
        stem = f"post_{post_id}_v{ver}_news_{layout}"
        html_path = target_out / f"{stem}_{w}x{hgt}.html"
        html_str = render_news_html(
            item,
            layout=layout,
            mode=eff_mode,
            fmt=fmt,
            mood=mood,
            photo_id=photo_id,
            tint_mode=tint_mode,
            enabled_modules=enabled_modules,
        )
        html_path.write_text(html_str, encoding="utf-8")

        img_fmt = "jpeg" if platform == "instagram" else "png"
        img_path = target_out / f"{stem}_{w}x{hgt}.{img_fmt}"
        await asyncio.wait_for(
            render_png_async(str(html_path), str(img_path), w, hgt, img_fmt),
            timeout=45.0,
        )

        cap_path = target_out / f"post_{post_id}_v{ver}_caption.txt"
        cap_path.write_text(caption_text, encoding="utf-8")

        with db() as conn:
            conn.execute(
                "UPDATE posts SET status = 'awaiting_approval' WHERE post_id = ?",
                (post_id,),
            )

        return PostGenerationResult(
            ok=True,
            fixture_id=fixture_key,
            post_id=post_id,
            content_version=ver,
            title=title,
            image_path=img_path,
            html_path=html_path,
            caption_path=cap_path,
        )
    except Exception as e:
        title_err, detail = _diagnose_exception("render", e)
        return PostGenerationResult(
            ok=False, fixture_id=fixture_key, post_id=post_id,
            failed_stage="render", error_title=title_err, error_detail=detail,
        )


async def generate_birthday_post_async(
    item: dict[str, Any],
    *,
    mode: str = "poster",
    fmt: str = "4:5",
    rim_light: bool = True,
    enabled_modules: list[str] | None = None,
    platform: str = "telegram",
    out_dir: Path | None = None,
    progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    """تولید ناهمزمان کارت «تولدت مبارک اسطوره» (Birthday Studio D47) با غنی‌سازی چندمنبعی و رندر Playwright."""
    import asyncio
    import threading
    from src.xgpedia.providers.birthday_free import enrich_birthday_player
    from src.xgpedia.render.card_kit.birthday_card import (
        BIRTHDAY_DEFAULT_MODE,
        BIRTHDAY_FORMATS,
        build_birthday_caption,
        render_birthday_html,
    )
    from src.xgpedia.render.render_png import render as render_png_async

    init_db()
    eff_mode = mode if mode in ("poster", "dossier", "minimal") else BIRTHDAY_DEFAULT_MODE
    item_id = str(item.get("id") or "bday_custom")
    fixture_key = f"birthday:{item_id}:{eff_mode}"

    if progress_cb:
        await progress_cb(f"⏳ (۱/۳) در حال تکمیل آمار واقعی از ویکی‌پدیا/TheSportsDB و نگارش یادداشت تولد ({fmt})...")

    try:
        cancel_ev = threading.Event()

        def _prepare() -> dict[str, Any]:
            return enrich_birthday_player(item, cancel_event=cancel_ev, fetch_network=True)

        try:
            enriched = await asyncio.wait_for(asyncio.to_thread(_prepare), timeout=110.0)
        finally:
            cancel_ev.set()

        caption_text = build_birthday_caption(enriched)
        nm = str(enriched.get("nameFa") or enriched.get("nameEn") or item_id)
        ag = enriched.get("age")
        title = f"تولدت مبارک {nm} ({ag} سالگی)" if ag else f"تولدت مبارک {nm}"
        now_iso = datetime.now(timezone.utc).isoformat()

        with db() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(content_version), 0) AS mv FROM posts "
                "WHERE fixture_id = ? AND post_type = 'birthday' AND target_platform = ?",
                (fixture_key, platform),
            ).fetchone()
            ver = int(row["mv"] if row else 0) + 1
            cur = conn.execute(
                """INSERT INTO posts
                   (fixture_id, post_type, target_platform, content_version, status, title, caption, draft_json, fact_json, created_at)
                   VALUES (?, 'birthday', ?, ?, 'draft', ?, ?, ?, ?, ?)""",
                (
                    fixture_key,
                    platform,
                    ver,
                    title,
                    caption_text,
                    json.dumps(
                        {
                            "title": title,
                            "mode": eff_mode,
                            "fmt": fmt,
                            "rim_light": rim_light,
                            "enabled_modules": enabled_modules,
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(enriched, ensure_ascii=False),
                    now_iso,
                ),
            )
            post_id = int(cur.lastrowid)
    except Exception as e:
        title_err, detail = _diagnose_exception("editorial", e)
        return PostGenerationResult(
            ok=False, fixture_id=fixture_key, failed_stage="editorial",
            error_title=title_err, error_detail=detail,
        )

    if progress_cb:
        await progress_cb(f"⏳ (۲/۳) در حال رندر پوستر تولد ({eff_mode} | {fmt})...")

    try:
        target_out = Path(out_dir or (ROOT / "output"))
        target_out.mkdir(parents=True, exist_ok=True)
        w, hgt = BIRTHDAY_FORMATS.get(fmt, BIRTHDAY_FORMATS["4:5"])
        stem = f"post_{post_id}_v{ver}_birthday_{eff_mode}"
        html_path = target_out / f"{stem}_{w}x{hgt}.html"
        html_str = render_birthday_html(
            enriched,
            mode=eff_mode,
            fmt=fmt,
            rim_light=rim_light,
            enabled_modules=enabled_modules,
        )
        html_path.write_text(html_str, encoding="utf-8")

        img_fmt = "jpeg" if platform == "instagram" else "png"
        img_path = target_out / f"{stem}_{w}x{hgt}.{img_fmt}"
        await asyncio.wait_for(
            render_png_async(str(html_path), str(img_path), w, hgt, img_fmt),
            timeout=45.0,
        )

        cap_path = target_out / f"post_{post_id}_v{ver}_caption.txt"
        cap_path.write_text(caption_text, encoding="utf-8")

        with db() as conn:
            conn.execute(
                "UPDATE posts SET status = 'awaiting_approval' WHERE post_id = ?",
                (post_id,),
            )

        return PostGenerationResult(
            ok=True,
            fixture_id=fixture_key,
            post_id=post_id,
            content_version=ver,
            title=title,
            image_path=img_path,
            html_path=html_path,
            caption_path=cap_path,
        )
    except Exception as e:
        title_err, detail = _diagnose_exception("render", e)
        return PostGenerationResult(
            ok=False, fixture_id=fixture_key, post_id=post_id,
            failed_stage="render", error_title=title_err, error_detail=detail,
        )


async def generate_transfer_post_async(
    item: dict[str, Any],
    *,
    slide: str = "slide1",
    header_mode: str = "full",
    fmt: str = "4:5",
    enabled_modules: list[str] | None = None,
    custom_modules: list[dict[str, Any]] | None = None,
    extra_kwargs: dict[str, Any] | None = None,
    platform: str = "telegram",
    out_dir: Path | None = None,
    progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    """تولید ناهمزمان کارت ماژولار «رادار نقل‌وانتقالات» (D48) با غنی‌سازی کامل پس از انتخاب شایعه."""
    import asyncio
    import threading
    from src.xgpedia.providers.transfer_radar_free import enrich_transfer_rumor
    from src.xgpedia.render.card_kit.transfer_radar_card import (
        TRANSFER_FORMATS,
        build_transfer_caption,
        render_transfer_radar_html,
    )
    from src.xgpedia.render.render_png import render as render_png_async

    init_db()
    item_id = str(item.get("id") or "tr_custom")
    fixture_key = f"transfer:{item_id}:{slide}"

    if progress_cb:
        await progress_cb(f"⏳ (۱/۳) در حال استخراج جزئیات کامل شایعه، عکس بازیکن و تحلیل فارسی ({fmt})...")

    try:
        cancel_ev = threading.Event()

        def _prepare() -> dict[str, Any]:
            return enrich_transfer_rumor(item, cancel_event=cancel_ev, fetch_network=True)

        try:
            enriched = await asyncio.wait_for(asyncio.to_thread(_prepare), timeout=110.0)
        finally:
            cancel_ev.set()

        caption_text = build_transfer_caption(enriched)
        pl_name = str((enriched.get("player") or {}).get("name") or item_id)
        to_name = str((enriched.get("to") or {}).get("name") or "")
        title = f"رادار نقل‌وانتقالات | {pl_name} ← {to_name}" if to_name else f"رادار نقل‌وانتقالات | {pl_name}"
        now_iso = datetime.now(timezone.utc).isoformat()

        with db() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(content_version), 0) AS mv FROM posts "
                "WHERE fixture_id = ? AND post_type = 'transfer_radar' AND target_platform = ?",
                (fixture_key, platform),
            ).fetchone()
            ver = int(row["mv"] if row else 0) + 1
            cur = conn.execute(
                """INSERT INTO posts
                   (fixture_id, post_type, target_platform, content_version, status, title, caption, draft_json, fact_json, created_at)
                   VALUES (?, 'transfer_radar', ?, ?, 'draft', ?, ?, ?, ?, ?)""",
                (
                    fixture_key,
                    platform,
                    ver,
                    title,
                    caption_text,
                    json.dumps(
                        {
                            "title": title,
                            "slide": slide,
                            "header_mode": header_mode,
                            "fmt": fmt,
                            "enabled_modules": enabled_modules,
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(enriched, ensure_ascii=False),
                    now_iso,
                ),
            )
            post_id = int(cur.lastrowid)
    except Exception as e:
        title_err, detail = _diagnose_exception("editorial", e)
        return PostGenerationResult(
            ok=False, fixture_id=fixture_key, failed_stage="editorial",
            error_title=title_err, error_detail=detail,
        )

    if progress_cb:
        await progress_cb(f"⏳ (۲/۳) در حال رندر کارت ماژولار رادار نقل‌وانتقالات ({slide} | {fmt})...")

    try:
        target_out = Path(out_dir or (ROOT / "output"))
        target_out.mkdir(parents=True, exist_ok=True)
        w, hgt = TRANSFER_FORMATS.get(fmt, TRANSFER_FORMATS["4:5"])
        stem = f"post_{post_id}_v{ver}_transfer_{slide}"
        html_path = target_out / f"{stem}_{w}x{hgt}.html"
        html_str = render_transfer_radar_html(
            enriched,
            slide=slide,
            header_mode=header_mode,
            fmt=fmt,
            enabled_modules=enabled_modules,
            custom_modules=custom_modules,
        )
        html_path.write_text(html_str, encoding="utf-8")

        img_fmt = "jpeg" if platform == "instagram" else "png"
        img_path = target_out / f"{stem}_{w}x{hgt}.{img_fmt}"
        await asyncio.wait_for(
            render_png_async(str(html_path), str(img_path), w, hgt, img_fmt),
            timeout=45.0,
        )

        cap_path = target_out / f"post_{post_id}_v{ver}_caption.txt"
        cap_path.write_text(caption_text, encoding="utf-8")

        with db() as conn:
            conn.execute(
                "UPDATE posts SET status = 'awaiting_approval' WHERE post_id = ?",
                (post_id,),
            )

        return PostGenerationResult(
            ok=True,
            fixture_id=fixture_key,
            post_id=post_id,
            content_version=ver,
            title=title,
            image_path=img_path,
            html_path=html_path,
            caption_path=cap_path,
        )
    except Exception as e:
        title_err, detail = _diagnose_exception("render", e)
        return PostGenerationResult(
            ok=False, fixture_id=fixture_key, post_id=post_id,
            failed_stage="render", error_title=title_err, error_detail=detail,
        )


async def generate_this_or_that_post_async(
    item: dict[str, Any],
    *,
    layout: str = "diagonal",
    fmt: str = "4:5",
    pick: str = "none",
    enabled_modules: list[str] | None = None,
    platform: str = "telegram",
    out_dir: Path | None = None,
    progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    """تولید ناهمزمان کارت اسلایدی «این یا اون؟» (This or That Showreel — D49)."""
    import asyncio
    from src.xgpedia.render.card_kit.this_or_that_card import (
        TOT_FORMATS,
        build_this_or_that_caption,
        render_this_or_that_html,
    )
    from src.xgpedia.render.render_png import render as render_png_async

    init_db()
    item_id = str(item.get("id") or "tot_custom")
    fixture_key = f"this_or_that:{item_id}:{layout}"

    if progress_cb:
        await progress_cb(f"⏳ (۱/۲) در حال آماده‌سازی کپشن جدالی و رندر کارت ({layout} | {fmt})...")

    try:
        caption_text = build_this_or_that_caption(item)
        lbl = str(item.get("label") or item.get("question") or item_id).lstrip("🔥✨ ").strip()
        title = f"این یا اون؟ | {lbl[:85]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        with db() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(content_version), 0) AS mv FROM posts "
                "WHERE fixture_id = ? AND post_type = 'this_or_that' AND target_platform = ?",
                (fixture_key, platform),
            ).fetchone()
            ver = int(row["mv"] if row else 0) + 1
            cur = conn.execute(
                """INSERT INTO posts
                   (fixture_id, post_type, target_platform, content_version, status, title, caption, draft_json, fact_json, created_at)
                   VALUES (?, 'this_or_that', ?, ?, 'draft', ?, ?, ?, ?, ?)""",
                (
                    fixture_key,
                    platform,
                    ver,
                    title,
                    caption_text,
                    json.dumps(
                        {"title": title, "layout": layout, "fmt": fmt, "pick": pick, "enabled_modules": enabled_modules},
                        ensure_ascii=False,
                    ),
                    json.dumps(item, ensure_ascii=False),
                    now_iso,
                ),
            )
            post_id = int(cur.lastrowid)

        target_out = Path(out_dir or (ROOT / "output"))
        target_out.mkdir(parents=True, exist_ok=True)
        w, hgt = TOT_FORMATS.get(fmt, TOT_FORMATS["4:5"])
        stem = f"post_{post_id}_v{ver}_tot_{layout}"
        html_path = target_out / f"{stem}_{w}x{hgt}.html"
        html_str = render_this_or_that_html(
            item,
            layout=layout,
            fmt=fmt,
            pick=pick,
            enabled_modules=enabled_modules,
        )
        html_path.write_text(html_str, encoding="utf-8")

        img_fmt = "jpeg" if platform == "instagram" else "png"
        img_path = target_out / f"{stem}_{w}x{hgt}.{img_fmt}"
        await asyncio.wait_for(
            render_png_async(str(html_path), str(img_path), w, hgt, img_fmt),
            timeout=45.0,
        )

        cap_path = target_out / f"post_{post_id}_v{ver}_caption.txt"
        cap_path.write_text(caption_text, encoding="utf-8")

        with db() as conn:
            conn.execute("UPDATE posts SET status = 'awaiting_approval' WHERE post_id = ?", (post_id,))

        return PostGenerationResult(
            ok=True,
            fixture_id=fixture_key,
            post_id=post_id,
            content_version=ver,
            title=title,
            image_path=img_path,
            html_path=html_path,
            caption_path=cap_path,
        )
    except Exception as e:
        title_err, detail = _diagnose_exception("render", e)
        return PostGenerationResult(
            ok=False, fixture_id=fixture_key, failed_stage="render",
            error_title=title_err, error_detail=detail,
        )


async def generate_players_rating_post_async(
    item: dict[str, Any],
    *,
    slide: str = "slide1",
    header_mode: str = "full",
    fmt: str = "4:5",
    pitch_mode: str | None = None,
    theme: str = "turf",
    kit_mode: bool = True,
    fx_mode: bool = True,
    enabled_modules: list[str] | None = None,
    custom_modules: list[dict[str, Any]] | None = None,
    platform: str = "telegram",
    out_dir: Path | None = None,
    progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    """تولید ناهمزمان کارت ماژولار «نمرات بازیکنان» (D51)."""
    import asyncio
    import threading
    from src.xgpedia.providers.players_rating_free import enrich_players_rating_match
    from src.xgpedia.render.card_kit.players_rating_card import (
        RATINGS_FORMATS,
        build_players_rating_caption,
        render_players_rating_html,
    )
    from src.xgpedia.render.render_png import render as render_png_async

    init_db()
    item_id = str(item.get("id") or "pr_custom")
    fixture_key = f"players_rating:{item_id}:{slide}"
    if progress_cb:
        await progress_cb(f"⏳ (۱/۳) در حال تکمیل نمرات و جمع‌بندی تحریریه مسابقه ({fmt})...")

    try:
        cancel_ev = threading.Event()
        try:
            enriched = await asyncio.wait_for(
                asyncio.to_thread(enrich_players_rating_match, item, cancel_event=cancel_ev, fetch_network=True),
                timeout=90.0,
            )
        finally:
            cancel_ev.set()

        caption_text = build_players_rating_caption(enriched)
        h_n = str((enriched.get("home") or {}).get("name") or "")
        a_n = str((enriched.get("away") or {}).get("name") or "")
        title = f"نمرات بازیکنان | {h_n} {enriched.get('homeGoals', 0)}-{enriched.get('awayGoals', 0)} {a_n}"
        now_iso = datetime.now(timezone.utc).isoformat()
        with db() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(content_version), 0) AS mv FROM posts "
                "WHERE fixture_id = ? AND post_type = 'players_rating' AND target_platform = ?",
                (fixture_key, platform),
            ).fetchone()
            ver = int(row["mv"] if row else 0) + 1
            cur = conn.execute(
                """INSERT INTO posts
                   (fixture_id, post_type, target_platform, content_version, status, title, caption, draft_json, fact_json, created_at)
                   VALUES (?, 'players_rating', ?, ?, 'draft', ?, ?, ?, ?, ?)""",
                (
                    fixture_key, platform, ver, title, caption_text,
                    json.dumps({"title": title, "slide": slide, "header_mode": header_mode, "fmt": fmt, "pitch_mode": pitch_mode, "theme": theme}, ensure_ascii=False),
                    json.dumps(enriched, ensure_ascii=False), now_iso,
                ),
            )
            post_id = int(cur.lastrowid)

        if progress_cb:
            await progress_cb(f"⏳ (۲/۳) در حال رندر کارت ماژولار نمرات بازیکنان ({slide} | {fmt})...")

        target_out = Path(out_dir or (ROOT / "output"))
        target_out.mkdir(parents=True, exist_ok=True)
        w, hgt = RATINGS_FORMATS.get(fmt, RATINGS_FORMATS["4:5"])
        stem = f"post_{post_id}_v{ver}_ratings_{slide}"
        html_path = target_out / f"{stem}_{w}x{hgt}.html"
        html_str = render_players_rating_html(
            enriched, slide=slide, header_mode=header_mode, fmt=fmt, pitch_mode=pitch_mode,
            theme=theme, kit_mode=kit_mode, fx_mode=fx_mode,
            enabled_modules=enabled_modules, custom_modules=custom_modules,
        )
        html_path.write_text(html_str, encoding="utf-8")
        img_fmt = "jpeg" if platform == "instagram" else "png"
        img_path = target_out / f"{stem}_{w}x{hgt}.{img_fmt}"
        await asyncio.wait_for(render_png_async(str(html_path), str(img_path), w, hgt, img_fmt), timeout=45.0)
        cap_path = target_out / f"post_{post_id}_v{ver}_caption.txt"
        cap_path.write_text(caption_text, encoding="utf-8")
        with db() as conn:
            conn.execute("UPDATE posts SET status = 'awaiting_approval' WHERE post_id = ?", (post_id,))
        return PostGenerationResult(
            ok=True, fixture_id=fixture_key, post_id=post_id, content_version=ver,
            title=title, image_path=img_path, html_path=html_path, caption_path=cap_path,
        )
    except Exception as e:
        title_err, detail = _diagnose_exception("render", e)
        return PostGenerationResult(ok=False, fixture_id=fixture_key, failed_stage="render", error_title=title_err, error_detail=detail)


async def generate_standings_post_async(
    item: dict[str, Any],
    *,
    slide: str = "slide1",
    header_mode: str = "hero",
    fmt: str = "4:5",
    lens: str | None = None,
    table_slice: str | None = None,
    spotlight: str | None = None,
    enabled_modules: list[str] | None = None,
    custom_modules: list[dict[str, Any]] | None = None,
    platform: str = "telegram",
    out_dir: Path | None = None,
    progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    """تولید ناهمزمان کارت ماژولار «جدول رده‌بندی» (D52)."""
    import asyncio
    from src.xgpedia.providers.standings_free import enrich_standings_league
    from src.xgpedia.render.card_kit.standings_card import (
        STANDINGS_FORMATS,
        build_standings_caption,
        render_standings_html,
    )
    from src.xgpedia.render.render_png import render as render_png_async

    init_db()
    item_id = str(item.get("id") or "st_custom")
    fixture_key = f"standings:{item_id}:{slide}"
    if progress_cb:
        await progress_cb(f"⏳ (۱/۳) در حال آماده‌سازی داده‌های جدول رده‌بندی ({fmt})...")

    try:
        enriched = await asyncio.to_thread(enrich_standings_league, item, fetch_network=False)
        caption_text = build_standings_caption(enriched)
        title = f"جدول رده‌بندی | {enriched.get('name', 'لیگ')}"
        now_iso = datetime.now(timezone.utc).isoformat()
        with db() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(content_version), 0) AS mv FROM posts "
                "WHERE fixture_id = ? AND post_type = 'standings' AND target_platform = ?",
                (fixture_key, platform),
            ).fetchone()
            ver = int(row["mv"] if row else 0) + 1
            cur = conn.execute(
                """INSERT INTO posts
                   (fixture_id, post_type, target_platform, content_version, status, title, caption, draft_json, fact_json, created_at)
                   VALUES (?, 'standings', ?, ?, 'draft', ?, ?, ?, ?, ?)""",
                (
                    fixture_key, platform, ver, title, caption_text,
                    json.dumps({"title": title, "slide": slide, "header_mode": header_mode, "fmt": fmt, "lens": lens, "table_slice": table_slice}, ensure_ascii=False),
                    json.dumps(enriched, ensure_ascii=False), now_iso,
                ),
            )
            post_id = int(cur.lastrowid)

        if progress_cb:
            await progress_cb(f"⏳ (۲/۳) در حال رندر کارت ماژولار جدول رده‌بندی ({slide} | {fmt})...")

        target_out = Path(out_dir or (ROOT / "output"))
        target_out.mkdir(parents=True, exist_ok=True)
        w, hgt = STANDINGS_FORMATS.get(fmt, STANDINGS_FORMATS["4:5"])
        stem = f"post_{post_id}_v{ver}_standings_{slide}"
        html_path = target_out / f"{stem}_{w}x{hgt}.html"
        html_str = render_standings_html(
            enriched, slide=slide, header_mode=header_mode, fmt=fmt, lens=lens,
            table_slice=table_slice, spotlight=spotlight,
            enabled_modules=enabled_modules, custom_modules=custom_modules,
        )
        html_path.write_text(html_str, encoding="utf-8")
        img_fmt = "jpeg" if platform == "instagram" else "png"
        img_path = target_out / f"{stem}_{w}x{hgt}.{img_fmt}"
        await asyncio.wait_for(render_png_async(str(html_path), str(img_path), w, hgt, img_fmt), timeout=45.0)
        cap_path = target_out / f"post_{post_id}_v{ver}_caption.txt"
        cap_path.write_text(caption_text, encoding="utf-8")
        with db() as conn:
            conn.execute("UPDATE posts SET status = 'awaiting_approval' WHERE post_id = ?", (post_id,))
        return PostGenerationResult(
            ok=True, fixture_id=fixture_key, post_id=post_id, content_version=ver,
            title=title, image_path=img_path, html_path=html_path, caption_path=cap_path,
        )
    except Exception as e:
        title_err, detail = _diagnose_exception("render", e)
        return PostGenerationResult(ok=False, fixture_id=fixture_key, failed_stage="render", error_title=title_err, error_detail=detail)


async def generate_injury_post_async(
    item: dict[str, Any],
    *,
    slide: str = "slide1",
    header_mode: str = "full",
    fmt: str = "4:5",
    severity_override: str | None = None,
    enabled_modules: list[str] | None = None,
    custom_modules: list[dict[str, Any]] | None = None,
    platform: str = "telegram",
    out_dir: Path | None = None,
    progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    """تولید ناهمزمان کارت ماژولار «آزمایشگاه مصدومیت» (D53)."""
    import asyncio
    import threading
    from src.xgpedia.providers.injury_free import enrich_injury_item
    from src.xgpedia.render.card_kit.injury_card import (
        INJURY_FORMATS,
        build_injury_caption,
        render_injury_html,
    )
    from src.xgpedia.render.render_png import render as render_png_async

    init_db()
    item_id = str(item.get("id") or "inj_custom")
    fixture_key = f"injury_lab:{item_id}:{slide}"
    if progress_cb:
        await progress_cb(f"⏳ (۱/۳) در حال تکمیل پرونده پزشکی، ترجمه فارسی و عکس بازیکن ({fmt})...")

    try:
        cancel_ev = threading.Event()
        try:
            enriched = await asyncio.wait_for(
                asyncio.to_thread(enrich_injury_item, item, cancel_event=cancel_ev, fetch_network=True),
                timeout=90.0,
            )
        finally:
            cancel_ev.set()

        caption_text = build_injury_caption(enriched)
        pl = enriched.get("player") or {}
        title = f"گزارش مصدومیت | {pl.get('name', '')} ({pl.get('club', '')})"
        now_iso = datetime.now(timezone.utc).isoformat()
        with db() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(content_version), 0) AS mv FROM posts "
                "WHERE fixture_id = ? AND post_type = 'injury_lab' AND target_platform = ?",
                (fixture_key, platform),
            ).fetchone()
            ver = int(row["mv"] if row else 0) + 1
            cur = conn.execute(
                """INSERT INTO posts
                   (fixture_id, post_type, target_platform, content_version, status, title, caption, draft_json, fact_json, created_at)
                   VALUES (?, 'injury_lab', ?, ?, 'draft', ?, ?, ?, ?, ?)""",
                (
                    fixture_key, platform, ver, title, caption_text,
                    json.dumps({"title": title, "slide": slide, "header_mode": header_mode, "fmt": fmt, "severity": severity_override}, ensure_ascii=False),
                    json.dumps(enriched, ensure_ascii=False), now_iso,
                ),
            )
            post_id = int(cur.lastrowid)

        if progress_cb:
            await progress_cb(f"⏳ (۲/۳) در حال رندر کارت ماژولار آزمایشگاه مصدومیت ({slide} | {fmt})...")

        target_out = Path(out_dir or (ROOT / "output"))
        target_out.mkdir(parents=True, exist_ok=True)
        w, hgt = INJURY_FORMATS.get(fmt, INJURY_FORMATS["4:5"])
        stem = f"post_{post_id}_v{ver}_injury_{slide}"
        html_path = target_out / f"{stem}_{w}x{hgt}.html"
        html_str = render_injury_html(
            enriched, slide=slide, header_mode=header_mode, fmt=fmt,
            severity_override=severity_override,
            enabled_modules=enabled_modules, custom_modules=custom_modules,
        )
        html_path.write_text(html_str, encoding="utf-8")
        img_fmt = "jpeg" if platform == "instagram" else "png"
        img_path = target_out / f"{stem}_{w}x{hgt}.{img_fmt}"
        await asyncio.wait_for(render_png_async(str(html_path), str(img_path), w, hgt, img_fmt), timeout=45.0)
        cap_path = target_out / f"post_{post_id}_v{ver}_caption.txt"
        cap_path.write_text(caption_text, encoding="utf-8")
        with db() as conn:
            conn.execute("UPDATE posts SET status = 'awaiting_approval' WHERE post_id = ?", (post_id,))
        return PostGenerationResult(
            ok=True, fixture_id=fixture_key, post_id=post_id, content_version=ver,
            title=title, image_path=img_path, html_path=html_path, caption_path=cap_path,
        )
    except Exception as e:
        title_err, detail = _diagnose_exception("render", e)
        return PostGenerationResult(ok=False, fixture_id=fixture_key, failed_stage="render", error_title=title_err, error_detail=detail)


async def generate_player_profile_post_async(
    item: dict[str, Any],
    *,
    slide: str = "slide1",
    header_mode: str = "full",
    fmt: str = "4:5",
    theme: str = "classic",
    enabled_modules: list[str] | None = None,
    custom_modules: list[dict[str, Any]] | None = None,
    platform: str = "telegram",
    out_dir: Path | None = None,
    progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    """تولید ناهمزمان کارت ماژولار «پروفایل فنی بازیکن» (D54)."""
    import asyncio
    import threading
    from src.xgpedia.providers.player_profile_free import enrich_player_profile
    from src.xgpedia.render.card_kit.player_card import (
        PLAYER_FORMATS,
        build_player_caption,
        render_player_html,
    )
    from src.xgpedia.render.render_png import render as render_png_async

    init_db()
    item_id = str(item.get("id") or "pl_custom")
    fixture_key = f"player_profile:{item_id}:{slide}"
    if progress_cb:
        await progress_cb(f"⏳ (۱/۳) در حال دریافت موج فرم، پرتره و گزارش دیده‌بان ({fmt})...")

    try:
        cancel_ev = threading.Event()
        try:
            enriched = await asyncio.wait_for(
                asyncio.to_thread(enrich_player_profile, item, cancel_event=cancel_ev, fetch_network=True),
                timeout=90.0,
            )
        finally:
            cancel_ev.set()

        caption_text = build_player_caption(enriched)
        title = f"پروفایل بازیکن | {enriched.get('name', '')} ({enriched.get('club', '')})"
        now_iso = datetime.now(timezone.utc).isoformat()
        with db() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(content_version), 0) AS mv FROM posts "
                "WHERE fixture_id = ? AND post_type = 'player_profile' AND target_platform = ?",
                (fixture_key, platform),
            ).fetchone()
            ver = int(row["mv"] if row else 0) + 1
            cur = conn.execute(
                """INSERT INTO posts
                   (fixture_id, post_type, target_platform, content_version, status, title, caption, draft_json, fact_json, created_at)
                   VALUES (?, 'player_profile', ?, ?, 'draft', ?, ?, ?, ?, ?)""",
                (
                    fixture_key, platform, ver, title, caption_text,
                    json.dumps({"title": title, "slide": slide, "header_mode": header_mode, "fmt": fmt, "theme": theme}, ensure_ascii=False),
                    json.dumps(enriched, ensure_ascii=False), now_iso,
                ),
            )
            post_id = int(cur.lastrowid)

        if progress_cb:
            await progress_cb(f"⏳ (۲/۳) در حال رندر کارت ماژولار پروفایل بازیکن ({slide} | {fmt})...")

        target_out = Path(out_dir or (ROOT / "output"))
        target_out.mkdir(parents=True, exist_ok=True)
        w, hgt = PLAYER_FORMATS.get(fmt, PLAYER_FORMATS["4:5"])
        stem = f"post_{post_id}_v{ver}_player_{slide}"
        html_path = target_out / f"{stem}_{w}x{hgt}.html"
        html_str = render_player_html(
            enriched, slide=slide, header_mode=header_mode, fmt=fmt, theme=theme,
            enabled_modules=enabled_modules, custom_modules=custom_modules,
        )
        html_path.write_text(html_str, encoding="utf-8")
        img_fmt = "jpeg" if platform == "instagram" else "png"
        img_path = target_out / f"{stem}_{w}x{hgt}.{img_fmt}"
        await asyncio.wait_for(render_png_async(str(html_path), str(img_path), w, hgt, img_fmt), timeout=45.0)
        cap_path = target_out / f"post_{post_id}_v{ver}_caption.txt"
        cap_path.write_text(caption_text, encoding="utf-8")
        with db() as conn:
            conn.execute("UPDATE posts SET status = 'awaiting_approval' WHERE post_id = ?", (post_id,))
        return PostGenerationResult(
            ok=True, fixture_id=fixture_key, post_id=post_id, content_version=ver,
            title=title, image_path=img_path, html_path=html_path, caption_path=cap_path,
        )
    except Exception as e:
        title_err, detail = _diagnose_exception("render", e)
        return PostGenerationResult(ok=False, fixture_id=fixture_key, failed_stage="render", error_title=title_err, error_detail=detail)
