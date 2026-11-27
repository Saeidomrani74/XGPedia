"""تأمین دادهٔ چندمنبعی و کاملاً رایگان برای کارت ماژولار «کارت بازیکن FC27» (FC27 Chrono Player Card — D56).

منابع رایگان (بدون وابستگی به `requests`، منحصراً Association Football / Soccer):
  1. FPL Official Bootstrap + Element Summary (`fantasy.premierleague.com/api/bootstrap-static/`)
     — آمار واقعی Opta فصل (گل، پاس گل، xG/90، xA/90، ICT، Threat، Creativity، Influence، فرم ۵ بازی اخیر)
       + عکس رسمی فصل جاری لیگ برتر (`resources.premierleague.com/premierleague/photos/players/250x250/p{code}.png`)
  2. TheSportsDB (`strSport == "Soccer"`) — شماره پیراهن واقعی (`strNumber`)، ملیت، پای تخصصی، سن
  3. پریست‌های آماده (`config/player_fc27_presets.json`).

قانون `null ≠ 0`:
  - هرگز قیمت فانتزی FPL (`now_cost`) به‌عنوان ارزش بازار واقعی نمایش داده نمی‌شود (`val` بدون عدد جعلی).
  - هرگز شماره پیراهن از `id % 99` ساخته نمی‌شود؛ در نبود شماره واقعی `None` می‌ماند.
"""
from __future__ import annotations

import json
import time
import urllib.parse
from typing import Any

from src.xgpedia.config import ROOT
from src.xgpedia.providers.player_profile_free import (
    FPL_BOOTSTRAP_URL,
    FPL_ELEMENT_SUMMARY_URL,
    PL_PHOTO_URLS,
    _FPL_CLUBS,
    _clean_fa_text,
    _download_image_data_uri,
    _http_get_json,
    _percentile,
)

PRESETS_PATH = ROOT / "config" / "player_fc27_presets.json"
_LIVE_CACHE: dict[str, Any] = {"ts": 0.0, "items": [], "teams_by_id": {}}

_SHORT_CLUB_FA: dict[str, str] = {
    "منچسترسیتی": "سیتی",
    "منچستریونایتد": "یونایتد",
    "کریستال پالاس": "پالاس",
    "ناتینگهام فارست": "فارست",
    "استون‌ویلا": "ویلا",
    "استون ویلا": "ویلا",
    "ولورهمپتون": "ولوز",
    "هال‌سیتی": "هال",
    "هال سیتی": "هال",
    "ساوتهمپتون": "سنتز",
    "تاتنهام هاتسپر": "تاتنهام",
    "نیوکاسل یونایتد": "نیوکاسل",
    "وستهم یونایتد": "وستهم",
    "لستر سیتی": "لستر",
    "لسترسیتی": "لستر",
    "لیدز یونایتد": "لیدز",
    "ایپسویچ تاون": "ایپسویچ",
    "کاونتری سیتی": "کاونتری",
    "شفیلد یونایتد": "شفیلد",
}


def _short_opp_label_fa(raw_team_name: str, short_fallback: str = "") -> str:
    """برچسب کوتاه و خوانای فارسی تیم حریف برای نمایش زیر ۵ نقطه روند فرم."""
    club_fa = _FPL_CLUBS.get(raw_team_name, (raw_team_name,))[0]
    if club_fa in _SHORT_CLUB_FA:
        return _SHORT_CLUB_FA[club_fa]
    if any("\u0600" <= c <= "\u06ff" for c in club_fa):
        return club_fa
    try:
        from src.xgpedia.config import translate_team_fa
        tr = translate_team_fa(raw_team_name)
        if tr in _SHORT_CLUB_FA:
            return _SHORT_CLUB_FA[tr]
        if any("\u0600" <= c <= "\u06ff" for c in tr):
            return tr
    except Exception:
        pass
    return short_fallback or club_fa[:6]
_CACHE_TTL_SEC = 900.0

