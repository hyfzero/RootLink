# RootLink Flutter 架构

RootLink 使用 `app / domain / data / features` 分层。页面只处理展示和交互，状态控制器编排用例，Repository 与 Service 负责持久化、网络和图片/角色包处理。

```text
lib/
  app/        依赖、主题、页面状态
  domain/     模型、接口、Prompt 与 Agent 运行时
  data/       JSON、迁移、会话、Provider、ZIP、图片实现
  features/   首页、聊天、设置、角色编辑和共享组件
```

## 主要边界

- `RoleRepository`：角色 CRUD、默认角色和资源解析。
- `SessionRepository`：当日会话、跨日归档与历史读取。
- `SettingsRepository`：主题、模型、密钥和生成质量。
- `ChatProvider`：普通响应、SSE 流、取消及错误映射。
- `AgentRuntime`：Prompt、上下文预算、工具循环及十轮保护。
- `CharacterPackageService`：`.amadues` v1 校验、导入、导出和回滚。
- `PortraitProcessor`：抠图、缩放、偏移和统一画布，运行于 isolate。

Riverpod 不使用代码生成；领域模型手写 JSON 映射，并通过 `extraFields` 或基于原 Map 更新的方式保留未知字段。导航使用 Flutter 原生 Navigator 和 `PopScope`。

## 数据流

```text
用户输入
  -> ChatController 追加用户消息
  -> RootLinkAgentRuntime 构造 Prompt 和预算上下文
  -> HttpChatProvider 解析增量 UTF-8 / SSE
  -> UI 更新气泡、思考过程或沉浸立绘
  -> 会话原子写入
  -> ReplyTag、人格状态、记忆与关系更新
  -> 跨日归档和日/月摘要
```

## 本地存储

```text
<application-support>/
  data/{role_id}/
    persona/
    session/current/
    session/archive/
    history/daily/
    history/summaries/
    tags/reply_tags.json
    assets/
    ui.json
    config.json
  config/
  .amadues_storage_migration_v1
```

首次启动会检查应用支持目录、Android 旧应用目录、`%LOCALAPPDATA%\amadues`、旧打包目录，以及 `ROOTLINK_STORAGE_ROOT`、`FLET_APP_STORAGE_DATA`、`AGENT_DATA_DIR`、`AGENT_CONFIG_DIR` 覆盖路径。迁移先进入临时目录，所有 JSON 可解析后才复制缺失文件；不会覆盖现有有效数据，也不会删除旧目录。

## 响应式界面

- `<840px`：单栏页面与底部导航。
- `>=840px`：268px 角色/导航侧栏和最大约 1200px 内容区。
- 统一品牌紫、16–26px 圆角、扁平表面、低层级阴影和深浅主题。

测试覆盖领域数据往返、原子写入、会话摘要、Provider/SSE、工具调用、角色包攻击与回滚，以及 390/840/1200px 页面和视觉基线。
