"""آداپتر API-Football — درس FBref: هر provider یک آداپتر مستقل با خروجی schema داخلی.

آزمون پوشش (روز ۱ هفتهٔ ۳) پیش از هر استفادهٔ عملیاتی اجرا شود:
pytest tests/test_api_football.py -m live  (نیازمند API_FOOTBALL_KEY)
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from src.xgpedia.providers.base import ProviderError, RateLimitBudget, RawResponse, with_backoff

BASE = os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io")
LEAGUE_ID_PL = 39  # Premier League


class ApiFootball:
    """آداپتر حداقلی MVP — فقط endpointهایی که خط تولید واقعاً مصرف می‌کند."""

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
            raise ProviderError(f"{endpoint}: HTTP {resp.status_code} - {resp.text[:200]}")
        body = resp.json()
        # API-Football خطاها را با HTTP 200 و results:0 برمی‌گرداند
        if body.get("errors"):
            raise ProviderError(f"{endpoint}: {body['errors']}")
        raw = RawResponse.build("api-football", endpoint, body, resp.status_code)
        raw.save()
        return raw

    # ---------- endpointهای MVP ----------

    def fixtures_by_date(self, date_iso: str) -> RawResponse:
        """بازی‌های یک روز: params: date=YYYY-MM-DD, league, season."""
        return self._get("/fixtures", {"date": date_iso, "league": LEAGUE_ID_PL})

    def fixture_statistics(self, fixture_id: int) -> RawResponse:
        """آمار مسابقه: شوت، شوت در چارچوب، مالکیت، کرنر، کارت و اگر باشد expected_goals."""
        return self._get("/fixtures/statistics", {"fixture": fixture_id})

    def fixture_events(self, fixture_id: int) -> RawResponse:
        """رویدادها: گل، کارت، تعویض."""
        return self._get("/fixtures/events", {"fixture": fixture_id})

    def lineups(self, fixture_id: int) -> RawResponse:
        """ترکیب — فقط پس از اعلام رسمی؛ زمان دریافت ثبت شود."""
        return self._get("/fixtures/lineups", {"fixture": fixture_id})

    def injuries(self, fixture_id: int) -> RawResponse:
        """مصدومیت/محرومیت — با اطلاعیهٔ باشگاه تطبیق دو‌منبعی شود."""
        return self._get("/injuries", {"fixture": fixture_id})

    def close(self) -> None:
        self._client.close()
