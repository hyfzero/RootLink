#pragma once

#include <atomic>
#include <memory>

#include "rootlink/audio/audio_config.h"
#include "rootlink/audio/audio_playback.h"

namespace rootlink::audio {

/**
 * @brief RV1106/Linux ALSA 阻塞播放实现。
 *
 * 与采集侧执行相同的精确格式复核；短写会继续提交余下采样，underrun 通过
 * snd_pcm_recover 恢复并记入统计。句柄非阻塞，数据等待有界阻塞；每帧写入与 drain
 * 各有 2s 安全上限，防止异常设备无限挂起。stop 使用 drop 立即清除设备队列。
 */
class AlsaAudioPlayback final : public AudioPlayback {
 public:
  explicit AlsaAudioPlayback(AudioConfig config);
  ~AlsaAudioPlayback() override;

  Status start() override;
  Status writeFrame(const std::vector<std::int16_t>& frame) override;
  Status drain() override;
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
