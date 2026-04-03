# Agent Core Brain 模块详细文档

## 模块概览

Brain 模块位于 `src/agent_core/brain/`，负责 Agent 的人格、历史、配置、标签持久化和 Prompt 构建。灵感来源于 OpenClaw 的提示生成和内存管理机制。

---

## 1. persona.py - 人格模块

定义 Agent 角色的人格特质，包括基本资料、背景故事和记忆系统。支持三种记忆类型：情景记忆(episodic)、偏好记忆(preference)、事实记忆(fact)。

### 1.1 PersonaProfile

角色基本配置数据类。

**字段**：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| name | str | - | 角色名称 |
| age | Optional[int] | None | 年龄 |
| gender | str | "unknown" | 性别 |
| personality_traits | list[str] | [] | 性格特征列表 |
| background | str | "" | 背景故事描述 |
| speaking_style | str | "friendly" | 说话风格 |
| birthday | Optional[str] | None | 生日 |
| interests | list[str] | [] | 兴趣爱好列表 |

**方法**：

```python
def to_dict() -> dict
```
序列化为字典格式。

```python
@classmethod
def from_dict(cls, data: dict) -> "PersonaProfile"
```
从字典反序列化创建对象。

---

### 1.2 MemoryEntry

单条记忆条目数据类。

**字段**：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| id | str | - | 记忆唯一标识符 |
| content | str | - | 记忆内容 |
| timestamp | float | - | 时间戳 |
| memory_type | str | "episodic" | 记忆类型 (episodic/preference/fact) |
| importance | float | 1.0 | 重要性等级 (0.0-2.0) |
| context | Optional[str] | None | 关联上下文/话题 |

**方法**：

```python
def to_dict() -> dict
```
序列化为字典格式。

```python
@classmethod
def from_dict(cls, data: dict) -> "MemoryEntry"
```
从字典反序列化创建对象。

---

### 1.3 Persona

人格管理器类。管理角色的配置和记忆，支持情景记忆、偏好记忆和事实记忆的存储与检索。

```python
def __init__(profile: PersonaProfile)
```
初始化人格管理器。

```python
def add_memory(
    content: str,
    memory_type: str = "episodic",
    importance: float = 1.0,
    context: Optional[str] = None,
) -> MemoryEntry
```
添加新记忆。自动生成唯一ID格式：`mem_{counter}_{timestamp}`，根据 memory_type 加入对应列表。

```python
def get_recent_memories(
    limit: int = 10,
    memory_type: Optional[str] = None,
) -> list[MemoryEntry]
```
获取最近的记忆。按时间倒序返回，可按类型过滤。memory_type 可选值："episodic" / "preference" / "fact"。

```python
def search_memories(query: str, limit: int = 5) -> list[MemoryEntry]
```
搜索记忆。基于关键词的简单包含匹配（大小写不敏感）。

```python
def to_dict() -> dict
```
序列化为字典格式。

```python
@classmethod
def from_dict(cls, data: dict) -> "Persona"
```
从字典反序列化创建对象。

```python
def build_persona_text() -> str
```
构建用于 Prompt 的人格描述文本。格式示例："你叫牧濑红莉潜。年龄：20岁。性别：女性。性格特点：聪明、理性。说话风格：傲娇。背景：..."

---

## 2. history.py - 历史消息管理模块

提供基于 Token 感知的历史消息管理系统，包含消息权重计算（角色权重 + 时间衰减 + 重要性）、每日摘要生成、Token 预算感知的消息队列。

### 2.1 MessageRole

消息角色枚举。

```python
USER = "user"         # 用户消息
ASSISTANT = "assistant"  # 助手回复
SYSTEM = "system"     # 系统消息
TOOL = "tool"         # 工具调用/结果
```

---

### 2.2 Message

单条对话消息数据类。

