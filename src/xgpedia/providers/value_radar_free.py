"""پرووایدر ۱۰۰٪ رایگان «رادار ارزش بازار و شکار نقل‌وانتقالات (+EV)» — بدون `requests`.

منابع زنده (Association Football / Soccer ONLY):
  - **FPL Official Bootstrap API** (`fetch_fpl_bootstrap`): قیمت بازار (`now_cost / 10`),
    دقایق بازی، گل، پاس گل، `xG`، `xA`، `xGI`، کلین‌شیت و درصد مالکیت برای همهٔ بازیکنان لیگ برتر انگلیس.
  - **محاسبهٔ شاخص `+EV` (ارزش در برابر قیمت)**:
    `ev_score = round((xGI_per_90 / max(price_m, 4.0)) * 100, 1)`
    که دقیقاً خروجی مورد انتظار تهاجمی به ازای هر میلیون پوند هزینه را می‌سنجد.
  - **پریست‌های آماده (`config/value_radar_presets.json`)**: فقط از دکمهٔ پریست‌ها (هرگز در لیست زنده مخلوط نمی‌شود).
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from src.xgpedia.config import ROOT

log = logging.getLogger(__name__)

PRESETS_PATH = ROOT / "config" / "value_radar_presets.json"
_CACHE_TTL_SEC = 600
_VR_CACHE: dict[str, Any] = {"ts": 0.0, "items": []}

_POS_MAP: dict[int, tuple[str, str]] = {
    1: ("GKP", "دروازه‌بان"),
    2: ("DEF", "مدافع"),
    3: ("MID", "هافبک"),
    4: ("FWD", "مهاجم"),
}

_CLUB_COLORS: dict[str, str] = {
    "ARS": "#EF0107",
    "AVL": "#A855F7",
    "BOU": "#DA291C",
    "BRE": "#E30613",
    "BHA": "#38BDF8",
    "CHE": "#38BDF8",
    "CRY": "#3B82F6",
    "EVE": "#38BDF8",
    "FUL": "#CBD5E1",
    "IPS": "#3B82F6",
    "LEI": "#3B82F6",
    "LIV": "#C8102E",
    "MCI": "#6CABDD",
    "MUN": "#DA291C",
    "NEW": "#E2E8F0",
    "NFO": "#E53233",
    "SOU": "#E62E45",
    "TOT": "#CBD5E1",
    "WHU": "#A855F7",
    "WOL": "#F59E0B",
    "LEE": "#F59E0B",
    "BUR": "#A855F7",
    "SUN": "#E62E45",
}


def load_value_radar_presets(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or PRESETS_PATH
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return [dict(x) for x in data if isinstance(x, dict)]
    except Exception as e:
        log.warning("failed to load value_radar_presets.json: %s", e)
        return []


def _tier_fa(ev_score: float, price: float) -> str:
    if ev_score >= 10.5 and price <= 7.5:
        return "شکار طلایی +EV"
    if ev_score >= 8.5:
        return "ارزش بالا"
    if price >= 10.0 and ev_score >= 6.5:
        return "ستاره ممتاز"
    if ev_score >= 6.5:
        return "متعادل"
    return "گران‌قیمت"


def _team_fa_name(short_code: str, fallback_en: str) -> str:
    try:
        from src.xgpedia.providers.pl_badges_free import lookup_pl_club
        info = lookup_pl_club(fallback_en, tla_hint=short_code)
        if info and info[0]:
            return str(info[0])
    except Exception:
        pass
    return fallback_en


def _player_fa_name(full_en: str) -> str:
    try:
        from src.xgpedia.providers.injury_free import transliterate_player_name_fa
        return transliterate_player_name_fa(full_en)
    except Exception:
        return full_en


def build_value_radar_editions_from_bootstrap(boot: dict[str, Any], *, min_minutes: int = 270) -> list[dict[str, Any]]:
    """استخراج ۵ نسخهٔ زنده از رادار ارزش بازار از دیتای واقعی FPL bootstrap."""
    if not isinstance(boot, dict):
        return []
    teams_by_id: dict[int, dict[str, Any]] = {
        int(t["id"]): t for t in (boot.get("teams") or []) if isinstance(t, dict) and t.get("id") is not None
    }
    raw_players: list[dict[str, Any]] = []
    for el in (boot.get("elements") or []):
        if not isinstance(el, dict):
            continue
        mins = int(el.get("minutes") or 0)
        if mins < min_minutes:
            continue
        pos_id = int(el.get("element_type") or 0)
        if pos_id not in (2, 3, 4):  # فقط بازیکنان میدانی (مدافع، هافبک، مهاجم)
            continue
        price = round(float(el.get("now_cost") or 0) / 10.0, 1)
        if price <= 0:
            continue
        xg = float(el.get("expected_goals") or 0.0)
        xa = float(el.get("expected_assists") or 0.0)
        xgi_raw = el.get("expected_goal_involvements")
        xgi = float(xgi_raw) if xgi_raw is not None else (xg + xa)
        if xgi <= 0.05 and pos_id in (3, 4):
            continue
        goals = int(el.get("goals_scored") or 0)
        assists = int(el.get("assists") or 0)
        cs = int(el.get("clean_sheets") or 0)
        own = float(el.get("selected_by_percent") or 0.0)

        xg90 = round(xg * 90.0 / mins, 2)
        xa90 = round(xa * 90.0 / mins, 2)
        xgi90 = round(xgi * 90.0 / mins, 2)
        # برای مدافعان، کلین‌شیت در ۹۰ دقیقه هم در شاخص ارزش لحاظ می‌شود
        cs_bonus = (cs * 90.0 / mins) * 0.45 if pos_id == 2 else 0.0
        ev_score = round(((xgi90 + cs_bonus) / max(price, 4.0)) * 100.0, 1)
        delta = round((goals + assists) - xgi, 2)

        t_obj = teams_by_id.get(int(el.get("team") or 0), {})
        t_code = str(t_obj.get("short_name") or "PL").upper()[:3]
        t_en = str(t_obj.get("name") or t_code)
        t_fa = _team_fa_name(t_code, t_en)

        first = str(el.get("first_name") or "").strip()
        second = str(el.get("second_name") or "").strip()
        web = str(el.get("web_name") or "").strip()
        full_en = f"{first} {second}".strip() or web
        pos_en, pos_fa = _POS_MAP.get(pos_id, ("MID", "هافبک"))

        raw_players.append({
            "name": _player_fa_name(web or full_en),
            "name_en": full_en,
            "club": t_fa,
            "club_code": t_code,
            "pos": pos_en,
            "pos_fa": pos_fa,
            "price": price,
            "minutes": mins,
            "goals": goals,
            "assists": assists,
            "clean_sheets": cs,
            "xg": round(xg, 2),
            "xa": round(xa, 2),
            "xgi": round(xgi, 2),
            "xg90": xg90,
            "xa90": xa90,
            "xgi90": xgi90,
            "ev_score": ev_score,
            "ev_tier": _tier_fa(ev_score, price),
            "delta": delta,
            "ownership": round(own, 1),
            "color": _CLUB_COLORS.get(t_code, "#E62E45"),
        })

    if len(raw_players) < 4:
        return []

    slices: list[tuple[str, str, str, list[dict[str, Any]]]] = [
        (
            "live_vr_pl_all",
            "شکارهای طلایی کل لیگ برتر (+EV)",
            "کل بازیکنان هجومی",
            [p for p in raw_players if p["pos"] in ("MID", "FWD")],
        ),
        (
            "live_vr_pl_fwd",
            "مهاجمان زیرقیمت بازار (FWD +EV)",
            "مهاجمان لیگ برتر",
            [p for p in raw_players if p["pos"] == "FWD"],
        ),
        (
            "live_vr_pl_mid",
            "هافبک‌های خلاق و ارزشمند (MID +EV)",
            "هافبک‌های لیگ برتر",
            [p for p in raw_players if p["pos"] == "MID"],
        ),
        (
            "live_vr_pl_def",
            "مدافعان هجومی و کلین‌شیت‌ساز (DEF +EV)",
            "مدافعان لیگ برتر",
            [p for p in raw_players if p["pos"] == "DEF"],
        ),
        (
            "live_vr_pl_diff",
            "جواهرهای کم‌مالکیت لیگ برتر (<۱۰٪)",
            "کم‌مالکیت (<۱۰٪)",
            [p for p in raw_players if p["pos"] in ("MID", "FWD") and p["ownership"] < 10.0],
        ),
    ]

    editions: list[dict[str, Any]] = []
    all_outfield = [p for p in raw_players if p["pos"] in ("MID", "FWD")]
    global_premium = max(all_outfield, key=lambda x: (x["price"], x["xgi90"])) if all_outfield else raw_players[0]

    for eid, title_fa, slice_fa, pool in slices:
        if len(pool) < 4:
            continue
        ranked = sorted(pool, key=lambda x: (x["ev_score"], x["xgi90"]), reverse=True)
        top_bargains = ranked[:8]
        # گران‌ترین ستارهٔ همان برش (یا کل لیگ) برای اسلاید مقایسه
        prem = max(pool, key=lambda x: (x["price"], x["xgi90"]))
        if prem["name_en"] == top_bargains[0]["name_en"]:
            prem = global_premium
        # برای نمودار Scatter، ستارهٔ گران‌قیمت هم در لیست باشد تا تضاد قیمت/عملکرد کاملاً دیده شود
        scatter_players = list(top_bargains)
        if all(p["name_en"] != prem["name_en"] for p in scatter_players):
            scatter_players.append(prem)

        avg_p = round(sum(p["price"] for p in pool) / len(pool), 1)
        avg_x = round(sum(p["xgi90"] for p in pool) / len(pool), 2)
        best = top_bargains[0]
        verdict = (
            f"{best['name']} ({best['club']}) با قیمت £{best['price']:.1f}M و خروجی {best['xgi90']:.2f} xGI/90، "
            f"با شاخص ارزش {best['ev_score']:.1f} بهترین شکار این بخش نسبت به میانگین لیگ (£{avg_p:.1f}M) است."
        )
        editions.append({
            "id": eid,
            "is_live": True,
            "title": title_fa,
            "subtitle": "مقایسهٔ خروجی واقعی در ۹۰ دقیقه با ارزش بازار (FPL / Opta)",
            "competition": "لیگ برتر انگلیس",
            "season": "فصل جاری",
            "slice_label": slice_fa,
            "source": "Opta FPL / XGPedia Scout",
            "avg_price": avg_p,
            "avg_xgi90": avg_x,
            "editorial_verdict": verdict,
            "players": scatter_players,
            "premium_benchmark": prem,
        })
    return editions


def fetch_live_value_radar_items(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    """دریافت لیست زندهٔ ۵ برش رادار ارزش بازار از FPL (با کش ۱۰ دقیقه‌ای)."""
    now = time.time()
    if not force_refresh and _VR_CACHE["items"] and (now - _VR_CACHE["ts"]) < _CACHE_TTL_SEC:
        return [dict(x) for x in _VR_CACHE["items"]]
    try:
        from src.xgpedia.providers.fpl_free import fetch_fpl_bootstrap
        boot = fetch_fpl_bootstrap(force_refresh=force_refresh)
        if not isinstance(boot, dict):
            return []
        editions = build_value_radar_editions_from_bootstrap(boot)
        if editions:
            _VR_CACHE["ts"] = now
            _VR_CACHE["items"] = [dict(x) for x in editions]
        return editions
    except Exception as e:
        log.warning("fetch_live_value_radar_items failed: %s", e)
        return []


def hydrate_value_radar_item(item: dict[str, Any]) -> dict[str, Any]:
    """تکمیل نهایی آیتم رادار ارزش بازار پیش از رندر آفلاین."""
    return dict(item)


def list_all_value_radar_items(*, include_live: bool = True, force_refresh: bool = False) -> dict[str, list[dict[str, Any]]]:
    presets = load_value_radar_presets()
    live = fetch_live_value_radar_items(force_refresh=force_refresh) if include_live else []
    return {"live": live, "presets": presets}
