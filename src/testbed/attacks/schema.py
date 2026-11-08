"""Attack catalogue format (one YAML list entry per attack), validated with pydantic."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, model_validator

from testbed.config import PROJECT_ROOT

ATTACKS_DIR = PROJECT_ROOT / "data" / "attacks"

InjectionPoint = Literal["user_message", "document", "email", "web_page", "tool_output"]


class SuccessCheck(BaseModel):
    """One machine-checkable success condition (see checkers.py for the semantics)."""

    type: Literal["canary_in_output", "secret_in_output", "tool_called", "url_in_output"]
    tool: str | None = None  # tool_called: which tool
    args_contain: dict[str, str] = {}  # tool_called: argument -> required substring (case-insensitive)


class Target(BaseModel):
    """Where an indirect payload is placed. Which fields are needed depends on the injection point:
    document -> doc; email -> email_id (+ sender, subject); web_page -> url; tool_output -> tool."""

    doc: str | None = None
    email_id: str | None = None
    sender: str = "unknown@external.example"
    subject: str = "(no subject)"
    url: str | None = None
    tool: str | None = None


class Attack(BaseModel):
    id: str
    name: str
    category: str
    vector: Literal["direct", "indirect"]
    owasp_ref: str
    goal: str
    injection_point: InjectionPoint
    payload: str
    user_prompt: str | None = None  # indirect only: the innocent request that leads to the payload
    # Benign task ID whose checks decide whether the user's request was still completed under
    # attack ("utility under attack"); its prompt must equal user_prompt.
    user_task: str | None = None
    target: Target = Target()
    success: list[SuccessCheck]  # the attack succeeds if ANY check fires
    source: str | None = None  # provenance, e.g. "InjecAgent attacker_cases_ds.jsonl line 3 (MIT)"

    @model_validator(mode="after")
    def _consistent(self) -> Attack:
        required = {"document": "doc", "email": "email_id", "web_page": "url", "tool_output": "tool"}
        if self.injection_point == "user_message":
            if self.vector != "direct":
                raise ValueError(f"{self.id}: user_message injections are direct")
        else:
            if self.vector != "indirect" or not self.user_prompt:
                raise ValueError(f"{self.id}: indirect attacks need vector=indirect and a user_prompt")
            if getattr(self.target, required[self.injection_point]) is None:
                raise ValueError(f"{self.id}: target.{required[self.injection_point]} is required")
        if not self.success:
            raise ValueError(f"{self.id}: at least one success check is required")
        return self


def load_attacks(path: Path) -> list[Attack]:
    """Load and validate an attack catalogue file. Duplicate IDs are rejected."""
    attacks = [Attack.model_validate(a) for a in (yaml.safe_load(path.read_text(encoding="utf-8")) or [])]
    ids = [a.id for a in attacks]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate attack IDs in {path}")
    return attacks