_POS_FC27: dict[int, tuple[str, str]] = {
    1: ("GK", "دروازه‌بان مدرن • SWEEPER KEEPER+"),
    2: ("DEF", "مدافع بازی‌ساز • BALL-PLAYING DEF+"),
    3: ("MID", "هافبک طراح و هجومی • PLAYMAKER++"),
    4: ("ST", "مهاجم نوک تمام‌کننده • POACHER++"),
}


def load_player_fc27_presets() -> list[dict[str, Any]]:
    if not PRESETS_PATH.exists():
        return []
    try:
        data = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _clamp_attr(val: float, lo: int = 45, hi: int = 97) -> int:
    return max(lo, min(hi, int(round(val))))


def _derive_fc27_attrs(
    *,
    pos_id: int,
    xg90: float,
    xa90: float,
    crea90: float,
    threat90: float,
    infl90: float,
    bps90: float,
    cs_rate: float,
    p_xg: int,
    p_xa: int,
    p_crea: int,
    p_threat: int,
    p_infl: int,
    p_bps: int,
) -> tuple[int, dict[str, int], list[str]]:
    """تبدیل آمار واقعی Opta/FPL به ۶ ویژگی کارت FC27 و PlayStyle+."""
    sho = _clamp_attr(56 + p_xg * 0.24 + p_threat * 0.16)
    pas = _clamp_attr(56 + p_xa * 0.22 + p_crea * 0.18)
    dri = _clamp_attr(58 + p_crea * 0.18 + p_threat * 0.15 + p_bps * 0.06)
    pac = _clamp_attr(62 + p_threat * 0.20 + p_xg * 0.12)
    def_v = _clamp_attr(40 + (p_infl * 0.34 + cs_rate * 28.0) if pos_id in (1, 2) else (38 + p_infl * 0.26 + p_bps * 0.12))
    phy = _clamp_attr(56 + p_infl * 0.24 + p_bps * 0.14)

    if pos_id == 4:
        ovr_raw = sho * 0.34 + pac * 0.20 + dri * 0.20 + phy * 0.14 + pas * 0.12
    elif pos_id == 3:
        ovr_raw = pas * 0.28 + dri * 0.26 + sho * 0.18 + pac * 0.14 + def_v * 0.07 + phy * 0.07
    elif pos_id == 2:
        ovr_raw = def_v * 0.38 + phy * 0.24 + pas * 0.16 + pac * 0.12 + dri * 0.10
    else:
        ovr_raw = def_v * 0.45 + phy * 0.25 + pas * 0.15 + dri * 0.15

    ovr = _clamp_attr(ovr_raw + 3.0, 74, 94)

    ps: list[str] = []
    if p_xg >= 85 or p_threat >= 88:
        ps.append("finesse")
    if p_crea >= 85 or p_xa >= 85:
        ps.append("incisive")
    if dri >= 84 and len(ps) < 2:
        ps.append("technical")
    if pac >= 85 and len(ps) < 2:
        ps.append("rapid")
    if pos_id == 2 and def_v >= 78 and len(ps) < 2:
        ps.append("anticipate")
    if not ps:
        ps = ["technical", "firsttouch"]

    return ovr, {"pac": pac, "sho": sho, "pas": pas, "dri": dri, "def": def_v, "phy": phy}, ps[:2]


