"""لایهٔ خودکارسازی بازی‌های امروز + زمان‌بندی انتشار ۲۴ ساعته + گزارش‌دهی شفاف خطاها.

جریان کامل (قابل استفاده هم از ربات تلگرام ادمین و هم از دستور `python run.py today`):
  ۱) `sync_today_matches`: دریافت آمار فصل + بازی‌های شروع‌نشدهٔ امروز (به وقت تهران) و ثبت در DB
  ۲) `list_today_matches`: نمایش لیست بازی‌های شروع‌نشدهٔ امروز با بررسی قابلیت تولید کارت پیش‌بازی
     و ذکر دقیق دلیل در صورت نبود دادهٔ کافی برای هر بازی
  ۳) `generate_match_post`: انتخاب یک بازی → ساخت فکت‌ها → تولید متن روان LLM + اعتبارسنجی →
     رندر کارت PNG + کپشن در `output/` با گزارش دقیق مرحله و علت در صورت بروز هر خطا
  ۴) `schedule_post_publish` + `run_due_scheduled_publishes`: وارد کردن ساعت ۲۴ ساعته (مثل `09:35`)
     برای انتشار خودکار همان روز در کانال تلگرام و اطلاع‌رسانی نتیجه به ادمین
"""
from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.xgpedia.config import CURRENT_SEASON_START, ROOT, team_name_fa
from src.xgpedia.db import db, init_db
from src.xgpedia.publishers import telegram_publish as tp

TEHRAN_TZ = timezone(timedelta(hours=3, minutes=30))
FA_TO_EN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


@dataclass
class TodayMatchInfo:
    fixture_id: str
    home_en: str
    away_en: str
    home_fa: str
    away_fa: str
    competition: str
    kickoff_utc: str
    kickoff_tehran: str  # HH:MM (24h)
    eligible: bool
    ineligible_reason: str = ""
    existing_post_id: int | None = None
    existing_post_status: str | None = None
    scheduled_time: str | None = None


@dataclass
class SyncTodayReport:
    tehran_date: str
    sync_results_ok: bool = True
    sync_results_detail: str = ""
    sync_fixtures_ok: bool = True
    sync_fixtures_detail: str = ""
    sync_odds_ok: bool = True
    sync_odds_detail: str = ""
    sync_understat_ok: bool = True
    sync_understat_detail: str = ""
    matches: list[TodayMatchInfo] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def eligible_matches(self) -> list[TodayMatchInfo]:
        return [m for m in self.matches if m.eligible]

    @property
    def ineligible_matches(self) -> list[TodayMatchInfo]:
        return [m for m in self.matches if not m.eligible]


@dataclass
class PostGenerationResult:
    ok: bool
    fixture_id: str
    post_id: int | None = None
    content_version: int | None = None
    image_path: Path | None = None
    html_path: Path | None = None
    caption_path: Path | None = None
    caption_text: str = ""
    title: str = ""
    failed_stage: str = ""
    error_title: str = ""
    error_detail: str = ""

    def format_error_fa(self) -> str:
        stage_fa = {
            "facts": "استخراج داده‌ها و فکت‌های مسابقه",
            "editorial": "تولید متن با هوش مصنوعی (LLM) یا اعتبارسنجی",
            "render": "رندر کارت تصویری (HTML/Playwright)",
            "db": "ذخیره‌سازی در پایگاه داده",
        }.get(self.failed_stage, self.failed_stage or "نامشخص")
        return (
            f"❌ خطا در مرحلهٔ «{stage_fa}»\n"
            f"بازی: {self.fixture_id}\n"
            f"عنوان خطا: {self.error_title}\n"
            f"علت دقیق:\n{self.error_detail}"
        )


def _parse_utc(iso_str: str) -> datetime:
    s = str(iso_str).strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _now_utc(now_utc: datetime | None = None) -> datetime:
    if now_utc is None:
        return datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        return now_utc.replace(tzinfo=timezone.utc)
    return now_utc.astimezone(timezone.utc)


