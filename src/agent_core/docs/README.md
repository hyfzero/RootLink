# Agent Core 核心层文档

## 概述

Agent Core 是一个 Python 实现的 Agent 核心层，灵感来源于 OpenClaw 的提示生成和内存管理机制。提供角色人格、历史消息管理、回复标签生成和持久化存储功能。

### 核心特性

- **人格系统**：支持年龄、性别、生平、性格等多维度角色定义
- **记忆管理**：情景记忆、偏好记忆、事实记忆三种类型
- **历史消息**：基于 Token 感知的权重管理和队列机制
- **回复标签**：自动生成表情、动作、姿态等UI显示标签
- **多语言支持**：中英文关键词检测和Unicode文本处理
- **持久化存储**：JSON/Markdown 分文件存储，便于跨设备同步

---

## 模块结构

```
agent_core/                    # 核心代码
├── __init__.py               # 包入口，导出所有公共API
├── config.py                 # 配置管理
├── persona.py                # 人格模块
├── history.py                # 历史消息管理
├── tags.py                   # 回复标签生成
├── persistence.py            # 持久化存储
├── prompt_builder.py         # Prompt构建器
├── docs/                     # 文档
│   ├── README.md             # 本文档
│   └── SPEC.md              # 英文规范文档
├── tests/                    # 测试代码
│   ├── test_agent_core.py   # 基础功能测试
│   └── test_amadues_kurisu.py  # 牧濑红莉栖人格测试
└── data/                     # 数据存储（运行时生成）
```

---

## 快速开始

### 基本使用

```python
from agent_core import (
    Persona, PersonaProfile, MessageHistory, MessageRole,
    PromptBuilder, AgentStorage, TagGenerator
)

# 1. 创建角色人格
profile = PersonaProfile(
    name="红莉栖",
    age=18,
    gender="female",
    personality_traits=["天才", "傲娇", "温柔"],
    background="18岁的天才少女科学家，就读于维克托多利亚大学。",
    speaking_style="傲娇但内心温柔，对冈部伦太郎有特殊的情感。"
)
persona = Persona(profile)

# 2. 添加记忆
persona.add_memory(
    content="用户是一个中二病患者，经常说些奇怪的话",
    memory_type="episodic",
    importance=1.5,
    context="用户特征"
)
persona.add_memory(
    content="用户喜欢在晚上使用程序",
    memory_type="preference",
    importance=1.0,
    context="使用习惯"
)

# 3. 管理历史消息
history = MessageHistory(max_context_tokens=4000)
history.add_message("晚上好，红莉栖。", MessageRole.USER)
history.add_message("哼，都几点了还来找我。", MessageRole.ASSISTANT)

# 4. 构建Prompt
builder = PromptBuilder(persona, history)
system_prompt = builder.build_system_prompt()

# 5. 生成回复标签
generator = TagGenerator()
tag = generator.generate_tag("msg_1", "哇，太棒了！")
print(f"情感: {tag.emotion}, 表情: {tag.expression}")

# 6. 持久化存储
storage = AgentStorage("./data")
storage.save_all_persona(persona)
storage.save_all_history(history)
```

---

## 模块详解

### 1. config.py - 配置管理

#### AgentConfig

主配置类，管理所有子配置。

```python
from agent_core.config import AgentConfig

config = AgentConfig(
    persona={"name": "红莉栖"},
    history={"max_context_tokens": 5000, "retention_days": 30},
    tags={"auto_generate": True, "emotion_model": "keyword"},
    storage={"data_dir": "./data", "format": "json"}
)
```

**配置项说明：**

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `max_context_tokens` | int | 4000 | 最大上下文Token数 |
| `daily_queue_threshold` | int | 100 | 触发队列插入的消息数阈值 |
| `importance_threshold` | float | 0.5 | 消息重要性阈值 |
| `retention_days` | int | 30 | 历史消息保留天数 |
| `token_reserved` | int | 1000 | 为系统提示保留的Token |

---

### 2. persona.py - 人格模块

#### PersonaProfile

角色配置数据类。

```python
from agent_core.persona import PersonaProfile

profile = PersonaProfile(
    name="红莉栖",
    age=18,
    gender="female",
    personality_traits=["天才", "傲娇", "温柔"],
    background="天才少女科学家，在维克托多利亚大学脑科学研究所工作。",
    speaking_style="傲娇但内心温柔",
    interests=["科学研究", "脑科学", "德国文学"]
)
```

