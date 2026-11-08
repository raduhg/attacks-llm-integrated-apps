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


def test_regex_on_real_data_has_signal() -> None:
    rows = load_split("test")
    assert len(rows) == 116
    s = evaluate(rows, regex_predicts)
    # The regex is a weak heuristic, but it must do better than chance: more true than false
    # positives, and it must not flag everything (some benign prompts pass).
    assert s.tp > s.fp and s.tn > 0 and s.recall > 0
