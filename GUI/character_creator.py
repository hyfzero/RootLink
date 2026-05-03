"""Create data-backed character brains from UI drafts."""

from __future__ import annotations

import json
import re
import shutil
import uuid
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any

from agent_core.brain import (
    MessageHistory,
    Persona,
    PersonaProfile,
    PersonalityState,
    SpeakingStyle,
    SpeakingStyleEngine,
    TagCache,
)
from agent_core.session import PathResolver

from .interfaces import CharacterDraft, MemoryDraft


ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
VALID_BRAIN_ID = re.compile(r"^[A-Za-z0-9_-]+$")
DEFAULT_ACCENT_PALETTE = ["#B6A8C9", "#8FB7B3", "#E1A95F", "#C98E8E", "#88A0C8", "#A9B86E"]
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESOURCE_DIR = PROJECT_ROOT / "resource"
DEFAULT_RESPONSE_LIMITS = {"max_tokens": 2000, "max_sentences": 5}


class CharacterCreationError(ValueError):
    """Raised when a character draft cannot be persisted."""


@dataclass(frozen=True)
class CharacterCreationResult:
    brain_id: str
    brain_dir: Path


class CharacterCreator:
    """Persist a complete brain directory for one character draft."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or PathResolver.get_data_dir()

    def create(self, draft: CharacterDraft) -> CharacterCreationResult:
        brain_id = self._validate_brain_id(draft.brain_id)
        name = draft.name.strip()
        if not name:
            raise CharacterCreationError("Character name is required.")

        self._data_dir.mkdir(parents=True, exist_ok=True)
        final_dir = self._data_dir / brain_id
        if final_dir.exists():
            raise CharacterCreationError(f"Character id '{brain_id}' already exists.")

        tmp_dir = self._data_dir / f".creating-{brain_id}-{uuid.uuid4().hex}"
        try:
            self._write_brain(tmp_dir, brain_id, name, draft)
            tmp_dir.rename(final_dir)
        except CharacterCreationError:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise
        except Exception as exc:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise CharacterCreationError(f"Failed to create character: {exc}") from exc

        return CharacterCreationResult(brain_id=brain_id, brain_dir=final_dir)

    def _write_brain(self, brain_dir: Path, brain_id: str, name: str, draft: CharacterDraft) -> None:
        for relative_dir in (
            "assets",
            "assets/portraits",
            "persona",
            "history",
            "history/daily",
            "history/summaries",
            "session/current",
            "session/archive",
            "tags",
        ):
            (brain_dir / relative_dir).mkdir(parents=True, exist_ok=True)

        template_dir = self._template_dir(draft.template)
        profile = self._build_profile(name, draft, template_dir)
        persona = Persona(profile)
        self._add_draft_memories(persona, draft.memories)

        self._write_json(brain_dir / "persona" / "profile.json", profile.to_dict())
        self._write_json(brain_dir / "persona" / "memories.json", self._memory_payload(persona))
        self._write_json(brain_dir / "persona" / "state.json", PersonalityState().to_dict())
        self._write_json(brain_dir / "persona" / "speaking_style.json", self._build_style(draft, template_dir).to_dict())
        self._write_json(brain_dir / "history" / "history.json", MessageHistory().to_dict())
        self._write_json(brain_dir / "tags" / "reply_tags.json", TagCache().to_dict())
        self._write_json(brain_dir / "config.json", self._build_config(template_dir))

        avatar_rel, portraits_rel = self._copy_assets(brain_dir, draft)
        self._write_json(brain_dir / "ui.json", self._build_ui(brain_id, draft, profile, avatar_rel, portraits_rel))

    def _build_profile(self, name: str, draft: CharacterDraft, template_dir: Path | None) -> PersonaProfile:
        template = self._read_template_json(template_dir, "persona/profile.json")
        age = self._parse_age(draft.age)
        if age is None:
            age = template.get("age")

        background = draft.background.strip() or draft.description.strip() or str(template.get("background") or "")
        traits = draft.personality_traits or [str(item) for item in template.get("personality_traits", [])]
        interests = draft.interests or [str(item) for item in template.get("interests", [])]

        return PersonaProfile(
            name=name,
            age=age if isinstance(age, int) else None,
            gender=draft.gender or str(template.get("gender") or "unknown"),
            personality_traits=[item.strip() for item in traits if str(item).strip()],
            background=background,
            speaking_style=draft.speaking_style_preset or str(template.get("speaking_style") or "friendly"),
            birthday=draft.birthday.strip() or template.get("birthday"),
            interests=[item.strip() for item in interests if str(item).strip()],
            relationship_state="neutral",
            relationship_score=0.0,
            relationship_updated_at=None,
        )

    def _build_style(self, draft: CharacterDraft, template_dir: Path | None) -> SpeakingStyleEngine:
        template = self._read_template_json(template_dir, "persona/speaking_style.json")
        if template:
            engine = SpeakingStyleEngine.from_dict(template)
        else:
            engine = SpeakingStyleEngine()
        base_style = engine.base_style
        defaults = CharacterDraft()
        inherit_defaults = bool(template)

        engine.base_style = SpeakingStyle(
            vocabulary_level=base_style.vocabulary_level if inherit_defaults and draft.vocabulary_level == defaults.vocabulary_level else draft.vocabulary_level,
            sentence_length=base_style.sentence_length if inherit_defaults and draft.sentence_length == defaults.sentence_length else draft.sentence_length,
            exclamation_rate=float(base_style.exclamation_rate if inherit_defaults and draft.exclamation_rate == defaults.exclamation_rate else draft.exclamation_rate),
            question_rate=float(base_style.question_rate if inherit_defaults and draft.question_rate == defaults.question_rate else draft.question_rate),
            ellipsis_rate=float(base_style.ellipsis_rate if inherit_defaults and draft.ellipsis_rate == defaults.ellipsis_rate else draft.ellipsis_rate),
            filler_words=list(base_style.filler_words),
            emotion_words=dict(base_style.emotion_words),
            emoji_usage=base_style.emoji_usage if inherit_defaults and draft.emoji_usage == defaults.emoji_usage else draft.emoji_usage,
            parenthesis_usage=base_style.parenthesis_usage if inherit_defaults and draft.parenthesis_usage == defaults.parenthesis_usage else draft.parenthesis_usage,
        )
        if not inherit_defaults or draft.influence_weight != defaults.influence_weight:
            engine.influence_weight = float(draft.influence_weight)
        return engine

    def _build_config(self, template_dir: Path | None) -> dict[str, Any]:
        template_config = self._read_template_json(template_dir, "config.json")
        if template_config:
            return template_config
        return {"response": dict(DEFAULT_RESPONSE_LIMITS)}

    def _build_ui(
        self,
        brain_id: str,
        draft: CharacterDraft,
        profile: PersonaProfile,
        avatar_rel: str,
        portraits_rel: dict[str, str],
    ) -> dict[str, Any]:
        tags = profile.personality_traits[:3] or ["custom"]
        intro = draft.description.strip() or profile.background[:120]
        return {
            "type": "Custom",
            "tags": tags,
            "intro": intro,
            "status_text": "Ready to chat.",
            "accent_color": self._accent_color(brain_id),
            "avatar": avatar_rel,
            "standing_image": portraits_rel.get("neutral", ""),
            "portraits": portraits_rel,
            "portrait_layout": self._json_safe(draft.portrait_layout) if draft.portrait_layout else {},
            "portrait_sources": {
                emotion: self._json_safe(edit)
                for emotion, edit in draft.portrait_edits.items()
                if str(getattr(edit, "source_path", "")).strip()
            },
            "last_message": "",
            "last_time": "",
        }

    def _copy_assets(self, brain_dir: Path, draft: CharacterDraft) -> tuple[str, dict[str, str]]:
        avatar_source = draft.avatar_path.strip()
        avatar_rel = ""
        if avatar_source:
            avatar_rel = self._copy_image(avatar_source, brain_dir / "assets", "avatar", brain_dir)

        portraits: dict[str, str] = {}
        for emotion, source in draft.portraits.items():
            if not str(source).strip():
                continue
            portraits[str(emotion)] = self._copy_image(
                str(source),
                brain_dir / "assets" / "portraits",
                str(emotion),
                brain_dir,
            )

        return avatar_rel, portraits

    def _copy_image(self, source: str, target_dir: Path, stem: str, brain_dir: Path) -> str:
        source_path = Path(source)
        if not source_path.exists() or not source_path.is_file():
            raise CharacterCreationError(f"Image file not found: {source}")
        suffix = source_path.suffix.lower()
        if suffix not in ALLOWED_IMAGE_EXTENSIONS:
            raise CharacterCreationError("Images must be PNG, JPG, JPEG, or WebP.")

        target = target_dir / f"{stem}{suffix}"
        shutil.copy2(source_path, target)
        return target.relative_to(brain_dir).as_posix()

    def _template_dir(self, template: str) -> Path | None:
        template_id = (template or "").strip()
        if not template_id or template_id == "default" or not VALID_BRAIN_ID.fullmatch(template_id):
            return None
        path = self._data_dir / template_id
        return path if path.is_dir() else None

    def _read_template_json(self, template_dir: Path | None, relative_path: str) -> dict[str, Any]:
        if template_dir is None:
            return {}
        path = template_dir / relative_path
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}

    def _add_draft_memories(self, persona: Persona, memories: list[MemoryDraft]) -> None:
        allowed_types = {"episodic", "preference", "fact", "daily_summary", "monthly_summary"}
        for memory in memories:
            content = memory.content.strip()
            if not content:
                continue
            memory_type = memory.memory_type if memory.memory_type in allowed_types else "episodic"
            persona.add_memory(
                content=content,
                memory_type=memory_type,
                importance=float(memory.importance),
                context=memory.context.strip() or None,
            )

    def _memory_payload(self, persona: Persona) -> dict[str, Any]:
        data = persona.to_dict()
        data.pop("profile", None)
        data.pop("state", None)
        return data

    def _validate_brain_id(self, value: str) -> str:
        brain_id = value.strip()
        if not brain_id:
            raise CharacterCreationError("Character id is required.")
        if not VALID_BRAIN_ID.fullmatch(brain_id):
            raise CharacterCreationError("Character id can only contain letters, numbers, '-' and '_'.")
        if brain_id in {".", ".."} or "/" in brain_id or "\\" in brain_id:
            raise CharacterCreationError("Character id cannot contain path separators.")
        return brain_id

    def _parse_age(self, value: str) -> int | None:
        text_value = value.strip()
        if not text_value:
            return None
        try:
            age = int(text_value)
        except ValueError:
            return None
        return age if age >= 0 else None

    def _accent_color(self, brain_id: str) -> str:
        index = sum(ord(char) for char in brain_id) % len(DEFAULT_ACCENT_PALETTE)
        return DEFAULT_ACCENT_PALETTE[index]

    def _json_safe(self, value: object) -> object:
        if value is None:
            return None
        if is_dataclass(value):
            return self._json_safe(asdict(value))
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        if isinstance(value, tuple):
            return [self._json_safe(item) for item in value]
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        return value

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
