# RootLink 语音终端用户手册

文档更新：2026-09-07。适用版本：2026-09-06 已完成构建验证的 Python 人格核心 + C++ 语音终端 + LVGL 单主界面。本文说明现有代码的配置、编译和运行。默认体验方式是 Windows WSL2/WSLg 或 x86 Ubuntu，使用真实麦克风、扬声器和云 API；也支持交叉编译 RV1106 程序。

程序的工作过程：听取一句话 → 语音识别 → 人格核心生成回答 → 语音合成 → 播放 → 继续听取下一句话。当前处理和播放时会停止采集，不支持边播放边插话。

2026-09-08 新增可选的日语播报：人格回答 → 独立 LLM 翻译 → CosyVoice v3.5-plus → 播放。配置及音色创建见[日语语音配置](JAPANESE_VOICE.md)。原始回答仍用于显示、历史和记忆；译文只用于播报。新模板需要填写自己的复刻音色 ID，旧配置不会自动切换。

启用界面时，上半部分显示状态，下半部分逐字显示人格返回的原文中文回复；长回复会自动滚动。`UI_TEXT_INTERVAL_MS` 控制每个 Unicode 字符的显示间隔，默认 50 ms、范围 10–1000 ms。点击重置会清空当前显示并取消本轮；日语翻译只影响 TTS，不改变下半部分的原文。显示节奏不保证与语音逐词同步。

新增可选的[牧濑红莉栖 · Amadeus 人格包](../../characters/kurisu_amadeus/README.md)，附官方来源考据及 App 可导入的 `.amadues` 文件。已有 Ubuntu 构建可运行 `./build/ubuntu/rootlink-voice voice --config config/windows-kurisu.conf.example`，使用独立人格数据目录和 `longxiaochun_v3` 知性女声。它是非官方风格适配，不是原声复刻；App 当前支持角色导入和文字交流，尚未接通 TTS。

## 1. 先找到这几份文件

本文命令除特别标注外，均在 **Ubuntu / WSL 终端** 的 `RootLink/embedded/rv1106` 目录执行。Windows 工作区 `D:\linux_test\AmaduesBot` 在 WSL 中对应 `/mnt/d/linux_test/AmaduesBot`。

| 文件 | 配置什么 | 通常何时修改 |
| --- | --- | --- |
| [config/build.cmake](config/build.cmake) | 编译目标、LVGL 源码路径、SDK 路径、CA 文件 | 首次编译或切换平台 |
| `build/windows-cloud/python-ui.conf` | 声卡、人格后端、模型名、窗口、数据路径 | 日常使用；本机启动脚本默认读取它 |
| [config/windows-python.conf.example](config/windows-python.conf.example) | Windows / WSL 运行配置模板 | 新机器复制一份再编辑 |
| `config/rootlink-secrets.env` | API 密钥 | 首次填写或更换密钥 |
| `config/models.json` | 对话 LLM 供应商地址和请求设置 | 更换 LLM 供应商或端点 |
| [config/role-example](config/role-example) | 初始角色数据 | 创建新角色或新测试副本 |

**编译目标和运行目标的名字不同**：构建配置用 `ROOTLINK_TARGET=ubuntu`，对应运行配置的 `TARGET=simulator`。`simulator` 表示在电脑上运行，仍然可以使用真实声卡和真实 API。

构建时选择的音频、云服务和显示后端必须与运行配置匹配。只改运行配置不能给旧二进制增加未编译进去的功能。修改密钥、模型名和角色路径通常不需要重新编译，重启程序即可。

## 2. API 要申请哪些，密钥填在哪里

默认使用以下三个服务，它们共用一项 `DASHSCOPE_API_KEY`：

| 环节 | 作用 | 当前配置模型 | 配置项 |
| --- | --- | --- | --- |
| ASR | 把录音转为文字 | `qwen3-asr-flash` | `ASR_PROVIDER=dashscope` |
| LLM | 按人格和记忆生成回答 | `qwen-plus` | `LLM_PROVIDER=qwen` |
| TTS | 把回答文字转为语音 | `cosyvoice-v3-flash` | `TTS_PROVIDER=dashscope` |

