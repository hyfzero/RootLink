# History - 消息历史与摘要

`history.py` 管理历史消息、当日消息队列、Token 感知上下文选择和每日摘要。它既支持规则摘要，也支持 LLM 驱动摘要。

## 职责边界

- 保存历史消息和每日历史。
- 按角色权重、时间衰减和重要性选择上下文消息。
- 生成或保存每日摘要。
- 不负责跨日归档文件路径；Session 的 `SessionStorage` 负责会话文件生命周期。

## 核心对象

- `MessageRole`：`USER`、`ASSISTANT`、`SYSTEM`、`TOOL`
- `Message`：`id`、`role`、`content`、`timestamp`、`token_count`、`weight`、`is_important`、`tags`、`tool_name`、`reply_to`
- `DailySummary`：摘要文本、重要消息、话题、消息数、情感基调、用户偏好、未完成话题
- `MessageQueue`：当日消息队列，支持阈值 flush
- `DailyHistory`：单日消息和规则摘要
- `MessageHistory`：主历史管理器
- `SummaryGenerator`：同步 LLM 摘要生成器
- `AsyncSummaryGenerator`：异步 LLM 摘要生成器

工具函数：

- `estimate_tokens(text)`
- `calculate_message_weight(message)`
- `detect_importance(content)`
- `generate_summary_with_llm(daily, llm_callable)`
- `generate_daily_summaries_with_llm(history, llm_callable)`

## 数据流/存储

`MessageHistory.get_context_messages()` 的选择逻辑：

```text
Token 预算
  -> 近期每日摘要约占预算一部分
  -> 当前队列消息按权重排序
  -> 在预算内加入消息
  -> 按时间顺序返回
```

`DailySummary` 的 LLM 字段：

- `emotional_tone`
- `user_preferences`
- `unfinished_topics`

## 典型用法

```python
from agent_core.brain import MessageHistory, MessageRole, SummaryGenerator

history = MessageHistory(max_context_tokens=4000, token_reserved=1000)
history.add_message("请记住我喜欢安静的工作环境", MessageRole.USER)
history.add_message("我记住了。", MessageRole.ASSISTANT)

context = history.get_context_messages(max_tokens=2000)

def llm(prompt: str) -> str:
    return '{"summary_text":"示例摘要","important_messages":[],"topics":[],"emotional_tone":"中性","user_preferences":[],"unfinished_topics":[]}'

summary = SummaryGenerator(llm_callable=llm).generate_summary(
    history.today_str,
    history.current_queue.messages,
)
```

## 注意事项

- `estimate_tokens(text, estimator)` 支持两种策略：`hybrid_v1`（默认）和 `legacy_char_div4`（回退）。
- 可在 `data/{brain_id}/config.json` 中通过 `history.token_estimator` 切换估算策略。
- 估算值仍是近似值，不等于 Provider 真实 token 计数。
- `MessageHistory.add_message()` 会对用户消息做重要性关键词检测。
- LLM 摘要失败时，`SummaryGenerator(use_fallback=True)` 会退回规则摘要。

## Model-level Tokenizer Routing

`MessageHistory` now supports model-aware tokenizer routing:

- `tokenizer_mode=auto`: try provider tokenizer first, fallback to heuristic.
- `tokenizer_mode=provider`: force provider tokenizer; if unavailable, warn and fallback.
- `tokenizer_mode=heuristic`: always use heuristic estimator.

Runtime input comes from `ModelConfig`:

```python
from agent_core.api.adapter import ModelConfig, APIProvider
from agent_core.brain import MessageHistory

model_cfg = ModelConfig(
    name="gpt-4o",
    provider=APIProvider.OPENAI,
    tokenizer_mode="auto",
    tokenizer_fallback="hybrid_v1",
)

history = MessageHistory(
    token_estimator="hybrid_v1",
    tokenizer_mode=model_cfg.tokenizer_mode,
    model_config=model_cfg,
)
```

For OpenAI, if optional `tiktoken` is installed, counting uses provider tokenizer (`provider_tokenizer`).
If unavailable, it falls back to heuristic (`heuristic_fallback`).
