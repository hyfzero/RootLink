#!/usr/bin/env python3
"""
Session 示例 - 完整的 Amadues 对话会话

展示:
1. 使用 Brain 初始化 Amadues
2. 使用 Model 加载统一配置目录中的 minimax 模型配置
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
    PersonalityState,
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
import json

# 数据存储基地址。统一走 PathResolver，避免直接读写项目目录 data/。
DATA_BASE = PathResolver.get_data_dir()


def load_persona_from_path(base_path: str | Path) -> tuple[Optional[Persona], Optional[SpeakingStyleEngine]]:
    """从指定路径加载 Persona 和 SpeakingStyle。

    期望目录结构:
        base_path/
            persona/
                profile.json
                memories.json
                speaking_style.json

    Args:
        base_path: Brain 数据目录，包含 persona/ 子目录

    Returns:
        (Persona, SpeakingStyleEngine) 元组，任一可能为 None
    """
    persona_path = Path(base_path)
    persona = None
    style_engine = None

    # 加载 profile.json
    profile_file = persona_path / "persona" / "profile.json"
    if profile_file.exists():
        try:
            with open(profile_file, "r", encoding="utf-8") as f:
                profile_data = json.load(f)
            profile = PersonaProfile.from_dict(profile_data)
            persona = Persona(profile)
        except (json.JSONDecodeError, IOError) as e:
            print(f"  警告: 无法加载 profile.json: {e}")

    # 加载 memories.json
    memories_file = persona_path / "persona" / "memories.json"
    if memories_file.exists() and persona:
        try:
            with open(memories_file, "r", encoding="utf-8") as f:
                memories_data = json.load(f)

            from agent_core.brain.persona import MemoryEntry
            for m in memories_data.get("episodic_memories", []):
                persona.episodic_memories.append(MemoryEntry.from_dict(m))
            for m in memories_data.get("preference_memories", []):
                persona.preference_memories.append(MemoryEntry.from_dict(m))
            for m in memories_data.get("fact_memories", []):
                persona.fact_memories.append(MemoryEntry.from_dict(m))
        except (json.JSONDecodeError, IOError) as e:
            print(f"  警告: 无法加载 memories.json: {e}")

    # 加载 state.json（运行时人格状态）
    state_file = persona_path / "persona" / "state.json"
    if state_file.exists() and persona:
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                persona.state = PersonalityState.from_dict(json.load(f))
        except (json.JSONDecodeError, IOError) as e:
            print(f"  警告: 无法加载 state.json: {e}")

    # 加载 speaking_style.json
    style_file = persona_path / "persona" / "speaking_style.json"
    if style_file.exists():
        try:
            with open(style_file, "r", encoding="utf-8") as f:
                style_data = json.load(f)
            style_engine = SpeakingStyleEngine.from_dict(style_data)
        except (json.JSONDecodeError, IOError) as e:
            print(f"  警告: 无法加载 speaking_style.json: {e}")

    return persona, style_engine


def load_model_from_config(config_dir: str | Path | None = None) -> ModelConfig:
    """从统一配置目录加载模型配置"""
    config_dir = Path(config_dir) if config_dir is not None else PathResolver.get_config_dir()
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
        tokenizer_mode=model_info.tokenizer_mode if model_info else "auto",
        tokenizer_fallback=model_info.tokenizer_fallback if model_info else "hybrid_v1",
    )


def create_default_brain(
    persona_path: Optional[str | Path] = None,
) -> dict:
    """创建默认 Brain 组件

    Args:
        brain_id: Brain ID
        persona_path: 可选的 persona 数据路径，如果提供则从该路径加载
    """

    # 1. 尝试从路径加载 Persona 和 SpeakingStyle
    persona = None
    style_engine = None
    if persona_path:
        print(f"  - 从 {persona_path} 加载 persona 数据...")
        loaded_persona, loaded_style = load_persona_from_path(persona_path)
        if loaded_persona:
            persona = loaded_persona
            print(f"    成功加载 Persona: {persona.profile.name}")
        if loaded_style:
            style_engine = loaded_style
            print(f"    成功加载 SpeakingStyle")

    # 2. 如果没有加载成功，创建默认配置
    if persona is None:
        profile = PersonaProfile(
            name="Amadues",
            age=20,
            gender="unknown",
            personality_traits=["智能", "友善", "好奇"],
            background="一个基于大语言模型的AI助手",
            speaking_style="friendly",
        )
        persona = Persona(profile)
        persona.add_memory(
            content="用户第一次启动会话",
            memory_type="episodic",
            importance=1.0,
        )

    if style_engine is None:
        style_engine = SpeakingStyleEngine(
            preset_name="gentle",
            influence_weight=0.5,
        )

    # 3. 创建历史管理器
    history = MessageHistory(
        max_context_tokens=4000,
        token_reserved=1000,
        retention_days=30,
    )

    # 4. 创建 Agent 配置
    config = AgentConfig()

    # 5. 创建 Prompt 构建器
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
    config_dir: str | Path | None = None,
    brain_id: str = "amadues",
    brain_base_path: Optional[str | Path] = None,
    persona_path: Optional[str | Path] = None,
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
        brain_base_path: Brain 数据根目录，默认使用 PathResolver.get_data_dir()

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
    if brain_base_path is None:
        brain_base_path = DATA_BASE
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
        components_dict = create_default_brain(persona_path)

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
    # session_manager.set_emotion_mode("llm")
    session_manager.set_emotion_mode("keyword")
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


def daily_memory_update(session_manager: SessionManager, last_date: list) -> None:
    """每日记忆更新

    在日期切换时调用，更新 Brain 中的记忆，并生成日终摘要
    """
    time_info = get_current_time_info()
    current_date = time_info['date']

    # 检查日期是否切换
    if last_date[0] and last_date[0] != current_date:
        print(f"\n日期切换检测: {last_date[0]} -> {current_date}")
        # 日期切换，尝试生成上一天的日终摘要
        try:
            old_session = session_manager.storage.get_session_by_date(last_date[0])
            if old_session and old_session.message_count >= 4:
                # 使用同步版本的日终摘要生成
                session_manager._generate_end_of_day_summary_sync(old_session)
                print(f"  - 日终摘要已生成")
        except Exception as e:
            print(f"  - 生成日终摘要失败: {e}")

    last_date[0] = current_date

    print(f"\n每日记忆更新 - {current_date}")

    # 获取当前 Brain 组件
    components = session_manager.brain_registry.current()
    persona = components.persona

    # 今日有足够消息则生成日终摘要（始终覆盖）
    today_session = session_manager.storage.get_session_by_date(current_date)
    if today_session and today_session.message_count >= 4:
        try:
            session_manager._generate_end_of_day_summary_sync(today_session)
            print(f"  - 今日日终摘要已生成")
        except Exception as e:
            print(f"  - 生成日终摘要失败: {e}")

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

            if user_input.lower() in ["summary", "日终摘要"]:
                # 手动触发日终摘要生成
                today = datetime.now().strftime("%Y-%m-%d")
                session = session_manager.storage.get_session_by_date(today)
                if session and session.message_count >= 4:
                    print(f"正在为 {today} 生成日终摘要...")
                    session_manager._generate_end_of_day_summary_sync(session)
                    print(f"日终摘要已生成，更新了 memory.json")
                else:
                    print(f"今日消息数不足或无 session: {session.message_count if session else 0}")
                continue

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
    parser.add_argument(
        "--config-dir",
        "-c",
        default=str(PathResolver.get_config_dir()),
        help="配置文件目录",
    )
    parser.add_argument("--brain-id", "-b", default="amadues", help="Brain ID")
    parser.add_argument("--persona-path", "-p", default=None, help="Persona 数据路径")
    parser.add_argument("--generate-summary", "-s", metavar="DATE",
                        help="手动生成指定日期的日终摘要（格式: YYYY-MM-DD，不指定则为今日）")
    parser.add_argument("--generate-monthly", "-m", metavar="YEAR-MONTH",
                        help="手动生成指定月份的月度总结（格式: YYYY-MM，不指定则为上月）")
    args = parser.parse_args()

    # 默认 persona 路径和 brain_base_path 统一使用 PathResolver 管理的数据目录
    if args.persona_path is None:
        persona_path = PathResolver.get_brain_dir(args.brain_id)
    else:
        persona_path = Path(args.persona_path)

    # brain_base_path 与 persona_path 保持一致
    brain_base_path = persona_path.parent

    # 初始化
    session_manager, brain_registry = initialize_amadues(
        config_dir=args.config_dir,
        brain_id=args.brain_id,
        brain_base_path=brain_base_path,
        persona_path=persona_path,
    )

    # 获取当前时间
    time_info = get_current_time_info()
    print(f"\n当前时间信息:")
    print(f"  日期: {time_info['date']}")
    print(f"  时间: {time_info['time']}")
    print(f"  星期: {time_info['weekday_cn']}")

    # 每日记忆更新（使用列表追踪上次的日期）
    last_date = [time_info['date']]
    daily_memory_update(session_manager, last_date)

    if args.message:
        # 命令行指定的消息
        for msg in args.message:
            send_message_example(session_manager, msg)
            print()
    elif args.generate_summary is not None:
        # 手动生成指定日期的日终摘要
        target_date = args.generate_summary if args.generate_summary else time_info['date']
        print(f"\n手动生成日终摘要: {target_date}")
        session = session_manager.storage.get_session_by_date(target_date)
        if session and session.message_count >= 4:
            session_manager._generate_end_of_day_summary_sync(session)
            print(f"日终摘要已生成并更新 memory.json")
        else:
            print(f"消息数不足或无 session: {session.message_count if session else 0}")
    elif args.generate_monthly is not None:
        # 手动生成指定月份的月度总结
        target_month = args.generate_monthly
        print(f"\n手动生成月度总结: {target_month}")
        # 获取该月所有每日摘要
        daily_summaries = []
        brain_id = args.brain_id
        summary_dir = PathResolver.get_brain_dir(brain_id) / "history" / "daily"
        if summary_dir.exists():
            for f in summary_dir.glob("*.summary.json"):
                date_str = f.stem.replace(".summary", "")
                if date_str.startswith(target_month):
                    import json
                    with open(f, "r", encoding="utf-8") as fp:
                        daily_summaries.append(json.load(fp))
        if daily_summaries:
            persona_context = session_manager.prompt_builder.build_persona_context()
            monthly_data = session_manager._generate_end_of_month_summary_sync(
                year_month=target_month,
                daily_summaries=daily_summaries,
                persona_context=persona_context,
            )
            session_manager._update_memories_from_monthly_summary(monthly_data)
            session_manager._clear_monthly_data(target_month)
            print(f"月度总结已生成并更新 memory.json")
        else:
            print(f"无该月的每日摘要数据")
    else:
        # 交互模式
        interactive_mode(session_manager)


if __name__ == "__main__":
    main()
