"""Reusable Flet controls for the mobile-first companion UI."""

from __future__ import annotations

import asyncio
import inspect
from typing import Callable, Optional

import flet as ft

try:
    from flet.controls.box import BoxFit
except ImportError:
    BoxFit = ft.ImageFit

from .interfaces import ChatMessage, CompanionRole, MemoryDraft
from .theme import MOTION, UI_FONT_FAMILY, animation, glass_gradient, hex_with_alpha, is_dark_palette, palette, soft_shadow

IMAGE_COVER = BoxFit.COVER
IMAGE_CONTAIN = BoxFit.CONTAIN
_DROPDOWN_ACCEPTS_MENU_STYLE = "menu_style" in inspect.signature(ft.Dropdown).parameters


def animated_click(handler: Optional[Callable], pressed_scale: float = 0.96) -> Callable:
    """Wrap click handlers with a short tap-scale feedback animation."""

    def _handle(event) -> None:
        control = event.control
        try:
            control.scale = pressed_scale
            control.update()
        except (AssertionError, RuntimeError):
            pass

        if handler:
            handler(event)

        async def _restore() -> None:
            await asyncio.sleep(0.08)
            try:
                control.scale = 1.0
                control.update()
            except (AssertionError, RuntimeError):
                pass

        try:
            page = control.page
        except RuntimeError:
            page = None
        if page:
            page.run_task(_restore)

    return _handle


def text(value: str, size: int, color: str, weight: ft.FontWeight | str | None = None, **kwargs) -> ft.Text:
    return ft.Text(value, size=size, color=color, weight=weight, font_family=UI_FONT_FAMILY, **kwargs)


def _role_tags(role: CompanionRole, limit: int) -> list[str]:
    return [tag.strip() for tag in role.tags[:limit] if tag.strip()]


def round_icon_button(icon: str, colors: dict[str, str], on_click: Optional[Callable] = None, size: int = 40) -> ft.Container:
    return ft.Container(
        width=size,
        height=size,
        border_radius=size / 2,
        bgcolor=colors["card"],
        border=ft.Border.all(1, colors["card_border"]),
        alignment=ft.Alignment(0, 0),
        ink=True,
        scale=1.0,
        animate_scale=animation("fast", phase="press"),
        animate_opacity=animation("fast", phase="press"),
        on_click=animated_click(on_click),
        content=ft.Icon(icon, size=18, color=colors["text"]),
    )


def avatar(path: str, size: int = 48, ring_color: Optional[str] = None, is_dark: bool = True) -> ft.Container:
    has_image = bool(path)
    return ft.Container(
        width=size,
        height=size,
        border_radius=size / 2,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        bgcolor=hex_with_alpha("#FFFFFF", 0x10 if is_dark else 0x22) if not has_image else None,
        border=ft.Border.all(1, ring_color or hex_with_alpha("#FFFFFF", 0x1A)),
        shadow=soft_shadow(is_dark, None, "card") if size >= 72 else None,
        alignment=ft.Alignment(0, 0),
        content=ft.Image(src=path, width=size, height=size, fit=IMAGE_COVER)
        if has_image
        else ft.Icon(ft.Icons.PERSON, size=max(16, size // 2), color=hex_with_alpha("#FFFFFF", 0x92) if is_dark else hex_with_alpha("#363040", 0x88)),
    )


def pill(label: str, color: str, is_dark: bool) -> ft.Container:
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=10, vertical=5),
        border_radius=16,
        bgcolor=hex_with_alpha(color, 28 if is_dark else 38),
        content=text(label, 11, hex_with_alpha(color, 238 if is_dark else 255)),
    )


def dropdown_control_style(colors: dict[str, str], radius: int = 18, text_size: int = 13) -> dict[str, object]:
    is_dark = is_dark_palette(colors)
    surface = colors.get("dropdown_surface", colors["input"])
    border_color = colors.get("dropdown_border", colors["input_border"])
    return {
        "text_size": text_size,
        "color": colors["text"],
        "text_style": ft.TextStyle(color=colors["text"], size=text_size),
        "label_style": ft.TextStyle(color=colors["text_secondary"], size=13),
        "border_radius": radius,
        "border_color": border_color,
        "focused_border_color": border_color,
        "bgcolor": surface,
        "filled": True,
        "fill_color": surface,
        "content_padding": ft.Padding.symmetric(horizontal=14, vertical=10),
        "menu_style": ft.MenuStyle(
            bgcolor=surface,
            elevation=12,
            shadow_color=hex_with_alpha("#000000", 0x40 if is_dark else 0x22),
            side=ft.BorderSide(1, border_color),
            padding=ft.Padding.symmetric(vertical=6),
        ),
    }


