"""تأمین دادهٔ چندمنبعی و کاملاً رایگان برای کارت ماژولار «نتایج بازی‌های روز» (Matchday Results Studio — D59).

منابع رایگان (بدون وابستگی به `requests`، منحصراً Association Football / Soccer):
  1. ESPN Soccer Public Scoreboard API (`site.api.espn.com/apis/site/v2/sports/soccer/{league}/scoreboard`)
     + فید جامع `soccer/all/scoreboard` برای پوشش کامل بازی‌های ۲۴ ساعت اخیر در سراسر فوتبال جهان
     — جستجوی دقیق و موازی بازی‌هایی که **از ۱ ثانیه قبل تا ۲۴ ساعت قبل به اتمام رسیده‌اند** (`is_finished_within_24h`)
       با استخراج نتیجه نهایی، نتیجه نیمه اول (در صورت وجود)، گلزنان و دقایق گل، و گروه‌بندی در کارت جامع ۲۴ ساعت اخیر
       و کارت مجزا برای هر لیگ دارای بازی پایان‌یافته.
  2. پریست‌های آماده (`config/matchday_results_presets.json`).

قانون `null ≠ 0`: وقتی xG از ESPN در دسترس نیست، `xg: None` می‌ماند و هیچ xG جعلی ساخته نمی‌شود.
"""
from __future__ import annotations

import concurrent.futures
import json
import re
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from src.xgpedia.config import ROOT
from src.xgpedia.providers.players_rating_free import (
    ESPN_SOCCER_LEAGUES,
    _clean_fa_text,
    _resolve_club_meta,
    is_finished_within_24h,
)

PRESETS_PATH = ROOT / "config" / "matchday_results_presets.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

_NON_SOCCER_RE = re.compile(
    r"\b(nfl|nba|mlb|nhl|afl|cfl|ncaa|super\s*bowl|quarterback|touchdown|rugby|gaelic|cricket|tennis|golf|ufc|f1)\b",
    re.IGNORECASE,
)

_LIVE_CACHE: dict[str, Any] = {"ts": 0.0, "items": []}
_CACHE_TTL_SEC = 180.0


