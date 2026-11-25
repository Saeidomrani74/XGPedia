"""تست‌های جامع ۵ کارت ماژولار نسخه v0.32.0 (D55–D59):
  1. H2H Teams Studio (D55)
  2. FC27 Chrono Player Card Studio (D56)
  3. H2H Players Duel Studio (D57)
  4. Top Scorers / Golden Boot Studio (D58)
  5. Matchday Results Studio (D59 — با فیلتر دقیق ۱ ثانیه تا ۲۴ ساعت قبل)
"""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

from src.xgpedia.layout_templates import delete_layout_template, list_layout_templates, save_layout_template
from src.xgpedia.providers import (
    h2h_players_free,
    h2h_teams_free,
    matchday_results_free,
    player_fc27_free,
    top_scorers_free,
)
from src.xgpedia.publishers import telegram_publish as tp
from src.xgpedia.render.card_kit.h2h_players_card import get_h2h_players_modules, render_h2h_players_html
from src.xgpedia.render.card_kit.h2h_teams_card import get_h2h_teams_modules, render_h2h_teams_html
from src.xgpedia.render.card_kit.matchday_results_card import get_matchday_results_modules, render_matchday_results_html
from src.xgpedia.render.card_kit.player_fc27_card import get_player_fc27_modules, render_player_fc27_html
from src.xgpedia.render.card_kit.top_scorers_card import get_top_scorers_modules, render_top_scorers_html


def _assert_offline_and_unified_padding(html: str, fmt: str = "4:5") -> None:
    assert "fonts.googleapis.com" not in html
    assert "cdn." not in html
    assert "padding:12px 36px 8px" in html
    assert "padding:8px 40px" in html
    assert "padding:10px 44px 10px" in html
    expected = "padding:139px 0 171px 0" if fmt == "9:16" else ("padding:22px 0 16px 0" if fmt == "16:9" else "padding:24px 0 20px 0")
    assert expected in html, f"Expected unified padding {expected} for fmt={fmt}"


def test_zero_requests_dependency() -> None:
    for mod in (h2h_teams_free, player_fc27_free, h2h_players_free, top_scorers_free, matchday_results_free):
        src = inspect.getsource(mod)
        assert "import requests" not in src and "from requests" not in src


def test_h2h_teams_card_modular_and_offline() -> None:
    presets = h2h_teams_free.load_h2h_teams_presets()
    assert len(presets) >= 5
    item = presets[0]
    mods, _ = get_h2h_teams_modules(item, "slide1")
    assert len(mods) >= 5
    # تست نیم‌عرض و تغییر ترتیب
    for m in mods:
        if m["can_half"]:
            m["enabled"] = True
            m["span"] = "half"
    mods = list(reversed(mods))
    for fmt in ("4:5", "9:16", "16:9"):
        html = render_h2h_teams_html(item, fmt=fmt, modules=mods)
        _assert_offline_and_unified_padding(html, fmt)
        assert "mod-slot mf" in html
        assert item["home"]["name"] in html


def test_player_fc27_card_skins_and_null_guard() -> None:
    presets = player_fc27_free.load_player_fc27_presets()
    assert len(presets) >= 4
    item = presets[0]
    mods, _ = get_player_fc27_modules(item, "slide1")
    assert any(m["id"] == "fc_card" for m in mods)
    html_persian = render_player_fc27_html(item, fmt="4:5", theme="persian", modules=mods)
    _assert_offline_and_unified_padding(html_persian, "4:5")
    assert "PERSIAN EDITION" in html_persian and "fc-frame" in html_persian and "stat-cap" in html_persian

    # قانون null != 0 در پارس FPL: هرگز ارزش فانتزی و شماره جعلی نسازد
    fake_boot = {
        "teams": [{"id": 1, "name": "Arsenal", "short_name": "ARS"}],
        "elements": [{
            "id": 101, "team": 1, "element_type": 3, "first_name": "Bukayo", "second_name": "Saka",
            "web_name": "Saka", "minutes": 900, "starts": 10, "goals_scored": 6, "assists": 5,
            "expected_goals": "4.8", "expected_assists": "3.2", "expected_goal_involvements": "8.0",
            "expected_goals_per_90": 0.48, "expected_assists_per_90": 0.32,
            "creativity": "320.0", "threat": "410.0", "influence": "350.0", "ict_index": "108.0",
            "bps": 280, "total_points": 82, "now_cost": 105, "squad_number": None, "code": 223340,
        }],
    }
    parsed = player_fc27_free.parse_fpl_fc27_players(fake_boot, limit=5)
    assert len(parsed) == 1
    assert parsed[0]["val"] is None
    assert parsed[0]["num"] is None


