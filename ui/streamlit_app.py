"""Live demo of the testbed: chat with Acme Assistant, switch defenses, replay attacks, see traces.

    uv run streamlit run ui/streamlit_app.py

Two modes:
  - Chat: talk to the assistant yourself, under any defense and app profile.
  - Attack: pick an attack from data/attacks/, run it, and see whether it succeeded, whether the
    user's own task was still done, and every step the assistant and the defense took.

Cost: every new request is a paid API call, so the sidebar has a budget cap and a dry-run switch.
Attack runs at repetitions 0-4 with the same model, profile and defense as an experiment are
served from the response cache: they replay the measured run exactly, for free.

The UI only wires existing pieces together (Assistant, prepare, build_defense, the checkers); it
adds no testbed logic of its own, so what the demo shows is what the experiments measured.
"""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

from testbed.app import Assistant, Sandbox, Trace, build_index
from testbed.app.assistant import SYSTEM_PROMPTS
from testbed.attacks.checkers import attack_succeeded, user_task_completed
from testbed.attacks.inject import prepare
from testbed.attacks.schema import ATTACKS_DIR, Attack, load_attacks
from testbed.config import load_models
from testbed.defenses import KNOWN_DEFENSES, build_defense
from testbed.evaluation.benign import tasks_by_id
from testbed.llm import BudgetExceeded, make_backend

DEFENSE_ORDER = ["D0", "D1", "D1-LLM", "D2", "D3", "D3-dm", "D4", "D5", "D6"]
DEFENSE_NAMES = {
    "D0": "D0 - no defense", "D1": "D1 - input filter (regex)", "D1-LLM": "D1-LLM - input filter (LLM detector)",
    "D2": "D2 - prompt hardening", "D3": "D3 - spotlighting", "D3-dm": "D3-dm - spotlighting + datamarking",
    "D4": "D4 - privilege separation", "D5": "D5 - output validation", "D6": "D6 - all combined",
}
DEFENSE_ORDER += sorted(set(KNOWN_DEFENSES) - set(DEFENSE_ORDER))  # a defense added later still appears


@st.cache_resource
def index() -> Any:
    """Embedding index over the clean corpus; built once per server process."""
    return build_index("clean")


@st.cache_data
def attacks() -> dict[str, Attack]:
    return {a.id: a for p in sorted(ATTACKS_DIR.glob("*.yaml")) for a in load_attacks(p)}


def backend(model: str, budget: float, dry_run: bool) -> Any:
    """One backend (and cost tracker) per settings combination, kept for the session."""
    key = f"backend:{model}:{budget}:{dry_run}"
    if key not in st.session_state:
        st.session_state[key] = make_backend(model, dry_run=dry_run, budget_usd=budget)
    return st.session_state[key]


def show_trace(events: list[dict[str, Any]]) -> None:
    """Render a run's trace: model calls, tool calls and results, and every defense decision."""
    for e in events:
        kind = e["event"]
        if kind == "model_call":
            u = e["usage"]
            src = "cache" if e["cached"] else ("dry run" if e["dry_run"] else "API")
            st.caption(f"Model call {e['step']}: {u['input_tokens']} in / {u['output_tokens']} out tokens, "
                       f"${e['cost_usd']:.5f}, stop = {e['stop_reason']}, from {src}")
        elif kind == "tool_call":
            st.markdown(f"**Tool call** `{e['name']}`")
            st.code(json.dumps(e["input"], indent=2, ensure_ascii=False), language="json")
        elif kind == "tool_result":
            with st.expander(f"Tool result from `{e['name']}`" + (" (error)" if e["is_error"] else "")):
                st.text(e["output"])
        elif kind == "defense_decision":
            st.warning(f"Defense {e['defense']} acted at `{e['hook']}`" + (f": {e['reason']}" if e.get("reason") else ""))
        elif kind == "detector_call":
            st.caption(f"D1-LLM detector call: ${e['cost_usd']:.5f}")


def sidebar() -> dict[str, Any]:
    models = load_models()
    with st.sidebar:
        st.header("Settings")
        model = st.selectbox("Model", list(models.models), index=list(models.models).index(models.default))
        profile = st.radio("App profile", list(SYSTEM_PROMPTS), horizontal=True,
                           help="default: the realistic prompt. weak: deliberately vulnerable (see CLAUDE.md).")
        defense = st.selectbox("Defense", DEFENSE_ORDER, format_func=lambda d: DEFENSE_NAMES.get(d, d))
        st.divider()
        budget = st.number_input("Budget for this session (USD)", min_value=0.01, max_value=2.0, value=0.10, step=0.05)
        dry_run = st.toggle("Dry run (no API calls)", value=False)
        spend = st.empty()  # filled at the end of the script, so it includes this run's calls
    return {"model": model, "profile": profile, "defense": defense, "backend": backend(model, budget, dry_run),
            "dry_run": dry_run, "spend": spend}


