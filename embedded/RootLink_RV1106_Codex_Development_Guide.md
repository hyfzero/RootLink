# RootLink RV1106 Voice Terminal — Codex Development Guide

> 当前代码手册：[用户手册](rv1106/USER_MANUAL.md)（API、配置、编译、运行）与 [开发手册](rv1106/DEVELOPER_MANUAL.md)（技术架构、协议、模块和扩展）。

> 统一构建入口：[CMake 双目标配置](rv1106/BUILDING.md)。修改 `rv1106/config/build.cmake` 的 `ROOTLINK_TARGET=ubuntu|rv1106`，分别生成 WSL/x86 SDL 程序与 ARM32/uClibc framebuffer 程序。

> 2026-09-06 实现更新：采用共享 Python `agent_core` 常驻子进程，C++ 负责 ASR/TTS/声卡，新增可选 LVGL 单主界面（SDL / framebuffer）。启动、配置、协议、数据恢复与部署以 [PYTHON_CORE.md](rv1106/PYTHON_CORE.md) 为准；已完成和待验收范围见 [VALIDATION.md](rv1106/VALIDATION.md)。下文保留原设计参考，旧的独立 C++ 人格流程只用于兼容后端。

> Windows 实操入口：[Windows 仿真、真实声卡与 LLM API 配置](rv1106/WINDOWS.md)。
> 当前 Windows 原生只支持离线模拟；电脑真实声卡可尝试 WSL2/WSLg 音频桥接，
> 先通过录音回放验收，再配置 `simulator + alsa + cloud`。原生 Windows 声卡后端尚未实现。

> Status: Design reference / implementation contract
> Target: RV1106 voice companion terminal integrated with RootLink Core
> Primary repositories:
> - RootLink: https://github.com/hyfzero/RootLink
> - Echo-Mate: https://github.com/No-Chicken/Echo-Mate
> - Echo-Mate demos: https://github.com/No-Chicken/Demo4Echo
>
> This document supplements the repository-level `AGENTS.md`.
> `AGENTS.md` remains the highest-priority local development guidance for Codex.
> Keep KISS / YAGNI / SOLID. Do not add speculative features.

---

## 1. Project goal

Build a physical voice terminal for RootLink on RV1106.

The terminal must:

1. Continuously listen for user speech without requiring a push-to-talk button.
2. Detect speech locally on RV1106.
3. Send detected speech to a public cloud ASR API.
4. Convert the ASR result into a RootLink chat turn.
5. Build the LLM context using the same RootLink character / memory / relationship semantics as the App.
6. Call a public cloud LLM API directly from the RV1106.
7. Send the LLM reply to a public cloud TTS API.
8. Play the returned audio through the RV1106 speaker.
9. Store local conversation events so they can later synchronize with the RootLink App.
10. Preserve future extensibility for RV1106 NPU vision input such as YOLO, without implementing vision in V1.

The project is **not** a rewrite of RootLink on RV1106.

The project is:

> **A RootLink Core runtime + voice I/O terminal whose heavy AI inference is provided by cloud APIs.**

---

## 2. Scope of V1

### Required

- RV1106 Linux userspace application.
- C/C++ implementation on RV1106.
- ALSA microphone capture.
- ALSA speaker playback.
- Local lightweight VAD.
- Pre-roll audio ring buffer.
- Automatic speech start / end detection.
- Cloud ASR.
- RootLink-compatible role/context loading.
- RootLink-compatible prompt construction.
- Cloud LLM call.
- Cloud TTS.
- Half-duplex conversation.
- Local conversation persistence.
- Basic RootLink App ↔ RV1106 synchronization interface.
- Provider abstraction for ASR / LLM / TTS.

### Explicitly out of scope for V1.0

Do **not** implement unless required to unblock V1.0:

- YOLO / camera pipeline.
- Full-duplex conversation.
- Barge-in / user interruption while TTS is playing.
- Acoustic Echo Cancellation (AEC).
- Local ASR model.
- Local LLM.
- Local neural TTS.
- Vector database.
- Complex memory retrieval.
- Cloud account / cloud synchronization backend.
- Custom AI server equivalent to Echo-Mate Server.
- FastText command classifier.
- LVGL UI.
- Multi-character simultaneous runtime.
- OTA.
- Production credential broker.

---

## 3. Reference project responsibilities

## 3.1 RootLink is the source of truth for Core semantics

RootLink currently provides the important companion semantics:

- `CompanionRole`
- `profile`
- `state`
- `memories`
- `speakingStyle`
- `config`
- sessions
- daily / monthly summaries
- relationship state
- prompt generation
- history token budgeting
- model-provider abstraction

Relevant current RootLink files include:

```text
lib/domain/models.dart
lib/domain/rootlink_agent_runtime.dart
lib/domain/repositories.dart
lib/data/file_role_repository.dart
lib/data/file_session_repository.dart
docs/architecture.md
AGENTS.md
```

The existing RootLink runtime already follows the conceptual flow:

```text
user input
  -> current role
  -> system prompt
  -> budgeted conversation history
  -> current user message
  -> provider
  -> streamed assistant response
```

