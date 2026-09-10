# RV1106 部署包使用说明

本包面向本工作区 DeskBot 使用的 `Amadues_chatRobo/SDK/rv1106-sdk`，ARM32 hard-float / uClibc。包含 C++ 语音界面、Python 人格核心、红莉栖角色种子、日语翻译与 CosyVoice 配置。ASR、人格 LLM、翻译和 TTS 需要联网。

## 安装

归档是匹配 SDK 的 rootfs overlay。推荐合入该 SDK 的固件根文件系统；也可在确认板端使用相同 SDK/rootfs 后安装。包内含动态加载器、libc 和 OpenSSL，不能覆盖到不匹配的系统。已有安装应先备份 `/etc/rootlink` 和 `/data/rootlink`；退出正在运行的 DeskBot/RootLink，避免争用屏幕和声卡。

将 `rootlink-rv1106-20260910-r2.tar.gz` 复制到板端 `/tmp` 后，以 root 执行：

```sh
# BusyBox tar 不一定支持 GNU tar 的 -z；明确使用 gzip 解压。
gzip -dc /tmp/rootlink-rv1106-20260910-r2.tar.gz | tar -xf - -C /
mkdir -p /data/rootlink/python-data /data/rootlink/sessions
if [ ! -f /etc/rootlink/rootlink-secrets.env ]; then
  cp /etc/rootlink/rootlink-secrets.env.example /etc/rootlink/rootlink-secrets.env
fi
chmod 600 /etc/rootlink/rootlink-secrets.env
```

编辑 `/etc/rootlink/rootlink-secrets.env`，填写自己的 `DEEPSEEK_API_KEY` 和 `DASHSCOPE_API_KEY`。包内不含真实密钥，不需要填写其他供应商。预设音色 ID 必须属于该 DashScope 账号且处于可用状态；换账号后修改 `/etc/rootlink/python.conf` 的 `TTS_VOICE`。

## 板端配置

主要配置在 `/etc/rootlink/python.conf`，供应商端点配置在 `/data/rootlink/config/models.json`。

- 默认 DeepSeek `deepseek-v4-flash` 思考，独立翻译为日语，再使用 `cosyvoice-v3.5-plus` 合成。
- framebuffer `/dev/fb0`、触摸 `/dev/input/event0` 参考 DeskBot。屏幕需提供 RGB565 或 32 位 RGB 真彩 framebuffer。触摸重置依赖 `BTN_TOUCH` 事件。
- 录音、播放默认 ALSA `default`。若不能打开，使用 `arecord -l`、`aplay -l` 检查实际设备并修改 `CAPTURE_DEVICE`、`PLAYBACK_DEVICE`；不能填写 WSL 的 `pulse`。设备须支持 16 kHz、单声道、S16_LE；必要时使用已安装 ALSA 配置提供转换设备。麦克风和扬声器还需板端 mixer 路由正确。
- 角色种子在 `/opt/rootlink/role-seed`，包含 `persona/memories.json`。首次启动复制到 `/data/rootlink/python-data/default`，之后从运行数据恢复。种子更新不会覆盖已有记忆；本包不携带桌面私人会话。
- 中文按日语音频句段显示，每页最多三行。`UI_PAGE_HOLD_MS=2000` 控制翻页停留；点击屏幕重置当前操作。
- 保证 `/data/rootlink` 可写、DNS/网络可用且系统时间正确，HTTPS 依赖证书和正确时间。

## 启动与检查

```sh
/usr/bin/python3.11 /opt/rootlink/check-python-target.py
/usr/bin/rootlink-voice doctor --config /etc/rootlink/python.conf
/usr/bin/rootlink-voice voice --config /etc/rootlink/python.conf
```

第一条验证 ARM Python、共享核心与 TLS 导入；第二条检查配置、Python 握手和声卡，不带 `--probe-cloud` 不调用云模型；第三条开始真实录音及云对话。Ctrl+C 退出。包内不自动启用开机服务。

## 包内容与验证边界

- `/usr/bin/rootlink-voice`、`/usr/bin/python3.11`、`/usr/lib/python3.11`：ARM 程序、Python 标准库、核心和轻量依赖。
- `/lib`、`/usr/lib`：由 SDK 提取的 ELF 动态依赖；`/usr/share/alsa`：声卡配置。
- `/opt/rootlink`：worker、导入检查、角色和许可；LVGL 与中文字形已编入程序，无需复制 DeskBot 源码或字体引擎。
- `/etc/rootlink`：运行配置与空密钥模板；`/etc/ssl/certs`：CA 证书；`/data/rootlink/config/models.json`：模型端点。
- `manifest.json`：文件哈希和构建来源。外部 SHA256 文件可用于确认传输完整性。

DeskBot 实板运行证明参考 SDK/驱动链路已使用过，不代表新增 Python 人格和分段音频链路已完成板端验收。ARM ELF 检查及 QEMU 导入不能替代实际屏幕、声卡、内存峰值、启动耗时与连续对话测试。完整验证记录见项目 `VALIDATION.md`。
