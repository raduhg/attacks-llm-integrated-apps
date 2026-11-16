#!/usr/bin/env python3
"""PreToolUse guard: blocks two safety-critical actions regardless of what any prompt says.

  1. Touching the `.env` file (it holds the paid API key): reading, editing, writing, searching
     it, or naming it in a shell command. `.env.example` is allowed.
  2. `git push --force` in any form (history rewrite on the shared branch).

Why a hook and not a sentence in CLAUDE.md: CLAUDE.md, memory files and anything the agent reads
are text the model may be talked out of, and a poisoned memory file could say the opposite. This
script runs outside the model. Exit code 2 blocks the tool call and shows stderr to the agent.

Claude Code sends the tool call as JSON on stdin: {"tool_name": ..., "tool_input": {...}}.
"""

from __future__ import annotations

import json
import re
import sys

# `.env` as a whole path component: not `.env.example`, `.venv`, `os.environ` or `$env:VAR`.
ENV_FILE = re.compile(r"(?<![\w.-])\.env(?![\w.-])")
FORCE_PUSH = re.compile(r"\bgit\b[^\n;&|]*\bpush\b[^\n;&|]*(--force|\s-f\b|\s\+\S)")

# Only these fields are checked. File *contents* being written are not, so documentation and
# tests may mention the `.env` file by name.
PATH_FIELDS = ("file_path", "path", "notebook_path", "pattern", "glob")


def violation(tool_input: dict) -> str | None:
    """Return the reason this tool call must be blocked, or None if it is allowed."""
    command = str(tool_input.get("command", ""))
    if FORCE_PUSH.search(command):
        return "force-push is not allowed in this repository"
    targets = [command] + [str(tool_input.get(f, "")) for f in PATH_FIELDS]
    if any(ENV_FILE.search(t.replace("\\", "/")) for t in targets):
        return "the .env file holds the API key and must not be read, edited or named in commands"
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0  # not a tool event we understand; do not block the session
    reason = violation(event.get("tool_input") or {})
    if reason:
        print(f"Blocked by .claude/hooks/guard.py: {reason}.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
