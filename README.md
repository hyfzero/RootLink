# RootLink

RootLink 是一款面向 Windows 与 Android 的本地优先 AI 角色陪伴应用。当前客户端使用 Flutter 3.41.4 / Dart 3.11 实现，支持角色创建、长期记忆、流式聊天、沉浸模式、立绘处理及 `.amadues` 角色包。

应用保留包名 `com.amadues.companion` 和旧版数据契约，可原位读取或迁移已有角色、会话、人格、记忆、设置与图片资源。API 密钥继续保存在本机，不提供账户或云同步。

## 主要能力

| 能力 | 说明 |
|---|---|
| 角色管理 | 五步创建/编辑流程，保留最后一个角色保护 |
| 模型接入 | MiniMax、DeepSeek、Qwen、GLM，以及旧配置中的 OpenAI、Anthropic、Kimi、Ollama、OpenRouter |
| 长期会话 | 每日会话、历史归档、日/月摘要、长期记忆与关系状态 |
| 对话体验 | SSE 流式输出、分句气泡、思考内容、取消、沉浸立绘模式 |
| 角色包 | `amadues.character-package` v1 导入导出、SHA-256 校验与失败回滚 |
| 响应式界面 | 390px 单栏；宽度达到 840px 后切换桌面双栏；深浅主题 |

## 开发

需要 Flutter `3.41.4`（Dart `3.11.x`）。

```powershell
flutter pub get
dart format --output=none --set-exit-if-changed lib test
flutter analyze
flutter test
```

本地发布脚本会先完成分析和全部测试，再构建指定平台：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_release.ps1 -Targets windows
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_release.ps1 -Targets apk
```

Android 正式构建需要 `android/key.properties` 指向原发布 keystore；Windows 构建需要 Visual Studio 的 Desktop development with C++。产物写入 `dist/release/`。

当前版本来自 `pubspec.yaml`：`0.2.0+114`。版本号和 Android build number 必须随发布递增。

## 数据兼容与旧实现

Flutter 客户端保持旧 JSON 文件名、字段、ID、时间格式和目录结构，未知字段在读写往返时保留。写入采用临时文件、校验、备份和替换流程；旧目录迁移会先复制到临时区并解析校验，失败时保留源数据并显示恢复提示。

旧 Python/Flet 实现与其 205 项测试当前仍作为迁移基线保留。只有数据兼容、UI、Windows/Android Release 和真实覆盖升级验证全部通过后，才允许一次性清理旧实现。

## 文档

- [架构说明](docs/architecture.md)
- [Windows 与 Android APK 本地打包](docs/build-windows-android.md)
- [Android 本地构建](docs/android-local-build.md)
- [Windows 与 Android 发布](docs/release-mobile-desktop.md)
- [用户指引](docs/USER_GUIDE.md)

项目基于 [MIT License](LICENSE) 开源。
