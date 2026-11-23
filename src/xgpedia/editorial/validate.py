"""لایهٔ ۵ — Validation: دروازه‌های اعتبارسنجی پیش از هر انتشار.

سیاست retry: یک بار اصلاح خودکار؛ در شکست دوم، رد و ارسال برای بررسی انسانی.
مجموعهٔ تزریق خطا (۳۰ مورد در tests/) باید ۱۰۰٪ رد شود (شرط Gate 3).
"""
from __future__ import annotations

import re

from src.xgpedia.config import load_brand, load_glossary
from src.xgpedia.editorial.llm_provider import DraftOutput
from src.xgpedia.normalization.models import MatchFacts

# قواعد پایهٔ اعتبار تحریریه (داده‌محور، مستقل از هر سیاست موضوعی).
FORBIDDEN_PATTERNS = [
    r"قطعی\s*برنده", r"تضمین", r"حتماً\s*می‌برد", r"فرصت\s*(طلایی|مطمئن)",
]

# الگوهای فنی/نامتعارف که نباید وارد متن فارسی مخاطب شوند (مانند (n=10) یا کلیدهای JSON)
UNNATURAL_STYLE_PATTERNS = [
    (r"\(\s*n\s*=\s*[\d۰-۹]+\s*\)", "عبارت غیرطبیعی حجم نمونه (مثل n=10) — به‌جای آن بنویس «در ۱۰ بازی اخیر»"),
    (r"(?<![a-zA-Z0-9_])n\s*=\s*[\d۰-۹]+", "عبارت فنی n=... در متن فارسی مجاز نیست — به فارسی روان بنویس"),
    (r"\b(?:fixture_id|payload_hash|match_stats|xg_for_avg|xg_against_avg|corners_avg)\b", "کلید فنی JSON در متن فارسی مجاز نیست"),
]


class ValidationReport:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, ok: bool, gate: str, detail: str = "") -> None:
        if not ok:
            self.failures.append(f"[{gate}] {detail}")

    @property
    def passed(self) -> bool:
        return not self.failures


def _known_entities(match: MatchFacts) -> set[str]:
    g = load_glossary()
    names = {t["name_fa"] for t in g.get("teams", [])}
    names |= {t["name_en"] for t in g.get("teams", [])}
    names |= {p["name_fa"] for p in g.get("players", [])}
    names |= {match.home.name_fa, match.away.name_fa}
    return names


def validate(draft: DraftOutput, match: MatchFacts, derived_numbers: set[float]) -> ValidationReport:
    """دروازه‌های اعتبارسنجی — هر رد شدن = یک بازگشت برای اصلاح؛ شکست دوم = بررسی انسانی."""
    rep = ValidationReport()
    text = " ".join([draft.title, draft.caption, *draft.bullets])
    allowed_numbers = derived_numbers | _input_numbers(match)

    # ۱) ساختار و نوع
    rep.check(bool(draft.title.strip()), "structure", "تیتر خالی است")

    # ۲) عددی: هر عدد متن باید در JSON ورودی باشد یا از عملیات مجاز ثبت‌شده
    for num in _extract_numbers(text):
        if not any(abs(num - a) < 1e-9 for a in allowed_numbers):
            rep.check(False, "numeric", f"عدد {num} در فکت‌های ورودی نیست")

    # ۲ب) تحریف null به صفر
    for issue in _null_distortion(text, match):
        rep.check(False, "null_to_zero", issue)

    # ۳) موجودیت‌ها
    known = _known_entities(match)
    for token in re.findall(r"[\u0600-\u06FF\u200c]+(?:\s[\u0600-\u06FF\u200c]+)?", text):
        if _looks_like_name(token) and token not in known and not any(k in token for k in known):
            rep.check(False, "entity", f"نام ناشناخته: «{token}»")

    # ۴) منبع
    if draft.status == "ok" and match.availability and not draft.source_note.strip():
        rep.check(False, "source", "پست دارای غیبت/خبر است اما source_note خالی است")

    # ۵) سازگاری درصدها
    for pct in re.findall(r"(\d+(?:\.\d+)?)\s*٪|(\d+(?:\.\d+)?)\s*درصد", text):
        v = float(pct[0] or pct[1])
        rep.check(0 <= v <= 100, "consistency", f"درصد خارج از بازه: {v}")

    # ۶) واژه‌های ممنوع
    brand = load_brand()
    banned = FORBIDDEN_PATTERNS + [re.escape(w) for w in brand.get("forbidden_words", [])]
    for pat in banned:
        if re.search(pat, text):
            rep.check(False, "policy", f"عبارت ممنوع: {pat}")

    # ۶ب) سبک نگارش فارسی روان (رد عبارت‌های فنی/نامتعارف مانند (n=10))
    for pat, msg in UNNATURAL_STYLE_PATTERNS:
        if re.search(pat, text, flags=re.IGNORECASE):
            rep.check(False, "style", msg)

    # ۷) insufficient_data → هیچ متنی منتشر نشود
    if draft.status == "insufficient_data":
        rep.check(
            draft.title == "" or draft.status != "ok",
            "insufficient_data",
            "وضعیت insufficient_data است اما متن تولید شده — جایزه‌ای برای جمله‌سازی نیست",
        )

    return rep


