"""Retrieval over the document corpus (the "R" in RAG).

Deliberately minimal, because retrieval quality is not the research question:
  - Chunking: one chunk per "## " section of a Markdown file (the title/intro is chunk 0).
  - Embeddings: sentence-transformers/all-MiniLM-L6-v2, run locally on CPU via fastembed (ONNX).
    This is an embedding model, not an LLM.
  - Search: brute-force cosine similarity over a numpy array. With ~100 chunks a vector
    database would add nothing but a dependency.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from testbed.config import PROJECT_ROOT

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # harmless on Windows without symlinks

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_CACHE = PROJECT_ROOT / ".cache" / "embeddings"
CORPUS_DIR = PROJECT_ROOT / "data" / "corpus"


@dataclass(frozen=True)
class Chunk:
    """One retrievable piece of a document."""

    doc: str  # file name, e.g. "expense_policy.md"
    text: str


def load_chunks(corpus_dir: Path) -> list[Chunk]:
    """Split every .md file in `corpus_dir` into sections, in a stable (sorted) order."""
    chunks: list[Chunk] = []
    for path in sorted(corpus_dir.glob("*.md")):
        sections = path.read_text(encoding="utf-8").split("\n## ")
        for i, section in enumerate(sections):
            text = section.strip() if i == 0 else "## " + section.strip()
            if text:
                chunks.append(Chunk(path.name, text))
    return chunks


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

    def search(self, query: str, k: int = 3) -> list[Chunk]:
        """Return the k chunks most similar to `query`."""
        q = next(iter(self._model.embed([query])))
        scores = self._vectors @ q  # fastembed returns unit vectors, so dot product = cosine
        top = np.argsort(-scores, kind="stable")[:k]  # stable: ties resolve the same way every run
        return [self.chunks[i] for i in top]
