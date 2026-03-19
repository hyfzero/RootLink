"""
Agent Core - Python核心层
包含Agent人格系统、历史消息机制、消息标签和持久化功能
"""

from .persona import Persona, PersonaManager
from .memory import Memory, MemoryManager, MessageWeight
from .history import HistoryManager, DailySummary, MessageQueue, ChatMessage
from .tags import ReplyTag, ReplyTagType, TagManager, TaggedReply
from .storage import Storage
from .agent import Agent, create_agent

__all__ = [
    "Persona",
    "PersonaManager",
    "Memory",
    "MemoryManager",
    "MessageWeight",
    "HistoryManager",
    "DailySummary",
    "MessageQueue",
    "ChatMessage",
    "ReplyTag",
    "ReplyTagType",
    "TagManager",
    "TaggedReply",
    "Storage",
    "Agent",
    "create_agent",
]
