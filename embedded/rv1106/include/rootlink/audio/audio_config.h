#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

#include "rootlink/audio/status.h"

namespace rootlink::audio {

// Phase 1 的线缆协议。这里有意使用编译期常量：若以后支持其他格式，应进入新阶段，
// 而不是让录音、WAV、缓冲区和网络各自悄悄采用不同参数。
inline constexpr std::uint32_t kSampleRate = 16000;
inline constexpr std::uint16_t kChannels = 1;
inline constexpr std::uint16_t kBitsPerSample = 16;
inline constexpr std::uint32_t kFrameDurationMs = 20;
inline constexpr std::size_t kSamplesPerFrame = 320;
inline constexpr std::size_t kBytesPerFrame = 640;
inline constexpr std::size_t kDefaultBufferFrames = 100;

struct AudioConfig {
  /// ALSA PCM 名称，例如 default 或 hw:0,0；仿真后端保留但不使用。
  std::string device{"default"};
  std::uint32_t sample_rate{kSampleRate};
  std::uint16_t channels{kChannels};
  std::uint16_t bits_per_sample{kBitsPerSample};
  std::uint32_t frame_duration_ms{kFrameDurationMs};

  /// 根据采样率和帧时长计算单声道采样数；Phase 1 固定返回 320。
  std::size_t samplesPerFrame() const noexcept;
  /// 包含全部声道的 PCM 字节数；Phase 1 固定返回 640。
  std::size_t bytesPerFrame() const noexcept;
  /// 拒绝任何偏离 16 kHz/mono/PCM16/20 ms 的配置。
  Status validate() const;
};

}  // namespace rootlink::audio
