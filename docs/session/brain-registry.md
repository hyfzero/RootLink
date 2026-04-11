# Brain Registry - 多 Brain 实例管理

`brain_registry.py` 从目录加载多个 Brain，并提供切换、创建、删除和 UI 信息读取。

## 职责边界

- 负责发现和加载多个 Brain。
- 为每个 Brain 创建 `Persona`、`MessageHistory`、`SpeakingStyleEngine`、`PromptBuilder` 和 `AgentConfig`。
- 提供当前 Brain 引用。
- 不负责发送消息或生成摘要；这些由 `SessionManager` 调度。

## 核心对象

- `BrainComponents`
  - `persona`
  - `history`
  - `style_engine`
  - `prompt_builder`
  - `config`
- `BrainInfo`
  - `id`
  - `name`
  - `description`
  - `avatar`
- `BrainRegistry`
  - `load_all()`
  - `register()`
  - `switch()`
  - `current()`
  - `current_brain_id()`
  - `list_brains()`
  - `get_brain_info()`
  - `create_brain()`
  - `delete_brain()`

## 数据流/存储

默认 base path 是 `PathResolver.get_data_dir()`，单个 Brain 目录形态：

```text
data/{brain_id}/
  config.json
  persona/
    profile.json
    memories.json
  history/
    history.json
```

加载顺序：

```text
config.json
  -> profile.json + memories.json
  -> history/history.json
  -> SpeakingStyleEngine
  -> PromptBuilder
  -> BrainComponents
```

## 典型用法

```python
from agent_core.session import BrainRegistry

registry = BrainRegistry()
brain_ids = registry.load_all()

registry.switch(brain_ids[0])
components = registry.current()
print(components.persona.profile.name)

info = registry.get_brain_info(registry.current_brain_id())
```

## 注意事项

- `load_all()` 会跳过加载失败的 Brain。
- `current()` 在未加载或未注册任何 Brain 时会抛出 `RuntimeError`。
- `delete_brain()` 不允许删除当前选中的 Brain。
