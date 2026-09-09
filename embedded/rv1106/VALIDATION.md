# Python 核心、语音与 LVGL 验证记录

## 2026-09-07：超时恢复与点击重置

WSL `build/ubuntu` 完成重新编译，离线测试 **6/6** 通过。新增模拟 ASR/TTS 超时后完成下一轮对话的测试，检查无重复 LLM 消息、无第二份 Python 历史、无误锁存 Error；Python 处理超时仍停止且不重放。SDL dummy 驱动测试覆盖五种状态下点击、重复事件合并，以及真实应用主循环中三次故障→点击→重建工作线程→故障→关闭窗口。

无界面 `build/simulator-simulated-mock` 回归 **5/5** 通过，包括完整 mock CLI 与信号退出。`file` 验证新 Ubuntu 程序为 x86-64，framebuffer 程序为 ARM32 EABI5、加载器 `/lib/ld-uClibc.so.0`。

ARM framebuffer 程序已重新交叉编译至 `build/rv1106-alsa-cloud-fbdev/rootlink-voice`，包含可配置 evdev 触摸输入。尚未在实板验证触摸节点、驱动异常、连续重置及音频资源恢复，也未重新调用付费云服务进行真实语音验收。下文的部署归档及哈希是 2026-09-06 的历史产物，不包含本次重置改动。

日期：2026-09-06。环境：Windows / WSL、项目 .venv、C++17 Release；参考 DeskBot 的 LVGL 9.2.3 开发版本。实板未参与本轮验收。

## 已通过

| 验证 | 结果 |
| --- | --- |
| Python / C++ 核心对照及故障 | **6/6**，16.29 秒；使用最终 SDL 构建的 bridge driver |
| 共享 Python 原有行为 | **22/22**；流式会话、提示词响应指导、MiniMax 流式适配 |
| SDL 云构建的离线测试 | **5/5**，2.84 秒；状态映射、显示与关闭、云协议、音频核心、语音核心 |
| 旧配置、无界面离线回归 | **5/5**，17.36 秒；原 4 项加状态映射，包含完整 mock CLI 与 SIGINT |
| WSLg 实际窗口 | 五种符号逐一渲染并检查，320×240 黑底白色居中；修复背景透明导致的残影；返回空闲的像素一致性纳入测试 |
| ARM framebuffer 构建 | ELF32 ARM EABI5，加载器 /lib/ld-uClibc.so.0；不链接 SDL |
| 最终部署包 | build/python-arm-release.tar.gz，12,104,408 字节；838 项文件清单、71 个 ARM32 ELF、依赖闭包及 curl/OpenSSL 检查通过；含 LVGL 许可证 |
| 目标 Python 导入 | QEMU 执行包内 Python 3.11.6；核心、requests、ssl、ctypes、fcntl 导入成功，32 位，CA 可加载；OpenSSL 1.1.1v；未加载 Flet/Pillow |

归档 SHA-256：`36f1c0399fadffa31353b9694e1eb3dfcb13aa43fc862b93ef1006c2bae4d1e0`。包内程序与最终 framebuffer 二进制逐字节一致；文件清单哈希已复核，未打入真实密钥文件和联调历史。

Python 对照固定时间、种子数据与 HTTP 响应，比较 Prompt、API URL/消息、最终回答、人格/关系状态、记忆和历史。覆盖多轮、情绪关系、种子记忆、历史预算截断、重启、跨日及跨月摘要；仅规范化时间戳和消息 ID。配置映射验证模型、地址、请求路径、认证头及超时。

故障覆盖认证、网络、进程中断、超时、截断流、非法协议、目录互斥、健康检查及退出；确认不重放、不在失败后同步重试。语音测试检查处理时采集停止，播放设备启动后才通知 Playing，取消后释放资源。界面错误状态不被 Stopping/Idle 覆盖。

## 真实音频与云服务

此前无界面分步验证已完成：真实录音样本 `build/windows-audio-check/mic.wav` → DashScope ASR → Python 人格核心 / Qwen → CosyVoice TTS → WSL PulseAudio 播放。产物为 `build/windows-cloud/python-chain.wav`。已验证安全升级已知阿里 OSS URL 到 HTTPS，以及受限修复流式 WAV 长度占位。

