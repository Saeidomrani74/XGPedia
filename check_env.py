"""بررسی محیط اجرا — روی ویندوز و لینوکس، قبل از شروع کار روزانه.

اجرا:  python check_env.py
بررسی می‌کند: نسخهٔ پایتون، بسته‌ها، دسترسی منابع، توکن‌ها، فایل‌های config.

نکتهٔ خروجی: همهٔ پیام‌های ترمینال عمداً انگلیسی/ASCII است — کنسول ویندوز
متن راست‌به‌چپ را درست نمایش نمی‌دهد (فارسی جدا و برعکس دیده می‌شود).
"""
from __future__ import annotations

import importlib.util
import os
import platform
import sys
import time
from datetime import date, timedelta
from pathlib import Path

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if not stream.isatty():
            try:
                stream.reconfigure(encoding="utf-8")
            except (AttributeError, OSError):
                pass

OK, WARN, FAIL = "[OK]", "[WARN]", "[FAIL]"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "", warn_only: bool = False) -> None:
    status = OK if ok else (WARN if warn_only else FAIL)
    results.append((status, name, detail))


def check_url(name: str, url: str, headers: dict[str, str] | None = None,
              tries: int = 3, timeout: float = 20.0, min_len: int = 1000,
              warn_only: bool = False) -> None:
    """GET با تلاش مجدد — timeout/handshake گذرا را فرصت می‌دهد."""
    import httpx

    last = ""
    for attempt in range(1, tries + 1):
        try:
            r = httpx.get(url, headers=headers or {}, follow_redirects=True, timeout=timeout)
            if r.status_code == 200 and len(r.text) >= min_len:
                check(name, True)
                return
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = str(e)[:70]
        if attempt < tries:
            time.sleep(2)
    check(name, False,
          f"{last} (after {tries} attempt(s)) - retry later or use a VPN if this host is blocked",
          warn_only=warn_only)


def main() -> int:
    print(f"XGPedia v8 environment check - {platform.system()} Python {sys.version.split()[0]}")
    print("-" * 64)
    root = Path(__file__).resolve().parent

    # 1) python
    check("Python >= 3.12", sys.version_info >= (3, 12),
          f"found {sys.version_info.major}.{sys.version_info.minor}")

    # 2) packages
    for pkg in ("httpx", "pydantic", "dotenv"):
        check(f"package {pkg}", importlib.util.find_spec(pkg) is not None)

    # 2b) render extras (optional at this stage - needed from week 5 / render layer)
    render_pkgs = ("jinja2", "playwright", "jdatetime")
    missing_render = [p for p in render_pkgs if importlib.util.find_spec(p) is None]
    check("render extras (jinja2+playwright+jdatetime)", not missing_render,
          "pip install -e \".[render]\" then: playwright install chromium"
          if missing_render else "", warn_only=True)
    if not missing_render:
        check("brand fonts (brand/fonts/Vazirmatn-*.woff2)",
              (root / "brand" / "fonts" / "Vazirmatn-Regular.woff2").exists(),
              "re-extract the package - woff2 files must sit in brand/fonts/", warn_only=True)

    # 3) config files
    for f in ("config/thresholds.json", "config/glossary_fa.json", "config/team_mapping.json"):
        check(f"config file {f}", (root / f).exists())

    # 4) .env + football-data.org token (optional - sync-results works without it)
    env_file = root / ".env"
    has_env = env_file.exists()
    check(".env file", has_env, "(copy .env.example to .env)" if not has_env else "", warn_only=True)
    token = os.environ.get("FOOTBALL_DATA_ORG_TOKEN", "")
    if has_env and not token:
        # lightweight read from .env itself (no dotenv dependency needed here)
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith("FOOTBALL_DATA_ORG_TOKEN=") and line.split("=", 1)[1].strip():
                token = "set"
    check("FOOTBALL_DATA_ORG_TOKEN (upcoming fixtures)", bool(token),
          "register free at https://www.football-data.org" if not token else "", warn_only=True)

    # LLM keys (optional at this stage - needed from week 4 / editorial layer)
    llm_keys = [k for k in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL") if os.environ.get(k)]
    check("LLM keys (editorial layer, week 4+)", len(llm_keys) == 3 or len(llm_keys) == 0,
          f"only {len(llm_keys)}/3 set - fill all three in .env or leave all empty"
          if 0 < len(llm_keys) < 3 else "", warn_only=True)

    # فصل جاری: «سال شروع» فصل (قبل از اوت = فصل قبل) — قابل override از env
    _season = os.environ.get("XGPEDIA_SEASON_START")
    season_start = int(_season) if _season else (date.today().year if date.today().month >= 8 else date.today().year - 1)
    season_code = f"{season_start % 100:02d}{(season_start + 1) % 100:02d}"

    # 5) network access to both primary sources (retries absorb transient SSL timeouts)
    # همان فصلِ واقعیِ کاربرد fixtures — با پارامتر season تا token validity جدا از وجود داده آزموده شود
    check_url("football-data.co.uk (xG + results CSV)",
              f"https://www.football-data.co.uk/mmz4281/{season_code}/E0.csv", tries=3)

    if token and token != "set":
        d1 = (date.today() - timedelta(days=14)).isoformat()
        d2 = date.today().isoformat()
        check_url("football-data.org API (token + current season data)",
                  f"https://api.football-data.org/v4/competitions/PL/matches?season={season_start}&dateFrom={d1}&dateTo={d2}",
                  headers={"X-Auth-Token": token}, tries=1, min_len=0, warn_only=True)

    # 6) database
    db_file = root / "data" / "dev.sqlite"
    check("database (run.py init)", db_file.exists(),
          "run: python run.py init" if not db_file.exists() else "")

    # output
    fails = 0
    for status, name, detail in results:
        line = f"  {status:<6} {name}"
        if detail:
            line += f" - {detail}"
        print(line)
        if status == FAIL:
            fails += 1

    print("-" * 64)
    if fails:
        print(f"[FAIL] {fails} item(s) failed - fix them before continuing.")
        return 1
    print("Environment is ready. Next step: python run.py sync-results")
    return 0


if __name__ == "__main__":
    sys.exit(main())
