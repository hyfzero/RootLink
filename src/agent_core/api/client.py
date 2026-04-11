"""Agent Core 核心层 - API Client 模块。

提供 ChatAgent、ToolExecutor、ProviderManager 等核心客户端类。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import requests

from ..brain.tokenizer import build_tokenizer_resolver
from .adapter import APIProvider, AdapterRegistry, BaseAdapter, ModelConfig
from .adapters import (
    AnthropicAdapter,
    MiniMaxAdapter,
    MoonshotAdapter,
    OllamaAdapter,
    OpenAIAdapter,
    OpenRouterAdapter,
)
from .message import Message, MessageContent, MessageRole, ToolCall, ToolDefinition
from .types import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    StreamChunk,
)

# 注册内置适配器
AdapterRegistry.register(APIProvider.MINIMAX, MiniMaxAdapter)
AdapterRegistry.register(APIProvider.OPENAI, OpenAIAdapter)
AdapterRegistry.register(APIProvider.ANTHROPIC, AnthropicAdapter)
AdapterRegistry.register(APIProvider.MOONSHOT, MoonshotAdapter)
AdapterRegistry.register(APIProvider.KIMI, MoonshotAdapter)  # Kimi 使用 Moonshot 兼容格式
AdapterRegistry.register(APIProvider.OLLAMA, OllamaAdapter)
AdapterRegistry.register(APIProvider.OPENROUTER, OpenRouterAdapter)

logger = logging.getLogger(__name__)


class ToolExecutor:
    """工具调用执行器。"""

    def __init__(self, tools: dict[str, Callable[..., Any]]):
        self.tools = tools

    def execute(self, tool_call: ToolCall) -> Any:
        """执行单个工具调用。"""
        tool_name = tool_call.name
        if tool_name not in self.tools:
            raise ValueError(f"Unknown tool: {tool_name}")

        args = tool_call.arguments
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}

        return self.tools[tool_name](**args)

    def execute_all(self, tool_calls: list[ToolCall]) -> list[tuple[str, Any]]:
        """执行多个工具调用。"""
        results = []
        for tc in tool_calls:
            try:
                result = self.execute(tc)
                results.append((tc.id, result))
            except Exception as e:
                results.append((tc.id, {"error": str(e)}))
        return results


class ChatAgent:
    """统一 API 调用客户端。"""

    def __init__(
        self,
        config: ModelConfig,
        adapter: Optional[BaseAdapter] = None,
    ):
        self.config = config
        self.adapter = adapter or AdapterRegistry.get(config.provider)

    def chat(
        self,
        messages: list[Message | dict],
        tools: Optional[list[ToolDefinition]] = None,
        stream: bool = False,
        **kwargs,
    ) -> ChatCompletionResponse | StreamChunk:
        """发送聊天请求。"""
        request = ChatCompletionRequest(
            model=self.config.name,
            messages=messages,
            temperature=kwargs.get("temperature", self.config.temperature),
            max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
            tools=tools,
            stream=stream,
            reasoning_split=getattr(self.config, "supports_thinking", False) and stream,
        )

        if stream:
            return self._stream(request)
        return self._send(request)

    def _send(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """发送同步请求。"""
        url = f"{self.config.resolved_base_url}/chat/completions"

        headers = self.adapter.build_headers(self.config)
        data = self.adapter.build_request(request, self.config)

        logger.debug(f"Request to {url}: {json.dumps(data, ensure_ascii=False)[:500]}")

        response = requests.post(url, headers=headers, json=data, timeout=60)
        response.raise_for_status()

        response_data = response.json()
        logger.debug(f"Response: {json.dumps(response_data, ensure_ascii=False)[:500]}")

        parsed = self.adapter.parse_response(response_data)
        return self._align_token_usage(request, parsed)

    def _align_token_usage(
        self,
        request: ChatCompletionRequest,
        response: ChatCompletionResponse,
    ) -> ChatCompletionResponse:
        usage = response.usage
        if usage.total_tokens > 0:
            if usage.source == "unknown":
                usage.source = "provider_usage"
            response.token_source = usage.source
            return response

        resolver = build_tokenizer_resolver(
            token_estimator=self.config.tokenizer_fallback,
            model_config=self.config,
            tokenizer_mode=self.config.tokenizer_mode,
        )
        prompt_count = resolver.count_messages(request.messages)
        completion_count = resolver.count_text(response.content)

        usage.prompt_tokens = prompt_count.tokens
        usage.completion_tokens = completion_count.tokens
        usage.total_tokens = prompt_count.tokens + completion_count.tokens
        usage.source = (
            "provider_tokenizer"
            if (prompt_count.source == "provider_tokenizer" and completion_count.source == "provider_tokenizer")
            else "heuristic_fallback"
        )
        response.token_source = usage.source
        return response

    def _stream(self, request: ChatCompletionRequest) -> StreamChunk:
        """发送流式请求。"""
        url = f"{self.config.resolved_base_url}/chat/completions"

        headers = self.adapter.build_headers(self.config)
        data = self.adapter.build_request(request, self.config)

        logger.debug(f"Streaming request to {url}")

        response = requests.post(url, headers=headers, json=data, stream=True, timeout=120)
        response.raise_for_status()

        accumulated = ""
        final_chunk: Optional[StreamChunk] = None

        for line in response.iter_lines():
            if not line:
                continue

            line_text = line.decode("utf-8")
            if line_text.startswith("data: "):
                line_text = line_text[6:]

            if line_text == "[DONE]":
                break

            try:
                chunk_data = json.loads(line_text)
                chunk = self.adapter.parse_stream_chunk(chunk_data)
                accumulated += chunk.delta
                final_chunk = chunk

                if chunk.is_complete:
                    break

            except json.JSONDecodeError:
                continue

        # 构建完整的响应
        is_complete = final_chunk.is_complete if final_chunk else True
        reasoning = final_chunk.reasoning if final_chunk else None
        return StreamChunk(delta=accumulated, is_complete=is_complete, reasoning=reasoning)

    @property
    def provider(self) -> APIProvider:
        return self.config.provider


@dataclass
class ProviderManager:
    """Provider 管理器，支持自动选择和回退。"""

    providers: list[ModelConfig] = field(default_factory=list)
    _agent_cache: dict[str, ChatAgent] = field(default_factory=dict)

    def add_provider(self, config: ModelConfig) -> None:
        """添加 Provider。"""
        self.providers.append(config)
        self._agent_cache.clear()

    def get_agent(self, provider: Optional[APIProvider] = None) -> ChatAgent:
        """获取 Agent 实例，优先使用指定 provider。"""
        if provider:
            config = self._find_config(provider)
            if config:
                cache_key = f"{config.provider}:{config.name}"
                if cache_key not in self._agent_cache:
                    self._agent_cache[cache_key] = ChatAgent(config)
                return self._agent_cache[cache_key]

        # 按优先级选择 MiniMax > 其他
        for p in self.providers:
            if p.provider == APIProvider.MINIMAX and p.resolved_api_key:
                cache_key = f"{p.provider}:{p.name}"
                if cache_key not in self._agent_cache:
                    self._agent_cache[cache_key] = ChatAgent(p)
                return self._agent_cache[cache_key]

        # 尝试其他可用的
        for p in self.providers:
            if p.resolved_api_key:
                cache_key = f"{p.provider}:{p.name}"
                if cache_key not in self._agent_cache:
                    self._agent_cache[cache_key] = ChatAgent(p)
                return self._agent_cache[cache_key]

        raise ValueError("No available provider with valid API key")

    def _find_config(self, provider: APIProvider) -> Optional[ModelConfig]:
        for config in self.providers:
            if config.provider == provider and config.resolved_api_key:
                return config
        return None

    @classmethod
    def from_env(cls) -> "ProviderManager":
        """从环境变量创建 Manager。"""
        manager = cls()

        # MiniMax
        if os.getenv("MINIMAX_API_KEY"):
            manager.add_provider(
                ModelConfig(
                    name="MiniMax-M2.5",
                    provider=APIProvider.MINIMAX,
                    supports_thinking=True,
                    supports_function_calling=True,
                )
            )

        # OpenAI
        if os.getenv("OPENAI_API_KEY"):
            manager.add_provider(
                ModelConfig(
                    name="gpt-4o",
                    provider=APIProvider.OPENAI,
                    supports_function_calling=True,
                )
            )

        # Anthropic
        if os.getenv("ANTHROPIC_API_KEY"):
            manager.add_provider(
                ModelConfig(
                    name="claude-sonnet-4-20250514",
                    provider=APIProvider.ANTHROPIC,
                    supports_function_calling=True,
                )
            )

        return manager


import os


@dataclass
class AgentRuntime:
    """Agent 运行时，协调 Prompt、History 和 API 调用。"""

    agent: ChatAgent
    tools: Optional[dict[str, Callable[..., Any]]] = None
    max_turns: int = 10

    def run(
        self,
        messages: list[Message],
        system_prompt: str = "",
        tools: Optional[list[ToolDefinition]] = None,
    ) -> Message:
        """运行 Agent 对话。"""
        if system_prompt:
            messages = [Message(role=MessageRole.SYSTEM, content=system_prompt)] + messages

        if self.tools:
            tool_defs = tools or [
                ToolDefinition(
                    name=name,
                    description=func.__doc__ or "",
                    parameters={"type": "object", "properties": {}},
                )
                for name, func in self.tools.items()
            ]
        else:
            tool_defs = tools

        all_messages = list(messages)

        for _ in range(self.max_turns):
            response = self.agent.chat(all_messages, tools=tool_defs)

            if isinstance(response, StreamChunk):
                content = response.delta
                reasoning = response.reasoning
                tool_calls = response.tool_calls
            else:
                content = response.content
                reasoning = getattr(response, "reasoning", None)
                tool_calls = response.tool_calls

            if tool_calls and self.tools:
                # 执行工具调用
                executor = ToolExecutor(self.tools)
                tool_results = executor.execute_all(tool_calls)

                # 添加助手消息
                all_messages.append(
                    Message(
                        role=MessageRole.ASSISTANT,
                        content=MessageContent(
                            text=content or "",
                            tool_calls=tool_calls,
                        ),
                    )
                )

                # 添加工具结果
                for tool_id, result in tool_results:
                    result_content = json.dumps(result) if isinstance(result, dict) else str(result)
                    all_messages.append(
                        Message(
                            role=MessageRole.TOOL,
                            content=result_content,
                            tool_call_id=tool_id,
                        )
                    )
            else:
                # 返回最终回复
                return Message(
                    role=MessageRole.ASSISTANT,
                    content=content or "",
                )

        # 达到最大轮次
        return Message(
            role=MessageRole.ASSISTANT,
            content="对话达到最大轮次限制。",
        )
