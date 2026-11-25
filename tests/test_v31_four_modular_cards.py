"""تست‌های جامع ۴ کارت ماژولار جدید XGPedia (v0.31.0 — D51 تا D54):
  1. Players Rating Studio (D51)
  2. Standings Studio (D52)
  3. Injury Lab (D53)
  4. Player Profile Studio (D54)
"""
from __future__ import annotations

import ast
from pathlib import Path

from src.xgpedia.layout_templates import (
    apply_template_to_modules,
    delete_layout_template,
    list_layout_templates,
    save_layout_template,
)
from src.xgpedia.providers.injury_free import (
    detect_injury_zone,
    enrich_injury_item,
    load_injury_presets,
    parse_fpl_injuries,
)
from src.xgpedia.providers.player_profile_free import (
    enrich_player_profile,
    load_player_profile_presets,
    parse_fpl_top_players,
)
from src.xgpedia.providers.players_rating_free import (
    enrich_players_rating_match,
    load_players_rating_presets,
    parse_espn_match_summary,
)
from src.xgpedia.providers.standings_free import (
    STANDINGS_LEAGUE_SPECS,
    load_standings_presets,
    parse_espn_standings,
)
from src.xgpedia.publishers import telegram_publish as tp
from src.xgpedia.render.card_kit.injury_card import (
    INJURY_SLIDES,
    build_injury_caption,
    get_injury_modules,
    render_injury_html,
)
from src.xgpedia.render.card_kit.player_card import (
    PLAYER_SLIDES,
    build_player_caption,
    get_player_modules,
    render_player_html,
)
from src.xgpedia.render.card_kit.players_rating_card import (
    RATINGS_SLIDES,
    build_players_rating_caption,
    get_players_rating_modules,
    render_players_rating_html,
)
from src.xgpedia.render.card_kit.standings_card import (
    STANDINGS_SLIDES,
    build_standings_caption,
    get_standings_modules,
    render_standings_html,
)


def _assert_offline_and_framed(html_str: str) -> None:
    assert "cdn.tailwindcss.com" not in html_str
    assert "fonts.googleapis.com" not in html_str
    assert "#E62E45" in html_str
    assert "M24 44V24H44" in html_str
    assert "@XGPedia" in html_str


def test_no_requests_dependency_in_new_providers() -> None:
    root = Path(__file__).resolve().parents[1]
    for rel in (
        "src/xgpedia/providers/players_rating_free.py",
        "src/xgpedia/providers/standings_free.py",
        "src/xgpedia/providers/injury_free.py",
        "src/xgpedia/providers/player_profile_free.py",
    ):
        tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "requests", f"Forbidden requests import in {rel}"
            elif isinstance(node, ast.ImportFrom):
                assert node.module != "requests", f"Forbidden requests import in {rel}"


def test_players_rating_card_all_slides_and_modular() -> None:
    presets = load_players_rating_presets()
    assert len(presets) == 4
    match = presets[0]
    for sid, _, pm, _ in RATINGS_SLIDES:
        html_out = render_players_rating_html(match, slide=sid, fmt="4:5", pitch_mode=pm)
        _assert_offline_and_framed(html_out)
        assert "آرسنال" in html_out
    # 9:16 & 16:9
    _assert_offline_and_framed(render_players_rating_html(match, slide="slide1", fmt="9:16"))
    _assert_offline_and_framed(render_players_rating_html(match, slide="slide1", fmt="16:9", header_mode="compact"))
    # Modular reorder & half/full
    mods, missing = get_players_rating_modules(match, "slide1")
    assert len(mods) == 4 and not missing
    mods[1]["enabled"] = True
    mods[1]["span"] = "half"
    mods[3]["enabled"] = True
    mods[3]["span"] = "half"
    html_custom = render_players_rating_html(match, custom_modules=mods)
    _assert_offline_and_framed(html_custom)
    cap = build_players_rating_caption(match)
    assert "نمرات بازیکنان" in cap


