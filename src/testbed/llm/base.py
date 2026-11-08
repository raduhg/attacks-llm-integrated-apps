"""The common LLM backend interface.

Every backend exposes `chat(messages, tools) -> LLMResponse`. Messages and tools use the
Anthropic Messages API shape (plain dicts): this project has a single provider, so a
provider-neutral translation layer would be code with no user.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel


class Usage(BaseModel):
    """Token counts reported by the API for one call."""

    input_tokens: int = 0
    output_tokens: int = 0  # includes thinking tokens
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class LLMResponse(BaseModel):
    """Result of one model call.

    `content` holds the raw content blocks (text, thinking, tool_use) exactly as returned,
    so they can be appended to the conversation unchanged on the next turn.
    """

    model: str
    content: list[dict[str, Any]]
    stop_reason: str | None
    usage: Usage
    cost_usd: float  # cost of the original API call (also reported for cache hits)
    latency_s: float  # latency of the original API call
    cached: bool = False  # served from the on-disk cache, no money spent now
    dry_run: bool = False  # no call made; usage and cost are estimates

    @property
    def text(self) -> str:
        """Concatenated text blocks (thinking and tool calls excluded)."""
        return "".join(b.get("text", "") for b in self.content if b.get("type") == "text")

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        """The tool_use blocks the model emitted."""
        return [b for b in self.content if b.get("type") == "tool_use"]


class LLMBackend(Protocol):
    """Interface every model backend implements."""

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        system: str | None = None,
        repetition: int = 0,
    ) -> LLMResponse:
        """Send one request. `repetition` separates the N repeated runs in the cache."""
        ...
