# RootLink

RootLink 是一款 Android 端 AI 角色陪伴应用，基于 `amadues` 的角色人格、结构化记忆、会话调度和多模型 API 能力构建。它支持创建角色、导入角色包、配置 MiniMax 或 DeepSeek 模型、长期聊天、情绪联动、日终总结和角色资料维护。

![RootLink 首页](docs/assets/user-guide/01-home.png)

## 核心能力

| 能力 | 说明 |
|------|------|
| 角色创建 | 通过五步向导配置基础信息、立绘、人格、记忆和语言风格 |
| 模型配置 | 支持 MiniMax 和 DeepSeek，API Key 在本机设置页维护 |
| 长期记忆 | 会话历史、日终总结和结构化记忆共同维持角色连续性 |
| 情绪表现 | 角色回复会带动情绪状态和立绘表现 |
| 角色包 | 支持 `.amadues` 角色包导入和导出 |
| 移动端体验 | 面向 Android 手机设计，包含常规聊天和沉浸陪伴模式 |

## 快速开始

1. 安装 `RootLink.apk`。
2. 打开应用，在首页右上角进入“设置”。
3. 选择模型来源，填写 API Key，点击“保存”。
4. 返回首页，点击“立即聊天”测试默认角色。
5. 需要自定义角色时，点击“创建角色”完成五步向导。

![RootLink 设置页](docs/assets/user-guide/04-settings.png)

## 使用文档

完整教程见 [docs/USER_GUIDE.md](docs/USER_GUIDE.md)，内容包括：

| 章节 | 内容 |
|------|------|
| 快速开始 | 安装、首页说明、第一次使用路径 |
| 设置 API | 模型来源、API Key、对话质量和常见问题 |
| 创建角色 | 五步创建向导和字段填写建议 |
| 立绘与抠图 | 图片规格、自动抠图、预设和微调 |
| 聊天交互 | 常规聊天、同步中、日终总结和沉浸模式 |
| 管理维护 | 编辑、导入、导出、备份和 PDF 导出建议 |

![RootLink 聊天页](docs/assets/user-guide/02-chat.png)

## 开发

本项目使用 Python 3.10 及以上。按照仓库约定，Python 环境使用 `.venv/`，不要使用系统主环境。

```powershell
.\.venv\Scripts\python.exe -m pytest
```

应用元信息位于 `pyproject.toml`：

| 项目 | 当前值 |
|------|--------|
| 产品名 | RootLink |
| 包名 | `com.amadues.companion` |
| 项目版本 | `0.1.7` |

## 文档地图

- [用户指引](docs/USER_GUIDE.md)
- [架构说明](docs/architecture.md)
- [API 层文档](docs/api/README.md)
- [Brain 模块文档](docs/brain/README.md)
- [Session 模块文档](docs/session/README.md)
- [GUI 文档](docs/gui/README.md)

## 导出 PDF

用户指引可以从仓库根目录导出为 PDF：

```powershell
pandoc docs/USER_GUIDE.md -o RootLink-user-guide.pdf
```

导出时请保留 `docs/assets/user-guide/` 目录，截图链接依赖该路径。
