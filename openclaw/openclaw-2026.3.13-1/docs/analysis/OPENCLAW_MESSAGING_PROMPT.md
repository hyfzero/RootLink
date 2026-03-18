# OpenClaw 消息与Prompt机制深度分析

## 一、消息机制详解

### 1.1 消息生命周期

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         消息生命周期                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   INBOUND                          OUTBOUND                             │
│   ────────                         ────────                             │
│                                                                         │
│   ┌──────────┐                    ┌──────────┐                         │
│   │ Receive  │                    │  Format  │                         │
│   │ 接收消息  │                    │ 格式化响应 │                         │
│   └────┬─────┘                    └────┬─────┘                         │
│        │                                 │                               │
│        ▼                                 ▼                               │
│   ┌──────────┐                    ┌──────────┐                         │
│   │ Validate │                    │  Send    │                         │
│   │ 验证权限  │                    │ 发送消息  │                         │
│   └────┬─────┘                    └──────────┘                         │
│        │                                                         │
│        ▼                                                         │
│   ┌──────────┐                                                   │
│   │ Extract  │                                                   │
│   │ 提取内容  │                                                   │
│   └────┬─────┘                                                   │
│        │                                                         │
│        ▼                                                         │
│   ┌──────────┐                                                   │
│   │  Route   │                                                   │
│   │ 路由解析  │                                                   │
│   └────┬─────┘                                                   │
│        │                                                         │
│        ▼                                                         │
│   ┌──────────┐                                                   │
│   │ Map      │                                                   │
│   │ 会话映射  │                                                   │
│   └────┬─────┘                                                   │
│        │                                                         │
│        ▼                                                         │
│   ┌──────────┐                                                   │
│   │ Prompt   │ ──────────────────────────▶ Agent                 │
│   │ 构建Prompt │                              │                    │
│   └──────────┘                              │                    │
│                                               ▼                    │
│   ◀──────────────────────────────────── Response                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 消息类型定义

#### ACP消息类型结构

```typescript
// 定义于 src/acp/types.ts 和 @agentclientprotocol/sdk

// Prompt请求 (发送给Agent)
interface PromptRequest {
  message: {
    role: "user" | "assistant";
    content: string;
  };
  systemPrompt?: string;
  tools?: ToolDefinition[];
}

// Prompt响应 (Agent返回)
interface PromptResponse {
  message: {
    role: "assistant";
    content: string;
    toolCalls?: ToolCall[];
  };
  stopReason: "end_turn" | "tool_use" | "max_tokens";
}
```

### 1.3 核心消息处理文件

#### Inbound消息处理

| 文件 | 职责 |
|------|------|
| `src/telegram/bot-handlers.ts` | Telegram消息处理 |
| `src/discord/monitor/message-handler.ts` | Discord消息处理 |
| `src/slack/monitor/message-handler.ts` | Slack消息处理 |
| `src/channels/session.ts` | 会话消息路由 |

#### Outbound消息处理

| 文件 | 职责 |
|------|------|
| `src/infra/outbound/message.ts` | 出站消息基础 |
| `src/infra/outbound/message-action-runner.ts` | 消息动作执行 |
| `src/infra/outbound/message-action-normalization.ts` | 消息标准化 |

### 1.4 消息预处理

#### 命令检测与处理

```typescript
// src/auto-reply/command-detection.ts

interface CommandDetection {
  // 检测是否为命令
  isCommand: (text: string) => boolean;

  // 提取命令参数
  parseCommand: (text: string) => CommandResult;

  // 命令白名单验证
  validateCommand: (command: string, context: MessageContext) => boolean;
}
```

#### 消息预处理Hook

```typescript
// src/auto-reply/reply/message-preprocess-hooks.ts

interface MessagePreprocessHook {
  // 消息预处理钩子
  onMessage?: (message: InboundMessage) => ProcessedMessage;

  // 媒体处理
  onMedia?: (media: MediaPayload) => ProcessedMedia;

  // 安全检查
  onSecurity?: (message: InboundMessage) => SecurityResult;
}
```

