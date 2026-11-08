"""Defenses D0-D6 with a common interface, built by name for experiments.

Names (what an experiment's `defenses:` list contains):
  D0      baseline, no defense
  D1      input filtering, regex only
  D1-LLM  input filtering, regex + LLM detector (extra cost tracked separately)
  D2      system prompt hardening + sandwich
  D3      spotlighting (delimiting)
  D3-dm   spotlighting with datamarking
  D4      privilege separation (least privilege + simulated approval)
  D5      output validation (generic patterns)
  D6      defense in depth: D1 + D2 + D3 + D4 + D5
"""

from __future__ import annotations

from testbed.defenses.base import Decision, Defense, DefenseStack
from testbed.defenses.d1_input_filter import D1InputFilter
from testbed.defenses.d2_hardening import D2Hardening
from testbed.defenses.d3_spotlighting import D3Spotlighting
from testbed.defenses.d4_privilege import D4Privilege
from testbed.defenses.d5_output import D5OutputValidation

__all__ = ["Decision", "Defense", "DefenseStack", "build_defense", "KNOWN_DEFENSES"]


def _d6() -> DefenseStack:
    return DefenseStack(
        [D1InputFilter(), D2Hardening(), D3Spotlighting(), D4Privilege(), D5OutputValidation()], name="D6"
    )


# name -> zero-arg factory, so each run gets a fresh instance (D3's random tag, detector backend).
_FACTORIES: dict[str, callable] = {
    "D0": Defense,
    "D1": D1InputFilter,
    "D1-LLM": lambda: D1InputFilter(use_llm=True),
    "D2": D2Hardening,
    "D3": D3Spotlighting,
    "D3-dm": lambda: D3Spotlighting(datamark=True),
    "D4": D4Privilege,
    "D5": D5OutputValidation,
    "D6": _d6,
}
KNOWN_DEFENSES = frozenset(_FACTORIES)


def build_defense(name: str) -> Defense:
    """Instantiate a defense by name (see module docstring for the list)."""
    if name not in _FACTORIES:
        raise KeyError(f"Unknown defense {name!r}; known: {sorted(KNOWN_DEFENSES)}")
    return _FACTORIES[name]()
