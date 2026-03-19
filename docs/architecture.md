# Godot Amadeus AI 聊天软件 - 架构设计文档

## 一、项目概述

基于 OpenClaw 架构思想，使用 Godot 引擎实现一个简化版的 Amadeus 人格模拟聊天应用。

### 核心目标

- 模拟《命运石之门》中 Amadeus 系统的核心功能
- 创建一个具有人格（Profile）和记忆（Memory）的 AI 聊天软件
- 比 OpenClaw 更聚焦：单一 Agent、无多渠道、专注人格模拟

### 与 OpenClaw 对比

| 特性 | OpenClaw | Godot Amadeus |
|------|----------|---------------|
| 目标 | 多渠道 AI 助手 | 人格模拟聊天 |
| Agent | 通用任务 Agent | 特定人格 Agent |
| Memory | 工具调用记忆 | 事件/语义记忆 |
| Profile | 工具能力集 | 人格数据 |
| 复杂度 | 高（20+ 渠道） | 低（单一界面） |

---

## 二、系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         UI Layer (Godot)                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │  ChatView  │  │ ProfileView │  │ MemoryTimelineView     │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Agent Controller                            │
│  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────┐  │
│  │ MessageHandler  │  │ PromptBuilder    │  │ ResponseGen   │  │
│  └─────────────────┘  └─────────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Core Systems                                │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────────┐  │
│  │ Profile System │  │ Memory System  │  │ LLM Connector    │  │
│  │ (人格定义)      │  │ (记忆管理)     │  │ (API 调用)       │  │
│  └───────────────┘  └───────────────┘  └───────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、核心模块设计

### 3.1 Profile System（人格配置）

PersonProfile 是人格的核心定义，参考 OpenClaw 的 system-prompt.ts 设计。

#### 数据结构

```gdscript
class_name PersonProfile
extends Resource

@export var name: String                    # 人格名称（如 "牧濑红莉栖"）
@export var display_name: String            # 显示名称
@export var description: String             # 人格简介
@export var personality_traits: Array[String]  # 性格特点数组
@export var speaking_style: String          # 说话风格描述
@export var background_story: String         # 背景故事（重要记忆点）
@export var knowledge_base: Array[String]    # 知识范围
@export var relationships: Dictionary       # 与用户的关系设定
@export var restrictions: Array[String]      # 行为限制
@export var avatar_path: String              # 头像资源路径
@export var voice_config: Dictionary         # 语音配置（TTS/STT）
```

#### System Prompt 构建

```gdscript
func build_system_prompt() -> String:
    return """你是 %s。

简介: %s

性格: %s

说话风格: %s

背景: %s

知识范围: %s

你与用户的关系: %s

请始终保持 %s 的人格特征进行对话。在回答时，考虑你们之前对话中形成的记忆和关系发展。
""" % [
    name,
    description,
    ", ".join(personality_traits),
    speaking_style,
    background_story,
    ", ".join(knowledge_base),
    relationships.get("default", "朋友"),
    name
]
```

#### 人格示例（牧濑红莉栖）

```json
{
    "name": "牧濑红莉栖",
    "display_name": "红莉栖",
    "description": "18岁，天才少女物理学家，BHS研究会的成员。",
    "personality_traits": [
        "傲娇",
        "理性",
        "毒舌",
        "外表坚强内心温柔",
        "对感兴趣的事物会变得热情"
    ],
    "speaking_style": "使用关西腔，语气直接，有时会吐槽。经常使用「笨蛋」等称呼。对物理相关话题会变得认真。",
    "background_story": "9岁时在俄罗斯发表物理论文，被视为天才。17岁时父亲去世。与母亲关系疏远。",
    "knowledge_base": [
        "物理学",
        "量子力学",
        "脑科学",
        "日常吐槽",
        "动漫宅"
    ],
    "relationships": {
        "default": "朋友",
        "dialogue": "根据对话发展逐渐变化"
    }
}
```

---

### 3.2 Memory System（记忆系统）

Memory 是 Amadeus 的核心，参考人类记忆的分类方式设计。

#### 记忆类型

```gdscript
enum MemoryType {
    EPISODIC,    # 事件记忆 - 具体的对话/事件
    SEMANTIC,    # 语义记忆 - 知识/事实
    WORKING      # 工作记忆 - 当前会话的短期记忆
}
```

