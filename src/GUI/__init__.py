"""ChatUI - Flet-based Galgame-style Chat Interface."""

from .main_view import MainView, ChatUIApp, DummyCallback
from .chat_view import ChatView
from .sidebar_view import SidebarView
from .components import (
    CharacterSprite,
    SpeechBubble,
    UserBubble,
    ChatInput,
    SettingsPanel,
)
from .interfaces import (
    IChatViewCallback,
    IChatViewProvider,
    ChatMessage,
    Character,
    ChatSettings,
)

__version__ = "0.1.0"

__all__ = [
    # Main views
    "MainView",
    "ChatUIApp",
    "ChatView",
    "SidebarView",
    # Components
    "CharacterSprite",
    "SpeechBubble",
    "UserBubble",
    "ChatInput",
    "SettingsPanel",
    # Interfaces
    "IChatViewCallback",
    "IChatViewProvider",
    "ChatMessage",
    "Character",
    "ChatSettings",
    # Utilities
    "DummyCallback",
]
