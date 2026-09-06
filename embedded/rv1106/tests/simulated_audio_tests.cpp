#include <chrono>
#include <cstdint>
#include <iostream>
#include <vector>

#include "rootlink/audio/audio_config.h"
#include "rootlink/audio/simulated_audio_capture.h"
#include "rootlink/audio/simulated_audio_playback.h"

using namespace std::chrono_literals;

int main() {
  rootlink::audio::AudioConfig config;
  rootlink::audio::SimulatedAudioCapture capture(config);
  rootlink::audio::SimulatedAudioPlayback playback(config);
  std::vector<std::int16_t> frame;

  // 第一帧立即可用；第二帧需要等待，用零超时可稳定验证 timeout 分支。
  if (!capture.start().ok() || !capture.start().ok()) return 1;
  if (!capture.readFrame(frame, 100ms).ok() || frame.size() != 320 || frame.front() != -6000) {
    return 2;
  }
  if (capture.readFrame(frame, 0ms).code() != rootlink::audio::AudioError::kTimeout) return 3;
  if (!capture.readFrame(frame, 100ms).ok()) return 4;
  if (!capture.stop().ok() || !capture.stop().ok() || capture.isRunning()) return 5;

  if (!playback.start().ok() || !playback.start().ok()) return 6;
  if (playback.writeFrame(std::vector<std::int16_t>(1)).code() !=
      rootlink::audio::AudioError::kInvalidArgument) {
    return 7;
  }
  if (!playback.writeFrame(frame).ok() || !playback.drain().ok()) return 8;
  if (!playback.stop().ok() || !playback.stop().ok() || playback.isRunning()) return 9;

  std::cout << "RootLink simulated audio backend tests passed\n";
  return 0;
}
