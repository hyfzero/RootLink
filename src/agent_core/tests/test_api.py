#!/usr/bin/env python3
"""API 模块测试脚本。"""

import os
import sys

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agent_core.api import ChatAgent, ModelConfig, APIProvider, MessageRole, ToolDefinition
from agent_core import ApiMessage


def get_api_key_and_provider():
    """从配置文件或环境变量获取 API key 和 provider。"""
    from agent_core.models import ModelsStorage
    storage = ModelsStorage("./config")
    config_data = storage.load()

    # 优先使用 MiniMax 配置
    if "minimax" in config_data.providers:
        return config_data.providers["minimax"].api_key, APIProvider.MINIMAX, "MiniMax-M2.5"

    # 尝试 OpenAI
    if "openai" in config_data.providers:
        return config_data.providers["openai"].api_key, APIProvider.OPENAI, "gpt-4o-mini"

    # 回退到环境变量
    if os.getenv("MINIMAX_API_KEY"):
        return os.getenv("MINIMAX_API_KEY"), APIProvider.MINIMAX, "MiniMax-M2.5"
    if os.getenv("OPENAI_API_KEY"):
        return os.getenv("OPENAI_API_KEY"), APIProvider.OPENAI, "gpt-4o-mini"

    return None, None, None


def test_minimax_basic():
    """测试 MiniMax 基础对话。"""
    print("\n=== 测试 MiniMax 基础对话 ===")

    api_key, provider, model_name = get_api_key_and_provider()
    if not api_key:
        print("SKIP: No API key found")
        return

    config = ModelConfig(
        name=model_name,
        provider=provider,
        supports_thinking=True,
    )
    config.api_key = api_key

    agent = ChatAgent(config)
    response = agent.chat(
        messages=[ApiMessage(role=MessageRole.USER, content="你好，请用一句话介绍自己。")],
        stream=False,
    )

    print(f"Response: {response.content}")
    print(f"Usage: {response.usage.to_dict()}")
    print(f"Reasoning: {response.reasoning[:100] if response.reasoning else 'None'}...")


def test_openai_basic():
    """测试 OpenAI 基础对话。"""
    print("\n=== 测试 OpenAI 基础对话 ===")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("SKIP: OPENAI_API_KEY not set")
        return

    config = ModelConfig(
        name="gpt-4o-mini",
        provider=APIProvider.OPENAI,
    )
    config.api_key = api_key

    agent = ChatAgent(config)
    response = agent.chat(
        messages=[ApiMessage(role=MessageRole.USER, content="你好，请用一句话介绍自己。")],
        stream=False,
    )

    print(f"Response: {response.content}")
    print(f"Usage: {response.usage.to_dict()}")


def test_tool_calling():
    """测试函数调用。"""
    print("\n=== 测试函数调用 ===")

    api_key, provider, model_name = get_api_key_and_provider()
    if not api_key:
        print("SKIP: No API key found")
        return

    config = ModelConfig(
        name=model_name,
        provider=provider,
        supports_thinking=True,
    )
    config.api_key = api_key

    # 定义工具
    tools = [
        ToolDefinition(
            name="get_weather",
            description="获取指定城市的天气信息",
            parameters={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称",
                    }
                },
                "required": ["city"],
            },
        )
    ]

    agent = ChatAgent(config)

    # 发送需要调用工具的请求
    response = agent.chat(
        messages=[
            ApiMessage(
                role=MessageRole.USER,
                content="北京今天天气怎么样？",
            )
        ],
        tools=tools,
        stream=False,
    )

    print(f"Response: {response.content}")
    if response.tool_calls:
        print(f"Tool calls: {[tc.name for tc in response.tool_calls]}")
        for tc in response.tool_calls:
            print(f"  - {tc.name}: {tc.arguments}")


def test_streaming():
    """测试流式响应。"""
    print("\n=== 测试流式响应 ===")

    # 尝试从配置加载
    from agent_core.models import ModelsStorage
    storage = ModelsStorage("./config")
    config_data = storage.load()

    api_key = None
    if "minimax" in config_data.providers:
        api_key = config_data.providers["minimax"].api_key

    if not api_key:
        api_key = os.getenv("MINIMAX_API_KEY")

    if not api_key:
        print("SKIP: No API key found (set MINIMAX_API_KEY or configure in config/models.json)")
        return

    config = ModelConfig(
        name="MiniMax-M2.5",
        provider=APIProvider.MINIMAX,
        supports_thinking=True,
    )
    config.api_key = api_key

    agent = ChatAgent(config)

    print("Streaming response: ", end="", flush=True)
    chunk = agent.chat(
        messages=[ApiMessage(role=MessageRole.USER, content="给我讲一个笑话。")],
        stream=True,
    )

    # 如果返回的是 StreamChunk
    if hasattr(chunk, "delta"):
        print(f"\nComplete: {chunk.is_complete}, Reasoning: {chunk.reasoning[:50] if chunk.reasoning else None}...")


def test_provider_manager():
    """测试 Provider 管理器。"""
    print("\n=== 测试 Provider 管理器 ===")

    from agent_core.api import ProviderManager

    manager = ProviderManager.from_env()

    if not manager.providers:
        print("SKIP: No providers configured via environment")
        return

    print(f"Configured providers: {[p.provider.value for p in manager.providers]}")

    try:
        agent = manager.get_agent()
        print(f"Selected agent provider: {agent.provider.value}")

        response = agent.chat(
            messages=[ApiMessage(role=MessageRole.USER, content="Hi")],
            stream=False,
        )
        print(f"Response: {response.content[:100]}...")
    except ValueError as e:
        print(f"Error: {e}")


def test_models_module():
    """测试 models 模块。"""
    print("\n=== 测试 Models 模块 ===")

    from agent_core.models import (
        MINIMAX_MODELS,
        get_all_providers,
        print_models_table,
        ModelsStorage,
        setup_provider,
    )

    # 列出所有 provider
    providers = get_all_providers()
    print(f"可用 Providers: {providers}")

    # 列出 MiniMax 模型
    print(f"\nMiniMax 模型数量: {len(MINIMAX_MODELS.models)}")
    for m in MINIMAX_MODELS.models[:2]:
        print(f"  - {m.id}: {m.name} (context: {m.context_window})")

    # 测试存储
    storage = ModelsStorage("./config")
    config = storage.load()
    print(f"\n当前配置的 Providers: {list(config.providers.keys())}")

    # 打印表格
    print("\n--- 模型表格 (MiniMax) ---")
    print_models_table("minimax")


def test_message_format():
    """测试消息格式转换。"""
    print("\n=== 测试消息格式 ===")

    # 测试 API Message
    msg = ApiMessage(role=MessageRole.USER, content="Hello")
    print(f"API Message dict: {msg.to_dict()}")

    # 测试 system message
    system_msg = ApiMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant.")
    print(f"System Message dict: {system_msg.to_dict()}")


if __name__ == "__main__":
    print("Agent Core API 测试脚本")
    print(f"Python: {sys.version}")

    test_models_module()
    test_message_format()
    test_provider_manager()
    test_minimax_basic()
    test_openai_basic()
    test_tool_calling()
    test_streaming()

    print("\n=== 所有测试完成 ===")