def _diagnose_exception(stage: str, exc: Exception) -> tuple[str, str]:
    """ترجمهٔ دقیق خطاهای فنی به گزارش واضح و قابل عیب‌یابی برای کاربر."""
    msg = str(exc).strip() or repr(exc)
    low = msg.lower()
    etype = type(exc).__name__

    if stage == "sync_results":
        if "timeout" in low or "connect" in low:
            return ("خطای شبکه در دریافت CSV آمار فصل", f"{etype}: {msg}\nبررسی کنید اینترنت/VPN متصل باشد.")
        return ("خطا در همگام‌سازی آمار نتایج فصل (football-data.co.uk)", f"{etype}: {msg}")

    if stage == "sync_fixtures":
        if "token" in low or "403" in low or "401" in low:
            return ("خطای احراز هویت API بازی‌ها (football-data.org)", f"{etype}: {msg}\nمقدار FOOTBALL_DATA_ORG_TOKEN را در .env بررسی کنید.")
        if "429" in low:
            return ("محدودیت نرخ درخواست API (HTTP 429)", f"{etype}: {msg}\nیک دقیقه صبر کنید و دوباره امتحان کنید.")
        return ("خطا در دریافت لیست بازی‌های پیش‌رو (football-data.org)", f"{etype}: {msg}")

    if stage == "facts":
        return ("خطا در ساخت فکت‌های مسابقه", f"{etype}: {msg}")

    if stage == "editorial":
        if "RejectedDraft" in etype:
            return ("متن تولیدی مدل از دروازه‌های اعتبارسنجی رد شد", msg)
        if "api_key" in low or "llm_" in low or "401" in low or "403" in low:
            return ("خطای کلید یا دسترسی سرویس LLM", f"{etype}: {msg}\nتنظیمات LLM_BASE_URL و LLM_API_KEY و LLM_MODEL را در .env بررسی کنید.")
        if "503" in low or "timeout" in low or "429" in low:
            return ("قطعی یا شلوغی موقت سرویس LLM", f"{etype}: {msg}\nچند لحظه بعد دوباره دکمهٔ تولید را بزنید.")
        return ("خطا در تولید پیش‌نویس تحریریه", f"{etype}: {msg}")

    if stage == "render":
        if "playwright" in low or "chromium" in low or "executable" in low:
            return ("خطای مرورگر Playwright در رندر تصویر", f"{etype}: {msg}\nدستور `playwright install chromium` را بررسی کنید.")
        if "studio" in low and "not found" in low:
            return ("قالب HTML استودیو در پوشه studio_templates یافت نشد", f"{etype}: {msg}")
        return ("خطا در رندر کارت تصویری", f"{etype}: {msg}")

    return (f"خطای غیرمنتظره ({etype})", msg)


# ─── ۱) بررسی بازی‌های شروع‌نشدهٔ امروز و قابلیت تولید کارت ───

def _check_match_eligibility(fixture_id: str) -> tuple[bool, str]:
    """بررسی واقعی‌بودن و کفایت داده برای تولید کارت پیش‌ازبازی."""
    from src.xgpedia.sync import build_match_facts

    try:
        facts = build_match_facts(fixture_id, post_match=False)
    except Exception as e:
        return False, f"خطا در خواندن فکت‌ها: {type(e).__name__}: {e}"

    home = facts.get("home") or {}
    away = facts.get("away") or {}
    missing: list[str] = []
    if not (home.get("xg_for_avg") and away.get("xg_for_avg")):
        missing.append("میانگین امید گل (xG)")
    if not (home.get("xg_series") and away.get("xg_series")):
        missing.append("روند بازی‌های اخیر")
    if not (home.get("last5") and away.get("last5")):
        missing.append("فرم ۵ بازی اخیر")

    # حداقل یکی از xG یا آمار مقایسه‌ای باید برای هر دو تیم موجود باشد
    has_xg = bool(home.get("xg_for_avg") and away.get("xg_for_avg"))
    has_xga = bool(home.get("xg_against_avg") and away.get("xg_against_avg"))
    has_sot = bool(home.get("sot_avg") and away.get("sot_avg"))
    has_series = bool(home.get("xg_series") and away.get("xg_series"))
    if not (has_xg or has_xga or has_sot or has_series):
        reason = "دادهٔ آماری کافی برای هر دو تیم در دیتابیس نیست"
        if missing:
            reason += f" (فقدان: {'، '.join(missing)})"
        return False, reason
    return True, ""


