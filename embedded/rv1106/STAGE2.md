# Stage 2：RV1106 半双工语音对话

本模块在 Phase 1 音频接口上新增 `rootlink-voice`。现已支持复用单一 Python 人格核心和可选 LVGL 单主界面，配置、协议及部署见 [PYTHON_CORE.md](PYTHON_CORE.md)。下文的 C++ 角色/历史处理和临时错误恢复规则适用于旧 `PERSONA_BACKEND=simple` 后端；Python 后端独占数据，错误时退出当前链路且不自动降级。
只参考 Echo-Mate 相同硬件与配置体验，不复用其 GPL PortAudio/Opus 源码。

流程：麦克风 → 自适应能量 VAD → DashScope ASR → RootLink 角色和最近历史 →
可切换国内 LLM → DashScope TTS → 扬声器。识别开始前关闭采集，播放结束后才恢复采集。
没有唤醒词、工具执行、流式 ASR/TTS、全双工打断、云同步或中转服务器。

## 1. 一份配置选择电脑/开发板与 API

Windows 用户先看 [Windows 仿真、真实声卡与 API 配置](WINDOWS.md)：包含原生离线
运行命令，以及 WSL2/WSLg 音频桥接的配置和逐步验收。原生真实声卡后端尚未实现。

编辑带中文注释的 [config/rootlink.conf](config/rootlink.conf)。在本目录执行下面所有命令。
配置只支持 `KEY=VALUE` 和整行 `#` 注释，不支持引号、shell 表达式、行尾注释。
相对路径按**进程工作目录**解释，不是按配置所在目录；板端请使用绝对路径。

| TARGET | AUDIO_API | SERVICE_MODE | 用途 |
| --- | --- | --- | --- |
| simulator | simulated | mock | 无声卡、无密钥、完全离线的自动对话仿真 |
| simulator | alsa | cloud | Linux 电脑真实声卡与云 API |
| rv1106 | alsa | cloud | 与 Echo-Mate 相同硬件的 32 位 ARM 程序 |

`TARGET` 决定编译目标，不是固件烧录格式；Linux/WSL 构建产物是 ELF，Windows 原生构建产物是 `.exe`。
后端在编译期选择，不能只修改配置就让 mock 二进制联网。切换以上三项后重新构建：

```sh
sh scripts/build.sh config/rootlink.conf
build/simulator-simulated-mock/rootlink-voice doctor --config config/rootlink.conf
build/simulator-simulated-mock/rootlink-voice voice --config config/rootlink.conf --duration 15
```

仿真采集每帧 20 ms，循环产生静音/测试波；ASR 返回固定中文，LLM 返回固定分段回复，
TTS 返回测试音而非人声，播放只按音频时间推进，不访问真实扬声器。
`rootlink-audio-smoke` 仍可单独录音/播放/回环，默认仿真录音保持 Phase 1 的连续测试波。

Linux/WSL 要求 CMake ≥ 3.18、C++17 编译器；云版另需 ALSA、libcurl（TLS）、json-c 开发包。
WSL 不直接提供板端 ALSA 声卡；可尝试经 WSLg PulseAudio 桥接电脑声卡，须先通过
[Windows 音频验收](WINDOWS.md)，这不等于板端硬件验收。Windows 原生仅支持模拟后端，
使用 CMake/MSVC 构建，统一 shell 入口在 WSL 内执行。

## 2. 国内模型与密钥

默认：ASR `qwen3-asr-flash`，LLM `qwen-plus`，TTS `cosyvoice-v3-flash` / `longanyang`。
这只是配置示例，不是代码中的模型白名单；账号需开通相应服务且支持指定模型/音色。

将 RootLink 导出的 `models.json` 放到配置指定位置，或从
[models.json.example](config/models.json.example) 复制模板。读取 `providers`、`base_url`、
`headers`、布尔 `auth_header`、兼容旧 `api_key` 以及顶层 `default_provider/default_model`。
附加字段 `chat_path` 默认为 `/chat/completions`，用于兼容端点的自定义路径。
只适配 OpenAI chat/completions 协议，不适配 Anthropic messages。

