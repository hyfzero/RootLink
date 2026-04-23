"""Agent Core 核心层 - Prompt构建器模块。

提供分段的Prompt构建功能，参考OpenClaw的系统提示构建方式。

构建顺序：
1. 身份定义 (Identity)
2. 人格特点 (Personality)
3. 近期记忆 (Recent Memories)
4. 历史摘要 (History Summaries)
5. 队列消息 (Queue Messages)
6. 运行时信息 (Runtime Info)

灵感来源：
- src/agents/system-prompt.ts (完整Prompt组合)
- src/auto-reply/reply/memory-flush.ts (每日记忆格式)
- src/agents/memory-search.ts (上下文搜索)
"""

from datetime import datetime
from typing import Any, Optional

from .persona import Persona
from .history import (
    MessageHistory,
    MessageRole,
    build_tokenizer_resolver,
    normalize_token_estimator,
)
from .config import AgentConfig
from .speaking_style import SpeakingStyleEngine


def format_message_for_context(message) -> str:
    """格式化单条消息为上下文字符串。

    Args:
        message: Message对象

    Returns:
        格式化的字符串
    """
    role = message.role.value if hasattr(message.role, "value") else message.role
    content = message.content if hasattr(message.content, "content") else message.content
    return f"[{role}] {content}"


def format_messages_for_context(messages: list) -> str:
    """格式化多条消息为上下文字符串。

    Args:
        messages: Message列表

    Returns:
        格式化的字符串
    """
    if not messages:
        return ""
    return "\n".join(format_message_for_context(m) for m in messages)


def format_summary_for_context(summary) -> str:
    """格式化每日摘要为上下文字符串。

    Args:
        summary: DailySummary对象

    Returns:
        格式化的字符串
    """
    date = summary.date if hasattr(summary, "date") else summary.get("date", "")
    summary_text = summary.summary_text if hasattr(summary, "summary_text") else summary.get("summary_text", "")
    topics = summary.topics if hasattr(summary, "topics") else summary.get("topics", [])

    parts = [f"## {date}"]
    parts.append(summary_text)
    if topics:
        parts.append(f"话题：{', '.join(topics)}")
    return "\n".join(parts)


