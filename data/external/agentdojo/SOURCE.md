# AgentDojo (third-party data)

- **Files:** `injection_tasks.py` (workspace suite v1: attack goals), `important_instructions_attacks.py`
  and `baseline_attacks.py` (attack templates), `LICENSE`. Unmodified copies.
- **Source:** https://github.com/ethz-spylab/agentdojo, paths `src/agentdojo/default_suites/v1/workspace/injection_tasks.py`,
  `src/agentdojo/attacks/important_instructions_attacks.py`, `src/agentdojo/attacks/baseline_attacks.py`
- **Commit:** `089ed468cf3ed0322acc66b0211f26d9d90dbf60` (downloaded 2026-11-21)
- **Licence:** MIT, Copyright (c) 2024 Edoardo Debenedetti, Jie Zhang, Mislav Balunovic,
  Luca Beurer-Kellner, Marc Fischer, and Florian Tramèr (see `LICENSE`)
- **Paper:** Debenedetti et al. *AgentDojo: A Dynamic Environment to Evaluate Prompt Injection
  Attacks and Defenses for LLM Agents.* NeurIPS 2024, Datasets and Benchmarks Track.

These are Python source files. They are **never imported or executed**: the converter
(`python -m testbed.attacks.import_agentdojo`) reads them with Python's `ast` parser and extracts
the goal strings and template strings as text.
