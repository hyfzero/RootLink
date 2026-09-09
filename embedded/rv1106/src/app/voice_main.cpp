#include "rootlink/voice/python_persona.h"
#include <chrono>
#include <algorithm>
#include <cmath>
#include <fstream>
#include <csignal>
#include <filesystem>
#include <iostream>
#include <memory>
#include <string>
#include <vector>
#include <atomic>
#include <thread>
#include "rootlink/ui/main_view.h"
#include "rootlink/ui/dialogue.h"

#include "rootlink/audio/audio_config.h"
#include "rootlink/audio/wav_file.h"
#include "rootlink/platform/process_memory.h"
#include "rootlink/voice/providers.h"
#include "rootlink/voice/codec.h"
#include "rootlink/voice/role.h"
#include "rootlink/voice/runtime_config.h"
#include "rootlink/voice/vad.h"
#include "rootlink/voice/voice_runtime.h"

#if defined(ROOTLINK_AUDIO_API_ALSA)
#include "rootlink/audio/alsa_audio_capture.h"
#include "rootlink/audio/alsa_audio_playback.h"
#else
#include "rootlink/audio/simulated_audio_capture.h"
#include "rootlink/audio/simulated_audio_playback.h"
#endif

namespace {

volatile std::sig_atomic_t g_stopped = 0;
std::atomic<bool> g_ui_stopped{false};
rootlink::ui::StateMailbox g_display_state;
rootlink::ui::DialogueMailbox g_dialogue;
void handleSignal(int) { g_stopped = 1; }

#if defined(ROOTLINK_AUDIO_API_ALSA)
using Capture = rootlink::audio::AlsaAudioCapture;
using Playback = rootlink::audio::AlsaAudioPlayback;
#else
using Capture = rootlink::audio::SimulatedAudioCapture;
using Playback = rootlink::audio::SimulatedAudioPlayback;
#endif

struct Options {
  std::string command;
  std::string config{ROOTLINK_DEFAULT_CONFIG_PATH};
  std::string input;
  std::string output;
  std::string output_dir{"segments"};
  std::string text;
  std::string capture_device;
  std::string playback_device;
  std::string asr_model;
  std::string llm_model;
  std::string tts_model;
  std::string tts_voice;
  std::string role_dir;
  std::string session_dir;
  std::size_t buffer_frames{0};
  double duration_seconds{0.0};
  bool probe_cloud{false};
};

void usage() {
  std::cerr << "RootLink RV1106 Stage 2 voice\n\n"
            << "Usage:\n"
            << "  rootlink-voice voice [--duration <seconds>] [--config <file>]\n"
            << "  rootlink-voice vad [--input <wav>] [--duration <seconds>] [--output-dir <dir>]\n"
            << "  rootlink-voice transcribe --input <wav>\n"
            << "  rootlink-voice chat --text <text>\n"
            << "  rootlink-voice synthesize --text <text> --output <wav>\n"
            << "  rootlink-voice doctor [--probe-cloud]\n\n"
            << "Options: --capture-device <pcm> --playback-device <pcm> --buffer-frames <n>\n"
            << "         --asr-model <name> --llm-model <name> --tts-model <name>\n"
            << "         --tts-voice <name> --role-dir <dir> --session-dir <dir>\n"
            << "Compiled audio API: " << ROOTLINK_AUDIO_API_NAME
            << ", service API: " << ROOTLINK_SERVICE_API_NAME << '\n';
}

bool next(int argc, char** argv, int& index, std::string& output) {
  if (index + 1 >= argc) return false;
  output = argv[++index];
  return true;
}

bool parse(int argc, char** argv, Options& options, std::string& error) {
  if (argc < 2) { error = "缺少命令"; return false; }
  options.command = argv[1];
  for (int index = 2; index < argc; ++index) {
    const std::string argument = argv[index];
    std::string value;
    if (argument == "--config") {
      if (!next(argc, argv, index, options.config)) { error = "--config 缺少值"; return false; }
    } else if (argument == "--input") {
      if (!next(argc, argv, index, options.input)) { error = "--input 缺少值"; return false; }
    } else if (argument == "--output") {
      if (!next(argc, argv, index, options.output)) { error = "--output 缺少值"; return false; }
    } else if (argument == "--output-dir") {
      if (!next(argc, argv, index, options.output_dir)) { error = "--output-dir 缺少值"; return false; }
    } else if (argument == "--text") {
      if (!next(argc, argv, index, options.text)) { error = "--text 缺少值"; return false; }
    } else if (argument == "--capture-device") {
      if (!next(argc, argv, index, options.capture_device)) { error = "--capture-device 缺少值"; return false; }
    } else if (argument == "--playback-device") {
      if (!next(argc, argv, index, options.playback_device)) { error = "--playback-device 缺少值"; return false; }
    } else if (argument == "--asr-model") {
      if (!next(argc, argv, index, options.asr_model)) { error = "--asr-model 缺少值"; return false; }
    } else if (argument == "--llm-model") {
      if (!next(argc, argv, index, options.llm_model)) { error = "--llm-model 缺少值"; return false; }
    } else if (argument == "--tts-model") {
      if (!next(argc, argv, index, options.tts_model)) { error = "--tts-model 缺少值"; return false; }
    } else if (argument == "--tts-voice") {
      if (!next(argc, argv, index, options.tts_voice)) { error = "--tts-voice 缺少值"; return false; }
    } else if (argument == "--role-dir") {
      if (!next(argc, argv, index, options.role_dir)) { error = "--role-dir 缺少值"; return false; }
    } else if (argument == "--session-dir") {
      if (!next(argc, argv, index, options.session_dir)) { error = "--session-dir 缺少值"; return false; }
    } else if (argument == "--buffer-frames") {
      if (!next(argc, argv, index, value)) { error = "--buffer-frames 缺少值"; return false; }
      try {
        std::size_t used = 0;
        // 先检查 64 位解析值，再转 size_t，防止 RV1106 上大整数截断后变成合法小容量。
        const auto parsed = std::stoull(value, &used);
        if (used != value.size() || value.front() == '-' || parsed == 0 ||
            parsed > 1000) throw std::invalid_argument("range");
        options.buffer_frames = static_cast<std::size_t>(parsed);
      } catch (...) { error = "--buffer-frames 必须是正整数"; return false; }
    } else if (argument == "--duration") {
      if (!next(argc, argv, index, value)) { error = "--duration 缺少值"; return false; }
      try {
        std::size_t used = 0;
        options.duration_seconds = std::stod(value, &used);
        if (used != value.size() || !std::isfinite(options.duration_seconds) ||
            options.duration_seconds > 86400) throw std::invalid_argument("range");
      }
      catch (...) { error = "--duration 不是有效数字"; return false; }
      if (options.duration_seconds <= 0) { error = "--duration 必须大于零"; return false; }
    } else if (argument == "--probe-cloud") {
      options.probe_cloud = true;
    } else {
      error = "未知参数：" + argument;
      return false;
    }
  }
  if (options.command == "transcribe" && options.input.empty()) {
    error = options.command + " 需要 --input"; return false;
  }
  if ((options.command == "chat" || options.command == "synthesize") && options.text.empty()) {
    error = options.command + " 需要 --text"; return false;
  }
  if (options.command == "synthesize" && options.output.empty()) {
    error = "synthesize 需要 --output"; return false;
  }
  if (options.command != "voice" && options.command != "vad" &&
      options.command != "transcribe" && options.command != "chat" &&
      options.command != "synthesize" && options.command != "doctor") {
    error = "未知命令：" + options.command; return false;
  }
  return true;
}

rootlink::audio::Result<std::vector<std::int16_t>> readWav(const std::string& path) {
  std::error_code ec;
  const auto bytes = std::filesystem::file_size(path, ec);
  if (ec || bytes > 8U * 1024U * 1024U)
    return rootlink::audio::Result<std::vector<std::int16_t>>(rootlink::audio::Status(
        rootlink::audio::AudioError::kStorageError, "输入 WAV 不可读或超过 8 MiB"));
  rootlink::audio::WavReader reader;
  auto status = reader.open(path);
  if (!status.ok()) return rootlink::audio::Result<std::vector<std::int16_t>>(status);
  std::vector<std::int16_t> samples;
  std::vector<std::int16_t> frame;
  while ((status = reader.readFrame(frame)).ok()) samples.insert(samples.end(), frame.begin(), frame.end());
  if (status.code() != rootlink::audio::AudioError::kEndOfStream)
    return rootlink::audio::Result<std::vector<std::int16_t>>(status);
  return rootlink::audio::Result<std::vector<std::int16_t>>(std::move(samples));
}

rootlink::audio::Status writeWav(const std::string& path,
                                 const std::vector<std::int16_t>& samples) {
  const auto wav = rootlink::voice::pcm16ToWav(samples);
  std::ofstream output(path, std::ios::binary);
  output.write(reinterpret_cast<const char*>(wav.data()), static_cast<std::streamsize>(wav.size()));
  output.close();
  return output ? rootlink::audio::Status::okStatus() : rootlink::audio::Status(
      rootlink::audio::AudioError::kStorageError, "无法写入 WAV 文件");
}

rootlink::audio::Status runVad(const Options& options,
                               const rootlink::voice::RuntimeConfig& config) {
  std::vector<std::int16_t> samples;
  std::unique_ptr<Capture> capture;
  if (!options.input.empty()) {
    auto wav = readWav(options.input);
    if (!wav.ok()) return wav.status();
    samples = std::move(wav.value());
  } else {
    rootlink::audio::AudioConfig audio_config;
    audio_config.device = config.capture_device;
#if defined(ROOTLINK_AUDIO_API_ALSA)
    capture = std::make_unique<Capture>(audio_config);
#else
    capture = std::make_unique<Capture>(audio_config, true);
#endif
    const auto status = capture->start();
    if (!status.ok()) return status;
  }
  std::filesystem::create_directories(options.output_dir);
  rootlink::voice::AdaptiveEnergyVad vad(config.vad);
  rootlink::voice::UtteranceSegmenter segmenter(config.vad);
  std::size_t segment_index = 0;
  // 离线文件结束相当于输入静音；补足结束窗，避免没有尾部静音的最后一句丢失。
  const auto end = samples.size() + config.vad.end_silence_ms / 20 * rootlink::audio::kSamplesPerFrame;
  const auto started = std::chrono::steady_clock::now();
  std::vector<std::int16_t> frame(rootlink::audio::kSamplesPerFrame);
  for (std::size_t offset = 0; capture || offset < end;) {
    if (g_stopped) return {rootlink::audio::AudioError::kCancelled, "VAD 已取消"};
    if (capture) {
      if (options.duration_seconds > 0 &&
          std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count() >=
              options.duration_seconds) break;
      const auto status = capture->readFrame(frame, std::chrono::milliseconds(100));
      if (status.code() == rootlink::audio::AudioError::kTimeout) continue;
      if (!status.ok()) return status;
    } else {
      std::fill(frame.begin(), frame.end(), 0);
      if (offset < samples.size())
        std::copy_n(samples.begin() + static_cast<std::ptrdiff_t>(offset),
                    std::min(frame.size(), samples.size() - offset), frame.begin());
      offset += rootlink::audio::kSamplesPerFrame;
    }
    auto analysis = vad.analyze(frame);
    if (!analysis.ok()) return analysis.status();
    auto event = segmenter.pushFrame(frame, analysis.value());
    if (!event.ok()) return event.status();
    if (event.value() == rootlink::voice::SegmentEvent::kCompleted ||
        event.value() == rootlink::voice::SegmentEvent::kForcedMaximum) {
      const auto path = std::filesystem::path(options.output_dir) /
                        ("segment-" + std::to_string(++segment_index) + ".wav");
      const auto status = writeWav(path.string(), segmenter.utterance());
      if (!status.ok()) return status;
      segmenter.reset();
    } else if (event.value() == rootlink::voice::SegmentEvent::kRejectedTooShort) {
      segmenter.reset();
    }
  }
  if (capture) {
    const auto status = capture->stop();
    if (!status.ok()) return status;
  }
  std::cout << "segments=" << segment_index << '\n';
  return rootlink::audio::Status::okStatus();
}

void printStats(const rootlink::voice::VoiceRuntimeStats& stats,
                const rootlink::audio::AudioDeviceStats& capture,
                const rootlink::audio::AudioDeviceStats& playback) {
  std::cout << "utterances=" << stats.utterances << '\n'
            << "turn_errors=" << stats.turn_errors << '\n'
            << "network_errors=" << stats.network_errors << '\n'
            << "authentication_errors=" << stats.authentication_errors << '\n'
            << "provider_errors=" << stats.provider_errors << '\n'
            << "vad_starts=" << stats.vad.starts << '\n'
            << "vad_completed=" << stats.vad.completed << '\n'
            << "vad_rejected_too_short=" << stats.vad.rejected_too_short << '\n'
            << "vad_forced_maximum=" << stats.vad.forced_maximum << '\n'
            << "asr_total_ms=" << stats.asr_ms << '\n'
            << "llm_first_delta_total_ms=" << stats.llm_first_delta_ms << '\n'
            << "llm_total_ms=" << stats.llm_total_ms << '\n'
            << "tts_total_ms=" << stats.tts_ms << '\n'
            << "playback_total_ms=" << stats.playback_ms << '\n'
            << "buffer_capacity_frames=" << stats.buffer.capacity_frames << '\n'
            << "buffer_high_watermark_frames=" << stats.buffer.high_watermark_frames << '\n'
            << "buffer_dropped_frames=" << stats.buffer.dropped_frames << '\n'
            << "capture_recoveries=" << capture.recoveries << '\n'
            << "playback_recoveries=" << playback.recoveries << '\n';
  const auto rss = rootlink::platform::residentMemoryKiB();
  if (rss) std::cout << "rss_kib=" << *rss << '\n';
  const auto peak = rootlink::platform::peakResidentMemoryKiB();
  if (peak) std::cout << "peak_rss_kib=" << *peak << '\n';
}

}  // namespace

