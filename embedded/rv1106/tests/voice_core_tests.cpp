#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

#include "rootlink/audio/audio_capture.h"
#include "rootlink/audio/audio_playback.h"
#include "rootlink/voice/codec.h"
#include "rootlink/voice/json_value.h"
#include "rootlink/voice/providers.h"
#include "rootlink/voice/role.h"
#include "rootlink/voice/vad.h"
#include "rootlink/voice/voice_runtime.h"

using namespace std::chrono_literals;
using rootlink::audio::AudioDeviceStats;
using rootlink::audio::AudioError;
using rootlink::audio::Status;

namespace {

std::atomic<int> failures{0};
#define CHECK(condition) do { if (!(condition)) { \
  std::cerr << __FILE__ << ':' << __LINE__ << " CHECK failed: " #condition << '\n'; ++failures; \
} } while (false)

std::vector<std::int16_t> frame(std::int16_t value) {
  return std::vector<std::int16_t>(rootlink::audio::kSamplesPerFrame, value);
}

void testJsonCodecAndSse() {
  const std::string source = R"({"name":"小林","items":[1,true,null],"line":"a\nb"})";
  auto parsed = rootlink::voice::JsonValue::parse(source);
  CHECK(parsed.ok());
  CHECK(parsed.value().find("name")->stringOr() == "小林");
  CHECK(rootlink::voice::JsonValue::parse(parsed.value().dump()).ok());
  CHECK(!rootlink::voice::JsonValue::parse("{bad").ok());
  CHECK(rootlink::voice::JsonValue::parse(R"("\ud83d\ude00")").value().stringOr() == "😀");
  CHECK(!rootlink::voice::JsonValue::parse(std::string(100, '[') + "0" + std::string(100, ']')).ok());

  const std::vector<std::uint8_t> raw{'M', 'a', 'n'};
  CHECK(rootlink::voice::base64Encode(raw) == "TWFu");
  const auto wav = rootlink::voice::pcm16ToWav(frame(123));
  auto decoded = rootlink::voice::wavToPcm16(wav);
  CHECK(decoded.ok() && decoded.value().size() == 320 && decoded.value().front() == 123);
  auto truncated = wav;
  truncated.pop_back();
  CHECK(!rootlink::voice::wavToPcm16(truncated).ok());
  auto streaming = wav;
  const std::uint32_t lengths[] = {0x7fffffbfU, 0x7fffff9bU};
  for (unsigned i = 0; i < 4; ++i) {
    streaming[4 + i] = static_cast<std::uint8_t>(lengths[0] >> (8 * i));
    streaming[40 + i] = static_cast<std::uint8_t>(lengths[1] >> (8 * i));
  }
  CHECK(!rootlink::voice::wavToPcm16(streaming).ok());
  CHECK(rootlink::voice::wavToPcm16(streaming, true).ok());
  streaming.pop_back();
  CHECK(!rootlink::voice::wavToPcm16(streaming, true).ok());

  rootlink::voice::SseParser sse;
  std::vector<rootlink::voice::SseEvent> events;
  const std::string stream = "data: {\"x\":1}\r\n\r\ndata: [DONE]\n\n";
  for (const char c : stream) {
    auto next = sse.feed(&c, 1);
    events.insert(events.end(), next.begin(), next.end());
  }
  CHECK(events.size() == 2);
  CHECK(events[0].data == "{\"x\":1}");
  CHECK(events[1].data == "[DONE]");
}

void testVadSegmentation() {
  rootlink::voice::VadConfig config;
  rootlink::voice::AdaptiveEnergyVad vad(config);
  rootlink::voice::UtteranceSegmenter segmenter(config);
  const std::size_t reserved = segmenter.reservedSamples();
  rootlink::voice::SegmentEvent last = rootlink::voice::SegmentEvent::kNone;
  auto feed = [&](std::int16_t value) {
    const auto samples = frame(value);
    auto analysis = vad.analyze(samples);
    CHECK(analysis.ok());
    auto event = segmenter.pushFrame(samples, analysis.value());
    CHECK(event.ok());
    if (event.ok()) last = event.value();
  };
  for (int i = 0; i < 25; ++i) feed(0);
  for (int i = 0; i < 20; ++i) feed(1200);
  for (int i = 0; i < 40; ++i) feed(0);
  CHECK(last == rootlink::voice::SegmentEvent::kCompleted);
  CHECK(segmenter.utterance().size() == 80 * rootlink::audio::kSamplesPerFrame);
  CHECK(segmenter.utterance().front() == 0);
  CHECK(segmenter.stats().starts == 1 && segmenter.stats().completed == 1);
  segmenter.reset();
  CHECK(segmenter.reservedSamples() == reserved);

  last = rootlink::voice::SegmentEvent::kNone;
  for (int i = 0; i < 3; ++i) feed(1200);
  for (int i = 0; i < 40; ++i) feed(0);
  CHECK(last == rootlink::voice::SegmentEvent::kRejectedTooShort);
}

