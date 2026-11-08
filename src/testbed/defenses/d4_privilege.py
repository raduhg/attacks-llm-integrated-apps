"""D4 Privilege separation: least privilege plus simulated human-in-the-loop approval.

Two deterministic, rule-based mechanisms (no extra model call; the optional dual-LLM pattern is
intentionally out of scope for now):

  - Least privilege (tools): the sensitive tools send_email and delete_file are offered to the
    model only when the user's own message clearly asks for that action. A request with no such
    intent never even sees those tools, so an injected instruction cannot call them.

  - Simulated approval (before_tool_call): if a sensitive tool is called anyway, it is allowed
    only when its key argument is grounded in the user's own message - the recipient address for
    send_email, the path for delete_file. This simulates a human who would only approve sending
    to a recipient they themselves named. An injected attacker address is therefore denied.
"""

from __future__ import annotations

import re
from typing import Any

from testbed.defenses.base import Decision, Defense

SENSITIVE = {"send_email", "delete_file"}
# Verbs in the USER message that grant each sensitive tool.
_GRANTS = {
    "send_email": re.compile(r"\b(send|email|e-mail|write|reply|notify|forward)\b", re.IGNORECASE),
    "delete_file": re.compile(r"\b(delete|remove|erase|clear)\b", re.IGNORECASE),
}
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")


class D4Privilege(Defense):
    name = "D4"

    def tools(self, all_tools: list[dict[str, Any]], user_msg: str) -> list[dict[str, Any]]:
        granted = {t for t, rx in _GRANTS.items() if rx.search(user_msg)}
        return [t for t in all_tools if t["name"] not in SENSITIVE or t["name"] in granted]

    def before_tool_call(self, name: str, args: dict[str, Any], user_msg: str) -> Decision:
        if name == "send_email":
            recipients = set(_EMAIL.findall(user_msg.lower()))
            if str(args.get("to", "")).lower() not in recipients:
                return Decision.block("recipient not named by user", text="[blocked: recipient not approved by the user]")
        if name == "delete_file":
            path = str(args.get("path", "")).lower()
            if not path or path not in user_msg.lower():
                return Decision.block("path not named by user", text="[blocked: deletion not approved by the user]")
        return Decision.allow()
