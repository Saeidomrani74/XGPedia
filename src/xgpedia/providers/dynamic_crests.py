"""دریافت و کش پویا و خودکار لوگوی رسمی (PNG/SVG) برای همهٔ باشگاه‌های فوتبال اروپا و جهان.

منابع رسمی بدون کلید API:
  1. ثبت خودکار `team["logo"]` از ESPN Scoreboard/Summary و `homeTeam["crest"]` از football-data.org در `data/team_logos.json`.
  2. کشف خودکار لیست کامل باشگاه‌های فصل جاری لیگ قهرمانان اروپا (`uefa.champions/teams`) و سایر لیگ‌ها از ESPN.
  3. ذخیرهٔ دائمی فایل PNG در `output/.badge_cache/dyn_<slug>.png` برای رندر فوق‌سریع و آفلاین کارت‌ها.
"""
from __future__ import annotations

import base64
import json
import re
import threading
import urllib.request
from pathlib import Path
from typing import Any

from src.xgpedia.config import ROOT, canonical_team_name

LOGO_REGISTRY_FILE = ROOT / "data" / "team_logos.json"
BADGE_CACHE_DIR = ROOT / "output" / ".badge_cache"
_LOCK = threading.RLock()
_UCL_DIRECTORY_FETCHED = False


def _slug_key(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")
    return s or "club"


def _load_registry() -> dict[str, str]:
    with _LOCK:
        if LOGO_REGISTRY_FILE.exists():
            try:
                data = json.loads(LOGO_REGISTRY_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return {str(k): str(v) for k, v in data.items() if k and v}
            except Exception:
                pass
    return {}


def _save_registry(reg: dict[str, str]) -> None:
    with _LOCK:
        LOGO_REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = LOGO_REGISTRY_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(reg, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(LOGO_REGISTRY_FILE)


def register_team_logo(team_name: str, logo_url: str) -> None:
    """ثبت URL رسمی لوگوی یک باشگاه در کش محلی `data/team_logos.json`."""
    url = str(logo_url or "").strip()
    raw = str(team_name or "").strip()
    if not (raw and url and url.startswith("http")):
        return
    canon = canonical_team_name(raw)
    with _LOCK:
        reg = _load_registry()
        changed = False
        for k in (canon, raw, _slug_key(canon), _slug_key(raw)):
            if k and reg.get(k) != url:
                reg[k] = url
                changed = True
        if changed:
            _save_registry(reg)


def _lookup_registered_url(team_name: str) -> str | None:
    reg = _load_registry()
    if not reg:
        return None
    canon = canonical_team_name(team_name)
    for k in (canon, team_name, _slug_key(canon), _slug_key(team_name)):
        if k and k in reg:
            return reg[k]
    low = _slug_key(canon)
    for k, v in reg.items():
        ks = _slug_key(k)
        if ks and low and (low == ks or (len(low) >= 4 and (low in ks or ks in low))):
            return v
    return None


def sync_ucl_team_logos_from_espn(*, timeout: float = 8.0) -> int:
    """دریافت یک‌بارهٔ لوگوی رسمی تمام باشگاه‌های حاضر در چمپیونزلیگ و لیگ‌های اروپایی از ESPN."""
    global _UCL_DIRECTORY_FETCHED
    _UCL_DIRECTORY_FETCHED = True
    added = 0
    endpoints = (
        "https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.champions/teams?limit=100",
        "https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.europa/teams?limit=100",
    )
    reg = _load_registry()
    changed = False
    for ep in endpoints:
        try:
            req = urllib.request.Request(ep, headers={"User-Agent": "Mozilla/5.0 XGPedia/0.53"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data: dict[str, Any] = json.loads(resp.read().decode("utf-8", errors="ignore"))
            sports = data.get("sports") or []
            for sp in sports:
                for lg in sp.get("leagues") or []:
                    for entry in lg.get("teams") or []:
                        tm = entry.get("team") if isinstance(entry, dict) else None
                        if not isinstance(tm, dict):
                            continue
                        logos = tm.get("logos") or []
                        href = ""
                        if logos and isinstance(logos[0], dict):
                            href = str(logos[0].get("href") or "").strip()
                        if not href:
                            continue
                        names = {
                            str(tm.get("displayName") or "").strip(),
                            str(tm.get("shortDisplayName") or "").strip(),
                            str(tm.get("name") or "").strip(),
                        }
                        for nm in names:
                            if not nm:
                                continue
                            cn = canonical_team_name(nm)
                            for k in (cn, nm, _slug_key(cn), _slug_key(nm)):
                                if k and reg.get(k) != href:
                                    reg[k] = href
                                    changed = True
                        added += 1
        except Exception:
            continue
    if changed:
        _save_registry(reg)
    return added


def fetch_and_cache_crest_data_uri(
    team_name: str,
    *,
    fetch_network: bool = True,
    timeout: float = 8.0,
) -> str | None:
    """برگرداندن `data:image/png|svg+xml;base64,...` رسمی برای هر باشگاه اروپایی با کش دیسک دائمی."""
    if not (team_name or "").strip():
        return None
    canon = canonical_team_name(team_name)
    slug = _slug_key(canon)

    # ۱) بررسی کش دیسک محلی
    for ext, mime in (("png", "image/png"), ("svg", "image/svg+xml")):
        cf = BADGE_CACHE_DIR / f"dyn_{slug}.{ext}"
        if cf.exists() and cf.stat().st_size > 200:
            b64 = base64.b64encode(cf.read_bytes()).decode("ascii")
            return f"data:{mime};base64,{b64}"

    # ۲) یافتن URL لوگو از رجیستری محلی (یا دریافت لیست چمپیونزلیگ از ESPN)
    url = _lookup_registered_url(canon)
    if not url and fetch_network and not _UCL_DIRECTORY_FETCHED:
        sync_ucl_team_logos_from_espn(timeout=timeout)
        url = _lookup_registered_url(canon)
    if not url or not fetch_network:
        return None

    # ۳) دانلود و ذخیره دائمی در کش دیسک
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 XGPedia/0.53"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        if len(raw) < 200:
            return None
        is_svg = raw.lstrip()[:5].startswith(b"<svg") or url.lower().endswith(".svg")
        ext = "svg" if is_svg else "png"
        mime = "image/svg+xml" if is_svg else "image/png"
        BADGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (BADGE_CACHE_DIR / f"dyn_{slug}.{ext}").write_bytes(raw)
        b64 = base64.b64encode(raw).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception:
        return None
