"""آزمون‌های نسخهٔ 0.28.0 — استودیو کارت تولد اسلایدی (D47): ۳ سبک × ۳ فرمت × ۶ ماژول + دیتای چندمنبعی رایگان + هشتگ و منبع هایپرلینک."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from src.xgpedia.providers.birthday_free import (
    enrich_birthday_player,
    load_birthday_presets,
    parse_wikidata_sparql_json,
    parse_wikimedia_births_json,
    parse_wikipedia_infobox_stats,
)
from src.xgpedia.publishers import telegram_publish as tp
from src.xgpedia.render.card_kit.birthday_card import (
    BIRTHDAY_DEFAULT_MODE,
    BIRTHDAY_FORMATS,
    BIRTHDAY_MODES,
    build_birthday_caption,
    get_birthday_modules,
    render_birthday_html,
)


def test_birthday_presets_loaded_and_default_mode():
    assert BIRTHDAY_DEFAULT_MODE == "poster"
    presets = load_birthday_presets(now=datetime(2026, 11, 24, tzinfo=timezone.utc))
    assert len(presets) == 5
    ids = {p["id"] for p in presets}
    assert {"preset_messi", "preset_ronaldo", "preset_taremi", "preset_mbappe", "preset_yamal"} == ids
    messi = next(p for p in presets if p["id"] == "preset_messi")
    assert messi["age"] == 39


def test_all_3_modes_and_3_formats_render_offline_with_postmatch_frame():
    presets = load_birthday_presets()
    messi = presets[0]
    for mode, _, _ in BIRTHDAY_MODES:
        for fmt, (w, h) in BIRTHDAY_FORMATS.items():
            html_out = render_birthday_html(messi, mode=mode, fmt=fmt)
            assert "cdn.tailwindcss.com" not in html_out
            assert "fonts.googleapis.com" not in html_out
            assert f"width:{w}px;height:{h}px" in html_out
            assert f"M24 44V24H44M{w - 24} 44V24H{w - 44}" in html_out
            assert "@XGPedia" in html_out
            assert "لیونل مسی" in html_out


def test_multi_source_parsers_wikimedia_wikidata_and_infobox_null_ne_zero():
    # ۱) Wikimedia births parser (فقط فوتبالیست‌ها را نگه می‌دارد)
    wm_payload = {
        "births": [
            {
                "year": 1990,
                "text": "Test Striker, English footballer",
                "pages": [{
                    "titles": {"normalized": "Test Striker"},
                    "description": "English association football player",
                    "extract": "Test Striker is an English footballer who plays as a forward.",
                    "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Test_Striker"}},
                }],
            },
            {
                "year": 1980,
                "text": "Random Politician, senator",
                "pages": [{"titles": {"normalized": "Random Politician"}, "description": "Politician"}],
            },
        ]
    }
    wm_items = parse_wikimedia_births_json(wm_payload, month=11, day=24, now=datetime(2026, 11, 24, tzinfo=timezone.utc))
    assert len(wm_items) == 1
    assert wm_items[0]["age"] == 36
    assert wm_items[0]["kpis"] is None and wm_items[0]["radar"] is None

    # ۲) Wikidata SPARQL parser
    wd_payload = {
        "results": {
            "bindings": [{
                "nameEn": {"value": "Pedri"},
                "nameFa": {"value": "پدری"},
                "dob": {"value": "2002-11-25T00:00:00Z"},
                "natFa": {"value": "اسپانیا"},
                "posFa": {"value": "هافبک"},
                "enwiki": {"value": "https://en.wikipedia.org/wiki/Pedri"},
                "sitelinks": {"value": "75"},
            }]
        }
    }
    wd_items = parse_wikidata_sparql_json(wd_payload, month=11, day=25, now=datetime(2026, 11, 25, tzinfo=timezone.utc))
    assert len(wd_items) == 1
    assert wd_items[0]["nameFa"] == "پدری" and wd_items[0]["age"] == 24

    # ۳) Wikipedia Infobox wikitext parser
    wikitext = """
    {{Infobox football biography
    | birth_date = {{birth date and age|1992|7|18|df=y}}
    | currentclub = [[Olympiacos F.C.|Olympiacos]]
    | clubnumber = 99
    | position = [[Forward (association football)|Striker]]
    | years1 = 2014–2018 | clubs1 = [[Persepolis F.C.|Persepolis]] | caps1 = 87 | goals1 = 45
    | years2 = 2020–2024 | clubs2 = [[FC Porto|Porto]] | caps2 = 122 | goals2 = 64
    }}
    """
    parsed = parse_wikipedia_infobox_stats(wikitext)
    assert parsed["club"] == "Olympiacos"
    assert parsed["jersey"] == 99
    assert parsed["kpis"]["apps"] == "209"
    assert parsed["kpis"]["goals"] == "109"
    assert parsed["kpis"]["assists"] is None  # null ≠ 0
    assert len(parsed["timeline"]) == 2


def test_birthday_module_gating_llm_tribute_and_telegram_caption_with_hashtags():
    raw_player = {
        "id": "wd_test1",
        "nameFa": "پدری",
        "nameEn": "PEDRI",
        "age": 24,
        "birthYear": 2002,
        "birthMonth": 11,
        "birthDay": 25,
        "club": "بارسلونا",
        "nat": "اسپانیا",
        "pos": "هافبک",
        "source": "Wikidata / Wikipedia",
        "source_url": "https://en.wikipedia.org/wiki/Pedri",
        "kpis": {"apps": "210", "goals": "28", "assists": None, "p90": None},
        "radar": None,
        "trophies": [],
        "timeline": [{"club": "بارسلونا", "years": "2020-26", "color": "#E62E45", "tag": "هافبک طراح"}],
    }

    class _FakeLLM:
        def generate(self, sys_p, payload):
            return SimpleNamespace(
                title="مغز متفکر میانه میدان کاتالان",
                caption="پدری در ۲۴ سالگی به ستون اصلی ریتم‌سازی بارسلونا و تیم ملی اسپانیا تبدیل شده است.",
                bullets=["ماسترو آرام خط میانی بارسلونا", "برنده جایزه کوپا و گلدن بوی"],
                source_note="پدری | بارسلونا",
            )

    enriched = enrich_birthday_player(raw_player, llm_provider=_FakeLLM(), fetch_network=False)
    mods, missing = get_birthday_modules(enriched, "poster")
    mod_ids = {m["id"] for m in mods}
    assert {"kpis", "timeline", "quote"} <= mod_ids
    assert "radar" not in mod_ids  # قانون null ≠ 0
    assert any("رادار" in m for m in missing)

    cap = build_birthday_caption(enriched)
    post = {
        "post_id": 88,
        "post_type": "birthday",
        "content_version": 1,
        "title": "تولدت مبارک پدری (24 سالگی)",
        "caption": cap,
        "draft_json": json.dumps({"title": "تولدت مبارک پدری"}, ensure_ascii=False),
        "fact_json": json.dumps(enriched, ensure_ascii=False),
    }
    full = tp.build_caption(post)
    assert full.startswith("<b>🎂 تولدت مبارک پدری")
    assert '<a href="https://en.wikipedia.org/wiki/Pedri">Wikidata / Wikipedia</a>' in full
    assert "#XGPedia" in full and "#تولدت_مبارک" in full and "#تولد_اسطوره" in full and "#بارسلونا" in full
    rev = tp.build_review_caption(post)
    assert tp._utf16_len(rev) <= tp.CAPTION_LIMIT


def test_strict_soccer_only_rejects_nfl_afl_cfl_rugby():
    wm_payload = {
        "births": [
            {
                "year": 1995,
                "text": "John Doe, American football quarterback (NFL)",
                "pages": [{"titles": {"normalized": "John Doe"}, "description": "American football player", "extract": "John Doe is an NFL linebacker."}],
            },
            {
                "year": 1993,
                "text": "Jack Smith, Australian rules footballer (AFL)",
                "pages": [{"titles": {"normalized": "Jack Smith"}, "description": "Australian rules footballer", "extract": "Plays in the AFL."}],
            },
            {
                "year": 1991,
                "text": "Mike Brown, Canadian football wide receiver",
                "pages": [{"titles": {"normalized": "Mike Brown"}, "description": "Canadian football player", "extract": "Played in the CFL."}],
            },
            {
                "year": 1992,
                "text": "Carlos Silva, Brazilian footballer",
                "pages": [{"titles": {"normalized": "Carlos Silva"}, "description": "Brazilian association football player", "extract": "Carlos Silva is a Brazilian midfielder."}],
            },
        ]
    }
    items = parse_wikimedia_births_json(wm_payload, month=11, day=24, now=datetime(2026, 11, 24, tzinfo=timezone.utc))
    assert len(items) == 1
    assert items[0]["nameEn"] == "CARLOS SILVA"