**字段**：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| id | str | - | 消息唯一标识符 |
| role | MessageRole | - | 消息角色 |
| content | str | - | 消息内容 |
| timestamp | float | - | 时间戳 |
| token_count | Optional[int] | None | Token数量估计 |
| weight | float | 1.0 | 消息权重 |
| is_important | bool | False | 是否标记为重要 |
| tags | list[str] | [] | 消息标签列表 |
| tool_name | Optional[str] | None | 关联的工具名称 |
| reply_to | Optional[str] | None | 回复的消息ID |

**方法**：

```python
def to_dict() -> dict
```
序列化为字典格式。

```python
@classmethod
def from_dict(cls, data: dict) -> "Message"
```
从字典反序列化创建对象。

---

### 2.3 DailySummary

每日对话摘要数据类。

**字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| date | str | 日期字符串 (YYYY-MM-DD) |
| summary_text | str | 摘要文本 |
| important_messages | list[str] | 重要消息ID列表 |
| topics | list[str] | 讨论话题列表 |
| message_count | int | 消息总数 |
| created_at | float | 创建时间戳 |
| emotional_tone | Optional[str] | 情感基调（LLM驱动新增） |
| user_preferences | list[str] | 用户偏好列表（LLM驱动新增） |
| unfinished_topics | list[str] | 未完成话题列表（LLM驱动新增） |

---

### 2.4 工具函数

#### estimate_tokens

```python
def estimate_tokens(text: str) -> int
```
估算文本的 Token 数量。使用字符数除以4作为粗略估计（适用于英文）。对于中文，每个字符可能对应更多 Token。

#### calculate_message_weight

```python
def calculate_message_weight(
    message: Message,
    max_age_hours: float = 168.0,  # 7天
) -> float
```
计算消息的有效权重。

**权重公式**：
```
权重 = 基础权重 × 时间衰减因子 × 重要性倍率
```

- 基础权重（来自角色类型）：USER=1.0, ASSISTANT=0.8, SYSTEM=0.3, TOOL=0.5
- 时间衰减因子：`max(0.1, 1.0 - (age_hours / max_age_hours))`
- 重要性倍率：`2.0` if is_important else `1.0`

#### detect_importance

```python
def detect_importance(content: str) -> bool
```
根据 IMPORTANT_PATTERNS 正则匹配检测消息是否包含重要关键词。检测范围包括中英文关键词，如"记住| forget |重要| important |喜欢| love"等。

---

### 2.5 MessageQueue

当日消息队列。当日消息先进入队列，通过特定机制才加入主上下文。

```python
def __init__(threshold: int = 100)
```
初始化消息队列。threshold 为触发 flush 的消息数量阈值。

```python
def add(message: Message) -> None
```
添加消息到队列。

```python
def should_flush() -> bool
```
检查队列是否应该 flush 到主历史。返回 `len(self.messages) >= self.threshold`。

```python
def clear() -> list[Message]
```
清空队列并返回所有消息。

```python
def get_weighted_sum() -> float
```
获取队列中所有消息的权重总和。

```python
def to_dict() -> dict
def @classmethod from_dict(cls, data: dict) -> "MessageQueue"
```

---

### 2.6 DailyHistory

单日历史记录管理器。

```python
def __init__(date_str: str)
```
初始化当日历史。date_str 格式为 "YYYY-MM-DD"。

```python
def add_message(message: Message) -> None
```
添加消息到当日历史。

```python
def get_messages() -> list[Message]
```
获取当日所有消息。

```python
def generate_summary(config: Optional[dict] = None) -> DailySummary
```
生成当日对话摘要。

**算法**：
1. 对每条消息打分（工具调用得高分、用户消息带意图、显式标记重要、中等长度优先）
2. 按得分降序排序
3. 选择得分最高的5条消息
4. 提取话题关键词
5. 构建摘要文本

```python
def _extract_topics() -> list[str]
```
基于关键词提取话题。检测话题类别：工作、个人、技术、购物、娱乐（中英文）。

---

### 2.7 MessageHistory

主历史记录管理器。提供 Token 感知的历史消息选择和管理功能。

