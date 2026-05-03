"""Load companion roles from data-backed brain directories."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agent_core.session import BrainRegistry, PathResolver

from .interfaces import CompanionRole

DEFAULT_ACCENT_COLOR = "#B6A8C9"
DEFAULT_ROLE_TYPE = "Companion"
DEFAULT_STATUS_TEXT = "Ready to chat."


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def _resolve_data_path(brain_dir: Path, value: object) -> str:
    raw_path = str(value or "").strip()
    if not raw_path:
        return ""

    path = Path(raw_path)
    if not path.is_absolute():
        path = brain_dir / path
    return path.as_posix()


def _load_portraits(brain_dir: Path, ui_data: dict[str, Any]) -> dict[str, str]:
    portraits_data = ui_data.get("portraits")
    portraits: dict[str, str] = {}
    if isinstance(portraits_data, dict):
        portraits = {
            str(emotion): _resolve_data_path(brain_dir, path)
            for emotion, path in portraits_data.items()
            if str(path or "").strip()
        }

    neutral_path = brain_dir / "assets" / "portraits" / "neutral.png"
    if "neutral" not in portraits and neutral_path.exists():
        portraits["neutral"] = neutral_path.as_posix()
    return portraits


def role_from_brain(registry: BrainRegistry, brain_id: str, data_dir: Optional[Path] = None) -> Optional[CompanionRole]:
    """Build a UI role from one loaded brain and its optional ui.json metadata."""

    info = registry.get_brain_info(brain_id)
    if info is None:
        return None

    root = data_dir or PathResolver.get_data_dir()
    brain_dir = root / brain_id
    ui_data = _read_json(brain_dir / "ui.json")
    portraits = _load_portraits(brain_dir, ui_data)
    avatar_path = _resolve_data_path(brain_dir, ui_data.get("avatar"))
    legacy_avatar_path = brain_dir / "assets" / "avatar.png"
    if not avatar_path and legacy_avatar_path.exists():
        avatar_path = legacy_avatar_path.as_posix()
    standing_image_path = (
        portraits.get("neutral")
        or _resolve_data_path(brain_dir, ui_data.get("standing_image") or ui_data.get("portrait"))
    )

    return CompanionRole(
        id=brain_id,
        name=info.name,
        type=str(ui_data.get("type") or DEFAULT_ROLE_TYPE),
        tags=[str(tag) for tag in ui_data.get("tags", []) if str(tag).strip()],
        intro=str(ui_data.get("intro") or info.description),
        status_text=str(ui_data.get("status_text") or DEFAULT_STATUS_TEXT),
        accent_color=str(ui_data.get("accent_color") or DEFAULT_ACCENT_COLOR),
        avatar_path=avatar_path,
        standing_image_path=standing_image_path,
        portraits=portraits,
        last_message=str(ui_data.get("last_message") or ""),
        last_time=str(ui_data.get("last_time") or ""),
    )


def load_roles_from_registry(registry: BrainRegistry, data_dir: Optional[Path] = None) -> list[CompanionRole]:
    """Return all loaded brains as UI roles."""

    roles: list[CompanionRole] = []
    for brain_id in sorted(registry.list_brains()):
        role = role_from_brain(registry, brain_id, data_dir)
        if role is not None:
            roles.append(role)
    return roles


def _load_roles_from_root(root: Path) -> list[CompanionRole]:
    if not root.exists():
        return []
    registry = BrainRegistry(root)
    registry.load_all()
    return load_roles_from_registry(registry, root)


def load_roles_from_data(data_dir: Optional[Path] = None) -> list[CompanionRole]:
    """Scan the data directory and return data-backed UI roles."""

    root = data_dir or PathResolver.get_data_dir()
    return _load_roles_from_root(root)
