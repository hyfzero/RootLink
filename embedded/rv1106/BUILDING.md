# 一份配置切换 Ubuntu / WSL 与 RV1106

构建配置为 [`config/build.cmake`](config/build.cmake)。与 DeskBot 的方式相同，先选择目标及工具链，再由 CMake 检测编译器。两个目标都在 Ubuntu / WSL 内构建，不需要先运行 `scripts/build.sh`。

只修改这一行即可选择目标：

```cmake
set(ROOTLINK_TARGET "ubuntu" CACHE STRING "ubuntu or rv1106" FORCE)
```

| 构建目标 | 编译器 / 产物 | 显示 | 音频 / 服务 |
| --- | --- | --- | --- |
| `ubuntu` | 本机 GCC，x86 Linux ELF；Windows 中通过 WSL 运行 | SDL | ALSA + curl 云服务 |
| `rv1106` | SDK Buildroot 工具链，ARM32 / uClibc ELF | framebuffer | ALSA + curl 云服务 |

同一文件还配置 LVGL 源码、SDK 和可信 CA 路径，默认使用本工作区的 DeskBot LVGL 与 RV1106 SDK。换目录时修改这些路径；WSL 内使用 Linux 路径，不能填写 `D:\...`。RV1106 需要 SDK 已生成包含 ALSA、curl、json-c、OpenSSL 的 Buildroot rootfs 和编译器 wrapper。

## Ubuntu / Windows WSL

先按 [WINDOWS.md](WINDOWS.md) 安装编译与声卡依赖；窗口额外需要 `libsdl2-dev`。配置目标保留 `ubuntu`，在 WSL 中执行：

```sh
cd /mnt/d/linux_test/AmaduesBot/RootLink/embedded/rv1106
cmake -S . -B build/ubuntu -C config/build.cmake
cmake --build build/ubuntu --parallel 4
ctest --test-dir build/ubuntu --output-on-failure
```

产物为 `build/ubuntu/rootlink-voice`，不是 Windows `.exe`。本机已配好 Python、声卡和密钥，可在 Windows 双击 `start-wsl-ui.cmd`，或在上述 WSL 目录执行：

```sh
sh scripts/run-wsl-ui.sh
```

启动脚本优先使用新产物，未生成时兼容原 `build/simulator-alsa-cloud-sdl`。它读取本机 `build/windows-cloud/python-ui.conf`，启动真实麦克风及云对话。其他机器需依照 [PYTHON_CORE.md](PYTHON_CORE.md) 准备 `.venv`、角色数据与运行配置，并设置 `UI_BACKEND=sdl`。

## RV1106

把同一配置的 `ROOTLINK_TARGET` 改为 `rv1106`，再执行：

```sh
cmake -S . -B build/rv1106 -C config/build.cmake
cmake --build build/rv1106 --parallel 4
file build/rv1106/rootlink-voice
```

产物为 `build/rv1106/rootlink-voice`。构建自动选择 `cmake/rv1106-toolchain.cmake` 和 framebuffer，不链接 SDL，不运行主机测试。板端运行配置使用 `TARGET=rv1106`、`UI_BACKEND=fbdev`，显示设备默认 `/dev/fb0`；部署 Python 核心、动态库与证书按 [PYTHON_CORE.md](PYTHON_CORE.md) 操作，打包时传入本次生成的程序路径。交叉编译通过不等于实板验收通过。

两个目标必须使用不同构建目录。误用旧目录时 CMake 会拒绝切换，以免混入另一平台的编译器缓存；改用上述对应目录即可。修改构建配置后重新执行含 `-C config/build.cmake` 的配置命令。

构建配置只负责编译，`PERSONA_BACKEND`、模型、密钥、角色数据、声卡设备和窗口尺寸仍由运行时 `.conf` / 密钥文件设置。不会把密钥编进程序。旧 `scripts/build.sh` 和不使用此配置的 CMake 调用仍保留，离线 mock 回归可以继续使用原入口。
