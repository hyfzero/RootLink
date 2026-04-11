# GUI - Flet Galgame 聊天界面

`src/GUI` 是基于 Flet 的 Galgame 风格聊天界面。它展示角色立绘、叠加对话框、底部输入和响应式侧边栏。

## 职责边界

- 提供 UI 组件、布局和 Control 层回调接口。
- 展示 AI 消息、打字机效果、角色状态、设置和历史列表。
- 不直接调用 LLM，不直接写 Brain 或 Session 数据。

## 核心对象

公共入口：`from GUI import ...`

- 视图：`MainView`、`ChatView`、`SidebarView`
- 应用包装：`ChatUIApp`、`DummyCallback`
- 组件：`CharacterSprite`、`SpeechBubble`、`UserBubble`、`ChatInput`、`SettingsPanel`
- 接口和数据结构：`IChatViewCallback`、`IChatViewProvider`、`ChatMessage`、`Character`、`ChatSettings`

## 数据流/存储

GUI 本身不存储聊天数据。交互流：

```text
ChatInput
  -> IChatViewCallback.on_message_send(text)
  -> Control 层调用 SessionManager
  -> IChatViewProvider.append_message()
  -> ChatView / SpeechBubble / CharacterSprite 更新显示
```

## 典型用法

```python
import flet as ft
from GUI import ChatUIApp, DummyCallback

def main(page: ft.Page):
    app = ChatUIApp(callback=DummyCallback())
    app.run(page)

ft.app(target=main)
```

## 注意事项

- 用户输入在 Galgame 风格中主要用于发送，不强调显示用户气泡；`UserBubble` 仍作为组件存在。
- 桌面端使用侧边栏固定布局，移动端使用覆盖/抽屉式侧边栏。
- `ChatSettings.text_speed` 控制打字机速度，默认 30ms/字符。
