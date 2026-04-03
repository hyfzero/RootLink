"""Agent Core 核心层 - 历史消息管理模块。

提供基于Token感知的历史消息管理系统，包含：
- 消息权重计算（角色权重 + 时间衰减 + 重要性）
- 每日摘要生成
- Token预算感知的消息队列

灵感来源：OpenClaw的session管理和compaction机制。
"""

import math
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


class MessageRole(Enum):
    """消息角色枚举。"""
    USER = "user"      # 用户消息
    ASSISTANT = "assistant"  # 助手回复
    SYSTEM = "system"  # 系统消息
    TOOL = "tool"      # 工具调用/结果


@dataclass
class Message:
    """单条对话消息。

    Attributes:
        id: 消息唯一标识符
        role: 消息角色
        content: 消息内容
        timestamp: 时间戳
        token_count: Token数量估计
        weight: 消息权重
        is_important: 是否标记为重要
        tags: 消息标签列表
        tool_name: 关联的工具名称
        reply_to: 回复的消息ID
    """

    id: str
    role: MessageRole
    content: str
    timestamp: float
    token_count: Optional[int] = None
    weight: float = 1.0
    is_important: bool = False
    tags: list[str] = field(default_factory=list)
    tool_name: Optional[str] = None
    reply_to: Optional[str] = None

    def __post_init__(self):
        """确保role是MessageRole枚举类型。"""
        if isinstance(self.role, str):
            self.role = MessageRole(self.role)

    def to_dict(self) -> dict:
        """转换为字典格式。"""
        return {
            "id": self.id,
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp,
            "token_count": self.token_count,
            "weight": self.weight,
            "is_important": self.is_important,
            "tags": self.tags,
            "tool_name": self.tool_name,
            "reply_to": self.reply_to,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        """从字典创建对象。"""
        return cls(
            id=data.get("id", ""),
            role=MessageRole(data.get("role", "user")),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", 0.0),
            token_count=data.get("token_count"),
            weight=data.get("weight", 1.0),
            is_important=data.get("is_important", False),
            tags=data.get("tags", []),
            tool_name=data.get("tool_name"),
            reply_to=data.get("reply_to"),
        )


@dataclass
class DailySummary:
    """每日对话摘要。

    Attributes:
        date: 日期字符串 (YYYY-MM-DD)
        summary_text: 摘要文本
        important_messages: 重要消息ID列表
        topics: 讨论话题列表
        message_count: 消息总数
        created_at: 创建时间戳
        emotional_tone: 情感基调 (LLM驱动新增)
        user_preferences: 用户偏好列表 (LLM驱动新增)
        unfinished_topics: 未完成话题列表 (LLM驱动新增)
    """

    date: str
    summary_text: str
    important_messages: list[str]
    topics: list[str]
    message_count: int
    created_at: float
    emotional_tone: Optional[str] = None  # LLM驱动新增
    user_preferences: list[str] = field(default_factory=list)  # LLM驱动新增
    unfinished_topics: list[str] = field(default_factory=list)  # LLM驱动新增

    def to_dict(self) -> dict:
        """转换为字典格式。"""
        return {
            "date": self.date,
            "summary_text": self.summary_text,
            "important_messages": self.important_messages,
            "topics": self.topics,
            "message_count": self.message_count,
            "created_at": self.created_at,
            "emotional_tone": self.emotional_tone,
            "user_preferences": self.user_preferences,
            "unfinished_topics": self.unfinished_topics,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DailySummary":
        """从字典创建对象。"""
        return cls(
            date=data.get("date", ""),
            summary_text=data.get("summary_text", ""),
            important_messages=data.get("important_messages", []),
            topics=data.get("topics", []),
            message_count=data.get("message_count", 0),
            created_at=data.get("created_at", 0.0),
            emotional_tone=data.get("emotional_tone"),
            user_preferences=data.get("user_preferences", []),
            unfinished_topics=data.get("unfinished_topics", []),
        )


# 各角色的基础权重
ROLE_BASE_WEIGHTS = {
    MessageRole.USER: 1.0,
    MessageRole.ASSISTANT: 0.8,
    MessageRole.SYSTEM: 0.3,
    MessageRole.TOOL: 0.5,
}

# 指示重要消息的关键词模式
IMPORTANT_PATTERNS = [
    r"\b(记住|忘记|永远|绝不)\b",
    r"\b(重要|关键|必要)\b",
    r"\b(喜欢|讨厌|偏好)\b",
    r"\b(钱|价格|购买|出售)\b",
    r"\b(秘密|私密|机密)\b",
    r"\b(任务|工作|完成)\b",
    r"\b(错误|问题|修复)\b",
    # 英文关键词（多语言支持）
    r"\b(remember|forget|never|always)\b",
    r"\b(important|crucial|essential)\b",
    r"\b(love|hate|prefer)\b",
]


def estimate_tokens(text: str) -> int:
    """估算文本的Token数量。

    使用字符数除以4作为粗略估计（适用于英文）。
    对于中文等语言，每个字符可能对应更多Token。
    更精确的实现应使用tiktoken等库。

    Args:
        text: 输入文本

    Returns:
        估计的Token数量
    """
    if not text:
        return 0
    # Unicode-aware: 使用字符数而非字节数
    char_count = len(text)
    # 粗略估计：中文约1-2 token/字符，英文约1/4
    # 简化处理：总字符数 / 4
    return max(1, char_count // 4)


def calculate_message_weight(
    message: Message,
    max_age_hours: float = 168.0,  # 7天
) -> float:
    """计算消息的有效权重。

    权重由以下因素决定：
    - 基础权重（来自角色类型）
    - 时间衰减
    - 重要性加成

    Args:
        message: 消息对象
        max_age_hours: 最大年龄（小时）

    Returns:
        计算后的权重值
    """
    base_weight = ROLE_BASE_WEIGHTS.get(message.role, 0.5)

    # 时间衰减
    age_hours = (time.time() - message.timestamp) / 3600
    time_factor = max(0.1, 1.0 - (age_hours / max_age_hours))

    # 重要性加成
    importance_multiplier = 2.0 if message.is_important else 1.0

    return base_weight * time_factor * importance_multiplier


def detect_importance(content: str) -> bool:
    """根据关键词检测消息是否重要。

    Args:
        content: 消息内容

    Returns:
        是否重要
    """
    content_lower = content.lower()
    for pattern in IMPORTANT_PATTERNS:
        if re.search(pattern, content_lower, re.IGNORECASE):
            return True
    return False


class MessageQueue:
    """当日消息队列。

    当日消息先进入队列，通过特定机制才加入主上下文。
    这参考了OpenClaw的会话管理和内存刷新机制。
    """

    def __init__(self, threshold: int = 100):
        """初始化消息队列。

        Args:
            threshold: 触发flush的消息数量阈值
        """
        self.messages: list[Message] = []
        self.threshold = threshold
        self._msg_counter = 0

    def add(self, message: Message) -> None:
        """添加消息到队列。"""
        self.messages.append(message)

    def should_flush(self) -> bool:
        """检查队列是否应该flush到主历史。"""
        return len(self.messages) >= self.threshold

    def clear(self) -> list[Message]:
        """清空队列并返回所有消息。"""
        msgs = self.messages
        self.messages = []
        return msgs

    def get_weighted_sum(self) -> float:
        """获取队列中所有消息的权重总和。"""
        return sum(calculate_message_weight(m) for m in self.messages)

    def to_dict(self) -> dict:
        """转换为字典格式。"""
        return {
            "messages": [m.to_dict() for m in self.messages],
            "threshold": self.threshold,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MessageQueue":
        """从字典创建对象。"""
        queue = cls(threshold=data.get("threshold", 100))
        queue.messages = [Message.from_dict(m) for m in data.get("messages", [])]
        return queue


class DailyHistory:
    """单日历史记录管理器。"""

    def __init__(self, date_str: str):
        """初始化当日历史。

        Args:
            date_str: 日期字符串 (YYYY-MM-DD)
        """
        self.date = date_str
        self.messages: list[Message] = []
        self.summary: Optional[DailySummary] = None
        self._msg_counter = 0

    def add_message(self, message: Message) -> None:
        """添加消息到当日历史。"""
        self.messages.append(message)

    def get_messages(self) -> list[Message]:
        """获取当日所有消息。"""
        return self.messages

    def generate_summary(self, config: Optional[dict] = None) -> DailySummary:
        """生成当日对话摘要。

        算法：
        1. 对每条消息打分
        2. 选择得分最高的N条消息
        3. 生成摘要文本

        Args:
            config: 可选的配置字典

        Returns:
            每日摘要对象
        """
        if not self.messages:
            return DailySummary(
                date=self.date,
                summary_text="今日无消息。",
                important_messages=[],
                topics=[],
                message_count=0,
                created_at=time.time(),
            )

        # 消息评分
        scored = []
        for msg in self.messages:
            score = 0.0

            # 工具调用得高分
            if msg.role == MessageRole.TOOL and msg.tool_name:
                score += 3.0

            # 用户消息带有明确意图
            if msg.role == MessageRole.USER:
                score += 1.0
                if detect_importance(msg.content):
                    score += 2.0

            # 显式标记的重要消息
            if msg.is_important:
                score += 2.0

            # 长度因素（中等长度优先）
            token_len = msg.token_count or estimate_tokens(msg.content)
            if 10 < token_len < 200:
                score += 0.5

            scored.append((msg, score))

        # 按得分降序排序
        scored.sort(key=lambda x: x[1], reverse=True)

        # 获取top消息
        top_messages = scored[:5]
        important_ids = [msg.id for msg, _ in top_messages]

        # 提取话题
        topics = self._extract_topics()

        # 构建摘要文本
        if top_messages:
            summary_parts = []
            for msg, score in top_messages[:3]:
                preview = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
                role_text = {"user": "用户", "assistant": "助手", "tool": "工具"}.get(msg.role.value, msg.role.value)
                summary_parts.append(f"- [{role_text}] {preview}")
            summary_text = "重要事件：\n" + "\n".join(summary_parts)
        else:
            summary_text = f"今日共{len(self.messages)}条消息。"

        summary = DailySummary(
            date=self.date,
            summary_text=summary_text,
            important_messages=important_ids,
            topics=topics,
            message_count=len(self.messages),
            created_at=time.time(),
        )

        self.summary = summary
        return summary

    def _extract_topics(self) -> list[str]:
        """基于关键词提取话题。"""
        topic_keywords = {
            "工作": ["工作", "项目", "会议", "截止日期", "任务"],
            "个人": ["家庭", "朋友", "家", "生活"],
            "技术": ["电脑", "代码", "软件", "程序", "bug"],
            "购物": ["买", "商店", "订单", "快递", "价格"],
            "娱乐": ["电影", "游戏", "音乐", "书籍", "节目"],
            # 英文话题
            "work": ["work", "project", "meeting", "deadline", "task"],
            "personal": ["family", "friend", "home", "life"],
            "technology": ["computer", "code", "software", "app", "bug"],
            "shopping": ["buy", "shop", "order", "deliver", "price"],
            "entertainment": ["movie", "game", "music", "book", "show"],
        }

        all_text = " ".join(m.content.lower() for m in self.messages)
        found_topics = []

        for topic, keywords in topic_keywords.items():
            if any(kw in all_text for kw in keywords):
                found_topics.append(topic)

        return found_topics[:5]

    def to_dict(self) -> dict:
        """转换为字典格式。"""
        return {
            "date": self.date,
            "messages": [m.to_dict() for m in self.messages],
            "summary": self.summary.to_dict() if self.summary else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DailyHistory":
        """从字典创建对象。"""
        history = cls(date_str=data.get("date", ""))
        history.messages = [Message.from_dict(m) for m in data.get("messages", [])]
        summary_data = data.get("summary")
        if summary_data:
            history.summary = DailySummary.from_dict(summary_data)
        return history


class MessageHistory:
    """主历史记录管理器。

    提供Token感知的历史消息选择和管理功能。
    参考OpenClaw的compact.ts和history.ts实现。
    """

    def __init__(
        self,
        max_context_tokens: int = 4000,
        token_reserved: int = 1000,
        retention_days: int = 30,
    ):
        """初始化历史管理器。

        Args:
            max_context_tokens: 最大上下文Token数
            token_reserved: 为系统提示保留的Token数
            retention_days: 历史消息保留天数
        """
        self.max_context_tokens = max_context_tokens
        self.token_reserved = token_reserved
        self.retention_days = retention_days

        self.daily_histories: dict[str, DailyHistory] = {}  # 日期 -> 当日历史
        self.daily_summaries: dict[str, DailySummary] = {}  # 日期 -> 每日摘要
        self.current_queue = MessageQueue()

        self._today: Optional[str] = None
        self._msg_counter = 0

    @property
    def today_str(self) -> str:
        """获取今日日期字符串。"""
        if self._today is None:
            self._today = datetime.now().strftime("%Y-%m-%d")
        return self._today

    def _get_or_create_daily(self, date: Optional[str] = None) -> DailyHistory:
        """获取或创建当日历史记录。"""
        date_str = date or self.today_str
        if date_str not in self.daily_histories:
            self.daily_histories[date_str] = DailyHistory(date_str)
        return self.daily_histories[date_str]

    def add_message(
        self,
        content: str,
        role: MessageRole,
        tool_name: Optional[str] = None,
        is_important: bool = False,
        tags: Optional[list[str]] = None,
        timestamp: Optional[float] = None,
    ) -> Message:
        """添加消息到历史。

        Args:
            content: 消息内容
            role: 消息角色
            tool_name: 关联工具名
            is_important: 是否重要
            tags: 标签列表
            timestamp: 可选的时间戳

        Returns:
            创建的消息对象
        """
        self._msg_counter += 1
        ts = timestamp or time.time()

        # 检查是否包含重要关键词
        if not is_important and role == MessageRole.USER:
            is_important = detect_importance(content)

        message = Message(
            id=f"msg_{self._msg_counter}_{int(ts)}",
            role=role,
            content=content,
            timestamp=ts,
            token_count=estimate_tokens(content),
            weight=ROLE_BASE_WEIGHTS.get(role, 0.5),
            is_important=is_important,
            tags=tags or [],
            tool_name=tool_name,
        )

        # 添加到当日历史
        daily = self._get_or_create_daily()
        daily.add_message(message)

        # 也添加到队列
        self.current_queue.add(message)

        return message

    def should_trigger_queue_insert(self) -> bool:
        """检查是否应该触发队列插入到上下文。"""
        return self.current_queue.should_flush()

    def get_context_messages(
        self,
        max_tokens: Optional[int] = None,
    ) -> list[Message]:
        """获取在Token预算内的上下文消息。

        算法：
        1. 计算可用预算
        2. 收集近期的每日摘要
        3. 按权重添加消息直到预算用尽
        4. 保持时间顺序

        Args:
            max_tokens: 最大Token数限制

        Returns:
            消息列表
        """
        budget = max_tokens or (self.max_context_tokens - self.token_reserved)
        result: list[Message] = []

        # 获取近3天的摘要（约占预算25%）
        dates = sorted(self.daily_summaries.keys(), reverse=True)[:3]
        summary_tokens = 0
        for date_str in dates:
            summary = self.daily_summaries[date_str]
            tokens = estimate_tokens(summary.summary_text)
            if summary_tokens + tokens <= budget // 4:
                summary_tokens += tokens

        # 获取当日队列消息
        queue_msgs = self.current_queue.messages.copy()

        # 按权重排序
        queue_msgs.sort(key=lambda m: calculate_message_weight(m), reverse=True)

        # 按预算添加消息
        for msg in queue_msgs:
            tokens = msg.token_count or estimate_tokens(msg.content)
            if tokens <= budget:
                result.append(msg)
                budget -= tokens
            else:
                break

        # 保持时间顺序
        result.sort(key=lambda m: m.timestamp)

        return result

    def finalize_day(self) -> DailySummary:
        """结束当日并生成摘要。

        在每日结束时或达到阈值时调用。

        Returns:
            每日摘要对象
        """
        daily = self._get_or_create_daily()
        summary = daily.generate_summary()

        self.daily_summaries[self.today_str] = summary
        self.current_queue.clear()

        return summary

    def cleanup_old_data(self) -> int:
        """清理超过保留期的历史数据。

        Returns:
            清理的天数
        """
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        cutoff_str = cutoff.strftime("%Y-%m-%d")

        removed = 0
        for date_str in list(self.daily_histories.keys()):
            if date_str < cutoff_str:
                del self.daily_histories[date_str]
                if date_str in self.daily_summaries:
                    del self.daily_summaries[date_str]
                removed += 1

        return removed

    def get_recent_summaries(self, days: int = 3) -> list[DailySummary]:
        """获取近期的每日摘要。

        Args:
            days: 天数

        Returns:
            摘要列表
        """
        dates = sorted(self.daily_summaries.keys(), reverse=True)[:days]
        return [self.daily_summaries[d] for d in dates]

    def to_dict(self) -> dict:
        """转换为字典格式。"""
        return {
            "daily_histories": {k: v.to_dict() for k, v in self.daily_histories.items()},
            "daily_summaries": {k: v.to_dict() for k, v in self.daily_summaries.items()},
            "current_queue": self.current_queue.to_dict(),
            "config": {
                "max_context_tokens": self.max_context_tokens,
                "token_reserved": self.token_reserved,
                "retention_days": self.retention_days,
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MessageHistory":
        """从字典创建对象。"""
        config = data.get("config", {})
        history = cls(
            max_context_tokens=config.get("max_context_tokens", 4000),
            token_reserved=config.get("token_reserved", 1000),
            retention_days=config.get("retention_days", 30),
        )

        for date_str, daily_data in data.get("daily_histories", {}).items():
            history.daily_histories[date_str] = DailyHistory.from_dict(daily_data)

        for date_str, summary_data in data.get("daily_summaries", {}).items():
            history.daily_summaries[date_str] = DailySummary.from_dict(summary_data)

        queue_data = data.get("current_queue", {})
        history.current_queue = MessageQueue.from_dict(queue_data)

        return history


# ============================================================================
# LLM驱动的记忆总结
# ============================================================================

from typing import Callable, Awaitable, Union


# 默认的同步LLM调用类型
LLMCallable = Callable[[str], str]


def _default_summary_prompt(date: str, messages: list[Message]) -> str:
    """构建用于生成摘要的默认Prompt。

    Args:
        date: 日期字符串
        messages: 消息列表

    Returns:
        摘要Prompt
    """
    role_names = {
        MessageRole.USER: "用户",
        MessageRole.ASSISTANT: "助手",
        MessageRole.SYSTEM: "系统",
        MessageRole.TOOL: "工具",
    }

    formatted_messages = []
    for msg in messages:
        role_text = role_names.get(msg.role, msg.role.value)
        content = msg.content[:300] + "..." if len(msg.content) > 300 else msg.content
        formatted_messages.append(f"[{role_text}] {content}")

    messages_text = "\n".join(formatted_messages)

    return f"""你是一个对话摘要助手。请分析以下日期为 {date} 的对话，生成简洁但信息丰富的摘要。

对话内容：
{messages_text}

请按以下JSON格式输出摘要（只输出JSON，不要有其他内容）：
{{
    "summary_text": "2-3句话的对话摘要，重点是重要事件、决定和用户偏好",
    "important_messages": ["最重要的1-2条消息ID或简短描述"],
    "topics": ["讨论的主要话题"],
    "emotional_tone": "整体情感基调（积极/中性/消极/混合）",
    "user_preferences": ["用户表达的任何偏好或决定"],
    "unfinished_topics": ["未完成或需要后续跟进的话题"]
}}

注意：
- summary_text 应该简洁但包含关键信息
- topics 只列出最重要的2-3个话题
- 如果没有重要的用户偏好，user_preferences 可以为空数组
- 如果没有未完成的话题，unfinished_topics 可以为空数组"""


class SummaryGenerator:
    """LLM驱动的摘要生成器。

    使用LLM生成高质量的对话摘要，替代规则驱动的方法。
    支持自定义LLM调用器，保持向后兼容。
    """

    def __init__(
        self,
        llm_callable: Optional[LLMCallable] = None,
        use_fallback: bool = True,
    ):
        """初始化摘要生成器。

        Args:
            llm_callable: LLM调用函数，签名为 (prompt: str) -> str
                         如果为None，使用规则驱动的后备方法
            use_fallback: 当LLM调用失败时是否使用规则后备
        """
        self.llm_callable = llm_callable
        self.use_fallback = use_fallback

    def generate_summary(
        self,
        date: str,
        messages: list[Message],
        config: Optional[dict] = None,
    ) -> DailySummary:
        """生成每日摘要。

        Args:
            date: 日期字符串
            messages: 消息列表
            config: 可选的配置字典

        Returns:
            DailySummary对象
        """
        if not messages:
            return DailySummary(
                date=date,
                summary_text="今日无消息。",
                important_messages=[],
                topics=[],
                message_count=0,
                created_at=time.time(),
            )

        # 优先尝试LLM生成
        if self.llm_callable is not None:
            try:
                return self._generate_with_llm(date, messages)
            except Exception as e:
                if self.use_fallback:
                    return self._generate_with_rules(date, messages)
                else:
                    raise RuntimeError(f"LLM摘要生成失败: {e}")

        # 使用规则后备方法
        return self._generate_with_rules(date, messages)

    def _generate_with_llm(self, date: str, messages: list[Message]) -> DailySummary:
        """使用LLM生成摘要。

        Args:
            date: 日期字符串
            messages: 消息列表

        Returns:
            DailySummary对象
        """
        prompt = _default_summary_prompt(date, messages)
        response_text = self.llm_callable(prompt)

        # 解析JSON响应
        import json

        try:
            # 尝试提取JSON（可能在markdown代码块中）
            json_str = response_text.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.startswith("```"):
                json_str = json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            json_str = json_str.strip()

            data = json.loads(json_str)

            return DailySummary(
                date=date,
                summary_text=data.get("summary_text", "今日对话摘要。"),
                important_messages=data.get("important_messages", []),
                topics=data.get("topics", []),
                message_count=len(messages),
                created_at=time.time(),
                emotional_tone=data.get("emotional_tone"),
                user_preferences=data.get("user_preferences", []),
                unfinished_topics=data.get("unfinished_topics", []),
            )
        except (json.JSONDecodeError, KeyError) as e:
            # JSON解析失败，尝试规则后备
            raise RuntimeError(f"JSON解析失败: {e}, 原始响应: {response_text[:200]}")

    def _generate_with_rules(self, date: str, messages: list[Message]) -> DailySummary:
        """使用规则方法生成摘要（后备方案）。

        Args:
            date: 日期字符串
            messages: 消息列表

        Returns:
            DailySummary对象
        """
        # 复用DailyHistory的规则方法逻辑
        daily = DailyHistory(date)
        for msg in messages:
            daily.messages.append(msg)
        return daily.generate_summary(config=None)


class AsyncSummaryGenerator:
    """异步LLM驱动的摘要生成器。

    支持异步LLM调用（如aiohttp或asyncio）。
    """

    def __init__(
        self,
        llm_callable: Callable[[str], Awaitable[str]],
        use_fallback: bool = True,
    ):
        """初始化异步摘要生成器。

        Args:
            llm_callable: 异步LLM调用函数，签名为 async def (prompt: str) -> str
            use_fallback: 当LLM调用失败时是否使用规则后备
        """
        self.llm_callable = llm_callable
        self.use_fallback = use_fallback

    async def generate_summary(
        self,
        date: str,
        messages: list[Message],
        config: Optional[dict] = None,
    ) -> DailySummary:
        """异步生成每日摘要。

        Args:
            date: 日期字符串
            messages: 消息列表
            config: 可选的配置字典

        Returns:
            DailySummary对象
        """
        if not messages:
            return DailySummary(
                date=date,
                summary_text="今日无消息。",
                important_messages=[],
                topics=[],
                message_count=0,
                created_at=time.time(),
            )

        # 优先尝试LLM生成
        try:
            return await self._generate_with_llm(date, messages)
        except Exception as e:
            if self.use_fallback:
                return self._generate_with_rules(date, messages)
            else:
                raise RuntimeError(f"LLM摘要生成失败: {e}")

    async def _generate_with_llm(self, date: str, messages: list[Message]) -> DailySummary:
        """异步使用LLM生成摘要。

        Args:
            date: 日期字符串
            messages: 消息列表

        Returns:
            DailySummary对象
        """
        import json

        prompt = _default_summary_prompt(date, messages)
        response_text = await self.llm_callable(prompt)

        try:
            json_str = response_text.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.startswith("```"):
                json_str = json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            json_str = json_str.strip()

            data = json.loads(json_str)

            return DailySummary(
                date=date,
                summary_text=data.get("summary_text", "今日对话摘要。"),
                important_messages=data.get("important_messages", []),
                topics=data.get("topics", []),
                message_count=len(messages),
                created_at=time.time(),
                emotional_tone=data.get("emotional_tone"),
                user_preferences=data.get("user_preferences", []),
                unfinished_topics=data.get("unfinished_topics", []),
            )
        except (json.JSONDecodeError, KeyError) as e:
            raise RuntimeError(f"JSON解析失败: {e}")

    def _generate_with_rules(self, date: str, messages: list[Message]) -> DailySummary:
        """使用规则方法生成摘要（后备方案）。

        Args:
            date: 日期字符串
            messages: 消息列表

        Returns:
            DailySummary对象
        """
        daily = DailyHistory(date)
        for msg in messages:
            daily.messages.append(msg)
        return daily.generate_summary(config=None)


# 为DailySummary添加新字段后的扩展方法
def generate_summary_with_llm(
    daily: DailyHistory,
    llm_callable: Optional[LLMCallable] = None,
    config: Optional[dict] = None,
) -> DailySummary:
    """为DailyHistory生成LLM驱动的摘要。

    这是一个便捷函数，将LLM驱动的摘要生成与DailyHistory关联。

    Args:
        daily: DailyHistory对象
        llm_callable: LLM调用函数
        config: 可选的配置字典

    Returns:
        DailySummary对象
    """
    generator = SummaryGenerator(llm_callable=llm_callable)
    return generator.generate_summary(daily.date, daily.messages, config)


def generate_daily_summaries_with_llm(
    history: MessageHistory,
    llm_callable: Optional[LLMCallable] = None,
) -> dict[str, DailySummary]:
    """为MessageHistory中的所有日期生成LLM驱动的摘要。

    Args:
        history: MessageHistory对象
        llm_callable: LLM调用函数

    Returns:
        日期到摘要的映射字典
    """
    generator = SummaryGenerator(llm_callable=llm_callable)
    results = {}

    for date_str, daily in history.daily_histories.items():
        if daily.messages:
            summary = generator.generate_summary(date_str, daily.messages)
            results[date_str] = summary
            history.daily_summaries[date_str] = summary

    return results
