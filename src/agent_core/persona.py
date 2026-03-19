"""
Agent人格系统
包含角色基本设定、年龄、性别、生平和记忆
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict


@dataclass
class LifeEvent:
    """人生事件"""
    year: int
    description: str
    importance: int = 5  # 1-10 重要性评分


@dataclass
class Persona:
    """Agent人格配置"""
    name: str = "未命名"
    age: int = 20
    gender: str = "未知"
    personality: str = ""  # 性格描述
    background: str = ""   # 背景故事
    interests: list[str] = field(default_factory=list)
    speaking_style: str = ""  # 说话风格
    life_events: list[LifeEvent] = field(default_factory=list)
    custom_data: dict = field(default_factory=dict)  # 自定义数据

    def to_dict(self) -> dict:
        """转换为字典"""
        data = asdict(self)
        data["life_events"] = [asdict(e) if isinstance(e, LifeEvent) else e for e in self.life_events]
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Persona":
        """从字典创建"""
        if "life_events" in data:
            data["life_events"] = [
                LifeEvent(**e) if isinstance(e, dict) else e
                for e in data["life_events"]
            ]
        return cls(**data)

    def get_prompt_context(self) -> str:
        """生成用于prompt的人格上下文"""
        context_parts = []

        # 基础信息
        context_parts.append(f"名字: {self.name}")
        context_parts.append(f"年龄: {self.age}岁")
        context_parts.append(f"性别: {self.gender}")

        # 性格
        if self.personality:
            context_parts.append(f"性格: {self.personality}")

        # 背景
        if self.background:
            context_parts.append(f"背景: {self.background}")

        # 兴趣
        if self.interests:
            context_parts.append(f"兴趣: {', '.join(self.interests)}")

        # 说话风格
        if self.speaking_style:
            context_parts.append(f"说话风格: {self.speaking_style}")

        # 重要人生事件
        if self.life_events:
            important_events = sorted(
                [e for e in self.life_events if e.importance >= 7],
                key=lambda x: x.year,
                reverse=True
            )[:5]
            if important_events:
                context_parts.append("重要经历:")
                for event in important_events:
                    context_parts.append(f"  - {event.year}年: {event.description}")

        return "\n".join(context_parts)


class PersonaManager:
    """人格管理器"""

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path
        self.current_persona: Optional[Persona] = None

    def create_persona(
        self,
        name: str,
        age: int,
        gender: str,
        personality: str = "",
        background: str = "",
        interests: list[str] = None,
        speaking_style: str = "",
    ) -> Persona:
        """创建新的人格"""
        self.current_persona = Persona(
            name=name,
            age=age,
            gender=gender,
            personality=personality,
            background=background,
            interests=interests or [],
            speaking_style=speaking_style,
        )
        return self.current_persona

    def load_persona(self, persona_id: str) -> Optional[Persona]:
        """从存储加载人格"""
        if not self.storage_path:
            return None

        persona_file = self.storage_path / f"persona_{persona_id}.json"
        if not persona_file.exists():
            return None

        try:
            with open(persona_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.current_persona = Persona.from_dict(data)
                return self.current_persona
        except Exception as e:
            print(f"加载人格失败: {e}")
            return None

    def save_persona(self, persona_id: str) -> bool:
        """保存人格到存储"""
        if not self.storage_path or not self.current_persona:
            return False

        try:
            self.storage_path.mkdir(parents=True, exist_ok=True)
            persona_file = self.storage_path / f"persona_{persona_id}.json"
            with open(persona_file, "w", encoding="utf-8") as f:
                json.dump(self.current_persona.to_dict(), f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存人格失败: {e}")
            return False

    def add_life_event(self, year: int, description: str, importance: int = 5) -> bool:
        """添加人生事件"""
        if not self.current_persona:
            return False

        event = LifeEvent(year=year, description=description, importance=importance)
        self.current_persona.life_events.append(event)
        return True

    def get_persona(self) -> Optional[Persona]:
        """获取当前人格"""
        return self.current_persona

    def update_persona(self, **kwargs) -> bool:
        """更新人格属性"""
        if not self.current_persona:
            return False

        for key, value in kwargs.items():
            if hasattr(self.current_persona, key):
                setattr(self.current_persona, key, value)
        return True
