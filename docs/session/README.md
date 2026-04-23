# Session 模块 - 会话调度中心

`agent_core.session` 将 Brain、API 和持久化串成完整聊天回合。它是应用层通常直接使用的运行时入口。

## 职责边界

- 管理当前 Brain、会话存储、摘要器、回复标签器和记忆更新器。
- 处理发送消息、日期/月切换、归档、摘要和导出。
- 封装 Brain PromptBuilder 生成 API 可用上下文。
- 不负责具体 Provider HTTP 请求实现，也不负责 GUI 渲染。

## 核心对象

公共入口：`from agent_core.session import ...`

- `SessionConfig`
- `PathResolver`
- `DaySession`、`SessionStorage`
- `BrainComponents`、`BrainInfo`、`BrainRegistry`
- `SessionPromptBuilder`
- `ReplyTagger`、`MemoryUpdater`
- `DailySummarizer`、`SyncDailySummarizer`
- `SessionManager`

未从顶层导出但存在：

- `MonthlySummarizer`：使用 `from agent_core.session.summarizer import MonthlySummarizer`

## 数据流/存储

```text
data/{brain_id}/session/current/YYYY-MM-DD.json
data/{brain_id}/session/archive/YYYY-MM/YYYY-MM-DD.json
data/{brain_id}/history/summaries/YYYY-MM-DD.summary.md
data/{brain_id}/history/summaries/YYYY-MM.monthly.md
data/{brain_id}/tags/reply_tags.json
data/{brain_id}/persona/memories.json
data/{brain_id}/persona/state.json
```

当前发送链路关键行为（2026-04 更新）：

- 每轮消息都会双轨写入：`SessionStorage`（完整会话文件）+ `MessageHistory`（prompt 上下文历史，持久化到 `history/history.json`）。
- 新进程启动后会优先加载 `history/history.json` 的今日队列；如果该文件缺失且当天 session 文件存在，会从 `session/current/YYYY-MM-DD.json` 恢复今日上下文。
- `SessionPromptBuilder.build_conversation_context()` 只注入最新用户消息，历史段落由 system prompt 统一承载，减少重复 token。
- 回复标签使用 `generate_and_save()`，`reply_tags.json` 每轮持久化。
- 运行时人格状态会在每轮用户/助手消息后更新，并写入 `persona/state.json`。
- 异步日摘要 JSON 与同步字段对齐（含 `topics/user_preferences/unfinished_topics` 等）。

## 典型用法

```python
from agent_core.api import APIProvider, ChatAgent, ModelConfig
from agent_core.brain import TagGenerator
from agent_core.session import BrainRegistry, SessionConfig, SessionManager

model_config = ModelConfig(name="MiniMax-M2.5", provider=APIProvider.MINIMAX)
registry = BrainRegistry()
registry.load_all()

manager = SessionManager(
    config=SessionConfig(model_config=model_config),
    brain_registry=registry,
    chat_agent=ChatAgent(model_config),
    tag_generator=TagGenerator(),
)

result = manager.send_message_sync("晚上好")
```

## 注意事项

- `send_message()` 是异步方法，`send_message_sync()` 是同步方法。
- 同步路径与异步路径都会在日期切换时尝试生成日终摘要（满足 `min_messages_for_summary` 时）。
- 切换 Brain 会重置 storage、summarizer、prompt builder 和 memory updater 缓存。

## 回归测试

```bash
python src/agent_core/tests/test_session_stability.py
```

示例脚本：

```bash
python src/agent_core/tests/generate_kurisu_brain.py
python src/agent_core/tests/session_example.py "谢谢你，红莉栖，今天也拜托你了"
```

`generate_kurisu_brain.py` 会生成 `profile.json`、`memories.json`、`state.json` 和 `speaking_style.json`。`session_example.py` 会加载现有 Brain，发送消息后更新 `state.json`。

## Config Examples (History + Memory + Prompt + Relationship)

`data/{brain_id}/config.json` can now control token estimator strategy, memory injection, and prompt section budgets.

