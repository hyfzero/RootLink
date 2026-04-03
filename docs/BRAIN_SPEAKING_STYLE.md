# 说话风格引擎 (Speaking Style Engine)

## 概述

说话风格引擎 (`brain/speaking_style.py`) 提供了精细的语言表达控制，让Agent的回复不仅仅是简单的"friendly"标签，而是能够精确控制词汇、句长、标点、口头禅等各个方面。

## 核心组件

### SpeakingStyle

说话风格配置数据类，包含以下属性：

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `vocabulary_level` | str | `"common"` | 词汇复杂度：`simple`/`common`/`academic` |
| `sentence_length` | str | `"varied"` | 句长偏好：`short`/`medium`/`long`/`varied` |
| `exclamation_rate` | float | `0.1` | 感叹号使用频率 (0.0-1.0) |
| `question_rate` | float | `0.15` | 问号使用频率 (0.0-1.0) |
| `ellipsis_rate` | float | `0.05` | 省略号使用频率 (0.0-1.0) |
| `filler_words` | list[str] | `[]` | 口头禅/填充词列表 |
| `emotion_words` | dict | `{}` | 按情绪分类的情绪词 |
| `emoji_usage` | str | `"none"` | emoji偏好：`none`/`sparse`/`适量`/`丰富` |
| `parenthesis_usage` | str | `"sparse"` | 括号偏好：`none`/`sparse`/`适量` |

### SpeakingStyleEngine

说话风格引擎主类，管理角色说话风格。

#### 初始化

```python
from brain import SpeakingStyleEngine, SpeakingStyle, PRESET_STYLES

# 方式1：使用预设风格
engine = SpeakingStyleEngine(preset_name="cheerful")

# 方式2：使用自定义风格
custom_style = SpeakingStyle(
    vocabulary_level="simple",
    sentence_length="short",
    exclamation_rate=0.3,
    filler_words=["嗯", "呀", "哈"],
    emoji_usage="适量",
)
engine = SpeakingStyleEngine(base_style=custom_style)
```

#### 主要方法

| 方法 | 说明 |
|------|------|
| `get_style(emotion)` | 获取当前适用的风格（考虑情绪修饰） |
| `set_emotion(emotion)` | 设置当前情绪 |
| `build_style_prompt(emotion)` | 生成风格指导Prompt片段 |

## 预设风格

| 风格名称 | 描述 | 适用场景 |
|----------|------|----------|
| `cheerful` | 活泼可爱型 | 轻松聊天、娱乐内容 |
| `gentle` | 温柔体贴型 | 关心用户、安慰场景 |
| `professional` | 专业正式型 | 工作场景、技术文档 |
| `casual` | 轻松随意型 | 日常闲聊 |
| `analytical` | 冷静理性型 | 分析问题、解决问题 |
| `humorous` | 幽默风趣型 | 娱乐、调侃 |
| `tsundere` | 高冷傲娇型 | 特定角色扮演 |

## 使用示例

### 基本使用

```python
from brain import SpeakingStyleEngine, get_preset_style

# 创建引擎
engine = SpeakingStyleEngine(preset_name="cheerful")

# 获取风格
style = engine.get_style()
print(f"口头禅: {engine.get_filler_word()}")
print(f"风格指导: {engine.build_style_prompt()}")

# 设置情绪
engine.set_emotion("happy")
happy_style = engine.get_style()
```

### 生成风格Prompt

```python
from brain import SpeakingStyleEngine

engine = SpeakingStyleEngine(preset_name="gentle")

# 生成系统Prompt片段
style_prompt = engine.build_style_prompt()
# 输出: "使用简单易懂的语言，避免生僻词汇。 可以适当使用口头禅：嗯、呀、哦、嗯。 ..."
```

### 情绪修饰器

情绪修饰器会在基础风格上添加临时调整：

```python
from brain import SpeakingStyleEngine, EMOTION_MODIFIERS

engine = SpeakingStyleEngine(preset_name="casual")

# 默认风格
normal_style = engine.get_style()
# 高兴时的风格（感叹号增多，句子变短）
happy_style = engine.get_style("happy")
# 悲伤时的风格（感叹号减少，添加"唉"等口头禅）
sad_style = engine.get_style("sad")
```

### 自定义情绪修饰器

```python
from brain import SpeakingStyleEngine, StyleModifier

engine = SpeakingStyleEngine(preset_name="casual")

# 添加自定义情绪修饰器
custom_modifier = StyleModifier(
    emotion="excited",
    exclamation_boost=0.3,
    sentence_length_shift="down",
    extra_fillers=["太棒了", "绝了"],
)
engine.add_emotion_modifier(custom_modifier)

excited_style = engine.get_style("excited")
```

## 序列化

引擎支持完整的序列化和反序列化：

```python
from brain import SpeakingStyleEngine

engine = SpeakingStyleEngine(preset_name="cheerful")
engine.set_emotion("happy")

# 序列化
data = engine.to_dict()

# 反序列化
restored = SpeakingStyleEngine.from_dict(data)
```

## 与 Persona 集成

说话风格引擎可以与 Persona 模块配合使用：

```python
from brain import Persona, PersonaProfile, SpeakingStyleEngine

# 创建角色
profile = PersonaProfile(
    name="小雪",
    speaking_style="gentle"
)
persona = Persona(profile)

# 创建风格引擎（根据角色配置）
style_engine = SpeakingStyleEngine(preset_name=profile.speaking_style)

# 生成系统提示时加入风格指导
system_prompt = f"""你是{persona.profile.name}。
{style_engine.build_style_prompt()}
"""
```

## 与 PromptBuilder 集成

推荐使用 `PromptBuilder` 的方式集成风格引擎：

```python
from brain import (
    Persona, PersonaProfile,
    SpeakingStyleEngine,
    PromptBuilder,
    MessageHistory,
)

# 初始化
persona = Persona(PersonaProfile(name="小雪"))
history = MessageHistory()
style_engine = SpeakingStyleEngine(preset_name="gentle")

# 在PromptBuilder中注入风格引擎
builder = PromptBuilder(
    persona=persona,
    history=history,
    style_engine=style_engine,
)

# 构建系统Prompt（自动包含风格段落）
system_prompt = builder.build_system_prompt()

# 带情绪的构建
style_engine.set_emotion("happy")
system_prompt_happy = builder.build_system_prompt(emotion="happy")
```

### 便捷函数方式

```python
from brain import build_full_conversation_prompt

prompt = build_full_conversation_prompt(
    persona=persona,
    history=history,
    current_message="今天天气真好",
    style_engine=style_engine,
    emotion="surprised",
)
```
