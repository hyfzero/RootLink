"""Session Manager 模块 - 配置管理。

提供 SessionManager 的配置定义。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..api.adapter import ModelConfig


@dataclass
class SessionConfig:
    """Session Manager 配置"""

    # 存储限制
    max_messages_per_day: int = 500       # 单日最大消息数
    max_tokens_per_day: int = 50000       # 单日最大 Token（近似）
    archive_retention_days: int = 30       # 归档保留天数

    # 摘要生成
    min_messages_for_summary: int = 4     # 触发摘要的最少消息数

    # 模型配置（从 config/agent_config.json 读取）
    model_config: Optional[ModelConfig] = None

    # 路径配置（留空使用默认）
    data_dir: Optional[str] = None
    brain_dir: Optional[str] = None

    # 存储格式
    use_msgpack: bool = False             # 大数据量时启用

    # Compact 策略
    compact_keep_min: int = 50            # Compact 最少保留消息数
    compact_keep_max: int = 100           # Compact 最多保留消息数

    def get_effective_data_dir(self) -> Path:
        """获取有效的数据目录"""
        if self.data_dir:
            return Path(self.data_dir)
        from .path_resolver import PathResolver
        return PathResolver.get_data_dir()

    def get_effective_brain_dir(self, brain_id: str = "default") -> Path:
        """获取有效的 Brain 目录"""
        if self.brain_dir:
            return Path(self.brain_dir) / brain_id
        from .path_resolver import PathResolver
        return PathResolver.get_brain_dir(brain_id)

    def calculate_keep_count(self, avg_token_per_message: int) -> int:
        """动态计算保留条数，确保不超出 Token 上限。

        Args:
            avg_token_per_message: 平均每条消息的 Token 数

        Returns:
            保留的消息条数（50-100 之间）
        """
        min_token = max(avg_token_per_message, 50)
        max_messages = self.max_tokens_per_day // min_token
        return max(self.compact_keep_min, min(self.compact_keep_max, max_messages))

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "max_messages_per_day": self.max_messages_per_day,
            "max_tokens_per_day": self.max_tokens_per_day,
            "archive_retention_days": self.archive_retention_days,
            "min_messages_for_summary": self.min_messages_for_summary,
            "use_msgpack": self.use_msgpack,
            "compact_keep_min": self.compact_keep_min,
            "compact_keep_max": self.compact_keep_max,
            "data_dir": self.data_dir,
            "brain_dir": self.brain_dir,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionConfig":
        """从字典创建"""
        return cls(
            max_messages_per_day=data.get("max_messages_per_day", 500),
            max_tokens_per_day=data.get("max_tokens_per_day", 50000),
            archive_retention_days=data.get("archive_retention_days", 30),
            min_messages_for_summary=data.get("min_messages_for_summary", 4),
            use_msgpack=data.get("use_msgpack", False),
            compact_keep_min=data.get("compact_keep_min", 50),
            compact_keep_max=data.get("compact_keep_max", 100),
            data_dir=data.get("data_dir"),
            brain_dir=data.get("brain_dir"),
        )
