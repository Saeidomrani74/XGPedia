"""تست‌های نسخه v0.69.0:
- استخراج آمار واقعی xG/پنالتی/شوت از XHR JSON جدید Understat (`/getLeagueData/{lg}/{yr}`)
- نام فارسی باشگاه‌های حقوقی Football-Data.org و تیم‌های صعودکرده ۲۰۲۶–۲۷
- پردازش دقیق پنالتی‌های لیگ برتر (penalties=None در FDO -> 0 برای بازیکن گل‌زن)
- پرکردن مسیر واقعی ۸ هفته اخیر (weeks / pace) از FPL element-summary برای ۳ نفر اول
"""
from __future__ import annotations

import io
import json
from unittest.mock import patch

from src.xgpedia.providers import top_scorers_free as tsf


class _FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
        return False


def test_understat_xhr_get_league_data_extracts_xg_pen_and_shots():
    payload = {
        "players": [
            {
                "player_name": "Raphinha",
                "goals": "15",
                "npg": "12",
                "xG": "11.42",
                "xA": "5.10",
                "shots": "54",
                "time": "1080",
            },
            {
                "player_name": "Kylian Mbappé",
                "goals": "13",
                "npg": "10",
                "xG": "12.05",
                "xA": "2.30",
                "shots": "61",
                "time": "1170",
            },
        ]
    }
    captured = {}

    def _fake_urlopen(req, timeout=8.0):
        captured["url"] = req.full_url
        captured["xhr"] = req.headers.get("X-requested-with")
        return _FakeResp(json.dumps(payload).encode("utf-8"))

    with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
        res = tsf._fetch_understat_league_player_stats("La_liga", [2026])

    assert captured["url"] == "https://understat.com/getLeagueData/La_liga/2026"
    assert captured["xhr"] == "XMLHttpRequest"
    assert "raphinha" in res
    assert res["raphinha"]["xg"] == 11.42
    assert res["raphinha"]["pen"] == 3
    assert res["raphinha"]["shots"] == 54
    assert res["raphinha"]["mins"] == 1080
    assert "mbappe" in res
    assert res["mbappe"]["xg"] == 12.05
    assert res["mbappe"]["pen"] == 3


def test_fdo_legal_and_promoted_clubs_map_to_clean_persian_names():
    cases = [
        ("Genoa CFC", "GEN", "جنوا"),
        ("Stade Rennais FC 1901", "REN", "رن"),
        ("AJ Auxerre", "AJA", "اوسر"),
        ("Racing Club de Lens", "RCL", "لانس"),
        ("Paris FC", "PFC", "پاریس اف\u200cسی"),
        ("Frosinone Calcio", "FRO", "فروزینونه"),
        ("Real Racing Club de Santander", "SAN", "راسینگ سانتاندر"),
        ("Le Mans FC", "LMN", "لومان"),
    ]
    for raw_team, tla, expected_fa in cases:
        entry = tsf._build_league_scorer_entry(
            raw_name="Test Player",
            raw_team=raw_team,
            tla=tla,
            goals=6,
            pen=1,
            mins=540,
            pos_raw="Offence",
            understat_map={},
        )
        assert entry["club"] == expected_fa, f"{raw_team} -> got {entry['club']!r}, expected {expected_fa!r}"


def test_fd_pl_penalties_treats_null_as_zero_and_preserves_positive():
    payload = {
        "scorers": [
            {"player": {"name": "Erling Haaland"}, "goals": 9, "penalties": 2},
            {"player": {"name": "Alexander Isak"}, "goals": 7, "penalties": None},
        ]
    }
    with patch(
        "urllib.request.urlopen",
        return_value=_FakeResp(json.dumps(payload).encode("utf-8")),
    ):
        res = tsf._fetch_fd_pl_penalties("dummy_token")

    assert res["erling haaland"]["pen"] == 2
    assert res["haaland"]["pen"] == 2
    assert res["alexander isak"]["pen"] == 0
    assert res["isak"]["pen"] == 0


def test_hydrate_top_scorers_item_populates_8_week_fpl_trajectory():
    item = {
        "id": "epl_live_2026",
        "is_preset": False,
        "players": [
            {"name": "هالند", "fpl_id": 101, "goals": 9},
            {"name": "ایساک", "fpl_id": 202, "goals": 7},
            {"name": "جکسون", "fpl_id": 303, "goals": 6},
        ],
    }

    fake_summaries = {
        "101": {
            "history": [
                {"round": 1, "goals_scored": 2},
                {"round": 2, "goals_scored": 1},
                {"round": 3, "goals_scored": 0},
                {"round": 4, "goals_scored": 2},
                {"round": 5, "goals_scored": 1},
                {"round": 6, "goals_scored": 0},
                {"round": 7, "goals_scored": 1},
                {"round": 8, "goals_scored": 1},
                {"round": 9, "goals_scored": 1},
            ]
        },
        "202": {
            "history": [
                {"round": 1, "goals_scored": 1},
                {"round": 2, "goals_scored": 0},
                {"round": 3, "goals_scored": 1},
                {"round": 4, "goals_scored": 1},
                {"round": 5, "goals_scored": 1},
                {"round": 6, "goals_scored": 1},
                {"round": 7, "goals_scored": 0},
                {"round": 8, "goals_scored": 1},
                {"round": 9, "goals_scored": 1},
            ]
        },
        "303": {
            "history": [
                {"round": 2, "goals_scored": 1},
                {"round": 3, "goals_scored": 1},
                {"round": 5, "goals_scored": 2},
                {"round": 7, "goals_scored": 1},
                {"round": 9, "goals_scored": 1},
            ]
        },
    }

    def _fake_get_json(url, timeout=6.0):
        for fid, data in fake_summaries.items():
            if f"/{fid}/" in url:
                return data
        return None

    with patch.object(tsf, "_http_get_json", side_effect=_fake_get_json):
        hydrated = tsf.hydrate_top_scorers_item(item)

    assert hydrated["_hydrated"] is True
    assert hydrated["weeks"] == [f"هفته {r}" for r in range(2, 10)]
    assert hydrated["players"][0]["pace"] == [3, 3, 5, 6, 6, 7, 8, 9]
    assert hydrated["players"][1]["pace"] == [1, 2, 3, 4, 5, 5, 6, 7]
    assert hydrated["players"][2]["pace"] == [1, 2, 2, 4, 4, 5, 5, 6]
