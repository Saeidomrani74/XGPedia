"""تأمین دادهٔ چندمنبعی و کاملاً رایگان برای کارت ماژولار «پروفایل فنی بازیکن» (Player Card Studio — D54).

منابع رایگان (بدون وابستگی به `requests`، منحصراً Association Football / Soccer):
  1. FPL Official Bootstrap + Element Summary API (`fantasy.premierleague.com/api/bootstrap-static/` + `element-summary/{id}/`)
     — آمار واقعی فصل، صدک ۰ تا ۹۹ نسبت به هم‌پستی‌ها، موج فرم ۶ بازی اخیر، شباهت کسینوسی DNA Match
       و عکس رسمی فصل جاری لیگ برتر (`resources.premierleague.com/premierleague/photos/players/250x250/p{code}.png`)
  2. TheSportsDB (`strSport == "Soccer"`) — شماره پیراهن واقعی (`strNumber`)، سن، قد، پای تخصصی و عکس Cutout فصل جاری
  3. پریست‌های آماده (`config/player_profile_presets.json`) + غنی‌سازی گزارش دیده‌بان فارسی با LLM.

قانون `null ≠ 0`:
  - هرگز قیمت بازی فانتزی FPL (`now_cost`) به‌عنوان ارزش بازار واقعی (`ارزش`) نمایش داده نمی‌شود؛ اگر ارزش بازار واقعی موجود نباشد `None` می‌ماند.
  - هرگز شماره پیراهن از `id % 99` ساخته نمی‌شود؛ فقط شماره واقعی (`squad_number` یا TheSportsDB `strNumber`) ثبت می‌شود.
"""
from __future__ import annotations

import base64
import json
import math
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.xgpedia.config import ROOT

PRESETS_PATH = ROOT / "config" / "player_profile_presets.json"
USER_AGENT = "XGPediaBot/0.31 (+https://t.me/XGPedia)"

FPL_BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_ELEMENT_SUMMARY_URL = "https://fantasy.premierleague.com/api/element-summary/{pid}/"
PL_PHOTO_URLS = (
    "https://resources.premierleague.com/premierleague/photos/players/250x250/p{code}.png",
    "https://resources.premierleague.com/premierleague/photos/players/110x140/p{code}.png",
)

_NON_SOCCER_RE = re.compile(
    r"\b(nfl|nba|mlb|nhl|afl|cfl|ncaa|rugby|gaelic|cricket|tennis|golf|ufc|f1|basketball|baseball)\b",
    re.IGNORECASE,
)
_CYRILLIC_CJK_RE = re.compile(r"[\u0400-\u04FF\u3040-\u30FF\u4E00-\u9FFF\uAC00-\uD7AF]+")

_FPL_CLUBS: dict[str, tuple[str, str, str, str]] = {
    "Arsenal": ("آرسنال", "ARS", "#EF0107", "#FFFFFF"),
    "Liverpool": ("لیورپول", "LIV", "#C8102E", "#F6EB61"),
    "Man City": ("منچسترسیتی", "MCI", "#38BDF8", "#FFFFFF"),
    "Chelsea": ("چلسی", "CHE", "#2563EB", "#FFFFFF"),
    "Man Utd": ("منچستریونایتد", "MUN", "#DA291C", "#FBE122"),
    "Spurs": ("تاتنهام", "TOT", "#E2E8F0", "#132257"),
    "Newcastle": ("نیوکاسل", "NEW", "#CBD5E1", "#0F172A"),
    "Aston Villa": ("استون ویلا", "AVL", "#95BFE5", "#670E36"),
    "Brighton": ("برایتون", "BHA", "#0057B8", "#FFCD00"),
    "Nott'm Forest": ("ناتینگهام فارست", "NFO", "#E53233", "#FFFFFF"),
    "West Ham": ("وستهام", "WHU", "#7A263A", "#1BB1E7"),
    "Fulham": ("فولام", "FUL", "#F8FAFC", "#CC0000"),
    "Everton": ("اورتون", "EVE", "#003399", "#FFFFFF"),
    "Brentford": ("برنتفورد", "BRE", "#E30613", "#FFFFFF"),
    "Crystal Palace": ("کریستال پالاس", "CRY", "#1B458F", "#C4122E"),
    "Bournemouth": ("بورنموث", "BOU", "#DA291C", "#000000"),
    "Wolves": ("ولورهمپتون", "WOL", "#FDB913", "#231F20"),
    "Leicester": ("لسترسیتی", "LEI", "#003090", "#FDBE11"),
    "Ipswich": ("ایپسویچ", "IPS", "#3A64A3", "#FFFFFF"),
    "Southampton": ("ساوتهمپتون", "SOU", "#D71920", "#FFFFFF"),
}

