"""تست‌های نسخه v0.42.0 — موتور یادگیری هوشمند APIها (`APIHealthRouter`)، حذف دکمه جمع کردن کیبورد و بهینه‌سازی ربات."""
from __future__ import annotations

import tempfile
from pathlib import Path

from src.xgpedia.core import api_health


def test_api_health_learns_fastest_healthy_and_skips_cooling() -> None:
    api_health.configure_health_store(persist=False, clear=True)

    # مدل A چند بار ۴۲۹ می‌خورد؛ مدل B سریع و سالم است؛ مدل C کندتر است
    api_health.record_failure("llm:ModelA", "429 Too Many Requests", status_code=429)
    api_health.record_success("llm:ModelB", latency_ms=220.0)
    api_health.record_success("llm:ModelB", latency_ms=240.0)
    api_health.record_success("llm:ModelC", latency_ms=3200.0)

    assert api_health.is_cooling("llm:ModelA") is True
    assert api_health.is_cooling("llm:ModelB") is False
    assert api_health.health_score("llm:ModelB") > api_health.health_score("llm:ModelC") > api_health.health_score("llm:ModelA")

    ranked = api_health.rank_items(["ModelA", "ModelC", "ModelB"], lambda x: f"llm:{x}")
    assert ranked[0] == "ModelB"
    assert ranked[-1] == "ModelA"

    ranked_skip = api_health.rank_items(["ModelA", "ModelC", "ModelB"], lambda x: f"llm:{x}", skip_cooling=True)
    assert "ModelA" not in ranked_skip
    assert ranked_skip == ["ModelB", "ModelC"]

    rep = api_health.format_health_report_fa()
    assert "گزارش یادگیری و سلامت APIها" in rep
    assert "llm:ModelB" in rep


def test_api_health_persists_across_restarts() -> None:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "api_health.json"
        api_health.configure_health_store(path=p, persist=True, clear=True)
        api_health.record_success("feed:BBC", latency_ms=310.0)
        assert p.exists()

        # شبیه‌سازی ری‌استارت کامل
        api_health.configure_health_store(path=p, persist=True, clear=True)
        snap = api_health.get_health_snapshot()
        assert "feed:BBC" in snap
        assert snap["feed:BBC"]["ok"] == 1
    api_health.configure_health_store(persist=False, clear=True)


def test_telegram_bot_removed_hide_keyboard_and_added_api_health() -> None:
    tb_src = Path("src/xgpedia/publishers/telegram_bot.py").read_text(encoding="utf-8")
    assert "جمع کردن کیبورد" not in tb_src
    assert 'callback_data="api:health"' in tb_src
    assert 'callback_data="api:health_reset"' in tb_src
    assert 'Command("health")' in tb_src