def dropdown(**kwargs) -> ft.Dropdown:
    menu_style = kwargs.get("menu_style")
    if not _DROPDOWN_ACCEPTS_MENU_STYLE:
        kwargs = dict(kwargs)
        kwargs.pop("menu_style", None)
    control = ft.Dropdown(**kwargs)
    if menu_style is not None:
        setattr(control, "menu_style", menu_style)
    return control


def section_card(content: ft.Control, colors: dict[str, str], padding: int = 20, *, solid: bool = False, radius: int = 24) -> ft.Container:
    is_dark = is_dark_palette(colors)
    bgcolor = colors.get("surface_solid_alt", colors["card"]) if solid else colors["card"]
    border_color = colors.get("dropdown_border", colors["card_border"]) if solid else colors["card_border"]
    return ft.Container(
        padding=padding,
        border_radius=radius,
        bgcolor=bgcolor,
        border=ft.Border.all(1, border_color),
        shadow=soft_shadow(is_dark, None, "card"),
        content=content,
    )


class MotionEntry(ft.Container):
    """Reusable mount animation container with optional delay."""

    def __init__(
        self,
        content: ft.Control,
        delay_ms: int = 0,
        offset: Optional[ft.Offset] = None,
        scale_from: float = 1.0,
        duration_name: str = "normal",
        curve: ft.AnimationCurve | None = None,
        key: str | None = None,
    ) -> None:
        self._delay_ms = delay_ms
        self._alive = True
        self._initial_offset = offset or ft.Offset(0, 0.05)
        super().__init__(
            key=key,
            content=content,
            opacity=0,
            offset=self._initial_offset,
            scale=scale_from,
            animate_opacity=animation(duration_name, curve=curve),
            animate_offset=animation(duration_name, curve=curve),
            animate_scale=animation(duration_name, curve=curve),
        )

    def did_mount(self) -> None:
        try:
            self.page.run_task(self._enter)
        except RuntimeError:
            pass

    def will_unmount(self) -> None:
        self._alive = False

    async def _enter(self) -> None:
        if self._delay_ms > 0:
            await asyncio.sleep(self._delay_ms / 1000)
        if not self._alive:
            return
        self.opacity = 1
        self.offset = ft.Offset(0, 0)
        self.scale = 1
        try:
            self.update()
        except (AssertionError, RuntimeError):
            pass


class StaggerEntry(MotionEntry):
    """Staggered vertical entry used by page sections."""

    def __init__(
        self,
        content: ft.Control,
        index: int = 0,
        offset_y: float = 0.05,
        scale_from: float = 1.0,
        duration_name: str = "slow",
        offset_x: float = 0.0,
        key: str | None = None,
    ) -> None:
        super().__init__(
            content=content,
            delay_ms=index * MOTION["stagger"],
            offset=ft.Offset(offset_x, offset_y),
            scale_from=scale_from,
            duration_name=duration_name,
            curve=ft.AnimationCurve.FAST_OUT_SLOWIN,
            key=key,
        )


class MessageBubbleEntry(MotionEntry):
    """Message-specific entry animation."""

    def __init__(self, content: ft.Control, key: str | None = None, delay_ms: int = 0) -> None:
        super().__init__(
            content=content,
            delay_ms=delay_ms,
            offset=ft.Offset(0, 0.03),
            scale_from=1.0,
            duration_name="message",
            curve=ft.AnimationCurve.FAST_OUT_SLOWIN,
            key=key,
        )


