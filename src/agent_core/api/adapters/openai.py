"""OpenAI API 适配器。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..adapter import APIProvider, BaseAdapter, ModelConfig
from ..types import ChatCompletionRequest, ChatCompletionResponse

if TYPE_CHECKING:
    pass


class OpenAIAdapter(BaseAdapter):
    """OpenAI API 适配器。"""

    provider = APIProvider.OPENAI

    def build_headers(self, config: ModelConfig) -> dict:
        return {
            "Authorization": f"Bearer {config.resolved_api_key}",
            "Content-Type": "application/json",
        }

    def build_request(self, request: ChatCompletionRequest, config: ModelConfig) -> dict:
        return request.to_dict()

    def parse_response(self, response_data: dict) -> ChatCompletionResponse:
        return ChatCompletionResponse.from_dict(response_data)
