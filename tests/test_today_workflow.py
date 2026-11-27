"""آزمون‌های خودکارسازی بازی‌های امروز، زمان‌بندی ۲۴ ساعته، گزارش‌دهی خطا و سبک فارسی روان."""
from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.xgpedia import db as db_mod
from src.xgpedia import today_workflow as tw
from src.xgpedia.editorial.llm_provider import DraftOutput
from src.xgpedia.editorial.validate import validate
from src.xgpedia.normalization.models import Last5, MatchFacts, SourceInfo, StatValue, TeamSide
from src.xgpedia.publishers import telegram_publish as tp


class FakeTransport:
    def __init__(self, fail_with: Exception | None = None) -> None:
        self.sent: list[dict] = []
        self.fail_with = fail_with

    async def send_photo(self, chat_id, photo, caption, reply_markup=None):
        if self.fail_with:
            raise self.fail_with
        self.sent.append({"chat_id": chat_id, "photo": photo, "caption": caption})
        return tp.SentMessage(chat_id=12345, message_id=len(self.sent) + 100)

    async def edit_text(self, chat_id, message_id, text):
        pass


class FakeGoodLLM:
    def generate(self, system_prompt, match, **_kw):
        return DraftOutput(
            status="ok",
            title="نبرد حساس آرسنال و لیورپول",
            bullets=[
                "آرسنال در آخرین بازی خود ۳ امتیاز گرفته است.",
                "میانگین امید گل آرسنال 1.53 و لیورپول 1.4 ثبت شده است.",
            ],
            caption="آرسنال و لیورپول با فرم نزدیک و امید گل 1.53 در برابر 1.4 به مصاف هم می‌روند.",
            source_note="",
            uncertainties=[],
        )


class FakeBadStyleLLM:
    def generate(self, system_prompt, match, **_kw):
        return DraftOutput(
            status="ok",
            title="آرسنال × لیورپول",
            bullets=["فرم اخیر (n=5): ۱۳ امتیاز."],
            caption="آمار امید گل (n=9) برابر 1.53 است.",
            source_note="",
            uncertainties=[],
        )


def _setup_temp_db(tmp_path: Path, monkeypatch) -> Path:
    db_file = tmp_path / "test.sqlite"
    monkeypatch.setattr(db_mod, "DATABASE_PATH", db_file)
    db_mod.init_db()
    return db_file


def _seed_today_fixtures(conn: sqlite3.Connection) -> None:
    # فرض: زمان فعلی 2026-11-21 10:00 UTC (= 13:30 تهران)
    # بازی ۱: امروز شروع‌نشده (16:30 UTC = 20:00 تهران) با دیتای کامل
    # بازی ۲: امروز قبلاً شروع شده (08:00 UTC = 11:30 تهران) → نباید در لیست بیاید
    # بازی ۳: امروز شروع‌نشده (18:00 UTC = 21:30 تهران) بدون دیتای آماری → ineligible با دلیل روشن
    # بازی ۴: فردا (2026-11-22 15:00 UTC) → نباید در لیست امروز بیاید
    fixtures = [
        ("fdo:1001", "football-data-org", "Premier League", "2026-27", "2026-11-21T16:30:00Z", "Arsenal", "Liverpool", "scheduled"),
        ("fdo:1002", "football-data-org", "Premier League", "2026-27", "2026-11-21T08:00:00Z", "Chelsea", "Everton", "scheduled"),
        ("fdo:1003", "football-data-org", "Premier League", "2026-27", "2026-11-21T18:00:00Z", "Fulham", "Brentford", "scheduled"),
        ("fdo:1004", "football-data-org", "Premier League", "2026-27", "2026-11-22T15:00:00Z", "Arsenal", "Chelsea", "scheduled"),
        # بازی‌های تمام‌شدهٔ قبلی برای تولید xG/فرم آرسنال و لیورپول
        ("fdcouk:2026-11-01:Arsenal:Everton", "football-data-co-uk", "Premier League", "2026-27", "2026-11-01", "Arsenal", "Everton", "finished"),
        ("fdcouk:2026-11-08:Liverpool:Everton", "football-data-co-uk", "Premier League", "2026-27", "2026-11-08", "Liverpool", "Everton", "finished"),
    ]
    for f in fixtures:
        conn.execute(
            "INSERT INTO fixtures (fixture_id, provider, competition, season, kickoff_utc, home_team, away_team, status, raw_payload_hash, collected_at) VALUES (?,?,?,?,?,?,?,?,NULL,'2026-11-21T09:00:00Z')", f
        )
    stats = [
        ("fdcouk:2026-11-01:Arsenal:Everton", "Arsenal", "expected_goals", 1.53),
        ("fdcouk:2026-11-01:Arsenal:Everton", "Arsenal", "goals", 2.0),
        ("fdcouk:2026-11-01:Arsenal:Everton", "Everton", "expected_goals", 0.71),
        ("fdcouk:2026-11-01:Arsenal:Everton", "Everton", "goals", 0.0),
        ("fdcouk:2026-11-08:Liverpool:Everton", "Liverpool", "expected_goals", 1.40),
        ("fdcouk:2026-11-08:Liverpool:Everton", "Liverpool", "goals", 2.0),
        ("fdcouk:2026-11-08:Liverpool:Everton", "Everton", "expected_goals", 0.82),
        ("fdcouk:2026-11-08:Liverpool:Everton", "Everton", "goals", 1.0),
    ]
    for fid, team, metric, val in stats:
        conn.execute(
            "INSERT INTO fixture_statistics (fixture_id, team, metric, value, n, provider, collected_at) VALUES (?,?,?,?,NULL,'football-data-co-uk','2026-11-21T09:00:00Z')",
            (fid, team, metric, val),
        )


