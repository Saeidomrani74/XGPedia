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
    sync_broadcasts_ok: bool = True
    sync_broadcasts_detail: str = ""
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


def _cache_fresh_summary(source_key: str, tehran_date: str, ttl_hours: float, now: datetime) -> str | None:
    """اگر همین منبع امروز در بازهٔ TTL قبلاً با موفقیت در DB ذخیره شده باشد، خلاصهٔ کش را برمی‌گرداند."""
    try:
        with db() as conn:
            row = conn.execute(
                "SELECT tehran_date, last_synced_at, summary FROM sync_cache WHERE source_key = ?",
                (source_key,),
            ).fetchone()
            if not row or row["tehran_date"] != tehran_date:
                return None
            last_dt = _parse_utc(row["last_synced_at"])
            age_h = (now - last_dt).total_seconds() / 3600.0
            if age_h > ttl_hours:
                return None
            if source_key == "results":
                cnt = conn.execute("SELECT COUNT(*) AS c FROM fixtures WHERE status='finished'").fetchone()["c"]
                if cnt == 0:
                    return None
            elif source_key == "fixtures":
                cnt = conn.execute("SELECT COUNT(*) AS c FROM fixtures WHERE status!='finished'").fetchone()["c"]
                if cnt == 0:
                    return None
            elif source_key == "understat":
                cnt = conn.execute("SELECT COUNT(*) AS c FROM team_enrichments").fetchone()["c"]
                if cnt == 0:
                    return None
            return f"از کش دیتابیس (بدون مصرف API — {row['summary'] or 'به‌روز'})"
    except Exception:
        return None


def _save_sync_cache(source_key: str, tehran_date: str, now: datetime, summary: str) -> None:
    try:
        with db() as conn:
            conn.execute(
                """
                INSERT INTO sync_cache (source_key, tehran_date, last_synced_at, summary)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source_key) DO UPDATE SET
                  tehran_date=excluded.tehran_date,
                  last_synced_at=excluded.last_synced_at,
                  summary=excluded.summary
                """,
                (source_key, tehran_date, now.strftime("%Y-%m-%dT%H:%M:%SZ"), summary),
            )
    except Exception:
        pass


