"""Session Manager 模块 - 多 Brain 实例注册表。

支持多个 Brain 配置（如不同人格）动态切换。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..brain import (
    Persona,
    PersonaProfile,
    PersonalityState,
    MessageHistory,
    SpeakingStyleEngine,
    PromptBuilder,
    AgentConfig,
)
from ..brain.speaking_style import PRESET_STYLES
from .path_resolver import PathResolver


@dataclass
class BrainComponents:
    """Brain 模块组件集合"""
    persona: Persona
    history: MessageHistory
    style_engine: SpeakingStyleEngine
    prompt_builder: PromptBuilder
    config: AgentConfig


@dataclass
class BrainInfo:
    """Brain 信息（供 UI 显示）"""
    id: str
    name: str
    description: str = ""
    avatar: Optional[str] = None


class BrainRegistry:
    """多 Brain 实例注册表（从目录加载）"""

    def __init__(self, base_path: Optional[Path] = None):
        """初始化注册表。

        Args:
            base_path: Brain 数据根目录，不指定则使用默认
        """
        self._brains: dict[str, BrainComponents] = {}
        self._current: Optional[str] = None
        self._base_path = base_path or PathResolver.get_data_dir()
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """确保 Brain 根目录存在"""
        self._base_path.mkdir(parents=True, exist_ok=True)

    def load_all(self) -> list[str]:
        """扫描目录加载所有 Brain，返回 ID 列表。

        目录结构:
            {base_path}/
            ├── default/
            │   ├── persona/
            │   │   ├── profile.json
            │   │   └── memories.json
            │   └── history/
            └── {brain_id}/
                └── ...
        """
        brain_ids = []

        if not self._base_path.exists():
            return brain_ids

        for brain_dir in self._base_path.iterdir():
            if not brain_dir.is_dir():
                continue

            brain_id = brain_dir.name
            try:
                components = self._load_brain_components(brain_dir)
                self._brains[brain_id] = components
                brain_ids.append(brain_id)
            except Exception as e:
                # 加载失败跳过，不影响其他 Brain
                print(f"Warning: Failed to load brain '{brain_id}': {e}")

        if not self._current and self._brains:
            # 默认使用第一个或名为 default 的
            self._current = "default" if "default" in self._brains else next(iter(self._brains))

        return brain_ids

    def _load_brain_components(self, brain_dir: Path) -> BrainComponents:
        """从目录加载单个 Brain 的组件。

        Args:
            brain_dir: Brain 目录路径

        Returns:
            BrainComponents 组件集合
        """
        persona_dir = brain_dir / "persona"
        history_dir = brain_dir / "history"

        # 加载或创建默认配置
        config = self._load_config(brain_dir)

        # 加载 Persona
        persona = self._load_persona(persona_dir, config)

        # 加载或创建 History
        history = self._load_history(history_dir, config)

        # 加载或创建 Style Engine
        speaking_style_str = persona.profile.speaking_style
        # 检查是否是预设风格
        if speaking_style_str in PRESET_STYLES:
            style_engine = SpeakingStyleEngine(preset_name=speaking_style_str)
        else:
            # 使用默认风格，可通过配置自定义
            style_engine = SpeakingStyleEngine(preset_name="gentle")

        # 创建 PromptBuilder
        prompt_builder = PromptBuilder(
            persona=persona,
            history=history,
            style_engine=style_engine,
            config=config,
        )

        return BrainComponents(
            persona=persona,
            history=history,
            style_engine=style_engine,
            prompt_builder=prompt_builder,
            config=config,
        )

    def _load_config(self, brain_dir: Path) -> AgentConfig:
        """加载 Brain 配置"""
        config_path = brain_dir / "config.json"
        if config_path.exists():
            import json
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return AgentConfig.from_dict(data)
        return AgentConfig()

    def _load_persona(self, persona_dir: Path, config: AgentConfig) -> Persona:
        """加载 Persona"""
        profile_path = persona_dir / "profile.json"
        memories_path = persona_dir / "memories.json"
        state_path = persona_dir / "state.json"

        persona_dir.mkdir(parents=True, exist_ok=True)

        if profile_path.exists():
            import json
            with open(profile_path, "r", encoding="utf-8") as f:
                profile_data = json.load(f)
            profile = PersonaProfile.from_dict(profile_data)
        else:
            profile = PersonaProfile(name=config.persona.name)
            profile_data = profile.to_dict()

        persona = Persona(profile)

        if memories_path.exists():
            import json
            with open(memories_path, "r", encoding="utf-8") as f:
                memories_data = json.load(f)
            persona = Persona.from_dict({"profile": profile_data, **memories_data})
        else:
            persona = Persona(profile)

        if state_path.exists():
            import json
            with open(state_path, "r", encoding="utf-8") as f:
                persona.state = PersonalityState.from_dict(json.load(f))

        return persona

    def _load_history(self, history_dir: Path, config: AgentConfig) -> MessageHistory:
        """加载 History"""
        history_dir.mkdir(parents=True, exist_ok=True)
        history_path = history_dir / "history.json"

        if history_path.exists():
            import json
            with open(history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            history = MessageHistory.from_dict(data)
            history.token_estimator = config.history.token_estimator
            return history

        return MessageHistory(
            max_context_tokens=config.history.max_context_tokens,
            token_reserved=config.history.token_reserved,
            retention_days=config.history.retention_days,
            token_estimator=config.history.token_estimator,
        )

    def register(self, brain_id: str, components: BrainComponents) -> None:
        """注册 Brain 实例（手工注册）"""
        self._brains[brain_id] = components

    def switch(self, brain_id: str) -> BrainComponents:
        """切换当前 Brain 实例。

        Args:
            brain_id: Brain ID

        Returns:
            切换后的 Brain 组件
        """
        if brain_id not in self._brains:
            raise KeyError(f"Brain '{brain_id}' not found")
        self._current = brain_id
        return self._brains[brain_id]

    def current(self) -> BrainComponents:
        """获取当前 Brain 实例。

        Returns:
            当前 Brain 组件
        """
        if not self._current or self._current not in self._brains:
            raise RuntimeError("No current brain selected")
        return self._brains[self._current]

    def current_brain_id(self) -> str:
        """获取当前 Brain ID。

        Returns:
            当前 Brain ID
        """
        if not self._current:
            return "default"
        return self._current

    def list_brains(self) -> list[str]:
        """列出所有已注册的 Brain ID。

        Returns:
            Brain ID 列表
        """
        return list(self._brains.keys())

    # === UI 层接口 ===

    def get_brain_info(self, brain_id: str) -> Optional[BrainInfo]:
        """获取 Brain 信息（供 UI 显示）。

        Args:
            brain_id: Brain ID

        Returns:
            Brain 信息
        """
        if brain_id not in self._brains:
            return None

        components = self._brains[brain_id]
        return BrainInfo(
            id=brain_id,
            name=components.persona.profile.name,
            description=components.persona.profile.background[:100] if components.persona.profile.background else "",
        )

    def create_brain(
        self,
        brain_id: str,
        template: str = "default",
        name: str = "New Persona"
    ) -> BrainComponents:
        """创建新 Brain（UI 调用）。

        Args:
            brain_id: 新 Brain ID
            template: 模板 Brain ID，复制其配置
            name: 角色名称

        Returns:
            新创建的 Brain 组件
        """
        if brain_id in self._brains:
            raise ValueError(f"Brain '{brain_id}' already exists")

        new_dir = self._base_path / brain_id
        new_dir.mkdir(parents=True, exist_ok=True)

        if template in self._brains:
            # 复制模板配置
            template_dir = self._base_path / template
            self._copy_directory(template_dir, new_dir)

            # 修改 name
            persona_dir = new_dir / "persona"
            profile_path = persona_dir / "profile.json"
            if profile_path.exists():
                import json
                with open(profile_path, "r", encoding="utf-8") as f:
                    profile_data = json.load(f)
                profile_data["name"] = name
                with open(profile_path, "w", encoding="utf-8") as f:
                    json.dump(profile_data, f, ensure_ascii=False, indent=2)
        else:
            # 创建基础结构
            persona_dir = new_dir / "persona"
            history_dir = new_dir / "history"
            persona_dir.mkdir(parents=True, exist_ok=True)
            history_dir.mkdir(parents=True, exist_ok=True)

            # 创建默认 profile
            import json
            profile_data = {
                "name": name,
                "gender": "unknown",
                "personality_traits": [],
                "background": "",
                "speaking_style": "friendly",
                "interests": [],
            }
            with open(persona_dir / "profile.json", "w", encoding="utf-8") as f:
                json.dump(profile_data, f, ensure_ascii=False, indent=2)

        # 加载并注册
        components = self._load_brain_components(new_dir)
        self._brains[brain_id] = components

        return components

    def _copy_directory(self, src: Path, dst: Path) -> None:
        """递归复制目录"""
        import shutil
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)

    def delete_brain(self, brain_id: str) -> None:
        """删除 Brain（UI 调用）。

        Args:
            brain_id: 要删除的 Brain ID
        """
        if brain_id not in self._brains:
            raise KeyError(f"Brain '{brain_id}' not found")

        if brain_id == self._current:
            raise ValueError("Cannot delete current brain")

        # 从内存移除
        del self._brains[brain_id]

        # 删除目录
        brain_dir = self._base_path / brain_id
        if brain_dir.exists():
            import shutil
            shutil.rmtree(brain_dir)
