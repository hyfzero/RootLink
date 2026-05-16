"""Figma mobile-first view implementation using Flet controls."""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import flet as ft

from .chat_text import split_display_sentences
from .components import (
    ChatInputBar,
    FormField,
    IMAGE_CONTAIN,
    IMAGE_COVER,
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
    dropdown,
    dropdown_control_style,
    round_icon_button,
    section_card,
    text,
)
from .interfaces import (
    CARD_COLOR_PRESETS,
    CharacterDraft,
    ChatMessage,
    CompanionRole,
    CompanionUICallback,
    CompanionUIView,
    MemoryDraft,
    PortraitEditDraft,
    UiSettings,
    UserProfile,
)
from .portrait_processing import PortraitProcessingError, export_aligned_portrait, sample_background_color
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
    ("deepseek", "DeepSeek"),
]

SETTINGS_MODELS = {
    "minimax": [("MiniMax-M2.5", "MiniMax M2.5")],
    "deepseek": [
        ("deepseek-v4-flash", "DeepSeek V4 Flash"),
        ("deepseek-v4-pro", "DeepSeek V4 Pro"),
    ],
}

DEFAULT_SETTINGS_MODELS = {
    "minimax": "MiniMax-M2.5",
    "deepseek": "deepseek-v4-flash",
}

PORTRAIT_EMOTIONS = [
    ("neutral", "默认"),
    ("happy", "开心"),
    ("sad", "难过"),
    ("angry", "生气"),
    ("surprised", "惊讶"),
]

PORTRAIT_CUTOUT_PRESETS = [
    ("soft", "保守", 18, 1),
    ("standard", "标准", 32, 2),
    ("strong", "强力", 55, 3),
]
PORTRAIT_PREVIEW_DEBOUNCE_SECONDS = 0.25

CREATE_STEPS = ["基础信息", "立绘", "人格", "记忆", "语言风格"]


TYPING_STATUS_TEXT = "\u6b63\u5728\u8f93\u5165\u4e2d"
REPLY_EMOTION_STATUS = {
    "neutral": "\u5e73\u9759 \U0001f610",
    "happy": "\u5f00\u5fc3 \U0001f60a",
    "sad": "\u96be\u8fc7 \U0001f622",
    "angry": "\u751f\u6c14 \U0001f620",
    "surprised": "\u60ca\u8bb6 \U0001f62e",
    "thinking": "\u601d\u8003\u4e2d \U0001f914",
    "confused": "\u56f0\u60d1 \U0001f615",
    "scared": "\u5bb3\u6015 \U0001f628",
    "embarrassed": "\u5bb3\u7f9e \U0001f633",
}

