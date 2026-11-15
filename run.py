"""run.py — درگاه واحد خط فرمان (نسخهٔ ۸).

منابع داده پس از قطع دسترسی پلن رایگان API-Football به فصل‌های جاری:
  - football-data.co.uk (CSV هفتگی): xG + شوت + کرنر مسابقه‌ها — بدون کلید
  - football-data.org (API v4): بازی‌های پیش‌رو + جدول — توکن رایگان

نکتهٔ خروجی ترمینال: همهٔ پیام‌های چاپ‌شده عمداً انگلیسی/ASCII است، چون کنسول
ویندوز (cmd) متن راست‌به‌چپ را درست شکل نمی‌دهد (فارسی جدا و برعکس دیده می‌شود).
اسناد و گزارش‌های فایل (مثل docs/provider-test.md) فارسی می‌مانند.

نمونه‌های اجرا:
  python run.py init                              # ساخت پایگاه داده
  python run.py sync-results                      # دانلود CSV فصل جاری → DB
  python run.py sync-results --season 2025        # فصل قبل (بدون xG — فقط آمار)
  python run.py fixtures --days 7                 # بازی‌های پیش‌رو (نیازمند توکن fdo)
  python run.py facts --fixture "fdcouk:2026-11-08:Manchester United:Aston Villa"
  python run.py status                            # تازگی داده و آمار DB
  python run.py test-provider --matches 5         # آزمون پوشش (روز ۱ هفتهٔ ۳)
  python run.py draft --fixture ID [--platform telegram] [--post-type preview]
  python run.py list-posts                        # پیش‌نویس‌های ذخیره‌شده
  python run.py show-post --post-id 1             # نمایش کامل یک پست
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# سازگاری ویندوز: اگر خروجی به فایل/لاگ می‌رود UTF-8 باشد؛ کنسول تعاملی خودش یونیکد است
if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if not stream.isatty():
            try:
                stream.reconfigure(encoding="utf-8")
            except (AttributeError, OSError):
                pass

from src.xgpedia.config import CURRENT_SEASON_START
from src.xgpedia.db import init_db
from src.xgpedia.sync import data_freshness, season_label

# anchor مسیر پروژه — دستورات همیشه از ریشهٔ پکیج کار می‌کنند، مستقل از cwd
ROOT = Path(__file__).resolve().parent


def cmd_sync_results(args: argparse.Namespace) -> None:
    """دانلود CSV football-data.co.uk فصل داده‌شده → fixtures + statistics در DB."""
    from src.xgpedia.providers.football_data_couk import FootballDataCoUk
    from src.xgpedia.sync import sync_csv_results

    api = FootballDataCoUk()
    try:
        rows, payload_hash, path = api.fetch_season_rows(args.season)
        if not rows:
            print("No finished rows found - the CSV may contain only upcoming fixtures")
            return
        summary = sync_csv_results(rows, payload_hash, season_start=args.season)
        xg_rows = sum(1 for r in rows if r.home_xg is not None)
        print(f"Season {season_label(args.season)}: {len(rows)} finished matches")
        print(f"  xG available for {xg_rows}/{len(rows)} matches")
        print(f"  fixtures: {summary['fixtures_new']} new, {summary['fixtures_updated']} updated")
        print(f"  stat rows: {summary['stats_rows']}")
        print(f"  raw file: {path.name} - sha256 prefix: {payload_hash[:12]}")
    finally:
        api.close()


def cmd_fixtures(args: argparse.Namespace) -> None:
    """Workflow A — بازی‌های پیش‌رو از football-data.org."""
    from src.xgpedia.providers.football_data_org import FootballDataOrg
    from src.xgpedia.sync import sync_upcoming_fixtures

    try:
        api = FootballDataOrg()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(2)
    try:
        raw = api.upcoming_fixtures(days=args.days)
        summary = sync_upcoming_fixtures(raw)
        for m in raw.payload.get("matches", []):
            print(
                f"  {m['utcDate'][:16].replace('T', ' ')} UTC - "
                f"{m['homeTeam']['name']} vs {m['awayTeam']['name']}"
            )
        print(f"- {summary['total_in_payload']} upcoming matches, new: {summary['upcoming_new']}")
    finally:
        api.close()


def cmd_facts(args: argparse.Namespace) -> None:
    """ساخت JSON واقعیت‌ها برای یک fixture — ورودی لایهٔ تحریریه."""
    from src.xgpedia.sync import build_match_facts

    facts = build_match_facts(args.fixture)
    out = Path(args.out) if args.out else None
    text = json.dumps(facts, ensure_ascii=False, indent=2)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"OK - saved to {out}")
    # پیش‌نمایش کنسول با ensure_ascii=True تا در هر ترمینالی درست دیده شود
    preview = json.dumps(facts, ensure_ascii=True, indent=2)
    print(preview[:1200])
    if len(preview) > 1200:
        print("... (use --out to save the full JSON)")


def cmd_status(_: argparse.Namespace) -> None:
    """تازگی داده — مبنای پایش cron روزانه."""
    info = data_freshness()
    print("Database status:")
    for k, v in info.items():
        print(f"  {k}: {v}")
    if info["last_finished_match"] != "-":
        last = info["last_finished_match"][:10]
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        age = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(last, "%Y-%m-%d")).days
        flag = "[WARN] data is stale (> 4 days)" if age > 4 else "[OK] fresh"
        print(f"  data age: {age} days - {flag}")


def cmd_test_provider(args: argparse.Namespace) -> None:
    """آزمون پوشش روی N مسابقهٔ اخیر CSV — خروجی docs/provider-test.md (فایل فارسی)."""
    from src.xgpedia.providers.football_data_couk import FootballDataCoUk

    api = FootballDataCoUk()
    try:
        rows, payload_hash, _ = api.fetch_season_rows(CURRENT_SEASON_START)
        sample = rows[-args.matches:]  # N بازی اخیر
        report = [
            "# آزمون پوشش football-data.co.uk",
            "",
            f"فصل: {season_label(CURRENT_SEASON_START)} · نمونه: {len(sample)} مسابقه · hash: {payload_hash[:12]}",
            "",
            "| مسابقه | xG | شوت | شوت در چارکوب | کرنر |",
            "|--------|----|------|----------------|------|",
        ]
        fields_ok = {"xg": 0, "shots": 0, "shots_on_target": 0, "corners": 0}
        for r in sample:
            has_xg = r.home_xg is not None and r.away_xg is not None
            has_shots = r.stats.get("total_shots") is not None
            has_sot = r.stats.get("shots_on_target") is not None
            has_corners = r.stats.get("corner_kicks") is not None
            fields_ok["xg"] += has_xg
            fields_ok["shots"] += has_shots
            fields_ok["shots_on_target"] += has_sot
            fields_ok["corners"] += has_corners
            report.append(
                f"| {r.date_utc} {r.home_team}-{r.away_team} "
                f"| {'+' if has_xg else 'x'} "
                f"| {'+' if has_shots else 'x'} "
                f"| {'+' if has_sot else 'x'} "
                f"| {'+' if has_corners else 'x'} |"
            )
        n = len(sample)
        report += [
            "",
            "## درصد پوشش",
            "",
            f"- xG: {fields_ok['xg']}/{n} ({fields_ok['xg'] / n:.0%})",
            f"- شوت: {fields_ok['shots']}/{n} ({fields_ok['shots'] / n:.0%})",
            f"- شوت در چارکوب: {fields_ok['shots_on_target']}/{n} ({fields_ok['shots_on_target'] / n:.0%})",
            f"- کرنر: {fields_ok['corners']}/{n} ({fields_ok['corners'] / n:.0%})",
            "",
            "منبع دوم: football-data.org — بازی‌های پیش‌رو و جدول (بدون xG، طبق طراحی سرویس).",
        ]
        out = ROOT / "docs" / "provider-test.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text("\n".join(report), encoding="utf-8")
        print(f"OK - report saved to {out}")
        print(
            f"coverage: xG {fields_ok['xg']}/{n}, shots {fields_ok['shots']}/{n}, "
            f"on-target {fields_ok['shots_on_target']}/{n}, corners {fields_ok['corners']}/{n}"
        )
    finally:
        api.close()


def cmd_list_fixtures(args: argparse.Namespace) -> None:
    """فهرست fixture_idهای ذخیره‌شده — برای انتخاب آرگومان دستور facts.

    جایگزین sqlite3 CLI که روی ویندوز به‌صورت پیش‌فرض نیست.
    """
    from src.xgpedia.db import db

    with db() as conn:
        rows = conn.execute(
            """
            SELECT fixture_id, kickoff_utc, home_team, away_team, status
            FROM fixtures
            ORDER BY kickoff_utc DESC, home_team
            LIMIT ?
            """,
            (args.limit,),
        ).fetchall()
    if not rows:
        print("No fixtures in DB yet - run first: python run.py sync-results")
        return
    for r in rows:
        mark = "F" if r["status"] == "finished" else "U"
        print(f"  [{mark}] {r['fixture_id']}  ({r['kickoff_utc']})")
    print(f"- {len(rows)} fixtures (F=finished, U=upcoming; raise the limit with --limit)")


def cmd_draft(args: argparse.Namespace) -> None:
    """تولید پیش‌نویس با LLM + عبور از هفت دروازهٔ validator + ذخیره در posts."""
    from src.xgpedia.editorial.draft import generate_draft, save_draft
    from src.xgpedia.editorial.llm_provider import OpenAICompatibleLLM
    from src.xgpedia.sync import build_match_facts

    try:
        llm = OpenAICompatibleLLM()
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(2)

    init_db()  # مهاجرت idempotent (ستون draft_json برای DBهای نسخهٔ قبل)
    facts = build_match_facts(args.fixture)
    print(f"fixture: {facts['fixture_id']}")
    print(f"generating {args.post_type} for {args.platform} with {llm.model} ...")
    try:
        draft, rep, n_attempts = generate_draft(
            llm, facts, post_type=args.post_type, target_platform=args.platform
        )
    except Exception as e:
        print(f"[REJECTED] draft did not pass the 7 gates after 2 attempts")
        print(str(e)[:1500])
        sys.exit(1)

    post_id = save_draft(draft, facts=MatchFacts_from_dict(facts),
                         post_type=args.post_type, target_platform=args.platform)
    print(f"OK - post_id {post_id} (validated, attempt {n_attempts})")
    print(f"  title: {draft.title}")
    for b in draft.bullets:
        print(f"  - {b}")
    print(f"  caption: {draft.caption}")
    if draft.uncertainties:
        print(f"  uncertainties: {'; '.join(draft.uncertainties)}")
    print(f"  source_note: {draft.source_note}")
    print(f"  full JSON: python run.py show-post --post-id {post_id}")


def MatchFacts_from_dict(facts: dict):
    from src.xgpedia.normalization.models import MatchFacts

    return MatchFacts.model_validate(facts)


def cmd_list_posts(_: argparse.Namespace) -> None:
    """فهرست پست‌های ذخیره‌شده در posts — با وضعیت و نسخه."""
    from src.xgpedia.db import db

    with db() as conn:
        rows = conn.execute(
            """
            SELECT post_id, fixture_id, post_type, target_platform, content_version,
                   status, title, created_at
            FROM posts ORDER BY post_id DESC LIMIT 20
            """
        ).fetchall()
    if not rows:
        print("No posts yet - run: python run.py draft --fixture <id>")
        return
    for r in rows:
        print(
            f"  [{r['post_id']}] {r['status']:<10} v{r['content_version']} "
            f"{r['post_type']}/{r['target_platform']}  {r['title'] or '(no title)'}"
        )
        print(f"        fixture: {r['fixture_id']}  ({r['created_at']})")
    print(f"- {len(rows)} posts (latest 20)")


def cmd_show_post(args: argparse.Namespace) -> None:
    """نمایش کامل یک پست — draft_json + fact_json (ensure_ascii برای ترمینال)."""
    from src.xgpedia.db import db

    with db() as conn:
        r = conn.execute("SELECT * FROM posts WHERE post_id = ?", (args.post_id,)).fetchone()
    if r is None:
        print(f"No post with post_id {args.post_id} - run: python run.py list-posts")
        return
    print(f"post_id: {r['post_id']}")
    print(f"fixture: {r['fixture_id']}")
    print(f"type/platform: {r['post_type']} / {r['target_platform']}  v{r['content_version']}")
    print(f"status: {r['status']}   created: {r['created_at']}")
    print("draft_json:")
    print(r["draft_json"] or "(none)")
    print("fact_json:")
    print((r["fact_json"] or "")[:600] + ("..." if r["fact_json"] and len(r["fact_json"]) > 600 else ""))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="xgpedia",
        description="XGPedia data pipeline - v8 (numbers come from APIs, never from model memory)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create the SQLite database")

    p_sync = sub.add_parser("sync-results", help="download results + xG CSV into DB")
    p_sync.add_argument("--season", type=int, default=CURRENT_SEASON_START,
                        help="season start year (e.g. 2026 = current 2026-27, 2025 = previous)")

    p_fix = sub.add_parser("fixtures", help="upcoming fixtures (needs football-data.org token)")
    p_fix.add_argument("--days", type=int, default=7)

    p_facts = sub.add_parser("facts", help="build the facts JSON for one fixture")
    p_facts.add_argument("--fixture", required=True)
    p_facts.add_argument("--out", default=None, help="optional output path for the JSON file")

    sub.add_parser("status", help="data freshness + DB stats")

    p_list = sub.add_parser("list-fixtures", help="list fixture IDs stored in DB (for facts)")
    p_list.add_argument("--limit", type=int, default=20)

    p_test = sub.add_parser("test-provider", help="provider field coverage test")
    p_test.add_argument("--matches", type=int, default=5)

    p_draft = sub.add_parser("draft", help="generate + validate a post draft with LLM")
    p_draft.add_argument("--fixture", required=True)
    p_draft.add_argument("--platform", default="telegram", choices=["telegram", "instagram", "website", "tiktok"])
    p_draft.add_argument("--post-type", default="preview", choices=["preview", "post_match", "number_of_day"])

    sub.add_parser("list-posts", help="list saved posts (drafts)")

    p_show = sub.add_parser("show-post", help="show one post in full")
    p_show.add_argument("--post-id", type=int, required=True)

    args = parser.parse_args(argv)
    if args.cmd == "init":
        init_db()
        print("OK - database created (data/dev.sqlite)")
    elif args.cmd == "sync-results":
        cmd_sync_results(args)
    elif args.cmd == "fixtures":
        cmd_fixtures(args)
    elif args.cmd == "facts":
        cmd_facts(args)
    elif args.cmd == "status":
        cmd_status(args)
    elif args.cmd == "list-fixtures":
        cmd_list_fixtures(args)
    elif args.cmd == "test-provider":
        cmd_test_provider(args)
    elif args.cmd == "draft":
        cmd_draft(args)
    elif args.cmd == "list-posts":
        cmd_list_posts(args)
    elif args.cmd == "show-post":
        cmd_show_post(args)
    else:
        parser.error("unknown command")
    return 0


if __name__ == "__main__":
    sys.exit(main())
