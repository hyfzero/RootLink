# Providers And Models - 模型目录与配置

`agent_core.models` 维护内置模型目录和统一配置目录下的 `models.json` 持久化；`agent_core.api.adapter.ModelConfig` 则是运行时调用 API 的配置对象。

## 职责边界

- Models 模块负责可选模型目录、Provider 配置、默认 Provider 和默认模型。
- API Adapter 模块负责实际发送请求时的 `ModelConfig`、Header 和请求体。
- Models 不直接调用 LLM；API 不负责保存 `models.json`。

## 核心对象

公共入口：`from agent_core.models import ...`

- `ModelCost`、`ModelInfo`、`ProviderCatalog`：内置模型目录数据结构。
- `ProviderConfig`：Provider base URL、API key、API 类型和额外 headers。
- `ModelsJsonConfig`：`models.json` 的整体结构。
- `ModelsStorage`：读取、写入、添加 Provider、设置默认 Provider。
- `get_model_catalog()`、`get_all_providers()`：查询内置目录。
- `setup_provider()`：快速写入 Provider 配置。
- `list_available_models()`、`print_models_table()`：查看模型目录。
- 内置目录：`MINIMAX_MODELS`、`DEEPSEEK_MODELS`、`QWEN_MODELS`、`OPENAI_MODELS`、`GLM_MODELS`、`ANTHROPIC_MODELS`、`MOONSHOT_MODELS`、`OLLAMA_MODELS`、`OPENROUTER_MODELS`。

API 运行时 Provider：

- `APIProvider`
- `ModelConfig`
- `MiniMaxAdapter`、`OpenAIAdapter`、`AnthropicAdapter`、`MoonshotAdapter`、`OllamaAdapter`、`OpenRouterAdapter`
- DeepSeek、Qwen、OpenAI 和 GLM 都复用 OpenAI-compatible 请求格式，由 `OpenAIAdapter` 承接。

## 数据流/存储

```text
PathResolver.get_config_dir()/models.json
  -> ModelsStorage.load()
  -> ProviderConfig / default provider
  -> 转换或手动创建 ModelConfig
  -> ChatAgent
```

环境变量也可直接供 `ProviderManager.from_env()` 使用：

- `MINIMAX_API_KEY`
- `DEEPSEEK_API_KEY`
- `DASHSCOPE_API_KEY`
- `GLM_API_KEY`
- `ANTHROPIC_API_KEY`
- `MOONSHOT_API_KEY`
- `OPENROUTER_API_KEY`

## 典型用法

```python
from agent_core.models import ModelsStorage, setup_provider

setup_provider("minimax", "your-api-key")

storage = ModelsStorage()
models_config = storage.load()
storage.set_default("minimax", "MiniMax-M2.5")

print(models_config.default_provider)
```

内置 GUI 当前暴露的 Provider 和默认模型：

| Provider | 默认模型 | 默认 base URL |
|----------|----------|---------------|
| `minimax` | `MiniMax-M2.5` | `https://api.minimaxi.com/v1` |
| `deepseek` | `deepseek-v4-flash` | `https://api.deepseek.com` |
| `qwen` | `qwen3.6-flash` | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `glm` | `glm-5.1` | `https://open.bigmodel.cn/api/paas/v4` |

直接从环境变量创建 ProviderManager：

```python
from agent_core.api import APIProvider, ProviderManager

manager = ProviderManager.from_env()
agent = manager.get_agent(APIProvider.MINIMAX)
```

## 注意事项

- `setup_provider()` 写入的是统一配置目录下的 `models.json`，不是 `data/{brain_id}`。
- `ModelConfig` 的 `supports_thinking=True` 会让 MiniMax 适配器带上 `reasoning_split`。
- `create_provider_from_catalog()` 存在于 `agent_core.models.models` 子模块，未从 `agent_core.models` 顶层导出。