```python
def __init__(
    max_context_tokens: int = 4000,
    token_reserved: int = 1000,
    retention_days: int = 30,
)
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| max_context_tokens | 4000 | 最大上下文Token数 |
| token_reserved | 1000 | 为系统提示保留的Token数 |
| retention_days | 30 | 历史消息保留天数 |

```python
def add_message(
    content: str,
    role: MessageRole,
    tool_name: Optional[str] = None,
    is_important: bool = False,
    tags: Optional[list[str]] = None,
    timestamp: Optional[float] = None,
) -> Message
```
添加消息到历史。自动检测是否包含重要关键词（仅对 USER 角色）。

```python
def should_trigger_queue_insert() -> bool
```
检查是否应该触发队列插入到上下文。

```python
def get_context_messages(max_tokens: Optional[int] = None) -> list[Message]
```
获取在 Token 预算内的上下文消息。

**算法**：
1. 计算可用预算：`max_tokens or (max_context_tokens - token_reserved)`
2. 获取近3天的每日摘要（约占预算25%）
3. 获取当日队列消息，按权重排序
4. 按预算依次添加消息
5. 最终按时间顺序返回

```python
def finalize_day() -> DailySummary
```
结束当日并生成摘要。同时将摘要存入 daily_summaries，清空 current_queue。

```python
def cleanup_old_data() -> int
```
清理超过保留期的历史数据。返回清理的天数。

```python
def get_recent_summaries(days: int = 3) -> list[DailySummary]
```
获取近期的每日摘要。

---

### 2.8 SummaryGenerator

LLM驱动的摘要生成器。使用 LLM 生成高质量的对话摘要，替代规则驱动的方法。

```python
def __init__(
    llm_callable: Optional[LLMCallable] = None,
    use_fallback: bool = True,
)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| llm_callable | LLMCallable | LLM调用函数，签名为 `(prompt: str) -> str`，为None时使用规则后备 |
| use_fallback | bool | 当LLM调用失败时是否使用规则后备 |

```python
def generate_summary(
    date: str,
    messages: list[Message],
    config: Optional[dict] = None,
) -> DailySummary
```
生成每日摘要。优先尝试 LLM 生成，失败时根据 use_fallback 决定是否使用规则后备。

---

### 2.9 AsyncSummaryGenerator

异步 LLM 驱动的摘要生成器。支持异步 LLM 调用（如 aiohttp 或 asyncio）。

```python
def __init__(
    llm_callable: Callable[[str], Awaitable[str]],
    use_fallback: bool = True,
)
```

---

## 3. config.py - 配置管理模块

提供 Agent 的基础配置管理，包括历史记录配置、标签配置、存储配置等。

### 3.1 HistoryConfig

历史消息管理配置。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| max_context_tokens | int | 4000 | 最大上下文Token数 |
| daily_queue_threshold | int | 100 | 触发队列插入的消息数量阈值 |
| importance_threshold | float | 0.5 | 重要性阈值 |
| retention_days | int | 30 | 历史消息保留天数 |
| summary_trigger_messages | int | 50 | 触发生成摘要的消息数量 |
| token_reserved | int | 1000 | 为系统提示等保留的Token数量 |

### 3.2 TagsConfig

回复标签配置。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| auto_generate | bool | True | 是否自动生成标签 |
| emotion_model | str | "keyword" | 情感识别模式: "keyword" 或 "llm" |
| default_emotion | str | "neutral" | 默认情感 |
| default_expression | str | "neutral" | 默认表情 |

### 3.3 StorageConfig

存储配置。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| data_dir | str | "./data" | 数据存储根目录 |
| format | str | "json" | 存储格式: "json" 或 "md" |

```python
@property
def data_path(self) -> Path
```
获取数据目录路径。

### 3.4 PersonaConfig

人格基础配置。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| name | str | "Assistant" | 角色名称 |
| age | Optional[int] | None | 年龄 |
| gender | str | "unknown" | 性别 |

### 3.5 AgentConfig

