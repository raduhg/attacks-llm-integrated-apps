"""Common defense interface and the stack that combines several defenses.

A defense overrides only the hooks it needs; every hook has a no-op default, so D0 (baseline)
is just the base class. The hooks match the four defense points marked in the agent loop:

    system_prompt(base)                  -> str      change the system prompt (once per run)
    tools(all_tools, user_msg)           -> tools    restrict the tool list (once per run)
    on_user_input(text)                  -> Decision allow / block the user's turn
    before_tool_call(name, args, user)   -> Decision allow / deny a tool call
    on_tool_result(name, output)         -> str      rewrite / wrap / drop a tool result
    on_output(text)                      -> Decision allow / redact / block the final answer
    sandwich_reminder()                  -> str|None text appended after each tool-result batch

Every non-trivial decision is logged by the assistant as a `defense_decision` event, so each
run's trace shows exactly what the defense did. A defense may issue its own API calls (e.g. the
D1 LLM detector) through `set_detector_backend`; those calls' cost is tracked separately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from testbed.llm.base import LLMBackend


@dataclass
class Decision:
    """Result of an allow/deny/redact hook.

    allowed=False  -> the action is blocked (user turn refused, tool call denied, output withheld)
    text           -> replacement text to use instead (a redacted answer, a refusal message)
    reason         -> short machine-readable reason, logged to the trace
    """

    allowed: bool = True
    text: str | None = None  # replacement, when the original must not be used as-is
    reason: str = ""

    @classmethod
    def allow(cls) -> Decision:
        return cls(allowed=True)

    @classmethod
    def block(cls, reason: str, text: str | None = None) -> Decision:
        return cls(allowed=False, reason=reason, text=text)


class Defense:
    """Base class and D0 baseline: every hook is a no-op."""

    name = "D0"

    def attach(self, backend: LLMBackend, log: Any) -> None:
        """Give the defense a backend for its own API calls and a `log(event, **data)` callable
        to record them to the trace. Used by D1-LLM; a no-op for defenses that make no calls."""

    def system_prompt(self, base: str) -> str:
        return base

    def tools(self, all_tools: list[dict[str, Any]], user_msg: str) -> list[dict[str, Any]]:
        return all_tools

    def on_user_input(self, text: str) -> Decision:
        return Decision.allow()

    def before_tool_call(self, name: str, args: dict[str, Any], user_msg: str) -> Decision:
        return Decision.allow()

    def on_tool_result(self, name: str, output: str) -> str:
        return output

    def on_output(self, text: str) -> Decision:
        return Decision.allow()

    def sandwich_reminder(self) -> str | None:
        return None


@dataclass
class DefenseStack(Defense):
    """Runs several defenses in order. Combining them is how D6 (defense in depth) is built.

    Composition rules (first decisive result wins, so adding a defense can only tighten things):
      - system_prompt: each defense transforms the previous defense's output in turn.
      - tools: intersected (each defense may further restrict).
      - on_user_input / before_tool_call: the first defense that blocks wins.
      - on_tool_result: chained (each sees the previous one's rewrite).
      - on_output: the first block wins; redactions chain.
      - sandwich_reminder: the reminders of all defenses, joined.
    """

    defenses: list[Defense] = field(default_factory=list)
    name: str = "stack"

    def attach(self, backend: LLMBackend, log: Any) -> None:
        for d in self.defenses:
            d.attach(backend, log)

    def system_prompt(self, base: str) -> str:
        for d in self.defenses:
            base = d.system_prompt(base)
        return base

    def tools(self, all_tools: list[dict[str, Any]], user_msg: str) -> list[dict[str, Any]]:
        for d in self.defenses:
            all_tools = d.tools(all_tools, user_msg)
        return all_tools

    def on_user_input(self, text: str) -> Decision:
        for d in self.defenses:
            if not (decision := d.on_user_input(text)).allowed:
                return decision
        return Decision.allow()

    def before_tool_call(self, name: str, args: dict[str, Any], user_msg: str) -> Decision:
        for d in self.defenses:
            if not (decision := d.before_tool_call(name, args, user_msg)).allowed:
                return decision
        return Decision.allow()

    def on_tool_result(self, name: str, output: str) -> str:
        for d in self.defenses:
            output = d.on_tool_result(name, output)
        return output

    def on_output(self, text: str) -> Decision:
        result = Decision.allow()
        for d in self.defenses:
            decision = d.on_output(text if result.text is None else result.text)
            if not decision.allowed:
                return decision
            if decision.text is not None:
                result = decision  # a redaction; keep chaining from the redacted text
        return result

    def sandwich_reminder(self) -> str | None:
        parts = [r for d in self.defenses if (r := d.sandwich_reminder())]
        return "\n".join(parts) if parts else None
