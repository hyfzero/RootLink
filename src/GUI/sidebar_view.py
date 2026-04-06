"""Sidebar view - navigation and settings panel."""

import flet as ft
from flet.controls.box import BoxFit
from typing import Optional, Callable, List

from .components import SettingsPanel
from .interfaces import Character


class SidebarView(ft.Container):
    """
    Sidebar panel for chat navigation and settings.
    Collapsible on mobile, always visible on desktop.
    Modern flat design.
    """

    def __init__(
        self,
        dark_mode: bool = True,
        colors: dict = None,
        on_history_select: Optional[Callable] = None,
        on_settings_change: Optional[Callable] = None,
        on_export: Optional[Callable] = None,
        on_import: Optional[Callable] = None,
        **kwargs
    ):
        super().__init__(**kwargs)

        self._dark_mode = dark_mode
        self._colors = colors or self._get_default_colors(dark_mode)
        self._on_history_select = on_history_select
        self._on_settings_change = on_settings_change
        self._on_export = on_export
        self._on_import = on_import

        self._build_ui()

    def _get_default_colors(self, dark_mode: bool) -> dict:
        """Get default color palette."""
        if dark_mode:
            return {
                "bg": "#18181B",
                "surface": "#1C1C1C",
                "primary": "#6366F1",
                "text": "#FFFFFF",
                "text_secondary": "#A1A1AA",
                "border": "#3F3F46",
                "hover": "#27272A",
            }
        else:
            return {
                "bg": "#FFFFFF",
                "surface": "#F4F4F5",
                "primary": "#6366F1",
                "text": "#18181B",
                "text_secondary": "#71717A",
                "border": "#E4E4E7",
                "hover": "#F4F4F5",
            }

    def set_colors(self, colors: dict) -> None:
        """Update colors."""
        self._colors = colors

    def _build_ui(self) -> None:
        """Build the sidebar UI."""
        colors = self._colors

        self.bgcolor = colors["bg"]

        # Character section
        character_section = self._build_character_section(colors)

        # Navigation section
        nav_section = self._build_navigation_section(colors)

        # Settings section
        settings_section = self._build_settings_section(colors)

        # 底部操作区域
        actions_section = self._build_actions_section(colors)

        # 可滚动内容区域 - 占满除底部操作外的所有空间
        scrollable_content = ft.Column(
            controls=[
                character_section,
                ft.Container(height=1, bgcolor=colors["border"]),
                nav_section,
                ft.Container(height=1, bgcolor=colors["border"]),
                settings_section,
                ft.Container(height=1, bgcolor=colors["border"]),
            ],
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        # Column 布局：可滚动内容 + 固定底部
        self.content = ft.Column(
            controls=[
                scrollable_content,
                actions_section,  # 固定在底部
            ],
            spacing=0,
            alignment=ft.MainAxisAlignment.START,  # 内容顶部对齐
        )

    def _build_character_section(self, colors: dict) -> ft.Container:
        """Build character info section."""
        self._avatar = ft.Container(
            width=48,
            height=48,
            border_radius=24,
            bgcolor=colors["surface"],
            content=ft.Icon(ft.Icons.PERSON, size=24, color=colors["text_secondary"]),
        )

        self._character_name = ft.Text(
            "Assistant",
            size=16,
            weight=ft.FontWeight.W_600,
            color=colors["text"],
        )

        self._character_status = ft.Container(
            padding=ft.padding.symmetric(horizontal=8, vertical=2),
            bgcolor=colors["primary"],
            border_radius=12,
            content=ft.Text("Online", size=11, color="#FFFFFF"),
        )

        return ft.Container(
            padding=ft.padding.all(16),
            content=ft.Row(
                controls=[
                    self._avatar,
                    ft.Container(width=12),
                    ft.Column(
                        controls=[
                            self._character_name,
                            ft.Container(height=4),
                            self._character_status,
                        ],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def _build_navigation_section(self, colors: dict) -> ft.Container:
        """Build navigation section with chat history."""
        self._history_list = ft.Column(controls=[], spacing=2)

        # Placeholder history items
        self._add_history_item("New Chat", "Start a new conversation", colors)
        self._add_history_item("Previous Chat 1", "Hello, how are you?", colors)
        self._add_history_item("Previous Chat 2", "Tell me a story", colors)

        return ft.Container(
            padding=ft.padding.all(16),
            content=ft.Column(
                controls=[
                    ft.Text(
                        "Chats",
                        size=12,
                        color=colors["text_secondary"],
                        weight=ft.FontWeight.W_500,
                    ),
                    ft.Container(height=12),
                    self._history_list,
                ],
                spacing=0,
            ),
        )

    def _add_history_item(self, title: str, subtitle: str, colors: dict) -> None:
        """Add a history item to the list."""
        item = ft.Container(
            padding=ft.padding.symmetric(horizontal=12, vertical=10),
            border_radius=8,
            on_click=self._handle_history_click,
            content=ft.Column(
                controls=[
                    ft.Text(
                        title,
                        size=14,
                        color=colors["text"],
                        weight=ft.FontWeight.W_500,
                    ),
                    ft.Text(
                        subtitle,
                        size=12,
                        color=colors["text_secondary"],
                        max_lines=1,
                    ),
                ],
                spacing=2,
            ),
        )
        self._history_list.controls.append(item)

    def _handle_history_click(self, e) -> None:
        """Handle history item click."""
        if self._on_history_select:
            title = e.control.content.controls[0].value
            self._on_history_select(title)

    def _build_settings_section(self, colors: dict) -> ft.Container:
        """Build settings section."""
        self._settings_panel = SettingsPanel(
            dark_mode=self._dark_mode,
            colors=colors,
            on_setting_change=self._handle_setting_change,
        )

        return ft.Container(
            padding=ft.padding.all(16),
            content=self._settings_panel,
        )

    def _handle_setting_change(self, key: str, value) -> None:
        """Handle settings change."""
        if self._on_settings_change:
            self._on_settings_change(key, value)

    def _build_actions_section(self, colors: dict) -> ft.Container:
        """Build export/import actions section."""
        self._export_btn = ft.TextButton(
            content=ft.Text("Export", size=13, color=colors["text_secondary"]),
            icon=ft.Icons.DOWNLOAD_OUTLINED,
            on_click=self._handle_export,
        )

        self._import_btn = ft.TextButton(
            content=ft.Text("Import", size=13, color=colors["text_secondary"]),
            icon=ft.Icons.UPLOAD_OUTLINED,
            on_click=self._handle_import,
        )

        return ft.Container(
            padding=ft.padding.all(16),
            content=ft.Row(
                controls=[self._export_btn, self._import_btn],
                spacing=8,
            ),
        )

    def _handle_export(self, e) -> None:
        """Handle export button click."""
        if self._on_export:
            self._on_export()

    def _handle_import(self, e) -> None:
        """Handle import button click."""
        if self._on_import:
            self._on_import()

    # Public API

    def update_character(self, character: Character) -> None:
        """Update character info."""
        if character.avatar_path:
            self._avatar.content = ft.Image(
                src=character.avatar_path,
                width=48,
                height=48,
                fit=BoxFit.COVER,
            )
        if character.name:
            self._character_name.value = character.name
        try:
            if self.page:
                self.update()
        except RuntimeError:
            pass

    def set_dark_mode(self, dark_mode: bool) -> None:
        """Update UI for theme change."""
        self._dark_mode = dark_mode
        self._colors = self._get_default_colors(dark_mode)
        self.bgcolor = self._colors["bg"]
        self._settings_panel.set_dark_mode(dark_mode)
        self._build_ui()
        self.update()

    def set_history(self, history: List[dict]) -> None:
        """Update chat history list."""
        colors = self._colors
        self._history_list.controls.clear()
        for item in history:
            self._add_history_item(
                item.get("title", ""),
                item.get("subtitle", ""),
                colors
            )
        self._history_list.update()

    def show(self) -> None:
        """Show the sidebar."""
        self.visible = True
        self.update()

    def hide(self) -> None:
        """Hide the sidebar."""
        self.visible = False
        self.update()

    def toggle(self) -> None:
        """Toggle sidebar visibility."""
        self.visible = not self.visible
        self.update()
