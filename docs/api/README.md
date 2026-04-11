# API 模块 - 多 Provider 聊天调用

`agent_core.api` 提供统一的聊天请求、响应、工具调用和 Provider 适配器接口。它不理解 Brain 记忆，也不负责 Session 生命周期。

## 职责边界

- 负责将统一 `Message`、`ToolDefinition`、`ChatCompletionRequest` 转换成各 Provider 的 HTTP 请求。
- 负责解析同步响应和流式块。
- 负责工具调用执行循环的基础封装。
- 不负责 Prompt 内容、人格状态、会话归档或 UI 标签。

## 核心对象

公共入口：`from agent_core.api import ...`

- `MessageRole`、`MessageContent`、`Message`：统一消息结构。
- `ToolCall`、`ToolDefinition`：工具调用结果与工具 schema。
- `APIProvider`：`minimax`、`openai`、`anthropic`、`moonshot`、`ollama`、`openrouter`。
- `ModelConfig`：单次 API 客户端配置。
- `BaseAdapter`、`AdapterRegistry`：Provider 适配器基类和注册表。
- `ChatCompletionRequest`、`ChatCompletionResponse`、`StreamChunk`、`UsageInfo`：请求和响应类型。
- `ChatAgent`：同步聊天客户端。
- `ToolExecutor`：本地函数工具执行器。
- `ProviderManager`：从环境变量或配置集合选择 Provider。
- `AgentRuntime`：多轮工具调用运行时。

## 数据流/存储

API 层本身不写业务数据。请求流程是：

```text
Message list
  -> ChatCompletionRequest
  -> ChatAgent
  -> AdapterRegistry 获取 BaseAdapter
  -> Provider HTTP API
  -> ChatCompletionResponse 或 StreamChunk
```

## 典型用法

```python
from agent_core.api import APIProvider, ChatAgent, Message, MessageRole, ModelConfig

config = ModelConfig(
    name="MiniMax-M2.5",
    provider=APIProvider.MINIMAX,
    supports_thinking=True,
)

agent = ChatAgent(config=config)
response = agent.chat([
    Message(role=MessageRole.USER, content="你好"),
])

print(response.content)
print(response.usage.total_tokens)
```

工具调用：

```python
from agent_core.api import ToolCall, ToolDefinition, ToolExecutor

tools = [
    ToolDefinition(
        name="get_weather",
        description="获取城市天气",
        parameters={
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    )
]

executor = ToolExecutor({"get_weather": lambda city: f"{city} 晴"})
result = executor.execute(ToolCall(id="call_1", name="get_weather", arguments={"city": "上海"}))
```

## 注意事项

- `ChatAgent.chat(..., stream=True)` 返回 `StreamChunk` 生成器，而非完整 `ChatCompletionResponse`。
- `ModelConfig.resolved_api_key` 会按 Provider 读取对应环境变量。
- API 层和 Brain 层各自都有 `MessageRole`/`Message` 类型；需要传入 API 客户端时使用 `agent_core.api.Message`。
