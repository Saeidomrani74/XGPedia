"""تست‌های یکپارچگی دادهٔ نسخهٔ 0.60.0: نبود فرمول xG تقریبی، نبود دقیقهٔ گل جعلی و سلامت سند انتقال."""
from __future__ import annotations

from pathlib import Path

from src.xgpedia.providers import espn_free as ef


def test_no_synthetic_xg_or_fake_goal_minutes_in_codebase() -> None:
    espn_src = Path("src/xgpedia/providers/espn_free.py").read_text(encoding="utf-8")
    assert "sot * 0.31" not in espn_src
    assert ") + 0.06" not in espn_src

    mdr_src = Path("src/xgpedia/providers/matchday_results_free.py").read_text(encoding="utf-8")
    assert "18 + h_g_idx * 17" not in mdr_src
    assert "24 + a_g_idx * 19" not in mdr_src


def test_espn_timing_wave_has_no_artificial_006_offset() -> None:
    ev = {
                "competitions": [
                    {
                        "status": {"type": {"state": "post"}},
                        "competitors": [
                            {"homeAway": "home", "team": {"id": "1", "displayName": "Arsenal"}},
                            {"homeAway": "away", "team": {"id": "2", "displayName": "Chelsea"}},
                        ],
                        "details": [
                            {"scoringPlay": True, "team": {"id": "1"}, "clock": {"displayValue": "10'", "value": 600}},  # min 10 -> bucket 0
                        ],
                    }
                ]
    }
    w = ef.parse_espn_timing_wave({"events": [ev, ev]})
    assert "Arsenal" in w
    # سطل‌های بدون رویداد باید دقیقاً 0.0 باشند (نه 0.06 ساختگی)
    assert w["Arsenal"][1] == 0.0
    assert w["Arsenal"][0] > 0.0


def test_handoff_doc_exists_and_preserves_all_roadmap_phases() -> None:
    doc = Path("docs/archive/XGPEDIA_HANDOFF_V060_FA.md") if Path("docs/archive/XGPEDIA_HANDOFF_V060_FA.md").exists() else Path("docs/XGPEDIA_HANDOFF_V060_FA.md")
    assert doc.exists()
    txt = doc.read_text(encoding="utf-8")
    for must in ("فاز ۵", "فاز ۸", "فاز ۲", "فاز ۴", "Live Ticker", "v0.60.0", "data-chains"):
        assert must in txt, f"Missing {must} in handoff doc"
