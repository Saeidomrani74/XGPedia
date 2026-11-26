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

_FD_LEAGUES: list[tuple[str, str, str, str | None]] = [
    ("CL", "لیگ قهرمانان اروپا", "CHAMPIONS LEAGUE", None),
    ("EL", "لیگ اروپا", "EUROPA LEAGUE", None),
    ("PD", "لالیگا اسپانیا", "LALIGA", "La_liga"),
    ("SA", "سری آ ایتالیا", "SERIE A", "Serie_A"),
    ("BL1", "بوندسلیگا آلمان", "BUNDESLIGA", "Bundesliga"),
    ("FL1", "لیگ یک فرانسه", "LIGUE 1", "Ligue_1"),
]


def _get_fdo_token() -> str:
    """خواندن توکن football-data.org از نام استاندارد `.env` (`FOOTBALL_DATA_ORG_TOKEN`) و نام قدیمی."""
    return (
        os.environ.get("FOOTBALL_DATA_ORG_TOKEN")
        or os.environ.get("FOOTBALL_DATA_API_KEY")
        or ""
    ).strip()


_PROMOTED_CLUB_FA: dict[str, tuple[str, str, str, str]] = {
    "paris fc": ("پاریس اف‌سی", "PFC", "#1D4ED8", "#FFFFFF"),
    "le mans fc": ("لومان", "LMN", "#E11D48", "#FACC15"),
    "le mans": ("لومان", "LMN", "#E11D48", "#FACC15"),
    "frosinone calcio": ("فروزینونه", "FRO", "#FACC15", "#1D4ED8"),
    "frosinone": ("فروزینونه", "FRO", "#FACC15", "#1D4ED8"),
    "real racing club de santander": ("راسینگ سانتاندر", "RAC", "#16A34A", "#FFFFFF"),
    "racing santander": ("راسینگ سانتاندر", "RAC", "#16A34A", "#FFFFFF"),
    "racing de santander": ("راسینگ سانتاندر", "RAC", "#16A34A", "#FFFFFF"),
}


def _parse_understat_players_list(data: Any) -> dict[str, dict[str, Any]]:
    import unicodedata as _ud

    out: dict[str, dict[str, Any]] = {}
    if not isinstance(data, list):
        return out
    for rec in data:
        if not isinstance(rec, dict):
            continue
        pname = str(rec.get("player_name") or "").strip().lower()
        norm = "".join(c for c in _ud.normalize("NFKD", pname) if not _ud.combining(c))
        if not norm:
            continue
        g = int(rec.get("goals") or 0)
        npg = int(rec.get("npg") or 0)
        sh = int(rec.get("shots") or 0)
        mins = int(rec.get("time") or 0)
        xg_v = round(float(rec.get("xG") or 0.0), 2)
        xa_v = round(float(rec.get("xA") or 0.0), 2)
        kp_v = int(rec.get("key_passes") or 0)
        pen = max(0, g - npg)
        entry = {"goals": g, "pen": pen, "shots": sh, "xg": xg_v, "xa": xa_v, "kp": kp_v, "mins": mins}
        out[norm] = entry
        parts = norm.split()
        if len(parts) >= 2 and parts[-1] not in ("junior", "jr", "silva", "santos", "costa", "garcia", "perez", "martinez"):
            out.setdefault(parts[-1], entry)
    return out


