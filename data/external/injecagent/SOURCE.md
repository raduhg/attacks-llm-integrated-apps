# InjecAgent (third-party data)

- **Files:** `attacker_cases_ds.jsonl` (32 data-stealing attacker cases),
  `test_cases_ds_enhanced.json` (544 test cases, "enhanced" setting; 817,594 bytes), `LICENCE`
- **Source:** https://github.com/uiuc-kang-lab/InjecAgent, `data/attacker_cases_ds.jsonl` and
  `data/test_cases_ds_enhanced.json` (the latter downloaded 2026-11-08, Milestone 5, used only to
  extract the enhanced setting's fixed prefix)
- **Commit:** `f19c9f2c79a41046eb13c03c51a24c567a8ffa07` (downloaded 2026-11-08, unmodified)
- **Licence:** MIT, Copyright (c) 2023 Qiusi Zhan (see `LICENCE`)
- **Paper:** Zhan, Liang, Ying, Kang. *InjecAgent: Benchmarking Indirect Prompt Injections in
  Tool-Integrated Large Language Model Agents.* Findings of ACL 2024, pp. 10471-10506.

Converted into this project's attack format by `python -m testbed.attacks.import_injecagent`
(see that module for the mapping). The original file is kept unchanged for traceability.
