# 项目架构 - 分层 Agent 框架

amadues 的核心是 `agent_core`，界面层是 `GUI`。`SessionManager` 是运行时调度中心，向下读取 Brain 状态并调用 API，向上返回可驱动 UI 的内容和标签。

## 职责边界

- Brain 层只负责人格、记忆、历史、标签、风格和 Prompt 构建，不直接调用外部模型 API。
- Session 层负责一个聊天回合的编排、数据隔离、跨日/月摘要和 Brain 反向更新。
- API/Models 层负责 Provider 适配、请求/响应类型、工具调用和模型配置。
- GUI 层只提供 Flet 组件与回调接口，不写入业务数据。

## 模块结构

```text
src/
  agent_core/
    brain/
    session/
    api/
    models/
    api.py
  GUI/
    components/
    interfaces/
```

## 核心数据流

```text
用户输入
  -> SessionManager 检查日期/月切换
  -> SessionStorage 保存用户消息
  -> MessageHistory 保存/恢复 prompt 今日上下文
  -> SessionPromptBuilder 构建 system prompt 和上下文
  -> ChatAgent 调用 Provider
  -> ReplyTagger 生成 ReplyTag
  -> SessionStorage 保存助手消息
  -> MemoryUpdater 按摘要或关键结果回写 Persona 记忆
  -> 返回 content/tag/message_id/brain_id
```

## 数据流/存储

实际路径由 `PathResolver` 决定。数据目录优先级为 `AGENT_DATA_DIR`、`FLET_APP_STORAGE_DATA`、Windows AppData、项目下的 `data/`；因此 Windows 桌面运行时可能默认写入 `%LOCALAPPDATA%/amadues/data`，而不是仓库内 `data/`。

```text
data/
  {brain_id}/
    persona/
      profile.json
      memories.json
    history/
      history.json
      daily/
      summaries/
    tags/
      reply_tags.json
    session/
      current/
        YYYY-MM-DD.json
      archive/
        YYYY-MM/
          YYYY-MM-DD.json
config/
  models.json
```

## 典型用法

```python
from agent_core.api import ChatAgent, ModelConfig, APIProvider
from agent_core.brain import TagGenerator
from agent_core.session import BrainRegistry, SessionConfig, SessionManager

model_config = ModelConfig(name="MiniMax-M2.5", provider=APIProvider.MINIMAX)
chat_agent = ChatAgent(config=model_config)

registry = BrainRegistry()
registry.load_all()

manager = SessionManager(
    config=SessionConfig(model_config=model_config),
    brain_registry=registry,
    chat_agent=chat_agent,
    tag_generator=TagGenerator(),
)

response = manager.send_message_sync("你好")
print(response["content"])
```

## 注意事项

- `docs` 描述当前实现，不保留历史 Phase 计划。
- `MonthlySummarizer` 存在于 `agent_core.session.summarizer`，但没有从 `agent_core.session` 顶层导出。
- 工作区可能存在无关变更；文档维护不应修改 `src/`。
