"""رجیستری مرکزی ۶ لیگ معتبر فوتبال اروپا در XGPedia (نسخهٔ 0.51.0).

منبع واحد حقیقت (Single Source of Truth) برای نگاشت یکپارچهٔ:
  - کد football-data.org (`PL`, `CL`, `PD`, `SA`, `BL1`, `FL1`)
  - اسلاگ عمومی ESPN (`eng.1`, `uefa.champions`, `esp.1`, `ita.1`, `ger.1`, `fra.1`)
  - کد CSV هفتگی football-data.co.uk (`E0`, `SP1`, `I1`, `D1`, `F1`)
  - اسلاگ Understat (`EPL`, `La_liga`, `Serie_A`, `Bundesliga`, `Ligue_1`)
  - کلید ورزشی The Odds API (`soccer_epl`, ...)
  - نام فارسی کامل، نام کوتاه و بج ایموجی در بات تلگرام و کارت‌ها
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LeagueSpec:
    code: str                    # FDO code: PL, CL, PD, SA, BL1, FL1
    espn_slug: str               # eng.1, uefa.champions, esp.1, ita.1, ger.1, fra.1
    name_en: str                 # Premier League, UEFA Champions League, ...
    name_fa: str                 # لیگ برتر انگلیس, ...
    short_fa: str                # لیگ برتر, چمپیونزلیگ, ...
    emoji: str                   # 🏴󠁧󠁢󠁥󠁮󠁧󠁿, 🏆, 🇪🇸, 🇮🇹, 🇩🇪, 🇫🇷
    csv_code: str | None         # E0, None, SP1, I1, D1, F1
    understat_slug: str | None   # EPL, None, La_liga, Serie_A, Bundesliga, Ligue_1
    odds_sport_key: str          # soccer_epl, ...


EUROPEAN_LEAGUES: tuple[LeagueSpec, ...] = (
    LeagueSpec(
        code="PL",
        espn_slug="eng.1",
        name_en="Premier League",
        name_fa="لیگ برتر انگلیس",
        short_fa="لیگ برتر",
        emoji="🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        csv_code="E0",
        understat_slug="EPL",
        odds_sport_key="soccer_epl",
    ),
    LeagueSpec(
        code="CL",
        espn_slug="uefa.champions",
        name_en="UEFA Champions League",
        name_fa="لیگ قهرمانان اروپا",
        short_fa="چمپیونزلیگ",
        emoji="🏆",
        csv_code=None,
        understat_slug=None,
        odds_sport_key="soccer_uefa_champs_league",
    ),
    LeagueSpec(
        code="EL",
        espn_slug="uefa.europa",
        name_en="UEFA Europa League",
        name_fa="لیگ اروپا",
        short_fa="لیگ اروپا",
        emoji="🟠",
        csv_code=None,
        understat_slug=None,
        odds_sport_key="soccer_uefa_europa_league",
    ),
    LeagueSpec(
        code="PD",
        espn_slug="esp.1",
        name_en="La Liga",
        name_fa="لالیگا اسپانیا",
        short_fa="لالیگا",
        emoji="🇪🇸",
        csv_code="SP1",
        understat_slug="La_liga",
        odds_sport_key="soccer_spain_la_liga",
    ),
    LeagueSpec(
        code="SA",
        espn_slug="ita.1",
        name_en="Serie A",
        name_fa="سری آ ایتالیا",
        short_fa="سری آ",
        emoji="🇮🇹",
        csv_code="I1",
        understat_slug="Serie_A",
        odds_sport_key="soccer_italy_serie_a",
    ),
    LeagueSpec(
        code="BL1",
        espn_slug="ger.1",
        name_en="Bundesliga",
        name_fa="بوندس‌لیگا آلمان",
        short_fa="بوندس‌لیگا",
        emoji="🇩🇪",
        csv_code="D1",
        understat_slug="Bundesliga",
        odds_sport_key="soccer_germany_bundesliga",
    ),
    LeagueSpec(
        code="FL1",
        espn_slug="fra.1",
        name_en="Ligue 1",
        name_fa="لیگ ۱ فرانسه",
        short_fa="لیگ ۱",
        emoji="🇫🇷",
        csv_code="F1",
        understat_slug="Ligue_1",
        odds_sport_key="soccer_france_ligue_one",
    ),
)

DOMESTIC_LEAGUES: tuple[LeagueSpec, ...] = tuple(lg for lg in EUROPEAN_LEAGUES if lg.csv_code)
EUROPEAN_FDO_CODES: tuple[str, ...] = tuple(lg.code for lg in EUROPEAN_LEAGUES)
EUROPEAN_ESPN_SLUGS: tuple[str, ...] = tuple(lg.espn_slug for lg in EUROPEAN_LEAGUES)
EUROPEAN_CSV_CODES: tuple[str, ...] = tuple(lg.csv_code for lg in DOMESTIC_LEAGUES if lg.csv_code)

_BY_CODE: dict[str, LeagueSpec] = {lg.code.upper(): lg for lg in EUROPEAN_LEAGUES}
_BY_ESPN: dict[str, LeagueSpec] = {lg.espn_slug.lower(): lg for lg in EUROPEAN_LEAGUES}
_BY_CSV: dict[str, LeagueSpec] = {lg.csv_code.upper(): lg for lg in DOMESTIC_LEAGUES if lg.csv_code}

_NAME_ALIASES: dict[str, LeagueSpec] = {}
for _lg in EUROPEAN_LEAGUES:
    for _k in (_lg.code, _lg.espn_slug, _lg.name_en, _lg.name_fa, _lg.short_fa):
        _NAME_ALIASES[_k.strip().lower()] = _lg
# نام‌های رسمی متداول در football-data.org و ESPN
_NAME_ALIASES.update({
    "primera division": _BY_CODE["PD"],
    "spanish laliga": _BY_CODE["PD"],
    "laliga": _BY_CODE["PD"],
    "english premier league": _BY_CODE["PL"],
    "epl": _BY_CODE["PL"],
    "champions league": _BY_CODE["CL"],
    "ucl": _BY_CODE["CL"],
    "europa league": _BY_CODE["EL"],
    "uel": _BY_CODE["EL"],
    "uefa europa": _BY_CODE["EL"],
    "لیگ اروپای یوفا": _BY_CODE["EL"],
    "italian serie a": _BY_CODE["SA"],
    "german bundesliga": _BY_CODE["BL1"],
    "french ligue 1": _BY_CODE["FL1"],
    "ligue 1 uber eats": _BY_CODE["FL1"],
    "ligue 1 mcdonald's": _BY_CODE["FL1"],
})


def league_by_code(code: str | None) -> LeagueSpec | None:
    if not code:
        return None
    return _BY_CODE.get(str(code).strip().upper())


def league_by_espn_slug(slug: str | None) -> LeagueSpec | None:
    if not slug:
        return None
    return _BY_ESPN.get(str(slug).strip().lower())


def league_by_csv_code(csv_code: str | None) -> LeagueSpec | None:
    if not csv_code:
        return None
    return _BY_CSV.get(str(csv_code).strip().upper())


def league_by_name(name: str | None) -> LeagueSpec | None:
    if not name:
        return None
    low = str(name).strip().lower()
    if low in _NAME_ALIASES:
        return _NAME_ALIASES[low]
    for alias, spec in _NAME_ALIASES.items():
        if alias and (alias in low or low in alias):
            return spec
    return None


def canonical_competition_name(raw: str | None, default: str = "Premier League") -> str:
    spec = league_by_name(raw)
    return spec.name_en if spec else (str(raw).strip() if raw and str(raw).strip() else default)


def competition_name_fa(raw: str | None) -> str:
    spec = league_by_name(raw)
    return spec.name_fa if spec else (str(raw or "").strip() or "فوتبال اروپا")


def competition_badge_fa(raw: str | None) -> str:
    """بج کوتاه و خوانا برای دکمه‌های تلگرام؛ مثلاً `🏆 چمپیونزلیگ` یا `🇪🇸 لالیگا`."""
    spec = league_by_name(raw)
    if spec:
        return f"{spec.emoji} {spec.short_fa}"
    return f"⚽ {str(raw or '').strip() or 'اروپا'}"
