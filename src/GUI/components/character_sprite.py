"""Character sprite component with galgame-style display."""

import flet as ft
from flet.controls.box import BoxFit


class CharacterSprite(ft.Container):
    """
    Displays a character sprite/avatar in the chat view.
    Modern flat design with subtle animation.
    Responsive - scales with parent container.
    """

    def __init__(
        self,
        sprite_path: str = "",
        name: str = "",
        on_tap=None,
        dark_mode: bool = True,
        **kwargs
    ):
        super().__init__(
            on_click=on_tap,
            expand=True,
            **kwargs
        )

        self._sprite_path = sprite_path
        self._name = name
        self._is_speaking = False
        self._dark_mode = dark_mode

        # Colors
        if dark_mode:
            bg_color = "#1C1C1C"
            icon_color = "#3F3F46"
            text_color = "#A1A1AA"
        else:
            bg_color = "#F4F4F5"
            icon_color = "#D4D4D8"
            text_color = "#71717A"

        self._image = ft.Image(
            src=self._sprite_path if self._sprite_path else None,
            fit=BoxFit.CONTAIN,
            visible=True if self._sprite_path else False,
        )

        self._placeholder = ft.Container(
            bgcolor=bg_color,
            border_radius=16,
            content=ft.Column(
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=60,
                        height=60,
                        border_radius=30,
                        bgcolor=icon_color,
                        content=ft.Icon(ft.Icons.PERSON, size=30, color=text_color),
                    ),
                    ft.Container(height=8),
                    ft.Text(
                        self._name or "Character",
                        size=12,
                        color=text_color,
                        weight=ft.FontWeight.W_500,
                    ),
                ],
            ),
            visible=False if self._sprite_path else True,
        )

        self.content = ft.Stack([self._placeholder, self._image])

    def set_sprite(self, sprite_path: str, name: str = "") -> None:
        """Update the sprite image and name."""
        self._sprite_path = sprite_path
        self._name = name

        if sprite_path:
            self._image.src = sprite_path
            self._image.visible = True
            self._placeholder.visible = False
        else:
            self._image.visible = False
            self._placeholder.visible = True

    def set_speaking(self, speaking: bool) -> None:
        """Enable or disable speaking animation."""
        if self._is_speaking != speaking:
            self._is_speaking = speaking
            # Subtle scale animation for speaking state
            self.scale = 1.02 if speaking else 1.0
            self.update()
