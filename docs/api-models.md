# Agent Core API 与模型架构文档

## 概述

Agent Core 提供统一的多模型 API 调用框架，参考 OpenClaw 的 Provider 架构设计。优先支持 MiniMax M2/M2.5，同时兼容 OpenAI、Anthropic、Moonshot/Kimi、Ollama、OpenRouter 等 Provider。

## 模块结构

```
agent_core/
├── brain/                  # Agent 大脑层（人格、历史、配置）
│   ├── __init__.py        # 统一导出入口
│   ├── persona.py         # 角色人格和记忆管理
│   ├── history.py         # 对话历史和 Token 感知管理
│   ├── config.py          # Agent 配置管理
│   ├── tags.py            # 回复表情/动作标签生成
│   ├── persistence.py     # JSON/Markdown 文件持久化
│   └── prompt_builder.py  # 分段式 Prompt 构建
├── api/                    # API 调用核心模块
│   ├── __init__.py        # 统一导出入口
│   ├── message.py         # 消息和角色定义
│   ├── adapter.py         # Provider 和适配器基类
│   ├── types.py           # 请求/响应数据类型
│   ├── client.py          # ChatAgent、ToolExecutor、ProviderManager、AgentRuntime
│   └── adapters/           # 具体适配器实现
│       ├── __init__.py
│       ├── minimax.py     # MiniMax 适配器
│       ├── openai.py      # OpenAI 适配器
│       ├── anthropic.py    # Anthropic 适配器
│       ├── moonshot.py     # Moonshot/Kimi 适配器
│       ├── ollama.py       # Ollama 适配器
│       └── openrouter.py  # OpenRouter 适配器
├── models/                 # 模型配置和目录
│   ├── __init__.py        # 便捷函数导出
│   └── models.py          # 模型目录、配置持久化
└── api.py                 # 向后兼容入口（重导出 api/）
```

## 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      应用层                                   │
│  AgentRuntime / ChatAgent / ProviderManager                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Adapter 层 (adapter.py)                  │
│  BaseAdapter (抽象基类)                                      │
│  └── MiniMaxAdapter / OpenAIAdapter / AnthropicAdapter / ...│
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    类型层 (types.py)                         │
│  ChatCompletionRequest / ChatCompletionResponse / StreamChunk │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    消息层 (message.py)                     │
│  Message / MessageContent / ToolCall / ToolDefinition     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    HTTP 请求 (requests)                      │
└─────────────────────────────────────────────────────────────┘
```

## 核心模块详解

### 1. message.py - 消息和角色定义

定义统一的消息结构、工具调用和函数定义。

```python
from agent_core.api.message import Message, MessageContent, MessageRole, ToolCall, ToolDefinition

# 消息角色
MessageRole.SYSTEM   # 系统提示
MessageRole.USER     # 用户消息
MessageRole.ASSISTANT # 助手回复
MessageRole.TOOL      # 工具调用结果

# 创建消息
msg = Message(role=MessageRole.USER, content="你好")
msg = Message(role=MessageRole.SYSTEM, content="你是一个助手")

# 工具调用
tool_call = ToolCall(id="call_123", name="get_weather", arguments={"city": "北京"})

# 工具定义
tool_def = ToolDefinition(
    name="get_weather",
    description="获取城市天气",
    parameters={
        "type": "object",
        "properties": {"city": {"type": "string", "description": "城市名"}},
        "required": ["city"],
    },
)
```

### 2. adapter.py - Provider 和适配器基类

```python
from agent_core.api.adapter import APIProvider, ModelConfig, BaseAdapter, AdapterRegistry

# Provider 枚举
APIProvider.MINIMAX    # MiniMax
APIProvider.OPENAI     # OpenAI
APIProvider.ANTHROPIC  # Anthropic (Claude)
APIProvider.MOONSHOT   # Moonshot/Kimi
APIProvider.OLLAMA     # Ollama (本地)
APIProvider.OPENROUTER # OpenRouter

