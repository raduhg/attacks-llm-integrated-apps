"""D5 Output validation: scan tool arguments and the final answer, redact or block.

Uses GENERIC patterns (testbed.defenses.patterns), not the exact planted secrets, so the score
is not circular with the success checkers. Two hooks:

  - before_tool_call: if a sensitive tool's arguments carry a generic secret or an external URL
    (e.g. an attacker trying to send PII out by email), the call is denied before it runs.
  - on_output: the final answer is scanned; generic secrets and external URLs are redacted in
    place. The answer is still shown, minus the sensitive spans.

This is the last line of defense: it catches leaks regardless of how the model was tricked.
"""

from __future__ import annotations

from typing import Any

from testbed.defenses.base import Decision, Defense
from testbed.defenses.d4_privilege import SENSITIVE
from testbed.defenses.patterns import EXTERNAL_URL, redact, secret_labels


class D5OutputValidation(Defense):
    name = "D5"

    def before_tool_call(self, name: str, args: dict[str, Any], user_msg: str) -> Decision:
        if name not in SENSITIVE:
            return Decision.allow()
        blob = " ".join(str(v) for v in args.values())
        hits = secret_labels(blob) + (["external_url"] if EXTERNAL_URL.search(blob) else [])
        # An email to an external recipient is the normal case; only block when a secret rides along.
        leaked = [h for h in hits if h != "email"]
        if leaked:
            return Decision.block("secret in tool args:" + ",".join(leaked), text="[blocked: sensitive data in tool call]")
        return Decision.allow()

    def on_output(self, text: str) -> Decision:
        redacted, hits = redact(text)
        if hits:
            return Decision(allowed=True, text=redacted, reason="redacted:" + ",".join(hits))
        return Decision.allow()
