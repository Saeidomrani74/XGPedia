"""تست‌های نسخه v0.46.0 — پشتیبانی کامل لالیگا اسپانیا (La Liga Glossary، رنگ‌ها، ورزشگاه‌ها، لوگوها و دیتای زنده)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from src.xgpedia.providers.laliga_live_free import build_laliga_matchweek_wrapup
from src.xgpedia.providers.pl_badges_free import get_pl_badge_data_uri, lookup_pl_club


def test_laliga_all_20_clubs_symmetric_in_all_four_configs_and_crests() -> None:
    gl = json.loads(Path("config/glossary_fa.json").read_text(encoding="utf-8"))
    ti = json.loads(Path("config/team_identities.json").read_text(encoding="utf-8"))
    tm = json.loads(Path("config/team_mapping.json").read_text(encoding="utf-8"))
    tv = json.loads(Path("config/team_venues.json").read_text(encoding="utf-8"))

    g_codes = {t["id"] for t in gl["teams"]}
    i_codes = {t["code"] for t in ti["teams"].values()}
    assert g_codes == i_codes, "Glossary and team_identities must remain 1:1 symmetric"

    for code, name_en, name_fa in (
        ("RMA", "Real Madrid", "رئال مادرید"),
        ("BAR", "Barcelona", "بارسلونا"),
        ("ATM", "Atletico Madrid", "اتلتیکو مادرید"),
        ("RSO", "Real Sociedad", "رئال سوسیداد"),
        ("BET", "Real Betis", "رئال بتیس"),
        ("SEV", "Sevilla", "سویا"),
        ("VAL", "Valencia", "والنسیا"),
        ("OSA", "Osasuna", "اوساسونا"),
        ("CVG", "Celta Vigo", "سلتاویگو"),
        ("RAY", "Rayo Vallecano", "رایو وایکانو"),
        ("MLL", "Mallorca", "مایورکا"),
        ("GET", "Getafe", "ختافه"),
        ("ALA", "Alaves", "آلاوس"),
        ("ESP", "Espanyol", "اسپانیول"),
        ("LPA", "Las Palmas", "لاس‌پالماس"),
        ("VLD", "Real Valladolid", "وایادولید"),
        ("LEG", "Leganes", "لگانس"),
    ):
        assert code in g_codes
        assert name_en in ti["teams"]
        assert name_en in tm["teams"]
        assert tm["teams"][name_en]["name_fa"] == name_fa
        assert name_en in tv["teams"]
        assert (Path("brand/crests") / f"{code}.svg").exists()


def test_pl_badges_bridge_resolves_laliga_clubs_and_offline_crests() -> None:
    for en, expected_fa, expected_tla in (
        ("Sevilla", "سویا", "SEV"),
        ("Real Betis", "رئال بتیس", "BET"),
        ("Real Sociedad", "رئال سوسیداد", "RSO"),
        ("Valencia", "والنسیا", "VAL"),
        ("Celta Vigo", "سلتاویگو", "CVG"),
    ):
        info = lookup_pl_club(en)
        assert info is not None
        assert info[0] == expected_fa
        assert info[1] == expected_tla
        uri = get_pl_badge_data_uri(en, fetch_network=False)
        assert uri is not None and uri.startswith("data:image/")


def test_laliga_live_matchweek_wrapup_builder() -> None:
    fake_rows = [
        {"rank": 1, "name": "بارسلونا", "name_en": "Barcelona", "code": "BAR", "color": "#A50044", "played": 14, "won": 11, "drawn": 1, "lost": 2, "gf": 42, "ga": 14, "gd": 28, "points": 34},
        {"rank": 2, "name": "رئال مادرید", "name_en": "Real Madrid", "code": "RMA", "color": "#F59E0B", "played": 13, "won": 9, "drawn": 3, "lost": 1, "gf": 28, "ga": 11, "gd": 17, "points": 30},
        {"rank": 3, "name": "اتلتیکو مادرید", "name_en": "Atletico Madrid", "code": "ATM", "color": "#CB3524", "played": 14, "won": 8, "drawn": 5, "lost": 1, "gf": 21, "ga": 8, "gd": 13, "points": 29},
        {"rank": 4, "name": "ویارئال", "name_en": "Villarreal", "code": "VIL", "color": "#F5E216", "played": 13, "won": 7, "drawn": 4, "lost": 2, "gf": 25, "ga": 21, "gd": 4, "points": 25},
        {"rank": 5, "name": "اتلتیک بیلبائو", "name_en": "Athletic Club", "code": "ATH", "color": "#EE2523", "played": 14, "won": 6, "drawn": 5, "lost": 3, "gf": 20, "ga": 13, "gd": 7, "points": 23},
        {"rank": 6, "name": "رئال بتیس", "name_en": "Real Betis", "code": "BET", "color": "#0BB363", "played": 14, "won": 5, "drawn": 5, "lost": 4, "gf": 16, "ga": 16, "gd": 0, "points": 20},
    ]
    with patch("src.xgpedia.providers.laliga_live_free.fetch_laliga_standings", return_value=fake_rows):
        mw = build_laliga_matchweek_wrapup()
    assert mw is not None
    assert mw["competition"] == "لالیگا اسپانیا"
    assert mw["bestAttack"]["team"] == "بارسلونا"
    assert mw["bestDefense"]["team"] == "اتلتیکو مادرید"