_POS_META: dict[int, tuple[str, str, str]] = {
    1: ("دروازه‌بان", "GK", "SWEEPER KEEPER"),
    2: ("مدافع", "DEF", "BALL-PLAYING DEFENDER"),
    3: ("هافبک", "MID", "ATTACKING MIDFIELDER"),
    4: ("مهاجم", "ST", "CHANNEL STRIKER"),
}

_LIVE_CACHE: dict[str, Any] = {"ts": 0.0, "items": [], "bootstrap": None}
_CACHE_TTL_SEC = 900.0


def _clean_fa_text(text: str) -> str:
    s = _CYRILLIC_CJK_RE.sub("", str(text or ""))
    s = s.replace("*", "").replace("`", "")
    return re.sub(r"\s+", " ", s).strip()


def _http_get_bytes(url: str, timeout: float = 8.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _http_get_json(url: str, timeout: float = 8.0) -> Any:
    return json.loads(_http_get_bytes(url, timeout=timeout).decode("utf-8", errors="replace"))


def _download_image_data_uri(url: str, timeout: float = 6.0) -> str | None:
    try:
        raw = _http_get_bytes(url, timeout=timeout)
        if len(raw) < 1200:
            return None
        mime = "image/png" if url.lower().endswith(".png") or raw[:4] == b"\x89PNG" else "image/jpeg"
        return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
    except Exception:
        return None


def _percentile(val: float, pool: list[float]) -> int:
    if not pool:
        return 50
    below = sum(1 for x in pool if x <= val)
    return max(1, min(99, int(round(below * 99.0 / len(pool)))))


def _cosine_sim(v1: list[float], v2: list[float]) -> int:
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    if n1 <= 0 or n2 <= 0:
        return 70
    return max(60, min(99, int(round((dot / (n1 * n2)) * 100))))


def load_player_profile_presets() -> list[dict[str, Any]]:
    if not PRESETS_PATH.exists():
        return []
    try:
        data = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def parse_fpl_top_players(bootstrap: dict[str, Any], *, limit: int = 24) -> list[dict[str, Any]]:
    """استخراج برترین بازیکنان زنده لیگ برتر از FPL Official (بدون شماره جعلی و بدون ارزش فانتزی)."""
    if not isinstance(bootstrap, dict):
        return []
    teams_by_id = {int(t["id"]): t for t in (bootstrap.get("teams") or []) if isinstance(t, dict) and t.get("id") is not None}
    elements = [e for e in (bootstrap.get("elements") or []) if isinstance(e, dict)]

    peers_by_pos: dict[int, list[dict[str, Any]]] = {}
    for el in elements:
        if float(el.get("minutes") or 0) >= 360:
            peers_by_pos.setdefault(int(el.get("element_type") or 3), []).append(el)

    candidates = [
        el for el in elements
        if int(el.get("element_type") or 3) != 1 and float(el.get("minutes") or 0) >= 360
    ]
    candidates.sort(
        key=lambda e: float(e.get("expected_goal_involvements") or 0) * 1.5 + float(e.get("total_points") or 0) * 0.12,
        reverse=True,
    )

    results: list[dict[str, Any]] = []
    for el in candidates[:limit]:
        pid = int(el.get("id") or 0)
        tid = int(el.get("team") or 0)
        pos_id = int(el.get("element_type") or 3)
        tobj = teams_by_id.get(tid) or {}
        t_raw = str(tobj.get("name") or "Club")
        c_fa, c_code, c_col, c_sec = _FPL_CLUBS.get(t_raw, (t_raw, str(tobj.get("short_name") or "FC")[:3].upper(), "#E62E45", "#FFFFFF"))
        pos_fa, pos_code, role_en = _POS_META.get(pos_id, ("هافبک", "MID", "ATTACKING MIDFIELDER"))

        mins = max(90.0, float(el.get("minutes") or 90.0))
        starts = int(el.get("starts") or max(1, round(mins / 85.0)))
        goals = int(el.get("goals_scored") or 0)
        assists = int(el.get("assists") or 0)
        xg90 = round(float(el.get("expected_goals") or 0.0) * 90.0 / mins, 2)
        xa90 = round(float(el.get("expected_assists") or 0.0) * 90.0 / mins, 2)
        xgi90 = round(xg90 + xa90, 2)
        creativity90 = round(float(el.get("creativity") or 0.0) * 90.0 / mins, 1)
        threat90 = round(float(el.get("threat") or 0.0) * 90.0 / mins, 1)
        influence90 = round(float(el.get("influence") or 0.0) * 90.0 / mins, 1)
        ict90 = round(float(el.get("ict_index") or 0.0) * 90.0 / mins, 1)
        bps90 = round(float(el.get("bps") or 0.0) * 90.0 / mins, 1)

        peers = peers_by_pos.get(pos_id) or [el]
        p_xg = _percentile(xg90, [float(p.get("expected_goals") or 0) * 90.0 / max(90.0, float(p.get("minutes") or 90.0)) for p in peers])
        p_xa = _percentile(xa90, [float(p.get("expected_assists") or 0) * 90.0 / max(90.0, float(p.get("minutes") or 90.0)) for p in peers])
        p_cre = _percentile(creativity90, [float(p.get("creativity") or 0) * 90.0 / max(90.0, float(p.get("minutes") or 90.0)) for p in peers])
        p_thr = _percentile(threat90, [float(p.get("threat") or 0) * 90.0 / max(90.0, float(p.get("minutes") or 90.0)) for p in peers])
        p_inf = _percentile(influence90, [float(p.get("influence") or 0) * 90.0 / max(90.0, float(p.get("minutes") or 90.0)) for p in peers])
        p_bps = _percentile(bps90, [float(p.get("bps") or 0) * 90.0 / max(90.0, float(p.get("minutes") or 90.0)) for p in peers])
        pct_overall = max(55, min(99, int(round((p_xg + p_xa + p_cre + p_thr + p_inf + p_bps) / 6.0))))
        ovr = round(min(9.8, max(6.8, 6.2 + (pct_overall / 100.0) * 3.3)), 1)
        grade = "A+" if ovr >= 9.0 else ("A" if ovr >= 8.4 else ("B+" if ovr >= 7.8 else "B"))

        my_vec = [xg90 * 100, xa90 * 100, creativity90, threat90, influence90, bps90]
        sim_scored = []
        for pe in peers:
            if int(pe.get("id") or 0) == pid:
                continue
            pm = max(90.0, float(pe.get("minutes") or 90.0))
            p_vec = [
                float(pe.get("expected_goals") or 0) * 9000.0 / pm,
                float(pe.get("expected_assists") or 0) * 9000.0 / pm,
                float(pe.get("creativity") or 0) * 90.0 / pm,
                float(pe.get("threat") or 0) * 90.0 / pm,
                float(pe.get("influence") or 0) * 90.0 / pm,
                float(pe.get("bps") or 0) * 90.0 / pm,
            ]
            sim = _cosine_sim(my_vec, p_vec)
            pt_obj = teams_by_id.get(int(pe.get("team") or 0)) or {}
            sim_scored.append((
                sim,
                {
                    "name": str(pe.get("web_name") or pe.get("second_name") or ""),
                    "club": str(pt_obj.get("short_name") or "PL")[:3].upper(),
                    "sim": sim,
                    "trait": f"{pos_fa} هم‌سبک در لیگ برتر (xG+xA: {(float(pe.get('expected_goal_involvements') or 0) * 90.0 / pm):.2f})",
                },
            ))
        sim_scored.sort(key=lambda x: x[0], reverse=True)
        similar = [x[1] for x in sim_scored[:3]]

        first = str(el.get("first_name") or "").strip()
        second = str(el.get("second_name") or "").strip()
        full_en = f"{first} {second}".strip() or str(el.get("web_name") or "")
        surname = (second.split()[-1] if second else full_en).upper()
        sq_num = el.get("squad_number")
        real_num = int(sq_num) if (sq_num is not None and str(sq_num).isdigit() and 1 <= int(sq_num) <= 99) else None
        fpl_code = el.get("code") or (str(el.get("photo") or "").split(".")[0] or None)

        results.append({
            "id": f"fpl_pl_{pid}",
            "fpl_id": pid,
            "fpl_code": fpl_code,
            "is_live": True,
            "name": full_en,
            "enName": full_en.upper(),
            "surname": surname,
            "club": c_fa,
            "code": c_code,
            "color": c_col,
            "secondary": c_sec,
            "competition": "لیگ برتر انگلیس",
            "round": "پروفایل زنده Opta / FPL",
            "badge": f"صدک {pct_overall} هم‌پستی‌ها",
            "leagueEn": "PREMIER LEAGUE",
            "season": "26/27",
            "source": "Premier League / Opta FPL",
            "source_url": "https://fantasy.premierleague.com/",
            "number": real_num,  # null != 0: هرگز id % 99 استفاده نمی‌شود
            "pos": pos_fa,
            "posCode": pos_code,
            "roleEn": role_en,
            "ovr": ovr,
            "grade": grade,
            "pctOverall": pct_overall,
            "age": None,
            "height": None,
            "foot": None,
            "value": None,  # null != 0: قیمت فانتزی FPL ارزش واقعی بازار نیست!
            "apps": f"{starts} بازی • {int(mins):,} دقیقه",
            "goals": goals,
            "assists": assists,
            "xgPer90": xg90,
            "xaPer90": xa90,
            "portrait": None,
            "imgZoom": 1.04,
            "imgY": 0,
            "pitchZones": [{"x": 82, "y": 50 if pos_id == 4 else 28, "r": 22, "p": 1.0}],
            "kpis": [
                {"label": "مشارکت مورد انتظار", "sub": "xG + xA / 90", "val": f"{xgi90:.2f}", "delta": f"صدک {max(p_xg, p_xa)}", "pct": max(p_xg, p_xa), "accent": "#34D399"},
                {"label": "شاخص خلاقیت", "sub": "CREATIVITY / 90", "val": f"{creativity90:.1f}", "delta": f"صدک {p_cre}", "pct": p_cre, "accent": "#38BDF8"},
                {"label": "شاخص تهدید دروازه", "sub": "THREAT / 90", "val": f"{threat90:.1f}", "delta": f"صدک {p_thr}", "pct": p_thr, "accent": "#FBBF24"},
                {"label": "شاخص کل ICT", "sub": "ICT INDEX / 90", "val": f"{ict90:.1f}", "delta": f"صدک {p_inf}", "pct": p_inf, "accent": "#E62E45"},
            ],
            "percentiles": [
                {"label": "امید گل در ۹۰ دقیقه (xG/90)", "val": f"{xg90:.2f}", "pct": p_xg},
                {"label": "امید پاس گل (xA/90)", "val": f"{xa90:.2f}", "pct": p_xa},
                {"label": "خلاقیت و خلق موقعیت", "val": f"{creativity90:.1f}", "pct": p_cre},
                {"label": "تهدید مستقیم دروازه", "val": f"{threat90:.1f}", "pct": p_thr},
                {"label": "اثرگذاری کلی (Influence)", "val": f"{influence90:.1f}", "pct": p_inf},
                {"label": "امتیاز فنی Opta BPS", "val": f"{bps90:.1f}", "pct": p_bps},
            ],
            "radarLabels": ["تمام‌کنندگی", "پاس گل", "خلاقیت", "تهدید", "اثرگذاری", "ثبات BPS"],
            "radarPlayer": [p_xg, p_xa, p_cre, p_thr, p_inf, p_bps],
            "radarAvg": [50, 50, 50, 50, 50, 50],
            "shots": None,
            "heatZones": None,
            "form": None,
            "duels": None,
            "xgChain": None,
            "similar": similar,
            "scout": None,
        })
    return results


def fetch_live_top_players(force_refresh: bool = False) -> list[dict[str, Any]]:
    now = time.time()
    if not force_refresh and _LIVE_CACHE["items"] and (now - _LIVE_CACHE["ts"]) < _CACHE_TTL_SEC:
        return list(_LIVE_CACHE["items"])
    try:
        bs = _http_get_json(FPL_BOOTSTRAP_URL, timeout=8.0)
        try:
            from src.xgpedia.providers.opta_hub import merge_fpl_and_european_bootstrap
            bs = merge_fpl_and_european_bootstrap(bs, force_refresh=force_refresh)
        except Exception:
            pass
        items = parse_fpl_top_players(bs, limit=36)
        _LIVE_CACHE["ts"] = now
        _LIVE_CACHE["items"] = items
        _LIVE_CACHE["bootstrap"] = bs
        return list(items)
    except Exception:
        return []


def list_player_profile_items(
    *, include_live: bool = True, force_refresh: bool = False
) -> dict[str, list[dict[str, Any]]]:
    presets = load_player_profile_presets()
    live = fetch_live_top_players(force_refresh=force_refresh) if include_live else []
    return {"live": live, "presets": presets}


def _fetch_fpl_player_form(pid: int) -> list[dict[str, Any]] | None:
    try:
        summary = _http_get_json(FPL_ELEMENT_SUMMARY_URL.format(pid=pid), timeout=7.0)
        hist = [h for h in (summary.get("history") or []) if isinstance(h, dict) and int(h.get("minutes") or 0) > 0]
        if len(hist) < 2:
            return None
        bs = _LIVE_CACHE.get("bootstrap") or {}
        team_short = {int(t["id"]): str(t.get("short_name") or "OPP")[:3].upper() for t in (bs.get("teams") or []) if isinstance(t, dict) and t.get("id") is not None}
        out = []
        for h in hist[-6:]:
            bps = float(h.get("bps") or 12)
            g = int(h.get("goals_scored") or 0)
            a = int(h.get("assists") or 0)
            rat = round(min(9.9, max(5.2, 5.6 + bps / 11.2 + (0.25 if g else 0) + (0.15 if a else 0))), 1)
            opp_id = int(h.get("opponent_team") or 0)
            out.append({"opp": team_short.get(opp_id, "OPP"), "rat": rat, "g": g, "a": a})
        return out
    except Exception:
        return None


def _enrich_bio_and_portrait(out: dict[str, Any]) -> None:
    """دریافت عکس رسمی فصل جاری (PL Official PNG ← TheSportsDB Soccer) و مشخصات واقعی (شماره، سن، قد، پا)."""
    fpl_code = out.get("fpl_code")
    if fpl_code and not out.get("portrait"):
        code_clean = re.sub(r"\D", "", str(fpl_code))
        if code_clean:
            for tpl in PL_PHOTO_URLS:
                uri = _download_image_data_uri(tpl.format(code=code_clean), timeout=5.0)
                if uri:
                    out["portrait"] = uri
                    break

    name = str(out.get("name") or "")
    if len(name) >= 3:
        try:
            q = urllib.parse.quote(name.strip())
            data = _http_get_json(f"https://www.thesportsdb.com/api/v1/json/3/searchplayers.php?p={q}", timeout=5.5)
            for pl in data.get("player") or []:
                if not isinstance(pl, dict):
                    continue
                if str(pl.get("strSport") or "").strip().lower() != "soccer":
                    continue
                num_raw = str(pl.get("strNumber") or "").strip()
                if not out.get("number") and num_raw.isdigit() and 1 <= int(num_raw) <= 99:
                    out["number"] = int(num_raw)
                born = str(pl.get("dateBorn") or "").strip()
                if not out.get("age") and len(born) >= 10:
                    try:
                        bdt = datetime.strptime(born[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                        now = datetime.now(timezone.utc)
                        out["age"] = now.year - bdt.year - ((now.month, now.day) < (bdt.month, bdt.day))
                    except Exception:
                        pass
                ht = str(pl.get("strHeight") or "").strip()
                if not out.get("height") and ht:
                    m_cm = re.search(r"(\d{3})\s*cm", ht, re.IGNORECASE)
                    m_m = re.search(r"1\.(\d{2})\s*m", ht, re.IGNORECASE)
                    if m_cm:
                        out["height"] = f"{m_cm.group(1)} cm"
                    elif m_m:
                        out["height"] = f"1{m_m.group(1)} cm"
                side = str(pl.get("strSide") or "").strip().lower()
                if not out.get("foot") and side in ("left", "right", "both"):
                    out["foot"] = "چپ‌پا" if side == "left" else ("راست‌پا" if side == "right" else "دوپا")
                if not out.get("portrait"):
                    for img_k in ("strCutout", "strRender", "strThumb"):
                        u = str(pl.get(img_k) or "").strip()
                        if u.startswith("http"):
                            uri = _download_image_data_uri(u, timeout=5.5)
                            if uri:
                                out["portrait"] = uri
                                break
                break
        except Exception:
            pass


def enrich_player_profile(
    item: dict[str, Any],
    *,
    cancel_event: threading.Event | None = None,
    fetch_network: bool = True,
) -> dict[str, Any]:
    """تکمیل موج فرم ۶ بازی، عکس فصل جاری، شماره واقعی و گزارش دیده‌بان فارسی."""
    out = json.loads(json.dumps(item))

    if fetch_network and out.get("fpl_id") and not out.get("form"):
        form = _fetch_fpl_player_form(int(out["fpl_id"]))
        if form:
            out["form"] = form

    if fetch_network and not out.get("is_preset"):
        _enrich_bio_and_portrait(out)

    if out.get("scout") and (out["scout"] or {}).get("body"):
        return out

    if fetch_network:
        try:
            from src.xgpedia.editorial.llm_provider import generate_text

            prompt = (
                "به‌عنوان دیده‌بان تاکتیکی فوتبال XGPedia، یک گزارش کوتاه فارسی برای پروفایل بازیکن زیر بنویس.\n"
                f"بازیکن: {out.get('name')} ({out.get('club')} — {out.get('pos')})\n"
                f"آمار فصل: {out.get('goals')} گل، {out.get('assists')} پاس گل، xG/90={out.get('xgPer90')}, xA/90={out.get('xaPer90')}, صدک کلی={out.get('pctOverall')}\n"
                'فقط JSON خالص با کلیدهای {"name_fa": "نام فارسی", "title": "تیتر کوتاه", "body": "تحلیل دو جمله‌ای فارسی بدون ستاره و بدون حروف غیرفارسی", '
                '"strengths": ["نقطه قوت ۱", "نقطه قوت ۲", "نقطه قوت ۳"], "watchout": "نقطه بهبود کوتاه", "tag": "تگ پایانی"}'
            )
            raw = generate_text(prompt, max_tokens=340, cancel_event=cancel_event)
            if raw:
                m = re.search(r"\{[\s\S]*\}", raw)
                if m:
                    parsed = json.loads(m.group(0))
                    if parsed.get("name_fa") and not out.get("is_preset"):
                        out["name"] = _clean_fa_text(parsed["name_fa"])[:40]
                    if parsed.get("title") and parsed.get("body"):
                        out["scout"] = {
                            "title": _clean_fa_text(parsed["title"])[:85],
                            "body": _clean_fa_text(parsed["body"])[:250],
                            "strengths": [_clean_fa_text(s)[:36] for s in (parsed.get("strengths") or [])[:3]],
                            "watchout": _clean_fa_text(parsed.get("watchout") or "حفظ ثبات در بازی‌های فشرده")[:90],
                            "tag": _clean_fa_text(parsed.get("tag") or f"صدک کلی {out.get('pctOverall', 80)} در میان هم‌پستی‌ها")[:90],
                        }
                        return out
        except Exception:
            pass

    out["scout"] = {
        "title": f"پروفایل اثرگذار {out.get('name', '')} در ترکیب {out.get('club', '')}",
        "body": (
            f"{out.get('name', '')} با ثبت {out.get('goals', 0)} گل و {out.get('assists', 0)} پاس گل "
            f"و میانگین {float(out.get('xgPer90') or 0) + float(out.get('xaPer90') or 0):.2f} مشارکت مورد انتظار در هر ۹۰ دقیقه، "
            f"در صدک {out.get('pctOverall', 80)} هم‌پستی‌های خود قرار دارد."
        ),
        "strengths": ["خلق موقعیت منظم", "اثرگذاری در یک‌سوم هجومی", "ثبات آماری فصل"],
        "watchout": "مدیریت بار بدنی در هفته‌های پرفشار",
        "tag": f"شاخص XGPedia: {out.get('ovr', 8.0)} | صدک {out.get('pctOverall', 80)}",
    }
    return out
