#!/usr/bin/env python3
"""Regression tests for runtime personality state rules."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_core.brain.persona import (  # noqa: E402
    Persona,
    PersonaProfile,
    PersonalityState,
    STATE_WARM_AFFINITY_THRESHOLD,
)
from agent_core.brain.config import RelationshipStateMachineConfig  # noqa: E402


class PersonalityStateTests(unittest.TestCase):
    def test_prompt_uses_runtime_warm_affinity_threshold(self) -> None:
        state = PersonalityState(affinity=STATE_WARM_AFFINITY_THRESHOLD, tension=0.0)

        self.assertIn("延续关系温度", state.build_prompt_text())

    def test_user_turn_without_signal_clears_stale_focus_when_tension_is_low(self) -> None:
        persona = Persona(
            PersonaProfile(name="Assistant"),
            state=PersonalityState(
                mood="focused",
                energy=0.62,
                affinity=4.8,
                tension=0.0,
                current_focus="延续积极互动",
                last_emotion="thinking",
            ),
        )

        state = persona.update_personality_state(
            content="记录一下今天的进度。",
            role="user",
            emotion=None,
        )

        self.assertIsNone(state.current_focus)
        self.assertEqual(state.mood, "neutral")

    def test_assistant_thinking_updates_focus_to_match_focused_mood(self) -> None:
        persona = Persona(
            PersonaProfile(name="Assistant"),
            state=PersonalityState(
                mood="warm",
                energy=0.6,
                affinity=4.8,
                tension=0.0,
                current_focus="延续积极互动",
            ),
        )

        state = persona.update_personality_state(
            content="我先整理一下思路。",
            role="assistant",
            emotion="thinking",
        )

        self.assertEqual(state.current_focus, "澄清问题并组织思路")
        self.assertEqual(state.mood, "focused")
        self.assertEqual(state.last_emotion, "thinking")

    def test_state_persists_long_mid_and_short_term_fields(self) -> None:
        state = PersonalityState(
            affinity=12.0,
            trust=14.0,
            familiarity=8.0,
            boundary_comfort=48.0,
            recent_valence=16.0,
            recent_support=11.0,
            recent_conflict=4.0,
        )

        restored = PersonalityState.from_dict(state.to_dict())

        self.assertEqual(restored.trust, 14.0)
        self.assertEqual(restored.familiarity, 8.0)
        self.assertEqual(restored.boundary_comfort, 48.0)
        self.assertEqual(restored.recent_valence, 16.0)
        self.assertEqual(restored.recent_support, 11.0)
        self.assertEqual(restored.recent_conflict, 4.0)

    def test_positive_trust_user_turn_updates_long_and_mid_term_axes(self) -> None:
        persona = Persona(PersonaProfile(name="Assistant"))

        state = persona.update_personality_state(
            content="谢谢你，我信任你，也放心依赖你。",
            role="user",
            emotion="happy",
        )

        self.assertGreater(state.affinity, 0.0)
        self.assertGreater(state.trust, 0.0)
        self.assertGreater(state.familiarity, 0.0)
        self.assertGreater(state.recent_valence, 0.0)
        self.assertGreater(state.recent_support, 0.0)

    def test_default_relationship_state_machine_has_lover_as_highest_state(self) -> None:
        persona = Persona(PersonaProfile(name="Assistant"))
        policy = RelationshipStateMachineConfig().to_dict()

        snapshot = persona.update_relationship_state(
            content="谢谢 喜欢 支持 关心 在意 陪伴 love 信任 放心 依赖 秘密 承诺 爱人 trust lover",
            role="user",
            policy=policy,
        )

        self.assertEqual(snapshot["state"], "lover")
        self.assertIn("爱人", snapshot["prompt_hint"])


if __name__ == "__main__":
    unittest.main()
