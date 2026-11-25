"""موتور کشف زنده و پیشنهاد «عدد روز» (Number of the Day) با دیتای واقعی فوتبال (بدون `requests`).

منابع زنده و واقعی (Association Football / Soccer ONLY):
  1. **کشف اعداد شگفت‌انگیز زنده از FPL Official API** (`fantasy.premierleague.com`):
     - عدد آقای گل زنده فصل (تعداد گل + میانگین دقیقه به ازای هر گل و مقایسه با نفر دوم)
     - کلینیکال‌ترین تمام‌کننده لیگ (بیشترین تفاضل مثبت `Goals - xG`)
     - ماشین خلق موقعیت زنده (بیشترین پاس گل / امید پاس گل `xA`)
     - خط حمله آتشین لیگ (بیشترین گل زده تیمی در جدول زنده)
     - دژ دفاعی لیگ (بیشترین کلین‌شیت زنده فصل)
  2. **جستجوی زنده اعداد و رکوردهای خبری از BBC Sport، The Guardian و ESPN Soccer**:
     - استخراج اعداد برجسته از تیترها و گزارش‌های روز (رکوردها، صدتایی‌ها، نوار بدون شکست، هت‌تریک‌ها و آمارهای خاص)
     - امتیازدهی تناسب با قالب کارت (`fit_score`) و پیشنهاد برترین موارد
  3. **پریست‌های آماده (`config/number_of_day_presets.json`)** فقط در دکمه فرعی پریست‌ها.
"""
from __future__ import annotations

import hashlib
import html as _html
import json
import logging
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from src.xgpedia.config import ROOT
from src.xgpedia.providers.pl_badges_free import lookup_pl_club

log = logging.getLogger(__name__)

PRESETS_PATH = ROOT / "config" / "number_of_day_presets.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

_NON_SOCCER_BLOCK = (
    "nfl", "nba", "mlb", "nhl", "cricket", "rugby", "tennis", "wimbledon",
    "formula 1", "f1 ", "ufc", "boxing", "golf", "snooker", "darts", "cycling",
    "super bowl", "quarterback", "touchdown", "innings", "wicket",
)

_NOD_CACHE: dict[str, Any] = {"ts": 0.0, "items": []}
_CACHE_TTL_SEC = 900.0


def load_number_of_day_presets(path: Path | None = None) -> list[dict[str, Any]]:
    """بارگذاری ۵ پریست استودیویی از `config/number_of_day_presets.json`."""
    p = path or PRESETS_PATH
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        items = raw.get("presets") if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            return []
        return [dict(it) for it in items if isinstance(it, dict) and it.get("id")]
    except Exception as e:
        log.warning("failed to load number_of_day_presets.json: %s", e)
        return []


def _clean(raw: str) -> str:
    s = _html.unescape(str(raw or ""))
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def _is_soccer(t: str, d: str) -> bool:
    blob = f" {t} {d} ".lower()
    return not any(b in blob for b in _NON_SOCCER_BLOCK)


def _fa_name(en_name: str) -> str:
    try:
        from src.xgpedia.providers.injury_free import transliterate_player_name_fa
        return transliterate_player_name_fa(en_name)
    except Exception:
        return en_name


