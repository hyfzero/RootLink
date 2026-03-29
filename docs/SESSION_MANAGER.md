# Session Manager 模块设计文档

## 1. 概述

**模块名称**: Session Manager
**功能定位**: 作为 Prompt 生成的核心调度器，同时负责对话数据的反向更新（生成回复标签、日终摘要）。

### 与 Brain 模块的协作关系

```
┌─────────────────────────────────────────────────────────────┐
│                    Session Manager                          │
│  (调度中心: 构建Prompt → 调用API → 接收回复 → 更新Brain)       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │  Prompt     │    │   API       │    │   Reply     │     │
│  │  Builder    │───▶│   Client    │───▶│   Tagger    │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│         │                                     │             │
│         ▼                                     ▼             │
│  ┌─────────────┐                      ┌─────────────┐      │
│  │   Brain     │◀─────────────────────│   Daily     │      │
│  │   Module    │    (日终摘要写入)      │   Summarizer│      │
│  └─────────────┘                      └─────────────┘      │
│         ▲                                                │
│         │                                                │
│  ┌─────────────┐    ┌─────────────┐                       │
│  │ Brain      │───▶│ Brain       │                       │
│  │ Registry   │    │ Switcher    │                       │
│  └─────────────┘    └─────────────┘                       │
│  (多 Brain 实例管理)                                      │
└─────────────────────────────────────────────────────────────┘
```

### 多 Brain 支持

**目录结构**:
```
data/brain/
├── default/                    # 默认 Brain
│   ├── persona/
│   │   ├── profile.json
│   │   └── memories.json
│   └── history/
│       └── ...
├── brain_001/                # Brain ID: brain_001
│   ├── persona/
│   └── history/
├── brain_002/                # Brain ID: brain_002
│   ├── persona/
│   └── history/
└── ...
```

**BrainRegistry 实现**:
```python
class BrainRegistry:
    """多 Brain 实例注册表（从目录加载）"""

    def __init__(self, base_path: Path):
        self._brains: dict[str, BrainComponents] = {}
        self._current: Optional[str] = None
        self._base_path = base_path

    def load_all(self) -> list[str]:
        """扫描目录加载所有 Brain，返回 ID 列表"""
        brain_dirs = [d for d in self._base_path.iterdir() if d.is_dir()]
        for brain_dir in brain_dirs:
            brain_id = brain_dir.name
            components = self._load_brain_components(brain_dir)
            self._brains[brain_id] = components
        if not self._current and self._brains:
            self._current = next(iter(self._brains))
        return list(self._brains.keys())

    def _load_brain_components(self, brain_dir: Path) -> BrainComponents:
        """从目录加载单个 Brain 的组件"""

    def switch(self, brain_id: str) -> BrainComponents:
        """切换当前 Brain 实例"""
        if brain_id not in self._brains:
            raise KeyError(f"Brain '{brain_id}' not found")
        self._current = brain_id
        return self._brains[brain_id]

    def current(self) -> BrainComponents:
        """获取当前 Brain 实例"""

    def list_brains(self) -> list[str]:
        """列出所有已注册的 Brain ID"""

    def current_brain_id(self) -> str:
        """获取当前 Brain ID"""

    # === UI 层接口 ===
    def get_brain_info(self, brain_id: str) -> BrainInfo:
        """获取 Brain 信息（供 UI 显示）"""

    def create_brain(self, brain_id: str, template: str = "default") -> BrainComponents:
        """创建新 Brain（UI 调用）"""

    def delete_brain(self, brain_id: str) -> None:
        """删除 Brain（UI 调用）"""
```

**Session 数据隔离**:
```
data/session/
├── default/              # 默认 Brain 的会话
│   ├── current/
│   └── archive/
├── brain_001/           # brain_001 的会话（独立）
│   ├── current/
│   └── archive/
└── brain_002/           # brain_002 的会话（独立）
    ├── current/
    └── archive/
```

### 核心职责

