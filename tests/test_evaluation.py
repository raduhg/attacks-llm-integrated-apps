"""Tests for the experiment runner, config validation and metrics. No API calls."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from testbed.app.rag import Chunk
from testbed.config import load_models
from testbed.evaluation.config import ExperimentConfig, load_experiment
from testbed.evaluation.metrics import aggregate, wilson
from testbed.evaluation.run import run_experiment, write_meta, write_summary
from testbed.llm import AnthropicBackend

CFG = dict(
    id="t", budget_usd=1.0, repetitions=2,
    attacks=["data/attacks/m3_initial.yaml"], benign=["data/benign_tasks/m2_smoke.yaml"],
)


# --- metrics ------------------------------------------------------------------


def test_wilson_known_values() -> None:
    assert wilson(0, 10) == pytest.approx((0.0, 0.2775), abs=1e-4)
    assert wilson(5, 10) == pytest.approx((0.2366, 0.7634), abs=1e-4)
    assert wilson(10, 10) == pytest.approx((0.7225, 1.0), abs=1e-4)


def row(kind: str, item: str, rep: int, ok: bool, category: str = "exfil", utility: bool | None = None) -> dict[str, Any]:
    return {
        "defense": "D0", "kind": kind, "item_id": item, "repetition": rep, "category": category,
        "vector": "indirect" if kind == "attack" else "none", "stop_reason": "end_turn",
        "attack_success": ok if kind == "attack" else None, "task_passed": ok if kind == "benign" else None,
        "user_task_completed": utility, "input_tokens": 100, "output_tokens": 10, "cost_usd": 0.001, "latency_s": 1.0,
    }


def test_aggregate_rates_and_spread() -> None:
    rows = [
        row("attack", "A1", 0, True, utility=False), row("attack", "A2", 0, False, utility=True),  # rep 0: ASR 0.5
        row("attack", "A1", 1, False, utility=True), row("attack", "A2", 1, False, utility=True),  # rep 1: ASR 0.0
        row("benign", "B1", 0, True), row("benign", "B1", 1, False),
    ]
    by = {(s["kind"], s["category"]): s for s in aggregate(rows)}
    a = by[("attack", "all")]
    assert (a["n_runs"], a["n_items"], a["repetitions"], a["rate"]) == (4, 2, 2, 0.25)
    assert a["rate_mean_reps"] == 0.25 and a["rate_std_reps"] == pytest.approx(0.3536, abs=1e-4)
    assert a["utility_under_attack"] == 0.75
    assert by[("attack", "exfil")]["rate"] == 0.25
    b = by[("benign", "all")]
    assert (b["rate"], b["false_positive_rate"]) == (0.5, 0.5)


# --- config -------------------------------------------------------------------


def test_baseline_config_is_valid() -> None:
    from testbed.config import PROJECT_ROOT

    cfg = load_experiment(PROJECT_ROOT / "config" / "experiments" / "m4_baseline.yaml")
    assert cfg.repetitions == 5 and cfg.defenses == ["D0"]


def test_config_rejects_bad_values() -> None:
    for bad in ({"defenses": ["D9"]}, {"repetitions": 0}, {"attacks": ["nope.yaml"]}, {"id": "../escape"}):
        with pytest.raises(ValidationError):
            ExperimentConfig.model_validate(CFG | bad)


# --- runner end to end (scripted model) ----------------------------------------


class FakeIndex:
    def search(self, query: str, k: int = 3) -> list[Chunk]:
        return [Chunk("doc.md", "text")]


class FakeClient:
    """Answers every request with plain text, so no tool is ever called."""

    class messages:  # noqa: N801
        calls = 0

        @classmethod
        def create(cls, **params: Any) -> Any:
            import anthropic

            cls.calls += 1
            return anthropic.types.Message.model_validate({
                "id": "m", "type": "message", "role": "assistant", "model": params["model"],
                "content": [{"type": "text", "text": "I cannot help with that."}],
                "stop_reason": "end_turn", "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 5},
            })


def test_run_experiment_writes_all_outputs(tmp_path: Path) -> None:
    cfg = ExperimentConfig.model_validate(CFG)
    backend = AnthropicBackend(load_models().models["haiku"], client=FakeClient())
    status = run_experiment(cfg, backend, FakeIndex(), tmp_path)
    write_meta(cfg, backend, tmp_path, status, "start")
    summary = write_summary(tmp_path)

    runs = [json.loads(ln) for ln in (tmp_path / "runs.jsonl").read_text(encoding="utf-8").splitlines()]
    assert status["status"] == "completed" and len(runs) == status["runs_planned"] == 2 * (10 + 11)
    assert {r["repetition"] for r in runs} == {0, 1}
    assert not any(r["attack_success"] for r in runs if r["kind"] == "attack")  # model never called a tool
    assert not any(r["task_passed"] for r in runs if r["kind"] == "benign")
    assert (tmp_path / "traces" / "D0" / "IA-DS-01_r1.jsonl").exists()
    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    assert meta["git_commit"] and meta["experiment"]["id"] == "t"
    assert (tmp_path / "summary.csv").exists() and summary[0]["defense"] == "D0"


def test_weak_profile_reaches_the_model(tmp_path: Path) -> None:
    from testbed.app.assistant import CANARY, SYSTEM_PROMPTS

    assert CANARY in SYSTEM_PROMPTS["weak"] and "confidential" not in SYSTEM_PROMPTS["weak"]
    seen: list[str] = []

    class Recording:
        class messages:  # noqa: N801
            @classmethod
            def create(cls, **params: Any) -> Any:
                seen.append(params["system"])
                return FakeClient.messages.create(**params)

    cfg = ExperimentConfig.model_validate(CFG | {"system_prompt": "weak", "repetitions": 1, "benign": []})
    run_experiment(cfg, AnthropicBackend(load_models().models["haiku"], client=Recording()), FakeIndex(), tmp_path)
    assert set(seen) == {SYSTEM_PROMPTS["weak"]}
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate(CFG | {"system_prompt": "strong"})


def test_budget_stop_is_reported(tmp_path: Path) -> None:
    cfg = ExperimentConfig.model_validate(CFG | {"budget_usd": 1e-9})
    backend = AnthropicBackend(load_models().models["haiku"], client=FakeClient())
    backend.tracker.budget_usd = 1e-9
    status = run_experiment(cfg, backend, FakeIndex(), tmp_path)
    assert status["status"] == "stopped: budget" and status["runs_done"] == 1
