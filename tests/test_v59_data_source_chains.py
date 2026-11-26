"""تست‌های نسخهٔ 0.59.0: موتور پلاگین‌پذیر زنجیرهٔ اولویت‌بندی منابع داده برای تمام ۲۳ کارت."""
from __future__ import annotations

import os
from unittest.mock import patch

from src.xgpedia.core.source_chain import (
    DataSourceChain,
    SourceCandidate,
    format_chains_report_fa,
    get_card_blueprint,
    list_all_card_blueprints,
    provider_priority_rank,
)
from src.xgpedia.providers import xg_engine as xge


def test_all_23_cards_have_required_fields_and_sorted_chains() -> None:
    bps = list_all_card_blueprints()
    assert len(bps) == 23
    card_ids = {b["card_id"] for b in bps}
    for must_have in (
        "pre_match", "post_match", "matchday_results", "shotmap_xg", "players_rating",
        "standings", "top_scorers", "player_profile", "player_fc27", "h2h_players",
        "h2h_teams", "lineup_injuries", "value_radar", "breaking_news",
    ):
        assert must_have in card_ids

    pm = get_card_blueprint("post_match")
    assert pm is not None
    assert "expected_goals" in pm["required_fields"]
    assert "shotmap_coords" in pm["required_fields"]
    xg_chain = pm["chains"]["match_xg_and_shotmap"]
    scores = [s["authority_score"] for s in xg_chain]
    assert scores == sorted(scores, reverse=True)
    assert provider_priority_rank("opta_official") > provider_priority_rank("sofascore") > provider_priority_rank("understat") > provider_priority_rank("espn-public")


def test_dynamic_source_registration_auto_sorts_by_authority() -> None:
    chain = DataSourceChain("test_domain")
    chain.register(SourceCandidate("espn-public", 78, "ESPN", fetcher=lambda: {"v": "espn"}))
    chain.register(SourceCandidate("understat", 88, "Understat", fetcher=lambda: {"v": "understat"}))
    # افزودن منبع معتبرتر جدید باید خودکار در صدر زنجیره قرار گیرد
    chain.register(SourceCandidate("fotmob", 93, "FotMob", fetcher=lambda: {"v": "fotmob"}))

    ordered_ids = [c.provider_id for c in chain.ordered_candidates(respect_health=False)]
    assert ordered_ids == ["fotmob", "understat", "espn-public"]

    res = chain.resolve(respect_health=False)
    assert res.ok is True
    assert res.provider_id == "fotmob"
    assert res.authority_score == 93
    assert res.data == {"v": "fotmob"}

    # منبع دارای کلید تنظیم‌نشده باید خودکار رد شود و وقتی کلید تنظیم شد در صدر قرار گیرد
    chain.register(SourceCandidate("sportmonks", 96, "Sportmonks", fetcher=lambda: {"v": "sportmonks"}, requires_env="SPORTMONKS_API_KEY"))
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("SPORTMONKS_API_KEY", None)
        res_no_key = chain.resolve(respect_health=False)
        assert res_no_key.provider_id == "fotmob"
    with patch.dict(os.environ, {"SPORTMONKS_API_KEY": "test_key_123"}):
        res_with_key = chain.resolve(respect_health=False)
        assert res_with_key.provider_id == "sportmonks"
        assert res_with_key.authority_score == 96


def test_xg_engine_exposes_pluggable_chain_and_report_formats() -> None:
    assert isinstance(xge.MATCH_XG_CHAIN, DataSourceChain)
    rep = format_chains_report_fa("post_match")
    assert "post_match" in rep and "fotmob" in rep and "sofascore" in rep
