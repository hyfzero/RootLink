#!/usr/bin/env python3
"""Tests for brain registry loading behavior."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

TEST_FILE = Path(__file__).resolve()
SRC_DIR = TEST_FILE.parents[2]

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agent_core.brain import PRESET_STYLES
from agent_core.session import BrainRegistry


def _write_minimal_brain(root: Path, brain_id: str, *, speaking_style: str = "gentle") -> Path:
    brain_dir = root / brain_id
    persona_dir = brain_dir / "persona"
    history_dir = brain_dir / "history"
    persona_dir.mkdir(parents=True)
    history_dir.mkdir()
    (persona_dir / "profile.json").write_text(
        json.dumps({"name": brain_id, "speaking_style": speaking_style}),
        encoding="utf-8",
    )
    (persona_dir / "memories.json").write_text(
        json.dumps(
            {
                "episodic_memories": [],
                "preference_memories": [],
                "fact_memories": [],
                "daily_summary_memories": [],
                "monthly_summary_memories": [],
            }
        ),
        encoding="utf-8",
    )
    (history_dir / "history.json").write_text(json.dumps({"daily_histories": {}, "daily_summaries": {}, "current_queue": {}}), encoding="utf-8")
    return brain_dir


class BrainRegistryTests(unittest.TestCase):
    def test_speaking_style_json_overrides_profile_preset(self) -> None:
        with tempfile.TemporaryDirectory() as data_root:
            brain_dir = _write_minimal_brain(Path(data_root), "custom_style", speaking_style="gentle")
            (brain_dir / "persona" / "speaking_style.json").write_text(
                json.dumps(
                    {
                        "base_style": {
                            "vocabulary_level": "academic",
                            "sentence_length": "long",
                            "exclamation_rate": 0.44,
                            "question_rate": 0.77,
                            "ellipsis_rate": 0.22,
                            "emoji_usage": "none",
                            "parenthesis_usage": "none",
                        },
                        "influence_weight": 0.12,
                        "custom_modifiers": {},
                    }
                ),
                encoding="utf-8",
            )

            registry = BrainRegistry(Path(data_root))
            registry.load_all()
            components = registry.switch("custom_style")

            self.assertEqual(components.style_engine.base_style.question_rate, 0.77)
            self.assertEqual(components.style_engine.base_style.sentence_length, "long")
            self.assertEqual(components.style_engine.influence_weight, 0.12)

    def test_missing_speaking_style_json_keeps_profile_preset_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as data_root:
            _write_minimal_brain(Path(data_root), "preset_style", speaking_style="casual")

            registry = BrainRegistry(Path(data_root))
            registry.load_all()
            components = registry.switch("preset_style")

            self.assertEqual(components.style_engine.base_style.sentence_length, PRESET_STYLES["casual"].sentence_length)
            self.assertEqual(components.style_engine.base_style.question_rate, PRESET_STYLES["casual"].question_rate)


if __name__ == "__main__":
    unittest.main()