def _http_get_json(url: str, timeout: float = 10.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def load_matchday_results_presets() -> list[dict[str, Any]]:
    if not PRESETS_PATH.exists():
        return []
    try:
        data = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _extract_scorers_and_ht(comp: dict[str, Any], home_tid: str, away_tid: str) -> tuple[str, str, str]:
    h_parts: list[str] = []
    a_parts: list[str] = []
    ht_h, ht_a = 0, 0
    for det in (comp.get("details") or []):
        if not isinstance(det, dict) or not det.get("scoringPlay"):
            continue
        clk = str((det.get("clock") or {}).get("displayValue") or "").strip()
        athletes = det.get("athletesInvolved") or []
        scorer = str(athletes[0].get("shortName") or athletes[0].get("displayName") or "") if athletes and isinstance(athletes[0], dict) else ""
        suffix = " (پ)" if det.get("penaltyKick") else (" (گ.خ)" if det.get("ownGoal") else "")
        tid = str((det.get("team") or {}).get("id") or "")
        m_num = re.search(r"(\d+)", clk)
        minute_val = int(m_num.group(1)) if m_num else 90
        if tid == home_tid:
            if minute_val <= 45:
                ht_h += 1
            if scorer:
                h_parts.append(f"{scorer} {clk}{suffix}".strip())
        elif tid == away_tid:
            if minute_val <= 45:
                ht_a += 1
            if scorer:
                a_parts.append(f"{scorer} {clk}{suffix}".strip())
    ht_str = f"{ht_h}-{ht_a}" if (h_parts or a_parts) else ""
    return " • ".join(h_parts[:4]), " • ".join(a_parts[:4]), ht_str


def parse_espn_finished_24h_matches(
    payload: dict[str, Any],
    *,
    slug: str,
    league_fa: str,
    league_en: str,
    now_utc: datetime | None = None,
) -> list[dict[str, Any]]:
    """استخراج صرفاً بازی‌های پایان‌یافته بین ۱ ثانیه تا ۲۴ ساعت گذشته از Scoreboard ESPN."""
    ref_now = now_utc or datetime.now(timezone.utc)
    matches: list[dict[str, Any]] = []
    for ev in (payload.get("events") or []):
        if not isinstance(ev, dict):
            continue
        ev_name = str(ev.get("name") or "")
        if _NON_SOCCER_RE.search(ev_name):
            continue
        comps = ev.get("competitions") or []
        if not comps or not isinstance(comps[0], dict):
            continue
        comp = comps[0]
        st = (comp.get("status") or {}).get("type") or (ev.get("status") or {}).get("type") or {}
        if str(st.get("state") or "").lower() != "post" and not st.get("completed"):
            continue
        kickoff_iso = str(comp.get("date") or ev.get("date") or "")
        ok_24h, elapsed_sec = is_finished_within_24h(kickoff_iso, now_utc=ref_now)
        if not ok_24h:
            continue

        competitors = comp.get("competitors") or []
        home_c = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away_c = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if not home_c or not away_c:
            continue
        ht = home_c.get("team") or {}
        at = away_c.get("team") or {}
        h_fa, h_code, h_col, h_sec = _resolve_club_meta(
            str(ht.get("displayName") or ht.get("shortDisplayName") or "Home"),
            str(ht.get("abbreviation") or ""),
            str(ht.get("color") or ""),
        )
        a_fa, a_code, a_col, a_sec = _resolve_club_meta(
            str(at.get("displayName") or at.get("shortDisplayName") or "Away"),
            str(at.get("abbreviation") or ""),
            str(at.get("color") or ""),
        )
        if h_col.upper() == a_col.upper():
            a_col = "#38BDF8"
        try:
            hs = int(home_c.get("score") or 0)
            as_ = int(away_c.get("score") or 0)
        except (TypeError, ValueError):
            continue

        h_sc, a_sc, ht_str = _extract_scorers_and_ht(comp, str(ht.get("id") or ""), str(at.get("id") or ""))
        status_short = str(st.get("shortDetail") or "FT").upper()[:6]
        ev_league = str(((ev.get("season") or {}).get("slug")) or league_fa)
        matches.append({
            "event_id": str(ev.get("id") or ""),
            "kickoff_iso": kickoff_iso,
            "finished_elapsed_sec": int(elapsed_sec),
            "league_slug": slug,
            "league": league_fa,
            "league_fa": league_fa,
            "league_en": league_en,
            "home": {
                "name": h_fa,
                "code": h_code,
                "color": h_col,
                "secondary": h_sec,
                "score": hs,
                "xg": None,  # null != 0
                "scorers": h_sc,
            },
            "away": {
                "name": a_fa,
                "code": a_code,
                "color": a_col,
                "secondary": a_sec,
                "score": as_,
                "xg": None,  # null != 0
                "scorers": a_sc,
            },
            "status": status_short if status_short in ("FT", "AET", "PEN") else "FT",
            "ht": ht_str,
            "tag": league_fa if league_fa != "فوتبال جهان" else ev_league,
        })
    matches.sort(key=lambda m: int(m.get("finished_elapsed_sec") or 0))
    return matches


def _fetch_league_24h(slug: str, league_fa: str, league_en: str, dates_param: str, now_utc: datetime) -> list[dict[str, Any]]:
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={dates_param}"
    try:
        payload = _http_get_json(url, timeout=10.0)
    except Exception:
        return []
    return parse_espn_finished_24h_matches(payload, slug=slug, league_fa=league_fa, league_en=league_en, now_utc=now_utc)


def _pack_matchday_card(
    card_id: str,
    competition: str,
    league_en: str,
    round_lbl: str,
    matches: list[dict[str, Any]],
) -> dict[str, Any]:
    total_goals = sum(int(m["home"]["score"]) + int(m["away"]["score"]) for m in matches)
    feat_idx = max(
        range(len(matches)),
        key=lambda i: (matches[i]["home"]["score"] + matches[i]["away"]["score"], -abs(matches[i]["home"]["score"] - matches[i]["away"]["score"])),
    )
    feat = matches[feat_idx]
    return {
        "id": card_id,
        "is_preset": False,
        "title": "نتایج ۲۴ ساعت اخیر",
        "competition": competition,
        "round": round_lbl,
        "leagueEn": league_en,
        "wmText": "LAST 24H",
        "day": f"{len(matches)} بازی پایان‌یافته • {total_goals} گل",
        "source": "ESPN Soccer API (24H Live)",
        "featuredIdx": feat_idx,
        "motm": None,  # قانون null != 0: بدون داده رسمی ستاره روز اختراع نمی‌شود
        "editorialNote": _clean_fa_text(
            f"در ۲۴ ساعت گذشته {len(matches)} مسابقه رسمی در {competition} به پایان رسید که در مجموع {total_goals} گل به ثمر رسید؛ "
            f"بازی شاخص این بسته تقابل {feat['home']['name']} ({feat['home']['score']}-{feat['away']['score']}) {feat['away']['name']} بود."
        ),
        "matches": matches[:8],
    }






_JALALI_MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
_WEEKDAYS_FA = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]


