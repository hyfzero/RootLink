#!/usr/bin/env python3
"""Regression tests for session prompt/memory stability fixes."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add src/ to import path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_core.api import APIProvider, ChatAgent
from agent_core.api.adapter import ModelConfig
from agent_core.api.adapters.minimax import MiniMaxAdapter
from agent_core.api.message import Message as ApiMessage, MessageRole as ApiMessageRole
from agent_core.api.types import ChatCompletionRequest, ChatCompletionResponse
from agent_core.brain import (
    AgentConfig,
    MessageHistory,
    MessageRole,
    Persona,
    PersonaProfile,
    PromptBuilder,
    TagGenerator,
    estimate_tokens,
)
from agent_core.brain.history import estimate_tokens_with_source
from agent_core.session import (
    BrainRegistry,
    DailySummarizer,
    SessionConfig,
    SessionManager,
    SessionStorage,
)
from agent_core.session.reply_tagger import MemoryUpdater


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


class _FakeChatAgent:
    def __init__(self, content: str):
        self._content = content
        self.calls: list[tuple[list[ApiMessage], bool]] = []

    def chat(self, messages: list[ApiMessage], stream: bool = False):
        self.calls.append((messages, stream))
        return _FakeResponse(self._content)


class SessionStabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._tmp_path = Path(self._tmp.name)
        self._old_agent_data_dir = os.environ.get("AGENT_DATA_DIR")
        os.environ["AGENT_DATA_DIR"] = str(self._tmp_path)

    def tearDown(self) -> None:
        if self._old_agent_data_dir is None:
            os.environ.pop("AGENT_DATA_DIR", None)
        else:
            os.environ["AGENT_DATA_DIR"] = self._old_agent_data_dir
        self._tmp.cleanup()

    def _build_session_manager(self, assistant_reply: str = "pong") -> tuple[SessionManager, BrainRegistry]:
        registry = BrainRegistry(self._tmp_path)
        registry.create_brain("testbrain", name="Tester")
        registry.switch("testbrain")

        manager = SessionManager(
            config=SessionConfig(min_messages_for_summary=1),
            brain_registry=registry,
            chat_agent=_FakeChatAgent(assistant_reply),  # type: ignore[arg-type]
            tag_generator=TagGenerator(),
        )
        return manager, registry

    def test_send_message_sync_updates_storage_history_and_tags(self) -> None:
        manager, registry = self._build_session_manager(assistant_reply="test-reply")

        result = manager.send_message_sync("hello-session")

        today_session = manager.storage.get_or_create_today()
        self.assertEqual(today_session.message_count, 2)

        queue_messages = registry.current().history.current_queue.messages
        self.assertEqual(len(queue_messages), 2)
        self.assertEqual(queue_messages[0].content, "hello-session")
        self.assertEqual(queue_messages[1].content, "test-reply")

        tags_path = self._tmp_path / "testbrain" / "tags" / "reply_tags.json"
        self.assertTrue(tags_path.exists())
        tags_data = json.loads(tags_path.read_text(encoding="utf-8"))
        self.assertIn(result["message_id"], tags_data.get("tags", {}))

    def test_build_conversation_context_keeps_only_latest_message(self) -> None:
        manager, _ = self._build_session_manager(assistant_reply="context-reply")
        manager.send_message_sync("first-message")

        context = manager.prompt_builder.build_conversation_context("latest-message")

        self.assertIn("latest-message", context)
        self.assertNotIn("##", context)

    def test_daily_summarizer_async_writes_structured_json(self) -> None:
        llm_json = """```json
{
  "summary_text": "summary text",
  "important_messages": ["important-1"],
  "topics": ["topic-a"],
  "emotional_tone": "neutral",
  "user_preferences": ["pref-a"],
  "unfinished_topics": ["todo-a"]
}
```"""
        summarizer = DailySummarizer(
            chat_agent=_FakeChatAgent(llm_json),  # type: ignore[arg-type]
            output_dir=self._tmp_path / "testbrain" / "history" / "summaries",
        )

        asyncio.run(
            summarizer.generate_summary(
                date="2026-04-11",
                messages=[
                    ApiMessage(role=ApiMessageRole.USER, content="u"),
                    ApiMessage(role=ApiMessageRole.ASSISTANT, content="a"),
                ],
                persona_context="",
            )
        )

        summary_json_path = (
            self._tmp_path / "testbrain" / "history" / "daily" / "2026-04-11.summary.json"
        )
        data = json.loads(summary_json_path.read_text(encoding="utf-8"))

        self.assertEqual(data["summary_text"], "summary text")
        self.assertEqual(data["important_messages"], ["important-1"])
        self.assertEqual(data["topics"], ["topic-a"])
        self.assertEqual(data["emotional_tone"], "neutral")
        self.assertEqual(data["user_preferences"], ["pref-a"])
        self.assertEqual(data["unfinished_topics"], ["todo-a"])
        self.assertEqual(data["message_count"], 2)

    def test_memory_updater_accepts_legacy_summary_payload(self) -> None:
        persona = Persona(PersonaProfile(name="legacy"))
        updater = MemoryUpdater(persona, storage_path=self._tmp_path / "legacy_memories.json")

        updater.update_from_summary(
            {
                "date": "2026-04-10",
                "summary_text": "legacy summary only",
            }
        )

        self.assertEqual(len(persona.daily_summary_memories), 1)
        memory = persona.daily_summary_memories[0]
        self.assertIn("legacy summary only", memory.content)
        self.assertTrue((memory.context or "").endswith("2026-04-10"))

    def test_memory_injection_policy_is_configurable(self) -> None:
        persona = Persona(PersonaProfile(name="policy-test"))
        persona.add_memory("old fact", memory_type="fact", importance=2.0, context="core")
        persona.add_memory("episodic low", memory_type="episodic", importance=0.4, context="chat")
        persona.add_memory("preference high", memory_type="preference", importance=1.6, context="habit")

        history = MessageHistory()
        config = AgentConfig(
            memory_injection={
                "enabled": True,
                "total_limit": 2,
                "per_type_limit": {"fact": 1, "preference": 1, "episodic": 1},
                "type_weight": {"fact": 1.2, "preference": 1.1, "episodic": 0.6},
                "min_importance": 0.5,
            }
        )
        builder = PromptBuilder(persona=persona, history=history, config=config)

        memory_section = builder.build_memory_section(limit=10)
        bullet_lines = [line for line in memory_section.splitlines() if line.startswith("- [")]
        self.assertEqual(len(bullet_lines), 2)
        self.assertNotIn("episodic low", memory_section)

    def test_token_estimator_modes(self) -> None:
        chinese = "你好，这是一次中文估算测试。"
        english = "This is a short english token estimation test."

        legacy_chinese = estimate_tokens(chinese, estimator="legacy_char_div4")
        hybrid_chinese = estimate_tokens(chinese, estimator="hybrid_v1")
        self.assertGreaterEqual(hybrid_chinese, legacy_chinese)

        legacy_english = estimate_tokens(english, estimator="legacy_char_div4")
        hybrid_english = estimate_tokens(english, estimator="hybrid_v1")
        self.assertGreater(hybrid_english, 0)
        self.assertLessEqual(hybrid_english, legacy_english * 2)

        self.assertEqual(
            legacy_english,
            max(1, len(english) // 4),
        )

    def test_token_estimate_reports_source(self) -> None:
        model_config = ModelConfig(
            name="gpt-4o",
            provider=APIProvider.OPENAI,
            tokenizer_mode="heuristic",
            tokenizer_fallback="legacy_char_div4",
        )
        result = estimate_tokens_with_source(
            "hello world",
            estimator="hybrid_v1",
            model_config=model_config,
        )
        self.assertEqual(result.source, "heuristic_fallback")
        self.assertEqual(result.tokens, max(1, len("hello world") // 4))

    def test_minimax_adapter_usage_normalization(self) -> None:
        adapter = MiniMaxAdapter()
        response = adapter.parse_response(
            {
                "id": "resp-1",
                "model": "MiniMax-M2.5",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "input_tokens": 12,
                    "output_tokens": 5,
                },
            }
        )
        self.assertEqual(response.usage.prompt_tokens, 12)
        self.assertEqual(response.usage.completion_tokens, 5)
        self.assertEqual(response.usage.total_tokens, 17)
        self.assertEqual(response.token_source, "provider_usage")

    def test_chat_agent_fills_usage_when_provider_missing(self) -> None:
        agent = ChatAgent(
            ModelConfig(
                name="MiniMax-M2.5",
                provider=APIProvider.MINIMAX,
                tokenizer_mode="heuristic",
                tokenizer_fallback="hybrid_v1",
            )
        )
        request = ChatCompletionRequest(
            model="MiniMax-M2.5",
            messages=[ApiMessage(role=ApiMessageRole.USER, content="hello")],
        )
        response = ChatCompletionResponse.from_dict(
            {
                "id": "resp-no-usage",
                "model": "MiniMax-M2.5",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "world"},
                        "finish_reason": "stop",
                    }
                ],
            }
        )

        aligned = agent._align_token_usage(request, response)
        self.assertGreater(aligned.usage.total_tokens, 0)
        self.assertEqual(aligned.token_source, "heuristic_fallback")

    def test_token_estimator_is_persisted_in_agent_config(self) -> None:
        config = AgentConfig(history={"token_estimator": "legacy_char_div4"})
        data = config.to_dict()
        self.assertEqual(data["history"]["token_estimator"], "legacy_char_div4")

        loaded = AgentConfig.from_dict(data)
        self.assertEqual(loaded.history.token_estimator, "legacy_char_div4")

    def test_history_and_session_storage_share_estimator_behavior(self) -> None:
        content = "这是同一条消息 mixed with english 123."

        history = MessageHistory(token_estimator="legacy_char_div4")
        history_msg = history.add_message(content, role=MessageRole.USER)

        storage = SessionStorage(
            config=SessionConfig(),
            brain_id="testbrain",
            token_estimator="legacy_char_div4",
        )
        session = storage.add_message("user", content)
        session_msg = session.messages[-1]

        self.assertEqual(history_msg.token_count, session_msg["token_count"])

    def test_history_and_storage_share_model_tokenizer_strategy(self) -> None:
        content = "model strategy check 123"
        model_config = ModelConfig(
            name="gpt-4o",
            provider=APIProvider.OPENAI,
            tokenizer_mode="heuristic",
            tokenizer_fallback="legacy_char_div4",
        )

        history = MessageHistory(
            token_estimator="hybrid_v1",
            tokenizer_mode=model_config.tokenizer_mode,
            model_config=model_config,
        )
        history_msg = history.add_message(content, role=MessageRole.USER)

        storage = SessionStorage(
            config=SessionConfig(),
            brain_id="testbrain-model",
            token_estimator="hybrid_v1",
            tokenizer_mode=model_config.tokenizer_mode,
            model_config=model_config,
        )
        session = storage.add_message("user", content)
        session_msg = session.messages[-1]

        self.assertEqual(history_msg.token_count, session_msg["token_count"])

    def test_prompt_budget_is_configurable(self) -> None:
        persona = Persona(
            PersonaProfile(
                name="budget-test",
                background="Long background " * 80,
                personality_traits=["a", "b", "c", "d", "e"],
                speaking_style="friendly",
            )
        )
        for i in range(8):
            persona.add_memory(
                content=f"memory {i} " + ("very long content " * 20),
                memory_type="fact",
                importance=1.0,
                context="budget",
            )

        history = MessageHistory()
        history.add_message("user message " + ("long " * 80), role=MessageRole.USER)
        history.add_message("assistant message " + ("long " * 80), role=MessageRole.ASSISTANT)

        config = AgentConfig(
            prompt_budget={
                "enabled": True,
                "total_tokens": 80,
                "section_tokens": {
                    "identity": 30,
                    "style": 15,
                    "memory": 20,
                    "history_summary": 20,
                    "queue": 20,
                    "runtime": 10,
                },
            }
        )
        builder = PromptBuilder(persona=persona, history=history, config=config)

        prompt = builder.build_system_prompt()
        self.assertLessEqual(estimate_tokens(prompt), 80)
        self.assertIn("budget-test", prompt)

    def test_relationship_state_machine_is_configurable(self) -> None:
        persona = Persona(PersonaProfile(name="relation-test"))
        config = AgentConfig(
            relationship_state_machine={
                "enabled": True,
                "default_state": "neutral",
                "initial_score": 0.0,
                "min_score": -20.0,
                "max_score": 20.0,
                "decay_per_turn": 0.0,
                "role_weight": {"user": 1.0, "assistant": 0.0},
                "signal_weights": {"positive": 5.0, "negative": -6.0},
                "signal_keywords": {
                    "positive": ["谢谢", "喜欢"],
                    "negative": ["讨厌"],
                },
                "states": [
                    {"name": "cold", "min_score": -20.0, "max_score": -1.0, "prompt_hint": "保持距离"},
                    {"name": "neutral", "min_score": -1.0, "max_score": 8.0, "prompt_hint": "自然交流"},
                    {"name": "warm", "min_score": 8.0, "max_score": 20.0, "prompt_hint": "更温和"},
                ],
            }
        )

        policy = config.relationship_state_machine.to_dict()
        persona.update_relationship_state("谢谢你，我很喜欢这个回答", role="user", policy=policy)
        snapshot = persona.get_relationship_snapshot(policy=policy)
        self.assertEqual(snapshot["state"], "warm")
        self.assertGreater(snapshot["score"], 0.0)

        builder = PromptBuilder(persona=persona, history=MessageHistory(), config=config)
        relationship_section = builder.build_relationship_section()
        self.assertIn("## 关系状态", relationship_section)
        self.assertIn("当前阶段：warm", relationship_section)

    def test_session_manager_syncs_relationship_state(self) -> None:
        manager, registry = self._build_session_manager(assistant_reply="好的，我会继续支持你。")
        registry.current().config.relationship_state_machine.enabled = True
        registry.current().config.relationship_state_machine.signal_keywords = {
            "positive": ["谢谢", "支持"],
            "negative": ["讨厌"],
            "trust": [],
            "conflict": [],
        }
        registry.current().config.relationship_state_machine.signal_weights = {
            "positive": 5.0,
            "negative": -6.0,
            "trust": 0.0,
            "conflict": 0.0,
        }
        registry.current().config.relationship_state_machine.decay_per_turn = 0.0
        registry.current().config.relationship_state_machine.role_weight = {"user": 1.0, "assistant": 0.0}
        registry.current().config.relationship_state_machine.states = [
            {"name": "cold", "min_score": -100.0, "max_score": -1.0, "prompt_hint": "冷淡"},
            {"name": "neutral", "min_score": -1.0, "max_score": 8.0, "prompt_hint": "中性"},
            {"name": "warm", "min_score": 8.0, "max_score": 100.0, "prompt_hint": "亲和"},
        ]

        manager.send_message_sync("谢谢你一直支持我")
        profile = registry.current().persona.profile
        self.assertEqual(profile.relationship_state, "warm")
        self.assertGreater(profile.relationship_score, 0.0)

        profile_path = self._tmp_path / "testbrain" / "persona" / "profile.json"
        saved = json.loads(profile_path.read_text(encoding="utf-8"))
        self.assertEqual(saved.get("relationship_state"), "warm")


if __name__ == "__main__":
    unittest.main()