The RV1106 implementation should preserve this semantic model.

### Important rule

Do not create a second, incompatible character model for the embedded device.

Bad:

```text
App:       affinity
RV1106:    friendship_score
```

Good:

```text
App:       affinity
RV1106:    affinity
```

The same rule applies to memories, state, relationship, role IDs, message roles, timestamps and schema versions.

---

## 3.2 Echo-Mate is the hardware / embedded reference

Echo-Mate is useful as an implementation reference for RV1106, especially:

- RV1106 build environment.
- ALSA / PortAudio audio path.
- C++ client structure.
- Opus integration.
- WebSocket client.
- JSON handling.
- ARM cross-compilation.
- RV1106 deployment.
- State-machine style voice interaction.
- Future YOLO / NPU integration.

The Echo-Mate board is documented as approximately:

```text
SoC:       RV1106
CPU:       single-core Cortex-A7
Memory:    256 MB DDR3L
Wi-Fi/BT:  RTL8723BS
Audio:     MIC + speaker interface
Storage:   SD / NAND
```

Relevant Echo-Mate / Demo4Echo paths:

```text
AIChat_demo/Client/
AIChat_demo/Client/Audio/
AIChat_demo/Client/WebSocket/
AIChat_demo/Client/README.md
AIChat_demo/Server/README.md
yolov5_demo/
DeskBot_demo/
```

### What to borrow from Echo-Mate

Borrow concepts and, where license-compatible and appropriate, implementation patterns for:

- audio capture / playback,
- audio queues,
- ring buffers,
- WebSocket lifecycle,
- ARM CMake toolchain setup,
- basic message/state architecture,
- reconnect logic,
- Opus if later required,
- future YOLO integration.

### What not to copy as architecture

Echo-Mate uses:

```text
RV1106 Client
    -> custom WebSocket protocol
    -> self-hosted Python Server
        -> FSMN-VAD
        -> SenseVoice
        -> FastText
        -> Qwen API
        -> CosyVoice API
```

This RootLink design intentionally avoids that server.

Do not recreate:

```text
Python AI server
Conda environment
local SenseVoice service
local FSMN-VAD server
FastText intent classifier
custom Client <-> AI Server gateway
```

unless a future requirement explicitly demands it.

---

## 4. Target architecture

```text
                         RootLink App
                    Windows / Android
                            |
                            |
                     RootLink Sync
                            |
                            v
+----------------------------------------------------------+
|                         RV1106                           |
|                                                          |
|  +---------------- RootLink Embedded Core ------------+  |
|  | Role                                                 | |
|  | User Profile                                         | |
|  | State                                                | |
|  | Relationship                                         | |
|  | Memory                                               | |
|  | Session                                              | |
|  | Prompt Builder                                       | |
|  | Sync metadata                                        | |
|  +------------------------------------------------------+ |
|                                                          |
| MIC                                                      |
|  |                                                       |
| ALSA capture                                             |
|  |                                                       |
| Ring buffer                                              |
|  |                                                       |
| Local VAD                                                |
|  |                                                       |
| Speech segment                                           |
+--|-------------------------------------------------------+
   |
   | HTTPS / WSS
   v
Cloud ASR
   |
   | text
   v
RootLink Prompt Builder
   |
   | role + user + state + memory + history + user input
   v
Cloud LLM
   |
   | text
   v
Cloud TTS
   |
   | PCM / WAV / supported stream
   v
+----------------------------------------------------------+
| RV1106                                                  |
|   Audio playback -> ALSA -> speaker                      |
+----------------------------------------------------------+
```

There is no mandatory self-hosted AI server.

---

## 5. Architectural principle: RootLink Core must remain equivalent

The App and embedded device may use different programming languages:

```text
RootLink App:     Dart / Flutter
RV1106:           C / C++
```

They do **not** need binary-identical implementations.

They **do** need:

- equivalent data schemas,
- equivalent state meanings,
- equivalent prompt semantics,
- compatible persistence formats,
- compatible sync protocol,
- deterministic schema migration rules.

Think of this as:

```text
                 RootLink Core Specification
                         /          \
                        /            \
                Dart implementation  C++ implementation
                      App                RV1106
```

Avoid forcing the Flutter runtime onto RV1106 merely to share source code.

---

## 6. RootLink Core model on RV1106

At minimum, embedded Core should model:

```text
CompanionRole
UserProfile
RoleState
RelationshipState
Memory
ChatMessage
Session
SpeakingStyle
ModelConfig
SyncMetadata
```

The embedded JSON representation should preserve unknown fields whenever reasonably possible, matching RootLink's compatibility philosophy.

### Character information

Current semantic categories:

```text
profile
  name
  age
  gender
  birthday
  personality_traits
  interests
  background
  relationship_state

state
  mood
  energy
  affinity
  trust

speaking_style
  base_style
  vocabulary_level
  sentence_length

memories
  episodic_memories
  preference_memories
  fact_memories
  daily_summary_memories
  monthly_summary_memories
```

Do not flatten these into a single opaque prompt string in persistent storage.