def list_today_matches(
    now_utc: datetime | None = None,
    post_type: str = "preview",
    platform: str = "telegram",
) -> list[TodayMatchInfo]:
    """بازی‌های شروع‌نشدهٔ امروز (به وقت تهران) موجود در DB همراه با وضعیت قابلیت تولید کارت."""
    init_db()
    now = _now_utc(now_utc)
    today_tehran = now.astimezone(TEHRAN_TZ).date()

    # بازهٔ ۲ روز UTC را می‌خوانیم و دقیقاً روی تاریخ تهران + شروع‌نشده فیلتر می‌کنیم
    utc_from = (today_tehran - timedelta(days=1)).isoformat()
    utc_to = (today_tehran + timedelta(days=2)).isoformat()

    with db() as conn:
        rows = conn.execute(
            """
            SELECT fixture_id, competition, kickoff_utc, home_team, away_team, status
            FROM fixtures
            WHERE substr(kickoff_utc, 1, 10) >= ? AND substr(kickoff_utc, 1, 10) <= ?
              AND status != 'finished'
            ORDER BY kickoff_utc, fixture_id
            """,
            (utc_from, utc_to),
        ).fetchall()

        latest_posts: dict[str, tuple[int, str]] = {}
        for pr in conn.execute(
            """
            SELECT fixture_id, post_id, status
            FROM posts
            WHERE post_type = ? AND target_platform = ?
            ORDER BY content_version ASC, post_id ASC
            """,
            (post_type, platform),
        ).fetchall():
            latest_posts[pr["fixture_id"]] = (pr["post_id"], pr["status"])

        pending_sched: dict[int, str] = {}
        for sr in conn.execute(
            "SELECT post_id, scheduled_time_tehran FROM scheduled_publishes WHERE status = 'pending'"
        ).fetchall():
            pending_sched[sr["post_id"]] = sr["scheduled_time_tehran"]

    result: list[TodayMatchInfo] = []
    for r in rows:
        try:
            ko_utc = _parse_utc(r["kickoff_utc"])
        except ValueError:
            continue
        ko_tehran = ko_utc.astimezone(TEHRAN_TZ)
        if ko_tehran.date() != today_tehran:
            continue
        if ko_utc <= now:
            continue  # بازی قبلاً شروع شده است

        fid = r["fixture_id"]
        eligible, reason = _check_match_eligibility(fid)
        post_info = latest_posts.get(fid)
        post_id = post_info[0] if post_info else None
        post_status = post_info[1] if post_info else None
        sched_time = pending_sched.get(post_id) if post_id is not None else None

        result.append(
            TodayMatchInfo(
                fixture_id=fid,
                home_en=r["home_team"],
                away_en=r["away_team"],
                home_fa=team_name_fa(r["home_team"]),
                away_fa=team_name_fa(r["away_team"]),
                competition=r["competition"],
                kickoff_utc=r["kickoff_utc"],
                kickoff_tehran=ko_tehran.strftime("%H:%M"),
                eligible=eligible,
                ineligible_reason=reason,
                existing_post_id=post_id,
                existing_post_status=post_status,
                scheduled_time=sched_time,
            )
        )
    return result


