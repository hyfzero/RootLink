"""Figma mobile-first view implementation using Flet controls."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import flet as ft

from .components import (
    ChatInputBar,
    FormField,
    IMAGE_CONTAIN,
    MemoryEditor,
    MessageBubble,
    MessageBubbleEntry,
    MotionEntry,
    QuickAction,
    RecentChatRow,
    RoleFeatureCard,
    RoleSelectorCard,
    StaggerEntry,
    TypingDots,
    animated_click,
    avatar,
    round_icon_button,
    section_card,
    text,
)
from .interfaces import (
    CharacterDraft,
    ChatMessage,
    CompanionRole,
    CompanionUICallback,
    CompanionUIView,
    MemoryDraft,
    UiSettings,
    UserProfile,
)
from .theme import (
    DEFAULT_ROLE_DATA,
    MOBILE_WIDTH,
    MOTION,
    animation,
    app_gradient,
    character_chat_gradient,
    hex_with_alpha,
    palette,
    soft_shadow,
)

SETTINGS_PROVIDERS = [
    ("openai", "OpenAI"),
    ("anthropic", "Anthropic"),
    ("google", "Google"),
    ("deepseek", "DeepSeek"),
    ("custom", "Custom"),
]

PORTRAIT_EMOTIONS = [
    ("neutral", "Neutral"),
    ("happy", "Happy"),
    ("sad", "Sad"),
    ("angry", "Angry"),
    ("surprised", "Surprised"),
]

CREATE_STEPS = ["Basic", "Portraits", "Personality", "Memory", "Style"]


def default_roles() -> list[CompanionRole]:
    return [CompanionRole(**item) for item in DEFAULT_ROLE_DATA]


class NoopCallback(CompanionUICallback):
    """Fallback callback so the UI can run standalone."""


class CompanionAppView(ft.Container, CompanionUIView):
    VALID_PAGES = ("home", "chat", "settings", "create")

    def __init__(
        self,
        callback: Optional[CompanionUICallback] = None,
        roles: Optional[list[CompanionRole]] = None,
        is_dark: bool = True,
    ) -> None:
        super().__init__(expand=True)
        self._callback = callback or NoopCallback()
        self._roles = roles or default_roles()
        self._active_role_id = self._roles[0].id if self._roles else ""
        self._page_name = "home"
        self._is_dark = is_dark
        self._chat_mode = "normal"
        self._chat_mode_seed = 0
        self._messages = self._seed_messages(self.active_role)
        self._seen_message_ids = {message.id for message in self._messages}
        self._typing = False
        self._settings = UiSettings(is_dark=is_dark)
        self._profile = UserProfile(name=self._settings.user_name)
        self._draft = CharacterDraft()
        self._create_step = 1
        self._create_step_seed = 0
        self._create_step_direction = 1
        self._emotion_id = "neutral"
        self._trait_field: Optional[ft.TextField] = None
        self._interest_field: Optional[ft.TextField] = None
        self._memory_editors: list[MemoryEditor] = []
        self.motion_enabled = True
        self._page_seed = {page: 0 for page in self.VALID_PAGES}
        self._build()

    @property
    def active_role(self) -> CompanionRole:
        for role in self._roles:
            if role.id == self._active_role_id:
                return role
        return self._roles[0]

    def _seed_messages(self, role: CompanionRole) -> list[ChatMessage]:
        seed = {
            "amadeus": "I remember where we stopped last time.",
            "shinji": "I am here. You can speak slowly.",
            "asuka": "Stop holding it alone. Say it directly.",
        }.get(role.id, "I am ready.")
        return [
            ChatMessage("seed-1", role.id, seed, False, datetime.now()),
            ChatMessage("seed-2", role.id, "Understood. Keep going.", True, datetime.now()),
            ChatMessage("seed-3", role.id, role.last_message or role.status_text, False, datetime.now()),
        ]

    def _colors(self) -> dict[str, str]:
        return palette(self._is_dark)

    def _touch_page(self, page: str) -> None:
        self._page_seed[page] = self._page_seed.get(page, 0) + 1

    def _build(self) -> None:
        colors = self._colors()
        page_content = self._build_current_page(colors)
        page_content.key = f"page-{self._page_name}-{self._page_seed[self._page_name]}-{self._active_role_id}-{self._chat_mode}-{self._create_step}"
        self.gradient = app_gradient(self._is_dark)
        self.content = ft.Row(
            expand=True,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                ft.Container(
                    width=MOBILE_WIDTH,
                    expand=True,
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                    content=ft.AnimatedSwitcher(
                        content=page_content,
                        duration=MOTION["normal"],
                        reverse_duration=MOTION["fast"],
                        switch_in_curve=ft.AnimationCurve.FAST_OUT_SLOWIN,
                        switch_out_curve=ft.AnimationCurve.EASE_IN_OUT,
                        transition=ft.AnimatedSwitcherTransition.FADE,
                    ),
                )
            ],
        )

    def _safe_update(self) -> None:
        self._build()
        try:
            self.update()
        except (AssertionError, RuntimeError):
            pass

    def _stagger(
        self,
        page: str,
        index: int,
        control: ft.Control,
        *,
        offset_y: float = 0.05,
        offset_x: float = 0.0,
        scale_from: float = 1.0,
    ) -> ft.Control:
        if not self.motion_enabled:
            return control
        return StaggerEntry(
            content=control,
            index=index,
            offset_y=offset_y,
            offset_x=offset_x,
            scale_from=scale_from,
            duration_name="slow",
            key=f"{page}-{self._page_seed.get(page, 0)}-{index}-{self._active_role_id}-{self._create_step}",
        )

    def _page_column(self, controls: list[ft.Control], scroll: bool = True) -> ft.Column:
        return ft.Column(
            controls=controls,
            spacing=0,
            expand=True,
            scroll=ft.ScrollMode.AUTO if scroll else None,
        )

    def _build_current_page(self, colors: dict[str, str]) -> ft.Control:
        if self._page_name == "chat":
            return self._build_chat_page(colors)
        if self._page_name == "settings":
            return self._build_settings_page(colors)
        if self._page_name == "create":
            return self._build_create_page(colors)
        return self._build_home_page(colors)

    def _build_home_page(self, colors: dict[str, str]) -> ft.Control:
        selected = self.active_role
        role_cards = [RoleSelectorCard(role, role.id == selected.id, self._is_dark, self.set_active_role) for role in self._roles]
        role_cards.append(self._create_selector_card(colors))
        controls = [
            self._stagger(
                "home",
                0,
                ft.Container(
                    padding=ft.padding.only(left=20, right=20, top=26, bottom=18),
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Container(
                                padding=ft.padding.symmetric(horizontal=15, vertical=10),
                                border_radius=22,
                                bgcolor=colors["card"],
                                border=ft.border.all(1, colors["card_border"]),
                                ink=True,
                                scale=1.0,
                                animate_scale=animation("fast", phase="press"),
                                on_click=animated_click(lambda _: self._toggle_theme()),
                                content=ft.Row(
                                    spacing=8,
                                    controls=[
                                        ft.Icon(ft.Icons.DARK_MODE if self._is_dark else ft.Icons.LIGHT_MODE, size=17, color=colors["text"]),
                                        text("Dark" if self._is_dark else "Light", 12, colors["text"]),
                                    ],
                                ),
                            ),
                            round_icon_button(ft.Icons.SETTINGS_OUTLINED, colors, lambda _: self.show_page("settings")),
                        ],
                    ),
                ),
            ),
            self._stagger(
                "home",
                1,
                ft.Container(
                    padding=ft.padding.symmetric(horizontal=20),
                    content=ft.Column(
                        spacing=7,
                        controls=[
                            text("Welcome back", 28, colors["text"], ft.FontWeight.W_500),
                            text("Choose a companion and continue your conversation.", 15, colors["text_secondary"]),
                        ],
                    ),
                ),
            ),
            self._stagger("home", 2, RoleFeatureCard(selected, self._is_dark, self._open_chat), offset_y=0.04, scale_from=0.98),
            self._stagger(
                "home",
                3,
                ft.Container(height=190, content=ft.Row(spacing=12, scroll=ft.ScrollMode.AUTO, controls=role_cards)),
            ),
            self._stagger(
                "home",
                4,
                ft.Row(
                    spacing=12,
                    controls=[
                        ft.Container(expand=True, content=QuickAction("Create role", "Start a 5-step wizard", ft.Icons.ADD, colors, lambda _: self.show_page("create"))),
                        ft.Container(expand=True, content=QuickAction("Open chat", "Jump to current role", ft.Icons.CHAT_BUBBLE_OUTLINE, colors, lambda _: self._open_chat(selected.id))),
                    ],
                ),
            ),
            self._stagger(
                "home",
                5,
                ft.Column(
                    spacing=12,
                    controls=[text("Recent chats", 15, colors["text_secondary"]), *[RecentChatRow(role, self._is_dark, self._open_chat) for role in self._roles]],
                ),
            ),
            ft.Container(height=28),
        ]
        return self._page_column([ft.Container(padding=ft.padding.symmetric(horizontal=20), content=ft.Column(spacing=24, controls=controls))])

    def _create_selector_card(self, colors: dict[str, str]) -> ft.Container:
        return ft.Container(
            width=140,
            padding=14,
            border_radius=18,
            bgcolor=colors["card"],
            border=ft.border.all(1, colors["card_border"]),
            ink=True,
            scale=1.0,
            animate_scale=animation("fast", phase="press"),
            animate_opacity=animation("fast", phase="press"),
            on_click=animated_click(lambda _: self.show_page("create")),
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=9,
                controls=[
                    ft.Container(width=56, height=56, border_radius=28, bgcolor=colors["muted"], alignment=ft.Alignment(0, 0), content=ft.Icon(ft.Icons.AUTO_AWESOME, size=22, color=colors["text_secondary"])),
                    text("Create role", 13, colors["text_secondary"], text_align=ft.TextAlign.CENTER),
                    text("New companion", 10, colors["text_tertiary"], text_align=ft.TextAlign.CENTER),
                ],
            ),
        )

    def _build_chat_page(self, colors: dict[str, str]) -> ft.Control:
        role = self.active_role
        header = ft.Container(
            padding=ft.padding.only(left=16, right=16, top=26, bottom=12),
            border=ft.border.only(bottom=ft.BorderSide(1, colors["card_border"])),
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    round_icon_button(ft.Icons.ARROW_BACK, colors, lambda _: self.show_page("home"), 36),
                    ft.Row(
                        expand=True,
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=10,
                        controls=[
                            avatar(role.avatar_path, 36, colors["card_border"]),
                            ft.Column(
                                spacing=2,
                                controls=[
                                    text(role.name, 15, colors["text"], ft.FontWeight.W_500),
                                    text(role.status_text, 11, colors["text_secondary"], max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                ],
                            ),
                        ],
                    ),
                    self._mode_switch(colors),
                ],
            ),
        )
        body = self._build_normal_chat(colors, role) if self._chat_mode == "normal" else self._build_immersive_chat(colors, role)
        if self.motion_enabled:
            body = MotionEntry(
                content=body,
                offset=ft.Offset(-0.05, 0) if self._chat_mode == "normal" else ft.Offset(0, 0.03),
                scale_from=1.0 if self._chat_mode == "normal" else 0.97,
                duration_name="normal",
                key=f"chat-body-{self._chat_mode}-{self._chat_mode_seed}",
            )
        return ft.Container(
            gradient=character_chat_gradient(role.id if self._chat_mode == "immersive" else "amadeus", self._is_dark),
            content=ft.Column(
                expand=True,
                spacing=0,
                controls=[
                    header,
                    ft.Container(
                        expand=True,
                        content=ft.AnimatedSwitcher(
                            content=body,
                            duration=MOTION["normal"],
                            reverse_duration=MOTION["fast"],
                            switch_in_curve=ft.AnimationCurve.FAST_OUT_SLOWIN,
                            switch_out_curve=ft.AnimationCurve.EASE_IN_OUT,
                            transition=ft.AnimatedSwitcherTransition.FADE,
                        ),
                    ),
                    ChatInputBar(role=role, is_dark=self._is_dark, mode=self._chat_mode, on_send=self._send_message, on_voice=lambda _: self._callback.on_voice_requested()),
                ],
            ),
        )

    def _mode_switch(self, colors: dict[str, str]) -> ft.Container:
        return ft.Container(
            padding=4,
            border_radius=16,
            bgcolor=colors["card"],
            border=ft.border.all(1, colors["card_border"]),
            content=ft.Row(spacing=4, controls=[self._mode_button("normal", "Chat", colors), self._mode_button("immersive", "Immersive", colors)]),
        )

    def _mode_button(self, mode: str, label: str, colors: dict[str, str]) -> ft.Container:
        active = self._chat_mode == mode
        return ft.Container(
            padding=ft.padding.symmetric(horizontal=10, vertical=7),
            border_radius=12,
            bgcolor=hex_with_alpha(self.active_role.accent_color, 58 if active else 0) if active else None,
            border=ft.border.all(1, hex_with_alpha(self.active_role.accent_color, 70) if active else colors["card_border"]),
            ink=True,
            scale=1.0,
            animate_scale=animation("fast", phase="press"),
            animate_opacity=animation("normal"),
            on_click=animated_click(lambda _: self._set_chat_mode(mode)),
            content=text(label, 11, colors["text"] if active else colors["text_secondary"]),
        )

    def _build_normal_chat(self, colors: dict[str, str], role: CompanionRole) -> ft.Control:
        chat_messages = [message for message in self._messages if message.role_id == role.id]
        controls: list[ft.Control] = []
        for message in chat_messages:
            bubble = MessageBubble(message, role, self._is_dark)
            if self.motion_enabled and message.id not in self._seen_message_ids:
                controls.append(MessageBubbleEntry(bubble, key=f"msg-{message.id}"))
                self._seen_message_ids.add(message.id)
            else:
                controls.append(bubble)
        if self._typing:
            controls.append(self._typing_indicator(role, colors))
        return ft.Container(
            padding=ft.padding.symmetric(horizontal=16, vertical=10),
            content=ft.ListView(controls=controls, spacing=12, auto_scroll=True, expand=True),
        )

    def _typing_indicator(self, role: CompanionRole, colors: dict[str, str]) -> ft.Control:
        return ft.Row(
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                avatar(role.avatar_path, 32, colors["card_border"]),
                ft.Container(
                    padding=ft.padding.symmetric(horizontal=12, vertical=10),
                    border_radius=14,
                    bgcolor=colors["message"],
                    border=ft.border.all(1, colors["message_border"]),
                    content=TypingDots(colors["text_secondary"]),
                ),
            ],
        )

    def _build_immersive_chat(self, colors: dict[str, str], role: CompanionRole) -> ft.Control:
        latest = next((m.text for m in reversed(self._messages) if m.role_id == role.id and not m.is_user), role.status_text)
        portrait: ft.Control = ft.Container(
            alignment=ft.Alignment(0, 1),
            content=ft.Image(src=role.standing_image_path, fit=IMAGE_CONTAIN, width=390, height=620),
        )
        dialogue: ft.Control = ft.Container(
            alignment=ft.Alignment(0, 1),
            margin=ft.margin.only(left=16, right=16, bottom=14),
            padding=ft.padding.symmetric(horizontal=16, vertical=14),
            border_radius=16,
            bgcolor=hex_with_alpha("#FFFFFF", 28 if self._is_dark else 220),
            border=ft.border.all(1, hex_with_alpha("#FFFFFF", 42 if self._is_dark else 58)),
            shadow=soft_shadow(self._is_dark, role.accent_color, "card"),
            content=text(latest, 14, colors["text"], max_lines=4, overflow=ft.TextOverflow.ELLIPSIS),
        )
        if self.motion_enabled:
            portrait = MotionEntry(content=portrait, delay_ms=200, offset=ft.Offset(0, 0.08), duration_name="slow", key=f"portrait-{self._chat_mode_seed}")
            dialogue = MotionEntry(content=dialogue, delay_ms=400, offset=ft.Offset(0, 0.06), duration_name="medium", key=f"dialogue-{self._chat_mode_seed}")
        return ft.Stack(expand=True, controls=[ft.Container(expand=True, bgcolor=hex_with_alpha("#000000", 14 if self._is_dark else 0)), portrait, dialogue])

    def _build_settings_page(self, colors: dict[str, str]) -> ft.Control:
        self._settings_name_field = FormField("Display name", "Your nickname", colors)
        self._settings_name_field.value = self._settings.user_name
        self._quality_slider = ft.Slider(
            min=0,
            max=100,
            divisions=20,
            value=self._settings.token_quality,
            active_color=self.active_role.accent_color,
            inactive_color=colors["muted"],
        )
        self._provider_dropdown = ft.Dropdown(
            label="Model provider",
            value=self._settings.model_provider,
            options=[ft.dropdown.Option(key, label) for key, label in SETTINGS_PROVIDERS],
            text_size=12,
            border_radius=14,
            border_color=colors["input_border"],
            bgcolor=colors["input"],
            color=colors["text"],
        )
        self._api_key_field = FormField("API key", "sk-...", colors, password=True)
        self._api_key_field.value = self._settings.api_key

        controls = [
            self._stagger("settings", 0, self._header("Settings", colors, lambda _: self.show_page("home")), offset_y=0.02),
            self._stagger("settings", 1, self._settings_profile_card(colors)),
            self._stagger("settings", 2, section_card(self._quality_card(colors), colors)),
            self._stagger("settings", 3, section_card(self._provider_card(colors), colors)),
            self._stagger("settings", 4, section_card(self._api_key_card(colors), colors)),
            self._stagger("settings", 5, self._primary_button("Save", self.active_role.accent_color, lambda _: self._save_settings())),
            ft.Container(height=28),
        ]
        return self._page_column([ft.Container(padding=ft.padding.symmetric(horizontal=20), content=ft.Column(spacing=14, controls=controls))])

    def _settings_profile_card(self, colors: dict[str, str]) -> ft.Control:
        image_path = self._settings.user_avatar_path or self.active_role.avatar_path
        return section_card(
            ft.Column(
                spacing=12,
                controls=[
                    ft.Row(
                        spacing=12,
                        controls=[
                            avatar(image_path, 70, self.active_role.accent_color),
                            ft.Column(
                                expand=True,
                                spacing=3,
                                controls=[
                                    text("Profile", 13, colors["text_secondary"]),
                                    text("UI-only profile settings", 11, colors["text_tertiary"]),
                                ],
                            ),
                            round_icon_button(ft.Icons.UPLOAD_FILE, colors, lambda _: self._callback.on_avatar_upload_requested(), size=36),
                        ],
                    ),
                    self._settings_name_field,
                ],
            ),
            colors,
        )

    def _quality_card(self, colors: dict[str, str]) -> ft.Control:
        return ft.Column(
            spacing=8,
            controls=[
                text("Conversation quality", 13, colors["text_secondary"]),
                text("Balance quality and speed", 11, colors["text_tertiary"]),
                self._quality_slider,
            ],
        )

    def _provider_card(self, colors: dict[str, str]) -> ft.Control:
        provider_desc = {
            "openai": "GPT family",
            "anthropic": "Claude family",
            "google": "Gemini family",
            "deepseek": "DeepSeek family",
            "custom": "Custom endpoint",
        }.get(self._provider_dropdown.value or "openai", "GPT family")
        return ft.Column(
            spacing=8,
            controls=[
                text("Model source", 13, colors["text_secondary"]),
                self._provider_dropdown,
                text(provider_desc, 11, colors["text_tertiary"]),
            ],
        )

    def _api_key_card(self, colors: dict[str, str]) -> ft.Control:
        return ft.Column(spacing=8, controls=[text("Credentials", 13, colors["text_secondary"]), self._api_key_field])

    def _build_create_page(self, colors: dict[str, str]) -> ft.Control:
        step_content = self._build_create_step(colors)
        if self.motion_enabled:
            direction_x = -0.06 if self._create_step_direction > 0 else 0.06
            step_content = MotionEntry(
                content=step_content,
                offset=ft.Offset(direction_x, 0),
                duration_name="normal",
                key=f"create-step-{self._create_step}-{self._create_step_seed}",
            )
        step_switcher = ft.AnimatedSwitcher(
            content=step_content,
            duration=MOTION["normal"],
            reverse_duration=MOTION["fast"],
            switch_in_curve=ft.AnimationCurve.FAST_OUT_SLOWIN,
            switch_out_curve=ft.AnimationCurve.EASE_IN_OUT,
            transition=ft.AnimatedSwitcherTransition.FADE,
        )
        controls = [
            self._stagger("create", 0, self._header("Create Companion", colors, lambda _: self.show_page("home")), offset_y=0.02),
            self._stagger("create", 1, self._create_progress(colors)),
            self._stagger("create", 2, ft.Container(content=step_switcher), offset_y=0.03),
            self._stagger("create", 3, self._create_footer(colors), offset_y=0.03),
            ft.Container(height=24),
        ]
        return self._page_column([ft.Container(padding=ft.padding.symmetric(horizontal=20), content=ft.Column(spacing=16, controls=controls))])

    def _create_progress(self, colors: dict[str, str]) -> ft.Control:
        bars: list[ft.Control] = []
        for index in range(1, 6):
            active = index <= self._create_step
            bars.append(
                ft.Container(
                    expand=True,
                    height=6,
                    border_radius=4,
                    bgcolor=hex_with_alpha(self.active_role.accent_color, 180 if active else 60),
                    opacity=1.0 if active else 0.7,
                    animate_opacity=animation("normal"),
                    animate_scale=animation("normal"),
                    scale=1.0 if active else 0.96,
                )
            )
        return section_card(
            ft.Column(
                spacing=10,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[text(f"Step {self._create_step}/5", 13, colors["text"]), text(CREATE_STEPS[self._create_step - 1], 12, colors["text_secondary"])],
                    ),
                    ft.Row(spacing=8, controls=bars),
                ],
            ),
            colors,
        )

    def _create_footer(self, colors: dict[str, str]) -> ft.Control:
        return ft.Row(
            spacing=10,
            controls=[
                ft.Container(expand=True, content=self._secondary_button("Back", colors, lambda _: self._previous_step())),
                ft.Container(
                    expand=True,
                    content=self._primary_button("Create" if self._create_step == 5 else "Next", self.active_role.accent_color, lambda _: self._next_step()),
                ),
            ],
        )

    def _build_create_step(self, colors: dict[str, str]) -> ft.Control:
        if self._create_step == 1:
            return self._basic_step(colors)
        if self._create_step == 2:
            return self._portrait_step(colors)
        if self._create_step == 3:
            return self._personality_step(colors)
        if self._create_step == 4:
            return self._memory_step(colors)
        return self._speaking_step(colors)

    def _basic_step(self, colors: dict[str, str]) -> ft.Control:
        self._brain_id_field = FormField("Brain ID", "companion-id", colors)
        self._brain_id_field.value = self._draft.brain_id
        self._template_dropdown = ft.Dropdown(
            label="Template",
            value=self._draft.template or "default",
            options=[ft.dropdown.Option("default"), ft.dropdown.Option("empathetic"), ft.dropdown.Option("strict")],
            text_size=12,
            border_radius=14,
            border_color=colors["input_border"],
            bgcolor=colors["input"],
            color=colors["text"],
        )
        self._name_field = FormField("Name", "Companion name", colors)
        self._name_field.value = self._draft.name
        self._description_field = FormField("Description", "Short persona summary", colors, multiline=True)
        self._description_field.value = self._draft.description
        return section_card(
            ft.Column(
                spacing=12,
                controls=[text("Basic information", 18, colors["text"], ft.FontWeight.W_500), self._brain_id_field, self._template_dropdown, self._name_field, self._description_field],
            ),
            colors,
        )

    def _portrait_step(self, colors: dict[str, str]) -> ft.Control:
        chips = []
        for emotion_id, label in PORTRAIT_EMOTIONS:
            selected = emotion_id == self._emotion_id
            chips.append(
                ft.Container(
                    padding=ft.padding.symmetric(horizontal=10, vertical=7),
                    border_radius=14,
                    bgcolor=hex_with_alpha(self.active_role.accent_color, 58 if selected else 0),
                    border=ft.border.all(1, hex_with_alpha(self.active_role.accent_color, 80) if selected else colors["card_border"]),
                    ink=True,
                    scale=1.0,
                    animate_scale=animation("fast", phase="press"),
                    on_click=animated_click(lambda _, value=emotion_id: self._set_emotion(value)),
                    content=text(label, 11, colors["text"] if selected else colors["text_secondary"]),
                )
            )
        preview_path = self._draft.portraits.get(self._emotion_id) or self.active_role.standing_image_path
        return section_card(
            ft.Column(
                spacing=12,
                controls=[
                    text("Portrait setup", 18, colors["text"], ft.FontWeight.W_500),
                    text("Select emotion and upload portrait image.", 12, colors["text_secondary"]),
                    ft.Row(spacing=8, wrap=True, controls=chips),
                    ft.Container(
                        height=260,
                        border_radius=18,
                        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                        bgcolor=colors["muted"],
                        border=ft.border.all(1, colors["card_border"]),
                        content=ft.Image(src=preview_path, fit=IMAGE_CONTAIN),
                    ),
                    self._primary_button(f"Upload {self._emotion_id} portrait", self.active_role.accent_color, lambda _: self._upload_portrait()),
                ],
            ),
            colors,
        )

    def _personality_step(self, colors: dict[str, str]) -> ft.Control:
        self._age_field = FormField("Age", "Optional", colors)
        self._age_field.value = self._draft.age
        self._gender_dropdown = ft.Dropdown(
            label="Gender",
            value=self._draft.gender or "unknown",
            options=[ft.dropdown.Option("unknown"), ft.dropdown.Option("female"), ft.dropdown.Option("male"), ft.dropdown.Option("other")],
            text_size=12,
            border_radius=14,
            border_color=colors["input_border"],
            bgcolor=colors["input"],
            color=colors["text"],
        )
        self._birthday_field = FormField("Birthday", "YYYY-MM-DD", colors)
        self._birthday_field.value = self._draft.birthday
        self._background_field = FormField("Background", "Context and history", colors, multiline=True)
        self._background_field.value = self._draft.background
        self._style_dropdown = ft.Dropdown(
            label="Speaking style preset",
            value=self._draft.speaking_style_preset or "friendly",
            options=[ft.dropdown.Option("friendly"), ft.dropdown.Option("calm"), ft.dropdown.Option("confident"), ft.dropdown.Option("direct")],
            text_size=12,
            border_radius=14,
            border_color=colors["input_border"],
            bgcolor=colors["input"],
            color=colors["text"],
        )
        self._trait_field = FormField("Add trait", "e.g. patient", colors)
        self._interest_field = FormField("Add interest", "e.g. piano", colors)
        return ft.Column(
            spacing=12,
            controls=[
                section_card(
                    ft.Column(
                        spacing=12,
                        controls=[
                            text("Personality", 18, colors["text"], ft.FontWeight.W_500),
                            ft.Row(spacing=10, controls=[ft.Container(expand=True, content=self._age_field), ft.Container(expand=True, content=self._gender_dropdown)]),
                            self._birthday_field,
                            self._background_field,
                            self._style_dropdown,
                        ],
                    ),
                    colors,
                ),
                section_card(
                    ft.Column(
                        spacing=10,
                        controls=[
                            text("Traits", 13, colors["text_secondary"]),
                            ft.Row(spacing=8, controls=[ft.Container(expand=True, content=self._trait_field), self._small_add_button(colors, lambda _: self._add_trait())]),
                            self._chip_wrap(self._draft.personality_traits, colors, self._remove_trait),
                            text("Interests", 13, colors["text_secondary"]),
                            ft.Row(spacing=8, controls=[ft.Container(expand=True, content=self._interest_field), self._small_add_button(colors, lambda _: self._add_interest())]),
                            self._chip_wrap(self._draft.interests, colors, self._remove_interest),
                        ],
                    ),
                    colors,
                ),
            ],
        )

    def _small_add_button(self, colors: dict[str, str], on_click) -> ft.Control:
        return ft.Container(
            width=48,
            height=48,
            border_radius=16,
            bgcolor=colors["card_strong"],
            alignment=ft.Alignment(0, 0),
            ink=True,
            scale=1.0,
            animate_scale=animation("fast", phase="press"),
            on_click=animated_click(on_click),
            content=ft.Icon(ft.Icons.ADD, color=colors["text"]),
        )

    def _memory_step(self, colors: dict[str, str]) -> ft.Control:
        self._memory_editors = []
        editors: list[ft.Control] = []
        for index, memory in enumerate(self._draft.memories):
            editor = MemoryEditor(memory, colors, lambda _, idx=index: self._remove_memory(idx))
            self._memory_editors.append(editor)
            editors.append(editor)
        if not editors:
            editors.append(
                section_card(
                    ft.Column(
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                        controls=[
                            ft.Icon(ft.Icons.AUTO_AWESOME, size=24, color=colors["text_tertiary"]),
                            text("No memories yet", 13, colors["text_secondary"]),
                            text("Add memory entries to guide role behavior.", 11, colors["text_tertiary"]),
                        ],
                    ),
                    colors,
                )
            )
        return ft.Column(
            spacing=12,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Column(spacing=2, controls=[text("Memory", 18, colors["text"], ft.FontWeight.W_500), text("Episodic, preference, and factual entries.", 13, colors["text_secondary"])]),
                        round_icon_button(ft.Icons.ADD, colors, lambda _: self._add_memory()),
                    ],
                ),
                *editors,
            ],
        )

    def _speaking_step(self, colors: dict[str, str]) -> ft.Control:
        self._vocabulary_dropdown = self._compact_dropdown("Vocabulary", self._draft.vocabulary_level, [("simple", "Simple"), ("common", "Common"), ("academic", "Academic")], colors)
        self._sentence_dropdown = self._compact_dropdown("Sentence length", self._draft.sentence_length, [("short", "Short"), ("medium", "Medium"), ("long", "Long"), ("varied", "Varied")], colors)
        self._emoji_dropdown = self._compact_dropdown("Emoji usage", self._draft.emoji_usage, [("none", "None"), ("sparse", "Sparse"), ("moderate", "Moderate"), ("rich", "Rich")], colors)
        self._parenthesis_dropdown = self._compact_dropdown("Parenthesis usage", self._draft.parenthesis_usage, [("none", "None"), ("sparse", "Sparse"), ("moderate", "Moderate")], colors)
        self._exclamation_slider = ft.Slider(min=0, max=1, divisions=10, value=self._draft.exclamation_rate)
        self._question_slider = ft.Slider(min=0, max=1, divisions=10, value=self._draft.question_rate)
        self._ellipsis_slider = ft.Slider(min=0, max=1, divisions=10, value=self._draft.ellipsis_rate)
        self._influence_slider = ft.Slider(min=0, max=1, divisions=10, value=self._draft.influence_weight)
        return section_card(
            ft.Column(
                spacing=12,
                controls=[
                    text("Language style", 18, colors["text"], ft.FontWeight.W_500),
                    self._vocabulary_dropdown,
                    self._sentence_dropdown,
                    self._slider_block("Exclamation rate", self._exclamation_slider, colors),
                    self._slider_block("Question rate", self._question_slider, colors),
                    self._slider_block("Ellipsis rate", self._ellipsis_slider, colors),
                    ft.Row(spacing=10, controls=[ft.Container(expand=True, content=self._emoji_dropdown), ft.Container(expand=True, content=self._parenthesis_dropdown)]),
                    self._slider_block("Memory influence weight", self._influence_slider, colors),
                ],
            ),
            colors,
        )

    def _compact_dropdown(self, label: str, value: str, options: list[tuple[str, str]], colors: dict[str, str]) -> ft.Dropdown:
        return ft.Dropdown(
            label=label,
            value=value,
            options=[ft.dropdown.Option(key, title) for key, title in options],
            text_size=12,
            border_radius=14,
            border_color=colors["input_border"],
            bgcolor=colors["input"],
            color=colors["text"],
        )

    def _slider_block(self, label: str, slider: ft.Slider, colors: dict[str, str]) -> ft.Control:
        return ft.Column(spacing=4, controls=[text(label, 12, colors["text_secondary"]), slider])

    def _chip_wrap(self, values: list[str], colors: dict[str, str], on_remove) -> ft.Control:
        if not values:
            return text("No entries yet.", 11, colors["text_tertiary"])
        chips: list[ft.Control] = []
        for item in values:
            chips.append(
                ft.Container(
                    padding=ft.padding.symmetric(horizontal=10, vertical=6),
                    border_radius=14,
                    bgcolor=colors["muted"],
                    border=ft.border.all(1, colors["card_border"]),
                    content=ft.Row(
                        spacing=6,
                        tight=True,
                        controls=[
                            text(item, 11, colors["text_secondary"]),
                            ft.IconButton(icon=ft.Icons.CLOSE, icon_size=14, icon_color=colors["text_tertiary"], on_click=lambda _, value=item: on_remove(value), style=ft.ButtonStyle(padding=0)),
                        ],
                    ),
                )
            )
        return ft.Row(spacing=8, wrap=True, controls=chips)

    def _header(self, title: str, colors: dict[str, str], on_back=None) -> ft.Container:
        return ft.Container(
            padding=ft.padding.only(left=0, right=0, top=26, bottom=16),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[round_icon_button(ft.Icons.CHEVRON_LEFT, colors, on_back or (lambda _: self.show_page("home"))), text(title, 20, colors["text"], ft.FontWeight.W_500), ft.Container(width=40)],
            ),
        )

    def _primary_button(self, label: str, color: str, on_click) -> ft.Container:
        button_text = "#1A1625" if self._is_dark else "#FFFFFF"
        return ft.Container(
            height=50,
            border_radius=18,
            bgcolor=color,
            shadow=soft_shadow(self._is_dark, color, "button"),
            alignment=ft.Alignment(0, 0),
            ink=True,
            scale=1.0,
            animate_scale=animation("fast", phase="press"),
            on_click=animated_click(on_click),
            content=text(label, 15, button_text, ft.FontWeight.W_500),
        )

    def _secondary_button(self, label: str, colors: dict[str, str], on_click) -> ft.Container:
        return ft.Container(
            height=48,
            border_radius=16,
            bgcolor=colors["card"],
            border=ft.border.all(1, colors["card_border"]),
            shadow=soft_shadow(self._is_dark, None, "card"),
            alignment=ft.Alignment(0, 0),
            ink=True,
            scale=1.0,
            animate_scale=animation("fast", phase="press"),
            on_click=animated_click(on_click),
            content=text(label, 14, colors["text"], ft.FontWeight.W_500),
        )

    def _toggle_theme(self) -> None:
        self._is_dark = not self._is_dark
        self._settings.is_dark = self._is_dark
        self._callback.on_theme_toggled(self._is_dark)
        self._safe_update()

    def _open_chat(self, role_id: str) -> None:
        self._active_role_id = role_id
        if not any(message.role_id == role_id for message in self._messages):
            seeded = self._seed_messages(self.active_role)
            self._messages.extend(seeded)
            self._seen_message_ids.update(message.id for message in seeded)
        self._callback.on_open_chat(role_id)
        self.show_page("chat")

    def _set_chat_mode(self, mode: str) -> None:
        if mode not in ("normal", "immersive"):
            return
        if self._chat_mode != mode:
            self._chat_mode = mode
            self._chat_mode_seed += 1
            self._callback.on_chat_mode_changed(mode)
            self._safe_update()

    def _send_message(self, value: str) -> None:
        self.append_message(ChatMessage(f"user-{len(self._messages) + 1}", self._active_role_id, value, True, datetime.now()))
        self._callback.on_send_message(self._active_role_id, value, self._chat_mode)

    def _save_settings(self) -> None:
        self._settings.token_quality = int(self._quality_slider.value or 50)
        self._settings.model_provider = self._provider_dropdown.value or "openai"
        self._settings.api_key = self._api_key_field.value or ""
        self._settings.user_name = self._settings_name_field.value or "User"
        self._profile.name = self._settings.user_name
        self._callback.on_settings_saved(self._settings)
        self.show_page("home")

    def _set_emotion(self, emotion_id: str) -> None:
        self._emotion_id = emotion_id
        self._safe_update()

    def _persist_current_step(self) -> None:
        if hasattr(self, "_brain_id_field"):
            self._draft.brain_id = self._brain_id_field.value or ""
            self._draft.template = self._template_dropdown.value or "default"
            self._draft.name = self._name_field.value or ""
            self._draft.description = self._description_field.value or ""
        if hasattr(self, "_age_field"):
            self._draft.age = self._age_field.value or ""
            self._draft.gender = self._gender_dropdown.value or "unknown"
            self._draft.birthday = self._birthday_field.value or ""
            self._draft.background = self._background_field.value or ""
            self._draft.speaking_style_preset = self._style_dropdown.value or "friendly"
        if self._memory_editors:
            self._draft.memories = [editor.to_draft() for editor in self._memory_editors]
        if hasattr(self, "_vocabulary_dropdown"):
            self._draft.vocabulary_level = self._vocabulary_dropdown.value or "common"
            self._draft.sentence_length = self._sentence_dropdown.value or "medium"
            self._draft.emoji_usage = self._emoji_dropdown.value or "sparse"
            self._draft.parenthesis_usage = self._parenthesis_dropdown.value or "sparse"
            self._draft.exclamation_rate = float(self._exclamation_slider.value or 0.3)
            self._draft.question_rate = float(self._question_slider.value or 0.2)
            self._draft.ellipsis_rate = float(self._ellipsis_slider.value or 0.1)
            self._draft.influence_weight = float(self._influence_slider.value or 0.8)

    def _next_step(self) -> None:
        self._persist_current_step()
        if self._create_step < 5:
            self._create_step_direction = 1
            self._create_step += 1
            self._create_step_seed += 1
            self._safe_update()
            return
        self._callback.on_character_create_requested(self._draft)
        self.show_page("home")

    def _previous_step(self) -> None:
        self._persist_current_step()
        if self._create_step > 1:
            self._create_step_direction = -1
            self._create_step -= 1
            self._create_step_seed += 1
            self._safe_update()

    def _upload_portrait(self) -> None:
        self._callback.on_portrait_upload_requested(self._emotion_id)

    def _add_trait(self) -> None:
        value = (self._trait_field.value if self._trait_field else "").strip()
        if value and value not in self._draft.personality_traits:
            self._draft.personality_traits.append(value)
            self._safe_update()

    def _remove_trait(self, value: str) -> None:
        self._draft.personality_traits = [item for item in self._draft.personality_traits if item != value]
        self._safe_update()

    def _add_interest(self) -> None:
        value = (self._interest_field.value if self._interest_field else "").strip()
        if value and value not in self._draft.interests:
            self._draft.interests.append(value)
            self._safe_update()

    def _remove_interest(self, value: str) -> None:
        self._draft.interests = [item for item in self._draft.interests if item != value]
        self._safe_update()

    def _add_memory(self) -> None:
        self._persist_current_step()
        self._draft.memories.append(MemoryDraft(content=""))
        self._safe_update()

    def _remove_memory(self, index: int) -> None:
        self._persist_current_step()
        if 0 <= index < len(self._draft.memories):
            del self._draft.memories[index]
        self._safe_update()

    def set_roles(self, roles: list[CompanionRole]) -> None:
        self._roles = roles
        if roles and self._active_role_id not in [role.id for role in roles]:
            self._active_role_id = roles[0].id
        self._safe_update()

    def set_active_role(self, role_id: str) -> None:
        if any(role.id == role_id for role in self._roles):
            self._active_role_id = role_id
            self._safe_update()

    def set_messages(self, messages: list[ChatMessage]) -> None:
        self._messages = messages
        self._seen_message_ids = {message.id for message in messages}
        self._safe_update()

    def append_message(self, message: ChatMessage) -> None:
        self._messages.append(message)
        self._safe_update()

    def set_typing(self, visible: bool) -> None:
        self._typing = visible
        self._safe_update()

    def apply_settings(self, settings: UiSettings) -> None:
        self._settings = settings
        self._is_dark = settings.is_dark
        self._safe_update()

    def show_page(self, page: str) -> None:
        if page not in self.VALID_PAGES:
            raise ValueError(f"Unknown page: {page}")
        self._page_name = page
        self._touch_page(page)
        self._safe_update()

    def clear_chat(self) -> None:
        active_role = self.active_role.id
        self._messages = [message for message in self._messages if message.role_id != active_role]
        self._seen_message_ids = {message.id for message in self._messages}
        self._safe_update()
