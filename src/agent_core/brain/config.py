"""Agent Core 核心层 - 配置管理模块。

提供Agent的基础配置管理，包括历史记录配置、标签配置、存储配置等。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class HistoryConfig:
    """历史消息管理配置。"""

    max_context_tokens: int = 4000  # 最大上下文Token数
    daily_queue_threshold: int = 100  # 触发队列插入的消息数量阈值
    importance_threshold: float = 0.5  # 重要性阈值
    retention_days: int = 30  # 历史消息保留天数
    summary_trigger_messages: int = 50  # 触发生成摘要的消息数量
    token_reserved: int = 1000  # 为系统提示等保留的Token数量


@dataclass
class TagsConfig:
    """回复标签配置。"""

    auto_generate: bool = True  # 是否自动生成标签
    emotion_model: str = "keyword"  # 情感识别模式: "keyword" 或 "llm"
    default_emotion: str = "neutral"  # 默认情感
    default_expression: str = "neutral"  # 默认表情


@dataclass
class StorageConfig:
    """存储配置。"""

    data_dir: str = "./data"  # 数据存储根目录
    format: str = "json"  # 存储格式: "json" 或 "md"

    @property
    def data_path(self) -> Path:
        """获取数据目录路径。"""
        return Path(self.data_dir)


@dataclass
class PersonaConfig:
    """人格基础配置。"""

    name: str = "Assistant"  # 角色名称
    age: Optional[int] = None  # 年龄
    gender: str = "unknown"  # 性别


@dataclass
class AgentConfig:
    """Agent主配置类。"""

    persona: PersonaConfig = field(default_factory=PersonaConfig)
    history: HistoryConfig = field(default_factory=HistoryConfig)
    tags: TagsConfig = field(default_factory=TagsConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)

    def __post_init__(self):
        """将字典类型的输入转换为正确的 dataclass 类型。"""
        if isinstance(self.persona, dict):
            self.persona = PersonaConfig(**self.persona)
        if isinstance(self.history, dict):
            self.history = HistoryConfig(**self.history)
        if isinstance(self.tags, dict):
            self.tags = TagsConfig(**self.tags)
        if isinstance(self.storage, dict):
            self.storage = StorageConfig(**self.storage)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentConfig":
        """从字典创建配置对象。

        Args:
            data: 配置字典

        Returns:
            AgentConfig实例
        """
        persona_data = data.get("persona", {})
        history_data = data.get("history", {})
        tags_data = data.get("tags", {})
        storage_data = data.get("storage", {})

        return cls(
            persona=PersonaConfig(**persona_data),
            history=HistoryConfig(**history_data),
            tags=TagsConfig(**tags_data),
            storage=StorageConfig(**storage_data),
        )

    def to_dict(self) -> dict:
        """将配置对象转换为字典。

        Returns:
            配置字典
        """
        return {
            "persona": {
                "name": self.persona.name,
                "age": self.persona.age,
                "gender": self.persona.gender,
            },
            "history": {
                "max_context_tokens": self.history.max_context_tokens,
                "daily_queue_threshold": self.history.daily_queue_threshold,
                "importance_threshold": self.history.importance_threshold,
                "retention_days": self.history.retention_days,
                "summary_trigger_messages": self.history.summary_trigger_messages,
                "token_reserved": self.history.token_reserved,
            },
            "tags": {
                "auto_generate": self.tags.auto_generate,
                "emotion_model": self.tags.emotion_model,
                "default_emotion": self.tags.default_emotion,
                "default_expression": self.tags.default_expression,
            },
            "storage": {
                "data_dir": self.storage.data_dir,
                "format": self.storage.format,
            },
        }
