#!/usr/bin/env python3
"""Tests for response length guidance in prompts."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TEST_FILE = Path(__file__).resolve()
SRC_DIR = TEST_FILE.parents[2]

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agent_core.brain import AgentConfig, Persona, PersonaProfile, PromptBuilder, ResponseConfig


class PromptBuilderResponseGuidanceTests(unittest.TestCase):
    def test_system_prompt_includes_soft_sentence_guidance(self) -> None:
        persona = Persona(PersonaProfile(name="Assistant"))
        config = AgentConfig(response=ResponseConfig(max_sentences=1))
        builder = PromptBuilder(persona=persona, config=config)

        prompt = builder.build_system_prompt()

        self.assertIn("## 回复长度", prompt)
        self.assertIn("默认自然控制在 1 句以内。", prompt)
        self.assertIn("不要因为长度限制把一句话说到一半。", prompt)

    def test_system_prompt_omits_response_guidance_when_disabled(self) -> None:
        persona = Persona(PersonaProfile(name="Assistant"))
        config = AgentConfig(response=ResponseConfig(max_sentences=None))
        builder = PromptBuilder(persona=persona, config=config)

        prompt = builder.build_system_prompt()

        self.assertNotIn("## 回复长度", prompt)


if __name__ == "__main__":
    unittest.main()
