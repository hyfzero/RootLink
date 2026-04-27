"""Public contracts for the mobile-first Flet companion UI."""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(slots=True)
class CompanionRole:
    """A companion role shown by the mobile UI."""

    id: str
    name: str
    type: str
    tags: list[str]
    intro: str
    status_text: str
    accent_color: str
    avatar_path: str
    standing_image_path: str
    portraits: dict[str, str] = field(default_factory=dict)
    last_message: str = ""
    last_time: str = ""


@dataclass(slots=True)
class ChatMessage:
    """A chat message rendered in normal chat mode."""

    id: str
    role_id: str
    text: str
    is_user: bool
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(slots=True)
class UserProfile:
    """User display information for the settings screen."""

    name: str = "用户"
    avatar_path: Optional[str] = None


@dataclass(slots=True)
class UiSettings:
    """Settings collected by the UI for the control layer."""

    is_dark: bool = True
    token_quality: int = 50
    model_provider: str = "minimax"
    api_key: str = ""
    user_name: str = "用户"
    user_avatar_path: Optional[str] = None


@dataclass(slots=True)
class MemoryDraft:
    """A memory row from the character creation wizard."""

    content: str
    memory_type: str = "episodic"
    importance: float = 1.0
    context: str = ""


@dataclass(slots=True)
class CharacterDraft:
    """Collected values from the character creation wizard."""

    brain_id: str = ""
    template: str = "default"
    name: str = ""
    description: str = ""
    portraits: dict[str, str] = field(default_factory=dict)
    age: str = ""
    gender: str = "unknown"
    birthday: str = ""
    personality_traits: list[str] = field(default_factory=list)
    interests: list[str] = field(default_factory=list)
    background: str = ""
    speaking_style_preset: str = "friendly"
    memories: list[MemoryDraft] = field(default_factory=list)
    vocabulary_level: str = "common"
    sentence_length: str = "medium"
    exclamation_rate: float = 0.3
    question_rate: float = 0.2
    ellipsis_rate: float = 0.1
    emoji_usage: str = "sparse"
    parenthesis_usage: str = "sparse"
    influence_weight: float = 0.8


class CompanionUICallback(ABC):
    """Callbacks invoked by the UI and implemented by the control layer."""

    def on_open_chat(self, role_id: str) -> None:
        pass

    def on_send_message(self, role_id: str, text: str, mode: str) -> None:
        pass

    def on_chat_mode_changed(self, mode: str) -> None:
        pass

    def on_settings_saved(self, settings: UiSettings) -> None:
        pass

    def on_character_create_requested(self, draft: CharacterDraft) -> None:
        pass

    def on_theme_toggled(self, is_dark: bool) -> None:
        pass

    def on_voice_requested(self) -> None:
        pass

    def on_avatar_upload_requested(self) -> None:
        pass

    def on_portrait_upload_requested(self, emotion_id: str) -> None:
        pass


class CompanionUIView(ABC):
    """Methods exposed by the UI for control-layer updates."""

    def set_roles(self, roles: list[CompanionRole]) -> None:
        raise NotImplementedError

    def set_active_role(self, role_id: str) -> None:
        raise NotImplementedError

    def set_messages(self, messages: list[ChatMessage]) -> None:
        raise NotImplementedError

    def set_role_messages(self, role_id: str, messages: list[ChatMessage]) -> None:
        raise NotImplementedError

    def append_message(self, message: ChatMessage) -> None:
        raise NotImplementedError

    def set_typing(self, visible: bool) -> None:
        raise NotImplementedError

    def apply_settings(self, settings: UiSettings) -> None:
        raise NotImplementedError

    def show_page(self, page: str) -> None:
        raise NotImplementedError

    def clear_chat(self) -> None:
        raise NotImplementedError