#### 记忆条目

```gdscript
class_name MemoryEntry
extends Resource

@export var id: String                      # 唯一标识
@export var type: MemoryType                 # 记忆类型
@export var content: String                  # 记忆内容
@export var timestamp: DateTime              # 时间戳
@export var importance: float                 # 重要程度 (0.0-1.0)
@export var emotional_tag: String            # 情感标签（开心/难过/生气等）
@export var keywords: Array[String]          # 关键词索引
@export var related_memory_ids: Array[String] # 关联记忆
@export var user_sentiment: float            # 用户情感倾向 (-1.0 到 1.0)
```

#### 记忆管理器

```gdscript
class_name MemoryManager
extends Node

# 存储
var episodic_memory: Array[MemoryEntry] = []
var semantic_memory: Array[MemoryEntry] = []
var working_memory: Array[MemoryEntry] = []  # 当前会话

# 配置
const MAX_WORKING_MEMORY = 10        # 工作记忆上限
const MAX_EPISODIC_STORAGE = 1000   # 长期记忆上限
const RECALL_LIMIT = 5              # 检索返回数量

# 添加记忆
func add_memory(entry: MemoryEntry) -> void:
    match entry.type:
        MemoryType.EPISODIC:
            episodic_memory.append(entry)
            _prune_if_needed()
        MemoryType.SEMANTIC:
            semantic_memory.append(entry)
        MemoryType.WORKING:
            working_memory.append(entry)
            _prune_working_memory()

# 记忆检索 - 基于关键词和重要性
func recall(query: String, limit: int = RECALL_LIMIT) -> Array[MemoryEntry]:
    var results: Array[MemoryEntry] = []
    var search_pool = working_memory + episodic_memory

    for memory in search_pool:
        if _matches_query(query, memory):
            results.append(memory)

    # 按重要性和时间排序
    results.sort_custom(func(a, b):
        if abs(a.importance - b.importance) > 0.1:
            return a.importance > b.importance
        return a.timestamp > b.timestamp

    return results.slice(0, limit)

# 构建发送给 LLM 的记忆上下文
func build_memory_context() -> String:
    if working_memory.is_empty():
        return ""

    var context = "以下是你们之前的对话记忆:\n\n"

    for memory in working_memory:
        var time_str = _format_timestamp(memory.timestamp)
        var emotion = "[%s]" % memory.emotional_tag if memory.emotional_tag else ""
        context += "%s %s\n%s\n\n" % [time_str, emotion, memory.content]

    return context

# 工作记忆 → 长期记忆（会话结束时调用）
func consolidate_to_long_term() -> void:
    for memory in working_memory:
        if memory.importance > 0.5:  # 重要记忆才保存
            memory.type = MemoryType.EPISODIC
            episodic_memory.append(memory)
    working_memory.clear()

func _matches_query(query: String, memory: MemoryEntry) -> bool:
    var query_lower = query.to_lower()

    # 内容包含
    if query_lower in memory.content.to_lower():
        return true

    # 关键词匹配
    for keyword in memory.keywords:
        if keyword.to_lower() in query_lower:
            return true

    return false

func _prune_working_memory() -> void:
    if working_memory.size() > MAX_WORKING_MEMORY:
        # 保留重要的，移除最旧的
        working_memory.sort_custom(func(a, b):
            if abs(a.importance - b.importance) > 0.1:
                return a.importance > b.importance
            return a.timestamp > b.timestamp)
        working_memory = working_memory.slice(0, MAX_WORKING_MEMORY)

func _prune_if_needed() -> void:
    if episodic_memory.size() > MAX_EPISODIC_STORAGE:
        # 移除最低重要性的记忆
        episodic_memory.sort_custom(func(a, b):
            return a.importance > b.importance)
        episodic_memory = episodic_memory.slice(0, MAX_EPISODIC_STORAGE)

func _format_timestamp(dt: DateTime) -> String:
    return "%04d-%02d-%02d %02d:%02d" % [dt.year, dt.month, dt.day, dt.hour, dt.minute]
```

---

### 3.3 LLM Connector（AI 连接层）

支持多种 LLM 提供商。

