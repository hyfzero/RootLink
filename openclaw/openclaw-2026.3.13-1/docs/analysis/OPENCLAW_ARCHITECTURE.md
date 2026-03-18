# OpenClaw 架构分析文档

## 一、项目概述

OpenClaw 是一个运行在用户自有设备上的**个人AI助手**，支持通过多种即时通讯渠道（WhatsApp、Telegram、Slack、Discord、iMessage等）与用户交互。

### 核心特性
- **多渠道消息接入**：支持20+消息平台
- **本地优先Gateway**：单一控制平面管理会话、渠道、工具和事件
- **Pi Agent Runtime**：RPC模式的AI Agent运行时
- **Live Canvas**：Agent驱动的可视化工作区
- **Skills平台**：可扩展的技能系统

---

## 二、整体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Messaging Channels                                │
│  WhatsApp / Telegram / Slack / Discord / Signal / iMessage / IRC /    │
│  Microsoft Teams / Matrix / Feishu / LINE / Mattermost / ...           │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Gateway (控制平面)                              │
│              ws://127.0.0.1:18789 (本地WebSocket服务)                  │
├─────────────────────────────────────────────────────────────────────────┤
│  ├─ Pi Agent (RPC模式)        │  ├─ CLI (openclaw命令)                 │
│  ├─ WebChat UI               │  ├─ macOS App                          │
│  ├─ Canvas Host              │  └─ 渠道协议适配层                     │
└─────────────────────────────────────────────────────────────────────────┘
```

### 核心目录结构

```
src/
├── acp/                    # Agent Control Plane (ACP) - 核心Agent控制协议
│   ├── client.ts           # ACP客户端实现
│   ├── server.ts           # ACP服务器实现
│   ├── translator.ts        # 消息转换层（处理Prompt/Response）
│   ├── session-mapper.ts    # 会话映射
│   ├── control-plane/      # 控制平面管理
│   └── runtime/            # 运行时类型定义
│
├── agents/                 # Agent实现
│   ├── acp-spawn.ts       # Agent Spawn（创建子Agent）
│   ├── system-prompt.ts   # System Prompt构建
│   ├── pi-embedded-runner/ # 嵌入式Pi Agent
│   └── tools/              # Agent工具定义
│
├── auto-reply/            # 自动回复引擎
│   ├── reply.ts           # 回复入口
│   ├── reply/agent-runner.ts  # Agent执行器
│   └── thinking.ts        # 思考级别控制
│
├── channels/              # 渠道抽象层
│   └── plugins/           # 渠道插件
│
├── config/               # 配置管理
│   ├── sessions.ts       # 会话存储
│   └── types.*           # 类型定义
│
├── gateway/              # Gateway服务器
│   ├── server.ts         # WebSocket服务器
│   └── client.ts         # 客户端连接
│
├── memory/               # 记忆系统
├── providers/            # LLM提供商
└── sessions/             # 会话管理
```

---

## 三、消息机制

### 3.1 消息流程架构

```
Inbound Message
      │
      ▼
