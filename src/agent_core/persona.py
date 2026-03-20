"""Agent Core 核心层 - 人格模块。

定义Agent角色的人格特质，包括基本资料、背景故事和记忆系统。
支持三种记忆类型：情景记忆(episodic)、偏好记忆(preference)、事实记忆(fact)。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class PersonaProfile:
    """Agent角色配置。

    Attributes:
        name: 角色名称
        age: 年龄
        gender: 性别
        personality_traits: 性格特征列表
        background: 背景故事描述
        speaking_style: 说话风格
        birthday: 生日
        interests: 兴趣爱好列表
    """

    name: str
    age: Optional[int] = None
    gender: str = "unknown"
    personality_traits: list[str] = field(default_factory=list)
    background: str = ""
    speaking_style: str = "friendly"
    birthday: Optional[str] = None
    interests: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """转换为字典格式。"""
        return {
            "name": self.name,
            "age": self.age,
            "gender": self.gender,
            "personality_traits": self.personality_traits,
            "background": self.background,
            "speaking_style": self.speaking_style,
            "birthday": self.birthday,
            "interests": self.interests,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PersonaProfile":
        """从字典创建对象。"""
        return cls(
            name=data.get("name", "Assistant"),
            age=data.get("age"),
            gender=data.get("gender", "unknown"),
            personality_traits=data.get("personality_traits", []),
            background=data.get("background", ""),
            speaking_style=data.get("speaking_style", "friendly"),
            birthday=data.get("birthday"),
            interests=data.get("interests", []),
        )


@dataclass
class MemoryEntry:
    """单条记忆条目。

    Attributes:
        id: 记忆唯一标识符
        content: 记忆内容
        timestamp: 时间戳
        memory_type: 记忆类型 (episodic/preference/fact)
        importance: 重要性等级 (0.0-2.0)
        context: 关联上下文/话题
    """

    id: str
    content: str
    timestamp: float
    memory_type: str = "episodic"
    importance: float = 1.0
    context: Optional[str] = None

    def to_dict(self) -> dict:
        """转换为字典格式。"""
        return {
            "id": self.id,
            "content": self.content,
            "timestamp": self.timestamp,
            "memory_type": self.memory_type,
            "importance": self.importance,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryEntry":
        """从字典创建对象。"""
        return cls(
            id=data.get("id", ""),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", 0.0),
            memory_type=data.get("memory_type", "episodic"),
            importance=data.get("importance", 1.0),
            context=data.get("context"),
        )


class Persona:
    """人格管理器。

    管理角色的配置和记忆，支持情景记忆、偏好记忆和事实记忆的存储与检索。
    """

    def __init__(self, profile: PersonaProfile):
        """初始化人格管理器。

        Args:
            profile: 角色配置
        """
        self.profile = profile
        self.episodic_memories: list[MemoryEntry] = []  # 情景记忆：重要经历
        self.preference_memories: list[MemoryEntry] = []  # 偏好记忆：用户喜好
        self.fact_memories: list[MemoryEntry] = []  # 事实记忆：已知事实
        self._memory_counter = 0

    def add_memory(
        self,
        content: str,
        memory_type: str = "episodic",
        importance: float = 1.0,
        context: Optional[str] = None,
    ) -> MemoryEntry:
        """添加新记忆。

        Args:
            content: 记忆内容
            memory_type: 记忆类型 ("episodic"/"preference"/"fact")
            importance: 重要性 (0.0-2.0)
            context: 关联上下文

        Returns:
            创建的记忆条目
        """
        self._memory_counter += 1
        memory = MemoryEntry(
            id=f"mem_{self._memory_counter}_{int(datetime.now().timestamp())}",
            content=content,
            timestamp=datetime.now().timestamp(),
            memory_type=memory_type,
            importance=importance,
            context=context,
        )

        if memory_type == "preference":
            self.preference_memories.append(memory)
        elif memory_type == "fact":
            self.fact_memories.append(memory)
        else:
            self.episodic_memories.append(memory)

        return memory

    def get_recent_memories(
        self,
        limit: int = 10,
        memory_type: Optional[str] = None,
    ) -> list[MemoryEntry]:
        """获取最近的记忆。

        Args:
            limit: 返回数量限制
            memory_type: 可选的类型过滤

        Returns:
            记忆列表，按时间倒序
        """
        if memory_type == "preference":
            memories = sorted(self.preference_memories, key=lambda m: m.timestamp, reverse=True)
        elif memory_type == "fact":
            memories = sorted(self.fact_memories, key=lambda m: m.timestamp, reverse=True)
        elif memory_type == "episodic":
            memories = sorted(self.episodic_memories, key=lambda m: m.timestamp, reverse=True)
        else:
            all_memories = (
                self.episodic_memories + self.preference_memories + self.fact_memories
            )
            memories = sorted(all_memories, key=lambda m: m.timestamp, reverse=True)

        return memories[:limit]

    def search_memories(self, query: str, limit: int = 5) -> list[MemoryEntry]:
        """搜索记忆。

        基于关键词的简单记忆搜索。

        Args:
            query: 搜索关键词
            limit: 返回数量限制

        Returns:
            匹配的记忆列表
        """
        query_lower = query.lower()
        results = []
        all_memories = self.episodic_memories + self.preference_memories + self.fact_memories

        for memory in all_memories:
            if query_lower in memory.content.lower():
                results.append(memory)

        return results[:limit]

    def to_dict(self) -> dict:
        """转换为字典格式。"""
        return {
            "profile": self.profile.to_dict(),
            "episodic_memories": [m.to_dict() for m in self.episodic_memories],
            "preference_memories": [m.to_dict() for m in self.preference_memories],
            "fact_memories": [m.to_dict() for m in self.fact_memories],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Persona":
        """从字典创建对象。"""
        profile = PersonaProfile.from_dict(data.get("profile", {}))
        persona = cls(profile)

        for m in data.get("episodic_memories", []):
            persona.episodic_memories.append(MemoryEntry.from_dict(m))
        for m in data.get("preference_memories", []):
            persona.preference_memories.append(MemoryEntry.from_dict(m))
        for m in data.get("fact_memories", []):
            persona.fact_memories.append(MemoryEntry.from_dict(m))

        return persona

    def build_persona_text(self) -> str:
        """构建用于Prompt的人格描述文本。

        Returns:
            人格描述字符串
        """
        parts = [f"你叫{self.profile.name}。"]

        if self.profile.age is not None:
            parts.append(f"年龄：{self.profile.age}岁。")

        if self.profile.gender != "unknown":
            gender_map = {"male": "男性", "female": "女性", "non-binary": "非二元"}
            gender_text = gender_map.get(self.profile.gender, self.profile.gender)
            parts.append(f"性别：{gender_text}。")

        if self.profile.personality_traits:
            traits = "、".join(self.profile.personality_traits)
            parts.append(f"性格特点：{traits}。")

        if self.profile.speaking_style:
            parts.append(f"说话风格：{self.profile.speaking_style}。")

        if self.profile.background:
            parts.append(f"背景：{self.profile.background}")

        if self.profile.interests:
            interests = "、".join(self.profile.interests)
            parts.append(f"兴趣爱好：{interests}。")

        return " ".join(parts)
