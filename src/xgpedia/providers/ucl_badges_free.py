"""لوگوها، رنگ‌ها و نگاشت رسمی باشگاه‌های لیگ قهرمانان اروپا (UEFA Champions League) — ۱۰۰٪ رایگان و بدون `requests`.

منبع لوگوها:
  1. کش دیسک (`output/.badge_cache/ucl_{TLA}.png`) و دانلود رسمی شفاف PNG از ESPN CDN (`a.espncdn.com/i/teamlogos/soccer/500/{espn_id}.png`)
  2. پشتیبان ۱۰۰٪ آفلاین و محلی از `brand/crests/{TLA}.svg` (به‌صورت `data:image/svg+xml;base64,...`)
"""
from __future__ import annotations

import base64
import urllib.request
from pathlib import Path

from src.xgpedia.config import ROOT

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
BADGE_CACHE_DIR = ROOT / "output" / ".badge_cache"
LOCAL_CRESTS_DIR = ROOT / "brand" / "crests"

# key -> (name_fa, tla, primary_hex, secondary_hex, espn_id)
UCL_CLUBS_MASTER: dict[str, tuple[str, str, str, str, int]] = {
    "real madrid": ("رئال مادرید", "RMA", "#F59E0B", "#FFFFFF", 86),
    "real madrid cf": ("رئال مادرید", "RMA", "#F59E0B", "#FFFFFF", 86),
    "barcelona": ("بارسلونا", "BAR", "#A50044", "#004D98", 83),
    "fc barcelona": ("بارسلونا", "BAR", "#A50044", "#004D98", 83),
    "atletico madrid": ("اتلتیکو مادرید", "ATM", "#CB3524", "#FFFFFF", 1068),
    "atlético madrid": ("اتلتیکو مادرید", "ATM", "#CB3524", "#FFFFFF", 1068),
    "atletico de madrid": ("اتلتیکو مادرید", "ATM", "#CB3524", "#FFFFFF", 1068),
    "girona": ("خیرونا", "GIR", "#CD2534", "#FFFFFF", 9812),
    "athletic club": ("اتلتیک بیلبائو", "ATH", "#EE2523", "#FFFFFF", 93),
    "athletic bilbao": ("اتلتیک بیلبائو", "ATH", "#EE2523", "#FFFFFF", 93),
    "villarreal": ("ویارئال", "VIL", "#F5E216", "#005187", 102),
    "bayern munich": ("بایرن مونیخ", "BAY", "#DC052D", "#FFFFFF", 132),
    "fc bayern munich": ("بایرن مونیخ", "BAY", "#DC052D", "#FFFFFF", 132),
    "bayern": ("بایرن مونیخ", "BAY", "#DC052D", "#FFFFFF", 132),
    "borussia dortmund": ("بروسیا دورتموند", "BVB", "#FDE100", "#111827", 124),
    "dortmund": ("بروسیا دورتموند", "BVB", "#FDE100", "#111827", 124),
    "bayer leverkusen": ("بایر لورکوزن", "LEV", "#E32221", "#111827", 131),
    "leverkusen": ("بایر لورکوزن", "LEV", "#E32221", "#111827", 131),
    "rb leipzig": ("آر بی لایپزیگ", "RBL", "#DD0741", "#FFFFFF", 11420),
    "leipzig": ("آر بی لایپزیگ", "RBL", "#DD0741", "#FFFFFF", 11420),
    "vfb stuttgart": ("اشتوتگارت", "STU", "#E32219", "#FFFFFF", 134),
    "stuttgart": ("اشتوتگارت", "STU", "#E32219", "#FFFFFF", 134),
    "eintracht frankfurt": ("آینتراخت فرانکفورت", "SGE", "#E1000F", "#111827", 125),
    "inter milan": ("اینتر میلان", "INT", "#010E80", "#38BDF8", 110),
    "internazionale": ("اینتر میلان", "INT", "#010E80", "#38BDF8", 110),
    "inter": ("اینتر میلان", "INT", "#010E80", "#38BDF8", 110),
    "ac milan": ("آث میلان", "MIL", "#FB090B", "#111827", 103),
    "milan": ("آث میلان", "MIL", "#FB090B", "#111827", 103),
    "juventus": ("یوونتوس", "JUV", "#E2E8F0", "#111827", 111),
    "atalanta": ("آتالانتا", "ATA", "#1E71B8", "#111827", 105),
    "napoli": ("ناپولی", "NAP", "#12A0D7", "#FFFFFF", 114),
    "bologna": ("بولونیا", "BOL", "#9F1F33", "#1A2F48", 107),
    "as roma": ("آاس رم", "ROM", "#8E1F2F", "#F0BC42", 104),
    "roma": ("آاس رم", "ROM", "#8E1F2F", "#F0BC42", 104),
    "paris saint-germain": ("پاری‌سن‌ژرمن", "PSG", "#004170", "#DA291C", 160),
    "psg": ("پاری‌سن‌ژرمن", "PSG", "#004170", "#DA291C", 160),
    "as monaco": ("موناکو", "MON", "#E51B22", "#FFFFFF", 174),
    "monaco": ("موناکو", "MON", "#E51B22", "#FFFFFF", 174),
    "lille": ("لیل", "LIL", "#E01E13", "#1D2B53", 166),
    "losc lille": ("لیل", "LIL", "#E01E13", "#1D2B53", 166),
    "brest": ("برست", "BST", "#E30613", "#FFFFFF", 6997),
    "stade brestois": ("برست", "BST", "#E30613", "#FFFFFF", 6997),
    "marseille": ("مارسی", "MAR", "#2FAEE0", "#FFFFFF", 176),
    "olympique marseille": ("مارسی", "MAR", "#2FAEE0", "#FFFFFF", 176),
    "benfica": ("بنفیکا", "BEN", "#E83030", "#FFFFFF", 1929),
    "sl benfica": ("بنفیکا", "BEN", "#E83030", "#FFFFFF", 1929),
    "sporting cp": ("اسپورتینگ لیسبون", "SCP", "#008057", "#FFFFFF", 2250),
    "sporting lisbon": ("اسپورتینگ لیسبون", "SCP", "#008057", "#FFFFFF", 2250),
    "fc porto": ("پورتو", "POR", "#00428C", "#FFFFFF", 437),
    "porto": ("پورتو", "POR", "#00428C", "#FFFFFF", 437),
    "psv eindhoven": ("پی‌اس‌وی آیندهوون", "PSV", "#ED1C24", "#FFFFFF", 148),
    "psv": ("پی‌اس‌وی آیندهوون", "PSV", "#ED1C24", "#FFFFFF", 148),
    "feyenoord": ("فاینورد", "FEY", "#EE1C25", "#FFFFFF", 142),
    "ajax": ("آژاکس", "AJX", "#D2122E", "#FFFFFF", 139),
    "celtic": ("سلتیک", "CEL", "#018749", "#FFFFFF", 256),
    "club brugge": ("کلوب بروژ", "BRU", "#0069B4", "#111827", 570),
    "shakhtar donetsk": ("شاختار دونتسک", "SHK", "#F36E21", "#111827", 493),
    "shakhtar": ("شاختار دونتسک", "SHK", "#F36E21", "#111827", 493),
    "red bull salzburg": ("ردبول سالزبورگ", "SAL", "#E2001A", "#FFFFFF", 2790),
    "salzburg": ("ردبول سالزبورگ", "SAL", "#E2001A", "#FFFFFF", 2790),
    "galatasaray": ("گالاتاسرای", "GAL", "#A90432", "#FDB912", 432),
    # La Liga clubs
    "real sociedad": ("رئال سوسیداد", "RSO", "#0067B1", "#FFFFFF", 89),
    "real betis": ("رئال بتیس", "BET", "#0BB363", "#FFFFFF", 244),
    "sevilla": ("سویا", "SEV", "#D40028", "#FFFFFF", 243),
    "valencia": ("والنسیا", "VAL", "#EE7500", "#111827", 94),
    "osasuna": ("اوساسونا", "OSA", "#D91A21", "#0A346F", 97),
    "celta vigo": ("سلتاویگو", "CVG", "#8AC3EE", "#E5254E", 85),
    "rayo vallecano": ("رایو وایکانو", "RAY", "#E53027", "#FFFFFF", 101),
    "mallorca": ("مایورکا", "MLL", "#E20613", "#111827", 84),
    "getafe": ("ختافه", "GET", "#005999", "#FFFFFF", 2922),
    "alaves": ("آلاوس", "ALA", "#0053A0", "#FFFFFF", 96),
    "espanyol": ("اسپانیول", "ESP", "#007FC8", "#FFFFFF", 88),
    "las palmas": ("لاس‌پالماس", "LPA", "#FFD200", "#005AA7", 98),
    "real valladolid": ("وایادولید", "VLD", "#5B2482", "#FFFFFF", 95),
    "leganes": ("لگانس", "LEG", "#0055A4", "#FFFFFF", 17534),
    # Serie A clubs
    "lazio": ("لاتزیو", "LAZ", "#87D8F7", "#FFFFFF", 112),
    "fiorentina": ("فیورنتینا", "FIO", "#482E92", "#FFFFFF", 109),
    "torino": ("تورینو", "TOR", "#8A1E03", "#FFFFFF", 239),
    "udinese": ("اودینزه", "UDI", "#E2E8F0", "#111827", 118),
    "genoa": ("جنوا", "GEN", "#AD1919", "#0A2342", 3263),
    "cagliari": ("کالیاری", "CAG", "#9E1B32", "#002350", 2925),
    "hellas verona": ("هلاس ورونا", "VER", "#005395", "#FFD200", 119),
    "empoli": ("امپولی", "EMP", "#00579C", "#FFFFFF", 2574),
    "lecce": ("لچه", "LEC", "#E30613", "#FDE100", 113),
    "parma": ("پارما", "PAR", "#FFD200", "#003399", 115),
    "como": ("کومو", "COM", "#0054A6", "#FFFFFF", 2572),
    "monza": ("مونتزا", "MNZ", "#E30613", "#FFFFFF", 4007),
    "venezia": ("ونتزیا", "VEN", "#F36E21", "#007A33", 17530),
    # Bundesliga clubs
    "sc freiburg": ("فرایبورگ", "SCF", "#E30613", "#111827", 126),
    "borussia monchengladbach": ("بروسیا مونشن‌گلادباخ", "BMG", "#16A34A", "#FFFFFF", 268),
    "werder bremen": ("وردربرمن", "SVW", "#1D9053", "#FFFFFF", 137),
    "vfl wolfsburg": ("ولفسبورگ", "WOB", "#65B32E", "#FFFFFF", 138),
    "mainz 05": ("ماینتس", "M05", "#C3141E", "#FFFFFF", 2950),
    "fc augsburg": ("آگسبورگ", "FCA", "#BA3733", "#16A34A", 3841),
    "union berlin": ("یونیون برلین", "FCU", "#EB1923", "#FFFFFF", 598),
    "tsg hoffenheim": ("هوفنهایم", "TSG", "#1C63B7", "#FFFFFF", 7911),
    "fc heidenheim": ("هایدنهایم", "HDH", "#E30613", "#003C82", 6418),
    "fc st. pauli": ("سن‌پائولی", "STP", "#624A2E", "#FFFFFF", 270),
    "holstein kiel": ("هولشتاین کیل", "KIE", "#005CA9", "#E30613", 7884),
    "vfl bochum": ("بوخوم", "BOC", "#005CA9", "#FFFFFF", 121),
    # Ligue 1 clubs
    "lyon": ("لیون", "LYO", "#14387F", "#DA291C", 167),
    "nice": ("نیس", "NIC", "#D40028", "#111827", 2502),
    "lens": ("لانس", "LEN", "#EC1C24", "#FFD200", 175),
    "rennes": ("رن", "REN", "#E30613", "#111827", 169),
    "strasbourg": ("استراسبورگ", "STR", "#009FE3", "#FFFFFF", 180),
    "reims": ("رمس", "REI", "#D71920", "#FFFFFF", 3243),
    "toulouse": ("تولوز", "TOU", "#5F259F", "#FFFFFF", 179),
    "auxerre": ("اوسر", "AJA", "#0055A4", "#FFFFFF", 172),
    "nantes": ("نانت", "NAN", "#FDE100", "#008057", 165),
    "angers": ("آنژه", "ANG", "#111827", "#FFFFFF", 7868),
    "saint-etienne": ("سنت‌اتین", "STE", "#008E46", "#FFFFFF", 178),
    "le havre": ("لوهاور", "HAC", "#6CABDD", "#002B5C", 3236),
    "montpellier": ("مون‌پلیه", "MTP", "#003B71", "#F36E21", 274),
}

