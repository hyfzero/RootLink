"""Thin control layer for wiring the Flet UI to the Amadues chat runtime."""

from __future__ import annotations

import json
import os
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
    NORMAL_CHARACTER_DELAY_SECONDS,
    NORMAL_SENTENCE_DELAY_SECONDS,
    consume_complete_sentence,
    split_display_sentences,
)
from .character_package import CharacterPackageError, export_character_package, import_character_package
from .character_creator import PORTRAIT_EDIT_FILE, PORTRAIT_EDIT_VERSION, VALID_BRAIN_ID, CharacterCreationError, CharacterCreator
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
KEY_BRAIN_ID = "key"
SHINJI_BRAIN_ID = "shinji"
MINIMAX_PROVIDER = "minimax"
MINIMAX_MODEL = "MiniMax-M2.5"
DEEPSEEK_PROVIDER = "deepseek"
DEEPSEEK_V4_FLASH_MODEL = "deepseek-v4-flash"
DEEPSEEK_V4_PRO_MODEL = "deepseek-v4-pro"
DEFAULT_MODEL_BY_PROVIDER = {
    MINIMAX_PROVIDER: MINIMAX_MODEL,
    DEEPSEEK_PROVIDER: DEEPSEEK_V4_FLASH_MODEL,
}
PROVIDER_BASE_URLS = {
    MINIMAX_PROVIDER: "https://api.minimaxi.com/v1",
    DEEPSEEK_PROVIDER: "https://api.deepseek.com",
}
PROVIDER_API_TYPES = {
    MINIMAX_PROVIDER: "openai",
    DEEPSEEK_PROVIDER: "openai",
}
PROVIDER_API_ENUMS = {
    MINIMAX_PROVIDER: APIProvider.MINIMAX,
    DEEPSEEK_PROVIDER: APIProvider.DEEPSEEK,
}
DEFAULT_ASSISTANT_NAME = "Amadues"
CONFIG_NOTICE = "\u8bf7\u5148\u5728\u8bbe\u7f6e\u9875\u4fdd\u5b58 API Key\u3002"
MISSING_API_KEY_NOTICE = f"API Key \u5c1a\u672a\u914d\u7f6e\u3002{CONFIG_NOTICE}"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESOURCE_DIR = PROJECT_ROOT / "resource"
DEFAULT_RESPONSE_LIMITS = {"max_tokens": 2000, "max_sentences": 5}
DEFAULT_KEY_SOURCE_ENV = "AMADUES_DEFAULT_KEY_SOURCE_DIR"


class ChatConfigurationError(RuntimeError):
    """Raised when the persisted chat configuration is incomplete."""


def _normalize_model_provider(provider_name: str) -> str:
    provider_name = (provider_name or "").strip().lower()
    if provider_name in DEFAULT_MODEL_BY_PROVIDER:
        return provider_name
    return MINIMAX_PROVIDER


def _normalize_model_name(provider_name: str, model_name: str) -> str:
    provider_name = _normalize_model_provider(provider_name)
    model_name = (model_name or "").strip()
    catalog = get_model_catalog(provider_name)
    if catalog and catalog.find_model(model_name):
        return model_name
    return DEFAULT_MODEL_BY_PROVIDER[provider_name]


def _provider_display_name(provider_name: str) -> str:
    return {
        MINIMAX_PROVIDER: "MiniMax",
        DEEPSEEK_PROVIDER: "DeepSeek",
    }.get(provider_name, provider_name)