Agent 主配置类。组合 persona, history, tags, storage 四个子配置。

```python
def __post_init__(self)
```
自动将字典类型的输入转换为正确的 dataclass 类型。

```python
@classmethod
def from_dict(cls, data: dict) -> "AgentConfig"
def to_dict(self) -> dict
```

---

## 4. tags.py - 回复标签模块

为每条回复生成标签，供 UI 层显示角色立绘表情、动作等。支持多语言（中英文）关键词检测和 LLM 解析两种模式。

### 4.1 常量

#### ALL_EMOTIONS

LLM 解析输出的固定情感列表，共 9 种：

```
happy, sad, angry, surprised, thinking, scared, embarrassed, confused, neutral
```

#### EMOTION_KEYWORDS

精简高确定性关键词映射（多语言）。

| 情感 | 英文关键词 | 中文关键词 |
|------|-----------|-----------|
| happy | happy, glad, joy, love, wonderful, great, excited, fantastic, perfect, haha, lol | 开心, 高兴, 快乐, 幸福, 太好, 哈哈, 棒, 完美, 喜欢 |
| sad | sad, cry, tears, depressed, miss, unhappy, lonely, hurt, pain, sorry | 伤心, 难过, 悲伤, 哭, 眼泪, 抑郁, 失落, 痛苦, 遗憾 |
| angry | angry, mad, hate, rage, furious, annoyed, stupid, idiot | 生气, 愤怒, 讨厌, 可恶, 恨, 气死了, 烦, 讨厌 |
| surprised | wow, surprised, shocked, omg, unexpected, amazing | 哇, 惊讶, 震惊, 真的, 什么, 想不到, 竟然 |
| thinking | think, wonder, consider, maybe, hmm, not sure, curious | 想, 思考, 考虑, 也许, 可能, 估计, 琢磨 |
| scared | scared, afraid, fear, worried, nervous, anxious, terrified | 害怕, 恐惧, 担心, 紧张, 可怕, 危险, 不安 |
| embarrassed | embarrassed, awkward, blush, shy, mistake, oops | 尴尬, 害羞, 不好意思, 脸红, 丢人, 糗 |
| confused | confused, puzzled, don't understand, unclear, strange | 困惑, 不明白, 不清楚, 什么意思, 搞不懂, 迷糊, 懵 |

#### EMOTION_TO_EXPRESSION

情感到面部表情的映射。

| 情感 | 表情 |
|------|------|
| happy | smile |
| sad | frown |
| angry | scowl |
| surprised | gasp |
| thinking | focused |
| scared | worried |
| embarrassed | blush |
| confused | puzzled |
| neutral | neutral |

#### ACTION_KEYWORDS

动作关键词映射。动作类型：wave, nod, shake_head, clap, pat, facepalm, shrug

#### OVERLAY_KEYWORDS

特效叠加层关键词映射。叠加层类型：blush, sweat_drop, tears, sparkle, anger_mark, question_mark

---

### 4.2 ReplyTag

单条回复的标签数据类。

**标签类型**：

| 类型 | 说明 |
|------|------|
| emotion | 情感状态 |
| expression | 面部表情 |
| action | 身体动作 |
| pose | 姿态 (standing/sitting/lying) |
| overlay | 特效叠加层 |

**字段**：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| message_id | str | - | 关联的消息ID |
| emotion | str | "neutral" | 情感状态 |
| expression | str | "neutral" | 面部表情 |
| action | Optional[str] | None | 身体动作 |
| pose | str | "standing" | 姿态 |
| overlays | list[str] | [] | 特效叠加层列表 |
| intensity | float | 1.0 | 表情强度 (0.0-2.0) |
| timestamp | float | 当前时间 | 时间戳 |

---

### 4.3 TagGenerator

回复标签生成器。支持两种情感解析模式：`keyword`（关键词匹配）和 `llm`（LLM 解析）。