在所选服务的控制台创建可访问对应模型和地域的密钥，并确认账户已开通相应服务。本表记录本项目当前配置，不代表任意账户都已有调用权限。

**推荐直接填写文件，不需要每次在终端输入密钥。** 用编辑器打开 `config/rootlink-secrets.env`：

```dotenv
DASHSCOPE_API_KEY=这里替换为你的真实密钥
DEEPSEEK_API_KEY=
GLM_API_KEY=
MOONSHOT_API_KEY=
MINIMAX_API_KEY=
```

默认组合只填写第一项，其他项留空。运行配置指定：

```ini
SECRETS_FILE=config/rootlink-secrets.env
```

也可以把密钥放到其他文件，并修改 `SECRETS_FILE` 指向它。读取优先级为：**非空进程环境变量 → 密钥文件 → LLM 的 models.json.api_key**。ASR/TTS 的密钥不从 models.json 读取。若改了文件却仍使用旧密钥，检查 WSL 终端是否还设置了同名环境变量。推荐密钥只保存在密钥文件，models.json 的 `api_key` 留空，不将密钥文件提交到仓库。

`.conf` 和 `.env` 均使用 UTF-8 无 BOM 的 `KEY=VALUE` 文本：不要写引号、等号两侧空格或行尾注释；说明文字单独放一行且以 `#` 开头。URL 必须是纯文本，不要粘贴成 Markdown 链接。

### 更换对话 LLM

ASR/TTS 当前云实现固定为 DashScope；更换 LLM 后，仍需保留 `DASHSCOPE_API_KEY` 用于识别和合成，并额外填写所选 LLM 的密钥：

| `LLM_PROVIDER` | 密钥项 | models.json 中的节点 |
| --- | --- | --- |
| `qwen` | `DASHSCOPE_API_KEY` | `providers.qwen` |
| `deepseek` | `DEEPSEEK_API_KEY` | `providers.deepseek` |
| `glm` | `GLM_API_KEY` | `providers.glm` |
| `moonshot` | `MOONSHOT_API_KEY` | `providers.moonshot` |
| `minimax` | `MINIMAX_API_KEY` | `providers.minimax` |

修改运行配置的 `LLM_PROVIDER`、`LLM_MODEL`，并核对 models.json 对应节点的 `base_url`。模型名填写该账户实际可用的名称。默认地址模板见 [models.json.example](config/models.json.example)。如果曾设置 `LLM_BASE_URL`，它会覆盖 models.json，换供应商时也要同步修改或删除。当前嵌入式入口要求 OpenAI 兼容接口，不能直接填写 Anthropic Messages 端点。

### TTS 实际调用哪个 API

下面是旧版直读配置。使用 `cosyvoice-v3.5-plus` 和日语翻译时，请使用[新配置示例](config/windows-kurisu-japanese.conf.example)和[配置步骤](JAPANESE_VOICE.md)，不能把下方系统音色直接用于 v3.5。

当前配置：

```ini
TTS_PROVIDER=dashscope
TTS_MODEL=cosyvoice-v3-flash
TTS_VOICE=longanyang
TTS_SAMPLE_RATE=16000
TTS_BASE_URL=https://dashscope.aliyuncs.com/api/v1
```

代码向 `https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer` 发送 POST，请求内容含 `model` 和 `input.text / voice / format / sample_rate`；格式为 WAV，采样率为 16000。收到音频地址后，再通过 HTTPS 下载并播放。它不是 OpenAI `/audio/speech` 接口，也不是 WebSocket 接口。

音色必须与所选 TTS 模型兼容。当前音频链路固定为 16 kHz、单声道、PCM16，不要把 `TTS_SAMPLE_RATE` 改成其他数值。更换服务协议需要开发适配，不能只替换 URL。

## 3. Windows / WSL 从零准备

Windows PowerShell 中执行：

```powershell
wsl --version
wsl -l -v
```

需要 WSL2 和可用的 WSLg 图形、音频会话。若在 Ubuntu 提示 `wsl: command not found`，说明命令输错了终端；回到 Windows PowerShell 执行。WSLg 音频排查见 [WINDOWS.md](WINDOWS.md)。