# ─── ۱) دروازهٔ سبک فارسی روان (ممنوعیت (n=10)) ───

def test_validator_rejects_ugly_sample_size_notation():
    match = MatchFacts(
        fixture_id="fdo:1",
        competition={"name": "Premier League", "season": "2026-27"},
        kickoff_utc="2026-11-21T16:30:00Z",
        source=SourceInfo(provider="football-data-co-uk", collected_at="2026-11-21T09:00:00Z"),
        home=TeamSide(
            name_fa="آرسنال", name_en="Arsenal",
            last5=Last5(n=5, points=13, goals_for=9, goals_against=3),
            xg_for_avg=StatValue(value=1.53, n=10, provider="football-data-co-uk"),
        ),
        away=TeamSide(
            name_fa="لیورپول", name_en="Liverpool",
            last5=Last5(n=5, points=11, goals_for=8, goals_against=4),
            xg_for_avg=StatValue(value=1.40, n=10, provider="football-data-co-uk"),
        ),
    )
    bad = DraftOutput(
        status="ok",
        title="آرسنال برابر لیورپول",
        bullets=["میانگین امید گل (n=10): آرسنال 1.53 و لیورپول 1.4."],
        caption="آمار فرم (n=5) دو تیم بسیار نزدیک است.",
        source_note="src",
        uncertainties=[],
    )
    rep_bad = validate(bad, match, set())
    assert not rep_bad.passed
    assert any("[style]" in f for f in rep_bad.failures)

    good = DraftOutput(
        status="ok",
        title="آرسنال برابر لیورپول",
        bullets=["در ۱۰ بازی اخیر میانگین امید گل آرسنال 1.53 و لیورپول 1.4 بوده است."],
        caption="در ۵ بازی اخیر آرسنال ۱۳ امتیاز و لیورپول ۱۱ امتیاز به دست آورده‌اند.",
        source_note="src",
        uncertainties=[],
    )
    rep_good = validate(good, match, set())
    assert rep_good.passed, rep_good.failures


# ─── ۲) فیلتر بازی‌های شروع‌نشدهٔ امروز و تشخیص قابلیت تولید کارت ───

def test_list_today_matches_filters_unstarted_and_checks_eligibility(tmp_path, monkeypatch):
    _setup_temp_db(tmp_path, monkeypatch)
    with db_mod.db() as conn:
        _seed_today_fixtures(conn)

    now = datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc)  # 13:30 تهران
    matches = tw.list_today_matches(now_utc=now)
    fids = [m.fixture_id for m in matches]
    assert fids == ["fdo:1001", "fdo:1003"]  # شروع‌شده (1002) و فردا (1004) حذف شدند

    m1, m3 = matches
    assert m1.eligible is True
    assert m1.kickoff_tehran == "20:00"
    assert m3.eligible is False
    assert "دادهٔ آماری کافی" in m3.ineligible_reason


