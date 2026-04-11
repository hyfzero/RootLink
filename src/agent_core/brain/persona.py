"""Agent Core 核心层 - 人格模块。

定义Agent角色的人格特质，包括基本资料、背景故事和记忆系统。
支持三种记忆类型：情景记忆(episodic)、偏好记忆(preference)、事实记忆(fact)。
"""

from dataclasses import dataclass, field
from datetime import datetime
import math
import time
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
    relationship_state: str = "neutral"
    relationship_score: float = 0.0
    relationship_updated_at: Optional[float] = None

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
            "relationship_state": self.relationship_state,
            "relationship_score": self.relationship_score,
            "relationship_updated_at": self.relationship_updated_at,
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
            relationship_state=data.get("relationship_state", "neutral"),
            relationship_score=float(data.get("relationship_score", 0.0)),
            relationship_updated_at=data.get("relationship_updated_at"),
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

    管理角色的配置和记忆，支持情景记忆、偏好记忆、事实记忆、日终总结和月终总结的存储与检索。
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
        self.daily_summary_memories: list[MemoryEntry] = []  # 日终总结记忆
        self.monthly_summary_memories: list[MemoryEntry] = []  # 月终总结记忆
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
            memory_type: 记忆类型 ("episodic"/"preference"/"fact"/"daily_summary"/"monthly_summary")
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

        if memory_type == "daily_summary":
            self.daily_summary_memories.append(memory)
        elif memory_type == "monthly_summary":
            self.monthly_summary_memories.append(memory)
        elif memory_type == "preference":
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
        if memory_type == "daily_summary":
            memories = sorted(self.daily_summary_memories, key=lambda m: m.timestamp, reverse=True)
        elif memory_type == "monthly_summary":
            memories = sorted(self.monthly_summary_memories, key=lambda m: m.timestamp, reverse=True)
        elif memory_type == "preference":
            memories = sorted(self.preference_memories, key=lambda m: m.timestamp, reverse=True)
        elif memory_type == "fact":
            memories = sorted(self.fact_memories, key=lambda m: m.timestamp, reverse=True)
        elif memory_type == "episodic":
            memories = sorted(self.episodic_memories, key=lambda m: m.timestamp, reverse=True)
        else:
            all_memories = (
                self.episodic_memories + self.preference_memories + self.fact_memories +
                self.daily_summary_memories + self.monthly_summary_memories
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
        all_memories = (
            self.episodic_memories + self.preference_memories + self.fact_memories +
            self.daily_summary_memories + self.monthly_summary_memories
        )

        for memory in all_memories:
            if query_lower in memory.content.lower():
                results.append(memory)

        return results[:limit]

    def get_relationship_snapshot(self, policy: Optional[dict] = None) -> dict:
        """获取当前关系状态快照。"""
        policy = policy or {}
        default_state = str(policy.get("default_state", "neutral"))
        initial_score = float(policy.get("initial_score", 0.0))

        state = self.profile.relationship_state or default_state
        score = float(self.profile.relationship_score if self.profile.relationship_score is not None else initial_score)
        updated_at = self.profile.relationship_updated_at

        hint = ""
        for state_cfg in (policy.get("states", []) or []):
            if isinstance(state_cfg, dict) and state_cfg.get("name") == state:
                hint = str(state_cfg.get("prompt_hint", ""))
                break

        return {
            "state": state,
            "score": score,
            "updated_at": updated_at,
            "prompt_hint": hint,
        }

    def update_relationship_state(
        self,
        content: str,
        role: str = "user",
        policy: Optional[dict] = None,
    ) -> dict:
        """按配置状态机更新关系状态。"""
        policy = policy or {}
        if not bool(policy.get("enabled", False)):
            return self.get_relationship_snapshot(policy)

        text = (content or "").lower()
        states = [s for s in (policy.get("states", []) or []) if isinstance(s, dict)]
        default_state = str(policy.get("default_state", "neutral"))

        min_score = float(policy.get("min_score", -100.0))
        max_score = float(policy.get("max_score", 100.0))
        decay_per_turn = float(policy.get("decay_per_turn", 0.0))
        decay_per_turn = min(max(decay_per_turn, 0.0), 1.0)

        role_weight = policy.get("role_weight", {}) or {}
        signal_weights = policy.get("signal_weights", {}) or {}
        signal_keywords = policy.get("signal_keywords", {}) or {}

        score = float(self.profile.relationship_score if self.profile.relationship_score is not None else policy.get("initial_score", 0.0))
        if decay_per_turn > 0:
            score *= (1.0 - decay_per_turn)

        delta = 0.0
        for signal, keywords in signal_keywords.items():
            if not isinstance(keywords, list) or not keywords:
                continue
            weight = float(signal_weights.get(signal, 0.0))
            hit_count = 0
            for kw in keywords:
                kw_str = str(kw).strip().lower()
                if kw_str and kw_str in text:
                    hit_count += 1
            delta += hit_count * weight

        delta *= float(role_weight.get(role, 1.0))
        score += delta
        score = max(min_score, min(max_score, score))

        # 由 score 映射状态
        state = default_state
        if states:
            sorted_states = sorted(states, key=lambda s: float(s.get("min_score", 0.0)))
            for idx, state_cfg in enumerate(sorted_states):
                low = float(state_cfg.get("min_score", min_score))
                high = float(state_cfg.get("max_score", max_score))
                is_last = idx == len(sorted_states) - 1
                in_range = (low <= score <= high) if is_last else (low <= score < high)
                if in_range:
                    state = str(state_cfg.get("name", default_state))
                    break

        self.profile.relationship_score = score
        self.profile.relationship_state = state
        self.profile.relationship_updated_at = time.time()

        return self.get_relationship_snapshot(policy)

    def get_memories_for_injection(
        self,
        policy: Optional[dict] = None,
        query: Optional[str] = None,
    ) -> list[MemoryEntry]:
        """按配置策略选择要注入 Prompt 的记忆。"""
        policy = policy or {}
        if not bool(policy.get("enabled", True)):
            return self.get_recent_memories(limit=10)

        total_limit = int(policy.get("total_limit", 8))
        if total_limit <= 0:
            return []

        per_type_limit: dict[str, int] = policy.get("per_type_limit", {}) or {}
        type_weight: dict[str, float] = policy.get("type_weight", {}) or {}
        min_importance = float(policy.get("min_importance", 0.0))
        half_life_days = max(0.1, float(policy.get("recency_half_life_days", 14.0)))
        dedupe = bool(policy.get("dedupe", True))
        sticky_contexts = [s for s in (policy.get("sticky_contexts", []) or []) if isinstance(s, str)]
        query_boost = bool(policy.get("query_boost", True))
        query_lower = (query or "").strip().lower()

        all_memories = (
            self.episodic_memories
            + self.preference_memories
            + self.fact_memories
            + self.daily_summary_memories
            + self.monthly_summary_memories
        )

        now_ts = time.time()

        def is_sticky(memory: MemoryEntry) -> bool:
            if not sticky_contexts:
                return False
            context = (memory.context or "").lower()
            return any(s.lower() in context for s in sticky_contexts)

        def score(memory: MemoryEntry) -> float:
            type_w = float(type_weight.get(memory.memory_type, 1.0))
            age_days = max(0.0, (now_ts - memory.timestamp) / 86400.0)
            recency = math.exp(-math.log(2) * (age_days / half_life_days))
            value = max(0.0, memory.importance) * type_w * recency
            if query_lower and query_boost:
                haystack = f"{memory.content}\n{memory.context or ''}".lower()
                if query_lower in haystack:
                    value *= 1.25
            if is_sticky(memory):
                value *= 1.3
            return value

        # 过滤候选（sticky 记忆可越过 min_importance）
        candidates = [
            m
            for m in all_memories
            if (m.importance >= min_importance) or is_sticky(m)
        ]
        candidates.sort(key=score, reverse=True)

        selected: list[MemoryEntry] = []
        selected_ids: set[str] = set()
        per_type_used: dict[str, int] = {}
        seen_keys: set[str] = set()

        def memory_key(memory: MemoryEntry) -> str:
            return f"{memory.memory_type}:{(memory.context or '').strip()}:{memory.content.strip()}"

        def try_add(memory: MemoryEntry, ignore_type_limit: bool = False) -> bool:
            if memory.id in selected_ids:
                return False
            if len(selected) >= total_limit:
                return False
            if not ignore_type_limit:
                type_cap = int(per_type_limit.get(memory.memory_type, total_limit))
                if type_cap <= 0:
                    return False
                if per_type_used.get(memory.memory_type, 0) >= type_cap:
                    return False
            if dedupe:
                key = memory_key(memory)
                if key in seen_keys:
                    return False
                seen_keys.add(key)
            selected.append(memory)
            selected_ids.add(memory.id)
            per_type_used[memory.memory_type] = per_type_used.get(memory.memory_type, 0) + 1
            return True

        # 先注入 sticky 上下文
        for memory in candidates:
            if is_sticky(memory):
                try_add(memory, ignore_type_limit=True)

        # 再按配额注入
        for memory in candidates:
            try_add(memory)

        # 保持时间顺序（便于模型理解）
        selected.sort(key=lambda m: m.timestamp)
        return selected

    def to_dict(self) -> dict:
        """转换为字典格式。"""
        return {
            "profile": self.profile.to_dict(),
            "episodic_memories": [m.to_dict() for m in self.episodic_memories],
            "preference_memories": [m.to_dict() for m in self.preference_memories],
            "fact_memories": [m.to_dict() for m in self.fact_memories],
            "daily_summary_memories": [m.to_dict() for m in self.daily_summary_memories],
            "monthly_summary_memories": [m.to_dict() for m in self.monthly_summary_memories],
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
        for m in data.get("daily_summary_memories", []):
            persona.daily_summary_memories.append(MemoryEntry.from_dict(m))
        for m in data.get("monthly_summary_memories", []):
            persona.monthly_summary_memories.append(MemoryEntry.from_dict(m))

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
