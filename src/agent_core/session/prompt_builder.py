"""Session Manager 模块 - Prompt 构建封装。

封装 Brain 模块的 PromptBuilder，提供更简洁的接口。
"""

from typing import Optional

from ..brain import (
    Persona,
    MessageHistory,
    SpeakingStyleEngine,
    PromptBuilder,
    AgentConfig,
    Message,
    MessageRole,
)


class SessionPromptBuilder:
    """Session 级别的 Prompt 构建器。

    封装 Brain 模块的 PromptBuilder，简化调用。
    """

    def __init__(
        self,
        persona: Persona,
        history: MessageHistory,
        style_engine: SpeakingStyleEngine,
        config: AgentConfig,
        model_config: Optional[object] = None,
    ):
        """初始化。

        Args:
            persona: Persona 实例
            history: MessageHistory 实例
            style_engine: SpeakingStyleEngine 实例
            config: AgentConfig 配置
        """
        self._inner = PromptBuilder(
            persona=persona,
            history=history,
            style_engine=style_engine,
            config=config,
            model_config=model_config,
        )
        # 保存引用用于动态切换
        self._persona = persona
        self._history = history
        self._style_engine = style_engine
        self._config = config
        self._model_config = model_config

    def set_model_config(self, model_config: Optional[object]) -> None:
        """Bind runtime model config for tokenizer routing."""
        self._model_config = model_config
        self._inner.set_model_config(model_config)

    def build_system_prompt(self, emotion: Optional[str] = None) -> str:
        """构建系统 Prompt。

        Args:
            emotion: 当前情绪状态

        Returns:
            系统提示字符串
        """
        return self._inner.build_system_prompt(emotion)

    def build_conversation_context(
        self,
        current_message: str,
        include_history: bool = True,
        max_history_tokens: int = 2000
    ) -> str:
        """构建对话上下文（用于 API 调用）。

        Args:
            current_message: 当前用户消息
            include_history: 是否包含历史消息
            max_history_tokens: 最大历史 Token 数

        Returns:
            上下文提示字符串
        """
        # 保留参数兼容性，实际只注入当前用户消息，避免与 system prompt 重复注入上下文。
        _ = include_history, max_history_tokens
        return f"用户最新消息: {current_message}"

    def build_full_prompt(
        self,
        current_message: str,
        emotion: Optional[str] = None,
        include_history: bool = True
    ) -> tuple[str, list[Message]]:
        """构建完整 Prompt 和消息列表。

        Args:
            current_message: 当前用户消息
            emotion: 当前情绪状态
            include_history: 是否包含历史

        Returns:
            (system_prompt, messages_for_api) 元组
        """
        system_prompt = self.build_system_prompt(emotion)

        messages = []
        if include_history:
            history_messages = self._history.get_context_messages()
            for msg in history_messages:
                messages.append(Message(
                    role=msg.role,
                    content=msg.content,
                    id=msg.id,
                    timestamp=msg.timestamp,
                ))

        # 添加当前消息
        messages.append(Message(
            role=MessageRole.USER,
            content=current_message,
            id=f"user_{id(current_message)}",
            timestamp=0,
        ))

        return system_prompt, messages

    def build_history_summary_for_context(self, days: int = 3) -> str:
        """构建历史摘要上下文。

        Args:
            days: 包含最近几天的摘要

        Returns:
            历史摘要字符串
        """
        return self._inner.build_history_summary_section(days=days)

    def build_persona_context(self) -> str:
        """构建人格上下文（用于摘要生成）。

        Returns:
            人格描述字符串
        """
        return self._persona.build_persona_text()

    def build_memory_context(self, limit: int = 10) -> str:
        """构建记忆上下文。

        Args:
            limit: 最近的记忆条数

        Returns:
            记忆描述字符串
        """
        memory_cfg = getattr(self._config, "memory_injection", None)
        if memory_cfg and getattr(memory_cfg, "enabled", True):
            policy = {
                "enabled": bool(getattr(memory_cfg, "enabled", True)),
                "total_limit": min(int(getattr(memory_cfg, "total_limit", limit)), limit),
                "per_type_limit": dict(getattr(memory_cfg, "per_type_limit", {}) or {}),
                "type_weight": dict(getattr(memory_cfg, "type_weight", {}) or {}),
                "recency_half_life_days": float(getattr(memory_cfg, "recency_half_life_days", 14.0)),
                "min_importance": float(getattr(memory_cfg, "min_importance", 0.0)),
                "dedupe": bool(getattr(memory_cfg, "dedupe", True)),
                "sticky_contexts": list(getattr(memory_cfg, "sticky_contexts", []) or []),
                "query_boost": bool(getattr(memory_cfg, "query_boost", True)),
            }
            memories = self._persona.get_memories_for_injection(policy=policy)
        else:
            memories = self._persona.get_recent_memories(limit=limit)
        if not memories:
            return ""

        memory_texts = [m.content for m in memories]
        return "相关记忆:\n- " + "\n- ".join(memory_texts)