def build_fpl_live_numbers(boot: dict[str, Any] | None = None, fixtures: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """استخراج ۵ «عدد روز» واقعی و زنده از آمار فصل جاری لیگ برتر انگلیس (FPL Official)."""
    if boot is None:
        try:
            from src.xgpedia.providers.fpl_free import fetch_fpl_bootstrap, fetch_fpl_fixtures
            boot = fetch_fpl_bootstrap()
            if fixtures is None:
                fixtures = fetch_fpl_fixtures()
        except Exception as e:
            log.warning("FPL live numbers skipped: %s", e)
            return []
    if not isinstance(boot, dict):
        return []

    teams = {t["id"]: t for t in (boot.get("teams") or []) if isinstance(t, dict) and "id" in t}
    elements = [e for e in (boot.get("elements") or []) if isinstance(e, dict)]
    if not teams or not elements:
        return []

    cur_gw = 1
    for ev in (boot.get("events") or []):
        if ev.get("is_current") or ev.get("is_previous"):
            cur_gw = max(cur_gw, int(ev.get("id") or 1))

    items: list[dict[str, Any]] = []

    # 1. عدد آقای گل زنده لیگ برتر (میانگین دقیقه به ازای هر گل یا مجموع گل‌ها)
    scorers = sorted(
        [e for e in elements if int(e.get("minutes") or 0) >= 180 and int(e.get("goals_scored") or 0) >= 1],
        key=lambda x: (int(x.get("goals_scored") or 0), float(x.get("expected_goals") or 0.0)),
        reverse=True,
    )
    if len(scorers) >= 2:
        top, runner = scorers[0], scorers[1]
        t_obj = teams.get(top.get("team"), {})
        c_info = lookup_pl_club(str(t_obj.get("short_name") or t_obj.get("name") or ""))
        en_full = f"{top.get('first_name', '')} {top.get('second_name', '')}".strip()
        fa_full = _fa_name(en_full)
        club_fa = c_info[0] if c_info else str(t_obj.get("name") or "")
        code = str(t_obj.get("short_name") or "PL")[:3].upper()
        accent = c_info[2] if c_info else "#38BDF8"
        g1 = int(top.get("goals_scored") or 0)
        g2 = int(runner.get("goals_scored") or 0)
        xg1 = float(top.get("expected_goals") or 0.0)
        mins = max(1, int(top.get("minutes") or 1))
        mpg = round(mins / max(1, g1))
        diff_g = g1 - g2
        items.append({
            "id": f"live_nod_topscorer_{top.get('id')}",
            "is_live": True,
            "fit_score": 97,
            "mode": "gazette",
            "accent": accent,
            "number": str(g1),
            "suffix": "",
            "unit": f"گل زده در هفته {cur_gw} لیگ برتر",
            "issue": f"{cur_gw:03d}",
            "category": "آمار زنده لیگ برتر",
            "date": f"هفته {cur_gw} فصل جاری",
            "subject": fa_full,
            "subjectEn": en_full.upper()[:22],
            "subjectCode": code,
            "pinText": f"{diff_g}+ گل بالاتر از نزدیک‌ترین تعقیب‌کننده" if diff_g > 0 else "صدرنشین مشترک کفش طلا",
            "ribbonText": f"PREMIER LEAGUE W{cur_gw} • GOLDEN BOOT LEADER",
            "headline": f"صدرنشینی {fa_full} در کورس کفش طلا با میانگین هر {mpg} دقیقه یک گل",
            "body": f"ستاره {club_fa} در {mins} دقیقه بازی رسمی {g1} گل از امید گل {xg1:.2f} به ثمر رسانده و تفاضل تمام‌کنندگی {g1 - xg1:+.2f} را ثبت کرده است.",
            "source": "Premier League / Opta FPL",
            "benchLabel": f"نفر دوم ({_fa_name(str(runner.get('web_name') or ''))})",
            "benchVal": g2,
            "heroNumVal": g1,
            "deltaLabel": f"+{diff_g} گل نسبت به نفر دوم" if diff_g > 0 else "رقابت شانه به شانه در صدر",
            "kpis": [[f"{xg1:.1f}", "امید گل (xG)"], [f"{mpg}'", "میانگین هر گل"], [str(mins), "دقایق بازی"]],
        })

    # 2. کلینیکال‌ترین تمام‌کننده فصل (بیشترین تفاضل مثبت Goals - xG)
    clinical = sorted(
        [e for e in elements if int(e.get("minutes") or 0) >= 270 and int(e.get("goals_scored") or 0) >= 3],
        key=lambda x: int(x.get("goals_scored") or 0) - float(x.get("expected_goals") or 0.0),
        reverse=True,
    )
    if clinical:
        cl_p = clinical[0]
        delta = int(cl_p.get("goals_scored") or 0) - float(cl_p.get("expected_goals") or 0.0)
        if delta >= 1.2:
            t_obj = teams.get(cl_p.get("team"), {})
            c_info = lookup_pl_club(str(t_obj.get("short_name") or t_obj.get("name") or ""))
            en_full = f"{cl_p.get('first_name', '')} {cl_p.get('second_name', '')}".strip()
            fa_full = _fa_name(en_full)
            club_fa = c_info[0] if c_info else str(t_obj.get("name") or "")
            code = str(t_obj.get("short_name") or "PL")[:3].upper()
            g_c = int(cl_p.get("goals_scored") or 0)
            xg_c = float(cl_p.get("expected_goals") or 0.0)
            mins_c = int(cl_p.get("minutes") or 0)
            items.append({
                "id": f"live_nod_clinical_{cl_p.get('id')}",
                "is_live": True,
                "fit_score": 95,
                "mode": "chromatic",
                "accent": "#E62E45",
                "number": f"{delta:.1f}",
                "suffix": "+",
                "unit": "گل فراتر از امید گل (G - xG)",
                "issue": f"{cur_gw:03d}",
                "category": "پدیده کلینیکال هفته",
                "date": f"هفته {cur_gw} لیگ برتر",
                "subject": fa_full,
                "subjectEn": en_full.upper()[:22],
                "subjectCode": code,
                "pinText": "بهترین نرخ تبدیل شوت به گل در لیگ برتر",
                "ribbonText": f"OVERPERFORMANCE • +{delta:.1f} ABOVE xG",
                "headline": f"{fa_full}؛ مرگبارترین تمام‌کننده فصل نسبت به کیفیت موقعیت‌ها",
                "body": f"بازیکن {club_fa} از موقعیت‌هایی به ارزش تنها {xg_c:.2f} امید گل توانسته {g_c} گل به ثمر برساند و کلینیکال‌ترین آمار فصل را ثبت کند.",
                "source": "Opta / FPL Live",
                "benchLabel": "امید گل مورد انتظار (xG)",
                "benchVal": round(xg_c, 1),
                "heroNumVal": g_c,
                "deltaLabel": f"+{delta:.1f} گل بالاتر از xG",
                "kpis": [[str(g_c), "گل واقعی"], [f"{xg_c:.2f}", "امید گل xG"], [str(mins_c), "دقیقه بازی"]],
            })

    # 3. ماشین خلق موقعیت زنده (بیشترین پاس گل فصل)
    assisters = sorted(
        [e for e in elements if int(e.get("minutes") or 0) >= 180 and int(e.get("assists") or 0) >= 2],
        key=lambda x: (int(x.get("assists") or 0), float(x.get("expected_assists") or 0.0)),
        reverse=True,
    )
    if len(assisters) >= 2:
        a1, a2 = assisters[0], assisters[1]
        t_obj = teams.get(a1.get("team"), {})
        c_info = lookup_pl_club(str(t_obj.get("short_name") or t_obj.get("name") or ""))
        en_full = f"{a1.get('first_name', '')} {a1.get('second_name', '')}".strip()
        fa_full = _fa_name(en_full)
        club_fa = c_info[0] if c_info else str(t_obj.get("name") or "")
        code = str(t_obj.get("short_name") or "PL")[:3].upper()
        ast1 = int(a1.get("assists") or 0)
        ast2 = int(a2.get("assists") or 0)
        xa1 = float(a1.get("expected_assists") or 0.0)
        cr1 = float(a1.get("creativity") or 0.0)
        items.append({
            "id": f"live_nod_assists_{a1.get('id')}",
            "is_live": True,
            "fit_score": 92,
            "mode": "foil",
            "accent": "#F59E0B",
            "number": str(ast1),
            "suffix": "",
            "unit": "پاس گل در فصل جاری لیگ برتر",
            "issue": f"{cur_gw:03d}",
            "category": "معمار حملات لیگ",
            "date": f"هفته {cur_gw} فصل جاری",
            "subject": fa_full,
            "subjectEn": en_full.upper()[:22],
            "subjectCode": code,
            "pinText": f"امید پاس گل {xa1:.2f} و شاخص خلاقیت {cr1:.0f}",
            "ribbonText": f"PLAYMAKER LEADER • {ast1} ASSISTS",
            "headline": f"{fa_full}؛ خلاق‌ترین مغز متفکر لیگ برتر تا هفته {cur_gw}",
            "body": f"ستاره {club_fa} با ثبت {ast1} پاس گل و امید پاس گل {xa1:.2f}، اصلی‌ترین موتور خلق موقعیت در لیگ برتر انگلیس بوده است.",
            "source": "Premier League / Opta FPL",
            "benchLabel": f"نفر دوم ({_fa_name(str(a2.get('web_name') or ''))})",
            "benchVal": ast2,
            "heroNumVal": ast1,
            "deltaLabel": f"+{ast1 - ast2} پاس گل برتر" if ast1 > ast2 else "صدرنشین جدول پاس گل",
            "kpis": [[f"{xa1:.2f}", "امید پاس xA"], [f"{cr1:.0f}", "خلاقیت"], [str(int(a1.get("goals_scored") or 0)), "گل زده"]],
        })

    # 4 & 5. دژ دفاعی و آتشین‌ترین خط حمله زنده از fixtures
    if fixtures:
        stats_t: dict[int, dict[str, int]] = {tid: {"gf": 0, "ga": 0, "cs": 0, "mp": 0, "pts": 0} for tid in teams}
        for fx in fixtures:
            if not fx.get("finished"):
                continue
            th_id, ta_id = fx.get("team_h"), fx.get("team_a")
            sh, sa = fx.get("team_h_score"), fx.get("team_a_score")
            if th_id not in stats_t or ta_id not in stats_t or sh is None or sa is None:
                continue
            sh, sa = int(sh), int(sa)
            stats_t[th_id]["mp"] += 1
            stats_t[ta_id]["mp"] += 1
            stats_t[th_id]["gf"] += sh
            stats_t[th_id]["ga"] += sa
            stats_t[ta_id]["gf"] += sa
            stats_t[ta_id]["ga"] += sh
            if sa == 0:
                stats_t[th_id]["cs"] += 1
            if sh == 0:
                stats_t[ta_id]["cs"] += 1
            if sh > sa:
                stats_t[th_id]["pts"] += 3
            elif sa > sh:
                stats_t[ta_id]["pts"] += 3
            else:
                stats_t[th_id]["pts"] += 1
                stats_t[ta_id]["pts"] += 1

        played_ids = [tid for tid, st in stats_t.items() if st["mp"] >= 2]
        if played_ids:
            # بهترین خط حمله
            att_id = max(played_ids, key=lambda tid: stats_t[tid]["gf"])
            avg_gf = round(sum(stats_t[tid]["gf"] for tid in played_ids) / len(played_ids))
            t_att = teams[att_id]
            c_info = lookup_pl_club(str(t_att.get("short_name") or t_att.get("name") or ""))
            cl_fa = c_info[0] if c_info else str(t_att.get("name") or "")
            code = str(t_att.get("short_name") or "PL")[:3].upper()
            st_a = stats_t[att_id]
            items.append({
                "id": f"live_nod_attack_{code}",
                "is_live": True,
                "fit_score": 93,
                "mode": "shatter",
                "accent": c_info[2] if c_info else "#E62E45",
                "number": str(st_a["gf"]),
                "suffix": "",
                "unit": f"گل زده در {st_a['mp']} مسابقه",
                "issue": f"{cur_gw:03d}",
                "category": "آتشین‌ترین خط حمله",
                "date": f"هفته {cur_gw} لیگ برتر",
                "subject": cl_fa,
                "subjectEn": str(t_att.get("name") or code).upper()[:20],
                "subjectCode": code,
                "pinText": f"میانگین {st_a['gf'] / max(1, st_a['mp']):.2f} گل در هر بازی",
                "ribbonText": f"TOP ATTACK • {st_a['gf']} GOALS SCORED",
                "headline": f"خط حمله {cl_fa}؛ پرگل‌ترین ماشین هجومی فصل جاری لیگ برتر",
                "body": f"{cl_fa} با ثبت {st_a['gf']} گل در {st_a['mp']} بازی، فاصله معناداری با میانگین گلزنی تیم‌های لیگ ({avg_gf} گل) ایجاد کرده است.",
                "source": "Premier League / FPL Live",
                "benchLabel": "میانگین گل تیم‌های لیگ",
                "benchVal": avg_gf,
                "heroNumVal": st_a["gf"],
                "deltaLabel": f"+{st_a['gf'] - avg_gf} گل بالاتر از میانگین لیگ",
                "kpis": [[f"{st_a['gf'] / max(1, st_a['mp']):.2f}", "گل در بازی"], [str(st_a["pts"]), "امتیاز"], [f"{st_a['gf'] - st_a['ga']:+d}", "تفاضل گل"]],
            })

            # بهترین خط دفاع (کلین‌شیت)
            def_id = max(played_ids, key=lambda tid: (stats_t[tid]["cs"], -stats_t[tid]["ga"]))
            t_def = teams[def_id]
            c_def = lookup_pl_club(str(t_def.get("short_name") or t_def.get("name") or ""))
            cl_def = c_def[0] if c_def else str(t_def.get("name") or "")
            cd_def = str(t_def.get("short_name") or "PL")[:3].upper()
            st_d = stats_t[def_id]
            if st_d["cs"] >= 2:
                cs_pct = round(st_d["cs"] / max(1, st_d["mp"]) * 100)
                items.append({
                    "id": f"live_nod_defense_{cd_def}",
                    "is_live": True,
                    "fit_score": 91,
                    "mode": "cathedral",
                    "accent": "#10B981",
                    "number": str(st_d["cs"]),
                    "suffix": "",
                    "unit": f"کلین‌شیت در {st_d['mp']} مسابقه",
                    "issue": f"{cur_gw:03d}",
                    "category": "دژ دفاعی لیگ برتر",
                    "date": f"هفته {cur_gw} فصل جاری",
                    "subject": cl_def,
                    "subjectEn": str(t_def.get("name") or cd_def).upper()[:20],
                    "subjectCode": cd_def,
                    "pinText": f"بسته نگه داشتن دروازه در {cs_pct}٪ بازی‌ها",
                    "ribbonText": f"CLEAN SHEET FORTRESS • {st_d['cs']} SHUTOUTS",
                    "headline": f"دیوار آهنین {cl_def}؛ مستحکم‌ترین خط دفاعی فصل جاری",
                    "body": f"{cl_def} در {st_d['cs']} بازی از {st_d['mp']} مسابقه دروازه‌اش را بسته نگه داشته و تنها {st_d['ga']} گل دریافت کرده است.",
                    "source": "Premier League / FPL Live",
                    "benchLabel": "تعداد گل خورده فصل",
                    "benchVal": st_d["ga"],
                    "heroNumVal": st_d["cs"],
                    "deltaLabel": f"{cs_pct}٪ نرخ کلین‌شیت",
                    "kpis": [[f"{cs_pct}٪", "نرخ کلین‌شیت"], [str(st_d["ga"]), "گل خورده"], [str(st_d["pts"]), "امتیاز"]],
                })


    # 6. بیشترین مشارکت گل (گل + پاس گل) فصل جاری
    involvers = sorted(
        [e for e in elements if int(e.get("minutes") or 0) >= 270 and (int(e.get("goals_scored") or 0) + int(e.get("assists") or 0)) >= 3],
        key=lambda x: (int(x.get("goals_scored") or 0) + int(x.get("assists") or 0), float(x.get("expected_goals") or 0.0) + float(x.get("expected_assists") or 0.0)),
        reverse=True,
    )
    if len(involvers) >= 2:
        p1, p2 = involvers[0], involvers[1]
        ga1 = int(p1.get("goals_scored") or 0) + int(p1.get("assists") or 0)
        ga2 = int(p2.get("goals_scored") or 0) + int(p2.get("assists") or 0)
        t_obj = teams.get(p1.get("team"), {})
        c_info = lookup_pl_club(str(t_obj.get("short_name") or t_obj.get("name") or ""))
        en_full = f"{p1.get('first_name', '')} {p1.get('second_name', '')}".strip()
        fa_full = _fa_name(en_full)
        club_fa = c_info[0] if c_info else str(t_obj.get("name") or "")
        code = str(t_obj.get("short_name") or "PL")[:3].upper()
        g1_v, a1_v = int(p1.get("goals_scored") or 0), int(p1.get("assists") or 0)
        mins_v = max(1, int(p1.get("minutes") or 1))
        xgi_v = float(p1.get("expected_goals") or 0.0) + float(p1.get("expected_assists") or 0.0)
        items.append({
            "id": f"live_nod_ga_{p1.get('id')}",
            "is_live": True,
            "fit_score": 96,
            "mode": "cathedral",
            "accent": c_info[2] if c_info else "#38BDF8",
            "number": str(ga1),
            "suffix": "",
            "unit": f"مشارکت مستقیم گل در هفته {cur_gw}",
            "issue": f"{cur_gw:03d}",
            "category": "مؤثرترین بازیکن لیگ برتر",
            "date": f"هفته {cur_gw} فصل جاری",
            "subject": fa_full,
            "subjectEn": en_full.upper()[:22],
            "subjectCode": code,
            "pinText": f"{g1_v} گل و {a1_v} پاس گل رسمی",
            "ribbonText": f"مؤثرترین ستاره لیگ • {ga1} مشارکت گل",
            "headline": f"{fa_full}؛ مؤثرترین بازیکن فصل لیگ برتر با {ga1} مشارکت مستقیم گل",
            "body": f"ستاره {club_fa} در {mins_v} دقیقه حضور در میدان روی {ga1} گل ({g1_v} گل و {a1_v} پاس گل) نقش مستقیم داشته و امید مشارکت {xgi_v:.1f} ثبت کرده است.",
            "source": "Premier League / Opta FPL",
            "benchLabel": f"نفر دوم ({_fa_name(str(p2.get('web_name') or ''))})",
            "benchVal": ga2,
            "heroNumVal": ga1,
            "deltaLabel": f"+{ga1 - ga2} مشارکت بیشتر از نفر دوم" if ga1 > ga2 else "صدرنشین مشترک مشارکت گل",
            "kpis": [[str(g1_v), "گل زده"], [str(a1_v), "پاس گل"], [f"{xgi_v:.1f}", "امید xG+xA"]],
        })

    return items


def extract_news_number_candidate(
    *,
    title: str,
    description: str,
    source_name: str,
    source_url: str = "",
) -> dict[str, Any] | None:
    """استخراج اعداد و رکوردهای مهم از اخبار زنده فوتبال (BBC/Guardian/ESPN)."""
    t = _clean(title)
    d = _clean(description)
    if not t or not _is_soccer(t, d):
        return None
    blob = f"{t} — {d}"
    low = blob.lower()
    if not any(k in low for k in ("record", "unbeaten", "goals", "streak", "consecutive", "milestone", "years", "hat-trick", "clean sheet", "win", "matches", "games", "first")):
        return None
    # پیدا کردن عدد شاخص (غیر از سال ۲۰۲۴-۲۰۲۷)
    nums = [m.group(1) for m in re.finditer(r"\b(\d{1,3}(?:\.\d)?)\b", t) if not (2020 <= float(m.group(1)) <= 2030)]
    if not nums:
        return None
    hero = nums[0]
    hid = hashlib.sha1(f"{source_name}|{t}".encode("utf-8", errors="ignore")).hexdigest()[:10]
    val_f = float(hero)
    # استخراج واحد فارسی واقعی بر اساس کلیدواژه خبر (بدون عبارات کلیشه‌ای)
    unit_fa = ""
    if "unbeaten" in low or "without defeat" in low:
        unit_fa = "بازی پیاپی بدون شکست"
    elif "hat-trick" in low or "hat trick" in low:
        unit_fa = "هت‌تریک ثبت‌شده"
    elif "clean sheet" in low:
        unit_fa = "کلین‌شیت ثبت‌شده"
    elif "goals" in low or "goal" in low:
        unit_fa = "گل ثبت‌شده"
    elif "win" in low or "victories" in low or "streak" in low:
        unit_fa = "پیروزی پیاپی"
    elif "matches" in low or "games" in low:
        unit_fa = "مسابقه رسمی"
    elif "years" in low:
        unit_fa = "سال"

    return {
        "id": f"live_nod_news_{hid}",
        "is_live": True,
        "fit_score": 82,
        "mode": "gazette",
        "accent": "#E62E45",
        "number": hero,
        "suffix": "",
        "unit": unit_fa,
        "issue": hero.replace(".", "")[:3].zfill(3),
        "category": "آمار زنده فوتبال",
        "date": "گزارش زنده امروز",
        "subject": "فوتبال اروپا",
        "subjectEn": "XGPEDIA",
        "subjectCode": "XGP",
        "pinText": "",
        "ribbonText": f"عدد روز فوتبال • {unit_fa or 'آمار ویژه'}",
        "headline": t[:95],
        "body": (d or t)[:200],
        "headline_en": t[:120],
        "body_en": (d or t)[:240],
        "source": source_name,
        "source_url": source_url,
        "benchLabel": "",
        "benchVal": None,
        "heroNumVal": val_f,
        "deltaLabel": "",
        "kpis": [],
    }


def _fetch_news_numbers(timeout: float = 6.0) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for src_name, url in (
        ("BBC Sport", "https://feeds.bbci.co.uk/sport/football/rss.xml"),
        ("The Guardian", "https://www.theguardian.com/football/rss"),
    ):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml,application/xml,text/xml"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read(450_000)
            root = ET.fromstring(raw)
            for it in root.findall(".//item")[:20]:
                c = extract_news_number_candidate(
                    title=(it.findtext("title") or "").strip(),
                    description=(it.findtext("description") or "").strip(),
                    source_name=src_name,
                    source_url=(it.findtext("link") or "").strip(),
                )
                if c:
                    out.append(c)
        except Exception as e:
            log.warning("Number of Day RSS failed (%s): %s", src_name, e)
    return out


def fetch_live_number_of_day_items(*, force_refresh: bool = False, max_items: int = 10) -> list[dict[str, Any]]:
    """جستجوی زنده و پیشنهاد برترین اعداد روز فوتبال (FPL داده‌محور + آمارهای خبری)."""
    now = time.time()
    if not force_refresh and _NOD_CACHE["items"] and (now - _NOD_CACHE["ts"]) < _CACHE_TTL_SEC:
        return [dict(x) for x in _NOD_CACHE["items"]]

    items: list[dict[str, Any]] = []
    fpl_items = build_fpl_live_numbers()
    items.extend(fpl_items)
    # فقط وقتی دیتای غنی و داده‌محور FPL کم باشد از اعداد خبری RSS استفاده شود
    if len(fpl_items) < 4:
        items.extend(_fetch_news_numbers())

    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for it in sorted(items, key=lambda x: int(x.get("fit_score") or 0), reverse=True):
        k = f"{it.get('number')}|{str(it.get('subject') or '')[:20]}"
        if k in seen:
            continue
        seen.add(k)
        uniq.append(it)
        if len(uniq) >= max_items:
            break

    if uniq:
        _NOD_CACHE["ts"] = now
        _NOD_CACHE["items"] = [dict(x) for x in uniq]
    return uniq


def list_all_number_of_day_items(*, include_live: bool = True, force_refresh: bool = False) -> dict[str, list[dict[str, Any]]]:
    presets = load_number_of_day_presets()
    live = fetch_live_number_of_day_items(force_refresh=force_refresh) if include_live else []
    return {"live": live, "presets": presets}


_FORBIDDEN_NOD_PHRASES = (
    "آمار برگزیده روز فوتبال",
    "عدد داغ در رسانه‌های معتبر اروپا",
    "عدد داغ در رسانه های معتبر اروپا",
)
_FORBIDDEN_NOD_KPI_LABELS = frozenset({"عدد شاخص", "وضعیت داده", "منبع"})


def _looks_english_text(text: str) -> bool:
    s = str(text or "").strip()
    if not s:
        return False
    en_n = sum(1 for c in s if "a" <= c.lower() <= "z")
    fa_n = sum(1 for c in s if "\u0600" <= c <= "\u06ff")
    return en_n >= 8 and en_n > fa_n * 1.2


def _translate_nod_text_fa(text: str, *, kind: str = "headline") -> str:
    raw = str(text or "").strip()
    if not raw or not _looks_english_text(raw):
        return raw
    try:
        from src.xgpedia.editorial.llm_provider import generate_text
        if kind == "headline":
            prompt = (
                "تیتر آماری فوتبال زیر را به فارسی روان، کوتاه و مجله‌ای (حداکثر ۱۲ کلمه) ترجمه کن. "
                "فقط خود تیتر فارسی را بدون توضیح اضافه برگردان:\n" + raw
            )
            max_tok = 90
        else:
            prompt = (
                "متن کوتاه آماری فوتبال زیر را به فارسی روان، دقیق و خبری (حداکثر ۲ جمله) ترجمه کن. "
                "فقط خود متن فارسی را برگردان:\n" + raw
            )
            max_tok = 180
        res = generate_text(prompt, max_tokens=max_tok)
        if res and len(res.strip()) >= 8 and not _looks_english_text(res):
            return res.strip().strip('"\'«»')
    except Exception:
        pass
    return raw


def hydrate_number_of_day_item(item: dict[str, Any]) -> dict[str, Any]:
    """تکمیل و فارسی‌سازی نهایی آیتم «عدد روز» پیش از رندر آفلاین + حذف عبارات و KPIهای اضافی."""
    out = dict(item)
    # ۱) حذف عبارات ممنوعه
    for field in ("unit", "pinText", "deltaLabel", "category"):
        val = str(out.get(field) or "").strip()
        if val in _FORBIDDEN_NOD_PHRASES:
            out[field] = ""
    # ۲) حذف KPIهای اضافی (عدد شاخص، وضعیت داده، منبع)
    if isinstance(out.get("kpis"), list):
        out["kpis"] = [
            k for k in out["kpis"]
            if isinstance(k, (list, tuple)) and len(k) >= 2 and str(k[1]).strip() not in _FORBIDDEN_NOD_KPI_LABELS
        ]
    # ۳) فارسی‌سازی تیتر، متن و موضوع در صورت انگلیسی بودن
    if _looks_english_text(str(out.get("headline") or "")):
        tr_hl = _translate_nod_text_fa(str(out["headline"]), kind="headline")
        if _looks_english_text(tr_hl):
            num_s = f"{out.get('number') or ''}{out.get('suffix') or ''}"
            unit_s = str(out.get("unit") or "").strip()
            out["headline"] = f"ثبت آمار {num_s} {unit_s} در فوتبال امروز".strip()
        else:
            out["headline"] = tr_hl
    if _looks_english_text(str(out.get("body") or "")):
        tr_bd = _translate_nod_text_fa(str(out["body"]), kind="body")
        if _looks_english_text(tr_bd):
            num_s = f"{out.get('number') or ''}{out.get('suffix') or ''}"
            unit_s = str(out.get("unit") or "آمار ویژه").strip()
            out["body"] = f"رکورد و عدد {num_s} ({unit_s}) یکی از شاخص‌ترین داده‌های ثبت‌شده در رقابت‌های امروز فوتبال است."
        else:
            out["body"] = tr_bd
    if _looks_english_text(str(out.get("subject") or "")):
        out["subject"] = "فوتبال اروپا"
    if _looks_english_text(str(out.get("ribbonText") or "")):
        unit_s = str(out.get("unit") or "آمار ویژه").strip()
        out["ribbonText"] = f"عدد روز فوتبال • {unit_s}"
    return out
