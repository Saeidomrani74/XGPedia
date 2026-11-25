"""اسکریپت تست زنده و ممیزی عملی تمام APIهای فوتبال در XGPedia (اجرا روی سیستم کاربر).

نحوه اجرا:
    python scripts/audit_football_apis.py
    python scripts/audit_football_apis.py --json
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from typing import Any

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

ENDPOINTS: list[tuple[str, str, str]] = [
    ("FPL Official Bootstrap", "https://fantasy.premierleague.com/api/bootstrap-static/", "PL Standings / Scorers / Players"),
    ("worldcup26.ir Meta (IR)", "https://worldcup26.ir/get/soccer/meta", "rezarahiminia/livescoreFootball (489★)"),
    ("worldcup26.ir LaLiga Table", "https://worldcup26.ir/get/soccer/esp.1/standings?season=2026", "LaLiga Live Standings (No Key)"),
    ("OpenLigaDB BL1 Table 2026", "https://api.openligadb.de/getbltable/bl1/2026", "Bundesliga Live Standings (No Key)"),
    ("OpenLigaDB BL1 Scorers 2026", "https://api.openligadb.de/getgoalgetters/bl1/2026", "Bundesliga Live Top Scorers (No Key)"),
    ("OpenLigaDB BL1 Matchday", "https://api.openligadb.de/getmatchdata/bl1", "Bundesliga Live HT/FT/Goals/Penalties"),
    ("openfootball JSON (EN 24-25)", "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/en.1.json", "Multi-Season H2H Archive (CC0)"),
    ("oritzio 26/27 LaLiga DB", "https://raw.githubusercontent.com/oritzio/football-database/master/Spain_LaLiga.json", "2026/27 Club Catalog JSON"),
    ("TheSportsDB PL Past Events", "https://www.thesportsdb.com/api/v1/json/3/eventspastleague.php?id=4328", "PL Goal Minutes & HT Scores"),
    ("BBC Sport Football RSS", "https://feeds.bbci.co.uk/sport/football/rss.xml", "Live Quotes / Debates / Numbers"),
]


def probe_endpoint(name: str, url: str, role: str, timeout: float = 8.0) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json,application/xml,*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = getattr(resp, "status", 200)
            body = resp.read(200_000)
        ms = round((time.perf_counter() - t0) * 1000)
        size_kb = round(len(body) / 1024, 1)
        count_hint = ""
        try:
            j = json.loads(body.decode("utf-8", errors="replace"))
            if isinstance(j, list):
                count_hint = f"{len(j)} items"
            elif isinstance(j, dict):
                count_hint = f"keys={list(j.keys())[:4]}"
        except Exception:
            count_hint = "XML/Text"
        return {"name": name, "role": role, "ok": True, "status": code, "ms": ms, "size_kb": size_kb, "detail": count_hint}
    except Exception as e:
        ms = round((time.perf_counter() - t0) * 1000)
        return {"name": name, "role": role, "ok": False, "status": 0, "ms": ms, "size_kb": 0.0, "detail": f"{type(e).__name__}: {str(e)[:80]}"}


def main() -> int:
    as_json = "--json" in sys.argv
    results = [probe_endpoint(n, u, r) for n, u, r in ENDPOINTS]
    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    ok_cnt = sum(1 for r in results if r["ok"])
    print(f"\n=== XGPedia Live Football API Audit ({ok_cnt}/{len(results)} OK) ===\n")
    for r in results:
        mark = "OK  " if r["ok"] else "FAIL"
        print(f"[{mark}] {r['name']:<30} | {r['ms']:>4} ms | {r['size_kb']:>5.1f} KB | {r['detail']}")
    print("")
    return 0 if ok_cnt > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
