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



async def _generate_v32_modular_post_async(
    *,
    post_type: str,
    item: dict[str, Any],
    hydrate_fn: Any,
    render_fn: Any,
    formats_map: dict[str, tuple[int, int]],
    title: str,
    caption_text: str,
    slide: str = "slide1",
    header_mode: str = "full",
    fmt: str = "4:5",
    theme: str | None = None,
    custom_modules: list[dict[str, Any]] | None = None,
    extra_kwargs: dict[str, Any] | None = None,
    platform: str = "telegram",
    out_dir: Path | None = None,
    progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    import asyncio
    from src.xgpedia.render.render_png import render as render_png_async

    init_db()
    item_id = str(item.get("id") or f"{post_type}_custom")
    fixture_key = f"{post_type}:{item_id}:{slide}"
    if progress_cb:
        await progress_cb(f"⏳ (۱/۳) در حال تکمیل داده‌های زنده ({fmt})...")

    try:
        enriched = await asyncio.to_thread(hydrate_fn, dict(item)) if hydrate_fn else dict(item)
        now_iso = datetime.now(timezone.utc).isoformat()
        with db() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(content_version), 0) AS mv FROM posts "
                "WHERE fixture_id = ? AND post_type = ? AND target_platform = ?",
                (fixture_key, post_type, platform),
            ).fetchone()
            ver = int(row["mv"] if row else 0) + 1
            cur = conn.execute(
                """INSERT INTO posts
                   (fixture_id, post_type, target_platform, content_version, status, title, caption, draft_json, fact_json, created_at)
                   VALUES (?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?)""",
                (
                    fixture_key, post_type, platform, ver, title, caption_text,
                    json.dumps({"title": title, "slide": slide, "header_mode": header_mode, "fmt": fmt, "theme": theme}, ensure_ascii=False),
                    json.dumps(enriched, ensure_ascii=False), now_iso,
                ),
            )
            post_id = int(cur.lastrowid)

        if progress_cb:
            await progress_cb(f"⏳ (۲/۳) در حال رندر کارت ماژولار ({slide} | {fmt})...")

        target_out = Path(out_dir or (ROOT / "output"))
        target_out.mkdir(parents=True, exist_ok=True)
        w, hgt = formats_map.get(fmt, formats_map["4:5"])
        stem = f"post_{post_id}_v{ver}_{post_type}_{slide}"
        html_path = target_out / f"{stem}_{w}x{hgt}.html"
        kwargs: dict[str, Any] = {"fmt": fmt, "header_mode": header_mode, "modules": custom_modules}
        if post_type in {"h2h_teams", "top_scorers", "player_fc27", "matchday_results", "h2h_players", "quote", "debate", "number_of_day"}:
            kwargs["slide"] = slide
        if extra_kwargs:
            kwargs.update(extra_kwargs)
        if theme is not None:
            kwargs["theme"] = theme
        html_str = render_fn(enriched, **kwargs)
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


