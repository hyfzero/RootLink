# Agent Core Session 模块详细文档

## 模块概览

Session 模块位于 `src/agent_core/session/`，负责 Prompt 生成与 Brain 反向更新。协调 Prompt 构建、API 调用、回复标签生成、日终摘要等核心功能。

---

## 1. path_resolver.py - 三端路径兼容解析器

提供跨平台（Windows/Linux/Mac）的路径解析支持。

### 1.1 环境变量

| 常量 | 说明 |
|------|------|
| `ENV_DATA_DIR` | `"AGENT_DATA_DIR"` - 数据目录环境变量 |
| `ENV_CONFIG_DIR` | `"AGENT_CONFIG_DIR"` - 配置目录环境变量 |

### 1.2 默认相对路径

| 常量 | 说明 |
|------|------|
| `DEFAULT_DATA_RELATIVE` | `"data"` - 相对于项目根目录 |
| `DEFAULT_CONFIG_RELATIVE` | `"config"` - 相对于项目根目录 |

### 1.3 PathResolver

三端路径解析器。优先使用环境变量，支持相对路径解析。

```python
def __init__(base_path: Optional[Path] = None)
```
初始化路径解析器。base_path 为项目根目录，不指定时自动查找。

```python
@classmethod
def _find_project_root(cls) -> Path
```
自动查找项目根目录。向上查找 `pyproject.toml`、`project.godot`、`setup.py`、`.git` 文件。

```python
@classmethod
def get_project_root(cls) -> Path
```
获取项目根目录。

```python
@classmethod
def get_data_dir(cls) -> Path
```
获取数据目录。优先级：`环境变量` > `项目根/data` > `./data`

```python
@classmethod
def get_config_dir(cls) -> Path
```
获取配置目录。优先级：`环境变量` > `项目根/config` > `./config`

```python
@classmethod
def get_brain_dir(cls, brain_id: str = "default") -> Path
```
获取 Brain 模块数据目录。格式：`{data_dir}/brain/{brain_id}/`

```python
@classmethod
def get_session_dir(cls, brain_id: str = "default") -> Path
```
获取 Session 数据目录。格式：`{data_dir}/session/{brain_id}/`

```python
@classmethod
def get_tags_dir(cls) -> Path
```
获取标签目录。格式：`{data_dir}/tags/`

```python
@classmethod
def resolve(cls, relative_path: str) -> Path
```
解析相对路径到绝对路径。

```python
@classmethod
def ensure_dir(cls, path: Path) -> Path
```
确保目录存在，不存在则创建。返回目录路径。

---

## 2. config.py - 配置管理

提供 SessionManager 的配置定义。

### 2.1 SessionConfig

Session Manager 配置数据类。

**字段**：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| max_messages_per_day | int | 500 | 单日最大消息数 |
| max_tokens_per_day | int | 50000 | 单日最大 Token（近似） |
| archive_retention_days | int | 30 | 归档保留天数 |
| min_messages_for_summary | int | 4 | 触发摘要的最少消息数 |
| model_config | Optional[ModelConfig] | None | 模型配置 |
| data_dir | Optional[str] | None | 数据目录（留空使用默认） |
| brain_dir | Optional[str] | None | Brain 目录（留空使用默认） |
| use_msgpack | bool | False | 大数据量时启用 MessagePack 格式 |
| compact_keep_min | int | 50 | Compact 最少保留消息数 |
| compact_keep_max | int | 100 | Compact 最多保留消息数 |

**方法**：

```python
def get_effective_data_dir(self) -> Path
```
获取有效的数据目录。优先使用 data_dir，否则使用 PathResolver。

```python
def get_effective_brain_dir(self, brain_id: str = "default") -> Path
```
获取有效的 Brain 目录。

```python
def calculate_keep_count(self, avg_token_per_message: int) -> int
```
动态计算保留条数，确保不超出 Token 上限。

**计算公式**：
```
min_token = max(avg_token_per_message, 50)
max_messages = max_tokens_per_day // min_token
return max(compact_keep_min, min(compact_keep_max, max_messages))
```

