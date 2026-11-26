"""تست‌های نسخهٔ 0.65.0: موازی‌سازی همگام‌سازی بازی‌های امروز، حذف تماس‌های تکراری FDO و رفع خطای کاذب TimeoutError در بات."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from src.xgpedia import today_workflow as tw


def test_telegram_bot_uses_heartbeat_wrapper_without_90s_timeout() -> None:
    src = Path("src/xgpedia/publishers/telegram_bot.py").read_text(encoding="utf-8")
    assert "async def _run_sync_with_heartbeat(" in src
    assert src.count("_run_sync_with_heartbeat(") >= 3
    assert src.count("tw.sync_today_matches") == 1
    assert "timeout_sec=240.0" in src


def test_today_workflow_parallelizes_csv_downloads_and_skips_fdo_for_el() -> None:
    src = Path("src/xgpedia/today_workflow.py").read_text(encoding="utf-8")
    assert "ThreadPoolExecutor(max_workers=6)" in src
    assert 'if lg.code == "EL":' in src
    # نباید scorers در _default_sync_fixtures دوباره فراخوانی شود
    fix_idx = src.index("def _default_sync_fixtures()")
    odds_idx = src.index("def _default_sync_odds()")
    assert "api.scorers(" not in src[fix_idx:odds_idx]
