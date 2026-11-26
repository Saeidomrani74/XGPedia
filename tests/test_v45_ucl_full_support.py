"""تست‌های نسخه v0.45.0 — پشتیبانی کامل لیگ قهرمانان اروپا (UCL Glossary، رنگ‌ها، لوگوها، ورزشگاه‌ها و دیتای زنده)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from src.xgpedia.providers.pl_badges_free import get_pl_badge_data_uri, lookup_pl_club
from src.xgpedia.providers.ucl_badges_free import get_ucl_badge_data_uri, lookup_ucl_club
from src.xgpedia.providers.ucl_live_free import build_ucl_matchweek_wrapup


def test_ucl_glossary_identities_mapping_and_venues_symmetry() -> None:
    """تمام ۳۵ باشگاه چمپیونزلیگ باید به‌صورت یکپارچه در هر ۴ فایل config و brand/crests حضور داشته باشند."""
    gl = json.loads(Path("config/glossary_fa.json").read_text(encoding="utf-8"))
    ti = json.loads(Path("config/team_identities.json").read_text(encoding="utf-8"))
    tm = json.loads(Path("config/team_mapping.json").read_text(encoding="utf-8"))
    tv = json.loads(Path("config/team_venues.json").read_text(encoding="utf-8"))

    g_codes = {t["id"] for t in gl["teams"]}
    i_codes = {t["code"] for t in ti["teams"].values()}
    assert g_codes == i_codes, "Glossary and team_identities team codes must stay 1:1 symmetric"

    for code, name_en, name_fa in (
        ("RMA", "Real Madrid", "رئال مادرید"),
        ("BAR", "Barcelona", "بارسلونا"),
        ("BAY", "Bayern Munich", "بایرن مونیخ"),
        ("PSG", "Paris Saint-Germain", "پاریس سن‌ژرمن"),
        ("INT", "Inter Milan", "اینتر میلان"),
        ("BVB", "Borussia Dortmund", "بوروسیا دورتموند"),
    ):
        assert code in g_codes
        assert name_en in ti["teams"]
        assert name_en in tm["teams"]
        assert tm["teams"][name_en]["name_fa"] == name_fa
        assert name_en in tv["teams"]
        assert (Path("brand/crests") / f"{code}.svg").exists()


def test_pl_badges_bridge_transparently_resolves_ucl_clubs_and_offline_crests() -> None:
    """تمام کارت‌های فعلی که lookup_pl_club / get_pl_badge_data_uri را صدا می‌زنند، باید باشگاه‌های UCL را هم بشناسند."""
    info = lookup_pl_club("Real Madrid")
    assert info is not None
    assert info[0] == "رئال مادرید"
    assert info[1] == "RMA"

    uri = get_pl_badge_data_uri("Bayern Munich", fetch_network=False)
    assert uri is not None
    assert uri.startswith("data:image/")

    uri2 = get_ucl_badge_data_uri("PSG", fetch_network=False)
    assert uri2 is not None
    assert uri2.startswith("data:image/")


def test_ucl_live_matchweek_wrapup_builder() -> None:
    fake_rows = [
        {"rank": 1, "name": "لیورپول", "name_en": "Liverpool", "code": "LIV", "color": "#C8102E", "played": 5, "won": 5, "drawn": 0, "lost": 0, "gf": 14, "ga": 2, "gd": 12, "points": 15},
        {"rank": 2, "name": "اینتر میلان", "name_en": "Inter Milan", "code": "INT", "color": "#010E80", "played": 5, "won": 4, "drawn": 1, "lost": 0, "gf": 9, "ga": 1, "gd": 8, "points": 13},
        {"rank": 3, "name": "بارسلونا", "name_en": "Barcelona", "code": "BAR", "color": "#A50044", "played": 5, "won": 4, "drawn": 0, "lost": 1, "gf": 18, "ga": 5, "gd": 13, "points": 12},
        {"rank": 4, "name": "بایرن مونیخ", "name_en": "Bayern Munich", "code": "BAY", "color": "#DC052D", "played": 5, "won": 3, "drawn": 1, "lost": 1, "gf": 15, "ga": 6, "gd": 9, "points": 10},
        {"rank": 5, "name": "رئال مادرید", "name_en": "Real Madrid", "code": "RMA", "color": "#F59E0B", "played": 5, "won": 3, "drawn": 0, "lost": 2, "gf": 11, "ga": 8, "gd": 3, "points": 9},
        {"rank": 6, "name": "پاریس سن‌ژرمن", "name_en": "Paris Saint-Germain", "code": "PSG", "color": "#004170", "played": 5, "won": 2, "drawn": 2, "lost": 1, "gf": 8, "ga": 6, "gd": 2, "points": 8},
    ]
    with patch("src.xgpedia.providers.ucl_live_free.fetch_ucl_standings", return_value=fake_rows):
        mw = build_ucl_matchweek_wrapup()
    assert mw is not None
    assert mw["competition"] == "لیگ قهرمانان اروپا"
    assert mw["bestAttack"]["team"] == "بارسلونا"
    assert mw["bestDefense"]["team"] == "اینتر میلان"