更换 LLM 时同时改 `LLM_PROVIDER` 和 `LLM_MODEL`，确保 `models.json` 中有同名 provider
与正确的 `base_url`。不要保留指向其他供应商的 `LLM_BASE_URL` 覆盖项。
若希望完全继承 RootLink 默认 provider/model，请注释配置中的这两个显式字段。
模板已列出五家供应商的兼容入口；非默认模型名请填写账号当前可用的模型 ID。

| Provider 标识 | 密钥变量 |
| --- | --- |
| qwen / dashscope | DASHSCOPE_API_KEY |
| deepseek | DEEPSEEK_API_KEY |
| glm | GLM_API_KEY |
| moonshot / kimi | MOONSHOT_API_KEY |
| minimax | MINIMAX_API_KEY |

同一个 DashScope 密钥默认供 ASR、Qwen LLM 和 TTS 使用。切换 DeepSeek 等只影响 LLM，
ASR/TTS 仍需 DashScope 密钥。`auth_header=false` 时不生成 Bearer 头，可通过 `headers`
提供供应商特定认证，但其中敏感内容也必须留在未提交的私有 models 文件中。

从 [rootlink-secrets.env.example](config/rootlink-secrets.env.example) 复制私有密钥文件，
编辑后设为 `chmod 600`。不要把真实密钥放在命令行、公共配置或版本库中。
本目录忽略 `config/rootlink-secrets.env`、`config/models.json` 和构建产物。

普通参数优先级：支持的命令行覆盖项 > 环境变量 > rootlink.conf 显式项 > models.json > 缺省值。
密钥优先级：进程环境变量 > SECRETS_FILE > models.json 的 api_key；没有密钥命令行参数。
密钥文件仅用于密钥，不替代普通配置。权限过宽时警告，不打印密钥值。

## 3. 六个命令

以下用 `rootlink-voice` 表示对应构建目录中的二进制；每次均应传 `--config`。

```sh
rootlink-voice doctor --config config/rootlink.conf
rootlink-voice vad --config config/rootlink.conf --duration 10 --output-dir build/live-segments
rootlink-voice vad --config config/rootlink.conf --input input.wav --output-dir build/segments
rootlink-voice transcribe --config config/rootlink.conf --input input.wav
rootlink-voice chat --config config/rootlink.conf --text '你好，今天过得怎么样？'
rootlink-voice synthesize --config config/rootlink.conf --text '你好' --output build/reply.wav
rootlink-voice voice --config config/rootlink.conf --duration 600
```

`vad` 不传 `--input` 时直接使用所选采集 API，自动将完整语句保存为
`segment-1.wav`、`segment-2.wav` 等；仿真模式无需硬件即可验证。省略 `--duration`
会持续监听直到 Ctrl+C。停止时丢弃尚未完成的语句；离线 WAV 则补足尾部静音。
请每次选择新的输出目录，避免覆盖同名片段。此命令不加载角色、不写会话、不调用云 API。

`doctor` 默认只检查配置、角色目录、编译后端、TLS/CA、密钥是否存在及设备能否打开。
它不检验密钥是否有效，也不验证云端可达性。只有 `doctor --probe-cloud` 明确调用
LLM、TTS、ASR 三项（会计费），默认测试和验收脚本不会自动加此参数。
`SERVICE_MODE=cloud` 时其他云命令和完整 voice 本身会计费。

支持 `--capture-device`、`--playback-device`、`--buffer-frames`、`--asr-model`、
`--llm-model`、`--tts-model`、`--tts-voice`、`--role-dir`、`--session-dir`。
Ctrl+C/SIGTERM 通过信号标志取消，信号处理器不调用 curl、不加锁或关闭音频句柄。
取消和设备关闭由运行线程完成，HTTP 通过进度回调终止，退出耗时受驱动响应影响。

## 4. 角色、历史与内存边界