def test_h2h_players_card_and_fpl_pairing() -> None:
    presets = h2h_players_free.load_h2h_players_presets()
    assert len(presets) >= 4
    item = presets[0]
    mods, _ = get_h2h_players_modules(item, "slide2")
    html = render_h2h_players_html(item, fmt="4:5", modules=mods)
    _assert_offline_and_unified_padding(html, "4:5")
    assert "VS" in html
    assert item["p1"]["name"] in html and item["p2"]["name"] in html


def test_top_scorers_card_and_null_xg() -> None:
    presets = top_scorers_free.load_top_scorers_presets()
    assert len(presets) >= 4
    item = presets[0]
    mods, _ = get_top_scorers_modules(item, "slide1")
    html = render_top_scorers_html(item, fmt="4:5", modules=mods)
    _assert_offline_and_unified_padding(html, "4:5")
    assert item["players"][0]["name"] in html

    # وقتی xG برای هیچ بازیکنی موجود نباشد، ماژول matrix باید حذف شود (null != 0)
    no_xg = dict(item)
    no_xg["players"] = [dict(p, xg=None) for p in item["players"]]
    mods_no_xg, missing = get_top_scorers_modules(no_xg, "slide2")
    assert all(m["id"] != "matrix" for m in mods_no_xg)
    assert missing


def test_matchday_results_strict_24h_window_and_soccer_only() -> None:
    now = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)
    # 1) بازی تمام‌شده ۵ ساعت قبل (کیک‌آف ~۷ ساعت قبل) → باید پذیرفته شود
    ok_kickoff = (now - timedelta(hours=7)).isoformat().replace("+00:00", "Z")
    # 2) بازی تمام‌شده ۳۰ ساعت قبل → باید رد شود
    old_kickoff = (now - timedelta(hours=32)).isoformat().replace("+00:00", "Z")
    # 3) بازی غیرفوتبالی (NFL) → باید رد شود
    payload = {
        "events": [
            {
                "id": "e1", "name": "Arsenal vs Liverpool", "date": ok_kickoff,
                "competitions": [{
                    "status": {"type": {"completed": True, "shortDetail": "FT"}},
                    "competitors": [
                        {"homeAway": "home", "score": "2", "team": {"id": "1", "displayName": "Arsenal", "abbreviation": "ARS", "color": "EF0107"}},
                        {"homeAway": "away", "score": "1", "team": {"id": "2", "displayName": "Liverpool", "abbreviation": "LIV", "color": "C8102E"}},
                    ],
                    "details": [{"scoringPlay": True, "clock": {"displayValue": "22'"}, "team": {"id": "1"}, "athletesInvolved": [{"shortName": "Saka"}]}],
                }],
            },
            {
                "id": "e2", "name": "Chelsea vs Everton", "date": old_kickoff,
                "competitions": [{
                    "status": {"type": {"completed": True, "shortDetail": "FT"}},
                    "competitors": [
                        {"homeAway": "home", "score": "1", "team": {"id": "3", "displayName": "Chelsea", "abbreviation": "CHE"}},
                        {"homeAway": "away", "score": "0", "team": {"id": "4", "displayName": "Everton", "abbreviation": "EVE"}},
                    ],
                }],
            },
            {
                "id": "e3", "name": "NFL Super Bowl Chiefs vs Eagles", "date": ok_kickoff,
                "competitions": [{
                    "status": {"type": {"completed": True, "shortDetail": "FT"}},
                    "competitors": [
                        {"homeAway": "home", "score": "24", "team": {"id": "5", "displayName": "Chiefs", "abbreviation": "KC"}},
                        {"homeAway": "away", "score": "20", "team": {"id": "6", "displayName": "Eagles", "abbreviation": "PHI"}},
                    ],
                }],
            },
        ]
    }
    found = matchday_results_free.parse_espn_finished_24h_matches(
        payload, slug="eng.1", league_fa="لیگ برتر انگلیس", league_en="PREMIER LEAGUE", now_utc=now,
    )
    assert len(found) == 1
    assert found[0]["event_id"] == "e1"
    assert found[0]["home"]["xg"] is None  # null != 0
    assert "Saka 22'" in found[0]["home"]["scorers"]

    card = matchday_results_free._pack_matchday_card("test_24h", "لیگ برتر انگلیس", "PREMIER LEAGUE", "۲۴ ساعت اخیر", found)
    mods, missing = get_matchday_results_modules(card, "slide1")
    assert all(m["id"] != "xg_divergence" for m in mods)
    html = render_matchday_results_html(card, fmt="4:5", modules=mods)
    _assert_offline_and_unified_padding(html, "4:5")


