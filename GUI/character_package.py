"""Cross-platform character package import and export."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from .character_creator import VALID_BRAIN_ID


PACKAGE_VERSION = 1
MANIFEST_NAME = "manifest.json"
BRAIN_ROOT = "brain"
PACKAGE_EXTENSION = ".amadues"
EXCLUDED_DIRS = {"__pycache__"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
EXCLUDED_NAME_PARTS = (".tmp.",)


class CharacterPackageError(ValueError):
    """Raised when a character package cannot be imported or exported."""


@dataclass(frozen=True)
class CharacterPackageResult:
    brain_id: str
    package_path: Path | None = None
    brain_dir: Path | None = None


def build_character_package_filename(brain_id: str, exported_at: datetime | None = None) -> str:
    """Return the default timestamped character package file name."""

    brain_id = _validate_brain_id(brain_id)
    exported_at = exported_at or datetime.now()
    timestamp = f"{exported_at.year}.{exported_at.month}.{exported_at.day}_{exported_at.hour}.{exported_at.minute:02d}"
    return f"{brain_id}_{timestamp}{PACKAGE_EXTENSION}"


def export_character_package(data_dir: Path, brain_id: str, package_path: Path) -> CharacterPackageResult:
    """Write one complete brain directory into a portable package."""

    brain_id = _validate_brain_id(brain_id)
    data_dir = Path(data_dir)
    brain_dir = data_dir / brain_id
    if not brain_dir.is_dir():
        raise CharacterPackageError(f"Character id '{brain_id}' does not exist.")

    package_path = _normalize_package_path(package_path)
    package_path.parent.mkdir(parents=True, exist_ok=True)
    files, directories = _collect_brain_entries(brain_dir)
    manifest = {
        "format": "amadues.character-package",
        "version": PACKAGE_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "brain_id": brain_id,
        "root": BRAIN_ROOT,
        "directories": directories,
        "files": [
            {"path": relative_path, "sha256": _sha256_file(brain_dir / relative_path), "size": (brain_dir / relative_path).stat().st_size}
            for relative_path in files
        ],
    }

    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
        for directory in directories:
            package.writestr(f"{BRAIN_ROOT}/{directory}/", b"")
        for relative_path in files:
            package.write(brain_dir / relative_path, f"{BRAIN_ROOT}/{relative_path}")

    return CharacterPackageResult(brain_id=brain_id, package_path=package_path)


def import_character_package(data_dir: Path, package_path: Path, *, overwrite: bool = True) -> CharacterPackageResult:
    """Import a package by replacing the matching brain directory atomically."""

    data_dir = Path(data_dir)
    package_path = Path(package_path)
    if not package_path.is_file():
        raise CharacterPackageError(f"Package file not found: {package_path}")

    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(package_path, "r") as package:
            _validate_zip_entries(package)
            manifest = _read_manifest(package)
            brain_id = _validate_brain_id(str(manifest.get("brain_id") or ""))
            files = _manifest_files(manifest)
            directories = _manifest_directories(manifest)
            _validate_manifest_matches_package(package, files)

            target_dir = data_dir / brain_id
            if target_dir.exists() and not overwrite:
                raise CharacterPackageError(f"Character id '{brain_id}' already exists.")

            import_root = data_dir / f".importing-{brain_id}-{uuid.uuid4().hex}"
            imported_brain_dir = import_root / brain_id
            backup_dir = data_dir / f".import-backup-{brain_id}-{uuid.uuid4().hex}"
            moved_existing = False
            try:
                imported_brain_dir.mkdir(parents=True)
                for directory in directories:
                    (imported_brain_dir / directory).mkdir(parents=True, exist_ok=True)
                for relative_path, expected_hash in files.items():
                    target_path = imported_brain_dir / relative_path
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    data = package.read(f"{BRAIN_ROOT}/{relative_path}")
                    actual_hash = hashlib.sha256(data).hexdigest()
                    if actual_hash != expected_hash:
                        raise CharacterPackageError(f"Package checksum mismatch: {relative_path}")
                    target_path.write_bytes(data)

                if target_dir.exists():
                    target_dir.rename(backup_dir)
                    moved_existing = True
                imported_brain_dir.rename(target_dir)
                shutil.rmtree(import_root, ignore_errors=True)
                shutil.rmtree(backup_dir, ignore_errors=True)
            except Exception:
                if target_dir.exists() and moved_existing:
                    shutil.rmtree(target_dir, ignore_errors=True)
                if moved_existing and backup_dir.exists():
                    backup_dir.rename(target_dir)
                shutil.rmtree(import_root, ignore_errors=True)
                raise
    except zipfile.BadZipFile as exc:
        raise CharacterPackageError("Character package is not a valid ZIP file.") from exc

    return CharacterPackageResult(brain_id=brain_id, brain_dir=data_dir / brain_id)


def _validate_brain_id(brain_id: str) -> str:
    value = brain_id.strip()
    if not value or not VALID_BRAIN_ID.match(value):
        raise CharacterPackageError("Character package contains an invalid character id.")
    return value


def _normalize_package_path(package_path: Path) -> Path:
    path = Path(package_path)
    if not path.suffix:
        path = path.with_suffix(PACKAGE_EXTENSION)
    return path


def _collect_brain_entries(brain_dir: Path) -> tuple[list[str], list[str]]:
    files: list[str] = []
    directories: set[str] = set()
    for path in sorted(brain_dir.rglob("*")):
        relative_path = path.relative_to(brain_dir).as_posix()
        if _is_excluded(path, relative_path):
            continue
        if path.is_dir():
            directories.add(relative_path)
            continue
        if path.is_file():
            directories.update(parent.as_posix() for parent in PurePosixPath(relative_path).parents if parent.as_posix() != ".")
            files.append(relative_path)
    return files, sorted(directories)


def _is_excluded(path: Path, relative_path: str) -> bool:
    if any(part in EXCLUDED_DIRS for part in path.parts):
        return True
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    return any(part in relative_path for part in EXCLUDED_NAME_PARTS)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_zip_entries(package: zipfile.ZipFile) -> None:
    seen: set[str] = set()
    for info in package.infolist():
        name = info.filename
        if name in seen:
            raise CharacterPackageError(f"Package contains duplicate path: {name}")
        seen.add(name)
        if not _safe_package_path(name):
            raise CharacterPackageError(f"Package contains unsafe path: {name}")
        if name != MANIFEST_NAME and not name.startswith(f"{BRAIN_ROOT}/"):
            raise CharacterPackageError(f"Package contains unexpected path: {name}")


def _safe_package_path(value: str) -> bool:
    if not value or "\\" in value or ":" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts


def _safe_brain_relative_path(value: str) -> str:
    if not value or value.endswith("/") or not _safe_package_path(value):
        raise CharacterPackageError(f"Package manifest contains unsafe path: {value}")
    return value


def _safe_brain_directory(value: str) -> str:
    if not value or value.endswith("/") or not _safe_package_path(value):
        raise CharacterPackageError(f"Package manifest contains unsafe directory: {value}")
    return value


def _read_manifest(package: zipfile.ZipFile) -> dict[str, Any]:
    try:
        data = json.loads(package.read(MANIFEST_NAME).decode("utf-8"))
    except KeyError as exc:
        raise CharacterPackageError("Package is missing manifest.json.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CharacterPackageError("Package manifest is invalid.") from exc
    if (
        not isinstance(data, dict)
        or data.get("format") != "amadues.character-package"
        or data.get("version") != PACKAGE_VERSION
        or data.get("root") != BRAIN_ROOT
    ):
        raise CharacterPackageError("Package manifest version is unsupported.")
    return data


def _manifest_files(manifest: dict[str, Any]) -> dict[str, str]:
    files: dict[str, str] = {}
    for item in manifest.get("files") or []:
        if not isinstance(item, dict):
            raise CharacterPackageError("Package manifest contains an invalid file entry.")
        path = _safe_brain_relative_path(str(item.get("path") or ""))
        sha256 = str(item.get("sha256") or "")
        if len(sha256) != 64 or any(char not in "0123456789abcdef" for char in sha256.lower()):
            raise CharacterPackageError(f"Package manifest contains an invalid checksum: {path}")
        if path in files:
            raise CharacterPackageError(f"Package manifest contains duplicate file: {path}")
        files[path] = sha256.lower()
    return files


def _manifest_directories(manifest: dict[str, Any]) -> list[str]:
    directories: list[str] = []
    seen: set[str] = set()
    for item in manifest.get("directories") or []:
        path = _safe_brain_directory(str(item or ""))
        if path in seen:
            raise CharacterPackageError(f"Package manifest contains duplicate directory: {path}")
        seen.add(path)
        directories.append(path)
    return directories


def _validate_manifest_matches_package(package: zipfile.ZipFile, files: dict[str, str]) -> None:
    expected = {f"{BRAIN_ROOT}/{relative_path}" for relative_path in files}
    actual = {info.filename for info in package.infolist() if not info.is_dir() and info.filename.startswith(f"{BRAIN_ROOT}/")}
    missing = expected - actual
    extra = actual - expected
    if missing:
        raise CharacterPackageError(f"Package is missing file: {sorted(missing)[0]}")
    if extra:
        raise CharacterPackageError(f"Package contains unmanaged file: {sorted(extra)[0]}")
