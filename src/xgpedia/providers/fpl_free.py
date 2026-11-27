"""پرووایدر رسمی و کاملاً رایگان Fantasy Premier League (بدون کلید API، بدون کلودفلر).

نقطهٔ پایانی رسمی لیگ برتر انگلیس:
  https://fantasy.premierleague.com/api/bootstrap-static/

در ۱ درخواست JSON سبک، اطلاعات رسمی Opta برای تمام ۲۰ تیم و همهٔ بازیکنان لیگ برتر را می‌دهد:
  - `expected_goal_involvements` (xG + xA رسمی)
  - `goals_scored`، `assists`، `minutes`، `element_type` (پست واقعی)
نتیجه: فعال‌سازی ۱۰۰٪ مطمئن ماژول «دوئل مهره‌های کلیدی (keyduel)» برای هر ۲۰ تیم لیگ برتر!
"""
from __future__ import annotations

from typing import Any

import httpx

from src.xgpedia.config import canonical_team_name

PROVIDER = "fpl-official"
FPL_BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"

FPL_TEAM_ALIASES: dict[str, str] = {
    "Man City": "Manchester City",
    "Man Utd": "Manchester United",
    "Nott'm Forest": "Nottingham Forest",
    "Spurs": "Tottenham",
    "Wolves": "Wolverhampton",
    "Newcastle": "Newcastle",
    "Brighton": "Brighton",
    "West Ham": "West Ham",
    "Leeds": "Leeds",
    "Hull": "Hull",
    "Ipswich": "Ipswich",
    "Coventry": "Coventry",
    "Sunderland": "Sunderland",
}

FPL_POS_FA: dict[int, str] = {
    1: "دروازه‌بان",
    2: "مدافع",
    3: "هافبک",
    4: "مهاجم",
}


def parse_fpl_key_players(payload: dict[str, Any]) -> dict[str, dict[str, str]]:
    """استخراج برترین مهرهٔ کلیدی هر ۲۰ تیم لیگ برتر از bootstrap-static رسمی FPL بر اساس xG+xA و گل/پاس گل."""
    team_id_to_canon: dict[int, str] = {}
    for t in payload.get("teams") or []:
        tid = t.get("id")
        raw = str(t.get("name") or "").strip()
        if tid is not None and raw:
            mapped = FPL_TEAM_ALIASES.get(raw, raw)
            team_id_to_canon[int(tid)] = canonical_team_name(mapped)

    best_by_team: dict[str, tuple[float, dict[str, str]]] = {}
    for el in payload.get("elements") or []:
        try:
            tid = int(el.get("team") or 0)
            team = team_id_to_canon.get(tid)
            if not team:
                continue
            mins = float(el.get("minutes") or 0)
            if mins < 90:
                continue
            # فقط بازیکنان میدانی (پست ۲، ۳، ۴) — نه دروازه‌بان
            et = int(el.get("element_type") or 3)
            if et == 1:
                continue
            xgi = float(el.get("expected_goal_involvements") or 0.0)
            goals = int(el.get("goals_scored") or 0)
            assists = int(el.get("assists") or 0)
            xgi90 = xgi * (90.0 / mins)
            score = xgi * 1.2 + (goals + assists) * 0.4 + xgi90 * 2.0
            first = str(el.get("first_name") or "").strip()
            second = str(el.get("second_name") or "").strip()
            web = str(el.get("web_name") or "").strip()
            full_name = f"{first} {second}".strip() if (first and second and len(f"{first} {second}") <= 22) else (web or second or first)
            if not full_name:
                continue
            cur = best_by_team.get(team)
            if cur is None or score > cur[0]:
                s1 = f"{xgi90:.2f} xG+xA" if xgi > 0 else f"{goals} گل"
                s2 = f"{goals} گل · {assists} پاس" if (goals or assists) else f"{int(mins)} دقیقه"
                best_by_team[team] = (
                    score,
                    {
                        "name": full_name,
                        "pos": FPL_POS_FA.get(et, "مهاجم"),
                        "s1": s1,
                        "s2": s2,
                    },
                )
        except (TypeError, ValueError):
            continue

    return {team: info for team, (_, info) in best_by_team.items()}



