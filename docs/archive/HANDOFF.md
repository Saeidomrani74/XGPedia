# HANDOFF — سند انتقال پروژهٔ XGPedia به چت جدید

> **به‌روزرسانی 2026-11-21:** وضعیت «اول بخوان» به `docs/NEW_CHAT_HANDOFF.md` منتقل شد
> (v0.11.1 · ۱۵۲ تست). این سند همچنان **مرجع معماری، قواعد طلایی و خطاهای دیده‌شده** است.

> **این فایل را اول بخوان.** هرچیز لازم برای ادامهٔ کار از همین‌جا شروع می‌شود.
> وضعیت: ۱۴۰۵/۰۸/۲۶ (2026-11-17) · نسخهٔ کد: v0.9.0 · شعبهٔ git: `main`
> آخرین کامیت: `be08d56 «Final CH 4»` (مخزن: github.com/Saeidomrani74/XGPedia)

---

## ۰) خلاصهٔ یک‌پاراگرافی — پروژه چیست و کجاست

XGPedia یک خط تولید محتوای فوتبال داده‌محور فارسی (لیگ برتر انگلیس) است:
**عدد را API می‌دهد، متن را مدل زبانی می‌نویسد، تصویر را قالب HTML می‌سازد و انتشار را زمان‌بند انجام می‌دهد.**
هفت لایه پیاده‌سازی و تست شده: Provider → Normalization → Analytics → Editorial (LLM+۷ دروازه) → DB (SQLite) → Rendering (HTML→PNG با Playwright) → انتشار (ربات تلگرام نوشته شده، هنوز یکپارچه نشده).
داده زندهٔ واقعی در DB هست (۴۹۰ بازی، ۶۹۲۰ ردیف آمار، xG فصل 2026-27)، یک پست کامل «پیش‌بازی» با همهٔ مراحل تولید→اعتبارسنجی→آرشیو→رندر انجام و تحویل شده، و **۹۷/۹۷ تست سبز** است.

---

## ۱) قانون طلایی و قواعد حیاتی (هرگز نقض نشود)

1. **عدد از کد/API، متن از مدل**: مدل زبانی هرگز عددی از حافظهٔ خودش نمی‌نویسد؛ تنها منبعش JSON واقعیت‌ها (MatchFacts) است. هر عددِ منتشرشده تا فایل خام provider (sha256 در `data/raw/`) ردیابی‌پذیر است.
2. **null ≠ 0**: دادهٔ غایب هرگز «۰» نمایش داده نمی‌شود؛ «داده در دسترس نیست». ردیفی که CSV مقدار نداد اصلاً درج نمی‌شود.
3. **عدم ادغام xG دو provider**: متریک `expected_goals` فقط از `football-data-co-uk` می‌آید.
4. **idempotency**: اجرای دوبارهٔ sync رکورد تکراری نمی‌سازد (کلید: fixture_id + team + metric + provider؛ پست: fixture_id + post_type + platform + content_version).
5. **source_note فقط از کد ساخته می‌شود** (provider + زمان + hash) — هرگز از مدل.
6. **رنگ/فونت فقط از `brand/brand.json`** (بخش `matchday_palette`) و **رنگ/کد تیم از `config/team_identities.json`** — هیچ رنگی در کد یا قالب هاردکد نمی‌شود.
7. **منبع طراحی کارت = `tools/matchday_studio.html`** — هر تغییر بصری اول آنجا، بعد قالب `match_preview.html.j2`.
8. **ارقام آماری لاتین با tabular-nums؛ تاریخ/ساعت جلالی با ارقام فارسی؛ نام‌های لاتین داخل `<bdi>`؛ ممیز لاتین.**
9. فایل‌های `.bat` فقط ASCII بمانند (کنسول ویندوز UTF-8 را خراب می‌کند)؛ پیام‌های ترمینال `run.py` انگلیسی، اسناد فارسی.
10. **extract نسخهٔ جدید همیشه در پوشهٔ تازه** — فایل‌های به‌جامانده از نسخهٔ قبل باعث ImportError می‌شود.

---

## ۲) معماری و جریان داده

```
football-data.co.uk (CSV هفتگی، xG/شوت/کرنر/کارت — بدون کلید)
football-data.org  (API بازی‌های پیش‌رو + جدول — توکن رایگان، ۱۰ req/min)
API-Football       (فقط fallback پولی؛ کد هست، مصرف نمی‌شود)
        │
        ▼ providers/ (سه آداپتر با backoff/timeout)
normalization/ (Pydantic: MatchFacts — «JSON واقعیت‌ها»؛ کلید همه‌چیز)
        │
        ▼
analytics/metrics.py (محاسبهٔ قطعی: میانگین‌ها، triggers،
        │             Dixon-Coles → ماتریس ۵×۵ + xPts + ضرایب منصفانه)
        ▼
DB SQLite (data/dev.sqlite — fixtures, fixture_statistics, raw_payloads, posts, …)
        │
        ├──► editorial/ (SYSTEM_PROMPT + LLMProvider → DraftOutput → ۷ دروازهٔ validate.py
        │                → retry یک‌بار → ذخیره در posts با status=validated)
        │
        └──► render/ (draft_json + fact_json آرشیوشده + brand + team_identities
                      → context → match_preview.html.j2 (۹ ماژول، ۳ فرمت)
                      → Playwright/Chromium → PNG تلگرام / JPEG اینستاگرام)
                       + کپشن .txt + JSON مستقل (export-post → data/exports/)
```

