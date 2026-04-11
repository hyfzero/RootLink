"""Ollama API 适配器。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..adapter import APIProvider, BaseAdapter, ModelConfig
from ..types import ChatCompletionRequest, ChatCompletionResponse, ChatCompletionChoice, UsageInfo

if TYPE_CHECKING:
    pass


class OllamaAdapter(BaseAdapter):
    """Ollama API 适配器。"""

    provider = APIProvider.OLLAMA

    def build_headers(self, config: ModelConfig) -> dict:
        return {
            "Content-Type": "application/json",
        }

    def build_request(self, request: ChatCompletionRequest, config: ModelConfig) -> dict:
        from ..message import Message

        data = request.to_dict()

        # Ollama 使用不同的字段名
        data["model"] = config.name
        data.pop("top_p", None)
        data.pop("tools", None)

        # 构建 messages
        messages = []
        for msg in request.messages:
            msg_dict = msg.to_dict() if isinstance(msg, Message) else msg
            messages.append(msg_dict)

        data["messages"] = messages

        return data

    def parse_response(self, response_data: dict) -> ChatCompletionResponse:
        from ..message import Message

        message_data = response_data.get("message", {})
        message = Message.from_dict(message_data)

        usage_data = response_data.get("usage", {})

        return ChatCompletionResponse(
            id=response_data.get("id", ""),
            model=response_data.get("model", ""),
            choices=[ChatCompletionChoice(message, response_data.get("done_reason", "stop"), 0)],
            usage=UsageInfo(
                prompt_tokens=usage_data.get("prompt_eval_count", 0),
                completion_tokens=usage_data.get("eval_count", 0),
                total_tokens=usage_data.get("prompt_eval_count", 0) + usage_data.get("eval_count", 0),
                source="provider_usage",
            ),
        )
