"""تأمین‌کنندهٔ پیشنهادهای داغ و جدال‌انگیز کارت «این یا اون؟» (XGPedia This or That — D49).

منابع رایگان و چندلایه (منحصراً فوتبال / Soccer):
  ۱) پیشنهادهای زندهٔ متناسب با بازی‌های داغ امروز در دیتابیس (ساخت خودکار دوئل‌های روز مسابقه)
  ۲) بانک ۱۰ دوئل جدالی و کلاسیک فوتبال ایران و جهان (config/this_or_that_presets.json)
  ۳) تولید دوئل جدالی تازه و موضوعی با روتر رایگان LLM (`generate_ai_debate_proposal`)
  ۴) دریافت اختیاری عکس واقعی بازیکنان از Wikipedia + TheSportsDB (`strSport == "Soccer"`).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from src.xgpedia.config import ROOT

log = logging.getLogger(__name__)


def load_this_or_that_presets() -> list[dict[str, Any]]:
    p = ROOT / "config" / "this_or_that_presets.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("failed loading this_or_that_presets.json: %s", e)
        return []


def build_today_match_debates(max_items: int = 3) -> list[dict[str, Any]]:
    """ساخت خودکار پیشنهادهای دوئل جدالی از بازی‌های مهم امروز در دیتابیس محلی (بدون هزینه و فوری)."""
    debates: list[dict[str, Any]] = []
    try:
        from src.xgpedia.today_workflow import list_today_matches
        matches = list_today_matches() or []
    except Exception:
        matches = []

    for m in matches[:max_items]:
        h_fa = str(m.get("home_fa") or m.get("home_name") or "").strip()
        a_fa = str(m.get("away_fa") or m.get("away_name") or "").strip()
        if not h_fa or not a_fa:
            continue
        comp = str(m.get("competition_fa") or m.get("competition_code") or "فوتبال اروپا").strip()
        fid = str(m.get("fixture_id") or f"{h_fa}_{a_fa}")
        hid = hashlib.sha1(f"tot_m:{fid}".encode("utf-8")).hexdigest()[:8]
        h_code = str(m.get("home_tla") or h_fa[:3]).upper()[:4]
        a_code = str(m.get("away_tla") or a_fa[:3]).upper()[:4]
        debates.append({
            "id": f"tot_live_{hid}",
            "label": f"🔥 {h_fa} × {a_fa}",
            "sub": f"دوئل داغ امروز | {comp}",
            "is_live": True,
            "layout": "diagonal",
            "category": f"دوئل داغ امروز | {comp}",
            "edition": "LIVE // TODAY",
            "question": f"در نبرد امروز {comp}، کدام تیم برندهٔ زمین خواهد بود؟",
            "cta": f"{h_fa} (A) یا {a_fa} (B)؟ پیش‌بینی و دلیلت رو کامنت کن!",
            "footer": f"XGPEDIA MATCHDAY DEBATE // {h_code} VS {a_code}",
            "pollA": 52,
            "a": {
                "name": h_fa,
                "sub": f"میزبان نبرد امروز | {comp}",
                "code": h_code,
                "num": "01",
                "rating": 90,
                "color": "#E62E45",
                "secondary": "#FFFFFF",
                "art": "crest",
                "tags": ["امتیاز میزبانی", "فشار سکوها", "شروع هجومی"],
            },
            "b": {
                "name": a_fa,
                "sub": f"میهمان مدعی | {comp}",
                "code": a_code,
                "num": "02",
                "rating": 89,
                "color": "#38BDF8",
                "secondary": "#FFFFFF",
                "art": "crest",
                "tags": ["انتقال سریع", "نظم دفاعی", "تهدید ضدحمله"],
            },
            "stats": [
                {"l": "برتری مالکیت و ریتم بازی", "a": 54, "b": 46},
                {"l": "خطر در انتقال‌های سریع", "a": 48, "b": 52},
                {"l": "شانس پیروزی در بازی بزرگ", "a": 52, "b": 48},
            ],
        })
    return debates


def list_this_or_that_suggestions(*, include_live_matches: bool = True) -> list[dict[str, Any]]:
    """لیست یکپارچه پیشنهادهای جذاب و جدال‌انگیز (ابتدا دوئل‌های بازی‌های داغ امروز + ۱۰ دوئل کلاسیک و داغ)."""
    live = build_today_match_debates(max_items=3) if include_live_matches else []
    presets = load_this_or_that_presets()
    return live + presets


def generate_ai_debate_proposal(
    *,
    topic_hint: str = "",
    llm_provider: Any = None,
    cancel_event: Any = None,
) -> dict[str, Any]:
    """تولید یک دوئل جدال‌انگیز و جذاب تازهٔ فوتبال (منحصراً Soccer) با روتر رایگان LLM."""
    if llm_provider is None:
        from src.xgpedia.editorial.llm_provider import build_default_llm
        llm_provider = build_default_llm()
    if cancel_event is not None and hasattr(llm_provider, "cancel_event"):
        llm_provider.cancel_event = cancel_event

    sys_prompt = (
        "تو سردبیر خلاق رسانه فوتبال XGPedia هستی. یک دوئل فوق‌العاده جدال‌انگیز، حساس و جذاب «این یا اون؟» منحصراً دربارهٔ فوتبال (Soccer — اروپا یا ایران) بساز.\n"
        "قوانین اجباری:\n"
        "1) خروجی را فقط به‌صورت JSON معتبر با دقیقاً همین کلیدها برگردان:\n"
        '{"status": "ok", "title": "...", "caption": "...", "bullets": ["...", "...", "..."], "source_note": "...", "uncertainties": []}\n'
        "- `status`: حتماً `\"ok\"` باشد.\n"
        "- `title`: سؤال اصلی و جدالی کارت (حداکثر ۶۸ کاراکتر، بدون ستاره `*`).\n"
        "- `caption`: متن دعوت به کامنت (CTA) جذاب در ۱ جمله کوتاه.\n"
        "- `bullets`: دقیقاً ۳ خط با فرمت مشخص:\n"
        "  خط ۱: `A: <نام کوتاه فارسی گزینه اول> | <توضیح ۴ کلمه‌ای> | <کد ۳ حرفی انگلیسی> | <تگ۱، تگ۲، تگ۳>`\n"
        "  خط ۲: `B: <نام کوتاه فارسی گزینه دوم> | <توضیح ۴ کلمه‌ای> | <کد ۳ حرفی انگلیسی> | <تگ۱، تگ۲، تگ۳>`\n"
        "  خط ۳: `STATS: <شاخص۱>:<عددA>:<عددB> | <شاخص۲>:<عددA>:<عددB> | <شاخص۳>:<عددA>:<عددB>` (اعداد بین 75 تا 99)\n"
        "- `source_note`: دسته‌بندی کوتاه ۳ کلمه‌ای (مثلاً «دوئل اسطوره‌های اروپا»).\n"
        "- `uncertainties`: آرایهٔ خالی `[]`."
    )
    draft = llm_provider.generate(
        sys_prompt,
        {"topic_hint": topic_hint or "یکی از جدال‌انگیزترین مقایسه‌های تاریخ یا روز فوتبال اروپا یا ایران"},
    )
    clean = lambda s: re.sub(r"\*([^*]+)\*", r"\1", str(s or "")).replace("*", "").strip()
    question = clean(getattr(draft, "title", "")) or "کدام ستاره را برای تیم رویایی‌ات انتخاب می‌کنی؟"
    cta = clean(getattr(draft, "caption", "")) or "انتخاب تو کدومه؟ A یا B رو کامنت کن!"
    cat = clean(getattr(draft, "source_note", "")) or "دوئل ویژه XGPedia"
    buls = [clean(b) for b in (getattr(draft, "bullets", None) or []) if clean(b)]

    side_a = {"name": "گزینه A", "sub": "ستاره اول", "code": "A", "num": "10", "rating": 94, "color": "#E62E45", "secondary": "#FFFFFF", "art": "jersey", "tags": ["تأثیرگذار", "بازی بزرگ", "ثبات"]}
    side_b = {"name": "گزینه B", "sub": "ستاره دوم", "code": "B", "num": "07", "rating": 94, "color": "#38BDF8", "secondary": "#F59E0B", "art": "jersey", "tags": ["خلاقیت", "سرعت", "دریبل"]}
    stats = [
        {"l": "تأثیر در بازی‌های بزرگ", "a": 94, "b": 92},
        {"l": "خلاقیت و خلق موقعیت", "a": 90, "b": 95},
        {"l": "ثبات در طول فصل", "a": 93, "b": 91},
    ]

    for line in buls:
        if line.upper().startswith("A:"):
            pts = [x.strip() for x in line.split(":", 1)[1].split("|")]
            if len(pts) >= 1 and pts[0]:
                side_a["name"] = pts[0]
            if len(pts) >= 2 and pts[1]:
                side_a["sub"] = pts[1]
            if len(pts) >= 3 and pts[2]:
                side_a["code"] = re.sub(r"[^A-Za-z0-9]", "", pts[2]).upper()[:4] or "A"
            if len(pts) >= 4 and pts[3]:
                side_a["tags"] = [t.strip() for t in re.split(r"[،,]", pts[3]) if t.strip()][:3]
        elif line.upper().startswith("B:"):
            pts = [x.strip() for x in line.split(":", 1)[1].split("|")]
            if len(pts) >= 1 and pts[0]:
                side_b["name"] = pts[0]
            if len(pts) >= 2 and pts[1]:
                side_b["sub"] = pts[1]
            if len(pts) >= 3 and pts[2]:
                side_b["code"] = re.sub(r"[^A-Za-z0-9]", "", pts[2]).upper()[:4] or "B"
            if len(pts) >= 4 and pts[3]:
                side_b["tags"] = [t.strip() for t in re.split(r"[،,]", pts[3]) if t.strip()][:3]
        elif line.upper().startswith("STATS:"):
            parsed_st = []
            for seg in line.split(":", 1)[1].split("|"):
                parts = [x.strip() for x in seg.split(":")]
                if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                    parsed_st.append({
                        "l": parts[0],
                        "a": max(50, min(99, int(parts[1]))),
                        "b": max(50, min(99, int(parts[2]))),
                    })
            if parsed_st:
                stats = parsed_st[:3]

    hid = hashlib.sha1(f"tot_ai:{side_a['name']}:{side_b['name']}".encode("utf-8")).hexdigest()[:8]
    return {
        "id": f"tot_ai_{hid}",
        "label": f"✨ {side_a['name']} × {side_b['name']}",
        "sub": cat,
        "layout": "diagonal",
        "category": cat,
        "edition": "AI // DEBATE",
        "question": question,
        "cta": cta,
        "footer": f"XGPEDIA DEBATE // {side_a['code']} VS {side_b['code']}",
        "pollA": 51,
        "a": side_a,
        "b": side_b,
        "stats": stats,
        "source": "XGPedia Editorial",
    }
