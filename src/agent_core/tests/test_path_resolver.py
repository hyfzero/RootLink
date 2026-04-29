#!/usr/bin/env python3
"""Regression tests for session path resolution."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_core.session.path_resolver import PathResolver


class PathResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self._repo_root = Path(__file__).resolve().parents[3]
        self._old_cwd = Path.cwd()
        self._old_env = {
            PathResolver.ENV_DATA_DIR: os.environ.get(PathResolver.ENV_DATA_DIR),
            PathResolver.ENV_FLET_DATA_DIR: os.environ.get(PathResolver.ENV_FLET_DATA_DIR),
            PathResolver.ENV_CONFIG_DIR: os.environ.get(PathResolver.ENV_CONFIG_DIR),
            PathResolver.ENV_WINDOWS_LOCAL_APPDATA: os.environ.get(PathResolver.ENV_WINDOWS_LOCAL_APPDATA),
            PathResolver.ENV_WINDOWS_ROAMING_APPDATA: os.environ.get(PathResolver.ENV_WINDOWS_ROAMING_APPDATA),
        }
        os.chdir(self._repo_root)
        for env_name in self._old_env:
            os.environ.pop(env_name, None)
        PathResolver.clear_app_storage_root()

    def tearDown(self) -> None:
        os.chdir(self._old_cwd)
        PathResolver.clear_app_storage_root()
        for env_name, env_value in self._old_env.items():
            if env_value is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = env_value

    def test_agent_data_dir_overrides_app_storage_root(self) -> None:
        with tempfile.TemporaryDirectory() as agent_dir, tempfile.TemporaryDirectory() as flet_dir:
            os.environ[PathResolver.ENV_DATA_DIR] = agent_dir
            PathResolver.configure_app_storage_root(flet_dir)

            self.assertEqual(PathResolver.get_data_dir(), Path(agent_dir))

    def test_configured_app_storage_root_maps_to_data_and_config(self) -> None:
        with tempfile.TemporaryDirectory() as app_root:
            PathResolver.configure_app_storage_root(app_root)

            self.assertEqual(PathResolver.get_data_dir(), Path(app_root) / "data")
            self.assertEqual(PathResolver.get_config_dir(), Path(app_root) / "config")

    def test_flet_data_dir_is_app_storage_root_when_agent_data_dir_is_unset(self) -> None:
        with tempfile.TemporaryDirectory() as flet_dir:
            os.environ[PathResolver.ENV_FLET_DATA_DIR] = flet_dir

            self.assertEqual(PathResolver.get_data_dir(), Path(flet_dir) / "data")
            self.assertEqual(PathResolver.get_config_dir(), Path(flet_dir) / "config")

    def test_data_dir_falls_back_to_project_data_dir(self) -> None:
        self.assertEqual(PathResolver.get_data_dir(), self._repo_root / "data")

    def test_agent_config_dir_overrides_other_config_locations(self) -> None:
        with tempfile.TemporaryDirectory() as config_dir, tempfile.TemporaryDirectory() as flet_dir:
            os.environ[PathResolver.ENV_CONFIG_DIR] = config_dir
            os.environ[PathResolver.ENV_FLET_DATA_DIR] = flet_dir

            self.assertEqual(PathResolver.get_config_dir(), Path(config_dir))

    def test_flet_data_dir_maps_to_config_subdirectory(self) -> None:
        with tempfile.TemporaryDirectory() as flet_dir:
            os.environ[PathResolver.ENV_FLET_DATA_DIR] = flet_dir

            self.assertEqual(
                PathResolver.get_config_dir(),
                Path(flet_dir) / PathResolver.DEFAULT_CONFIG_RELATIVE,
            )

    def test_config_dir_falls_back_to_project_config_dir(self) -> None:
        self.assertEqual(PathResolver.get_config_dir(), self._repo_root / "config")

    @unittest.skipUnless(os.name == "nt", "Windows app data fallback is Windows-only")
    def test_windows_local_appdata_is_used_before_project_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as appdata_dir:
            os.environ[PathResolver.ENV_WINDOWS_LOCAL_APPDATA] = appdata_dir

            self.assertEqual(
                PathResolver.get_data_dir(),
                Path(appdata_dir) / PathResolver.APP_DIR_NAME / "data",
            )

    @unittest.skipUnless(os.name == "nt", "Windows app data fallback is Windows-only")
    def test_existing_windows_package_appdata_is_legacy_source_only(self) -> None:
        with tempfile.TemporaryDirectory() as appdata_dir:
            os.environ[PathResolver.ENV_WINDOWS_LOCAL_APPDATA] = appdata_dir
            packaged_dir = (
                Path(appdata_dir)
                / "Packages"
                / "PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0"
                / "LocalCache"
                / "Local"
                / PathResolver.APP_DIR_NAME
            )
            (packaged_dir / "data").mkdir(parents=True)

            self.assertEqual(
                PathResolver.get_data_dir(),
                Path(appdata_dir) / PathResolver.APP_DIR_NAME / "data",
            )
            self.assertIn(packaged_dir, PathResolver.legacy_app_storage_roots())

    @unittest.skipUnless(os.name == "nt", "Windows app data fallback is Windows-only")
    def test_legacy_storage_migration_copies_missing_files_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as appdata_dir, tempfile.TemporaryDirectory() as target_dir:
            os.environ[PathResolver.ENV_WINDOWS_LOCAL_APPDATA] = appdata_dir
            legacy_root = Path(appdata_dir) / PathResolver.APP_DIR_NAME
            legacy_avatar = legacy_root / "data" / "amadues" / "assets" / "avatar.png"
            legacy_models = legacy_root / "config" / "models.json"
            legacy_avatar.parent.mkdir(parents=True)
            legacy_models.parent.mkdir(parents=True)
            legacy_avatar.write_bytes(b"legacy-avatar")
            legacy_models.write_text("legacy-models", encoding="utf-8")

            target_root = Path(target_dir)
            existing_models = target_root / "config" / "models.json"
            existing_models.parent.mkdir(parents=True)
            existing_models.write_text("new-models", encoding="utf-8")

            PathResolver.migrate_legacy_app_storage(target_root)

            self.assertEqual((target_root / "data" / "amadues" / "assets" / "avatar.png").read_bytes(), b"legacy-avatar")
            self.assertEqual(existing_models.read_text(encoding="utf-8"), "new-models")
            self.assertTrue(legacy_avatar.exists())
            self.assertTrue((target_root / PathResolver.MIGRATION_MARKER).exists())

    @unittest.skipUnless(os.name == "nt", "Windows app data fallback is Windows-only")
    def test_windows_local_appdata_is_used_before_project_config_dir(self) -> None:
        with tempfile.TemporaryDirectory() as appdata_dir:
            os.environ[PathResolver.ENV_WINDOWS_LOCAL_APPDATA] = appdata_dir

            self.assertEqual(
                PathResolver.get_config_dir(),
                Path(appdata_dir) / PathResolver.APP_DIR_NAME / "config",
            )

    def test_brain_dir_appends_brain_id_to_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as flet_dir:
            os.environ[PathResolver.ENV_FLET_DATA_DIR] = flet_dir

            self.assertEqual(PathResolver.get_brain_dir("amadues"), Path(flet_dir) / "data" / "amadues")


if __name__ == "__main__":
    unittest.main()
