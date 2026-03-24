"""Agent Core 核心层 - 说话风格引擎模块。

提供动态的说话风格控制，包括：
- 词汇复杂度
- 句长偏好
- 标点习惯
- 口头禅/填充词
- 情绪指示词

该模块让Agent的回复不仅仅是"friendly"这样的简单标签，
而是能够精细控制语言表达的各个方面。
"""

from dataclasses import dataclass, field
from typing import Optional
import random


@dataclass
class SpeakingStyle:
    """说话风格配置。

    Attributes:
        vocabulary_level: 词汇复杂度 (simple/common/academic)
        sentence_length: 句长偏好 (short/medium/long/varied)
        exclamation_rate: 感叹号使用频率 (0.0-1.0)
        question_rate: 问号使用频率 (0.0-1.0)
        ellipsis_rate: 省略号使用频率 (0.0-1.0)
        filler_words: 口头禅/填充词列表
        emotion_words: 情绪词列表（按情绪分类）
        emoji_usage: emoji使用偏好 (none/sparse/适量/丰富)
        parenthesis_usage: 括号使用偏好 (none/sparse/适量)
    """

    vocabulary_level: str = "common"  # simple/common/academic
    sentence_length: str = "varied"  # short/medium/long/varied
    exclamation_rate: float = 0.1  # 0.0-1.0
    question_rate: float = 0.15  # 0.0-1.0
    ellipsis_rate: float = 0.05  # 0.0-1.0
    filler_words: list[str] = field(default_factory=list)
    emotion_words: dict[str, list[str]] = field(default_factory=dict)
    emoji_usage: str = "none"  # none/sparse/适量/丰富
    parenthesis_usage: str = "sparse"  # none/sparse/适量

    def to_dict(self) -> dict:
        """转换为字典格式。"""
        return {
            "vocabulary_level": self.vocabulary_level,
            "sentence_length": self.sentence_length,
            "exclamation_rate": self.exclamation_rate,
            "question_rate": self.question_rate,
            "ellipsis_rate": self.ellipsis_rate,
            "filler_words": self.filler_words,
            "emotion_words": self.emotion_words,
            "emoji_usage": self.emoji_usage,
            "parenthesis_usage": self.parenthesis_usage,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SpeakingStyle":
        """从字典创建对象。"""
        return cls(
            vocabulary_level=data.get("vocabulary_level", "common"),
            sentence_length=data.get("sentence_length", "varied"),
            exclamation_rate=data.get("exclamation_rate", 0.1),
            question_rate=data.get("question_rate", 0.15),
            ellipsis_rate=data.get("ellipsis_rate", 0.05),
            filler_words=data.get("filler_words", []),
            emotion_words=data.get("emotion_words", {}),
            emoji_usage=data.get("emoji_usage", "none"),
            parenthesis_usage=data.get("parenthesis_usage", "sparse"),
        )


# 预设说话风格
PRESET_STYLES = {
    # 活泼可爱型
    "cheerful": SpeakingStyle(
        vocabulary_level="simple",
        sentence_length="short",
        exclamation_rate=0.3,
        question_rate=0.2,
        filler_words=["嗯嗯", "呀", "哈", "哇", "诶"],
        emotion_words={
            "happy": ["开心", "高兴", "太棒了", "超赞", "嘿嘿"],
            "surprised": ["哇", "真的吗", "诶呀"],
        },
        emoji_usage="适量",
        parenthesis_usage="sparse",
    ),
    # 温柔体贴型
    "gentle": SpeakingStyle(
        vocabulary_level="common",
        sentence_length="medium",
        exclamation_rate=0.05,
        question_rate=0.1,
        filler_words=["呢", "呀", "哦", "嗯", "亲爱的"],
        emotion_words={
            "happy": ["开心", "欣慰", "真好"],
            "sad": ["心疼", "难过"],
        },
        emoji_usage="sparse",
        parenthesis_usage="sparse",
    ),
    # 专业正式型
    "professional": SpeakingStyle(
        vocabulary_level="academic",
        sentence_length="long",
        exclamation_rate=0.02,
        question_rate=0.1,
        filler_words=["是的", "可以说", "从这个角度"],
        emotion_words={
            "happy": ["满意", "认可"],
        },
        emoji_usage="none",
        parenthesis_usage="适量",
    ),
    # 轻松随意型
    "casual": SpeakingStyle(
        vocabulary_level="common",
        sentence_length="varied",
        exclamation_rate=0.15,
        question_rate=0.2,
        filler_words=["那个", "其实", "吧", "嗯", "呃"],
        emotion_words={
            "happy": ["哈哈", "挺好的", "不错"],
            "thinking": ["好像", "感觉", "大概"],
        },
        emoji_usage="sparse",
        parenthesis_usage="sparse",
    ),
    # 冷静理性型
    "analytical": SpeakingStyle(
        vocabulary_level="academic",
        sentence_length="long",
        exclamation_rate=0.0,
        question_rate=0.15,
        filler_words=["首先", "其次", "因此", "然而", "综上所述"],
        emotion_words={},
        emoji_usage="none",
        parenthesis_usage="none",
    ),
    # 幽默风趣型
    "humorous": SpeakingStyle(
        vocabulary_level="common",
        sentence_length="short",
        exclamation_rate=0.25,
        question_rate=0.15,
        filler_words=["哈哈", "笑死", "没毛病", "没毛病啊"],
        emotion_words={
            "happy": ["笑死", "绝了", "太逗了", "笑点"],
        },
        emoji_usage="丰富",
        parenthesis_usage="sparse",
    ),
    # 高冷傲娇型
    "tsundere": SpeakingStyle(
        vocabulary_level="common",
        sentence_length="short",
        exclamation_rate=0.1,
        question_rate=0.1,
        filler_words=["哼", "才不是", "随便", "无所谓"],
        emotion_words={
            "happy": ["哼", "算你走运"],
            "angry": ["哼", "气死了", "烦死了"],
        },
        emoji_usage="sparse",
        parenthesis_usage="none",
    ),
}


@dataclass
class StyleModifier:
    """说话风格修饰器。

    用于在特定情绪或场景下临时调整说话风格。
    """

    emotion: str  # 关联的情绪
    vocabulary_shift: Optional[str] = None  # 词汇级别调整
    sentence_length_shift: str = "none"  # none/up/down
    exclamation_boost: float = 0.0  # 感叹号频率调整
    question_boost: float = 0.0  # 问号频率调整
    ellipsis_boost: float = 0.0  # 省略号频率调整
    extra_fillers: list[str] = field(default_factory=list)  # 额外口头禅
    tone_indicator: Optional[str] = None  # 语气指示词

    def apply(self, base_style: SpeakingStyle) -> SpeakingStyle:
        """将修饰器应用到基础风格。

        Args:
            base_style: 基础风格

        Returns:
            调整后的风格
        """
        # 复制基础风格
        style = SpeakingStyle(
            vocabulary_level=self.vocabulary_shift or base_style.vocabulary_level,
            sentence_length=base_style.sentence_length,
            exclamation_rate=base_style.exclamation_rate + self.exclamation_boost,
            question_rate=base_style.question_rate + self.question_boost,
            ellipsis_rate=base_style.ellipsis_rate + self.ellipsis_boost,
            filler_words=base_style.filler_words.copy(),
            emotion_words=base_style.emotion_words.copy(),
            emoji_usage=base_style.emoji_usage,
            parenthesis_usage=base_style.parenthesis_usage,
        )

        # 句长调整
        if self.sentence_length_shift == "up":
            length_order = ["short", "medium", "long", "varied"]
            current_idx = length_order.index(style.sentence_length) if style.sentence_length in length_order else 1
            style.sentence_length = length_order[min(current_idx + 1, len(length_order) - 1)]
        elif self.sentence_length_shift == "down":
            length_order = ["short", "medium", "long", "varied"]
            current_idx = length_order.index(style.sentence_length) if style.sentence_length in length_order else 1
            style.sentence_length = length_order[max(current_idx - 1, 0)]

        # 添加额外口头禅
        style.filler_words.extend(self.extra_fillers)

        return style


# 预设情绪修饰器
EMOTION_MODIFIERS = {
    "happy": StyleModifier(
        emotion="happy",
        exclamation_boost=0.15,
        sentence_length_shift="down",
    ),
    "sad": StyleModifier(
        emotion="sad",
        exclamation_boost=-0.1,
        question_boost=0.1,
        sentence_length_shift="down",
        extra_fillers=["...", "唉"],
    ),
    "angry": StyleModifier(
        emotion="angry",
        exclamation_boost=0.2,
        sentence_length_shift="down",
        extra_fillers=["哼", "可恶"],
    ),
    "thinking": StyleModifier(
        emotion="thinking",
        question_boost=0.15,
        ellipsis_boost=0.1,
        sentence_length_shift="up",
    ),
    "surprised": StyleModifier(
        emotion="surprised",
        exclamation_boost=0.2,
        question_boost=0.1,
        sentence_length_shift="down",
    ),
    "embarrassed": StyleModifier(
        emotion="embarrassed",
        exclamation_boost=-0.1,
        question_boost=0.05,
        extra_fillers=["呃", "那个"],
    ),
}


class SpeakingStyleEngine:
    """说话风格引擎。

    管理角色的说话风格，支持预设风格、自定义配置和动态调整。
    """

    def __init__(
        self,
        base_style: Optional[SpeakingStyle] = None,
        preset_name: Optional[str] = None,
    ):
        """初始化说话风格引擎。

        Args:
            base_style: 自定义基础风格
            preset_name: 预设风格名称
        """
        if preset_name and preset_name in PRESET_STYLES:
            self.base_style = PRESET_STYLES[preset_name]
        elif base_style:
            self.base_style = base_style
        else:
            self.base_style = SpeakingStyle()

        self._current_emotion: Optional[str] = None
        self._custom_modifiers: dict[str, StyleModifier] = {}

    def get_style(self, emotion: Optional[str] = None) -> SpeakingStyle:
        """获取当前说话风格。

        Args:
            emotion: 可选的当前情绪

        Returns:
            当前适用的风格
        """
        style = self.base_style

        # 应用情绪修饰器
        if emotion and emotion in EMOTION_MODIFIERS:
            modifier = EMOTION_MODIFIERS[emotion]
            style = modifier.apply(style)
        elif emotion and emotion in self._custom_modifiers:
            modifier = self._custom_modifiers[emotion]
            style = modifier.apply(style)

        return style

    def set_emotion(self, emotion: Optional[str]) -> None:
        """设置当前情绪。

        Args:
            emotion: 情绪类型
        """
        self._current_emotion = emotion

    def add_emotion_modifier(self, modifier: StyleModifier) -> None:
        """添加自定义情绪修饰器。

        Args:
            modifier: 情绪修饰器
        """
        self._custom_modifiers[modifier.emotion] = modifier

    def get_filler_word(self) -> Optional[str]:
        """随机获取一个口头禅。

        Returns:
            口头禅或None
        """
        if not self.base_style.filler_words:
            return None
        return random.choice(self.base_style.filler_words)

    def get_emotion_word(self, emotion: str) -> Optional[str]:
        """获取指定情绪的一个情绪词。

        Args:
            emotion: 情绪类型

        Returns:
            情绪词或None
        """
        emotion_words = self.base_style.emotion_words.get(emotion, [])
        if not emotion_words:
            return None
        return random.choice(emotion_words)

    def should_use_exclamation(self) -> bool:
        """判断是否应该使用感叹号。

        Returns:
            是否使用感叹号
        """
        style = self.get_style(self._current_emotion)
        return random.random() < style.exclamation_rate

    def should_use_emoji(self) -> bool:
        """判断是否应该使用emoji。

        Returns:
            是否使用emoji
        """
        style = self.base_style
        if style.emoji_usage == "none":
            return False
        elif style.emoji_usage == "sparse":
            return random.random() < 0.1
        elif style.emoji_usage == "适量":
            return random.random() < 0.3
        elif style.emoji_usage == "丰富":
            return random.random() < 0.5
        return False

    def get_emoji_for_emotion(self, emotion: str) -> Optional[str]:
        """获取情绪对应的emoji。

        Args:
            emotion: 情绪类型

        Returns:
            emoji或None
        """
        emotion_emoji_map = {
            "happy": ["^_^", "(* ^ ω ^)", "(≧▽≦)", "♪♪♪"],
            "sad": ["(；ω；)", "(´;ω;`)", "(|´・ω・)ノ"],
            "angry": ["(╯°□°）╯︵ ┻━┻", "(｀Д´)"],
            "thinking": ["(；・∀・)", "(´・ω・｀)", "(-_-;)"],
            "surprised": ["(´°△°`)", "(°o°)", "Σ(°△°|||)"],
            "embarrassed": ["(*/ω＼*)", "(〃▽〃)", "(*/ω\\*)"],
            "neutral": [],
        }
        emojis = emotion_emoji_map.get(emotion, [])
        if not emojis:
            return None
        return random.choice(emojis)

    def build_style_prompt(self, emotion: Optional[str] = None) -> str:
        """构建风格指导Prompt。

        用于在系统提示中加入说话风格指导。

        Args:
            emotion: 可选的当前情绪

        Returns:
            风格指导文本
        """
        style = self.get_style(emotion)
        parts = []

        # 词汇复杂度
        if style.vocabulary_level == "simple":
            parts.append("使用简单易懂的语言，避免生僻词汇。")
        elif style.vocabulary_level == "academic":
            parts.append("使用正式、专业的学术语言。")

        # 句长偏好
        if style.sentence_length == "short":
            parts.append("使用短句，简洁明了。")
        elif style.sentence_length == "long":
            parts.append("使用长句，详细阐述。")

        # 口头禅
        if style.filler_words:
            fillers = "、".join(style.filler_words[:3])
            parts.append(f"可以适当使用口头禅：{fillers}。")

        # 情绪词
        if style.emotion_words:
            for emotion, words in style.emotion_words.items():
                if words:
                    emotion_word = words[0]
                    parts.append(f"表达{emotion}时可用：{emotion_word}。")

        # 标点习惯
        if style.exclamation_rate > 0.2:
            parts.append("可以适当使用感叹号表达情感。")
        elif style.exclamation_rate < 0.05:
            parts.append("保持克制的标点使用，避免过多感叹号。")

        return " ".join(parts)

    def to_dict(self) -> dict:
        """转换为字典格式。"""
        return {
            "base_style": self.base_style.to_dict(),
            "current_emotion": self._current_emotion,
            "custom_modifiers": {
                k: {
                    "emotion": v.emotion,
                    "vocabulary_shift": v.vocabulary_shift,
                    "sentence_length_shift": v.sentence_length_shift,
                    "exclamation_boost": v.exclamation_boost,
                    "question_boost": v.question_boost,
                    "extra_fillers": v.extra_fillers,
                    "tone_indicator": v.tone_indicator,
                }
                for k, v in self._custom_modifiers.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SpeakingStyleEngine":
        """从字典创建对象。"""
        base_style = SpeakingStyle.from_dict(data.get("base_style", {}))
        engine = cls(base_style=base_style)
        engine._current_emotion = data.get("current_emotion")

        for k, v in data.get("custom_modifiers", {}).items():
            modifier = StyleModifier(
                emotion=v["emotion"],
                vocabulary_shift=v.get("vocabulary_shift"),
                sentence_length_shift=v.get("sentence_length_shift", "none"),
                exclamation_boost=v.get("exclamation_boost", 0.0),
                question_boost=v.get("question_boost", 0.0),
                extra_fillers=v.get("extra_fillers", []),
                tone_indicator=v.get("tone_indicator"),
            )
            engine._custom_modifiers[k] = modifier

        return engine


def get_preset_style(name: str) -> Optional[SpeakingStyle]:
    """获取预设风格。

    Args:
        name: 预设名称

    Returns:
        SpeakingStyle或None
    """
    return PRESET_STYLES.get(name)


def list_preset_styles() -> list[str]:
    """列出所有预设风格名称。

    Returns:
        预设名称列表
    """
    return list(PRESET_STYLES.keys())