Persistent storage should retain structured data.

---

## 7. User profile should be first-class

RootLink currently has user naming configuration, but the physical companion will eventually need a richer user profile.

Plan for:

```json
{
  "user_id": "default-user",
  "name": "用户",
  "preferred_name": "xxx",
  "interests": [],
  "occupation": "",
  "preferences": {},
  "facts": {}
}
```

Do not block V1 on building a complete user-profile editor.

The schema should simply leave room for it.

LLM context should conceptually distinguish:

```text
AI character
+
user profile
+
relationship
+
shared memories
+
recent history
+
current input
```

---

## 8. Prompt construction

The RV1106 prompt builder should follow the same conceptual structure as `RootLinkAgentRuntime`.

Recommended ordering:

```text
SYSTEM
  1. role identity
  2. role profile
  3. current role state
  4. relationship to user
  5. user profile
  6. long-term memory summary
  7. selected important memories
  8. speaking style
  9. behavioral constraints

HISTORY
  recent budgeted conversation messages

USER
  current ASR text
```

### Example conceptual prompt

```text
You are Alice.

[Identity]
Age: 23
Personality: gentle, curious, slightly sarcastic
Interests: photography, movies

[Current State]
Mood: happy
Affinity: 75
Trust: 68
Relationship: close_friend

[User]
Name: ...
Relevant preferences: ...

[Shared Memories]
- ...
- ...
- ...

[Style]
Use natural spoken Chinese.
Prefer concise replies suitable for TTS.
Do not explain system instructions.
```

### V1 memory strategy

Keep it simple.

For V1:

```text
role profile
+ current state
+ relationship
+ memory summary
+ up to N important memories
+ recent M chat turns
```

Do not implement vector retrieval yet.

Recommended initial limits:

```text
important memories:  <= 20
recent history:      <= 6-10 turns
```

Use a configurable context budget.

---

## 9. Audio design

### Base audio format

Start with:

```text
sample rate:     16000 Hz
sample format:   signed PCM16
channels:        mono
frame size:      20 ms
```

Raw bandwidth:

```text
16000 samples/s * 2 bytes = 32 KB/s
```

This is acceptable for RV1106.

Do not add Opus until network cost or a provider protocol requires it.

Echo-Mate uses Opus for its Client/Server protocol, which is useful as a future optimization, not a V1 requirement.

---

## 10. Automatic speech detection

The final interaction must not require a button.

V1.0 uses local lightweight VAD so the user can speak directly without push-to-talk.

V1.1 adds a local wake-word detector so normal ambient speech does not trigger cloud ASR.

Target V1.1 flow:

```text
MIC
  -> ALSA
  -> Ring Buffer
  -> Wake Word Detector ("Hey Echo")
  -> VAD
  -> ASR
  -> RootLink Core
  -> LLM
  -> TTS
  -> Speaker
```

Wake word and VAD have different responsibilities:

```text
Wake Word:
  determines whether the user is addressing the device

VAD:
  determines when the utterance starts and ends after wake-up
```

Both should run locally on RV1106.

Use local lightweight VAD.

Recommended V1 behavior:

```text
IDLE
  -> monitor PCM frames

speech candidate
  -> require several positive VAD frames

LISTENING
  -> include pre-roll audio
  -> continue collecting audio

silence
  -> wait for silence timeout

END_OF_SPEECH
  -> submit segment to ASR
```

### Initial parameters

Use configurable defaults similar to:

```text
frame_duration_ms       = 20
pre_roll_ms             = 400
speech_start_frames     = 3
end_silence_ms          = 800
max_utterance_ms        = 30000
```

These are starting values, not hard-coded product requirements.

### Pre-roll ring buffer

Always retain recent audio before VAD trigger.

Purpose:

```text
without pre-roll:
"帮我查天气"
    ^
VAD detects here
result may become:
"我查天气"
```

With approximately 400 ms pre-roll, the beginning of speech is preserved.


---

## 10.1 Wake word design (V1.1)

V1.1 must support local keyword spotting such as:

```text
"Hey Echo"
```

Do not send continuous microphone audio to the cloud merely to detect wake-up.

Recommended pipeline:

```text
continuous PCM
   |
   v
WakeWordDetector
   |
   | detected
   v
AWAKE
   |
   v
VAD / speech capture
   |
   v
ASR
```

The wake-word engine should be isolated behind an interface such as:

```cpp
class WakeWordDetector {
public:
    virtual ~WakeWordDetector() = default;

    virtual bool process(
        const int16_t* pcm,
        size_t samples
    ) = 0;
};
```

The RootLink Core must not depend on wake-word implementation details.

Recommended module ownership:

```text
audio/
  capture/
  playback/
  ring_buffer/
  vad/
  wake_word/
```

### Wake word followed immediately by the command

The implementation must support natural phrases such as:

```text
"Hey Echo，今天天气怎么样？"
```

Do not require:

```text
"Hey Echo"
[pause]
"今天天气怎么样？"
```

Therefore the PCM ring buffer must continue across wake-word detection and preserve the post-wake audio needed by VAD/ASR.

