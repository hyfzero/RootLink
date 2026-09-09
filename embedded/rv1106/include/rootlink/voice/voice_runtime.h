#pragma once

#include <atomic>
#include <chrono>
#include <cstdint>
#include <functional>
#include <string>
#include <vector>

#include "rootlink/audio/audio_capture.h"
#include "rootlink/audio/audio_playback.h"
#include "rootlink/audio/pcm_ring_buffer.h"
#include "rootlink/voice/providers.h"
#include "rootlink/voice/role.h"
#include "rootlink/voice/runtime_config.h"
#include "rootlink/voice/vad.h"

namespace rootlink::voice {

/** @brief 状态只在 run 所在线程变更；观察器同步调用，不得阻塞。 */
enum class VoiceState {
  kIdle,
  kListening,
  kTranscribing,
  kThinking,
  kSynthesizing,
  kPlaying,
  kError,
  kStopping,
};

/** @brief 本次 run 的累计计数/毫秒；结束后读取，不能与 run 并发读。 */
struct VoiceRuntimeStats {
  std::uint64_t utterances{0};
  std::uint64_t turn_errors{0};
  std::uint64_t asr_ms{0};
  std::uint64_t llm_first_delta_ms{0};
  std::uint64_t llm_total_ms{0};
  std::uint64_t tts_ms{0};
  std::uint64_t playback_ms{0};
  std::uint64_t network_errors{0};
  std::uint64_t authentication_errors{0};
  std::uint64_t provider_errors{0};
  audio::PcmRingBufferStats buffer;
  SegmenterStats vad;
};

/** @brief 同步状态/文本通知；回调不得抛异常或重入运行时。 */
struct VoiceObserver {
  std::function<void(VoiceState)> on_state;
  std::function<void(const std::string&)> on_transcript;
  std::function<void(const std::string&)> on_answer_delta;
  std::function<void(const audio::Status&)> on_error;
  std::function<void(const std::string&)> on_answer; // authoritative completed original text
  // 仅设置该回调时启用句子级中日语音同步；参数为原中文分段与 PCM 时长。
  std::function<void(const std::string&, std::uint64_t)> on_speech_segment;
  // 分段音频 drain 后轮询；返回 true 表示 UI 已展示完该段。
  std::function<bool()> speech_segment_complete;
};

/**
 * @brief Stage 2 半双工运行时。
 *
 * 检测到完整语句后先停止采集，从物理层保证云端处理和扬声器播放期间不会再次
 * 触发 VAD；播放 drain/stop 完成、采集队列清空后才重新进入 LISTENING。
 */
class VoiceRuntime {
 public:
  VoiceRuntime(audio::AudioCapture& capture, audio::AudioPlayback& playback,
               AsrProvider& asr, LlmProvider& llm, TtsProvider& tts,
               CompanionRole role, ConversationSession& session,
               RuntimeConfig config, VoiceObserver observer = {});
  ~VoiceRuntime();

  /** @brief 每实例只运行一次；duration 为零表示持续到取消。依赖对象必须存活到析构。 */
  audio::Status run(std::chrono::milliseconds duration, const StopRequested& stopped);
  /** @brief 可跨线程通知取消；调用者仍须等待 run 返回后再析构。 */
  void cancel() noexcept;
  VoiceState state() const noexcept { return state_; }
  const VoiceRuntimeStats& stats() const noexcept { return stats_; }

 private:
  audio::Status processUtterance(const std::vector<std::int16_t>& samples,
                                 const StopRequested& stopped);
  audio::Status playSamples(const std::vector<std::int16_t>& samples,
                            const StopRequested& stopped,
                            const std::function<void()>& on_first_frame = {});
  void setState(VoiceState state);
  bool isFatal(const audio::Status& status) const noexcept;

  audio::AudioCapture& capture_;
  audio::AudioPlayback& playback_;
  AsrProvider& asr_;
  LlmProvider& llm_;
  TtsProvider& tts_;
  CompanionRole role_;
  ConversationSession& session_;
  RuntimeConfig config_;
  VoiceObserver observer_;
  AdaptiveEnergyVad vad_;
  UtteranceSegmenter segmenter_;
  PromptBuilder prompt_builder_;
  audio::PcmRingBuffer buffer_;
  VoiceState state_{VoiceState::kIdle};
  VoiceRuntimeStats stats_;
  std::atomic<bool> cancelled_{false};
  bool used_{false};
};

const char* voiceStateName(VoiceState state) noexcept;

}  // namespace rootlink::voice
