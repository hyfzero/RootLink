#include "rootlink/voice/providers.h"

#include <cmath>

#include "rootlink/audio/audio_config.h"

namespace rootlink::voice {

audio::Result<std::string> MockAsrProvider::transcribe(
    const std::vector<std::int16_t>&, const StopRequested& stopped) {
  cancelled_.store(false);
  if ((stopped && stopped()) || cancelled_.load())
    return audio::Result<std::string>(audio::Status(audio::AudioError::kCancelled, "ASR 已取消"));
  return audio::Result<std::string>(std::string("你好，这是离线语音测试。"));
}

audio::Result<std::string> MockLlmProvider::complete(
    const std::vector<ChatMessage>& messages, const TextDelta& on_delta,
    const StopRequested& stopped) {
  cancelled_.store(false);
  if ((stopped && stopped()) || cancelled_.load())
    return audio::Result<std::string>(audio::Status(audio::AudioError::kCancelled, "LLM 已取消"));
  const std::string input = messages.empty() ? std::string() : messages.back().content;
  const std::string answer = "我听到了：" + input;
  // 刻意拆成两个 chunk，保证仿真路径也执行增量输出而不是走特殊捷径。
  const std::size_t split = answer.size() / 2;
  if (on_delta) {
    on_delta(answer.substr(0, split));
    on_delta(answer.substr(split));
  }
  return audio::Result<std::string>(answer);
}

audio::Result<std::vector<std::int16_t>> MockTtsProvider::synthesize(
    const std::string& text, const StopRequested& stopped) {
  cancelled_.store(false);
  if ((stopped && stopped()) || cancelled_.load())
    return audio::Result<std::vector<std::int16_t>>(
        audio::Status(audio::AudioError::kCancelled, "TTS 已取消"));
  const std::size_t frames = std::max<std::size_t>(25, std::min<std::size_t>(150, text.size() * 2));
  std::vector<std::int16_t> samples(frames * audio::kSamplesPerFrame);
  constexpr double kPi = 3.14159265358979323846;
  for (std::size_t index = 0; index < samples.size(); ++index)
    samples[index] = static_cast<std::int16_t>(std::sin(2.0 * kPi * 440.0 * index / 16000.0) * 2500.0);
  return audio::Result<std::vector<std::int16_t>>(std::move(samples));
}

}  // namespace rootlink::voice
