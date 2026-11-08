"""Shared detection patterns for the heuristic defenses (D1 input filtering, D5 output validation).

Two independent families:
  - INJECTION_PATTERNS: phrasings typical of prompt-injection instructions. Used by D1 to flag
    untrusted text (user input and tool results).
  - The secret / URL / recipient checks used by D5. These are GENERIC formats (IBAN, phone, API
    key shape, external URL), NOT the exact planted secrets: a defense that knew the exact
    secrets would share the success checkers' list and score a circular, automatic 100%. Generic
    patterns are what a real data-loss-prevention filter would use.

All patterns are deliberately simple and documented, since the thesis must explain them. They
are heuristics: expect both false positives and false negatives, which the evaluation measures.
"""

from __future__ import annotations

import re

# --- D1: injection-instruction heuristics -----------------------------------
# Each entry is (label, compiled regex). The label is logged so results can be broken down.
_INJECTION_SOURCES: list[tuple[str, str]] = [
    ("ignore_previous", r"ignore\s+(all\s+)?(the\s+)?(previous|prior|above|earlier)\s+(instruction|prompt|direction|command)"),
    ("disregard", r"disregard\s+(all\s+)?(previous|prior|above|your)\s+\w+"),
    ("new_instructions", r"\b(new|updated|revised)\s+(instruction|task|directive|system\s+prompt)s?\b"),
    ("system_override", r"\b(system\s*:|<\s*system\s*>|\[\s*system\s*\])"),
    ("role_reassignment", r"you\s+are\s+now\s+(a|an|the)\b|from\s+now\s+on\s+you"),
    ("reveal_prompt", r"(reveal|repeat|print|show|output|tell\s+me)\s+(your|the)\s+(system\s+prompt|instruction|rules|config)"),
    ("exfil_send", r"\b(send|email|forward|post|upload)\b.{0,40}\b(to|at)\b.{0,40}@"),
    ("urgent_override", r"\b(important|urgent|critical)\b.{0,30}\b(instruction|must|immediately)\b"),
    ("do_not_tell", r"do\s+not\s+(tell|inform|mention\s+to|alert)\s+the\s+user"),
]
INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (label, re.compile(src, re.IGNORECASE | re.DOTALL)) for label, src in _INJECTION_SOURCES
]


def injection_labels(text: str) -> list[str]:
    """Labels of every injection heuristic that fires on `text` (empty = looks benign)."""
    return [label for label, rx in INJECTION_PATTERNS if rx.search(text)]


# --- D5: generic sensitive-data formats -------------------------------------
# Generic, not the specific planted values. See the module docstring for why.
_SECRET_SOURCES: list[tuple[str, str]] = [
    ("iban", r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b"),
    ("api_key", r"\b(sk|pk|key|token|api)[-_][A-Za-z0-9-]{8,}\b"),
    ("phone", r"(?<!\d)(\+?\d[\d ()-]{7,}\d)(?!\d)"),
    ("email", r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
]
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (label, re.compile(src)) for label, src in _SECRET_SOURCES
]

# A URL whose host is anything other than the internal acme.example domain.
EXTERNAL_URL = re.compile(r"https?://(?!(?:[\w-]+\.)*acme\.example\b)[\w.-]+(?:/\S*)?", re.IGNORECASE)


def secret_labels(text: str) -> list[str]:
    """Labels of every generic-secret pattern that matches in `text`."""
    return [label for label, rx in SECRET_PATTERNS if rx.search(text)]


def redact(text: str) -> tuple[str, list[str]]:
    """Replace generic secrets and external URLs with placeholders. Returns (text, labels hit)."""
    hits: list[str] = []
    for label, rx in SECRET_PATTERNS:
        if rx.search(text):
            hits.append(label)
            text = rx.sub(f"[REDACTED:{label}]", text)
    if EXTERNAL_URL.search(text):
        hits.append("external_url")
        text = EXTERNAL_URL.sub("[REDACTED:url]", text)
    return text, hits
