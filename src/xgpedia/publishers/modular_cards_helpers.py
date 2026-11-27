"""توابع کمکی استودیوی کارت‌های ماژولار و ریلز (استخراج‌شده از modular_cards_bot.py در v0.73.0)."""
from __future__ import annotations

import logging
from typing import Any

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

log = logging.getLogger("xgpedia.modular_bot")


def _specs():
    from src.xgpedia.publishers.modular_cards_bot import CARD_SPECS
    return CARD_SPECS


async def _safe_answer(cb: CallbackQuery, text: str = "", show_alert: bool = False) -> None:
    try:
        await cb.answer(text, show_alert=show_alert)
    except Exception:
        pass


def build_schematic(mods: list[dict[str, Any]]) -> str:
    """پیش‌نمایش متنی ترتیب و عرض ماژول‌های فعال."""
    active = [m for m in mods if m.get("enabled")]
    if not active:
        return "[ هیچ ماژولی فعال نیست ]"
    rows: list[str] = []
    i = 0
    while i < len(active):
        m = active[i]
        short = m["title_fa"].split("(")[0].strip()[:18]
        if m.get("span") == "half" and m.get("can_half", False):
            if i + 1 < len(active) and active[i + 1].get("span") == "half" and active[i + 1].get("can_half", False):
                s2 = active[i + 1]["title_fa"].split("(")[0].strip()[:18]
                rows.append(f"[ ½ {short} ] [ ½ {s2} ]")
                i += 2
                continue
            rows.append(f"[ ½ {short} (تمام‌عرض خودکار) ]")
        else:
            rows.append(f"[  ۱  {short}  ]")
        i += 1
    return "\n".join(rows)


def _item_label(card_kind: str, it: dict[str, Any]) -> str:
    if card_kind == "players_rating":
        h = (it.get("home") or {}).get("name", "")
        a = (it.get("away") or {}).get("name", "")
        ago_s = it.get("finished_elapsed_sec")
        ago_txt = f" • {max(1, int(ago_s) // 3600)}س قبل" if ago_s is not None and int(ago_s) >= 3600 else (f" • {max(1, int(ago_s) // 60)}د قبل" if ago_s is not None else "")
        return f"{h} {it.get('homeGoals', 0)}-{it.get('awayGoals', 0)} {a} ({it.get('competition', '')}){ago_txt}"
    if card_kind == "standings":
        return f"{it.get('name', '')} — {it.get('round', '')}"
    if card_kind == "injury_lab":
        pl = it.get("player") or {}
        inj = it.get("injury") or {}
        return f"{pl.get('name', '')} ({pl.get('club', '')}) • {inj.get('eta', '')}"
    if card_kind == "h2h_teams":
        h = (it.get("home") or {}).get("name", "")
        a = (it.get("away") or {}).get("name", "")
        return f"{h} مقابل {a} ({it.get('competition', '')})"
    if card_kind == "player_fc27":
        return f"{it.get('name', '')} ({it.get('club', '')}) • OVR {it.get('ovr', '')}"
    if card_kind == "h2h_players":
        p1 = (it.get("p1") or {}).get("name", "")
        p2 = (it.get("p2") or {}).get("name", "")
        return f"{p1} 🆚 {p2} ({it.get('competition', '')})"
    if card_kind == "top_scorers":
        return f"{it.get('competition', '')} — {it.get('round', '')}"
    if card_kind == "matchday_results":
        cnt = len(it.get("matches") or [])
        return f"{it.get('competition', '')} ({cnt} بازی)"
    if card_kind == "quote":
        sp = str(it.get("speaker") or "نقل‌قول")
        fit = it.get("fit_score")
        fit_s = f" • امتیاز {fit}" if fit else ""
        q_short = str(it.get("quote") or "").replace("*", "")[:36]
        return f"{sp}: «{q_short}…»{fit_s}"
    if card_kind == "debate":
        a = (it.get("sideA") or {}).get("name", "")
        b = (it.get("sideB") or {}).get("name", "")
        ht = it.get("heat")
        ht_s = f" • {ht}°" if ht else ""
        return f"{a} × {b} ({it.get('category', '')}){ht_s}"
    if card_kind == "number_of_day":
        num = f"{it.get('number', '')}{it.get('suffix', '')}"
        return f"[{num}] {it.get('subject', '')} — {it.get('unit', '')}"
    if card_kind == "matchweek_wrapup":
        return f"{it.get('competition', '')} — {it.get('round', 'خلاصه هفته')}"
    if card_kind == "shotmap_xg":
        h, a = it.get("home") or {}, it.get("away") or {}
        return f"{h.get('name', '')} {h.get('score', 0)}-{a.get('score', 0)} {a.get('name', '')} ({it.get('competition', '')})"
    if card_kind == "value_radar":
        return f"{it.get('title', 'رادار ارزش بازار')} ({it.get('competition', '')})"
    if card_kind == "lineup_injuries":
        h, a = it.get("home") or {}, it.get("away") or {}
        return f"{h.get('name', '')} × {a.get('name', '')} ({it.get('round', 'پیش‌رو')})"
    return f"{it.get('name', '')} ({it.get('club', '')}) • XG {it.get('ovr', '')}"