最初 audio-smoke 播放任意长度 TTS WAV 因尾帧未对齐失败，随后 aplay -D pulse 播放成功；正式 VoiceRuntime 会给尾帧补静音。这是录音样本的分步验证，不能表述为连续实时麦克风/界面的完整验收。

本轮带界面联调脚本 `tests/check_recorded_ui_cloud.py` 已准备，但**尚未执行**。自动审批拒绝把这份具体录音发送至 DashScope/Qwen，要求明确授权该录音向该第三方发送。因此带界面的真实云语音状态同步尚未验收，与上述离线测试及此前无界面结果分别记录。

脚本通过独立 ALSA file 配置注入既有录音，使用 Pulse 采集时钟和真实扬声器，调用真实云服务，播放完成并恢复监听后发送 SIGINT 检查退出。不修改全局声卡配置，历史另存独立目录。

## 复现

在 embedded/rv1106 中执行，不访问真实云端：

```sh
PERSONA_TEST_DRIVER=build/simulator-alsa-cloud-sdl/rootlink_persona_bridge_driver \
  ../../.venv/bin/python tests/test_persona_bridge.py
ctest --test-dir build/simulator-alsa-cloud-sdl --output-on-failure
sh scripts/build.sh config/rootlink.conf
build/simulator-alsa-cloud-sdl/rootlink_ui_preview build/ui-preview
```

截图：build/ui-preview/{idle,listening,thinking,speaking,error}.bmp。CTest 原始日志位于各构建目录的 Testing/Temporary/LastTest.log。

获得该录音发送至云服务的授权后，执行下列联调；输出目录必须尚不存在：

```sh
../../.venv/bin/python tests/check_recorded_ui_cloud.py \
  --voice build/simulator-alsa-cloud-sdl/rootlink-voice \
  --config build/windows-cloud/python.conf \
  --input build/windows-audio-check/mic.wav \
  --output build/ui-cloud-check --allow-cloud
```

期望：Idle → Listening → Transcribing → Thinking → Synthesizing → Playing → Idle → Listening；处理阶段 ....，Playing 阶段 ！，恢复采集后 ？。结果写入输出目录的 result.json，含私人对话的日志仅留本地。

## 2026-09-06：统一 CMake 构建配置

- `cmake -S . -B build/ubuntu -C config/build.cmake` 原生编译完成；产物经 `file` 确认为 x86-64 Linux ELF，动态依赖含 SDL2。
- 同一配置通过 `-DROOTLINK_TARGET=rv1106` 覆盖目标后，在独立 `build/rv1106` 目录交叉编译完成；产物为 ARM32 EABI5，解释器 `/lib/ld-uClibc.so.0`，依赖 ALSA、curl、json-c、OpenSSL，不依赖 SDL。
- Ubuntu CTest **5/5**（状态、SDL dummy 预览、云协议模拟、音频核心、语音核心）；旧无界面离线构建 CTest **5/5**。
- 新 Ubuntu 程序使用本地 `python-ui.conf` 执行不带云探测的 `doctor`，结果 `doctor=ok`。本次没有发送录音或执行真实云对话。
- 尝试在 Ubuntu 构建目录切换 RV1106 被明确拒绝，随后重新加载配置恢复 Ubuntu 并增量构建成功。配置文件交付默认值保持 `ubuntu`。
- WSL 挂载盘构建出现约 1 秒文件时间偏差警告，构建退出码均为 0；上述 ELF 检查和主机测试通过。板端仍需按下面清单实测。
- Windows 启动脚本优先选择 `build/ubuntu/rootlink-voice`，继续使用现有本地运行配置。构建步骤见 [BUILDING.md](BUILDING.md)。

## 2026-09-08：日语翻译与 CosyVoice v3.5