class PromptBuilder:
    """Prompt构建器。

    参考OpenClaw的分段式Prompt构建方式。
    """

    def __init__(
        self,
        persona: Persona,
        history: Optional[MessageHistory] = None,
        config: Optional[AgentConfig] = None,
        style_engine: Optional[SpeakingStyleEngine] = None,
        model_config: Optional[object] = None,
    ):
        """初始化Prompt构建器。

        Args:
            persona: Persona对象
            history: 可选的MessageHistory对象
            config: 可选的AgentConfig对象
            style_engine: 可选的说话风格引擎
        """
        self.persona = persona
        self.history = history
        self.config = config or AgentConfig()
        self.style_engine = style_engine
        self.model_config = model_config
        self._resolver_cache = None
        self._resolver_cache_key = None

    def set_model_config(self, model_config: Optional[object]) -> None:
        """Bind runtime model config for tokenizer routing."""
        self.model_config = model_config
        self._resolver_cache = None
        self._resolver_cache_key = None

    def _memory_policy_to_dict(self, limit: Optional[int] = None) -> dict[str, Any]:
        """将 memory_injection 配置转换为字典策略。"""
        policy_cfg = getattr(self.config, "memory_injection", None)
        if policy_cfg is None:
            return {"enabled": False}

        total_limit = int(getattr(policy_cfg, "total_limit", limit or 8))
        if limit is not None and limit > 0:
            total_limit = min(total_limit, limit)

        return {
            "enabled": bool(getattr(policy_cfg, "enabled", True)),
            "total_limit": total_limit,
            "per_type_limit": dict(getattr(policy_cfg, "per_type_limit", {}) or {}),
            "type_weight": dict(getattr(policy_cfg, "type_weight", {}) or {}),
            "recency_half_life_days": float(getattr(policy_cfg, "recency_half_life_days", 14.0)),
            "min_importance": float(getattr(policy_cfg, "min_importance", 0.0)),
            "dedupe": bool(getattr(policy_cfg, "dedupe", True)),
            "sticky_contexts": list(getattr(policy_cfg, "sticky_contexts", []) or []),
            "query_boost": bool(getattr(policy_cfg, "query_boost", True)),
        }

    def _prompt_budget_to_dict(self) -> dict[str, Any]:
        """将 prompt_budget 配置转换为可执行预算。"""
        budget_cfg = getattr(self.config, "prompt_budget", None)
        if budget_cfg is None:
            return {"enabled": False}

        return {
            "enabled": bool(getattr(budget_cfg, "enabled", False)),
            "total_tokens": int(getattr(budget_cfg, "total_tokens", 0)),
            "section_tokens": dict(getattr(budget_cfg, "section_tokens", {}) or {}),
        }

    def _relationship_policy_to_dict(self) -> dict[str, Any]:
        """将 relationship_state_machine 配置转换为策略字典。"""
        relation_cfg = getattr(self.config, "relationship_state_machine", None)
        if relation_cfg is None:
            return {"enabled": False}

        raw_states = list(getattr(relation_cfg, "states", []) or [])
        states: list[dict[str, Any]] = []
        for state in raw_states:
            if hasattr(state, "to_dict"):
                states.append(state.to_dict())
            elif isinstance(state, dict):
                states.append(state)

        return {
            "enabled": bool(getattr(relation_cfg, "enabled", False)),
            "default_state": str(getattr(relation_cfg, "default_state", "neutral")),
            "initial_score": float(getattr(relation_cfg, "initial_score", 0.0)),
            "min_score": float(getattr(relation_cfg, "min_score", -100.0)),
            "max_score": float(getattr(relation_cfg, "max_score", 100.0)),
            "decay_per_turn": float(getattr(relation_cfg, "decay_per_turn", 0.0)),
            "role_weight": dict(getattr(relation_cfg, "role_weight", {}) or {}),
            "signal_weights": dict(getattr(relation_cfg, "signal_weights", {}) or {}),
            "signal_keywords": dict(getattr(relation_cfg, "signal_keywords", {}) or {}),
            "states": states,
        }

    def _token_estimator(self) -> str:
        """Get token estimator strategy from config with safe fallback."""
        history_cfg = getattr(self.config, "history", None)
        estimator = getattr(history_cfg, "token_estimator", "hybrid_v1")
        return normalize_token_estimator(estimator)

    def _estimate_tokens(self, text: str) -> int:
        """Estimate tokens with the same strategy used by history/storage."""
        estimator = self._token_estimator()
        model_provider = getattr(self.model_config, "provider", None)
        model_name = getattr(self.model_config, "name", None)
        model_mode = getattr(self.model_config, "tokenizer_mode", None)
        model_fallback = getattr(self.model_config, "tokenizer_fallback", None)
        cache_key = (
            estimator,
            str(model_provider) if model_provider is not None else None,
            model_name,
            model_mode,
            model_fallback,
        )
        if self._resolver_cache is None or self._resolver_cache_key != cache_key:
            self._resolver_cache = build_tokenizer_resolver(
                token_estimator=estimator,
                model_config=self.model_config,
            )
            self._resolver_cache_key = cache_key
        return self._resolver_cache.count_text(text).tokens

    def _truncate_text_by_tokens(self, text: str, max_tokens: Optional[int]) -> str:
        """按近似 token 预算裁剪文本。"""
        if not text:
            return ""
        if max_tokens is None:
            return text
        if max_tokens <= 0:
            return ""
        if self._estimate_tokens(text) <= max_tokens:
            return text

        low, high = 0, len(text)
        while low < high:
            mid = (low + high + 1) // 2
            candidate = text[:mid].rstrip()
            if self._estimate_tokens(candidate) <= max_tokens:
                low = mid
            else:
                high = mid - 1

        if low <= 0:
            return ""

        clipped = text[:low].rstrip()
        if low < len(text):
            suffix = "..."
            while clipped and self._estimate_tokens(f"{clipped}{suffix}") > max_tokens:
                clipped = clipped[:-1].rstrip()
            if clipped and self._estimate_tokens(suffix) <= max_tokens:
                clipped = f"{clipped}{suffix}"
        return clipped

    def _compose_sections(self, sections: list[tuple[str, str]]) -> str:
        """按配置拼接并执行分段预算与总预算。"""
        filtered = [(name, text) for name, text in sections if text]
        if not filtered:
            return ""

        budget = self._prompt_budget_to_dict()
        if not budget.get("enabled", False):
            return "\n\n".join(text for _, text in filtered)

        section_limits: dict[str, int] = budget.get("section_tokens", {}) or {}
        section_trimmed: list[tuple[str, str]] = []
        for name, text in filtered:
            limit = section_limits.get(name)
            if isinstance(limit, (int, float)):
                text = self._truncate_text_by_tokens(text, int(limit))
            if text:
                section_trimmed.append((name, text))

        total_limit = int(budget.get("total_tokens", 0))
        if total_limit <= 0:
            return "\n\n".join(text for _, text in section_trimmed)

        final_sections: list[str] = []
        used_tokens = 0
        for _, text in section_trimmed:
            remaining = total_limit - used_tokens
            if remaining <= 0:
                break
            text_tokens = self._estimate_tokens(text)
            if text_tokens <= remaining:
                final_sections.append(text)
                used_tokens += text_tokens
                continue

            clipped = self._truncate_text_by_tokens(text, remaining)
            if clipped:
                final_sections.append(clipped)
                used_tokens += self._estimate_tokens(clipped)
            break

        composed = "\n\n".join(final_sections)
        if self._estimate_tokens(composed) > total_limit:
            composed = self._truncate_text_by_tokens(composed, total_limit)
        return composed

    def build_identity_section(self) -> str:
        """构建身份/角色定义段落。

        Returns:
            身份描述文本
        """
        return self.persona.build_persona_text()

    def build_style_section(self, emotion: Optional[str] = None) -> str:
        """构建说话风格指导段落。

        Args:
            emotion: 可选的当前情绪，会影响风格调整

        Returns:
            风格指导文本
        """
        if not self.style_engine:
            return ""

        style_prompt = self.style_engine.build_style_prompt(emotion=emotion)
        if not style_prompt:
            return ""

        parts = ["## 说话风格"]
        parts.append(style_prompt)
        return "\n".join(parts)

    def build_memory_section(self, limit: int = 5) -> str:
        """构建近期记忆段落。

        Args:
            limit: 返回的记忆数量限制

        Returns:
            记忆描述文本
        """
        policy = self._memory_policy_to_dict(limit=limit)
        if policy.get("enabled", False):
            memories = self.persona.get_memories_for_injection(policy=policy)
        else:
            memories = self.persona.get_recent_memories(limit=limit)
        if not memories:
            return ""

        parts = ["## 近期记忆"]
        for mem in memories:
            timestamp = datetime.fromtimestamp(mem.timestamp).strftime("%Y-%m-%d")
            parts.append(f"- [{timestamp}] {mem.content}")

        return "\n".join(parts)

    def build_relationship_section(self) -> str:
        """构建关系状态段落。"""
        policy = self._relationship_policy_to_dict()
        if not policy.get("enabled", False):
            return ""

        snapshot = self.persona.get_relationship_snapshot(policy=policy)
        state = snapshot.get("state", "neutral")
        score = float(snapshot.get("score", 0.0))
        hint = snapshot.get("prompt_hint", "")

        parts = [
            "## 关系状态",
            f"当前阶段：{state}",
            f"关系分值：{score:.2f}",
        ]
        if hint:
            parts.append(f"互动指引：{hint}")

        return "\n".join(parts)

    def build_personality_state_section(self) -> str:
        """构建运行时人格状态段落。"""
        state_text = self.persona.build_personality_state_text()
        if not state_text:
            return ""

        return "\n".join([
            "## 当前人格状态",
            state_text,
        ])

    def build_search_memory_section(self, query: str, limit: int = 3) -> str:
        """构建搜索相关的记忆段落。

        Args:
            query: 搜索关键词
            limit: 返回的记忆数量限制

        Returns:
            记忆描述文本
        """
        policy = self._memory_policy_to_dict(limit=limit)
        if policy.get("enabled", False):
            memories = self.persona.get_memories_for_injection(policy=policy, query=query)
            query_lower = query.lower()
            matched = [
                m for m in memories
                if query_lower in f"{m.content}\n{m.context or ''}".lower()
            ]
            if matched:
                memories = matched
            elif query:
                memories = self.persona.search_memories(query, limit=limit)
        else:
            memories = self.persona.search_memories(query, limit=limit)
        if not memories:
            return ""

        parts = ["## 相关记忆"]
        for mem in memories:
            parts.append(f"- {mem.content}")

        return "\n".join(parts)

    def build_history_summary_section(self, days: int = 3) -> str:
        """构建近期对话摘要段落。

        Args:
            days: 涵盖的天数

        Returns:
            摘要描述文本
        """
        if not self.history:
            return ""

        summaries = self.history.get_recent_summaries(days=days)
        if not summaries:
            return ""

        parts = ["## 近期对话"]
        for summary in summaries:
            parts.append(format_summary_for_context(summary))

        return "\n\n".join(parts)

    def build_queue_section(self, max_tokens: Optional[int] = None) -> str:
        """构建当前队列消息段落。

        Args:
            max_tokens: 最大Token数限制

        Returns:
            消息描述文本
        """
        if not self.history:
            return ""

        messages = self.history.get_context_messages(max_tokens=max_tokens)
        if not messages:
            return ""

        parts = ["## 今日消息"]
        parts.append(format_messages_for_context(messages))

        return "\n".join(parts)

    def build_runtime_section(self, timezone: str = "Asia/Shanghai") -> str:
        """构建运行时信息段落。

        Args:
            timezone: 时区

        Returns:
            运行时信息文本
        """
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")
        day_str = now.strftime("%A")

        # 星期几的中文映射
        day_map = {
            "Monday": "星期一",
            "Tuesday": "星期二",
            "Wednesday": "星期三",
            "Thursday": "星期四",
            "Friday": "星期五",
            "Saturday": "星期六",
            "Sunday": "星期日",
        }
        day_cn = day_map.get(day_str, day_str)

        parts = [
            "## 当前时间",
            f"日期：{date_str}",
            f"时间：{time_str}",
            f"星期：{day_cn}",
        ]

        return "\n".join(parts)

    def build_system_prompt(self, emotion: Optional[str] = None) -> str:
        """构建完整的系统Prompt。

        按顺序包含所有段落。

        Args:
            emotion: 可选的当前情绪，用于风格调整

        Returns:
            完整的系统Prompt文本
        """
        sections: list[tuple[str, str]] = [
            ("identity", self.build_identity_section()),
            ("style", self.build_style_section(emotion=emotion)),
            ("relationship", self.build_relationship_section()),
            ("personality_state", self.build_personality_state_section()),
            ("memory", self.build_memory_section()),
            ("history_summary", self.build_history_summary_section()),
            ("queue", self.build_queue_section()),
            ("runtime", self.build_runtime_section()),
        ]
        return self._compose_sections(sections)

    def build_context_prompt(
        self,
        query: Optional[str] = None,
        include_queue: bool = True,
        max_queue_tokens: Optional[int] = None,
        emotion: Optional[str] = None,
    ) -> str:
        """构建上下文Prompt。

        Args:
            query: 可选的搜索关键词
            include_queue: 是否包含队列消息
            max_queue_tokens: 队列消息的最大Token数
            emotion: 可选的当前情绪，用于风格调整

        Returns:
            上下文Prompt文本
        """
        sections: list[tuple[str, str]] = [
            ("identity", self.build_identity_section()),
            ("style", self.build_style_section(emotion=emotion)),
            ("relationship", self.build_relationship_section()),
            ("personality_state", self.build_personality_state_section()),
        ]

        if query:
            sections.append(("memory", self.build_search_memory_section(query)))

        sections.append(("history_summary", self.build_history_summary_section()))

        if include_queue:
            sections.append(("queue", self.build_queue_section(max_tokens=max_queue_tokens)))

        sections.append(("runtime", self.build_runtime_section()))

        return self._compose_sections(sections)


