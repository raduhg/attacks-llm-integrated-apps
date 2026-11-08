"""Token/cost accounting and the per-experiment budget limit."""

from __future__ import annotations

from dataclasses import dataclass

from testbed.config import Prices
from testbed.llm.base import LLMResponse, Usage


class BudgetExceeded(RuntimeError):
    """Raised before a paid call once the budget is used up, so a run stops cleanly."""


def cost_usd(usage: Usage, prices: Prices) -> float:
    """Price one call from its token usage."""
    return (
        usage.input_tokens * prices.input
        + usage.output_tokens * prices.output
        + usage.cache_read_tokens * prices.cache_read
        + usage.cache_write_tokens * prices.cache_write
    ) / 1_000_000


@dataclass
class CostTracker:
    """Running totals for one run.

    The budget is checked before every paid call; a run can overshoot by at most the cost
    of the single call that crosses the limit. Cache hits are free and never count.
    """

    budget_usd: float | None = None
    spent_usd: float = 0.0  # real money (or, in dry-run mode, estimated money)
    paid_calls: int = 0
    cached_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def check_budget(self) -> None:
        """Raise BudgetExceeded if no budget is left for another paid call."""
        if self.budget_usd is not None and self.spent_usd >= self.budget_usd:
            raise BudgetExceeded(f"Budget of ${self.budget_usd:.4f} reached (spent ${self.spent_usd:.4f}).")

    def record(self, response: LLMResponse) -> None:
        """Add one response to the totals."""
        if response.cached:
            self.cached_calls += 1
            return
        self.paid_calls += 1
        self.spent_usd += response.cost_usd
        self.input_tokens += response.usage.input_tokens
        self.output_tokens += response.usage.output_tokens

    def summary(self, dry_run: bool = False) -> str:
        """One-line human-readable summary."""
        label = "planned API calls" if dry_run else "API calls"
        money = "estimated cost" if dry_run else "spent"
        return (
            f"{self.paid_calls} {label}, {self.cached_calls} cache hits, "
            f"{self.input_tokens} in / {self.output_tokens} out tokens, {money} ${self.spent_usd:.6f}"
        )
