#include <atomic>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <future>
#include <iostream>
#include <mutex>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include "rootlink/audio/audio_capture.h"
#include "rootlink/audio/audio_config.h"
#include "rootlink/audio/audio_playback.h"
#include "rootlink/audio/audio_session.h"
#include "rootlink/audio/pcm_ring_buffer.h"
#include "rootlink/audio/wav_file.h"

using namespace std::chrono_literals;
using rootlink::audio::AudioConfig;
using rootlink::audio::AudioDeviceStats;
using rootlink::audio::AudioError;
using rootlink::audio::PcmRingBuffer;
using rootlink::audio::Status;

namespace {

std::atomic<int> failures{0};

#define CHECK(condition)                                                                        \
  do {                                                                                          \
    if (!(condition)) {                                                                         \
      std::cerr << __FILE__ << ':' << __LINE__ << " CHECK failed: " #condition << '\n';        \
      ++failures;                                                                               \
    }                                                                                           \
  } while (false)

std::vector<std::int16_t> frame(std::int16_t value) {
  return std::vector<std::int16_t>(rootlink::audio::kSamplesPerFrame, value);
}

void testConfig() {
  AudioConfig config;
  CHECK(config.samplesPerFrame() == 320);
  CHECK(config.bytesPerFrame() == 640);
  CHECK(config.validate().ok());
  config.sample_rate = 8000;
  CHECK(config.validate().code() == AudioError::kUnsupportedFormat);
}

void testRingFifoWrapAndDrop() {
  PcmRingBuffer buffer(3, rootlink::audio::kSamplesPerFrame);
  CHECK(buffer.push(frame(1)).ok());
  CHECK(buffer.push(frame(2)).ok());
  CHECK(buffer.push(frame(3)).ok());
  CHECK(buffer.push(frame(4)).ok());
  std::vector<std::int16_t> output;
  CHECK(buffer.pop(output, 1ms).ok() && output.front() == 2);
  CHECK(buffer.push(frame(5)).ok());
  CHECK(buffer.pop(output, 1ms).ok() && output.front() == 3);
  CHECK(buffer.pop(output, 1ms).ok() && output.front() == 4);
  CHECK(buffer.pop(output, 1ms).ok() && output.front() == 5);
  const auto stats = buffer.stats();
  CHECK(stats.capacity_frames == 3);
  CHECK(stats.high_watermark_frames == 3);
  CHECK(stats.dropped_frames == 1);
  CHECK(stats.size_frames == 0);
}

void testRingTimeoutAndCloseWake() {
  PcmRingBuffer buffer(2, rootlink::audio::kSamplesPerFrame);
  std::vector<std::int16_t> output;
  CHECK(buffer.pop(output, 5ms).code() == AudioError::kTimeout);
  auto waiting = std::async(std::launch::async, [&] { return buffer.pop(output, 5s); });
  std::this_thread::sleep_for(10ms);
  buffer.close();
  CHECK(waiting.wait_for(200ms) == std::future_status::ready);
  CHECK(waiting.get().code() == AudioError::kClosed);
  CHECK(buffer.push(frame(1)).code() == AudioError::kClosed);
  buffer.close();
}

void testRingConcurrentAndFixedStorage() {
  PcmRingBuffer buffer(32, rootlink::audio::kSamplesPerFrame);
  const auto allocated = buffer.stats().allocated_samples;
  std::atomic<bool> producer_done{false};
  std::thread producer([&] {
    for (int i = 0; i < 10000; ++i) CHECK(buffer.push(frame(static_cast<std::int16_t>(i))).ok());
    producer_done = true;
    buffer.close();
  });
  std::thread consumer([&] {
    std::vector<std::int16_t> output;
    while (true) {
      const Status status = buffer.pop(output, 10ms);
      if (status.code() == AudioError::kClosed) break;
      CHECK(status.ok() || status.code() == AudioError::kTimeout);
    }
  });
  producer.join();
  consumer.join();
  CHECK(producer_done.load());
  CHECK(buffer.stats().allocated_samples == allocated);
  CHECK(buffer.stats().high_watermark_frames <= 32);

  PcmRingBuffer stress(100, rootlink::audio::kSamplesPerFrame);
  const auto stress_allocated = stress.stats().allocated_samples;
  const auto sample = frame(7);
  for (int i = 0; i < 1000000; ++i) CHECK(stress.push(sample).ok());
  const auto stats = stress.stats();
  CHECK(stats.allocated_samples == stress_allocated);
  CHECK(stats.size_frames == 100);
  CHECK(stats.dropped_frames == 999900);
}

std::filesystem::path tempWav(const std::string& name) {
  return std::filesystem::temp_directory_path() / name;
}

class EventLog {
 public:
  void add(std::string event) {
    std::lock_guard<std::mutex> lock(mutex_);
    events_.push_back(std::move(event));
  }