void testVadBoundariesAndStress() {
  using namespace rootlink::voice;
  VadConfig config;
  AdaptiveEnergyVad vad(config);
  const auto quiet = frame(100), speech = frame(1400), silence = frame(0);
  for (int i = 0; i < 1000; ++i) CHECK(!vad.analyze(quiet).value().speech);
  const double baseline = vad.analyze(quiet).value().noise_floor;
  CHECK(vad.analyze(speech).value().noise_floor == baseline);
  CHECK(vad.analyze(frame(-32768)).value().rms == 32768);
  vad.reset();
  CHECK(!vad.analyze(silence).value().speech);
  CHECK(!vad.analyze({1}).ok());
  // 启动和重置后第一帧恰好是弱语音，不应把它吸收为底噪。
  vad.reset();
  CHECK(vad.analyze(frame(300)).value().speech);
  vad.reset();
  CHECK(vad.analyze(frame(250)).value().speech);

  UtteranceSegmenter segmenter(config);
  const auto capacity = segmenter.reservedSamples();
  VadAnalysis yes, no;
  yes.speech = true;
  // 单次撞击不启动；弱音被预录音保留；600ms 自然停顿不切句。
  CHECK(segmenter.pushFrame(speech, yes).value() == SegmentEvent::kNone);
  CHECK(segmenter.pushFrame(quiet, no).value() == SegmentEvent::kNone);
  for (int i = 0; i < 20; ++i) segmenter.pushFrame(quiet, no);
  for (int i = 0; i < 20; ++i) segmenter.pushFrame(speech, yes);
  for (int i = 0; i < 30; ++i) CHECK(segmenter.pushFrame(silence, no).value() == SegmentEvent::kNone);
  CHECK(segmenter.inSpeech() && segmenter.utterance().front() == 100);
  segmenter.reset();
  // 百万帧快速推进，不按墙钟等待；最大语句终止、重置后分配容量不变。
  std::size_t forced = 0;
  for (int i = 0; i < 1000000; ++i) {
    const auto event = segmenter.pushFrame(speech, yes);
    CHECK(event.ok());
    CHECK(segmenter.reservedSamples() == capacity);
    CHECK(segmenter.utterance().size() <= 480000);
    if (event.value() == SegmentEvent::kForcedMaximum) {
      ++forced;
      CHECK(segmenter.utterance().size() == 480000);
      CHECK(!segmenter.pushFrame(speech, yes).ok());
      segmenter.reset();
    }
  }
  CHECK(forced > 600);
}

std::filesystem::path tempRoot(const std::string& suffix) {
  return std::filesystem::temp_directory_path() /
         ("rootlink-stage2-" + suffix + "-" + std::to_string(
             std::chrono::steady_clock::now().time_since_epoch().count()));
}

