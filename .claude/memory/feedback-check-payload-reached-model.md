---
name: feedback-check-payload-reached-model
description: For indirect attacks, confirm in the trace that the payload reached the model before trusting the result
metadata:
  type: feedback
---

An indirect attack only measures something if its payload appears in a tool result the model received. Check the traces for that before reporting an attack success rate, especially a rate of 0.

**Why:** two indirect leakage attacks were injected as a separate document and a separate email that the benign request never retrieved or opened. Their 0% ASR was reported as a result but was a non-measurement. They now inject into the output of the tool the request calls.
**How to apply:** after the first run of a new indirect attack, grep its trace for a distinctive part of the payload in `tool_result` events. Prefer `injection_point: tool_output` tied to the carrier task's tool.
