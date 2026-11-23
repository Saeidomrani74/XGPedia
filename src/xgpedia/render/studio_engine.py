"""موتور رندر مستقیم از قالب‌های استودیویی HTML (`studio_templates/`).

این ماژول فایل‌های HTML استودیو (مانند `studio_templates/pre_match.html` و
`studio_templates/post_match.html`) را **عیناً و بدون تغییر طراحی** می‌خواند،
فونت‌های محلی `brand/fonts/` و داده‌های واقعی مسابقه را تزریق می‌کند، ماژول‌ها
را دقیقاً بر اساس اولویت تعریف‌شده و تکمیل‌بودن داده‌های واقعی انتخاب می‌کند،
و فقط بوم نهایی `#ea` را در ابعاد دقیق فرمت (4:5، 9:16، 16:9) خروجی می‌دهد.

قواعد کلیدی:
  - هیچ دیتای هاردکدی روی کارت باقی نمی‌ماند؛ فقط داده‌های واقعی و معتبر.
  - هیچ ماژولی حذف نمی‌شود؛ اما فقط ماژول‌هایی که دیتای کامل دارند نمایش داده می‌شوند.
  - نیم‌فضای خالی (orphan half-width) در هیچ فرمتی مجاز نیست؛ خودکار تمام‌عرض می‌شود.
  - `watchout` (باید حواسشون بهش باشه) و `autopsy` (روایت آماری و گره تاکتیکی بازی)
    هرگز روی کارت نمایش داده نمی‌شوند و به‌صورت خودکار به متن کپشن اضافه می‌شوند.
"""
from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

from src.xgpedia.config import ROOT

STUDIO_TEMPLATES_DIR = Path(
    os.environ.get("XGPEDIA_STUDIO_TEMPLATES_DIR") or (ROOT / "studio_templates")
)
FONTS_DIR = ROOT / "brand" / "fonts"

# نگاشت نوع کارت به نام فایل در پوشه studio_templates/
TEMPLATE_FILENAME_BY_TYPE: dict[str, str] = {
    "preview": "pre_match.html",
    "pre_match": "pre_match.html",
    "post_match": "post_match.html",
}

# ─── ترتیب اولویت ماژول‌ها (دقیقاً مطابق دستور کاربر) ───

PRE_MATCH_PRIORITY: list[str] = [
    "radar",     # ۱ - رادار ۶ محوره تاکتیکی
    "keyduel",   # ۲ - تقابل مهره‌های کلیدی
    "signals",   # ۳ - سیگنال‌های آماری و ارزش بازار (+EV)
    "wave",      # ۴ - موج زمانی امید گل (۱۵ دقیقه‌ای)
    "trend10",   # ۵ - روند امید گل در ۱۰ بازی اخیر
    "stats",     # ۶ - مقایسه شاخص‌های فنی (xG / xGA / SOT)
    "poisson",   # ۷ - ماتریس احتمال دقیق نتیجه (پواسون ۵×۵)
]
PRE_MATCH_CAPTION_ONLY: set[str] = {"watchout"}  # ۸ - باید حواسشون بهش باشه → فقط در کپشن

POST_MATCH_PRIORITY: list[str] = [
    "xgrace",      # ۱ - نمودار جریان امید گل (xG Race)
    "shotmap",     # ۲ - نقشه شوت و کیفیت موقعیت‌ها
    "momentum",    # ۳ - موج فشار و برتری حملات (۵ دقیقه‌ای)
    "efficiency",  # ۴ - دقت ضربه نهایی و عملکرد دروازه‌بان‌ها
    "toprated",    # ۵ - برترین‌های زمین (Top Rated — تک‌خطی)
    "motm",        # ۶ - ستاره زمین (MOTM) و رقیب برتر
    "stats",       # ۷ - آمار کلیدی مسابقه (۹۰ دقیقه)
]
POST_MATCH_CAPTION_ONLY: set[str] = {"autopsy"}  # ۸ - روایت آماری و گره تاکتیکی بازی → فقط در کپشن

# ظرفیت هر فرمت برای جلوگیری از سرریز و حفظ خوانایی موبایل
FORMAT_CAPACITY_FULL: dict[str, int] = {"4:5": 2, "9:16": 3, "16:9": 2}
FORMAT_CAPACITY_COMPACT: dict[str, int] = {"4:5": 3, "9:16": 4, "16:9": 2}

FORMATS: dict[str, tuple[int, int]] = {
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}


def resolve_studio_template(
    card_type: str, template_dir: str | Path | None = None
) -> Path:
    """یافتن فایل HTML استودیو متناظر با نوع کارت از پوشه studio_templates/."""
    base = Path(template_dir) if template_dir is not None else STUDIO_TEMPLATES_DIR
    filename = TEMPLATE_FILENAME_BY_TYPE.get(card_type, f"{card_type}.html")
    path = base / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Studio HTML template not found: {path}. "
            f"Place '{filename}' inside '{base}'."
        )
    return path


# قالب پیش‌فرض رسمی و قفل‌شدهٔ کارت پیش‌ازبازی (D43) برای خودکارسازی و کاستومایزر
DEFAULT_PRE_MATCH_TEMPLATE: list[tuple[str, str]] = [
    ("radar", "half"),
    ("trend10", "half"),
    ("signals", "full"),
]
DEFAULT_PRE_MATCH_HEADER_MODE: str = "full"
# قالب پیش‌فرض رسمی و قفل‌شدهٔ کارت پس‌ازبازی (D44) برای خودکارسازی و کاستومایزر
DEFAULT_POST_MATCH_TEMPLATE: list[tuple[str, str]] = [
    ("momentum", "half"),
    ("stats", "half"),
    ("toprated", "half"),
    ("efficiency", "half"),
]
DEFAULT_PRE_MATCH_BROADCAST_FALLBACK: str = "پخش آنلاین"