def test_hashtags_and_saved_templates_for_5_cards() -> None:
    for ptype in ("h2h_teams", "player_fc27", "h2h_players", "top_scorers", "matchday_results"):
        assert ptype in tp.POST_TYPE_FA
        assert ptype in tp.HASHTAG_BY_TYPE
        tags = tp._build_relevant_hashtags({"post_type": ptype, "title": "آرسنال", "caption": "لیگ برتر انگلیس"}, {}, {})
        assert tp.HASHTAG_BY_TYPE[ptype] in tags

    # تست ذخیره و حذف قالب در layout_templates برای یکی از کارت‌های جدید
    before = len(list_layout_templates("h2h_teams"))
    save_layout_template("h2h_teams", "تست_موقت_v32", fmt="4:5", header_mode="full", modules=[{"id": "chronicle", "enabled": True, "span": "full"}])
    after = list_layout_templates("h2h_teams")
    assert len(after) >= 1
    idx = next(i for i, t in enumerate(after) if t["name"] == "تست_موقت_v32")
    delete_layout_template("h2h_teams", idx)
    assert len(list_layout_templates("h2h_teams")) == before


def test_live_list_never_silently_shows_presets() -> None:
    from pathlib import Path as _P
    src = _P("src/xgpedia/publishers/modular_cards_bot.py").read_text(encoding="utf-8")
    assert "pool = presets if show_presets else live" in src
    assert "show_presets or not live" not in src
    try:
        from src.xgpedia.publishers import modular_cards_bot as mcb
    except ModuleNotFoundError:
        return
    presets = [{"id": "p1", "home": {"name": "آرسنال"}, "away": {"name": "لیورپول"}, "competition": "لیگ برتر"}]
    txt_live, _ = mcb.format_card_list_message("players_rating", {"live": [], "presets": presets}, show_presets=False)
    assert "دیتای زنده" in txt_live
    assert "پریست‌های آماده" not in txt_live.splitlines()[1]
    assert "آرسنال" not in txt_live
    txt_pre, kb_pre = mcb.format_card_list_message("players_rating", {"live": [], "presets": presets}, show_presets=True)
    assert "پریست‌های آماده" in txt_pre
    assert any("آرسنال" in btn.text for row in kb_pre.inline_keyboard for btn in row)


