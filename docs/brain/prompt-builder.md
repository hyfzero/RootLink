# Prompt Builder - 分段式 Prompt 构建

`prompt_builder.py` 将人格、风格、关系状态、运行时人格状态、记忆、历史摘要、队列消息和运行时信息组合成系统 Prompt 或上下文 Prompt。

## 职责边界

- 提供可复用的 Prompt 段落构建。
- 从 `Persona`、`MessageHistory`、`SpeakingStyleEngine` 读取上下文。
- 不调用 LLM，也不保存 Prompt。

## 核心对象

- `PromptBuilder`
  - `build_identity_section()`
  - `build_style_section()`
  - `build_relationship_section()`
  - `build_personality_state_section()`
  - `build_memory_section()`
  - `build_search_memory_section()`
  - `build_history_summary_section()`
  - `build_queue_section()`
  - `build_runtime_section()`
  - `build_system_prompt()`
  - `build_context_prompt()`
- 格式化工具：
  - `format_message_for_context()`
  - `format_messages_for_context()`
  - `format_summary_for_context()`
- 便捷函数：
  - `build_minimal_prompt()`
  - `build_full_conversation_prompt()`
  - `build_memory_flush_prompt()`

## 数据流/存储

默认系统 Prompt 顺序：

```text
身份定义
  -> 说话风格
  -> 关系状态
  -> 当前人格状态
  -> 近期记忆
  -> 历史摘要
  -> 当前队列消息
  -> 当前时间
```

## 典型用法

```python
from agent_core.brain import (
    MessageHistory,
    Persona,
    PersonaProfile,
    PromptBuilder,
    SpeakingStyleEngine,
)

persona = Persona(PersonaProfile(name="小雪", speaking_style="gentle"))
history = MessageHistory()
style = SpeakingStyleEngine(preset_name="gentle")

builder = PromptBuilder(persona, history=history, style_engine=style)
system_prompt = builder.build_system_prompt(emotion="thinking")
context_prompt = builder.build_context_prompt(query="用户偏好", include_queue=True)
```

## 注意事项

- `build_runtime_section()` 默认时区是 `Asia/Shanghai`。
- `build_context_prompt(query=...)` 会按关键词搜索相关记忆。
- Session 层还有 `SessionPromptBuilder`，它封装 Brain 的 `PromptBuilder` 并返回 API 消息列表。
- `当前人格状态` 段来自 `Persona.state`，放在记忆之前，帮助模型在读取长期记忆前先获得当前互动姿态。