进入 WSL Ubuntu，安装依赖：

```sh
sudo apt-get update
sudo apt-get install build-essential cmake libsdl2-dev libasound2-dev libasound2-plugins alsa-utils pulseaudio-utils libcurl4-openssl-dev libjson-c-dev ca-certificates python3-venv
cd /mnt/d/linux_test/AmaduesBot/RootLink
python3 -m venv .venv
.venv/bin/python -m pip install -r embedded/rv1106/requirements-core.txt
cd embedded/rv1106
```

已有可用 `.venv` 时复用它。无界面人格核心只安装这份轻量依赖，不需要 Flet、Pillow 或桌面打包依赖。

首次创建本地配置，以下命令会保留已经存在的文件：

```sh
mkdir -p build/windows-cloud
test -f build/windows-cloud/python-ui.conf || cp config/windows-python.conf.example build/windows-cloud/python-ui.conf
test -f config/models.json || cp config/models.json.example config/models.json
test -f config/rootlink-secrets.env || cp config/rootlink-secrets.env.example config/rootlink-secrets.env
chmod 600 config/rootlink-secrets.env
```

在 Windows 编辑器中打开这些文件也可以；但配置中的路径必须按 WSL 写法填写。编辑 `python-ui.conf`，以这份完整示例为准，并在密钥文件中填写真实密钥：

```ini
TARGET=simulator
AUDIO_API=alsa
SERVICE_MODE=cloud
CAPTURE_DEVICE=pulse
PLAYBACK_DEVICE=pulse
UI_BACKEND=sdl
UI_WIDTH=320
UI_HEIGHT=240
PERSONA_BACKEND=python
PYTHON_EXECUTABLE=../../.venv/bin/python
PYTHON_CORE_ENTRY=scripts/persona-worker.py
PYTHON_DATA_DIR=build/windows-cloud/kurisu-canon-python-data
PERSONA_START_TIMEOUT_MS=30000
PERSONA_TURN_TIMEOUT_MS=300000
ROLE_DIR=../../characters/kurisu_amadeus
SESSION_DIR=build/windows-cloud/sessions
MODELS_FILE=config/models.json
SECRETS_FILE=config/rootlink-secrets.env
ASR_PROVIDER=dashscope
ASR_MODEL=qwen3-asr-flash
ASR_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-v4-flash
LLM_BASE_URL=https://api.deepseek.com
TTS_PROVIDER=dashscope
TTS_MODEL=cosyvoice-v3-flash
TTS_VOICE=longxiaochun_v3
TTS_SAMPLE_RATE=16000
TTS_BASE_URL=https://dashscope.aliyuncs.com/api/v1
```

相对路径按**运行命令所在目录**解释，不是按 `.conf` 所在目录解释。`BUILD_DIR` 等旧构建脚本选项无需放进这份运行配置；新入口的输出目录由 CMake 的 `-B` 指定。

检查声卡桥接：

```sh
pactl info
arecord -L
aplay -L
```

应能连接 WSLg 音频服务，并找到 `pulse` 设备。原生 Ubuntu 可以改用实际 ALSA 设备，例如 `default`，录音和播放设备允许分别设置。不要在 Windows PowerShell 中设置 Linux 的 `PULSE_SERVER`；相关处理应在 WSL 中进行。

## 4. 用 CMake 编译并运行

编辑 [config/build.cmake](config/build.cmake)，保留：

```cmake
set(ROOTLINK_TARGET "ubuntu" CACHE STRING "ubuntu or rv1106" FORCE)
```

确认 `ROOTLINK_LVGL_SOURCE_DIR` 指向工作区的 `Amadues_chatRobo/Demo/DeskBot_demo/lvgl`。执行：

```sh
cmake -S . -B build/ubuntu -C config/build.cmake
cmake --build build/ubuntu --parallel 4
ctest --test-dir build/ubuntu --output-on-failure
build/ubuntu/rootlink-voice doctor --config build/windows-cloud/python-ui.conf
```