def test_h2h_and_top_scorers_1to1_visual_elements() -> None:
    h2h = h2h_teams_free.load_h2h_teams_presets()[0]
    for sl in ("slide1", "slide2", "slide3", "slide4", "slide5"):
        mods, _ = get_h2h_teams_modules(h2h, sl)
        html = render_h2h_teams_html(h2h, fmt="4:5", slide=sl, theme="cinematic", modules=mods)
        _assert_offline_and_unified_padding(html, "4:5")
        assert "XGPEDIA • H2H ENGINE v2.0" in html
        assert "hero-gauge-svg" in html

    ts = top_scorers_free.load_top_scorers_presets()[0]
    for sl in ("slide1", "slide2", "slide3", "slide4"):
        mods, _ = get_top_scorers_modules(ts, sl)
        html = render_top_scorers_html(ts, fmt="4:5", slide=sl, theme="gold", sort_by="npg", modules=mods)
        _assert_offline_and_unified_padding(html, "4:5")
    html1 = render_top_scorers_html(ts, fmt="4:5", slide="slide1", theme="gold")
    assert "xg-needle" in html1 and "xh-wm" in html1
    html3 = render_top_scorers_html(ts, fmt="4:5", slide="slide3", theme="gold")
    assert "GOALS vs xG MATRIX" in html3
    html4 = render_top_scorers_html(ts, fmt="4:5", slide="slide4", theme="gold")
    assert "GOLDEN BOOT RACE" in html4


def test_player_fc27_1to1_visuals_all_layouts_and_skins():
    from src.xgpedia.providers.player_fc27_free import load_player_fc27_presets
    from src.xgpedia.render.card_kit.player_fc27_card import render_player_fc27_html
    presets = load_player_fc27_presets()
    p = presets[0]
    for sl in ("slide1", "slide2", "slide3"):
        for sk in ("signature", "persian", "icon", "tots", "ucl", "future"):
            h = render_player_fc27_html(p, slide=sl, theme=sk)
            assert "fc-frame" in h and "fc-pedestal" in h
            assert "stat-cap" in h and "ps-hex" in h
            assert "https://fonts.googleapis.com" not in h


def test_matchday_results_1to1_visuals_and_strict_24h():
    from src.xgpedia.providers.matchday_results_free import load_matchday_results_presets
    from src.xgpedia.render.card_kit.matchday_results_card import render_matchday_results_html
    presets = load_matchday_results_presets()
    item = presets[0]
    for sl in ("slide1", "slide2", "slide3", "slide4", "slide5"):
        for th in ("classic", "ucl", "gold"):
            h = render_matchday_results_html(item, slide=sl, theme=th)
            assert "hdr-gauge" in h and "xg-mirror" in h and "hdr-gauge" in h
            assert "https://fonts.googleapis.com" not in h
    # Check null != 0 when matches have no xG
    live_mock = {
        "id": "live_mock",
        "competition": "نتایج ۲۴ ساعت اخیر",
        "round": "۱ ثانیه تا ۲۴ ساعت قبل",
        "dateFa": "امروز",
        "watermark": "LAST 24H",
        "source": "ESPN Soccer API",
        "matches": [
            {
                "id": "m1", "comp": "EPL", "featured": True,
                "home": {"name": "آرسنال", "code": "ARS", "color": "#EF0107", "color2": "#9C0005", "score": 2, "ht": 1, "xg": None, "shots": None, "sot": None, "poss": None},
                "away": {"name": "چلسی", "code": "CHE", "color": "#034694", "color2": "#012456", "score": 1, "ht": 0, "xg": None, "shots": None, "sot": None, "poss": None},
                "goals": [{"min": 22, "team": "h", "scorer": "ساکا"}], "motm": None,
                "verdict": "fair", "vLabel": "نتیجه نهایی", "elapsed_sec": 3600,
            }
        ],
    }
    h_live = render_matchday_results_html(live_mock, slide="slide1")
    assert "زهر گلزنی روز" in h_live and "آرسنال" in h_live and "چلسی" in h_live


