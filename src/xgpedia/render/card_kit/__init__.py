"""معماری یکپارچه و ماژولار کارت‌های XGPedia (`card_kit`)."""
from __future__ import annotations

from src.xgpedia.render.card_kit.base_shell import render_unified_card_html
from src.xgpedia.render.card_kit.modules import MODULE_REGISTRY, ModuleSpec, render_module_html

__all__ = [
    "MODULE_REGISTRY",
    "ModuleSpec",
    "render_module_html",
    "render_unified_card_html",
]
