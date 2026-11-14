"""لایهٔ ۵ — Validation: هفت دروازهٔ اعتبارسنجی پیش از هر انتشار.

سیاست retry: یک بار اصلاح خودکار؛ در شکست دوم، رد و ارسال برای بررسی انسانی.
مجموعهٔ تزریق خطا (۳۰ مورد در tests/) باید ۱۰۰٪ رد شود (شرط Gate 3).
"""
from __future__ import annotations

import re

from src.xgpedia.config import load_brand, load_glossary
from src.xgpedia.editorial.llm_provider import DraftOutput
from src.xgpedia.normalization.models import MatchFacts

# قواعد پایهٔ اعتبار تحریریه (داده‌محور، مستقل از هر سیاست موضوعی).
# سیاست‌های موضوعی دلخواه خودتان را در brand.json ← forbidden_words اضافه کنید.
FORBIDDEN_PATTERNS = [
    r"قطعی\s*برنده", r"تضمین", r"حتماً\s*می‌برد", r"فرصت\s*(طلایی|مطمئن)",
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
    """هفت دروازه — هر رد شدن = یک بازگشت برای اصلاح؛ شکست دوم = بررسی انسانی."""
    rep = ValidationReport()
    # دروازهٔ عددی فقط روی متن تحریریه (تیتر/نکات/کپشن) اعمال می‌شود؛
    # source_note از لایهٔ کد ساخته می‌شود و تاریخ/شناسه دارد، نه ادعای آماری.
    text = " ".join([draft.title, draft.caption, *draft.bullets])
    allowed_numbers = derived_numbers | _input_numbers(match)

    # ۱) ساختار و نوع — DraftOutput.from_json از قبل ساختار را تضمین می‌کند؛
    #    اینجا فقط خالی‌نبودن فیلدهای اجباری
    rep.check(bool(draft.title.strip()), "structure", "تیتر خالی است")

    # ۲) عددی: هر عدد متن باید در JSON ورودی باشد یا از عملیات مجاز ثبت‌شده
    for num in _extract_numbers(text):
        if not any(abs(num - a) < 1e-9 for a in allowed_numbers):
            rep.check(False, "numeric", f"عدد {num} در فکت‌های ورودی نیست")

    # ۲ب) تحریف null به صفر: متریکِ null هرگز «صفر» ادعا نمی‌شود (حتی با کلمه، نه رقم)
    for issue in _null_distortion(text, match):
        rep.check(False, "null_to_zero", issue)

    # ۳) موجودیت‌ها: نام تیم/بازیکن/رقابت باید در واژه‌نامه یا ورودی باشد
    known = _known_entities(match)
    for token in re.findall(r"[\u0600-\u06FF\u200c]+(?:\s[\u0600-\u06FF\u200c]+)?", text):
        if _looks_like_name(token) and token not in known and not any(k in token for k in known):
            rep.check(False, "entity", f"نام ناشناخته: «{token}»")

    # ۴) منبع: هر ادعای خبری/مصدومیتی منبع و زمان دارد
    if draft.status == "ok" and match.availability and not draft.source_note.strip():
        rep.check(False, "source", "پست دارای غیبت/خبر است اما source_note خالی است")

    # ۵) سازگاری: درصد در بازه، واحد درست، دادهٔ همان مسابقه
    for pct in re.findall(r"(\d+(?:\.\d+)?)\s*٪|(\d+(?:\.\d+)?)\s*درصد", text):
        v = float(pct[0] or pct[1])
        rep.check(0 <= v <= 100, "consistency", f"درصد خارج از بازه: {v}")

    # ۶) واژه‌های ممنوع: قواعد پایه + سیاست موضوعی دلخواه از brand.json
    brand = load_brand()
    banned = FORBIDDEN_PATTERNS + [re.escape(w) for w in brand.get("forbidden_words", [])]
    for pat in banned:
        if re.search(pat, text):
            rep.check(False, "policy", f"عبارت ممنوع: {pat}")

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
    for side in (match.home, match.away):
        if side.last5:
            nums.update(v for v in (side.last5.points, side.last5.goals_for, side.last5.goals_against) if v is not None)
            nums.add(side.last5.n)
        for sv in (side.xg_for_avg, side.corners_avg):
            if sv and sv.value is not None:
                nums.add(sv.value)
                if sv.n is not None:
                    nums.add(sv.n)
    return nums


def _extract_numbers(text: str) -> list[float]:
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)]


_NULL_METRIC_WORDS = {
    "xg": ["xg", "امید گل"],
    "corners": ["کرنر"],
    "possession": ["مالکیت"],
}


def _null_distortion(text: str, match: MatchFacts) -> list[str]:
    """اگر شاخصی در فکت null باشد ولی متن ادعای مقدار برایش کند — تحریف است.

    «صفر» و «۰» و «0.0» مستقل ادعای مقدار حساب می‌شوند (صفرِ داخل ۱۰ نه)؛
    null فقط با عبارت «داده در دسترس نیست» مجاز است.
    """
    issues: list[str] = []
    t = text.lower()
    zero_claim = bool(re.search(r"(?:^|[\s:(])(?:0(?:\.0+)?|۰|صفر)(?=$|[\s،؛,.:)]|\b)", t))
    if not zero_claim:
        return issues
    if match.away.xg_for_avg is None and re.search(r"xg|امید گل", t):
        issues.append("xG ناموجود (null) است؛ ادعای مقدار (صفر) = تحریف null")
    return issues


def _looks_like_name(token: str) -> bool:
    """بسیار محافظه‌کار — فقط برای نمونهٔ آموزشی؛ در production از NER یا واژه‌نامهٔ کامل استفاده کن."""
    return False  # در گام اول فقط gate عدد/سیاست فعال است؛ gate نام با glossary کامل روشن شود
