#!/usr/bin/env python3
"""Tests for MiniMax OpenAI-compatible streaming behavior."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

TEST_FILE = Path(__file__).resolve()
SRC_DIR = TEST_FILE.parents[2]

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agent_core.api.adapter import APIProvider, ModelConfig
from agent_core.api.adapters.minimax import MiniMaxAdapter
from agent_core.api.client import ChatAgent
from agent_core.api.message import Message, MessageRole
from agent_core.api.types import ChatCompletionRequest
from agent_core.models import get_model_catalog


class FakeStreamingResponse:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = payloads

    def __enter__(self) -> "FakeStreamingResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    def iter_lines(self):
        for payload in self.payloads:
            yield f"data: {json.dumps(payload)}".encode("utf-8")
        yield b"data: [DONE]"


class MiniMaxStreamingTests(unittest.TestCase):
    def test_build_request_uses_minimax_completion_token_field(self) -> None:
        adapter = MiniMaxAdapter()
        config = ModelConfig(name="MiniMax-M2.5", provider=APIProvider.MINIMAX, supports_thinking=True)
        request = ChatCompletionRequest(
            model="MiniMax-M2.5",
            messages=[Message(role=MessageRole.USER, content="hi")],
            max_tokens=123,
            stream=True,
            reasoning_split=True,
        )

        data = adapter.build_request(request, config)

        self.assertNotIn("max_tokens", data)
        self.assertEqual(data["max_completion_tokens"], 123)
        self.assertTrue(data["stream"])
        self.assertTrue(data["reasoning_split"])

    def test_build_request_does_not_force_reasoning_split_for_sync_calls(self) -> None:
        adapter = MiniMaxAdapter()
        config = ModelConfig(name="MiniMax-M2.5", provider=APIProvider.MINIMAX, supports_thinking=True)
        request = ChatCompletionRequest(
            model="MiniMax-M2.5",
            messages=[Message(role=MessageRole.USER, content="hi")],
            stream=False,
            reasoning_split=False,
        )

        data = adapter.build_request(request, config)

        self.assertNotIn("reasoning_split", data)

    def test_parse_response_reads_nested_reasoning_usage(self) -> None:
        response = MiniMaxAdapter().parse_response(
            {
                "id": "chatcmpl-1",
                "model": "MiniMax-M2.5",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 5,
                    "completion_tokens_details": {"reasoning_tokens": 2},
                },
            }
        )

        self.assertEqual(response.usage.reasoning_tokens, 2)
        self.assertEqual(response.usage.total_tokens, 10)

    def test_stream_chat_converts_minimax_cumulative_content_to_deltas(self) -> None:
        config = ModelConfig(
            name="MiniMax-M2.5",
            provider=APIProvider.MINIMAX,
            api_key="test-key",
            base_url="https://example.test/v1",
            supports_thinking=True,
        )
        agent = ChatAgent(config=config)
        payloads = [
            {"choices": [{"delta": {"content": "你"}, "finish_reason": None}]},
            {"choices": [{"delta": {"content": "你好"}, "finish_reason": None}]},
            {"choices": [{"delta": {"content": "你好。"}, "finish_reason": "stop"}]},
        ]

        captured_request: dict = {}

        def fake_post(url, headers, json, stream, timeout):
            captured_request.update(json)
            return FakeStreamingResponse(payloads)

        with patch("agent_core.api.client.requests.post", side_effect=fake_post):
            chunks = list(agent.stream_chat([Message(role=MessageRole.USER, content="hi")], max_tokens=50))

        self.assertEqual([chunk.delta for chunk in chunks], ["你", "好", "。"])
        self.assertEqual(captured_request["max_completion_tokens"], 50)
        self.assertNotIn("max_tokens", captured_request)

    def test_minimax_catalog_uses_chat_completion_output_limit(self) -> None:
        catalog = get_model_catalog("minimax")
        self.assertIsNotNone(catalog)

        model = catalog.find_model("MiniMax-M2.5")

        self.assertIsNotNone(model)
        self.assertEqual(model.max_tokens, 2048)


if __name__ == "__main__":
    unittest.main()
