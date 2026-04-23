# amadues 文档索引

amadues 是一个基于 Python 的 AI Agent 框架，核心能力包括角色人格、结构化记忆、会话调度、多模型 API 调用和 Galgame 风格聊天界面。

本目录以 `src/` 中的当前实现为准。旧设计稿中的目录、导入路径或阶段计划如果和源码冲突，以源码为准。

## 职责边界

- `agent_core.brain` 管理人格、记忆、历史、标签、说话风格、Prompt 和基础持久化。
- `agent_core.session` 编排一次聊天回合，处理跨日归档、摘要、回复标签、记忆回写和多 Brain 切换。
- `agent_core.api` 提供统一聊天 API、Provider 适配器、工具调用和响应类型。
- `agent_core.models` 维护模型目录、Provider 配置和 `config/models.json` 持久化。
- `GUI` 提供 Flet Galgame 风格界面组件和 Control 层回调接口。

## 文档地图

- [architecture.md](architecture.md)：整体架构、数据流和存储约定
- [api/README.md](api/README.md)：API 层消息、适配器、客户端和运行时
- [api/providers-and-models.md](api/providers-and-models.md)：Provider、模型目录和配置存储
- [brain/README.md](brain/README.md)：Brain 模块总览
- [brain/persona.md](brain/persona.md)：人格和记忆
- [brain/history.md](brain/history.md)：历史、队列、摘要
- [brain/tags.md](brain/tags.md)：回复标签和情感解析
- [brain/speaking-style.md](brain/speaking-style.md)：说话风格引擎
- [brain/prompt-builder.md](brain/prompt-builder.md)：Prompt 分段构建
- [brain/persistence-and-config.md](brain/persistence-and-config.md)：配置与文件持久化
- [session/README.md](session/README.md)：Session 模块总览
- [session/path-and-storage.md](session/path-and-storage.md)：路径解析和会话存储
- [session/brain-registry.md](session/brain-registry.md)：多 Brain 管理
- [session/prompt-and-manager.md](session/prompt-and-manager.md)：SessionPromptBuilder 和 SessionManager
- [session/summarizer-and-memory.md](session/summarizer-and-memory.md)：日/月摘要、标签和记忆回写
- [session/skill-vs-runtime.md](session/skill-vs-runtime.md)：人格模拟中 skill 与运行时系统的方案优劣分析
- [gui/README.md](gui/README.md)：GUI 总览
- [gui/components-and-interfaces.md](gui/components-and-interfaces.md)：组件和接口

## 维护约定

- 示例优先使用公共入口：`agent_core.brain`、`agent_core.session`、`agent_core.api`、`agent_core.models`、`GUI`。
- 未从模块 `__init__.py` 导出的对象，用明确子模块路径导入。
- 数据路径统一描述为 `data/{brain_id}/...`；Session 当前/归档数据位于 `data/{brain_id}/session/...`。
- 文档不记录已经过时的实现阶段、Phase 计划或重复设计草案。

## 最近同步

2026-04-23 更新：

- Brain 文档补充 `PersonalityState`，说明 `persona/state.json` 是运行时人格状态文件，和 GUI 静态配置 `profile.json` 分离。
- Prompt 文档补充 `当前人格状态` 段，顺序为 `identity -> style -> relationship -> personality_state -> memory -> history_summary -> queue -> runtime`。
- Tags 文档补充 LLM 情感模式：优先 LLM JSON 解析，失败回退关键词检测。
- Session 文档补充每轮消息会更新 `Persona.state` 并持久化到 `state.json`。
- 示例脚本文档说明 `generate_kurisu_brain.py` 会生成 `state.json`，`session_example.py` 会加载并更新它。
