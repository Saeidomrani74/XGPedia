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
ESPN_EPL_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard"

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


def parse_espn_upcoming(payload: dict[str, Any]) -> dict[str, Any]:
    """استخراج ضرایب زنده و مهره‌های کلیدی از JSON بازی‌های پیش‌رو در ESPN."""
    odds_rows: list[dict[str, Any]] = []
    key_players: dict[str, dict[str, str]] = {}

    if not isinstance(payload, dict):
        return {"odds_rows": odds_rows, "key_players": key_players}
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

        h_name = _norm_espn_team((home_c.get("team") or {}).get("displayName") or "")
        a_name = _norm_espn_team((away_c.get("team") or {}).get("displayName") or "")

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

    return {"odds_rows": odds_rows, "key_players": key_players}


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
            out[team] = [round((v / n_m) + 0.06, 2) for v in b]
    return out


class ESPNFreeProvider:
    """کلاینت رایگان و بدون کلید API برای داده‌های زندهٔ لیگ برتر از ESPN."""

    def __init__(self, timeout: float = 15.0) -> None:
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"},
        )

    def close(self) -> None:
        self._client.close()

    def fetch_epl_enrichments(
        self, now_utc: datetime | None = None, match_dates: list[str] | None = None
    ) -> dict[str, Any]:
        """دریافت ضرایب زنده + مهره‌های کلیدی + موج زمانی ۱۵ دقیقه‌ای (فقط تک‌تاریخ معتبر برای جلوگیری از 400)."""
        now = now_utc or datetime.now(timezone.utc)
        # ۱) هفتهٔ جاری بدون پارامتر dates (همیشه HTTP 200)
        r_up = self._client.get(ESPN_EPL_SCOREBOARD)
        r_up.raise_for_status()
        up = parse_espn_upcoming(r_up.json())

        # ۲) تاریخچهٔ بازی‌های اخیر با تک‌تاریخ YYYYMMDD (از تاریخ بازی‌های واقعی ثبت‌شده در DB)
        dates_to_check: list[str] = []
        if match_dates:
            for d in match_dates[:12]:
                clean = str(d).replace("-", "")[:8]
                if len(clean) == 8 and clean.isdigit() and clean not in dates_to_check:
                    dates_to_check.append(clean)
        else:
            for delta in range(1, 22, 2):
                dates_to_check.append((now - timedelta(days=delta)).strftime("%Y%m%d"))

        merged_events: list[dict[str, Any]] = []
        for ymd in dates_to_check:
            try:
                r_h = self._client.get(ESPN_EPL_SCOREBOARD, params={"dates": ymd})
                if r_h.status_code == 200:
                    merged_events.extend(r_h.json().get("events") or [])
            except Exception:
                continue

        wave_map = parse_espn_timing_wave({"events": merged_events})
        if len(up["key_players"]) < 10 and merged_events:
            hist_up = parse_espn_upcoming({"events": merged_events})
            for t, kp in hist_up["key_players"].items():
                up["key_players"].setdefault(t, kp)

        return {
            "odds_rows": up["odds_rows"],
            "key_players": up["key_players"],
            "wave_map": wave_map,
        }