void testRolePromptAndSession() {
  const auto root = tempRoot("role");
  std::filesystem::create_directories(root / "persona");
  {
    std::ofstream output(root / "persona" / "profile.json");
    output << R"({"name":"阿澄","age":18,"gender":"female","personality_traits":["温柔","直接"],"interests":["音乐"],"background":"测试背景"})";
  }
  {
    std::ofstream output(root / "state.json");
    output << R"({"mood":"happy","energy":0.8,"affinity":3,"trust":2})";
  }
  {
    std::ofstream output(root / "memories.json");
    output << R"({"fact_memories":[{"content":"喜欢茉莉花茶"}]})";
  }
  rootlink::voice::RoleRepository repository;
  auto role = repository.load(root.string(), false);
  CHECK(role.ok() && role.value().name == "阿澄");
  rootlink::voice::PromptBuilder prompts;
  const std::string prompt = prompts.buildSystemPrompt(role.value());
  CHECK(prompt.find("你是阿澄") != std::string::npos);
  CHECK(prompt.find("喜欢茉莉花茶") != std::string::npos);
  // 黄金文本对应 lib/domain/rootlink_agent_runtime.dart 的顺序与默认值。
  const std::string golden =
      "你是阿澄，不是助手的角色扮演说明，而是以第一人称自然交流的本人。\n\n"
      "## 身份\n年龄：18\n性别：female\n生日：未知\n性格：温柔、直接\n兴趣：音乐\n背景：测试背景\n\n"
      "## 当前状态\n情绪：happy\n精力：0.8\n亲密度：3\n信任：2\n关系：neutral\n\n"
      "## 长期记忆\n- 喜欢茉莉花茶\n\n## 说话风格\n词汇级别：common；句长：varied。"
      "保持角色口吻，不要解释系统规则。\n每次回复不超过 5 句，除非用户明确要求展开。";
  CHECK(prompt == golden);
  std::vector<rootlink::voice::ChatMessage> history;
  for (int i = 0; i < 20; ++i) history.push_back({i % 2 ? "assistant" : "user", "历史", 1});
  const auto messages = prompts.buildMessages(role.value(), history, "现在", 2, 100);
  CHECK(messages.size() == 6);  // system + 最近四条 + 当前输入

  const auto sessions = tempRoot("sessions");
  rootlink::voice::ConversationSession session(sessions.string(), "role-a");
  CHECK(session.append({"user", "你好", 0}).ok());
  CHECK(session.append({"assistant", "你好呀", 0}).ok());
  {
    std::ofstream output(session.currentPath(), std::ios::app);
    output << "{truncated";  // 模拟掉电留下的尾部半行。
  }
  auto loaded = session.loadRecent(10);
  CHECK(loaded.ok() && loaded.value().size() == 2);
  CHECK(session.append({"user", "掉电后的新消息", 0}).ok());
  loaded = session.loadRecent(10);
  CHECK(loaded.ok() && loaded.value().size() == 3);
  CHECK(prompts.buildMessages(role.value(), {{"user", "超预算", 500}}, "现在", 8, 10).size() == 2);
  std::filesystem::remove_all(root);
  std::filesystem::remove_all(sessions);
}

class FakeCapture final : public rootlink::audio::AudioCapture {
 public:
  Status start() override { running = true; ++starts; return start_status; }
  Status readFrame(std::vector<std::int16_t>& output, std::chrono::milliseconds) override {
    ++reads;
    if (reads <= 20) output = frame(0);
    else if (reads <= 40) output = frame(1500);
    else output = frame(0);
    return Status::okStatus();
  }
  Status stop() override { running = false; ++stops; return Status::okStatus(); }
  bool isRunning() const noexcept override { return running; }
  AudioDeviceStats stats() const noexcept override { return {}; }
  int starts{0}; int stops{0}; int reads{0}; bool running{false};
  Status start_status;
};

class FakePlayback final : public rootlink::audio::AudioPlayback {
 public:
  Status start() override { running = true; ++starts; return Status::okStatus(); }
  Status writeFrame(const std::vector<std::int16_t>& input) override {
    CHECK(running && input.size() == 320); ++writes; return write_status;
  }
  Status drain() override { ++drains; return Status::okStatus(); }
  Status stop() override { running = false; ++stops; return Status::okStatus(); }
  bool isRunning() const noexcept override { return running; }
  AudioDeviceStats stats() const noexcept override { return {}; }
  int starts{0}; int stops{0}; int writes{0}; int drains{0}; bool running{false};
  Status write_status;
};

void testVoiceRuntimeCleanup() {
  FakeCapture capture;
  FakePlayback playback;
  rootlink::voice::MockAsrProvider asr;
  rootlink::voice::MockLlmProvider llm;
  rootlink::voice::MockTtsProvider tts;
  const auto sessions = tempRoot("runtime");
  rootlink::voice::ConversationSession session(sessions.string(), "default");
  rootlink::voice::RuntimeConfig config;
  std::vector<rootlink::voice::VoiceState> states;
  rootlink::voice::VoiceObserver observer;
  observer.on_state = [&](rootlink::voice::VoiceState state) {
    states.push_back(state);
    if (state == rootlink::voice::VoiceState::kPlaying) CHECK(playback.running);
    if (state == rootlink::voice::VoiceState::kListening) CHECK(capture.running);
    if (state == rootlink::voice::VoiceState::kPlaying ||
        state == rootlink::voice::VoiceState::kTranscribing ||
        state == rootlink::voice::VoiceState::kThinking ||
        state == rootlink::voice::VoiceState::kSynthesizing) CHECK(!capture.running);
  };
  rootlink::voice::VoiceRuntime runtime(capture, playback, asr, llm, tts,
                                        rootlink::voice::CompanionRole{}, session, config, observer);
  // drain 表示整段播放已经结束；此时再请求退出可验证正常清理，而不是中途取消。
  const Status status = runtime.run(0ms, [&] { return playback.drains > 0; });
  CHECK(status.ok());
  CHECK(capture.starts == 1 && capture.stops >= 1 && !capture.running);
  CHECK(playback.starts == 1 && playback.drains == 1 && !playback.running);
  CHECK(runtime.stats().utterances == 1);
  CHECK(std::find(states.begin(), states.end(), rootlink::voice::VoiceState::kTranscribing) != states.end());
  CHECK(std::find(states.begin(), states.end(), rootlink::voice::VoiceState::kPlaying) != states.end());
  std::filesystem::remove_all(sessions);
}

