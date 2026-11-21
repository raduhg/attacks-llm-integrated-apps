# Evidence 2: a failing check blocks the merge

- **Date:** 2026-11-21
- **Pull request:** https://github.com/raduhg/attacks-llm-integrated-apps/pull/2 (branch `evidence/failing-check`)
- **Change:** one deliberate unused import in `src/testbed/__init__.py`, which ruff reports as F401.
- **CI run:** https://github.com/raduhg/attacks-llm-integrated-apps/actions/runs/44891582485

| Job | Result |
|---|---|
| lint | failure |
| test | success |
| security | success |
| build | skipped (needs lint, test and security) |

**Result:** the pull request's merge box showed merging as blocked because a required check failed
(confirmed by the repository owner; screenshot `02-merge-blocked.png`). The pull request was closed
without merging, so the lint error never reached `main`.

Note: GitHub's REST API reported this pull request's `mergeable_state` as `unstable` rather than
`blocked`. With repository rulesets that field does not reflect the rules reliably, so the merge
box is the evidence, not the API field.