| 职责 | 说明 |
|------|------|
| **Prompt 构建** | 调用 Brain 模块构建完整 Prompt |
| **对话存储** | 以日期为单位存储聊天记录，支持 Token 限制 |
| **回复标签生成** | 每次 API 响应时生成 ReplyTag |
| **日终摘要** | 日期切换时调用 LLM 生成当日摘要 |
| **Brain 反向更新** | 将摘要和标签写回 Brain 模块 |

---

## 2. 目录结构

```
src/agent_core/
├── brain/                    # 现有 Brain 模块（只读 persona）
├── api/                      # 现有 API 模块
├── session/                  # 新增 Session Manager 模块
│   ├── __init__.py           # 统一导出
│   ├── manager.py            # SessionManager 主类
│   ├── prompt_builder.py     # Prompt 构建封装
│   ├── storage.py            # 对话存储（按日期）
│   ├── summarizer.py         # 日终摘要生成
│   ├── reply_tagger.py       # 回复标签生成（调用 brain.tags）
│   ├── path_resolver.py      # 三端路径兼容解析
│   └── config.py             # Session 配置
```

---

## 3. 功能设计

### 3.1 跨三端路径解析 (`path_resolver.py`)

**目标**: 兼容 Windows/Linux/Mac 三端的数据路径。

**设计原则**:
- 使用 `pathlib.Path` 而不是字符串拼接
- 环境变量优先于硬编码路径
- 相对路径基于项目根目录解析

```python
class PathResolver:
    """三端路径解析器"""

    # 环境变量配置项
    ENV_DATA_DIR = "AGENT_DATA_DIR"  # 数据根目录
    ENV_CONFIG_DIR = "AGENT_CONFIG_DIR"  # 配置目录

    # 默认相对路径（相对于项目根目录）
    DEFAULT_DATA_RELATIVE = "data"
    DEFAULT_CONFIG_RELATIVE = "config"

    @classmethod
    def get_project_root(cls) -> Path:
        """获取项目根目录（向上查找 pyproject.toml / project.godot）"""

    @classmethod
    def get_data_dir(cls) -> Path:
        """获取数据目录，优先级: 环境变量 > 项目根/data > ./data"""

    @classmethod
    def get_brain_dir(cls) -> Path:
        """Brain 模块数据目录: {data_dir}/brain/"""

    @classmethod
    def get_session_dir(cls) -> Path:
        """Session 数据目录: {data_dir}/session/"""

    @classmethod
    def resolve(cls, relative_path: str) -> Path:
        """解析相对路径到绝对路径"""
```

**路径结构**:
```
data/                          # 数据根目录
├── brain/                     # Brain 模块数据
│   ├── persona/
│   │   ├── profile.json
│   │   └── memories.json
│   └── history/
│       ├── daily/            # 每日消息 (YYYY-MM-DD.json)
│       └── summaries/       # 每日摘要 (YYYY-MM-DD.summary.md)
│
├── session/                  # Session Manager 数据
│   ├── current/              # 当日对话记录
│   │   └── YYYY-MM-DD.json
│   ├── archive/              # 历史归档（按月分目录）
│   │   └── 2026-03/
│   │       └── 2026-03-28.json
│   └── temp/                 # 临时文件（摘要生成中）
│
└── tags/                     # 回复标签（Session 生成）
    └── reply_tags.json
```

---

### 3.2 对话存储 (`storage.py`)

**目标**: 以日期为单位存储聊天记录，支持 Token 限制和自动清理。

**设计原则** (参考 OpenClaw 的 Token 感知机制):
- 不无限制扩大，单日消息有上限
- 早于当前日期的消息自动归档到 archive
- 定期清理过旧数据