```python
def to_dict(self) -> dict
def @classmethod from_dict(cls, data: dict) -> "SessionConfig"
```

---

## 3. storage.py - 会话存储管理

以日期为单位存储聊天记录，支持 Token 限制和自动清理。参考 OpenClaw 的 Token 感知机制。

### 3.1 DaySession

单日会话数据类。

**字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| date | str | 日期 YYYY-MM-DD |
| messages | list[dict] | 消息列表（使用字典便于序列化） |
| message_count | int | 消息总数 |
| total_tokens_estimate | int | 总 Token 估计数 |
| summary_generated | bool | 是否已生成摘要 |

**方法**：

```python
def add_message(role: str, content: str) -> None
```
添加消息，带 Token 估算。自动生成消息 ID 格式：`msg_{count}_{timestamp}`。

```python
def needs_compact(self, max_messages: int, max_tokens: int) -> bool
```
检查是否需要压缩。条件：`message_count > max_messages` 或 `total_tokens_estimate > max_tokens`。

```python
def compact(self, keep_last_n: int) -> None
```
压缩保留最近 N 条消息，并重新计算 token 总数。

```python
def get_messages(self) -> list[Message]
```
获取消息列表（转换为 Message 对象）。

```python
def to_dict() -> dict
def @classmethod from_dict(cls, data: dict) -> "DaySession"
```

---

### 3.2 SessionStorage

会话存储管理器。

```python
def __init__(
    config: SessionConfig,
    resolver: Optional[PathResolver] = None,
    brain_id: str = "default",
    use_msgpack: bool = False
)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| config | SessionConfig | Session 配置 |
| resolver | PathResolver | 路径解析器，不指定则创建默认 |
| brain_id | str | Brain ID，用于多 Brain 支持 |
| use_msgpack | bool | 是否使用 MessagePack 格式 |

**存储目录结构**：
```
session/{brain_id}/
├── current/
│   └── YYYY-MM-DD.json
└── archive/
    └── YYYY-MM/
        └── YYYY-MM-DD.json
```

**方法**：

```python
def get_or_create_today(self) -> DaySession
```
获取或创建当日 Session。优先从磁盘加载当日的现有 Session。

```python
def add_message(self, role: str, content: str) -> DaySession
```
添加消息到当日 Session。自动检查是否需要 compact，超限时动态计算保留条数。

```python
def get_today_messages(self) -> list[Message]
```
获取当日所有消息。

```python
def _save_session(self, session: DaySession) -> None
```
保存 Session 到磁盘。

```python
def archive_if_new_day(self) -> Optional[DaySession]
```
检查日期是否切换，若是则归档旧 Session。返回被归档的旧 Session（如果有）。

```python
def archive_session(self, session: DaySession) -> None
```
归档 Session 到 `archive/{year-month}/`，并删除 current 中的文件。

```python
def cleanup_old_archives(self) -> int
```
清理超过保留期的归档。返回删除数量。

```python
def get_recent_sessions(self, days: int = 7) -> list[DaySession]
```
获取最近 N 天的 Session。优先从 current 加载，不存在则从 archive 加载。

```python
def get_session_by_date(self, date: str) -> Optional[DaySession]
```
按日期获取 Session。先检查 current，再检查 archive。

```python
def switch_brain(self, brain_id: str) -> None
```
切换 Brain ID。重置缓存并重新创建目录结构。

---

## 4. brain_registry.py - 多 Brain 实例管理

支持多个 Brain 配置（如不同人格）动态切换。

### 4.1 BrainComponents

Brain 模块组件集合数据类。

```python
@dataclass
class BrainComponents:
    persona: Persona
    history: MessageHistory
    style_engine: SpeakingStyleEngine
    prompt_builder: PromptBuilder
    config: AgentConfig
```

### 4.2 BrainInfo

Brain 信息（供 UI 显示）数据类。

```python
@dataclass
class BrainInfo:
    id: str
    name: str
    description: str = ""
    avatar: Optional[str] = None
