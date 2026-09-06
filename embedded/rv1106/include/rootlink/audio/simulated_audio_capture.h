#pragma once

#include <atomic>
#include <chrono>
#include <cstdint>
#include <mutex>

#include "rootlink/audio/audio_capture.h"
#include "rootlink/audio/audio_config.h"

namespace rootlink::audio {

/**
 * @brief 无硬件音频输入后端。
 *
 * 默认以真实的 20 ms 节拍产生连续测试音，保持 Phase 1 录音测试行为。
 * voice_pattern=true 时循环产生“静音—测试音—静音”，使 mock 模式可自动走完
 * VAD、ASR、LLM、TTS 和播放，而不需要真实麦克风。
 * 该后端不模拟 ALSA 故障，也不会访问麦克风。
 */
class SimulatedAudioCapture final : public AudioCapture {
 public:
  explicit SimulatedAudioCapture(AudioConfig config, bool voice_pattern = false);
  ~SimulatedAudioCapture() override;

  /// 重置节拍和波形相位；重复调用是安全的。
  Status start() override;

  /// 等待下一帧时刻并生成恰好 320 个采样；等待超过 timeout 时返回 kTimeout。
  Status readFrame(std::vector<std::int16_t>& frame,
                   std::chrono::milliseconds timeout) override;

  /// 停止生成；重复调用是安全的，最迟在一个 20 ms 帧周期内生效。
  Status stop() override;
  bool isRunning() const noexcept override;
  AudioDeviceStats stats() const noexcept override;

 private:
  AudioConfig config_;
  bool voice_pattern_{false};
  std::atomic<bool> running_{false};
  std::mutex timing_mutex_;
  std::chrono::steady_clock::time_point next_frame_{};
  std::uint64_t sample_index_{0};
  std::uint64_t frame_index_{0};
};

}  // namespace rootlink::audio