class TypingDots(ft.Row):
    """Local animated typing dots that do not trigger page-wide rebuilds."""

    def __init__(self, color: str) -> None:
        self._phase = 0
        self._alive = True
        self._color = color
        super().__init__(spacing=5, tight=True, controls=self._build_dots())

    def did_mount(self) -> None:
        self._alive = True
        try:
            self.page.run_task(self._pulse_loop)
        except RuntimeError:
            pass

    def will_unmount(self) -> None:
        self._alive = False

    def _build_dots(self) -> list[ft.Control]:
        dots: list[ft.Control] = []
        for index in range(3):
            active = index == self._phase % 3
            dots.append(
                ft.Container(
                    width=8,
                    height=8,
                    border_radius=4,
                    bgcolor=self._color,
                    opacity=1.0 if active else 0.32,
                    scale=1.16 if active else 0.88,
                    animate_opacity=animation("normal"),
                    animate_scale=animation("normal"),
                )
            )
        return dots

    async def _pulse_loop(self) -> None:
        while self._alive:
            await asyncio.sleep(0.42)
            if not self._alive:
                break
            self._phase = (self._phase + 1) % 3
            self.controls = self._build_dots()
            try:
                self.update()
            except (AssertionError, RuntimeError):
                break


class RoleFeatureCard(ft.Container):
    """Large selected-role card from the Figma home screen."""

    def __init__(
        self,
        role: CompanionRole,
        is_dark: bool,
        on_chat: Callable[[str], None],
        on_edit: Callable[[str], None] | None = None,
        on_export: Callable[[str], None] | None = None,
    ) -> None:
        colors = palette(is_dark)
        action_controls: list[ft.Control] = []
        if on_edit is not None:
            action_controls.append(ft.Container(
                width=38,
                height=38,
                border_radius=19,
                tooltip="\u7f16\u8f91\u89d2\u8272",
                bgcolor=hex_with_alpha("#FFFFFF", 28 if is_dark else 180),
                border=ft.Border.all(1, hex_with_alpha("#FFFFFF", 42 if is_dark else 210)),
                alignment=ft.Alignment(0, 0),
                ink=True,
                scale=1.0,
                animate_scale=animation("fast", phase="press"),
                on_click=animated_click(lambda _: on_edit(role.id)),
                content=ft.Icon(ft.Icons.EDIT_OUTLINED, size=17, color=colors["text_secondary"]),
            ))
        if on_export is not None:
            action_controls.append(ft.Container(
                width=38,
                height=38,
                border_radius=19,
                tooltip="\u5bfc\u51fa\u89d2\u8272",
                bgcolor=hex_with_alpha("#FFFFFF", 28 if is_dark else 180),
                border=ft.Border.all(1, hex_with_alpha("#FFFFFF", 42 if is_dark else 210)),
                alignment=ft.Alignment(0, 0),
                ink=True,
                scale=1.0,
                animate_scale=animation("fast", phase="press"),
                on_click=animated_click(lambda _: on_export(role.id)),
                content=ft.Icon(ft.Icons.IOS_SHARE, size=17, color=colors["text_secondary"]),
            ))
        header_controls: list[ft.Control] = [
            ft.Stack(
                width=86,
                height=86,
                controls=[
                    avatar(role.avatar_path, 80, hex_with_alpha(role.accent_color, 90), is_dark),
                    ft.Container(
                        width=18,
                        height=18,
                        right=2,
                        bottom=2,
                        border_radius=9,
                        bgcolor=role.accent_color,
                        border=ft.Border.all(2, "#1E1A2E" if is_dark else "#EBE9F3"),
                    ),
                ],
            ),
            ft.Column(
                expand=True,
                spacing=7,
                controls=[
                    text(role.name, 20, colors["text"], ft.FontWeight.W_500),
                ],
            ),
        ]
        if action_controls:
            header_controls.append(ft.Row(spacing=8, controls=action_controls))
        super().__init__(
            padding=24,
            border_radius=28,
            border=ft.Border.all(1, hex_with_alpha(role.accent_color, 32 if is_dark else 48)),
            gradient=glass_gradient(role.accent_color, is_dark),
            shadow=soft_shadow(is_dark, role.accent_color, "card"),
            opacity=1.0,
            scale=1.0,
            animate_opacity=animation("page"),
            animate_scale=animation("normal", ft.AnimationCurve.FAST_OUT_SLOWIN),
            content=ft.Column(
                spacing=18,
                controls=[
                    ft.Row(
                        spacing=18,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        controls=header_controls,
                    ),
                    text(role.intro, 14, colors["text_secondary"]),
                    ft.Container(
                        height=48,
                        border_radius=16,
                        bgcolor=role.accent_color,
                        shadow=soft_shadow(is_dark, role.accent_color, "button"),
                        alignment=ft.Alignment(0, 0),
                        ink=True,
                        scale=1.0,
                        animate_scale=animation("fast", phase="press"),
                        on_click=animated_click(lambda _: on_chat(role.id)),
                        content=ft.Row(
                            alignment=ft.MainAxisAlignment.CENTER,
                            spacing=8,
                            controls=[
                                ft.Icon(ft.Icons.CHAT_BUBBLE_OUTLINE, size=18, color=colors["button_text_dark"]),
                                text("立即聊天", 15, colors["button_text_dark"], ft.FontWeight.W_500),
                            ],
                        ),
                    ),
                ],
            ),
        )