正式部署建议 `ROLE_DIR=/data/rootlink/roles/default`、`SESSION_DIR=/data/rootlink/sessions`。
支持 `persona/profile.json` 或扁平 `profile.json`，其余 state/memories/speaking_style
支持相应根目录或 persona 子目录。示例在 [role-example](config/role-example)。
系统提示按照 `lib/domain/rootlink_agent_runtime.dart` 的身份、状态、长期记忆、风格顺序生成，
之后是最近历史、当前用户输入。只读取角色，不替代 RootLink 的角色状态演化逻辑。
默认最近 8 轮，历史约 12,000 token；采用 UTF-8 字符近似估算，非模型精确 tokenizer。
每个角色 JSON 限 256 KiB、models/config 限 1 MiB、单次 JSON/SSE 响应限 2 MiB。

LLM 成功即追加 user/assistant 到 `<SESSION_DIR>/<角色目录名>/YYYY-MM-DD.jsonl`，
再开始 TTS，因而 TTS 失败不丢已生成回答。重载跳过损坏行，追加前隔离残留半行。
每个日期文件最多读尾部 1 MiB，内存历史有上限。单进程单角色写入，不支持多进程同时写同一会话。
会话是持续增长的本地日志，磁盘保留/清理策略由部署方负责；flush 不等同于掉电级 fsync 保证。

VAD 阈值为绝对 RMS 下限与噪声基线倍率的较大值，仅非语音帧更新 EWMA。
连续 3 帧开始，完整保留首个阳性帧前 400 ms；800 ms 静音结束，语音阳性帧累计至少 300 ms。
最长 30 秒包含预录音和尾部静音。语句区预分配 960,000 字节，预录音约 14.7 KB，
环形区默认 64 KB。云端 WAV/Base64/JSON 另占工作内存，**并非整个进程仅占 1 MiB**。
能量 VAD 无法辨别人声与持续大噪声，应先通过离线 `vad` 和实录调阈值。
采集和 VAD 同线程快速消费，环形区高水位可能仅 1；并不是额外的后台采集队列。

## 5. 云协议与失败策略

ASR 使用内存 WAV Data URI，不公开上传文件；LLM 按任意字节边界解析 SSE，隐藏
`reasoning_content`，MiniMax 累积正文去重，识别但拒绝执行工具请求。缺少完成标志的
断流不会保存半个回答。网络只对连接失败/429/5xx 重试一次，已有 SSE 正文后不重发。
鉴权、其他 4xx、TLS 配置及存储/设备错误退出；单轮超时、临时网络或供应商错误恢复监听。

TTS 请求 `input` 中指定 text/voice/format/sample_rate。下载上限 8 MiB，仅 HTTPS，
证书验证不可关闭，下载不附带 API 密钥；WAV 必须为 16 kHz/mono/PCM16，无隐式重采样。
已通过真实账号确认：已知阿里 OSS 主机的 HTTP 签名地址可保持路径/查询签名不变，仅将 scheme 升级为 HTTPS 后下载；其他 HTTP 地址仍拒绝。CosyVoice 的已知流式 WAV 长度占位值做受限修正，通用 WAV 校验保持严格。
默认连接 5 秒、ASR/TTS 每次请求 45 秒、LLM 60 秒；TTS 合成和下载为两次请求。
日志不包含录音、密钥或完整云响应，但 transcript/answer 和会话仍是私人对话，请限制权限。