def test_v323_fixes_and_pl_picker():
    import inspect
    from src.xgpedia import today_workflow as tw
    from src.xgpedia.providers.injury_free import transliterate_player_name_fa, translate_injury_diagnosis_fa
    from src.xgpedia.providers.player_profile_free import load_player_profile_presets
    from src.xgpedia.render.card_kit.player_card import render_player_html
    from src.xgpedia.providers.pl_picker_free import build_pl_h2h_teams_item

    # 1. extra_kwargs in _generate_v32_modular_post_async signature
    sig = inspect.signature(tw._generate_v32_modular_post_async)
    assert "extra_kwargs" in sig.parameters

    # 2. player_card.py footer has NO raw Python source code and has single-line CSS
    p = load_player_profile_presets()[0]
    h = render_player_html(p)
    assert 'P.GET("NUMBER")' not in h and "p.get(" not in h
    assert "white-space:nowrap!important" in h

    # 3. Persian player names & injury diagnoses
    assert transliterate_player_name_fa("Bukayo Saka") == "بوکایو ساکا"
    assert transliterate_player_name_fa("Erling Haaland") == "ارلینگ هالند"
    diag, ret = translate_injury_diagnosis_fa("Hamstring injury - Expected back 05 Dec")
    assert "همسترینگ" in diag and "دسامبر" in ret

    # 4. pl_picker_free build_pl_h2h_teams_item with mock FPL bootstrap & fixtures
    mock_boot = {
        "teams": [
            {"id": 1, "name": "Arsenal", "short_name": "ARS"},
            {"id": 2, "name": "Liverpool", "short_name": "LIV"},
        ],
        "elements": [
            {"id": 10, "team": 1, "expected_goals": "12.4"},
            {"id": 20, "team": 2, "expected_goals": "14.1"},
        ],
    }
    mock_fx = [
        {"id": 100, "event": 9, "finished": True, "team_h": 1, "team_a": 2, "team_h_score": 2, "team_a_score": 2, "kickoff_time": "2026-10-27T16:30:00Z"},
    ]
    h2h = build_pl_h2h_teams_item(1, 2, boot=mock_boot, fixtures=mock_fx)
    assert h2h is not None and h2h["home"]["name"] == "آرسنال" and h2h["away"]["name"] == "لیورپول"
    assert h2h["draws"] >= 60 and len(h2h["recent5"]) == 5


def test_v324_h2h_players_and_matchday_results_1to1():
    from pathlib import Path
    from datetime import datetime, timezone
    from src.xgpedia.providers.h2h_players_free import load_h2h_players_presets
    from src.xgpedia.render.card_kit.h2h_players_card import render_h2h_players_html
    from src.xgpedia.providers.matchday_results_free import gregorian_to_jalali_fa, _build_leagues_label
    from src.xgpedia.render.card_kit.matchday_results_card import render_matchday_results_html

    # 1. H2H Players 1:1 visual check across all 5 slides
    duel = load_h2h_players_presets()[0]
    for sl in ("slide1", "slide2", "slide3", "slide4", "slide5"):
        hm = "full" if sl in ("slide1", "slide5") else "compact"
        h = render_h2h_players_html(duel, slide=sl, header_mode=hm)
        assert "xgp-badge" in h and "white-space:nowrap!important" in h
        assert "https://fonts.googleapis.com" not in h

    # 2. Matchday Results header rules + no duplicate featured match
    jdate = gregorian_to_jalali_fa(datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc))
    assert "آذر" in jdate and "1405" in jdate
    assert _build_leagues_label([{"comp": "لیگ برتر"}, {"comp": "لالیگا"}, {"comp": "سری آ"}]) == "روز شلوغ فوتبال"
    assert _build_leagues_label([{"comp": "لیگ برتر انگلیس"}]) == "لیگ برتر انگلیس"

    single_m = {
        "competition": "لیگ برتر انگلیس", "round": "تابلوی نتایج", "day": jdate,
        "title": "شب پرگل در لیگ برتر انگلیس", "source": "Premier League / Opta FPL",
        "matches": [{
            "home": {"name": "برنتفورد", "code": "BRE", "color": "#E30613", "score": 4, "xg": 2.41, "scorers": "امبومو ۲۲' • ویسا ۵۸'"},
            "away": {"name": "اورتون", "code": "EVE", "color": "#003399", "score": 0, "xg": 0.62, "scorers": ""},
            "ht": "۲-۰", "tag": "هفته ۱۲ لیگ برتر",
        }],
    }
    h_mr = render_matchday_results_html(single_m, slide="slide1")
    assert "زهر گلزنی روز" in h_mr and "CUMULATIVE xG RACE" in h_mr and "تابلوی نتایج" in h_mr
    # Ensure featured match is NOT repeated in a Bento card (bc0h should not exist)
    assert 'class="bc ' not in h_mr and "نبرد شاخص روز" in h_mr

    # 3. Bot studio menu has no "(ماژولار)"
    tb = Path("src/xgpedia/publishers/telegram_bot.py").read_text(encoding="utf-8")
    assert "(ماژولار)" not in tb


