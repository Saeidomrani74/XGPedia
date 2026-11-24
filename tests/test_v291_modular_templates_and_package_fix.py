"""آزمون‌های نسخهٔ 0.29.1 — رفع برش کپسول بسته مالی، ماژولار کامل (عرض نیم/کامل + ترتیب دلخواه) و ذخیره تا ۵ قالب نام‌گذاری‌شده."""
from __future__ import annotations

import pytest

from src.xgpedia import layout_templates as lt
from src.xgpedia.providers.transfer_radar_free import load_transfer_presets
from src.xgpedia.render.card_kit.transfer_radar_card import (
    get_transfer_modules,
    render_transfer_radar_html,
)


def test_saved_named_templates_crud_cap_5_and_apply():
    card_k = "test_modular_v291"
    # پاک‌سازی اسلات‌های تست قبلی
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

    # قالب ششم با نام جدید باید رد شود (سقف ۵)
    with pytest.raises(ValueError):
        lt.save_layout_template(card_k, "قالب ششم", fmt="4:5", header_mode="full", modules=mods)

    # ذخیره با نام تکراری باید همان قالب را به‌روزرسانی کند (نه خطا)
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


def test_transfer_radar_custom_order_half_width_and_unclipped_package_capsule():
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
    # کپسول بسته مالی با flex-shrink:0 و ارتفاع ۱۲px و گرید منعطف بدون برش
    assert "grid-auto-rows:minmax(0,auto)" in html_out
    assert ".mf .tr-pkg-grid" in html_out
    # ترتیب سفارشی رعایت شده (verdict قبل از package و package قبل از pipeline)
    assert html_out.index("جمع‌بندی تحریریه XGPedia") < html_out.index("بسته مالی و ساختار قرارداد")
    assert html_out.index("بسته مالی و ساختار قرارداد") < html_out.index("مسیر پیشرفت معامله")
