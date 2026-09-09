#include "rootlink/voice/voice_runtime.h"

#include <algorithm>
#include <thread>

#include "rootlink/audio/audio_config.h"

namespace rootlink::voice {
namespace {

std::uint64_t elapsedMs(std::chrono::steady_clock::time_point begin) {
  return static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
                                        std::chrono::steady_clock::now() - begin)
                                        .count());
}

}  // namespace

const char* voiceStateName(VoiceState state) noexcept {
  switch (state) {
    case VoiceState::kIdle: return "IDLE";
    case VoiceState::kListening: return "LISTENING";
    case VoiceState::kTranscribing: return "TRANSCRIBING";
    case VoiceState::kThinking: return "THINKING";
    case VoiceState::kSynthesizing: return "SYNTHESIZING";
    case VoiceState::kPlaying: return "PLAYING";
    case VoiceState::kError: return "ERROR";
    case VoiceState::kStopping: return "STOPPING";
  }
  return "UNKNOWN";
}

VoiceRuntime::VoiceRuntime(audio::AudioCapture& capture, audio::AudioPlayback& playback,
                           AsrProvider& asr, LlmProvider& llm, TtsProvider& tts,
                           CompanionRole role, ConversationSession& session,
                           RuntimeConfig config, VoiceObserver observer)
    : capture_(capture), playback_(playback), asr_(asr), llm_(llm), tts_(tts),
      role_(std::move(role)), session_(session), config_(std::move(config)),
      observer_(std::move(observer)), vad_(config_.vad), segmenter_(config_.vad),
      buffer_(config_.buffer_frames, audio::kSamplesPerFrame) {}

VoiceRuntime::~VoiceRuntime() {
  cancel();
  (void)capture_.stop();
  (void)playback_.stop();
}

void VoiceRuntime::setState(VoiceState state) {
  state_ = state;
  if (observer_.on_state) observer_.on_state(state);
}

bool VoiceRuntime::isFatal(const audio::Status& status) const noexcept {
  return status.code() == audio::AudioError::kConfigError ||
         status.code() == audio::AudioError::kAuthenticationError ||
         status.code() == audio::AudioError::kDeviceError ||
         status.code() == audio::AudioError::kStorageError;
}

audio::Status VoiceRuntime::run(std::chrono::milliseconds duration,
                                const StopRequested& stopped) {
  if (used_) return {audio::AudioError::kInvalidState, "VoiceRuntime 每个实例只允许 run 一次"};
  used_ = true;
  const auto started = std::chrono::steady_clock::now();
  auto should_stop = [&] {
    return cancelled_ || (stopped && stopped()) ||
           (duration.count() > 0 && std::chrono::steady_clock::now() - started >= duration);
  };
  setState(VoiceState::kIdle);
  if (should_stop()) { buffer_.close(); return audio::Status::okStatus(); }
  audio::Status status = capture_.start();
  if (!status.ok()) { (void)capture_.stop(); return status; }
  setState(VoiceState::kListening);
  std::vector<std::int16_t> frame;
  while (!should_stop()) {
    status = capture_.readFrame(frame, std::chrono::milliseconds(100));
    if (status.code() == audio::AudioError::kTimeout) continue;
    if (!status.ok()) break;
    status = buffer_.push(frame);
    if (!status.ok()) break;
    status = buffer_.pop(frame, std::chrono::milliseconds(0));
    if (!status.ok()) break;
    auto analysis = vad_.analyze(frame);
    if (!analysis.ok()) { status = analysis.status(); break; }
    auto event = segmenter_.pushFrame(frame, analysis.value());
    if (!event.ok()) { status = event.status(); break; }
    if (event.value() == SegmentEvent::kRejectedTooShort) {
      segmenter_.reset();
      continue;
    }
    if (event.value() != SegmentEvent::kCompleted &&
        event.value() != SegmentEvent::kForcedMaximum) continue;

    // 保持对预分配语句区的只读引用；本轮处理结束前不 reset，避免再复制约 1 MiB。
    const auto& utterance = segmenter_.utterance();
    status = capture_.stop();
    if (!status.ok()) break;
    status = processUtterance(utterance, should_stop);
    segmenter_.reset();
    if (!status.ok()) {
      if (status.code() == audio::AudioError::kCancelled && should_stop()) break;
      ++stats_.turn_errors;
      if (status.code() == audio::AudioError::kNetworkError ||
          status.code() == audio::AudioError::kRateLimited ||
          status.code() == audio::AudioError::kTimeout) ++stats_.network_errors;
      else if (status.code() == audio::AudioError::kAuthenticationError)
        ++stats_.authentication_errors;
      else if (status.code() == audio::AudioError::kProviderError)
        ++stats_.provider_errors;
      // ASR/TTS failures leave the resident personality core usable. A failed
      // Python exchange terminates that process and must never be replayed.
      const bool terminal = isFatal(status) ||
          (config_.persona_backend == "python" && state_ == VoiceState::kThinking);
      status = {status.code(), std::string("stage=") + voiceStateName(state_) +
          (terminal ? " action=exit: " : " action=skip_turn_resume_listening: ") + status.message()};
      if (observer_.on_error) observer_.on_error(status);
      if (terminal) { setState(VoiceState::kError); break; }
      status = audio::Status::okStatus();
    }
    if (should_stop()) break;
    // ALSA 停止后重新 prepare 能丢弃处理期间的旧采集数据；仿真后端也会重置节拍。
    setState(VoiceState::kIdle);
    status = capture_.start();
    if (!status.ok()) break;
    setState(VoiceState::kListening);
  }
  const bool normal_stop = state_ != VoiceState::kError &&
      (status.ok() || status.code() == audio::AudioError::kInterrupted ||
       status.code() == audio::AudioError::kCancelled ||
       ((status.code() == audio::AudioError::kTimeout || status.code() == audio::AudioError::kClosed) && should_stop()));
  setState(normal_stop ? VoiceState::kStopping : VoiceState::kError);
  const audio::Status capture_stop = capture_.stop();
  (void)playback_.stop();
  buffer_.close();
  stats_.buffer = buffer_.stats();
  stats_.vad = segmenter_.stats();
  setState(normal_stop && capture_stop.ok() ? VoiceState::kIdle : VoiceState::kError);
  if (normal_stop)
    return capture_stop.ok() ? audio::Status::okStatus() : capture_stop;
  return status;
}

