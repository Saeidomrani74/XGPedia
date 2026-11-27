"""تست‌های رگرسیون جامع فاز صفر (v0.72.0 — ممیزی و رفع باگ کلی XGPedia)."""
from __future__ import annotations

import ast
import json
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_no_leaked_session_files_in_repo_root() -> None:
    """نباید هیچ فایل نشست یا توکن لو‌رفته در ریشهٔ پروژه وجود داشته باشد."""
    assert not list(ROOT.glob("*session*.json"))
    assert not (ROOT / "__nonexistent_test_ig_session__.json").exists()
    assert not (ROOT / "src" / "xgpedia" / "render" / "sync.py").exists()


def test_run_py_defines_ok_and_fail_cleanly() -> None:
    """OK و FAIL در run.py باید تعریف شده باشند و براکت تکراری نسازند."""
    import run as run_mod

    assert run_mod.OK == "OK"
    assert run_mod.FAIL == "FAIL"


def test_telegram_bot_and_breaking_news_no_undefined_names() -> None:
    """بررسی استاتیک نبود باگ‌های NameError قبلی در telegram_bot.py و breaking_news_free.py."""
    tb_src = (ROOT / "src" / "xgpedia" / "publishers" / "telegram_bot.py").read_text(encoding="utf-8")
    assert "logger.warning(" not in tb_src
    assert "await _tb_rep.stop_heartbeat()\n        if not res.ok:" not in tb_src
    assert 'match_lbl = f"{st[\'home_fa\']} × {st[\'away_fa\']}"' in tb_src
    assert "from pathlib import Path" in tb_src.splitlines()[:25]

    bn_src = (ROOT / "src" / "xgpedia" / "providers" / "breaking_news_free.py").read_text(encoding="utf-8")
    assert "_clean_text(" not in bn_src
    assert "_clean_html_text(raw_p)" in bn_src


def test_sofascore_feature_flag_preserved_default_off(monkeypatch) -> None:
    """قانون دائمی v0.71.0: SofaScore باید به‌صورت پیش‌فرض خاموش بماند."""
    from src.xgpedia.providers.xg_engine import is_sofascore_enabled

    monkeypatch.delenv("XGPEDIA_ENABLE_SOFASCORE", raising=False)
    assert is_sofascore_enabled() is False
    monkeypatch.setenv("XGPEDIA_ENABLE_SOFASCORE", "1")
    assert is_sofascore_enabled() is True