def sync_today_matches(
    *,
    now_utc: datetime | None = None,
    sync_results_fn: Callable[[], str] | None = None,
    sync_fixtures_fn: Callable[[], str] | None = None,
    sync_odds_fn: Callable[[], str] | None = None,
    sync_understat_fn: Callable[[], str] | None = None,
) -> SyncTodayReport:
    """دریافت آمار نتایج فصل + بازی‌های شروع‌نشدهٔ امروز و ذخیره در DB با گزارش کامل خطاها."""
    init_db()
    now = _now_utc(now_utc)
    tehran_date = now.astimezone(TEHRAN_TZ).date().isoformat()
    report = SyncTodayReport(tehran_date=tehran_date)

    if sync_results_fn is None:
        def _default_sync_results() -> str:
            from src.xgpedia.providers.football_data_couk import FootballDataCoUk
            from src.xgpedia.sync import sync_csv_results

            api = FootballDataCoUk()
            try:
                rows, payload_hash, _ = api.fetch_season_rows(CURRENT_SEASON_START)
            finally:
                api.close()
            if not rows:
                return "0 بازی پایان‌یافته در CSV"
            s = sync_csv_results(rows, payload_hash, season_start=CURRENT_SEASON_START)
            return f"{len(rows)} بازی بررسی شد (جدید: {s['fixtures_new']}، آمار جدید: {s['stats_rows']})"

        sync_results_fn = _default_sync_results

    if sync_fixtures_fn is None:
        def _default_sync_fixtures() -> str:
            from src.xgpedia.providers.football_data_org import FootballDataOrg
            from src.xgpedia.sync import sync_upcoming_fixtures

            api = FootballDataOrg()
            try:
                raw = api.upcoming_fixtures(days=2)
                s = sync_upcoming_fixtures(raw)
                return f"{s['total_in_payload']} بازی پیش‌رو دریافت شد (جدید: {s['upcoming_new']})"
            finally:
                api.close()

        sync_fixtures_fn = _default_sync_fixtures

    try:
        report.sync_results_detail = sync_results_fn()
    except Exception as e:
        report.sync_results_ok = False
        title, detail = _diagnose_exception("sync_results", e)
        report.sync_results_detail = f"{title}: {detail}"
        report.errors.append(f"[آمار فصل] {title} — {detail}")

    try:
        report.sync_fixtures_detail = sync_fixtures_fn()
    except Exception as e:
        report.sync_fixtures_ok = False
        title, detail = _diagnose_exception("sync_fixtures", e)
        report.sync_fixtures_detail = f"{title}: {detail}"
        report.errors.append(f"[بازی‌های امروز] {title} — {detail}")

    if sync_odds_fn is None:
        def _default_sync_odds() -> str:
            from src.xgpedia.providers.football_data_couk import FootballDataCoUk
            from src.xgpedia.sync import sync_upcoming_odds

            api = FootballDataCoUk()
            try:
                rows = api.fetch_upcoming_odds()
            finally:
                api.close()
            s = sync_upcoming_odds(rows)
            return f"{s['odds_saved']} بازی دارای ضریب بازار (+EV)"

        sync_odds_fn = _default_sync_odds

    if sync_understat_fn is None:
        def _default_sync_understat() -> str:
            from src.xgpedia.providers.understat import UnderstatProvider
            from src.xgpedia.sync import sync_understat_league

            api = UnderstatProvider()
            try:
                data = api.fetch_epl_league_data(CURRENT_SEASON_START)
            finally:
                api.close()
            s = sync_understat_league(data, season_start=CURRENT_SEASON_START)
            return f"{s['key_players']} مهرهٔ کلیدی و PPDA از Understat"

        sync_understat_fn = _default_sync_understat

    try:
        report.sync_odds_detail = sync_odds_fn()
    except Exception as e:
        report.sync_odds_ok = False
        report.sync_odds_detail = f"اختیاری — در دسترس نبود ({type(e).__name__}: {str(e)[:120]})"

    try:
        report.sync_understat_detail = sync_understat_fn()
    except Exception as e:
        report.sync_understat_ok = False
        report.sync_understat_detail = f"اختیاری — در دسترس نبود ({type(e).__name__}: {str(e)[:120]})"

    report.matches = list_today_matches(now_utc=now)
    return report


# ─── ۲) تولید پست کامل (فکت + متن LLM + کارت PNG + کپشن) برای بازی انتخاب‌شده ───

def generate_match_post(
    fixture_id: str,
    *,
    post_type: str = "preview",
    fmt: str = "4:5",
    platform: str = "telegram",
    out_dir: Path | None = None,
    llm_provider: Any = None,
    render_fn: Callable[..., tuple[Path, Path, Path]] | None = None,
) -> PostGenerationResult:
    """تولید کامل پست (کارت PNG + کپشن آماده) برای یک بازی با گزارش‌دهی دقیق خطا در هر مرحله."""
    from src.xgpedia.editorial.draft import generate_draft, save_draft
    from src.xgpedia.normalization.models import MatchFacts
    from src.xgpedia.render.cards import render_preview_card
    from src.xgpedia.sync import build_match_facts

    init_db()

    # گام ۱: استخراج فکت‌ها
    try:
        facts = build_match_facts(fixture_id, post_match=(post_type == "post_match"))
    except Exception as e:
        title, detail = _diagnose_exception("facts", e)
        return PostGenerationResult(
            ok=False, fixture_id=fixture_id, failed_stage="facts",
            error_title=title, error_detail=detail,
        )

    # گام ۲: تولید متن LLM + اعتبارسنجی + ذخیره در DB
    try:
        if llm_provider is None:
            from src.xgpedia.editorial.llm_provider import OpenAICompatibleLLM

            llm_provider = OpenAICompatibleLLM()
        draft_obj, _, _ = generate_draft(
            llm_provider, facts, post_type=post_type, target_platform=platform
        )
        post_id = save_draft(
            draft_obj,
            facts=MatchFacts.model_validate(facts),
            post_type=post_type,
            target_platform=platform,
        )
    except Exception as e:
        title, detail = _diagnose_exception("editorial", e)
        return PostGenerationResult(
            ok=False, fixture_id=fixture_id, failed_stage="editorial",
            error_title=title, error_detail=detail,
        )

    # گام ۳: رندر کارت تصویری و فایل کپشن
    try:
        post = tp.load_post(post_id)
        draft_dict = json.loads(post["draft_json"] or "{}")
        fact_dict = json.loads(post["fact_json"] or "{}")
        target_out = out_dir or (ROOT / "output")
        do_render = render_fn or render_preview_card
        html_path, img_path, cap_path = do_render(
            draft_dict,
            fact_dict,
            out_dir=target_out,
            post_id=post_id,
            version=post["content_version"],
            platform=platform,
            post_type=post_type,
            fmt=fmt,
        )
        # آماده‌سازی وضعیت برای انتشار فوری یا زمان‌بندی‌شده
        with db() as conn:
            conn.execute(
                "UPDATE posts SET status = 'awaiting_approval' WHERE post_id = ?",
                (post_id,),
            )
        caption_text = cap_path.read_text(encoding="utf-8") if cap_path.exists() else ""
        return PostGenerationResult(
            ok=True,
            fixture_id=fixture_id,
            post_id=post_id,
            content_version=post["content_version"],
            image_path=img_path,
            html_path=html_path,
            caption_path=cap_path,
            caption_text=caption_text,
            title=draft_obj.title,
        )
    except Exception as e:
        title, detail = _diagnose_exception("render", e)
        return PostGenerationResult(
            ok=False, fixture_id=fixture_id, post_id=post_id, failed_stage="render",
            error_title=title, error_detail=detail,
        )


