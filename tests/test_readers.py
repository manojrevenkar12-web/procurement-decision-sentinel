"""Readers speak the real wire formats; the transport is replaced in tests."""

from __future__ import annotations

import json

import httpx
from helpers import COPPER_BODY, COPPER_READ, msg

from sentinel.platform.prompt import build_prompt
from sentinel.platform.readers import AnthropicReader, OpenAICompatibleReader
from sentinel.platform.validate import read_signal


def test_anthropic_reader_forces_the_tool_and_caches_the_system_prompt() -> None:
    seen: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"content": [{"type": "tool_use", "name": "submit_signal", "input": COPPER_READ}], "usage": {"input_tokens": 120, "cache_read_input_tokens": 800, "output_tokens": 90}})

    r = AnthropicReader("k", "claude-test", client=httpx.Client(transport=httpx.MockTransport(handler)))
    res = read_signal(r, build_prompt(msg("M1", "Copper", COPPER_BODY)), 1)
    assert res.read is not None and res.read.commodity == "LME copper"
    assert seen["tool_choice"] == {"type": "tool", "name": "submit_signal"}
    assert seen["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "<untrusted" in seen["messages"][0]["content"]
    assert res.tokens_in == 920 and res.tokens_cached == 800


def test_openai_compatible_reader_asks_for_the_schema() -> None:
    seen: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(COPPER_READ)}}], "usage": {"prompt_tokens": 900, "completion_tokens": 80, "prompt_tokens_details": {"cached_tokens": 700}}})

    r = OpenAICompatibleReader("k", "open-model", base_url="http://local/v1", client=httpx.Client(transport=httpx.MockTransport(handler)))
    res = read_signal(r, build_prompt(msg("M1", "Copper", COPPER_BODY)), 1)
    assert res.read is not None and seen["response_format"]["type"] == "json_schema"
    assert res.tokens_cached == 700


def test_extra_fields_are_rejected_then_repaired() -> None:
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(json.loads(req.content))
        bad = {**COPPER_READ, "decision": "buy now"} if len(calls) == 1 else COPPER_READ
        return httpx.Response(200, json={"content": [{"type": "tool_use", "name": "submit_signal", "input": bad}], "usage": {}})

    r = AnthropicReader("k", "claude-test", client=httpx.Client(transport=httpx.MockTransport(handler)))
    res = read_signal(r, build_prompt(msg("M1", "Copper", COPPER_BODY)), 1)
    assert res.read is not None and res.attempts == 2 and "previous reply" in calls[1]["messages"][0]["content"]
