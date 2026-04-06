"""Interface definitions for Control layer callbacks."""

from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ChatMessage:
    """Represents a chat message."""
    id: str
    text: str
    is_user: bool
    timestamp: datetime
    character_id: Optional[str] = None


@dataclass
class Character:
    """Represents a character with sprite and avatar."""
    id: str
    name: str
    sprite_path: str
    avatar_path: str


@dataclass
class ChatSettings:
    """Chat application settings."""
    theme: str = "dark"
    text_speed: int = 30
    auto_scroll: bool = True


class IChatViewCallback(ABC):
    """
    Interface that UI layer uses to communicate with Control layer.
    Control layer implements these callbacks.
    """

    @abstractmethod
    def on_message_send(self, text: str) -> None:
        """Called when user sends a message."""
        pass

    @abstractmethod
    def on_settings_changed(self, settings: ChatSettings) -> None:
        """Called when user changes settings."""
        pass

    @abstractmethod
    def on_theme_toggle(self) -> None:
        """Called when user toggles theme."""
        pass

    @abstractmethod
    def on_sidebar_toggle(self) -> None:
        """Called when user toggles sidebar visibility."""
        pass

    @abstractmethod
    def on_chat_history_select(self, chat_id: str) -> None:
        """Called when user selects a chat history item."""
        pass

    @abstractmethod
    def on_sprite_tapped(self) -> None:
        """Called when user taps character sprite."""
        pass


class IChatViewProvider(ABC):
    """
    Interface that Control layer uses to communicate with UI layer.
    UI layer implements these methods.
    """

    @abstractmethod
    def append_message(self, message: ChatMessage) -> None:
        """Add a new message to the chat view."""
        pass

    @abstractmethod
    def update_character(self, character: Character) -> None:
        """Update the displayed character sprite."""
        pass

    @abstractmethod
    def set_typing_indicator(self, visible: bool) -> None:
        """Show or hide typing indicator."""
        pass

    @abstractmethod
    def clear_chat(self) -> None:
        """Clear all messages from chat view."""
        pass

    @abstractmethod
    def set_sidebar_visible(self, visible: bool) -> None:
        """Show or hide sidebar."""
        pass

    @abstractmethod
    def apply_settings(self, settings: ChatSettings) -> None:
        """Apply settings to UI."""
        pass