def test_standings_card_all_slides_and_null_not_zero() -> None:
    presets = load_standings_presets()
    assert len(presets) == 4
    lg = presets[0]
    for sid, _, ln, slc, hm, _ in STANDINGS_SLIDES:
        html_out = render_standings_html(lg, slide=sid, lens=ln, table_slice=slc, header_mode=hm, fmt="4:5")
        _assert_offline_and_framed(html_out)
        assert "لیگ برتر انگلیس" in html_out
    _assert_offline_and_framed(render_standings_html(lg, slide="slide3", fmt="16:9"))
    # null != 0 check: league without xG/xPTS should report justice & quadrant as missing
    no_xg = {**lg, "teams": [{**t, "xpts": None, "xg90": None, "xga90": None} for t in lg["teams"]]}
    mods, missing = get_standings_modules(no_xg, "slide1")
    mod_ids = {m["id"] for m in mods}
    assert "table" in mod_ids
    assert "justice" not in mod_ids and "quadrant" not in mod_ids
    assert len(missing) >= 2
    assert "جدول رده‌بندی" in build_standings_caption(lg)


def test_injury_card_all_slides_and_anatomical_zones() -> None:
    presets = load_injury_presets()
    assert len(presets) == 4
    item = presets[0]
    for sid, _, hm, _ in INJURY_SLIDES:
        html_out = render_injury_html(item, slide=sid, header_mode=hm, fmt="4:5")
        _assert_offline_and_framed(html_out)
        assert "بوکایو ساکا" in html_out
    _assert_offline_and_framed(render_injury_html(item, slide="slide1", fmt="9:16", severity_override="doubt"))
    mods, missing = get_injury_modules(item, "slide1")
    assert len(mods) == 7 and not missing
    assert detect_injury_zone("ACL knee surgery ruled out") == "acl"
    assert detect_injury_zone("Hamstring strain grade 2") == "hamstring"
    assert "گزارش پزشکی" in build_injury_caption(item)


def test_player_profile_card_all_slides_and_themes() -> None:
    presets = load_player_profile_presets()
    assert len(presets) == 4
    pl = presets[0]
    for sid, _, hm, _ in PLAYER_SLIDES:
        html_out = render_player_html(pl, slide=sid, header_mode=hm, fmt="4:5")
        _assert_offline_and_framed(html_out)
        assert "بوکایو ساکا" in html_out
    for th in ("classic", "gold", "blueprint"):
        _assert_offline_and_framed(render_player_html(pl, slide="slide1", theme=th, fmt="16:9"))
    mods, missing = get_player_modules(pl, "slide1")
    assert len(mods) == 9 and not missing
    assert "پروفایل فنی بازیکن" in build_player_caption(pl)


