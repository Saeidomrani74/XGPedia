"""گرم‌کن هوشمند پس‌زمینه (Background Warmer — v0.78.0).

دریافت تدریجی و کم‌فشار داده‌های هیدراتاسیون (Opta پس‌ازبازی، Understat XHR پنج لیگ، FPL Bootstrap)
در پس‌زمینه با رعایت بودجهٔ نرخ (`hydration_cache.can_spend_budget`) تا هنگام کلیک ادمین در ربات،
پاسخ زیر ۱ ثانیه آماده باشد و هیچ‌گاه سقف درخواست APIها پر نشود.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

from src.xgpedia.core import hydration_cache as hc

log = logging.getLogger("xgpedia.warmer")

UNDERSTAT_DOMESTIC_LEAGUES = ("EPL", "La_liga", "Serie_A", "Bundesliga", "Ligue_1")


def is_warmer_enabled() -> bool:
    raw = (os.getenv("XGPEDIA_ENABLE_WARMER", "1") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def warm_hydration_cycle(*, max_post_match: int = 2, max_understat: int = 1) -> dict[str, Any]:
    """یک چرخهٔ کوتاه و کم‌فشار گرم‌کردن کش (مناسب اجرا هر ۱۵ تا ۲۰ دقیقه در پس‌زمینه)."""
    stats: dict[str, Any] = {"post_match_warmed": 0, "understat_warmed": 0, "fpl_warmed": False, "purged": 0}

    # ۱) گرم‌کردن بازی‌های تازه تمام‌شده (بیش از ۱۵ دقیقه از پایان، حداکثر ۲ بازی در هر چرخه)
    if max_post_match > 0 and hc.can_spend_budget("fotmob_post_match"):
        try:
            from src.xgpedia import today_workflow as tw
            recent = tw.list_recent_finished_fixtures(hours=6.0)
            for item in recent:
                if stats["post_match_warmed"] >= max_post_match:
                    break
                if getattr(item, "has_xg", False):
                    continue
                if not hc.can_spend_budget("fotmob_post_match"):
                    break
                hc.record_budget_spend("fotmob_post_match")
                res = tw.enrich_post_match_fixture(item.fixture_id)
                if res and any(res.values()):
                    stats["post_match_warmed"] += 1
        except Exception as exc:
            from src.xgpedia.core.error_metrics import record_error
            record_error("warmer.post_match", exc)

    # ۲) قطره‌چکانی Understat XHR (در هر چرخه حداکثر ۱ لیگ که کش ۱۲ ساعتهٔ آن رو به انقضاست)
    if max_understat > 0 and hc.can_spend_budget("understat_league_xhr"):
        try:
            from src.xgpedia.providers.top_scorers_free import _fetch_understat_league_player_stats
            now = datetime.now(timezone.utc)
            cur_yr = now.year if now.month >= 7 else now.year - 1
            for slug in UNDERSTAT_DOMESTIC_LEAGUES:
                if stats["understat_warmed"] >= max_understat:
                    break
                ck = f"understat_league_xhr:{slug}:{cur_yr}"
                if hc.is_fresh(ck, lead_sec=3600):
                    continue
                if not hc.can_spend_budget("understat_league_xhr"):
                    break
                data = _fetch_understat_league_player_stats(slug, season_years=[cur_yr])
                if data:
                    stats["understat_warmed"] += 1
        except Exception as exc:
            from src.xgpedia.core.error_metrics import record_error
            record_error("warmer.understat", exc)

    # ۳) قطره‌چکانی FPL Bootstrap (اگر کش ۶ ساعته رو به انقضاست)
    if hc.can_spend_budget("fpl_bootstrap") and not hc.is_fresh("fpl_bootstrap:current", lead_sec=1800):
        try:
            from src.xgpedia.providers.fpl_free import fetch_fpl_bootstrap
            boot = fetch_fpl_bootstrap()
            if boot:
                hc.set_cached("fpl_bootstrap:current", "fpl_bootstrap", {"ok": True, "events": len(boot.get("events") or [])})
                stats["fpl_warmed"] = True
        except Exception as exc:
            from src.xgpedia.core.error_metrics import record_error
            record_error("warmer.fpl", exc)

    # ۴) پاک‌سازی ردیف‌های خیلی قدیمی
    stats["purged"] = hc.purge_expired(older_than_sec=14 * 86400)
    return stats


async def background_warmer_loop(interval_sec: float = 900.0) -> None:
    """حلقهٔ آرام پس‌زمینه برای ربات تلگرام (هر ۱۵ دقیقه یک‌بار با تاخیر اولیهٔ ۴۵ ثانیه)."""
    if not is_warmer_enabled():
        log.info("Background warmer disabled (XGPEDIA_ENABLE_WARMER=0)")
        return
    await asyncio.sleep(45.0)
    while True:
        try:
            res = await asyncio.to_thread(warm_hydration_cycle)
            if res["post_match_warmed"] or res["understat_warmed"] or res["fpl_warmed"]:
                log.info("Background warmer cycle completed: %s", res)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Background warmer error: %s", exc)
        await asyncio.sleep(max(120.0, interval_sec))
