"""موتور پلاگین‌پذیر زنجیرهٔ اولویت‌بندی منابع داده (`DataSourceChain`) بر اساس اعتبار منبع (v0.59.0).

طراحی:
  - هر کارت در `config/data_source_chains.json` فهرست دقیق فیلدهای مورد نیاز و دامنه‌های داده‌ای خود را دارد.
  - هر منبع داده دارای `authority_score` (امتیاز اعتبار ۰ تا ۱۰۰) است.
  - با افزودن هر منبع جدید از طریق `register()` یا اضافه کردن به `config/data_source_chains.json`،
    منبع جدید به‌طور خودکار بر اساس امتیاز اعتبار در جایگاه درست زنجیره قرار می‌گیرد (معتبرتر = اولویت بالاتر).
  - موتور در زمان اجرا با `api_health` هماهنگ است: منابع دارای کلید تنظیم‌نشده رد می‌شوند و منابع در وضعیت
    cooldown موقتاً به انتهای صف منتقل می‌شوند تا پایداری ۱۰۰٪ حفظ شود.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from src.xgpedia.config import ROOT
from src.xgpedia.core import api_health

log = logging.getLogger(__name__)

CHAINS_CONFIG_FILE = ROOT / "config" / "data_source_chains.json"


@dataclass
class SourceCandidate:
    """یک منبع داده در زنجیره با امتیاز اعتبار مشخص (۰ تا ۱۰۰)."""

    provider_id: str
    authority_score: int
    label_fa: str
    fetcher: Callable[..., Any] | None = None
    requires_env: str | None = None
    coverage: str = "all_6_leagues"
    tier: str = "verified_api"
    health_key: str = ""

    def is_available(self) -> bool:
        if self.requires_env:
            return bool((os.getenv(self.requires_env) or "").strip())
        return True

    @property
    def effective_health_key(self) -> str:
        return self.health_key or f"chain:{self.provider_id}"


@dataclass
class ChainResolution:
    """نتیجهٔ اجرای زنجیره همراه با منبع برنده و گزارش تلاش‌ها."""

    ok: bool
    provider_id: str = ""
    authority_score: int = 0
    data: Any = None
    attempts: list[str] = field(default_factory=list)


class DataSourceChain:
    """زنجیرهٔ پویا و مرتب‌شوندهٔ منابع داده بر اساس `authority_score` (بالاتر = معتبرتر)."""

    def __init__(self, domain: str, candidates: list[SourceCandidate] | None = None) -> None:
        self.domain = domain
        self._candidates: list[SourceCandidate] = []
        for c in candidates or []:
            self.register(c)

    def register(self, candidate: SourceCandidate) -> None:
        """افزودن یا به‌روزرسانی یک منبع در زنجیره و مرتب‌سازی خودکار بر اساس امتیاز اعتبار (نزولی)."""
        self._candidates = [c for c in self._candidates if c.provider_id != candidate.provider_id]
        self._candidates.append(candidate)
        self._candidates.sort(key=lambda c: c.authority_score, reverse=True)

    def ordered_candidates(self, *, respect_health: bool = True) -> list[SourceCandidate]:
        """فهرست منابع فعال مرتب‌شده از معتبرترین به ضعیف‌ترین (منابع در cooldown به انتها می‌روند)."""
        active = [c for c in self._candidates if c.is_available()]
        if not respect_health:
            return active
        healthy: list[SourceCandidate] = []
        cooling: list[SourceCandidate] = []
        for c in active:
            if api_health.is_in_cooldown(c.effective_health_key):
                cooling.append(c)
            else:
                healthy.append(c)
        return healthy + cooling

    def resolve(
        self,
        *args: Any,
        validator: Callable[[Any], bool] | None = None,
        respect_health: bool = True,
        **kwargs: Any,
    ) -> ChainResolution:
        """اجرای زنجیره به ترتیب اعتبار تا اولین منبع معتبر؛ با ثبت خودکار سلامت در `api_health`."""
        attempts: list[str] = []
        for cand in self.ordered_candidates(respect_health=respect_health):
            if cand.fetcher is None:
                attempts.append(f"{cand.provider_id}(score={cand.authority_score}): no fetcher")
                continue
            t0 = time.perf_counter()
            try:
                res = cand.fetcher(*args, **kwargs)
                valid = validator(res) if validator else (res is not None)
                if valid:
                    api_health.record_success(cand.effective_health_key, (time.perf_counter() - t0) * 1000.0)
                    attempts.append(f"{cand.provider_id}(score={cand.authority_score}): OK")
                    return ChainResolution(
                        ok=True,
                        provider_id=cand.provider_id,
                        authority_score=cand.authority_score,
                        data=res,
                        attempts=attempts,
                    )
                attempts.append(f"{cand.provider_id}(score={cand.authority_score}): empty")
            except Exception as e:
                api_health.record_failure(cand.effective_health_key, f"{type(e).__name__}: {e}")
                attempts.append(f"{cand.provider_id}(score={cand.authority_score}): {type(e).__name__}")
        return ChainResolution(ok=False, attempts=attempts)


# ─── خواندن رجیستری مرکزی JSON و نقشهٔ امتیاز اعتبار ──────────────────────────

@lru_cache(maxsize=1)
def load_data_source_chains(path: Path | None = None) -> dict[str, Any]:
    p = path or CHAINS_CONFIG_FILE
    if not p.exists():
        return {"domain_chains": {}, "cards": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def get_domain_authority_map(domain: str) -> dict[str, int]:
    """برگرداندن دیکشنری `{provider_id: authority_score}` برای یک دامنه (مثل `match_xg_and_shotmap`)."""
    cfg = load_data_source_chains()
    entries = (cfg.get("domain_chains") or {}).get(domain) or []
    return {str(e["provider_id"]): int(e.get("authority_score") or 0) for e in entries if e.get("provider_id")}


def provider_priority_rank(provider_id: str, domain: str = "match_xg_and_shotmap") -> int:
    """رتبهٔ عددی برای مقایسه/مرتب‌سازی در دیتابیس (عدد بزرگ‌تر = منبع معتبرتر)."""
    return get_domain_authority_map(domain).get(str(provider_id or "").strip(), 0)


def get_card_blueprint(card_id: str) -> dict[str, Any] | None:
    """برگرداندن نقشهٔ کامل یک کارت: فیلدهای مورد نیاز + زنجیرهٔ مرتب‌شدهٔ منابع هر دامنه."""
    cfg = load_data_source_chains()
    card = (cfg.get("cards") or {}).get(card_id)
    if not isinstance(card, dict):
        return None
    dom_chains = cfg.get("domain_chains") or {}
    resolved_chains: dict[str, list[dict[str, Any]]] = {}
    for d in card.get("domains") or []:
        items = list(dom_chains.get(d) or [])
        items.sort(key=lambda x: int(x.get("authority_score") or 0), reverse=True)
        resolved_chains[d] = [
            {
                **it,
                "configured": (not it.get("requires_env")) or bool((os.getenv(str(it["requires_env"])) or "").strip()),
            }
            for it in items
        ]
    return {
        "card_id": card_id,
        "title_fa": card.get("title_fa", card_id),
        "required_fields": list(card.get("required_fields") or []),
        "chains": resolved_chains,
    }


def list_all_card_blueprints() -> list[dict[str, Any]]:
    cfg = load_data_source_chains()
    out: list[dict[str, Any]] = []
    for cid in (cfg.get("cards") or {}):
        bp = get_card_blueprint(cid)
        if bp:
            out.append(bp)
    return out


def format_chains_report_fa(card_id: str | None = None) -> str:
    """گزارش خوانای فارسی از تمامی کارت‌ها، فیلدهای مورد نیاز و زنجیرهٔ اولویت‌بندی منابع آن‌ها."""
    bps = [get_card_blueprint(card_id)] if card_id else list_all_card_blueprints()
    bps = [b for b in bps if b]
    if not bps:
        return f"کارتی با شناسهٔ «{card_id}» یافت نشد."
    lines: list[str] = [f"=== زنجیرهٔ اولویت‌بندی منابع دادهٔ XGPedia ({len(bps)} کارت) ==="]
    for bp in bps:
        lines.append(f"\n[{bp['card_id']}] {bp['title_fa']}")
        lines.append("  فیلدهای مورد نیاز: " + "، ".join(bp["required_fields"]))
        for dom, srcs in bp["chains"].items():
            chain_str = " → ".join(
                f"{'✅' if s['configured'] else '🔑'}{s['provider_id']}({s['authority_score']})"
                for s in srcs
            )
            lines.append(f"  • {dom}: {chain_str}")
    return "\n".join(lines)
