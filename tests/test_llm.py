"""Tests for the LLM layer. The API is always mocked: no test makes a paid call."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import anthropic
import pytest

from testbed.config import ModelConfig, Prices, load_models
from testbed.llm import AnthropicBackend, BudgetExceeded, CostTracker, ResponseCache, Usage
from testbed.llm.cache import cache_key
from testbed.llm.cost import cost_usd

PRICES = Prices(input=0.10, output=0.50, cache_read=0.01, cache_write=0.125)
MODEL = ModelConfig(id="claude-haiku-5-5", max_tokens=1000, effort="medium", price_per_mtok=PRICES)
MSGS = [{"role": "user", "content": "hi"}]


class FakeMessages:
    """Stands in for `client.messages`; records every request."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create(self, **params: Any) -> anthropic.types.Message:
        self.calls.append(params)
        return anthropic.types.Message.model_validate(
            {
                "id": f"msg_{len(self.calls)}",
                "type": "message",
                "role": "assistant",
                "model": params["model"],
                "content": [
                    {"type": "thinking", "thinking": "", "signature": "sig"},
                    {"type": "text", "text": f"reply {len(self.calls)}"},
                ],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1000, "output_tokens": 2000},
            }
        )


class FakeClient:
    def __init__(self) -> None:
        self.messages = FakeMessages()


def backend(tmp_path: Path, **kw: Any) -> tuple[AnthropicBackend, FakeClient]:
    client = FakeClient()
    return AnthropicBackend(MODEL, cache=ResponseCache(tmp_path), client=client, **kw), client


# --- config -----------------------------------------------------------------


def test_models_yaml_is_valid() -> None:
    models = load_models()
    assert models.default in models.models
    assert models.models["haiku"].id == "claude-haiku-5-5"


# --- cost -------------------------------------------------------------------


def test_cost_formula() -> None:
    usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000, cache_read_tokens=1_000_000, cache_write_tokens=1_000_000)
    assert cost_usd(usage, PRICES) == pytest.approx(0.10 + 0.50 + 0.01 + 0.125)


def test_budget_stops_before_next_paid_call(tmp_path: Path) -> None:
    b, client = backend(tmp_path, tracker=CostTracker(budget_usd=0.0011))
    b.chat(MSGS)  # costs 1000*0.10/1e6 + 2000*0.50/1e6 = $0.0011
    with pytest.raises(BudgetExceeded):
        b.chat([{"role": "user", "content": "another"}])
    assert len(client.messages.calls) == 1


def test_cache_hits_are_free_even_over_budget(tmp_path: Path) -> None:
    b, _ = backend(tmp_path, tracker=CostTracker(budget_usd=0.0011))
    b.chat(MSGS)
    r = b.chat(MSGS)  # same request: cache hit, allowed although budget is used up
    assert r.cached
    assert b.tracker.paid_calls == 1 and b.tracker.cached_calls == 1


# --- cache ------------------------------------------------------------------


def test_cache_key_depends_on_repetition() -> None:
    params = {"model": "m", "messages": MSGS}
    assert cache_key(params, 0) == cache_key(dict(params), 0)
    assert cache_key(params, 0) != cache_key(params, 1)


def test_repeated_call_is_served_from_cache(tmp_path: Path) -> None:
    b, client = backend(tmp_path)
    first = b.chat(MSGS)
    second = b.chat(MSGS)
    assert len(client.messages.calls) == 1
    assert not first.cached and second.cached
    assert second.text == first.text == "reply 1"
    assert second.cost_usd == first.cost_usd  # original cost is kept for analysis


def test_each_repetition_is_a_real_call(tmp_path: Path) -> None:
    b, client = backend(tmp_path)
    texts = {b.chat(MSGS, repetition=i).text for i in range(3)}
    assert len(client.messages.calls) == 3
    assert texts == {"reply 1", "reply 2", "reply 3"}


def test_cache_survives_a_new_backend(tmp_path: Path) -> None:
    backend(tmp_path)[0].chat(MSGS)
    b2, client2 = backend(tmp_path)  # e.g. after a crash and restart
    assert b2.chat(MSGS).cached
    assert client2.messages.calls == []


# --- request shape ----------------------------------------------------------


def test_request_params(tmp_path: Path) -> None:
    b, client = backend(tmp_path)
    tools = [{"name": "t", "description": "d", "input_schema": {"type": "object", "properties": {}}}]
    b.chat(MSGS, tools, system="sys")
    sent = client.messages.calls[0]
    assert sent["system"] == "sys" and sent["tools"] == tools
    assert sent["output_config"] == {"effort": "medium"}
    for p in ("temperature", "top_p", "top_k"):  # Haiku 5.5 returns 400 on non-default sampling params
        assert p not in sent


def test_no_tools_or_system_omits_the_keys(tmp_path: Path) -> None:
    b, client = backend(tmp_path)
    b.chat(MSGS)
    assert "tools" not in client.messages.calls[0] and "system" not in client.messages.calls[0]


def test_thinking_blocks_are_kept_for_replay(tmp_path: Path) -> None:
    b, _ = backend(tmp_path)
    r = b.chat(MSGS)
    assert r.content[0] == {"type": "thinking", "thinking": "", "signature": "sig"}
    assert r.text == "reply 1"


# --- dry run ----------------------------------------------------------------


def test_dry_run_never_calls_the_api(tmp_path: Path) -> None:
    b, client = backend(tmp_path, dry_run=True)
    r = b.chat(MSGS)
    assert client.messages.calls == []
    assert r.dry_run and r.cost_usd > 0
    assert b.tracker.paid_calls == 1  # counted as a planned call
    assert list(tmp_path.iterdir()) == []  # estimates are never cached


def test_dry_run_does_not_need_an_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    b = AnthropicBackend(MODEL, dry_run=True)  # no client injected
    assert b.chat(MSGS).dry_run
    assert b._client is None
