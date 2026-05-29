#!/usr/bin/env python3
"""Tests for portable character packages."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
import warnings
import zipfile
from datetime import datetime
from pathlib import Path

TEST_FILE = Path(__file__).resolve()
SRC_DIR = TEST_FILE.parents[2]
REPO_ROOT = TEST_FILE.parents[3]

for path in (str(REPO_ROOT), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from GUI.character_creator import CharacterCreator
from GUI.character_package import CharacterPackageError, build_character_package_filename, export_character_package, import_character_package
from GUI.interfaces import CharacterDraft


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _file_hashes(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): _sha256(path) for path in sorted(root.rglob("*")) if path.is_file()}


class CharacterPackageTests(unittest.TestCase):
    def test_build_character_package_filename_adds_export_datetime(self) -> None:
        filename = build_character_package_filename("key", datetime(2026, 5, 26, 21, 4))

        self.assertEqual(filename, "key_2026.5.26_21.04.amadues")

    def test_export_import_restores_complete_brain_files(self) -> None:
        with tempfile.TemporaryDirectory() as source_root, tempfile.TemporaryDirectory() as target_root, tempfile.TemporaryDirectory() as assets_root:
            image_path = Path(assets_root) / "avatar.png"
            image_path.write_bytes(b"image-bytes")
            source_data = Path(source_root)
            result = CharacterCreator(source_data).create(
                CharacterDraft(
                    brain_id="portable",
                    name="Portable",
                    avatar_path=str(image_path),
                    portraits={"neutral": str(image_path), "happy": str(image_path)},
                )
            )
            brain_dir = result.brain_dir
            (brain_dir / "session" / "current" / "2026-05-04.json").write_text(json.dumps({"messages": ["hello"]}), encoding="utf-8")
            (brain_dir / "history" / "daily" / "2026-05-04.json").write_text(json.dumps({"summary": "day"}), encoding="utf-8")
            (brain_dir / "tags" / "extra.json").write_text(json.dumps({"tag": "value"}), encoding="utf-8")
            (brain_dir / "__pycache__").mkdir()
            (brain_dir / "__pycache__" / "ignored.pyc").write_bytes(b"cache")
            (brain_dir / "assets" / "preview.tmp.123.png").write_bytes(b"temporary")

            package_path = Path(target_root) / "portable.amadues"
            export_character_package(source_data, "portable", package_path)
            imported = import_character_package(Path(target_root), package_path)

            with zipfile.ZipFile(package_path, "r") as package:
                names = set(package.namelist())
                self.assertIn("manifest.json", names)
                self.assertIn("brain/persona/profile.json", names)
                self.assertIn("brain/assets/avatar.png", names)
                self.assertIn("brain/assets/portraits/neutral.png", names)
                self.assertIn("brain/history/history.json", names)
                self.assertIn("brain/session/current/2026-05-04.json", names)
                self.assertNotIn("brain/__pycache__/ignored.pyc", names)
                self.assertNotIn("brain/assets/preview.tmp.123.png", names)

            expected = _file_hashes(brain_dir)
            expected.pop("__pycache__/ignored.pyc")
            expected.pop("assets/preview.tmp.123.png")
            self.assertEqual(imported.brain_id, "portable")
            self.assertEqual(_file_hashes(Path(target_root) / "portable"), expected)

    def test_import_overwrites_existing_id_and_rejects_invalid_package_without_destroying_target(self) -> None:
        with tempfile.TemporaryDirectory() as source_root, tempfile.TemporaryDirectory() as target_root:
            source_data = Path(source_root)
            target_data = Path(target_root)
            CharacterCreator(source_data).create(CharacterDraft(brain_id="same_id", name="Source"))
            CharacterCreator(target_data).create(CharacterDraft(brain_id="same_id", name="Target"))
            package_path = target_data / "same_id.amadues"
            export_character_package(source_data, "same_id", package_path)

            import_character_package(target_data, package_path)
            profile = json.loads((target_data / "same_id" / "persona" / "profile.json").read_text(encoding="utf-8"))
            self.assertEqual(profile["name"], "Source")

            bad_package = target_data / "bad.amadues"
            with zipfile.ZipFile(bad_package, "w") as package:
                package.writestr(
                    "manifest.json",
                    json.dumps(
                        {
                            "format": "amadues.character-package",
                            "version": 1,
                            "brain_id": "same_id",
                            "root": "brain",
                            "directories": [],
                            "files": [{"path": "persona/profile.json", "sha256": "0" * 64}],
                        }
                    ),
                )
                package.writestr("brain/persona/profile.json", b"not-the-hash")

            with self.assertRaises(CharacterPackageError):
                import_character_package(target_data, bad_package)
            profile = json.loads((target_data / "same_id" / "persona" / "profile.json").read_text(encoding="utf-8"))
            self.assertEqual(profile["name"], "Source")

    def test_import_rejects_unsafe_and_duplicate_paths(self) -> None:
        with tempfile.TemporaryDirectory() as data_root:
            data_dir = Path(data_root)
            unsafe_package = data_dir / "unsafe.amadues"
            with zipfile.ZipFile(unsafe_package, "w") as package:
                package.writestr("manifest.json", "{}")
                package.writestr("../escape.txt", "bad")
            with self.assertRaises(CharacterPackageError):
                import_character_package(data_dir, unsafe_package)

            duplicate_package = data_dir / "duplicate.amadues"
            with zipfile.ZipFile(duplicate_package, "w") as package:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    package.writestr("manifest.json", "{}")
                    package.writestr("manifest.json", "{}")
            with self.assertRaises(CharacterPackageError):
                import_character_package(data_dir, duplicate_package)


if __name__ == "__main__":
    unittest.main()
