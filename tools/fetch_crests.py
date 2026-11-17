"""دانلود لوگوی رسمی تیم‌ها → brand/crests/{CODE}.svg — ابزار مستقل (فقط stdlib).

منبع: Wikimedia Commons از طریق Special:FilePath — نسخهٔ SVG (برداری، باکیفیت)
اولویت دارد؛ اگر SVG نبود PNG همان کد ذخیره می‌شود. رندرر (cards.py) خودش
svg-اول می‌گزیند و برای تیم بدون فایل، نشان انتزاعی یک‌دست می‌سازد.

اجرا:  python tools/fetch_crests.py [--force] [--only ARS,LIV]

لایسنس/استفاده: نشان باشگاه‌ها علامت تجاری‌اند؛ مصرف اینجا نمایشی-تحریریه
(شناسایی تیم در کارت آماری) است — همان به‌کارگیری رایج رسانه‌ها. اگر روزی
کاربرد تجاری شد، جایگزین رسمی/مجاز لازم است.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDENTITIES = ROOT / "config" / "team_identities.json"
OUT_DIR = ROOT / "brand" / "crests"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 XGPediaCrestFetcher/1.0"
)
TIMEOUT = 25

# نام canonical → فایل نشان رسمی. نشان‌های جاری باشگاه‌های انگلیسی «استفادهٔ منصفانه»
# هستند و روی en.wikipedia (آپلود محلی) می‌زنند نه Commons؛ همهٔ نام‌ها با API راستی‌آزمایی شده‌اند.
COMMONS_NAMES: dict[str, list[str]] = {
    "Arsenal": ["Arsenal FC.svg"],
    "Aston Villa": ["Aston Villa FC new crest.svg"],
    "Bournemouth": ["AFC Bournemouth (2013).svg"],
    "Brentford": ["Brentford FC crest.svg"],
    "Brighton": ["Brighton and Hove Albion FC crest.svg"],
    "Chelsea": ["Chelsea FC.svg"],
    "Coventry City": ["Coventry City FC crest.svg"],
    "Crystal Palace": ["Crystal Palace FC logo (2022).svg"],
    "Everton": ["Everton F.C. (2013).svg"],
    "Fulham": ["Fulham FC.svg"],
    "Hull City": ["Hull City A.F.C. logo.svg"],
    "Ipswich Town": ["Ipswich Town.svg"],
    "Leeds United": ["Leeds United F.C. logo.svg"],
    "Liverpool": ["Liverpool FC.svg"],
    "Manchester City": ["Manchester City FC badge.svg"],
    "Manchester United": ["Manchester United FC crest.svg"],
    "Newcastle United": ["Newcastle United Logo.svg"],
    "Nottingham Forest": ["Nottingham Forest F.C. logo.svg"],
    "Sunderland": ["Logo Sunderland.svg"],
    "Tottenham": ["Tottenham Hotspur.svg"],
}

WIKIS = ("en.wikipedia.org", "commons.wikimedia.org")  # اول انگلیسی؛ فال‌بک کامانز


def _fetch(url: str) -> tuple[bytes | None, str | None]:
    """دانلود یک URL؛ خروجی (داده، content-type). None = خطا."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read(), resp.headers.get("Content-Type", "")
    except Exception as e:  # noqa: BLE001 - گزارش خطا مهم‌تر از نوع آن است
        print(f"    ! {type(e).__name__}: {e}")
        return None, None


def _looks_valid(data: bytes, suffix: str) -> bool:
    """رد کردن صفحهٔ خطای HTML/مسیر اشتباه — فایل باید با امضای درست شروع شود."""
    head = data[:600].lstrip()
    if suffix == ".svg":
        return b"<svg" in head or b"<?xml" in head
    return data[:8] == b"\x89PNG\r\n\x1a\n"


def _direct_url(name: str) -> str | None:
    """URL مستقیم upload.wikimedia.org از طریق imageinfo — مسیر دوم وقتی FilePath محدود شده."""
    import json

    url = (
        "https://en.wikipedia.org/w/api.php?"
        + urllib.parse.urlencode({
            "action": "query", "titles": f"File:{name}",
            "prop": "imageinfo", "iiprop": "url", "format": "json",
        })
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        data = json.loads(urllib.request.urlopen(req, timeout=TIMEOUT).read())
        for pg in data["query"]["pages"].values():
            if "imageinfo" in pg:
                return pg["imageinfo"][0]["url"].split("?")[0]
    except Exception as e:  # noqa: BLE001
        print(f"    ! imageinfo: {type(e).__name__}: {e}")
    return None


def fetch_team(canonical: str, code: str, force: bool) -> str:
    for suffix in (".svg", ".png"):
        out = OUT_DIR / f"{code}{suffix}"
        if out.exists() and not force:
            return f"skip (exists: {out.name})"
        for name in COMMONS_NAMES.get(canonical, []):
            urls = [f"https://{host}/wiki/Special:FilePath/{urllib.parse.quote(name)}" for host in WIKIS]
            direct = _direct_url(name)
            if direct:
                urls.append(direct)
            for url in urls:
                print(f"    → {urllib.parse.urlparse(url).netloc.split('.')[0]}:{name}")
                data, ctype = _fetch(url)
                if data and _looks_valid(data, suffix):
                    OUT_DIR.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(data)
                    return f"ok   {out.name} ({len(data) // 1024} KB, {ctype.split(';')[0]})"
                if data is not None:
                    print(f"    ! محتوای نامعتبر ({ctype}) — گزینهٔ بعدی")
    return "FAIL — نشان انتزاعی استودیو جایگزین می‌شود"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="دانلود مجدد حتی اگر فایل موجود است")
    ap.add_argument("--only", default=None, help="فقط این کدها (جداشده با کاما): ARS,LIV")
    args = ap.parse_args(argv)

    identities = json.loads(IDENTITIES.read_text(encoding="utf-8"))["teams"]
    only = {x.strip().upper() for x in args.only.split(",")} if args.only else None

    results: list[tuple[str, str, str]] = []
    for canonical, ident in identities.items():
        code = ident["code"]
        if only and code not in only:
            continue
        print(f"[{code}] {canonical}")
        results.append((code, canonical, fetch_team(canonical, code, args.force)))

    ok = sum(1 for _, _, r in results if r.startswith(("ok", "skip")))
    print("\n──── خلاصه ────")
    for code, canonical, r in results:
        print(f"  {code:4} {canonical:22} {r}")
    print(f"\n{ok}/{len(results)} تیم لوگو دارد؛ بقیه با نشان انتزاعی استودیو رندر می‌شوند.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
