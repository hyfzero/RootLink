"""Agent Core 核心层 - 模型配置和Provider目录模块。

参考 OpenClaw 的 models-config.providers.static.ts 设计，
提供预定义的模型目录和 JSON 配置持久化。

模型信息保存在 models.json 中，包含：
- provider 配置 (base_url, api_key 等)
- 可用模型列表
- 模型元信息 (context_window, max_tokens, cost 等)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import hashlib


# =============================================================================
# 模型目录 (预定义)
# =============================================================================


@dataclass
class ModelCost:
    """模型成本信息。"""

    input: float = 0.0  # 每百万 token 输入成本
    output: float = 0.0  # 每百万 token 输出成本
    cache_read: float = 0.0
    cache_write: float = 0.0


@dataclass
class ModelInfo:
    """单个模型的元信息。"""

    id: str  # 模型标识符
    name: str  # 显示名称
    reasoning: bool = False  # 是否支持思考/推理
    input_types: list[str] = field(default_factory=lambda: ["text"])  # 支持的输入类型
    context_window: int = 128000  # 上下文窗口大小
    max_tokens: int = 8192  # 最大输出 token 数
    cost: ModelCost = field(default_factory=ModelCost)

    tokenizer_mode: str = "auto"
    tokenizer_fallback: str = "hybrid_v1"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "reasoning": self.reasoning,
            "input_types": self.input_types,
            "context_window": self.context_window,
            "max_tokens": self.max_tokens,
            "tokenizer_mode": self.tokenizer_mode,
            "tokenizer_fallback": self.tokenizer_fallback,
            "cost": asdict(self.cost),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModelInfo":
        cost_data = data.get("cost", {})
        cost = ModelCost(
            input=cost_data.get("input", 0.0),
            output=cost_data.get("output", 0.0),
            cache_read=cost_data.get("cache_read", 0.0),
            cache_write=cost_data.get("cache_write", 0.0),
        )
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            reasoning=data.get("reasoning", False),
            input_types=data.get("input_types", ["text"]),
            context_window=data.get("context_window", 128000),
            max_tokens=data.get("max_tokens", 8192),
            tokenizer_mode=data.get("tokenizer_mode", "auto"),
            tokenizer_fallback=data.get("tokenizer_fallback", "hybrid_v1"),
            cost=cost,
        )


@dataclass
class ProviderCatalog:
    """Provider 的模型目录。"""

    models: list[ModelInfo] = field(default_factory=list)

    def find_model(self, model_id: str) -> Optional[ModelInfo]:
        for model in self.models:
            if model.id == model_id:
                return model
        return None

    def to_dict(self) -> dict:
        return {"models": [m.to_dict() for m in self.models]}

    @classmethod
    def from_dict(cls, data: dict) -> "ProviderCatalog":
        models = [ModelInfo.from_dict(m) for m in data.get("models", [])]
        return cls(models=models)


# =============================================================================
# 内置模型目录
# =============================================================================


# MiniMax Provider
MINIMAX_MODELS = ProviderCatalog(
    models=[
        ModelInfo(
            id="MiniMax-M2.5",
            name="MiniMax M2.5",
            reasoning=True,
            input_types=["text"],
            context_window=204800,
            max_tokens=2048,
            cost=ModelCost(input=0.3, output=1.2, cache_read=0.03, cache_write=0.12),
        ),
        ModelInfo(
            id="MiniMax-M2.5-highspeed",
            name="MiniMax M2.5 Highspeed",
            reasoning=True,
            input_types=["text"],
            context_window=204800,
            max_tokens=2048,
            cost=ModelCost(input=0.5, output=2.0, cache_read=0.05, cache_write=0.2),
        ),
        ModelInfo(
            id="MiniMax-VL-01",
            name="MiniMax VL 01",
            reasoning=False,
            input_types=["text", "image"],
            context_window=1000000,
            max_tokens=65536,
            cost=ModelCost(input=0.5, output=2.0, cache_read=0.05, cache_write=0.2),
        ),
        ModelInfo(
            id="abab5.5-chat",
            name="ABAB 5.5 Chat",
            reasoning=False,
            input_types=["text"],
            context_window=245000,
            max_tokens=8192,
            cost=ModelCost(input=0.1, output=0.1),
        ),
    ]
)

# DeepSeek Provider
DEEPSEEK_MODELS = ProviderCatalog(
    models=[
        ModelInfo(
            id="deepseek-v4-flash",
            name="DeepSeek V4 Flash",
            reasoning=False,
            input_types=["text"],
            context_window=128000,
            max_tokens=8192,
            cost=ModelCost(),
        ),
        ModelInfo(
            id="deepseek-v4-pro",
            name="DeepSeek V4 Pro",
            reasoning=False,
            input_types=["text"],
            context_window=128000,
            max_tokens=8192,
            cost=ModelCost(),
        ),
    ]
)

# OpenAI Provider
OPENAI_MODELS = ProviderCatalog(
    models=[
        ModelInfo(
            id="gpt-4o",
            name="GPT-4o",
            reasoning=False,
            input_types=["text", "image"],
            context_window=128000,
            max_tokens=16384,
            cost=ModelCost(input=2.5, output=10.0),
        ),
        ModelInfo(
            id="gpt-4o-mini",
            name="GPT-4o Mini",
            reasoning=False,
            input_types=["text", "image"],
            context_window=128000,
            max_tokens=16384,
            cost=ModelCost(input=0.15, output=0.6),
        ),
        ModelInfo(
            id="gpt-4-turbo",
            name="GPT-4 Turbo",
            reasoning=False,
            input_types=["text", "image"],
            context_window=128000,
            max_tokens=4096,
            cost=ModelCost(input=10.0, output=30.0),
        ),
        ModelInfo(
            id="o1-preview",
            name="o1 Preview",
            reasoning=True,
            input_types=["text"],
            context_window=128000,
            max_tokens=32768,
            cost=ModelCost(input=15.0, output=60.0),
        ),
        ModelInfo(
            id="o1-mini",
            name="o1 Mini",
            reasoning=True,
            input_types=["text"],
            context_window=128000,
            max_tokens=65536,
            cost=ModelCost(input=3.0, output=12.0),
        ),
    ]
)

# Anthropic Provider
ANTHROPIC_MODELS = ProviderCatalog(
    models=[
        ModelInfo(
            id="claude-opus-4-6",
            name="Claude Opus 4.6",
            reasoning=False,
            input_types=["text", "image"],
            context_window=200000,
            max_tokens=8192,
            cost=ModelCost(input=3.0, output=15.0, cache_read=0.3, cache_write=3.75),
        ),
        ModelInfo(
            id="claude-sonnet-4-20250514",
            name="Claude Sonnet 4",
            reasoning=False,
            input_types=["text", "image"],
            context_window=200000,
            max_tokens=8192,
            cost=ModelCost(input=0.003, output=0.015, cache_read=0.0003, cache_write=0.0015),
        ),
        ModelInfo(
            id="claude-3-5-sonnet-latest",
            name="Claude 3.5 Sonnet",
            reasoning=False,
            input_types=["text", "image"],
            context_window=200000,
            max_tokens=8192,
            cost=ModelCost(input=3.0, output=15.0, cache_read=0.3, cache_write=3.75),
        ),
        ModelInfo(
            id="claude-3-5-haiku-latest",
            name="Claude 3.5 Haiku",
            reasoning=False,
            input_types=["text", "image"],
            context_window=200000,
            max_tokens=8192,
            cost=ModelCost(input=0.8, output=4.0, cache_read=0.08, cache_write=1.0),
        ),
    ]
)

# Moonshot/Kimi Provider
MOONSHOT_MODELS = ProviderCatalog(
    models=[
        ModelInfo(
            id="kimi-k2.5",
            name="Kimi K2.5",
            reasoning=False,
            input_types=["text", "image"],
            context_window=256000,
            max_tokens=8192,
            cost=ModelCost(input=0.0, output=0.0),  # 待确认价格
        ),
        ModelInfo(
            id="kimi-k2.5-32k",
            name="Kimi K2.5 32K",
            reasoning=False,
            input_types=["text", "image"],
            context_window=32000,
            max_tokens=32768,
            cost=ModelCost(input=0.0, output=0.0),
        ),
    ]
)

# Ollama Provider (本地模型，cost 为 0)
OLLAMA_MODELS = ProviderCatalog(
    models=[
        ModelInfo(
            id="llama3.1:8b",
            name="Llama 3.1 8B",
            reasoning=False,
            input_types=["text"],
            context_window=128000,
            max_tokens=8192,
            cost=ModelCost(),
        ),
        ModelInfo(
            id="llama3.1:70b",
            name="Llama 3.1 70B",
            reasoning=False,
            input_types=["text"],
            context_window=128000,
            max_tokens=8192,
            cost=ModelCost(),
        ),
        ModelInfo(
            id="qwen2.5:14b",
            name="Qwen 2.5 14B",
            reasoning=False,
            input_types=["text"],
            context_window=128000,
            max_tokens=8192,
            cost=ModelCost(),
        ),
        ModelInfo(
            id="mistral:7b",
            name="Mistral 7B",
            reasoning=False,
            input_types=["text"],
            context_window=128000,
            max_tokens=8192,
            cost=ModelCost(),
        ),
    ]
)

# OpenRouter Provider
OPENROUTER_MODELS = ProviderCatalog(
    models=[
        ModelInfo(
            id="auto",
            name="OpenRouter Auto",
            reasoning=False,
            input_types=["text", "image"],
            context_window=200000,
            max_tokens=8192,
            cost=ModelCost(input=0.0, output=0.0),
        ),
        ModelInfo(
            id="openrouter/hunter-alpha",
            name="Hunter Alpha",
            reasoning=True,
            input_types=["text"],
            context_window=1048576,
            max_tokens=65536,
            cost=ModelCost(input=0.0, output=0.0),
        ),
        ModelInfo(
            id="openrouter/healer-alpha",
            name="Healer Alpha",
            reasoning=True,
            input_types=["text", "image"],
            context_window=262144,
            max_tokens=65536,
            cost=ModelCost(input=0.0, output=0.0),
        ),
    ]
)

# 模型目录注册表
MODEL_CATALOGS: dict[str, ProviderCatalog] = {
    "minimax": MINIMAX_MODELS,
    "deepseek": DEEPSEEK_MODELS,
    "openai": OPENAI_MODELS,
    "anthropic": ANTHROPIC_MODELS,
    "moonshot": MOONSHOT_MODELS,
    "kimi": MOONSHOT_MODELS,  # Kimi 使用 Moonshot 兼容 API
    "ollama": OLLAMA_MODELS,
    "openrouter": OPENROUTER_MODELS,
}


def get_model_catalog(provider: str) -> Optional[ProviderCatalog]:
    """获取 Provider 的模型目录。"""
    return MODEL_CATALOGS.get(provider.lower())


def get_all_providers() -> list[str]:
    """获取所有已注册的 Provider 名称。"""
    return list(MODEL_CATALOGS.keys())


# =============================================================================
# Provider 配置
# =============================================================================


@dataclass
class ProviderConfig:
    """Provider 配置。"""

    base_url: str
    api_key: Optional[str] = None
    api_type: str = "openai"  # openai, anthropic-messages
    auth_header: bool = True  # 是否使用 Authorization header
    headers: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """转换为字典（存储用，包含完整 API Key）。"""
        result = {
            "base_url": self.base_url,
            "api_type": self.api_type,
            "auth_header": self.auth_header,
        }
        if self.api_key:
            result["api_key"] = self.api_key
        if self.headers:
            result["headers"] = self.headers
        return result

    def to_display_dict(self) -> dict:
        """转换为字典（显示用，API Key 被掩码）。"""
        result = {
            "base_url": self.base_url,
            "api_type": self.api_type,
            "auth_header": self.auth_header,
        }
        if self.api_key:
            # 掩码显示
            if len(self.api_key) > 8:
                result["api_key"] = self.api_key[:4] + "****" + self.api_key[-4:]
            else:
                result["api_key"] = "****"
        if self.headers:
            result["headers"] = self.headers
        return result
        if self.headers:
            result["headers"] = self.headers
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "ProviderConfig":
        return cls(
            base_url=data.get("base_url", ""),
            api_key=data.get("api_key"),
            api_type=data.get("api_type", "openai"),
            auth_header=data.get("auth_header", True),
            headers=data.get("headers", {}),
        )


# =============================================================================
# 配置文件结构
# =============================================================================


@dataclass
class ModelsJsonConfig:
    """models.json 配置文件结构。"""

    version: str = "1.0"
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    default_provider: Optional[str] = None
    default_model: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "updated_at": self.updated_at,
            "providers": {k: v.to_dict() for k, v in self.providers.items()},
            "default_provider": self.default_provider,
            "default_model": self.default_model,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModelsJsonConfig":
        providers = {}
        for k, v in data.get("providers", {}).items():
            providers[k] = ProviderConfig.from_dict(v)
        return cls(
            version=data.get("version", "1.0"),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            providers=providers,
            default_provider=data.get("default_provider"),
            default_model=data.get("default_model"),
        )


# =============================================================================
# 持久化操作
# =============================================================================


class ModelsStorage:
    """模型配置的持久化管理。"""

    def __init__(self, config_dir: Optional[str | Path] = None):
        if config_dir is None:
            from ..session.path_resolver import PathResolver

            resolved_config_dir = PathResolver.get_config_dir()
        else:
            resolved_config_dir = Path(config_dir)

        self.config_dir = Path(resolved_config_dir)
        self.models_file = self.config_dir / "models.json"

    def load(self) -> ModelsJsonConfig:
        """加载 models.json 配置。"""
        if not self.models_file.exists():
            return ModelsJsonConfig()

        try:
            with open(self.models_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ModelsJsonConfig.from_dict(data)
        except (json.JSONDecodeError, IOError):
            return ModelsJsonConfig()

    def save(self, config: ModelsJsonConfig) -> None:
        """保存配置到 models.json。"""
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # 原子写入
        temp_file = self.models_file.with_suffix(f".json.tmp.{os.getpid()}")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
            temp_file.replace(self.models_file)
        except Exception:
            if temp_file.exists():
                temp_file.unlink()
            raise

    def add_provider(
        self,
        name: str,
        base_url: str,
        api_key: Optional[str] = None,
        api_type: str = "openai",
        headers: Optional[dict[str, str]] = None,
    ) -> ModelsJsonConfig:
        """添加或更新 Provider。"""
        config = self.load()

        provider = ProviderConfig(
            base_url=base_url,
            api_key=api_key,
            api_type=api_type,
            headers=headers or {},
        )
        config.providers[name] = provider

        # 如果是第一个 provider，设为默认
        if config.default_provider is None:
            config.default_provider = name

        self.save(config)
        return config

    def remove_provider(self, name: str) -> ModelsJsonConfig:
        """移除 Provider。"""
        config = self.load()

        if name in config.providers:
            del config.providers[name]

        if config.default_provider == name:
            config.default_provider = next(iter(config.providers), None)

        self.save(config)
        return config

    def set_default(self, provider: str, model: Optional[str] = None) -> ModelsJsonConfig:
        """设置默认 Provider 和模型。"""
        config = self.load()
        config.default_provider = provider
        if model:
            config.default_model = model
        self.save(config)
        return config

    def get_provider_config(self, name: str) -> Optional[ProviderConfig]:
        """获取 Provider 配置。"""
        config = self.load()
        return config.providers.get(name)

    def list_providers(self) -> list[str]:
        """列出所有配置的 Provider。"""
        config = self.load()
        return list(config.providers.keys())


# =============================================================================
# Provider 工厂函数
# =============================================================================


@dataclass
class ProviderFactoryResult:
    """Provider 工厂函数结果。"""

    name: str
    provider: ProviderConfig
    models: ProviderCatalog


def create_provider_from_catalog(
    provider_name: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    headers: Optional[dict[str, str]] = None,
) -> Optional[ProviderFactoryResult]:
    """从内置目录创建 Provider 配置。"""
    catalog = get_model_catalog(provider_name)
    if not catalog:
        return None

    # 默认 base URL
    default_urls = {
        "minimax": "https://api.minimaxi.com/v1",
        "deepseek": "https://api.deepseek.com",
        "openai": "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com/v1",
        "moonshot": "https://api.moonshot.cn/v1",
        "kimi": "https://api.moonshot.cn/v1",
        "ollama": "http://localhost:11434/v1",
        "openrouter": "https://openrouter.ai/api/v1",
    }

    provider = ProviderConfig(
        base_url=base_url or default_urls.get(provider_name, ""),
        api_key=api_key,
        api_type="anthropic-messages" if provider_name == "anthropic" else "openai",
        headers=headers or {},
    )

    return ProviderFactoryResult(
        name=provider_name,
        provider=provider,
        models=catalog,
    )


# =============================================================================
# 便捷函数
# =============================================================================


def setup_provider(
    name: str,
    api_key: str,
    config_dir: Optional[str | Path] = None,
) -> ModelsJsonConfig:
    """快速设置 Provider。"""
    storage = ModelsStorage(config_dir)

    result = create_provider_from_catalog(name, api_key)
    if not result:
        raise ValueError(f"Unknown provider: {name}")

    return storage.add_provider(
        name=result.name,
        base_url=result.provider.base_url,
        api_key=api_key,
        api_type=result.provider.api_type,
        headers=result.provider.headers,
    )


def list_available_models(provider: Optional[str] = None) -> dict[str, list[ModelInfo]]:
    """列出可用模型。"""
    if provider:
        catalog = get_model_catalog(provider)
        if catalog:
            return {provider: catalog.models}
        return {}

    return {k: v.models for k, v in MODEL_CATALOGS.items()}


def print_models_table(provider: Optional[str] = None) -> None:
    """打印模型表格。"""
    models_dict = list_available_models(provider)

    for prov, models in models_dict.items():
        print(f"\n## {prov.upper()}")
        print(f"{'Model ID':<30} {'Name':<25} {'Context':<12} {'Max Tokens':<12} {'Reasoning':<10}")
        print("-" * 90)
        for m in models:
            print(f"{m.id:<30} {m.name:<25} {m.context_window:<12} {m.max_tokens:<12} {'Yes' if m.reasoning else 'No':<10}")
