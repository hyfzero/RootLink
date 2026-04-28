"""Figma mobile-first view implementation using Flet controls."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

import flet as ft

from .chat_text import split_display_sentences
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
    MOBILE_WIDTH,
    MOTION,
    animation,
    app_gradient,
    character_chat_gradient,
    glass_gradient,
    hex_with_alpha,
    palette,
    soft_shadow,
)
from .role_loader import load_roles_from_data

EMPTY_ROLE = CompanionRole(
    id="",
    name="未创建角色",
    type="Empty",
    tags=[],
    intro="当前还没有可用角色。",
    status_text="请先创建角色。",
    accent_color="#B6A8C9",
    avatar_path="",
    standing_image_path="",
)

SETTINGS_PROVIDERS = [
    ("minimax", "MiniMax"),
]

PORTRAIT_EMOTIONS = [
    ("neutral", "平静"),
    ("happy", "开心"),
    ("sad", "难过"),
    ("angry", "生气"),
    ("surprised", "惊讶"),
]

CREATE_STEPS = ["基础信息", "立绘", "人格", "记忆", "语言风格"]


def default_roles() -> list[CompanionRole]:
    return load_roles_from_data()


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
        super().__init__(expand=True, animate=animation("slow", ft.AnimationCurve.EASE_IN_OUT))
        self._callback = callback or NoopCallback()
        self._roles = default_roles() if roles is None else roles
        self._active_role_id = self._roles[0].id if self._roles else ""
        self._page_name = "home"
        self._is_dark = is_dark
        self._chat_mode = "normal"
        self._chat_mode_seed = 0
        self._messages = self._seed_messages(self.active_role) if self._roles else []
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
        self._chat_launching_role_id: Optional[str] = None
        self._chat_entry_seed = 0
        self._chat_list_view: Optional[ft.ListView] = None
        self._immersive_dialogue_text: Optional[ft.Text] = None
        self._pending_scroll_to_latest = False
        self._immersive_message_id: Optional[str] = None
        self._immersive_message_text = ""
        self._immersive_segments: list[str] = []
        self._immersive_index = 0
        self._immersive_display_text = ""
        self._immersive_typewriter_generation = 0
        self._build()

    def did_mount(self) -> None:
        self._trigger_scroll_to_latest()

    @property
    def active_role(self) -> CompanionRole:
        for role in self._roles:
            if role.id == self._active_role_id:
                return role
        if self._roles:
            return self._roles[0]
        return EMPTY_ROLE

    def _seed_messages(self, role: CompanionRole) -> list[ChatMessage]:
        seed = {
            "amadeus": "记得你上次停下来的地方。准备好继续了吗？",
            "shinji": "我会在这里。你可以慢慢说。",
            "asuka": "别一个人扛着，直接说出来。",
        }.get(role.id, "我已经准备好了。")
        return [
            ChatMessage("seed-1", role.id, seed, False, datetime.now()),
            ChatMessage("seed-2", role.id, "最近有点累。", True, datetime.now()),
            ChatMessage("seed-3", role.id, role.last_message or role.status_text, False, datetime.now()),
        ]

    def _colors(self) -> dict[str, str]:
        return palette(self._is_dark)

    def _touch_page(self, page: str) -> None:
        self._page_seed[page] = self._page_seed.get(page, 0) + 1

    def _build(self) -> None:
        colors = self._colors()
        self._chat_list_view = None
        self._immersive_dialogue_text = None
        page_content = self._build_current_page(colors)
        page_content.key = f"page-{self._page_name}-{self._page_seed[self._page_name]}-{self._active_role_id}-{self._chat_mode}-{self._create_step}"
        self.gradient = app_gradient(self._is_dark)
        content_width = self._content_width()
        self.content = ft.Row(
            expand=True,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                ft.Container(
                    width=content_width,
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

    def _content_width(self) -> int:
        try:
            page = self.page
        except RuntimeError:
            page = None
        if page is None:
            return MOBILE_WIDTH
        page_width = getattr(page, "width", None) or MOBILE_WIDTH
        resolved_width = int(page_width)
        if resolved_width <= 0:
            return MOBILE_WIDTH
        return min(MOBILE_WIDTH, resolved_width)

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
        if not self._roles:
            return self._build_empty_home_page(colors)
        selected = self.active_role
        role_cards = [RoleSelectorCard(role, role.id == selected.id, self._is_dark, self.set_active_role) for role in self._roles]
        role_cards.append(self._create_selector_card(colors))
        launching = self._chat_launching_role_id == selected.id
        feature_card = ft.Container(
            content=RoleFeatureCard(selected, self._is_dark, self._begin_open_chat),
            scale=0.97 if launching else 1.0,
            opacity=0.72 if launching else 1.0,
            animate_scale=animation("fast", phase="press"),
            animate_opacity=animation("fast", phase="exit"),
        )
        controls = [
            self._stagger(
                "home",
                0,
                ft.Container(
                    padding=ft.padding.only(bottom=2),
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        spacing=12,
                        controls=[
                            ft.Container(expand=True),
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
                                        text("夜晚" if self._is_dark else "白天", 12, colors["text"]),
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
                    content=ft.Column(
                        spacing=7,
                        controls=[
                            text("晚上好，今天想和谁聊聊天？" if self._is_dark else "你好，今天想和谁聊聊天？", 28, colors["text"], ft.FontWeight.W_500),
                            text("深夜的陪伴，从选择一个懂你的人开始" if self._is_dark else "每一天的陪伴，从选择一个懂你的人开始", 15, colors["text_secondary"]),
                        ],
                    ),
                ),
            ),
            self._stagger("home", 2, feature_card, offset_y=0.04, scale_from=0.98),
            self._stagger(
                "home",
                3,
                ft.Container(height=148, content=ft.Row(spacing=12, scroll=ft.ScrollMode.AUTO, controls=role_cards)),
            ),
            self._stagger(
                "home",
                4,
                ft.Row(
                    spacing=12,
                    controls=[
                        ft.Container(expand=True, content=QuickAction("创建角色", "定制专属陪伴", ft.Icons.ADD, colors, lambda _: self.show_page("create"))),
                        ft.Container(expand=True, content=QuickAction("继续话题", "上次聊到哪", ft.Icons.ACCESS_TIME, colors, lambda _: self._begin_open_chat(selected.id))),
                    ],
                ),
            ),
            self._stagger(
                "home",
                5,
                ft.Column(
                    spacing=12,
                    controls=[text("最近聊天", 15, colors["text_secondary"]), *[RecentChatRow(role, self._is_dark, self._begin_open_chat) for role in self._roles]],
                ),
            ),
            ft.Container(height=28),
        ]
        return self._page_column([ft.Container(padding=ft.padding.only(left=20, right=20, top=32, bottom=20), content=ft.Column(spacing=28, controls=controls))])

    def _build_empty_home_page(self, colors: dict[str, str]) -> ft.Control:
        controls = [
            self._stagger(
                "home",
                0,
                ft.Container(
                    padding=ft.padding.only(bottom=2),
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        spacing=12,
                        controls=[
                            ft.Container(expand=True),
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
                                        text("澶滄櫄" if self._is_dark else "鐧藉ぉ", 12, colors["text"]),
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
                ft.Column(
                    spacing=10,
                    controls=[
                        text("还没有角色", 28, colors["text"], ft.FontWeight.W_500),
                        text("当前会按 data 目录动态加载 brain。现在 data 下还没有可用 brain。", 15, colors["text_secondary"]),
                    ],
                ),
            ),
            self._stagger(
                "home",
                2,
                section_card(
                    ft.Column(
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=10,
                        controls=[
                            ft.Icon(ft.Icons.PSYCHOLOGY_ALT_OUTLINED, size=28, color=colors["text_tertiary"]),
                            text("暂无可显示角色", 16, colors["text"], ft.FontWeight.W_500, text_align=ft.TextAlign.CENTER),
                            text("创建角色流程暂未实现。后续创建完成后，这里会自动显示 data 中扫描到的 brain。", 12, colors["text_secondary"], text_align=ft.TextAlign.CENTER),
                        ],
                    ),
                    colors,
                ),
                scale_from=0.98,
            ),
            self._stagger(
                "home",
                3,
                ft.Container(
                    height=148,
                    content=ft.Row(spacing=12, scroll=ft.ScrollMode.AUTO, controls=[self._create_selector_card(colors)]),
                ),
            ),
            self._stagger(
                "home",
                4,
                ft.Container(
                    expand=False,
                    content=QuickAction("创建角色", "功能暂未实现", ft.Icons.ADD, colors, lambda _: self.show_page("create")),
                ),
            ),
            ft.Container(height=28),
        ]
        return self._page_column([ft.Container(padding=ft.padding.only(left=20, right=20, top=32, bottom=20), content=ft.Column(spacing=28, controls=controls))])

    def _create_selector_card(self, colors: dict[str, str]) -> ft.Container:
        return ft.Container(
            width=140,
            padding=14,
            border_radius=18,
            bgcolor=colors["card"],
            border=ft.border.all(2, colors["card_border"]),
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
                    text("创建角色", 13, colors["text_secondary"], text_align=ft.TextAlign.CENTER),
                    text("定制陪伴", 10, colors["text_tertiary"], text_align=ft.TextAlign.CENTER),
                ],
            ),
        )

    def _build_chat_page(self, colors: dict[str, str]) -> ft.Control:
        if not self._roles:
            return ft.Container(
                gradient=character_chat_gradient("", self._is_dark),
                content=ft.Column(
                    expand=True,
                    spacing=0,
                    controls=[
                        ft.Container(
                            padding=ft.padding.only(left=16, right=16, top=26, bottom=12),
                            border=ft.border.only(bottom=ft.BorderSide(1, colors["card_border"])),
                            content=ft.Row(
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    round_icon_button(ft.Icons.ARROW_BACK, colors, lambda _: self.show_page("home"), 36),
                                    ft.Container(expand=True, alignment=ft.alignment.center, content=text("暂无角色", 15, colors["text"], ft.FontWeight.W_500)),
                                    ft.Container(width=36),
                                ],
                            ),
                        ),
                        ft.Container(
                            expand=True,
                            padding=ft.padding.symmetric(horizontal=16, vertical=20),
                            content=section_card(
                                ft.Column(
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                    spacing=10,
                                    controls=[
                                        ft.Icon(ft.Icons.CHAT_BUBBLE_OUTLINE, size=28, color=colors["text_tertiary"]),
                                        text("当前没有可聊天角色", 16, colors["text"], ft.FontWeight.W_500, text_align=ft.TextAlign.CENTER),
                                        text("请先在 data 目录准备 brain。创建角色功能暂未实现。", 12, colors["text_secondary"], text_align=ft.TextAlign.CENTER),
                                    ],
                                ),
                                colors,
                            ),
                        ),
                    ],
                ),
            )
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
                            avatar(role.avatar_path, 36, colors["card_border"], self._is_dark),
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
                delay_ms=100,
                offset=ft.Offset(-0.05, 0) if self._chat_mode == "normal" else ft.Offset(0, 0.03),
                scale_from=1.0 if self._chat_mode == "normal" else 0.97,
                duration_name="normal",
                key=f"chat-body-{self._chat_mode}-{self._chat_mode_seed}-{self._chat_entry_seed}",
            )
        body.expand = True
        if self.motion_enabled:
            header = MotionEntry(
                content=header,
                offset=ft.Offset(0, -0.03),
                duration_name="normal",
                key=f"chat-header-{self._chat_entry_seed}-{self._chat_mode_seed}",
            )
        input_bar: ft.Control = ChatInputBar(role=role, is_dark=self._is_dark, mode=self._chat_mode, on_send=self._send_message, on_voice=lambda _: self._callback.on_voice_requested())
        if self.motion_enabled:
            input_bar = MotionEntry(
                content=input_bar,
                delay_ms=180,
                offset=ft.Offset(0, 0.04),
                duration_name="normal",
                key=f"chat-input-{self._chat_entry_seed}-{self._chat_mode_seed}",
            )
        return ft.Container(
            gradient=character_chat_gradient(role.id if self._chat_mode == "immersive" else "", self._is_dark),
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
                    input_bar,
                ],
            ),
        )

    def _mode_switch(self, colors: dict[str, str]) -> ft.Container:
        return ft.Container(
            padding=4,
            border_radius=16,
            bgcolor=colors["card"],
            border=ft.border.all(1, colors["card_border"]),
            content=ft.Row(
                spacing=4,
                controls=[
                    self._mode_button("normal", ft.Icons.CHAT_BUBBLE_OUTLINE, "常规聊天", colors),
                    self._mode_button("immersive", ft.Icons.AUTO_AWESOME, "沉浸陪伴", colors),
                ],
            ),
        )

    def _mode_button(self, mode: str, icon: str, tooltip: str, colors: dict[str, str]) -> ft.Container:
        active = self._chat_mode == mode
        return ft.Container(
            width=32,
            height=32,
            border_radius=16,
            bgcolor=hex_with_alpha(self.active_role.accent_color, 58 if active else 0) if active else None,
            border=ft.border.all(1, hex_with_alpha(self.active_role.accent_color, 70) if active else colors["card_border"]),
            tooltip=tooltip,
            alignment=ft.Alignment(0, 0),
            ink=True,
            scale=1.0,
            animate_scale=animation("fast", phase="press"),
            animate_opacity=animation("normal"),
            on_click=animated_click(lambda _: self._set_chat_mode(mode)),
            content=ft.Icon(icon, size=16, color=colors["text"] if active else colors["text_secondary"]),
        )

    def _latest_role_reply_text(self, role: CompanionRole) -> str:
        return next((message.text for message in reversed(self._messages) if message.role_id == role.id and not message.is_user), role.status_text)

    def _role_messages(self, role_id: str) -> list[ChatMessage]:
        return [message for message in self._messages if message.role_id == role_id]

    def _normal_display_messages(self, role_id: str) -> list[ChatMessage]:
        display_messages: list[ChatMessage] = []
        for message in self._role_messages(role_id):
            if message.is_user or message.is_streaming:
                display_messages.append(message)
                continue
            sentences = split_display_sentences(message.text)
            if len(sentences) <= 1:
                display_messages.append(message)
                continue
            for index, sentence in enumerate(sentences):
                display_messages.append(
                    ChatMessage(
                        id=f"{message.id}-display-{index}",
                        role_id=message.role_id,
                        text=sentence,
                        is_user=False,
                        timestamp=message.timestamp,
                    )
                )
        return display_messages

    def _latest_role_reply(self, role: CompanionRole) -> Optional[ChatMessage]:
        return next((message for message in reversed(self._messages) if message.role_id == role.id and not message.is_user), None)

    def _schedule_scroll_to_latest(self) -> None:
        self._pending_scroll_to_latest = True

    def _has_normal_chat_content(self, role_id: str) -> bool:
        return bool(self._role_messages(role_id) or self._typing)

    def _trigger_scroll_to_latest(self) -> None:
        if not self._pending_scroll_to_latest:
            return
        try:
            page = self.page
        except RuntimeError:
            return
        self._pending_scroll_to_latest = False

        async def _scroll_now() -> None:
            await self._scroll_chat_to_latest_async()

        async def _after_mount() -> None:
            await asyncio.sleep(0.05)
            await self._scroll_chat_to_latest_async()

        page.run_task(_scroll_now)
        page.run_task(_after_mount)

    async def _scroll_chat_to_latest_async(self) -> None:
        if self._chat_mode != "normal" or self._chat_list_view is None:
            return
        if not self._has_normal_chat_content(self.active_role.id):
            return
        try:
            await self._chat_list_view.scroll_to(offset=0, duration=0)
            self._chat_list_view.update()
        except (AssertionError, RuntimeError):
            pass

    def _split_immersive_sentences(self, value: str) -> list[str]:
        return split_display_sentences(value.replace("\r\n", "\n"))

    def _reset_immersive_state(self, role: CompanionRole) -> None:
        latest_message = self._latest_role_reply(role)
        if latest_message is None:
            self._immersive_message_id = None
            self._immersive_message_text = ""
            self._immersive_segments = []
            self._immersive_index = 0
            self._immersive_display_text = ""
            return
        latest_text = latest_message.text
        if latest_message.id == self._immersive_message_id and latest_text == self._immersive_message_text:
            return
        same_message = latest_message.id == self._immersive_message_id
        self._immersive_message_id = latest_message.id
        self._immersive_message_text = latest_text
        previous_display = self._immersive_display_text
        self._immersive_segments = self._split_immersive_sentences(latest_text)
        if not same_message:
            self._immersive_index = 0
            self._immersive_display_text = ""
        elif self._immersive_segments:
            self._immersive_index = min(self._immersive_index, len(self._immersive_segments) - 1)
            current_target = self._immersive_segments[self._immersive_index]
            self._immersive_display_text = previous_display if current_target.startswith(previous_display) else ""
        else:
            self._immersive_index = 0
            self._immersive_display_text = ""

    def _current_immersive_text(self, role: CompanionRole) -> str:
        if not self._immersive_segments:
            latest_reply = self._latest_role_reply(role)
            if latest_reply is not None:
                return latest_reply.text
            return role.status_text
        return self._immersive_segments[self._immersive_index]

    def _visible_immersive_text(self, role: CompanionRole) -> str:
        if not self._immersive_segments:
            return self._current_immersive_text(role)
        return self._immersive_display_text

    def _set_immersive_dialogue_text(self, value: str) -> None:
        if self._immersive_dialogue_text is None:
            return
        self._immersive_dialogue_text.value = value
        try:
            self._immersive_dialogue_text.update()
        except (AssertionError, RuntimeError):
            self._safe_update()

    def _schedule_immersive_typewriter(self) -> None:
        if self._chat_mode != "immersive" or self._immersive_dialogue_text is None:
            return
        if not self._immersive_segments:
            return
        try:
            page = self.page
        except RuntimeError:
            return

        self._immersive_typewriter_generation += 1
        generation = self._immersive_typewriter_generation

        async def _run_typewriter() -> None:
            while generation == self._immersive_typewriter_generation:
                target = self._current_immersive_text(self.active_role)
                if self._immersive_display_text == target:
                    return
                if target.startswith(self._immersive_display_text):
                    next_length = min(len(target), len(self._immersive_display_text) + 1)
                    self._immersive_display_text = target[:next_length]
                else:
                    self._immersive_display_text = target[:1]
                self._set_immersive_dialogue_text(self._immersive_display_text)
                await asyncio.sleep(0.025)

        page.run_task(_run_typewriter)

    def _advance_immersive_text(self, _) -> None:
        if self._chat_mode != "immersive" or not self._immersive_segments:
            return
        if self._immersive_dialogue_text is None:
            if self._immersive_index < len(self._immersive_segments) - 1:
                self._immersive_index += 1
            return
        target = self._current_immersive_text(self.active_role)
        if self._immersive_display_text != target:
            self._immersive_typewriter_generation += 1
            self._immersive_display_text = target
            self._set_immersive_dialogue_text(target)
            return
        if self._immersive_index >= len(self._immersive_segments) - 1:
            return
        self._immersive_index += 1
        self._immersive_display_text = ""
        self._set_immersive_dialogue_text("")
        self._schedule_immersive_typewriter()

    def _build_chat_message_controls(self, colors: dict[str, str], role: CompanionRole) -> list[ft.Control]:
        chat_messages = self._normal_display_messages(role.id) if self._chat_mode == "normal" else self._role_messages(role.id)
        controls: list[ft.Control] = []
        for message in chat_messages:
            bubble = MessageBubble(message, role, self._is_dark)
            if self.motion_enabled and message.id not in self._seen_message_ids:
                controls.append(MessageBubbleEntry(bubble, key=f"msg-{message.id}"))
                self._seen_message_ids.add(message.id)
            else:
                controls.append(ft.Container(content=bubble, key=f"msg-{message.id}"))
        if self._typing:
            controls.append(self._typing_indicator(role, colors))
        return controls

    def _build_normal_chat_controls(self, colors: dict[str, str], role: CompanionRole) -> list[ft.Control]:
        return list(reversed(self._build_chat_message_controls(colors, role)))

    def _refresh_chat_surface(self) -> bool:
        if self._page_name != "chat":
            return False
        if not self._roles:
            return False

        role = self.active_role
        if self._chat_mode == "normal":
            if self._chat_list_view is None:
                return False
            self._chat_list_view.controls = self._build_normal_chat_controls(self._colors(), role)
            try:
                self._chat_list_view.update()
            except (AssertionError, RuntimeError):
                return False
            self._trigger_scroll_to_latest()
            return True

        if self._immersive_dialogue_text is None:
            return False
        self._reset_immersive_state(role)
        self._immersive_dialogue_text.value = self._visible_immersive_text(role)
        try:
            self._immersive_dialogue_text.update()
        except (AssertionError, RuntimeError):
            return False
        self._schedule_immersive_typewriter()
        return True

    def _build_normal_chat(self, colors: dict[str, str], role: CompanionRole) -> ft.Control:
        self._chat_list_view = ft.ListView(
            controls=self._build_normal_chat_controls(colors, role),
            spacing=12,
            reverse=True,
            expand=True,
            auto_scroll=False,
            build_controls_on_demand=False,
            padding=0,
        )
        return ft.Container(
            expand=True,
            padding=ft.padding.symmetric(horizontal=16, vertical=10),
            content=self._chat_list_view,
        )

    def _typing_indicator(self, role: CompanionRole, colors: dict[str, str]) -> ft.Control:
        return ft.Row(
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                avatar(role.avatar_path, 32, colors["card_border"], self._is_dark),
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
        self._reset_immersive_state(role)
        self._immersive_dialogue_text = text(self._visible_immersive_text(role), 15, colors["text_soft"], max_lines=None)
        self._schedule_immersive_typewriter()
        portrait: ft.Control = ft.Container(
            alignment=ft.Alignment(0, 1),
            content=ft.Image(src=role.standing_image_path, fit=IMAGE_CONTAIN, width=390, height=520),
        )
        dialogue: ft.Control = ft.Container(
            height=168,
            margin=ft.margin.only(left=16, right=16, bottom=12),
            padding=ft.padding.symmetric(horizontal=18, vertical=16),
            border_radius=24,
            gradient=glass_gradient(role.accent_color, self._is_dark, strong=True),
            border=ft.border.all(1, hex_with_alpha(role.accent_color, 0x36 if self._is_dark else 0x48)),
            shadow=soft_shadow(self._is_dark, role.accent_color, "card"),
            ink=True,
            scale=1.0,
            animate_scale=animation("fast", phase="press"),
            on_click=animated_click(self._advance_immersive_text),
            content=ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    avatar(role.avatar_path, 40, hex_with_alpha(role.accent_color, 0x66), self._is_dark),
                    ft.Column(
                        expand=True,
                        spacing=5,
                        controls=[
                            text(role.name, 13, hex_with_alpha(role.accent_color, 0xEE), ft.FontWeight.W_500),
                            self._immersive_dialogue_text,
                        ],
                    ),
                ],
            ),
        )
        if self.motion_enabled:
            portrait = MotionEntry(content=portrait, delay_ms=200, offset=ft.Offset(0, 0.08), duration_name="slow", key=f"portrait-{self._chat_mode_seed}")
            dialogue = MotionEntry(content=dialogue, delay_ms=400, offset=ft.Offset(0, 0.06), duration_name="medium", key=f"dialogue-{self._chat_mode_seed}")
        return ft.Container(
            expand=True,
            bgcolor=hex_with_alpha("#000000", 14 if self._is_dark else 0),
            content=ft.Column(
                expand=True,
                spacing=0,
                controls=[
                    ft.Container(
                        expand=True,
                        alignment=ft.Alignment(0, 1),
                        clip_behavior=ft.ClipBehavior.HARD_EDGE,
                        padding=ft.padding.only(left=10, right=10, top=10),
                        content=portrait,
                    ),
                    dialogue,
                ],
            ),
        )

    def _build_settings_page(self, colors: dict[str, str]) -> ft.Control:
        self._settings_name_field = FormField("显示名称", "你的昵称", colors)
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
            label="模型来源",
            value=self._settings.model_provider,
            options=[ft.dropdown.Option(key, label) for key, label in SETTINGS_PROVIDERS],
            text_size=12,
            border_radius=14,
            border_color=colors["input_border"],
            bgcolor=colors["input"],
            color=colors["text"],
        )
        self._api_key_field = FormField("接口密钥", "sk-...", colors, password=True)
        self._api_key_field.value = self._settings.api_key

        controls = [
            self._stagger("settings", 0, self._header("设置", colors, lambda _: self.show_page("home")), offset_y=0.02),
            self._stagger("settings", 1, self._settings_profile_card(colors)),
            self._stagger("settings", 2, section_card(self._quality_card(colors), colors)),
            self._stagger("settings", 3, section_card(self._provider_card(colors), colors)),
            self._stagger("settings", 4, section_card(self._api_key_card(colors), colors)),
            self._stagger("settings", 5, self._primary_button("保存", self.active_role.accent_color, lambda _: self._save_settings())),
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
                            avatar(image_path, 70, self.active_role.accent_color, self._is_dark),
                            ft.Column(
                                expand=True,
                                spacing=3,
                                controls=[
                                    text("个人资料", 13, colors["text_secondary"]),
                                    text("仅用于界面展示的资料设置", 11, colors["text_tertiary"]),
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
                text("对话质量", 13, colors["text_secondary"]),
                text("平衡回复质量与速度", 11, colors["text_tertiary"]),
                self._quality_slider,
            ],
        )

    def _provider_card(self, colors: dict[str, str]) -> ft.Control:
        provider_desc = {
            "openai": "GPT 系列",
            "anthropic": "Claude 系列",
            "google": "Gemini 系列",
            "deepseek": "DeepSeek 系列",
            "custom": "自定义 API 地址",
        }.get(self._provider_dropdown.value or "openai", "GPT 系列")
        return ft.Column(
            spacing=8,
            controls=[
                text("模型来源", 13, colors["text_secondary"]),
                self._provider_dropdown,
                text(provider_desc, 11, colors["text_tertiary"]),
            ],
        )

    def _api_key_card(self, colors: dict[str, str]) -> ft.Control:
        return ft.Column(spacing=8, controls=[text("凭据", 13, colors["text_secondary"]), self._api_key_field])

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
            self._stagger("create", 0, self._header("创建角色", colors, lambda _: self.show_page("home")), offset_y=0.02),
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
                        controls=[text(f"第 {self._create_step}/5 步", 13, colors["text"]), text(CREATE_STEPS[self._create_step - 1], 12, colors["text_secondary"])],
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
                ft.Container(expand=True, content=self._secondary_button("上一步", colors, lambda _: self._previous_step())),
                ft.Container(
                    expand=True,
                    content=self._primary_button("创建" if self._create_step == 5 else "下一步", self.active_role.accent_color, lambda _: self._next_step()),
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
        self._brain_id_field = FormField("角色标识", "companion-id", colors)
        self._brain_id_field.value = self._draft.brain_id
        self._template_dropdown = ft.Dropdown(
            label="模板",
            value=self._draft.template or "default",
            options=[ft.dropdown.Option("default", "默认"), ft.dropdown.Option("empathetic", "共情"), ft.dropdown.Option("strict", "克制")],
            text_size=12,
            border_radius=14,
            border_color=colors["input_border"],
            bgcolor=colors["input"],
            color=colors["text"],
        )
        self._name_field = FormField("名称", "角色名称", colors)
        self._name_field.value = self._draft.name
        self._description_field = FormField("描述", "简短描述这个角色", colors, multiline=True)
        self._description_field.value = self._draft.description
        return section_card(
            ft.Column(
                spacing=12,
                controls=[text("基础信息", 18, colors["text"], ft.FontWeight.W_500), self._brain_id_field, self._template_dropdown, self._name_field, self._description_field],
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
                    text("立绘设置", 18, colors["text"], ft.FontWeight.W_500),
                    text("选择情绪并上传对应立绘。", 12, colors["text_secondary"]),
                    ft.Row(spacing=8, wrap=True, controls=chips),
                    ft.Container(
                        height=260,
                        border_radius=18,
                        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                        bgcolor=colors["muted"],
                        border=ft.border.all(1, colors["card_border"]),
                        content=ft.Image(src=preview_path, fit=IMAGE_CONTAIN),
                    ),
                    self._primary_button(f"上传{self._current_emotion_label()}立绘", self.active_role.accent_color, lambda _: self._upload_portrait()),
                ],
            ),
            colors,
        )

    def _personality_step(self, colors: dict[str, str]) -> ft.Control:
        self._age_field = FormField("年龄", "可选", colors)
        self._age_field.value = self._draft.age
        self._gender_dropdown = ft.Dropdown(
            label="性别",
            value=self._draft.gender or "unknown",
            options=[ft.dropdown.Option("unknown", "未知"), ft.dropdown.Option("female", "女性"), ft.dropdown.Option("male", "男性"), ft.dropdown.Option("other", "其他")],
            text_size=12,
            border_radius=14,
            border_color=colors["input_border"],
            bgcolor=colors["input"],
            color=colors["text"],
        )
        self._birthday_field = FormField("生日", "YYYY-MM-DD", colors)
        self._birthday_field.value = self._draft.birthday
        self._background_field = FormField("背景", "角色经历与上下文", colors, multiline=True)
        self._background_field.value = self._draft.background
        self._style_dropdown = ft.Dropdown(
            label="语言风格预设",
            value=self._draft.speaking_style_preset or "friendly",
            options=[ft.dropdown.Option("friendly", "友好"), ft.dropdown.Option("calm", "冷静"), ft.dropdown.Option("confident", "自信"), ft.dropdown.Option("direct", "直接")],
            text_size=12,
            border_radius=14,
            border_color=colors["input_border"],
            bgcolor=colors["input"],
            color=colors["text"],
        )
        self._trait_field = FormField("添加特质", "例如：耐心", colors)
        self._interest_field = FormField("添加兴趣", "例如：钢琴", colors)
        return ft.Column(
            spacing=12,
            controls=[
                section_card(
                    ft.Column(
                        spacing=12,
                        controls=[
                            text("人格", 18, colors["text"], ft.FontWeight.W_500),
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
                            text("特质", 13, colors["text_secondary"]),
                            ft.Row(spacing=8, controls=[ft.Container(expand=True, content=self._trait_field), self._small_add_button(colors, lambda _: self._add_trait())]),
                            self._chip_wrap(self._draft.personality_traits, colors, self._remove_trait),
                            text("兴趣", 13, colors["text_secondary"]),
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
                            text("还没有记忆", 13, colors["text_secondary"]),
                            text("添加记忆条目来引导角色行为。", 11, colors["text_tertiary"]),
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
                        ft.Column(spacing=2, controls=[text("记忆", 18, colors["text"], ft.FontWeight.W_500), text("记录情节、偏好和事实。", 13, colors["text_secondary"])]),
                        round_icon_button(ft.Icons.ADD, colors, lambda _: self._add_memory()),
                    ],
                ),
                *editors,
            ],
        )

    def _speaking_step(self, colors: dict[str, str]) -> ft.Control:
        self._vocabulary_dropdown = self._compact_dropdown("词汇难度", self._draft.vocabulary_level, [("simple", "简单"), ("common", "常用"), ("academic", "学术")], colors)
        self._sentence_dropdown = self._compact_dropdown("句子长度", self._draft.sentence_length, [("short", "短句"), ("medium", "中等"), ("long", "长句"), ("varied", "变化")], colors)
        self._emoji_dropdown = self._compact_dropdown("表情使用", self._draft.emoji_usage, [("none", "不用"), ("sparse", "少量"), ("moderate", "适中"), ("rich", "丰富")], colors)
        self._parenthesis_dropdown = self._compact_dropdown("括号补充", self._draft.parenthesis_usage, [("none", "不用"), ("sparse", "少量"), ("moderate", "适中")], colors)
        self._exclamation_slider = ft.Slider(min=0, max=1, divisions=10, value=self._draft.exclamation_rate)
        self._question_slider = ft.Slider(min=0, max=1, divisions=10, value=self._draft.question_rate)
        self._ellipsis_slider = ft.Slider(min=0, max=1, divisions=10, value=self._draft.ellipsis_rate)
        self._influence_slider = ft.Slider(min=0, max=1, divisions=10, value=self._draft.influence_weight)
        return section_card(
            ft.Column(
                spacing=12,
                controls=[
                    text("语言风格", 18, colors["text"], ft.FontWeight.W_500),
                    self._vocabulary_dropdown,
                    self._sentence_dropdown,
                    self._slider_block("感叹号频率", self._exclamation_slider, colors),
                    self._slider_block("问句频率", self._question_slider, colors),
                    self._slider_block("省略号频率", self._ellipsis_slider, colors),
                    ft.Row(spacing=10, controls=[ft.Container(expand=True, content=self._emoji_dropdown), ft.Container(expand=True, content=self._parenthesis_dropdown)]),
                    self._slider_block("记忆影响权重", self._influence_slider, colors),
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
            return text("还没有条目。", 11, colors["text_tertiary"])
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

    def _prepare_chat(self, role_id: str) -> None:
        if not any(role.id == role_id for role in self._roles):
            return
        self._active_role_id = role_id
        if not any(message.role_id == role_id for message in self._messages):
            seeded = self._seed_messages(self.active_role)
            self._messages.extend(seeded)
            self._seen_message_ids.update(message.id for message in seeded)

    def _begin_open_chat(self, role_id: str) -> None:
        self._prepare_chat(role_id)
        self._callback.on_open_chat(role_id)
        if not self.motion_enabled:
            self._chat_entry_seed += 1
            self.show_page("chat")
            return
        self._chat_launching_role_id = role_id
        self._safe_update()

        async def _finish_open() -> None:
            await asyncio.sleep(MOTION["fast"] / 1000)
            if self._chat_launching_role_id != role_id:
                return
            self._chat_launching_role_id = None
            self._chat_entry_seed += 1
            self.show_page("chat")

        try:
            page = self.page
        except RuntimeError:
            page = None
        if page:
            page.run_task(_finish_open)
        else:
            self._chat_launching_role_id = None
            self._chat_entry_seed += 1
            self.show_page("chat")

    def _open_chat(self, role_id: str) -> None:
        self._prepare_chat(role_id)
        self._callback.on_open_chat(role_id)
        self._chat_entry_seed += 1
        self.show_page("chat")

    def _set_chat_mode(self, mode: str) -> None:
        if mode not in ("normal", "immersive"):
            return
        if self._chat_mode != mode:
            self._chat_mode = mode
            self._chat_mode_seed += 1
            if mode == "normal":
                self._schedule_scroll_to_latest()
            else:
                self._reset_immersive_state(self.active_role)
            self._callback.on_chat_mode_changed(mode)
            self._safe_update()
            if mode == "normal":
                self._trigger_scroll_to_latest()

    def _send_message(self, value: str) -> None:
        if not self._active_role_id:
            return
        self.append_message(ChatMessage(f"user-{len(self._messages) + 1}", self._active_role_id, value, True, datetime.now()))
        self._callback.on_send_message(self._active_role_id, value, self._chat_mode)

    def _save_settings(self) -> None:
        self._settings.token_quality = int(self._quality_slider.value or 50)
        self._settings.model_provider = self._provider_dropdown.value or "minimax"
        self._settings.api_key = self._api_key_field.value or ""
        self._settings.user_name = self._settings_name_field.value or "用户"
        self._profile.name = self._settings.user_name
        self._callback.on_settings_saved(self._settings)
        self.show_page("home")

    def _set_emotion(self, emotion_id: str) -> None:
        self._emotion_id = emotion_id
        self._safe_update()

    def _current_emotion_label(self) -> str:
        for emotion_id, label in PORTRAIT_EMOTIONS:
            if emotion_id == self._emotion_id:
                return label
        return "当前"

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
        if not roles:
            self._active_role_id = ""
        elif self._active_role_id not in [role.id for role in roles]:
            self._active_role_id = roles[0].id
        self._safe_update()

    def set_active_role(self, role_id: str) -> None:
        if any(role.id == role_id for role in self._roles):
            self._active_role_id = role_id
            if self._chat_mode == "immersive":
                self._reset_immersive_state(self.active_role)
            elif self._page_name == "chat":
                self._schedule_scroll_to_latest()
            self._safe_update()
            if self._page_name == "chat" and self._chat_mode == "normal":
                self._trigger_scroll_to_latest()

    def set_messages(self, messages: list[ChatMessage]) -> None:
        self._messages = messages
        self._seen_message_ids = {message.id for message in messages}
        if self._chat_mode == "immersive":
            self._reset_immersive_state(self.active_role)
        elif self._page_name == "chat":
            self._schedule_scroll_to_latest()
        if not self._refresh_chat_surface():
            self._safe_update()
            self._trigger_scroll_to_latest()

    def set_role_messages(self, role_id: str, messages: list[ChatMessage]) -> None:
        retained = [message for message in self._messages if message.role_id != role_id]
        self._messages = retained + messages
        retained_ids = {message.id for message in retained}
        self._seen_message_ids = retained_ids | {message.id for message in messages}
        if role_id == self._active_role_id:
            if self._chat_mode == "immersive":
                self._reset_immersive_state(self.active_role)
            elif self._page_name == "chat":
                self._schedule_scroll_to_latest()
        if not self._refresh_chat_surface():
            self._safe_update()
            self._trigger_scroll_to_latest()

    def append_message(self, message: ChatMessage) -> None:
        self._messages.append(message)
        if message.role_id == self._active_role_id:
            if self._chat_mode == "immersive" and not message.is_user:
                self._reset_immersive_state(self.active_role)
            elif self._page_name == "chat":
                self._schedule_scroll_to_latest()
        if not self._refresh_chat_surface():
            self._safe_update()
            self._trigger_scroll_to_latest()

    def update_message_text(self, message_id: str, text: str, is_streaming: bool = False) -> None:
        updated_message: ChatMessage | None = None
        for message in self._messages:
            if message.id == message_id:
                message.text = text
                message.is_streaming = is_streaming
                updated_message = message
                break
        if updated_message is None:
            return
        if updated_message.role_id == self._active_role_id:
            if self._chat_mode == "immersive" and not updated_message.is_user:
                self._reset_immersive_state(self.active_role)
            elif self._page_name == "chat":
                self._schedule_scroll_to_latest()
        if not self._refresh_chat_surface():
            self._safe_update()
            self._trigger_scroll_to_latest()

    def set_typing(self, visible: bool) -> None:
        self._typing = visible
        if self._page_name == "chat" and self._chat_mode == "normal":
            self._schedule_scroll_to_latest()
        if not self._refresh_chat_surface():
            self._safe_update()
            if self._page_name == "chat" and self._chat_mode == "normal":
                self._trigger_scroll_to_latest()

    def apply_settings(self, settings: UiSettings) -> None:
        self._settings = settings
        self._is_dark = settings.is_dark
        self._profile.name = settings.user_name
        self._profile.avatar_path = settings.user_avatar_path
        self._safe_update()

    def show_page(self, page: str) -> None:
        if page not in self.VALID_PAGES:
            raise ValueError(f"Unknown page: {page}")
        self._page_name = page
        if page == "chat":
            if not self._roles:
                self._chat_mode = "normal"
            elif self._chat_mode == "normal":
                self._schedule_scroll_to_latest()
            else:
                self._reset_immersive_state(self.active_role)
        self._touch_page(page)
        self._safe_update()
        if page == "chat" and self._chat_mode == "normal":
            self._trigger_scroll_to_latest()

    def clear_chat(self) -> None:
        if not self._active_role_id:
            return
        active_role = self.active_role.id
        self._messages = [message for message in self._messages if message.role_id != active_role]
        self._seen_message_ids = {message.id for message in self._messages}
        self._immersive_message_id = None
        self._immersive_message_text = ""
        self._immersive_segments = []
        self._immersive_index = 0
        self._immersive_display_text = ""
        self._immersive_typewriter_generation += 1
        if not self._refresh_chat_surface():
            self._safe_update()