┌─────────────────┐
│  Channel Adapter │  (telegram/discord/slack/...)
│  渠道适配层       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Message Handler │  (消息预处理、验证)
│  消息处理器       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Route Resolve  │  (路由解析、Agent选择)
│  路由解析        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Session Mapper │  (会话映射/创建)
│  会话映射        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  ACP Translator │  (转换为Prompt请求)
│  协议转换层      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Pi Agent Core  │  (AI推理引擎)
│  Agent核心       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Response       │  (生成响应)
│  响应生成        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Outbound       │  (发送回原渠道)
│  出站处理        │
└─────────────────┘
```

### 3.2 核心消息类型

#### ACP协议消息类型（定义在`src/acp/translator.ts`）

```typescript
// 核心请求/响应类型
InitializeRequest / InitializeResponse   // 初始化
NewSessionRequest / NewSessionResponse   // 创建会话
LoadSessionRequest / LoadSessionResponse // 加载会话
PromptRequest / PromptResponse           // 发送Prompt获取响应
AuthenticateRequest / AuthenticateResponse // 认证
ListSessionsRequest / ListSessionsResponse // 列出会话
SetSessionConfigOptionRequest           // 设置会话配置
SetSessionModeRequest                   // 设置会话模式
CancelNotification                       // 取消通知
```

### 3.3 消息处理关键文件

| 文件 | 职责 |
|------|------|
| `src/acp/translator.ts` | 消息协议转换，处理Prompt/Response |
| `src/acp/session-mapper.ts` | 会话key解析和映射 |
| `src/auto-reply/reply/agent-runner.ts` | Agent执行和响应生成 |
| `src/channels/session.ts` | 渠道会话管理 |
| `src/channels/targets.ts` | 消息目标解析 |

---

## 四、Prompt机制

### 4.1 System Prompt构建

OpenClaw使用模块化方式构建System Prompt，核心文件位于：

- **`src/agents/system-prompt.ts`** - 主Prompt构建器
- **`src/agents/pi-embedded-runner/system-prompt.ts`** - 嵌入式运行时版本

#### Prompt模式（PromptMode）

```typescript
type PromptMode = "full" | "minimal" | "none";
// "full"   - 完整Prompt（主Agent）
// "minimal" - 精简Prompt（子Agent）
// "none"   - 仅基本身份标识
```

### 4.2 Prompt结构详解

```
┌──────────────────────────────────────────────────────────────────────┐
│                    System Prompt 组成结构                            │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. 身份声明                                                         │
│     "You are a personal assistant running inside OpenClaw."         │
│                                                                      │
│  2. 工具定义 (Tooling)                                              │
│     - 核心工具列表（read/write/edit/exec/browser等）               │
│     - 工具使用规范和说明                                             │
│     - 工具调用风格指南                                               │
│                                                                      │
│  3. 安全策略 (Safety)                                               │
│     - 目标约束：无独立目标，优先安全                                 │
│     - 合规要求：遵守暂停/审计请求                                    │
│                                                                      │
│  4. OpenClaw CLI参考                                                │
│     - Gateway管理命令                                                │
│     - 配置管理命令                                                   │
│                                                                      │
│  5. Skills (可选)                                                   │
│     - 技能加载规则                                                   │
│     - 技能使用约束                                                   │
│                                                                      │
│  6. Memory Recall (可选)                                            │
│     - 记忆检索工具使用指导                                           │
│     - 引用格式规范                                                   │
│                                                                      │
│  7. 工作区 (Workspace)                                              │
│     - 当前工作目录                                                   │
│     - 文件操作指导                                                   │
│                                                                      │
│  8. 运行时信息 (Runtime)                                            │
│     - 主机信息 (OS/Node版本)                                        │
│     - 模型信息                                                       │
│     - 渠道能力                                                       │
│                                                                      │
│  9. 消息功能 (Messaging, 可选)                                       │
│     - 会话回复路由                                                   │
│     - 跨会话消息                                                     │
│     - 子Agent编排                                                    │
│                                                                      │
│ 10. 消息渠道能力 (Channel-specific)                                  │
│     - 内联按钮                                                       │
│     - 回复标签                                                       │
│     - TTS语音提示                                                    │
│                                                                      │
│ 11. 模型别名 (可选)                                                  │
│     - 模型名称映射                                                   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.3 Prompt构建参数

`buildAgentSystemPrompt()`函数接收的关键参数：

```typescript
interface BuildPromptParams {
  workspaceDir: string;           // 工作目录
  defaultThinkLevel?: ThinkLevel; // 思考级别
  reasoningLevel?: ReasoningLevel; // 推理级别
  extraSystemPrompt?: string;     // 额外系统Prompt
  ownerNumbers?: string[];        // 授权用户ID
  ownerDisplay?: "raw" | "hash";  // ID显示方式
  toolNames?: string[];           // 可用工具名
  toolSummaries?: Record<string, string>; // 工具描述
  modelAliasLines?: string[];     // 模型别名
  userTimezone?: string;          // 用户时区
  skillsPrompt?: string;          // 技能配置
  promptMode?: PromptMode;       // Prompt模式
  runtimeInfo?: {                 // 运行时信息
    agentId?: string;
    host?: string;
    os?: string;
    model?: string;
    channel?: string;
    capabilities?: string[];
  };
  sandboxInfo?: EmbeddedSandboxInfo; // 沙箱信息
  memoryCitationsMode?: MemoryCitationsMode; // 引用模式
}
```

