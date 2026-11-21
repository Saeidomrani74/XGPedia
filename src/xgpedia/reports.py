"""گزارش هفتگی کوتاه — معیار پایان دروازهٔ ۳ (NEXT_STEPS مرحلهٔ ۶).

۷ روز آخر را از DB می‌خواند (بدون شبکه): پست‌ها بر اساس وضعیت، لاگ انتشار
(ok/dry_run/خطا)، تصمیم‌های ادمین‌ها و تازگی داده. خروجی: مارک‌داون فارسی.

قاعدهٔ توقف (NEXT_STEPS مرحلهٔ ۶): دو خطای مهم در ۷ روز = توقف انتشار خودکار
آن دسته — «خطای مهم» = رکورد publishing_logs با result نه ok و نه dry_run
(مثلاً error رندر/ارسال که در گام publish زنجیرهٔ daily ثبت می‌شود).
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from src.xgpedia.db import db
from src.xgpedia.sync import data_freshness

STOP_RULE_ERRORS = 2


def _iso_days(days: int, end: date | None) -> tuple[str, str]:
    """بازهٔ [end-days+1 .. end] به‌صورت دو رشتهٔ YYYY-MM-DD."""
    end_d = end or datetime.now(UTC).date()
    start_d = end_d - timedelta(days=days - 1)
    return start_d.isoformat(), end_d.isoformat()


def _between(col: str) -> str:
    """شرط بازهٔ تاریخ روی ستون ISO — substr تا پسوندهای زمانی‌/منطقه‌ای قطع شوند."""
    return f"substr({col},1,10) BETWEEN ? AND ?"


def weekly_report(days: int = 7, end: date | None = None) -> str:
    """گزارش مارک‌داون فارسی `days` روز منتهی به `end` (پیش‌فرض: امروز UTC)."""
    start_s, end_s = _iso_days(days, end)
    with db() as conn:
        posts_by_status = dict(
            conn.execute(
                f"SELECT status, COUNT(*) FROM posts WHERE {_between('created_at')} GROUP BY status",
                (start_s, end_s),
            ).fetchall()
        )
        pub_by_result = dict(
            conn.execute(
                f"SELECT result, COUNT(*) FROM publishing_logs WHERE {_between('published_at')} GROUP BY result",
                (start_s, end_s),
            ).fetchall()
        )
        mod_by_action = dict(
            conn.execute(
                f"SELECT action, COUNT(*) FROM moderation_logs WHERE {_between('created_at')} GROUP BY action",
                (start_s, end_s),
            ).fetchall()
        )
        last_pub = conn.execute(
            "SELECT p.post_id, p.title, l.platform_message_id, l.published_at"
            " FROM publishing_logs l JOIN posts p ON p.post_id = l.post_id"
            " WHERE l.result = 'ok' ORDER BY l.published_at DESC LIMIT 1"
        ).fetchone()

    total_posts = sum(posts_by_status.values())
    published = posts_by_status.get("published", 0)
    corrected = posts_by_status.get("corrected", 0)
    ok_sends = pub_by_result.get("ok", 0)
    dry_runs = pub_by_result.get("dry_run", 0)
    important_errors = sum(
        n for r, n in pub_by_result.items() if r not in ("ok", "dry_run")
    )
    pending = posts_by_status.get("awaiting_approval", 0)

    if important_errors >= STOP_RULE_ERRORS:
        verdict = f"⛔ **توقف** — {important_errors} خطای مهم در {days} روز (قاعدهٔ NEXT_STEPS: ≥۲ = توقف آن دسته)"
    elif important_errors == 1:
        verdict = "⚠️ یک خطای مهم — دفعهٔ بعدی با دقت بیشتر؛ خطای دوم یعنی توقف"
    else:
        verdict = "✅ بدون خطای مهم"

    fresh = data_freshness()
    last_finished = fresh.get("last_finished_match", "-")

    md = [
        f"# گزارش هفتگی XGPedia — {start_s} تا {end_s}",
        "",
        f"بازه: {days} روز · مجموع پست‌ها: **{total_posts}**",
        "",
        "| شاخص | مقدار |",
        "|---|---|",
        f"| منتشرشده | {published} |",
        f"| در صف تأیید | {pending} |",
        f"| آمادهٔ ارسال (validated) | {posts_by_status.get('validated', 0)} |",
        f"| ردشده/ناتمام (failed) | {posts_by_status.get('failed', 0)} |",
        f"| پیش‌نویس باقی‌مانده | {posts_by_status.get('draft', 0)} |",
        f"| اصلاح‌شده | {corrected} |",
        f"| ارسال موفق (publishing_logs ok) | {ok_sends} |",
        f"| dry-run | {dry_runs} |",
        f"| **خطای مهم** | **{important_errors}** |",
        f"| تأیید / رد / ویرایش ادمین | {mod_by_action.get('approve', 0)}"
        f" / {mod_by_action.get('reject', 0)} / {mod_by_action.get('edit', 0)} |",
        f"| آخرین دادهٔ مسابقهٔ تمام‌شده | {last_finished} |",
        "",
        f"**رأی: {verdict}**",
        "",
    ]
    if last_pub:
        md.append(
            f"آخرین پست منتشرشده: پست {last_pub['post_id']} — {(last_pub['title'] or '')[:60]}"
            f" (پیام {last_pub['platform_message_id']} در {last_pub['published_at'][:16]})"
        )
    else:
        md.append("هنوز هیچ پستی منتشر نشده است.")
    if corrected:
        md.append("")
        md.append(
            f"⚠️ {corrected} اصلاحیه در این بازه — ردیف‌های آن در `docs/corrections.md` به‌روز باشند."
        )
    return "\n".join(md) + "\n"


def save_weekly_report(root, days: int = 7, end: date | None = None) -> str:
    """نوشتن گزارش در docs/weekly/week-<شروع>_<پایان>.md — خروجی: مسیر فایل.

    معیار پایان دروازهٔ ۳: «گزارش هفتگی کوتاه در docs/».
    """
    from pathlib import Path

    start_s, end_s = _iso_days(days, end)
    out_dir = Path(root) / "docs" / "weekly"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"week-{start_s}_{end_s}.md"
    path.write_text(weekly_report(days, end), encoding="utf-8")
    return str(path)