def parse_fpl_fc27_players(bootstrap: dict[str, Any], *, limit: int = 24) -> list[dict[str, Any]]:
    if not isinstance(bootstrap, dict):
        return []
    teams_by_id = {int(t["id"]): t for t in (bootstrap.get("teams") or []) if isinstance(t, dict) and t.get("id") is not None}
    if teams_by_id:
        _LIVE_CACHE["teams_by_id"] = {
            tid: {
                "name": str(tobj.get("name") or ""),
                "short": str(tobj.get("short_name") or ""),
                "label_fa": _short_opp_label_fa(str(tobj.get("name") or ""), str(tobj.get("short_name") or "")),
            }
            for tid, tobj in teams_by_id.items()
        }
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
        key=lambda e: float(e.get("expected_goal_involvements") or 0) * 1.6 + float(e.get("total_points") or 0) * 0.12,
        reverse=True,
    )

    out: list[dict[str, Any]] = []
    for el in candidates[:limit]:
        pid = int(el.get("id") or 0)
        tid = int(el.get("team") or 0)
        pos_id = int(el.get("element_type") or 3)
        tobj = teams_by_id.get(tid) or {}
        t_raw = str(tobj.get("name") or "Club")
        club_fa, club_code, col, sec = _FPL_CLUBS.get(t_raw, (t_raw, str(tobj.get("short_name") or "CLB")[:3].upper(), "#38BDF8", "#FFFFFF"))

        mins = max(1.0, float(el.get("minutes") or 0))
        apps = max(1, int(el.get("starts") or round(mins / 82.0)))
        xg90 = float(el.get("expected_goals_per_90") or (float(el.get("expected_goals") or 0) * 90.0 / mins))
        xa90 = float(el.get("expected_assists_per_90") or (float(el.get("expected_assists") or 0) * 90.0 / mins))
        crea90 = float(el.get("creativity") or 0) * 90.0 / mins
        threat90 = float(el.get("threat") or 0) * 90.0 / mins
        infl90 = float(el.get("influence") or 0) * 90.0 / mins
        bps90 = float(el.get("bps") or 0) * 90.0 / mins
        ict90 = float(el.get("ict_index") or 0) * 90.0 / mins
        cs_rate = float(el.get("clean_sheets") or 0) / apps

        peers = peers_by_pos.get(pos_id) or candidates
        p_xg = _percentile(xg90, [float(p.get("expected_goals_per_90") or 0) for p in peers])
        p_xa = _percentile(xa90, [float(p.get("expected_assists_per_90") or 0) for p in peers])
        p_crea = _percentile(crea90, [float(p.get("creativity") or 0) * 90.0 / max(1.0, float(p.get("minutes") or 1)) for p in peers])
        p_threat = _percentile(threat90, [float(p.get("threat") or 0) * 90.0 / max(1.0, float(p.get("minutes") or 1)) for p in peers])
        p_infl = _percentile(infl90, [float(p.get("influence") or 0) * 90.0 / max(1.0, float(p.get("minutes") or 1)) for p in peers])
        p_bps = _percentile(bps90, [float(p.get("bps") or 0) * 90.0 / max(1.0, float(p.get("minutes") or 1)) for p in peers])

        ovr, stats, ps = _derive_fc27_attrs(
            pos_id=pos_id, xg90=xg90, xa90=xa90, crea90=crea90, threat90=threat90,
            infl90=infl90, bps90=bps90, cs_rate=cs_rate,
            p_xg=p_xg, p_xa=p_xa, p_crea=p_crea, p_threat=p_threat, p_infl=p_infl, p_bps=p_bps,
        )
        pos_code, role_lbl = _POS_FC27.get(pos_id, ("MID", "هافبک محوری"))
        first_n = str(el.get("first_name") or "").strip()
        second_n = str(el.get("second_name") or "").strip()
        from src.xgpedia.providers.injury_free import transliterate_player_name_fa
        web_n = str(el.get("web_name") or "").strip()
        full_en = f"{first_n} {second_n}".strip() or web_n or "Player"
        sec_words = second_n.split()
        compact_full = f"{first_n} {sec_words[-1]}".strip() if (first_n and len(sec_words) >= 2) else full_en
        # اولویت با نام کامل یا اول+آخر (مثلاً Bruno Fernandes)، سپس web_name (مثل B.Fernandes)
        cand_en = compact_full if len(full_en.split()) >= 3 else full_en
        name_fa = transliterate_player_name_fa(cand_en)
        if not name_fa or name_fa == "بازیکن":
            name_fa = transliterate_player_name_fa(web_n or full_en)
        goals = int(el.get("goals_scored") or 0)
        assists = int(el.get("assists") or 0)
        squad_num = el.get("squad_number")
        try:
            real_num = int(squad_num) if squad_num not in (None, "", 0, "0") else None
        except (TypeError, ValueError):
            real_num = None

        xgp_idx = round(min(99.0, max(62.0, (p_xg + p_xa + p_crea + p_threat + p_infl + p_bps) / 6.0 + 12.0)), 1)
        tier = "tots" if ovr >= 89 else ("signature" if ovr >= 84 else "future")
        photo_code = str(el.get("code") or "")

        out.append({
            "id": f"fpl_fc27_{pid}",
            "is_preset": False,
            "fpl_id": pid,
            "fpl_photo_code": photo_code,
            "tier": tier,
            "name": name_fa,
            "en": full_en.upper(),
            "pos": pos_code,
            "num": real_num,
            "nat": "EPL",
            "club": club_fa,
            "code": club_code,
            "color": col,
            "secondary": sec,
            "competition": "لیگ برتر انگلیس",
            "leagueEn": "PREMIER LEAGUE",
            "season": "26/27",
            "badge": "کارت زنده Opta / FPL",
            "source": "Premier League / Opta FPL",
            "foot": "",
            "stars": f"{goals} گل • {assists} پاس گل • {int(mins)} دقیقه",
            "ovr": ovr,
            "boost": None,
            "stats": stats,
            "ps": ps,
            "role": role_lbl,
            "val": None,  # قانون null != 0: قیمت فانتزی FPL هرگز ارزش بازار نیست
            "xgpIndex": xgp_idx,
            "p90": {
                "xg": round(xg90, 2),
                "xa": round(xa90, 2),
                "xt": round(ict90 / 10.0, 2),
                "sca": round(bps90 / 6.5, 1),
            },
            "radar": [p_xg, p_xa, p_crea, p_threat, p_infl, p_bps],
            "form": [],
            "form_opponents": [],
            "heat": [],
            "verdictTitle": f"عملکرد فصل {name_fa} در ترکیب {club_fa}",
            "verdictBody": _clean_fa_text(
                f"{name_fa} در {int(mins)} دقیقه بازی، {goals} گل و {assists} پاس گل ثبت کرده و با میانگین "
                f"{xg90 + xa90:.2f} مشارکت مورد انتظار در هر ۹۰ دقیقه، ریتینگ FC27 برابر {ovr} به دست آورده است."
            ),
            "photoUrl": None,
            "_hydrated": False,
        })
    return out