Conceptually:

```text
PCM stream:
... Hey Echo 今天天气怎么样 ...
        ^
        wake detected
        |
        +---- preserve following PCM ---->
```

The wake-word detector must not discard the command portion that follows the keyword.

### V1.1 wake state machine

Recommended states:

```text
SLEEPING
  -> WAKE_CANDIDATE
  -> AWAKE
  -> LISTENING
  -> ASR_PENDING
  -> LLM_PENDING
  -> TTS_PENDING
  -> PLAYING
  -> SLEEPING
```

Typical transitions:

```text
SLEEPING
  -> WAKE_CANDIDATE    wake-word probability rises

WAKE_CANDIDATE
  -> SLEEPING          false trigger
  -> AWAKE             wake confirmed

AWAKE
  -> LISTENING         speech begins
  -> SLEEPING          wake timeout / no speech

LISTENING
  -> ASR_PENDING       end-of-speech

ASR_PENDING
  -> LLM_PENDING

LLM_PENDING
  -> TTS_PENDING

TTS_PENDING
  -> PLAYING

PLAYING
  -> SLEEPING
```

### Half-duplex limitation in V1.1

During TTS playback:

```text
WakeWordDetector = disabled
VAD trigger       = disabled
```

This prevents the device from detecting its own speaker output.

Therefore V1.1 does **not** support:

```text
assistant speaking
  +
user says "Hey Echo"
  ->
interrupt assistant
```

That behavior requires a later AEC + barge-in milestone.

Future full-duplex path:

```text
TTS reference
     |
     v
AEC <- MIC
 |
 v
Wake Word
 |
 v
VAD / ASR
```

Do not implement AEC merely to complete V1.1.

---

## 11. Half-duplex V1

V1 must be half-duplex.

While TTS is playing:

```text
speaker active
VAD trigger disabled
no new ASR request
```

State flow:

```text
IDLE
  -> LISTENING
  -> ASR
  -> THINKING
  -> TTS
  -> PLAYING
  -> IDLE
```

This avoids the device hearing its own TTS output.

Do not implement AEC or barge-in in V1.

Future full-duplex:

```text
TTS reference
    |
    v
AEC -> VAD -> ASR
```

is a separate milestone.

---

## 12. Cloud API strategy

Heavy models remain in the cloud.

V1 cloud responsibilities:

```text
ASR
LLM
TTS
```

RV1106 responsibilities:

```text
capture
VAD
context
networking
persistence
playback
sync
```

### Recommended initial provider direction

For a China-oriented prototype, use one provider family when possible to reduce integration complexity.

A practical initial choice is:

```text
ASR: Qwen / DashScope speech API
LLM: Qwen compatible chat API
TTS: Qwen TTS / CosyVoice cloud API
```

However, the code must not hard-code RootLink Core to one cloud vendor.

---

## 13. Provider interfaces

Define narrow provider abstractions.

Example conceptual C++ interfaces:

```cpp
class AsrProvider {
public:
    virtual ~AsrProvider() = default;
    virtual AsrResult transcribe(const AudioSegment& audio) = 0;
};

class LlmProvider {
public:
    virtual ~LlmProvider() = default;
    virtual ChatResult chat(const ChatRequest& request) = 0;
};

class TtsProvider {
public:
    virtual ~TtsProvider() = default;
    virtual TtsResult synthesize(const std::string& text) = 0;
};
```

RootLink Core must depend on abstractions, not vendor-specific code.

Vendor implementation examples:

```text
DashScopeAsrProvider
QwenChatProvider
CosyVoiceTtsProvider
```

Future:

```text
OpenAIChatProvider
DeepSeekChatProvider
OtherAsrProvider
OtherTtsProvider
```

---

## 14. Networking

V1 may use both:

```text
HTTPS
WSS
```

depending on provider requirements.

Expected embedded dependencies may include:

```text
ALSA
OpenSSL / mbedTLS
libcurl
websocketpp or libwebsockets
jsoncpp / cJSON / another lightweight JSON library
pthread
```

Do not add multiple libraries for the same responsibility without reason.

Prefer existing Echo-Mate-compatible components if they already compile reliably in the RV1106 Buildroot/sysroot.

### Required network behavior

Implement:

- DNS failures.
- connection timeout.
- TLS validation.
- API timeout.
- WebSocket reconnect.
- server disconnect.
- partial response handling.
- clean cancellation.
- readable error logs.

Never infinite-block the main state machine.

---

## 15. API credentials

### Prototype

For a personal prototype, storing API keys locally on RV1106 is acceptable.

Example:

```text
/etc/rootlink/secrets.json
```

Use restricted filesystem permissions.

Never commit real API keys to Git.

### Product

A production device must not rely on a long-lived shared secret stored in firmware or a readable filesystem.

Future product architecture may require:

```text
RV1106
  -> credential broker / short-lived token service
  -> cloud AI API
```

This is intentionally not a V1 requirement.

---

## 16. Local persistence

Do not reduce the RV1106 to a stateless microphone.

It should be a RootLink runtime node.

