#!/usr/bin/env python3
"""测试每日总结功能"""

import os
import sys
import asyncio
from pathlib import Path

# Windows 终端编码处理
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

_script_dir = Path(__file__).parent.resolve()
_project_root = _script_dir.parent.parent.parent.resolve()
sys.path.insert(0, str(_project_root / "src"))

from agent_core.session import SessionManager, SessionConfig, BrainRegistry
from agent_core.session.path_resolver import PathResolver
from agent_core.api import ChatAgent
from agent_core.api.adapter import ModelConfig, APIProvider
from agent_core.models import ModelsStorage
from agent_core.brain import TagGenerator


def load_model_from_config(config_dir: str = "./config") -> ModelConfig:
    """从 config/models.json 加载模型配置"""
    storage = ModelsStorage(config_dir)
    config = storage.load()
    provider_name = config.default_provider or "minimax"
    from agent_core.models import ProviderConfig
    provider_config: ProviderConfig = config.providers.get(provider_name)
    if not provider_config:
        raise ValueError(f"Provider '{provider_name}' not found in config")

    from agent_core.models import get_model_catalog
    catalog = get_model_catalog(provider_name)
    model_name = config.default_model or "MiniMax-M2.5"
    model_info = catalog.find_model(model_name) if catalog else None

    return ModelConfig(
        name=model_name,
        provider=APIProvider.MINIMAX,
        api_key=provider_config.api_key,
        base_url=provider_config.base_url,
        max_tokens=model_info.max_tokens if model_info else 8192,
        temperature=0.7,
        supports_thinking=True,
        supports_function_calling=True,
    )


async def test_daily_summary():
    """测试每日总结"""
    print("=" * 60)
    print("测试每日总结功能")
    print("=" * 60)

    # 初始化
    config_dir = "./config"
    brain_id = "amadues"
    brain_base_path = os.path.join(_project_root, "data")

    # 加载模型配置
    print("\n[1] 加载模型配置...")
    model_config = load_model_from_config(config_dir)
    print(f"  - Model: {model_config.name}")

    # 创建 ChatAgent
    print("\n[2] 创建 ChatAgent...")
    chat_agent = ChatAgent(config=model_config)

    # 创建 BrainRegistry
    print("\n[3] 初始化 Brain...")
    brain_registry = BrainRegistry(Path(brain_base_path))
    existing_brains = brain_registry.load_all()
    if brain_id in existing_brains:
        print(f"  - 已加载 Brain: {brain_id}")
        brain_registry.switch(brain_id)
    else:
        print(f"  - Brain '{brain_id}' 不存在")
        return

    # 创建 SessionManager
    print("\n[4] 创建 SessionManager...")
    session_config = SessionConfig(
        model_config=model_config,
        max_messages_per_day=500,
        max_tokens_per_day=50000,
        min_messages_for_summary=4,
    )
    session_manager = SessionManager(
        config=session_config,
        brain_registry=brain_registry,
        chat_agent=chat_agent,
        tag_generator=TagGenerator(),
    )
    print(f"  - SessionManager 创建成功")

    # 发送几条消息
    print("\n[5] 发送测试消息...")
    messages = [
        "你好，今天天气真好",
        "我周末想去公园散步",
        "有什么好看的电影推荐吗？",
        "周末打算吃火锅"
    ]

    for i, msg in enumerate(messages, 1):
        print(f"\n  消息 {i}/4: {msg}")
        response = await session_manager.send_message(msg)
        print(f"  助手回复: {response['content'][:50]}...")
        print(f"  标签: emotion={response['tag'].emotion}", flush=True)

    # 检查当前 session 的消息数量
    print("\n[6] 检查 session 状态...")
    storage = session_manager.storage
    today_session = storage.get_or_create_today()
    print(f"  今日消息数: {today_session.message_count}")
    print(f"  摘要已生成: {today_session.summary_generated}")

    # 手动触发日终摘要生成
    print("\n[7] 手动触发日终摘要生成...")
    if today_session.message_count >= session_config.min_messages_for_summary:
        print(f"  消息数 ({today_session.message_count}) >= 阈值 ({session_config.min_messages_for_summary})")
        print("  正在生成摘要...")

        try:
            persona_context = session_manager.prompt_builder.build_persona_context()
            messages_list = today_session.get_messages()
            summary_path = await session_manager.summarizer.generate_summary(
                date=today_session.date,
                messages=messages_list,
                persona_context=persona_context,
            )
            print(f"  摘要已保存: {summary_path}")

            # 显示摘要内容
            summary_file = Path(summary_path)
            if summary_file.exists():
                print("\n[8] 摘要内容:")
                print("-" * 40)
                print(summary_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  生成摘要失败: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"  消息数不足: {today_session.message_count} < {session_config.min_messages_for_summary}")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_daily_summary())