def test_live_parsers_and_soccer_only_guard() -> None:
    # 1. ESPN Match Summary parser + NFL rejection
    nfl_summary = {
        "header": {"competitions": [{"competitors": [
            {"homeAway": "home", "score": "21", "team": {"displayName": "NFL Chiefs"}},
            {"homeAway": "away", "score": "14", "team": {"displayName": "NFL Bills"}},
        ]}]},
        "rosters": [{}, {}],
    }
    assert parse_espn_match_summary(nfl_summary, league_slug="nfl", league_fa="NFL", league_en="NFL", event_id="1") is None

    # 2. ESPN Standings parser + deterministic Monte Carlo odds
    fake_st = {
        "children": [{
            "standings": {
                "entries": [
                    {
                        "team": {"displayName": name, "abbreviation": code},
                        "stats": [
                            {"name": "gamesPlayed", "value": 10},
                            {"name": "wins", "value": 10 - i},
                            {"name": "ties", "value": i % 2},
                            {"name": "losses", "value": i},
                            {"name": "pointsFor", "value": 25 - i * 2},
                            {"name": "pointsAgainst", "value": 8 + i * 2},
                            {"name": "points", "value": (10 - i) * 3 + (i % 2)},
                        ],
                    }
                    for i, (name, code) in enumerate([
                        ("Arsenal", "ARS"), ("Liverpool", "LIV"), ("Manchester City", "MCI"),
                        ("Chelsea", "CHE"), ("Aston Villa", "AVL"), ("Everton", "EVE"),
                    ])
                ]
            }
        }]
    }
    parsed_st = parse_espn_standings(fake_st, STANDINGS_LEAGUE_SPECS[0])
    assert parsed_st is not None and len(parsed_st["teams"]) == 6
    assert parsed_st["teams"][0]["code"] == "ARS"
    assert parsed_st["teams"][0]["xpts"] is None  # null != 0 when Understat not provided
    assert parsed_st["teams"][0]["titleP"] is None  # no simulated Monte Carlo

    # 3. FPL Injuries & Top Players parsers
    fake_bs = {
        "teams": [
            {"id": 1, "name": "Arsenal", "short_name": "ARS"},
            {"id": 2, "name": "Chelsea", "short_name": "CHE"},
        ],
        "elements": [
            {
                "id": 7, "team": 1, "element_type": 3, "first_name": "Bukayo", "second_name": "Saka",
                "web_name": "Saka", "status": "i", "news": "Hamstring injury - Expected back 15 Dec",
                "chance_of_playing_next_round": 25, "selected_by_percent": "38.5", "minutes": 900,
                "starts": 10, "goals_scored": 6, "assists": 7, "expected_goals": "4.8",
                "expected_assists": "4.1", "expected_goal_involvements": "8.9", "creativity": "420",
                "threat": "390", "influence": "380", "ict_index": "119", "bps": 240, "now_cost": 102, "total_points": 78,
            },
            {
                "id": 11, "team": 1, "element_type": 3, "first_name": "Gabriel", "second_name": "Martinelli",
                "web_name": "Martinelli", "status": "a", "news": "", "selected_by_percent": "12.0",
                "minutes": 720, "starts": 8, "goals_scored": 4, "assists": 3, "expected_goals": "3.2",
                "expected_assists": "2.1", "expected_goal_involvements": "5.3", "creativity": "250",
                "threat": "310", "influence": "240", "ict_index": "80", "bps": 170, "now_cost": 70, "total_points": 52,
            },
        ],
    }
    injs = parse_fpl_injuries(fake_bs, [{"team_h": 1, "team_a": 2, "finished": False, "team_h_difficulty": 4, "team_a_difficulty": 4}])
    assert len(injs) == 1
    assert injs[0]["injury"]["zone"] == "hamstring"
    assert injs[0]["impact"] is None and injs[0]["history"] is None  # null != 0
    assert len(injs[0]["replacements"]) == 1

    players = parse_fpl_top_players(fake_bs)
    assert len(players) == 2
    assert players[0]["code"] == "ARS"
    assert players[0]["shots"] is None  # null != 0
    assert len(players[0]["similar"]) == 1

    # Offline fallback enrichment
    enr_inj = enrich_injury_item(injs[0], fetch_network=False)
    assert enr_inj["verdict"] and enr_inj["verdict"]["body"]
    enr_pl = enrich_player_profile(players[0], fetch_network=False)
    assert enr_pl["scout"] and enr_pl["scout"]["body"]
    enr_pr = enrich_players_rating_match(load_players_rating_presets()[0], fetch_network=False)
    assert enr_pr["verdict"] and enr_pr["verdict"]["body"]


def test_layout_templates_and_telegram_hashtags_for_all_4_cards() -> None:
    for ctype in ("players_rating", "standings", "injury_lab", "player_profile"):
        # Clean existing if any
        while list_layout_templates(ctype):
            delete_layout_template(ctype, 0)
        mods = [
            {"id": "m1", "enabled": True, "span": "half", "can_half": True},
            {"id": "m2", "enabled": True, "span": "full", "can_half": False},
        ]
        saved = save_layout_template(ctype, "قالب تست", fmt="9:16", header_mode="compact", modules=mods)
        assert saved["name"] == "قالب تست"
        tpls = list_layout_templates(ctype)
        assert len(tpls) == 1
        applied = apply_template_to_modules(mods, tpls[0])
        assert applied[0]["span"] == "half"
        assert delete_layout_template(ctype, 0) is True

        tags = tp._build_relevant_hashtags({"post_type": ctype, "title": "آرسنال لیگ برتر", "caption": ""}, {}, {})
        assert "#XGPedia" in tags and "#فوتبال" in tags
        assert tp.HASHTAG_BY_TYPE[ctype] in tags


