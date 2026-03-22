# Agent Core Brain 模块架构文档

## 概述

Brain 模块是 Agent 的"大脑"，负责管理角色人格、对话历史、记忆系统、配置和 Prompt 构建。灵感来源于 OpenClaw 的 session 管理和系统提示构建机制。

## 模块结构

```
brain/
├── __init__.py         # 统一导出入口
├── persona.py          # 角色人格和记忆管理
├── history.py          # 对话历史和 Token 感知管理
├── config.py           # Agent 配置管理
├── tags.py             # 回复表情/动作标签生成
├── persistence.py      # JSON/Markdown 文件持久化
└── prompt_builder.py   # 分段式 Prompt 构建
```

## 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      PromptBuilder                            │
│  build_system_prompt() / build_context_prompt()              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       Persona                                │
│  build_persona_text() / add_memory() / search_memories()   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    MessageHistory                            │
│  add_message() / get_context_messages() / finalize_day()    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      TagGenerator                            │
│  generate_tag() → ReplyTag (emotion/expression/action)     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     AgentConfig                              │
│  PersonaConfig / HistoryConfig / TagsConfig / StorageConfig │
└─────────────────────────────────────────────────────────────┘
```

## 核心模块详解

### 1. persona.py - 人格与记忆

```python
from agent_core.brain import Persona, PersonaProfile, MemoryEntry

# 创建角色配置
profile = PersonaProfile(
    name="红莉栖",
    age=18,
    gender="female",
    personality_traits=["天才", "傲娇", "温柔"],
    background="18岁的天才少女科学家",
    speaking_style="傲娇但内心温柔",
    interests=["物理学", "动漫", "咖啡"]
)

# 创建人格管理器
persona = Persona(profile)

# 添加记忆（三种类型）
persona.add_memory(
    content="用户喜欢在晚上使用程序",
    memory_type="preference",   # 偏好记忆
    importance=1.5
)

persona.add_memory(
    content="今天讨论了时间机器的原理",
    memory_type="episodic",     # 情景记忆
    importance=1.0
)

persona.add_memory(
    content="用户的名字是冈部",
    memory_type="fact",         # 事实记忆
    importance=2.0
)

# 获取最近记忆
recent = persona.get_recent_memories(limit=5)

# 搜索记忆
results = persona.search_memories("时间机器")

# 构建人格描述文本（用于 Prompt）
persona_text = persona.build_persona_text()
```

**记忆类型：**

| 类型 | 说明 | 用途 |
|------|------|------|
| `episodic` | 情景记忆 | 重要经历、事件 |
| `preference` | 偏好记忆 | 用户喜好、习惯 |
| `fact` | 事实记忆 | 已知事实、信息 |

---

### 2. history.py - 对话历史管理

```python
from agent_core.brain import MessageHistory, MessageRole, calculate_message_weight

# 创建历史管理器
history = MessageHistory(
    max_context_tokens=4000,    # 最大上下文 Token 数
    token_reserved=1000,        # 为系统提示保留的 Token
    retention_days=30           # 历史保留天数
)

# 添加消息
history.add_message("晚上好", MessageRole.USER)
history.add_message("哼，都几点了还来找我。", MessageRole.ASSISTANT)
history.add_message("我想讨论时间机器的问题。", MessageRole.USER, is_important=True)

# 获取在 Token 预算内的上下文消息
context = history.get_context_messages(max_tokens=2000)

# 检查是否应该触发队列插入
if history.should_trigger_queue_insert():
    pass  # 触发某些操作

# 结束当日并生成摘要
summary = history.finalize_day()

# 获取近3天的每日摘要
recent = history.get_recent_summaries(days=3)

# 清理过期数据
removed = history.cleanup_old_data()
```

**消息角色：**

| 角色 | 基础权重 | 说明 |
|------|----------|------|
| `USER` | 1.0 | 用户消息 |
| `ASSISTANT` | 0.8 | 助手回复 |
| `SYSTEM` | 0.3 | 系统消息 |
| `TOOL` | 0.5 | 工具调用/结果 |

**权重计算公式：**
```
weight = 角色基础权重 × 时间衰减因子 × 重要性倍数
```

---

### 3. config.py - 配置管理

```python
from agent_core.brain import AgentConfig, HistoryConfig, TagsConfig, StorageConfig