def chat_tab(cfg: dict[str, Any]) -> None:
    key = f"chat:{cfg['model']}:{cfg['profile']}:{cfg['defense']}"
    history = st.session_state.setdefault(key, {"messages": [], "turns": []})
    if st.button("New conversation"):
        history["messages"].clear()
        history["turns"].clear()
    for user_text, answer, events in history["turns"]:
        st.chat_message("user").write(user_text)
        with st.chat_message("assistant"):
            st.write(answer or "*(no answer)*")
            with st.expander("Trace"):
                show_trace(events)
    if prompt := st.chat_input("Ask Acme Assistant"):
        trace = Trace()
        assistant = Assistant(cfg["backend"], Sandbox(index()), system=SYSTEM_PROMPTS[cfg["profile"]], trace=trace,
                              defense=build_defense(cfg["defense"]))
        start = len(history["messages"])
        history["messages"].append({"role": "user", "content": prompt})
        try:
            result = assistant.run(history["messages"])
        except BudgetExceeded as e:
            del history["messages"][start:]  # keep the history valid for the API
            st.error(str(e))
            return
        history["turns"].append((prompt, result.answer, trace.events))
        st.rerun()


def attack_tab(cfg: dict[str, Any]) -> None:
    catalogue = attacks()
    attack = catalogue[st.selectbox("Attack", list(catalogue), format_func=lambda i: f"{i}: {catalogue[i].name}")]
    st.write(f"**Category:** {attack.category.replace('_', ' ')} · **Vector:** {attack.vector} · "
             f"**Injected into:** {attack.injection_point.replace('_', ' ')} · **OWASP:** {attack.owasp_ref}")
    st.write(f"**Goal:** {attack.goal}")
    st.write(f"**User's request:** {attack.user_prompt or '(the payload is the user message)'}")
    with st.expander("Payload"):
        st.text(attack.payload)
        st.caption(f"Source: {attack.source or 'n/a'}")
    rep = st.number_input("Repetition", min_value=0, max_value=99, value=0,
                          help="0-4 replay the cached experiment runs for this model, profile and defense (free).")
    if not st.button("Run attack", type="primary"):
        return
    sandbox, messages = prepare(attack, index())
    trace = Trace()
    assistant = Assistant(cfg["backend"], sandbox, system=SYSTEM_PROMPTS[cfg["profile"]], trace=trace,
                          defense=build_defense(cfg["defense"]))
    try:
        result = assistant.run(messages, repetition=int(rep))
    except BudgetExceeded as e:
        st.error(str(e))
        return
    fired = attack_succeeded(attack.success, trace, sandbox)
    done = user_task_completed(tasks_by_id()[attack.user_task], trace) if attack.user_task else None
    if fired:
        st.error(f"Attack SUCCEEDED: {', '.join(fired)}")
    elif result.stop_reason == "refusal":
        st.info("Attack failed: the model refused.")
    else:
        st.success("Attack failed: no success condition fired.")
    if done is not None:
        st.write(f"User's own task completed: **{'yes' if done else 'no'}**")
    if sandbox.outbox or sandbox.deleted:
        st.write("Recorded side effects (sandbox only):", {"outbox": sandbox.outbox, "deleted": sandbox.deleted})
    st.subheader("Answer shown to the user")
    st.write(result.answer or "*(no answer)*")
    st.subheader("Trace")
    show_trace(trace.events)


def main() -> None:
    st.set_page_config(page_title="Prompt injection testbed", layout="wide")
    st.title("Prompt injection testbed: Acme Assistant")
    cfg = sidebar()
    st.caption(f"Model `{cfg['model']}`, {cfg['profile']} profile, defense {DEFENSE_NAMES.get(cfg['defense'], cfg['defense'])}. "
               "All tools are sandboxed: no real email, web request or file deletion.")
    chat, attack = st.tabs(["Chat", "Attack"])
    with chat:
        chat_tab(cfg)
    with attack:
        attack_tab(cfg)
    cfg["spend"].caption(cfg["backend"].tracker.summary(dry_run=cfg["dry_run"]))


main()
