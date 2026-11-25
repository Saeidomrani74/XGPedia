"""تأمین دادهٔ چندمنبعی و کاملاً رایگان برای کارت ماژولار «جدول گلزنان / کفش طلا» (Top Scorers Studio — D58).

منابع رایگان (بدون وابستگی به `requests`، منحصراً Association Football / Soccer):
  1. FPL Official Bootstrap (`fantasy.premierleague.com/api/bootstrap-static/`)
     — جدول زنده و واقعی گلزنان لیگ برتر انگلیس (گل، پنالتی، گل غیرپنالتی، Opta xG، دقایق بازی، گل/۹۰، عکس رسمی فصل جاری)
  2. Football-Data.org v4 (اختیاری با `FOOTBALL_DATA_API_KEY` در `.env`) — `/v4/competitions/{code}/scorers` برای لالیگا، سری آ، بوندسلیگا، لیگ یک و لیگ قهرمانان
  3. پریست‌های آماده (`config/top_scorers_presets.json`).

قانون `null ≠ 0`: اگر xG یا تعداد شوت برای لیگی در API موجود نباشد، عدد جعلی ساخته نمی‌شود و `None` می‌ماند.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any

from src.xgpedia.config import ROOT
from src.xgpedia.providers.player_profile_free import (
    FPL_BOOTSTRAP_URL,
    PL_PHOTO_URLS,
    _FPL_CLUBS,
    _POS_META,
    _download_image_data_uri,
    _http_get_json,
    _percentile,
)
from src.xgpedia.providers.pl_badges_free import get_pl_badge_data_uri
from src.xgpedia.providers.players_rating_free import _resolve_club_meta

PRESETS_PATH = ROOT / "config" / "top_scorers_presets.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

_LIVE_CACHE: dict[str, Any] = {"ts": 0.0, "items": []}
_CACHE_TTL_SEC = 900.0

_FD_LEAGUES: list[tuple[str, str, str]] = [
    ("CL", "لیگ قهرمانان اروپا", "CHAMPIONS LEAGUE"),
    ("PD", "لالیگا اسپانیا", "LALIGA"),
    ("SA", "سری آ ایتالیا", "SERIE A"),
    ("BL1", "بوندسلیگا آلمان", "BUNDESLIGA"),
    ("FL1", "لیگ یک فرانسه", "LIGUE 1"),
]


def load_top_scorers_presets() -> list[dict[str, Any]]:
    if not PRESETS_PATH.exists():
        return []
    try:
        data = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []






def _fetch_bbc_epl_penalties_and_shots() -> dict[str, dict[str, int]]:
    """استخراج دقیق تعداد پنالتی‌ها و شوت‌های کل بازیکنان لیگ برتر از صفحه عمومی BBC Sport Top Scorers."""
    import re as _re
    import unicodedata as _ud
    try:
        req = urllib.request.Request(
            "https://www.bbc.com/sport/football/premier-league/top-scorers",
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en-GB,en;q=0.9"},
        )
        with urllib.request.urlopen(req, timeout=7.0) as resp:
            html_txt = resp.read().decode("utf-8", errors="replace")
        # Extract embedded JSON state (__INITIAL_DATA__)
        m = _re.search(r'window\.__INITIAL_DATA__\s*=\s*"(.+?)";</script>', html_txt)
        raw_str = None
        if m:
            raw_str = m.group(1).encode("utf-8").decode("unicode_escape")
        else:
            m2 = _re.search(r'"topScorers":(\[.*?\])', html_txt)
            if m2:
                raw_str = m2.group(1)
        out: dict[str, dict[str, int]] = {}
        if raw_str:
            # Find player entries with name, goals, penalties, shots
            for pm in _re.finditer(r'"(?:fullName|shortName|name)"\s*:\s*"([^"]+)"[^{}]{0,400}?"goals"\s*:\s*(\d+)[^{}]{0,400}?"penalties"\s*:\s*(\d+)', raw_str):
                nm, g_s, p_s = pm.group(1), int(pm.group(2)), int(pm.group(3))
                sh_m = _re.search(r'"shotsTotal"\s*:\s*(\d+)|"shots"\s*:\s*(\d+)', raw_str[pm.start():pm.end()+250])
                sh = int(sh_m.group(1) or sh_m.group(2)) if sh_m else 0
                norm = "".join(c for c in _ud.normalize("NFKD", nm.lower().strip()) if not _ud.combining(c))
                if norm:
                    ent = {"goals": g_s, "pen": p_s, "shots": sh}
                    out[norm] = ent
                    parts = norm.split()
                    if len(parts) >= 2:
                        out[parts[-1]] = ent
        return out
    except Exception:
        return {}


def _fetch_understat_epl_player_stats(bootstrap: dict[str, Any] | None = None) -> dict[str, dict[str, int]]:
    """استخراج تعداد واقعی پنالتی (`goals - npg`) و شوت کل (`shots`) بازیکنان لیگ برتر از Understat (با تشخیص دقیق سال فصل از FPL)."""
    import re as _re
    import unicodedata as _ud
    from datetime import datetime, timezone

    years_to_try: list[int] = []
    if isinstance(bootstrap, dict):
        evs = bootstrap.get("events") or []
        if evs and isinstance(evs[0], dict):
            dl = str(evs[0].get("deadline_time") or "")
            if len(dl) >= 4 and dl[:4].isdigit():
                years_to_try.append(int(dl[:4]))
    now = datetime.now(timezone.utc)
    cur_yr = now.year if now.month >= 7 else now.year - 1
    for y in (cur_yr, cur_yr - 1, 2025, 2024):
        if y not in years_to_try:
            years_to_try.append(y)

    for season_yr in years_to_try[:3]:
        url = f"https://understat.com/league/EPL/{season_yr}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
            with urllib.request.urlopen(req, timeout=7.0) as resp:
                html_txt = resp.read().decode("utf-8", errors="replace")
            m = _re.search(r"playersData\s*=\s*JSON\.parse\('([^']+)'\)", html_txt)
            if not m:
                continue
            decoded = m.group(1).encode("utf-8").decode("unicode_escape")
            data = json.loads(decoded)
            out: dict[str, dict[str, int]] = {}
            for rec in (data if isinstance(data, list) else []):
                if not isinstance(rec, dict):
                    continue
                pname = str(rec.get("player_name") or "").strip().lower()
                norm = "".join(c for c in _ud.normalize("NFKD", pname) if not _ud.combining(c))
                if not norm:
                    continue
                g = int(rec.get("goals") or 0)
                npg = int(rec.get("npg") or 0)
                sh = int(rec.get("shots") or 0)
                pen = max(0, g - npg)
                entry = {"goals": g, "pen": pen, "shots": sh}
                out[norm] = entry
                parts = norm.split()
                if len(parts) >= 2:
                    out[parts[-1]] = entry
            if out:
                return out
        except Exception:
            continue
    return {}


def _match_understat_player(umap: dict[str, dict[str, int]], full_en: str, short_en: str) -> dict[str, int] | None:
    import unicodedata as _ud
    if not umap:
        return None
    for cand in (full_en, short_en):
        norm = "".join(c for c in _ud.normalize("NFKD", str(cand or "").lower().strip()) if not _ud.combining(c))
        if norm in umap:
            return umap[norm]
        parts = norm.split()
        if parts and parts[-1] in umap:
            return umap[parts[-1]]
    return None




def _fetch_fd_pl_penalties(api_key: str) -> dict[str, dict[str, int]]:
    """پشتیبان دقیق تعداد پنالتی گلزنان لیگ برتر از Football-Data.org (در صورت وجود کلید رایگان)."""
    import unicodedata as _ud
    if not api_key:
        return {}
    url = "https://api.football-data.org/v4/competitions/PL/scorers?limit=25"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "X-Auth-Token": api_key})
        with urllib.request.urlopen(req, timeout=7.0) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        out: dict[str, dict[str, int]] = {}
        for row in (payload.get("scorers") or []):
            if not isinstance(row, dict):
                continue
            pl = row.get("player") or {}
            nm = str(pl.get("name") or "").strip().lower()
            pen = row.get("penalties")
            if not nm or pen is None:
                continue
            norm = "".join(c for c in _ud.normalize("NFKD", nm) if not _ud.combining(c))
            ent = {"goals": int(row.get("goals") or 0), "pen": int(pen), "shots": 0}
            out[norm] = ent
            parts = norm.split()
            if len(parts) >= 2:
                out[parts[-1]] = ent
        return out
    except Exception:
        return {}


def _fetch_epl_penalties_and_shots_map(bootstrap: dict[str, Any] | None = None) -> dict[str, dict[str, int]]:
    """تجمیع چندمنبعی تعداد واقعی پنالتی و شوت بازیکنان لیگ برتر (Understat + BBC Sport + Football-Data.org)."""
    merged: dict[str, dict[str, int]] = {}
    # ۱) Understat (دقیق‌ترین منبع: goals - npg + shots)
    u_map = _fetch_understat_epl_player_stats(bootstrap)
    if u_map:
        merged.update(u_map)
    # ۲) BBC Sport Top Scorers (تکمیل یا پشتیبان بدون کلید)
    if len(merged) < 12:
        bbc_map = _fetch_bbc_epl_penalties_and_shots()
        for k, v in bbc_map.items():
            if k not in merged:
                merged[k] = v
            elif merged[k].get("shots", 0) == 0 and v.get("shots", 0) > 0:
                merged[k]["shots"] = v["shots"]
    # ۳) Football-Data.org PL (در صورت تنظیم کلید رایگان در .env)
    fd_key = os.environ.get("FOOTBALL_DATA_API_KEY", "").strip()
    if fd_key and len(merged) < 12:
        for k, v in _fetch_fd_pl_penalties(fd_key).items():
            if k not in merged:
                merged[k] = v
    return merged


def parse_fpl_top_scorers(bootstrap: dict[str, Any], *, top_n: int = 8, understat_map: dict[str, dict[str, int]] | None = None) -> dict[str, Any] | None:
    if not isinstance(bootstrap, dict):
        return None
    teams_by_id = {int(t["id"]): t for t in (bootstrap.get("teams") or []) if isinstance(t, dict) and t.get("id") is not None}
    elements = [e for e in (bootstrap.get("elements") or []) if isinstance(e, dict) and int(e.get("goals_scored") or 0) > 0]
    if not elements:
        return None

    elements.sort(
        key=lambda e: (int(e.get("goals_scored") or 0), int(e.get("assists") or 0), -int(e.get("minutes") or 9999)),
        reverse=True,
    )
    top = elements[:top_n]
    events = [ev for ev in (bootstrap.get("events") or []) if isinstance(ev, dict) and ev.get("is_current")]
    gw = int(events[0]["id"]) if events else 0

    xg_pool = [float(p.get("expected_goals") or 0) for p in elements]
    th_pool = [float(p.get("threat") or 0) for p in elements]
    cr_pool = [float(p.get("creativity") or 0) for p in elements]
    in_pool = [float(p.get("influence") or 0) for p in elements]
    bp_pool = [float(p.get("bps") or 0) for p in elements]

    players: list[dict[str, Any]] = []
    for el in top:
        tid = int(el.get("team") or 0)
        tobj = teams_by_id.get(tid) or {}
        t_raw = str(tobj.get("name") or "Club")
        club_fa, club_code, col, sec = _FPL_CLUBS.get(t_raw, (t_raw, str(tobj.get("short_name") or "CLB")[:3].upper(), "#38BDF8", "#FFFFFF"))
        pos_fa = _POS_META.get(int(el.get("element_type") or 4), ("مهاجم", "ST", ""))[0]
        goals = int(el.get("goals_scored") or 0)
        xg = round(float(el.get("expected_goals") or 0), 2)
        mins = max(1, int(el.get("minutes") or 0))
        pen_missed = int(el.get("penalties_missed") or 0)
        # FPL bootstrap does not expose exact penalties_scored directly; keep pen as None (null != 0)
        from src.xgpedia.providers.injury_free import transliterate_player_name_fa
        first_n = str(el.get("first_name") or "").strip()
        second_n = str(el.get("second_name") or "").strip()
        web_n = str(el.get("web_name") or "").strip()
        full_en = f"{first_n} {second_n}".strip() or web_n or "Player"
        # برای نام‌های چندکلمه‌ای (مانند بازیکنان برزیلی) از web_name کوتاه و معروف استفاده شود
        display_en = web_n if (len(full_en.split()) >= 3 and web_n) else full_en
        name_fa = transliterate_player_name_fa(display_en)
        short_fa = transliterate_player_name_fa(web_n or second_n or display_en)
        u_hit = _match_understat_player(understat_map or {}, full_en, web_n)
        real_pen = u_hit["pen"] if u_hit else None
        real_shots = u_hit["shots"] if (u_hit and u_hit["shots"] > 0) else None
        squad_num = el.get("squad_number")
        try:
            real_num = int(squad_num) if squad_num not in (None, "", 0, "0") else None
        except (TypeError, ValueError):
            real_num = None

        g90 = goals * 90.0 / mins
        p_g90 = _percentile(g90, [int(p.get("goals_scored") or 0) * 90.0 / max(1, int(p.get("minutes") or 1)) for p in elements])
        players.append({
            "fpl_id": int(el.get("id") or 0),
            "fpl_photo_code": str(el.get("code") or ""),
            "name": name_fa,
            "short": short_fa,
            "club": club_fa,
            "code": club_code,
            "logoUrl": get_pl_badge_data_uri(t_raw, tla_hint=club_code, badge_code=int(tobj.get("code") or 0) or None),
            "pos": pos_fa,
            "num": real_num,
            "color": col,
            "secondary": sec,
            "goals": goals,
            "pen": real_pen,
            "pen_missed": pen_missed,
            "xg": xg,
            "mins": mins,
            "shots": real_shots,
            "sot": None,
            "streak": 0,
            "radar": [
                p_g90,
                _percentile(xg, xg_pool),
                _percentile(float(el.get("threat") or 0), th_pool),
                _percentile(float(el.get("creativity") or 0), cr_pool),
                _percentile(float(el.get("influence") or 0), in_pool),
                _percentile(float(el.get("bps") or 0), bp_pool),
            ],
            "pace": [],
            "photoUrl": None,
        })

    leader = players[0]
    runner = players[1] if len(players) > 1 else None
    g90_l = leader["goals"] * 90.0 / max(1, leader["mins"])
    delta_l = leader["goals"] - (leader["xg"] or 0.0)
    insight = (
        f"{leader['name']} با {leader['goals']} گل در {leader['mins']} دقیقه (میانگین {g90_l:.2f} گل در ۹۰ دقیقه "
        f"و تفاضل {delta_l:+.1f} نسبت به امید گل) صدرنشین زنده کفش طلای لیگ برتر است."
    )
    if runner:
        insight += f" نزدیک‌ترین تعقیب‌کننده او {runner['name']} با {runner['goals']} گل است."

    return {
        "id": "live_fpl_pl",
        "is_preset": False,
        "competition": "لیگ برتر انگلیس",
        "round": f"هفته {gw} • جدول زنده گلزنان" if gw else "جدول زنده گلزنان لیگ برتر",
        "leagueEn": "PREMIER LEAGUE",
        "season": "26/27",
        "weekCode": f"W{gw}" if gw else "LIVE",
        "source": "Premier League / Opta FPL",
        "weeks": [],
        "paceInsight": insight,
        "players": players,
        "_hydrated": False,
    }


def _fetch_fd_scorers(code: str, fa_name: str, en_name: str, api_key: str) -> dict[str, Any] | None:
    url = f"https://api.football-data.org/v4/competitions/{code}/scorers?limit=8"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "X-Auth-Token": api_key})
    try:
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return None
    raw_scorers = payload.get("scorers") or []
    if not raw_scorers:
        return None

    players: list[dict[str, Any]] = []
    for row in raw_scorers[:8]:
        if not isinstance(row, dict):
            continue
        pl = row.get("player") or {}
        tm = row.get("team") or {}
        c_fa, c_code, col, sec = _resolve_club_meta(str(tm.get("name") or "Club"), str(tm.get("tla") or ""), "")
        goals = int(row.get("goals") or 0)
        pen = row.get("penalties")
        played = int(row.get("playedMatches") or 0)
        name = str(pl.get("name") or "Player")
        players.append({
            "name": name,
            "short": name.split()[-1] if name.split() else name,
            "club": c_fa,
            "code": c_code,
            "pos": str(pl.get("section") or "مهاجم"),
            "num": None,
            "color": col,
            "secondary": sec,
            "goals": goals,
            "pen": int(pen) if pen is not None else None,
            "xg": None,  # Football-Data.org does not provide xG (null != 0)
            "mins": played * 90 if played > 0 else None,
            "shots": None,
            "sot": None,
            "streak": 0,
            "radar": [],
            "pace": [],
            "photoUrl": None,
        })
    if not players:
        return None
    lead = players[0]
    return {
        "id": f"live_fd_{code.lower()}",
        "is_preset": False,
        "competition": fa_name,
        "round": f"جدول زنده گلزنان • {fa_name}",
        "leagueEn": en_name,
        "season": "26/27",
        "weekCode": "LIVE",
        "source": "Football-Data.org v4",
        "weeks": [],
        "paceInsight": f"{lead['name']} ({lead['club']}) با {lead['goals']} گل در صدر جدول گلزنان {fa_name} قرار دارد.",
        "players": players,
        "_hydrated": True,
    }


def fetch_live_top_scorers_items(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    now_ts = time.time()
    if not force_refresh and _LIVE_CACHE["items"] and (now_ts - _LIVE_CACHE["ts"]) < _CACHE_TTL_SEC:
        return list(_LIVE_CACHE["items"])

    items: list[dict[str, Any]] = []
    try:
        bootstrap = _http_get_json(FPL_BOOTSTRAP_URL, timeout=9.0)
        pen_map = _fetch_epl_penalties_and_shots_map(bootstrap)
        epl = parse_fpl_top_scorers(bootstrap, top_n=8, understat_map=pen_map)
        if epl:
            items.append(epl)
    except Exception:
        pass

    fd_key = os.environ.get("FOOTBALL_DATA_API_KEY", "").strip()
    if fd_key:
        for code, fa_name, en_name in _FD_LEAGUES:
            item = _fetch_fd_scorers(code, fa_name, en_name, fd_key)
            if item:
                items.append(item)

    # جدول گلزنان زنده بوندس‌لیگا از OpenLigaDB (رایگان و بدون نیاز به کلید — v0.36.0)
    if not any(it.get("id") == "live_fd_bl1" for it in items):
        try:
            from src.xgpedia.providers.open_football_hub import fetch_openligadb_bundesliga_top_scorers
            bl_sc = fetch_openligadb_bundesliga_top_scorers()
            if bl_sc:
                items.append(bl_sc)
        except Exception:
            pass

    _LIVE_CACHE["ts"] = now_ts
    _LIVE_CACHE["items"] = items
    return list(items)


def hydrate_top_scorers_item(item: dict[str, Any]) -> dict[str, Any]:
    """دریافت عکس رسمی فصل جاری برای ۳ نفر اول جدول گلزنان (تنبل)."""
    if not isinstance(item, dict) or item.get("is_preset") or item.get("_hydrated"):
        return item
    for pl in (item.get("players") or [])[:3]:
        pcode = str(pl.get("fpl_photo_code") or "")
        if pcode and not pl.get("photoUrl"):
            for tmpl in PL_PHOTO_URLS:
                uri = _download_image_data_uri(tmpl.format(code=pcode), timeout=5.0)
                if uri:
                    pl["photoUrl"] = uri
                    break
    item["_hydrated"] = True
    return item


def list_all_top_scorers_items(*, include_live: bool = True, force_refresh: bool = False) -> list[dict[str, Any]]:
    presets = load_top_scorers_presets()
    live = fetch_live_top_scorers_items(force_refresh=force_refresh) if include_live else []
    return live + presets
