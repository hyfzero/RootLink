# ChatUI - Galgame 风格聊天界面规格说明

## 1. 项目概述

**项目名称：** ChatUI
**项目类型：** 基于 Flet 的跨平台聊天界面
**核心功能：** Galgame 风格的聊天界面，立绘（角色 sprite）占据屏幕 60%，对话框（Speech Bubble）叠加在立绘上方，支持打字机效果。
**目标用户：** 需要现代、响应式聊天界面的桌面和移动端用户。

---

## 2. 架构

### 层级分离

```
┌─────────────────────────────────────────┐
│              UI Layer (src/GUI/)         │
│  - Views (screens, components)           │
│  - Interface callbacks for Control      │
│  - Flet widget composition               │
└─────────────────────────────────────────┘
                    │
                    ▼ (interface callbacks)
┌─────────────────────────────────────────┐
│         Control Layer (src/Control/)    │
│  - User input handling                  │
│  - Business logic coordination           │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│          Core Layer (src/Core/)         │
│  - Chat message processing              │
│  - Character/avatar management           │
└─────────────────────────────────────────┘
```

### 目录结构

```
src/
├── GUI/
│   ├── __init__.py          # GUI 模块导出
│   ├── main_view.py         # 主应用入口，页面布局
│   ├── chat_view.py         # 聊天界面 UI (Galgame 布局)
│   ├── sidebar_view.py      # 侧边栏
│   ├── components/
│   │   ├── __init__.py
│   │   ├── character_sprite.py   # 立绘组件
│   │   ├── speech_bubble.py     # 对话框组件 (打字机效果)
│   │   ├── chat_input.py        # 消息输入组件
│   │   └── settings_panel.py    # 设置面板组件
│   └── interfaces/
│       ├── __init__.py
│       └── chat_interface.py     # 控制层抽象接口
└── Control/
    └── (placeholder - 用户实现)
```

---

## 3. UI/UX 规格

### 3.1 布局结构 (Galgame 风格)

**桌面端布局 (≥768px):**
```
┌──────────────────────────────────────────────────────┐
│ [≡]  Chat Title                    [Settings] [Theme]│
├──────────┬────────────────────────────────────────────┤
│          │                                            │
│ Sidebar  │     角色区域 (60%)                         │
│  (15%)   │  ┌──────────────────────────────────┐    │
│          │  │                                  │    │
│ - Avatar │  │       [Character Sprite]         │    │
│ - Name   │  │         立绘 (叠加层)              │    │
│ - Status │  │                                  │    │
│ ──────── │  │   ┌──────────────────────────┐   │    │
│ - History│  │   │   Speech Bubble          │   │    │
│ - Settings│ │   │   对话框 (叠加在立绘上)    │   │    │
│          │  │   └──────────────────────────┘   │    │
│ - Export │  └──────────────────────────────────┘    │
│ - Import │                                            │
│          ├────────────────────────────────────────────┤
│          │  [📎] [Input Field............] [Send]    │
└──────────┴────────────────────────────────────────────┘
```

**移动端布局 (<768px):**
```
┌────────────────────────┐
│ [☰]  Chat Title   [⚙] │
├────────────────────────┤
│                        │
│  角色区域 (Stack布局)    │
│  ┌──────────────────┐  │
│  │ [Character Sprite] │  │
│  │   立绘             │  │
│  │ ┌──────────────┐  │  │
│  │ │ Speech Bubble│  │  │
│  │ │ 对话框        │  │  │
│  │ └──────────────┘  │  │
│  └──────────────────┘  │
│                        │
├────────────────────────┤
│ [📎] [Input....] [➤] │
└────────────────────────┘
```

**布局比例说明：**
| 区域 | 占比 | 说明 |
|------|------|------|
| 角色区域 | 60% | 立绘 + 对话框 (Stack 叠加) |
| 输入框 | 固定 60px | 底部固定 |
| 侧边栏 | 15% | 桌面端显示，移动端 overlay |

**侧边栏：** 桌面端固定显示，移动端可滑动展开/收起。

---

### 3.2 组件功能说明

#### CharacterSprite (立绘组件)
- **功能：** 显示角色立绘/头像
- **位置：** 角色区域底层 (Stack 底部)
- **状态：**
  - Default: 静态显示
  - Speaking: 轻微缩放动画 (1.0 → 1.02), 200ms
- **特性：** 自适应父容器尺寸 (expand=True)

#### SpeechBubble (对话框组件)
- **功能：** 显示 AI 回复文本，打字机效果
- **位置：** 角色区域顶层 (Stack 顶部，叠加在立绘上)
- **样式：**
  - padding: 31x20 (增大40%)
  - border_radius: 26/8
  - 字体大小: 19px
- **效果：** 打字机动画，每字符 30ms (可配置)
- **特性：** 水平填充可用宽度 (float("inf"))

#### ChatInput (输入组件)
- **功能：** 消息输入框 + 发送按钮
- **位置：** 底部固定区域
- **组成：**
  - 附件按钮 (左侧)
  - 输入框 (中间，可扩展)
  - 发送按钮 (右侧，启用时主题色，禁用时灰色)

#### SidebarView (侧边栏组件)
- **功能：** 导航、设置、聊天历史
- **宽度：** 页面宽度 × 15% (最大 180px)
- **区域：**
  - 角色信息 (头像、名称、状态)
  - 聊天历史列表 (可滚动)
  - 设置面板 (主题切换、文本速度等)
  - Export/Import (固定底部)

