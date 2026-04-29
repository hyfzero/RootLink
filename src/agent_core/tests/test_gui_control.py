#!/usr/bin/env python3
"""Tests for the thin GUI control layer."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

TEST_FILE = Path(__file__).resolve()
SRC_DIR = TEST_FILE.parents[2]
REPO_ROOT = TEST_FILE.parents[3]

for path in (str(REPO_ROOT), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from GUI.control import (
    AMADUES_BRAIN_ID,
    AMADUES_UI_ROLE_ID,
    MINIMAX_MODEL,
    MINIMAX_PROVIDER,
    AmaduesController,
    AmaduesRuntime,
    UiSettingsStorage,
    build_amadues_runtime,
)
from GUI.interfaces import ChatMessage, CompanionRole, CompanionUIView, UiSettings
from GUI.role_loader import load_roles_from_data
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
        self.reply_emotions: list[tuple[str, str]] = []
        self.applied_settings: UiSettings | None = None
        self.pages: list[str] = []

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

    def set_reply_emotion(self, role_id: str, emotion: str) -> None:
        self.reply_emotions.append((role_id, emotion))

    def apply_settings(self, settings: UiSettings) -> None:
        self.applied_settings = settings

    def show_page(self, page: str) -> None:
        self.pages.append(page)

    def clear_chat(self) -> None:
        self.messages = []


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

            loaded = storage.load_ui_settings()
            self.assertFalse(loaded.is_dark)
            self.assertEqual(loaded.token_quality, 80)
            self.assertEqual(loaded.model_provider, MINIMAX_PROVIDER)
            self.assertEqual(loaded.api_key, "test-key")
            self.assertEqual(loaded.user_name, "Tester")
            self.assertEqual(loaded.user_avatar_path, "avatar.png")

    def test_build_amadues_runtime_raises_when_no_brain_exists(self) -> None:
        with tempfile.TemporaryDirectory() as config_dir, tempfile.TemporaryDirectory() as data_dir:
            os.environ[PathResolver.ENV_CONFIG_DIR] = config_dir
            os.environ[PathResolver.ENV_DATA_DIR] = data_dir

            storage = UiSettingsStorage(config_dir)
            storage.save_minimax_config("runtime-key")

            with self.assertRaisesRegex(RuntimeError, "No brains found"):
                build_amadues_runtime(config_dir=config_dir)

            self.assertEqual(list(Path(data_dir).iterdir()), [])

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

    def test_open_chat_without_api_key_injects_notice_message(self) -> None:
        with tempfile.TemporaryDirectory() as config_dir:
            controller = AmaduesController(settings_storage=UiSettingsStorage(config_dir))
            view = StubView()
            controller.bind_view(view)

            controller.on_open_chat(AMADUES_UI_ROLE_ID)

            self.assertIn(AMADUES_UI_ROLE_ID, view.role_messages)
            notice = view.role_messages[AMADUES_UI_ROLE_ID][0]
            self.assertIn("MiniMax", notice.text)
            self.assertIn("API Key", notice.text)

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

        self.assertEqual(len(view.role_messages[AMADUES_UI_ROLE_ID]), 2)
        self.assertTrue(view.role_messages[AMADUES_UI_ROLE_ID][0].is_user)
        self.assertFalse(view.role_messages[AMADUES_UI_ROLE_ID][1].is_user)

    def test_send_message_appends_backend_reply(self) -> None:
        manager = FakeSessionManager(reply={"message_id": "reply-1", "content": "assistant reply"})
        controller = AmaduesController(
            runtime_factory=lambda: AmaduesRuntime(manager, SimpleNamespace()),
            normal_sentence_delay=0,
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
        )
        view = StubView()
        controller.bind_view(view)

        controller.on_send_message(AMADUES_UI_ROLE_ID, "hi", "normal")
        controller.wait_for_streams()

        self.assertEqual([message.text for message in view.appended], ["第一"])
        self.assertNotIn("", [message.text for message in view.appended])
        self.assertFalse(view.appended[0].is_streaming)

    def test_single_delta_with_multiple_sentences_creates_multiple_bubbles(self) -> None:
        manager = FakeSessionManager(
            reply={"message_id": "reply-1", "content": "第一句。第二句！"},
            stream_deltas=["第一句。第二句！"],
        )
        controller = AmaduesController(
            runtime_factory=lambda: AmaduesRuntime(manager, SimpleNamespace()),
            normal_sentence_delay=0,
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
            self.assertEqual(calls["count"], 1)

            controller.on_settings_saved(
                UiSettings(
                    is_dark=True,
                    token_quality=50,
                    model_provider=MINIMAX_PROVIDER,
                    api_key="new-key",
                    user_name="Tester",
                )
            )
            controller.on_open_chat(AMADUES_UI_ROLE_ID)

            self.assertEqual(calls["count"], 2)
            self.assertEqual(view.applied_settings.api_key, "new-key")


if __name__ == "__main__":
    unittest.main()
