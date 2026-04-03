"""Agent Core API 模块。

统一的多模型 API 调用接口。
"""

from .message import Message, MessageContent, MessageRole, ToolCall, ToolDefinition
from .adapter import APIProvider, BaseAdapter, ModelConfig, AdapterRegistry
from .types import ChatCompletionRequest, ChatCompletionResponse, ChatCompletionChoice, UsageInfo, StreamChunk
from .client import ChatAgent, ToolExecutor, ProviderManager, AgentRuntime
from .adapters import MiniMaxAdapter, OpenAIAdapter, AnthropicAdapter, MoonshotAdapter, OllamaAdapter, OpenRouterAdapter

# 向后兼容别名
ApiMessage = Message

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
