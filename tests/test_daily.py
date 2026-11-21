"""تست‌های خط تولید روزانه (NEXT_STEPS مرحلهٔ ۳) — بدون شبکه/LLM/توکن.

plan_day و run_daily با DB موقت و گام‌های ساختگی آزموده می‌شوند؛ این‌ها قفل
می‌شوند: idempotency روزانه (پست موجود → SKIP نه LLM دوباره)، ایزولاسیون خطای
هر بازی، سقف limit، تحمل خطای sync و دستور بازیابی دستی بعد از شکست رندر/صف.
"""
from __future__ import annotations

import contextlib
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.xgpedia import daily as daily_mod
from src.xgpedia.daily import DailySteps, plan_day, run_daily, staleness_note
from src.xgpedia.db import SCHEMA

# ─── زیرساخت تست: DB موقت + گام‌های ساختگی ───


@pytest.fixture()
def daily_db(tmp_path, monkeypatch):
    """DB موقت: سه بازی فردا (یکی با پست موجود)، یکی پس‌فردا، یکی تمام‌شده."""
    conn = sqlite3.connect(tmp_path / "daily.sqlite")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    now = "2026-11-18T08:00:00Z"

    def add(fid, kickoff, home, away, status):
        conn.execute(
            "INSERT INTO fixtures (fixture_id, provider, competition, season, kickoff_utc,"
            " home_team, away_team, status, collected_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (fid, "fdo", "Premier League", "2026-27", kickoff, home, away, status, now),
        )

    add("fdo:1", "2026-11-19T15:00:00Z", "Arsenal", "Liverpool", "scheduled")
    add("fdo:2", "2026-11-19T17:30:00Z", "Man City", "Chelsea", "scheduled")
    add("fdo:3", "2026-11-19T20:00:00Z", "Aston Villa", "Newcastle", "scheduled")
    add("fdo:4", "2026-11-20T20:00:00Z", "Tottenham", "West Ham", "scheduled")  # روز بعد
    # تمام‌شده در همان روز + گرانولاریتی فقط-تاریخ (مثل CSV) — نباید انتخاب شود
    add("fdcouk:2026-11-19:Everton:Fulham", "2026-11-19", "Everton", "Fulham", "finished")
    # پست منتشرشده برای بازی ۳ — کلید idempotency روزانه
    conn.execute(
        "INSERT INTO posts (fixture_id, post_type, target_platform, content_version,"
        " status, created_at) VALUES ('fdo:3','preview','telegram',1,'published',?)",
        (now,),
    )
    conn.commit()

    @contextlib.contextmanager
    def fake_db():
        yield conn

    monkeypatch.setattr(daily_mod, "db", fake_db)
    # data_freshness در سازندهٔ staleness_note به DB واقعی وصل است — ساختگی
    monkeypatch.setattr(daily_mod, "data_freshness",
                        lambda: {"last_finished_match": "2026-11-17T20:00:00Z"})
    # در تست‌ها صف تأیید «پیکربندی‌شده» فرض می‌شود؛ تستِ پیکربندی‌نبودن جدا هست
    monkeypatch.setattr(daily_mod, "_telegram_configured", lambda: True)
    yield conn
    conn.close()


def fake_steps(calls: list, fails: set = frozenset()) -> DailySteps:
    """شش گام ساختگی — calls را به‌ترتیب ثبت می‌کند؛ fails = {(گام, موضوع)}.

    موضوع: facts/draft با fixture_id، render/submit با post_id (fdo:1→101 و …).
    """
    nxt = iter([101, 102, 103, 104])

    def maybe(step, subject):
        if (step, subject) in fails:
            raise RuntimeError(f"{step} boom for {subject}")

    def sync_results_fn():
        calls.append(("sync",))
        maybe("sync", "csv")
        return "csv ok"

    def sync_fixtures_fn():
        calls.append(("fixtures",))
        maybe("fixtures", "fdo")
        return "fdo ok"

    def facts_fn(fid, post_type):
        calls.append(("facts", fid))
        maybe("facts", fid)
        return {"fixture_id": fid, "post_type": post_type}

    def draft_fn(facts, post_type, platform):
        calls.append(("draft", facts["fixture_id"]))
        maybe("draft", facts["fixture_id"])
        return next(nxt)

    def render_fn(post_id, fmt):
        calls.append(("render", post_id, fmt))
        maybe("render", post_id)
        return Path(f"output/card_{post_id}.png")

    def submit_fn(post_id):
        calls.append(("submit", post_id))
        maybe("submit", post_id)

    return DailySteps(
        sync_results_fn=sync_results_fn, sync_fixtures_fn=sync_fixtures_fn,
        facts_fn=facts_fn, draft_fn=draft_fn, render_fn=render_fn, submit_fn=submit_fn,
    )


# ─── برنامهٔ روز (خالص) ───


def test_plan_day_filters_date_status_and_existing_post(daily_db):
    """فقط بازی‌های همان روزِ تمام‌نشدهٔ بی‌پست؛ دارای‌پست → skipped (idempotency)."""
    todo, skipped = plan_day(daily_db, "2026-11-19", limit=8)
    assert [f["fixture_id"] for f in todo] == ["fdo:1", "fdo:2"]  # ۳ پست دارد، ۴ فردا نیست،Everton تمام‌شده
    assert skipped == ["fdo:3"]


