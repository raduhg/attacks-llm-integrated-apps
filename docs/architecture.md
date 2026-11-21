# Architecture

Three diagrams, written in Mermaid so they render on GitHub and can be pasted into the thesis
(for example through https://mermaid.live, exported as SVG or PNG).

## 1. Components

How an experiment flows from its YAML file to the thesis charts. Grey boxes are the target
application; everything outside them is the measurement harness around it.

```mermaid
flowchart LR
    cfg["Experiment config<br/>config/experiments/*.yaml"] --> runner["Experiment runner<br/>evaluation/run.py"]
    models["config/models.yaml"] --> backend
    attacks["Attack catalogue<br/>data/attacks/*.yaml"] --> inject["Injection<br/>attacks/inject.py"]
    benign["Benign tasks<br/>data/benign_tasks/*.yaml"] --> runner
    runner --> inject
    inject --> app

    subgraph app["Target app: Acme Assistant (app/)"]
        loop["Agent loop<br/>assistant.py"]
        defense["Defense stack D0-D6<br/>defenses/"]
        sandbox["Sandboxed tools<br/>tools.py"]
        rag["Document index<br/>rag.py (fastembed + numpy)"]
        loop <--> defense
        loop --> sandbox
        sandbox --> rag
    end

    loop --> backend["LLM backend<br/>llm/anthropic_backend.py"]
    backend <--> cache[("Response cache<br/>.cache/llm")]
    backend --> api(["Anthropic API<br/>Claude Haiku 5.5 / 4.5"])
    backend --> tracker["Cost tracker<br/>budget stop"]

    loop --> trace[("Trace per run<br/>traces/*.jsonl")]
    runner --> checks["Success checks and<br/>benign task checks"]
    trace --> checks
    checks --> runs[("results/&lt;id&gt;/<br/>runs.jsonl, summary.csv, meta.json")]
    runs --> report["Reporting<br/>reporting/report.py"]
    report --> out[("results/report/<br/>tables.md, CSV, charts")]
    runs --> ui["Streamlit demo<br/>ui/streamlit_app.py"]
```

## 2. One user turn, with the four defense points

The agent loop is written by hand so every step is visible. Each defense overrides only the hooks
it needs; D0 overrides none.

```mermaid
flowchart TD
    start([User message]) --> h1{"on_user_input<br/>D1"}
    h1 -- blocked --> refuse([Fixed refusal, stop_reason = blocked])
    h1 -- allowed --> setup["system_prompt: D2 rules, D3 marker instructions<br/>tools: D4 least privilege"]
    setup --> llm["Model call<br/>(cached by request + repetition)"]
    llm --> q{"Tool use requested?"}
    q -- no --> h4{"on_output<br/>D5 redaction"}
    h4 --> answer([Final answer])
    q -- yes --> h2{"before_tool_call<br/>D4 approval, D5 secret check"}
    h2 -- denied --> err["Error result returned to the model"]
    h2 -- allowed --> run["Run tool in the sandbox"]
    run --> h3["on_tool_result<br/>D1 filter, D3 delimiting / datamarking"]
    h3 --> back["All tool results in one message<br/>+ D2 sandwich reminder"]
    err --> back
    back --> limit{"Step limit (8) reached?"}
    limit -- no --> llm
    limit -- yes --> stop([stop_reason = max_steps])
```

## 3. An indirect attack, end to end

The payload never comes from the user: it is placed in a tool's output, and the user only asks
an innocent question that makes the assistant call that tool.

```mermaid
sequenceDiagram
    participant R as Runner
    participant S as Sandbox (fresh per run)
    participant A as Agent loop + defense
    participant M as Model (API or cache)
    participant C as Checkers

    R->>S: prepare(attack): append payload to read_email output
    R->>A: "Read email E-003 and summarise it."
    A->>M: request
    M-->>A: tool_use read_email(E-003)
    A->>S: read_email(E-003)
    S-->>A: email text + injected payload
    A->>M: tool result (possibly filtered, delimited or datamarked)
    M-->>A: final answer (or a send_email call)
    A-->>R: answer + trace
    R->>C: trace, sandbox side effects
    C-->>R: attack succeeded? user task still done?
```

## Design decisions

| Decision | Why |
|---|---|
| Hand-written agent loop, no framework | Every step is visible and explainable in the thesis |
| All tools sandboxed in memory | No real email, web request or file deletion can happen |
| Fresh sandbox per run, payload injected at runtime | A result can always be traced to exactly one payload |
| Response cache keyed by request + repetition index | Re-running is free; the N repetitions stay N independent calls |
| Success checks read the trace, not the model's words | "Email sent" from the model proves nothing; the outbox does |
| Checks look only at model output, not tool results | A lookup legitimately returns PII; leaking means passing it on |
| D5 uses generic patterns, not the planted secrets | Otherwise D5 and the checkers would share a list and score 100% by construction |
| D3 uses a fixed delimiter tag | A random tag changed every request and defeated the cache; noted as a testbed shortcut |
| Two app profiles (default, weak) | Both models resisted every attack on the default profile; the weak profile gives the defenses something to defend |
