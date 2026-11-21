# Evidence 3: a pull request is merged only after all checks pass

- **Date:** 2026-11-21
- **Pull request:** https://github.com/raduhg/attacks-llm-integrated-apps/pull/1 (branch `fix/ci-gitleaks`)
- **Change:** run gitleaks as a checksum-pinned binary instead of the gitleaks action, plus evidence 1.

All four required checks passed on the pull request (lint, test, security, build), and the pull
request was then merged into `main` as merge commit `90d9bdb`. CI also passed on `main` after the
merge.

Together with evidence 1 (direct push rejected) and evidence 2 (failing check blocks merge), this
shows that every change reaches `main` through a pull request with passing checks.

Screenshot of the merge box with all checks green: `03-merge-checks-passed.png` (add if available).
