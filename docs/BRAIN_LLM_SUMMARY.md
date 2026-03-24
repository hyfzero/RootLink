# LLM驱动的记忆总结 (LLM-Driven Memory Summarization)

## 概述

传统的规则驱动摘要使用关键词匹配和启发式评分，难以捕捉对话中的细微语义和情感变化。LLM驱动的记忆总结利用大语言模型的理解能力，生成更准确、更丰富的每日对话摘要。

## 核心组件

### SummaryGenerator

LLM驱动的摘要生成器。

```python
from brain.history import SummaryGenerator, MessageHistory, Message, MessageRole
```

#### 初始化

```python
# 方式1：传入LLM调用函数
def my_llm_callable(prompt: str) -> str:
    # 调用你的LLM API
    response = llm_api.complete(prompt)
    return response

generator = SummaryGenerator(llm_callable=my_llm_callable)

# 方式2：不传LLM调用器（使用规则后备）
generator = SummaryGenerator()  # 退化为规则方法

# 方式3：禁用后备，LLM失败时直接抛出异常
generator = SummaryGenerator(llm_callable=my_llm_callable, use_fallback=False)
```

#### 生成摘要

```python
# 为一组消息生成摘要
messages = [
    Message(id="1", role=MessageRole.USER, content="今天工作很累", timestamp=time.time()),
    Message(id="2", role=MessageRole.ASSISTANT, content="辛苦啦，要注意休息哦", timestamp=time.time()),
]

summary = generator.generate_summary("2026-03-24", messages)
print(summary.summary_text)
print(summary.topics)
print(summary.emotional_tone)  # LLM新增字段
```

### DailySummary 新增字段

原有的 `DailySummary` dataclass 新增了以下LLM驱动的字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `emotional_tone` | str? | 情感基调：`积极`/`中性`/`消极`/`混合` |
| `user_preferences` | list[str] | 用户表达的任何偏好或决定 |
| `unfinished_topics` | list[str] | 未完成或需要后续跟进的话题 |

### AsyncSummaryGenerator

异步版本的摘要生成器，适用于异步应用：

```python
import asyncio
from brain.history import AsyncSummaryGenerator

async def async_llm_callable(prompt: str) -> str:
    response = await llm_api.acomplete(prompt)
    return response

async_generator = AsyncSummaryGenerator(llm_callable=async_llm_callable)

async def main():
    summary = await async_generator.generate_summary("2026-03-24", messages)
    print(summary.summary_text)

asyncio.run(main())
```

## 与 MessageHistory 集成

### 便捷函数

```python
from brain.history import (
    MessageHistory,
    generate_summary_with_llm,
    generate_daily_summaries_with_llm,
)

# 为历史中的所有日期生成LLM摘要
def my_llm(prompt: str) -> str:
    return llm_api.complete(prompt)

history = MessageHistory()

# ... 添加消息 ...

# 方式1：批量生成
summaries = generate_daily_summaries_with_llm(history, llm_callable=my_llm)

# 方式2：单日生成
daily = history.daily_histories["2026-03-24"]
summary = generate_summary_with_llm(daily, llm_callable=my_llm)
```

### 直接使用生成器

```python
from brain.history import MessageHistory, SummaryGenerator

def my_llm(prompt: str) -> str:
    return llm_api.complete(prompt)

history = MessageHistory()
generator = SummaryGenerator(llm_callable=my_llm)

# 在 finalize_day 时使用
summary = generator.generate_summary(
    history.today_str,
    history.current_queue.messages
)
history.daily_summaries[history.today_str] = summary
```

## LLM Prompt 模板

默认使用的Prompt模板如下（可通过自定义 `SummaryGenerator` 覆盖）：

