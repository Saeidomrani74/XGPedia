# XGPedia v8 — کیت خط تولید با منابع دادهٔ جدید

نسخهٔ ۸ کیت شروع، پس از قطع دسترسی پلن رایگان API-Football به فصل‌های جاری (پاییز ۲۰۲۶).

## چه چیزی عوض شد؟

| | نسخهٔ ۷ (قبلی) | نسخهٔ ۸ (این پکیج) |
|---|---|---|
| منبع xG و آمار مسابقه | API-Football (پلن رایگان) | **football-data.co.uk** — CSV هفتگی، بدون کلید |
| بازی‌های پیش‌رو و جدول | API-Football | **football-data.org** — API رسمی، توکن رایگان |
| هزینه | ۰ (تا محدودیت) | **۰** |
| وابستگی به سرویس در حال مرگ | Understat/FotMob حذف شدند | هیچ‌کدام استفاده نمی‌شوند |
| API-Football | منبع اصلی | فقط fallback پولی (کد باقی است) |

### چرا این دو منبع؟

راستی‌آزمایی ۱۵ نوامبر ۲۰۲۶ (جزئیات در سند «تحلیل منابع داده»):

- **football-data.co.uk** — فایل `E0.csv` فصل جاری ۲۰۲۷–۲۰۲۶ با ستون‌های **xG هر دو تیم** (`HxG`/`AxG`)، شوت، شوت در چارکوب، کرنر، کارت. به‌روز تا ۸ نوامبر ۲۰۲۶ در آزمون. بدون ثبت‌نام، بدون rate limit، بدون کلید.
- **football-data.org** — لیگ برتر در ۱۲ مسابقهٔ رایگان همیشگی؛ بازی‌های پیش‌رو با ساعت کیک‌آف UTC، جدول، ترکیب. ۱۰ درخواست بر دقیقه (برای خط تولید ما کافی است). **xG ندارد** — به همین دلیل xG فقط از منبع اول می‌آید و قاعدهٔ «عدم ادغام xG دو provider» رعایت می‌شود.

### محدودیت‌های شناخته‌شده

1. **xG فقط از فصل ۲۰۲۷–۲۰۲۶**: فایل فصل قبل (۲۰۲۶–۲۰۲۵) آمار کامل شوت دارد ولی ستون xG خالی است. برای کالیبرهٔ thresholds با xG تاریخی، منبع دیگری لازم خواهد شد (تصمیم Gate 2).
2. **به‌روزرسانی CSV هفتگی است** و ساعت دقیق آن تضمین نشده؛ `daily-sync.bat` هر روز می‌گیرد و `status` عمر داده را هشدار می‌دهد (آستانه: ۴ روز).
3. **ساعت کیک‌آف در CSV نیست**؛ برای بازی‌های پیش‌رو از football-data.org بیایید (دقیق و UTC).

## قانون طلایی (بدون تغییر)

عدد را API می‌دهد، متن را مدل زبانی می‌نویسد، تصویر را قالب HTML می‌سازد و
انتشار را زمان‌بند انجام می‌دهد — مدل زبانی هرگز عددی از حافظهٔ خودش نمی‌نویسد.
هر عددِ منتشرشده باید تا پاسخ خام provider ردیابی‌پذیر باشد.

## شروع سریع روی ویندوز

**مهم:** هر بار نسخهٔ جدید را در یک **پوشهٔ تازه** باز کنید — extract روی پوشهٔ نسخهٔ قبلی، فایل‌های به‌جامانده از نسخهٔ قبل را باقی می‌گذارد و باعث ImportError در تست‌ها می‌شود.

```bat
REM ۱) پیش‌نیاز: Python 3.12+ از python.org (تیک Add to PATH هنگام نصب)
REM ۲) دابل‌کلیک روی:
setup.bat

REM ۳) توکن رایگان football-data.org را در .env بگذارید:
REM    FOOTBALL_DATA_ORG_TOKEN=...
REM    (ثبت‌نام: https://www.football-data.org — مجانی)

REM ۴) بررسی محیط:
python check_env.py

REM ۵) دریافت داده:
python run.py sync-results                 REM نتایج + xG فصل جاری → DB
python run.py sync-results --season 2026   REM فصل قبل (آمار بدون xG)
python run.py fixtures --days 7            REM بازی‌های پیش‌رو
python run.py status                       REM تازگی داده
python run.py list-fixtures                REM فهرست fixture_idها برای facts
```

### چرا خروجی ترمینال همه انگلیسی است؟

سه دلیل — هر سه محدودیت خود ویندوز است، نه انتخاب سلیقه‌ای:

1. **فایل‌های bat**: پردازشگر `cmd.exe` فایل‌های bat حاوی متن فارسی/UTF-8 را غلط تجزیه می‌کند (دستورها از وسط می‌شکنند — مثل `'cho' is not recognized`).
2. **متن فارسی در کنسول**: کنسول قدیمی ویندوز (`cmd.exe`) متن راست‌به‌چپ را درست شکل نمی‌دهد — حروف فارسی جدا و برعکس نمایش داده می‌شوند. این مشکل رندر خود ویندوز است و از داخل کد قابل اصلاح نیست.
3. بنابراین **همهٔ پیام‌های ترمینال (bat + پایتون) انگلیسی/ASCII** هستند تا در هر ترمینالی درست دیده شوند. اسناد و گزارش‌های فایل (README، docs/، provider-test.md) فارسی می‌مانند چون در ادیتور/مرورگر درست رندر می‌شوند.

