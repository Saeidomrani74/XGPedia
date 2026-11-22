# راهنمای گام‌به‌گام راه‌اندازی کلیدهای رایگان هوش مصنوعی در XGPedia (نسخه 0.17.0)

با این تنظیمات، دیگر هیچ‌وقت به‌خاطر خطای `429 Too Many Requests` یا `503 Service Unavailable` یک سرویس متوقف نمی‌شوی؛ چون XGPedia به‌صورت خودکار و فوری از مدل اول به مدل‌ها و ارائه‌دهندگان پشتیبان سوییچ می‌کند.

---

## گام ۱: اصلاح آدرس Gemini در `.env` (خیلی مهم!)
در فایل `.env` خودت حتماً `LLM_BASE_URL` را روی آدرس رسمی OpenAI-compatible گوگل بگذار و کلیدت را در `GEMINI_API_KEY` هم وارد کن:

```env
GEMINI_API_KEY=کلید_AI_Studio_تو
GEMINI_MODEL_CHAIN=gemini-4-hydrogen,gemini-4-neon,gemini-3.8-flash,gemini-3.6-flash,gemini-3.5-flash-lite,gemini-2.5-flash
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
LLM_API_KEY=کلید_AI_Studio_تو
LLM_MODEL=gemini-3.8-flash
```
- **نکته مهم:** مدل‌های `gemini-4-hydrogen` و `gemini-4-neon` در API گوگل روی **Paid Tier** هستند؛ اگر روی پلن رایگان باشی، روتر XGPedia در کسری از ثانیه آن‌ها را رد می‌کند و سراغ `gemini-3.8-flash` و سپس `gemini-3.6-flash` و `gemini-2.5-flash` می‌رود. هر وقت Billing را فعال کردی، خودکار از اولویت ۱ (`gemini-4-hydrogen`) و ۲ (`gemini-4-neon`) استفاده می‌شود.

---

## گام ۲: افزودن ۳ پشتیبان رایگانِ فارسی‌دان عالی (بدون کارت بانکی، زیر ۳ دقیقه)
پیشنهاد می‌کنیم حداقل این ۳ کلید رایگان را بگیری و در `.env` بگذاری تا عملاً هیچ‌وقت به خطای `429` نخوری:

1. **Groq (سرعت فوق‌العاده + مدل `qwen/qwen3.8-27b` با فارسی عالی — ۳۰ درخواست/دقیقه و ۱۰۰۰ درخواست/روز):**
   - برو به `https://console.groq.com/keys` → با ایمیل/گوگل وارد شو → `Create API Key` → در `.env` بگذار:
     `GROQ_API_KEY=...`
2. **OpenRouter (دسترسی به `google/gemma-4-31b-it:free` و `nemotron-3-ultra-550b:free` — ۲۰ درخواست/دقیقه):**
   - برو به `https://openrouter.ai/keys` → ورود با گوگل → `Create Key` → در `.env` بگذار:
     `OPENROUTER_API_KEY=...`
3. **Cohere (مدل‌های `Command A` و `Aya Expanse 32B` مخصوص زبان‌های غیرانگلیسی و فارسی بسیار روان — ۱۰۰۰ درخواست/ماه):**
   - برو به `https://dashboard.cohere.com/api-keys` → ساخت Trial Key رایگان → در `.env` بگذار:
     `COHERE_API_KEY=...`

*(اختیاری برای پشتیبان بیشتر: `MISTRAL_API_KEY` از `console.mistral.ai`، `NVIDIA_API_KEY` از `build.nvidia.com`، `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN` از `dash.cloudflare.com`، `ZAI_API_KEY` از `z.ai`)*

- **پشتیبان اضطراری بدون کلید (خودکار روشن):** حتی اگر هیچ‌کدام از کلیدهای بالا را نگذاری، `OVHcloud` (مدل `Qwen3.5-397B-A17B`)، `Kilo Code` و `LLM7.io` بدون کلید در انتهای زنجیره فعال‌اند (`LLM_ENABLE_ANONYMOUS_FALLBACK=1`).

---

## گام ۳: راه‌اندازی تولید تصویر و ویدیوی باکیفیت رایگان
- **بدون هیچ کلیدی (همین الان آماده):** `Pollinations.ai` با مدل `FLUX` بدون واترمارک و نامحدود فعال است.
- **برای کیفیت و پایداری حرفه‌ای (بدون کارت بانکی):**
  1. **Cloudflare Workers AI** (`10,000 Neurons/day` رایگان برای **FLUX.1 Schnell** + متن): از `https://dash.cloudflare.com` مقدار `CLOUDFLARE_ACCOUNT_ID` و `CLOUDFLARE_API_TOKEN` را در `.env` بگذار.
  2. **Replicate** (`$5` اعتبار رایگان بدون کارت برای **FLUX Schnell** و ویدیوی **Wan 2.1**): از `https://replicate.com/account/api-tokens` کلید `REPLICATE_API_TOKEN` را بگذار.
  3. **Together AI** (`$5` رایگان برای `FLUX.1-schnell-Free`): `TOGETHER_API_KEY` از `https://api.together.ai`.
  4. **Hugging Face** (رایگان برای FLUX و Wan 2.1): `HF_TOKEN` از `https://huggingface.co/settings/tokens`.
  5. **ریلز/استوری متحرک محلی (۱۰۰٪ رایگان و نامحدود):** اگر `ffmpeg` روی ویندوز نصب باشد (`winget install Gyan.FFmpeg`)، XGPedia می‌تواند هر کارت PNG را به ویدیوی متحرک `1080×1920` بدون واترمارک تبدیل کند.

---

## گام ۴: تست زنجیره در ترمینال
```powershell
python run.py llm-status
python run.py gen-image --prompt "Football stadium at night, cinematic floodlights, Premier League matchday atmosphere" --out output/test_bg.png
python run.py gen-video --image output/test_bg.png --out output/test_reel.mp4
```
