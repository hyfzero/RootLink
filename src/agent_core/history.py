"""
历史消息管理系统
包含每日梗概生成、消息权重队列和当天消息队列
"""

import json
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass, field, asdict
from collections import deque
from .memory import Memory, MessageWeight


@dataclass
class DailySummary:
    """每日消息梗概"""
    date: str  # YYYY-MM-DD格式
    summary: str  # 当天消息的模糊梗概
    important_events: list[str] = field(default_factory=list)  # 重要事件列表
    message_count: int = 0
    participants: list[str] = field(default_factory=list)  # 参与者
    topics: list[str] = field(default_factory=list)  # 讨论话题

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DailySummary":
        return cls(**data)


@dataclass
class ChatMessage:
    """聊天消息"""
    id: str
    sender: str
    content: str
    timestamp: datetime
    weight: MessageWeight = MessageWeight.NORMAL
    reply_to: Optional[str] = None  # 回复的消息ID
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "sender": self.sender,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "weight": self.weight.value,
            "reply_to": self.reply_to,
            "tags": self.tags,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ChatMessage":
        if isinstance(data.get("weight"), int):
            data["weight"] = MessageWeight(data["weight"])
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


class MessageQueue:
    """当天消息队列"""

    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self.queue: deque = deque(maxlen=max_size)
        self.current_date: Optional[date] = None
        self.pending_messages: list[ChatMessage] = []  # 待加入prompt的消息

    def add_message(self, message: ChatMessage) -> None:
        """添加消息到队列"""
        today = date.today()

        # 如果日期变了，重置队列
        if self.current_date and self.current_date != today:
            self._archive_current_day()

        self.current_date = today
        self.queue.append(message)

    def _archive_current_day(self) -> None:
        """归档当天消息（由外部调用）"""
        pass

    def get_messages_for_prompt(
        self,
        max_messages: int = 20,
        min_weight: MessageWeight = MessageWeight.TRIVIAL,
    ) -> list[ChatMessage]:
        """
        获取要加入prompt的消息
        策略：高权重消息优先，但也保留一些低权重的上下文
        """
        if not self.queue:
            return []

        # 按权重排序，高权重在前
        sorted_messages = sorted(
            self.queue,
            key=lambda m: m.weight.value,
            reverse=True
        )

        # 选取高权重消息
        high_weight = [m for m in sorted_messages if m.weight.value >= MessageWeight.IMPORTANT.value]

        # 如果高权重消息足够，直接返回
        if len(high_weight) >= max_messages:
            return high_weight[:max_messages]

        # 否则补充一些普通消息作为上下文
        remaining = max_messages - len(high_weight)
        normal_weight = [m for m in sorted_messages if m not in high_weight]
        normal_weight = normal_weight[:remaining]

        # 合并并按时间排序
        result = high_weight + normal_weight
        result.sort(key=lambda m: m.timestamp)
        return result

    def get_pending_messages(self) -> list[ChatMessage]:
        """获取待处理的消息"""
        return list(self.pending_messages)

    def mark_as_used(self, message_ids: list[str]) -> None:
        """标记消息已被使用"""
        self.pending_messages = [
            m for m in self.pending_messages if m.id not in message_ids
        ]

    def to_dict(self) -> dict:
        return {
            "max_size": self.max_size,
            "current_date": self.current_date.isoformat() if self.current_date else None,
            "queue": [m.to_dict() for m in self.queue],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MessageQueue":
        queue = cls(max_size=data.get("max_size", 100))
        if data.get("current_date"):
            queue.current_date = date.fromisoformat(data["current_date"])
        queue.queue = deque(
            [ChatMessage.from_dict(m) for m in data.get("queue", [])],
            maxlen=queue.max_size
        )
        return queue


class HistoryManager:
    """
    历史消息管理器

    功能:
    1. 每天生成模糊梗概，找出最重要的消息
    2. 给历史消息权重
    3. 当天消息保存到队列，通过机制加入prompt
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path
        self.daily_summaries: dict[str, DailySummary] = {}  # key: YYYY-MM-DD
        self.today_queue: MessageQueue = MessageQueue()
        self.max_history_days: int = 30  # 保留历史的天数

    def add_message(
        self,
        sender: str,
        content: str,
        weight: MessageWeight = MessageWeight.NORMAL,
        tags: list[str] = None,
        reply_to: str = None,
    ) -> ChatMessage:
        """添加消息"""
        message = ChatMessage(
            id=f"msg_{datetime.now().timestamp()}",
            sender=sender,
            content=content,
            timestamp=datetime.now(),
            weight=weight,
            tags=tags or [],
            reply_to=reply_to,
        )
        self.today_queue.add_message(message)
        return message

    def generate_daily_summary(self, target_date: Optional[date] = None) -> DailySummary:
        """
        生成每日梗概
        策略：找出当天最重要的消息，生成模糊梗概
        """
        target = target_date or date.today()
        date_str = target.isoformat()

        # 获取当天的消息
        if target == date.today():
            messages = list(self.today_queue.queue)
        else:
            messages = self._load_day_messages(target)

        if not messages:
            return DailySummary(
                date=date_str,
                summary="今天没有消息",
                message_count=0,
            )

        # 按权重排序，找出最重要的消息
        important_messages = sorted(
            messages,
            key=lambda m: m.weight.value,
            reverse=True
        )

        # 提取重要事件
        important_events = []
        topics = set()
        participants = set()

        for msg in important_messages[:5]:  # 取前5个重要的
            participants.add(msg.sender)
            if msg.tags:
                topics.update(msg.tags)

            # 生成模糊的事件描述
            if msg.weight.value >= MessageWeight.IMPORTANT.value:
                # 模糊化处理
                content_preview = msg.content[:50] + "..." if len(msg.content) > 50 else msg.content
                important_events.append(f"[{msg.sender}]: {content_preview}")

        # 生成梗概
        if important_events:
            summary = f"今天有{len(messages)}条消息，讨论了{', '.join(list(topics)[:3]) if topics else 'various topics'}。"
        else:
            summary = f"今天有{len(messages)}条消息，比较平静的一天。"

        daily_summary = DailySummary(
            date=date_str,
            summary=summary,
            important_events=important_events,
            message_count=len(messages),
            participants=list(participants),
            topics=list(topics),
        )

        self.daily_summaries[date_str] = daily_summary
        return daily_summary

    def get_recent_summaries(self, days: int = 7) -> list[DailySummary]:
        """获取最近几天的梗概"""
        result = []
        today = date.today()

        for i in range(days):
            target_date = today - timedelta(days=i)
            date_str = target_date.isoformat()

            if date_str in self.daily_summaries:
                result.append(self.daily_summaries[date_str])
            else:
                # 尝试从文件加载
                summary = self._load_summary(target_date)
                if summary:
                    result.append(summary)
                    self.daily_summaries[date_str] = summary

        return result

    def get_prompt_context(
        self,
        max_messages: int = 20,
        include_days: int = 7,
    ) -> str:
        """
        生成用于prompt的历史上下文
        """
        context_parts = []

        # 获取最近几天的梗概
        recent_summaries = self.get_recent_summaries(include_days)
        if recent_summaries:
            context_parts.append("## 最近几天的对话概要")
            for summary in reversed(recent_summaries):
                if summary.message_count > 0:
                    context_parts.append(f"### {summary.date}")
                    context_parts.append(summary.summary)
                    if summary.important_events:
                        context_parts.append("重要事件:")
                        for event in summary.important_events[:3]:
                            context_parts.append(f"  - {event}")
                context_parts.append("")

        # 获取当天要加入prompt的消息
        today_messages = self.today_queue.get_messages_for_prompt(max_messages)
        if today_messages:
            context_parts.append("## 今天的对话")
            for msg in today_messages:
                time_str = msg.timestamp.strftime("%H:%M")
                weight_indicator = "★" * (msg.weight.value // 3)  # 权重可视化
                context_parts.append(f"[{time_str}] {msg.sender}: {msg.content} {weight_indicator}")
            context_parts.append("")

        return "\n".join(context_parts)

    def _load_day_messages(self, target_date: date) -> list[ChatMessage]:
        """加载指定日期的消息"""
        if not self.storage_path:
            return []

        date_str = target_date.isoformat()
        message_file = self.storage_path / f"messages_{date_str}.json"

        if not message_file.exists():
            return []

        try:
            with open(message_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [ChatMessage.from_dict(m) for m in data]
        except Exception as e:
            print(f"加载消息失败: {e}")
            return []

    def _load_summary(self, target_date: date) -> Optional[DailySummary]:
        """从文件加载每日梗概"""
        if not self.storage_path:
            return None

        date_str = target_date.isoformat()
        summary_file = self.storage_path / f"summary_{date_str}.json"

        if not summary_file.exists():
            return None

        try:
            with open(summary_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return DailySummary.from_dict(data)
        except Exception as e:
            print(f"加载梗概失败: {e}")
            return None

    def save_day(self, target_date: Optional[date] = None) -> bool:
        """保存指定日期的数据"""
        if not self.storage_path:
            return False

        target = target_date or date.today()
        date_str = target.isoformat()

        try:
            storage_dir = self.storage_path
            storage_dir.mkdir(parents=True, exist_ok=True)

            # 保存当天的消息
            if target == date.today():
                messages = list(self.today_queue.queue)
            else:
                messages = self._load_day_messages(target)

            if messages:
                with open(storage_dir / f"messages_{date_str}.json", "w", encoding="utf-8") as f:
                    json.dump([m.to_dict() for m in messages], f, ensure_ascii=False, indent=2)

            # 生成并保存梗概
            summary = self.generate_daily_summary(target)
            with open(storage_dir / f"summary_{date_str}.json", "w", encoding="utf-8") as f:
                json.dump(summary.to_dict(), f, ensure_ascii=False, indent=2)

            # 清理旧数据
            self._cleanup_old_data()

            return True
        except Exception as e:
            print(f"保存历史数据失败: {e}")
            return False

    def _cleanup_old_data(self) -> None:
        """清理过期的历史数据"""
        if not self.storage_path:
            return

        cutoff_date = date.today() - timedelta(days=self.max_history_days)
        cutoff_str = cutoff_date.isoformat()

        # 遍历文件，删除过期的
        for file in self.storage_path.glob("messages_*.json"):
            if file.stem.split("_")[1] < cutoff_str:
                file.unlink()

        for file in self.storage_path.glob("summary_*.json"):
            if file.stem.split("_")[1] < cutoff_str:
                file.unlink()

    def load_history(self, agent_id: str) -> bool:
        """加载历史数据"""
        if not self.storage_path:
            return False

        storage_dir = self.storage_path / agent_id
        if not storage_dir.exists():
            return False

        try:
            # 加载梗概索引
            summaries_file = storage_dir / "summaries.json"
            if summaries_file.exists():
                with open(summaries_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.daily_summaries = {
                        k: DailySummary.from_dict(v) for k, v in data.items()
                    }

            # 加载今天的队列状态
            queue_file = storage_dir / "today_queue.json"
            if queue_file.exists():
                with open(queue_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.today_queue = MessageQueue.from_dict(data)

            return True
        except Exception as e:
            print(f"加载历史失败: {e}")
            return False

    def save_history(self, agent_id: str) -> bool:
        """保存历史数据"""
        if not self.storage_path:
            return False

        try:
            storage_dir = self.storage_path / agent_id
            storage_dir.mkdir(parents=True, exist_ok=True)

            # 保存梗概索引
            with open(storage_dir / "summaries.json", "w", encoding="utf-8") as f:
                json.dump(
                    {k: v.to_dict() for k, v in self.daily_summaries.items()},
                    f, ensure_ascii=False, indent=2
                )

            # 保存今天的队列状态
            with open(storage_dir / "today_queue.json", "w", encoding="utf-8") as f:
                json.dump(self.today_queue.to_dict(), f, ensure_ascii=False, indent=2)

            return True
        except Exception as e:
            print(f"保存历史失败: {e}")
            return False
