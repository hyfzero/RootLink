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
    PersonalityState,
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

    def _reload_session_manager(self, assistant_reply: str = "pong") -> tuple[SessionManager, BrainRegistry, _FakeChatAgent]:
        registry = BrainRegistry(self._tmp_path)
        registry.load_all()
        registry.switch("testbrain")

        chat_agent = _FakeChatAgent(assistant_reply)
        manager = SessionManager(
            config=SessionConfig(min_messages_for_summary=1),
            brain_registry=registry,
            chat_agent=chat_agent,  # type: ignore[arg-type]
            tag_generator=TagGenerator(),
        )
        return manager, registry, chat_agent

    def test_send_message_sync_updates_storage_history_and_tags(self) -> None:
        manager, registry = self._build_session_manager(assistant_reply="test-reply")

        result = manager.send_message_sync("hello-session")

        today_session = manager.storage.get_or_create_today()
        self.assertEqual(today_session.message_count, 2)

        queue_messages = registry.current().history.current_queue.messages
        self.assertEqual(len(queue_messages), 2)
        self.assertEqual(queue_messages[0].content, "hello-session")
        self.assertEqual(queue_messages[1].content, "test-reply")

        history_path = self._tmp_path / "testbrain" / "history" / "history.json"
        self.assertTrue(history_path.exists())
        history_data = json.loads(history_path.read_text(encoding="utf-8"))
        persisted_queue = history_data.get("current_queue", {}).get("messages", [])
        self.assertEqual([m.get("content") for m in persisted_queue], ["hello-session", "test-reply"])

        tags_path = self._tmp_path / "testbrain" / "tags" / "reply_tags.json"
        self.assertTrue(tags_path.exists())
        tags_data = json.loads(tags_path.read_text(encoding="utf-8"))
        self.assertIn(result["message_id"], tags_data.get("tags", {}))

    def test_reloaded_manager_injects_persisted_history_queue(self) -> None:
        manager, _ = self._build_session_manager(assistant_reply="morning-reply")
        manager.send_message_sync("morning-context")

        reloaded_manager, _, chat_agent = self._reload_session_manager(assistant_reply="afternoon-reply")
        reloaded_manager.send_message_sync("afternoon-message")

        system_prompt = chat_agent.calls[-1][0][0].content
        self.assertIn("morning-context", system_prompt)
        self.assertIn("morning-reply", system_prompt)
        self.assertIn("afternoon-message", system_prompt)

    def test_reloaded_manager_restores_today_context_from_session_when_history_missing(self) -> None:
        manager, _ = self._build_session_manager(assistant_reply="session-only-reply")
        manager.send_message_sync("session-only-morning")

        history_path = self._tmp_path / "testbrain" / "history" / "history.json"
        history_path.unlink()

        reloaded_manager, registry, chat_agent = self._reload_session_manager(assistant_reply="fallback-reply")
        self.assertEqual(len(registry.current().history.current_queue.messages), 0)

        reloaded_manager.send_message_sync("fallback-afternoon")

        restored_messages = registry.current().history.current_queue.messages
        self.assertIn("session-only-morning", [m.content for m in restored_messages])
        self.assertIn("session-only-reply", [m.content for m in restored_messages])

        system_prompt = chat_agent.calls[-1][0][0].content
        self.assertIn("session-only-morning", system_prompt)
        self.assertIn("session-only-reply", system_prompt)

    def test_build_conversation_context_keeps_only_latest_message(self) -> None:
        manager, _ = self._build_session_manager(assistant_reply="context-reply")
        manager.send_message_sync("first-message")

        context = manager.prompt_builder.build_conversation_context("latest-message")

        self.assertIn("latest-message", context)
        self.assertNotIn("##", context)

    def test_llm_emotion_mode_parses_json_response(self) -> None:
        generator = TagGenerator(
            llm_callable=lambda prompt: '{"emotion":"happy"}',
            emotion_mode="llm",
        )

        tag = generator.generate_tag("llm-emotion", "ignored text")

        self.assertEqual(tag.emotion, "happy")
        self.assertEqual(tag.expression, "smile")

    def test_llm_emotion_mode_falls_back_to_keywords(self) -> None:
        unknown_generator = TagGenerator(
            llm_callable=lambda prompt: '{"emotion":"mystery"}',
            emotion_mode="llm",
        )
        self.assertEqual(
            unknown_generator.generate_tag("fallback-unknown", "I am so happy today").emotion,
            "happy",
        )

        def failing_llm(prompt: str) -> str:
            raise RuntimeError("llm unavailable")

        failing_generator = TagGenerator(llm_callable=failing_llm, emotion_mode="llm")
        self.assertEqual(
            failing_generator.generate_tag("fallback-error", "I am angry about this bug").emotion,
            "angry",
        )

    def test_brain_registry_loads_default_personality_state_without_state_file(self) -> None:
        registry = BrainRegistry(self._tmp_path)
        components = registry.create_brain("state-default", name="StateDefault")

        self.assertIsInstance(components.persona.state, PersonalityState)
        self.assertEqual(components.persona.state.mood, "neutral")
        self.assertFalse((self._tmp_path / "state-default" / "persona" / "state.json").exists())

    def test_personality_state_persists_separately_from_profile(self) -> None:
        manager, registry = self._build_session_manager(assistant_reply="我会继续支持你。")

        manager.send_message_sync("谢谢你一直支持我")

        state_path = self._tmp_path / "testbrain" / "persona" / "state.json"
        profile_path = self._tmp_path / "testbrain" / "persona" / "profile.json"
        state_data = json.loads(state_path.read_text(encoding="utf-8"))
        profile_data = json.loads(profile_path.read_text(encoding="utf-8"))

        self.assertGreater(state_data["affinity"], 0.0)
        self.assertIn(state_data["mood"], ["warm", "focused", "neutral"])
        self.assertNotIn("personality_state", profile_data)

        reloaded = BrainRegistry(self._tmp_path)
        reloaded.load_all()
        reloaded.switch("testbrain")
        self.assertEqual(
            reloaded.current().persona.state.to_dict()["affinity"],
            registry.current().persona.state.to_dict()["affinity"],
        )

    def test_personality_state_section_is_injected_before_memory(self) -> None:
        persona = Persona(PersonaProfile(name="state-prompt"))
        persona.state = PersonalityState(
            mood="warm",
            affinity=15.0,
            current_focus="延续积极互动",
            last_emotion="happy",
        )
        persona.add_memory("用户喜欢稳定的陪伴感", memory_type="preference", importance=1.5)

        builder = PromptBuilder(persona=persona, history=MessageHistory(), config=AgentConfig())
        prompt = builder.build_system_prompt()

        self.assertIn("## 当前人格状态", prompt)
        self.assertIn("当前心境：温和亲近", prompt)
        self.assertIn("最近自身情绪：happy", prompt)
        self.assertLess(prompt.index("## 当前人格状态"), prompt.index("## 近期记忆"))

    def test_personality_state_user_turn_only_updates_relationship_side(self) -> None:
        persona = Persona(PersonaProfile(name="user-state"))
        persona.state = PersonalityState(
            mood="warm",
            energy=0.62,
            affinity=4.0,
            tension=0.5,
            current_focus="延续积极互动",
            last_emotion="happy",
        )

        persona.update_personality_state("谢谢你一直支持我", role="user", emotion="happy")

        self.assertGreater(persona.state.affinity, 4.0)
        self.assertLess(persona.state.tension, 0.5)
        self.assertEqual(persona.state.current_focus, "延续积极互动")
        self.assertEqual(persona.state.last_emotion, "happy")
        self.assertAlmostEqual(persona.state.energy, 0.6, places=2)

    def test_personality_state_assistant_turn_only_updates_self_state(self) -> None:
        persona = Persona(PersonaProfile(name="assistant-state"))
        persona.state = PersonalityState(
            mood="neutral",
            energy=0.52,
            affinity=9.0,
            tension=1.0,
            current_focus="延续积极互动",
            last_emotion="neutral",
        )

        persona.update_personality_state("哈哈，那我继续陪着你。", role="assistant", emotion="happy")

        self.assertEqual(persona.state.mood, "warm")
        self.assertGreater(persona.state.energy, 0.52)
        self.assertEqual(persona.state.last_emotion, "happy")
        self.assertEqual(persona.state.affinity, 9.0)
        self.assertLess(persona.state.tension, 1.0)

    def test_personality_state_natural_decay_preserves_warm_baseline(self) -> None:
        persona = Persona(PersonaProfile(name="warm-baseline"))
        persona.state = PersonalityState(
            mood="warm",
            energy=0.72,
            affinity=16.0,
            tension=1.2,
            current_focus="延续积极互动",
            last_emotion="happy",
        )

        persona.update_personality_state("今天就先这样。", role="user")

        self.assertEqual(persona.state.mood, "warm")
        self.assertLess(persona.state.tension, 1.2)
        self.assertLess(persona.state.energy, 0.72)
        self.assertEqual(persona.state.last_emotion, "happy")

    def test_personality_state_natural_decay_reduces_tension_and_recenters_energy(self) -> None:
        persona = Persona(PersonaProfile(name="decay-state"))
        persona.state = PersonalityState(
            mood="tense",
            energy=0.85,
            affinity=2.0,
            tension=6.5,
            current_focus="缓和对话张力",
        )

        persona.update_personality_state("收到。", role="assistant", emotion="neutral")
        persona.update_personality_state("嗯。", role="assistant", emotion="neutral")

        self.assertLess(persona.state.tension, 6.5)
        self.assertLess(persona.state.energy, 0.85)
        self.assertGreater(persona.state.energy, 0.6)

    def test_personality_state_damping_caps_single_turn_delta(self) -> None:
        persona = Persona(PersonaProfile(name="damping-state"))
        persona.state = PersonalityState(affinity=10.0, tension=0.0)

        persona.update_personality_state(
            "谢谢谢谢谢谢你，我真的很喜欢很喜欢，也很信任很信任你",
            role="user",
            emotion="happy",
        )
        positive_affinity = persona.state.affinity

        self.assertLessEqual(positive_affinity - 10.0, 2.0)

        persona.state.affinity = 10.0
        persona.state.tension = 0.0
        persona.update_personality_state(
            "我讨厌讨厌讨厌你，真的很烦很烦，生气死了，闭嘴，蠢，hate hate",
            role="user",
            emotion="angry",
        )

        self.assertLessEqual(10.0 - persona.state.affinity, 2.0)
        self.assertLessEqual(persona.state.tension, 3.0)

    def test_last_emotion_tracks_assistant_only(self) -> None:
        persona = Persona(PersonaProfile(name="emotion-owner"))
        persona.state = PersonalityState(last_emotion="happy", current_focus="延续积极互动")

        persona.update_personality_state("我现在很生气", role="user", emotion="angry")
        self.assertEqual(persona.state.last_emotion, "happy")

        persona.update_personality_state("我会继续帮你。", role="assistant", emotion="thinking")
        self.assertEqual(persona.state.last_emotion, "thinking")

    def test_personality_state_updates_for_negative_input(self) -> None:
        persona = Persona(PersonaProfile(name="negative-state"))
        persona.state = PersonalityState(last_emotion="happy")

        persona.update_personality_state("你这样很烦，我讨厌这个回答", role="user", emotion="angry")

        self.assertGreater(persona.state.tension, 0.0)
        self.assertEqual(persona.state.mood, "tense")
        self.assertEqual(persona.state.last_emotion, "happy")

    def test_send_message_sync_preserves_warm_state_for_positive_interaction(self) -> None:
        manager, registry = self._build_session_manager(assistant_reply="哈哈，我也很开心继续陪着你。")
        registry.current().persona.state.affinity = 10.0
        registry.current().persona.state.current_focus = "延续积极互动"

        manager.send_message_sync("谢谢你一直支持我")

        state_path = self._tmp_path / "testbrain" / "persona" / "state.json"
        state_data = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertGreater(state_data["affinity"], 10.0)
        self.assertEqual(state_data["mood"], "warm")

        reloaded = BrainRegistry(self._tmp_path)
        reloaded.load_all()
        reloaded.switch("testbrain")
        self.assertEqual(reloaded.current().persona.state.mood, "warm")

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