Recommended conceptual storage:

```text
/data/rootlink/
  config/
  roles/
    {role_id}/
      profile.json
      state.json
      speaking_style.json
      memories.json
      config.json
  sessions/
    current/
    archive/
  history/
    daily/
    summaries/
  sync/
    metadata.json
    pending_events.jsonl
```

The exact path may change to align with RootLink's existing storage contract.

### Persistence rule

Prefer:

```text
temporary file
-> validate
-> fsync if required
-> atomic replace
```

Do not directly overwrite important JSON in place.

RootLink already follows an atomic / validation-oriented persistence philosophy; preserve it on embedded where practical.

---

## 17. Conversation event model

Every voice turn should result in normal RootLink chat messages.

Example:

```json
{
  "id": "msg-...",
  "role": "user",
  "content": "今天工作有点累",
  "timestamp": 0
}
```

and:

```json
{
  "id": "msg-...",
  "role": "assistant",
  "content": "那今天早点休息。",
  "timestamp": 0
}
```

ASR-specific metadata may be stored as optional extra fields, for example:

```json
{
  "source": "rv1106_voice",
  "asr_confidence": 0.0
}
```

Unknown metadata should not break App compatibility.

---

## 18. RootLink App synchronization

Synchronization must be planned as **bidirectional**, not App -> device only.

Use cases:

```text
App chat
  -> new session / memory / relationship state
  -> sync to RV1106

RV1106 voice chat
  -> new session / memory / relationship state
  -> sync to App
```

Both endpoints represent the same companion identity.

---

## 19. Sync protocol V1

Keep synchronization simple.

First version can be LAN-based.

Potential transport:

```text
HTTP over local Wi-Fi
```

RV1106 may expose a small local endpoint.

Example:

```text
GET  /api/v1/status
GET  /api/v1/sync/state
POST /api/v1/sync/push
GET  /api/v1/sync/pull
```

Do not implement a full cloud sync system.

### Sync unit

Prefer domain objects / events instead of blindly copying the entire storage tree.

Suggested event envelope:

```json
{
  "protocol": "rootlink-sync",
  "version": 1,
  "event_id": "uuid",
  "device_id": "rv1106-001",
  "entity_type": "chat_message",
  "entity_id": "msg-001",
  "role_id": "alice",
  "updated_at": 0,
  "payload": {}
}
```

Potential entity types:

```text
role_profile
role_state
relationship
memory
chat_message
session_summary
settings_subset
```

---

## 20. Conflict strategy

Do not overengineer distributed synchronization in V1.

Use simple, documented rules.

Recommended:

### Append-only entities

For:

```text
chat_message
memory_event
```

use unique IDs and merge by ID.

### Mutable entities

For:

```text
role_state
profile
relationship
```

use:

```text
updated_at
revision
origin_device
```

Initial conflict strategy may be last-write-wins per entity if the semantics are documented.

Do not silently merge arbitrary JSON fields unless explicitly designed.

---

## 21. RootLink Core vs platform layer

Recommended separation:

```text
embedded/rv1106/
  core/
    model/
    prompt/
    memory/
    session/
    sync/

  audio/
    capture/
    playback/
    vad/
    ring_buffer/

  providers/
    asr/
    llm/
    tts/

  net/
    http/
    websocket/
    tls/

  platform/
    filesystem/
    clock/
    device_id/

  app/
    voice_state_machine/
    main/
```

The Core layer must not directly depend on ALSA.

Bad:

```text
PromptBuilder -> ALSA
```

Good:

```text
AudioCapture -> VoiceRuntime -> AgentCore -> LlmProvider
```

---

## 22. Recommended repository layout

Prefer keeping embedded development close to RootLink Core definitions.

Possible RootLink monorepo layout:

```text
RootLink/
  lib/                      # existing Flutter / Dart
  docs/
  test/

  embedded/
    rv1106/
      CMakeLists.txt
      toolchain/
      src/
      include/
      tests/
      README.md

  schemas/
    rootlink/
      companion_role.schema.json
      chat_message.schema.json
      sync_event.schema.json
      version.json
```

Important:

Do not vendor the complete Echo-Mate SDK or huge binary dependencies into RootLink without a specific reason.

Reference Echo-Mate externally or reuse small compatible modules according to licensing and project needs.

---

## 23. Shared schema strategy

A shared schema directory is strongly recommended.

Example:

```text
schemas/rootlink/
```

The Dart and C++ implementations should both be tested against the same fixture JSON.

Add golden fixtures such as:

```text
testdata/
  role_basic.json
  role_with_memories.json
  session_basic.json
  sync_events.json
```

Required invariant:

```text
JSON produced by App
    -> RV1106 parses correctly

JSON produced by RV1106
    -> App parses correctly
```

This matters more than source-code reuse.

---

## 24. Prompt compatibility tests

Create shared prompt fixtures.

Example input:

```text
role fixture
state fixture
memory fixture
history fixture
user input
```

Expected structural output should verify:

- role name included.
- role background included.
- state included.
- relationship included.
- selected memories included.
- history order preserved.
- current user input last.
- context budget respected.

