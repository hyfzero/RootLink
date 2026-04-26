"""Thin control layer for wiring the Flet UI to the Amadues chat runtime."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agent_core.api import ChatAgent
from agent_core.api.adapter import APIProvider, ModelConfig
from agent_core.brain import (
    AgentConfig,
    MessageHistory,
    Persona,
    PersonaProfile,
    PromptBuilder,
    SpeakingStyleEngine,
    TagGenerator,
)
from agent_core.models import ModelsJsonConfig, ModelsStorage, ProviderConfig, get_model_catalog
from agent_core.session import BrainRegistry, PathResolver, SessionConfig, SessionManager
from agent_core.session.brain_registry import BrainComponents

from .interfaces import (
    CharacterDraft,
    ChatMessage,
    CompanionUICallback,
    CompanionUIView,
    UiSettings,
)


AMADUES_BRAIN_ID = "amadues"
AMADUES_UI_ROLE_ID = "amadeus"
MINIMAX_PROVIDER = "minimax"
MINIMAX_MODEL = "MiniMax-M2.5"
DEFAULT_ASSISTANT_NAME = "\u963f\u739b\u8fea\u65af"
CONFIG_NOTICE = "\u8bf7\u5148\u5728\u8bbe\u7f6e\u9875\u4fdd\u5b58 MiniMax API Key\u3002"


class ChatConfigurationError(RuntimeError):
    """Raised when the persisted chat configuration is incomplete."""


@dataclass(slots=True)
class AmaduesRuntime:
    """Cached runtime objects used by the control layer."""

    session_manager: SessionManager
    brain_registry: BrainRegistry


class UiSettingsStorage:
    """Persistence for UI-facing settings and chat provider configuration."""

    def __init__(self, config_dir: str | Path | None = None) -> None:
        resolved_dir = Path(config_dir) if config_dir is not None else PathResolver.get_config_dir()
        self.config_dir = Path(resolved_dir)
        self.ui_settings_file = self.config_dir / "ui_settings.json"
        self.models_storage = ModelsStorage(self.config_dir)

    def load_ui_settings(self) -> UiSettings:
        settings = UiSettings(model_provider=MINIMAX_PROVIDER)
        if self.ui_settings_file.exists():
            with open(self.ui_settings_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            settings = UiSettings(
                is_dark=data.get("is_dark", settings.is_dark),
                token_quality=int(data.get("token_quality", settings.token_quality)),
                model_provider=MINIMAX_PROVIDER,
                user_name=data.get("user_name", settings.user_name),
                user_avatar_path=data.get("user_avatar_path"),
            )

        chat_config = self.load_chat_config()
        provider_config = chat_config.providers.get(MINIMAX_PROVIDER)
        settings.model_provider = MINIMAX_PROVIDER
        settings.api_key = provider_config.api_key if provider_config else ""
        return settings

    def save_ui_settings(self, settings: UiSettings) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "is_dark": settings.is_dark,
            "token_quality": settings.token_quality,
            "model_provider": MINIMAX_PROVIDER,
            "user_name": settings.user_name,
            "user_avatar_path": settings.user_avatar_path,
        }
        with open(self.ui_settings_file, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def load_chat_config(self) -> ModelsJsonConfig:
        return self.models_storage.load()

    def save_minimax_config(self, api_key: str) -> None:
        config = self.models_storage.load()
        config.providers[MINIMAX_PROVIDER] = ProviderConfig(
            base_url="https://api.minimaxi.com/v1",
            api_key=api_key.strip(),
            api_type="anthropic-messages",
            auth_header=True,
        )
        config.default_provider = MINIMAX_PROVIDER
        config.default_model = MINIMAX_MODEL
        self.models_storage.save(config)


def _default_persona_profile() -> PersonaProfile:
    return PersonaProfile(
        name=DEFAULT_ASSISTANT_NAME,
        age=20,
        gender="unknown",
        personality_traits=["rational", "friendly", "smart"],
        background="A thoughtful AI companion focused on calm conversation.",
        speaking_style="friendly",
    )


def _load_model_config(config_dir: str | Path | None = None) -> ModelConfig:
    storage = ModelsStorage(config_dir)
    config = storage.load()
    provider_config = config.providers.get(MINIMAX_PROVIDER)
    if provider_config is None or not (provider_config.api_key or "").strip():
        raise ChatConfigurationError("MiniMax API key is not configured.")

    catalog = get_model_catalog(MINIMAX_PROVIDER)
    model_name = config.default_model or MINIMAX_MODEL
    model_info = catalog.find_model(model_name) if catalog else None
    return ModelConfig(
        name=model_name,
        provider=APIProvider.MINIMAX,
        api_key=provider_config.api_key,
        base_url=provider_config.base_url,
        max_tokens=model_info.max_tokens if model_info else 8192,
        temperature=0.7,
        supports_thinking=True,
        supports_function_calling=True,
        tokenizer_mode=model_info.tokenizer_mode if model_info else "auto",
        tokenizer_fallback=model_info.tokenizer_fallback if model_info else "hybrid_v1",
    )


def _ensure_default_amadues_data(brain_id: str = AMADUES_BRAIN_ID) -> Path:
    brain_dir = PathResolver.get_brain_dir(brain_id)
    persona_dir = brain_dir / "persona"
    history_dir = brain_dir / "history"

    persona_dir.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)

    profile_path = persona_dir / "profile.json"
    if not profile_path.exists():
        with open(profile_path, "w", encoding="utf-8") as handle:
            json.dump(_default_persona_profile().to_dict(), handle, ensure_ascii=False, indent=2)

    memories_path = persona_dir / "memories.json"
    if not memories_path.exists():
        with open(memories_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "episodic_memories": [
                        {
                            "content": "The user opened the chat for the first time.",
                            "memory_type": "episodic",
                            "importance": 1.0,
                        }
                    ],
                    "preference_memories": [],
                    "fact_memories": [],
                },
                handle,
                ensure_ascii=False,
                indent=2,
            )

    speaking_style_path = persona_dir / "speaking_style.json"
    if not speaking_style_path.exists():
        style = SpeakingStyleEngine(preset_name="gentle", influence_weight=0.5)
        with open(speaking_style_path, "w", encoding="utf-8") as handle:
            json.dump(style.to_dict(), handle, ensure_ascii=False, indent=2)

    return brain_dir


def _build_default_brain_components() -> BrainComponents:
    profile = _default_persona_profile()
    persona = Persona(profile)
    history = MessageHistory(
        max_context_tokens=4000,
        token_reserved=1000,
        retention_days=30,
    )
    style_engine = SpeakingStyleEngine(preset_name="gentle", influence_weight=0.5)
    config = AgentConfig()
    prompt_builder = PromptBuilder(
        persona=persona,
        history=history,
        style_engine=style_engine,
        config=config,
    )
    return BrainComponents(
        persona=persona,
        history=history,
        style_engine=style_engine,
        prompt_builder=prompt_builder,
        config=config,
    )


def build_amadues_runtime(
    config_dir: str | Path | None = None,
    brain_id: str = AMADUES_BRAIN_ID,
) -> AmaduesRuntime:
    model_config = _load_model_config(config_dir)
    chat_agent = ChatAgent(config=model_config)

    _ensure_default_amadues_data(brain_id)
    brain_registry = BrainRegistry(PathResolver.get_data_dir())
    brain_registry.load_all()

    if brain_id not in brain_registry.list_brains():
        brain_registry.register(brain_id, _build_default_brain_components())

    brain_registry.switch(brain_id)
    session_config = SessionConfig(
        model_config=model_config,
        max_messages_per_day=500,
        max_tokens_per_day=50000,
        min_messages_for_summary=4,
    )
    session_manager = SessionManager(
        config=session_config,
        brain_registry=brain_registry,
        chat_agent=chat_agent,
        tag_generator=TagGenerator(),
    )
    session_manager.set_emotion_mode("keyword")
    session_manager.storage.get_or_create_today()
    return AmaduesRuntime(session_manager=session_manager, brain_registry=brain_registry)


class AmaduesController(CompanionUICallback):
    """Control layer that binds the Flet UI to the Amadues chat runtime."""

    def __init__(
        self,
        view: Optional[CompanionUIView] = None,
        settings_storage: Optional[UiSettingsStorage] = None,
        runtime_factory: Optional[Callable[[], AmaduesRuntime]] = None,
    ) -> None:
        self.view = view
        self.settings_storage = settings_storage or UiSettingsStorage()
        if runtime_factory is None:
            self._runtime_factory = lambda: build_amadues_runtime(
                config_dir=self.settings_storage.config_dir
            )
        else:
            self._runtime_factory = runtime_factory
        self._runtime: Optional[AmaduesRuntime] = None
        self._settings = self.settings_storage.load_ui_settings()
        self._role_mapping = {AMADUES_UI_ROLE_ID: AMADUES_BRAIN_ID}

    @property
    def initial_settings(self) -> UiSettings:
        return self._settings

    def bind_view(self, view: CompanionUIView) -> None:
        self.view = view
        self.view.apply_settings(self._settings)

    def _invalidate_runtime(self) -> None:
        self._runtime = None

    def _get_runtime(self) -> AmaduesRuntime:
        if self._runtime is None:
            self._runtime = self._runtime_factory()
        return self._runtime

    def _is_amadues_role(self, role_id: str) -> bool:
        return self._role_mapping.get(role_id) == AMADUES_BRAIN_ID

    def _message_from_storage(self, role_id: str, raw_message: object) -> ChatMessage:
        raw_role = getattr(raw_message, "role", None)
        is_user = getattr(raw_role, "value", raw_role) == "user"
        timestamp = getattr(raw_message, "timestamp", None)
        dt_value = datetime.fromtimestamp(float(timestamp)) if timestamp is not None else datetime.now()
        return ChatMessage(
            id=str(getattr(raw_message, "id", f"session-{dt_value.timestamp()}")),
            role_id=role_id,
            text=str(getattr(raw_message, "content", "")),
            is_user=is_user,
            timestamp=dt_value,
        )

    def _load_today_messages(self, role_id: str, runtime: AmaduesRuntime) -> list[ChatMessage]:
        return [
            self._message_from_storage(role_id, message)
            for message in runtime.session_manager.storage.get_today_messages()
        ]

    def _notice(self, role_id: str, text: str) -> ChatMessage:
        return ChatMessage(
            id=f"notice-{int(datetime.now().timestamp() * 1000)}",
            role_id=role_id,
            text=text,
            is_user=False,
            timestamp=datetime.now(),
        )

    def _replace_role_messages(self, role_id: str, messages: list[ChatMessage]) -> None:
        if self.view is None:
            return
        replace_method = getattr(self.view, "set_role_messages", None)
        if callable(replace_method):
            replace_method(role_id, messages)
            return
        self.view.set_messages(messages)

    def on_open_chat(self, role_id: str) -> None:
        if not self._is_amadues_role(role_id):
            print(f"[ui] open chat demo: {role_id}")
            return

        try:
            runtime = self._get_runtime()
            messages = self._load_today_messages(role_id, runtime)
            self._replace_role_messages(role_id, messages)
        except ChatConfigurationError:
            self._replace_role_messages(
                role_id,
                [self._notice(role_id, f"MiniMax \u5c1a\u672a\u914d\u7f6e\u3002{CONFIG_NOTICE}")],
            )
        except Exception as exc:
            self._replace_role_messages(
                role_id,
                [self._notice(role_id, f"\u804a\u5929\u521d\u59cb\u5316\u5931\u8d25\uff1a{exc}")],
            )

    def on_send_message(self, role_id: str, text: str, mode: str) -> None:
        if self.view is None:
            return

        if not self._is_amadues_role(role_id):
            self.view.append_message(
                ChatMessage(
                    id=f"demo-{datetime.now().timestamp()}",
                    role_id=role_id,
                    text="\u5f53\u524d\u53ea\u6709 Amadeus \u63a5\u5165\u4e86\u771f\u5b9e\u804a\u5929\uff0c\u5176\u4ed6\u89d2\u8272\u4ecd\u4fdd\u6301 demo \u6a21\u5f0f\u3002",
                    is_user=False,
                    timestamp=datetime.now(),
                )
            )
            return

        self.view.set_typing(True)
        try:
            runtime = self._get_runtime()
            result = runtime.session_manager.send_message_sync(user_message=text, emotion=None)
            self.view.append_message(
                ChatMessage(
                    id=str(result.get("message_id", f"assistant-{datetime.now().timestamp()}")),
                    role_id=role_id,
                    text=str(result.get("content", "")),
                    is_user=False,
                    timestamp=datetime.now(),
                )
            )
        except ChatConfigurationError:
            self.view.append_message(
                self._notice(role_id, f"MiniMax \u5c1a\u672a\u914d\u7f6e\u3002{CONFIG_NOTICE}")
            )
        except Exception as exc:
            self.view.append_message(self._notice(role_id, f"\u6d88\u606f\u53d1\u9001\u5931\u8d25\uff1a{exc}"))
        finally:
            self.view.set_typing(False)

    def on_chat_mode_changed(self, mode: str) -> None:
        print(f"[ui] chat mode: {mode}")

    def on_settings_saved(self, settings: UiSettings) -> None:
        settings.model_provider = MINIMAX_PROVIDER
        self.settings_storage.save_minimax_config(settings.api_key)
        self.settings_storage.save_ui_settings(settings)
        self._settings = self.settings_storage.load_ui_settings()
        self._invalidate_runtime()
        if self.view is not None:
            self.view.apply_settings(self._settings)

    def on_character_create_requested(self, draft: CharacterDraft) -> None:
        print(f"[ui] create character demo: id={draft.brain_id} name={draft.name}")

    def on_theme_toggled(self, is_dark: bool) -> None:
        self._settings.is_dark = is_dark

    def on_voice_requested(self) -> None:
        print("[ui] voice requested")

    def on_avatar_upload_requested(self) -> None:
        print("[ui] avatar upload requested")

    def on_portrait_upload_requested(self, emotion_id: str) -> None:
        print(f"[ui] portrait upload requested: {emotion_id}")
