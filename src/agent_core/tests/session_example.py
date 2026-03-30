#!/usr/bin/env python3
"""
Session 示例 - 完整的 Amadues 对话会话

展示:
1. 使用 Brain 初始化 Amadues
2. 使用 Model 加载 ./config 的 minimax 模型配置
3. Session 完整流程:
   - 获取时间
   - 每日更新记忆
   - 消息机制
   - 输入对话与模型交流

用法:
  python session_example.py

或者交互模式:
  python session_example.py --interactive
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Windows 终端编码处理
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 添加 src 目录到路径
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_script_dir, "..", "..", ".."))
sys.path.insert(0, os.path.join(_project_root, "src"))

from agent_core.brain import (
    Persona,
    PersonaProfile,
    MessageHistory,
    SpeakingStyleEngine,
    PromptBuilder,
    AgentConfig,
    TagGenerator,
    Message,
    MessageRole,
)
from agent_core.models import ModelsStorage, ProviderConfig
from agent_core.api import ChatAgent
from agent_core.api.adapter import ModelConfig, APIProvider
from agent_core.session import (
    SessionManager,
    SessionConfig,
    BrainRegistry,
    PathResolver,
)


def load_model_from_config(config_dir: str = "./config") -> ModelConfig:
    """从 config/models.json 加载模型配置"""
    storage = ModelsStorage(config_dir)
    config = storage.load()

    # 获取默认 provider
    provider_name = config.default_provider or "minimax"
    provider_config: ProviderConfig = config.providers.get(provider_name)

    if not provider_config:
        raise ValueError(f"Provider '{provider_name}' not found in config")

    # 获取模型目录中的模型信息
    from agent_core.models import get_model_catalog
    catalog = get_model_catalog(provider_name)

    # 默认使用 M2.5 模型
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


def create_default_brain(brain_id: str = "default") -> dict:
    """创建默认 Brain 组件"""

    # 1. 创建角色配置
    profile = PersonaProfile(
        name="阿玛迪斯",
        age=20,
        gender="unknown",
        personality_traits=["智能", "友善", "好奇"],
        background="一个基于大语言模型的AI助手",
        speaking_style="friendly",
    )

    # 2. 创建人格管理器
    persona = Persona(profile)
    persona.add_memory(
        content="用户第一次启动会话",
        memory_type="episodic",
        importance=1.0,
    )

    # 3. 创建历史管理器
    history = MessageHistory(
        max_context_tokens=4000,
        token_reserved=1000,
        retention_days=30,
    )

    # 4. 创建说话风格引擎
    style_engine = SpeakingStyleEngine(
        preset_name="gentle",
        influence_weight=0.5,
    )

    # 5. 创建 Agent 配置
    config = AgentConfig()

    # 6. 创建 Prompt 构建器
    prompt_builder = PromptBuilder(
        persona=persona,
        history=history,
        style_engine=style_engine,
        config=config,
    )

    return {
        "persona": persona,
        "history": history,
        "style_engine": style_engine,
        "prompt_builder": prompt_builder,
        "config": config,
    }


def initialize_amadues(
    config_dir: str = "./config",
    brain_id: str = "amadues",
    brain_base_path: Optional[str] = None,
) -> tuple[SessionManager, BrainRegistry]:
    """初始化 Amadues 会话系统

    流程:
    1. 加载模型配置
    2. 创建 BrainRegistry
    3. 加载 Brain 组件（从已有数据或创建新的）
    4. 创建 SessionManager

    Args:
        config_dir: 配置文件目录
        brain_id: Brain ID
        brain_base_path: Brain 数据根目录，默认使用 {project_root}/src/agent_core/data

    Returns:
        (SessionManager, BrainRegistry) 元组
    """
    print("=" * 60)
    print("Amadues 初始化")
    print("=" * 60)

    # 1. 加载模型配置
    print("\n[1/4] 加载模型配置...")
    model_config = load_model_from_config(config_dir)
    print(f"  - Provider: {model_config.provider}")
    print(f"  - Model: {model_config.name}")
    print(f"  - Base URL: {model_config.resolved_base_url}")

    # 2. 创建 ChatAgent
    print("\n[2/4] 创建 ChatAgent...")
    chat_agent = ChatAgent(config=model_config)
    print(f"  - ChatAgent 创建成功")

    # 3. 创建 BrainRegistry
    print("\n[3/4] 初始化 Brain...")
    # 默认使用 src/agent_core/data 目录
    if brain_base_path is None:
        brain_base_path = os.path.join(_project_root, "src", "agent_core", "data")
    brain_registry = BrainRegistry(Path(brain_base_path))

    # 加载已有 Brain
    existing_brains = brain_registry.load_all()
    if brain_id in existing_brains:
        print(f"  - 已加载 Brain: {brain_id}")
        brain_registry.switch(brain_id)

        # 显示 Brain 信息
        info = brain_registry.get_brain_info(brain_id)
        if info:
            print(f"  - 名称: {info.name}")
    elif not existing_brains:
        # 没有 Brain，创建一个默认的
        print(f"  - 创建新 Brain: {brain_id}")
        components_dict = create_default_brain(brain_id)

        from agent_core.session.brain_registry import BrainComponents
        components = BrainComponents(
            persona=components_dict["persona"],
            history=components_dict["history"],
            style_engine=components_dict["style_engine"],
            prompt_builder=components_dict["prompt_builder"],
            config=components_dict["config"],
        )
        brain_registry.register(brain_id, components)
        brain_registry.switch(brain_id)
        print(f"  - Brain '{brain_id}' 注册成功")
    else:
        # 使用第一个可用的 Brain
        print(f"  - Brain '{brain_id}' 不存在，使用: {existing_brains[0]}")
        brain_registry.switch(existing_brains[0])
        brain_id = existing_brains[0]

    # 4. 创建 SessionManager
    print("\n[4/4] 创建 SessionManager...")
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

    return session_manager, brain_registry


def get_current_time_info() -> dict:
    """获取当前时间信息"""
    now = datetime.now()
    return {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
        "weekday_cn": ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()],
        "timestamp": now.timestamp(),
    }


def daily_memory_update(session_manager: SessionManager) -> None:
    """每日记忆更新

    在日期切换时调用，更新 Brain 中的记忆
    """
    time_info = get_current_time_info()
    print(f"\n每日记忆更新 - {time_info['date']}")

    # 获取当前 Brain 组件
    components = session_manager.brain_registry.current()
    persona = components.persona

    # 添加日期相关的情景记忆
    persona.add_memory(
        content=f"用户在 {time_info['date']} {time_info['time']} 使用了 Amadues 系统",
        memory_type="episodic",
        importance=1.0,
        context="系统使用",
    )

    # 获取近期的对话历史
    recent_sessions = session_manager.get_conversation_history(days=7)
    if recent_sessions:
        total_messages = sum(s.message_count for s in recent_sessions)
        persona.add_memory(
            content=f"用户在过去7天产生了 {total_messages} 条对话消息",
            memory_type="fact",
            importance=1.5,
            context="使用统计",
        )

    print(f"  - 已添加日期记忆")
    print(f"  - 当前记忆总数: {len(persona.get_recent_memories())}")


def send_message_example(session_manager: SessionManager, user_input: str) -> dict:
    """发送消息示例

    Args:
        session_manager: SessionManager 实例
        user_input: 用户输入

    Returns:
        响应字典
    """
    print(f"\n用户: {user_input}")

    # 同步发送消息
    response = session_manager.send_message_sync(
        user_message=user_input,
        emotion=None,
    )

    print(f"助手: {response['content']}")
    print(f"  - 消息ID: {response['message_id']}")
    print(f"  - 标签: emotion={response['tag'].emotion}, expression={response['tag'].expression}", flush=True)

    return response


def interactive_mode(session_manager: SessionManager) -> None:
    """交互模式"""
    print("\n" + "=" * 60)
    print("交互模式 (输入 'quit' 或 'exit' 退出)")
    print("=" * 60)

    # 获取时间信息
    time_info = get_current_time_info()
    print(f"\n当前时间: {time_info['date']} {time_info['time']} {time_info['weekday_cn']}")

    while True:
        try:
            user_input = input("\n你: ").strip()

            if user_input.lower() in ["quit", "exit", "退出"]:
                print("再见!")
                break

            if not user_input:
                continue

            response = send_message_example(session_manager, user_input)

        except KeyboardInterrupt:
            print("\n\n已退出")
            break
        except Exception as e:
            print(f"错误: {e}")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Amadues Session 示例")
    parser.add_argument("message", nargs="*", help="直接发送消息（留空进入交互模式）")
    parser.add_argument("--config-dir", "-c", default="./config", help="配置文件目录")
    parser.add_argument("--brain-id", "-b", default="amadues", help="Brain ID")
    args = parser.parse_args()

    # 初始化
    session_manager, brain_registry = initialize_amadues(
        config_dir=args.config_dir,
        brain_id=args.brain_id,
    )

    # 获取当前时间
    time_info = get_current_time_info()
    print(f"\n当前时间信息:")
    print(f"  日期: {time_info['date']}")
    print(f"  时间: {time_info['time']}")
    print(f"  星期: {time_info['weekday_cn']}")

    # 每日记忆更新
    daily_memory_update(session_manager)

    if args.message:
        # 命令行指定的消息
        for msg in args.message:
            send_message_example(session_manager, msg)
            print()
    else:
        # 交互模式
        interactive_mode(session_manager)


if __name__ == "__main__":
    main()