```gdscript
class_name LLMConnector
extends Node

enum Provider {
    OPENAI,
    ANTHROPIC,
    OLLAMA,
    CUSTOM
}

@export var provider: Provider = Provider.OPENAI
@export var api_key: String
@export var base_url: String = "https://api.openai.com/v1"
@export var model: String = "gpt-4"
@export var temperature: float = 0.8
@export var max_tokens: int = 1000

var http_client: HTTPRequest
var pending_callback: Callable

signal response_received(content: String)
signal error_occurred(message: String)

func _ready():
    http_client = HTTPRequest.new()
    add_child(http_client)
    http_client.request_completed.connect(_on_request_completed)

func send_message(messages: Array[Dictionary], callback: Callable) -> void:
    pending_callback = callback

    var payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": false
    }

    var headers = [
        "Authorization: Bearer %s" % api_key,
        "Content-Type: application/json"
    ]

    var url = base_url
    match provider:
        Provider.OPENAI:
            url += "/chat/completions"
        Provider.ANTHROPIC:
            url = "https://api.anthropic.com/v1/messages"
            payload["system"] = messages[0]["content"] if messages and messages[0].has("role") and messages[0]["role"] == "system" else ""

    var error = http_client.request(url, headers, HTTPClient.METHOD_POST, JSON.stringify(payload))
    if error != OK:
        error_occurred.emit("请求失败: " % error)

func _on_request_completed(result, response_code, headers, body):
    if response_code != 200:
        error_occurred.emit("API 错误: %d" % response_code)
        return

    var json = JSON.parse_string(body.get_string_from_utf8())
    # 解析响应并调用 callback
    var content = _extract_content(json)
    pending_callback.call(content)

func _extract_content(response: Dictionary) -> String:
    match provider:
        Provider.OPENAI:
            if response.has("choices") and response["choices"].size() > 0:
                return response["choices"][0]["message"]["content"]
        Provider.ANTHROPIC:
            if response.has("content"):
                return response["content"][0]["text"]
    return ""
```

---

### 3.4 Prompt Builder（提示词构建）

参考 OpenClaw 的模块化 Prompt 设计。

```gdscript
class_name PromptBuilder
extends Node

@export var profile: PersonProfile
@export var memory_manager: MemoryManager

func build_prompt(user_message: String) -> Array[Dictionary]:
    var messages: Array[Dictionary] = []

    # 1. System Message
    messages.append({
        "role": "system",
        "content": _build_system_prompt()
    })

    # 2. Memory Context
    var memory_context = memory_manager.build_memory_context()
    if memory_context != "":
        messages.append({
            "role": "system",
            "content": memory_context
        })

    # 3. User Message
    messages.append({
        "role": "user",
        "content": user_message
    })

    return messages

func _build_system_prompt() -> String:
    return profile.build_system_prompt()
```

---

### 3.5 Agent Controller（Agent 控制器）

整合所有模块的主控制器。

```gdscript
class_name AgentController
extends Node

@export var profile: PersonProfile
@export var memory_manager: MemoryManager
@export var llm_connector: LLMConnector
@export var prompt_builder: PromptBuilder

signal message_sent(content: String)
signal response_received(content: String)
signal error_occurred(message: String)

func _ready():
    prompt_builder.profile = profile
    prompt_builder.memory_manager = memory_manager

func process_message(user_input: String) -> void:
    # 1. 构建 Prompt
    var messages = prompt_builder.build_prompt(user_input)

    # 2. 添加用户消息到记忆
    _add_to_memory(user_input, false)

    # 3. 发送到 LLM
    llm_connector.send_message(messages, _on_response_received)

func _on_response_received(response: String) -> void:
    # 4. 添加回复到记忆
    _add_to_memory(response, true)

    # 5. 发送信号
    response_received.emit(response)

func _add_to_memory(content: String, is_ai: bool) -> void:
    var entry = MemoryEntry.new()
    entry.id = str(Time.get_unix_time_from_system())
    entry.type = MemoryType.WORKING
    entry.content = content
    entry.timestamp = Time.get_datetime_dict_from_system()
    entry.importance = 0.5
    entry.emotional_tag = "neutral"
    entry.user_sentiment = 0.0 if is_ai else 0.0

    memory_manager.add_memory(entry)

func end_session() -> void:
    memory_manager.consolidate_to_long_term()
```

---

## 四、UI 设计

### 4.1 场景结构

