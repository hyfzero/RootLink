# Windows 与 Android 发布流程

正式发布由 `.github/workflows/release-mobile-desktop.yml` 完成。版本标签会触发 Flutter 格式检查、静态分析、全部测试、Windows Release、签名 Android APK 和 GitHub Release。阿里云 OSS 与 Gitee 镜像工作流继续消费 GitHub Release 产物。

## 固定配置

- Flutter：`3.41.4`
- 产品名与 artifact：`RootLink`
- Android 包名：`com.amadues.companion`
- 版本和 build number：`pubspec.yaml` 的 `version: <semver>+<number>`
- 发布 workflow：`Release Windows and Android`

Android build number 每次发布必须递增；正式 APK 必须使用旧版本同一份 keystore。

## GitHub 签名 Secrets

- `ANDROID_KEYSTORE_BASE64`
- `ANDROID_KEYSTORE_PASSWORD`
- `ANDROID_KEY_PASSWORD`
- `ANDROID_KEY_ALIAS`

密钥、密码和 Base64 内容不得提交到 Git、Release 或构建日志。

## 发布步骤

1. 修改 `pubspec.yaml`，例如 `version: 0.2.1+115`。
2. 运行 `dart format --output=none --set-exit-if-changed lib test`、`flutter analyze` 和 `flutter test`。
3. 使用 `scripts/build_release.ps1` 完成本地 Windows/Android Release 验证。
4. 在旧 APK 上执行真实覆盖升级测试，并用旧 Windows 数据快照验证迁移。
5. 提交后创建与版本一致的标签：

```powershell
git tag -a v0.2.1 -m "RootLink v0.2.1"
git push origin main
git push origin v0.2.1
```

标签必须等于 `v<pubspec semver>`。已公开的标签不得移动或复用。

## 产物验证

Release 应包含：

- `RootLink-v<version>-windows.zip`
- `RootLink-v<version>-android.apk`

Windows ZIP 解压后启动 `RootLink.exe`。Android 使用 `aapt dump badging` 与 `apksigner verify --print-certs` 检查包名、versionName、versionCode 和正式证书，再执行 `adb install -r` 覆盖测试。

## 国内镜像

GitHub 是主仓库。`Sync Aliyun OSS Release` 把 APK 设为 `application/vnd.android.package-archive`、Windows ZIP 设为 `application/zip`，并通过公开 URL 做响应头检查。`Sync Gitee Release` 由带 `rootlink-release-cn` 标签的国内 self-hosted runner 上传同版本附件；它不参与日常构建，也不镜像开发分支。

需要补同步已有版本时，在 Actions 中手动运行对应同步 workflow。国内 runner 暂时离线不会阻塞 GitHub 主发布。

## 旧实现清理门槛

以下条件必须全部满足后，才允许一次性删除 Python/Flet 源码、测试和旧构建配置：

- Flutter 数据兼容、Provider、Agent、角色包与 UI 测试全部通过。
- Windows Release 与正式签名 Android Release 均成功。
- Android 真实覆盖升级验证角色、聊天、设置、记忆和资源无损。
- Windows 旧目录快照迁移通过。
- 新旧 `.amadues` 双向导入验证通过。

任一门槛未完成时，旧实现继续作为行为基线保留。
