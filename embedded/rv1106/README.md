# RootLink RV1106 音频核心与 Stage 2 语音对话

当前推荐入口：

- [用户手册](USER_MANUAL.md)：API 密钥填在哪里、运行配置、Ubuntu/WSL 与 RV1106 编译、启动和排错。
- [开发手册](DEVELOPER_MANUAL.md)：共享 Python 人格核心、C++ 语音链路、进程协议、UI 线程模型与测试扩展。
- [统一 CMake 构建配置](BUILDING.md)：新构建入口。下文 Phase 1 / Stage 2 旧入口保留用于兼容。

Stage 2 使用 [config/rootlink.conf](config/rootlink.conf) 统一选择仿真/开发板和 ASR、LLM、TTS。
完整使用、密钥、角色、交叉编译和验收说明见 [STAGE2.md](STAGE2.md)。
Windows 离线仿真和真实声卡 + LLM API 的配置步骤见 [WINDOWS.md](WINDOWS.md)。
当前原生 Windows 仅支持离线模拟；真实声卡方案使用 WSL2/WSLg 桥接，需先验收音频。
下面保留 Phase 1 音频核心说明；独立音频测试工具仍可使用。

This directory is an independent C++17 component for the Echo-Mate-compatible RV1106 board. It does
not change the RootLink Flutter or Python build, and it does not reuse Echo-Mate's GPL PortAudio/Opus
implementation.

## 一份配置切换仿真/开发板

编辑 [`config/rootlink.conf`](config/rootlink.conf)，然后在 Linux/WSL 执行：

```sh
sh embedded/rv1106/scripts/build.sh
```

配置项如下：

| 配置项 | 可选值 | 作用 |
| --- | --- | --- |
| `TARGET` | `simulator` / `rv1106` | 选择本机程序或 32 位 ARM 板端程序 |
| `AUDIO_API` | `simulated` / `alsa` | 选择无硬件仿真或真实 ALSA 声卡 |
| `BUILD_TYPE` | `Release` / `Debug` 等 | 选择优化或调试构建 |
| `BUILD_TESTS` | `ON` / `OFF` | 是否构建并运行主机测试 |
| `BUILD_DIR` | 路径或留空 | 自定义输出目录 |
| `RV1106_SDK_ROOT` | SDK 绝对路径或留空 | 板端交叉编译 SDK；留空时读同名环境变量 |
| `CAPTURE_DEVICE` | ALSA PCM 名称 | 编译进 CLI 的默认录音设备 |
| `PLAYBACK_DEVICE` | ALSA PCM 名称 | 编译进 CLI 的默认播放设备 |
| `BUFFER_FRAMES` | 正整数 | 编译进 CLI 的默认回环容量，推荐 100 |

推荐组合：

- `simulator + simulated`：默认配置，无麦克风、无 ALSA 也能录制测试波、播放和回环。
- `simulator + alsa`：在 Linux/WSL 上使用电脑真实声卡。
- `rv1106 + alsa`：生成 Echo-Mate 同硬件可运行的 ARM ELF。

`rv1106 + simulated` 会被构建入口明确拒绝。当前统一入口还会检查 SERVICE_MODE，
合法组合见 Stage 2 文档。旧 `rootlink-audio.conf` 只保留作为 Phase 1 参数参考。

## Fixed audio contract

- 16000 Hz, mono, signed 16-bit little-endian PCM
- 20 ms per frame: 320 samples / 640 bytes
- Loopback buffer default: 100 frames (2 seconds, 64,000 bytes of PCM storage)
- A full loopback buffer discards the oldest frame and increments `dropped_frames`

ALSA setup rejects a device when the negotiated rate, channels, format, or period differs from this
contract. Capture and playback use blocking ALSA operations and recover transient overruns/underruns
with `snd_pcm_recover()`.

## Host tests (no ALSA required)

```sh
cmake -S embedded/rv1106 -B embedded/rv1106/build/host \
  -DROOTLINK_AUDIO_API=none \
  -DROOTLINK_AUDIO_BUILD_CLI=OFF \
  -DBUILD_TESTING=ON
cmake --build embedded/rv1106/build/host --parallel
ctest --test-dir embedded/rv1106/build/host --output-on-failure
```

The tests cover FIFO/wrap/drop-oldest behavior, timeout and close wake-up, concurrent access, a
one-million-frame fixed-allocation stress run, WAV round trips and rejection, plus fake-device cleanup
for normal, user-stop, and device-error paths.

## RV1106 cross-build

The external SDK is never copied into RootLink. First generate the Echo-Mate Buildroot rootfs/sysroot
using that SDK's documented rootfs build. Then run from a Linux environment:

```sh
export RV1106_SDK_ROOT=/path/to/rv1106-sdk
sh embedded/rv1106/scripts/build-rv1106.sh
```

The toolchain configuration checks these inputs before compiling. It uses Buildroot's compiler wrapper
and asks that wrapper for the exact sysroot path, so SDK naming differences are not hard-coded:

- `sysdrv/source/buildroot/buildroot-2023.02.6/output/host/bin/arm-rockchip830-linux-uclibcgnueabihf-g++`
- the sysroot reported by that compiler (commonly `output/host/arm-buildroot-linux-uclibcgnueabihf/sysroot`)
- `usr/include/alsa/asoundlib.h` and target `libasound` in that sysroot

If this SDK variant uses a different output directory, update only the external SDK or pass a matching
SDK root; no local absolute SDK path is embedded in the project.

## Commands

```sh
rootlink-audio-smoke record --output test.wav --duration 5 \
  --capture-device default
rootlink-audio-smoke play --input test.wav --playback-device default
rootlink-audio-smoke loopback --duration 30 \
  --capture-device default --playback-device default --buffer-frames 100
```

执行 `rootlink-audio-smoke --help` 会显示该二进制编译时选择的 `audio API`。运行命令的
统计输出也包含 `audio_api=simulated` 或 `audio_api=alsa`，因此不会把仿真结果误认为
真机声卡结果。`simulated` 输入是按真实时间产生的确定性 200 Hz 测试波，输出按真实
20 ms 帧率消费但不会发出系统声音。

Omit loopback `--duration` to run until `Ctrl+C`. Both ALSA devices default to `default`; use an actual
`hw:X,Y` device on boards without an ALSA default. WAV input is intentionally limited to the fixed
Phase 1 format.

## Board acceptance

Copy `rootlink-audio-smoke` and `scripts/board-acceptance.sh` to the board, then run:

```sh
chmod +x rootlink-audio-smoke board-acceptance.sh
CAPTURE_DEVICE=default PLAYBACK_DEVICE=default LOOPBACK_SECONDS=30 \
  ./board-acceptance.sh ./rootlink-audio-smoke
```

The script lists available ALSA hardware when the utilities exist, records and checks a WAV, plays it,
and optionally runs timed loopback. The executable reports ring-buffer high-water/drop statistics,
ALSA recovery counts, and Linux RSS. The script deliberately does not modify mixer volume.

For the long-run acceptance, run `loopback --duration 600` and verify that RSS stabilizes after warmup,
the high-water mark never exceeds capacity, and temporary ALSA faults increase recovery counters rather
than terminating the process. Missing or busy devices must return a nonzero exit with a readable ALSA
error.
