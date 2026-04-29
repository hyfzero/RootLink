"""Thin control layer for wiring the Flet UI to the Amadues chat runtime."""

from __future__ import annotations

import json
import shutil
import sys
import threading
import time
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
    PersonaProfile,
    SpeakingStyleEngine,
    TagGenerator,
)
from agent_core.models import ModelsJsonConfig, ModelsStorage, ProviderConfig, get_model_catalog
from agent_core.session import BrainRegistry, PathResolver, SessionConfig, SessionManager

from .chat_text import (
    NORMAL_SENTENCE_DELAY_SECONDS,
    consume_complete_sentence,
    split_display_sentences,
)
from .interfaces import (
    CharacterDraft,
    ChatMessage,
    CompanionRole,
    CompanionUICallback,
    CompanionUIView,
    UiSettings,
)
from .role_loader import load_roles_from_data, load_roles_from_registry


AMADUES_BRAIN_ID = "amadues"
AMADUES_UI_ROLE_ID = AMADUES_BRAIN_ID
SHINJI_BRAIN_ID = "shinji"
MINIMAX_PROVIDER = "minimax"
MINIMAX_MODEL = "MiniMax-M2.5"
DEFAULT_ASSISTANT_NAME = "\u963f\u739b\u8fea\u65af"
CONFIG_NOTICE = "\u8bf7\u5148\u5728\u8bbe\u7f6e\u9875\u4fdd\u5b58 MiniMax API Key\u3002"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESOURCE_DIR = PROJECT_ROOT / "resource"
DEFAULT_RESPONSE_LIMITS = {"max_tokens": 2000, "max_sentences": 5}


class ChatConfigurationError(RuntimeError):
    """Raised when the persisted chat configuration is incomplete."""


class _NormalMessageStreamer:
    """Buffers assistant deltas into sentence-sized UI bubbles."""

    def __init__(
        self,
        view: CompanionUIView,
        role_id: str,
        base_id: str,
        sentence_delay: float = NORMAL_SENTENCE_DELAY_SECONDS,
    ) -> None:
        self._view = view
        self._role_id = role_id
        self._base_id = base_id
        self._pending = ""
        self._index = 0
        self._current_id: str | None = None
        self._sentence_delay = sentence_delay
        self._has_emitted_sentence = False

    def push(self, delta: str) -> None:
        if not delta:
            return
        self._pending += delta
        if self._current_id is None:
            self._pending = self._pending.lstrip()
        if not self._pending.strip():
            return

        while self._pending:
            sentence, rest = consume_complete_sentence(self._pending)
            if sentence is None:
                self._show_current(self._pending, is_streaming=True)
                break
            self._show_current(sentence, is_streaming=False)
            self._pending = rest
            self._current_id = None
            self._index += 1
            self._has_emitted_sentence = True
            if self._pending.strip():
                time.sleep(self._sentence_delay)
            else:
                self._pending = ""
                break

    def finish(self, content: str | None = None) -> None:
        if content and not self._current_id and not self._pending:
            for sentence in split_display_sentences(content):
                self._pace_after_previous_sentence()
                self._show_current(sentence, is_streaming=False)
                self._current_id = None
                self._index += 1
                self._has_emitted_sentence = True
            return
        if self._current_id is not None:
            final_text = self._pending.strip()
            if final_text:
                self._view.update_message_text(self._current_id, final_text, is_streaming=False)
            self._current_id = None
            self._pending = ""

    def _pace_after_previous_sentence(self) -> None:
        if self._has_emitted_sentence:
            time.sleep(self._sentence_delay)

    def _show_current(self, text: str, is_streaming: bool) -> None:
        visible_text = text.strip()
        if not visible_text:
            return
        if self._current_id is not None:
            self._view.update_message_text(self._current_id, visible_text, is_streaming=is_streaming)
            return
        message_id = f"{self._base_id}-{self._index}"
        self._current_id = message_id
        self._view.append_message(
            ChatMessage(
                id=message_id,
                role_id=self._role_id,
                text=visible_text,
                is_user=False,
                timestamp=datetime.now(),
                is_streaming=is_streaming,
            )
        )


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


