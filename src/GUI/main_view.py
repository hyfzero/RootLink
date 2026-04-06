"""Main view - application shell with responsive layout."""

import flet as ft
from typing import Optional

from .chat_view import ChatView
from .sidebar_view import SidebarView
from .interfaces import (
    IChatViewCallback,
    IChatViewProvider,
    ChatMessage,
    Character,
    ChatSettings,
)


class MainView(ft.Container, IChatViewProvider):
    """
    Main application view with responsive layout.
    Combines ChatView and SidebarView with adaptive behavior.
    """

    # Breakpoints
    MOBILE_WIDTH = 768

    def __init__(
        self,
        page: ft.Page,
        dark_mode: bool = True,
        callback: Optional[IChatViewCallback] = None,
        expand: bool = True,
        **kwargs
    ):
        super().__init__(expand=expand, **kwargs)

        self._page = page
        self._dark_mode = dark_mode
        self._callback = callback
        self._sidebar_visible = True
        self._is_mobile = False

        # Modern color palette
        self._colors = self._get_colors(dark_mode)

        # Build UI
        self._build_sidebar()
        self._build_chat()
        self._build_layout()

        # Initial responsive check
        page.on_resize = self._handle_resize

    def _get_colors(self, dark_mode: bool) -> dict:
        """Get modern color palette."""
        if dark_mode:
            return {
                "bg": "#0F0F0F",
                "surface": "#1C1C1C",
                "surface_elevated": "#252525",
                "primary": "#6366F1",
                "primary_hover": "#818CF8",
                "text": "#FFFFFF",
                "text_secondary": "#A1A1AA",
                "border": "#3F3F46",
                "sidebar_bg": "#18181B",
                "hover": "#27272A",
                "bubble_ai": "#262637",
                "bubble_user": "#6366F1",
            }
        else:
            return {
                "bg": "#FAFAFA",
                "surface": "#FFFFFF",
                "surface_elevated": "#F4F4F5",
                "primary": "#6366F1",
                "primary_hover": "#4F46E5",
                "text": "#18181B",
                "text_secondary": "#71717A",
                "border": "#E4E4E7",
                "sidebar_bg": "#FFFFFF",
                "hover": "#F4F4F5",
                "bubble_ai": "#F4F4F5",
                "bubble_user": "#6366F1",
            }

    def _build_sidebar(self) -> None:
        """Build the sidebar component."""
        colors = self._colors
        self._sidebar = SidebarView(
            dark_mode=self._dark_mode,
            colors=colors,
            on_history_select=self._handle_history_select,
            on_settings_change=self._handle_settings_change,
            on_export=self._handle_export,
            on_import=self._handle_import,
        )

    def _build_chat(self) -> None:
        """Build the chat view component."""
        colors = self._colors
        self._chat = ChatView(
            dark_mode=self._dark_mode,
            colors=colors,
            on_message_send=self._handle_message_send,
            on_sprite_tap=self._handle_sprite_tap,
        )

    def _build_layout(self) -> None:
        """Build the main layout based on screen size."""
        self._is_mobile = self._page.width < self.MOBILE_WIDTH
        colors = self._colors

        if self._is_mobile:
            self._build_mobile_layout(colors)
        else:
            self._build_desktop_layout(colors)

    def _build_desktop_layout(self, colors: dict) -> None:
        """Build desktop layout with visible sidebar."""
        sidebar_width = min(300, self._page.width * 0.5)  # 220px or 25% of screen
        self._sidebar.width = sidebar_width
        self._sidebar.visible = self._sidebar_visible
        self._sidebar.bgcolor = colors["sidebar_bg"]

        # Main content area with header
        self._header = ft.Container(
            height=56,
            bgcolor=colors["surface"],
            border=ft.Border(
                bottom=ft.BorderSide(1, colors["border"])
            ),
            padding=ft.padding.symmetric(horizontal=16),
            content=ft.Row(
                controls=[
                    ft.IconButton(
                        icon=ft.Icons.MENU,
                        icon_color=colors["text"],
                        on_click=self._toggle_sidebar,
                    ),
                    ft.Text(
                        "ChatUI",
                        size=18,
                        weight=ft.FontWeight.W_600,
                        color=colors["text"],
                    ),
                ],
            ),
        )

        chat_with_header = ft.Column(
            controls=[self._header, self._chat],
            spacing=0,
            expand=True,
        )

        # Chat content container that expands
        chat_container = ft.Container(
            content=chat_with_header,
            expand=True,
            bgcolor=colors["bg"],
        )

        self.content = ft.Row(
            controls=[
                self._sidebar,
                chat_container,
            ],
            spacing=0,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    def _build_mobile_layout(self, colors: dict) -> None:
        """Build mobile layout."""
        # Mobile header
        self._header = ft.Container(
            height=56,
            bgcolor=colors["surface"],
            border=ft.Border(
                bottom=ft.BorderSide(1, colors["border"])
            ),
            padding=ft.padding.symmetric(horizontal=8),
            content=ft.Row(
                controls=[
                    ft.IconButton(
                        icon=ft.Icons.MENU,
                        icon_color=colors["text"],
                        on_click=self._open_sidebar,
                    ),
                    ft.Text(
                        "ChatUI",
                        size=18,
                        weight=ft.FontWeight.W_600,
                        color=colors["text"],
                    ),
                    ft.Container(expand=True),
                    ft.IconButton(
                        icon=ft.Icons.SETTINGS,
                        icon_color=colors["text"],
                        on_click=self._open_sidebar,
                    ),
                ],
            ),
        )

        chat_with_header = ft.Column(
            controls=[self._header, self._chat],
            spacing=0,
            expand=True,
        )

        # Mobile uses overlay sidebar
        self._sidebar.width = self._page.width * 0.8
        self._sidebar.visible = True
        self._sidebar.bgcolor = colors["sidebar_bg"]

        self.content = ft.Stack(
            controls=[
                chat_with_header,
                self._sidebar,
            ],
            expand=True,
        )
        self._sidebar.visible = False

    def _handle_resize(self, e=None) -> None:
        """Handle window resize for responsive layout."""
        new_is_mobile = self._page.width < self.MOBILE_WIDTH
        if new_is_mobile != self._is_mobile:
            self._is_mobile = new_is_mobile
            self._build_layout()
            self.update()

    def _toggle_sidebar(self, e) -> None:
        """Toggle sidebar visibility (desktop)."""
        self._sidebar_visible = not self._sidebar_visible
        self._sidebar.visible = self._sidebar_visible
        self.update()

    def _open_sidebar(self, e) -> None:
        """Open sidebar (mobile)."""
        self._sidebar.visible = True
        self.update()

    def _close_sidebar(self, e) -> None:
        """Close sidebar (mobile)."""
        # Check if click was on sidebar or outside
        self._sidebar.visible = False
        self.update()

    def _handle_message_send(self, text: str) -> None:
        """Handle message send from chat view."""
        if self._callback:
            self._callback.on_message_send(text)

    def _handle_sprite_tap(self) -> None:
        """Handle sprite tap event."""
        if self._callback:
            self._callback.on_sprite_tapped()

    def _handle_history_select(self, chat_id: str) -> None:
        """Handle history item selection."""
        if self._callback:
            self._callback.on_chat_history_select(chat_id)

    def _handle_settings_change(self, key: str, value) -> None:
        """Handle settings change."""
        if key == "theme":
            self.set_dark_mode(value == "dark")
        elif self._callback:
            settings = ChatSettings()
            setattr(settings, key, value)
            self._callback.on_settings_changed(settings)

    def _handle_export(self) -> None:
        """Handle export action."""
        pass

    def _handle_import(self) -> None:
        """Handle import action."""
        pass

    # IChatViewProvider implementation

    def append_message(self, message: ChatMessage) -> None:
        """Add a new message to the chat view."""
        self._chat.append_message(message)

    def update_character(self, character: Character) -> None:
        """Update the displayed character sprite."""
        self._chat.update_character(character)
        self._sidebar.update_character(character)

    def set_typing_indicator(self, visible: bool) -> None:
        """Show or hide typing indicator."""
        self._chat.show_typing_indicator(visible)

    def clear_chat(self) -> None:
        """Clear all messages from chat view."""
        self._chat.clear_chat()

    def set_sidebar_visible(self, visible: bool) -> None:
        """Show or hide sidebar."""
        self._sidebar_visible = visible
        if not self._is_mobile:
            self._sidebar.visible = visible
            self.update()

    def apply_settings(self, settings: ChatSettings) -> None:
        """Apply settings to UI."""
        self.set_dark_mode(settings.theme == "dark")
        self._chat.set_text_speed(settings.text_speed)

    def set_dark_mode(self, dark_mode: bool) -> None:
        """Update UI for theme change."""
        self._dark_mode = dark_mode
        self._colors = self._get_colors(dark_mode)
        self._chat.set_dark_mode(dark_mode)
        self._chat.set_colors(self._colors)
        self._sidebar.set_dark_mode(dark_mode)
        self._sidebar.set_colors(self._colors)
        self._build_layout()
        self.update()


class ChatUIApp:
    """Application wrapper for ChatUI."""

    def __init__(
        self,
        title: str = "ChatUI",
        dark_mode: bool = True,
        width: float = 1200,
        height: float = 800,
    ):
        self._title = title
        self._dark_mode = dark_mode
        self._width = width
        self._height = height

    def run(self, page: ft.Page) -> None:
        """Initialize and run the application."""
        page.title = self._title
        page.theme_mode = ft.ThemeMode.DARK if self._dark_mode else ft.ThemeMode.LIGHT
        page.window_width = self._width
        page.window_height = self._height
        page.padding = 0

        main_view = MainView(
            page=page,
            dark_mode=self._dark_mode,
            callback=DummyCallback(),
            expand=True,
        )

        page.add(main_view)


class DummyCallback(IChatViewCallback):
    """Dummy callback for standalone testing."""

    def on_message_send(self, text: str) -> None:
        print(f"Message sent: {text}")

    def on_settings_changed(self, settings: ChatSettings) -> None:
        pass

    def on_theme_toggle(self) -> None:
        pass

    def on_sidebar_toggle(self) -> None:
        pass

    def on_chat_history_select(self, chat_id: str) -> None:
        pass

    def on_sprite_tapped(self) -> None:
        pass
