"""Experiment runner: the (repetition x defense x item) matrix from one YAML config.

    python -m testbed.evaluation.run config/experiments/m4_baseline.yaml --dry-run
    python -m testbed.evaluation.run config/experiments/m4_baseline.yaml

Output in results/<experiment_id>/:
    meta.json      config snapshot, model, versions, git commit, timestamp, status
    runs.jsonl     one row per run (written as it goes, so a crash keeps what was done)
    summary.csv    aggregated metrics (see metrics.py)
    traces/<defense>/<item>_r<rep>.jsonl   full trace of every run

Repetitions are the outer loop, so a budget stop leaves whole repetitions behind. Re-running
an experiment after a crash or budget stop is free for everything already done (response cache).
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any

from testbed.app.assistant import SYSTEM_PROMPTS, Assistant
from testbed.app.rag import EMBEDDING_MODEL, TOP_K
from testbed.app.tools import Sandbox, Searchable
from testbed.app.trace import Trace
from testbed.attacks.checkers import attack_succeeded, user_task_completed
from testbed.attacks.inject import prepare
from testbed.attacks.schema import Attack, load_attacks
from testbed.config import PROJECT_ROOT
from testbed.defenses import build_defense
from testbed.evaluation.benign import BenignTask, check_task, load_tasks, tasks_by_id
from testbed.evaluation.config import ExperimentConfig, load_experiment
from testbed.evaluation.metrics import aggregate
from testbed.llm import AnthropicBackend, BudgetExceeded

RESULTS_DIR = PROJECT_ROOT / "results"


def _usage_fields(trace: Trace) -> dict[str, Any]:
    """Token/cost/latency for one run. Assistant calls (model_call) and the D1-LLM detector
    (detector_call) are summed separately, so the detector's extra cost is reported on its own."""
    calls = trace.of("model_call")
    det = trace.of("detector_call")
    return {
        "steps": len(calls),
        "input_tokens": sum(c["usage"]["input_tokens"] for c in calls),
        "output_tokens": sum(c["usage"]["output_tokens"] for c in calls),
        "cost_usd": round(sum(c["cost_usd"] for c in calls), 8),  # original cost, also for cache hits
        "latency_s": round(sum(c["latency_s"] for c in calls), 3),
        "detector_calls": len(det),
        "detector_cost_usd": round(sum(c["cost_usd"] for c in det), 8),
        "detector_tokens": sum(c["usage"]["input_tokens"] + c["usage"]["output_tokens"] for c in det),
        "all_cached": all(c["cached"] for c in calls),
    }


def run_attack(attack: Attack, ctx: dict[str, Any], defense: str, rep: int, trace_path: Path) -> dict[str, Any]:
    sandbox, messages = prepare(attack, ctx["index"])
    trace = Trace(trace_path)
    trace.log("attack", id=attack.id, category=attack.category, vector=attack.vector, defense=defense, repetition=rep)
    assistant = Assistant(ctx["backend"], sandbox, system=ctx["system"], trace=trace, max_steps=ctx["max_steps"],
                          defense=build_defense(defense))
    result = assistant.run(messages, repetition=rep)
    fired = attack_succeeded(attack.success, trace, sandbox)
    done = user_task_completed(ctx["tasks"][attack.user_task], trace) if attack.user_task else None
    trace.log("attack_result", succeeded=bool(fired), checks_fired=fired, user_task_completed=done)
    return {
        "kind": "attack", "item_id": attack.id, "category": attack.category, "vector": attack.vector,
        "owasp_ref": attack.owasp_ref, "attack_success": bool(fired), "checks_fired": fired,
        "user_task_completed": done, "task_passed": None, "stop_reason": result.stop_reason,
        **_usage_fields(trace),
    }


def run_benign(task: BenignTask, ctx: dict[str, Any], defense: str, rep: int, trace_path: Path) -> dict[str, Any]:
    trace = Trace(trace_path)
    trace.log("benign_task", id=task.id, defense=defense, repetition=rep)
    assistant = Assistant(ctx["backend"], Sandbox(ctx["index"]), system=ctx["system"], trace=trace,
                          max_steps=ctx["max_steps"], defense=build_defense(defense))
    result = assistant.run([{"role": "user", "content": task.prompt}], repetition=rep)
    failures = check_task(task, result.answer, trace.of("tool_call"))
    trace.log("benign_result", passed=not failures, failures=failures)
    return {
        "kind": "benign", "item_id": task.id, "category": "benign", "vector": "none", "owasp_ref": "",
        "attack_success": None, "checks_fired": [], "user_task_completed": None, "task_passed": not failures,
        "failures": failures, "stop_reason": result.stop_reason, **_usage_fields(trace),
    }