# 模型配置
config = ModelConfig(
    name="MiniMax-M2.5",
    provider=APIProvider.MINIMAX,
    api_key="your-key",           # 可选，默认从环境变量读取
    base_url="https://api.minimaxi.com/v1",  # 可选
    max_tokens=4096,
    temperature=0.7,
    supports_function_calling=True,
    supports_streaming=True,
    supports_thinking=True,       # MiniMax M2.5 思考链
)
```

### 3. types.py - 请求和响应类型

```python
from agent_core.api.types import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChoice,
    UsageInfo,
    StreamChunk,
)

# 请求
request = ChatCompletionRequest(
    model="MiniMax-M2.5",
    messages=[msg],
    temperature=0.7,
    max_tokens=4096,
    tools=[tool_def],
    stream=False,
)

# 响应
response = adapter.parse_response(data)
print(response.content)          # 文本
print(response.tool_calls)      # 工具调用
print(response.usage.to_dict())  # Token 使用量
print(response.reasoning)       # 思考过程 (M2.5)

# 流式块
chunk = adapter.parse_stream_chunk(data)
print(chunk.delta)          # 增量文本
print(chunk.is_complete)    # 是否完成
```

### 4. adapters/ - 适配器实现

| 文件 | Provider | 特点 |
|------|----------|------|
| `minimax.py` | MiniMax | 支持 `reasoning_split` |
| `openai.py` | OpenAI | 标准格式 |
| `anthropic.py` | Anthropic | Claude 格式转换 |
| `moonshot.py` | Moonshot/Kimi | OpenAI 兼容 |
| `ollama.py` | Ollama | 本地模型 |
| `openrouter.py` | OpenRouter | 聚合网关 |

每个适配器继承 `BaseAdapter`，实现：

```python
class MiniMaxAdapter(BaseAdapter):
    provider = APIProvider.MINIMAX

    def build_headers(self, config: ModelConfig) -> dict:
        return {"Authorization": f"Bearer {config.resolved_api_key}"}

    def build_request(self, request: ChatCompletionRequest, config: ModelConfig) -> dict:
        data = request.to_dict()
        if config.supports_thinking:
            data["reasoning_split"] = True
        return data

    def parse_response(self, response_data: dict) -> ChatCompletionResponse:
        return ChatCompletionResponse.from_dict(response_data)
```

### 5. client.py - 核心客户端

```python
from agent_core.api.client import ChatAgent, ToolExecutor, ProviderManager, AgentRuntime

# ChatAgent - 统一 API 客户端
config = ModelConfig(name="MiniMax-M2.5", provider=APIProvider.MINIMAX)
config.api_key = "your-key"

agent = ChatAgent(config)
response = agent.chat([Message(role=MessageRole.USER, content="你好")])
print(response.content)

# ToolExecutor - 工具调用执行器
def get_weather(city: str):
    return f"{city}晴天"

executor = ToolExecutor(tools={"get_weather": get_weather})
if response.tool_calls:
    results = executor.execute_all(response.tool_calls)

# ProviderManager - 多 Provider 管理
manager = ProviderManager.from_env()  # 从环境变量加载
agent = manager.get_agent()          # 优先 MiniMax
agent = manager.get_agent(APIProvider.OPENAI)  # 指定

# AgentRuntime - 完整运行时
runtime = AgentRuntime(agent=agent, tools={"get_weather": get_weather}, max_turns=10)
result = runtime.run(messages, system_prompt="你是一个助手")
```

### 6. models.py - 模型配置和目录

```python
from agent_core.models import (
    MINIMAX_MODELS,
    OPENAI_MODELS,
    ANTHROPIC_MODELS,
    ProviderConfig,
    ModelsStorage,
    setup_provider,
    get_model_catalog,
)

