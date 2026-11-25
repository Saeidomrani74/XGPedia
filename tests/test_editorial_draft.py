"""آزمون‌های لایهٔ تحریریه — تولید پیش‌نویس با FakeLLM + دروازه‌ها + ذخیره در posts.

اجرا:  python -m pytest tests/ -v
پوشش:
  - مسیر خوش‌خیم: یک پاسخ سالم → validated در تلاش اول
  - مسیر retry: پاسخ بد → feedback validator → پاسخ سالم → validated در تلاش دوم
  - رد نهایی: دو پاسخ بد → RejectedDraft
  - DraftOutput.from_json: فنس ```json، کلید ناشناخته، status نامعتبر
  - build_source_note: provider/زمان/hash از کد، نه مدل
  - save_draft: نسخه‌بندی idempotent (content_version = max+1)
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from src.xgpedia.editorial.draft import (
    RejectedDraft,
    build_source_note,
    generate_draft,
    save_draft,
)
from src.xgpedia.editorial.llm_provider import DraftOutput
from src.xgpedia.editorial.prompt import SYSTEM_PROMPT
from src.xgpedia.normalization.models import (
    DataQuality,
    Last5,
    MatchFacts,
    SourceInfo,
    StatValue,
    TeamSide,
)


def make_facts() -> dict:
    """فکت‌های نمونه با ساختار واقعی build_match_facts."""
    m = MatchFacts(
        fixture_id="fdcouk:2026-11-08:Manchester United:Aston Villa",
        competition={"name": "Premier League", "season": "2026-27"},
        kickoff_utc="2026-11-08T00:00:00Z",
        source=SourceInfo(provider="football-data-co-uk", collected_at="2026-11-15T08:22:46Z",
                          payload_hash="d598a5f681e1a9a4acf9dad9fb203b68da6f67e2d195678dbe99e95fbba14593"),
        home=TeamSide(name_fa="منچستریونایتد", name_en="Manchester United",
                      last5=Last5(n=5, points=3, goals_for=3, goals_against=8),
                      xg_for_avg=StatValue(value=1.53, n=9, provider="football-data-co-uk"),
                      corners_avg=StatValue(value=5.8, n=10, provider="football-data-co-uk")),
        away=TeamSide(name_fa="استون ویلا", name_en="Aston Villa",
                      last5=Last5(n=5, points=11, goals_for=9, goals_against=6),
                      xg_for_avg=StatValue(value=1.2, n=9, provider="football-data-co-uk"),
                      corners_avg=StatValue(value=3.7, n=10, provider="football-data-co-uk")),
        data_quality=DataQuality(missing_fields=[]),
    )
    return json.loads(m.model_dump_json())


GOOD_RAW = json.dumps({
    "status": "ok",
    "title": "استون ویلا با فرم داغ به اُلدترافورد می‌آید",
    "bullets": [
        "استون ویلا ۱۱ امتیاز از ۵ بازی اخیر",
        "میانگین xG منچستریونایتد: 1.53 در 9 بازی",
    ],
    "caption": "شمارش معکوس برای دیدار منچستریونایتد و استون ویلا آغاز شده است. "
               "میهمان با ۱۱ امتیاز در ۵ بازی اخیر در فرم بهتری است، در حالی که "
               "میزبان در همین بازه فقط ۳ امتیاز گرفته و ۸ گل خورده است.",
    "source_note": "",
    "uncertainties": ["فرم ۵ بازی اخیر گارانتی نتایج آینده نیست"],
}, ensure_ascii=False)

BAD_NUMERIC_RAW = json.dumps({
    "status": "ok",
    "title": "استون ویلا با فرم داغ به اُلدترافورد می‌آید",
    "bullets": ["استون ویلا ۱۲ امتیاز از ۵ بازی اخیر"],
    "caption": "میهمان با فرمی عالی و ۱۲ امتیاز در ۵ بازی اخیر به میزبانی منچستریونایتد می‌رود.",
    "source_note": "",
    "uncertainties": [],
}, ensure_ascii=False)


class FakeLLM:
    """LLM ساختگی با فهرست پاسخ‌های از پیش تعیین‌شده و ثبت فراخوانی‌ها."""

    name = "fake"

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def generate(self, system_prompt: str, facts, **kw) -> DraftOutput:
        self.calls.append({"prompt": system_prompt, "payload": facts, "kwargs": kw})
        raw = self.responses.pop(0)
        return DraftOutput.from_json(raw)


class RepairFakeLLM(FakeLLM):
    """در تلاش اول عدد غلط می‌دهد؛ اگر feedback بگیرد، پاسخ سالم می‌دهد."""

    def generate(self, system_prompt: str, facts, **kw) -> DraftOutput:
        self.calls.append({"prompt": system_prompt, "payload": facts, "kwargs": kw})
        if kw.get("repair_feedback"):
            return DraftOutput.from_json(GOOD_RAW)
        return DraftOutput.from_json(BAD_NUMERIC_RAW)


# ─── مسیر خوش‌خیم ───

def test_happy_path_validated_first_attempt():
    llm = FakeLLM([GOOD_RAW])
    draft, rep, attempts = generate_draft(llm, make_facts())
    assert rep.passed, rep.failures
    assert attempts == 1
    assert draft.status == "ok"
    assert "football-data-co-uk" in draft.source_note  # source_note از کد
    assert llm.calls[0]["prompt"].startswith(SYSTEM_PROMPT.strip())  # system prompt واقعی (+ لحن/زوایای روایی فاز ۳)


# ─── مسیر retry ───

def test_retry_with_feedback_validates_second_attempt():
    llm = RepairFakeLLM([])
    draft, rep, attempts = generate_draft(llm, make_facts())
    assert rep.passed, rep.failures
    assert attempts == 2
    # feedback و پیش‌نویس ردشده به تلاش دوم رسیدند
    second_call = llm.calls[1]
    assert second_call["kwargs"].get("repair_feedback")
    assert "12" in second_call["kwargs"]["repair_feedback"]


def test_reject_after_two_bad_attempts():
    llm = FakeLLM([BAD_NUMERIC_RAW, BAD_NUMERIC_RAW])
    with pytest.raises(RejectedDraft):
        generate_draft(llm, make_facts())
    assert len(llm.calls) == 2


# ─── استحکام from_json ───

def test_from_json_strips_code_fence():
    fenced = "```json\n" + GOOD_RAW + "\n```"
    d = DraftOutput.from_json(fenced)
    assert d.status == "ok"
    assert d.title.startswith("استون ویلا")


def test_from_json_rejects_unknown_key():
    raw = json.dumps({"status": "ok", "title": "t", "bullets": [], "caption": "c",
                      "source_note": "", "uncertainties": [], "extra": 1})
    with pytest.raises(ValueError):
        DraftOutput.from_json(raw)


def test_from_json_rejects_bad_status():
    raw = json.dumps({"status": "maybe", "title": "t", "bullets": [], "caption": "c",
                      "source_note": "", "uncertainties": []})
    with pytest.raises(ValueError):
        DraftOutput.from_json(raw)


# ─── source_note از کد ───

def test_build_source_note_from_code_not_model():
    facts = make_facts()
    match = MatchFacts.model_validate(facts)
    note = build_source_note(match)
    assert "football-data-co-uk" in note
    assert "2026-11-15 08:22" in note
    assert "d598a5f681e1" in note  # hash prefix


# ─── save_draft: نسخه‌بندی idempotent ───

def _tmp_db(tmp_path):
    from contextlib import contextmanager

    from src.xgpedia.db import SCHEMA

    db_path = tmp_path / "test_posts.sqlite"
    _conn = sqlite3.connect(db_path)
    _conn.row_factory = sqlite3.Row
    _conn.executescript(SCHEMA)
    _conn.commit()

    @contextmanager
    def db():
        try:
            yield _conn
            _conn.commit()
        finally:
            pass

    return db, _conn


def test_save_draft_versions_incrementally(tmp_path, monkeypatch):
    from src.xgpedia.db import db as real_db

    db, conn = _tmp_db(tmp_path)
    monkeypatch.setattr("src.xgpedia.editorial.draft.db", db)

    facts = MatchFacts.model_validate(make_facts())
    draft = DraftOutput.from_json(GOOD_RAW)

    id1 = save_draft(draft, facts, "preview", "telegram")
    id2 = save_draft(draft, facts, "preview", "telegram")

    assert id2 == id1 + 1
    rows = conn.execute(
        "SELECT content_version, status, draft_json FROM posts ORDER BY post_id"
    ).fetchall()
    assert [r["content_version"] for r in rows] == [1, 2]
    assert all(r["status"] == "validated" for r in rows)
    dj = json.loads(rows[0]["draft_json"])
    assert dj["bullets"][0].startswith("استون ویلا")


def test_save_draft_real_db_compatible(tmp_path, monkeypatch):
    """ستون‌های INSERT باید با SCHEMA واقعی db.py منطبق باشند."""
    from src.xgpedia.db import db as real_db

    db, conn = _tmp_db(tmp_path)
    monkeypatch.setattr("src.xgpedia.editorial.draft.db", db)

    facts = MatchFacts.model_validate(make_facts())
    draft = DraftOutput.from_json(GOOD_RAW)
    pid = save_draft(draft, facts, "preview", "instagram")
    row = conn.execute("SELECT * FROM posts WHERE post_id = ?", (pid,)).fetchone()
    assert row["target_platform"] == "instagram"
    assert row["fact_json"] is not None and row["draft_json"] is not None
