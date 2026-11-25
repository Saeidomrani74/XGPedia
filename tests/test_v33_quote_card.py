"""تست‌های کامل کارت اسلایدی نقل‌قول XGPedia (`v0.33.0 — Quote Studio`)."""
from __future__ import annotations

from pathlib import Path


def test_quote_zero_requests_dependency() -> None:
    for p in (
        "src/xgpedia/providers/quote_free.py",
        "src/xgpedia/render/card_kit/quote_card.py",
    ):
        txt = Path(p).read_text(encoding="utf-8")
        assert "import requests" not in txt and "from requests" not in txt


def test_quote_presets_and_live_extractor_soccer_only() -> None:
    from src.xgpedia.providers.quote_free import (
        extract_quote_candidate,
        load_quote_presets,
        pair_duel_quotes,
    )

    presets = load_quote_presets()
    assert len(presets) == 5
    assert any(p.get("layout") == "duel" for p in presets)

    # 1. Valid football quote (Arteta)
    c1 = extract_quote_candidate(
        title='Mikel Arteta: "We showed real mentality and belief to control the title race"',
        description="Arsenal boss Mikel Arteta praised his players after the Premier League victory.",
        source_name="BBC Sport",
        source_url="https://www.bbc.com/sport/football/articles/test1",
        pub_date="Tue, 24 Nov 2026 14:00:00 GMT",
        image_url="https://ichef.bbci.co.uk/news/240/cpsprodpb/test.jpg",
    )
    assert c1 is not None
    assert c1["speaker"] == "میکل آرتتا"
    assert c1["clubCode"] == "ARS"
    assert c1["fit_score"] >= 60
    assert "*" in c1["quote"]
    assert "/1024/" in c1["photoSrc"]

    # 2. Valid football quote (Guardiola)
    c2 = extract_quote_candidate(
        title='Pep Guardiola insists "the pressure of the Champions League makes us better"',
        description="Manchester City manager Pep Guardiola spoke ahead of the clash.",
        source_name="The Guardian",
        source_url="https://www.theguardian.com/football/test2",
        pub_date="Tue, 24 Nov 2026 15:00:00 GMT",
    )
    assert c2 is not None
    assert c2["speaker"] == "پپ گواردیولا"
    assert c2["clubCode"] == "MCI"

    # 3. Auto duel pairing
    paired = pair_duel_quotes([c1, c2])
    assert paired[0]["speaker2"] == "پپ گواردیولا"
    assert paired[0]["clubCode2"] == "MCI"
    assert paired[0]["color2"].lower() != paired[0]["color"].lower()

    # 4. Strict Soccer-only filter rejects NFL/NBA/Cricket
    nfl = extract_quote_candidate(
        title='Super Bowl quarterback says "we need a touchdown in the fourth quarter"',
        description="NFL star speaks after practice.",
        source_name="ESPN",
    )
    assert nfl is None


def test_quote_card_5_slides_3_formats_offline_and_null_guard() -> None:
    from src.xgpedia.providers.quote_free import load_quote_presets
    from src.xgpedia.render.card_kit.quote_card import (
        QUOTE_FORMATS,
        QUOTE_SLIDES,
        get_quote_modules,
        render_quote_html,
    )

    assert len(QUOTE_SLIDES) == 5
    preset = dict(load_quote_presets()[0])
    preset["color"] = "#003399"  # Dark Everton blue should be brightened

    for sl, _, hm in QUOTE_SLIDES:
        assert hm == "full"
        for fmt in QUOTE_FORMATS:
            h = render_quote_html(preset, slide=sl, header_mode=hm, fmt=fmt)
            assert "cdn.tailwindcss.com" not in h
            assert "fonts.googleapis.com" not in h
            assert "white-space:nowrap!important" in h
            assert 'stroke="#E62E45"' in h
            assert "@XGPedia" in h
            if sl == "slide5":
                assert ">VS<" in h and preset["speaker"] in h and preset["speaker2"] in h

    # Highlight styles
    assert "qhl-pill" in render_quote_html(preset, slide="slide1", hl_style="pill")
    assert "qhl-accent" in render_quote_html(preset, slide="slide1", hl_style="accent")

    # null ≠ 0: when stats is empty, stats bar must not appear
    no_stats = dict(preset)
    no_stats["stats"] = []
    mods, miss = get_quote_modules(no_stats, "slide1")
    assert any("آمار" in m for m in miss)
    h_ns = render_quote_html(no_stats, slide="slide1", modules=mods)
    assert "بررسی آماری" not in h_ns


def test_quote_bot_workflow_and_hashtags_wired() -> None:
    from src.xgpedia import today_workflow as tw
    from src.xgpedia.publishers import telegram_publish as tp

    assert hasattr(tw, "generate_quote_post_async")
    assert "quote" in tp.POST_TYPE_FA
    assert tp.HASHTAG_BY_TYPE.get("quote") == "#نقل_قول_فوتبالی"

    mb_txt = Path("src/xgpedia/publishers/modular_cards_bot.py").read_text(encoding="utf-8")
    assert '"quote": {' in mb_txt and '"prefix": "qt"' in mb_txt and '"cmd": "quote"' in mb_txt
    assert "generate_quote_post_async" in mb_txt

    tb_txt = Path("src/xgpedia/publishers/telegram_bot.py").read_text(encoding="utf-8")
    assert "qt:list:1" in tb_txt and "qt:refresh" in tb_txt
    assert "(ماژولار)" not in tb_txt
