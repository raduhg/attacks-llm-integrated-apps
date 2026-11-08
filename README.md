# Prompt Injection Testbed

Experimental testbed for the dissertation *Prompt Injection Attacks on LLM-Integrated
Applications: Evaluation and Mitigation Strategies*. See `CLAUDE.md` for the full design.

Status: **Milestone 1** (LLM backend, response cache, cost tracking, dry-run, chat loop).

## Setup

Requires Python 3.11+. Works on Windows, macOS and Linux.

With [uv](https://docs.astral.sh/uv/) (exact versions from `uv.lock`):

```
uv sync
```

Or with plain pip:

```
python -m venv .venv
.venv\Scripts\activate        # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -e . pytest
```

Then copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`.

## Run

```
uv run pytest                              # offline tests; the API is mocked
uv run python -m testbed.chat --dry-run    # no API calls, prints estimated cost
uv run python -m testbed.chat --budget 0.05
```

(Without uv, drop the `uv run` prefix inside the activated venv.)

## Cost control

- **Response cache** (`.cache/llm/`, one JSON file per call): keyed by the exact request
  parameters plus the repetition index, so the N repetitions of an experiment are real
  independent calls, while re-running anything is free.
- **Dry-run mode**: estimates tokens (~4 characters/token for input, a fixed per-call
  output allowance from `config/models.yaml`) and cost without calling the API.
- **Budget limit**: checked before every paid call; stops cleanly with `BudgetExceeded`.
- **Retries**: the Anthropic SDK retries 429/529/5xx with exponential backoff
  (`max_retries` in `config/models.yaml`).

## Methodology notes

- Model: Claude Haiku 5.5 (`claude-haiku-5-5`), configured in `config/models.yaml`.
- Temperature: this model rejects non-default sampling parameters, so none are sent and
  every call uses the API default temperature of 1.0. The API has no seed parameter.
- Adaptive thinking is on (model default), effort `medium`. Thinking tokens are billed as
  output tokens and are included in all token/cost figures.
