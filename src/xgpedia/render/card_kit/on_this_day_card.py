"""کارت «در چنین روزی» (On This Day — Showreel V2) در حالت اسلایدی یکپارچه با `card_kit`.

ویژگی‌های اجباری رعایت‌شده (تصمیم D45):
  - ۱۰۰٪ آفلاین و بدون هرگونه CDN خارجی (فونت محلی Vazirmatn/JetBrains Mono/Space Grotesk + لوگوی واقعی SVG برند)
  - حفظ کامل هر ۴ پوستر (`cover`, `tactical`, `collector`, `editorial`) × ۳ تم (`core`, `gold`, `noir`) × ۳ فرمت (`4:5`, `9:16`, `16:9`) × ۳ پس‌زمینه (`stadium`, `spotlight`, `pure`)
  - قابلیت انتخاب و خاموش/روشن کردن ماژول‌های داخلی هر اسلاید به‌صورت جداگانه در ربات
  - هدر قفل‌شده در دقیقاً ۲ خط (`flex-wrap: nowrap`)، کنتراست خودکار WCAG >= 4.8 (`resolve_visible_team_colors`)،
    ترتیب امن `esc(fa(...))`، عدم استفاده از `•` کنار ارقام فارسی، و رعایت کامل `null ≠ 0` (بدون عدد یا اسکوربرد جعلی).
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.xgpedia.config import ROOT as PROJECT_ROOT
from src.xgpedia.render.card_kit.helpers import (
    contrast_ink,
    ensure_dark_bg_contrast,
    esc,
    fa,
    luminance,
    resolve_visible_team_colors,
    team_crest_svg_or_img,
)
from src.xgpedia.render.cards import _brand_logo_data_uri
from src.xgpedia.render.studio_engine import FORMATS, build_embedded_font_css

OTD_DEFAULT_SLIDE = "cover"

OTD_SLIDES: list[tuple[str, str, str]] = [
    ("cover", "پوستر ۱: کاور سینمایی مجله‌ای", "COVER"),
    ("tactical", "پوستر ۲: تله‌متری و بازسازی تاکتیکی", "TACTICAL"),
    ("collector", "پوستر ۳: کارت کلکسیونی هولوگرافیک", "FOIL CARD"),
    ("editorial", "پوستر ۴: نقل‌قول سینمایی و میراث", "QUOTE"),
]

OTD_THEMES: dict[str, dict[str, str]] = {
    "core": {
        "label_fa": "تاکتیکال مدرن",
        "accent": "#E62E45",
        "accent_soft": "#FF6B7F",
        "accent_glow": "rgba(230,46,69,.55)",
        "canvas": "#0A1226",
        "glass": "linear-gradient(160deg,rgba(14,25,52,.84),rgba(7,13,29,.94))",
        "glass_strong": "linear-gradient(155deg,rgba(16,28,58,.92),rgba(6,11,24,.97))",
        "border": "rgba(248,250,252,.16)",
        "stroke": "rgba(248,250,252,.16)",
        "grade": "linear-gradient(180deg,rgba(10,18,38,.78) 0%,rgba(13,23,48,.46) 38%,rgba(10,18,38,.88) 75%,rgba(7,13,29,.97) 100%)",
        "badge_bg": "linear-gradient(135deg,#E62E45,#B91C32)",
        "badge_ink": "#FFFFFF",
        "glow_tint": "rgba(230,46,69,.18)",
    },
    "gold": {
        "label_fa": "آرشیو طلایی",
        "accent": "#EAB308",
        "accent_soft": "#FDE047",
        "accent_glow": "rgba(234,179,8,.5)",
        "canvas": "#090F1E",
        "glass": "linear-gradient(160deg,rgba(20,26,46,.86),rgba(8,12,24,.95))",
        "glass_strong": "linear-gradient(155deg,rgba(25,31,52,.93),rgba(8,11,22,.98))",
        "border": "rgba(250,204,21,.28)",
        "stroke": "rgba(250,204,21,.22)",
        "grade": "linear-gradient(180deg,rgba(9,15,30,.76) 0%,rgba(12,18,34,.44) 38%,rgba(9,15,30,.89) 76%,rgba(7,11,22,.97) 100%)",
        "badge_bg": "linear-gradient(135deg,#CA8A04,#EAB308)",
        "badge_ink": "#070D1D",
        "glow_tint": "rgba(234,179,8,.17)",
    },
    "noir": {
        "label_fa": "سینمایی نئون",
        "accent": "#FF2A4B",
        "accent_soft": "#FF6B81",
        "accent_glow": "rgba(255,42,75,.6)",
        "canvas": "#040812",
        "glass": "linear-gradient(160deg,rgba(12,18,34,.88),rgba(4,7,16,.96))",
        "glass_strong": "linear-gradient(155deg,rgba(16,22,40,.94),rgba(4,7,14,.98))",
        "border": "rgba(255,42,75,.32)",
        "stroke": "rgba(255,42,75,.25)",
        "grade": "linear-gradient(180deg,rgba(4,8,18,.84) 0%,rgba(6,10,22,.48) 38%,rgba(4,8,18,.93) 76%,rgba(3,6,14,.98) 100%)",
        "badge_bg": "linear-gradient(135deg,#E62E45,#B91C32)",
        "badge_ink": "#FFFFFF",
        "glow_tint": "rgba(255,42,75,.18)",
    },
}

OTD_BG_MODES: list[tuple[str, str]] = [
    ("stadium", "استادیوم شب"),
    ("spotlight", "توپ و نورافکن"),
    ("pure", "گرافیک خالص"),
]

# تعریف ماژول‌های داخلی قابل انتخاب در هر اسلاید (حالت اسلایدی)
SLIDE_MODULE_SPECS: dict[str, list[tuple[str, str]]] = {
    "cover": [
        ("scoreboard", "نتیجه و لوگوها"),
        ("pulse", "نبض درام ۹۰ دقیقه‌ای"),
        ("goals", "گل‌های سرنوشت‌ساز"),
        ("story", "روایت آن شب"),
        ("numbers", "اعداد ماندگار"),
    ],
    "tactical": [
        ("scoreboard", "نوار نتیجه بالا"),
        ("pitch", "بازسازی تاکتیکی زمین"),
        ("numbers", "اعداد ماندگار"),
        ("story", "روایت آن شب (بنر)"),
    ],
    "collector": [
        ("scoreboard", "تقابل لوگو و نتیجه"),
        ("numbers", "سه‌گانه آمار"),
        ("legacy", "میراث پیش و پس از رویداد"),
    ],
    "editorial": [
        ("quote", "نقل‌قول ماندگار"),
        ("story", "داک روایت و برچسب"),
        ("legacy", "میراث پیش و پس از رویداد"),
    ],
}


@lru_cache(maxsize=4)
def _otd_bg_data_uri(bg_mode: str) -> str | None:
    if bg_mode not in ("stadium", "spotlight"):
        return None
    p = PROJECT_ROOT / "brand" / "backgrounds" / f"otd_{bg_mode}.webp"
    if not p.exists():
        return None
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:image/webp;base64,{b64}"


def _event_module_availability(ev: dict[str, Any]) -> dict[str, bool]:
    home = ev.get("home")
    away = ev.get("away")
    has_match = bool(
        isinstance(home, dict) and isinstance(away, dict)
        and home.get("name") and away.get("name")
        and home.get("score") is not None and away.get("score") is not None
    )
    pulse = ev.get("pulse")
    goals = ev.get("goals")
    replay = ev.get("replay")
    numbers = ev.get("numbers")
    story = ev.get("story")
    quote = ev.get("quote")
    legacy = ev.get("legacy")
    return {
        "scoreboard": has_match,
        "pulse": bool(isinstance(pulse, list) and len(pulse) >= 4),
        "goals": bool(isinstance(goals, list) and len(goals) >= 1),
        "pitch": bool(isinstance(replay, dict) and replay.get("title") and (replay.get("run") or replay.get("passes"))),
        "numbers": bool(isinstance(numbers, list) and len(numbers) >= 1),
        "story": bool(isinstance(story, dict) and (story.get("body") or story.get("headline"))),
        "quote": bool(isinstance(quote, dict) and quote.get("text")),
        "legacy": bool(isinstance(legacy, dict) and (legacy.get("before") or legacy.get("after"))),
    }


def get_otd_slide_availability(ev: dict[str, Any]) -> dict[str, bool]:
    """تعیین اینکه کدام‌یک از ۴ پوستر برای رویداد فعلی دیتای واقعی کافی دارند."""
    avail = _event_module_availability(ev)
    return {
        "cover": True,
        "tactical": avail["pitch"],
        "collector": bool(avail["scoreboard"] or avail["numbers"] or avail["legacy"]),
        "editorial": bool(avail["quote"] or avail["story"]),
    }


def get_otd_slide_modules(ev: dict[str, Any], slide: str) -> tuple[list[dict[str, Any]], list[str]]:
    """برگرداندن لیست ماژول‌های دارای دیتا (قابل انتخاب) و ماژول‌های بدون دیتا برای اسلاید انتخابی."""
    avail = _event_module_availability(ev)
    specs = SLIDE_MODULE_SPECS.get(slide, SLIDE_MODULE_SPECS["cover"])
    enabled_list: list[dict[str, Any]] = []
    missing_list: list[str] = []
    for mod_id, title_fa in specs:
        if avail.get(mod_id, False):
            enabled_list.append({"id": mod_id, "title_fa": title_fa, "enabled": True})
        else:
            missing_list.append(title_fa)
    return enabled_list, missing_list


def _resolve_team_colors(ev: dict[str, Any], canvas_bg: str, accent: str) -> tuple[str, str]:
    home = ev.get("home") if isinstance(ev.get("home"), dict) else None
    away = ev.get("away") if isinstance(ev.get("away"), dict) else None
    if home and away:
        return resolve_visible_team_colors(home, away, bg=canvas_bg, min_ratio=4.8)
    return ensure_dark_bg_contrast(accent, bg=canvas_bg, min_ratio=4.8), "#38BDF8"















from src.xgpedia.render.card_kit.on_this_day_art import (  # noqa: E402, F401
    _brand_header_logo,
    _build_event_title_art,
    _build_pitch_svg,
    _build_pulse_svg,
    _map_pitch_xy,
    _remap_svg_path_to_real_pitch,
)

def _render_cover(ev: dict[str, Any], enabled: set[str], hc: str, ac: str, accent: str, is_banner: bool, is_story: bool) -> str:
    crest_sz = 132 if is_banner else (152 if is_story else 142)
    year_sz = 250 if is_banner else (330 if is_story else 300)
    year_txt = str(ev.get("year") or "")
    home = ev.get("home") if isinstance(ev.get("home"), dict) else None
    away = ev.get("away") if isinstance(ev.get("away"), dict) else None

    scoreboard_html = ""
    if "scoreboard" in enabled and home and away:
        agg_pill = (
            f'<div class="otd-agg-pill">{esc(fa(ev.get("aggNote", "")))}</div>'
            if ev.get("aggNote") else ""
        )
        scoreboard_html = (
            f'<div class="otd-sb-grid">'
            f'<div class="otd-sb-team">'
            f'<div class="otd-crest-wrap"><div class="otd-crest-glow" style="background:{hc}"></div>'
            f'{team_crest_svg_or_img(home, "otdh", crest_sz)}</div>'
            f'<span class="otd-team-name{" otd-team-name-bn" if is_banner else ""}">{esc(fa(home.get("name", "")))}</span>'
            f'</div>'
            f'<div class="otd-sb-center">'
            f'<div class="score-prism otd-score-box">'
            f'<span class="otd-score-num{" otd-score-num-bn" if is_banner else ""}" style="color:{hc};text-shadow:0 0 28px {hc}66">{esc(fa(home.get("score", "")))}</span>'
            f'<div class="otd-ft-col"><span class="fm otd-ft-lbl">FT</span></div>'
            f'<span class="otd-score-num{" otd-score-num-bn" if is_banner else ""}" style="color:{ac};text-shadow:0 0 28px {ac}66">{esc(fa(away.get("score", "")))}</span>'
            f'</div>{agg_pill}</div>'
            f'<div class="otd-sb-team">'
            f'<div class="otd-crest-wrap"><div class="otd-crest-glow" style="background:{ac}"></div>'
            f'{team_crest_svg_or_img(away, "otda", crest_sz)}</div>'
            f'<span class="otd-team-name{" otd-team-name-bn" if is_banner else ""}">{esc(fa(away.get("name", "")))}</span>'
            f'</div></div>'
        )
    else:
        # حالت رویداد تاریخی/زادروز بدون نتیجهٔ مسابقه (رعایت null ≠ 0)
        scoreboard_html = (
            f'<div class="otd-milestone-year">'
            f'<div dir="ltr" class="year-solid-grad" style="font-size:{118 if is_banner else 148}px">{esc(year_txt)}</div>'
            f'</div>'
        )

    kicker_html = (
        f'<div class="otd-kicker"><span class="otd-dot-glow"></span>'
        f'<span>{esc(fa(ev.get("kicker", "")))}</span></div>'
        if ev.get("kicker") else ""
    )

    title_art_html = _build_event_title_art(ev, accent, is_banner, is_story)
    hero_block = (
        f'<div class="otd-hero{" otd-hero-bn" if is_banner else ""}">'
        f'<div class="year-monolith otd-year-bg" style="font-size:{year_sz}px">{esc(year_txt)}</div>'
        f'{kicker_html}'
        f'{scoreboard_html}'
        f'{title_art_html}'
        f'</div>'
    )

    bottom_parts: list[str] = []
    # نبض درام و گل‌ها
    show_pulse = "pulse" in enabled and bool(ev.get("pulse"))
    show_goals = "goals" in enabled and bool(ev.get("goals"))
    if show_pulse or show_goals:
        pulse_svg = _build_pulse_svg(ev, hc, ac, accent, 880, 122 if is_story else 92) if show_pulse else ""
        goals_html = ""
        if show_goals:
            goal_chips = []
            for g in (ev.get("goals") or []):
                gcol = hc if g.get("side") == "home" else ac
                cls = "otd-goal-chip otd-goal-key" if g.get("key") else "otd-goal-chip"
                goal_chips.append(
                    f'<div class="{cls}">'
                    f'<span class="fm otd-goal-min" style="color:{gcol}">{esc(fa(g.get("label", "")))}</span>'
                    f'<span class="otd-goal-pl">{esc(fa(g.get("player", "")))}</span>'
                    f'</div>'
                )
            goals_html = f'<div class="otd-goals-wrap">{"".join(goal_chips)}</div>'
        bottom_parts.append(
            f'<div class="hud-card otd-pulse-card">'
            f'<div class="fbw otd-mod-hdr">'
            f'<div class="fi otd-mod-title-wrap"><span class="otd-accent-bar"></span>'
            f'<span class="otd-mod-title">نبض درام ۹۰ دقیقه‌ای و گل‌های سرنوشت‌ساز</span></div>'
            f'<span dir="ltr" class="fm otd-mod-tag">DRAMA PULSE | {esc(year_txt)}</span>'
            f'</div>{pulse_svg}{goals_html}</div>'
        )

    # روایت + اعداد ماندگار
    story = ev.get("story") if isinstance(ev.get("story"), dict) else None
    nums = ev.get("numbers") if isinstance(ev.get("numbers"), list) else []
    show_story = "story" in enabled and bool(story and (story.get("body") or story.get("headline")))
    show_nums = "numbers" in enabled and bool(nums)

    if show_story or show_nums:
        story_box = ""
        if show_story and story:
            story_box = (
                f'<div class="hud-solid otd-story-box{" otd-span-7" if (show_nums and not is_banner) else " otd-span-12"}">'
                f'<div class="otd-story-hl">{esc(fa(story.get("headline", "")))}</div>'
                f'<p class="otd-story-body" style="font-size:{20 if is_story else 18.5}px">{esc(fa(story.get("body", "")))}</p>'
                f'</div>'
            )
        nums_box = ""
        if show_nums:
            bar_cols = ["var(--xg-accent)", "#F59E0B", "#38BDF8"]
            num_items = "".join(
                f'<div class="hud-card otd-num-row" style="border-right:4px solid {bar_cols[i % 3]}">'
                f'<div class="otd-num-meta">'
                f'<div class="otd-num-unit">{esc(fa(n.get("unit", "")))}</div>'
                f'<div class="otd-num-sub">{esc(fa(n.get("sub", "")))}</div>'
                f'</div>'
                f'<div dir="ltr" class="fd otd-num-val">{esc(fa(n.get("val", "")))}</div>'
                f'</div>'
                for i, n in enumerate(nums[:3])
            )
            if is_banner or not show_story:
                nums_box = f'<div class="otd-nums-grid-3">{num_items}</div>'
            else:
                nums_box = f'<div class="otd-span-5 otd-nums-col">{num_items}</div>'

        if is_banner or not (show_story and show_nums):
            bottom_parts.append(f'<div class="fcol otd-gap-14">{story_box}{nums_box}</div>')
        else:
            bottom_parts.append(f'<div class="otd-grid-12 otd-gap-16">{story_box}{nums_box}</div>')

    bottom_hud = f'<div class="fcol otd-gap-14{" otd-justify-center" if is_banner else " otd-shrink-0"}">{"".join(bottom_parts)}</div>'
    if is_banner:
        return (
            f'<div class="otd-banner-grid">'
            f'<div class="fcol otd-justify-center">{hero_block}</div>'
            f'<div class="fcol otd-justify-center">{bottom_hud}</div>'
            f'</div>'
        )
    return f'{hero_block}{bottom_hud}'


def _render_tactical(ev: dict[str, Any], enabled: set[str], hc: str, ac: str, canvas_bg: str, is_banner: bool, is_story: bool) -> str:
    home = ev.get("home") if isinstance(ev.get("home"), dict) else None
    away = ev.get("away") if isinstance(ev.get("away"), dict) else None
    year_txt = str(ev.get("year") or "")
    replay = ev.get("replay") if isinstance(ev.get("replay"), dict) else {}

    compact_top = ""
    if "scoreboard" in enabled and home and away:
        compact_top = (
            f'<div class="hud-solid otd-tac-top">'
            f'<div class="fi otd-gap-14 otd-minw-0">'
            f'{team_crest_svg_or_img(home, "otdth", 62)}'
            f'<div class="score-prism otd-tac-score">'
            f'<span class="otd-tac-snum" style="color:{hc}">{esc(fa(home.get("score", "")))}</span>'
            f'<span class="otd-col-dash">—</span>'
            f'<span class="otd-tac-snum" style="color:{ac}">{esc(fa(away.get("score", "")))}</span>'
            f'</div>'
            f'{team_crest_svg_or_img(away, "otdta", 62)}'
            f'<div class="otd-minw-0">'
            f'<div class="otd-tac-title">{esc(fa(ev.get("title", "")))}</div>'
            f'<div class="otd-tac-agg">{esc(fa(ev.get("aggNote", "")))}</div>'
            f'</div></div>'
            f'<div dir="ltr" class="year-solid-grad otd-tac-year">{esc(year_txt)}</div>'
            f'</div>'
        )

    pitch_card = ""
    if "pitch" in enabled and replay:
        pitch_card = (
            f'<div class="hud-solid otd-pitch-card">'
            f'<div class="fbw otd-pitch-hdr">'
            f'<div class="fi otd-gap-12 otd-minw-0">'
            f'<span class="otd-accent-bar-lg"></span>'
            f'<div class="otd-minw-0">'
            f'<h2 class="otd-pitch-title">{esc(fa(replay.get("title", "")))}</h2>'
            f'<span class="otd-pitch-sub">تله‌متری لحظه تعیین‌کننده مسابقه | آرشیو XGPedia</span>'
            f'</div></div>'
            f'<span dir="ltr" class="fm otd-pitch-badge">{esc(replay.get("badge", ""))}</span>'
            f'</div>'
            f'<div class="otd-pitch-stage">{_build_pitch_svg(ev, canvas_bg, 640 if is_story else (490 if is_banner else 560))}</div>'
            f'<p class="otd-pitch-cap">{esc(fa(replay.get("caption", "")))}</p>'
            f'</div>'
        )

    nums_row = ""
    nums = ev.get("numbers") if isinstance(ev.get("numbers"), list) else []
    if "numbers" in enabled and nums:
        top_cols = ["var(--xg-accent)", "#F59E0B", "#38BDF8"]
        unit_cols = ["var(--xg-accent-soft)", "#FDE047", "#7DD3FC"]
        cards = "".join(
            f'<div class="hud-card otd-tnum-card">'
            f'<div class="otd-tnum-bar" style="background:{top_cols[i % 3]}"></div>'
            f'<div dir="ltr" class="fd otd-tnum-val">{esc(fa(n.get("val", "")))}</div>'
            f'<div class="otd-tnum-unit" style="color:{unit_cols[i % 3]}">{esc(fa(n.get("unit", "")))}</div>'
            f'<div class="otd-tnum-sub">{esc(fa(n.get("sub", "")))}</div>'
            f'</div>'
            for i, n in enumerate(nums[:3])
        )
        nums_row = f'<div class="otd-grid-{min(3, len(nums))} otd-gap-16 otd-shrink-0">{cards}</div>'

    if is_banner:
        story = ev.get("story") if isinstance(ev.get("story"), dict) else None
        story_card = ""
        if "story" in enabled and story:
            story_card = (
                f'<div class="hud-card otd-story-bn">'
                f'<div class="otd-story-hl">{esc(fa(story.get("headline", "")))}</div>'
                f'<p class="otd-story-body" style="font-size:18.5px">{esc(fa(story.get("body", "")))}</p>'
                f'</div>'
            )
        return (
            f'<div class="otd-tac-bn-grid">'
            f'<div class="fcol otd-gap-14 otd-minh-0">{pitch_card}</div>'
            f'<div class="fcol otd-justify-between otd-gap-14 otd-minh-0">{compact_top}{story_card}{nums_row}</div>'
            f'</div>'
        )
    return f'<div class="fcol otd-flex-1 otd-justify-between otd-gap-16 otd-minh-0">{compact_top}{pitch_card}{nums_row}</div>'


def _render_collector(ev: dict[str, Any], enabled: set[str], hc: str, ac: str, is_banner: bool) -> str:
    home = ev.get("home") if isinstance(ev.get("home"), dict) else None
    away = ev.get("away") if isinstance(ev.get("away"), dict) else None
    year_txt = str(ev.get("year") or "")
    crest_sz = 118 if is_banner else 144

    if "scoreboard" in enabled and home and away:
        centerpiece = (
            f'<div class="otd-col-faceoff">'
            f'<div class="otd-col-team">'
            f'{team_crest_svg_or_img(home, "otdfh", crest_sz)}'
            f'<span class="otd-col-tname">{esc(fa(home.get("name", "")))}</span>'
            f'</div>'
            f'<div class="otd-col-mid">'
            f'<div dir="ltr" class="year-solid-grad" style="font-size:{92 if is_banner else 112}px">{esc(year_txt)}</div>'
            f'<div class="score-prism otd-col-score">'
            f'<span class="otd-col-snum" style="color:{hc}">{esc(fa(home.get("score", "")))}</span>'
            f'<span class="otd-col-dash">—</span>'
            f'<span class="otd-col-snum" style="color:{ac}">{esc(fa(away.get("score", "")))}</span>'
            f'</div>'
            f'<span class="otd-col-title">{esc(fa(ev.get("title", "")))}</span>'
            f'</div>'
            f'<div class="otd-col-team">'
            f'{team_crest_svg_or_img(away, "otdfa", crest_sz)}'
            f'<span class="otd-col-tname">{esc(fa(away.get("name", "")))}</span>'
            f'</div></div>'
        )
    else:
        centerpiece = (
            f'<div class="otd-col-milestone">'
            f'<div dir="ltr" class="year-solid-grad" style="font-size:{110 if is_banner else 136}px">{esc(year_txt)}</div>'
            f'<div class="otd-col-mtitle">{esc(fa(ev.get("title", "")))}</div>'
            f'<p class="otd-col-msub">{esc(fa(ev.get("subtitle", "")))}</p>'
            f'</div>'
        )

    nums_html = ""
    nums = ev.get("numbers") if isinstance(ev.get("numbers"), list) else []
    if "numbers" in enabled and nums:
        unit_cols = ["var(--xg-accent-soft)", "#FDE047", "#7DD3FC"]
        triptych = "".join(
            f'<div class="otd-col-num">'
            f'<div dir="ltr" class="fd otd-col-nval">{esc(fa(n.get("val", "")))}</div>'
            f'<div class="otd-col-nunit" style="color:{unit_cols[i % 3]}">{esc(fa(n.get("unit", "")))}</div>'
            f'<div class="otd-col-nsub">{esc(fa(n.get("sub", "")))}</div>'
            f'</div>'
            for i, n in enumerate(nums[:3])
        )
        nums_html = f'<div class="otd-grid-{min(3, len(nums))} otd-gap-16 otd-z10">{triptych}</div>'

    legacy_html = ""
    leg = ev.get("legacy") if isinstance(ev.get("legacy"), dict) else None
    if "legacy" in enabled and leg:
        legacy_html = (
            f'<div class="otd-legacy-grid otd-legacy-border otd-z10">'
            f'<div class="otd-leg-card otd-leg-before">'
            f'<span class="otd-leg-ttl-b">{esc(fa(leg.get("beforeTitle", "پیش از این روز")))}</span>'
            f'<p class="otd-leg-txt-b">{esc(fa(leg.get("before", "")))}</p>'
            f'</div>'
            f'<div class="otd-leg-card otd-leg-after">'
            f'<span class="otd-leg-ttl-a">{esc(fa(leg.get("afterTitle", "میراث ماندگار")))}</span>'
            f'<p class="otd-leg-txt-a">{esc(fa(leg.get("after", "")))}</p>'
            f'</div></div>'
        )

    return (
        f'<div class="foil-frame otd-foil-card">'
        f'<div class="foil-sheen"></div>'
        f'<div class="fbw otd-col-top otd-z10">'
        f'<div class="fi otd-gap-12 otd-minw-0">'
        f'<span class="fm otd-col-badge">COLLECTOR EDITION</span>'
        f'<span class="otd-col-kicker">{esc(fa(ev.get("kicker", "")))}</span>'
        f'</div>'
        f'<span dir="ltr" class="fm otd-col-code">{esc(ev.get("archiveCode", ""))}</span>'
        f'</div>'
        f'{centerpiece}{nums_html}{legacy_html}'
        f'</div>'
    )


def _render_editorial(ev: dict[str, Any], enabled: set[str], is_banner: bool, is_story: bool) -> str:
    home = ev.get("home") if isinstance(ev.get("home"), dict) else None
    away = ev.get("away") if isinstance(ev.get("away"), dict) else None
    year_txt = str(ev.get("year") or "")
    quote = ev.get("quote") if isinstance(ev.get("quote"), dict) else None
    story = ev.get("story") if isinstance(ev.get("story"), dict) else None
    leg = ev.get("legacy") if isinstance(ev.get("legacy"), dict) else None

    quote_stage = ""
    if "quote" in enabled and quote and quote.get("text"):
        q_sz = 38 if is_banner else (48 if is_story else 43)
        quote_stage = (
            f'<div class="otd-quote-stage{" otd-quote-bn" if is_banner else ""}">'
            f'<div class="year-monolith otd-quote-year" style="font-size:{200 if is_banner else 240}px">{esc(year_txt)}</div>'
            f'<svg class="otd-quote-icon" viewBox="0 0 64 64" fill="var(--xg-accent)">'
            f'<path d="M26 16H10v18h10c0 6-4 10-10 12v6c10-2 16-9 16-20V16zm28 0H38v18h10c0 6-4 10-10 12v6c10-2 16-9 16-20V16z"/></svg>'
            f'<blockquote class="otd-blockquote" style="font-size:{q_sz}px">{esc(fa(quote.get("text", "")))}</blockquote>'
            f'<div class="fi otd-gap-16 otd-z10">'
            f'<div class="otd-quote-dash"></div>'
            f'<div><div class="otd-quote-by">{esc(fa(quote.get("by", "")))}</div>'
            f'<div class="otd-quote-role">{esc(fa(quote.get("role", "")))}</div></div>'
            f'</div></div>'
        )
    else:
        # اگر نقل‌قول وجود نداشت (رویداد زنده ویکی‌پدیا)، تیتر سینمایی رویداد نمایش داده می‌شود
        quote_stage = (
            f'<div class="otd-quote-stage{" otd-quote-bn" if is_banner else ""}">'
            f'<div class="year-monolith otd-quote-year" style="font-size:{200 if is_banner else 240}px">{esc(year_txt)}</div>'
            f'<div class="otd-kicker"><span class="otd-dot-glow"></span><span>{esc(fa(ev.get("kicker", "")))}</span></div>'
            f'<blockquote class="otd-blockquote" style="font-size:{38 if is_banner else 44}px">{esc(fa(ev.get("title", "")))}</blockquote>'
            f'<p class="otd-sub" style="font-size:22px;text-align:right">{esc(fa(ev.get("subtitle", "")))}</p>'
            f'</div>'
        )

    dock_parts: list[str] = []
    if "story" in enabled and story:
        mini_match = ""
        if home and away:
            mini_match = (
                f'{team_crest_svg_or_img(home, "otdeh", 50)}'
                f'<span class="otd-ed-score">{esc(fa(home.get("score", "")))} – {esc(fa(away.get("score", "")))}</span>'
                f'{team_crest_svg_or_img(away, "otdea", 50)}'
            )
        tag_row = (
            f'<div class="otd-ed-tag"><span class="otd-emerald-dot"></span><span>{esc(fa(story.get("tag", "")))}</span></div>'
            if story.get("tag") else ""
        )
        dock_parts.append(
            f'<div class="hud-solid otd-ed-story">'
            f'<div class="fbw otd-ed-shdr">'
            f'<div class="fi otd-gap-12 otd-minw-0">{mini_match}'
            f'<span class="otd-ed-title">{esc(fa(ev.get("title", "")))}</span></div>'
            f'<span dir="ltr" class="fm otd-mod-tag">CHRONICLE</span>'
            f'</div>'
            f'<p class="otd-ed-body">{esc(fa(story.get("body", "")))}</p>'
            f'{tag_row}</div>'
        )

    if "legacy" in enabled and leg:
        dock_parts.append(
            f'<div class="otd-legacy-grid">'
            f'<div class="hud-card otd-leg-card otd-leg-before">'
            f'<span class="otd-leg-ttl-b">{esc(fa(leg.get("beforeTitle", "پیش از این روز")))}</span>'
            f'<p class="otd-leg-txt-b">{esc(fa(leg.get("before", "")))}</p>'
            f'</div>'
            f'<div class="hud-card otd-leg-card otd-leg-after">'
            f'<span class="otd-leg-ttl-a">{esc(fa(leg.get("afterTitle", "میراث ماندگار")))}</span>'
            f'<p class="otd-leg-txt-a">{esc(fa(leg.get("after", "")))}</p>'
            f'</div></div>'
        )

    story_dock = f'<div class="fcol otd-gap-14{" otd-justify-center" if is_banner else " otd-shrink-0"}">{"".join(dock_parts)}</div>'
    if is_banner:
        return (
            f'<div class="otd-banner-grid">'
            f'<div class="fcol otd-justify-center">{quote_stage}</div>'
            f'<div class="fcol otd-justify-center">{story_dock}</div>'
            f'</div>'
        )
    return f'{quote_stage}{story_dock}'


def render_on_this_day_html(
    event: dict[str, Any],
    *,
    slide: str = "cover",
    theme: str = "core",
    fmt: str = "4:5",
    bg_mode: str | None = None,
    enabled_modules: list[str] | None = None,
    foil: bool = True,
) -> str:
    """تولید HTML کامل و ۱۰۰٪ آفلاین برای کارت «در چنین روزی» (Showreel V2)."""
    slide = slide if slide in SLIDE_MODULE_SPECS else "cover"
    th = OTD_THEMES.get(theme, OTD_THEMES["core"])
    w, h = FORMATS.get(fmt, FORMATS["4:5"])
    is_banner = fmt == "16:9"
    is_story = fmt == "9:16"
    pad_top, pad_bot = (139, 171) if is_story else ((22, 16) if is_banner else (24, 20))

    avail_mods, _ = get_otd_slide_modules(event, slide)
    avail_ids = {m["id"] for m in avail_mods}
    if enabled_modules is not None:
        enabled = {m for m in enabled_modules if m in avail_ids}
    else:
        enabled = set(avail_ids)

    hc, ac = _resolve_team_colors(event, th["canvas"], th["accent"])
    eff_bg = bg_mode if bg_mode in ("stadium", "spotlight", "pure") else str(event.get("defaultBg") or "stadium")
    bg_uri = _otd_bg_data_uri(eff_bg)
    bg_img_html = (
        f'<img src="{bg_uri}" alt="" class="otd-bg-img">'
        if bg_uri else ""
    )

    year_int = int(event.get("year") or datetime.now(timezone.utc).year)
    yrs_ago = max(1, datetime.now(timezone.utc).year - year_int)

    if slide == "tactical" and "pitch" in avail_ids:
        stage_html = _render_tactical(event, enabled, hc, ac, th["canvas"], is_banner, is_story)
    elif slide == "collector":
        stage_html = _render_collector(event, enabled, hc, ac, is_banner)
    elif slide == "editorial":
        stage_html = _render_editorial(event, enabled, is_banner, is_story)
    else:
        stage_html = _render_cover(event, enabled, hc, ac, th["accent"], is_banner, is_story)

    # خط دوم هدر — قفل‌شده در یک خط (بدون wrap) و بدون • کنار ارقام فارسی
    meta_parts = [p for p in [event.get("competition"), event.get("stadium"), event.get("dateEn")] if p]
    meta_html = ' <span class="otd-sep">|</span> '.join(
        f'<span dir="ltr" class="fm otd-meta-en">{esc(p)}</span>'
        if p == event.get("dateEn") else f'<span class="otd-meta-txt">{esc(fa(p))}</span>'
        for p in meta_parts
    )

    spine_html = ""
    if foil and not is_banner:
        spine_txt = f'XGPEDIA ARCHIVE // {event.get("archiveCode") or year_int} // ON THIS DAY'
        spine_html = (
            f'<div class="otd-spine">'
            f'<span class="otd-spine-line-t"></span>'
            f'<span dir="ltr" class="spine-rail fm otd-spine-txt">{esc(spine_txt)}</span>'
            f'<svg width="14" height="42" viewBox="0 0 16 46" fill="#F8FAFC" fill-opacity=".55">'
            f'<rect y="0" width="16" height="2"/><rect y="4" width="16" height="4"/>'
            f'<rect y="10" width="16" height="1.5"/><rect y="14" width="16" height="3"/>'
            f'<rect y="19" width="16" height="1.5"/><rect y="23" width="16" height="5"/>'
            f'<rect y="30" width="16" height="2"/><rect y="34" width="16" height="1.5"/>'
            f'<rect y="38" width="16" height="4"/><rect y="44" width="16" height="2"/></svg>'
            f'<span class="otd-spine-line-b"></span>'
            f'</div>'
        )

    footer_tag = f'{(event.get("leagueEn") or "ARCHIVE").upper()} | {year_int} | ON THIS DAY'
    source_txt = str(event.get("source") or "XGPedia Archive")
    # مختصات چهارگوشه قرمز دقیقاً هم‌تراز با کارت Post-Match (base_shell.py: 24px تا 44px)
    crh_d = (
        f"M24 44V24H44M{w - 24} 44V24H{w - 44}"
        f"M24 {h - 44}V{h - 24}H44M{w - 24} {h - 44}V{h - 24}H{w - 44}"
    )

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<title>{esc(event.get("title", "XGPedia On This Day"))}</title>
<style>
{build_embedded_font_css()}
:root{{
  --xg-accent:{th["accent"]};
  --xg-accent-soft:{th["accent_soft"]};
  --xg-accent-glow:{th["accent_glow"]};
  --xg-canvas:{th["canvas"]};
  --xg-glass:{th["glass"]};
  --xg-glass-strong:{th["glass_strong"]};
  --xg-border:{th["border"]};
  --xg-stroke:{th["stroke"]};
}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{w}px;height:{h}px;overflow:hidden;background:var(--xg-canvas);color:#F8FAFC;
  font-family:'Vazirmatn',system-ui,sans-serif;font-feature-settings:"tnum";font-variant-numeric:tabular-nums}}
.fm{{font-family:'JetBrains Mono','Space Grotesk',monospace}}
.fd{{font-family:'Space Grotesk','Vazirmatn',sans-serif}}
.fi{{display:flex;align-items:center}}
.fbw{{display:flex;align-items:center;justify-content:space-between}}
.fcol{{display:flex;flex-direction:column}}
.otd-flex-1{{flex:1}}
.otd-minh-0{{min-height:0}}
.otd-minw-0{{min-width:0}}
.otd-shrink-0{{flex-shrink:0}}
.otd-justify-center{{justify-content:center}}
.otd-justify-between{{justify-content:space-between}}
.otd-z10{{position:relative;z-index:10}}
.otd-gap-12{{gap:12px}}.otd-gap-14{{gap:14px}}.otd-gap-16{{gap:16px}}
.otd-svg-full{{width:100%;height:auto;display:block}}
.otd-canvas{{
  position:relative;width:{w}px;height:{h}px;overflow:hidden;
  background:var(--xg-canvas);display:flex;flex-direction:column;justify-content:space-between;
  padding:{pad_top}px 0 {pad_bot}px;
}}
.otd-photo-layer{{position:absolute;inset:0;z-index:0;pointer-events:none;overflow:hidden}}
.otd-bg-img{{width:100%;height:100%;object-fit:cover;object-position:center;opacity:.60;filter:contrast(1.10) saturate(.74)}}
.otd-color-grade{{position:absolute;inset:0;background:{th["grade"]}}}
.otd-ambient{{position:absolute;inset:0;z-index:0;pointer-events:none;
  background:radial-gradient(circle at 86% 26%,{hc}38,transparent 48%),
             radial-gradient(circle at 14% 26%,{ac}38,transparent 48%),
             radial-gradient(circle at 50% 34%,{th["glow_tint"]},transparent 55%)}}
.otd-scanlines{{position:absolute;inset:0;z-index:0;pointer-events:none;
  background:repeating-linear-gradient(to bottom,#ffffff04 0 1px,#0000 1px 4px)}}
.otd-frame-svg{{position:absolute;inset:0;width:100%;height:100%;z-index:0;pointer-events:none}}

/* Header: قفل‌شده در دقیقاً ۲ خط */
.otd-header{{position:relative;z-index:10;padding:12px 36px 8px;display:flex;align-items:center;justify-content:space-between;gap:14px;flex-shrink:0}}
.otd-hdr-left{{display:flex;flex-direction:column;align-items:flex-start;gap:7px;min-width:0;flex:1}}
.otd-hdr-row1{{display:flex;align-items:center;flex-wrap:nowrap;gap:10px;white-space:nowrap;overflow:hidden}}
.otd-hdr-row2{{display:flex;align-items:center;flex-wrap:nowrap;gap:10px;white-space:nowrap;overflow:hidden;font-size:17px;font-weight:700;color:#E2E8F0;max-width:100%}}
.otd-badge{{padding:5px 18px;border-radius:999px;font-size:19px;font-weight:900;display:inline-flex;align-items:center;gap:8px;
  background:{th["badge_bg"]};color:{th["badge_ink"]};border:1px solid rgba(255,255,255,.32);
  box-shadow:0 8px 22px rgba(0,0,0,.38);flex-shrink:0}}
.otd-date-pill{{padding:5px 15px;border-radius:999px;font-size:19px;font-weight:800;color:#FFFFFF;
  background:rgba(15,25,52,.80);border:1px solid rgba(255,255,255,.22);flex-shrink:0}}
.otd-ago-pill{{padding:5px 14px;border-radius:999px;font-size:17.5px;font-weight:800;color:#FDE047;
  background:rgba(245,158,11,.18);border:1px solid rgba(250,204,21,.50);flex-shrink:0}}
.otd-meta-txt{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.otd-meta-en{{font-size:15.5px;font-weight:700;color:#CBD5E1;flex-shrink:0}}
.otd-sep{{color:#64748B;flex-shrink:0}}
.otd-brand{{display:flex;align-items:center;gap:10px;flex-shrink:0}}
.otd-brand-img{{height:48px;width:auto;display:block;filter:drop-shadow(0 6px 14px rgba(0,0,0,.45))}}
.otd-brand-txt{{font-size:32px;font-weight:800;line-height:1;letter-spacing:-0.02em}}

/* Spine */
.otd-spine{{position:absolute;left:18px;top:50%;transform:translateY(-50%);z-index:20;display:flex;flex-direction:column;align-items:center;gap:14px;opacity:.82;pointer-events:none}}
.otd-spine-line-t{{width:2px;height:56px;border-radius:99px;background:linear-gradient(to bottom,transparent,var(--xg-accent))}}
.otd-spine-line-b{{width:2px;height:56px;border-radius:99px;background:linear-gradient(to top,transparent,var(--xg-accent))}}
.spine-rail{{writing-mode:vertical-rl;text-orientation:mixed;letter-spacing:.20em}}
.otd-spine-txt{{font-size:12px;font-weight:700;color:#CBD5E1;text-transform:uppercase}}

/* Stage & Footer */
.otd-stage{{position:relative;z-index:10;flex:1;padding:8px 40px;display:flex;flex-direction:column;justify-content:space-between;min-height:0;overflow:hidden;gap:14px}}
.otd-footer{{position:relative;z-index:10;padding:10px 44px 10px;flex-shrink:0}}
.otd-footer-line{{border-top:1px solid rgba(255,255,255,.15);margin-bottom:8px}}
.otd-foot-dot{{width:11px;height:11px;border-radius:999px;background:var(--xg-accent);box-shadow:0 0 12px var(--xg-accent);flex-shrink:0}}
.otd-foot-tag{{font-size:16.5px;font-weight:800;letter-spacing:.12em;color:#F1F5F9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.otd-foot-handle{{font-size:19px;font-weight:800;color:#FFFFFF}}
.otd-foot-src{{font-size:16px;font-weight:600;color:#CBD5E1}}

/* Glass Surfaces */
.hud-card{{position:relative;border-radius:22px;overflow:hidden;background:var(--xg-glass);border:1.5px solid var(--xg-border);
  box-shadow:0 18px 46px -14px rgba(0,0,0,.78),inset 0 1px 0 rgba(255,255,255,.16)}}
.hud-solid{{position:relative;border-radius:22px;overflow:hidden;background:var(--xg-glass-strong);border:1.5px solid var(--xg-border);
  box-shadow:0 22px 54px -14px rgba(0,0,0,.85),inset 0 1px 0 rgba(255,255,255,.20)}}
.score-prism{{position:relative;border-radius:24px;background:linear-gradient(180deg,rgba(11,20,42,.90),rgba(4,9,22,.97));
  border:1.5px solid rgba(255,255,255,.24);box-shadow:0 22px 52px -10px rgba(0,0,0,.9),0 0 38px -12px var(--xg-accent-glow),inset 0 1px 0 rgba(255,255,255,.26)}}
.foil-frame{{position:relative;border-radius:26px;overflow:hidden;background:linear-gradient(155deg,rgba(15,24,48,.84),rgba(6,10,22,.95));
  border:2px solid var(--xg-border);box-shadow:0 26px 66px -12px rgba(0,0,0,.9),inset 0 1px 0 rgba(255,255,255,.24)}}
.foil-sheen{{position:absolute;inset:0;pointer-events:none;background:linear-gradient(125deg,transparent 24%,rgba(255,255,255,.07) 42%,rgba(255,255,255,.01) 54%,transparent 72%)}}
.year-monolith{{font-family:'Space Grotesk',sans-serif;font-weight:800;line-height:.82;letter-spacing:-0.05em;white-space:nowrap;
  color:rgba(248,250,252,.045);-webkit-text-stroke:2.5px var(--xg-stroke);filter:drop-shadow(0 18px 40px rgba(0,0,0,.65));pointer-events:none}}
.year-solid-grad{{font-family:'Space Grotesk',sans-serif;font-weight:800;line-height:.86;letter-spacing:-0.04em;
  background:linear-gradient(180deg,#FFFFFF 0%,rgba(248,250,252,.82) 55%,rgba(148,163,184,.28) 100%);
  -webkit-background-clip:text;background-clip:text;color:transparent}}

/* Cover Slide */
.otd-banner-grid{{flex:1;display:grid;grid-template-columns:1fr 1fr;gap:28px;align-items:stretch;min-height:0}}
.otd-hero{{position:relative;flex:1;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;padding:6px 0}}
.otd-hero-bn{{padding-left:24px;border-left:1px solid rgba(255,255,255,.12)}}
.otd-year-bg{{position:absolute;left:50%;top:34%;transform:translate(-50%,-50%)}}
.otd-kicker{{position:relative;z-index:10;display:inline-flex;align-items:center;gap:10px;padding:6px 20px;border-radius:999px;
  background:rgba(0,0,0,.48);border:1px solid rgba(255,255,255,.22);margin-bottom:16px;font-size:18.5px;font-weight:800;color:#FDE047}}
.otd-dot-glow{{width:10px;height:10px;border-radius:999px;background:var(--xg-accent);box-shadow:0 0 12px var(--xg-accent);flex-shrink:0}}
.otd-sb-grid{{position:relative;z-index:10;width:100%;display:grid;grid-template-columns:3fr 6fr 3fr;align-items:center;gap:8px;margin:4px 0}}
.otd-sb-team{{display:flex;flex-direction:column;align-items:center}}
.otd-crest-wrap{{position:relative;display:flex;align-items:center;justify-content:center}}
.otd-crest-glow{{position:absolute;inset:0;border-radius:999px;filter:blur(26px);opacity:.38}}
.otd-team-name{{font-size:32px;font-weight:900;color:#FFFFFF;margin-top:8px;text-shadow:0 4px 14px rgba(0,0,0,.85)}}
.otd-team-name-bn{{font-size:28px}}
.otd-sb-center{{display:flex;flex-direction:column;align-items:center;gap:10px}}
.otd-score-box{{padding:14px 34px;display:flex;align-items:center;justify-content:center;gap:28px;min-width:270px}}
.otd-score-num{{font-size:84px;font-weight:900;line-height:1}}
.otd-score-num-bn{{font-size:72px}}
.otd-ft-col{{display:flex;flex-direction:column;align-items:center;gap:6px}}
.otd-diamond{{width:15px;height:15px;transform:rotate(45deg);border-radius:3px;background:var(--xg-accent);box-shadow:0 0 20px var(--xg-accent)}}
.otd-diamond-sm{{width:10px;height:10px;transform:rotate(45deg);border-radius:2px;background:var(--xg-accent)}}
.otd-ft-lbl{{font-size:18px;font-weight:900;color:#E2E8F0;letter-spacing:.16em;padding:4px 12px;border-radius:10px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.16)}}
.otd-agg-pill{{padding:6px 18px;border-radius:999px;background:rgba(0,0,0,.58);border:1px solid rgba(250,204,21,.45);
  font-size:17.5px;font-weight:800;color:#FDE047}}
.otd-milestone-year{{position:relative;z-index:10;margin:10px 0}}
.otd-headline-wrap{{position:relative;z-index:10;margin-top:14px;max-width:96%;display:flex;flex-direction:column;align-items:center;gap:10px}}
.otd-h1-stage{{position:relative;display:flex;align-items:center;justify-content:center;padding:6px 28px;min-height:92px}}
.otd-title-motif{{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0}}
.otd-h1-art{{position:relative;z-index:2;font-weight:900;line-height:1.06;letter-spacing:-0.025em;
  filter:drop-shadow(0 12px 26px rgba(0,0,0,.88))}}
.otd-ornament-row{{display:flex;align-items:center;justify-content:center;gap:14px;width:100%;max-width:640px}}
.otd-orn-line{{flex:1;height:2px;border-radius:99px;background:linear-gradient(90deg,transparent,var(--xg-accent),transparent);opacity:.78}}
.otd-orn-pill{{padding:4px 16px;border-radius:999px;background:rgba(7,13,29,.78);border:1px solid rgba(255,255,255,.24);
  font-size:16.5px;font-weight:800;color:#F8FAFC;white-space:nowrap}}
.otd-sub{{font-weight:700;color:#F1F5F9;line-height:1.58;text-shadow:0 4px 14px rgba(0,0,0,.92)}}

/* Pulse & Goals */
.otd-pulse-card{{padding:14px 22px;display:flex;flex-direction:column;gap:10px}}
.otd-mod-hdr{{gap:10px}}
.otd-mod-title-wrap{{gap:10px}}
.otd-accent-bar{{width:7px;height:22px;border-radius:99px;background:var(--xg-accent);flex-shrink:0}}
.otd-accent-bar-lg{{width:9px;height:32px;border-radius:99px;background:var(--xg-accent);flex-shrink:0}}
.otd-mod-title{{font-size:21px;font-weight:900;color:#FFFFFF}}
.otd-mod-tag{{font-size:14px;font-weight:800;color:#CBD5E1;letter-spacing:.08em;flex-shrink:0}}
.otd-goals-wrap{{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding-top:4px}}
.otd-goal-chip{{display:inline-flex;align-items:center;gap:8px;padding:4px 12px;border-radius:11px;
  background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12)}}
.otd-goal-key{{background:rgba(255,255,255,.12);border-color:rgba(250,204,21,.52)}}
.otd-goal-min{{font-size:15px;font-weight:900}}
.otd-goal-pl{{font-size:16px;font-weight:800;color:#FFFFFF}}

/* Story & Numbers */
.otd-grid-12{{display:grid;grid-template-columns:repeat(12,minmax(0,1fr))}}
.otd-span-7{{grid-column:span 7}}.otd-span-5{{grid-column:span 5}}.otd-span-12{{grid-column:span 12}}
.otd-grid-3{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr))}}
.otd-grid-2{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}}
.otd-grid-1{{display:grid;grid-template-columns:1fr}}
.otd-story-box{{padding:16px 22px;display:flex;flex-direction:column;justify-content:space-between;gap:8px}}
.otd-story-bn{{padding:18px 20px;flex:1;display:flex;flex-direction:column;justify-content:space-between;gap:10px}}
.otd-story-hl{{font-size:19.5px;font-weight:900;color:#FDE047}}
.otd-story-body{{font-weight:600;color:#F1F5F9;line-height:1.62}}
.otd-nums-col{{display:flex;flex-direction:column;gap:10px}}
.otd-nums-grid-3{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}
.otd-num-row{{padding:10px 16px;display:flex;align-items:center;justify-content:space-between;gap:10px}}
.otd-num-meta{{min-width:0}}
.otd-num-unit{{font-size:17px;font-weight:900;color:#FFFFFF;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.otd-num-sub{{font-size:14px;font-weight:600;color:#CBD5E1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.otd-num-val{{font-size:29px;font-weight:800;line-height:1;color:#FFFFFF;flex-shrink:0}}

/* Tactical Slide */
.otd-tac-bn-grid{{flex:1;display:grid;grid-template-columns:7fr 5fr;gap:22px;align-items:stretch;min-height:0}}
.otd-tac-top{{padding:14px 22px;display:flex;align-items:center;justify-content:space-between;gap:14px;flex-shrink:0}}
.otd-tac-score{{padding:8px 18px;display:flex;align-items:center;gap:14px;flex-shrink:0}}
.otd-tac-snum{{font-size:34px;font-weight:900;line-height:1}}
.otd-tac-title{{font-size:26px;font-weight:900;color:#FFFFFF;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.otd-tac-agg{{font-size:16.5px;font-weight:700;color:#FDE047;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.otd-tac-year{{font-size:52px;flex-shrink:0}}
.otd-pitch-card{{padding:18px 24px;flex:1;display:flex;flex-direction:column;justify-content:space-between;gap:12px;min-height:0}}
.otd-pitch-hdr{{border-bottom:1px solid rgba(255,255,255,.12);padding-bottom:12px;gap:12px}}
.otd-pitch-title{{font-size:25px;font-weight:900;color:#FFFFFF;line-height:1.2}}
.otd-pitch-sub{{font-size:15.5px;font-weight:700;color:#CBD5E1}}
.otd-pitch-badge{{font-size:15px;font-weight:800;padding:6px 14px;border-radius:12px;
  background:rgba(230,46,69,.20);border:1px solid rgba(230,46,69,.50);color:#FF7A8B;flex-shrink:0}}
.otd-pitch-stage{{flex:1;display:flex;align-items:center;justify-content:center;min-height:0}}
.otd-pitch-cap{{font-size:20px;font-weight:700;color:#F1F5F9;line-height:1.58;border-top:1px solid rgba(255,255,255,.12);padding-top:12px}}
.otd-tnum-card{{padding:18px 16px;display:flex;flex-direction:column;align-items:center;text-align:center;gap:6px}}
.otd-tnum-bar{{position:absolute;top:0;left:0;right:0;height:6px}}
.otd-tnum-val{{font-size:44px;font-weight:800;color:#FFFFFF;line-height:1;margin-top:4px}}
.otd-tnum-unit{{font-size:20px;font-weight:900}}
.otd-tnum-sub{{font-size:15.5px;font-weight:600;color:#CBD5E1}}

/* Collector Slide */
.otd-foil-card{{flex:1;padding:24px 28px;display:flex;flex-direction:column;justify-content:space-between;gap:18px}}
.otd-col-top{{border-bottom:1px solid rgba(255,255,255,.14);padding-bottom:14px;gap:12px}}
.otd-col-badge{{padding:5px 14px;border-radius:9px;background:rgba(250,204,21,.20);border:1px solid rgba(250,204,21,.50);
  color:#FDE047;font-size:15px;font-weight:800;letter-spacing:.10em;flex-shrink:0}}
.otd-col-kicker{{font-size:19px;font-weight:800;color:#E2E8F0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.otd-col-code{{font-size:17px;font-weight:800;color:#CBD5E1;letter-spacing:.14em;flex-shrink:0}}
.otd-col-faceoff{{position:relative;z-index:10;display:grid;grid-template-columns:1fr 1fr 1fr;align-items:center;gap:14px;margin:auto 0}}
.otd-col-team{{display:flex;flex-direction:column;align-items:center;gap:8px}}
.otd-col-tname{{font-size:30px;font-weight:900;color:#FFFFFF}}
.otd-col-mid{{display:flex;flex-direction:column;align-items:center;text-align:center;gap:8px}}
.otd-col-score{{padding:10px 26px;display:flex;align-items:center;gap:22px}}
.otd-col-snum{{font-size:50px;font-weight:900;line-height:1}}
.otd-col-dash{{font-size:24px;font-weight:900;color:#94A3B8}}
.otd-col-title{{font-size:19px;font-weight:800;color:#FDE047;margin-top:4px}}
.otd-col-milestone{{position:relative;z-index:10;display:flex;flex-direction:column;align-items:center;text-align:center;gap:12px;margin:auto 0}}
.otd-col-mtitle{{font-size:44px;font-weight:900;color:#FFFFFF}}
.otd-col-msub{{font-size:22px;font-weight:700;color:#E2E8F0;max-width:86%;line-height:1.6}}
.otd-col-num{{border-radius:18px;padding:16px;background:rgba(0,0,0,.38);border:1px solid rgba(255,255,255,.15);
  display:flex;flex-direction:column;align-items:center;text-align:center;gap:5px}}
.otd-col-nval{{font-size:40px;font-weight:800;color:#FFFFFF;line-height:1}}
.otd-col-nunit{{font-size:18.5px;font-weight:900}}
.otd-col-nsub{{font-size:15px;font-weight:600;color:#CBD5E1}}

/* Legacy Split */
.otd-legacy-grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
.otd-legacy-border{{padding-top:10px;border-top:1px solid rgba(255,255,255,.12)}}
.otd-leg-card{{padding:16px 18px;border-radius:18px;display:flex;flex-direction:column;gap:6px}}
.otd-leg-before{{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.12);border-right:5px solid #94A3B8}}
.otd-leg-after{{background:rgba(16,185,129,.10);border:1px solid rgba(52,211,153,.35);border-right:5px solid #10B981}}
.otd-leg-ttl-b{{font-size:19px;font-weight:900;color:#CBD5E1}}
.otd-leg-ttl-a{{font-size:19px;font-weight:900;color:#6EE7B7}}
.otd-leg-txt-b{{font-size:17px;font-weight:600;color:#E2E8F0;line-height:1.56}}
.otd-leg-txt-a{{font-size:17px;font-weight:600;color:#FFFFFF;line-height:1.56}}

/* Editorial Slide */
.otd-quote-stage{{position:relative;flex:1;display:flex;flex-direction:column;justify-content:center;align-items:flex-start;gap:20px;padding:10px 0}}
.otd-quote-bn{{padding-left:28px;border-left:1px solid rgba(255,255,255,.12)}}
.otd-quote-year{{position:absolute;left:18px;top:24px}}
.otd-quote-icon{{position:relative;z-index:10;width:84px;height:84px;filter:drop-shadow(0 0 24px var(--xg-accent-glow))}}
.otd-blockquote{{position:relative;z-index:10;font-weight:900;color:#FFFFFF;line-height:1.42;padding-right:22px;
  border-right:6px solid var(--xg-accent);text-shadow:0 10px 26px rgba(0,0,0,.90)}}
.otd-quote-dash{{width:52px;height:3px;border-radius:99px;background:var(--xg-accent)}}
.otd-quote-by{{font-size:26px;font-weight:900;color:var(--xg-accent-soft)}}
.otd-quote-role{{font-size:18.5px;font-weight:700;color:#CBD5E1}}
.otd-ed-story{{padding:20px 22px;display:flex;flex-direction:column;gap:12px}}
.otd-ed-shdr{{border-bottom:1px solid rgba(255,255,255,.12);padding-bottom:10px;gap:10px}}
.otd-ed-score{{font-size:26px;font-weight:900;color:#FFFFFF;flex-shrink:0}}
.otd-ed-title{{font-size:22px;font-weight:900;color:#FDE047;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.otd-ed-body{{font-size:19.5px;font-weight:600;color:#F1F5F9;line-height:1.65}}
.otd-ed-tag{{display:flex;align-items:center;gap:10px;padding-top:10px;border-top:1px solid rgba(255,255,255,.10);
  font-size:17.5px;font-weight:800;color:#6EE7B7}}
.otd-emerald-dot{{width:10px;height:10px;border-radius:999px;background:#34D399;flex-shrink:0}}

footer, footer .fbw, footer .cf-row, footer .fi, footer .cf-left, footer .cf-right, .xg-footer, .foot-row, .card-footer{{flex-wrap:nowrap!important;white-space:nowrap!important;min-width:0!important;}}
footer span, footer div, .pl-foot-tag, .pl-foot-s, .in-foot-tag, .pr-foot-tag, .st-foot-tag, .cf-tag{{white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;min-width:0!important;}}
</style>
</head>
<body>
<div class="otd-canvas" dir="rtl">
  <div class="otd-photo-layer">{bg_img_html}<div class="otd-color-grade"></div></div>
  <div class="otd-ambient"></div>
  <svg class="otd-frame-svg" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid slice" fill="none">
    <defs>
      <pattern id="tg" width="54" height="54" patternUnits="userSpaceOnUse"><path d="M54 0H0v54" stroke="#F8FAFC" stroke-opacity=".05"/></pattern>
      <radialGradient id="rf" cx="50%" cy="32%" r="48%">
        <stop offset="0" stop-color="{th["accent"]}" stop-opacity=".26"/>
        <stop offset=".55" stop-color="{th["accent"]}" stop-opacity=".07"/>
        <stop offset="1" stop-color="{th["accent"]}" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect width="100%" height="100%" fill="url(#tg)"/>
    <rect x="12" y="12" width="{w - 24}" height="{h - 24}" rx="18" stroke="#F8FAFC" stroke-opacity=".12" stroke-width="1.5"/>
    <g stroke="#F8FAFC" stroke-opacity=".08" stroke-width="1.4">
      <line x1="{w // 2}" y1="16" x2="{w // 2}" y2="{h - 16}" stroke-dasharray="7 9"/>
      <circle cx="{w // 2}" cy="{int(h * 0.30)}" r="190"/>
      <circle cx="{w // 2}" cy="{int(h * 0.30)}" r="290" stroke-dasharray="3 8" stroke-opacity=".14"/>
    </g>
    <circle cx="{w // 2}" cy="{int(h * 0.30)}" r="320" fill="url(#rf)"/>
    <path d="{crh_d}" stroke="{th["accent"]}" stroke-opacity=".62" stroke-width="2.2"/>
  </svg>
  <div class="otd-scanlines"></div>
  {spine_html}
  <header class="otd-header">
    <div class="otd-hdr-left">
      <div class="otd-hdr-row1">
        <div class="otd-badge">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
          <span>در چنین روزی</span>
        </div>
        <span class="otd-date-pill">{esc(fa(event.get("dateFa", "")))}</span>
        <span class="otd-ago-pill">{esc(fa(f"{yrs_ago} سال پیش"))}</span>
      </div>
      <div class="otd-hdr-row2">{meta_html}</div>
    </div>
    {_brand_header_logo(th["accent"])}
  </header>
  <main class="otd-stage">{stage_html}</main>
  <footer class="otd-footer">
    <div class="otd-footer-line"></div>
    <div class="fbw otd-gap-14">
      <div class="fi otd-gap-12 otd-minw-0">
        <span class="otd-foot-dot"></span>
        <span dir="ltr" class="fm otd-foot-tag">{esc(footer_tag)}</span>
      </div>
      <div class="fi otd-gap-12 fm otd-shrink-0" dir="ltr">
        <span class="otd-foot-handle">@XGPedia</span>
        <span class="otd-sep">|</span>
        <span class="otd-foot-src">{esc(source_txt)}</span>
      </div>
    </div>
  </footer>
</div>
</body>
</html>"""


def build_on_this_day_caption(event: dict[str, Any], *, slide: str = "cover") -> str:
    """تولید کپشن تحریریهٔ مستند فارسی (متن تمیز بدون تگ HTML تکراری برای تلگرام)."""
    date_fa = fa(event.get("dateFa") or "")
    sub = fa(event.get("subtitle") or "")
    story_body = fa((event.get("story") or {}).get("body") or "")
    quote = event.get("quote") if isinstance(event.get("quote"), dict) else None
    home = event.get("home") if isinstance(event.get("home"), dict) else None
    away = event.get("away") if isinstance(event.get("away"), dict) else None

    lines: list[str] = []
    if home and away:
        lines.append(
            f"⚽ {fa(home['name'])} {fa(home['score'])}–{fa(away['score'])} {fa(away['name'])}"
            + (f" | {date_fa}" if date_fa else "")
        )
    elif date_fa:
        lines.append(f"📅 {date_fa}")

    if sub:
        lines.append(sub)
    if story_body and story_body != sub:
        lines.append(story_body)
    if quote and quote.get("text"):
        lines.append(f"💬 {fa(quote['text'])} — {fa(quote.get('by', ''))}")

    return "\n\n".join(lines)
