"""موتور کشف زنده و پیشنهاد مناظره‌های داغ و داده‌محور فوتبال (۱۰۰٪ رایگان، بدون `requests`).

منابع زنده و واقعی فوتبال (Association Football / Soccer ONLY):
  1. **مناظره‌های آماری زنده از FPL Official API** (`fantasy.premierleague.com`):
     - کورس قهرمانی لیگ برتر: مقایسه دو مدعی اول جدول زنده (امتیاز، گل زده، امید گل تیمی، کلین‌شیت)
     - دوئل کفش طلا: مقایسه دو گلزن برتر فصل جاری (گل، xG، تهدید، دقایق، نرخ گل/۹۰) با پرتره رسمی FPL
     - دوئل بهترین بازی‌ساز: مقایسه دو خلاق‌ترین بازیکن فصل (پاس گل، xA، خلاقیت، اثرگذاری) با پرتره رسمی FPL
  2. **جستجوی زنده سوژه‌های جنجالی و مناظره از اخبار فوتبال**:
     - BBC Sport Football RSS (`https://feeds.bbci.co.uk/sport/football/rss.xml`)
     - The Guardian Football RSS (`https://www.theguardian.com/football/rss`)
     - ESPN Soccer Live News (`eng.1`, `uefa.champions`, `esp.1`)
     - تشخیص خودکار سوژه‌های مناسب مناظره (تقابل دو باشگاه/ستاره، VAR و داوری، فشار روی سرمربی، فرمت و تقویم، نقل‌وانتقالات داغ) و امتیازدهی تناسب (`fit_score` و `heat`).
  3. **پریست‌های آماده (`config/debate_presets.json`)** فقط در دکمه فرعی پریست‌ها.
"""
from __future__ import annotations

import base64
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
from src.xgpedia.providers.breaking_news_free import _looks_mostly_english, upgrade_news_image_url
from src.xgpedia.providers.pl_badges_free import lookup_pl_club, resolve_distinct_team_colors

log = logging.getLogger(__name__)

PRESETS_PATH = ROOT / "config" / "debate_presets.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

_NON_SOCCER_BLOCK = (
    "nfl", "nba", "mlb", "nhl", "cricket", "rugby", "tennis", "wimbledon",
    "formula 1", "f1 ", "ufc", "boxing", "golf", "snooker", "darts", "cycling",
    "super bowl", "quarterback", "touchdown", "innings", "wicket",
)

_DEBATE_RSS_FEEDS: list[tuple[str, str]] = [
    ("BBC Sport", "https://feeds.bbci.co.uk/sport/football/rss.xml"),
    ("The Guardian", "https://www.theguardian.com/football/rss"),
]

_DEBATE_ESPN_FEEDS: list[tuple[str, str]] = [
    ("eng.1", "لیگ برتر انگلیس"),
    ("uefa.champions", "لیگ قهرمانان اروپا"),
    ("uefa.europa", "لیگ اروپا"),
    ("esp.1", "لالیگا اسپانیا"),
    ("ita.1", "سری آ ایتالیا"),
    ("ger.1", "بوندس‌لیگا آلمان"),
    ("fra.1", "لیگ ۱ فرانسه"),
]

_CLUB_MAP: list[tuple[str, str, str, str]] = [
    ("arsenal", "آرسنال", "ARS", "#EF0107"),
    ("liverpool", "لیورپول", "LIV", "#C8102E"),
    ("manchester city", "منچسترسیتی", "MCI", "#6CABDD"),
    ("man city", "منچسترسیتی", "MCI", "#6CABDD"),
    ("manchester united", "منچستریونایتد", "MUN", "#DA291C"),
    ("man utd", "منچستریونایتد", "MUN", "#DA291C"),
    ("chelsea", "چلسی", "CHE", "#38BDF8"),
    ("tottenham", "تاتنهام", "TOT", "#CBD5E1"),
    ("spurs", "تاتنهام", "TOT", "#CBD5E1"),
    ("newcastle", "نیوکاسل", "NEW", "#E2E8F0"),
    ("aston villa", "استون ویلا", "AVL", "#A855F7"),
    ("everton", "اورتون", "EVE", "#38BDF8"),
    ("real madrid", "رئال مادرید", "RMA", "#F59E0B"),
    ("barcelona", "بارسلونا", "BAR", "#E62E45"),
    ("bayern munich", "بایرن مونیخ", "BAY", "#DC052D"),
    ("psg", "پاری‌سن‌ژرمن", "PSG", "#38BDF8"),
    ("inter milan", "اینتر میلان", "INT", "#3B82F6"),
]

_DEBATE_CACHE: dict[str, Any] = {"ts": 0.0, "items": []}
_CACHE_TTL_SEC = 900.0


def load_debate_presets(path: Path | None = None) -> list[dict[str, Any]]:
    """بارگذاری ۵ پریست استودیویی از `config/debate_presets.json`."""
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
        log.warning("failed to load debate_presets.json: %s", e)
        return []


def _clean(raw: str) -> str:
    s = _html.unescape(str(raw or ""))
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def _is_soccer(t: str, d: str) -> bool:
    blob = f" {t} {d} ".lower()
    return not any(b in blob for b in _NON_SOCCER_BLOCK)


def _norm_score(val: float, max_v: float, floor: int = 48, ceil: int = 99) -> int:
    if max_v <= 0:
        return 70
    r = max(0.0, min(1.0, val / max_v))
    return int(round(floor + r * (ceil - floor)))


def _fa_name(en_name: str) -> str:
    try:
        from src.xgpedia.providers.injury_free import transliterate_player_name_fa
        return transliterate_player_name_fa(en_name)
    except Exception:
        return en_name


