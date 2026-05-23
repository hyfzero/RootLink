"""Agent Core 核心层 - Provider 和 Adapter 适配器模块。

定义 Provider 枚举、模型配置和抽象适配器接口。
每个 Provider 有对应的 Adapter 负责请求/响应的格式转换。
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .message import Message, ToolDefinition
    from .types import ChatCompletionRequest, ChatCompletionResponse, StreamChunk


class APIProvider(str):
    """支持的 API 提供商枚举。"""

    MINIMAX = "minimax"
    DEEPSEEK = "deepseek"
    OPENAI = "openai"
    GLM = "glm"
    ANTHROPIC = "anthropic"
    MOONSHOT = "moonshot"
    KIMI = "kimi"
    OLLAMA = "ollama"
    OPENROUTER = "openrouter"


@dataclass
class ModelConfig:
    """模型配置。"""

    name: str
    provider: APIProvider
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.7
    supports_function_calling: bool = True
    supports_streaming: bool = True
    supports_thinking: bool = False  # MiniMax M2.5 等支持

    tokenizer_mode: str = "auto"  # auto / provider / heuristic
    tokenizer_fallback: str = "hybrid_v1"  # hybrid_v1 / legacy_char_div4
    @property
    def resolved_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        env_map = {
            APIProvider.MINIMAX: "MINIMAX_API_KEY",
            APIProvider.DEEPSEEK: "DEEPSEEK_API_KEY",
            APIProvider.OPENAI: "OPENAI_API_KEY",
            APIProvider.GLM: "GLM_API_KEY",
            APIProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
            APIProvider.MOONSHOT: "MOONSHOT_API_KEY",
            APIProvider.KIMI: "KIMI_API_KEY",
            APIProvider.OLLAMA: None,
            APIProvider.OPENROUTER: "OPENROUTER_API_KEY",
        }
        env_name = env_map.get(self.provider)
        if env_name:
            return os.getenv(env_name, "")
        return ""

    @property
    def resolved_base_url(self) -> str:
        if self.base_url:
            return self.base_url
        defaults = {
            APIProvider.MINIMAX: "https://api.minimaxi.com/v1",
            APIProvider.DEEPSEEK: "https://api.deepseek.com",
            APIProvider.OPENAI: "https://api.openai.com/v1",
            APIProvider.GLM: "https://open.bigmodel.cn/api/paas/v4",
            APIProvider.ANTHROPIC: "https://api.anthropic.com/v1",
            APIProvider.MOONSHOT: "https://api.moonshot.cn/v1",
            APIProvider.KIMI: "https://api.moonshot.cn/v1",
            APIProvider.OLLAMA: "http://localhost:11434/v1",
            APIProvider.OPENROUTER: "https://openrouter.ai/api/v1",
        }
        return defaults.get(self.provider, "")


class BaseAdapter(ABC):
    """API 适配器基类，定义各 Provider 的适配接口。"""

    provider: APIProvider
    cumulative_stream_content = False

    @abstractmethod
    def build_request(self, request: "ChatCompletionRequest", config: ModelConfig) -> dict:
        """构建 Provider 特定的请求格式。"""
        pass

    @abstractmethod
    def parse_response(self, response_data: dict) -> "ChatCompletionResponse":
        """解析 Provider 响应。"""
        pass

    @abstractmethod
    def build_headers(self, config: ModelConfig) -> dict:
        """构建请求头。"""
        pass

    def parse_stream_chunk(self, chunk_data: dict) -> "StreamChunk":
        """解析流式响应块。默认实现，可被子类覆盖。"""
        from .types import StreamChunk

        delta = ""
        is_complete = False
        tool_calls = None
        reasoning = None
        finish_reason = None

        if "choices" in chunk_data:
            choice = chunk_data["choices"][0]
            delta_data = choice.get("delta", {})
            if isinstance(delta_data, dict):
                delta = delta_data.get("content", "") or delta_data.get("text", "") or ""
            elif isinstance(delta_data, str):
                delta = delta_data

            finish_reason = choice.get("finish_reason")

            if "tool_calls" in delta_data:
                from .message import ToolCall
                tool_calls = [ToolCall.from_dict(tc) for tc in delta_data["tool_calls"]]

            is_complete = finish_reason in ("stop", "tool_calls", "eos")

        if "thinking" in chunk_data:
            reasoning = chunk_data["thinking"]

        return StreamChunk(
            delta=delta,
            is_complete=is_complete,
            tool_calls=tool_calls,
            reasoning=reasoning,
            finish_reason=finish_reason,
        )


class AdapterRegistry:
    """适配器注册表。"""

    _adapters: dict[APIProvider, type[BaseAdapter]] = {}

    @classmethod
    def get(cls, provider: APIProvider) -> BaseAdapter:
        adapter_class = cls._adapters.get(provider)
        if not adapter_class:
            raise ValueError(f"Unsupported provider: {provider}")
        return adapter_class()

    @classmethod
    def register(cls, provider: APIProvider, adapter_class: type[BaseAdapter]) -> None:
        cls._adapters[provider] = adapter_class