def build_minimal_prompt(persona: Persona, message: str) -> str:
    """构建最小Prompt（仅身份和当前消息）。

    Args:
        persona: Persona对象
        message: 用户消息

    Returns:
        最小Prompt文本
    """
    identity = persona.build_persona_text()
    return f"{identity}\n\n用户：{message}\n\n助手："


def build_full_conversation_prompt(
    persona: Persona,
    history: MessageHistory,
    current_message: str,
    config: Optional[AgentConfig] = None,
    style_engine: Optional[SpeakingStyleEngine] = None,
    emotion: Optional[str] = None,
) -> str:
    """构建完整的对话Prompt。

    这是每个Agent轮次使用的主要Prompt。

    Args:
        persona: Persona对象
        history: MessageHistory对象
        current_message: 当前用户消息
        config: 可选的AgentConfig对象
        style_engine: 可选的说话风格引擎
        emotion: 可选的当前情绪

    Returns:
        完整对话Prompt文本
    """
    builder = PromptBuilder(persona, history, config, style_engine)

    # 基础上下文
    context = builder.build_context_prompt(
        query=None,
        include_queue=True,
        max_queue_tokens=config.history.max_context_tokens // 4 if config else 1000,
        emotion=emotion,
    )

    # 添加当前消息
    prompt = f"""{context}

## 当前对话

用户：{current_message}

助手："""

    return prompt


def build_memory_flush_prompt(
    date: str,
    message_count: int,
    messages: list,
) -> str:
    """构建记忆刷新Prompt。

    用于将对话内容刷新到每日记忆文件中。
    参考OpenClaw的memory-flush.ts实现。

    Args:
        date: 日期字符串
        message_count: 消息总数
        messages: 消息列表

    Returns:
        记忆刷新Prompt文本
    """
    message_previews = []
    for msg in messages[-10:]:  # 最近10条消息
        role = msg.role.value if hasattr(msg.role, "value") else msg.role
        preview = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
        role_text = {"user": "用户", "assistant": "助手", "tool": "工具", "system": "系统"}.get(role, role)
        message_previews.append(f"- [{role_text}] {preview}")

    prompt = f"""每日记忆刷新。

今天是 {date}。请从今日对话中提取重要信息并保存。

消息总数：{message_count}
最近消息：
{chr(10).join(message_previews)}

请将重要信息保存到 memory/{date}.md，遵循以下规则：
- 只保存重要的事实、偏好和决定
- 不要逐条复制每条消息
- 使用要点列表保持清晰
- 相关时包含日期信息
- 如果没有重要的事情，简单说明即可
"""
    return prompt