```python
@dataclass
class SessionConfig:
    """Session 配置"""
    max_messages_per_day: int = 500      # 单日最大消息数
    max_tokens_per_day: int = 50000       # 单日最大 Token（近似）
    archive_retention_days: int = 30      # 归档保留天数
    current_day_messages_limit: int = 200 # 当日消息软上限（超过时 compact）

class DaySession:
    """单日会话数据"""

    date: str                             # YYYY-MM-DD
    messages: list[Message]                # 当日消息列表
    message_count: int                    # 消息计数
    total_tokens_estimate: int            # 总 Token 估算
    summary_generated: bool = False       # 是否已生成摘要

    def add_message(self, role: str, content: str) -> None:
        """添加消息，带 Token 估算"""

    def needs_compact(self) -> bool:
        """是否需要压缩（超过单日上限）"""

    def compact(self, keep_last_n: int = 100) -> None:
        """压缩保留最近 N 条消息"""

class SessionStorage:
    """会话存储管理器"""

    def __init__(
        self,
        config: SessionConfig,
        resolver: PathResolver,
        use_msgpack: bool = False
    ):
        self.config = config
        self.resolver = resolver
        self._use_msgpack = use_msgpack
        self._today_session: Optional[DaySession] = None
        self._current_date: Optional[str] = None

    def _load(self, path: Path) -> Any:
        """根据格式加载文件"""
        if self._use_msgpack and path.suffix == ".msgpack":
            import msgpack
            return msgpack.unpackb(path.read_bytes(), raw=False)
        return json.loads(path.read_text(encoding="utf-8"))

    def _save(self, path: Path, data: Any) -> None:
        """根据格式保存文件"""
        if self._use_msgpack and path.suffix == ".msgpack":
            import msgpack
            path.write_bytes(msgpack.packb(data, use_single_float=True))
        else:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # === 核心操作 ===

    def get_or_create_today(self) -> DaySession:
        """获取或创建当日 Session"""

    def add_message(self, role: str, content: str) -> DaySession:
        """添加消息到当日 Session"""

    def get_today_messages(self) -> list[Message]:
        """获取当日所有消息"""

    def archive_if_new_day(self) -> Optional[DaySession]:
        """检查日期是否切换，若是则归档旧 Session"""

    # === 归档管理 ===

    def archive_session(self, session: DaySession) -> None:
        """归档 Session 到 archive/{year-month}/"""

    def cleanup_old_archives(self) -> int:
        """清理超过保留期的归档，返回删除数量"""

    # === 批量读取 ===

    def get_recent_sessions(self, days: int = 7) -> list[DaySession]:
        """获取最近 N 天的 Session"""

    def get_session_by_date(self, date: str) -> Optional[DaySession]:
        """按日期获取 Session"""
```

**Token 估算策略**:
```python
def estimate_tokens(text: str) -> int:
    """粗略估算中英文混合文本的 Token 数"""
    # 中文: 每字符 ≈ 1.5 Token
    # 英文: 每单词 ≈ 1.3 Token
    # 留 20% buffer
```

**Compact 机制**:
- 当 `message_count > max_messages_per_day` 或 `total_tokens > max_tokens_per_day` 时触发
- 动态计算保留条数：基于 `max_tokens_per_day` 和平均消息长度估算，**通常 50-100 条**
- 优先保留用户消息（权重更高）
- 标记该日需要摘要（摘要可以基于压缩后的数据）

```python
def calculate_keep_count(self, avg_token_per_message: int) -> int:
    """动态计算保留条数，确保不超出 Token 上限"""
    max_messages = self.config.max_tokens_per_day // max(avg_token_per_message, 50)
    # 限制在 50-100 之间
    return max(50, min(100, max_messages))
```

---

### 3.3 Prompt 构建封装 (`prompt_builder.py`)

**目标**: 封装 Brain 模块的 PromptBuilder，提供更简洁的接口。

```python
class SessionPromptBuilder:
    """Session 级别的 Prompt 构建器"""

    def __init__(
        self,
        persona: Persona,
        history: MessageHistory,
        style_engine: SpeakingStyleEngine,
        config: AgentConfig
    ):
        self.persona = persona
        self.history = history
        self.style_engine = style_engine
        self.config = config

    def build_system_prompt(self, emotion: Optional[str] = None) -> str:
        """构建系统 Prompt"""

    def build_conversation_context(
        self,
        current_message: str,
        include_history: bool = True,
        max_history_tokens: int = 2000
    ) -> str:
        """构建对话上下文（用于 API 调用）"""

    def build_full_prompt(
        self,
        current_message: str,
        emotion: Optional[str] = None,
        include_history: bool = True
    ) -> tuple[str, list[Message]]:
        """
        构建完整 Prompt 和消息列表
        返回: (system_prompt, messages_for_api)
        """
```

