#pragma once

#include <cstdint>
#include <vector>

#include "rootlink/audio/audio_config.h"
#include "rootlink/audio/status.h"
#include "rootlink/voice/runtime_config.h"

namespace rootlink::voice {

struct VadAnalysis {
  double rms{0.0};
  std::int16_t peak{0};
  double threshold{0.0};
  double noise_floor{0.0};
  bool speech{false};
};

/** @brief 单帧 VAD 接口；实现不能保存或输出原始音频。 */
class VadDetector {
 public:
  virtual ~VadDetector() = default;
  virtual audio::Result<VadAnalysis> analyze(const std::vector<std::int16_t>& frame) = 0;
  virtual void reset() noexcept = 0;
};

/**
 * @brief 针对 RV1106 的无模型自适应能量 VAD。
 *
 * 阈值取绝对下限与环境噪声倍率中的较大值。噪声基线只在当前帧未超过阈值时
 * 更新，避免讲话本身把基线越抬越高而造成句中漏检。
 */
class AdaptiveEnergyVad final : public VadDetector {
 public:
  explicit AdaptiveEnergyVad(VadConfig config);
  audio::Result<VadAnalysis> analyze(const std::vector<std::int16_t>& frame) override;
  void reset() noexcept override;

 private:
  VadConfig config_;
  double noise_floor_{0.0};
  bool initialized_{false};
};

enum class SegmentEvent { kNone, kStarted, kCompleted, kRejectedTooShort, kForcedMaximum };

struct SegmenterStats {
  std::uint64_t starts{0};
  std::uint64_t completed{0};
  std::uint64_t rejected_too_short{0};
  std::uint64_t forced_maximum{0};
};

/**
 * @brief 把帧级 VAD 结果组合为一条完整语句。
 *
 * 构造时预留最长语句空间，并用固定大小的循环区保存 pre-roll。kCompleted 或
 * kForcedMaximum 返回后，调用方在下一次 pushFrame 前读取 utterance() 并 reset()。
 */
class UtteranceSegmenter {
 public:
  explicit UtteranceSegmenter(VadConfig config);

  audio::Result<SegmentEvent> pushFrame(const std::vector<std::int16_t>& frame,
                                        const VadAnalysis& analysis);
  const std::vector<std::int16_t>& utterance() const noexcept { return utterance_; }
  void reset() noexcept;
  bool inSpeech() const noexcept { return in_speech_; }
  const SegmenterStats& stats() const noexcept { return stats_; }
  std::size_t reservedSamples() const noexcept { return utterance_.capacity(); }

 private:
  void savePreRoll(const std::vector<std::int16_t>& frame);
  void appendPreRoll();

  VadConfig config_;
  std::size_t pre_roll_frames_{0};
  std::size_t end_silence_frames_{0};
  std::size_t min_speech_frames_{0};
  std::size_t max_frames_{0};
  std::vector<std::int16_t> pre_roll_;
  std::size_t pre_roll_write_{0};
  std::size_t pre_roll_size_{0};
  std::vector<std::int16_t> utterance_;
  std::size_t positive_frames_{0};
  std::size_t silent_frames_{0};
  std::size_t speech_frames_{0};
  bool in_speech_{false};
  bool finished_{false};
  SegmenterStats stats_;
};

}  // namespace rootlink::voice
