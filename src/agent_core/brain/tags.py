"""Agent Core 核心层 - 回复标签模块。

为每条回复生成标签，供UI层显示角色立绘表情、动作等。
支持多语言关键词检测和 LLM 解析两种模式。

标签类型：
- emotion: 情感状态
- expression: 面部表情
- action: 身体动作
- pose: 姿态
- overlay: 特效叠加层
"""

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..api.client import ChatAgent


# 情感关键词映射（多语言统一）
EMOTION_KEYWORDS = {
    "happy": ["happy", "glad", "joy", "excited", "wonderful", "great", "love", "best", "awesome", "yay", "haha", "lol", "开心", "高兴", "快乐", "幸福", "太好了", "太棒了", "哈哈", "嘿嘿", "嘻嘻"],
    "sad": ["sad", "unhappy", "depressed", "miss", "lonely", "sorry", "cry", "tears", "unfortunate", "伤心", "难过", "悲伤", "哭泣", "眼泪", "遗憾", "沮丧"],
    "angry": ["angry", "mad", "annoyed", "frustrated", "hate", "stupid", "idiot", "grr", "argh", "生气", "愤怒", "恼火", "讨厌", "可恶", "哼", "气死了"],
    "surprised": ["wow", "oh", "surprised", "shocked", "unexpected", "really", "what", "huh", "whoa", "哇", "哦", "惊讶", "震惊", "真的吗", "什么", "咦"],
    "thinking": ["hmm", "think", "consider", "wonder", "maybe", "perhaps", "not sure", "let me", "嗯", "思考", "考虑", "也许", "可能", "不太确定", "让我想想"],
    "scared": ["scared", "afraid", "fear", "worried", "nervous", "terrified", "panic", "害怕", "恐惧", "担心", "紧张", "可怕"],
    "embarrassed": ["embarrassed", "shy", "awkward", "oops", "oh no", "mistake", "尴尬", "害羞", "不好意思", "失误", "糟糕"],
    "confused": ["confused", "puzzled", "don't understand", "unclear", "what do you mean", "困惑", "不明白", "不清楚", "什么意思", "啥"],
    "neutral": [],
}

# 情感到表情的映射
EMOTION_TO_EXPRESSION = {
    "happy": "smile",
    "sad": "frown",
    "angry": "scowl",
    "surprised": "gasp",
    "thinking": "focused",
    "scared": "worried",
    "embarrassed": "blush",
    "confused": "puzzled",
    "neutral": "neutral",
}

# 特效叠加层关键词
OVERLAY_KEYWORDS = {
    "blush": ["blush", "cheeks", "flustered", "脸红", "害羞"],
    "sweat_drop": ["sweat", "nervous", "tense", "汗", "紧张"],
    "tears": ["cry", "tears", "sad", "sobbing", "哭", "眼泪"],
    "sparkle": ["amazing", "wonderful", "perfect", "love it", "闪亮", "完美"],
    "anger_mark": ["angry", "mad", "annoyed", "怒", "生气"],
    "question_mark": ["confused", "what", "huh", "?", "什么", "？"],
}

# 动作关键词
ACTION_KEYWORDS = {
    "wave": ["wave", "hello", "hi", "bye", "goodbye", "挥手", "你好", "再见", "嗨"],
    "nod": ["yes", "agree", "understand", "right", "ok", "sure", "点头", "好的", "嗯"],
    "shake_head": ["no", "disagree", "wrong", "not", "never", "摇头", "不", "不是"],
    "clap": ["applause", "great", "awesome", "wow", "amazing", "鼓掌", "厉害"],
    "pat": ["pat", "pet", "comfort", "拍", "安慰"],
    "facepalm": ["facepalm", "stupid", "dumb", "oops", "mistake", "捂脸", "晕"],
    "shrug": ["maybe", "whatever", "not sure", "perhaps", "耸肩", "随便", "无所谓"],
}


