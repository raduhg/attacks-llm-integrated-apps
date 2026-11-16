---
name: feedback-cost-estimate-target-model
description: Cost estimates must use the price of the model that will actually run
metadata:
  type: feedback
---

Estimate the cost of a run from the price of the model in that experiment's config, and from the dry run, not from memory of an earlier run.

**Why:** a Haiku 4.5 probe was quoted at $0.05 using Haiku 5.5's price. Haiku 4.5 costs 10x more, so the real figure was about $0.60. The error was caught by the dry run before any money was spent.
**How to apply:** run `--dry-run` on the exact config before quoting a cost. If the corrected figure is several times what was quoted, stop and ask again.
