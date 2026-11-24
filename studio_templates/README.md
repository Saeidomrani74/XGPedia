# XGPedia Studio HTML Reference Templates (v0.30.2)

این پوشه شامل فایل‌های HTML مرجع (طراحی ۱:۱) برای تمام ۷ خانوادهٔ کارت در XGPedia است.
**قانون دائمی تطابق ۱:۱**: هنگام توسعه یا به‌روزرسانی هر کارت در `src/xgpedia/render/card_kit/`، تمام جزئیات گرافیکی (واترمارک‌ها، قوس‌ها، خطوط نقطه‌چین، شفافیت کادرها، گرادیان‌ها، آیکون‌ها و تناسبات) باید عیناً و بدون ساده‌سازی از این قالب‌ها پورت شوند و به‌صورت ۱۰۰٪ آفلاین (بدون CDN) با فریم چهارگوشهٔ قرمز استاندارد رندر شوند.

| فایل مرجع | خانوادهٔ کارت | تصمیم معماری | نوع ساختار | فایل رندر پایتون |
|---|---|---|---|---|
| `pre_match.html` | پیش‌بازی (Pre-Match) | D43 | **ماژولار** (عرض `½`/`۱` + ترتیب + ۵ قالب) | `src/xgpedia/render/card_kit/pre_match_card.py` |
| `post_match.html` | پس‌ازبازی (Post-Match) | D44 | **ماژولار** (عرض `½`/`۱` + ترتیب + ۵ قالب) | `src/xgpedia/render/card_kit/post_match_card.py` |
| `on_this_day.html` | در چنین روزی (On This Day) | D45 | **اسلایدی** (۴ اسلاید + ماژول‌های داخلی) | `src/xgpedia/render/card_kit/on_this_day_card.py` |
| `breaking_news.html` | خبر فوری و رسمی (Breaking News) | D46 | **اسلایدی** (۴ اسلاید + فیلتر نور ملایم) | `src/xgpedia/render/card_kit/news_card.py` |
| `birthday.html` | استودیو تولد (Birthday Studio) | D47 | **اسلایدی** (۳ مود + منحصراً Soccer) | `src/xgpedia/render/card_kit/birthday_card.py` |
| `transfer_radar.html` | رادار نقل‌وانتقالات (Transfer Radar) | D48 | **ماژولار** (عرض `½`/`۱` + ترتیب + ۵ قالب + کادر بالایی شفاف) | `src/xgpedia/render/card_kit/transfer_radar_card.py` |
| `this_or_that.html` | این یا اون (This or That) | D49 | **اسلایدی** (۴ چیدمان + ۱۰ دوئل آماده + پیشنهاد زنده) | `src/xgpedia/render/card_kit/this_or_that_card.py` |