def fetch_live_player_fc27_items(*, force_refresh: bool = False, limit: int = 24) -> list[dict[str, Any]]:
    now_ts = time.time()
    if not force_refresh and _LIVE_CACHE["items"] and (now_ts - _LIVE_CACHE["ts"]) < _CACHE_TTL_SEC:
        return list(_LIVE_CACHE["items"])[:limit]
    try:
        bootstrap = _http_get_json(FPL_BOOTSTRAP_URL, timeout=9.0)
    except Exception:
        return []
    try:
        from src.xgpedia.providers.opta_hub import merge_fpl_and_european_bootstrap
        bootstrap = merge_fpl_and_european_bootstrap(bootstrap, force_refresh=force_refresh)
    except Exception:
        pass
    items = parse_fpl_fc27_players(bootstrap, limit=max(limit, 36))
    _LIVE_CACHE["ts"] = now_ts
    _LIVE_CACHE["items"] = items
    return list(items)


def hydrate_player_fc27_item(item: dict[str, Any]) -> dict[str, Any]:
    """دریافت عکس رسمی فصل جاری لیگ برتر، فرم ۵ بازی اخیر و شماره پیراهن واقعی از TheSportsDB."""
    if not isinstance(item, dict) or item.get("is_preset") or item.get("_hydrated"):
        return item

    # 1. عکس رسمی فصل جاری PL
    pcode = str(item.get("fpl_photo_code") or "")
    if pcode and not item.get("photoUrl"):
        for tmpl in PL_PHOTO_URLS:
            uri = _download_image_data_uri(tmpl.format(code=pcode), timeout=5.5)
            if uri:
                item["photoUrl"] = uri
                break

    # 2. فرم ۵ بازی اخیر واقعی از FPL element-summary
    pid = item.get("fpl_id")
    if pid:
        try:
            summ = _http_get_json(FPL_ELEMENT_SUMMARY_URL.format(pid=pid), timeout=6.5)
            hist = [h for h in (summ.get("history") or []) if isinstance(h, dict) and int(h.get("minutes") or 0) > 0]
            last5 = hist[-5:]
            teams_map = _LIVE_CACHE.get("teams_by_id") or {}
            if not teams_map:
                try:
                    bs = _http_get_json(FPL_BOOTSTRAP_URL, timeout=6.0)
                    if isinstance(bs, dict) and bs.get("teams"):
                        teams_map = {
                            int(t["id"]): {
                                "name": str(t.get("name") or ""),
                                "short": str(t.get("short_name") or ""),
                                "label_fa": _short_opp_label_fa(str(t.get("name") or ""), str(t.get("short_name") or "")),
                            }
                            for t in bs["teams"]
                            if isinstance(t, dict) and t.get("id") is not None
                        }
                        _LIVE_CACHE["teams_by_id"] = teams_map
                except Exception:
                    teams_map = {}
            form_vals: list[float] = []
            form_opps: list[str] = []
            for h in last5:
                bps = float(h.get("bps") or 0)
                g = int(h.get("goals_scored") or 0)
                a = int(h.get("assists") or 0)
                rt = round(min(9.8, max(5.2, 5.7 + bps / 11.0 + g * 0.25 + a * 0.15)), 1)
                form_vals.append(rt)
                opp_id = h.get("opponent_team")
                opp_lbl = ""
                if opp_id is not None:
                    try:
                        tinfo = teams_map.get(int(opp_id)) or {}
                        opp_lbl = str(tinfo.get("label_fa") or "")
                    except (TypeError, ValueError):
                        opp_lbl = ""
                form_opps.append(opp_lbl)
            if form_vals:
                item["form"] = form_vals
                if any(form_opps):
                    item["form_opponents"] = form_opps
        except Exception:
            pass

    # 3. شماره پیراهن و پای تخصصی واقعی از TheSportsDB (منحصراً Soccer)
    if item.get("num") is None or not item.get("foot"):
        q = urllib.parse.quote(str(item.get("en") or item.get("name") or "").title())
        if q:
            try:
                tsdb = _http_get_json(f"https://www.thesportsdb.com/api/v1/json/3/searchplayers.php?p={q}", timeout=6.0)
                for p in (tsdb.get("player") or []):
                    if not isinstance(p, dict):
                        continue
                    if str(p.get("strSport") or "").strip().lower() != "soccer":
                        continue
                    if item.get("num") is None and p.get("strNumber"):
                        try:
                            n = int(str(p["strNumber"]).strip())
                            if 1 <= n <= 99:
                                item["num"] = n
                        except ValueError:
                            pass
                    if not item.get("foot") and p.get("strSide"):
                        side = str(p["strSide"]).lower()
                        item["foot"] = "چپ‌پا" if "left" in side else ("راست‌پا" if "right" in side else "")
                    if not item.get("photoUrl") and p.get("strCutout"):
                        uri = _download_image_data_uri(str(p["strCutout"]), timeout=5.5)
                        if uri:
                            item["photoUrl"] = uri
                    break
            except Exception:
                pass

    item["_hydrated"] = True
    return item


def list_all_player_fc27_items(*, include_live: bool = True, force_refresh: bool = False) -> list[dict[str, Any]]:
    presets = load_player_fc27_presets()
    live = fetch_live_player_fc27_items(force_refresh=force_refresh) if include_live else []
    return live + presets
