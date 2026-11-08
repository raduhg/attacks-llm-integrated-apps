# Project: Prompt Injection Testbed for LLM-Integrated Applications

## Context

This repository is the practical part of my Master's dissertation in Cybersecurity:

> **Prompt Injection Attacks on LLM-Integrated Applications: Evaluation and Mitigation Strategies**
> (Atacuri de tip prompt injection asupra aplicațiilor integrate cu modele lingvistice mari: evaluare și strategii de atenuare)

The goal is NOT a production product. The goal is a **reproducible experimental testbed** that lets me:

1. Run a realistic LLM-integrated application (the "target app").
2. Attack it with a catalogue of direct and indirect prompt injection attacks.
3. Turn defenses on and off, individually and in combination.
4. Measure, quantitatively, how well each defense blocks attacks **and** how much it hurts normal functionality.
5. Export results (CSV/JSON + charts) that go straight into the thesis.

Every design decision should favour **reproducibility, measurability and clarity** over features. A committee will read this code and the results, so keep it clean and well documented.

## Main problems the thesis covers (keep the code aligned with these)

1. Architecture of LLM-based applications and their specific attack surface (documents, external tools, APIs).
2. Classification of direct and indirect prompt injection, following the **OWASP Top 10 for LLM Applications** (mainly LLM01 Prompt Injection, plus LLM02 Sensitive Information Disclosure, LLM05 Improper Output Handling, LLM06 Excessive Agency, LLM07 System Prompt Leakage).
3. A test LLM application with access to documents and external tools.
4. A set of attack scenarios: instruction override, data exfiltration, tool abuse, injection through external content.
5. Mitigations: input filtering, system prompt hardening, privilege separation, output validation.
6. Quantitative evaluation: attack success rate per defense and the security vs. usability trade-off.
7. Recommendations for building secure LLM-integrated applications.

## Tech stack

