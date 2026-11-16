---
name: run-experiment
description: Run a testbed experiment from a YAML config safely - dry run, cost approval, paid run, cache check, validity check, summary. Use whenever the user asks to run, re-run or probe an experiment in config/experiments/.
---

# Run an experiment

Every experiment costs real money and its numbers go into a dissertation. Follow these steps in
order and do not skip one because the run "looks small".

## 1. Check the config

- The file is in `config/experiments/` and names the model, app profile (`system_prompt`),
  defenses, attack files, benign files, repetitions and `budget_usd`.
- Run `uv run pytest -q`. Do not spend money on a failing tree.

## 2. Dry run

```
uv run python -m testbed.evaluation.run config/experiments/<id>.yaml --dry-run
```

Report to the user: runs planned, runs needing new API calls, the dry-run cost, and a likely cost
from the measured cost per run of the same model. The dry-run figure is a worst case.

## 3. Ask for approval

State the model, the likely cost, the budget cap in the file and the budget spent so far. Wait for
an explicit yes. If the figure is several times an earlier quote, say so and ask again.
Never call a re-run free unless the dry run shows 0 runs needing new API calls.

## 4. Paid run

```
uv run python -m testbed.evaluation.run config/experiments/<id>.yaml
```

Run long experiments in the background. A budget stop is not a failure: everything done is cached.

## 5. Check the measurement is valid

- Status is `completed` and the run count equals the planned count.
- For every new indirect attack, confirm in `results/<id>/traces/` that the payload appears in a
  `tool_result` event. A payload that never reached the model is a non-measurement.
- Read a few answers when a rate is exactly 0 or 1.
- Run the same command again: it must report `0 API calls`. If not, some request content is
  non-deterministic; find and fix it before reporting.

## 6. Report

Give ASR, utility under attack and benign success per defense as counts with sample sizes, the
model and app profile, the real cost, and what was not checked. If the working tree was dirty,
say that `meta.json` records `git_dirty: true` and that a re-run after committing fixes it.

## 7. Commit only when asked

`results/` is git-ignored. Commit configs and code when the user asks, never the `.env` file.
