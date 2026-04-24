"""Session Manager module path resolver.

Resolves project paths for local development and persistent app data paths
for packaged Flet apps on Windows, Android, and iOS.
"""

from pathlib import Path
from typing import Optional
import os


class PathResolver:
    """Resolve project and persistent data paths.

    Data directory priority:
    AGENT_DATA_DIR > FLET_APP_STORAGE_DATA > Windows app data > project_root/data.

    Config directory priority:
    AGENT_CONFIG_DIR > FLET_APP_STORAGE_DATA/config >
    Windows app data/amadues/config > project_root/config.
    """

    ENV_DATA_DIR = "AGENT_DATA_DIR"
    ENV_CONFIG_DIR = "AGENT_CONFIG_DIR"
    ENV_FLET_DATA_DIR = "FLET_APP_STORAGE_DATA"
    ENV_WINDOWS_LOCAL_APPDATA = "LOCALAPPDATA"
    ENV_WINDOWS_ROAMING_APPDATA = "APPDATA"

    APP_DIR_NAME = "amadues"
    DEFAULT_DATA_RELATIVE = "data"
    DEFAULT_CONFIG_RELATIVE = "config"

    def __init__(self, base_path: Optional[Path] = None):
        self._base_path = base_path or self._find_project_root()

    @classmethod
    def _find_project_root(cls) -> Path:
        current = Path.cwd()

        markers = ["pyproject.toml", "setup.py", ".git"]
        for parent in [current] + list(current.parents):
            for marker in markers:
                if (parent / marker).exists():
                    return parent

        return current

    @classmethod
    def get_project_root(cls) -> Path:
        return cls()._base_path

    @classmethod
    def _env_path(cls, env_name: str) -> Optional[Path]:
        env_path = os.environ.get(env_name)
        if not env_path:
            return None
        return Path(env_path).expanduser()

    @classmethod
    def _windows_app_dir(cls) -> Optional[Path]:
        if os.name != "nt":
            return None

        appdata_root = cls._env_path(cls.ENV_WINDOWS_LOCAL_APPDATA)
        if appdata_root is None:
            appdata_root = cls._env_path(cls.ENV_WINDOWS_ROAMING_APPDATA)
        if appdata_root is None:
            return None

        return appdata_root / cls.APP_DIR_NAME

    @classmethod
    def _windows_data_dir(cls) -> Optional[Path]:
        app_dir = cls._windows_app_dir()
        if app_dir is None:
            return None
        return app_dir / cls.DEFAULT_DATA_RELATIVE

    @classmethod
    def _windows_config_dir(cls) -> Optional[Path]:
        app_dir = cls._windows_app_dir()
        if app_dir is None:
            return None
        return app_dir / cls.DEFAULT_CONFIG_RELATIVE

    @classmethod
    def get_data_dir(cls) -> Path:
        if data_dir := cls._env_path(cls.ENV_DATA_DIR):
            return data_dir

        if flet_data_dir := cls._env_path(cls.ENV_FLET_DATA_DIR):
            return flet_data_dir

        if windows_data_dir := cls._windows_data_dir():
            return windows_data_dir

        return cls()._base_path / cls.DEFAULT_DATA_RELATIVE

    @classmethod
    def get_config_dir(cls) -> Path:
        if config_dir := cls._env_path(cls.ENV_CONFIG_DIR):
            return config_dir

        if flet_data_dir := cls._env_path(cls.ENV_FLET_DATA_DIR):
            return flet_data_dir / cls.DEFAULT_CONFIG_RELATIVE

        if windows_config_dir := cls._windows_config_dir():
            return windows_config_dir

        return cls()._base_path / cls.DEFAULT_CONFIG_RELATIVE

    @classmethod
    def get_brain_dir(cls, brain_id: str = "default") -> Path:
        return cls.get_data_dir() / brain_id

    @classmethod
    def get_session_dir(cls, brain_id: str = "default") -> Path:
        return cls.get_data_dir() / brain_id / "session"

    @classmethod
    def get_tags_dir(cls, brain_id: str = "default") -> Path:
        return cls.get_data_dir() / brain_id / "tags"

    @classmethod
    def resolve(cls, relative_path: str) -> Path:
        return cls()._base_path / relative_path

    @classmethod
    def ensure_dir(cls, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        return path
