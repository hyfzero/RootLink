# Windows 与 Android APK 本地打包

本文是 RootLink 本地构建与打包的统一入口。项目使用 Flutter 3.41.4 / Dart 3.11，Windows 和 Android 均从仓库根目录执行命令。

## 1. 当前构建配置

| 项目 | 值 |
|---|---|
| Flutter | 3.41.4 stable |
| Dart | 3.11.x |
| 应用版本 | 读取 `pubspec.yaml` 的 `version` |
| Windows 程序名 | `RootLink.exe` |
| Android 包名 | `com.amadues.companion` |
| Android 最低版本 | API 28 |
| Android 编译 SDK | API 36 |
| Java | JDK 17 |

打包前如需发布新版本，先修改 `pubspec.yaml`：

```yaml
version: 0.2.1+115
```

- `0.2.1` 是用户看到的版本号。
- `115` 是 Android `versionCode`，每次发布都必须递增。

## 2. 首次环境准备

### 通用环境

安装 Flutter 3.41.4，并确保新打开的 PowerShell 可以执行：

```powershell
flutter --version
flutter doctor -v
```

如果 Flutter 没有加入 PATH，可以在命令中使用完整路径，例如：

```powershell
& "C:\Users\<user>\flutter\3.41.4\bin\flutter.bat" --version
```

进入仓库根目录并安装依赖：

```powershell
cd D:\LLM_Proj\amadues
flutter pub get
```

### Windows 环境

安装 Visual Studio 2022 或 Visual Studio Build Tools 2022，并勾选：

- Desktop development with C++（使用 C++ 的桌面开发）
- MSVC C++ x64/x86 build tools
- Windows 10/11 SDK
- C++ CMake tools for Windows

然后检查：

```powershell
flutter config --enable-windows-desktop
flutter doctor -v
```

`flutter doctor` 中的 `Visual Studio - develop Windows apps` 应显示为通过。

### Android 环境

安装 Android Studio，并在 SDK Manager 中确认以下组件可用：

- Android SDK Platform 36
- Android SDK Build-Tools 36.0.0
- Android SDK Platform-Tools
- Android SDK Command-line Tools
- NDK 28.2.13676358
- CMake 3.22.1

本机默认 SDK 路径通常为：

```text
C:\Users\<user>\AppData\Local\Android\Sdk
```

配置 Flutter 并接受许可证：

```powershell
flutter config --android-sdk "C:\Users\<user>\AppData\Local\Android\Sdk"
flutter doctor --android-licenses
flutter doctor -v
```

`flutter doctor` 中的 `Android toolchain` 应显示为通过，并确认 Java 为 JDK 17、Android 许可证全部接受。Windows 还应开启“开发者模式”，以便 Flutter 插件创建符号链接。

## 3. 打包前检查

推荐在每次正式打包前依次执行：

```powershell
flutter pub get
dart format --output=none --set-exit-if-changed lib test
flutter analyze
flutter test
```

任何一步失败都应先修复，不要发布未通过检查的产物。

## 4. Windows 打包

### 直接构建

```powershell
flutter build windows --release
```

构建目录：

```text
build\windows\x64\runner\Release\
```

可以直接启动：

```powershell
.\build\windows\x64\runner\Release\RootLink.exe
```

发布时不能只复制 `RootLink.exe`。必须把 `Release` 目录中的 DLL、`data` 等文件一起分发。推荐使用项目脚本生成完整 ZIP：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build_release.ps1 `
  -Targets windows
```

脚本会先执行依赖安装、静态分析和全部测试，然后生成：

```text
dist\release\RootLink-v<version>-windows.zip
```

发布前应把 ZIP 解压到一个全新目录，再启动 `RootLink.exe` 做一次冒烟测试。

## 5. Android APK 打包

### 调试 APK

调试包不需要发布证书，适合本机安装和功能测试：

```powershell
flutter build apk --debug
```

输出位置：

```text
build\app\outputs\flutter-apk\app-debug.apk
```

连接已开启 USB 调试的 Android 设备后，可以执行：

```powershell
adb devices -l
adb install -r .\build\app\outputs\flutter-apk\app-debug.apk
```

### 正式 APK 签名

