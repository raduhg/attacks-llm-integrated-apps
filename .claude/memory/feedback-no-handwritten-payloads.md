---
name: feedback-no-handwritten-payloads
description: Attack payloads come from published datasets or small generators, never written ad hoc
metadata:
  type: feedback
---

Take attack payloads from published, permissively licensed datasets (InjecAgent, deepset/prompt-injections) through a converter, or build them from short templates in a generator module. Record the source, revision and licence in `data/external/<name>/SOURCE.md` and in each attack's `source` field.

**Why:** every payload must be traceable to a citable source for the thesis, and ad hoc payload writing was repeatedly stopped by the assistant's safety filter, which stalled the work.
**How to apply:** to add an attack category, first look for a dataset; write converter or generator code, plus a test that the committed YAML matches its output.