# ─── ۳) زمان‌بندی انتشار ۲۴ ساعته به وقت تهران (مثلاً 09:35) ───

def parse_today_tehran_time(
    time_str: str, now_utc: datetime | None = None
) -> tuple[str, str]:
    """پارس و اعتبارسنجی ساعت ۲۴ ساعته امروز به وقت تهران (مانند 09:35 یا ۰۹:۳۵).

    خروجی: `(scheduled_at_utc_iso, normalized_hhmm_tehran)`
    """
    cleaned = str(time_str or "").strip().translate(FA_TO_EN_DIGITS)
    m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", cleaned)
    if not m:
        raise ValueError(
            "فرمت ساعت نامعتبر است. لطفاً ساعت را با فرمت ۲۴ ساعته HH:MM وارد کنید (مثلاً 09:35 یا 21:15)."
        )
    hour, minute = int(m.group(1)), int(m.group(2))
    hhmm = f"{hour:02d}:{minute:02d}"

    now = _now_utc(now_utc)
    now_tehran = now.astimezone(TEHRAN_TZ)
    target_tehran = now_tehran.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target_tehran <= now_tehran + timedelta(seconds=10):
        raise ValueError(
            f"ساعت {hhmm} برای امروز گذشته است (ساعت فعلی تهران: {now_tehran.strftime('%H:%M')}). "
            "لطفاً ساعتی بعد از زمان فعلی امروز وارد کنید."
        )
    target_utc = target_tehran.astimezone(timezone.utc)
    return target_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), hhmm


