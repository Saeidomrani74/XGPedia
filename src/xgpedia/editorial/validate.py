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
    if draft.status == "ok":
        rep.check(bool(draft.title.strip()), "structure", "تیتر خالی است")

    # ۲) عددی: هر عدد متن باید در JSON ورودی باشد یا از عملیات مجاز ثبت‌شده
    for num in _extract_numbers(text):
        if not any(abs(num - a) < 1e-9 for a in allowed_numbers):
            rep.check(False, "numeric", f"عدد {num} در فکت‌های ورودی نیست")

    # ۲الف) اتصال عدد به تیم/شاخص (ED-02: جلوگیری از جابه‌جایی عدد میزبان و میهمان)
    segmented_text = "\n".join([draft.title, draft.caption, *draft.bullets])
    for issue in _check_side_metric_bindings(segmented_text, match, derived_numbers):
        rep.check(False, "numeric_binding", issue)

    # ۲ب) تحریف null به صفر
    for issue in _null_distortion(text, match):
        rep.check(False, "null_to_zero", issue)

    # ۳) موجودیت‌ها (بررسی نام‌های معرفی‌شده پس از نقش‌های فوتبالی تا نام ساختگی بازیکن/باشگاه عبور نکند)
    known = _known_entities(match)
    for candidate in _extract_role_bound_entities(text):
        if _looks_like_name(candidate) and not _is_known_entity(candidate, known):
            rep.check(False, "entity", f"نام ناشناخته: «{candidate}»")

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
        has_public_copy = bool(
            draft.title.strip()
            or draft.caption.strip()
            or any(str(b).strip() for b in draft.bullets)
        )
        rep.check(
            not has_public_copy,
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
            for attr in (
                "goals",
                "expected_goals",
                "total_shots",
                "shots_on_target",
                "corner_kicks",
                "corners",
                "fouls",
                "possession",
                "big_chances",
                "yellow_cards",
                "red_cards",
            ):
                sv = getattr(ms, attr, None)
                if sv and getattr(sv, "value", None) is not None:
                    nums.add(float(sv.value))
        if getattr(side, "insideBox", None) is not None:
            try:
                nums.add(float(side.insideBox))
            except (TypeError, ValueError):
                pass
        gk = getattr(side, "gk", None)
        if isinstance(gk, dict):
            for gk_k in ("saves", "psxg", "ga"):
                if gk.get(gk_k) is not None:
                    try:
                        nums.add(float(gk[gk_k]))
                    except (TypeError, ValueError):
                        pass
            if gk.get("psxg") is not None and gk.get("ga") is not None:
                try:
                    diff_gk = round(float(gk["psxg"]) - float(gk["ga"]), 2)
                    nums.add(diff_gk)
                    nums.add(abs(diff_gk))
                except (TypeError, ValueError):
                    pass
        if getattr(side, "scorersText", None):
            for raw_n in re.findall(r"\d+(?:\.\d+)?", str(side.scorersText)):
                try:
                    nums.add(float(raw_n))
                except ValueError:
                    pass
        for sh in getattr(side, "shotList", None) or []:
            if isinstance(sh, (list, tuple)) and len(sh) >= 6:
                for idx in (2, 5):
                    try:
                        nums.add(round(float(sh[idx]), 2))
                    except (TypeError, ValueError):
                        pass
        kp = getattr(side, "kp", None)
        if isinstance(kp, dict):
            for k in ("s1", "s2"):
                for raw_n in re.findall(r"\d+(?:\.\d+)?", str(kp.get(k) or "")):
                    try:
                        nums.add(float(raw_n))
                    except ValueError:
                        pass
    for tp in getattr(match, "topPlayers", None) or []:
        if isinstance(tp, dict):
            if tp.get("rating") is not None:
                try:
                    nums.add(float(tp["rating"]))
                except (TypeError, ValueError):
                    pass
            for raw_n in re.findall(r"\d+(?:\.\d+)?", str(tp.get("stat") or "")):
                try:
                    nums.add(float(raw_n))
                except ValueError:
                    pass
    motm = getattr(match, "motm", None)
    if isinstance(motm, dict):
        for mk in ("rating", "number"):
            if motm.get(mk) is not None:
                try:
                    nums.add(float(motm[mk]))
                except (TypeError, ValueError):
                    pass
        for ch in motm.get("chips") or []:
            if isinstance(ch, dict):
                for raw_n in re.findall(r"\d+(?:\.\d+)?", str(ch.get("val") or "")):
                    try:
                        nums.add(float(raw_n))
                    except ValueError:
                        pass
        ru = motm.get("runnerUp") or motm.get("runner_up")
        if isinstance(ru, dict):
            if ru.get("rating") is not None:
                try:
                    nums.add(float(ru["rating"]))
                except (TypeError, ValueError):
                    pass
            for raw_n in re.findall(r"\d+(?:\.\d+)?", str(ru.get("stat") or "")):
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


def _side_metric_is_null(side, metric: str) -> bool:
    ms = getattr(side, "match_stats", None)
    if metric == "xg":
        has_avg = side.xg_for_avg is not None and side.xg_for_avg.value is not None
        has_match = (
            ms is not None
            and getattr(ms, "expected_goals", None) is not None
            and ms.expected_goals.value is not None
        )
        return not (has_avg or has_match)
    if metric == "corners":
        has_avg = side.corners_avg is not None and side.corners_avg.value is not None
        has_match = (
            ms is not None
            and (
                (getattr(ms, "corner_kicks", None) is not None and ms.corner_kicks.value is not None)
                or (getattr(ms, "corners", None) is not None and ms.corners.value is not None)
            )
        )
        return not (has_avg or has_match)
    if metric == "possession":
        has_match = (
            ms is not None
            and getattr(ms, "possession", None) is not None
            and ms.possession.value is not None
        )
        return not has_match
    return False


def _null_distortion(text: str, match: MatchFacts) -> list[str]:
    """اگر شاخصی در فکت (میزبان یا میهمان) null باشد ولی متن ادعای صفر کند — تحریف است."""
    issues: list[str] = []
    t = text.lower()
    zero_claim = bool(re.search(r"(?:^|[\s:(])(?:0(?:\.0+)?|۰|صفر)(?=$|[\s،؛,.:)]|\b)", t))
    if not zero_claim:
        return issues

    home_tokens = [x.lower() for x in (match.home.name_fa, match.home.name_en, "میزبان") if x]
    away_tokens = [x.lower() for x in (match.away.name_fa, match.away.name_en, "میهمان") if x]
    mentions_home = any(tok in t for tok in home_tokens)
    mentions_away = any(tok in t for tok in away_tokens)

    for metric, keywords in _NULL_METRIC_WORDS.items():
        if not any(kw in t for kw in keywords):
            continue
        home_null = _side_metric_is_null(match.home, metric)
        away_null = _side_metric_is_null(match.away, metric)
        if home_null and (mentions_home or not mentions_away):
            issues.append(f"{metric} تیم میزبان ناموجود (null) است؛ ادعای مقدار (صفر) = تحریف null")
        if away_null and (mentions_away or not mentions_home):
            issues.append(f"{metric} تیم میهمان ناموجود (null) است؛ ادعای مقدار (صفر) = تحریف null")
    return issues


_ENTITY_ROLE_PREFIXES = (
    "بازیکن",
    "مهاجم",
    "هافبک",
    "مدافع",
    "دروازه‌بان",
    "دروازه بان",
    "سرمربی",
    "کاپیتان",
    "باشگاه",
)
_COMMON_NON_NAMES = {
    "میزبان", "میهمان", "مهمان", "برتر", "فعلی", "جدید", "قبلی", "اصلی", "جوان",
    "تیم", "حریف", "لیگ", "فصل", "بازی", "مسابقه", "امشب", "هفته", "اخیر",
    "کلیدی", "برجسته", "ستاره", "گلزن", "آماده", "مصدوم", "محروم", "غایب",
    "این", "آن", "دو", "هر", "خود", "شان", "ایشان",
}


def _extract_role_bound_entities(text: str) -> list[str]:
    """استخراج نام‌های معرفی‌شده بلافاصله پس از نقش‌های فوتبالی (مثل «مهاجم فلان بهمانی»)."""
    found: list[str] = []
    prefix_pat = "|".join(re.escape(p) for p in _ENTITY_ROLE_PREFIXES)
    # دو واژهٔ فارسی پس از نقش (نام و نام خانوادگی)
    rx = re.compile(rf"(?:{prefix_pat})\s+([\u0600-\u06FF\u200c]{{3,}}\s+[\u0600-\u06FF\u200c]{{3,}})")
    for m in rx.finditer(text):
        cand = m.group(1).strip()
        if cand:
            found.append(cand)
    return found


def _is_known_entity(token: str, known: set[str]) -> bool:
    if token in known:
        return True
    tok_norm = token.replace("\u200c", " ").strip()
    for k in known:
        k_norm = k.replace("\u200c", " ").strip()
        if not k_norm:
            continue
        if tok_norm == k_norm or k_norm in tok_norm or tok_norm in k_norm:
            return True
    return False


def _looks_like_name(token: str) -> bool:
    parts = [p.strip() for p in token.split() if p.strip()]
    if len(parts) < 2:
        return False
    if any(p in _COMMON_NON_NAMES for p in parts):
        return False
    return all(len(p) >= 3 for p in parts)


_METRIC_BINDING_KEYWORDS = {
    "points": ("امتیاز",),
    "xg": ("xg", "امید گل"),
    "corners": ("کرنر",),
}


def _side_metric_values(side, metric: str) -> set[float]:
    vals: set[float] = set()
    if metric == "points":
        if side.last5 and side.last5.points is not None:
            vals.add(float(side.last5.points))
        return vals
    if metric == "xg":
        if side.xg_for_avg and side.xg_for_avg.value is not None:
            vals.add(float(side.xg_for_avg.value))
        if side.xg_against_avg and side.xg_against_avg.value is not None:
            vals.add(float(side.xg_against_avg.value))
        ms = getattr(side, "match_stats", None)
        if ms and getattr(ms, "expected_goals", None) and ms.expected_goals.value is not None:
            vals.add(float(ms.expected_goals.value))
        for v in getattr(side, "xg_series", None) or []:
            if v is not None:
                vals.add(float(v))
        return vals
    if metric == "corners":
        if side.corners_avg and side.corners_avg.value is not None:
            vals.add(float(side.corners_avg.value))
        ms = getattr(side, "match_stats", None)
        if ms:
            for attr in ("corner_kicks", "corners"):
                sv = getattr(ms, attr, None)
                if sv and getattr(sv, "value", None) is not None:
                    vals.add(float(sv.value))
        return vals
    return vals


def _side_window_numbers(side) -> set[float]:
    win: set[float] = set()
    if side.last5 and side.last5.n is not None:
        win.add(float(side.last5.n))
    for sv in (side.xg_for_avg, side.xg_against_avg, side.sot_avg, side.corners_avg):
        if sv and sv.n is not None:
            win.add(float(sv.n))
    return win


def _check_side_metric_bindings(text: str, match: MatchFacts, derived_numbers: set[float]) -> list[str]:
    """اگر جمله‌ای صراحتاً فقط از یک تیم و یک شاخص (امتیاز/xG/کرنر) نام ببرد ولی عدد تیم مقابل را بیاورد، رد می‌شود."""
    issues: list[str] = []
    home_tokens = [x.lower() for x in (match.home.name_fa, match.home.name_en, "میزبان") if x]
    away_tokens = [x.lower() for x in (match.away.name_fa, match.away.name_en, "میهمان") if x]
    clauses = re.split(r"[.!؟؛\n،]+", text)
    for clause in clauses:
        low = clause.lower().strip()
        if not low:
            continue
        has_home = any(t in low for t in home_tokens)
        has_away = any(t in low for t in away_tokens)
        if has_home == has_away:
            continue  # یا هیچ تیمی ذکر نشده یا هر دو تیم در یک جمله مقایسه شده‌اند
        side, other, side_lbl = (match.home, match.away, match.home.name_fa) if has_home else (match.away, match.home, match.away.name_fa)
        win_nums = _side_window_numbers(side)
        for metric, kws in _METRIC_BINDING_KEYWORDS.items():
            if not any(kw in low for kw in kws):
                continue
            own_vals = _side_metric_values(side, metric)
            other_vals = _side_metric_values(other, metric)
            if not other_vals:
                continue
            # عددهای چسبیده به این شاخص در همین جمله
            for num in _extract_numbers(low):
                if any(abs(num - w) < 1e-9 for w in win_nums):
                    continue
                if any(abs(num - d) < 1e-9 for d in derived_numbers):
                    continue
                in_own = any(abs(num - v) < 1e-9 for v in own_vals)
                in_other = any(abs(num - v) < 1e-9 for v in other_vals)
                if in_other and not in_own:
                    issues.append(f"عدد {num} برای شاخص {metric} متعلق به {side_lbl} نیست (جابه‌جایی میزبان/میهمان)")
    return issues
