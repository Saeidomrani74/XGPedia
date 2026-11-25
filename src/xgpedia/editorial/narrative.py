"""فاز ۳ — موتور تحریریهٔ چندلحنی (Multi-Tone Editorial) و استخراج خودکار زوایای روایی (Narrative Hooks).

۴ لحن قابل انتخاب در ربات و پایپ‌لاین:
  1. `analytical`: تحلیلی عمیق (اصلی XGPedia — پیش‌فرض)
  2. `fan_light`: لایت و سریع (مناسب کانال‌های طرفداری و خوانش فوری)
  3. `x_thread`: رشته‌توییت X / توییتر (۳ تا ۴ بخش کوتاه با قلاب و پرسش تعاملی)
  4. `reels_script`: اسکریپت ویدیوی ۶۰ ثانیه‌ای (Reels / Shorts با قلاب ۳ ثانیه‌ای)

قاعدهٔ دائمی XGPedia: در تمام لحن‌ها، هر عدد باید عیناً در JSON ورودی (یا مشتق مجاز) باشد
و هیچ آمار یا ادعای جعلی ساخته نمی‌شود (`null ≠ 0`).
"""
from __future__ import annotations

from typing import Any

from src.xgpedia.editorial.prompt import SYSTEM_PROMPT
from src.xgpedia.normalization.models import MatchFacts

EDITORIAL_TONES: dict[str, dict[str, str]] = {
    "analytical": {
        "label_fa": "تحلیلی عمیق",
        "short_fa": "تحلیلی",
        "icon": "📊",
        "directive": (
            "لحن انتخاب‌شده: «تحلیلی عمیق و داده‌محور (سبک اصلی XGPedia)».\n"
            "- بر ساختار تاکتیکی، کیفیت خلق موقعیت (امید گل)، توازن حمله و دفاع و معنای اعداد تمرکز کن."
        ),
    },
    "fan_light": {
        "label_fa": "لایت و سریع (طرفداری)",
        "short_fa": "لایت",
        "icon": "⚡",
        "directive": (
            "لحن انتخاب‌شده: «لایت، پرانرژی و سریع (مناسب کانال طرفداری)».\n"
            "- جملات کوتاه‌تر، هیجان‌انگیزتر و صمیمی‌تر بنویس تا مخاطب در ۵ ثانیه جذب شود.\n"
            "- همچنان پایبندی ۱۰۰٪ به اعداد واقعی JSON الزامی است و هیچ عدد جعلی نساز."
        ),
    },
    "x_thread": {
        "label_fa": "رشته‌توییت X",
        "short_fa": "رشته‌توییت",
        "icon": "🧵",
        "directive": (
            "لحن انتخاب‌شده: «رشته‌توییت آماده انتشار در X (توییتر)».\n"
            "- متن `caption` را در ۳ پاراگراف کوتاه با خط خالی بین آن‌ها بنویس (پاراگراف ۱: قلاب جذاب، پاراگراف ۲: مغز آماری مسابقه، پاراگراف ۳: جمع‌بندی و یک پرسش برای تعامل مخاطب).\n"
            "- هرگز از شمارهٔ رشته مثل 1/3 استفاده نکن (چون اعداد خارج از JSON توسط دروازهٔ اعتبارسنجی رد می‌شوند)."
        ),
    },
    "reels_script": {
        "label_fa": "اسکریپت ریلز ۶۰ ثانیه‌ای",
        "short_fa": "ریلز ۶۰ث",
        "icon": "🎬",
        "directive": (
            "لحن انتخاب‌شده: «اسکریپت گفتاری ویدیوی کوتاه (Reels / Shorts)».\n"
            "- متن `caption` را به‌صورت گفتاری و روان برای اجرا جلوی دوربین یا نریشن بنویس:\n"
            "  جمله اول یک قلاب فوری برای توقف اسکرول، جملات میانی تحلیل سریع آمار واقعی JSON، و جمله آخر یک دعوت به کامنت‌گذاری.\n"
            "- همچنان هیچ عدد خارج از JSON (حتی عدد ۶۰ یا ۳ ثانیه) در متن ننویس."
        ),
    },
}


def normalize_tone(tone: str | None) -> str:
    t = str(tone or "analytical").strip().lower()
    return t if t in EDITORIAL_TONES else "analytical"


