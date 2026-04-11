# Summarizer And Memory - 摘要、标签与记忆回写

`summarizer.py` 生成日终和月终摘要，`reply_tagger.py` 生成回复标签并把摘要提取的信息写回 Persona 记忆。

## 职责边界

- `DailySummarizer` 和 `MonthlySummarizer` 调用 LLM 并保存摘要文件。
- `SyncDailySummarizer` 用同步 callable 生成日摘要。
- `ReplyTagger` 生成并保存回复标签。
- `MemoryUpdater` 写入 `persona/memories.json`。
- 何时触发摘要由 `SessionManager` 决定。

## 核心对象

顶层导出：

- `DailySummarizer`
- `SyncDailySummarizer`
- `ReplyTagger`
- `MemoryUpdater`

明确子模块导入：

```python
from agent_core.session.summarizer import MonthlySummarizer
```

主要方法：

- `DailySummarizer.generate_summary(date, messages, persona_context="")`
- `MonthlySummarizer.generate_summary(year_month, daily_summaries, persona_context="")`
- `SyncDailySummarizer.generate_summary(date, messages, persona_context="")`
- `ReplyTagger.generate_tag()`、`generate_and_save()`、`get_recent_tags()`
- `MemoryUpdater.add_episodic_memory()`、`add_preference_memory()`、`add_fact_memory()`
- `MemoryUpdater.add_daily_summary_memory()`、`add_monthly_summary_memory()`
- `MemoryUpdater.update_from_summary()`、`update_from_monthly_summary()`

## 数据流/存储

日摘要输出：

```text
data/{brain_id}/history/summaries/YYYY-MM-DD.summary.md
data/{brain_id}/history/daily/YYYY-MM-DD.summary.json
```

月摘要输出：

```text
data/{brain_id}/history/summaries/YYYY-MM.monthly.md
data/{brain_id}/history/summaries/YYYY-MM.monthly.json
```

标签和记忆：

```text
data/{brain_id}/tags/reply_tags.json
data/{brain_id}/persona/memories.json
```

## 典型用法

```python
from agent_core.brain import TagGenerator
from agent_core.session import ReplyTagger

tagger = ReplyTagger(TagGenerator())
tag = tagger.generate_and_save(
    message_id="msg_1",
    response_text="太好了，已经完成了！",
)
```

月摘要：

```python
from agent_core.session.summarizer import MonthlySummarizer

monthly = MonthlySummarizer(chat_agent, output_dir)
data = await monthly.generate_summary("2026-04", daily_summaries)
```

## 注意事项

- 摘要 Prompt 要求 LLM 返回 JSON；解析后会格式化为 Markdown。
- `MemoryUpdater` 会把用户偏好、未完成话题、重要消息和月度变化拆成不同类型记忆。
- 摘要失败不应阻塞主聊天流程，调用方应记录错误并继续。
