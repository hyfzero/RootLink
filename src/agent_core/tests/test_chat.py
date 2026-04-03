#!/usr/bin/env python3
"""
Amadeus Chat - Python 测试脚本
支持 OpenAI / MiniMax Token Plan API

用法:
  python test_chat.py minimax                    # MiniMax
  python test_chat.py openai <api_key>          # OpenAI
"""

import os
import sys
import json
import urllib.request
import urllib.error

# ========== 配置 ==========
DEFAULT_OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
DEFAULT_MINIMAX_KEY = os.environ.get("MINIMAX_API_KEY", "sk-cp-vAU2LGd4d-l4_nkQGV2yQh_QeWxPFh2GZPsQLx0q4YyLMzwf2kAyjBs1-OIeJSChQxFuQyVtJ6aXk3gPthXALlYzL06p3_HYDlS7316Up80p0EoDZqVftcY")

# 模型配置
MODEL_OPENAI = "gpt-4"
MODEL_MINIMAX = "MiniMax-M2.7"
TEMPERATURE = 0.8
MAX_TOKENS = 500

# MiniMax Token Plan 配置
MINIMAX_URL = "https://api.minimaxi.com/v1/chat/completions"

# OpenAI 配置
OPENAI_URL = "https://api.openai.com/v1/chat/completions"


# ========== 人格定义 ==========
PERSONA = """你是牧濑红莉栖，18岁的天才少女物理学家，就读于 vk 大学。

性格特点：
- 外表傲娇，但内心温柔
- 理性务实，说话直接
- 有时会毒舌吐槽
- 对感兴趣的事物会变得热情

说话风格：
- 使用关西腔语气
- 经常称呼对方为「笨蛋」或「阿虚」
- 对物理相关话题会变得认真
- 适当的时候会表现出傲娇的一面

请用这个人格来和我对话，保持轻松愉快的氛围。"""


class AmadeusChat:
    def __init__(self, api_key: str, provider: str = "minimax"):
        self.api_key = api_key
        self.provider = provider
        self.messages = [
            {"role": "system", "content": PERSONA}
        ]

    def _make_request(self, url: str, payload: dict) -> dict:
        """发送 HTTP 请求"""
        data = json.dumps(payload).encode('utf-8')

        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            },
            method="POST"
        )

        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))

    def send(self, user_input: str) -> str:
        """发送消息并获取回复"""
        if not user_input.strip():
            return "请输入内容"

        # 添加用户消息
        self.messages.append({"role": "user", "content": user_input})

        # 构建请求
        payload = {
            "model": MODEL_MINIMAX if self.provider == "minimax" else MODEL_OPENAI,
            "messages": self.messages,
            "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS
        }

        url = MINIMAX_URL if self.provider == "minimax" else OPENAI_URL

        try:
            response = self._make_request(url, payload)

            if "choices" in response and len(response["choices"]) > 0:
                content = response["choices"][0]["message"]["content"]

                # 添加 AI 回复
                self.messages.append({"role": "assistant", "content": content})
                return content
            else:
                return f"无法解析响应: {response}"

        except urllib.error.HTTPError as e:
            return f"HTTP 错误 ({e.code}): {e.read().decode('utf-8')}"
        except Exception as e:
            return f"错误: {str(e)}"

    def clear(self):
        """清除对话历史"""
        self.messages = [{"role": "system", "content": PERSONA}]


def main():
    # 解析参数
    provider = "minimax"
    api_key = ""

    if len(sys.argv) == 1:
        # 使用环境变量
        if DEFAULT_MINIMAX_KEY:
            api_key = DEFAULT_MINIMAX_KEY
            provider = "minimax"
        elif DEFAULT_OPENAI_KEY:
            api_key = DEFAULT_OPENAI_KEY
            provider = "openai"
    elif len(sys.argv) >= 2:
        if sys.argv[1].lower() == "openai":
            provider = "openai"
            api_key = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OPENAI_KEY
        elif sys.argv[1].lower() == "minimax":
            provider = "minimax"
            api_key = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_MINIMAX_KEY

    if not api_key:
        print("错误: 请提供 API Key")
        print("用法:")
        print("  python test_chat.py minimax [api_key]     # MiniMax")
        print("  python test_chat.py openai <api_key>     # OpenAI")
        print()
        print("或设置环境变量:")
        print("  set MINIMAX_API_KEY=your_key")
        print("  set OPENAI_API_KEY=your_key")
        sys.exit(1)

    provider_name = "MiniMax" if provider == "minimax" else "OpenAI"
    print("=" * 50)
    print(f"  Amadeus Chat - {provider_name} 实验版")
    print("  (输入 'quit' 退出, 'clear' 清除历史)")
    print("=" * 50)
    print()

    chat = AmadeusChat(api_key, provider)

    while True:
        try:
            user_input = input("你: ").strip()

            if not user_input:
                continue

            if user_input.lower() == "quit":
                print("\n对话结束，再见！")
                break

            if user_input.lower() == "clear":
                chat.clear()
                print("[历史已清除]")
                print()
                continue

            response = chat.send(user_input)
            print(f"\n红莉栖: {response}\n")

        except KeyboardInterrupt:
            print("\n\n对话结束，再见！")
            break
        except EOFError:
            break


if __name__ == "__main__":
    main()
