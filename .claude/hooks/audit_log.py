#!/usr/bin/env python3
"""
Claude Code audit hook.

Claude Code runs this script on every hook event (see .claude/settings.json)
and passes the event as JSON on stdin. The script appends one human-readable
entry per event to `audit.log` in the project root.

Logged events:
  SessionStart / SessionEnd  - session boundaries
  UserPromptSubmit           - every prompt you type
  PreToolUse                 - every tool call Claude is about to make (with its input)
  PostToolUse                - the result of every tool call
  Notification               - permission requests and idle notifications
  Stop / SubagentStop        - Claude (or a subagent) finished responding
  PreCompact                 - context compaction

Design rules:
  * Standard library only, works on Windows, macOS and Linux.
  * Never blocks Claude Code: any error is swallowed and the script exits 0.
  * Secrets that look like API keys are redacted before writing.
  * Long values are truncated so the log stays readable.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

MAX_VALUE_CHARS = 2000  # truncate long inputs/outputs per field
LOG_FILE_NAME = "audit.log"

# Patterns for secrets that must never end up in the log.
SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"),            # Anthropic keys
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}"),      # OpenAI-style keys
    re.compile(r"(?i)(api[_-]?key|secret|token|password)(\s*[=:]\s*)(\S+)"),
]


def redact(text: str) -> str:
    for pattern in SECRET_PATTERNS:
        if pattern.groups >= 3:
            text = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text)
        else:
            text = pattern.sub("[REDACTED]", text)
    return text


def to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(value)
    text = redact(text)
    if len(text) > MAX_VALUE_CHARS:
        text = text[:MAX_VALUE_CHARS] + f" ...[truncated, {len(text)} chars total]"
    return text


def indent(text: str) -> str:
    return "\n".join("    " + line for line in text.splitlines()) if text else "    (empty)"


def summarize_tool_input(tool_name: str, tool_input: dict) -> str:
    """Short one-line summary for the most common tools; full input follows below."""
    if not isinstance(tool_input, dict):
        return ""
    if tool_name == "Bash":
        return tool_input.get("command", "")
    if tool_name in ("Read", "Write", "Edit", "MultiEdit", "NotebookEdit"):
        return tool_input.get("file_path", "") or tool_input.get("notebook_path", "")
    if tool_name in ("Glob", "Grep"):
        return f"pattern={tool_input.get('pattern', '')} path={tool_input.get('path', '.')}"
    if tool_name in ("WebFetch", "WebSearch"):
        return tool_input.get("url", "") or tool_input.get("query", "")
    if tool_name in ("Task", "Agent"):
        return tool_input.get("description", "")
    return ""


def build_entry(event: dict) -> str:
    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    name = event.get("hook_event_name", "Unknown")
    session = str(event.get("session_id", "?"))[:8]
    header = f"[{ts}] [session {session}] {name}"

    lines: list[str] = []

    if name == "UserPromptSubmit":
        lines.append(f"{header}")
        lines.append(indent(to_text(event.get("prompt"))))

    elif name == "PreToolUse":
        tool = event.get("tool_name", "?")
        tool_input = event.get("tool_input", {})
        summary = to_text(summarize_tool_input(tool, tool_input))
        lines.append(f"{header} -> {tool}" + (f": {summary.splitlines()[0] if summary else ''}"))
        lines.append("  input:")
        lines.append(indent(to_text(tool_input)))

    elif name == "PostToolUse":
        tool = event.get("tool_name", "?")
        response = event.get("tool_response")
        status = "OK"
        if isinstance(response, dict) and (response.get("is_error") or response.get("error")):
            status = "ERROR"
        lines.append(f"{header} <- {tool} [{status}]")
        lines.append("  result:")
        lines.append(indent(to_text(response)))

    elif name == "Notification":
        lines.append(f"{header}: {to_text(event.get('message'))}")

    elif name == "SessionStart":
        lines.append(f"{header} (source={event.get('source', '?')}, cwd={event.get('cwd', '?')})")

    elif name == "SessionEnd":
        lines.append(f"{header} (reason={event.get('reason', '?')})")

    elif name in ("Stop", "SubagentStop"):
        lines.append(f"{header}: response finished")

    elif name == "PreCompact":
        lines.append(f"{header} (trigger={event.get('trigger', '?')})")

    else:
        lines.append(f"{header}")
        lines.append(indent(to_text(event)))

    return "\n".join(lines) + "\n"


def log_path(event: dict) -> Path:
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd()
    return Path(project_dir) / LOG_FILE_NAME


def main() -> None:
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except Exception:
        event = {"hook_event_name": "Unparseable", "raw": "(could not parse hook input)"}

    try:
        entry = build_entry(event)
        with open(log_path(event), "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        pass  # logging must never break Claude Code

    sys.exit(0)


if __name__ == "__main__":
    main()