FPL_FIXTURES_URL = "https://fantasy.premierleague.com/api/fixtures/"
FPL_LIVE_GW_URL = "https://fantasy.premierleague.com/api/event/{gw}/live/"


def _bps_to_rating(bps: float, goals: int = 0, assists: int = 0) -> float:
    """شاخص نمایشی تخمینی از FPL BPS (این مقدار rating رسمی Opta/FotMob نیست)."""
    raw = 5.6 + (float(bps) / 11.2) + (0.25 if goals > 0 else 0.0) + (0.15 if assists > 0 else 0.0)
    return round(min(9.9, max(5.0, raw)), 1)


def parse_fpl_match_post_details(
    bootstrap: dict[str, Any],
    fixtures: list[dict[str, Any]],
    live_gw: dict[str, Any],
    home_en: str,
    away_en: str,
    match_date: str = "",
) -> dict[str, Any] | None:
    """استخراج آمار مسابقه از FPL Official (امتیاز BPS به‌عنوان شاخص تخمینی و xGC جدا از PSxG)."""
    h_canon = canonical_team_name(home_en)
    a_canon = canonical_team_name(away_en)

    tid_to_canon: dict[int, str] = {}
    for t in bootstrap.get("teams") or []:
        tid = t.get("id")
        raw = str(t.get("name") or "").strip()
        if tid is not None and raw:
            tid_to_canon[int(tid)] = canonical_team_name(FPL_TEAM_ALIASES.get(raw, raw))

    # پیدا کردن fixture دقیق FPL
    target_fx = None
    for fx in fixtures or []:
        if not isinstance(fx, dict):
            continue
        th = tid_to_canon.get(int(fx.get("team_h") or 0))
        ta = tid_to_canon.get(int(fx.get("team_a") or 0))
        if th == h_canon and ta == a_canon:
            if match_date:
                ko_d = str(fx.get("kickoff_time") or "")[:10]
                if ko_d and abs((int(ko_d.replace("-", "")) - int(match_date.replace("-", "")))) > 2:
                    continue
            target_fx = fx
            break
    if not target_fx:
        return None

    fx_id = int(target_fx.get("id") or 0)
    team_h_id = int(target_fx.get("team_h") or 0)
    team_a_id = int(target_fx.get("team_a") or 0)
    h_goals = int(target_fx.get("team_h_score") or 0)
    a_goals = int(target_fx.get("team_a_score") or 0)

    el_meta: dict[int, dict[str, Any]] = {}
    for el in bootstrap.get("elements") or []:
        if isinstance(el, dict) and el.get("id") is not None:
            el_meta[int(el["id"])] = el

    played: list[dict[str, Any]] = []
    home_gk = None
    away_gk = None

    for item in (live_gw.get("elements") or []):
        if not isinstance(item, dict):
            continue
        eid = int(item.get("id") or 0)
        meta = el_meta.get(eid)
        if not meta:
            continue
        tid = int(meta.get("team") or 0)
        if tid not in (team_h_id, team_a_id):
            continue
        side = "home" if tid == team_h_id else "away"
        # بررسی اینکه این بازیکن واقعاً در همین fixture بازی کرده (از explain)
        explains = item.get("explain") or []
        if fx_id and explains:
            if not any(isinstance(ex, dict) and int(ex.get("fixture") or 0) == fx_id for ex in explains):
                continue
        st = item.get("stats") if isinstance(item.get("stats"), dict) else {}
        mins = int(st.get("minutes") or 0)
        if mins <= 0:
            continue

        bps = float(st.get("bps") or 0)
        goals = int(st.get("goals_scored") or 0)
        assists = int(st.get("assists") or 0)
        saves = int(st.get("saves") or 0)
        _raw_xg = st.get("expected_goals")
        _raw_xa = st.get("expected_assists")
        _raw_xgc = st.get("expected_goals_conceded")
        xg = float(_raw_xg) if _raw_xg not in (None, "") else None
        xa = float(_raw_xa) if _raw_xa not in (None, "") else None
        xgc = float(_raw_xgc) if _raw_xgc not in (None, "") else None
        gc = int(st.get("goals_conceded") or 0)
        threat = float(st.get("threat") or 0.0)
        creativity = float(st.get("creativity") or 0.0)
        influence = float(st.get("influence") or 0.0)
        et = int(meta.get("element_type") or 3)
        name = str(meta.get("web_name") or f"{meta.get('first_name', '')} {meta.get('second_name', '')}").strip()
        if not name:
            continue

        rating = _bps_to_rating(bps, goals, assists)
        stat_parts: list[str] = []
        if goals:
            stat_parts.append(f"{goals} گل")
        if assists:
            stat_parts.append(f"{assists} پاس گل")
        if et == 1 and saves:
            stat_parts.append(f"{saves} مهار")
        if not stat_parts:
            if xg is not None and xa is not None and (xg + xa) >= 0.25:
                stat_parts.append(f"{xg + xa:.2f} xG+xA")
            else:
                stat_parts.append(f"{mins} دقیقه، BPS {int(bps)}")

        entry = {
            "name": name,
            "side": side,
            "pos": FPL_POS_FA.get(et, "بازیکن"),
            "number": int(meta.get("squad_number") or 0) or None,
            "stat": "، ".join(stat_parts[:2]),
            "rating": rating,
            "rating_method": "xgpedia_bps_proxy",
            "bps": bps,
            "goals": goals,
            "assists": assists,
            "xg": xg,
            "xa": xa,
            "saves": saves,
            "mins": mins,
            "et": et,
            "threat": threat,
            "creativity": creativity,
            "influence": influence,
        }
        played.append(entry)

        if et == 1 and mins >= 45:
            gk_obj = {
                "name": name,
                "saves": saves,
                "psxg": None,
                "xgc": round(xgc, 2) if xgc is not None else None,
                "ga": a_goals if side == "home" else h_goals,
            }
            if side == "home":
                home_gk = gk_obj
            else:
                away_gk = gk_obj

    if len(played) < 4:
        return None

    played.sort(key=lambda x: (-x["bps"], -x["goals"], -x["assists"], -x["mins"]))
    top5 = [
        {"name": p["name"], "side": p["side"], "stat": p["stat"], "rating": p["rating"]}
        for p in played[:5]
    ]

    best = played[0]
    opp_side = "away" if best["side"] == "home" else "home"
    opp_best = next((p for p in played if p["side"] == opp_side), played[1])

    # اطلاعات غیرتکراری و جذاب Opta (هرگز مقدار صفر برای شاخص‌های نهایی‌نشده نمایش داده نمی‌شود)
    if best.get("et") == 1:
        c2 = {"label": "تاثیرگذاری FPL", "val": f"{best['influence']:.0f}"} if best["influence"] > 0 else {"label": "امتیاز BPS", "val": str(int(best["bps"]))}
        chips = [
            {"label": "مهار شوت", "val": str(best["saves"])},
            c2,
            {"label": "دقیقه حضور", "val": f"{best['mins']}′"},
        ]
    else:
        c2 = (
            {"label": "تهدید دروازه", "val": f"{best['threat']:.0f}"}
            if best["threat"] > 0
            else ({"label": "امید گل (xG)", "val": f"{best['xg']:.2f}"} if best.get("xg") is not None else {"label": "امتیاز BPS", "val": str(int(best["bps"]))})
        )
        c3 = (
            {"label": "خلاقیت FPL", "val": f"{best['creativity']:.0f}"}
            if best["creativity"] > 0
            else (
                {"label": "امید پاس گل (xA)", "val": f"{best['xa']:.2f}"}
                if best.get("xa") is not None and best["xa"] > 0
                else {"label": "دقیقه حضور", "val": f"{best['mins']}′"}
            )
        )
        chips = [
            *([{"label": "xG + xA", "val": f"{best['xg'] + best['xa']:.2f}"}] if best.get("xg") is not None and best.get("xa") is not None else ([{"label": "امید گل (xG)", "val": f"{best['xg']:.2f}"}] if best.get("xg") is not None else [])),
            c2,
            c3,
        ]
    motm = {
        "side": best["side"],
        "name": best["name"],
        "pos": best["pos"],
        "number": best["number"],
        "rating": best["rating"],
        "chips": chips,
        "runnerUp": {
            "side": opp_best["side"],
            "name": opp_best["name"],
            "stat": opp_best["stat"],
            "rating": opp_best["rating"],
        },
    }

    return {
        "top_players": top5,
        "motm": motm,
        "home_gk": home_gk,
        "away_gk": away_gk,
    }


