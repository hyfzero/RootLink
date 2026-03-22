"""Agent Core 核心层 - 请求和响应类型模块。

定义 API 调用相关的请求/响应数据结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .message import Message, ToolDefinition


@dataclass
class ChatCompletionRequest:
    """聊天补全请求。"""

    model: str
    messages: list[Message | dict]
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 1.0
    tools: Optional[list[ToolDefinition]] = None
    stream: bool = False
    reasoning_split: bool = False  # MiniMax M2.5 专用

    def to_dict(self) -> dict:
        from .message import Message

        messages = [m.to_dict() if isinstance(m, Message) else m for m in self.messages]

        result: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "stream": self.stream,
        }

        if self.tools:
            result["tools"] = [t.to_dict() for t in self.tools]

        if self.reasoning_split:
            result["reasoning_split"] = True

        return result


@dataclass
class ChatCompletionChoice:
    """聊天补全选项。"""

    message: "Message"
    finish_reason: str
    index: int = 0


@dataclass
class UsageInfo:
    """Token 使用信息。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0  # MiniMax M2.5

    def to_dict(self) -> dict:
        result = {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }
        if self.reasoning_tokens > 0:
            result["reasoning_tokens"] = self.reasoning_tokens
        return result


@dataclass
class ChatCompletionResponse:
    """聊天补全响应。"""

    id: str
    model: str
    choices: list[ChatCompletionChoice]
    usage: UsageInfo
    reasoning: Optional[str] = None  # MiniMax M2.5 thinking

    @property
    def content(self) -> str:
        if not self.choices:
            return ""
        msg = self.choices[0].message
        if isinstance(msg.content, str):
            return msg.content
        return msg.content.text or ""

    @property
    def tool_calls(self) -> list["ToolCall"]:
        from .message import ToolCall

        if not self.choices:
            return []
        msg = self.choices[0].message
        if isinstance(msg.content, str):
            return []
        return msg.content.tool_calls or []

    @classmethod
    def from_dict(cls, data: dict) -> "ChatCompletionResponse":
        from .message import Message, MessageContent, ToolCall

        choices = []
        for i, choice_data in enumerate(data.get("choices", [])):
            message_data = choice_data.get("message", {})
            message = Message.from_dict(message_data)
            finish_reason = choice_data.get("finish_reason", "stop")
            choices.append(ChatCompletionChoice(message, finish_reason, i))

        usage_data = data.get("usage", {})
        reasoning = data.get("reasoning") or data.get("thinking") or data.get("reasoning_details")

        usage = UsageInfo(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
            reasoning_tokens=usage_data.get("reasoning_tokens", 0),
        )

        return cls(
            id=data.get("id", ""),
            model=data.get("model", ""),
            choices=choices,
            usage=usage,
            reasoning=reasoning,
        )


@dataclass
class StreamChunk:
    """流式响应块。"""

    delta: str
    is_complete: bool = False
    tool_calls: Optional[list["ToolCall"]] = None
    reasoning: Optional[str] = None
    finish_reason: Optional[str] = None


# ToolCall 需要在这里导入以避免循环引用
from .message import ToolCall
