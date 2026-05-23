#!/usr/bin/env python3
"""Tests for the thin GUI control layer."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

TEST_FILE = Path(__file__).resolve()
SRC_DIR = TEST_FILE.parents[2]
REPO_ROOT = TEST_FILE.parents[3]

for path in (str(REPO_ROOT), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from GUI.control import (
    AMADUES_BRAIN_ID,
    AMADUES_UI_ROLE_ID,
    DEEPSEEK_PROVIDER,
    DEEPSEEK_V4_FLASH_MODEL,
    DEEPSEEK_V4_PRO_MODEL,
    DEFAULT_KEY_SOURCE_ENV,
    KEY_BRAIN_ID,
    KEY_DEFAULT_BACKGROUND,
    KEY_DOCTORATE_MEMORY_CONTENT,
    KEY_DOCTORATE_MEMORY_ID,
    KEY_PROJECT_MEMORY_CONTENT,
    MINIMAX_MODEL,
    MINIMAX_PROVIDER,
    AmaduesController,
    AmaduesRuntime,
    UiSettingsStorage,
    _load_model_config,
    build_amadues_runtime,
    ensure_default_startup_data,
)
from GUI.character_creator import PORTRAIT_EDIT_FILE, CharacterCreator
from GUI.interfaces import CharacterDraft, ChatMessage, CompanionRole, CompanionUIView, UiSettings
from GUI.role_loader import load_roles_from_data
from agent_core.api.adapter import APIProvider, AdapterRegistry
from agent_core.models import get_model_catalog
from agent_core.session.path_resolver import PathResolver


class StubView(CompanionUIView):
    def __init__(self) -> None:
        self.roles: list[CompanionRole] = []
        self.active_role_id = ""
        self.messages: list[ChatMessage] = []
        self.role_messages: dict[str, list[ChatMessage]] = {}
        self.appended: list[ChatMessage] = []
        self.updated: list[tuple[str, str, bool]] = []
        self.typing_states: list[bool] = []
        self.syncing_states: list[bool] = []
        self.reply_emotions: list[tuple[str, str]] = []
        self.applied_settings: UiSettings | None = None
        self.pages: list[str] = []
        self.notices: list[tuple[str, bool]] = []

    def set_roles(self, roles: list[CompanionRole]) -> None:
        self.roles = roles

    def set_active_role(self, role_id: str) -> None:
        self.active_role_id = role_id

    def set_messages(self, messages: list[ChatMessage]) -> None:
        self.messages = list(messages)

    def set_role_messages(self, role_id: str, messages: list[ChatMessage]) -> None:
        self.role_messages[role_id] = list(messages)

    def append_message(self, message: ChatMessage) -> None:
        self.appended.append(message)

    def update_message_text(self, message_id: str, text: str, is_streaming: bool = False) -> None:
        self.updated.append((message_id, text, is_streaming))
        for message in self.appended:
            if message.id == message_id:
                message.text = text
                message.is_streaming = is_streaming
                break

    def set_typing(self, visible: bool) -> None:
        self.typing_states.append(visible)

    def set_syncing(self, visible: bool) -> None:
        self.syncing_states.append(visible)

    def set_reply_emotion(self, role_id: str, emotion: str) -> None:
        self.reply_emotions.append((role_id, emotion))

    def apply_settings(self, settings: UiSettings) -> None:
        self.applied_settings = settings

    def show_page(self, page: str) -> None:
        self.pages.append(page)

    def clear_chat(self) -> None:
        self.messages = []

    def show_notice(self, message: str, is_error: bool = False) -> None:
        self.notices.append((message, is_error))


class DispatchRecordingView(StubView):
    def __init__(self) -> None:
        super().__init__()
        self.dispatch_count = 0

    def dispatch_ui(self, callback) -> None:
        self.dispatch_count += 1
        callback()


class FakeSessionStorage:
    def __init__(self, messages: list[object] | None = None) -> None:
        self._messages = messages or []

    def get_today_messages(self) -> list[object]:
        return list(self._messages)


class FakeSessionManager:
    def __init__(
        self,
        messages: list[object] | None = None,
        reply: dict | None = None,
        stream_deltas: list[str] | None = None,
    ) -> None:
        self.storage = FakeSessionStorage(messages)
        self.reply = reply or {
            "message_id": "assistant-1",
            "content": "stub reply",
            "tag": SimpleNamespace(emotion="neutral"),
        }
        self.stream_deltas = stream_deltas
        self.sent: list[tuple[str, object]] = []
        self.switched: list[str] = []

    def send_message_sync(self, user_message: str, emotion: object = None) -> dict:
        self.sent.append((user_message, emotion))
        return dict(self.reply)

    def send_message_stream(self, user_message: str, emotion: object = None):
        self.sent.append((user_message, emotion))
        content = str(self.reply.get("content", ""))
        if self.stream_deltas is None:
            midpoint = max(1, len(content) // 2)
            deltas = [content[:midpoint], content[midpoint:]]
        else:
            deltas = self.stream_deltas
        for delta in deltas:
            if delta:
                yield {"type": "delta", "delta": delta}
        yield {"type": "done", **dict(self.reply)}

    def switch_brain(self, brain_id: str) -> None:
        self.switched.append(brain_id)


class FakeBrainRegistry:
    def __init__(self, brain_ids: list[str], current: str = AMADUES_BRAIN_ID) -> None:
        self._brain_ids = brain_ids
        self._current = current

    def list_brains(self) -> list[str]:
        return list(self._brain_ids)

    def current_brain_id(self) -> str:
        return self._current

    def get_brain_info(self, brain_id: str) -> SimpleNamespace | None:
        if brain_id not in self._brain_ids:
            return None
        return SimpleNamespace(id=brain_id, name=brain_id.title(), description=f"{brain_id} description")


class GuiControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = {
            PathResolver.ENV_DATA_DIR: os.environ.get(PathResolver.ENV_DATA_DIR),
            PathResolver.ENV_CONFIG_DIR: os.environ.get(PathResolver.ENV_CONFIG_DIR),
            PathResolver.ENV_FLET_DATA_DIR: os.environ.get(PathResolver.ENV_FLET_DATA_DIR),
            DEFAULT_KEY_SOURCE_ENV: os.environ.get(DEFAULT_KEY_SOURCE_ENV),
        }
        for env_name in self._env_backup:
            os.environ.pop(env_name, None)
        self._data_tmp = tempfile.TemporaryDirectory()
        os.environ[PathResolver.ENV_DATA_DIR] = self._data_tmp.name

    def tearDown(self) -> None:
        self._data_tmp.cleanup()
        for env_name, env_value in self._env_backup.items():
            if env_value is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = env_value

    def test_ui_settings_storage_splits_chat_and_ui_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as config_dir:
            storage = UiSettingsStorage(config_dir)
            settings = UiSettings(
                is_dark=False,
                token_quality=80,
                model_provider=MINIMAX_PROVIDER,
                model_name=MINIMAX_MODEL,
                api_key="test-key",
                user_name="Tester",
                user_avatar_path="avatar.png",
            )

            storage.save_minimax_config(settings.api_key)
            storage.save_ui_settings(settings)

            chat_config = storage.load_chat_config()
            provider = chat_config.providers[MINIMAX_PROVIDER]
            self.assertEqual(chat_config.default_provider, MINIMAX_PROVIDER)
            self.assertEqual(chat_config.default_model, MINIMAX_MODEL)
            self.assertEqual(provider.api_key, "test-key")
            self.assertEqual(provider.api_type, "openai")
            self.assertTrue(provider.auth_header)

            ui_payload = json.loads((Path(config_dir) / "ui_settings.json").read_text(encoding="utf-8"))
            self.assertNotIn("api_key", ui_payload)
            self.assertEqual(ui_payload["user_name"], "Tester")
            self.assertEqual(ui_payload["model_provider"], MINIMAX_PROVIDER)
            self.assertEqual(ui_payload["model_name"], MINIMAX_MODEL)

            loaded = storage.load_ui_settings()
            self.assertFalse(loaded.is_dark)
            self.assertEqual(loaded.token_quality, 80)
            self.assertEqual(loaded.model_provider, MINIMAX_PROVIDER)
            self.assertEqual(loaded.model_name, MINIMAX_MODEL)
            self.assertEqual(loaded.api_key, "test-key")
            self.assertEqual(loaded.user_name, "Tester")
            self.assertEqual(loaded.user_avatar_path, "avatar.png")

    def test_ui_settings_storage_persists_deepseek_model_choice(self) -> None:
        with tempfile.TemporaryDirectory() as config_dir:
            storage = UiSettingsStorage(config_dir)
            settings = UiSettings(
                is_dark=True,
                token_quality=60,
                model_provider=DEEPSEEK_PROVIDER,
                model_name=DEEPSEEK_V4_PRO_MODEL,
                api_key="deepseek-key",
                user_name="Tester",
            )

            storage.save_provider_config(settings.model_provider, settings.api_key, settings.model_name)
            storage.save_ui_settings(settings)

            chat_config = storage.load_chat_config()
            provider = chat_config.providers[DEEPSEEK_PROVIDER]
            self.assertEqual(chat_config.default_provider, DEEPSEEK_PROVIDER)
            self.assertEqual(chat_config.default_model, DEEPSEEK_V4_PRO_MODEL)
            self.assertEqual(provider.base_url, "https://api.deepseek.com")
            self.assertEqual(provider.api_key, "deepseek-key")
            self.assertEqual(provider.api_type, "openai")
            self.assertTrue(provider.auth_header)

            loaded = storage.load_ui_settings()
            self.assertEqual(loaded.model_provider, DEEPSEEK_PROVIDER)
            self.assertEqual(loaded.model_name, DEEPSEEK_V4_PRO_MODEL)
            self.assertEqual(loaded.api_key, "deepseek-key")

            model_config = _load_model_config(config_dir)
            self.assertEqual(model_config.provider, APIProvider.DEEPSEEK)
            self.assertEqual(model_config.name, DEEPSEEK_V4_PRO_MODEL)
            self.assertEqual(model_config.base_url, "https://api.deepseek.com")

    def test_deepseek_catalog_and_adapter_are_registered(self) -> None:
        catalog = get_model_catalog(DEEPSEEK_PROVIDER)

        self.assertIsNotNone(catalog)
        self.assertIsNotNone(catalog.find_model(DEEPSEEK_V4_FLASH_MODEL))
        self.assertIsNotNone(catalog.find_model(DEEPSEEK_V4_PRO_MODEL))
        self.assertEqual(AdapterRegistry.get(APIProvider.DEEPSEEK).__class__.__name__, "OpenAIAdapter")

    def test_build_amadues_runtime_raises_when_no_brain_exists(self) -> None:
        with tempfile.TemporaryDirectory() as config_dir, tempfile.TemporaryDirectory() as data_dir:
            os.environ[PathResolver.ENV_CONFIG_DIR] = config_dir
            os.environ[PathResolver.ENV_DATA_DIR] = data_dir

            storage = UiSettingsStorage(config_dir)
            storage.save_minimax_config("runtime-key")

            with self.assertRaisesRegex(RuntimeError, "No brains found"):
                build_amadues_runtime(config_dir=config_dir)

            self.assertEqual(list(Path(data_dir).iterdir()), [])

    def test_build_amadues_runtime_defaults_to_key(self) -> None:
        with tempfile.TemporaryDirectory() as config_dir, tempfile.TemporaryDirectory() as data_dir:
            os.environ[PathResolver.ENV_CONFIG_DIR] = config_dir
            os.environ[PathResolver.ENV_DATA_DIR] = data_dir

            storage = UiSettingsStorage(config_dir)
            storage.save_minimax_config("runtime-key")

            for brain_id, name in ((AMADUES_BRAIN_ID, "Amadues"), (KEY_BRAIN_ID, "Key")):
                persona_dir = Path(data_dir) / brain_id / "persona"
                persona_dir.mkdir(parents=True)
                (persona_dir / "profile.json").write_text(
                    json.dumps({"name": name, "background": f"{name} background"}),
                    encoding="utf-8",
                )
                (persona_dir / "memories.json").write_text(
                    json.dumps(
                        {
                            "episodic_memories": [],
                            "preference_memories": [],
                            "fact_memories": [],
                        }
                    ),
                    encoding="utf-8",
                )

            runtime = build_amadues_runtime(config_dir=config_dir)

            self.assertEqual(runtime.brain_registry.current_brain_id(), KEY_BRAIN_ID)

    def test_default_startup_data_copies_key_seed(self) -> None:
        with tempfile.TemporaryDirectory() as seed_dir:
            seed_root = Path(seed_dir)
            (seed_root / "persona").mkdir(parents=True)
            (seed_root / "assets" / "portraits").mkdir(parents=True)
            (seed_root / "tags").mkdir(parents=True)
            (seed_root / "persona" / "profile.json").write_text(
                json.dumps({"name": "健", "background": "seed background"}, ensure_ascii=False),
                encoding="utf-8",
            )
            (seed_root / "persona" / "memories.json").write_text(
                json.dumps(
                    {
                        "episodic_memories": [],
                        "preference_memories": [],
                        "fact_memories": [],
                    }
                ),
                encoding="utf-8",
            )
            (seed_root / "ui.json").write_text(
                json.dumps(
                    {
                        "type": "Custom",
                        "avatar": "assets/avatar.png",
                        "portraits": {"neutral": "assets/portraits/neutral-abc123.png"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (seed_root / "assets" / "avatar.png").write_bytes(b"avatar")
            (seed_root / "assets" / "portraits" / "neutral-abc123.png").write_bytes(b"portrait")
            os.environ[DEFAULT_KEY_SOURCE_ENV] = seed_dir

            ensure_default_startup_data()

        profile_path = Path(self._data_tmp.name) / KEY_BRAIN_ID / "persona" / "profile.json"
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        ui_path = Path(self._data_tmp.name) / KEY_BRAIN_ID / "ui.json"
        ui_data = json.loads(ui_path.read_text(encoding="utf-8"))
        memories_path = Path(self._data_tmp.name) / KEY_BRAIN_ID / "persona" / "memories.json"
        memories = json.loads(memories_path.read_text(encoding="utf-8"))

        self.assertEqual(profile["name"], "健")
        self.assertEqual(profile["background"], KEY_DEFAULT_BACKGROUND)
        self.assertEqual(memories["fact_memories"], [])
        self.assertEqual(ui_data["portraits"]["neutral"], "assets/portraits/neutral-abc123.png")
        self.assertTrue((Path(self._data_tmp.name) / KEY_BRAIN_ID / "assets" / "avatar.png").exists())
        self.assertTrue(
            (Path(self._data_tmp.name) / KEY_BRAIN_ID / "assets" / "portraits" / "neutral-abc123.png").exists()
        )

    def test_default_startup_data_uses_packaged_key_seed_without_windows_path(self) -> None:
        ensure_default_startup_data()

        key_dir = Path(self._data_tmp.name) / KEY_BRAIN_ID
        packaged_key_dir = REPO_ROOT / "resource" / KEY_BRAIN_ID
        profile = json.loads((key_dir / "persona" / "profile.json").read_text(encoding="utf-8"))
        memories = json.loads((key_dir / "persona" / "memories.json").read_text(encoding="utf-8"))
        ui_data = json.loads((key_dir / "ui.json").read_text(encoding="utf-8"))
        edit_data = json.loads((key_dir / PORTRAIT_EDIT_FILE).read_text(encoding="utf-8"))

        self.assertEqual(profile["name"], "\u5065")
        self.assertEqual(profile["background"], KEY_DEFAULT_BACKGROUND)
        episodic_contents = [memory["content"] for memory in memories["episodic_memories"]]
        self.assertIn("第一次见面时，会比较紧张", episodic_contents)
        fact_contents = [memory["content"] for memory in memories["fact_memories"]]
        self.assertIn("在一切的根部，我们彼此相连", fact_contents)
        self.assertIn(KEY_PROJECT_MEMORY_CONTENT, fact_contents)
        self.assertIn(KEY_DOCTORATE_MEMORY_CONTENT, fact_contents)
        self.assertNotIn("在院士门下读博，全年午休，半夜回到寝室打游戏", fact_contents)
        self.assertEqual(ui_data["avatar"], "assets/avatar.png")
        self.assertEqual(ui_data["portraits"]["happy"], "assets/portraits/happy-3dd92ea1.png")
        self.assertEqual(ui_data["portraits"]["neutral"], "assets/portraits/neutral-640321d0.png")
        self.assertNotIn("portrait_sources", ui_data)
        self.assertNotIn("portrait_layout", ui_data)
        self.assertEqual(edit_data["version"], 1)
        self.assertEqual(edit_data["edits"]["neutral"]["source_path"], "assets/portrait_sources/neutral-640321d0.png")
        self.assertEqual(edit_data["edits"]["neutral"]["processed_path"], "assets/portraits/neutral-640321d0.png")
        self.assertEqual(edit_data["edits"]["neutral"]["render_mode"], "cutout")
        self.assertEqual(edit_data["edits"]["neutral"]["scale"], 1.0)
        serialized_ui = json.dumps(ui_data, ensure_ascii=False)
        serialized_edits = json.dumps(edit_data, ensure_ascii=False)
        self.assertNotIn("D:\\", serialized_ui)
        self.assertNotIn("AppData", serialized_ui)
        self.assertNotIn("D:\\", serialized_edits)
        self.assertNotIn("AppData", serialized_edits)
        self.assertEqual((key_dir / "assets" / "avatar.png").read_bytes(), (packaged_key_dir / "assets" / "avatar.png").read_bytes())
        self.assertEqual(
            (key_dir / "assets" / "portrait_sources" / "neutral-640321d0.png").read_bytes(),
            (packaged_key_dir / "assets" / "portrait_sources" / "neutral-640321d0.png").read_bytes(),
        )
        self.assertFalse((Path(self._data_tmp.name) / AMADUES_BRAIN_ID).exists())

    def test_default_startup_data_does_not_create_key_when_other_roles_exist(self) -> None:
        data_dir = Path(self._data_tmp.name)
        CharacterCreator(data_dir).create(CharacterDraft(brain_id="custom", name="Custom"))

        result = ensure_default_startup_data()

        self.assertEqual(result, data_dir / "custom")
        self.assertTrue((data_dir / "custom").exists())
        self.assertFalse((data_dir / KEY_BRAIN_ID).exists())

    def test_default_startup_data_repairs_legacy_key_with_amadues_assets(self) -> None:
        key_dir = Path(self._data_tmp.name) / KEY_BRAIN_ID
        (key_dir / "assets" / "portraits").mkdir(parents=True)
        (key_dir / "persona").mkdir(parents=True)
        shutil.copy2(REPO_ROOT / "resource" / "amadues.png", key_dir / "assets" / "avatar.png")
        shutil.copy2(REPO_ROOT / "resource" / "amadues_Full_profile.png", key_dir / "assets" / "portraits" / "neutral.png")
        (key_dir / "persona" / "profile.json").write_text(json.dumps({"name": "bad"}), encoding="utf-8")
        (key_dir / "ui.json").write_text(
            json.dumps({"avatar": "assets/avatar.png", "portraits": {"neutral": "assets/portraits/neutral.png"}}),
            encoding="utf-8",
        )

        ensure_default_startup_data()

        packaged_key_dir = REPO_ROOT / "resource" / KEY_BRAIN_ID
        ui_data = json.loads((key_dir / "ui.json").read_text(encoding="utf-8"))
        self.assertEqual(ui_data["portraits"]["neutral"], "assets/portraits/neutral-640321d0.png")
        self.assertEqual((key_dir / "assets" / "avatar.png").read_bytes(), (packaged_key_dir / "assets" / "avatar.png").read_bytes())

    def test_default_startup_data_repairs_key_missing_packaged_portrait_assets(self) -> None:
        key_dir = Path(self._data_tmp.name) / KEY_BRAIN_ID
        (key_dir / "persona").mkdir(parents=True)
        (key_dir / "persona" / "profile.json").write_text(json.dumps({"name": "Key"}), encoding="utf-8")
        (key_dir / "persona" / "memories.json").write_text(
            json.dumps({"episodic_memories": [], "preference_memories": [], "fact_memories": []}),
            encoding="utf-8",
        )
        (key_dir / "ui.json").write_text(
            json.dumps(
                {
                    "avatar": "assets/avatar.png",
                    "standing_image": "assets/portraits/neutral-640321d0.png",
                    "portraits": {"neutral": "assets/portraits/neutral-640321d0.png"},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        ensure_default_startup_data()

        packaged_key_dir = REPO_ROOT / "resource" / KEY_BRAIN_ID
        self.assertEqual(
            (key_dir / "assets" / "portraits" / "neutral-640321d0.png").read_bytes(),
            (packaged_key_dir / "assets" / "portraits" / "neutral-640321d0.png").read_bytes(),
        )
        self.assertTrue((key_dir / "assets" / "portraits" / "happy-3dd92ea1.png").exists())

    def test_default_startup_data_does_not_rewrite_existing_key_project_memory(self) -> None:
        key_dir = Path(self._data_tmp.name) / KEY_BRAIN_ID
        (key_dir / "persona").mkdir(parents=True)
        (key_dir / "persona" / "profile.json").write_text(json.dumps({"name": "健"}), encoding="utf-8")
        (key_dir / "persona" / "memories.json").write_text(
            json.dumps(
                {
                    "episodic_memories": [],
                    "preference_memories": [],
                    "fact_memories": [
                        {
                            "id": "mem_5_1778516483",
                            "content": "在一个“项目“中，把自己的消息输入给了ai，制作了健。",
                            "timestamp": 1778516483.315087,
                            "memory_type": "fact",
                            "importance": 1.0,
                            "context": "背景",
                        },
                        {
                            "id": "custom",
                            "content": "保留用户后续写入的记忆。",
                            "memory_type": "fact",
                            "importance": 1.0,
                            "context": "背景",
                        },
                    ],
                    "daily_summary_memories": [],
                    "monthly_summary_memories": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        ensure_default_startup_data()

        memories = json.loads((key_dir / "persona" / "memories.json").read_text(encoding="utf-8"))
        contents = [memory["content"] for memory in memories["fact_memories"]]
        self.assertNotIn(KEY_PROJECT_MEMORY_CONTENT, contents)
        self.assertIn("保留用户后续写入的记忆。", contents)
        self.assertIn("在一个“项目“中，把自己的消息输入给了ai，制作了健。", contents)

    def test_default_startup_data_does_not_rewrite_existing_key_doctorate_memory(self) -> None:
        key_dir = Path(self._data_tmp.name) / KEY_BRAIN_ID
        (key_dir / "persona").mkdir(parents=True)
        (key_dir / "persona" / "profile.json").write_text(json.dumps({"name": "健"}), encoding="utf-8")
        (key_dir / "persona" / "memories.json").write_text(
            json.dumps(
                {
                    "episodic_memories": [],
                    "preference_memories": [],
                    "fact_memories": [
                        {
                            "id": KEY_DOCTORATE_MEMORY_ID,
                            "content": "在院士门下读博，全年午休，半夜回到寝室打游戏",
                            "timestamp": 1778516483.315087,
                            "memory_type": "fact",
                            "importance": 1.0,
                            "context": "背景",
                        },
                        {
                            "id": "custom",
                            "content": "保留用户后续写入的记忆。",
                            "memory_type": "fact",
                            "importance": 1.0,
                            "context": "背景",
                        },
                    ],
                    "daily_summary_memories": [],
                    "monthly_summary_memories": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        ensure_default_startup_data()

        memories = json.loads((key_dir / "persona" / "memories.json").read_text(encoding="utf-8"))
        contents = [memory["content"] for memory in memories["fact_memories"]]
        self.assertNotIn(KEY_DOCTORATE_MEMORY_CONTENT, contents)
        self.assertIn("保留用户后续写入的记忆。", contents)
        self.assertIn("在院士门下读博，全年午休，半夜回到寝室打游戏", contents)

    def test_default_startup_data_does_not_add_missing_packaged_key_memories(self) -> None:
        key_dir = Path(self._data_tmp.name) / KEY_BRAIN_ID
        (key_dir / "persona").mkdir(parents=True)
        (key_dir / "persona" / "profile.json").write_text(json.dumps({"name": "健"}), encoding="utf-8")
        (key_dir / "persona" / "memories.json").write_text(
            json.dumps(
                {
                    "episodic_memories": [],
                    "preference_memories": [
                        {
                            "id": "mem_1_1778516483",
                            "content": "旧的喜好记忆。",
                            "timestamp": 1778516483.315087,
                            "memory_type": "preference",
                            "importance": 0.1,
                            "context": "旧上下文",
                        },
                        {
                            "id": "custom",
                            "content": "保留用户后续写入的喜好。",
                            "memory_type": "preference",
                            "importance": 1.0,
                            "context": "喜好",
                        },
                    ],
                    "fact_memories": [
                        {
                            "id": "mem_6_1778516483",
                            "content": "旧的事实记忆。",
                            "timestamp": 1778516483.315087,
                            "memory_type": "fact",
                            "importance": 0.1,
                            "context": "旧上下文",
                        }
                    ],
                    "daily_summary_memories": [],
                    "monthly_summary_memories": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        ensure_default_startup_data()

        memories = json.loads((key_dir / "persona" / "memories.json").read_text(encoding="utf-8"))
        episodic_contents = [memory["content"] for memory in memories["episodic_memories"]]
        preference_contents = [memory["content"] for memory in memories["preference_memories"]]
        fact_contents = [memory["content"] for memory in memories["fact_memories"]]
        self.assertNotIn("在一切的根部，我们彼此相连", episodic_contents)
        self.assertNotIn("第一次见面时，会比较紧张", episodic_contents)
        self.assertIn("旧的喜好记忆。", preference_contents)
        self.assertIn("保留用户后续写入的喜好。", preference_contents)
        self.assertIn("旧的事实记忆。", fact_contents)
        self.assertNotIn("身体很差，且表现出一直很困的样子", fact_contents)

    def test_bind_view_keeps_roles_empty_when_data_directory_has_no_brain(self) -> None:
        with tempfile.TemporaryDirectory() as config_dir, tempfile.TemporaryDirectory() as data_dir:
            os.environ[PathResolver.ENV_CONFIG_DIR] = config_dir
            os.environ[PathResolver.ENV_DATA_DIR] = data_dir

            controller = AmaduesController(settings_storage=UiSettingsStorage(config_dir))
            view = StubView()
            controller.bind_view(view)

            self.assertEqual(view.roles, [])

    def test_loading_roles_does_not_create_missing_data_directory(self) -> None:
        with tempfile.TemporaryDirectory() as parent_dir:
            data_dir = Path(parent_dir) / "missing-data"

            roles = load_roles_from_data(data_dir)

            self.assertEqual(roles, [])
            self.assertFalse(data_dir.exists())

    def test_bind_view_loads_roles_from_data_directory(self) -> None:
        with tempfile.TemporaryDirectory() as config_dir, tempfile.TemporaryDirectory() as data_dir:
            os.environ[PathResolver.ENV_CONFIG_DIR] = config_dir
            os.environ[PathResolver.ENV_DATA_DIR] = data_dir

            for brain_id, name in ((AMADUES_BRAIN_ID, "Amadeus"), ("shinji", "碇真嗣")):
                brain_dir = Path(data_dir) / brain_id
                persona_dir = brain_dir / "persona"
                portrait_dir = brain_dir / "assets" / "portraits"
                persona_dir.mkdir(parents=True)
                portrait_dir.mkdir(parents=True)
                (brain_dir / "assets" / "avatar.png").write_bytes(b"avatar")
                (portrait_dir / "neutral.png").write_bytes(b"portrait")
                (persona_dir / "profile.json").write_text(
                    json.dumps({"name": name, "background": f"{name} background"}, ensure_ascii=False),
                    encoding="utf-8",
                )
                (persona_dir / "memories.json").write_text(
                    json.dumps(
                        {
                            "episodic_memories": [],
                            "preference_memories": [],
                            "fact_memories": [],
                        }
                    ),
                    encoding="utf-8",
                )
                (brain_dir / "ui.json").write_text(
                    json.dumps(
                        {
                            "type": "test",
                            "tags": ["data"],
                            "avatar": "assets/avatar.png",
                            "portraits": {"neutral": "assets/portraits/neutral.png"},
                            "accent_color": "#123456",
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )

            controller = AmaduesController(settings_storage=UiSettingsStorage(config_dir))
            view = StubView()
            controller.bind_view(view)

            self.assertEqual([role.id for role in view.roles], [AMADUES_BRAIN_ID, "shinji"])
            shinji = next(role for role in view.roles if role.id == "shinji")
            self.assertEqual(shinji.name, "碇真嗣")
            self.assertEqual(shinji.portraits["neutral"], (Path(data_dir) / "shinji" / "assets" / "portraits" / "neutral.png").as_posix())
            self.assertEqual(shinji.standing_image_path, shinji.portraits["neutral"])

    def test_load_roles_ignores_missing_portrait_paths(self) -> None:
        with tempfile.TemporaryDirectory() as data_dir:
            brain_dir = Path(data_dir) / "role"
            persona_dir = brain_dir / "persona"
            portrait_dir = brain_dir / "assets" / "portraits"
            persona_dir.mkdir(parents=True)
            portrait_dir.mkdir(parents=True)
            (portrait_dir / "standing.png").write_bytes(b"standing")
            (persona_dir / "profile.json").write_text(
                json.dumps({"name": "Role", "background": "Role background"}),
                encoding="utf-8",
            )
            (persona_dir / "memories.json").write_text(
                json.dumps({"episodic_memories": [], "preference_memories": [], "fact_memories": []}),
                encoding="utf-8",
            )
            (brain_dir / "ui.json").write_text(
                json.dumps(
                    {
                        "portraits": {"neutral": "assets/portraits/missing.png"},
                        "standing_image": "assets/portraits/standing.png",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            role = load_roles_from_data(Path(data_dir))[0]

        self.assertNotIn("neutral", role.portraits)
        self.assertEqual(role.standing_image_path, (Path(data_dir) / "role" / "assets" / "portraits" / "standing.png").as_posix())

    def test_character_create_writes_data_refreshes_roles_and_selects_new_role(self) -> None:
        with tempfile.TemporaryDirectory() as config_dir, tempfile.TemporaryDirectory() as data_dir:
            os.environ[PathResolver.ENV_CONFIG_DIR] = config_dir
            os.environ[PathResolver.ENV_DATA_DIR] = data_dir

            controller = AmaduesController(settings_storage=UiSettingsStorage(config_dir))
            controller._runtime = object()
            view = StubView()
            controller.bind_view(view)

            draft = CharacterDraft(
                brain_id="new_role",
                name="New Role",
                description="A newly created role.",
            )
            controller.on_character_create_requested(draft)

            self.assertTrue((Path(data_dir) / "new_role" / "ui.json").exists())
            self.assertIn("new_role", [role.id for role in view.roles])
            self.assertEqual(view.active_role_id, "new_role")
            self.assertIsNone(controller._runtime)
            self.assertEqual(view.pages[-1], "home")
            self.assertTrue(view.notices)
            self.assertFalse(view.notices[-1][1])

    def test_character_create_validation_failure_keeps_runtime_and_reports_notice(self) -> None:
        with tempfile.TemporaryDirectory() as config_dir, tempfile.TemporaryDirectory() as data_dir:
            os.environ[PathResolver.ENV_CONFIG_DIR] = config_dir
            os.environ[PathResolver.ENV_DATA_DIR] = data_dir

            controller = AmaduesController(settings_storage=UiSettingsStorage(config_dir))
            runtime = object()
            controller._runtime = runtime
            view = StubView()
            controller.bind_view(view)

            controller.on_character_create_requested(CharacterDraft(brain_id="../bad", name="Bad"))

            self.assertIs(controller._runtime, runtime)
            self.assertEqual(view.pages, [])
            self.assertTrue(view.notices[-1][1])
            self.assertFalse(any(Path(data_dir).iterdir()))

    def test_character_delete_removes_role_refreshes_roles_and_selects_remaining_role(self) -> None:
        with tempfile.TemporaryDirectory() as config_dir, tempfile.TemporaryDirectory() as data_dir:
            os.environ[PathResolver.ENV_CONFIG_DIR] = config_dir
            os.environ[PathResolver.ENV_DATA_DIR] = data_dir
            creator = CharacterCreator(Path(data_dir))
            creator.create(CharacterDraft(brain_id="alpha", name="Alpha"))
            creator.create(CharacterDraft(brain_id="beta", name="Beta"))

            controller = AmaduesController(settings_storage=UiSettingsStorage(config_dir))
            controller._runtime = object()
            view = StubView()
            controller.bind_view(view)
            view.set_active_role("beta")

            deleted = controller.on_character_delete_requested("beta")

            self.assertTrue(deleted)
            self.assertFalse((Path(data_dir) / "beta").exists())
            self.assertEqual([role.id for role in view.roles], ["alpha"])
            self.assertEqual(view.active_role_id, "alpha")
            self.assertIsNone(controller._runtime)
            self.assertEqual(view.pages[-1], "home")
            self.assertFalse(view.notices[-1][1])

    def test_character_delete_keeps_last_remaining_role(self) -> None:
        with tempfile.TemporaryDirectory() as config_dir, tempfile.TemporaryDirectory() as data_dir:
            os.environ[PathResolver.ENV_CONFIG_DIR] = config_dir
            os.environ[PathResolver.ENV_DATA_DIR] = data_dir
            CharacterCreator(Path(data_dir)).create(CharacterDraft(brain_id="solo", name="Solo"))

            controller = AmaduesController(settings_storage=UiSettingsStorage(config_dir))
            runtime = object()
            controller._runtime = runtime
            view = StubView()
            controller.bind_view(view)

            deleted = controller.on_character_delete_requested("solo")

            self.assertFalse(deleted)
            self.assertTrue((Path(data_dir) / "solo").exists())
            self.assertEqual([role.id for role in view.roles], ["solo"])
            self.assertIs(controller._runtime, runtime)
            self.assertTrue(view.notices[-1][1])

    def test_open_chat_without_api_key_injects_notice_message(self) -> None:
        with tempfile.TemporaryDirectory() as config_dir:
            controller = AmaduesController(settings_storage=UiSettingsStorage(config_dir))
            view = StubView()
            controller.bind_view(view)

            controller.on_open_chat(AMADUES_UI_ROLE_ID)
            controller.wait_for_streams()

            self.assertIn(AMADUES_UI_ROLE_ID, view.role_messages)
            notice = view.role_messages[AMADUES_UI_ROLE_ID][0]
            self.assertIn("API Key", notice.text)
            self.assertNotIn("MiniMax", notice.text)
            self.assertEqual(view.syncing_states, [True, False])

    def test_open_chat_loads_today_messages(self) -> None:
        timestamp = 1_700_000_000
        manager = FakeSessionManager(
            messages=[
                SimpleNamespace(id="u1", role="user", content="hello", timestamp=timestamp),
                SimpleNamespace(id="a1", role="assistant", content="world", timestamp=timestamp + 1),
            ]
        )
        controller = AmaduesController(runtime_factory=lambda: AmaduesRuntime(manager, SimpleNamespace()))
        view = StubView()
        controller.bind_view(view)

        controller.on_open_chat(AMADUES_UI_ROLE_ID)
        controller.wait_for_streams()

        self.assertEqual(len(view.role_messages[AMADUES_UI_ROLE_ID]), 2)
        self.assertTrue(view.role_messages[AMADUES_UI_ROLE_ID][0].is_user)
        self.assertFalse(view.role_messages[AMADUES_UI_ROLE_ID][1].is_user)

    def test_open_chat_dispatches_background_sync_updates_to_ui(self) -> None:
        manager = FakeSessionManager(messages=[SimpleNamespace(id="a1", role="assistant", content="world", timestamp=1_700_000_000)])
        controller = AmaduesController(runtime_factory=lambda: AmaduesRuntime(manager, SimpleNamespace()))
        view = DispatchRecordingView()
        controller.bind_view(view)
        view.dispatch_count = 0

        controller.on_open_chat(AMADUES_UI_ROLE_ID)
        controller.wait_for_streams()

        self.assertGreaterEqual(view.dispatch_count, 3)
        self.assertEqual(view.syncing_states, [True, False])
        self.assertEqual(view.role_messages[AMADUES_UI_ROLE_ID][0].text, "world")

    def test_send_message_appends_backend_reply(self) -> None:
        manager = FakeSessionManager(reply={"message_id": "reply-1", "content": "assistant reply"})
        controller = AmaduesController(
            runtime_factory=lambda: AmaduesRuntime(manager, SimpleNamespace()),
            normal_sentence_delay=0,
            normal_character_delay=0,
        )
        view = StubView()
        controller.bind_view(view)

        controller.on_send_message(AMADUES_UI_ROLE_ID, "hi", "normal")
        controller.wait_for_streams()

        self.assertEqual(manager.sent, [("hi", None)])
        self.assertEqual(view.typing_states, [True, False])
        self.assertEqual(view.appended[-1].text, "assistant reply")
        self.assertFalse(view.appended[-1].is_user)
        self.assertEqual(view.updated[-1][2], False)

    def test_send_message_dispatches_stream_updates_to_ui(self) -> None:
        manager = FakeSessionManager(reply={"message_id": "reply-1", "content": "ABC!"}, stream_deltas=["ABC!"])
        controller = AmaduesController(
            runtime_factory=lambda: AmaduesRuntime(manager, SimpleNamespace()),
            normal_sentence_delay=0,
            normal_character_delay=0,
        )
        view = DispatchRecordingView()
        controller.bind_view(view)
        view.dispatch_count = 0

        controller.on_send_message(AMADUES_UI_ROLE_ID, "hi", "normal")
        controller.wait_for_streams()

        self.assertGreaterEqual(view.dispatch_count, 5)
        self.assertEqual(view.typing_states, [True, False])
        self.assertEqual(view.appended[0].text, "ABC!")
        self.assertFalse(view.appended[0].is_streaming)

    def test_send_message_publishes_reply_emotion(self) -> None:
        manager = FakeSessionManager(
            reply={
                "message_id": "reply-1",
                "content": "assistant reply",
                "tag": SimpleNamespace(emotion="happy"),
            }
        )
        controller = AmaduesController(
            runtime_factory=lambda: AmaduesRuntime(manager, SimpleNamespace()),
            normal_sentence_delay=0,
            normal_character_delay=0,
        )
        view = StubView()
        controller.bind_view(view)

        controller.on_send_message(AMADUES_UI_ROLE_ID, "hi", "normal")
        controller.wait_for_streams()

        self.assertEqual(view.reply_emotions, [(AMADUES_UI_ROLE_ID, "happy")])

    def test_send_message_switches_to_data_role_brain(self) -> None:
        manager = FakeSessionManager(reply={"message_id": "reply-1", "content": "shinji reply"})
        registry = FakeBrainRegistry([AMADUES_BRAIN_ID, "shinji"], current=AMADUES_BRAIN_ID)
        controller = AmaduesController(
            runtime_factory=lambda: AmaduesRuntime(manager, registry),
            normal_sentence_delay=0,
            normal_character_delay=0,
        )
        view = StubView()
        controller.bind_view(view)

        controller.on_send_message("shinji", "hi", "normal")
        controller.wait_for_streams()

        self.assertEqual(manager.switched, ["shinji"])
        self.assertEqual(manager.sent, [("hi", None)])
        self.assertEqual(view.appended[-1].role_id, "shinji")
        self.assertEqual(view.appended[-1].text, "shinji reply")

    def test_send_message_splits_streamed_reply_into_sentence_bubbles(self) -> None:
        manager = FakeSessionManager(reply={"message_id": "reply-1", "content": "第一句。第二句！"})
        controller = AmaduesController(
            runtime_factory=lambda: AmaduesRuntime(manager, SimpleNamespace()),
            normal_sentence_delay=0,
            normal_character_delay=0,
        )
        view = StubView()
        controller.bind_view(view)

        controller.on_send_message(AMADUES_UI_ROLE_ID, "hi", "normal")
        controller.wait_for_streams()

        self.assertEqual([message.text for message in view.appended[-2:]], ["第一句。", "第二句！"])
        self.assertFalse(view.appended[-1].is_streaming)

    def test_streamed_reply_does_not_create_blank_first_assistant_bubble(self) -> None:
        manager = FakeSessionManager(
            reply={"message_id": "reply-1", "content": "第一"},
            stream_deltas=["第一"],
        )
        controller = AmaduesController(
            runtime_factory=lambda: AmaduesRuntime(manager, SimpleNamespace()),
            normal_sentence_delay=0,
            normal_character_delay=0,
        )
        view = StubView()
        controller.bind_view(view)

        controller.on_send_message(AMADUES_UI_ROLE_ID, "hi", "normal")
        controller.wait_for_streams()

        self.assertEqual([message.text for message in view.appended], ["第一"])
        self.assertNotIn("", [message.text for message in view.appended])
        self.assertFalse(view.appended[0].is_streaming)

    def test_normal_reply_reveals_text_character_by_character(self) -> None:
        manager = FakeSessionManager(
            reply={"message_id": "reply-1", "content": "ABC!"},
            stream_deltas=["ABC!"],
        )
        controller = AmaduesController(
            runtime_factory=lambda: AmaduesRuntime(manager, SimpleNamespace()),
            normal_sentence_delay=0,
            normal_character_delay=0,
        )
        view = StubView()
        controller.bind_view(view)

        controller.on_send_message(AMADUES_UI_ROLE_ID, "hi", "normal")
        controller.wait_for_streams()

        self.assertEqual(view.appended[0].text, "ABC!")
        self.assertEqual(
            view.updated,
            [
                (view.appended[0].id, "AB", True),
                (view.appended[0].id, "ABC", True),
                (view.appended[0].id, "ABC!", False),
            ],
        )

    def test_normal_reply_delays_between_sentence_bubbles_across_chunks(self) -> None:
        manager = FakeSessionManager(
            reply={"message_id": "reply-1", "content": "A!B!"},
            stream_deltas=["A!", "B!"],
        )
        controller = AmaduesController(
            runtime_factory=lambda: AmaduesRuntime(manager, SimpleNamespace()),
            normal_sentence_delay=0.2,
            normal_character_delay=0,
        )
        view = StubView()
        controller.bind_view(view)

        with patch("GUI.control.time.sleep") as sleep:
            controller.on_send_message(AMADUES_UI_ROLE_ID, "hi", "normal")
            controller.wait_for_streams()

        self.assertEqual([message.text for message in view.appended], ["A!", "B!"])
        sleep.assert_called_once_with(0.2)

    def test_single_delta_with_multiple_sentences_creates_multiple_bubbles(self) -> None:
        manager = FakeSessionManager(
            reply={"message_id": "reply-1", "content": "第一句。第二句！"},
            stream_deltas=["第一句。第二句！"],
        )
        controller = AmaduesController(
            runtime_factory=lambda: AmaduesRuntime(manager, SimpleNamespace()),
            normal_sentence_delay=0,
            normal_character_delay=0,
        )
        view = StubView()
        controller.bind_view(view)

        controller.on_send_message(AMADUES_UI_ROLE_ID, "hi", "normal")
        controller.wait_for_streams()

        self.assertEqual([message.text for message in view.appended], ["第一句。", "第二句！"])
        self.assertEqual([message.is_streaming for message in view.appended], [False, False])

    def test_unfinished_stream_tail_finishes_current_bubble_only(self) -> None:
        manager = FakeSessionManager(
            reply={"message_id": "reply-1", "content": "还没说完"},
            stream_deltas=["还没说完"],
        )
        controller = AmaduesController(
            runtime_factory=lambda: AmaduesRuntime(manager, SimpleNamespace()),
            normal_sentence_delay=0,
            normal_character_delay=0,
        )
        view = StubView()
        controller.bind_view(view)

        controller.on_send_message(AMADUES_UI_ROLE_ID, "hi", "normal")
        controller.wait_for_streams()

        self.assertEqual(len(view.appended), 1)
        self.assertEqual(view.appended[0].text, "还没说完")
        self.assertFalse(view.appended[0].is_streaming)

    def test_send_message_updates_single_immersive_message_while_streaming(self) -> None:
        manager = FakeSessionManager(reply={"message_id": "reply-1", "content": "第一句。第二句！"})
        controller = AmaduesController(runtime_factory=lambda: AmaduesRuntime(manager, SimpleNamespace()))
        view = StubView()
        controller.bind_view(view)

        controller.on_send_message(AMADUES_UI_ROLE_ID, "hi", "immersive")
        controller.wait_for_streams()

        self.assertEqual(len(view.appended), 1)
        self.assertEqual(view.appended[0].text, "第一句。第二句！")
        self.assertFalse(view.appended[0].is_streaming)

    def test_saving_settings_invalidates_cached_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as config_dir:
            calls = {"count": 0}

            def factory() -> AmaduesRuntime:
                calls["count"] += 1
                manager = FakeSessionManager()
                return AmaduesRuntime(manager, SimpleNamespace())

            controller = AmaduesController(
                settings_storage=UiSettingsStorage(config_dir),
                runtime_factory=factory,
            )
            view = StubView()
            controller.bind_view(view)

            controller.on_open_chat(AMADUES_UI_ROLE_ID)
            controller.on_open_chat(AMADUES_UI_ROLE_ID)
            controller.wait_for_streams()
            self.assertEqual(calls["count"], 1)

            controller.on_settings_saved(
                UiSettings(
                    is_dark=True,
                    token_quality=50,
                    model_provider=DEEPSEEK_PROVIDER,
                    model_name=DEEPSEEK_V4_FLASH_MODEL,
                    api_key="new-key",
                    user_name="Tester",
                )
            )
            controller.on_open_chat(AMADUES_UI_ROLE_ID)
            controller.wait_for_streams()

            self.assertEqual(calls["count"], 2)
            self.assertEqual(view.applied_settings.api_key, "new-key")
            self.assertEqual(view.applied_settings.model_provider, DEEPSEEK_PROVIDER)
            self.assertEqual(view.applied_settings.model_name, DEEPSEEK_V4_FLASH_MODEL)


if __name__ == "__main__":
    unittest.main()