```json
{
  "history": {
    "token_estimator": "hybrid_v1"
  },
  "memory_injection": {
    "enabled": true,
    "total_limit": 8,
    "per_type_limit": {
      "fact": 3,
      "preference": 3,
      "episodic": 2,
      "daily_summary": 1,
      "monthly_summary": 1
    },
    "type_weight": {
      "fact": 1.4,
      "preference": 1.3,
      "episodic": 1.0,
      "daily_summary": 0.7,
      "monthly_summary": 1.1
    },
    "recency_half_life_days": 14.0,
    "min_importance": 0.0,
    "dedupe": true,
    "sticky_contexts": ["project", "deadline"],
    "query_boost": true
  },
  "prompt_budget": {
    "enabled": true,
    "total_tokens": 3000,
    "section_tokens": {
      "identity": 800,
      "style": 400,
      "relationship": 180,
      "memory": 900,
      "history_summary": 700,
      "queue": 900,
      "runtime": 120
    }
  },
  "relationship_state_machine": {
    "enabled": true,
    "default_state": "neutral",
    "initial_score": 0.0,
    "min_score": -100.0,
    "max_score": 100.0,
    "decay_per_turn": 0.02,
    "role_weight": {
      "user": 1.0,
      "assistant": 0.25
    },
    "signal_weights": {
      "positive": 6.0,
      "trust": 8.0,
      "negative": -8.0,
      "conflict": -12.0
    },
    "signal_keywords": {
      "positive": ["谢谢", "喜欢", "支持"],
      "trust": ["信任", "放心", "承诺"],
      "negative": ["讨厌", "烦", "失望"],
      "conflict": ["闭嘴", "滚", "骗子"]
    },
    "states": [
      {"name": "cold", "min_score": -100.0, "max_score": -25.0, "prompt_hint": "保持克制"},
      {"name": "neutral", "min_score": -25.0, "max_score": 20.0, "prompt_hint": "自然交流"},
      {"name": "warm", "min_score": 20.0, "max_score": 60.0, "prompt_hint": "适度关心"},
      {"name": "close", "min_score": 60.0, "max_score": 101.0, "prompt_hint": "强化信任连续性"}
    ]
  }
}
```

`history.token_estimator` defaults to `hybrid_v1`; set `legacy_char_div4` to rollback to previous behavior.

## Model Tokenizer Config

Runtime tokenizer behavior is controlled by `ModelConfig` (API/model layer), not by changing session call signatures:

```python
from agent_core.api.adapter import ModelConfig, APIProvider

cfg = ModelConfig(
    name="gpt-4o",
    provider=APIProvider.OPENAI,
    tokenizer_mode="auto",            # auto | provider | heuristic
    tokenizer_fallback="hybrid_v1",   # hybrid_v1 | legacy_char_div4
)
```

Behavior:

- OpenAI: if `tiktoken` is available -> provider tokenizer counting.
- Otherwise -> fallback heuristic counting.
- MiniMax: request protocol unchanged; usage fields are normalized when returned, else fallback counting.

## Add New Model Checklist (with DeepSeek example)

When adding a new model/provider, follow this order:

1. Register model metadata in `src/agent_core/models/models.py` (`ModelInfo`).
2. Set tokenizer defaults for that model (`tokenizer_mode/tokenizer_fallback`).
3. If provider has tokenizer support, add counter routing; if not, fallback to heuristic.
4. Map provider usage fields in adapter parse logic.
5. Run consistency tests (`PromptBuilder` / `MessageHistory` / `SessionStorage`).

DeepSeek example (fallback-first):

```python
deepseek_cfg = ModelConfig(
    name="deepseek-chat",
    provider=APIProvider.OPENROUTER,  # or your dedicated provider enum when added
    tokenizer_mode="auto",
    tokenizer_fallback="hybrid_v1",
)
```

If a dedicated DeepSeek tokenizer is added later, only extend tokenizer routing + adapter usage mapping. Budget/compact/business logic stays unchanged.