# 查询模型
model = MINIMAX_MODELS.find_model("MiniMax-M2.5")
print(model.name)           # "MiniMax M2.5"
print(model.context_window)  # 1000000
print(model.cost.input)     # 0.3 (每百万 token)

# 配置持久化
setup_provider("minimax", "your-key", "./config")

storage = ModelsStorage("./config")
config = storage.load()
storage.set_default("minimax", "MiniMax-M2.5")
```

---

## 统一导入方式

```python
# 推荐：从 api.py 统一导入
from agent_core.api import (
    ChatAgent,
    ModelConfig,
    APIProvider,
    ApiMessage,         # Message 的别名
    MessageRole,
    ToolCall,
    ToolDefinition,
    ToolExecutor,
    ProviderManager,
    AgentRuntime,
)

# 或者：从具体模块导入（更清晰）
from agent_core.api.message import Message, MessageRole, ToolCall
from agent_core.api.adapter import ModelConfig, APIProvider
from agent_core.api.client import ChatAgent, ToolExecutor
from agent_core.models import MINIMAX_MODELS, setup_provider
```

---

## 完整示例

### 基础对话

```python
from agent_core.api import ChatAgent, ModelConfig, APIProvider, ApiMessage, MessageRole

config = ModelConfig(name="MiniMax-M2.5", provider=APIProvider.MINIMAX)
config.api_key = "your-key"

agent = ChatAgent(config)
response = agent.chat([
    ApiMessage(role=MessageRole.USER, content="你好")
])
print(response.content)
```

### 带工具调用的对话

```python
from agent_core.api import ChatAgent, ToolDefinition, ToolExecutor

tools = [ToolDefinition(
    name="get_weather",
    description="获取天气",
    parameters={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
)]

def get_weather(city: str):
    return f"{city}晴天"

executor = ToolExecutor({"get_weather": get_weather})

response = agent.chat(messages, tools=tools)
if response.tool_calls:
    results = executor.execute_all(response.tool_calls)
```

### 配置管理

```python
from agent_core.models import setup_provider, ModelsStorage, print_models_table

# 一键配置
setup_provider("minimax", "your-key", "./config")

# 查看模型
print_models_table("minimax")

# 加载配置
storage = ModelsStorage("./config")
config = storage.load()
```

---

## OpenClaw 参考

本设计参考了 OpenClaw 的模型配置架构：

| 特性 | OpenClaw | Agent Core |
|------|----------|------------|
| 语言 | TypeScript | Python |
| 消息格式 | TypeScript 类型 | Python dataclass |
| Provider 定义 | `models-config.providers.static.ts` | `models/` + `api/adapters/` |
| 配置持久化 | `models.json` | `config/models.json` |
| API 传输 | Pi (内部) | `requests` 库 |
| Auth | Secret profiles | 环境变量/配置文件 |

### 关键文件对应

| OpenClaw | Agent Core |
|-----------|------------|
| `src/agents/models-config.providers.static.ts` | `models/models.py` (MODEL_CATALOGS) |
| `src/agents/models-config.ts` | `models/models.py` (ModelsStorage) |
| `src/agents/models-config.providers.ts` | `api/adapter.py` (APIProvider) |
| Provider adapters | `api/adapters/*.py` |

---

## 错误处理

```python
import requests

try:
    response = agent.chat(messages)
except requests.HTTPError as e:
    if e.response.status_code == 401:
        print("API Key 无效")
    elif e.response.status_code == 429:
        print("请求频率限制")
    elif e.response.status_code == 400:
        print("请求参数错误")
except requests.Timeout:
    print("请求超时")
```

---

## 环境变量

| 变量 | 说明 |
|------|------|
| `MINIMAX_API_KEY` | MiniMax API Key |
| `OPENAI_API_KEY` | OpenAI API Key |
| `ANTHROPIC_API_KEY` | Anthropic API Key |
| `MOONSHOT_API_KEY` | Moonshot/Kimi API Key |
| `OPENROUTER_API_KEY` | OpenRouter API Key |
