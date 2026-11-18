"""آزمون‌های کارت پس‌از‌بازی (post_match) — تم Warm Terracotta عین استودیوی post-match.html.

اجرا:  python -m pytest tests/test_post_match_cards.py -v
پوشش:
  - build_match_facts(post_match=True): نتیجه + آمار خودِ بازی + روند شامل همین بازی + خطای بازی ناتمام
  - context: نتیجه، احتمال‌های ۱X۲ فقط از xG خودِ بازی (Dixon-Coles)، دلتای بهره‌وری گل
  - ماژول‌ها: smart فضاآگاه (پرکردن grid تا ظرفیت فرمت)؛ متریک غایب → ردیف/ماژول حذف
  - تم: همهٔ رنگ‌ها از brand.json (postmatch_palette) — هیچ هگز هاردکد در قالب
  - کمترین داده: بدون سری/بولت → کپشن، ماژول یتیم تمام‌عرض، کارت همچنان پر
  - رندر واقعی Playwright → PNG سالم و غیرخالی
"""
from __future__ import annotations

import contextlib
import re
import sqlite3

import pytest

RENDER_DEPS = pytest.importorskip("jinja2", reason="render extras not installed")
pytest.importorskip("jdatetime", reason="render extras not installed")

from src.xgpedia.config import load_brand, load_team_identities
from src.xgpedia.render.post_match_cards import (
    build_post_match_context,
    render_post_match_card,
    render_post_match_html,
)

PROVIDER = "football-data-co-uk"


def _stat(v: float | None) -> dict | None:
    return {"value": v, "n": 1, "provider": PROVIDER} if v is not None else None


def _facts(**overrides) -> dict:
    """فکت‌های پس‌از‌بازی — همان ساختار build_match_facts(post_match=True)."""
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
        "title": "ساندرلند موفقیت سنگینش را کامل کرد",
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
        # (fid, kickoff, home, away, status, stats[(team, metric, value)])
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
    # روند شامل همین بازی: آخرین عضو سری = xG خودِ بازی
    assert f["home"]["xg_series"][-1] == 2.38
    assert f["away"]["xg_series"][-1] == 0.66
    # متریک غایب → مقدار None می‌ماند (null≠0؛ رندرر ردیفش را نمی‌سازد)
    assert f["home"]["match_stats"]["corner_kicks"] is None


def test_post_match_facts_rejects_unfinished(pm_conn, monkeypatch):
    from src.xgpedia import sync as sync_mod
    from src.xgpedia.sync import build_match_facts

    monkeypatch.setattr(sync_mod, "db", lambda: _fake_db(pm_conn))
    with pytest.raises(ValueError, match="finished"):
        build_match_facts("f-future", post_match=True)


# ─── context کارت ───

def test_post_match_context_score_probs_and_modules():
    ctx = build_post_match_context(_draft(), _facts())
    assert ctx["score"] == {"home": 1, "away": 0}
    # احتمال‌ها فقط از xG خودِ بازی (Dixon-Coles): 2.38 vs 0.66 → برتری قاطع میزبان
    cap = ctx["capsule"]
    assert cap is not None
    pcts = [s["pct"] for s in cap]
    assert sum(pcts) == 100
    assert pcts[0] > pcts[1] > 10  # میزبان بالاتر از میهمان
    # دلتای بهره‌وری گل: 1 - 2.38 = -1.38
    assert ctx["hero"]["delta_home"] == "-1.38"
    assert ctx["hero"]["delta_away"] == "-0.66"
    # smart 4:5: stats + دو نیم‌عرض (story, trend10) + verdict
    ids = [m["id"] for m in ctx["modules"] if m["enabled"]]
    assert ids == ["stats", "trend10", "story", "verdict"]
    # همهٔ ۶ متریک مشترک → ۶ ردیف آمار
    assert len(ctx["module_data"]["stats"]["rows"]) == 6
    # verdict: برتری کیفی ساندرلند (فاصلهٔ ۱.۷۲ xG)
    assert "ساندرلند" in ctx["module_data"]["verdict"]["fair_title"]


