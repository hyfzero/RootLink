#include "rootlink/audio/audio_session.h"

#include <atomic>
#include <mutex>
#include <thread>
#include <utility>
#include <vector>

#include "rootlink/audio/wav_file.h"

namespace rootlink::audio {
namespace {

bool shouldStop(const StopRequested& callback) { return callback && callback(); }

Status preferFirst(Status first, const Status& next) {
  // 清理阶段也可能失败，但不能覆盖更早、更接近根因的业务错误。
  return first.ok() && !next.ok() ? next : first;
}

}  // namespace

Status recordToWav(AudioCapture& capture, const AudioConfig& config,
                   const std::string& output_path, std::chrono::milliseconds duration,
                   const StopRequested& stop_requested) {
  if (duration.count() <= 0) {
    return {AudioError::kInvalidArgument, "record duration must be greater than zero"};
  }
  Status result = config.validate();
  if (!result.ok()) return result;

  WavWriter writer;
  // 先创建 WAV 再启动设备，确保设备启动失败时仍能通过 close 修正/关闭文件。
  result = writer.open(output_path, config);
  if (!result.ok()) return result;
  result = capture.start();
  if (!result.ok()) {
    (void)writer.close();
    return result;
  }

  const auto deadline = std::chrono::steady_clock::now() + duration;
  std::vector<std::int16_t> frame;
  while (std::chrono::steady_clock::now() < deadline && !shouldStop(stop_requested)) {
    const Status read = capture.readFrame(frame, std::chrono::milliseconds(100));
    if (read.code() == AudioError::kTimeout) continue;
    if (!read.ok()) {
      result = read;
      break;
    }
    result = writer.writeFrame(frame);
    if (!result.ok()) break;
  }

  // 无论自然结束、Ctrl+C 还是读写失败，都走同一个确定的清理顺序。
  result = preferFirst(std::move(result), capture.stop());
  result = preferFirst(std::move(result), writer.close());
  return result;
}

Status playWav(AudioPlayback& playback, const std::string& input_path,
               const StopRequested& stop_requested) {
  WavReader reader;
  Status result = reader.open(input_path);
  if (!result.ok()) return result;
  result = playback.start();
  if (!result.ok()) return result;

  bool reached_end = false;
  std::vector<std::int16_t> frame;
  while (!shouldStop(stop_requested)) {
    const Status read = reader.readFrame(frame);
    if (read.code() == AudioError::kEndOfStream) {
      reached_end = true;
      break;
    }
    if (!read.ok()) {
      result = read;
      break;
    }
    result = playback.writeFrame(frame);
    if (!result.ok()) break;
  }
  // 只有自然读到文件末尾才等待声卡排空；用户中断应快速退出。
  if (result.ok() && reached_end) result = playback.drain();
  result = preferFirst(std::move(result), playback.stop());
  reader.close();
  return result;
}

Status runLoopback(AudioCapture& capture, AudioPlayback& playback, const AudioConfig& config,
                   std::size_t buffer_frames, std::chrono::milliseconds duration,
                   const StopRequested& stop_requested, AudioSessionReport* report) {
  if (buffer_frames == 0 || duration.count() < 0) {
    return {AudioError::kInvalidArgument, "buffer size must be positive and duration non-negative"};
  }
  Status result = config.validate();
  if (!result.ok()) return result;

  PcmRingBuffer buffer(buffer_frames, config.samplesPerFrame());
  result = capture.start();
  if (!result.ok()) return result;
  result = playback.start();
  if (!result.ok()) {
    result = preferFirst(std::move(result), capture.stop());
    return result;
  }

  std::atomic<bool> finishing{false};
  std::mutex error_mutex;
  Status worker_error = Status::okStatus();
  // ALSA capture 是阻塞操作，因此独立生产线程能让主线程持续检查时限/信号，
  // 同时以有界队列隔离采集与播放的短时抖动。
  std::thread producer([&] {
    std::vector<std::int16_t> frame;
    while (!finishing.load(std::memory_order_relaxed)) {
      const Status read = capture.readFrame(frame, std::chrono::milliseconds(100));
      if (read.code() == AudioError::kTimeout) continue;
      if (!read.ok()) {
        std::lock_guard<std::mutex> lock(error_mutex);
        worker_error = read;
        break;
      }
      const Status pushed = buffer.push(frame);
      if (pushed.code() == AudioError::kClosed) break;
      if (!pushed.ok()) {
        std::lock_guard<std::mutex> lock(error_mutex);
        worker_error = pushed;
        break;
      }
    }
    // 任何生产侧退出都会关闭队列，立即唤醒可能正在 pop 的主线程。
    finishing.store(true, std::memory_order_relaxed);
    buffer.close();
  });

  const auto start = std::chrono::steady_clock::now();
  std::vector<std::int16_t> frame;
  while (!finishing.load(std::memory_order_relaxed)) {
    if (shouldStop(stop_requested) ||
        (duration.count() > 0 && std::chrono::steady_clock::now() - start >= duration)) {
      finishing.store(true, std::memory_order_relaxed);
      buffer.close();
      break;
    }
    const Status popped = buffer.pop(frame, std::chrono::milliseconds(100));
    if (popped.code() == AudioError::kTimeout) continue;
    if (popped.code() == AudioError::kClosed) break;
    if (!popped.ok()) {
      result = popped;
      break;
    }
    result = playback.writeFrame(frame);
    if (!result.ok()) break;
  }

  // 先发布停止并 close，再 join；否则生产线程可能还在等待消费者，形成退出死锁。
  finishing.store(true, std::memory_order_relaxed);
  buffer.close();
  producer.join();
  {
    std::lock_guard<std::mutex> lock(error_mutex);
    result = preferFirst(std::move(result), worker_error);
  }
  result = preferFirst(std::move(result), capture.stop());
  if (result.ok()) result = playback.drain();
  result = preferFirst(std::move(result), playback.stop());

  if (report != nullptr) {
    report->buffer = buffer.stats();
    report->capture = capture.stats();
    report->playback = playback.stats();
  }
  return result;
}

}  // namespace rootlink::audio