def test_plan_day_limit_caps_posts(daily_db):
    """limit روی بازی‌های بی‌پست اعمال می‌شود (سقف هزینهٔ LLM هر اجرا)."""
    todo, skipped = plan_day(daily_db, "2026-11-19", limit=1)
    assert [f["fixture_id"] for f in todo] == ["fdo:1"]
    assert skipped == ["fdo:3"]  # skipped همیشه کامل گزارش می‌شود


def test_staleness_note_thresholds(monkeypatch):
    """همان آستانهٔ ۴ روز cmd_status؛ خالی بودن DB هم WARN است."""
    monkeypatch.setattr(daily_mod, "data_freshness", lambda: {"last_finished_match": "-"})
    assert "WARN" in staleness_note()
    monkeypatch.setattr(daily_mod, "data_freshness",
                        lambda: {"last_finished_match": "2026-11-17T20:00:00Z"})
    assert "OK" in staleness_note(today=date(2026, 11, 18))
    assert "stale" in staleness_note(today=date(2026, 11, 25))


# ─── ارکستراتور ───


def test_run_daily_happy_path_order_and_submit(daily_db):
    """هر بازی: facts → draft → render → submit؛ بازی دارای پست رد می‌شود."""
    calls: list = []
    msgs: list = []
    res = run_daily(target_date="2026-11-19", steps=fake_steps(calls),
                    sync=False, log=msgs.append)
    assert res.created == [101, 102] and res.rendered == [101, 102]
    assert res.submitted == [101, 102]
    assert res.skipped_existing == ["fdo:3"]
    assert not res.failed and res.exit_code == 0
    assert res.fixtures_found == 3  # دو قابل‌پردازش + یکی دارای پست
    keys = [c[0] for c in calls]
    assert keys == ["facts", "draft", "render", "submit"] * 2  # ترتیب قفل شد
    assert any("SKIP - fdo:3" in m for m in msgs)


def test_run_daily_isolates_fixture_failure(daily_db):
    """شکست draft بازی دوم، بازی اول را نمی‌اندازد — exit ۱ نه کرش."""
    calls: list = []
    res = run_daily(target_date="2026-11-19", steps=fake_steps(calls, {("draft", "fdo:2")}),
                    sync=False, log=lambda m: None)
    assert res.created == [101] and res.submitted == [101]  # اولی کامل انجام شد
    assert len(res.failed) == 1 and res.failed[0].startswith("fdo:2:")
    assert res.exit_code == 1


def test_run_daily_render_failure_gives_manual_command(daily_db):
    """پست ساخته شده ولی رندر نیفتاده → دستور بازیابی دقیق در failed."""
    res = run_daily(target_date="2026-11-19",
                    steps=fake_steps([], {("render", 102)}), sync=False, log=lambda m: None)
    assert res.created == [101, 102] and res.rendered == [101]
    assert any("render-post --post-id 102" in m for m in res.failed)


def test_run_daily_submit_failure_gives_manual_command(daily_db):
    """شکست صف تأیید پست را از بین نمی‌برد → manual: publish --post-id."""
    res = run_daily(target_date="2026-11-19",
                    steps=fake_steps([], {("submit", 102)}), sync=False, log=lambda m: None)
    assert res.created == [101, 102] and res.rendered == [101, 102]
    assert res.submitted == [101]
    assert any("publish --post-id 102" in m for m in res.failed)
    assert res.exit_code == 1


def test_run_daily_sync_failure_is_tolerated(daily_db):
    """شبکه قطع → دو WARN، ادامه با DB موجود و ساخت پست‌ها."""
    res = run_daily(target_date="2026-11-19",
                    steps=fake_steps([], {("sync", "csv"), ("fixtures", "fdo")}),
                    sync=True, log=lambda m: None)
    assert res.sync_ok is False and res.fixtures_sync_ok is False
    assert res.created == [101, 102] and res.exit_code == 0  # خطای sync «failed» نیست


def test_run_daily_no_matches_that_day_is_ok(daily_db):
    """روز بدون بازی = موفقیت خاموش (cron نباید آلارم بدهد)."""
    res = run_daily(target_date="2026-12-25", steps=fake_steps([]), sync=False,
                    log=lambda m: None)
    assert res.exit_code == 0 and not res.created and res.fixtures_found == 0


def test_run_daily_no_submit_flag(daily_db):
    """--no-submit: رندر هست، صف تأیید نه (حالت بازبینی دستی)."""
    calls: list = []
    res = run_daily(target_date="2026-11-19", steps=fake_steps(calls),
                    submit=False, sync=False, log=lambda m: None)
    assert res.rendered == [101, 102] and not res.submitted
    assert "submit" not in [c[0] for c in calls]
    assert res.exit_code == 0


def test_run_daily_telegram_unconfigured_warns_not_fails(daily_db, monkeypatch):
    """توکن نیست → WARN و ادامه؛ رندرشده‌ها «شکست» حساب نمی‌شوند (exit ۰)."""
    monkeypatch.setattr(daily_mod, "_telegram_configured", lambda: False)
    calls: list = []
    msgs: list = []
    res = run_daily(target_date="2026-11-19", steps=fake_steps(calls),
                    submit=True, sync=False, log=msgs.append)
    assert res.created == [101, 102] and not res.submitted
    assert "submit" not in [c[0] for c in calls]
    assert res.exit_code == 0
    assert any("not configured" in m for m in msgs)