```python
def __init__(
    default_emotion: str = "neutral",
    default_expression: str = "neutral",
    llm_callable: Optional[Callable[[str], str]] = None,
    emotion_mode: str = "keyword",
)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| default_emotion | str | 默认情感 |
| default_expression | str | 默认表情 |
| llm_callable | Callable | LLM调用函数，签名为 `(prompt: str) -> str` |
| emotion_mode | str | 解析模式：`"keyword"` 或 `"llm"` |

#### 模式切换

```python
def set_emotion_mode(mode: str) -> None
```
设置情感解析模式。mode 必须为 `"keyword"` 或 `"llm"`。

```python
def set_llm_callable(llm_callable: Callable[[str], str]) -> None
```
设置 LLM 调用函数。

```python
def detect_emotion(text: str) -> tuple[str, float]
```
从文本内容检测情感。自动根据 `emotion_mode` 选择：
- `"keyword"`：多语言关键词匹配
- `"llm"`：调用 LLM 解析

返回 `(情感类型, 置信度)`。

```python
def detect_expression(emotion: str) -> str
```
根据情感获取对应表情。

```python
def detect_action(text: str) -> Optional[str]
```
从文本检测动作。

```python
def detect_overlays(text: str, emotion: str) -> list[str]
```
检测特效叠加层。

```python
def calculate_intensity(text: str, emotion: str) -> float
```
计算表情强度。

**强度修饰因子**：
- 增强修饰词（very, really, 非常, 特别）：+0.2
- 弱化修饰词（slightly, a bit, 有点）：-0.2
- 多感叹号：+0.3 × min(数量, 3)
- 多问号：+0.2 × min(数量, 3)

返回范围：`max(0.3, min(2.0, base))`

```python
def generate_tag(
    message_id: str,
    content: str,
    context: Optional[str] = None,
) -> ReplyTag
```
生成完整的回复标签。

---

### 4.4 TagCache

回复标签缓存。存储最近使用过的标签，支持按 ID 查询和 LRU 淘汰。

```python
def __init__(max_size: int = 100)
```

```python
def add(tag: ReplyTag) -> None
```
添加标签到缓存。超量时淘汰最旧的条目。

```python
def get(message_id: str) -> Optional[ReplyTag]
```
根据消息ID获取标签。

```python
def get_recent(limit: int = 10) -> list[ReplyTag]
```
获取最近的标签列表。按时间倒序返回。

---

## 5. speaking_style.py - 说话风格引擎模块

提供动态的说话风格控制，包括词汇复杂度、句长偏好、标点习惯、口头禅/填充词、情绪指示词。

### 5.1 SpeakingStyle

说话风格配置数据类。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| vocabulary_level | str | "common" | 词汇复杂度 (simple/common/academic) |
| sentence_length | str | "varied" | 句长偏好 (short/medium/long/varied) |
| exclamation_rate | float | 0.1 | 感叹号使用频率 (0.0-1.0) |
| question_rate | float | 0.15 | 问号使用频率 (0.0-1.0) |
| ellipsis_rate | float | 0.05 | 省略号使用频率 (0.0-1.0) |
| filler_words | list[str] | [] | 口头禅/填充词列表 |
| emotion_words | dict[str, list[str]] | {} | 情绪词列表（按情绪分类） |
| emoji_usage | str | "none" | emoji使用偏好 (none/sparse/适量/丰富) |
| parenthesis_usage | str | "sparse" | 括号使用偏好 (none/sparse/适量) |

```python
def to_dict() -> dict
def @classmethod from_dict(cls, data: dict) -> "SpeakingStyle"
```

---

### 5.2 PRESET_STYLES

预设说话风格字典。

| 预设名 | vocabulary_level | sentence_length | 说明 |
|--------|------------------|-----------------|------|
| cheerful | simple | short | 活泼可爱型 |
| gentle | common | medium | 温柔体贴型 |
| professional | academic | long | 专业正式型 |
| casual | common | varied | 轻松随意型 |
| analytical | academic | long | 冷静理性型 |
| humorous | common | short | 幽默风趣型 |
| tsundere | common | short | 高冷傲娇型 |

---

### 5.3 StyleModifier

说话风格修饰器。用于在特定情绪或场景下临时调整说话风格。

**字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| emotion | str | 关联的情绪 |
| vocabulary_shift | Optional[str] | 词汇级别调整 |
| sentence_length_shift | str | none/up/down |
| exclamation_boost | float | 感叹号频率调整 |
| question_boost | float | 问号频率调整 |
| ellipsis_boost | float | 省略号频率调整 |
| extra_fillers | list[str] | 额外口头禅 |
| tone_indicator | Optional[str] | 语气指示词 |

```python
def apply(self, base_style: SpeakingStyle) -> SpeakingStyle
```
将修饰器应用到基础风格。复制基础风格后应用各项调整。

---

### 5.4 EMOTION_MODIFIERS

预设情绪修饰器字典。包含：happy, sad, angry, thinking, surprised, embarrassed。

---

### 5.5 SpeakingStyleEngine

说话风格引擎。管理角色的说话风格，支持预设风格、自定义配置和动态调整。

```python
def __init__(
    base_style: Optional[SpeakingStyle] = None,
    preset_name: Optional[str] = None,
    influence_weight: float = 1.0,
)
```

| 参数 | 说明 |
|------|------|
| base_style | 自定义基础风格 |
| preset_name | 预设风格名称，优先级高于 base_style |
| influence_weight | 影响权重 (0.0-1.0)，0.0 = 几乎不影响，1.0 = 完全影响 |

```python
def get_style(emotion: Optional[str] = None) -> SpeakingStyle
```
获取当前说话风格。应用情绪修饰器（EMOTION_MODIFIERS 或自定义 _custom_modifiers）。

```python
def set_emotion(emotion: Optional[str]) -> None
```
设置当前情绪。

```python
def add_emotion_modifier(modifier: StyleModifier) -> None
```
添加自定义情绪修饰器。

```python
def get_filler_word() -> Optional[str]
```
随机获取一个口头禅。

```python
def get_emotion_word(emotion: str) -> Optional[str]
```
获取指定情绪的一个情绪词。

```python
def should_use_exclamation() -> bool
```
基于当前风格的 exclamation_rate 随机判断是否使用感叹号。

```python
def should_use_emoji() -> bool
```
基于 emoji_usage 判断是否使用 emoji。频率：none=0%, sparse=10%, 适量=30%, 丰富=50%。

```python
def get_emoji_for_emotion(emotion: str) -> Optional[str]
```
获取情绪对应的 emoji。

**情绪emoji映射**：
- happy: `^_^`, `(* ^ ω ^)`, `(≧▽≦)`, `♪♪♪`
- sad: `(`；ω；`)`, `(´;ω;`)`, `(|´・ω・)ノ`
- angry: `(╯°□°）╯︵ ┻━┻`, `(｀Д´)`
- thinking: `(；・∀・)`, `(´・ω・｀)`, `(-_-;)`
- surprised: `(´°△°`)`, `(°o°)`, `Σ(°△°|||)`
- embarrassed: `(*/ω＼*)`, `(〃▽〃)`

```python
def build_style_prompt(emotion: Optional[str] = None) -> str
```
构建风格指导 Prompt。根据 influence_weight 决定详细程度：

| 权重阈值 | 输出内容 |
|----------|----------|
| > 0.3 | 词汇复杂度、句长偏好 |
| > 0.5 | 标点习惯 |
| > 0.6 | 口头禅（最多2个） |
| > 0.7 | 情绪词 |

```python
def to_dict() -> dict
def @classmethod from_dict(cls, data: dict) -> "SpeakingStyleEngine"
```

---

## 6. persistence.py - 持久化存储模块

提供 JSON 和 Markdown 格式的文件存储功能。每个模块独立存储文件，便于跨设备同步。

### 6.1 存储目录结构

```
data/
  persona/
    profile.json      # 角色基本配置
    memories.json     # 记忆数据
  history/
    daily/
      YYYY-MM-DD.json      # 每日消息
      YYYY-MM-DD.summary.md # 每日摘要
    queue.json        # 当前队列
    weights.json      # 权重配置
    index.json        # 主索引
  tags/
    reply_tags.json   # 回复标签缓存
    emotion_map.json  # 情感映射
  config/
    agent_config.json # Agent配置
