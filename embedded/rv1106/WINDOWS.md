# Windows 仿真与真实声卡、LLM API 配置

推荐构建入口见 [一份 CMake 配置切换 Ubuntu / WSL 与 RV1106](BUILDING.md)：修改 `config/build.cmake` 中的 `ROOTLINK_TARGET`，直接使用 CMake 编译。Ubuntu 产物位于 `build/ubuntu/rootlink-voice`。

使用共享 Python 人格核心和 LVGL 单主界面，请接着看 [Python 核心与界面启动指南](PYTHON_CORE.md)。旧配置默认 `PERSONA_BACKEND=simple`、`UI_BACKEND=none`；Python 示例为 `config/windows-python.conf.example`，启用窗口需设 `UI_BACKEND=sdl` 并重新构建。

## 先选运行方式

`TARGET=simulator` 表示在电脑上运行，不表示所有输入和服务都必须是假的。
是否访问声卡由 `AUDIO_API` 决定，是否访问云服务由 `SERVICE_MODE` 决定。

| 目标 | 当前可行方式 | 配置 |
| --- | --- | --- |
| Windows 完全离线测试 | 原生 MSVC 构建，或 WSL 构建 | `simulator / simulated / mock` |
| Windows 电脑真实麦克风、扬声器和云模型 | WSL2 + WSLg + ALSA PulseAudio 插件；须先通过下面的声卡验收 | `simulator / alsa / cloud`，设备 `pulse` |
| Windows 原生 `.exe` 直接访问声卡和云模型 | 当前未实现，不能靠配置开启 | 需增加 Windows 音频后端及对应构建、配置支持 |

当前代码只允许上述离线组合和 `simulator/alsa/cloud`、`rv1106/alsa/cloud`。
`simulated + cloud`、`alsa + mock`、分别选择 ASR/LLM/TTS 的 mock/cloud 都尚不支持。
`AUDIO_API=wasapi` 或 `windows` 也不是有效配置。

