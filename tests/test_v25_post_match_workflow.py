"""تست‌های جامع نسخهٔ v0.25.0 — راه‌اندازی کامل کارت‌های پس‌ازبازی در ربات با دیتای واقعی (۱ ثانیه تا ۲۴ ساعت پیش)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.xgpedia import db as db_mod
from src.xgpedia.providers.espn_free import parse_espn_finished_summary
from src.xgpedia.render.card_kit.helpers import wcag_contrast
from src.xgpedia.render.post_match_cards import render_post_match_html
from src.xgpedia.sync import build_match_facts, sync_espn_finished_matches
from src.xgpedia.today_workflow import list_recent_finished_fixtures


def test_parse_espn_finished_summary_real_stats_scorers_momentum_and_gk():
    summary = {
        "header": {
            "id": "701234",
            "competitions": [
                {
                    "date": "2026-11-22T17:30:00Z",
                    "status": {"type": {"state": "post"}},
                    "competitors": [
                        {"homeAway": "home", "score": "2", "team": {"id": "367", "displayName": "Tottenham Hotspur"}},
                        {"homeAway": "away", "score": "1", "team": {"id": "361", "displayName": "Newcastle United"}},
                    ],
                }
            ],
        },
        "boxscore": {
            "teams": [
                {
                    "team": {"id": "367", "displayName": "Tottenham Hotspur"},
                    "statistics": [
                        {"name": "possessionPct", "displayValue": "58%"},
                        {"name": "totalShots", "displayValue": "15"},
                        {"name": "shotsOnTarget", "displayValue": "6"},
                        {"name": "wonCorners", "displayValue": "7"},
                        {"name": "foulsCommitted", "displayValue": "10"},
                        {"name": "saves", "displayValue": "3"},
                        {"name": "expectedGoals", "displayValue": "2.15"},
                    ],
                },
                {
                    "team": {"id": "361", "displayName": "Newcastle United"},
                    "statistics": [
                        {"name": "possessionPct", "displayValue": "42%"},
                        {"name": "totalShots", "displayValue": "9"},
                        {"name": "shotsOnTarget", "displayValue": "4"},
                        {"name": "wonCorners", "displayValue": "3"},
                        {"name": "foulsCommitted", "displayValue": "12"},
                        {"name": "saves", "displayValue": "4"},
                        {"name": "expectedGoals", "displayValue": "1.12"},
                    ],
                },
            ]
        },
        "keyEvents": [
            {"scoringPlay": True, "type": {"text": "Goal"}, "team": {"id": "367"}, "clock": {"value": 900}, "participants": [{"athlete": {"shortName": "Son"}}]},
            {"scoringPlay": False, "type": {"text": "Shot"}, "team": {"id": "367"}, "clock": {"value": 1500}},
            {"scoringPlay": False, "type": {"text": "Corner"}, "team": {"id": "361"}, "clock": {"value": 2100}},
            {"scoringPlay": True, "type": {"text": "Goal"}, "team": {"id": "361"}, "clock": {"value": 2800}, "participants": [{"athlete": {"shortName": "Isak"}}]},
            {"scoringPlay": False, "type": {"text": "Shot"}, "team": {"id": "367"}, "clock": {"value": 3600}},
            {"scoringPlay": True, "type": {"text": "Goal"}, "team": {"id": "367"}, "clock": {"value": 4500}, "participants": [{"athlete": {"shortName": "Maddison"}}]},
        ],
        "rosters": [
            {
                "team": {"id": "367"},
                "roster": [{"starter": True, "position": {"abbreviation": "G"}, "athlete": {"shortName": "Vicario"}}],
            },
            {
                "team": {"id": "361"},
                "roster": [{"starter": True, "position": {"abbreviation": "G"}, "athlete": {"shortName": "Pope"}}],
            },
        ],
    }

    parsed = parse_espn_finished_summary(summary)
    assert parsed is not None
    assert parsed["home_team"] == "Tottenham"
    assert parsed["away_team"] == "Newcastle United"
    assert parsed["home_goals"] == 2 and parsed["away_goals"] == 1
    assert parsed["home_stats"]["possession"] == 58.0
    assert parsed["home_stats"]["total_shots"] == 15.0
    assert parsed["home_stats"]["expected_goals"] > 0
    assert "Son 15′" in parsed["details"]["scorers_home"]
    assert "Maddison 75′" in parsed["details"]["scorers_home"]
    assert "Isak 47′" in parsed["details"]["scorers_away"]
    assert isinstance(parsed["details"]["momentum"], list) and len(parsed["details"]["momentum"]) == 18
    assert parsed["details"]["home_gk"]["name"] == "Vicario"
    assert parsed["details"]["away_gk"]["name"] == "Pope"


def test_list_recent_finished_fixtures_exact_1s_to_24h_window(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "post_window.db"
    monkeypatch.setattr(db_mod, "DATABASE_PATH", db_path)
    db_mod.init_db()

    now = datetime(2026, 11, 23, 12, 0, 0, tzinfo=timezone.utc)
    # ۱) بازی تمام‌شده ۱۰ دقیقه پیش (kickoff حدود ۲ ساعت پیش) -> باید بیاید
    ko_recent = (now - timedelta(hours=2, minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    # ۲) بازی تمام‌شده ۳۶ ساعت پیش -> نباید بیاید (خارج از بازه ۲۴ ساعته)
    ko_old = (now - timedelta(hours=38)).strftime("%Y-%m-%dT%H:%M:%SZ")
    # ۳) بازی تمام‌شده ۱ ثانیه پیش (kickoff = 115m + 1s پیش) -> باید بیاید
    ko_just_ended = (now - timedelta(minutes=115, seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    sync_espn_finished_matches([
        {
            "event_id": "101", "home_team": "Tottenham", "away_team": "Newcastle",
            "kickoff_utc": ko_recent, "home_goals": 2, "away_goals": 1,
            "home_stats": {"expected_goals": 1.85, "total_shots": 14, "shots_on_target": 6, "possession": 56},
            "away_stats": {"expected_goals": 1.12, "total_shots": 9, "shots_on_target": 3, "possession": 44},
            "details": {"scorers_home": "Son 15'", "scorers_away": "Isak 47'", "momentum": [15, -10, 20, 5, -5, 10]},
        },
        {
            "event_id": "102", "home_team": "Arsenal", "away_team": "Chelsea",
            "kickoff_utc": ko_old, "home_goals": 1, "away_goals": 1,
            "home_stats": {"expected_goals": 1.4, "total_shots": 11, "shots_on_target": 4},
            "away_stats": {"expected_goals": 1.2, "total_shots": 10, "shots_on_target": 4},
            "details": {},
        },
        {
            "event_id": "103", "home_team": "Liverpool", "away_team": "Everton",
            "kickoff_utc": ko_just_ended, "home_goals": 3, "away_goals": 0,
            "home_stats": {"expected_goals": 2.4, "total_shots": 18, "shots_on_target": 8},
            "away_stats": {"expected_goals": 0.6, "total_shots": 5, "shots_on_target": 1},
            "details": {"scorers_home": "Salah 20'"},
        },
    ], season_start=2026)

    items = list_recent_finished_fixtures(now_utc=now, hours=24.0)
    fids = [it.fixture_id for it in items]
    assert "espn:103" in fids
    assert "espn:101" in fids
    assert "espn:102" not in fids
    # جدیدترین بازی باید اول لیست باشد
    assert fids[0] == "espn:103"


def test_post_match_card_custom_modules_dark_contrast_and_mobile_readability():
    facts = {
        "fixture_id": "espn:101",
        "competition": {"name": "Premier League", "season": "2026-27"},
        "matchday": 12,
        "round": "هفته ۱۲ • گزارش پس‌ازبازی",
        "stadium": "ورزشگاه تاتنهام",
        "kickoff_utc": "2026-11-22T17:30:00Z",
        "source": {"provider": "espn-public"},
        "result": {"home_goals": 2, "away_goals": 1},
        "momentum": [15, -10, 22, 8, -14, 18, 12, -5],
        "home": {
            "name_fa": "تاتنهام", "name_en": "Tottenham", "sub": "توماس فرانک",
            "scorersText": "سون ۱۵'، مدیسون ۷۵'",
            "match_stats": {
                "expected_goals": {"value": 1.85}, "possession": {"value": 56},
                "total_shots": {"value": 14}, "shots_on_target": {"value": 6},
            },
        },
        "away": {
            "name_fa": "نیوکاسل", "name_en": "Newcastle", "sub": "ادی هاو",
            "scorersText": "ایساک ۴۷'",
            "match_stats": {
                "expected_goals": {"value": 1.12}, "possession": {"value": 44},
                "total_shots": {"value": 9}, "shots_on_target": {"value": 3},
            },
        },
    }
    draft = {"title": "برد تاتنهام", "bullets": ["برتری در xG"], "caption": "گزارش پس‌ازبازی."}
    html = render_post_match_html(
        draft,
        facts,
        fmt="4:5",
        header_mode="full",
        custom_modules=[{"id": "momentum", "span": "full"}, {"id": "stats", "span": "full"}],
    )
    assert "پایان بازی" in html
    assert "سون ۱۵" in html
    assert "موج فشار" in html
    # رنگ‌های تیره تاتنهام (#132257) و نیوکاسل (#241F20) باید خودکار به کنتراست خوانا تبدیل شده باشند
    assert "#132257" not in html
    assert "#241F20" not in html
    assert "#617FE7" in html  # تاتنهام روشن‌شده با WCAG >= 4.8
    assert wcag_contrast("#617FE7", "#0D1730") >= 4.8


def test_fpl_and_understat_unlock_all_7_post_match_modules_and_survive_pydantic(tmp_path: Path, monkeypatch):
    from src.xgpedia.normalization.models import MatchFacts
    from src.xgpedia.providers.fpl_free import parse_fpl_match_post_details
    from src.xgpedia.providers.understat import parse_understat_match_shots
    from src.xgpedia.render.post_match_cards import build_post_match_context
    from src.xgpedia.sync import merge_post_match_details

    db_path = tmp_path / "all7_post.db"
    monkeypatch.setattr(db_mod, "DATABASE_PATH", db_path)
    db_mod.init_db()

    # ۱) ذخیرهٔ اولیه از ESPN (آمار + گلزنان + مومنتوم)
    sync_espn_finished_matches([{
        "event_id": "901", "home_team": "Liverpool", "away_team": "Manchester United",
        "kickoff_utc": "2026-11-22T16:30:00Z", "home_goals": 2, "away_goals": 1,
        "home_stats": {"expected_goals": 1.9, "possession": 61.0, "total_shots": 16.0, "shots_on_target": 7.0, "corner_kicks": 8.0, "fouls": 9.0},
        "away_stats": {"expected_goals": 1.1, "possession": 39.0, "total_shots": 9.0, "shots_on_target": 3.0, "corner_kicks": 4.0, "fouls": 13.0},
        "details": {"scorers_home": "Salah 23', Diaz 68'", "scorers_away": "Fernandes 51'", "momentum": [20, 10, -5, 30, -15, 18, 12, -8]},
    }], season_start=2026)

    # ۲) پارس FPL Official Live GW -> toprated + motm + GK (Opta BPS & xGC)
    bs = {
        "teams": [{"id": 11, "name": "Liverpool"}, {"id": 14, "name": "Man Utd"}],
        "elements": [
            {"id": 1, "team": 11, "element_type": 1, "web_name": "Alisson", "squad_number": 1},
            {"id": 2, "team": 11, "element_type": 3, "web_name": "Salah", "squad_number": 11},
            {"id": 3, "team": 11, "element_type": 3, "web_name": "Diaz", "squad_number": 7},
            {"id": 4, "team": 14, "element_type": 1, "web_name": "Onana", "squad_number": 24},
            {"id": 5, "team": 14, "element_type": 3, "web_name": "B.Fernandes", "squad_number": 8},
            {"id": 6, "team": 14, "element_type": 4, "web_name": "Hojlund", "squad_number": 9},
        ],
    }
    fxs = [{"id": 55, "team_h": 11, "team_a": 14, "team_h_score": 2, "team_a_score": 1, "kickoff_time": "2026-11-22T16:30:00Z"}]
    live_gw = {
        "elements": [
            {"id": 1, "explain": [{"fixture": 55}], "stats": {"minutes": 90, "bps": 22, "saves": 3, "expected_goals_conceded": 1.15}},
            {"id": 2, "explain": [{"fixture": 55}], "stats": {"minutes": 90, "bps": 44, "goals_scored": 1, "assists": 1, "expected_goals": 0.72, "expected_assists": 0.41}},
            {"id": 3, "explain": [{"fixture": 55}], "stats": {"minutes": 85, "bps": 34, "goals_scored": 1, "expected_goals": 0.55}},
            {"id": 4, "explain": [{"fixture": 55}], "stats": {"minutes": 90, "bps": 26, "saves": 5, "expected_goals_conceded": 2.05}},
            {"id": 5, "explain": [{"fixture": 55}], "stats": {"minutes": 90, "bps": 36, "goals_scored": 1, "expected_goals": 0.48, "expected_assists": 0.30}},
            {"id": 6, "explain": [{"fixture": 55}], "stats": {"minutes": 78, "bps": 14, "expected_goals": 0.35}},
        ]
    }
    fpl_det = parse_fpl_match_post_details(bs, fxs, live_gw, "Liverpool", "Manchester United", "2026-11-22")
    assert fpl_det is not None
    assert len(fpl_det["top_players"]) == 5
    assert fpl_det["motm"]["name"] == "Salah"
    assert fpl_det["motm"]["runnerUp"]["name"] == "B.Fernandes"
    assert fpl_det["home_gk"]["name"] == "Alisson" and fpl_det["away_gk"]["name"] == "Onana"
    # قانون null != 0 و صحت شاخص: xGC در FPL هرگز به نام PSxG ثبت نمی‌شود
    assert fpl_det["home_gk"]["psxg"] is None and fpl_det["home_gk"]["xgc"] == 1.15
    assert fpl_det["away_gk"]["psxg"] is None and fpl_det["away_gk"]["xgc"] == 2.05
    merge_post_match_details("espn:901", fpl_det, provider="fpl-official")
    # افزودن PSxG واقعی (xGOT faced از FotMob/Opta) برای بازشدن ماژول efficiency
    merge_post_match_details(
        "espn:901",
        {
            "home_gk": {**fpl_det["home_gk"], "psxg": 1.42},
            "away_gk": {**fpl_det["away_gk"], "psxg": 2.18},
        },
        provider="fotmob",
    )

    # ۳) پارس Understat shotsData -> xgrace + shotmap + insideBox
    us_det = parse_understat_match_shots({
        "h": [
            {"X": "0.89", "Y": "0.48", "xG": "0.45", "minute": "23", "player": "Mohamed Salah", "result": "Goal"},
            {"X": "0.86", "Y": "0.52", "xG": "0.38", "minute": "68", "player": "Luis Diaz", "result": "Goal"},
            {"X": "0.75", "Y": "0.35", "xG": "0.08", "minute": "80", "player": "Szoboszlai", "result": "SavedShot"},
        ],
        "a": [
            {"X": "0.88", "Y": "0.50", "xG": "0.34", "minute": "51", "player": "Bruno Fernandes", "result": "Goal"},
            {"X": "0.79", "Y": "0.60", "xG": "0.12", "minute": "72", "player": "Hojlund", "result": "MissedShots"},
        ],
    })
    assert us_det is not None and us_det["home_inside_box"] == 2 and us_det["away_inside_box"] == 1
    merge_post_match_details(
        "espn:901",
        {
            "home_shots": us_det["home_shots"], "away_shots": us_det["away_shots"],
            "home_inside_box": us_det["home_inside_box"], "away_inside_box": us_det["away_inside_box"],
        },
        provider="understat",
        extra_stats={"Liverpool": {"expected_goals": us_det["home_xg"]}, "Manchester United": {"expected_goals": us_det["away_xg"]}},
    )

    # ۴) بررسی build_match_facts + عبور کامل از Pydantic بدون حذف هیچ ماژولی!
    facts = build_match_facts("espn:901", post_match=True)
    # تست سازگاری با Pydantic (بدون از دست رفتن momentum/topPlayers/motm/shotList/gk/scorersText)
    if hasattr(MatchFacts, "model_validate"):
        validated = MatchFacts.model_validate(facts)
        roundtrip = validated.model_dump()
    else:
        validated = MatchFacts.parse_obj(facts)
        roundtrip = validated.dict()

    ctx = build_post_match_context({"title": "برد لیورپول", "bullets": ["برتری"], "caption": "گزارش"}, roundtrip, fmt="4:5")
    for mod_id in ("xgrace", "shotmap", "momentum", "efficiency", "toprated", "motm", "stats"):
        assert ctx["has"][mod_id] is True, f"Module {mod_id} should be available!"
    html = render_post_match_html(
        {"title": "برد لیورپول", "bullets": ["برتری"], "caption": "گزارش"},
        roundtrip,
        fmt="4:5",
        custom_modules=[{"id": "momentum", "span": "full"}, {"id": "stats", "span": "full"}],
    )
    assert "موج فشار" in html and "آمار کلیدی مسابقه" in html


def test_v252_scorers_no_html_entity_no_zero_goal_label_and_motm_wording():
    from src.xgpedia.render.card_kit.modules.post_modules import render_motm

    facts = {
        "fixture_id": "espn:400",
        "competition": {"name": "Premier League", "season": "2026-27"},
        "matchday": 11,
        "round": "هفته ۱۱ • کالبدشکافی پس از بازی",
        "stadium": "ورزشگاه آنفیلد",
        "kickoff_utc": "2026-11-22T16:30:00Z",
        "source": {"provider": "espn-public"},
        "result": {"home_goals": 4, "away_goals": 0},
        "home": {
            "name_fa": "لیورپول", "name_en": "Liverpool", "sub": "آندونی ایرائولا",
            "scorersText": "ویرتز ۱۲'، انگوموها ۱۷'، سوبوسلای ۶۴'",
            "match_stats": {"expected_goals": {"value": 4.43}, "total_shots": {"value": 28}, "shots_on_target": {"value": 11}},
        },
        "away": {
            "name_fa": "منچستریونایتد", "name_en": "Manchester United", "sub": "مائوریسیو پوچتینو",
            "match_stats": {"expected_goals": {"value": 1.35}, "total_shots": {"value": 10}, "shots_on_target": {"value": 3}},
        },
    }
    html = render_post_match_html({"title": "برد ۴-۰", "bullets": ["برتری"], "caption": "گزارش"}, facts, fmt="4:5")
    # هرگز نباید &#x۲۷; (entity خراب فارسی‌شده) یا «بدون گل زده» روی کارت بیاید
    assert "&#x۲۷;" not in html
    assert "بدون گل زده" not in html
    assert "ویرتز ۱۲" in html

    motm_html = render_motm({
        "match": {
            "home": {"name": "لیورپول", "color": "#F04360"},
            "away": {"name": "منچستریونایتد", "color": "#FBBF24"},
            "motm": {
                "side": "home", "name": "Wirtz", "pos": "هافبک", "rating": 9.4,
                "chips": [{"label": "گل", "val": "1"}],
                "runnerUp": {"side": "away", "name": "Lammens", "rating": 7.1},
            },
        }
    })
    assert "برترین بازیکن حریف" in motm_html


def test_v253_default_post_match_template_d44_zero_duplication_and_persian_scorers():
    from src.xgpedia.config import format_scorers_fa
    from src.xgpedia.render.post_match_cards import _build_post_stats_rows
    from src.xgpedia.render.studio_engine import DEFAULT_POST_MATCH_TEMPLATE, select_studio_modules

    assert DEFAULT_POST_MATCH_TEMPLATE == [
        ("momentum", "half"),
        ("stats", "half"),
        ("toprated", "half"),
        ("efficiency", "half"),
    ]
    all_has = {k: True for k in ("xgrace", "shotmap", "momentum", "efficiency", "toprated", "motm", "stats")}
    mods = select_studio_modules("post_match", all_has, fmt="4:5", layout="smart", header_mode="full")
    assert [(m["id"], m["span"]) for m in mods] == DEFAULT_POST_MATCH_TEMPLATE

    # آمار مسابقه نباید امید گل تکراری داشته باشد و باید کیفیت هر شوت (xG/شوت) را بسازد
    rows = _build_post_stats_rows(
        {"expected_goals": 4.43, "possession": 63, "total_shots": 28, "shots_on_target": 11, "corner_kicks": 8},
        {"expected_goals": 1.35, "possession": 37, "total_shots": 10, "shots_on_target": 3, "corner_kicks": 2},
    )
    labels = [r["label"] for r in rows]
    assert not any("امید گل واقعی" in l for l in labels)
    assert any("کیفیت هر شوت" in l for l in labels)

    # نام گلزنان به فارسی تبدیل شود
    fa_sc = format_scorers_fa("Florian Wirtz 12′, Rio Ngumoha 17′, Dominik Szoboszlai 64′")
    assert "ویرتز" in fa_sc and "انگوموها" in fa_sc and "سوبوسلای" in fa_sc
    assert not any("a" <= ch.lower() <= "z" for ch in fa_sc)