def schedule_post_publish(
    post_id: int,
    time_hhmm: str,
    admin_user_id: int,
    *,
    now_utc: datetime | None = None,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    """ثبت زمان‌بندی انتشار خودکار یک پست برای ساعت مشخص‌شده در امروز (به وقت تهران)."""
    init_db()
    if not tp.is_admin(admin_user_id):
        raise PermissionError(f"کاربر {admin_user_id} در لیست ادمین‌ها نیست.")
    if tp.already_published(post_id):
        raise ValueError(f"پست #{post_id} قبلاً در کانال منتشر شده است.")

    post = tp.load_post(post_id)
    tp.find_card_image(post_id, post["content_version"], out_dir=out_dir)

    scheduled_at_utc, hhmm = parse_today_tehran_time(time_hhmm, now_utc=now_utc)
    now_iso = _now_utc(now_utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with db() as conn:
        # لغو زمان‌بندی قبلی همین پست در صورت وجود
        conn.execute(
            "UPDATE scheduled_publishes SET status = 'cancelled' "
            "WHERE post_id = ? AND status = 'pending'",
            (post_id,),
        )
        cur = conn.execute(
            """
            INSERT INTO scheduled_publishes
              (post_id, scheduled_at_utc, scheduled_time_tehran, scheduled_by_admin, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (post_id, scheduled_at_utc, hhmm, admin_user_id, now_iso),
        )
        sched_id = cur.lastrowid or 0
        conn.execute("UPDATE posts SET status = 'scheduled' WHERE post_id = ?", (post_id,))
        conn.execute(
            "INSERT INTO moderation_logs (post_id, admin_user_id, action, created_at) VALUES (?,?,?,?)",
            (post_id, admin_user_id, f"schedule:{hhmm}", now_iso),
        )

    return {
        "schedule_id": sched_id,
        "post_id": post_id,
        "scheduled_time_tehran": hhmm,
        "scheduled_at_utc": scheduled_at_utc,
    }


def cancel_scheduled_publish(schedule_id: int, admin_user_id: int) -> None:
    """لغو یک انتشار زمان‌بندی‌شدهٔ در انتظار."""
    init_db()
    if not tp.is_admin(admin_user_id):
        raise PermissionError(f"کاربر {admin_user_id} مجاز نیست.")
    with db() as conn:
        row = conn.execute(
            "SELECT post_id, status FROM scheduled_publishes WHERE id = ?", (schedule_id,)
        ).fetchone()
        if not row:
            raise LookupError(f"زمان‌بندی #{schedule_id} پیدا نشد.")
        if row["status"] != "pending":
            raise ValueError(f"زمان‌بندی #{schedule_id} در وضعیت '{row['status']}' است و قابل لغو نیست.")
        conn.execute("UPDATE scheduled_publishes SET status = 'cancelled' WHERE id = ?", (schedule_id,))
        conn.execute("UPDATE posts SET status = 'awaiting_approval' WHERE post_id = ?", (row["post_id"],))


def list_pending_schedules() -> list[dict[str, Any]]:
    """فهرست تمام پست‌های زمان‌بندی‌شدهٔ در انتظار انتشار."""
    init_db()
    with db() as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.post_id, s.scheduled_time_tehran, s.scheduled_at_utc,
                   s.scheduled_by_admin, p.title, p.fixture_id, p.post_type
            FROM scheduled_publishes s
            JOIN posts p ON p.post_id = s.post_id
            WHERE s.status = 'pending'
            ORDER BY s.scheduled_at_utc ASC
            """
        ).fetchall()
    return [dict(r) for r in rows]


async def run_due_scheduled_publishes(
    transport: tp.TelegramTransport,
    *,
    channel_id: str | int = "",
    now_utc: datetime | None = None,
    notify_fn: Callable[[int, str], Awaitable[None]] | None = None,
) -> list[dict[str, Any]]:
    """اجرای تمام زمان‌بندی‌هایی که زمان انتشارشان رسیده است (idempotent)."""
    init_db()
    now = _now_utc(now_utc)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    with db() as conn:
        due_rows = conn.execute(
            """
            SELECT id, post_id, scheduled_time_tehran, scheduled_by_admin
            FROM scheduled_publishes
            WHERE status = 'pending' AND scheduled_at_utc <= ?
            ORDER BY scheduled_at_utc ASC
            """,
            (now_iso,),
        ).fetchall()

    outcomes: list[dict[str, Any]] = []
    for row in due_rows:
        sid = row["id"]
        pid = row["post_id"]
        admin_id = row["scheduled_by_admin"]
        hhmm = row["scheduled_time_tehran"]
        try:
            res = await tp.approve_and_publish(pid, admin_id, transport, channel_id=channel_id)
            with db() as conn:
                conn.execute(
                    "UPDATE scheduled_publishes SET status='published', executed_at=? WHERE id=?",
                    (now_iso, sid),
                )
            outcomes.append({"schedule_id": sid, "post_id": pid, "ok": True, "message_id": res["message_id"]})
            if notify_fn:
                await notify_fn(
                    admin_id,
                    f"✅ انتشار زمان‌بندی‌شده ساعت {hhmm} با موفقیت انجام شد!\n"
                    f"پست #{pid} در کانال منتشر شد (شناسه پیام: {res['message_id']}).",
                )
        except Exception as e:
            err_msg = f"{type(e).__name__}: {e}"
            with db() as conn:
                conn.execute(
                    "UPDATE scheduled_publishes SET status='failed', error_detail=?, executed_at=? WHERE id=?",
                    (err_msg, now_iso, sid),
                )
            outcomes.append({"schedule_id": sid, "post_id": pid, "ok": False, "error": err_msg})
            if notify_fn:
                await notify_fn(
                    admin_id,
                    f"❌ خطا در انتشار زمان‌بندی‌شده ساعت {hhmm} برای پست #{pid}!\n"
                    f"علت دقیق: {err_msg}",
                )
    return outcomes