def test_sync_today_matches_reports_exact_errors_without_crashing(tmp_path, monkeypatch):
    _setup_temp_db(tmp_path, monkeypatch)
    with db_mod.db() as conn:
        _seed_today_fixtures(conn)

    now = datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc)
    rep = tw.sync_today_matches(
        now_utc=now,
        sync_results_fn=lambda: "100 بازی به‌روز شد",
        sync_fixtures_fn=lambda: (_ for _ in ()).throw(RuntimeError("HTTP 403 invalid token")),
    )
    assert rep.sync_results_ok is True
    assert rep.sync_fixtures_ok is False
    assert any("FOOTBALL_DATA_ORG_TOKEN" in e for e in rep.errors)
    # با وجود خطای API، بازی‌های موجود در DB همچنان برگردانده می‌شوند
    assert len(rep.eligible_matches) == 1


# ─── ۳) تولید پست کامل + گزارش‌دهی دقیق خطاها ───

def test_generate_match_post_success_and_error_diagnostics(tmp_path, monkeypatch):
    _setup_temp_db(tmp_path, monkeypatch)
    with db_mod.db() as conn:
        _seed_today_fixtures(conn)

    def fake_render(draft, facts, out_dir, post_id, version, **_kw):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        h = out_dir / f"post_{post_id}_v{version}_preview_1080x1350.html"
        p = out_dir / f"post_{post_id}_v{version}_preview_1080x1350.png"
        c = out_dir / f"post_{post_id}_v{version}_caption.txt"
        h.write_text("<html/>", encoding="utf-8")
        p.write_bytes(b"PNGDATA")
        c.write_text("کپشن کامل\n\n#پیش_بازی", encoding="utf-8")
        return h, p, c

    # مسیر موفق
    res = tw.generate_match_post(
        "fdo:1001", out_dir=tmp_path, llm_provider=FakeGoodLLM(), render_fn=fake_render
    )
    assert res.ok is True
    assert res.post_id is not None
    assert res.image_path.exists()

    # مسیر خطای اعتبارسنجی (مدل n=5 نوشته و بعد از ۲ تلاش رد می‌شود)
    res_bad = tw.generate_match_post(
        "fdo:1001", out_dir=tmp_path, llm_provider=FakeBadStyleLLM(), render_fn=fake_render
    )
    assert res_bad.ok is False
    assert res_bad.failed_stage == "editorial"
    assert "اعتبارسنجی" in res_bad.error_title
    assert "[style]" in res_bad.error_detail


# ─── ۴) زمان‌بندی ۲۴ ساعته تهران (09:35) و انتشار خودکار ───

def test_parse_today_tehran_time_24h_and_persian_digits():
    now = datetime(2026, 11, 21, 5, 30, tzinfo=timezone.utc)  # 09:00 تهران
    utc_iso, hhmm = tw.parse_today_tehran_time("09:35", now_utc=now)
    assert hhmm == "09:35"
    assert utc_iso == "2026-11-21T06:05:00Z"

    utc_iso_fa, hhmm_fa = tw.parse_today_tehran_time("۲۱:۴۵", now_utc=now)
    assert hhmm_fa == "21:45"
    assert utc_iso_fa == "2026-11-21T18:15:00Z"

    with pytest.raises(ValueError, match="گذشته"):
        tw.parse_today_tehran_time("08:50", now_utc=now)

    with pytest.raises(ValueError, match="نامعتبر"):
        tw.parse_today_tehran_time("25:99", now_utc=now)


