#pragma once

#include <atomic>
#include <memory>

#include "rootlink/audio/audio_capture.h"
#include "rootlink/audio/audio_config.h"

namespace rootlink::audio {

/**
 * @brief RV1106/Linux ALSA 阻塞采集实现。
 *
 * start 会逐项协商并复核 S16_LE、单声道、16 kHz 和 320-sample period；任何近似但
 * 不精确的结果都被拒绝。readFrame 使用 snd_pcm_wait，并用 snd_pcm_recover 处理
 * 可恢复 overrun。PIMPL 隔离 ALSA 类型，公共头不要求包含 asoundlib.h。
 */
class AlsaAudioCapture final : public AudioCapture {
 public:
  explicit AlsaAudioCapture(AudioConfig config);
  ~AlsaAudioCapture() override;

  Status start() override;
  Status readFrame(std::vector<std::int16_t>& frame,
                   std::chrono::milliseconds timeout) override;
  Status stop() override;
  bool isRunning() const noexcept override;
  AudioDeviceStats stats() const noexcept override;

 private:
  struct Impl;
  AudioConfig config_;
  std::unique_ptr<Impl> impl_;
  std::atomic<bool> running_{false};
  std::atomic<std::uint64_t> recoveries_{0};
};

}  // namespace rootlink::audio
