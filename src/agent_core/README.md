# Agent 核心层 - 技术文档

Python实现的Agent核心系统，提供人格、记忆、历史消息和标签管理功能。

## 目录

1. [架构概览](#架构概览)
2. [人格系统](#人格系统)
3. [记忆系统](#记忆系统)
4. [历史消息机制](#历史消息机制)
5. [标签系统](#标签系统)
6. [存储系统](#存储系统)
7. [使用示例](#使用示例)

---

## 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                        Agent                                 │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐   │
│  │   Persona   │ │   Memory    │ │    HistoryManager   │   │
│  │   Manager   │ │   Manager   │ │                     │   │
│  └─────────────┘ └─────────────┘ └─────────────────────┘   │
│  ┌─────────────┐ ┌─────────────────────────────────────┐   │
│  │    Tag      │ │            Storage                  │   │
│  │   Manager   │ │    (JSON持久化 + 自动备份)          │   │
│  └─────────────┘ └─────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 人格系统

### 数据结构

```python
@dataclass
class Persona:
    name: str              # 名字
    age: int               # 年龄
    gender: str            # 性别
    personality: str      # 性格描述
    background: str       # 背景故事
    interests: list[str]  # 兴趣列表
    speaking_style: str   # 说话风格
    life_events: list[LifeEvent]  # 人生事件
    custom_data: dict     # 自定义数据

@dataclass
class LifeEvent:
    year: int       # 年份
    description: str # 事件描述
    importance: int  # 重要性 1-10
```

### Prompt生成

人格系统可以将角色信息转换为Prompt上下文：

```python
persona = Persona(
    name="小美",
    age=18,
    gender="女",
    personality="活泼开朗",
    background="大学生",
    interests=["音乐", "编程"],
    speaking_style="温柔可爱~"
)

prompt = persona.get_prompt_context()
# 输出:
# 名字: 小美
# 年龄: 18岁
# 性别: 女
# 性格: 活泼开朗
# ...
```

### PersonaManager

```python
manager = PersonaManager(storage_path)

# 创建人格
persona = manager.create_persona(
    name="小美",
    age=18,
    gender="女",
    personality="活泼开朗",
)

# 添加人生事件
manager.add_life_event(2020, "考入大学", importance=8)

# 保存/加载
manager.save_persona("agent_001")
manager.load_persona("agent_001")
```

---

## 记忆系统

### 消息权重

权重等级用于区分消息的重要程度：

| 等级 | 枚举值 | 说明 |
|------|--------|------|
| TRIVIAL | 1 | 无关紧要 |
| LOW | 2 | 低权重 |
| NORMAL | 3 | 普通 |
| IMPORTANT | 5 | 重要 |
| CRITICAL | 8 | 关键 |
| MEMORABLE | 10 | 值得铭记 |

### 长期记忆 vs 短期记忆

```python
manager = MemoryManager()

# 长期记忆 - 跨会话持久保存
manager.add_long_term_memory(
    content="用户喜欢讨论AI话题",
    weight=MessageWeight.IMPORTANT,
    tags=["AI", "偏好"]
)

# 搜索记忆
results = manager.search_memories("AI")

# 获取重要记忆
important = manager.get_important_memories(MessageWeight.IMPORTANT)

# 会话记忆 - 短期
manager.create_conversation("session_001")
manager.add_to_conversation(
    "session_001",
    "用户: 你好",
    weight=MessageWeight.NORMAL
)
```

---

## 历史消息机制

### 设计目标

1. **每日梗概** - 每天自动生成模糊梗概，保存最重要的消息
2. **消息权重** - 给每条消息分配权重，高权重消息更易被选中
3. **队列管理** - 当天消息存入队列，通过机制决定哪些加入Prompt

### 每日梗概生成

```python
manager = HistoryManager()

# 添加消息
manager.add_message(
    sender="用户A",
    content="今天天气真好！",
    weight=MessageWeight.NORMAL
)
manager.add_message(
    sender="用户B",
    content="帮我解释深度学习",
    weight=MessageWeight.IMPORTANT,
    tags=["技术"]
)

# 生成当日梗概
summary = manager.generate_daily_summary()
# DailySummary:
#   date: "2026-03-19"
#   summary: "今天有3条消息，讨论了技术。"
#   important_events: ["[用户B]: 帮我解释深..."]
#   message_count: 3
#   participants: ["用户A", "用户B"]
#   topics: ["技术"]
```

### 消息队列策略

`MessageQueue` 决定哪些消息加入Prompt：

```python
# 获取要加入Prompt的消息
# 策略：高权重优先，但也保留上下文
messages = queue.get_messages_for_prompt(
    max_messages=20,
    min_weight=MessageWeight.TRIVIAL
)
```

**策略说明：**
1. 高权重(IMPORTANT及以上)消息优先入选
2. 如果高权重消息足够，直接返回
3. 否则补充部分普通消息作为上下文
4. 最终按时间排序返回

### Prompt上下文生成

```python
context = manager.get_prompt_context(
    max_messages=20,
    include_days=7
)
# 输出格式:
# ## 最近几天的对话概要
# ### 2026-03-19
# 今天有3条消息，讨论了技术。
# 重要事件:
#   - [用户B]: 帮我解释深...
#
# ## 今天的对话
# [21:34] 用户A: 今天天气真好！
# [21:35] 用户B: 帮我解释深度学习 ★★
```

---

## 标签系统

### 标签类型

```python
class ReplyTagType(Enum):
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
```

### 自动标签分析

基于关键词匹配自动生成标签：

```python
manager = TagManager()

# 分析内容
tags = manager.analyze_content_for_tags("你好呀！今天真开心！")
# -> [ReplyTagType.HAPPY, ReplyTagType.GREETING]

tags = manager.analyze_content_for_tags("为什么天空是蓝色的？")
# -> [ReplyTagType.QUESTION]
```

**关键词映射：**
- 开心/高兴/快乐 → HAPPY
- 难过/伤心/悲伤 → SAD
- 生气/愤怒 → ANGRY
- 惊讶/意外 → SURPRISED
- 问句(?/？/什么/为什么/怎么) → QUESTION
- 你好/早上好/嗨 → GREETING
- 再见/拜拜 → GOODBYE

### 标签显示信息

用于UI立绘显示：

```python
from agent_core.tags import get_tag_for_display

display = get_tag_for_display(tag)
# {
#     "type": "happy",
#     "display_name": "Happy",
#     "confidence": 0.7,
#     "intensity": 0.5,
#     "icon": ":)",
#     "color": "#4CAF50"
# }
```

---

## 存储系统

### JSON持久化

```python
storage = Storage(Path("./data"))

# 保存
storage.save_agent_data("agent_001", {"key": "value"})

# 加载
data = storage.load_agent_data("agent_001")

# 列表
agents = storage.list_agents()

# 删除
storage.delete_agent("agent_001")
```

### 自动备份

每次保存自动创建备份，保留最近5个：

```
data/
├── backups/
│   ├── agent_001_20260319_143022.json
│   ├── agent_001_20260319_143055.json
│   └── agent_001_20260319_143128.json
├── agent_001.json
└── config.json
```

### Agent存储

整合所有子系统的统一存储：

```python
agent = Agent("agent_001", storage_path)

# ... 修改数据 ...

agent.save()  # 保存所有数据

# 加载
loaded = Agent.load_from_storage("agent_001", storage_path)
```

---

## 使用示例

### 完整示例

```python
from pathlib import Path
from agent_core import (
    Agent,
    create_agent,
    MessageWeight,
)

# 1. 创建Agent
agent = create_agent(
    agent_id="assistant_001",
    name="小美",
    age=18,
    gender="女",
    personality="活泼开朗，喜欢帮助人",
    background="大学生，热爱学习",
    interests=["动漫", "音乐", "编程"],
    speaking_style="语气温柔，偶尔用~结尾",
    storage_path=Path("./data"),
)

# 2. 添加消息历史
agent.add_message(
    sender="用户",
    content="今天天气真好！",
    weight=MessageWeight.NORMAL
)
agent.add_message(
    sender="用户",
    content="能告诉我什么是机器学习吗？",
    weight=MessageWeight.IMPORTANT,
    tags=["技术"]
)

# 3. 添加回复（自动标签）
reply = agent.add_reply(
    message_id="msg_001",
    content="机器学习是人工智能的一个分支..."
)

# 4. 获取标签用于立绘
tags = agent.get_reply_tags("msg_001")
# [{'type': 'neutral', 'display_name': 'Neutral', ...}]

# 5. 生成完整Prompt
prompt = agent.generate_prompt(
    max_history_messages=20,
    include_days=7
)

# 6. 保存
agent.save()

# 7. 查看状态
status = agent.get_status()
# {
#     'agent_id': 'assistant_001',
#     'persona': '小美',
#     'long_term_memories_count': 0,
#     'today_messages_count': 2,
#     'tagged_replies_count': 1,
#     'daily_summaries_count': 0
# }
```

### 跨设备使用

将存储目录放在云同步目录（如OneDrive、Dropbox）：

```python
# 设备A
agent = create_agent(
    agent_id="me",
    name="小美",
    storage_path=Path("C:/Users/Me/OneDrive/agent_data")
)
agent.save()

# 设备B (同一存储路径)
agent = Agent.load_from_storage("me", Path("C:/Users/Me/OneDrive/agent_data"))
```

---

## API参考

### Agent

| 方法 | 说明 |
|------|------|
| `create_persona()` | 创建人格 |
| `get_persona()` | 获取当前人格 |
| `get_persona_prompt()` | 获取人格Prompt |
| `add_message()` | 添加消息 |
| `add_reply()` | 添加回复（带标签） |
| `get_reply_tags()` | 获取回复标签 |
| `generate_prompt()` | 生成完整Prompt |
| `save()` | 保存所有数据 |
| `load()` | 加载所有数据 |
| `get_status()` | 获取状态 |

### MessageWeight

| 值 | 说明 |
|----|------|
| `TRIVIAL(1)` | 无关紧要 |
| `LOW(2)` | 低权重 |
| `NORMAL(3)` | 普通 |
| `IMPORTANT(5)` | 重要 |
| `CRITICAL(8)` | 关键 |
| `MEMORABLE(10)` | 值得铭记 |

### ReplyTagType

见 [标签系统](#标签系统) 部分。
