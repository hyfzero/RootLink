# RootLink 文档索引

RootLink 当前客户端使用 Flutter 3.41.4 / Dart 3.11，面向 Windows 与 Android。仓库中的 Python/Flet 文件仅作为迁移行为基线保留；它们不是新版本的运行时入口，并会在兼容、签名升级和双平台 Release 门槛全部通过后统一清理。

## 当前文档

- [用户指南](USER_GUIDE.md)：角色、聊天、沉浸模式、导入导出和设置
- [Flutter 架构](architecture.md)：分层、依赖、数据契约和响应式 UI
- [Windows 与 Android APK 本地打包](build-windows-android.md)：环境准备、调试构建、正式签名、产物位置与本地验证
- [Android 本地构建](android-local-build.md)：Android 签名与覆盖升级专项说明
- [发布流程](release-mobile-desktop.md)：GitHub Release、Windows ZIP、签名 APK、CI 与清理门槛

## 旧实现参考

`api/`、`brain/`、`session/` 和 `gui/` 下的文档描述 Python/Flet 版本，仅用于核对旧 JSON、Provider、人格、记忆、会话与界面行为。Flutter 对应实现位于仓库根目录的 `lib/` 与 `test/`，若两者表述冲突，以当前 Flutter 实现及兼容测试为准。

## 数据约定

- 角色数据继续位于 `data/{brain_id}/...`。
- 当前与历史会话继续位于 `data/{brain_id}/session/...`。
- 旧 JSON 的未知字段在 Dart 读写往返后保留。
- `.amadues` 继续采用 `amadues.character-package` v1 格式。
- 迁移只复制并校验数据，不自动删除旧用户目录。