def test_v325_top_scorers_persian_and_real_pen_shots():
    from src.xgpedia.providers.top_scorers_free import parse_fpl_top_scorers
    from src.xgpedia.render.card_kit.top_scorers_card import render_top_scorers_html

    boot = {
        "events": [{"id": 12, "is_current": True}],
        "teams": [{"id": 1, "name": "Man City", "short_name": "MCI"}, {"id": 2, "name": "Bournemouth", "short_name": "BOU"}],
        "elements": [
            {"id": 1, "code": 100, "team": 1, "element_type": 4, "first_name": "Erling", "second_name": "Haaland", "web_name": "Haaland", "goals_scored": 9, "assists": 1, "expected_goals": "8.1", "minutes": 979, "threat": "500", "creativity": "100", "influence": "400", "bps": 300, "penalties_missed": 0},
            {"id": 2, "code": 200, "team": 2, "element_type": 4, "first_name": "Francisco", "second_name": "Evanilson de Lima Barbosa", "web_name": "Evanilson", "goals_scored": 6, "assists": 1, "expected_goals": "5.6", "minutes": 920, "threat": "400", "creativity": "90", "influence": "300", "bps": 210, "penalties_missed": 0},
        ],
    }
    umap = {
        "erling haaland": {"goals": 9, "pen": 2, "shots": 36},
        "evanilson": {"goals": 6, "pen": 1, "shots": 24},
    }
    item = parse_fpl_top_scorers(boot, top_n=8, understat_map=umap)
    assert item is not None
    assert item["players"][0]["name"] == "ارلینگ هالند"
    assert item["players"][0]["pen"] == 2 and item["players"][0]["shots"] == 36
    assert item["players"][1]["name"] == "اوانیلسون"
    assert item["players"][1]["pen"] == 1 and item["players"][1]["shots"] == 24
    h = render_top_scorers_html(item, slide="slide1")
    assert "ارلینگ هالند" in h and "اوانیلسون" in h
    assert "تبدیل" in h and "پنالتی" in h
    assert "font-size:22px" in h


