# XGPedia Studio HTML Reference Templates (v0.31.0)

این پوشه شامل فایل‌های HTML مرجع (طراحی ۱:۱) برای تمام ۱۱ خانوادهٔ کارت در XGPedia است.
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
| `players_rating.html` | نمرات بازیکنان (Players Rating) | D51 | **ماژولار** (عرض `½`/`۱` + ترتیب + ۵ قالب + زمین استادیوم وکتور) | `src/xgpedia/render/card_kit/players_rating_card.py` |
| `standings.html` | جدول رده‌بندی (Standings Studio) | D52 | **ماژولار** (عرض `½`/`۱` + ترتیب + ۵ قالب + لنز کلاسیک/xPTS/xG + کوادرانت) | `src/xgpedia/render/card_kit/standings_card.py` |
| `injury_lab.html` | آزمایشگاه مصدومیت (Injury Lab) | D53 | **ماژولار** (عرض `½`/`۱` + ترتیب + ۵ قالب + اسکنر آناتومی ۷ ناحیه) | `src/xgpedia/render/card_kit/injury_card.py` |
| `player_profile.html` | پروفایل فنی بازیکن (Player Studio) | D54 | **ماژولار** (عرض `½`/`۱` + ترتیب + ۵ قالب + رادار/شوت‌مپ/فرم/DNA) | `src/xgpedia/render/card_kit/player_card.py` |
- `h2h_teams.html` → کارت ماژولار تقابل مستقیم تیم‌ها (D55 — `h2h_teams_card.py`)
- `player_fc27.html` → کارت ماژولار بازیکن FC27 (D56 — `player_fc27_card.py`)
- `h2h_players.html` → کارت ماژولار مقایسه دو بازیکن (D57 — `h2h_players_card.py`)
- `top_scorers.html` → کارت ماژولار جدول گلزنان / کفش طلا (D58 — `top_scorers_card.py`)
- `matchday_results.html` → کارت ماژولار نتایج ۲۴ ساعت اخیر (D59 — `matchday_results_card.py`)
