"""Agent Core Brain 模块 - Agent人格、历史、配置管理。

提供：
- persona: 角色人格和记忆管理
- history: 历史消息和Token感知权重管理
- tags: 回复表情/动作标签生成
- config: 配置管理
- persistence: JSON/Markdown文件持久化
- prompt_builder: 分段式Prompt构建
"""

from .persona import Persona, PersonaProfile, MemoryEntry
from .history import (
    MessageHistory,
    MessageQueue,
    DailyHistory,
    DailySummary,
    Message,
    MessageRole,
    calculate_message_weight,
    estimate_tokens,
)
from .tags import ReplyTag, TagGenerator, TagCache
from .config import AgentConfig, HistoryConfig, TagsConfig, StorageConfig, PersonaConfig
from .persistence import AgentStorage, PersonaStorage, HistoryStorage, TagsStorage, ConfigStorage
from .prompt_builder import (
    PromptBuilder,
    build_minimal_prompt,
    build_full_conversation_prompt,
    build_memory_flush_prompt,
)

__all__ = [
    # 人格模块
    "Persona",
    "PersonaProfile",
    "MemoryEntry",
    # 历史消息模块
    "MessageHistory",
    "MessageQueue",
    "DailyHistory",
    "DailySummary",
    "Message",
    "MessageRole",
    "calculate_message_weight",
    "estimate_tokens",
    # 标签模块
    "ReplyTag",
    "TagGenerator",
    "TagCache",
    # 配置模块
    "AgentConfig",
    "HistoryConfig",
    "TagsConfig",
    "StorageConfig",
    "PersonaConfig",
    # 存储模块
    "AgentStorage",
    "PersonaStorage",
    "HistoryStorage",
    "TagsStorage",
    "ConfigStorage",
    # Prompt构建模块
    "PromptBuilder",
    "build_minimal_prompt",
    "build_full_conversation_prompt",
    "build_memory_flush_prompt",
]