Exact punctuation does not necessarily need byte-for-byte equality if both runtimes remain semantically equivalent.

If practical, keep a common prompt-template version identifier:

```text
prompt_schema_version = 1
```

---

## 25. Voice state machine

Use an explicit state machine.

Recommended states:

```text
BOOT
IDLE
SPEECH_CANDIDATE
LISTENING
ASR_PENDING
LLM_PENDING
TTS_PENDING
PLAYING
ERROR_RECOVERY
```

Example:

```text
BOOT
  -> IDLE

IDLE
  -> SPEECH_CANDIDATE

SPEECH_CANDIDATE
  -> IDLE          if false trigger
  -> LISTENING     if speech confirmed

LISTENING
  -> ASR_PENDING   on end-of-speech
  -> ERROR_RECOVERY on timeout/fault

ASR_PENDING
  -> LLM_PENDING

LLM_PENDING
  -> TTS_PENDING

TTS_PENDING
  -> PLAYING

PLAYING
  -> IDLE

ERROR_RECOVERY
  -> IDLE
```

State transitions should be logged.

---

## 26. Threading model

Do not create many unmanaged threads.

A reasonable first design:

```text
Thread 1: main/state machine
Thread 2: audio capture
Thread 3: network worker / provider call
Thread 4: audio playback, if necessary
```

Or use a small event-loop design if the selected networking library supports it cleanly.

All queues must have explicit ownership and bounded capacity.

Avoid hidden blocking waits.

---

## 27. Memory constraints

RV1106 has limited RAM.

Rules:

- do not load large AI models.
- use bounded audio buffers.
- use bounded chat history.
- use bounded memory selection.
- avoid keeping full TTS audio in RAM if streaming playback is available.
- avoid copying large byte buffers repeatedly.
- avoid unnecessary JSON DOM duplication.
- record high-water memory usage during development.

V1 should remain comfortably below the device's practical memory ceiling.

---

## 28. Error handling UX

The terminal needs recoverable voice behavior.

Examples:

```text
ASR failure
  -> discard turn or play short local/system error sound
  -> return to IDLE

LLM timeout
  -> return to IDLE

TTS failure
  -> optionally log/display text reply
  -> return to IDLE

Wi-Fi lost
  -> do not repeatedly spin at 100% CPU
  -> retry with backoff
```

Do not crash the voice process because a cloud API is temporarily unavailable.

---

## 29. Logging

Use structured log categories:

```text
AUDIO
VAD
ASR
CORE
PROMPT
LLM
TTS
SYNC
NET
STATE
STORAGE
```

Never log secrets.

During development, log timing:

```text
speech_duration
asr_latency
llm_first_token_latency
llm_total_latency
tts_first_audio_latency
tts_total_latency
end_to_end_latency
```

These metrics will matter more to conversational quality than raw CPU utilization.

---

## 30. Latency target

V1 is successful if it feels conversational, even if not fully realtime.

Measure:

```text
speech end
  -> ASR text
  -> LLM first response
  -> TTS first playable audio
```

Prefer streaming where it substantially reduces perceived latency, but do not introduce streaming complexity before the basic pipeline is stable.

Implementation order:

```text
correctness first
then streaming
then latency optimization
```

---

## 31. Development phases

## Phase 0 — Board readiness

Verify on RV1106:

```text
SSH
network
DNS
system time
TLS certificates
ALSA capture device
ALSA playback device
cross-compiler
CMake
filesystem write location
```

Exit criteria:

- record a WAV/PCM sample.
- copy or inspect it.
- play a known audio sample.
- perform HTTPS request to a test endpoint.

---

## Phase 1 — Audio core

Implement:

```text
AudioCapture
AudioPlayback
RingBuffer
```

Exit criteria:

- stable continuous 16 kHz mono PCM capture.
- bounded buffer.
- clean startup/shutdown.
- no memory growth.

---

## Phase 2 — Local automatic VAD (V1.0)

Implement:

```text
frame VAD
speech confirmation
400 ms pre-roll
800 ms end silence
30 s max utterance
```

Exit criteria:

- user can speak naturally without a button.
- beginning of first syllable is preserved.
- normal short pauses do not split one sentence excessively.

---

## Phase 2.1 — Wake word (V1.1)

Add a local keyword-spotting layer before VAD.

Required behavior:

```text
ambient speech
  -> no cloud request

"Hey Echo"
  -> wake

"Hey Echo，今天天气怎么样？"
  -> wake + preserve command audio
  -> VAD
  -> ASR
```

Exit criteria:

- wake word runs locally on RV1106.
- normal nearby speech does not routinely trigger ASR.
- wake-word + command in one sentence is supported.
- ring buffer preserves audio after wake detection.
- playback state disables wake-word triggering in V1.1.

---

## Phase 3 — Cloud ASR

Implement one provider.

Exit criteria:

```text
speech
-> VAD segment
-> ASR
-> UTF-8 text printed in terminal
```

No RootLink Core required yet beyond basic shell.

---

## Phase 4 — Embedded RootLink Core compatibility

