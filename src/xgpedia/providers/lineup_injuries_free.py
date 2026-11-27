"""پرووایدر ۱۰۰٪ رایگان «کارت ترکیب احتمالی و غایبان» — بدون `requests`.

منابع زنده (Association Football / Soccer ONLY):
  - **FPL Official Bootstrap + Fixtures API** (`fetch_fpl_bootstrap`, `fetch_fpl_fixtures`):
    - بازی‌های پیش‌رو لیگ برتر (`finished == False`)
    - انتخاب هوشمند ترکیب احتمالی ۱۱ نفرهٔ هر تیم بر پایهٔ دقایق واقعی بازی و وضعیت آمادگی (`status`, `chance_of_playing_next_round`)
    - فهرست دقیق مصدومان، محرومان و بازیکنان مشکوک همراه با درصد شانس حضور واقعی (`0%`, `25%`, `50%`, `75%`)
    - محاسبهٔ شاخص آمادگی ترکیب (`availability_pct`) بر پایهٔ سهم دقایق بازیکنان در دسترس
  - **پریست‌های آماده (`config/lineup_injuries_presets.json`)**: فقط از دکمهٔ پریست‌ها.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from src.xgpedia.config import ROOT

log = logging.getLogger(__name__)

PRESETS_PATH = ROOT / "config" / "lineup_injuries_presets.json"
_CACHE_TTL_SEC = 600
_LI_CACHE: dict[str, Any] = {"ts": 0.0, "items": []}

_POS_FA = {1: "دروازه‌بان", 2: "مدافع", 3: "هافبک", 4: "مهاجم"}
_POS_EN = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
_CLUB_COLORS: dict[str, str] = {
    "ARS": "#EF0107", "AVL": "#A855F7", "BOU": "#DA291C", "BRE": "#E30613",
    "BHA": "#38BDF8", "CHE": "#38BDF8", "CRY": "#3B82F6", "EVE": "#38BDF8",
    "FUL": "#CBD5E1", "IPS": "#3B82F6", "LEI": "#3B82F6", "LIV": "#C8102E",
    "MCI": "#6CABDD", "MUN": "#DA291C", "NEW": "#E2E8F0", "NFO": "#E53233",
    "SOU": "#E62E45", "TOT": "#CBD5E1", "WHU": "#A855F7", "WOL": "#F59E0B",
    "LEE": "#F59E0B", "BUR": "#A855F7", "SUN": "#E62E45",
}


def load_lineup_injuries_presets(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or PRESETS_PATH
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return [dict(x) for x in data if isinstance(x, dict)]
    except Exception as e:
        log.warning("failed to load lineup_injuries_presets.json: %s", e)
        return []


def _team_fa(code: str, fallback: str) -> str:
    try:
        from src.xgpedia.providers.pl_badges_free import lookup_pl_club
        info = lookup_pl_club(fallback, tla_hint=code)
        if info and info[0]:
            return str(info[0])
    except Exception as _em_exc:
        from src.xgpedia.core.error_metrics import record_error as _rec_err
        _rec_err("provider.lineup_injuries", _em_exc)
    return fallback


def _player_fa(name_en: str) -> str:
    try:
        from src.xgpedia.providers.injury_free import transliterate_player_name_fa
        return transliterate_player_name_fa(name_en)
    except Exception:
        return name_en


def _status_fa(status: str, chance: int | None) -> str:
    st = (status or "").lower()
    if st == "s":
        return "محروم"
    if st == "i":
        return f"مصدوم ({chance}%)" if (chance is not None and chance > 0) else "مصدوم"
    if st == "u":
        return "غایب"
    if chance is not None and chance < 100:
        return f"مشکوک {chance}٪"
    return "مشکوک"


def _assign_pitch_coords(starters: list[dict[str, Any]], *, is_home: bool) -> list[dict[str, Any]]:
    """چیدمان تمیز مختصات (x, y) برای ۱۱ بازیکن در نیمهٔ زمین میزبان (بالا) یا میهمان (پایین)."""
    by_pos: dict[str, list[dict[str, Any]]] = {"GKP": [], "DEF": [], "MID": [], "FWD": []}
    for p in starters:
        by_pos.setdefault(p["pos"], []).append(p)

    # سطرهای عمودی برای میزبان (بالا -> وسط) و میهمان (پایین -> وسط)
    y_rows = {"GKP": 8, "DEF": 21, "MID": 35, "FWD": 46} if is_home else {"GKP": 92, "DEF": 79, "MID": 65, "FWD": 54}
    out: list[dict[str, Any]] = []
    for pos_key in ("GKP", "DEF", "MID", "FWD"):
        group = by_pos.get(pos_key) or []
        n = len(group)
        if n == 0:
            continue
        if n == 1:
            xs = [50]
        elif n == 2:
            xs = [34, 66]
        elif n == 3:
            xs = [20, 50, 80]
        elif n == 4:
            xs = [16, 39, 61, 84]
        else:
            step = 72.0 / max(1, n - 1)
            xs = [round(14 + i * step) for i in range(n)]
        for p, xv in zip(group, xs):
            item = dict(p)
            item["x"] = xv
            item["y"] = y_rows[pos_key]
            out.append(item)
    return out


def _build_team_lineup_and_absentees(
    team_obj: dict[str, Any],
    team_elements: list[dict[str, Any]],
    *,
    is_home: bool,
) -> dict[str, Any]:
    code = str(team_obj.get("short_name") or "PL").upper()[:3]
    name_en = str(team_obj.get("name") or code)
    name_fa = _team_fa(code, name_en)
    color = _CLUB_COLORS.get(code, "#E62E45" if is_home else "#38BDF8")

    parsed: list[dict[str, Any]] = []
    absentees: list[dict[str, Any]] = []
    for el in team_elements:
        if not isinstance(el, dict):
            continue
        pos_id = int(el.get("element_type") or 0)
        if pos_id not in (1, 2, 3, 4):
            continue
        mins = int(el.get("minutes") or 0)
        status = str(el.get("status") or "a").lower()
        ch_raw = el.get("chance_of_playing_next_round")
        chance = int(ch_raw) if ch_raw is not None else (100 if status == "a" else 0)
        web = str(el.get("web_name") or el.get("second_name") or "").strip()
        if not web:
            continue
        nm_fa = _player_fa(web)
        rec = {
            "name": nm_fa,
            "name_en": web,
            "pos": _POS_EN[pos_id],
            "pos_fa": _POS_FA[pos_id],
            "minutes": mins,
            "chance": chance,
            "status": status,
            "xgi": float(el.get("expected_goal_involvements") or 0.0),
        }
        parsed.append(rec)
        if status != "a" or chance < 100:
            absentees.append({
                "name": nm_fa,
                "pos_fa": _POS_FA[pos_id],
                "status_fa": _status_fa(status, chance),
                "chance": chance,
                "minutes": mins,
            })

    # انتخاب ترکیب احتمالی ۱۱ نفره از بازیکنان در دسترس (شانس >= ۵۰٪) بر اساس دقایق بازی
    avail = [p for p in parsed if p["chance"] >= 50]
    avail_by_pos = {
        k: sorted([p for p in avail if p["pos"] == k], key=lambda x: (x["minutes"], x["chance"]), reverse=True)
        for k in ("GKP", "DEF", "MID", "FWD")
    }
    gk = avail_by_pos["GKP"][:1]
    defs = avail_by_pos["DEF"][:4]
    mids = avail_by_pos["MID"][:4]
    fwds = avail_by_pos["FWD"][:2]

    # تنظیم نهایی به دقیقاً ۱۱ بازیکن با فرمیشن استاندارد (مثلاً 4-3-3 یا 4-4-2 یا 4-5-1)
    selected = gk + defs + mids + fwds
    if len(selected) > 11:
        # یک هافبک کمتر برای 4-3-3 اگر ۳ مهاجم خوب داریم، وگرنه ۴-۴-۲
        selected = gk + defs[:4] + mids[:3] + fwds[:3]
        if len(selected) > 11:
            selected = selected[:11]
    if len(selected) < 11:
        used = {p["name_en"] for p in selected}
        rest = sorted([p for p in avail if p["name_en"] not in used and p["pos"] != "GKP"], key=lambda x: x["minutes"], reverse=True)
        selected.extend(rest[: (11 - len(selected))])

    n_def = sum(1 for p in selected if p["pos"] == "DEF")
    n_mid = sum(1 for p in selected if p["pos"] == "MID")
    n_fwd = sum(1 for p in selected if p["pos"] == "FWD")
    formation = f"{n_def}-{n_mid}-{n_fwd}" if (n_def + n_mid + n_fwd) == 10 else "4-3-3"

    # شاخص آمادگی تیم بر پایهٔ سهم دقایق بازیکنان در دسترس از کل دقایق
    tot_mins = sum(p["minutes"] for p in parsed)
    av_mins = sum(p["minutes"] * (p["chance"] / 100.0) for p in parsed)
    avail_pct = round((av_mins / tot_mins) * 100) if tot_mins > 0 else 85
    avail_pct = max(45, min(100, avail_pct))

    absentees_sorted = sorted(absentees, key=lambda x: (x["chance"] == 0, x["minutes"]), reverse=True)[:6]
    return {
        "name": name_fa,
        "code": code,
        "color": color,
        "formation": formation,
        "availability_pct": avail_pct,
        "lineup": _assign_pitch_coords(selected, is_home=is_home),
        "absentees": absentees_sorted,
    }


def build_lineup_injuries_from_fpl(
    boot: dict[str, Any],
    fixtures: list[dict[str, Any]],
    *,
    max_matches: int = 10,
) -> list[dict[str, Any]]:
    """ساخت لیست زندهٔ کارت‌های ترکیب احتمالی و غایبان برای بازی‌های پیش‌رو لیگ برتر."""
    if not isinstance(boot, dict) or not isinstance(fixtures, list):
        return []
    teams_by_id = {int(t["id"]): t for t in (boot.get("teams") or []) if isinstance(t, dict) and t.get("id") is not None}
    els_by_team: dict[int, list[dict[str, Any]]] = {}
    for el in (boot.get("elements") or []):
        if isinstance(el, dict) and el.get("team") is not None:
            els_by_team.setdefault(int(el["team"]), []).append(el)

    upcoming = [f for f in fixtures if isinstance(f, dict) and not f.get("finished") and f.get("team_h") and f.get("team_a")]
    upcoming.sort(key=lambda x: str(x.get("kickoff_time") or "9999"))

    out: list[dict[str, Any]] = []
    for fx in upcoming[:max_matches]:
        th = teams_by_id.get(int(fx["team_h"]))
        ta = teams_by_id.get(int(fx["team_a"]))
        if not th or not ta:
            continue
        home_data = _build_team_lineup_and_absentees(th, els_by_team.get(int(fx["team_h"]), []), is_home=True)
        away_data = _build_team_lineup_and_absentees(ta, els_by_team.get(int(fx["team_a"]), []), is_home=False)
        if len(home_data["lineup"]) < 7 or len(away_data["lineup"]) < 7:
            continue

        # دوئل‌های کلیدی بر اساس ستاره‌های در دسترس دو تیم
        h_att = sorted([p for p in home_data["lineup"] if p["pos"] in ("FWD", "MID")], key=lambda x: x.get("xgi", 0), reverse=True)
        a_def = sorted([p for p in away_data["lineup"] if p["pos"] == "DEF"], key=lambda x: x.get("minutes", 0), reverse=True)
        a_att = sorted([p for p in away_data["lineup"] if p["pos"] in ("FWD", "MID")], key=lambda x: x.get("xgi", 0), reverse=True)
        h_def = sorted([p for p in home_data["lineup"] if p["pos"] == "DEF"], key=lambda x: x.get("minutes", 0), reverse=True)
        duels: list[dict[str, str]] = []
        if h_att and a_def:
            duels.append({"title": "خطر میزبان در برابر دفاع میهمان", "home_p": h_att[0]["name"], "away_p": a_def[0]["name"]})
        if a_att and h_def:
            duels.append({"title": "خطر میهمان در برابر دفاع میزبان", "home_p": h_def[0]["name"], "away_p": a_att[0]["name"]})
        if len(h_att) > 1 and len(a_att) > 1:
            duels.append({"title": "جنگ خلاقیت میانه میدان", "home_p": h_att[1]["name"], "away_p": a_att[1]["name"]})

        ev_gw = fx.get("event")
        rnd = f"هفته {ev_gw}" if ev_gw else "هفته پیش‌رو"
        ko = str(fx.get("kickoff_time") or "")[:16].replace("T", " ")
        verdict = (
            f"{home_data['name']} با آمادگی {home_data['availability_pct']}٪ ({len(home_data['absentees'])} غایب/مشکوک) "
            f"در برابر {away_data['name']} با آمادگی {away_data['availability_pct']}٪ ({len(away_data['absentees'])} غایب/مشکوک) صف‌آرایی می‌کند."
        )
        out.append({
            "id": f"live_li_{fx.get('id') or home_data['code'] + '_' + away_data['code']}",
            "is_live": True,
            "competition": "لیگ برتر انگلیس",
            "round": rnd,
            "kickoff_fa": ko or "بازی پیش‌رو",
            "source": "Opta FPL / XGPedia Tactical",
            "editorial_verdict": verdict,
            "home": home_data,
            "away": away_data,
            "key_duels": duels,
        })
    return out


def fetch_live_lineup_injuries_items(*, force_refresh: bool = False, max_matches: int = 10) -> list[dict[str, Any]]:
    now = time.time()
    if not force_refresh and _LI_CACHE["items"] and (now - _LI_CACHE["ts"]) < _CACHE_TTL_SEC:
        return [dict(x) for x in _LI_CACHE["items"]]
    try:
        from src.xgpedia.providers.fpl_free import fetch_fpl_bootstrap, fetch_fpl_fixtures
        boot = fetch_fpl_bootstrap(force_refresh=force_refresh)
        fixtures = fetch_fpl_fixtures(force_refresh=force_refresh)
        items = build_lineup_injuries_from_fpl(boot or {}, fixtures or [], max_matches=max_matches)
        if items:
            _LI_CACHE["ts"] = now
            _LI_CACHE["items"] = [dict(x) for x in items]
        return items
    except Exception as e:
        log.warning("fetch_live_lineup_injuries_items failed: %s", e)
        return []


def hydrate_lineup_injuries_item(item: dict[str, Any]) -> dict[str, Any]:
    return dict(item)


def list_all_lineup_injuries_items(*, include_live: bool = True, force_refresh: bool = False) -> dict[str, list[dict[str, Any]]]:
    presets = load_lineup_injuries_presets()
    live = fetch_live_lineup_injuries_items(force_refresh=force_refresh) if include_live else []
    return {"live": live, "presets": presets}
