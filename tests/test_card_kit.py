"""آزمون‌های معماری یکپارچه و ماژولار کارت‌ها (`card_kit`) + هدر کامل + نیم‌عرض/تمام‌عرض."""
from __future__ import annotations

from src.xgpedia.config import team_venue
from src.xgpedia.render.card_kit import MODULE_REGISTRY, render_unified_card_html
from src.xgpedia.render.cards import build_preview_context, render_preview_html
from src.xgpedia.render.post_match_cards import render_post_match_html


def _rich_pre_facts() -> dict:
    return {
        "fixture_id": "fdo:555",
        "competition": {"name": "Premier League", "season": "2026-27"},
        "matchday": 12,
        "round": "هفته ۱۲ • پیش‌بازی آماری",
        "stadium": "ورزشگاه آنفیلد",
        "broadcast": "پخش زنده: شبکه سه",
        "kickoff_utc": "2026-11-22T16:30:00Z",
        "source": {"provider": "football-data-co-uk"},
        "market_odds": {"home": 1.95, "draw": 3.60, "away": 3.80, "over25": 1.80, "btts": 1.75},
        "home": {
            "name_fa": "لیورپول", "name_en": "Liverpool", "sub": "آرنه اسلوت",
            "xg_for_avg": {"value": 1.58, "n": 10}, "xg_against_avg": {"value": 0.85, "n": 10},
            "sot_avg": {"value": 6.2, "n": 10},
            "xg_series": [1.4, 1.8, 1.2, 1.9, 1.6, 1.5, 1.7, 1.4, 1.8, 1.58],
            "recent_form": {"sequence": "WLWWL", "n": 5},
            "radar": [87, 83, 68, 84, 91, 99],
            "kp": {"name": "محمد صلاح", "pos": "مهاجم", "s1": "1.05 xG+xA", "s2": "3.1 پاس کلیدی"},
        },
        "away": {
            "name_fa": "منچستریونایتد", "name_en": "Manchester United", "sub": "روبن آموریم",
            "xg_for_avg": {"value": 1.74, "n": 10}, "xg_against_avg": {"value": 1.02, "n": 10},
            "sot_avg": {"value": 5.8, "n": 10},
            "xg_series": [1.6, 2.1, 1.3, 1.5, 1.7, 1.4, 1.6, 1.5, 1.8, 1.74],
            "recent_form": {"sequence": "DDLLD", "n": 5},
            "radar": [80, 80, 91, 79, 87, 80],
            "kp": {"name": "برونو فرناندز", "pos": "هافبک", "s1": "0.88 xG+xA", "s2": "3.5 پاس کلیدی"},
        },
    }


def _draft() -> dict:
    return {"title": "نبرد آنفیلد", "bullets": ["نکته"], "caption": "پیش‌بازی حساس لیگ برتر."}


def test_unified_card_header_shows_round_stadium_broadcast_and_real_weekcode():
    html = render_preview_html(_draft(), _rich_pre_facts(), fmt="4:5")
    assert "هفته ۱۲ • پیش‌بازی آماری" in html
    assert "ورزشگاه آنفیلد" in html
    assert "پخش زنده: شبکه سه" in html
    assert "PREMIER LEAGUE 26/27 W12 • PRE-MATCH" in html
    assert "آرنه اسلوت" in html
    assert "روبن آموریم" in html
    assert "cdn.tailwindcss.com" not in html
    assert "fonts.googleapis.com" not in html


def test_all_svgs_use_meet_aspect_ratio_for_zero_clipping():
    """همهٔ SVGهای نموداری (رادار و روند ۱۰ بازی) در هر دو حالت نیم‌عرض و تمام‌عرض fit-svg و meet دارند."""
    custom_half = [{"id": "radar", "span": "half"}, {"id": "trend10", "span": "half"}]
    html_half = render_preview_html(_draft(), _rich_pre_facts(), fmt="4:5", custom_modules=custom_half)
    assert 'class="xm mod-half"' in html_half
    assert 'class="fit-svg"' in html_half
    assert 'preserveAspectRatio="xMidYMid meet"' in html_half
    # viewBox اختصاصی نیم‌عرض برای رادار (560x420) و روند (520x240)
    assert 'viewBox="0 0 560 420"' in html_half
    assert 'viewBox="0 0 540 260"' in html_half

    custom_full = [{"id": "radar", "span": "full"}, {"id": "trend10", "span": "full"}]
    html_full = render_preview_html(_draft(), _rich_pre_facts(), fmt="4:5", custom_modules=custom_full)
    assert 'class="xm mod-full"' in html_full
    assert 'viewBox="0 0 900 420"' in html_full
    assert 'viewBox="0 0 900 275"' in html_full


def test_orphan_half_auto_promoted_to_full():
    """تک ماژول نیم‌عرض بدون جفت، خودکار تمام‌عرض می‌شود تا نیم‌فضای خالی نماند."""
    ctx = build_preview_context(
        _draft(), _rich_pre_facts(), custom_modules=[{"id": "radar", "span": "half"}]
    )
    html = render_unified_card_html(ctx["studio_payload"])
    assert 'class="xm mod-full"' in html
    assert 'class="xm mod-half"' not in html


def test_all_formats_and_compact_header_render_cleanly():
    for fmt, (w, h) in (("4:5", (1080, 1350)), ("9:16", (1080, 1920)), ("16:9", (1920, 1080))):
        for hm in ("full", "compact"):
            html = render_preview_html(
                _draft(), _rich_pre_facts(), fmt=fmt, header_mode=hm,
                custom_modules=[{"id": "keyduel", "span": "half"}, {"id": "poisson", "span": "half"}, {"id": "signals", "span": "full"}],
            )
            assert f"width:{w}px;height:{h}px;" in html
            if hm == "compact":
                assert 'class="hero-compact"' in html
            else:
                assert 'class="hero-full"' in html


def test_post_match_uses_same_unified_navy_base_shell():
    pm_facts = _rich_pre_facts()
    pm_facts["result"] = {"home_goals": 2, "away_goals": 1}
    pm_facts["home"]["match_stats"] = {"expected_goals": {"value": 2.1}, "total_shots": {"value": 14}, "shots_on_target": {"value": 6}}
    pm_facts["away"]["match_stats"] = {"expected_goals": {"value": 1.1}, "total_shots": {"value": 9}, "shots_on_target": {"value": 3}}
    html = render_post_match_html(_draft(), pm_facts, fmt="4:5")
    assert "background:#0D1730" in html
    assert "PREMIER LEAGUE 26/27 W12 • POST-MATCH" in html
    assert "ورزشگاه آنفیلد" in html


def test_team_venues_covers_key_epl_teams():
    assert team_venue("Liverpool FC")["stadium_fa"] == "ورزشگاه آنفیلد"
    assert team_venue("Hull City AFC")["stadium_fa"] == "ورزشگاه MKM"
    from src.xgpedia.config import translate_coach_fa
    assert translate_coach_fa("Mikel Arteta") == "میکل آرتتا"
    assert "coach_fa" not in team_venue("Arsenal")
    assert "radar" in MODULE_REGISTRY and MODULE_REGISTRY["radar"].can_half is True
    assert "signals" in MODULE_REGISTRY and MODULE_REGISTRY["signals"].can_half is False