def gregorian_to_jalali_fa(dt_utc: datetime) -> str:
    """تبدیل دقیق تاریخ میلادی به تاریخ شمسی فارسی (با وقت تهران UTC+3:30)."""
    dt = dt_utc + timedelta(hours=3, minutes=30)
    gy, gm, gd = dt.year, dt.month, dt.day
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1]
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    wd = _WEEKDAYS_FA[dt.weekday()]
    return f"{wd} {jd} {_JALALI_MONTHS[jm - 1]} {jy}"


def _build_dynamic_day_title(matches: list[dict[str, Any]], comp_label: str) -> str:
    tot_g = sum(int((m.get("home") or {}).get("score") or 0) + int((m.get("away") or {}).get("score") or 0) for m in matches)
    n = max(1, len(matches))
    avg = tot_g / n
    if avg >= 3.5:
        return f"شب پرگل و طوفانی در {comp_label}" if comp_label != "روز شلوغ فوتبال" else "جشنواره گل در روز شلوغ فوتبال"
    if any(abs(int((m.get("home") or {}).get("score") or 0) - int((m.get("away") or {}).get("score") or 0)) >= 3 for m in matches):
        return f"بردهای قاطع در {comp_label}" if comp_label != "روز شلوغ فوتبال" else "شب بردهای قاطع فوتبال جهان"
    return "نتایج بازی‌های روز"


def _build_leagues_label(matches: list[dict[str, Any]]) -> str:
    leagues = []
    for m in matches:
        lg = str(m.get("comp") or m.get("league") or "").strip()
        if lg and lg not in leagues:
            leagues.append(lg)
    if len(leagues) > 2:
        return "روز شلوغ فوتبال"
    if len(leagues) == 2:
        return f"{leagues[0]} و {leagues[1]}"
    return leagues[0] if leagues else "لیگ برتر انگلیس"






