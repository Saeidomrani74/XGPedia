"""پرووایدر رایگان The Odds API برای ضرایب زندهٔ بازار لیگ برتر (+EV / signals).

پلن رایگان رسمی (بدون کارت بانکی، ۵۰۰ درخواست در ماه):
  https://the-odds-api.com  →  کلید را در `.env` با نام `ODDS_API_KEY=...` بگذارید.
با هر ۱ درخواست، ضرایب زندهٔ 1X2 و Over/Under 2.5 همهٔ بازی‌های پیش‌رو لیگ برتر دریافت می‌شود.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from src.xgpedia.config import canonical_team_name

PROVIDER = "the-odds-api"
BASE_URL = "https://api.the-odds-api.com/v4/sports/soccer_epl/odds"


def parse_odds_api_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """استخراج میانگین ضرایب اعشاری واقعی (1X2 و Over 2.5) از پاسخ JSON سرویس The Odds API."""
    out: list[dict[str, Any]] = []
    for ev in events or []:
        h_raw = str(ev.get("home_team") or "").strip()
        a_raw = str(ev.get("away_team") or "").strip()
        commence = str(ev.get("commence_time") or "")[:10]
        if not (h_raw and a_raw and commence):
            continue
        h_canon = canonical_team_name(h_raw)
        a_canon = canonical_team_name(a_raw)

        h_odds, d_odds, a_odds, o25_odds = [], [], [], []
        for bm in ev.get("bookmakers") or []:
            for mk in bm.get("markets") or []:
                mkey = mk.get("key")
                outcomes = mk.get("outcomes") or []
                if mkey == "h2h":
                    for o in outcomes:
                        nm = str(o.get("name") or "").strip()
                        pr = o.get("price")
                        if not isinstance(pr, (int, float)) or pr <= 1.0:
                            continue
                        if nm == h_raw or canonical_team_name(nm) == h_canon:
                            h_odds.append(float(pr))
                        elif nm == a_raw or canonical_team_name(nm) == a_canon:
                            a_odds.append(float(pr))
                        elif nm.lower() == "draw":
                            d_odds.append(float(pr))
                elif mkey == "totals":
                    for o in outcomes:
                        if str(o.get("name") or "").lower() == "over" and o.get("point") in (2.5, "2.5"):
                            pr = o.get("price")
                            if isinstance(pr, (int, float)) and pr > 1.0:
                                o25_odds.append(float(pr))

        if not (h_odds or d_odds or a_odds or o25_odds):
            continue
        avg = lambda arr: round(sum(arr) / len(arr), 2) if arr else None
        out.append({
            "home_team": h_canon,
            "away_team": a_canon,
            "match_date": commence,
            "home_odds": avg(h_odds),
            "draw_odds": avg(d_odds),
            "away_odds": avg(a_odds),
            "over25_odds": avg(o25_odds),
            "btts_odds": None,
        })
    return out


class TheOddsAPIProvider:
    """دریافت ضرایب زندهٔ لیگ برتر از The Odds API (در صورت تنظیم ODDS_API_KEY در .env)."""

    def __init__(self, api_key: str | None = None, timeout: float = 15.0) -> None:
        self.api_key = (api_key or os.environ.get("ODDS_API_KEY") or "").strip()
        self._client = httpx.Client(timeout=timeout, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    def fetch_epl_odds(self) -> list[dict[str, Any]]:
        if not self.api_key:
            return []
        r = self._client.get(
            BASE_URL,
            params={
                "apiKey": self.api_key,
                "regions": "uk,eu",
                "markets": "h2h,totals",
                "oddsFormat": "decimal",
            },
        )
        r.raise_for_status()
        return parse_odds_api_events(r.json())