_BY_TLA: dict[str, tuple[str, str, str, str, int]] = {v[1]: v for v in UCL_CLUBS_MASTER.values()}
_BY_FA: dict[str, tuple[str, str, str, str, int]] = {v[0]: v for v in UCL_CLUBS_MASTER.values()}
_BY_ESPN: dict[int, tuple[str, str, str, str, int]] = {v[4]: v for v in UCL_CLUBS_MASTER.values()}


def lookup_ucl_club(
    name: str | None = None,
    *,
    tla_hint: str | None = None,
    espn_id: int | None = None,
) -> tuple[str, str, str, str, int] | None:
    """یافتن اطلاعات کامل باشگاه چمپیونزلیگ: `(name_fa, tla, primary_hex, secondary_hex, espn_id)`."""
    if espn_id and int(espn_id) in _BY_ESPN:
        return _BY_ESPN[int(espn_id)]
    if tla_hint:
        t = str(tla_hint).strip().upper()[:3]
        if t in _BY_TLA:
            return _BY_TLA[t]
    nm = str(name or "").strip()
    if not nm:
        return None
    if nm in _BY_FA:
        return _BY_FA[nm]
    low = nm.lower()
    if low in UCL_CLUBS_MASTER:
        return UCL_CLUBS_MASTER[low]
    if low.upper()[:3] in _BY_TLA and len(low) <= 4:
        return _BY_TLA[low.upper()[:3]]
    for k, v in UCL_CLUBS_MASTER.items():
        if k in low or low in k:
            return v
    return None


