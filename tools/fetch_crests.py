"""دانلود لوگوی رسمی تمام ۱۵۱ باشگاه → brand/crests/{CODE}.svg|png — ابزار مستقل (فقط stdlib).

زنجیرهٔ منابع (بدون نیاز به requests یا توکن):
  1. Wikimedia / Wikipedia SVG رسمی (برای نام‌های راستی‌آزمایی‌شده)
  2. CDN عمومی football-data.org (`https://crests.football-data.org/{fdo_id}.svg|.png`) بر پایهٔ `config/team_mapping.json`
  3. API عمومی تیم‌های ESPN (`site.api.espn.com`) برای لیگ‌های اروپایی (نشان رسمی 500×500 PNG)

اجرا:
  python tools/fetch_crests.py --only-placeholders     # ارتقای ۱۳۱ نشان مونوگرام موقت به لوگوی واقعی
  python tools/fetch_crests.py --only ARS,RMA,BAR      # فقط باشگاه‌های مشخص
  python tools/fetch_crests.py --force --workers 6     # دانلود مجدد همهٔ ۱۵۱ باشگاه به‌صورت موازی
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import sys
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
IDENTITIES = ROOT / "config" / "team_identities.json"
MAPPING = ROOT / "config" / "team_mapping.json"
OUT_DIR = ROOT / "brand" / "crests"

UA = "XGPediaCrestFetcher/2.1 (https://t.me/XGPedia; football-data-media) Python-urllib/3"
LOGO_REGISTRY = ROOT / "data" / "team_logos.json"
TIMEOUT = 20
PLACEHOLDER_MAX_BYTES = 1500  # مونوگرام‌های سه‌حرفی تولیدشده زیر ۱۵۰۰ بایت هستند

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

WIKIS = ("en.wikipedia.org", "commons.wikimedia.org")
ESPN_LEAGUE_SLUGS = (
    "eng.1", "eng.2", "esp.1", "ita.1", "ger.1", "fra.1",
    "uefa.champions", "uefa.europa",
    "por.1", "ned.1", "bel.1", "tur.1", "gre.1", "sco.1",
)


def _norm(text: str) -> str:
    s = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).strip().lower()


def is_placeholder_crest(path: Path) -> bool:
    """تشخیص مونوگرام سه‌حرفی موقت (SVG کوچک زیر ۱۵۰۰ بایت) از لوگوی واقعی."""
    if not path.exists():
        return True
    if path.suffix.lower() == ".svg" and path.stat().st_size < PLACEHOLDER_MAX_BYTES:
        return True
    return False


def _fetch(url: str, timeout: int = TIMEOUT) -> tuple[bytes | None, str | None]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(), resp.headers.get("Content-Type", "")
    except Exception:
        return None, None


def _looks_valid(data: bytes, suffix: str) -> bool:
    if not data or len(data) < 200:
        return False
    head = data[:600].lstrip()
    if suffix == ".svg":
        return (b"<svg" in head or b"<?xml" in head) and len(data) >= PLACEHOLDER_MAX_BYTES
    return data[:8] == b"\x89PNG\r\n\x1a\n"


def _direct_wiki_url(name: str) -> str | None:
    url = (
        "https://en.wikipedia.org/w/api.php?"
        + urllib.parse.urlencode({
            "action": "query",
            "titles": f"File:{name}",
            "prop": "imageinfo",
            "iiprop": "url",
            "format": "json",
        })
    )
    data, _ = _fetch(url)
    if not data:
        return None
    try:
        payload = json.loads(data)
        for pg in payload.get("query", {}).get("pages", {}).values():
            if "imageinfo" in pg:
                return pg["imageinfo"][0]["url"].split("?")[0]
    except Exception:
        return None
    return None


def _build_espn_logo_index() -> dict[str, str]:
    """بارگذاری یک‌بارهٔ نقشهٔ نام تیم → URL لوگوی رسمی PNG از ESPN برای لیگ‌های اروپایی."""
    index: dict[str, str] = {}
    for slug in ESPN_LEAGUE_SLUGS:
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/teams?limit=100"
        raw, _ = _fetch(url, timeout=5)
        if not raw:
            continue
        try:
            data = json.loads(raw)
            for sp in data.get("sports", []):
                for lg in sp.get("leagues", []):
                    for item in lg.get("teams", []):
                        team = item.get("team", {})
                        logos = team.get("logos") or []
                        href = logos[0].get("href") if logos and isinstance(logos[0], dict) else None
                        if not href:
                            continue
                        for key in (
                            team.get("displayName"),
                            team.get("shortDisplayName"),
                            team.get("name"),
                            team.get("location"),
                        ):
                            nk = _norm(key or "")
                            if nk and nk not in index:
                                index[nk] = href
        except Exception:
            continue
    return index




def _load_local_logo_registry() -> dict[str, str]:
    """خواندن رجیستری محلی data/team_logos.json (پرشده توسط dynamic_crests/ESPN/FDO)."""
    if not LOGO_REGISTRY.exists():
        return {}
    try:
        raw = json.loads(LOGO_REGISTRY.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return {_norm(k): str(v) for k, v in raw.items() if k and isinstance(v, str) and v.startswith("http")}
    except Exception:
        return {}
    return {}


def _lookup_fotmob_logo(canonical: str) -> str | None:
    """یافتن لوگوی رسمی PNG باشگاه از FotMob suggest API + CDN رسمی images.fotmob.com."""
    url = "https://www.fotmob.com/api/search/suggest?" + urllib.parse.urlencode({"term": canonical, "lang": "en"})
    raw, _ = _fetch(url, timeout=10)
    if not raw:
        return None
    try:
        groups = json.loads(raw)
        if not isinstance(groups, list):
            return None
        for grp in groups:
            if not isinstance(grp, dict):
                continue
            for opt in grp.get("options") or []:
                payload = opt.get("payload") if isinstance(opt, dict) else None
                if not isinstance(payload, dict):
                    continue
                if payload.get("type") == "team" and payload.get("id"):
                    tid = str(payload["id"]).strip()
                    if tid.isdigit():
                        return f"https://images.fotmob.com/image_resources/logo/teamlogo/{tid}.png"
    except Exception:
        return None
    return None


def _extract_thesportsdb_soccer_badge(payload: dict[str, Any]) -> str | None:
    """استخراج strBadge صرفاً برای تیم‌های فوتبال واقعی (strSport == Soccer)."""
    for team in payload.get("teams") or []:
        if not isinstance(team, dict):
            continue
        if (team.get("strSport") or "").strip().lower() != "soccer":
            continue
        badge = (team.get("strBadge") or team.get("strTeamBadge") or "").strip()
        if badge.startswith("http"):
            return badge
    return None


def _lookup_thesportsdb_badge(canonical: str, team_map_entry: dict[str, Any] | None = None) -> str | None:
    """جستجوی رایگان نشان تیم فوتبال در TheSportsDB v3 (فقط Association Football)."""
    queries = [canonical]
    short = canonical
    for tok in ("FC ", "FK ", "SC ", "AC ", "NK ", "SCU ", " FC", " FK", " SC", " FF", " SK"):
        short = short.replace(tok, " ").strip()
    if short and short != canonical:
        queries.append(short)
    if team_map_entry and team_map_entry.get("csv_short"):
        cs = str(team_map_entry["csv_short"]).strip()
        if cs and cs not in queries:
            queries.append(cs)

    for q in queries[:3]:
        url = "https://www.thesportsdb.com/api/v1/json/3/searchteams.php?" + urllib.parse.urlencode({"t": q})
        raw, _ = _fetch(url)
        if not raw:
            continue
        try:
            badge = _extract_thesportsdb_soccer_badge(json.loads(raw))
            if badge:
                return badge
        except Exception:
            continue
    return None


def _lookup_wikidata_logo_urls(canonical: str) -> list[tuple[str, str]]:
    """یافتن فایل لوگوی رسمی (P154) باشگاه از ویکی‌پدیا/ویکی‌دیتا."""
    out: list[tuple[str, str]] = []
    search_url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query",
        "list": "search",
        "srsearch": f'"{canonical}" football club',
        "srlimit": 1,
        "format": "json",
    })
    raw, _ = _fetch(search_url)
    if not raw:
        return out
    try:
        hits = json.loads(raw).get("query", {}).get("search") or []
        if not hits:
            return out
        title = hits[0]["title"]
        pp_url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
            "action": "query",
            "titles": title,
            "prop": "pageprops",
            "ppprop": "wikibase_item",
            "format": "json",
        })
        pp_raw, _ = _fetch(pp_url)
        if not pp_raw:
            return out
        qid = None
        for pg in json.loads(pp_raw).get("query", {}).get("pages", {}).values():
            qid = (pg.get("pageprops") or {}).get("wikibase_item")
            if qid:
                break
        if not qid:
            return out
        wd_url = f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
        wd_raw, _ = _fetch(wd_url)
        if not wd_raw:
            return out
        ent = json.loads(wd_raw).get("entities", {}).get(qid, {})
        claims = ent.get("claims", {}).get("P154") or []
        for cl in claims[:2]:
            fname = cl.get("mainsnak", {}).get("datavalue", {}).get("value")
            if not isinstance(fname, str) or not fname.strip():
                continue
            ext = ".svg" if fname.lower().endswith(".svg") else ".png"
            for host in WIKIS:
                out.append((ext, f"https://{host}/wiki/Special:FilePath/{urllib.parse.quote(fname)}"))
    except Exception:
        return out
    return out



def _extract_infobox_image_from_wikitext(wikitext: str) -> str | None:
    """استخراج نام فایل لوگو/عکس از فیلد `| image =` در Infobox بخش اول صفحهٔ ویکی‌پدیا."""
    import re as _re
    for pat in (
        r"^\s*\|\s*(?:image|logo|crest)\s*=\s*([^\n|{}]+)",
        r"\|\s*(?:image|logo|crest)\s*=\s*([^\n|{}]+)",
    ):
        m = _re.search(pat, wikitext or "", flags=_re.IGNORECASE | _re.MULTILINE)
        if m:
            raw = m.group(1).strip()
            # حذف کامنت HTML و پیشوند File:/Image: و [[...]]
            raw = _re.sub(r"<!--.*?-->", "", raw, flags=_re.DOTALL).strip()
            raw = raw.lstrip("[").split("|")[0].rstrip("]").strip()
            raw = _re.sub(r"^(?:File|Image):", "", raw, flags=_re.IGNORECASE).strip()
            if raw and any(raw.lower().endswith(ext) for ext in (".svg", ".png", ".jpg", ".jpeg", ".webp")):
                return raw
    return None


def _lookup_wikipedia_infobox_logo(canonical: str) -> list[tuple[str, str]]:
    """استخراج لوگوی رسمی (از جمله فایل‌های fair-use محلی en.wikipedia) از Infobox صفحهٔ باشگاه."""
    out: list[tuple[str, str]] = []
    for query in (f'"{canonical}" football club', f"{canonical} F.C.", canonical):
        search_url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": 3,
            "format": "json",
        })
        raw, _ = _fetch(search_url, timeout=12)
        if not raw:
            continue
        try:
            hits = json.loads(raw).get("query", {}).get("search") or []
        except Exception:
            continue
        for hit in hits[:2]:
            title = hit.get("title") or ""
            if not title:
                continue
            rev_url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
                "action": "query",
                "titles": title,
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
                "rvsection": 0,
                "format": "json",
            })
            rev_raw, _ = _fetch(rev_url, timeout=12)
            if not rev_raw:
                continue
            try:
                pages = json.loads(rev_raw).get("query", {}).get("pages", {})
                wikitext = ""
                for pg in pages.values():
                    revs = pg.get("revisions") or []
                    if revs:
                        slots = revs[0].get("slots", {})
                        wikitext = (slots.get("main") or {}).get("*") or revs[0].get("*") or ""
                        break
                fname = _extract_infobox_image_from_wikitext(wikitext)
                if not fname:
                    continue
                ext = ".svg" if fname.lower().endswith(".svg") else ".png"
                direct = _direct_wiki_url(fname)
                if direct:
                    out.append((ext, direct))
                for host in WIKIS:
                    out.append((ext, f"https://{host}/wiki/Special:FilePath/{urllib.parse.quote(fname)}"))
                if out:
                    return out
            except Exception:
                continue
    return out


def _lookup_espn_cdn_from_ucl_master(canonical: str) -> str | None:
    """دریافت مستقیم PNG 500x500 از CDN رسمی a.espncdn.com با استفاده از espn_id موجود در ucl_badges_free."""
    try:
        sys.path.insert(0, str(ROOT))
        from src.xgpedia.providers.ucl_badges_free import lookup_ucl_club
        hit = lookup_ucl_club(canonical)
        if hit and hit[4]:
            return f"https://a.espncdn.com/i/teamlogos/soccer/500/{hit[4]}.png"
    except Exception:
        return None
    return None


def build_candidate_urls(
    canonical: str,
    team_map_entry: dict[str, Any] | None = None,
    espn_index: dict[str, str] | None = None,
) -> list[tuple[str, str]]:
    """ساخت لیست اولویت‌دار `(suffix, url)` برای یک باشگاه از ۳ منبع بدون نیاز به توکن."""
    cands: list[tuple[str, str]] = []
    # ۱) Wikimedia SVG
    for name in COMMONS_NAMES.get(canonical, []):
        for host in WIKIS:
            cands.append((".svg", f"https://{host}/wiki/Special:FilePath/{urllib.parse.quote(name)}"))
        direct = _direct_wiki_url(name)
        if direct:
            cands.append((".svg", direct))

    # ۲) football-data.org public crest CDN (SVG اول، سپس PNG)
    fdo_id = (team_map_entry or {}).get("fdo_id")
    if fdo_id:
        cands.append((".svg", f"https://crests.football-data.org/{fdo_id}.svg"))
        cands.append((".png", f"https://crests.football-data.org/{fdo_id}.png"))

    # ۳) ESPN 500x500 official PNG
    if espn_index:
        probe_names = [canonical]
        if team_map_entry:
            if team_map_entry.get("csv_short"):
                probe_names.append(str(team_map_entry["csv_short"]))
            for al in team_map_entry.get("aliases") or []:
                probe_names.append(str(al))
        for nm in probe_names:
            href = espn_index.get(_norm(nm))
            if href:
                cands.append((".png", href))
                break
    return cands


def fetch_team(
    canonical: str,
    code: str,
    *,
    force: bool = False,
    only_placeholders: bool = False,
    team_map_entry: dict[str, Any] | None = None,
    espn_index: dict[str, str] | None = None,
) -> str:
    svg_out = OUT_DIR / f"{code}.svg"
    png_out = OUT_DIR / f"{code}.png"
    has_real = (svg_out.exists() and not is_placeholder_crest(svg_out)) or png_out.exists()
    if has_real and not force:
        existing = svg_out.name if (svg_out.exists() and not is_placeholder_crest(svg_out)) else png_out.name
        return f"skip (real: {existing})"
    if not force and not only_placeholders and svg_out.exists():
        return f"skip (exists: {svg_out.name})"

    def _try_download(cands: list[tuple[str, str]]) -> str | None:
        for suffix, url in cands:
            data, ctype = _fetch(url)
            if data and _looks_valid(data, suffix):
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                out = OUT_DIR / f"{code}{suffix}"
                out.write_bytes(data)
                if suffix == ".png" and svg_out.exists() and is_placeholder_crest(svg_out):
                    try:
                        svg_out.unlink()
                    except OSError:
                        pass
                return f"ok   {out.name} ({max(1, len(data) // 1024)} KB, {(ctype or '').split(';')[0]})"
        return None

    # ۱ تا ۳) منابع سریع (Wikimedia + football-data.org + ESPN)
    hit = _try_download(build_candidate_urls(canonical, team_map_entry=team_map_entry, espn_index=espn_index))
    if hit:
        return hit

    # ۳ب) رجیستری محلی data/team_logos.json (از dynamic_crests)
    local_reg = _load_local_logo_registry()
    reg_url = local_reg.get(_norm(canonical))
    if reg_url:
        reg_ext = ".svg" if reg_url.lower().endswith(".svg") else ".png"
        hit = _try_download([(reg_ext, reg_url)])
        if hit:
            return hit + " [Registry]"

    # ۴) FotMob CDN رسمی (images.fotmob.com)
    fm_url = _lookup_fotmob_logo(canonical)
    if fm_url:
        hit = _try_download([(".png", fm_url)])
        if hit:
            return hit + " [FotMob]"

    # ۵) TheSportsDB رایگان (strBadge — صرفاً Soccer)
    tsdb_badge = _lookup_thesportsdb_badge(canonical, team_map_entry=team_map_entry)
    if tsdb_badge:
        tsdb_ext = ".svg" if tsdb_badge.lower().endswith(".svg") else ".png"
        hit = _try_download([(tsdb_ext, tsdb_badge)])
        if hit:
            return hit + " [TheSportsDB]"

    # ۵ب) ESPN CDN مستقیم (a.espncdn.com) از روی espn_id موجود در ucl_badges_free
    espn_cdn = _lookup_espn_cdn_from_ucl_master(canonical)
    if espn_cdn:
        hit = _try_download([(".png", espn_cdn)])
        if hit:
            return hit + " [ESPN-CDN]"

    # ۶) Wikipedia Infobox Section-0 (`| image =` — پوشش فایل‌های fair-use محلی en.wikipedia)
    ib_cands = _lookup_wikipedia_infobox_logo(canonical)
    if ib_cands:
        hit = _try_download(ib_cands)
        if hit:
            return hit + " [Wiki-Infobox]"

    # ۷) Wikidata P154 (لوگوی رسمی از صفحهٔ ویکی‌دیتا)
    wd_cands = _lookup_wikidata_logo_urls(canonical)
    if wd_cands:
        hit = _try_download(wd_cands)
        if hit:
            return hit + " [Wikidata]"

    return "FAIL — نشان انتزاعی استودیو حفظ شد"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="دانلود مجدد حتی اگر لوگوی واقعی موجود است")
    ap.add_argument("--only-placeholders", action="store_true", help="فقط جایگزینی نشان‌های مونوگرام موقت (<1.5KB)")
    ap.add_argument("--only", default=None, help="فقط این کدها (جداشده با کاما): ARS,LIV,RMA")
    ap.add_argument("--workers", type=int, default=6, help="تعداد دانلود همزمان (پیش‌فرض ۶)")
    ap.add_argument("--no-espn", action="store_true", help="عدم استفاده از شاخص ESPN")
    args = ap.parse_args(argv)

    identities = json.loads(IDENTITIES.read_text(encoding="utf-8"))["teams"]
    mapping = json.loads(MAPPING.read_text(encoding="utf-8")).get("teams", {}) if MAPPING.exists() else {}
    only = {x.strip().upper() for x in args.only.split(",")} if args.only else None

    targets = [
        (canonical, ident["code"])
        for canonical, ident in identities.items()
        if not only or ident["code"] in only
    ]

    espn_index = {} if args.no_espn else _build_espn_logo_index()
    print(f"Targets: {len(targets)} clubs | ESPN logo index: {len(espn_index)} entries")

    results: list[tuple[str, str, str]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = {
            ex.submit(
                fetch_team,
                canonical,
                code,
                force=args.force,
                only_placeholders=args.only_placeholders,
                team_map_entry=mapping.get(canonical),
                espn_index=espn_index,
            ): (code, canonical)
            for canonical, code in targets
        }
        for fut in as_completed(futs):
            code, canonical = futs[fut]
            res = fut.result()
            results.append((code, canonical, res))
            print(f"  [{code}] {canonical:24s} -> {res}")

    results.sort(key=lambda r: r[0])
    ok = sum(1 for _, _, r in results if r.startswith(("ok", "skip")))
    print(f"\n──── خلاصه: {ok}/{len(results)} باشگاه دارای لوگوی واقعی ────")
    return 0


if __name__ == "__main__":
    sys.exit(main())
