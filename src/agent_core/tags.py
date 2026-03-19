"""
消息标签系统
用于为回复添加标签，便于交互层做立绘显示
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict
from enum import Enum


class ReplyTagType(Enum):
    """回复标签类型"""
    # 情绪类
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    SURPRISED = "surprised"
    EXCITED = "excited"
    CALM = "calm"
    EMBARRASSED = "embarrassed"
    CONFUSED = "confused"

    # 动作类
    THINKING = "thinking"
    LAUGHING = "laughing"
    CRYING = "crying"
    SHOUTING = "shouting"
    WHISPERING = "whispering"

    # 状态类
    TIRED = "tired"
    ENERGETIC = "energetic"
    SLEEPY = "sleepy"
    HUNGRY = "hungry"

    # 交互类
    GREETING = "greeting"
    GOODBYE = "goodbye"
    QUESTION = "question"
    ANSWER = "answer"
    JOKE = "joke"
    COMPLAINT = "compliment"

    # 特殊类
    NEUTRAL = "neutral"


@dataclass
class ReplyTag:
    """回复标签"""
    tag_type: ReplyTagType
    confidence: float = 1.0  # 置信度 0-1
    intensity: float = 0.5    # 强度 0-1
    custom_data: dict = field(default_factory=dict)  # 自定义数据

    def to_dict(self) -> dict:
        return {
            "tag_type": self.tag_type.value,
            "confidence": self.confidence,
            "intensity": self.intensity,
            "custom_data": self.custom_data,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReplyTag":
        if isinstance(data.get("tag_type"), str):
            data["tag_type"] = ReplyTagType(data["tag_type"])
        return cls(**data)


@dataclass
class TaggedReply:
    """带标签的回复"""
    message_id: str
    content: str
    tags: list[ReplyTag]
    timestamp: datetime
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "content": self.content,
            "tags": [t.to_dict() for t in self.tags],
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaggedReply":
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        if "tags" in data:
            data["tags"] = [ReplyTag.from_dict(t) if isinstance(t, dict) else t for t in data["tags"]]
        return cls(**data)

    def get_primary_tag(self) -> Optional[ReplyTagType]:
        """获取主要标签（置信度最高的）"""
        if not self.tags:
            return None
        return max(self.tags, key=lambda t: t.confidence).tag_type

    def get_all_tag_types(self) -> list[ReplyTagType]:
        """获取所有标签类型"""
        return [t.tag_type for t in self.tags]


class TagManager:
    """标签管理器"""

    # 情绪到标签的映射
    EMOTION_MAPPING = {
        "开心": ReplyTagType.HAPPY,
        "高兴": ReplyTagType.HAPPY,
        "快乐": ReplyTagType.HAPPY,
        "难过": ReplyTagType.SAD,
        "伤心": ReplyTagType.SAD,
        "悲伤": ReplyTagType.SAD,
        "生气": ReplyTagType.ANGRY,
        "愤怒": ReplyTagType.ANGRY,
        "惊讶": ReplyTagType.SURPRISED,
        "意外": ReplyTagType.SURPRISED,
        "兴奋": ReplyTagType.EXCITED,
        "激动": ReplyTagType.EXCITED,
        "平静": ReplyTagType.CALM,
        "冷静": ReplyTagType.CALM,
        "尴尬": ReplyTagType.EMBARRASSED,
        "困惑": ReplyTagType.CONFUSED,
        "疑惑": ReplyTagType.CONFUSED,
    }

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path
        self.tagged_replies: list[TaggedReply] = []

    def create_tag(
        self,
        tag_type: ReplyTagType,
        confidence: float = 1.0,
        intensity: float = 0.5,
        custom_data: dict = None,
    ) -> ReplyTag:
        """创建标签"""
        return ReplyTag(
            tag_type=tag_type,
            confidence=min(max(confidence, 0.0), 1.0),  # 限制在0-1
            intensity=min(max(intensity, 0.0), 1.0),
            custom_data=custom_data or {},
        )

    def analyze_content_for_tags(self, content: str) -> list[ReplyTag]:
        """
        分析内容，生成标签
        基于关键词匹配
        """
        tags = []
        content_lower = content.lower()

        # 简单的关键词匹配
        for keyword, tag_type in self.EMOTION_MAPPING.items():
            if keyword in content_lower:
                # 检查是否已经有相同类型的标签
                existing = [t for t in tags if t.tag_type == tag_type]
                if not existing:
                    tags.append(self.create_tag(tag_type, confidence=0.7))

        # 检测问句
        if "?" in content or "？" in content or content_lower.startswith(("什么", "为什么", "怎么", "如何", "谁", "哪里", "是不是", "有没有")):
            existing = [t for t in tags if t.tag_type == ReplyTagType.QUESTION]
            if not existing:
                tags.append(self.create_tag(ReplyTagType.QUESTION, confidence=0.8))

        # 检测问候
        greetings = ["你好", "早上好", "中午好", "晚上好", "嗨", "hi", "hello", "hey"]
        for g in greetings:
            if content_lower.startswith(g):
                existing = [t for t in tags if t.tag_type == ReplyTagType.GREETING]
                if not existing:
                    tags.append(self.create_tag(ReplyTagType.GREETING, confidence=0.9))
                break

        # 检测再见
        goodbyes = ["再见", "拜拜", "bye", "走了", "回见"]
        for g in goodbyes:
            if g in content_lower:
                existing = [t for t in tags if t.tag_type == ReplyTagType.GOODBYE]
                if not existing:
                    tags.append(self.create_tag(ReplyTagType.GOODBYE, confidence=0.9))
                break

        # 如果没有检测到任何标签，默认中性
        if not tags:
            tags.append(self.create_tag(ReplyTagType.NEUTRAL, confidence=1.0))

        return tags

    def create_tagged_reply(
        self,
        message_id: str,
        content: str,
        tags: list[ReplyTag] = None,
        metadata: dict = None,
    ) -> TaggedReply:
        """创建带标签的回复"""
        if tags is None:
            tags = self.analyze_content_for_tags(content)

        tagged_reply = TaggedReply(
            message_id=message_id,
            content=content,
            tags=tags,
            timestamp=datetime.now(),
            metadata=metadata or {},
        )

        self.tagged_replies.append(tagged_reply)
        return tagged_reply

    def get_reply_by_id(self, message_id: str) -> Optional[TaggedReply]:
        """根据ID获取回复"""
        for reply in reversed(self.tagged_replies):
            if reply.message_id == message_id:
                return reply
        return None

    def get_replies_by_tag(
        self,
        tag_type: ReplyTagType,
        limit: int = 10,
    ) -> list[TaggedReply]:
        """根据标签类型获取回复"""
        result = []
        for reply in reversed(self.tagged_replies):
            if tag_type in reply.get_all_tag_types():
                result.append(reply)
                if len(result) >= limit:
                    break
        return result

    def get_recent_tags(self, count: int = 5) -> list[ReplyTagType]:
        """获取最近使用的标签"""
        recent = self.tagged_replies[-count:] if len(self.tagged_replies) >= count else self.tagged_replies
        result = []
        for reply in recent:
            primary = reply.get_primary_tag()
            if primary and primary not in result:
                result.append(primary)
        return result

    def save_tags(self, agent_id: str) -> bool:
        """保存标签数据"""
        if not self.storage_path:
            return False

        try:
            storage_dir = self.storage_path / agent_id
            storage_dir.mkdir(parents=True, exist_ok=True)

            with open(storage_dir / "tagged_replies.json", "w", encoding="utf-8") as f:
                json.dump(
                    [r.to_dict() for r in self.tagged_replies],
                    f, ensure_ascii=False, indent=2
                )
            return True
        except Exception as e:
            print(f"保存标签失败: {e}")
            return False

    def load_tags(self, agent_id: str) -> bool:
        """加载标签数据"""
        if not self.storage_path:
            return False

        storage_dir = self.storage_path / agent_id
        tags_file = storage_dir / "tagged_replies.json"

        if not tags_file.exists():
            return False

        try:
            with open(tags_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.tagged_replies = [TaggedReply.from_dict(r) for r in data]
            return True
        except Exception as e:
            print(f"加载标签失败: {e}")
            return False


def get_tag_for_display(tag: ReplyTag) -> dict:
    """获取用于UI显示的标签信息"""
    return {
        "type": tag.tag_type.value,
        "display_name": tag.tag_type.value.capitalize(),
        "confidence": tag.confidence,
        "intensity": tag.intensity,
        "icon": _get_tag_icon(tag.tag_type),
        "color": _get_tag_color(tag.tag_type),
    }


def _get_tag_icon(tag_type: ReplyTagType) -> str:
    """获取标签图标 (使用ASCII避免编码问题)"""
    ICONS = {
        ReplyTagType.HAPPY: ":)",
        ReplyTagType.SAD: ":(",
        ReplyTagType.ANGRY: ">:(",
        ReplyTagType.SURPRISED: ":o",
        ReplyTagType.EXCITED: ":D",
        ReplyTagType.CALM: ":|",
        ReplyTagType.EMBARRASSED: ":S",
        ReplyTagType.CONFUSED: ":?",
        ReplyTagType.THINKING: "...",
        ReplyTagType.LAUGHING: ":))",
        ReplyTagType.CRYING: ":')",
        ReplyTagType.SHOUTING: ":!",
        ReplyTagType.WHISPERING: ":..",
        ReplyTagType.TIRED: "-_-",
        ReplyTagType.ENERGETIC: "*.*",
        ReplyTagType.SLEEPY: "-.-",
        ReplyTagType.HUNGRY: ":3",
        ReplyTagType.GREETING: "hi",
        ReplyTagType.GOODBYE: "bye",
        ReplyTagType.QUESTION: "???",
        ReplyTagType.ANSWER: "!!!",
        ReplyTagType.JOKE: "^^",
        ReplyTagType.COMPLAINT: ":thumbsup:",
        ReplyTagType.NEUTRAL: "-_-",
    }
    return ICONS.get(tag_type, "-_-")


def _get_tag_color(tag_type: ReplyTagType) -> str:
    """获取标签颜色"""
    COLORS = {
        ReplyTagType.HAPPY: "#4CAF50",
        ReplyTagType.SAD: "#2196F3",
        ReplyTagType.ANGRY: "#F44336",
        ReplyTagType.SURPRISED: "#FF9800",
        ReplyTagType.EXCITED: "#FF5722",
        ReplyTagType.CALM: "#9C27B0",
        ReplyTagType.EMBARRASSED: "#E91E63",
        ReplyTagType.CONFUSED: "#607D8B",
        ReplyTagType.THINKING: "#795548",
        ReplyTagType.LAUGHING: "#FFEB3B",
        ReplyTagType.CRYING: "#00BCD4",
        ReplyTagType.SHOUTING: "#F44336",
        ReplyTagType.WHISPERING: "#3F51B5",
        ReplyTagType.TIRED: "#9E9E9E",
        ReplyTagType.ENERGETIC: "#FFEB3B",
        ReplyTagType.SLEEPY: "#673AB7",
        ReplyTagType.HUNGRY: "#FF9800",
        ReplyTagType.GREETING: "#4CAF50",
        ReplyTagType.GOODBYE: "#8BC34A",
        ReplyTagType.QUESTION: "#03A9F4",
        ReplyTagType.ANSWER: "#8BC34A",
        ReplyTagType.JOKE: "#FFEB3B",
        ReplyTagType.COMPLAINT: "#E91E63",
        ReplyTagType.NEUTRAL: "#9E9E9E",
    }
    return COLORS.get(tag_type, "#9E9E9E")
