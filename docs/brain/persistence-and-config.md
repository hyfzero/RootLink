# Persistence And Config - 配置与文件存储

Brain 的配置和存储分成两部分：`config.py` 定义内存中的配置结构，`persistence.py` 负责 JSON/Markdown 文件读写。

## 职责边界

- Config 定义 Agent 的人格、历史、标签、存储默认参数。
- Persistence 负责单 Brain 数据的文件读写。
- 多 Brain 目录隔离由 Session 层处理。
- Provider 和模型配置不在这里，见 `agent_core.models`。

## 核心对象

配置：

- `HistoryConfig`
- `TagsConfig`
- `StorageConfig`
- `PersonaConfig`
- `AgentConfig`

存储：

- `FileStorage`
- `PersonaStorage`
- `HistoryStorage`
- `TagsStorage`
- `ConfigStorage`
- `AgentStorage`

## 数据流/存储

`AgentStorage("./data")` 默认创建：

```text
data/
  persona/
    profile.json
    memories.json
    state.json
  history/
    daily/
    queue.json
    weights.json
    index.json
  tags/
    reply_tags.json
    emotion_map.json
  config/
    agent_config.json
```

## 典型用法

```python
from agent_core.brain import AgentConfig, AgentStorage, Persona, PersonaProfile

config = AgentConfig(
    persona={"name": "小雪", "age": 18},
    history={"max_context_tokens": 4000},
    tags={"emotion_model": "keyword"},
    storage={"data_dir": "./data", "format": "json"},
)

persona = Persona(PersonaProfile(name="小雪"))
storage = AgentStorage("./data")
storage.save_all_persona(persona)
loaded = storage.load_all_persona()
```

## Runtime Personality State

`PersonaStorage` 现在会同时读写运行时人格状态：

```text
data/{brain_id}/persona/state.json
```

约定：

- `profile.json`：静态人格配置，面向 GUI 编辑。
- `memories.json`：长期记忆、偏好、事实和摘要记忆。
- `state.json`：运行时人格状态，如 `mood/energy/affinity/tension/current_focus/last_emotion`。

`save_full()` 会保存 profile、memories 和 state；`load_full()` 在缺少 `state.json` 时会使用默认 `PersonalityState`。

## 注意事项

- `AgentConfig.__post_init__()` 会把传入的 dict 转成对应 dataclass。
- `StorageConfig.format` 当前描述的是 `"json"` 或 `"md"`；SessionStorage 另有 `use_msgpack`。
- `FileStorage` 读写失败时返回 `None` 或 `False`，调用方应自行处理。
- 不要把 `state.json` 的字段加入 GUI 静态人格表单，除非明确做运行时调试面板。
