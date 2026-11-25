"""تست‌های نسخه v0.40.1 — محور X شکسته (Broken Axis)، ۴ گوشه قرمز یکپارچه، فونت درشت و رفع باگ نام باشگاه."""
from __future__ import annotations

from src.xgpedia.providers.lineup_injuries_free import _team_fa
from src.xgpedia.providers.value_radar_free import _team_fa_name
from src.xgpedia.render.card_kit.lineup_injuries_card import render_lineup_injuries_html
from src.xgpedia.render.card_kit.value_radar_card import render_value_radar_html
from src.xgpedia.providers.lineup_injuries_free import load_lineup_injuries_presets
from src.xgpedia.providers.value_radar_free import load_value_radar_presets


def test_team_fa_returns_persian_club_name_not_hex_color() -> None:
    """lookup_pl_club[0] نام فارسی باشگاه است و نباید کد رنگ hex برگردد."""
    nm1 = _team_fa_name("CRY", "Crystal Palace")
    nm2 = _team_fa("ARS", "Arsenal")
    assert not nm1.startswith("#"), f"Got hex instead of club name: {nm1}"
    assert not nm2.startswith("#"), f"Got hex instead of club name: {nm2}"
    assert "آرسنال" in nm2


def test_value_radar_broken_x_axis_and_four_red_corners() -> None:
    presets = load_value_radar_presets()
    it = dict(presets[0])
    # شبیه‌سازی شکاف بزرگ قیمت (۵-۷ میلیون در برابر ۱۵ میلیون هالند)
    it["players"] = [
        {"name": "نکتیاه", "club": "کریستال پالاس", "club_code": "CRY", "price": 5.4, "xgi90": 0.84, "ev_score": 15.6, "color": "#3B82F6"},
        {"name": "تیرنو بری", "club": "اورتون", "club_code": "EVE", "price": 5.7, "xgi90": 0.77, "ev_score": 13.5, "color": "#38BDF8"},
        {"name": "ایسیدور", "club": "ساندرلند", "club_code": "SUN", "price": 5.4, "xgi90": 0.62, "ev_score": 11.5, "color": "#E62E45"},
        {"name": "اوانیلسون", "club": "بورنموث", "club_code": "BOU", "price": 6.4, "xgi90": 0.66, "ev_score": 10.3, "color": "#DA291C"},
        {"name": "ارلینگ هالند", "club": "منچسترسیتی", "club_code": "MCI", "price": 15.0, "xgi90": 0.90, "ev_score": 6.0, "color": "#6CABDD"},
    ]
    html = render_value_radar_html(it, slide="slide1", fmt="4:5")
    # ۱) ۴ گوشه قرمز رسمی XGPedia
    for cls in ("c-tl", "c-tr", "c-bl", "c-br"):
        assert cls in html
    # ۲) محور X شکسته با علامت // و جهت LTR روی SVG برای عدم بریدگی متن
    assert "⋯ // ⋯" in html
    assert "فاصله قیمت" in html
    assert 'direction="ltr"' in html


def test_lineup_injuries_also_has_four_red_corners() -> None:
    it = load_lineup_injuries_presets()[0]
    html = render_lineup_injuries_html(it, slide="slide1", fmt="4:5")
    for cls in ("c-tl", "c-tr", "c-bl", "c-br"):
        assert cls in html