**کلید معماری رندر**: ورودی رندر *همان دو JSON آرشیوشده در جدول posts* است — تصویر دقیقاً از همان داده‌هایی ساخته می‌شود که متن از آن‌ها نوشته شد. پست‌ها با `content_version` نسخه‌بندی می‌شوند.

## ۳) وضعیت هر لایه (راستی‌آزمایی‌شده 2026-11-17)

| لایه | فایل | وضعیت |
|---|---|---|
| ۱ Provider | `providers/football_data_couk.py`, `football_data_org.py`, `api_football.py` | ✅ فعال؛ CSV تا 2026-11-15، فصل 2026-27 با xG |
| ۲ Normalization | `normalization/models.py` (MatchFacts + RecentForm + xg_series) | ✅ کامل |
| ۳ Analytics | `analytics/metrics.py` (+ `dixon_coles_matrix`, `expected_points`) | ✅ کامل و تست‌شده |
| ۴ Editorial | `editorial/prompt.py`, `draft.py`, `validate.py`, `llm_provider.py` | ✅ کار کرده (پست ۱ با موفقیت تولید و validated شد) |
| ۵ DB | `db.py`, `sync.py` | ✅ ۴۹۰ fixture / ۶۹۲۰ stat / ۱ پست |
| ۶ Render | `render/cards.py` (۸۶۴ خط) + `templates/match_preview.html.j2` (۷۶۳ خط) | ✅ ۳ فرمت × ۴ چیدمان؛ ۹۷ تست سبز |
| ۷ Publish | `publishers/telegram_bot.py` (aiogram 3، ۱۰۰ خط) | ⚠️ **نوشته شده، تست نشده، به posts وصل نیست، دستور CLI ندارد** |
| استودیوی طراحی | `tools/matchday_studio.html` (۲۳۴۶ خط) | ✅ مرجع بصری — با Tailwind/html2canvas، آفلاین هم باز می‌شود |
| دارایی‌ها | `brand/` (لوگو SVG/PNG کامل، ۴ فونت ×۲ فرمت، ۲۰ نشان تیم) | ✅ کامل |

### تست‌ها — وضعیت سبز واقعی

```
python -m pytest tests/ -q   →   97 passed
```
(بدون `.[render]` نصب‌شده یک تست رندر skip می‌شود؛ با render extras همهٔ ۹۷ می‌گذارند.)
فایل‌ها: `test_core_rules` (۴) · `test_providers_v8` (۱۱) · `test_sync_facts` (۸) · `test_analytics_dc` (۱۲) · `test_editorial_draft` (۱۶) · `test_validator_injections` (۱۰) · `test_render_cards` (۳۰+).

## ۴) دستورهای خط فرمان (run.py)

| دستور | کار | نیاز |
|---|---|---|
| `init` | ساخت SQLite | — |
| `sync-results [--season YYYY]` | CSV نتایج+xG → DB | شبکه |
| `fixtures --days 7` | بازی‌های پیش‌رو → DB | توکن football-data.org |
| `list-fixtures [--limit N]` | فهرست fixture_idها | — |
| `facts --fixture ID [--out f.json]` | ساخت fact_json از DB (xg/xga/sot/فرم/روند۱۰) | — |
| `draft --fixture ID [--platform telegram] [--post-type preview]` | LLM + ۷ دروازه → posts | کلید LLM در .env |
| `list-posts` / `show-post --post-id N` | بازبینی پست‌ها | — |
| `export-post --post-id N [--out f]` | JSON مستقل → `data/exports/` | — |
| `render-post --post-id N [--format 4:5\|9:16\|16:9] [--layout smart\|v1\|v2\|v3] [--out dir]` | کارت + کپشن → `output/` | `.[render]` + chromium |
| `status` | تازگی داده + آمار DB | — |
| `test-provider --matches 5` | گزارش پوشش → `docs/provider-test.md` | شبکه |

نمونهٔ fixture_id: `fdcouk:2026-11-08:Manchester United:Aston Villa`

## ۵) راه‌اندازی سریع (روی ویندوز کاربر)

```bat
REM 1) Python 3.12+ با تیک Add to PATH — بعد دابل‌کلیک:
setup.bat
REM 2) pip install -e ".[render]" && playwright install chromium   (نصب شده است)
REM 3) توکن‌ها در .env: FOOTBALL_DATA_ORG_TOKEN و LLM_BASE_URL/LLM_API_KEY/LLM_MODEL
REM 4) python check_env.py
```
مخزن git: `https://github.com/Saeidomrani74/XGPedia.git` (شعبهٔ main، ۵ کامیت).

## ۶) نقاط ضعف / بدهی شناخته‌شده (مهم برای چت بعدی)

