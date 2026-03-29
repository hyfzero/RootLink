"""Session Manager 模块 - 核心调度类。

协调所有组件，提供统一的会话管理接口。
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from ..api.client import ChatAgent
from ..api.adapter import ModelConfig
from ..brain import (
    ReplyTag,
    TagGenerator,
    Message,
    MessageRole,
)

from .brain_registry import BrainRegistry, BrainComponents
from .config import SessionConfig
from .path_resolver import PathResolver
from .storage import SessionStorage, DaySession
from .prompt_builder import SessionPromptBuilder
from .reply_tagger import ReplyTagger, MemoryUpdater
from .summarizer import DailySummarizer


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

        # 标签生成器
        if tag_generator is None:
            tag_generator = TagGenerator()
        self.tagger = ReplyTagger(tag_generator)

        # 当前 Brain ID
        self._current_brain_id = brain_registry.current_brain_id()

        # 存储（延迟初始化）
        self._storage: Optional[SessionStorage] = None

        # 日期跟踪
        self._current_date: Optional[str] = None

        # 摘要器（延迟初始化）
        self._summarizer: Optional[DailySummarizer] = None

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
    def prompt_builder(self) -> SessionPromptBuilder:
        """获取当前 Brain 的 PromptBuilder"""
        components = self.brain_registry.current()
        return SessionPromptBuilder(
            persona=components.persona,
            history=components.history,
            style_engine=components.style_engine,
            config=components.config,
        )

    @property
    def memory_updater(self) -> MemoryUpdater:
        """获取记忆更新器"""
        components = self.brain_registry.current()
        return MemoryUpdater(components.persona)

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

        if self._current_date is not None and self._current_date != today:
            # 日期切换：归档
            old_session = self.storage.archive_if_new_day()
            if old_session and old_session.message_count >= self.config.min_messages_for_summary:
                # 同步模式下只归档，不生成摘要
                pass

        self._current_date = today
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

    def _update_memories_from_summary(self, date: str) -> None:
        """从摘要更新记忆。

        Args:
            date: 摘要日期
        """
        try:
            summary_path = PathResolver.get_brain_dir(self._current_brain_id) / "history" / "daily" / f"{date}.summary.json"
            if summary_path.exists():
                import json
                with open(summary_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                self.memory_updater.update_from_summary(data)
        except Exception as e:
            print(f"Warning: Failed to update memories: {e}")

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
        messages = [
            Message(id="system", role=MessageRole.SYSTEM, content=system_prompt, timestamp=0),
            Message(id="context", role=MessageRole.USER, content=context, timestamp=0),
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
        messages = [
            Message(id="system", role=MessageRole.SYSTEM, content=system_prompt, timestamp=0),
            Message(id="context", role=MessageRole.USER, content=context, timestamp=0),
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
            import json
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
