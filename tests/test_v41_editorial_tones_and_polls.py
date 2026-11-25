"""تست‌های نسخه v0.41.0 (فاز ۳) — تحریریه چندلحنی، زوایای روایی (Narrative Hooks) و نظرسنجی تعاملی خودکار (Auto-Poll)."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from src.xgpedia.editorial.draft import generate_draft
from src.xgpedia.editorial.llm_provider import DraftOutput
from src.xgpedia.editorial.narrative import (
    EDITORIAL_TONES,
    build_system_prompt,
    extract_narrative_hooks,
    normalize_tone,
)
from src.xgpedia.publishers import telegram_publish as tp


def test_four_editorial_tones_and_narrative_hooks_extraction() -> None:
    assert set(EDITORIAL_TONES.keys()) == {"analytical", "fan_light", "x_thread", "reels_script"}
    assert normalize_tone("unknown_tone") == "analytical"

    sample = json.loads(Path("data/samples/fact.json").read_text(encoding="utf-8"))
    # تقویت سناریوی فرم و اخبار زنده برای تست استخراج زوایای روایی
    sample["home"]["last5"] = {"points": 13, "goals_for": 12, "goals_against": 3}
    sample["home"]["xg_for_avg"] = 1.95
    sample["away"]["xg_for_avg"] = 1.10
    sample["recent_news"] = [{"title": "New manager prepares for first game in huge derby clash"}]

    hooks = extract_narrative_hooks(sample)
    assert len(hooks) >= 2
    assert any("اوج فرم" in h or "برتری واضح" in h for h in hooks)
    assert any("سرمربیگری" in h or "دربی" in h for h in hooks)

    for t in EDITORIAL_TONES:
        sp = build_system_prompt(t, hooks)
        assert EDITORIAL_TONES[t]["directive"] in sp
        assert "زوایای داستانی پیشنهادی" in sp


def test_generate_draft_forwards_selected_tone_prompt_to_provider() -> None:
    from src.xgpedia.normalization.models import MatchFacts
    if not hasattr(MatchFacts, "model_validate"):
        return
    sample = json.loads(Path("data/samples/fact.json").read_text(encoding="utf-8"))
    seen_prompts: list[str] = []

    class _FakeLLM:
        def generate(self, system_prompt, facts, **kw):
            seen_prompts.append(system_prompt)
            return DraftOutput(
                status="ok",
                title="نبرد حساس هفته در لیگ برتر",
                bullets=["عملکرد دو تیم بر پایه داده‌های واقعی فصل بررسی شد."],
                caption="تقابل دو تیم با انگیزه بالا برگزار می‌شود و آمارهای ثبت‌شده تصویر روشنی از روند مسابقه می‌دهند.",
                source_note="",
                uncertainties=[],
            )

    draft, rep, attempts = generate_draft(_FakeLLM(), sample, tone="reels_script")
    assert rep.passed
    assert attempts == 1
    assert seen_prompts
    assert "اسکریپت گفتاری ویدیوی کوتاه" in seen_prompts[0]


def test_build_auto_poll_for_preview_debate_this_or_that_and_lineup() -> None:
    p_prev = {
        "post_type": "preview",
        "fact_json": json.dumps({"home": {"name_fa": "آرسنال"}, "away": {"name_fa": "لیورپول"}}),
    }
    poll1 = tp.build_auto_poll(p_prev)
    assert poll1 is not None
    assert "آرسنال" in poll1["question"] and "لیورپول" in poll1["question"]
    assert poll1["options"] == ["برد آرسنال", "تساوی", "برد لیورپول"]

    p_deb = {
        "post_type": "debate",
        "title": "بهترین مهاجم لیگ برتر",
        "fact_json": json.dumps({"title": "بهترین مهاجم فصل؟", "sideA": {"name": "هالند"}, "sideB": {"name": "صلاح"}}),
    }
    poll2 = tp.build_auto_poll(p_deb)
    assert poll2 is not None
    assert poll2["options"][:2] == ["هالند", "صلاح"]

    p_tot = {
        "post_type": "this_or_that",
        "fact_json": json.dumps({"a": {"name": "آرسنال"}, "b": {"name": "چلسی"}}),
    }
    poll3 = tp.build_auto_poll(p_tot)
    assert poll3 is not None
    assert poll3["options"] == ["آرسنال", "چلسی"]

    # کارت‌های غیرتعاملی مثل جدول نباید Poll بسازند
    assert tp.build_auto_poll({"post_type": "standings", "fact_json": "{}"}) is None


def test_telegram_bot_has_tone_selector_and_send_poll() -> None:
    tb_src = Path("src/xgpedia/publishers/telegram_bot.py").read_text(encoding="utf-8")
    assert "async def send_poll(" in tb_src
    assert 'callback_data="cz:tone:analytical"' in tb_src
    assert 'callback_data="cz:tone:reels_script"' in tb_src
    assert 'elif action == "tone"' in tb_src
    assert 'tone=st.get("tone", "analytical")' in tb_src


def test_narrative_hooks_handles_metric_dict_objects() -> None:
    """در MatchFacts واقعی فیلد xg_for_avg به‌صورت دیکشنری Metric ({'value': 1.9, 'n': 10}) است."""
    facts_metric = {
        "home": {"name_fa": "آرسنال", "last5": {"points": 13, "goals_for": 12}, "xg_for_avg": {"value": 1.92, "n": 10}},
        "away": {"name_fa": "چلسی", "last5": {"points": 4, "goals_for": 3}, "xg_for_avg": {"value": 1.15, "n": 10}},
        "recent_news": [],
    }
    hooks = extract_narrative_hooks(facts_metric)
    assert len(hooks) >= 2