def test_v311_user_feedback_fixes() -> None:
    from datetime import datetime, timedelta, timezone
    from src.xgpedia.providers.players_rating_free import is_finished_within_24h, parse_espn_scoreboard_finished_24h
    from src.xgpedia.providers.injury_free import parse_fpl_injuries
    from src.xgpedia.providers.player_profile_free import parse_fpl_top_players

    # 1. Exact unified 4-corner red frame padding across ALL 4 cards (24px 0 20px for 4:5, 139px 0 171px for 9:16)
    h_pr = render_players_rating_html(load_players_rating_presets()[0], fmt="4:5")
    h_st = render_standings_html(load_standings_presets()[0], fmt="4:5")
    h_in = render_injury_html(load_injury_presets()[0], fmt="4:5")
    h_pl = render_player_html(load_player_profile_presets()[0], fmt="4:5")
    for h_out in (h_pr, h_st, h_in, h_pl):
        assert "padding:24px 0 20px" in h_out
        assert "padding:12px 36px 8px" in h_out
        assert "padding:10px 44px 10px" in h_out

    # 2. Standings: NO Monte Carlo 10K in header, YES glowing last form match (.fdot.fW.fl)
    assert "MONTE CARLO" not in h_st.upper()
    assert "مونت‌کارلو" not in h_st
    assert ".fdot.fW.fl" in h_st and "box-shadow:0 0 12px" in h_st

    # 3. Players Rating 1s..24h finished window
    now = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)
    # Kickoff 3 hours ago -> ended ~1h05m ago -> VALID
    ok1, _ = is_finished_within_24h((now - timedelta(hours=3)).isoformat(), now_utc=now)
    assert ok1 is True
    # Kickoff 40 hours ago -> ended ~38h ago -> INVALID (>24h)
    ok2, _ = is_finished_within_24h((now - timedelta(hours=40)).isoformat(), now_utc=now)
    assert ok2 is False
    # Future kickoff -> INVALID
    ok3, _ = is_finished_within_24h((now + timedelta(hours=2)).isoformat(), now_utc=now)
    assert ok3 is False

    # 4. Injury & Player Profile: NEVER fake jersey number (id % 99), NEVER show FPL budget as real market value
    bs = {
        "teams": [{"id": 1, "name": "Man City", "short_name": "MCI"}],
        "elements": [{
            "id": 15, "code": 223094, "team": 1, "element_type": 4,
            "first_name": "Erling", "second_name": "Haaland", "web_name": "Haaland",
            "squad_number": None, "status": "d", "news": "Knock - 75% chance",
            "chance_of_playing_next_round": 75, "selected_by_percent": "60.0",
            "minutes": 979, "starts": 11, "goals_scored": 9, "assists": 0,
            "expected_goals": "8.0", "expected_assists": "0.9", "expected_goal_involvements": "8.9",
            "creativity": "68", "threat": "486", "influence": "347", "ict_index": "90", "bps": 320,
            "now_cost": 158, "total_points": 80,
        }],
    }
    inj_items = parse_fpl_injuries(bs, [])
    assert inj_items[0]["player"]["number"] is None
    assert inj_items[0]["fpl_code"] == 223094

    pl_items = parse_fpl_top_players(bs)
    assert pl_items[0]["number"] is None
    assert pl_items[0]["value"] is None  # FPL 15.8M is NOT real transfer market value
    h_live_pl = render_player_html(pl_items[0], fmt="4:5")
    assert "#15" not in h_live_pl
    assert "FPL£" not in h_live_pl
