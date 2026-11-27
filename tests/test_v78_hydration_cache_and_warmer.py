"""تست‌های نسخه v0.78.0 — کش پایدار SQLite با TTL هوشمند، SWR، بودجهٔ نرخ و گرم‌کن پس‌زمینه."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch


def test_hydration_cache_fresh_stale_swr_and_purge(tmp_path, monkeypatch) -> None:
    """کش SQLite باید hit تازه، SWR روی نیمه‌تازه و پاک‌سازی ردیف‌های قدیمی را دقیق انجام دهد."""
    from src.xgpedia import db as db_mod
    from src.xgpedia.core import hydration_cache as hc

    test_db = tmp_path / "hydration_v78.sqlite"
    monkeypatch.setattr(db_mod, "DATABASE_PATH", test_db)
    db_mod.init_db()
    hc.reset_rate_budgets()

    with db_mod.db() as conn:
        assert db_mod.get_schema_version(conn) >= 5

    # ۱) Cold miss -> fetch & persist
    calls = {"n": 0}
    def _fetcher():
        calls["n"] += 1
        return {"goals": 18, "xg": 15.4}

    v1 = hc.get_or_fetch("understat_league_xhr:EPL:2026", "understat_league_xhr", _fetcher, ttl_sec=3600)
    assert v1 == {"goals": 18, "xg": 15.4}
    assert calls["n"] == 1

    # ۲) Fresh hit -> zero network calls
    v2 = hc.get_or_fetch("understat_league_xhr:EPL:2026", "understat_league_xhr", _fetcher, ttl_sec=3600)
    assert v2 == v1
    assert calls["n"] == 1

    # ۳) Stale hit within grace window -> returns stale immediately
    now_t = time.time()
    hc.set_cached("fpl_element_summary:99", "fpl_element_summary", {"history": [1, 2]}, ttl_sec=10, now=now_t - 20)
    hit, val, is_stale = hc.get_cached("fpl_element_summary:99", allow_stale_sec=60, now=now_t)
    assert hit is True and is_stale is True and val == {"history": [1, 2]}

    # ۴) Purge old expired entries
    hc.set_cached("old:key", "fpl_bootstrap", {"x": 1}, ttl_sec=1, now=now_t - 20 * 86400)
    purged = hc.purge_expired(older_than_sec=14 * 86400, now=now_t)
    assert purged >= 1

    stats = hc.get_cache_stats(now=now_t)
    assert stats["total"] >= 1


def test_hydration_cache_rate_budget_enforces_min_interval() -> None:
    """نگهبان نرخ باید از ارسال پشت‌سرهم درخواست‌ها سریع‌تر از min_interval جلوگیری کند."""
    from src.xgpedia.core import hydration_cache as hc

    hc.reset_rate_budgets()
    t0 = 1_700_000_000.0
    assert hc.can_spend_budget("understat_league_xhr", now=t0) is True
    hc.record_budget_spend("understat_league_xhr", now=t0)
    # ۱ ثانیه بعد (< 4.0s min_interval) باید رد شود
    assert hc.can_spend_budget("understat_league_xhr", now=t0 + 1.0) is False
    # ۵ ثانیه بعد (> 4.0s min_interval) مجاز است
    assert hc.can_spend_budget("understat_league_xhr", now=t0 + 5.0) is True


def test_background_warmer_respects_feature_flag_and_caps(tmp_path, monkeypatch) -> None:
    """گرم‌کن پس‌زمینه باید از فلگ محیطی و سقف آیتم در هر چرخه پیروی کند."""
    from src.xgpedia import db as db_mod
    from src.xgpedia.core import background_warmer as bw
    from src.xgpedia.core import hydration_cache as hc

    monkeypatch.setattr(db_mod, "DATABASE_PATH", tmp_path / "warm.sqlite")
    db_mod.init_db()
    hc.reset_rate_budgets()

    monkeypatch.setenv("XGPEDIA_ENABLE_WARMER", "0")
    assert bw.is_warmer_enabled() is False
    monkeypatch.setenv("XGPEDIA_ENABLE_WARMER", "1")
    assert bw.is_warmer_enabled() is True

    # با لیست خالی و بدون شبکه، چرخه باید بدون کرش و با آمار ۰ تمام شود
    with (
        patch("src.xgpedia.today_workflow.list_recent_finished_fixtures", return_value=[]),
        patch("src.xgpedia.providers.top_scorers_free._fetch_understat_league_player_stats", return_value={"p": {"goals": 5}}),
        patch("src.xgpedia.providers.fpl_free.fetch_fpl_bootstrap", return_value={"events": [1, 2]}),
    ):
        res = bw.warm_hydration_cycle(max_post_match=2, max_understat=1)
        assert res["understat_warmed"] == 1
        assert res["fpl_warmed"] is True