int runMain(int argc, char** argv) {
  if (argc == 2 && (std::string(argv[1]) == "--help" || std::string(argv[1]) == "-h")) {
    usage(); return 0;
  }
  Options options;
  std::string error;
  if (!parse(argc, argv, options, error)) {
    std::cerr << "error: " << error << "\n\n"; usage(); return 2;
  }
  auto loaded = rootlink::voice::loadRuntimeConfig(options.config);
  if (!loaded.ok()) { std::cerr << "config error: " << loaded.status().message() << '\n'; return 2; }
  rootlink::voice::RuntimeConfig config = std::move(loaded.value());
  for (const auto& warning : config.warnings) std::cerr << "warning: " << warning << '\n';
  if (!options.capture_device.empty()) config.capture_device = options.capture_device;
  if (!options.playback_device.empty()) config.playback_device = options.playback_device;
  if (!options.asr_model.empty()) config.asr.model = options.asr_model;
  if (!options.llm_model.empty()) config.llm.model = options.llm_model;
  if (!options.tts_model.empty()) config.tts.model = options.tts_model;
  if (!options.tts_voice.empty()) config.tts_voice = options.tts_voice;
  if (!options.role_dir.empty()) config.role_dir = options.role_dir;
  if (!options.session_dir.empty()) config.session_dir = options.session_dir;
  if (options.buffer_frames != 0) config.buffer_frames = options.buffer_frames;
  const auto validated = config.validate();
  if (!validated.ok()) { std::cerr << validated.message() << '\n'; return 2; }
  if (options.command == "voice" || options.command == "synthesize") {
    std::cerr << "tts_translate_to=" << config.tts_translate_to << '\n'
              << "tts_model=" << config.tts.model << '\n'
              << "tts_translation_timeout_ms=" << config.tts_translation_timeout_ms << '\n'
              << "tts_timeout_ms=" << config.tts_timeout_ms << '\n'
              << "connect_timeout_ms=" << config.connect_timeout_ms << '\n';
  }
#if defined(ROOTLINK_AUDIO_API_ALSA)
  if (config.audio_api != "alsa") {
    std::cerr << "config error: 此二进制按 alsa 构建，请设置 AUDIO_API=alsa\n"; return 2;
  }
#else
  if (config.audio_api != "simulated") {
    std::cerr << "config error: 此二进制按 simulated 构建，请设置 AUDIO_API=simulated\n"; return 2;
  }
#endif
#if defined(ROOTLINK_SERVICE_API_CURL)
  if (config.service_mode != "cloud") {
    std::cerr << "config error: 此二进制按 cloud 构建，请设置 SERVICE_MODE=cloud\n"; return 2;
  }
#else
  if (config.service_mode != "mock") {
    std::cerr << "config error: 此二进制未包含 curl 云端后端，请重新按 cloud 构建\n"; return 2;
  }
#endif
  std::signal(SIGINT, handleSignal);
  std::signal(SIGTERM, handleSignal);
  const auto stopped = [] { return g_stopped != 0 || g_ui_stopped.load(); };

  // 本地分段无需角色、会话或云服务初始化。
  if (options.command == "vad") {
    const auto status = runVad(options, config);
    if (status.ok() || (status.code() == rootlink::audio::AudioError::kCancelled && stopped())) return 0;
    std::cerr << "vad error: " << status.message() << '\n';
    return 1;
  }

  rootlink::voice::RoleRepository roles;
  auto role = config.persona_backend == "python"
      ? rootlink::audio::Result<rootlink::voice::CompanionRole>(rootlink::voice::CompanionRole{})
      : roles.load(config.role_dir, config.service_mode == "mock");
  if (!role.ok()) { std::cerr << role.status().message() << '\n'; return 1; }
  rootlink::voice::ConversationSession session(config.session_dir, role.value().id);
  std::unique_ptr<rootlink::voice::AsrProvider> asr;
  std::unique_ptr<rootlink::voice::LlmProvider> llm;
  std::unique_ptr<rootlink::voice::TtsProvider> tts;
  const rootlink::voice::ProviderDiagnostic tts_diagnostics = [](const std::string& event) {
    std::cerr << event << '\n';
  };
#if defined(ROOTLINK_SERVICE_API_CURL)
  rootlink::voice::CurlHttpClient http;
  asr = std::make_unique<rootlink::voice::DashScopeAsrProvider>(http, config);
  llm = std::make_unique<rootlink::voice::OpenAiCompatibleLlmProvider>(http, config);
  tts = std::make_unique<rootlink::voice::DashScopeTtsProvider>(http, config, tts_diagnostics);
#else
  asr = std::make_unique<rootlink::voice::MockAsrProvider>();
  llm = std::make_unique<rootlink::voice::MockLlmProvider>();
  tts = std::make_unique<rootlink::voice::MockTtsProvider>();
#endif

  rootlink::audio::Status status;
  if (config.persona_backend == "python" && options.command != "transcribe" && options.command != "synthesize") {
    auto core = std::make_unique<rootlink::voice::PythonPersonaProvider>(config);
    status = core->start(stopped);
    if (status.ok()) status = core->health();
    if (!status.ok()) { std::cerr << status.message() << '\n'; return 1; }
    llm = std::move(core);
  }
  if (config.tts_translate_to == "ja") {
    std::unique_ptr<rootlink::voice::LlmProvider> translator;
#if defined(ROOTLINK_SERVICE_API_CURL)
    auto translation_config = config;
    translation_config.retry_count = 0;  // 翻译失败不可重放，避免额外云端请求。
    translation_config.llm_timeout_ms = config.tts_translation_timeout_ms;
    translator = std::make_unique<rootlink::voice::OpenAiCompatibleLlmProvider>(
        http, std::move(translation_config), true, true);
#else
    // mock 模式保持离线且确定性；测试可注入专用翻译器覆盖此路径。
    translator = std::make_unique<rootlink::voice::MockLlmProvider>();
#endif
    tts = std::make_unique<rootlink::voice::TranslatedTtsProvider>(
        std::move(translator), std::move(tts),
        [](const std::string& japanese) { std::cout << "tts_text_ja=" << japanese << '\n'; },
        tts_diagnostics);
  }
  if (options.command == "transcribe") {
    auto wav = readWav(options.input);
    if (!wav.ok()) status = wav.status();
    else {
      auto result = asr->transcribe(wav.value(), stopped);
      if (result.ok()) std::cout << result.value() << '\n'; else status = result.status();
    }
  } else if (options.command == "chat" && config.persona_backend == "python") {
    auto result = llm->complete({{"user", options.text, 0}}, [](const std::string& delta) { std::cout << delta << std::flush; }, stopped);
    std::cout << '\n';
    if (!result.ok()) status = result.status();
  } else if (options.command == "chat") {
    auto history = session.loadRecent(config.history_turns * 2);
    if (!history.ok()) status = history.status();
    else {
      rootlink::voice::PromptBuilder prompts;
      const auto messages = prompts.buildMessages(role.value(), history.value(), options.text,
                                                   config.history_turns, config.history_token_budget);
      auto result = llm->complete(messages, [](const std::string& delta) { std::cout << delta << std::flush; }, stopped);
      std::cout << '\n';
      if (!result.ok()) status = result.status();
      else {
        status = session.append({"user", options.text, 0});
        if (status.ok()) status = session.append({"assistant", result.value(), 0});
      }
    }
  } else if (options.command == "synthesize") {
    auto result = tts->synthesize(options.text, stopped);
    status = result.ok() ? writeWav(options.output, result.value()) : result.status();
  } else {
    rootlink::audio::AudioConfig capture_config;
    capture_config.device = config.capture_device;
    rootlink::audio::AudioConfig playback_config;
    playback_config.device = config.playback_device;
#if defined(ROOTLINK_AUDIO_API_ALSA)
    Capture capture(capture_config);
#else
    Capture capture(capture_config, true);
#endif
    Playback playback(playback_config);
    if (options.command == "doctor") {
      std::cout << "target=" << config.target << '\n'
                << "audio_api=" << config.audio_api << '\n'
                << "service_mode=" << config.service_mode << '\n'
                << "asr_model=" << config.asr.model << '\n'
                << "llm_provider=" << config.llm.name << '\n'
                << "llm_model=" << config.llm.model << '\n'
                << "tts_model=" << config.tts.model << '\n';
#if defined(ROOTLINK_SERVICE_API_CURL)
      std::cout << "tls_certificate_verification=enabled\n";
      status = http.checkEnvironment();
      if (status.ok() && (config.asr.api_key.empty() ||
          (config.llm.auth_header && config.llm.api_key.empty()) || config.tts.api_key.empty()))
        status = {rootlink::audio::AudioError::kAuthenticationError,
                  "cloud 模式缺少 ASR、LLM 或 TTS 所需环境变量/密钥文件配置"};
#endif
      if (status.ok()) status = capture.start();
      if (status.ok()) status = capture.stop();
      if (status.ok()) status = playback.start();
      if (status.ok()) status = playback.stop();
      if (status.ok() && options.probe_cloud) {
        // 只有这一显式选项会在 doctor 中产生费用：依次探测三类供应商。
        auto result = llm->complete({{"user", "只回复：连接正常", 0}}, {}, stopped);
        if (!result.ok()) status = result.status();
        else {
          auto speech = tts->synthesize("连接正常", stopped);
          if (!speech.ok()) status = speech.status();
          else {
            auto text = asr->transcribe(speech.value(), stopped);
            if (!text.ok()) status = text.status();
            else std::cout << "cloud_probe=asr,llm,tts_ok\n";
          }
        }
      }
      if (status.ok()) std::cout << "doctor=ok\n";
    } else {
      rootlink::voice::VoiceObserver observer;
      const bool dialogue_enabled = config.ui_backend != "none";
      observer.on_state = [dialogue_enabled](rootlink::voice::VoiceState state) {
        if (dialogue_enabled && state == rootlink::voice::VoiceState::kThinking)
          g_dialogue.beginTurn();
        g_display_state.publish(state);
        std::cout << '\n' << "state=" << rootlink::voice::voiceStateName(state) << '\n';
      };
      observer.on_transcript = [](const std::string& value) { std::cout << "user=" << value << '\n'; };
      observer.on_answer_delta = [dialogue_enabled](const std::string& value) {
        if (dialogue_enabled) g_dialogue.append(value);
        std::cout << value << std::flush;
      };
      observer.on_answer = [dialogue_enabled](const std::string& value) {
        if (dialogue_enabled) g_dialogue.replace(value);
      };
      observer.on_error = [](const rootlink::audio::Status& value) {
        std::cerr << "turn_error=" << value.message() << '\n';
      };
      rootlink::voice::VoiceRuntime runtime(capture, playback, *asr, *llm, *tts,
                                            role.value(), session, config, observer);
      const auto duration = std::chrono::milliseconds(
          static_cast<std::int64_t>(options.duration_seconds * 1000.0));
      status = runtime.run(duration, stopped);
      std::cout << '\n';
      printStats(runtime.stats(), capture.stats(), playback.stats());
#if defined(ROOTLINK_SERVICE_API_CURL)
      const auto cloud = http.stats();
      std::cout << "http_requests=" << cloud.requests << '\n'
                << "network_retries=" << cloud.retries << '\n'
                << "http_authentication_errors=" << cloud.authentication_errors << '\n'
                << "http_rate_limit_errors=" << cloud.rate_limit_errors << '\n'
                << "http_provider_errors=" << cloud.provider_errors << '\n';
#endif
    }
  }
  if (!status.ok()) {
    if (status.code() == rootlink::audio::AudioError::kCancelled && stopped()) return 0;
    std::cerr << "voice error (" << static_cast<int>(status.code()) << "): "
              << status.message() << '\n';
    return 1;
  }
  return 0;
}

