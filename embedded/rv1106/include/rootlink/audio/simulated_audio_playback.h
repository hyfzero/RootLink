#pragma once

#include <atomic>
#include <chrono>
#include <mutex>

#include "rootlink/audio/audio_config.h"
#include "rootlink/audio/audio_playback.h"

namespace rootlink::audio {

/**
 * @brief 无硬件音频输出后端。
 *
 * 输入帧会被校验后丢弃，但类会按 20 ms/帧限速。因此 play 和 loopback 在仿真
 * 环境中的时序接近真机，而不是瞬间消费完整 WAV。它不会产生系统声音。
 */
class SimulatedAudioPlayback final : public AudioPlayback {
 public:
  explicit SimulatedAudioPlayback(AudioConfig config);
  ~SimulatedAudioPlayback() override;

  Status start() override;
  Status writeFrame(const std::vector<std::int16_t>& frame) override;
  Status drain() override;
  Status stop() override;
  bool isRunning() const noexcept override;
  AudioDeviceStats stats() const noexcept override;

 private:
  AudioConfig config_;
  std::atomic<bool> running_{false};
  std::mutex timing_mutex_;
  std::chrono::steady_clock::time_point next_frame_{};
};

}  // namespace rootlink::audio