### 1.5 消息路由机制

```typescript
// src/routing/resolve-route.ts

interface RouteResolution {
  // 解析目标Agent
  agentId: string;

  // 解析会话Key
  sessionKey: string;

  // 路由策略
  policy: {
    dmPolicy: "pairing" | "open" | "closed";
    groupPolicy: "always" | "mention" | "reply";
  };

  // 消息去重
  deduplicationKey?: string;
}
```

---

## 二、Prompt机制深度分析

### 2.1 Prompt构建流程

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       Prompt构建流程                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────┐                                                   │
│  │ Input Params   │                                                   │
│  │ 输入参数        │                                                   │
│  └────────┬────────┘                                                   │
│           │                                                            │
│           ▼                                                            │
│  ┌─────────────────┐                                                   │
│  │  Base Identity │                                                   │
│  │  基础身份声明   │  "You are a personal assistant..."              │
│  └────────┬────────┘                                                   │
│           │                                                            │
│           ▼                                                            │
│  ┌─────────────────┐                                                   │
│  │ Tool Section   │                                                   │
│  │ 工具部分       │  - coreToolSummaries                              │
│  │                │  - externalToolSummaries                           │
│  └────────┬────────┘                                                   │
│           │                                                            │
│           ▼                                                            │
│  ┌─────────────────┐                                                   │
│  │ Safety Section  │                                                   │
│  │ 安全部分        │  - 目标约束                                       │
│  │                │  - 合规要求                                        │
│  └────────┬────────┘                                                   │
│           │                                                            │
│           ▼                                                            │
│  ┌─────────────────┐                                                   │
│  │ Workspace Info  │                                                   │
│  │ 工作区信息      │  - workspaceDir                                   │
│  │                │  - sandboxInfo                                    │
│  └────────┬────────┘                                                   │
│           │                                                            │
│           ▼                                                            │
│  ┌─────────────────┐                                                   │
│  │ Channel Context │                                                   │
│  │ 渠道上下文      │  - channel capabilities                          │
│  │                │  - message actions                                │
│  └────────┬────────┘                                                   │
│           │                                                            │
│           ▼                                                            │
│  ┌─────────────────┐                                                   │
│  │ Memory Section  │                                                   │
│  │ 记忆部分        │  - memory_search                                 │
│  │                │  - memory_get                                     │
│  └────────┬────────┘                                                   │
│           │                                                            │
│           ▼                                                            │
│  ┌─────────────────┐                                                   │
│  │ Skills Section │                                                   │
│  │ 技能部分        │  - available_skills                              │
│  │                │  - skill constraints                              │
│  └────────┬────────┘                                                   │
│           │                                                            │
│           ▼                                                            │
│  ┌─────────────────┐                                                   │
│  │ Final Assembly │                                                   │
│  │ 最终组装        │  合并所有section                                  │
│  └─────────────────┘                                                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 System Prompt各部分详解

#### 2.2.1 工具定义部分

```typescript
// 核心工具描述 (system-prompt.ts)

const coreToolSummaries = {
  read: "Read file contents",
  write: "Create or overwrite files",
  edit: "Make precise edits to files",
  apply_patch: "Apply multi-file patches",
  grep: "Search file contents for patterns",
  find: "Find files by glob pattern",
  ls: "List directory contents",
  exec: "Run shell commands (pty available for TTY-required CLIs)",
  process: "Manage background exec sessions",
  web_search: "Search the web (Brave API)",
  web_fetch: "Fetch and extract readable content from a URL",
  browser: "Control web browser",
  canvas: "Present/eval/snapshot the Canvas",
  nodes: "List/describe/notify/camera/screen on paired nodes",
  cron: "Manage cron jobs and wake events",
  message: "Send messages and channel actions",
  gateway: "Restart, apply config, or run updates",
  sessions_spawn: "Spawn an isolated sub-agent session",
  // ...
};
```