def sync_today_matches(
    *,
    now_utc: datetime | None = None,
    force: bool = False,
    sync_results_fn: Callable[[], str] | None = None,
    sync_fixtures_fn: Callable[[], str] | None = None,
    sync_odds_fn: Callable[[], str] | None = None,
    sync_understat_fn: Callable[[], str] | None = None,
    sync_broadcasts_fn: Callable[[], str] | None = None,
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
                rows, payload_hash, saved_csv_path = api.fetch_season_rows(CURRENT_SEASON_START)
            finally:
                api.close()
            if not rows:
                return "0 بازی پایان‌یافته در CSV"
            s = sync_csv_results(rows, payload_hash, season_start=CURRENT_SEASON_START)
            wave_cnt = 0
            try:
                from src.xgpedia.providers.football_data_couk import compute_wave_from_csv
                from src.xgpedia.sync import sync_csv_waves

                if saved_csv_path and saved_csv_path.exists():
                    wmap = compute_wave_from_csv(saved_csv_path.read_text(encoding="utf-8", errors="ignore"))
                    ws = sync_csv_waves(wmap, season_start=CURRENT_SEASON_START)
                    wave_cnt = ws.get("waves", 0)
            except Exception:
                pass
            wave_note = f"، موج زمانی: {wave_cnt} تیم" if wave_cnt else ""
            return f"{len(rows)} بازی بررسی شد (جدید: {s['fixtures_new']}، آمار جدید: {s['stats_rows']}{wave_note})"

        sync_results_fn = _default_sync_results

    if sync_fixtures_fn is None:
        def _default_sync_fixtures() -> str:
            from src.xgpedia.providers.football_data_org import FootballDataOrg
            from src.xgpedia.sync import sync_team_metadata, sync_upcoming_fixtures

            api = FootballDataOrg()
            try:
                raw = api.upcoming_fixtures(days=2)
                s = sync_upcoming_fixtures(raw)
                # همگام‌سازی زندهٔ سرمربی و ورزشگاه تیم‌ها (حداکثر روزی ۱ بار با کش ۲۴ ساعته)
                if force or _cache_fresh_summary("teams", tehran_date, 24.0, now) is None:
                    try:
                        t_raw = api.teams(CURRENT_SEASON_START)
                        ts = sync_team_metadata(t_raw, season_start=CURRENT_SEASON_START)
                        try:
                            from src.xgpedia.sync import sync_fdo_scorers
                            sc_raw = api.scorers(limit=100, season_start=CURRENT_SEASON_START)
                            sync_fdo_scorers(sc_raw, season_start=CURRENT_SEASON_START)
                        except Exception:
                            pass
                        _save_sync_cache("teams", tehran_date, now, f"{ts['teams_saved']} تیم")
                    except Exception:
                        pass
                # همگام‌سازی مستقل و ۴ ساعتهٔ سرمربی زنده (جدا از کش ۲۴ ساعتهٔ teams؛ فقط در صورت موفقیت کش می‌شود)
                if force or _cache_fresh_summary("coaches", tehran_date, 4.0, now) is None:
                    try:
                        from src.xgpedia.sync import sync_live_coaches_for_teams

                        upcoming_teams = []
                        for _m in (raw.payload or {}).get("matches") or []:
                            ht = ((_m.get("homeTeam") or {}).get("name") or "").strip()
                            at = ((_m.get("awayTeam") or {}).get("name") or "").strip()
                            if ht:
                                upcoming_teams.append(ht)
                            if at:
                                upcoming_teams.append(at)
                        if upcoming_teams:
                            c_res = sync_live_coaches_for_teams(upcoming_teams, season_start=CURRENT_SEASON_START)
                            if c_res.get("coaches_updated", 0) > 0:
                                _save_sync_cache("coaches", tehran_date, now, f"{c_res['coaches_updated']} مربی")
                    except Exception:
                        pass
                return f"{s['total_in_payload']} بازی پیش‌رو دریافت شد (جدید: {s['upcoming_new']})"
            finally:
                api.close()

        sync_fixtures_fn = _default_sync_fixtures

    cached_res = _cache_fresh_summary("results", tehran_date, 6.0, now) if (not force and getattr(sync_results_fn, "__name__", "") == "_default_sync_results") else None
    if cached_res is not None:
        report.sync_results_detail = cached_res
    else:
        try:
            report.sync_results_detail = sync_results_fn()
            _save_sync_cache("results", tehran_date, now, report.sync_results_detail)
        except Exception as e:
            report.sync_results_ok = False
            title, detail = _diagnose_exception("sync_results", e)
            report.sync_results_detail = f"{title}: {detail}"
            report.errors.append(f"[آمار فصل] {title} — {detail}")

    cached_fix = _cache_fresh_summary("fixtures", tehran_date, 3.0, now) if (not force and getattr(sync_fixtures_fn, "__name__", "") == "_default_sync_fixtures") else None
    if cached_fix is not None:
        report.sync_fixtures_detail = cached_fix
    else:
        try:
            report.sync_fixtures_detail = sync_fixtures_fn()
            _save_sync_cache("fixtures", tehran_date, now, report.sync_fixtures_detail)
        except Exception as e:
            report.sync_fixtures_ok = False
            title, detail = _diagnose_exception("sync_fixtures", e)
            report.sync_fixtures_detail = f"{title}: {detail}"
            report.errors.append(f"[بازی‌های امروز] {title} — {detail}")

    if sync_odds_fn is None:
        def _default_sync_odds() -> str:
            from src.xgpedia.providers.football_data_couk import FootballDataCoUk
            from src.xgpedia.providers.the_odds_api import TheOddsAPIProvider
            from src.xgpedia.sync import sync_upcoming_odds

            total_saved = 0
            sources_used: list[str] = []
            try:
                api = FootballDataCoUk()
                try:
                    rows = api.fetch_upcoming_odds()
                finally:
                    api.close()
                s = sync_upcoming_odds(rows)
                total_saved += s["odds_saved"]
                if s["odds_saved"]:
                    sources_used.append(f"CSV:{s['odds_saved']}")
            except Exception:
                pass
            try:
                oapi = TheOddsAPIProvider()
                try:
                    orows = oapi.fetch_epl_odds()
                finally:
                    oapi.close()
                if orows:
                    s2 = sync_upcoming_odds(orows, provider="the-odds-api")
                    total_saved += s2["odds_saved"]
                    sources_used.append(f"OddsAPI:{s2['odds_saved']}")
            except Exception:
                pass
            src_note = f" ({'، '.join(sources_used)})" if sources_used else ""
            return f"{total_saved} بازی دارای ضریب بازار (+EV){src_note}"

        sync_odds_fn = _default_sync_odds

    if sync_understat_fn is None:
        def _default_sync_understat() -> str:
            parts: list[str] = []
            try:
                from src.xgpedia.providers.football_data_org import FootballDataOrg
                from src.xgpedia.sync import sync_fdo_scorers

                fdo_api = FootballDataOrg()
                try:
                    sc_raw = fdo_api.scorers(limit=100, season_start=CURRENT_SEASON_START)
                    fdo_s = sync_fdo_scorers(sc_raw, season_start=CURRENT_SEASON_START)
                    parts.append(f"FDO-Scorers ({fdo_s['key_players']} ستاره)")
                finally:
                    fdo_api.close()
            except Exception as e_fdo_sc:
                parts.append(f"FDO-Scorers خطا ({type(e_fdo_sc).__name__})")
            try:
                from src.xgpedia.providers.fpl_free import FPLFreeProvider
                from src.xgpedia.sync import sync_fpl_key_players

                fapi = FPLFreeProvider()
                try:
                    kp_map = fapi.fetch_key_players()
                finally:
                    fapi.close()
                fs = sync_fpl_key_players(kp_map, season_start=CURRENT_SEASON_START)
                parts.append(f"FPL ({fs['key_players']} ستاره)")
            except Exception as e_fpl:
                parts.append(f"FPL خطا ({type(e_fpl).__name__})")
            try:
                from src.xgpedia.providers.espn_free import ESPNFreeProvider
                from src.xgpedia.sync import sync_espn_enrichments

                eapi = ESPNFreeProvider()
                try:
                    with db() as _c:
                        _mdates = [r[0] for r in _c.execute(
                            "SELECT DISTINCT substr(kickoff_utc,1,10) FROM fixtures WHERE status='finished' ORDER BY kickoff_utc DESC LIMIT 12"
                        ).fetchall()]
                    edata = eapi.fetch_epl_enrichments(now_utc=now, match_dates=_mdates)
                finally:
                    eapi.close()
                es = sync_espn_enrichments(edata, season_start=CURRENT_SEASON_START)
                parts.append(f"ESPN ({es['waves']} موج، {es['key_players']} ستاره، {es['odds_saved']} ضریب)")
            except Exception as e_espn:
                parts.append(f"ESPN خطا ({type(e_espn).__name__}: {str(e_espn)[:60]})")
            try:
                from src.xgpedia.providers.understat import UnderstatProvider
                from src.xgpedia.sync import sync_understat_league

                api = UnderstatProvider()
                try:
                    data = api.fetch_epl_league_data(CURRENT_SEASON_START)
                finally:
                    api.close()
                s = sync_understat_league(data, season_start=CURRENT_SEASON_START)
                parts.append(f"Understat ({s['key_players']} ستاره)")
            except Exception as e_us:
                parts.append(f"Understat خطا ({type(e_us).__name__}: {str(e_us)[:60]})")
            if not parts:
                raise RuntimeError("هیچ‌یک از منابع تکمیلی (ESPN/Understat) در دسترس نبودند")
            return " + ".join(parts)

        sync_understat_fn = _default_sync_understat

    cached_odds = _cache_fresh_summary("odds", tehran_date, 3.0, now) if (not force and getattr(sync_odds_fn, "__name__", "") == "_default_sync_odds") else None
    if cached_odds is not None:
        report.sync_odds_detail = cached_odds
    else:
        try:
            report.sync_odds_detail = sync_odds_fn()
            _save_sync_cache("odds", tehran_date, now, report.sync_odds_detail)
        except Exception as e:
            report.sync_odds_ok = False
            report.sync_odds_detail = f"اختیاری — در دسترس نبود ({type(e).__name__}: {str(e)[:120]})"

    cached_us = _cache_fresh_summary("understat", tehran_date, 6.0, now) if (not force and getattr(sync_understat_fn, "__name__", "") == "_default_sync_understat") else None
    if cached_us is not None:
        report.sync_understat_detail = cached_us
    else:
        try:
            report.sync_understat_detail = sync_understat_fn()
            _save_sync_cache("understat", tehran_date, now, report.sync_understat_detail)
        except Exception as e:
            report.sync_understat_ok = False
            report.sync_understat_detail = f"اختیاری — در دسترس نبود ({type(e).__name__}: {str(e)[:120]})"

    report.matches = list_today_matches(now_utc=now)

    if sync_broadcasts_fn is None:
        def _default_sync_broadcasts() -> str:
            from src.xgpedia.providers.irib_conductor import IRIBConductorProvider
            from src.xgpedia.sync import sync_irib_broadcasts

            if not report.matches:
                return "بدون بازی شروع‌نشده برای بررسی پخش"
            api = IRIBConductorProvider()
            try:
                progs, errs = api.fetch_all_programs()
            finally:
                api.close()
            fx_list = [
                {
                    "fixture_id": m.fixture_id,
                    "home_en": m.home_en,
                    "away_en": m.away_en,
                    "home_fa": m.home_fa,
                    "away_fa": m.away_fa,
                    "kickoff_tehran": m.kickoff_tehran,
                }
                for m in report.matches
            ]
            s = sync_irib_broadcasts(progs, fx_list, tehran_date=tehran_date)
            err_note = (" (خطا: " + "؛ ".join(errs) + ")") if errs and not progs else ""
            return f"{s['matched']} بازی با پخش زنده (شبکه سه/ورزش){err_note}"

        sync_broadcasts_fn = _default_sync_broadcasts

    cached_bc = _cache_fresh_summary("broadcasts", tehran_date, 2.0, now) if (not force and getattr(sync_broadcasts_fn, "__name__", "") == "_default_sync_broadcasts") else None
    if cached_bc is not None:
        report.sync_broadcasts_detail = cached_bc
    else:
        try:
            report.sync_broadcasts_detail = sync_broadcasts_fn()
            _save_sync_cache("broadcasts", tehran_date, now, report.sync_broadcasts_detail)
        except Exception as e:
            report.sync_broadcasts_ok = False
            report.sync_broadcasts_detail = f"اختیاری — در دسترس نبود ({type(e).__name__}: {str(e)[:120]})"

    return report


# ─── ۲) تولید پست کامل (فکت + متن LLM + کارت PNG + کپشن) برای بازی انتخاب‌شده ───

def get_match_card_options(
    fixture_id: str,
    *,
    post_type: str = "preview",
    fmt: str = "4:5",
) -> dict[str, Any]:
    """استخراج لیست ماژول‌های دارای دیتای کامل برای یک بازی + قابلیت نیم‌عرض بودن هر ماژول."""
    from src.xgpedia.render.card_kit import MODULE_REGISTRY
    from src.xgpedia.render.cards import build_preview_context
    from src.xgpedia.render.post_match_cards import build_post_match_context
    from src.xgpedia.render.studio_engine import POST_MATCH_PRIORITY, PRE_MATCH_PRIORITY
    from src.xgpedia.sync import build_match_facts

    init_db()
    facts = build_match_facts(fixture_id, post_match=(post_type == "post_match"))
    dummy_draft = {"title": "", "bullets": [], "caption": ""}
    if post_type == "post_match":
        ctx = build_post_match_context(dummy_draft, facts, fmt=fmt)
        # اگر ماژول‌های پس‌ازبازی هنوز کامل غنی‌سازی نشده بودند، همان‌لحظه از FPL/Understat تکمیل می‌کنیم
        if sum(1 for k, v in ctx["has"].items() if v and k != "autopsy") <= 2:
            try:
                enrich_post_match_fixture(fixture_id)
                facts = build_match_facts(fixture_id, post_match=True)
                ctx = build_post_match_context(dummy_draft, facts, fmt=fmt)
            except Exception:
                pass
        priority = POST_MATCH_PRIORITY
    else:
        ctx = build_preview_context(dummy_draft, facts, fmt=fmt)
        priority = PRE_MATCH_PRIORITY

    default_ordered = [(m["id"], m.get("span", "full")) for m in ctx["modules"] if m.get("enabled")]
    default_ids = dict(default_ordered)
    ordered_ids = [mid for mid, _ in default_ordered] + [mid for mid in priority if mid not in default_ids]
    available: list[dict[str, Any]] = []
    for mod_id in ordered_ids:
        if not ctx["has"].get(mod_id):
            continue
        spec = MODULE_REGISTRY.get(mod_id)
        if spec is None:
            continue
        available.append({
            "id": mod_id,
            "title_fa": spec.title_fa,
            "can_half": spec.can_half,
            "enabled": mod_id in default_ids,
            "span": default_ids.get(mod_id, "full"),
        })

    missing_mods: list[str] = []
    for mod_id in priority:
        if not ctx["has"].get(mod_id):
            spec = MODULE_REGISTRY.get(mod_id)
            if spec:
                missing_mods.append(spec.title_fa)
    return {
        "fixture_id": fixture_id,
        "home_fa": facts["home"]["name_fa"],
        "away_fa": facts["away"]["name_fa"],
        "round": facts.get("round") or "",
        "stadium": facts.get("stadium") or "",
        "broadcast": facts.get("broadcast") or "پخش آنلاین",
        "available_modules": available,
        "missing_modules": missing_mods,
    }



def _refresh_live_coaches_on_facts(facts: dict[str, Any]) -> None:
    """به‌روزرسانی لحظه‌ای سرمربی دو تیم از ویکی‌پدیا/ویکی‌دیتا پیش از تولید کارت و کپشن.

    تضمین می‌کند سرمربی روی کارت و سرمربی داخل کپشن همیشه یکسان و زنده باشند
    و نام قدیمی football-data.org هرگز روی کارت باقی نماند.
    """
    try:
        from src.xgpedia.config import canonical_team_name
        from src.xgpedia.sync import ensure_live_coaches_fresh

        h_obj = facts.get("home") or {}
        a_obj = facts.get("away") or {}
        h_en = (h_obj.get("name_en") or "").strip()
        a_en = (a_obj.get("name_en") or "").strip()
        teams = [t for t in (h_en, a_en) if t]
        if not teams:
            return
        res = ensure_live_coaches_fresh(teams, season_start=CURRENT_SEASON_START, max_age_hours=4.0, timeout=6.0)
        cmap = res.get("coaches_fa") or {}
        if h_en:
            hc = cmap.get(canonical_team_name(h_en))
            if hc:
                h_obj["sub"] = hc
        if a_en:
            ac = cmap.get(canonical_team_name(a_en))
            if ac:
                a_obj["sub"] = ac
    except Exception:
        pass


def _attach_live_breaking_news(facts: dict[str, Any]) -> None:
    """افزودن خودکار اخبار مهم ۷ روز اخیر دو تیم (تغییر سرمربی، مصدومیت، محرومیت) به فکت‌ها برای کپشن."""
    if facts.get("recent_news"):
        return
    try:
        from src.xgpedia.providers.live_intel_free import fetch_match_breaking_news

        h_en = ((facts.get("home") or {}).get("name_en") or "").strip()
        a_en = ((facts.get("away") or {}).get("name_en") or "").strip()
        if h_en and a_en:
            news = fetch_match_breaking_news(h_en, a_en, max_items=6, timeout=8.0)
            if news:
                facts["recent_news"] = news
    except Exception:
        pass


def generate_match_post(
    fixture_id: str,
    *,
    post_type: str = "preview",
    fmt: str = "4:5",
    platform: str = "telegram",
    header_mode: str = "full",
    custom_modules: list[dict[str, Any]] | None = None,
    broadcast_override: str | None = None,
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
        _refresh_live_coaches_on_facts(facts)
        _attach_live_breaking_news(facts)
    except Exception as e:
        title, detail = _diagnose_exception("facts", e)
        return PostGenerationResult(
            ok=False, fixture_id=fixture_id, failed_stage="facts",
            error_title=title, error_detail=detail,
        )

    # گام ۲: تولید متن LLM + اعتبارسنجی + ذخیره در DB
    try:
        if llm_provider is None:
            from src.xgpedia.editorial.llm_provider import build_default_llm

            llm_provider = build_default_llm()
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
        if render_fn is not None:
            do_render = render_fn
        elif post_type == "post_match":
            from src.xgpedia.render.post_match_cards import render_post_match_card
            do_render = render_post_match_card
        else:
            do_render = render_preview_card
        render_kw: dict[str, Any] = {
            "out_dir": target_out,
            "post_id": post_id,
            "version": post["content_version"],
            "platform": platform,
            "post_type": post_type,
            "fmt": fmt,
        }
        if render_fn is None:
            render_kw["header_mode"] = header_mode
            render_kw["custom_modules"] = custom_modules
            render_kw["broadcast_override"] = broadcast_override
        html_path, img_path, cap_path = do_render(draft_dict, fact_dict, **render_kw)
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


async def generate_match_post_async(
    fixture_id: str,
    *,
    post_type: str = "preview",
    fmt: str = "4:5",
    platform: str = "telegram",
    header_mode: str = "full",
    custom_modules: list[dict[str, Any]] | None = None,
    broadcast_override: str | None = None,
    out_dir: Path | None = None,
    llm_provider: Any = None,
    progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    """نسخهٔ ناهمزمان تولید پست برای ربات تلگرام — رندر Playwright مستقیم روی event loop اصلی (بدون هنگ ویندوز)."""
    import asyncio
    from src.xgpedia.editorial.draft import generate_draft, save_draft
    from src.xgpedia.normalization.models import MatchFacts
    from src.xgpedia.render.cards import FORMATS, render_preview_html
    from src.xgpedia.render.post_match_cards import render_post_match_html
    from src.xgpedia.render.render_png import render as render_png_async
    from src.xgpedia.render.studio_engine import build_card_caption
    from src.xgpedia.sync import build_match_facts

    init_db()

    if progress_cb:
        await progress_cb("⏳ (۱/۳) در حال استخراج داده‌ها و نگارش متن تحریریه (LLM)...")

    import threading

    cancel_ev = threading.Event()

    def _step1_facts_and_draft() -> tuple[int, dict, dict, str]:
        facts = build_match_facts(fixture_id, post_match=(post_type == "post_match"))
        _refresh_live_coaches_on_facts(facts)
        _attach_live_breaking_news(facts)
        prov = llm_provider
        if prov is None:
            from src.xgpedia.editorial.llm_provider import build_default_llm

            prov = build_default_llm()
        if hasattr(prov, "cancel_event"):
            prov.cancel_event = cancel_ev
        draft_obj, _, _ = generate_draft(
            prov, facts, post_type=post_type, target_platform=platform
        )
        pid = save_draft(
            draft_obj,
            facts=MatchFacts.model_validate(facts),
            post_type=post_type,
            target_platform=platform,
        )
        post = tp.load_post(pid)
        return (
            pid,
            json.loads(post["draft_json"] or "{}"),
            json.loads(post["fact_json"] or "{}"),
            draft_obj.title,
        )

    try:
        post_id, draft_dict, fact_dict, title = await asyncio.wait_for(
            asyncio.to_thread(_step1_facts_and_draft), timeout=120.0
        )
    except Exception as e:
        cancel_ev.set()
        title_err, detail = _diagnose_exception("editorial", e)
        return PostGenerationResult(
            ok=False, fixture_id=fixture_id, failed_stage="editorial",
            error_title=title_err, error_detail=detail,
        )
    finally:
        cancel_ev.set()

    if progress_cb:
        await progress_cb(f"⏳ (۲/۳) متن تحریریه آماده شد! در حال رندر کارت {fmt}...")

    try:
        post = tp.load_post(post_id)
        version = post["content_version"]
        target_out = Path(out_dir or (ROOT / "output"))
        target_out.mkdir(parents=True, exist_ok=True)
        w, hgt = FORMATS.get(fmt, FORMATS["4:5"])
        stem = f"post_{post_id}_v{version}_{post_type}"
        html_path = target_out / f"{stem}_{w}x{hgt}.html"
        if post_type == "post_match":
            html_str = render_post_match_html(
                draft_dict, fact_dict, fmt=fmt, header_mode=header_mode,
                custom_modules=custom_modules, broadcast_override=broadcast_override,
            )
        else:
            html_str = render_preview_html(
                draft_dict, fact_dict, post_type=post_type, fmt=fmt,
                header_mode=header_mode, custom_modules=custom_modules,
                broadcast_override=broadcast_override,
            )
        html_path.write_text(html_str, encoding="utf-8")

        img_fmt = "jpeg" if platform == "instagram" else "png"
        img_path = target_out / f"{stem}_{w}x{hgt}.{img_fmt}"
        await asyncio.wait_for(
            render_png_async(str(html_path), str(img_path), w, hgt, img_fmt),
            timeout=45.0,
        )

        cap_path = target_out / f"post_{post_id}_v{version}_caption.txt"
        caption_text = build_card_caption(draft_dict, fact_dict, post_type)
        cap_path.write_text(caption_text, encoding="utf-8")

        with db() as conn:
            conn.execute(
                "UPDATE posts SET status = 'awaiting_approval' WHERE post_id = ?",
                (post_id,),
            )

        return PostGenerationResult(
            ok=True,
            fixture_id=fixture_id,
            post_id=post_id,
            content_version=version,
            image_path=img_path,
            html_path=html_path,
            caption_path=cap_path,
            caption_text=caption_text,
            title=title,
        )
    except Exception as e:
        title_err, detail = _diagnose_exception("render", e)
        return PostGenerationResult(
            ok=False, fixture_id=fixture_id, post_id=post_id, failed_stage="render",
            error_title=title_err, error_detail=detail,
        )


def regenerate_or_edit_post_text(
    post_id: int,
    *,
    instruction: str = "",
    llm_provider: Any = None,
    out_dir: Path | None = None,
) -> PostGenerationResult:
    """تولید مجدد متن یا ویرایش متن فعلی پست با توضیح ادمین (بدون نیاز به رندر مجدد تصویر)."""
    from src.xgpedia.editorial.draft import generate_draft
    from src.xgpedia.render.studio_engine import build_card_caption

    init_db()
    try:
        post = tp.load_post(post_id)
    except Exception as e:
        return PostGenerationResult(
            ok=False, fixture_id="", post_id=post_id, failed_stage="db",
            error_title="پست یافت نشد", error_detail=str(e),
        )

    fixture_id = post["fixture_id"]
    post_type = post["post_type"]
    platform = post["target_platform"]
    version = post["content_version"]
    facts = json.loads(post["fact_json"] or "{}")
    current_draft_json = post["draft_json"] or "{}"

    try:
        prov = llm_provider
        if prov is None:
            from src.xgpedia.editorial.llm_provider import build_default_llm

            prov = build_default_llm()
        draft_obj, _, _ = generate_draft(
            prov,
            facts,
            post_type=post_type,
            target_platform=platform,
            edit_instruction=instruction.strip(),
            current_draft_json=current_draft_json if instruction.strip() else "",
        )
    except Exception as e:
        title_err, detail = _diagnose_exception("editorial", e)
        return PostGenerationResult(
            ok=False, fixture_id=fixture_id, post_id=post_id, failed_stage="editorial",
            error_title=title_err, error_detail=detail,
        )

    payload = {
        "status": draft_obj.status,
        "title": draft_obj.title,
        "bullets": draft_obj.bullets,
        "caption": draft_obj.caption,
        "source_note": draft_obj.source_note,
        "uncertainties": draft_obj.uncertainties,
    }
    with db() as conn:
        conn.execute(
            "UPDATE posts SET title = ?, caption = ?, draft_json = ?, status = 'awaiting_approval' WHERE post_id = ?",
            (draft_obj.title, draft_obj.caption, json.dumps(payload, ensure_ascii=False), post_id),
        )

    target_out = Path(out_dir or (ROOT / "output"))
    cap_path = target_out / f"post_{post_id}_v{version}_caption.txt"
    caption_text = build_card_caption(payload, facts, post_type)
    if target_out.exists():
        cap_path.write_text(caption_text, encoding="utf-8")

    img_path: Path | None = None
    try:
        img_path = tp.find_card_image(post_id, version, out_dir=target_out)
    except Exception:
        img_path = None

    return PostGenerationResult(
        ok=True,
        fixture_id=fixture_id,
        post_id=post_id,
        content_version=version,
        image_path=img_path,
        caption_path=cap_path if cap_path.exists() else None,
        caption_text=caption_text,
        title=draft_obj.title,
    )


@dataclass
class RecentFinishedMatchInfo:
    fixture_id: str
    home_en: str
    away_en: str
    home_fa: str
    away_fa: str
    home_goals: int
    away_goals: int
    kickoff_utc: str
    kickoff_tehran: str
    elapsed_fa: str
    finished_seconds_ago: float
    existing_post_id: int | None = None
    existing_post_status: str | None = None


def _format_elapsed_fa(seconds: float) -> str:
    sec = max(1, int(seconds))
    if sec < 60:
        return "لحظاتی پیش"
    mins = sec // 60
    if mins < 60:
        return f"{mins} دقیقه پیش"
    hrs = mins // 60
    rem_m = mins % 60
    if rem_m >= 15 and hrs < 6:
        return f"{hrs} ساعت و {rem_m} دقیقه پیش"
    return f"{hrs} ساعت پیش"


def sync_recent_finished_matches(
    *, now_utc: datetime | None = None, hours: float = 24.0
) -> dict[str, Any]:
    """دریافت زندهٔ بازی‌های پایان‌یافته از ۱ ثانیه تا ۲۴ ساعت پیش از ESPN (/summary) + football-data.org."""
    from src.xgpedia.providers.espn_free import ESPNFreeProvider
    from src.xgpedia.sync import sync_espn_finished_matches, sync_finished_matches_from_fdo

    init_db()
    now = _now_utc(now_utc)
    fdo_saved = 0
    espn_saved = 0
    espn_stats = 0
    errors: list[str] = []

    # ۱) football-data.org (بازی‌های FINISHED ۲ روز اخیر برای matchday و شناسهٔ استاندارد fdo:)
    try:
        from src.xgpedia.providers.football_data_org import FootballDataOrg

        fdo = FootballDataOrg()
        try:
            raw_fin = fdo.played_fixtures(days_back=2, season_start=CURRENT_SEASON_START)
            fdo_saved = sync_finished_matches_from_fdo(raw_fin, season_start=CURRENT_SEASON_START).get("finished_saved", 0)
        finally:
            fdo.close()
    except Exception as e:
        errors.append(f"FDO: {type(e).__name__}")

    # ۲) ESPN Public /summary (آمار واقعی لحظه‌ای، گلزنان، مومنتوم ۵ دقیقه‌ای و دروازه‌بان بلافاصله پس از سوت پایان)
    try:
        espn = ESPNFreeProvider(timeout=12.0)
        try:
            finished_rows = espn.fetch_recent_finished_matches(now_utc=now, hours=hours)
        finally:
            espn.close()
        if finished_rows:
            s_res = sync_espn_finished_matches(finished_rows, season_start=CURRENT_SEASON_START)
            espn_saved = s_res.get("finished_saved", 0)
            espn_stats = s_res.get("stats_rows", 0)
    except Exception as e:
        errors.append(f"ESPN: {type(e).__name__}")

    # ۳) تکمیل خودکار ماژول‌های پیشرفته (FPL: TopRated/MOTM/GK + Understat: xG Race/ShotMap) برای بازی‌های ۲۴ ساعت اخیر
    enriched_cnt = 0
    try:
        recent = list_recent_finished_fixtures(now_utc=now, hours=hours)
        for item in recent[:8]:
            er = enrich_post_match_fixture(item.fixture_id)
            if er.get("fpl") or er.get("understat"):
                enriched_cnt += 1
    except Exception:
        pass

    return {
        "fdo_saved": fdo_saved,
        "espn_saved": espn_saved,
        "espn_stats": espn_stats,
        "enriched": enriched_cnt,
        "errors": errors,
    }


def list_recent_finished_fixtures(
    *, now_utc: datetime | None = None, hours: float = 24.0
) -> list[RecentFinishedMatchInfo]:
    """فهرست بازی‌های پایان‌یافته دقیقاً در بازهٔ ۱ ثانیه پیش تا `hours` ساعت پیش (جدیدترین اول)."""
    init_db()
    now = _now_utc(now_utc)
    min_ko = (now - timedelta(hours=hours + 3.0)).strftime("%Y-%m-%dT%H:%M:%SZ")

    with db() as conn:
        rows = conn.execute(
            """
            SELECT fixture_id, provider, kickoff_utc, home_team, away_team
            FROM fixtures
            WHERE status = 'finished'
              AND kickoff_utc >= ?
            ORDER BY kickoff_utc DESC
            """,
            (min_ko,),
        ).fetchall()

        out: list[RecentFinishedMatchInfo] = []
        seen_pair_day: set[tuple[str, str, str]] = set()
        for r in rows:
            ko_raw = str(r["kickoff_utc"] or "")
            try:
                ko_dt = datetime.fromisoformat(ko_raw.replace("Z", "+00:00"))
                if ko_dt.tzinfo is None:
                    ko_dt = ko_dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue

            # برآورد لحظهٔ سوت پایان: کیک‌آف + ۱۱۵ دقیقه (اگر بازی تازه تمام شده و هنوز < 115m از کیک‌آف گذشته، حداقل ۱ ثانیه)
            est_end = ko_dt + timedelta(minutes=115)
            if ko_dt > now:
                continue
            elapsed_sec = (now - est_end).total_seconds()
            if elapsed_sec < 1.0:
                # بازی واقعاً status='finished' است و همین لحظه (مثلاً در دقیقه ۹۴) تمام شده
                if (now - ko_dt).total_seconds() >= 90 * 60:
                    elapsed_sec = 1.0
                else:
                    continue
            if elapsed_sec > hours * 3600.0:
                continue

            pair_key = (r["home_team"], r["away_team"], ko_raw[:10])
            if pair_key in seen_pair_day:
                continue
            seen_pair_day.add(pair_key)

            post_row = conn.execute(
                """
                SELECT post_id, status FROM posts
                WHERE fixture_id = ? AND post_type = 'post_match'
                ORDER BY post_id DESC LIMIT 1
                """,
                (r["fixture_id"],),
            ).fetchone()

            hg_row = conn.execute(
                "SELECT value FROM fixture_statistics WHERE fixture_id=? AND team=? AND metric='goals' ORDER BY collected_at DESC LIMIT 1",
                (r["fixture_id"], r["home_team"]),
            ).fetchone()
            ag_row = conn.execute(
                "SELECT value FROM fixture_statistics WHERE fixture_id=? AND team=? AND metric='goals' ORDER BY collected_at DESC LIMIT 1",
                (r["fixture_id"], r["away_team"]),
            ).fetchone()
            if not (hg_row and ag_row and hg_row["value"] is not None and ag_row["value"] is not None):
                continue

            out.append(
                RecentFinishedMatchInfo(
                    fixture_id=r["fixture_id"],
                    home_en=r["home_team"],
                    away_en=r["away_team"],
                    home_fa=team_name_fa(r["home_team"]),
                    away_fa=team_name_fa(r["away_team"]),
                    home_goals=int(round(float(hg_row["value"]))),
                    away_goals=int(round(float(ag_row["value"]))),
                    kickoff_utc=ko_raw,
                    kickoff_tehran=ko_dt.astimezone(TEHRAN_TZ).strftime("%H:%M"),
                    elapsed_fa=_format_elapsed_fa(elapsed_sec),
                    finished_seconds_ago=elapsed_sec,
                    existing_post_id=post_row["post_id"] if post_row else None,
                    existing_post_status=post_row["status"] if post_row else None,
                )
            )

    out.sort(key=lambda x: x.finished_seconds_ago)
    return out


def enrich_post_match_fixture(fixture_id: str) -> dict[str, bool]:
    """تکمیل خودکار دیتای پس‌ازبازی یک مسابقه از منابع رایگان FPL Official (TopRated/MOTM/GK) + Understat (xG Race/ShotMap)."""
    from src.xgpedia.providers.fpl_free import FPLFreeProvider
    from src.xgpedia.providers.understat import fetch_match_shots_understat
    from src.xgpedia.sync import merge_post_match_details

    init_db()
    with db() as conn:
        fx = conn.execute(
            "SELECT home_team, away_team, kickoff_utc FROM fixtures WHERE fixture_id = ?",
            (fixture_id,),
        ).fetchone()
    if not fx:
        return {"fpl": False, "understat": False}

    h_en, a_en = fx["home_team"], fx["away_team"]
    m_date = str(fx["kickoff_utc"] or "")[:10]
    fpl_ok = False
    us_ok = False

    # ۱) FPL Official Live GW -> toprated, motm, gk (PSxG/Saves Opta)
    try:
        fpl = FPLFreeProvider(timeout=12.0)
        try:
            fpl_det = fpl.fetch_match_post_details(h_en, a_en, m_date)
        finally:
            fpl.close()
        if fpl_det:
            fpl_ok = merge_post_match_details(fixture_id, fpl_det, provider="fpl-official")
    except Exception:
        pass

    # ۲) Understat -> shotList + insideBox + real shot-level xG (xgrace + shotmap)
    try:
        us_det = fetch_match_shots_understat(h_en, a_en, m_date, season_start=CURRENT_SEASON_START, timeout=10.0)
        if us_det:
            extra_st = {}
            if us_det.get("home_xg") is not None:
                extra_st[h_en] = {"expected_goals": float(us_det["home_xg"])}
            if us_det.get("away_xg") is not None:
                extra_st[a_en] = {"expected_goals": float(us_det["away_xg"])}
            us_ok = merge_post_match_details(
                fixture_id,
                {
                    "home_shots": us_det["home_shots"],
                    "away_shots": us_det["away_shots"],
                    "home_inside_box": us_det["home_inside_box"],
                    "away_inside_box": us_det["away_inside_box"],
                },
                provider="understat",
                extra_stats=extra_st,
            )
    except Exception:
        pass

    return {"fpl": fpl_ok, "understat": us_ok}


async def generate_on_this_day_post_async(
    event: dict[str, Any],
    *,
    slide: str = "cover",
    theme: str = "core",
    fmt: str = "4:5",
    bg_mode: str | None = None,
    enabled_modules: list[str] | None = None,
    platform: str = "telegram",
    out_dir: Path | None = None,
    progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    """تولید ناهمزمان کارت «در چنین روزی» (Showreel V2) با رندر Playwright و ثبت در جدول posts."""
    import asyncio
    from src.xgpedia.render.card_kit.on_this_day_card import (
        build_on_this_day_caption,
        render_on_this_day_html,
    )
    from src.xgpedia.render.render_png import render as render_png_async
    from src.xgpedia.render.studio_engine import FORMATS

    init_db()
    ev_id = str(event.get("id") or "otd_custom")
    fixture_key = f"otd:{ev_id}:{slide}"

    if progress_cb:
        await progress_cb(f"⏳ (۱/۳) در حال آماده‌سازی کپشن مستند و قالب {slide} ({fmt})...")

    try:
        caption_text = build_on_this_day_caption(event, slide=slide)
        title = f"در چنین روزی | {event.get('title') or ev_id} ({event.get('year') or ''})"
        now_iso = datetime.now(timezone.utc).isoformat()
        with db() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(content_version), 0) AS mv FROM posts "
                "WHERE fixture_id = ? AND post_type = 'on_this_day' AND target_platform = ?",
                (fixture_key, platform),
            ).fetchone()
            ver = int(row["mv"] if row else 0) + 1
            cur = conn.execute(
                """INSERT INTO posts
                   (fixture_id, post_type, target_platform, content_version, status, title, caption, draft_json, fact_json, created_at)
                   VALUES (?, 'on_this_day', ?, ?, 'draft', ?, ?, ?, ?, ?)""",
                (
                    fixture_key,
                    platform,
                    ver,
                    title,
                    caption_text,
                    json.dumps(
                        {
                            "title": title,
                            "slide": slide,
                            "theme": theme,
                            "fmt": fmt,
                            "bg_mode": bg_mode,
                            "enabled_modules": enabled_modules,
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(event, ensure_ascii=False),
                    now_iso,
                ),
            )
            post_id = int(cur.lastrowid)
    except Exception as e:
        title_err, detail = _diagnose_exception("editorial", e)
        return PostGenerationResult(
            ok=False, fixture_id=fixture_key, failed_stage="editorial",
            error_title=title_err, error_detail=detail,
        )

    if progress_cb:
        await progress_cb(f"⏳ (۲/۳) در حال رندر پوستر «در چنین روزی» ({fmt})...")

    try:
        target_out = Path(out_dir or (ROOT / "output"))
        target_out.mkdir(parents=True, exist_ok=True)
        w, hgt = FORMATS.get(fmt, FORMATS["4:5"])
        stem = f"post_{post_id}_v{ver}_on_this_day_{slide}"
        html_path = target_out / f"{stem}_{w}x{hgt}.html"
        html_str = render_on_this_day_html(
            event,
            slide=slide,
            theme=theme,
            fmt=fmt,
            bg_mode=bg_mode,
            enabled_modules=enabled_modules,
        )
        html_path.write_text(html_str, encoding="utf-8")

        img_fmt = "jpeg" if platform == "instagram" else "png"
        img_path = target_out / f"{stem}_{w}x{hgt}.{img_fmt}"
        await asyncio.wait_for(
            render_png_async(str(html_path), str(img_path), w, hgt, img_fmt),
            timeout=45.0,
        )

        cap_path = target_out / f"post_{post_id}_v{ver}_caption.txt"
        cap_path.write_text(caption_text, encoding="utf-8")

        with db() as conn:
            conn.execute(
                "UPDATE posts SET status = 'awaiting_approval' WHERE post_id = ?",
                (post_id,),
            )

        return PostGenerationResult(
            ok=True,
            fixture_id=fixture_key,
            post_id=post_id,
            content_version=ver,
            title=title,
            image_path=img_path,
            html_path=html_path,
            caption_path=cap_path,
        )
    except Exception as e:
        title_err, detail = _diagnose_exception("render", e)
        return PostGenerationResult(
            ok=False, fixture_id=fixture_key, post_id=post_id,
            failed_stage="render", error_title=title_err, error_detail=detail,
        )


async def generate_news_post_async(
    item: dict[str, Any],
    *,
    layout: str = "cinematic",
    mode: str | None = None,
    fmt: str = "4:5",
    mood: str | None = None,
    photo_id: str | None = None,
    tint_mode: str = "light",
    enabled_modules: list[str] | None = None,
    platform: str = "telegram",
    out_dir: Path | None = None,
    progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    """تولید ناهمزمان کارت «خبر فوری و رسمی» (PRO WIRE v2) با رندر Playwright و ثبت در جدول posts."""
    import asyncio
    from src.xgpedia.render.card_kit.news_card import (
        NEWS_FORMATS,
        NEWS_MODES,
        build_news_caption,
        render_news_html,
    )
    from src.xgpedia.render.render_png import render as render_png_async

    init_db()
    item_id = str(item.get("id") or "news_custom")
    eff_mode = mode if mode in NEWS_MODES else str(item.get("mode") or "breaking")
    fixture_key = f"news:{item_id}:{layout}"

    if progress_cb:
        await progress_cb(f"⏳ (۱/۳) در حال ترجمهٔ ژورنالیستی خبر به فارسی و دریافت تصویر واقعی خبر ({fmt})...")

    try:
        from src.xgpedia.providers.breaking_news_free import (
            fetch_image_data_uri,
            translate_news_item_to_persian,
        )

        import threading

        cancel_ev = threading.Event()

        def _prepare_item() -> dict[str, Any]:
            enriched = translate_news_item_to_persian(item, cancel_event=cancel_ev)
            if cancel_ev.is_set():
                raise TimeoutError("زمان آماده‌سازی خبر به پایان رسید.")
            if not enriched.get("photoDataUri") and (enriched.get("photoUrl") or enriched.get("source_url")):
                data_uri = fetch_image_data_uri(enriched.get("photoUrl"), source_url=enriched.get("source_url"))
                if data_uri:
                    enriched["photoDataUri"] = data_uri
            return enriched

        try:
            item = await asyncio.wait_for(asyncio.to_thread(_prepare_item), timeout=110.0)
        finally:
            cancel_ev.set()
        caption_text = build_news_caption(item, mode=eff_mode)
        m_fa = NEWS_MODES.get(eff_mode, NEWS_MODES["breaking"])["fa"]
        clean_hl = str(item.get("headline") or item.get("title") or item_id).replace("*", "")
        title = f"{m_fa} | {clean_hl[:90]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        with db() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(content_version), 0) AS mv FROM posts "
                "WHERE fixture_id = ? AND post_type = 'breaking_news' AND target_platform = ?",
                (fixture_key, platform),
            ).fetchone()
            ver = int(row["mv"] if row else 0) + 1
            cur = conn.execute(
                """INSERT INTO posts
                   (fixture_id, post_type, target_platform, content_version, status, title, caption, draft_json, fact_json, created_at)
                   VALUES (?, 'breaking_news', ?, ?, 'draft', ?, ?, ?, ?, ?)""",
                (
                    fixture_key,
                    platform,
                    ver,
                    title,
                    caption_text,
                    json.dumps(
                        {
                            "title": title,
                            "layout": layout,
                            "mode": eff_mode,
                            "fmt": fmt,
                            "mood": mood,
                            "photo_id": photo_id,
                            "tint_mode": tint_mode,
                            "enabled_modules": enabled_modules,
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(item, ensure_ascii=False),
                    now_iso,
                ),
            )
            post_id = int(cur.lastrowid)
    except Exception as e:
        title_err, detail = _diagnose_exception("editorial", e)
        return PostGenerationResult(
            ok=False, fixture_id=fixture_key, failed_stage="editorial",
            error_title=title_err, error_detail=detail,
        )

    if progress_cb:
        await progress_cb(f"⏳ (۲/۳) در حال رندر پوستر خبری ({fmt})...")

    try:
        target_out = Path(out_dir or (ROOT / "output"))
        target_out.mkdir(parents=True, exist_ok=True)
        w, hgt = NEWS_FORMATS.get(fmt, NEWS_FORMATS["4:5"])
        stem = f"post_{post_id}_v{ver}_news_{layout}"
        html_path = target_out / f"{stem}_{w}x{hgt}.html"
        html_str = render_news_html(
            item,
            layout=layout,
            mode=eff_mode,
            fmt=fmt,
            mood=mood,
            photo_id=photo_id,
            tint_mode=tint_mode,
            enabled_modules=enabled_modules,
        )
        html_path.write_text(html_str, encoding="utf-8")

        img_fmt = "jpeg" if platform == "instagram" else "png"
        img_path = target_out / f"{stem}_{w}x{hgt}.{img_fmt}"
        await asyncio.wait_for(
            render_png_async(str(html_path), str(img_path), w, hgt, img_fmt),
            timeout=45.0,
        )

        cap_path = target_out / f"post_{post_id}_v{ver}_caption.txt"
        cap_path.write_text(caption_text, encoding="utf-8")

        with db() as conn:
            conn.execute(
                "UPDATE posts SET status = 'awaiting_approval' WHERE post_id = ?",
                (post_id,),
            )

        return PostGenerationResult(
            ok=True,
            fixture_id=fixture_key,
            post_id=post_id,
            content_version=ver,
            title=title,
            image_path=img_path,
            html_path=html_path,
            caption_path=cap_path,
        )
    except Exception as e:
        title_err, detail = _diagnose_exception("render", e)
        return PostGenerationResult(
            ok=False, fixture_id=fixture_key, post_id=post_id,
            failed_stage="render", error_title=title_err, error_detail=detail,
        )


async def generate_birthday_post_async(
    item: dict[str, Any],
    *,
    mode: str = "poster",
    fmt: str = "4:5",
    rim_light: bool = True,
    enabled_modules: list[str] | None = None,
    platform: str = "telegram",
    out_dir: Path | None = None,
    progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    """تولید ناهمزمان کارت «تولدت مبارک اسطوره» (Birthday Studio D47) با غنی‌سازی چندمنبعی و رندر Playwright."""
    import asyncio
    import threading
    from src.xgpedia.providers.birthday_free import enrich_birthday_player
    from src.xgpedia.render.card_kit.birthday_card import (
        BIRTHDAY_DEFAULT_MODE,
        BIRTHDAY_FORMATS,
        build_birthday_caption,
        render_birthday_html,
    )
    from src.xgpedia.render.render_png import render as render_png_async

    init_db()
    eff_mode = mode if mode in ("poster", "dossier", "minimal") else BIRTHDAY_DEFAULT_MODE
    item_id = str(item.get("id") or "bday_custom")
    fixture_key = f"birthday:{item_id}:{eff_mode}"

    if progress_cb:
        await progress_cb(f"⏳ (۱/۳) در حال تکمیل آمار واقعی از ویکی‌پدیا/TheSportsDB و نگارش یادداشت تولد ({fmt})...")

    try:
        cancel_ev = threading.Event()

        def _prepare() -> dict[str, Any]:
            return enrich_birthday_player(item, cancel_event=cancel_ev, fetch_network=True)

        try:
            enriched = await asyncio.wait_for(asyncio.to_thread(_prepare), timeout=110.0)
        finally:
            cancel_ev.set()

        caption_text = build_birthday_caption(enriched)
        nm = str(enriched.get("nameFa") or enriched.get("nameEn") or item_id)
        ag = enriched.get("age")
        title = f"تولدت مبارک {nm} ({ag} سالگی)" if ag else f"تولدت مبارک {nm}"
        now_iso = datetime.now(timezone.utc).isoformat()

        with db() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(content_version), 0) AS mv FROM posts "
                "WHERE fixture_id = ? AND post_type = 'birthday' AND target_platform = ?",
                (fixture_key, platform),
            ).fetchone()
            ver = int(row["mv"] if row else 0) + 1
            cur = conn.execute(
                """INSERT INTO posts
                   (fixture_id, post_type, target_platform, content_version, status, title, caption, draft_json, fact_json, created_at)
                   VALUES (?, 'birthday', ?, ?, 'draft', ?, ?, ?, ?, ?)""",
                (
                    fixture_key,
                    platform,
                    ver,
                    title,
                    caption_text,
                    json.dumps(
                        {
                            "title": title,
                            "mode": eff_mode,
                            "fmt": fmt,
                            "rim_light": rim_light,
                            "enabled_modules": enabled_modules,
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(enriched, ensure_ascii=False),
                    now_iso,
                ),
            )
            post_id = int(cur.lastrowid)
    except Exception as e:
        title_err, detail = _diagnose_exception("editorial", e)
        return PostGenerationResult(
            ok=False, fixture_id=fixture_key, failed_stage="editorial",
            error_title=title_err, error_detail=detail,
        )

    if progress_cb:
        await progress_cb(f"⏳ (۲/۳) در حال رندر پوستر تولد ({eff_mode} | {fmt})...")

    try:
        target_out = Path(out_dir or (ROOT / "output"))
        target_out.mkdir(parents=True, exist_ok=True)
        w, hgt = BIRTHDAY_FORMATS.get(fmt, BIRTHDAY_FORMATS["4:5"])
        stem = f"post_{post_id}_v{ver}_birthday_{eff_mode}"
        html_path = target_out / f"{stem}_{w}x{hgt}.html"
        html_str = render_birthday_html(
            enriched,
            mode=eff_mode,
            fmt=fmt,
            rim_light=rim_light,
            enabled_modules=enabled_modules,
        )
        html_path.write_text(html_str, encoding="utf-8")

        img_fmt = "jpeg" if platform == "instagram" else "png"
        img_path = target_out / f"{stem}_{w}x{hgt}.{img_fmt}"
        await asyncio.wait_for(
            render_png_async(str(html_path), str(img_path), w, hgt, img_fmt),
            timeout=45.0,
        )

        cap_path = target_out / f"post_{post_id}_v{ver}_caption.txt"
        cap_path.write_text(caption_text, encoding="utf-8")

        with db() as conn:
            conn.execute(
                "UPDATE posts SET status = 'awaiting_approval' WHERE post_id = ?",
                (post_id,),
            )

        return PostGenerationResult(
            ok=True,
            fixture_id=fixture_key,
            post_id=post_id,
            content_version=ver,
            title=title,
            image_path=img_path,
            html_path=html_path,
            caption_path=cap_path,
        )
    except Exception as e:
        title_err, detail = _diagnose_exception("render", e)
        return PostGenerationResult(
            ok=False, fixture_id=fixture_key, post_id=post_id,
            failed_stage="render", error_title=title_err, error_detail=detail,
        )


async def generate_transfer_post_async(
    item: dict[str, Any],
    *,
    slide: str = "slide1",
    header_mode: str = "full",
    fmt: str = "4:5",
    enabled_modules: list[str] | None = None,
    custom_modules: list[dict[str, Any]] | None = None,
    platform: str = "telegram",
    out_dir: Path | None = None,
    progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    """تولید ناهمزمان کارت ماژولار «رادار نقل‌وانتقالات» (D48) با غنی‌سازی کامل پس از انتخاب شایعه."""
    import asyncio
    import threading
    from src.xgpedia.providers.transfer_radar_free import enrich_transfer_rumor
    from src.xgpedia.render.card_kit.transfer_radar_card import (
        TRANSFER_FORMATS,
        build_transfer_caption,
        render_transfer_radar_html,
    )
    from src.xgpedia.render.render_png import render as render_png_async

    init_db()
    item_id = str(item.get("id") or "tr_custom")
    fixture_key = f"transfer:{item_id}:{slide}"

    if progress_cb:
        await progress_cb(f"⏳ (۱/۳) در حال استخراج جزئیات کامل شایعه، عکس بازیکن و تحلیل فارسی ({fmt})...")

    try:
        cancel_ev = threading.Event()

        def _prepare() -> dict[str, Any]:
            return enrich_transfer_rumor(item, cancel_event=cancel_ev, fetch_network=True)

        try:
            enriched = await asyncio.wait_for(asyncio.to_thread(_prepare), timeout=110.0)
        finally:
            cancel_ev.set()

        caption_text = build_transfer_caption(enriched)
        pl_name = str((enriched.get("player") or {}).get("name") or item_id)
        to_name = str((enriched.get("to") or {}).get("name") or "")
        title = f"رادار نقل‌وانتقالات | {pl_name} ← {to_name}" if to_name else f"رادار نقل‌وانتقالات | {pl_name}"
        now_iso = datetime.now(timezone.utc).isoformat()

        with db() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(content_version), 0) AS mv FROM posts "
                "WHERE fixture_id = ? AND post_type = 'transfer_radar' AND target_platform = ?",
                (fixture_key, platform),
            ).fetchone()
            ver = int(row["mv"] if row else 0) + 1
            cur = conn.execute(
                """INSERT INTO posts
                   (fixture_id, post_type, target_platform, content_version, status, title, caption, draft_json, fact_json, created_at)
                   VALUES (?, 'transfer_radar', ?, ?, 'draft', ?, ?, ?, ?, ?)""",
                (
                    fixture_key,
                    platform,
                    ver,
                    title,
                    caption_text,
                    json.dumps(
                        {
                            "title": title,
                            "slide": slide,
                            "header_mode": header_mode,
                            "fmt": fmt,
                            "enabled_modules": enabled_modules,
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(enriched, ensure_ascii=False),
                    now_iso,
                ),
            )
            post_id = int(cur.lastrowid)
    except Exception as e:
        title_err, detail = _diagnose_exception("editorial", e)
        return PostGenerationResult(
            ok=False, fixture_id=fixture_key, failed_stage="editorial",
            error_title=title_err, error_detail=detail,
        )

    if progress_cb:
        await progress_cb(f"⏳ (۲/۳) در حال رندر کارت ماژولار رادار نقل‌وانتقالات ({slide} | {fmt})...")

    try:
        target_out = Path(out_dir or (ROOT / "output"))
        target_out.mkdir(parents=True, exist_ok=True)
        w, hgt = TRANSFER_FORMATS.get(fmt, TRANSFER_FORMATS["4:5"])
        stem = f"post_{post_id}_v{ver}_transfer_{slide}"
        html_path = target_out / f"{stem}_{w}x{hgt}.html"
        html_str = render_transfer_radar_html(
            enriched,
            slide=slide,
            header_mode=header_mode,
            fmt=fmt,
            enabled_modules=enabled_modules,
            custom_modules=custom_modules,
        )
        html_path.write_text(html_str, encoding="utf-8")

        img_fmt = "jpeg" if platform == "instagram" else "png"
        img_path = target_out / f"{stem}_{w}x{hgt}.{img_fmt}"
        await asyncio.wait_for(
            render_png_async(str(html_path), str(img_path), w, hgt, img_fmt),
            timeout=45.0,
        )

        cap_path = target_out / f"post_{post_id}_v{ver}_caption.txt"
        cap_path.write_text(caption_text, encoding="utf-8")

        with db() as conn:
            conn.execute(
                "UPDATE posts SET status = 'awaiting_approval' WHERE post_id = ?",
                (post_id,),
            )

        return PostGenerationResult(
            ok=True,
            fixture_id=fixture_key,
            post_id=post_id,
            content_version=ver,
            title=title,
            image_path=img_path,
            html_path=html_path,
            caption_path=cap_path,
        )
    except Exception as e:
        title_err, detail = _diagnose_exception("render", e)
        return PostGenerationResult(
            ok=False, fixture_id=fixture_key, post_id=post_id,
            failed_stage="render", error_title=title_err, error_detail=detail,
        )


async def generate_this_or_that_post_async(
    item: dict[str, Any],
    *,
    layout: str = "diagonal",
    fmt: str = "4:5",
    pick: str = "none",
    enabled_modules: list[str] | None = None,
    platform: str = "telegram",
    out_dir: Path | None = None,
    progress_cb: Callable[[str], Awaitable[None]] | None = None,
) -> PostGenerationResult:
    """تولید ناهمزمان کارت اسلایدی «این یا اون؟» (This or That Showreel — D49)."""
    import asyncio
    from src.xgpedia.render.card_kit.this_or_that_card import (
        TOT_FORMATS,
        build_this_or_that_caption,
        render_this_or_that_html,
    )
    from src.xgpedia.render.render_png import render as render_png_async

    init_db()
    item_id = str(item.get("id") or "tot_custom")
    fixture_key = f"this_or_that:{item_id}:{layout}"

    if progress_cb:
        await progress_cb(f"⏳ (۱/۲) در حال آماده‌سازی کپشن جدالی و رندر کارت ({layout} | {fmt})...")

    try:
        caption_text = build_this_or_that_caption(item)
        lbl = str(item.get("label") or item.get("question") or item_id).lstrip("🔥✨ ").strip()
        title = f"این یا اون؟ | {lbl[:85]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        with db() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(content_version), 0) AS mv FROM posts "
                "WHERE fixture_id = ? AND post_type = 'this_or_that' AND target_platform = ?",
                (fixture_key, platform),
            ).fetchone()
            ver = int(row["mv"] if row else 0) + 1
            cur = conn.execute(
                """INSERT INTO posts
                   (fixture_id, post_type, target_platform, content_version, status, title, caption, draft_json, fact_json, created_at)
                   VALUES (?, 'this_or_that', ?, ?, 'draft', ?, ?, ?, ?, ?)""",
                (
                    fixture_key,
                    platform,
                    ver,
                    title,
                    caption_text,
                    json.dumps(
                        {"title": title, "layout": layout, "fmt": fmt, "pick": pick, "enabled_modules": enabled_modules},
                        ensure_ascii=False,
                    ),
                    json.dumps(item, ensure_ascii=False),
                    now_iso,
                ),
            )
            post_id = int(cur.lastrowid)

        target_out = Path(out_dir or (ROOT / "output"))
        target_out.mkdir(parents=True, exist_ok=True)
        w, hgt = TOT_FORMATS.get(fmt, TOT_FORMATS["4:5"])
        stem = f"post_{post_id}_v{ver}_tot_{layout}"
        html_path = target_out / f"{stem}_{w}x{hgt}.html"
        html_str = render_this_or_that_html(
            item,
            layout=layout,
            fmt=fmt,
            pick=pick,
            enabled_modules=enabled_modules,
        )
        html_path.write_text(html_str, encoding="utf-8")

        img_fmt = "jpeg" if platform == "instagram" else "png"
        img_path = target_out / f"{stem}_{w}x{hgt}.{img_fmt}"
        await asyncio.wait_for(
            render_png_async(str(html_path), str(img_path), w, hgt, img_fmt),
            timeout=45.0,
        )

        cap_path = target_out / f"post_{post_id}_v{ver}_caption.txt"
        cap_path.write_text(caption_text, encoding="utf-8")

        with db() as conn:
            conn.execute("UPDATE posts SET status = 'awaiting_approval' WHERE post_id = ?", (post_id,))

        return PostGenerationResult(
            ok=True,
            fixture_id=fixture_key,
            post_id=post_id,
            content_version=ver,
            title=title,
            image_path=img_path,
            html_path=html_path,
            caption_path=cap_path,
        )
    except Exception as e:
        title_err, detail = _diagnose_exception("render", e)
        return PostGenerationResult(
            ok=False, fixture_id=fixture_key, failed_stage="render",
            error_title=title_err, error_detail=detail,
        )