#### Persona

人格管理器，提供记忆的添加、搜索、检索功能。

```python
# 添加记忆
persona.add_memory(
    content="用户喜欢在晚上使用程序",
    memory_type="preference",  # "episodic", "preference", "fact"
    importance=1.5,
    context="使用习惯"
)

# 获取近期记忆
recent = persona.get_recent_memories(limit=10, memory_type="preference")

# 搜索记忆
results = persona.search_memories("德国", limit=5)

# 构建人格文本
persona_text = persona.build_persona_text()
# 输出: "你叫红莉栖。年龄：18岁。性别：女性。..."
```

---

### 3. history.py - 历史消息管理

#### MessageRole

消息角色枚举。

```python
from agent_core.history import MessageRole

MessageRole.USER      # 用户消息
MessageRole.ASSISTANT # 助手回复
MessageRole.SYSTEM    # 系统消息
MessageRole.TOOL      # 工具调用/结果
```

#### MessageHistory

主历史管理器，核心功能：

**消息权重计算：**

```
权重 = 基础权重 × 时间衰减因子 × 重要性倍数

基础权重：
- USER: 1.0
- ASSISTANT: 0.8
- TOOL: 0.5
- SYSTEM: 0.3

时间衰减：每7天减半
重要性倍数：标记重要消息得2x加成
```

**每日摘要生成：**

```python
# 添加消息
history.add_message("内容", MessageRole.USER, is_important=True)

# 结束一天并生成摘要
summary = history.finalize_day()
# DailySummary包含:
# - summary_text: 摘要文本
# - important_messages: 重要消息ID列表
# - topics: 讨论话题列表
# - message_count: 消息总数
```

**Token感知上下文选择：**

```python
# 获取在Token预算内的消息
messages = history.get_context_messages(max_tokens=2000)

# 检查是否应触发队列插入
if history.should_trigger_queue_insert():
    history.finalize_day()
```

---

### 4. tags.py - 回复标签生成

#### ReplyTag

单条回复的标签数据。

```python
@dataclass
class ReplyTag:
    message_id: str     # 关联的消息ID
    emotion: str        # 情感: happy, sad, angry, surprised, thinking...
    expression: str     # 表情: smile, frown, scowl, gasp...
    action: str        # 动作: wave, nod, shake_head, shrug...
    pose: str          # 姿态: standing, sitting, lying
    overlays: list     # 特效: blush, sweat_drop, tears...
    intensity: float   # 强度: 0.3 - 2.0
```

#### TagGenerator

自动标签生成器。

```python
generator = TagGenerator(
    default_emotion="neutral",
    default_expression="neutral"
)

# 生成标签
tag = generator.generate_tag(
    message_id="msg_123",
    content="哇，太棒了！这简直完美！"
)
# tag.emotion -> "happy"
# tag.expression -> "smile"
# tag.intensity -> 1.6  (多个感叹号加强度)
```

**支持的中英文关键词：**

| 情感 | 英文关键词 | 中文关键词 |
|------|-----------|-----------|
| happy | happy, great, awesome, lol | 开心, 高兴, 太好了, 哈哈 |
| sad | sad, cry, miss, tears | 伤心, 难过, 哭泣, 眼泪 |
| angry | angry, mad, hate, grr | 生气, 愤怒, 讨厌, 气死了 |
| thinking | hmm, think, consider, maybe | 嗯, 思考, 也许, 让我想想 |

---

### 5. persistence.py - 持久化存储

#### AgentStorage

统一的存储管理器。

```python
from agent_core import AgentStorage

storage = AgentStorage("./data")

# 保存
storage.save_all_persona(persona)
storage.save_all_history(history)
storage.save_all_tags(tag_cache)

# 加载
persona = storage.load_all_persona()
history = storage.load_all_history()
tags = storage.load_all_tags()
```

**文件结构：**

```
data/
├── persona/
│   ├── profile.json      # 角色配置
│   └── memories.json     # 记忆数据
├── history/
│   ├── daily/
│   │   ├── 2026-03-21.json       # 每日消息
│   └── 2026-03-21.summary.md      # 每日摘要(人类可读)
│   ├── queue.json        # 当前队列
│   ├── weights.json      # 权重配置
│   └── index.json        # 历史索引
├── tags/
│   ├── reply_tags.json   # 标签缓存
│   └── emotion_map.json  # 情感映射
└── config/
    └── agent_config.json # Agent配置
```