def run_experiment(cfg: ExperimentConfig, backend: AnthropicBackend, index: Searchable, out: Path) -> dict[str, Any]:
    """Run the whole matrix, writing runs.jsonl as it goes. Returns a status dict."""
    attacks = [a for p in cfg.attacks for a in load_attacks(PROJECT_ROOT / p)]
    benign = [t for p in cfg.benign for t in load_tasks(PROJECT_ROOT / p)]
    ctx = {"backend": backend, "index": index, "tasks": tasks_by_id(), "max_steps": cfg.max_steps,
           "system": SYSTEM_PROMPTS[cfg.system_prompt]}
    items: list[tuple[str, Any]] = [("attack", a) for a in attacks] + [("benign", t) for t in benign]

    out.mkdir(parents=True, exist_ok=True)
    runs_file = out / "runs.jsonl"
    runs_file.write_text("", encoding="utf-8")
    done = 0
    try:
        for rep in range(cfg.repetitions):
            for defense in cfg.defenses:
                for kind, item in items:
                    trace_path = out / "traces" / defense / f"{item.id}_r{rep}.jsonl"
                    runner = run_attack if kind == "attack" else run_benign
                    row = runner(item, ctx, defense, rep, trace_path)
                    if backend.dry_run:
                        continue
                    row = {"experiment": cfg.id, "model": backend.model.id, "defense": defense, "repetition": rep, **row}
                    with runs_file.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    done += 1
    except BudgetExceeded as e:
        return {"status": "stopped: budget", "detail": str(e), "runs_done": done}
    return {"status": "completed", "runs_done": done, "runs_planned": cfg.repetitions * len(cfg.defenses) * len(items)}


def write_summary(out: Path) -> list[dict[str, Any]]:
    """Aggregate runs.jsonl into summary.csv."""
    rows = [json.loads(l) for l in (out / "runs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    summary = aggregate(rows)
    if summary:
        with (out / "summary.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(summary[0]))
            writer.writeheader()
            writer.writerows(summary)
    return summary


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def write_meta(cfg: ExperimentConfig, backend: AnthropicBackend, out: Path, status: dict[str, Any], started: str) -> None:
    meta = {
        "experiment": cfg.model_dump(mode="json"),
        "model": backend.model.model_dump(mode="json"),
        "temperature": "API default (1.0); sampling parameters are not sent",
        "embedding_model": EMBEDDING_MODEL,
        "retrieval_top_k": TOP_K,
        "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty": _git("status", "--porcelain") not in ("", "unknown"),
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": {p: version(p) for p in ("anthropic", "fastembed", "pydantic")},
        "spend": backend.tracker.summary(),
        **status,
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    from testbed.app import build_index
    from testbed.llm import make_backend

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    cfg = load_experiment(args.config)
    backend = make_backend(cfg.model, dry_run=args.dry_run, budget_usd=cfg.budget_usd)
    out = RESULTS_DIR / cfg.id
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    status = run_experiment(cfg, backend, build_index(cfg.corpus), out)

    if args.dry_run:
        t = backend.tracker
        per_call = t.spent_usd / t.paid_calls if t.paid_calls else 0.0
        est_calls = t.paid_calls * cfg.est_calls_per_run
        # shortcut: runs whose first call is cached are assumed fully cached (true for repeats of
        # earlier runs); first-call cost stands in for later steps. Good to roughly +/-50%.
        print(f"{status['runs_planned']} runs planned: {t.paid_calls} need new API calls, {t.cached_calls} calls served from cache.")
        print(f"Estimate: ~{est_calls:.0f} API calls, ~${est_calls * per_call:.4f} (budget ${cfg.budget_usd}).")
        return

    write_meta(cfg, backend, out, status, started)
    summary = write_summary(out)
    print(f"{status['status']}: {status['runs_done']} runs. {backend.tracker.summary()}")
    for s in summary:
        extra = f" utility={s['utility_under_attack']}" if s["kind"] == "attack" else f" fpr={s['false_positive_rate']}"
        print(
            f"  {s['defense']} {s['kind']:<6} {s['category']:<18} {s['vector']:<8} n={s['n_runs']:<4} "
            f"rate={s['rate']:.3f} (reps {s['rate_mean_reps']:.3f}+/-{s['rate_std_reps']:.3f}, "
            f"95% CI {s['ci_low']:.3f}-{s['ci_high']:.3f}){extra}"
        )
    print(f"Results in {out}")


if __name__ == "__main__":
    main()