def get_ucl_badge_data_uri(
    name: str | None = None,
    *,
    tla_hint: str | None = None,
    espn_id: int | None = None,
    fetch_network: bool = True,
    timeout: float = 4.5,
) -> str | None:
    """برگرداندن لوگوی رسمی باشگاه چمپیونزلیگ (PNG کش‌شده از ESPN یا SVG محلی ۱۰۰٪ آفلاین)."""
    info = lookup_ucl_club(name, tla_hint=tla_hint, espn_id=espn_id)
    if not info:
        return None
    _, tla, _, _, eid = info

    # ۱) کش دیسک PNG رسمی
    BADGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_p = BADGE_CACHE_DIR / f"ucl_{tla.lower()}.png"
    if cache_p.exists() and cache_p.stat().st_size > 400:
        return "data:image/png;base64," + base64.b64encode(cache_p.read_bytes()).decode("ascii")

    # ۲) دانلود از ESPN CDN رسمی (بدون requests)
    if fetch_network and eid:
        url = f"https://a.espncdn.com/i/teamlogos/soccer/500/{eid}.png"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/png,image/*"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read(512_000)
            if len(raw) > 400:
                cache_p.write_bytes(raw)
                return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
        except Exception:
            pass

    # ۳) پشتیبان ۱۰۰٪ آفلاین SVG برداری محلی
    svg_p = LOCAL_CRESTS_DIR / f"{tla}.svg"
    if svg_p.exists():
        return "data:image/svg+xml;base64," + base64.b64encode(svg_p.read_bytes()).decode("ascii")
    return None
