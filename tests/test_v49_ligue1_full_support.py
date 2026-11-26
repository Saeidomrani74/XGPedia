"""تست‌های نسخه v0.49.0 — پشتیبانی کامل لیگ ۱ فرانسه (Ligue 1 Glossary، رنگ‌ها، ورزشگاه‌ها، لوگوها و دیتای زنده)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from src.xgpedia.providers.ligue1_live_free import build_ligue1_matchweek_wrapup
from src.xgpedia.providers.pl_badges_free import get_pl_badge_data_uri, lookup_pl_club


def test_ligue1_all_18_clubs_symmetric_in_all_four_configs_and_crests() -> None:
    gl = json.loads(Path("config/glossary_fa.json").read_text(encoding="utf-8"))
    ti = json.loads(Path("config/team_identities.json").read_text(encoding="utf-8"))
    tm = json.loads(Path("config/team_mapping.json").read_text(encoding="utf-8"))
    tv = json.loads(Path("config/team_venues.json").read_text(encoding="utf-8"))

    g_codes = {t["id"] for t in gl["teams"]}
    i_codes = {t["code"] for t in ti["teams"].values()}
    assert g_codes == i_codes, "Glossary and team_identities must remain 1:1 symmetric"

    for code, name_en, name_fa in (
        ("PSG", "Paris Saint-Germain", "پاری‌سن‌ژرمن"),
        ("MON", "AS Monaco", "موناکو"),
        ("LIL", "Lille", "لیل"),
        ("MAR", "Marseille", "مارسی"),
        ("BST", "Brest", "برست"),
        ("LYO", "Lyon", "لیون"),
        ("NIC", "Nice", "نیس"),
        ("LEN", "Lens", "لانس"),
        ("REN", "Rennes", "رن"),
        ("STR", "Strasbourg", "استراسبورگ"),
        ("REI", "Reims", "رمس"),
        ("TOU", "Toulouse", "تولوز"),
        ("AJA", "Auxerre", "اوسر"),
        ("NAN", "Nantes", "نانت"),
        ("ANG", "Angers", "آنژه"),
        ("STE", "Saint-Etienne", "سنت‌اتین"),
        ("HAC", "Le Havre", "لوهاور"),
        ("MTP", "Montpellier", "مون‌پلیه"),
    ):
        assert code in g_codes
        assert name_en in ti["teams"]
        assert name_en in tm["teams"]
        assert tm["teams"][name_en]["name_fa"] == name_fa
        assert name_en in tv["teams"]
        assert (Path("brand/crests") / f"{code}.svg").exists()


def test_pl_badges_bridge_resolves_ligue1_clubs_and_offline_crests() -> None:
    for en, expected_fa, expected_tla in (
        ("Lyon", "لیون", "LYO"),
        ("Nice", "نیس", "NIC"),
        ("Lens", "لانس", "LEN"),
        ("Rennes", "رن", "REN"),
        ("Strasbourg", "استراسبورگ", "STR"),
    ):
        info = lookup_pl_club(en)
        assert info is not None
        assert info[0] == expected_fa
        assert info[1] == expected_tla
        uri = get_pl_badge_data_uri(en, fetch_network=False)
        assert uri is not None and uri.startswith("data:image/")


def test_ligue1_live_matchweek_wrapup_builder() -> None:
    fake_rows = [
        {"rank": 1, "name": "پاری‌سن‌ژرمن", "name_en": "Paris Saint-Germain", "code": "PSG", "color": "#004170", "played": 12, "won": 10, "drawn": 2, "lost": 0, "gf": 36, "ga": 10, "gd": 26, "points": 32},
        {"rank": 2, "name": "موناکو", "name_en": "AS Monaco", "code": "MON", "color": "#E51B22", "played": 12, "won": 8, "drawn": 2, "lost": 2, "gf": 21, "ga": 10, "gd": 11, "points": 26},
        {"rank": 3, "name": "مارسی", "name_en": "Marseille", "code": "MAR", "color": "#2FAEE0", "played": 12, "won": 7, "drawn": 2, "lost": 3, "gf": 27, "ga": 16, "gd": 11, "points": 23},
        {"rank": 4, "name": "لیل", "name_en": "Lille", "code": "LIL", "color": "#E01E13", "played": 12, "won": 6, "drawn": 4, "lost": 2, "gf": 19, "ga": 11, "gd": 8, "points": 22},
        {"rank": 5, "name": "نیس", "name_en": "Nice", "code": "NIC", "color": "#D40028", "played": 12, "won": 5, "drawn": 5, "lost": 2, "gf": 23, "ga": 12, "gd": 11, "points": 20},
        {"rank": 6, "name": "لیون", "name_en": "Lyon", "code": "LYO", "color": "#14387F", "played": 12, "won": 5, "drawn": 4, "lost": 3, "gf": 19, "ga": 16, "gd": 3, "points": 19},
    ]
    with patch("src.xgpedia.providers.ligue1_live_free.fetch_ligue1_standings", return_value=fake_rows):
        mw = build_ligue1_matchweek_wrapup()
    assert mw is not None
    assert mw["competition"] == "لیگ ۱ فرانسه"
    assert mw["bestAttack"]["team"] == "پاری‌سن‌ژرمن"
    assert mw["bestDefense"]["team"] == "پاری‌سن‌ژرمن"
