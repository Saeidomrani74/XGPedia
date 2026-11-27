"""تست‌های نسخه v0.48.0 — پشتیبانی کامل بوندس‌لیگا آلمان (Bundesliga Glossary، رنگ‌ها، ورزشگاه‌ها، لوگوها و دیتای زنده)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from src.xgpedia.providers.bundesliga_live_free import build_bundesliga_matchweek_wrapup
from src.xgpedia.providers.pl_badges_free import get_pl_badge_data_uri, lookup_pl_club


def test_bundesliga_all_18_clubs_symmetric_in_all_four_configs_and_crests() -> None:
    gl = json.loads(Path("config/glossary_fa.json").read_text(encoding="utf-8"))
    ti = json.loads(Path("config/team_identities.json").read_text(encoding="utf-8"))
    tm = json.loads(Path("config/team_mapping.json").read_text(encoding="utf-8"))
    tv = json.loads(Path("config/team_venues.json").read_text(encoding="utf-8"))

    g_codes = {t["id"] for t in gl["teams"]}
    i_codes = {t["code"] for t in ti["teams"].values()}
    assert g_codes == i_codes, "Glossary and team_identities must remain 1:1 symmetric"

    for code, name_en, name_fa in (
        ("BAY", "Bayern Munich", "بایرن مونیخ"),
        ("BVB", "Borussia Dortmund", "بوروسیا دورتموند"),
        ("LEV", "Bayer Leverkusen", "بایر لورکوزن"),
        ("RBL", "RB Leipzig", "آر بی لایپزیگ"),
        ("STU", "VfB Stuttgart", "اشتوتگارت"),
        ("SGE", "Eintracht Frankfurt", "آینتراخت فرانکفورت"),
        ("SCF", "SC Freiburg", "فرایبورگ"),
        ("BMG", "Borussia Monchengladbach", "بوروسیا مونشن‌گلادباخ"),
        ("SVW", "Werder Bremen", "وردربرمن"),
        ("WOB", "VfL Wolfsburg", "ولفسبورگ"),
        ("M05", "Mainz 05", "ماینتس"),
        ("FCA", "FC Augsburg", "آوگسبورگ"),
        ("FCU", "Union Berlin", "یونیون برلین"),
        ("TSG", "TSG Hoffenheim", "هوفنهایم"),
        ("HDH", "FC Heidenheim", "هایدنهایم"),
        ("STP", "FC St. Pauli", "سن‌پائولی"),
        ("KIE", "Holstein Kiel", "هولشتاین کیل"),
        ("BOC", "VfL Bochum", "بوخوم"),
    ):
        assert code in g_codes
        assert name_en in ti["teams"]
        assert name_en in tm["teams"]
        assert tm["teams"][name_en]["name_fa"] == name_fa
        assert name_en in tv["teams"]
        assert (Path("brand/crests") / f"{code}.svg").exists() or (Path("brand/crests") / f"{code}.png").exists()


def test_pl_badges_bridge_resolves_bundesliga_clubs_and_offline_crests() -> None:
    for en, expected_fa, expected_tla in (
        ("SC Freiburg", "فرایبورگ", "SCF"),
        ("Werder Bremen", "وردربرمن", "SVW"),
        ("VfL Wolfsburg", "ولفسبورگ", "WOB"),
        ("Union Berlin", "یونیون برلین", "FCU"),
        ("Mainz 05", "ماینتس", "M05"),
    ):
        info = lookup_pl_club(en)
        assert info is not None
        assert info[0] == expected_fa
        assert info[1] == expected_tla
        uri = get_pl_badge_data_uri(en, fetch_network=False)
        assert uri is not None and uri.startswith("data:image/")


def test_bundesliga_live_matchweek_wrapup_builder() -> None:
    fake_rows = [
        {"rank": 1, "name": "بایرن مونیخ", "name_en": "Bayern Munich", "code": "BAY", "color": "#DC052D", "played": 11, "won": 9, "drawn": 2, "lost": 0, "gf": 36, "ga": 7, "gd": 29, "points": 29},
        {"rank": 2, "name": "آینتراخت فرانکفورت", "name_en": "Eintracht Frankfurt", "code": "SGE", "color": "#E1000F", "played": 11, "won": 7, "drawn": 2, "lost": 2, "gf": 27, "ga": 16, "gd": 11, "points": 23},
        {"rank": 3, "name": "آر بی لایپزیگ", "name_en": "RB Leipzig", "code": "RBL", "color": "#DD0741", "played": 11, "won": 6, "drawn": 3, "lost": 2, "gf": 18, "ga": 9, "gd": 9, "points": 21},
        {"rank": 4, "name": "بایر لورکوزن", "name_en": "Bayer Leverkusen", "code": "LEV", "color": "#E32221", "played": 11, "won": 5, "drawn": 5, "lost": 1, "gf": 26, "ga": 18, "gd": 8, "points": 20},
        {"rank": 5, "name": "بوروسیا دورتموند", "name_en": "Borussia Dortmund", "code": "BVB", "color": "#FDE100", "played": 11, "won": 6, "drawn": 1, "lost": 4, "gf": 22, "ga": 18, "gd": 4, "points": 19},
        {"rank": 6, "name": "فرایبورگ", "name_en": "SC Freiburg", "code": "SCF", "color": "#E30613", "played": 11, "won": 5, "drawn": 2, "lost": 4, "gf": 13, "ga": 15, "gd": -2, "points": 17},
    ]
    with patch("src.xgpedia.providers.bundesliga_live_free.fetch_bundesliga_standings", return_value=fake_rows):
        mw = build_bundesliga_matchweek_wrapup()
    assert mw is not None
    assert mw["competition"] == "بوندس‌لیگا آلمان"
    assert mw["bestAttack"]["team"] == "بایرن مونیخ"
    assert mw["bestDefense"]["team"] == "بایرن مونیخ"
