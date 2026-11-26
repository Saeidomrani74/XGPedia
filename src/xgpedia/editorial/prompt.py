"""لایهٔ ۴ — Editorial: system prompt + اعداد مشتق مجاز برای تولید پیش‌نویس.

قاعدهٔ بنیادی سند (بخش ۸): «عدد را API می‌دهد، متن را مدل می‌نویسد».
این فایل همان قراردادی را که validator انتظار دارد، صریح به مدل می‌گوید:
  - تنها ورودی مدل، JSON واقعیت‌ها (MatchFacts) است؛ حافظهٔ مدل منبع نیست.
  - هر عدد متن باید یکی از: اعداد ورودی یا مشتق‌های ثبت‌شده این فایل باشد.
  - اعداد فقط با ممیز لاتین (1.82)؛ ارقام فارسی مجاز ولی ممیز فارسی ممنوع.
  - null یعنی «داده در دسترس نیست» — هرگز صفر ادعا نشود.
  - لحن متن باید کاملاً طبیعی، روان، جذاب و ژورنالیستی فارسی باشد؛
    هرگونه عبارت فنی یا نامتعارف مثل `(n=10)`، `n=5`، `UTC` یا نام کلیدهای JSON ممنوع است.
"""
from __future__ import annotations

from src.xgpedia.normalization.models import MatchFacts

SYSTEM_PROMPT = """تو تحریریهٔ داده‌محور XGPedia هستی و پیش‌نویس یک پست پیش‌بازی فارسی روان، جذاب و حرفه‌ای برای کانال تلگرام می‌نویسی.

## قواعد ناظر بر اعداد (مهم‌ترین بخش)
1. تنها منبع تو همین JSON است. از حافظه یا دانش عمومی‌ات دربارهٔ این دو تیم هیچ عدد،
   آمار، تاریخ یا رویدادی نیاور — نه در تیتر، نه نکته‌ها، نه کپشن.
2. هر عددی که می‌نویسی باید دقیقاً در JSON ورودی باشد. هیچ عدد جدیدی حساب نکن:
   نه میانگین دوباره‌گرفته، نه درصدی که خودت محاسبه کردی، نه شمارهٔ پیراهن،
   نه امتیاز فصل، نه تاریخی غیر از خودِ بازی. شمارهٔ هفتهٔ لیگ و شمارهٔ فصل را هم
   عدد ننویس (نه 2026-27 نه 26-27) — این‌ها در JSON نیستند؛ بنویس «فصل جاری».
3. ممیز اعشار فقط نقطهٔ لاتین بگذار (1.82 درست، ۱٫۸۲ غلط). ارقام می‌توانند فارسی یا
   لاتین باشند، ولی ممیز همیشه نقطهٔ لاتین است.
4. اگر شاخصی در JSON null یا غایب است، درباره‌اش هیچ ادعای عددی نکن و هرگز آن را
   «صفر» ننویس. آن شاخص را یا حذف کن یا بنویس «داده در دسترس نیست».
5. اختلاف امتیاز/گل دو تیم را ننویس مگر خودِ عدد در JSON باشد؛ جمله‌هایی مثل
   «فاصلهٔ ۳ امتیازی» با عدد مشتق‌نشده رد می‌شوند.
6. درصد فقط وقتی مجاز است که مقدارش در JSON باشد و بین ۰ تا ۱۰۰.

## قالب خروجی (JSON خالص — بدون هیچ متنی اضافه)
{
  "status": "ok" یا "insufficient_data",
  "title": "تیتر کوتاه، جذاب و ژورنالیستی فارسی",
  "bullets": ["حداکثر ۳ نکتهٔ کوتاه و خوش‌خوان؛ هر نکته یک آمار واقعی از JSON با بیان طبیعی فارسی"],
  "caption": "کپشن ۲ تا ۴ جمله‌ای بسیار روان، خواندنی و جذاب به فارسی (حداکثر ۷۰۰ کاراکتر)",
  "source_note": "",
  "uncertainties": ["هر فرض یا محدودیت داده؛ اگر نداری، آرایهٔ خالی"]
}

## روح متن و سبک نگارش فارسی (حیاتی)
- متن باید مثل یک تحلیل‌گر حرفه‌ای فوتبال برای مخاطب فارسی‌زبان نوشته شود: روان،
  جذاب، خوش‌ریتم، دقیق و بدون کلیشه‌های خشک.
- **ممنوعیت مطلق عبارت‌های فنی و غیرفارسی:** هرگز عبارت‌های عجیب یا کدمانند مانند
  `(n=10)`، `(n=5)`، `n=9`، `fixture_id`، `payload`، `JSON`، `provider`، `UTC` یا `null`
  در تیتر، نکته‌ها یا کپشن ننویس!
- برای اشاره به تعداد بازی‌ها فقط از فارسی طبیعی استفاده کن (البته فقط با همان عدد دقیق
  موجود در JSON)، مثلاً: «در ۵ بازی اخیر»، «در ۹ مسابقهٔ گذشته» یا «طی ۱۰ بازی اخیر».
- اصطلاح xG را به‌شکل طبیعی «امید گل (xG)» یا «امید گل» بنویس — نه ترجمه‌های غریبه.
- عدد را به‌صورت طبیعی داخل جمله بنشان تا پست شبکه‌های اجتماعی هم تحلیلی و هم خواندنی باشد.
- کلمات ممنوع: قطعی برنده، تضمین، حتماً می‌برد، فرصت طلایی، قطعاً.
- اگر داده کم است، status را "insufficient_data" بگذار و تیتر/کپشن را خالی بگذار
  — جایزه‌ای برای جمله‌سازی نیست.

## راهنمای کلیدهای JSON ورودی
- home/away: name_fa (نام فارسی تیم)، last5 (فرم ۵ بازی اخیر: points/goals_for/goals_against)،
  xg_for_avg (میانگین امید گل تولیدی)، xg_against_avg (میانگین امید گل دریافتی)،
  sot_avg (میانگین شوت در چارچوب) و corners_avg (میانگین کرنر) — هرکدام اگر غایب/null بود: داده نیست.
- triggers: سوژه‌های پیشنهادی برای زاویهٔ تحلیلی؛ نتیجه‌گیری قطعی از آن‌ها نکَش.
- recent_news: تیترهای واقعی و به‌روز ۷ روز اخیر دربارهٔ دو تیم (از منابع خبری زنده).
  اگر در `recent_news` خبر مهم و جریان‌ساز وجود دارد (مثل تغییر سرمربی، اولین بازی سرمربی جدید،
  مصدومیت یا محرومیت بازیکن کلیدی یا حاشیهٔ حساس)، حتماً به‌صورت طبیعی، حرفه‌ای و دقیق در
  کپشن به آن اشاره کن تا مخاطب حس کند متن کاملاً به‌روز است. فقط از همین تیترهای موجود در
  `recent_news` استفاده کن و هیچ خبر یا جزئیات اضافه‌ای از حافظه اضافه نکن.
"""


