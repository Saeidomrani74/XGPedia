# XGPedia v0.11 — کیت خط تولید محتوای داده‌محور فوتبال

نسخهٔ ۱۱ کیت شروع (v0.79.0): انتشار تلگرام + خط تولید روزانه + بهبودهای رندر + ابزارهای دروازهٔ ۳ (`check-telegram`، `weekly-report`، GATE3_RUNBOOK — D28) + retry خطای گذرای LLM (D30).

> **شروع از چت جدید؟** اول `docs/NEW_CHAT_HANDOFF.md` را بخوان (وضعیت روز + برنامهٔ
> مرحله‌به‌مرحله + رودمپ کلی + راهنمای محیط).

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
python run.py sync-results --season 2025   REM فصل قبل (آمار بدون xG)
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
| `sync-results [--season 2026\|2025]` | نتایج + xG + شوت/کرنر/کارت → DB | football-data.co.uk |
| `fixtures --days 7` | بازی‌های پیش‌رو با کیک‌آف UTC → DB | football-data.org |
| `list-fixtures [--limit 20]` | فهرست fixture_idهای DB — برای انتخاب آرگومان `facts` (بدون نیاز به sqlite3 CLI) | DB |
| `facts --fixture ID [--out f.json]` | «JSON واقعیت‌ها»: فرم ۵ بازی، میانگین xG، کرنر، تریگرها | DB |
| `draft --fixture ID [--platform telegram] [--post-type preview]` | تولید پیش‌نویس با LLM + عبور از ۷ دروازهٔ validator → ثبت در posts | LLM + DB |
| `list-posts` | فهرست پست‌های ذخیره‌شده | DB |
| `show-post --post-id N` | نمایش کامل draft_json + fact_json یک پست | DB |
| `export-post --post-id N [--out f.json]` | خروجی JSON مستقل یک پست (متادیتا + draft + fact) در `data/exports/` | DB |
| `render-post --post-id N [--out dir]` | رندر کارت تصویری ۱۰۸۰×۱۳۵۰ از پست آرشیوشده + فایل کپشن | DB + قالب HTML |
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
  editorial/     prompt.py + draft.py (جدید) + llm_provider + validate — تولید و اعتبارسنجی متن
  render/        (جدید v0.9) cards.py + templates/ — کارت از draft_json+fact_json+brand با Playwright
tests/           ۶۵ تست: قواعد حیاتی + نگاشت نام + idempotency + null≠0 + تحریریه + رندر
brand/fonts/     (جدید) Vazirmatn woff2 — فونت به‌صورت data URI داخل HTML جاسازی می‌شود
setup.bat        راه‌اندازی ویندوز در یک کلیک
daily-sync.bat   همگام‌سازی روزانه (برای Task Scheduler)
check_env.py     بررسی محیط و توکن و دسترسی منابع
run.py           درگاه خط فرمان
```

## گردش کار روزانه (Workflow A در نسخهٔ جدید)

از v0.10 کل زنجیره یک دستور است — `python run.py daily` (یا `daily-sync.bat`
در Task Scheduler؛ زنجیرهٔ زیر را به‌ترتیب اجرا می‌کند):

```
sync-results → fixtures --days 7        ← هر دو با تحمل خطا؛ DB قبلی می‌ماند
   ↓
status                                   ← اگر عمر داده > ۴ روز: هشدار
   ↓
برای هر بازیِ فردا که پست preview ندارد:
   facts → draft (LLM + ۷ دروازه) → render-post → صف تأیید تلگرام
```

قواعد (D26): اجرای دوبارهٔ همان روز پست تکراری نمی‌سازد (بازیِ دارای پست
رد می‌شود)؛ شکست یک بازی بقیه را نمی‌اندازد (exit code ۱ = اجرا ناقص)؛ بدون
`TELEGRAM_BOT_TOKEN` فقط رندر می‌شود و دستور `publish --post-id` چاپ می‌شود.

دستورهای تک‌قدمی همچنان برای بازبینی دستی کار می‌کنند:

```
python run.py facts --fixture <بازی امروزی> --out data/samples/fact.json
   ↓
python run.py draft --fixture <بازی امروزی>       ← تولید متن با LLM + ۷ دروازه
   ↓
python run.py list-posts / show-post              ← بازبینی پیش‌نویس
   ↓
python run.py export-post --post-id N             ← JSON مستقل برای آرشیو/برداشتن
   ↓
