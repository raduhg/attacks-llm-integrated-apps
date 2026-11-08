"""Anthropic Messages API backend with response cache, cost tracking and dry-run mode.

Call flow for `chat()`:
  1. Build the exact request parameters (these are also what the cache key hashes).
  2. Cache hit  -> return the stored response; no money spent.
  3. Dry run    -> return a placeholder with estimated tokens/cost; the API is never called.
  4. Otherwise  -> check the budget, call the API (the SDK retries 429/529/5xx with
                   exponential backoff), price the call, store it in the cache.

Sampling parameters (temperature, top_p, top_k) are deliberately never sent: Claude Haiku 5.5
rejects non-default values, so all runs use the API default temperature of 1.0.
"""

from __future__ import annotations

import json
import time
from typing import Any

import anthropic

from testbed.config import ModelConfig
from testbed.llm.base import LLMResponse, Usage
from testbed.llm.cache import ResponseCache, cache_key
from testbed.llm.cost import CostTracker, cost_usd

CHARS_PER_TOKEN = 4  # rough heuristic, used only for dry-run estimates


class AnthropicBackend:
    """`LLMBackend` implementation for the Anthropic API."""

    def __init__(
        self,
        model: ModelConfig,
        *,
        cache: ResponseCache | None = None,
        tracker: CostTracker | None = None,
        dry_run: bool = False,
        max_retries: int = 5,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.cache = cache
        self.tracker = tracker or CostTracker()
        self.dry_run = dry_run
        self.max_retries = max_retries
        self._client = client  # injected in tests; created lazily otherwise

    @property
    def client(self) -> Any:
        """The SDK client, created on first real call (dry runs never need an API key)."""
        if self._client is None:
            self._client = anthropic.Anthropic(max_retries=self.max_retries)
        return self._client

    def build_params(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        system: str | None,
    ) -> dict[str, Any]:
        """The exact keyword arguments sent to `messages.create`."""
        params: dict[str, Any] = {
            "model": self.model.id,
            "max_tokens": self.model.max_tokens,
            "messages": messages,
        }
        if system:
            params["system"] = system
        if tools:
            params["tools"] = tools
        if self.model.effort:
            params["output_config"] = {"effort": self.model.effort}
        if self.model.thinking:
            params["thinking"] = self.model.thinking
        return params

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        system: str | None = None,
        repetition: int = 0,
    ) -> LLMResponse:
        """Send one request (see the module docstring for the order of checks)."""
        params = self.build_params(messages, tools, system)
        key = cache_key(params, repetition)

        if self.cache is not None and (hit := self.cache.get(key)) is not None:
            response = LLMResponse.model_validate(hit).model_copy(update={"cached": True})
        elif self.dry_run:
            response = self._estimate(params)
        else:
            self.tracker.check_budget()
            response = self._call(params)
            if self.cache is not None:
                self.cache.put(key, params, repetition, response.model_dump(mode="json"))

        self.tracker.record(response)
        return response

    def _call(self, params: dict[str, Any]) -> LLMResponse:
        """One real API call."""
        start = time.perf_counter()
        message = self.client.messages.create(**params)
        latency = time.perf_counter() - start
        u = message.usage
        usage = Usage(
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            cache_read_tokens=u.cache_read_input_tokens or 0,
            cache_write_tokens=u.cache_creation_input_tokens or 0,
        )
        return LLMResponse(
            model=message.model,
            # exclude_unset keeps only fields the API returned, so blocks replay unchanged
            content=[b.model_dump(mode="json", exclude_unset=True) for b in message.content],
            stop_reason=message.stop_reason,
            usage=usage,
            cost_usd=cost_usd(usage, self.model.price_per_mtok),
            latency_s=latency,
        )

    def _estimate(self, params: dict[str, Any]) -> LLMResponse:
        """Placeholder response with estimated usage, for dry-run mode."""
        usage = Usage(
            input_tokens=len(json.dumps(params, ensure_ascii=False)) // CHARS_PER_TOKEN,
            output_tokens=self.model.dry_run_output_tokens,
        )
        return LLMResponse(
            model=self.model.id,
            content=[{"type": "text", "text": "[dry-run: no API call made]"}],
            stop_reason="end_turn",
            usage=usage,
            cost_usd=cost_usd(usage, self.model.price_per_mtok),
            latency_s=0.0,
            dry_run=True,
        )
