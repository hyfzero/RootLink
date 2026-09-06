#include "rootlink/audio/simulated_audio_playback.h"

#include <thread>
#include <utility>

namespace rootlink::audio {

SimulatedAudioPlayback::SimulatedAudioPlayback(AudioConfig config) : config_(std::move(config)) {}

SimulatedAudioPlayback::~SimulatedAudioPlayback() { (void)stop(); }

Status SimulatedAudioPlayback::start() {
  if (running_.load()) return Status::okStatus();
  const Status valid = config_.validate();
  if (!valid.ok()) return valid;

  std::lock_guard<std::mutex> lock(timing_mutex_);
  next_frame_ = std::chrono::steady_clock::now();
  running_.store(true);
  return Status::okStatus();
}

Status SimulatedAudioPlayback::writeFrame(const std::vector<std::int16_t>& frame) {
  if (!running_.load()) {
    return {AudioError::kInvalidState, "simulated playback is not running"};
  }
  if (frame.size() != config_.samplesPerFrame()) {
    return {AudioError::kInvalidArgument, "playback frame must contain exactly 320 samples"};
  }

  std::chrono::steady_clock::time_point frame_time;
  {
    std::lock_guard<std::mutex> lock(timing_mutex_);
    const auto now = std::chrono::steady_clock::now();
    frame_time = next_frame_ > now ? next_frame_ : now;
    next_frame_ = frame_time + std::chrono::milliseconds(config_.frame_duration_ms);
  }
  if (frame_time > std::chrono::steady_clock::now()) std::this_thread::sleep_until(frame_time);
  if (!running_.load()) return {AudioError::kInterrupted, "simulated playback stopped"};
  return Status::okStatus();
}

// 仿真后端没有内核缓冲区，所有已提交帧在 writeFrame 返回时即视为消费完成。
Status SimulatedAudioPlayback::drain() { return Status::okStatus(); }

Status SimulatedAudioPlayback::stop() {
  running_.store(false);
  return Status::okStatus();
}

bool SimulatedAudioPlayback::isRunning() const noexcept { return running_.load(); }

AudioDeviceStats SimulatedAudioPlayback::stats() const noexcept { return {}; }

}  // namespace rootlink::audio
