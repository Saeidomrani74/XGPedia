"""انتخابگر زنده و هوشمند لیگ برتر انگلیس (لیگ ← تیم ← بازیکن/تیم) برای کارت‌های ماژولار XGPedia.

منبع ۱۰۰٪ رایگان و بدون کلید API:
  - Premier League Official FPL API (`fantasy.premierleague.com/api/bootstrap-static/` + `fixtures/`)
  - منحصراً Association Football / Soccer، بدون وابستگی به `requests`، رعایت کامل `null ≠ 0`.

کاربردها:
  1. لیست ۲۰ تیم فعلی لیگ برتر انگلیس (با رتبه و امتیاز زنده)
  2. لیست بازیکنان هر تیم (مرتب‌شده بر اساس دقایق بازی و امتیاز فصل)
  3. ساخت آنی و واقعی کارت‌های:
     - `h2h_teams` (تقابل مستقیم دو تیم دلخواه + پیشنهاد هوشمند تیم‌های همسان کنونی)
     - `h2h_players` (مقایسه دو بازیکن دلخواه)
     - `player_fc27` (کارت FC27 بازیکن دلخواه)
     - `player_profile` (پروفایل آماری بازیکن دلخواه)
"""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.xgpedia.providers.players_rating_free import _resolve_club_meta

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
FPL_BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_FIXTURES_URL = "https://fantasy.premierleague.com/api/fixtures/"

_CACHE: dict[str, Any] = {"ts": 0.0, "boot": None, "fixtures": None}
_CACHE_TTL = 300.0

_POS_CODE = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
_POS_FA = {1: "دروازه‌بان", 2: "مدافع", 3: "هافبک", 4: "مهاجم"}