Implement:

```text
CompanionRole loader
ChatMessage
Session
state
memory
prompt builder
storage
```

Use shared fixtures.

Exit criteria:

- RV1106 can read a role exported/generated by RootLink.
- prompt contains expected profile/state/memory/history semantics.
- no independent incompatible embedded character schema exists.

---

## Phase 5 — LLM

Pipeline:

```text
ASR text
-> RootLink prompt
-> LLM
-> assistant text
```

Exit criteria:

- character identity is preserved.
- current memories are reflected.
- recent history works.
- response is suitable for spoken output.

---

## Phase 6 — TTS and half-duplex voice loop

V1.0 pipeline:

```text
voice
-> VAD
-> ASR
-> RootLink Core
-> LLM
-> TTS
-> speaker
-> IDLE
```

V1.1 pipeline:

```text
"Hey Echo"
-> Wake Word
-> VAD
-> ASR
-> RootLink Core
-> LLM
-> TTS
-> speaker
-> SLEEPING
```

Exit criteria:

- fully automatic conversation.
- no push button.
- V1.0 supports direct speech activation.
- V1.1 supports local `Hey Echo` wake-up.
- wake-word + command in one phrase works.
- device does not recursively recognize its own TTS because wake-word/VAD triggers are disabled during playback.

V1.0 is the basic voice-loop milestone.

V1.1 is the intended desk-companion interaction milestone.

---

## Phase 7 — RootLink sync

Implement LAN sync.

Exit criteria:

- App can transfer active role/context to RV1106.
- RV1106 voice messages can be imported/synchronized back into App.
- App conversation and device conversation share the same role identity.
- duplicate message IDs do not create duplicate chat records.

---

## Phase 8 — Optimization

Only after V1.1 is stable:

- streaming ASR.
- streaming LLM.
- sentence-level streaming TTS.
- Opus.
- improved memory selection.
- better sync conflicts.

---

## Phase 9 — Vision

Future only:

```text
camera
-> RV1106 ISP / NPU
-> YOLO
-> scene context
-> RootLink Agent context
-> LLM
```

Vision output should be treated as an additional context source:

```json
{
  "vision_context": {
    "objects": [
      {"label": "cup", "count": 1},
      {"label": "laptop", "count": 1}
    ]
  }
}
```

Do not redesign RootLink Core around vision.

---

## 32. Echo-Mate reuse map

| Area | Echo-Mate reference | RootLink RV1106 decision |
|---|---|---|
| RV1106 board | use | same hardware class |
| Cross compile | reuse pattern | yes |
| ALSA / audio | reuse pattern | yes |
| AudioProcess architecture | reference | yes |
| Opus | reference | later unless required |
| websocketpp | reuse if suitable | yes |
| JSON protocol pattern | reference only | provider APIs + RootLink sync |
| Python Server | do not copy | no |
| FSMN-VAD server | do not copy | local lightweight VAD |
| SenseVoice server | do not copy | cloud ASR |
| FastText | do not copy | not needed |
| Qwen API | conceptually reuse | yes |
| CosyVoice API | conceptually reuse | yes |
| LVGL | ignore in V1 | no |
| YOLO demo | future reference | later |

---

## 33. RootLink integration map

| RootLink capability | Embedded treatment |
|---|---|
| `CompanionRole` | compatible C++ model |
| `profile` | preserve |
| `state` | preserve |
| `memories` | preserve |
| `speakingStyle` | preserve |
| `config` | preserve relevant fields |
| `ChatMessage` | compatible schema |
| session | local persistence + sync |
| prompt builder | semantic parity |
| token budget | simplified compatible budget |
| provider abstraction | mirrored concept |
| daily/monthly summaries | App may remain primary writer initially |
| relationship updates | preserve schema; exact ownership can evolve |
| character package | not required on RV1106 V1 |
| portrait/UI | not required on RV1106 V1 |

---

## 34. Ownership of memory and summaries

For V1, avoid implementing two competing memory engines.

Recommended ownership:

```text
RV1106:
  records raw conversation turns
  uses synchronized memory/context
  may update lightweight runtime state if required

RootLink App:
  remains primary manager for
    long-term memory extraction
    daily summaries
    monthly summaries
    advanced relationship maintenance
```

Later, if embedded independence becomes a requirement, memory-maintenance logic can be ported into the shared Core specification.

Do not duplicate advanced memory algorithms prematurely.

---

## 35. Codex implementation rules

When Codex works on this project:

1. Read repository `AGENTS.md` first.
2. Read this document before changing embedded architecture.
3. Inspect existing RootLink models before creating new schemas.
4. Inspect Echo-Mate client code before implementing duplicate RV1106 infrastructure.
5. Do not copy the Echo-Mate server architecture.
6. Prefer small vertical milestones.
7. Keep commits buildable.
8. Add tests for serialization and schema compatibility.
9. Do not add local AI models to RV1106 unless explicitly requested.
10. Do not change RootLink persistent schema casually.
11. Preserve unknown JSON fields where possible.
12. Do not store API keys in source code.
13. Do not couple RootLink Core to one AI provider.
14. Do not couple Core to ALSA / RV1106 platform APIs.
15. Do not implement future YOLO/AEC/wake-word features while working on V1.
16. Log state transitions and cloud latency.
17. Prefer bounded buffers and bounded queues.
18. Do not use busy loops for network/audio state waiting.
19. Keep recovery paths back to `IDLE`.
20. Before adding a dependency, confirm the RV1106 Buildroot/sysroot can support it.

