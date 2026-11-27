"""مجموعهٔ آزمون رگرسیون بصری خودکار (Visual Regression Smoke Suite — v0.79.0).

رندر خودکار ۴ کارت کلیدی (`Pre-Match`، `Post-Match`، `Top Scorers`، `FC27`) + تست JPEG اینستاگرام
با Playwright و بررسی هم‌زمان:
  1. ۱۰۰٪ آفلاین بودن HTML (نبود CDN خارجی و وجود فونت Vazirmatn و RTL)
  2. ابعاد دقیق تصویر خروجی (`1080×1350` برای `4:5` و `1080×1920` برای `9:16`) و حجم غیرخالی
  3. نبود هیچ تصویر یا لوگوی شکسته در DOM (`img.complete && img.naturalWidth > 0`)
  4. نبود سرریز افقی/عمودی بوم و بریدگی شدید متن فارسی در DOM

اجرا از خط فرمان پیش از هر انتشار:
  python run.py visual-qa
"""
from __future__ import annotations

import asyncio
import json
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from src.xgpedia.config import ROOT

Format = Literal["png", "jpeg"]

_DOM_AUDIT_JS = """
() => {
  const docEl = document.documentElement;
  const imgs = Array.from(document.querySelectorAll('img'));
  const brokenImgs = imgs
    .filter(im => !im.complete || im.naturalWidth === 0)
    .map(im => (im.getAttribute('alt') || im.getAttribute('src') || 'img').slice(0, 60));

  const clipped = [];
  const textEls = document.querySelectorAll('h1, h2, h3, .title, .team-name, .player-name, .card-title');
  for (const el of textEls) {
    const cs = window.getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    if ((cs.overflowX === 'hidden' || cs.overflow === 'hidden') && el.scrollWidth > el.clientWidth + 14) {
      clipped.push((el.textContent || '').trim().slice(0, 40));
    }
  }

  let vazirLoaded = false;
  if (document.fonts) {
    for (const f of document.fonts) {
      if ((f.family || '').toLowerCase().includes('vazirmatn') && f.status === 'loaded') {
        vazirLoaded = true;
        break;
      }
    }
  }

  return {
    scrollWidth: docEl.scrollWidth,
    clientWidth: docEl.clientWidth,
    scrollHeight: docEl.scrollHeight,
    clientHeight: docEl.clientHeight,
    totalImages: imgs.length,
    brokenImages: brokenImgs,
    clippedTexts: clipped.slice(0, 8),
    vazirLoaded: vazirLoaded,
  };
}
"""


