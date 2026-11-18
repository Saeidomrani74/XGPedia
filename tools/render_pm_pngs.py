"""رندر PNG کارت‌های پس‌از‌بازی + شبیه‌سازی نمایش روی گوشی (~390px عرض).

خروجی‌ها در /tmp/pmcheck: کارت کامل + نسخهٔ گوشی (برای قضاوت خوانایی D24).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.xgpedia.render.post_match_cards import render_post_match_html
from src.xgpedia.render.render_png import render_sync

_spec = importlib.util.spec_from_file_location("tpm", ROOT / "tests" / "test_post_match_cards.py")
_tpm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_tpm)
draft, facts = _tpm._draft(), _tpm._facts()

OUT = Path("/tmp/pmcheck")
OUT.mkdir(parents=True, exist_ok=True)

from src.xgpedia.render.cards import FORMATS

for fmt in ("4:5", "9:16", "16:9"):
    w, h = FORMATS[fmt]
    html = render_post_match_html(draft, facts, fmt=fmt)
    hp = OUT / f"card_{fmt.replace(':', '_')}.html"
    hp.write_text(html, encoding="utf-8")
    png = OUT / f"card_{fmt.replace(':', '_')}.png"
    render_sync(str(hp), str(png), w, h, "png")
    print(f"{fmt}: {png.name} {png.stat().st_size // 1024} KB")

# نسخهٔ گوشی: عرض ۳۹۰px — همان چیزی که کاربر در تلگرام/اینستاگرام می‌بیند
from PIL import Image

for fmt in ("4:5", "9:16", "16:9"):
    src = OUT / f"card_{fmt.replace(':', '_')}.png"
    with Image.open(src) as im:
        im = im.convert("RGB")
        ph = round(im.height * 390 / im.width)
        small = im.resize((390, ph), Image.LANCZOS)
        dst = OUT / f"phone_{fmt.replace(':', '_')}.jpg"
        small.save(dst, "JPEG", quality=82)
        print(f"phone {fmt}: {dst.name} {dst.stat().st_size // 1024} KB")
