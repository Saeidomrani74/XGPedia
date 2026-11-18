"""تست‌های لایهٔ انتشار تلگرام (NEXT_STEPS مرحلهٔ ۲) — بدون توکن و بدون شبکه.

منطق (کپشن/فلو/idempotency/لاگ‌ها) با FakeTransport و DB موقت آزموده می‌شود؛
بدون نیاز به pytest-asyncio — هر تست با asyncio.run اجرا می‌شود.
ماژول aiogram فقط برای تست دودی importorskip می‌شود.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.xgpedia.db import SCHEMA
from src.xgpedia.publishers import telegram_publish as tp

# ─── زیرساخت تست: DB موقت + transport ساختگی ───

@pytest.fixture()
def pub_db(tmp_path, monkeypatch):
    """DB موقت با schema کامل + یک پست نمونه؛ db() ماژول به آن وصل می‌شود."""
    conn = sqlite3.connect(tmp_path / "pub.sqlite")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    draft = {
        "status": "ok",
        "title": "نبرد صدرنشینان <b>در</b> امارات",
        "bullets": ["بولت ۱", "بولت ۲"],
        "caption": "پیش‌بازی لیگ برتر <script>alert(1)</script>",
        "source_note": "football-data-co-uk · 2026-11-15",
        "uncertainties": [],
    }
    conn.execute(
        "INSERT INTO posts (fixture_id, post_type, target_platform, content_version, status,"
        " title, caption, draft_json, fact_json, created_at)"
        " VALUES ('fdcouk:x:Arsenal:Liverpool','preview','telegram',1,'validated',"
        " ?, ?, ?, '{}', '2026-11-15T00:00:00Z')",
        ("نبرد صدرنشینان <b>در</b> امارات", "پیش‌بینی لیگ برتر <script>alert(1)</script>",
         json.dumps(draft, ensure_ascii=False)),
    )
    conn.commit()

    @contextlib.contextmanager
    def fake_db():
        yield conn

    monkeypatch.setattr(tp, "db", fake_db)
    # ادمین‌های ساختگی — is_admin باید در sandbox (env خالی) هم درست کار کند
    monkeypatch.setattr(tp, "ADMIN_TELEGRAM_IDS", frozenset(ADMINS))
    # کارت رندرشدهٔ ساختگی — find_card_image باید آن را پیدا کند
    out = tmp_path / "output"
    out.mkdir()
    (out / "post_1_v1_preview_1080x1350.png").write_bytes(b"png")
    monkeypatch.setattr(tp, "ROOT", tmp_path)
    yield conn
    conn.close()


class FakeTransport:
    """ثبت دقیقاً همان دو متد قرارداد TelegramTransport — هیچ تماسی با شبکه."""

    def __init__(self):
        self.sent: list[dict] = []

    async def send_photo(self, chat_id, photo, caption, reply_markup=None):
        self.sent.append({"chat_id": chat_id, "photo": photo, "caption": caption,
                          "reply_markup": reply_markup})
        return tp.SentMessage(chat_id, 1000 + len(self.sent))

    async def edit_text(self, chat_id, message_id, text):
        self.sent.append({"edit": (chat_id, message_id, text)})


ADMIN = 111
ADMINS = {ADMIN, 222}


def _post(conn) -> dict:
    return dict(conn.execute("SELECT * FROM posts WHERE post_id=1").fetchone())


def run(coro):
    return asyncio.run(coro)


# ─── کپشن ایمن ───

def test_caption_escapes_llm_html(pub_db):
    """متن LLM هرگز HTML خام نیست — تگ‌های تزریقی escape می‌شوند، ساختار خودمان می‌ماند."""
    cap = tp.build_caption(_post(pub_db))
    assert cap.startswith("<b>") and "نبرد صدرنشینان" in cap
    assert "<script>" not in cap and "&lt;script&gt;" in cap
    assert "&lt;b&gt;در&lt;/b&gt;" in cap  # تگ داخل تیتر LLM خنثی شده
    assert "#پیش_بازی" in cap  # هشتگ نوع پست
    assert "منبع:" in cap


# ─── فلو تأیید ───

def test_submit_sends_to_admins_with_buttons(pub_db):
    """submit → کارت+کپشن برای همهٔ ادمین‌ها با دکمهٔ تأیید → awaiting_approval."""
    t = FakeTransport()
    run(tp.submit_for_approval(1, t, ADMINS))
    assert len(t.sent) == 2 and all(s["chat_id"] in ADMINS for s in t.sent)
    kb = t.sent[0]["reply_markup"]["inline_keyboard"][0]
    assert {"approve:1", "reject:1", "edit:1"} == {b["callback_data"] for b in kb}
    assert "نیازمند تأیید" in t.sent[0]["caption"]
    assert _post(pub_db)["status"] == "awaiting_approval"


def test_approve_publishes_to_channel_and_logs(pub_db, monkeypatch):
    """تأیید ادمین → ارسال به کانال → published + publishing_logs + moderation_logs."""
    monkeypatch.setattr(tp, "TELEGRAM_CHANNEL_ID", "-100123")
    t = FakeTransport()
    run(tp.submit_for_approval(1, t, ADMINS))
    result = run(tp.approve_and_publish(1, ADMIN, t))
    assert result["chat_id"] == -100123
    # ارسال سوم = کانال؛ بدون دکمه و با کپشن انتشار (نه بازبینی)
    assert t.sent[-1]["chat_id"] == -100123 and t.sent[-1]["reply_markup"] is None
    assert "#پیش_بازی" in t.sent[-1]["caption"]
    assert _post(pub_db)["status"] == "published"
    logs = [dict(r) for r in pub_db.execute("SELECT * FROM publishing_logs")]
    assert len(logs) == 1 and logs[0]["result"] == "ok"
    assert logs[0]["platform_message_id"] == "-100123:1003"
    mods = [dict(r) for r in pub_db.execute("SELECT * FROM moderation_logs")]
    assert [m["action"] for m in mods] == ["approve"] and mods[0]["admin_user_id"] == ADMIN


def test_publish_is_idempotent(pub_db, monkeypatch):
    """اجرای دوبارهٔ همان پست → پست تکراری نمی‌رود (معیار پایان NEXT_STEPS ۲)."""
    monkeypatch.setattr(tp, "TELEGRAM_CHANNEL_ID", "-100123")
    t = FakeTransport()
    run(tp.submit_for_approval(1, t, ADMINS))
    run(tp.approve_and_publish(1, ADMIN, t))
    with pytest.raises(ValueError, match="idempotency"):
        run(tp.approve_and_publish(1, ADMIN, t))
    with pytest.raises(ValueError, match="idempotency"):
        run(tp.submit_for_approval(1, t, ADMINS))
    assert len([s for s in t.sent if s.get("chat_id") == -100123]) == 1  # فقط یک بار کانال


def test_reject_and_back_to_draft(pub_db):
    t = FakeTransport()
    run(tp.submit_for_approval(1, t, ADMINS))
    run(tp.reject_post(1, ADMIN, reason="weak"))
    assert _post(pub_db)["status"] == "failed"
    run(tp.back_to_draft(1, ADMIN, action="edit"))
    assert _post(pub_db)["status"] == "draft"
    mods = [r["action"] for r in pub_db.execute("SELECT action FROM moderation_logs")]
    assert mods == ["reject:weak", "edit"]


# ─── قواعد دسترسی و خطاها ───

def test_non_admin_cannot_decide(pub_db, monkeypatch):
    monkeypatch.setattr(tp, "is_admin", lambda uid: uid in ADMINS)
    t = FakeTransport()
    run(tp.submit_for_approval(1, t, ADMINS))
    with pytest.raises(PermissionError):
        run(tp.approve_and_publish(1, 999, t))
    with pytest.raises(PermissionError):
        run(tp.reject_post(1, 999))


def test_missing_card_and_post_errors(pub_db):
    t = FakeTransport()
    with pytest.raises(LookupError):
        run(tp.submit_for_approval(99, t, ADMINS))
    # کارت رندرنشده — رندر بعدی لازم است
    (tp.ROOT / "output" / "post_1_v1_preview_1080x1350.png").unlink()
    with pytest.raises(FileNotFoundError, match="render-post"):
        run(tp.submit_for_approval(1, t, ADMINS))


def test_empty_admins_rejected(pub_db):
    with pytest.raises(ValueError, match="ADMIN_TELEGRAM_IDS"):
        run(tp.submit_for_approval(1, FakeTransport(), set()))


def test_find_card_prefers_latest_render(pub_db):
    """چند فرمت رندرشده → آخرین رندر (mtime) انتخاب می‌شود."""
    (tp.ROOT / "output" / "post_1_v1_preview_1080x1920.png").write_bytes(b"newer")
    import os

    os.utime(tp.ROOT / "output" / "post_1_v1_preview_1080x1920.png", (2e9, 2e9))
    assert tp.find_card_image(1, 1).name == "post_1_v1_preview_1080x1920.png"


def test_submit_survives_one_broken_admin_chat(pub_db):
    """یک چت خراب (مثلاً شناسهٔ ربات در ADMIN_TELEGRAM_IDS) کل submit را نمی‌اندازد؛
    بقیهٔ ادمین‌ها پیام می‌گیرند و وضعیت awaiting_approval می‌شود."""
    class HalfBrokenTransport(FakeTransport):
        async def send_photo(self, chat_id, photo, caption, reply_markup=None):
            if chat_id == 222:  # مثلاً chat not found
                raise RuntimeError("chat not found")
            return await super().send_photo(chat_id, photo, caption, reply_markup)

    t = HalfBrokenTransport()
    run(tp.submit_for_approval(1, t, ADMINS))
    assert [s["chat_id"] for s in t.sent] == [ADMIN]
    assert _post(pub_db)["status"] == "awaiting_approval"
    # همهٔ ادمین‌ها خراب → خطای واضح، وضعیت دست‌نخورده
    class AllBroken(FakeTransport):
        async def send_photo(self, chat_id, photo, caption, reply_markup=None):
            raise RuntimeError("chat not found")

    with pytest.raises(ValueError, match="ADMIN_TELEGRAM_IDS"):
        run(tp.submit_for_approval(1, AllBroken(), ADMINS))


def test_bot_module_smoke():
    """ماژول aiogram ایمپورت می‌شود و transport ساخته می‌شود (بدون اجرای polling)."""
    pytest.importorskip("aiogram", reason="publish extras not installed")
    from aiogram import Bot

    from src.xgpedia.publishers.telegram_bot import AiogramTransport, make_transport

    assert isinstance(make_transport(Bot("1:test")), AiogramTransport)


def test_transport_uploads_local_file_not_url():
    """رگرسیون باگ ویندوز: مسیر محلی (C:\\…) رشته‌ای به تلگرام نرود —
    «Wrong port number in the URL» می‌دهد؛ باید FSInputFile آپلود شود."""
    pytest.importorskip("aiogram", reason="publish extras not installed")
    from aiogram.types import FSInputFile

    from src.xgpedia.publishers.telegram_bot import AiogramTransport

    captured = {}

    class _Msg:
        class chat:
            id = 42

        message_id = 7

    class FakeBot:
        async def send_photo(self, chat_id, photo, caption=None, parse_mode=None, reply_markup=None):
            captured["photo"] = photo
            return _Msg()

    t = AiogramTransport(FakeBot())
    # مسیر محلی → آپلود واقعی با FSInputFile (خودِ فایل لازم نیست وجود داشته باشد)
    asyncio.run(t.send_photo(1, r"C:\Users\saeid\StudioProjects\XGPedia\output\post_1.png", "cap"))
    assert isinstance(captured["photo"], FSInputFile)
    assert str(captured["photo"].path).endswith("post_1.png")
    # URL واقعی → همان رشته می‌ماند (تلگرام خودش می‌گیرد)
    asyncio.run(t.send_photo(1, "https://example.com/card.png", "cap"))
    assert captured["photo"] == "https://example.com/card.png"
