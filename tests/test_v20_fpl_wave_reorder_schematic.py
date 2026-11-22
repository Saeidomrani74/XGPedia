"""تست‌های v0.20.0:
- پرووایدر رایگان FPL رسمی برای ماژول مهره کلیدی (keyduel)
- استخراج خودکار موج زمانی ۱۵ دقیقه‌ای (wave) از HT/FT در E0.csv
- ثبت در دیتابیس و بازیابی از _team_enrichment_from_db (همهٔ ۷ ماژول پیش‌ازبازی)
- اعتبارسنجی سخت‌گیرانهٔ نیم‌عرض (validate_half_width_layout)
- پیش‌نمایش شماتیک مکانی (_build_layout_schematic) و جابه‌جایی عمودی (cz:up / cz:dn) در تلگرام
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.xgpedia import db as db_mod
from src.xgpedia.db import db, init_db
from src.xgpedia.providers.football_data_couk import compute_wave_from_csv
from src.xgpedia.providers.fpl_free import parse_fpl_key_players
from src.xgpedia.publishers import telegram_bot as tb
from src.xgpedia.render.card_kit.base_shell import validate_half_width_layout
from src.xgpedia.sync import _team_enrichment_from_db, sync_csv_waves, sync_fpl_key_players


SAMPLE_FPL = {
    "teams": [
        {"id": 1, "name": "Arsenal"},
        {"id": 12, "name": "Man City"},
    ],
    "elements": [
        # دروازه‌بان باید نادیده گرفته شود
        {
            "team": 1,
            "element_type": 1,
            "minutes": 900,
            "expected_goal_involvements": "10.0",
            "goals_scored": 0,
            "assists": 0,
            "first_name": "David",
            "second_name": "Raya",
            "web_name": "Raya",
        },
        # بازیکن با دقیقهٔ کم باید نادیده گرفته شود
        {
            "team": 1,
            "element_type": 4,
            "minutes": 30,
            "expected_goal_involvements": "5.0",
            "goals_scored": 2,
            "assists": 1,
            "first_name": "Sub",
            "second_name": "Player",
            "web_name": "Sub",
        },
        # مهره کلیدی واقعی آرسنال
        {
            "team": 1,
            "element_type": 3,
            "minutes": 900,
            "expected_goal_involvements": "8.50",
            "goals_scored": 5,
            "assists": 6,
            "first_name": "Bukayo",
            "second_name": "Saka",
            "web_name": "Saka",
        },
        # مهره کلیدی واقعی منچستر سیتی
        {
            "team": 12,
            "element_type": 4,
            "minutes": 810,
            "expected_goal_involvements": "10.20",
            "goals_scored": 11,
            "assists": 1,
            "first_name": "Erling",
            "second_name": "Haaland",
            "web_name": "Haaland",
        },
    ],
}

SAMPLE_CSV = """Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,HTHG,HTAG
E0,01/11/2026,Arsenal,Man City,2,1,1,0
E0,08/11/2026,Man City,Arsenal,3,1,1,1
E0,15/11/2026,Arsenal,Chelsea,2,0,0,0
"""


def test_parse_fpl_key_players_extracts_top_outfield_players():
    res = parse_fpl_key_players(SAMPLE_FPL)
    assert "Arsenal" in res
    assert "Manchester City" in res
    assert res["Arsenal"]["name"] == "Bukayo Saka"
    assert res["Arsenal"]["pos"] == "هافبک"
    assert "xG+xA" in res["Arsenal"]["s1"]
    assert res["Manchester City"]["name"] == "Erling Haaland"
    assert res["Manchester City"]["pos"] == "مهاجم"


def test_compute_wave_from_csv_produces_six_buckets():
    waves = compute_wave_from_csv(SAMPLE_CSV)
    assert "Arsenal" in waves
    assert "Manchester City" in waves
    assert len(waves["Arsenal"]) == 6
    assert all(v > 0 for v in waves["Arsenal"])
    # آرسنال در ۳ بازی ۲ گل نیمه اول و ۳ گل نیمه دوم زده -> نیمه دوم باید بزرگ‌تر از نیمه اول باشد
    assert sum(waves["Arsenal"][3:]) > sum(waves["Arsenal"][:3])


def test_sync_fpl_and_csv_wave_into_db_and_enrichment(tmp_path, monkeypatch):
    db_path = tmp_path / "test_v20.db"
    monkeypatch.setattr(db_mod, "DATABASE_PATH", db_path)
    init_db()

    kps = parse_fpl_key_players(SAMPLE_FPL)
    waves = compute_wave_from_csv(SAMPLE_CSV)

    res_kp = sync_fpl_key_players(kps, season_start=2026)
    res_wv = sync_csv_waves(waves, season_start=2026)
    assert sum(res_kp.values()) >= 2
    assert sum(res_wv.values()) >= 2

    with db() as conn:
        ars = _team_enrichment_from_db(conn, "Arsenal", "2026-27")
        mci = _team_enrichment_from_db(conn, "Manchester City", "2026-27")

    assert ars["kp"] is not None
    assert ars["kp"]["name"] == "Bukayo Saka"
    assert ars["wave"] is not None and len(ars["wave"]) == 6
    assert mci["kp"] is not None
    assert mci["kp"]["name"] == "Erling Haaland"


def test_validate_half_width_layout_rejects_unpaired_and_accepts_pairs():
    ok_mods = [
        {"id": "radar", "title_fa": "رادار", "span": "half", "enabled": True},
        {"id": "trend10", "title_fa": "روند", "span": "half", "enabled": True},
        {"id": "bars", "title_fa": "شاخص‌ها", "span": "full", "enabled": True},
    ]
    assert validate_half_width_layout(ok_mods) == []

    bad_end = [
        {"id": "bars", "title_fa": "شاخص‌ها", "span": "full", "enabled": True},
        {"id": "radar", "title_fa": "رادار", "span": "half", "enabled": True},
    ]
    errs_end = validate_half_width_layout(bad_end)
    assert len(errs_end) == 1
    assert "رادار" in errs_end[0]

    bad_mid = [
        {"id": "radar", "title_fa": "رادار", "span": "half", "enabled": True},
        {"id": "bars", "title_fa": "شاخص‌ها", "span": "full", "enabled": True},
        {"id": "trend10", "title_fa": "روند", "span": "half", "enabled": True},
    ]
    errs_mid = validate_half_width_layout(bad_mid)
    assert len(errs_mid) == 2


def test_schematic_preview_and_vertical_reorder_and_strict_build(monkeypatch):
    mods = [
        {"id": "radar", "title_fa": "رادار تاکتیکی", "span": "half", "can_half": True, "enabled": True},
        {"id": "bars", "title_fa": "شاخص‌های فنی", "span": "full", "can_half": True, "enabled": True},
        {"id": "trend10", "title_fa": "روند ۱۰ بازی", "span": "half", "can_half": True, "enabled": True},
    ]
    schematic, errs = tb._build_layout_schematic(mods)
    assert "⚠️ جای خالی!" in schematic
    assert len(errs) == 2

    st = {
        "fixture_id": "fdo:999",
        "home_fa": "آرسنال",
        "away_fa": "منچسترسیتی",
        "round": "هفته ۱۲",
        "stadium": "امارات",
        "fmt": "4:5",
        "header_mode": "full",
        "broadcast_idx": 0,
        "modules": mods,
        "missing_modules": [],
    }
    text, markup = tb._render_customizer_view(st)
    assert "<pre>" in text
    assert "خطای چیدمان نیم‌عرض" in text
    # دکمه‌های جابه‌جایی عمودی ⬆️ و ⬇️ وجود دارند
    all_cbs = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert "cz:up:bars" in all_cbs
    assert "cz:dn:radar" in all_cbs

    # تست تعامل: ۱) build هنگام وجود جای خالی بلاک می‌شود ۲) جابه‌جایی عمودی جفت‌سازی را درست می‌کند
    monkeypatch.setattr(tb.tp, "is_admin", lambda uid: True)
    tb._CUSTOMIZER_STATE[42] = st

    cb_build = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        data="cz:build",
        answer=AsyncMock(),
        message=SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock()),
    )
    asyncio.run(tb.on_customizer_action(cb_build, bot=SimpleNamespace()))
    cb_build.answer.assert_awaited()
    args, kwargs = cb_build.answer.call_args
    assert kwargs.get("show_alert") is True
    assert "خالی" in args[0]

    # حالا trend10 را یک ردیف بالا می‌بریم تا کنار radar جفت شود
    cb_up = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        data="cz:up:trend10",
        answer=AsyncMock(),
        message=SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock()),
    )
    asyncio.run(tb.on_customizer_action(cb_up, bot=SimpleNamespace()))
    assert [m["id"] for m in st["modules"]] == ["radar", "trend10", "bars"]
    schematic_ok, errs_ok = tb._build_layout_schematic(st["modules"])
    assert errs_ok == []
    assert "⚠️ جای خالی!" not in schematic_ok