协议依据：[Qwen ASR](https://help.aliyun.com/en/model-studio/qwen-asr-api-reference)、
[Qwen OpenAI 兼容](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)、
[CosyVoice HTTP](https://help.aliyun.com/en/model-studio/cosyvoice-tts-http-api)。
百炼新业务空间域名可通过各 `*_BASE_URL` 覆盖；北京旧域名仍保留为默认，密钥地域必须匹配。

## 6. 交叉编译和板端验收

在外部 Echo-Mate SDK 中生成其板级配置对应的 Buildroot rootfs，启用：

```text
BR2_PACKAGE_ALSA_LIB=y
BR2_PACKAGE_LIBCURL=y
BR2_PACKAGE_JSON_C=y
BR2_PACKAGE_OPENSSL=y
BR2_PACKAGE_CA_CERTIFICATES=y
```

还需确保 libcurl 启用 HTTPS/OpenSSL，并且 C++ 工具链包含标准库/filesystem 支持。
SDK 的 `./build.sh rootfs` 会修改外部 SDK 构建输出，耗时与磁盘需求取决于 SDK；
本项目不会自动下载、提交 SDK 或修改其板级配置。

```sh
export RV1106_SDK_ROOT=/absolute/path/to/rv1106-sdk
TARGET=rv1106 AUDIO_API=alsa SERVICE_MODE=cloud sh scripts/build.sh config/rootlink.conf
sh scripts/verify-arm.sh build/rv1106-alsa-cloud/rootlink-voice /absolute/path/to/buildroot/sysroot
```

工具链检查 Echo-Mate Buildroot 2023.02.6 `output/host/bin` 中的 Rockchip wrapper，
查询其 sysroot，查找目标 ALSA/curl/json-c/OpenSSL 库；CA 可位于 staging sysroot 或 target rootfs。
如果 SDK 已有目标库但尚未打包 CA，可显式指定可信系统提供的证书包（证书是架构无关数据）：

```sh
export RV1106_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
TARGET=rv1106 AUDIO_API=alsa SERVICE_MODE=cloud sh scripts/build.sh config/rootlink.conf
```

此时构建会把 CA 复制到 `build/rv1106-alsa-cloud/deployment/etc/ssl/certs/ca-certificates.crt`。
必须同时部署到板端 `/etc/ssl/certs/ca-certificates.crt`，不能仅复制可执行程序；
也可继续用 Buildroot 的 CA 组件生成完整 rootfs。部署前检查系统时间，时间错误会导致证书校验失败。
GCC 8 的独立 `stdc++fs` 库由 CMake 自动链接，使用目标工具链而非主机库。
`verify-arm.sh` 使用 file/readelf 检查 ELF32 ARM、目标依赖和 curl TLS，不在主机执行 ARM 文件。
缺失 wrapper 时不能拿裸编译器或主机库冒充交叉编译成功。

板端部署匹配 rootfs 的二进制与动态库、CA、角色及私有配置；将配置三项设为
`rv1106/alsa/cloud`，路径改为 `/data/rootlink/...`。声卡默认 default，不可用则选择实际 `hw:X,Y`。
不要盲目提高混音器音量。先跑 Phase 1 录音回放，再跑：

```sh
sh scripts/voice-acceptance.sh /usr/bin/rootlink-voice /data/rootlink/config/rootlink.conf 600 --allow-cloud
```

脚本生成权限受限的独立报告目录，采样 `/proc/<pid>/status`，输出 VAD、各阶段累计耗时、
网络重试/错误、缓冲容量/高水位/丢帧、ALSA 恢复次数及 RSS/VmHWM；不自动调整声卡。
手动检验句首、自然停顿、播放不自触发、速度音质、临时断网后恢复以及 Ctrl+C 退出。
预热至少 60 秒后检查 RSS 曲线是否持续上升；10 分钟是最低验收，不是无泄漏证明。

## 7. 可复现离线测试与交付状态

```sh
cmake -S . -B build/pure -DROOTLINK_AUDIO_API=none -DROOTLINK_SERVICE_API=mock -DBUILD_TESTING=ON
cmake --build build/pure --parallel
ctest --test-dir build/pure --output-on-failure
cmake -S . -B build/cloud -DROOTLINK_AUDIO_API=alsa -DROOTLINK_SERVICE_API=curl -DBUILD_TESTING=ON
cmake --build build/cloud --parallel
ctest --test-dir build/cloud --output-on-failure
sh scripts/test-voice-cli.sh build/simulator-simulated-mock/rootlink-voice config/rootlink.conf
```

纯逻辑测试不链接 ALSA/curl/json-c；云协议测试额外需要 curl/json-c 开发包，但使用
注入的假 HTTP 响应，不访问网络，不读取真实密钥，不产生费用。
覆盖帧队列、百万帧容量压力、VAD 边界、WAV/Base64、SSE 逐字节分包、协议请求、
鉴权/重试/断流、角色提示黄金文本、会话残行恢复、半双工和各阶段取消。

实际构建、测试与尚未验证项目见 [VALIDATION.md](VALIDATION.md)。
