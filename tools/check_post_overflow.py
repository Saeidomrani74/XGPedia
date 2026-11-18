"""اندازه‌گیری سرریز کارت‌های پیش‌بازی و پس‌از‌بازی در هر ۳ فرمت — به جای حدس، عدد.

روی هر HTML رندرشده با پلی‌رایت:
  - scrollHeight/clientHeight هر سکشن و هر کارت ماژول (سرریز = بریده‌شدن محتوا)
  - scrollWidth/clientWidth متن‌های nowrap (کوتاه‌شدگی با ellipsis)
  - ارتفاع واقعی سکشن‌ها برای تنظیم کف‌های D24

Usage (project root): python tools/check_post_overflow.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.xgpedia.render.cards import FORMATS, render_preview_html 
from src.xgpedia.render.post_match_cards import render_post_match_html 


def _fixture(test_file: str):
    spec = importlib.util.spec_from_file_location(test_file, ROOT / "tests" / test_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_pm = _fixture("test_post_match_cards.py")
_pv = _fixture("test_render_cards.py")

# (نام کارت، تابع رندر، draft، facts)
CARDS = [
    ("post-match", render_post_match_html, _pm._draft(), _pm._facts()),
    ("preview", render_preview_html, _pv._draft(), _pv._facts()),
]

OUT = Path("/tmp/pmcheck")
OUT.mkdir(parents=True, exist_ok=True)

JS = """
() => {
  const px = (el) => Math.round(el.getBoundingClientRect().height);
  const out = {sections: [], cards: [], clipped_text: []};
  for (const sel of ['#card-masthead', '#card-hero-section', '#modules-grid', '#card-footer', '#card-main-body']) {
    const el = document.querySelector(sel);
    if (el) out.sections.push([sel, px(el), el.scrollHeight > el.clientHeight + 2 ? 'OVERFLOW' : 'ok']);
  }
  document.querySelectorAll('.xg-glass-card, .xg-tactical-editorial').forEach((el) => {
    const t = (el.querySelector('.mod-title')?.textContent || '').trim();
    // سرریزِ واقعی = تهِ فرزندان غیرمطلق بیرون از کادر؛ شبه‌عنصر/سVG تزئینیِ مطلق
    // (مثل بیضی editorial) عمداً با overflow:hidden بریده می‌شود و سرریز حساب نمی‌شود
    const rect = el.getBoundingClientRect();
    let contentBottom = rect.top;
    for (const c of el.children) {
      if (getComputedStyle(c).position === 'absolute') continue;
      contentBottom = Math.max(contentBottom, c.getBoundingClientRect().bottom);
    }
    const over = contentBottom > rect.bottom + 2;
    out.cards.push([t, Math.round(rect.height), Math.round(contentBottom - rect.top),
                    Math.round(rect.height), over ? 'OVERFLOW' : 'ok']);
  });
  for (const sel of ['.team-name', '.mod-title', '.story-title', '.team-sub', '.focus-title']) {
    document.querySelectorAll(sel).forEach((el) => {
      if (el.scrollWidth > el.clientWidth + 2)
        out.clipped_text.push([sel, el.textContent.trim().slice(0, 24), el.scrollWidth, el.clientWidth]);
    });
  }
  const grid = document.querySelector('#modules-grid');
  if (grid) out.grid_h = px(grid);
  return out;
}
"""


def main() -> int:
    from playwright.sync_api import sync_playwright

    failures = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for card_name, render_fn, draft, facts in CARDS:
            for fmt in ("4:5", "9:16", "16:9"):
                w, h = FORMATS[fmt]
                html = render_fn(draft, facts, fmt=fmt)
                hp = OUT / f"check_{card_name}_{fmt.replace(':', '_')}.html"
                hp.write_text(html, encoding="utf-8")
                page = browser.new_page(viewport={"width": w, "height": h})
                page.goto(f"file://{hp}")
                page.wait_for_timeout(250)
                r = page.evaluate(JS)
                print(f"\n════ {card_name} {fmt} ({w}x{h}) ════")
                for name, hgt, status in r["sections"]:
                    print(f"  {name:22s} h={hgt:4d}  {status}")
                    if status != "ok":
                        failures += 1
                print(f"  {'modules-grid height':22s} h={r.get('grid_h', 0)}")
                for title, hgt, sh, ch, status in r["cards"]:
                    print(f"  card «{title}» h={hgt} scroll={sh}/{ch}  {status}")
                    if status != "ok":
                        failures += 1
                for sel, txt, sw, cw in r["clipped_text"]:
                    print(f"  CLIPPED {sel} «{txt}…» {sw}>{cw}")
                page.close()
        browser.close()
    print(f"\n{'FAIL: ' + str(failures) + ' overflow' if failures else 'ALL OK - no overflow'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