**与 Brain 模块的 PromptBuilder 对比**:

| Brain PromptBuilder | Session PromptBuilder |
|---------------------|-----------------------|
| 底层构建器 | 封装层，简化调用 |
| 需要手动传入各组件 | 内部持有 Brain 组件 |
| 返回字符串 | 同时返回 Prompt 和 Message 列表 |

---

### 3.4 记忆更新与回复标签 (`reply_tagger.py`)

**目标**: 每次 API 响应时生成 ReplyTag，并更新 Brain 模块的记忆。

**设计**:

```
┌─────────────────────────────────────────────────────────┐
│                 Reply 处理流程                            │
│                                                         │
│  API 响应文本                                           │
│       │                                                 │
│       ▼                                                 │
│  ┌─────────────┐                                        │
│  │ ReplyTag    │ ←── 复用 brain.tags.TagGenerator        │
│  └──────┬──────┘                                        │
│         │                                               │
│         ▼                                               │
│  ┌─────────────┐                                        │
│  │ 记忆更新    │ ←── 更新 Persona 的情景/偏好/事实记忆   │
│  │ (可选)     │     仅写入 persona/memories.json        │
│  └─────────────┘     不修改 persona/profile.json        │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**回复标签生成**: 直接复用 `brain.tags.TagGenerator`

```python
class ReplyTagger:
    """回复标签生成器（委托给 Brain Tags）"""

    def __init__(self, tag_generator: TagGenerator):
        self.tag_generator = tag_generator

    def generate_tag(
        self,
        message_id: str,
        response_text: str,
        emotion_hint: Optional[str] = None
    ) -> ReplyTag:
        """
        生成单条回复的标签
        """
        return self.tag_generator.generate_tag(
            text=response_text,
            emotion_hint=emotion_hint,
            message_id=message_id
        )

    def generate_and_save(
        self,
        message_id: str,
        response_text: str,
        storage_path: Path
    ) -> ReplyTag:
        """生成标签并保存到 storage"""
        tag = self.generate_tag(message_id, response_text)
        self._save_tag(tag, storage_path)
        return tag
```

**更新流程**:
```
API 响应到达
    ↓
ReplyTagger.generate_tag()
    ↓
保存到 data/tags/reply_tags.json
    ↓
SessionManager 通知 Brain 模块更新（如有必要）
```

---

### 3.5 日终摘要生成 (`summarizer.py`)

**目标**: 日期切换时调用 LLM 生成当日对话摘要。

**设计原则**:
- 只调用一次 API
- **摘要模型与当前对话模型一致**（从 config 读取）
- 摘要内容写入 Brain 模块的 history/summaries/
- 更新 persona 记忆文件

```python
class DailySummarizer:
    """日终摘要生成器"""

    def __init__(
        self,
        chat_agent: ChatAgent,
        output_dir: Path,
        model_config: ModelConfig          # 从配置文件读取
    ):
        self.chat_agent = chat_agent
        self.output_dir = output_dir
        self.model_config = model_config  # 摘要使用当前对话模型

    def _build_summary_prompt(
        self,
        date: str,
        messages: list[Message],
        persona_context: str
    ) -> str:
        """构建摘要 Prompt"""
        # 包含: 日期、当日消息人格上下文、消息列表
```

**摘要内容结构** (参考 Brain LLM Summary 设计):
```markdown
# 2026-03-28 对话摘要

## 情感基调
[愉快/中性/低沉/紧张/...]

## 话题回顾
- [话题1]: 简要描述
- [话题2]: 简要描述

## 用户偏好
- [发现的偏好1]
- [发现的偏好2]

## 未完成话题
- [话题1] - 状态：待继续

