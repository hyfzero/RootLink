"""Session Manager module path resolver.

Resolves project paths for local development and persistent app data paths
for packaged Flet apps on Windows, Android, and iOS.
"""

from pathlib import Path
from typing import Optional
import os
import shutil


class PathResolver:
    """Resolve project and persistent data paths.

    Data directory priority:
    AGENT_DATA_DIR > configured app storage root/data >
    FLET_APP_STORAGE_DATA/data > Windows app data > project_root/data.

    Config directory priority:
    AGENT_CONFIG_DIR > configured app storage root/config >
    FLET_APP_STORAGE_DATA/config > Windows app data/amadues/config > project_root/config.
    """

    ENV_DATA_DIR = "AGENT_DATA_DIR"
    ENV_CONFIG_DIR = "AGENT_CONFIG_DIR"
    ENV_FLET_DATA_DIR = "FLET_APP_STORAGE_DATA"
    ENV_WINDOWS_LOCAL_APPDATA = "LOCALAPPDATA"
    ENV_WINDOWS_ROAMING_APPDATA = "APPDATA"

    APP_DIR_NAME = "amadues"
    DEFAULT_DATA_RELATIVE = "data"
    DEFAULT_CONFIG_RELATIVE = "config"
    MIGRATION_MARKER = ".amadues_storage_migration_v1"
    _app_storage_root: Optional[Path] = None

    def __init__(self, base_path: Optional[Path] = None):
        self._base_path = base_path or self._find_project_root()

    @classmethod
    def configure_app_storage_root(cls, root: Path | str) -> None:
        """Set the runtime app storage root resolved by the GUI bootstrap."""
        cls._app_storage_root = Path(root).expanduser()

    @classmethod
    def clear_app_storage_root(cls) -> None:
        """Clear runtime app storage root; intended for tests and diagnostics."""
        cls._app_storage_root = None

    @classmethod
    def get_app_storage_root(cls) -> Optional[Path]:
        if cls._app_storage_root is not None:
            return cls._app_storage_root
        return cls._env_path(cls.ENV_FLET_DATA_DIR)

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
    def _windows_packaged_app_dirs(cls, appdata_root: Path) -> list[Path]:
        packages_dir = appdata_root / "Packages"
        if not packages_dir.exists():
            return []

        return sorted(
            packages_dir.glob("PythonSoftwareFoundation.Python.*_*/LocalCache/Local/" + cls.APP_DIR_NAME)
        )

    @classmethod
    def legacy_app_storage_roots(cls) -> list[Path]:
        """Return existing legacy roots that may contain data/config to migrate."""
        if os.name != "nt":
            return []

        appdata_root = cls._env_path(cls.ENV_WINDOWS_LOCAL_APPDATA)
        if appdata_root is None:
            appdata_root = cls._env_path(cls.ENV_WINDOWS_ROAMING_APPDATA)
        if appdata_root is None:
            return []

        candidates = cls._windows_packaged_app_dirs(appdata_root)
        candidates.append(appdata_root / cls.APP_DIR_NAME)

        roots: list[Path] = []
        for candidate in candidates:
            if (candidate / cls.DEFAULT_DATA_RELATIVE).exists() or (candidate / cls.DEFAULT_CONFIG_RELATIVE).exists():
                roots.append(candidate)
        return roots

    @classmethod
    def migrate_legacy_app_storage(cls, target_root: Path | str) -> None:
        """Copy missing data/config files from legacy roots without deleting sources."""
        target = Path(target_root).expanduser()
        marker = target / cls.MIGRATION_MARKER
        if marker.exists():
            return

        target.mkdir(parents=True, exist_ok=True)
        target_resolved = target.resolve()
        for source in cls.legacy_app_storage_roots():
            try:
                if source.resolve() == target_resolved:
                    continue
            except OSError:
                continue

            for child_name in (cls.DEFAULT_DATA_RELATIVE, cls.DEFAULT_CONFIG_RELATIVE):
                cls._copy_missing_tree(source / child_name, target / child_name)

        marker.write_text("ok\n", encoding="utf-8")

    @classmethod
    def _copy_missing_tree(cls, source: Path, target: Path) -> None:
        if not source.exists():
            return
        if source.is_file():
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            return

        for item in source.rglob("*"):
            relative = item.relative_to(source)
            destination = target / relative
            if item.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            elif item.is_file() and not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, destination)

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

        if app_storage_root := cls.get_app_storage_root():
            return app_storage_root / cls.DEFAULT_DATA_RELATIVE

        if windows_data_dir := cls._windows_data_dir():
            return windows_data_dir

        return cls()._base_path / cls.DEFAULT_DATA_RELATIVE

    @classmethod
    def get_config_dir(cls) -> Path:
        if config_dir := cls._env_path(cls.ENV_CONFIG_DIR):
            return config_dir

        if app_storage_root := cls.get_app_storage_root():
            return app_storage_root / cls.DEFAULT_CONFIG_RELATIVE

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
