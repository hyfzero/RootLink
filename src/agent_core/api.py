"""Agent Core API 模块 - 向后兼容入口。

实际实现在 agent_core.api 子包中。
请使用 `from agent_core.api import ...` 而不是 `from agent_core.api import ...`
"""

# 从子包重新导出，保持向后兼容
from agent_core.api import (
    Message,
    MessageContent,
    MessageRole,
    ToolCall,
    ToolDefinition,
    ApiMessage,
    APIProvider,
    BaseAdapter,
    ModelConfig,
    AdapterRegistry,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChoice,
    UsageInfo,
    StreamChunk,
    ChatAgent,
    ToolExecutor,
    ProviderManager,
    AgentRuntime,
    MiniMaxAdapter,
    OpenAIAdapter,
    AnthropicAdapter,
    MoonshotAdapter,
    OllamaAdapter,
    OpenRouterAdapter,
)

__all__ = [
    "Message",
    "MessageContent",
    "MessageRole",
    "ToolCall",
    "ToolDefinition",
    "ApiMessage",
    "APIProvider",
    "BaseAdapter",
    "ModelConfig",
    "AdapterRegistry",
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "ChatCompletionChoice",
    "UsageInfo",
    "StreamChunk",
    "ChatAgent",
    "ToolExecutor",
    "ProviderManager",
    "AgentRuntime",
    "MiniMaxAdapter",
    "OpenAIAdapter",
    "AnthropicAdapter",
    "MoonshotAdapter",
    "OllamaAdapter",
    "OpenRouterAdapter",
]
