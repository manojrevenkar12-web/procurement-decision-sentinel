"""Readers turn a prompt into a reply. The sentinel never trusts the reply's shape.

`AnthropicReader` calls Claude through the Messages API with a forced tool and a cached system prompt.
`OpenAICompatibleReader` calls any OpenAI-compatible endpoint with a strict JSON schema. Both are plain HTTP over
httpx so tests can replace the transport.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from ..domain import Prompt, Reply, SignalRead
from .prompt import tool_schema


class Reader(Protocol):
    def read(self, prompt: Prompt) -> Reply: ...


def _repair_note(prompt: Prompt) -> str:
    if prompt.attempt == 0 or not prompt.previous_error:
        return ""
    return "\n\nYour previous reply did not match the schema. Error:\n" + prompt.previous_error[:800] + "\nReply again through the tool."


@dataclass
class AnthropicReader:
    api_key: str
    model: str
    max_tokens: int = 800
    client: httpx.Client | None = None
    url: str = "https://api.anthropic.com/v1/messages"

    def read(self, prompt: Prompt) -> Reply:
        client = self.client or httpx.Client(timeout=60)
        body = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": [{"type": "text", "text": prompt.system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": prompt.user + _repair_note(prompt)}],
            "tools": [tool_schema()],
            "tool_choice": {"type": "tool", "name": "submit_signal"},
        }
        start = time.monotonic()
        r = client.post(self.url, json=body, headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"})
        r.raise_for_status()
        data = r.json()
        blocks = [b for b in data.get("content", []) if b.get("type") == "tool_use"]
        text = json.dumps(blocks[0]["input"]) if blocks else ""
        u = data.get("usage", {})
        cached = int(u.get("cache_read_input_tokens", 0))
        return Reply(text, int(u.get("input_tokens", 0)) + cached, cached, int(u.get("output_tokens", 0)), time.monotonic() - start)


@dataclass
class OpenAICompatibleReader:
    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1"
    client: httpx.Client | None = None

    def read(self, prompt: Prompt) -> Reply:
        client = self.client or httpx.Client(timeout=60)
        schema: dict[str, Any] = SignalRead.model_json_schema()
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": prompt.system}, {"role": "user", "content": prompt.user + _repair_note(prompt)}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "signal", "schema": schema}},
        }
        start = time.monotonic()
        r = client.post(self.base_url.rstrip("/") + "/chat/completions", json=body, headers={"Authorization": f"Bearer {self.api_key}"})
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"].get("content") or ""
        u = data.get("usage", {})
        cached = int((u.get("prompt_tokens_details") or {}).get("cached_tokens", 0))
        return Reply(text, int(u.get("prompt_tokens", 0)), cached, int(u.get("completion_tokens", 0)), time.monotonic() - start)
