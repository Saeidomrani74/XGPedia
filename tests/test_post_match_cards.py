"""آزمون‌های کارت پس‌ازبازی — موتور قالب استودیویی (`studio_templates/post_match.html`).

اجرا:  python -m pytest tests/test_post_match_cards.py -v
پوشش:
  - build_match_facts(post_match=True): نتیجه + آمار خودِ بازی + خطای بازی ناتمام
  - ترتیب اولویت ماژول‌های پس‌ازبازی (xgrace → shotmap → momentum → efficiency → toprated → motm → stats)
  - انتقال «روایت آماری و گره تاکتیکی بازی» (autopsy) به کپشن و عدم نمایش آن روی کارت
  - null≠0: بدون مالکیت/موقعیت بزرگ/دروازه‌بان واقعی، دادهٔ جعلی تولید نمی‌شود
  - سازوکار پوشهٔ `studio_templates/post_match.html` و خروجی خودبسنده
  - رندر واقعی Playwright (در صورت نصب)
"""
from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

import pytest

from src.xgpedia.render.post_match_cards import (
    build_post_match_context,
    render_post_match_card,
    render_post_match_html,
)
from src.xgpedia.render.studio_engine import (
    POST_MATCH_CAPTION_ONLY,
    POST_MATCH_PRIORITY,
    STUDIO_TEMPLATES_DIR,
)

PROVIDER = "football-data-co-uk"


def _stat(v: float | None) -> dict | None:
    return {"value": v, "n": 1, "provider": PROVIDER} if v is not None else None


def _facts(**overrides) -> dict:
    """فکت‌های واقعی پس‌ازبازی — همان ساختار build_match_facts(post_match=True)."""
    base = {
        "fixture_id": f"{PROVIDER}:2026-11-08:Sunderland:Chelsea",
        "competition": {"name": "Premier League", "season": "2026-27"},
        "kickoff_utc": "2026-11-08T16:30:00Z",
        "source": {"provider": PROVIDER, "collected_at": "2026-11-17T04:00:06Z",
                   "payload_hash": "abc123"},
        "result": {"home_goals": 1, "away_goals": 0},
        "home": {
            "name_fa": "ساندرلند", "name_en": "Sunderland",
            "xg_series": [1.2, 0.8, 1.6, 0.9, 1.4, 1.1, 1.8, 1.0, 1.3, 2.38],
            "match_stats": {
                "goals": _stat(1), "expected_goals": _stat(2.38), "total_shots": _stat(9),
                "shots_on_target": _stat(2), "corner_kicks": _stat(2), "fouls": _stat(17),
                "yellow_cards": _stat(5), "red_cards": _stat(0),
            },
        },
        "away": {
            "name_fa": "چلسی", "name_en": "Chelsea",
            "xg_series": [1.9, 1.5, 2.1, 1.2, 1.7, 1.4, 1.6, 1.9, 1.1, 0.66],
            "match_stats": {
                "goals": _stat(0), "expected_goals": _stat(0.66), "total_shots": _stat(10),
                "shots_on_target": _stat(4), "corner_kicks": _stat(2), "fouls": _stat(8),
                "yellow_cards": _stat(4), "red_cards": _stat(0),
            },
        },
        "data_quality": {"missing_fields": []},
    }
    base.update(overrides)
    return base


def _draft(**overrides) -> dict:
    base = {
        "status": "ok",
        "title": "ساندرلند برتری آماری‌اش را کامل کرد",
        "bullets": [
            "ساندرلند با ۲.۳۸ امید گل بهترین عملکرد فصلش را ثبت کرد.",
            "چلسی با وجود ۱۰ شوت، فقط ۰.۶۶ xG ساخت.",
        ],
        "caption": "ساندرلند ۱-۰ چلسی؛ عدالت آماری کامل.",
        "source_note": "deterministic-sample",
    }
    base.update(overrides)
    return base


# ─── لایهٔ داده: build_match_facts(post_match=True) ───

SCHEMA = """
CREATE TABLE fixtures (
  fixture_id TEXT PRIMARY KEY, provider TEXT NOT NULL, competition TEXT NOT NULL,
  season TEXT NOT NULL, kickoff_utc TEXT NOT NULL, home_team TEXT NOT NULL,
  away_team TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'scheduled',
  raw_payload_hash TEXT, collected_at TEXT NOT NULL
);
CREATE TABLE fixture_statistics (
  fixture_id TEXT NOT NULL, team TEXT NOT NULL, metric TEXT NOT NULL,
  value REAL, n INTEGER, provider TEXT NOT NULL, collected_at TEXT NOT NULL,
  PRIMARY KEY (fixture_id, team, metric, provider)
);
"""