`doctor` 不带 `--probe-cloud` 时只做本地检查，不调用云模型；`doctor=ok` 不等于密钥和真实网络已经验证。产物 `build/ubuntu/rootlink-voice` 是 x86 Linux 文件，在 WSL 中运行，不是 Windows `.exe`。

编译完成并配置好 API、声卡及 Python 环境后，可以在 WSL Ubuntu 终端直接运行编译产物，开始真实语音对话：

```sh
cd /mnt/d/linux_test/AmaduesBot/RootLink/embedded/rv1106

./build/ubuntu/rootlink-voice voice \
  --config build/windows-cloud/python-ui.conf
```

这里读取已有的 `build/windows-cloud/python-ui.conf`；首次使用请先按第 3 节创建并编辑该文件。直接运行不需要启动脚本，窗口是否启用由配置中的 `UI_BACKEND=sdl` 决定；配置内的相对路径按上面的工作目录使用。

当前 WSL 配置与新建配置模板默认使用 `characters/kurisu_amadeus` 人格及其预置记忆，配套女声为 `longxiaochun_v3`。首次启动会在 `build/windows-cloud/kurisu-canon-python-data` 初始化数据；后续启动恢复这里的会话。旧人格数据目录保留，不自动合并。更换人格无需重新编译。

当前默认对话 LLM 为 DeepSeek Flash（`deepseek-v4-flash`），使用 `config/rootlink-secrets.env` 中的 `DEEPSEEK_API_KEY`；ASR 和 TTS 仍使用 `DASHSCOPE_API_KEY`，两个密钥均需配置。按照 [DeepSeek 官方说明](https://api-docs.deepseek.com/guides/thinking_mode/)，该模型默认启用思考模式；本配置沿用服务端默认模式。修改模型后重启程序即可，无须重新编译，也不需要清除人格历史。单独的 `windows-kurisu.conf.example` 仍是 Qwen 组合示例。

也可以使用便捷启动脚本：

```sh
sh scripts/run-wsl-ui.sh
```

也可以在 Windows 双击 [start-wsl-ui.cmd](start-wsl-ui.cmd)。这两个入口使用 `python-ui.conf`，优先运行 `build/ubuntu/rootlink-voice`；旧 SDL 产物只作为未构建新版本时的兼容路径。使用自定义运行配置可执行 `sh scripts/run-wsl-ui.sh 你的配置路径`。

| 窗口符号 | 含义 |
| --- | --- |
| `？` | 正在采集，等待你说话 |
| `....` | 正在识别、生成回答或合成语音 |
| `！` | 正在播放回答 |
| `—` | 初始化、空闲或正常停止 |
| `×` | 发生故障；点击屏幕重置，或关闭窗口 |

**点击窗口或轻触屏幕任意位置后松开，可以重置语音运行状态。** 正常收音、思考、播放中及故障时均可使用。程序先取消当前操作并释放声卡、Python 子进程，再重新加载运行配置、恢复已保存的人格数据并收音。取消期间窗口继续响应，重复点击合并处理；不会删除记忆，也不会自动重发失败的消息。已生成并保存、但尚未播放的回答仍可能留在历史中。

ASR 或 TTS 超时、临时网络错误会跳过当前轮，自动恢复 `？`；日志标注失败阶段和 `action=skip_turn_resume_listening`。Python 人格处理失败、密钥或设备错误会停在 `×`，点击重置后再试。持续配置错误需要先修改配置文件，再点击重置。关闭窗口或 Ctrl+C 始终用于退出。

WSL 的 SDL 窗口直接支持鼠标左键点击。嵌入式 framebuffer 还需在运行配置中指定触摸输入节点，例如参考 DeskBot 的配置：

```ini
UI_BACKEND=fbdev
UI_DEVICE=/dev/fb0
UI_INPUT_DEVICE=/dev/input/event0
```

实际节点以板上的 `/proc/bus/input/devices` 为准，需要可读权限及 `BTN_TOUCH` 按下/松开事件。只配置 `/dev/fb0` 只能显示，不能接收点击；`UI_INPUT_DEVICE` 留空则不启用板端触摸重置。配置了不存在或无权限的节点会直接报告初始化错误。实板触摸与驱动异常恢复仍需在设备上验证。

关闭窗口或 Ctrl+C 退出。真实 `voice`、`chat`、`transcribe`、`synthesize` 会调用对应云服务；对话还会更新人格数据。

需要分步定位问题时，执行：

```sh
build/ubuntu/rootlink-voice chat --config build/windows-cloud/python-ui.conf --text '你好'
build/ubuntu/rootlink-voice synthesize --config build/windows-cloud/python-ui.conf --text '语音测试' --output build/windows-cloud/tts-check.wav
aplay -D pulse build/windows-cloud/tts-check.wav
```

`chat` 检查人格和 LLM，`synthesize` 检查 TTS；它们不开状态窗口。模型调用通过后，再运行完整语音链路。

## 5. RV1106 编译与部署

仍在 Ubuntu / WSL 编译。把同一份 `config/build.cmake` 的目标改为 `rv1106`，检查 SDK、LVGL 和可信 CA 路径：

```cmake
set(ROOTLINK_TARGET "rv1106" CACHE STRING "ubuntu or rv1106" FORCE)
```

```sh
cmake -S . -B build/rv1106 -C config/build.cmake
cmake --build build/rv1106 --parallel 4
file build/rv1106/rootlink-voice
```

SDK 必须先生成与固件匹配的 Buildroot rootfs 和工具链 wrapper。产物应为 ARM32 / uClibc。两个目标必须使用独立构建目录；修改配置后重跑包含 `-C` 的命令。板端不运行 Ubuntu CTest。

只复制 C++ 程序不足以启用 Python 人格核心。还需要匹配的 ARM Python、共享核心、动态库、证书、角色种子及可写数据目录。部署包生成命令：

```sh
../../.venv/bin/python scripts/package-python-core.py \
  --target-root /你的SDK对应的Buildroot输出目录/target \
  --voice build/rv1106/rootlink-voice \
  --lvgl-source /你的DeskBot_demo/lvgl \
  --output build/python-arm-user-release
```

把占位路径换为真实路径，输出目录必须尚不存在。包是匹配固件 rootfs 的 overlay，由固件流程合入；不要用 WSL 的 x86 Python 替代，也不要向不匹配的运行系统直接覆盖系统库。详细步骤见 [PYTHON_CORE.md](PYTHON_CORE.md#arm-部署包)。

板端采用 [rv1106-python.conf.example](config/rv1106-python.conf.example)：`TARGET=rv1106`、`UI_BACKEND=fbdev`、`UI_DEVICE=/dev/fb0`，声卡按板端实际设备配置。包内运行配置为 `/etc/rootlink/python.conf`；密钥填入 `/etc/rootlink/rootlink-secrets.env`，人格数据存入 `/data/rootlink/python-data`。

首次在板端准备密钥与数据目录，已有文件不会被覆盖：

```sh
test -f /etc/rootlink/rootlink-secrets.env || cp /etc/rootlink/rootlink-secrets.env.example /etc/rootlink/rootlink-secrets.env
chmod 600 /etc/rootlink/rootlink-secrets.env
mkdir -p /data/rootlink/python-data /data/rootlink/config
```

然后用编辑器填写密钥，确保实际运行程序的用户能读取密钥并写入数据目录。默认 Qwen 可以使用程序内置端点；若要自定义端点或切换供应商，把开发机的 `config/models.json.example` 复制到板端 `/data/rootlink/config/models.json` 后编辑，不复制含有私人密钥的本地 models.json。完成后验证并启动：

```sh
/usr/bin/python3.11 /opt/rootlink/check-python-target.py
/usr/bin/rootlink-voice doctor --config /etc/rootlink/python.conf
/usr/bin/rootlink-voice voice --config /etc/rootlink/python.conf
```

当前已验证交叉编译和 ARM 解释器的 QEMU 导入；实板显示、声卡、启动耗时、内存峰值和长时间对话仍待测量，参见 [VALIDATION.md](VALIDATION.md)。

## 6. 角色、历史与常见问题

常用运行参数的作用如下；不熟悉的项先保持模板默认值：

| 参数 | 含义 |
| --- | --- |
| `PERSONA_BACKEND=python` | 启用共享人格核心；`simple` 为兼容后端 |
| `PYTHON_EXECUTABLE`、`PYTHON_CORE_ENTRY` | 解释器和核心入口路径，不能把两者拼成一条命令 |
| `PYTHON_DATA_DIR` | Python 的独立可写数据目录 |
| `SESSION_DIR` | 兼容 C++ 会话目录；Python 不向这里追加另一份对话 |
| `CAPTURE_DEVICE`、`PLAYBACK_DEVICE` | ALSA 录音和播放设备名；WSLg 默认 `pulse` |
| `UI_BACKEND` | `none` / `sdl` / `fbdev`，需与编译能力匹配；启动脚本固定启用 SDL |
| `UI_WIDTH`、`UI_HEIGHT` | SDL 窗口尺寸，默认 320×240；framebuffer 使用设备实际尺寸 |
| `UI_TEXT_INTERVAL_MS` | 下半部分回复逐 Unicode 字符显示间隔，默认 50 ms，允许 10–1000 ms；环境变量可覆盖配置 |
| `UI_DEVICE` | framebuffer 设备，默认 `/dev/fb0` |
| `PERSONA_START_TIMEOUT_MS` | Python 启动等待，默认 30000 ms |
| `PERSONA_TURN_TIMEOUT_MS` | 完整人格处理等待，默认 300000 ms |
| `ASR_TIMEOUT_MS`、`LLM_TIMEOUT_MS`、`TTS_TIMEOUT_MS` | 各服务请求超时，默认 45000 / 60000 / 45000 ms |

若希望暂时不开窗口，直接运行二进制并通过环境变量覆盖：

```sh
UI_BACKEND=none build/ubuntu/rootlink-voice voice --config build/windows-cloud/python-ui.conf
```

`ROLE_DIR` 是初始种子，必须包含非空 `persona/profile.json`。Python 首次运行会复制到 `PYTHON_DATA_DIR/default`，后续恢复该目录已有数据。关闭程序后备份整个 `PYTHON_DATA_DIR`，即可保留人格、记忆和会话数据。测试新角色时选一个新的独立数据目录；修改种子不会覆盖旧运行数据，也不要让两个程序同时使用同一数据目录。

| 现象 | 检查方法 |
| --- | --- |
| 缺少密钥、401 或认证失败 | 检查 `SECRETS_FILE`、所选供应商和同名环境变量；确认账户模型权限 |
| 改了模型却请求旧地址 | 检查 `LLM_BASE_URL` 环境变量或运行配置是否覆盖 models.json |
| `Unknown PCM pulse`、录不到声音 | 检查 ALSA Pulse 插件、WSLg 音频和 Windows 麦克风权限，按 WINDOWS.md 排查 |
| SDL 无法创建窗口 | 在 WSLg 图形会话运行，检查 SDL2 依赖；编译配置与 `UI_BACKEND` 要匹配 |
| Python 启动失败 | 检查 `.venv` 依赖、解释器和入口路径、角色 profile，以及数据目录是否被另一进程占用 |
| 编译提示切换目标或旧缓存 | 对新入口分别使用 `build/ubuntu`、`build/rv1106`，不要复用旧脚本目录 |
| 回答很慢，一直显示 `....` | ASR、LLM、摘要和 TTS 都属于处理阶段；完整人格操作默认上限 300 秒 |
| 说话被过早截断 | 可按实际噪声调整 `VAD_END_SILENCE_MS`，默认 800；毫秒项需满足配置校验，不必首次就调参 |
| 修改 `HISTORY_TURNS` 不影响人格历史 | 该项及 `HISTORY_TOKEN_BUDGET` 供简化 C++ 后端使用；Python 使用自己的角色与会话配置 |
| 修改源码后还是旧行为 | C++ 改动重新构建；Python 源码改动重启进程，板端重新打包发布 |

要完全离线测试，可保留旧入口 `sh scripts/build.sh config/rootlink.conf`，默认 `simulator + simulated + mock` 不访问真实声卡或 API。不要把云版本仅通过运行参数改为 mock；后端依赖在构建时确定。
