# Prompt Injection Testbed

Experimental testbed for the dissertation *Prompt Injection Attacks on LLM-Integrated
Applications: Evaluation and Mitigation Strategies* (Master's in Cybersecurity).

It runs a realistic LLM-integrated application, attacks it with direct and indirect prompt
injections, turns defenses on and off, and measures both how many attacks succeed and how much
each defense hurts normal use. Every number in the thesis can be regenerated from this repository.

- **Architecture and diagrams:** [docs/architecture.md](docs/architecture.md)
- **Security risk register and CI pipeline:** [docs/security-risk-project.md](docs/security-risk-project.md)
- **How the AI coding agent is configured:** [docs/ai-configuration.md](docs/ai-configuration.md)
- **Full design and decisions:** [CLAUDE.md](CLAUDE.md)

## What is in it

| Part | Where | What it does |
|---|---|---|
| Target app | `src/testbed/app/` | "Acme Assistant": document search (RAG) plus six sandboxed tools (`search_documents`, `read_email`, `send_email`, `fetch_url`, `get_customer_record`, `delete_file`). No real email, web request or file deletion ever happens |
| LLM backend | `src/testbed/llm/` | Anthropic API, response cache, cost tracking, budget stop, dry run |
| Attacks | `src/testbed/attacks/`, `data/attacks/` | 28 attacks: 20 indirect data-exfiltration cases from InjecAgent (base and enhanced) and 8 system-prompt-leakage attacks; injected at runtime into the right place; deterministic success checks |
| Benign tasks | `data/benign_tasks/` | 40 ordinary requests with expected answers and tool calls, for false-positive and usability measurement |
| Defenses | `src/testbed/defenses/` | D0 (none), D1 input filter (regex, optional LLM detector), D2 prompt hardening, D3 spotlighting (optional datamarking), D4 privilege separation, D5 output validation, D6 all combined |
| Runner and metrics | `src/testbed/evaluation/` | YAML-configured experiments, N repetitions, Wilson 95% intervals |
| Reporting | `src/testbed/reporting/` | Thesis tables and charts from the results on disk |
| Demo | `ui/streamlit_app.py` | Chat with the assistant, toggle defenses, replay attacks, inspect traces |

## Setup

Python 3.11 or newer, on Windows, macOS or Linux.

With [uv](https://docs.astral.sh/uv/), which installs the exact versions in `uv.lock`:

```
uv sync
```

Or with plain pip:

```
python -m venv .venv
.venv\Scripts\activate          # Windows; on macOS/Linux: source .venv/bin/activate
pip install -e . pytest ruff
```

Then:

1. Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`. The `.env` file is git-ignored.
2. Optional, recommended: enable the local secret check with `git config core.hooksPath .githooks`.
3. The first run downloads the embedding model (`all-MiniLM-L6-v2`, about 90 MB) into
   `.cache/embeddings/`. No API key is needed for that.

Without uv, run the commands below inside the activated environment and drop the `uv run` prefix.

## Check the installation (offline, free)

```
uv run pytest -q          # 100 tests; the API is always mocked
uv run ruff check .       # lint, including security rules
```

## Reproducing the results

Every experiment is a YAML file in `config/experiments/`. Always dry-run first: it prints the
number of planned API calls and a worst-case cost.

```
uv run python -m testbed.evaluation.run config/experiments/<id>.yaml --dry-run
uv run python -m testbed.evaluation.run config/experiments/<id>.yaml
```

Each run writes `results/<id>/` with `meta.json` (full config, model, package versions, git
commit, timestamps), `runs.jsonl` (one row per run), `summary.csv` and one trace per run.

| Experiment | Model | App profile | Defenses | Attacks | Benign | N | Runs | Cost from an empty cache |
|---|---|---|---|---|---|---|---|---|
| `m4_baseline` | Haiku 5.5 | default | D0 | 10 exfiltration | 11 | 5 | 105 | about $0.04 |
| `m5_defenses` | Haiku 5.5 | default | all 9 | 20 exfiltration (base + enhanced) | 40 | 5 | 2,700 | about $0.99 |
| `m6_leakage` | Haiku 5.5 | default | 8 (no D3-dm) | 8 leakage | – | 5 | 320 | about $0.07 |
| `m6_haiku45_probe` | Haiku 4.5 | default | D0 | 20 exfiltration | – | 3 | 60 | about $0.18 |
| `m6_weak_probe` | Haiku 5.5 | weak | D0 | 28 (both categories) | – | 3 | 84 | about $0.03 |
| `m6_weak_probe_haiku45` | Haiku 4.5 | weak | D0 | 28 (both categories) | – | 3 | 84 | about $0.23 |
| `m6_weak_haiku45_defenses` | Haiku 4.5 | weak | all 9 | 8 leakage | 11 | 5 | 855 | about $2.24 |
| `m6_benign_smoke` | Haiku 5.5 | default | D0 | – | 29 | 1 | 29 | about $0.01 |

The cost column is the sum of the original cost of every call in that experiment, which is what a
fresh clone with no response cache pays. Experiments share some calls, so running all of them
costs somewhat less than the sum (about $3.80). `m6_weak_defenses` is configured but deliberately
not run: the probe showed Haiku 5.5 is not vulnerable even on the weak profile.

**What "reproduce" means here.** The model runs at temperature 1.0 (the API default; this model
does not accept another value and has no seed). Re-running on the machine that produced the
results is served from the response cache in `.cache/llm/` and gives identical numbers for free.
Running from a fresh clone makes new API calls, so individual runs differ; the rates should fall
within the reported 95% intervals. To share the exact runs, copy `.cache/llm/` (it holds only
requests and responses to fake data, and no key).

Then build the thesis tables and charts (no API calls):

```
uv run python -m testbed.reporting.report
```

This writes `results/report/`: `tables.md`, per-defense CSV files, and four charts
(`fig_asr_heatmap.png`, `fig_asr_fpr.png`, `fig_tradeoff.png`, `fig_models.png`).

### Detector accuracy (D1)

The D1 detectors are also scored on a labelled public dataset (deepset/prompt-injections, 116
test prompts):

```
uv run python -m testbed.defenses.detector_eval --split test          # regex only, free
uv run python -m testbed.defenses.detector_eval --split test --llm    # plus LLM detector, about $0.005
```

Result on the test split: regex precision 1.000, recall 0.050; LLM detector precision 1.000,
recall 0.567. This result is printed, not saved under `results/`.

## Headline results

All on fake data, in the sandbox. Every number is tied to a model and an app profile.

- **Default profile:** Claude Haiku 5.5 and Haiku 4.5 resisted every attack with no defense: 0/100
  exfiltration runs and 0/40 leakage runs on Haiku 5.5, 0/60 exfiltration runs on Haiku 4.5.
  Defenses therefore differ only in cost to usability: D1 and D1-LLM fail 15/200 benign runs,
  D5 10/200, D6 20/200; D2, D3 and D4 fail none.
- **Weak profile** (a deliberately vulnerable system prompt): Haiku 5.5 still resisted (0/84),
  Haiku 4.5 leaked the canary in 19/40 runs. There, D2, D1-LLM and D6 reduced leakage to 0/40,
  D3 to 6/40 (all indirect leaks stopped), while D4 and D5 had no effect.

Full tables and intervals: `results/report/tables.md` after running the reporting command.

## Live demo

```
uv run streamlit run ui/streamlit_app.py
```

Choose a model, app profile and defense, then chat or run any attack from the catalogue. The
page shows whether the attack succeeded, whether the user's own task was still done, and every
step of the trace, including each defense decision. Repetitions 0–4 replay the measured runs from
the cache for free; anything new is a paid call, limited by the budget in the sidebar, and a
dry-run switch turns API calls off.

## Cost control

- **Response cache** (`.cache/llm/`, one JSON file per call), keyed by the exact request plus the
  repetition index: N repetitions are N real calls, and any re-run is free.
- **Dry run:** estimates calls and cost without calling the API.
- **Budget:** each experiment has `budget_usd`; the runner stops cleanly when it is reached, and a
  re-run resumes from the cache.
- **Retries:** the SDK retries rate limits and overloads (429/529) with exponential backoff.
- **No API key in CI:** tests mock the API.

## Methodology notes

- **Models** are configured in `config/models.yaml` and never hard-coded. Haiku 5.5 runs with
  adaptive thinking at effort `medium`; Haiku 4.5 has no thinking. Thinking tokens are counted in
  all token and cost figures.
- **App profiles:** `default` is a realistic system prompt; `weak` removes the confidentiality note
  and tells the assistant to act on requests it finds in content it reads. Selected per
  experiment with `system_prompt:`.
- **Success is checked from the trace**, not from the model's words: the canary or a planted
  secret in the model's own output, a forbidden tool call, or a URL to the attacker's domain.
  Tool results are excluded, because a lookup legitimately returns fake PII to the model.
- **Utility under attack** checks whether the user's own request was still completed, using the
  same rules as the benign task set.
- **Retrieval** returns the top 5 document sections (raised from 3 because the embedding model
  ranked exact error codes poorly).
- **Known limits:** secret checks are exact text matches, so a re-encoded leak is missed; D3 uses a
  fixed delimiter tag so that requests stay cacheable; attack categories cover exfiltration and
  leakage, not yet tool abuse or obfuscation.

## Data and licences

All "sensitive" data in `data/` is invented. Third-party attack data is used under its licence,
with source, revision and licence recorded next to it:

- InjecAgent (MIT, Findings of ACL 2024): `data/external/injecagent/SOURCE.md`
- deepset/prompt-injections (Apache-2.0): `data/external/deepset_prompt_injections/SOURCE.md`
