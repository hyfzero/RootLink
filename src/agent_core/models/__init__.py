"""Agent Core 模型配置模块。

提供预定义的模型目录和 JSON 配置持久化。
"""

from .models import (
    # 数据类
    ModelCost,
    ModelInfo,
    ProviderCatalog,
    ProviderConfig,
    ModelsJsonConfig,
    # 存储
    ModelsStorage,
    # 便捷函数
    get_model_catalog,
    get_all_providers,
    setup_provider,
    list_available_models,
    print_models_table,
    # 内置目录
    MINIMAX_MODELS,
    DEEPSEEK_MODELS,
    OPENAI_MODELS,
    GLM_MODELS,
    ANTHROPIC_MODELS,
    MOONSHOT_MODELS,
    OLLAMA_MODELS,
    OPENROUTER_MODELS,
)

__all__ = [
    "ModelCost",
    "ModelInfo",
    "ProviderCatalog",
    "ProviderConfig",
    "ModelsJsonConfig",
    "ModelsStorage",
    "get_model_catalog",
    "get_all_providers",
    "setup_provider",
    "list_available_models",
    "print_models_table",
    "MINIMAX_MODELS",
    "DEEPSEEK_MODELS",
    "OPENAI_MODELS",
    "GLM_MODELS",
    "ANTHROPIC_MODELS",
    "MOONSHOT_MODELS",
    "OLLAMA_MODELS",
    "OPENROUTER_MODELS",
]