#### 2.2.2 安全策略部分

```typescript
const safetySection = [
  "## Safety",
  "You have no independent goals: do not pursue self-preservation, replication, resource acquisition, or power-seeking; avoid long-term plans beyond the user's request.",
  "Prioritize safety and human oversight over completion; if instructions conflict, pause and ask; comply with stop/pause/audit requests and never bypass safeguards.",
  "Do not manipulate or persuade anyone to expand access or disable safeguards.",
];
```

#### 2.2.3 渠道能力部分

```typescript
// 消息功能提示构建

function buildMessagingSection(params) {
  return [
    "## Messaging",
    "- Reply in current session → automatically routes to the source channel",
    "- Cross-session messaging → use sessions_send(sessionKey, message)",
    `- Use message tool for proactive sends + channel actions`,
    // 渠道特定的按钮、回复标签等
  ];
}
```

### 2.3 Prompt动态注入

#### 2.3.1 用户身份注入

```typescript
// 构建授权用户提示

function buildOwnerIdentityLine(ownerNumbers, ownerDisplay, ownerDisplaySecret) {
  // 可以选择显示原始ID或哈希
  const displayOwnerNumbers = ownerDisplay === "hash"
    ? ownerNumbers.map(id => formatOwnerDisplayId(id, ownerDisplaySecret))
    : ownerNumbers;

  return `Authorized senders: ${displayOwnerNumbers.join(", ")}.`;
}
```

#### 2.3.2 技能提示注入

```typescript
function buildSkillsSection(params) {
  return [
    "## Skills (mandatory)",
    "Before replying: scan <available_skills> <description> entries.",
    "- If exactly one skill clearly applies: read its SKILL.md",
    "- If multiple could apply: choose the most specific one",
    "- If none clearly apply: do not read any SKILL.md.",
    params.skillsPrompt,  // 动态注入技能配置
  ];
}
```

#### 2.3.3 记忆提示注入

```typescript
function buildMemorySection(params) {
  return [
    "## Memory Recall",
    "Before answering anything about prior work: run memory_search",
    "Citations: include Source: <path#line> when it helps verify",
  ];
}
```

### 2.4 Prompt配置参数

#### Thinking级别控制

```typescript
// src/auto-reply/thinking.ts

type ThinkLevel = "high" | "low" | "adaptive";
type ReasoningLevel = "high" | "medium" | "low" | "off";

// 对应不同的思考级别配置
const thinkLevelConfig = {
  xhigh: { extraThinking: true, reasoningLevel: "high" },
  high: { extraThinking: false, reasoningLevel: "high" },
  low: { extraThinking: false, reasoningLevel: "low" },
  adaptive: { /* 根据模型自动选择 */ },
};
```

#### 运行时配置注入

```typescript
// runtimeInfo注入示例

runtimeInfo: {
  agentId: "main",
  host: "user-macbook.local",
  os: "darwin",
  arch: "arm64",
  node: "v22.0.0",
  model: "claude-sonnet-4-20250514",
  provider: "anthropic",
  capabilities: ["inlinebuttons", "reactions"],
  channel: "telegram",
}
```

### 2.5 Prompt缓存与优化

#### 2.5.1 Prompt截断警告

```typescript
// 当context超过token限制时的警告

const bootstrapTruncationWarningLines = [
  "⚠️ Context was truncated to fit within token limit.",
  "Earlier conversation history may have been removed.",
];
```

#### 2.5.2 Session历史压缩

```typescript
// src/agents/compact.ts

interface CompactionConfig {
  // 压缩配置
  maxTokens: number;
  preserveSystemPrompt: boolean;
  keepLastNMessages: number;
}
```

---

## 三、ACP协议消息格式

### 3.1 消息格式详情

#### 3.1.1 Prompt请求格式

