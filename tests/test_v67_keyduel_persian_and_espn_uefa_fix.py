"""تست‌های نسخهٔ 0.67.0: فارسی‌سازی خودکار نام مهره‌های کلیدی در کارت پیش‌ازبازی + دریافت تاریخچه لیگ اروپا از تقویم dict/str ESPN."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.xgpedia.providers.espn_free import ESPNFreeProvider
from src.xgpedia.render.card_kit.modules.keyduel import render_keyduel


def test_keyduel_translates_english_player_names_to_persian() -> None:
    payload = {
        "match": {
            "home": {
                "color": "#EF4444",
                "kp": {"name": "Santiago Hezze", "pos": "هافبک", "s1": "1 گل", "s2": "مهره کلیدی تیم"},
            },
            "away": {
                "color": "#3B82F6",
                "kp": {"name": "Alphadjo Cisse", "pos": "مهاجم / گلزن", "s1": "6 گل", "s2": "12 بازی"},
            },
        }
    }
    html = render_keyduel(payload, span="full", fmt="4:5")
    assert "Santiago Hezze" not in html
    assert "Alphadjo Cisse" not in html
    assert any("\u0600" <= ch <= "\u06FF" for ch in html)


def test_espn_calendar_handles_dict_entries_and_no_limit_param() -> None:
    cal_resp = MagicMock(status_code=200)
    cal_resp.json.return_value = {
        "leagues": [
            {
                "calendar": [
                    {"label": "MD1", "startDate": "2026-09-17T07:00Z"},
                    {"label": "MD4", "entries": [{"startDate": "2026-11-05T07:00Z"}]},
                ]
            }
        ]
    }
    seen_params: list[dict] = []

    def _fake_get(self, url: str, *args, **kwargs):
        params = kwargs.get("params") or {}
        seen_params.append(params)
        r = MagicMock(status_code=200)
        if params.get("dates") == "20261105":
            r.json.return_value = {
                "events": [
                    {
                        "id": "uel_99",
                        "date": "2026-11-05T19:00Z",
                        "competitions": [
                            {
                                "date": "2026-11-05T19:00Z",
                                "status": {"type": {"completed": True, "state": "post"}},
                                "competitors": [
                                    {"homeAway": "home", "score": "1", "team": {"displayName": "Levski Sofia"}, "statistics": []},
                                    {"homeAway": "away", "score": "0", "team": {"displayName": "Jagiellonia Białystok"}, "statistics": []},
                                ],
                            }
                        ],
                    }
                ]
            }
        else:
            r.json.return_value = {"events": []}
        return r

    prov = ESPNFreeProvider()
    try:
        with (
            patch.object(prov._client, "get", return_value=cal_resp),
            patch("httpx.Client.get", new=_fake_get),
        ):
            rows = prov.fetch_competition_season_finished_matches(
                "uefa.europa",
                competition_name="UEFA Europa League",
                now_utc=datetime(2026, 11, 26, 10, 0, tzinfo=timezone.utc),
            )
    finally:
        prov.close()

    assert len(rows) == 1
    assert rows[0]["event_id"] == "uel_99"
    assert all("limit" not in p for p in seen_params)
