#!/usr/bin/env python3
"""Tests for session-level streaming message events."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

TEST_FILE = Path(__file__).resolve()
SRC_DIR = TEST_FILE.parents[2]

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

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
    def __init__(self, chunks: list[str], fallback: str = "fallback。", fail_stream: bool = False) -> None:
        self.chunks = chunks
        self.fallback = fallback
        self.fail_stream = fail_stream
        self.stream_kwargs: list[dict] = []
        self.chat_kwargs: list[dict] = []

    def stream_chat(self, messages, **kwargs):
        self.stream_kwargs.append(kwargs)
        if self.fail_stream:
            raise RuntimeError("stream unavailable")
        for chunk in self.chunks:
            yield StreamChunk(delta=chunk)

    def chat(self, messages, stream: bool = False, **kwargs):
        self.chat_kwargs.append({"stream": stream, **kwargs})
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


def make_manager(chat_agent: FakeChatAgent, response_config: object | None = None) -> TestSessionManager:
    manager = TestSessionManager.__new__(TestSessionManager)
    manager._storage = FakeStorage()
    manager.chat_agent = chat_agent
    manager.tagger = FakeTagger()
    manager.fake_prompt_builder = FakePromptBuilder()
    manager._current_brain_id = "test-brain"
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