def build_fpl_live_debates(boot: dict[str, Any] | None = None, fixtures: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """ساخت خودکار ۳ مناظره زنده و ۱۰۰٪ داده‌محور از آمار واقعی فصل جاری لیگ برتر (FPL Official)."""
    if boot is None:
        try:
            from src.xgpedia.providers.fpl_free import fetch_fpl_bootstrap, fetch_fpl_fixtures
            boot = fetch_fpl_bootstrap()
            if fixtures is None:
                fixtures = fetch_fpl_fixtures()
        except Exception as e:
            log.warning("FPL live debates skipped: %s", e)
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

    debates: list[dict[str, Any]] = []

    # 1. مناظره کورس کفش طلا (دو گلزن برتر زنده فصل جاری)
    strikers = sorted(
        [e for e in elements if int(e.get("minutes") or 0) >= 180 and int(e.get("goals_scored") or 0) >= 1],
        key=lambda x: (int(x.get("goals_scored") or 0), float(x.get("expected_goals") or 0.0)),
        reverse=True,
    )
    if len(strikers) >= 2:
        p1, p2 = strikers[0], strikers[1]
        t1, t2 = teams.get(p1.get("team"), {}), teams.get(p2.get("team"), {})
        c1_info = lookup_pl_club(str(t1.get("short_name") or t1.get("name") or ""))
        c2_info = lookup_pl_club(str(t2.get("short_name") or t2.get("name") or ""))
        n1 = _fa_name(f"{p1.get('first_name', '')} {p1.get('second_name', '')}".strip())
        n2 = _fa_name(f"{p2.get('first_name', '')} {p2.get('second_name', '')}".strip())
        cl1 = c1_info[0] if c1_info else str(t1.get("name") or "")
        cl2 = c2_info[0] if c2_info else str(t2.get("name") or "")
        cd1 = str(t1.get("short_name") or "PL1")[:3].upper()
        cd2 = str(t2.get("short_name") or "PL2")[:3].upper()
        col1, col2 = resolve_distinct_team_colors(
            c1_info[2] if c1_info else "#38BDF8",
            c2_info[2] if c2_info else "#E62E45",
        )
        g1, g2 = int(p1.get("goals_scored") or 0), int(p2.get("goals_scored") or 0)
        _xg1_raw, _xg2_raw = p1.get("expected_goals"), p2.get("expected_goals")
        _xa1_raw, _xa2_raw = p1.get("expected_assists"), p2.get("expected_assists")
        xg1 = float(_xg1_raw) if _xg1_raw not in (None, "") else 0.0
        xg2 = float(_xg2_raw) if _xg2_raw not in (None, "") else 0.0
        xa1 = float(_xa1_raw) if _xa1_raw not in (None, "") else 0.0
        xa2 = float(_xa2_raw) if _xa2_raw not in (None, "") else 0.0
        m1, m2 = max(1, int(p1.get("minutes") or 1)), max(1, int(p2.get("minutes") or 1))
        g90_1, g90_2 = g1 * 90.0 / m1, g2 * 90.0 / m2
        th1, th2 = float(p1.get("threat") or 0.0), float(p2.get("threat") or 0.0)
        cr1, cr2 = float(p1.get("creativity") or 0.0), float(p2.get("creativity") or 0.0)
        inf1, inf2 = float(p1.get("influence") or 0.0), float(p2.get("influence") or 0.0)
        bps1, bps2 = float(p1.get("bps") or 0.0), float(p2.get("bps") or 0.0)
        tot_g = max(1, g1 + g2)
        v_a = max(35, min(68, int(round(g1 / tot_g * 100))))
        img1 = f"https://resources.premierleague.com/premierleague/photos/players/250x250/p{p1['code']}.png" if p1.get("code") else None
        img2 = f"https://resources.premierleague.com/premierleague/photos/players/250x250/p{p2['code']}.png" if p2.get("code") else None

        debates.append({
            "id": f"live_db_goldenboot_{p1.get('id')}_{p2.get('id')}",
            "is_live": True,
            "fit_score": 96,
            "category": "لیگ برتر انگلیس • کورس کفش طلا",
            "episode": f"هفته {cur_gw} • دوئل زنده گلزنان",
            "title": f"خطرناک‌ترین تمام‌کننده فصل جاری لیگ برتر؛ {n1} یا {n2}؟",
            "highlight": "خطرناک‌ترین تمام‌کننده",
            "hotTake": f"{n1} با {g1} گل و امید گل {xg1:.2f} در صدر جدول گلزنان ایستاده، اما {n2} با {g2} گل و نرخ {g90_2:.2f} گل در هر ۹۰ دقیقه جدی‌ترین تهدید برای کفش طلای این فصل است.",
            "tag": f"PREMIER LEAGUE W{cur_gw} • GOLDEN BOOT DEBATE",
            "source": "Opta / FPL Live",
            "heat": 95,
            "voteA": v_a,
            "voteTotal": "برآورد آماری زنده",
            "cta": f"{n1} یا {n2}؟ کدام مهاجم کفش طلا را می‌برد؟",
            "verdict": f"تا هفته {cur_gw}، {n1} با تفاضل گل-امیدگل {g1 - xg1:+.2f} و {n2} با {g2 - xg2:+.2f} دو سبک متفاوت تمام‌کنندگی در لیگ برتر ارائه داده‌اند.",
            "radarLabels": ["گلزنی", "امید گل xG", "تهدید دروازه", "خلاقیت", "اثرگذاری", "نرخ در ۹۰ دقیقه"],
            "radarA": [
                _norm_score(g1, max(g1, g2, 1)),
                _norm_score(xg1, max(xg1, xg2, 0.1)),
                _norm_score(th1, max(th1, th2, 1)),
                _norm_score(cr1, max(cr1, cr2, 1)),
                _norm_score(inf1, max(inf1, inf2, 1)),
                _norm_score(g90_1, max(g90_1, g90_2, 0.1)),
            ],
            "radarB": [
                _norm_score(g2, max(g1, g2, 1)),
                _norm_score(xg2, max(xg1, xg2, 0.1)),
                _norm_score(th2, max(th1, th2, 1)),
                _norm_score(cr2, max(cr1, cr2, 1)),
                _norm_score(inf2, max(inf1, inf2, 1)),
                _norm_score(g90_2, max(g90_1, g90_2, 0.1)),
            ],
            "sideA": {
                "name": n1,
                "sub": f"{cl1} • {g1} گل در {m1} دقیقه",
                "code": cd1,
                "color": col1,
                "secondary": "#FFFFFF",
                "entityType": "person",
                "fpl_photo_code": str(p1.get("code") or ""),
                "img": img1,
                "thesis": f"ثبت {g1} گل از امید گل {xg1:.2f} با نرخ {g90_1:.2f} گل در هر ۹۰ دقیقه",
                "args": [
                    f"امید گل تجمعی {xg1:.2f} و تفاضل تمام‌کنندگی {g1 - xg1:+.2f} در فصل جاری",
                    f"شاخص تهدید مستقیم دروازه {th1:.0f} و امتیاز فنی Opta BPS برابر {bps1:.0f}",
                    f"مشارکت تهاجمی با امید پاس گل {xa1:.2f} در کنار حضور {m1} دقیقه‌ای در زمین",
                ],
                "statLabel": "گل زده زنده",
                "statVal": f"{g1} گل ({g90_1:.2f}/90)",
                "blindspot": f"شاخص خلاقیت {cr1:.0f} نشان می‌دهد وابستگی به تغذیه هم‌تیمی‌ها در بازی‌های بسته بالاست" if cr1 < cr2 else f"فشار حفظ نرخ تبدیل {g1 - xg1:+.2f} در هفته‌های فشرده پیش رو",
            },
            "sideB": {
                "name": n2,
                "sub": f"{cl2} • {g2} گل در {m2} دقیقه",
                "code": cd2,
                "color": col2,
                "secondary": "#FFFFFF",
                "entityType": "person",
                "fpl_photo_code": str(p2.get("code") or ""),
                "img": img2,
                "thesis": f"ثبت {g2} گل از امید گل {xg2:.2f} با نرخ {g90_2:.2f} گل در هر ۹۰ دقیقه",
                "args": [
                    f"امید گل تجمعی {xg2:.2f} و تفاضل تمام‌کنندگی {g2 - xg2:+.2f} در فصل جاری",
                    f"شاخص تهدید مستقیم دروازه {th2:.0f} و امتیاز فنی Opta BPS برابر {bps2:.0f}",
                    f"مشارکت تهاجمی با امید پاس گل {xa2:.2f} در {m2} دقیقه بازی رسمی",
                ],
                "statLabel": "گل زده زنده",
                "statVal": f"{g2} گل ({g90_2:.2f}/90)",
                "blindspot": f"نیاز به کاهش فاصله گلزنی نسبت به صدر جدول ({g1 - g2} گل اختلاف)" if g1 > g2 else "مدیریت بار بدنی و حفظ ثبات در بازی‌های خارج از خانه",
            },
            "metrics": [
                {"label": "تعداد گل فصل", "a": _norm_score(g1, max(g1, g2, 1)), "b": _norm_score(g2, max(g1, g2, 1))},
                {"label": "امید گل (xG)", "a": _norm_score(xg1, max(xg1, xg2, 0.1)), "b": _norm_score(xg2, max(xg1, xg2, 0.1))},
                {"label": "تهدید دروازه (Threat)", "a": _norm_score(th1, max(th1, th2, 1)), "b": _norm_score(th2, max(th1, th2, 1))},
                {"label": "خلاقیت و بازی‌سازی", "a": _norm_score(cr1, max(cr1, cr2, 1)), "b": _norm_score(cr2, max(cr1, cr2, 1))},
            ],
        })

    # 2. مناظره کورس قهرمانی بین دو تیم برتر جدول زنده (بر اساس امتیاز واقعی fixtures)
    if fixtures:
        pts_map: dict[int, dict[str, float]] = {tid: {"pts": 0, "gf": 0, "ga": 0, "w": 0, "cs": 0, "mp": 0} for tid in teams}
        for fx in fixtures:
            if not fx.get("finished"):
                continue
            th_id, ta_id = fx.get("team_h"), fx.get("team_a")
            sh, sa = fx.get("team_h_score"), fx.get("team_a_score")
            if th_id not in pts_map or ta_id not in pts_map or sh is None or sa is None:
                continue
            sh, sa = int(sh), int(sa)
            pts_map[th_id]["mp"] += 1
            pts_map[ta_id]["mp"] += 1
            pts_map[th_id]["gf"] += sh
            pts_map[th_id]["ga"] += sa
            pts_map[ta_id]["gf"] += sa
            pts_map[ta_id]["ga"] += sh
            if sa == 0:
                pts_map[th_id]["cs"] += 1
            if sh == 0:
                pts_map[ta_id]["cs"] += 1
            if sh > sa:
                pts_map[th_id]["pts"] += 3
                pts_map[th_id]["w"] += 1
            elif sa > sh:
                pts_map[ta_id]["pts"] += 3
                pts_map[ta_id]["w"] += 1
            else:
                pts_map[th_id]["pts"] += 1
                pts_map[ta_id]["pts"] += 1
        ranked = sorted(
            [tid for tid, st in pts_map.items() if st["mp"] > 0],
            key=lambda tid: (pts_map[tid]["pts"], pts_map[tid]["gf"] - pts_map[tid]["ga"], pts_map[tid]["gf"]),
            reverse=True,
        )
        if len(ranked) >= 2:
            id1, id2 = ranked[0], ranked[1]
            s1, s2 = pts_map[id1], pts_map[id2]
            t1, t2 = teams[id1], teams[id2]
            c1_info = lookup_pl_club(str(t1.get("short_name") or t1.get("name") or ""))
            c2_info = lookup_pl_club(str(t2.get("short_name") or t2.get("name") or ""))
            cl1 = c1_info[0] if c1_info else str(t1.get("name") or "")
            cl2 = c2_info[0] if c2_info else str(t2.get("name") or "")
            cd1 = str(t1.get("short_name") or "T1")[:3].upper()
            cd2 = str(t2.get("short_name") or "T2")[:3].upper()
            col1, col2 = resolve_distinct_team_colors(
                c1_info[2] if c1_info else "#EF0107",
                c2_info[2] if c2_info else "#38BDF8",
            )
            xg1 = sum(float(e.get("expected_goals") or 0.0) for e in elements if e.get("team") == id1)
            xg2 = sum(float(e.get("expected_goals") or 0.0) for e in elements if e.get("team") == id2)
            gd1, gd2 = int(s1["gf"] - s1["ga"]), int(s2["gf"] - s2["ga"])
            v_a = max(40, min(65, int(round(s1["pts"] / max(1, s1["pts"] + s2["pts"]) * 100))))

            debates.append({
                "id": f"live_db_titlerace_{cd1}_{cd2}",
                "is_live": True,
                "fit_score": 98,
                "category": "لیگ برتر انگلیس • کورس قهرمانی",
                "episode": f"هفته {cur_gw} • نبرد صدرنشینان",
                "title": f"مدعی اصلی جام قهرمانی این فصل؛ {cl1} یا {cl2}؟",
                "highlight": "مدعی اصلی جام قهرمانی",
                "hotTake": f"{cl1} با {int(s1['pts'])} امتیاز و تفاضل گل {gd1:+d} در صدر جدول ایستاده، اما {cl2} با {int(s2['pts'])} امتیاز و امید گل تجمعی {xg2:.1f} سایه‌به‌سایه صدرنشین را تعقیب می‌کند.",
                "tag": f"PREMIER LEAGUE W{cur_gw} • TITLE RACE",
                "source": "Premier League / FPL Live",
                "heat": 97,
                "voteA": v_a,
                "voteTotal": "برآورد جدول زنده",
                "cta": f"جام قهرمانی به {cl1} می‌رسد یا {cl2}؟ رأیت را بنویس",
                "verdict": f"اختلاف {int(s1['pts'] - s2['pts'])} امتیازی در هفته {cur_gw} نشان می‌دهد نبرد قهرمانی بین {cl1} و {cl2} تا هفته‌های پایانی نفس‌گیر خواهد بود.",
                "radarLabels": ["امتیاز جدول", "قدرت گلزنی", "امید گل xG", "استحکام دفاع", "کلین‌شیت", "نرخ پیروزی"],
                "radarA": [
                    _norm_score(s1["pts"], max(s1["pts"], s2["pts"], 1)),
                    _norm_score(s1["gf"], max(s1["gf"], s2["gf"], 1)),
                    _norm_score(xg1, max(xg1, xg2, 0.1)),
                    _norm_score(max(1, 35 - s1["ga"]), 35),
                    _norm_score(s1["cs"], max(s1["cs"], s2["cs"], 1)),
                    _norm_score(s1["w"] / max(1, s1["mp"]), 1.0),
                ],
                "radarB": [
                    _norm_score(s2["pts"], max(s1["pts"], s2["pts"], 1)),
                    _norm_score(s2["gf"], max(s1["gf"], s2["gf"], 1)),
                    _norm_score(xg2, max(xg1, xg2, 0.1)),
                    _norm_score(max(1, 35 - s2["ga"]), 35),
                    _norm_score(s2["cs"], max(s1["cs"], s2["cs"], 1)),
                    _norm_score(s2["w"] / max(1, s2["mp"]), 1.0),
                ],
                "sideA": {
                    "name": cl1,
                    "sub": f"رتبه ۱ جدول • {int(s1['pts'])} امتیاز",
                    "code": cd1,
                    "color": col1,
                    "secondary": "#FFFFFF",
                    "entityType": "team",
                    "img": None,
                    "thesis": f"صدرنشینی مقتدرانه با {int(s1['w'])} برد و تفاضل گل {gd1:+d} در {int(s1['mp'])} مسابقه",
                    "args": [
                        f"خط حمله مؤثر با {int(s1['gf'])} گل زده و امید گل تجمعی {xg1:.1f}",
                        f"ثبت {int(s1['cs'])} کلین‌شیت و دریافت تنها {int(s1['ga'])} گل خورده",
                        f"میانگین {s1['pts'] / max(1, s1['mp']):.2f} امتیاز در هر بازی لیگ برتر",
                    ],
                    "statLabel": "امتیاز زنده جدول",
                    "statVal": f"{int(s1['pts'])} امتیاز ({gd1:+d})",
                    "blindspot": "حفظ تمرکز زیر فشار صدرنشینی و مدیریت مصدومیت‌ها در نیم‌فصل دوم",
                },
                "sideB": {
                    "name": cl2,
                    "sub": f"رتبه ۲ جدول • {int(s2['pts'])} امتیاز",
                    "code": cd2,
                    "color": col2,
                    "secondary": "#FFFFFF",
                    "entityType": "team",
                    "img": None,
                    "thesis": f"تعقیب بی‌وقفه صدر با {int(s2['w'])} برد و {int(s2['gf'])} گل زده",
                    "args": [
                        f"امید گل تجمعی {xg2:.1f} و تفاضل گل {gd2:+d} در {int(s2['mp'])} بازی",
                        f"ثبت {int(s2['cs'])} کلین‌شیت و دریافت {int(s2['ga'])} گل تا اینجای فصل",
                        f"میانگین {s2['pts'] / max(1, s2['mp']):.2f} امتیاز در هر مسابقه",
                    ],
                    "statLabel": "امتیاز زنده جدول",
                    "statVal": f"{int(s2['pts'])} امتیاز ({gd2:+d})",
                    "blindspot": f"جبران اختلاف {int(s1['pts'] - s2['pts'])} امتیازی در تقابل‌های مستقیم پیش رو",
                },
                "metrics": [
                    {"label": "امتیاز جدول زنده", "a": _norm_score(s1["pts"], max(s1["pts"], s2["pts"], 1)), "b": _norm_score(s2["pts"], max(s1["pts"], s2["pts"], 1))},
                    {"label": "گل زده فصل", "a": _norm_score(s1["gf"], max(s1["gf"], s2["gf"], 1)), "b": _norm_score(s2["gf"], max(s1["gf"], s2["gf"], 1))},
                    {"label": "امید گل تیمی (xG)", "a": _norm_score(xg1, max(xg1, xg2, 0.1)), "b": _norm_score(xg2, max(xg1, xg2, 0.1))},
                    {"label": "تعداد کلین‌شیت", "a": _norm_score(s1["cs"], max(s1["cs"], s2["cs"], 1)), "b": _norm_score(s2["cs"], max(s1["cs"], s2["cs"], 1))},
                ],
            })

    # 3. مناظره بهترین بازی‌ساز زنده فصل
    creators = sorted(
        [e for e in elements if int(e.get("minutes") or 0) >= 180 and float(e.get("creativity") or 0.0) > 10],
        key=lambda x: (float(x.get("expected_assists") or 0.0), float(x.get("creativity") or 0.0)),
        reverse=True,
    )
    if len(creators) >= 2:
        p1, p2 = creators[0], creators[1]
        t1, t2 = teams.get(p1.get("team"), {}), teams.get(p2.get("team"), {})
        c1_info = lookup_pl_club(str(t1.get("short_name") or t1.get("name") or ""))
        c2_info = lookup_pl_club(str(t2.get("short_name") or t2.get("name") or ""))
        n1 = _fa_name(f"{p1.get('first_name', '')} {p1.get('second_name', '')}".strip())
        n2 = _fa_name(f"{p2.get('first_name', '')} {p2.get('second_name', '')}".strip())
        cl1 = c1_info[0] if c1_info else str(t1.get("name") or "")
        cl2 = c2_info[0] if c2_info else str(t2.get("name") or "")
        cd1 = str(t1.get("short_name") or "CR1")[:3].upper()
        cd2 = str(t2.get("short_name") or "CR2")[:3].upper()
        col1, col2 = resolve_distinct_team_colors(
            c1_info[2] if c1_info else "#38BDF8",
            c2_info[2] if c2_info else "#F59E0B",
        )
        a1, a2 = int(p1.get("assists") or 0), int(p2.get("assists") or 0)
        xa1, xa2 = float(p1.get("expected_assists") or 0.0), float(p2.get("expected_assists") or 0.0)
        cr1, cr2 = float(p1.get("creativity") or 0.0), float(p2.get("creativity") or 0.0)
        inf1, inf2 = float(p1.get("influence") or 0.0), float(p2.get("influence") or 0.0)
        g1, g2 = int(p1.get("goals_scored") or 0), int(p2.get("goals_scored") or 0)
        m1, m2 = max(1, int(p1.get("minutes") or 1)), max(1, int(p2.get("minutes") or 1))
        img1 = f"https://resources.premierleague.com/premierleague/photos/players/250x250/p{p1['code']}.png" if p1.get("code") else None
        img2 = f"https://resources.premierleague.com/premierleague/photos/players/250x250/p{p2['code']}.png" if p2.get("code") else None

        debates.append({
            "id": f"live_db_playmaker_{p1.get('id')}_{p2.get('id')}",
            "is_live": True,
            "fit_score": 92,
            "category": "لیگ برتر انگلیس • مغزهای متفکر",
            "episode": f"هفته {cur_gw} • دوئل بازی‌سازان",
            "title": f"بهترین بازی‌ساز فصل جاری لیگ برتر؛ {n1} یا {n2}؟",
            "highlight": "بهترین بازی‌ساز",
            "hotTake": f"{n1} با امید پاس گل {xa1:.2f} و شاخص خلاقیت {cr1:.0f} پیشتاز خلق موقعیت است، اما {n2} با {a2} پاس گل و امید پاس گل {xa2:.2f} رقیب شانه به شانه اوست.",
            "tag": f"PREMIER LEAGUE W{cur_gw} • PLAYMAKER DUEL",
            "source": "Opta / FPL Live",
            "heat": 90,
            "voteA": 53,
            "voteTotal": "برآورد آماری زنده",
            "cta": f"بازی‌سازی {n1} را ترجیح می‌دهی یا {n2}؟",
            "verdict": f"هر دو بازیکن با خلق موقعیت پیوسته ({xa1:.2f} مقابل {xa2:.2f} xA) موتور تهاجمی تیم خود در فصل جاری بوده‌اند.",
            "radarLabels": ["امید پاس گل xA", "پاس گل", "خلاقیت", "اثرگذاری", "گلزنی", "ثبات دقایق"],
            "radarA": [
                _norm_score(xa1, max(xa1, xa2, 0.1)),
                _norm_score(a1, max(a1, a2, 1)),
                _norm_score(cr1, max(cr1, cr2, 1)),
                _norm_score(inf1, max(inf1, inf2, 1)),
                _norm_score(g1, max(g1, g2, 1)),
                _norm_score(m1, max(m1, m2, 1)),
            ],
            "radarB": [
                _norm_score(xa2, max(xa1, xa2, 0.1)),
                _norm_score(a2, max(a1, a2, 1)),
                _norm_score(cr2, max(cr1, cr2, 1)),
                _norm_score(inf2, max(inf1, inf2, 1)),
                _norm_score(g2, max(g1, g2, 1)),
                _norm_score(m2, max(m1, m2, 1)),
            ],
            "sideA": {
                "name": n1,
                "sub": f"{cl1} • {a1} پاس گل و {xa1:.2f} xA",
                "code": cd1,
                "color": col1,
                "secondary": "#FFFFFF",
                "entityType": "person",
                "fpl_photo_code": str(p1.get("code") or ""),
                "img": img1,
                "thesis": f"خلق موقعیت مستمر با امید پاس گل {xa1:.2f} و شاخص خلاقیت {cr1:.0f}",
                "args": [
                    f"ثبت {a1} پاس گل رسمی و {g1} گل زده در {m1} دقیقه بازی",
                    f"شاخص اثرگذاری کلی (Influence) برابر {inf1:.0f} در ترکیب {cl1}",
                    f"میانگین {xa1 * 90 / m1:.2f} امید پاس گل در هر ۹۰ دقیقه",
                ],
                "statLabel": "امید پاس گل زنده",
                "statVal": f"{xa1:.2f} xA ({a1} پاس)",
                "blindspot": "وابستگی تبدیل پاس‌های کلیدی به دقت تمام‌کنندگان خط حمله",
            },
            "sideB": {
                "name": n2,
                "sub": f"{cl2} • {a2} پاس گل و {xa2:.2f} xA",
                "code": cd2,
                "color": col2,
                "secondary": "#FFFFFF",
                "entityType": "person",
                "fpl_photo_code": str(p2.get("code") or ""),
                "img": img2,
                "thesis": f"بازی‌سازی مؤثر با امید پاس گل {xa2:.2f} و شاخص خلاقیت {cr2:.0f}",
                "args": [
                    f"ثبت {a2} پاس گل رسمی و {g2} گل زده در {m2} دقیقه بازی",
                    f"شاخص اثرگذاری کلی (Influence) برابر {inf2:.0f} در ترکیب {cl2}",
                    f"میانگین {xa2 * 90 / m2:.2f} امید پاس گل در هر ۹۰ دقیقه",
                ],
                "statLabel": "امید پاس گل زنده",
                "statVal": f"{xa2:.2f} xA ({a2} پاس)",
                "blindspot": "فشار یارگیری فشرده رقبا در نیم‌فضاهای میانی",
            },
            "metrics": [
                {"label": "امید پاس گل (xA)", "a": _norm_score(xa1, max(xa1, xa2, 0.1)), "b": _norm_score(xa2, max(xa1, xa2, 0.1))},
                {"label": "شاخص خلاقیت", "a": _norm_score(cr1, max(cr1, cr2, 1)), "b": _norm_score(cr2, max(cr1, cr2, 1))},
                {"label": "تعداد پاس گل", "a": _norm_score(a1, max(a1, a2, 1)), "b": _norm_score(a2, max(a1, a2, 1))},
                {"label": "اثرگذاری کلی", "a": _norm_score(inf1, max(inf1, inf2, 1)), "b": _norm_score(inf2, max(inf1, inf2, 1))},
            ],
        })

    return debates


def extract_news_debate_candidate(
    *,
    title: str,
    description: str,
    source_name: str,
    source_url: str = "",
    image_url: str | None = None,
    default_comp: str = "فوتبال اروپا",
) -> dict[str, Any] | None:
    """استخراج سوژه مناظره واقعی از اخبار داغ فوتبال (VAR، تقابل دو تیم، فشار سرمربی، نقل‌وانتقالات)."""
    t = _clean(title)
    d = _clean(description)
    if not t or not _is_soccer(t, d):
        return None

    low = f"{t} {d}".lower()
    # تشخیص کلیدواژه‌های مناظره و بحث داغ
    is_var = any(k in low for k in ("var", "referee", "penalty", "red card", "offside", "controversy"))
    is_mgr = any(k in low for k in ("sacked", "sack", "pressure", "under fire", "future", "should stay", "job"))
    is_transfer = any(k in low for k in ("transfer", "bid", "sign", "price tag", "worth", "release clause"))
    is_clash = any(k in low for k in (" vs ", " v ", "versus", "title race", "better", "who should", "debate", "rivals"))

    matched_clubs: list[tuple[str, str, str]] = []
    seen_codes: set[str] = set()
    for ck, cfa, ccode, ccol in _CLUB_MAP:
        if ck in low and ccode not in seen_codes:
            seen_codes.add(ccode)
            matched_clubs.append((cfa, ccode, ccol))
            if len(matched_clubs) >= 2:
                break

    score = 0
    if len(matched_clubs) == 2:
        score += 35
    if is_var or is_mgr or is_clash:
        score += 30
    elif is_transfer:
        score += 22
    if "?" in t or any(k in low for k in ("should", "could", "debate", "verdict", "why")):
        score += 20
    if image_url:
        score += 10

    if score < 48:
        return None

    hid = hashlib.sha1(f"{source_name}|{t}".encode("utf-8", errors="ignore")).hexdigest()[:10]
    img_hd = upgrade_news_image_url(image_url)

    if len(matched_clubs) == 2:
        (n1, cd1, c1), (n2, cd2, c2) = matched_clubs[0], matched_clubs[1]
        col1, col2 = resolve_distinct_team_colors(c1, c2)
        cat = f"{default_comp} • تقابل داغ"
        ep = "مناظره زنده رسانه‌ای"
        q_title = f"کدام تیم در نبرد {n1} و {n2} دست بالا را دارد؟"
        hl = f"{n1} و {n2}"
        side_a = {
            "name": n1, "sub": "برتری تاکتیکی و ساختاری", "code": cd1, "color": col1, "secondary": "#FFFFFF", "entityType": "team", "img": None,
            "thesis": f"ساختار منسجم‌تر و کنترل جریان بازی در لحظات کلیدی به سود {n1}",
            "args": [f"آمادگی بالای مهره‌های کلیدی {n1} در هفته‌های اخیر", f"برتری در مدیریت ریتم مسابقه و خلق موقعیت‌های باکیفیت", "ثبات ساختاری در فاز انتقال دفاع به حمله"],
            "statLabel": "", "statVal": "",
            "blindspot": f"آسیب‌پذیری در فضاهای پشت خط دفاعی برابر ضدحملات سریع {n2}",
        }
        side_b = {
            "name": n2, "sub": "کیفیت فردی و توان تغییر بازی", "code": cd2, "color": col2, "secondary": "#FFFFFF", "entityType": "team", "img": None,
            "thesis": f"کیفیت فردی و توان تغییر جریان مسابقه در لحظات حساس به سود {n2}",
            "args": [f"انگیزه بالا و تهدید مستقیم دروازه از سوی خط حمله {n2}", "توانایی بهره‌برداری از اشتباهات فردی و ضربات ایستگاهی", "شخصیت تیمی در بازی‌های بزرگ و پرفشار"],
            "statLabel": "", "statVal": "",
            "blindspot": f"چالش مهار پرس از بالای {n1} در نیمه اول مسابقه",
        }
        radar_labels = ["انسجام تیمی", "کیفیت فردی", "فاز هجومی", "ساختار دفاعی", "فرم اخیر", "فشار روانی"]
        radar_a, radar_b = [88, 86, 89, 85, 87, 84], [84, 88, 86, 82, 85, 87]
        metrics = [
            {"label": "کنترل میانه میدان", "a": 88, "b": 82},
            {"label": "تهدید در انتقال سریع", "a": 84, "b": 89},
            {"label": "ثبات دفاعی", "a": 86, "b": 81},
            {"label": "آمادگی روحی", "a": 85, "b": 87},
        ]
        verdict = f"گزارش زنده {source_name} تقابل {n1} و {n2} را به یکی از داغ‌ترین بحث‌های روز فوتبال اروپا تبدیل کرده است."
    elif is_var:
        club_lbl = matched_clubs[0][0] if matched_clubs else default_comp
        cat = f"{default_comp} • جنجال داوری و VAR"
        ep = "دادگاه داوری زنده"
        q_title = f"جنجال داوری در {club_lbl}؛ تصمیم درست قانون یا اشتباه پرهزینه؟"
        hl = "جنجال داوری"
        side_a = {
            "name": "موافق تصمیم داور", "sub": "انطباق با پروتکل VAR و قانون", "code": "PRO", "color": "#38BDF8", "secondary": "#FFFFFF", "entityType": "stance", "img": None,
            "thesis": "تصمیم داور مطابق متن صریح قانون و بازبینی تصاویر VAR بوده است",
            "args": ["شفافیت پروتکل داوری در صحنه‌های حساس محوطه جریمه", "اولویت اجرای یکسان قانون بر هیجان لحظه‌ای سکوها", "کاهش خطای آشکار انسانی با تکیه بر بازبینی ویدیویی"],
            "statLabel": "شدت واکنش", "statVal": "داغ و جنجالی",
            "blindspot": "تفسیرپذیری برخی صحنه‌های ۵۰-۵۰ حتی با بازبینی چندباره",
        }
        side_b = {
            "name": "منتقد تصمیم داور", "sub": "اعتراض به ریتم و تفسیر سخت‌گیرانه", "code": "CON", "color": "#E62E45", "secondary": "#FFFFFF", "img": None,
            "thesis": "تفسیر بیش‌ازحد سخت‌گیرانه روح طبیعی فوتبال و عدالت بازی را مخدوش کرد",
            "args": ["تغییر سرنوشت نتیجه با یک تصمیم میلیمتری و بحث‌برانگیز", "نبود یکنواختی در تصمیم‌های مشابه طی هفته‌های اخیر", "توقف طولانی مسابقه و افت تمرکز بازیکنان"],
            "statLabel": "موج انتقادات", "statVal": "بالا",
            "blindspot": "نبود راهکار جایگزین بدون خطا برای صحنه‌های سریع محوطه",
        }
        radar_labels = ["انطباق قانون", "عدالت ورزشی", "حفظ ریتم", "شفافیت", "اجماع کارشناسی", "تأثیر بر نتیجه"]
        radar_a, radar_b = [89, 78, 56, 82, 70, 92], [65, 86, 91, 74, 80, 90]
        metrics = [
            {"label": "انطباق با متن قانون", "a": 88, "b": 64},
            {"label": "حفظ ریتم مسابقه", "a": 54, "b": 90},
            {"label": "پذیرش میان هواداران", "a": 58, "b": 84},
            {"label": "تأثیر مستقیم بر جدول", "a": 91, "b": 89},
        ]
        verdict = f"بحث داغ داوری که در {source_name} بازتاب گسترده‌ای داشته، دوباره استانداردهای VAR را زیر ذره‌بین برده است."
    else:
        club_lbl = matched_clubs[0][0] if matched_clubs else default_comp
        cd = matched_clubs[0][1] if matched_clubs else "XGP"
        cat = f"{default_comp} • پرونده داغ روز"
        ep = "مناظره زنده رسانه‌ای"
        q_title = f"چالش بزرگ در {club_lbl}؛ تداوم مسیر فعلی یا تغییر فوری؟"
        hl = "چالش بزرگ"
        side_a = {
            "name": "حمایت از ثبات", "sub": f"تداوم پروژه در {club_lbl}", "code": cd, "color": "#10B981", "secondary": "#FFFFFF", "entityType": "team", "img": None,
            "thesis": "ثبات فنی و اعتماد به پروژه میان‌مدت تنها مسیر بازگشت به اوج است",
            "args": ["تغییرات شتاب‌زده در میانه فصل معمولاً بحران را عمیق‌تر می‌کند", "شاخص‌های زیربنایی تیم ظرفیت بهبود در هفته‌های آینده را دارد", "نیاز به زمان برای هماهنگی کامل ترکیب و ایده‌های تاکتیکی"],
            "statLabel": "رویکرد تحلیلی", "statVal": "پروژه بلندمدت",
            "blindspot": "کمبود صبر هواداران و فشار شدید جدول در صورت تداوم افت نتایج",
        }
        side_b = {
            "name": "ضرورت تغییر فوری", "sub": "شوک فنی و بازنگری سریع", "code": "CHG", "color": "#E62E45", "secondary": "#FFFFFF", "img": None,
            "thesis": "برای نجات فصل، تصمیم قاطع و تغییر رویکرد پیش از دیر شدن ضروری است",
            "args": ["افت محسوس نتایج و کاهش اعتمادبه‌نفس تیم در بازی‌های حساس", "فرصت محدود جدول برای جبران امتیازات ازدست‌رفته", "نیاز به شوک روانی و اصلاح فوری ساختار تاکتیکی"],
            "statLabel": "فشار رسانه‌ای", "statVal": "بحرانی",
            "blindspot": "ریسک نبود گزینه جایگزین آماده و هزینه‌های سنگین تغییر میانه فصل",
        }
        radar_labels = ["ثبات ساختاری", "نتیجه‌گیری فوری", "حمایت رختکن", "ریسک مالی", "فشار هواداران", "آینده‌نگری"]
        radar_a, radar_b = [90, 62, 82, 85, 58, 92], [58, 86, 68, 60, 90, 65]
        metrics = [
            {"label": "شانس موفقیت کوتاه‌مدت", "a": 62, "b": 85},
            {"label": "ثبات و آینده‌نگری", "a": 90, "b": 58},
            {"label": "همراهی افکار عمومی", "a": 56, "b": 84},
            {"label": "منطق اقتصادی باشگاه", "a": 86, "b": 60},
        ]
        verdict = f"پرونده داغ {club_lbl} به نقل از {source_name} دو نگاه کاملاً متضاد را میان هواداران و کارشناسان شکل داده است."

    return {
        "id": f"live_db_news_{hid}",
        "is_live": True,
        "fit_score": min(95, score),
        "category": cat,
        "episode": ep,
        "title": q_title,
        "highlight": hl,
        "hotTake": f"{t}. {d[:140]}".strip(),
        "tag": f"{source_name.upper()} • LIVE DEBATE",
        "source": source_name,
        "source_url": source_url,
        "heat": min(96, max(76, score + 14)),
        "voteA": 52,
        "voteTotal": "نظرسنجی زنده XGPedia",
        "cta": "تو کدام جبهه را انتخاب می‌کنی؟ نظرت را بنویس",
        "verdict": verdict,
        "radarLabels": radar_labels,
        "radarA": radar_a,
        "radarB": radar_b,
        "sideA": side_a,
        "sideB": side_b,
        "metrics": metrics,
    }


def _fetch_news_debates(timeout: float = 6.0) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    # RSS
    for src_name, url in _DEBATE_RSS_FEEDS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml,application/xml,text/xml"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read(450_000)
            root = ET.fromstring(raw)
            for it in root.findall(".//item")[:22]:
                title = (it.findtext("title") or "").strip()
                desc = (it.findtext("description") or "").strip()
                link = (it.findtext("link") or "").strip()
                img = None
                for ch in it:
                    tg = ch.tag.lower()
                    if tg.endswith(("thumbnail", "content")) or tg == "enclosure":
                        u = ch.attrib.get("url")
                        if u and u.startswith("http"):
                            img = u
                            break
                cand = extract_news_debate_candidate(title=title, description=desc, source_name=src_name, source_url=link, image_url=img)
                if cand:
                    out.append(cand)
        except Exception as e:
            log.warning("Debate RSS failed (%s): %s", src_name, e)
    # ESPN Soccer
    for slug, comp_fa in _DEBATE_ESPN_FEEDS:
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/news?limit=15"
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read(450_000).decode("utf-8", errors="replace"))
            for art in (data.get("articles") or [])[:15]:
                if not isinstance(art, dict):
                    continue
                title = str(art.get("headline") or "").strip()
                desc = str(art.get("description") or "").strip()
                links = art.get("links") or {}
                link = str(((links.get("web") or {}).get("href")) or "") if isinstance(links, dict) else ""
                imgs = art.get("images") or []
                img = str(imgs[0].get("url") or "") if (isinstance(imgs, list) and imgs and isinstance(imgs[0], dict)) else None
                cand = extract_news_debate_candidate(
                    title=title, description=desc, source_name="ESPN Soccer", source_url=link, image_url=img, default_comp=comp_fa,
                )
                if cand:
                    out.append(cand)
        except Exception as e:
            log.warning("Debate ESPN failed (%s): %s", slug, e)
    return out


