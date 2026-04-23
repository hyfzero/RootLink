# Brain 模块 - 人格与记忆核心

`agent_core.brain` 是 Agent 的人格层。它保存角色资料、记忆、历史、回复标签、说话风格和 Prompt 构建能力。

## 职责边界

- 管理人格资料、记忆和历史上下文。
- 为 Session 或直接调用 API 的代码构建 Prompt。
- 为 UI 生成回复情绪/表情/动作标签。
- 提供基础 JSON/Markdown 持久化。
- 不负责 Provider 调用、跨日归档和多 Brain 生命周期调度。

## 核心对象

公共入口：`from agent_core.brain import ...`

- Persona：`PersonaProfile`、`PersonalityState`、`MemoryEntry`、`Persona`
- History：`MessageRole`、`Message`、`DailySummary`、`MessageQueue`、`DailyHistory`、`MessageHistory`
- Summary：`SummaryGenerator`、`AsyncSummaryGenerator`、`generate_summary_with_llm()`、`generate_daily_summaries_with_llm()`
- Tags：`ReplyTag`、`TagGenerator`、`TagCache`
- Style：`SpeakingStyle`、`StyleModifier`、`SpeakingStyleEngine`、`PRESET_STYLES`
- Prompt：`PromptBuilder`、`build_minimal_prompt()`、`build_full_conversation_prompt()`、`build_memory_flush_prompt()`
- Config/Storage：`AgentConfig`、`HistoryConfig`、`TagsConfig`、`StorageConfig`、`PersonaConfig`、`AgentStorage`

## 数据流/存储

Brain 的基础存储类默认使用：

```text
data/
  persona/
  history/
  tags/
  config/
```

在 Session 多 Brain 模式下，Brain 数据被放进：

```text
data/{brain_id}/
  persona/
    profile.json
    memories.json
    state.json
  history/
  tags/
```

`profile.json` 保存 GUI 可编辑的静态人格；`state.json` 保存运行时人格状态，包含当前心境、精力、亲近感、张力、关注点和上一轮情绪信号。

## 典型用法

```python
from agent_core.brain import (
    MessageHistory,
    MessageRole,
    Persona,
    PersonaProfile,
    PromptBuilder,
    SpeakingStyleEngine,
)

persona = Persona(PersonaProfile(name="小雪", speaking_style="gentle"))
persona.add_memory("用户喜欢晚上聊天", "preference", importance=1.5)

history = MessageHistory(max_context_tokens=4000)
history.add_message("你好", MessageRole.USER)

style = SpeakingStyleEngine(preset_name="gentle")
builder = PromptBuilder(persona=persona, history=history, style_engine=style)

system_prompt = builder.build_system_prompt(emotion="happy")
```

## 注意事项

- Brain 的 `Message` 类型用于历史上下文；API 层的 `Message` 类型用于 Provider 请求。
- `SummaryGenerator` 可以无 LLM callable 运行，此时使用规则后备。
- `AgentStorage` 是单 Brain 的基础存储工具；多 Brain 隔离由 Session 层的 `BrainRegistry` 和 `PathResolver` 管理。
- `PersonalityState` 是运行时状态，不应作为 GUI 静态配置项直接编辑。
