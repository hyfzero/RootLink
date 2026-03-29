"""Session Manager 模块 - 日终摘要生成。

日期切换时调用 LLM 生成当日对话摘要。
"""

import json
from pathlib import Path
from typing import Optional

from ..api.client import ChatAgent
from ..api.adapter import ModelConfig
from ..brain.history import Message, MessageRole


class DailySummarizer:
    """日终摘要生成器。

    日期切换时调用 LLM 生成当日对话摘要。
    """

    def __init__(
        self,
        chat_agent: ChatAgent,
        output_dir: Path,
        model_config: Optional[ModelConfig] = None
    ):
        """初始化。

        Args:
            chat_agent: ChatAgent 实例
            output_dir: 摘要输出目录
            model_config: 模型配置（用于指定使用哪个模型）
        """
        self.chat_agent = chat_agent
        self.output_dir = output_dir
        self.model_config = model_config
        output_dir.mkdir(parents=True, exist_ok=True)

    async def generate_summary(
        self,
        date: str,                          # YYYY-MM-DD
        messages: list[Message],
        persona_context: str = ""           # 用于摘要的人格上下文
    ) -> str:
        """调用 LLM 生成当日摘要。

        Args:
            date: 日期
            messages: 当日消息列表
            persona_context: 人格上下文

        Returns:
            摘要文件路径
        """
        prompt = self._build_summary_prompt(date, messages, persona_context)

        response = await self._call_llm(prompt)

        summary_text = self._parse_summary_response(response)

        # 保存为 Markdown
        output_path = self.output_dir / f"{date}.summary.md"
        output_path.write_text(summary_text, encoding="utf-8")

        # 同时保存 JSON 格式（便于程序读取）
        json_path = self.output_dir.parent / "daily" / f"{date}.summary.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)

        summary_data = {
            "date": date,
            "summary_text": summary_text,
            "message_count": len(messages),
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2)

        return str(output_path)

    def _build_summary_prompt(
        self,
        date: str,
        messages: list[Message],
        persona_context: str
    ) -> str:
        """构建摘要 Prompt。

        Args:
            date: 日期
            messages: 消息列表
            persona_context: 人格上下文

        Returns:
            摘要 Prompt
        """
        role_names = {
            MessageRole.USER: "用户",
            MessageRole.ASSISTANT: "助手",
            MessageRole.SYSTEM: "系统",
            MessageRole.TOOL: "工具",
        }

        formatted_messages = []
        for msg in messages:
            role_text = role_names.get(msg.role, msg.role.value)
            content = msg.content[:300] + "..." if len(msg.content) > 300 else msg.content
            formatted_messages.append(f"[{role_text}] {content}")

        messages_text = "\n".join(formatted_messages)

        persona_section = f"\n\n人格背景:\n{persona_context}" if persona_context else ""

        return f"""你是一个对话摘要助手。请分析以下日期为 {date} 的对话，生成简洁但信息丰富的摘要。

人格背景:{persona_section}

对话内容：
{messages_text}

请按以下JSON格式输出摘要（只输出JSON，不要有其他内容）：
{{
    "summary_text": "2-3句话的对话摘要，重点是重要事件、决定和用户偏好",
    "important_messages": ["最重要的1-2条消息ID或简短描述"],
    "topics": ["讨论的主要话题"],
    "emotional_tone": "整体情感基调（积极/中性/消极/混合）",
    "user_preferences": ["用户表达的任何偏好或决定"],
    "unfinished_topics": ["未完成或需要后续跟进的话题"]
}}

注意：
- summary_text 应该简洁但包含关键信息
- topics 只列出最重要的2-3个话题
- 如果没有重要的用户偏好，user_preferences 可以为空数组
- 如果没有未完成的话题，unfinished_topics 可以为空数组"""

    async def _call_llm(self, prompt: str) -> str:
        """调用 LLM 获取摘要。

        Args:
            prompt: 摘要 Prompt

        Returns:
            LLM 响应文本
        """
        messages = [Message(
            id="summary_prompt",
            role=MessageRole.USER,
            content=prompt,
            timestamp=0,
        )]

        response = self.chat_agent.chat(messages, stream=False)

        if hasattr(response, 'content'):
            return response.content
        elif hasattr(response, 'delta'):
            return response.delta
        else:
            return str(response)

    def _parse_summary_response(self, response_text: str) -> str:
        """解析 LLM 响应，提取摘要内容。

        Args:
            response_text: LLM 响应文本

        Returns:
            格式化的摘要文本
        """
        try:
            # 尝试提取 JSON
            json_str = response_text.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.startswith("```"):
                json_str = json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            json_str = json_str.strip()

            data = json.loads(json_str)

            # 格式化为 Markdown
            md_parts = [f"# {data.get('date', '摘要')} 对话摘要\n"]

            if emotional_tone := data.get("emotional_tone"):
                md_parts.append(f"## 情感基调\n{emotional_tone}\n")

            if topics := data.get("topics"):
                md_parts.append(f"## 话题回顾\n")
                for topic in topics:
                    md_parts.append(f"- {topic}")
                md_parts.append("")

            if user_prefs := data.get("user_preferences"):
                md_parts.append(f"## 用户偏好\n")
                for pref in user_prefs:
                    md_parts.append(f"- {pref}")
                md_parts.append("")

            if unfinished := data.get("unfinished_topics"):
                md_parts.append(f"## 未完成话题\n")
                for topic in unfinished:
                    md_parts.append(f"- {topic}")
                md_parts.append("")

            if important := data.get("important_messages"):
                md_parts.append(f"## 关键事件\n")
                for msg in important:
                    md_parts.append(f"- {msg}")
                md_parts.append("")

            if summary_text := data.get("summary_text"):
                md_parts.append(f"## 摘要\n{summary_text}\n")

            return "\n".join(md_parts)

        except (json.JSONDecodeError, KeyError) as e:
            # 解析失败，返回原始文本
            return f"# 摘要\n{response_text}\n\n<!-- 解析失败，原始内容 -->\n"


