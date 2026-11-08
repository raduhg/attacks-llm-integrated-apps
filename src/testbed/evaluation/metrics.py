"""Aggregation of per-run rows into the summary table (summary.csv).

Each summary row describes one group of runs (defense x kind x category x vector, plus an
"all" row per defense and kind). `rate` means:
  - kind=attack: Attack Success Rate (ASR) = successful attacks / attempts
  - kind=benign: task success rate (false positive rate = 1 - rate)

Uncertainty is reported two ways:
  - rate_mean_reps / rate_std_reps: the rate computed separately for each repetition,
    then mean and sample standard deviation across the N repetitions;
  - ci_low / ci_high: Wilson score 95% interval over all attempts in the group
    (well-behaved when the rate is near 0 or 1, unlike the normal approximation).
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Any

Z_95 = 1.959964


def wilson(k: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for k successes out of n trials."""
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _outcome(row: dict[str, Any]) -> bool:
    return bool(row["attack_success"]) if row["kind"] == "attack" else bool(row["task_passed"])


def _summarise(key: tuple[str, str, str, str], rows: list[dict[str, Any]]) -> dict[str, Any]:
    defense, kind, category, vector = key
    k = sum(_outcome(r) for r in rows)
    n = len(rows)
    by_rep: dict[int, list[bool]] = defaultdict(list)
    for r in rows:
        by_rep[r["repetition"]].append(_outcome(r))
    rep_rates = [sum(v) / len(v) for _, v in sorted(by_rep.items())]
    low, high = wilson(k, n)
    utility = [r["user_task_completed"] for r in rows if r.get("user_task_completed") is not None]
    return {
        "defense": defense,
        "kind": kind,
        "category": category,
        "vector": vector,
        "n_runs": n,
        "n_items": len({r["item_id"] for r in rows}),
        "repetitions": len(by_rep),
        "rate": round(k / n, 4),
        "rate_mean_reps": round(statistics.mean(rep_rates), 4),
        "rate_std_reps": round(statistics.stdev(rep_rates), 4) if len(rep_rates) > 1 else 0.0,
        "ci_low": round(low, 4),
        "ci_high": round(high, 4),
        "utility_under_attack": round(sum(utility) / len(utility), 4) if utility else "",
        "false_positive_rate": round(1 - k / n, 4) if kind == "benign" else "",
        "refusals": sum(r["stop_reason"] == "refusal" for r in rows),
        "mean_input_tokens": round(statistics.mean(r["input_tokens"] for r in rows), 1),
        "mean_output_tokens": round(statistics.mean(r["output_tokens"] for r in rows), 1),
        "mean_cost_usd": round(statistics.mean(r["cost_usd"] for r in rows), 6),
        "mean_detector_cost_usd": round(statistics.mean(r.get("detector_cost_usd", 0) for r in rows), 6),
        "mean_latency_s": round(statistics.mean(r["latency_s"] for r in rows), 3),
    }


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group run rows and summarise each group (see module docstring)."""
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[(r["defense"], r["kind"], "all", "all")].append(r)
        if r["kind"] == "attack":
            groups[(r["defense"], "attack", r["category"], r["vector"])].append(r)
    return [_summarise(key, groups[key]) for key in sorted(groups)]
