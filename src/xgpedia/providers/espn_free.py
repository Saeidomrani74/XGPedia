"""پرووایدر رایگان و بدون کلید API از ESPN Public Scoreboard JSON برای لیگ برتر انگلیس.

کاربرد در XGPedia (کاملاً رایگان، بدون کلید API، بدون کلودفلر):
  1) `odds`: ضرایب زندهٔ بازار برای بازی‌های پیش‌رو (تبدیل Moneyline آمریکایی به ضریب اعشاری) → فعال‌سازی ماژول `+EV / signals`
  2) `key_players`: برترین گلزنان/پاسورهای هر تیم از بخش `leaders` → فعال‌سازی ماژول `مهرهٔ کلیدی / keyduel`
  3) `wave`: توزیع واقعی دقایق گل‌زنی هر تیم در ۶ بازهٔ ۱۵ دقیقه‌ای (`0-15` تا `76-90`) از بازی‌های اخیر → فعال‌سازی ماژول `موج زمانی ۱۵ دقیقه‌ای / wave`
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from src.xgpedia.config import canonical_team_name

PROVIDER = "espn-public"
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.xgpedia.core.leagues import EUROPEAN_LEAGUES, LeagueSpec, league_by_espn_slug

ESPN_EPL_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard"
ESPN_EPL_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/summary"


def espn_scoreboard_url(slug: str = "eng.1") -> str:
    return f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard"


def espn_summary_url(slug: str = "eng.1") -> str:
    return f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/summary"

ESPN_TEAM_ALIASES: dict[str, str] = {
    "AFC Bournemouth": "Bournemouth",
    "Brighton & Hove Albion": "Brighton",
    "Hull City": "Hull",
    "Ipswich Town": "Ipswich",
    "Leeds United": "Leeds",
    "Leicester City": "Leicester",
    "Manchester City": "Manchester City",
    "Manchester United": "Manchester United",
    "Newcastle United": "Newcastle",
    "Nottingham Forest": "Nottingham Forest",
    "Tottenham Hotspur": "Tottenham",
    "West Ham United": "West Ham",
    "Wolverhampton Wanderers": "Wolverhampton",
    "Coventry City": "Coventry",
}


def _norm_espn_team(raw_name: str) -> str:
    s = (raw_name or "").strip()
    mapped = ESPN_TEAM_ALIASES.get(s, s)
    return canonical_team_name(mapped)


def american_to_decimal_odds(ml: Any) -> float | None:
    """تبدیل ضریب آمریکایی (+150 یا -120) به ضریب اعشاری اروپایی (2.50 یا 1.83)."""
    if ml is None:
        return None
    try:
        v = float(str(ml).strip().replace("+", ""))
    except (TypeError, ValueError):
        return None
    if v == 0:
        return None
    if v > 0:
        return round(1.0 + v / 100.0, 2)
    return round(1.0 + 100.0 / abs(v), 2)


def parse_espn_upcoming(payload: dict[str, Any], *, competition_name: str = "Premier League", league_slug: str = "eng.1") -> dict[str, Any]:
    """استخراج ضرایب زنده و مهره‌های کلیدی از JSON بازی‌های پیش‌رو در ESPN."""
    odds_rows: list[dict[str, Any]] = []
    key_players: dict[str, dict[str, str]] = {}
    upcoming_fixtures: list[dict[str, Any]] = []

    if not isinstance(payload, dict):
        return {"odds_rows": odds_rows, "key_players": key_players, "upcoming_fixtures": upcoming_fixtures}
    for ev in payload.get("events") or []:
        if not isinstance(ev, dict):
            continue
        comps = ev.get("competitions") or []
        if not comps or not isinstance(comps[0], dict):
            continue
        comp = comps[0]
        date_str = str(comp.get("date") or ev.get("date") or "")[:10]
        competitors = [c for c in (comp.get("competitors") or []) if isinstance(c, dict)]
        home_c = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away_c = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if not (home_c and away_c):
            continue

        h_tm_u = home_c.get("team") or {}
        a_tm_u = away_c.get("team") or {}
        h_name = _norm_espn_team(h_tm_u.get("displayName") or "")
        a_name = _norm_espn_team(a_tm_u.get("displayName") or "")
        try:
            from src.xgpedia.providers.dynamic_crests import register_team_logo
            if h_name and h_tm_u.get("logo"):
                register_team_logo(h_name, str(h_tm_u["logo"]))
            if a_name and a_tm_u.get("logo"):
                register_team_logo(a_name, str(a_tm_u["logo"]))
        except Exception:
            pass

        # ۰) بازی‌های شروع‌نشده برای همگام‌سازی خودکار همهٔ ۶ لیگ حتی در صورت محدودیت FDO
        st_obj = comp.get("status") if isinstance(comp.get("status"), dict) else {}
        st_type = st_obj.get("type") if isinstance(st_obj.get("type"), dict) else {}
        st_state = str(st_type.get("state") or "").lower()
        ko_full = str(comp.get("date") or ev.get("date") or "")
        eid_u = str(ev.get("id") or "")
        if h_name and a_name and st_state == "pre" and ko_full and eid_u:
            upcoming_fixtures.append({
                "event_id": eid_u,
                "home_team": h_name,
                "away_team": a_name,
                "kickoff_utc": ko_full,
                "competition": competition_name,
                "league_slug": league_slug,
            })

        # ۱) ضرایب زنده
        odds_list = [o for o in (comp.get("odds") or []) if isinstance(o, dict)]
        if odds_list and date_str and h_name and a_name:
            od = odds_list[0]
            h_odd = american_to_decimal_odds((od.get("homeTeamOdds") or {}).get("moneyLine"))
            a_odd = american_to_decimal_odds((od.get("awayTeamOdds") or {}).get("moneyLine"))
            d_odd = american_to_decimal_odds((od.get("drawOdds") or {}).get("moneyLine"))
            ou_val = od.get("overUnder")
            o25_odd = american_to_decimal_odds(od.get("overOdds")) if ou_val in (2.5, "2.5") else None
            if h_odd or a_odd or d_odd:
                odds_rows.append({
                    "home_team": h_name,
                    "away_team": a_name,
                    "match_date": date_str,
                    "home_odds": h_odd,
                    "draw_odds": d_odd,
                    "away_odds": a_odd,
                    "over25_odds": o25_odd,
                    "btts_odds": None,
                })

        # ۲) مهرهٔ کلیدی (گلزن برتر) از leaders هر تیم
        for c_obj, t_canon in ((home_c, h_name), (away_c, a_name)):
            if not t_canon or t_canon in key_players:
                continue
            leaders = [cat for cat in (c_obj.get("leaders") or []) if isinstance(cat, dict)]
            scorer_cat = next(
                (cat for cat in leaders if "goal" in str(cat.get("name") or "").lower()),
                leaders[0] if leaders else None,
            )
            assist_cat = next(
                (cat for cat in leaders if "assist" in str(cat.get("name") or "").lower()),
                None,
            )
            sc_leaders = [x for x in (scorer_cat.get("leaders") or []) if isinstance(x, dict)] if scorer_cat else []
            if sc_leaders:
                top = sc_leaders[0]
                ath = top.get("athlete") if isinstance(top.get("athlete"), dict) else {}
                pname = str(ath.get("displayName") or ath.get("shortName") or "").strip()
                val = str(top.get("displayValue") or top.get("value") or "").strip()
                pos = str((ath.get("position") or {}).get("abbreviation") or "").upper()
                pos_fa = {"F": "مهاجم", "FW": "مهاجم", "M": "هافبک", "MF": "هافبک", "D": "مدافع"}.get(pos, "مهاجم")
                s2 = "مهره کلیدی تیم"
                as_leaders = [x for x in (assist_cat.get("leaders") or []) if isinstance(x, dict)] if assist_cat else []
                if as_leaders:
                    a_top = as_leaders[0]
                    a_ath = a_top.get("athlete") if isinstance(a_top.get("athlete"), dict) else {}
                    if str(a_ath.get("displayName") or "").strip() == pname:
                        s2 = f"{a_top.get('displayValue') or a_top.get('value')} پاس گل"
                if pname:
                    key_players[t_canon] = {
                        "name": pname,
                        "pos": pos_fa,
                        "s1": f"{val} گل" if val else "گلزن برتر",
                        "s2": s2,
                    }

    return {"odds_rows": odds_rows, "key_players": key_players, "upcoming_fixtures": upcoming_fixtures}


def parse_espn_timing_wave(payload: dict[str, Any]) -> dict[str, list[float]]:
    """محاسبهٔ توزیع واقعی ۶ بازهٔ ۱۵ دقیقه‌ای (`0-15` تا `76-90`) از دقایق واقعی گل‌های تیم‌ها در بازی‌های اخیر."""
    buckets_by_team: dict[str, list[float]] = {}
    matches_by_team: dict[str, int] = {}

    if not isinstance(payload, dict):
        return {}
    for ev in payload.get("events") or []:
        if not isinstance(ev, dict):
            continue
        comps = ev.get("competitions") or []
        if not comps or not isinstance(comps[0], dict):
            continue
        comp = comps[0]
        st_obj = comp.get("status") if isinstance(comp.get("status"), dict) else {}
        st_type = st_obj.get("type") if isinstance(st_obj.get("type"), dict) else {}
        status_state = str(st_type.get("state") or "").lower()
        if status_state != "post":
            continue
        id_to_team: dict[str, str] = {}
        for c in comp.get("competitors") or []:
            if not isinstance(c, dict):
                continue
            tm_obj = c.get("team") if isinstance(c.get("team"), dict) else {}
            tid = str(tm_obj.get("id") or "")
            tname = _norm_espn_team(tm_obj.get("displayName") or "")
            if tid and tname:
                id_to_team[tid] = tname
                buckets_by_team.setdefault(tname, [0.0] * 6)
                matches_by_team[tname] = matches_by_team.get(tname, 0) + 1

        for det in comp.get("details") or []:
            if not isinstance(det, dict) or not det.get("scoringPlay"):
                continue
            dtm = det.get("team") if isinstance(det.get("team"), dict) else {}
            tid = str(dtm.get("id") or "")
            tname = id_to_team.get(tid)
            if not tname:
                continue
            sec = (det.get("clock") or {}).get("value")
            if sec is None:
                continue
            try:
                minute = float(sec) / 60.0
            except (TypeError, ValueError):
                continue
            idx = min(5, max(0, int((max(1.0, minute) - 1.0) // 15)))
            buckets_by_team[tname][idx] += 1.0

    # نرمال‌سازی به میانگین هر بازی در هر بازهٔ ۱۵ دقیقه‌ای (فقط برای تیم‌هایی با حداقل ۲ بازی و ۱ گل)
    out: dict[str, list[float]] = {}
    for team, b in buckets_by_team.items():
        n_m = matches_by_team.get(team, 0)
        if n_m >= 2 and sum(b) > 0:
            # افزودن پس‌زمینهٔ بسیار جزئی ۰.۰۶ برای هموارسازی منحنی بدون صفر مطلق
            out[team] = [round(v / n_m, 2) for v in b]
    return out




def _parse_espn_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        s = str(val).strip().replace("%", "")
        return float(s)
    except (TypeError, ValueError):
        return None


def parse_espn_finished_summary(
    summary: dict[str, Any],
    scoreboard_event: dict[str, Any] | None = None,
    *,
    competition_name: str = "Premier League",
    league_slug: str = "eng.1",
) -> dict[str, Any] | None:
    """استخراج آمار واقعی و کامل یک بازی پایان‌یافته از ESPN `/summary?event={id}` (کاملاً رایگان).

    قانون `null ≠ 0`: هیچ عددی ساخته یا هاردکد نمی‌شود؛ فقط آمارهای واقعی برگشتی از ESPN استخراج می‌شوند.
    """
    if not isinstance(summary, dict):
        return None
    header = summary.get("header") if isinstance(summary.get("header"), dict) else {}
    comps = [c for c in (header.get("competitions") or []) if isinstance(c, dict)]
    if not comps and isinstance(scoreboard_event, dict):
        comps = [c for c in (scoreboard_event.get("competitions") or []) if isinstance(c, dict)]
    if not comps:
        return None
    comp = comps[0]

    st_obj = comp.get("status") if isinstance(comp.get("status"), dict) else {}
    st_type = st_obj.get("type") if isinstance(st_obj.get("type"), dict) else {}
    state = str(st_type.get("state") or "").lower()
    if state and state != "post":
        return None

    competitors = [c for c in (comp.get("competitors") or []) if isinstance(c, dict)]
    home_c = next((c for c in competitors if c.get("homeAway") == "home"), None)
    away_c = next((c for c in competitors if c.get("homeAway") == "away"), None)
    if not (home_c and away_c):
        return None

    h_tm = home_c.get("team") if isinstance(home_c.get("team"), dict) else {}
    a_tm = away_c.get("team") if isinstance(away_c.get("team"), dict) else {}
    h_name = _norm_espn_team(str(h_tm.get("displayName") or h_tm.get("name") or ""))
    a_name = _norm_espn_team(str(a_tm.get("displayName") or a_tm.get("name") or ""))
    try:
        from src.xgpedia.providers.dynamic_crests import register_team_logo
        for _tn, _to in ((h_name, h_tm), (a_name, a_tm)):
            _lurl = str(_to.get("logo") or "").strip()
            if not _lurl and isinstance(_to.get("logos"), list) and _to["logos"]:
                _lurl = str((_to["logos"][0] or {}).get("href") or "").strip()
            if _tn and _lurl:
                register_team_logo(_tn, _lurl)
    except Exception:
        pass
    h_id = str(h_tm.get("id") or "")
    a_id = str(a_tm.get("id") or "")
    if not (h_name and a_name):
        return None

    try:
        hg = int(float(home_c.get("score"))) if home_c.get("score") is not None else None
        ag = int(float(away_c.get("score"))) if away_c.get("score") is not None else None
    except (TypeError, ValueError):
        hg = ag = None
    if hg is None or ag is None:
        return None

    event_id = str(header.get("id") or (scoreboard_event.get("id") if isinstance(scoreboard_event, dict) else "") or "")
    kickoff_utc = str(comp.get("date") or (scoreboard_event.get("date") if isinstance(scoreboard_event, dict) else "") or "")
    if kickoff_utc and not kickoff_utc.endswith("Z") and "+" not in kickoff_utc:
        kickoff_utc = kickoff_utc + "Z"

    # آمار واقعی دو تیم از boxscore.teams
    box = summary.get("boxscore") if isinstance(summary.get("boxscore"), dict) else {}
    stat_map = {
        "possessionpct": "possession",
        "totalshots": "total_shots",
        "shotsontarget": "shots_on_target",
        "woncorners": "corner_kicks",
        "foulscommitted": "fouls",
        "expectedgoals": "expected_goals",
        "saves": "saves",
        "goalkeepersaves": "saves",
    }
    team_stats: dict[str, dict[str, float]] = {"home": {}, "away": {}}
    for bt in box.get("teams") or []:
        if not isinstance(bt, dict):
            continue
        t_obj = bt.get("team") if isinstance(bt.get("team"), dict) else {}
        tid = str(t_obj.get("id") or "")
        side_key = "home" if tid == h_id else ("away" if tid == a_id else None)
        if side_key is None:
            tn = _norm_espn_team(str(t_obj.get("displayName") or ""))
            side_key = "home" if tn == h_name else ("away" if tn == a_name else None)
        if side_key is None:
            continue
        for st_item in bt.get("statistics") or []:
            if not isinstance(st_item, dict):
                continue
            k_raw = str(st_item.get("name") or "").strip().lower()
            lbl_raw = str(st_item.get("label") or "").strip().lower()
            mapped = stat_map.get(k_raw) or stat_map.get(lbl_raw)
            if not mapped and ("expected goal" in lbl_raw or "expectedgoal" in k_raw or k_raw == "xg"):
                mapped = "expected_goals"
            if mapped:
                val = _parse_espn_float(st_item.get("displayValue"))
                if val is not None:
                    team_stats[side_key][mapped] = val

    # قاعدهٔ هویتی XGPedia (null ≠ 0): هرگز xG ساختگی از تعداد شوت تولید نمی‌شود؛
    # xG واقعی Opta از موتور `xg_engine` (SofaScore → FotMob → Understat) تامین می‌شود.

    # استخراج گلزنان واقعی با دقیقه (مرتب زمانی) + موج فشار ۵ دقیقه‌ای از کل commentary + keyEvents
    import re as _re

    key_events = [k for k in (summary.get("keyEvents") or []) if isinstance(k, dict)]
    commentary = [c for c in (summary.get("commentary") or []) if isinstance(c, dict)]
    scorers_h_raw: list[tuple[int, str]] = []
    scorers_a_raw: list[tuple[int, str]] = []
    mom_buckets = [0.0] * 18
    timed_events = 0

    def _extract_minute(clk_obj: Any) -> int | None:
        if not isinstance(clk_obj, dict):
            return None
        cv = _parse_espn_float(clk_obj.get("value"))
        if cv is not None and cv > 0:
            return int(round(cv / 60.0))
        cd = str(clk_obj.get("displayValue") or "").strip()
        mm = _re.search(r"(\d+)", cd)
        return int(mm.group(1)) if mm else None

    def _side_from_team_obj(t_obj: Any) -> str | None:
        if not isinstance(t_obj, dict):
            return None
        tid = str(t_obj.get("id") or "")
        if tid == h_id:
            return "home"
        if tid == a_id:
            return "away"
        tn = _norm_espn_team(str(t_obj.get("displayName") or t_obj.get("name") or ""))
        if tn == h_name:
            return "home"
        if tn == a_name:
            return "away"
        return None

    for ev in key_events:
        ev_type = ev.get("type") if isinstance(ev.get("type"), dict) else {}
        t_txt = str(ev_type.get("text") or ev_type.get("type") or "").lower()
        side = _side_from_team_obj(ev.get("team"))
        minute = _extract_minute(ev.get("clock"))

        # گلزنان واقعی (با علامت ′ بدون مشکل HTML entity)
        if ev.get("scoringPlay") or "goal" in t_txt:
            parts = [p for p in (ev.get("participants") or []) if isinstance(p, dict)]
            scorer_name = ""
            if parts:
                ath = parts[0].get("athlete") if isinstance(parts[0].get("athlete"), dict) else {}
                scorer_name = str(ath.get("shortName") or ath.get("displayName") or "").strip()
            if scorer_name:
                m_lbl = f" {minute}′" if minute is not None else ""
                entry = f"{scorer_name}{m_lbl}"
                if side == "home":
                    scorers_h_raw.append((minute or 99, entry))
                elif side == "away":
                    scorers_a_raw.append((minute or 99, entry))

        # رویدادهای کلیدی (فقط اگر commentary خالی بود یا به‌عنوان مکمل)
        if not commentary and side and minute is not None:
            b_idx = min(17, max(0, (max(1, minute) - 1) // 5))
            weight = 35.0 if (ev.get("scoringPlay") or "goal" in t_txt) else (
                18.0 if ("shot" in t_txt or "save" in t_txt or "penalty" in t_txt) else (
                    10.0 if ("corner" in t_txt or "offside" in t_txt) else (
                        5.0 if ("foul" in t_txt or "card" in t_txt) else 0.0
                    )
                )
            )
            if weight > 0:
                mom_buckets[b_idx] += weight if side == "home" else -weight
                timed_events += 1

    # استفاده از commentary کامل دقیقه‌به‌دقیقه (۶۰ تا ۱۲۰ رویداد واقعی در طول ۹۰ دقیقه!) برای موج فشار واقعی شبیه FotMob
    for cm in commentary:
        play = cm.get("play") if isinstance(cm.get("play"), dict) else {}
        pt = play.get("type") if isinstance(play.get("type"), dict) else {}
        t_txt = (str(pt.get("text") or "") + " " + str(cm.get("text") or "")).lower()
        side = _side_from_team_obj(play.get("team"))
        if side is None:
            # تشخیص تیم از متن گزارش رسمی ESPN در صورت نبود play.team
            if h_name.lower() in t_txt and a_name.lower() not in t_txt:
                side = "home"
            elif a_name.lower() in t_txt and h_name.lower() not in t_txt:
                side = "away"
        minute = _extract_minute(cm.get("time")) or _extract_minute(play.get("clock"))
        if not side or minute is None:
            continue
        b_idx = min(17, max(0, (max(1, minute) - 1) // 5))
        weight = 0.0
        if play.get("scoringPlay") or "goal!" in t_txt:
            weight = 36.0
        elif "attempt saved" in t_txt or "hit the" in t_txt or "penalty" in t_txt:
            weight = 22.0
        elif "attempt missed" in t_txt or "attempt blocked" in t_txt or "shot" in t_txt:
            weight = 15.0
        elif "corner" in t_txt:
            weight = 11.0
        elif "free kick" in t_txt or "offside" in t_txt or "dangerous" in t_txt:
            weight = 7.0
        elif "foul" in t_txt:
            # خطای تیم مقابل یعنی فشار تیم صاحب توپ
            weight = 4.0
        if weight > 0:
            mom_buckets[b_idx] += weight if side == "home" else -weight
            timed_events += 1

    scorers_h_raw.sort(key=lambda x: x[0])
    scorers_a_raw.sort(key=lambda x: x[0])
    scorers_h = [e for _, e in scorers_h_raw]
    scorers_a = [e for _, e in scorers_a_raw]
    momentum = [round(v, 1) for v in mom_buckets] if timed_events >= 6 else None

    # استخراج نام دروازه‌بان واقعی از rosters (در صورت وجود saves واقعی)
    gk_info: dict[str, dict[str, Any] | None] = {"home": None, "away": None}
    for rost in summary.get("rosters") or []:
        if not isinstance(rost, dict):
            continue
        t_obj = rost.get("team") if isinstance(rost.get("team"), dict) else {}
        tid = str(t_obj.get("id") or "")
        sk = "home" if tid == h_id else ("away" if tid == a_id else None)
        if not sk:
            continue
        opp = "away" if sk == "home" else "home"
        ga_val = ag if sk == "home" else hg
        opp_xg = team_stats[opp].get("expected_goals")
        saves_val = team_stats[sk].get("saves")
        for pl in rost.get("roster") or []:
            if not isinstance(pl, dict):
                continue
            pos_obj = pl.get("position") if isinstance(pl.get("position"), dict) else {}
            pos_abbr = str(pos_obj.get("abbreviation") or "").upper()
            if pos_abbr in ("G", "GK") and pl.get("starter"):
                ath = pl.get("athlete") if isinstance(pl.get("athlete"), dict) else {}
                gk_name = str(ath.get("shortName") or ath.get("displayName") or "").strip()
                eff_saves = saves_val
                if eff_saves is None:
                    for pst in pl.get("stats") or []:
                        if not isinstance(pst, dict):
                            continue
                        pk = str(pst.get("name") or pst.get("abbreviation") or "").strip().lower()
                        if pk in ("saves", "sv", "goalkeepersaves"):
                            sv = _parse_espn_float(pst.get("value") if pst.get("value") is not None else pst.get("displayValue"))
                            if sv is not None:
                                eff_saves = sv
                                break
                if gk_name and eff_saves is not None:
                    gk_info[sk] = {
                        "name": gk_name,
                        "saves": int(round(eff_saves)),
                        "psxg": round(float(opp_xg), 2) if opp_xg is not None else None,
                        "ga": int(ga_val),
                    }
                break

    return {
        "event_id": event_id,
        "competition": competition_name,
        "league_slug": league_slug,
        "home_team": h_name,
        "away_team": a_name,
        "kickoff_utc": kickoff_utc,
        "home_goals": hg,
        "away_goals": ag,
        "home_stats": team_stats["home"],
        "away_stats": team_stats["away"],
        "details": {
            "scorers_home": "، ".join(scorers_h[:5]),
            "scorers_away": "، ".join(scorers_a[:5]),
            "momentum": momentum,
            "home_gk": gk_info["home"],
            "away_gk": gk_info["away"],
        },
    }




def parse_espn_scoreboard_finished(
    payload: dict[str, Any],
    *,
    competition_name: str = "UEFA Europa League",
    league_slug: str = "uefa.europa",
) -> list[dict[str, Any]]:
    """استخراج بازی‌های پایان‌یافته و آمار واقعی آن‌ها از پاسخ scoreboard ESPN (برای تاریخچهٔ فصل لیگ اروپا و چمپیونزلیگ)."""
    out: list[dict[str, Any]] = []
    if not isinstance(payload, dict):
        return out
    stat_map = {
        "possessionpct": "possession",
        "totalshots": "total_shots",
        "shotsontarget": "shots_on_target",
        "woncorners": "corner_kicks",
        "foulscommitted": "fouls",
    }
    for ev in payload.get("events") or []:
        if not isinstance(ev, dict):
            continue
        comps = ev.get("competitions") or []
        comp = comps[0] if comps and isinstance(comps[0], dict) else {}
        st_type = ((comp.get("status") or ev.get("status") or {}).get("type") or {})
        if not st_type.get("completed") and str(st_type.get("state") or "").lower() != "post":
            continue
        competitors = comp.get("competitors") or []
        home_c = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away_c = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if not (home_c and away_c):
            continue
        h_name = _norm_espn_team(str(((home_c.get("team") or {}).get("displayName")) or ""))
        a_name = _norm_espn_team(str(((away_c.get("team") or {}).get("displayName")) or ""))
        if not (h_name and a_name):
            continue
        try:
            hg = int(float(home_c.get("score")))
            ag = int(float(away_c.get("score")))
        except (TypeError, ValueError):
            continue
        kickoff_utc = str(comp.get("date") or ev.get("date") or "")
        if kickoff_utc and not kickoff_utc.endswith("Z") and "+" not in kickoff_utc:
            kickoff_utc = kickoff_utc + "Z"

        def _extract_side_stats(c_obj: dict[str, Any]) -> dict[str, float]:
            res_s: dict[str, float] = {}
            for st_item in c_obj.get("statistics") or []:
                if not isinstance(st_item, dict):
                    continue
                k_raw = str(st_item.get("name") or "").strip().lower()
                mapped = stat_map.get(k_raw)
                if mapped:
                    val = _parse_espn_float(st_item.get("displayValue"))
                    if val is not None:
                        res_s[mapped] = val
            return res_s

        out.append({
            "event_id": str(ev.get("id") or ""),
            "competition": competition_name,
            "league_slug": league_slug,
            "home_team": h_name,
            "away_team": a_name,
            "kickoff_utc": kickoff_utc,
            "home_goals": hg,
            "away_goals": ag,
            "home_stats": _extract_side_stats(home_c),
            "away_stats": _extract_side_stats(away_c),
            "details": {},
        })
    return out


class ESPNFreeProvider:
    """کلاینت رایگان و بدون کلید API برای داده‌های زندهٔ ۶ لیگ معتبر اروپا از ESPN."""

    def __init__(self, timeout: float = 15.0) -> None:
        self._timeout = timeout
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"},
        )

    def close(self) -> None:
        self._client.close()

    def _resolve_leagues(self, leagues: list[str] | tuple[str, ...] | None) -> list[LeagueSpec]:
        if not leagues:
            return list(EUROPEAN_LEAGUES)
        out: list[LeagueSpec] = []
        for item in leagues:
            spec = league_by_espn_slug(str(item))
            if spec:
                out.append(spec)
        return out or list(EUROPEAN_LEAGUES)

    def fetch_epl_enrichments(
        self,
        now_utc: datetime | None = None,
        match_dates: list[str] | None = None,
        leagues: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        """دریافت ضرایب زنده + مهره‌های کلیدی + بازی‌های پیش‌رو + موج زمانی ۱۵ دقیقه‌ای برای همهٔ ۶ لیگ اروپا."""
        now = now_utc or datetime.now(timezone.utc)
        target_leagues = self._resolve_leagues(leagues)

        all_odds: list[dict[str, Any]] = []
        all_kp: dict[str, dict[str, str]] = {}
        all_upcoming: list[dict[str, Any]] = []
        all_waves: dict[str, list[float]] = {}

        dates_to_check: list[str] = []
        if match_dates:
            for d in match_dates[:12]:
                clean = str(d).replace("-", "")[:8]
                if len(clean) == 8 and clean.isdigit() and clean not in dates_to_check:
                    dates_to_check.append(clean)
        else:
            for delta in range(1, 15, 2):
                dates_to_check.append((now - timedelta(days=delta)).strftime("%Y%m%d"))

        def _fetch_one_league(spec: LeagueSpec) -> tuple[dict[str, Any], dict[str, list[float]]]:
            sb_url = espn_scoreboard_url(spec.espn_slug)
            up_local: dict[str, Any] = {"odds_rows": [], "key_players": {}, "upcoming_fixtures": []}
            merged_events: list[dict[str, Any]] = []
            try:
                r_up = self._client.get(sb_url)
                if r_up.status_code == 200:
                    up_local = parse_espn_upcoming(
                        r_up.json(), competition_name=spec.name_en, league_slug=spec.espn_slug
                    )
            except Exception:
                pass
            for ymd in dates_to_check[:6]:
                try:
                    r_h = self._client.get(sb_url, params={"dates": ymd})
                    if r_h.status_code == 200:
                        merged_events.extend(r_h.json().get("events") or [])
                except Exception:
                    continue
            wmap = parse_espn_timing_wave({"events": merged_events})
            if len(up_local["key_players"]) < 10 and merged_events:
                hist_up = parse_espn_upcoming(
                    {"events": merged_events}, competition_name=spec.name_en, league_slug=spec.espn_slug
                )
                for t, kp in hist_up["key_players"].items():
                    up_local["key_players"].setdefault(t, kp)
            return up_local, wmap

        with ThreadPoolExecutor(max_workers=min(6, len(target_leagues))) as ex:
            futs = [ex.submit(_fetch_one_league, spec) for spec in target_leagues]
            for fut in as_completed(futs):
                try:
                    up_l, w_l = fut.result()
                    all_odds.extend(up_l.get("odds_rows") or [])
                    all_upcoming.extend(up_l.get("upcoming_fixtures") or [])
                    for t, kp in (up_l.get("key_players") or {}).items():
                        all_kp.setdefault(t, kp)
                    for t, wv in (w_l or {}).items():
                        all_waves.setdefault(t, wv)
                except Exception:
                    continue

        return {
            "odds_rows": all_odds,
            "key_players": all_kp,
            "wave_map": all_waves,
            "upcoming_fixtures": all_upcoming,
        }

    def fetch_recent_finished_matches(
        self,
        now_utc: datetime | None = None,
        hours: float = 24.0,
        leagues: list[str] | tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        """دریافت زندهٔ بازی‌های پایان‌یافته از ۱ ثانیه پیش تا `hours` ساعت پیش در همهٔ ۶ لیگ معتبر اروپا همراه با آمار واقعی `/summary`."""
        now = now_utc or datetime.now(timezone.utc)
        target_leagues = self._resolve_leagues(leagues)
        dates = [
            now.strftime("%Y%m%d"),
            (now - timedelta(days=1)).strftime("%Y%m%d"),
        ]

        def _fetch_league_finished(spec: LeagueSpec) -> list[dict[str, Any]]:
            sb_url = espn_scoreboard_url(spec.espn_slug)
            sum_url = espn_summary_url(spec.espn_slug)
            seen_local: set[str] = set()
            out_local: list[dict[str, Any]] = []
            for ymd in dates:
                try:
                    r = self._client.get(sb_url, params={"dates": ymd})
                    if r.status_code != 200:
                        continue
                    payload = r.json()
                except Exception:
                    continue
                for ev in (payload.get("events") or []):
                    if not isinstance(ev, dict):
                        continue
                    eid = str(ev.get("id") or "")
                    if not eid or eid in seen_local:
                        continue
                    comps = [c for c in (ev.get("competitions") or []) if isinstance(c, dict)]
                    if not comps:
                        continue
                    st_obj = comps[0].get("status") if isinstance(comps[0].get("status"), dict) else {}
                    st_type = st_obj.get("type") if isinstance(st_obj.get("type"), dict) else {}
                    if str(st_type.get("state") or "").lower() != "post":
                        continue
                    ko_raw = str(comps[0].get("date") or ev.get("date") or "")
                    try:
                        ko_dt = datetime.fromisoformat(ko_raw.replace("Z", "+00:00"))
                        est_end = ko_dt + timedelta(minutes=115)
                        if ko_dt > now:
                            continue
                        elapsed_from_end = (now - min(est_end, now)).total_seconds()
                        if (now - ko_dt).total_seconds() > (hours + 2.5) * 3600.0:
                            continue
                        if elapsed_from_end > hours * 3600.0:
                            continue
                    except Exception:
                        pass
                    seen_local.add(eid)
                    try:
                        rs = self._client.get(sum_url, params={"event": eid})
                        if rs.status_code == 200:
                            parsed = parse_espn_finished_summary(
                                rs.json(),
                                scoreboard_event=ev,
                                competition_name=spec.name_en,
                                league_slug=spec.espn_slug,
                            )
                            if parsed:
                                out_local.append(parsed)
                    except Exception:
                        continue
            return out_local

        seen_ids: set[str] = set()
        results: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=min(6, len(target_leagues))) as ex:
            futs = [ex.submit(_fetch_league_finished, spec) for spec in target_leagues]
            for fut in as_completed(futs):
                try:
                    for item in fut.result():
                        eid = str(item.get("event_id") or "")
                        if eid and eid in seen_ids:
                            continue
                        if eid:
                            seen_ids.add(eid)
                        results.append(item)
                except Exception:
                    continue
        return results

    def fetch_competition_season_finished_matches(
        self,
        league_slug: str = "uefa.europa",
        *,
        competition_name: str = "UEFA Europa League",
        now_utc: datetime | None = None,
        days_back: int = 95,
    ) -> list[dict[str, Any]]:
        """دریافت تمام بازی‌های پایان‌یافتهٔ فصل جاری یک رقابت (مانند لیگ اروپا/چمپیونزلیگ) از تقویم رسمی ESPN."""
        from concurrent.futures import ThreadPoolExecutor

        now = now_utc or datetime.now(timezone.utc)
        min_day = (now - timedelta(days=days_back)).strftime("%Y-%m-%d")
        today_day = now.strftime("%Y-%m-%d")
        base_url = espn_scoreboard_url(league_slug)

        import logging as _logging
        _log = _logging.getLogger(__name__)

        # ۱) خواندن لیست دقیق روزهای برگزاری فصل جاری از leagues[0].calendar در ESPN (پشتیبانی از str و dict)
        cal_ymds: list[str] = []

        def _collect_cal_dates(node: Any) -> None:
            if isinstance(node, str):
                d_str = node[:10]
                if len(d_str) == 10 and d_str[4] == "-" and min_day <= d_str <= today_day:
                    ymd = d_str.replace("-", "")
                    if ymd not in cal_ymds:
                        cal_ymds.append(ymd)
            elif isinstance(node, dict):
                for k in ("startDate", "endDate", "date", "value"):
                    if isinstance(node.get(k), str):
                        _collect_cal_dates(node[k])
                for k in ("entries", "calendar"):
                    if isinstance(node.get(k), list):
                        for sub in node[k]:
                            _collect_cal_dates(sub)
            elif isinstance(node, list):
                for sub in node:
                    _collect_cal_dates(sub)

        try:
            r0 = self._client.get(base_url)
            if r0.status_code == 200:
                p0 = r0.json()
                for lg in p0.get("leagues") or []:
                    if isinstance(lg, dict):
                        _collect_cal_dates(lg.get("calendar"))
        except Exception as e_cal:
            _log.warning("espn_free calendar fetch failed for %s: %s", league_slug, e_cal)

        # ۲) اگر تقویم در پاسخ نبود، بازه را به پنجره‌های ۷ روزه تقسیم می‌کنیم تا ESPN محدودیت بازه نزند
        query_tokens: list[str] = cal_ymds[-16:] if cal_ymds else []
        if not query_tokens:
            cur_end = now
            while (now - cur_end).days < days_back:
                cur_start = max(now - timedelta(days=days_back), cur_end - timedelta(days=6))
                query_tokens.append(f"{cur_start.strftime('%Y%m%d')}-{cur_end.strftime('%Y%m%d')}")
                cur_end = cur_start - timedelta(days=1)

        def _fetch_token(tok: str) -> list[dict[str, Any]]:
            try:
                with httpx.Client(
                    timeout=self._timeout,
                    follow_redirects=True,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"},
                ) as cl:
                    r = cl.get(base_url, params={"dates": tok})
                    if r.status_code != 200:
                        return []
                    return parse_espn_scoreboard_finished(
                        r.json(), competition_name=competition_name, league_slug=league_slug
                    )
            except Exception:
                return []

        results: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        with ThreadPoolExecutor(max_workers=6) as pool:
            for chunk in pool.map(_fetch_token, query_tokens):
                for item in chunk:
                    key = item.get("event_id") or f"{item.get('kickoff_utc')}:{item.get('home_team')}:{item.get('away_team')}"
                    if key not in seen_ids:
                        seen_ids.add(key)
                        results.append(item)
        return results
