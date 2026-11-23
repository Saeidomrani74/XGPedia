"""تست‌های نسخهٔ v0.24.0:
- رفع بنیادین باگ سرمربی قدیمی روی کارت (پارسر چندخطی Infobox ویکی‌پدیا، پشتیبان ساختاری Wikidata P286،
  به‌روزرسانی خودکار ۴ ساعته و لحظه‌ای `ensure_live_coaches_fresh` و `_refresh_live_coaches_on_facts`)
- ارتقای خوانایی و اندازهٔ فونت کارت‌های `card_kit` برای نمایشگر موبایل در تلگرام و اینستاگرام
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.xgpedia import db as db_mod
from src.xgpedia.providers import live_intel_free as lif
from src.xgpedia.render.card_kit.modules.post_modules import render_momentum, render_shotmap, render_xgrace
from src.xgpedia.render.card_kit.modules.radar import render_radar
from src.xgpedia.render.card_kit.modules.trend10 import render_trend10, render_wave
from src.xgpedia.render.cards import render_preview_html
from src.xgpedia.sync import ensure_live_coaches_fresh
from src.xgpedia.today_workflow import _refresh_live_coaches_on_facts


def test_parse_coach_from_multiline_ref_and_next_line_wikitext():
    wiki_multiline_ref = """
{{Infobox football club
| clubname = Manchester United
| ground   = [[Old Trafford]]
| manager  = [[Mauricio Pochettino]]<ref name="bbc">
  {{cite news |title=Man Utd appoint Pochettino |publisher=BBC Sport}}
</ref>
}}
"""
    assert lif.parse_coach_from_wikitext(wiki_multiline_ref) == "Mauricio Pochettino"

    wiki_next_line = """
{{Infobox football club
| head_coach =
  {{flagicon|ARG}} [[Mauricio Pochettino]] (head coach)
| league = [[Premier League]]
}}
"""
    assert lif.parse_coach_from_wikitext(wiki_next_line) == "Mauricio Pochettino"


def test_wikidata_p286_picks_active_coach_over_ended_previous():
    claims = {
        "P286": [
            {
                "rank": "normal",
                "mainsnak": {"datavalue": {"value": {"id": "Q111_OLD"}}},
                "qualifiers": {
                    "P580": [{"datavalue": {"value": {"time": "+2026-01-01T00:00:00Z"}}}],
                    "P582": [{"datavalue": {"value": {"time": "+2026-11-10T00:00:00Z"}}}],
                },
            },
            {
                "rank": "preferred",
                "mainsnak": {"datavalue": {"value": {"id": "Q222_NEW"}}},
                "qualifiers": {
                    "P580": [{"datavalue": {"value": {"time": "+2026-11-12T00:00:00Z"}}}],
                },
            },
        ]
    }
    assert lif.parse_coach_qid_from_wikidata_claims(claims) == "Q222_NEW"


def test_ensure_live_coaches_fresh_and_override_stale_card_coach(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "coach_fresh.db"
    monkeypatch.setattr(db_mod, "DATABASE_PATH", db_path)
    db_mod.init_db()

    # سناریوی واقعی باگ: football-data-org هنوز مایکل کریک را دارد و wikipedia-live قدیمی (۱۰ ساعت پیش) است
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with db_mod.db() as conn:
        conn.execute(
            "INSERT INTO team_metadata (team, season, venue_en, coach_en, provider, collected_at) "
            "VALUES ('Manchester United', '2026-27', 'Old Trafford', 'Michael Carrick', 'football-data-org', ?)",
            (stale_ts,),
        )

    calls: list[str] = []

    def _fake_wiki(team: str):
        calls.append(team)
        return ("Mauricio Pochettino", "مائوریسیو پوچتینو")

    monkeypatch.setattr(lif, "fetch_live_coach_wikipedia", _fake_wiki)

    facts = {
        "home": {"name_en": "Manchester United", "name_fa": "منچستریونایتد", "sub": "مایکل کریک"},
        "away": {"name_en": "Liverpool", "name_fa": "لیورپول", "sub": "آرنه اسلوت"},
    }
    _refresh_live_coaches_on_facts(facts)
    assert facts["home"]["sub"] == "مائوریسیو پوچتینو"
    assert "Manchester United" in calls

    # فراخوانی دوم در کمتر از ۴ ساعت نباید دوباره درخواست شبکه بزند
    prev_len = len(calls)
    res2 = ensure_live_coaches_fresh(["Manchester United"], season_start=2026, max_age_hours=4.0)
    assert len(calls) == prev_len
    assert res2["coaches_fa"]["Manchester United"] == "مائوریسیو پوچتینو"


def test_mobile_readability_font_upgrades_in_card_kit():
    facts = {
        "fixture_id": "fdo:777",
        "competition": {"name": "Premier League", "season": "2026-27"},
        "matchday": 12,
        "round": "هفته ۱۲ • نبرد سنگین‌وزن‌ها",
        "stadium": "الدترافورد",
        "broadcast": "پخش زنده: شبکه سه",
        "kickoff_utc": "2026-11-22T16:30:00Z",
        "source": {"provider": "football-data-co-uk"},
        "market_odds": {"home": 2.45, "draw": 3.55, "away": 2.95, "over25": 1.82, "btts": 1.74},
        "home": {
            "name_fa": "منچستریونایتد", "name_en": "Manchester United", "sub": "مائوریسیو پوچتینو",
            "xg_for_avg": {"value": 1.74, "n": 10}, "xg_against_avg": {"value": 1.02, "n": 10},
            "sot_avg": {"value": 5.8, "n": 10},
            "xg_series": [1.6, 2.1, 1.3, 1.5, 1.7, 1.4, 1.6, 1.5, 1.8, 1.74],
            "wave": [0.22, 0.28, 0.34, 0.30, 0.36, 0.42],
            "recent_form": {"sequence": "WWDWL", "n": 5},
            "radar": [80, 80, 91, 79, 87, 80],
            "kp": {"name": "برونو فرناندز", "pos": "هافبک", "s1": "0.88 xG+xA", "s2": "3.5 پاس کلیدی"},
        },
        "away": {
            "name_fa": "لیورپول", "name_en": "Liverpool", "sub": "آرنه اسلوت",
            "xg_for_avg": {"value": 1.58, "n": 10}, "xg_against_avg": {"value": 0.85, "n": 10},
            "sot_avg": {"value": 6.2, "n": 10},
            "xg_series": [1.4, 1.8, 1.2, 1.9, 1.6, 1.5, 1.7, 1.4, 1.8, 1.58],
            "wave": [0.25, 0.31, 0.29, 0.33, 0.35, 0.39],
            "recent_form": {"sequence": "WLWWL", "n": 5},
            "radar": [87, 83, 68, 84, 91, 99],
            "kp": {"name": "محمد صلاح", "pos": "مهاجم", "s1": "1.05 xG+xA", "s2": "3.1 پاس کلیدی"},
        },
    }
    draft = {"title": "نبرد اولدترافورد", "bullets": ["نکته"], "caption": "پیش‌بازی."}
    html = render_preview_html(
        draft,
        facts,
        fmt="4:5",
        custom_modules=[{"id": "radar", "span": "half"}, {"id": "trend10", "span": "half"}, {"id": "signals", "span": "full"}],
    )
    # بررسی ارتقای فونت‌های کلیدی برای خوانایی موبایل (تلگرام و اینستاگرام)
    assert ".team-sub{font-size:24px;" in html
    assert ".mh-title{font-size:28px;" in html
    assert ".et{font-size:26px;" in html
    assert ".em{font-size:21px;" in html
    assert ".evv{font-size:20px;" in html
    assert ".epb{width:100%;padding:3px 8px;border-radius:8px;display:inline-flex;align-items:baseline;justify-content:center;gap:4px;\n  font-size:28px;" in html

    # بررسی SVG ماژول‌ها (فونت‌های بزرگ‌تر بدون تغییر viewBoxهای استاندارد)
    payload_svg = {
        "match": {
            "weekCode": "W12",
            "home": {"name": "منچستریونایتد", "color": "#EF4444", "radar": [80]*6, "last10": [1.5]*10, "wave": [0.3]*6, "xg": 1.7, "shots": 12, "shotList": [(80, 50, 0.4, "goal", "A", 20)]},
            "away": {"name": "لیورپول", "color": "#38BDF8", "radar": [85]*6, "last10": [1.4]*10, "wave": [0.3]*6, "xg": 1.4, "shots": 10, "shotList": [(82, 45, 0.3, "sot", "B", 55)]},
            "momentum": [20, -15, 30, -10],
        }
    }
    rad_html = render_radar(payload_svg, span="full")
    assert 'font-size="40"' in rad_html
    assert "mod-legend" not in rad_html
    assert 'font-size="24"' in render_trend10(payload_svg, span="full")
    wave_html = render_wave(payload_svg, span="full")
    assert 'font-size="25"' in wave_html
    assert ">xG<" in wave_html
    assert ">۰.۰<" in wave_html
    assert ">۰.۲<" in wave_html
    assert ">۰.۴<" in wave_html
    assert 'font-size="18"' in render_xgrace(payload_svg, span="full")
    assert 'font-size="21"' in render_shotmap(payload_svg, span="full")
    assert 'font-size="21"' in render_momentum(payload_svg, span="full")


def test_dark_bg_contrast_auto_lift_and_pair_separation():
    from src.xgpedia.render.card_kit.helpers import ensure_dark_bg_contrast, resolve_visible_team_colors, wcag_contrast

    for dark_hex, sec in (("#132257", "#FFFFFF"), ("#241F20", "#FFFFFF"), ("#034694", "#FFFFFF"), ("#670E36", "#95BFE8")):
        lifted = ensure_dark_bg_contrast(dark_hex, secondary=sec)
        assert wcag_contrast(lifted, "#0D1730") >= 4.8

    # دو تیم آبی تیره کنار هم نباید رنگ نزدیک داشته باشند
    hc, ac = resolve_visible_team_colors(
        {"color": "#034694", "secondary": "#FFFFFF"},
        {"color": "#003399", "secondary": "#FFFFFF"},
    )
    assert wcag_contrast(hc, "#0D1730") >= 4.8
    assert wcag_contrast(ac, "#0D1730") >= 4.8
    assert hc != ac


def test_validator_allows_real_matchday_and_still_rejects_fabricated_numbers():
    from src.xgpedia.editorial.llm_provider import DraftOutput
    from src.xgpedia.editorial.validate import validate
    from src.xgpedia.normalization.models import MatchFacts, SourceInfo, TeamSide

    mf_with_md = MatchFacts(
        fixture_id="fdo:11",
        competition={"name": "Premier League", "season": "2026-27"},
        kickoff_utc="2026-11-23T15:00:00Z",
        source=SourceInfo(provider="football-data-org", collected_at="2026-11-23T08:00:00Z"),
        home=TeamSide(name_fa="برنتفورد", name_en="Brentford"),
        away=TeamSide(name_fa="اورتون", name_en="Everton"),
        matchday=11,
    )
    d = DraftOutput(
        status="ok",
        title="پیش‌بازی هفته ۱۱",
        bullets=["نبرد هفته ۱۱ لیگ برتر"],
        caption="در هفته ۱۱ لیگ برتر برنتفورد میزبان اورتون است.",
        source_note="football-data.org",
        uncertainties=[],
    )
    assert validate(d, mf_with_md, set()).passed

    # وقتی matchday در فکت نباشد، عدد ۱۱ همچنان باید رد شود (حفظ کامل دروازهٔ Gate 3)
    mf_no_md = MatchFacts(
        fixture_id="fdo:12",
        competition={"name": "Premier League", "season": "2026-27"},
        kickoff_utc="2026-11-23T15:00:00Z",
        source=SourceInfo(provider="football-data-org", collected_at="2026-11-23T08:00:00Z"),
        home=TeamSide(name_fa="برنتفورد", name_en="Brentford"),
        away=TeamSide(name_fa="اورتون", name_en="Everton"),
        matchday=None,
    )
    assert not validate(d, mf_no_md, set()).passed


def test_espn_parser_handles_null_entries_without_nonetype_error():
    from src.xgpedia.providers.espn_free import parse_espn_timing_wave, parse_espn_upcoming

    weird_payload = {
        "events": [
            None,
            {
                "date": "2026-11-23T15:00Z",
                "competitions": [
                    {
                        "date": "2026-11-23T15:00Z",
                        "odds": [None],
                        "status": None,
                        "competitors": [
                            None,
                            {"homeAway": "home", "team": {"id": "1", "displayName": "Brentford"}, "leaders": [None, {"name": "goals", "leaders": [None]}]},
                            {"homeAway": "away", "team": {"id": "2", "displayName": "Everton"}, "leaders": None},
                        ],
                        "details": [None, {"scoringPlay": True, "team": None, "clock": None}],
                    }
                ],
            },
        ]
    }
    res = parse_espn_upcoming(weird_payload)
    assert res == {"odds_rows": [], "key_players": {}}
    assert parse_espn_timing_wave(weird_payload) == {}


def test_db_migration_adds_wave_json_to_legacy_team_enrichments(tmp_path: Path, monkeypatch):
    import sqlite3

    db_path = tmp_path / "legacy_no_wave.db"
    # شبیه‌سازی دیتابیس قدیمی بدون ستون wave_json
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE team_enrichments (
          team TEXT NOT NULL,
          season TEXT NOT NULL,
          ppda REAL,
          xpts REAL,
          key_player_json TEXT,
          provider TEXT NOT NULL,
          collected_at TEXT NOT NULL,
          PRIMARY KEY (team, season, provider)
        )
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(db_mod, "DATABASE_PATH", db_path)
    db_mod.init_db()

    with db_mod.db() as c2:
        cols = {r["name"] for r in c2.execute("PRAGMA table_info(team_enrichments)")}
    assert "wave_json" in cols


def test_default_pre_match_template_locked_for_automation():
    from src.xgpedia.render.studio_engine import DEFAULT_PRE_MATCH_TEMPLATE, select_studio_modules

    assert DEFAULT_PRE_MATCH_TEMPLATE == [
        ("radar", "half"),
        ("trend10", "half"),
        ("signals", "full"),
    ]
    all_has = {k: True for k in ("radar", "keyduel", "signals", "wave", "trend10", "stats", "poisson")}
    mods = select_studio_modules("preview", all_has, fmt="4:5", layout="smart", header_mode="full")
    assert [(m["id"], m["span"]) for m in mods] == [
        ("radar", "half"),
        ("trend10", "half"),
        ("signals", "full"),
    ]
