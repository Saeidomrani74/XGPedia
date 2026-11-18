"""Make a SAMPLE post_match post from real DB facts - for render testing without LLM keys.

Usage (project root):
    python tools/make_sample_postmatch.py --fixture "fdcouk:2026-11-08:Sunderland:Chelsea"
    python run.py render-post --post-id <id>

The draft text is deterministic and every number in it comes from the real fact_json
built by sync.build_match_facts(post_match=True). The post is saved with
status='draft' (NOT validated) - real editorial text still comes from `run.py draft`.
Idempotent: re-running updates the existing sample post instead of inserting a new one.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.xgpedia.db import db, init_db
from src.xgpedia.sync import build_match_facts


def main() -> int:
    ap = argparse.ArgumentParser(description="sample post_match post from real facts")
    ap.add_argument("--fixture", required=True, help="finished fixture_id (see run.py list-fixtures)")
    ap.add_argument("--platform", default="telegram")
    args = ap.parse_args()

    try:
        facts = build_match_facts(args.fixture, post_match=True)
    except (KeyError, ValueError) as e:
        print(f"[FAIL] {e}")
        return 2

    result = facts.get("result") or {}
    ms_h = (facts["home"].get("match_stats") or {})
    ms_a = (facts["away"].get("match_stats") or {})

    def v(stats: dict, key: str) -> str:
        node = stats.get(key)
        return str(node["value"]) if node and node.get("value") is not None else "N/A"

    draft = {
        "status": "sample",
        "title": "گزارش آماری پس از بازی (نمونهٔ قطعی — نه خروجی مدل)",
        "bullets": [
            (
                f"{facts['home']['name_fa']} با {v(ms_h, 'expected_goals')} امید گل در برابر "
                f"{v(ms_a, 'expected_goals')} برای {facts['away']['name_fa']}."
            ),
            (
                f"شوت‌ها: {v(ms_h, 'total_shots')} در برابر {v(ms_a, 'total_shots')}؛ "
                f"شوت در چارچوب: {v(ms_h, 'shots_on_target')} در برابر {v(ms_a, 'shots_on_target')}."
            ),
        ],
        "caption": (
            f"{facts['home']['name_fa']} {result.get('home_goals')}-{result.get('away_goals')} "
            f"{facts['away']['name_fa']} | xG: {v(ms_h, 'expected_goals')} - {v(ms_a, 'expected_goals')}"
        ),
        "source_note": "sample (deterministic) - all numbers from fact_json",
        "uncertainties": [],
    }

    init_db()
    now = datetime.now(UTC).isoformat()
    with db() as conn:
        row = conn.execute(
            "SELECT post_id, content_version FROM posts WHERE fixture_id=? AND post_type=? AND target_platform=?"
            " ORDER BY post_id DESC",
            (args.fixture, "post_match", args.platform),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE posts SET draft_json=?, fact_json=?, created_at=? WHERE post_id=?",
                (json.dumps(draft, ensure_ascii=False), json.dumps(facts, ensure_ascii=False),
                 now, row["post_id"]),
            )
            post_id, version = row["post_id"], row["content_version"]
            print(f"OK - updated post_id {post_id} (v{version})")
        else:
            conn.execute(
                """INSERT INTO posts (fixture_id, post_type, target_platform, content_version,
                   status, title, caption, draft_json, fact_json, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (args.fixture, "post_match", args.platform, 1, "draft", draft["title"],
                 draft["caption"], json.dumps(draft, ensure_ascii=False),
                 json.dumps(facts, ensure_ascii=False), now),
            )
            post_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
            print(f"OK - inserted post_id {post_id} (v1)")
    print(f"next: python run.py render-post --post-id {post_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
