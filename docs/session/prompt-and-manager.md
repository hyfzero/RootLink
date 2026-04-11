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
  -> storage.add_message("user", user_message)
  -> add_message_to_history("user", user_message)   # 失败仅告警，不中断主流程
  -> prompt_builder.build_system_prompt()
  -> prompt_builder.build_conversation_context()
  -> _call_api()
  -> ReplyTagger.generate_and_save()
  -> storage.add_message("assistant", response)
  -> add_message_to_history("assistant", response)  # 失败仅告警，不中断主流程
  -> return dict
```

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
- 消息写入 `MessageHistory` 是“尽力而为”：异常只会告警，不会阻塞主聊天流程。

## 配置化策略

- 记忆注入策略：`AgentConfig.memory_injection`（按类型配额、权重、时间衰减、重要度阈值、去重、sticky context、query boost）。
- Prompt 分段预算：`AgentConfig.prompt_budget`（`section_tokens` + `total_tokens`）。
- 关系状态机：`AgentConfig.relationship_state_machine`（信号词/权重/衰减/状态区间/prompt_hint）。
- 默认行为兼容：关闭预算时，PromptBuilder 保持原有拼接；开启预算时按 `identity -> style -> relationship -> memory -> history_summary -> queue -> runtime` 顺序裁剪。
