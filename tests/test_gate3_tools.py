"""تست‌های ابزارهای دروازهٔ ۳ (NEXT_STEPS مرحلهٔ ۶) — بدون شبکه/توکن.

check_telegram با fetch ساختگی: هر خطای رایج روز صفر (توکن غلط، کانال پیدا‌نشده،
رباتِ غیرادمین، ادمینِ بدون /start) و حالت همه‌سبز. weekly_report با DB موقت:
شمارش وضعیت‌ها، خروج بازهٔ خارج، رأی قاعدهٔ توقف (≥۲ خطای مهم) و ذخیرهٔ فایل.
"""
from __future__ import annotations

import asyncio
import contextlib
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.xgpedia import reports as reports_mod
from src.xgpedia.db import SCHEMA
from src.xgpedia.publishers.telegram_check import check_telegram

TOK, CH, ADMINS = "123:abc", "-1001234567890", {111, 222}


class FakeFetch:
    """پاسخ‌های ساختگی تلگرام — کلید: (method, chat_id)؛ پیش‌فرض: ok."""

    def __init__(self, responses: dict | None = None):
        self.responses = responses or {}
        self.calls: list[tuple[str, dict]] = []

    async def __call__(self, method: str, params: dict) -> dict:
        self.calls.append((method, params))
        key = (method, params.get("chat_id"))
        if key in self.responses:
            return self.responses[key]
        return {"ok": True, "result": {"id": params.get("chat_id"), "type": "chat"}}


def run_check(fetch, **kw):
    return asyncio.run(check_telegram(
        fetch, token=kw.get("token", TOK), channel_id=kw.get("channel_id", CH),
        admin_ids=kw.get("admin_ids", ADMINS),
    ))


def test_check_all_green():
    """همه‌سبز: توکن، کانال، ادمین‌بودن ربات و دسترسی به هر دو ادمین."""
    fetch = FakeFetch({
        ("getMe", None): {"ok": True, "result": {"id": 42, "username": "xgpedia_bot"}},
        ("getChat", CH): {"ok": True, "result": {"id": -100123, "title": "XGPedia", "type": "channel"}},
        ("getChatMember", CH): {"ok": True, "result": {"status": "administrator"}},
    })
    ok, lines = run_check(fetch)
    assert ok
    assert "[OK]   token valid - bot @xgpedia_bot (id=42)" in lines
    assert any("channel: 'XGPedia'" in ln for ln in lines)
    assert any("administrator of the channel" in ln for ln in lines)
    assert any("admin 111 is reachable" in ln for ln in lines)
    assert "all green" in lines[-1]
    # هیچ متد ارسالی صدا زده نشده — فقط سه متد خواندن
    assert {m for m, _ in fetch.calls} == {"getMe", "getChat", "getChatMember"}


def test_check_missing_env_no_network():
    """env ناقص: سه FAIL و صفر تماس شبکه‌ای (fetch=None اصلاً لازم نیست)."""
    ok, lines = run_check(None, token="", channel_id="", admin_ids=frozenset())
    assert not ok
    assert any("TELEGRAM_BOT_TOKEN is empty" in ln for ln in lines)
    assert any("no network call was made" in ln for ln in lines)


def test_check_bad_token():
    fetch = FakeFetch({("getMe", None): {"ok": False, "description": "Unauthorized"}})
    ok, lines = run_check(fetch)
    assert not ok
    assert any("token rejected" in ln and "Unauthorized" in ln for ln in lines)


def test_check_channel_not_found():
    fetch = FakeFetch({
        ("getMe", None): {"ok": True, "result": {"id": 42, "username": "b"}},
        ("getChat", CH): {"ok": False, "description": "Bad Request: chat not found"},
    })
    ok, lines = run_check(fetch)
    assert not ok
    assert any("channel not found" in ln for ln in lines)


def test_check_bot_not_channel_admin():
    """ربات فقط member است → FAIL با راهنمای Add admin."""
    fetch = FakeFetch({
        ("getMe", None): {"ok": True, "result": {"id": 42, "username": "b"}},
        ("getChatMember", CH): {"ok": True, "result": {"status": "member"}},
    })
    ok, lines = run_check(fetch)
    assert not ok
    assert any("Administrators -> Add admin" in ln for ln in lines)


def test_check_admin_without_start_is_warn_not_fail():
    """یک ادمین /start نکرده → WARN (نه FAIL)؛ هیچ‌کدام → FAIL."""
    fetch = FakeFetch({
        ("getMe", None): {"ok": True, "result": {"id": 42, "username": "b"}},
        ("getChat", 111): {"ok": True, "result": {"id": 111, "type": "private"}},
        ("getChat", 222): {"ok": False, "description": "Bad Request: chat not found"},
    })
    ok, lines = run_check(fetch)
    assert ok  # یک ادمین می‌رسد → هشدار می‌ماند، جریان ممکن است
    assert any("admin 222 not reachable" in ln and "/start" in ln for ln in lines)

    fetch_none = FakeFetch({
        ("getMe", None): {"ok": True, "result": {"id": 42, "username": "b"}},
        ("getChat", 111): {"ok": False, "description": "chat not found"},
        ("getChat", 222): {"ok": False, "description": "chat not found"},
    })
    ok2, lines2 = run_check(fetch_none)
    assert not ok2
    assert any("no admin has started the bot" in ln for ln in lines2)