def test_post_match_context_minimal_data_fills():
    """کمترین داده: بدون سری و بدون بولت — story از کپشن، trend10 خاموش، یتیم تمام‌عرض."""
    facts = _facts()
    for side in ("home", "away"):
        facts[side]["xg_series"] = None
    ctx = build_post_match_context(_draft(bullets=[]), facts)
    ids = [m["id"] for m in ctx["modules"] if m["enabled"]]
    # story (از کپشن) + shotquality جانشین trend10 می‌شوند؛ grid همچنان پر
    assert ids == ["stats", "story", "shotquality", "verdict"]
    assert ctx["module_data"]["story"]["body_lines"] == [_draft(bullets=[])["caption"]]


def test_post_match_missing_metric_drops_row():
    facts = _facts()
    for m in ("corner_kicks", "fouls", "yellow_cards", "red_cards", "shots_on_target"):
        del facts["home"]["match_stats"][m]
        del facts["away"]["match_stats"][m]
    ctx = build_post_match_context(_draft(), facts)
    labels = [r["label"] for r in ctx["module_data"]["stats"]["rows"]]
    assert labels == ["امید گل واقعی (xG)", "شوت کل (در چارچوب)"]


def test_post_match_theme_colors_from_brand_json():
    brand = load_brand()
    pal = brand["postmatch_palette"]
    ctx = build_post_match_context(_draft(), _facts())
    assert ctx["t"]["board_bg"] == pal["board_bg"]
    assert ctx["t"]["accent"] == pal["accent"]
    html = render_post_match_html(_draft(), _facts())
    assert pal["board_bg"] in html
    assert pal["accent"] in html
    assert 'dir="rtl"' in html
    # لوگوی رسمی برند در سرصفحه (data-URI)
    assert "brand-logo-img" in html


def test_post_match_html_no_hardcoded_hex():
    """داخل <style> فقط رنگ‌های brand.json (postmatch + colors) و هویت تیم‌ها."""
    html = render_post_match_html(_draft(), _facts())
    style_part = html.split("<style>")[1].split("</style>")[0]
    hexes = set(re.findall(r"#[0-9A-Fa-f]{6}\b", style_part))
    allowed = set(load_brand()["postmatch_palette"].values())
    allowed |= set(load_brand()["colors"].values())
    allowed |= set(load_brand()["matchday_palette"].values())
    for ident in load_team_identities()["teams"].values():
        for c in (ident.get("colors") or {}).values():
            if isinstance(c, str) and c.startswith("#"):
                allowed.add(c)
    assert hexes <= allowed, hexes - allowed


def test_post_match_latin_digits_for_stats():
    """ارقام آماری لاتین (D16) — xG با ممیز لاتین؛ تاریخ فارسی جدا."""
    html = render_post_match_html(_draft(), _facts())
    assert ">2.38<" in html or "2.38" in html
    assert "۰-۰" not in html  # نتیجه با ارقام لاتین


def test_render_post_match_real_png(tmp_path):
    pytest.importorskip("playwright", reason="playwright not installed")
    _html, img_path, cap_path = render_post_match_card(
        _draft(), _facts(), out_dir=tmp_path, post_id=9, version=1, platform="telegram",
    )
    assert img_path.name == "post_9_v1_post_match_1080x1350.png"
    assert "#پس_از_بازی" in cap_path.read_text(encoding="utf-8")
    try:
        from PIL import Image
    except ImportError:
        return
    with Image.open(img_path) as im:
        assert im.size == (1080, 1350)
        g = im.convert("L")
        h = g.histogram()
        non_white = 1 - h[255] / sum(h)
        assert non_white > 0.3  # کارت روشن (خاکی) — نباید سفید خالی باشد