def _fix_orphan_halves(modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """جلوگیری کامل از نیم‌فضای خالی در گرید ۲ ستونه (#mg).

    هر ماژول نیم‌عرض (half) که در ردیف خودش جفت نیم‌عرض نداشته باشد، خودکار به
    تمام‌عرض (full) ارتقا می‌یابد تا هیچ نیم‌فضای خالی در کارت باقی نماند.
    """
    enabled = [m for m in modules if m.get("enabled")]
    i = 0
    while i < len(enabled):
        cur = enabled[i]
        if cur.get("span") == "half":
            if i + 1 < len(enabled) and enabled[i + 1].get("span") == "half":
                i += 2  # جفت کامل نیم‌عرض در یک ردیف
                continue
            cur["span"] = "full"  # نیم‌عرض یتیم → تمام‌عرض
        i += 1
    return modules


def select_studio_modules(
    card_type: str,
    has: dict[str, bool],
    fmt: str = "4:5",
    layout: str = "smart",
    header_mode: str = "full",
) -> list[dict[str, Any]]:
    """انتخاب ماژول‌های کارت بر اساس اولویت تعریف‌شده و تکمیل‌بودن دیتای واقعی.

    - ماژول‌های مخصوص کپشن (`watchout` در پیش‌ازبازی و `autopsy` در پس‌ازبازی)
      هرگز روی کارت فعال نمی‌شوند.
    - در حالت `smart` (پیش‌فرض): به ترتیب اولویت کاربر تا ظرفیت فرمت، فقط ماژول‌های
      دارای دیتای کامل انتخاب می‌شوند و تمام‌عرض (بدون نیم‌فضای خالی) چیده می‌شوند.
    - در حالت‌های صریح (`v1`/`v2`/`v3`): فقط ماژول‌های دارای دیتای کامل روشن می‌شوند
      و نیم‌عرض‌های یتیم خودکار تمام‌عرض می‌گردند.
    """
    is_post = card_type == "post_match"
    priority = POST_MATCH_PRIORITY if is_post else PRE_MATCH_PRIORITY
    caption_only = POST_MATCH_CAPTION_ONLY if is_post else PRE_MATCH_CAPTION_ONLY

    cap_map = FORMAT_CAPACITY_COMPACT if header_mode == "compact" else FORMAT_CAPACITY_FULL
    capacity = cap_map.get(fmt, 2)

    if layout == "smart":
        if not is_post:
            # قالب پیش‌فرض قفل‌شدهٔ XGPedia (D43): رادار تاکتیکی ½ + روند xG اخیر ½ | سیگنال‌های ارزش ۱
            selected: list[dict[str, Any]] = []
            used: set[str] = set()
            for mod_id, span in DEFAULT_PRE_MATCH_TEMPLATE:
                if mod_id not in caption_only and has.get(mod_id, False):
                    selected.append({"id": mod_id, "enabled": True, "span": span})
                    used.add(mod_id)
            if len(selected) < 2:
                for mod_id in priority:
                    if mod_id not in caption_only and mod_id not in used and has.get(mod_id, False):
                        selected.append({"id": mod_id, "enabled": True, "span": "full"})
                        used.add(mod_id)
                        if len(selected) >= capacity:
                            break
            return _fix_orphan_halves(selected)
        # قالب پیش‌فرض قفل‌شدهٔ پس‌ازبازی (D44): موج فشار ½ + آمار مسابقه ½ | برترین‌های زمین ½ + دقت شوت و دروازه‌بان ½
        selected_pm: list[dict[str, Any]] = []
        used_pm: set[str] = set()
        for mod_id, span in DEFAULT_POST_MATCH_TEMPLATE:
            if mod_id not in caption_only and has.get(mod_id, False):
                selected_pm.append({"id": mod_id, "enabled": True, "span": span})
                used_pm.add(mod_id)
        if len(selected_pm) < 2:
            for mod_id in priority:
                if mod_id not in caption_only and mod_id not in used_pm and has.get(mod_id, False):
                    selected_pm.append({"id": mod_id, "enabled": True, "span": "full"})
                    used_pm.add(mod_id)
                    if len(selected_pm) >= capacity:
                        break
        return _fix_orphan_halves(selected_pm)

    if is_post:
        presets: dict[str, list[tuple[str, str]]] = {
            "v1": [("xgrace", "full"), ("shotmap", "full"), ("stats", "full")],
            "v2": [("momentum", "full"), ("efficiency", "full"), ("stats", "full")],
            "v3": [("toprated", "full"), ("motm", "full"), ("stats", "full")],
        }
    else:
        presets = {
            "v1": [("radar", "full"), ("keyduel", "full"), ("stats", "full")],
            "v2": [("stats", "full"), ("poisson", "full"), ("signals", "full")],
            "v3": [("trend10", "full"), ("wave", "full"), ("stats", "full")],
        }

    preset_spec = presets.get(layout, presets["v1"])
    selected = []
    for mod_id, span in preset_spec:
        if mod_id in caption_only:
            continue
        if has.get(mod_id, False):
            selected.append({"id": mod_id, "enabled": True, "span": span})
        if len(selected) >= capacity:
            break
    # اگر از پریست صریح چیزی داده نداشت، با اولویت هوشمند پر کن تا کارت خالی نماند
    if not selected:
        for mod_id in priority:
            if mod_id not in caption_only and has.get(mod_id, False):
                selected.append({"id": mod_id, "enabled": True, "span": "full"})
                if len(selected) >= capacity:
                    break
    return _fix_orphan_halves(selected)


# ─── ساخت کپشن با انتقال watchout و autopsy به کپشن ───

def build_card_caption(
    draft: dict[str, Any],
    facts: dict[str, Any],
    post_type: str = "preview",
) -> str:
    """ساخت متن کپشن نهایی: کپشن اصلی + متن هشدارها (پیش‌ازبازی) یا روایت تاکتیکی (پس‌ازبازی).

    طبق الزام کاربر:
      - «باید حواسشون بهش باشه» (watchout) فقط در کپشن پیش‌ازبازی می‌آید و نه روی کارت.
      - «روایت آماری و گره تاکتیکی بازی» (autopsy) فقط در کپشن پس‌ازبازی می‌آید و نه روی کارت.
    """
    parts: list[str] = []
    base_caption = (draft.get("caption") or "").strip()
    if base_caption:
        parts.append(base_caption)

    if post_type in ("preview", "pre_match"):
        watch_lines: list[str] = []
        home_f = facts.get("home") or {}
        away_f = facts.get("away") or {}
        h_name = home_f.get("name_fa") or "میزبان"
        a_name = away_f.get("name_fa") or "میهمان"

        d_watch = draft.get("watchout")
        if isinstance(d_watch, dict):
            if d_watch.get("home"):
                watch_lines.append(f"• {h_name}: {str(d_watch['home']).strip()}")
            if d_watch.get("away"):
                watch_lines.append(f"• {a_name}: {str(d_watch['away']).strip()}")
        elif isinstance(d_watch, str) and d_watch.strip():
            watch_lines.append(d_watch.strip())
        elif isinstance(d_watch, list):
            for item in d_watch:
                if str(item).strip():
                    watch_lines.append(f"• {str(item).strip()}")

        if not watch_lines:
            if home_f.get("watchout"):
                watch_lines.append(f"• {h_name}: {str(home_f['watchout']).strip()}")
            if away_f.get("watchout"):
                watch_lines.append(f"• {a_name}: {str(away_f['watchout']).strip()}")

        if watch_lines:
            block = "⚠️ باید حواسشون بهش باشه:\n" + "\n".join(watch_lines)
            if block not in base_caption:
                parts.append(block)

    elif post_type == "post_match":
        autopsy_lines: list[str] = []
        d_autopsy = draft.get("autopsy") or draft.get("story") or facts.get("story")
        if isinstance(d_autopsy, dict):
            title = str(d_autopsy.get("title") or "").strip()
            body = str(d_autopsy.get("body") or "").strip()
            tag = str(d_autopsy.get("tag") or "").strip()
            if title:
                autopsy_lines.append(title)
            if body and body not in base_caption:
                autopsy_lines.append(body)
            if tag and tag not in base_caption:
                autopsy_lines.append(f"نکته کلیدی: {tag}")
        elif isinstance(d_autopsy, str) and d_autopsy.strip():
            autopsy_lines.append(d_autopsy.strip())
        else:
            title = str(draft.get("title") or "").strip()
            bullets = [str(b).strip() for b in (draft.get("bullets") or []) if str(b).strip()]
            if title and title not in base_caption:
                autopsy_lines.append(title)
            for b in bullets:
                if b not in base_caption:
                    autopsy_lines.append(f"• {b}")

        if autopsy_lines:
            block = "🎯 روایت آماری و گره تاکتیکی بازی:\n" + "\n".join(autopsy_lines)
            parts.append(block)

    tag_map = {
        "preview": "#پیش_بازی",
        "pre_match": "#پیش_بازی",
        "post_match": "#پس_از_بازی",
        "number_of_day": "#عدد_روز",
    }
    tag = tag_map.get(post_type)
    body_text = "\n\n".join(p for p in parts if p)
    if tag and tag not in body_text:
        return f"{body_text}\n\n{tag}" if body_text else tag
    return body_text


# ─── فونت‌های محلی خودبسنده ───

def build_embedded_font_css() -> str:
    """تولید بلوک @font-face از فونت‌های محلی brand/fonts/ برای رندر بدون اینترنت."""
    font_specs = (
        ("Vazirmatn-Regular.woff2", "Vazirmatn", "400"),
        ("Vazirmatn-Medium.woff2", "Vazirmatn", "500"),
        ("Vazirmatn-Bold.woff2", "Vazirmatn", "600"),
        ("Vazirmatn-Bold.woff2", "Vazirmatn", "700"),
        ("Vazirmatn-Black.woff2", "Vazirmatn", "800"),
        ("Vazirmatn-Black.woff2", "Vazirmatn", "900"),
        ("JetBrainsMono-var.woff2", "JetBrains Mono", "100 800"),
        ("SpaceGrotesk-var.woff2", "Space Grotesk", "300 800"),
    )
    cache: dict[str, str] = {}
    rules: list[str] = []
    for filename, family, weight in font_specs:
        path = FONTS_DIR / filename
        if not path.exists():
            continue
        if filename not in cache:
            cache[filename] = base64.b64encode(path.read_bytes()).decode("ascii")
        rules.append(
            f"@font-face{{font-family:'{family}';font-weight:{weight};"
            f"font-display:swap;src:url('data:font/woff2;base64,{cache[filename]}') format('woff2');}}"
        )
    return "\n".join(rules)


# ─── کامپایلر سبک پشتیبان Tailwind برای رندر آفلاین/بدون CDN ───

_TW_COLORS: dict[str, str] = {
    "white": "#ffffff",
    "black": "#000000",
    "transparent": "transparent",
    "slate-100": "#f1f5f9",
    "slate-200": "#e2e8f0",
    "slate-300": "#cbd5e1",
    "slate-400": "#94a3b8",
    "slate-500": "#64748b",
    "zinc-100": "#f4f4f5",
    "zinc-200": "#e4e4e7",
    "zinc-300": "#d4d4d8",
    "zinc-400": "#a1a1aa",
    "zinc-500": "#71717a",
    "zinc-600": "#52525b",
    "amber-200": "#fde68a",
    "amber-300": "#fcd34d",
    "amber-400": "#fbbf24",
    "amber-500": "#f59e0b",
    "emerald-200": "#a7f3d0",
    "emerald-300": "#6ee7b7",
    "emerald-400": "#34d399",
    "emerald-500": "#10b981",
    "sky-300": "#7dd3fc",
    "sky-400": "#38bdf8",
    "sky-500": "#0ea5e9",
    "rose-300": "#fda4af",
    "rose-400": "#fb7185",
}


def _tw_escape(cls: str) -> str:
    return re.sub(r"([^a-zA-Z0-9_-])", r"\\\1", cls)


def _tw_color(token: str) -> str | None:
    alpha = None
    if "/" in token:
        token, a_str = token.rsplit("/", 1)
        a_str = a_str.strip("[]")
        try:
            a_val = float(a_str)
            alpha = a_val if a_val <= 1.0 and "." in a_str else a_val / 100.0
        except ValueError:
            alpha = None
    if token.startswith("[") and token.endswith("]"):
        raw = token[1:-1]
    else:
        raw = _TW_COLORS.get(token)
    if not raw:
        return None
    if alpha is None or raw == "transparent":
        return raw
    h = raw.lstrip("#")
    if len(h) == 3:
        h = "".join(c + c for c in h)
    if len(h) != 6:
        return raw
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha:.3g})"