```

---

### 6.2 FileStorage

基于文件的存储基类。

```python
def __init__(base_dir: str = "./data")
```
初始化文件存储，自动创建必要的目录结构。

```python
def _ensure_directories() -> None
```
创建必要的目录结构。

```python
def _read_json(path: Path) -> Optional[dict]
```
安全读取 JSON 文件。失败返回 None。

```python
def _write_json(path: Path, data: dict) -> bool
```
安全写入 JSON 文件。使用 `ensure_ascii=False, indent=2`。

```python
def _read_md(path: Path) -> Optional[str]
def _write_md(path: Path, content: str) -> bool
```

---

### 6.3 PersonaStorage

人格数据存储。

| 方法 | 说明 |
|------|------|
| `save_profile(persona)` | 保存 profile.json |
| `load_profile()` | 加载 profile.json，返回 dict |
| `save_memories(persona)` | 保存 memories.json |
| `load_memories()` | 加载 memories.json，返回 dict |
| `save_full(persona)` | 同时保存 profile 和 memories |
| `load_full()` | 加载完整人格数据，返回 Persona 或 None |

---

### 6.4 HistoryStorage

历史消息存储。

| 方法 | 说明 |
|------|------|
| `save_daily_messages(date, messages, summary)` | 保存每日消息到 JSON |
| `load_daily_messages(date)` | 加载每日消息 |
| `save_daily_summary_md(summary)` | 保存每日摘要为 Markdown（人类可读格式） |
| `save_queue(queue_data)` | 保存当前队列状态 |
| `load_queue()` | 加载队列状态 |
| `save_weights(weights)` | 保存消息权重配置 |
| `load_weights()` | 加载消息权重配置 |
| `save_full_history(history)` | 保存完整的历史数据（每日消息、摘要、队列、索引） |
| `load_full_history()` | 加载完整的历史数据 |

---

### 6.5 TagsStorage

回复标签存储。

| 方法 | 说明 |
|------|------|
| `save_tags(cache)` | 保存标签缓存 |
| `load_tags()` | 加载标签缓存，返回 TagCache 或 None |
| `save_tag(tag)` | 保存单条标签（追加到缓存） |
| `save_emotion_map(emotion_map)` | 保存自定义情感映射 |
| `load_emotion_map()` | 加载情感映射 |

---

### 6.6 ConfigStorage

配置存储。

| 方法 | 说明 |
|------|------|
| `save_config(config)` | 保存 Agent 配置 |
| `load_config()` | 加载 Agent 配置 |

---

### 6.7 AgentStorage

统一的存储管理器。整合所有类型的存储操作。

```python
def __init__(base_dir: str = "./data")
```
初始化统一存储管理器，同时初始化 persona, history, tags, config 四个存储实例。

| 方法 | 说明 |
|------|------|
| `save_all_persona(persona)` | 保存所有人格数据 |
| `load_all_persona()` | 加载所有人格数据 |
| `save_all_history(history)` | 保存所有历史数据 |
| `load_all_history()` | 加载所有历史数据 |
| `save_all_tags(cache)` | 保存所有标签数据 |
| `load_all_tags()` | 加载所有标签数据 |

---

## 7. prompt_builder.py - Prompt 构建模块

提供分段的 Prompt 构建功能，参考 OpenClaw 的系统提示构建方式。

### 7.1 构建顺序

1. 身份定义 (Identity)
2. 人格特点 (Personality)
3. 近期记忆 (Recent Memories)
4. 历史摘要 (History Summaries)
5. 队列消息 (Queue Messages)
6. 运行时信息 (Runtime Info)

---

### 7.2 PromptBuilder

分段式 Prompt 构建器。

```python
def __init__(
    persona: Persona,
    history: Optional[MessageHistory] = None,
    config: Optional[AgentConfig] = None,
    style_engine: Optional[SpeakingStyleEngine] = None,
)
```

```python
def build_identity_section() -> str
```
构建身份/角色定义段落。调用 `persona.build_persona_text()`。

```python
def build_style_section(emotion: Optional[str] = None) -> str
```
构建说话风格指导段落。调用 `style_engine.build_style_prompt(emotion=emotion)`。

```python
def build_memory_section(limit: int = 5) -> str
```
构建近期记忆段落。格式：
```
## 近期记忆
- [2024-01-01] 记忆内容...
```

```python
def build_search_memory_section(query: str, limit: int = 3) -> str
```
构建搜索相关的记忆段落。根据关键词搜索匹配的记忆。

```python
def build_history_summary_section(days: int = 3) -> str
```
构建近期对话摘要段落。获取近 N 天的每日摘要。

```python
def build_queue_section(max_tokens: Optional[int] = None) -> str
```
构建当前队列消息段落。获取在 Token 预算内的上下文消息。

```python
def build_runtime_section(timezone: str = "Asia/Shanghai") -> str
```
构建运行时信息段落。包含日期、时间、星期（带中文映射）。

```python
def build_system_prompt(emotion: Optional[str] = None) -> str
```
构建完整的系统 Prompt。按顺序包含所有段落。

```python
def build_context_prompt(
    query: Optional[str] = None,
    include_queue: bool = True,
    max_queue_tokens: Optional[int] = None,
    emotion: Optional[str] = None,
) -> str
```
构建上下文 Prompt。可选包含搜索相关的记忆。

---

### 7.3 便捷函数

```python
def build_minimal_prompt(persona: Persona, message: str) -> str
```
构建最小 Prompt（仅身份和当前消息）。格式：
```
你叫{name}。
用户：{message}
助手：
```

```python
def build_full_conversation_prompt(
    persona: Persona,
    history: MessageHistory,
    current_message: str,
    config: Optional[AgentConfig] = None,
    style_engine: Optional[SpeakingStyleEngine] = None,
    emotion: Optional[str] = None,
) -> str
```
构建完整的对话 Prompt。这是每个 Agent 轮次使用的主要 Prompt。

```python
def build_memory_flush_prompt(
    date: str,
    message_count: int,
    messages: list,
) -> str
```
构建记忆刷新 Prompt。用于将对话内容刷新到每日记忆文件中。包含最近10条消息预览，并指示 LLM 保存到 `memory/{date}.md`。

---

## 8. 模块依赖关系

```
__init__.py (统一导出)
├── persona.py
│   ├── PersonaProfile
│   ├── MemoryEntry
│   └── Persona
├── history.py
│   ├── MessageRole
│   ├── Message
│   ├── DailySummary
│   ├── MessageQueue
│   ├── DailyHistory
│   ├── MessageHistory
│   ├── SummaryGenerator
│   ├── AsyncSummaryGenerator
│   └── 工具函数 (estimate_tokens, calculate_message_weight, detect_importance)
├── config.py
│   ├── HistoryConfig
│   ├── TagsConfig
│   ├── StorageConfig
│   ├── PersonaConfig
│   └── AgentConfig
├── tags.py
│   ├── ReplyTag
│   ├── TagGenerator
│   └── TagCache
├── speaking_style.py
│   ├── SpeakingStyle
│   ├── StyleModifier
│   ├── SpeakingStyleEngine
│   ├── PRESET_STYLES
│   ├── EMOTION_MODIFIERS
│   └── 便捷函数
├── persistence.py
│   ├── FileStorage (基类)
│   ├── PersonaStorage
│   ├── HistoryStorage
│   ├── TagsStorage
│   ├── ConfigStorage
│   └── AgentStorage
└── prompt_builder.py
    ├── PromptBuilder
    └── 便捷函数
```
