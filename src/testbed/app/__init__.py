"""The target application ("Acme Assistant"): RAG, sandboxed tools, agent loop, trace."""

from __future__ import annotations

from testbed.app.assistant import CANARY, SYSTEM_PROMPT, AgentResult, Assistant
from testbed.app.rag import CORPUS_DIR, DocumentIndex
from testbed.app.tools import TOOLS, Sandbox
from testbed.app.trace import Trace

__all__ = ["CANARY", "SYSTEM_PROMPT", "TOOLS", "AgentResult", "Assistant", "DocumentIndex", "Sandbox", "Trace", "build_index"]


def build_index(corpus: str = "clean") -> DocumentIndex:
    """Embedding index over data/corpus/<corpus> ("clean" now; "poisoned" from Milestone 3)."""
    return DocumentIndex(CORPUS_DIR / corpus)
