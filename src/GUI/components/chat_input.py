"""Chat input component for message composition."""

import flet as ft


class ChatInput(ft.Container):
    """
    Message input field with send button.
    Modern flat design.
    """

    def __init__(
        self,
        on_send=None,
        on_attachment=None,
        dark_mode: bool = True,
        colors: dict = None,
        placeholder: str = "Type a message...",
        **kwargs
    ):
        super().__init__(**kwargs)

        self._on_send = on_send
        self._on_attachment = on_attachment
        self._colors = colors or self._get_default_colors(dark_mode)

        bg_color = self._colors.get("surface", "#1C1C1C")
        input_bg = self._colors.get("bg", "#0F0F0F")
        input_color = self._colors.get("text", "#FFFFFF")
        placeholder_color = self._colors.get("text_secondary", "#A1A1AA")
        primary = self._colors.get("primary", "#6366F1")

        self._text_field = ft.TextField(
            hint_text=placeholder,
            hint_style=ft.TextStyle(color=placeholder_color),
            text_style=ft.TextStyle(color=input_color, size=15),
            bgcolor=input_bg,
            border_radius=24,
            filled=True,
            fill_color=input_bg,
            border_color="transparent",
            focused_border_color=primary,
            on_submit=self._handle_send,
            content_padding=ft.padding.symmetric(horizontal=16, vertical=12),
            multiline=False,
        )

        self._send_btn = ft.Container(
            width=40,
            height=40,
            border_radius=20,
            bgcolor=primary,
            on_click=self._handle_send,
            content=ft.Icon(ft.Icons.SEND, size=20, color="#FFFFFF"),
        )

        self._attach_btn = ft.Container(
            width=40,
            height=40,
            border_radius=20,
            on_click=self._handle_attachment,
            content=ft.Icon(ft.Icons.ATTACH_FILE, size=20, color=placeholder_color),
        )

        self.content = ft.Row(
            controls=[
                self._attach_btn,
                ft.Container(width=8),
                self._text_field,  # expand=True is set on the TextField below
                ft.Container(width=8),
                self._send_btn,
            ],
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        )

        # TextField expands to fill available space
        self._text_field.expand = True

        self._text_field.on_change = self._on_input_change

    def _get_default_colors(self, dark_mode: bool) -> dict:
        """Get default color palette."""
        if dark_mode:
            return {
                "bg": "#0F0F0F",
                "surface": "#1C1C1C",
                "primary": "#6366F1",
                "text": "#FFFFFF",
                "text_secondary": "#A1A1AA",
            }
        else:
            return {
                "bg": "#FAFAFA",
                "surface": "#FFFFFF",
                "primary": "#6366F1",
                "text": "#18181B",
                "text_secondary": "#71717A",
            }

    def _on_input_change(self, e) -> None:
        """Enable/disable send button based on input."""
        has_text = bool(self._text_field.value and self._text_field.value.strip())
        self._send_btn.bgcolor = self._colors.get("primary", "#6366F1") if has_text else "#3F3F46"
        self.update()

    def _handle_send(self, e) -> None:
        """Handle send action."""
        text = self._text_field.value
        if text and text.strip():
            if self._on_send:
                self._on_send(text.strip())
            self._text_field.value = ""
            self._send_btn.bgcolor = "#3F3F46"
            self.update()

    def _handle_attachment(self, e) -> None:
        """Handle attachment action."""
        if self._on_attachment:
            self._on_attachment()

    def get_value(self) -> str:
        """Get current input text."""
        return self._text_field.value or ""

    def clear(self) -> None:
        """Clear the input field."""
        self._text_field.value = ""
        self._send_btn.bgcolor = "#3F3F46"
        self.update()

    def focus(self) -> None:
        """Focus the text input."""
        self._text_field.focus()
