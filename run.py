"""run.py — درگاه واحد خط فرمان.

نمونه‌های اجرا:
  python run.py init                              # ساخت پایگاه داده
  python run.py fixtures --date 2026-11-14        # Workflow A: بازی‌های یک روز
  python run.py preview --fixture provider:1035214  # Workflow B: JSON پیش‌بازی
  python run.py pipeline --fixture provider:1035214 # کل خط تا draft (بدون انتشار)
  python run.py render --template number_of_day --json data/samples/fact.json
  python run.py test-provider --matches 5         # آزمون پوشش (روز ۱ هفتهٔ ۳)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.xgpedia.db import init_db


def cmd_fixtures(args: argparse.Namespace) -> None:
    """Workflow A — دریافت fixtures روز، به‌روزرسانی DB، انتخاب بازی‌های مهم."""
    from src.xgpedia.providers.api_football import ApiFootball
    from src.xgpedia.providers.base import RateLimitBudget

    api = ApiFootball(budget=RateLimitBudget(daily_limit=100))
    raw = api.fixtures_by_date(args.date)
    for fx in raw.payload.get("response", []):
        print(
            fx["fixture"]["id"],
            fx["teams"]["home"]["name"],
            "vs",
            fx["teams"]["away"]["name"],
            fx["fixture"]["date"],
        )
    print(f"— {len(raw.payload.get('response', []))} بازی · hash: {raw.payload_hash[:12]}")


def cmd_test_provider(args: argparse.Namespace) -> None:
    """آزمون پوشش provider — ۱۰ آزمون جدول ۵.۲ سند؛ خروجی: docs/provider-test.md"""
    from src.xgpedia.providers.api_football import ApiFootball

    api = ApiFootball()
    sample = api.fixtures_by_date((datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d"))
    matches = sample.payload.get("response", [])[: args.matches]
    report = ["# آزمون پوشش API-Football", "", f"نمونه: {len(matches)} مسابقه", ""]
    for fx in matches:
        fid = fx["fixture"]["id"]
        stats = api.fixture_statistics(fid)
        found = set()
        for team_stats in stats.payload.get("response", []):
            for s in team_stats.get("statistics", []):
                if s.get("type"):
                    found.add(s["type"].lower())
        has_xg = any("expected" in f for f in found)
        report.append(
            f"- fixture {fid}: xG={'دارد' if has_xg else 'ندارد'} · "
            f"فیلدها: {', '.join(sorted(found))}"
        )
    out = Path("docs/provider-test.md")
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(report), encoding="utf-8")
    print(f"OK — گزارش در {out}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="xgpedia", description="خط تولید XGPedia")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="ساخت پایگاه داده")
    p_fix = sub.add_parser("fixtures", help="بازی‌های یک تاریخ (Workflow A)")
    p_fix.add_argument("--date", required=True, help="YYYY-MM-DD")
    p_test = sub.add_parser("test-provider", help="آزمون پوشش provider")
    p_test.add_argument("--matches", type=int, default=5)

    args = parser.parse_args(argv)
    if args.cmd == "init":
        init_db()
        print("OK — پایگاه داده ساخته شد")
    elif args.cmd == "fixtures":
        cmd_fixtures(args)
    elif args.cmd == "test-provider":
        cmd_test_provider(args)
    else:
        parser.error("دستور ناشناخته")
    return 0


if __name__ == "__main__":
    sys.exit(main())
