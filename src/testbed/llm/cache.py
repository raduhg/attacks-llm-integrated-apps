"""On-disk response cache.

The key is a SHA-256 hash of the exact request parameters plus the repetition index.
Including the repetition index is a methodological choice: the N repetitions of an
experiment are N real, independent API calls, while re-running the same experiment
(e.g. after a crash, or to redo the analysis) is served from disk at no cost.

Each entry is one human-readable JSON file holding both the request and the response.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def cache_key(params: dict[str, Any], repetition: int) -> str:
    """Deterministic hash of the request parameters and repetition index."""
    blob = json.dumps({"params": params, "repetition": repetition}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class ResponseCache:
    """A directory of `<key>.json` files."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        """Return the cached response dict, or None on a miss."""
        path = self._path(key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))["response"]

    def put(self, key: str, params: dict[str, Any], repetition: int, response: dict[str, Any]) -> None:
        """Store a response. Written to a temp file first so a crash never leaves a corrupt entry."""
        self.directory.mkdir(parents=True, exist_ok=True)
        entry = {"params": params, "repetition": repetition, "response": response}
        tmp = self._path(key).with_suffix(".tmp")
        tmp.write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._path(key))
