# 牧濑红莉栖 · Amadeus 人格包

版本：2026-09-07。角色 ID：`kurisu_amadeus`。这是依据官方公开资料与指定百科制作的跨终端非官方角色档案及人格适配，以《STEINS;GATE 0》初始 Amadeus 为参照。详细考据、人物关系、作品差异、原创对话示例和未核验事项见 [research/DOSSIER.md](research/DOSSIER.md)。含剧情信息。

这不是完整原作数据库，也不是官方产品或声优复刻。不会把未发生的用户互动、其他世界线剧情写成共同记忆。没有收录原作剧本、音频或人物图片。

## App 直接导入

1. 使用同目录上一级的 `kurisu_amadeus.amadues` 文件，不要选本文件或单个 JSON。
2. 在 RootLink App 打开「设置 → 本地数据 → 导入角色包」，选择该文件。
3. 返回角色列表选择「牧濑红莉栖·Amadeus」，在 App 的模型设置中配置自己的 LLM 地址、模型与 API 密钥，即可文字交流。

包使用 App 已支持的 `amadues.character-package` v1 格式，带文件大小和 SHA-256 校验。角色初始关系中立，预置 30 条带来源和作品范围的角色记忆（6 条情景、3 条偏好、21 条事实）；日月摘要为空，不带聊天记录、账号或密钥。再次导入同一 ID 可能覆盖已使用的角色，请先导出备份。

`research`、本说明及 `voice.json` 会随导入保留；App 当前不会自动检索考据文档，也没有接通 TTS 播放。`voice.json` 是语音配置说明，**导入成功不代表 App 自动获得女声**。Flutter App 与嵌入式 Python 使用兼容的角色数据，各自的运行逻辑并不因此完全相同。

## WSL / x86 Ubuntu 启用

已有带 SDL、ALSA 和云服务的 Ubuntu 构建时，在 WSL 执行：

```sh
cd /mnt/d/linux_test/AmaduesBot/RootLink/embedded/rv1106
./build/ubuntu/rootlink-voice voice --config config/windows-kurisu.conf.example
```

不必经过启动脚本。首次构建步骤见 `embedded/rv1106/USER_MANUAL.md`；该配置需要 WSLg 显示和 PulseAudio 声卡，以及项目 `.venv` 中的 Python 核心依赖。

密钥仍填写在 `embedded/rv1106/config/rootlink-secrets.env`：

```dotenv
DASHSCOPE_API_KEY=填写你自己的密钥
```

示例的 Qwen LLM、DashScope ASR、CosyVoice TTS 共用该密钥；账户需要对应模型与北京地域的权限。LLM 地址等仍由 `config/models.json` 配置。包中不含任何密钥。该配置的关键项为：

```dotenv
ROLE_DIR=../../characters/kurisu_amadeus
PERSONA_BACKEND=python
PYTHON_DATA_DIR=build/windows-cloud/kurisu-python-data
TTS_PROVIDER=dashscope
TTS_MODEL=cosyvoice-v3-flash
TTS_VOICE=longxiaochun_v3
TTS_SAMPLE_RATE=16000
TTS_BASE_URL=https://dashscope.aliyuncs.com/api/v1
```

`longxiaochun_v3` 是官方列出的知性女声，支持中文普通话和英文，是气质方向的选择，不是今井麻美或红莉栖的原声。官方列表不标注其支持 Instruct，勿自行添加情绪指令并假设会生效。选型依据与来源见考据文档；还需要你在实际声卡试听确认听感。

Python **仅首次**把种子人格复制到独立数据目录，此后恢复目录中的状态和历史。这里采用新目录，避免混入原示例的历史。以后更新种子配置不会覆盖旧运行数据：要体验全新种子，请配置另一个尚未使用的 `PYTHON_DATA_DIR`；保留旧目录以便恢复。App 和嵌入式导入后各自保存数据，不会自动实时同步。

## RV1106 部署

把整个 `kurisu_amadeus` 文件夹复制到板端角色目录；运行配置将 `ROLE_DIR` 指向它，`PYTHON_DATA_DIR` 指向另一处可写持久目录。保留板端 Python 解释器、核心入口、ALSA 设备和 `UI_BACKEND=fbdev` 配置，仅替换人格路径与上述 TTS 项。不要把 WSL 模板中的 `.venv`、PulseAudio 或 SDL 配置原样用于板端。

本次仅新增数据、配置和测试，无须因更换人格重新编译 C++。板端显示、网络、TLS、内存及真实语音效果仍需实机验证。

## 文件与维护

- `persona/profile.json`：运行时身份、性格、记忆边界和表达规则。
- `persona/state.json`、`memories.json`：中立起点与有来源的预置角色记忆。
- `persona/speaking_style.json`：少量中文表达偏好，不是原作逐字口癖。
- `config.json`：日常三句的回复目标；沿用默认关闭的 Prompt 分区预算，避免长身份说明被截断。
- `ui.json`：App 列表简介；`voice.json`：语音选型元数据。
- `research/canon_records.json`：47 条结构化档案，包含来源索引、适用作品及是否注入运行记忆。
- `research/CHARACTER_ARCHIVE.md`：助手到 Amadeus 的档案导航、时间线与版本差异。
- `research/DOSSIER.md`：供人阅读的带来源资料，不自动作为亲历记忆注入。

编辑源目录后，从 RootLink 根目录使用 `.venv/bin/python scripts/build_kurisu_package.py` 重新生成包。验证命令：

```sh
flutter test test/kurisu_character_package_test.dart
.venv/bin/python embedded/rv1106/tests/test_kurisu_character.py
```

这两项检查实际导入/再导出、资料完整性、Prompt 身份边界和 Python 重启恢复；不调用付费 API，不代表模型每次都遵循设定或已经通过真实语音试听。

## 本次验证记录（2026-09-07）

| 检查 | 结果 |
|---|---|
| Flutter 实际导入、构建 Prompt、再导出并重新导入；逐文件比较源目录 | 通过 |
| 既有角色包正常导入、路径穿越拒绝、损坏覆盖保留旧角色 | 通过；与上项合计 4/4 |
| WSL `.venv` 中实际 `create_manager` 加载完整身份、独立运行数据、重启恢复、种子未改动 | 通过，1/1 |
| 现有 Ubuntu 二进制 `doctor --config config/windows-kurisu.conf.example` | `doctor=ok`；Python 启动、TLS 环境、PulseAudio 采集/播放初始化通过 |
| 云 LLM 行为、女声试听、完整录音到回答播放、RV1106 实板 | 本次未验证 |

`doctor` 未启用 `--probe-cloud`，因此不会据此宣称云模型已调用成功。WSL 的密钥文件权限检查提示现有文件权限较宽，未输出密钥，也未把它纳入角色包。

## 档案与运行记忆

这份档案可独立阅读，不以嵌入式硬件为前提。`canon_records.json` 保存全部 47 条本次收集的记录；`persona/memories.json` 将其中 30 条转换为 App 与 Python 都能读取的格式。情景条目明确标注“非本机亲历”，角色偏好明确区别于用户偏好。时间戳 0 表示未设定剧情精确时刻，不代表故事发生在 1970 年。日月摘要留给实际会话生成。

App 当前最多向 Prompt 取前 30 条记忆；Python 还会按预算筛选，因此收录不等于每轮都加载全部资料。背景中始终保留身份与记忆边界，完整考据则随角色包保存。新增动态记忆后，部分预置条目可能不进入当轮 Prompt。本次没有增加自动检索资料库功能。

百科转述的署名、来源和许可说明见档案导航。未获得正文的游戏分支、漫画、广播剧和资料集不冒充已全量核验。
