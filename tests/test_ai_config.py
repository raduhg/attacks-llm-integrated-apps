"""Tests for the AI configuration: the guard hook and the in-repo memory index.

The agent's configuration is treated like code: the hook has behaviour tests, and the memory
index is checked for consistency so a pull request cannot leave it out of sync.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

import pytest

from testbed.config import PROJECT_ROOT

GUARD = PROJECT_ROOT / ".claude" / "hooks" / "guard.py"
MEMORY = PROJECT_ROOT / ".claude" / "memory"


def guard(tool_input: dict) -> int:
    """Run the hook as Claude Code does (JSON on stdin) and return its exit code."""
    event = json.dumps({"tool_name": "X", "tool_input": tool_input})
    return subprocess.run([sys.executable, str(GUARD)], input=event, text=True, capture_output=True).returncode


@pytest.mark.parametrize(
    "tool_input",
    [
        {"file_path": "C:\\proj\\.env"},
        {"file_path": "/home/u/proj/.env"},
        {"command": "cat .env"},
        {"command": "type .env | findstr KEY"},
        {"pattern": "KEY", "path": ".env"},
        {"command": "git push --force origin main"},
        {"command": "git push -f"},
        {"command": "git push --force-with-lease"},
        {"command": "git push origin +main"},
    ],
)
def test_guard_blocks(tool_input: dict) -> None:
    assert guard(tool_input) == 2


@pytest.mark.parametrize(
    "tool_input",
    [
        {"file_path": "/proj/.env.example"},
        {"command": "uv run pytest -q"},
        {"command": "ls .venv && python -c 'import os; os.environ'"},
        {"command": "$env:FOO = 'x'; git status"},
        {"command": "git push origin main"},
        {"file_path": "/proj/README.md", "content": "copy .env.example to .env"},  # contents are not checked
    ],
)
def test_guard_allows(tool_input: dict) -> None:
    assert guard(tool_input) == 0


def test_guard_ignores_malformed_input() -> None:
    assert subprocess.run([sys.executable, str(GUARD)], input="not json", text=True).returncode == 0


def test_guard_is_registered_as_pretooluse_hook() -> None:
    settings = json.loads((PROJECT_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    commands = [h["command"] for entry in settings["hooks"]["PreToolUse"] for h in entry["hooks"]]
    assert any("guard.py" in c for c in commands)


def test_memory_index_matches_files() -> None:
    index = (MEMORY / "MEMORY.md").read_text(encoding="utf-8")
    linked = set(re.findall(r"\]\(([\w.-]+\.md)\)", index))
    files = {p.name for p in MEMORY.glob("*.md")} - {"MEMORY.md"}
    assert linked == files
    for name in files:  # every memory file declares what it is
        text = (MEMORY / name).read_text(encoding="utf-8")
        assert text.startswith("---\nname: " + name[:-3] + "\n") and "\n  type: " in text