python run.py render-post --post-id N             ← کارت ۱۰۸۰×۱۳۵۰ + کپشن در output/
```

نمونهٔ اجرای daily با تاریخ و سقف دلخواه:

```
python run.py daily --date 2026-11-19 --limit 4 --format 4:5
python run.py daily --no-submit     # فقط رندر؛ صف تأیید نه
python run.py daily --no-sync       # بدون شبکه، از DB موجود
```

### لایهٔ تحریریه چطور کار می‌کند (جدید در v0.8.5)

`python run.py draft --fixture <id>` این زنجیره را اجرا می‌کند:

1. فکت‌ها از DB با همان `build_match_facts` ساخته می‌شوند (ورودیِ واحد).
2. `SYSTEM_PROMPT` (در `editorial/prompt.py`) همراه JSON فکت‌ها به مدل می‌رود؛
   تنها منبع مجاز مدل همین JSON است — نه حافظه‌اش.
3. خروجی مدل با `DraftOutput.from_json` پارس می‌شود (کلیدهای غیرمجاز رد).
4. **source_note هرگز از مدل نمی‌آید** — کد آن را با provider/زمان/hash می‌سازد.
5. هفت دروازهٔ `validate.py`؛ رد شد → یک بار retry با عین خطاها به مدل؛
   دوباره رد شد → `RejectedDraft` و بررسی انسانی (خط خروج `exit 1`).
6. پست معتبر در جدول `posts` با `status='validated'` و `content_version` تازه
   ذخیره می‌شود (draft_json + fact_json — هر دو آرشیو می‌شوند).

کلید LLM در `.env`: `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` — هر سرویس
سازگار با OpenAI Chat Completions (OpenAI، DeepSeek، OpenRouter، z-ai و ...)؛
نمونه‌ها در `.env.example`.

### لایهٔ رندر چطور کار می‌کند (v0.10 — طراحی استودیو)

`python run.py render-post --post-id N [--format 4:5|9:16|16:9] [--layout smart|v1|v2|v3]` این زنجیره را اجرا می‌کند:

1. ردیف پست از DB خوانده می‌شود — ورودی رندر **همان draft_json + fact_json آرشیوشده**
   است؛ یعنی تصویر دقیقاً از همان داده‌هایی ساخته می‌شود که متن از آن‌ها نوشته شد.
2. `render/cards.py` از این دو JSON + `brand/brand.json` (بخش matchday_palette) +
   `config/team_identities.json` (کد و رنگ رسمی هر تیم) یک context می‌سازد:
   تاریخ جلالی و ساعت تهران با ارقام فارسی؛ ارقام آماری لاتین tabular؛
   احتمال‌های ۱X۲، ضرایب منصفانه و ماتریس پواسون به‌صورت قطعی از دو عدد xG با
   مدل Dixon-Coles مشتق می‌شوند (`analytics/metrics.py`)؛ ماژولی که داده‌اش نیست
   رندر نمی‌شود (null≠0).
3. قالب `templates/match_preview.html.j2` — بازپیاده‌سازی عینی `tools/matchday_studio.html`
   (استودیوی مرجع طراحی): ۹ ماژول (stats/radar/focus/watchout/keyduel/poisson/wave/trend10/signals)،
   چیدمان smart (داده‌محور) یا v1/v2/v3، سه فرمت خروجی.
   فونت‌ها (Vazirmatn + Space Grotesk + JetBrains Mono) data URI درون‌جاسازی می‌شوند.
4. Playwright (Chromium) بعد از `document.fonts.ready` اسکرین‌شات می‌گیرد:
   تلگرام/سایت → PNG؛ اینستاگرام → JPEG (الزام API).
5. خروجی در **`output/`** (قابل تغییر با `--out`): تصویر `post_{id}_v{ver}_{type}_{W}x{H}.{png|jpeg}`
   + فایل کپشن `.txt` (کپشن + هشتگ ثابت نوع پست) + HTML میانی (خودبسنده).

دارایی‌های تیمی: `python tools/fetch_crests.py` لوگوی رسمی SVG تیم‌ها را در
`brand/crests/{CODE}.svg` می‌گذارد (۲۰/۲۰ تیم لیگ برتر موجود است). تیمِ بدون فایل با
نشان انتزاعی یک‌دستِ خود استودیو (رنگ + کد) رندر می‌شود.

نقشهٔ دارایی‌ها و ماژول‌های منتظرِ داده (رادار صدک، مهرهٔ کلیدی، موج زمانی، +EV،
کارت بازیکن، عکس بازیکن، …): **`docs/ROADMAP.md`**.

**شروع در چت/محیط جدید؟** اول `docs/HANDOFF.md` (وضعیت کامل پروژه و قواعد حیاتی)
سپس `docs/NEXT_STEPS.md` (برنامهٔ مرحله‌به‌مرحله) را بخوانید.

پیش‌نیاز (یک بار): `pip install -e ".[render]"` سپس `playwright install chromium`.

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
| `Error: FOOTBALL_DATA_ORG_TOKEN is not set` با وجود .env پرشده | در نسخه‌های قبل از 0.8.3 فایل .env load نمی‌شد؛ یا Notepad پسوند پنهان `.txt` اضافه کرده | به v8.3+ ارتقا دهید؛ در Explorer گزینهٔ File name extensions را روشن کنید — نام باید دقیقاً `.env` و در ریشهٔ پکیج باشد (فاصله بعد از `=` اشکالی ندارد) |
| `pytest: No module named pytest` | نصب توسعه‌ای بدون dev | `pip install pytest` (در setup.bat خودکار است) |
| خطای ۴۲۹ در fixtures | سقف ۱۰ درخواست/دقیقه football-data.org | چند ثانیه صبر؛ آداپتر خودش backoff می‌زند |
| تازگی داده > ۴ روز در status | تعطیلی بین‌المللی یا تغییر ساختار CSV | فایل خام همان روز را در `data/raw/` ببینید |

## دروازه‌ها (بدون تغییر)

- **Gate 2 (پایان هفتهٔ ۳):** اگر آزمون پوشش روی ۵ مسابعه زیر آستانه بود یا CSV بیش از ۴ روز کهنه ماند → ارتقای API-Football Pro (۱۹ دلار/ماه، کنترل قیمت checkout طبق D18).

## سند مرجع

جزئیات راستی‌آزمایی منابع و دلیل انتخاب: «XGPedia_تحلیل_منابع_داده.docx» (همراه این پکیج در `docs/`).
