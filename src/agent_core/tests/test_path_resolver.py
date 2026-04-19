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

    def tearDown(self) -> None:
        os.chdir(self._old_cwd)
        for env_name, env_value in self._old_env.items():
            if env_value is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = env_value

    def test_agent_data_dir_overrides_flet_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as agent_dir, tempfile.TemporaryDirectory() as flet_dir:
            os.environ[PathResolver.ENV_DATA_DIR] = agent_dir
            os.environ[PathResolver.ENV_FLET_DATA_DIR] = flet_dir

            self.assertEqual(PathResolver.get_data_dir(), Path(agent_dir))

    def test_flet_data_dir_is_used_when_agent_data_dir_is_unset(self) -> None:
        with tempfile.TemporaryDirectory() as flet_dir:
            os.environ[PathResolver.ENV_FLET_DATA_DIR] = flet_dir

            self.assertEqual(PathResolver.get_data_dir(), Path(flet_dir))

    def test_data_dir_falls_back_to_project_data_dir(self) -> None:
        self.assertEqual(PathResolver.get_data_dir(), self._repo_root / "data")

    @unittest.skipUnless(os.name == "nt", "Windows app data fallback is Windows-only")
    def test_windows_local_appdata_is_used_before_project_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as appdata_dir:
            os.environ[PathResolver.ENV_WINDOWS_LOCAL_APPDATA] = appdata_dir

            self.assertEqual(
                PathResolver.get_data_dir(),
                Path(appdata_dir) / PathResolver.APP_DIR_NAME / "data",
            )

    def test_brain_dir_appends_brain_id_to_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as flet_dir:
            os.environ[PathResolver.ENV_FLET_DATA_DIR] = flet_dir

            self.assertEqual(PathResolver.get_brain_dir("amadues"), Path(flet_dir) / "amadues")


if __name__ == "__main__":
    unittest.main()