```

### 4.3 BrainRegistry

多 Brain 实例注册表（从目录加载）。

**目录结构**：
```
{base_path}/
├── default/
│   ├── persona/
│   │   ├── profile.json
│   │   └── memories.json
│   ├── history/
│   └── config.json
└── {brain_id}/
    └── ...
```

```python
def __init__(base_path: Optional[Path] = None)
```
初始化注册表。base_path 默认为 `{数据目录}/brain`。

```python
def load_all(self) -> list[str]
```
扫描目录加载所有 Brain，返回 ID 列表。跳过加载失败的 Brain。

```python
def _load_brain_components(self, brain_dir: Path) -> BrainComponents
```
从目录加载单个 Brain 的组件。

**加载流程**：
1. 加载或创建 AgentConfig
2. 加载 Persona（profile.json + memories.json）
3. 加载或创建 MessageHistory
4. 创建 SpeakingStyleEngine
5. 创建 PromptBuilder

```python
def _load_config(self, brain_dir: Path) -> AgentConfig
```
加载 Brain 配置。从 `brain_dir/config.json` 读取，不存在则返回默认 AgentConfig()。

```python
def _load_persona(self, persona_dir: Path, config: AgentConfig) -> Persona
```
加载 Persona。从 profile.json 和 memories.json 读取。

```python
def _load_history(self, history_dir: Path, config: AgentConfig) -> MessageHistory
```
加载 History。从 `history_dir/history.json` 读取，不存在则创建新的。

```python
def register(self, brain_id: str, components: BrainComponents) -> None
```
手工注册 Brain 实例。

```python
def switch(self, brain_id: str) -> BrainComponents
```
切换当前 Brain 实例。brain_id 不存在时抛出 KeyError。

```python
def current(self) -> BrainComponents
```
获取当前 Brain 实例。当前 brain 未设置时抛出 RuntimeError。

```python
def current_brain_id(self) -> str
```
获取当前 Brain ID。未设置时返回 "default"。

```python
def list_brains(self) -> list[str]
```
列出所有已注册的 Brain ID。

```python
def get_brain_info(self, brain_id: str) -> Optional[BrainInfo]
```
获取 Brain 信息（供 UI 显示）。

```python
def create_brain(
    brain_id: str,
    template: str = "default",
    name: str = "New Persona"
) -> BrainComponents
```
创建新 Brain（UI 调用）。如果 template 存在则复制其配置，否则创建基础结构。

```python
def delete_brain(self, brain_id: str) -> None
```
删除 Brain（UI 调用）。不允许删除当前选中的 Brain。

---

## 5. summarizer.py - 日终摘要生成

日期切换时调用 LLM 生成当日对话摘要。

### 5.1 DailySummarizer

日终摘要生成器（异步版本）。

```python
def __init__(
    chat_agent: ChatAgent,
    output_dir: Path,
    model_config: Optional[ModelConfig] = None
)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| chat_agent | ChatAgent | ChatAgent 实例 |
| output_dir | Path | 摘要输出目录 |
| model_config | ModelConfig | 模型配置 |

```python
async def generate_summary(
    self,
    date: str,                          # YYYY-MM-DD
    messages: list[Message],
    persona_context: str = ""           # 用于摘要的人格上下文
) -> str
```
调用 LLM 生成当日摘要。

**流程**：
1. 构建摘要 Prompt
2. 调用 LLM
3. 解析 JSON 响应
4. 保存为 Markdown 和 JSON

**输出文件**：
- `{output_dir}/{date}.summary.md` - Markdown 格式
- `{output_dir}/../daily/{date}.summary.json` - JSON 格式

```python
def _build_summary_prompt(
    self,
    date: str,
    messages: list[Message],
    persona_context: str
) -> str
```
构建摘要 Prompt。要求 LLM 返回 JSON 格式，包含：
- summary_text: 对话摘要
- important_messages: 重要消息
- topics: 讨论话题
- emotional_tone: 情感基调
- user_preferences: 用户偏好
- unfinished_topics: 未完成话题

