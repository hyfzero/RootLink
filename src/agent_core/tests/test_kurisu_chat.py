#!/usr/bin/env python3
"""
牧濑红莉栖 (Kurisu Makise) - 红莉栖对话测试脚本
使用 MiniMax API 进行对话，带打字机效果

用法:
  python test_kurisu_chat.py
"""

import os
import sys
import time
import json

# 添加 src 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_core.api import ChatAgent, ModelConfig, APIProvider, ApiMessage, MessageRole
from agent_core.models import ModelsStorage
from agent_core.brain import PersonaStorage, Persona, SpeakingStyleEngine

# ========== 配置 ==========
TEMPERATURE = 0.8
MAX_TOKENS = 500
TYPEWRITER_DELAY = 0.03  # 打字机效果延迟（秒）

# Brain 目录路径
BRAIN_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "persona")


def load_persona_with_style(brain_dir: str) -> tuple[Persona, SpeakingStyleEngine]:
    """从持久化文件加载人格和说话风格引擎

    Returns:
        tuple: (Persona, SpeakingStyleEngine)
    """
    storage = PersonaStorage(brain_dir)

    # 加载人格
    persona = storage.load_full()
    if not persona:
        raise FileNotFoundError(f"Brain 文件不存在: {brain_dir}")

    # 加载说话风格
    style_path = os.path.join(brain_dir, "speaking_style.json")
    with open(style_path, "r", encoding="utf-8") as f:
        style_data = json.load(f)

    style_engine = SpeakingStyleEngine.from_dict(style_data)
    return persona, style_engine


def build_system_prompt(persona: Persona, style_engine: SpeakingStyleEngine) -> str:
    """构建系统 prompt

    Args:
        persona: 人格对象
        style_engine: 说话风格引擎

    Returns:
        系统 prompt 字符串
    """
    parts = [
        f"你是{persona.profile.name}。",
        f"你是 Amadeus 系统中的 AI，不是真正的{persona.profile.name}。",
        "",
    ]

    # 添加说话风格指导（受 influence_weight 影响）
    style_prompt = style_engine.build_style_prompt()
    if style_prompt:
        parts.append(f"说话风格：{style_prompt}")
        parts.append("")

    parts.append("请和我正常对话。")

    return "\n".join(parts)


def get_api_config():
    """从配置文件加载 API 配置"""
    storage = ModelsStorage("./config")
    config_data = storage.load()

    if "minimax" in config_data.providers:
        provider_config = config_data.providers["minimax"]
        return provider_config.api_key, APIProvider.MINIMAX, "MiniMax-M2.5"

    raise ValueError("未在 config/models.json 中找到 MiniMax 配置")


def typewriter_print(text: str, delay: float = TYPEWRITER_DELAY):
    """打字机效果输出"""
    for char in text:
        print(char, end="", flush=True)
        time.sleep(delay)
    print()


class KurisuChat:
    """牧濑红莉栖对话类"""

    def __init__(self, agent: ChatAgent, system_prompt: str):
        self.agent = agent
        self.messages = [ApiMessage(role=MessageRole.SYSTEM, content=system_prompt)]

    def send(self, user_input: str, stream: bool = True) -> str:
        """发送消息并获取回复"""
        if not user_input.strip():
            return "请输入内容"

        try:
            if stream:
                return self._stream_response(user_input)
            else:
                return self._normal_response(user_input)

        except Exception as e:
            return f"错误: {str(e)}"

    def _normal_response(self, user_input: str) -> str:
        """普通响应模式"""
        self.messages.append(ApiMessage(role=MessageRole.USER, content=user_input))

        response = self.agent.chat(messages=self.messages, stream=False)

        content = response.content if hasattr(response, 'content') else str(response)
        self.messages.append(ApiMessage(role=MessageRole.ASSISTANT, content=content))
        return content

    def _stream_response(self, user_input: str) -> str:
        """流式响应模式（打字机效果）"""
        self.messages.append(ApiMessage(role=MessageRole.USER, content=user_input))

        chunk = self.agent.chat(messages=self.messages, stream=True)

        accumulated = ""
        if hasattr(chunk, 'delta'):
            accumulated = chunk.delta
            for char in accumulated:
                print(char, end="", flush=True)
                time.sleep(TYPEWRITER_DELAY)
            print()
        else:
            accumulated = str(chunk)

        self.messages.append(ApiMessage(role=MessageRole.ASSISTANT, content=accumulated))
        return accumulated

    def clear(self):
        """清除对话历史（保留 system prompt）"""
        system_prompt = self.messages[0]
        self.messages = [system_prompt]


def main():
    # 从配置文件加载 API 配置
    try:
        api_key, provider, model_name = get_api_config()
        print(f"API 配置: {provider} / {model_name}")
    except ValueError as e:
        print(f"错误: {e}")
        print("请在 config/models.json 中配置 MiniMax API")
        sys.exit(1)

    # 创建 ChatAgent
    config = ModelConfig(
        name=model_name,
        provider=provider,
        supports_thinking=True,
    )
    config.api_key = api_key
    agent = ChatAgent(config)

    # 从 Brain 系统加载人格和说话风格
    brain_path = os.path.abspath(BRAIN_DIR)
    print(f"加载 Brain: {brain_path}")
    persona, style_engine = load_persona_with_style(brain_path)
    system_prompt = build_system_prompt(persona, style_engine)
    print(f"人格已加载: {persona.profile.name} (Amadeus)")
    print(f"说话风格影响权重: {style_engine.influence_weight}")
    print()

    # 创建对话实例
    chat = KurisuChat(agent, system_prompt)

    # 打印欢迎语
    print("=" * 60)
    print("  牧濑红莉栖 (Kurisu Makise) - Amadeus 对话测试")
    print("  输入 'quit' 退出, 'clear' 清除历史")
    print("=" * 60)
    print()

    # 模拟开场白
    print("红莉栖: ", end="", flush=True)
    welcome = "哼，你来了啊。有什么事情吗？没事的话我还要继续做实验呢。"
    typewriter_print(welcome, TYPEWRITER_DELAY)
    print()

    while True:
        try:
            user_input = input("你: ").strip()

            if not user_input:
                continue

            if user_input.lower() == "quit":
                print("\n红莉栖: ", end="", flush=True)
                goodbye = "哼，要走了吗。算了，随便你。"
                typewriter_print(goodbye, TYPEWRITER_DELAY)
                print()
                break

            if user_input.lower() == "clear":
                chat.clear()
                print("[历史已清除]")
                print()
                continue

            print()
            print("红莉栖: ", end="", flush=True)
            response = chat.send(user_input)
            print()
            print()

        except KeyboardInterrupt:
            print("\n\n红莉栖: ", end="", flush=True)
            goodbye = "真是的，突然就...算了，下次再见吧。"
            typewriter_print(goodbye, TYPEWRITER_DELAY)
            print()
            break
        except EOFError:
            break


if __name__ == "__main__":
    main()
