"""Tests for the detector-evaluation harness. No API calls (regex only, plus a scripted predictor)."""

from __future__ import annotations

import pytest

from testbed.defenses.detector_eval import Scores, evaluate, load_split, regex_predicts


def test_scores_metrics() -> None:
    s = Scores()
    for pred, truth in [(True, True), (True, True), (False, True), (True, False), (False, False)]:
        s.add(pred, truth)
    assert (s.tp, s.fp, s.tn, s.fn) == (2, 1, 1, 1)
    assert s.precision == pytest.approx(2 / 3)
    assert s.recall == pytest.approx(2 / 3)
    assert s.f1 == pytest.approx(2 / 3)
    assert s.accuracy == pytest.approx(3 / 5)


def test_scores_empty_denominators_are_zero() -> None:
    s = Scores()
    assert s.precision == 0.0 and s.recall == 0.0 and s.f1 == 0.0 and s.accuracy == 0.0


def test_evaluate_counts_a_perfect_predictor() -> None:
    rows = [("x", 1), ("y", 0)]
    s = evaluate(rows, lambda t: t == "x")
    assert (s.tp, s.tn, s.fp, s.fn) == (1, 1, 0, 0) and s.f1 == 1.0


def test_regex_run_saves_scores_with_provenance(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import json

    from testbed.defenses.detector_eval import main

    main(["--split", "test", "--limit", "20", "--out", str(tmp_path)])  # regex only: free, no API
    record = json.loads((tmp_path / "test.json").read_text(encoding="utf-8"))
    assert record["prompts"] == 20 and set(record["detectors"]) == {"regex"}
    assert record["detectors"]["regex"]["n"] == 20
    assert record["dataset_revision"].startswith("4f61ecb") and record["git_commit"]


def test_dry_run_saves_nothing(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from testbed.defenses.detector_eval import main

    main(["--split", "test", "--limit", "3", "--llm", "--dry-run", "--out", str(tmp_path)])
    assert list(tmp_path.iterdir()) == []


def test_regex_on_real_data_has_signal() -> None:
    rows = load_split("test")
    assert len(rows) == 116
    s = evaluate(rows, regex_predicts)
    # The regex is a weak heuristic, but it must do better than chance: more true than false
    # positives, and it must not flag everything (some benign prompts pass).
    assert s.tp > s.fp and s.tn > 0 and s.recall > 0