@pytest.fixture()
def pm_conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    rows = [
        ("f-prev", "2026-10-30", "Sunderland", "Everton", "finished",
         [("Sunderland", "expected_goals", 1.1), ("Everton", "expected_goals", 0.8),
          ("Sunderland", "goals", 1), ("Everton", "goals", 1)]),
        ("f-now", "2026-11-08", "Sunderland", "Chelsea", "finished",
         [("Sunderland", "expected_goals", 2.38), ("Chelsea", "expected_goals", 0.66),
          ("Sunderland", "goals", 1), ("Chelsea", "goals", 0),
          ("Sunderland", "total_shots", 9), ("Chelsea", "total_shots", 10),
          ("Sunderland", "shots_on_target", 2), ("Chelsea", "shots_on_target", 4)]),
        ("f-future", "2026-11-22", "Chelsea", "Arsenal", "scheduled", []),
    ]
    for fid, kickoff, home, away, status, stats in rows:
        c.execute("INSERT INTO fixtures VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (fid, PROVIDER, "Premier League", "2026-27", kickoff, home, away,
                   status, None, "2026-11-17T00:00:00Z"))
        for team, metric, value in stats:
            c.execute("INSERT INTO fixture_statistics VALUES (?,?,?,?,?,?,?)",
                      (fid, team, metric, value, None, PROVIDER, "2026-11-17T00:00:00Z"))
    yield c
    c.close()


@contextlib.contextmanager
def _fake_db(conn: sqlite3.Connection):
    yield conn


def test_post_match_facts_from_db(pm_conn, monkeypatch):
    from src.xgpedia import sync as sync_mod
    from src.xgpedia.sync import build_match_facts

    monkeypatch.setattr(sync_mod, "db", lambda: _fake_db(pm_conn))
    f = build_match_facts("f-now", post_match=True)

    assert f["result"] == {"home_goals": 1, "away_goals": 0}
    ms = f["home"]["match_stats"]
    assert ms["expected_goals"]["value"] == 2.38
    assert ms["total_shots"]["value"] == 9
    assert ms["goals"]["value"] == 1.0
    assert f["home"]["xg_series"][-1] == 2.38
    assert f["away"]["xg_series"][-1] == 0.66
    assert f["home"]["match_stats"]["corner_kicks"] is None


def test_post_match_facts_rejects_unfinished(pm_conn, monkeypatch):
    from src.xgpedia import sync as sync_mod
    from src.xgpedia.sync import build_match_facts

    monkeypatch.setattr(sync_mod, "db", lambda: _fake_db(pm_conn))
    with pytest.raises(ValueError, match="finished"):
        build_match_facts("f-future", post_match=True)


# ─── ترتیب اولویت ماژول‌های پس‌ازبازی و انتقال autopsy به کپشن ───

def test_post_match_priority_order_constant():
    assert POST_MATCH_PRIORITY == [
        "xgrace", "shotmap", "momentum", "efficiency", "toprated", "motm", "stats",
    ]
    assert POST_MATCH_CAPTION_ONLY == {"autopsy"}


def test_post_match_context_with_current_real_data():
    """با دیتای واقعی فعلی فقط ماژول stats داده کامل دارد؛ autopsy به کپشن می‌رود."""
    ctx = build_post_match_context(_draft(), _facts())
    assert ctx["score"] == {"home": 1, "away": 0}
    cap = ctx["capsule"]
    assert cap is not None
    assert sum(s["pct"] for s in cap) == 100
    assert ctx["hero"]["delta_home"] == "-1.38"
    assert ctx["hero"]["delta_away"] == "-0.66"

    # فقط ماژول‌های دارای دیتای کامل روشن‌اند
    assert [m["id"] for m in ctx["modules"] if m["enabled"]] == ["stats"]
    assert len(ctx["module_data"]["stats"]["rows"]) == 4
    # هیچ ردیف جعلی مالکیت (0٪) در statsRows نیست
    labels = [r["label"] for r in ctx["module_data"]["stats"]["rows"]]
    assert "مالکیت توپ (٪)" not in labels
    assert labels == ["شوت کل (در چارچوب)", "کیفیت هر شوت (xG/شوت)", "کرنر", "خطا"]


