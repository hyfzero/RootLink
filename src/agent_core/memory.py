"""
记忆系统
包含长期记忆、短期记忆和消息权重管理
"""

import json
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import deque


class MessageWeight(Enum):
    """消息权重等级"""
    TRIVIAL = 1      # 无关紧要
    LOW = 2          # 低权重
    NORMAL = 3       # 普通
    IMPORTANT = 5    # 重要
    CRITICAL = 8     # 关键
    MEMORABLE = 10   # 值得铭记


@dataclass
class Memory:
    """记忆条目"""
    id: str
    content: str
    timestamp: datetime
    weight: MessageWeight = MessageWeight.NORMAL
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    source_message_id: Optional[str] = None

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "weight": self.weight.value,
            "tags": self.tags,
            "metadata": self.metadata,
            "source_message_id": self.source_message_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Memory":
        """从字典创建"""
        if isinstance(data.get("weight"), int):
            data["weight"] = MessageWeight(data["weight"])
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class ConversationMemory:
    """会话记忆 - 短期记忆"""
    session_id: str
    messages: list[Memory] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)

    def add_message(self, memory: Memory) -> None:
        """添加消息到会话"""
        self.messages.append(memory)
        self.last_updated = datetime.now()

    def get_recent_messages(self, count: int = 10) -> list[Memory]:
        """获取最近的消息"""
        return self.messages[-count:]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ConversationMemory":
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if isinstance(data.get("last_updated"), str):
            data["last_updated"] = datetime.fromisoformat(data["last_updated"])
        if "messages" in data:
            data["messages"] = [Memory.from_dict(m) if isinstance(m, dict) else m for m in data["messages"]]
        return cls(**data)


class MemoryManager:
    """记忆管理器"""

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path
        self.long_term_memories: list[Memory] = []  # 长期记忆
        self.conversation_memories: dict[str, ConversationMemory] = {}  # 会话记忆

    def add_long_term_memory(
        self,
        content: str,
        weight: MessageWeight = MessageWeight.NORMAL,
        tags: list[str] = None,
        metadata: dict = None,
    ) -> Memory:
        """添加长期记忆"""
        memory = Memory(
            id=f"mem_{datetime.now().timestamp()}",
            content=content,
            timestamp=datetime.now(),
            weight=weight,
            tags=tags or [],
            metadata=metadata or {},
        )
        self.long_term_memories.append(memory)
        return memory

    def search_memories(self, query: str, limit: int = 5) -> list[Memory]:
        """搜索记忆"""
        query_lower = query.lower()
        scored_memories = []

        for memory in self.long_term_memories:
            score = 0
            # 内容匹配
            if query_lower in memory.content.lower():
                score += 5
            # 标签匹配
            for tag in memory.tags:
                if query_lower in tag.lower():
                    score += 3
            # 权重加成
            score += memory.weight.value

            if score > 0:
                scored_memories.append((score, memory))

        # 按分数排序并返回
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored_memories[:limit]]

    def get_important_memories(self, min_weight: MessageWeight = MessageWeight.IMPORTANT) -> list[Memory]:
        """获取重要记忆"""
        return [m for m in self.long_term_memories if m.weight.value >= min_weight.value]

    def create_conversation(self, session_id: str) -> ConversationMemory:
        """创建新会话"""
        conversation = ConversationMemory(session_id=session_id)
        self.conversation_memories[session_id] = conversation
        return conversation

    def get_conversation(self, session_id: str) -> Optional[ConversationMemory]:
        """获取会话"""
        return self.conversation_memories.get(session_id)

    def add_to_conversation(
        self,
        session_id: str,
        content: str,
        weight: MessageWeight = MessageWeight.NORMAL,
        tags: list[str] = None,
        source_message_id: str = None,
    ) -> Optional[Memory]:
        """添加消息到会话"""
        if session_id not in self.conversation_memories:
            self.create_conversation(session_id)

        memory = Memory(
            id=f"msg_{datetime.now().timestamp()}",
            content=content,
            timestamp=datetime.now(),
            weight=weight,
            tags=tags or [],
            source_message_id=source_message_id,
        )
        self.conversation_memories[session_id].add_message(memory)
        return memory

    def save_to_storage(self, agent_id: str) -> bool:
        """保存记忆到存储"""
        if not self.storage_path:
            return False

        try:
            storage_dir = self.storage_path / agent_id
            storage_dir.mkdir(parents=True, exist_ok=True)

            # 保存长期记忆
            with open(storage_dir / "long_term_memories.json", "w", encoding="utf-8") as f:
                json.dump(
                    [m.to_dict() for m in self.long_term_memories],
                    f, ensure_ascii=False, indent=2
                )

            # 保存会话记忆
            with open(storage_dir / "conversation_memories.json", "w", encoding="utf-8") as f:
                json.dump(
                    {k: v.to_dict() for k, v in self.conversation_memories.items()},
                    f, ensure_ascii=False, indent=2
                )

            return True
        except Exception as e:
            print(f"保存记忆失败: {e}")
            return False

    def load_from_storage(self, agent_id: str) -> bool:
        """从存储加载记忆"""
        if not self.storage_path:
            return False

        storage_dir = self.storage_path / agent_id

        try:
            # 加载长期记忆
            long_term_file = storage_dir / "long_term_memories.json"
            if long_term_file.exists():
                with open(long_term_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.long_term_memories = [Memory.from_dict(m) for m in data]

            # 加载会话记忆
            conv_file = storage_dir / "conversation_memories.json"
            if conv_file.exists():
                with open(conv_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.conversation_memories = {
                        k: ConversationMemory.from_dict(v) for k, v in data.items()
                    }

            return True
        except Exception as e:
            print(f"加载记忆失败: {e}")
            return False
