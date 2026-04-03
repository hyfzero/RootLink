"""Session Manager 模块 - 三端路径兼容解析器。

提供跨平台（Windows/Linux/Mac）的路径解析支持。
"""

from pathlib import Path
from typing import Optional
import os


class PathResolver:
    """三端路径解析器。

    优先使用环境变量，支持相对路径解析。
    """

    # 环境变量配置项
    ENV_DATA_DIR = "AGENT_DATA_DIR"
    ENV_CONFIG_DIR = "AGENT_CONFIG_DIR"

    # 默认相对路径（相对于项目根目录）
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

        向上查找 pyproject.toml 或 project.godot 文件。
        """
        current = Path.cwd()

        # 向上查找项目标记文件
        markers = ["pyproject.toml", "project.godot", "setup.py", ".git"]
        for parent in [current] + list(current.parents):
            for marker in markers:
                if (parent / marker).exists():
                    return parent

        # 没找到则使用当前目录
        return current

    @classmethod
    def get_project_root(cls) -> Path:
        """获取项目根目录（向上查找 pyproject.toml / project.godot）"""
        return cls()._base_path

    @classmethod
    def get_data_dir(cls) -> Path:
        """获取数据目录。

        优先级: 环境变量 > 项目根/data > ./data
        """
        if env_path := os.environ.get(cls.ENV_DATA_DIR):
            return Path(env_path)

        base = cls()._base_path
        data_dir = base / cls.DEFAULT_DATA_RELATIVE
        return data_dir

    @classmethod
    def get_config_dir(cls) -> Path:
        """获取配置目录。

        优先级: 环境变量 > 项目根/config > ./config
        """
        if env_path := os.environ.get(cls.ENV_CONFIG_DIR):
            return Path(env_path)

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
