"""Agent Core Brain 模块 - Agent人格、历史、配置管理。

提供：
- persona: 角色人格和记忆管理
- history: 历史消息和Token感知权重管理
- tags: 回复表情/动作标签生成
- config: 配置管理
- persistence: JSON/Markdown文件持久化
- prompt_builder: 分段式Prompt构建
- speaking_style: 说话风格引擎
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
    SummaryGenerator,
    AsyncSummaryGenerator,
    generate_summary_with_llm,
    generate_daily_summaries_with_llm,
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
from .speaking_style import (
    SpeakingStyle,
    SpeakingStyleEngine,
    StyleModifier,
    PRESET_STYLES,
    EMOTION_MODIFIERS,
    get_preset_style,
    list_preset_styles,
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
    # LLM摘要生成
    "SummaryGenerator",
    "AsyncSummaryGenerator",
    "generate_summary_with_llm",
    "generate_daily_summaries_with_llm",
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
    # 说话风格引擎
    "SpeakingStyle",
    "SpeakingStyleEngine",
    "StyleModifier",
    "PRESET_STYLES",
    "EMOTION_MODIFIERS",
    "get_preset_style",
    "list_preset_styles",
]
