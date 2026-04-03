"""Agent Core 核心层 - 适配器实现模块。

每个文件实现一个 Provider 的适配器。
"""

from .minimax import MiniMaxAdapter
from .openai import OpenAIAdapter
from .anthropic import AnthropicAdapter
from .moonshot import MoonshotAdapter
from .ollama import OllamaAdapter
from .openrouter import OpenRouterAdapter

# 导入到包级别方便访问
__all__ = [
    "MiniMaxAdapter",
    "OpenAIAdapter",
    "AnthropicAdapter",
    "MoonshotAdapter",
    "OllamaAdapter",
    "OpenRouterAdapter",
]
