"""Retrieval over the document corpus (the "R" in RAG).

Deliberately minimal, because retrieval quality is not the research question:
  - Chunking: one chunk per "## " section of a Markdown file (the title/intro is chunk 0).
  - Embeddings: sentence-transformers/all-MiniLM-L6-v2, run locally on CPU via fastembed (ONNX).
    This is an embedding model, not an LLM.
  - Search: brute-force cosine similarity over a numpy array. With ~100 chunks a vector
    database would add nothing but a dependency.
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from testbed.config import PROJECT_ROOT

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # harmless on Windows without symlinks

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_CACHE = PROJECT_ROOT / ".cache" / "embeddings"
CORPUS_DIR = PROJECT_ROOT / "data" / "corpus"
# Chunks returned per search. Raised from 3 to 5 after the Milestone 4 baseline: MiniLM ranks
# exact codes (e.g. "E-207") poorly, and k=3 missed the right section in 2 of 5 runs of B05.
TOP_K = 5


@dataclass(frozen=True)
class Chunk:
    """One retrievable piece of a document."""

    doc: str  # file name, e.g. "expense_policy.md"
    text: str


def _split_sections(markdown: str) -> list[str]:
    """One piece per "## " section; text before the first section is its own piece."""
    parts = markdown.split("\n## ")
    texts = [parts[0].strip()] + ["## " + p.strip() for p in parts[1:]]
    return [t for t in texts if t.strip("# ")]


def load_chunks(corpus_dir: Path) -> list[Chunk]:
    """Split every .md file in `corpus_dir` into sections, in a stable (sorted) order."""
    return [Chunk(p.name, t) for p in sorted(corpus_dir.glob("*.md")) for t in _split_sections(p.read_text(encoding="utf-8"))]


class DocumentIndex:
    """In-memory embedding index over one corpus (e.g. data/corpus/clean)."""

    def __init__(self, corpus_dir: Path) -> None:
        from fastembed import TextEmbedding  # imported here so modules that only need Chunk stay light

        self.corpus_dir = corpus_dir
        self.chunks = load_chunks(corpus_dir)
        if not self.chunks:
            raise ValueError(f"No .md documents found in {corpus_dir}")
        self._model = TextEmbedding(EMBEDDING_MODEL, cache_dir=str(EMBEDDING_CACHE))
        self._vectors = np.array(list(self._model.embed([c.text for c in self.chunks])))

    def with_document(self, doc: str, markdown: str) -> DocumentIndex:
        """A copy of this index with one extra document added; the original is unchanged.
        Used to inject a document for a single attack run without re-embedding the corpus."""
        extra = [Chunk(doc, t) for t in _split_sections(markdown)]
        new = copy.copy(self)
        new.chunks = self.chunks + extra
        new._vectors = np.vstack([self._vectors, np.array(list(self._model.embed([c.text for c in extra])))])
        return new

    def search(self, query: str, k: int = TOP_K) -> list[Chunk]:
        """Return the k chunks most similar to `query`."""
        q = next(iter(self._model.embed([query])))
        scores = self._vectors @ q  # fastembed returns unit vectors, so dot product = cosine
        top = np.argsort(-scores, kind="stable")[:k]  # stable: ties resolve the same way every run
        return [self.chunks[i] for i in top]
