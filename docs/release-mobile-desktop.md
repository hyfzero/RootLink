# Android/iOS 发布打包

本项目使用 Flet 打包。Windows、Android 和 iOS 统一通过
`.github/workflows/release-mobile-desktop.yml` 构建，避免在 Windows 本机打 iOS。

## 固定配置

- 应用入口：`main.py`
- Flet module：`main`
- 产品名：`Amadues Companion`
- artifact：`AmaduesCompanion`
- bundle id：`com.amadues.companion`
- 版本号来源：workflow 中的 `BUILD_VERSION`

这些值需要和 `pyproject.toml` 的 `[tool.flet]` 配置保持一致。

## Android 签名

准备一个发布 keystore，并把内容写入 GitHub Actions secrets。

```powershell
.\scripts\prepare_android_signing.ps1 `
  -KeystorePath .\release.jks `
  -StorePassword "<store-password>" `
  -KeyPassword "<key-password>" `
  -Alias "amadues-release"
```

脚本会输出 `ANDROID_KEYSTORE_BASE64`，其余 secrets 按实际值填写：

- `ANDROID_KEYSTORE_BASE64`
- `ANDROID_KEYSTORE_PASSWORD`
- `ANDROID_KEY_PASSWORD`
- `ANDROID_KEY_ALIAS`

`release.jks` 是私钥文件，不能提交到仓库。

## iOS 签名

在 Apple Developer 后台为 `com.amadues.companion` 准备发布证书和 App Store
provisioning profile。

需要写入 GitHub Actions secrets：

- `APPLE_TEAM_ID`
- `IOS_CERTIFICATE_BASE64`
- `IOS_CERTIFICATE_PASSWORD`
- `IOS_PROVISIONING_PROFILE_BASE64`
- `IOS_PROVISIONING_PROFILE_NAME`

本地把 `.p12` 和 `.mobileprovision` 转成 base64：

```powershell
.\scripts\encode_file_base64.ps1 .\ios_distribution.p12
.\scripts\encode_file_base64.ps1 .\AmaduesCompanion.mobileprovision
```

`.p12` 和 `.mobileprovision` 都是敏感文件，不能提交到仓库。

## 触发构建

手动构建：

1. 打开 GitHub Actions。
2. 选择 `Release Windows Android iOS`。
3. 点击 `Run workflow`。
4. 下载 artifacts：
   - `AmaduesCompanion-windows`
   - `AmaduesCompanion-android`
   - `AmaduesCompanion-ios`

发布构建：

```powershell
git tag v0.1.0
git push origin v0.1.0
```

tag 名匹配 `v*` 时，workflow 会在三端构建成功后创建 GitHub Release。

## 验证

- Windows job 需要通过 smoke test。
- Android artifact 需要包含 `.apk` 和 `.aab`。
- iOS artifact 需要包含 `.ipa`。
- Android APK 下载到真机安装并启动，确认主界面、资源图片、聊天页和设置页可用。
- iOS IPA 用 TestFlight 或 Apple Transporter 上传验证签名。
