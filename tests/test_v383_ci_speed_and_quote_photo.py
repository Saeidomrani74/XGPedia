"""تست‌های نسخه v0.38.3 — رفع خطای GitHub Actions، سرعت pytest و تصویر کارت نقل‌قول گاردین."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from src.xgpedia.providers.breaking_news_free import upgrade_news_image_url
from src.xgpedia.providers.quote_free import _resolve_photo_data_uri, extract_quote_candidate


def test_github_workflow_has_no_secrets_in_if_expression() -> None:
    """در GitHub Actions استفاده مستقیم از secrets.* در خط if: خطای Invalid workflow می‌دهد."""
    wf = Path(".github/workflows/jobs.yml").read_text(encoding="utf-8")
    for line in wf.splitlines():
        stripped = line.strip()
        if stripped.startswith("if:"):
            assert "secrets." not in stripped, f"Invalid secrets usage in if: {stripped}"
    assert "FOOTBALL_DATA_ORG_TOKEN" in wf


def test_upgrade_news_image_url_preserves_signed_guardian_urls() -> None:
    """تغییر width در لینک امضادار i.guim.co.uk باعث 403 می‌شود؛ باید دست‌نخورده بماند."""
    signed = "https://i.guim.co.uk/img/media/abc/0_0_3000_1800/3000.jpg?width=460&quality=85&auto=format&fit=max&s=deadbeef1234"
    assert upgrade_news_image_url(signed) == signed

    unsigned = "https://i.guim.co.uk/img/media/abc/0_0_3000_1800/3000.jpg?width=460&quality=85"
    assert "width=1200" in (upgrade_news_image_url(unsigned) or "")

    bbc = "https://ichef.bbci.co.uk/ace/standard/240/cpsprodpb/test.jpg"
    assert "/1024/" in (upgrade_news_image_url(bbc) or "")


def test_resolve_photo_prefers_guardian_og_image_and_falls_back_cleanly() -> None:
    """برای تامبنیل ریز گاردین، ابتدا og:image باکیفیت را امتحان کند و در صورت خطا روی لینک اصلی برگردد."""
    small_guim = "https://i.guim.co.uk/img/media/x.jpg?width=460&s=sig1"
    hd_og = "https://i.guim.co.uk/img/media/x.jpg?width=1200&s=sig2"

    def _fake_dl(url: str, timeout: float = 6.0) -> str:
        if url == hd_og:
            return "data:image/jpeg;base64,HDIMAGE"
        if url == small_guim:
            return "data:image/jpeg;base64,SMALLIMAGE"
        return ""

    with patch("src.xgpedia.providers.quote_free._fetch_og_image_from_article", return_value=hd_og), patch(
        "src.xgpedia.providers.quote_free._download_image_data_uri", side_effect=_fake_dl
    ):
        uri = _resolve_photo_data_uri(small_guim, small_guim, "https://www.theguardian.com/football/test", "")
    assert uri == "data:image/jpeg;base64,HDIMAGE"

    # اگر og:image نبود، از لینک امضادار اصلی گاردین استفاده کند (خالی نماند!)
    with patch("src.xgpedia.providers.quote_free._fetch_og_image_from_article", return_value=""), patch(
        "src.xgpedia.providers.quote_free._download_image_data_uri", side_effect=_fake_dl
    ):
        uri2 = _resolve_photo_data_uri(small_guim, small_guim, "https://www.theguardian.com/football/test", "")
    assert uri2 == "data:image/jpeg;base64,SMALLIMAGE"


def test_pochettino_detected_in_speaker_db() -> None:
    cand = extract_quote_candidate(
        title="Mauricio Pochettino: 'We have an amazing car, we need to be at the right level to drive it'",
        description="Pochettino spoke to reporters after the match.",
        source_name="The Guardian",
        image_url="https://i.guim.co.uk/img/media/x.jpg?width=460&s=sig1",
    )
    assert cand is not None
    assert cand["speaker"] == "مائوریسیو پوچتینو"
    assert cand["photoSrc_raw"] == "https://i.guim.co.uk/img/media/x.jpg?width=460&s=sig1"
