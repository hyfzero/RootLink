"""Agent Core 核心层 - 持久化存储模块。

提供JSON和Markdown格式的文件存储功能。
每个模块独立存储文件，便于跨设备同步。

存储结构：
data/
  persona/
    profile.json      # 角色基本配置
    memories.json     # 记忆数据
  history/
    daily/
      YYYY-MM-DD.json      # 每日消息
      YYYY-MM-DD.summary.md # 每日摘要
    queue.json        # 当前队列
    weights.json      # 权重配置
  tags/
    reply_tags.json   # 回复标签缓存
    emotion_map.json  # 情感映射
  config/
    agent_config.json # Agent配置

灵感来源：OpenClaw的session文件存储 (*.jsonl) 和 memory/*.md 格式。
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .persona import Persona
from .history import MessageHistory, DailySummary
from .tags import TagCache, ReplyTag


class FileStorage:
    """基于文件的存储基类。"""

    def __init__(self, base_dir: str = "./data"):
        """初始化文件存储。

        Args:
            base_dir: 数据存储根目录
        """
        self.base_dir = Path(base_dir)
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """创建必要的目录结构。"""
        dirs = [
            "persona",
            "history/daily",
            "tags",
            "config",
        ]
        for d in dirs:
            (self.base_dir / d).mkdir(parents=True, exist_ok=True)

    def _read_json(self, path: Path) -> Optional[dict]:
        """安全读取JSON文件。

        Args:
            path: 文件路径

        Returns:
            文件内容字典，失败返回None
        """
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def _write_json(self, path: Path, data: dict) -> bool:
        """安全写入JSON文件。

        Args:
            path: 文件路径
            data: 要写入的数据

        Returns:
            是否成功
        """
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except (IOError, TypeError):
            return False

    def _read_md(self, path: Path) -> Optional[str]:
        """安全读取Markdown文件。

        Args:
            path: 文件路径

        Returns:
            文件内容字符串，失败返回None
        """
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except IOError:
            return None

    def _write_md(self, path: Path, content: str) -> bool:
        """安全写入Markdown文件。

        Args:
            path: 文件路径
            content: 要写入的内容

        Returns:
            是否成功
        """
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except IOError:
            return False


class PersonaStorage(FileStorage):
    """人格数据存储。"""

    def save_profile(self, persona: Persona) -> bool:
        """保存角色配置。

        Args:
            persona: Persona对象

        Returns:
            是否成功
        """
        path = self.base_dir / "persona" / "profile.json"
        return self._write_json(path, persona.profile.to_dict())

    def load_profile(self) -> Optional[dict]:
        """加载角色配置字典。

        Returns:
            配置字典
        """
        path = self.base_dir / "persona" / "profile.json"
        return self._read_json(path)

    def save_memories(self, persona: Persona) -> bool:
        """保存记忆数据。

        Args:
            persona: Persona对象

        Returns:
            是否成功
        """
        path = self.base_dir / "persona" / "memories.json"
        memories_data = {
            "episodic_memories": [m.to_dict() for m in persona.episodic_memories],
            "preference_memories": [m.to_dict() for m in persona.preference_memories],
            "fact_memories": [m.to_dict() for m in persona.fact_memories],
            "daily_summary_memories": [m.to_dict() for m in persona.daily_summary_memories],
            "monthly_summary_memories": [m.to_dict() for m in persona.monthly_summary_memories],
        }
        return self._write_json(path, memories_data)

    def load_memories(self) -> Optional[dict]:
        """加载记忆数据。

        Returns:
            记忆字典
        """
        path = self.base_dir / "persona" / "memories.json"
        return self._read_json(path)

    def save_state(self, persona: Persona) -> bool:
        """保存运行时人格状态。"""
        path = self.base_dir / "persona" / "state.json"
        return self._write_json(path, persona.state.to_dict())

    def load_state(self) -> Optional[dict]:
        """加载运行时人格状态字典。"""
        path = self.base_dir / "persona" / "state.json"
        return self._read_json(path)

    def save_full(self, persona: Persona) -> bool:
        """保存完整的人格数据。

        Args:
            persona: Persona对象

        Returns:
            是否全部成功
        """
        return self.save_profile(persona) and self.save_memories(persona) and self.save_state(persona)

    def load_full(self) -> Optional[Persona]:
        """加载完整的人格数据。

        Returns:
            Persona对象，加载失败返回None
        """
        profile_data = self.load_profile()
        if not profile_data:
            return None

        from .persona import Persona, PersonaProfile, MemoryEntry, PersonalityState

        profile = PersonaProfile.from_dict(profile_data)
        persona = Persona(profile, state=PersonalityState.from_dict(self.load_state()))

        memories_data = self.load_memories()
        if memories_data:
            for m in memories_data.get("episodic_memories", []):
                persona.episodic_memories.append(MemoryEntry.from_dict(m))
            for m in memories_data.get("preference_memories", []):
                persona.preference_memories.append(MemoryEntry.from_dict(m))
            for m in memories_data.get("fact_memories", []):
                persona.fact_memories.append(MemoryEntry.from_dict(m))
            for m in memories_data.get("daily_summary_memories", []):
                persona.daily_summary_memories.append(MemoryEntry.from_dict(m))
            for m in memories_data.get("monthly_summary_memories", []):
                persona.monthly_summary_memories.append(MemoryEntry.from_dict(m))

        return persona


class HistoryStorage(FileStorage):
    """历史消息存储。"""

    def save_daily_messages(
        self,
        date: str,
        messages: list,
        summary: Optional[DailySummary] = None,
    ) -> bool:
        """保存每日消息到JSON。

        Args:
            date: 日期字符串
            messages: 消息列表
            summary: 可选的每日摘要

        Returns:
            是否成功
        """
        path = self.base_dir / "history" / "daily" / f"{date}.json"
        data = {
            "date": date,
            "messages": [m.to_dict() if hasattr(m, "to_dict") else m for m in messages],
            "summary": summary.to_dict() if summary else None,
        }
        return self._write_json(path, data)

    def load_daily_messages(self, date: str) -> Optional[dict]:
        """加载每日消息。

        Args:
            date: 日期字符串

        Returns:
            消息字典
        """
        path = self.base_dir / "history" / "daily" / f"{date}.json"
        return self._read_json(path)

    def save_daily_summary_md(self, summary: DailySummary) -> bool:
        """保存每日摘要为Markdown（人类可读格式）。

        Args:
            summary: 每日摘要对象

        Returns:
            是否成功
        """
        path = self.base_dir / "history" / "daily" / f"{summary.date}.summary.md"
        content = f"# 每日摘要 - {summary.date}\n\n"
        content += f"## 摘要\n{summary.summary_text}\n\n"
        content += f"## 话题\n{', '.join(summary.topics) if summary.topics else '无'}\n\n"
        content += f"## 统计\n- 消息总数：{summary.message_count}\n"
        content += f"- 重要消息数：{len(summary.important_messages)}\n"
        content += f"- 生成时间：{datetime.fromtimestamp(summary.created_at).strftime('%Y-%m-%d %H:%M:%S')}\n"
        return self._write_md(path, content)

    def save_queue(self, queue_data: dict) -> bool:
        """保存当前队列状态。

        Args:
            queue_data: 队列数据字典

        Returns:
            是否成功
        """
        path = self.base_dir / "history" / "queue.json"
        return self._write_json(path, queue_data)

    def load_queue(self) -> Optional[dict]:
        """加载队列状态。

        Returns:
            队列数据字典
        """
        path = self.base_dir / "history" / "queue.json"
        return self._read_json(path)

    def save_weights(self, weights: dict) -> bool:
        """保存消息权重配置。

        Args:
            weights: 权重配置字典

        Returns:
            是否成功
        """
        path = self.base_dir / "history" / "weights.json"
        return self._write_json(path, weights)

    def load_weights(self) -> Optional[dict]:
        """加载消息权重配置。

        Returns:
            权重配置字典
        """
        path = self.base_dir / "history" / "weights.json"
        return self._read_json(path)

    def save_full_history(self, history: MessageHistory) -> bool:
        """保存完整的历史数据。

        Args:
            history: MessageHistory对象

        Returns:
            是否成功
        """
        # 保存每日消息
        for date_str, daily in history.daily_histories.items():
            self.save_daily_messages(date_str, daily.messages, daily.summary)

        # 保存摘要为Markdown
        for date_str, summary in history.daily_summaries.items():
            self.save_daily_summary_md(summary)

        # 保存队列
        self.save_queue(history.current_queue.to_dict())

        # 保存主索引
        index_path = self.base_dir / "history" / "index.json"
        index_data = {
            "dates": list(history.daily_histories.keys()),
            "summary_dates": list(history.daily_summaries.keys()),
            "last_updated": datetime.now().isoformat(),
        }
        return self._write_json(index_path, index_data)

    def load_full_history(self) -> Optional[MessageHistory]:
        """加载完整的历史数据。

        Returns:
            MessageHistory对象，加载失败返回None
        """
        index_path = self.base_dir / "history" / "index.json"
        index_data = self._read_json(index_path)
        if not index_data:
            return None

        from .history import MessageHistory

        history = MessageHistory()

        # 加载每日历史
        for date_str in index_data.get("dates", []):
            daily_data = self.load_daily_messages(date_str)
            if daily_data:
                from .history import DailyHistory, Message

                daily = DailyHistory(date_str)
                for msg_data in daily_data.get("messages", []):
                    daily.messages.append(Message.from_dict(msg_data))
                summary_data = daily_data.get("summary")
                if summary_data:
                    daily.summary = DailySummary.from_dict(summary_data)
                history.daily_histories[date_str] = daily

        # 加载队列
        queue_data = self.load_queue()
        if queue_data:
            from .history import MessageQueue

            history.current_queue = MessageQueue.from_dict(queue_data)

        return history


class TagsStorage(FileStorage):
    """回复标签存储。"""

    def save_tags(self, cache: TagCache) -> bool:
        """保存标签缓存。

        Args:
            cache: TagCache对象

        Returns:
            是否成功
        """
        path = self.base_dir / "tags" / "reply_tags.json"
        return self._write_json(path, cache.to_dict())

    def load_tags(self) -> Optional[TagCache]:
        """加载标签缓存。

        Returns:
            TagCache对象
        """
        path = self.base_dir / "tags" / "reply_tags.json"
        data = self._read_json(path)
        if not data:
            return None
        return TagCache.from_dict(data)

    def save_tag(self, tag: ReplyTag) -> bool:
        """保存单条标签。

        Args:
            tag: ReplyTag对象

        Returns:
            是否成功
        """
        cache = self.load_tags() or TagCache()
        cache.add(tag)
        return self.save_tags(cache)

    def save_emotion_map(self, emotion_map: dict) -> bool:
        """保存自定义情感映射。

        Args:
            emotion_map: 情感映射字典

        Returns:
            是否成功
        """
        path = self.base_dir / "tags" / "emotion_map.json"
        return self._write_json(path, emotion_map)

    def load_emotion_map(self) -> Optional[dict]:
        """加载自定义情感映射。

        Returns:
            情感映射字典
        """
        path = self.base_dir / "tags" / "emotion_map.json"
        return self._read_json(path)


class ConfigStorage(FileStorage):
    """配置存储。"""

    def save_config(self, config: dict) -> bool:
        """保存Agent配置。

        Args:
            config: 配置字典

        Returns:
            是否成功
        """
        path = self.base_dir / "config" / "agent_config.json"
        return self._write_json(path, config)

    def load_config(self) -> Optional[dict]:
        """加载Agent配置。

        Returns:
            配置字典
        """
        path = self.base_dir / "config" / "agent_config.json"
        return self._read_json(path)


class AgentStorage:
    """统一的存储管理器。

    整合所有类型的存储操作。
    """

    def __init__(self, base_dir: str = "./data"):
        """初始化统一存储管理器。

        Args:
            base_dir: 数据存储根目录
        """
        self.persona = PersonaStorage(base_dir)
        self.history = HistoryStorage(base_dir)
        self.tags = TagsStorage(base_dir)
        self.config = ConfigStorage(base_dir)
        self.base_dir = Path(base_dir)

    def save_all_persona(self, persona: Persona) -> bool:
        """保存所有人格数据。

        Args:
            persona: Persona对象

        Returns:
            是否成功
        """
        return self.persona.save_full(persona)

    def load_all_persona(self) -> Optional[Persona]:
        """加载所有人格数据。

        Returns:
            Persona对象
        """
        return self.persona.load_full()

    def save_all_history(self, history: MessageHistory) -> bool:
        """保存所有历史数据。

        Args:
            history: MessageHistory对象

        Returns:
            是否成功
        """
        return self.history.save_full_history(history)

    def load_all_history(self) -> Optional[MessageHistory]:
        """加载所有历史数据。

        Returns:
            MessageHistory对象
        """
        return self.history.load_full_history()

    def save_all_tags(self, cache: TagCache) -> bool:
        """保存所有标签数据。

        Args:
            cache: TagCache对象

        Returns:
            是否成功
        """
        return self.tags.save_tags(cache)

    def load_all_tags(self) -> Optional[TagCache]:
        """加载所有标签数据。

        Returns:
            TagCache对象
        """
        return self.tags.load_tags()
