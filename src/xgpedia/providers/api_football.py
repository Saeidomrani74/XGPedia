"""Ø¢Ø¯Ø§Ù¾ØªØ± API-Football â€” Ø¯Ø±Ø³ FBref: Ù‡Ø± provider ÛŒÚ© Ø¢Ø¯Ø§Ù¾ØªØ± Ù…Ø³ØªÙ‚Ù„ Ø¨Ø§ Ø®Ø±ÙˆØ¬ÛŒ schema Ø¯Ø§Ø®Ù„ÛŒ.

Ø¢Ø²Ù…ÙˆÙ† Ù¾ÙˆØ´Ø´ (Ø±ÙˆØ² Û± Ù‡ÙØªÙ‡Ù” Û³) Ù¾ÛŒØ´ Ø§Ø² Ù‡Ø± Ø§Ø³ØªÙØ§Ø¯Ù‡Ù” Ø¹Ù…Ù„ÛŒØ§ØªÛŒ Ø§Ø¬Ø±Ø§ Ø´ÙˆØ¯:
pytest tests/test_api_football.py -m live  (Ù†ÛŒØ§Ø²Ù…Ù†Ø¯ API_FOOTBALL_KEY)
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from src.xgpedia.providers.base import ProviderError, RateLimitBudget, RawResponse, with_backoff

BASE = os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io")
LEAGUE_ID_PL = 39  # Premier League


class ApiFootball:
    """Ø¢Ø¯Ø§Ù¾ØªØ± Ø­Ø¯Ø§Ù‚Ù„ÛŒ MVP â€” ÙÙ‚Ø· endpointÙ‡Ø§ÛŒÛŒ Ú©Ù‡ Ø®Ø· ØªÙˆÙ„ÛŒØ¯ ÙˆØ§Ù‚Ø¹Ø§Ù‹ Ù…ØµØ±Ù Ù…ÛŒâ€ŒÚ©Ù†Ø¯."""

    def __init__(self, api_key: str | None = None, budget: RateLimitBudget | None = None) -> None:
        self.api_key = api_key or os.environ["API_FOOTBALL_KEY"]
        self.budget = budget or RateLimitBudget()
        self._client = httpx.Client(
            base_url=BASE,
            headers={"x-apisports-key": self.api_key},
            timeout=15.0,
        )

    def _get(self, endpoint: str, params: dict[str, Any]) -> RawResponse:
        self.budget.spend(1, endpoint)

        def call() -> httpx.Response:
            r = self._client.get(endpoint, params=params)
            if r.status_code >= 500:
                raise ProviderError(f"{endpoint}: {r.status_code}")
            return r

        resp = with_backoff(call)
        if resp.status_code != 200:
            raise ProviderError(f"{endpoint}: HTTP {resp.status_code} â€” {resp.text[:200]}")
        body = resp.json()
        # API-Football Ø®Ø·Ø§Ù‡Ø§ Ø±Ø§ Ø¨Ø§ HTTP 200 Ùˆ results:0 Ø¨Ø±Ù…ÛŒâ€ŒÚ¯Ø±Ø¯Ø§Ù†Ø¯
        if body.get("errors"):
            raise ProviderError(f"{endpoint}: {body['errors']}")
        raw = RawResponse.build("api-football", endpoint, body, resp.status_code)
        raw.save()
        return raw

    # ---------- endpointÙ‡Ø§ÛŒ MVP ----------

    def fixtures_by_date(self, date_iso: str) -> RawResponse:
        """Ø¨Ø§Ø²ÛŒâ€ŒÙ‡Ø§ÛŒ ÛŒÚ© Ø±ÙˆØ²: params: date=YYYY-MM-DD, league, season."""
        y, m, _ = (int(part) for part in date_iso.split("-"))
        season = y if m >= 8 else y - 1
        return self._get("/fixtures", {"date": date_iso, "league": LEAGUE_ID_PL, "season": season})

    def fixture_statistics(self, fixture_id: int) -> RawResponse:
        """Ø¢Ù…Ø§Ø± Ù…Ø³Ø§Ø¨Ù‚Ù‡: Ø´ÙˆØªØŒ Ø´ÙˆØª Ø¯Ø± Ú†Ø§Ø±Ú†ÙˆØ¨ØŒ Ù…Ø§Ù„Ú©ÛŒØªØŒ Ú©Ø±Ù†Ø±ØŒ Ú©Ø§Ø±Øª Ùˆ Ø§Ú¯Ø± Ø¨Ø§Ø´Ø¯ expected_goals."""
        return self._get("/fixtures/statistics", {"fixture": fixture_id})

    def fixture_events(self, fixture_id: int) -> RawResponse:
        """Ø±ÙˆÛŒØ¯Ø§Ø¯Ù‡Ø§: Ú¯Ù„ØŒ Ú©Ø§Ø±ØªØŒ ØªØ¹ÙˆÛŒØ¶."""
        return self._get("/fixtures/events", {"fixture": fixture_id})

    def lineups(self, fixture_id: int) -> RawResponse:
        """ØªØ±Ú©ÛŒØ¨ â€” ÙÙ‚Ø· Ù¾Ø³ Ø§Ø² Ø§Ø¹Ù„Ø§Ù… Ø±Ø³Ù…ÛŒØ› Ø²Ù…Ø§Ù† Ø¯Ø±ÛŒØ§ÙØª Ø«Ø¨Øª Ø´ÙˆØ¯."""
        return self._get("/fixtures/lineups", {"fixture": fixture_id})

    def injuries(self, fixture_id: int) -> RawResponse:
        """Ù…ØµØ¯ÙˆÙ…ÛŒØª/Ù…Ø­Ø±ÙˆÙ…ÛŒØª â€” Ø¨Ø§ Ø§Ø·Ù„Ø§Ø¹ÛŒÙ‡Ù” Ø¨Ø§Ø´Ú¯Ø§Ù‡ ØªØ·Ø¨ÛŒÙ‚ Ø¯Ùˆâ€ŒÙ…Ù†Ø¨Ø¹ÛŒ Ø´ÙˆØ¯."""
        return self._get("/injuries", {"fixture": fixture_id})

    def close(self) -> None:
        self._client.close()