def _http_get_json(url: str, timeout: float = 9.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def fetch_pl_bootstrap_and_fixtures(*, force_refresh: bool = False) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    now = time.time()
    if not force_refresh and _CACHE["boot"] and (now - _CACHE["ts"]) < _CACHE_TTL:
        return _CACHE["boot"], list(_CACHE["fixtures"] or [])
    try:
        boot = _http_get_json(FPL_BOOTSTRAP_URL, timeout=9.0)
        fixtures = _http_get_json(FPL_FIXTURES_URL, timeout=9.0)
        if isinstance(boot, dict):
            _CACHE["ts"] = now
            _CACHE["boot"] = boot
            _CACHE["fixtures"] = fixtures if isinstance(fixtures, list) else []
            return boot, list(_CACHE["fixtures"])
    except Exception:
        pass
    return _CACHE["boot"], list(_CACHE["fixtures"] or [])


def _compute_pl_team_stats(boot: dict[str, Any], fixtures: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    stats: dict[int, dict[str, Any]] = {}
    for tobj in boot.get("teams") or []:
        if not isinstance(tobj, dict) or tobj.get("id") is None:
            continue
        tid = int(tobj["id"])
        raw_name = str(tobj.get("name") or "")
        short_name = str(tobj.get("short_name") or "")
        fa, code, col, sec = _resolve_club_meta(raw_name, short_name)
        stats[tid] = {
            "id": tid,
            "raw_name": raw_name,
            "name": fa,
            "code": code,
            "color": col,
            "color2": sec,
            "mp": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "pts": 0, "cs": 0,
            "results": [],
        }

    for fx in fixtures:
        if not isinstance(fx, dict) or not fx.get("finished"):
            continue
        ht, at = fx.get("team_h"), fx.get("team_a")
        hs, as_ = fx.get("team_h_score"), fx.get("team_a_score")
        if ht not in stats or at not in stats or hs is None or as_ is None:
            continue
        hs, as_ = int(hs), int(as_)
        ko = str(fx.get("kickoff_time") or "")
        sh, sa = stats[int(ht)], stats[int(at)]
        sh["mp"] += 1; sa["mp"] += 1
        sh["gf"] += hs; sh["ga"] += as_
        sa["gf"] += as_; sa["ga"] += hs
        if as_ == 0:
            sh["cs"] += 1
        if hs == 0:
            sa["cs"] += 1
        if hs > as_:
            sh["w"] += 1; sh["pts"] += 3; sh["results"].append((ko, "W"))
            sa["l"] += 1; sa["results"].append((ko, "L"))
        elif hs < as_:
            sa["w"] += 1; sa["pts"] += 3; sa["results"].append((ko, "W"))
            sh["l"] += 1; sh["results"].append((ko, "L"))
        else:
            sh["d"] += 1; sh["pts"] += 1; sh["results"].append((ko, "D"))
            sa["d"] += 1; sa["pts"] += 1; sa["results"].append((ko, "D"))

    ranked = sorted(stats.values(), key=lambda t: (t["pts"], t["gf"] - t["ga"], t["gf"], t["name"]), reverse=True)
    for idx, rec in enumerate(ranked, 1):
        rec["rank"] = idx
        rec["results"].sort(key=lambda x: x[0])
        rec["form"] = [r for _, r in rec["results"][-5:]]
    return stats


def list_pl_teams(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    """لیست ۲۰ تیم لیگ برتر انگلیس مرتب‌شده بر اساس رتبه زنده جدول."""
    boot, fixtures = fetch_pl_bootstrap_and_fixtures(force_refresh=force_refresh)
    if not boot:
        return []
    stats = _compute_pl_team_stats(boot, fixtures)
    return sorted(stats.values(), key=lambda t: t["rank"])


def list_pl_team_players(team_id: int, *, force_refresh: bool = False) -> list[dict[str, Any]]:
    """لیست بازیکنان یک تیم لیگ برتر انگلیس مرتب‌شده بر اساس دقایق بازی و امتیاز فصل."""
    boot, _ = fetch_pl_bootstrap_and_fixtures(force_refresh=force_refresh)
    if not boot:
        return []
    out: list[dict[str, Any]] = []
    for el in boot.get("elements") or []:
        if not isinstance(el, dict) or int(el.get("team") or 0) != int(team_id):
            continue
        pos_id = int(el.get("element_type") or 3)
        full_name = f"{el.get('first_name', '')} {el.get('second_name', '')}".strip() or str(el.get("web_name") or "")
        out.append({
            "id": int(el["id"]),
            "name": full_name,
            "web_name": str(el.get("web_name") or full_name),
            "pos": _POS_CODE.get(pos_id, "MID"),
            "pos_fa": _POS_FA.get(pos_id, "بازیکن"),
            "minutes": int(el.get("minutes") or 0),
            "goals": int(el.get("goals_scored") or 0),
            "assists": int(el.get("assists") or 0),
            "points": int(el.get("total_points") or 0),
        })
    out.sort(key=lambda p: (p["minutes"], p["points"], p["goals"]), reverse=True)
    return out




_UNDERSTAT_CACHE_DIR = Path(__file__).resolve().parents[3] / "output" / ".understat_epl_cache"


def _fetch_understat_epl_season_dates(season_yr: int) -> list[dict[str, Any]]:
    """دریافت و کش محلی لیست مسابقات یک فصل لیگ برتر انگلیس از Understat (شامل xG واقعی هر مسابقه)."""
    import re as _re
    try:
        _UNDERSTAT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        now_yr = datetime.now(timezone.utc).year
        cache_f = _UNDERSTAT_CACHE_DIR / f"epl_{season_yr}.json"
        # Past seasons are immutable -> cache permanently; current season -> cache 12h
        if cache_f.exists() and cache_f.stat().st_size > 500:
            age = time.time() - cache_f.stat().st_mtime
            if season_yr < now_yr - 1 or age < 43200:
                return json.loads(cache_f.read_text(encoding="utf-8"))
        req = urllib.request.Request(
            f"https://understat.com/league/EPL/{season_yr}",
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
        )
        with urllib.request.urlopen(req, timeout=7.0) as resp:
            html_txt = resp.read().decode("utf-8", errors="replace")
        m = _re.search(r"datesData\s*=\s*JSON\.parse\('([^']+)'\)", html_txt)
        if not m:
            return []
        dates = json.loads(m.group(1).encode("utf-8").decode("unicode_escape"))
        if isinstance(dates, list) and dates:
            cache_f.write_text(json.dumps(dates, ensure_ascii=False), encoding="utf-8")
            return dates
    except Exception:
        pass
    return []



_CSV_H2H_CACHE_DIR = Path(__file__).resolve().parents[3] / "output" / ".pl_h2h_csv_cache"


def _norm_pl_team_h2h(s: str) -> str:
    import unicodedata as _ud
    raw = "".join(c for c in _ud.normalize("NFKD", str(s or "").lower()) if not _ud.combining(c)).strip()
    aliases = {
        "man city": "manchester city",
        "manchester city fc": "manchester city",
        "man utd": "manchester united",
        "man united": "manchester united",
        "manchester united fc": "manchester united",
        "spurs": "tottenham",
        "tottenham hotspur": "tottenham",
        "tottenham hotspur fc": "tottenham",
        "nott'm forest": "nottingham forest",
        "nottm forest": "nottingham forest",
        "nottingham forest fc": "nottingham forest",
        "wolves": "wolverhampton",
        "wolverhampton wanderers": "wolverhampton",
        "newcastle": "newcastle united",
        "newcastle utd": "newcastle united",
        "west ham": "west ham united",
        "leicester": "leicester city",
        "brighton & hove albion": "brighton",
        "brighton and hove albion": "brighton",
        "afc bournemouth": "bournemouth",
        "leeds united": "leeds",
        "ipswich town": "ipswich",
        "luton town": "luton",
        "sheffield united": "sheffield utd",
    }
    return aliases.get(raw, raw)


def _fetch_fd_couk_e0_season(season_yr: int) -> list[dict[str, Any]]:
    """دریافت و کش دائمی فایل آزاد E0.csv یک فصل لیگ برتر از football-data.co.uk (بدون کلید API و بدون requests)."""
    import csv
    import io
    try:
        _CSV_H2H_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        now_yr = datetime.now(timezone.utc).year
        yy = f"{season_yr % 100:02d}{(season_yr + 1) % 100:02d}"
        cache_f = _CSV_H2H_CACHE_DIR / f"E0_{yy}.json"
        if cache_f.exists() and cache_f.stat().st_size > 400:
            age = time.time() - cache_f.stat().st_mtime
            if season_yr < now_yr - 1 or age < 43200:
                return json.loads(cache_f.read_text(encoding="utf-8"))
        url = f"https://www.football-data.co.uk/mmz4281/{yy}/E0.csv"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=6.5) as resp:
            raw_csv = resp.read().decode("utf-8-sig", errors="replace")
        rows: list[dict[str, Any]] = []
        for row in csv.DictReader(io.StringIO(raw_csv)):
            ht = (row.get("HomeTeam") or "").strip()
            at = (row.get("AwayTeam") or "").strip()
            hg_s = (row.get("FTHG") or "").strip()
            ag_s = (row.get("FTAG") or "").strip()
            dt_s = (row.get("Date") or "").strip()
            if not (ht and at and hg_s.isdigit() and ag_s.isdigit()):
                continue
            # Convert DD/MM/YY or DD/MM/YYYY -> YYYY-MM-DD
            iso_dt = ""
            parts = dt_s.split("/")
            if len(parts) == 3:
                d_p, m_p, y_p = parts
                y_full = f"20{y_p}" if len(y_p) == 2 else y_p
                iso_dt = f"{y_full}-{m_p.zfill(2)}-{d_p.zfill(2)}"
            rows.append({"date": iso_dt, "h": ht, "a": at, "hg": int(hg_s), "ag": int(ag_s)})
        if rows:
            cache_f.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            return rows
    except Exception:
        pass
    return []


def _collect_football_data_couk_pl_h2h(t1_en: str, t2_en: str, *, fpl_season_yr: int, start_yr: int = 2010) -> list[dict[str, Any]]:
    """جمع‌آوری تاریخچه کامل تقابل‌های دو تیم در لیگ برتر از ۲۰۱۰ تا امروز از فایل‌های رسمی E0.csv."""
    import concurrent.futures
    n1, n2 = _norm_pl_team_h2h(t1_en), _norm_pl_team_h2h(t2_en)
    seasons = list(range(start_yr, fpl_season_yr + 1))
    out: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for yr, rows in zip(seasons, ex.map(_fetch_fd_couk_e0_season, seasons)):
            for r in rows:
                dh = _norm_pl_team_h2h(r.get("h") or "")
                da = _norm_pl_team_h2h(r.get("a") or "")
                m1 = (n1 == dh or (len(n1) >= 5 and (n1[:5] in dh or dh[:5] in n1))) and (n2 == da or (len(n2) >= 5 and (n2[:5] in da or da[:5] in n2)))
                m2 = (n2 == dh or (len(n2) >= 5 and (n2[:5] in dh or dh[:5] in n2))) and (n1 == da or (len(n1) >= 5 and (n1[:5] in da or da[:5] in n1)))
                if not (m1 or m2):
                    continue
                t1_is_home = bool(m1)
                hg_raw, ag_raw = int(r["hg"]), int(r["ag"])
                dt_s = str(r.get("date") or "")
                out.append({
                    "date": dt_s,
                    "year": dt_s[:4] or str(yr),
                    "comp": "لیگ برتر",
                    "t1_is_home": t1_is_home,
                    "hg": hg_raw if t1_is_home else ag_raw,
                    "ag": ag_raw if t1_is_home else hg_raw,
                    "hxg": None,
                    "axg": None,
                })
    out.sort(key=lambda g: g["date"], reverse=True)
    return out


def _collect_multi_season_pl_h2h(t1_en: str, t2_en: str, *, fpl_season_yr: int) -> list[dict[str, Any]]:
    """جمع‌آوری موازی تمام تقابل‌های تاریخی دو تیم در لیگ برتر انگلیس از ۲۰۱۴ تا امروز همراه با xG واقعی."""
    import concurrent.futures
    import unicodedata as _ud

    def _norm(s: str) -> str:
        s = "".join(c for c in _ud.normalize("NFKD", str(s or "").lower()) if not _ud.combining(c))
        aliases = {
            "man city": "manchester city", "man utd": "manchester united",
            "spurs": "tottenham", "nott'm forest": "nottingham forest",
            "wolves": "wolverhampton wanderers", "newcastle": "newcastle united",
            "west ham": "west ham united", "leicester": "leicester city",
            "brighton": "brighton", "leeds": "leeds",
        }
        return aliases.get(s.strip(), s.strip())

    n1, n2 = _norm(t1_en), _norm(t2_en)
    seasons = list(range(2014, fpl_season_yr + 1))
    all_games: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        for yr, dates in zip(seasons, ex.map(_fetch_understat_epl_season_dates, seasons)):
            for d in dates:
                if not isinstance(d, dict) or not d.get("isResult"):
                    continue
                dh = _norm(str((d.get("h") or {}).get("title") or ""))
                da = _norm(str((d.get("a") or {}).get("title") or ""))
                if not ((n1[:5] in dh or dh[:5] in n1) and (n2[:5] in da or da[:5] in n2)) and not ((n2[:5] in dh or dh[:5] in n2) and (n1[:5] in da or da[:5] in n1)):
                    continue
                t1_is_home = (n1[:5] in dh or dh[:5] in n1)
                g_obj = d.get("goals") or {}
                x_obj = d.get("xG") or {}
                try:
                    hg_raw, ag_raw = int(g_obj.get("h") or 0), int(g_obj.get("a") or 0)
                    hxg_raw, axg_raw = round(float(x_obj.get("h") or 0.0), 2), round(float(x_obj.get("a") or 0.0), 2)
                except (TypeError, ValueError):
                    continue
                dt_str = str(d.get("datetime") or "")[:10]
                all_games.append({
                    "date": dt_str,
                    "year": dt_str[:4] or str(yr),
                    "comp": "لیگ برتر",
                    "t1_is_home": t1_is_home,
                    "hg": hg_raw if t1_is_home else ag_raw,
                    "ag": ag_raw if t1_is_home else hg_raw,
                    "hxg": hxg_raw if t1_is_home else axg_raw,
                    "axg": axg_raw if t1_is_home else hxg_raw,
                })
    all_games.sort(key=lambda g: g["date"], reverse=True)
    return all_games



_PL_H2H_ARCHIVE_PATH = Path(__file__).resolve().parents[3] / "config" / "pl_h2h_history.json"


def _lookup_pl_h2h_archive(code1: str, code2: str) -> dict[str, Any] | None:
    """بارگذاری آرشیو رسمی تقابل‌های تاریخی دو تیم لیگ برتر (و برگرداندن خودکار در صورت جابه‌جایی میزبان/میهمان)."""
    if not _PL_H2H_ARCHIVE_PATH.exists():
        return None
    try:
        db = json.loads(_PL_H2H_ARCHIVE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    k1 = f"{code1.upper()}_{code2.upper()}"
    k2 = f"{code2.upper()}_{code1.upper()}"
    if k1 in db:
        return dict(db[k1])
    if k2 in db:
        r = db[k2]
        return {
            "since": r["since"],
            "h_wins": r["a_wins"], "draws": r["draws"], "a_wins": r["h_wins"],
            "h_goals": r["a_goals"], "a_goals": r["h_goals"],
            "h_cs": r["a_cs"], "a_cs": r["h_cs"],
            "h_xg": r["a_xg"], "a_xg": r["h_xg"],
            "h_big": r["a_big"], "a_big": r["h_big"],
            "recent5": [
                {"date": g["date"], "comp": g["comp"], "venue": g["venue"], "hg": g["ag"], "ag": g["hg"], "hxg": g.get("axg"), "axg": g.get("hxg")}
                for g in (r.get("recent5") or [])
            ],
        }
    return None


def build_pl_h2h_teams_item(
    team1_id: int,
    team2_id: int,
    *,
    boot: dict[str, Any] | None = None,
    fixtures: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """ساخت کارت کامل تقابل تاریخی و زنده دو تیم لیگ برتر انگلیس (آرشیو چندفصلی Understat + FPL + لوگوهای رسمی)."""
    from src.xgpedia.providers.pl_badges_free import get_pl_badge_data_uri, resolve_distinct_team_colors
    if boot is None or fixtures is None:
        boot, fixtures = fetch_pl_bootstrap_and_fixtures()
    if not boot:
        return None
    stats = _compute_pl_team_stats(boot, fixtures or [])
    t1 = stats.get(int(team1_id))
    t2 = stats.get(int(team2_id))
    if not t1 or not t2 or int(team1_id) == int(team2_id):
        return None

    teams_raw_by_id = {int(t["id"]): t for t in (boot.get("teams") or []) if isinstance(t, dict) and t.get("id") is not None}
    c1, c2 = resolve_distinct_team_colors(t1["color"], t2["color"])
    logo1 = get_pl_badge_data_uri(t1["raw_name"], tla_hint=t1["code"], badge_code=int((teams_raw_by_id.get(int(team1_id)) or {}).get("code") or 0) or None)
    logo2 = get_pl_badge_data_uri(t2["raw_name"], tla_hint=t2["code"], badge_code=int((teams_raw_by_id.get(int(team2_id)) or {}).get("code") or 0) or None)

    evs = boot.get("events") or []
    fpl_yr = int(str(evs[0].get("deadline_time") or "2025")[:4]) if (evs and isinstance(evs[0], dict) and str(evs[0].get("deadline_time") or "")[:4].isdigit()) else 2025
    hist = _collect_multi_season_pl_h2h(t1["raw_name"], t2["raw_name"], fpl_season_yr=fpl_yr)
    # تکمیل تاریخچه چندفصله (۲۰۱۰ تا امروز) از football-data.co.uk E0.csv برای همه جفت‌تیم‌ها (از جمله وقتی Understat ناقص است)
    csv_hist = _collect_football_data_couk_pl_h2h(t1["raw_name"], t2["raw_name"], fpl_season_yr=fpl_yr, start_yr=2010)
    if csv_hist:
        by_date = {g["date"]: g for g in hist if g.get("date")}
        for cg in csv_hist:
            dt_k = cg.get("date") or ""
            if dt_k and dt_k not in by_date:
                hist.append(cg)
                by_date[dt_k] = cg
    # پشتیبان تکمیلی از openfootball/football.json اگر هنوز تاریخچه کوتاه بود
    if len(hist) < 4:
        try:
            from src.xgpedia.providers.open_football_hub import fetch_openfootball_h2h
            of_res = fetch_openfootball_h2h("en.1", t1["raw_name"], t2["raw_name"])
            by_date = {g["date"]: g for g in hist if g.get("date")}
            for rg in (of_res.get("recent") or []):
                dt_k = str(rg.get("date") or "")[:10]
                if dt_k and dt_k not in by_date:
                    t1_h = _norm_pl_team_h2h(str(rg.get("team1") or ""))[:5] == _norm_pl_team_h2h(t1["raw_name"])[:5]
                    s1, s2 = int(rg.get("g1") or 0), int(rg.get("g2") or 0)
                    hist.append({
                        "date": dt_k, "year": dt_k[:4], "comp": "لیگ برتر", "t1_is_home": t1_h,
                        "hg": s1 if t1_h else s2, "ag": s2 if t1_h else s1, "hxg": None, "axg": None,
                    })
                    by_date[dt_k] = hist[-1]
        except Exception:
            pass

    # Merge any current-season finished FPL fixtures not already in hist
    seen_dates = {g["date"] for g in hist}
    for fx in fixtures or []:
        if not isinstance(fx, dict) or not fx.get("finished"):
            continue
        ht, at = fx.get("team_h"), fx.get("team_a")
        hs, as_ = fx.get("team_h_score"), fx.get("team_a_score")
        if hs is None or as_ is None:
            continue
        if {int(ht or 0), int(at or 0)} == {int(team1_id), int(team2_id)}:
            dt_s = str(fx.get("kickoff_time") or "")[:10]
            if dt_s not in seen_dates:
                t1_h = int(ht) == int(team1_id)
                hist.insert(0, {
                    "date": dt_s, "year": dt_s[:4] or str(fpl_yr), "comp": "لیگ برتر", "t1_is_home": t1_h,
                    "hg": int(hs) if t1_h else int(as_), "ag": int(as_) if t1_h else int(hs),
                    "hxg": None, "axg": None,
                })

    hist.sort(key=lambda g: g["date"], reverse=True)
    arch = _lookup_pl_h2h_archive(t1["code"], t2["code"])
    if arch:
        # Merge any newer current-season matches on top of verified all-time historical archive
        arch_dates = {g["date"] for g in (arch.get("recent5") or [])}
        newer = [g for g in hist if g["date"] and g["date"] > max(arch_dates, default="2025-05-01") and g["date"] not in arch_dates]
        w1 = int(arch["h_wins"]) + sum(1 for g in newer if g["hg"] > g["ag"])
        w2 = int(arch["a_wins"]) + sum(1 for g in newer if g["ag"] > g["hg"])
        dr = int(arch["draws"]) + sum(1 for g in newer if g["hg"] == g["ag"])
        g1 = int(arch["h_goals"]) + sum(g["hg"] for g in newer)
        g2 = int(arch["a_goals"]) + sum(g["ag"] for g in newer)
        cs1 = int(arch["h_cs"]) + sum(1 for g in newer if g["ag"] == 0)
        cs2 = int(arch["a_cs"]) + sum(1 for g in newer if g["hg"] == 0)
        tot_m = w1 + dr + w2
        xg1_avg, xg2_avg = arch.get("h_xg"), arch.get("a_xg")
        big1, big2 = arch.get("h_big", "—"), arch.get("a_big", "—")
        comb_r5 = [
            {"date": g["date"], "comp": g["comp"], "venue": f"میزبانی {t1['name']}" if g["t1_is_home"] else f"میزبانی {t2['name']}", "hg": g["hg"], "ag": g["ag"], "hxg": g.get("hxg"), "axg": g.get("axg")}
            for g in newer
        ] + list(arch.get("recent5") or [])
        recent5 = comb_r5[:5]
        momentum8 = [{"label": str(g["date"])[:4], "hg": g["hg"], "ag": g["ag"]} for g in reversed(comb_r5[:8])]
        l10_w1 = round(sum(1 for g in recent5 if g["hg"] > g["ag"]) / max(1, len(recent5)) * 100)
        l10_w2 = round(sum(1 for g in recent5 if g["ag"] > g["hg"]) / max(1, len(recent5)) * 100)
        avg_g = round((g1 + g2) / max(1, tot_m), 2)
        btts_pct = round(sum(1 for g in recent5 if g["hg"] > 0 and g["ag"] > 0) / max(1, len(recent5)) * 100)
        over25_pct = round(sum(1 for g in recent5 if (g["hg"] + g["ag"]) >= 3) / max(1, len(recent5)) * 100)
        first_yr = str(arch.get("since") or "1900")
        return {
            "id": f"pl_h2h_{team1_id}_{team2_id}",
            "is_live": True,
            "competition": "لیگ برتر انگلیس",
            "leagueEn": "PREMIER LEAGUE",
            "round": f"آمار تاریخ تقابل‌ها • از {first_yr}",
            "eraNote": f"آرشیو رسمی {tot_m} تقابل تاریخی ({first_yr} تا امروز)",
            "stadiumScope": "تمامی رقابت‌های رسمی",
            "scopeBadge": "تمامی رقابت‌ها",
            "source": "Opta / XGPedia Archive",
            "source_url": "https://fantasy.premierleague.com/",
            "draws": dr,
            "home": {
                "name": t1["name"], "sub": f"رتبه #{t1['rank']} لیگ برتر • {t1['pts']} امتیاز",
                "code": t1["code"], "color": c1, "secondary": t1["color2"], "logoUrl": logo1 or "",
                "wins": w1, "goals": g1, "xgPerMatch": xg1_avg, "cleanSheets": cs1,
                "last10WinPct": l10_w1, "biggestWin": big1,
                "streak": f"{w1} برد از {tot_m} تقابل تاریخی",
                "venueName": f"میزبانی {t1['name']}", "venueStats": None,
            },
            "away": {
                "name": t2["name"], "sub": f"رتبه #{t2['rank']} لیگ برتر • {t2['pts']} امتیاز",
                "code": t2["code"], "color": c2, "secondary": t2["color2"], "logoUrl": logo2 or "",
                "wins": w2, "goals": g2, "xgPerMatch": xg2_avg, "cleanSheets": cs2,
                "last10WinPct": l10_w2, "biggestWin": big2,
                "streak": f"{w2} برد از {tot_m} تقابل تاریخی",
                "venueName": f"میزبانی {t2['name']}", "venueStats": None,
            },
            "recent5": recent5,
            "momentum8": momentum8,
            "dna": {
                "avgGoals": avg_g, "btts": btts_pct, "over25": over25_pct, "cards": None,
                "headline": f"موازنه تاریخی در {tot_m} تقابل رسمی از سال {first_yr}",
                "body": f"در {tot_m} تقابل رسمی تاریخ دو باشگاه، {t1['name']} {w1} پیروزی و {t2['name']} {w2} پیروزی ثبت کرده‌اند ({dr} تساوی) با میانگین {avg_g:.2f} گل در هر مسابقه.",
            },
        }
    tot_m = len(hist)
    w1 = sum(1 for g in hist if g["hg"] > g["ag"])
    w2 = sum(1 for g in hist if g["ag"] > g["hg"])
    dr = sum(1 for g in hist if g["hg"] == g["ag"])
    g1 = sum(g["hg"] for g in hist)
    g2 = sum(g["ag"] for g in hist)
    cs1 = sum(1 for g in hist if g["ag"] == 0)
    cs2 = sum(1 for g in hist if g["hg"] == 0)

    xg_games = [g for g in hist if g.get("hxg") is not None and g.get("axg") is not None]
    xg1_avg = round(sum(g["hxg"] for g in xg_games) / len(xg_games), 2) if xg_games else None
    xg2_avg = round(sum(g["axg"] for g in xg_games) / len(xg_games), 2) if xg_games else None

    last10 = hist[:10]
    l10_w1 = round(sum(1 for g in last10 if g["hg"] > g["ag"]) / len(last10) * 100) if last10 else None
    l10_w2 = round(sum(1 for g in last10 if g["ag"] > g["hg"]) / len(last10) * 100) if last10 else None

    big1_g = max((g for g in hist if g["hg"] > g["ag"]), key=lambda g: (g["hg"] - g["ag"], g["hg"]), default=None)
    big2_g = max((g for g in hist if g["ag"] > g["hg"]), key=lambda g: (g["ag"] - g["hg"], g["ag"]), default=None)
    big1 = f"{big1_g['hg']} - {big1_g['ag']} (لیگ {big1_g['year']})" if big1_g else "—"
    big2 = f"{big2_g['ag']} - {big2_g['hg']} (لیگ {big2_g['year']})" if big2_g else "—"

    recent5 = [
        {
            "date": g["date"] or g["year"],
            "comp": g["comp"],
            "venue": f"میزبانی {t1['name']}" if g["t1_is_home"] else f"میزبانی {t2['name']}",
            "hg": g["hg"], "ag": g["ag"], "hxg": g.get("hxg"), "axg": g.get("axg"),
        }
        for g in hist[:5]
    ]
    momentum8 = [{"label": g["year"], "hg": g["hg"], "ag": g["ag"]} for g in reversed(hist[:8])]

    # Venue split (Fortress)
    h_home_games = [g for g in hist if g["t1_is_home"]]
    a_home_games = [g for g in hist if not g["t1_is_home"]]
    v1_stats = {
        "w": sum(1 for g in h_home_games if g["hg"] > g["ag"]),
        "d": sum(1 for g in h_home_games if g["hg"] == g["ag"]),
        "l": sum(1 for g in h_home_games if g["hg"] < g["ag"]),
        "gf": round(sum(g["hg"] for g in h_home_games) / max(1, len(h_home_games)), 2),
        "ga": round(sum(g["ag"] for g in h_home_games) / max(1, len(h_home_games)), 2),
    } if h_home_games else None
    v2_stats = {
        "w": sum(1 for g in a_home_games if g["ag"] > g["hg"]),
        "d": sum(1 for g in a_home_games if g["hg"] == g["ag"]),
        "l": sum(1 for g in a_home_games if g["ag"] < g["hg"]),
        "gf": round(sum(g["ag"] for g in a_home_games) / max(1, len(a_home_games)), 2),
        "ga": round(sum(g["hg"] for g in a_home_games) / max(1, len(a_home_games)), 2),
    } if a_home_games else None

    avg_g = round((g1 + g2) / max(1, tot_m), 2) if tot_m else 0.0
    btts_pct = round(sum(1 for g in hist if g["hg"] > 0 and g["ag"] > 0) / max(1, tot_m) * 100) if tot_m else 0
    over25_pct = round(sum(1 for g in hist if (g["hg"] + g["ag"]) >= 3) / max(1, tot_m) * 100) if tot_m else 0
    first_yr = hist[-1]["year"] if hist else str(fpl_yr)

    return {
        "id": f"pl_h2h_{team1_id}_{team2_id}",
        "is_live": True,
        "competition": "لیگ برتر انگلیس",
        "leagueEn": "PREMIER LEAGUE",
        "round": f"آمار تقابل‌های لیگ برتر • از {first_yr}" if tot_m >= 2 else f"رتبه #{t1['rank']} مقابل رتبه #{t2['rank']}",
        "eraNote": f"آرشیو رسمی {tot_m} تقابل لیگ برتر ({first_yr} تا امروز) • رتبه فعلی #{t1['rank']} مقابل #{t2['rank']}",
        "stadiumScope": "تمامی رقابت‌های رسمی",
        "scopeBadge": "لیگ برتر انگلیس",
        "source": "Understat / Opta FPL",
        "source_url": "https://understat.com/league/EPL",
        "draws": dr,
        "home": {
            "name": t1["name"], "sub": f"رتبه #{t1['rank']} لیگ برتر • {t1['pts']} امتیاز",
            "code": t1["code"], "color": c1, "secondary": t1["color2"], "logoUrl": logo1 or "",
            "wins": w1, "goals": g1, "xgPerMatch": xg1_avg, "cleanSheets": cs1,
            "last10WinPct": l10_w1, "biggestWin": big1,
            "streak": f"{w1} برد از {tot_m} تقابل" if tot_m else "رقیب لیگ برتری",
            "venueName": f"میزبانی {t1['name']}", "venueStats": v1_stats,
        },
        "away": {
            "name": t2["name"], "sub": f"رتبه #{t2['rank']} لیگ برتر • {t2['pts']} امتیاز",
            "code": t2["code"], "color": c2, "secondary": t2["color2"], "logoUrl": logo2 or "",
            "wins": w2, "goals": g2, "xgPerMatch": xg2_avg, "cleanSheets": cs2,
            "last10WinPct": l10_w2, "biggestWin": big2,
            "streak": f"{w2} برد از {tot_m} تقابل" if tot_m else "رقیب لیگ برتری",
            "venueName": f"میزبانی {t2['name']}", "venueStats": v2_stats,
        },
        "recent5": recent5,
        "momentum8": momentum8,
        "dna": {
            "avgGoals": avg_g, "btts": btts_pct, "over25": over25_pct, "cards": None,
            "headline": f"کفه ترازو در {tot_m} تقابل رسمی {t1['name']} و {t2['name']}",
            "body": (
                f"در {tot_m} تقابل اخیر لیگ برتر از {first_yr}، {t1['name']} {w1} برد و {t2['name']} {w2} برد ثبت کرده‌اند "
                f"({dr} تساوی)؛ میانگین گل هر مسابقه {avg_g:.2f} بوده و در {btts_pct}٪ بازی‌ها هر دو تیم گل زده‌اند."
            ),
        },
    }


def build_smart_pl_h2h_team_suggestions(*, force_refresh: bool = False, limit: int = 12) -> list[dict[str, Any]]:
    """پیشنهاد هوشمند تقابل تیم‌های همسان کنونی (هم‌رتبه‌های جدول و دیدارهای نزدیک لیگ برتر انگلیس)."""
    boot, fixtures = fetch_pl_bootstrap_and_fixtures(force_refresh=force_refresh)
    if not boot:
        return []
    stats = _compute_pl_team_stats(boot, fixtures)
    ranked = sorted(stats.values(), key=lambda t: t["rank"])
    pairs: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()

    def _add(a: int, b: int) -> None:
        key = (min(a, b), max(a, b))
        if a != b and key not in seen:
            seen.add(key)
            pairs.append((a, b))

    # 1) Adjacent same-tier peers in current standings (1v2, 3v4, 5v6, 7v8, 1v3, 2v4)
    for i in range(0, min(10, len(ranked) - 1), 2):
        _add(ranked[i]["id"], ranked[i + 1]["id"])
    if len(ranked) >= 4:
        _add(ranked[0]["id"], ranked[2]["id"])
        _add(ranked[1]["id"], ranked[3]["id"])

    # 2) Upcoming close-rank Premier League fixtures
    upcoming = [fx for fx in fixtures if isinstance(fx, dict) and not fx.get("finished") and fx.get("kickoff_time")]
    upcoming.sort(key=lambda fx: str(fx.get("kickoff_time") or ""))
    for fx in upcoming[:10]:
        ht, at = fx.get("team_h"), fx.get("team_a")
        if ht in stats and at in stats:
            _add(int(ht), int(at))

    out: list[dict[str, Any]] = []
    for t1_id, t2_id in pairs[:limit]:
        it = build_pl_h2h_teams_item(t1_id, t2_id, boot=boot, fixtures=fixtures)
        if it:
            out.append(it)
    return out


def build_pl_h2h_players_item(player1_id: int, player2_id: int) -> dict[str, Any] | None:
    """ساخت کارت مقایسه دو بازیکن دلخواه لیگ برتر انگلیس از FPL Official API."""
    boot, _ = fetch_pl_bootstrap_and_fixtures()
    if not boot or int(player1_id) == int(player2_id):
        return None
    from src.xgpedia.providers.h2h_players_free import _build_player_side
    teams_by_id = {int(t["id"]): t for t in (boot.get("teams") or []) if isinstance(t, dict) and t.get("id") is not None}
    el_map = {int(e["id"]): e for e in (boot.get("elements") or []) if isinstance(e, dict) and e.get("id") is not None}
    e1, e2 = el_map.get(int(player1_id)), el_map.get(int(player2_id))
    if not e1 or not e2:
        return None
    peers = [e for e in (boot.get("elements") or []) if isinstance(e, dict) and int(e.get("minutes") or 0) >= 90] or [e1, e2]
    p1 = _build_player_side(e1, teams_by_id, peers, fallback_color="#38BDF8")
    p2 = _build_player_side(e2, teams_by_id, peers, fallback_color="#E62E45")
    now = datetime.now(timezone.utc)
    season_yr = now.year if now.month >= 7 else now.year - 1
    return {
        "id": f"pl_h2p_{player1_id}_{player2_id}",
        "is_live": True,
        "competition": "لیگ برتر انگلیس",
        "leagueEn": "PREMIER LEAGUE",
        "season": f"{str(season_yr)[-2:]}/{str(season_yr + 1)[-2:]}",
        "round": "مقایسه مستقیم انتخابی • زنده FPL",
        "context": f"دوئل آماری {p1['name']} ({p1['club']}) در برابر {p2['name']} ({p2['club']})",
        "source": "Premier League / Opta FPL",
        "source_url": "https://fantasy.premierleague.com/",
        "p1": p1,
        "p2": p2,
    }


def build_pl_fc27_item(player_id: int) -> dict[str, Any] | None:
    """ساخت کارت FC27 برای یک بازیکن دلخواه لیگ برتر انگلیس."""
    boot, _ = fetch_pl_bootstrap_and_fixtures()
    if not boot:
        return None
    from src.xgpedia.providers.player_fc27_free import parse_fpl_fc27_players
    # Filter bootstrap elements to just this player + top peers for percentile context
    el_map = {int(e["id"]): e for e in (boot.get("elements") or []) if isinstance(e, dict) and e.get("id") is not None}
    if int(player_id) not in el_map:
        return None
    all_items = parse_fpl_fc27_players(boot, limit=600)
    target_id = f"fpl_fc27_{int(player_id)}"
    for it in all_items:
        if it.get("id") == target_id:
            return it
    # Fallback: build directly for this element even if minutes < threshold
    mini_boot = dict(boot)
    el_copy = dict(el_map[int(player_id)])
    if int(el_copy.get("minutes") or 0) < 90:
        el_copy["minutes"] = max(90, int(el_copy.get("minutes") or 0))
    mini_boot["elements"] = [el_copy]
    items = parse_fpl_fc27_players(mini_boot, limit=5)
    return items[0] if items else None


def build_pl_profile_item(player_id: int) -> dict[str, Any] | None:
    """ساخت کارت پروفایل آماری برای یک بازیکن دلخواه لیگ برتر انگلیس."""
    boot, _ = fetch_pl_bootstrap_and_fixtures()
    if not boot:
        return None
    from src.xgpedia.providers.player_profile_free import parse_fpl_top_players
    el_map = {int(e["id"]): e for e in (boot.get("elements") or []) if isinstance(e, dict) and e.get("id") is not None}
    if int(player_id) not in el_map:
        return None
    all_items = parse_fpl_top_players(boot, limit=600)
    target_id = f"fpl_pl_{int(player_id)}"
    for it in all_items:
        if it.get("id") == target_id:
            return it
    mini_boot = dict(boot)
    el_copy = dict(el_map[int(player_id)])
    if int(el_copy.get("minutes") or 0) < 90:
        el_copy["minutes"] = max(90, int(el_copy.get("minutes") or 0))
    mini_boot["elements"] = [el_copy]
    items = parse_fpl_top_players(mini_boot, limit=5)
    return items[0] if items else None
