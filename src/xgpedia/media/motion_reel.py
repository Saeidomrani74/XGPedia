"""موتور موشن‌گرافیک پویا و فریم‌به‌فریم XGPedia (`Kinetic Motion Studio — 9:16 Reels/Shorts`).

برخلاف اسلایدشوهای ثابت، تمام المان‌ها در یک صحنهٔ HTML5/SVG/JS با ساعت دقیق `window.__setTime(t)`
به شکل کاملاً متحرک، با انیمیشن فنری (Spring)، شمارندهٔ زندهٔ اعداد، نوارهای پیشرفت متحرک،
حرکت دوربین و اینترو/اوتروی امضادار با لوگوی رسمی XGPedia فریم‌به‌فریم رندر و مستقیم به FFmpeg پایپ می‌شوند.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from src.xgpedia.config import ROOT
from src.xgpedia.render.card_kit.helpers import esc
from src.xgpedia.render.cards import _brand_logo_data_uri
from src.xgpedia.render.studio_engine import build_embedded_font_css


def _red_emblem_data_uri() -> str:
    p = ROOT / "brand" / "logo" / "svg" / "logo-xg-red.svg"
    if p.exists():
        return "data:image/svg+xml;base64," + base64.b64encode(p.read_bytes()).decode("ascii")
    return _brand_logo_data_uri() or ""


def _club_crest_uri(code: str, name: str = "") -> str:
    cd = str(code or "").strip().upper()[:3]
    if not cd or cd == "XGP":
        return ""
    try:
        from src.xgpedia.providers.pl_badges_free import get_pl_badge_data_uri, lookup_pl_club
        info = lookup_pl_club(name or cd, tla_hint=cd)
        if info and info[4]:
            return get_pl_badge_data_uri(info[1], tla_hint=info[1], badge_code=info[4], size=100, fetch_network=False) or ""
    except Exception:
        pass
    return ""


def extract_motion_story(card_kind: str, item: dict[str, Any]) -> dict[str, Any]:
    """استخراج ساختار داستانیِ متحرک (تیتر، قهرمان، ۳ تا ۴ متریک شمارنده‌دار، نوارها و جمع‌بندی) از هر نوع کارت."""
    story: dict[str, Any] = {
        "kicker": "تحلیل زنده XGPedia",
        "headline": "گزارش ویژه فوتبال اروپا",
        "subline": "داده‌های واقعی و تحلیل تاکتیکی",
        "accent": "#E62E45",
        "accent2": "#38BDF8",
        "photo": "",
        "crest": "",
        "quote_or_body": "",
        "metrics": [],   # [{"label": "...", "target": 42.5, "prefix": "", "suffix": "", "decimals": 1, "pct": 85}]
        "bars": [],      # [{"label": "...", "val_text": "...", "pct": 82, "color": "#10B981"}]
        "verdict": "",
        "cta": "نظر تو چیه؟ تو کامنت بنویس 👇",
    }

    if card_kind == "quote":
        story["kicker"] = f"نقل‌قول روز • {item.get('competition') or 'فوتبال اروپا'}"
        story["headline"] = str(item.get("speaker") or "نقل‌قول روز")
        story["subline"] = str(item.get("role") or item.get("match") or "واکنش رسانه‌ای")
        story["accent"] = str(item.get("color") or "#E62E45")
        story["photo"] = str(item.get("photoSrc") or "")
        story["crest"] = _club_crest_uri(str(item.get("clubCode") or ""))
        story["quote_or_body"] = str(item.get("quote") or "").replace("*", "")
        for st in (item.get("stats") or [])[:3]:
            val_s = str(st.get("val") or "")
            num = _parse_first_float(val_s)
            story["metrics"].append({
                "label": str(st.get("label") or "آمار"),
                "target": num if num is not None else 0,
                "raw": val_s,
                "decimals": 1 if ("." in val_s and num is not None) else 0,
                "pct": min(96, max(28, int((num or 50) % 100))),
            })
        story["verdict"] = f"منبع: {item.get('source') or 'XGPedia'} • {item.get('match') or ''}"

    elif card_kind == "value_radar":
        players = sorted(item.get("players") or [], key=lambda x: float(x.get("ev_score") or 0), reverse=True)
        top1 = players[0] if players else {}
        story["kicker"] = f"رادار ارزش بازار (+EV) • {item.get('competition') or 'لیگ برتر'}"
        story["headline"] = str(item.get("title") or "شکارهای طلایی بازار")
        story["subline"] = f"شکار برتر: {top1.get('name', '')} ({top1.get('club', '')})"
        story["accent"] = "#10B981"
        story["accent2"] = "#E62E45"
        story["crest"] = _club_crest_uri(str(top1.get("club_code") or ""), str(top1.get("club") or ""))
        story["quote_or_body"] = str(item.get("editorial_verdict") or "")
        if top1:
            story["metrics"] = [
                {"label": "شاخص +EV", "target": float(top1.get("ev_score") or 0), "prefix": "+", "decimals": 1, "pct": 94},
                {"label": "قیمت بازار", "target": float(top1.get("price") or 0), "prefix": "£", "suffix": "M", "decimals": 1, "pct": 52},
                {"label": "امید گل+پاس / ۹۰", "target": float(top1.get("xgi90") or 0), "decimals": 2, "pct": 86},
            ]
        max_ev = max((float(p.get("ev_score") or 1) for p in players[:4]), default=12.0)
        for p in players[:4]:
            ev = float(p.get("ev_score") or 0)
            story["bars"].append({
                "label": f"{p.get('name', '')} (£{float(p.get('price') or 0):.1f}M)",
                "val_text": f"+{ev:.1f} EV",
                "pct": min(100, max(25, round((ev / max(1.0, max_ev)) * 100))),
                "color": "#10B981",
            })
        story["verdict"] = str(item.get("editorial_verdict") or "")

    elif card_kind == "lineup_injuries":
        h, a = item.get("home") or {}, item.get("away") or {}
        story["kicker"] = f"ترکیب احتمالی و غایبان • {item.get('competition') or 'لیگ برتر'}"
        story["headline"] = f"{h.get('name', 'میزبان')} × {a.get('name', 'میهمان')}"
        story["subline"] = f"چیدمان {h.get('formation', '4-3-3')} در برابر {a.get('formation', '4-2-3-1')}"
        story["accent"] = str(h.get("color") or "#E62E45")
        story["accent2"] = str(a.get("color") or "#38BDF8")
        story["crest"] = _club_crest_uri(str(h.get("code") or ""), str(h.get("name") or ""))
        story["quote_or_body"] = str(item.get("editorial_verdict") or "")
        story["metrics"] = [
            {"label": f"آمادگی {h.get('name', 'میزبان')}", "target": int(h.get("availability_pct") or 85), "suffix": "%", "decimals": 0, "pct": int(h.get("availability_pct") or 85)},
            {"label": f"آمادگی {a.get('name', 'میهمان')}", "target": int(a.get("availability_pct") or 85), "suffix": "%", "decimals": 0, "pct": int(a.get("availability_pct") or 85)},
            {"label": "کل غایبان دو تیم", "target": len(h.get("absentees") or []) + len(a.get("absentees") or []), "decimals": 0, "pct": 65},
        ]
        for ab in ((h.get("absentees") or [])[:2] + (a.get("absentees") or [])[:2]):
            ch = int(ab.get("chance") or 0)
            story["bars"].append({
                "label": f"{ab.get('name', '')} ({ab.get('pos_fa', '')})",
                "val_text": str(ab.get("status_fa") or "غایب"),
                "pct": max(15, ch),
                "color": "#EF4444" if ch == 0 else ("#F59E0B" if ch <= 50 else "#10B981"),
            })
        story["verdict"] = str(item.get("editorial_verdict") or "")

    elif card_kind == "shotmap_xg":
        h, a = item.get("home") or {}, item.get("away") or {}
        story["kicker"] = f"نقشه شوت و امید گل • {item.get('competition') or 'فوتبال اروپا'}"
        story["headline"] = f"{h.get('name', '')} {h.get('score', 0)} - {a.get('score', 0)} {a.get('name', '')}"
        story["subline"] = f"امید گل: {float(h.get('xg') or 0):.2f} در برابر {float(a.get('xg') or 0):.2f}"
        story["accent"] = "#E62E45"
        story["accent2"] = "#38BDF8"
        story["crest"] = _club_crest_uri(str(h.get("code") or ""), str(h.get("name") or ""))
        story["quote_or_body"] = str(item.get("editorialVerdict") or "")
        story["metrics"] = [
            {"label": f"امید گل {h.get('name', '')}", "target": float(h.get("xg") or 0), "decimals": 2, "pct": min(98, int(float(h.get("xg") or 0) * 35))},
            {"label": f"امید گل {a.get('name', '')}", "target": float(a.get("xg") or 0), "decimals": 2, "pct": min(98, int(float(a.get("xg") or 0) * 35))},
            {"label": "مجموع شوت‌ها", "target": len(item.get("shots") or []), "decimals": 0, "pct": 78},
        ]
        story["bars"] = [
            {"label": f"شوت {h.get('name', '')}", "val_text": f"{float(h.get('xg') or 0):.2f} xG", "pct": 80, "color": "#E62E45"},
            {"label": f"شوت {a.get('name', '')}", "val_text": f"{float(a.get('xg') or 0):.2f} xG", "pct": 62, "color": "#38BDF8"},
        ]
        story["verdict"] = str(item.get("editorialVerdict") or "")

    elif card_kind == "debate":
        sa, sb = item.get("sideA") or {}, item.get("sideB") or {}
        story["kicker"] = f"مناظره روز • {item.get('competition') or 'فوتبال اروپا'}"
        story["headline"] = str(item.get("title") or f"{sa.get('name', '')} یا {sb.get('name', '')}؟")
        story["subline"] = f"{sa.get('name', '')} در برابر {sb.get('name', '')}"
        story["quote_or_body"] = str(item.get("verdict") or "")
        story["metrics"] = [
            {"label": str(sa.get("name") or "طرف اول"), "target": 52, "suffix": "%", "decimals": 0, "pct": 52},
            {"label": str(sb.get("name") or "طرف دوم"), "target": 48, "suffix": "%", "decimals": 0, "pct": 48},
        ]
        story["verdict"] = str(item.get("cta") or "تو طرف کدومی؟ تو کامنت بنویس 👇")

    elif card_kind == "number_of_day":
        num_v = _parse_first_float(str(item.get("number") or "0")) or 0
        story["kicker"] = "عدد روز XGPedia"
        story["headline"] = str(item.get("headline") or item.get("subject") or "آمار ویژه امروز")
        story["subline"] = f"{item.get('number', '')}{item.get('suffix', '')} {item.get('unit', '')}"
        story["quote_or_body"] = str(item.get("body") or "")
        story["metrics"] = [
            {"label": str(item.get("unit") or "عدد شاخص"), "target": num_v, "suffix": str(item.get("suffix") or ""), "decimals": 1 if "." in str(item.get("number") or "") else 0, "pct": 92},
        ]
        story["verdict"] = str(item.get("subject") or "")

    else:
        # پشتیبانی هوشمند از تمام کارت‌های دیگر (خلاصه هفته، جدول، گلزنان، نتایج، H2H و...)
        story["kicker"] = f"استودیو XGPedia • {item.get('competition') or 'فوتبال اروپا'}"
        story["headline"] = str(item.get("title") or item.get("round") or item.get("name") or "گزارش تحلیلی روز")
        story["subline"] = str(item.get("subtitle") or item.get("season") or "آمار زنده و بررسی تاکتیکی")
        story["quote_or_body"] = str(item.get("editorialVerdict") or item.get("editorial_verdict") or item.get("verdict") or "")
        story["verdict"] = str(item.get("source") or "XGPedia Live Analytics")

    if not story["metrics"]:
        story["metrics"] = [
            {"label": "دقت داده زنده", "target": 100, "suffix": "%", "decimals": 0, "pct": 100},
            {"label": "تحلیل تاکتیکی", "target": 90, "suffix": "′", "decimals": 0, "pct": 90},
        ]
    return story


def _parse_first_float(s: str) -> float | None:
    import re
    m = re.search(r"-?\d+(?:\.\d+)?", str(s or "").replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def render_kinetic_motion_html(
    card_kind: str,
    item: dict[str, Any],
    *,
    width: int = 1080,
    height: int = 1920,
    duration_sec: float = 14.0,
) -> str:
    """تولید صفحهٔ HTML5/SVG/JS موشن‌گرافیک ۱۰۰٪ آفلاین با ساعت دقیق `window.__setTime(t)`."""
    story = extract_motion_story(card_kind, item)
    logo_uri = _brand_logo_data_uri() or ""
    emblem_uri = _red_emblem_data_uri()
    story_json = json.dumps(story, ensure_ascii=False)
    font_css = build_embedded_font_css()

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8"/>
<style>
{font_css}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:{width}px;height:{height}px;overflow:hidden;background:#081022;color:#F8FAFC;font-family:'Vazirmatn',sans-serif}}
#stage{{position:relative;width:{width}px;height:{height}px;overflow:hidden;background:#081022}}
.bg-grid{{position:absolute;inset:-120px;background-image:linear-gradient(rgba(255,255,255,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.045) 1px,transparent 1px);background-size:64px 64px;will-change:transform}}
.orb{{position:absolute;border-radius:999px;filter:blur(95px);pointer-events:none;will-change:transform,opacity}}
.laser{{position:absolute;height:4px;border-radius:99px;background:linear-gradient(90deg,transparent,#E62E45,#38BDF8,transparent);pointer-events:none;will-change:transform,opacity}}
.crn{{position:absolute;width:36px;height:36px;pointer-events:none;z-index:40}}
.c-tl{{top:26px;left:26px;border-top:4px solid #E62E45;border-left:4px solid #E62E45;border-top-left-radius:10px}}
.c-tr{{top:26px;right:26px;border-top:4px solid #E62E45;border-right:4px solid #E62E45;border-top-right-radius:10px}}
.c-bl{{bottom:26px;left:26px;border-bottom:4px solid #E62E45;border-left:4px solid #E62E45;border-bottom-left-radius:10px}}
.c-br{{bottom:26px;right:26px;border-bottom:4px solid #E62E45;border-right:4px solid #E62E45;border-bottom-right-radius:10px}}
.wm-corner{{position:absolute;top:52px;left:54px;z-index:35;display:flex;align-items:center;gap:12px;opacity:0}}
.wm-corner img{{height:46px;width:auto;filter:drop-shadow(0 6px 18px rgba(0,0,0,.6))}}
.prog-bar{{position:absolute;bottom:0;left:0;height:8px;background:linear-gradient(90deg,#E62E45,#38BDF8,#10B981);z-index:50;width:0%}}
.scene{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:120px 64px;opacity:0;pointer-events:none}}
/* Act 1: Intro */
.intro-ring{{width:340px;height:340px;border-radius:999px;border:3px solid rgba(230,46,69,.55);display:flex;align-items:center;justify-content:center;box-shadow:0 0 90px rgba(230,46,69,.35),inset 0 0 60px rgba(56,189,248,.18)}}
.intro-logo{{height:120px;width:auto;filter:drop-shadow(0 14px 36px rgba(230,46,69,.55))}}
.intro-tag{{margin-top:44px;padding:14px 36px;border-radius:999px;background:rgba(230,46,69,.18);border:2px solid rgba(230,46,69,.7);font-size:30px;font-weight:900;color:#fff;letter-spacing:-.01em}}
.intro-line{{margin-top:24px;height:5px;width:0px;border-radius:99px;background:linear-gradient(90deg,#E62E45,#38BDF8)}}
/* Act 2: Hero */
.hero-photo-wrap{{position:absolute;top:0;left:0;right:0;height:54%;overflow:hidden}}
.hero-photo{{width:100%;height:100%;object-fit:cover;object-position:50% 20%;will-change:transform}}
.hero-vig{{position:absolute;inset:0;background:linear-gradient(180deg,rgba(8,16,34,.55) 0%,rgba(8,16,34,.12) 28%,rgba(8,16,34,.82) 78%,#081022 100%)}}
.hero-card{{position:relative;z-index:5;width:100%;margin-top:auto;margin-bottom:80px;display:flex;flex-direction:column;gap:24px}}
.kicker-pill{{display:inline-flex;align-items:center;gap:12px;padding:10px 26px;border-radius:999px;background:rgba(15,23,42,.88);border:1.5px solid rgba(230,46,69,.65);font-size:24px;font-weight:900;color:#F8FAFC;width:fit-content}}
.hero-title{{font-size:66px;font-weight:900;line-height:1.25;color:#fff;text-shadow:0 12px 36px rgba(0,0,0,.7)}}
.hero-sub{{font-size:32px;font-weight:700;color:#CBD5E1}}
.hero-quote{{margin-top:12px;padding:30px 34px;border-radius:26px;background:rgba(15,23,42,.86);border-right:8px solid #E62E45;font-size:38px;font-weight:900;line-height:1.55;color:#fff;box-shadow:0 24px 60px rgba(0,0,0,.55)}}
.crest-badge{{width:128px;height:128px;border-radius:28px;background:rgba(15,23,42,.86);border:2px solid rgba(255,255,255,.22);padding:14px;display:flex;align-items:center;justify-content:center;box-shadow:0 20px 50px rgba(0,0,0,.6)}}
.crest-badge img{{width:100%;height:100%;object-fit:contain}}
/* Act 3: Animated Metrics & Bars */
.m-grid{{width:100%;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;margin-top:26px}}
.m-card{{background:rgba(15,23,42,.86);border:1.5px solid rgba(56,189,248,.38);border-radius:26px;padding:30px 18px;text-align:center;box-shadow:0 18px 46px rgba(0,0,0,.5)}}
.m-val{{font-family:'Space Grotesk','Vazirmatn',sans-serif;font-size:56px;font-weight:900;color:#34D399}}
.m-lbl{{font-size:22px;font-weight:800;color:#CBD5E1;margin-top:10px}}
.bars-wrap{{width:100%;display:flex;flex-direction:column;gap:20px;margin-top:34px}}
.b-item{{background:rgba(15,23,42,.84);border:1px solid rgba(255,255,255,.12);border-radius:22px;padding:22px 26px}}
.b-top{{display:flex;justify-content:space-between;align-items:center;font-size:26px;font-weight:900;margin-bottom:14px}}
.b-track{{height:18px;border-radius:999px;background:rgba(255,255,255,.1);overflow:hidden}}
.b-fill{{height:100%;border-radius:999px;width:0%}}
/* Act 4: Verdict */
.verdict-box{{width:100%;padding:42px 38px;border-radius:30px;background:linear-gradient(145deg,rgba(230,46,69,.22),rgba(15,23,42,.92));border:2px solid rgba(230,46,69,.55);font-size:38px;font-weight:900;line-height:1.6;text-align:center;color:#fff;box-shadow:0 28px 70px rgba(0,0,0,.6)}}
.cta-pill{{margin-top:40px;padding:18px 42px;border-radius:999px;background:#E62E45;font-size:30px;font-weight:900;color:#fff;box-shadow:0 14px 40px rgba(230,46,69,.55)}}
/* Act 5: Outro */
.outro-handle{{margin-top:32px;font-family:'Space Grotesk',sans-serif;font-size:52px;font-weight:900;color:#fff;letter-spacing:.04em}}
.outro-sub{{margin-top:14px;font-size:28px;font-weight:800;color:#94A3B8}}
</style>
</head>
<body>
<div id="stage">
  <div id="bgGrid" class="bg-grid"></div>
  <div id="orb1" class="orb" style="width:520px;height:520px;background:rgba(230,46,69,.32);top:-80px;right:-80px"></div>
  <div id="orb2" class="orb" style="width:560px;height:560px;background:rgba(56,189,248,.26);bottom:-120px;left:-100px"></div>
  <div id="laser1" class="laser" style="width:900px;top:240px;left:-900px"></div>
  <div id="laser2" class="laser" style="width:900px;bottom:280px;right:-900px"></div>

  <div class="crn c-tl"></div><div class="crn c-tr"></div><div class="crn c-bl"></div><div class="crn c-br"></div>
  <div id="wmCorner" class="wm-corner">
    {f'<img src="{logo_uri}" alt="XGPedia"/>' if logo_uri else '<span style="font-size:32px;font-weight:900;color:#E62E45">XGPedia</span>'}
  </div>
  <div id="progBar" class="prog-bar"></div>

  <!-- ACT 1: Signature Intro (0.0s - 1.8s) -->
  <div id="scIntro" class="scene">
    <div id="introRing" class="intro-ring">
      {f'<img src="{emblem_uri}" class="intro-logo" alt="XGPedia"/>' if emblem_uri else '<div style="font-size:64px;font-weight:900;color:#E62E45">XG</div>'}
    </div>
    <div id="introTag" class="intro-tag">{esc(story["kicker"])}</div>
    <div id="introLine" class="intro-line"></div>
  </div>

  <!-- ACT 2: Kinetic Hero (1.8s - 5.6s) -->
  <div id="scHero" class="scene" style="justify-content:flex-end;align-items:flex-start;padding:130px 58px">
    <div id="heroPhotoWrap" class="hero-photo-wrap" style="display:none">
      <img id="heroPhoto" class="hero-photo" src="" alt=""/>
      <div class="hero-vig"></div>
    </div>
    <div class="hero-card">
      <div id="heroCrest" class="crest-badge" style="display:none"><img id="heroCrestImg" src="" alt=""/></div>
      <div id="heroKicker" class="kicker-pill">{esc(story["kicker"])}</div>
      <div id="heroTitle" class="hero-title">{esc(story["headline"])}</div>
      <div id="heroSub" class="hero-sub">{esc(story["subline"])}</div>
      <div id="heroQuote" class="hero-quote" style="display:none"></div>
    </div>
  </div>

  <!-- ACT 3: Animated Metrics & Bars (5.6s - 10.6s) -->
  <div id="scData" class="scene" style="align-items:stretch;justify-content:center;padding:150px 54px">
    <div id="dataHdr" class="kicker-pill" style="margin-bottom:14px">📊 داده‌های کلیدی و تحلیل زنده</div>
    <div id="dataTitle" style="font-size:46px;font-weight:900;color:#fff;margin-bottom:10px">{esc(story["headline"])}</div>
    <div id="mGrid" class="m-grid"></div>
    <div id="barsWrap" class="bars-wrap"></div>
  </div>

  <!-- ACT 4: Verdict & CTA (10.6s - 12.6s) -->
  <div id="scVerdict" class="scene">
    <div id="vKicker" class="kicker-pill" style="margin-bottom:32px">⚡ جمع‌بندی تحریریه XGPedia</div>
    <div id="verdictBox" class="verdict-box"></div>
    <div id="ctaPill" class="cta-pill">{esc(story["cta"])}</div>
  </div>

  <!-- ACT 5: Signature Outro (12.6s - 14.0s) -->
  <div id="scOutro" class="scene">
    <div id="outroRing" class="intro-ring" style="width:360px;height:360px">
      {f'<img src="{logo_uri or emblem_uri}" style="height:105px;width:auto" alt="XGPedia"/>' if (logo_uri or emblem_uri) else '<div style="font-size:64px;font-weight:900;color:#E62E45">XGPedia</div>'}
    </div>
    <div id="outroHandle" class="outro-handle" dir="ltr">@XGPedia</div>
    <div id="outroSub" class="outro-sub">فوتبال به زبان داده و امید گل</div>
  </div>
</div>

<script>
const STORY = {story_json};
const DUR = {duration_sec:.2f};

function clamp(v, a, b) {{ return Math.max(a, Math.min(b, v)); }}
function easeOutBack(x) {{
  const c1 = 1.70158, c3 = c1 + 1;
  return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2);
}}
function easeOutCubic(x) {{ return 1 - Math.pow(1 - x, 3); }}
function faNum(s) {{
  return String(s).replace(/[0-9]/g, d => '۰۱۲۳۴۵۶۷۸۹'[Number(d)]);
}}

// Initialize dynamic DOM once
(function initDOM() {{
  if (STORY.photo) {{
    document.getElementById('heroPhotoWrap').style.display = 'block';
    document.getElementById('heroPhoto').src = STORY.photo;
  }}
  if (STORY.crest) {{
    document.getElementById('heroCrest').style.display = 'flex';
    document.getElementById('heroCrestImg').src = STORY.crest;
  }}
  if (STORY.quote_or_body) {{
    const q = document.getElementById('heroQuote');
    q.style.display = 'block';
    q.textContent = STORY.quote_or_body;
  }}
  document.getElementById('verdictBox').textContent = STORY.verdict || STORY.quote_or_body || STORY.subline;

  const mg = document.getElementById('mGrid');
  const metrics = STORY.metrics || [];
  mg.style.gridTemplateColumns = `repeat(${{Math.min(3, Math.max(1, metrics.length))}}, minmax(0, 1fr))`;
  metrics.slice(0, 3).forEach((m, i) => {{
    const div = document.createElement('div');
    div.className = 'm-card';
    div.id = `mc_${{i}}`;
    div.innerHTML = `<div class="m-val" id="mv_${{i}}">۰</div><div class="m-lbl">${{m.label}}</div>`;
    mg.appendChild(div);
  }});

  const bw = document.getElementById('barsWrap');
  (STORY.bars || []).slice(0, 4).forEach((b, i) => {{
    const div = document.createElement('div');
    div.className = 'b-item';
    div.id = `bi_${{i}}`;
    div.innerHTML = `<div class="b-top"><span>${{b.label}}</span><span style="color:${{b.color || '#34D399'}}">${{faNum(b.val_text)}}</span></div><div class="b-track"><div class="b-fill" id="bf_${{i}}" style="background:linear-gradient(90deg,${{b.color || '#10B981'}},#38BDF8)"></div></div>`;
    bw.appendChild(div);
  }});
}})();

function sceneAlpha(t, s, e, fade=0.35) {{
  if (t < s || t > e) return 0;
  if (t < s + fade) return easeOutCubic((t - s) / fade);
  if (t > e - fade) return easeOutCubic((e - t) / fade);
  return 1;
}}

window.__setTime = function(t) {{
  // Continuous kinetic background motion
  document.getElementById('bgGrid').style.transform = `translate3d(${{(t * 14) % 64}}px, ${{(t * 10) % 64}}px, 0)`;
  document.getElementById('orb1').style.transform = `translate3d(${{Math.sin(t * 0.9) * 55}}px, ${{Math.cos(t * 0.7) * 45}}px, 0) scale(${{1 + Math.sin(t * 1.4) * 0.08}})`;
  document.getElementById('orb2').style.transform = `translate3d(${{Math.cos(t * 0.8) * 60}}px, ${{Math.sin(t * 0.6) * 50}}px, 0) scale(${{1 + Math.cos(t * 1.2) * 0.08}})`;
  document.getElementById('progBar').style.width = `${{clamp((t / DUR) * 100, 0, 100)}}%`;

  // Laser sweeps on transitions
  const l1p = clamp((t % 3.6) / 0.85, 0, 1);
  document.getElementById('laser1').style.transform = `translateX(${{l1p * 2100}}px)`;
  document.getElementById('laser1').style.opacity = l1p < 1 ? (1 - l1p) * 0.8 : 0;

  // Persistent corner watermark during Acts 2-4
  document.getElementById('wmCorner').style.opacity = (t >= 1.8 && t <= 12.6) ? 0.92 : 0;

  // ACT 1: Signature Intro (0.0 - 1.95s)
  const a1 = sceneAlpha(t, 0.0, 1.95, 0.30);
  const sc1 = document.getElementById('scIntro');
  sc1.style.opacity = a1;
  if (a1 > 0) {{
    const p1 = easeOutBack(clamp(t / 0.65, 0, 1));
    document.getElementById('introRing').style.transform = `scale(${{0.35 + 0.65 * p1}}) rotate(${{(1 - clamp(t / 0.7, 0, 1)) * -18}}deg)`;
    const pt = easeOutCubic(clamp((t - 0.35) / 0.45, 0, 1));
    document.getElementById('introTag').style.transform = `translateY(${{(1 - pt) * 50}}px)`;
    document.getElementById('introTag').style.opacity = pt;
    document.getElementById('introLine').style.width = `${{easeOutCubic(clamp((t - 0.55) / 0.5, 0, 1)) * 420}}px`;
  }}

  // ACT 2: Kinetic Hero (1.8 - 5.75s)
  const a2 = sceneAlpha(t, 1.8, 5.75, 0.32);
  const sc2 = document.getElementById('scHero');
  sc2.style.opacity = a2;
  if (a2 > 0) {{
    const lt = t - 1.8;
    const zoom = 1.0 + clamp(lt / 4.0, 0, 1) * 0.09;
    document.getElementById('heroPhoto').style.transform = `scale(${{zoom}}) translateY(${{-lt * 4}}px)`;
    const pC = easeOutBack(clamp(lt / 0.55, 0, 1));
    document.getElementById('heroCrest').style.transform = `scale(${{0.2 + 0.8 * pC}})`;
    const pK = easeOutCubic(clamp((lt - 0.10) / 0.45, 0, 1));
    document.getElementById('heroKicker').style.transform = `translateX(${{(1 - pK) * 90}}px)`;
    document.getElementById('heroKicker').style.opacity = pK;
    const pT = easeOutCubic(clamp((lt - 0.22) / 0.55, 0, 1));
    document.getElementById('heroTitle').style.transform = `translateY(${{(1 - pT) * 70}}px)`;
    document.getElementById('heroTitle').style.opacity = pT;
    const pS = easeOutCubic(clamp((lt - 0.40) / 0.50, 0, 1));
    document.getElementById('heroSub').style.transform = `translateY(${{(1 - pS) * 50}}px)`;
    document.getElementById('heroSub').style.opacity = pS;
    const pQ = easeOutBack(clamp((lt - 0.65) / 0.60, 0, 1));
    document.getElementById('heroQuote').style.transform = `translateY(${{(1 - pQ) * 65}}px) scale(${{0.94 + 0.06 * clamp(pQ, 0, 1)}})`;
    document.getElementById('heroQuote').style.opacity = clamp((lt - 0.65) / 0.35, 0, 1);
  }}

  // ACT 3: Animated Metrics & Bars (5.6 - 10.75s)
  const a3 = sceneAlpha(t, 5.6, 10.75, 0.32);
  const sc3 = document.getElementById('scData');
  sc3.style.opacity = a3;
  if (a3 > 0) {{
    const lt = t - 5.6;
    const metrics = STORY.metrics || [];
    metrics.slice(0, 3).forEach((m, i) => {{
      const pm = easeOutBack(clamp((lt - i * 0.18) / 0.55, 0, 1));
      const card = document.getElementById(`mc_${{i}}`);
      if (card) {{
        card.style.transform = `translateY(${{(1 - pm) * 75}}px) scale(${{0.85 + 0.15 * clamp(pm, 0, 1)}})`;
        card.style.opacity = clamp((lt - i * 0.18) / 0.35, 0, 1);
      }}
      const cp = easeOutCubic(clamp((lt - 0.25 - i * 0.15) / 1.15, 0, 1));
      const cur = (m.target || 0) * cp;
      const dec = m.decimals || 0;
      const formatted = (m.prefix || '') + cur.toFixed(dec) + (m.suffix || '');
      const mv = document.getElementById(`mv_${{i}}`);
      if (mv) mv.textContent = faNum(formatted);
    }});

    (STORY.bars || []).slice(0, 4).forEach((b, i) => {{
      const delay = 0.75 + i * 0.22;
      const pb = easeOutCubic(clamp((lt - delay) / 0.55, 0, 1));
      const item = document.getElementById(`bi_${{i}}`);
      if (item) {{
        item.style.transform = `translateX(${{(1 - pb) * 110}}px)`;
        item.style.opacity = pb;
      }}
      const fill = document.getElementById(`bf_${{i}}`);
      if (fill) {{
        const pf = easeOutCubic(clamp((lt - delay - 0.15) / 0.85, 0, 1));
        fill.style.width = `${{pf * (b.pct || 70)}}%`;
      }}
    }});
  }}

  // ACT 4: Verdict & CTA (10.6 - 12.75s)
  const a4 = sceneAlpha(t, 10.6, 12.75, 0.30);
  const sc4 = document.getElementById('scVerdict');
  sc4.style.opacity = a4;
  if (a4 > 0) {{
    const lt = t - 10.6;
    const pv = easeOutBack(clamp(lt / 0.55, 0, 1));
    document.getElementById('verdictBox').style.transform = `scale(${{0.82 + 0.18 * pv}})`;
    const pulse = 1 + Math.sin(lt * 7.5) * 0.04;
    document.getElementById('ctaPill').style.transform = `scale(${{easeOutBack(clamp((lt - 0.35) / 0.45, 0, 1)) * pulse}})`;
  }}

  // ACT 5: Signature Branded Outro (12.6 - DUR)
  const a5 = sceneAlpha(t, 12.6, DUR + 0.2, 0.30);
  const sc5 = document.getElementById('scOutro');
  sc5.style.opacity = a5;
  if (a5 > 0) {{
    const lt = t - 12.6;
    const po = easeOutBack(clamp(lt / 0.55, 0, 1));
    document.getElementById('outroRing').style.transform = `scale(${{0.4 + 0.6 * po}})`;
    const ph = easeOutCubic(clamp((lt - 0.25) / 0.45, 0, 1));
    document.getElementById('outroHandle').style.transform = `translateY(${{(1 - ph) * 40}}px)`;
    document.getElementById('outroHandle').style.opacity = ph;
  }}
}};

window.__setTime(0);
</script>
</body>
</html>"""
