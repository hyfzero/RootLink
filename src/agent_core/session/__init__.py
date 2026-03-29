"""Agent Core Session Manager 模块 - Prompt 生成与 Brain 反向更新。

提供：
- path_resolver: 三端路径兼容解析
- config: Session 配置定义
- storage: 会话存储管理
- brain_registry: 多 Brain 实例管理
- prompt_builder: Prompt 构建封装
- reply_tagger: 回复标签生成与记忆更新
- summarizer: 日终摘要生成
- manager: 核心调度类
"""

from .config import SessionConfig
from .path_resolver import PathResolver
from .storage import SessionStorage, DaySession
from .brain_registry import BrainRegistry, BrainComponents, BrainInfo
from .prompt_builder import SessionPromptBuilder
from .reply_tagger import ReplyTagger, MemoryUpdater
from .summarizer import DailySummarizer, SyncDailySummarizer
from .manager import SessionManager

__all__ = [
    # 配置
    "SessionConfig",
    # 路径
    "PathResolver",
    # 存储
    "SessionStorage",
    "DaySession",
    # 多 Brain
    "BrainRegistry",
    "BrainComponents",
    "BrainInfo",
    # Prompt
    "SessionPromptBuilder",
    # 标签与记忆
    "ReplyTagger",
    "MemoryUpdater",
    # 摘要
    "DailySummarizer",
    "SyncDailySummarizer",
    # 核心
    "SessionManager",
]
