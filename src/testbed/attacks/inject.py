"""Per-attack runtime injection.

Each attack gets a fresh Sandbox (and, for documents, a copy of the index) with its payload
placed at its injection point. The clean data on disk and the shared index are never changed,
so attacks are isolated: a result can always be traced to exactly one payload.
"""

from __future__ import annotations

from typing import Any

from testbed.app.rag import DocumentIndex
from testbed.app.tools import Sandbox
from testbed.attacks.schema import Attack


def prepare(attack: Attack, index: DocumentIndex) -> tuple[Sandbox, list[dict[str, Any]]]:
    """Return the sandbox for this attack and the opening conversation."""
    t = attack.target
    if attack.injection_point == "document":
        sandbox = Sandbox(index.with_document(t.doc, attack.payload))  # type: ignore[arg-type]
    else:
        sandbox = Sandbox(index)
    if attack.injection_point == "email":
        sandbox.emails[t.email_id] = {  # type: ignore[index]
            "id": t.email_id, "from": t.sender, "to": "assistant-user@acme.example",
            "date": "2026-11-07", "subject": t.subject, "body": attack.payload,
        }
    elif attack.injection_point == "web_page":
        sandbox.pages[t.url] = attack.payload  # type: ignore[index]
    elif attack.injection_point == "tool_output":
        sandbox.output_suffix[t.tool] = attack.payload  # type: ignore[index]

    prompt = attack.payload if attack.injection_point == "user_message" else attack.user_prompt
    return sandbox, [{"role": "user", "content": prompt}]