def test_post_match_autopsy_never_on_card_and_always_in_caption():
    """روایت آماری و گره تاکتیکی بازی روی کارت نیست و در کپشن قرار می‌گیرد."""
    ctx = build_post_match_context(_draft(), _facts())
    assert ctx["has"]["autopsy"] is False
    assert "autopsy" not in [m["id"] for m in ctx["modules"]]
    assert "روایت آماری و گره تاکتیکی بازی" in ctx["caption_text"]
    assert "ساندرلند برتری آماری‌اش را کامل کرد" in ctx["caption_text"]
    assert ctx["caption_text"].endswith("#پس_از_بازی")


def test_post_match_full_priority_when_all_data_available():
    """با کامل‌بودن داده‌های رویدادی/بازیکن، اولویت ۱ تا ۷ دقیقاً رعایت می‌شود."""
    facts = _facts(
        momentum=[30, 45, -20, 15, 50, -35, 25, 40],
        topPlayers=[{"name": "ساکا", "side": "home", "stat": "۱ گل", "rating": 8.8}],
        motm={
            "side": "home", "name": "ساکا", "pos": "وینگر", "number": 7, "rating": 8.8,
            "chips": [{"label": "گل", "val": "۱"}],
            "runnerUp": {"side": "away", "name": "پالمر", "stat": "۴ شوت", "rating": 7.9},
        },
    )
    facts["home"]["shotList"] = [[88, 52, 0.42, "goal", "مهاجم", 22]]
    facts["away"]["shotList"] = [[82, 44, 0.18, "sot", "هافبک", 55]]
    facts["home"]["insideBox"] = 7
    facts["away"]["insideBox"] = 4
    facts["home"]["gk"] = {"name": "دروازه‌بان ۱", "saves": 4, "psxg": 1.2, "ga": 0}
    facts["away"]["gk"] = {"name": "دروازه‌بان ۲", "saves": 3, "psxg": 1.8, "ga": 1}

    ctx45 = build_post_match_context(_draft(), facts, fmt="4:5")
    assert [(m["id"], m["span"]) for m in ctx45["modules"]] == [
        ("momentum", "half"), ("stats", "half"), ("toprated", "half"), ("efficiency", "half")
    ]

    ctx916 = build_post_match_context(_draft(), facts, fmt="9:16")
    assert [(m["id"], m["span"]) for m in ctx916["modules"]] == [
        ("momentum", "half"), ("stats", "half"), ("toprated", "half"), ("efficiency", "half")
    ]


def test_post_match_missing_metric_drops_row():
    facts = _facts()
    for m in ("corner_kicks", "fouls", "yellow_cards", "red_cards", "shots_on_target"):
        del facts["home"]["match_stats"][m]
        del facts["away"]["match_stats"][m]
    ctx = build_post_match_context(_draft(), facts)
    labels = [r["label"] for r in ctx["module_data"]["stats"]["rows"]]
    assert labels == ["شوت کل (در چارچوب)", "کیفیت هر شوت (xG/شوت)"]


def test_post_match_studio_template_renders_exact_design(tmp_path: Path):
    assert (STUDIO_TEMPLATES_DIR / "post_match.html").exists()
    html = render_post_match_html(_draft(), _facts(), fmt="4:5")
    assert 'id="xgpedia-unified"' in html
    assert "width:1080px;height:1350px;" in html
    assert "cdn.tailwindcss.com" not in html
    assert "fonts.googleapis.com" not in html

    # تست جایگذاری فایل اختصاصی در پوشهٔ قالب‌ها
    src = (STUDIO_TEMPLATES_DIR / "post_match.html").read_text(encoding="utf-8")
    marker = "<!-- CUSTOM_POST_MATCH_STUDIO -->"
    (tmp_path / "post_match.html").write_text(marker + "\n" + src, encoding="utf-8")
    html_custom = render_post_match_html(_draft(), _facts(), template_dir=tmp_path)
    assert marker in html_custom


def test_render_post_match_real_png(tmp_path):
    pytest.importorskip("playwright", reason="playwright not installed")
    _html, img_path, cap_path = render_post_match_card(
        _draft(), _facts(), out_dir=tmp_path, post_id=9, version=1, platform="telegram",
    )
    assert img_path.name == "post_9_v1_post_match_1080x1350.png"
    cap_txt = cap_path.read_text(encoding="utf-8")
    assert "#پس_از_بازی" in cap_txt
    assert "روایت آماری و گره تاکتیکی بازی" in cap_txt