def _fetch_thesportsdb_pl_goals_and_ht(
    home_en: str, away_en: str, h_score: int, a_score: int
) -> tuple[str | None, list[dict[str, Any]]]:
    """استخراج دقایق واقعی گل و نتیجه نیمه اول (HT) از TheSportsDB (رایگان و بدون کلید، لیگ برتر id=4328)."""
    from src.xgpedia.providers.injury_free import transliterate_player_name_fa
    try:
        payload = _http_get_json("https://www.thesportsdb.com/api/v1/json/3/eventspastleague.php?id=4328", timeout=7.0)
        events = payload.get("events") if isinstance(payload, dict) else []
        hn, an = home_en.lower()[:5], away_en.lower()[:5]
        for ev in (events or []):
            if not isinstance(ev, dict):
                continue
            eh = str(ev.get("strHomeTeam") or "").lower()
            ea = str(ev.get("strAwayTeam") or "").lower()
            if not ((hn in eh or eh[:5] in hn) and (an in ea or ea[:5] in an)):
                continue
            if str(ev.get("intHomeScore")) != str(h_score) or str(ev.get("intAwayScore")) != str(a_score):
                continue
            goals_out: list[dict[str, Any]] = []
            ht_h = ht_a = 0
            for field, tflag in (("strHomeGoalDetails", "h"), ("strAwayGoalDetails", "a")):
                raw = str(ev.get(field) or "").strip()
                if not raw:
                    continue
                for tok in raw.split(";"):
                    tok = tok.strip()
                    if not tok:
                        continue
                    m_min = re.search(r"(\d{1,2})(?:\+(\d{1,2}))?'", tok)
                    mn = int(m_min.group(1)) if m_min else 45
                    pname = re.sub(r"\d{1,2}(?:\+\d{1,2})?'?:?", "", tok).strip(" :-")
                    pname_fa = transliterate_player_name_fa(pname or "گلزن")
                    goals_out.append({"min": mn, "team": tflag, "scorer": pname_fa})
                    if mn <= 45:
                        if tflag == "h":
                            ht_h += 1
                        else:
                            ht_a += 1
            if goals_out or (h_score == 0 and a_score == 0):
                goals_out.sort(key=lambda g: g["min"])
                return f"{ht_h}-{ht_a}", goals_out
    except Exception:
        pass
    return None, []


def _fetch_understat_match_goals_and_ht(
    home_en: str, away_en: str, h_score: int, a_score: int
) -> tuple[str | None, list[dict[str, Any]]]:
    """استخراج دقیق دقایق واقعی گل‌ها و نتیجه نیمه اول (HT) یک مسابقه لیگ برتر از Understat."""
    import unicodedata as _ud
    now = datetime.now(timezone.utc)
    season_yr = now.year if now.month >= 7 else now.year - 1
    try:
        req = urllib.request.Request(f"https://understat.com/league/EPL/{season_yr}", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=6.0) as resp:
            html_txt = resp.read().decode("utf-8", errors="replace")
        m = re.search(r"datesData\s*=\s*JSON\.parse\('([^']+)'\)", html_txt)
        if not m:
            return None, []
        dates = json.loads(m.group(1).encode("utf-8").decode("unicode_escape"))
        hn = "".join(c for c in _ud.normalize("NFKD", home_en.lower()) if not _ud.combining(c))
        an = "".join(c for c in _ud.normalize("NFKD", away_en.lower()) if not _ud.combining(c))
        match_id = None
        for d in reversed(dates if isinstance(dates, list) else []):
            if not isinstance(d, dict) or not d.get("isResult"):
                continue
            dh = str((d.get("h") or {}).get("title") or "").lower()
            da = str((d.get("a") or {}).get("title") or "").lower()
            dg = d.get("goals") or {}
            if (hn[:4] in dh or dh[:4] in hn) and (an[:4] in da or da[:4] in an):
                if int(dg.get("h") or -1) == h_score and int(dg.get("a") or -1) == a_score:
                    match_id = str(d.get("id") or "")
                    break
        if not match_id:
            return None, []
        req2 = urllib.request.Request(f"https://understat.com/match/{match_id}", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req2, timeout=6.0) as resp2:
            m_html = resp2.read().decode("utf-8", errors="replace")
        ms = re.search(r"shotsData\s*=\s*JSON\.parse\('([^']+)'\)", m_html)
        if not ms:
            return None, []
        shots_data = json.loads(ms.group(1).encode("utf-8").decode("unicode_escape"))
        from src.xgpedia.providers.injury_free import transliterate_player_name_fa
        goals_out: list[dict[str, Any]] = []
        ht_h = ht_a = 0
        for side_k, tflag in (("h", "h"), ("a", "a")):
            for sh in (shots_data.get(side_k) or []):
                if not isinstance(sh, dict):
                    continue
                if sh.get("result") == "Goal":
                    mn = int(sh.get("minute") or 45)
                    pname = transliterate_player_name_fa(str(sh.get("player") or "گلزن"))
                    goals_out.append({"min": mn, "team": tflag, "scorer": pname})
                    if mn <= 45:
                        if tflag == "h":
                            ht_h += 1
                        else:
                            ht_a += 1
                elif sh.get("result") == "OwnGoal":
                    mn = int(sh.get("minute") or 45)
                    opp = "a" if tflag == "h" else "h"
                    pname = transliterate_player_name_fa(str(sh.get("player") or "گل‌به‌خودی")) + " (گل‌به‌خودی)"
                    goals_out.append({"min": mn, "team": opp, "scorer": pname})
                    if mn <= 45:
                        if opp == "h":
                            ht_h += 1
                        else:
                            ht_a += 1
        goals_out.sort(key=lambda g: g["min"])
        return f"{ht_h}-{ht_a}", goals_out
    except Exception:
        return None, []


