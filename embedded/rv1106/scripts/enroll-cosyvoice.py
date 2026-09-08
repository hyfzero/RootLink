#!/usr/bin/env python3
"""Create or resume a bounded DashScope CosyVoice enrollment."""

from __future__ import annotations

import argparse
import json
import math
import os
import queue
import re
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlparse


class EnrollmentError(Exception):
    """An expected, user-facing enrollment failure."""


_PREFIX = re.compile(r"^[A-Za-z0-9]{1,10}$")
_TRUSTED_BASE_HOSTS = {"dashscope.aliyuncs.com", "cn-beijing.maas.aliyuncs.com"}
_WORKSPACE_HOST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*\.cn-beijing\.maas\.aliyuncs\.com$", re.IGNORECASE)


def _https_url(value: str, *, base: bool = False) -> str:
    parsed = urlparse(value)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise EnrollmentError("invalid URL")
    if base:
        hostname = parsed.hostname.lower()
        if parsed.username is not None or parsed.password is not None:
            raise EnrollmentError("untrusted base URL")
        try:
            port = parsed.port
        except ValueError as exc:
            raise EnrollmentError("untrusted base URL") from exc
        if port not in (None, 443):
            raise EnrollmentError("untrusted base URL")
        if hostname not in _TRUSTED_BASE_HOSTS and not _WORKSPACE_HOST.fullmatch(hostname):
            raise EnrollmentError("untrusted base URL")
    return value


def _read_api_key(path: Path) -> str:
    env_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if env_key.strip():
        return env_key.strip()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise EnrollmentError("unable to read secrets file") from exc
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == "DASHSCOPE_API_KEY" and value.strip():
            return value.strip()
    raise EnrollmentError("DASHSCOPE_API_KEY is missing")


def _write_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = None
    try:
        handle = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=str(path.parent),
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        )
        with handle:
            json.dump(record, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    except OSError as exc:
        if handle is not None:
            try:
                os.unlink(handle.name)
            except OSError:
                pass
        raise EnrollmentError("unable to write output") from exc


def _load_record(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EnrollmentError("existing output is invalid") from exc
    if not isinstance(data, dict):
        raise EnrollmentError("existing output is invalid")
    return data


def _bounded_call(function, timeout: float):
    """Run an SDK request with a hard caller-side deadline."""
    result: queue.Queue = queue.Queue(maxsize=1)

    def invoke() -> None:
        try:
            result.put((True, function()))
        except BaseException as exc:  # transfer without printing SDK details
            result.put((False, exc))

    worker = threading.Thread(target=invoke, daemon=True)
    worker.start()
    worker.join(max(0.0, timeout))
    if worker.is_alive():
        raise EnrollmentError("request timed out")
    ok, value = result.get_nowait()
    if not ok:
        raise EnrollmentError("provider request failed") from value
    return value


def _service(api_key: str, base_url: str):
    try:
        import dashscope  # type: ignore
        from dashscope.audio.tts_v2 import VoiceEnrollmentService  # type: ignore
    except ImportError as exc:
        raise EnrollmentError("dashscope SDK is unavailable") from exc
    # These are the official SDK globals used by the sample; no key is printed.
    dashscope.api_key = api_key
    dashscope.base_http_api_url = base_url
    try:
        return VoiceEnrollmentService()
    except Exception as exc:
        raise EnrollmentError("unable to initialize provider") from exc


def _voice_id(value) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        for key in ("voice_id", "voiceId", "id"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    raise EnrollmentError("provider returned no voice ID")


def _status(value) -> str:
    if not isinstance(value, dict):
        raise EnrollmentError("provider returned invalid status")
    candidate = value.get("status")
    return candidate.strip().upper() if isinstance(candidate, str) else ""


def _validate_voice_model(voice_id: str, model: str) -> None:
    if not voice_id.startswith(model + "-"):
        raise EnrollmentError("voice ID does not match model")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--audio-url")
    source.add_argument("--voice-id")
    parser.add_argument("--prefix", default="amadeus")
    parser.add_argument("--model", default="cosyvoice-v3.5-plus")
    parser.add_argument("--secrets-file", default="config/rootlink-secrets.env")
    parser.add_argument("--base-url", default="https://dashscope.aliyuncs.com/api/v1")
    parser.add_argument("--output", default="build/windows-cloud/cosyvoice-voice.json")
    parser.add_argument("--timeout", type=float, default=300.0)
    return parser


def run(args, *, service_factory=None, clock=time.monotonic, sleeper=time.sleep) -> int:
    if not _PREFIX.fullmatch(args.prefix):
        raise EnrollmentError("prefix must be 1-10 alphanumeric characters")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        raise EnrollmentError("timeout must be positive")
    base_url = _https_url(args.base_url, base=True)
    audio_url = _https_url(args.audio_url) if args.audio_url else None
    output = Path(args.output)
    record = _load_record(output)
    resume = bool(args.voice_id)

    if resume:
        if record and record.get("voice_id") not in (None, args.voice_id):
            raise EnrollmentError("output belongs to another voice ID")
        if record and record.get("model", args.model) != args.model:
            raise EnrollmentError("output model does not match")
        if record and record.get("target_model", args.model) != args.model:
            raise EnrollmentError("output model does not match")
        if record and record.get("prefix", args.prefix) != args.prefix:
            raise EnrollmentError("output prefix does not match")
        voice_id = args.voice_id
        _validate_voice_model(voice_id, args.model)
        if record is None:
            record = {"voice_id": voice_id, "model": args.model, "prefix": args.prefix}
    else:
        if record is not None:
            raise EnrollmentError("output already exists; resume with --voice-id")

    api_key = _read_api_key(Path(args.secrets_file))
    service = service_factory(api_key, base_url) if service_factory else _service(api_key, base_url)
    deadline = clock() + args.timeout

    if not resume:
        remaining = deadline - clock()
        if remaining <= 0:
            raise EnrollmentError("timeout exceeded")
        try:
            created = _bounded_call(
                lambda: service.create_voice(
                    target_model=args.model, prefix=args.prefix, url=audio_url,
                    language_hints=["ja"],
                ), remaining,
            )
        except EnrollmentError:
            raise
        except Exception as exc:
            raise EnrollmentError("provider request failed") from exc
        voice_id = _voice_id(created)
        _validate_voice_model(voice_id, args.model)
        record = {"voice_id": voice_id, "model": args.model, "target_model": args.model, "prefix": args.prefix,
                  "audio_url": audio_url, "status": "PENDING"}
        _write_record(output, record)

    while True:
        remaining = deadline - clock()
        if remaining <= 0:
            record["status"] = "TIMEOUT"
            _write_record(output, record)
            raise EnrollmentError("poll timeout")
        response = _bounded_call(lambda: service.query_voice(voice_id), remaining)
        if isinstance(response, dict) and "target_model" in response:
            target_model = response.get("target_model")
            if target_model != args.model:
                raise EnrollmentError("provider model does not match")
        state = _status(response)
        record["status"] = state or "PENDING"
        if state == "OK":
            record.update({"TTS_MODEL": args.model, "TTS_VOICE": voice_id})
            _write_record(output, record)
            print(f"TTS_MODEL={args.model}")
            print(f"TTS_VOICE={voice_id}")
            return 0
        if state == "UNDEPLOYED":
            _write_record(output, record)
            raise EnrollmentError("voice enrollment failed")
        wait_for = min(10.0, max(0.0, deadline - clock()))
        if wait_for <= 0:
            continue
        sleeper(wait_for)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        print("enrollment interrupted", file=sys.stderr)
        return 130
    except EnrollmentError as exc:
        print(f"enrollment error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"enrollment error: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