# 直接创建
config = AgentConfig(
    persona={"name": "红莉栖", "age": 18, "gender": "female"},
    history={"max_context_tokens": 5000, "retention_days": 7},
    tags={"auto_generate": True, "emotion_model": "keyword"},
    storage={"data_dir": "./data", "format": "json"}
)

# 从字典加载
loaded = AgentConfig.from_dict(config.to_dict())
```

**配置项说明：**

| 配置类 | 关键参数 | 默认值 |
|--------|----------|--------|
| `HistoryConfig` | `max_context_tokens` | 4000 |
| | `retention_days` | 30 |
| | `token_reserved` | 1000 |
| `TagsConfig` | `auto_generate` | True |
| | `emotion_model` | "keyword" |
| `StorageConfig` | `data_dir` | "./data" |
| | `format` | "json" |

---

### 4. tags.py - 回复标签生成

```python
from agent_core.brain import TagGenerator, TagCache, ReplyTag

# 创建标签生成器
generator = TagGenerator()

# 生成标签
tag = generator.generate_tag(
    message_id="msg_123",
    content="太开心了！这个问题终于解决了！"
)

print(f"Emotion: {tag.emotion}")      # happy
print(f"Expression: {tag.expression}") # smile
print(f"Action: {tag.action}")        # None
print(f"Overlays: {tag.overlays}")    # ["sparkle"]
print(f"Intensity: {tag.intensity}")  # 1.4

# 使用标签缓存
cache = TagCache(max_size=100)
cache.add(tag)

recent = cache.get_recent(limit=5)
```

**情感类型：** happy, sad, angry, surprised, thinking, scared, embarrassed, confused, neutral

**表情映射：**

| Emotion | Expression |
|---------|------------|
| happy | smile |
| sad | frown |
| angry | scowl |
| surprised | gasp |
| thinking | focused |
| scared | worried |
| embarrassed | blush |
| confused | puzzled |
| neutral | neutral |

---

### 5. prompt_builder.py - Prompt 构建

```python
from agent_core.brain import PromptBuilder, build_full_conversation_prompt

builder = PromptBuilder(persona, history, config)

# 构建完整系统 Prompt
system_prompt = builder.build_system_prompt()

# 各段落单独构建
identity = builder.build_identity_section()       # 身份定义
memory = builder.build_memory_section(limit=5)    # 近期记忆
summaries = builder.build_history_summary_section(days=3)  # 历史摘要
queue = builder.build_queue_section()            # 当前队列消息
runtime = builder.build_runtime_section()        # 运行时信息

# 构建上下文 Prompt（带搜索）
context_prompt = builder.build_context_prompt(
    query="时间机器",
    include_queue=True,
    max_queue_tokens=1000
)

# 便捷函数
prompt = build_full_conversation_prompt(persona, history, "你好", config)
minimal = build_minimal_prompt(persona, "今天天气如何？")
```

**Prompt 构建顺序：**

```
1. 身份定义 (Identity)
   └── 你叫红莉栖。年龄：18岁。性别：女性。性格特点：天才、傲娇、温柔...

2. 近期记忆 (Recent Memories)
   └── ## 近期记忆
       - [2026-03-20] 用户提到喜欢在晚上使用程序
       - [2026-03-19] 讨论了时间机器的原理

3. 历史摘要 (History Summaries)
   └── ## 近期对话
       ## 2026-03-20
       重要事件：...
       话题：技术、工作

4. 队列消息 (Queue Messages)
   └── ## 今日消息
       [user] 晚上好
       [assistant] 哼，都几点了...

5. 运行时信息 (Runtime Info)
   └── ## 当前时间
       日期：2026-03-22
       时间：21:30:00
       星期：星期日
