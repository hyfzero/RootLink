"""Session Manager 模块 - 回复标签生成与记忆更新。

每次 API 响应时生成 ReplyTag，并更新 Brain 模块的记忆。
"""

import json
import time
from pathlib import Path
from typing import Optional

from ..brain import ReplyTag, TagGenerator, Persona
from .path_resolver import PathResolver


class ReplyTagger:
    """回复标签生成器与记忆更新器。

    委托给 Brain Tags 模块生成标签，同时处理记忆更新。
    """

    def __init__(
        self,
        tag_generator: TagGenerator,
        storage_path: Optional[Path] = None
    ):
        """初始化。

        Args:
            tag_generator: TagGenerator 实例
            storage_path: 标签存储路径，不指定则使用默认
        """
        self.tag_generator = tag_generator
        self._storage_path = storage_path or PathResolver.get_tags_dir()
        self._storage_path.mkdir(parents=True, exist_ok=True)
        self._tags_file = self._storage_path / "reply_tags.json"
        self._tags_cache: dict[str, ReplyTag] = {}
        self._recent_order: list[str] = []
        self._load_tags()

    def _load_tags(self) -> None:
        """从磁盘加载已有标签"""
        if self._tags_file.exists():
            try:
                with open(self._tags_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for msg_id, tag_data in data.get("tags", {}).items():
                    self._tags_cache[msg_id] = ReplyTag.from_dict(tag_data)
                self._recent_order = data.get("recent_order", [])
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_tags(self) -> None:
        """保存标签到磁盘"""
        data = {
            "tags": {k: v.to_dict() for k, v in self._tags_cache.items()},
            "recent_order": self._recent_order[-100:]  # 只保留最近100条
        }
        with open(self._tags_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def generate_tag(
        self,
        message_id: str,
        response_text: str,
        emotion_hint: Optional[str] = None
    ) -> ReplyTag:
        """生成单条回复的标签。

        Args:
            message_id: 消息 ID
            response_text: 回复文本
            emotion_hint: 可选的情绪提示

        Returns:
            ReplyTag 对象
        """
        tag = self.tag_generator.generate_tag(
            message_id=message_id,
            content=response_text,
            context=emotion_hint,
        )

        # 缓存
        self._tags_cache[message_id] = tag
        self._recent_order.append(message_id)
        if len(self._recent_order) > 100:
            self._recent_order = self._recent_order[-100:]

        return tag

    def generate_and_save(
        self,
        message_id: str,
        response_text: str,
        emotion_hint: Optional[str] = None
    ) -> ReplyTag:
        """生成标签并保存到存储。

        Args:
            message_id: 消息 ID
            response_text: 回复文本
            emotion_hint: 可选的情绪提示

        Returns:
            ReplyTag 对象
        """
        tag = self.generate_tag(message_id, response_text, emotion_hint)
        self._save_tags()
        return tag

    def get_tag(self, message_id: str) -> Optional[ReplyTag]:
        """根据消息 ID 获取标签。

        Args:
            message_id: 消息 ID

        Returns:
            ReplyTag 或 None
        """
        return self._tags_cache.get(message_id)

    def get_recent_tags(self, limit: int = 10) -> list[ReplyTag]:
        """获取最近的标签。

        Args:
            limit: 返回数量限制

        Returns:
            ReplyTag 列表
        """
        result = []
        for msg_id in reversed(self._recent_order):
            if msg_id in self._tags_cache:
                result.append(self._tags_cache[msg_id])
                if len(result) >= limit:
                    break
        return result


class MemoryUpdater:
    """记忆更新器 - 更新 Persona 的情景/偏好/事实记忆。

    仅写入 persona/memories.json，不修改 profile.json。
    """

    def __init__(
        self,
        persona: Persona,
        storage_path: Optional[Path] = None
    ):
        """初始化。

        Args:
            persona: Persona 实例
            storage_path: 存储路径，不指定则使用默认
        """
        self.persona = persona
        self._storage_path = storage_path

    def _get_storage_path(self) -> Path:
        """获取存储路径"""
        if self._storage_path:
            return self._storage_path

        # 从 PathResolver 获取
        return PathResolver.get_brain_dir() / "persona" / "memories.json"

    def add_episodic_memory(
        self,
        content: str,
        importance: float = 1.0,
        context: Optional[str] = None
    ) -> None:
        """添加情景记忆。

        Args:
            content: 记忆内容
            importance: 重要性 (0.0-2.0)
            context: 关联上下文
        """
        self.persona.add_memory(
            content=content,
            memory_type="episodic",
            importance=importance,
            context=context,
        )
        self.save()

    def add_preference_memory(
        self,
        content: str,
        importance: float = 1.0,
        context: Optional[str] = None
    ) -> None:
        """添加偏好记忆。

        Args:
            content: 记忆内容
            importance: 重要性 (0.0-2.0)
            context: 关联上下文
        """
        self.persona.add_memory(
            content=content,
            memory_type="preference",
            importance=importance,
            context=context,
        )
        self.save()

    def add_fact_memory(
        self,
        content: str,
        importance: float = 1.0,
        context: Optional[str] = None
    ) -> None:
        """添加事实记忆。

        Args:
            content: 记忆内容
            importance: 重要性 (0.0-2.0)
            context: 关联上下文
        """
        self.persona.add_memory(
            content=content,
            memory_type="fact",
            importance=importance,
            context=context,
        )
        self.save()

    def update_from_summary(self, summary_data: dict) -> None:
        """从日终摘要更新记忆。

        Args:
            summary_data: 摘要数据，包含 user_preferences、unfinished_topics 等
        """
        date_str = summary_data.get("date", "")

        # 更新用户偏好 - 较低 importance
        for pref in summary_data.get("user_preferences", []):
            self.add_preference_memory(
                content=f"用户偏好: {pref}",
                importance=0.5,  # 较低 importance
                context=f"日终摘要-{date_str}"
            )

        # 更新未完成话题
        for topic in summary_data.get("unfinished_topics", []):
            self.add_episodic_memory(
                content=f"未完成话题: {topic}",
                importance=0.8,
                context=f"日终摘要-{date_str}"
            )

        # 更新关键事件（如果有）
        for event in summary_data.get("important_messages", []):
            self.add_episodic_memory(
                content=f"重要事件: {event}",
                importance=1.0,
                context=f"日终摘要-{date_str}"
            )

    def update_from_monthly_summary(self, monthly_data: dict) -> None:
        """从月度总结更新记忆。

        月度总结以较高 importance 加入。

        Args:
            monthly_data: 月度总结数据
        """
        year_month = monthly_data.get("year_month", "")

        # 更新主要事件 - 高 importance
        for event in monthly_data.get("major_events", []):
            self.add_episodic_memory(
                content=f"【{year_month}】重要事件: {event}",
                importance=1.8,
                context=f"月度总结-{year_month}"
            )

        # 更新长期偏好 - 高 importance
        for pref in monthly_data.get("user_long_term_preferences", []):
            self.add_preference_memory(
                content=f"用户长期偏好: {pref}",
                importance=1.8,
                context=f"月度总结-{year_month}"
            )

        # 更新月度话题
        for topic in monthly_data.get("monthly_topics", []):
            self.add_episodic_memory(
                content=f"【{year_month}】主要话题: {topic}",
                importance=1.5,
                context=f"月度总结-{year_month}"
            )

        # 更新成长或变化
        for change in monthly_data.get("growth_or_change", []):
            self.add_episodic_memory(
                content=f"【{year_month}】用户变化: {change}",
                importance=1.5,
                context=f"月度总结-{year_month}"
            )

    def save(self) -> None:
        """保存记忆到磁盘"""
        storage_path = self._get_storage_path()
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "episodic_memories": [m.to_dict() for m in self.persona.episodic_memories],
            "preference_memories": [m.to_dict() for m in self.persona.preference_memories],
            "fact_memories": [m.to_dict() for m in self.persona.fact_memories],
            "updated_at": time.time(),
        }

        with open(storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self) -> None:
        """从磁盘加载记忆"""
        storage_path = self._get_storage_path()
        if not storage_path.exists():
            return

        with open(storage_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        from ..brain import MemoryEntry

        self.persona.episodic_memories = [
            MemoryEntry.from_dict(m) for m in data.get("episodic_memories", [])
        ]
        self.persona.preference_memories = [
            MemoryEntry.from_dict(m) for m in data.get("preference_memories", [])
        ]
        self.persona.fact_memories = [
            MemoryEntry.from_dict(m) for m in data.get("fact_memories", [])
        ]
