"""Agent Core 核心层 - 消息和角色定义模块。

定义统一的消息结构、工具调用和函数定义。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class MessageRole(str, Enum):
    """消息角色枚举。"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class MessageContent:
    """消息内容，支持文本和工具调用。"""

    text: Optional[str] = None
    tool_calls: Optional[list[ToolCall]] = None

    def to_dict(self) -> dict:
        result = {}
        if self.text is not None:
            result["text"] = self.text
        if self.tool_calls:
            result["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "MessageContent":
        text = data.get("text") or data.get("content")
        tool_calls = None
        if "tool_calls" in data:
            tool_calls = [ToolCall.from_dict(tc) for tc in data["tool_calls"]]
        elif "tool_call" in data:
            tc = data["tool_call"]
            if isinstance(tc, dict):
                tool_calls = [ToolCall.from_dict(tc)]
        return cls(text=text, tool_calls=tool_calls)


@dataclass
class ToolCall:
    """工具调用。"""

    id: str
    name: str
    arguments: str | dict

    def to_dict(self) -> dict:
        args = self.arguments if isinstance(self.arguments, str) else json.dumps(self.arguments)
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": args,
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ToolCall":
        func = data.get("function", data)
        args = func.get("arguments", "{}")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {"raw": args}
        return cls(
            id=data.get("id", ""),
            name=func.get("name", ""),
            arguments=args,
        )


@dataclass
class ToolDefinition:
    """工具定义。"""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema 格式

    def to_dict(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class Message:
    """对话消息。"""

    role: MessageRole
    content: str | MessageContent
    name: Optional[str] = None  # tool role 时需要
    tool_call_id: Optional[str] = None  # tool 消息需要

    def to_dict(self) -> dict:
        if isinstance(self.content, str):
            content_value = self.content
            tool_calls = None
        else:
            content_value = self.content.text or ""
            tool_calls = self.content.tool_calls

        result: dict[str, Any] = {
            "role": self.role.value,
            "content": content_value,
        }
        if tool_calls:
            result["tool_calls"] = [tc.to_dict() for tc in tool_calls]
        if self.name:
            result["name"] = self.name
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        role = MessageRole(data.get("role", "user"))
        content_data = data.get("content", "")
        top_level_tool_calls = data.get("tool_calls")

        if isinstance(content_data, str):
            if top_level_tool_calls:
                content = MessageContent(
                    text=content_data,
                    tool_calls=[ToolCall.from_dict(tc) for tc in top_level_tool_calls],
                )
            else:
                content = content_data
        else:
            content = MessageContent.from_dict(content_data)
            if top_level_tool_calls:
                content.tool_calls = [ToolCall.from_dict(tc) for tc in top_level_tool_calls]

        return cls(
            role=role,
            content=content,
            name=data.get("name"),
            tool_call_id=data.get("tool_call_id"),
        )
