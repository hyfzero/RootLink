# 日语翻译与 CosyVoice 语音配置

更新：2026-09-08。目标链路：录音 → ASR → Python 人格核心生成原始回答 → DeepSeek 翻译成日语 → CosyVoice 合成 WAV → 声卡播放。

## 需要填写什么

密钥继续写入 `config/rootlink-secrets.env`，不写进代码或命令行：

```dotenv
DASHSCOPE_API_KEY=你的北京地域百炼密钥
DEEPSEEK_API_KEY=你的DeepSeek密钥
```

`DASHSCOPE_API_KEY` 用于 ASR、创建音色和 TTS；`DEEPSEEK_API_KEY` 用于人格对话及独立翻译。无界面每轮新增一次翻译调用；界面同步模式按句段分别翻译和合成，会增加请求次数和模型用量。播放当前段时提前合成下一段，以减少句间等待，但不保证无缝衔接；分段也可能影响语气和上下文连贯性。翻译复用 `LLM_PROVIDER / LLM_MODEL / LLM_BASE_URL` 及其认证配置。

在当前运行配置 `build/windows-cloud/python-ui.conf` 中更新以下部分即可。**先获得真实音色 ID，再替换模型和音色；不要把占位符当作 ID。**

```ini
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-v4-flash
LLM_BASE_URL=https://api.deepseek.com
TTS_PROVIDER=dashscope
TTS_MODEL=cosyvoice-v3.5-plus
TTS_VOICE=这里替换为创建成功的完整voice_id
TTS_SAMPLE_RATE=16000
TTS_BASE_URL=https://dashscope.aliyuncs.com/api/v1
TTS_TRANSLATE_TO=ja
TTS_TRANSLATION_TIMEOUT_MS=60000
TTS_TIMEOUT_MS=60000
```

`TTS_TRANSLATE_TO=none` 关闭翻译，也是旧配置缺省行为。翻译超时单独计算，之后才开始 TTS 合成超时；总等待还包括人格调用与音频下载。整个翻译和合成过程显示 `....`，实际播放才显示 `！`。

