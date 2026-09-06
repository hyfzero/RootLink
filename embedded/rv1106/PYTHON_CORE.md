# Python 人格核心与状态主界面

Python `src/agent_core` 是唯一人格实现。桌面与嵌入式入口复用 `SessionManager`，包括 Prompt、关系与人格状态、记忆选择与更新、会话恢复，以及日月摘要和相关 LLM 调用。部署包中的源码是该实现的发布快照，后续修改源代码后重新打包，不维护另一套人格逻辑。

链路：C++ 采集 → ASR → 常驻 Python 会话 → 最终回答 → C++ TTS → 播放。

## Windows / WSL 启动

推荐使用 [统一 CMake 构建配置](BUILDING.md)：`config/build.cmake` 选择 `ubuntu` 或 `rv1106`。Windows 启动脚本优先运行新产物 `build/ubuntu/rootlink-voice`。下文旧脚本入口继续兼容。

本机已准备带窗口的测试版本：在 Windows 双击本目录的 `start-wsl-ui.cmd`，或在 WSL 的本目录执行 `sh scripts/run-wsl-ui.sh`。使用 `build/windows-cloud/python-ui.conf`，沿用现有模型与密钥文件，声卡为 `pulse`，窗口为 320×240；本轮测试人格数据存入 `build/windows-cloud/ui-python-data`。该启动入口会开启真实麦克风和云语音对话，关闭窗口或 Ctrl+C 退出。此配置和二进制属于本地 build 产物，其他电脑需按下文构建。

先按 [WINDOWS.md](WINDOWS.md) 准备 WSLg、ALSA PulseAudio 插件和云构建依赖。在 **WSL** 中执行：

```sh
cd /mnt/d/linux_test/AmaduesBot/RootLink
python3 -m venv .venv
.venv/bin/python -m pip install -r embedded/rv1106/requirements-core.txt
cd embedded/rv1106
mkdir -p build/windows-cloud
cp config/windows-python.conf.example build/windows-cloud/python.conf
```

如果上述配置文件已经存在，直接编辑它，避免覆盖本地设置。只安装轻量核心依赖，不安装 Flet、Pillow、桌面打包工具或大型 tokenizer。模型使用现有 `MODELS_FILE` 和供应商设置，密钥沿用环境变量 → `SECRETS_FILE` → models.json 中 api_key 的优先级。Qwen + DashScope ASR/TTS 只需填写 `DASHSCOPE_API_KEY`；密钥文件是单独的文本文件，无需写入命令行。

```sh
chmod 600 config/rootlink-secrets.env
sh scripts/build.sh build/windows-cloud/python.conf
build/simulator-alsa-cloud/rootlink-voice doctor --config build/windows-cloud/python.conf
build/simulator-alsa-cloud/rootlink-voice chat --config build/windows-cloud/python.conf --text '你好'
build/simulator-alsa-cloud/rootlink-voice voice --config build/windows-cloud/python.conf
```

`doctor` 校验 Python 握手和声卡开关；不带 `--probe-cloud` 时不调用云模型。`chat` 和 `voice` 会产生模型费用并更新独立的联调数据副本。

| 配置 | 用途 / 默认 |
| --- | --- |
| `PERSONA_BACKEND` | `simple` 保持旧 C++ 后端；显式设置 `python` 启用共享核心 |
| `PYTHON_EXECUTABLE` | 开发环境 `../../.venv/bin/python`；板端 `/usr/bin/python3.11` |
| `PYTHON_CORE_ENTRY` | 开发环境 `scripts/persona-worker.py` |
| `PYTHON_DATA_DIR` | 独立可写目录，例如 `build/windows-cloud/python-data` |
| `ROLE_DIR` | 初始角色种子，例如 `config/role-example` |
| `PERSONA_START_TIMEOUT_MS` | 启动握手 30000 ms |
| `PERSONA_TURN_TIMEOUT_MS` | 完整对话 300000 ms，包含可能触发的摘要 |
| `LLM_TIMEOUT_MS` | 单次 Python HTTP 请求超时；完整操作另受上项限制 |