class FPLFreeProvider:
    """کلاینت رسمی و رایگان Fantasy Premier League (بدون نیاز به کلید API)."""

    def __init__(self, timeout: float = 15.0) -> None:
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0",
                "Accept": "application/json",
            },
        )

    def close(self) -> None:
        self._client.close()

    def fetch_key_players(self) -> dict[str, dict[str, str]]:
        r = self._client.get(FPL_BOOTSTRAP_URL)
        r.raise_for_status()
        return parse_fpl_key_players(r.json())

    def fetch_match_post_details(
        self, home_en: str, away_en: str, match_date: str = ""
    ) -> dict[str, Any] | None:
        """دریافت زندهٔ Top Rated، MOTM و دروازه‌بان (PSxG/Saves) یک بازی از API رسمی FPL."""
        r_bs = self._client.get(FPL_BOOTSTRAP_URL)
        r_bs.raise_for_status()
        bs = r_bs.json()
        # پیدا کردن شمارهٔ هفتهٔ جاری/آخرین هفتهٔ فعال
        events = bs.get("events") or []
        cur_ev = next((e for e in events if e.get("is_current")), None)
        if cur_ev is None:
            finished_evs = [e for e in events if e.get("finished")]
            cur_ev = finished_evs[-1] if finished_evs else None
        if not cur_ev:
            return None
        gw = int(cur_ev["id"])
        for cand_gw in (gw, max(1, gw - 1)):
            r_fx = self._client.get(FPL_FIXTURES_URL, params={"event": cand_gw})
            if r_fx.status_code != 200:
                continue
            r_lv = self._client.get(FPL_LIVE_GW_URL.format(gw=cand_gw))
            if r_lv.status_code != 200:
                continue
            parsed = parse_fpl_match_post_details(bs, r_fx.json(), r_lv.json(), home_en, away_en, match_date)
            if parsed:
                return parsed
        return None


