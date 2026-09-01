# Android 本地构建

RootLink Android 客户端是原生 Flutter 工程，不再通过 Flet 或 Python 运行时打包。

Windows 与 Android 的完整环境准备、构建命令、产物位置和常见问题统一记录在[Windows 与 Android APK 本地打包](build-windows-android.md)。本文只保留 Android 正式签名与覆盖升级的专项要求。

## 环境

- Flutter 3.41.4 / Dart 3.11
- Android SDK、platform-tools 和 Flutter 要求的 Android toolchain
- Windows 开发机需启用 Developer Mode，以允许插件创建符号链接

先检查环境：

```powershell
flutter doctor -v
flutter pub get
flutter analyze
flutter test
```

## 签名

正式 APK 必须继续使用旧版本的同一份 keystore，否则无法覆盖安装。不要重新生成发布证书。

在本机创建不纳入 Git 的 `android/key.properties`：

```properties
storeFile=C:/Users/<user>/.rootlink/signing/rootlink-release.jks
storePassword=<store password>
keyAlias=<key alias>
keyPassword=<key password>
```

`*.jks`、`android/key.properties` 和任何密码都不得提交到仓库或写入日志。

## 构建与验证

```powershell
flutter build apk --release
```

或者运行包含分析、测试和产物命名的脚本：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_release.ps1 -Targets apk
```

输出为 `dist/release/RootLink-v<version>-android.apk`。验证包名、版本与签名：

```powershell
aapt dump badging .\dist\release\RootLink-v<version>-android.apk
apksigner verify --verbose --print-certs .\dist\release\RootLink-v<version>-android.apk
```

必须确认包名为 `com.amadues.companion`、versionName 与 `pubspec.yaml` 一致、versionCode 等于 `+` 后的 build number，并且证书 SHA-256 与旧正式 APK 相同。

## 覆盖升级测试

1. 在旧版 RootLink 中创建角色、聊天、修改设置并导入一张立绘。
2. 不卸载旧版，执行 `adb install -r <new-apk>`。
3. 启动并逐项确认角色、会话、设置、记忆和图片无损。
4. 导出 `.amadues` 并重新导入，验证包兼容。

```powershell
adb devices -l
adb install -r .\dist\release\RootLink-v<version>-android.apk
adb shell monkey -p com.amadues.companion -c android.intent.category.LAUNCHER 1
```

如果覆盖失败，先比较新旧 APK 证书，不能用卸载应用作为发布验证的替代方案，因为卸载会清除本地数据。
