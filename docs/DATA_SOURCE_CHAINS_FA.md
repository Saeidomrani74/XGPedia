# زنجیرهٔ اولویت‌بندی منابع داده در XGPedia (v0.59.0)

تمامی **۲۳ کارت** پروژه در فایل مرکزی `config/data_source_chains.json` و موتور پلاگین‌پذیر `src/xgpedia/core/source_chain.py` ثبت شده‌اند. هر منبع داده یک **امتیاز اعتبار (`authority_score`: از ۰ تا ۱۰۰)** دارد و موتور در زمان اجرا منابع را از **معتبرترین به ضعیف‌ترین** اجرا می‌کند (و منابع بدون کلید یا در وضعیت `cooldown` را خودکار رد می‌کند).

## سطح‌بندی اعتبار منابع (Authority Tiers)
* **۹۰–۱۰۰ (`official_opta`)**: دیتای رسمی Opta / Stats Perform، Sportmonks xG، SofaScore Opta، FotMob Opta، FPL Official
* **۷۵–۸۹ (`verified_api`)**: Football-Data.org v4، Understat، API-Football v3، ESPN Soccer Public، The Odds API
* **۶۰–۷۴ (`verified_public`)**: BBC Sport، The Guardian، Sky Sports، Wikipedia/Wikidata، Football-Data.co.uk CSV، کنداکتور صداوسیما
* **۱–۵۹ (`community_fallback`)**: کش‌های محلی و سپر گرافیکی آفلاین

## چگونه منبع جدید اضافه کنیم؟
1. منبع جدید را با `authority_score` مناسب در `config/data_source_chains.json` زیر دامنهٔ مربوطه اضافه کن (مثلاً `sportmonks` با امتیاز `96` در `match_xg_and_shotmap`).
2. اگر تابع دریافت زنده دارد، یک `SourceCandidate` با `register_xg_source(...)` یا `chain.register(...)` ثبت کن.
3. زنجیره به‌صورت خودکار بر اساس `authority_score` مرتب می‌شود و `sync.py` (`_match_metrics`) هم بلافاصله اولویت دیتابیس را از همان رجیستری می‌خواند.

## مشاهدهٔ زندهٔ زنجیرهٔ هر ۲۳ کارت در ترمینال
```powershell
python run.py data-chains
python run.py data-chains --card post_match
```