### روی لینوکس/مک

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python run.py init
python -m pytest tests/ -v
python run.py sync-results
```

## دستورات run.py

| دستور | کار | منبع |
|---|---|---|
| `init` | ساخت SQLite | — |
| `sync-results [--season 2027\|2026]` | نتایج + xG + شوت/کرنر/کارت → DB | football-data.co.uk |
| `fixtures --days 7` | بازی‌های پیش‌رو با کیک‌آف UTC → DB | football-data.org |
| `list-fixtures [--limit 20]` | فهرست fixture_idهای DB — برای انتخاب آرگومان `facts` (بدون نیاز به sqlite3 CLI) | DB |
| `facts --fixture ID [--out f.json]` | «JSON واقعیت‌ها»: فرم ۵ بازی، میانگین xG، کرنر، تریگرها | DB |
| `status` | تازگی داده + آمار DB + هشدار کهنگی | DB |
| `test-provider --matches 5` | آزمون پوشش فیلدها → `docs/provider-test.md` | football-data.co.uk |

شناسهٔ fixture برای `facts`: `fdcouk:<تاریخ>:<خانگی>:<میهمانی>` مثل:
`fdcouk:2026-11-08:Manchester United:Aston Villa` — لیست کامل: `python run.py list-fixtures`

## ساختار

```
config/          team_mapping.json (جدید) + thresholds + glossary (فصل ۲۷-۲۶)
src/xgpedia/
  providers/     football_data_couk.py (جدید) + football_data_org.py (جدید) + api_football.py (fallback)
  normalization/ Pydantic schema؛ null≠0 (بدون تغییر)
  analytics/     محاسبهٔ قطعی (بدون تغییر)
  sync.py        (جدید) CSV/API → DB + ساخت MatchFacts + پایش تازگی
tests/           ۳۶ تست: قواعد حیاتی + نگاشت نام + idempotency + null≠0
setup.bat        راه‌اندازی ویندوز در یک کلیک
daily-sync.bat   همگام‌سازی روزانه (برای Task Scheduler)
check_env.py     بررسی محیط و توکن و دسترسی منابع
run.py           درگاه خط فرمان
```

## گردش کار روزانه (Workflow A در نسخهٔ جدید)

```
daily-sync.bat (یا اجرای دستی ۲ دستور sync)
   ↓
python run.py status          ← اگر عمر داده > ۴ روز: هشدار
   ↓
python run.py facts --fixture <بازی امروزی> --out data/samples/fact.json
   ↓
(هفته‌های بعد) لایهٔ تحریریه و رندر روی fact.json کار می‌کنند — بدون تغییر در schema
```

## قواعد حیاتی که این نسخه رعایت می‌کند

- **null ≠ 0**: ردیفی که CSV مقدار نداد اصلاً درج نمی‌شود؛ «۰ کرنر» هرگز نمایش داده نمی‌شود.
- **idempotency**: اجرای دوبارهٔ sync هیچ رکورد تکراری نمی‌سازد (کلید: fixture_id + team + metric + provider).
- **provenance**: هر CSV خام با sha256 در `data/raw/` ذخیره می‌شود؛ هر عدد تا فایل خام ردیابی‌پذیر است.
- **عدم ادغام xG دو provider**: متریک expected_goals فقط با provider `football-data-co-uk` ذخیره می‌شود.
- **فصل جدید = فقط یک خط**: `CURRENT_SEASON_START` در `config.py` + نام تیم‌های صعودکرده در `team_mapping.json`.

## عیب‌یابی ویندوز

| علامت | علت | راه‌حل |
|---|---|---|
| `'python' is not recognized` | پایتون در PATH نیست | نصب مجدد با تیک «Add python.exe to PATH»؛ یا اجرای bat از داخل «Command Prompt» بعد از `py -3` |
| پیام‌های عجیب قطعه‌قطعه در bat (مثل `'cho' is not recognized`) | فایل bat ویرایش شده و متن فارسی گرفته | نسخهٔ سالم را از zip دوباره باز کنید؛ فایل‌های bat فقط ASCII بمانند |
| `ImportError: cannot import name ...` در تست‌ها | **فایل‌های به‌جامانده از نسخهٔ قبلی** — extract جدید روی پوشهٔ قدیمی انجام شده | پوشهٔ قدیمی را کامل حذف/تغییرنام دهید و zip را در پوشهٔ تازه باز کنید، بعد setup.bat |
| فارسی برعکس/جدا در ترمینال | کنسول ویندوز متن RTL را درست رندر نمی‌کند | طبیعی است — خروجی‌های ترمینال این پکیج انگلیسی است؛ فارسی فقط در فایل‌ها و اسناد است |
| `[FAIL] football-data.co.uk ... handshake timed out` | کندی/فیلترینگ شبکه به میزبان CSV | check_env سه بار تلاش می‌کند؛ اگر باز هم نشد VPN یا ساعت دیگری امتحان کنید |
| `pytest: No module named pytest` | نصب توسعه‌ای بدون dev | `pip install pytest` (در setup.bat خودکار است) |
| خطای ۴۲۹ در fixtures | سقف ۱۰ درخواست/دقیقه football-data.org | چند ثانیه صبر؛ آداپتر خودش backoff می‌زند |
| تازگی داده > ۴ روز در status | تعطیلی بین‌المللی یا تغییر ساختار CSV | فایل خام همان روز را در `data/raw/` ببینید |

## دروازه‌ها (بدون تغییر)

- **Gate 2 (پایان هفتهٔ ۳):** اگر آزمون پوشش روی ۵ مسابعه زیر آستانه بود یا CSV بیش از ۴ روز کهنه ماند → ارتقای API-Football Pro (۱۹ دلار/ماه، کنترل قیمت checkout طبق D18).

## سند مرجع

جزئیات راستی‌آزمایی منابع و دلیل انتخاب: «XGPedia_تحلیل_منابع_داده.docx» (همراه این پکیج در `docs/`).
