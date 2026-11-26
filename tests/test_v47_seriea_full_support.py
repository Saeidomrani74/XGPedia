"""تست‌های نسخه v0.47.0 — پشتیبانی کامل سری آ ایتالیا (Serie A Glossary، رنگ‌ها، ورزشگاه‌ها، لوگوها و دیتای زنده)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from src.xgpedia.providers.pl_badges_free import get_pl_badge_data_uri, lookup_pl_club
from src.xgpedia.providers.seriea_live_free import build_seriea_matchweek_wrapup


def test_seriea_all_20_clubs_symmetric_in_all_four_configs_and_crests() -> None:
    gl = json.loads(Path("config/glossary_fa.json").read_text(encoding="utf-8"))
    ti = json.loads(Path("config/team_identities.json").read_text(encoding="utf-8"))
    tm = json.loads(Path("config/team_mapping.json").read_text(encoding="utf-8"))
    tv = json.loads(Path("config/team_venues.json").read_text(encoding="utf-8"))

    g_codes = {t["id"] for t in gl["teams"]}
    i_codes = {t["code"] for t in ti["teams"].values()}
    assert g_codes == i_codes, "Glossary and team_identities must remain 1:1 symmetric"

    for code, name_en, name_fa in (
        ("INT", "Inter Milan", "اینتر میلان"),
        ("MIL", "AC Milan", "آث میلان"),
        ("JUV", "Juventus", "یوونتوس"),
        ("ATA", "Atalanta", "آتالانتا"),
        ("NAP", "Napoli", "ناپولی"),
        ("LAZ", "Lazio", "لاتزیو"),
        ("FIO", "Fiorentina", "فیورنتینا"),
        ("TOR", "Torino", "تورینو"),
        ("UDI", "Udinese", "اودینزه"),
        ("GEN", "Genoa", "جنوا"),
        ("CAG", "Cagliari", "کالیاری"),
        ("VER", "Hellas Verona", "هلاس ورونا"),
        ("EMP", "Empoli", "امپولی"),
        ("LEC", "Lecce", "لچه"),
        ("PAR", "Parma", "پارما"),
        ("COM", "Como", "کومو"),
        ("MNZ", "Monza", "مونتزا"),
        ("VEN", "Venezia", "ونتزیا"),
    ):
        assert code in g_codes
        assert name_en in ti["teams"]
        assert name_en in tm["teams"]
        assert tm["teams"][name_en]["name_fa"] == name_fa
        assert name_en in tv["teams"]
        assert (Path("brand/crests") / f"{code}.svg").exists()


def test_pl_badges_bridge_resolves_seriea_clubs_and_offline_crests() -> None:
    for en, expected_fa, expected_tla in (
        ("Lazio", "لاتزیو", "LAZ"),
        ("Fiorentina", "فیورنتینا", "FIO"),
        ("Torino", "تورینو", "TOR"),
        ("Parma", "پارما", "PAR"),
        ("Como", "کومو", "COM"),
    ):
        info = lookup_pl_club(en)
        assert info is not None
        assert info[0] == expected_fa
        assert info[1] == expected_tla
        uri = get_pl_badge_data_uri(en, fetch_network=False)
        assert uri is not None and uri.startswith("data:image/")


def test_seriea_live_matchweek_wrapup_builder() -> None:
    fake_rows = [
        {"rank": 1, "name": "ناپولی", "name_en": "Napoli", "code": "NAP", "color": "#12A0D7", "played": 13, "won": 9, "drawn": 2, "lost": 2, "gf": 21, "ga": 9, "gd": 12, "points": 29},
        {"rank": 2, "name": "آتالانتا", "name_en": "Atalanta", "code": "ATA", "color": "#1E71B8", "played": 13, "won": 9, "drawn": 1, "lost": 3, "gf": 34, "ga": 16, "gd": 18, "points": 28},
        {"rank": 3, "name": "اینتر میلان", "name_en": "Inter Milan", "code": "INT", "color": "#010E80", "played": 13, "won": 8, "drawn": 4, "lost": 1, "gf": 31, "ga": 14, "gd": 17, "points": 28},
        {"rank": 4, "name": "فیورنتینا", "name_en": "Fiorentina", "code": "FIO", "color": "#482E92", "played": 13, "won": 8, "drawn": 4, "lost": 1, "gf": 27, "ga": 10, "gd": 17, "points": 28},
        {"rank": 5, "name": "لاتزیو", "name_en": "Lazio", "code": "LAZ", "color": "#87D8F7", "played": 13, "won": 9, "drawn": 1, "lost": 3, "gf": 28, "ga": 14, "gd": 14, "points": 28},
        {"rank": 6, "name": "یوونتوس", "name_en": "Juventus", "code": "JUV", "color": "#E2E8F0", "played": 13, "won": 6, "drawn": 7, "lost": 0, "gf": 21, "ga": 7, "gd": 14, "points": 25},
    ]
    with patch("src.xgpedia.providers.seriea_live_free.fetch_seriea_standings", return_value=fake_rows):
        mw = build_seriea_matchweek_wrapup()
    assert mw is not None
    assert mw["competition"] == "سری آ ایتالیا"
    assert mw["bestAttack"]["team"] == "آتالانتا"
    assert mw["bestDefense"]["team"] == "یوونتوس"
