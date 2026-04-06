"""Speech bubble component with typewriter text effect."""

import flet as ft


class SpeechBubble(ft.Container):
    """
    AI speech bubble with typewriter text animation effect.
    Modern flat design. Responsive width.
    """

    def __init__(
        self,
        text: str = "",
        text_speed: int = 30,
        dark_mode: bool = True,
        bubble_color: str = None,
        text_color: str = None,
        on_typewriter_complete=None,
        **kwargs
    ):
        super().__init__(
            padding=ft.padding.symmetric(horizontal=31, vertical=20),  # 增大40%
            border_radius=ft.border_radius.only(top_left=26, top_right=26, bottom_left=8, bottom_right=26),
            **kwargs
        )

        self._text = text
        self._displayed_text = ""
        self._text_speed = text_speed
        self._on_typewriter_complete = on_typewriter_complete
        self._typewriter_running = False
        self._typewriter_index = 0
        self._page = None

        # Colors
        if dark_mode:
            self._bubble_color = bubble_color or "#262637"
            self._text_color = text_color or "#E4E4E7"
        else:
            self._bubble_color = bubble_color or "#F4F4F5"
            self._text_color = text_color or "#18181B"

        self._text_control = ft.Text(
            value="",
            size=19,  # 增大字体
            color=self._text_color,
            weight=ft.FontWeight.W_400,
        )

        self.bgcolor = self._bubble_color
        self.width = float("inf")  # Fill available width
        self.content = ft.Column(
            controls=[self._text_control],
            tight=True,
        )

    def set_text(self, text: str, animate: bool = True) -> None:
        """Set the bubble text, optionally with typewriter effect."""
        self._text = text

        if animate and text:
            self._start_typewriter()
        else:
            self._displayed_text = text
            self._text_control.value = text
            self.update()

    def _start_typewriter(self) -> None:
        """Start the typewriter animation."""
        self._typewriter_running = True
        self._typewriter_index = 0
        self._displayed_text = ""
        self._text_control.value = ""

        if self.page:
            self._page = self.page
            self._page.run_task(self._typewriter_loop)
        else:
            self._typewriter_running = False
            self._displayed_text = self._text
            self._text_control.value = self._text
            self.update()

    async def _typewriter_loop(self) -> None:
        """Async typewriter loop."""
        if not self._page:
            return

        while self._typewriter_running and self._typewriter_index < len(self._text):
            self._displayed_text += self._text[self._typewriter_index]
            self._text_control.value = self._displayed_text
            self._typewriter_index += 1
            self.update()
            await ft.sleep_async(self._text_speed / 1000.0)

        if self._typewriter_index >= len(self._text):
            self._typewriter_running = False
            if self._on_typewriter_complete:
                self._on_typewriter_complete()

    def skip_typewriter(self) -> None:
        """Immediately show full text."""
        self._typewriter_running = False
        self._displayed_text = self._text
        self._text_control.value = self._text
        self.update()


class UserBubble(ft.Container):
    """
    User message bubble - right aligned, instant display.
    Modern flat design. Responsive width.
    """

    def __init__(
        self,
        text: str = "",
        dark_mode: bool = True,
        bubble_color: str = None,
        **kwargs
    ):
        super().__init__(
            padding=ft.padding.symmetric(horizontal=20, vertical=14),
            border_radius=ft.border_radius.only(top_left=20, top_right=20, bottom_left=20, bottom_right=4),
            **kwargs
        )

        # User bubble is always primary color
        self._bubble_color = bubble_color or "#6366F1"
        self._text_color = "#FFFFFF"

        self.bgcolor = self._bubble_color
        self.width = 350  # Fixed width for consistency
        self.alignment = ft.Alignment(1, 0)

        self.content = ft.Text(
            value=text,
            size=15,
            color=self._text_color,
            weight=ft.FontWeight.W_400,
        )

    def set_text(self, text: str) -> None:
        """Update the bubble text."""
        self.content.value = text
        self.update()