class _NormalMessageStreamer:
    """Buffers assistant deltas into sentence-sized UI bubbles."""

    def __init__(
        self,
        view: CompanionUIView,
        role_id: str,
        base_id: str,
        sentence_delay: float = NORMAL_SENTENCE_DELAY_SECONDS,
        character_delay: float = NORMAL_CHARACTER_DELAY_SECONDS,
    ) -> None:
        self._view = view
        self._role_id = role_id
        self._base_id = base_id
        self._pending = ""
        self._index = 0
        self._current_id: str | None = None
        self._current_text = ""
        self._sentence_delay = sentence_delay
        self._character_delay = character_delay
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
            self._current_text = ""
            self._index += 1
            self._has_emitted_sentence = True
            if self._pending.strip():
                continue
            else:
                self._pending = ""
                break

    def finish(self, content: str | None = None) -> None:
        if content and not self._current_id and not self._pending:
            for sentence in split_display_sentences(content):
                self._show_current(sentence, is_streaming=False)
                self._current_id = None
                self._current_text = ""
                self._index += 1
                self._has_emitted_sentence = True
            return
        if self._current_id is not None:
            final_text = self._pending.strip()
            if final_text:
                self._show_current(final_text, is_streaming=False)
            self._current_id = None
            self._current_text = ""
            self._pending = ""

    def _pace_after_previous_sentence(self) -> None:
        if self._has_emitted_sentence:
            time.sleep(self._sentence_delay)

    def _show_current(self, text: str, is_streaming: bool) -> None:
        visible_text = text.strip()
        if not visible_text:
            return
        if self._current_id is not None:
            self._reveal_current_text(visible_text, is_streaming=is_streaming)
            return
        self._pace_after_previous_sentence()
        message_id = f"{self._base_id}-{self._index}"
        self._current_id = message_id
        initial_text = visible_text[:1]
        self._current_text = initial_text
        self._view.append_message(
            ChatMessage(
                id=message_id,
                role_id=self._role_id,
                text=initial_text,
                is_user=False,
                timestamp=datetime.now(),
                is_streaming=is_streaming or initial_text != visible_text,
            )
        )
        self._reveal_current_text(visible_text, is_streaming=is_streaming)

    def _reveal_current_text(self, visible_text: str, is_streaming: bool) -> None:
        if self._current_id is None:
            return
        if visible_text == self._current_text:
            self._view.update_message_text(self._current_id, visible_text, is_streaming=is_streaming)
            return
        if not visible_text.startswith(self._current_text):
            self._current_text = visible_text
            self._view.update_message_text(self._current_id, visible_text, is_streaming=is_streaming)
            return

        for index in range(len(self._current_text) + 1, len(visible_text) + 1):
            self._sleep_character_delay()
            partial_text = visible_text[:index]
            self._current_text = partial_text
            self._view.update_message_text(
                self._current_id,
                partial_text,
                is_streaming=is_streaming or partial_text != visible_text,
            )

    def _sleep_character_delay(self) -> None:
        if self._character_delay > 0:
            time.sleep(self._character_delay)


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
        data: dict[str, object] = {}
        chat_config = self.load_chat_config()
        if self.ui_settings_file.exists():
            with open(self.ui_settings_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)

        provider_name = _normalize_model_provider(
            str(data.get("model_provider") or chat_config.default_provider or MINIMAX_PROVIDER)
        )
        model_name = data.get("model_name")
        if not model_name and chat_config.default_provider == provider_name:
            model_name = chat_config.default_model
        model_name = _normalize_model_name(provider_name, str(model_name or ""))

        settings = UiSettings(
            is_dark=bool(data.get("is_dark", True)),
            token_quality=int(data.get("token_quality", 50)),
            model_provider=provider_name,
            model_name=model_name,
            user_name=str(data.get("user_name", UiSettings().user_name)),
            user_avatar_path=data.get("user_avatar_path") if isinstance(data.get("user_avatar_path"), str) else None,
        )
        provider_config = chat_config.providers.get(provider_name)
        settings.api_key = provider_config.api_key if provider_config else ""
        return settings

    def save_ui_settings(self, settings: UiSettings) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        provider_name = _normalize_model_provider(settings.model_provider)
        model_name = _normalize_model_name(provider_name, settings.model_name)
        payload = {
            "is_dark": settings.is_dark,
            "token_quality": settings.token_quality,
            "model_provider": provider_name,
            "model_name": model_name,
            "user_name": settings.user_name,
            "user_avatar_path": settings.user_avatar_path,
        }
        with open(self.ui_settings_file, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def load_chat_config(self) -> ModelsJsonConfig:
        return self.models_storage.load()

    def save_minimax_config(self, api_key: str) -> None:
        self.save_provider_config(MINIMAX_PROVIDER, api_key, MINIMAX_MODEL)

    def save_provider_config(self, provider_name: str, api_key: str, model_name: str | None = None) -> None:
        provider_name = _normalize_model_provider(provider_name)
        model_name = _normalize_model_name(provider_name, model_name or "")
        config = self.models_storage.load()
        config.providers[provider_name] = ProviderConfig(
            base_url=PROVIDER_BASE_URLS[provider_name],
            api_key=api_key.strip(),
            api_type=PROVIDER_API_TYPES[provider_name],
            auth_header=True,
        )
        config.default_provider = provider_name
        config.default_model = model_name
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


def _copy_missing_tree(source: Path, target: Path, *, overwrite: bool = False) -> None:
    if not source.exists():
        return
    if source.is_file():
        if overwrite or not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return
    for item in source.rglob("*"):
        relative = item.relative_to(source)
        destination = target / relative
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif item.is_file() and (overwrite or not destination.exists()):
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return False


def _default_key_source_dir() -> Path:
    env_path = os.environ.get(DEFAULT_KEY_SOURCE_ENV)
    if env_path:
        return Path(env_path).expanduser()
    return RESOURCE_DIR / KEY_BRAIN_ID


def _default_key_source_dirs() -> list[Path]:
    sources = [_default_key_source_dir()]
    legacy_windows_seed = Path.home() / "AppData" / "Roaming" / "Appveyor Systems Inc" / "Flet" / "data" / KEY_BRAIN_ID
    if not any(_same_path(source, legacy_windows_seed) for source in sources):
        sources.append(legacy_windows_seed)
    return sources


def _copy_default_key_seed(source_dirs: Path | list[Path], brain_dir: Path, *, overwrite: bool = False) -> bool:
    candidates = [source_dirs] if isinstance(source_dirs, Path) else source_dirs
    source_dir = next(
        (
            source
            for source in candidates
            if source.exists()
            and not _same_path(source, brain_dir)
            and (source / "persona" / "profile.json").exists()
        ),
        None,
    )
    if source_dir is None:
        return False

    for child_name in ("assets", "persona", "tags"):
        _copy_missing_tree(source_dir / child_name, brain_dir / child_name, overwrite=overwrite)
    for file_name in ("config.json", "ui.json", PORTRAIT_EDIT_FILE):
        _copy_missing_tree(source_dir / file_name, brain_dir / file_name, overwrite=overwrite)
    return True


def _same_file_content(left: Path, right: Path) -> bool:
    try:
        return left.is_file() and right.is_file() and left.read_bytes() == right.read_bytes()
    except OSError:
        return False


def _key_uses_legacy_amadues_assets(brain_dir: Path) -> bool:
    return _same_file_content(brain_dir / "assets" / "avatar.png", RESOURCE_DIR / "amadues.png") or _same_file_content(
        brain_dir / "assets" / "portraits" / "neutral.png",
        RESOURCE_DIR / "amadues_Full_profile.png",
    )


def _reply_tag_emotion(tag: object) -> str:
    if tag is None:
        return ""
    if isinstance(tag, dict):
        return str(tag.get("emotion") or "")
    return str(getattr(tag, "emotion", "") or "")


def _load_model_config(config_dir: str | Path | None = None) -> ModelConfig:
    storage = ModelsStorage(config_dir)
    config = storage.load()
    provider_name = _normalize_model_provider(config.default_provider or MINIMAX_PROVIDER)
    provider_config = config.providers.get(provider_name)
    if provider_config is None or not (provider_config.api_key or "").strip():
        raise ChatConfigurationError(f"{_provider_display_name(provider_name)} API key is not configured.")

    catalog = get_model_catalog(provider_name)
    model_name = _normalize_model_name(provider_name, config.default_model or "")
    model_info = catalog.find_model(model_name) if catalog else None
    return ModelConfig(
        name=model_name,
        provider=PROVIDER_API_ENUMS[provider_name],
        api_key=provider_config.api_key,
        base_url=provider_config.base_url,
        max_tokens=model_info.max_tokens if model_info else 8192,
        temperature=0.7,
        supports_thinking=bool(model_info.reasoning) if model_info else False,
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
            "status_text": "",
            "accent_color": "#B6A8C9",
            "avatar": "assets/avatar.png",
            "portraits": {"neutral": "assets/portraits/neutral.png"},
            "last_message": "",
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


def _ensure_default_key_data(brain_id: str = KEY_BRAIN_ID) -> Path:
    brain_dir = PathResolver.get_brain_dir(brain_id)
    persona_dir = brain_dir / "persona"
    history_dir = brain_dir / "history"
    assets_dir = brain_dir / "assets"
    portraits_dir = assets_dir / "portraits"
    tags_dir = brain_dir / "tags"

    persona_dir.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    portraits_dir.mkdir(parents=True, exist_ok=True)
    tags_dir.mkdir(parents=True, exist_ok=True)

    seed_sources = _default_key_source_dirs()
    _copy_default_key_seed(seed_sources, brain_dir)
    if _key_uses_legacy_amadues_assets(brain_dir):
        _copy_default_key_seed(seed_sources, brain_dir, overwrite=True)

    _write_json_if_missing(persona_dir / "profile.json", _key_default_profile())
    _ensure_response_config(brain_dir / "config.json", DEFAULT_RESPONSE_LIMITS)
    _write_json_if_missing(
        persona_dir / "memories.json",
        {
            "episodic_memories": [],
            "preference_memories": [],
            "fact_memories": [],
            "daily_summary_memories": [],
            "monthly_summary_memories": [],
        },
    )
    _write_json_if_missing(
        persona_dir / "state.json",
        {
            "mood": "neutral",
            "energy": 0.6,
            "affinity": 0.0,
            "trust": 0.0,
            "familiarity": 0.0,
            "boundary_comfort": 50.0,
            "recent_valence": 0.0,
            "recent_support": 0.0,
            "recent_conflict": 0.0,
            "tension": 0.0,
            "current_focus": None,
            "last_emotion": "neutral",
            "updated_at": None,
        },
    )
    _write_json_if_missing(
        persona_dir / "speaking_style.json",
        {
            "base_style": {
                "vocabulary_level": "academic",
                "sentence_length": "short",
                "exclamation_rate": 0.08,
                "question_rate": 0.15,
                "ellipsis_rate": 0.7,
                "filler_words": [],
                "emotion_words": {},
                "emoji_usage": "sparse",
                "parenthesis_usage": "sparse",
            },
            "influence_weight": 0.2,
            "current_emotion": None,
            "custom_modifiers": {},
        },
    )
    _write_json_if_missing(brain_dir / "ui.json", _key_default_ui())
    _write_json_if_missing(brain_dir / PORTRAIT_EDIT_FILE, _key_default_portrait_edits())
    _write_json_if_missing(tags_dir / "reply_tags.json", {"tags": {}, "recent_order": [], "max_size": 100})
    _ensure_key_portrait_source_assets(brain_dir)

    return brain_dir


def _sync_key_defaults(brain_dir: Path) -> None:
    _merge_json(brain_dir / "persona" / "profile.json", _key_default_profile())
    _merge_json(brain_dir / "ui.json", _key_default_ui())
    _write_json_if_missing(brain_dir / PORTRAIT_EDIT_FILE, _key_default_portrait_edits())
    _ensure_key_portrait_source_assets(brain_dir)


_KEY_PROFILE_RUNTIME_KEYS = ("relationship_state", "relationship_score", "relationship_updated_at")


def _key_default_profile() -> dict:
    return {
        "name": "健",
        "age": 26,
        "gender": "male",
        "personality_traits": ["身体差", "冷静", "耐心", "博士生", "内耗", "冷幽默"],
        "background": "计算机科学博士生，从小成绩优异，一直热衷于研究虚拟化人格。做事非常脱线，神经大条。喜欢偶像应援等亚文化，常在半夜上线打游戏。",
        "speaking_style": "calm",
        "birthday": "1998.2.14",
        "interests": ["数学", "编程", "偶像", "游戏", "漫画", "亚文化"],
    }


def _key_default_ui() -> dict:
    return {
        "type": "Custom",
        "tags": ["身体差", "冷静", "耐心"],
        "intro": "一个被困在数字世界的灵魂",
        "status_text": "",
        "accent_color": "#B6A8C9",
        "avatar": "assets/avatar.png",
        "standing_image": "assets/portraits/neutral-640321d0.png",
        "portraits": {
            "happy": "assets/portraits/happy-3dd92ea1.png",
            "sad": "assets/portraits/sad-52b3dbf7.png",
            "angry": "assets/portraits/angry-de915d2d.png",
            "surprised": "assets/portraits/surprised-a41574a0.png",
            "neutral": "assets/portraits/neutral-640321d0.png",
        },
        "last_message": "",
        "last_time": "",
    }


def _key_default_portrait_edits() -> dict:
    return {
        "version": PORTRAIT_EDIT_VERSION,
        "layout": {"canvas_width": 390, "canvas_height": 520, "anchor_bbox": [28, 65, 363, 455]},
        "edits": {
            "happy": {
                "source_path": "assets/portrait_sources/happy-3dd92ea1.png",
                "processed_path": "assets/portraits/happy-3dd92ea1.png",
                "render_mode": "cutout",
                "background_color": [218, 134, 64],
                "tolerance": 120, "feather": 0, "crop_box": None,
                "scale": 1.0, "offset_x": 0, "offset_y": 0,
            },
            "sad": {
                "source_path": "assets/portrait_sources/sad-52b3dbf7.png",
                "processed_path": "assets/portraits/sad-52b3dbf7.png",
                "render_mode": "cutout",
                "background_color": [218, 134, 64],
                "tolerance": 120, "feather": 0, "crop_box": None,
                "scale": 1.0, "offset_x": 0, "offset_y": 0,
            },
            "angry": {
                "source_path": "assets/portrait_sources/angry-de915d2d.png",
                "processed_path": "assets/portraits/angry-de915d2d.png",
                "render_mode": "cutout",
                "background_color": [218, 134, 64],
                "tolerance": 120, "feather": 0, "crop_box": None,
                "scale": 1.0, "offset_x": 0, "offset_y": 0,
            },
            "surprised": {
                "source_path": "assets/portrait_sources/surprised-a41574a0.png",
                "processed_path": "assets/portraits/surprised-a41574a0.png",
                "render_mode": "cutout",
                "background_color": [218, 134, 64],
                "tolerance": 55, "feather": 0, "crop_box": None,
                "scale": 1.0, "offset_x": 0, "offset_y": 0,
            },
            "neutral": {
                "source_path": "assets/portrait_sources/neutral-640321d0.png",
                "processed_path": "assets/portraits/neutral-640321d0.png",
                "render_mode": "cutout",
                "background_color": [218, 134, 64],
                "tolerance": 32, "feather": 0, "crop_box": None,
                "scale": 1.0, "offset_x": 0, "offset_y": 0,
            },
        },
    }


def _ensure_key_portrait_source_assets(brain_dir: Path) -> None:
    edit_file = brain_dir / PORTRAIT_EDIT_FILE
    try:
        data = json.loads(edit_file.read_text(encoding="utf-8")) if edit_file.exists() else {}
    except (json.JSONDecodeError, OSError):
        data = {}
    edits = data.get("edits") if isinstance(data, dict) else None
    if not isinstance(edits, dict):
        edits = _key_default_portrait_edits()["edits"]

    for edit in edits.values():
        if not isinstance(edit, dict):
            continue
        source_path = str(edit.get("source_path") or "")
        processed_path = str(edit.get("processed_path") or "")
        if not source_path or not processed_path:
            continue
        source = brain_dir / source_path
        processed = brain_dir / processed_path
        if not source.exists() and processed.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(processed, source)


def _merge_json(path: Path, defaults: dict) -> None:
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    merged = dict(existing)
    merged.update(defaults)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")


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
            "background": "14岁时被任命为EVA初号机驾驶员，成为第三适格者",
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
            "intro": "14岁时被任命为EVA初号机驾驶员，成为第三适格者",
            "status_text": "",
            "accent_color": "#AEB8C7",
            "avatar": "assets/avatar.png",
            "portraits": {"neutral": "assets/portraits/neutral.png"},
            "last_message": "",
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


def ensure_default_startup_data() -> Path:
    data_dir = PathResolver.get_data_dir()
    roles = load_roles_from_data(data_dir)
    if roles:
        key_dir = data_dir / KEY_BRAIN_ID
        if key_dir.is_dir():
            if _key_uses_legacy_amadues_assets(key_dir):
                _copy_default_key_seed(_default_key_source_dirs(), key_dir, overwrite=True)
            if DEFAULT_KEY_SOURCE_ENV not in os.environ:
                _sync_key_defaults(key_dir)
        return data_dir / roles[0].id
    return _ensure_default_key_data()


def build_amadues_runtime(
    config_dir: str | Path | None = None,
    brain_id: str = KEY_BRAIN_ID,
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
        normal_character_delay: float | None = NORMAL_CHARACTER_DELAY_SECONDS,
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
        self._normal_character_delay = 0 if normal_character_delay is None else normal_character_delay

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
                [self._notice(role_id, MISSING_API_KEY_NOTICE)],
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
        final_emotion = ""
        try:
            runtime = self._get_runtime()
            self._select_role_runtime(role_id, runtime)
            stream_method = getattr(runtime.session_manager, "send_message_stream", None)
            if not callable(stream_method):
                result = runtime.session_manager.send_message_sync(user_message=text, emotion=None)
                final_emotion = _reply_tag_emotion(result.get("tag"))
                self._append_finished_reply(role_id, mode, assistant_id, str(result.get("content", "")))
                return

            if mode == "normal":
                normal_streamer = _NormalMessageStreamer(
                    self.view,
                    role_id,
                    assistant_id,
                    sentence_delay=self._normal_sentence_delay,
                    character_delay=self._normal_character_delay,
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
                    final_emotion = _reply_tag_emotion(event.get("tag"))
                    if normal_streamer is not None:
                        normal_streamer.finish(content if not accumulated else None)
                    else:
                        self.view.update_message_text(assistant_id, content, is_streaming=False)
                    return
                elif event_type == "error":
                    raise RuntimeError(str(event.get("error", "unknown streaming error")))
        except ChatConfigurationError:
            self.view.append_message(
                self._notice(role_id, MISSING_API_KEY_NOTICE)
            )
        except Exception as exc:
            self.view.append_message(self._notice(role_id, f"\u6d88\u606f\u53d1\u9001\u5931\u8d25\uff1a{exc}"))
        finally:
            if normal_streamer is not None:
                normal_streamer.finish()
            elif immersive_started:
                self.view.update_message_text(assistant_id, accumulated, is_streaming=False)
            self.view.set_typing(False)
            if final_emotion and callable(getattr(self.view, "set_reply_emotion", None)):
                self.view.set_reply_emotion(role_id, final_emotion)

    def _append_finished_reply(self, role_id: str, mode: str, assistant_id: str, content: str) -> None:
        if self.view is None:
            return
        if mode == "normal":
            streamer = _NormalMessageStreamer(
                self.view,
                role_id,
                assistant_id,
                sentence_delay=self._normal_sentence_delay,
                character_delay=self._normal_character_delay,
            )
            streamer.finish(content)
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
        settings.model_provider = _normalize_model_provider(settings.model_provider)
        settings.model_name = _normalize_model_name(settings.model_provider, settings.model_name)
        self.settings_storage.save_provider_config(settings.model_provider, settings.api_key, settings.model_name)
        self.settings_storage.save_ui_settings(settings)
        self._settings = self.settings_storage.load_ui_settings()
        self._invalidate_runtime()
        if self.view is not None:
            self.view.apply_settings(self._settings)

    def on_character_create_requested(self, draft: CharacterDraft) -> None:
        try:
            result = CharacterCreator(PathResolver.get_data_dir()).create(draft)
        except CharacterCreationError as exc:
            if self.view is not None:
                self.view.show_notice(str(exc), is_error=True)
            else:
                print(f"[ui] create character failed: {exc}")
            return

        self._invalidate_runtime()
        if self.view is not None:
            self._publish_data_roles()
            self.view.set_active_role(result.brain_id)
            self.view.show_notice(f"Created character: {draft.name.strip()}")
            self.view.show_page("home")

    def load_character_draft(self, role_id: str) -> CharacterDraft | None:
        try:
            brain_id = self._resolve_brain_id(role_id, self._runtime)
            return CharacterCreator(PathResolver.get_data_dir()).load_draft(brain_id)
        except CharacterCreationError as exc:
            if self.view is not None:
                self.view.show_notice(str(exc), is_error=True)
            else:
                print(f"[ui] load character failed: {exc}")
        return None

    def on_character_update_requested(self, role_id: str, draft: CharacterDraft) -> None:
        try:
            brain_id = self._resolve_brain_id(role_id, self._runtime)
            result = CharacterCreator(PathResolver.get_data_dir()).update(brain_id, draft)
        except CharacterCreationError as exc:
            if self.view is not None:
                self.view.show_notice(str(exc), is_error=True)
            else:
                print(f"[ui] update character failed: {exc}")
            return

        self._invalidate_runtime()
        if self.view is not None:
            self._publish_data_roles()
            self.view.set_active_role(result.brain_id)
            self.view.show_notice(f"Saved character: {draft.name.strip()}")
            self.view.show_page("home")

    def on_character_delete_requested(self, role_id: str) -> bool:
        try:
            brain_id = self._resolve_brain_id(role_id, self._runtime)
            data_dir = PathResolver.get_data_dir()
            roles = load_roles_from_data(data_dir)
            if len(roles) <= 1:
                raise CharacterCreationError("至少需要保留一个人格")
            if not VALID_BRAIN_ID.fullmatch(brain_id):
                raise CharacterCreationError(f"Invalid character id: {brain_id}")

            brain_dir = (data_dir / brain_id).resolve()
            data_root = data_dir.resolve()
            if brain_dir.parent != data_root or not brain_dir.is_dir():
                raise CharacterCreationError(f"Character id '{brain_id}' does not exist.")

            shutil.rmtree(brain_dir)
        except (CharacterCreationError, OSError) as exc:
            if self.view is not None:
                self.view.show_notice(str(exc), is_error=True)
            else:
                print(f"[ui] delete character failed: {exc}")
            return False

        self._role_mapping.pop(role_id, None)
        self._role_mapping.pop(brain_id, None)
        self._invalidate_runtime()
        if self.view is not None:
            self._publish_data_roles()
            remaining_roles = load_roles_from_data(PathResolver.get_data_dir())
            if remaining_roles:
                self.view.set_active_role(remaining_roles[0].id)
            self.view.show_notice(f"Deleted character: {brain_id}")
            self.view.show_page("home")
        return True

    def on_character_export_requested(self, role_id: str, destination_path: str = "") -> str:
        try:
            brain_id = self._resolve_brain_id(role_id, self._runtime)
            package_path = Path(destination_path).expanduser() if destination_path else self._default_export_path(brain_id)
            result = export_character_package(PathResolver.get_data_dir(), brain_id, package_path)
        except (CharacterPackageError, OSError) as exc:
            if self.view is not None:
                self.view.show_notice(str(exc), is_error=True)
            else:
                print(f"[ui] export character failed: {exc}")
            return ""

        if self.view is not None and result.package_path is not None:
            self.view.show_notice(f"Exported character: {result.package_path}")
        return result.package_path.as_posix() if result.package_path is not None else ""

    def on_character_import_requested(self, package_path: str) -> str:
        try:
            result = import_character_package(PathResolver.get_data_dir(), Path(package_path), overwrite=True)
        except (CharacterPackageError, OSError) as exc:
            if self.view is not None:
                self.view.show_notice(str(exc), is_error=True)
            else:
                print(f"[ui] import character failed: {exc}")
            return ""

        self._invalidate_runtime()
        if self.view is not None:
            self._publish_data_roles()
            self.view.set_active_role(result.brain_id)
            self.view.show_notice(f"Imported character: {result.brain_id}")
        return result.brain_id

    def _default_export_path(self, brain_id: str) -> Path:
        exports_dir = PathResolver.get_app_storage_root()
        base_dir = (exports_dir / "exports") if exports_dir is not None else (PathResolver.get_data_dir().parent / "exports")
        return base_dir / f"{brain_id}.amadues"

    def on_theme_toggled(self, is_dark: bool) -> None:
        self._settings.is_dark = is_dark

    def on_voice_requested(self) -> None:
        print("[ui] voice requested")

    def on_avatar_upload_requested(self) -> None:
        print("[ui] avatar upload requested")

    def on_portrait_upload_requested(self, emotion_id: str) -> None:
        print(f"[ui] portrait upload requested: {emotion_id}")