## 关键事件
- [关键事件描述]
```

---

### 3.6 Session Manager 主类 (`manager.py`)

**目标**: 协调所有组件，提供统一的会话管理接口。

```python
class SessionManager:
    """Session 管理器 - 核心调度类"""

    def __init__(
        self,
        config: SessionConfig,
        path_resolver: PathResolver,
        brain_registry: BrainRegistry,        # 多 Brain 注册表
        chat_agent: ChatAgent,
        tag_generator: TagGenerator,
        use_msgpack: bool = False
    ):
        self.config = config
        self.brain_registry = brain_registry
        self.storage = SessionStorage(config, path_resolver, use_msgpack)
        self.summarizer = DailySummarizer(chat_agent, path_resolver.get_brain_dir() / "history" / "summaries", config.model_config)
        self.tagger = ReplyTagger(tag_generator)
        self._current_date: Optional[str] = None

    @property
    def prompt_builder(self) -> SessionPromptBuilder:
        """获取当前 Brain 的 PromptBuilder"""
        return SessionPromptBuilder(**self.brain_registry.current())

    def _get_session_dir(self) -> Path:
        """获取当前 Brain 的 Session 目录"""
        return self.resolver.get_session_dir() / self.brain_registry.current_brain_id()

    # === 对话流程 ===

    async def send_message(
        self,
        user_message: str,
        emotion: Optional[str] = None,
        stream: bool = False
    ) -> ChatResponse:
        """
        发送消息并处理响应
        流程:
        1. 检查日期切换 → 归档旧 Session → 生成摘要
        2. 保存用户消息
        3. 构建 Prompt
        4. 调用 API
        5. 生成回复标签
        6. 保存助手消息
        7. 返回响应
        """
        # 1. 日期切换检查
        await self._check_and_handle_day_change()

        # 2. 保存用户消息
        self.storage.add_message("user", user_message)

        # 3. 构建 Prompt
        system_prompt = self.prompt_builder.build_system_prompt(emotion)
        context = self.prompt_builder.build_conversation_context(user_message)

        # 4. 调用 API
        response = await self._call_api(system_prompt, context, stream)

        # 5. 生成回复标签
        message_id = self._generate_message_id()
        reply_tag = self.tagger.generate_tag(message_id, response.content)
        self._save_reply_tag(reply_tag)

        # 6. 保存助手消息
        self.storage.add_message("assistant", response.content)

        # 7. 返回
        return response

    # === 日期切换处理 ===

    async def _check_and_handle_day_change(self) -> None:
        """检查并处理日期切换"""
        today = datetime.now().strftime("%Y-%m-%d")

        if self._current_date is not None and self._current_date != today:
            # 日期切换：归档 → 生成摘要
            old_session = self.storage.archive_if_new_day()
            if old_session:
                await self._generate_end_of_day_summary(old_session)

        self._current_date = today
        self.storage.get_or_create_today()

    async def _generate_end_of_day_summary(self, session: DaySession) -> None:
        """生成日终摘要"""
        if session.summary_generated:
            return

        messages = session.messages
        if len(messages) < 4:  # 太少消息不生成
            return

        persona_context = self.prompt_builder.persona.build_persona_text()
        await self.summarizer.generate_summary(
            date=session.date,
            messages=messages,
            persona_context=persona_context
        )
        session.summary_generated = True

    # === 辅助方法 ===

    def _generate_message_id(self) -> str:
        """生成消息 ID"""

    def _save_reply_tag(self, tag: ReplyTag) -> None:
        """保存回复标签到 data/tags/"""

    async def _call_api(
        self,
        system_prompt: str,
        context: str,
        stream: bool
    ) -> ChatResponse:
        """调用 API"""

    def get_conversation_history(self, days: int = 7) -> list[DaySession]:
        """获取最近 N 天的会话历史"""

    def export_session(self, date: str, format: str = "json") -> str:
        """导出会话数据"""
```

---

## 4. 配置设计

### 4.1 SessionConfig

```python
# session/config.py

