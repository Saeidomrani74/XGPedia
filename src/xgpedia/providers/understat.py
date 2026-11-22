"""آداپتر رایگان Understat — استخراج مهرهٔ کلیدی تیم‌ها، PPDA و نقشه شوت / xG Race.

چرا Understat؟
  - کاملاً رایگان و بدون نیاز به کلید API برای ۵ لیگ معتبر اروپا (از جمله لیگ برتر انگلیس).
  - داده‌های JSON ساختاریافته (playersData، teamsData، datesData، shotsData) مستقیماً
    درون صفحات عمومی آن قرار دارد.
  - کاملاً fault-tolerant: اگر سایت در دسترس نباشد یا ساختار تغییر کند، خطا را به شکل
    شفاف برمی‌گرداند و بقیهٔ خط تولید XGPedia متوقف نمی‌شود (null ≠ 0).
"""
from __future__ import annotations

import codecs
import json
import re
from pathlib import Path
from typing import Any

import httpx

from src.xgpedia.config import CURRENT_SEASON_START, RAW_PAYLOAD_DIR, canonical_team_name

PROVIDER = "understat"
BASE_URL = "https://understat.com"

# نگاشت نام‌های خاص Understat به نام canonical در team_mapping.json
UNDERSTAT_TEAM_ALIASES: dict[str, str] = {
    "Manchester United": "Manchester United",
    "Manchester City": "Manchester City",
    "Newcastle United": "Newcastle",
    "Wolverhampton Wanderers": "Wolverhampton",
    "Nottingham Forest": "Nottingham Forest",
    "Brighton": "Brighton",
    "Leeds": "Leeds",
    "Leeds United": "Leeds",
    "Hull": "Hull",
    "Hull City": "Hull",
    "Coventry": "Coventry",
    "Coventry City": "Coventry",
    "Ipswich": "Ipswich",
    "Ipswich Town": "Ipswich",
    "Tottenham": "Tottenham",
    "Sunderland": "Sunderland",
}

POS_FA: dict[str, str] = {
    "F": "مهاجم",
    "FW": "مهاجم",
    "M": "هافبک",
    "MF": "هافبک",
    "D": "مدافع",
    "DF": "مدافع",
    "GK": "دروازه‌بان",
    "S": "مهاجم",
}


def _decode_embedded_json(html_text: str, var_name: str) -> Any | None:
    """استخراج و پارس `var <var_name> = JSON.parse('...')` از HTML عمومی Understat."""
    pattern = rf"var\s+{re.escape(var_name)}\s*=\s*JSON\.parse\('([^']+)'\)"
    m = re.search(pattern, html_text)
    if not m:
        return None
    raw_escaped = m.group(1)
    decoded = codecs.decode(raw_escaped, "unicode_escape")
    return json.loads(decoded)


def _pos_to_fa(raw_pos: str) -> str:
    first = (raw_pos or "").split()[0].strip().upper()
    return POS_FA.get(first, "بازیکن هجومی")


def _norm_team(name: str) -> str:
    mapped = UNDERSTAT_TEAM_ALIASES.get(name.strip(), name.strip())
    return canonical_team_name(mapped)