int safeRun(int argc, char** argv) {
  try { return runMain(argc, argv); }
  catch (const std::exception&) {
    // 异常 what() 可能来自第三方并携带请求内容；只打印无敏感信息的固定提示。
    std::cerr << "运行失败：文件系统或资源异常，请检查目录权限和可用内存\n";
    return 1;
  }
}

int main(int argc, char** argv) {
  try {
    Options options;
    std::string error;
    if (!parse(argc, argv, options, error) || options.command != "voice") return safeRun(argc, argv);
    auto loaded = rootlink::voice::loadRuntimeConfig(options.config);
    if (!loaded.ok() || loaded.value().ui_backend == "none") return safeRun(argc, argv);
    std::signal(SIGINT, handleSignal);
    std::signal(SIGTERM, handleSignal);
    rootlink::ui::MainView view;
    const auto started = view.initialize(loaded.value());
    if (!started.ok()) { std::cerr << started.message() << '\n'; return 1; }
    rootlink::ui::DialogueTypewriter dialogue(loaded.value().ui_text_interval_ms);
    rootlink::ui::DialogueSnapshot dialogue_snapshot;
    std::uint64_t dialogue_revision = 0;
    const auto ui_time_ms = [] {
      return static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
          std::chrono::steady_clock::now().time_since_epoch()).count());
    };
    g_dialogue.beginTurn();
    std::atomic<bool> finished{false};
    int result = 1;
    auto run_worker = [&] {
      result = safeRun(argc, argv);
      if (result != 0) g_display_state.publish(rootlink::voice::VoiceState::kError);
      finished.store(true);
    };
    std::thread worker(run_worker);
    bool resetting = false;
    try {
      // Never join a running worker on a tap: keep servicing the display while
      // cooperative cancellation closes requests, audio and the Python process.
      while (view.tick(g_display_state.read())) {
        if (g_stopped) break;
        if (!resetting) {
          const auto now = ui_time_ms();
          if (g_dialogue.readIfChanged(dialogue_revision, dialogue_snapshot))
            dialogue.update(dialogue_snapshot, now);
          dialogue.tick(now);
          view.setDialogue(dialogue.visible());
        }
        if (view.takeResetRequest() && !resetting) {
          resetting = true;
          g_ui_stopped.store(true);
          dialogue.clear(ui_time_ms());
          view.setDialogue("");
          std::cout << "reset=requested; cancelling current turn without replay\n";
        }
        if (finished.load()) {
          if (resetting) {
            worker.join(); // old providers and audio have now been destroyed
            g_display_state.reset();
            g_dialogue.beginTurn();
            g_ui_stopped.store(false);
            finished.store(false);
            resetting = false;
            std::cout << "reset=ready; restarting voice runtime\n";
            worker = std::thread(run_worker);
          } else if (result == 0) break;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
      }
    } catch (...) {
      g_ui_stopped.store(true);
      if (worker.joinable()) worker.join();
      throw;
    }
    g_ui_stopped.store(true);
    if (worker.joinable()) worker.join();
    return result;
  } catch (...) {
    std::cerr << "Cannot initialize or run UI resources\n";
    return 1;
  }
}