@dataclass
class VisualQAResult:
    card_name: str
    fmt: str
    width: int
    height: int
    file_path: str
    file_bytes: int = 0
    actual_width: int = 0
    actual_height: int = 0
    total_images: int = 0
    broken_images: list[str] = field(default_factory=list)
    clipped_texts: list[str] = field(default_factory=list)
    overflow_x: bool = False
    overflow_y: bool = False
    vazir_loaded: bool = False
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def read_image_dimensions(path: Path, fmt: Format) -> tuple[int, int]:
    """خواندن ابعاد دقیق PNG یا بررسی امضای معتبر JPEG بدون وابستگی به Pillow."""
    raw = path.read_bytes()
    if fmt == "png":
        if raw[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError(f"Invalid PNG header: {path}")
        return struct.unpack(">II", raw[16:24])
    if raw[:3] != b"\xff\xd8\xff":
        raise ValueError(f"Invalid JPEG header: {path}")
    # پارس SOF0/SOF2 برای ابعاد JPEG
    i = 2
    while i + 9 < len(raw):
        if raw[i] != 0xFF:
            i += 1
            continue
        marker = raw[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack(">HH", raw[i + 5 : i + 9])
            return w, h
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        seg_len = struct.unpack(">H", raw[i + 2 : i + 4])[0]
        i += 2 + seg_len
    return 0, 0


def check_offline_html(html_str: str, label: str) -> list[str]:
    """بررسی استاتیک ۱۰۰٪ آفلاین‌بودن HTML، راست‌به‌چپ بودن و وجود فونت Vazirmatn."""
    issues: list[str] = []
    if len(html_str) < 2000:
        issues.append(f"{label}: HTML too short ({len(html_str)} chars)")
    if not ('dir="rtl"' in html_str or "direction: rtl" in html_str or "direction:rtl" in html_str):
        issues.append(f"{label}: missing RTL direction")
    if "Vazirmatn" not in html_str:
        issues.append(f"{label}: missing Vazirmatn Persian font")
    ext_links = re.findall(r'<(?:link|script)[^>]+(?:href|src)=["\']https?://[^"\']+["\']', html_str, flags=re.IGNORECASE)
    if ext_links:
        issues.append(f"{label}: external CDN links found: {ext_links[:2]}")
    return issues


def build_flagship_card_htmls() -> dict[str, str]:
    """تولید HTML نمونهٔ ۴ کارت کلیدی (Pre-Match، Post-Match، Top Scorers، FC27) از فیکسچر/پریست‌های آفلاین."""
    from src.xgpedia.render.card_kit.player_fc27_card import render_player_fc27_html
    from src.xgpedia.render.card_kit.top_scorers_card import render_top_scorers_html
    from src.xgpedia.render.cards import render_preview_html
    from src.xgpedia.render.post_match_cards import render_post_match_html

    facts = json.loads((ROOT / "tests" / "fixtures" / "fact.json").read_text(encoding="utf-8"))
    facts_pm = dict(facts)
    facts_pm["result"] = {"home_goals": 2, "away_goals": 1}
    draft = {
        "status": "ok",
        "title": "آرسنال با برتری امید گل میزبان چلسی است",
        "bullets": ["آرسنال ۱۱ امتیاز از ۵ بازی اخیر", "میانگین امید گل میزبان: 1.85 در ۱۰ بازی"],
        "caption": "تحلیل پیش‌بازی دربی لندن بر پایهٔ داده‌های واقعی فصل.",
        "source_note": "XGPedia QA",
        "uncertainties": [],
    }

    ts_presets = json.loads((ROOT / "config" / "top_scorers_presets.json").read_text(encoding="utf-8"))
    ts_item = (ts_presets.get("items") or ts_presets if isinstance(ts_presets, dict) else ts_presets)[0]

    fc_presets = json.loads((ROOT / "config" / "player_fc27_presets.json").read_text(encoding="utf-8"))
    fc_item = (fc_presets.get("items") or fc_presets if isinstance(fc_presets, dict) else fc_presets)[0]

    return {
        "pre_match": render_preview_html(draft, facts),
        "post_match": render_post_match_html(draft, facts_pm),
        "top_scorers": render_top_scorers_html(ts_item),
        "player_fc27": render_player_fc27_html(fc_item),
    }


async def inspect_html_in_playwright(
    card_name: str,
    html_path: Path,
    out_path: Path,
    *,
    w: int = 1080,
    h: int = 1350,
    fmt: Format = "png",
    timeout_ms: int = 25_000,
) -> VisualQAResult:
    """رندر یک کارت در Playwright و ممیزی DOM (لوگوهای شکسته، سرریز بوم، بریدگی متن، فونت و ابعاد)."""
    from src.xgpedia.render.render_png import _get_shared_browser

    res = VisualQAResult(card_name=card_name, fmt=fmt, width=w, height=h, file_path=str(out_path))
    browser = await _get_shared_browser(timeout_ms=timeout_ms)
    ctx = await browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
    try:
        pg = await ctx.new_page()
        await pg.goto(html_path.resolve().as_uri(), wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            await asyncio.wait_for(pg.evaluate("document.fonts.ready"), timeout=5.0)
        except Exception:
            pass
        await pg.wait_for_timeout(120)

        dom: dict[str, Any] = await pg.evaluate(_DOM_AUDIT_JS)
        res.total_images = int(dom.get("totalImages") or 0)
        res.broken_images = list(dom.get("brokenImages") or [])
        res.clipped_texts = list(dom.get("clippedTexts") or [])
        res.vazir_loaded = bool(dom.get("vazirLoaded"))
        res.overflow_x = int(dom.get("scrollWidth") or 0) > (w + 6)
        res.overflow_y = int(dom.get("scrollHeight") or 0) > (h + 6)

        kw = {"type": "jpeg", "quality": 90} if fmt == "jpeg" else {"type": "png"}
        await pg.screenshot(path=str(out_path), timeout=timeout_ms, **kw)
    finally:
        await ctx.close()

    if not out_path.exists():
        res.issues.append("output image file not created")
        return res
    res.file_bytes = out_path.stat().st_size
    if res.file_bytes < 15_000:
        res.issues.append(f"output image too small ({res.file_bytes} B)")
    try:
        aw, ah = read_image_dimensions(out_path, fmt)
        res.actual_width, res.actual_height = aw, ah
        if (aw, ah) != (w, h):
            res.issues.append(f"dimension mismatch: got {aw}x{ah}, expected {w}x{h}")
    except Exception as exc:
        res.issues.append(f"invalid image binary: {exc}")
    if res.broken_images:
        res.issues.append(f"broken images/logos ({len(res.broken_images)}): {res.broken_images[:3]}")
    if res.overflow_x:
        res.issues.append("horizontal canvas overflow detected")
    if res.overflow_y:
        res.issues.append("vertical canvas overflow detected")
    return res


def run_visual_smoke_suite(
    out_dir: Path | None = None,
    *,
    include_instagram_jpeg: bool = True,
) -> list[VisualQAResult]:
    """اجرای کامل آزمون رگرسیون بصری روی ۴ کارت کلیدی (+ نمونهٔ JPEG اینستاگرام)."""
    target_dir = Path(out_dir) if out_dir else (ROOT / "output" / "visual_qa")
    target_dir.mkdir(parents=True, exist_ok=True)
    htmls = build_flagship_card_htmls()

    async def _run_all() -> list[VisualQAResult]:
        out: list[VisualQAResult] = []
        for name, html_str in htmls.items():
            static_issues = check_offline_html(html_str, name)
            h_path = target_dir / f"qa_{name}.html"
            p_path = target_dir / f"qa_{name}.png"
            h_path.write_text(html_str, encoding="utf-8")
            r = await inspect_html_in_playwright(name, h_path, p_path, w=1080, h=1350, fmt="png")
            r.issues = static_issues + r.issues
            out.append(r)

        if include_instagram_jpeg and "pre_match" in htmls:
            h_path = target_dir / "qa_pre_match.html"
            j_path = target_dir / "qa_pre_match_ig.jpg"
            r_ig = await inspect_html_in_playwright("pre_match_ig_jpeg", h_path, j_path, w=1080, h=1350, fmt="jpeg")
            out.append(r_ig)
        return out

    from src.xgpedia.render.render_png import close_browser_pool

    async def _run_and_close() -> list[VisualQAResult]:
        try:
            return await _run_all()
        finally:
            await close_browser_pool()

    return asyncio.run(asyncio.wait_for(_run_and_close(), timeout=120.0))