def _tw_spacing(val: str) -> str | None:
    if val == "px":
        return "1px"
    if val == "full":
        return "100%"
    if val == "auto":
        return "auto"
    if val.startswith("[") and val.endswith("]"):
        return val[1:-1]
    try:
        return f"{float(val) * 0.25:g}rem"
    except ValueError:
        return None


def _compile_single_tw(cls: str) -> str | None:
    """تبدیل یک کلاس Tailwind به قاعدهٔ CSS (پشتیبان آفلاین برای رندر بدون CDN)."""
    if ":" in cls and not cls.startswith("["):
        return None  # responsive/hover prefixes ignored for fixed artboard export
    sel = f".{_tw_escape(cls)}"

    static: dict[str, str] = {
        "flex": "display:flex",
        "inline-flex": "display:inline-flex",
        "grid": "display:grid",
        "block": "display:block",
        "inline": "display:inline",
        "inline-block": "display:inline-block",
        "hidden": "display:none",
        "relative": "position:relative",
        "absolute": "position:absolute",
        "fixed": "position:fixed",
        "static": "position:static",
        "flex-1": "flex:1 1 0%",
        "flex-col": "flex-direction:column",
        "flex-row": "flex-direction:row",
        "flex-wrap": "flex-wrap:wrap",
        "shrink": "flex-shrink:1",
        "shrink-0": "flex-shrink:0",
        "min-h-0": "min-height:0px",
        "min-w-0": "min-width:0px",
        "items-center": "align-items:center",
        "items-start": "align-items:flex-start",
        "items-end": "align-items:flex-end",
        "items-stretch": "align-items:stretch",
        "items-baseline": "align-items:baseline",
        "justify-center": "justify-content:center",
        "justify-between": "justify-content:space-between",
        "justify-end": "justify-content:flex-end",
        "justify-start": "justify-content:flex-start",
        "content-start": "align-content:flex-start",
        "content-center": "align-content:center",
        "auto-rows-fr": "grid-auto-rows:minmax(0,1fr)",
        "auto-rows-min": "grid-auto-rows:min-content",
        "inset-0": "inset:0px",
        "inset-x-0": "left:0px;right:0px",
        "top-0": "top:0px",
        "top-1/2": "top:50%",
        "left-1/2": "left:50%",
        "overflow-hidden": "overflow:hidden",
        "pointer-events-none": "pointer-events:none",
        "object-contain": "object-fit:contain",
        "whitespace-nowrap": "white-space:nowrap",
        "truncate": "overflow:hidden;text-overflow:ellipsis;white-space:nowrap",
        "line-clamp-1": "overflow:hidden;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:1",
        "uppercase": "text-transform:uppercase",
        "text-center": "text-align:center",
        "text-right": "text-align:right",
        "text-left": "text-align:left",
        "font-normal": "font-weight:400",
        "font-medium": "font-weight:500",
        "font-semibold": "font-weight:600",
        "font-bold": "font-weight:700",
        "font-extrabold": "font-weight:800",
        "font-black": "font-weight:900",
        "leading-none": "line-height:1",
        "leading-tight": "line-height:1.25",
        "leading-snug": "line-height:1.375",
        "leading-relaxed": "line-height:1.625",
        "tracking-tighter": "letter-spacing:-0.05em",
        "tracking-tight": "letter-spacing:-0.025em",
        "tracking-wider": "letter-spacing:0.05em",
        "border": "border-width:1px",
        "border-2": "border-width:2px",
        "border-t": "border-top-width:1px",
        "border-b": "border-bottom-width:1px",
        "border-l": "border-left-width:1px",
        "border-r": "border-right-width:1px",
        "border-t-2": "border-top-width:2px",
        "border-b-2": "border-bottom-width:2px",
        "text-xs": "font-size:0.75rem;line-height:1rem",
        "text-sm": "font-size:0.875rem;line-height:1.25rem",
        "text-base": "font-size:1rem;line-height:1.5rem",
        "border-dashed": "border-style:dashed",
        "rounded": "border-radius:0.25rem",
        "rounded-md": "border-radius:0.375rem",
        "rounded-lg": "border-radius:0.5rem",
        "rounded-xl": "border-radius:0.75rem",
        "rounded-2xl": "border-radius:1rem",
        "rounded-3xl": "border-radius:1.5rem",
        "rounded-full": "border-radius:9999px",
        "rotate-45": "transform:rotate(45deg)",
        "-translate-x-1/2": "transform:translateX(-50%)",
        "-translate-y-1/2": "transform:translateY(-50%)",
        "shadow-inner": "box-shadow:inset 0 2px 4px 0 rgba(0,0,0,0.25)",
        "shadow-lg": "box-shadow:0 10px 15px -3px rgba(0,0,0,0.3)",
        "shadow-xl": "box-shadow:0 20px 25px -5px rgba(0,0,0,0.35)",
        "bg-gradient-to-b": "background-image:linear-gradient(to bottom,var(--tw-gradient-from,transparent),var(--tw-gradient-to,transparent))",
    }
    if cls in static:
        return f"{sel}{{{static[cls]}}}"

    # z-index
    m = re.fullmatch(r"z-(\d+)", cls)
    if m:
        return f"{sel}{{z-index:{m.group(1)}}}"

    # grid-cols / col-span
    m = re.fullmatch(r"grid-cols-(\d+)", cls)
    if m:
        return f"{sel}{{grid-template-columns:repeat({m.group(1)},minmax(0,1fr))}}"
    m = re.fullmatch(r"col-span-(\d+)", cls)
    if m:
        return f"{sel}{{grid-column:span {m.group(1)} / span {m.group(1)}}}"

    # gap
    m = re.fullmatch(r"gap-(.+)", cls)
    if m:
        sp = _tw_spacing(m.group(1))
        if sp:
            return f"{sel}{{gap:{sp}}}"

    # space-y
    m = re.fullmatch(r"space-y-(.+)", cls)
    if m:
        sp = _tw_spacing(m.group(1))
        if sp:
            return f"{sel}>*+*{{margin-top:{sp}}}"

    # padding & margin
    m = re.fullmatch(r"(-?)(p|m)(x|y|t|b|l|r)?-(.+)", cls)
    if m:
        neg, kind, side, raw_v = m.groups()
        sp = _tw_spacing(raw_v)
        if sp:
            if neg:
                sp = f"-{sp}"
            prop = "padding" if kind == "p" else "margin"
            if side is None:
                return f"{sel}{{{prop}:{sp}}}"
            if side == "x":
                return f"{sel}{{{prop}-left:{sp};{prop}-right:{sp}}}"
            if side == "y":
                return f"{sel}{{{prop}-top:{sp};{prop}-bottom:{sp}}}"
            smap = {"t": "top", "b": "bottom", "l": "left", "r": "right"}
            return f"{sel}{{{prop}-{smap[side]}:{sp}}}"

    # width / height / min / max
    m = re.fullmatch(r"(min-|max-)?(w|h)-(.+)", cls)
    if m:
        prefix, dim, raw_v = m.groups()
        sp = _tw_spacing(raw_v)
        if sp:
            prop = f"{prefix or ''}{'width' if dim == 'w' else 'height'}"
            return f"{sel}{{{prop}:{sp}}}"

    # top / bottom / left / right
    m = re.fullmatch(r"(-?)(top|bottom|left|right)-(.+)", cls)
    if m:
        neg, side, raw_v = m.groups()
        sp = _tw_spacing(raw_v)
        if sp:
            return f"{sel}{{{side}:{'-' if neg else ''}{sp}}}"

    # text-[Npx] or text-color
    m = re.fullmatch(r"text-\[([^\]]+)\]", cls)
    if m:
        v = m.group(1)
        if v.startswith("#"):
            return f"{sel}{{color:{v}}}"
        return f"{sel}{{font-size:{v}}}"
    if cls.startswith("text-"):
        col = _tw_color(cls[5:])
        if col:
            return f"{sel}{{color:{col}}}"

    # leading-[...] / tracking-[...] / rounded-[...] / opacity-[...]
    m = re.fullmatch(r"leading-\[([^\]]+)\]", cls)
    if m:
        return f"{sel}{{line-height:{m.group(1)}}}"
    m = re.fullmatch(r"tracking-\[([^\]]+)\]", cls)
    if m:
        return f"{sel}{{letter-spacing:{m.group(1)}}}"
    m = re.fullmatch(r"rounded-\[([^\]]+)\]", cls)
    if m:
        return f"{sel}{{border-radius:{m.group(1)}}}"
    m = re.fullmatch(r"opacity-\[([^\]]+)\]", cls)
    if m:
        return f"{sel}{{opacity:{m.group(1)}}}"

    # bg / border / from / to colors
    if cls.startswith("bg-"):
        col = _tw_color(cls[3:])
        if col:
            return f"{sel}{{background-color:{col}}}"
    if cls.startswith("border-"):
        col = _tw_color(cls[7:])
        if col:
            return f"{sel}{{border-color:{col}}}"
    if cls.startswith("from-"):
        col = _tw_color(cls[5:])
        if col:
            return f"{sel}{{--tw-gradient-from:{col}}}"
    if cls.startswith("to-"):
        col = _tw_color(cls[3:])
        if col:
            return f"{sel}{{--tw-gradient-to:{col}}}"

    # shadow-[...] / drop-shadow-[...]
    m = re.fullmatch(r"shadow-\[([^\]]+)\]", cls)
    if m:
        return f"{sel}{{box-shadow:{m.group(1).replace('_', ' ')}}}"
    m = re.fullmatch(r"drop-shadow-\[([^\]]+)\]", cls)
    if m:
        return f"{sel}{{filter:drop-shadow({m.group(1).replace('_', ' ')})}}"

    return None


