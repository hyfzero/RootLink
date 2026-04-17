"""Demo entry point for the Figma mobile-first companion UI."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import flet as ft

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from GUI.interfaces import CharacterDraft, ChatMessage, CompanionUICallback, UiSettings
    from GUI.views import CompanionAppView
else:
    from .interfaces import CharacterDraft, ChatMessage, CompanionUICallback, UiSettings
    from .views import CompanionAppView


class DemoCallback(CompanionUICallback):
    """A non-business callback for local UI smoke testing."""

    def __init__(self, view: CompanionAppView | None = None) -> None:
        self.view = view

    def on_open_chat(self, role_id: str) -> None:
        print(f"[ui] open chat: {role_id}")

    def on_send_message(self, role_id: str, text: str, mode: str) -> None:
        print(f"[ui] send message: role={role_id} mode={mode} text={text}")
        if self.view:
            self.view.append_message(
                ChatMessage(
                    id=f"demo-{datetime.now().timestamp()}",
                    role_id=role_id,
                    text="Received. Real control-layer responses appear here after integration.",
                    is_user=False,
                    timestamp=datetime.now(),
                )
            )

    def on_chat_mode_changed(self, mode: str) -> None:
        print(f"[ui] chat mode: {mode}")

    def on_settings_saved(self, settings: UiSettings) -> None:
        print(f"[ui] settings saved: provider={settings.model_provider} quality={settings.token_quality}")

    def on_character_create_requested(self, draft: CharacterDraft) -> None:
        print(f"[ui] create character: id={draft.brain_id} name={draft.name}")

    def on_theme_toggled(self, is_dark: bool) -> None:
        print(f"[ui] theme: {'dark' if is_dark else 'light'}")

    def on_voice_requested(self) -> None:
        print("[ui] voice requested")

    def on_avatar_upload_requested(self) -> None:
        print("[ui] avatar upload requested")

    def on_portrait_upload_requested(self, emotion_id: str) -> None:
        print(f"[ui] portrait upload requested: {emotion_id}")


def run_demo(page: ft.Page) -> None:
    page.title = "Amadues Companion UI"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0
    page.spacing = 0
    page.window_width = 480
    page.window_height = 860
    page.window_min_width = 360
    page.window_min_height = 640

    callback = DemoCallback()
    view = CompanionAppView(callback=callback, is_dark=True)
    callback.view = view
    page.add(view)


def main() -> None:
    ft.run(run_demo)


if __name__ == "__main__":
    main()
