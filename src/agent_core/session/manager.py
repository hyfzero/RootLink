"""Session Manager 模块 - 核心调度类。

协调所有组件，提供统一的会话管理接口。
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from ..api.client import ChatAgent
from ..api.adapter import ModelConfig
from ..api.message import Message as ApiMessage, MessageRole as ApiMessageRole
from ..brain import (
    ReplyTag,
    TagGenerator,
    Message,
    MessageRole,
)


def _make_llm_callable(chat_agent: ChatAgent):
    """创建LLM调用函数，适配ChatAgent接口。"""
    def llm_callable(prompt: str) -> str:
        messages = [ApiMessage(role=ApiMessageRole.USER, content=prompt)]
        response = chat_agent.chat(messages, stream=False)
        if hasattr(response, 'content'):
            return response.content
        return ""
    return llm_callable

from .brain_registry import BrainRegistry, BrainComponents
from .config import SessionConfig
from .path_resolver import PathResolver
from .storage import SessionStorage, DaySession
from .prompt_builder import SessionPromptBuilder
from .reply_tagger import ReplyTagger, MemoryUpdater
from .summarizer import DailySummarizer, MonthlySummarizer


class SessionManager:
    """Session 管理器 - 核心调度类。

    协调 Prompt 构建、API 调用、回复标签生成、日终摘要等。
    """

    def __init__(
        self,
        config: SessionConfig,
        brain_registry: BrainRegistry,
        chat_agent: ChatAgent,
        tag_generator: Optional[TagGenerator] = None,
        use_msgpack: bool = False
    ):
        """初始化 Session 管理器。

        Args:
            config: Session 配置
            brain_registry: Brain 注册表（支持多 Brain）
            chat_agent: ChatAgent 实例
            tag_generator: TagGenerator 实例，不指定则创建默认
            use_msgpack: 是否使用 MessagePack 格式
        """
        self.config = config
        self.brain_registry = brain_registry
        self.chat_agent = chat_agent
        self.use_msgpack = use_msgpack

        # 当前 Brain ID
        self._current_brain_id = brain_registry.current_brain_id()

        # 标签生成器（使用 brain_id 对应的 tags 目录）
        if tag_generator is None:
            llm_callable = _make_llm_callable(chat_agent)
            tag_generator = TagGenerator(llm_callable=llm_callable, emotion_mode="keyword")
        elif tag_generator.llm_callable is None:
            # 用户传入了 TagGenerator 但没有 llm_callable，自动补充
            tag_generator.set_llm_callable(_make_llm_callable(chat_agent))
        tags_dir = PathResolver.get_tags_dir(self._current_brain_id)
        self.tagger = ReplyTagger(tag_generator, storage_path=tags_dir)

        # 存储（延迟初始化）
        self._storage: Optional[SessionStorage] = None

        # 日期跟踪
        self._current_date: Optional[str] = None
        self._current_month: Optional[str] = None

        # 摘要器（延迟初始化）
        self._summarizer: Optional[DailySummarizer] = None
        self._monthly_summarizer: Optional["MonthlySummarizer"] = None

    @property
    def storage(self) -> SessionStorage:
        """获取存储实例（延迟初始化）"""
        if self._storage is None:
            self._storage = SessionStorage(
                config=self.config,
                resolver=PathResolver(),
                brain_id=self._current_brain_id,
                use_msgpack=self.use_msgpack,
            )
        return self._storage

    @property
    def summarizer(self) -> DailySummarizer:
        """获取摘要器实例（延迟初始化）"""
        if self._summarizer is None:
            self._summarizer = DailySummarizer(
                chat_agent=self.chat_agent,
                output_dir=PathResolver.get_brain_dir(self._current_brain_id) / "history" / "summaries",
                model_config=self.config.model_config,
            )
        return self._summarizer

    @property
    def monthly_summarizer(self) -> MonthlySummarizer:
        """获取月度总结器实例（延迟初始化）"""
        if self._monthly_summarizer is None:
            self._monthly_summarizer = MonthlySummarizer(
                chat_agent=self.chat_agent,
                output_dir=PathResolver.get_brain_dir(self._current_brain_id) / "history" / "summaries",
                model_config=self.config.model_config,
            )
        return self._monthly_summarizer

    @property
    def prompt_builder(self) -> SessionPromptBuilder:
        """获取当前 Brain 的 PromptBuilder"""
        components = self.brain_registry.current()
        return SessionPromptBuilder(
            persona=components.persona,
            history=components.history,
            style_engine=components.style_engine,
            config=components.config,
        )

    # ==================== UI层标签解析模式控制 ====================

    def get_emotion_mode(self) -> str:
        """获取当前情感解析模式。

        Returns:
            "keyword" 或 "llm"
        """
        return self.tagger.tag_generator.emotion_mode

    def set_emotion_mode(self, mode: str) -> None:
        """设置情感解析模式。

        Args:
            mode: "keyword" 使用关键词匹配，"llm" 使用LLM解析
        """
        if mode not in ("keyword", "llm"):
            raise ValueError(f"mode must be 'keyword' or 'llm', got '{mode}'")
        self.tagger.tag_generator.set_emotion_mode(mode)

    def is_llm_emotion_enabled(self) -> bool:
        """检查是否启用LLM情感解析。

        Returns:
            True if LLM mode is enabled
        """
        return self.tagger.tag_generator.emotion_mode == "llm"

    @property
    def memory_updater(self) -> MemoryUpdater:
        """获取记忆更新器"""
        components = self.brain_registry.current()
        # 使用 BrainRegistry 的 base_path 来确保路径一致
        brain_dir = self.brain_registry._base_path / self._current_brain_id
        storage_path = brain_dir / "persona" / "memories.json"
        return MemoryUpdater(components.persona, storage_path=storage_path)

    # === 对话流程 ===

    async def send_message(
        self,
        user_message: str,
        emotion: Optional[str] = None,
        stream: bool = False
    ) -> dict:
        """发送消息并处理响应。

        流程:
        1. 检查日期切换 → 归档旧 Session → 生成摘要
        2. 保存用户消息
        3. 构建 Prompt
        4. 调用 API
        5. 生成回复标签
        6. 保存助手消息
        7. 返回响应

        Args:
            user_message: 用户消息
            emotion: 当前情绪状态
            stream: 是否流式返回

        Returns:
            响应字典，包含 content、tag 等
        """
        # 1. 日期切换检查
        await self._check_and_handle_day_change()

        # 2. 保存用户消息
        self.storage.add_message("user", user_message)

        # 3. 构建 Prompt
        system_prompt = self.prompt_builder.build_system_prompt(emotion)
        context = self.prompt_builder.build_conversation_context(user_message)

        # 4. 调用 API
        response = await self._call_api(system_prompt, context, stream)

        # 5. 生成回复标签
        message_id = self._generate_message_id()
        reply_tag = self.tagger.generate_tag(message_id, response.get("content", ""))

        # 6. 保存助手消息
        self.storage.add_message("assistant", response.get("content", ""))

        # 7. 返回
        return {
            "content": response.get("content", ""),
            "tag": reply_tag,
            "message_id": message_id,
            "brain_id": self._current_brain_id,
        }

    def send_message_sync(
        self,
        user_message: str,
        emotion: Optional[str] = None,
    ) -> dict:
        """同步版本的消息发送。

        Args:
            user_message: 用户消息
            emotion: 当前情绪状态

        Returns:
            响应字典
        """
        # 日期切换检查（同步版本）
        self._check_and_handle_day_change_sync()

        # 保存用户消息
        self.storage.add_message("user", user_message)

        # 构建 Prompt
        system_prompt = self.prompt_builder.build_system_prompt(emotion)
        context = self.prompt_builder.build_conversation_context(user_message)

        # 调用 API（同步）
        response = self._call_api_sync(system_prompt, context)

        # 生成回复标签
        message_id = self._generate_message_id()
        reply_tag = self.tagger.generate_tag(message_id, response.get("content", ""))

        # 保存助手消息
        self.storage.add_message("assistant", response.get("content", ""))

        return {
            "content": response.get("content", ""),
            "tag": reply_tag,
            "message_id": message_id,
            "brain_id": self._current_brain_id,
        }

    # === 日期切换处理 ===

    async def _check_and_handle_day_change(self) -> None:
        """检查并处理日期切换（异步版本）"""
        today = datetime.now().strftime("%Y-%m-%d")

        if self._current_date is not None and self._current_date != today:
            # 日期切换：归档 → 生成摘要
            old_session = self.storage.archive_if_new_day()
            if old_session:
                await self._generate_end_of_day_summary(old_session)

        self._current_date = today
        self.storage.get_or_create_today()

    def _check_and_handle_day_change_sync(self) -> None:
        """检查并处理日期切换（同步版本）"""
        today = datetime.now().strftime("%Y-%m-%d")
        current_month = datetime.now().strftime("%Y-%m")

        if self._current_date is not None and self._current_date != today:
            # 日期切换：归档并生成日终摘要
            old_session = self.storage.archive_if_new_day()
            if old_session and old_session.message_count >= self.config.min_messages_for_summary:
                self._generate_end_of_day_summary_sync(old_session)

        # 检查月份切换
        if self._current_month is not None and self._current_month != current_month:
            self._handle_month_change(self._current_month)

        self._current_date = today
        self._current_month = current_month
        self.storage.get_or_create_today()

    async def _generate_end_of_day_summary(self, session: DaySession) -> None:
        """生成日终摘要（异步）"""
        if session.summary_generated:
            return

        if session.message_count < self.config.min_messages_for_summary:
            return

        try:
            persona_context = self.prompt_builder.build_persona_context()
            messages = session.get_messages()
            await self.summarizer.generate_summary(
                date=session.date,
                messages=messages,
                persona_context=persona_context,
            )
            session.summary_generated = True

            # 从摘要更新记忆
            self._update_memories_from_summary(session.date)

        except Exception as e:
            print(f"Warning: Failed to generate summary: {e}")

    def _generate_end_of_day_summary_sync(self, session: DaySession) -> None:
        """生成日终摘要（同步版本）"""
        if session.summary_generated:
            return

        if session.message_count < self.config.min_messages_for_summary:
            return

        try:
            persona_context = self.prompt_builder.build_persona_context()
            messages = session.get_messages()

            # 同步调用 LLM 生成摘要
            prompt = self.summarizer._build_summary_prompt(
                date=session.date,
                messages=messages,
                persona_context=persona_context,
            )
            response_text = self._call_llm_sync_for_summary(prompt)

            # 解析 LLM 返回的 JSON 获取结构化数据
            json_data = self._parse_summary_json(response_text)

            # 生成 Markdown 格式的摘要
            summary_text = self.summarizer._parse_summary_response(response_text)

            # 保存为 Markdown
            output_path = self.summarizer.output_dir / f"{session.date}.summary.md"
            output_path.write_text(summary_text, encoding="utf-8")

            # 保存完整的 JSON（包含结构化字段）
            json_path = self.summarizer.output_dir.parent / "daily" / f"{session.date}.summary.json"
            json_path.parent.mkdir(parents=True, exist_ok=True)
            summary_data = {
                "date": session.date,
                "summary_text": json_data.get("summary_text", ""),
                "important_messages": json_data.get("important_messages", []),
                "topics": json_data.get("topics", []),
                "emotional_tone": json_data.get("emotional_tone", ""),
                "user_preferences": json_data.get("user_preferences", []),
                "unfinished_topics": json_data.get("unfinished_topics", []),
                "message_count": len(messages),
            }
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(summary_data, f, ensure_ascii=False, indent=2)

            session.summary_generated = True

            # 从摘要更新记忆（较低 importance）
            self._update_memories_from_summary(session.date)

        except Exception as e:
            print(f"Warning: Failed to generate summary (sync): {e}")

    def _parse_summary_json(self, response_text: str) -> dict:
        """解析 LLM 返回的 JSON 响应。"""
        try:
            json_str = response_text.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.startswith("```"):
                json_str = json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            json_str = json_str.strip()
            return json.loads(json_str)
        except json.JSONDecodeError:
            return {}

    def _update_memories_from_summary(self, date: str) -> None:
        """从摘要更新记忆。

        Args:
            date: 摘要日期
        """
        try:
            # 使用 BrainRegistry 的 base_path 确保路径一致
            brain_dir = self.brain_registry._base_path / self._current_brain_id
            summary_path = brain_dir / "history" / "daily" / f"{date}.summary.json"
            if summary_path.exists():
                with open(summary_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                self.memory_updater.update_from_summary(data)
        except Exception as e:
            print(f"Warning: Failed to update memories: {e}")

    def _handle_month_change(self, old_month: str) -> None:
        """处理月份切换。

        Args:
            old_month: 上个月份 (YYYY-MM)
        """
        print(f"\n月份切换: {old_month} -> {datetime.now().strftime('%Y-%m')}")

        # 获取上个月的所有每日摘要
        daily_summaries = []
        summary_dir = PathResolver.get_brain_dir(self._current_brain_id) / "history" / "daily"

        if summary_dir.exists():
            for summary_file in summary_dir.glob("*.summary.json"):
                # 检查日期是否属于上个月
                date_str = summary_file.stem.replace(".summary", "")
                if date_str.startswith(old_month):
                    try:
                        with open(summary_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            daily_summaries.append(data)
                    except Exception:
                        pass

        if daily_summaries:
            # 生成月度总结
            persona_context = self.prompt_builder.build_persona_context()
            monthly_data = self._generate_end_of_month_summary_sync(
                year_month=old_month,
                daily_summaries=daily_summaries,
                persona_context=persona_context,
            )
            # 高优先级更新记忆
            self._update_memories_from_monthly_summary(monthly_data)
            # 清空当月数据
            self._clear_monthly_data(old_month)
            print(f"  - 月度总结已生成并更新记忆")
        else:
            print(f"  - 无每日摘要数据，跳过月度总结")

    async def _generate_end_of_month_summary(
        self,
        year_month: str,
        daily_summaries: list[dict],
        persona_context: str
    ) -> dict:
        """生成月度总结（异步）"""
        monthly_data = await self.monthly_summarizer.generate_summary(
            year_month=year_month,
            daily_summaries=daily_summaries,
            persona_context=persona_context,
        )
        return monthly_data

    def _generate_end_of_month_summary_sync(
        self,
        year_month: str,
        daily_summaries: list[dict],
        persona_context: str
    ) -> dict:
        """生成月度总结（同步版本，使用同步调用）"""
        prompt = self.monthly_summarizer._build_summary_prompt(
            year_month, daily_summaries, persona_context
        )
        response_text = self._call_llm_sync_for_summary(prompt)
        monthly_data = self.monthly_summarizer._parse_summary_response(response_text, year_month)

        # 保存文件
        summary_dir = PathResolver.get_brain_dir(self._current_brain_id) / "history" / "summaries"
        summary_dir.mkdir(parents=True, exist_ok=True)

        json_path = summary_dir / f"{year_month}.monthly.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(monthly_data, f, ensure_ascii=False, indent=2)

        md_path = summary_dir / f"{year_month}.monthly.md"
        md_content = self.monthly_summarizer._format_markdown(monthly_data)
        md_path.write_text(md_content, encoding="utf-8")

        return monthly_data

    def _call_llm_sync_for_summary(self, prompt: str) -> str:
        """同步调用 LLM 获取摘要。"""
        from ..api.message import Message as ApiMessage, MessageRole as ApiMessageRole
        messages = [
            ApiMessage(role=ApiMessageRole.USER, content=prompt),
        ]
        response = self.chat_agent.chat(messages, stream=False)
        if hasattr(response, 'content'):
            return response.content
        return str(response)

    def _update_memories_from_monthly_summary(self, monthly_data: dict) -> None:
        """从月度总结更新记忆。

        Args:
            monthly_data: 月度总结数据
        """
        try:
            self.memory_updater.update_from_monthly_summary(monthly_data)
            self.memory_updater.save()
        except Exception as e:
            print(f"Warning: Failed to update memories from monthly summary: {e}")

    def _clear_monthly_data(self, year_month: str) -> None:
        """清空指定月份的记忆数据。

        注意：只清空 daily_summary_memories（参与 prompt 构建），
        本地 JSON/MD 文件保留以备后用（如需要重建记忆）。

        Args:
            year_month: 要清空的月份 (YYYY-MM)
        """
        try:
            # 清空 Persona.daily_summary_memories 中该月份的记忆
            # （这些才是参与 prompt 构建的数据）
            persona = self.memory_updater.persona
            original_count = len(persona.daily_summary_memories)
            persona.daily_summary_memories = [
                m for m in persona.daily_summary_memories
                if not m.context.startswith(f"日终摘要-{year_month}")
            ]
            cleared_count = original_count - len(persona.daily_summary_memories)

            # 保存更新后的记忆到文件
            self.memory_updater.save()

            print(f"  - 已清空 {year_month} 的日终记忆 ({cleared_count} 条)，本地文件保留")

            # === 以下为保留代码，暂不使用 ===
            # 如需彻底删除本地文件，可启用以下代码：
            #
            # # 删除每日消息文件
            # daily_dir = PathResolver.get_brain_dir(self._current_brain_id) / "history" / "daily"
            # if daily_dir.exists():
            #     for f in daily_dir.glob("*.json"):
            #         date_str = f.stem
            #         if date_str.startswith(year_month):
            #             f.unlink()
            #
            #     for f in daily_dir.glob("*.summary.json"):
            #         date_str = f.stem.replace(".summary", "")
            #         if date_str.startswith(year_month):
            #             f.unlink()
            #
            # # 清理 MessageHistory 中的当月数据
            # if hasattr(self.storage, '_history') and self.storage._history:
            #     for date_key in list(self.storage._history.daily_histories.keys()):
            #         if date_key.startswith(year_month):
            #             del self.storage._history.daily_histories[date_key]
            #     for date_key in list(self.storage._history.daily_summaries.keys()):
            #         if date_key.startswith(year_month):
            #             del self.storage._history.daily_summaries[date_key]

        except Exception as e:
            print(f"Warning: Failed to clear monthly data: {e}")

    # === Brain 切换 ===

    def switch_brain(self, brain_id: str) -> None:
        """切换 Brain 实例。

        Args:
            brain_id: Brain ID
        """
        # 切换 Brain
        self.brain_registry.switch(brain_id)
        self._current_brain_id = brain_id

        # 重置存储和摘要器
        self._storage = None
        self._summarizer = None

        # 检查日期切换
        self._check_and_handle_day_change_sync()

    def create_brain(
        self,
        brain_id: str,
        name: str = "New Persona",
        template: str = "default"
    ) -> BrainComponents:
        """创建新 Brain（UI 调用）。

        Args:
            brain_id: Brain ID
            name: 角色名称
            template: 模板 Brain ID

        Returns:
            新创建的 Brain 组件
        """
        return self.brain_registry.create_brain(brain_id, template, name)

    def list_brains(self) -> list[dict]:
        """列出所有 Brain。

        Returns:
            Brain 信息列表
        """
        result = []
        for brain_id in self.brain_registry.list_brains():
            info = self.brain_registry.get_brain_info(brain_id)
            if info:
                result.append({
                    "id": info.id,
                    "name": info.name,
                    "description": info.description,
                })
        return result

    # === 辅助方法 ===

    def _generate_message_id(self) -> str:
        """生成消息 ID"""
        return f"msg_{int(time.time() * 1000)}"

    async def _call_api(
        self,
        system_prompt: str,
        context: str,
        stream: bool
    ) -> dict:
        """调用 API（异步）"""
        # 使用 api.message.Message 而不是 brain.Message
        messages = [
            ApiMessage(role=ApiMessageRole.SYSTEM, content=system_prompt),
            ApiMessage(role=ApiMessageRole.USER, content=context),
        ]

        response = self.chat_agent.chat(messages, stream=stream)

        if hasattr(response, 'content'):
            return {"content": response.content}
        elif hasattr(response, 'delta'):
            return {"content": response.delta}
        else:
            return {"content": str(response)}

    def _call_api_sync(self, system_prompt: str, context: str) -> dict:
        """调用 API（同步）"""
        # 使用 api.message.Message 而不是 brain.Message
        messages = [
            ApiMessage(role=ApiMessageRole.SYSTEM, content=system_prompt),
            ApiMessage(role=ApiMessageRole.USER, content=context),
        ]

        response = self.chat_agent.chat(messages, stream=False)

        if hasattr(response, 'content'):
            return {"content": response.content}
        else:
            return {"content": str(response)}

    def get_conversation_history(self, days: int = 7) -> list[DaySession]:
        """获取最近 N 天的会话历史。

        Args:
            days: 天数

        Returns:
            DaySession 列表
        """
        return self.storage.get_recent_sessions(days)

    def export_session(self, date: str, format: str = "json") -> str:
        """导出会话数据。

        Args:
            date: 日期
            format: 导出格式 (json/markdown)

        Returns:
            导出内容
        """
        session = self.storage.get_session_by_date(date)
        if not session:
            return ""

        if format == "markdown":
            lines = [f"# {date} 对话记录\n"]
            for msg in session.messages:
                role = "用户" if msg.get("role") == "user" else "助手"
                content = msg.get("content", "")
                lines.append(f"\n## {role}\n{content}\n")
            return "\n".join(lines)
        else:
            return json.dumps(session.to_dict(), ensure_ascii=False, indent=2)

    # === 便捷方法 ===

    def add_message_to_history(
        self,
        role: str,
        content: str,
        tags: Optional[list[str]] = None
    ) -> Message:
        """添加消息到历史。

        Args:
            role: 角色 (user/assistant)
            content: 内容
            tags: 标签

        Returns:
            Message 对象
        """
        components = self.brain_registry.current()
        msg = components.history.add_message(
            content=content,
            role=MessageRole.USER if role == "user" else MessageRole.ASSISTANT,
            tags=tags or [],
        )
        return msg

    def get_today_messages(self) -> list[Message]:
        """获取当日所有消息。

        Returns:
            Message 列表
        """
        return self.storage.get_today_messages()