### 4.4 Prompt分段构建函数

| 函数 | 职责 |
|------|------|
| `buildSkillsSection()` | 构建Skills提示 |
| `buildMemorySection()` | 构建Memory Recall提示 |
| `buildUserIdentitySection()` | 构建授权用户提示 |
| `buildTimeSection()` | 构建时间信息 |
| `buildReplyTagsSection()` | 构建回复标签提示 |
| `buildMessagingSection()` | 构建消息功能提示 |
| `buildVoiceSection()` | 构建TTS语音提示 |
| `buildDocsSection()` | 构建文档链接提示 |

---

## 五、Agent控制平面 (ACP)

### 5.1 ACP协议概述

ACP (Agent Control Plane) 是OpenClaw的核心Agent控制协议，基于`@agentclientprotocol/sdk`实现。

#### 核心概念

- **Session（会话）**：Agent与用户的对话上下文
- **Prompt（提示）**：发送给Agent的输入
- **Tool Call（工具调用）**：Agent请求执行的操作
- **Event（事件）**：Agent运行时的事件（开始/结束/工具调用等）

### 5.2 ACP架构组件

```
┌─────────────────────────────────────────────────────────────────┐
│                      ACP Server                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────┐   │
│  │  Translator    │  │  Session Manager│  │  Tool Registry│   │
│  │  (消息转换)     │  │  (会话管理)     │  │  (工具注册)    │   │
│  └────────┬────────┘  └────────┬────────┘  └───────┬───────┘   │
│           │                    │                    │            │
│           └────────────────────┼────────────────────┘            │
│                                │                                   │
│                    ┌───────────┴───────────┐                       │
│                    │   Control Plane      │                       │
│                    │   (控制平面管理器)     │                       │
│                    └───────────┬───────────┘                       │
└────────────────────────────────┼──────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Pi Agent Runtime                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────┐   │
│  │  System Prompt │  │  Tool Executor  │  │  State Manager│   │
│  │  (系统提示)     │  │  (工具执行器)    │  │  (状态管理)    │   │
│  └─────────────────┘  └─────────────────┘  └───────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 5.3 关键ACP文件

| 文件 | 职责 |
|------|------|
| `src/acp/translator.ts` | ACP协议消息转换核心 |
| `src/acp/session.ts` | 会话存储管理 |
| `src/acp/client.ts` | ACP客户端实现 |
| `src/acp/server.ts` | ACP服务器实现 |
| `src/acp/control-plane/manager.ts` | 控制平面管理 |

---

## 六、会话管理

### 6.1 会话模型

```
┌─────────────────────────────────────────────────────────────────┐
│                      Session Model                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  main session (主会话)                                          │
│    │                                                             │
│    ├──  Direct Chat (直接对话)                                   │
│    │                                                             │
│    ├──  Group Isolation (群组隔离)                              │
│    │    └──  Thread-bound Sessions (线程绑定会话)              │
│    │                                                             │
│    └──  Activation Modes                                        │
│         ├──  auto (自动)                                        │
│         ├──  manual (手动)                                      │
│         └──  voice-wake (语音唤醒)                              │
│                                                                  │
│  Sub-agents (子Agent)                                           │
│    ├──  Spawned Sessions                                        │
│    └──  ACP Harness                                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 会话关键文件

| 文件 | 职责 |
|------|------|
| `src/config/sessions.ts` | 会话存储和加载 |
| `src/acp/session-mapper.ts` | 会话key解析 |
| `src/channels/session.ts` | 渠道会话处理 |

---

## 七、工具系统

### 7.1 核心工具列表

OpenClaw Agent可用的核心工具（定义在`system-prompt.ts`）：