- 实际 WSL SDL 目录 `build/ubuntu` 增量构建成功，CTest **6/6**（UI 状态、预览、重置、云协议、音频核心、语音核心）。未将用户的 SDL 构建改成无界面。
- 离线翻译测试覆盖源文本/译文为空、取消、下游不得被错误调用、无状态提示、DeepSeek 翻译专用关闭思考、截断/过滤结果拒绝和日本语 TTS 请求。人格请求保持原设置。
- 音色管理工具独立测试 **12/12**，包含状态轮询、恢复、模型绑定、域名校验、异常脱敏及超时参数校验；测试不访问真实云服务。
- `build/rv1106-alsa-cloud-fbdev/rootlink-voice` 交叉编译成功，ELF32 ARM EABI5 hard-float，解释器 `/lib/ld-uClibc.so.0`。WSL 挂载盘产生时钟偏差警告，构建成功。
- 用户授权只读查询音色，选定 ID `cosyvoice-v3.5-plus-bailian-ab03a1beb9264dd9aa221cf3c5e9c760`，模型 `cosyvoice-v3.5-plus`，查询状态 `OK`。本机配置已启用 `TTS_TRANSLATE_TO=ja`。
- 真实正式 `synthesize` 调用成功：固定中文文本“先把条件说清楚。一次实验还不能证明你的结论。” → 独立 DeepSeek 翻译 → CosyVoice 合成。输出 `build/windows-cloud/kurisu-japanese-check.wav`：110880 帧，6.93 秒，16 kHz / 单声道 / PCM16；通过 WSL `aplay -D pulse` 播放一次。仅执行一次合成链路，无自动重试；不调用人格、不录音、不写历史。不能据此宣称角色相似度、连续语音或实板验收成功。
- 本次未重新制作完整 ARM Python 部署归档；旧归档不能代表本次新二进制。实板运行与声音相似度不由编译或离线测试代替。

## 2026-09-09：语音超时诊断

- WSL SDL 增量编译成功，CTest **6/6** 通过；增加翻译回调、POST 503 和 GET 504 的阶段、耗时及错误类别验证。
- 保持当前连接 5000 ms、翻译与 TTS 各 60000 ms 的配置，真实合成三次短句和一次 56 字中文科学句，四次均返回日语译文并生成 WAV，没有复现超时。短句翻译 704–1071 ms、合成 1649–1791 ms、下载 842–990 ms；长句分别为 1116 / 5969 / 1333 ms。
- 产物为 `build/windows-cloud/kurisu-japanese-diagnostic1.wav` 至 `kurisu-japanese-diagnostic4.wav`。本次未录音、未更新人格历史，也未做听感验收。
- 原超时根因尚未复现，不能宣称已根治。新版错误明确区分翻译、CosyVoice POST、音频 GET，并提供无密钥和签名 URL 的网络时间诊断。没有扩大自动重试或增加中文回退。

## 2026-09-09：下半屏中文对话框

- 上半屏保留状态符号，下半屏增加深色细边框对话框，原始回答默认每 50 ms 显示一个 Unicode 字符。长文本换行并纵向滚动；点击重置清空显示及待显示内容，旧工作线程结束后才能开始新轮。
- WSL `build/ubuntu` 最终编译完成，CTest **6/6** 通过，包括 UTF-8 分片、无效编码、显示节奏、最终文本校正、显示缓冲上限、重置和实际字形解码。无界面 `build/simulator-simulated-mock` 编译完成、CTest **5/5** 通过。
- SDL dummy 与真实 WSLg 窗口预览均通过。已人工检查短句、长句滚动和清空截图；补上 `LV_USE_FONT_COMPRESSED=1` 后，中文和假名正常显示。截图位于本地 `build/ui-dialogue-preview/` 和 `build/ui-dialogue-wslg/`，不随源码提交。
- `build/rv1106-alsa-cloud-fbdev/rootlink-voice` 按最终字体配置交叉编译完成：ELF32 ARM EABI5，解释器 `/lib/ld-uClibc.so.0`；`size` 的 text/data/bss 合计 2,419,178 bytes，这不是运行时内存测量。构建出现已有挂载盘 clock-skew 和 LVGL 配置提示，无编译错误。
- 本次界面验证未重新调用真实录音与云语音链路，日语合成验证沿用上一节记录；中文显示保持原始回答，日语仅用于播报。尚未实测板端屏幕、中文逐字显示与声音的主观体验及连续运行资源占用，也未重新制作完整 Python 部署归档。