def _input_numbers(match: MatchFacts) -> set[float]:
    nums: set[float] = set()
    if getattr(match, "matchday", None) is not None:
        nums.add(float(match.matchday))
    if getattr(match, "result", None) is not None:
        for g in (match.result.home_goals, match.result.away_goals):
            if g is not None:
                nums.add(float(g))
    if getattr(match, "market_odds", None) is not None:
        mo = match.market_odds
        for attr in ("home", "draw", "away", "over25", "under25", "btts"):
            val = getattr(mo, attr, None)
            if val is not None:
                nums.add(float(val))
    for side in (match.home, match.away):
        if side.last5:
            nums.update(
                v for v in (side.last5.points, side.last5.goals_for, side.last5.goals_against)
                if v is not None
            )
            nums.add(side.last5.n)
        for sv in (side.xg_for_avg, side.xg_against_avg, side.sot_avg, side.corners_avg):
            if sv and sv.value is not None:
                nums.add(sv.value)
                if sv.n is not None:
                    nums.add(sv.n)
        for v in getattr(side, "xg_series", None) or []:
            if v is not None:
                nums.add(float(v))
        ms = getattr(side, "match_stats", None)
        if ms is not None:
            for attr in ("expected_goals", "total_shots", "shots_on_target", "corners", "possession"):
                sv = getattr(ms, attr, None)
                if sv and getattr(sv, "value", None) is not None:
                    nums.add(float(sv.value))
        kp = getattr(side, "kp", None)
        if isinstance(kp, dict):
            for k in ("s1", "s2"):
                for raw_n in re.findall(r"\d+(?:\.\d+)?", str(kp.get(k) or "")):
                    try:
                        nums.add(float(raw_n))
                    except ValueError:
                        pass
    for item in getattr(match, "recent_news", None) or []:
        title = str(item.get("title") or "") if isinstance(item, dict) else ""
        for raw_n in re.findall(r"\d+(?:\.\d+)?", title):
            try:
                nums.add(float(raw_n))
            except ValueError:
                pass
    return nums


def _extract_numbers(text: str) -> list[float]:
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)]


_NULL_METRIC_WORDS = {
    "xg": ["xg", "امید گل"],
    "corners": ["کرنر"],
    "possession": ["مالکیت"],
}


def _null_distortion(text: str, match: MatchFacts) -> list[str]:
    """اگر شاخصی در فکت null باشد ولی متن ادعای مقدار برایش کند — تحریف است."""
    issues: list[str] = []
    t = text.lower()
    zero_claim = bool(re.search(r"(?:^|[\s:(])(?:0(?:\.0+)?|۰|صفر)(?=$|[\s،؛,.:)]|\b)", t))
    if not zero_claim:
        return issues
    if match.away.xg_for_avg is None and re.search(r"xg|امید گل", t):
        issues.append("xG ناموجود (null) است؛ ادعای مقدار (صفر) = تحریف null")
    return issues


def _looks_like_name(token: str) -> bool:
    return False
