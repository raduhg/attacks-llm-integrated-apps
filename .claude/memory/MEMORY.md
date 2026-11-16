# Project memory index

One line per memory file. Files are in this folder; `tests/test_ai_config.py` fails if a file is
missing from this index or the index points at a file that does not exist.

- [Testbed decisions](project-testbed-decisions.md) — model, budget, language, cache key, RAG, profiles
- [Cost estimates use the target model's price](feedback-cost-estimate-target-model.md) — a 10x error happened once
- [Prove a re-run is cached before calling it free](feedback-prove-rerun-is-cached.md) — dry-run first
- [Check that an indirect payload reached the model](feedback-check-payload-reached-model.md) — a 0% ASR can be a non-measurement
- [No hand-written attack payloads](feedback-no-handwritten-payloads.md) — datasets or generators, with provenance
