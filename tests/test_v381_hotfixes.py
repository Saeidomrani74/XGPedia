"""تست‌های واحد هات‌فیکس v0.38.1:
  1. رفع `KeyError: 'title'` در `modular_cards_bot.py` برای کارت‌های `matchweek_wrapup` و `shotmap_xg`
  2. جلوگیری از تشخیص اشتباه گوینده در `quote_free.py` (مثلاً `"I am really enjoying playing under Iraola"`)
  3. بازیابی عکس (`og:image` / ویکی‌پدیا) و نسبت تصویر ثابت `4:3` مطابق نمونه در `quote_card.py`
"""
from __future__ import annotations

import ast
from pathlib import Path


def test_v381_modular_cards_bot_all_specs_have_title_and_list_hint() -> None:
    src = Path("src/xgpedia/publishers/modular_cards_bot.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    specs_val = None
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "CARD_SPECS":
            specs_val = ast.literal_eval(node.value)
            break
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "CARD_SPECS" for t in node.targets):
            specs_val = ast.literal_eval(node.value)
            break
    assert isinstance(specs_val, dict) and len(specs_val) >= 12
    for kind, spec in specs_val.items():
        assert spec.get("title"), f"{kind} missing 'title'"
        assert spec.get("list_hint"), f"{kind} missing 'list_hint'"
        assert "title_fa" not in spec, f"{kind} should use 'title', not 'title_fa'"


def test_v381_quote_speaker_detection_does_not_misattribute_under_iraola() -> None:
    from src.xgpedia.providers.quote_free import extract_quote_candidate

    cand = extract_quote_candidate(
        title='Evanilson: "I am really enjoying playing under Iraola at Bournemouth"',
        description="Bournemouth striker Evanilson praised manager Andoni Iraola.",
        source_name="The Guardian",
    )
    assert cand is not None
    assert cand["speaker"] != "آندونی ایرائولا"
    assert cand["clubCode"] == "BOU"


def test_v381_quote_card_fixed_4_3_aspect_ratio_and_fallback_helpers() -> None:
    from src.xgpedia.providers.quote_free import load_quote_presets
    from src.xgpedia.render.card_kit.quote_card import render_quote_html

    preset = dict(load_quote_presets()[0])
    preset["photoSrc"] = "data:image/png;base64,iVBORw0KGgo="
    h = render_quote_html(preset, slide="slide1", fmt="4:5")
    assert "aspect-ratio:4/3" in h

    qf_src = Path("src/xgpedia/providers/quote_free.py").read_text(encoding="utf-8")
    assert "_fetch_og_image_from_article" in qf_src
    assert "_fetch_wikipedia_portrait" in qf_src