audio::Status VoiceRuntime::processUtterance(const std::vector<std::int16_t>& samples,
                                             const StopRequested& stopped) {
  setState(VoiceState::kTranscribing);
  auto begin = std::chrono::steady_clock::now();
  auto transcription = asr_.transcribe(samples, stopped);
  stats_.asr_ms += elapsedMs(begin);
  if (!transcription.ok()) return transcription.status();
  if (transcription.value().empty())
    return {audio::AudioError::kProviderError, "ASR 返回了空文本"};
  if (observer_.on_transcript) observer_.on_transcript(transcription.value());

  std::vector<ChatMessage> messages{{"user", transcription.value(), 0}};
  if (config_.persona_backend != "python") {
    auto history = session_.loadRecent(config_.history_turns * 2);
    if (!history.ok()) return history.status();
    messages = prompt_builder_.buildMessages(role_, history.value(), transcription.value(),
        config_.history_turns, config_.history_token_budget);
  }
  setState(VoiceState::kThinking);
  begin = std::chrono::steady_clock::now();
  bool first_delta = true;
  auto answer = llm_.complete(messages, [&](const std::string& delta) {
    if (first_delta) {
      stats_.llm_first_delta_ms += elapsedMs(begin);
      first_delta = false;
    }
    if (observer_.on_answer_delta) observer_.on_answer_delta(delta);
  }, stopped);
  stats_.llm_total_ms += elapsedMs(begin);
  if (!answer.ok()) return answer.status();
  if (answer.value().empty()) return {audio::AudioError::kProviderError, "LLM 返回了空回答"};
  if (observer_.on_answer) observer_.on_answer(answer.value());

  if (config_.persona_backend != "python") {
  audio::Status stored = session_.append({"user", transcription.value(), 0});
  if (!stored.ok()) return stored;
  stored = session_.append({"assistant", answer.value(), 0});
  if (!stored.ok()) return stored;
  }
  ++stats_.utterances;

  setState(VoiceState::kSynthesizing);
  begin = std::chrono::steady_clock::now();
  auto speech = tts_.synthesize(answer.value(), stopped);
  stats_.tts_ms += elapsedMs(begin);
  if (!speech.ok()) return speech.status();
  const auto played = playSamples(speech.value(), stopped);
  if (!played.ok() && (cancelled_ || (stopped && stopped())))
    return {audio::AudioError::kCancelled, "播放已取消"};
  if (!played.ok() && played.code() != audio::AudioError::kCancelled)
    return {audio::AudioError::kDeviceError, played.message()};
  return played;
}

audio::Status VoiceRuntime::playSamples(const std::vector<std::int16_t>& samples,
                                        const StopRequested& stopped) {
  if (samples.empty())
    return {audio::AudioError::kUnsupportedFormat, "TTS PCM 为空"};
  const auto begin = std::chrono::steady_clock::now();
  audio::Status status = playback_.start();
  if (!status.ok()) return status;
  setState(VoiceState::kPlaying);
  std::vector<std::int16_t> frame(audio::kSamplesPerFrame);
  for (std::size_t offset = 0; offset < samples.size(); offset += audio::kSamplesPerFrame) {
    if ((stopped && stopped()) || cancelled_) {
      (void)playback_.stop();
      return {audio::AudioError::kCancelled, "播放已取消"};
    }
    // 云端 WAV 不保证 20 ms 对齐；只给最后一次硬件写入补静音，不改变存储音频。
    std::fill(frame.begin(), frame.end(), 0);
    std::copy_n(samples.begin() + static_cast<std::ptrdiff_t>(offset),
                std::min(audio::kSamplesPerFrame, samples.size() - offset),
                frame.begin());
    status = playback_.writeFrame(frame);
    if (!status.ok()) { (void)playback_.stop(); return status; }
  }
  status = playback_.drain();
  const audio::Status stop_status = playback_.stop();
  stats_.playback_ms += elapsedMs(begin);
  return !status.ok() ? status : stop_status;
}

void VoiceRuntime::cancel() noexcept {
  cancelled_ = true;
  asr_.cancel();
  llm_.cancel();
  tts_.cancel();
  // 取消方只通知；音频句柄由 run 所在线程关闭，避免并发 close/read 的竞态。
  buffer_.close();
}

}  // namespace rootlink::voice
