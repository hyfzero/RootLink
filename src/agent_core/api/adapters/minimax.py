"""MiniMax API 适配器。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..adapter import APIProvider, BaseAdapter, ModelConfig
from ..types import ChatCompletionRequest, ChatCompletionResponse, StreamChunk

if TYPE_CHECKING:
    from ..message import ToolCall


class MiniMaxAdapter(BaseAdapter):
    """MiniMax API 适配器。"""

    provider = APIProvider.MINIMAX

    def build_headers(self, config: ModelConfig) -> dict:
        return {
            "Authorization": f"Bearer {config.resolved_api_key}",
            "Content-Type": "application/json",
        }

    def build_request(self, request: ChatCompletionRequest, config: ModelConfig) -> dict:
        data = request.to_dict()

        # MiniMax M2/M2.5 支持 reasoning_split
        if config.supports_thinking:
            data["reasoning_split"] = True

        return data

    def parse_response(self, response_data: dict) -> ChatCompletionResponse:
        usage_data = response_data.get("usage", {}) or {}

        prompt_tokens = (
            usage_data.get("prompt_tokens")
            or usage_data.get("input_tokens")
            or usage_data.get("prompt_token_count")
            or 0
        )
        completion_tokens = (
            usage_data.get("completion_tokens")
            or usage_data.get("output_tokens")
            or usage_data.get("completion_token_count")
            or 0
        )
        reasoning_tokens = (
            usage_data.get("reasoning_tokens")
            or usage_data.get("thinking_tokens")
            or 0
        )
        total_tokens = (
            usage_data.get("total_tokens")
            or usage_data.get("total_token_count")
            or (prompt_tokens + completion_tokens + reasoning_tokens)
        )

        normalized = dict(response_data)
        normalized["usage"] = {
            "prompt_tokens": int(prompt_tokens),
            "completion_tokens": int(completion_tokens),
            "total_tokens": int(total_tokens),
            "reasoning_tokens": int(reasoning_tokens),
        }
        if total_tokens > 0:
            normalized["usage"]["source"] = "provider_usage"

        return ChatCompletionResponse.from_dict(normalized)

    def parse_stream_chunk(self, chunk_data: dict) -> StreamChunk:
        delta = ""
        is_complete = False
        reasoning = None
        finish_reason = None
        tool_calls = None

        if "choices" in chunk_data:
            choice = chunk_data["choices"][0]
            delta_data = choice.get("delta", {})

            if isinstance(delta_data, dict):
                delta = delta_data.get("content", "") or delta_data.get("text", "") or ""
                if "tool_calls" in delta_data:
                    from ..message import ToolCall
                    tool_calls = [ToolCall.from_dict(tc) for tc in delta_data["tool_calls"]]
                    return StreamChunk(delta="", is_complete=False, tool_calls=tool_calls)
            elif isinstance(delta_data, str):
                delta = delta_data

            finish_reason = choice.get("finish_reason")
            is_complete = finish_reason in ("stop", "eos")

        # MiniMax M2.5 reasoning
        if "thinking" in chunk_data:
            reasoning = chunk_data["thinking"]

        return StreamChunk(
            delta=delta,
            is_complete=is_complete,
            reasoning=reasoning,
            finish_reason=finish_reason,
            tool_calls=tool_calls,
        )
