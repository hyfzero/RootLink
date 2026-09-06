"""Versioned local JSON-lines bridge. No GUI, tool execution or protocol logging."""
from __future__ import annotations

import contextlib
import json
import logging
import os
from pathlib import Path
import shutil
import sys

from .api.adapter import ModelConfig
from .api.client import ChatAgent
from .session.brain_registry import BrainRegistry
from .session.config import SessionConfig
from .session.manager import SessionManager
from .session.path_resolver import PathResolver

LIMIT = 2 * 1024 * 1024


def create_manager(settings: dict, chat_agent=None) -> SessionManager:
    """Import seed data once; all subsequent writes belong to the original core."""
    root = Path(settings["data_dir"]).resolve()
    seed = Path(settings["role_dir"]).resolve()
    if root == seed or root in seed.parents or seed in root.parents:
        raise ValueError("seed and runtime data must be separate")
    profile = seed / "persona/profile.json"
    if not profile.is_file() or not json.loads(profile.read_text(encoding="utf-8")):
        raise ValueError("nonempty persona/profile.json required")
    root.mkdir(parents=True, exist_ok=True)
    os.environ["AGENT_DATA_DIR"] = str(root)
    os.environ["AGENT_CONFIG_DIR"] = str(root / "config")
    PathResolver.clear_app_storage_root()
    destination = root / "default"
    if not destination.exists():
        # Import only persona/config data, never the old C++ session files.
        staging = root / "seed.tmp"
        if staging.exists():
            shutil.rmtree(staging)
        (staging / "persona").mkdir(parents=True)
        for name in ("profile.json", "state.json", "memories.json", "speaking_style.json"):
            source = seed / "persona" / name
            if not source.exists():
                source = seed / name
            if source.exists():
                value = json.loads(source.read_text(encoding="utf-8"))
                if not isinstance(value, dict):
                    raise ValueError("role JSON must be an object")
                shutil.copyfile(source, staging / "persona" / name)
        if (seed / "config.json").exists():
            shutil.copyfile(seed / "config.json", staging / "config.json")
        staging.rename(destination)
    # Never silently reconstruct a missing runtime persona from defaults.
    runtime_profile = destination / "persona/profile.json"
    value = json.loads(runtime_profile.read_text(encoding="utf-8")) if runtime_profile.is_file() else None
    if not isinstance(value, dict) or not value:
        raise ValueError("invalid runtime persona")
    model = settings["model"]
    config = ModelConfig(name=model["name"], provider=model["provider"],
                         api_key=model.get("api_key"), base_url=model["base_url"].rstrip("/"),
                         tokenizer_mode="heuristic", tokenizer_fallback="hybrid_v1",
                         supports_function_calling=False)
    if chat_agent is None:
        chat_agent = ChatAgent(config)
        chat_agent.require_complete_stream = True
        # Keep provider request/response adapters; override only transport settings.
        chat_agent.extra_headers = model.get("headers", {})
        chat_agent.auth_header = model.get("auth_header", True)
        chat_agent.chat_path = model.get("chat_path", "/chat/completions")
        chat_agent.request_timeout = settings.get("llm_timeout_ms", 60000) / 1000
    registry = BrainRegistry(root)
    registry.register("default", registry._load_brain_components(destination))
    registry.switch("default")
    return SessionManager(SessionConfig(model_config=config), registry, chat_agent,
                          use_msgpack=False, tools={}, tool_definitions=None)


def serve(source, sink, factory=create_manager) -> int:
    manager = None
    last_id = 0
    lock_file = None

    def emit(request_id, event, **fields):
        data = json.dumps(dict(v=1, id=request_id, event=event, **fields), ensure_ascii=False)
        if len(data.encode("utf-8")) > LIMIT:
            raise ValueError("response too large")
        sink.write(data + "\n")
        sink.flush()

    try:
        while True:
            line = source.readline(LIMIT + 1)
            if not line:
                return 0
            request_id = 0
            try:
                if len(line.encode("utf-8")) > LIMIT or not line.endswith("\n"):
                    raise ValueError("invalid frame")
                request = json.loads(line)
                request_id = request["id"]
                if (request.get("v") != 1 or type(request_id) is not int
                        or request_id <= last_id):
                    raise ValueError("version or request ID")
                last_id = request_id
                operation = request["op"]
                if operation == "init" and manager is None:
                    # Lifetime lock prevents two workers writing the same brain.
                    import fcntl
                    root = Path(request["settings"]["data_dir"]).resolve()
                    root.mkdir(parents=True, exist_ok=True)
                    lock_file = (root / ".core.lock").open("a")
                    fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    manager = factory(request["settings"])
                    emit(request_id, "ready")
                elif operation == "health" and manager is not None:
                    emit(request_id, "ready")
                elif operation == "shutdown":
                    emit(request_id, "done", text="")
                    return 0
                elif operation == "message" and manager is not None:
                    message = request.get("text")
                    if not isinstance(message, str) or not message.strip() or len(message.encode("utf-8")) > 128 * 1024:
                        raise ValueError("invalid message")
                    done = False
                    for event in manager.send_message_stream(message, allow_sync_fallback=False):
                        if event["type"] == "delta":
                            emit(request_id, "delta", text=event["delta"])
                        elif event["type"] == "done":
                            if not event.get("content"):
                                raise ValueError("empty answer")
                            emit(request_id, "done", text=event["content"])
                            done = True
                        else:
                            raise RuntimeError("core request failed")
                    if not done:
                        raise RuntimeError("incomplete reply")
                else:
                    raise ValueError("invalid operation")
            except Exception:
                # Never return exception text: providers may embed keys or payloads.
                emit(request_id if type(request_id) is int else 0, "error", code="core_failed")
                return 1
    finally:
        if lock_file is not None:
            lock_file.close()


def main() -> int:
    logging.disable(logging.CRITICAL)
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    protocol = sys.stdout
    # Legacy core print statements must never contaminate the protocol or leak responses.
    with open(os.devnull, "w") as discarded, contextlib.redirect_stdout(discarded), contextlib.redirect_stderr(discarded):
        return serve(sys.stdin, protocol)


if __name__ == "__main__":
    raise SystemExit(main())
