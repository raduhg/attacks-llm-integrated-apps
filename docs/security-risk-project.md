# Security risk project: definition, risk register and controls

## Project definition

A reproducible testbed that measures prompt injection attacks against an LLM-integrated
application and the effect of defenses on them. It consists of a sandboxed target application
(an assistant with document search and mocked tools), an attack catalogue, six defenses, an
experiment runner and an analysis pipeline. Results feed a Master's dissertation.

## Scope

In scope: the Python package in `src/testbed/`, its data and configuration, the Claude Code
configuration in `.claude/`, the CI pipeline and the repository's Git workflow.

Out of scope: production deployment (nothing is deployed), hosted infrastructure (none is
provisioned), and the security of the Anthropic API itself. All "sensitive" data in `data/` is
fake, and the assistant's tools have no real side effects.

The scope follows from the register below: every in-scope component is one where a listed risk
can occur, and each risk has at least one control that is implemented in this repository.

## Risk register

Likelihood and impact are rated Low / Medium / High for this project (one developer, a paid API
key with a $10 budget, results used in an academic assessment).

| ID | Risk | Likelihood | Impact | Controls | Residual |
|---|---|---|---|---|---|
| R1 | **Secret leakage**: the API key in `.env` is committed or pushed | Medium | High (key abuse, spend) | `.env` git-ignored; `.githooks/pre-commit` blocks staging it or any key-shaped string; gitleaks on every PR over full history; GitHub push protection; guard hook stops the AI agent reading the file | Low |
| R2 | **History rewrite**: a force-push to `main` destroys or silently alters commits that results are tied to | Low | High (results no longer reproducible) | Branch protection rejects force-pushes and deletions on `main`; guard hook blocks every force-push form for the agent; `meta.json` records the commit hash of each result | Low |
| R3 | **Over-scoped credentials**: a broad personal token or workflow token is stolen or misused | Medium | High | Fine-grained personal access token limited to this repository (Contents and Pull requests only, with expiry); workflow token `contents: read`; no job-level permission increase (tested); no secrets in CI | Low |
| R4 | **Supply chain**: a compromised GitHub Action or a vulnerable Python dependency | Medium | High | Every action pinned to a commit SHA (tested); `uv.lock` with hashes and `uv sync --locked`; `pip-audit` on the locked versions in CI | Medium |
| R5 | **Unsafe code patterns** introduced into the testbed (shell injection, unsafe deserialisation) | Low | Medium | `ruff` security rules (flake8-bandit `S`) in CI; exceptions are listed with a reason in `pyproject.toml` | Low |
| R6 | **Wrong measurements**: a defect in checkers, defenses or the runner makes a reported number false | Medium | High (invalid thesis results) | 94 offline tests in CI; lint; build job installs the wheel in a clean environment; the `run-experiment` skill requires a validity check | Medium |
| R7 | **Unreviewed or poisoned changes** reach `main`, including to the agent's instructions and memory | Medium | High | Protected `main`: pull request required, failing checks block merge; memory and skills live in the repo and are diffed in PRs; tests cover the guard hook and memory index | Low |
| R8 | **Uncontrolled API spend**, in CI or by the agent | Low | Medium | CI uses no API key and tests mock the API (tested); per-experiment budget cap; dry run and approval before every paid run | Low |
| R9 | **Third-party attack data** misused or unattributed | Low | Medium | Only permissively licensed datasets; source, revision and licence recorded in `data/external/*/SOURCE.md`; payloads run only against the sandbox | Low |

## Git CLI push risks and their controls

| Push risk | Control | Where |
|---|---|---|
| Secret leakage | Pre-commit hook refuses the key file and key-shaped strings; gitleaks in CI; GitHub secret scanning with push protection | `.githooks/pre-commit`, `security` job, repository settings |
| Force-push history rewrite | Branch protection on `main` (no force-push, no deletion); the agent's guard hook blocks `--force`, `-f`, `--force-with-lease` and `+refspec` | repository settings, `.claude/hooks/guard.py` |
| Over-scoped credentials | Fine-grained token scoped to this one repository with only Contents and Pull requests permissions and an expiry date, stored in the OS credential manager; read-only workflow token | GitHub token settings, `ci.yml` |

Enable the local hook once per clone:

```
git config core.hooksPath .githooks
```

## CI/CD pipeline

`.github/workflows/ci.yml` runs on every pull request and on pushes to `main`.

| Job | What it runs | Risk it guards |
|---|---|---|
| `lint` | `ruff check .` with error, import, bug and security rules | R5, R6 |
| `test` | `pytest` (offline; the API is mocked) | R6, R7, R8 |
| `security` | gitleaks secret scan over the full history; `pip-audit` on the locked dependencies | R1, R4 |
| `build` | `uv build`, then installs the wheel in a clean environment and imports it; uploads the artifact. Runs only if the other three pass | R6 |

Pipeline hardening (R3, R4), checked by `tests/test_ci_config.py`:

- Every third-party action is pinned to a full commit SHA, with the release tag in a comment.
- gitleaks runs as a downloaded binary fixed by version and SHA-256 checksum, not through a
  third-party action (the action failed on its first run here without a usable error).
- `permissions: contents: read` at workflow level, and no job widens it.
- No secret other than the automatic `GITHUB_TOKEN` is referenced. The paid API key is never in CI.
- `persist-credentials: false` on checkout, so the token is not left in the working copy.

## Protected main branch

Settings to apply on GitHub (Settings → Branches → Add branch ruleset, target `main`):

- Require a pull request before merging.
- Require status checks to pass: `lint`, `test`, `security`, `build`.
- Block force pushes. Restrict deletions.
- Do not allow bypassing the above (include administrators).

Evidence to collect once the repository is on GitHub:

1. A direct `git push origin main` rejected by the server.
2. A pull request with a failing check, showing the merge button blocked.
3. The same pull request merged after the check passes.

## Status

Implemented and verified locally: lint, tests, dependency audit, build, the pre-commit hook and
the guard hook. The workflow runs on GitHub: https://github.com/raduhg/attacks-llm-integrated-apps/actions.
Not yet applied: branch protection on `main`, and the evidence listed above.