def _get_slides_and_modules(card_kind: str, item: dict[str, Any], slide: str) -> tuple[list[tuple], list[dict[str, Any]], list[str]]:
    preview_it = dict(item)
    if card_kind == "players_rating":
        from src.xgpedia.render.card_kit.players_rating_card import RATINGS_SLIDES, get_players_rating_modules
        if not preview_it.get("verdict"):
            preview_it["verdict"] = {"title": "تحلیل", "body": "(در مرحله ساخت تکمیل می‌شود)", "tag": "XGPedia"}
        mods, miss = get_players_rating_modules(preview_it, slide)
        return RATINGS_SLIDES, mods, miss
    if card_kind == "standings":
        from src.xgpedia.render.card_kit.standings_card import STANDINGS_SLIDES, get_standings_modules
        mods, miss = get_standings_modules(preview_it, slide)
        return STANDINGS_SLIDES, mods, miss
    if card_kind == "injury_lab":
        from src.xgpedia.render.card_kit.injury_card import INJURY_SLIDES, get_injury_modules
        if not preview_it.get("verdict"):
            preview_it["verdict"] = {"title": "تحلیل", "body": "(در مرحله ساخت تکمیل می‌شود)", "tag": "XGPedia"}
        mods, miss = get_injury_modules(preview_it, slide)
        return INJURY_SLIDES, mods, miss
    if card_kind == "h2h_teams":
        from src.xgpedia.render.card_kit.h2h_teams_card import H2H_TEAMS_SLIDES, get_h2h_teams_modules
        mods, miss = get_h2h_teams_modules(preview_it, slide)
        return H2H_TEAMS_SLIDES, mods, miss
    if card_kind == "player_fc27":
        from src.xgpedia.render.card_kit.player_fc27_card import FC27_SLIDES, get_player_fc27_modules
        mods, miss = get_player_fc27_modules(preview_it, slide)
        return FC27_SLIDES, mods, miss
    if card_kind == "h2h_players":
        from src.xgpedia.render.card_kit.h2h_players_card import H2H_PLAYERS_SLIDES, get_h2h_players_modules
        mods, miss = get_h2h_players_modules(preview_it, slide)
        return H2H_PLAYERS_SLIDES, mods, miss
    if card_kind == "top_scorers":
        from src.xgpedia.render.card_kit.top_scorers_card import TOP_SCORERS_SLIDES, get_top_scorers_modules
        mods, miss = get_top_scorers_modules(preview_it, slide)
        return TOP_SCORERS_SLIDES, mods, miss
    if card_kind == "matchday_results":
        from src.xgpedia.render.card_kit.matchday_results_card import MATCHDAY_RESULTS_SLIDES, get_matchday_results_modules
        mods, miss = get_matchday_results_modules(preview_it, slide)
        return MATCHDAY_RESULTS_SLIDES, mods, miss
    if card_kind == "quote":
        from src.xgpedia.render.card_kit.quote_card import QUOTE_SLIDES, get_quote_modules
        mods, miss = get_quote_modules(preview_it, slide)
        return QUOTE_SLIDES, mods, miss
    if card_kind == "debate":
        from src.xgpedia.render.card_kit.debate_card import DEBATE_SLIDES, get_debate_modules
        mods, miss = get_debate_modules(preview_it, slide)
        return DEBATE_SLIDES, mods, miss
    if card_kind == "number_of_day":
        from src.xgpedia.render.card_kit.number_of_day_card import NOD_SLIDES, get_number_of_day_modules
        mods, miss = get_number_of_day_modules(preview_it, slide)
        return NOD_SLIDES, mods, miss
    if card_kind == "matchweek_wrapup":
        from src.xgpedia.render.card_kit.matchweek_wrapup_card import WRAPUP_SLIDES, get_matchweek_wrapup_modules
        mods, miss = get_matchweek_wrapup_modules(preview_it, slide)
        return [(sid, lbl, "full") for sid, lbl, _, _ in WRAPUP_SLIDES], mods, miss
    if card_kind == "shotmap_xg":
        from src.xgpedia.render.card_kit.shotmap_xg_card import SHOTMAP_SLIDES, get_shotmap_xg_modules
        mods, miss = get_shotmap_xg_modules(preview_it, slide)
        return [(sid, lbl, "full") for sid, lbl, _, _ in SHOTMAP_SLIDES], mods, miss
    if card_kind == "value_radar":
        from src.xgpedia.render.card_kit.value_radar_card import VALUE_RADAR_SLIDES, get_value_radar_modules
        mods, miss = get_value_radar_modules(preview_it, slide)
        return VALUE_RADAR_SLIDES, mods, miss
    if card_kind == "lineup_injuries":
        from src.xgpedia.render.card_kit.lineup_injuries_card import LINEUP_SLIDES, get_lineup_injuries_modules
        mods, miss = get_lineup_injuries_modules(preview_it, slide)
        return LINEUP_SLIDES, mods, miss
    from src.xgpedia.render.card_kit.player_card import PLAYER_SLIDES, get_player_modules
    if not preview_it.get("scout"):
        preview_it["scout"] = {"title": "گزارش دیده‌بان", "body": "(در مرحله ساخت تکمیل می‌شود)", "strengths": [], "watchout": "", "tag": "XGPedia"}
    mods, miss = get_player_modules(preview_it, slide)
    return PLAYER_SLIDES, mods, miss


