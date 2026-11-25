"""تست‌های واحد هات‌فیکس v0.36.2:
  1. رفع UnboundLocalError متغیر `pk` در `players_rating_free.fetch_live_rated_matches`
  2. جایگزینی لوگوی رسمی `brand/logo/svg/logo-xg-red.svg` در پایین کارت FC27
  3. نمایش لوگوی واقعی باشگاه‌های انگلیس در کارت‌های گزارش پزشکی، جدول رده‌بندی و پروفایل فنی بازیکن
"""
from __future__ import annotations

from unittest.mock import patch


def test_v362_players_rating_no_pk_unbound_error() -> None:
    from src.xgpedia.providers import players_rating_free as prf

    # وقتی ESPN لیست خالی برمی‌گرداند نباید UnboundLocalError رخ دهد
    with (
        patch.object(prf, "_fetch_fpl_finished_24h_rated_matches", return_value=[]),
        patch.object(prf, "_http_get_json", return_value={"events": []}),
    ):
        res = prf.fetch_live_rated_matches(force_refresh=True)
        assert isinstance(res, list)


def test_v362_fc27_uses_brand_logo_xg_red_svg() -> None:
    from src.xgpedia.providers.player_fc27_free import load_player_fc27_presets
    from src.xgpedia.render.card_kit.player_fc27_card import _brand_xg_red_data_uri, render_player_fc27_html

    uri = _brand_xg_red_data_uri()
    assert uri and uri.startswith("data:image/svg+xml;base64,")

    item = load_player_fc27_presets()[0]
    html = render_player_fc27_html(item, fmt="4:5", slide="slide1")
    assert f'<image href="{uri}"' in html
    assert '<rect x="145" y="33" width="30" height="30" rx="6" fill="#E62E45"/>' not in html


def test_v362_real_pl_logos_in_injury_standings_and_player_profile() -> None:
    from src.xgpedia.render.card_kit.injury_card import _crest_svg as inj_crest
    from src.xgpedia.render.card_kit.player_card import _crest_svg as pl_crest
    from src.xgpedia.render.card_kit.standings_card import _crest_svg as st_crest

    h_inj = inj_crest({"club": "آرسنال", "clubCode": "ARS", "color": "#EF0107"}, 72)
    assert "data:image/" in h_inj and "<img " in h_inj

    h_st = st_crest({"name": "منچسترسیتی", "code": "MCI", "color": "#38BDF8"}, 36, "s1")
    assert "data:image/" in h_st and "<img " in h_st

    h_pl = pl_crest({"club": "لیورپول", "code": "LIV", "color": "#C8102E"}, 64)
    assert "data:image/" in h_pl and "<img " in h_pl
