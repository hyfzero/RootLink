"""Flet UI package for the Amadues companion app."""

from .app import DemoCallback, main, run_app, run_demo
from .control import (
    AMADUES_BRAIN_ID,
    AMADUES_UI_ROLE_ID,
    DEEPSEEK_PROVIDER,
    DEEPSEEK_V4_FLASH_MODEL,
    DEEPSEEK_V4_PRO_MODEL,
    MINIMAX_MODEL,
    MINIMAX_PROVIDER,
    AmaduesController,
    ChatConfigurationError,
    UiSettingsStorage,
    build_amadues_runtime,
    ensure_default_startup_data,
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
from .views import CompanionAppView, default_roles

__all__ = [
    "AMADUES_BRAIN_ID",
    "AMADUES_UI_ROLE_ID",
    "DEEPSEEK_PROVIDER",
    "DEEPSEEK_V4_FLASH_MODEL",
    "DEEPSEEK_V4_PRO_MODEL",
    "MINIMAX_MODEL",
    "MINIMAX_PROVIDER",
    "AmaduesController",
    "CharacterDraft",
    "ChatConfigurationError",
    "ChatMessage",
    "CompanionAppView",
    "CompanionRole",
    "CompanionUICallback",
    "CompanionUIView",
    "DemoCallback",
    "MemoryDraft",
    "UiSettings",
    "UiSettingsStorage",
    "UserProfile",
    "build_amadues_runtime",
    "default_roles",
    "ensure_default_startup_data",
    "main",
    "run_app",
    "run_demo",
]
