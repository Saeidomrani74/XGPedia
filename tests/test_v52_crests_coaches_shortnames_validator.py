"""تست‌های نسخهٔ 0.52.0: لوگوهای رسمی ۶ لیگ، ویکی‌پدیای ۱۰۷ باشگاه، نام کوتاه بدون سه‌نقطه و اعتبارسنجی LLM."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from src.xgpedia.config import card_short_team_name_fa
from src.xgpedia.editorial.draft import generate_draft
from src.xgpedia.editorial.llm_provider import DraftOutput
from src.xgpedia.editorial.prompt import derived_numbers
from src.xgpedia.normalization.models import MatchFacts, MatchResult, MatchStats, StatValue, TeamSide
from src.xgpedia.providers.live_intel_free import TEAM_WIKI_TITLES
from src.xgpedia.providers.pl_badges_free import lookup_pl_club
from src.xgpedia.render.cards import _crest_data_uri


def test_all_107_clubs_have_wiki_titles_and_badges() -> None:
    g = json.loads(Path("config/glossary_fa.json").read_text(encoding="utf-8"))
    teams = g["teams"]
    assert len(teams) >= 139
    missing_wiki = [t["name_en"] for t in teams if t["name_en"] not in TEAM_WIKI_TITLES]
    assert missing_wiki == [], f"Missing TEAM_WIKI_TITLES: {missing_wiki}"
    # هر ۱۰۷ باشگاه اصلی ۶ لیگ در lookup_pl_club هستند و ۳۲ باشگاه جدید چمپیونزلیگ از dynamic_crests می‌گیرند
    covered = [t["name_en"] for t in teams if lookup_pl_club(t["name_en"]) is not None]
    assert len(covered) >= 107
    assert TEAM_WIKI_TITLES["Sporting CP"] == "Sporting CP"
    assert TEAM_WIKI_TITLES["AS Roma"] == "AS Roma"


def test_short_team_names_eliminate_ellipsis_truncation() -> None:
    assert card_short_team_name_fa("Sporting CP", "اسپورتینگ لیسبون") == "اسپورتینگ"
    assert card_short_team_name_fa("Borussia Monchengladbach", "بروسیا مونشن‌گلادباخ") == "گلادباخ"
    assert card_short_team_name_fa("Eintracht Frankfurt", "آینتراخت فرانکفورت") == "فرانکفورت"
    assert card_short_team_name_fa("Borussia Dortmund", "بروسیا دورتموند") == "دورتموند"
    assert card_short_team_name_fa("Atletico Madrid", "اتلتیکو مادرید") == "اتلتیکو"
    assert card_short_team_name_fa("PSV Eindhoven", "پی‌اس‌وی آیندهوون") == "آیندهوون"
    assert card_short_team_name_fa("Nottingham Forest", "ناتینگهام فارست") == "ناتینگهام"
    assert card_short_team_name_fa("Manchester United", "منچستریونایتد") == "منچستریونایتد"
    assert card_short_team_name_fa("Arsenal", "آرسنال") == "آرسنال"


def test_crest_data_uri_prefers_live_espn_png_over_placeholder_svg() -> None:
    fake_png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB"
    with patch("src.xgpedia.providers.pl_badges_free.get_pl_badge_data_uri", return_value=fake_png) as mk:
        # Sporting CP has a <2.5KB placeholder SVG -> must fetch official PNG
        uri = _crest_data_uri("Sporting CP")
        assert uri == fake_png
        mk.assert_called_once_with("Sporting CP")

    # Arsenal has a real 14KB local SVG -> must NOT call network
    with patch("src.xgpedia.providers.pl_badges_free.get_pl_badge_data_uri") as mk2:
        uri_ars = _crest_data_uri("Arsenal")
        assert uri_ars is not None and uri_ars.startswith("data:image/svg+xml;base64,")
        mk2.assert_not_called()


def test_derived_numbers_allows_total_shots_and_shot_share_and_recovers_empty_title() -> None:
    match = MatchFacts(
        fixture_id="fdo:575408",
        competition={"name": "UEFA Champions League", "season": "2026-27"},
        kickoff_utc="2026-11-25T20:00:00Z",
        home=TeamSide(
            name_en="Sporting CP",
            name_fa="اسپورتینگ لیسبون",
            match_stats=MatchStats(
                expected_goals=StatValue(value=1.66, n=1, unit="xG"),
                total_shots=StatValue(value=11, n=1),
                shots_on_target=StatValue(value=4, n=1),
                possession=StatValue(value=51, n=1, unit="%"),
            ),
        ),
        away=TeamSide(
            name_en="Manchester United",
            name_fa="منچستریونایتد",
            match_stats=MatchStats(
                expected_goals=StatValue(value=0.92, n=1, unit="xG"),
                total_shots=StatValue(value=7, n=1),
                shots_on_target=StatValue(value=2, n=1),
                possession=StatValue(value=49, n=1, unit="%"),
            ),
        ),
        result=MatchResult(home_goals=2, away_goals=2),
        source={"provider": "espn-public", "collected_at": "2026-11-26T00:00:00Z"},
    )
    dn = derived_numbers(match)
    assert 18.0 in dn  # 11 + 7 total shots
    assert 61.0 in dn  # round(11 / 18 * 100) shot share
    assert 36.0 in dn  # round(4 / 11 * 100) shot accuracy
    assert 4.0 in dn   # 2 + 2 total goals

    class _EmptyTitleLLM:
        def generate(self, sys_prompt, m, **kwargs):
            return DraftOutput(
                status="ok",
                title="",
                bullets=["از ۱۸ شوت مسابقه، ۶۱ درصد سهم اسپورتینگ لیسبون بود."],
                caption="تساوی ۲-۲ با برتری امید گل ۱.۶۶ میزبان.",
                source_note="",
                uncertainties=[],
            )

    draft, rep, attempts = generate_draft(_EmptyTitleLLM(), (match.model_dump() if hasattr(match, 'model_dump') else match.dict()), post_type="post_match")
    assert rep.passed is True
    assert attempts == 1
    assert "اسپورتینگ لیسبون" in draft.title and "2-2" in draft.title