async def generate_h2h_teams_post_async(
    item: dict[str, Any], *, slide: str = "slide1", header_mode: str = "full", fmt: str = "4:5",
    theme: str = "classic", custom_modules: list[dict[str, Any]] | None = None,
    platform: str = "telegram", out_dir: Path | None = None, progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    from src.xgpedia.providers.h2h_teams_free import hydrate_h2h_teams_item
    from src.xgpedia.render.card_kit.h2h_teams_card import H2H_TEAMS_FORMATS, render_h2h_teams_html
    h = (item.get("home") or {}).get("name", "")
    a = (item.get("away") or {}).get("name", "")
    title = f"تقابل مستقیم | {h} مقابل {a}"
    cap = f"⚔️ تقابل مستقیم {h} و {a} ({item.get('competition', '')})\n{item.get('eraNote') or item.get('round') or ''}\n📊 منبع: {item.get('source', 'ESPN / XGPedia')}\n@XGPedia"
    return await _generate_v32_modular_post_async(
        post_type="h2h_teams", item=item, hydrate_fn=hydrate_h2h_teams_item, render_fn=render_h2h_teams_html,
        formats_map=H2H_TEAMS_FORMATS, title=title, caption_text=cap, slide=slide, header_mode=header_mode,
        fmt=fmt, theme=theme, custom_modules=custom_modules, platform=platform, out_dir=out_dir, progress_cb=progress_cb,
    )


async def generate_player_fc27_post_async(
    item: dict[str, Any], *, slide: str = "slide1", header_mode: str = "full", fmt: str = "4:5",
    theme: str | None = None, custom_modules: list[dict[str, Any]] | None = None,
    platform: str = "telegram", out_dir: Path | None = None, progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    from src.xgpedia.providers.player_fc27_free import hydrate_player_fc27_item
    from src.xgpedia.render.card_kit.player_fc27_card import FC27_FORMATS, render_player_fc27_html
    title = f"کارت FC27 | {item.get('name', '')} ({item.get('club', '')})"
    cap = f"🃏 کارت FC27 {item.get('name', '')} ({item.get('club', '')}) — ریتینگ {item.get('ovr', '')}\n{item.get('verdictBody') or ''}\n📊 منبع: {item.get('source', 'Opta / FPL')}\n@XGPedia"
    return await _generate_v32_modular_post_async(
        post_type="player_fc27", item=item, hydrate_fn=hydrate_player_fc27_item, render_fn=render_player_fc27_html,
        formats_map=FC27_FORMATS, title=title, caption_text=cap, slide=slide, header_mode=header_mode,
        fmt=fmt, theme=theme, custom_modules=custom_modules, platform=platform, out_dir=out_dir, progress_cb=progress_cb,
    )


async def generate_h2h_players_post_async(
    item: dict[str, Any], *, slide: str = "slide1", header_mode: str = "full", fmt: str = "4:5",
    theme: str = "classic", custom_modules: list[dict[str, Any]] | None = None,
    platform: str = "telegram", out_dir: Path | None = None, progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    from src.xgpedia.providers.h2h_players_free import hydrate_h2h_players_item
    from src.xgpedia.render.card_kit.h2h_players_card import H2H_PLAYERS_FORMATS, render_h2h_players_html
    p1 = (item.get("p1") or {}).get("name", "")
    p2 = (item.get("p2") or {}).get("name", "")
    title = f"مقایسه دو بازیکن | {p1} مقابل {p2}"
    cap = f"🆚 دوئل آماری {p1} و {p2} ({item.get('competition', '')})\n{item.get('context') or item.get('round') or ''}\n📊 منبع: {item.get('source', 'Opta / FPL')}\n@XGPedia"
    return await _generate_v32_modular_post_async(
        post_type="h2h_players", item=item, hydrate_fn=hydrate_h2h_players_item, render_fn=render_h2h_players_html,
        formats_map=H2H_PLAYERS_FORMATS, title=title, caption_text=cap, slide=slide, header_mode=header_mode,
        fmt=fmt, theme=theme, custom_modules=custom_modules, platform=platform, out_dir=out_dir, progress_cb=progress_cb,
    )


async def generate_top_scorers_post_async(
    item: dict[str, Any], *, slide: str = "slide1", header_mode: str = "full", fmt: str = "4:5",
    theme: str = "gold", sort_by: str = "goals", custom_modules: list[dict[str, Any]] | None = None,
    platform: str = "telegram", out_dir: Path | None = None, progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    from src.xgpedia.providers.top_scorers_free import hydrate_top_scorers_item
    from src.xgpedia.render.card_kit.top_scorers_card import TOP_SCORERS_FORMATS, render_top_scorers_html
    title = f"جدول گلزنان | {item.get('competition', '')}"
    cap = f"👟 کورس کفش طلا — {item.get('competition', '')}\n{item.get('paceInsight') or ''}\n📊 منبع: {item.get('source', 'Opta / FPL')}\n@XGPedia"
    return await _generate_v32_modular_post_async(
        post_type="top_scorers", item=item, hydrate_fn=hydrate_top_scorers_item, render_fn=render_top_scorers_html,
        formats_map=TOP_SCORERS_FORMATS, title=title, caption_text=cap, slide=slide, header_mode=header_mode,
        fmt=fmt, theme=theme, custom_modules=custom_modules, extra_kwargs={"sort_by": sort_by}, platform=platform, out_dir=out_dir, progress_cb=progress_cb,
    )


async def generate_matchday_results_post_async(
    item: dict[str, Any], *, slide: str = "slide1", header_mode: str = "full", fmt: str = "4:5",
    theme: str = "classic", custom_modules: list[dict[str, Any]] | None = None,
    platform: str = "telegram", out_dir: Path | None = None, progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    from src.xgpedia.render.card_kit.matchday_results_card import MATCHDAY_RESULTS_FORMATS, render_matchday_results_html
    title = f"نتایج ۲۴ ساعت اخیر | {item.get('competition', '')}"
    cap = f"📊 نتایج رسمی ۲۴ ساعت اخیر — {item.get('competition', '')}\n{item.get('editorialNote') or ''}\n📊 منبع: {item.get('source', 'ESPN Soccer API')}\n@XGPedia"
    return await _generate_v32_modular_post_async(
        post_type="matchday_results", item=item, hydrate_fn=None, render_fn=render_matchday_results_html,
        formats_map=MATCHDAY_RESULTS_FORMATS, title=title, caption_text=cap, slide=slide, header_mode=header_mode,
        fmt=fmt, theme=theme, custom_modules=custom_modules, platform=platform, out_dir=out_dir, progress_cb=progress_cb,
    )


async def generate_quote_post_async(
    item: dict[str, Any], *, slide: str = "slide1", header_mode: str = "full", fmt: str = "4:5",
    hl_style: str | None = None, grade: str | None = None, custom_modules: list[dict[str, Any]] | None = None,
    platform: str = "telegram", out_dir: Path | None = None, progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    import asyncio
    from src.xgpedia.providers.quote_free import hydrate_quote_item
    from src.xgpedia.render.card_kit.quote_card import QUOTE_FORMATS, render_quote_html
    if progress_cb:
        await progress_cb("⏳ در حال ترجمه فارسی نقل‌قول و دریافت آمار زنده...")
    item = await asyncio.to_thread(hydrate_quote_item, item)
    sp = str(item.get("speaker") or "نقل‌قول روز")
    comp = str(item.get("competition") or "فوتبال جهان")
    q_clean = str(item.get("quote") or "").replace("*", "")
    title = f"نقل‌قول روز | {sp}"
    cap = f"💬 {sp} ({comp}):\n«{q_clean}»\n📊 منبع: {item.get('source', 'XGPedia')}\n@XGPedia"
    extra: dict[str, Any] = {}
    if hl_style:
        extra["hl_style"] = hl_style
    if grade:
        extra["grade"] = grade
    return await _generate_v32_modular_post_async(
        post_type="quote", item=item, hydrate_fn=None, render_fn=render_quote_html,
        formats_map=QUOTE_FORMATS, title=title, caption_text=cap, slide=slide, header_mode=header_mode,
        fmt=fmt, custom_modules=custom_modules, extra_kwargs=extra or None,
        platform=platform, out_dir=out_dir, progress_cb=progress_cb,
    )


async def generate_debate_post_async(
    item: dict[str, Any], *, slide: str = "slide1", header_mode: str = "full", fmt: str = "4:5",
    theme: str = "classic", custom_modules: list[dict[str, Any]] | None = None,
    platform: str = "telegram", out_dir: Path | None = None, progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    from src.xgpedia.providers.debate_free import hydrate_debate_item
    from src.xgpedia.render.card_kit.debate_card import DEBATE_FORMATS, render_debate_html
    sa = (item.get("sideA") or {}).get("name", "")
    sb = (item.get("sideB") or {}).get("name", "")
    title = f"مناظره روز | {sa} × {sb}"
    cap = f"🔥 {item.get('title', '')}\n⚔️ {sa} در برابر {sb}\n{item.get('verdict') or ''}\n💬 {item.get('cta') or 'رأی تو چیه؟'}\n📊 منبع: {item.get('source', 'XGPedia')}\n@XGPedia"
    return await _generate_v32_modular_post_async(
        post_type="debate", item=item, hydrate_fn=hydrate_debate_item, render_fn=render_debate_html,
        formats_map=DEBATE_FORMATS, title=title, caption_text=cap, slide=slide, header_mode=header_mode,
        fmt=fmt, theme=theme, custom_modules=custom_modules,
        platform=platform, out_dir=out_dir, progress_cb=progress_cb,
    )


async def generate_number_of_day_post_async(
    item: dict[str, Any], *, slide: str = "slide1", header_mode: str = "full", fmt: str = "4:5",
    theme: str = "lalezar", custom_modules: list[dict[str, Any]] | None = None,
    platform: str = "telegram", out_dir: Path | None = None, progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    from src.xgpedia.providers.number_of_day_free import hydrate_number_of_day_item
    from src.xgpedia.render.card_kit.number_of_day_card import NOD_FORMATS, render_number_of_day_html
    item = hydrate_number_of_day_item(item)
    num = f"{item.get('number', '')}{item.get('suffix', '')}"
    sub = str(item.get("subject") or "عدد روز")
    title = f"عدد روز | {num} — {sub}"
    cap = f"🔢 عدد روز XGPedia: {num} {item.get('unit', '')}\n📌 {item.get('headline', '')}\n{item.get('body', '')}\n📊 منبع: {item.get('source', 'XGPedia')}\n@XGPedia"
    return await _generate_v32_modular_post_async(
        post_type="number_of_day", item=item, hydrate_fn=hydrate_number_of_day_item, render_fn=render_number_of_day_html,
        formats_map=NOD_FORMATS, title=title, caption_text=cap, slide=slide, header_mode=header_mode,
        fmt=fmt, theme=theme, custom_modules=custom_modules,
        platform=platform, out_dir=out_dir, progress_cb=progress_cb,
    )


async def generate_matchweek_wrapup_post_async(
    item: dict[str, Any], *, slide: str = "slide1", header_mode: str = "full", fmt: str = "4:5",
    theme: str = "classic", custom_modules: list[dict[str, Any]] | None = None,
    platform: str = "telegram", out_dir: Path | None = None, progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    from src.xgpedia.render.card_kit.matchweek_wrapup_card import WRAPUP_FORMATS, render_matchweek_wrapup_html
    comp = str(item.get("competition") or "لیگ برتر انگلیس")
    rnd = str(item.get("round") or "خلاصهٔ هفته و قدرت فرم")
    verdict = str(item.get("editorialVerdict") or "")
    title = f"خلاصهٔ هفته | {comp}"
    cap = f"📊 {rnd}\n{verdict}\n📈 منبع: {item.get('source', 'XGPedia')}\n@XGPedia"
    return await _generate_v32_modular_post_async(
        post_type="matchweek_wrapup", item=item, hydrate_fn=None, render_fn=render_matchweek_wrapup_html,
        formats_map=WRAPUP_FORMATS, title=title, caption_text=cap, slide=slide, header_mode=header_mode,
        fmt=fmt, theme=theme, custom_modules=custom_modules,
        platform=platform, out_dir=out_dir, progress_cb=progress_cb,
    )


async def generate_shotmap_xg_post_async(
    item: dict[str, Any], *, slide: str = "slide1", header_mode: str = "full", fmt: str = "4:5",
    theme: str = "classic", custom_modules: list[dict[str, Any]] | None = None,
    platform: str = "telegram", out_dir: Path | None = None, progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    from src.xgpedia.providers.shotmap_xg_free import hydrate_shotmap_xg_item
    from src.xgpedia.render.card_kit.shotmap_xg_card import SHOTMAP_FORMATS, render_shotmap_xg_html
    h_nm = str((item.get("home") or {}).get("name") or "")
    a_nm = str((item.get("away") or {}).get("name") or "")
    title = f"نقشهٔ شوت و امید گل | {h_nm} × {a_nm}"
    cap = f"🎯 نقشهٔ شوت و مومنتوم امید گل | {h_nm} × {a_nm}\n{item.get('editorialVerdict') or ''}\n📊 منبع: {item.get('source', 'Understat / XGPedia')}\n@XGPedia"
    return await _generate_v32_modular_post_async(
        post_type="shotmap_xg", item=item, hydrate_fn=hydrate_shotmap_xg_item, render_fn=render_shotmap_xg_html,
        formats_map=SHOTMAP_FORMATS, title=title, caption_text=cap, slide=slide, header_mode=header_mode,
        fmt=fmt, theme=theme, custom_modules=custom_modules,
        platform=platform, out_dir=out_dir, progress_cb=progress_cb,
    )


async def generate_value_radar_post_async(
    item: dict[str, Any], *, slide: str = "slide1", header_mode: str = "full", fmt: str = "4:5",
    theme: str = "classic", custom_modules: list[dict[str, Any]] | None = None,
    platform: str = "telegram", out_dir: Path | None = None, progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    from src.xgpedia.providers.value_radar_free import hydrate_value_radar_item
    from src.xgpedia.render.card_kit.value_radar_card import VALUE_RADAR_FORMATS, render_value_radar_html
    ttl = str(item.get("title") or "رادار ارزش بازار (+EV)")
    verdict = str(item.get("editorial_verdict") or "")
    title = f"رادار ارزش بازار | {ttl}"
    cap = f"💎 {ttl}\n{verdict}\n📊 منبع: {item.get('source', 'Opta FPL / XGPedia')}\n@XGPedia"
    return await _generate_v32_modular_post_async(
        post_type="value_radar", item=item, hydrate_fn=hydrate_value_radar_item, render_fn=render_value_radar_html,
        formats_map=VALUE_RADAR_FORMATS, title=title, caption_text=cap, slide=slide, header_mode=header_mode,
        fmt=fmt, theme=theme, custom_modules=custom_modules,
        platform=platform, out_dir=out_dir, progress_cb=progress_cb,
    )


async def generate_lineup_injuries_post_async(
    item: dict[str, Any], *, slide: str = "slide1", header_mode: str = "full", fmt: str = "4:5",
    theme: str = "classic", custom_modules: list[dict[str, Any]] | None = None,
    platform: str = "telegram", out_dir: Path | None = None, progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    from src.xgpedia.providers.lineup_injuries_free import hydrate_lineup_injuries_item
    from src.xgpedia.render.card_kit.lineup_injuries_card import LINEUP_FORMATS, render_lineup_injuries_html
    h_nm = str((item.get("home") or {}).get("name") or "")
    a_nm = str((item.get("away") or {}).get("name") or "")
    verdict = str(item.get("editorial_verdict") or "")
    title = f"ترکیب احتمالی و غایبان | {h_nm} × {a_nm}"
    cap = f"📋 ترکیب احتمالی و غایبان | {h_nm} × {a_nm}\n{verdict}\n📊 منبع: {item.get('source', 'Opta FPL / XGPedia')}\n@XGPedia"
    return await _generate_v32_modular_post_async(
        post_type="lineup_injuries", item=item, hydrate_fn=hydrate_lineup_injuries_item, render_fn=render_lineup_injuries_html,
        formats_map=LINEUP_FORMATS, title=title, caption_text=cap, slide=slide, header_mode=header_mode,
        fmt=fmt, theme=theme, custom_modules=custom_modules,
        platform=platform, out_dir=out_dir, progress_cb=progress_cb,
    )
