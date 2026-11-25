"""تست‌های جامع استودیو ۵ اسلایده و ماژولار «نقشهٔ شوت و مومنتوم امید گل» (`v0.38.0 — Shot-Map & xG Timeline Studio`)."""
from __future__ import annotations

from pathlib import Path


def test_v38_zero_requests_dependency() -> None:
    for p in (
        "src/xgpedia/providers/shotmap_xg_free.py",
        "src/xgpedia/render/card_kit/shotmap_xg_card.py",
    ):
        txt = Path(p).read_text(encoding="utf-8")
        assert "import requests" not in txt and "from requests" not in txt


def test_v38_shotmap_provider_presets_and_understat_parser() -> None:
    from src.xgpedia.providers.shotmap_xg_free import (
        load_shotmap_xg_presets,
        parse_understat_shots_payload,
    )

    presets = load_shotmap_xg_presets()
    assert len(presets) >= 2
    assert len(presets[0]["shots"]) >= 10

    raw_shots = {
        "h": [
            {"X": "0.89", "Y": "0.46", "xG": "0.35", "minute": "14", "result": "Goal", "situation": "OpenPlay", "player": "Bukayo Saka"},
            {"X": "0.885", "Y": "0.50", "xG": "0.76", "minute": "62", "result": "Goal", "situation": "Penalty", "player": "Bukayo Saka"},
        ],
        "a": [
            {"X": "0.91", "Y": "0.52", "xG": "0.41", "minute": "38", "result": "SavedShot", "situation": "OpenPlay", "player": "Mohamed Salah"},
        ],
    }
    parsed = parse_understat_shots_payload(raw_shots)
    assert len(parsed) == 3
    assert parsed[0]["min"] == 14 and parsed[0]["result"] == "Goal"
    assert any(s["situation"] == "Penalty" for s in parsed)


def test_v38_shotmap_card_5_slides_3_formats_offline_and_null_guard() -> None:
    from src.xgpedia.providers.shotmap_xg_free import load_shotmap_xg_presets
    from src.xgpedia.render.card_kit.shotmap_xg_card import (
        SHOTMAP_FORMATS,
        SHOTMAP_SLIDES,
        get_shotmap_xg_modules,
        render_shotmap_xg_html,
    )

    assert len(SHOTMAP_SLIDES) == 5
    preset = dict(load_shotmap_xg_presets()[0])
    for sl, _, _, _ in SHOTMAP_SLIDES:
        for fmt in SHOTMAP_FORMATS:
            h = render_shotmap_xg_html(preset, slide=sl, fmt=fmt, theme="classic")
            assert "cdn.tailwindcss.com" not in h
            assert "fonts.googleapis.com" not in h
            assert "white-space:nowrap!important" in h
            assert 'stroke="#E62E45"' in h
            assert "@XGPedia" in h
            assert "data:image/" in h  # لوگوی واقعی آرسنال و لیورپول

    # قانون null != 0: وقتی لیست شوت‌ها خالی باشد، ماژول‌های وابسته به مختصات شوت حذف می‌شوند
    no_shots = dict(preset, shots=[])
    mods, miss = get_shotmap_xg_modules(no_shots, "slide1")
    assert all(m["id"] != "pitch_shotmap" for m in mods)
    assert any("نقشهٔ شوت" in m for m in miss)


def test_v38_shotmap_bot_and_hashtags_wired() -> None:
    from src.xgpedia import today_workflow as tw
    from src.xgpedia.publishers import telegram_publish as tp

    assert hasattr(tw, "generate_shotmap_xg_post_async")
    assert "shotmap_xg" in tp.POST_TYPE_FA
    assert tp.HASHTAG_BY_TYPE.get("shotmap_xg") == "#نقشه_شوت"

    mb_txt = Path("src/xgpedia/publishers/modular_cards_bot.py").read_text(encoding="utf-8")
    assert '"shotmap_xg": {' in mb_txt and '"prefix": "sm"' in mb_txt and '"cmd": "shotmap"' in mb_txt
    assert "generate_shotmap_xg_post_async" in mb_txt

    tb_txt = Path("src/xgpedia/publishers/telegram_bot.py").read_text(encoding="utf-8")
    assert "sm:list:1" in tb_txt
