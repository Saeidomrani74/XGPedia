"""تست‌های نسخهٔ 0.18.0 — دریافت زندهٔ سرمربی و ورزشگاه از football-data.org (بدون هاردکد)."""
from __future__ import annotations

from pathlib import Path

from src.xgpedia import db as db_mod
from src.xgpedia.providers.base import RawResponse
from src.xgpedia.sync import build_match_facts, sync_team_metadata


def test_live_coach_and_venue_from_football_data_org_never_hardcoded(tmp_path: Path, monkeypatch):
    db_file = tmp_path / "live_meta.db"
    monkeypatch.setattr(db_mod, "DATABASE_PATH", db_file)
    db_mod.init_db()

    # درج یک بازی پیش‌رو
    with db_mod.db() as conn:
        conn.execute(
            "INSERT INTO fixtures (fixture_id, provider, competition, season, kickoff_utc, home_team, away_team, status, raw_payload_hash, collected_at) "
            "VALUES ('fdo:999','football-data-org','Premier League','2026-27','2026-11-22T16:30:00Z','Liverpool','Manchester United','scheduled',NULL,'2026-11-22T08:00:00Z')"
        )

    # ۱) قبل از همگام‌سازی team_metadata، هیچ نام سرمربی هاردکد نباید نمایش داده شود!
    facts_before = build_match_facts("fdo:999", post_match=False)
    assert facts_before["home"]["sub"] is None
    assert facts_before["away"]["sub"] is None

    # ۲) همگام‌سازی زنده از پاسخ /v4/competitions/PL/teams
    raw = RawResponse.build(
        "football-data-org",
        "/competitions/PL/teams",
        {
            "teams": [
                {
                    "id": 64,
                    "name": "Liverpool FC",
                    "venue": "Anfield",
                    "coach": {"name": "Andoni Iraola"},
                },
                {
                    "id": 66,
                    "name": "Manchester United FC",
                    "venue": "Old Trafford",
                    "coach": {"name": "New Appointed Coach"},
                },
            ]
        },
        200,
    )
    res = sync_team_metadata(raw, season_start=2026)
    assert res["teams_saved"] == 2

    # ۳) پس از همگام‌سازی: سرمربی شناخته‌شده به فارسی ترجمه می‌شود و سرمربی جدید دقیقاً از API می‌آید!
    facts_after = build_match_facts("fdo:999", post_match=False)
    assert facts_after["home"]["sub"] == "آندونی ایرائولا"
    assert facts_after["away"]["sub"] is not None
    assert any("\u0600" <= ch <= "\u06FF" for ch in facts_after["away"]["sub"])
    assert facts_after["away"]["sub"] != "New Appointed Coach"
    assert facts_after["stadium"] == "ورزشگاه آنفیلد"
