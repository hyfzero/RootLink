#!/usr/bin/env python3
"""Tests for session-level streaming message events."""

from __future__ import annotations

import asyncio
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

TEST_FILE = Path(__file__).resolve()
SRC_DIR = TEST_FILE.parents[2]

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agent_core.api.message import ToolCall, ToolDefinition
from agent_core.api.types import StreamChunk
from agent_core.brain.tags import ReplyTag
from agent_core.session.manager import SessionManager
from agent_core.session.storage import DaySession


class FakeStorage:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def add_message(self, role: str, content: str) -> None:
        self.messages.append((role, content))

    def get_or_create_today(self) -> None:
        return None

    def archive_stale_current_sessions(self, today: str | None = None) -> list[DaySession]:
        return []

    def archive_session(self, session: DaySession) -> None:
        return None


class FakePromptBuilder:
    def build_system_prompt(self, emotion: str | None) -> str:
        return "system"

    def build_conversation_context(self, user_message: str) -> str:
        return f"context:{user_message}"


class FakeTagger:
    def __init__(self) -> None:
        self.generated: list[tuple[str, str]] = []

    def generate_and_save(self, message_id: str, content: str) -> ReplyTag:
        self.generated.append((message_id, content))
        return ReplyTag(message_id=message_id, emotion="neutral")


class FakeChatAgent:
    def __init__(
        self,
        chunks: list[str | StreamChunk],
        fallback: str = "fallback。",
        fail_stream: bool = False,
        chat_responses: list[object] | None = None,
        stream_turns: list[list[str | StreamChunk]] | None = None,
        chat_delay: float = 0.0,
    ) -> None:
        self.chunks = chunks
        self.fallback = fallback
        self.fail_stream = fail_stream
        self.chat_responses = list(chat_responses or [])
        self.chat_delay = chat_delay
        self.stream_turns = stream_turns
        self.stream_turn_index = 0
        self.stream_kwargs: list[dict] = []
        self.chat_kwargs: list[dict] = []
        self.chat_messages: list[list[object]] = []
        self.stream_messages: list[list[object]] = []

    def stream_chat(self, messages, **kwargs):
        self.stream_messages.append(list(messages))
        self.stream_kwargs.append(kwargs)
        if self.fail_stream:
            raise RuntimeError("stream unavailable")
        if self.stream_turns is None:
            chunks = self.chunks
        else:
            chunks = self.stream_turns[self.stream_turn_index]
            self.stream_turn_index += 1
        for chunk in chunks:
            yield chunk if isinstance(chunk, StreamChunk) else StreamChunk(delta=chunk)

    def chat(self, messages, stream: bool = False, **kwargs):
        if self.chat_delay:
            time.sleep(self.chat_delay)
        self.chat_messages.append(list(messages))
        self.chat_kwargs.append({"stream": stream, **kwargs})
        if self.chat_responses:
            return self.chat_responses.pop(0)
        return SimpleNamespace(content=self.fallback)


class TestSessionManager(SessionManager):
    @property
    def prompt_builder(self) -> FakePromptBuilder:
        return self.fake_prompt_builder

    def _check_and_handle_day_change_sync(self) -> None:
        return None

    def _sync_tokenizer_runtime(self) -> None:
        return None

    def _sync_history_message(self, role: str, content: str) -> None:
        return None

    def _sync_relationship_state(self, role: str, content: str) -> None:
        return None

    def _sync_personality_state(self, role: str, content: str, emotion: str | None = None) -> None:
        return None

    def _generate_message_id(self) -> str:
        return "assistant-1"


class FakeStaleStorage:
    def __init__(self, sessions: list[DaySession]) -> None:
        self.sessions = sessions
        self.archived_after_summary: list[DaySession] = []
        self.requested_today: str | None = None

    def archive_stale_current_sessions(self, today: str | None = None) -> list[DaySession]:
        self.requested_today = today
        return self.sessions

    def archive_session(self, session: DaySession) -> None:
        self.archived_after_summary.append(session)