  std::vector<std::string> snapshot() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return events_;
  }

 private:
  mutable std::mutex mutex_;
  std::vector<std::string> events_;
};

void testWavRoundTripAndValidation() {
  const auto path = tempWav("rootlink-audio-test.wav");
  AudioConfig config;
  rootlink::audio::WavWriter writer;
  CHECK(writer.open(path.string(), config).ok());
  CHECK(writer.writeFrame(frame(123)).ok());
  CHECK(writer.writeFrame(frame(-321)).ok());
  CHECK(writer.close().ok());
  CHECK(std::filesystem::file_size(path) == 44 + 2 * rootlink::audio::kBytesPerFrame);

  rootlink::audio::WavReader reader;
  CHECK(reader.open(path.string()).ok());
  std::vector<std::int16_t> output;
  CHECK(reader.readFrame(output).ok() && output.front() == 123);
  CHECK(reader.readFrame(output).ok() && output.front() == -321);
  CHECK(reader.readFrame(output).code() == AudioError::kEndOfStream);
  reader.close();

  {
    std::fstream corrupt(path, std::ios::in | std::ios::out | std::ios::binary);
    const char stereo_channels[2] = {2, 0};
    corrupt.seekp(22);
    corrupt.write(stereo_channels, sizeof(stereo_channels));
  }
  CHECK(reader.open(path.string()).code() == AudioError::kUnsupportedFormat);

  AudioConfig invalid = config;
  invalid.channels = 2;
  CHECK(writer.open(path.string(), invalid).code() == AudioError::kUnsupportedFormat);

  rootlink::audio::WavWriter truncated_writer;
  CHECK(truncated_writer.open(path.string(), config).ok());
  CHECK(truncated_writer.writeFrame(frame(8)).ok());
  CHECK(truncated_writer.close().ok());
  std::filesystem::resize_file(path, 44 + 100);
  CHECK(reader.open(path.string()).code() == AudioError::kUnsupportedFormat);
  std::filesystem::remove(path);
}

class FakeCapture final : public rootlink::audio::AudioCapture {
 public:
  Status start() override {
    ++starts;
    if (events != nullptr) events->add("capture.start");
    if (start_status.ok()) running = true;
    return start_status;
  }
  Status readFrame(std::vector<std::int16_t>& output, std::chrono::milliseconds) override {
    const int current = ++reads;
    if (fail_after > 0 && current > fail_after) {
      return {AudioError::kDeviceError, "fake capture failure"};
    }
    output = frame(static_cast<std::int16_t>(current));
    return Status::okStatus();
  }
  Status stop() override {
    ++stops;
    if (events != nullptr) events->add("capture.stop");
    running = false;
    return Status::okStatus();
  }
  bool isRunning() const noexcept override { return running.load(); }
  AudioDeviceStats stats() const noexcept override { return {}; }

  std::atomic<int> starts{0};
  std::atomic<int> reads{0};
  std::atomic<int> stops{0};
  std::atomic<bool> running{false};
  int fail_after{0};
  EventLog* events{nullptr};
  Status start_status;
};