```

---

### 6. persistence.py - 数据持久化

```python
from agent_core.brain import AgentStorage

# 创建存储管理器
storage = AgentStorage("./data")

# 保存所有数据
storage.save_all_persona(persona)
storage.save_all_history(history)
storage.save_all_tags(tag_cache)
storage.save_all_config(config)

# 加载所有数据
loaded_persona = storage.load_all_persona()
loaded_history = storage.load_all_history()
loaded_tags = storage.load_all_tags()
loaded_config = storage.load_all_config()
```

**存储结构：**

```
data/
├── persona/
│   ├── profile.json      # 角色基本配置
│   └── memories.json     # 记忆数据
├── history/
│   ├── daily/
│   │   ├── 2026-03-20.json
│   │   └── 2026-03-20.summary.md
│   └── queue.json        # 当前队列
├── tags/
│   └── reply_tags.json   # 标签缓存
└── config/
    └── agent_config.json # Agent 配置
```

---

## 统一导入方式

```python
# 推荐：从 brain 统一导入
from agent_core.brain import (
    Persona,
    PersonaProfile,
    MemoryEntry,
    MessageHistory,
    MessageRole,
    Message,
    AgentConfig,
    TagGenerator,
    TagCache,
    ReplyTag,
    PromptBuilder,
    AgentStorage,
    build_full_conversation_prompt,
    build_minimal_prompt,
)

# 或者：从具体模块导入
from agent_core.brain.persona import Persona, PersonaProfile
from agent_core.brain.history import MessageHistory, MessageRole
from agent_core.brain.config import AgentConfig
```

---

## 完整使用示例

```python
from agent_core.brain import (
    Persona, PersonaProfile, MessageHistory, MessageRole,
    AgentConfig, PromptBuilder, TagGenerator, AgentStorage
)

# 1. 创建人格
profile = PersonaProfile(
    name="红莉栖",
    age=18,
    gender="female",
    personality_traits=["天才", "傲娇"],
    speaking_style="傲娇但内心温柔"
)
persona = Persona(profile)
persona.add_memory("用户名叫冈部", "fact")
persona.add_memory("用户晚上比较有空", "preference")

# 2. 创建历史
history = MessageHistory(max_context_tokens=4000)
history.add_message("冈部，时间机器研究得如何了？", MessageRole.USER)
history.add_message("还在理论阶段...", MessageRole.ASSISTANT)

# 3. 创建配置
config = AgentConfig()

# 4. 构建 Prompt
builder = PromptBuilder(persona, history, config)
system_prompt = builder.build_system_prompt()

# 5. 生成回复标签
generator = TagGenerator()
response_text = "哼，虽然理论还有些问题，但前景不错。"
tag = generator.generate_tag("msg_3", response_text)

# 6. 持久化存储
storage = AgentStorage("./data")
storage.save_all_persona(persona)
storage.save_all_history(history)
```

---

## OpenClaw 参考

| 特性 | OpenClaw | Agent Core Brain |
|------|----------|------------------|
| 人格管理 | `persona.ts` | `persona.py` |
| 记忆系统 | `memory/*.md` | `persona.py` (episodic/preference/fact) |
| 历史管理 | `session.ts` | `history.py` |
| Token 感知 | `compact.ts` | `history.py` (get_context_messages) |
| 系统 Prompt | `system-prompt.ts` | `prompt_builder.py` |
| 标签生成 | `emote.ts` | `tags.py` |
| 数据持久化 | `*.jsonl`, `memory/*.md` | `persistence.py` |

---

## 文件对应

| OpenClaw | Agent Core Brain |
|-----------|------------------|
| `src/agents/persona.ts` | `brain/persona.py` |
| `src/agents/history.ts` | `brain/history.py` |
| `src/agents/config.ts` | `brain/config.py` |
| `src/agents/tags.ts` | `brain/tags.py` |
| `src/agents/storage.ts` | `brain/persistence.py` |
| `src/agents/system-prompt.ts` | `brain/prompt_builder.py` |
