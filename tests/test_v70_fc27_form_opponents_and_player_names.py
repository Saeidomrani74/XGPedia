"""تست‌های نسخه v0.70.0:
- نمایش نام تیم‌های حریف زیر نقاط روند فرم ۵ بازی در کارت FC 27
- رفع خطای «بفرناندس» و پشتیبانی از فرم‌های مخفف بدون فاصله مثل B.Fernandes
- یکسان‌سازی مصطلح‌ترین نوشتار فارسی نام بازیکنان در glossary_fa، config و injury_free
"""
from __future__ import annotations

from unittest.mock import patch

from src.xgpedia.config import translate_player_fa
from src.xgpedia.providers import injury_free as inf
from src.xgpedia.providers import player_fc27_free as fc_free
from src.xgpedia.render.card_kit import player_fc27_card as fc_card


def test_bruno_fernandes_and_dot_abbreviations_never_glue_initial():
    assert inf.transliterate_player_name_fa("B.Fernandes") == "برونو فرناندز"
    assert inf.transliterate_player_name_fa("B. Fernandes") == "برونو فرناندز"
    assert inf.transliterate_player_name_fa("Bruno Borges Fernandes") == "برونو فرناندز"
    assert inf.transliterate_player_name_fa("Bruno Fernandes") == "برونو فرناندز"
    assert translate_player_fa("B.Fernandes") == "برونو فرناندز"
    assert translate_player_fa("Bruno Borges Fernandes") == "برونو فرناندز"

    # نام مخفف خارج از دیکشنری نیز نباید حرف اول را به نام‌خانوادگی بچسباند
    unknown = inf.transliterate_player_name_fa("J.Kowalski")
    assert not unknown.startswith("جک"), f"Initial glued to surname: {unknown!r}"


def test_standardized_idiomatic_persian_player_names():
    expected = {
        "Florian Wirtz": "فلوریان ویرتز",
        "Viktor Gyökeres": "ویکتور گیوکرش",
        "Rayan Cherki": "رایان شرکی",
        "Cody Gakpo": "کودی گاکپو",
        "Rúben Dias": "روبن دیاس",
        "Kobbie Mainoo": "کوبی ماینو",
        "Mohammed Kudus": "محمد کودوس",
        "Bruno Guimarães": "برونو گیمارش",
        "Gabriel Magalhães": "گابریل ماگالائس",
        "Tijjani Reijnders": "تیجانی ریندرز",
        "Morgan Gibbs-White": "مورگان گیبز-وایت",
        "Xaver Schlager": "زاور اشلاگر",
        "Vitaly Janelt": "ویتالی یانلت",
        "Marc Guéhi": "مارک گهی",
    }
    for en, fa_exp in expected.items():
        got = inf.transliterate_player_name_fa(en)
        assert got == fa_exp, f"{en}: got {got!r}, expected {fa_exp!r}"


def test_fc27_parse_and_hydrate_extracts_bruno_name_and_5_form_opponents():
    bootstrap = {
        "teams": [
            {"id": 1, "name": "Arsenal", "short_name": "ARS"},
            {"id": 6, "name": "Chelsea", "short_name": "CHE"},
            {"id": 8, "name": "Everton", "short_name": "EVE"},
            {"id": 12, "name": "Liverpool", "short_name": "LIV"},
            {"id": 14, "name": "Man Utd", "short_name": "MUN"},
            {"id": 20, "name": "Wolves", "short_name": "WOL"},
        ],
        "elements": [
            {
                "id": 366,
                "code": 141746,
                "team": 14,
                "element_type": 3,
                "first_name": "Bruno",
                "second_name": "Borges Fernandes",
                "web_name": "B.Fernandes",
                "minutes": 900,
                "starts": 10,
                "goals_scored": 4,
                "assists": 2,
                "expected_goals": "4.4",
                "expected_assists": "2.3",
                "expected_goals_per_90": 0.44,
                "expected_assists_per_90": 0.23,
                "expected_goal_involvements": "6.7",
                "creativity": "410",
                "threat": "280",
                "influence": "350",
                "ict_index": "98",
                "bps": "247",
                "clean_sheets": 3,
                "total_points": 62,
            }
        ],
    }

    items = fc_free.parse_fpl_fc27_players(bootstrap, limit=5)
    assert len(items) == 1
    item = items[0]
    assert item["name"] == "برونو فرناندز"
    assert "بفرناندس" not in item["verdictTitle"]
    assert "برونو فرناندز" in item["verdictTitle"]

    fake_summary = {
        "history": [
            {"minutes": 90, "bps": 10, "goals_scored": 0, "assists": 0, "opponent_team": 1},
            {"minutes": 90, "bps": 8, "goals_scored": 0, "assists": 0, "opponent_team": 6},
            {"minutes": 90, "bps": 16, "goals_scored": 0, "assists": 0, "opponent_team": 8},
            {"minutes": 90, "bps": 39, "goals_scored": 2, "assists": 0, "opponent_team": 12},
            {"minutes": 90, "bps": 24, "goals_scored": 1, "assists": 0, "opponent_team": 20},
        ]
    }

    with patch.object(fc_free, "_download_image_data_uri", return_value=None), patch.object(
        fc_free,
        "_http_get_json",
        side_effect=lambda url, timeout=6.5: fake_summary if "element-summary" in url else {},
    ):
        hydrated = fc_free.hydrate_player_fc27_item(item)

    assert len(hydrated["form"]) == 5
    assert hydrated["form_opponents"] == ["آرسنال", "چلسی", "اورتون", "لیورپول", "ولوز"]

    html = fc_card.render_player_fc27_html(hydrated, fmt="4:5", slide="slide1")
    assert "برونو فرناندز" in html
    assert "بفرناندس" not in html
    for opp in ("آرسنال", "چلسی", "اورتون", "لیورپول", "ولوز"):
        assert opp in html, f"Opponent {opp!r} missing in FC27 sparkline HTML"
    assert 'viewBox="0 0 240 124"' in html
