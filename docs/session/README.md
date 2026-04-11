# Session 模块 - 会话调度中心

`agent_core.session` 将 Brain、API 和持久化串成完整聊天回合。它是应用层通常直接使用的运行时入口。

## 职责边界

- 管理当前 Brain、会话存储、摘要器、回复标签器和记忆更新器。
- 处理发送消息、日期/月切换、归档、摘要和导出。
- 封装 Brain PromptBuilder 生成 API 可用上下文。
- 不负责具体 Provider HTTP 请求实现，也不负责 GUI 渲染。

## 核心对象

公共入口：`from agent_core.session import ...`

- `SessionConfig`
- `PathResolver`
- `DaySession`、`SessionStorage`
- `BrainComponents`、`BrainInfo`、`BrainRegistry`
- `SessionPromptBuilder`
- `ReplyTagger`、`MemoryUpdater`
- `DailySummarizer`、`SyncDailySummarizer`
- `SessionManager`

未从顶层导出但存在：

- `MonthlySummarizer`：使用 `from agent_core.session.summarizer import MonthlySummarizer`

## 数据流/存储

```text
data/{brain_id}/session/current/YYYY-MM-DD.json
data/{brain_id}/session/archive/YYYY-MM/YYYY-MM-DD.json
data/{brain_id}/history/summaries/YYYY-MM-DD.summary.md
data/{brain_id}/history/summaries/YYYY-MM.monthly.md
data/{brain_id}/tags/reply_tags.json
data/{brain_id}/persona/memories.json
```

## 典型用法

```python
from agent_core.api import APIProvider, ChatAgent, ModelConfig
from agent_core.brain import TagGenerator
from agent_core.session import BrainRegistry, SessionConfig, SessionManager

model_config = ModelConfig(name="MiniMax-M2.5", provider=APIProvider.MINIMAX)
registry = BrainRegistry()
registry.load_all()

manager = SessionManager(
    config=SessionConfig(model_config=model_config),
    brain_registry=registry,
    chat_agent=ChatAgent(model_config),
    tag_generator=TagGenerator(),
)

result = manager.send_message_sync("晚上好")
```

## 注意事项

- `send_message()` 是异步方法，`send_message_sync()` 是同步方法。
- 同步日期切换只做归档；异步路径会生成摘要。
- 切换 Brain 会重置 storage、summarizer、prompt builder 和 memory updater 缓存。
