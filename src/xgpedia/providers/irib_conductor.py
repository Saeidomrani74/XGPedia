"""پرووایدر رایگان جدول پخش زندهٔ تلویزیون ایران (شبکه سه و شبکه ورزش).

منابع رسمی صداوسیما (بدون کلید API):
  - https://varzeshtv.ir/conductor  (شبکه ورزش)
  - https://tv3.ir/conductor        (شبکه سه)

ویژگی‌ها:
  - پاک‌سازی کاراکترهای پنهان (ZWJ / ZWNJ / کشیده) و یکسان‌سازی ی/ک عربی-فارسی
    (در جدول واقعی صداوسیما گاهی «لیور‍‍پول» با ZWJ درج می‌شود).
  - تفکیک پخش زنده از برنامه‌های تکراری/خاطره‌انگیز/مستند با بررسی کلمات کلیدی
    و تطبیق ساعت شروع مسابقه با جدول پخش (±۹۰ دقیقه).
  - تحمل کامل خطای شبکه: اگر یکی یا هر دو سایت در دسترس نباشد، استثنا کل جریان را نمی‌اندازد.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse
from dataclasses import dataclass
from typing import Any

import httpx

from src.xgpedia.config import team_name_fa

VARZESH_CONDUCTOR_URL = "https://varzeshtv.ir/conductor"
_IRIB_LOG = logging.getLogger(__name__)
_IRIB_INSECURE_HOSTS = ("tv3.ir", "varzeshtv.ir")

TV3_CONDUCTOR_URL = "https://tv3.ir/conductor"

FA_TO_EN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

# نام‌های کوتاه یا جایگزین رایج در جدول پخش صداوسیما
TEAM_ALIASES_FA: dict[str, tuple[str, ...]] = {
    "Arsenal": ("آرسنال", "ارسنال"),
    "Aston Villa": ("استون ویلا", "استونویلا", "ویلا"),
    "Bournemouth": ("بورنموث", "بورنموث"),
    "Brentford": ("برنتفورد",),
    "Brighton": ("برایتون",),
    "Burnley": ("برنلی",),
    "Chelsea": ("چلسی",),
    "Crystal Palace": ("کریستال پالاس", "پالاس"),
    "Everton": ("اورتون",),
    "Fulham": ("فولام", "فولهام"),
    "Hull": ("هال سیتی", "هالسیتی", "هال"),
    "Ipswich": ("ایپسویچ",),
    "Leeds": ("لیدز", "لیدزیونایتد"),
    "Leicester": ("لستر", "لسترسیتی"),
    "Liverpool": ("لیورپول",),
    "Luton": ("لوتون",),
    "Manchester City": ("منچسترسیتی", "منچستر سیتی", "من سیتی"),
    "Manchester United": ("منچستریونایتد", "منچستر یونایتد", "من یونایتد"),
    "Newcastle": ("نیوکاسل",),
    "Nottingham Forest": ("ناتینگهام", "نوتینگهام", "فارست"),
    "Sheffield United": ("شفیلد",),
    "Southampton": ("ساوتهمپتون",),
    "Sunderland": ("ساندرلند",),
    "Tottenham": ("تاتنهام",),
    "West Ham": ("وستهم", "وست هم"),
    "Wolverhampton": ("ولورهمپتون", "ولوز"),
    "Wolves": ("ولورهمپتون", "ولوز"),
}

_REPLAY_KEYWORDS = ("خاطره", "تکرار", "منتخب", "خلاصه", "مستند", "آرشیو", "کلیپ", "بازپخش")


@dataclass
class ConductorProgram:
    channel_key: str     # "tv3" | "varzesh"
    channel_label: str   # "پخش زنده: شبکه سه" | "پخش زنده: شبکه ورزش"
    start_time: str      # "HH:MM"
    title: str
    is_live: bool


def normalize_fa(text: str) -> str:
    """نرمال‌سازی کامل متن فارسی برای تطبیق دقیق نام تیم‌ها در جدول پخش."""
    s = str(text or "").translate(FA_TO_EN_DIGITS)
    s = (
        s.replace("\u200c", "")
        .replace("\u200d", "")
        .replace("\u200e", "")
        .replace("\u200f", "")
        .replace("\ufeff", "")
        .replace("ـ", "")
        .replace("ي", "ی")
        .replace("ك", "ک")
        .replace("ة", "ه")
        .replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
    )
    return re.sub(r"\s+", "", s).lower()


def _time_to_minutes(hhmm: str) -> int | None:
    m = re.search(r"(\d{1,2}):(\d{2})", str(hhmm or "").translate(FA_TO_EN_DIGITS))
    if not m:
        return None
    h, mn = int(m.group(1)), int(m.group(2))
    if 0 <= h <= 23 and 0 <= mn <= 59:
        return h * 60 + mn
    return None


def parse_conductor_html(html_text: str, channel_key: str, channel_label: str) -> list[ConductorProgram]:
    """استخراج ردیف‌های جدول پخش از HTML سایت‌های صداوسیما (tv3.ir و varzeshtv.ir)."""
    programs: list[ConductorProgram] = []
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_text, "html.parser")
        for tr in soup.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            time_val = ""
            title_val = ""
            for c in cells:
                c_en = c.translate(FA_TO_EN_DIGITS)
                m = re.fullmatch(r"\d{1,2}:\d{2}", c_en.strip())
                if m and not time_val:
                    time_val = c_en.strip().zfill(5)
                elif len(c.strip()) > len(title_val) and not re.fullmatch(r"\d{2}:\d{2}:\d{2}", c_en.strip()):
                    title_val = c.strip()
            if time_val and title_val:
                is_live = "زنده" in title_val or any("زنده" in c for c in cells)
                programs.append(
                    ConductorProgram(
                        channel_key=channel_key,
                        channel_label=channel_label,
                        start_time=time_val,
                        title=title_val,
                        is_live=is_live,
                    )
                )
    except Exception:
        pass

    if programs:
        return programs

    # مسیر پشتیبان بدون bs4 یا اگر ساختار div/table متفاوت بود
    clean = re.sub(r"<[^>]+>", "\n", html_text)
    lines = [ln.strip() for ln in clean.splitlines() if ln.strip()]
    for i, ln in enumerate(lines):
        m = re.fullmatch(r"\d{1,2}:\d{2}", ln.translate(FA_TO_EN_DIGITS))
        if m and i + 1 < len(lines):
            title = lines[i + 1]
            if len(title) >= 3:
                programs.append(
                    ConductorProgram(
                        channel_key=channel_key,
                        channel_label=channel_label,
                        start_time=ln.translate(FA_TO_EN_DIGITS).zfill(5),
                        title=title,
                        is_live=("زنده" in title),
                    )
                )
    return programs


def _team_tokens(name_en: str, name_fa: str = "") -> list[str]:
    tokens: list[str] = []
    if name_fa:
        tokens.append(normalize_fa(name_fa))
    fa_auto = team_name_fa(name_en)
    if fa_auto:
        tokens.append(normalize_fa(fa_auto))
    for alias in TEAM_ALIASES_FA.get(name_en, ()):
        tokens.append(normalize_fa(alias))
    # حذف تکراری و توکن‌های خیلی کوتاه
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        if len(t) >= 3 and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def match_fixture_broadcast(
    programs: list[ConductorProgram],
    home_en: str,
    away_en: str,
    *,
    home_fa: str = "",
    away_fa: str = "",
    kickoff_tehran: str = "",
) -> ConductorProgram | None:
    """پیدا کردن برنامهٔ پخش زندهٔ منطبق با یک مسابقه در لیست برنامه‌های شبکه سه و ورزش."""
    h_toks = _team_tokens(home_en, home_fa)
    a_toks = _team_tokens(away_en, away_fa)
    if not h_toks or not a_toks:
        return None

    ko_min = _time_to_minutes(kickoff_tehran)
    candidates: list[tuple[int, ConductorProgram]] = []

    for prog in programs:
        norm_title = normalize_fa(prog.title)
        if not (any(ht in norm_title for ht in h_toks) and any(at in norm_title for at in a_toks)):
            continue
        # رد کردن برنامه‌های آرشیوی/خاطره‌انگیز/خلاصه مگر آنکه صراحتاً «زنده» باشند
        if any(kw in prog.title for kw in _REPLAY_KEYWORDS) and not prog.is_live:
            continue

        score = 0
        if prog.is_live:
            score += 50
        p_min = _time_to_minutes(prog.start_time)
        if ko_min is not None and p_min is not None:
            diff = abs(p_min - ko_min)
            if diff <= 30:
                score += 60
            elif diff <= 90:
                score += 30
            else:
                # اختلاف ساعت زیاد (مثلاً تکرار صبح یا نیمه‌شب)
                if not prog.is_live:
                    continue
                score -= 20
        # اولویت اندک برای نیمه اول یا عنوان اصلی
        if "نیمه اول" in prog.title or "فوتبال" in prog.title:
            score += 5
        candidates.append((score, prog))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


class IRIBConductorProvider:
    """دریافت جدول پخش امروز شبکه ورزش و شبکه سه."""

    def __init__(self, timeout: float = 12.0) -> None:
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
                "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.5",
            },
        )

    def close(self) -> None:
        self._client.close()

    def fetch_all_programs(self) -> tuple[list[ConductorProgram], list[str]]:
        """دریافت برنامه‌های امروز هر دو شبکه؛ خطای یک شبکه مانع شبکهٔ دیگر نمی‌شود."""
        all_progs: list[ConductorProgram] = []
        errors: list[str] = []
        sources = (
            ("tv3", "پخش زنده: شبکه سه", TV3_CONDUCTOR_URL),
            ("varzesh", "پخش زنده: شبکه ورزش", VARZESH_CONDUCTOR_URL),
        )
        for key, label, url in sources:
            try:
                try:
                    r = self._client.get(url)
                except httpx.ConnectError as ssl_err:
                    # برخی سایت‌های صداوسیما (tv3.ir / varzeshtv.ir) روی ویندوز زنجیرهٔ گواهی ناقص دارند
                    host = (urlparse(url).hostname or "").lower()
                    allowed_insecure = any(host == h or host.endswith("." + h) for h in _IRIB_INSECURE_HOSTS)
                    if allowed_insecure and ("CERTIFICATE_VERIFY_FAILED" in str(ssl_err) or "SSL" in str(ssl_err).upper()):
                        _IRIB_LOG.warning("IRIB TLS verify disabled for allowlisted host %s: %s", host, ssl_err)
                        with httpx.Client(
                            timeout=self._client.timeout,
                            follow_redirects=True,
                            verify=False,
                            headers=dict(self._client.headers),
                        ) as insecure_client:
                            r = insecure_client.get(url)
                    else:
                        raise
                r.raise_for_status()
                all_progs.extend(parse_conductor_html(r.text, key, label))
            except Exception as e:
                from src.xgpedia.core.error_metrics import record_error
                record_error(f"irib.{key}", e)
                errors.append(f"{key}: {type(e).__name__}: {str(e)[:80]}")
        return all_progs, errors