def _num(val: Any) -> float | None:
    """استخراج عدد از مقدار ساده یا شیء Metric ({'value': 1.82, 'n': 10})."""
    if val is None:
        return None
    if isinstance(val, dict):
        val = val.get("value")
    elif hasattr(val, "value") and not isinstance(val, (int, float, str)):
        val = getattr(val, "value", None)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def extract_narrative_hooks(match: MatchFacts | dict[str, Any]) -> list[str]:
    """استخراج خودکار زوایای داستانی/تحلیلی (Narrative Hooks) فقط از داده‌های واقعی MatchFacts."""
    if isinstance(match, MatchFacts):
        data = match.model_dump(mode="json")
    elif isinstance(match, dict):
        data = match
    else:
        return []

    hooks: list[str] = []
    home = data.get("home") or {}
    away = data.get("away") or {}
    h_nm = str(home.get("name_fa") or "تیم میزبان")
    a_nm = str(away.get("name_fa") or "تیم میهمان")

    # ۱) بررسی بیش‌عملکرد / کم‌عملکرد گلزنی نسبت به امید گل (کیفی، بدون ساخت عدد جدید)
    for side_nm, side in ((h_nm, home), (a_nm, away)):
        l5 = side.get("last5") if isinstance(side.get("last5"), dict) else {}
        gf = _num(l5.get("goals_for"))
        pts = _num(l5.get("points"))
        xgf = _num(side.get("xg_for_avg"))
        if pts is not None:
            if int(pts) >= 12:
                hooks.append(f"اوج فرم {side_nm}: عملکرد قدرتمند در بازی‌های اخیر (بر پایهٔ امتیاز ثبت‌شده در JSON).")
            elif int(pts) <= 4:
                hooks.append(f"فشار نتیجه‌گیری روی {side_nm}: افت امتیازگیری در بازی‌های اخیر.")
        if gf is not None and xgf is not None and float(xgf) > 0:
            est_5 = float(xgf) * 5.0
            if float(gf) >= est_5 + 2.5:
                hooks.append(f"بیش‌عملکرد گلزنی {side_nm}: بهره‌وری بالای مهاجمان نسبت به میانگین امید گل.")
            elif float(gf) <= est_5 - 2.5:
                hooks.append(f"کم‌عملکرد گلزنی {side_nm}: خلق موقعیت بهتر از تعداد گل‌های واقعی (پتانسیل بازگشت به میانگین).")

    # ۲) شکاف واضح در خلق موقعیت (xG For) بین دو تیم
    h_xg = _num(home.get("xg_for_avg"))
    a_xg = _num(away.get("xg_for_avg"))
    if h_xg is not None and a_xg is not None:
        diff = float(h_xg) - float(a_xg)
        if diff >= 0.45:
            hooks.append(f"برتری واضح خلق موقعیت برای {h_nm} نسبت به {a_nm} بر پایهٔ میانگین امید گل.")
        elif diff <= -0.45:
            hooks.append(f"برتری واضح خلق موقعیت برای {a_nm} نسبت به {h_nm} حتی در خانهٔ حریف.")

    # ۳) زوایای خبری زنده از recent_news (سرمربی جدید، دربی، تقابل با تیم سابق، مصدوم کلیدی)
    news = data.get("recent_news") or []
    blob = " ".join(str(n.get("title") or n) if isinstance(n, dict) else str(n) for n in news).lower()
    if any(k in blob for k in ("new manager", "first game", "appointed", "sacked", "interim")):
        hooks.append("زاویهٔ داغ نیمکت: اشاره به تحولات تازهٔ سرمربیگری بر پایهٔ تیترهای recent_news.")
    if any(k in blob for k in ("derby", "rivalry", "title race", "six-pointer")):
        hooks.append("حساسیت ویژهٔ مسابقه (دربی یا نبرد مستقیم بالانشینان) بر پایهٔ اخبار زنده.")
    if any(k in blob for k in ("injury", "injured", "ruled out", "suspended", "red card")):
        hooks.append("تأثیر غایبان و مصدومان کلیدی بر ترکیب مسابقه بر پایهٔ تیترهای recent_news.")

    return hooks[:4]


def build_system_prompt(tone: str = "analytical", narrative_hooks: list[str] | None = None) -> str:
    """ترکیب پرامپت استاندارد XGPedia با دستورالعمل لحن انتخابی و زوایای روایی استخراج‌شده."""
    t_key = normalize_tone(tone)
    tone_cfg = EDITORIAL_TONES[t_key]
    parts = [SYSTEM_PROMPT.rstrip(), "", "## دستورالعمل لحن و قالب تحریریه", tone_cfg["directive"]]
    if narrative_hooks:
        parts.append("")
        parts.append("## زوایای داستانی پیشنهادی (بر پایهٔ داده‌های واقعی JSON)")
        for hk in narrative_hooks:
            parts.append(f"- {hk}")
        parts.append("از ۱ یا ۲ زاویهٔ بالا به‌شکل طبیعی در تیتر و کپشن استفاده کن (بدون افزودن هیچ عدد جدید خارج از JSON).")
    return "\n".join(parts) + "\n"