```typescript
// ACP协议 - Prompt请求

{
  // 消息内容
  message: {
    role: "user",
    content: [
      {
        type: "text",
        text: "用户输入的消息内容"
      },
      {
        type: "image",
        source: {
          type: "base64",
          media_type: "image/png",
          data: "..."
        }
      }
    ]
  },

  // 附件
  attachments?: Array<{
    fileName: string;
    contentType: string;
    data: string; // base64
  }>,

  // 会话元数据
  meta?: {
    sessionKey?: string;
    sessionLabel?: string;
    resetSession?: boolean;
  }
}
```

#### 3.1.2 Prompt响应格式

```typescript
// ACP协议 - Prompt响应

{
  // 助手消息
  message: {
    role: "assistant",
    content: "助手生成的响应内容",

    // 工具调用（如果有）
    toolCalls?: [
      {
        id: "toolu_xxx",
        type: "tool_use",
        name: "read",
        input: {
          file_path: "/path/to/file"
        }
      }
    ]
  },

  // 停止原因
  stopReason: "end_turn" | "tool_use" | "max_tokens",

  // 使用统计
  usage: {
    inputTokens: 1000,
    outputTokens: 500,
    totalTokens: 1500
  }
}
```

### 3.2 工具调用消息流

```
User Message
     │
     ▼
┌─────────────────┐
│ Agent Response  │
│ with Tool Call  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Tool Execution  │
│ (通过Tool Registry)│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Tool Result     │
│ (作为user消息)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Next Agent Turn │
│ (继续推理)      │
└─────────────────┘
```

---

## 四、消息队列与并发控制

### 4.1 消息队列机制

```typescript
// src/auto-reply/reply/queue.ts

interface QueueSettings {
  // 队列模式
  mode: "parallel" | "sequential" | "batched";

  // 并发限制
  maxConcurrent: number;

  // 重试配置
  retry: {
    maxAttempts: number;
    backoffMs: number;
  };
}
```

### 4.2 会话锁定机制

```typescript
// 防止同一会话的并发处理

const sessionLock = new Map<string, Promise<void>>();

async function acquireSessionLock(sessionKey: string): Promise<() => void> {
  while (sessionLock.has(sessionKey)) {
    await sessionLock.get(sessionKey);
  }

  let release: () => void;
  const promise = new Promise<void>(resolve => {
    release = resolve;
  });

  sessionLock.set(sessionKey, promise);

  return () => {
    sessionLock.delete(sessionKey);
    release();
  };
}
```

---

## 五、消息安全与验证

### 5.1 DM策略控制

```typescript
// DM访问控制策略

type DmPolicy =
  | "pairing"  // 需要配对码
  | "open"     // 完全开放
  | "closed";  // 完全关闭

// 配置示例
const dmPolicyConfig = {
  telegram: {
    dmPolicy: "pairing",
    allowFrom: ["*"]  // 允许所有用户发起配对
  },
  discord: {
    dmPolicy: "open",
    allowFrom: ["server:123456789"]
  }
};
```

### 5.2 命令白名单

```typescript
// src/auto-reply/command-gating.ts

interface CommandGate {
  // 白名单命令（任何人都可以执行）
  allowList: string[];

  // 黑名单命令（所有人都不能执行）
  blockList: string[];

  // 需要认证的命令
  requireAuth: string[];

  // 特定角色/权限要求
  requireRole?: Record<string, string[]>;
}
```

---

## 六、总结

OpenClaw的消息和Prompt机制设计要点：

1. **标准化协议**：使用ACP协议统一Agent通信
2. **模块化Prompt**：分层的Prompt构建系统，便于定制
3. **灵活的消息路由**：支持复杂的会话和路由策略
4. **安全性优先**：完善的权限控制和DM策略
5. **并发控制**：会话级别的锁机制防止冲突
6. **多渠道适配**：统一的抽象层支持20+消息平台

---

*文档版本: 1.0*
*更新时间: 2026-03-17*