```python
async def _call_llm(self, prompt: str) -> str
```
调用 LLM 获取摘要。

```python
def _parse_summary_response(self, response_text: str) -> str
```
解析 LLM 响应，提取 JSON 并格式化为 Markdown。

---

### 5.2 SyncDailySummarizer

同步版本的日终摘要生成器。

```python
def __init__(
    self,
    llm_callable,  # (prompt: str) -> str
    output_dir: Path
)
```

```python
def generate_summary(
    self,
    date: str,
    messages: list[Message],
    persona_context: str = ""
) -> str
```
同步生成摘要。

---

## 6. reply_tagger.py - 回复标签生成与记忆更新

每次 API 响应时生成 ReplyTag，并更新 Brain 模块的记忆。

### 6.1 ReplyTagger

回复标签生成器与记忆更新器。委托给 Brain Tags 模块生成标签，同时处理记忆更新。

```python
def __init__(
    tag_generator: TagGenerator,
    storage_path: Optional[Path] = None
)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| tag_generator | TagGenerator | TagGenerator 实例 |
| storage_path | Path | 标签存储路径，默认为 `{tags_dir}/reply_tags.json` |

```python
def _load_tags(self) -> None
```
从磁盘加载已有标签。

```python
def _save_tags(self) -> None
```
保存标签到磁盘。只保留最近 100 条。

```python
def generate_tag(
    self,
    message_id: str,
    response_text: str,
    emotion_hint: Optional[str] = None
) -> ReplyTag
```
生成单条回复的标签。

```python
def generate_and_save(
    self,
    message_id: str,
    response_text: str,
    emotion_hint: Optional[str] = None
) -> ReplyTag
```
生成标签并保存到存储。

```python
def get_tag(self, message_id: str) -> Optional[ReplyTag]
```
根据消息 ID 获取标签。

```python
def get_recent_tags(self, limit: int = 10) -> list[ReplyTag]
```
获取最近的标签列表。

---

### 6.2 MemoryUpdater

记忆更新器 - 更新 Persona 的情景/偏好/事实记忆。仅写入 `persona/memories.json`，不修改 `profile.json`。

```python
def __init__(
    persona: Persona,
    storage_path: Optional[Path] = None
)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| persona | Persona | Persona 实例 |
| storage_path | Path | 存储路径，默认为 `{brain_dir}/persona/memories.json` |

```python
def _get_storage_path(self) -> Path
```
获取存储路径。

```python
def add_episodic_memory(
    self,
    content: str,
    importance: float = 1.0,
    context: Optional[str] = None
) -> None
```
添加情景记忆。调用 `persona.add_memory()` 后自动保存。

```python
def add_preference_memory(
    self,
    content: str,
    importance: float = 1.0,
    context: Optional[str] = None
) -> None
```
添加偏好记忆。

```python
def add_fact_memory(
    self,
    content: str,
    importance: float = 1.0,
    context: Optional[str] = None
) -> None
```
添加事实记忆。

```python
def update_from_summary(self, summary_data: dict) -> None
```
从日终摘要更新记忆。

**处理逻辑**：
- user_preferences → add_preference_memory (importance=1.5)
- unfinished_topics → add_episodic_memory (importance=1.0)
- important_messages → add_episodic_memory (importance=1.5)

```python
def save(self) -> None
```
保存记忆到磁盘。写入 JSON 文件，包含 updated_at 时间戳。

```python
def load(self) -> None
```
从磁盘加载记忆。

---

## 7. prompt_builder.py - Prompt 构建封装

封装 Brain 模块的 PromptBuilder，提供更简洁的接口。

### 7.1 SessionPromptBuilder

Session 级别的 Prompt 构建器。

```python
def __init__(
    persona: Persona,
    history: MessageHistory,
    style_engine: SpeakingStyleEngine,
    config: AgentConfig,
)
```