HOME_TITLE_TEXT = "今天想和谁聊聊天"
HOME_SUBTITLE_TEXT = "在一切的根部，我们彼此相连"


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
        self._messages: list[ChatMessage] = []
        self._seen_message_ids = {message.id for message in self._messages}
        self._typing = False
        self._reply_emotions: dict[str, str] = {}
        self._settings = UiSettings(is_dark=is_dark)
        self._profile = UserProfile(name=self._settings.user_name)
        self._draft = CharacterDraft()
        self._create_mode = "create"
        self._editing_role_id = ""
        self._create_step = 1
        self._create_step_seed = 0
        self._create_step_direction = 1
        self._emotion_id = "neutral"
        self._file_picker: Optional[ft.FilePicker] = None
        self._share: Optional[ft.Share] = None
        self._file_picker_target: tuple[str, str] | None = None
        self._trait_field: Optional[ft.TextField] = None
        self._interest_field: Optional[ft.TextField] = None
        self._trait_chips: Optional[ft.Row] = None
        self._interest_chips: Optional[ft.Row] = None
        self._memory_editors: list[MemoryEditor] = []
        self._memory_list: Optional[ft.Column] = None
        self._portrait_tolerance_slider: Optional[ft.Slider] = None
        self._portrait_feather_slider: Optional[ft.Slider] = None
        self._portrait_scale_slider: Optional[ft.Slider] = None
        self._portrait_offset_x_slider: Optional[ft.Slider] = None
        self._portrait_offset_y_slider: Optional[ft.Slider] = None
        self._portrait_value_labels: dict[str, ft.Text] = {}
        self._portrait_preview_container: Optional[ft.Container] = None
        self._portrait_advanced_open = False
        self._portrait_extra_open = False
        self._portrait_preview_generation = 0
        self._portrait_rendering_emotion_id = ""
        self._portrait_preview_session_id = uuid.uuid4().hex
        self._portrait_preview_paths: dict[str, str] = {}
        self.motion_enabled = True
        self._page_history: list[str] = []
        self._navigation_route = ""
        self._navigation_routes: tuple[str, ...] = ()
        self._force_platform_route_sync = False
        self._navigation_revision = 0
        self._page_seed = {page: 0 for page in self.VALID_PAGES}
        self._chat_entry_seed = 0
        self._suppress_next_chat_entry_motion = False
        self._chat_input_drafts: dict[tuple[str, str], str] = {}
        self._chat_list_view: Optional[ft.ListView] = None
        self._chat_status_text: Optional[ft.Text] = None
        self._immersive_dialogue_text: Optional[ft.Text] = None
        self._immersive_portrait_container: Optional[ft.Container] = None
        self._pending_scroll_to_latest = False
        self._immersive_message_id: Optional[str] = None
        self._immersive_message_text = ""
        self._immersive_segments: list[str] = []
        self._immersive_index = 0
        self._immersive_display_text = ""
        self._immersive_typewriter_generation = 0
        self._scroll_generation = 0
        self._last_content_width: int | None = None
        self._last_content_width_from_page = False
        self._build()

    def did_mount(self) -> None:
        self._ensure_file_picker()
        self.refresh_layout()
        self._schedule_initial_layout_refresh()
        self._trigger_scroll_to_latest()

    @property
    def active_role(self) -> CompanionRole:
        for role in self._roles:
            if role.id == self._active_role_id:
                return role
        if self._roles:
            return self._roles[0]
        return EMPTY_ROLE

    def _colors(self) -> dict[str, str]:
        return palette(self._is_dark)

    def _touch_page(self, page: str) -> None:
        self._page_seed[page] = self._page_seed.get(page, 0) + 1

    def _reset_create_navigation(self) -> None:
        self._create_step = 1
        self._create_step_seed += 1
        self._create_step_direction = 1
        self._emotion_id = "neutral"
        self._portrait_advanced_open = False
        self._portrait_extra_open = False
        self._portrait_rendering_emotion_id = ""
        self._portrait_preview_generation += 1
        self._portrait_preview_session_id = uuid.uuid4().hex
        self._portrait_preview_paths = {}
        self._memory_editors = []
        self._memory_list = None
        self._portrait_value_labels = {}
        self._portrait_preview_container = None

    def _create_accent_color(self) -> str:
        return self._draft.accent_color.strip() or self.active_role.accent_color

    def _begin_create(self) -> None:
        self._create_mode = "create"
        self._editing_role_id = ""
        self._draft = CharacterDraft()
        self._reset_create_navigation()
        self.show_page("create")

    def _begin_edit_role(self, role_id: str) -> None:
        draft = self._callback.load_character_draft(role_id)
        if draft is None:
            self.show_notice("\u65e0\u6cd5\u8bfb\u53d6\u89d2\u8272\u6570\u636e", is_error=True)
            return
        self._create_mode = "edit"
        self._editing_role_id = role_id
        self._draft = draft
        self._reset_create_navigation()
        self._portrait_extra_open = self._draft_has_extra_portraits()
        self.show_page("create")

    def _build(self) -> None:
        colors = self._colors()
        self._chat_list_view = None
        self._immersive_dialogue_text = None
        self._immersive_portrait_container = None
        page_content = self._build_current_page(colors)
        page_content.key = f"page-{self._page_name}-{self._page_seed[self._page_name]}-{self._active_role_id}-{self._chat_mode}-{self._create_mode}-{self._editing_role_id}-{self._create_step}"
        self.gradient = app_gradient(self._is_dark)
        content_width = self._content_width()
        self._last_content_width = content_width
        self._last_content_width_from_page = self._has_page_for_layout()
        page_shell: ft.Control = ft.Row(
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
        if self._is_mobile_platform():
            page_shell = ft.GestureDetector(
                content=page_shell,
                on_horizontal_drag_end=self._handle_horizontal_back_drag,
            )
        self.content = page_shell

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

    def _has_page_for_layout(self) -> bool:
        try:
            self.page
            return True
        except RuntimeError:
            return False

    def _is_mobile_keyboard_sensitive_page(self) -> bool:
        return self._page_name in {"chat", "create"} and self._is_mobile_platform()

    def _handle_horizontal_back_drag(self, event) -> None:
        velocity = getattr(event, "primary_velocity", None)
        if velocity is None:
            velocity = getattr(getattr(event, "velocity", None), "x", 0)
        try:
            velocity_value = float(velocity or 0)
        except (TypeError, ValueError):
            return
        if abs(velocity_value) < 300:
            return
        self.go_back()

    def refresh_layout(self) -> None:
        content_width = self._content_width()
        if self._last_content_width == content_width:
            return
        if self._last_content_width_from_page and self._is_mobile_keyboard_sensitive_page():
            self._last_content_width = content_width
            return
        self._safe_update()

    def _schedule_initial_layout_refresh(self) -> None:
        try:
            page = self.page
        except RuntimeError:
            return
        run_task = getattr(page, "run_task", None)
        if not callable(run_task):
            return
        try:
            run_task(self._refresh_layout_after_mount)
        except TypeError:
            return

    async def _refresh_layout_after_mount(self) -> None:
        for delay in (0, 0.05, 0.2):
            await asyncio.sleep(delay)
            self.refresh_layout()

    def _safe_update(self) -> None:
        self._build()
        try:
            self.update()
        except (AssertionError, RuntimeError):
            pass
        self._sync_platform_navigation_stack()

    def _sync_platform_navigation_stack(self) -> None:
        try:
            page = self.page
        except RuntimeError:
            return
        page_views = getattr(page, "views", None)
        if not isinstance(page_views, list):
            return
        stack = [name for name in [*self._page_history, self._page_name] if name in self.VALID_PAGES]
        if not stack or stack[0] != "home":
            stack.insert(0, "home")
        compact_stack: list[str] = []
        for name in stack:
            if not compact_stack or compact_stack[-1] != name:
                compact_stack.append(name)
        views = [
            ft.View(
                route=f"/{index}-{name}-{self._navigation_revision}",
                controls=[self] if index == len(compact_stack) - 1 else [],
                padding=0,
                spacing=0,
            )
            for index, name in enumerate(compact_stack)
        ]
        try:
            current_route = str(getattr(page, "route", "") or "")
            page.views = views
            top_route = views[-1].route
            self._navigation_route = top_route
            self._navigation_routes = tuple(view.route for view in views)
            force_route_sync = self._force_platform_route_sync
            self._force_platform_route_sync = False
            go = getattr(page, "go", None)
            if callable(go) and (force_route_sync or current_route != top_route):
                go(top_route)
            else:
                page.route = top_route
                page.update()
        except (AssertionError, RuntimeError):
            pass

    def force_platform_route_sync(self) -> None:
        self._force_platform_route_sync = True
        self._navigation_revision += 1

    def handle_platform_route_change(self, route: object) -> bool:
        route_value = str(route or "")
        if not route_value or route_value == self._navigation_route:
            return False
        if route_value not in self._navigation_routes:
            return False
        self.force_platform_route_sync()
        return self.go_back()

    def _ensure_file_picker(self) -> ft.FilePicker | None:
        if self._file_picker is None:
            self._file_picker = ft.FilePicker()
        try:
            page = self.page
        except RuntimeError:
            return None
        if hasattr(page, "services"):
            return self._file_picker
        overlay = getattr(page, "overlay", None)
        if overlay is None:
            return None
        if self._file_picker not in overlay:
            overlay.append(self._file_picker)
            try:
                page.update()
            except Exception:
                pass
        return self._file_picker

    def _ensure_share(self) -> ft.Share | None:
        if self._share is None:
            self._share = ft.Share()
        try:
            page = self.page
        except RuntimeError:
            return None
        registry = getattr(page, "_services", None)
        register_service = getattr(registry, "register_service", None)
        registered_services = getattr(registry, "_services", None)
        if callable(register_service) and (
            not isinstance(registered_services, list) or self._share not in registered_services
        ):
            try:
                register_service(self._share)
            except Exception:
                pass
        return self._share

    def _open_image_picker(self, target: str, emotion_id: str = "") -> None:
        picker = self._ensure_file_picker()
        if picker is None:
            self.show_notice("File picker is unavailable before the page is mounted.", is_error=True)
            return
        self._file_picker_target = (target, emotion_id)
        try:
            page = self.page
        except RuntimeError:
            page = None
        if page is None:
            self.show_notice("File picker is unavailable before the page is mounted.", is_error=True)
            return
        page.run_task(self._pick_image_file, picker)

    def _begin_export_role(self, role_id: str) -> None:
        if self._is_mobile_platform():
            self.show_notice("正在导出角色...")
            try:
                page = self.page
            except RuntimeError:
                page = None
            run_task = getattr(page, "run_task", None) if page is not None else None
            if callable(run_task):
                run_task(self._export_and_share_character_package, role_id)
            else:
                package_path = self._export_role_to_path(role_id, "")
                if package_path:
                    self.show_notice(f"角色已导出：{package_path}")
            return
        picker = self._ensure_file_picker()
        if picker is None:
            self._export_role_to_path(role_id, "")
            return
        try:
            page = self.page
        except RuntimeError:
            page = None
        if page is None:
            self._export_role_to_path(role_id, "")
            return
        page.run_task(self._save_character_package, picker, role_id)

    async def _save_character_package(self, picker: ft.FilePicker, role_id: str) -> None:
        try:
            destination = await picker.save_file(
                dialog_title="\u5bfc\u51fa\u89d2\u8272",
                file_name=f"{role_id}.amadues",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["amadues", "zip"],
            )
        except Exception:
            self._export_role_to_path(role_id, "")
            return
        if not destination:
            return
        self._export_role_to_path(role_id, destination)

    async def _export_and_share_character_package(self, role_id: str) -> None:
        package_path = self._export_role_to_path(role_id, "")
        if not package_path:
            self.show_notice("导出角色失败", is_error=True)
            return
        share = self._ensure_share()
        if share is None:
            await self._show_export_share_fallback(package_path)
            return
        try:
            result = await share.share_files(
                [ft.ShareFile(path=package_path, name=Path(package_path).name)],
                title="导出角色",
                text="Amadues character package",
            )
        except Exception:
            await self._show_export_share_fallback(package_path)
            return
        status = str(getattr(getattr(result, "status", ""), "value", getattr(result, "status", ""))).lower()
        if status == "unavailable":
            await self._show_export_share_fallback(package_path)
        elif status == "dismissed":
            self.show_notice(f"角色已导出：{package_path}")

    async def _show_export_share_fallback(self, package_path: str) -> None:
        copied = await self._copy_export_path_to_clipboard(package_path)
        suffix = "，路径已复制" if copied else ""
        self.show_notice(f"角色已导出：{package_path}{suffix}")

    async def _copy_export_path_to_clipboard(self, package_path: str) -> bool:
        try:
            page = self.page
        except RuntimeError:
            return False
        setter = getattr(page, "set_clipboard", None)
        if callable(setter):
            try:
                setter(package_path)
                return True
            except Exception:
                return False
        try:
            clipboard = getattr(page, "clipboard", None)
            set_value = getattr(clipboard, "set", None)
            if not callable(set_value):
                return False
            result = set_value(package_path)
            if asyncio.iscoroutine(result):
                await result
            return True
        except Exception:
            return False

    def _export_role_to_path(self, role_id: str, destination_path: str) -> str:
        return self._callback.on_character_export_requested(role_id, destination_path)

    def _confirm_delete_role(self, role_id: str) -> None:
        role = next((item for item in self._roles if item.id == role_id), None)
        if role is None:
            self.show_notice("\u627e\u4e0d\u5230\u8981\u5220\u9664\u7684\u89d2\u8272", is_error=True)
            return
        if len(self._roles) <= 1:
            self.show_notice("\u81f3\u5c11\u9700\u8981\u4fdd\u7559\u4e00\u4e2a\u4eba\u683c", is_error=True)
            return
        try:
            page = self.page
        except RuntimeError:
            self._delete_role(role_id)
            return

        colors = self._colors()
        dialog = ft.AlertDialog(
            modal=True,
            title=text("\u5220\u9664\u4eba\u683c", 18, colors["text"], ft.FontWeight.W_500),
            content=text(
                f"\u786e\u5b9a\u5220\u9664\u300c{role.name}\u300d\u5417\uff1f\u5220\u9664\u540e\u8be5\u4eba\u683c\u7684\u672c\u5730\u6570\u636e\u4e5f\u4f1a\u88ab\u79fb\u9664\u3002",
                14,
                colors["text_secondary"],
            ),
            actions=[
                ft.TextButton("\u53d6\u6d88", on_click=lambda _: self._close_dialog(dialog)),
                ft.TextButton(
                    "\u5220\u9664",
                    style=ft.ButtonStyle(color="#D92D20"),
                    on_click=lambda _: self._delete_role_from_dialog(role_id, dialog),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._show_dialog(dialog, page)

    def _show_dialog(self, dialog: ft.AlertDialog, page: ft.Page) -> None:
        dialog.open = True
        show_dialog = getattr(page, "show_dialog", None)
        if callable(show_dialog):
            show_dialog(dialog)
            return
        page.dialog = dialog
        page.update()

    def _close_dialog(self, dialog: ft.AlertDialog) -> None:
        dialog.open = False
        try:
            dialog.update()
        except (AssertionError, RuntimeError, TypeError, AttributeError):
            try:
                self.page.update()
            except (AssertionError, RuntimeError, TypeError, AttributeError):
                pass

    def _delete_role_from_dialog(self, role_id: str, dialog: ft.AlertDialog) -> None:
        self._close_dialog(dialog)
        self._delete_role(role_id)

    def _delete_role(self, role_id: str) -> None:
        if self._callback.on_character_delete_requested(role_id):
            self._messages = [message for message in self._messages if message.role_id != role_id]
            self._seen_message_ids = {message.id for message in self._messages}

    def _is_mobile_platform(self) -> bool:
        try:
            page = self.page
        except RuntimeError:
            return False
        platform = getattr(page, "platform", None)
        platform_value = getattr(platform, "value", platform)
        normalized = str(platform_value).lower()
        return normalized in {"android", "ios"} or "android" in normalized or "ios" in normalized

    def _open_package_import_picker(self) -> None:
        picker = self._ensure_file_picker()
        if picker is None:
            self.show_notice("File picker is unavailable before the page is mounted.", is_error=True)
            return
        try:
            page = self.page
        except RuntimeError:
            page = None
        if page is None:
            self.show_notice("File picker is unavailable before the page is mounted.", is_error=True)
            return
        page.run_task(self._pick_character_package, picker)

    async def _pick_character_package(self, picker: ft.FilePicker) -> None:
        try:
            files = await picker.pick_files(
                allow_multiple=False,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["amadues", "zip"],
            )
        except Exception:
            self.show_notice("Could not open the file picker.", is_error=True)
            return
        self._handle_package_pick(files)

    def _handle_package_pick(self, files: object) -> None:
        selected_files = getattr(files, "files", files)
        if not selected_files:
            return
        file_path = getattr(selected_files[0], "path", "") or ""
        if not file_path:
            self.show_notice("Could not read selected file path.", is_error=True)
            return
        if Path(file_path).suffix.lower() not in {".amadues", ".zip"}:
            self.show_notice("Character packages must be AMADUES or ZIP files.", is_error=True)
            return
        self._callback.on_character_import_requested(file_path)

    async def _pick_image_file(self, picker: ft.FilePicker) -> None:
        try:
            files = await picker.pick_files(
                allow_multiple=False,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["png", "jpg", "jpeg", "webp"],
            )
        except Exception:
            self._file_picker_target = None
            self.show_notice("Could not open the file picker.", is_error=True)
            return
        self._handle_image_pick(files)

    def _handle_image_pick(self, files: object) -> None:
        target = self._file_picker_target
        self._file_picker_target = None
        selected_files = getattr(files, "files", files)
        if target is None or not selected_files:
            return

        file_path = getattr(selected_files[0], "path", "") or ""
        if not file_path:
            self.show_notice("Could not read selected file path.", is_error=True)
            return
        if Path(file_path).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            self.show_notice("Images must be PNG, JPG, JPEG, or WebP.", is_error=True)
            return

        kind, emotion_id = target
        if kind == "avatar":
            self._draft.avatar_path = file_path
        elif kind == "portrait" and emotion_id:
            try:
                background_color = sample_background_color(file_path)
                self._draft.portrait_edits[emotion_id] = PortraitEditDraft(
                    source_path=file_path,
                    background_color=background_color,
                )
                self._process_portrait(emotion_id, refresh=False)
            except PortraitProcessingError as exc:
                self.show_notice(str(exc), is_error=True)
                return
        self._safe_update()

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
            key=f"{page}-{self._page_seed.get(page, 0)}-{index}-{self._active_role_id}-{self._create_mode}-{self._create_step}",
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
        role_cards = [RoleSelectorCard(role, role.id == selected.id, self._is_dark, self._handle_home_role_select) for role in self._roles]
        role_cards.append(self._create_selector_card(colors))
        recent_roles = self._recent_roles()
        feature_card = ft.Container(
            content=RoleFeatureCard(selected, self._is_dark, self._begin_open_chat, self._begin_edit_role, self._begin_export_role),
        )
        controls = [
            self._stagger(
                "home",
                0,
                ft.Container(
                    padding=ft.Padding.only(bottom=2),
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        spacing=12,
                        controls=[
                            ft.Container(expand=True),
                            ft.Container(
                                padding=ft.Padding.symmetric(horizontal=15, vertical=10),
                                border_radius=22,
                                bgcolor=colors["card"],
                                border=ft.Border.all(1, colors["card_border"]),
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
                            text(HOME_TITLE_TEXT, 28, colors["text"], ft.FontWeight.W_500),
                            text(HOME_SUBTITLE_TEXT, 15, colors["text_secondary"]),
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
                self._home_quick_actions(colors),
            ),
            self._stagger(
                "home",
                5,
                ft.Column(
                    spacing=12,
                    controls=[text("最近聊天", 15, colors["text_secondary"]), *[RecentChatRow(role, self._is_dark, self._begin_open_chat) for role in recent_roles]],
                ),
            ),
            ft.Container(height=28),
        ]
        return self._page_column([ft.Container(padding=ft.Padding.only(left=20, right=20, top=32, bottom=20), content=ft.Column(spacing=28, controls=controls))])

    def _home_quick_actions(self, colors: dict[str, str]) -> ft.Control:
        actions = [
            QuickAction("创建角色", "定制专属陪伴", ft.Icons.ADD, colors, lambda _: self._begin_create()),
            QuickAction("人格导入", "导入完整角色包", ft.Icons.FILE_UPLOAD_OUTLINED, colors, lambda _: self._open_package_import_picker()),
        ]
        if self._content_width() < 420:
            return ft.Column(spacing=12, controls=actions)
        return ft.Row(
            spacing=12,
            controls=[ft.Container(expand=True, content=action) for action in actions],
        )

    def _build_empty_home_page(self, colors: dict[str, str]) -> ft.Control:
        controls = [
            self._stagger(
                "home",
                0,
                ft.Container(
                    padding=ft.Padding.only(bottom=2),
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        spacing=12,
                        controls=[
                            ft.Container(expand=True),
                            ft.Container(
                                padding=ft.Padding.symmetric(horizontal=15, vertical=10),
                                border_radius=22,
                                bgcolor=colors["card"],
                                border=ft.Border.all(1, colors["card_border"]),
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
                    content=QuickAction("创建角色", "功能暂未实现", ft.Icons.ADD, colors, lambda _: self._begin_create()),
                ),
            ),
            ft.Container(height=28),
        ]
        return self._page_column([ft.Container(padding=ft.Padding.only(left=20, right=20, top=32, bottom=20), content=ft.Column(spacing=28, controls=controls))])

    def _create_selector_card(self, colors: dict[str, str]) -> ft.Container:
        return ft.Container(
            width=140,
            padding=14,
            border_radius=18,
            bgcolor=colors["card"],
            border=ft.Border.all(2, colors["card_border"]),
            ink=True,
            scale=1.0,
            animate_scale=animation("fast", phase="press"),
            animate_opacity=animation("fast", phase="press"),
            on_click=animated_click(lambda _: self._begin_create()),
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
        suppress_entry_motion = self._suppress_next_chat_entry_motion
        self._suppress_next_chat_entry_motion = False
        section_motion_enabled = self.motion_enabled and not suppress_entry_motion
        if not self._roles:
            return ft.Container(
                gradient=character_chat_gradient("", self._is_dark),
                content=ft.Column(
                    expand=True,
                    spacing=0,
                    controls=[
                        ft.Container(
                            padding=ft.Padding.only(left=16, right=16, top=26, bottom=12),
                            border=ft.Border.only(bottom=ft.BorderSide(1, colors["card_border"])),
                            content=ft.Row(
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    round_icon_button(ft.Icons.ARROW_BACK, colors, lambda _: self.go_back(), 36),
                                    ft.Container(expand=True, alignment=ft.alignment.center, content=text("暂无角色", 15, colors["text"], ft.FontWeight.W_500)),
                                    ft.Container(width=36),
                                ],
                            ),
                        ),
                        ft.Container(
                            expand=True,
                            padding=ft.Padding.symmetric(horizontal=16, vertical=20),
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
        self._chat_status_text = text(
            self._chat_status_value(role),
            11,
            colors["text_secondary"],
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
        header = ft.Container(
            padding=ft.Padding.only(left=16, right=16, top=26, bottom=12),
            border=ft.Border.only(bottom=ft.BorderSide(1, colors["card_border"])),
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    round_icon_button(ft.Icons.ARROW_BACK, colors, lambda _: self.go_back(), 36),
                    ft.Row(
                        expand=True,
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=10,
                        controls=[
                            self._editable_chat_avatar(role, colors),
                            ft.Column(
                                spacing=2,
                                controls=[
                                    text(role.name, 15, colors["text"], ft.FontWeight.W_500),
                                    self._chat_status_text,
                                ],
                            ),
                        ],
                    ),
                    self._mode_switch(colors),
                ],
            ),
        )
        body = self._build_normal_chat(colors, role) if self._chat_mode == "normal" else self._build_immersive_chat(colors, role)
        if section_motion_enabled:
            body = MotionEntry(
                content=body,
                delay_ms=100,
                offset=ft.Offset(-0.05, 0) if self._chat_mode == "normal" else ft.Offset(0, 0.03),
                scale_from=1.0 if self._chat_mode == "normal" else 0.97,
                duration_name="normal",
                key=f"chat-body-{self._chat_mode}-{self._chat_mode_seed}-{self._chat_entry_seed}",
            )
        body.expand = True
        if section_motion_enabled:
            header = MotionEntry(
                content=header,
                offset=ft.Offset(0, -0.03),
                duration_name="normal",
                key=f"chat-header-{self._chat_entry_seed}-{self._chat_mode_seed}",
            )
        input_bar: ft.Control = ChatInputBar(
            role=role,
            is_dark=self._is_dark,
            mode=self._chat_mode,
            on_send=self._send_message,
            on_voice=lambda _: self._callback.on_voice_requested(),
            initial_value=self._chat_input_value(role.id, self._chat_mode),
            on_change=lambda value, role_id=role.id, mode=self._chat_mode: self._set_chat_input_value(role_id, mode, value),
        )
        if section_motion_enabled:
            input_bar = MotionEntry(
                content=input_bar,
                delay_ms=180,
                offset=ft.Offset(0, 0.04),
                duration_name="normal",
                key=f"chat-input-{self._chat_entry_seed}-{self._chat_mode_seed}",
            )
        body_host: ft.Control = body
        if section_motion_enabled:
            body_host = ft.AnimatedSwitcher(
                content=body,
                duration=MOTION["normal"],
                reverse_duration=MOTION["fast"],
                switch_in_curve=ft.AnimationCurve.FAST_OUT_SLOWIN,
                switch_out_curve=ft.AnimationCurve.EASE_IN_OUT,
                transition=ft.AnimatedSwitcherTransition.FADE,
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
                        content=body_host,
                    ),
                    input_bar,
                ],
            ),
        )

    def _editable_chat_avatar(self, role: CompanionRole, colors: dict[str, str]) -> ft.Control:
        return ft.GestureDetector(
            on_long_press=lambda _: self._begin_edit_role(role.id),
            content=ft.Container(
                content=avatar(role.avatar_path, 36, colors["card_border"], self._is_dark),
            ),
        )

    def _mode_switch(self, colors: dict[str, str]) -> ft.Container:
        return ft.Container(
            padding=4,
            border_radius=16,
            bgcolor=colors["card"],
            border=ft.Border.all(1, colors["card_border"]),
            content=ft.Row(
                spacing=4,
                controls=[
                    self._mode_button("normal", ft.Icons.CHAT_BUBBLE_OUTLINE, "常规聊天", colors),
                    self._mode_button("immersive", ft.Icons.AUTO_AWESOME, "沉浸陪伴", colors),
                ],
            ),
        )

    def _mode_button(self, mode: str, icon: str, tooltip: str, colors: dict[str, str]) -> ft.IconButton:
        active = self._chat_mode == mode
        border_color = hex_with_alpha(self.active_role.accent_color, 70) if active else colors["card_border"]
        return ft.IconButton(
            icon=icon,
            icon_size=16,
            icon_color=colors["text"] if active else colors["text_secondary"],
            bgcolor=hex_with_alpha(self.active_role.accent_color, 58) if active else None,
            tooltip=tooltip,
            width=32,
            height=32,
            alignment=ft.Alignment(0, 0),
            padding=0,
            splash_radius=18,
            scale=1.0,
            animate_scale=animation("fast", phase="press"),
            animate_opacity=animation("normal"),
            style=ft.ButtonStyle(
                padding=0,
                side=ft.BorderSide(1, border_color),
                shape=ft.RoundedRectangleBorder(radius=16),
            ),
            on_click=animated_click(lambda _: self._set_chat_mode(mode)),
        )

    def _latest_role_reply_text(self, role: CompanionRole) -> str:
        return next((message.text for message in reversed(self._messages) if message.role_id == role.id and not message.is_user), "")

    def _normalize_emotion(self, emotion: str) -> str:
        return str(emotion or "").strip().replace("_zh", "").lower()

    def _chat_status_value(self, role: CompanionRole) -> str:
        if self._typing:
            return TYPING_STATUS_TEXT
        emotion = self._normalize_emotion(self._reply_emotions.get(role.id, ""))
        if emotion:
            return REPLY_EMOTION_STATUS.get(emotion, emotion)
        return ""

    def _refresh_chat_status(self) -> bool:
        if self._page_name != "chat" or self._chat_status_text is None or not self._roles:
            return False
        self._chat_status_text.value = self._chat_status_value(self.active_role)
        try:
            self._chat_status_text.update()
        except (AssertionError, RuntimeError):
            return False
        return True

    def _role_messages(self, role_id: str) -> list[ChatMessage]:
        return [message for message in self._messages if message.role_id == role_id]

    def _recent_roles(self) -> list[CompanionRole]:
        return sorted(self._roles, key=lambda role: role.last_timestamp, reverse=True)

    def _sync_role_recent_message(self, role_id: str) -> None:
        role = next((candidate for candidate in self._roles if candidate.id == role_id), None)
        if role is None:
            return
        latest = next((message for message in reversed(self._normal_display_messages(role_id)) if message.text.strip()), None)
        if latest is None:
            role.last_message = ""
            role.last_time = ""
            role.last_timestamp = 0.0
            return
        role.last_message = latest.text
        role.last_time = latest.timestamp.strftime("%H:%M")
        role.last_timestamp = latest.timestamp.timestamp()

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
        self._scroll_generation += 1
        generation = self._scroll_generation

        async def _scroll_now() -> None:
            await self._scroll_chat_to_latest_async(generation)

        async def _after_mount() -> None:
            await asyncio.sleep(0.05)
            await self._scroll_chat_to_latest_async(generation)

        run_task = getattr(page, "run_task", None)
        if not callable(run_task):
            return
        try:
            run_task(_scroll_now)
            run_task(_after_mount)
        except (AssertionError, RuntimeError, TypeError, AttributeError):
            return

    async def _scroll_chat_to_latest_async(self, generation: int | None = None) -> None:
        if generation is not None and generation != self._scroll_generation:
            return
        if self._chat_mode != "normal" or self._chat_list_view is None:
            return
        if not self._has_normal_chat_content(self.active_role.id):
            return
        try:
            await self._chat_list_view.scroll_to(offset=0, duration=0)
            if generation is not None and generation != self._scroll_generation:
                return
            self._chat_list_view.update()
        except (AssertionError, RuntimeError, TypeError, AttributeError):
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
            return ""
        return self._immersive_segments[self._immersive_index]

    def _visible_immersive_text(self, role: CompanionRole) -> str:
        if not self._immersive_segments:
            return self._current_immersive_text(role)
        return self._immersive_display_text

    def _set_immersive_dialogue_text(
        self,
        value: str,
        *,
        expected_control: ft.Text | None = None,
        generation: int | None = None,
    ) -> bool:
        dialogue_text = self._immersive_dialogue_text
        if dialogue_text is None:
            return False
        if expected_control is not None and dialogue_text is not expected_control:
            return False
        if generation is not None and generation != self._immersive_typewriter_generation:
            return False
        dialogue_text.value = value
        try:
            dialogue_text.page
        except (AssertionError, RuntimeError, TypeError, AttributeError):
            return True
        try:
            dialogue_text.update()
        except (AssertionError, RuntimeError, TypeError, AttributeError):
            return False
        return True

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
        dialogue_text = self._immersive_dialogue_text
        role_id = self.active_role.id
        mode_seed = self._chat_mode_seed

        async def _run_typewriter() -> None:
            await asyncio.sleep(0)
            while generation == self._immersive_typewriter_generation:
                if (
                    self._page_name != "chat"
                    or self._chat_mode != "immersive"
                    or self._chat_mode_seed != mode_seed
                    or self.active_role.id != role_id
                    or self._immersive_dialogue_text is not dialogue_text
                ):
                    return
                target = self._current_immersive_text(self.active_role)
                if self._immersive_display_text == target:
                    return
                if target.startswith(self._immersive_display_text):
                    next_length = min(len(target), len(self._immersive_display_text) + 1)
                    self._immersive_display_text = target[:next_length]
                else:
                    self._immersive_display_text = target[:1]
                if not self._set_immersive_dialogue_text(
                    self._immersive_display_text,
                    expected_control=dialogue_text,
                    generation=generation,
                ):
                    return
                await asyncio.sleep(0.025)

        run_task = getattr(page, "run_task", None)
        if not callable(run_task):
            return
        try:
            run_task(_run_typewriter)
        except (AssertionError, RuntimeError, TypeError, AttributeError):
            return

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
            except (AssertionError, RuntimeError, TypeError, AttributeError):
                return False
            self._trigger_scroll_to_latest()
            return True

        if self._immersive_dialogue_text is None:
            return False
        self._reset_immersive_state(role)
        if not self._set_immersive_dialogue_text(self._visible_immersive_text(role)):
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
            padding=ft.Padding.symmetric(horizontal=16, vertical=10),
            content=self._chat_list_view,
        )

    def _typing_indicator(self, role: CompanionRole, colors: dict[str, str]) -> ft.Control:
        return ft.Row(
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                avatar(role.avatar_path, 32, colors["card_border"], self._is_dark),
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                    border_radius=14,
                    bgcolor=colors["message"],
                    border=ft.Border.all(1, colors["message_border"]),
                    content=TypingDots(colors["text_secondary"]),
                ),
            ],
        )

    def _build_immersive_chat(self, colors: dict[str, str], role: CompanionRole) -> ft.Control:
        self._reset_immersive_state(role)
        self._immersive_dialogue_text = text(self._visible_immersive_text(role), 15, colors["text_soft"], max_lines=None)
        self._schedule_immersive_typewriter()
        self._immersive_portrait_container = ft.Container(
            alignment=ft.Alignment(0, 1),
            content=self._immersive_portrait_content(role, colors),
        )
        portrait: ft.Control = self._immersive_portrait_container
        dialogue: ft.Control = ft.Container(
            height=168,
            margin=ft.Margin(left=16, right=16, bottom=12),
            padding=ft.Padding.symmetric(horizontal=18, vertical=16),
            border_radius=24,
            gradient=glass_gradient(role.accent_color, self._is_dark, strong=True),
            border=ft.Border.all(1, hex_with_alpha(role.accent_color, 0x36 if self._is_dark else 0x48)),
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
                        padding=ft.Padding.only(left=10, right=10, top=10),
                        content=portrait,
                    ),
                    dialogue,
                ],
            ),
        )

    def _current_portrait_path(self, role: CompanionRole) -> str:
        emotion = self._normalize_emotion(self._reply_emotions.get(role.id, ""))
        if emotion:
            portrait_path = role.portraits.get(emotion, "")
            if portrait_path:
                return portrait_path
        return role.portraits.get("neutral", "") or role.standing_image_path

    def _immersive_portrait_content(self, role: CompanionRole, colors: dict[str, str]) -> ft.Control:
        portrait_path = self._current_portrait_path(role)
        if portrait_path:
            return ft.Image(src=portrait_path, fit=IMAGE_CONTAIN, width=390, height=520)
        return ft.Icon(ft.Icons.PERSON_OUTLINE, size=120, color=colors["text_tertiary"])

    def _refresh_immersive_portrait(self) -> bool:
        if self._page_name != "chat" or self._chat_mode != "immersive" or self._immersive_portrait_container is None:
            return False
        self._immersive_portrait_container.content = self._immersive_portrait_content(self.active_role, self._colors())
        try:
            self._immersive_portrait_container.update()
        except (AssertionError, RuntimeError):
            return False
        return True

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
        self._provider_dropdown = dropdown(
            label="模型来源",
            value=self._settings.model_provider,
            options=[ft.dropdown.Option(key, label) for key, label in SETTINGS_PROVIDERS],
            on_select=self._on_settings_provider_changed,
            **dropdown_control_style(colors, radius=14, text_size=12),
        )
        self._model_dropdown = dropdown(
            label="模型",
            value=self._settings.model_name,
            options=self._settings_model_options(self._settings.model_provider),
            **dropdown_control_style(colors, radius=14, text_size=12),
        )
        self._ensure_settings_model_value()
        self._api_key_field = FormField("接口密钥", "sk-...", colors, password=True)
        self._api_key_field.value = self._settings.api_key

        controls = [
            self._stagger("settings", 0, self._header("设置", colors, lambda _: self.go_back()), offset_y=0.02),
            # self._stagger("settings", 1, self._settings_profile_card(colors)),
            self._stagger("settings", 2, section_card(self._quality_card(colors), colors)),
            self._stagger("settings", 3, section_card(self._provider_card(colors), colors)),
            self._stagger("settings", 4, section_card(self._api_key_card(colors), colors)),
            self._stagger("settings", 5, self._primary_button("保存", self.active_role.accent_color, lambda _: self._save_settings())),
            ft.Container(height=28),
        ]
        return self._page_column([ft.Container(padding=ft.Padding.symmetric(horizontal=20), content=ft.Column(spacing=14, controls=controls))])

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
            "minimax": "MiniMax M2.5",
            "deepseek": "DeepSeek V4 Flash / Pro",
        }.get(self._provider_dropdown.value or "minimax", "MiniMax M2.5")
        self._provider_desc_text = text(provider_desc, 11, colors["text_tertiary"])
        return ft.Column(
            spacing=8,
            controls=[
                text("模型来源", 13, colors["text_secondary"]),
                self._provider_dropdown,
                self._model_dropdown,
                self._provider_desc_text,
            ],
        )

    def _settings_model_options(self, provider: str | None) -> list[ft.dropdown.Option]:
        models = SETTINGS_MODELS.get(provider or "minimax", SETTINGS_MODELS["minimax"])
        return [ft.dropdown.Option(key, label) for key, label in models]

    def _ensure_settings_model_value(self) -> None:
        provider = self._provider_dropdown.value or "minimax"
        allowed = {key for key, _label in SETTINGS_MODELS.get(provider, SETTINGS_MODELS["minimax"])}
        if self._model_dropdown.value not in allowed:
            self._model_dropdown.value = DEFAULT_SETTINGS_MODELS.get(provider, DEFAULT_SETTINGS_MODELS["minimax"])

    def _on_settings_provider_changed(self, _event: ft.ControlEvent | None = None) -> None:
        event_control = getattr(_event, "control", None)
        provider = getattr(event_control, "value", None) or self._provider_dropdown.value or "minimax"
        self._model_dropdown.options = self._settings_model_options(provider)
        self._ensure_settings_model_value()
        self._settings.model_provider = provider
        self._settings.model_name = self._model_dropdown.value or DEFAULT_SETTINGS_MODELS.get(provider, DEFAULT_SETTINGS_MODELS["minimax"])
        if hasattr(self, "_provider_desc_text"):
            self._provider_desc_text.value = {
                "minimax": "MiniMax M2.5",
                "deepseek": "DeepSeek V4 Flash / Pro",
            }.get(provider, "MiniMax M2.5")
        try:
            self._provider_dropdown.update()
            self._model_dropdown.update()
            if hasattr(self, "_provider_desc_text"):
                self._provider_desc_text.update()
        except (AssertionError, RuntimeError):
            return

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
                key=f"create-step-{self._create_mode}-{self._editing_role_id}-{self._create_step}-{self._create_step_seed}",
            )
        step_switcher = ft.AnimatedSwitcher(
            content=step_content,
            duration=MOTION["normal"],
            reverse_duration=MOTION["fast"],
            switch_in_curve=ft.AnimationCurve.FAST_OUT_SLOWIN,
            switch_out_curve=ft.AnimationCurve.EASE_IN_OUT,
            transition=ft.AnimatedSwitcherTransition.FADE,
        )
        title = "\u7f16\u8f91\u89d2\u8272" if self._create_mode == "edit" else "\u521b\u5efa\u89d2\u8272"
        header_action = self._delete_role_header_button(colors) if self._create_mode == "edit" else None
        controls = [
            self._stagger("create", 0, self._header(title, colors, lambda _: self.go_back(), action=header_action), offset_y=0.02),
            self._stagger("create", 1, self._create_progress(colors)),
            self._stagger("create", 2, ft.Container(content=step_switcher), offset_y=0.03),
            self._stagger("create", 3, self._create_footer(colors), offset_y=0.03),
            ft.Container(height=24),
        ]
        return self._page_column([ft.Container(padding=ft.Padding.only(left=20, right=20, top=4, bottom=20), content=ft.Column(spacing=18, controls=controls))])

    def _delete_role_header_button(self, colors: dict[str, str]) -> ft.Control:
        return ft.Container(
            width=40,
            height=40,
            border_radius=20,
            tooltip="\u5220\u9664\u4eba\u683c",
            bgcolor=hex_with_alpha("#D92D20", 24 if self._is_dark else 30),
            border=ft.Border.all(1, hex_with_alpha("#D92D20", 72 if self._is_dark else 58)),
            alignment=ft.Alignment(0, 0),
            ink=True,
            scale=1.0,
            animate_scale=animation("fast", phase="press"),
            on_click=animated_click(lambda _: self._confirm_delete_role(self._editing_role_id)),
            content=ft.Icon(ft.Icons.DELETE_OUTLINE, size=19, color="#F04438" if self._is_dark else "#B42318"),
        )

    def _create_progress(self, colors: dict[str, str]) -> ft.Control:
        accent_color = self._create_accent_color()
        bars: list[ft.Control] = []
        for index in range(1, 6):
            active = index <= self._create_step
            bars.append(
                ft.Container(
                    expand=True,
                    height=8,
                    border_radius=999,
                    bgcolor=hex_with_alpha(accent_color, 210 if active else 42),
                    opacity=1.0 if active else 0.82,
                    animate_opacity=animation("normal"),
                    animate_scale=animation("normal"),
                    scale=1.0 if active else 0.98,
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
            padding=22,
            solid=True,
            radius=28,
        )

    def _create_footer(self, colors: dict[str, str]) -> ft.Control:
        final_label = "\u4fdd\u5b58" if self._create_mode == "edit" else "\u521b\u5efa"
        accent_color = self._create_accent_color()
        return ft.Row(
            spacing=10,
            controls=[
                ft.Container(expand=True, content=self._secondary_button("上一步", colors, lambda _: self._previous_step(), ft.Icons.CHEVRON_LEFT, subtle=self._create_step == 1)),
                ft.Container(
                    expand=True,
                    content=self._primary_button(final_label if self._create_step == 5 else "下一步", accent_color, lambda _: self._next_step(), ft.Icons.CHECK if self._create_step == 5 else ft.Icons.CHEVRON_RIGHT),
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
        self._brain_id_field = FormField("角色标识", "companion-id", colors, solid=True)
        self._brain_id_field.value = self._draft.brain_id
        self._brain_id_field.disabled = self._create_mode == "edit"
        self._brain_id_field.on_change = lambda _: self._sync_basic_draft()
        self._template_dropdown = dropdown(
            label="模板",
            value=self._draft.template or "default",
            options=[ft.dropdown.Option("default", "默认"), ft.dropdown.Option("empathetic", "共情"), ft.dropdown.Option("strict", "克制")],
            **dropdown_control_style(colors, radius=18, text_size=13),
        )
        self._template_dropdown.disabled = self._create_mode == "edit"
        self._template_dropdown.on_change = lambda _: self._sync_basic_draft()
        self._name_field = FormField("名称", "角色名称", colors, solid=True)
        self._name_field.value = self._draft.name
        self._name_field.on_change = lambda _: self._sync_basic_draft()
        self._description_field = FormField("描述", "简短描述这个角色", colors, multiline=True, solid=True)
        self._description_field.value = self._draft.description
        self._description_field.on_change = lambda _: self._sync_basic_draft()
        return section_card(
            ft.Column(
                spacing=12,
                controls=[
                    text("基础信息", 18, colors["text"], ft.FontWeight.W_500),
                    self._brain_id_field,
                    self._template_dropdown,
                    self._name_field,
                    self._description_field,
                    self._card_color_selector(colors),
                ],
            ),
            colors,
            padding=22,
            solid=True,
            radius=28,
        )

    def _card_color_selector(self, colors: dict[str, str]) -> ft.Control:
        selected_color = self._draft.accent_color.strip()
        controls: list[ft.Control] = []
        for _, label, color in CARD_COLOR_PRESETS:
            selected = selected_color == color
            controls.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                    border_radius=14,
                    bgcolor=hex_with_alpha(color, 42) if selected else colors["card_strong"],
                    border=ft.Border.all(1, hex_with_alpha(color, 120) if selected else colors["card_border"]),
                    ink=True,
                    scale=1.0,
                    animate_scale=animation("fast", phase="press"),
                    on_click=animated_click(lambda _, value=color: self._set_draft_accent_color(value)),
                    content=ft.Row(
                        spacing=7,
                        tight=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(width=14, height=14, border_radius=7, bgcolor=color, border=ft.Border.all(1, hex_with_alpha("#FFFFFF", 90))),
                            text(label, 11, colors["text"] if selected else colors["text_secondary"], max_lines=1),
                        ],
                    ),
                )
            )
        return ft.Column(
            spacing=8,
            controls=[
                text("卡片配色", 13, colors["text"], ft.FontWeight.W_500),
                ft.Row(spacing=8, wrap=True, controls=controls),
            ],
        )

    def _portrait_step(self, colors: dict[str, str]) -> ft.Control:
        chips = []
        visible_emotions = PORTRAIT_EMOTIONS if self._portrait_extra_open else [PORTRAIT_EMOTIONS[0]]
        for emotion_id, label in visible_emotions:
            selected = emotion_id == self._emotion_id
            chips.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=10, vertical=7),
                    border_radius=14,
                    bgcolor=hex_with_alpha(self.active_role.accent_color, 58 if selected else 0),
                    border=ft.Border.all(1, hex_with_alpha(self.active_role.accent_color, 80) if selected else colors["card_border"]),
                    ink=True,
                    scale=1.0,
                    animate_scale=animation("fast", phase="press"),
                    on_click=animated_click(lambda _, value=emotion_id: self._set_emotion(value)),
                    content=text(label, 11, colors["text"] if selected else colors["text_secondary"]),
                )
            )
        emotion_row_controls: list[ft.Control] = chips
        if not self._portrait_extra_open:
            emotion_row_controls.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=10, vertical=7),
                    border_radius=14,
                    bgcolor=colors.get("surface_solid", colors["card"]),
                    border=ft.Border.all(1, colors.get("dropdown_border", colors["card_border"])),
                    ink=True,
                    scale=1.0,
                    animate_scale=animation("fast", phase="press"),
                    on_click=animated_click(lambda _: self._show_more_portrait_emotions()),
                    content=ft.Row(
                        spacing=5,
                        tight=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.ADD, size=13, color=colors["text_secondary"]),
                            text("更多表情", 11, colors["text_secondary"], max_lines=1),
                        ],
                    ),
                )
            )
        emotion_controls: list[ft.Control] = [ft.Row(spacing=8, wrap=True, controls=emotion_row_controls)]
        avatar_path = self._draft.avatar_path
        preview_path = self._draft.portraits.get(self._emotion_id, "")
        self._portrait_preview_container = ft.Container(
            height=260,
            border_radius=18,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            bgcolor=colors["muted"],
            border=ft.Border.all(1, colors["card_border"]),
            alignment=ft.Alignment(0, 0),
            content=self._portrait_preview_content(preview_path, colors),
        )
        return section_card(
            ft.Column(
                spacing=12,
                controls=[
                    text("立绘设置", 18, colors["text"], ft.FontWeight.W_500),
                    text("选择情绪并上传对应立绘。", 12, colors["text_secondary"]),
                    ft.Row(
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(
                                width=82,
                                height=82,
                                border_radius=41,
                                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                                bgcolor=colors["muted"],
                                border=ft.Border.all(1, colors["card_border"]),
                                content=ft.Image(src=avatar_path, fit=IMAGE_COVER)
                                if avatar_path
                                else ft.Icon(ft.Icons.PERSON, size=28, color=colors["text_tertiary"]),
                            ),
                            ft.Container(
                                expand=True,
                                content=ft.Column(
                                    spacing=8,
                                    controls=[
                                        text("头像", 13, colors["text"], ft.FontWeight.W_500),
                                        ft.Row(
                                            spacing=8,
                                            controls=[
                                                ft.Container(expand=True, content=self._secondary_button("替换", colors, lambda _: self._upload_create_avatar(), ft.Icons.IMAGE_OUTLINED)),
                                                ft.Container(expand=True, content=self._secondary_button("移除", colors, lambda _: self._remove_create_avatar(), ft.Icons.DELETE_OUTLINE, subtle=True)),
                                            ],
                                        ),
                                    ],
                                ),
                            ),
                        ],
                    ),
                    *emotion_controls,
                    self._portrait_preview_container,
                    ft.Row(
                        spacing=10,
                        controls=[
                            ft.Container(expand=True, content=self._primary_button("更换立绘", self.active_role.accent_color, lambda _: self._upload_portrait(), ft.Icons.ADD_PHOTO_ALTERNATE_OUTLINED)),
                            ft.Container(expand=True, content=self._secondary_button("移除", colors, lambda _: self._remove_portrait(), ft.Icons.DELETE_OUTLINE, subtle=True)),
                        ],
                    ),
                    self._portrait_processing_panel(colors),
                ],
            ),
            colors,
            padding=22,
            solid=True,
            radius=28,
        )

    def _portrait_preview_content(self, preview_path: str, colors: dict[str, str]) -> ft.Control:
        if preview_path:
            return ft.Image(src=preview_path, fit=IMAGE_CONTAIN)
        return ft.Icon(ft.Icons.PERSON_OUTLINE, size=56, color=colors["text_tertiary"])

    def _refresh_portrait_preview_control(self, emotion_id: str) -> bool:
        if emotion_id != self._emotion_id or self._portrait_preview_container is None:
            return False
        self._portrait_preview_container.content = self._portrait_preview_content(
            self._draft.portraits.get(emotion_id, ""),
            self._colors(),
        )
        return self._try_update_control(self._portrait_preview_container)

    def _portrait_processing_panel(self, colors: dict[str, str]) -> ft.Control:
        edit = self._draft.portrait_edits.get(self._emotion_id)
        self._portrait_value_labels = {}
        if edit is None or not edit.source_path:
            return ft.Container(
                padding=ft.Padding.symmetric(horizontal=14, vertical=12),
                border_radius=14,
                bgcolor=hex_with_alpha(self.active_role.accent_color, 28),
                border=ft.Border.all(1, hex_with_alpha(self.active_role.accent_color, 58)),
                content=ft.Row(
                    spacing=8,
                    controls=[
                        ft.Icon(ft.Icons.CONTENT_CUT, size=16, color=colors["text_secondary"]),
                        text("上传立绘后可进行抠图和对齐。", 12, colors["text_secondary"]),
                    ],
                ),
            )

        self._portrait_tolerance_slider = self._portrait_slider(0, 120, 24, edit.tolerance)
        self._portrait_feather_slider = self._portrait_slider(0, 8, 8, edit.feather)
        self._portrait_scale_slider = self._portrait_slider(0.5, 1.5, 20, edit.scale)
        self._portrait_offset_x_slider = self._portrait_slider(-120, 120, 24, edit.offset_x)
        self._portrait_offset_y_slider = self._portrait_slider(-120, 120, 24, edit.offset_y)

        warning = ft.Container()
        if edit.warning:
            warning = ft.Container(
                padding=ft.Padding.symmetric(horizontal=12, vertical=9),
                border_radius=12,
                bgcolor=hex_with_alpha("#F59E0B", 34),
                border=ft.Border.all(1, hex_with_alpha("#F59E0B", 78)),
                content=text(edit.warning, 11, colors["text_secondary"]),
            )

        status = ft.Container()
        if self._portrait_rendering_emotion_id == self._emotion_id:
            status = ft.Container(
                padding=ft.Padding.symmetric(horizontal=12, vertical=9),
                border_radius=12,
                bgcolor=hex_with_alpha(self.active_role.accent_color, 28),
                border=ft.Border.all(1, hex_with_alpha(self.active_role.accent_color, 58)),
                content=ft.Row(
                    spacing=8,
                    controls=[
                        ft.ProgressRing(width=14, height=14, stroke_width=2, color=self.active_role.accent_color),
                        text("正在生成预览...", 11, colors["text_secondary"]),
                    ],
                ),
            )

        preset_controls = [
            self._portrait_preset_button(preset_id, label, edit, colors)
            for preset_id, label, _, _ in PORTRAIT_CUTOUT_PRESETS
        ]
        advanced_controls: list[ft.Control] = []
        if self._portrait_advanced_open:
            advanced_controls = [
                self._portrait_slider_row("背景清理强度", self._portrait_tolerance_slider, colors, "tolerance", "int"),
                self._portrait_slider_row("边缘柔和度", self._portrait_feather_slider, colors, "feather", "int"),
                self._portrait_slider_row("缩放", self._portrait_scale_slider, colors, "scale", "scale"),
                self._portrait_slider_row("横向偏移", self._portrait_offset_x_slider, colors, "offset_x", "int"),
                self._portrait_slider_row("纵向偏移", self._portrait_offset_y_slider, colors, "offset_y", "int"),
            ]

        return ft.Container(
            padding=14,
            border_radius=18,
            bgcolor=colors["input"],
            border=ft.Border.all(1, colors["input_border"]),
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.CONTENT_CUT, size=16, color=colors["text_secondary"]),
                            ft.Column(
                                spacing=1,
                                controls=[
                                    text("抠图预设", 12, colors["text"], ft.FontWeight.W_500),
                                    text("调整后会自动刷新预览", 11, colors["text_tertiary"]),
                                ],
                            ),
                        ],
                    ),
                    ft.Row(spacing=8, wrap=True, controls=preset_controls),
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.COLORIZE_OUTLINED, size=16, color=colors["text_secondary"]),
                            ft.Column(
                                spacing=1,
                                controls=[
                                    text("选择背景位置", 12, colors["text"], ft.FontWeight.W_500),
                                    text("选一块纯背景作为清理参考", 11, colors["text_tertiary"]),
                                ],
                            ),
                            ft.Container(width=18, height=18, border_radius=9, bgcolor=self._portrait_color_hex(edit.background_color), border=ft.Border.all(1, colors["card_border"])),
                        ],
                    ),
                    ft.Row(
                        spacing=8,
                        wrap=True,
                        controls=[
                            self._mini_button("左上角", colors, lambda _: self._set_portrait_background("top_left")),
                            self._mini_button("右上角", colors, lambda _: self._set_portrait_background("top_right")),
                            self._mini_button("左下角", colors, lambda _: self._set_portrait_background("bottom_left")),
                            self._mini_button("右下角", colors, lambda _: self._set_portrait_background("bottom_right")),
                        ],
                    ),
                    self._mini_button("收起高级微调" if self._portrait_advanced_open else "高级微调", colors, lambda _: self._toggle_portrait_advanced()),
                    *advanced_controls,
                    status,
                    warning,
                ],
            ),
        )

    def _portrait_slider(self, min_value: float, max_value: float, divisions: int, value: float) -> ft.Slider:
        return ft.Slider(
            min=min_value,
            max=max_value,
            divisions=divisions,
            value=value,
            active_color=self.active_role.accent_color,
            inactive_color=self._colors()["muted"],
            on_change=lambda _: self._queue_portrait_preview(refresh_page=False),
        )

    def _portrait_slider_row(self, label: str, slider: ft.Slider, colors: dict[str, str], value_key: str, value_format: str) -> ft.Control:
        value_label = text(self._format_portrait_slider_value(slider.value, value_format), 12, colors["text"], ft.FontWeight.W_600)
        self._portrait_value_labels[value_key] = value_label
        original_on_change = slider.on_change

        def handle_change(event) -> None:
            value_label.value = self._format_portrait_slider_value(slider.value, value_format)
            self._try_update_control(value_label)
            if original_on_change is not None:
                original_on_change(event)

        slider.on_change = handle_change
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border_radius=14,
            bgcolor=hex_with_alpha(self.active_role.accent_color, 18),
            border=ft.Border.all(1, hex_with_alpha(self.active_role.accent_color, 42)),
            content=ft.Column(
                spacing=4,
                controls=[
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(expand=True, content=text(label, 12, colors["text_secondary"], ft.FontWeight.W_500)),
                            ft.Container(
                                padding=ft.Padding.symmetric(horizontal=9, vertical=4),
                                border_radius=10,
                                bgcolor=colors["card_strong"],
                                border=ft.Border.all(1, colors["card_border"]),
                                content=value_label,
                            ),
                        ],
                    ),
                    ft.Container(height=36, content=slider),
                ],
            ),
        )

    def _format_portrait_slider_value(self, value: object, value_format: str) -> str:
        numeric_value = float(value or 0)
        if value_format == "scale":
            return f"{numeric_value:.2f}"
        return str(int(round(numeric_value)))

    def _refresh_portrait_value_label(self, value_key: str, value_format: str, value: object) -> None:
        label = self._portrait_value_labels.get(value_key)
        if label is None:
            return
        label.value = self._format_portrait_slider_value(value, value_format)
        self._try_update_control(label)

    def _portrait_preset_button(self, preset_id: str, label: str, edit: PortraitEditDraft, colors: dict[str, str]) -> ft.Control:
        selected = self._portrait_preset_id(edit) == preset_id
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            border_radius=12,
            bgcolor=hex_with_alpha(self.active_role.accent_color, 48) if selected else colors["card_strong"],
            border=ft.Border.all(1, hex_with_alpha(self.active_role.accent_color, 88) if selected else colors["card_border"]),
            ink=True,
            scale=1.0,
            animate_scale=animation("fast", phase="press"),
            on_click=animated_click(lambda _, value=preset_id: self._set_portrait_preset(value)),
            content=text(label, 11, colors["text"]),
        )

    def _mini_button(self, label: str, colors: dict[str, str], on_click) -> ft.Control:
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=10, vertical=7),
            border_radius=12,
            bgcolor=colors["card_strong"],
            border=ft.Border.all(1, colors["card_border"]),
            ink=True,
            scale=1.0,
            animate_scale=animation("fast", phase="press"),
            on_click=animated_click(on_click),
            content=text(label, 11, colors["text"]),
        )

    def _portrait_color_hex(self, color: tuple[int, int, int]) -> str:
        red, green, blue = [max(0, min(255, int(channel))) for channel in color]
        return f"#{red:02X}{green:02X}{blue:02X}"

    def _personality_step(self, colors: dict[str, str]) -> ft.Control:
        self._age_field = FormField("年龄", "可选", colors, solid=True)
        self._age_field.value = self._draft.age
        self._age_field.on_change = lambda _: self._sync_personality_draft()
        self._gender_dropdown = dropdown(
            label="性别",
            value=self._draft.gender or "unknown",
            options=[ft.dropdown.Option("unknown", "未知"), ft.dropdown.Option("female", "女性"), ft.dropdown.Option("male", "男性"), ft.dropdown.Option("other", "其他")],
            **dropdown_control_style(colors, radius=18, text_size=13),
        )
        self._birthday_field = FormField("生日", "YYYY-MM-DD", colors, solid=True)
        self._gender_dropdown.on_change = lambda _: self._sync_personality_draft()
        self._birthday_field.value = self._draft.birthday
        self._birthday_field.on_change = lambda _: self._sync_personality_draft()
        self._background_field = FormField("背景", "角色经历与上下文", colors, multiline=True, solid=True)
        self._background_field.value = self._draft.background
        self._background_field.on_change = lambda _: self._sync_personality_draft()
        self._style_dropdown = dropdown(
            label="语言风格预设",
            value=self._draft.speaking_style_preset or "friendly",
            options=[ft.dropdown.Option("friendly", "友好"), ft.dropdown.Option("calm", "冷静"), ft.dropdown.Option("confident", "自信"), ft.dropdown.Option("direct", "直接")],
            **dropdown_control_style(colors, radius=18, text_size=13),
        )
        self._trait_field = FormField("添加特质", "例如：耐心", colors, solid=True)
        self._interest_field = FormField("添加兴趣", "例如：钢琴", colors, solid=True)
        self._style_dropdown.on_change = lambda _: self._sync_personality_draft()
        self._trait_chips = self._chip_wrap(self._draft.personality_traits, colors, self._remove_trait)
        self._interest_chips = self._chip_wrap(self._draft.interests, colors, self._remove_interest)
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
                    padding=22,
                    solid=True,
                    radius=28,
                ),
                section_card(
                    ft.Column(
                        spacing=10,
                        controls=[
                            text("特质", 13, colors["text_secondary"]),
                            ft.Row(spacing=8, controls=[ft.Container(expand=True, content=self._trait_field), self._small_add_button(colors, lambda _: self._add_trait())]),
                            self._trait_chips,
                            text("兴趣", 13, colors["text_secondary"]),
                            ft.Row(spacing=8, controls=[ft.Container(expand=True, content=self._interest_field), self._small_add_button(colors, lambda _: self._add_interest())]),
                            self._interest_chips,
                        ],
                    ),
                    colors,
                    padding=20,
                    solid=True,
                    radius=28,
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
        self._memory_list = ft.Column(spacing=12, controls=self._memory_controls(colors))
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
                self._memory_list,
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
            padding=22,
            solid=True,
            radius=28,
        )

    def _compact_dropdown(self, label: str, value: str, options: list[tuple[str, str]], colors: dict[str, str]) -> ft.Dropdown:
        return dropdown(
            label=label,
            value=value,
            options=[ft.dropdown.Option(key, title) for key, title in options],
            **dropdown_control_style(colors, radius=18, text_size=13),
        )

    def _slider_block(self, label: str, slider: ft.Slider, colors: dict[str, str]) -> ft.Control:
        return ft.Column(spacing=4, controls=[text(label, 12, colors["text_secondary"]), slider])

    def _memory_controls(self, colors: dict[str, str]) -> list[ft.Control]:
        self._memory_editors = []
        controls: list[ft.Control] = []
        for index, memory in enumerate(self._draft.memories):
            editor = MemoryEditor(memory, colors, lambda idx=index: self._remove_memory(idx))
            self._memory_editors.append(editor)
            controls.append(editor)
        if controls:
            return controls
        return [
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
                padding=22,
                solid=True,
                radius=28,
            )
        ]

    def _chip_controls(self, values: list[str], colors: dict[str, str], on_remove) -> list[ft.Control]:
        if not values:
            return [text("还没有条目。", 11, colors["text_tertiary"])]
        chips: list[ft.Control] = []
        for item in values:
            chips.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                    border_radius=14,
                    bgcolor=colors["muted"],
                    border=ft.Border.all(1, colors["card_border"]),
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
        return chips

    def _chip_wrap(self, values: list[str], colors: dict[str, str], on_remove) -> ft.Row:
        return ft.Row(spacing=8, wrap=True, controls=self._chip_controls(values, colors, on_remove))

    def _try_update_control(self, control: Optional[ft.Control]) -> bool:
        if control is None:
            return False
        try:
            control.update()
        except (AssertionError, RuntimeError):
            return False
        return True

    def _refresh_trait_chips(self) -> None:
        if self._trait_chips is None:
            return
        self._trait_chips.controls = self._chip_controls(self._draft.personality_traits, self._colors(), self._remove_trait)
        self._try_update_control(self._trait_chips)

    def _refresh_interest_chips(self) -> None:
        if self._interest_chips is None:
            return
        self._interest_chips.controls = self._chip_controls(self._draft.interests, self._colors(), self._remove_interest)
        self._try_update_control(self._interest_chips)

    def _refresh_memory_list(self) -> None:
        if self._memory_list is None:
            return
        self._memory_list.controls = self._memory_controls(self._colors())
        self._try_update_control(self._memory_list)

    def _header(self, title: str, colors: dict[str, str], on_back=None, action: ft.Control | None = None) -> ft.Container:
        return ft.Container(
            padding=ft.Padding.only(left=0, right=0, top=26, bottom=16),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    round_icon_button(ft.Icons.CHEVRON_LEFT, colors, on_back or (lambda _: self.go_back())),
                    text(title, 20, colors["text"], ft.FontWeight.W_500),
                    action or ft.Container(width=40),
                ],
            ),
        )

    def _button_content(self, label: str, color: str, icon: str | None = None, size: int = 15) -> ft.Control:
        if icon is None:
            return text(label, size, color, ft.FontWeight.W_500)
        return ft.Row(
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=7,
            tight=True,
            controls=[
                ft.Icon(icon, size=17, color=color),
                text(label, size, color, ft.FontWeight.W_500, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            ],
        )

    def _primary_button(self, label: str, color: str, on_click, icon: str | None = None) -> ft.Container:
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
            content=self._button_content(label, button_text, icon),
        )

    def _secondary_button(self, label: str, colors: dict[str, str], on_click, icon: str | None = None, subtle: bool = False) -> ft.Container:
        fill_color = colors.get("surface_solid", colors["card"]) if not subtle else colors["muted"]
        border_color = colors.get("dropdown_border", colors["card_border"]) if not subtle else colors["card_border"]
        return ft.Container(
            height=48,
            border_radius=18,
            bgcolor=fill_color,
            border=ft.Border.all(1, border_color),
            shadow=None if subtle else soft_shadow(self._is_dark, None, "card"),
            alignment=ft.Alignment(0, 0),
            ink=True,
            scale=1.0,
            animate_scale=animation("fast", phase="press"),
            on_click=animated_click(on_click),
            content=self._button_content(label, colors["text"], icon, size=14),
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

    def _handle_home_role_select(self, role_id: str) -> None:
        if self._is_mobile_platform():
            self._open_chat(role_id)
            return
        self.set_active_role(role_id)

    def _begin_open_chat(self, role_id: str) -> None:
        self._prepare_chat(role_id)
        self._callback.on_open_chat(role_id)
        self._chat_entry_seed += 1
        self._suppress_next_chat_entry_motion = True
        self.show_page("chat")

    def _open_chat(self, role_id: str) -> None:
        self._prepare_chat(role_id)
        self._callback.on_open_chat(role_id)
        self._chat_entry_seed += 1
        self._suppress_next_chat_entry_motion = True
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

    def _chat_input_key(self, role_id: str, mode: str) -> tuple[str, str]:
        return (role_id, mode)

    def _chat_input_value(self, role_id: str, mode: str) -> str:
        return self._chat_input_drafts.get(self._chat_input_key(role_id, mode), "")

    def _set_chat_input_value(self, role_id: str, mode: str, value: str) -> None:
        key = self._chat_input_key(role_id, mode)
        if value:
            self._chat_input_drafts[key] = value
        else:
            self._chat_input_drafts.pop(key, None)

    def _send_message(self, value: str) -> None:
        if not self._active_role_id:
            return
        self._set_chat_input_value(self._active_role_id, self._chat_mode, "")
        self.append_message(ChatMessage(f"user-{len(self._messages) + 1}", self._active_role_id, value, True, datetime.now()))
        self._callback.on_send_message(self._active_role_id, value, self._chat_mode)

    def _save_settings(self) -> None:
        self._settings.token_quality = int(self._quality_slider.value or 50)
        self._settings.model_provider = self._provider_dropdown.value or "minimax"
        self._settings.model_name = self._model_dropdown.value or DEFAULT_SETTINGS_MODELS.get(
            self._settings.model_provider,
            DEFAULT_SETTINGS_MODELS["minimax"],
        )
        self._settings.api_key = self._api_key_field.value or ""
        self._settings.user_name = self._settings_name_field.value or "用户"
        self._profile.name = self._settings.user_name
        self._callback.on_settings_saved(self._settings)
        self.show_page("home", add_to_history=False)

    def _set_emotion(self, emotion_id: str) -> None:
        self._emotion_id = emotion_id
        self._safe_update()

    def _show_more_portrait_emotions(self) -> None:
        self._portrait_extra_open = True
        self._safe_update()

    def _draft_has_extra_portraits(self) -> bool:
        emotion_ids = set(self._draft.portraits) | set(self._draft.portrait_edits)
        return any(emotion_id != "neutral" for emotion_id in emotion_ids)

    def _current_emotion_label(self) -> str:
        for emotion_id, label in PORTRAIT_EMOTIONS:
            if emotion_id == self._emotion_id:
                return label
        return "当前"

    def _sync_basic_draft(self) -> None:
        if not hasattr(self, "_brain_id_field"):
            return
        self._draft.brain_id = self._brain_id_field.value or ""
        self._draft.template = self._template_dropdown.value or "default"
        self._draft.name = self._name_field.value or ""
        self._draft.description = self._description_field.value or ""

    def _set_draft_accent_color(self, color: str) -> None:
        self._sync_basic_draft()
        self._draft.accent_color = color
        self._safe_update()

    def _sync_personality_draft(self) -> None:
        if not hasattr(self, "_age_field"):
            return
        self._draft.age = self._age_field.value or ""
        self._draft.gender = self._gender_dropdown.value or "unknown"
        self._draft.birthday = self._birthday_field.value or ""
        self._draft.background = self._background_field.value or ""
        self._draft.speaking_style_preset = self._style_dropdown.value or "friendly"

    def _persist_current_step(self) -> None:
        self._sync_basic_draft()
        self._sync_personality_draft()
        self._sync_current_portrait_edit_controls()
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

    def _sync_current_portrait_edit_controls(self) -> None:
        edit = self._draft.portrait_edits.get(self._emotion_id)
        if edit is not None:
            self._sync_portrait_edit_from_controls(edit)

    def _next_step(self) -> None:
        self._persist_current_step()
        if self._create_step < 5:
            self._create_step_direction = 1
            self._create_step += 1
            self._create_step_seed += 1
            self._safe_update()
            return
        if self._create_mode == "edit":
            self._callback.on_character_update_requested(self._editing_role_id or self._draft.brain_id, self._draft)
            return
        self._callback.on_character_create_requested(self._draft)

    def _previous_step(self) -> None:
        self._persist_current_step()
        if self._create_step > 1:
            self._create_step_direction = -1
            self._create_step -= 1
            self._create_step_seed += 1
            self._safe_update()

    def _upload_portrait(self) -> None:
        self._open_image_picker("portrait", self._emotion_id)

    def _remove_portrait(self) -> None:
        self._draft.portraits.pop(self._emotion_id, None)
        self._draft.portrait_edits.pop(self._emotion_id, None)
        if self._emotion_id == "neutral":
            self._draft.portrait_layout = None
        self._safe_update()

    def _process_current_portrait(self) -> None:
        self._queue_portrait_preview()

    def _process_portrait(
        self,
        emotion_id: str,
        *,
        refresh: bool = True,
        sync_controls: bool = True,
        expected_generation: int | None = None,
    ) -> bool:
        edit = self._draft.portrait_edits.get(emotion_id)
        if edit is None:
            return False
        if sync_controls:
            self._sync_portrait_edit_from_controls(edit)
        layout = None if emotion_id == "neutral" else self._draft.portrait_layout
        try:
            output_path = self._portrait_preview_output_path(emotion_id)
            old_output_path = self._portrait_preview_paths.get(emotion_id, "")
            output_path, resolved_layout, warning = export_aligned_portrait(edit, layout, output_path=output_path)
        except PortraitProcessingError as exc:
            self.show_notice(str(exc), is_error=True)
            return False
        if expected_generation is not None and expected_generation != self._portrait_preview_generation:
            self._cleanup_portrait_preview_path(str(output_path))
            return False
        edit.processed_path = str(output_path)
        edit.warning = warning
        self._draft.portraits[emotion_id] = str(output_path)
        self._portrait_preview_paths[emotion_id] = str(output_path)
        self._cleanup_portrait_preview_path(old_output_path, keep=str(output_path))
        if emotion_id == "neutral":
            self._draft.portrait_layout = resolved_layout
        if refresh:
            self._safe_update()
        return True

    def _sync_portrait_edit_from_controls(self, edit: PortraitEditDraft) -> None:
        if self._portrait_tolerance_slider is not None and self._portrait_tolerance_slider.value is not None:
            edit.tolerance = int(self._portrait_tolerance_slider.value)
        if self._portrait_feather_slider is not None and self._portrait_feather_slider.value is not None:
            edit.feather = int(self._portrait_feather_slider.value)
        if self._portrait_scale_slider is not None and self._portrait_scale_slider.value is not None:
            edit.scale = float(self._portrait_scale_slider.value)
        if self._portrait_offset_x_slider is not None:
            edit.offset_x = int(self._portrait_offset_x_slider.value or 0)
        if self._portrait_offset_y_slider is not None:
            edit.offset_y = int(self._portrait_offset_y_slider.value or 0)

    def _set_portrait_background(self, preset: str) -> None:
        edit = self._draft.portrait_edits.get(self._emotion_id)
        if edit is None or not edit.source_path:
            return
        try:
            edit.background_color = sample_background_color(edit.source_path, preset)
        except PortraitProcessingError as exc:
            self.show_notice(str(exc), is_error=True)
            return
        self._queue_portrait_preview()

    def _set_portrait_preset(self, preset_id: str) -> None:
        edit = self._draft.portrait_edits.get(self._emotion_id)
        if edit is None:
            return
        for candidate_id, _, tolerance, feather in PORTRAIT_CUTOUT_PRESETS:
            if candidate_id == preset_id:
                edit.tolerance = tolerance
                edit.feather = feather
                if self._portrait_tolerance_slider is not None:
                    self._portrait_tolerance_slider.value = tolerance
                    self._refresh_portrait_value_label("tolerance", "int", tolerance)
                if self._portrait_feather_slider is not None:
                    self._portrait_feather_slider.value = feather
                    self._refresh_portrait_value_label("feather", "int", feather)
                self._queue_portrait_preview()
                return

    def _portrait_preset_id(self, edit: PortraitEditDraft) -> str:
        for preset_id, _, tolerance, feather in PORTRAIT_CUTOUT_PRESETS:
            if edit.tolerance == tolerance and edit.feather == feather:
                return preset_id
        return ""

    def _toggle_portrait_advanced(self) -> None:
        self._portrait_advanced_open = not self._portrait_advanced_open
        self._safe_update()

    def _queue_portrait_preview(self, *, refresh_page: bool = True) -> None:
        edit = self._draft.portrait_edits.get(self._emotion_id)
        if edit is None:
            return
        emotion_id = self._emotion_id
        self._sync_portrait_edit_from_controls(edit)
        self._portrait_preview_generation += 1
        generation = self._portrait_preview_generation

        async def _render_later() -> None:
            await asyncio.sleep(PORTRAIT_PREVIEW_DEBOUNCE_SECONDS)
            if generation != self._portrait_preview_generation or self._emotion_id != emotion_id:
                return
            if refresh_page:
                self._portrait_rendering_emotion_id = emotion_id
                self._safe_update()
            processed = self._process_portrait(emotion_id, refresh=False, sync_controls=False, expected_generation=generation)
            if generation == self._portrait_preview_generation:
                self._portrait_rendering_emotion_id = ""
                if refresh_page:
                    self._safe_update()
                elif processed and not self._refresh_portrait_preview_control(emotion_id):
                    self._safe_update()

        try:
            page = self.page
        except RuntimeError:
            page = None
        if page is None:
            processed = self._process_portrait(emotion_id, refresh=refresh_page, sync_controls=False)
            if processed and not refresh_page:
                self._refresh_portrait_preview_control(emotion_id)
            return
        page.run_task(_render_later)

    def _portrait_preview_output_path(self, emotion_id: str) -> Path:
        safe_emotion = "".join(character for character in emotion_id if character.isalnum() or character in ("-", "_")) or "portrait"
        root = Path(tempfile.gettempdir()) / "amadues_portraits" / self._portrait_preview_session_id
        return root / f"{safe_emotion}-{self._portrait_preview_generation}.png"

    def _cleanup_portrait_preview_path(self, path: str, *, keep: str = "") -> None:
        if not path or path == keep:
            return
        try:
            preview_path = Path(path)
            session_root = Path(tempfile.gettempdir()) / "amadues_portraits" / self._portrait_preview_session_id
            if preview_path.is_file() and session_root in preview_path.parents:
                preview_path.unlink(missing_ok=True)
        except OSError:
            pass

    def _upload_create_avatar(self) -> None:
        self._open_image_picker("avatar")

    def _remove_create_avatar(self) -> None:
        self._draft.avatar_path = ""
        self._safe_update()

    def _add_trait(self) -> None:
        self._persist_current_step()
        value = (self._trait_field.value if self._trait_field else "").strip()
        if value and value not in self._draft.personality_traits:
            self._draft.personality_traits.append(value)
            if self._trait_field is not None:
                self._trait_field.value = ""
                self._try_update_control(self._trait_field)
            self._refresh_trait_chips()

    def _remove_trait(self, value: str) -> None:
        self._persist_current_step()
        self._draft.personality_traits = [item for item in self._draft.personality_traits if item != value]
        self._refresh_trait_chips()

    def _add_interest(self) -> None:
        self._persist_current_step()
        value = (self._interest_field.value if self._interest_field else "").strip()
        if value and value not in self._draft.interests:
            self._draft.interests.append(value)
            if self._interest_field is not None:
                self._interest_field.value = ""
                self._try_update_control(self._interest_field)
            self._refresh_interest_chips()

    def _remove_interest(self, value: str) -> None:
        self._persist_current_step()
        self._draft.interests = [item for item in self._draft.interests if item != value]
        self._refresh_interest_chips()

    def _add_memory(self) -> None:
        self._persist_current_step()
        self._draft.memories.append(MemoryDraft(content=""))
        self._refresh_memory_list()

    def _remove_memory(self, index: int) -> None:
        self._persist_current_step()
        if 0 <= index < len(self._draft.memories):
            del self._draft.memories[index]
        self._refresh_memory_list()

    def set_roles(self, roles: list[CompanionRole]) -> None:
        self._roles = roles
        if not roles:
            self._active_role_id = ""
        elif self._active_role_id not in [role.id for role in roles]:
            self._active_role_id = roles[0].id
        for role in self._roles:
            if any(message.role_id == role.id for message in self._messages):
                self._sync_role_recent_message(role.id)
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
        for role in self._roles:
            self._sync_role_recent_message(role.id)
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
        self._sync_role_recent_message(role_id)
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
        self._sync_role_recent_message(message.role_id)
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
        self._sync_role_recent_message(updated_message.role_id)
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
        self._refresh_chat_status()
        if self._page_name == "chat" and self._chat_mode == "normal":
            self._schedule_scroll_to_latest()
        if not self._refresh_chat_surface():
            self._safe_update()
            if self._page_name == "chat" and self._chat_mode == "normal":
                self._trigger_scroll_to_latest()

    def set_reply_emotion(self, role_id: str, emotion: str) -> None:
        normalized = self._normalize_emotion(emotion)
        if normalized:
            self._reply_emotions[role_id] = normalized
        if role_id == self._active_role_id and self._chat_mode == "immersive":
            self._refresh_chat_status()
            if not self._refresh_immersive_portrait():
                self._safe_update()
            return
        if role_id == self._active_role_id and not self._refresh_chat_status():
            self._safe_update()

    def apply_settings(self, settings: UiSettings) -> None:
        self._settings = settings
        self._is_dark = settings.is_dark
        self._profile.name = settings.user_name
        self._profile.avatar_path = settings.user_avatar_path
        self._safe_update()

    def go_back(self) -> bool:
        if self._page_name == "create" and self._create_step > 1:
            self._previous_step()
            return True
        while self._page_history:
            previous = self._page_history.pop()
            if previous in self.VALID_PAGES and previous != self._page_name:
                self.show_page(previous, add_to_history=False)
                return True
        if self._page_name != "home":
            self.show_page("home", add_to_history=False)
            return True
        return False

    def show_page(self, page: str, *, add_to_history: bool = True) -> None:
        if page not in self.VALID_PAGES:
            raise ValueError(f"Unknown page: {page}")
        current_page = self._page_name
        if add_to_history and page != "home" and current_page != page:
            if not self._page_history or self._page_history[-1] != current_page:
                self._page_history.append(current_page)
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
        self._sync_role_recent_message(active_role)
        if not self._refresh_chat_surface():
            self._safe_update()

    def show_notice(self, message: str, is_error: bool = False) -> None:
        try:
            snack_bar = ft.SnackBar(
                content=text(message, 13, "#FFFFFF"),
                bgcolor="#B42318" if is_error else self.active_role.accent_color,
            )
            page = self.page
            snack_bar.open = True
            show_dialog = getattr(page, "show_dialog", None)
            if callable(show_dialog):
                show_dialog(snack_bar)
            else:
                page.snack_bar = snack_bar
                page.update()
        except Exception:
            print(f"[ui] {'error' if is_error else 'notice'}: {message}")
