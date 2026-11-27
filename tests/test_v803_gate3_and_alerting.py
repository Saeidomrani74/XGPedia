"""تست‌های دروازهٔ ۳ (retry، جلوگیری از انتشار تکراری، کانال هشدار و جریان Git/PR) — v0.80.3."""
from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def test_v803_alert_digest_retries_on_transient_failure_and_succeeds():
    from src.xgpedia.core import alerting

    calls: list[tuple[str | int, str]] = []

    async def flaky_send(chat_id, text):
        calls.append((chat_id, text))
        if len(calls) < 3:
            raise RuntimeError("429 Too Many Requests (transient)")
        return {"ok": True, "message_id": 9901}

    with patch.object(alerting, "ALERT_TELEGRAM_CHAT_ID", "-100999888777"):
        res = asyncio.run(
            alerting.send_alert_digest_telegram(
                send_fn=flaky_send,
                max_retries=3,
                backoff_sec=0.0,
            )
        )
    assert res["sent"] is True
    assert res["attempts"] == 3
    assert res["chat_id"] == "-100999888777"
    assert len(calls) == 3


def test_v803_alert_target_falls_back_to_admin_ids():
    from src.xgpedia.core import alerting

    with patch.object(alerting, "ALERT_TELEGRAM_CHAT_ID", ""), patch.object(
        alerting, "ADMIN_TELEGRAM_IDS", frozenset({222, 111})
    ):
        assert alerting.resolve_alert_chat_id() == 111


def test_v803_duplicate_publish_is_blocked_in_telegram_publish():
    from src.xgpedia import db as db_mod
    from src.xgpedia.publishers import telegram_publish as tp

    sent_messages: list[dict] = []

    class _FakeTransport:
        async def send_message(self, chat_id, text, **kw):
            sent_messages.append({"chat_id": chat_id, "text": text})
            from types import SimpleNamespace; return SimpleNamespace(chat_id=chat_id, message_id=500 + len(sent_messages))

        async def send_photo(self, chat_id, photo, caption="", **kw):
            sent_messages.append({"chat_id": chat_id, "caption": caption})
            from types import SimpleNamespace; return SimpleNamespace(chat_id=chat_id, message_id=500 + len(sent_messages))

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "dup_guard.sqlite"
        with (
            patch.object(db_mod, "DATABASE_PATH", db_path),
            patch.object(tp, "ADMIN_TELEGRAM_IDS", frozenset({777})),
            patch.object(tp, "TELEGRAM_CHANNEL_ID", "@xgpedia_test"),
            patch.object(tp, "find_card_image", return_value=None),
        ):
            db_mod.init_db()
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            with db_mod.db() as conn:
                conn.execute(
                    "INSERT INTO fixtures (fixture_id, provider, competition, season, kickoff_utc, home_team, away_team, status, collected_at) "
                    "VALUES ('fdo:901', 'football-data.org', 'Premier League', '2026-27', ?, 'Arsenal', 'Chelsea', 'scheduled', ?)",
                    (now, now),
                )
                cur = conn.execute(
                    "INSERT INTO posts (fixture_id, post_type, target_platform, content_version, status, title, caption, created_at) "
                    "VALUES ('fdo:901', 'pre_match', 'telegram', 1, 'awaiting_approval', 'عنوان تست', 'کپشن تست', ?)",
                    (now,),
                )
                post_id = int(cur.lastrowid)

            tr = _FakeTransport()
            first = asyncio.run(tp.approve_and_publish(post_id, 777, tr))
            assert first["message_id"] == 501
            assert len(sent_messages) == 1

            # تلاش دوم برای انتشار مجدد همان پست باید مسدود شود و هیچ پیام تکراری ارسال نگردد
            blocked = False
            try:
                asyncio.run(tp.approve_and_publish(post_id, 777, tr))
            except Exception:
                blocked = True
            assert blocked is True, "Duplicate publish must be rejected"
            assert len(sent_messages) == 1, "No duplicate Telegram message may be sent"


def test_v803_gate3_7day_streak_detection():
    from src.xgpedia import db as db_mod
    from src.xgpedia.core import alerting

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "gate3.sqlite"
        with patch.object(db_mod, "DATABASE_PATH", db_path):
            db_mod.init_db()
            now = datetime.now(timezone.utc)
            with db_mod.db() as conn:
                conn.execute(
                    "INSERT INTO posts (post_id, fixture_id, post_type, target_platform, content_version, status, title, caption, created_at) "
                    "VALUES (1, 'fdo:1', 'pre_match', 'telegram', 1, 'published', 't', 'c', ?)",
                    (now.strftime("%Y-%m-%dT%H:%M:%SZ"),),
                )
                for d in range(7):
                    ts = (now - timedelta(days=d)).strftime("%Y-%m-%dT12:00:00Z")
                    conn.execute(
                        "INSERT INTO publishing_logs (post_id, platform_message_id, published_at, result) VALUES (1, 'msg_1', ?, 'ok')",
                        (ts,),
                    )
            health = alerting.collect_gate3_health(days=7)
            assert health["published_total"] == 7
            assert health["published_unique_days"] == 7
            assert health["gate3_7day_passed"] is True
            report = alerting.format_gate3_report_ascii(health)
            assert "PASSED (7/7 days clean)" in report


def test_v803_git_pr_workflow_and_scripts_present():
    pr_ci = ROOT / ".github" / "workflows" / "pr_ci.yml"
    pr_tpl = ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"
    ps_script = ROOT / "scripts" / "new_feature_branch.ps1"
    assert pr_ci.exists() and "pull_request:" in pr_ci.read_text(encoding="utf-8")
    assert "visual-qa" in pr_ci.read_text(encoding="utf-8")
    assert pr_tpl.exists()
    assert ps_script.exists()