class RoleSelectorCard(ft.Container):
    """Small horizontal role selector card."""

    def __init__(self, role: CompanionRole, selected: bool, is_dark: bool, on_select: Callable[[str], None]) -> None:
        colors = palette(is_dark)
        tags = _role_tags(role, 3)
        label_controls: list[ft.Control] = [
            text(role.name, 13, colors["text"], ft.FontWeight.W_500, text_align=ft.TextAlign.CENTER),
        ]
        if tags:
            label_controls.append(
                text(
                    " · ".join(tags),
                    10,
                    colors["text_tertiary"],
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    text_align=ft.TextAlign.CENTER,
                )
            )
        super().__init__(
            width=140,
            padding=14,
            border_radius=18,
            opacity=1 if selected else 0.65,
            border=ft.Border.all(1, hex_with_alpha(role.accent_color, 96) if selected else colors["card_border"]),
            gradient=glass_gradient(role.accent_color, is_dark, selected),
            shadow=soft_shadow(is_dark, role.accent_color if selected else None, "card") if selected else None,
            ink=True,
            scale=1.0,
            animate_scale=animation("fast", phase="press"),
            animate_opacity=animation("normal"),
            on_click=animated_click(lambda _: on_select(role.id)),
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=9,
                controls=[
                    avatar(role.avatar_path, 56, hex_with_alpha(role.accent_color, 50), is_dark),
                    ft.Column(
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=2,
                        controls=label_controls,
                    ),
                ],
            ),
        )


class RecentChatRow(ft.Container):
    def __init__(self, role: CompanionRole, is_dark: bool, on_open: Callable[[str], None]) -> None:
        colors = palette(is_dark)
        super().__init__(
            padding=16,
            border_radius=18,
            bgcolor=colors["card"],
            border=ft.Border.all(1, colors["card_border"]),
            shadow=soft_shadow(is_dark, None, "card"),
            ink=True,
            scale=1.0,
            animate_scale=animation("fast", phase="press"),
            animate_opacity=animation("normal"),
            on_click=animated_click(lambda _: on_open(role.id)),
            content=ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    avatar(role.avatar_path, 48, hex_with_alpha(role.accent_color, 48), is_dark),
                    ft.Column(
                        expand=True,
                        spacing=4,
                        controls=[
                            ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN, controls=[text(role.name, 14, colors["text"]), text(role.last_time, 11, colors["text_tertiary"])]),
                            text(role.last_message, 12, colors["text_secondary"], max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ],
                    ),
                ],
            ),
        )


class QuickAction(ft.Container):
    def __init__(self, title: str, subtitle: str, icon: str, colors: dict[str, str], on_click: Callable) -> None:
        is_dark = is_dark_palette(colors)
        super().__init__(
            padding=14,
            border_radius=18,
            bgcolor=colors["card"],
            border=ft.Border.all(1, colors["card_border"]),
            shadow=soft_shadow(is_dark, None, "card"),
            ink=True,
            scale=1.0,
            animate_scale=animation("fast", phase="press"),
            on_click=animated_click(on_click),
            content=ft.Row(
                spacing=10,
                controls=[
                    ft.Container(width=40, height=40, border_radius=20, bgcolor=colors["muted"], alignment=ft.Alignment(0, 0), content=ft.Icon(icon, size=18, color=colors["text_secondary"])),
                    ft.Column(expand=True, spacing=2, controls=[text(title, 13, colors["text"]), text(subtitle, 10, colors["text_tertiary"], max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)]),
                ],
            ),
        )


