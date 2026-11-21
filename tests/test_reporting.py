"""Tests for the reporting module on small synthetic results. No API calls."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from testbed.reporting.report import build_report, defense_metrics, model_comparison, rate


def attack(defense: str, ok: bool, category: str = "system_prompt_leakage", done: bool | None = True) -> dict[str, Any]:
    return {"defense": defense, "kind": "attack", "category": category, "attack_success": ok,
            "user_task_completed": done, "task_passed": None, "cost_usd": 0.001, "detector_cost_usd": 0.0}


def benign(defense: str, ok: bool) -> dict[str, Any]:
    return {"defense": defense, "kind": "benign", "category": "benign", "attack_success": None,
            "user_task_completed": None, "task_passed": ok, "cost_usd": 0.002, "detector_cost_usd": 0.0005}


def write_exp(results: Path, exp: str, rows: list[dict[str, Any]], reps: int = 5) -> None:
    d = results / exp
    d.mkdir(parents=True)
    (d / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    (d / "meta.json").write_text(json.dumps({"experiment": {"repetitions": reps}, "git_commit": "abcdef1234",
                                             "git_dirty": False, "finished_utc": "2026-11-21"}), encoding="utf-8")


def test_rate_and_not_measured() -> None:
    assert rate(0, 0)["rate"] is None
    r = rate(5, 10)
    assert r["rate"] == 0.5 and r["lo"] == pytest.approx(0.2366, abs=1e-4)


def test_defense_metrics_counts() -> None:
    rows = [attack("D0", True), attack("D0", False, done=False), benign("D0", True), benign("D0", False),
            attack("D2", False, category="data_exfiltration")]
    m = defense_metrics(rows)
    assert (m["D0"]["asr"]["k"], m["D0"]["asr"]["n"]) == (1, 2)
    assert (m["D0"]["utility"]["k"], m["D0"]["fpr"]["k"], m["D0"]["fpr"]["n"]) == (1, 1, 2)
    assert m["D0"]["cost_per_run"] == pytest.approx((0.001 * 2 + 0.0025 * 2) / 4)
    assert defense_metrics(rows, "data_exfiltration")["D0"]["asr"]["n"] == 0  # category filter


def test_model_comparison_prefers_more_attempts(tmp_path: Path) -> None:
    from testbed.reporting.report import load

    write_exp(tmp_path, "m6_weak_probe_haiku45", [attack("D0", True)] * 3, reps=3)
    write_exp(tmp_path, "m6_weak_haiku45_defenses", [attack("D0", True)] * 2 + [attack("D0", False)] * 8)
    data = {e: load(e, tmp_path) for e in ("m6_weak_probe_haiku45", "m6_weak_haiku45_defenses")}
    [(cat, model, profile, r, exp)] = model_comparison(data)
    assert (model, profile, r["k"], r["n"], exp) == ("Haiku 4.5", "weak", 2, 10, "m6_weak_haiku45_defenses")


def test_build_report_writes_every_output(tmp_path: Path) -> None:
    rows = [attack(d, d == "D0") for d in ("D0", "D1", "D2") for _ in range(4)] + [benign(d, True) for d in ("D0", "D1", "D2")]
    write_exp(tmp_path, "m6_weak_haiku45_defenses", rows)
    write_exp(tmp_path, "m5_defenses", [attack(d, False, "data_exfiltration") for d in ("D0", "D1")] + [benign("D1", False)])
    out = build_report(results=tmp_path)
    names = {p.name for p in out.iterdir()}
    assert {"tables.md", "fig_asr_heatmap.png", "fig_asr_fpr.png", "fig_tradeoff.png", "fig_models.png",
            "defenses_m6_weak_haiku45_defenses.csv", "defenses_m5_defenses.csv"} <= names
    tables = (out / "tables.md").read_text(encoding="utf-8")
    assert "| D0 | 4/4 (100%" in tables and "Haiku 4.5, weak profile" in tables