class TestSummaryManager(SessionManager):
    def _generate_end_of_day_summary_sync(self, session: DaySession) -> None:
        session.summary_generated = True


def make_manager(
    chat_agent: FakeChatAgent,
    response_config: object | None = None,
    tools: dict | None = None,
    tool_definitions: list[ToolDefinition] | None = None,
    max_tool_turns: int = 10,
) -> TestSessionManager:
    manager = TestSessionManager.__new__(TestSessionManager)
    manager._storage = FakeStorage()
    manager.chat_agent = chat_agent
    manager.tagger = FakeTagger()
    manager.fake_prompt_builder = FakePromptBuilder()
    manager._current_brain_id = "test-brain"
    manager.tools = tools or {}
    manager.tool_definitions = tool_definitions
    manager.max_tool_turns = max_tool_turns
    manager.brain_registry = SimpleNamespace(
        current=lambda: SimpleNamespace(
            config=SimpleNamespace(response=response_config or SimpleNamespace())
        )
    )
    return manager


class SessionStreamingTests(unittest.TestCase):
    def test_send_message_stream_accumulates_and_saves_one_assistant_message(self) -> None:
        manager = make_manager(FakeChatAgent(["第一", "句。", "第二句！"]))

        events = list(manager.send_message_stream("hi"))

        self.assertEqual([event["type"] for event in events], ["delta", "delta", "delta", "done"])
        self.assertEqual(events[-1]["content"], "第一句。第二句！")
        self.assertEqual(manager.storage.messages, [("user", "hi"), ("assistant", "第一句。第二句！")])
        self.assertEqual(manager.tagger.generated, [("assistant-1", "第一句。第二句！")])

    def test_send_message_stream_falls_back_to_sync_reply_before_any_delta(self) -> None:
        manager = make_manager(FakeChatAgent([], fallback="兜底回复。", fail_stream=True))

        events = list(manager.send_message_stream("hi"))

        self.assertEqual([event["type"] for event in events], ["delta", "done"])
        self.assertEqual(events[0]["delta"], "兜底回复。")
        self.assertEqual(events[-1]["content"], "兜底回复。")
        self.assertEqual(manager.storage.messages, [("user", "hi"), ("assistant", "兜底回复。")])


    def test_send_message_stream_limits_reply_to_max_sentences(self) -> None:
        chat_agent = FakeChatAgent(["one. two. three."])
        manager = make_manager(
            chat_agent,
            response_config=SimpleNamespace(max_tokens=123, max_sentences=2),
        )

        events = list(manager.send_message_stream("hi"))

        self.assertEqual(chat_agent.stream_kwargs, [{"max_tokens": 123}])
        self.assertEqual([event["type"] for event in events], ["delta", "done"])
        self.assertEqual(events[0]["delta"], "one. two.")
        self.assertEqual(events[-1]["content"], "one. two.")
        self.assertEqual(manager.storage.messages, [("user", "hi"), ("assistant", "one. two.")])

    def test_send_message_sync_limits_reply_to_max_sentences(self) -> None:
        chat_agent = FakeChatAgent([], fallback="one. two. three.")
        manager = make_manager(
            chat_agent,
            response_config=SimpleNamespace(max_tokens=321, max_sentences=1),
        )

        response = manager.send_message_sync("hi")

        self.assertEqual(chat_agent.chat_kwargs, [{"stream": False, "max_tokens": 321}])
        self.assertEqual(response["content"], "one.")
        self.assertEqual(manager.storage.messages, [("user", "hi"), ("assistant", "one.")])

    def test_send_message_async_matches_sync_message_path(self) -> None:
        sync_manager = make_manager(FakeChatAgent([], fallback="same reply."))
        async_manager = make_manager(FakeChatAgent([], fallback="same reply."))

        sync_response = sync_manager.send_message_sync("hi", emotion="calm")
        async_response = asyncio.run(
            async_manager.send_message("hi", emotion="calm", stream=True)
        )

        self.assertEqual(async_response["content"], sync_response["content"])
        self.assertEqual(async_manager.storage.messages, sync_manager.storage.messages)
        self.assertEqual(async_manager.chat_agent.chat_kwargs, [{"stream": False}])

    def test_send_message_async_does_not_call_legacy_call_api_helper(self) -> None:
        manager = make_manager(FakeChatAgent([], fallback="async final."))

        async def fail_call_api(*args, **kwargs):
            raise AssertionError("_call_api should not be used")

        manager._call_api = fail_call_api  # type: ignore[attr-defined]

        response = asyncio.run(manager.send_message("hi"))

        self.assertEqual(response["content"], "async final.")
        self.assertEqual(manager.storage.messages, [("user", "hi"), ("assistant", "async final.")])

    def test_send_message_async_does_not_block_event_loop(self) -> None:
        manager = make_manager(FakeChatAgent([], fallback="slow final.", chat_delay=0.2))

        async def run_message_and_sleep() -> tuple[dict, float]:
            task = asyncio.create_task(manager.send_message("hi"))
            started = time.perf_counter()
            await asyncio.sleep(0.02)
            sleep_elapsed = time.perf_counter() - started
            response = await task
            return response, sleep_elapsed

        response, sleep_elapsed = asyncio.run(run_message_and_sleep())

        self.assertLess(sleep_elapsed, 0.12)
        self.assertEqual(response["content"], "slow final.")

    def test_send_message_async_executes_tool_calls_before_final_reply(self) -> None:
        tool_call = ToolCall(id="call-1", name="lookup", arguments={"query": "hi"})
        chat_agent = FakeChatAgent(
            [],
            chat_responses=[
                SimpleNamespace(content="", tool_calls=[tool_call]),
                SimpleNamespace(content="async tool final."),
            ],
        )
        tool_definition = ToolDefinition(
            name="lookup",
            description="Lookup.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
            },
        )
        manager = make_manager(
            chat_agent,
            tools={"lookup": lambda query: {"answer": query.upper()}},
            tool_definitions=[tool_definition],
        )

        response = asyncio.run(manager.send_message("hi"))

        self.assertEqual(response["content"], "async tool final.")
        self.assertEqual(manager.storage.messages, [("user", "hi"), ("assistant", "async tool final.")])
        self.assertEqual(len(chat_agent.chat_messages), 2)
        self.assertEqual(chat_agent.chat_messages[1][-2].role.value, "assistant")
        self.assertEqual(chat_agent.chat_messages[1][-1].role.value, "tool")
        self.assertEqual(chat_agent.chat_messages[1][-1].tool_call_id, "call-1")

    def test_send_message_sync_executes_tool_calls_before_final_reply(self) -> None:
        tool_call = ToolCall(id="call-1", name="lookup", arguments={"query": "hi"})
        chat_agent = FakeChatAgent(
            [],
            chat_responses=[
                SimpleNamespace(content="", tool_calls=[tool_call]),
                SimpleNamespace(content="tool final."),
            ],
        )
        tool_definition = ToolDefinition(
            name="lookup",
            description="Lookup.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
            },
        )
        manager = make_manager(
            chat_agent,
            tools={"lookup": lambda query: {"answer": query.upper()}},
            tool_definitions=[tool_definition],
        )

        response = manager.send_message_sync("hi")

        self.assertEqual(response["content"], "tool final.")
        self.assertEqual(manager.storage.messages, [("user", "hi"), ("assistant", "tool final.")])
        self.assertEqual(len(chat_agent.chat_messages), 2)
        self.assertEqual(chat_agent.chat_kwargs[0]["tools"], [tool_definition])
        self.assertEqual(chat_agent.chat_messages[1][-2].role.value, "assistant")
        self.assertEqual(chat_agent.chat_messages[1][-1].role.value, "tool")
        self.assertEqual(chat_agent.chat_messages[1][-1].tool_call_id, "call-1")
        self.assertIn('"answer": "HI"', chat_agent.chat_messages[1][-1].content)

    def test_send_message_sync_feeds_tool_errors_back_to_model(self) -> None:
        tool_call = ToolCall(id="call-1", name="explode", arguments={})
        chat_agent = FakeChatAgent(
            [],
            chat_responses=[
                SimpleNamespace(content="", tool_calls=[tool_call]),
                SimpleNamespace(content="recovered."),
            ],
        )

        def explode() -> str:
            raise RuntimeError("boom")

        manager = make_manager(
            chat_agent,
            tools={"explode": explode},
            tool_definitions=[
                ToolDefinition(
                    name="explode",
                    description="",
                    parameters={"type": "object", "properties": {}},
                )
            ],
        )

        response = manager.send_message_sync("hi")

        self.assertEqual(response["content"], "recovered.")
        self.assertIn("boom", chat_agent.chat_messages[1][-1].content)
        self.assertEqual(manager.storage.messages, [("user", "hi"), ("assistant", "recovered.")])

    def test_send_message_stream_executes_empty_delta_tool_call(self) -> None:
        tool_call = ToolCall(id="call-1", name="lookup", arguments={"query": "hi"})
        chat_agent = FakeChatAgent(
            [],
            stream_turns=[
                [StreamChunk(delta="", tool_calls=[tool_call])],
                ["stream final."],
            ],
        )
        manager = make_manager(
            chat_agent,
            tools={"lookup": lambda query: {"answer": query}},
            tool_definitions=[
                ToolDefinition(
                    name="lookup",
                    description="",
                    parameters={"type": "object", "properties": {}},
                )
            ],
        )

        events = list(manager.send_message_stream("hi"))

        self.assertEqual([event["type"] for event in events], ["delta", "done"])
        self.assertEqual(events[0]["delta"], "stream final.")
        self.assertEqual(events[-1]["content"], "stream final.")
        self.assertEqual(manager.storage.messages, [("user", "hi"), ("assistant", "stream final.")])
        self.assertEqual(chat_agent.stream_messages[1][-1].role.value, "tool")

    def test_send_message_sync_returns_max_turn_message_once(self) -> None:
        tool_call = ToolCall(id="call-1", name="lookup", arguments={})
        chat_agent = FakeChatAgent(
            [],
            chat_responses=[SimpleNamespace(content="", tool_calls=[tool_call])],
        )
        manager = make_manager(
            chat_agent,
            tools={"lookup": lambda: "ok"},
            tool_definitions=[
                ToolDefinition(
                    name="lookup",
                    description="",
                    parameters={"type": "object", "properties": {}},
                )
            ],
            max_tool_turns=1,
        )

        response = manager.send_message_sync("hi")

        self.assertEqual(response["content"], "Tool call loop reached max turns.")
        self.assertEqual(
            manager.storage.messages,
            [("user", "hi"), ("assistant", "Tool call loop reached max turns.")],
        )

    def test_finalize_stale_current_sessions_generates_missing_summary(self) -> None:
        stale_session = DaySession(date="2026-05-20", message_count=4)
        short_session = DaySession(date="2026-05-19", message_count=3)
        done_session = DaySession(date="2026-05-18", message_count=4, summary_generated=True)
        manager = TestSummaryManager.__new__(TestSummaryManager)
        manager._storage = FakeStaleStorage([stale_session, short_session, done_session])
        manager.config = SimpleNamespace(min_messages_for_summary=4)
        manager._current_date = None
        manager._current_month = None

        generated_count = manager.finalize_stale_current_sessions_sync()

        self.assertEqual(generated_count, 1)
        self.assertTrue(stale_session.summary_generated)
        self.assertFalse(short_session.summary_generated)
        self.assertEqual(manager.storage.archived_after_summary, [stale_session])
        self.assertIsNotNone(manager.storage.requested_today)


if __name__ == "__main__":
    unittest.main()
