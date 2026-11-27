"""داشبورد یادگیری ترجیحات ادمین و آمادگی انتشار خودکار بر پایهٔ جدول `post_metrics` (v0.80.0)."""
from __future__ import annotations

from typing import Any

from src.xgpedia import db as db_mod


def summarize_post_metrics(
    *,
    min_samples: int = 10,
    auto_threshold: float = 0.95,
    max_avg_edits: float = 0.25,
) -> dict[str, Any]:
    """خلاصه‌سازی تصمیم‌های ثبت‌شده در `post_metrics` به تفکیک `card_type` و `tone`.

    قالب‌هایی که حداقل `min_samples` نمونه، نرخ تایید >= `auto_threshold` و میانگین ویرایش <= `max_avg_edits`
    داشته باشند به‌عنوان نامزد انتشار خودکار (`auto_publish_candidates`) معرفی می‌شوند.
    """
    by_card: dict[str, dict[str, Any]] = {}
    by_tone: dict[str, dict[str, Any]] = {}
    total = 0
    total_approved = 0

    try:
        with db_mod.db() as conn:
            rows = conn.execute(
                """
                SELECT card_type, COALESCE(tone, 'default') AS tone,
                       admin_decision, COALESCE(edit_count, 0) AS edit_count
                FROM post_metrics
                ORDER BY recorded_at DESC
                """
            ).fetchall()
    except Exception:
        rows = []

    for r in rows:
        ct = str(r["card_type"] or "unknown")
        tn = str(r["tone"] or "default")
        dec = str(r["admin_decision"] or "").lower()
        edits = int(r["edit_count"] or 0)
        is_ok = dec in ("approved", "published", "auto_published")

        total += 1
        if is_ok:
            total_approved += 1

        for bucket, key in ((by_card, ct), (by_tone, tn)):
            st = bucket.setdefault(key, {"total": 0, "approved": 0, "rejected": 0, "edits_sum": 0})
            st["total"] += 1
            if is_ok:
                st["approved"] += 1
            elif dec in ("rejected", "cancelled", "discarded"):
                st["rejected"] += 1
            st["edits_sum"] += edits

    auto_candidates: list[str] = []
    for ct, st in by_card.items():
        st["approval_rate"] = round(st["approved"] / st["total"], 4) if st["total"] else 0.0
        st["avg_edits"] = round(st["edits_sum"] / st["total"], 2) if st["total"] else 0.0
        st["auto_ready"] = (
            st["total"] >= min_samples
            and st["approval_rate"] >= auto_threshold
            and st["avg_edits"] <= max_avg_edits
        )
        if st["auto_ready"]:
            auto_candidates.append(ct)

    for tn, st in by_tone.items():
        st["approval_rate"] = round(st["approved"] / st["total"], 4) if st["total"] else 0.0
        st["avg_edits"] = round(st["edits_sum"] / st["total"], 2) if st["total"] else 0.0

    return {
        "total": total,
        "approved": total_approved,
        "overall_approval_rate": round(total_approved / total, 4) if total else 0.0,
        "by_card": by_card,
        "by_tone": by_tone,
        "auto_publish_candidates": sorted(auto_candidates),
    }


def format_metrics_report_fa(summary: dict[str, Any] | None = None) -> str:
    """قالب‌بندی گزارش فارسی خوانا برای دستور `/metrics` تلگرام."""
    s = summary if summary is not None else summarize_post_metrics()
    total = int(s.get("total") or 0)
    if total == 0:
        return (
            "📊 <b>داشبورد یادگیری و کیفیت انتشار (XGPedia Metrics)</b>\n\n"
            "هنوز تصمیمی در جدول <code>post_metrics</code> ثبت نشده است.\n"
            "با تایید، ویرایش یا رد پست‌ها در ربات، آمار دقت و آمادگی انتشار خودکار اینجا نمایش داده می‌شود."
        )

    pct = round(float(s.get("overall_approval_rate") or 0.0) * 100, 1)
    lines = [
        "📊 <b>داشبورد یادگیری و کیفیت انتشار (XGPedia Metrics)</b>",
        f"• کل تصمیم‌های ثبت‌شده: <b>{total}</b> | نرخ تایید کلی: <b>{pct}%</b>",
        "",
        "<b>عملکرد به تفکیک نوع کارت:</b>",
    ]
    by_card = s.get("by_card") or {}
    for ct, st in sorted(by_card.items(), key=lambda kv: (-kv[1]["total"], kv[0]))[:12]:
        cpct = round(st["approval_rate"] * 100, 1)
        badge = " ✅ آماده خودکارسازی" if st.get("auto_ready") else ""
        lines.append(
            f"• <code>{ct}</code>: {st['approved']}/{st['total']} ({cpct}%) | میانگین ویرایش: {st['avg_edits']}{badge}"
        )

    cands = s.get("auto_publish_candidates") or []
    lines.append("")
    if cands:
        lines.append("🤖 <b>قالب‌های آمادهٔ انتشار خودکار (≥۹۵٪ تایید، ≥۱۰ نمونه):</b> " + "، ".join(f"<code>{c}</code>" for c in cands))
    else:
        lines.append("🤖 هنوز قالبی به حدنصاب انتشار خودکار (≥۱۰ نمونه و ≥۹۵٪ تایید) نرسیده است.")
    return "\n".join(lines)