@dataclass
class SessionConfig:
    """Session Manager 配置"""

    # 存储限制
    max_messages_per_day: int = 500
    max_tokens_per_day: int = 50000
    archive_retention_days: int = 30

    # 摘要生成
    min_messages_for_summary: int = 4

    # 模型配置（从 config/agent_config.json 读取）
    model_config: ModelConfig

    # 路径配置（留空使用默认）
    data_dir: Optional[str] = None
    brain_dir: Optional[str] = None

    # 存储格式
    use_msgpack: bool = False  # 大数据量时启用
```

### 4.2 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `AGENT_DATA_DIR` | 数据根目录 | `./data` |
| `AGENT_CONFIG_DIR` | 配置目录 | `./config` |

---

## 5. 数据流图

### 5.1 发送消息完整流程

```
用户发送消息
       │
       ▼
┌──────────────────┐
│ 日期切换检查      │ ──是──▶ 归档旧Session → 生成日终摘要
└────────┬─────────┘
         │否
         ▼
┌──────────────────┐
│ 保存用户消息      │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 检查消息上限      │ ──是──▶ Compact（保留最近100条）
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 构建 System Prompt│ ← Brain.Persona
│ 构建 Context      │ ← Brain.History + Brain.StyleEngine
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 调用 API          │ ← ChatAgent (MiniMax/OpenAI/...)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 生成 ReplyTag    │ ← Brain.Tags
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 保存助手消息      │
└────────┬─────────┘
         │
         ▼
      返回响应
```

### 5.2 日期切换流程

```
日期检测: today != _current_date
         │
         ▼
┌──────────────────┐
│ 归档当日 Session │ → data/session/archive/YYYY-MM/YYYY-MM-DD.json
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 消息数 >= 4 ?    │ ──否──▶ 跳过摘要
└────────┬─────────┘
         │是
         ▼
┌──────────────────┐
│ 调用 LLM 生成摘要 │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 保存到 Brain     │ → data/brain/history/summaries/YYYY-MM-DD.summary.md
└──────────────────┘
```

---

## 6. 与 Brain 模块的边界

| 操作 | Brain 模块 | Session 模块 |
|------|-----------|-------------|
| 读取 persona/profile.json | ✅ | ✅ (只读) |
| 读取 persona/memories.json | ✅ | ✅ (只读) |
| **写入 persona/memories.json** | ✅ | ✅ (更新情景/偏好/事实记忆) |
| 写入 persona/profile.json | ✅ | ❌ (不修改人格配置) |
| 读取 history/daily/*.json | ✅ | ✅ |
| 写入 history/daily/*.json | ✅ | ✅ (协作) |
| 写入 history/summaries/*.md | ✅ | ✅ (Session 生成) |
| 读取 tags/ | ✅ | ✅ |
| 写入 tags/ | ✅ | ✅ |
| 构建 Prompt | ✅ | ✅ (封装) |
| 管理 Session 生命周期 | ❌ | ✅ |
| 生成 ReplyTag | ✅ | ✅ (调用) |
| 生成日终摘要 | ❌ | ✅ |

---

## 7. 错误处理

| 场景 | 处理方式 |
|------|----------|
| API 调用失败 | 重试 3 次，间隔指数退避 |
| 摘要生成失败 | 记录日志，不阻塞主流程 |
| 文件写入失败 | 抛出异常，打印路径 |
| 日期切换时旧 Session 未保存 | 强制保存到 archive |
| Token 估算溢出 | 触发 Compact |

---

## 8. 已确认需求

1. **MessagePack 格式支持** - 大数据量时性能更优，存储层需同时支持 JSON 和 MessagePack
2. **多 Brain 实例切换** - 支持多个 Brain 配置（如不同人格）动态切换

---

## 9. 实现优先级

1. **Phase 1: 核心框架**
   - `path_resolver.py` - 路径兼容
   - `config.py` - 配置定义
   - `storage.py` - 基础存储

2. **Phase 2: Prompt 构建**
   - `prompt_builder.py` - 封装 Brain PromptBuilder

3. **Phase 3: 回复标签**
   - `reply_tagger.py` - 调用 Brain Tags

4. **Phase 4: 日终摘要**
   - `summarizer.py` - LLM 调用

5. **Phase 5: 集成**
   - `manager.py` - 统一调度
   - 与现有系统集成测试