```
你是一个对话摘要助手。请分析以下日期为 {date} 的对话，生成简洁但信息丰富的摘要。

对话内容：
[{角色}] {消息内容}
...

请按以下JSON格式输出摘要（只输出JSON，不要有其他内容）：
{
    "summary_text": "2-3句话的对话摘要，重点是重要事件、决定和用户偏好",
    "important_messages": ["最重要的1-2条消息ID或简短描述"],
    "topics": ["讨论的主要话题"],
    "emotional_tone": "整体情感基调（积极/中性/消极/混合）",
    "user_preferences": ["用户表达的任何偏好或决定"],
    "unfinished_topics": ["未完成或需要后续跟进的话题"]
}
```

## 使用示例

### 完整示例

```python
import time
from brain import (
    Persona,
    PersonaProfile,
    MessageHistory,
    Message,
    MessageRole,
    SummaryGenerator,
    SpeakingStyleEngine,
)

# 初始化
persona = Persona(PersonaProfile(name="小雪", speaking_style="gentle"))
history = MessageHistory()
style_engine = SpeakingStyleEngine(preset_name="gentle")

# LLM调用函数
def llm_complete(prompt: str) -> str:
    # 这里应该是实际的API调用
    # return openai.ChatCompletion.create(prompt=prompt)
    return '{"summary_text": "示例摘要", "important_messages": [], "topics": [], "emotional_tone": "中性", "user_preferences": [], "unfinished_topics": []}'

generator = SummaryGenerator(llm_callable=llm_complete)

# 模拟对话
history.add_message(Message(
    id="1",
    role=MessageRole.USER,
    content="我今天想买个新手机，预算大概5000左右",
    timestamp=time.time(),
))

history.add_message(Message(
    id="2",
    role=MessageRole.ASSISTANT,
    content="好的，5000元预算的话，可以考虑小米、OPPO或者vivo的新款。要我帮你推荐几款吗？",
    timestamp=time.time(),
))

# 生成当日摘要
summary = generator.generate_summary(history.today_str, history.current_queue.messages)
print(f"日期: {summary.date}")
print(f"摘要: {summary.summary_text}")
print(f"话题: {summary.topics}")
print(f"情感基调: {summary.emotional_tone}")
print(f"用户偏好: {summary.user_preferences}")
print(f"未完成话题: {summary.unfinished_topics}")
```

### 兼容旧代码

原有的 `DailyHistory.generate_summary()` 方法保持不变，使用规则驱动：

```python
from brain import MessageHistory, DailyHistory

history = MessageHistory()

# ... 添加消息 ...

# 旧方式（规则驱动）
daily = history.daily_histories[history.today_str]
summary = daily.generate_summary()  # 仍然是规则方法
```

新代码可以直接传入LLM调用器：

```python
from brain.history import DailyHistory, SummaryGenerator

def my_llm(prompt: str) -> str:
    return llm.complete(prompt)

daily = DailyHistory("2026-03-24")
# ... 添加消息 ...

# 新方式（LLM驱动）
generator = SummaryGenerator(llm_callable=my_llm)
summary = generator.generate_summary(daily.date, daily.messages)
```

## 错误处理

```python
from brain.history import SummaryGenerator

generator = SummaryGenerator(llm_callable=my_llm, use_fallback=True)

try:
    summary = generator.generate_summary(date, messages)
except RuntimeError as e:
    # LLM调用或解析失败，且use_fallback=False
    print(f"生成失败: {e}")
```

当 `use_fallback=True`（默认）时，任何LLM错误都会触发规则后备方法，确保系统始终能生成摘要。

## 性能考虑

- LLM调用有网络延迟，批量生成时建议使用 `AsyncSummaryGenerator`
- 消息过多时，可以先进行预过滤或截断
- 可以设置 `max_tokens` 参数限制输出长度

## 序列化

新字段自动支持序列化：

```python
# DailySummary 序列化
data = summary.to_dict()
restored = DailySummary.from_dict(data)

# 验证新字段
print(restored.emotional_tone)  # "中性"
print(restored.user_preferences)  # ["预算5000", "想买手机"]
```
