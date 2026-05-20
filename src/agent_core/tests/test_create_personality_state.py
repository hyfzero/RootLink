#!/usr/bin/env python3
"""Tests for create-flow personality form state."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TEST_FILE = Path(__file__).resolve()
SRC_DIR = TEST_FILE.parents[2]
REPO_ROOT = TEST_FILE.parents[3]

for path in (str(REPO_ROOT), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from GUI.interfaces import CompanionRole, MemoryDraft
from GUI.components import MemoryEditor
from GUI.views import CompanionAppView


class NoRebuildCompanionAppView(CompanionAppView):
    def __init__(self, roles: list[CompanionRole]) -> None:
        self.safe_update_calls = 0
        super().__init__(roles=roles)

    def _safe_update(self) -> None:
        self.safe_update_calls += 1


def make_role() -> CompanionRole:
    return CompanionRole(
        id="amadeus",
        name="Amadeus",
        type="Test",
        tags=[],
        intro="intro",
        status_text="status",
        accent_color="#FF6600",
        avatar_path="",
        standing_image_path="",
    )


class CreatePersonalityStateTests(unittest.TestCase):
    def test_adding_trait_preserves_personality_fields(self) -> None:
        view = NoRebuildCompanionAppView(roles=[make_role()])
        view._personality_step(view._colors())
        view._age_field.value = "18"
        view._birthday_field.value = "2008-01-01"
        view._background_field.value = "转学生。"
        view._gender_dropdown.value = "female"
        view._style_dropdown.value = "calm"
        view._trait_field.value = "认真"

        view._add_trait()

        self.assertEqual(view._draft.age, "18")
        self.assertEqual(view._draft.birthday, "2008-01-01")
        self.assertEqual(view._draft.background, "转学生。")
        self.assertEqual(view._draft.gender, "female")
        self.assertEqual(view._draft.speaking_style_preset, "calm")
        self.assertEqual(view._draft.personality_traits, ["认真"])
        self.assertEqual(view._trait_field.value, "")
        self.assertEqual(view.safe_update_calls, 0)

    def test_adding_interest_preserves_personality_fields(self) -> None:
        view = NoRebuildCompanionAppView(roles=[make_role()])
        view._personality_step(view._colors())
        view._age_field.value = "21"
        view._birthday_field.value = "2005-05-04"
        view._background_field.value = "喜欢安静的地方。"
        view._interest_field.value = "钢琴"

        view._add_interest()

        self.assertEqual(view._draft.age, "21")
        self.assertEqual(view._draft.birthday, "2005-05-04")
        self.assertEqual(view._draft.background, "喜欢安静的地方。")
        self.assertEqual(view._draft.interests, ["钢琴"])
        self.assertEqual(view._interest_field.value, "")
        self.assertEqual(view.safe_update_calls, 0)

    def test_removing_trait_and_interest_updates_without_page_rebuild(self) -> None:
        view = NoRebuildCompanionAppView(roles=[make_role()])
        view._draft.personality_traits = ["认真", "温柔"]
        view._draft.interests = ["钢琴", "阅读"]
        view._personality_step(view._colors())

        view._remove_trait("认真")
        view._remove_interest("钢琴")

        self.assertEqual(view._draft.personality_traits, ["温柔"])
        self.assertEqual(view._draft.interests, ["阅读"])
        self.assertEqual(view.safe_update_calls, 0)

    def test_adding_memory_updates_without_page_rebuild(self) -> None:
        view = NoRebuildCompanionAppView(roles=[make_role()])
        view._memory_step(view._colors())

        view._add_memory()

        self.assertEqual(len(view._draft.memories), 1)
        self.assertEqual(len(view._memory_editors), 1)
        self.assertEqual(view._draft.memories[0].memory_type, "episodic")
        self.assertTrue(view._memory_category_open["episodic"])
        self.assertEqual(view.safe_update_calls, 0)

    def test_memory_categories_default_open_only_when_populated(self) -> None:
        view = NoRebuildCompanionAppView(roles=[make_role()])
        view._draft.memories = [MemoryDraft(content="pref", memory_type="preference")]

        view._memory_step(view._colors())

        self.assertFalse(view._memory_category_open["episodic"])
        self.assertTrue(view._memory_category_open["preference"])
        self.assertFalse(view._memory_category_open["fact"])
        self.assertFalse(view._memory_category_open["daily_summary"])
        self.assertFalse(view._memory_category_open["monthly_summary"])
        self.assertEqual(len(view._memory_editors), 1)
        self.assertEqual(view._memory_editor_indices, [0])

    def test_adding_memory_to_category_opens_group(self) -> None:
        view = NoRebuildCompanionAppView(roles=[make_role()])
        view._memory_step(view._colors())

        view._add_memory("daily_summary")

        self.assertEqual(len(view._draft.memories), 1)
        self.assertEqual(view._draft.memories[0].memory_type, "daily_summary")
        self.assertTrue(view._memory_category_open["daily_summary"])
        self.assertEqual(len(view._memory_editors), 1)
        self.assertEqual(view._memory_editor_indices, [0])
        self.assertEqual(view.safe_update_calls, 0)

    def test_memory_type_change_moves_editor_between_categories(self) -> None:
        view = NoRebuildCompanionAppView(roles=[make_role()])
        view._draft.memories = [MemoryDraft(content="note", memory_type="episodic")]
        view._memory_step(view._colors())

        view._memory_editors[0].type_dropdown.value = "fact"
        view._memory_editors[0].type_dropdown.on_change(None)

        self.assertEqual(view._draft.memories[0].memory_type, "fact")
        self.assertTrue(view._memory_category_open["fact"])
        self.assertEqual(len(view._memory_editors), 1)
        self.assertEqual(view._memory_editor_indices, [0])
        self.assertEqual(view._memory_editors[0].type_dropdown.value, "fact")
        self.assertEqual(view.safe_update_calls, 0)

    def test_memory_close_button_removes_without_crashing(self) -> None:
        view = NoRebuildCompanionAppView(roles=[make_role()])
        view._draft.memories = [MemoryDraft(content="记住这件事")]
        view._memory_step(view._colors())
        close_button = view._memory_editors[0].content.controls[0].controls[1]

        close_button.on_click(None)

        self.assertEqual(view._draft.memories, [])
        self.assertEqual(view.safe_update_calls, 0)

    def test_memory_importance_shows_live_numeric_value(self) -> None:
        colors = CompanionAppView(roles=[make_role()])._colors()
        editor = MemoryEditor(MemoryDraft(content="note", importance=1.2), colors, lambda: None)

        self.assertEqual(editor.importance_value.value, "1.2 / 2.0")

        editor.importance.value = 1.7
        editor.importance.on_change(None)

        self.assertEqual(editor.importance_value.value, "1.7 / 2.0")


if __name__ == "__main__":
    unittest.main()
