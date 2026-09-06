#pragma once

#include <chrono>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <mutex>
#include <vector>

#include "rootlink/audio/status.h"

namespace rootlink::audio {

/// 环形缓冲区的不可变容量、实时水位和累计流量指标。
struct PcmRingBufferStats {
  std::size_t capacity_frames{0};
  std::size_t size_frames{0};
  std::size_t high_watermark_frames{0};
  std::size_t allocated_samples{0};
  std::uint64_t pushed_frames{0};
  std::uint64_t popped_frames{0};
  std::uint64_t dropped_frames{0};
  bool closed{false};
};

/**
 * @brief 有界、线程安全、运行期零扩容的 PCM 帧队列。
 *
 * 构造时一次分配 capacity_frames * samples_per_frame 个采样。队列满时 push 丢弃
 * 最旧帧而不阻塞采集线程；close 会唤醒全部 pop 等待者，且关闭后不可重新打开。
 */
class PcmRingBuffer {
 public:
  PcmRingBuffer(std::size_t capacity_frames, std::size_t samples_per_frame);

  PcmRingBuffer(const PcmRingBuffer&) = delete;
  PcmRingBuffer& operator=(const PcmRingBuffer&) = delete;

  /// 写入一帧；满载时覆盖逻辑上的最旧帧并增加 dropped_frames。
  Status push(const std::int16_t* samples, std::size_t sample_count);
  Status push(const std::vector<std::int16_t>& frame);
  /// 最多等待 timeout；关闭后先读完残留帧，再返回 kClosed。
  Status pop(std::vector<std::int16_t>& frame,
             std::chrono::milliseconds timeout);
  /// 永久关闭并唤醒所有等待线程；可重复调用。
  void close() noexcept;
  /// 清空未读帧但保留容量、累计计数和关闭状态。
  void clear() noexcept;
  PcmRingBufferStats stats() const noexcept;

 private:
  const std::size_t capacity_frames_;
  const std::size_t samples_per_frame_;
  std::vector<std::int16_t> storage_;

  mutable std::mutex mutex_;
  std::condition_variable readable_;
  std::size_t head_{0};
  std::size_t size_{0};
  std::size_t high_watermark_{0};
  std::uint64_t pushed_{0};
  std::uint64_t popped_{0};
  std::uint64_t dropped_{0};
  bool closed_{false};
};

}  // namespace rootlink::audio
