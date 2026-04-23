# Persona - 人格与记忆

`persona.py` 定义角色静态资料、运行时人格状态和动态记忆。它是 Prompt 身份段、人格状态段、记忆段和 Session 记忆回写的核心数据来源。

## 职责边界

- 保存角色名称、年龄、性别、性格、背景、说话风格、生日和兴趣。
- 保存运行时人格状态：心境、精力、亲近感、张力、当前关注和上一轮情绪。
- 保存三类动态记忆：`episodic`、`preference`、`fact`。
- 提供最近记忆、关键词搜索、人格文本构建和人格状态更新。
- 不负责文件写入；持久化由 `PersonaStorage`、`AgentStorage` 或 Session 的 `MemoryUpdater` 处理。

## 核心对象

- `PersonaProfile`
  - 字段：`name`、`age`、`gender`、`personality_traits`、`background`、`speaking_style`、`birthday`、`interests`
  - 方法：`to_dict()`、`from_dict()`
- `PersonalityState`
  - 字段：`mood`、`energy`、`affinity`、`tension`、`current_focus`、`last_emotion`、`updated_at`
  - 方法：`to_dict()`、`from_dict()`、`build_prompt_text()`
- `MemoryEntry`
  - 字段：`id`、`content`、`timestamp`、`memory_type`、`importance`、`context`
  - 方法：`to_dict()`、`from_dict()`
- `Persona`
  - `add_memory()`
  - `get_recent_memories()`
  - `search_memories()`
  - `update_personality_state()`
  - `build_personality_state_text()`
  - `build_persona_text()`
  - `to_dict()`、`from_dict()`

## 数据流/存储

Session 模式下通常写入：

```text
data/{brain_id}/persona/profile.json
data/{brain_id}/persona/memories.json
data/{brain_id}/persona/state.json
```

约定：

- `profile.json` 是角色静态配置。
- `memories.json` 是动态记忆和摘要记忆。
- `state.json` 是运行时人格状态，由后端自动创建、加载和更新。
- Session 的 `MemoryUpdater` 只写动态记忆，不应修改 `profile.json`。
- `state.json` 与 `profile.json` 分离，避免 GUI 编辑静态人格时混入运行时状态。

## 典型用法

```python
from agent_core.brain import Persona, PersonaProfile

profile = PersonaProfile(
    name="红莉栖",
    age=18,
    gender="female",
    personality_traits=["聪明", "理性", "傲娇"],
    speaking_style="tsundere",
)

persona = Persona(profile)
persona.add_memory("用户喜欢夜间写代码", "preference", importance=1.5)
persona.add_memory("今天讨论了时间机器", "episodic")
persona.update_personality_state("谢谢你一直支持我", role="user", emotion="happy")

print(persona.build_persona_text())
print(persona.build_personality_state_text())
```

## 注意事项

- `memory_type` 只应使用 `episodic`、`preference`、`fact` 或 Session 已支持的摘要记忆类型。
- `importance` 推荐保持在 `0.0` 到 `2.0`。
- 搜索是简单包含匹配，不是向量检索。
- `PersonalityState` 更新规则是固定轻量规则，不通过 `AgentConfig` 暴露配置项。
