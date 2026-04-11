"""Anthropic API 适配器。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..adapter import APIProvider, BaseAdapter, ModelConfig
from ..types import ChatCompletionRequest, ChatCompletionResponse, ChatCompletionChoice, UsageInfo

if TYPE_CHECKING:
    pass


class AnthropicAdapter(BaseAdapter):
    """Anthropic API 适配器 (支持 Claude)。"""

    provider = APIProvider.ANTHROPIC

    def build_headers(self, config: ModelConfig) -> dict:
        return {
            "x-api-key": config.resolved_api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

    def build_request(self, request: ChatCompletionRequest, config: ModelConfig) -> dict:
        from ..message import Message, MessageContent

        # 转换为 Anthropic 格式
        data: dict = {
            "model": config.name,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        # 处理 messages
        messages = []
        system_content = ""

        for msg in request.messages:
            msg_dict = msg.to_dict() if isinstance(msg, Message) else msg

            if msg_dict["role"] == "system":
                system_content = msg_dict["content"]
            else:
                messages.append(msg_dict)

        data["messages"] = messages

        if system_content:
            data["system"] = system_content

        # 转换 tools 为 Anthropic 格式
        if request.tools:
            data["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in request.tools
            ]

        if request.stream:
            data["stream"] = True

        return data

    def parse_response(self, response_data: dict) -> ChatCompletionResponse:
        from ..message import Message, MessageContent, ToolCall

        # Anthropic 响应格式转换
        content = response_data.get("content", [])
        text = ""
        tool_calls = []

        if isinstance(content, list):
            for block in content:
                if block.get("type") == "text":
                    text = block.get("text", "")
                elif block.get("type") == "tool_use":
                    tool_calls.append(
                        ToolCall(
                            id=block.get("id", ""),
                            name=block.get("name", ""),
                            arguments=block.get("input", {}),
                        )
                    )

        message = Message(
            role="assistant",
            content=MessageContent(text=text, tool_calls=tool_calls if tool_calls else None),
        )

        usage_data = response_data.get("usage", {})
        usage = UsageInfo(
            prompt_tokens=usage_data.get("input_tokens", 0),
            completion_tokens=usage_data.get("output_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
            source="provider_usage",
        )

        return ChatCompletionResponse(
            id=response_data.get("id", ""),
            model=response_data.get("model", ""),
            choices=[ChatCompletionChoice(message, response_data.get("stop_reason", "end_turn"), 0)],
            usage=usage,
        )
