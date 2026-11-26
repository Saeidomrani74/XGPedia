"""آداپتر football-data.org — منبع بازی‌های پیش‌رو، کیک‌آف و جدول برای ۶ لیگ معتبر اروپا.

پشتیبانی کامل از ۶ رقابت رایگان رسمی football-data.org v4:
  - `PL` (لیگ برتر انگلیس)، `CL` (لیگ قهرمانان اروپا)، `PD` (لالیگا اسپانیا)،
    `SA` (سری آ ایتالیا)، `BL1` (بوندس‌لیگا آلمان)، `FL1` (لیگ ۱ فرانسه).
  - پلن رایگان: ۱۰ درخواست بر دقیقه؛ توکن از ثبت‌نام رایگان.
  - هیچ endpoint برای xG ندارد — xG فقط از football-data.co.uk / Understat می‌آید.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from src.xgpedia.config import CURRENT_SEASON_START
from src.xgpedia.core.leagues import EUROPEAN_FDO_CODES
from src.xgpedia.providers.base import ProviderError, RateLimitBudget, RawResponse, with_backoff

PROVIDER = "football-data-org"
BASE = "https://api.football-data.org/v4"
PL_CODE = "PL"


class FootballDataOrg:
    """API رسمی v4 — fixtures پیش‌رو، نتایج، جدول و گلزنان برای همهٔ ۶ لیگ معتبر اروپا."""

    def __init__(
        self,
        token: str | None = None,
        budget: RateLimitBudget | None = None,
    ) -> None:
        self.token = token or os.environ.get("FOOTBALL_DATA_ORG_TOKEN", "")
        if not self.token:
            raise ProviderError(
                "FOOTBALL_DATA_ORG_TOKEN is not set - register free at football-data.org and fill .env"
            )
        self.budget = budget or RateLimitBudget(daily_limit=10_000)  # سقف مؤثر: ۱۰ req/min
        self._client = httpx.Client(
            base_url=BASE,
            headers={"X-Auth-Token": self.token},
            timeout=15.0,
        )

    def _get(self, endpoint: str, params: dict[str, Any]) -> RawResponse:
        self.budget.spend(1, endpoint)

        def call() -> httpx.Response:
            r = self._client.get(endpoint, params=params)
            if r.status_code >= 500:
                raise ProviderError(f"{endpoint}: {r.status_code}")
            if r.status_code == 429:  # rate limit — بازگشت برای backoff
                raise ProviderError(f"{endpoint}: 429 rate limit")
            return r

        resp = with_backoff(call)
        if resp.status_code != 200:
            hint = ""
            if resp.status_code == 404:
                hint = (
                    " - season may not have data yet; the API takes the season START year "
                    f"(currently {CURRENT_SEASON_START}). If it still fails early in a new season, "
                    "set XGPEDIA_SEASON_START to the previous year in .env"
                )
            raise ProviderError(f"{endpoint}: HTTP {resp.status_code} - {resp.text[:200]}{hint}")
        body = resp.json()
        if body.get("errorCode") or body.get("message") and resp.status_code != 200:
            raise ProviderError(f"{endpoint}: {body}")
        raw = RawResponse.build(PROVIDER, endpoint, body, resp.status_code)
        raw.save()
        return raw

    # ---------- endpointهای مصرفی چندلیگی ----------

    def upcoming_fixtures(
        self,
        days: int = 7,
        season_start: int = CURRENT_SEASON_START,
        competition: str = PL_CODE,
    ) -> RawResponse:
        """بازی‌های N روز آیندهٔ یک رقابت (پیش‌فرض: PL؛ پشتیبانی از PL/CL/PD/SA/BL1/FL1)."""
        from datetime import datetime, timedelta, timezone

        today = datetime.now(timezone.utc).date()
        comp = (competition or PL_CODE).strip().upper()
        return self._get(
            f"/competitions/{comp}/matches",
            {
                "dateFrom": today.isoformat(),
                "dateTo": (today + timedelta(days=days)).isoformat(),
                "season": season_start,
                "status": "SCHEDULED",
            },
        )

    def played_fixtures(
        self,
        days_back: int = 10,
        season_start: int = CURRENT_SEASON_START,
        competition: str = PL_CODE,
    ) -> RawResponse:
        """بازی‌های N روز گذشته (FINISHED) یک رقابت."""
        from datetime import datetime, timedelta, timezone

        today = datetime.now(timezone.utc).date()
        comp = (competition or PL_CODE).strip().upper()
        return self._get(
            f"/competitions/{comp}/matches",
            {
                "dateFrom": (today - timedelta(days=days_back)).isoformat(),
                "dateTo": today.isoformat(),
                "season": season_start,
                "status": "FINISHED",
            },
        )

    def standings(self, season_start: int = CURRENT_SEASON_START, competition: str = PL_CODE) -> RawResponse:
        """جدول لیگ (TOTAL/HOME/AWAY) — مبنای فرم و جایگاه."""
        comp = (competition or PL_CODE).strip().upper()
        return self._get(f"/competitions/{comp}/standings", {"season": season_start})

    def teams(self, season_start: int = CURRENT_SEASON_START, competition: str = PL_CODE) -> RawResponse:
        """اطلاعات زندهٔ تیم‌های فصل (ورزشگاه و سرمربی فعلی)."""
        comp = (competition or PL_CODE).strip().upper()
        return self._get(f"/competitions/{comp}/teams", {"season": season_start})

    def scorers(
        self,
        limit: int = 50,
        season_start: int = CURRENT_SEASON_START,
        competition: str = PL_CODE,
    ) -> RawResponse:
        """برترین گلزنان و پاسورهای فصل (رایگان) — منبع مطمئن ماژول مهرهٔ کلیدی."""
        comp = (competition or PL_CODE).strip().upper()
        return self._get(f"/competitions/{comp}/scorers", {"season": season_start, "limit": limit})

    def close(self) -> None:
        self._client.close()


__all__ = ["PROVIDER", "BASE", "PL_CODE", "EUROPEAN_FDO_CODES", "FootballDataOrg"]