class MessageBubble(ft.Container):
    def __init__(self, message: ChatMessage, role: CompanionRole, is_dark: bool) -> None:
        colors = palette(is_dark)
        is_user = message.is_user
        bubble_bg = hex_with_alpha(role.accent_color, 0x25 if is_dark else 0x30) if is_user else colors["message"]
        time_value = message.timestamp.strftime("%H:%M")
        bubble = ft.Column(
            expand=True,
            spacing=4,
            horizontal_alignment=ft.CrossAxisAlignment.END if is_user else ft.CrossAxisAlignment.START,
            controls=[
                ft.Container(
                    expand=True,
                    padding=ft.Padding.symmetric(horizontal=14, vertical=10),
                    border_radius=ft.BorderRadius.only(top_left=20 if is_user else 12, top_right=12 if is_user else 20, bottom_left=20, bottom_right=20),
                    bgcolor=bubble_bg,
                    border=ft.Border.all(1, hex_with_alpha(role.accent_color, 0x30 if is_dark else 0x40) if is_user else colors["message_border"]),
                    shadow=soft_shadow(is_dark, role.accent_color if is_user else None, "card"),
                    content=text(message.text, 14, colors["text"], max_lines=None),
                ),
                text(time_value, 10, colors["text_tertiary"]),
            ],
        )
        row_controls: list[ft.Control] = [
            ft.Container(
                expand=True,
                alignment=ft.Alignment(1, 0) if is_user else ft.Alignment(-1, 0),
                content=bubble,
            )
        ]
        if not is_user:
            row_controls.insert(0, ft.Container(width=32, content=avatar(role.avatar_path, 32, colors["card_border"], is_dark)))
        super().__init__(
            alignment=ft.Alignment(1, 0) if is_user else ft.Alignment(-1, 0),
            expand=True,
            content=ft.Row(
                expand=True,
                alignment=ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.START,
                spacing=8,
                controls=row_controls,
            ),
        )


class ChatInputBar(ft.Container):
    """Bottom input row used by both chat modes."""

    def __init__(
        self,
        role: CompanionRole,
        is_dark: bool,
        mode: str,
        on_send: Callable[[str], None],
        on_voice: Optional[Callable] = None,
        initial_value: str = "",
        on_change: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._colors = palette(is_dark)
        self._on_send = on_send
        self._on_change = on_change
        placeholder = "写下你的回应..." if mode == "immersive" else "给她发消息..."
        self._field = ft.TextField(
            value=initial_value,
            hint_text=placeholder,
            text_size=15,
            color=self._colors["text"],
            hint_style=ft.TextStyle(
                color=self._colors["text_tertiary"],
                size=15,
                font_family=UI_FONT_FAMILY,
            ),
            border=ft.InputBorder.NONE,
            filled=False,
            bgcolor=ft.Colors.TRANSPARENT,
            cursor_color=role.accent_color,
            content_padding=ft.Padding.symmetric(horizontal=18, vertical=12),
            on_change=self._handle_change,
            on_submit=self._handle_send,
            expand=True,
        )
        input_shell = ft.Container(
            expand=True,
            border_radius=24,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            bgcolor=self._colors["input"],
            border=ft.Border.all(1, self._colors["input_border"]),
            content=self._field,
        )
        mic_button = ft.Container(
            width=42,
            height=42,
            border_radius=21,
            bgcolor=self._colors["input_button"],
            border=ft.Border.all(1, self._colors["input_border"]),
            alignment=ft.Alignment(0, 0),
            ink=True,
            scale=1.0,
            animate_scale=animation("fast", phase="press"),
            on_click=animated_click(on_voice),
            content=ft.Icon(ft.Icons.MIC_NONE_OUTLINED, size=19, color=self._colors["text_secondary"]),
        )
        send_button = ft.Container(
            width=42,
            height=42,
            border_radius=21,
            bgcolor=role.accent_color,
            shadow=soft_shadow(is_dark, role.accent_color, "button"),
            alignment=ft.Alignment(0, 0),
            ink=True,
            scale=1.0,
            animate_scale=animation("fast", phase="press"),
            on_click=animated_click(self._handle_send),
            content=ft.Icon(ft.Icons.ARROW_UPWARD, size=21, color="#FFFFFF"),
        )
        super().__init__(
            padding=ft.Padding.only(left=14, right=14, top=10, bottom=18),
            bgcolor=self._colors["input_bar"],
            border=ft.Border.only(top=ft.BorderSide(1, self._colors["card_border"])),
            content=ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    input_shell,
                    mic_button,
                    send_button,
                ],
            ),
        )

    def _handle_change(self, event) -> None:
        if self._on_change is None:
            return
        control = getattr(event, "control", None)
        self._on_change(getattr(control, "value", self._field.value) or "")

    def _handle_send(self, event) -> None:
        value = (self._field.value or "").strip()
        if not value:
            return
        self._field.value = ""
        if self._on_change is not None:
            self._on_change("")
        self._on_send(value)
        try:
            self.update()
        except RuntimeError:
            pass