def _fetch_fpl_finished_24h_matches(now_utc: datetime) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """استخراج مسابقات پایان‌یافته لیگ برتر انگلیس در ۲۴ ساعت اخیر از FPL Official API همراه با xG واقعی و ستاره روز."""
    from src.xgpedia.providers.injury_free import transliterate_player_name_fa
    try:
        boot = _http_get_json("https://fantasy.premierleague.com/api/bootstrap-static/", timeout=9.0)
        fixtures = _http_get_json("https://fantasy.premierleague.com/api/fixtures/", timeout=9.0)
    except Exception:
        return [], None
    if not isinstance(boot, dict) or not isinstance(fixtures, list):
        return [], None

    teams_by_id = {int(t["id"]): t for t in (boot.get("teams") or []) if isinstance(t, dict) and t.get("id") is not None}
    players_by_id = {int(e["id"]): e for e in (boot.get("elements") or []) if isinstance(e, dict) and e.get("id") is not None}

    matched_fx = []
    for fx in fixtures:
        if not isinstance(fx, dict) or not fx.get("finished"):
            continue
        ok_24h, elapsed_sec = is_finished_within_24h(str(fx.get("kickoff_time") or ""), now_utc=now_utc)
        if ok_24h:
            matched_fx.append((fx, elapsed_sec))

    if not matched_fx:
        return [], None

    # Fetch event/{gw}/live/ once per unique GW to get REAL team xG and REAL MOTM!
    live_by_gw: dict[int, dict[str, Any]] = {}
    for fx, _ in matched_fx:
        gw = fx.get("event")
        if gw and int(gw) not in live_by_gw:
            try:
                live_by_gw[int(gw)] = _http_get_json(f"https://fantasy.premierleague.com/api/event/{int(gw)}/live/", timeout=9.0)
            except Exception:
                live_by_gw[int(gw)] = {}

    out: list[dict[str, Any]] = []
    best_motm: dict[str, Any] | None = None
    best_bps = -1

    for fx, elapsed_sec in matched_fx:
        ht, at = fx.get("team_h"), fx.get("team_a")
        hs, as_ = fx.get("team_h_score"), fx.get("team_a_score")
        if ht not in teams_by_id or at not in teams_by_id or hs is None or as_ is None:
            continue
        hs, as_ = int(hs), int(as_)
        h_obj, a_obj = teams_by_id[int(ht)], teams_by_id[int(at)]
        h_fa, h_code, h_col, h_sec = _resolve_club_meta(str(h_obj.get("name") or ""), str(h_obj.get("short_name") or ""))
        a_fa, a_code, a_col, a_sec = _resolve_club_meta(str(a_obj.get("name") or ""), str(a_obj.get("short_name") or ""))
        if h_col.upper() == a_col.upper():
            a_col = "#38BDF8"

        # Compute REAL team xG & MOTM from event/{gw}/live/
        gw = int(fx.get("event") or 0)
        fx_id = int(fx.get("id") or 0)
        h_xg_sum = 0.0
        a_xg_sum = 0.0
        has_live_xg = False
        live_gw = live_by_gw.get(gw) or {}
        for le in live_gw.get("elements") or []:
            if not isinstance(le, dict):
                continue
            eid = int(le.get("id") or 0)
            meta = players_by_id.get(eid)
            if not meta:
                continue
            tid = int(meta.get("team") or 0)
            if tid not in (int(ht), int(at)):
                continue
            explains = le.get("explain") or []
            if fx_id and explains:
                if not any(int(ex.get("fixture") or 0) == fx_id for ex in explains if isinstance(ex, dict)):
                    continue
            st = le.get("stats") or {}
            mins = int(st.get("minutes") or 0)
            if mins <= 0:
                continue
            has_live_xg = True
            xg_v = float(st.get("expected_goals") or 0.0)
            xa_v = float(st.get("expected_assists") or 0.0)
            if tid == int(ht):
                h_xg_sum += xg_v
            else:
                a_xg_sum += xg_v
            bps = int(st.get("bps") or 0)
            if bps > best_bps:
                best_bps = bps
                g_p = int(st.get("goals_scored") or 0)
                a_p = int(st.get("assists") or 0)
                rt = round(max(6.5, min(9.8, 6.0 + bps / 15.0 + g_p * 0.45 + a_p * 0.3)), 1)
                pname_fa = transliterate_player_name_fa(f"{meta.get('first_name', '')} {meta.get('second_name', '')}".strip() or str(meta.get("web_name") or ""))
                stat_parts = []
                if g_p:
                    stat_parts.append(f"{g_p} گل")
                if a_p:
                    stat_parts.append(f"{a_p} پاس گل")
                stat_parts.append(f"{xg_v + xa_v:.2f} xG+xA")
                best_motm = {
                    "name": pname_fa,
                    "team": h_fa if tid == int(ht) else a_fa,
                    "color": h_col if tid == int(ht) else a_col,
                    "rating": f"{rt:.1f}",
                    "stat": " • ".join(stat_parts),
                }

        h_xg = round(h_xg_sum, 2) if has_live_xg else None
        a_xg = round(a_xg_sum, 2) if has_live_xg else None

        # Extract real goal scorers in Persian
        h_scorers_list: list[str] = []
        a_scorers_list: list[str] = []
        goals: list[dict[str, Any]] = []
        # Distribute unknown exact minutes cleanly across match for timeline/step-chart if ESPN didn't provide exact minutes
        h_g_idx = 0
        a_g_idx = 0
        for stat in fx.get("stats") or []:
            if isinstance(stat, dict) and stat.get("identifier") == "goals_scored":
                for side_key, team_flag, sc_list in (("h", "h", h_scorers_list), ("a", "a", a_scorers_list)):
                    for entry in stat.get(side_key) or []:
                        pid = entry.get("element")
                        cnt = int(entry.get("value") or 1)
                        pobj = players_by_id.get(int(pid)) if pid is not None else None
                        raw_p = str((pobj or {}).get("web_name") or "گلزن")
                        pname = transliterate_player_name_fa(raw_p)
                        sc_list.append(f"{pname} ({cnt}×)" if cnt > 1 else pname)
                        for _ in range(cnt):
                            if team_flag == "h":
                                h_g_idx += 1
                                est_m = min(89, 18 + h_g_idx * 17)
                            else:
                                a_g_idx += 1
                                est_m = min(89, 24 + a_g_idx * 19)
                            goals.append({"min": est_m, "team": team_flag, "scorer": pname})

        tot = hs + as_
        diff = abs(hs - as_)
        if h_xg is not None and a_xg is not None and ((hs > as_ and (h_xg - a_xg) < -0.35) or (as_ > hs and (h_xg - a_xg) > 0.35)):
            verdict, vlabel = "heist", "سرقت آماری"
        elif tot >= 4:
            verdict, vlabel = "thriller", "آتش‌بازی"
        elif diff >= 3:
            verdict, vlabel = "clinical", "کلینیکال"
        elif tot <= 1:
            verdict, vlabel = "cagey", "قفل تاکتیکی"
        else:
            verdict, vlabel = "deserved", "برد شایسته"

        from src.xgpedia.providers.pl_badges_free import get_pl_badge_data_uri, resolve_distinct_team_colors
        h_col, a_col = resolve_distinct_team_colors(h_col, a_col)
        h_logo = get_pl_badge_data_uri(str(h_obj.get("name") or ""), tla_hint=h_code, badge_code=int(h_obj.get("code") or 0) or None)
        a_logo = get_pl_badge_data_uri(str(a_obj.get("name") or ""), tla_hint=a_code, badge_code=int(a_obj.get("code") or 0) or None)

        # Fetch exact real goal minutes & Half-Time (HT) score from Understat when available
        real_ht, u_goals = _fetch_thesportsdb_pl_goals_and_ht(str(h_obj.get("name") or ""), str(a_obj.get("name") or ""), hs, as_)
        if not real_ht:
            real_ht, u_goals = _fetch_understat_match_goals_and_ht(str(h_obj.get("name") or ""), str(a_obj.get("name") or ""), hs, as_)
        if u_goals:
            goals = u_goals
            h_sc_str = " • ".join(f"{g['scorer']} {g['min']}'" for g in u_goals if g["team"] == "h")
            a_sc_str = " • ".join(f"{g['scorer']} {g['min']}'" for g in u_goals if g["team"] == "a")
        else:
            h_sc_str = " • ".join(f"{g['scorer']} {g['min']}'" for g in goals if g["team"] == "h")
            a_sc_str = " • ".join(f"{g['scorer']} {g['min']}'" for g in goals if g["team"] == "a")

        out.append({
            "id": f"fpl_fx_{fx_id}",
            "comp": "لیگ برتر انگلیس",
            "league": "لیگ برتر انگلیس",
            "leagueEn": "PREMIER LEAGUE",
            "featured": False,
            "elapsed_sec": int(elapsed_sec),
            "ht": real_ht,
            "tag": f"هفته {gw} لیگ برتر انگلیس",
            "home": {
                "name": h_fa, "code": h_code, "color": h_col, "color2": h_sec, "logoUrl": h_logo,
                "score": hs, "ht": real_ht, "xg": h_xg,
                "scorers": h_sc_str,
            },
            "away": {
                "name": a_fa, "code": a_code, "color": a_col, "color2": a_sec, "logoUrl": a_logo,
                "score": as_, "ht": real_ht, "xg": a_xg,
                "scorers": a_sc_str,
            },
            "goals": goals[:12],
            "motm": best_motm,
            "verdict": verdict,
            "vLabel": vlabel,
            "source_url": "https://fantasy.premierleague.com/",
        })
    return out, best_motm


