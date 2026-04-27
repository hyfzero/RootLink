# Prompt And Manager - 会话 Prompt 与主调度

`SessionPromptBuilder` 简化 Brain Prompt 构建；`SessionManager` 协调存储、Prompt、API、标签、摘要和 Brain 切换。

## 职责边界

- `SessionPromptBuilder` 只封装 Prompt 构建，不调用 API。
- `SessionManager` 负责完整发送流程和运行时缓存。
- API HTTP 请求仍由 `ChatAgent` 负责。
- GUI 应通过 Control 层调用 Session，不直接操作 Session 内部缓存。

## 核心对象

`SessionPromptBuilder`：

- `build_system_prompt()`
- `build_conversation_context()`
- `build_full_prompt()`
- `build_history_summary_for_context()`
- `build_persona_context()`
- `build_memory_context()`

`SessionManager`：

- 属性：`storage`、`summarizer`、`monthly_summarizer`、`prompt_builder`、`memory_updater`
- 情感模式：`get_emotion_mode()`、`set_emotion_mode()`、`is_llm_emotion_enabled()`
- 对话：`send_message()`、`send_message_sync()`
- Brain：`switch_brain()`、`create_brain()`、`list_brains()`
- 辅助：`get_conversation_history()`、`export_session()`、`add_message_to_history()`、`get_today_messages()`

## 数据流/存储

异步发送流程：

```text
send_message(user_message)
  -> _check_and_handle_day_change()
  -> restore today MessageHistory queue from history/session storage if needed
  -> storage.add_message("user", user_message)
  -> add_message_to_history("user", user_message)
  -> save history/history.json                      # 失败仅告警，不中断主流程
  -> update_personality_state("user", user_message) # 更新长期关系/中期氛围/tension/current_focus
  -> prompt_builder.build_system_prompt()
  -> prompt_builder.build_conversation_context()
  -> _call_api()
  -> ReplyTagger.generate_and_save()
  -> storage.add_message("assistant", response)
  -> add_message_to_history("assistant", response)
  -> save history/history.json                      # 失败仅告警，不中断主流程
  -> update_personality_state("assistant", response) # 更新 mood/energy/last_emotion
  -> return dict
```

Prompt 历史来源：

- `SessionStorage` 保存完整按日会话，供导出、摘要和兜底恢复使用。
- `MessageHistory.current_queue` 是 system prompt 中 `## 今日消息` 的直接来源。
- `history/history.json` 保存 `MessageHistory`，让同一天跨进程运行时能延续今日上下文。
- 如果 `history/history.json` 缺失且当前队列为空，`SessionManager` 会从当天 `SessionStorage` 重建队列；如果队列已存在，则不会重复重放 session 文件。

返回格式：

```python
{
    "content": str,
    "tag": ReplyTag,
    "message_id": str,
    "brain_id": str,
}
```

## 典型用法

```python
from agent_core.session import SessionManager

async def chat(manager: SessionManager):
    result = await manager.send_message("你好", emotion="happy")
    print(result["content"])

def chat_sync(manager: SessionManager):
    result = manager.send_message_sync("你好")
    print(result["tag"].emotion)
```

导出会话：

```python
markdown = manager.export_session("2026-04-11", format="markdown")
json_text = manager.export_session("2026-04-11", format="json")
```

## 注意事项

- `set_emotion_mode("llm")` 会配置 `TagGenerator` 使用 LLM callable。
- `switch_brain()` 会让 SessionStorage 切到新 `brain_id` 并清空相关延迟初始化缓存。
- `build_conversation_context()` 当前只注入“用户最新消息”，历史摘要和队列消息由 system prompt 统一承载，避免重复占用 token。
- `send_message()` 与 `send_message_sync()` 都会调用 `ReplyTagger.generate_and_save()`，确保 `reply_tags.json` 每轮稳定落盘。
- 消息写入和保存 `MessageHistory` 是“尽力而为”：异常只会告警，不会阻塞主聊天流程。
- `send_message()` 与 `send_message_sync()` 都会同步更新 `Persona.state` 并写入 `persona/state.json`；失败只告警，不阻塞聊天流程。
- `Persona.state` 的自然回落主要作用于 `recent_*`、`tension/energy/mood`，不会快速降低长期关系维度。
- 高亲和、低张力场景下，即使没有强信号，`mood` 也会维持轻微 `warm`，目标是“可控亲密关系”，不是长期不温不火。

## 配置化策略

- 记忆注入策略：`AgentConfig.memory_injection`（按类型配额、权重、时间衰减、重要度阈值、去重、sticky context、query boost）。
- Prompt 分段预算：`AgentConfig.prompt_budget`（`section_tokens` + `total_tokens`）。
- 关系状态机：`AgentConfig.relationship_state_machine`（信号词/权重/衰减/状态区间/prompt_hint）。
- 默认行为兼容：关闭预算时，PromptBuilder 保持原有拼接；开启预算时按 `identity -> style -> relationship -> personality_state -> memory -> history_summary -> queue -> runtime` 顺序裁剪。
- 运行时人格状态不是配置项，固定规则更新，避免给 GUI 增加额外配置复杂度。