@dataclass
class ReplyTag:
    """单条回复的标签。

    Attributes:
        message_id: 关联的消息ID
        emotion: 情感状态
        expression: 面部表情
        action: 身体动作
        pose: 姿态 (standing/sitting/lying)
        overlays: 特效叠加层列表
        intensity: 表情强度 (0.0-2.0)
        timestamp: 时间戳
    """

    message_id: str
    emotion: str = "neutral"
    expression: str = "neutral"
    action: Optional[str] = None
    pose: str = "standing"
    overlays: list[str] = field(default_factory=list)
    intensity: float = 1.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        """转换为字典格式。"""
        return {
            "message_id": self.message_id,
            "emotion": self.emotion,
            "expression": self.expression,
            "action": self.action,
            "pose": self.pose,
            "overlays": self.overlays,
            "intensity": self.intensity,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReplyTag":
        """从字典创建对象。"""
        return cls(
            message_id=data.get("message_id", ""),
            emotion=data.get("emotion", "neutral"),
            expression=data.get("expression", "neutral"),
            action=data.get("action"),
            pose=data.get("pose", "standing"),
            overlays=data.get("overlays", []),
            intensity=data.get("intensity", 1.0),
            timestamp=data.get("timestamp", 0.0),
        )


class TagGenerator:
    """回复标签生成器。

    根据消息内容自动生成情感、表情、动作等标签。
    支持多语言关键词检测。
    """

    def __init__(
        self,
        default_emotion: str = "neutral",
        default_expression: str = "neutral",
    ):
        """初始化标签生成器。

        Args:
            default_emotion: 默认情感
            default_expression: 默认表情
        """
        self.default_emotion = default_emotion
        self.default_expression = default_expression

    def detect_emotion(self, text: str) -> tuple[str, float]:
        """从文本内容检测情感。

        使用多语言关键词匹配。

        Args:
            text: 消息文本

        Returns:
            (情感类型, 置信度) 元组
        """
        text_lower = text.lower()
        scores: dict[str, float] = {}

        # 检测所有情感关键词
        for emotion, keywords in EMOTION_KEYWORDS.items():
            if not keywords:
                continue
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[emotion] = score

        if not scores:
            return self.default_emotion, 0.0

        # 获取得分最高的情感
        best = max(scores.items(), key=lambda x: x[1])
        confidence = min(1.0, best[1] / 3.0)

        return best[0], confidence

    def detect_expression(self, emotion: str) -> str:
        """根据情感获取对应表情。

        Args:
            emotion: 情感类型

        Returns:
            表情类型
        """
        if emotion in EMOTION_TO_EXPRESSION:
            return EMOTION_TO_EXPRESSION[emotion]
        return self.default_expression

    def detect_action(self, text: str) -> Optional[str]:
        """从文本检测动作。

        Args:
            text: 消息文本

        Returns:
            动作类型或None
        """
        text_lower = text.lower()

        for action, keywords in ACTION_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                return action

        return None

    def detect_overlays(self, text: str, emotion: str) -> list[str]:
        """检测特效叠加层。

        Args:
            text: 消息文本
            emotion: 情感类型

        Returns:
            叠加层列表
        """
        text_lower = text.lower()
        overlays = []

        for overlay, keywords in OVERLAY_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                overlays.append(overlay)

        # 基于情感的叠加层
        if emotion == "embarrassed" and "blush" not in overlays:
            overlays.append("blush")
        elif emotion == "sad" and "tears" not in overlays:
            overlays.append("tears")

        return overlays

    def calculate_intensity(self, text: str, emotion: str) -> float:
        """计算表情强度。

        基于文本中的修饰词和标点符号。

        Args:
            text: 消息文本
            emotion: 情感类型

        Returns:
            强度值 (0.3-2.0)
        """
        base = 1.0

        # 强度修饰词
        intensifiers = ["very", "really", "extremely", "so", "totally", "absolutely", "太", "非常", "特别", "极其"]
        for intensifier in intensifiers:
            if intensifier in text.lower():
                base += 0.2

        # 弱化修饰词
        diminishers = ["slightly", "a bit", "somewhat", "maybe", "有点", "稍微", "一点", "或许"]
        for diminisher in diminishers:
            if diminisher in text.lower():
                base -= 0.2

        # 多个感叹号/问号
        exclaim_count = text.count("!")
        question_count = text.count("?")
        # 中文感叹号/问号
        exclaim_count += text.count("！")
        question_count += text.count("？")

        if exclaim_count > 1:
            base += 0.3 * min(exclaim_count, 3)
        if question_count > 1:
            base += 0.2 * min(question_count, 3)

        return max(0.3, min(2.0, base))

    def generate_tag(
        self,
        message_id: str,
        content: str,
        context: Optional[str] = None,
    ) -> ReplyTag:
        """生成完整的回复标签。

        Args:
            message_id: 消息ID
            content: 消息内容
            context: 可选的上下文信息

        Returns:
            ReplyTag对象
        """
        emotion, confidence = self.detect_emotion(content)
        expression = self.detect_expression(emotion)
        action = self.detect_action(content)
        overlays = self.detect_overlays(content, emotion)
        intensity = self.calculate_intensity(content, emotion)

        # 低置信度时使用默认值
        if confidence < 0.2:
            emotion = self.default_emotion
            expression = self.default_expression

        return ReplyTag(
            message_id=message_id,
            emotion=emotion,
            expression=expression,
            action=action,
            pose="standing",
            overlays=overlays,
            intensity=intensity,
        )


class LLMTagGenerator:
    """基于 LLM 的回复标签生成器。

    使用 LLM 分析消息内容，生成情感、表情、动作等标签。
    参考日终摘要使用同一个模型。
    """

    # LLM 使用的情感、表情、动作词汇表（供 Prompt 参考）
    EMOTIONS = ["happy", "sad", "angry", "surprised", "thinking", "scared", "embarrassed", "confused", "neutral"]
    EXPRESSIONS = ["smile", "frown", "scowl", "gasp", "focused", "worried", "blush", "puzzled", "neutral"]
    ACTIONS = ["wave", "nod", "shake_head", "clap", "pat", "facepalm", "shrug", None]
    POSES = ["standing", "sitting", "lying"]
    OVERLAYS = ["blush", "sweat_drop", "tears", "sparkle", "anger_mark", "question_mark"]

    def __init__(
        self,
        chat_agent: "ChatAgent",
        default_emotion: str = "neutral",
        default_expression: str = "neutral",
    ):
        """初始化 LLM 标签生成器。

        Args:
            chat_agent: ChatAgent 实例
            default_emotion: 默认情感
            default_expression: 默认表情
        """
        self.chat_agent = chat_agent
        self.default_emotion = default_emotion
        self.default_expression = default_expression

    def generate_tag(
        self,
        message_id: str,
        content: str,
        context: Optional[str] = None,
    ) -> ReplyTag:
        """使用 LLM 生成完整的回复标签。

        Args:
            message_id: 消息ID
            content: 消息内容
            context: 可选的上下文信息（如情绪提示）

        Returns:
            ReplyTag对象
        """
        prompt = self._build_tag_prompt(content, context)

        response = self._call_llm(prompt)

        return self._parse_tag_response(message_id, response)

    def _build_tag_prompt(self, content: str, context: Optional[str]) -> str:
        """构建标签生成 Prompt。

        Args:
            content: 消息内容
            context: 可选的上下文

        Returns:
            Prompt 字符串
        """
        context_section = f"\n上下文提示: {context}" if context else ""

        return f"""你是一个回复标签生成助手。请分析以下消息，生成适合UI显示的标签。

消息内容：
{content}
{context_section}

请从以下选项中选择合适的标签：

emotion（情感）: {', '.join(self.EMOTIONS)}
expression（表情）: {', '.join(self.EXPRESSIONS)}
action（动作，可选）: {', '.join(str(a) for a in self.ACTIONS)}
pose（姿态）: {', '.join(self.POSES)}
overlays（特效叠加层，可多选）: {', '.join(self.OVERLAYS)}
intensity（表情强度，0.3-2.0）: 0.3(很弱) - 1.0(正常) - 2.0(强烈)

请按以下JSON格式输出（只输出JSON，不要有其他内容）：
{{
    "emotion": "选择最合适的情感",
    "expression": "对应的表情",
    "action": "动作（如果没有明显的动作则使用null）",
    "pose": "姿态（默认为standing）",
    "overlays": ["特效叠加层列表（如果没有则为空数组）"],
    "intensity": 1.0
}}

注意：
- emotion 和 expression 必须从给定列表中选择
- action 如果消息中没有明显的动作意图则使用 null
- overlays 基于情感和内容关键词综合判断
- intensity 根据消息的情绪强烈程度选择合适的值"""

    def _call_llm(self, prompt: str) -> str:
        """调用 LLM 获取标签。

        Args:
            prompt: 标签生成 Prompt

        Returns:
            LLM 响应文本
        """
        from ..api.message import Message as ApiMessage, MessageRole as ApiMessageRole

        messages = [ApiMessage(
            role=ApiMessageRole.USER,
            content=prompt,
        )]

        response = self.chat_agent.chat(messages, stream=False)

        if hasattr(response, 'content'):
            return response.content
        elif hasattr(response, 'delta'):
            return response.delta
        else:
            return str(response)

    def _parse_tag_response(self, message_id: str, response_text: str) -> ReplyTag:
        """解析 LLM 响应，提取标签数据。

        Args:
            message_id: 消息ID
            response_text: LLM 响应文本

        Returns:
            ReplyTag对象
        """
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

            return ReplyTag(
                message_id=message_id,
                emotion=data.get("emotion", self.default_emotion),
                expression=data.get("expression", self.default_expression),
                action=data.get("action"),
                pose=data.get("pose", "standing"),
                overlays=data.get("overlays", []),
                intensity=data.get("intensity", 1.0),
            )

        except (json.JSONDecodeError, KeyError, TypeError):
            # 解析失败，使用默认值
            return ReplyTag(
                message_id=message_id,
                emotion=self.default_emotion,
                expression=self.default_expression,
                pose="standing",
            )


class UnifiedTagGenerator:
    """统一的标签生成器，支持切换硬编码和 LLM 模式。

    根据配置自动选择使用硬编码关键词还是 LLM 生成标签。
    """

    def __init__(
        self,
        chat_agent: Optional["ChatAgent"] = None,
        mode: str = "keyword",
        default_emotion: str = "neutral",
        default_expression: str = "neutral",
    ):
        """初始化统一标签生成器。

        Args:
            chat_agent: ChatAgent 实例（LLM 模式需要）
            mode: 模式 "keyword" 或 "llm"
            default_emotion: 默认情感
            default_expression: 默认表情
        """
        self.mode = mode
        self._keyword_generator = TagGenerator(
            default_emotion=default_emotion,
            default_expression=default_expression,
        )
        self._llm_generator = LLMTagGenerator(
            chat_agent=chat_agent,
            default_emotion=default_emotion,
            default_expression=default_expression,
        ) if chat_agent else None

    def generate_tag(
        self,
        message_id: str,
        content: str,
        context: Optional[str] = None,
    ) -> ReplyTag:
        """生成回复标签。

        Args:
            message_id: 消息ID
            content: 消息内容
            context: 可选的上下文信息

        Returns:
            ReplyTag对象
        """
        if self.mode == "llm" and self._llm_generator:
            return self._llm_generator.generate_tag(message_id, content, context)
        return self._keyword_generator.generate_tag(message_id, content, context)

    @property
    def supports_llm(self) -> bool:
        """是否支持 LLM 模式。"""
        return self._llm_generator is not None


class TagCache:
    """回复标签缓存。

    存储最近使用过的标签，支持按ID查询和LRU淘汰。
    """

    def __init__(self, max_size: int = 100):
        """初始化缓存。

        Args:
            max_size: 最大缓存条目数
        """
        self.tags: dict[str, ReplyTag] = {}
        self.recent_order: list[str] = []
        self.max_size = max_size

    def add(self, tag: ReplyTag) -> None:
        """添加标签到缓存。"""
        self.tags[tag.message_id] = tag
        self.recent_order.append(tag.message_id)

        # 超量时淘汰最旧的
        while len(self.recent_order) > self.max_size:
            oldest = self.recent_order.pop(0)
            if oldest in self.tags:
                del self.tags[oldest]

    def get(self, message_id: str) -> Optional[ReplyTag]:
        """根据消息ID获取标签。"""
        return self.tags.get(message_id)

    def get_recent(self, limit: int = 10) -> list[ReplyTag]:
        """获取最近的标签。

        Args:
            limit: 返回数量限制

        Returns:
            按时间倒序的标签列表
        """
        result = []
        for msg_id in reversed(self.recent_order):
            if msg_id in self.tags:
                result.append(self.tags[msg_id])
                if len(result) >= limit:
                    break
        return result

    def to_dict(self) -> dict:
        """转换为字典格式。"""
        return {
            "tags": {k: v.to_dict() for k, v in self.tags.items()},
            "recent_order": self.recent_order,
            "max_size": self.max_size,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TagCache":
        """从字典创建对象。"""
        cache = cls(max_size=data.get("max_size", 100))
        for msg_id, tag_data in data.get("tags", {}).items():
            cache.tags[msg_id] = ReplyTag.from_dict(tag_data)
        cache.recent_order = data.get("recent_order", [])
        return cache
