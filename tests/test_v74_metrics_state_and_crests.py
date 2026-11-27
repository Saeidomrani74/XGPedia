"""تست‌های نسخه v0.74.0 — ماندگاری کامل وضعیت استودیوها، error_metrics، جدول post_metrics و fetch_crests ۱۵۱ باشگاهی."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_post_metrics_table_and_summary(tmp_path, monkeypatch) -> None:
    """جدول post_metrics باید تصمیم‌های ادمین را ثبت و نرخ تایید را محاسبه کند."""
    from src.xgpedia import db as db_mod

    test_db = tmp_path / "metrics_v74.sqlite"
    monkeypatch.setattr(db_mod, "DATABASE_PATH", test_db)
    db_mod.init_db()

    with db_mod.db() as conn:
        assert db_mod.get_schema_version(conn) >= 3

    db_mod.record_post_metric("pre_match", "approved", post_id=1, tone="analytical", render_ms=420)
    db_mod.record_post_metric("pre_match", "approved", post_id=2, tone="analytical", render_ms=380)
    db_mod.record_post_metric("pre_match", "rejected", post_id=3, tone="fan_light")
    db_mod.record_post_metric("quote", "edited", post_id=4, tone="fan_light", edit_count=2)

    summary = db_mod.get_post_metrics_summary(days=30)
    assert summary["total"] == 4
    assert summary["by_decision"]["approved"] == 2
    assert summary["by_decision"]["rejected"] == 1
    assert summary["by_card_type"]["pre_match"]["approved"] == 2
    assert summary["by_card_type"]["pre_match"]["rejected"] == 1
    assert summary["by_card_type"]["pre_match"]["approval_rate"] == 66.7
    assert summary["total_edits"] == 2


def test_studio_and_modular_state_dicts_use_persistent_sqlite_backing() -> None:
    """دیکشنری‌های وضعیت در bot_studio_* و modular_cards_bot باید از PersistentStateDict استفاده کنند."""
    otd_src = (ROOT / "src" / "xgpedia" / "publishers" / "bot_studio_otd_news.py").read_text(encoding="utf-8")
    assert 'PersistentStateDict("otd_state"' in otd_src
    assert 'PersistentStateDict("news_state"' in otd_src

    btt_src = (ROOT / "src" / "xgpedia" / "publishers" / "bot_studio_bday_transfer_tot.py").read_text(encoding="utf-8")
    for ns in ("bday_state", "tr_state", "tot_state", "awaiting_template_name"):
        assert f'PersistentStateDict("{ns}"' in btt_src

    mcb_src = (ROOT / "src" / "xgpedia" / "publishers" / "modular_cards_bot.py").read_text(encoding="utf-8")
    assert 'PersistentStateDict(f"modular_state_{k}"' in mcb_src
    assert 'PersistentStateDict("modular_picker_state"' in mcb_src


def test_error_metrics_wired_into_core_providers() -> None:
    """پروایدرهای کلیدی باید خطاهای مهارشده را در error_metrics ثبت کنند."""
    for rel in (
        "src/xgpedia/providers/xg_engine.py",
        "src/xgpedia/providers/top_scorers_free.py",
        "src/xgpedia/providers/espn_free.py",
        "src/xgpedia/editorial/llm_provider.py",
    ):
        txt = (ROOT / rel).read_text(encoding="utf-8")
        assert "error_metrics" in txt and "record_error" in txt, f"error_metrics.record_error missing in {rel}"


def test_fetch_crests_covers_151_clubs_and_detects_placeholders(tmp_path) -> None:
    """tools/fetch_crests.py باید هر ۱۵۱ باشگاه را بخواند، مونوگرام‌ها را تشخیص دهد و URL بسازد."""
    spec = importlib.util.spec_from_file_location("fetch_crests_mod", ROOT / "tools" / "fetch_crests.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # تشخیص مونوگرام کوچک در برابر لوگوی واقعی
    small_svg = tmp_path / "AJA.svg"
    small_svg.write_text("<svg>AJA</svg>", encoding="utf-8")
    big_svg = tmp_path / "ARS.svg"
    big_svg.write_text("<svg>" + ("x" * 2500) + "</svg>", encoding="utf-8")
    assert mod.is_placeholder_crest(small_svg) is True
    assert mod.is_placeholder_crest(big_svg) is False

    # تولید کاندیدای football-data.org و ESPN برای باشگاه غیرانگلیسی
    mapping = json.loads((ROOT / "config" / "team_mapping.json").read_text(encoding="utf-8"))["teams"]
    assert len(mapping) == 151
    rm_entry = mapping["Real Madrid"]
    cands = mod.build_candidate_urls("Real Madrid", team_map_entry=rm_entry, espn_index={"real madrid": "https://a.espncdn.com/rm.png"})
    urls = [u for _, u in cands]
    assert any("crests.football-data.org/" in u and u.endswith(".svg") for u in urls)
    assert "https://a.espncdn.com/rm.png" in urls


def test_fetch_crests_thesportsdb_filters_soccer_only() -> None:
    """قانون دائمی Association Football Only: استخراج strBadge باید فقط strSport == Soccer را بپذیرد."""
    spec = importlib.util.spec_from_file_location("fetch_crests_mod2", ROOT / "tools" / "fetch_crests.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    payload = {
        "teams": [
            {"strTeam": "Olympiacos BC", "strSport": "Basketball", "strBadge": "https://example.com/bball.png"},
            {"strTeam": "Olympiacos", "strSport": "Soccer", "strBadge": "https://example.com/oly_soccer.png"},
        ]
    }
    assert mod._extract_thesportsdb_soccer_badge(payload) == "https://example.com/oly_soccer.png"
    assert mod._extract_thesportsdb_soccer_badge({"teams": [{"strSport": "American Football", "strBadge": "https://x/nfl.png"}]}) is None