class FailingAsr final : public rootlink::voice::AsrProvider {
 public:
  Status failure{AudioError::kNetworkError, "injected"};
  rootlink::audio::Result<std::string> transcribe(const std::vector<std::int16_t>&,
      const rootlink::voice::StopRequested&) override { return rootlink::audio::Result<std::string>(failure); }
  void cancel() noexcept override {}
};
class FailingTts final : public rootlink::voice::TtsProvider {
 public:
  rootlink::audio::Result<std::vector<std::int16_t>> synthesize(const std::string&,
      const rootlink::voice::StopRequested&) override {
    return rootlink::audio::Result<std::vector<std::int16_t>>(Status(AudioError::kTimeout, "injected"));
  }
  void cancel() noexcept override {}
};

// 测试只使用虚构密钥，并恢复原环境；断言失败不会把密钥值打印出来。
class ScopedEnvironment {
 public:
  explicit ScopedEnvironment(const char* key) : key_(key) {
    if (const char* old = std::getenv(key)) { present_ = true; old_ = old; }
    set("");
  }
  ~ScopedEnvironment() { set(present_ ? old_.c_str() : ""); }
  void set(const char* value) {
#if defined(_WIN32)
    _putenv_s(key_.c_str(), value);
#else
    if (*value) setenv(key_.c_str(), value, 1); else unsetenv(key_.c_str());
#endif
  }
 private:
  std::string key_, old_;
  bool present_{false};
};

void testConfigPriorityAndValidation() {
  using namespace rootlink::voice;
  ScopedEnvironment target("TARGET"), audio("AUDIO_API"), service("SERVICE_MODE");
  ScopedEnvironment provider("LLM_PROVIDER"), model("LLM_MODEL"), base("LLM_BASE_URL");
  ScopedEnvironment models_env("MODELS_FILE"), secrets_env("SECRETS_FILE");
  ScopedEnvironment key("DEEPSEEK_API_KEY"), buffer("BUFFER_FRAMES");
  const auto root = tempRoot("config");
  std::filesystem::create_directories(root);
  const auto config_path = root / "rootlink.conf";
  const auto secrets = root / "secrets.env";
  {
    std::ofstream output(root / "models.json");
    output << R"({"default_provider":"deepseek","default_model":"fixture-model","providers":{)"
           << R"("deepseek":{"base_url":"https://fixture.invalid/v1","api_key":"fixture-json",)"
           << R"("auth_header":false,"headers":{"X-Fixture":"value"},"chat_path":"/custom/chat"}}})";
  }
  {
    std::ofstream output(config_path);
    output << "MODELS_FILE=" << (root / "models.json").generic_string()
           << "\nSECRETS_FILE=" << secrets.generic_string() << "\nBUFFER_FRAMES=40\n";
  }
  auto json_config = loadRuntimeConfig(config_path.string());
  CHECK(json_config.ok());
  if (!json_config.ok()) { std::filesystem::remove_all(root); return; }
  CHECK(json_config.value().llm.name == "deepseek");
  CHECK(json_config.value().llm.model == "fixture-model");
  CHECK(json_config.value().llm.api_key == "fixture-json");
  CHECK(!json_config.value().llm.auth_header);
  CHECK(json_config.value().llm.chat_path == "/custom/chat");
  CHECK(json_config.value().llm.headers.at("X-Fixture") == "value");
  { std::ofstream output(secrets); output << "DEEPSEEK_API_KEY=fixture-file\n"; }
  CHECK(loadRuntimeConfig(config_path.string()).value().llm.api_key == "fixture-file");
  key.set("fixture-environment"); model.set("override-model"); buffer.set("50");
  base.set("https://override.invalid/v1");
  auto overridden = loadRuntimeConfig(config_path.string());
  CHECK(overridden.ok());
  CHECK(overridden.value().llm.api_key == "fixture-environment");
  CHECK(overridden.value().llm.model == "override-model");
  CHECK(overridden.value().llm.base_url == "https://override.invalid/v1");
  CHECK(overridden.value().buffer_frames == 50);
  for (const char* invalid : {"-1", "nan", "0", "1001", "18446744073709551616"}) {
    buffer.set(invalid);
    CHECK(!loadRuntimeConfig(config_path.string()).ok());
  }
  RuntimeConfig invalid;
  invalid.vad.max_utterance_ms = 420;
  CHECK(!invalid.validate().ok());
  invalid = RuntimeConfig{}; invalid.service_mode = "cloud";
  CHECK(!invalid.validate().ok());
  invalid.audio_api = "alsa";
  CHECK(invalid.validate().ok());
  invalid.llm.base_url = "http://fixture.invalid";
  CHECK(!invalid.validate().ok());
  std::filesystem::remove_all(root);
}