1. **ربات تلگرام (`publishers/telegram_bot.py`) استخوان‌بندی است**: DRAFTS را در حافظهٔ process نگه می‌دارد (نه جدول posts)، به CLI وصل نیست، هرگز اجرا نشده. لایهٔ ۷ واقعی = کار بعدی.
2. **چیدمان smart کارت روند۱۰بازی و پواسون را نشان نمی‌دهد** (فقط stats/focus/radar/keyduel/watchout/signals وقتی داده دارند). برای دیدن trend10/poisson/wave از `--layout v2` یا `v3` استفاده کن — کد و داده (xg_series) هر دو آماده‌اند. تصمیم تحریریه‌ای: یا smart را گسترش دهی یا پیش‌فرض را عوض کنی.
3. **fact_json پست ۱ در DB قدیمی بود** (قبل از فیلدهای xg_series/recent_form ساخته شده بود). رفع شد با rebuild `facts` + `UPDATE posts`. درس: بعد از هر تغییر schema فکت، پست‌های نمونه را از نو بساز. حالا درست است.
4. **CI (`.github/workflows/jobs.yml`) با کد نمی‌خواند**: `fixtures --date` که وجود ندارد (فلگ واقعی `--days` است) و `API_FOOTBALL_KEY` می‌فرستد در حالی که fixtures از football-data.org و توکن `FOOTBALL_DATA_ORG_TOKEN` استفاده می‌کند. قبل از روشن‌کردن cron درستش کن.
5. **درخت مخزن کمی شلوغ است**: `.idea/`، `__pycache__/`، `.pytest_cache/`، `xgpedia.egg-info/`، `run.cpython-314.pyc` داخل zip/git رفته‌اند. پاک‌سازی + افزودن به `.gitignore` (که خودش هم در git نیست!) لازم است.
6. نسخه در `pyproject.toml` = 0.9.0 ولی README بخش رندر را «v0.10 — طراحی استودیو» صدا می‌زند. هماهنگ کن.
7. **تست پیکسلی فقط 4:5 تلگرام** دارد؛ 9:16/16:9 و JPEG اینستاگرام smoke ندارند (بدهی فنی ثبت‌شده در ROADMAP).

## ۷) خطاها و راه‌حل‌هایی که در راه دیدیم (از چت‌های قبلی)

| علامت | علت | راه‌حل |
|---|---|---|
| `ModuleNotFoundError: jdatetime` | render extras در محیط جدید نصب نیست | `pip install -e ".[render]"` |
| کارت بدون دایره‌های فرم/روند/سیگنال | fact_json پست قبل از فیلدهای جدید ساخته شده | `run.py facts --fixture … --out …` و به‌روزرسانی fact_json پست |
| playwright `Executable doesn't exist` | نسخهٔ کتابخانه با نسخهٔ مرورگر cache ناهماهنگ | `playwright install chromium` در همان محیط؛ در venv جدا حتماً همان نسخه |
| ImportErrorهای عجیب در تست | extract روی پوشهٔ نسخهٔ قبل | پوشهٔ تازه، همیشه |
| فارسی برعکس در ترمینال | کنسول ویندوز | طبیعی؛ ترمینال انگلیسی، فایل‌ها فارسی |
| ۴۲۹ در fixtures | سقف ۱۰ req/min | backoff خودکار هست؛ صبر |

## ۸) نقشهٔ فایل‌ها (فقط مسیرهای مهم)

```
run.py                     درگاه CLI (۱۲ دستور)
src/xgpedia/
  config.py                مسیرها/فصل/نام providerها — همه از اینجا
  db.py sync.py            schema + پرکردن DB + build_match_facts
  providers/ normalization/ analytics/ editorial/ render/ publishers/
brand/                     brand.json (matchday_palette!) · logo/ · crests/ · fonts/
config/                    team_identities.json · team_mapping.json · thresholds.json · glossary_fa.json
tools/matchday_studio.html استودیوی مرجع طراحی کارت
tools/fetch_crests.py      دانلود نشان تیم‌ها (۲۰/۲۰ انجام شده)
docs/                      ROADMAP.md · decisions.md (دفتر تصمیم D1-D18) · corrections.md · calendar.md · brand-check.md
data/                      dev.sqlite · raw/ (CSV/JSON خام با sha256) · exports/ · samples/fact.json
output/                    خروجی‌های رندر
tests/                     ۹۷ تست
.github/workflows/jobs.yml CI (خراب — بند ۶/۴ بالا)
```

## ۹) اولین پیام پیشنهادی برای چت جدید

> «پروژهٔ XGPedia را از پکیج handoff ادامه می‌دهم. فایل `HANDOFF.md` و `NEXT_STEPS.md` را بخوان. از مرحلهٔ ۱ NEXT_STEPS شروع کن.»

بعد از آن، این سه فایل را به چت بده (یا مسیرشان را بگو):
`HANDOFF.md` (این فایل) · `NEXT_STEPS.md` (برنامهٔ مرحله‌به‌مرحله) · `docs/ROADMAP.md` (رودمپ دارایی‌ها — داخل خود پروژه هست).
