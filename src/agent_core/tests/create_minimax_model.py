#!/usr/bin/env python3
"""Create and save a MiniMax model config using the native storage objects."""

from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SRC_DIR = SCRIPT_DIR.parents[2] / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agent_core.models import ModelsStorage, ProviderConfig
from agent_core.session import PathResolver

MINIMAX_API_KEY = "sk-cp-vAU2LGd4d-l4_nkQGV2yQh_QeWxPFh2GZPsQLx0q4YyLMzwf2kAyjBs1-OIeJSChQxFuQyVtJ6aXk3gPthXALlYzL06p3_HYDlS7316Up80p0EoDZqVftcY"


def build_minimax_provider() -> ProviderConfig:
    """Build the MiniMax provider config with the required wire format."""
    return ProviderConfig(
        base_url="https://api.minimaxi.com/v1",
        api_key=MINIMAX_API_KEY,
        api_type="openai",
        auth_header=True,
    )


def create_minimax_model() -> Path:
    """Create the MiniMax provider config and set MiniMax-M2.5 as default."""
    target_dir = PathResolver.get_config_dir()
    storage = ModelsStorage(target_dir)
    config = storage.load()

    config.providers["minimax"] = build_minimax_provider()
    config.default_provider = "minimax"
    config.default_model = "MiniMax-M2.5"
    storage.save(config)

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
