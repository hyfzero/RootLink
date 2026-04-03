"""OpenRouter API 适配器。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..adapter import APIProvider, BaseAdapter, ModelConfig
from ..types import ChatCompletionRequest, ChatCompletionResponse

if TYPE_CHECKING:
    pass


class OpenRouterAdapter(BaseAdapter):
    """OpenRouter API 适配器。"""

    provider = APIProvider.OPENROUTER

    def build_headers(self, config: ModelConfig) -> dict:
        return {
            "Authorization": f"Bearer {config.resolved_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/amadues",
            "X-Title": "AgentCore",
        }

    def build_request(self, request: ChatCompletionRequest, config: ModelConfig) -> dict:
        data = request.to_dict()

        # OpenRouter 特定的 extra_body
        data["extra_body"] = {
            "provider": {
                "require_api_key": True,
            }
        }

        return data

    def parse_response(self, response_data: dict) -> ChatCompletionResponse:
        return ChatCompletionResponse.from_dict(response_data)