def _fetch_provider_data(card_kind: str, *, include_live: bool = True, force_refresh: bool = False) -> dict[str, list[dict[str, Any]]]:
    if card_kind == "players_rating":
        from src.xgpedia.providers.players_rating_free import list_players_rating_items
        return list_players_rating_items(include_live=include_live, force_refresh=force_refresh)
    if card_kind == "standings":
        from src.xgpedia.providers.standings_free import list_standings_leagues
        return list_standings_leagues(include_live=include_live, force_refresh=force_refresh)
    if card_kind == "injury_lab":
        from src.xgpedia.providers.injury_free import list_injury_items
        return list_injury_items(include_live=include_live, force_refresh=force_refresh)
    if card_kind == "h2h_teams":
        from src.xgpedia.providers.h2h_teams_free import fetch_live_h2h_teams_items, load_h2h_teams_presets
        return {"live": fetch_live_h2h_teams_items(force_refresh=force_refresh) if include_live else [], "presets": load_h2h_teams_presets()}
    if card_kind == "player_fc27":
        from src.xgpedia.providers.player_fc27_free import fetch_live_player_fc27_items, load_player_fc27_presets
        return {"live": fetch_live_player_fc27_items(force_refresh=force_refresh) if include_live else [], "presets": load_player_fc27_presets()}
    if card_kind == "h2h_players":
        from src.xgpedia.providers.h2h_players_free import fetch_live_h2h_players_items, load_h2h_players_presets
        return {"live": fetch_live_h2h_players_items(force_refresh=force_refresh) if include_live else [], "presets": load_h2h_players_presets()}
    if card_kind == "top_scorers":
        from src.xgpedia.providers.top_scorers_free import fetch_live_top_scorers_items, load_top_scorers_presets
        return {"live": fetch_live_top_scorers_items(force_refresh=force_refresh) if include_live else [], "presets": load_top_scorers_presets()}
    if card_kind == "matchday_results":
        from src.xgpedia.providers.matchday_results_free import fetch_live_matchday_results_items, load_matchday_results_presets
        return {"live": fetch_live_matchday_results_items(force_refresh=force_refresh) if include_live else [], "presets": load_matchday_results_presets()}
    if card_kind == "quote":
        from src.xgpedia.providers.quote_free import fetch_live_quote_items, load_quote_presets
        return {"live": fetch_live_quote_items(force_refresh=force_refresh) if include_live else [], "presets": load_quote_presets()}
    if card_kind == "debate":
        from src.xgpedia.providers.debate_free import fetch_live_debate_items, load_debate_presets
        return {"live": fetch_live_debate_items(force_refresh=force_refresh) if include_live else [], "presets": load_debate_presets()}
    if card_kind == "number_of_day":
        from src.xgpedia.providers.number_of_day_free import fetch_live_number_of_day_items, load_number_of_day_presets
        return {"live": fetch_live_number_of_day_items(force_refresh=force_refresh) if include_live else [], "presets": load_number_of_day_presets()}
    if card_kind == "matchweek_wrapup":
        from src.xgpedia.providers.matchweek_wrapup_free import fetch_live_matchweek_wrapup_items, load_matchweek_wrapup_presets
        return {"live": fetch_live_matchweek_wrapup_items(force_refresh=force_refresh) if include_live else [], "presets": load_matchweek_wrapup_presets()}
    if card_kind == "shotmap_xg":
        from src.xgpedia.providers.shotmap_xg_free import fetch_live_shotmap_xg_items, load_shotmap_xg_presets
        return {"live": fetch_live_shotmap_xg_items(force_refresh=force_refresh) if include_live else [], "presets": load_shotmap_xg_presets()}
    if card_kind == "value_radar":
        from src.xgpedia.providers.value_radar_free import fetch_live_value_radar_items, load_value_radar_presets
        return {"live": fetch_live_value_radar_items(force_refresh=force_refresh) if include_live else [], "presets": load_value_radar_presets()}
    if card_kind == "lineup_injuries":
        from src.xgpedia.providers.lineup_injuries_free import fetch_live_lineup_injuries_items, load_lineup_injuries_presets
        return {"live": fetch_live_lineup_injuries_items(force_refresh=force_refresh) if include_live else [], "presets": load_lineup_injuries_presets()}
    from src.xgpedia.providers.player_profile_free import list_player_profile_items
    return list_player_profile_items(include_live=include_live, force_refresh=force_refresh)


