#!/usr/bin/env python3
"""Tests for data-backed character creation."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

TEST_FILE = Path(__file__).resolve()
SRC_DIR = TEST_FILE.parents[2]
REPO_ROOT = TEST_FILE.parents[3]

for path in (str(REPO_ROOT), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from GUI.character_creator import CharacterCreationError, CharacterCreator
from GUI.interfaces import CharacterDraft, MemoryDraft
from GUI.role_loader import load_roles_from_data


class CharacterCreatorTests(unittest.TestCase):
    def test_create_writes_complete_brain_structure_and_loadable_ui_role(self) -> None:
        with tempfile.TemporaryDirectory() as data_root, tempfile.TemporaryDirectory() as assets_root:
            image_path = Path(assets_root) / "avatar.png"
            image_path.write_bytes(b"png-bytes")

            draft = CharacterDraft(
                brain_id="custom_role",
                name="Custom Role",
                description="A data-backed character.",
                avatar_path=str(image_path),
                portraits={"neutral": str(image_path), "happy": str(image_path)},
                personality_traits=["warm", "direct"],
                memories=[MemoryDraft(content="Likes tea.", memory_type="preference", importance=1.5)],
            )

            result = CharacterCreator(Path(data_root)).create(draft)
            brain_dir = result.brain_dir

            expected_files = [
                "assets/avatar.png",
                "assets/portraits/neutral.png",
                "assets/portraits/happy.png",
                "persona/profile.json",
                "persona/memories.json",
                "persona/state.json",
                "persona/speaking_style.json",
                "history/history.json",
                "tags/reply_tags.json",
                "config.json",
                "ui.json",
            ]
            for relative_path in expected_files:
                self.assertTrue((brain_dir / relative_path).exists(), relative_path)

            for relative_dir in ("history/daily", "history/summaries", "session/current", "session/archive"):
                self.assertTrue((brain_dir / relative_dir).is_dir(), relative_dir)

            roles = load_roles_from_data(Path(data_root))
            self.assertEqual([role.id for role in roles], ["custom_role"])
            self.assertEqual(roles[0].name, "Custom Role")
            self.assertEqual(roles[0].portraits["neutral"], (brain_dir / "assets/portraits/neutral.png").as_posix())

    def test_create_uses_selected_card_accent_color(self) -> None:
        with tempfile.TemporaryDirectory() as data_root:
            result = CharacterCreator(Path(data_root)).create(
                CharacterDraft(brain_id="accent_role", name="Accent Role", accent_color="#88A0C8")
            )
            ui = json.loads((result.brain_dir / "ui.json").read_text(encoding="utf-8"))

            self.assertEqual(ui["accent_color"], "#88A0C8")
            roles = load_roles_from_data(Path(data_root))
            self.assertEqual(roles[0].accent_color, "#88A0C8")

    def test_validation_failures_leave_no_partial_directory(self) -> None:
        cases = [
            CharacterDraft(brain_id="", name="No Id"),
            CharacterDraft(brain_id="../bad", name="Bad Id"),
            CharacterDraft(brain_id="valid_id", name=""),
        ]
        for draft in cases:
            with self.subTest(draft=draft):
                with tempfile.TemporaryDirectory() as data_root:
                    with self.assertRaises(CharacterCreationError):
                        CharacterCreator(Path(data_root)).create(draft)
                    self.assertEqual(list(Path(data_root).iterdir()), [])

    def test_duplicate_brain_id_fails_without_overwriting_existing_character(self) -> None:
        with tempfile.TemporaryDirectory() as data_root:
            data_dir = Path(data_root)
            existing = data_dir / "dup"
            existing.mkdir()
            sentinel = existing / "sentinel.txt"
            sentinel.write_text("keep", encoding="utf-8")

            with self.assertRaises(CharacterCreationError):
                CharacterCreator(data_dir).create(CharacterDraft(brain_id="dup", name="Duplicate"))

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
            self.assertFalse(any(path.name.startswith(".creating-dup-") for path in data_dir.iterdir()))

    def test_create_allows_empty_avatar_and_portrait_without_default_assets(self) -> None:
        with tempfile.TemporaryDirectory() as data_root:
            result = CharacterCreator(Path(data_root)).create(CharacterDraft(brain_id="empty_assets", name="Empty Assets"))
            brain_dir = result.brain_dir
            ui = json.loads((brain_dir / "ui.json").read_text(encoding="utf-8"))

            self.assertEqual(ui["avatar"], "")
            self.assertEqual(ui["standing_image"], "")
            self.assertEqual(ui["portraits"], {})
            self.assertFalse((brain_dir / "assets" / "avatar.png").exists())
            self.assertFalse((brain_dir / "assets" / "portraits" / "neutral.png").exists())

            roles = load_roles_from_data(Path(data_root))
            self.assertEqual(roles[0].avatar_path, "")
            self.assertEqual(roles[0].standing_image_path, "")
            self.assertEqual(roles[0].last_message, "")
            self.assertEqual(roles[0].last_time, "")

    def test_role_recent_chat_comes_from_session_messages_only(self) -> None:
        with tempfile.TemporaryDirectory() as data_root:
            result = CharacterCreator(Path(data_root)).create(CharacterDraft(brain_id="recent_role", name="Recent Role"))
            brain_dir = result.brain_dir
            ui_path = brain_dir / "ui.json"
            ui = json.loads(ui_path.read_text(encoding="utf-8"))
            ui["last_message"] = "stale default"
            ui["last_time"] = "00:00"
            ui_path.write_text(json.dumps(ui, ensure_ascii=False), encoding="utf-8")

            roles = load_roles_from_data(Path(data_root))
            self.assertEqual(roles[0].last_message, "")
            self.assertEqual(roles[0].last_time, "")

            session_path = brain_dir / "session" / "current" / "2026-05-04.json"
            session_path.write_text(
                json.dumps(
                    {
                        "date": "2026-05-04",
                        "messages": [
                            {"role": "user", "content": "older", "timestamp": 1777860000},
                            {"role": "assistant", "content": "第一句。最新一句。", "timestamp": 1777860060},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            roles = load_roles_from_data(Path(data_root))
            self.assertEqual(roles[0].last_message, "最新一句。")
            self.assertEqual(roles[0].last_time, datetime.fromtimestamp(1777860060).strftime("%H:%M"))
            self.assertEqual(roles[0].last_timestamp, 1777860060)

    def test_load_and_update_character_preserves_runtime_files_and_cleans_removed_assets(self) -> None:
        with tempfile.TemporaryDirectory() as data_root, tempfile.TemporaryDirectory() as assets_root:
            image_path = Path(assets_root) / "avatar.png"
            image_path.write_bytes(b"png-bytes")
            creator = CharacterCreator(Path(data_root))
            result = creator.create(
                CharacterDraft(
                    brain_id="editable",
                    name="Editable",
                    description="Original intro",
                    avatar_path=str(image_path),
                    portraits={"neutral": str(image_path)},
                    age="19",
                    birthday="2000-01-01",
                    background="Original background",
                    personality_traits=["calm"],
                    interests=["music"],
                    memories=[MemoryDraft(content="Likes tea.", memory_type="preference", importance=1.4, context="seed")],
                )
            )
            brain_dir = result.brain_dir
            (brain_dir / "history" / "history.json").write_text(json.dumps({"marker": "history"}), encoding="utf-8")
            (brain_dir / "persona" / "state.json").write_text(json.dumps({"marker": "state"}), encoding="utf-8")
            (brain_dir / "tags" / "reply_tags.json").write_text(json.dumps({"marker": "tags"}), encoding="utf-8")
            (brain_dir / "config.json").write_text(json.dumps({"marker": "config"}), encoding="utf-8")

            profile_path = brain_dir / "persona" / "profile.json"
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["relationship_state"] = "warm"
            profile["relationship_score"] = 12.5
            profile["relationship_updated_at"] = 12345.0
            profile_path.write_text(json.dumps(profile), encoding="utf-8")

            ui_path = brain_dir / "ui.json"
            ui = json.loads(ui_path.read_text(encoding="utf-8"))
            ui["last_message"] = "recent"
            ui["last_time"] = "now"
            ui_path.write_text(json.dumps(ui), encoding="utf-8")

            memories_path = brain_dir / "persona" / "memories.json"
            memories = json.loads(memories_path.read_text(encoding="utf-8"))
            original_memory = memories["preference_memories"][0]
            memories["daily_summary_memories"] = [{"id": "daily", "content": "daily", "timestamp": 1.0, "memory_type": "daily_summary", "importance": 1.0, "context": None}]
            memories["monthly_summary_memories"] = [{"id": "monthly", "content": "monthly", "timestamp": 2.0, "memory_type": "monthly_summary", "importance": 1.0, "context": None}]
            memories_path.write_text(json.dumps(memories), encoding="utf-8")

            loaded = creator.load_draft("editable")
            self.assertEqual(loaded.name, "Editable")
            self.assertEqual(loaded.age, "19")
            self.assertEqual(loaded.birthday, "2000-01-01")
            self.assertEqual(loaded.background, "Original background")
            self.assertEqual(loaded.memories[0].memory_id, original_memory["id"])
            self.assertEqual(loaded.memories[0].timestamp, original_memory["timestamp"])

            loaded.name = "Edited"
            loaded.background = "Edited background"
            loaded.description = "Edited intro"
            loaded.accent_color = "#88A0C8"
            loaded.avatar_path = ""
            loaded.portraits.pop("neutral", None)
            loaded.memories[0].content = "Likes coffee."
            creator.update("editable", loaded)

            self.assertEqual(json.loads((brain_dir / "history" / "history.json").read_text(encoding="utf-8")), {"marker": "history"})
            self.assertEqual(json.loads((brain_dir / "persona" / "state.json").read_text(encoding="utf-8")), {"marker": "state"})
            self.assertEqual(json.loads((brain_dir / "tags" / "reply_tags.json").read_text(encoding="utf-8")), {"marker": "tags"})
            self.assertEqual(json.loads((brain_dir / "config.json").read_text(encoding="utf-8")), {"marker": "config"})

            updated_profile = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertEqual(updated_profile["name"], "Edited")
            self.assertEqual(updated_profile["background"], "Edited background")
            self.assertEqual(updated_profile["relationship_state"], "warm")
            self.assertEqual(updated_profile["relationship_score"], 12.5)

            updated_memories = json.loads(memories_path.read_text(encoding="utf-8"))
            self.assertEqual(updated_memories["preference_memories"][0]["id"], original_memory["id"])
            self.assertEqual(updated_memories["preference_memories"][0]["timestamp"], original_memory["timestamp"])
            self.assertEqual(updated_memories["preference_memories"][0]["content"], "Likes coffee.")
            self.assertEqual(updated_memories["daily_summary_memories"][0]["id"], "daily")
            self.assertEqual(updated_memories["monthly_summary_memories"][0]["id"], "monthly")

            updated_ui = json.loads(ui_path.read_text(encoding="utf-8"))
            self.assertEqual(updated_ui["last_message"], "recent")
            self.assertEqual(updated_ui["last_time"], "now")
            self.assertEqual(updated_ui["accent_color"], "#88A0C8")
            self.assertEqual(updated_ui["avatar"], "")
            self.assertEqual(updated_ui["standing_image"], "")
            self.assertEqual(updated_ui["portraits"], {})
            self.assertFalse((brain_dir / "assets" / "avatar.png").exists())
            self.assertFalse((brain_dir / "assets" / "portraits" / "neutral.png").exists())

            roles = load_roles_from_data(Path(data_root))
            self.assertEqual(roles[0].name, "Edited")
            self.assertEqual(roles[0].avatar_path, "")
            self.assertEqual(roles[0].standing_image_path, "")

    def test_update_changed_avatar_uses_versioned_path_to_bust_image_cache(self) -> None:
        with tempfile.TemporaryDirectory() as data_root, tempfile.TemporaryDirectory() as assets_root:
            old_image = Path(assets_root) / "old.png"
            old_image.write_bytes(b"old-png")
            new_image = Path(assets_root) / "new.png"
            new_image.write_bytes(b"new-png")
            creator = CharacterCreator(Path(data_root))
            result = creator.create(CharacterDraft(brain_id="cache_bust", name="Cache Bust", avatar_path=str(old_image)))
            brain_dir = result.brain_dir

            loaded = creator.load_draft("cache_bust")
            self.assertEqual(loaded.avatar_path, (brain_dir / "assets" / "avatar.png").as_posix())
            loaded.avatar_path = str(new_image)
            creator.update("cache_bust", loaded)

            ui = json.loads((brain_dir / "ui.json").read_text(encoding="utf-8"))
            self.assertRegex(ui["avatar"], r"^assets/avatar-[0-9a-f]{8}\.png$")
            self.assertTrue((brain_dir / ui["avatar"]).exists())
            self.assertFalse((brain_dir / "assets" / "avatar.png").exists())

            roles = load_roles_from_data(Path(data_root))
            self.assertEqual(roles[0].avatar_path, (brain_dir / ui["avatar"]).as_posix())

    def test_update_ignores_stale_versioned_portrait_keys(self) -> None:
        with tempfile.TemporaryDirectory() as data_root, tempfile.TemporaryDirectory() as assets_root:
            old_image = Path(assets_root) / "old.png"
            old_image.write_bytes(b"old-png")
            new_image = Path(assets_root) / "new.png"
            new_image.write_bytes(b"new-png")
            creator = CharacterCreator(Path(data_root))
            result = creator.create(
                CharacterDraft(
                    brain_id="portrait_cache",
                    name="Portrait Cache",
                    portraits={"neutral": str(old_image)},
                )
            )
            brain_dir = result.brain_dir

            loaded = creator.load_draft("portrait_cache")
            loaded.portraits["neutral"] = str(new_image)
            loaded.portraits["neutral-deadbeef"] = (brain_dir / "assets" / "portraits" / "neutral-deadbeef.png").as_posix()
            creator.update("portrait_cache", loaded)

            ui = json.loads((brain_dir / "ui.json").read_text(encoding="utf-8"))
            self.assertEqual(set(ui["portraits"]), {"neutral"})
            self.assertRegex(ui["portraits"]["neutral"], r"^assets/portraits/neutral-[0-9a-f]{8}\.png$")

            reloaded = creator.load_draft("portrait_cache")
            self.assertEqual(set(reloaded.portraits), {"neutral"})

    def test_template_creation_only_inherits_config_profile_and_style_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as data_root:
            data_dir = Path(data_root)
            template_dir = data_dir / "template"
            (template_dir / "persona").mkdir(parents=True)
            (template_dir / "history").mkdir()
            (template_dir / "assets").mkdir()
            (template_dir / "session" / "current").mkdir(parents=True)

            (template_dir / "config.json").write_text(
                json.dumps({"response": {"max_tokens": 777, "max_sentences": 3}}),
                encoding="utf-8",
            )
            (template_dir / "persona" / "profile.json").write_text(
                json.dumps({"name": "Template", "background": "template background", "personality_traits": ["template_trait"]}),
                encoding="utf-8",
            )
            (template_dir / "persona" / "speaking_style.json").write_text(
                json.dumps(
                    {
                        "base_style": {"question_rate": 0.77, "sentence_length": "long"},
                        "influence_weight": 0.33,
                        "custom_modifiers": {},
                    }
                ),
                encoding="utf-8",
            )
            (template_dir / "persona" / "memories.json").write_text(json.dumps({"episodic_memories": [{"id": "copy-me"}]}), encoding="utf-8")
            (template_dir / "history" / "history.json").write_text(json.dumps({"marker": "copy-me"}), encoding="utf-8")
            (template_dir / "assets" / "avatar.png").write_bytes(b"template-avatar")
            (template_dir / "session" / "current" / "state.json").write_text("copy-me", encoding="utf-8")

            result = CharacterCreator(data_dir).create(
                CharacterDraft(brain_id="from_template", template="template", name="From Template")
            )
            brain_dir = result.brain_dir

            self.assertEqual(json.loads((brain_dir / "config.json").read_text(encoding="utf-8"))["response"]["max_tokens"], 777)
            profile = json.loads((brain_dir / "persona" / "profile.json").read_text(encoding="utf-8"))
            self.assertEqual(profile["background"], "template background")
            self.assertEqual(profile["personality_traits"], ["template_trait"])
            style = json.loads((brain_dir / "persona" / "speaking_style.json").read_text(encoding="utf-8"))
            self.assertEqual(style["base_style"]["question_rate"], 0.77)
            self.assertEqual(style["influence_weight"], 0.33)

            memories = json.loads((brain_dir / "persona" / "memories.json").read_text(encoding="utf-8"))
            self.assertEqual(memories["episodic_memories"], [])
            history = json.loads((brain_dir / "history" / "history.json").read_text(encoding="utf-8"))
            self.assertNotIn("marker", history)
            self.assertFalse((brain_dir / "session" / "current" / "state.json").exists())
            self.assertFalse((brain_dir / "assets" / "avatar.png").exists())


if __name__ == "__main__":
    unittest.main()