def parse_league_key_players(players_data: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """انتخاب بهترین مهرهٔ کلیدی هر تیم از playersData بر اساس (xG + xA) در ۹۰ دقیقه.

    حداقل ۱۸۰ دقیقه بازی برای جلوگیری از نویز بازیکنان کم‌دقیقه.
    خروجی: `{canonical_team_name: {"name": ..., "pos": ..., "s1": ..., "s2": ...}}`
    """
    best_by_team: dict[str, tuple[float, dict[str, str]]] = {}
    for p in players_data:
        try:
            mins = float(p.get("time") or 0)
            if mins < 180:
                continue
            xg = float(p.get("xG") or 0)
            xa = float(p.get("xA") or 0)
            kp_total = float(p.get("key_passes") or 0)
            team_raw = str(p.get("team_title") or "").split(",")[0].strip()
            if not team_raw:
                continue
            team = _norm_team(team_raw)
            per90_factor = 90.0 / mins
            xgi_90 = (xg + xa) * per90_factor
            kp_90 = kp_total * per90_factor
            # امتیاز ترکیبی حجم مشارکت + نرخ per-90 برای انتخاب ستارهٔ اصلی تیم
            score = (xg + xa) * 0.65 + xgi_90 * 2.5
            cur = best_by_team.get(team)
            if cur is None or score > cur[0]:
                best_by_team[team] = (
                    score,
                    {
                        "name": str(p.get("player_name") or "").strip(),
                        "pos": _pos_to_fa(str(p.get("position") or "")),
                        "s1": f"{xgi_90:.2f} xG+xA",
                        "s2": f"{kp_90:.1f} پاس کلیدی",
                    },
                )
        except (TypeError, ValueError):
            continue
    return {team: info for team, (_, info) in best_by_team.items() if info["name"]}


def parse_league_team_ppda(teams_data: dict[str, Any]) -> dict[str, dict[str, float]]:
    """استخراج میانگین PPDA و پاس‌های عمقی (deep) هر تیم از teamsData برای تقویت رادار."""
    out: dict[str, dict[str, float]] = {}
    for _tid, tnode in (teams_data or {}).items():
        title = str(tnode.get("title") or "").strip()
        history = tnode.get("history") or []
        if not title or not history:
            continue
        ppda_vals: list[float] = []
        deep_vals: list[float] = []
        for h in history:
            ppda = h.get("ppda") or {}
            att = ppda.get("att")
            dfn = ppda.get("def")
            if att is not None and dfn and float(dfn) > 0:
                ppda_vals.append(float(att) / float(dfn))
            if h.get("deep") is not None:
                deep_vals.append(float(h["deep"]))
        entry: dict[str, float] = {}
        if ppda_vals:
            entry["ppda"] = round(sum(ppda_vals) / len(ppda_vals), 2)
        if deep_vals:
            entry["deep"] = round(sum(deep_vals) / len(deep_vals), 2)
        if entry:
            out[_norm_team(title)] = entry
    return out


def parse_match_shots(shots_data: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """تبدیل shotsData صفحهٔ یک بازی Understat به ساختار دقیق `shotList` و `insideBox` استودیو.

    فرمت هر شوت: `[x_0_100, y_0_100, xg, 'goal'|'sot'|'miss', player_name, minute]`
    """
    def _conv(items: list[dict[str, Any]]) -> tuple[list[list[Any]], int]:
        out: list[list[Any]] = []
        inside = 0
        for s in items:
            try:
                x = round(float(s["X"]) * 100.0, 1)
                y = round(float(s["Y"]) * 100.0, 1)
                xg = round(float(s["xG"]), 3)
                res = str(s.get("result") or "")
                stype = "goal" if res == "Goal" else ("sot" if res == "SavedShot" else "miss")
                player = str(s.get("player") or "").strip()
                minute = int(float(s.get("minute") or 0))
                out.append([x, y, xg, stype, player, minute])
                if x >= 83.0 and 21.0 <= y <= 79.0:
                    inside += 1
            except (KeyError, TypeError, ValueError):
                continue
        return out, inside

    h_list, h_in = _conv(shots_data.get("h") or [])
    a_list, a_in = _conv(shots_data.get("a") or [])
    return {
        "home_shots": h_list,
        "home_inside_box": h_in,
        "away_shots": a_list,
        "away_inside_box": a_in,
    }


class UnderstatProvider:
    """کلاینت سبک HTTP برای خواندن داده‌های عمومی رایگان Understat (لیگ برتر انگلیس)."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or (RAW_PAYLOAD_DIR / PROVIDER)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=20.0,
            follow_redirects=True,
        )

    def fetch_epl_league_data(self, season_start: int = CURRENT_SEASON_START) -> dict[str, Any]:
        """دریافت مهره‌های کلیدی + PPDA/Deep تمام ۲۰ تیم لیگ برتر از صفحهٔ فصل Understat."""
        resp = self._client.get(f"/league/EPL/{season_start}")
        if resp.status_code != 200:
            raise RuntimeError(f"Understat league page HTTP {resp.status_code}")
        html_text = resp.text
        players_raw = _decode_embedded_json(html_text, "playersData") or []
        teams_raw = _decode_embedded_json(html_text, "teamsData") or {}
        dates_raw = _decode_embedded_json(html_text, "datesData") or []

        key_players = parse_league_key_players(players_raw)
        team_metrics = parse_league_team_ppda(teams_raw)
        return {
            "key_players": key_players,
            "team_metrics": team_metrics,
            "matches_count": len(dates_raw),
        }

    def fetch_match_shots(self, understat_match_id: str | int) -> dict[str, Any]:
        """دریافت نقشه شوت و جریان xG یک بازی پایان‌یافته از صفحهٔ بازی در Understat."""
        resp = self._client.get(f"/match/{understat_match_id}")
        if resp.status_code != 200:
            raise RuntimeError(f"Understat match {understat_match_id} HTTP {resp.status_code}")
        shots_raw = _decode_embedded_json(resp.text, "shotsData")
        if not shots_raw:
            raise RuntimeError(f"shotsData not found in Understat match {understat_match_id}")
        return parse_match_shots(shots_raw)

    def close(self) -> None:
        self._client.close()
