"""تست‌های نسخه v0.38.5 — رفع کامل بریدگی کناره‌های عکس، متن ناقص و نبودن لوگوی باشگاه در کارت نقل‌قول."""
from __future__ import annotations

from src.xgpedia.providers.quote_free import (
    _detect_speaker_and_club,
    _is_incomplete_fragment,
    extract_quote_candidate,
)
from src.xgpedia.render.card_kit.quote_card import render_quote_html


def test_incomplete_fragment_detector_catches_dangling_en_and_fa() -> None:
    assert _is_incomplete_fragment("از شکست سنگین‌شان در برابر لیورپول به") is True
    assert _is_incomplete_fragment("from their heavy defeat against Liverpool to") is True
    assert _is_incomplete_fragment("t score more in Dortmund draw") is True
    assert _is_incomplete_fragment("ما باید در لحظات کلیدی بازی دقیق‌تر و منسجم‌تر عمل کنیم.") is False


def test_pochettino_inherits_real_club_crest_and_competition_from_article() -> None:
    """وقتی گوینده در SPEAKER_DB کد XGP دارد (مثل پوچتینو)، باشگاه واقعی از تیتر/توضیح خبر استخراج شود."""
    meta = _detect_speaker_and_club(
        "Pochettino: 'Painful defeat in first game'",
        "Tottenham boss Mauricio Pochettino reacts after defeat against Liverpool.",
    )
    assert meta["speaker"] == "مائوریسیو پوچتینو"
    assert meta["clubCode"] == "TOT"
    assert meta["competition"] == "لیگ برتر انگلیس"


def test_quote_card_uses_16_10_with_side_and_bottom_vignette_and_real_logo() -> None:
    item = {
        "speaker": "مائوریسیو پوچتینو",
        "role": "سرمربی • تاتنهام",
        "clubCode": "TOT",
        "color": "#CBD5E1",
        "quote": "این شکست *دردناک* بود، اما از فردا با تمرکز کامل برای جبران تلاش می‌کنیم.",
        "photoSrc": "data:image/png;base64,AAAA",
        "stats": [
            {"label": "گل زده فصل", "val": "31"},
            {"label": "امید گل تیم", "val": "29.4"},
            {"label": "کلین‌شیت", "val": "7"},
        ],
    }
    html = render_quote_html(item, slide="slide1", fmt="4:5")
    assert "aspect-ratio:16/10" in html
    assert "linear-gradient(90deg,rgba(13,23,48,.90)" in html
    assert "data:image/svg+xml;base64," in html  # لوگوی واقعی تاتنهام (نه سپر آبی XGP)

    # حتی وقتی clubCode == XGP باشد، لوگوی رسمی برند XGPedia (logo-xg-red.svg) رندر شود نه سپر جعلی
    item_xgp = dict(item, clubCode="XGP")
    html_xgp = render_quote_html(item_xgp, slide="slide1", fmt="4:5")
    assert 'alt="XGPedia"' in html_xgp


def test_extract_quote_rejects_dangling_single_quote_fragment() -> None:
    cand = extract_quote_candidate(
        title="Pochettino reacts to painful defeat against Liverpool",
        description="Mauricio Pochettino spoke about his players' heavy defeat against Liverpool to 'find a response immediately in training'",
        source_name="BBC Sport",
        image_url="https://ichef.bbci.co.uk/ace/standard/1024/cpsprodpb/test.jpg",
    )
    assert cand is not None
    assert not _is_incomplete_fragment(cand["quote"])
    assert cand.get("context_title")
    assert cand.get("context_desc")
