"""تست‌های نسخهٔ 0.62.0: جلوگیری از تداخل هویت بازیکنان (لوییز جونیور ≠ وینیسیوس جونیور)، فونت xG وسط، عرض برترین‌های زمین و ولیدیتور پس‌ازبازی."""
from __future__ import annotations

from datetime import datetime, timezone

from src.xgpedia.config import translate_player_fa
from src.xgpedia.editorial.llm_provider import DraftOutput
from src.xgpedia.editorial.validate import _input_numbers, validate
from src.xgpedia.normalization.models import MatchFacts, MatchResult, MatchStats, SourceInfo, StatValue, TeamSide
from src.xgpedia.render.card_kit.base_shell import _render_post_hero, _render_pre_hero, _unified_css


def test_player_identity_never_confuses_luiz_junior_with_vinicius_junior() -> None:
    assert translate_player_fa("Luiz Júnior") == "لوییز جونیور"
    assert translate_player_fa("Luiz Junior") == "لوییز جونیور"
    assert "وینیسیوس" not in translate_player_fa("L. Júnior")
    assert "وینیسیوس" not in translate_player_fa("Carlos Júnior")
    assert "وینیسیوس" not in translate_player_fa("Junior Firpo")
    assert translate_player_fa("Vinicius Junior") == "وینیسیوس جونیور"
    assert translate_player_fa("Vinícius Júnior") == "وینیسیوس جونیور"
    assert translate_player_fa("Vini Jr") == "وینیسیوس جونیور"
    # عدم تداخل نام‌خانوادگی مشترک با نام کامل بازیکن دیگر
    assert translate_player_fa("Joan García") == "خوان گارسیا"
    assert translate_player_fa("Eric García") == "گارسیا"
    assert translate_player_fa("J. Oblak") == "اوبلاک"


def test_center_xg_total_uses_same_font_as_side_xg_and_toprated_has_wider_stat() -> None:
    payload = {
        "hasProbs": True,
        "match": {
            "scoreHome": 0,
            "scoreAway": 1,
            "probHome": 32,
            "probDraw": 33,
            "probAway": 35,
            "home": {"name": "اسلاویا پراگ", "color": "#EF4444", "xg": 0.97, "code": "SLA", "secondary": "#FFF"},
            "away": {"name": "ویارئال", "color": "#FACC15", "xg": 1.05, "code": "VIL", "secondary": "#000"},
        },
    }
    post_html = _render_post_hero(payload, fmt="4:5", header_mode="full")
    pre_html = _render_pre_hero(payload, fmt="4:5", header_mode="full")
    assert '<span class="hx-tot">' in post_html
    assert '<span class="hx-tot fm">' not in post_html
    assert '<span class="hx-tot">' in pre_html
    assert '<span class="hx-tot fm">' not in pre_html

    css = _unified_css(1080, 1350, "4:5")
    assert ".mod-half .tr-st{max-width:225px" in css


def test_validator_allows_post_match_ratings_saves_and_real_match_xg_with_zero_goals() -> None:
    facts = MatchFacts(
        fixture_id="espn:401915375",
        competition={"name": "UEFA Champions League", "season": "2026-27"},
        kickoff_utc=datetime(2026, 11, 25, 20, 0, tzinfo=timezone.utc),
        source=SourceInfo(provider="espn-public", collected_at="2026-11-26T10:00:00Z"),
        result=MatchResult(home_goals=0, away_goals=2),
        home=TeamSide(
            name_fa="شاختار دونتسک",
            name_en="Shakhtar Donetsk",
            xg_for_avg=None,
            match_stats=MatchStats(
                goals=StatValue(value=0),
                expected_goals=StatValue(value=0.60),
                total_shots=StatValue(value=9),
                shots_on_target=StatValue(value=2),
                corner_kicks=StatValue(value=4),
                big_chances=StatValue(value=1),
            ),
            gk={"name": "ریزنیک", "saves": 4, "psxg": 1.75, "ga": 2},
        ),
        away=TeamSide(
            name_fa="فنرباغچه",
            name_en="Fenerbahce",
            xg_for_avg=None,
            match_stats=MatchStats(
                goals=StatValue(value=2),
                expected_goals=StatValue(value=1.75),
                total_shots=StatValue(value=14),
                shots_on_target=StatValue(value=6),
                corner_kicks=StatValue(value=5),
                big_chances=StatValue(value=3),
            ),
            gk={"name": "لیواکوویچ", "saves": 2, "psxg": 0.60, "ga": 0},
        ),
        topPlayers=[
            {"name": "تادیچ", "side": "away", "stat": "1 گل", "rating": 8.1},
        ],
        motm={
            "side": "away",
            "name": "تادیچ",
            "pos": "هافبک",
            "number": 10,
            "rating": 8.1,
            "chips": [{"label": "امتیاز Opta", "val": "8.1"}],
            "runnerUp": {"side": "home", "name": "ریزنیک", "stat": "4 مهار", "rating": 7.4},
        },
    )
    nums = _input_numbers(facts)
    assert 8.1 in nums
    assert 4.0 in nums
    assert 0.6 in nums and 1.75 in nums

    draft = DraftOutput(
        status="ok",
        title="شاختار 0-2 فنرباغچه",
        bullets=["امید گل 0.60 مقابل 1.75", "تادیچ با امتیاز 8.1 و ریزنیک با 4 مهار"],
        caption="فنرباغچه با نتیجه 2-0 و برتری xG پیروز شد.",
        source_note="منبع داده: espn-public",
        uncertainties=[],
    )
    rep = validate(draft, facts, set())
    assert rep.passed, f"Unexpected validator failures: {rep.failures}"


def test_validator_still_blocks_null_to_zero_when_xg_truly_missing() -> None:
    facts = MatchFacts(
        fixture_id="fdo:1",
        competition={"name": "Premier League", "season": "2026-27"},
        kickoff_utc=datetime(2026, 11, 26, 20, 0, tzinfo=timezone.utc),
        source=SourceInfo(provider="football-data.org", collected_at="2026-11-26T10:00:00Z"),
        home=TeamSide(name_fa="آرسنال", name_en="Arsenal", xg_for_avg=StatValue(value=1.8, n=5)),
        away=TeamSide(name_fa="چلسی", name_en="Chelsea", xg_for_avg=None),
    )
    draft = DraftOutput(
        status="ok",
        title="آرسنال مقابل چلسی",
        bullets=["امید گل چلسی صفر است"],
        caption="xG چلسی در این فصل 0 بوده است.",
        source_note="منبع داده: football-data.org",
        uncertainties=[],
    )
    rep = validate(draft, facts, set())
    assert not rep.passed
    assert any("[null_to_zero]" in f for f in rep.failures)
