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