---

## 36. Definition of Done for V1

V1 is complete only when all of the following are true:

### Audio

- microphone capture works on target hardware.
- playback works on target hardware.
- local VAD automatically starts/stops a user utterance.
- no button is needed.
- pre-roll prevents clipped first syllables.

### Wake word — required for V1.1

- local keyword spotting recognizes configured wake word such as `Hey Echo`.
- ordinary ambient speech does not normally initiate cloud ASR.
- `Hey Echo + command` in one phrase is supported.
- wake-word/VAD triggers are disabled while TTS is playing in half-duplex mode.

### ASR

- speech is sent to cloud ASR.
- valid UTF-8 text is returned.
- network errors recover without restarting device.

### RootLink Core

- embedded device loads RootLink-compatible role data.
- role profile is included in model context.
- relationship state is included.
- memory summary / important memories are included.
- recent conversation history is included.
- schema tests pass against shared fixtures.

### LLM

- device calls public LLM API directly.
- response follows selected RootLink role.
- provider can be changed without modifying Core.

### TTS

- LLM reply is converted to speech.
- audio plays automatically.
- device returns to listening state after playback.
- microphone does not trigger on its own playback in V1 half-duplex mode.

### Persistence

- both user and assistant text turns are persisted.
- sudden restart does not corrupt core JSON/session data.

### Sync

- RootLink App and RV1106 can exchange at least active role + conversation events.
- duplicate sync does not duplicate messages.

---

## 37. First implementation task for Codex

Do not begin by implementing the whole architecture.

First task:

```text
Create embedded/rv1106 skeleton
-> target builds with RV1106 toolchain
-> AudioCapture abstraction
-> ALSA implementation
-> AudioPlayback abstraction
-> ALSA implementation
-> bounded PCM ring buffer
-> command-line audio loopback / record-playback smoke test
```

Second task:

```text
Add local VAD
-> 20 ms PCM frames
-> pre-roll
-> speech start confirmation
-> end silence timeout
-> save each detected utterance to a test PCM/WAV file
```

Third task for the intended V1.1 interaction:

```text
Add WakeWordDetector abstraction
-> configure `Hey Echo`
-> run locally on continuous PCM
-> transition SLEEPING -> AWAKE
-> preserve post-wake command audio
-> feed command into existing VAD path
```

Cloud ASR may be integrated after VAD is verified; wake-word work may then be added before declaring the desk-companion V1.1 milestone complete.

---

## 38. Key design decisions summary

The following decisions are intentional and should not be casually reversed:

```text
[YES] RootLink Core semantics shared across App and RV1106
[YES] C++ embedded implementation
[YES] local lightweight VAD
[YES] public cloud ASR
[YES] public cloud LLM
[YES] public cloud TTS
[YES] direct RV1106 -> cloud API for prototype
[YES] automatic voice activation
[YES] local VAD in V1.0
[YES] local `Hey Echo` wake word in V1.1
[YES] wake-word + command in one phrase
[YES] half-duplex V1.x
[YES] bidirectional App/device sync planned from the start
[YES] Echo-Mate client used as RV1106 reference

[NO] self-hosted AI server in V1.x
[NO] local LLM
[NO] local general ASR
[NO] Echo-Mate Python Server clone
[NO] FastText command classifier
[NO] push-to-talk final UX
[NO] AEC in V1.x
[NO] barge-in during TTS in V1.x
[NO] YOLO in V1.x
[NO] independent embedded character schema
```

---

## 39. Source references

### RootLink

Repository:

```text
https://github.com/hyfzero/RootLink
```

Priority references:

```text
AGENTS.md
README.md
docs/architecture.md
lib/domain/models.dart
lib/domain/rootlink_agent_runtime.dart
lib/domain/repositories.dart
lib/data/file_role_repository.dart
lib/data/file_session_repository.dart
```

### Echo-Mate

Repository:

```text
https://github.com/No-Chicken/Echo-Mate
```

The `Demo` submodule points to:

```text
https://github.com/No-Chicken/Demo4Echo
```

Priority references:

```text
Demo4Echo/README.md
AIChat_demo/Client/README.md
AIChat_demo/Client/Audio/AudioProcess.h
AIChat_demo/Client/WebSocket/
AIChat_demo/Server/README.md
yolov5_demo/
```

Use Echo-Mate primarily as the embedded/RV1106 implementation reference.

Use RootLink as the product/Core semantic source of truth.

---

## 40. One-sentence architecture rule

> **RV1106 runs RootLink Core + local voice I/O; the cloud runs heavy AI inference; RootLink App and RV1106 remain two synchronized runtimes of the same companion.**
