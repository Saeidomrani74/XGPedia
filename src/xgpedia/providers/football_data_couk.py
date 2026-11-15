"""آداپتر football-data.co.uk — منبع اصلی xG و آمار مسابقه (تصمیم D4/D5، نسخهٔ ۸).

درس FBref: هر provider یک آداپتر مستقل با خروجی schema داخلی.
این منبع CSV هفتگی است (نه API): فایل mmz4281/<YY><YY+1>/E0.csv برای لیگ برتر.

راستی‌آزمایی ۱۵ نوامبر ۲۰۲۶:
  - فصل ۲۰۲۷–۲۰۲۶: ۱۰۰ بازی تا ۸ نوامبر، ستون‌های HxG/AxG در ۱۰۰٪ رکوردها پر است.
  - فصل ۲۰۲۶–۲۰۲۵: ۳۸۰ بازی کامل شوت/کرنر؛ ستون xG خالی است (xG از فصل ۲۷-۲۶ اضافه شده).
  - تاریخ‌ها فرمت dd/mm/yyyy انگلیسی‌اند؛ نام تیم‌ها کوتاه («Man City»).

قواعد لایهٔ Ingestion عیناً برقرار است: پاسخ خام (CSV) با sha256 ذخیره
می‌شود، هر عدد تا فایل خام ردیابی‌پذیر است و null یعنی «داده نیست».
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from src.xgpedia.config import RAW_PAYLOAD_DIR, TEAM_MAPPING_FILE, load_team_mapping

PROVIDER = "football-data-co-uk"
BASE = "https://www.football-data.co.uk"
LEAGUE_PL = "E0"  # Premier League

# فصل CSV: کلید «سال شروع» فصل → کد پوشهٔ mmz4281/<YY><YY+1>.
# فصل ۲۰۲۶–۲۰۲۷ (سال شروع ۲۰۲۶) → پوشهٔ 2627.
SEASON_CSV = {
    2025: "2526",  # فصل ۲۰۲۵–۲۰۲۶
    2026: "2627",  # فصل ۲۰۲۶–۲۰۲۷ (جاری)
}

# ستون‌های آماری که خط تولید مصرف می‌کند — هر ستونِ خالی → None (هرگز 0).
CSV_STAT_COLUMNS = {
    "HS": "total_shots",
    "AS": "total_shots_away",          # در ذخیرهٔ per-team ترجمه می‌شود
    "HST": "shots_on_target",
    "AST": "shots_on_target_away",
    "HC": "corner_kicks",
    "AC": "corner_kicks_away",
    "HF": "fouls",
    "AF": "fouls_away",
    "HY": "yellow_cards",
    "AY": "yellow_cards_away",
    "HR": "red_cards",
    "AR": "red_cards_away",
}


@dataclass
class CsvMatchRow:
    """یک ردیف نرمال‌شدهٔ CSV — واحد سازندهٔ fixtures و statistics."""

    date_utc: str                # ISO yyyy-mm-dd (بازی‌ها بعدازظهر انگلیس‌اند؛ تاریخ محلی حفظ می‌شود)
    home_team: str               # نام canonical (نگاشت از csv_short)
    away_team: str
    home_goals: int
    away_goals: int
    home_xg: float | None        # None = فایل xG نداده (فصل‌های قدیمی)
    away_xg: float | None
    stats: dict[str, float | None]  # کلیدها: total_shots, shots_on_target, corner_kicks, ...
    referee: str | None


def _to_float(val: str | None) -> float | None:
    """رشتهٔ CSV به float — خالی/غیرعددی → None (قاعدهٔ null≠0)."""
    if val is None:
        return None
    v = val.strip()
    if v in {"", "None", "null", "NaN"}:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _to_int(val: str | None) -> int | None:
    f = _to_float(val)
    return int(f) if f is not None else None


class FootballDataCoUk:
    """دانلود و نرمال‌سازی CSV هفتگی — منبع xG مسابقه‌به‌مسابقه."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or (RAW_PAYLOAD_DIR / PROVIDER)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._client = httpx.Client(
            base_url=BASE,
            headers={"User-Agent": "XGPedia/0.8 (research; contact via channel)"},
            timeout=30.0,
            follow_redirects=True,  # football-data.co.uk با 302 به فایل می‌رسد
        )

    # ---------- دریافت و ذخیرهٔ خام ----------

    def download_season_csv(self, start_year: int) -> tuple[str, Path]:
        """دانلود CSV یک فصل؛ خروجی: (متن خام، مسیر ذخیره). hash از محتوا ساخته می‌شود."""
        code = SEASON_CSV.get(start_year)
        if code is None:
            raise ValueError(f"season {start_year} is not supported (only {sorted(SEASON_CSV)})")
        url_path = f"/mmz4281/{code}/{LEAGUE_PL}.csv"
        resp = self._client.get(url_path)
        if resp.status_code != 200:
            raise RuntimeError(f"CSV download failed: HTTP {resp.status_code} - check network/VPN and retry")
        text = resp.text
        if len(text) < 500 or text.lstrip().startswith("<"):
            raise RuntimeError("CSV response is not valid (HTML page or empty)")

        # ذخیرهٔ خام با sha256 — همان قاعدهٔ RawResponse
        payload_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        day = time.strftime("%Y-%m-%d", time.gmtime())
        out_dir = self.data_dir / day
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{LEAGUE_PL}_{code}_{payload_hash[:12]}.csv"
        if not out_file.exists():  # idempotent
            meta = {
                "provider": PROVIDER,
                "endpoint": url_path,
                "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "payload_hash": payload_hash,
                "http_status": 200,
            }
            out_file.write_text(
                json.dumps(meta, ensure_ascii=False) + "\n" + text, encoding="utf-8-sig"
            )
        return text, out_file

    # ---------- نرمال‌سازی ----------

    def parse_season(self, csv_text: str) -> list[CsvMatchRow]:
        """CSV خام → ردیف‌های نرمال. نام تیم از csv_short به canonical نگاشت می‌شود."""
        reader = csv.DictReader(io.StringIO(csv_text))

        mapping = load_team_mapping()
        csv_to_canonical = {
            t["csv_short"]: canonical for canonical, t in mapping["teams"].items()
        }
        csv_to_canonical.update({
            t["csv_short"]: canonical for canonical, t in mapping.get("relegated_2025_26", {}).items()
        })

        rows: list[CsvMatchRow] = []
        for r in reader:
            # ردیف‌های نیمه‌کارهٔ انتهای فایل (فقط برنامه، بدون نتیجه) رد می‌شوند
            hg = _to_int(r.get("FTHG"))
            ag = _to_int(r.get("FTAG"))
            if hg is None or ag is None:
                continue

            home_csv = (r.get("HomeTeam") or "").strip()
            away_csv = (r.get("AwayTeam") or "").strip()
            home = csv_to_canonical.get(home_csv, home_csv)
            away = csv_to_canonical.get(away_csv, away_csv)

            # تاریخ dd/mm/yyyy → yyyy-mm-dd (تاریخ محلی انگلیس، بدون تبدید timezone)
            d = (r.get("Date") or "").strip()
            try:
                dt = datetime.strptime(d, "%d/%m/%Y")
                date_iso = dt.strftime("%Y-%m-%d")
            except ValueError:
                continue  # ردیف بدون تاریخ معتبر → داده نیست

            # آمار خانگی/میهمانی به دو سوی مستقل تبدیل می‌شود
            home_xg = _to_float(r.get("HxG"))
            away_xg = _to_float(r.get("AxG"))

            rows.append(
                CsvMatchRow(
                    date_utc=date_iso,
                    home_team=home,
                    away_team=away,
                    home_goals=hg,
                    away_goals=ag,
                    home_xg=home_xg,
                    away_xg=away_xg,
                    stats={
                        "total_shots": _to_float(r.get("HS")),
                        "shots_on_target": _to_float(r.get("HST")),
                        "corner_kicks": _to_float(r.get("HC")),
                        "fouls": _to_float(r.get("HF")),
                        "yellow_cards": _to_float(r.get("HY")),
                        "red_cards": _to_float(r.get("HR")),
                        "total_shots_away": _to_float(r.get("AS")),
                        "shots_on_target_away": _to_float(r.get("AST")),
                        "corner_kicks_away": _to_float(r.get("AC")),
                        "fouls_away": _to_float(r.get("AF")),
                        "yellow_cards_away": _to_float(r.get("AY")),
                        "red_cards_away": _to_float(r.get("AR")),
                    },
                    referee=(r.get("Referee") or "").strip() or None,
                )
            )
        return rows

    # ---------- دسترسی راحت ----------

    def fetch_season_rows(self, start_year: int) -> tuple[list[CsvMatchRow], str, Path]:
        """دانلود + نرمال‌سازی در یک فراخوانی — خروجی: (ردیف‌ها، hash، مسیر خام)."""
        text, path = self.download_season_csv(start_year)
        rows = self.parse_season(text)
        payload_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return rows, payload_hash, path

    def close(self) -> None:
        self._client.close()


def season_label(start_year: int) -> str:
    """برچسب فصل به سبک سند: ۲۰۲۶ (سال شروع) → «2026-27»."""
    return f"{start_year}-{str(start_year + 1)[2:]}"
