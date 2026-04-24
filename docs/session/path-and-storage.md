# Path And Storage - 路径解析与会话存储

`path_resolver.py` 统一数据目录解析，`storage.py` 按日期保存当前会话和归档会话。

## 职责边界

- `PathResolver` 负责跨平台路径，不保存业务对象。
- `SessionStorage` 保存当前日会话、归档旧会话、按日期读取会话。
- `DaySession` 是可序列化的单日会话数据。
- 不负责生成摘要、更新 Persona 记忆，也不是 prompt 历史的直接注入层。

## 核心对象

`PathResolver`：

- `ENV_DATA_DIR = "AGENT_DATA_DIR"`
- `ENV_CONFIG_DIR = "AGENT_CONFIG_DIR"`
- `get_project_root()`
- `get_data_dir()`
- `get_config_dir()`
- `get_brain_dir(brain_id)` -> `data/{brain_id}`
- `get_session_dir(brain_id)` -> `data/{brain_id}/session`
- `get_tags_dir(brain_id)` -> `data/{brain_id}/tags`
- `resolve(relative_path)`
- `ensure_dir(path)`

`SessionConfig`：

- `max_messages_per_day`
- `max_tokens_per_day`
- `archive_retention_days`
- `min_messages_for_summary`
- `model_config`
- `data_dir`
- `brain_dir`
- `use_msgpack`
- `compact_keep_min`
- `compact_keep_max`
- `calculate_keep_count()`

`DaySession`：

- `add_message()`
- `needs_compact()`
- `compact()`
- `get_messages()`
- `to_dict()`、`from_dict()`

`SessionStorage`：

- `get_or_create_today()`
- `add_message()`
- `get_today_messages()`
- `archive_if_new_day()`
- `archive_session()`
- `cleanup_old_archives()`
- `get_recent_sessions()`
- `get_session_by_date()`
- `switch_brain()`

## 数据流/存储

```text
SessionStorage(brain_id="default")
  -> data/default/session/current/YYYY-MM-DD.json
  -> data/default/session/archive/YYYY-MM/YYYY-MM-DD.json
```

`session/current/YYYY-MM-DD.json` 是完整按日会话记录。Prompt 中的 `## 今日消息` 直接来自 `MessageHistory.current_queue`，该队列由 `SessionManager` 保存到 `history/history.json`；当 `history/history.json` 缺失且队列为空时，`SessionManager` 会用当天 session 文件恢复上下文。

当消息数或估算 token 超过配置上限时，`SessionStorage.add_message()` 会调用 `DaySession.compact()`，保留条数由 `SessionConfig.calculate_keep_count()` 决定。

## 典型用法

```python
from agent_core.session import PathResolver, SessionConfig, SessionStorage

print(PathResolver.get_brain_dir("kurisu"))
print(PathResolver.get_session_dir("kurisu"))

storage = SessionStorage(SessionConfig(), brain_id="kurisu")
storage.add_message("user", "你好")
messages = storage.get_today_messages()
```

## 注意事项

- `DaySession.messages` 内部保存 dict，`get_messages()` 才转换成 Brain 的 `Message`。
- `SessionStorage` 的 token 估算策略与当前 Brain 的 `history.token_estimator` 对齐，`compact` 判定会随之变化。
- `use_msgpack=True` 会使用 `.msgpack` 扩展名。
- 数据路径优先级为 `AGENT_DATA_DIR`、`FLET_APP_STORAGE_DATA`、Windows AppData、项目默认 `data`；配置路径优先级为 `AGENT_CONFIG_DIR`、`FLET_APP_STORAGE_DATA/config`、Windows AppData/`amadues/config`、项目默认 `config`。

## Token Strategy Alignment

`SessionStorage` now aligns with runtime model tokenizer strategy:

- Uses the same resolver chain as `MessageHistory`/`PromptBuilder`.
- Supports runtime `tokenizer_mode` + `tokenizer_fallback` from `ModelConfig`.
- `DaySession` persists `tokenizer_mode/model_provider/model_name` for observability.

This keeps `add_message` token counting and compact thresholds consistent with prompt budgeting.
