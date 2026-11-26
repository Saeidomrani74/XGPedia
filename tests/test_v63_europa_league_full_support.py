"""تست‌های نسخهٔ 0.63.0: پشتیبانی کامل از لیگ اروپا (UEFA Europa League) و تقارن ۱:۱ تمام ۱۵۱ باشگاه."""
from __future__ import annotations

import json
from pathlib import Path

from src.xgpedia.config import canonical_team_name, card_short_team_name_fa, team_identity, team_name_fa, translate_player_fa
from src.xgpedia.core.leagues import (
    EUROPEAN_ESPN_SLUGS,
    EUROPEAN_FDO_CODES,
    EUROPEAN_LEAGUES,
    competition_badge_fa,
    competition_name_fa,
    league_by_code,
    league_by_espn_slug,
    league_by_name,
)
from src.xgpedia.providers.breaking_news_free import ESPN_NEWS_FEEDS
from src.xgpedia.providers.debate_free import _DEBATE_ESPN_FEEDS
from src.xgpedia.providers.live_intel_free import TEAM_WIKI_TITLES
from src.xgpedia.providers.quote_free import ESPN_QUOTE_FEEDS
from src.xgpedia.providers.standings_free import STANDINGS_LEAGUE_SPECS
from src.xgpedia.render.cards import COMPETITION_FA

WINDOWS_RESERVED = {"AUX", "CON", "PRN", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}

ALL_36_UEL_2026_27_CLUBS = [
    "Bayer Leverkusen", "Benfica", "Juventus", "AC Milan", "Lyon",
    "AZ Alkmaar", "Olympiacos", "Real Sociedad", "Marseille",
    "Ferencvaros", "Viktoria Plzen", "Union Saint-Gilloise", "Dinamo Zagreb",
    "Red Bull Salzburg", "Celtic", "Sparta Prague", "Rennes", "Anderlecht",
    "Sturm Graz", "Lech Poznan", "Crystal Palace", "Bournemouth", "Sunderland",
    "NK Celje", "Jagiellonia Bialystok", "AC Omonia", "Celta Vigo",
    "TSG Hoffenheim", "Besiktas", "SCU Torreense", "Hapoel Be'er Sheva",
    "NEC Nijmegen", "OFI Crete", "Lillestrom SK", "Levski Sofia", "Ararat-Armenia",
]


def test_europa_league_registered_across_registry_and_providers() -> None:
    assert len(EUROPEAN_LEAGUES) == 7
    assert "EL" in EUROPEAN_FDO_CODES
    assert "uefa.europa" in EUROPEAN_ESPN_SLUGS
    el = league_by_code("EL")
    assert el is not None
    assert el.espn_slug == "uefa.europa"
    assert el.name_en == "UEFA Europa League"
    assert el.name_fa == "لیگ اروپا"
    assert league_by_espn_slug("uefa.europa") == el
    assert league_by_name("UEL") == el
    assert league_by_name("Europa League") == el
    assert competition_name_fa("uefa.europa") == "لیگ اروپا"
    assert "لیگ اروپا" in competition_badge_fa("EL")
    assert COMPETITION_FA.get("UEFA Europa League") == "لیگ اروپا"

    assert any(lg["espn_slug"] == "uefa.europa" and lg["id"] == "live_uel" for lg in STANDINGS_LEAGUE_SPECS)
    assert any(slug == "uefa.europa" for slug, _, _ in ESPN_NEWS_FEEDS)
    assert any(slug == "uefa.europa" for slug, _ in _DEBATE_ESPN_FEEDS)
    assert any(slug == "uefa.europa" for slug, _, _ in ESPN_QUOTE_FEEDS)


def test_151_clubs_1to1_symmetry_no_windows_reserved_and_all_36_uel_clubs_complete() -> None:
    ti = json.loads(Path("config/team_identities.json").read_text(encoding="utf-8"))["teams"]
    gl = json.loads(Path("config/glossary_fa.json").read_text(encoding="utf-8"))["teams"]
    tm = json.loads(Path("config/team_mapping.json").read_text(encoding="utf-8"))["teams"]
    tv = json.loads(Path("config/team_venues.json").read_text(encoding="utf-8"))["teams"]

    assert len(ti) == len(gl) == len(tm) == len(tv) == 151
    i_codes = {v["code"] for v in ti.values()}
    g_codes = {t["id"] for t in gl}
    assert i_codes == g_codes
    assert not (i_codes & WINDOWS_RESERVED)

    # هر ۳۶ باشگاه فصل ۲۶/۲۷ لیگ اروپا باید هویت، رنگ، نام فارسی، ورزشگاه، لوگوی SVG و عنوان ویکی‌پدیا داشته باشند
    for club in ALL_36_UEL_2026_27_CLUBS:
        canon = canonical_team_name(club)
        ident = team_identity(canon)
        assert ident is not None, f"Missing identity for {club}"
        assert ident["code"] not in WINDOWS_RESERVED
        crest_path = Path(ident.get("crest") or f"brand/crests/{ident['code']}.svg")
        assert crest_path.exists(), f"Missing SVG crest for {club}: {crest_path}"
        assert team_name_fa(canon), f"Missing Persian name for {club}"
        assert canon in tv or club in tv, f"Missing stadium for {club}"
        assert canon in TEAM_WIKI_TITLES or club in TEAM_WIKI_TITLES, f"Missing Wikipedia title for {club}"

    # نام‌های کوتاه هدر و نام‌های بازیکنان لیگ اروپا
    assert card_short_team_name_fa("Jagiellonia Bialystok") == "یاگیلونیا"
    assert card_short_team_name_fa("NEC Nijmegen") == "نایمخن"
    assert translate_player_fa("Vangelis Pavlidis") == "پاولیدیس"
    assert translate_player_fa("Mikel Oyarzabal") == "اویارزابال"
    assert translate_player_fa("Ayoub El Kaabi") == "ال‌کعبی"
