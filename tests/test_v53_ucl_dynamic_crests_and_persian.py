"""تست‌های نسخهٔ 0.53.0: پوشش کامل چمپیونزلیگ (۱۳۹ باشگاه)، لوگوهای پویای ESPN/FDO و فارسی‌سازی دروازه‌بان‌ها."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from src.xgpedia.config import card_short_team_name_fa, team_name_fa
from src.xgpedia.providers import dynamic_crests as dc
from src.xgpedia.providers.live_intel_free import TEAM_WIKI_TITLES
from src.xgpedia.render.cards import _crest_data_uri
from src.xgpedia.render.post_match_cards import _valid_gk


def test_139_clubs_symmetric_across_all_4_configs_and_wiki() -> None:
    g = json.loads(Path("config/glossary_fa.json").read_text(encoding="utf-8"))
    ti = json.loads(Path("config/team_identities.json").read_text(encoding="utf-8"))
    tm = json.loads(Path("config/team_mapping.json").read_text(encoding="utf-8"))
    tv = json.loads(Path("config/team_venues.json").read_text(encoding="utf-8"))

    g_names = {t["name_en"] for t in g["teams"]}
    assert len(g_names) >= 139
    assert g_names == set(ti["teams"].keys())
    assert len(tm["teams"]) >= 139
    assert "Sabah FK" in tm["teams"] and "Sabah FK" in tv["teams"]

    # همهٔ باشگاه‌ها عنوان ویکی‌پدیا دارند
    missing_wiki = [n for n in g_names if n not in TEAM_WIKI_TITLES]
    assert missing_wiki == [], f"Missing wiki titles: {missing_wiki}"

    # باشگاه‌های چمپیونزلیگ مثل Sabah FK و Qarabag و Olympiacos
    assert team_name_fa("Sabah FK") == "صباح باکو"
    assert card_short_team_name_fa("Sabah FK", team_name_fa("Sabah FK")) == "صباح باکو"
    assert team_name_fa("Qarabag") == "قره‌باغ"
    assert team_name_fa("Olympiacos") == "المپیاکوس"
    assert team_name_fa("Union Saint-Gilloise") == "یونیون سنت ژیلواز"
    assert card_short_team_name_fa("Union Saint-Gilloise", team_name_fa("Union Saint-Gilloise")) == "سنت ژیلواز"


def test_unknown_club_auto_transliterates_to_persian() -> None:
    # حتی اگر یک باشگاه کاملاً جدید در آینده اضافه شود، نام انگلیسی خام برنمی‌گرداند
    res = team_name_fa("Zrinjski Mostar FK")
    assert res != "Zrinjski Mostar FK"
    assert any("\u0600" <= ch <= "\u06FF" for ch in res)


def test_dynamic_crest_register_and_render_resolution(tmp_path) -> None:
    reg_file = tmp_path / "team_logos.json"
    cache_dir = tmp_path / "badge_cache"
    fake_png = b"\x89PNG\r\n\x1a\n" + b"X" * 300

    with patch.object(dc, "LOGO_REGISTRY_FILE", reg_file), patch.object(dc, "BADGE_CACHE_DIR", cache_dir):
        dc.register_team_logo("Sabah FK", "https://a.espncdn.com/i/teamlogos/soccer/500/20842.png")
        assert dc._lookup_registered_url("Sabah FK") == "https://a.espncdn.com/i/teamlogos/soccer/500/20842.png"

        # ذخیره در کش دیسک و بازیابی از _crest_data_uri
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "dyn_sabah_fk.png").write_bytes(fake_png)
        uri = _crest_data_uri("Sabah FK")
        assert uri is not None and uri.startswith("data:image/png;base64,")


def test_goalkeeper_names_translated_to_persian() -> None:
    gk1 = _valid_gk({"name": "S. Pokatilov", "saves": 9, "psxg": 1.23, "ga": 1})
    gk2 = _valid_gk({"name": "J. García", "saves": 2, "psxg": 5.0, "ga": 4})
    assert gk1 is not None and gk2 is not None
    assert any("\u0600" <= ch <= "\u06FF" for ch in gk1["name"]), f"GK1 still English: {gk1['name']}"
    assert any("\u0600" <= ch <= "\u06FF" for ch in gk2["name"]), f"GK2 still English: {gk2['name']}"