def fetch_live_debate_items(*, force_refresh: bool = False, max_items: int = 10) -> list[dict[str, Any]]:
    """جستجوی زنده و پیشنهاد برترین مناظره‌های واقعی فوتبال (ترکیب FPL داده‌محور + اخبار داغ)."""
    now = time.time()
    if not force_refresh and _DEBATE_CACHE["items"] and (now - _DEBATE_CACHE["ts"]) < _CACHE_TTL_SEC:
        return [dict(x) for x in _DEBATE_CACHE["items"]]

    items: list[dict[str, Any]] = []
    items.extend(build_fpl_live_debates())
    items.extend(_fetch_news_debates())

    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for it in sorted(items, key=lambda x: (int(x.get("fit_score") or 0), int(x.get("heat") or 0)), reverse=True):
        k = str(it.get("title") or "").strip().lower()[:45]
        if not k or k in seen:
            continue
        seen.add(k)
        uniq.append(it)
        if len(uniq) >= max_items:
            break

    if uniq:
        _DEBATE_CACHE["ts"] = now
        _DEBATE_CACHE["items"] = [dict(x) for x in uniq]
    return uniq


def list_all_debate_items(*, include_live: bool = True, force_refresh: bool = False) -> dict[str, list[dict[str, Any]]]:
    """برگرداندن جداگانه مناظره‌های زنده و پریست‌ها."""
    presets = load_debate_presets()
    live = fetch_live_debate_items(force_refresh=force_refresh) if include_live else []
    return {"live": live, "presets": presets}


