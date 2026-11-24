"""آزمون‌های نسخهٔ 0.29.0 — کارت ماژولار رادار نقل‌وانتقالات (D48): ۵ منبع رایگان + امتیازدهی داغ بودن + ۱۰ ماژول + هشتگ و منبع هایپرلینک."""
from __future__ import annotations

import json
from types import SimpleNamespace

from src.xgpedia.providers.transfer_radar_free import (
    compute_rumor_hotness,
    enrich_transfer_rumor,
    load_transfer_presets,
    parse_transfer_rss_xml,
)
from src.xgpedia.publishers import telegram_publish as tp
from src.xgpedia.render.card_kit.transfer_radar_card import (
    TRANSFER_DEFAULT_SLIDE,
    TRANSFER_FORMATS,
    TRANSFER_SLIDES,
    build_transfer_caption,
    get_transfer_modules,
    render_transfer_radar_html,
)


def test_transfer_presets_and_all_5_slides_3_formats_render_offline():
    assert TRANSFER_DEFAULT_SLIDE == "slide1"
    presets = load_transfer_presets()
    assert len(presets) == 4
    gyo = presets[0]
    for sid, _, hm, _ in TRANSFER_SLIDES:
        for fmt, (w, h) in TRANSFER_FORMATS.items():
            html_out = render_transfer_radar_html(gyo, slide=sid, header_mode=hm, fmt=fmt)
            assert "cdn.tailwindcss.com" not in html_out
            assert "fonts.googleapis.com" not in html_out
            assert f"width:{w}px;height:{h}px" in html_out
            assert f"M24 44V24H44M{w - 24} 44V24H{w - 44}" in html_out
            assert "@XGPedia" in html_out


def test_rss_parser_filters_soccer_only_and_scores_hotness():
    xml = b"""<?xml version="1.0"?>
    <rss><channel>
      <item>
        <title>Arsenal in advanced talks to sign Viktor Gyokeres for &#8364;75m</title>
        <description>Personal terms agreed with Sporting striker ahead of medical.</description>
        <link>https://www.theguardian.com/football/2026/gyokeres-arsenal</link>
      </item>
      <item>
        <title>NFL trade rumor: quarterback signs new contract</title>
        <description>American football transfer deal.</description>
        <link>https://example.com/nfl</link>
      </item>
    </channel></rss>"""
    items = parse_transfer_rss_xml(xml, source_name="The Guardian", tier=1)
    assert len(items) == 1
    it = items[0]
    assert it["status"] == "hot"
    assert it["hotness"] >= 85
    assert it["finance"]["fixed"] == 75.0
    assert it["tacticalFit"] is None  # null ≠ 0

    h_done, st_done, stg_done = compute_rumor_hotness("Here we go: Real Madrid done deal for star", "", tier=1)
    assert st_done == "done" and stg_done == 5 and h_done >= 85


def test_transfer_on_demand_llm_enrichment_module_gating_and_telegram_caption():
    raw = {
        "id": "tr_live1",
        "headline_en": "Arsenal close to €75m deal for Viktor Gyokeres",
        "lead_en": "Arsenal have reached personal terms with Viktor Gyokeres.",
        "source": "The Guardian",
        "source_url": "https://www.theguardian.com/football/2026/gyokeres-arsenal",
        "tier": 1,
        "hotness": 91,
        "status": "hot",
        "prob": 78,
        "stayProb": 12,
        "stage": 4,
        "player": {"name": "Viktor Gyokeres", "nameEn": "", "pos": "", "age": None, "nat": "", "flag": "", "num": None},
        "from": {"name": "", "sub": "", "code": "FRM", "color": "#10B981", "secondary": "#FFFFFF"},
        "to": {"name": "", "sub": "", "code": "DST", "color": "#E62E45", "secondary": "#FFFFFF"},
        "finance": {"fixed": None, "addon": None, "salary": None, "years": None, "marketVal": None, "modelVal": None, "dealType": "شایعه", "mv": None},
        "tacticalFit": None,
        "credibility": {"score": 88, "sources": [{"name": "The Guardian", "outlet": "The Guardian", "tier": 1, "conf": 88, "time": "امروز"}]},
        "stats": None,
        "valuation": None,
        "rivals": [],
        "verdict": None,
    }

    class _FakeLLM:
        def generate(self, sys_p, payload):
            return SimpleNamespace(
                title="توافق شخصی آرسنال با گیوکرش نهایی شد",
                caption="آرسنال پس از هفته‌ها مذاکره با نمایندهٔ ویکتور گیوکرش به توافق شخصی رسیده و اکنون روی ساختار نهایی مبلغ با اسپورتینگ چانه‌زنی می‌کند.",
                bullets=[
                    "PLAYER: ویکتور گیوکرش | Viktor Gyokeres | مهاجم نوک",
                    "CLUBS: اسپورتینگ لیسبون | آرسنال | 75 | hot | 82",
                    "چانه‌زنی نهایی روی قسط‌بندی پاداش‌ها در جریان است.",
                ],
                source_note="The Guardian",
            )

    enr = enrich_transfer_rumor(raw, llm_provider=_FakeLLM(), fetch_network=False)
    assert enr["player"]["name"] == "ویکتور گیوکرش"
    assert enr["to"]["name"] == "آرسنال"
    assert enr["finance"]["fixed"] == 75.0
    assert enr["prob"] == 82

    mods, missing = get_transfer_modules(enr, "slide1")
    mids = {m["id"] for m in mods}
    assert {"pipeline", "package", "credibility", "rivals", "verdict"} <= mids
    assert "tacticalfit" not in mids  # null ≠ 0
    assert any("رادار" in m for m in missing)

    cap = build_transfer_caption(enr)
    post = {
        "post_id": 91,
        "post_type": "transfer_radar",
        "content_version": 1,
        "title": "رادار نقل‌وانتقالات | ویکتور گیوکرش ← آرسنال",
        "caption": cap,
        "draft_json": json.dumps({"title": "رادار نقل‌وانتقالات | ویکتور گیوکرش ← آرسنال"}, ensure_ascii=False),
        "fact_json": json.dumps(enr, ensure_ascii=False),
    }
    full = tp.build_caption(post)
    assert full.startswith("<b>📡 رادار نقل‌وانتقالات")
    assert '<a href="https://www.theguardian.com/football/2026/gyokeres-arsenal">The Guardian</a>' in full
    assert "#XGPedia" in full and "#نقل_و_انتقالات" in full and "#رادار_نقل_و_انتقالات" in full and "#آرسنال" in full
    assert tp._utf16_len(tp.build_review_caption(post)) <= tp.CAPTION_LIMIT
