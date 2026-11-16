---
name: project-testbed-decisions
description: Confirmed decisions for the prompt-injection testbed (model, budget, language, cache, RAG, app profiles)
metadata:
  type: project
---

- Model: Claude Haiku 5.5 for bulk runs; Haiku 4.5 (`haiku45`) only for the per-model comparison (10x the price). Total API budget: $10.
- Anthropic only, no second provider. Charts, labels and corpus in English.
- The response cache key includes the repetition index, so N repetitions are N real calls.
- Temperature is the API default (1.0); Haiku 5.5 rejects sampling parameters and there is no seed.
- RAG: fastembed all-MiniLM-L6-v2 + numpy cosine search, top-k 5, no vector database.
- Two app profiles: `default` (both models resisted every attack) and `weak` (deliberately vulnerable). Every reported number must say which profile and model it comes from.

**Why:** these resolve the open points in CLAUDE.md and are part of the methodology chapter.
**How to apply:** keep cost estimates within the budget; do not propose local models or a second provider.
