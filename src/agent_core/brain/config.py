"""Agent Core 核心层 - 配置管理模块。

提供Agent的基础配置管理，包括历史记录配置、标签配置、存储配置等。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class HistoryConfig:
    """历史消息管理配置。"""

    max_context_tokens: int = 4000  # 最大上下文Token数
    daily_queue_threshold: int = 100  # 触发队列插入的消息数量阈值
    importance_threshold: float = 0.5  # 重要性阈值
    retention_days: int = 30  # 历史消息保留天数
    summary_trigger_messages: int = 50  # 触发生成摘要的消息数量
    token_reserved: int = 1000  # 为系统提示等保留的Token数量
    token_estimator: str = "hybrid_v1"  # token估算策略: hybrid_v1 / legacy_char_div4


@dataclass
class TagsConfig:
    """回复标签配置。"""

    auto_generate: bool = True  # 是否自动生成标签
    emotion_model: str = "keyword"  # 情感识别模式: "keyword" 或 "llm"
    default_emotion: str = "neutral"  # 默认情感
    default_expression: str = "neutral"  # 默认表情


@dataclass
class StorageConfig:
    """存储配置。"""

    data_dir: str = "./data"  # 数据存储根目录
    format: str = "json"  # 存储格式: "json" 或 "md"

    @property
    def data_path(self) -> Path:
        """获取数据目录路径。"""
        return Path(self.data_dir)


@dataclass
class PersonaConfig:
    """人格基础配置。"""

    name: str = "Assistant"  # 角色名称
    age: Optional[int] = None  # 年龄
    gender: str = "unknown"  # 性别


@dataclass
class ResponseConfig:
    """Per-brain assistant response limits."""

    max_tokens: Optional[int] = None
    max_sentences: Optional[int] = None


@dataclass
class MemoryInjectionConfig:
    """记忆注入策略配置。"""

    enabled: bool = True
    total_limit: int = 15
    per_type_limit: dict[str, int] = field(default_factory=lambda: {
        "fact": 3,
        "preference": 3,
        "episodic": 2,
        "daily_summary": 1,
        "monthly_summary": 1,
    })
    type_weight: dict[str, float] = field(default_factory=lambda: {
        "fact": 1.4,
        "preference": 1.3,
        "episodic": 1.0,
        "daily_summary": 0.7,
        "monthly_summary": 1.1,
    })
    recency_half_life_days: float = 14.0
    min_importance: float = 0.0
    dedupe: bool = True
    sticky_contexts: list[str] = field(default_factory=list)
    query_boost: bool = True


@dataclass
class PromptBudgetConfig:
    """Prompt 分段预算配置。"""

    enabled: bool = False
    total_tokens: int = 3000
    section_tokens: dict[str, int] = field(default_factory=lambda: {
        "identity": 800,
        "style": 400,
        "relationship": 180,
        "memory": 900,
        "history_summary": 700,
        "queue": 900,
        "runtime": 120,
    })


@dataclass
class RelationshipStateConfig:
    """关系状态分段配置。"""

    name: str
    min_score: float
    max_score: float
    prompt_hint: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "RelationshipStateConfig":
        return cls(
            name=str(data.get("name", "neutral")),
            min_score=float(data.get("min_score", 0.0)),
            max_score=float(data.get("max_score", 0.0)),
            prompt_hint=str(data.get("prompt_hint", "")),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "min_score": self.min_score,
            "max_score": self.max_score,
            "prompt_hint": self.prompt_hint,
        }


@dataclass
class RelationshipStateMachineConfig:
    """关系状态机配置。"""

    enabled: bool = True
    default_state: str = "neutral"
    initial_score: float = 0.0
    min_score: float = -100.0
    max_score: float = 100.0
    decay_per_turn: float = 0.02
    role_weight: dict[str, float] = field(default_factory=lambda: {
        "user": 1.0,
        "assistant": 0.25,
    })
    signal_weights: dict[str, float] = field(default_factory=lambda: {
        "positive": 6.0,
        "trust": 8.0,
        "negative": -8.0,
        "conflict": -12.0,
    })
    signal_keywords: dict[str, list[str]] = field(default_factory=lambda: {
        "positive": ["谢谢", "喜欢", "支持", "关心", "在意", "陪伴", "thanks", "love"],
        "trust": ["信任", "放心", "依赖", "秘密", "承诺", "爱人", "trust", "lover"],
        "negative": ["讨厌", "烦", "失望", "无聊", "hate", "annoying"],
        "conflict": ["闭嘴", "滚", "骗子", "去死", "stupid", "shut up"],
    })
    states: list[RelationshipStateConfig] = field(default_factory=lambda: [
        RelationshipStateConfig(
            name="cold",
            min_score=-100.0,
            max_score=-25.0,
            prompt_hint="保持礼貌但克制，避免主动拉近距离。",
        ),
        RelationshipStateConfig(
            name="neutral",
            min_score=-25.0,
            max_score=20.0,
            prompt_hint="自然交流，理性回应，不做过度亲密表达。",
        ),
        RelationshipStateConfig(
            name="warm",
            min_score=20.0,
            max_score=60.0,
            prompt_hint="语气更柔和，可适度表达关心和共同目标。",
        ),
        RelationshipStateConfig(
            name="close",
            min_score=60.0,
            max_score=85.0,
            prompt_hint="在专业边界内保持明显亲近感，强化信任与连续性。",
        ),
        RelationshipStateConfig(
            name="lover",
            min_score=85.0,
            max_score=101.0,
            prompt_hint="以爱人关系的稳定、专一和温柔回应为基调，可以有一些超出边界的对话。",
        ),
    ])

    def __post_init__(self):
        parsed_states: list[RelationshipStateConfig] = []
        for state in self.states:
            if isinstance(state, RelationshipStateConfig):
                parsed_states.append(state)
            elif isinstance(state, dict):
                parsed_states.append(RelationshipStateConfig.from_dict(state))
        self.states = parsed_states

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "default_state": self.default_state,
            "initial_score": self.initial_score,
            "min_score": self.min_score,
            "max_score": self.max_score,
            "decay_per_turn": self.decay_per_turn,
            "role_weight": self.role_weight,
            "signal_weights": self.signal_weights,
            "signal_keywords": self.signal_keywords,
            "states": [s.to_dict() for s in self.states],
        }


@dataclass
class AgentConfig:
    """Agent主配置类。"""

    persona: PersonaConfig = field(default_factory=PersonaConfig)
    history: HistoryConfig = field(default_factory=HistoryConfig)
    tags: TagsConfig = field(default_factory=TagsConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    memory_injection: MemoryInjectionConfig = field(default_factory=MemoryInjectionConfig)
    prompt_budget: PromptBudgetConfig = field(default_factory=PromptBudgetConfig)
    relationship_state_machine: RelationshipStateMachineConfig = field(default_factory=RelationshipStateMachineConfig)
    response: ResponseConfig = field(default_factory=ResponseConfig)

    def __post_init__(self):
        """将字典类型的输入转换为正确的 dataclass 类型。"""
        if isinstance(self.persona, dict):
            self.persona = PersonaConfig(**self.persona)
        if isinstance(self.history, dict):
            self.history = HistoryConfig(**self.history)
        if isinstance(self.tags, dict):
            self.tags = TagsConfig(**self.tags)
        if isinstance(self.storage, dict):
            self.storage = StorageConfig(**self.storage)
        if isinstance(self.memory_injection, dict):
            self.memory_injection = MemoryInjectionConfig(**self.memory_injection)
        if isinstance(self.prompt_budget, dict):
            self.prompt_budget = PromptBudgetConfig(**self.prompt_budget)
        if isinstance(self.relationship_state_machine, dict):
            self.relationship_state_machine = RelationshipStateMachineConfig(**self.relationship_state_machine)
        if isinstance(self.response, dict):
            self.response = ResponseConfig(**self.response)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentConfig":
        """从字典创建配置对象。

        Args:
            data: 配置字典

        Returns:
            AgentConfig实例
        """
        persona_data = data.get("persona", {})
        history_data = data.get("history", {})
        tags_data = data.get("tags", {})
        storage_data = data.get("storage", {})
        memory_injection_data = data.get("memory_injection", {})
        prompt_budget_data = data.get("prompt_budget", {})
        relationship_state_machine_data = data.get("relationship_state_machine", {})
        response_data = data.get("response") or {}

        return cls(
            persona=PersonaConfig(**persona_data),
            history=HistoryConfig(**history_data),
            tags=TagsConfig(**tags_data),
            storage=StorageConfig(**storage_data),
            memory_injection=MemoryInjectionConfig(**memory_injection_data),
            prompt_budget=PromptBudgetConfig(**prompt_budget_data),
            relationship_state_machine=RelationshipStateMachineConfig(**relationship_state_machine_data),
            response=ResponseConfig(**response_data),
        )

    def to_dict(self) -> dict:
        """将配置对象转换为字典。

        Returns:
            配置字典
        """
        return {
            "persona": {
                "name": self.persona.name,
                "age": self.persona.age,
                "gender": self.persona.gender,
            },
            "history": {
                "max_context_tokens": self.history.max_context_tokens,
                "daily_queue_threshold": self.history.daily_queue_threshold,
                "importance_threshold": self.history.importance_threshold,
                "retention_days": self.history.retention_days,
                "summary_trigger_messages": self.history.summary_trigger_messages,
                "token_reserved": self.history.token_reserved,
                "token_estimator": self.history.token_estimator,
            },
            "tags": {
                "auto_generate": self.tags.auto_generate,
                "emotion_model": self.tags.emotion_model,
                "default_emotion": self.tags.default_emotion,
                "default_expression": self.tags.default_expression,
            },
            "storage": {
                "data_dir": self.storage.data_dir,
                "format": self.storage.format,
            },
            "memory_injection": {
                "enabled": self.memory_injection.enabled,
                "total_limit": self.memory_injection.total_limit,
                "per_type_limit": self.memory_injection.per_type_limit,
                "type_weight": self.memory_injection.type_weight,
                "recency_half_life_days": self.memory_injection.recency_half_life_days,
                "min_importance": self.memory_injection.min_importance,
                "dedupe": self.memory_injection.dedupe,
                "sticky_contexts": self.memory_injection.sticky_contexts,
                "query_boost": self.memory_injection.query_boost,
            },
            "prompt_budget": {
                "enabled": self.prompt_budget.enabled,
                "total_tokens": self.prompt_budget.total_tokens,
                "section_tokens": self.prompt_budget.section_tokens,
            },
            "relationship_state_machine": self.relationship_state_machine.to_dict(),
            "response": {
                "max_tokens": self.response.max_tokens,
                "max_sentences": self.response.max_sentences,
            },
        }