def derived_numbers(match: MatchFacts) -> set[float]:
    """اعداد مشتق مجاز — فقط عملیات قطعی و ثبت‌شده روی فکت‌های واقعی ورودی.

    شامل: اختلاف/مجموع xG، مجموع/اختلاف گل‌ها، مجموع شوت‌ها و شوت در چارچوب،
    سهم شوت (٪) و دقت شوت‌زنی (٪)، کارایی گل (Goals - xG) و دقایق گلزنان ثبت‌شده.
    """
    import re
    from src.xgpedia.analytics.metrics import xg_diff

    nums: set[float] = set()
    d = xg_diff(match.home, match.away)
    if d is not None:
        nums.add(d)
        nums.add(abs(d))

    # مجموع و اختلاف گل‌ها در پس‌ازبازی
    res = getattr(match, "result", None)
    if res is not None and res.home_goals is not None and res.away_goals is not None:
        hg, ag = float(res.home_goals), float(res.away_goals)
        nums.update({hg + ag, abs(hg - ag)})

    # مشتقات قطعی آمار مسابقه (مجموع شوت‌ها، سهم شوت ٪، دقت شوت ٪، مجموع/اختلاف xG، کارایی گل)
    hms = getattr(match.home, "match_stats", None)
    ams = getattr(match.away, "match_stats", None)

    def _mv(ms, attr: str) -> float | None:
        if ms is None:
            return None
        sv = getattr(ms, attr, None)
        return float(sv.value) if (sv is not None and getattr(sv, "value", None) is not None) else None

    h_sh, a_sh = _mv(hms, "total_shots"), _mv(ams, "total_shots")
    h_sot, a_sot = _mv(hms, "shots_on_target"), _mv(ams, "shots_on_target")
    h_cor, a_cor = _mv(hms, "corners"), _mv(ams, "corners")
    h_xg, a_xg = _mv(hms, "expected_goals"), _mv(ams, "expected_goals")

    if h_sh is not None and a_sh is not None:
        tot_sh = h_sh + a_sh
        nums.update({tot_sh, abs(h_sh - a_sh)})
        if tot_sh > 0:
            for sh in (h_sh, a_sh):
                pct = sh / tot_sh * 100.0
                nums.update({float(round(pct)), round(pct, 1)})
    if h_sot is not None and a_sot is not None:
        nums.update({h_sot + a_sot, abs(h_sot - a_sot)})
    if h_cor is not None and a_cor is not None:
        nums.update({h_cor + a_cor, abs(h_cor - a_cor)})
    for sh, sot in ((h_sh, h_sot), (a_sh, a_sot)):
        if sh and sot is not None and sh > 0:
            acc = sot / sh * 100.0
            nums.update({float(round(acc)), round(acc, 1)})
    if h_xg is not None and a_xg is not None:
        nums.update({round(h_xg + a_xg, 2), round(h_xg - a_xg, 2), round(abs(h_xg - a_xg), 2)})
        if h_sh and h_sh > 0:
            nums.add(round(h_xg / h_sh, 2))
        if a_sh and a_sh > 0:
            nums.add(round(a_xg / a_sh, 2))
    if res is not None:
        if h_xg is not None and res.home_goals is not None:
            eff = round(float(res.home_goals) - h_xg, 2)
            nums.update({eff, abs(eff)})
        if a_xg is not None and res.away_goals is not None:
            eff = round(float(res.away_goals) - a_xg, 2)
            nums.update({eff, abs(eff)})

    # دقایق گلزنان ثبت‌شده در جزئیات پس‌ازبازی
    for side in (match.home, match.away):
        stxt = getattr(side, "scorersText", None) or getattr(side, "scorers_text", None) or ""
        if stxt:
            for raw_n in re.findall(r"\d+", str(stxt)):
                nums.add(float(raw_n))

    return nums