def _resolve_reel_pipeline(card_kind: str):
    """بازگرداندن (slides, render_fn, hydrate_fn) برای تبدیل هر کارت اسلایدی به ریلز ویدیویی ۹:۱۶."""
    if card_kind == "matchweek_wrapup":
        from src.xgpedia.render.card_kit.matchweek_wrapup_card import WRAPUP_SLIDES, render_matchweek_wrapup_html
        return [s[0] for s in WRAPUP_SLIDES], render_matchweek_wrapup_html, None
    if card_kind == "shotmap_xg":
        from src.xgpedia.providers.shotmap_xg_free import hydrate_shotmap_xg_item
        from src.xgpedia.render.card_kit.shotmap_xg_card import SHOTMAP_SLIDES, render_shotmap_xg_html
        return [s[0] for s in SHOTMAP_SLIDES], render_shotmap_xg_html, hydrate_shotmap_xg_item
    if card_kind == "value_radar":
        from src.xgpedia.providers.value_radar_free import hydrate_value_radar_item
        from src.xgpedia.render.card_kit.value_radar_card import VALUE_RADAR_SLIDES, render_value_radar_html
        return [s[0] for s in VALUE_RADAR_SLIDES], render_value_radar_html, hydrate_value_radar_item
    if card_kind == "lineup_injuries":
        from src.xgpedia.providers.lineup_injuries_free import hydrate_lineup_injuries_item
        from src.xgpedia.render.card_kit.lineup_injuries_card import LINEUP_SLIDES, render_lineup_injuries_html
        return [s[0] for s in LINEUP_SLIDES], render_lineup_injuries_html, hydrate_lineup_injuries_item
    if card_kind == "quote":
        from src.xgpedia.providers.quote_free import hydrate_quote_item
        from src.xgpedia.render.card_kit.quote_card import QUOTE_SLIDES, render_quote_html
        return [s[0] for s in QUOTE_SLIDES[:3]], render_quote_html, hydrate_quote_item
    if card_kind == "debate":
        from src.xgpedia.providers.debate_free import hydrate_debate_item
        from src.xgpedia.render.card_kit.debate_card import DEBATE_SLIDES, render_debate_html
        return [s[0] for s in DEBATE_SLIDES[:4]], render_debate_html, hydrate_debate_item
    if card_kind == "number_of_day":
        from src.xgpedia.providers.number_of_day_free import hydrate_number_of_day_item
        from src.xgpedia.render.card_kit.number_of_day_card import NOD_SLIDES, render_number_of_day_html
        return [s[0] for s in NOD_SLIDES[:3]], render_number_of_day_html, hydrate_number_of_day_item
    if card_kind == "standings":
        from src.xgpedia.render.card_kit.standings_card import STANDINGS_SLIDES, render_standings_html
        return [s[0] for s in STANDINGS_SLIDES[:4]], render_standings_html, None
    if card_kind == "top_scorers":
        from src.xgpedia.render.card_kit.top_scorers_card import TOP_SCORERS_SLIDES, render_top_scorers_html
        return [s[0] for s in TOP_SCORERS_SLIDES[:4]], render_top_scorers_html, None
    if card_kind == "matchday_results":
        from src.xgpedia.render.card_kit.matchday_results_card import RESULTS_SLIDES, render_matchday_results_html
        return [s[0] for s in RESULTS_SLIDES[:4]], render_matchday_results_html, None
    if card_kind == "h2h_teams":
        from src.xgpedia.render.card_kit.h2h_teams_card import H2H_TEAMS_SLIDES, render_h2h_teams_html
        return [s[0] for s in H2H_TEAMS_SLIDES[:4]], render_h2h_teams_html, None
    return None, None, None