void testCancellationAndErrors() {
  using namespace rootlink::voice;
  const auto root = tempRoot("errors");
  RuntimeConfig config;
  for (auto state : {VoiceState::kIdle, VoiceState::kListening, VoiceState::kTranscribing,
                    VoiceState::kThinking, VoiceState::kSynthesizing, VoiceState::kPlaying}) {
    FakeCapture capture;
    FakePlayback playback;
    MockAsrProvider asr; MockLlmProvider llm; MockTtsProvider tts;
    ConversationSession session(root.string(), "cancel");
    bool stop = false;
    VoiceObserver observer;
    observer.on_state = [&](VoiceState current) { if (current == state) stop = true; };
    VoiceRuntime runtime(capture, playback, asr, llm, tts, {}, session, config, observer);
    CHECK(runtime.run(1000ms, [&] { return stop; }).ok());
    CHECK(!capture.running && !playback.running);
    CHECK(!runtime.run(1ms, {}).ok());
  }
  for (auto code : {AudioError::kNetworkError, AudioError::kTimeout, AudioError::kAuthenticationError,
                   AudioError::kConfigError}) {
    FakeCapture capture; FakePlayback playback;
    FailingAsr asr; asr.failure = {code, "injected"};
    MockLlmProvider llm; MockTtsProvider tts;
    ConversationSession session(root.string(), "failure");
    VoiceRuntime runtime(capture, playback, asr, llm, tts, {}, session, config);
    auto result = runtime.run(1000ms, [&] { return capture.starts >= 2; });
    CHECK(result.ok() == (code == AudioError::kNetworkError || code == AudioError::kTimeout));
    CHECK(runtime.stats().turn_errors == 1);
    CHECK(!capture.running && !playback.running);
  }
  {
    FakeCapture capture; FakePlayback playback;
    MockAsrProvider asr; MockLlmProvider llm; FailingTts tts;
    ConversationSession session(root.string(), "tts-failure");
    VoiceRuntime runtime(capture, playback, asr, llm, tts, {}, session, config);
    CHECK(runtime.run(1000ms, [&] { return capture.starts >= 2; }).ok());
    CHECK(session.loadRecent(8).value().size() == 2);  // TTS 失败仍保留回答。
    CHECK(playback.starts == 0);
  }
  {
    FakeCapture capture; FakePlayback playback;
    playback.write_status = {AudioError::kDeviceError, "injected"};
    MockAsrProvider asr; MockLlmProvider llm; MockTtsProvider tts;
    ConversationSession session(root.string(), "device-failure");
    VoiceRuntime runtime(capture, playback, asr, llm, tts, {}, session, config);
    CHECK(!runtime.run(1000ms, {}).ok());
    CHECK(!capture.running && !playback.running);
  }
  std::filesystem::remove_all(root);
}

}  // namespace

int main() {
  testJsonCodecAndSse();
  testVadSegmentation();
  testVadBoundariesAndStress();
  testRolePromptAndSession();
  testVoiceRuntimeCleanup();
  testCancellationAndErrors();
  testConfigPriorityAndValidation();
  if (failures.load() != 0) {
    std::cerr << failures.load() << " Stage 2 checks failed\n";
    return 1;
  }
  std::cout << "All RootLink RV1106 Stage 2 core tests passed\n";
  return 0;
}
