"""LLM backends, response cache and cost tracking."""

from __future__ import annotations

from dotenv import load_dotenv

from testbed.config import CACHE_DIR, load_models
from testbed.llm.anthropic_backend import AnthropicBackend
from testbed.llm.base import LLMBackend, LLMResponse, Usage
from testbed.llm.cache import ResponseCache
from testbed.llm.cost import BudgetExceeded, CostTracker

__all__ = [
    "AnthropicBackend",
    "BudgetExceeded",
    "CostTracker",
    "LLMBackend",
    "LLMResponse",
    "ResponseCache",
    "Usage",
    "make_backend",
]


def make_backend(
    model_key: str | None = None,
    *,
    use_cache: bool = True,
    dry_run: bool = False,
    budget_usd: float | None = None,
) -> AnthropicBackend:
    """Build a backend from config/models.yaml. Reads ANTHROPIC_API_KEY from .env if present."""
    load_dotenv()
    models = load_models()
    key = model_key or models.default
    if key not in models.models:
        raise KeyError(f"Unknown model '{key}'. Known: {sorted(models.models)}")
    return AnthropicBackend(
        models.models[key],
        cache=ResponseCache(CACHE_DIR) if use_cache else None,
        tracker=CostTracker(budget_usd=budget_usd),
        dry_run=dry_run,
        max_retries=models.max_retries,
    )