# ─── گزارش هفتگی ───

TODAY = "2026-11-21"  # شنبه — بازهٔ ۷روزه: 2026-11-15..2026-11-21


@pytest.fixture()
def report_db(tmp_path, monkeypatch):
    """DB موقت: ۴ پست در بازه (+۱ خارج بازه)، لاگ انتشار و تصمیم ادمین."""
    conn = sqlite3.connect(tmp_path / "report.sqlite")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)

    def add_post(pid, fixture, status, created):
        conn.execute(
            "INSERT INTO posts (post_id, fixture_id, post_type, target_platform,"
            " content_version, status, title, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (pid, fixture, "preview", "telegram", 1, status, f"post {pid}", created),
        )

    add_post(1, "f1", "published", f"{TODAY}T09:00:00+00:00")   # در بازه
    add_post(2, "f2", "published", "2026-11-19T09:00:00+00:00")  # در بازه
    add_post(3, "f3", "failed", "2026-11-18T09:00:00+00:00")     # در بازه
    add_post(4, "f4", "draft", "2026-11-17T09:00:00+00:00")      # در بازه
    add_post(6, "f6", "validated", "2026-11-16T09:00:00+00:00")  # در بازه — آمادهٔ ارسال
    add_post(5, "f5", "published", "2026-10-01T09:00:00+00:00")  # خارج بازه
    conn.execute(
        "INSERT INTO publishing_logs (post_id, platform_message_id, permalink, published_at, result)"
        " VALUES (1,'-100123:5','',?, 'ok')", (f"{TODAY}T10:00:00+00:00",),
    )
    conn.execute(
        "INSERT INTO publishing_logs (post_id, platform_message_id, permalink, published_at, result)"
        " VALUES (2,'-100123:6','',?, 'ok')", ("2026-11-19T10:00:00+00:00",),
    )
    conn.execute(
        "INSERT INTO moderation_logs (post_id, admin_user_id, action, created_at)"
        " VALUES (1, 111, 'approve', ?)", (f"{TODAY}T10:00:00+00:00",),
    )
    conn.execute(
        "INSERT INTO moderation_logs (post_id, admin_user_id, action, created_at)"
        " VALUES (3, 111, 'reject', ?)", ("2026-11-18T10:00:00+00:00",),
    )
    conn.commit()

    @contextlib.contextmanager
    def fake_db():
        yield conn

    monkeypatch.setattr(reports_mod, "db", fake_db)
    # data_freshness به DB واقعی وصل است — ساختگی (همان الگوی test_daily)
    monkeypatch.setattr(reports_mod, "data_freshness",
                        lambda: {"last_finished_match": "2026-11-20T22:00:00Z"})
    yield conn
    conn.close()


def test_weekly_report_counts_and_verdict_ok(report_db):
    """شمارش وضعیت‌ها در بازه + خروج پستِ خارج بازه + رأی سبز بدون خطا."""
    from datetime import date

    md = reports_mod.weekly_report(days=7, end=date(2026, 11, 21))
    assert f"# گزارش هفتگی XGPedia — 2026-11-15 تا {TODAY}" in md
    assert "| منتشرشده | 2 |" in md          # پست ۵ خارج بازه شمرده نمی‌شود
    assert "| آمادهٔ ارسال (validated) | 1 |" in md
    assert "| ردشده/ناتمام (failed) | 1 |" in md
    assert "| پیش‌نویس باقی‌مانده | 1 |" in md
    assert "| ارسال موفق (publishing_logs ok) | 2 |" in md
    assert "| تأیید / رد / ویرایش ادمین | 1 / 1 / 0 |" in md
    assert "بدون خطای مهم" in md
    assert "پست 1" in md and "-100123:5" in md  # آخرین پست منتشرشده


def test_weekly_report_stop_rule_two_errors(report_db):
    """قاعدهٔ توقف NEXT_STEPS مرحلهٔ ۶: ≥۲ خطای مهم در ۷ روز → رأی توقف."""
    from datetime import date

    report_db.execute(
        "INSERT INTO publishing_logs (post_id, platform_message_id, permalink, published_at, result)"
        " VALUES (3,'','',?,'error')", ("2026-11-16T10:00:00+00:00",),
    )
    report_db.execute(
        "INSERT INTO publishing_logs (post_id, platform_message_id, permalink, published_at, result)"
        " VALUES (4,'','',?,'error')", ("2026-11-15T10:00:00+00:00",),
    )
    report_db.commit()
    md = reports_mod.weekly_report(days=7, end=date(2026, 11, 21))
    assert "| **خطای مهم** | **2** |" in md
    assert "توقف" in md and "≥۲" in md


def test_weekly_report_saved_to_docs_weekly(report_db, tmp_path):
    """ذخیره در docs/weekly/week-<شروع>_<پایان>.md (معیار پایان Gate 3)."""
    from datetime import date

    path = reports_mod.save_weekly_report(tmp_path, days=7, end=date(2026, 11, 21))
    p = Path(path)
    assert p.exists() and p.parent.name == "weekly"
    assert p.name == "week-2026-11-15_2026-11-21.md"
    assert "گزارش هفتگی" in p.read_text(encoding="utf-8")
