#!/usr/bin/env python3
"""Copy repo config/models.json into the resolved persistent config directory."""

from __future__ import annotations

import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agent_core.models import ModelsJsonConfig, ModelsStorage
from agent_core.session import PathResolver


def save_models_config(
    source_file: Path | None = None,
    target_dir: Path | None = None,
) -> Path:
    """Load repo models.json and save it to the resolved config directory."""
    source_path = source_file or (PROJECT_ROOT / "config" / "models.json")
    destination_dir = target_dir or PathResolver.get_config_dir()

    if not source_path.exists():
        raise FileNotFoundError(f"Source config not found: {source_path}")

    with open(source_path, "r", encoding="utf-8") as source_handle:
        config = ModelsJsonConfig.from_dict(json.load(source_handle))

    storage = ModelsStorage(destination_dir)
    storage.save(config)
    return storage.models_file


def main() -> int:
    source_path = PROJECT_ROOT / "config" / "models.json"

    try:
        target_file = save_models_config(source_file=source_path)
    except Exception as exc:  # pragma: no cover
        print(f"Source: {source_path}")
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Source: {source_path}")
    print(f"Target: {target_file}")
    print("Saved: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