```
MainScene
├── UI (CanvasLayer)
│   ├── ChatPanel
│   │   ├── MessageList (ScrollContainer)
│   │   │   └── MessageBubble (重复)
│   │   └── InputPanel
│   │       ├── TextEdit
│   │       └── SendButton
│   ├── SidePanel (可折叠)
│   │   ├── ProfileCard
│   │   │   ├── Avatar
│   │   │   ├── NameLabel
│   │   │   └── StatusLabel
│   │   └── MemoryTimeline
│   │       └── MemoryItem (重复)
│   └── TopBar
│       ├── Title
│       └── SettingsButton
```

### 4.2 消息气泡

```gdscript
class_name MessageBubble
extends Control

enum MessageType { USER, AI }

@export var message_type: MessageType = MessageType.USER
@export var avatar_texture: Texture2D

func setup(content: String, type: MessageType) -> void:
    message_type = type
    $Label.text = content

    if type == MessageType.AI:
        add_theme_stylebox_override("panel", _get_ai_style())
        $Avatar.texture = avatar_texture
    else:
        add_theme_stylebox_override("panel", _get_user_style())
```

---

## 五、实施路线图

### Phase 1: MVP（最小可行产品）

- [ ] Profile 系统（静态 JSON 配置）
- [ ] Memory 系统（简单数组存储）
- [ ] LLM Connector（OpenAI API）
- [ ] 基础聊天 UI
- [ ] 基本的 Prompt 构建

**预计时间**: 1-2 周

### Phase 2: 记忆增强

- [ ] 分层记忆（工作/长期）
- [ ] 记忆检索（关键词 + 重要度）
- [ ] 情感标签系统
- [ ] 会话记忆持久化（JSON）

**预计时间**: 1-2 周

### Phase 3: 人格深化

- [ ] 多人格支持（可切换）
- [ ] 记忆编辑能力（Amadeus 核心特性）
- [ ] 可视化时间线
- [ ] 关系发展系统

**预计时间**: 2-3 周

### Phase 4: 高级功能（可选）

- [ ] 语音合成（TTS）
- [ ] 语音识别（STT）
- [ ] 离线支持（Ollama）
- [ ] 向量记忆检索

---

## 六、技术决策

### 需要提前决定的问题

| 问题 | 选项 | 推荐 |
|------|------|------|
| 目标平台 | 桌面端 / 移动端 / Web | 桌面端（Windows/Mac） |
| LLM 提供商 | OpenAI / Claude / Ollama | OpenAI（gpt-4） |
| 记忆存储 | SQLite / JSON / 内存 | JSON（简单） |
| 语音功能 | 有 / 无 | 后期添加 |
| 网络 | 在线 / 离线 | 前期在线，后期支持 Ollama |

### 关键技术栈

- **引擎**: Godot 4.6+
- **语言**: GDScript
- **网络**: Godot HTTPRequest
- **存储**: FileAccess (JSON)
- **LLM**: OpenAI API / Anthropic API / Ollama

---

## 七、可行性分析

### 优势

1. **Godot 适合 UI 开发** - 丰富的 2D/3D 界面组件
2. **简化版 OpenClaw** - 去掉复杂功能，聚焦核心
3. **现代 LLM 能力强** - GPT-4/Claude 已能很好地模拟人格
4. **本地化潜力** - 可完全离线运行（Ollama）

### 挑战

1. **Godot 非最佳选择** - 纯聊天软件 Web/移动端更合适
2. **记忆系统复杂度** - 要产生"认识你很久"的真实感
3. **实时性** - LLM API 延迟影响体验
4. **人格一致性** - 长对话保持人格一致是难点

### 风险与缓解

| 风险 | 缓解方案 |
|------|----------|
| API 延迟 | 流式输出 + 打字机效果 |
| 人格漂移 | 每次调用强制 system prompt |
| 记忆膨胀 | 定期总结 + 向量检索（后期） |
| 离线能力 | 支持 Ollama 本地模型 |

---

## 八、总结

本项目完全可行。核心难点不在技术，而在：

1. **Profile 设计** - 如何精心设计人格定义让 AI 扮演得逼真
2. **Memory 调优** - 如何让记忆系统产生"认识你很久"的真实感

建议从 Phase 1 开始，快速验证核心交互体验，再逐步迭代。

---

*文档版本: 1.0*
*创建日期: 2026-03-18*