**内部组件**：
- `_inner`: 封装的 Brain PromptBuilder
- `_persona`, `_history`, `_style_engine`, `_config`: 引用（用于动态切换）

```python
def build_system_prompt(self, emotion: Optional[str] = None) -> str
```
构建系统 Prompt。委托给 `_inner.build_system_prompt()`。

```python
def build_conversation_context(
    self,
    current_message: str,
    include_history: bool = True,
    max_history_tokens: int = 2000
) -> str
```
构建对话上下文（用于 API 调用）。

**格式**：
```
{历史摘要段落}
{队列消息段落}
用户最新消息: {current_message}
```

```python
def build_full_prompt(
    self,
    current_message: str,
    emotion: Optional[str] = None,
    include_history: bool = True
) -> tuple[str, list[Message]]
```
构建完整 Prompt 和消息列表。

**返回**：
- system_prompt: 系统提示
- messages_for_api: Message 列表

```python
def build_history_summary_for_context(self, days: int = 3) -> str
```
构建历史摘要上下文。

```python
def build_persona_context(self) -> str
```
构建人格上下文。调用 `persona.build_persona_text()`。

```python
def build_memory_context(self, limit: int = 10) -> str
```
构建记忆上下文。

**格式**：
```
相关记忆:
- 记忆内容1
- 记忆内容2
```

---

## 8. manager.py - 核心调度类

协调所有组件，提供统一的会话管理接口。

### 8.1 SessionManager

Session 管理器 - 核心调度类。

```python
def __init__(
    config: SessionConfig,
    brain_registry: BrainRegistry,
    chat_agent: ChatAgent,
    tag_generator: Optional[TagGenerator] = None,
    use_msgpack: bool = False
)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| config | SessionConfig | Session 配置 |
| brain_registry | BrainRegistry | Brain 注册表（支持多 Brain） |
| chat_agent | ChatAgent | ChatAgent 实例 |
| tag_generator | TagGenerator | TagGenerator 实例，不指定则创建默认 |
| use_msgpack | bool | 是否使用 MessagePack 格式 |

**属性**：

```python
@property
def storage(self) -> SessionStorage
```
获取存储实例（延迟初始化）。

```python
@property
def summarizer(self) -> DailySummarizer
```
获取摘要器实例（延迟初始化）。

```python
@property
def prompt_builder(self) -> SessionPromptBuilder
```
获取当前 Brain 的 PromptBuilder。

```python
@property
def memory_updater(self) -> MemoryUpdater
```
获取记忆更新器。

---

### 8.2 对话流程

```python
async def send_message(
    self,
    user_message: str,
    emotion: Optional[str] = None,
    stream: bool = False
) -> dict
```
发送消息并处理响应（异步）。

**流程**：
1. 检查日期切换 → 归档旧 Session → 生成摘要
2. 保存用户消息
3. 构建 Prompt
4. 调用 API
5. 生成回复标签
6. 保存助手消息
7. 返回响应

**返回字典**：
```python
{
    "content": str,       # 回复内容
    "tag": ReplyTag,      # 回复标签
    "message_id": str,     # 消息ID
    "brain_id": str,       # 当前Brain ID
}
```

```python
def send_message_sync(
    self,
    user_message: str,
    emotion: Optional[str] = None,
) -> dict
```
发送消息并处理响应（同步版本）。

---

### 8.3 日期切换处理

```python
async def _check_and_handle_day_change(self) -> None
```
检查并处理日期切换（异步版本）。

**处理逻辑**：
1. 检测日期变化
2. 归档旧 Session
3. 生成日终摘要
4. 更新记忆

```python
def _check_and_handle_day_change_sync(self) -> None
```
检查并处理日期切换（同步版本）。同步模式下只归档，不生成摘要。

```python
async def _generate_end_of_day_summary(self, session: DaySession) -> None
```
生成日终摘要（异步）。

**条件检查**：
- session.summary_generated 已为 True → 跳过
- session.message_count < min_messages_for_summary → 跳过

```python
def _update_memories_from_summary(self, date: str) -> None
```
从摘要更新记忆。从 `{brain_dir}/history/daily/{date}.summary.json` 读取并更新。

---

### 8.4 Brain 切换

```python
def switch_brain(self, brain_id: str) -> None
```
切换 Brain 实例。重置存储和摘要器。

```python
def create_brain(
    self,
    brain_id: str,
    name: str = "New Persona",
    template: str = "default"
) -> BrainComponents
```
创建新 Brain（UI 调用）。

```python
def list_brains(self) -> list[dict]
```
列出所有 Brain。

**返回格式**：
```python
[
    {"id": str, "name": str, "description": str},
    ...
]
```

---

### 8.5 辅助方法

```python
def _generate_message_id(self) -> str
```
生成消息 ID。格式：`msg_{timestamp_ms}`

```python
async def _call_api(
    self,
    system_prompt: str,
    context: str,
    stream: bool
) -> dict
```
调用 API（异步）。

```python
def _call_api_sync(self, system_prompt: str, context: str) -> dict
```
调用 API（同步）。

```python
def get_conversation_history(self, days: int = 7) -> list[DaySession]
```
获取最近 N 天的会话历史。

```python
def export_session(self, date: str, format: str = "json") -> str
```
导出会话数据。

| format | 说明 |
|--------|------|
| json | 返回 JSON 字符串 |
| markdown | 返回 Markdown 格式 |

```python
def add_message_to_history(
    self,
    role: str,
    content: str,
    tags: Optional[list[str]] = None
) -> Message
```
添加消息到 Brain 的 MessageHistory。

```python
def get_today_messages(self) -> list[Message]
```
获取当日所有消息。

---

## 9. 模块依赖关系

```
__init__.py (统一导出)
├── config.py
│   └── SessionConfig
├── path_resolver.py
│   └── PathResolver
├── storage.py
│   ├── DaySession
│   └── SessionStorage
├── brain_registry.py
│   ├── BrainComponents
│   ├── BrainInfo
│   └── BrainRegistry
├── summarizer.py
│   ├── DailySummarizer (异步)
│   └── SyncDailySummarizer (同步)
├── reply_tagger.py
│   ├── ReplyTagger
│   └── MemoryUpdater
├── prompt_builder.py
│   └── SessionPromptBuilder
└── manager.py
    └── SessionManager (核心调度)
