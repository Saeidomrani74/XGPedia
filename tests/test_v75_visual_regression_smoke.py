"""آزمون رگرسیون بصری خودکار (Visual Smoke QA — v0.75.0) برای ۴ کارت کلیدی XGPedia:
  1. Pre-Match (پیش‌ازبازی)
  2. Post-Match (پس‌ازبازی)
  3. Top Scorers (جدول گلزنان و کفش طلا)
  4. Player FC27 (کارت بازیکن FC27)

بررسی‌ها:
  - ۱۰۰٪ آفلاین (نبود لینک CDN خارجی در HTML/CSS و وجود فونت فارسی Vazirmatn)
  - رندر واقعی PNG با Playwright (در صورت نصب Chromium) با ابعاد دقیق 1080×1350 و حجم غیرخالی
  - بررسی نبود بریدگی افقی/عمودی متن فارسی در DOM (overflow check)
"""
from __future__ import annotations

import json
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _png_dimensions(png_path: Path) -> tuple[int, int]:
    """خواندن ابعاد دقیق PNG از هدر IHDR بدون وابستگی به Pillow."""
    raw = png_path.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n", f"Invalid PNG header: {png_path}"
    w, h = struct.unpack(">II", raw[16:24])
    return w, h


def _assert_offline_persian_html(html_str: str, label: str) -> None:
    """تضمین ۱۰۰٪ آفلاین‌بودن HTML، راست‌به‌چپ بودن و وجود فونت فارسی."""
    assert len(html_str) > 2000, f"{label}: HTML too short"
    assert 'dir="rtl"' in html_str or "direction: rtl" in html_str or "direction:rtl" in html_str, (
        f"{label}: missing RTL direction"
    )
    assert "Vazirmatn" in html_str, f"{label}: missing Vazirmatn Persian font"
    # هیچ CDN خارجی برای فونت یا اسکریپت نباید در HTML رندرشده وجود داشته باشد
    ext_links = re.findall(r'<(?:link|script)[^>]+(?:href|src)=["\']https?://[^"\']+["\']', html_str, flags=re.IGNORECASE)
    assert not ext_links, f"{label}: external CDN links found in offline HTML: {ext_links[:2]}"


def _build_four_flagship_htmls() -> dict[str, str]:
    from src.xgpedia.render.card_kit.player_fc27_card import render_player_fc27_html
    from src.xgpedia.render.card_kit.top_scorers_card import render_top_scorers_html
    from src.xgpedia.render.cards import render_preview_html
    from src.xgpedia.render.post_match_cards import render_post_match_html

    facts = json.loads((ROOT / "tests" / "fixtures" / "fact.json").read_text(encoding="utf-8"))
    facts_pm = dict(facts)
    facts_pm["result"] = {"home_goals": 2, "away_goals": 1}
    draft = {
        "status": "ok",
        "title": "آرسنال با برتری امید گل میزبان چلسی است",
        "bullets": ["آرسنال ۱۱ امتیاز از ۵ بازی اخیر", "میانگین امید گل میزبان: 1.85 در ۱۰ بازی"],
        "caption": "تحلیل پیش‌بازی دربی لندن بر پایهٔ داده‌های واقعی فصل.",
        "source_note": "XGPedia QA",
        "uncertainties": [],
    }

    ts_presets = json.loads((ROOT / "config" / "top_scorers_presets.json").read_text(encoding="utf-8"))
    ts_item = (ts_presets.get("items") or ts_presets if isinstance(ts_presets, dict) else ts_presets)[0]

    fc_presets = json.loads((ROOT / "config" / "player_fc27_presets.json").read_text(encoding="utf-8"))
    fc_item = (fc_presets.get("items") or fc_presets if isinstance(fc_presets, dict) else fc_presets)[0]

    return {
        "pre_match": render_preview_html(draft, facts),
        "post_match": render_post_match_html(draft, facts_pm),
        "top_scorers": render_top_scorers_html(ts_item),
        "player_fc27": render_player_fc27_html(fc_item),
    }

def test_visual_smoke_four_flagship_cards_offline_html() -> None:
    """هر ۴ کارت کلیدی باید بدون CDN خارجی، با فونت Vazirmatn و RTL رندر شوند."""
    htmls = _build_four_flagship_htmls()
    for name, html_str in htmls.items():
        _assert_offline_persian_html(html_str, name)


def test_visual_smoke_four_flagship_cards_real_png_and_no_overflow(tmp_path) -> None:
    """رندر واقعی PNG برای ۴ کارت کلیدی + JPEG اینستاگرام با چک ابعاد، لوگوهای شکسته و سرریز DOM."""
    from tests.conftest import require_chromium
    from src.xgpedia.render.visual_qa import run_visual_smoke_suite

    require_chromium()
    results = run_visual_smoke_suite(out_dir=tmp_path, include_instagram_jpeg=True)
    assert len(results) == 7
    for r in results:
        assert r.ok, f"{r.card_name} failed Visual QA: {r.issues}"
        assert not r.broken_images, f"{r.card_name} has broken logos/images: {r.broken_images}"
        assert (r.actual_width, r.actual_height) == (r.width, r.height)

def test_source_chain_multidimensional_quality_profile_ranking() -> None:
    """ارزیابی چندبعدی SourceQualityProfile باید ترتیب زنجیره را بر اساس امتیاز ترکیبی تنظیم کند."""
    from src.xgpedia.core.source_chain import DataSourceChain, SourceCandidate, SourceQualityProfile

    chain = DataSourceChain("test_multidim")
    chain.register(
        SourceCandidate(
            "high_raw_low_rights",
            95,
            "Source A",
            quality_profile=SourceQualityProfile(reliability=60, data_quality=90, freshness=70, rights_safety=40),
        )
    )
    chain.register(
        SourceCandidate(
            "balanced_strong",
            85,
            "Source B",
            quality_profile=SourceQualityProfile(reliability=92, data_quality=90, freshness=90, rights_safety=95),
        )
    )
    ordered = [c.provider_id for c in chain.ordered_candidates(respect_health=False)]
    assert ordered == ["balanced_strong", "high_raw_low_rights"]