正式 APK 必须配置 `android/key.properties`。如果需要覆盖安装旧版 RootLink，必须使用旧版完全相同的 keystore、alias 和密码；重新生成证书会导致覆盖安装失败。

将 keystore 放在仓库外的安全目录，然后创建不会提交到 Git 的 `android/key.properties`：

```properties
storeFile=C:/Users/<user>/.rootlink/signing/rootlink-release.jks
storePassword=<store password>
keyAlias=<key alias>
keyPassword=<key password>
```

Windows 路径推荐使用 `/`，避免 `.properties` 文件把反斜杠当成转义字符。不要把 keystore、密码、`key.properties` 或私钥 Base64 提交到仓库或输出到日志。

`scripts/prepare_android_signing.ps1` 只能用于建立一条全新的签名链。已经发布过 RootLink 时不要运行它来替换旧证书。

配置完成后可以直接构建：

```powershell
flutter build apk --release
```

直接构建的输出位置：

```text
build\app\outputs\flutter-apk\app-release.apk
```

推荐使用统一脚本完成检查、构建和命名：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build_release.ps1 `
  -Targets apk
```

脚本输出：

```text
dist\release\RootLink-v<version>-android.apk
```

### 同时构建 Windows 和 APK

已经配置 Android 正式签名后，可一次构建两个平台：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& .\scripts\build_release.ps1 -Targets @("windows", "apk")
```

Flutter 不在 PATH 时，给脚本传入完整路径：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& .\scripts\build_release.ps1 `
  -Targets @("windows", "apk") `
  -FlutterPath "C:\Users\<user>\flutter\3.41.4\bin\flutter.bat"
```

## 6. 正式产物验证

### Windows

1. 确认 ZIP 内包含 `RootLink.exe`、DLL 和 `data` 目录。
2. 解压到空目录并启动应用。
3. 验证首页、聊天、角色图片、导入导出和设置读写。
4. 使用旧版数据目录快照验证角色、会话和设置迁移。

### Android

使用 Android SDK Build Tools 检查包名、版本和证书：

```powershell
$buildTools = Join-Path $env:ANDROID_HOME "build-tools\36.0.0"
& (Join-Path $buildTools "aapt.exe") dump badging `
  .\dist\release\RootLink-v<version>-android.apk
& (Join-Path $buildTools "apksigner.bat") verify --verbose --print-certs `
  .\dist\release\RootLink-v<version>-android.apk
```

必须确认：

- 包名是 `com.amadues.companion`。
- `versionName` 与 `pubspec.yaml` 中 `+` 前的版本一致。
- `versionCode` 与 `+` 后的数字一致。
- 证书 SHA-256 与旧正式 APK 完全相同。

覆盖升级测试时不要先卸载旧版，因为卸载会清除应用沙箱数据：

```powershell
adb install -r .\dist\release\RootLink-v<version>-android.apk
adb shell monkey -p com.amadues.companion `
  -c android.intent.category.LAUNCHER 1
```

升级后逐项检查角色、聊天记录、记忆、设置、立绘和 `.amadues` 导入导出。

## 7. 常见问题

### `flutter` 或 `adb` 找不到

关闭并重新打开终端或 Codex，使新的用户 PATH 生效。仍然失败时检查 PATH 是否包含 Flutter 的 `bin` 和 Android SDK 的 `platform-tools`。

### Windows 构建提示缺少 Visual Studio 工具

打开 Visual Studio Installer，补装 Desktop development with C++、MSVC、Windows SDK 和 CMake，然后重新运行 `flutter doctor -v`。

### Release APK 提示缺少 `android/key.properties`

这是防止误发未签名或签名不一致 APK 的保护。恢复原发布 keystore 并按本文创建 `android/key.properties` 后再构建。

### Gradle、Kotlin 或插件缓存异常

先关闭正在运行的应用，再执行：

```powershell
flutter clean
flutter pub get
flutter build apk --debug
```

首次 Android 构建会下载 Gradle、Maven 依赖和缺少的 SDK 组件，耗时较长属于正常现象。

## 8. 线上发布

本地 ZIP 和 APK 验证通过后，再按[Windows 与 Android 发布流程](release-mobile-desktop.md)创建版本标签并触发 GitHub Release。CI 使用相同 Flutter 版本，并从 GitHub Secrets 恢复 Android 正式签名材料。
