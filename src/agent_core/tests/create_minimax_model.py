#!/usr/bin/env python3
"""Create and save a MiniMax model config using the built-in model helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agent_core.models import ModelsStorage, setup_provider
from agent_core.session import PathResolver


def load_minimax_api_key() -> str:
    """Load the MiniMax API key from the repo config file."""
    source_path = PROJECT_ROOT / "config" / "models.json"
    if not source_path.exists():
        raise FileNotFoundError(f"Source config not found: {source_path}")

    with open(source_path, "r", encoding="utf-8") as source_handle:
        data = json.load(source_handle)

    api_key = data.get("providers", {}).get("minimax", {}).get("api_key")
    if not api_key:
        raise ValueError(f"MiniMax API key not found in {source_path}")

    return str(api_key)


def create_minimax_model() -> Path:
    """Create the MiniMax provider config and set MiniMax-M2.5 as default."""
    api_key = load_minimax_api_key()
    target_dir = PathResolver.get_config_dir()

    setup_provider("minimax", api_key, config_dir=target_dir)
    storage = ModelsStorage(target_dir)
    storage.set_default("minimax", "MiniMax-M2.5")

    return storage.models_file


def main() -> int:
    try:
        target_file = create_minimax_model()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("Provider: minimax")
    print("Model: MiniMax-M2.5")
    print(f"Target: {target_file}")
    print("Saved: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
