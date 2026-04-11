# Speaking Style - 说话风格引擎

`speaking_style.py` 让角色回复风格不仅是一个标签，而是由词汇复杂度、句长、标点、口头禅、情绪词和 emoji 偏好共同决定。

## 职责边界

- 管理基础说话风格和情绪修饰器。
- 为 PromptBuilder 输出风格指导段落。
- 提供随机口头禅、情绪词和 emoji 判断。
- 不直接改写 LLM 输出文本。

## 核心对象

- `SpeakingStyle`
  - `vocabulary_level`：`simple`、`common`、`academic`
  - `sentence_length`：`short`、`medium`、`long`、`varied`
  - `exclamation_rate`、`question_rate`、`ellipsis_rate`
  - `filler_words`、`emotion_words`
  - `emoji_usage`、`parenthesis_usage`
- `StyleModifier`
  - 针对情绪临时调整词汇、句长、标点和口头禅。
- `SpeakingStyleEngine`
  - `get_style()`
  - `set_emotion()`
  - `add_emotion_modifier()`
  - `get_filler_word()`
  - `get_emotion_word()`
  - `should_use_exclamation()`
  - `should_use_emoji()`
  - `get_emoji_for_emotion()`
  - `build_style_prompt()`
- 便捷函数：`get_preset_style()`、`list_preset_styles()`

预设风格：

```text
cheerful, gentle, professional, casual, analytical, humorous, tsundere
```

## 典型用法

```python
from agent_core.brain import SpeakingStyle, SpeakingStyleEngine

engine = SpeakingStyleEngine(preset_name="gentle")
prompt_section = engine.build_style_prompt(emotion="happy")

custom = SpeakingStyle(
    vocabulary_level="simple",
    sentence_length="short",
    filler_words=["嗯", "呀"],
    emoji_usage="sparse",
)
custom_engine = SpeakingStyleEngine(base_style=custom)
```

## 注意事项

- `preset_name` 优先于传入的 `base_style`。
- `influence_weight` 控制风格提示的详细程度，权重越低输出越少。
- 风格引擎只是给 LLM 的 Prompt 指导，不保证最终文本严格满足所有概率参数。