WSLg 提供麦克风及扬声器的 PulseAudio 服务，ALSA 官方插件可把应用的 ALSA 调用接到
这个服务。2026-09-06 已在本机完成录音样本 → 真实 ASR → Python 人格核心/真实 LLM →
真实 TTS → PulseAudio 播放验证。连续实时语音和主观音质仍需另行验收，详细结果见 [验证记录](VALIDATION.md)。
依据：[WSLg 音频架构](https://github.com/microsoft/wslg)、
[ALSA PulseAudio 插件说明](https://github.com/alsa-project/alsa-plugins/blob/master/doc/README-pulse)。

## A. Windows 原生离线仿真

准备 CMake ≥ 3.18 和支持 C++17 的 Visual Studio C++ 构建工具。
在可使用 MSVC 的 Developer PowerShell 中执行；本节所有路径都是 Windows 路径：

```powershell
Set-Location D:\linux_test\AmaduesBot\RootLink\embedded\rv1106
cmake -S . -B build/windows-simulated-mock -DROOTLINK_AUDIO_API=simulated -DROOTLINK_SERVICE_API=mock -DBUILD_TESTING=ON
cmake --build build/windows-simulated-mock --config Release --parallel
ctest --test-dir build/windows-simulated-mock -C Release --output-on-failure
.\build\windows-simulated-mock\Release\rootlink-voice.exe doctor --config config/rootlink.conf
.\build\windows-simulated-mock\Release\rootlink-voice.exe voice --config config/rootlink.conf --duration 15
```

这里假设使用 Visual Studio 多配置生成器；其他生成器的程序可能直接位于构建目录。
保持默认配置 `TARGET=simulator`、`AUDIO_API=simulated`、`SERVICE_MODE=mock`。
不会使用真实声卡，不会发出人声，不会调用 LLM；填入密钥也不会改变 mock 的行为。
Windows CTest 运行组件测试；基于 shell 的 CLI/SIGINT 验收仅在 Linux/WSL 注册。

## B. Windows 真实声卡 + 云服务（WSL 路线）

### 1. 检查 WSLg

Windows PowerShell 中执行：

```powershell
wsl --version
wsl -l -v
```

应有 WSLg 版本，使用的 Linux 发行版应为 WSL 2。没有 WSL 时，按
[Microsoft WSLg 安装说明](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gui-apps)
安装；旧环境可执行 `wsl --update`。更新后如需 `wsl --shutdown`，先保存其他 WSL 工作，
该命令会停止全部发行版。Windows 应满足官方 WSLg 条件（Windows 10 build 19044+ 或 Windows 11）。

在 Windows 声音设置中选择并测试目标输入/输出设备，允许桌面应用访问麦克风。
接下来所有 `sh`、`sudo`、`export` 命令均在 **WSL Ubuntu 终端** 执行，不是在 PowerShell。

```sh
sudo apt-get update
sudo apt-get install build-essential cmake libasound2-dev libasound2-plugins alsa-utils pulseaudio-utils libcurl4-openssl-dev libjson-c-dev ca-certificates
printf 'PULSE_SERVER=%s\n' "$PULSE_SERVER"
pactl info
pactl list short sources
pactl list short sinks
```

应能连接 WSLg 音频服务并列出输入/输出。WSLg 通常注入 `PULSE_SERVER`；不要随意改成
TCP 地址或另启动一个 PulseAudio 服务。如果变量为空，先检查 WSLg 会话；仅当
`test -S /mnt/wslg/PulseServer` 成功时，可在当前终端设置
`export PULSE_SERVER=unix:/mnt/wslg/PulseServer` 再检查。

### 2. 让 ALSA 使用 WSLg 音频

```sh
arecord -L
aplay -L
```

若已有 `pulse`，直接使用它。若提示 `Unknown PCM pulse`，在现有 `~/.asoundrc` 中
合并以下内容（文件不存在才新建；不要覆盖原有设备配置）：

```text
pcm.pulse {
    type pulse
}
ctl.pulse {
    type pulse
}
```

这里通过名字显式选择插件，无需把系统全局默认设备改掉。插件遵循 `PULSE_SERVER`，
默认使用服务端输入/输出；可参考
[ALSA 官方配置说明](https://github.com/alsa-project/alsa-plugins/blob/master/doc/README-pulse)。
`arecord -l` 没有硬件声卡不一定是故障；此路线使用 `pulse`，不是 `hw:0,0`。

先录 5 秒真人说话并回放：

```sh
cd /mnt/d/linux_test/AmaduesBot/RootLink/embedded/rv1106
mkdir -p build/windows-audio-check
arecord -D pulse -t wav -f S16_LE -r 16000 -c 1 -d 5 build/windows-audio-check/mic.wav
aplay -D pulse build/windows-audio-check/mic.wav
```

必须听到自己的声音。无声、录到扬声器回声、连接超时都应先解决：检查 Windows 麦克风
权限、静音及选中设备，确认 PulseAudio 输入不是输出的 monitor。
通过这一步后还需通过第 4 步本项目的录音回放；本项目额外要求准确的 20 ms 帧周期。

### 3. 配置真实 API

保留 `config/rootlink.conf` 的离线默认值，复制一份供本地联调使用：

```sh
mkdir -p build/windows-cloud
cp -i config/rootlink.conf build/windows-cloud/rootlink.conf
```

编辑复制的文件，替换相应字段（其他 VAD、超时等字段保留默认值）：

```ini
TARGET=simulator
AUDIO_API=alsa
SERVICE_MODE=cloud
CAPTURE_DEVICE=pulse
PLAYBACK_DEVICE=pulse
BUILD_DIR=
MODELS_FILE=config/models.json
SECRETS_FILE=config/rootlink-secrets.env
ROLE_DIR=config/role-example
SESSION_DIR=build/windows-cloud/sessions
LLM_PROVIDER=qwen
LLM_MODEL=qwen-plus
ASR_PROVIDER=dashscope
TTS_PROVIDER=dashscope
```

这些相对路径按运行时工作目录 `embedded/rv1106` 解释。WSL 访问 Windows 文件要用
`/mnt/d/...`，不能在该配置中使用 `D:\...`。已有同名环境变量会覆盖配置；切换模式前
检查自己是否曾 `export TARGET`、`AUDIO_API`、`SERVICE_MODE`、`LLM_BASE_URL` 等。

首次准备私有模型和密钥文件；`-i` 会在目标已有内容时询问，保留已配置的文件：

```sh
cp -i config/models.json.example config/models.json
cp -i config/rootlink-secrets.env.example config/rootlink-secrets.env
chmod 600 config/rootlink-secrets.env
```

在编辑器里把密钥填入 `config/rootlink-secrets.env` 的 `DASHSCOPE_API_KEY=` 后面，
不加引号。不要把真实值贴进聊天或命令历史。该变量默认供 DashScope ASR、Qwen LLM
和 DashScope TTS 使用；模型、音色及区域应与账号实际开通情况匹配，示例不是可用性保证。
Windows 挂载盘的权限语义可能导致 `chmod` 不生效；此时将私有密钥文件放到 WSL 用户目录，
设为 600，并把 `SECRETS_FILE` 改成它的 Linux 绝对路径。

只换 LLM 时，在上述联调配置中修改 `LLM_PROVIDER` 与 `LLM_MODEL`，并在
`config/models.json` 的同名 provider 下填对应兼容地址；模型名按账号可用 ID 填写。
例如选择 `deepseek` 时，密钥文件还需填写 `DEEPSEEK_API_KEY`。
清除或注释残留的 `LLM_BASE_URL` 覆盖项，否则仍可能请求旧供应商。

LLM 使用 OpenAI 兼容 chat/completions 协议；`base_url` 填基础地址，默认另拼接
`/chat/completions`。自定义路径在 models.json 的 provider 下设置 `chat_path`，
不要在默认路径配置下把完整 `/chat/completions` 地址重复填入 `base_url`。

**完整语音对话需要 ASR + LLM + TTS 三项服务。** 只有 LLM 密钥时，可先运行后面的
`chat --text` 验证文字问答；该命令不会打开声卡，也不调用 ASR/TTS，但仍要求按现有
规则配置并构建 `alsa/cloud`。此时 `doctor` 会因为缺 ASR/TTS 密钥报错，不能据此判定
单独的 LLM 请求失败。当前没有“真实 LLM + mock ASR/TTS”的混合开关。

### 4. 编译并按顺序验收

```sh
sh scripts/build.sh build/windows-cloud/rootlink.conf
```

输出为 `build/simulator-alsa-cloud/rootlink-voice`，这是运行在 WSL 的 Linux 程序。
与 Windows 原生 `.exe` 和 ARM 板端程序不是同一种产物。

先用项目自己的严格音频接口录音/回放；这两条不访问云服务：

```sh
build/simulator-alsa-cloud/rootlink-audio-smoke record --capture-device pulse --duration 5 --output build/windows-audio-check/rootlink-mic.wav
build/simulator-alsa-cloud/rootlink-audio-smoke play --playback-device pulse --input build/windows-audio-check/rootlink-mic.wav
build/simulator-alsa-cloud/rootlink-voice vad --config build/windows-cloud/rootlink.conf --duration 10 --output-dir build/windows-audio-check/segments
```

接着检查配置并测试云端。`doctor` 默认不联网；从 `chat` 开始会实际调用服务：

```sh
build/simulator-alsa-cloud/rootlink-voice doctor --config build/windows-cloud/rootlink.conf
build/simulator-alsa-cloud/rootlink-voice chat --config build/windows-cloud/rootlink.conf --text '你好，请简短介绍自己'
build/simulator-alsa-cloud/rootlink-voice transcribe --config build/windows-cloud/rootlink.conf --input build/windows-audio-check/rootlink-mic.wav
build/simulator-alsa-cloud/rootlink-voice synthesize --config build/windows-cloud/rootlink.conf --text '声音测试' --output build/windows-audio-check/reply.wav
build/simulator-alsa-cloud/rootlink-audio-smoke play --playback-device pulse --input build/windows-audio-check/reply.wav
build/simulator-alsa-cloud/rootlink-voice voice --config build/windows-cloud/rootlink.conf --duration 60
```

ASR 应返回所说文字，LLM 应返回真实模型回答，TTS 应能播放人声；全部通过再使用完整
`voice`。省略 `--duration` 持续运行，Ctrl+C 退出。播放期间停止采集，属于半双工。
真实 TTS 若返回 HTTP 下载地址，当前实现会拒绝，参见 [Stage 2 云协议限制](STAGE2.md#5-云协议与失败策略)。

## 常见问题与当前边界

### 终端环境与粘贴问题

- `用户名@电脑名:~$` 是 Ubuntu shell；`wsl --version` 和 `wsl -l -v` 要在
  Windows PowerShell 中执行。Ubuntu 提示的 `sudo apt install wsl` 不是这里需要的修复。
- 只复制代码框中的命令，不复制 Markdown 的三个反引号。若粘贴后提示符变成单独的
  `>`，按 Ctrl+C 取消未完成的输入，再逐条执行命令。
- `sudo` 使用 Linux 用户密码，输入时不显示字符。若后续已经出现各包的 `Setting up`
  和 `pactl info` 服务器信息，说明安装与音频服务连接已成功，不必因前面的密码错误重装。
- `PULSE_SERVER=unix:/mnt/wslg/PulseServer` 且能列出 `RDPSource`、`RDPSink`，
  表示桥接服务可连接；接下来仍需实际录音回放，不能仅凭设备列表认定声音已通过验收。

| 现象 | 检查方向 |
| --- | --- |
| 改成 cloud 仍提示二进制不匹配 | 重新构建并使用 `simulator-alsa-cloud` 下的程序 |
| 填了真实密钥仍返回固定文本 | 正在使用 mock 配置或 mock 二进制 |
| `Unknown PCM pulse` | 安装 ALSA PulseAudio 插件，并检查 `~/.asoundrc` |
| `Connection refused` / `pactl info` 失败 | WSLg 会话、PulseServer socket 和 `PULSE_SERVER` |
| 普通 arecord 可用，项目报 20 ms / 16000 Hz 错误 | 项目严格格式协商未通过，当前桥接环境尚不可用；需要音频适配修改，不能只改 API 密钥解决 |
| `401/403` | 对应供应商密钥、权限及服务区域 |
| 找不到角色或配置 | 当前工作目录和 WSL 路径；运行命令必须带正确的 `--config` |
| 切换模型后访问旧地址 | 环境变量和 `LLM_BASE_URL` 优先于 models.json |

如果目标明确是不使用 WSL 的 Windows 原生真实语音，需要后续实现 Windows 采集/播放
后端（例如 WASAPI）、接入后端选择与校验，并验证 Windows curl/json-c/TLS 构建和
真实声卡生命周期。这些是待开发内容，本次文档更新没有声称它们已实现。