相对路径按当前工作目录解释；解释器与入口作为独立参数传给系统，不通过 shell 拼接。Python 后端当前运行于 Linux/WSL，Windows 原生 `.exe` 不支持该子进程接口。ASR/TTS 继续读取 C++ 自己的供应商配置。

## 数据、协议与故障

首次启动要求种子包含非空 `persona/profile.json`，将角色 profile/state/memories/speaking_style 和 config 复制到 `PYTHON_DATA_DIR/default`，保持原有 Python JSON 格式。种子与运行目录不能相同或互相包含。后续从该目录恢复，不重复导入种子，也不合并 C++ `SESSION_DIR` 历史。修改种子不会覆盖已运行的人格；需要重新联调时选择一个新的数据目录。

Python 独占人格、记忆和历史写入，目录锁阻止两个 worker 同时使用同一数据目录。启用 Python 时 C++ 只提交当前用户文本，不拼接人格 Prompt、不另调对话 LLM、不追加 C++ 会话文件。工具执行关闭；摘要仍按现有核心规则触发，无独立后台调度。

协议为标准输入/输出上的 UTF-8 JSON 行，不开放网络端口。每行上限 2 MiB，用户消息上限 128 KiB。`v=1`，请求 `id` 为递增正整数，事件回显同一 ID。

```json
{"v":1,"id":1,"op":"init","settings":{"data_dir":"/data/rootlink/python-data","role_dir":"/opt/rootlink/role-seed","model":{"name":"qwen-plus","provider":"qwen","base_url":"https://dashscope.aliyuncs.com/compatible-mode/v1","api_key":"<通过私有进程通道传入>"}}}
{"v":1,"id":1,"event":"ready"}
{"v":1,"id":2,"op":"message","text":"你好"}
{"v":1,"id":2,"event":"delta","text":"你好。"}
{"v":1,"id":2,"event":"done","text":"你好。"}
{"v":1,"id":3,"op":"health"}
{"v":1,"id":3,"event":"ready"}
{"v":1,"id":4,"op":"shutdown"}
{"v":1,"id":4,"event":"done","text":""}
```

适配层还传递 `headers`、`auth_header`、`chat_path` 和 `llm_timeout_ms`。日志不记录协议内容和密钥。旧核心可能输出的诊断被无界面入口抑制，标准输出仅供协议使用；C++ 的固定错误提示写标准错误。

文本增量只供显示；TTS 仅使用 `done.text`。超时、非法协议、认证/网络失败或子进程退出会终止当前轮，清理进程与音频，不自动降级、不重放消息。重新运行应用后恢复已保存数据。核心可能已保存用户输入及部分状态更新，失败不意味着整轮事务回滚；未完成回答不作为完整回答播放。摘要的非致命失败行为沿用共享核心。

## LVGL 单主界面

默认无界面。需要 WSL 窗口时，在配置中设置 `UI_BACKEND=sdl`，然后执行：

```sh
export LVGL_SOURCE_DIR=/mnt/d/linux_test/AmaduesBot/Amadues_chatRobo/Demo/DeskBot_demo/lvgl
sh scripts/build.sh build/windows-cloud/python.conf
build/simulator-alsa-cloud-sdl/rootlink-voice voice --config build/windows-cloud/python.conf
```

LVGL 使用参考目录现有版本，仅链接核心和选定显示后端，不引入 DeskBot 菜单、聊天库或其他应用。WSL 需要 SDL2 开发库和可用的 WSLg 图形会话。`UI_WIDTH=320`、`UI_HEIGHT=240` 为窗口默认尺寸。板端使用 `UI_BACKEND=fbdev`、`UI_DEVICE=/dev/fb0`；屏幕尺寸读取 framebuffer 实际信息，支持 RGB565 / XRGB8888 真彩色。资源在退出时显式释放。

| 状态 | 黑底白色居中符号 |
| --- | --- |
| 正在采集、等待说话 | `？` |
| ASR、人格处理、TTS 合成 | `....` |
| 实际播放回答 | `！` |
| 初始化、空闲、正常停止 | `—` |
| 故障 | `×`，保留到退出 |

