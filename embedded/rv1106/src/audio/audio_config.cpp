#include "rootlink/audio/audio_config.h"

namespace rootlink::audio {

std::size_t AudioConfig::samplesPerFrame() const noexcept {
  return static_cast<std::size_t>(sample_rate) * channels * frame_duration_ms / 1000U;
}

std::size_t AudioConfig::bytesPerFrame() const noexcept {
  return samplesPerFrame() * bits_per_sample / 8U;
}

Status AudioConfig::validate() const {
  if (device.empty()) {
    return {AudioError::kInvalidArgument, "audio device name must not be empty"};
  }
  if (sample_rate != kSampleRate || channels != kChannels ||
      bits_per_sample != kBitsPerSample || frame_duration_ms != kFrameDurationMs) {
    return {AudioError::kUnsupportedFormat,
            "Phase 1 requires exactly 16000 Hz, mono, S16_LE, 20 ms frames"};
  }
  if (samplesPerFrame() != kSamplesPerFrame || bytesPerFrame() != kBytesPerFrame) {
    return {AudioError::kUnsupportedFormat, "audio frame size is not 320 samples / 640 bytes"};
  }
  return Status::okStatus();
}

}  // namespace rootlink::audio
