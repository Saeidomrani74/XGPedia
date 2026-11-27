"""تست‌های نسخه v0.71.0:
- حذف SofaScore از مسیر پیش‌فرض fetch_real_match_xg بدون حذف کد آن (فلگ XGPEDIA_ENABLE_SOFASCORE)
- اولویت‌دهی به FotMob → FotMob Playwright → Understat و اجرای SofaScore فقط با XGPEDIA_ENABLE_SOFASCORE=1
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from src.xgpedia.providers import xg_engine as xge


def test_sofascore_is_skipped_by_default_in_fetch_real_match_xg():
    sofa_http = MagicMock(return_value={"home_xg": 1.1, "away_xg": 0.9, "provider": "sofascore"})
    sofa_pw = MagicMock(return_value={"home_xg": 1.1, "away_xg": 0.9, "provider": "sofascore"})
    fotmob_http = MagicMock(return_value=None)
    fotmob_pw = MagicMock(return_value={"home_xg": 2.19, "away_xg": 1.70, "provider": "fotmob"})
    diag: list[str] = []

    with patch.dict(os.environ, {"XGPEDIA_ENABLE_SOFASCORE": ""}, clear=False), patch.object(
        xge, "fetch_sofascore_match_xg", sofa_http
    ), patch.object(xge, "fetch_sofascore_via_playwright", sofa_pw), patch.object(
        xge, "fetch_fotmob_match_xg", fotmob_http
    ), patch.object(xge, "fetch_fotmob_via_playwright", fotmob_pw):
        res = xge.fetch_real_match_xg("Olympiacos", "AC Milan", "2026-11-26", diag=diag)

    assert res is not None
    assert res["provider"] == "fotmob"
    assert res["home_xg"] == 2.19
    assert sofa_http.call_count == 0
    assert sofa_pw.call_count == 0


def test_sofascore_runs_as_last_fallback_when_env_flag_enabled():
    sofa_http = MagicMock(return_value={"home_xg": 1.45, "away_xg": 0.88, "provider": "sofascore"})
    fotmob_http = MagicMock(return_value=None)
    fotmob_pw = MagicMock(return_value=None)

    with patch.dict(os.environ, {"XGPEDIA_ENABLE_SOFASCORE": "1"}, clear=False), patch.object(
        xge, "fetch_sofascore_match_xg", sofa_http
    ), patch.object(xge, "fetch_fotmob_match_xg", fotmob_http), patch.object(
        xge, "fetch_fotmob_via_playwright", fotmob_pw
    ), patch("src.xgpedia.providers.understat.fetch_match_shots_understat", return_value=None):
        res = xge.fetch_real_match_xg("Olympiacos", "AC Milan", "2026-11-26")

    assert res is not None
    assert res["provider"] == "sofascore"
    assert sofa_http.call_count == 1