#### SettingsPanel (设置面板组件)
- **功能：** 主题切换、文本速度调节
- **位置：** 侧边栏内，可滚动

---

### 3.3 视觉设计

**色彩方案：**
| 角色 | 深色模式   | 浅色模式   |
|------|-----------|-----------|
| Background | `#0F0F0F` | `#FAFAFA` |
| Surface | `#1C1C1C` | `#FFFFFF` |
| Primary | `#6366F1` | `#6366F1` |
| Text | `#FFFFFF` | `#18181B` |
| Text Secondary | `#A1A1AA` | `#71717A` |
| Border | `#3F3F46` | `#E4E4E7` |
| Sidebar BG | `#18181B` | `#FFFFFF` |
| Bubble AI | `#262637` | `#F4F4F5` |
| Bubble User | `#6366F1` | `#6366F1` |

**字体：**
- 系统默认字体 (Windows: Segoe UI, macOS: SF Pro, Android: Roboto)
- 对话框文本: 19px, FontWeight.W_400
- 输入框: 15px, FontWeight.W_400

**间距系统 (8pt 网格):**
- `xs`: 4px
- `sm`: 8px
- `md`: 16px
- `lg`: 24px
- `xl`: 32px

**视觉效果：**
- Border Radius: 24px (对话框), 16px (卡片)
- Transitions: 200ms ease-in-out
- 立绘淡入: 300ms

---

## 4. 功能规格

### 4.1 核心功能

1. **聊天显示**
   - 显示角色立绘 (自适应尺寸)
   - AI 回复显示在对话框 (打字机效果)
   - 用户输入仅发送，不显示气泡 (Galgame 风格)

2. **消息输入**
   - 文本输入框 + 发送按钮
   - Enter 键发送
   - 发送后清空输入框

3. **侧边栏**
   - 切换显示/隐藏
   - 设置面板
   - 查看聊天历史
   - Export/Import 固定底部

4. **响应式设计**
   - 桌面端/平板/移动端自适应布局
   - 侧边栏比例: 15%
   - 角色区域: 60%

### 4.2 用户交互

| 操作 | 桌面端 | 移动端 |
|------|--------|--------|
| 发送消息 | Enter / 点击发送 | 点击发送 |
| 切换侧边栏 | 点击菜单图标 | 左滑边缘 |
| 打开设置 | 点击齿轮图标 | 点击齿轮图标 |
| 切换主题 | 设置面板切换 | 设置面板切换 |

### 4.3 控制层接口 (UI → Control)

```python
class IChatViewCallback:
    """UI 层调用，控制层实现"""

    def on_message_send(self, text: str) -> None:
        """用户发送消息"""
        pass

    def on_settings_changed(self, settings: ChatSettings) -> None:
        """用户修改设置"""
        pass

    def on_theme_toggle(self) -> None:
        """用户切换主题"""
        pass

    def on_sidebar_toggle(self) -> None:
        """用户切换侧边栏"""
        pass

    def on_chat_history_select(self, chat_id: str) -> None:
        """用户选择聊天历史"""
        pass

    def on_sprite_tapped(self) -> None:
        """用户点击立绘"""
        pass
```

### 4.4 数据结构

```python
@dataclass
class ChatMessage:
    """聊天消息"""
    id: str
    text: str
    is_user: bool        # True=用户消息, False=AI消息
    timestamp: datetime
    character_id: Optional[str] = None

@dataclass
class Character:
    """角色信息"""
    id: str
    name: str
    sprite_path: str     # 立绘图片路径
    avatar_path: str     # 小头像路径

@dataclass
class ChatSettings:
    """聊天设置"""
    theme: str = "dark"           # "light" | "dark"
    text_speed: int = 30          # 打字机速度 (ms/字符)
    auto_scroll: bool = True
```

### 4.5 UI 层提供者接口 (Control → UI)

```python
class IChatViewProvider:
    """控制层调用，UI 层实现"""

    def append_message(self, message: ChatMessage) -> None:
        """添加消息到聊天视图"""
        pass

    def update_character(self, character: Character) -> None:
        """更新显示的角色立绘"""
        pass

    def set_typing_indicator(self, visible: bool) -> None:
        """显示/隐藏打字指示器"""
        pass

    def clear_chat(self) -> None:
        """清空聊天"""
        pass

    def set_sidebar_visible(self, visible: bool) -> None:
        """显示/隐藏侧边栏"""
        pass

    def apply_settings(self, settings: ChatSettings) -> None:
        """应用设置"""
        pass
```

---

## 5. 响应式断点

| 断点 | 宽度 | 布局 |
|------|------|------|
| Mobile S | < 375px | 单列，紧凑 |
| Mobile L | 375-767px | 单列，标准 |
| 平板 | 768-1023px | 侧边栏 overlay |
| 桌面端 | ≥ 1024px | 侧边栏固定显示 (15%) |

---

## 6. 验收标准

### 功能
- [x] 聊天区域显示立绘和对话框 (Galgame 叠加布局)
- [x] AI 消息打字机效果
- [x] 用户可通过输入框发送消息
- [x] 侧边栏在桌面端/移动端正确切换
- [x] 主题切换 (深色/浅色)
- [x] 布局自适应屏幕尺寸

### 视觉
- [x] 色彩符合规格
- [x] 字体大小一致
- [x] 间距遵循 8pt 网格
- [x] 动画流畅
- [x] Export/Import 固定底部

### 技术
- [x] 所有 UI 代码在 `src/GUI/`
- [x] 定义了控制层接口
- [x] UI 层无硬编码业务逻辑
- [x] Flet 控件正确清理