---

### 6. prompt_builder.py - Prompt构建器

#### PromptBuilder

分段式Prompt构建器。

```python
builder = PromptBuilder(persona, history, config)

# 构建完整系统Prompt
system_prompt = builder.build_system_prompt()

# 构建上下文Prompt（带搜索）
context_prompt = builder.build_context_prompt(
    query="用户偏好",
    include_queue=True,
    max_queue_tokens=1000
)
```

**构建顺序：**

```
1. 身份定义 (Identity)
   "你叫红莉栖。年龄：18岁..."

2. 近期记忆 (Recent Memories)
   "## 近期记忆
    - [2026-03-20] 用户喜欢在晚上使用..."

3. 历史摘要 (History Summaries)
   "## 近期对话
    ## 2026-03-20
    重要事件：
    - [用户] 询问关于时间机器..."

4. 今日队列 (Queue Messages)
   "## 今日消息
    [user] 晚上好
    [assistant] 哼，都几点了..."

5. 运行时信息 (Runtime Info)
   "## 当前时间
    日期：2026-03-21
    时间：00:11:20
    星期：星期六"
```

---

## 与OpenClaw机制的对应关系

| OpenClaw机制 | Agent Core实现 | 说明 |
|-------------|---------------|------|
| `system-prompt.ts` | `prompt_builder.py` | 分段式Prompt构建 |
| `memory-flush.ts` | `history.py::finalize_day()` | 每日摘要生成 |
| `compact.ts` | `history.py::get_context_messages()` | Token预算管理 |
| `history.ts` | `history.py::MessageQueue` | 消息队列管理 |
| Session持久化 | `persistence.py` | 分文件JSON存储 |
| 消息标签 | `tags.py` | 表情/动作标签 |

---

## 完整示例

```python
from agent_core import (
    Persona, PersonaProfile, MessageHistory, MessageRole,
    PromptBuilder, AgentStorage, TagGenerator, TagCache,
    build_full_conversation_prompt
)
from agent_core.config import AgentConfig

# 初始化
config = AgentConfig(history={"max_context_tokens": 4000})
storage = AgentStorage("./data")

# 加载或创建人格
persona = storage.load_all_persona()
if persona is None:
    profile = PersonaProfile(
        name="红莉栖",
        age=18,
        gender="female",
        personality_traits=["天才", "傲娇", "温柔"],
        background="维克托多利亚大学脑科学研究所的天才研究员。"
    )
    persona = Persona(profile)

# 加载或创建历史
history = storage.load_all_history()
if history is None:
    history = MessageHistory()

# 加载标签缓存
tag_cache = storage.load_all_tags()
if tag_cache is None:
    tag_cache = TagCache()

# 对话循环
tag_generator = TagGenerator()

def chat(user_input: str):
    global persona, history, tag_cache

    # 添加用户消息
    history.add_message(user_input, MessageRole.USER)

    # 构建Prompt
    prompt = build_full_conversation_prompt(
        persona=persona,
        history=history,
        current_message=user_input,
        config=config
    )

    # TODO: 调用LLM获取回复
    # assistant_response = llm.chat(prompt)

    # 模拟回复
    assistant_response = "哼，我知道了。"

    # 添加助手回复
    history.add_message(assistant_response, MessageRole.ASSISTANT)

    # 生成回复标签
    last_msg = history.current_queue.messages[-1]
    tag = tag_generator.generate_tag(last_msg.id, assistant_response)
    tag_cache.add(tag)

    # 保存
    storage.save_all_persona(persona)
    storage.save_all_history(history)
    storage.save_all_tags(tag_cache)

    return assistant_response, tag
```

---

## 多语言支持

代码和关键词检测支持中英文混合：

```python
# 情感检测（多语言）
tag = generator.generate_tag("msg_1", "哇，太棒了！哈哈哈！")
# emotion: happy

# 动作检测
tag = generator.generate_tag("msg_2", "好的，我明白了。")
# action: nod

# 记忆搜索
persona.add_memory("用户喜欢喝咖啡", memory_type="preference")
results = persona.search_memories("coffee")
```

---

## 版本

- **版本号**: 0.1.0
- **依赖**: Python 3.8+
- **字符编码**: UTF-8