def test_llm_anonymous_fallback_disabled_by_default(monkeypatch) -> None:
    """در v0.72.0 مسیرهای ناشناس LLM باید به‌صورت پیش‌فرض غیرفعال باشند."""
    from src.xgpedia.editorial.llm_provider import build_free_llm_chain_from_env

    for k in (
        "LLM_ENABLE_ANONYMOUS_FALLBACK",
        "LLM_API_KEY",
        "GROQ_API_KEY",
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "MISTRAL_API_KEY",
        "CEREBRAS_API_KEY",
        "SAMBANOVA_API_KEY",
        "COHERE_API_KEY",
        "GITHUB_TOKEN",
        "NVIDIA_API_KEY",
        "CLOUDFLARE_API_TOKEN",
        "ZAI_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)

    chain_default = build_free_llm_chain_from_env()
    assert not any("OVHcloud Free" in ep.label or "Kilo Code Free" in ep.label for ep in chain_default)

    monkeypatch.setenv("LLM_ENABLE_ANONYMOUS_FALLBACK", "1")
    chain_enabled = build_free_llm_chain_from_env()
    assert any("OVHcloud Free" in ep.label for ep in chain_enabled)


def test_db_pragmas_and_schema_version(tmp_path, monkeypatch) -> None:
    """db() باید foreign_keys=ON، busy_timeout و user_version را تنظیم کند."""
    from src.xgpedia import db as db_mod

    test_db = tmp_path / "test_v72.sqlite"
    monkeypatch.setattr(db_mod, "DATABASE_PATH", test_db)
    db_mod.init_db()

    with db_mod.db() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 30000
        assert db_mod.get_schema_version(conn) >= db_mod.SCHEMA_VERSION
        enr_cols = {r["name"] for r in conn.execute("PRAGMA table_info(team_enrichments)")}
        assert "wave_json" in enr_cols


def test_151_clubs_exact_1to1_symmetry() -> None:
    """تقارن ۱۰۰٪ ۱:۱ هر ۱۵۱ باشگاه در identities، mapping و venues."""
    ti = json.loads((ROOT / "config" / "team_identities.json").read_text(encoding="utf-8"))["teams"]
    tm = json.loads((ROOT / "config" / "team_mapping.json").read_text(encoding="utf-8"))["teams"]
    tv = json.loads((ROOT / "config" / "team_venues.json").read_text(encoding="utf-8"))["teams"]

    assert len(ti) == 151
    assert set(ti.keys()) == set(tm.keys()) == set(tv.keys())

    from src.xgpedia.config import canonical_team_name, team_venue

    for short_name, full_name in (
        ("Coventry", "Coventry City"),
        ("Hull", "Hull City"),
        ("Ipswich", "Ipswich Town"),
        ("Leeds", "Leeds United"),
        ("Newcastle", "Newcastle United"),
    ):
        assert canonical_team_name(short_name) == full_name
        assert canonical_team_name(full_name) == full_name
        assert team_venue(short_name).get("stadium_fa")


def test_validator_catches_home_null_insufficient_data_and_unknown_role_entity() -> None:
    """ولیدیتور باید تحریف null میزبان، insufficient_data با متن، و نام ناشناخته را رد کند."""
    from src.xgpedia.editorial.llm_provider import DraftOutput
    from src.xgpedia.editorial.validate import validate
    from src.xgpedia.normalization.models import Last5, MatchFacts, SourceInfo, StatValue, TeamSide

    m = MatchFacts(
        fixture_id="test:1",
        competition={"name": "Premier League", "season": "2026-27"},
        kickoff_utc="2026-11-14T17:30:00Z",
        source=SourceInfo(provider="test", collected_at="2026-11-13T09:00:00Z"),
        home=TeamSide(
            name_fa="آرسنال",
            name_en="Arsenal",
            last5=Last5(n=5, points=10, goals_for=9, goals_against=4),
            xg_for_avg=None,
            corners_avg=None,
        ),
        away=TeamSide(
            name_fa="چلسی",
            name_en="Chelsea",
            last5=Last5(n=5, points=7, goals_for=6, goals_against=6),
            xg_for_avg=StatValue(value=1.4, n=5),
            corners_avg=StatValue(value=5.4, n=5),
        ),
    )

    # ۱) تحریف null میزبان
    d_home_null = DraftOutput(
        status="ok",
        title="آرسنال در خانه",
        bullets=["آرسنال ۱۰ امتیاز از ۵ بازی اخیر"],
        caption="امید گل آرسنال صفر است.",
        source_note="test",
        uncertainties=[],
    )
    rep1 = validate(d_home_null, m, set())
    assert not rep1.passed
    assert any("null_to_zero" in f for f in rep1.failures)

    # ۲) insufficient_data نباید متن عمومی داشته باشد
    d_insuff = DraftOutput(
        status="insufficient_data",
        title="پیش‌بازی آرسنال",
        bullets=[],
        caption="",
        source_note="",
        uncertainties=[],
    )
    rep2 = validate(d_insuff, m, set())
    assert not rep2.passed
    assert any("insufficient_data" in f for f in rep2.failures)

    # ۳) نام ساختگی پس از نقش فوتبالی باید رد شود
    d_fake_ent = DraftOutput(
        status="ok",
        title="آرسنال آماده است",
        bullets=["آرسنال ۱۰ امتیاز از ۵ بازی اخیر"],
        caption="مهاجم فرضی ساختگی‌زاده امشب گل می‌زند.",
        source_note="test",
        uncertainties=[],
    )
    rep3 = validate(d_fake_ent, m, set())
    assert not rep3.passed
    assert any("entity" in f for f in rep3.failures)


def test_omnichannel_ig_graph_reels_polls_container_before_publish(monkeypatch) -> None:
    """در انتشار Reels از طریق Graph API باید ابتدا وضعیت کانتینر FINISHED شود."""
    from src.xgpedia.publishers import omnichannel as omni

    calls: list[str] = []

    class _Resp:
        def __init__(self, data: dict):
            self._data = data
            self.text = json.dumps(data)

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._data

    statuses = iter(["IN_PROGRESS", "FINISHED"])

    class _FakeHttpx:
        @staticmethod
        def get(url, **kw):
            calls.append(f"GET:{url}")
            return _Resp({"status_code": next(statuses)})

    res = omni._poll_ig_container_status(_FakeHttpx, "cid_123", "tok", "v22.0", max_attempts=5, interval_sec=0.0)
    assert res == "FINISHED"
    assert len(calls) == 2
    assert "v22.0/cid_123" in calls[0]


def test_error_metrics_counter_records_and_resets() -> None:
    """شمارندهٔ ساختاریافتهٔ خطاها باید خطاها را ثبت و بازنشانی کند."""
    from src.xgpedia.core import error_metrics as em

    em.reset_error_counts()
    em.record_error("unit.test", ValueError("bad sample"), detail="ctx")
    counts = em.get_error_counts()
    assert counts.get("unit.test:ValueError") == 1
    recent = em.get_recent_errors(5)
    assert recent and recent[-1]["scope"] == "unit.test"
    em.reset_error_counts()
    assert em.get_error_counts() == {}


def test_pyproject_has_no_invalid_gitleaks_and_matches_v0722() -> None:
    """pyproject.toml باید نسخه 0.72.0 داشته باشد و gitleaks نامعتبر در آن نباشد."""
    txt = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.79.0"' in txt
    assert "gitleaks" not in txt
    assert "curl_cffi" in txt
    assert "instagrapi" in txt


def test_all_modified_python_files_parse_cleanly() -> None:
    """تمام فایل‌های اصلی پایتون باید بدون خطای نحوی پارس شوند."""
    for rel in (
        "run.py",
        "src/xgpedia/db.py",
        "src/xgpedia/sync.py",
        "src/xgpedia/core/error_metrics.py",
        "src/xgpedia/editorial/validate.py",
        "src/xgpedia/editorial/llm_provider.py",
        "src/xgpedia/providers/breaking_news_free.py",
        "src/xgpedia/providers/irib_conductor.py",
        "src/xgpedia/providers/top_scorers_free.py",
        "src/xgpedia/providers/fpl_free.py",
        "src/xgpedia/providers/player_profile_free.py",
        "src/xgpedia/publishers/omnichannel.py",
        "src/xgpedia/publishers/telegram_bot.py",
        "src/xgpedia/render/render_png.py",
    ):
        src = (ROOT / rel).read_text(encoding="utf-8")
        ast.parse(src, filename=rel)


def test_validator_ed02_rejects_swapped_team_metric_numbers() -> None:
    """ED-02: جابه‌جایی عدد امتیاز یا xG بین میزبان و میهمان باید رد شود."""
    from src.xgpedia.editorial.llm_provider import DraftOutput
    from src.xgpedia.editorial.validate import validate
    from src.xgpedia.normalization.models import Last5, MatchFacts, SourceInfo, StatValue, TeamSide

    m = MatchFacts(
        fixture_id="test:ed02",
        competition={"name": "Premier League", "season": "2026-27"},
        kickoff_utc="2026-11-14T17:30:00Z",
        source=SourceInfo(provider="test", collected_at="2026-11-13T09:00:00Z"),
        home=TeamSide(
            name_fa="آرسنال",
            name_en="Arsenal",
            last5=Last5(n=5, points=10, goals_for=9, goals_against=4),
            xg_for_avg=StatValue(value=1.82, n=5),
            corners_avg=StatValue(value=6.1, n=5),
        ),
        away=TeamSide(
            name_fa="چلسی",
            name_en="Chelsea",
            last5=Last5(n=5, points=7, goals_for=6, goals_against=6),
            xg_for_avg=StatValue(value=1.15, n=5),
            corners_avg=StatValue(value=5.4, n=5),
        ),
    )

    # جابه‌جایی امتیاز آرسنال (10) به نام چلسی (7)
    d_swap = DraftOutput(
        status="ok",
        title="آرسنال در خانه",
        bullets=["آرسنال ۱۰ امتیاز از ۵ بازی اخیر"],
        caption="چلسی ۱۰ امتیاز در ۵ بازی اخیر کسب کرده است.",
        source_note="test",
        uncertainties=[],
    )
    rep = validate(d_swap, m, set())
    assert not rep.passed
    assert any("numeric_binding" in f for f in rep.failures)

    # حالت صحیح باید پاس شود
    d_ok = DraftOutput(
        status="ok",
        title="آرسنال در خانه",
        bullets=["آرسنال ۱۰ امتیاز از ۵ بازی اخیر", "چلسی ۷ امتیاز از ۵ بازی اخیر"],
        caption="میانگین xG آرسنال 1.82 است.",
        source_note="test",
        uncertainties=[],
    )
    rep_ok = validate(d_ok, m, set())
    assert rep_ok.passed, rep_ok.failures


def test_data_source_chains_src01_tier_governance() -> None:
    """SRC-01: فقط opta_official باید زیر tier رسمی official_opta باشد."""
    dsc = json.loads((ROOT / "config" / "data_source_chains.json").read_text(encoding="utf-8"))
    assert dsc["version"] == "0.79.0"
    for domain, items in dsc["domain_chains"].items():
        for item in items:
            if item.get("tier") == "official_opta":
                assert item["provider_id"] == "opta_official", f"Unexpected official_opta in {domain}: {item}"


def test_persistent_state_dict_survives_restart(tmp_path, monkeypatch) -> None:
    """OPS-03: وضعیت ربات ذخیره شده در PersistentStateDict باید پس از نمونه‌سازی مجدد حفظ شود."""
    from src.xgpedia import db as db_mod

    test_db = tmp_path / "bot_state.sqlite"
    monkeypatch.setattr(db_mod, "DATABASE_PATH", test_db)
    db_mod.init_db()

    st1 = db_mod.PersistentStateDict("customizer_state", key_type=int)
    st1[12345] = {"fixture_id": "fx1", "fmt": "4:5"}

    # شبیه‌سازی ری‌استارت با ساخت نمونهٔ جدید روی همان دیتابیس
    st2 = db_mod.PersistentStateDict("customizer_state", key_type=int)
    assert st2.get(12345) == {"fixture_id": "fx1", "fmt": "4:5"}
    st2.pop(12345)

    st3 = db_mod.PersistentStateDict("customizer_state", key_type=int)
    assert st3.get(12345) is None


def test_api_health_report_includes_suppressed_error_metrics() -> None:
    """گزارش /health باید خطاهای مهارشدهٔ error_metrics را نمایش دهد."""
    from src.xgpedia.core import api_health, error_metrics

    api_health.configure_health_store(persist=False, clear=True)
    error_metrics.reset_error_counts()
    api_health.record_success("feed:fotmob", 120.0)
    error_metrics.record_error("breaking_news.excerpt", RuntimeError("boom"))

    report = api_health.format_health_report_fa()
    assert "breaking_news.excerpt:RuntimeError" in report

    api_health.reset_health()
    assert error_metrics.get_error_counts() == {}


def test_telegram_bot_registers_admin_only_middleware() -> None:
    """AdminOnlyMiddleware باید روی router.message و router.callback_query ثبت شده باشد."""
    tb_src = (ROOT / "src" / "xgpedia" / "publishers" / "telegram_bot.py").read_text(encoding="utf-8")
    assert "class AdminOnlyMiddleware(BaseMiddleware):" in tb_src
    assert "router.message.middleware(_ADMIN_GUARD_MW)" in tb_src
    assert "router.callback_query.middleware(_ADMIN_GUARD_MW)" in tb_src
