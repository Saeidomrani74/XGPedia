"""لایهٔ ۹ — خط تولید روزانهٔ سرتاسری (Workflow A خودکار — NEXT_STEPS مرحلهٔ ۳).

زنجیرهٔ هر اجرا به ترتیب:
  sync-results → fixtures (هر دو با تحمل خطا) → status (هشدار کهنگی) →
  برای هر بازیِ روزِ هدف که هنوز پست ندارد: facts → draft (LLM + ۷ دروازه) →
  render-post → صف تأیید تلگرام (اگر توکن هست؛ وگرنه WARN و ادامه).

قواعد طراحی (D26):
  - idempotency روزانه: اگر برای (fixture, post_type, platform) پستی هست، بازی
    رد می‌شود — اجرای دوبارهٔ cron همان روز نه LLM صدا می‌زند نه پست تکراری می‌سازد.
  - ایزولاسیون خطا: شکست یک بازی (فکت/LLM/رندر) بقیهٔ روز را نمی‌اندازد؛ فقط
    exit code = ۱ می‌شود تا Task Scheduler/CI بفهمد اجرا ناقص بوده.
  - submit اختیاری: بدون TELEGRAM_BOT_TOKEN/ADMIN_TELEGRAM_IDS فقط یک WARN —
    کارت‌ها در output/ می‌مانند و دستور بازیابی دقیق چاپ می‌شود.
  - پیام‌های کنسول انگلیسی/ASCII (قاعدهٔ run.py)؛ فارسی فقط در تلگرام/اسناد.

همهٔ گام‌ها قابل‌تزریق‌اند (DailySteps) — همان الگوی transport مرحلهٔ ۲؛
تست‌ها بدون شبکه/LLM/توکن سبز می‌مانند. اتصال به پیاده‌سازی‌های واقعی در
default_steps() است و importهای سنگین (LLM/Playwright/aiogram) lazy می‌مانند.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from src.xgpedia.db import db
from src.xgpedia.sync import data_freshness

POST_TYPE_DEFAULT = "preview"
PLATFORM_DEFAULT = "telegram"
STALE_AFTER_DAYS = 4  # همان آستانهٔ هشدار cmd_status


@dataclass
class DailyResult:
    """خلاصهٔ یک اجرا — exit_code برای Task Scheduler و CI."""

    target_date: str
    fixtures_found: int = 0
    created: list[int] = field(default_factory=list)      # post_idهای ساخته‌شده
    rendered: list[int] = field(default_factory=list)
    submitted: list[int] = field(default_factory=list)
    skipped_existing: list[str] = field(default_factory=list)  # fixture_idهای دارای پست
    failed: list[str] = field(default_factory=list)
    sync_ok: bool = True
    fixtures_sync_ok: bool = True

    @property
    def exit_code(self) -> int:
        return 1 if self.failed else 0


# ─── ۱) برنامهٔ روز — خالص، فقط DB ───


def fixtures_on_date(conn, date_utc: str) -> list[dict]:
    """بازی‌های تمام‌نشدهٔ روز داده‌شده.

    substr لازم است چون kickoff_utc دو گرانولاریتی دارد: CSV فقط تاریخ
    («2026-11-08») و football-data.org کامل ISO («2026-11-19T20:00:00Z»).
    """
    rows = conn.execute(
        """
        SELECT fixture_id, kickoff_utc, home_team, away_team, status
        FROM fixtures
        WHERE substr(kickoff_utc, 1, 10) = ? AND status != 'finished'
        ORDER BY kickoff_utc, fixture_id
        """,
        (date_utc,),
    ).fetchall()
    return [dict(r) for r in rows]


def fixtures_with_post(conn, fixture_ids: list[str], post_type: str, platform: str) -> set[str]:
    """fixture_idهایی که برای همین (نوع پست، پلتفرم) پست دارند — کلید idempotency."""
    if not fixture_ids:
        return set()
    ph = ",".join("?" * len(fixture_ids))
    rows = conn.execute(
        f"SELECT DISTINCT fixture_id FROM posts "
        f"WHERE fixture_id IN ({ph}) AND post_type = ? AND target_platform = ?",
        (*fixture_ids, post_type, platform),
    ).fetchall()
    return {r["fixture_id"] for r in rows}


def plan_day(
    conn, date_utc: str, post_type: str = POST_TYPE_DEFAULT,
    platform: str = PLATFORM_DEFAULT, limit: int = 8,
) -> tuple[list[dict], list[str]]:
    """(بازی‌های قابل‌پردازش، ردشده‌ها چون پست دارند) — قلب idempotency روزانه.

    limit روی بازی‌های «بدون پست» اعمال می‌شود (سقف هزینهٔ LLM در هر اجرا)؛
    بازی‌های دارای پست همیشه در skipped گزارش می‌شوند تا لاگ صادق بماند.
    """
    on_date = fixtures_on_date(conn, date_utc)
    have_post = fixtures_with_post(
        conn, [f["fixture_id"] for f in on_date], post_type, platform
    )
    todo = [f for f in on_date if f["fixture_id"] not in have_post][: max(limit, 0)]
    return todo, sorted(have_post)


def staleness_note(today: date | None = None) -> str | None:
    """[OK]/[WARN] کهنگی داده — همان آستانهٔ ۴ روزِ cmd_status؛ برای تست today قابل‌تزریق."""
    info = data_freshness()
    last = info["last_finished_match"]
    if last == "-":
        return "[WARN] no finished matches in DB - run: python run.py sync-results"
    today = today or datetime.now(UTC).date()
    age = (today - date.fromisoformat(last[:10])).days
    if age > STALE_AFTER_DAYS:
        return f"[WARN] data is stale ({age} days > {STALE_AFTER_DAYS}) - check sync-results"
    return f"[OK] data fresh ({age} days old)"


# ─── ۲) گام‌های قابل‌تزریق ───


@dataclass
class DailySteps:
    """شش گام زنجیره — تست‌ها همه را ساختگی می‌دهند؛ پیش‌فرض: default_steps()."""

    sync_results_fn: Callable[[], str]
    sync_fixtures_fn: Callable[[], str]
    facts_fn: Callable[[str, str], dict]
    draft_fn: Callable[[dict, str, str], int]
    render_fn: Callable[[int, str], Path]
    submit_fn: Callable[[int], None]


def default_steps() -> DailySteps:
    """اتصال به پیاده‌سازی‌های واقعی — قرارداد همان متن cmdهای تک‌قدمی run.py."""
    from src.xgpedia.config import CURRENT_SEASON_START, ROOT
    from src.xgpedia.editorial.draft import generate_draft, save_draft
    from src.xgpedia.editorial.llm_provider import OpenAICompatibleLLM
    from src.xgpedia.normalization.models import MatchFacts
    from src.xgpedia.providers.football_data_couk import FootballDataCoUk
    from src.xgpedia.render.cards import render_preview_card
    from src.xgpedia.sync import build_match_facts, sync_csv_results, sync_upcoming_fixtures

    def sync_results_fn() -> str:
        api = FootballDataCoUk()
        try:
            rows, payload_hash, _ = api.fetch_season_rows(CURRENT_SEASON_START)
        finally:
            api.close()
        if not rows:
            return "0 finished rows (CSV may hold only upcoming fixtures)"
        s = sync_csv_results(rows, payload_hash, season_start=CURRENT_SEASON_START)
        return (f"{len(rows)} matches, fixtures +{s['fixtures_new']}/"
                f"~{s['fixtures_updated']}, stats {s['stats_rows']}")

    def sync_fixtures_fn() -> str:
        from src.xgpedia.providers.football_data_org import FootballDataOrg

        api = FootballDataOrg()  # بدون توکن → خطای واضح؛ بالادسته تحمل می‌کند
        try:
            raw = api.upcoming_fixtures(days=7)
            s = sync_upcoming_fixtures(raw)
            return f"{s['total_in_payload']} upcoming, new {s['upcoming_new']}"
        finally:
            api.close()

    llm = None  # یک کلاینت در طول اجرا — نه به‌ازای هر بازی

    def facts_fn(fixture_id: str, post_type: str) -> dict:
        return build_match_facts(fixture_id, post_match=(post_type == "post_match"))

    def draft_fn(facts: dict, post_type: str, platform: str) -> int:
        nonlocal llm
        if llm is None:
            llm = OpenAICompatibleLLM()
        draft, _, _ = generate_draft(llm, facts, post_type=post_type, target_platform=platform)
        return save_draft(
            draft, facts=MatchFacts.model_validate(facts),
            post_type=post_type, target_platform=platform,
        )

    def render_fn(post_id: int, fmt: str) -> Path:
        with db() as conn:
            r = conn.execute("SELECT * FROM posts WHERE post_id = ?", (post_id,)).fetchone()
        if r is None or not r["draft_json"] or not r["fact_json"]:
            raise FileNotFoundError(f"post {post_id} has no archived draft/facts to render")
        _, img_path, _ = render_preview_card(
            json.loads(r["draft_json"]), json.loads(r["fact_json"]),
            out_dir=ROOT / "output", post_id=post_id, version=r["content_version"],
            platform=r["target_platform"], post_type=r["post_type"], fmt=fmt,
        )
        return img_path

    def submit_fn(post_id: int) -> None:
        from src.xgpedia.publishers.telegram_publish import publish_cli

        rc = publish_cli(post_id, dry_run=False)
        if rc:
            raise RuntimeError(f"publish_cli returned {rc}")

    return DailySteps(
        sync_results_fn=sync_results_fn, sync_fixtures_fn=sync_fixtures_fn,
        facts_fn=facts_fn, draft_fn=draft_fn, render_fn=render_fn, submit_fn=submit_fn,
    )


def _telegram_configured() -> bool:
    """صف تأیید فقط وقتی وصل است که توکن و ادمین هر دو باشند (وگرنه WARN، نه خطا)."""
    try:
        from src.xgpedia.config import ADMIN_TELEGRAM_IDS, TELEGRAM_BOT_TOKEN

        return bool(TELEGRAM_BOT_TOKEN and ADMIN_TELEGRAM_IDS)
    except Exception:  # noqa: BLE001 — پیکربندی ناقص = غیرفعال، نه کرش
        return False


# ─── ۳) ارکستراتور ───


def run_daily(
    target_date: str | None = None,
    limit: int = 8,
    post_type: str = POST_TYPE_DEFAULT,
    platform: str = PLATFORM_DEFAULT,
    fmt: str = "4:5",
    submit: bool = True,
    sync: bool = True,
    steps: DailySteps | None = None,
    log: Callable[[str], None] = print,
) -> DailyResult:
    """اجرای کل زنجیرهٔ روز — پیش‌فرض روزِ هدف = فردای UTC.

    خطای sync → WARN و ادامه با DB موجود؛ خطای هر بازی → ایزوله و ثبت در
    failed (با دستور بازیابی دستی)؛ هیچ استثنایی از این تابع بیرون نمی‌رود.
    """
    date_utc = target_date or (datetime.now(UTC) + timedelta(days=1)).date().isoformat()
    res = DailyResult(target_date=date_utc)
    steps = steps or default_steps()

    if sync:
        for name, fn, attr in (
            ("sync-results", steps.sync_results_fn, "sync_ok"),
            ("fixtures", steps.sync_fixtures_fn, "fixtures_sync_ok"),
        ):
            try:
                log(f"OK - {name}: {fn()}")
            except Exception as e:  # noqa: BLE001 — دادهٔ دیروز هنوز قابل‌استفاده است
                setattr(res, attr, False)
                log(f"WARN - {name} failed ({type(e).__name__}: {str(e)[:200]})"
                    " - continuing with DB as-is")

    note = staleness_note()
    if note:
        log(note)

    with db() as conn:
        todo, skipped = plan_day(conn, date_utc, post_type, platform, limit)
    res.fixtures_found = len(todo) + len(skipped)
    res.skipped_existing = skipped
    for fid in skipped:
        log(f"SKIP - {fid} (post already exists - daily is idempotent)")

    if not todo:
        log(f"OK - nothing to generate for {date_utc} ({res.fixtures_found} fixture(s) checked)")
        return res

    submit_enabled = submit and _telegram_configured()
    if submit and not submit_enabled:
        log("WARN - Telegram not configured (TELEGRAM_BOT_TOKEN / ADMIN_TELEGRAM_IDS)"
            " - cards stay in output/; manual: python run.py publish --post-id N")

    log(f"plan: {len(todo)} {post_type} post(s) for {date_utc} (limit {limit})")
    for fx in todo:
        fid = fx["fixture_id"]
        label = f"{fx['home_team']} vs {fx['away_team']} ({fx['kickoff_utc']})"
        post_id: int | None = None
        try:
            facts = steps.facts_fn(fid, post_type)
            post_id = steps.draft_fn(facts, post_type, platform)
            res.created.append(post_id)
            img = steps.render_fn(post_id, fmt)
            res.rendered.append(post_id)
            log(f"OK - {label} -> post {post_id} rendered: {Path(img).name}")
            if submit_enabled:
                try:
                    steps.submit_fn(post_id)
                    res.submitted.append(post_id)
                    log(f"OK - post {post_id} sent to review queue")
                except Exception as e:  # noqa: BLE001 — پست هست؛ فقط صف نیفتاده
                    msg = (f"{fid}: submit failed ({type(e).__name__}: {str(e)[:150]})"
                           f" - manual: python run.py publish --post-id {post_id}")
                    res.failed.append(msg)
                    log(f"WARN - {msg}")
        except Exception as e:  # noqa: BLE001 — ایزولاسیون: این بازی، بقیه را نمی‌اندازد
            msg = f"{fid}: {type(e).__name__}: {str(e)[:250]}"
            if post_id is not None:  # پست ساخته شده ولی رندر/مرحلهٔ بعد نیفتاده
                msg += f" - manual: python run.py render-post --post-id {post_id}"
            res.failed.append(msg)
            log(f"FAIL - {msg}")

    log(
        f"done {date_utc}: found {res.fixtures_found}, created {len(res.created)}, "
        f"rendered {len(res.rendered)}, submitted {len(res.submitted)}, "
        f"skipped {len(res.skipped_existing)}, failed {len(res.failed)}"
    )
    return res