符号采用小型拉丁字体和线段绘制，不加载整套中文字库。界面仅在 `voice` 命令中打开。LVGL 在主线程运行，语音在工作线程运行，状态通过线程安全快照更新。关闭窗口或 Ctrl+C 取消处理，等待释放音频与 Python 后再退出；发生故障时窗口保留 `×`，关闭窗口退出。`UI_BACKEND=none` 保持原有命令行行为。

## ARM 部署包

必须使用与实际固件匹配的 SDK Buildroot target 根目录，不能打包 WSL 的 x86 解释器。当前使用 SDK Python 3.11、ARM32 EABI5、uClibc。构建时给出 SDK 与 LVGL 路径：

```sh
export RV1106_SDK_ROOT=/mnt/d/linux_test/AmaduesBot/Amadues_chatRobo/SDK/rv1106-sdk
export LVGL_SOURCE_DIR=/mnt/d/linux_test/AmaduesBot/Amadues_chatRobo/Demo/DeskBot_demo/lvgl
export RV1106_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
sh scripts/build.sh config/rv1106-python.conf.example
../../.venv/bin/python scripts/package-python-core.py \
  --target-root /home/asd665940056/.cache/amadues/rv1106-buildroot-output/target \
  --voice build/rv1106-alsa-cloud-fbdev/rootlink-voice \
  --lvgl-source "$LVGL_SOURCE_DIR" \
  --output build/python-arm-release
```

`--target-root` 替换为本机 SDK 对应的 target 路径；输出必须是尚不存在的目录。脚本提取解释器、标准库、共享核心、固定版本轻量依赖、TLS/CA、动态库依赖闭包和配置示例，验证全部 ELF 为 ARM32，再生成 manifest 与 tar.gz。归档是同版本 rootfs 的 overlay，包含 libc/TLS 等库；由固件构建流程合入匹配的 rootfs，不在不匹配的运行系统上盲目覆盖系统库。

部署后复制 `/etc/rootlink/rootlink-secrets.env.example` 为 `/etc/rootlink/rootlink-secrets.env` 并填写密钥，限制文件权限，保证 `/data/rootlink` 可写，然后在板端执行：

```sh
/usr/bin/python3.11 /opt/rootlink/check-python-target.py
/usr/bin/rootlink-voice doctor --config /etc/rootlink/python.conf
/usr/bin/rootlink-voice voice --config /etc/rootlink/python.conf
```

包内不包含真实密钥或本机联调历史。实板还需验证显示设备、声卡配置、证书时钟、启动耗时、内存峰值和连续对话稳定性；QEMU 的 ARM 导入成功不等于实板验收成功。

## 回归与验收

在 `embedded/rv1106` 目录执行：

```sh
../../.venv/bin/python tests/test_persona_bridge.py
ctest --test-dir build/simulator-alsa-cloud-sdl --output-on-failure
sh scripts/build.sh config/rootlink.conf
build/simulator-alsa-cloud-sdl/rootlink_ui_preview build/ui-preview
```

对照测试固定时间、初始数据与模拟 HTTP 响应，比较直接 Python 调用和 C++ 进程接口调用的 Prompt、API 请求、回答、人格状态、记忆及历史，覆盖多轮、情绪关系、记忆注入、历史预算、重启、跨日和跨月。仅规范化时间戳与消息 ID。故障测试检查单次调用、无密钥泄露、进程中断、超时、截断流、非法协议、目录锁、健康检查与退出。

真实链路验证使用已有录音样本依次执行 `transcribe`、`chat`、`synthesize`，并由 `aplay -D pulse` 播放最终 WAV。CosyVoice 返回的已知阿里 OSS HTTP 签名地址仅升级 scheme 为 HTTPS，查询签名保持原样；其他 HTTP 地址仍拒绝。对 CosyVoice 已确认的流式 WAV 占位长度做受限修正，通用 WAV 校验保持严格。旧 audio-smoke 播放要求完整 20 ms 帧，任意长度的 TTS WAV 可用 aplay 检查；正式语音运行时会给尾帧补静音。

最新结果及限制见 [VALIDATION.md](VALIDATION.md)。
