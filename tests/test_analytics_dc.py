"""آزمون‌های مدل Dixon-Coles و قواعد رنگ تیم — مشتق قطعی از fact، بدون دادهٔ خارجی.

اجرا:  python -m pytest tests/test_analytics_dc.py -v
"""
from __future__ import annotations

import pytest

from src.xgpedia.analytics.metrics import dixon_coles_matrix, expected_points
from src.xgpedia.config import load_team_identities
from src.xgpedia.render.cards import _select_modules, display_colors


# ─── ماتریس Dixon-Coles ───

def test_dc_matrix_sums_to_one():
    dc = dixon_coles_matrix(1.53, 1.4)
    # ۱X۲ نرمال‌شده روی مجموع ماتریس است — همیشه دقیقاً ۱
    assert dc["pH"] + dc["pD"] + dc["pA"] == pytest.approx(1.0, abs=1e-6)
    # سلول‌های خام مثل استودیو با تعدیل tau جابه‌جا می‌شوند — انحراف ناچیز از ۱
    flat = sum(sum(row) for row in dc["matrix"])
    assert flat == pytest.approx(1.0, abs=0.01)


def test_dc_matrix_shape_and_cells():
    dc = dixon_coles_matrix(1.53, 1.4)
    assert len(dc["matrix"]) == 7 and all(len(row) == 7 for row in dc["matrix"])
    assert dc["matrix"][0][0] > 0.04  # پرتکرارترین نتیجهٔ لیگ معمولاً نزدیک ۱-۱/۰-۰ است


def test_dc_home_advantage_through_larger_lambda():
    """xG بزرگ‌تر → احتمال برد بیشتر؛ تقارن ورودی → تقارن خروجی."""
    dc = dixon_coles_matrix(2.0, 1.0)
    assert dc["pH"] > dc["pA"]
    sym = dixon_coles_matrix(1.5, 1.5)
    assert sym["pH"] == pytest.approx(sym["pA"], abs=1e-9)


def test_dc_o25_and_btts_monotone_in_lambda():
    low = dixon_coles_matrix(0.8, 0.7)
    high = dixon_coles_matrix(2.2, 2.0)
    assert high["pO25"] > low["pO25"]
    assert high["pBTTS"] > low["pBTTS"]


def test_expected_points_formula():
    # 100% برد → 3 امتیاز؛ 50/25/25 → میزبان 1.75، میهمان 1.0
    assert expected_points(1.0, 0.0, 0.0) == (3.0, 0.0)
    h, a = expected_points(0.5, 0.25, 0.25)
    assert h == pytest.approx(1.75)
    assert a == pytest.approx(1.0)


# ─── انتخاب رنگ نمایشی دو تیم ───

def _idents():
    return load_team_identities()["teams"]


def test_display_colors_distinct_primaries_pass_through():
    t = _idents()
    # آرسنال قرمز در برابر چلسی آبی — فاصلهٔ کافی؛ هر دو رنگ اصلی رسمی می‌مانند
    hc, ac = display_colors(t["Arsenal"], t["Chelsea"], "#38BDF8")
    assert hc == "#EF0107"
    assert ac == "#034694"


def test_display_colors_close_reds_get_secondary():
    t = _idents()
    # آرسنال × لیورپول — دو قرمز نزدیک؛ میهمان به رنگ ثانویه (طلایی) می‌رود
    hc, ac = display_colors(t["Arsenal"], t["Liverpool"], "#38BDF8")
    assert hc == "#EF0107"
    assert ac == "#F6EB61"


def test_display_colors_white_vs_white_gets_secondary():
    t = _idents()
    # فولام × لیدز — هر دو سفید؛ میهمان به رنگ ثانویهٔ خودش (آبی لیدز) می‌رود
    hc, ac = display_colors(t["Fulham"], t["Leeds United"], "#38BDF8")
    assert hc == "#FFFFFF"
    assert ac == "#1D428A"


def test_display_colors_missing_identity_uses_fallback():
    hc, ac = display_colors(None, None, "#38BDF8")
    assert hc == "#38BDF8" and ac == "#38BDF8"


# ─── انتخاب ماژول‌ها (موتور اولویت‌بندی استودیو — D31) ───

def test_smart_selects_only_available_modules():
    has = {"stats": True, "trend10": True, "signals": True, "radar": False, "poisson": True}
    # طبق قالب پیش‌فرض قفل‌شده (D43): radar (ناموجود) -> trend10 -> signals
    mods = _select_modules("smart", has, fmt="4:5")
    assert [m["id"] for m in mods] == ["trend10", "signals"]
    assert all(m["enabled"] for m in mods)
    mods9 = _select_modules("smart", has, fmt="9:16")
    assert [m["id"] for m in mods9] == ["trend10", "signals"]


def test_v2_includes_poisson_and_wave_only_with_data():
    has = {"stats": True, "poisson": True, "wave": False, "signals": True}
    mods = _select_modules("v2", has)
    enabled = [m["id"] for m in mods if m["enabled"]]
    assert "poisson" in enabled and "wave" not in enabled


def test_unknown_layout_falls_back_to_v1():
    mods = _select_modules("nope", {"stats": True, "radar": True, "keyduel": True})
    assert [m["id"] for m in mods] == ["radar", "keyduel"]