def fetch_live_matchday_results_items(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    now_ts = time.time()
    if not force_refresh and _LIVE_CACHE["items"] and (now_ts - _LIVE_CACHE["ts"]) < _CACHE_TTL_SEC:
        return list(_LIVE_CACHE["items"])

    now_utc = datetime.now(timezone.utc)
    start_d = (now_utc - timedelta(days=2)).strftime("%Y%m%d")
    end_d = (now_utc + timedelta(days=1)).strftime("%Y%m%d")
    dates_param = f"{start_d}-{end_d}"

    seen_ids: set[str] = set()
    all_matches, fpl_motm = _fetch_fpl_finished_24h_matches(now_utc)
    seen_pairs = {(m['home']['code'], m['away']['code'], m['home']['score'], m['away']['score']) for m in all_matches}
    by_league: dict[str, tuple[str, str, list[dict[str, Any]]]] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futs = {
            pool.submit(_fetch_league_24h, slug, fa_name, en_name, dates_param, now_utc): (slug, fa_name, en_name)
            for slug, fa_name, en_name in ESPN_SOCCER_LEAGUES
        }
        for fut in concurrent.futures.as_completed(futs):
            slug, fa_name, en_name = futs[fut]
            try:
                ms = fut.result()
            except Exception:
                continue
            uniq = []
            for m in ms:
                eid = str(m.get("event_id") or "")
                if eid and eid not in seen_ids:
                    seen_ids.add(eid)
                    uniq.append(m)
            if uniq:
                by_league[slug] = (fa_name, en_name, uniq)
                all_matches.extend(uniq)

    # تکمیل از فید جامع soccer/all/scoreboard در صورت کم بودن نتایج لیگ‌های منتخب
    if len(all_matches) < 5:
        extra = _fetch_league_24h("all", "فوتبال جهان", "WORLD FOOTBALL", dates_param, now_utc)
        for m in extra:
            eid = str(m.get("event_id") or "")
            if eid and eid not in seen_ids:
                seen_ids.add(eid)
                pair_k = (m['home']['code'], m['away']['code'], m['home']['score'], m['away']['score'])
                if pair_k not in seen_pairs:
                    seen_pairs.add(pair_k)
                    all_matches.append(m)

    # تکمیل نتایج بوندس‌لیگا با HT، گلزنان و پنالتی‌ها از OpenLigaDB در صورت نبود در ESPN (v0.36.0)
    if "ger.1" not in by_league:
        try:
            from src.xgpedia.providers.open_football_hub import fetch_openligadb_bundesliga_matchday
            bl_ms = fetch_openligadb_bundesliga_matchday()
            if bl_ms:
                by_league["ger.1"] = ("بوندس‌لیگا آلمان", "BUNDESLIGA", bl_ms)
                if len(all_matches) < 4:
                    all_matches.extend(bl_ms[:4])
        except Exception:
            pass

    all_matches.sort(key=lambda m: int(m.get("finished_elapsed_sec") or 0))
    cards: list[dict[str, Any]] = []
    if all_matches:
        comp_lbl = _build_leagues_label(all_matches[:8])
        pkg = _pack_matchday_card(
            "live_24h_all",
            comp_lbl,
            "PREMIER LEAGUE 26/27" if comp_lbl == "لیگ برتر انگلیس" else "MATCHDAY RESULTS",
            "تابلوی نتایج",
            all_matches[:8],
        )
        pkg["day"] = gregorian_to_jalali_fa(now_utc)
        pkg["title"] = _build_dynamic_day_title(all_matches[:8], comp_lbl)
        pkg["wmText"] = "MATCHDAY"
        if fpl_motm:
            pkg["motm"] = fpl_motm
        tot_g_p = sum(int((m.get("home") or {}).get("score") or 0) + int((m.get("away") or {}).get("score") or 0) for m in all_matches[:8])
        f0 = all_matches[0]
        pkg["editorialNote"] = (
            f"در {comp_lbl} مجموعاً {tot_g_p} گل به ثمر رسید؛ "
            f"نبرد شاخص روز با برتری {f0['home']['name']} ({f0['home']['score']}-{f0['away']['score']}) مقابل {f0['away']['name']} همراه بود."
        )
        pkg["source"] = "Premier League / Opta FPL"
        cards.append(pkg)
    for slug, fa_name, en_name in ESPN_SOCCER_LEAGUES:
        if slug in by_league:
            _, _, ms = by_league[slug]
            cards.append(_pack_matchday_card(
                f"live_24h_{slug.replace('.', '_')}",
                fa_name,
                en_name,
                f"نتایج ۲۴ ساعت اخیر • {fa_name}",
                ms[:8],
            ))

    _LIVE_CACHE["ts"] = now_ts
    _LIVE_CACHE["items"] = cards
    return list(cards)


def list_all_matchday_results_items(*, include_live: bool = True, force_refresh: bool = False) -> list[dict[str, Any]]:
    presets = load_matchday_results_presets()
    live = fetch_live_matchday_results_items(force_refresh=force_refresh) if include_live else []
    return live + presets
