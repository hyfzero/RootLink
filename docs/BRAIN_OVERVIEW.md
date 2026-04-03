# Brain 模块

Agent的核心人格层，负责管理角色人格、记忆、说话风格和对话历史。

## 模块结构

```
brain/
├── __init__.py           # 统一导出入口
├── persona.py            # 角色人格和记忆管理
├── history.py            # 历史消息管理（含LLM摘要）
├── tags.py               # 回复表情/动作标签
├── config.py             # 配置管理
├── persistence.py        # 文件持久化
├── prompt_builder.py     # 分段式Prompt构建
├── speaking_style.py     # 说话风格引擎
└── *.md                  # 文档
```

## 核心模块

### [Persona - 人格管理](BRAIN_PERSONA.md)

管理Agent的静态人格配置和动态记忆。

```python
from brain import Persona, PersonaProfile, MemoryEntry

profile = PersonaProfile(
    name="小雪",
    age=18,
    personality_traits=["温柔", "体贴", "有点害羞"],
    speaking_style="gentle",
)
persona = Persona(profile)

# 添加记忆
persona.add_memory(
    content="用户喜欢在晚上听轻音乐",
    memory_type="preference",
    importance=1.5,
)
```

### [History - 历史消息管理](BRAIN_HISTORY.md)

Token感知的消息管理，支持LLM驱动的每日摘要。

```python
from brain import MessageHistory, MessageRole, SummaryGenerator

history = MessageHistory(max_context_tokens=4000)

history.add_message(
    content="今天天气真好",
    role=MessageRole.USER,
    is_important=False,
)

# 使用LLM生成摘要
def llm_callable(prompt):
    return openai.complete(prompt)

generator = SummaryGenerator(llm_callable=llm_callable)
summary = generator.generate_summary("2026-03-24", history.current_queue.messages)
```

### [Tags - 回复标签](BRAIN_TAGS.md)

基于关键词的情感/表情/动作标签生成，用于UI层显示角色立绘。

```python
from brain import TagGenerator

generator = TagGenerator()
tag = generator.generate_tag(
    message_id="msg_1",
    content="太开心了！今天考试通过了！",
)
# tag.emotion = "happy"
# tag.expression = "smile"
# tag.overlays = ["blush"]
```

### [Speaking Style - 说话风格引擎](BRAIN_SPEAKING_STYLE.md)

精细控制Agent的语言表达风格。

```python
from brain import SpeakingStyleEngine, PRESET_STYLES

# 使用预设风格
engine = SpeakingStyleEngine(preset_name="cheerful")

# 生成风格指导Prompt
style_prompt = engine.build_style_prompt(emotion="happy")
```

### [LLM Summary - LLM驱动的记忆总结](BRAIN_LLM_SUMMARY.md)

使用大语言模型生成高质量的对话摘要。

```python
from brain.history import SummaryGenerator, generate_daily_summaries_with_llm

def llm_callable(prompt):
    return openai.complete(prompt)

# 为所有历史生成LLM摘要
summaries = generate_daily_summaries_with_llm(history, llm_callable=llm_callable)
```

## 配置管理

```python
from brain import AgentConfig

config = AgentConfig(
    persona={"name": "小雪", "age": 18},
    history={"max_context_tokens": 4000},
    tags={"auto_generate": True},
    storage={"data_dir": "./data", "format": "json"},
)
```

## 持久化

```python
from brain import AgentStorage

storage = AgentStorage(base_dir="./data")

# 保存
storage.save_all_persona(persona)
storage.save_all_history(history)
storage.save_all_tags(tag_cache)

# 加载
persona = storage.load_all_persona()
history = storage.load_all_history()
```

## Prompt构建

```python
from brain import PromptBuilder, SpeakingStyleEngine

# 创建风格引擎
style_engine = SpeakingStyleEngine(preset_name="gentle")

# 创建PromptBuilder时注入风格引擎
builder = PromptBuilder(
    persona=persona,
    history=history,
    style_engine=style_engine,
)

# 构建完整系统Prompt（可指定当前情绪）
system_prompt = builder.build_system_prompt(emotion="happy")

# 构建上下文Prompt
context_prompt = builder.build_context_prompt(
    query="用户偏好",
    include_queue=True,
    emotion="surprised",
)
```

### 说话风格段落示例

构建后的prompt中会包含以下风格段落：

```
## 身份定义
你叫小雪。年龄：18岁。性格特点：温柔、体贴。说话风格：gentle。

## 说话风格
使用简单易懂的语言，避免生僻词汇。可以适当使用口头禅：嗯、呀、哦。...

## 近期记忆
...

## 当前时间
...
```

## 与 API 层集成

```python
from brain import Persona, PersonaProfile, MessageHistory
from api import ChatAgent, ProviderManager

# 初始化
persona = Persona(PersonaProfile(name="小雪"))
history = MessageHistory()

# API调用
manager = ProviderManager.from_env()
agent = manager.get_agent()
response = agent.chat([
    Message(role=MessageRole.SYSTEM, content=system_prompt),
    Message(role=MessageRole.USER, content=user_message),
])
```
