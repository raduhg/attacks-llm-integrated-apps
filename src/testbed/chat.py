"""Minimal interactive chat loop, to exercise the backend by hand.

    python -m testbed.chat                 # real calls (cached)
    python -m testbed.chat --dry-run       # no API calls, prints estimated cost
    python -m testbed.chat --budget 0.05   # stop once $0.05 has been spent

Type `exit` (or press Ctrl+D / Ctrl+Z then Enter on Windows) to quit.
"""

from __future__ import annotations

import argparse
from typing import Any

import anthropic

from testbed.llm import BudgetExceeded, make_backend


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", help="model key from config/models.yaml (default: the file's 'default')")
    parser.add_argument("--dry-run", action="store_true", help="never call the API; estimate cost instead")
    parser.add_argument("--no-cache", action="store_true", help="bypass the on-disk response cache")
    parser.add_argument("--budget", type=float, help="stop after spending this many USD")
    parser.add_argument("--system", default="You are a helpful assistant.", help="system prompt")
    args = parser.parse_args(argv)

    backend = make_backend(args.model, use_cache=not args.no_cache, dry_run=args.dry_run, budget_usd=args.budget)
    print(f"model={backend.model.id} dry_run={args.dry_run} cache={'off' if args.no_cache else 'on'}")

    messages: list[dict[str, Any]] = []
    while True:
        try:
            user = input("\nyou> ").strip()
        except EOFError:
            break
        if user.lower() in {"exit", "quit"}:
            break
        if not user:
            continue
        messages.append({"role": "user", "content": user})
        try:
            r = backend.chat(messages, system=args.system)
        except BudgetExceeded as e:
            print(f"[stopped] {e}")
            break
        except anthropic.APIError as e:  # retries already exhausted inside the SDK
            print(f"[api error] {e}")
            messages.pop()
            continue
        # Append the full content (incl. thinking blocks) unchanged, as the API requires.
        messages.append({"role": "assistant", "content": r.content})
        source = "dry-run" if r.dry_run else "cache" if r.cached else "api"
        print(f"\nassistant> {r.text}")
        print(
            f"  [{source}] stop={r.stop_reason} in={r.usage.input_tokens} out={r.usage.output_tokens} "
            f"cost=${r.cost_usd:.6f} latency={r.latency_s:.2f}s"
        )

    print("\n" + backend.tracker.summary(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
