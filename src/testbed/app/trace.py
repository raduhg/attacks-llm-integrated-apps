"""Structured run trace: one JSON object per line (JSONL), so every run can be inspected later."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class Trace:
    """Collects events in memory and, if `path` is given, appends them to a JSONL file."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.events: list[dict[str, Any]] = []
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")  # one file per run: start empty

    def log(self, event: str, **data: Any) -> None:
        """Record one event, e.g. log("tool_call", name="send_email", input={...})."""
        record = {"t": round(time.time(), 3), "event": event, **data}
        self.events.append(record)
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def of(self, event: str) -> list[dict[str, Any]]:
        """All events of one type."""
        return [e for e in self.events if e["event"] == event]