| 工具名 | 描述 |
|--------|------|
| `read` | 读取文件内容 |
| `write` | 创建或覆写文件 |
| `edit` | 精确编辑文件 |
| `apply_patch` | 应用多文件补丁 |
| `grep` | 搜索文件内容 |
| `find` | 按glob模式查找文件 |
| `ls` | 列出目录内容 |
| `exec` | 运行shell命令 |
| `process` | 管理后台exec会话 |
| `web_search` | 网页搜索 |
| `web_fetch` | 获取网页内容 |
| `browser` | 控制浏览器 |
| `canvas` | Canvas操作 |
| `nodes` | 节点设备控制 |
| `cron` | 定时任务管理 |
| `message` | 发送消息 |
| `gateway` | Gateway控制 |
| `sessions_spawn` | 创建子Agent会话 |
| `session_status` | 会话状态查询 |

### 7.2 工具定义位置

- **核心工具**：在`src/agents/system-prompt.ts`中硬编码
- **外部工具**：在`src/agents/tool-summaries.ts`中配置
- **Skill工具**：在skills配置中动态加载

---

## 八、渠道接入

### 8.1 支持的渠道

| 渠道 | 协议库 | 目录 |
|------|--------|------|
| WhatsApp | Baileys | `src/whatsapp/` |
| Telegram | grammY | `src/telegram/` |
| Slack | Bolt | `src/slack/` |
| Discord | discord.js | `src/discord/` |
| Signal | signal-cli | `src/signal/` |
| iMessage | BlueBubbles | `src/imessage/` |
| IRC | - | `src/irc/` |
| Microsoft Teams | - | `src/msteams/` |
| Matrix | - | `src/matrix/` |
| WebChat | - | `src/web/` |

### 8.2 渠道架构

每个渠道都有相似的架构：
- **Monitor**：接收和处理入站消息
- **Bot**：发送消息和处理事件
- **Handlers**：业务逻辑处理

---

## 九、关键数据流

### 9.1 完整消息处理流程

```
1. 用户发送消息到渠道
   │
2. 渠道Adapter接收（如Telegram Bot）
   │
3. Message Handler预处理
   │ - 验证发送者权限
   │ - 提取媒体内容
   │ - 应用组策略
   │
4. Route Resolver解析路由
   │ - 解析Agent ID
   │ - 解析会话Key
   │ - 应用dmPolicy
   │
5. Session Manager获取/创建会话
   │ - 加载会话历史
   │ - 应用会话配置
   │
6. ACP Translator构建Prompt
   │ - 组合System Prompt
   │ - 注入会话上下文
   │ - 应用Thinking级别
   │
7. Pi Agent处理
   │ - 执行推理
   │ - 调用工具
   │ - 生成响应
   │
8. Response处理
   │ - 分块（如果启用）
   │ - 流式输出（如果支持）
   │
9. Outbound发送
   │ - 格式化为渠道格式
   │ - 发送回原渠道
   │
10. 状态更新
    - 保存会话
    - 更新使用统计
```

---

## 十、配置系统

### 10.1 配置类型

| 配置类型 | 文件 | 职责 |
|----------|------|------|
| Gateway配置 | `config.yaml` | Gateway全局配置 |
| 渠道配置 | `channels.*` | 各渠道特定配置 |
| 会话配置 | `sessions.json` | 会话状态存储 |
| Agent配置 | `agents/` | Agent特定设置 |

### 10.2 配置Schema

主要配置Schema定义在：
- `src/config/zod-schema.core.ts` - 核心配置
- `src/config/types.*.ts` - 各模块类型

---

## 十一、总结

OpenClaw是一个设计精良的个人AI助手框架，其架构特点：

1. **分层设计**：清晰的协议层、Agent层、渠道层分离
2. **ACP协议**：标准化的Agent控制协议
3. **模块化Prompt**：灵活可配置的Prompt构建系统
4. **多渠道支持**：统一的抽象接口适配多种消息平台
5. **会话管理**：完善的会话状态和历史管理
6. **工具系统**：丰富的内置工具和可扩展技能系统

这个架构使得OpenClaw能够作为一个强大的本地AI助手框架，支持多种交互方式和使用场景。

---

*文档生成时间: 2026-03-17*
*基于OpenClaw源码分析 (版本: openclaw-2026.3.13-1)*