def _download_img_uri(url: str | None, timeout: float = 6.0) -> str | None:
    u = str(url or "").strip()
    if not u:
        return None
    if u.startswith("data:image/"):
        return u
    if not u.startswith(("http://", "https://")):
        return None
    try:
        req = urllib.request.Request(u, headers={"User-Agent": USER_AGENT, "Accept": "image/*,*/*;q=0.8"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(3 * 1024 * 1024)
            if len(raw) < 1200:
                return None
            ct = str(resp.headers.get("Content-Type") or "image/png").split(";")[0].strip().lower()
            if not ct.startswith("image/"):
                ct = "image/png"
            return f"data:{ct};base64,{base64.b64encode(raw).decode('ascii')}"
    except Exception:
        return None


def hydrate_debate_item(item: dict[str, Any]) -> dict[str, Any]:
    """تکمیل نهایی آیتم مناظره پیش از رندر آفلاین (لوگوی واقعی تیم‌ها، پرتره دقیق اشخاص و ترجمه فارسی)."""
    from src.xgpedia.providers.player_profile_free import PL_PHOTO_URLS
    out = json.loads(json.dumps(item, ensure_ascii=False))
    for side_key in ("sideA", "sideB"):
        side = out.get(side_key)
        if not isinstance(side, dict):
            continue
        ent_type = str(side.get("entityType") or "").lower()
        # اگر طرف مناظره تیم/باشگاه باشد هرگز عکس خبری اشتباه روی آن گذاشته نشود (باید لوگوی باشگاه نمایش داده شود)
        if ent_type == "team" or (not ent_type and lookup_pl_club(str(side.get("name") or "")) is not None):
            side["entityType"] = "team"
            side["img"] = None
            continue
        # برای اشخاص (بازیکنان/مربیان): دانلود عکس دقیق با پشتیبان چندمسیره PL_PHOTO_URLS
        pcode = str(side.get("fpl_photo_code") or "").strip()
        img_u = str(side.get("img") or "").strip()
        if img_u.startswith(("http://", "https://")):
            dl = _download_img_uri(img_u)
            if not dl and pcode:
                for tmpl in PL_PHOTO_URLS:
                    dl = _download_img_uri(tmpl.format(code=pcode))
                    if dl:
                        break
            side["img"] = dl
        elif not img_u and pcode:
            for tmpl in PL_PHOTO_URLS:
                dl = _download_img_uri(tmpl.format(code=pcode))
                if dl:
                    side["img"] = dl
                    break
    ht = str(out.get("hotTake") or "").strip()
    if ht and _looks_mostly_english(ht):
        try:
            from src.xgpedia.editorial.llm_provider import generate_text
            res = generate_text(
                f"این ادعای داغ فوتبالی را به فارسی روان و مجله‌ای در حداکثر ۲ جمله ترجمه کن:\n{ht}",
                max_tokens=180,
            )
            if res and len(res.strip()) >= 15 and not _looks_mostly_english(res):
                out["hotTake"] = res.strip().strip('"\'«»')
        except Exception:
            pass
    return out
