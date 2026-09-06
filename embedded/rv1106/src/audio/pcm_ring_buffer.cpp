#include "rootlink/audio/pcm_ring_buffer.h"

#include <algorithm>
#include <limits>
#include <stdexcept>

namespace rootlink::audio {
namespace {

std::size_t checkedStorageSize(std::size_t capacity_frames, std::size_t samples_per_frame) {
  if (capacity_frames == 0 || samples_per_frame == 0 ||
      capacity_frames > std::numeric_limits<std::size_t>::max() / samples_per_frame) {
    throw std::invalid_argument("ring buffer capacity and frame size are invalid");
  }
  return capacity_frames * samples_per_frame;
}

}  // namespace

PcmRingBuffer::PcmRingBuffer(std::size_t capacity_frames, std::size_t samples_per_frame)
    : capacity_frames_(capacity_frames),
      samples_per_frame_(samples_per_frame),
      storage_(checkedStorageSize(capacity_frames, samples_per_frame)) {}

Status PcmRingBuffer::push(const std::int16_t* samples, std::size_t sample_count) {
  if (samples == nullptr || sample_count != samples_per_frame_) {
    return {AudioError::kInvalidArgument, "PCM frame has an invalid sample count"};
  }

  std::lock_guard<std::mutex> lock(mutex_);
  if (closed_) {
    return {AudioError::kClosed, "ring buffer is closed"};
  }

  if (size_ == capacity_frames_) {
    // 满载策略是推进 head 丢最旧帧；采集线程绝不等待较慢的播放/网络消费者。
    head_ = (head_ + 1) % capacity_frames_;
    --size_;
    ++dropped_;
  }

  // tail 只是在预分配 storage_ 中计算写槽位，不会触发 vector 扩容。
  const std::size_t tail = (head_ + size_) % capacity_frames_;
  std::copy_n(samples, samples_per_frame_, storage_.begin() + tail * samples_per_frame_);
  ++size_;
  ++pushed_;
  high_watermark_ = std::max(high_watermark_, size_);
  readable_.notify_one();
  return Status::okStatus();
}

Status PcmRingBuffer::push(const std::vector<std::int16_t>& frame) {
  return push(frame.data(), frame.size());
}

Status PcmRingBuffer::pop(std::vector<std::int16_t>& frame,
                          std::chrono::milliseconds timeout) {
  std::unique_lock<std::mutex> lock(mutex_);
  // 谓词式等待同时抵抗虚假唤醒；close() 与有数据都能解除等待。
  if (!readable_.wait_for(lock, timeout, [this] { return size_ > 0 || closed_; })) {
    return {AudioError::kTimeout, "timed out waiting for a PCM frame"};
  }
  // close 后仍允许读完队列；只有“已关闭且已排空”才返回 kClosed。
  if (size_ == 0) {
    return {AudioError::kClosed, "ring buffer is closed"};
  }

  frame.resize(samples_per_frame_);
  std::copy_n(storage_.begin() + head_ * samples_per_frame_, samples_per_frame_, frame.begin());
  head_ = (head_ + 1) % capacity_frames_;
  --size_;
  ++popped_;
  return Status::okStatus();
}

void PcmRingBuffer::close() noexcept {
  std::lock_guard<std::mutex> lock(mutex_);
  closed_ = true;
  readable_.notify_all();
}

void PcmRingBuffer::clear() noexcept {
  std::lock_guard<std::mutex> lock(mutex_);
  head_ = 0;
  size_ = 0;
}

PcmRingBufferStats PcmRingBuffer::stats() const noexcept {
  std::lock_guard<std::mutex> lock(mutex_);
  return {capacity_frames_, size_, high_watermark_, storage_.capacity(), pushed_, popped_, dropped_,
          closed_};
}

}  // namespace rootlink::audio