class FakePlayback final : public rootlink::audio::AudioPlayback {
 public:
  Status start() override {
    ++starts;
    if (events != nullptr) events->add("playback.start");
    if (start_status.ok()) running = true;
    return start_status;
  }
  Status writeFrame(const std::vector<std::int16_t>& input) override {
    CHECK(input.size() == rootlink::audio::kSamplesPerFrame);
    ++writes;
    if (fail_after > 0 && writes.load() > fail_after) {
      return {AudioError::kDeviceError, "fake playback failure"};
    }
    return Status::okStatus();
  }
  Status drain() override {
    ++drains;
    if (events != nullptr) events->add("playback.drain");
    return Status::okStatus();
  }
  Status stop() override {
    ++stops;
    if (events != nullptr) events->add("playback.stop");
    running = false;
    return Status::okStatus();
  }
  bool isRunning() const noexcept override { return running.load(); }
  AudioDeviceStats stats() const noexcept override { return {}; }

  std::atomic<int> starts{0};
  std::atomic<int> writes{0};
  std::atomic<int> drains{0};
  std::atomic<int> stops{0};
  std::atomic<bool> running{false};
  int fail_after{0};
  EventLog* events{nullptr};
  Status start_status;
};

void testSessionCleanup() {
  const auto path = tempWav("rootlink-audio-session-test.wav");
  AudioConfig config;
  EventLog record_events;
  FakeCapture capture;
  capture.events = &record_events;
  CHECK(rootlink::audio::recordToWav(capture, config, path.string(), 1s,
                                     [&] { return capture.reads.load() >= 3; })
            .ok());
  CHECK(capture.starts == 1 && capture.stops == 1 && !capture.isRunning());
  CHECK(record_events.snapshot() ==
        std::vector<std::string>({"capture.start", "capture.stop"}));

  EventLog playback_events;
  FakePlayback playback;
  playback.events = &playback_events;
  CHECK(rootlink::audio::playWav(playback, path.string(), [] { return false; }).ok());
  CHECK(playback.starts == 1 && playback.stops == 1 && playback.drains == 1);
  CHECK(playback_events.snapshot() == std::vector<std::string>(
                                             {"playback.start", "playback.drain", "playback.stop"}));

  FakeCapture loop_capture;
  FakePlayback loop_playback;
  rootlink::audio::AudioSessionReport report;
  CHECK(rootlink::audio::runLoopback(loop_capture, loop_playback, config, 4, 0ms,
                                    [&] { return loop_capture.reads.load() >= 20; }, &report)
            .ok());
  CHECK(loop_capture.stops == 1 && loop_playback.stops == 1);
  CHECK(report.buffer.capacity_frames == 4);
  CHECK(report.buffer.high_watermark_frames <= 4);

  FakeCapture failing_capture;
  failing_capture.fail_after = 1;
  FakePlayback failing_playback;
  const Status failed = rootlink::audio::runLoopback(
      failing_capture, failing_playback, config, 4, 1s, [] { return false; }, nullptr);
  CHECK(failed.code() == AudioError::kDeviceError);
  CHECK(failing_capture.stops == 1 && failing_playback.stops == 1);

  FakeCapture start_failing_capture;
  start_failing_capture.start_status = {AudioError::kDeviceError, "fake start failure"};
  CHECK(rootlink::audio::recordToWav(start_failing_capture, config, path.string(), 1s,
                                    [] { return false; })
            .code() == AudioError::kDeviceError);
  CHECK(start_failing_capture.starts == 1 && start_failing_capture.stops == 0);

  FakeCapture capture_for_playback_failure;
  FakePlayback start_failing_playback;
  start_failing_playback.start_status = {AudioError::kDeviceError, "fake start failure"};
  CHECK(rootlink::audio::runLoopback(capture_for_playback_failure, start_failing_playback,
                                    config, 4, 1s, [] { return false; }, nullptr)
            .code() == AudioError::kDeviceError);
  CHECK(capture_for_playback_failure.stops == 1 && start_failing_playback.stops == 0);
  std::filesystem::remove(path);
}

}  // namespace

int main() {
  testConfig();
  testRingFifoWrapAndDrop();
  testRingTimeoutAndCloseWake();
  testRingConcurrentAndFixedStorage();
  testWavRoundTripAndValidation();
  testSessionCleanup();
  if (failures.load() != 0) {
    std::cerr << failures.load() << " test checks failed\n";
    return 1;
  }
  std::cout << "All RootLink RV1106 audio core tests passed\n";
  return 0;
}