class SyncDailySummarizer:
    """同步版本的日终摘要生成器。"""

    def __init__(
        self,
        llm_callable,  # (prompt: str) -> str
        output_dir: Path
    ):
        self.llm_callable = llm_callable
        self.output_dir = output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

    def generate_summary(
        self,
        date: str,
        messages: list[Message],
        persona_context: str = ""
    ) -> str:
        """同步生成摘要。

        Args:
            date: 日期
            messages: 消息列表
            persona_context: 人格上下文

        Returns:
            摘要文件路径
        """
        prompt = self._build_summary_prompt(date, messages, persona_context)
        response_text = self.llm_callable(prompt)
        summary_text = self._parse_summary_response(response_text)

        output_path = self.output_dir / f"{date}.summary.md"
        output_path.write_text(summary_text, encoding="utf-8")

        return str(output_path)

    def _build_summary_prompt(
        self,
        date: str,
        messages: list[Message],
        persona_context: str
    ) -> str:
        """构建摘要 Prompt"""
        role_names = {
            MessageRole.USER: "用户",
            MessageRole.ASSISTANT: "助手",
            MessageRole.SYSTEM: "系统",
            MessageRole.TOOL: "工具",
        }

        formatted_messages = []
        for msg in messages:
            role_text = role_names.get(msg.role, msg.role.value)
            content = msg.content[:300] + "..." if len(msg.content) > 300 else msg.content
            formatted_messages.append(f"[{role_text}] {content}")

        messages_text = "\n".join(formatted_messages)
        persona_section = f"\n\n人格背景:\n{persona_context}" if persona_context else ""

        return f"""你是一个对话摘要助手。请分析以下日期为 {date} 的对话，生成简洁但信息丰富的摘要。

人格背景:{persona_section}

对话内容：
{messages_text}

请按以下JSON格式输出摘要（只输出JSON，不要有其他内容）：
{{
    "summary_text": "2-3句话的对话摘要",
    "important_messages": ["最重要的1-2条"],
    "topics": ["讨论的主要话题"],
    "emotional_tone": "整体情感基调",
    "user_preferences": ["用户偏好"],
    "unfinished_topics": ["未完成话题"]
}}"""

    def _parse_summary_response(self, response_text: str) -> str:
        """解析摘要响应"""
        try:
            json_str = response_text.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0]
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0]
            data = json.loads(json_str.strip())

            md_parts = [f"# {data.get('date', '摘要')} 对话摘要\n"]
            if ts := data.get("emotional_tone"):
                md_parts.append(f"## 情感基调\n{ts}\n")
            if topics := data.get("topics"):
                md_parts.append("## 话题\n- " + "\n- ".join(topics) + "\n")
            if prefs := data.get("user_preferences"):
                md_parts.append("## 偏好\n- " + "\n- ".join(prefs) + "\n")
            if unfinished := data.get("unfinished_topics"):
                md_parts.append("## 未完成\n- " + "\n- ".join(unfinished) + "\n")
            if summary := data.get("summary_text"):
                md_parts.append(f"## 摘要\n{summary}\n")

            return "\n".join(md_parts)
        except:
            return f"# 摘要\n{response_text}\n"
