"""آزمون‌های نسخهٔ 0.29.1 و 0.30.1 — ماژولار کامل، ذخیره تا ۵ قالب، تطابق ۱:۱ این یا اون و رادار نقل‌وانتقالات، کد باشگاه و پاک‌سازی سیریلیک."""
from __future__ import annotations

import pathlib
import pytest

from src.xgpedia import layout_templates as lt
from src.xgpedia.providers.this_or_that_free import load_this_or_that_presets
from src.xgpedia.providers.transfer_radar_free import (
    _clean_fa_llm_text,
    _club_code,
    load_transfer_presets,
)
from src.xgpedia.render.card_kit.this_or_that_card import render_this_or_that_html
from src.xgpedia.render.card_kit.transfer_radar_card import (
    get_transfer_modules,
    render_transfer_radar_html,
)


def test_saved_named_templates_crud_cap_5_and_apply():
    card_k = "test_modular_v291"
    while lt.delete_layout_template(card_k, 0):
        pass

    mods = [
        {"id": "pipeline", "title_fa": "مسیر", "enabled": True, "can_half": False, "span": "full"},
        {"id": "package", "title_fa": "بسته مالی", "enabled": True, "can_half": True, "span": "half"},
        {"id": "verdict", "title_fa": "تحلیل", "enabled": True, "can_half": True, "span": "half"},
    ]
    for i in range(1, 6):
        lt.save_layout_template(card_k, f"قالب {i}", fmt="4:5", header_mode="full", modules=mods)
    assert len(lt.list_layout_templates(card_k)) == 5

    with pytest.raises(ValueError):
        lt.save_layout_template(card_k, "قالب ششم", fmt="4:5", header_mode="full", modules=mods)

    lt.save_layout_template(
        card_k,
        "قالب 1",
        fmt="9:16",
        header_mode="compact",
        modules=[mods[2], mods[1], mods[0]],
    )
    tpls = lt.list_layout_templates(card_k)
    assert len(tpls) == 5 and tpls[0]["fmt"] == "9:16" and tpls[0]["header_mode"] == "compact"

    applied = lt.apply_template_to_modules(mods, tpls[0])
    assert [m["id"] for m in applied] == ["verdict", "package", "pipeline"]
    assert applied[0]["span"] == "half" and applied[2]["span"] == "full"

    assert lt.delete_layout_template(card_k, 0) is True
    assert len(lt.list_layout_templates(card_k)) == 4
    while lt.delete_layout_template(card_k, 0):
        pass


def test_transfer_radar_custom_order_half_width_and_exact_1to1_fidelity():
    gyo = load_transfer_presets()[0]
    mods, _ = get_transfer_modules(gyo, "slide1")
    pkg = next(m for m in mods if m["id"] == "package")
    assert pkg["can_half"] is True

    custom_order = [
        {"id": "verdict", "enabled": True, "span": "half"},
        {"id": "package", "enabled": True, "span": "half"},
        {"id": "pipeline", "enabled": True, "span": "full"},
    ]
    html_out = render_transfer_radar_html(gyo, fmt="4:5", header_mode="full", custom_modules=custom_order)
    # ساختار ۱:۱ گرید و کپسول پرداخت بدون برش
    assert "grid-auto-rows:1fr" in html_out
    assert "flex-shrink:0" in html_out
    assert ".mf .tr-pkg-grid" in html_out
    # جزئیات گرافیکی ۱:۱ رادار نقل‌وانتقالات
    assert "M830 155Q490 12 150 155" in html_out  # قوس پروازی نقطه‌چین بین باشگاه‌ها
    assert 'id="swg"' in html_out  # سکتور چرخان رادار
    assert "tr-v-wm" in html_out  # واترمارک سیبل رادار در جمع‌بندی تحریریه
    assert ".tr-hero-full{position:relative;border-radius:28px;background:transparent !important;" in html_out  # شفافیت دقیق کادر بالایی طبق HTML اصلی
    assert 'viewBox="0 0 24 24"' in html_out  # آیکون رادار در تگ هدر
    # ترتیب سفارشی
    assert html_out.index("جمع‌بندی تحریریه XGPedia") < html_out.index("بسته مالی و ساختار قرارداد")
    assert html_out.index("بسته مالی و ساختار قرارداد") < html_out.index("مسیر پیشرفت معامله")


def test_this_or_that_exact_1to1_fidelity_and_bot_json_import():
    preset = load_this_or_that_presets()[0]
    html_out = render_this_or_that_html(preset, layout="diagonal", fmt="4:5")
    assert "tt-wm-a" in html_out  # واترمارک شماره بزرگ پس‌زمینه
    assert 'x1="596"' in html_out  # خط مورب نقطه‌چین موازی
    assert "tt-cta-ico" in html_out  # باکس آیکون گفت‌وگو در CTA
    assert "tt-c-shine" in html_out or "linearGradient" in html_out

    # اطمینان از وجود import json در telegram_bot.py
    bot_src = pathlib.Path("src/xgpedia/publishers/telegram_bot.py").read_text(encoding="utf-8")
    assert "\nimport json\n" in bot_src

    # کدهای تمیز باشگاه و پاک‌سازی سیریلیک
    assert _club_code("آرسنال/پاری‌سن ژرمن") == "ARS"
    assert _club_code("رش لایپزیگ") == "RBL"
    assert _club_code("چلسی") == "CHE"
    assert "указыва" not in _clean_fa_llm_text("منابع خبری указыва که مذاکرات آغاز شده است.")