```

**跨模块依赖**：
- `SessionManager` 依赖 `BrainRegistry`, `SessionStorage`, `SessionPromptBuilder`, `ReplyTagger`, `DailySummarizer`
- `BrainRegistry` 依赖 `Persona`, `MessageHistory`, `SpeakingStyleEngine`, `PromptBuilder` (均来自 brain 模块)
- `SessionPromptBuilder` 依赖 `PromptBuilder` (来自 brain 模块)
- `ReplyTagger` 依赖 `TagGenerator` (来自 brain 模块)
- `SessionStorage` 依赖 `SessionConfig`, `PathResolver`, `DaySession`
- `DailySummarizer` 依赖 `ChatAgent`, `ModelConfig`, `Message` (来自 api 模块)

---

## 10. 典型使用流程

### 10.1 初始化

```python
from agent_core.session import SessionManager, SessionConfig, BrainRegistry
from agent_core.api import ChatAgent, ModelConfig

# 1. 创建配置
config = SessionConfig()

# 2. 创建 ChatAgent
chat_agent = ChatAgent(model_config)

# 3. 初始化 BrainRegistry 并加载
brain_registry = BrainRegistry()
brain_registry.load_all()

# 4. 创建 SessionManager
manager = SessionManager(config, brain_registry, chat_agent)
```

### 10.2 发送消息

```python
# 异步
response = await manager.send_message("你好", emotion="happy")
print(response["content"], response["tag"])

# 同步
response = manager.send_message_sync("你好")
```

### 10.3 切换 Brain

```python
manager.switch_brain("makise")
response = await manager.send_message("...")
```

### 10.4 创建新 Brain

```python
manager.create_brain("new_id", name="新角色", template="default")
```
