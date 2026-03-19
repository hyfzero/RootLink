"""
Agent核心类
整合人格、记忆、历史消息和标签系统
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from .persona import Persona, PersonaManager
from .memory import Memory, MemoryManager, MessageWeight, ConversationMemory
from .history import HistoryManager, ChatMessage, DailySummary
from .tags import ReplyTag, ReplyTagType, TagManager, TaggedReply, get_tag_for_display
from .storage import Storage


class Agent:
    """
    Agent核心类

    整合以下功能:
    1. Agent人格系统
    2. 历史消息机制
    3. 消息标签系统
    4. 持久化存储
    """

    def __init__(
        self,
        agent_id: str,
        storage_path: Optional[Path] = None,
    ):
        self.agent_id = agent_id
        self.storage_path = Path(storage_path) if storage_path else None

        # 初始化各子系统
        self.persona_manager = PersonaManager(self.storage_path)
        self.memory_manager = MemoryManager(self.storage_path)
        self.history_manager = HistoryManager(self.storage_path)
        self.tag_manager = TagManager(self.storage_path)

        # 存储
        if self.storage_path:
            self.storage = Storage(self.storage_path)
        else:
            self.storage = None

    def create_persona(
        self,
        name: str,
        age: int,
        gender: str,
        personality: str = "",
        background: str = "",
        interests: list[str] = None,
        speaking_style: str = "",
    ) -> Persona:
        """创建人格"""
        return self.persona_manager.create_persona(
            name=name,
            age=age,
            gender=gender,
            personality=personality,
            background=background,
            interests=interests,
            speaking_style=speaking_style,
        )

    def get_persona(self) -> Optional[Persona]:
        """获取当前人格"""
        return self.persona_manager.get_persona()

    def get_persona_prompt(self) -> str:
        """获取人格prompt"""
        persona = self.persona_manager.get_persona()
        if not persona:
            return ""
        return persona.get_prompt_context()

    def add_message(
        self,
        sender: str,
        content: str,
        weight: MessageWeight = MessageWeight.NORMAL,
        tags: list[str] = None,
    ) -> ChatMessage:
        """添加消息"""
        return self.history_manager.add_message(
            sender=sender,
            content=content,
            weight=weight,
            tags=tags,
        )

    def add_reply(
        self,
        message_id: str,
        content: str,
        auto_tag: bool = True,
        metadata: dict = None,
    ) -> TaggedReply:
        """添加回复（带标签）"""
        if auto_tag:
            tags = self.tag_manager.analyze_content_for_tags(content)
        else:
            tags = []

        return self.tag_manager.create_tagged_reply(
            message_id=message_id,
            content=content,
            tags=tags,
            metadata=metadata,
        )

    def get_reply_tags(self, message_id: str) -> Optional[list[dict]]:
        """获取回复的标签（用于UI显示）"""
        reply = self.tag_manager.get_reply_by_id(message_id)
        if not reply:
            return None
        return [get_tag_for_display(tag) for tag in reply.tags]

    def generate_prompt(
        self,
        max_history_messages: int = 20,
        include_days: int = 7,
    ) -> str:
        """
        生成完整的prompt

        包含:
        1. Agent人格信息
        2. 历史消息梗概
        3. 当天重要消息
        """
        prompt_parts = []

        # 1. 人格上下文
        persona_context = self.get_persona_prompt()
        if persona_context:
            prompt_parts.append("## Agent人格")
            prompt_parts.append(persona_context)
            prompt_parts.append("")

        # 2. 历史消息上下文
        history_context = self.history_manager.get_prompt_context(
            max_messages=max_history_messages,
            include_days=include_days,
        )
        if history_context:
            prompt_parts.append(history_context)

        return "\n".join(prompt_parts)

    def save(self) -> bool:
        """保存所有数据"""
        if not self.storage:
            return False

        data = {
            "agent_id": self.agent_id,
            "saved_at": datetime.now().isoformat(),
        }

        # 保存人格
        persona = self.persona_manager.get_persona()
        if persona:
            data["persona"] = persona.to_dict()

        # 保存长期记忆
        data["long_term_memories"] = [
            m.to_dict() for m in self.memory_manager.long_term_memories
        ]

        # 保存历史梗概
        data["daily_summaries"] = {
            k: v.to_dict() for k, v in self.history_manager.daily_summaries.items()
        }
        data["today_queue"] = self.history_manager.today_queue.to_dict()

        # 保存标签
        data["tagged_replies"] = [
            r.to_dict() for r in self.tag_manager.tagged_replies
        ]

        return self.storage.save_agent_data(self.agent_id, data)

    def load(self) -> bool:
        """加载所有数据"""
        if not self.storage:
            return False

        data = self.storage.load_agent_data(self.agent_id)
        if not data:
            return False

        # 加载人格
        if "persona" in data:
            self.persona_manager.current_persona = Persona.from_dict(data["persona"])

        # 加载长期记忆
        if "long_term_memories" in data:
            self.memory_manager.long_term_memories = [
                Memory.from_dict(m) for m in data["long_term_memories"]
            ]

        # 加载历史
        if "daily_summaries" in data:
            self.history_manager.daily_summaries = {
                k: DailySummary.from_dict(v) for k, v in data["daily_summaries"].items()
            }

        if "today_queue" in data:
            from .history import MessageQueue
            self.history_manager.today_queue = MessageQueue.from_dict(data["today_queue"])

        # 加载标签
        if "tagged_replies" in data:
            self.tag_manager.tagged_replies = [
                TaggedReply.from_dict(r) for r in data["tagged_replies"]
            ]

        return True

    @classmethod
    def load_from_storage(
        cls,
        agent_id: str,
        storage_path: Path,
    ) -> Optional["Agent"]:
        """从存储加载Agent"""
        agent = cls(agent_id, storage_path)
        if agent.load():
            return agent
        return None

    def get_status(self) -> dict:
        """获取Agent状态"""
        return {
            "agent_id": self.agent_id,
            "persona": self.persona_manager.get_persona().name if self.persona_manager.get_persona() else None,
            "long_term_memories_count": len(self.memory_manager.long_term_memories),
            "today_messages_count": len(self.history_manager.today_queue.queue),
            "tagged_replies_count": len(self.tag_manager.tagged_replies),
            "daily_summaries_count": len(self.history_manager.daily_summaries),
        }


def create_agent(
    agent_id: str,
    name: str,
    age: int,
    gender: str,
    personality: str = "",
    background: str = "",
    interests: list[str] = None,
    speaking_style: str = "",
    storage_path: Path = None,
) -> Agent:
    """创建新Agent的便捷函数"""
    agent = Agent(agent_id, storage_path)
    agent.create_persona(
        name=name,
        age=age,
        gender=gender,
        personality=personality,
        background=background,
        interests=interests,
        speaking_style=speaking_style,
    )
    return agent
