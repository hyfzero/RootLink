# Python 核心、语音与 LVGL 验证记录

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

## 待实板和人工验收

- 与固件匹配的 SDK/rootfs 部署、framebuffer 像素格式、方向、声卡参数及音画状态同步。
- 启动耗时、Python+C++ 总内存峰值、至少 10 分钟连续对话及更长时间稳定性。
- 实际环境 VAD 句首/停顿、噪声误触发、播放不自触发、速度和主观音质。
- 真实网络/TLS/系统时钟、断网及退出时驱动响应。

QEMU 导入、WSLg 窗口和 mock 回归均不能替代实板成功。资源不足时基于当前接口与行为对照测试评估唯一 C++ 核心，不维护两份人格实现。启动与部署参见 [PYTHON_CORE.md](PYTHON_CORE.md)。