## 2026-09-09：标点补字与三行分页

- 字库补充 U+2000–U+206F 通用标点范围，确认弯引号、破折号及省略号具有实际字形并能解码。保持 16px / 2bpp；未宣称覆盖所有 Unicode 字符。
- 对话框按实际字体和宽度排版，每页最多三行；默认停留 2000 ms 后清屏逐字显示下一页，最后一页保留，替代上一节的纵向滚动。`UI_PAGE_HOLD_MS=0..10000` 可配置停留时间，字符间隔仍由 `UI_TEXT_INTERVAL_MS` 控制。
- WSL `build/ubuntu` 编译完成，CTest **6/6** 通过。新增验证覆盖连续三页、停顿、不突发补字、最终页保留、跨页换行、重置和配置边界；实际 LVGL 测量验证三行可容纳、四行拒绝。
- SDL dummy 与真实 WSLg 窗口预览通过，人工检查通用标点和完整三行无裁切。截图在本地 `build/ui-pages-preview/`、`build/ui-pages-wslg/`。本轮未调用录音或云服务，未做实板显示验收。
- 无界面回归 **5/5** 通过；framebuffer 版本交叉编译完成，产物确认为 ARM32 EABI5，解释器 `/lib/ld-uClibc.so.0`。当前 WSL 配置已写入 `UI_PAGE_HOLD_MS=2000`。

## 2026-09-10：日语音频与中文句段同步

- 有界面对话按中文句段分别翻译、合成日语；第一帧音频写入成功后才发布对应中文字幕，逐字速度由该段 PCM 时长计算。最多预取下一段；当前音频播放和字幕显示都结束后才切换。无界面仍使用完整回答合成。
- 保留每页三行及 `UI_PAGE_HOLD_MS` 停留；翻页停留冻结逐字时钟，可能使字幕结束晚于音频，此时等待字幕完成。属于句段级同步，不是中文词语与日语音素的时间戳对齐。
- WSL `build/ubuntu/rootlink-voice` 最终源码编译完成，CTest **6/6** 通过；无界面 `build/simulator-simulated-mock` 编译完成，CTest **5/5** 通过。覆盖 UTF-8 分句、连续三段播放、字幕确认、预取取消、等待超时、分页时钟及重置后拒绝旧确认。
- 真实 WSLg `rootlink_ui_preview` 退出码为 0，实际 LVGL 字体测量的字幕节奏、三行限制及窗口关闭检查通过；输出目录为 `build/ui-sync-wslg/`。本轮没有调用云服务、录音或进行真实日语音画听感验收。
- 字幕确认等待复用 `PERSONA_TURN_TIMEOUT_MS`（默认 300 秒）。超时或重置会取消并等待预取结束，不自动重放；字幕与下一段音频不会因丢失确认无限等待。
- framebuffer 交叉编译完成，`build/rv1106-alsa-cloud-fbdev/rootlink-voice` 为 ELF32 ARM EABI5，解释器 `/lib/ld-uClibc.so.0`。本轮未重新生成完整 Python 部署归档，未执行板端运行。
- 分段会增加翻译与 TTS 请求次数，也可能影响跨句语气连贯性；预取不能保证网络条件下无间隙。真实云语音、声卡缓冲延迟及板端资源占用仍需验收。

## 待实板和人工验收

- 与固件匹配的 SDK/rootfs 部署、framebuffer 像素格式、方向、声卡参数及音画状态同步。
- 启动耗时、Python+C++ 总内存峰值、至少 10 分钟连续对话及更长时间稳定性。
- 实际环境 VAD 句首/停顿、噪声误触发、播放不自触发、速度和主观音质。
- 真实网络/TLS/系统时钟、断网及退出时驱动响应。

QEMU 导入、WSLg 窗口和 mock 回归均不能替代实板成功。资源不足时基于当前接口与行为对照测试评估唯一 C++ 核心，不维护两份人格实现。启动与部署参见 [PYTHON_CORE.md](PYTHON_CORE.md)。