def build_tailwind_fallback_css(html_source: str) -> str:
    """تولید CSS پشتیبان برای تمام کلاس‌های Tailwind موجود در قالب استودیو (برای رندر آفلاین)."""
    tokens: set[str] = set()
    # استخراج از class="..." و رشته‌های کلاس داخل JS
    for m in re.finditer(r'class=["\']([^"\']+)["\']', html_source):
        for tok in m.group(1).split():
            if "${" not in tok:
                tokens.add(tok)
    for m in re.finditer(r'class="([^"`]+)"', html_source):
        for tok in m.group(1).split():
            if "${" not in tok:
                tokens.add(tok)
    # استخراج رشته‌های کلاس رایج داخل ternaryهای JS (مثل "text-[28px]" یا "col-span-4")
    for m in re.finditer(
        r'["\']((?:col-span-\d+|grid-cols-\d+|text-\[[^\]]+\]|p[xybtlr]?-\[?[\d.]+\w*\]?|'
        r'm[xybtlr]?-\[?[\d.]+\w*\]?|gap-[\d.]+|space-y-[\d.]+|rounded-[\w\[\]]+|'
        r'w-\[?[\d.]+\w*\]?|h-\[?[\d.]+\w*\]?|max-w-\[?[\d.]+\w*\]?|min-w-\[?[\d.]+\w*\]?|'
        r'leading-\[?[\w.]+\]?|bg-[\w#/\[\].-]+|border-[\w#/\[\].-]+|text-[\w#/\[\].-]+|'
        r'from-[\w#/\[\].-]+|to-[\w#/\[\].-]+|shadow-\[[^\]]+\]|drop-shadow-\[[^\]]+\]|'
        r'font-\w+|flex-1|flex-col|hidden|inline|inline-flex|auto-rows-\w+|content-\w+)[^"\']*)["\']',
        html_source,
    ):
        for tok in m.group(1).split():
            if "${" not in tok and len(tok) <= 64:
                tokens.add(tok)

    preflight = (
        "*,::before,::after{box-sizing:border-box;border-width:0;border-style:solid;border-color:rgba(255,255,255,0.12)}"
        "h1,h2,h3,h4,h5,h6,p{margin:0;font-size:inherit;font-weight:inherit}"
        "svg,img{display:block;vertical-align:middle}"
    )
    rules = [preflight]
    for cls in sorted(tokens):
        rule = _compile_single_tw(cls)
        if rule:
            rules.append(rule)
    return "\n".join(rules)