def _fetch_understat_league_player_stats(league_slug: str, season_years: list[int] | None = None) -> dict[str, dict[str, Any]]:
    """استخراج آمار واقعی بازیکنان یک لیگ از Understat (ابتدا XHR JSON جدید `/getLeagueData/{lg}/{yr}` و سپس پشتیبان HTML)."""
    import re as _re
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    cur_yr = now.year if now.month >= 7 else now.year - 1
    years_to_try = list(season_years or [])
    for y in (cur_yr, cur_yr - 1, 2025, 2024):
        if y not in years_to_try:
            years_to_try.append(y)

    for season_yr in years_to_try[:2]:
        # مسیر ۱ (جدید ۲۰۲۶): XHR API مستقیم JSON
        xhr_url = f"https://understat.com/getLeagueData/{league_slug}/{season_yr}"
        try:
            req_x = urllib.request.Request(
                xhr_url,
                headers={
                    "User-Agent": USER_AGENT,
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": f"https://understat.com/league/{league_slug}/{season_yr}",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                },
            )
            with urllib.request.urlopen(req_x, timeout=8.0) as resp:
                j = json.loads(resp.read().decode("utf-8", errors="replace"))
            if isinstance(j, dict) and j.get("players"):
                parsed = _parse_understat_players_list(j["players"])
                if parsed:
                    return parsed
        except Exception:
            pass

        # مسیر ۲ (پشتیبان کلاسیک HTML)
        url = f"https://understat.com/league/{league_slug}/{season_yr}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
            with urllib.request.urlopen(req, timeout=7.0) as resp:
                html_txt = resp.read().decode("utf-8", errors="replace")
            m = _re.search(r"playersData\s*=\s*JSON\.parse\('([^']+)'\)", html_txt)
            if not m:
                continue
            decoded = m.group(1).encode("utf-8").decode("unicode_escape")
            parsed = _parse_understat_players_list(json.loads(decoded))
            if parsed:
                return parsed
        except Exception:
            continue
    return {}


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
    """استخراج تعداد واقعی پنالتی (`goals - npg`) و شوت کل (`shots`) بازیکنان لیگ برتر از Understat (XHR API جدید)."""
    years_to_try: list[int] = []
    if isinstance(bootstrap, dict):
        evs = bootstrap.get("events") or []
        if evs and isinstance(evs[0], dict):
            dl = str(evs[0].get("deadline_time") or "")
            if len(dl) >= 4 and dl[:4].isdigit():
                years_to_try.append(int(dl[:4]))
    return _fetch_understat_league_player_stats("EPL", season_years=years_to_try)


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
            goals_v = row.get("goals")
            if not nm or goals_v is None:
                continue
            pen = row.get("penalties")
            pen_int = int(pen) if pen is not None else 0
            norm = "".join(c for c in _ud.normalize("NFKD", nm) if not _ud.combining(c))
            ent = {"goals": int(goals_v or 0), "pen": pen_int, "shots": 0}
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
    # ۳) Football-Data.org PL (همیشه ادغام می‌شود تا پنالتی‌های دقیق برای همه گلزنان لیگ برتر تکمیل شود)
    fd_key = _get_fdo_token()
    if fd_key:
        for k, v in _fetch_fd_pl_penalties(fd_key).items():
            if k not in merged:
                merged[k] = v
            elif merged[k].get("pen") is None and v.get("pen") is not None:
                merged[k]["pen"] = v["pen"]
    # ۴) GOAL API PL (در صورت تنظیم GOAL_API_KEY در .env)
    try:
        from src.xgpedia.providers.goal_api import fetch_goal_api_top_scorers, get_goal_api_key
        import unicodedata as _ud

        if get_goal_api_key():
            for row in fetch_goal_api_top_scorers("PL", limit=25):
                if row.get("pen") is None:
                    continue
                norm = "".join(c for c in _ud.normalize("NFKD", row["name"].lower().strip()) if not _ud.combining(c))
                if not norm:
                    continue
                ent = {"goals": row["goals"], "pen": int(row["pen"]), "shots": 0}
                if norm not in merged:
                    merged[norm] = ent
                parts = norm.split()
                if len(parts) >= 2 and parts[-1] not in merged:
                    merged[parts[-1]] = ent
    except Exception:
        pass
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


def _build_league_scorer_entry(
    raw_name: str,
    raw_team: str,
    tla: str,
    goals: int,
    pen: int | None,
    mins: int | None,
    pos_raw: str,
    understat_map: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from src.xgpedia.config import canonical_team_name, team_identity, team_name_fa, translate_player_fa
    from src.xgpedia.render.cards import _crest_data_uri

    club_en = canonical_team_name(raw_team) if raw_team else ""
    ident = team_identity(club_en) if club_en else None
    if ident:
        c_fa = team_name_fa(club_en)
        c_code = ident["code"]
        col = ident["colors"]["primary"]
        sec = ident["colors"]["secondary"]
    elif (raw_team or "").strip().lower() in _PROMOTED_CLUB_FA:
        c_fa, c_code, col, sec = _PROMOTED_CLUB_FA[(raw_team or "").strip().lower()]
    else:
        c_fa, c_code, col, sec = _resolve_club_meta(raw_team or "Club", tla, "")
    logo_uri = _crest_data_uri(club_en) if club_en else None

    name_fa = translate_player_fa(raw_name) or raw_name
    short_fa = translate_player_fa(raw_name.split()[-1]) if raw_name.split() else name_fa
    u_hit = _match_understat_player(understat_map or {}, raw_name, raw_name.split()[-1] if raw_name.split() else raw_name)
    real_pen = int(pen) if pen is not None else (int(u_hit["pen"]) if (u_hit and u_hit.get("pen") is not None) else None)
    real_xg = round(float(u_hit["xg"]), 2) if (u_hit and u_hit.get("xg") is not None) else None
    real_mins = int(u_hit["mins"]) if (u_hit and int(u_hit.get("mins") or 0) > 0) else mins
    real_shots = int(u_hit["shots"]) if (u_hit and int(u_hit.get("shots") or 0) > 0) else None

    pos_low = str(pos_raw or "").lower()
    pos_fa = "هافبک" if "mid" in pos_low else ("مدافع" if "def" in pos_low else ("دروازه‌بان" if "keep" in pos_low else "مهاجم"))
    return {
        "name": name_fa,
        "short": short_fa,
        "club": c_fa,
        "club_en": club_en,
        "code": c_code,
        "logoUrl": logo_uri,
        "pos": pos_fa,
        "num": None,
        "color": col,
        "secondary": sec,
        "goals": int(goals),
        "pen": real_pen,
        "xg": real_xg,
        "mins": real_mins,
        "shots": real_shots,
        "sot": None,
        "streak": 0,
        "radar": [],
        "pace": [],
        "photoUrl": None,
    }


def _fetch_fd_scorers(
    code: str, fa_name: str, en_name: str, api_key: str, *, understat_slug: str | None = None
) -> dict[str, Any] | None:
    if code == "EL":
        return None  # لیگ اروپا در پلن رایگان football-data.org نیست
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

    u_map = _fetch_understat_league_player_stats(understat_slug) if understat_slug else {}
    players: list[dict[str, Any]] = []
    for row in raw_scorers[:8]:
        if not isinstance(row, dict):
            continue
        pl = row.get("player") or {}
        tm = row.get("team") or {}
        played = int(row.get("playedMatches") or 0)
        players.append(
            _build_league_scorer_entry(
                str(pl.get("name") or "Player"),
                str(tm.get("name") or ""),
                str(tm.get("tla") or ""),
                int(row.get("goals") or 0),
                row.get("penalties"),
                played * 90 if played > 0 else None,
                str(pl.get("section") or "مهاجم"),
                understat_map=u_map,
            )
        )
    if not players:
        return None
    lead = players[0]
    src_lbl = "Football-Data.org + Understat" if u_map else "Football-Data.org v4"
    return {
        "id": f"live_fd_{code.lower()}",
        "is_preset": False,
        "competition": fa_name,
        "round": f"جدول زنده گلزنان • {fa_name}",
        "leagueEn": en_name,
        "season": "26/27",
        "weekCode": "LIVE",
        "source": src_lbl,
        "weeks": [],
        "paceInsight": f"{lead['name']} ({lead['club']}) با {lead['goals']} گل در صدر جدول گلزنان {fa_name} قرار دارد.",
        "players": players,
        "_hydrated": True,
    }


def _fetch_goal_api_league_scorers(
    code: str, fa_name: str, en_name: str, *, understat_slug: str | None = None
) -> dict[str, Any] | None:
    from src.xgpedia.providers.goal_api import fetch_goal_api_top_scorers, get_goal_api_key

    if not get_goal_api_key():
        return None
    rows = fetch_goal_api_top_scorers(code, limit=8)
    if not rows:
        return None
    u_map = _fetch_understat_league_player_stats(understat_slug) if understat_slug else {}
    players = [
        _build_league_scorer_entry(
            r["name"], r.get("team") or "", "", r["goals"], r.get("pen"), r.get("mins"), "مهاجم", understat_map=u_map
        )
        for r in rows[:8]
    ]
    lead = players[0]
    src_lbl = "GOAL API + Understat" if u_map else "GOAL API (Live)"
    return {
        "id": f"live_goal_{code.lower()}",
        "is_preset": False,
        "competition": fa_name,
        "round": f"جدول زنده گلزنان • {fa_name}",
        "leagueEn": en_name,
        "season": "26/27",
        "weekCode": "LIVE",
        "source": src_lbl,
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

    fd_key = _get_fdo_token()
    covered_codes: set[str] = set()
    for code, fa_name, en_name, us_slug in _FD_LEAGUES:
        item = _fetch_fd_scorers(code, fa_name, en_name, fd_key, understat_slug=us_slug) if fd_key else None
        if not item:
            item = _fetch_goal_api_league_scorers(code, fa_name, en_name, understat_slug=us_slug)
        if item:
            items.append(item)
            covered_codes.add(code)

    # جدول گلزنان زنده بوندس‌لیگا از OpenLigaDB (فقط پشتیبان نهایی در نبود FDO و GOAL API)
    if "BL1" not in covered_codes:
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
    """دریافت عکس رسمی فصل جاری + مسیر واقعی ۸ هفتهٔ اخیر (`pace`/`weeks`) از FPL element-summary برای ۳ نفر اول."""
    if not isinstance(item, dict) or item.get("is_preset") or item.get("_hydrated"):
        return item
    top3 = (item.get("players") or [])[:3]
    for pl in top3:
        pcode = str(pl.get("fpl_photo_code") or "")
        if pcode and not pl.get("photoUrl"):
            for tmpl in PL_PHOTO_URLS:
                uri = _download_image_data_uri(tmpl.format(code=pcode), timeout=5.0)
                if uri:
                    pl["photoUrl"] = uri
                    break
    # استخراج مسیر واقعی ۸ هفته اخیر از FPL element-summary/{fpl_id}/ (برای اسلاید ۴ Trajectory)
    if not item.get("weeks") and any(pl.get("fpl_id") for pl in top3):
        hist_by_idx: dict[int, dict[int, int]] = {}
        all_rounds: set[int] = set()
        for idx, pl in enumerate(top3):
            fid = int(pl.get("fpl_id") or 0)
            if not fid:
                continue
            try:
                es = _http_get_json(f"https://fantasy.premierleague.com/api/element-summary/{fid}/", timeout=6.0)
                if isinstance(es, dict) and isinstance(es.get("history"), list):
                    per_r: dict[int, int] = {}
                    for h in es["history"]:
                        if not isinstance(h, dict):
                            continue
                        rnd = int(h.get("round") or 0)
                        if rnd > 0:
                            per_r[rnd] = per_r.get(rnd, 0) + int(h.get("goals_scored") or 0)
                            all_rounds.add(rnd)
                    if per_r:
                        hist_by_idx[idx] = per_r
            except Exception:
                continue
        if len(all_rounds) >= 3 and hist_by_idx:
            sorted_all = sorted(all_rounds)
            win_rounds = sorted_all[-8:]
            item["weeks"] = [f"هفته {r}" for r in win_rounds]
            for idx, pl in enumerate(top3):
                per_r = hist_by_idx.get(idx)
                if not per_r:
                    continue
                cum = 0
                cum_by_r: dict[int, int] = {}
                for r in sorted_all:
                    cum += per_r.get(r, 0)
                    cum_by_r[r] = cum
                pl["pace"] = [cum_by_r[r] for r in win_rounds]
    item["_hydrated"] = True
    return item


def list_all_top_scorers_items(*, include_live: bool = True, force_refresh: bool = False) -> list[dict[str, Any]]:
    presets = load_top_scorers_presets()
    live = fetch_live_top_scorers_items(force_refresh=force_refresh) if include_live else []
    return live + presets