class FormField(ft.TextField):
    def __init__(self, label: str, placeholder: str, colors: dict[str, str], multiline: bool = False, password: bool = False, solid: bool = False):
        fill_color = colors.get("surface_solid", colors["input"]) if solid else colors["input"]
        border_color = colors.get("dropdown_border", colors["input_border"]) if solid else colors["input_border"]
        super().__init__(
            label=label,
            hint_text=placeholder,
            text_size=14,
            min_lines=3 if multiline else None,
            max_lines=5 if multiline else 1,
            multiline=multiline,
            password=password,
            can_reveal_password=password,
            color=colors["text"],
            label_style=ft.TextStyle(color=colors["text_secondary"], size=13),
            hint_style=ft.TextStyle(color=colors["text_tertiary"], size=13),
            border_radius=20 if solid else 22,
            border_color=border_color,
            focused_border_color=border_color,
            bgcolor=fill_color,
            filled=True,
            fill_color=fill_color,
            content_padding=ft.Padding.symmetric(horizontal=14, vertical=12),
        )


class MemoryEditor(ft.Container):
    def __init__(self, memory: MemoryDraft, colors: dict[str, str], on_remove: Callable[[], None]) -> None:
        self._memory = memory
        self.content_field = FormField("记忆内容", "记忆内容...", colors, multiline=True, solid=True)
        self.content_field.value = memory.content
        self.context_field = FormField("上下文", "例如：第一次见面", colors, solid=True)
        self.context_field.value = memory.context
        self.type_dropdown = dropdown(
            label="类型",
            value=memory.memory_type,
            options=[
                ft.dropdown.Option("episodic", "情节记忆"),
                ft.dropdown.Option("preference", "偏好记忆"),
                ft.dropdown.Option("fact", "事实记忆"),
                ft.dropdown.Option("daily_summary", "日度总结"),
                ft.dropdown.Option("monthly_summary", "月度总结"),
            ],
            **dropdown_control_style(colors, radius=18, text_size=12),
        )
        self.importance_value = text(self._importance_label(memory.importance), 12, colors["text_secondary"])
        self.importance = ft.Slider(min=0, max=2, divisions=20, value=memory.importance, on_change=lambda _: self._update_importance_label())
        super().__init__(
            padding=16,
            border_radius=24,
            bgcolor=colors.get("surface_solid_alt", colors["card"]),
            border=ft.Border.all(1, colors.get("dropdown_border", colors["card_border"])),
            shadow=soft_shadow(is_dark_palette(colors), None, "card"),
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN, controls=[text("记忆条目", 13, colors["text_secondary"]), ft.IconButton(icon=ft.Icons.CLOSE, icon_color=colors["text_tertiary"], on_click=lambda _: on_remove())]),
                    self.content_field,
                    self.type_dropdown,
                    ft.Column(
                        spacing=2,
                        controls=[
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[text("重要度", 12, colors["text_secondary"]), self.importance_value],
                            ),
                            self.importance,
                        ],
                    ),
                    self.context_field,
                ],
            ),
        )

    def _importance_label(self, value: float | None) -> str:
        return f"{float(value or 0):.1f} / 2.0"

    def _update_importance_label(self) -> None:
        self.importance_value.value = self._importance_label(self.importance.value)
        try:
            self.importance_value.update()
        except (AssertionError, RuntimeError):
            pass

    def to_draft(self) -> MemoryDraft:
        return MemoryDraft(
            content=self.content_field.value or "",
            memory_type=self.type_dropdown.value or "episodic",
            importance=float(self.importance.value or 1.0),
            context=self.context_field.value or "",
            memory_id=self._memory.memory_id,
            timestamp=self._memory.timestamp,
        )
