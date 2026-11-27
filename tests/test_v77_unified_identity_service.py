"""تست‌های نسخه v0.77.0 — سرویس واحد هویت نام‌ها (Unified Identity Service) با کش LRU و یکتایی کامل."""
from __future__ import annotations


def test_unified_identity_service_player_consistency_and_lru_cache() -> None:
    """هر ۳ مسیر (identity_service، config.translate_player_fa، injury_free) باید خروجی کاملاً یکسان بدهند."""
    from src.xgpedia.config import translate_player_fa
    from src.xgpedia.core.identity_service import (
        clear_identity_caches,
        get_unified_player_map,
        resolve_player_name_fa,
    )
    from src.xgpedia.providers.injury_free import transliterate_player_name_fa

    clear_identity_caches()
    umap = get_unified_player_map()
    assert len(umap) >= 277

    samples = (
        ("Bruno Fernandes", "برونو فرناندز"),
        ("B.Fernandes", "برونو فرناندز"),
        ("B. Fernandes", "برونو فرناندز"),
        ("Erling Haaland", "ارلینگ هالند"),
        ("Kylian Mbappé", "کیلیان امباپه"),
        ("Bukayo Saka", "بوکایو ساکا"),
    )
    for raw, expected_fa in samples:
        r_svc = resolve_player_name_fa(raw)
        r_cfg = translate_player_fa(raw)
        r_inj = transliterate_player_name_fa(raw)
        assert r_svc == expected_fa, f"Expected {expected_fa} for {raw}, got {r_svc}"
        assert r_cfg == r_svc, f"config mismatch for {raw}: {r_cfg} != {r_svc}"
        assert r_inj == r_svc, f"injury_free mismatch for {raw}: {r_inj} != {r_svc}"

    # بررسی فعال‌بودن کش LRU
    info = resolve_player_name_fa.cache_info()
    assert info.hits >= len(samples) * 2


def test_unified_identity_service_team_resolution_and_audit() -> None:
    """سرویس واحد باید هویت باشگاه و ممیزی یکتایی ۱۵۱ باشگاه را با کش LRU برگرداند."""
    from src.xgpedia.core.identity_service import (
        audit_identity_consistency,
        clear_identity_caches,
        resolve_team_identity,
    )

    clear_identity_caches()
    t1 = resolve_team_identity("Newcastle")
    t2 = resolve_team_identity("Newcastle")
    assert t1["canonical"] == "Newcastle United"
    assert t1["code"] == "NEW"
    assert t1["name_fa"] == "نیوکاسل"
    assert t1["stadium_fa"]
    assert resolve_team_identity.cache_info().hits >= 1

    audit = audit_identity_consistency()
    assert audit["clubs_count"] == 151
    assert audit["clubs_symmetric_1to1"] is True
    assert audit["duplicate_club_codes"] is False
    assert audit["windows_reserved_codes"] == []
    assert audit["unified_player_entries"] >= 277
