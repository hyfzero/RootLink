"""Agent Core 核心层 - Python Agent人格与历史消息管理库。

提供角色人格、历史消息管理、回复标签生成、Prompt构建和统一API调用功能。
灵感来源于OpenClaw的提示生成和内存管理机制。

功能模块：
- brain: Agent人格、历史、配置、Prompt构建
  - persona: 角色人格和记忆管理
  - history: 历史消息和Token感知权重管理
  - tags: 回复表情/动作标签生成
  - config: 配置管理
  - persistence: JSON/Markdown文件持久化
  - prompt_builder: 分段式Prompt构建
- api: 统一多模型API调用 (优先MiniMax，支持OpenAI/Anthropic等)
- models: 模型目录配置和Provider管理 (参考OpenClaw models.json)

使用示例：
    from agent_core import Persona, MessageHistory, PromptBuilder, AgentStorage
    from agent_core.brain import PersonaProfile
    from agent_core.brain import MessageRole
    from agent_core.api import ChatAgent, ModelConfig, APIProvider, ApiMessage

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

    # API调用示例 (使用MiniMax)
    config = ModelConfig(
        name="MiniMax-M2.5",
        provider=APIProvider.MINIMAX,
        supports_thinking=True
    )
    agent = ChatAgent(config)
    response = agent.chat([ApiMessage(role=MessageRole.USER, content="你好")])

    # 保存数据
    storage = AgentStorage("./data")
    storage.save_all_persona(persona)
    storage.save_all_history(history)
"""

from .brain import Persona, PersonaProfile, PersonalityState, MemoryEntry
from .brain import (
    MessageHistory,
    MessageQueue,
    DailyHistory,
    DailySummary,
    Message,
    MessageRole,
    calculate_message_weight,
    estimate_tokens,
)
from .brain import ReplyTag, TagGenerator, TagCache
from .brain import (
    AgentConfig,
    HistoryConfig,
    TagsConfig,
    StorageConfig,
    PersonaConfig,
    ResponseConfig,
    MemoryInjectionConfig,
    PromptBudgetConfig,
    RelationshipStateConfig,
    RelationshipStateMachineConfig,
)
from .brain import AgentStorage, PersonaStorage, HistoryStorage, TagsStorage, ConfigStorage
from .brain import (
    PromptBuilder,
    build_minimal_prompt,
    build_full_conversation_prompt,
    build_memory_flush_prompt,
)
from .api import (
    ChatAgent,
    ModelConfig,
    APIProvider,
    Message as ApiMessage,
    ToolCall,
    ToolDefinition,
    ToolExecutor,
    AgentRuntime,
    ProviderManager,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChoice,
    UsageInfo,
    StreamChunk,
    MessageContent,
    AdapterRegistry,
    BaseAdapter,
    MiniMaxAdapter,
    OpenAIAdapter,
    AnthropicAdapter,
    MoonshotAdapter,
    OllamaAdapter,
    OpenRouterAdapter,
)
from .models import (
    ModelCost,
    ModelInfo,
    ProviderCatalog,
    ProviderConfig,
    ModelsJsonConfig,
    ModelsStorage,
    get_model_catalog,
    get_all_providers,
    setup_provider,
    list_available_models,
    print_models_table,
    MINIMAX_MODELS,
    DEEPSEEK_MODELS,
    OPENAI_MODELS,
    ANTHROPIC_MODELS,
    MOONSHOT_MODELS,
    OLLAMA_MODELS,
    OPENROUTER_MODELS,
)

__all__ = [
    # 人格模块
    "Persona",
    "PersonaProfile",
    "PersonalityState",
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
    "ResponseConfig",
    "MemoryInjectionConfig",
    "PromptBudgetConfig",
    "RelationshipStateConfig",
    "RelationshipStateMachineConfig",
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
    # API模块
    "ChatAgent",
    "ModelConfig",
    "APIProvider",
    "ApiMessage",
    "ToolCall",
    "ToolDefinition",
    "ToolExecutor",
    "AgentRuntime",
    "ProviderManager",
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "ChatCompletionChoice",
    "UsageInfo",
    "StreamChunk",
    "MessageContent",
    "AdapterRegistry",
    "BaseAdapter",
    "MiniMaxAdapter",
    "OpenAIAdapter",
    "AnthropicAdapter",
    "MoonshotAdapter",
    "OllamaAdapter",
    "OpenRouterAdapter",
    # 模型配置模块
    "ModelCost",
    "ModelInfo",
    "ProviderCatalog",
    "ProviderConfig",
    "ModelsJsonConfig",
    "ModelsStorage",
    "get_model_catalog",
    "get_all_providers",
    "setup_provider",
    "list_available_models",
    "print_models_table",
    "MINIMAX_MODELS",
    "DEEPSEEK_MODELS",
    "OPENAI_MODELS",
    "ANTHROPIC_MODELS",
    "MOONSHOT_MODELS",
    "OLLAMA_MODELS",
    "OPENROUTER_MODELS",
]

__version__ = "0.1.9"
