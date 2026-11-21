"""Evaluate the D1 injection detectors on the labelled deepset/prompt-injections set.

Measures how well each detector distinguishes injection (label 1) from benign (label 0):
  - regex: the heuristic patterns (testbed.defenses.patterns.injection_labels), free.
  - llm:   the separate classifier call (one paid API call per prompt, cached), run only with
           --llm and counted against the budget.

    python -m testbed.defenses.detector_eval                 # regex only, free
    python -m testbed.defenses.detector_eval --llm --dry-run # planned LLM calls (cached ones are free)
    python -m testbed.defenses.detector_eval --llm --budget 0.30 --split test

Scores are saved with their provenance to results/detector_eval/<split>.json, which the report
(testbed.reporting.report) turns into a table. A dry run saves nothing.

Reports a confusion matrix and precision / recall / F1 / accuracy per detector. These feed the
thesis's D1 analysis: the regex trades recall for zero cost, the LLM detector trades cost for
recall, and this set quantifies the trade-off independently of the app-specific attack runs.
"""

from __future__ import annotations

import argparse
import glob
import json
from dataclasses import dataclass
from pathlib import Path

from testbed.config import PROJECT_ROOT
from testbed.defenses.d1_input_filter import DETECTOR_SYSTEM
from testbed.defenses.patterns import injection_labels

DATA_DIR = PROJECT_ROOT / "data" / "external" / "deepset_prompt_injections"
DATASET_REVISION = "4f61ecb038e9c3fb77e21034b22511b523772cdd"  # see SOURCE.md in DATA_DIR
RESULTS_DIR = PROJECT_ROOT / "results" / "detector_eval"


@dataclass
class Scores:
    """Binary-classification scores (positive class = injection)."""

    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    def add(self, predicted_injection: bool, is_injection: bool) -> None:
        if is_injection:
            self.tp += predicted_injection
            self.fn += not predicted_injection
        else:
            self.fp += predicted_injection
            self.tn += not predicted_injection

    @property
    def n(self) -> int:
        return self.tp + self.fp + self.tn + self.fn

    def _safe(self, num: int, den: int) -> float:
        return num / den if den else 0.0

    @property
    def precision(self) -> float:
        return self._safe(self.tp, self.tp + self.fp)

    @property
    def recall(self) -> float:
        return self._safe(self.tp, self.tp + self.fn)

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return self._safe(2 * p * r, p + r)

    @property
    def accuracy(self) -> float:
        return self._safe(self.tp + self.tn, self.n)

    def to_dict(self) -> dict[str, float | int]:
        return {"n": self.n, "tp": self.tp, "fp": self.fp, "tn": self.tn, "fn": self.fn,
                "precision": self.precision, "recall": self.recall, "f1": self.f1, "accuracy": self.accuracy}

    def line(self, name: str) -> str:
        return (
            f"{name:<8} n={self.n:<4} tp={self.tp} fp={self.fp} tn={self.tn} fn={self.fn}  "
            f"precision={self.precision:.3f} recall={self.recall:.3f} f1={self.f1:.3f} accuracy={self.accuracy:.3f}"
        )


def load_split(split: str, data_dir: Path = DATA_DIR) -> list[tuple[str, int]]:
    """Return (text, label) pairs for the given split, read from the parquet file."""
    import pandas as pd  # local import: only detector evaluation needs pandas

    path = glob.glob(str(data_dir / f"{split}-*.parquet"))[0]
    df = pd.read_parquet(path)
    return list(zip(df["text"].astype(str), df["label"].astype(int), strict=True))


def regex_predicts(text: str) -> bool:
    return bool(injection_labels(text))


def evaluate(rows: list[tuple[str, int]], predict) -> Scores:  # type: ignore[no-untyped-def]
    """Score a predictor `predict(text) -> bool` over labelled rows."""
    scores = Scores()
    for text, label in rows:
        scores.add(predict(text), label == 1)
    return scores


def _llm_predictor(backend):  # type: ignore[no-untyped-def]
    """A paid predictor: classify each prompt with one cached detector call."""

    def predict(text: str) -> bool:
        r = backend.chat([{"role": "user", "content": f"UNTRUSTED TEXT:\n{text}"}],
                         system=DETECTOR_SYSTEM, repetition=1_000_000)
        return "INJECTION" in r.text.upper()

    return predict


def main(argv: list[str] | None = None) -> None:
    from testbed.llm import BudgetExceeded, make_backend

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", choices=["train", "test"], default="test")
    parser.add_argument("--llm", action="store_true", help="also evaluate the LLM detector (paid)")
    parser.add_argument("--limit", type=int, help="evaluate only the first N rows")
    parser.add_argument("--budget", type=float, default=0.30)
    parser.add_argument("--model", help="model key from config/models.yaml")
    parser.add_argument("--dry-run", action="store_true", help="count planned LLM calls; call nothing, save nothing")
    parser.add_argument("--out", type=Path, default=RESULTS_DIR, help="folder for <split>.json (default results/detector_eval)")
    args = parser.parse_args(argv)

    rows = load_split(args.split)[: args.limit]
    print(f"deepset/prompt-injections [{args.split}], {len(rows)} prompts")
    regex = evaluate(rows, regex_predicts)
    print(regex.line("regex"))
    record: dict = {"split": args.split, "prompts": len(rows), "detectors": {"regex": regex.to_dict()}}

    if args.llm:
        backend = make_backend(args.model, dry_run=args.dry_run, budget_usd=args.budget)
        try:
            llm = evaluate(rows, _llm_predictor(backend))
        except BudgetExceeded as e:
            print(f"[stopped] {e}; nothing saved")
            return
        finally:
            print(backend.tracker.summary(dry_run=args.dry_run))
        if args.dry_run:
            return  # dry-run predictions are placeholders, not results
        print(llm.line("llm"))
        record["detectors"]["llm"] = llm.to_dict()
        record["llm_model"] = backend.model.id
        record["llm_spend"] = backend.tracker.summary()
    elif args.dry_run:
        return

    path = save(record, args.out)
    print(f"Saved {path}")


def save(record: dict, out: Path) -> Path:
    """Write the scores with their provenance to <out>/<split>.json."""
    from datetime import datetime, timezone

    from testbed.evaluation.run import _git

    record |= {
        "dataset": "deepset/prompt-injections",
        "dataset_revision": DATASET_REVISION,
        "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty": _git("status", "--porcelain") not in ("", "unknown"),
        "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{record['split']}.json"
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return path


if __name__ == "__main__":
    main()
