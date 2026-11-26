"""تست‌های نسخهٔ 0.66.0: استخراج تمام هفته‌های گذشتهٔ لیگ اروپا از تقویم ESPN + تکمیل خودکار ردیف دوم کارت پیش‌ازبازی."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.xgpedia.providers.espn_free import ESPNFreeProvider
from src.xgpedia.render.studio_engine import select_studio_modules


def test_espn_calendar_fetches_all_past_uel_matchdays() -> None:
    cal_resp = MagicMock(status_code=200)
    cal_resp.json.return_value = {
        "leagues": [
            {
                "calendar": [
                    "2026-09-17T07:00Z",
                    "2026-10-01T07:00Z",
                    "2026-11-05T07:00Z",
                    "2026-12-10T07:00Z",  # آینده — نباید خوانده شود
                ]
            }
        ]
    }

    def _mk_event(eid: str, day: str, home: str, away: str, hg: str, ag: str) -> dict:
        return {
            "id": eid,
            "date": f"{day}T19:00Z",
            "competitions": [
                {
                    "date": f"{day}T19:00Z",
                    "status": {"type": {"completed": True, "state": "post"}},
                    "competitors": [
                        {"homeAway": "home", "score": hg, "team": {"displayName": home}, "statistics": []},
                        {"homeAway": "away", "score": ag, "team": {"displayName": away}, "statistics": []},
                    ],
                }
            ],
        }

    by_date = {
        "20260917": {"events": [_mk_event("e1", "2026-09-17", "Ferencváros", "Celtic", "3", "1")]},
        "20261001": {"events": [_mk_event("e2", "2026-10-01", "NK Celje", "Omonia", "0", "3")]},
        "20261105": {"events": [_mk_event("e3", "2026-11-05", "Levski Sofia", "Jagiellonia Białystok", "1", "0")]},
    }

    def _fake_client_get(self, url: str, *args, **kwargs):
        r = MagicMock(status_code=200)
        d_param = (kwargs.get("params") or {}).get("dates", "")
        for d, payload in by_date.items():
            if f"dates={d}" in url or d_param == d:
                r.json.return_value = payload
                return r
        r.json.return_value = {"events": []}
        return r

    prov = ESPNFreeProvider()
    try:
        with (
            patch.object(prov._client, "get", return_value=cal_resp),
            patch("httpx.Client.get", new=_fake_client_get),
        ):
            rows = prov.fetch_competition_season_finished_matches(
                "uefa.europa",
                competition_name="UEFA Europa League",
                now_utc=datetime(2026, 11, 26, 10, 0, tzinfo=timezone.utc),
            )
    finally:
        prov.close()

    assert len(rows) == 3
    ids = {r["event_id"] for r in rows}
    assert ids == {"e1", "e2", "e3"}


def test_preview_smart_layout_fills_third_module_when_signals_missing() -> None:
    has = {
        "radar": True,
        "trend10": True,
        "signals": False,
        "wave": False,
        "keyduel": True,
        "stats": True,
        "poisson": True,
        "watchout": True,
    }
    mods = select_studio_modules("preview", has, fmt="4:5", layout="smart", header_mode="full")
    assert len(mods) == 3
    assert [m["id"] for m in mods[:2]] == ["radar", "trend10"]
    assert mods[2]["span"] == "full"
    assert mods[2]["id"] in ("keyduel", "stats", "poisson")
