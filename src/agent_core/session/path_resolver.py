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
        """初始化路径解析器。

        Args:
            base_path: 项目根目录，不指定时自动查找
        """
        self._base_path = base_path or self._find_project_root()

    @classmethod
    def _find_project_root(cls) -> Path:
        """自动查找项目根目录。

        向上查找 Python 项目标记文件。
        """
        current = Path.cwd()

        # 向上查找项目标记文件
        markers = ["pyproject.toml", "setup.py", ".git"]
        for parent in [current] + list(current.parents):
            for marker in markers:
                if (parent / marker).exists():
                    return parent

        # 没找到则使用当前目录
        return current

    @classmethod
    def get_project_root(cls) -> Path:
        """获取项目根目录（向上查找 pyproject.toml / setup.py / .git）"""
        return cls()._base_path

    @classmethod
    def _env_path(cls, env_name: str) -> Optional[Path]:
        env_path = os.environ.get(env_name)
        if not env_path:
            return None
        return Path(env_path).expanduser()

    @classmethod
    def _windows_data_dir(cls) -> Optional[Path]:
        if os.name != "nt":
            return None

        appdata_root = cls._env_path(cls.ENV_WINDOWS_LOCAL_APPDATA)
        if appdata_root is None:
            appdata_root = cls._env_path(cls.ENV_WINDOWS_ROAMING_APPDATA)
        if appdata_root is None:
            return None

        return appdata_root / cls.APP_DIR_NAME / cls.DEFAULT_DATA_RELATIVE

    @classmethod
    def get_data_dir(cls) -> Path:
        """获取数据目录。

        优先级: AGENT_DATA_DIR > FLET_APP_STORAGE_DATA > Windows AppData > 项目根/data
        """
        if data_dir := cls._env_path(cls.ENV_DATA_DIR):
            return data_dir

        if flet_data_dir := cls._env_path(cls.ENV_FLET_DATA_DIR):
            return flet_data_dir

        if windows_data_dir := cls._windows_data_dir():
            return windows_data_dir

        base = cls()._base_path
        data_dir = base / cls.DEFAULT_DATA_RELATIVE
        return data_dir

    @classmethod
    def get_config_dir(cls) -> Path:
        """获取配置目录。

        优先级: 环境变量 > 项目根/config > ./config
        """
        if config_dir := cls._env_path(cls.ENV_CONFIG_DIR):
            return config_dir

        base = cls()._base_path
        config_dir = base / cls.DEFAULT_CONFIG_RELATIVE
        return config_dir

    @classmethod
    def get_brain_dir(cls, brain_id: str = "default") -> Path:
        """Brain 模块数据目录: {data_dir}/{brain_id}/"""
        return cls.get_data_dir() / brain_id

    @classmethod
    def get_session_dir(cls, brain_id: str = "default") -> Path:
        """Session 数据目录: {data_dir}/{brain_id}/session/"""
        return cls.get_data_dir() / brain_id / "session"

    @classmethod
    def get_tags_dir(cls, brain_id: str = "default") -> Path:
        """标签目录: {data_dir}/{brain_id}/tags/"""
        return cls.get_data_dir() / brain_id / "tags"

    @classmethod
    def resolve(cls, relative_path: str) -> Path:
        """解析相对路径到绝对路径。

        Args:
            relative_path: 相对路径

        Returns:
            绝对路径
        """
        base = cls()._base_path
        return base / relative_path

    @classmethod
    def ensure_dir(cls, path: Path) -> Path:
        """确保目录存在，不存在则创建。

        Args:
            path: 目录路径

        Returns:
            目录路径
        """
        path.mkdir(parents=True, exist_ok=True)
        return path