def test_schedule_and_auto_publish_due_post(tmp_path, monkeypatch):
    _setup_temp_db(tmp_path, monkeypatch)
    monkeypatch.setattr(tp, "ADMIN_TELEGRAM_IDS", frozenset({777}))
    monkeypatch.setattr(tp, "ROOT", tmp_path)
    with db_mod.db() as conn:
        _seed_today_fixtures(conn)

    out_dir = tmp_path / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    def fake_render(draft, facts, out_dir, post_id, version, **_kw):
        h = Path(out_dir) / f"post_{post_id}_v{version}_preview_1080x1350.html"
        p = Path(out_dir) / f"post_{post_id}_v{version}_preview_1080x1350.png"
        c = Path(out_dir) / f"post_{post_id}_v{version}_caption.txt"
        h.write_text("<html/>", encoding="utf-8")
        p.write_bytes(b"PNGDATA")
        c.write_text("کپشن", encoding="utf-8")
        return h, p, c

    gen = tw.generate_match_post(
        "fdo:1001", out_dir=out_dir, llm_provider=FakeGoodLLM(), render_fn=fake_render
    )
    assert gen.ok

    now_before = datetime(2026, 11, 21, 5, 30, tzinfo=timezone.utc)  # 09:00 تهران
    sched = tw.schedule_post_publish(
        gen.post_id, "09:35", admin_user_id=777, now_utc=now_before, out_dir=out_dir
    )
    assert sched["scheduled_time_tehran"] == "09:35"
    assert len(tw.list_pending_schedules()) == 1

    # پیش از رسیدن ساعت 09:35 هیچ پستی منتشر نمی‌شود
    transport = FakeTransport()
    notifications: list[tuple[int, str]] = []

    async def fake_notify(uid, text):
        notifications.append((uid, text))

    out_early = asyncio.run(
        tw.run_due_scheduled_publishes(
            transport, channel_id="@xgpedia_channel", now_utc=now_before, notify_fn=fake_notify
        )
    )
    assert out_early == []
    assert len(transport.sent) == 0

    # پس از رسیدن ساعت 09:35 (06:05 UTC) خودکار منتشر می‌شود و به ادمین اطلاع می‌دهد
    now_due = datetime(2026, 11, 21, 6, 5, 30, tzinfo=timezone.utc)
    out_due = asyncio.run(
        tw.run_due_scheduled_publishes(
            transport, channel_id="@xgpedia_channel", now_utc=now_due, notify_fn=fake_notify
        )
    )
    assert len(out_due) == 1 and out_due[0]["ok"] is True
    assert transport.sent[0]["chat_id"] == "@xgpedia_channel"
    assert len(notifications) == 1 and "09:35" in notifications[0][1]
    assert tw.list_pending_schedules() == []


def test_raw_fdo_team_names_match_csv_stats(tmp_path, monkeypatch):
    """نام‌های خام football-data.org (مثل Liverpool FC / Hull City AFC) باید دقیق به آمار CSV وصل شوند."""
    from src.xgpedia.config import canonical_team_name, team_identity, team_name_fa

    assert canonical_team_name("Liverpool FC", 64) == "Liverpool"
    assert canonical_team_name("Manchester United FC", 66) == "Manchester United"
    assert canonical_team_name("Brighton & Hove Albion FC", 397) == "Brighton"
    assert canonical_team_name("Hull City AFC", 395) == "Hull City"
    assert canonical_team_name("AFC Bournemouth", 354) == "Bournemouth"
    assert canonical_team_name("Tottenham Hotspur FC", 73) == "Tottenham"
    assert canonical_team_name("Newcastle United FC", 67) == "Newcastle United"
    assert team_name_fa("Hull City AFC") == "هال سیتی"
    assert team_name_fa("Brighton & Hove Albion FC") == "برایتون"
    assert team_name_fa("Liverpool FC") == "لیورپول"
    assert team_name_fa("Manchester United FC") == "منچستریونایتد"
    assert team_identity("Hull") is not None and team_identity("Hull")["code"] == "HUL"

    _setup_temp_db(tmp_path, monkeypatch)
    with db_mod.db() as conn:
        _seed_today_fixtures(conn)
        conn.execute(
            "INSERT INTO fixtures (fixture_id, provider, competition, season, kickoff_utc, home_team, away_team, status, raw_payload_hash, collected_at) VALUES (?, 'football-data-org', 'Premier League', '2026-27', ?, ?, ?, 'scheduled', NULL, '2026-11-21T09:00:00Z')",
            ("fdo:2001", "2026-11-21T19:00:00Z", "Arsenal FC", "Liverpool FC"),
        )
    now = datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc)
    matches = {m.fixture_id: m for m in tw.list_today_matches(now_utc=now)}
    assert matches["fdo:2001"].eligible is True
    assert matches["fdo:2001"].home_fa == "آرسنال"
    assert matches["fdo:2001"].away_fa == "لیورپول"
