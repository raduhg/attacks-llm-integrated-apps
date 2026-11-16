---
name: feedback-prove-rerun-is-cached
description: Never call a re-run free without a dry run showing zero new API calls
metadata:
  type: feedback
---

Before saying a re-run "comes from the cache" or "costs nothing", run `--dry-run` and confirm it reports 0 runs needing new API calls.

**Why:** a re-run described as free cost $0.78. Defense D3 put a random tag in the system prompt, so its requests never matched the cache. The tag is now a fixed constant and a test checks that two D3 instances produce identical text.
**How to apply:** anything sent to the model must be deterministic for a given (experiment, item, repetition). After changing a defense or prompt, expect its rows to need new paid calls and say so.
