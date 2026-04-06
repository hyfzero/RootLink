"""Chat view - main chat interface with galgame-style display."""

import flet as ft
from typing import Optional, Callable

from .components import (
    CharacterSprite,
    SpeechBubble,
    ChatInput,
)
from .interfaces import ChatMessage, Character


class ChatView(ft.Container):
    """
    Main chat view with character sprite, speech bubble, and message list.
    Implements galgame-style conversation display.
    """

    def __init__(
        self,
        dark_mode: bool = True,
        colors: dict = None,
        text_speed: int = 30,
        on_message_send: Optional[Callable] = None,
        on_sprite_tap: Optional[Callable] = None,
        **kwargs
    ):
        super().__init__(expand=True, **kwargs)

        self._dark_mode = dark_mode
        self._colors = colors or self._get_default_colors(dark_mode)
        self._text_speed = text_speed
        self._on_message_send = on_message_send
        self._on_sprite_tap = on_sprite_tap

        self._build_ui()

    def _get_default_colors(self, dark_mode: bool) -> dict:
        """Get default color palette."""
        if dark_mode:
            return {
                "bg": "#0F0F0F",
                "surface": "#1C1C1C",
                "primary": "#6366F1",
                "text": "#FFFFFF",
                "text_secondary": "#A1A1AA",
                "bubble_ai": "#262637",
                "bubble_user": "#6366F1",
            }
        else:
            return {
                "bg": "#FAFAFA",
                "surface": "#FFFFFF",
                "primary": "#6366F1",
                "text": "#18181B",
                "text_secondary": "#71717A",
                "bubble_ai": "#F4F4F5",
                "bubble_user": "#6366F1",
            }

    def set_colors(self, colors: dict) -> None:
        """Update colors."""
        self._colors = colors

    def _build_ui(self) -> None:
        """Build the chat view UI components."""
        self.bgcolor = self._colors["bg"]

        self._build_sprite_area()
        self._build_input_area()

        # Sprite 60% + Bubble 20% + Input 固定高度
        # 使用 expand 比例: sprite(6) + bubble(2) = 8份, 输入框固定
        self.content = ft.Column(
            controls=[
                self._sprite_container,  # 60% - Sprite + Bubble
                self._input_container,  # 固定高度
            ],
            spacing=0,
            expand=True,
        )

    def _build_sprite_area(self) -> None:
        """Build the character sprite and speech bubble area. Galgame style: sprite 60%, bubble 20%."""
        colors = self._colors

        # Character sprite - galgame style large sprite
        self._sprite = CharacterSprite(
            on_tap=self._handle_sprite_tap,
            dark_mode=self._dark_mode,
        )

        # Speech bubble - below sprite
        self._bubble = SpeechBubble(
            text_speed=self._text_speed,
            dark_mode=self._dark_mode,
            bubble_color=colors["bubble_ai"],
            text_color=colors["text"],
        )

        # 角色区域 - Stack 布局，bubble 叠加在 sprite 上面
        self._sprite_container = ft.Container(
            content=ft.Stack(
                controls=[
                    # 立绘 - 底层
                    self._sprite,
                    # 对话框 - 顶层，底部中央，带 padding
                    ft.Container(
                        content=self._bubble,
                        alignment=ft.Alignment(0, 1),  # 底部居中
                        padding=ft.padding.symmetric(horizontal=24, vertical=16),  # 四周留白
                        bottom=20,  # 距离底部
                        left=40,    # 距离左边
                        right=40,   # 距离右边
                    ),
                ],
                expand=True,
            ),
            padding=ft.padding.all(8),
            expand=True,
        )

    def _build_input_area(self) -> None:
        """Build the message input area."""
        colors = self._colors

        self._input_container = ft.Container(
            bgcolor=colors["surface"],
            border=ft.Border(
                top=ft.BorderSide(1, colors.get("border", "#3F3F46"))
            ),
            content=ChatInput(
                on_send=self._handle_message_send,
                dark_mode=self._dark_mode,
                colors=colors,
            ),
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
            height=60,
        )

    def _handle_message_send(self, text: str) -> None:
        """Handle message send from input."""
        if self._on_message_send:
            self._on_message_send(text)

    def _handle_sprite_tap(self, e) -> None:
        """Handle sprite tap event."""
        if self._on_sprite_tap:
            self._on_sprite_tap()

    # Public API for Control layer

    def append_message(self, message: ChatMessage) -> None:
        """Append a message to the chat view. Galgame style: only AI messages shown."""
        if message.is_user:
            # User message - not displayed in galgame style (just input)
            return

        # AI message - show in speech bubble
        self._bubble.set_text(message.text, animate=True)

    def show_ai_message(self, text: str, animate: bool = True) -> None:
        """Show AI message in speech bubble."""
        self._bubble.set_text(text, animate=animate)

    def update_character(self, character: Character) -> None:
        """Update the character sprite."""
        self._sprite.set_sprite(character.sprite_path, character.name)

    def set_sprite_speaking(self, speaking: bool) -> None:
        """Set sprite speaking animation state."""
        self._sprite.set_speaking(speaking)

    def show_typing_indicator(self, visible: bool) -> None:
        """Show typing indicator."""
        self._sprite.set_speaking(visible)

    def clear_chat(self) -> None:
        """Clear all messages and reset bubble."""
        self._bubble.set_text("", animate=False)
        self.update()

    def set_dark_mode(self, dark_mode: bool) -> None:
        """Update UI for theme change."""
        self._dark_mode = dark_mode
        self._colors = self._get_default_colors(dark_mode)
        self.bgcolor = self._colors["bg"]
        self._build_ui()
        self.update()

    def set_text_speed(self, speed: int) -> None:
        """Update text speed for typewriter effect."""
        self._text_speed = speed
        self._bubble._text_speed = speed

    def focus_input(self) -> None:
        """Focus the message input field."""
        self._input_container.content.focus()

    def get_input(self) -> ChatInput:
        """Get the chat input component."""
        return self._input_container.content
