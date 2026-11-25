"""تست‌های نسخه v0.38.2 — رفع ۴ مشکل نهایی کارت نقل‌قول روز (quote_free + quote_card + today_workflow)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from src.xgpedia.providers.quote_free import (
    _attach_real_fpl_stats,
    _try_translate_quote_fa,
    extract_quote_candidate,
)
from src.xgpedia.render.card_kit.quote_card import get_quote_modules, render_quote_html


def test_apostrophe_contractions_never_slice_quote() -> None:
    """آپاستروف داخل کلمات (didn't / side's) نباید به عنوان گیومه متن را از وسط ببرد."""
    cand = extract_quote_candidate(
        title="Arteta says Arsenal didn't score more in Dortmund draw",
        description="Arsenal manager Mikel Arteta rued his side's missed chances after the Champions League draw.",
        source_name="ESPN Soccer",
        image_url="https://example.com/arteta.jpg",
    )
    assert cand is not None
    q = cand["quote"].replace("*", "")
    assert not q.startswith("t "), f"Quote sliced mid-contraction: {q!r}"
    assert " — " not in q, f"Quote crossed title/description separator: {q!r}"
    assert "Arteta" in q or "missed chances" in q


def test_real_single_quoted_speech_still_extracted() -> None:
    """گیومهٔ تکی واقعی در مرز کلمات همچنان درست استخراج شود."""
    cand = extract_quote_candidate(
        title="Pep Guardiola: 'We must control the midfield and press high every single minute'",
        description="Man City boss spoke after the win.",
        source_name="BBC Sport",
        image_url="https://example.com/pep.jpg",
    )
    assert cand is not None
    q = cand["quote"].replace("*", "")
    assert q == "We must control the midfield and press high every single minute"


def test_quote_photo_starts_flush_at_top_zero() -> None:
    """عکس پس‌زمینه در spotlight و poster باید از top:0 بدون margin-top شروع شود."""
    item = {
        "speaker": "میکل آرتتا",
        "role": "سرمربی آرسنال",
        "clubCode": "ARS",
        "color": "#EF0107",
        "quote": "ما باید در *لحظات کلیدی* بازی دقیق‌تر باشیم.",
        "photoSrc": "data:image/png;base64,AAAA",
        "stats": [
            {"label": "گل زده فصل", "val": "42"},
            {"label": "امید گل تیم", "val": "38.4"},
            {"label": "کلین‌شیت", "val": "11"},
        ],
    }
    for sl in ("slide1", "slide4"):
        html = render_quote_html(item, slide=sl, fmt="4:5")
        assert "position:absolute;top:0;left:0;right:0" in html
        assert "margin-top:22px" not in html
        assert "بررسی آماری" in html


def test_live_item_keeps_stats_module_enabled_for_hydration() -> None:
    """در آیتم زنده قبل از hydration، ماژول stats نباید پیش‌فرض خاموش شود تا باکس‌های پایین نمایش داده شوند."""
    live_item = {"id": "live_qt_1", "is_live": True, "stats": []}
    mods, missing = get_quote_modules(live_item, "slide1")
    st_mod = next(m for m in mods if m["id"] == "stats")
    assert st_mod["enabled"] is True
    assert not missing

    # پس از hydration و افزودن ۳ شاخص، با همین custom_modules باید رندر شود
    live_item["speaker"] = "میکل آرتتا"
    live_item["quote"] = "ما از *مالکیت توپ* کوتاه نمی‌آییم."
    live_item["stats"] = [
        {"label": "گل زده فصل", "val": "42"},
        {"label": "امید گل تیم", "val": "38.4"},
        {"label": "کلین‌شیت", "val": "11"},
    ]
    html = render_quote_html(live_item, slide="slide1", fmt="4:5", modules=mods)
    assert "بررسی آماری" in html
    assert "امید گل تیم" in html


def test_structured_llm_translation_used_for_quote() -> None:
    """ترجمه فارسی نقل‌قول باید از مسیر پایدار build_default_llm().generate استفاده کند."""
    fake_llm = SimpleNamespace(
        generate=lambda sys_p, payload: SimpleNamespace(
            status="ok",
            title="واکنش آرتتا پس از تساوی",
            caption="باید از موقعیت‌هایمان در *دورتموند* بهتر استفاده می‌کردیم.",
            bullets=[],
            source_note="XGPedia",
            uncertainties=[],
        )
    )
    with patch("src.xgpedia.editorial.llm_provider.build_default_llm", return_value=fake_llm):
        fa_q = _try_translate_quote_fa(
            "We should have scored more goals in the draw against Dortmund",
            speaker_fa="میکل آرتتا",
            competition="لیگ قهرمانان اروپا",
        )
    assert "دورتموند" in fa_q
    assert "*" in fa_q


def test_attach_real_stats_supports_european_clubs() -> None:
    """باشگاه‌های غیرانگلیسی (مثل رئال مادرید) هم از جدول زنده ۳ شاخص واقعی بگیرند."""
    item = {"speaker_en": "Carlo Ancelotti", "clubCode": "RMA", "stats": []}
    fake_rows = [{"team": "Real Madrid", "rank": 1, "points": 68, "goals_for": 61}]
    with patch("src.xgpedia.providers.fpl_free.fetch_fpl_bootstrap", return_value=None), patch(
        "src.xgpedia.providers.open_football_hub.fetch_wc26_standings", return_value=fake_rows
    ):
        _attach_real_fpl_stats(item)
    assert len(item["stats"]) == 3
    assert item["stats"][0]["val"] == "#1"
    assert item["stats"][1]["val"] == "68"