# ─── تزریق داده و حالت خروجی به فایل HTML استودیو ───

def _export_mode_css(w: int, h: int) -> str:
    """CSS حالت خروجی — مخفی‌کردن کامل UI استودیو و قفل‌کردن بوم #ea در ابعاد دقیق W×H."""
    return f"""
/* XGPedia Export Mode — renders #ea edge-to-edge at exact {w}x{h} */
aside#sb, aside#sp, main#sc > div:first-child, main#sc > div:last-child,
nav, #ts, #to, #szo, #sz {{ display: none !important; }}
html, body {{
  width: {w}px !important; height: {h}px !important;
  margin: 0 !important; padding: 0 !important;
  overflow: hidden !important; background: #000 !important;
}}
body > div, main#sc, #vp, #vp > div, #aw {{
  position: static !important; width: {w}px !important; height: {h}px !important;
  margin: 0 !important; padding: 0 !important; border-radius: 0 !important;
  box-shadow: none !important; overflow: hidden !important; background: transparent !important;
  display: block !important; max-width: none !important; max-height: none !important;
}}
#ea {{
  position: fixed !important; top: 0 !important; left: 0 !important;
  width: {w}px !important; height: {h}px !important;
  transform: none !important; transition: none !important;
}}
"""


_POST_RENDER_JS = r"""
window.__XGPEDIA_POST_RENDER__ = function(P) {
  const ea = document.getElementById('ea');
  const mg = document.getElementById('mg');
  const hs = document.getElementById('hs');
  const fa = v => String(v).replace(/\d/g, d => '۰۱۲۳۴۵۶۷۸۹'[d]);

  // 1) Clean empty optional header pills (round, stadium, broadcast, time)
  const cr = document.getElementById('cr');
  if (cr && !cr.textContent.trim()) cr.style.display = 'none';
  const cb = document.getElementById('cb');
  if (cb && !cb.textContent.trim()) cb.style.display = 'none';
  const cs = document.getElementById('cs');
  if (cs && !cs.textContent.trim()) {
    const wrap = cs.parentElement;
    if (wrap) {
      if (wrap.previousElementSibling && wrap.previousElementSibling.textContent.trim() === '•') {
        wrap.previousElementSibling.style.display = 'none';
      }
      wrap.style.display = 'none';
    }
  }
  const cd = document.getElementById('cd');
  if (cd && P.dateLineOverride != null) {
    cd.textContent = P.dateLineOverride;
  }

  // 2) Handle missing probabilities / xG cleanly (null != 0)
  if (!P.hasProbs && hs) {
    hs.querySelectorAll('.pc').forEach(el => {
      const parent = el.parentElement;
      if (parent && parent !== hs && parent.querySelectorAll('.pc').length === 1) {
        parent.style.display = 'none';
      } else {
        el.style.display = 'none';
      }
    });
    const hx = hs.querySelector('.hx');
    if (hx) hx.style.display = 'none';
  }

  // 3) Post-Match: never show "بدون گل زده" when a team actually scored > 0 goals (missing scorer names)
  if (P.cardType === 'post_match' && hs && P.match) {
    const teamCols = hs.querySelectorAll('.col-span-4');
    if (teamCols.length >= 3) {
      [[teamCols[0], P.match.scoreHome, P.match.home && P.match.home.scorersText],
       [teamCols[2], P.match.scoreAway, P.match.away && P.match.away.scorersText]].forEach(([col, sc, txt]) => {
        if (Number(sc) > 0 && !(txt || '').trim()) {
          col.querySelectorAll('div').forEach(d => {
            if (d.textContent.trim() === 'بدون گل زده') d.style.display = 'none';
          });
        }
      });
    }
  }

  // 4) Replace stats rows with ONLY real non-null pairs (prevents null -> 0.00)
  if (Array.isArray(P.statsRows) && mg) {
    const modCards = Array.from(mg.children);
    const enabledMods = (P.modules || []).filter(m => m.enabled);
    enabledMods.forEach((mod, idx) => {
      const card = modCards[idx];
      if (!card) return;
      if (mod.id === 'stats' && P.statsRows.length > 0) {
        const hc = P.match.home.color;
        const ac = P.match.away.color;
        const body = card.children[1];
        if (body) {
          if (P.cardType === 'post_match') {
            body.innerHTML = P.statsRows.map(r => (
              `<div class="space-y-1.5">` +
              `<div class="grid grid-cols-3 items-center">` +
              `<span class="text-right text-[27px] bk leading-none" style="color:${hc}">${fa(r.h)}</span>` +
              `<span class="text-center text-[21px] eb text-zinc-100 leading-tight nw">${r.label}</span>` +
              `<span class="text-left text-[27px] bk leading-none" style="color:${ac}">${fa(r.a)}</span>` +
              `</div>` +
              `<div class="grid grid-cols-2 gap-2">` +
              `<div class="cbt hsd"><div class="cbh" style="width:${r.h_pct}%;background:linear-gradient(90deg,${hc}B8,${hc})"></div></div>` +
              `<div class="cbt asd"><div class="cba" style="width:${r.a_pct}%;background:linear-gradient(270deg,${ac}B8,${ac})"></div></div>` +
              `</div></div>`
            )).join('');
          } else {
            body.innerHTML = P.statsRows.map(r => (
              `<div class="space-y-2">` +
              `<div class="grid grid-cols-3 items-center">` +
              `<span class="text-right text-[34px] font-black leading-none" style="color:${hc}">${fa(r.h)}</span>` +
              `<span class="text-center text-[24px] font-extrabold text-slate-100 leading-tight">${r.label}</span>` +
              `<span class="text-left text-[34px] font-black leading-none" style="color:${ac}">${fa(r.a)}</span>` +
              `</div>` +
              `<div class="grid grid-cols-2 gap-2">` +
              `<div class="ct hs"><div class="ch" style="width:${r.h_pct}%;background:${hc}"></div></div>` +
              `<div class="ct as"><div class="ca" style="width:${r.a_pct}%;background:${ac}"></div></div>` +
              `</div></div>`
            )).join('');
          }
        }
      }
      // Replace Pre-Match signals rows with REAL bookmaker odds + true EV (never simulated)
      if (mod.id === 'signals' && Array.isArray(P.signalsItems) && P.signalsItems.length > 0) {
        const el = card.querySelector('.el');
        if (el) {
          const br = (lb, lc, k, pct) => {
            const n = Math.min(100, pct), tx = fa(pct.toFixed(1)) + '٪', inB = n >= 70;
            return `<div class="ebr"><span class="ebl ${lc}">${lb}</span><div class="ebt"><div class="ef${k}" style="width:${n.toFixed(1)}%">${inB ? `<span class="evv ei${k}">${tx}</span>` : ''}</div>${inB ? '' : `<span class="evv eo${k}">${tx}</span>`}</div></div>`;
          };
          el.innerHTML = P.signalsItems.map(it => (
            `<div class="er"><div class="min-w-0 text-right"><div class="et">${it.title}</div>` +
            `<div class="em">ضریب ${fa(it.odds.toFixed(2))} · معادل ${fa(it.market_pct.toFixed(1))}٪</div></div>` +
            `<div class="ebc">${br('احتمال سنجی مدل','text-slate-300','m',it.model_pct)}${br('احتمال سنجی بازار','text-slate-400','k',it.market_pct)}</div>` +
            `<div class="epw ${it.tier_class}"><div dir="ltr" class="epb"><span>+${fa(it.ev_pct.toFixed(1))}٪</span><span class="ept">EV</span></div>` +
            `<span class="eps">${it.tier_label}</span></div></div>`
          )).join('');
        }
      }
    });
  }

  // 5) Enforce ZERO empty half-spaces in #mg grid across ALL formats (4:5, 9:16, 16:9)
  if (mg) {
    const kids = Array.from(mg.children);
    if (P.fmt === '16:9') {
      mg.style.gridAutoRows = 'minmax(0, 1fr)';
    }
    let i = 0;
    while (i < kids.length) {
      const k = kids[i];
      const isHalf = k.classList.contains('mf') || k.classList.contains('mh2') || k.classList.contains('col-span-1');
      if (isHalf) {
        const next = kids[i + 1];
        const nextHalf = next && (next.classList.contains('mf') || next.classList.contains('mh2') || next.classList.contains('col-span-1'));
        if (nextHalf) {
          i += 2;
          continue;
        }
        k.classList.remove('mf', 'mh2', 'col-span-1');
        k.classList.add(P.cardType === 'post_match' ? 'mf2' : 'w-full', 'col-span-2');
        k.style.gridColumn = '1 / -1';
      } else {
        k.style.gridColumn = '1 / -1';
      }
      i += 1;
    }
  }

  // 6) Anti-overflow safety guard: if any content slightly exceeds #ea height, activate compact density class
  if (ea && (ea.scrollHeight > ea.clientHeight + 2)) {
    ea.classList.add(P.cardType === 'post_match' ? 'dn' : 'dc');
  }
};
"""


