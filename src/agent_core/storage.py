"""
存储系统
提供JSON文件持久化功能，支持跨设备同步
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .persona import Persona
    from .memory import MemoryManager
    from .history import HistoryManager
    from .tags import TagManager


class Storage:
    """
    统一存储管理器

    功能：
    1. JSON文件持久化
    2. 支持跨设备（通过共享存储路径）
    3. 自动备份
    """

    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)
        self.backup_path = self.base_path / "backups"

    def ensure_directories(self) -> None:
        """确保目录存在"""
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.backup_path.mkdir(parents=True, exist_ok=True)

    def save_agent_data(
        self,
        agent_id: str,
        data: dict,
        create_backup: bool = True,
    ) -> bool:
        """保存Agent数据"""
        self.ensure_directories()

        if create_backup:
            self._create_backup(agent_id)

        try:
            file_path = self.base_path / f"{agent_id}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存数据失败: {e}")
            return False

    def load_agent_data(self, agent_id: str) -> Optional[dict]:
        """加载Agent数据"""
        file_path = self.base_path / f"{agent_id}.json"

        if not file_path.exists():
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"加载数据失败: {e}")
            return None

    def _create_backup(self, agent_id: str) -> None:
        """创建备份"""
        file_path = self.base_path / f"{agent_id}.json"
        if not file_path.exists():
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{agent_id}_{timestamp}.json"
        backup_file = self.backup_path / backup_name

        try:
            shutil.copy2(file_path, backup_file)
            # 只保留最近5个备份
            self._cleanup_backups(agent_id)
        except Exception as e:
            print(f"创建备份失败: {e}")

    def _cleanup_backups(self, agent_id: str, keep_count: int = 5) -> None:
        """清理旧备份"""
        backups = sorted(
            self.backup_path.glob(f"{agent_id}_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        for old_backup in backups[keep_count:]:
            try:
                old_backup.unlink()
            except Exception:
                pass

    def list_agents(self) -> list[str]:
        """列出所有Agent"""
        agents = []
        for file in self.base_path.glob("*.json"):
            if file.stem != "config":  # 排除配置文件
                agents.append(file.stem)
        return agents

    def delete_agent(self, agent_id: str) -> bool:
        """删除Agent数据"""
        file_path = self.base_path / f"{agent_id}.json"
        if file_path.exists():
            try:
                file_path.unlink()
                return True
            except Exception as e:
                print(f"删除失败: {e}")
                return False
        return False


class AgentStorage:
    """
    Agent专用存储
    整合Persona、Memory、History、Tags的持久化
    """

    def __init__(self, storage: "Storage", agent_id: str):
        self.storage = storage
        self.agent_id = agent_id
        self._storage_path = storage.base_path if storage else None

    def save_all(
        self,
        persona: "Optional[Persona]" = None,
        memory_manager: "Optional[MemoryManager]" = None,
        history_manager: "Optional[HistoryManager]" = None,
        tag_manager: "Optional[TagManager]" = None,
    ) -> bool:
        """保存所有组件数据"""
        data = {
            "agent_id": self.agent_id,
            "saved_at": datetime.now().isoformat(),
        }

        if persona:
            data["persona"] = persona.to_dict()

        if memory_manager:
            data["long_term_memories"] = [
                m.to_dict() for m in memory_manager.long_term_memories
            ]

        if history_manager:
            data["daily_summaries"] = {
                k: v.to_dict() for k, v in history_manager.daily_summaries.items()
            }

        if tag_manager:
            data["tagged_replies"] = [
                r.to_dict() for r in tag_manager.tagged_replies
            ]

        return self.storage.save_agent_data(self.agent_id, data)

    def load_all(
        self,
    ) -> tuple[
        "Optional[Persona]",
        "Optional[MemoryManager]",
        "Optional[HistoryManager]",
        "Optional[TagManager]",
    ]:
        """加载所有组件数据"""
        data = self.storage.load_agent_data(self.agent_id)
        if not data:
            return None, None, None, None

        persona = None
        if "persona" in data:
            from .persona import Persona
            persona = Persona.from_dict(data["persona"])

        memory_manager = None
        if "long_term_memories" in data:
            from .memory import Memory, MemoryManager
            memory_manager = MemoryManager(self._storage_path)
            memory_manager.long_term_memories = [
                Memory.from_dict(m) for m in data["long_term_memories"]
            ]

        history_manager = None
        if "daily_summaries" in data:
            from .history import DailySummary, HistoryManager
            history_manager = HistoryManager(self._storage_path)
            history_manager.daily_summaries = {
                k: DailySummary.from_dict(v) for k, v in data["daily_summaries"].items()
            }

        tag_manager = None
        if "tagged_replies" in data:
            from .tags import TaggedReply, TagManager
            tag_manager = TagManager(self._storage_path)
            tag_manager.tagged_replies = [
                TaggedReply.from_dict(r) for r in data["tagged_replies"]
            ]

        return persona, memory_manager, history_manager, tag_manager