CosyVoice v3.5-plus 只支持北京地域的复刻/设计音色，没有系统音色；`longanyang`、`longxiaochun_v3` 不能直接沿用。合成模型必须与创建音色时的 `target_model` 相同。日语选择声音复刻；当前文档列出的声音设计语言范围为中、英文。[模型与语言说明](https://help.aliyun.com/zh/model-studio/tts-model)、[实时合成说明](https://help.aliyun.com/zh/model-studio/realtime-tts-user-guide)

## 一次性创建日语音色

已有匹配模型且状态为 `OK` 的 `voice_id` 时可跳过本节。音色 ID 是你在该服务创建的资源标识，不是 Hugging Face 模型名或本地 `.pth` 文件。

准备自己选定、可用于复刻的参考音频及公网 HTTPS 地址。优先干净的日语单人说话，无背景音乐、重叠对白；不要直接使用示例中的官方样本 URL，那会复刻示例说话者。参考音频质量影响音色和韵律，不能仅靠“红莉栖”名字得到原角色声音。采样和时长要求以[声音复刻指南](https://help.aliyun.com/zh/model-studio/voice-cloning-user-guide)为准。

在 WSL 中执行（安装仅用于电脑上的音色管理工具，板端正常播报不依赖 DashScope Python SDK）：

```sh
cd /mnt/d/linux_test/AmaduesBot/RootLink/embedded/rv1106
../../.venv/bin/python -m pip install -r requirements-voice-tools.txt
../../.venv/bin/python scripts/enroll-cosyvoice.py \
  --audio-url 'https://你的音频地址/sample.wav' \
  --prefix amadeus \
  --secrets-file config/rootlink-secrets.env
```

创建结果立即记录在 `build/windows-cloud/cosyvoice-voice.json`，之后轮询状态。完成时输出 `TTS_MODEL` 和 `TTS_VOICE` 配置行，复制进运行配置即可。创建仅执行一次；中断后使用已经记录的 ID 查询，不要重新创建：

```sh
../../.venv/bin/python scripts/enroll-cosyvoice.py \
  --voice-id '这里替换为完整voice_id' \
  --secrets-file config/rootlink-secrets.env
```

工具不会自动上传本地音频，也不会自动生成或播放测试语音。`UNDEPLOYED` 为失败，等待超时返回错误；不会把它当成成功音色。密钥只从非空环境变量或密钥文件读取，环境变量优先，不输出服务端异常正文。

底层使用你提供的 `VoiceEnrollmentService.create_voice / query_voice` 方法，创建时带 `language_hints=["ja"]`。官方 SDK 文档建议使用 `https://你的WorkspaceId.cn-beijing.maas.aliyuncs.com/api/v1`，并明确旧 `dashscope.aliyuncs.com` 域名仍可用；工具可通过 `--base-url` 设置，运行程序对应修改 `TTS_BASE_URL`。[SDK 参考](https://help.aliyun.com/zh/model-studio/voice-clone-python-sdk)

## 编译和直接运行

已有 Ubuntu 构建目录时：

```sh
cd /mnt/d/linux_test/AmaduesBot/RootLink/embedded/rv1106
cmake --build build/ubuntu --parallel 4
./build/ubuntu/rootlink-voice voice \
  --config build/windows-cloud/python-ui.conf
```

首次构建先执行 `cmake -S . -B build/ubuntu -C config/build.cmake`，依赖和配置见[用户手册](USER_MANUAL.md)。不必通过启动脚本运行。

也可复制完整的[日语配置模板](config/windows-kurisu-japanese.conf.example)到 `build/windows-cloud/japanese-ui.conf`，填写 `TTS_VOICE` 后运行：

```sh
./build/ubuntu/rootlink-voice voice \
  --config build/windows-cloud/japanese-ui.conf
```

模板复用当前 Kurisu 人格数据目录 `build/windows-cloud/kurisu-canon-python-data`；若你的原配置不同，沿用自己的 `PYTHON_DATA_DIR`，不要同时启动两个进程写同一目录。

本机 `build/windows-cloud/python-ui.conf` 已按用户选择启用 `cosyvoice-v3.5-plus` 和日语翻译，音色 ID 为 `cosyvoice-v3.5-plus-bailian-ab03a1beb9264dd9aa221cf3c5e9c760`，此前只读查询状态为 `OK`。此 ID 属于当前账户；其他用户应创建自己的音色。可提交的模板保留占位符，不自动覆盖其他账户配置。

## 与示例 Python 合成的关系

示例 `SpeechSynthesizer.call` 使用 SDK 的 WebSocket 合成。板端程序仍使用 C++ 的官方 CosyVoice HTTP 合成接口 `/services/audio/tts/SpeechSynthesizer`，传入同一模型与音色 ID，请求日语文本、16 kHz WAV，再 HTTPS 下载播放。没有在每次播报时启动 Python SDK，也没有在板端运行 CosyVoice 模型。v3.5-plus 在官方 HTTP 支持模型中。[HTTP 合成参考](https://help.aliyun.com/zh/model-studio/non-realtime-tts-user-guide)

所以这是一种“本地终端 + 云端翻译/合成”方案，WSL 与 RV1106 可共用；不等同于完全离线 TTS。角色文字、历史和记忆仍由唯一 Python 核心维护。译文不写入人格历史；翻译失败不会改为播报原文，也不重新执行人格消息。App 角色导入格式保持原样，当前 App 文字界面不会因此自动新增语音功能。

## 超时与中文输出排查

终端中的人格回答是原始文字，通常为中文；它先写入人格会话，随后才进行独立日语翻译。`tts_text_ja=` 显示实际送往 CosyVoice 的完整日语译文。只有出现 `state=PLAYING` 才表示开始播放；在 `SYNTHESIZING` 报错的轮次会跳过播报，不回退为中文，也不重放人格请求。语音失败前已保存的原始回答仍会保留在历史中。

新版日志区分翻译、CosyVoice 合成请求和音频下载，并记录各阶段耗时。发生网络错误时额外记录 DNS、连接、TLS、首字节、总耗时和已接收字节数，不记录密钥或签名下载地址。这些网络时间是从该请求开始累计的时间点；值为零也可能表示该阶段尚未完成，不能单凭零值断言该阶段没有耗时。

`CONNECT_TIMEOUT_MS` 限制连接阶段；`TTS_TRANSLATION_TIMEOUT_MS` 只限制翻译；`TTS_TIMEOUT_MS` 分别限制合成请求和音频下载，并非整轮总预算。先看失败阶段和耗时再调整相应参数。延长合成预算不能解决连接阶段就失败的问题。环境变量会覆盖配置文件；启动日志打印实际生效的翻译开关和超时预算。

超时后正常路径是重新进入 `LISTENING`；屏幕点击可取消当前处理并重置。若仍持续失败，保留包含失败阶段及耗时的错误行用于定位，不需要发送密钥文件。

## 验证范围

自动化验证和构建结果记录在 [VALIDATION.md](VALIDATION.md)。本机已使用所选 voice_id，通过正式 C++ `synthesize` 入口完成固定中文文本 → DeepSeek 翻译 → CosyVoice 合成，生成 `build/windows-cloud/kurisu-japanese-check.wav`（16 kHz、单声道、PCM16，6.93 秒），并通过 `aplay -D pulse` 播放一次。本次不涉及真实录音或人格历史更新；日语发音的主观评价、角色相似度、完整连续对话及实板效果仍需人工验收。
