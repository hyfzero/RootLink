# Windows 和 Android 发布流程

RootLink 的正式发布由 `.github/workflows/release-mobile-desktop.yml` 完成。
推送版本标签后，GitHub Actions 会构建 Windows ZIP 和正式签名 Android APK，
把两个文件发布到同一个 GitHub Release。独立的 Gitee 同步流程随后通过国内
自托管 runner，同步安装包到 Gitee 公开镜像。
GitHub 始终是主仓库，日常开发不向 Gitee 推送。

## Gitee 发布镜像

首次启用前，在 [Gitee 私人令牌设置](https://gitee.com/profile/personal_access_tokens)
创建一个启用 `projects` 权限的令牌，然后在 GitHub 仓库的
[`Actions secrets`](https://github.com/hyfzero/RootLink/settings/secrets/actions/new)
中添加 Repository secret：

| 名称 | 内容 |
|------|------|
| `GITEE_RELEASE` | Gitee 私人令牌 |

不需要手动创建 Gitee 仓库。首次同步时，workflow 会在令牌所属账号下创建公开的
`RootLink` 仓库。此后的同步由 GitHub Release 的 `published` 事件触发。

Gitee 附件上传必须使用一台位于国内、带 `rootlink-release-cn` 标签的 GitHub
self-hosted runner。不要使用 GitHub 托管的美国 runner 直接上传大文件，否则跨境链路
可能持续数小时。runner 只负责读取已经发布的 GitHub 安装包并上传到 Gitee，不参与日常构建。

在仓库的 `Settings > Actions > Runners` 中添加 runner，按 GitHub 页面给出的命令安装，
配置时增加标签：

```text
rootlink-release-cn
```

Windows runner 需要安装 Git for Windows，确保 Actions 可以使用 `bash`、`curl`
和 `base64`；同时需要提供 `jq`。Linux runner 需要安装 Bash、curl、base64 和 jq。

Gitee 镜像包含同版本 Release、版本标签、Windows ZIP 和 Android APK。同步任务不会检出
项目源码，也不会日常同步 Git 分支；Gitee 标签以镜像仓库的 `main` 为目标创建。

本地仓库只保留 GitHub `origin`，不要把 Gitee 设置为默认 push 远端。这样普通提交和
分支仍只进入 GitHub，Gitee 仅保存已经正式发布的版本。

需要补同步已有版本时，在 GitHub Actions 中手动运行 `Sync Gitee Release`，
输入对应版本标签即可。该流程直接读取现有 GitHub Release，不会重新构建安装包。
如果国内 runner 暂时离线，GitHub Release 仍会正常完成，Gitee 同步任务会排队等待，
不会阻塞主发布流程。

如果现有 GitHub Release 产物从国内下载过慢，并且发布机本地 `dist/release` 已保留同版本
正式产物，可以手动运行 `Sync Gitee Release` 并把 `artifact_source` 设为 `local_dist`。
这条快速路径只读取国内 runner 本机文件，然后上传到 Gitee Release。

本地构建用于提前发现问题，不作为正式发布产物来源。

## 固定配置

- 应用入口：`main.py`
- 产品名和 artifact：`RootLink`
- Android 包名：`com.amadues.companion`
- 版本号：`pyproject.toml` 中的 `project.version`
- Android build number：`pyproject.toml` 中的 `tool.flet.build_number`
- 正式签名文件：`C:\Users\YY\.rootlink\signing\rootlink-release.jks`
- 正式发布 workflow：`Release Windows and Android`

`project.version` 使用语义化版本。每次 Android 发布时，
`tool.flet.build_number` 必须严格递增。

## 一次性签名配置

正式 keystore 已经创建并配置到 GitHub。日常发布不得重新生成证书，
否则新 APK 无法覆盖安装旧版本。

本地签名目录需要单独备份：

```text
C:\Users\YY\.rootlink\signing\
```

仓库的 GitHub Actions Secrets 必须包含：

- `ANDROID_KEYSTORE_BASE64`
- `ANDROID_KEYSTORE_PASSWORD`
- `ANDROID_KEY_PASSWORD`
- `ANDROID_KEY_ALIAS`

只检查 Secrets 名称，不读取值：

```powershell
gh secret list
```

`*.jks`、密码、Base64 私钥内容不得提交到 Git、Release 或日志。只有在首次创建
全新应用签名时才使用 `scripts/prepare_android_signing.ps1`。该脚本会安全提示输入密码，
不会显示密码或私钥 Base64。

## 1. 更新版本

修改 `pyproject.toml`：

```toml
[project]
version = "0.1.10"

[tool.flet]
build_number = 114
```

检查版本和工作区：

```powershell
git status --short --branch
git diff -- pyproject.toml
```

## 2. 本地验证

始终使用仓库中的 `.venv`：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

同时构建 Windows 和 Android 测试产物：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_release.ps1
```

也可以只构建其中一个：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_release.ps1 -Targets windows
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_release.ps1 -Targets apk
```

本地产物位于 `dist/release/`。本地 APK 不替代 GitHub Actions 生成的正式签名 APK。

连接手机后做冒烟测试：

```powershell
adb devices -l
adb install -r .\dist\release\RootLink-v0.1.10-android.apk
adb shell monkey -p com.amadues.companion -c android.intent.category.LAUNCHER 1
```

至少检查启动、API 设置、主界面和一次模型请求。

## 3. 提交并创建标签

先提交版本和本次发布内容，再推送 `main`：

```powershell
git add <本次修改的文件>
git commit -m "release: prepare v0.1.10"
git push origin main
```

标签必须与 `project.version` 完全一致，格式为 `v<version>`：

```powershell
git tag -a v0.1.10 -m "RootLink v0.1.10"
git push origin v0.1.10
```

不要在已公开的 Release 上移动或复用标签。发布后需要修复时，递增补丁版本并创建新标签。

## 4. 检查 GitHub Actions

标签推送后，workflow 会依次执行：

1. `Read release version`
2. `Windows`
3. `Android APK`
4. `GitHub Release`

查看运行状态：

```powershell
gh run list --workflow release-mobile-desktop.yml --limit 5
gh run watch <run-id>
```

四个 job 全部成功后，Release 应包含：

- `RootLink-v0.1.10-windows.zip`
- `RootLink-v0.1.10-android.apk`

Release 标题和说明统一使用英文，避免客户端或终端编码导致乱码。

## 5. 验证正式产物

下载 Release 产物：

```powershell
gh release download v0.1.10 --dir .\dist\verify\v0.1.10
```

验证 APK 包名、版本和签名：

```powershell
aapt dump badging .\dist\verify\v0.1.10\RootLink-v0.1.10-android.apk
apksigner verify --verbose --print-certs .\dist\verify\v0.1.10\RootLink-v0.1.10-android.apk
```

确认以下结果：

- 包名是 `com.amadues.companion`
- `versionName` 等于本次 `project.version`
- `versionCode` 等于本次 `tool.flet.build_number`
- APK 签名有效
- 证书不是 `CN=Android Debug`
- 证书 SHA-256 与正式证书记录一致

在已安装正式版本的手机上覆盖安装，用于验证后续升级能力：

```powershell
adb install -r .\dist\verify\v0.1.10\RootLink-v0.1.10-android.apk
adb shell monkey -p com.amadues.companion -c android.intent.category.LAUNCHER 1
```

解压 Windows ZIP，启动 `RootLink.exe`，确认程序可以进入主界面。

## 常见失败

### 缺少 Android signing Secrets

确认四个 Secrets 都存在，然后重新运行失败的 job。不要生成新 keystore。

```powershell
gh secret list
gh run rerun <run-id> --failed
```

### 标签与版本不一致

workflow 要求标签等于 `v<project.version>`。如果 Release 尚未公开，可以修正版本并重建标签；
如果已经公开，发布新的补丁版本，不移动旧标签。

### GitHub 连接超时

这是到 `github.com:443` 的网络问题，不是 Git 分支问题。确认代理或网络恢复后重试：

```powershell
git push origin main
git push origin v0.1.10
```

### APK 无法覆盖安装

先用 `apksigner` 比较新旧 APK 的证书 SHA-256。签名不同只能卸载旧应用，
会清除本地数据。正式版本必须始终使用同一份 keystore。

### 正式 keystore 丢失

从离线备份恢复。没有原 keystore 就无法为现有安装用户提供可覆盖升级的 APK。

## 发布完成清单

- `main` 已推送，工作区干净
- 标签与 `project.version` 一致
- Android build number 已递增
- GitHub Actions 四个 job 全部成功
- Release 说明为英文
- Windows ZIP 和 Android APK 均存在
- APK 包名、版本、正式证书验证通过
- 手机覆盖安装和启动通过
- Windows 解压启动通过
