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
from typing import Optional

from .persona import Persona
from .history import MessageHistory, MessageRole
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
        memories = self.persona.get_recent_memories(limit=limit)
        if not memories:
            return ""

        parts = ["## 近期记忆"]
        for mem in memories:
            timestamp = datetime.fromtimestamp(mem.timestamp).strftime("%Y-%m-%d")
            parts.append(f"- [{timestamp}] {mem.content}")

        return "\n".join(parts)

    def build_search_memory_section(self, query: str, limit: int = 3) -> str:
        """构建搜索相关的记忆段落。

        Args:
            query: 搜索关键词
            limit: 返回的记忆数量限制

        Returns:
            记忆描述文本
        """
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
        sections = []

        # 1. 身份定义
        sections.append(self.build_identity_section())
        sections.append("")

        # 2. 说话风格
        style_section = self.build_style_section(emotion=emotion)
        if style_section:
            sections.append(style_section)
            sections.append("")

        # 3. 近期记忆
        memory_section = self.build_memory_section()
        if memory_section:
            sections.append(memory_section)
            sections.append("")

        # 4. 历史摘要
        summary_section = self.build_history_summary_section()
        if summary_section:
            sections.append(summary_section)
            sections.append("")

        # 5. 队列消息
        queue_section = self.build_queue_section()
        if queue_section:
            sections.append(queue_section)
            sections.append("")

        # 6. 运行时信息
        sections.append(self.build_runtime_section())
        sections.append("")

        return "\n".join(sections)

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
        sections = []

        # 身份定义
        sections.append(self.build_identity_section())
        sections.append("")

        # 说话风格
        style_section = self.build_style_section(emotion=emotion)
        if style_section:
            sections.append(style_section)
            sections.append("")

        # 搜索相关的记忆
        if query:
            search_section = self.build_search_memory_section(query)
            if search_section:
                sections.append(search_section)
                sections.append("")

        # 历史摘要
        summary_section = self.build_history_summary_section()
        if summary_section:
            sections.append(summary_section)
            sections.append("")

        # 队列消息
        if include_queue:
            queue_section = self.build_queue_section(max_tokens=max_queue_tokens)
            if queue_section:
                sections.append(queue_section)
                sections.append("")

        # 运行时信息
        sections.append(self.build_runtime_section())

        return "\n".join(sections)


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
