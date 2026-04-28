#!/usr/bin/env python3
"""Tests for GUI view-only chat behavior."""

from __future__ import annotations

import asyncio
import sys
import unittest
from datetime import datetime
from pathlib import Path

import flet as ft

TEST_FILE = Path(__file__).resolve()
SRC_DIR = TEST_FILE.parents[2]
REPO_ROOT = TEST_FILE.parents[3]

for path in (str(REPO_ROOT), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from GUI.components import MessageBubble
from GUI.interfaces import ChatMessage, CompanionRole
from GUI.views import CompanionAppView


def make_role() -> CompanionRole:
    return CompanionRole(
        id="amadeus",
        name="Amadeus",
        type="Test",
        tags=["test"],
        intro="intro",
        status_text="status",
        accent_color="#FF6600",
        avatar_path="assets/portrait.png",
        standing_image_path="assets/standing.png",
        last_message="last",
        last_time="now",
    )


class FakePage:
    def __init__(self) -> None:
        self.task_calls = 0

    def run_task(self, coro_func) -> None:
        self.task_calls += 1
        asyncio.run(coro_func())

    def update(self, *_controls) -> None:
        return None


class TrackingCompanionAppView(CompanionAppView):
    def __init__(self, page: FakePage | None = None) -> None:
        self.scroll_calls = 0
        self._fake_page = page
        super().__init__(roles=[make_role()])

    @property
    def page(self):  # type: ignore[override]
        if self._fake_page is None:
            raise RuntimeError("Control must be added to the page first")
        return self._fake_page

    async def _scroll_chat_to_latest_async(self) -> None:
        self.scroll_calls += 1


class FakeListView:
    def __init__(self) -> None:
        self.scroll_requests: list[dict[str, object]] = []
        self.update_calls = 0

    async def scroll_to(self, **kwargs) -> None:
        self.scroll_requests.append(kwargs)

    def update(self) -> None:
        self.update_calls += 1


class GuiViewTests(unittest.TestCase):
    def test_view_supports_empty_role_list(self) -> None:
        view = CompanionAppView(roles=[])

        self.assertEqual(view._roles, [])
        self.assertEqual(view.active_role.id, "")
        self.assertEqual(view._messages, [])

    def test_split_immersive_sentences_handles_punctuation_and_newlines(self) -> None:
        view = CompanionAppView(roles=[make_role()])

        segments = view._split_immersive_sentences("第一句。第二句！\n第三句？第四句")

        self.assertEqual(segments, ["第一句。", "第二句！", "第三句？", "第四句"])

    def test_split_immersive_sentences_falls_back_to_single_segment(self) -> None:
        view = CompanionAppView(roles=[make_role()])

        segments = view._split_immersive_sentences("没有句末标点也要完整显示")

        self.assertEqual(segments, ["没有句末标点也要完整显示"])

    def test_immersive_state_advances_one_sentence_at_a_time(self) -> None:
        role = make_role()
        view = CompanionAppView(roles=[role])
        view._active_role_id = role.id
        view._chat_mode = "immersive"
        view._messages = [
            ChatMessage("assistant-1", role.id, "第一句。第二句！第三句？", False, datetime.now()),
        ]

        view._reset_immersive_state(role)

        self.assertEqual(view._current_immersive_text(role), "第一句。")

        view._advance_immersive_text(None)
        self.assertEqual(view._current_immersive_text(role), "第二句！")

        view._advance_immersive_text(None)
        self.assertEqual(view._current_immersive_text(role), "第三句？")

        view._advance_immersive_text(None)
        self.assertEqual(view._current_immersive_text(role), "第三句？")

    def test_immersive_click_completes_current_sentence_before_advancing(self) -> None:
        role = make_role()
        view = CompanionAppView(roles=[role])
        view._active_role_id = role.id
        view._chat_mode = "immersive"
        view._messages = [
            ChatMessage("assistant-1", role.id, "第一句。第二句！", False, datetime.now()),
        ]
        view._immersive_dialogue_text = ft.Text("")
        view._reset_immersive_state(role)
        view._immersive_display_text = "第一"

        view._advance_immersive_text(None)

        self.assertEqual(view._immersive_index, 0)
        self.assertEqual(view._immersive_display_text, "第一句。")

        view._advance_immersive_text(None)

        self.assertEqual(view._immersive_index, 1)

    def test_update_message_text_refreshes_streaming_message(self) -> None:
        role = make_role()
        view = CompanionAppView(roles=[role])
        view._active_role_id = role.id
        view._messages = [
            ChatMessage("assistant-1", role.id, "旧", False, datetime.now(), is_streaming=True),
        ]

        view.update_message_text("assistant-1", "新内容", is_streaming=False)

        self.assertEqual(view._messages[0].text, "新内容")
        self.assertFalse(view._messages[0].is_streaming)

    def test_new_assistant_message_resets_immersive_state(self) -> None:
        role = make_role()
        view = CompanionAppView(roles=[role])
        view._active_role_id = role.id
        view._chat_mode = "immersive"
        view._messages = [
            ChatMessage("assistant-1", role.id, "第一句。第二句。", False, datetime.now()),
        ]
        view._reset_immersive_state(role)
        view._advance_immersive_text(None)

        view.append_message(ChatMessage("assistant-2", role.id, "新的第一句。新的第二句。", False, datetime.now()))

        self.assertEqual(view._immersive_message_id, "assistant-2")
        self.assertEqual(view._current_immersive_text(role), "新的第一句。")

    def test_show_page_chat_in_normal_mode_triggers_bottom_scroll_tasks(self) -> None:
        role = make_role()
        fake_page = FakePage()
        view = TrackingCompanionAppView(page=fake_page)
        view._messages = [
            ChatMessage("assistant-1", role.id, "hello", False, datetime.now()),
            ChatMessage("assistant-2", role.id, "world", False, datetime.now()),
        ]

        view.show_page("chat")

        self.assertEqual(fake_page.task_calls, 2)
        self.assertEqual(view.scroll_calls, 2)

    def test_set_role_messages_in_normal_chat_triggers_bottom_scroll_tasks(self) -> None:
        role = make_role()
        fake_page = FakePage()
        view = TrackingCompanionAppView(page=fake_page)
        view.show_page("chat")
        view.scroll_calls = 0
        fake_page.task_calls = 0

        view.set_role_messages(
            role.id,
            [
                ChatMessage("assistant-1", role.id, "first", False, datetime.now()),
                ChatMessage("assistant-2", role.id, "second", False, datetime.now()),
            ],
        )

        self.assertEqual(fake_page.task_calls, 2)
        self.assertEqual(view.scroll_calls, 2)

    def test_set_typing_in_normal_chat_triggers_bottom_scroll_tasks(self) -> None:
        fake_page = FakePage()
        view = TrackingCompanionAppView(page=fake_page)
        view.show_page("chat")
        view.scroll_calls = 0
        fake_page.task_calls = 0

        view.set_typing(True)

        self.assertEqual(fake_page.task_calls, 2)
        self.assertEqual(view.scroll_calls, 2)

    def test_scroll_chat_to_latest_async_uses_start_offset_for_reversed_list(self) -> None:
        role = make_role()
        view = CompanionAppView(roles=[role])
        view._active_role_id = role.id
        view._chat_mode = "normal"
        view._messages = [
            ChatMessage("assistant-1", role.id, "hello", False, datetime.now()),
            ChatMessage("assistant-2", role.id, "world", False, datetime.now()),
        ]
        fake_list_view = FakeListView()
        view._chat_list_view = fake_list_view

        asyncio.run(view._scroll_chat_to_latest_async())

        self.assertEqual(fake_list_view.scroll_requests, [{"offset": 0, "duration": 0}])
        self.assertEqual(fake_list_view.update_calls, 1)

    def test_did_mount_flushes_pending_bottom_scroll(self) -> None:
        fake_page = FakePage()
        view = TrackingCompanionAppView(page=fake_page)
        view._pending_scroll_to_latest = True

        view.did_mount()

        self.assertEqual(fake_page.task_calls, 2)
        self.assertEqual(view.scroll_calls, 2)

    def test_build_normal_chat_uses_reversed_list_view(self) -> None:
        role = make_role()
        view = CompanionAppView(roles=[role])

        container = view._build_normal_chat(view._colors(), role)

        list_view = container.content
        self.assertTrue(container.expand)
        self.assertTrue(list_view.expand)
        self.assertTrue(list_view.reverse)
        self.assertFalse(list_view.auto_scroll)
        self.assertFalse(list_view.build_controls_on_demand)

    def test_build_normal_chat_controls_keep_latest_content_first(self) -> None:
        role = make_role()
        view = CompanionAppView(roles=[role])
        first = ChatMessage("assistant-1", role.id, "older", False, datetime.now())
        second = ChatMessage("assistant-2", role.id, "newer", False, datetime.now())
        view._messages = [first, second]
        view._typing = True

        controls = view._build_normal_chat_controls(view._colors(), role)

        self.assertEqual(getattr(controls[0], "key", None), None)
        self.assertEqual(getattr(controls[1], "key", None), "msg-assistant-2")
        self.assertEqual(getattr(controls[2], "key", None), "msg-assistant-1")

    def test_normal_renderer_splits_complete_assistant_message_into_virtual_bubbles(self) -> None:
        role = make_role()
        view = CompanionAppView(roles=[role])
        view._messages = [
            ChatMessage("assistant-1", role.id, "第一句。第二句！", False, datetime.now()),
        ]

        controls = view._build_chat_message_controls(view._colors(), role)

        self.assertEqual(
            [getattr(control, "key", None) for control in controls],
            ["msg-assistant-1-display-0", "msg-assistant-1-display-1"],
        )
        self.assertEqual(len(view._messages), 1)

    def test_normal_renderer_does_not_split_streaming_assistant_message(self) -> None:
        role = make_role()
        view = CompanionAppView(roles=[role])
        view._messages = [
            ChatMessage("assistant-1", role.id, "第一句。第二句！", False, datetime.now(), is_streaming=True),
        ]

        controls = view._build_chat_message_controls(view._colors(), role)

        self.assertEqual([getattr(control, "key", None) for control in controls], ["msg-assistant-1"])

    def test_switching_from_immersive_to_normal_shows_virtual_sentence_bubbles(self) -> None:
        role = make_role()
        view = TrackingCompanionAppView(page=FakePage())
        view._active_role_id = role.id
        view._chat_mode = "immersive"
        view._messages = [
            ChatMessage("assistant-1", role.id, "第一句。第二句！", False, datetime.now()),
        ]

        view._set_chat_mode("normal")
        controls = view._build_chat_message_controls(view._colors(), role)

        self.assertEqual(
            [getattr(control, "key", None) for control in controls],
            ["msg-assistant-1-display-0", "msg-assistant-1-display-1"],
        )

    def test_message_bubble_layout_is_responsive(self) -> None:
        role = make_role()
        bubble = MessageBubble(ChatMessage("assistant-1", role.id, "A longer message that should wrap cleanly.", False, datetime.now()), role, True)

        self.assertTrue(bubble.expand)
        self.assertTrue(bubble.content.expand)
        self.assertEqual(len(bubble.content.controls), 2)
        self.assertEqual(getattr(bubble.content.controls[0], "width", None), 32)
        self.assertTrue(bubble.content.controls[1].expand)


if __name__ == "__main__":
    unittest.main()
