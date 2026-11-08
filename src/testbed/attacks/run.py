"""Run an attack catalogue once against the baseline assistant (D0) and report each result.

    python -m testbed.attacks.run --dry-run
    python -m testbed.attacks.run --budget 0.05

Traces go to results/attacks_smoke/<attack_id>.jsonl. Repetitions, defenses and CSV output
come with the experiment runner in Milestone 4.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from testbed.config import PROJECT_ROOT

from testbed.attacks.schema import ATTACKS_DIR, load_attacks


def main(argv: list[str] | None = None) -> None:
    from testbed.app import Assistant, Trace, build_index
    from testbed.attacks.checkers import attack_succeeded, user_task_completed
    from testbed.attacks.inject import prepare
    from testbed.evaluation.benign import tasks_by_id
    from testbed.llm import BudgetExceeded, make_backend

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--attacks", type=Path, default=ATTACKS_DIR / "m3_initial.yaml")
    parser.add_argument("--model", help="model key from config/models.yaml")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--budget", type=float, default=0.05, help="USD limit for this run (default 0.05)")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "results" / "attacks_smoke")
    args = parser.parse_args(argv)

    attacks = load_attacks(args.attacks)
    if not attacks:
        print(f"No attacks in {args.attacks}.")
        return
    tasks = tasks_by_id()
    backend = make_backend(args.model, dry_run=args.dry_run, budget_usd=args.budget)
    index = build_index("clean")
    succeeded = refused = with_task = task_done = 0
    for attack in attacks:
        sandbox, messages = prepare(attack, index)
        trace = Trace(args.out / f"{attack.id}.jsonl")
        trace.log("attack", id=attack.id, category=attack.category, vector=attack.vector, owasp_ref=attack.owasp_ref)
        try:
            result = Assistant(backend, sandbox, trace=trace).run(messages)
        except BudgetExceeded as e:
            print(f"[stopped] {e}")
            break
        if args.dry_run:
            continue
        fired = attack_succeeded(attack.success, trace, sandbox)
        done = user_task_completed(tasks[attack.user_task], trace) if attack.user_task else None
        trace.log(
            "attack_result", succeeded=bool(fired), checks_fired=fired, user_task_completed=done, stop_reason=result.stop_reason
        )
        succeeded += bool(fired)
        refused += result.stop_reason == "refusal"
        with_task += done is not None
        task_done += bool(done)
        status = "SUCCESS" if fired else ("REFUSED" if result.stop_reason == "refusal" else "failed")
        task = "-" if done is None else ("done" if done else "NOT DONE")
        print(f"{attack.id:<8} {status:<8} user_task={task:<8} {attack.category:<18} {attack.vector:<8} fired={fired or '-'}")

    if args.dry_run:
        print(f"{len(attacks)} attacks. " + backend.tracker.summary(dry_run=True))
        print("Note: only the first model call per attack is counted; real runs take ~2-3 calls.")
    else:
        print(f"\nASR (baseline, N=1): {succeeded}/{len(attacks)}; refusals: {refused}; "
              f"user task completed under attack: {task_done}/{with_task}. " + backend.tracker.summary())


if __name__ == "__main__":
    main()
