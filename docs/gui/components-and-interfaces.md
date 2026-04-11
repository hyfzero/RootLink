# Components And Interfaces - GUI 组件与回调

GUI 层由 Flet 组件和两个抽象接口组成。Control 层实现回调，GUI 层实现 Provider 方法。

## 职责边界

- 组件负责渲染和局部交互。
- `IChatViewCallback` 是 UI 调用 Control 的接口。
- `IChatViewProvider` 是 Control 更新 UI 的接口。
- 不在组件内写业务逻辑或调用 `SessionManager`。

## 核心对象

数据结构：

- `ChatMessage`
  - `id`
  - `text`
  - `is_user`
  - `timestamp`
  - `character_id`
- `Character`
  - `id`
  - `name`
  - `sprite_path`
  - `avatar_path`
- `ChatSettings`
  - `theme`
  - `text_speed`
  - `auto_scroll`

回调接口：

- `IChatViewCallback.on_message_send(text)`
- `IChatViewCallback.on_settings_changed(settings)`
- `IChatViewCallback.on_theme_toggle()`
- `IChatViewCallback.on_sidebar_toggle()`
- `IChatViewCallback.on_chat_history_select(chat_id)`
- `IChatViewCallback.on_sprite_tapped()`

Provider 接口：

- `IChatViewProvider.append_message(message)`
- `IChatViewProvider.update_character(character)`
- `IChatViewProvider.set_typing_indicator(visible)`
- `IChatViewProvider.clear_chat()`
- `IChatViewProvider.set_sidebar_visible(visible)`
- `IChatViewProvider.apply_settings(settings)`

主要组件：

- `CharacterSprite`：显示立绘，支持 speaking 状态轻微缩放。
- `SpeechBubble`：显示 AI 文本，支持打字机动画和跳过。
- `UserBubble`：用户消息气泡组件。
- `ChatInput`：输入框、附件按钮和发送按钮。
- `SettingsPanel`：主题、文本速度、自动滚动等设置。
- `SidebarView`：角色信息、历史、设置和导入导出按钮。
- `ChatView`：角色区域和底部输入。
- `MainView`：桌面/移动响应式组合布局。

## 数据流/存储

```text
用户点击发送
  -> ChatInput._handle_send()
  -> ChatView._handle_message_send()
  -> MainView._handle_message_send()
  -> IChatViewCallback.on_message_send()

Control 收到回复
  -> IChatViewProvider.append_message()
  -> MainView.append_message()
  -> ChatView.append_message()
  -> SpeechBubble.set_text()
```

## 典型用法

```python
from datetime import datetime
from GUI import ChatMessage, Character

main_view.update_character(Character(
    id="kurisu",
    name="红莉栖",
    sprite_path="assets/kurisu.png",
    avatar_path="assets/kurisu_avatar.png",
))

main_view.append_message(ChatMessage(
    id="msg_1",
    text="助手回复文本",
    is_user=False,
    timestamp=datetime.now(),
))
```

## 注意事项

- `MainView` 同时实现 `IChatViewProvider`。
- `DummyCallback` 只适合演示和占位。
- 图像路径由调用方提供；GUI 组件不负责寻找或生成角色资源。
