"""Agent Core 核心层 - Python Agent人格与历史消息管理库。

提供角色人格、历史消息管理、回复标签生成和Prompt构建功能。
灵感来源于OpenClaw的提示生成和内存管理机制。

功能模块：
- persona: 角色人格和记忆管理
- history: 历史消息和Token感知权重管理
- tags: 回复表情/动作标签生成
- config: 配置管理
- persistence: JSON/Markdown文件持久化
- prompt_builder: 分段式Prompt构建

使用示例：
    from agent_core import Persona, MessageHistory, PromptBuilder, AgentStorage
    from agent_core.persona import PersonaProfile
    from agent_core.history import MessageRole

    # 创建角色人格
    profile = PersonaProfile(
        name="红莉栖",
        age=18,
        gender="female",
        personality_traits=["天才", "傲娇", "温柔"],
        background="18岁的天才少女科学家，就读于维克托多利亚大学。",
        speaking_style="傲娇但内心温柔"
    )
    persona = Persona(profile)

    # 添加记忆
    persona.add_memory(
        content="用户喜欢在晚上使用程序",
        memory_type="preference",
        importance=1.5
    )

    # 创建历史管理器
    history = MessageHistory(max_context_tokens=4000)

    # 添加消息
    history.add_message("晚上好，红莉栖。", MessageRole.USER)
    history.add_message("哼，都几点了还来找我。", MessageRole.ASSISTANT)

    # 构建Prompt
    builder = PromptBuilder(persona, history)
    prompt = builder.build_system_prompt()

    # 保存数据
    storage = AgentStorage("./data")
    storage.save_all_persona(persona)
    storage.save_all_history(history)
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

__version__ = "0.1.0"
