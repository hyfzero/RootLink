#include "rootlink/audio/simulated_audio_capture.h"

#include <thread>
#include <utility>

namespace rootlink::audio {

SimulatedAudioCapture::SimulatedAudioCapture(AudioConfig config, bool voice_pattern)
    : config_(std::move(config)), voice_pattern_(voice_pattern) {}

SimulatedAudioCapture::~SimulatedAudioCapture() { (void)stop(); }

Status SimulatedAudioCapture::start() {
  if (running_.load()) return Status::okStatus();
  const Status valid = config_.validate();
  if (!valid.ok()) return valid;

  std::lock_guard<std::mutex> lock(timing_mutex_);
  sample_index_ = 0;
  frame_index_ = 0;
  next_frame_ = std::chrono::steady_clock::now();
  running_.store(true);
  return Status::okStatus();
}

Status SimulatedAudioCapture::readFrame(std::vector<std::int16_t>& frame,
                                        std::chrono::milliseconds timeout) {
  if (!running_.load()) {
    return {AudioError::kInvalidState, "simulated capture is not running"};
  }
  if (timeout.count() < 0) {
    return {AudioError::kInvalidArgument, "capture timeout must be non-negative"};
  }

  std::chrono::steady_clock::time_point frame_time;
  {
    // 只有确认 timeout 足够时才预订时间槽，超时不会偷偷丢掉下一帧。若调用方已
    // 落后于节拍，则从当前时间重新起算，避免为了“追赶”而瞬间生成大量旧帧。
    std::lock_guard<std::mutex> lock(timing_mutex_);
    const auto now = std::chrono::steady_clock::now();
    frame_time = next_frame_ > now ? next_frame_ : now;
    if (frame_time - now > timeout) {
      return {AudioError::kTimeout, "simulated capture timed out"};
    }
    next_frame_ = frame_time + std::chrono::milliseconds(config_.frame_duration_ms);
  }

  if (frame_time > std::chrono::steady_clock::now()) std::this_thread::sleep_until(frame_time);
  if (!running_.load()) return {AudioError::kInterrupted, "simulated capture stopped"};

  frame.resize(config_.samplesPerFrame());
  // 一个 2.4 秒周期：400 ms 静音、1 秒语音、1 秒尾静音。尾静音超过默认
  // 800 ms，确保离线仿真可以稳定地产生完整语句并回到监听状态。
  const std::uint64_t phase_frame = frame_index_ % 120U;
  const bool speaking = !voice_pattern_ || (phase_frame >= 20U && phase_frame < 70U);
  for (std::int16_t& sample : frame) {
    if (speaking) {
      // 80 个采样一个周期，即 16 kHz 下 200 Hz；幅度足以越过默认 VAD 阈值。
      const auto phase = static_cast<std::int32_t>(sample_index_ % 80U);
      sample = static_cast<std::int16_t>(phase * 150 - 6000);
    } else {
      sample = 0;
    }
    ++sample_index_;
  }
  ++frame_index_;
  return Status::okStatus();
}

Status SimulatedAudioCapture::stop() {
  running_.store(false);
  return Status::okStatus();
}

bool SimulatedAudioCapture::isRunning() const noexcept { return running_.load(); }

AudioDeviceStats SimulatedAudioCapture::stats() const noexcept { return {}; }

}  // namespace rootlink::audio
