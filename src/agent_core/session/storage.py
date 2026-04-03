"""Session Manager 模块 - 会话存储管理。

以日期为单位存储聊天记录，支持 Token 限制和自动清理。
参考 OpenClaw 的 Token 感知机制。
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from ..brain.history import Message, MessageRole, estimate_tokens
from .config import SessionConfig
from .path_resolver import PathResolver


@dataclass
class DaySession:
    """单日会话数据"""

    date: str                              # YYYY-MM-DD
    messages: list[dict] = field(default_factory=list)  # 使用字典而非 Message 对象便于序列化
    message_count: int = 0
    total_tokens_estimate: int = 0
    summary_generated: bool = False

    def add_message(self, role: str, content: str) -> None:
        """添加消息，带 Token 估算"""
        self.message_count += 1
        token_count = estimate_tokens(content)
        self.total_tokens_estimate += token_count

        self.messages.append({
            "id": f"msg_{self.message_count}_{int(time.time())}",
            "role": role,
            "content": content,
            "timestamp": time.time(),
            "token_count": token_count,
        })

    def needs_compact(self, max_messages: int, max_tokens: int) -> bool:
        """是否需要压缩（超过单日上限）"""
        return (self.message_count > max_messages or
                self.total_tokens_estimate > max_tokens)

    def compact(self, keep_last_n: int) -> None:
        """压缩保留最近 N 条消息"""
        if len(self.messages) > keep_last_n:
            self.messages = self.messages[-keep_last_n:]
            # 重新计算 token
            self.total_tokens_estimate = sum(m.get("token_count", 0) for m in self.messages)

    def get_messages(self) -> list[Message]:
        """获取消息列表（转换为 Message 对象）"""
        return [Message(
            id=m["id"],
            role=MessageRole(m["role"]),
            content=m["content"],
            timestamp=m["timestamp"],
            token_count=m.get("token_count"),
        ) for m in self.messages]

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "date": self.date,
            "messages": self.messages,
            "message_count": self.message_count,
            "total_tokens_estimate": self.total_tokens_estimate,
            "summary_generated": self.summary_generated,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DaySession":
        """从字典创建"""
        session = cls(date=data.get("date", ""))
        session.messages = data.get("messages", [])
        session.message_count = data.get("message_count", 0)
        session.total_tokens_estimate = data.get("total_tokens_estimate", 0)
        session.summary_generated = data.get("summary_generated", False)
        return session


class SessionStorage:
    """会话存储管理器"""

    def __init__(
        self,
        config: SessionConfig,
        resolver: Optional[PathResolver] = None,
        brain_id: str = "default",
        use_msgpack: bool = False
    ):
        """初始化会话存储管理器。

        Args:
            config: Session 配置
            resolver: 路径解析器，不指定则创建默认
            brain_id: Brain ID，用于多 Brain 支持
            use_msgpack: 是否使用 MessagePack 格式
        """
        self.config = config
        self.resolver = resolver or PathResolver()
        self._brain_id = brain_id
        self._use_msgpack = use_msgpack
        self._today_session: Optional[DaySession] = None
        self._current_date: Optional[str] = None

        # 确保目录存在
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """确保必要的目录存在"""
        session_dir = self.resolver.get_session_dir(self._brain_id)
        current_dir = session_dir / "current"
        archive_dir = session_dir / "archive"
        self.resolver.ensure_dir(current_dir)
        self.resolver.ensure_dir(archive_dir)

    def _get_session_path(self, date: str, is_archive: bool = False) -> Path:
        """获取 Session 文件路径"""
        session_dir = self.resolver.get_session_dir(self._brain_id)
        if is_archive:
            year_month = date[:7]  # YYYY-MM
            archive_dir = session_dir / "archive" / year_month
            self.resolver.ensure_dir(archive_dir)
            ext = ".msgpack" if self._use_msgpack else ".json"
            return archive_dir / f"{date}{ext}"
        else:
            ext = ".msgpack" if self._use_msgpack else ".json"
            return session_dir / "current" / f"{date}{ext}"

    def _load(self, path: Path) -> dict:
        """根据格式加载文件"""
        if not path.exists():
            return {}

        if self._use_msgpack and path.suffix == ".msgpack":
            import msgpack
            return msgpack.unpackb(path.read_bytes(), raw=False)
        return json.loads(path.read_text(encoding="utf-8"))

    def _save(self, path: Path, data: dict) -> None:
        """根据格式保存文件"""
        if self._use_msgpack and path.suffix == ".msgpack":
            import msgpack
            path.write_bytes(msgpack.packb(data, use_single_float=True))
        else:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # === 核心操作 ===

    def get_or_create_today(self) -> DaySession:
        """获取或创建当日 Session"""
        today = datetime.now().strftime("%Y-%m-%d")

        if self._today_session is None or self._current_date != today:
            # 尝试从磁盘加载
            session_path = self._get_session_path(today)
            if session_path.exists():
                data = self._load(session_path)
                self._today_session = DaySession.from_dict(data)
            else:
                self._today_session = DaySession(date=today)

            self._current_date = today

        return self._today_session

    def add_message(self, role: str, content: str) -> DaySession:
        """添加消息到当日 Session"""
        session = self.get_or_create_today()
        session.add_message(role, content)

        # 检查是否需要 compact
        if session.needs_compact(self.config.max_messages_per_day, self.config.max_tokens_per_day):
            # 动态计算保留条数
            avg_token = session.total_tokens_estimate // max(session.message_count, 1)
            keep_count = self.config.calculate_keep_count(avg_token)
            session.compact(keep_count)

        # 持久化
        self._save_session(session)
        return session

    def get_today_messages(self) -> list[Message]:
        """获取当日所有消息"""
        session = self.get_or_create_today()
        return session.get_messages()

    def _save_session(self, session: DaySession) -> None:
        """保存 Session 到磁盘"""
        path = self._get_session_path(session.date)
        self._save(path, session.to_dict())

    def archive_if_new_day(self) -> Optional[DaySession]:
        """检查日期是否切换，若是则归档旧 Session"""
        today = datetime.now().strftime("%Y-%m-%d")

        if self._current_date is not None and self._current_date != today:
            # 日期切换，归档旧 Session
            if self._today_session:
                self.archive_session(self._today_session)

            old_session = self._today_session

            # 重置当日 Session
            self._today_session = DaySession(date=today)
            self._current_date = today

            return old_session

        return None

    # === 归档管理 ===

    def archive_session(self, session: DaySession) -> None:
        """归档 Session 到 archive/{year-month}/"""
        archive_path = self._get_session_path(session.date, is_archive=True)
        self._save(archive_path, session.to_dict())

        # 删除 current 中的文件（如果存在）
        current_path = self._get_session_path(session.date, is_archive=False)
        if current_path.exists():
            current_path.unlink()

    def cleanup_old_archives(self) -> int:
        """清理超过保留期的归档，返回删除数量"""
        session_dir = self.resolver.get_session_dir(self._brain_id)
        archive_dir = session_dir / "archive"

        if not archive_dir.exists():
            return 0

        cutoff = datetime.now().timestamp() - (self.config.archive_retention_days * 24 * 3600)
        deleted_count = 0

        for year_month_dir in archive_dir.iterdir():
            if not year_month_dir.is_dir():
                continue

            for file in year_month_dir.iterdir():
                if file.stat().st_mtime < cutoff:
                    file.unlink()
                    deleted_count += 1

        return deleted_count

    # === 批量读取 ===

    def get_recent_sessions(self, days: int = 7) -> list[DaySession]:
        """获取最近 N 天的 Session"""
        sessions = []
        today = datetime.now()

        for i in range(days):
            date = (today - timedelta(days=i)).strftime("%Y-%m-%d")

            # 先尝试 current
            session_path = self._get_session_path(date, is_archive=False)
            if session_path.exists():
                data = self._load(session_path)
                sessions.append(DaySession.from_dict(data))
            else:
                # 再尝试 archive
                session_path = self._get_session_path(date, is_archive=True)
                if session_path.exists():
                    data = self._load(session_path)
                    sessions.append(DaySession.from_dict(data))

        return sessions

    def get_session_by_date(self, date: str) -> Optional[DaySession]:
        """按日期获取 Session"""
        # 先尝试 current
        session_path = self._get_session_path(date, is_archive=False)
        if session_path.exists():
            data = self._load(session_path)
            return DaySession.from_dict(data)

        # 再尝试 archive
        session_path = self._get_session_path(date, is_archive=True)
        if session_path.exists():
            data = self._load(session_path)
            return DaySession.from_dict(data)

        return None

    # === 当前 Brain ID ===

    def switch_brain(self, brain_id: str) -> None:
        """切换 Brain ID（改变存储路径）"""
        self._brain_id = brain_id
        self._today_session = None
        self._current_date = None
        self._ensure_directories()