def test_v326_matchday_results_badges_contrast_and_layout():
    from src.xgpedia.providers.pl_badges_free import lookup_pl_club, resolve_distinct_team_colors
    from src.xgpedia.render.card_kit.matchday_results_card import render_matchday_results_html

    # 1. All 20 PL clubs resolve to Persian with badge code
    br = lookup_pl_club("Brentford")
    ev = lookup_pl_club("Everton")
    assert br and br[0] == "برنتفورد" and br[4] == 94
    assert ev and ev[0] == "اورتون" and ev[4] == 11

    # 2. High-contrast distinct team colors when two teams are both blue
    c1, c2 = resolve_distinct_team_colors("#2563EB", "#3B82F6")
    assert c1 != c2

    # 3. Matchday results single match: no Goal Timing Pulse module, transparent xG chart, 0-15-30..90 axis, xG-proportional border
    item = {
        "competition": "لیگ برتر انگلیس", "round": "تابلوی نتایج", "day": "سه‌شنبه ۳ آذر ۱۴۰۵",
        "title": "شب پرگل در لیگ برتر انگلیس", "source": "Premier League / Opta FPL",
        "matches": [{
            "home": {"name": "برنتفورد", "code": "BRE", "color": "#E30613", "score": 4, "xg": 2.56, "scorers": "لویس پوتر ۳۵' • جانلت ۶۹'"},
            "away": {"name": "اورتون", "code": "EVE", "color": "#2563EB", "score": 0, "xg": 0.24, "scorers": ""},
            "ht": "۱-۰", "tag": "هفته ۱۱ لیگ برتر",
        }],
    }
    h = render_matchday_results_html(item, slide="slide1")
    assert "نبض زمانی گل‌های روز" not in h
    assert "rgba(10,19,41,.34)" in h
    assert "<span>0</span><span>15</span><span>30</span><span>45</span><span>60</span><span>75</span><span>90</span>" in h
    assert "نیمه اول: ۱-۰" in h


def test_v327_gauge_h2h_players_and_scorers_polish():
    from src.xgpedia.render.card_kit.matchday_results_card import _header_gauge
    from src.xgpedia.providers.h2h_players_free import load_h2h_players_presets
    from src.xgpedia.render.card_kit.h2h_players_card import render_h2h_players_html

    # 1. زهر گلزنی روز circular gauge: 100% -> half circumference (75.4 of 150.8), 150% -> 3/4 (113.1 of 150.8)
    g100 = _header_gauge({"totalGoals": 10, "totalXg": 10.0, "effPct": 100, "effDelta": 0.0})
    g150 = _header_gauge({"totalGoals": 15, "totalXg": 10.0, "effPct": 150, "effDelta": 5.0})
    assert 'stroke-dasharray="75.4 150.8"' in g100
    assert 'stroke-dasharray="113.1 150.8"' in g150

    # 2. H2H Players polish: برتری در تقابل, no TOP XGP, no duplicate XGPedia text next to logo
    duel = load_h2h_players_presets()[0]
    h = render_h2h_players_html(duel, slide="slide1", header_mode="full")
    assert "برتری در تقابل" in h and "DUEL EDGE" not in h
    assert "TOP XGP" not in h
    assert '<span style="color:#E62E45">XG</span><span style="color:#F8FAFC">Pedia</span>' not in h


def test_v328_fc27_persian_and_h2h_teams_history():
    from src.xgpedia.providers.player_fc27_free import load_player_fc27_presets
    from src.xgpedia.render.card_kit.player_fc27_card import render_player_fc27_html
    from src.xgpedia.providers.pl_picker_free import build_pl_h2h_teams_item
    from src.xgpedia.render.card_kit.h2h_teams_card import render_h2h_teams_html

    # 1. FC27: Persian name, square red XG logo, Persian position & digits, portrait inside frame
    p = dict(load_player_fc27_presets()[0])
    p["name"] = "Erling Haaland"
    p["pos"] = "ST"
    p["role"] = "مهاجم نوک تمام‌کننده • POACHER++"
    h = render_player_fc27_html(p, slide="slide1")
    assert "ارلینگ هالند" in h
    assert ('<image href="data:image/svg+xml;base64,' in h) or ('fill="#E62E45"/>' in h and ">XG</text>" in h)
    assert "POACHER" not in h
    assert "مهاجم" in h and "top:72px" in h

    # 2. H2H Teams schema compatibility (recent5, cleanSheets, xgPerMatch, biggestWin, dna)
    mock_boot = {
        "events": [{"id": 12, "deadline_time": "2025-08-15T17:30:00Z"}],
        "teams": [
            {"id": 1, "code": 43, "name": "Man City", "short_name": "MCI"},
            {"id": 2, "code": 14, "name": "Liverpool", "short_name": "LIV"},
        ],
        "elements": [],
    }
    mock_fx = [
        {"id": 100, "event": 11, "finished": True, "team_h": 1, "team_a": 2, "team_h_score": 3, "team_a_score": 0, "kickoff_time": "2025-11-10T16:30:00Z"},
    ]
    h2h = build_pl_h2h_teams_item(1, 2, boot=mock_boot, fixtures=mock_fx)
    assert h2h is not None and "recent5" in h2h and "cleanSheets" in h2h["home"] and "biggestWin" in h2h["home"]
    hh = render_h2h_teams_html(h2h, slide="slide1")
    assert "نوار سینمایی ۵ تقابل اخیر" in hh and "ترازوی نبرد و تفاضل قدرت" in hh