def _write_json_if_missing(path: Path, payload: dict) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _ensure_response_config(path: Path, response_limits: dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            payload = loaded
    if isinstance(payload.get("response"), dict):
        return
    payload["response"] = response_limits
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _copy_asset_if_missing(source: Path, target: Path) -> None:
    if source.exists() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


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
    assets_dir = brain_dir / "assets"
    portraits_dir = assets_dir / "portraits"

    persona_dir.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    portraits_dir.mkdir(parents=True, exist_ok=True)

    _write_json_if_missing(persona_dir / "profile.json", _default_persona_profile().to_dict())
    _ensure_response_config(brain_dir / "config.json", DEFAULT_RESPONSE_LIMITS)
    _write_json_if_missing(
        persona_dir / "memories.json",
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
    )

    speaking_style_path = persona_dir / "speaking_style.json"
    if not speaking_style_path.exists():
        style = SpeakingStyleEngine(preset_name="gentle", influence_weight=0.5)
        _write_json_if_missing(speaking_style_path, style.to_dict())

    _write_json_if_missing(
        brain_dir / "ui.json",
        {
            "type": "\u7406\u6027\u8bb0\u5fc6\u578b",
            "tags": ["\u7406\u6027", "\u514b\u5236", "\u806a\u660e"],
            "intro": "\u50cf\u4ece\u8bb0\u5fc6\u6df1\u5904\u88ab\u91cd\u65b0\u5524\u9192\u7684\u5979\uff0c\u51b7\u9759\u3001\u51c6\u786e\uff0c\u4e5f\u5e26\u7740\u4e00\u70b9\u65e0\u6cd5\u89e6\u78b0\u7684\u8ddd\u79bb\u611f\u3002",
            "status_text": "\u8bb0\u5f97\u4f60\u4e0a\u6b21\u505c\u4e0b\u6765\u7684\u5730\u65b9\u3002",
            "accent_color": "#B6A8C9",
            "avatar": "assets/avatar.png",
            "portraits": {"neutral": "assets/portraits/neutral.png"},
            "last_message": "\u4eca\u5929\u5b9e\u9a8c\u8fdb\u5c55\u5982\u4f55\uff1f",
            "last_time": "",
        },
    )

    asset_pairs = (
        (RESOURCE_DIR / "amadues.png", assets_dir / "avatar.png"),
        (RESOURCE_DIR / "amadues_Full_profile.png", portraits_dir / "neutral.png"),
    )
    for source, target in asset_pairs:
        _copy_asset_if_missing(source, target)

    return brain_dir


def _ensure_default_shinji_data(brain_id: str = SHINJI_BRAIN_ID) -> Path:
    brain_dir = PathResolver.get_brain_dir(brain_id)
    persona_dir = brain_dir / "persona"
    history_dir = brain_dir / "history"
    assets_dir = brain_dir / "assets"
    portraits_dir = assets_dir / "portraits"

    persona_dir.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    portraits_dir.mkdir(parents=True, exist_ok=True)

    _write_json_if_missing(
        persona_dir / "profile.json",
        {
            "name": "碇真嗣",
            "age": 14,
            "gender": "male",
            "personality_traits": [
                "敏感",
                "内向",
                "谨慎",
                "共情力强",
                "不擅表达",
                "害怕被拒绝",
                "渴望被理解",
            ],
            "background": "第三新东京市的 EVA 驾驶员。习惯把真实想法压低，不主动打扰别人，也不擅长直接说出自己的需要。面对压力时容易退缩，但仍会认真倾听他人的话，并试着用温和、笨拙的方式回应。",
            "speaking_style": "gentle",
            "birthday": "6月6日",
            "interests": ["听音乐", "拉大提琴", "安静的地方", "被需要的感觉"],
            "relationship_state": "neutral",
            "relationship_score": 0.0,
            "relationship_updated_at": None,
        },
    )
    _ensure_response_config(brain_dir / "config.json", DEFAULT_RESPONSE_LIMITS)
    _write_json_if_missing(
        persona_dir / "memories.json",
        {
            "episodic_memories": [],
            "preference_memories": [],
            "fact_memories": [
                {
                    "content": "碇真嗣习惯先倾听，再用简短、谨慎的话回应。",
                    "memory_type": "fact",
                    "importance": 1.0,
                },
                {
                    "content": "碇真嗣在压力下容易退缩，但并不冷漠。",
                    "memory_type": "fact",
                    "importance": 1.0,
                },
            ],
        },
    )
    speaking_style_path = persona_dir / "speaking_style.json"
    if not speaking_style_path.exists():
        style = SpeakingStyleEngine(preset_name="gentle", influence_weight=0.45)
        _write_json_if_missing(speaking_style_path, style.to_dict())

    _write_json_if_missing(
        brain_dir / "ui.json",
        {
            "type": "内向倾听型",
            "tags": ["敏感", "克制", "共情"],
            "intro": "不太会热闹地安慰你，但会认真听你说完。",
            "status_text": "会安静地等你说下去。",
            "accent_color": "#AEB8C7",
            "avatar": "assets/avatar.png",
            "portraits": {"neutral": "assets/portraits/neutral.png"},
            "last_message": "嗯...我明白那种感觉。",
            "last_time": "",
        },
    )

    asset_pairs = (
        (RESOURCE_DIR / "Shinji.png", assets_dir / "avatar.png"),
        (RESOURCE_DIR / "Shinji_Ikari_full_profile.png", portraits_dir / "neutral.png"),
    )
    for source, target in asset_pairs:
        _copy_asset_if_missing(source, target)

    return brain_dir


def build_amadues_runtime(
    config_dir: str | Path | None = None,
    brain_id: str = AMADUES_BRAIN_ID,
) -> AmaduesRuntime:
    model_config = _load_model_config(config_dir)
    chat_agent = ChatAgent(config=model_config)

    brain_registry = BrainRegistry(PathResolver.get_data_dir())
    brain_registry.load_all()

    loaded_brains = brain_registry.list_brains()
    if not loaded_brains:
        raise RuntimeError("No brains found in the data directory.")

    selected_brain_id = brain_id if brain_id in loaded_brains else loaded_brains[0]
    brain_registry.switch(selected_brain_id)
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
        normal_sentence_delay: float = NORMAL_SENTENCE_DELAY_SECONDS,
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
        self._role_mapping: dict[str, str] = {}
        self._stream_threads: list[threading.Thread] = []
        self._normal_sentence_delay = normal_sentence_delay

    @property
    def initial_settings(self) -> UiSettings:
        return self._settings

    def bind_view(self, view: CompanionUIView) -> None:
        self.view = view
        self.view.apply_settings(self._settings)
        self._publish_data_roles()

    def _invalidate_runtime(self) -> None:
        self._runtime = None

    def _get_runtime(self) -> AmaduesRuntime:
        if self._runtime is None:
            self._runtime = self._runtime_factory()
            self._publish_runtime_roles(self._runtime)
        return self._runtime

    def _remember_roles(self, roles: list[CompanionRole]) -> None:
        for role in roles:
            self._role_mapping[role.id] = role.id

    def _publish_data_roles(self) -> None:
        if self.view is None:
            return
        roles = load_roles_from_data()
        self._remember_roles(roles)
        self.view.set_roles(roles)

    def _publish_runtime_roles(self, runtime: AmaduesRuntime) -> None:
        if self.view is None:
            return
        if not callable(getattr(runtime.brain_registry, "list_brains", None)):
            return
        roles = load_roles_from_registry(runtime.brain_registry, PathResolver.get_data_dir())
        self._remember_roles(roles)
        self.view.set_roles(roles)

    def _resolve_brain_id(self, role_id: str, runtime: Optional[AmaduesRuntime] = None) -> str:
        mapped_id = self._role_mapping.get(role_id, role_id)
        registry = getattr(runtime, "brain_registry", None) if runtime is not None else None
        list_brains = getattr(registry, "list_brains", None)
        if callable(list_brains):
            brain_ids = set(list_brains())
            if mapped_id in brain_ids:
                return mapped_id
            if role_id in brain_ids:
                return role_id
        return mapped_id

    def _select_role_runtime(self, role_id: str, runtime: AmaduesRuntime) -> str:
        brain_id = self._resolve_brain_id(role_id, runtime)
        registry = getattr(runtime, "brain_registry", None)
        list_brains = getattr(registry, "list_brains", None)
        if callable(list_brains) and brain_id not in set(list_brains()):
            raise KeyError(f"Brain '{brain_id}' not found")

        current_brain_id = None
        current_method = getattr(registry, "current_brain_id", None)
        if callable(current_method):
            current_brain_id = current_method()

        if current_brain_id != brain_id:
            switch_brain = getattr(runtime.session_manager, "switch_brain", None)
            if callable(switch_brain):
                switch_brain(brain_id)
        return brain_id

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
        try:
            runtime = self._get_runtime()
            self._select_role_runtime(role_id, runtime)
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

        self.view.set_typing(True)
        thread = threading.Thread(
            target=self._send_message_worker,
            args=(role_id, text, mode),
            daemon=True,
        )
        self._stream_threads.append(thread)
        thread.start()

    def wait_for_streams(self, timeout: float | None = None) -> None:
        """Wait for active message workers; used by tests and diagnostics."""
        for thread in list(self._stream_threads):
            thread.join(timeout=timeout)
            if not thread.is_alive():
                self._stream_threads.remove(thread)

    def _send_message_worker(self, role_id: str, text: str, mode: str) -> None:
        if self.view is None:
            return
        assistant_id = f"assistant-{datetime.now().timestamp()}"
        normal_streamer: _NormalMessageStreamer | None = None
        immersive_started = False
        accumulated = ""
        try:
            runtime = self._get_runtime()
            self._select_role_runtime(role_id, runtime)
            stream_method = getattr(runtime.session_manager, "send_message_stream", None)
            if not callable(stream_method):
                result = runtime.session_manager.send_message_sync(user_message=text, emotion=None)
                self._append_finished_reply(role_id, mode, assistant_id, str(result.get("content", "")))
                return

            if mode == "normal":
                normal_streamer = _NormalMessageStreamer(
                    self.view,
                    role_id,
                    assistant_id,
                    sentence_delay=self._normal_sentence_delay,
                )
            else:
                self.view.append_message(
                    ChatMessage(
                        id=assistant_id,
                        role_id=role_id,
                        text="",
                        is_user=False,
                        timestamp=datetime.now(),
                        is_streaming=True,
                    )
                )
                immersive_started = True

            for event in stream_method(user_message=text, emotion=None):
                event_type = event.get("type")
                if event_type == "delta":
                    delta = str(event.get("delta", ""))
                    if not delta:
                        continue
                    accumulated += delta
                    if normal_streamer is not None:
                        normal_streamer.push(delta)
                    else:
                        self.view.update_message_text(assistant_id, accumulated, is_streaming=True)
                elif event_type == "done":
                    content = str(event.get("content", accumulated))
                    if normal_streamer is not None:
                        normal_streamer.finish(content if not accumulated else None)
                    else:
                        self.view.update_message_text(assistant_id, content, is_streaming=False)
                    return
                elif event_type == "error":
                    raise RuntimeError(str(event.get("error", "unknown streaming error")))
        except ChatConfigurationError:
            self.view.append_message(
                self._notice(role_id, f"MiniMax \u5c1a\u672a\u914d\u7f6e\u3002{CONFIG_NOTICE}")
            )
        except Exception as exc:
            self.view.append_message(self._notice(role_id, f"\u6d88\u606f\u53d1\u9001\u5931\u8d25\uff1a{exc}"))
        finally:
            if normal_streamer is not None:
                normal_streamer.finish()
            elif immersive_started:
                self.view.update_message_text(assistant_id, accumulated, is_streaming=False)
            self.view.set_typing(False)

    def _append_finished_reply(self, role_id: str, mode: str, assistant_id: str, content: str) -> None:
        if self.view is None:
            return
        if mode == "normal":
            for index, sentence in enumerate(split_display_sentences(content) or [content]):
                self.view.append_message(
                    ChatMessage(
                        id=f"{assistant_id}-{index}",
                        role_id=role_id,
                        text=sentence,
                        is_user=False,
                        timestamp=datetime.now(),
                    )
                )
            return
        self.view.append_message(
            ChatMessage(
                id=assistant_id,
                role_id=role_id,
                text=content,
                is_user=False,
                timestamp=datetime.now(),
            )
        )

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
