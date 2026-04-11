# Tags - 回复标签与情感解析

`tags.py` 为每条回复生成 `ReplyTag`，供 GUI 决定角色立绘表情、动作、姿态和特效层。

## 职责边界

- 根据回复文本检测情感、表情、动作、特效和强度。
- 支持关键词模式和 LLM 模式。
- 提供最近标签缓存。
- 不负责把标签写到 Session 文件；Session 的 `ReplyTagger` 负责保存。

## 核心对象

- `ReplyTag`
  - 字段：`message_id`、`emotion`、`expression`、`action`、`pose`、`overlays`、`intensity`、`timestamp`
  - 方法：`to_dict()`、`from_dict()`
- `TagGenerator`
  - `set_emotion_mode("keyword" | "llm")`
  - `set_llm_callable()`
  - `detect_emotion()`
  - `detect_expression()`
  - `detect_action()`
  - `detect_overlays()`
  - `calculate_intensity()`
  - `generate_tag()`
- `TagCache`
  - `add()`
  - `get()`
  - `get_recent()`

支持情感：

```text
happy, sad, angry, surprised, thinking, scared, embarrassed, confused, neutral
```

## 数据流/存储

```text
assistant response text
  -> TagGenerator.generate_tag()
  -> ReplyTag
  -> Session ReplyTagger 保存到 data/{brain_id}/tags/reply_tags.json
  -> GUI 根据 emotion/expression/action/overlays 更新立绘
```

## 典型用法

```python
from agent_core.brain import TagGenerator

generator = TagGenerator(emotion_mode="keyword")
tag = generator.generate_tag(
    message_id="msg_1",
    content="太好了，这个问题终于解决了！",
)

print(tag.emotion, tag.expression, tag.overlays)
```

LLM 模式：

```python
from agent_core.brain import TagGenerator

generator = TagGenerator(llm_callable=lambda prompt: '{"emotion":"happy","confidence":0.9}')
generator.set_emotion_mode("llm")
```

## 注意事项

- 关键词模式速度快、无需外部调用，但语义细节有限。
- LLM callable 必须返回可解析的情感结果；失败时实现会回退默认情感。
- `intensity` 会受增强词、弱化词、感叹号和问号影响。
