"""Settings panel component for sidebar."""

import flet as ft


class SettingsPanel(ft.Container):
    """
    Settings panel with theme toggle and other options.
    Modern flat design.
    """

    def __init__(
        self,
        settings: dict = None,
        colors: dict = None,
        on_setting_change=None,
        dark_mode: bool = True,
        **kwargs
    ):
        super().__init__(**kwargs)

        self._settings = settings or {
            "theme": "dark" if dark_mode else "light",
            "text_speed": 30,
            "auto_scroll": True,
        }
        self._colors = colors or self._get_default_colors(dark_mode)
        self._on_setting_change = on_setting_change
        self._dark_mode = dark_mode

        self._build_content()

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
            }
        else:
            return {
                "bg": "#FFFFFF",
                "surface": "#F4F4F5",
                "primary": "#6366F1",
                "text": "#18181B",
                "text_secondary": "#71717A",
                "border": "#E4E4E7",
            }

    def _build_content(self) -> None:
        """Build the settings panel content."""
        colors = self._colors

        # Theme toggle
        self._theme_toggle = ft.Row(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.DARK_MODE, size=18, color=colors["text_secondary"]),
                        ft.Text("Dark Mode", color=colors["text"], size=14),
                    ],
                ),
                ft.Switch(
                    value=self._settings.get("theme", "dark") == "dark",
                    on_change=self._on_theme_change,
                    active_color=colors["primary"],
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        # Text speed slider
        self._speed_slider = ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.SPEED, size=18, color=colors["text_secondary"]),
                        ft.Text("Text Speed", color=colors["text"], size=14),
                    ],
                ),
                ft.Row(
                    controls=[
                        ft.Slider(
                            min=10,
                            max=100,
                            divisions=9,
                            value=self._settings.get("text_speed", 30),
                            on_change=self._on_speed_change,
                            active_color=colors["primary"],
                        ),
                        ft.Container(
                            width=40,
                            content=ft.Text(
                                f"{self._settings.get('text_speed', 30)}ms",
                                color=colors["text_secondary"],
                                size=12,
                            ),
                        ),
                    ],
                ),
            ],
            spacing=8,
        )

        # Auto scroll toggle
        self._auto_scroll_toggle = ft.Row(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.VERTICAL_ALIGN_BOTTOM, size=18, color=colors["text_secondary"]),
                        ft.Text("Auto Scroll", color=colors["text"], size=14),
                    ],
                ),
                ft.Switch(
                    value=self._settings.get("auto_scroll", True),
                    on_change=self._on_auto_scroll_change,
                    active_color=colors["primary"],
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        # Clear chat button
        self._clear_btn = ft.Container(
            on_click=self._on_clear_chat,
            padding=ft.padding.symmetric(horizontal=16, vertical=10),
            border_radius=8,
            bgcolor="#EF4444",
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.DELETE_OUTLINE, size=18, color="#FFFFFF"),
                    ft.Text("Clear Chat", color="#FFFFFF", size=14),
                ],
                spacing=8,
            ),
        )

        self.content = ft.Column(
            controls=[
                ft.Text(
                    "Settings",
                    size=12,
                    weight=ft.FontWeight.W_500,
                    color=colors["text_secondary"],
                ),
                ft.Container(height=16),
                ft.Column(
                    controls=[
                        self._theme_toggle,
                        ft.Container(height=16),
                        self._speed_slider,
                        ft.Container(height=16),
                        self._auto_scroll_toggle,
                    ],
                    spacing=12,
                ),
                ft.Container(height=16),
                self._clear_btn,
            ],
            spacing=0,
        )

    def _on_theme_change(self, e) -> None:
        """Handle theme toggle change."""
        new_theme = "dark" if e.control.value else "light"
        self._settings["theme"] = new_theme
        if self._on_setting_change:
            self._on_setting_change("theme", new_theme)

    def _on_speed_change(self, e) -> None:
        """Handle text speed slider change."""
        speed = int(e.control.value)
        self._settings["text_speed"] = speed
        self._speed_slider.controls[1].controls[1].content.value = f"{speed}ms"
        self._speed_slider.controls[1].update()
        if self._on_setting_change:
            self._on_setting_change("text_speed", speed)

    def _on_auto_scroll_change(self, e) -> None:
        """Handle auto scroll toggle change."""
        self._settings["auto_scroll"] = e.control.value
        if self._on_setting_change:
            self._on_setting_change("auto_scroll", e.control.value)

    def _on_clear_chat(self, e) -> None:
        """Handle clear chat button click."""
        if self._on_setting_change:
            self._on_setting_change("clear_chat", True)

    def update_settings(self, settings: dict) -> None:
        """Update settings from external source."""
        self._settings = settings
        self._build_content()

    def set_dark_mode(self, dark_mode: bool) -> None:
        """Update colors for theme change."""
        self._dark_mode = dark_mode
        self._colors = self._get_default_colors(dark_mode)
        self._build_content()
        self.update()

    def set_colors(self, colors: dict) -> None:
        """Update colors."""
        self._colors = colors
        self._build_content()
        self.update()
