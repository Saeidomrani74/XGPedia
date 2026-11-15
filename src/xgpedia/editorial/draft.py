"""لایهٔ ۴ — Editorial: تولید پیش‌نویس با مدل و عبور از هفت دروازهٔ validator.

سیاست retry (بخش ۸ سند): یک بار اصلاح خودکار؛ در شکست دوم، رد و ارسال برای
بررسی انسانی. خروجی موفق در جدول posts با status='validated' ذخیره می‌شود.

قاعدهٔ حیاتی: source_note هرگز از مدل نمی‌آید — لایهٔ کد آن را با نام provider
و تاریخ جمع‌آوری می‌سازد (مدل فقط متن می‌نویسد؛ عدد/نام/زمان از کد است).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from src.xgpedia.db import db
from src.xgpedia.editorial.llm_provider import DraftOutput, LLMProvider
from src.xgpedia.editorial.prompt import SYSTEM_PROMPT, derived_numbers
from src.xgpedia.editorial.validate import ValidationReport, validate
from src.xgpedia.normalization.models import MatchFacts


class RejectedDraft(Exception):
    """پیش‌نویس بعد از دو تلاش هم از دروازه‌ها نگذشت — نیازمند بررسی انسانی."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_source_note(match: MatchFacts) -> str:
    """یادداشت منبع از لایهٔ کد — با شناسهٔ منبع و زمان جمع‌آوری از JSON ورودی."""
    provider = match.source.provider
    collected = (match.source.collected_at or "")[:16].replace("T", " ")
    source_note = f"منبع داده: {provider} · جمع‌آوری {collected} (UTC)"
    if match.source.payload_hash:
        source_note += f" · hash {match.source.payload_hash[:12]}"
    return source_note


def _validate_draft(draft: DraftOutput, match: MatchFacts) -> ValidationReport:
    """اعتبارسنجی با source_note واقعیِ لایهٔ کد (نه چیزی که مدل نوشته)."""
    from dataclasses import replace

    d = replace(draft, source_note=build_source_note(match))
    return validate(d, match, derived_numbers(match))


def generate_draft(
    provider: LLMProvider,
    facts: dict,
    post_type: str = "preview",
    target_platform: str = "telegram",
) -> tuple[DraftOutput, ValidationReport, int]:
    """تولید پیش‌نویس + اعتبارسنجی + retry (حداکثر ۲ تلاش).

    خروجی: (پیش‌نویس نهایی، گزارش validator، تعداد تلاش).
    در شکست دوم → RejectedDraft با گزارش کامل.
    """
    from dataclasses import replace

    match = MatchFacts.model_validate(facts)
    attempts: list[str] = []
    feedback = ""
    previous_raw = ""

    for attempt in (1, 2):
        if attempt == 1 or not hasattr(provider, "generate"):
            draft = provider.generate(SYSTEM_PROMPT, match)
        else:
            try:
                draft = provider.generate(
                    SYSTEM_PROMPT, match, repair_feedback=feedback, previous_raw=previous_raw
                )
            except TypeError:
                # providerهای ساده (مثل FakeLLM تست) آرگومان اصلاحی نمی‌گیرند
                draft = provider.generate(SYSTEM_PROMPT, match)
        rep = _validate_draft(draft, match)
        if rep.passed:
            # source_note را همیشه از کد بازنویسی می‌کنیم — عدد/نام/زمان از کد است
            final = replace(draft, source_note=build_source_note(match))
            return final, rep, attempt
        attempts.append("; ".join(rep.failures))
        feedback = "; ".join(rep.failures)
        previous_raw = json.dumps(
            {
                "status": draft.status,
                "title": draft.title,
                "bullets": draft.bullets,
                "caption": draft.caption,
                "source_note": draft.source_note,
                "uncertainties": draft.uncertainties,
            },
            ensure_ascii=False,
        )
        if attempt == 1:
            print(f"  [attempt 1] validator rejected - retrying with feedback")
            print(f"    {attempts[0][:300]}")

    raise RejectedDraft(
        "پیش‌نویس بعد از ۲ تلاش هم از دروازه‌ها نگذشت:\n  - تلاش ۱: "
        + attempts[0]
        + "\n  - تلاش ۲: "
        + attempts[1]
    )


def save_draft(
    draft: DraftOutput,
    facts: MatchFacts,
    post_type: str,
    target_platform: str,
    conn: sqlite3.Connection | None = None,
) -> int:
    """ذخیرهٔ پیش‌نویس معتبر در posts — idempotent با content_version جدید.

    کلید یکتا: (fixture_id, post_type, target_platform, content_version).
    اگر نسخه‌ای از قبل برای همین سه‌گانه وجود دارد، content_version = max+1 می‌شود.
    status='validated' یعنی از هفت دروازه گذشته؛ انتشار هنوز تأیید دستی می‌خواهد.
    """
    payload = {
        "status": draft.status,
        "title": draft.title,
        "bullets": draft.bullets,
        "caption": draft.caption,
        "source_note": draft.source_note,
        "uncertainties": draft.uncertainties,
    }
    now = _utc_now_iso()

    def _save(c: sqlite3.Connection) -> int:
        row = c.execute(
            "SELECT COALESCE(MAX(content_version), 0) FROM posts "
            "WHERE fixture_id = ? AND post_type = ? AND target_platform = ?",
            (facts.fixture_id, post_type, target_platform),
        ).fetchone()
        next_version = (row[0] or 0) + 1
        cur = c.execute(
            """
            INSERT INTO posts (fixture_id, post_type, target_platform, content_version,
                               status, title, caption, draft_json, fact_json, created_at)
            VALUES (?, ?, ?, ?, 'validated', ?, ?, ?, ?, ?)
            """,
            (
                facts.fixture_id,
                post_type,
                target_platform,
                next_version,
                draft.title,
                draft.caption,
                json.dumps(payload, ensure_ascii=False),
                json.dumps(facts.model_dump(mode="json"), ensure_ascii=False),
                now,
            ),
        )
        return cur.lastrowid or 0

    if conn is not None:
        return _save(conn)
    with db() as c:
        return _save(c)