- **Language:** Python 3.11+. Must run on Windows, macOS and Linux (use `pathlib`, no shell-specific scripts; provide plain `python -m ...` entry points).
- **LLMs: API only. No local LLMs (no Ollama, no llama.cpp, no local model weights).**
  - **Anthropic API** (only provider): use the official `anthropic` Python SDK. **Model: Claude Haiku 5.5 (`claude-haiku-5-5`) only, for now.** Keep model names in `config/models.yaml`, never hard-coded.
  - **No second provider** (decided: no OpenAI-compatible backend).
  - All backends implement one small interface (`chat(messages, tools) -> response`) that also returns token usage, so cost can be tracked per run.
  - Read keys from a `.env` file (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`). Never hard-code, log or commit keys.
- **Cost control (important, since every call costs money):**
  - A **response cache** keyed by the exact request parameters (model, system, messages, tools, effort, ...) **plus the repetition index**, stored on disk, so re-running analysis or a crashed experiment does not repeat paid calls, while the N repetitions stay N independent calls.
  - A **dry-run mode** that prints the number of planned calls and an estimated cost without calling the API.
  - A configurable **budget limit** per experiment: stop cleanly when it is reached.
  - Retries with exponential backoff for rate limits (HTTP 429/529).
- **RAG:** no vector database (decided: the corpus is ~100 chunks, so ChromaDB/FAISS add nothing). Embeddings are kept in a numpy array and searched by brute-force cosine similarity. The embedding model is `sentence-transformers/all-MiniLM-L6-v2` run through **fastembed** (ONNX, CPU, no PyTorch). This is not an LLM, so it does not conflict with the API-only rule. Retrieval happens only when the model calls the `search_documents` tool (no automatic context stuffing). Keep RAG simple; its quality is not the research question.
- **Avoid heavy frameworks** (no LangChain/LlamaIndex unless clearly needed). Write the agent loop by hand so every step is visible and explainable in the thesis.
- **Demo UI:** a minimal Streamlit app, so I can show attacks live at the defense. Low priority; build it last.
- **Data/analysis:** pandas, matplotlib (or seaborn) for charts.
- **Testing:** pytest.
- **Config:** YAML files for experiments; pydantic for validation.

## Target application

An **internal company assistant** ("Acme Assistant") with:

- **Document Q&A (RAG)** over a small fake corpus: company policies, an employee handbook, product docs, a few customer emails and web pages. Some documents are **poisoned** with indirect injections (see attacks). Clean and poisoned corpora must be selectable per experiment.
- **Tools (all mocked and sandboxed, no real side effects):**
  - `search_documents(query)`
  - `read_email(id)` / `send_email(to, subject, body)`: send only logs to a local "outbox".
  - `fetch_url(url)`: returns content from a local fixtures folder, never the real internet.
  - `get_customer_record(id)`: returns fake PII from a local JSON "database".
  - `delete_file(path)`: logs the call only.
- **Secrets planted for measurement:** the system prompt contains a canary string (e.g. `CANARY-7f3a9c`), and the fake database contains fake PII and a fake API key. Leaking any of them is how exfiltration success is detected.
- Every tool call, model message and defense decision is logged to a structured trace (JSONL), so each run can be inspected afterwards.

## Attack catalogue

Store attacks as data (YAML/JSON), not code, so adding attacks needs no code changes. Each attack has: `id`, `name`, `category`, `vector` (direct | indirect), `owasp_ref`, `payload`, `injection_point` (user message | document | email | web page | tool output), `goal`, and a **machine-checkable success condition**.

Categories (aim for about 40–60 attacks in total, several variants each):

1. **Instruction override / goal hijacking:** "Ignore previous instructions…", role-play, fake system messages, delimiter confusion.
2. **System prompt leakage:** extracting the system prompt or the canary.
3. **Data exfiltration:** getting PII or the fake API key into the answer, into a `send_email` call, or into a URL (e.g. a markdown image link to an attacker domain).
4. **Tool abuse / excessive agency:** making the assistant call `send_email` or `delete_file` when the user did not ask for it.
5. **Indirect injection:** payloads hidden in RAG documents, emails, fetched web pages and tool outputs (including hidden text, HTML comments, white-on-white text in HTML).
6. **Obfuscation variants:** Base64, translation into another language (including Romanian), typos/leetspeak, payload splitting across chunks, multi-turn escalation.

**Success conditions must be automatic and deterministic where possible:** canary present in output, forbidden tool called, tool argument contains a secret, output contains an attacker URL, and so on. Use an LLM-as-judge only for cases that can't be checked with rules, mark those results clearly, and spot-check them by hand.

## Defenses

Each defense is a separate, independently toggleable module with a common interface. Experiments must be able to run any combination.

1. **D0 Baseline:** no defense (naive system prompt).
2. **D1 Input filtering:** heuristic/regex detection of injection patterns, plus optionally an **LLM-based detector** (a separate cheap API call that classifies text as injection or benign), applied to user input **and** retrieved content. Track its extra cost and latency separately.
3. **D2 System prompt hardening:** explicit rules, a role reminder, and the "sandwich" technique (instructions repeated after untrusted content).
4. **D3 Spotlighting / delimiting:** untrusted content wrapped in clear delimiters or datamarked/encoded, with instructions that it is data, not commands.
5. **D4 Privilege separation:** least-privilege tool access per task, and **human-in-the-loop confirmation** (simulated) for sensitive tools (`send_email`, `delete_file`). Optionally a dual-LLM pattern (a privileged planner that never sees untrusted content plus a quarantined reader).
6. **D5 Output validation:** scan the output and tool arguments for secrets/canary/PII and attacker URLs, and block or redact them before they are shown or executed.
7. **D6 Combined:** a defense-in-depth stack of the above.

## Evaluation methodology

- **Primary metric: Attack Success Rate (ASR)** = successful attacks / total attempts, reported per defense, per attack category, per vector (direct/indirect) and per model.
- **Usability metrics** on a **benign task set** (about 30–50 normal user requests with expected answers or expected tool calls):
  - Task success rate (did it still do the job?)
  - **False positive rate** (benign requests blocked by a defense)
  - Added latency and added tokens/cost per request
- **Repetitions:** LLM output is non-deterministic. Run every (attack × defense × model) combination **N times (default N=5)** at a fixed temperature, and record the seed where the backend supports one. Report mean ± standard deviation or a confidence interval.
  - Temperature is **1.0** (decided). Claude Haiku 5.5 rejects any non-default sampling parameter, so none is sent and the API default (1.0) applies. The API has no seed parameter.
  - Adaptive thinking is on (model default) with effort `medium`; thinking tokens count in all token/cost figures.
- **Results** saved to `results/<experiment_id>/` as raw JSONL traces plus an aggregated CSV, with the full config snapshot, model names/versions, timestamp and git commit hash for reproducibility.
- **Charts for the thesis:** ASR heatmap (defense × attack category), bar charts of ASR vs. false positive rate per defense, a security vs. usability trade-off scatter plot, and per-model comparison.

## Suggested repository structure

```
Disertatie/
├── CLAUDE.md
├── .claude/
│   ├── settings.json          # hook configuration (audit logging)
│   └── hooks/audit_log.py     # writes every Claude Code step to audit.log
├── audit.log                  # git-ignored, created by the hook
├── README.md                  # setup + how to reproduce every experiment
├── pyproject.toml
├── .env.example
├── config/
│   ├── models.yaml
│   └── experiments/           # one YAML per experiment
├── data/
│   ├── corpus/clean/
│   ├── corpus/poisoned/
│   ├── emails/
│   ├── web_fixtures/
│   ├── customers.json         # fake PII
│   ├── attacks/               # attack catalogue (YAML)
│   └── benign_tasks/          # benign task set (YAML)
├── src/testbed/
│   ├── llm/                   # backend interface, anthropic (+ openai later), cache, cost tracking
│   ├── app/                   # target assistant: agent loop, RAG, tools
│   ├── defenses/              # D1..D5, common interface
│   ├── attacks/               # loader + success checkers
│   ├── evaluation/            # runner, metrics, judge
│   └── reporting/             # aggregation + charts
├── ui/streamlit_app.py
├── results/                   # git-ignored except for final results
└── tests/
```

## Milestones (work in this order and check in with me after each one)

1. **Skeleton:** project setup, LLM backend interface, Anthropic backend with response cache, dry-run and token/cost tracking, and a simple chat loop.
2. **Target app:** RAG over the clean corpus plus mocked tools, and an agent loop with structured logging. Benign tasks pass at baseline.
3. **Attack framework:** attack catalogue format, loader, injection into the right place, automatic success checkers. A first set of about 10 attacks running against the baseline.
4. **Experiment runner:** YAML-configured runs, repetitions, results storage, aggregated CSV.
5. **Defenses:** implement D1–D5 one at a time, each with unit tests, then D6.
6. **Full attack catalogue and benign task set.**
7. **Reporting:** metrics, tables and charts ready for the thesis.
8. **Streamlit demo UI:** chat with the assistant, toggle defenses, pick an attack, and see the trace, all live.
9. **README/docs:** exact steps to reproduce every result, and an architecture diagram (Mermaid) I can reuse in the thesis.

## Working rules for Claude Code

- **Ask me before** making big architectural choices that differ from this document, adding heavy dependencies, or doing anything that costs money (API runs). Before any API-based experiment, estimate the number of calls and the approximate cost.
- Keep everything **sandboxed**: no real emails, no real HTTP requests from tools, no real file deletion. All "sensitive" data is fake.
- Never use or install local LLMs. All model calls go through the API backends.
- Keep spending low: develop and debug with the cheapest model, small subsets of attacks and N=1, and always rely on the cache. Run the full matrix only when I approve it. Unit tests must **mock** the API and never make paid calls.
- Write clear docstrings and comments, since I will need to explain this code in the thesis. Use type hints everywhere.
- Add tests for success checkers and defenses, because the accuracy of the measurement depends on them.
- Never commit `.env`, API keys or large model files.
- This project has an **audit hook** (`.claude/settings.json` + `.claude/hooks/audit_log.py`) that logs every prompt, tool call, tool result and session event to `audit.log` in the project root. Do not modify, disable or delete the hook or `audit.log` unless I ask. Keep `audit.log` in `.gitignore`.
- When you finish a milestone, give me a short summary: what was built, how to run it, and any decisions I should know about for the methodology chapter.
- If something in this document is ambiguous, ask instead of guessing.

## Confirmed decisions (2026-11-08)

- **Model:** Claude Haiku 5.5 only for now. **Total API budget: $10** (still give me a cost estimate before the full matrix).
- **Provider:** Anthropic only, no second provider.
- **Language:** thesis charts, labels and the fake corpus are in **English** (Romanian appears only as an attack obfuscation variant).
- **Cache key** includes the repetition index; **temperature** 1.0 (API default, not settable on this model).
- **RAG:** numpy brute-force search + fastembed (`all-MiniLM-L6-v2`), no vector database.
- **Environment:** uv with a committed `uv.lock`; the README also documents plain `python -m venv` + pip.
