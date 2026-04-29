"""Entry points for the Flet companion UI."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import flet as ft

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

if __package__ in (None, ""):
    from GUI.control import AmaduesController
    from GUI.interfaces import CharacterDraft, ChatMessage, CompanionUICallback, UiSettings
    from GUI.views import CompanionAppView
    from agent_core.session import PathResolver
else:
    from .control import AmaduesController
    from .interfaces import CharacterDraft, ChatMessage, CompanionUICallback, UiSettings
    from .views import CompanionAppView
    from agent_core.session import PathResolver


def _configure_page(page: ft.Page, *, is_dark: bool) -> None:
    page.title = "Amadues Companion"
    page.theme_mode = ft.ThemeMode.DARK if is_dark else ft.ThemeMode.LIGHT
    page.padding = 0
    page.spacing = 0
    page.window_width = 480
    page.window_height = 860
    page.window_min_width = 360
    page.window_min_height = 640


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
                    text="\u5df2\u6536\u5230\u3002\u63a5\u5165\u63a7\u5236\u5c42\u540e\uff0c\u771f\u5b9e\u56de\u590d\u4f1a\u663e\u793a\u5728\u8fd9\u91cc\u3002",
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


async def _resolve_app_storage_root(page: ft.Page) -> Path | None:
    storage_paths = getattr(page, "storage_paths", None)
    get_support_dir = getattr(storage_paths, "get_application_support_directory", None)
    if callable(get_support_dir):
        try:
            support_dir = await get_support_dir()
        except Exception:
            support_dir = None
        if support_dir:
            return Path(str(support_dir))

    flet_data_dir = os.environ.get(PathResolver.ENV_FLET_DATA_DIR)
    if flet_data_dir:
        return Path(flet_data_dir).expanduser()
    return None


async def _bootstrap_app_storage(page: ft.Page) -> None:
    app_root = await _resolve_app_storage_root(page)
    if app_root is None:
        return
    PathResolver.configure_app_storage_root(app_root)
    PathResolver.migrate_legacy_app_storage(app_root)


async def run_demo(page: ft.Page) -> None:
    await _bootstrap_app_storage(page)
    _configure_page(page, is_dark=True)
    callback = DemoCallback()
    view = CompanionAppView(callback=callback, is_dark=True)
    callback.view = view
    page.add(view)


async def run_app(page: ft.Page) -> None:
    await _bootstrap_app_storage(page)
    controller = AmaduesController()
    _configure_page(page, is_dark=controller.initial_settings.is_dark)
    view = CompanionAppView(callback=controller, is_dark=controller.initial_settings.is_dark)
    controller.bind_view(view)
    page.add(view)


def main() -> None:
    ft.run(run_app)


if __name__ == "__main__":
    main()
