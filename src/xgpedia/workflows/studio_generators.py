"""نمای یکپارچهٔ تولیدکننده‌های کارت‌های استودیویی و ماژولار (بازآرایی‌شده در v0.75.0)."""
from __future__ import annotations

from src.xgpedia.workflows.studio_core_generators import (  # noqa: F401
    generate_on_this_day_post_async,
    generate_news_post_async,
    generate_birthday_post_async,
    generate_transfer_post_async,
    generate_this_or_that_post_async,
    generate_players_rating_post_async,
    generate_standings_post_async,
    generate_injury_post_async,
    generate_player_profile_post_async,
)
from src.xgpedia.workflows.studio_modular_generators import (  # noqa: F401
    _generate_v32_modular_post_async,
    generate_h2h_teams_post_async,
    generate_player_fc27_post_async,
    generate_h2h_players_post_async,
    generate_top_scorers_post_async,
    generate_matchday_results_post_async,
    generate_quote_post_async,
    generate_debate_post_async,
    generate_number_of_day_post_async,
    generate_matchweek_wrapup_post_async,
    generate_shotmap_xg_post_async,
    generate_value_radar_post_async,
    generate_lineup_injuries_post_async,
)