# ---------------------------------------------------------------------------
# توابع عمومی و کش‌شده دریافت Bootstrap و Fixtures رسمی FPL (بدون requests)
# ---------------------------------------------------------------------------
_FPL_CACHE: dict[str, tuple[float, Any]] = {}
_FPL_CACHE_TTL = 600.0
_FPL_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
FPL_FIXTURES_URL = "https://fantasy.premierleague.com/api/fixtures/"


def _fpl_get_json_urllib(url: str, *, timeout: float = 9.0) -> Any:
    import json
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": _FPL_UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def fetch_fpl_bootstrap(*, force_refresh: bool = False, timeout: float = 9.0) -> dict[str, Any]:
    """دریافت کش‌شده و رایگان `bootstrap-static` رسمی لیگ برتر انگلیس (بدون کلید API و بدون requests)."""
    import time
    now = time.monotonic()
    hit = _FPL_CACHE.get("bootstrap")
    if not force_refresh and hit and (now - hit[0]) < _FPL_CACHE_TTL and isinstance(hit[1], dict):
        return hit[1]
    data = _fpl_get_json_urllib(FPL_BOOTSTRAP_URL, timeout=timeout)
    if isinstance(data, dict):
        _FPL_CACHE["bootstrap"] = (now, data)
        return data
    return {}


def fetch_fpl_fixtures(*, force_refresh: bool = False, timeout: float = 9.0) -> list[dict[str, Any]]:
    """دریافت کش‌شده و رایگان `fixtures` رسمی لیگ برتر انگلیس (بدون کلید API و بدون requests)."""
    import time
    now = time.monotonic()
    hit = _FPL_CACHE.get("fixtures")
    if not force_refresh and hit and (now - hit[0]) < _FPL_CACHE_TTL and isinstance(hit[1], list):
        return hit[1]
    data = _fpl_get_json_urllib(FPL_FIXTURES_URL, timeout=timeout)
    if isinstance(data, list):
        _FPL_CACHE["fixtures"] = (now, data)
        return data
    return []
