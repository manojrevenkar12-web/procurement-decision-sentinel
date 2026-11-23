"""The truth stays in the world; the world does not read the sentinel's settings; the sentinel never imports the world."""

from __future__ import annotations

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "src" / "sentinel"
TRUTH = ("impacts", "near_misses", "tolerance", "events", "by_msg", "injection_targets", "has_capacity", "lookalike_of")


def _imports(path: Path) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.add(("." * node.level) + node.module)
        elif isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
    return out


def test_the_sentinel_and_the_api_never_import_the_world() -> None:
    guarded = list((PKG / "platform").glob("*.py")) + [PKG / "service" / "api.py", PKG / "service" / "store.py"]
    for path in guarded:
        for mod in _imports(path):
            assert "world" not in mod, f"{path.relative_to(PKG)} imports {mod}"
            assert "sim" not in mod.split("."), f"{path.relative_to(PKG)} imports {mod}"
            assert "lab" not in mod.split("."), f"{path.relative_to(PKG)} imports {mod}"


def test_only_the_world_the_simulation_and_the_evaluation_touch_the_truth() -> None:
    allowed = {PKG / "sim" / "evaluate.py", PKG / "sim" / "simulate.py", PKG / "lab" / "study.py"}
    for path in PKG.rglob("*.py"):
        if path.parent == PKG / "world" or path in allowed:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and node.attr in TRUTH:
                raise AssertionError(f"{path.relative_to(PKG)} reads {node.attr}")


def test_the_simulation_hands_the_sentinel_only_master_data_and_messages() -> None:
    src = (PKG / "sim" / "simulate.py").read_text(encoding="utf-8")
    assert "Sentinel(self.md," in src and "sentinel.handle(msg," in src


def test_the_world_does_not_read_the_sentinel_settings() -> None:
    for path in (PKG / "world").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "platform.yml" not in text and "config.platform" not in text, path.name
        for mod in _imports(path):
            assert "platform" not in mod.split("."), f"world/{path.name} imports {mod}"


def test_the_sentinel_reads_only_its_own_settings() -> None:
    for path in (PKG / "platform").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "world.yml" not in text and "gates.yml" not in text and "designs.yml" not in text, path.name


def test_the_model_never_decides_categories_or_money_in_the_sentinel() -> None:
    src = (PKG / "platform" / "pipeline.py").read_text(encoding="utf-8")
    assert "affected_categories" not in src and "urgency" not in src
