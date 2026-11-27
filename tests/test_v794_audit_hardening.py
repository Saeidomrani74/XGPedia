"""تست‌های رگرسیون ممیزی جامع v0.79.4 (برگرفته از هر ۳ گزارش تحلیلی)."""
from __future__ import annotations

import ast
import builtins
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BUILTINS = set(dir(builtins)) | {
    "__name__", "__file__", "__doc__", "__package__", "__spec__", "__all__", "__annotations__",
}


def _scan_undefined_names(path: Path) -> list[tuple[int, str]]:
    """بررسی ایستا برای نام‌های تعریف‌نشده (معادل Ruff F821، بدون نیاز به ابزار بیرونی)."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))
    if any(isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names) for n in ast.walk(tree)):
        return []
    has_future_ann = any(
        isinstance(n, ast.ImportFrom) and n.module == "__future__" and any(a.name == "annotations" for a in n.names)
        for n in tree.body
    )

    def _collect_defs(node: ast.AST, scope: set[str]) -> None:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                nm = alias.asname or alias.name.split(".")[0]
                if nm != "*":
                    scope.add(nm)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            scope.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                for sub in ast.walk(t):
                    if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                        scope.add(sub.id)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            if isinstance(node.target, ast.Name):
                scope.add(node.target.id)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            for sub in ast.walk(node.target):
                if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                    scope.add(sub.id)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars:
                    for sub in ast.walk(item.optional_vars):
                        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                            scope.add(sub.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            scope.add(node.name)
        elif isinstance(node, ast.NamedExpr):
            scope.add(node.target.id)

    def _collect_block(stmts: list[ast.stmt], scope: set[str]) -> None:
        for s in stmts:
            _collect_defs(s, scope)
            for sub in ast.walk(s):
                if isinstance(sub, ast.NamedExpr):
                    scope.add(sub.target.id)
            if isinstance(s, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try)):
                for attr in ("body", "orelse", "finalbody"):
                    sub_b = getattr(s, attr, None)
                    if isinstance(sub_b, list):
                        _collect_block(sub_b, scope)
                if isinstance(s, ast.Try):
                    for h in s.handlers:
                        if h.name:
                            scope.add(h.name)
                        _collect_block(h.body, scope)

    mod_globals = set(BUILTINS)
    _collect_block(tree.body, mod_globals)
    undef: list[tuple[int, str]] = []

    def _visit_scope(node: ast.AST, parent: set[str]) -> None:
        local = set(parent)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            for a in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs):
                local.add(a.arg)
            if args.vararg:
                local.add(args.vararg.arg)
            if args.kwarg:
                local.add(args.kwarg.arg)
            _collect_block(node.body, local)
            _check_exprs(node.body, local)
        elif isinstance(node, ast.ClassDef):
            for s in node.body:
                if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    _visit_scope(s, parent)

    def _check_exprs(nodes: list[ast.AST], scope: set[str]) -> None:
        for n in nodes:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                _visit_scope(n, scope)
                continue
            if isinstance(n, ast.Lambda):
                lscope = set(scope)
                for a in list(n.args.posonlyargs) + list(n.args.args) + list(n.args.kwonlyargs):
                    lscope.add(a.arg)
                if n.args.vararg:
                    lscope.add(n.args.vararg.arg)
                if n.args.kwarg:
                    lscope.add(n.args.kwarg.arg)
                _check_exprs([n.body], lscope)
                continue
            if isinstance(n, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
                cscope = set(scope)
                for gen in n.generators:
                    _check_exprs([gen.iter], cscope)
                    for sub in ast.walk(gen.target):
                        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                            cscope.add(sub.id)
                    _check_exprs(gen.ifs, cscope)
                if isinstance(n, ast.DictComp):
                    _check_exprs([n.key, n.value], cscope)
                else:
                    _check_exprs([n.elt], cscope)
                continue
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                if n.id not in scope:
                    undef.append((n.lineno, n.id))
                continue
            for field, val in ast.iter_fields(n):
                if has_future_ann and field in ("annotation", "returns"):
                    continue
                if isinstance(val, list):
                    _check_exprs([x for x in val if isinstance(x, ast.AST)], scope)
                elif isinstance(val, ast.AST):
                    _check_exprs([val], scope)

    _check_exprs(tree.body, mod_globals)
    return undef


def test_zero_undefined_names_in_xg_engine_playwright_and_entire_src():
    targets = sorted(list((ROOT / "src").rglob("*.py")) + [ROOT / "run.py"])
    failures: dict[str, list[tuple[int, str]]] = {}
    for p in targets:
        hits = _scan_undefined_names(p)
        if hits:
            failures[str(p.relative_to(ROOT))] = hits
    assert failures == {}, f"Undefined names detected: {failures}"


def test_zero_b023_loop_closures_in_fixed_modules():
    for rel in (
        "src/xgpedia/providers/birthday_free.py",
        "src/xgpedia/providers/open_football_hub.py",
        "src/xgpedia/sync.py",
    ):
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        leaks = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.For, ast.AsyncFor)):
                loop_vars = {n.id for n in ast.walk(node.target) if isinstance(n, ast.Name)}
                for sub in ast.walk(node):
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                        args = sub.args
                        params = {a.arg for a in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)}
                        body_nodes = sub.body if isinstance(sub.body, list) else [sub.body]
                        used = {n.id for bn in body_nodes for n in ast.walk(bn) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
                        bad = (used & loop_vars) - params
                        if bad:
                            leaks.append((sub.lineno, sorted(bad)))
        assert leaks == [], f"B023 loop closure in {rel}: {leaks}"


def test_psxg_not_fabricated_from_xgc_or_opp_xg():
    from src.xgpedia.providers.fpl_free import parse_fpl_match_post_details
    from src.xgpedia.providers.xg_engine_fotmob import parse_fotmob_match_details

    # FPL: expected_goals_conceded must stay xgc, never relabeled as psxg; missing squad_number -> None
    bs = {
        "teams": [{"id": 1, "name": "Arsenal"}, {"id": 2, "name": "Chelsea"}],
        "elements": [
            {"id": 10, "team": 1, "element_type": 1, "web_name": "Raya"},
            {"id": 11, "team": 1, "element_type": 3, "web_name": "Saka", "squad_number": 7},
            {"id": 12, "team": 2, "element_type": 1, "web_name": "Sanchez", "squad_number": 1},
            {"id": 13, "team": 2, "element_type": 3, "web_name": "Palmer", "squad_number": 20},
        ],
    }
    fxs = [{"id": 1, "team_h": 1, "team_a": 2, "team_h_score": 1, "team_a_score": 0, "kickoff_time": "2026-11-26T18:00:00Z"}]
    live_gw = {
        "elements": [
            {"id": 10, "explain": [{"fixture": 1}], "stats": {"minutes": 90, "bps": 30, "saves": 4, "expected_goals_conceded": 0.95}},
            {"id": 11, "explain": [{"fixture": 1}], "stats": {"minutes": 90, "bps": 40, "goals_scored": 1, "expected_goals": 0.6}},
            {"id": 12, "explain": [{"fixture": 1}], "stats": {"minutes": 90, "bps": 22, "saves": 3, "expected_goals_conceded": 1.45}},
            {"id": 13, "explain": [{"fixture": 1}], "stats": {"minutes": 90, "bps": 20, "expected_goals": 0.35}},
        ]
    }
    det = parse_fpl_match_post_details(bs, fxs, live_gw, "Arsenal", "Chelsea", "2026-11-26")
    assert det is not None
    assert det["home_gk"]["psxg"] is None
    assert det["home_gk"]["xgc"] == 0.95
    assert det["away_gk"]["psxg"] is None
    assert det["away_gk"]["xgc"] == 1.45

    # FotMob: when xGOT faced is missing, do NOT fall back to opponent pre-shot xG
    payload = {
        "general": {"homeTeam": {"id": 1, "name": "Arsenal"}, "awayTeam": {"id": 2, "name": "Chelsea"}},
        "header": {"teams": [{"id": 1, "score": 1}, {"id": 2, "score": 0}]},
        "content": {
            "stats": {"Periods": {"All": {"stats": [{"stats": [{"key": "expected_goals", "stats": ["1.50", "0.80"]}]}]}}},
            "lineup": {
                "lineup": [
                    {"players": [[{"id": "10", "name": {"fullName": "David Raya"}, "positionId": 11, "usualPosition": 0, "performance": {"rating": 7.6}}]]},
                    {"players": [[{"id": "20", "name": {"fullName": "Robert Sanchez"}, "positionId": 11, "usualPosition": 0, "performance": {"rating": 6.8}}]]},
                ]
            },
            "playerStats": {
                "10": {"stats": [{"title": "Top stats", "stats": {"Saves": {"key": "saves", "stat": {"value": 3}}}}]},
                "20": {"stats": [{"title": "Top stats", "stats": {"Saves": {"key": "saves", "stat": {"value": 4}}}}]},
            },
        },
    }
    fm = parse_fotmob_match_details(payload)
    assert "home_gk" not in fm and "away_gk" not in fm


def test_standings_presets_have_visible_sample_badge():
    from src.xgpedia.providers.standings_free import load_standings_presets
    from src.xgpedia.render.card_kit.standings_card import render_standings_html

    presets = load_standings_presets()
    assert presets, "Expected standings presets"
    assert presets[0].get("is_preset") is True
    html = render_standings_html(presets[0], fmt="4:5")
    assert "نمونه • SAMPLE" in html
    assert "XGPedia Sample" in html


def test_admin_telegram_ids_safe_parsing():
    from src.xgpedia.config import _parse_admin_telegram_ids

    assert _parse_admin_telegram_ids("123, bad_id, 456, , xyz") == frozenset({123, 456})
    assert _parse_admin_telegram_ids("") == frozenset()


def test_match_facts_preserves_real_per_metric_provider():
    from src.xgpedia import db as db_mod
    from src.xgpedia.sync import build_match_facts, merge_post_match_details, sync_espn_finished_matches

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "lineage.db"
        with patch.object(db_mod, "DATABASE_PATH", db_path):
            db_mod.init_db()
            sync_espn_finished_matches([{
                "event_id": "777",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "kickoff_utc": "2026-11-26T18:00:00Z",
                "home_goals": 2,
                "away_goals": 1,
                "home_stats": {"possession": 58.0, "total_shots": 14.0},
                "away_stats": {"possession": 42.0, "total_shots": 8.0},
            }], season_start=2026)
            merge_post_match_details(
                "espn:777",
                {},
                provider="fotmob",
                extra_stats={"Arsenal": {"expected_goals": 1.85}, "Chelsea": {"expected_goals": 0.92}},
            )
            facts = build_match_facts("espn:777", post_match=True)
            assert facts["home"]["match_stats"]["expected_goals"]["provider"] == "fotmob"
            assert facts["home"]["match_stats"]["possession"]["provider"].startswith("espn")


def test_dead_j2_templates_and_jinja2_removed():
    assert list((ROOT / "src").rglob("*.j2")) == []
    assert "jinja2" not in (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    assert "C:\\Users\\saeid" not in (ROOT / "PROJECT_BIBLE_AND_ROADMAP.md").read_text(encoding="utf-8")


def test_db_schema_has_no_duplicate_create_table():
    import collections
    import re
    from src.xgpedia import db as db_mod

    db_src = (ROOT / "src" / "xgpedia" / "db.py").read_text(encoding="utf-8")
    counts = collections.Counter(re.findall(r"CREATE TABLE IF NOT EXISTS\s+(\w+)", db_src))
    dups = {k: v for k, v in counts.items() if v != 1}
    assert dups == {}, f"Duplicate CREATE TABLE in db.py: {dups}"
    assert len(counts) >= 16

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "unified.db"
        with patch.object(db_mod, "DATABASE_PATH", db_path):
            db_mod.init_db()
            with db_mod.db() as conn:
                tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for expected in ("fixtures", "posts", "bot_kv_state", "post_metrics", "api_hydration_cache"):
                assert expected in tables


def test_all_card_renderers_support_universal_sample_badge():
    from src.xgpedia.render.card_kit.helpers import inject_sample_badge_html

    sample_html = "<html><body><div>card</div></body></html>"
    marked = inject_sample_badge_html(sample_html, {"id": "preset_demo", "is_preset": True})
    assert "xg-sample-pill" in marked and "SAMPLE" in marked
    live = inject_sample_badge_html(sample_html, {"id": "live_1", "is_preset": False})
    assert live == sample_html

    for p in sorted((ROOT / "src" / "xgpedia" / "render" / "card_kit").glob("*_card.py")):
        src = p.read_text(encoding="utf-8")
        assert ("@with_sample_badge" in src) or ("sample_badge_html" in src), f"{p.name} missing sample badge wiring"