def render_from_studio_template(
    card_type: str,
    payload: dict[str, Any],
    template_dir: str | Path | None = None,
) -> str:
    """تولید HTML نهایی دقیقاً از روی فایل استودیویی داخل پوشه studio_templates/.

    - فایل منبع در `studio_templates/` را دست‌نخورده می‌خواند.
    - فونت‌های محلی `brand/fonts/` را به‌صورت data URI تزریق می‌کند.
    - CSS پشتیبان Tailwind را برای رندر آفلاین/بدون CDN اضافه می‌کند.
    - CSS حالت خروجی (فقط `#ea` در ابعاد دقیق فرمت) را تزریق می‌کند.
    - payload دیتای واقعی و لیست ماژول‌های اولویت‌بندی‌شده را به اسکریپت استودیو تزریق می‌کند.
    """
    tpl_path = resolve_studio_template(card_type, template_dir=template_dir)
    html = tpl_path.read_text(encoding="utf-8")

    fmt = payload.get("fmt", "4:5")
    w, h = FORMATS.get(fmt, FORMATS["4:5"])

    font_css = build_embedded_font_css()
    tw_fallback_css = build_tailwind_fallback_css(html)
    export_css = _export_mode_css(w, h)

    # حذف لینک‌های خارجی Google Fonts و Tailwind CDN از خروجی نهایی تا رندر ۱۰۰٪ خودبسنده،
    # فوری و بدون وابستگی به اینترنت/فیلترینگ باشد (فونت‌های محلی و CSS کامل Tailwind جاسازی شده‌اند).
    html = re.sub(r"<link[^>]+fonts\.(?:googleapis|gstatic)\.com[^>]*>", "", html)
    html = re.sub(r"<script[^>]+cdn\.tailwindcss\.com[^>]*>\s*</script>", "", html)

    head_injection = (
        f'<style id="xgpedia-fonts">\n{font_css}\n</style>\n'
        f'<style id="xgpedia-tw-fallback">\n{tw_fallback_css}\n</style>\n'
    )
    export_style_tag = f'<style id="xgpedia-export-mode">\n{export_css}\n</style>\n'

    # تزریق فونت‌ها و پشتیبان Tailwind قبل از اولین <style> تا استایل اختصاصی استودیو اولویت داشته باشد
    if "<style>" in html:
        html = html.replace("<style>", head_injection + "<style>", 1)
    elif "</head>" in html:
        html = html.replace("</head>", head_injection + "</head>", 1)

    # تزریق CSS حالت خروجی دقیقاً پیش از </head>
    if "</head>" in html:
        html = html.replace("</head>", export_style_tag + "</head>", 1)

    # تزریق payload واقعی + هوک post-render پیش از اسکریپت اصلی استودیو
    safe_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    payload_script = (
        f'<script id="xgpedia-payload">\n'
        f"window.__XGPEDIA_PAYLOAD__ = {safe_json};\n"
        f"{_POST_RENDER_JS}\n"
        f"</script>\n"
    )
    if "<script>" in html:
        html = html.replace("<script>", payload_script + "<script>", 1)
    elif "</body>" in html:
        html = html.replace("</body>", payload_script + "</body>", 1)

    # اتصال تمیز داخل IIFE استودیو (پشتیبانی از هر دو الگوی Pre-Match و Post-Match)
    pre_hook = (
        "if(window.__XGPEDIA_PAYLOAD__){"
        "const _P=window.__XGPEDIA_PAYLOAD__;"
        "S.fmt=_P.fmt;S.hm=_P.headerMode||'full';S.sp='custom';S.sz=false;S.zm=1;S.m=_P.match;"
        "if(Array.isArray(_P.modules)){"
        "S.mods=_P.modules.map(x=>({id:x.id,e:!!x.enabled,s:x.span==='half'?'half':'full'}));"
        "}"
        "draw();"
        "window.__XGPEDIA_POST_RENDER__&&window.__XGPEDIA_POST_RENDER__(_P);"
        "}else{setSlide('slide1');mob('preview');}"
    )
    post_hook = (
        "if(window.__XGPEDIA_PAYLOAD__){"
        "const _P=window.__XGPEDIA_PAYLOAD__;"
        "S.f=_P.fmt;S.h=_P.headerMode||'full';S.s='custom';S.z=false;S.zm=1;S.m=_P.match;"
        "if(Array.isArray(_P.modules)){"
        "S.ms=_P.modules.map(x=>({id:x.id,e:!!x.enabled,p:x.span==='half'?'half':'full'}));"
        "}"
        "R();"
        "window.__XGPEDIA_POST_RENDER__&&window.__XGPEDIA_POST_RENDER__(_P);"
        "}else{yf();ss('slide1');mv('preview');}"
    )

    if "setSlide('slide1');mob('preview');" in html:
        html = html.replace("setSlide('slide1');mob('preview');", pre_hook, 1)
    elif 'yf();ss("slide1");mv("preview")' in html:
        html = html.replace('yf();ss("slide1");mv("preview")', post_hook, 1)
    else:
        raise RuntimeError(
            f"Could not find studio initialization hook in {tpl_path.name}. "
            "Ensure the studio HTML ends its init with setSlide('slide1');mob('preview'); "
            'or yf();ss("slide1");mv("preview").'
        )

    return html