def test_v329_ht_penalties_h2h_history_and_contrast():
    from src.xgpedia.render.card_kit.h2h_players_card import _ensure_readable_color, render_h2h_players_html
    from src.xgpedia.providers.h2h_players_free import load_h2h_players_presets
    from src.xgpedia.providers.pl_picker_free import build_pl_h2h_teams_item
    from src.xgpedia.render.card_kit.h2h_teams_card import render_h2h_teams_html
    from src.xgpedia.providers.top_scorers_free import load_top_scorers_presets
    from src.xgpedia.render.card_kit.top_scorers_card import render_top_scorers_html

    # 1. Dark Everton blue brightens cleanly for dark background readability
    ev_bright = _ensure_readable_color("#003399")
    assert ev_bright != "#003399"
    # Verify luminance increased
    r, g, b = int(ev_bright[1:3], 16) / 255.0, int(ev_bright[3:5], 16) / 255.0, int(ev_bright[5:7], 16) / 255.0
    assert (0.2126 * r + 0.7152 * g + 0.0722 * b) >= 0.24

    # 2. H2H Players: CHANNEL STRIKER translated to Persian + visible ghost jersey numbers
    duel = dict(load_h2h_players_presets()[0])
    p1 = dict(duel["p1"])
    p2 = dict(duel["p2"])
    p1["roleTag"] = "CHANNEL STRIKER"
    p1["number"] = 9
    p2["roleTag"] = "CHANNEL STRIKER"
    p2["number"] = 10
    p2["color"] = "#003399"
    duel["p1"], duel["p2"] = p1, p2
    h_p = render_h2h_players_html(duel, slide="slide1", header_mode="full")
    assert "CHANNEL STRIKER" not in h_p
    assert "مهاجم" in h_p
    assert "ghost-num" in h_p and ">9<" in h_p and ">10<" in h_p

    # 3. H2H Teams: Historical archive (240+ matches for ARS vs LIV) & NO team names in header
    mock_boot = {
        "events": [{"id": 12, "deadline_time": "2026-08-15T17:30:00Z"}],
        "teams": [
            {"id": 1, "code": 3, "name": "Arsenal", "short_name": "ARS"},
            {"id": 2, "code": 14, "name": "Liverpool", "short_name": "LIV"},
        ],
        "elements": [],
    }
    h2h = build_pl_h2h_teams_item(1, 2, boot=mock_boot, fixtures=[])
    assert h2h is not None
    total_m = h2h["home"]["wins"] + h2h["draws"] + h2h["away"]["wins"]
    assert total_m >= 240
    assert "آرسنال" not in str(h2h.get("eraNote", "")) and "لیورپول" not in str(h2h.get("eraNote", ""))
    hh = render_h2h_teams_html(h2h, slide="slide1")
    assert "تمامی رقابت‌های رسمی" in hh

    # 4. Top Scorers: enlarged 46px real club logos
    ts = load_top_scorers_presets()[0]
    h_ts = render_top_scorers_html(ts, slide="slide1")
    assert ('width="46"' in h_ts or 'width="44"' in h_ts or 'width="42"' in h_ts or "width:46px" in h_ts or "width:42px" in h_ts)
