"""The held-out seeds run once; gates read the right numbers; reports are generated."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentinel import cli, config
from sentinel.lab import report, study


def test_heldout_runs_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(study, "REPORTS", tmp_path)
    monkeypatch.setattr(study, "LOCK", tmp_path / "heldout.lock")
    calls: list[str] = []
    monkeypatch.setattr(study, "run_split", lambda split: calls.append(split) or {"designs": {"platform": {"metrics": {"value_share": 0.5, "precision": 0.9}}}, "gates": {"platform_pass": True}})
    assert cli.main(["run", "heldout"]) == 0
    assert cli.main(["run", "heldout"]) == 3
    assert calls == ["heldout"]
    assert "config_sha256" in json.loads((tmp_path / "heldout.lock").read_text())


def test_gates_compare_against_the_right_side() -> None:
    m = {
        "value_share": 0.8,
        "precision": 0.9,
        "minutes_per_week": 100.0,
        "decision_median_h": 10.0,
        "injection_cards": 0,
        "namesake_cards": 0,
        "wrong_entity_cards": 0,
        "rumour_cards": 0,
        "duplicate_cards": 0,
        "cost_per_accepted_card_eur": 0.01,
    }
    sq = {**m, "value_share": 0.7, "minutes_per_week": 300.0}
    res = {"designs": {"platform": {"metrics": m}, "status_quo": {"metrics": sq}}, "model_swap": []}
    g = study.check_gates(res, config.gates())
    assert g["platform_pass"]
    res["designs"]["platform"]["metrics"] = {**m, "injection_cards": 1}
    assert not study.check_gates(res, config.gates())["platform_pass"]


def test_the_committed_dev_report_passes_its_gates_and_renders() -> None:
    dev = json.loads((config.REPORTS / "dev.json").read_text())
    assert dev["gates"]["platform_pass"]
    md = report.report_md()
    assert "## Development seeds" in md and "### Gates" in md
    assert report.START in report.readme_block() and report.END in report.readme_block()
