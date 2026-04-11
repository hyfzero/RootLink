"""Session Manager 模块 - 日终摘要生成。

日期切换时调用 LLM 生成当日对话摘要。
"""

import json
from pathlib import Path
from typing import Optional

from ..api.client import ChatAgent
from ..api.adapter import ModelConfig
from ..api.message import Message as ApiMessage, MessageRole as ApiMessageRole


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
        messages: list[ApiMessage],
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
        summary_json = self._parse_summary_json(response)

        summary_text = self._parse_summary_response(response)

        # 保存为 Markdown
        output_path = self.output_dir / f"{date}.summary.md"
        output_path.write_text(summary_text, encoding="utf-8")

        # 同时保存 JSON 格式（便于程序读取）
        json_path = self.output_dir.parent / "daily" / f"{date}.summary.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)

        summary_data = {
            "date": date,
            "summary_text": self._as_string(summary_json.get("summary_text")),
            "important_messages": self._as_str_list(summary_json.get("important_messages")),
            "topics": self._as_str_list(summary_json.get("topics")),
            "emotional_tone": self._as_string(summary_json.get("emotional_tone")),
            "user_preferences": self._as_str_list(summary_json.get("user_preferences")),
            "unfinished_topics": self._as_str_list(summary_json.get("unfinished_topics")),
            "message_count": len(messages),
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2)

        return str(output_path)

    def _build_summary_prompt(
        self,
        date: str,
        messages: list[ApiMessage],
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
            ApiMessageRole.USER: "用户",
            ApiMessageRole.ASSISTANT: "助手",
            ApiMessageRole.SYSTEM: "系统",
            ApiMessageRole.TOOL: "工具",
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
    "summary_text": "2-3句话的对话摘要，重点是重要事件和日常闲聊",
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
        messages = [ApiMessage(
            role=ApiMessageRole.USER,
            content=prompt,
        )]

        response = self.chat_agent.chat(messages, stream=False)

        if hasattr(response, 'content'):
            return response.content
        elif hasattr(response, 'delta'):
            return response.delta
        else:
            return str(response)

    def _parse_summary_json(self, response_text: str) -> dict:
        """解析 LLM 的 JSON 响应，失败返回空字典。"""
        try:
            json_str = response_text.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.startswith("```"):
                json_str = json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            json_str = json_str.strip()
            data = json.loads(json_str)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _as_string(self, value: object) -> str:
        """将任意值转换为字符串，None 转为空字符串。"""
        if value is None:
            return ""
        return value if isinstance(value, str) else str(value)

    def _as_str_list(self, value: object) -> list[str]:
        """将任意值标准化为字符串列表。"""
        if not isinstance(value, list):
            return []
        normalized: list[str] = []
        for item in value:
            text = self._as_string(item).strip()
            if text:
                normalized.append(text)
        return normalized

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


class MonthlySummarizer:
    """月度总结生成器。

    月份切换时调用 LLM 生成当月对话汇总。
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
            model_config: 模型配置
        """
        self.chat_agent = chat_agent
        self.output_dir = output_dir
        self.model_config = model_config
        output_dir.mkdir(parents=True, exist_ok=True)

    async def generate_summary(
        self,
        year_month: str,  # YYYY-MM
        daily_summaries: list[dict],  # 每日摘要列表
        persona_context: str = ""
    ) -> dict:
        """调用 LLM 生成月度总结。

        Args:
            year_month: 年月 (YYYY-MM)
            daily_summaries: 每日摘要数据列表
            persona_context: 人格上下文

        Returns:
            包含 summary_text 和其他字段的字典
        """
        prompt = self._build_summary_prompt(year_month, daily_summaries, persona_context)
        response = await self._call_llm(prompt)

        summary_data = self._parse_summary_response(response, year_month)

        # 保存 JSON
        json_path = self.output_dir / f"{year_month}.monthly.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2)

        # 保存 Markdown
        md_path = self.output_dir / f"{year_month}.monthly.md"
        md_content = self._format_markdown(summary_data)
        md_path.write_text(md_content, encoding="utf-8")

        return summary_data

    def _build_summary_prompt(
        self,
        year_month: str,
        daily_summaries: list[dict],
        persona_context: str
    ) -> str:
        """构建月度总结 Prompt。"""
        # 汇总每日摘要
        summary_lines = []
        for day_summary in daily_summaries:
            date = day_summary.get("date", "")
            summary_text = day_summary.get("summary_text", "")
            topics = day_summary.get("topics", [])
            emotional_tone = day_summary.get("emotional_tone", "")
            user_prefs = day_summary.get("user_preferences", [])

            line = f"- {date}: {summary_text}"
            if topics:
                line += f" (话题: {', '.join(topics[:2])})"
            if user_prefs:
                line += f" [偏好: {', '.join(user_prefs[:2])}]"
            summary_lines.append(line)

        summaries_text = "\n".join(summary_lines)
        persona_section = f"\n\n人格背景:\n{persona_context}" if persona_context else ""

        return f"""你是一个对话总结助手。请分析以下 {year_month} 月的每日对话，生成该月的整体总结。

人格背景:{persona_section}

月内每日摘要：
{summaries_text}

请按以下JSON格式输出月度总结（只输出JSON，不要有其他内容）：
{{
    "year_month": "{year_month}",
    "summary_text": "2-3句话的月度总结，重点是主要事件、用户整体状态和长期偏好",
    "major_events": ["本月最重要的1-3个事件"],
    "monthly_topics": ["本月讨论的主要话题"],
    "overall_emotional_tone": "本月整体情感基调（积极/中性/消极/混合）",
    "user_long_term_preferences": ["用户本月表现出的长期偏好或习惯"],
    "unfinished_monthly_topics": ["本月未完成的话题"],
    "growth_or_change": ["用户可能表现出的成长或变化"]
}}

注意：
- summary_text 应该简洁但包含关键信息
- major_events 只列出最重要的1-3个事件
- user_long_term_preferences 是本月体现出的相对稳定的偏好
- 如果没有重要的长期偏好，user_long_term_preferences 可以为空数组"""

    async def _call_llm(self, prompt: str) -> str:
        """调用 LLM。"""
        messages = [ApiMessage(
            role=ApiMessageRole.USER,
            content=prompt,
        )]
        response = self.chat_agent.chat(messages, stream=False)
        if hasattr(response, 'content'):
            return response.content
        return str(response)

    def _parse_summary_response(self, response_text: str, year_month: str) -> dict:
        """解析 LLM 响应。"""
        try:
            json_str = response_text.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.startswith("```"):
                json_str = json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            json_str = json_str.strip()
            data = json.loads(json_str)
            data["year_month"] = year_month
            return data
        except json.JSONDecodeError:
            return {
                "year_month": year_month,
                "summary_text": response_text[:500],
                "major_events": [],
                "monthly_topics": [],
                "overall_emotional_tone": "未知",
                "user_long_term_preferences": [],
                "unfinished_monthly_topics": [],
                "growth_or_change": [],
            }

    def _format_markdown(self, data: dict) -> str:
        """格式化为 Markdown。"""
        parts = [f"# {data.get('year_month', '')} 月度总结\n"]
        if summary := data.get("summary_text"):
            parts.append(f"## 总结\n{summary}\n")
        if events := data.get("major_events"):
            parts.append("## 主要事件\n")
            for e in events:
                parts.append(f"- {e}")
            parts.append("")
        if topics := data.get("monthly_topics"):
            parts.append("## 主要话题\n")
            for t in topics:
                parts.append(f"- {t}")
            parts.append("")
        if tone := data.get("overall_emotional_tone"):
            parts.append(f"## 整体情感\n{tone}\n")
        if prefs := data.get("user_long_term_preferences"):
            parts.append("## 用户长期偏好\n")
            for p in prefs:
                parts.append(f"- {p}")
            parts.append("")
        return "\n".join(parts)


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
        messages: list[ApiMessage],
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
        messages: list[ApiMessage],
        persona_context: str
    ) -> str:
        """构建摘要 Prompt"""
        role_names = {
            ApiMessageRole.USER: "用户",
            ApiMessageRole.ASSISTANT: "助手",
            ApiMessageRole.SYSTEM: "系统",
            ApiMessageRole.TOOL: "工具",
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
