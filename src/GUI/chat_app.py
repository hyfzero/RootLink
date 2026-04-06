"""Standalone ChatUI Application Entry Point."""

import sys
import os

# Add project root to path for imports
_current_file = os.path.abspath(__file__)
# d:/Godot/amadues/src/GUI/chat_app.py -> d:/Godot/amadues
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(_current_file)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import flet as ft
from datetime import datetime

from src.GUI.main_view import MainView, ChatUIApp
from src.GUI.interfaces import ChatMessage, Character


class DemoCallback(ChatUIApp):
    """
    Demo callback for testing ChatUI.
    Implements IChatViewCallback to handle user interactions.
    """

    def __init__(self, main_view: MainView):
        super().__init__()
        self._main_view = main_view
        self._message_count = 0

    def on_message_send(self, text: str) -> None:
        """Handle user message and generate AI response."""
        # Add user message
        user_msg = ChatMessage(
            id=f"user_{self._message_count}",
            text=text,
            is_user=True,
            timestamp=datetime.now(),
        )
        self._main_view.append_message(user_msg)
        self._message_count += 1

        # Show typing indicator
        self._main_view.set_typing_indicator(True)

        # Simulate AI response after delay
        def show_ai_response():
            self._main_view.set_typing_indicator(False)

            ai_msg = ChatMessage(
                id=f"ai_{self._message_count}",
                text=f"You said: {text}\n\nThis is a demo response.",
                is_user=False,
                timestamp=datetime.now(),
            )
            self._main_view.append_message(ai_msg)
            self._message_count += 1

        # Schedule response (simplified demo)
        import asyncio
        self._main_view._page.run_task(self._delayed_response)

    async def _delayed_response(self) -> None:
        """Delayed AI response for demo."""
        import asyncio
        await asyncio.sleep(1.0)
        self._main_view.set_typing_indicator(False)

        ai_msg = ChatMessage(
            id=f"ai_{self._message_count}",
            text="This is a demo AI response. Configure the Control layer to add real AI functionality.",
            is_user=False,
            timestamp=datetime.now(),
        )
        self._main_view.append_message(ai_msg)
        self._message_count += 1

    def on_settings_changed(self, settings) -> None:
        """Handle settings change."""
        print(f"Settings changed: {settings}")

    def on_theme_toggle(self) -> None:
        """Handle theme toggle."""
        pass

    def on_sidebar_toggle(self) -> None:
        """Handle sidebar toggle."""
        pass

    def on_chat_history_select(self, chat_id: str) -> None:
        """Handle chat history selection."""
        print(f"Selected chat: {chat_id}")

    def on_sprite_tapped(self) -> None:
        """Handle sprite tap."""
        print("Sprite tapped!")


def main(page: ft.Page):
    """Main entry point for the ChatUI application."""
    # Initialize main view with callback
    main_view = MainView(
        page=page,
        dark_mode=True,
        callback=DemoCallback(main_view=None),  # We'll fix this after creation
        expand=True,
    )

    # Fix callback with main_view reference
    demo_callback = DemoCallback(main_view)
    main_view._callback = demo_callback

    # Set initial character (demo)
    demo_character = Character(
        id="assistant",
        name="Assistant",
        sprite_path="",  # No sprite path, will show placeholder
        avatar_path="",
    )
    main_view.update_character(demo_character)

    # Configure page
    page.title = "ChatUI - Galgame Chat Interface"
    page.theme_mode = ft.ThemeMode.DARK
    page.window_width = 1200
    page.window_height = 800
    page.padding = 0
    page.add(main_view)


if __name__ == "__main__":
    ft.run(main)
