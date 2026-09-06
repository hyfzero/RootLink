#include "rootlink/voice/vad.h"

#include <algorithm>
#include <cmath>
#include <limits>

namespace rootlink::voice {

AdaptiveEnergyVad::AdaptiveEnergyVad(VadConfig config) : config_(config) {}

audio::Result<VadAnalysis> AdaptiveEnergyVad::analyze(
    const std::vector<std::int16_t>& frame) {
  if (frame.size() != audio::kSamplesPerFrame) {
    return audio::Result<VadAnalysis>(audio::Status(
        audio::AudioError::kInvalidArgument, "VAD 输入必须恰好包含 320 个采样"));
  }
  long double sum_squares = 0.0;
  std::int32_t peak = 0;
  for (const std::int16_t sample : frame) {
    const std::int32_t magnitude = sample == std::numeric_limits<std::int16_t>::min()
                                       ? 32768
                                       : std::abs(static_cast<std::int32_t>(sample));
    peak = std::max(peak, magnitude);
    sum_squares += static_cast<long double>(sample) * sample;
  }
  const double rms = std::sqrt(static_cast<double>(sum_squares / frame.size()));
  if (!initialized_) {
    // 初始帧可能正好包含语音，因此初值不能直接高于绝对门限；后续安静帧会平滑
    // 收敛到真实底噪。
    noise_floor_ = std::min(rms, config_.min_rms / config_.noise_multiplier);
    initialized_ = true;
  }
  const double threshold = std::max(config_.min_rms, noise_floor_ * config_.noise_multiplier);
  const bool speech = rms >= threshold;
  if (!speech) {
    noise_floor_ = (1.0 - config_.noise_alpha) * noise_floor_ + config_.noise_alpha * rms;
  }
  VadAnalysis output;
  output.rms = rms;
  output.peak = static_cast<std::int16_t>(std::min(peak, 32767));
  output.threshold = threshold;
  output.noise_floor = noise_floor_;
  output.speech = speech;
  return audio::Result<VadAnalysis>(output);
}

void AdaptiveEnergyVad::reset() noexcept {
  noise_floor_ = 0.0;
  initialized_ = false;
}

UtteranceSegmenter::UtteranceSegmenter(VadConfig config)
    : config_(config),
      pre_roll_frames_(config.pre_roll_ms / audio::kFrameDurationMs + config.start_frames),
      end_silence_frames_(config.end_silence_ms / audio::kFrameDurationMs),
      min_speech_frames_(config.min_utterance_ms / audio::kFrameDurationMs),
      max_frames_(config.max_utterance_ms / audio::kFrameDurationMs),
      pre_roll_(pre_roll_frames_ * audio::kSamplesPerFrame) {
  utterance_.reserve(max_frames_ * audio::kSamplesPerFrame);
}

void UtteranceSegmenter::savePreRoll(const std::vector<std::int16_t>& frame) {
  if (pre_roll_frames_ == 0) return;
  const std::size_t offset = pre_roll_write_ * audio::kSamplesPerFrame;
  std::copy(frame.begin(), frame.end(), pre_roll_.begin() + static_cast<std::ptrdiff_t>(offset));
  pre_roll_write_ = (pre_roll_write_ + 1) % pre_roll_frames_;
  pre_roll_size_ = std::min(pre_roll_size_ + 1, pre_roll_frames_);
}

void UtteranceSegmenter::appendPreRoll() {
  if (pre_roll_size_ == 0) return;
  const std::size_t oldest = (pre_roll_write_ + pre_roll_frames_ - pre_roll_size_) % pre_roll_frames_;
  for (std::size_t index = 0; index < pre_roll_size_; ++index) {
    const std::size_t frame_index = (oldest + index) % pre_roll_frames_;
    const auto begin = pre_roll_.begin() + static_cast<std::ptrdiff_t>(frame_index * audio::kSamplesPerFrame);
    utterance_.insert(utterance_.end(), begin, begin + audio::kSamplesPerFrame);
  }
}

audio::Result<SegmentEvent> UtteranceSegmenter::pushFrame(
    const std::vector<std::int16_t>& frame, const VadAnalysis& analysis) {
  if (finished_)
    return audio::Result<SegmentEvent>(audio::Status(audio::AudioError::kInvalidState,
                                                     "读取已完成语句后必须先 reset"));
  if (frame.size() != audio::kSamplesPerFrame) {
    return audio::Result<SegmentEvent>(audio::Status(
        audio::AudioError::kInvalidArgument, "语句切分输入必须恰好包含 320 个采样"));
  }
  if (!in_speech_) {
    savePreRoll(frame);
    positive_frames_ = analysis.speech ? positive_frames_ + 1 : 0;
    if (positive_frames_ < config_.start_frames) return audio::Result<SegmentEvent>(SegmentEvent::kNone);
    in_speech_ = true;
    silent_frames_ = 0;
    speech_frames_ = positive_frames_;
    utterance_.clear();
    appendPreRoll();
    ++stats_.starts;
    return audio::Result<SegmentEvent>(SegmentEvent::kStarted);
  }

  utterance_.insert(utterance_.end(), frame.begin(), frame.end());
  if (analysis.speech) {
    ++speech_frames_;
    silent_frames_ = 0;
  } else {
    ++silent_frames_;
  }
  const std::size_t utterance_frames = utterance_.size() / audio::kSamplesPerFrame;
  if (utterance_frames >= max_frames_) {
    finished_ = true;
    ++stats_.forced_maximum;
    return audio::Result<SegmentEvent>(SegmentEvent::kForcedMaximum);
  }
  if (silent_frames_ < end_silence_frames_) return audio::Result<SegmentEvent>(SegmentEvent::kNone);
  finished_ = true;
  if (speech_frames_ < min_speech_frames_) {
    ++stats_.rejected_too_short;
    return audio::Result<SegmentEvent>(SegmentEvent::kRejectedTooShort);
  }
  ++stats_.completed;
  return audio::Result<SegmentEvent>(SegmentEvent::kCompleted);
}

void UtteranceSegmenter::reset() noexcept {
  pre_roll_write_ = 0;
  pre_roll_size_ = 0;
  utterance_.clear();
  positive_frames_ = 0;
  silent_frames_ = 0;
  speech_frames_ = 0;
  in_speech_ = false;
  finished_ = false;
}

}  // namespace rootlink::voice
