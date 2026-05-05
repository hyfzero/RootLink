#!/usr/bin/env python3
"""Tests for Flet app storage bootstrap."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

TEST_FILE = Path(__file__).resolve()
SRC_DIR = TEST_FILE.parents[2]
REPO_ROOT = TEST_FILE.parents[3]

for path in (str(REPO_ROOT), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from GUI import app as gui_app
from agent_core.session.path_resolver import PathResolver


class FakeStoragePaths:
    def __init__(self, support_dir: Path | str | None) -> None:
        self.support_dir = support_dir

    async def get_application_support_directory(self) -> str | None:
        return str(self.support_dir) if self.support_dir is not None else None


class FakePage:
    def __init__(self, support_dir: Path | str | None = None) -> None:
        self.storage_paths = FakeStoragePaths(support_dir)
        self.added: list[object] = []

    def add(self, control: object) -> None:
        self.added.append(control)


class FakeView:
    def __init__(self, callback: object, is_dark: bool) -> None:
        self.callback = callback
        self.is_dark = is_dark


class GuiAppStorageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._env_backup = {
            PathResolver.ENV_DATA_DIR: os.environ.get(PathResolver.ENV_DATA_DIR),
            PathResolver.ENV_CONFIG_DIR: os.environ.get(PathResolver.ENV_CONFIG_DIR),
            PathResolver.ENV_FLET_DATA_DIR: os.environ.get(PathResolver.ENV_FLET_DATA_DIR),
            PathResolver.ENV_WINDOWS_LOCAL_APPDATA: os.environ.get(PathResolver.ENV_WINDOWS_LOCAL_APPDATA),
            PathResolver.ENV_WINDOWS_ROAMING_APPDATA: os.environ.get(PathResolver.ENV_WINDOWS_ROAMING_APPDATA),
        }
        for env_name in self._env_backup:
            os.environ.pop(env_name, None)
        PathResolver.clear_app_storage_root()

    def tearDown(self) -> None:
        PathResolver.clear_app_storage_root()
        for env_name, env_value in self._env_backup.items():
            if env_value is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = env_value

    async def test_run_app_configures_storage_before_controller_creation(self) -> None:
        with tempfile.TemporaryDirectory() as app_root:
            created_paths: dict[str, Path] = {}

            class FakeController:
                initial_settings = SimpleNamespace(is_dark=False)

                def __init__(self) -> None:
                    created_paths["data"] = PathResolver.get_data_dir()
                    created_paths["config"] = PathResolver.get_config_dir()

                def bind_view(self, view: object) -> None:
                    created_paths["bound"] = Path("bound")

            with (
                patch.object(gui_app, "AmaduesController", FakeController),
                patch.object(gui_app, "CompanionAppView", FakeView),
            ):
                page = FakePage(app_root)
                await gui_app.run_app(page)

            self.assertEqual(created_paths["data"], Path(app_root) / "data")
            self.assertEqual(created_paths["config"], Path(app_root) / "config")
            self.assertEqual(created_paths["bound"], Path("bound"))
            self.assertFalse((Path(app_root) / "data" / "amadues").exists())
            self.assertTrue((Path(app_root) / "data" / "shinji").exists())
            self.assertEqual(len(page.added), 1)

    async def test_bootstrap_falls_back_to_flet_storage_env(self) -> None:
        with tempfile.TemporaryDirectory() as app_root:
            os.environ[PathResolver.ENV_FLET_DATA_DIR] = app_root

            await gui_app._bootstrap_app_storage(FakePage(None))

            self.assertEqual(PathResolver.get_data_dir(), Path(app_root) / "data")
            self.assertEqual(PathResolver.get_config_dir(), Path(app_root) / "config")

    async def test_run_app_creates_only_default_shinji_on_empty_storage(self) -> None:
        with tempfile.TemporaryDirectory() as app_root:
            with (
                patch.object(gui_app, "AmaduesController") as controller_type,
                patch.object(gui_app, "CompanionAppView", FakeView),
            ):
                controller = controller_type.return_value
                controller.initial_settings = SimpleNamespace(is_dark=True)

                await gui_app.run_app(FakePage(app_root))

            data_root = Path(app_root) / "data"
            self.assertFalse((data_root / "amadues").exists())
            self.assertTrue((data_root / "shinji" / "persona" / "profile.json").exists())
            self.assertTrue((data_root / "shinji" / "ui.json").exists())

    async def test_configure_bundled_flet_view_path_uses_packaged_client(self) -> None:
        with tempfile.TemporaryDirectory() as bundle_root:
            view_dir = Path(bundle_root) / "flet_desktop" / "app" / "flet"
            view_dir.mkdir(parents=True)
            view_path = view_dir / "flet.exe"
            view_path.write_bytes(b"exe")
            (view_dir / "zlib.dll").write_bytes(b"VCRUNTIME140D.dll ucrtbased.dll")

            previous_view_path = os.environ.get("FLET_VIEW_PATH")
            os.environ.pop("FLET_VIEW_PATH", None)
            try:
                with (
                    patch.object(gui_app.sys, "_MEIPASS", bundle_root, create=True),
                    patch.object(gui_app.os, "name", "nt"),
                ):
                    gui_app._configure_bundled_flet_view_path()

                self.assertEqual(os.environ["FLET_VIEW_PATH"], str(view_dir))
                self.assertFalse((view_dir / "zlib.dll").exists())
            finally:
                if previous_view_path is None:
                    os.environ.pop("FLET_VIEW_PATH", None)
                else:
                    os.environ["FLET_VIEW_PATH"] = previous_view_path


if __name__ == "__main__":
    unittest.main()
