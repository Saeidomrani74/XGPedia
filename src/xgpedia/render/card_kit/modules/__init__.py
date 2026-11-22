"""رجیستری مرکزی ماژول‌های قابل استفاده مجدد XGPedia (`card_kit.modules`).

هر ماژول شامل:
  - `id`: شناسه یکتا
  - `title_fa`: عنوان فارسی برای نمایش در پنل کاستومایز تلگرام
  - `can_half`: آیا قابلیت نمایش نیم‌عرض (½) در کنار یک ماژول نیم‌عرض دیگر را دارد؟
  - `card_types`: انواع کارت‌هایی که از این ماژول استفاده می‌کنند
  - `render`: تابع تولید HTML خالص و بهینه‌شده برای نیم‌عرض و تمام‌عرض
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from src.xgpedia.render.card_kit.modules.keyduel import render_keyduel
from src.xgpedia.render.card_kit.modules.poisson import render_poisson
from src.xgpedia.render.card_kit.modules.post_modules import (
    render_efficiency,
    render_momentum,
    render_motm,
    render_shotmap,
    render_toprated,
    render_xgrace,
)
from src.xgpedia.render.card_kit.modules.radar import render_radar
from src.xgpedia.render.card_kit.modules.signals import render_signals
from src.xgpedia.render.card_kit.modules.stats import render_stats
from src.xgpedia.render.card_kit.modules.trend10 import render_trend10, render_wave


@dataclass(frozen=True)
class ModuleSpec:
    id: str
    title_fa: str
    can_half: bool
    card_types: tuple[str, ...]
    render: Callable[[dict[str, Any], str, str], str]


MODULE_REGISTRY: dict[str, ModuleSpec] = {
    # ─── ماژول‌های پیش‌ازبازی ───
    "radar": ModuleSpec("radar", "رادار ۶ محوره تاکتیکی", True, ("preview", "pre_match"), render_radar),
    "keyduel": ModuleSpec("keyduel", "تقابل مهره‌های کلیدی", True, ("preview", "pre_match"), render_keyduel),
    "signals": ModuleSpec("signals", "سیگنال‌های ارزش (+EV)", False, ("preview", "pre_match"), render_signals),
    "wave": ModuleSpec("wave", "موج ۱۵ دقیقه‌ای xG", True, ("preview", "pre_match"), render_wave),
    "trend10": ModuleSpec("trend10", "روند xG در ۱۰ بازی اخیر", True, ("preview", "pre_match"), render_trend10),
    "stats": ModuleSpec("stats", "مقایسه شاخص‌های فنی", True, ("preview", "pre_match", "post_match"), render_stats),
    "poisson": ModuleSpec("poisson", "ماتریس پواسون ۵×۵", True, ("preview", "pre_match"), render_poisson),
    # ─── ماژول‌های پس‌ازبازی ───
    "xgrace": ModuleSpec("xgrace", "نمودار جریان امید گل", True, ("post_match",), render_xgrace),
    "shotmap": ModuleSpec("shotmap", "نقشه شوت و موقعیت‌ها", True, ("post_match",), render_shotmap),
    "momentum": ModuleSpec("momentum", "موج فشار ۵ دقیقه‌ای", True, ("post_match",), render_momentum),
    "efficiency": ModuleSpec("efficiency", "دقت ضربه و دروازه‌بان‌ها", True, ("post_match",), render_efficiency),
    "toprated": ModuleSpec("toprated", "برترین‌های زمین (Top Rated)", True, ("post_match",), render_toprated),
    "motm": ModuleSpec("motm", "ستاره زمین (MOTM)", True, ("post_match",), render_motm),
}


def render_module_html(mod_id: str, payload: dict[str, Any], span: str = "full", fmt: str = "4:5") -> str:
    spec = MODULE_REGISTRY.get(mod_id)
    if spec is None:
        return ""
    effective_span = span if (span == "half" and spec.can_half) else "full"
    return spec.render(payload, effective_span, fmt)
