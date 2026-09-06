#include "rootlink/voice/codec.h"

#include <algorithm>
#include <cstring>

namespace rootlink::voice {
namespace {

void put16(std::vector<std::uint8_t>& output, std::size_t offset, std::uint16_t value) {
  output[offset] = static_cast<std::uint8_t>(value & 0xffU);
  output[offset + 1] = static_cast<std::uint8_t>((value >> 8U) & 0xffU);
}
void put32(std::vector<std::uint8_t>& output, std::size_t offset, std::uint32_t value) {
  for (unsigned index = 0; index < 4; ++index)
    output[offset + index] = static_cast<std::uint8_t>((value >> (index * 8U)) & 0xffU);
}
std::uint16_t get16(const std::vector<std::uint8_t>& input, std::size_t offset) {
  return static_cast<std::uint16_t>(input[offset]) |
         static_cast<std::uint16_t>(input[offset + 1] << 8U);
}
std::uint32_t get32(const std::vector<std::uint8_t>& input, std::size_t offset) {
  return static_cast<std::uint32_t>(input[offset]) |
         (static_cast<std::uint32_t>(input[offset + 1]) << 8U) |
         (static_cast<std::uint32_t>(input[offset + 2]) << 16U) |
         (static_cast<std::uint32_t>(input[offset + 3]) << 24U);
}
bool tag(const std::vector<std::uint8_t>& input, std::size_t offset, const char* expected) {
  return offset + 4 <= input.size() && std::memcmp(input.data() + offset, expected, 4) == 0;
}

}  // namespace

std::string base64Encode(const std::vector<std::uint8_t>& input) {
  static constexpr char alphabet[] =
      "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  std::string output;
  output.reserve((input.size() + 2) / 3 * 4);
  for (std::size_t offset = 0; offset < input.size(); offset += 3) {
    const std::uint32_t a = input[offset];
    const std::uint32_t b = offset + 1 < input.size() ? input[offset + 1] : 0;
    const std::uint32_t c = offset + 2 < input.size() ? input[offset + 2] : 0;
    const std::uint32_t value = (a << 16U) | (b << 8U) | c;
    output.push_back(alphabet[(value >> 18U) & 63U]);
    output.push_back(alphabet[(value >> 12U) & 63U]);
    output.push_back(offset + 1 < input.size() ? alphabet[(value >> 6U) & 63U] : '=');
    output.push_back(offset + 2 < input.size() ? alphabet[value & 63U] : '=');
  }
  return output;
}

std::vector<std::uint8_t> pcm16ToWav(const std::vector<std::int16_t>& samples) {
  const std::size_t byte_count = samples.size() * sizeof(std::int16_t);
  std::vector<std::uint8_t> output(44 + byte_count, 0);
  std::memcpy(output.data(), "RIFF", 4);
  put32(output, 4, static_cast<std::uint32_t>(36 + byte_count));
  std::memcpy(output.data() + 8, "WAVEfmt ", 8);
  put32(output, 16, 16);
  put16(output, 20, 1);
  put16(output, 22, 1);
  put32(output, 24, 16000);
  put32(output, 28, 32000);
  put16(output, 32, 2);
  put16(output, 34, 16);
  std::memcpy(output.data() + 36, "data", 4);
  put32(output, 40, static_cast<std::uint32_t>(byte_count));
  for (std::size_t index = 0; index < samples.size(); ++index)
    put16(output, 44 + index * 2, static_cast<std::uint16_t>(samples[index]));
  return output;
}

audio::Result<std::vector<std::int16_t>> wavToPcm16(const std::vector<std::uint8_t>& wav, bool cosyvoice_stream_header) {
  // CosyVoice HTTP WAV uses these exact streaming length placeholders even
  // after a complete HTTPS download. Only accept the observed canonical header.
  if (cosyvoice_stream_header && wav.size() >= 44 && tag(wav, 0, "RIFF") &&
      tag(wav, 8, "WAVE") && tag(wav, 12, "fmt ") && get32(wav, 16) == 16 &&
      tag(wav, 36, "data") && get32(wav, 4) == 0x7fffffbfU &&
      get32(wav, 40) == 0x7fffff9bU && wav.size() < 0x7fffffbfU) {
    auto normalized = wav;
    put32(normalized, 4, static_cast<std::uint32_t>(wav.size() - 8));
    put32(normalized, 40, static_cast<std::uint32_t>(wav.size() - 44));
    return wavToPcm16(normalized);
  }
  using audio::AudioError;
  if (wav.size() < 44 || !tag(wav, 0, "RIFF") || !tag(wav, 8, "WAVE") ||
      static_cast<std::uint64_t>(get32(wav, 4)) + 8 != wav.size())
    return audio::Result<std::vector<std::int16_t>>(audio::Status(AudioError::kUnsupportedFormat,
                                                                  "TTS 返回的内容不是 WAV"));
  std::size_t offset = 12;
  bool valid_format = false;
  std::size_t data_offset = 0;
  std::size_t data_size = 0;
  while (offset + 8 <= wav.size()) {
    const std::uint32_t size = get32(wav, offset + 4);
    const std::size_t content = offset + 8;
    // 用减法检查，避免 RV1106 的 32 位 size_t 在恶意 chunk 长度处发生加法回绕。
    if (size > wav.size() - content)
      return audio::Result<std::vector<std::int16_t>>(audio::Status(AudioError::kUnsupportedFormat,
                                                                    "TTS WAV chunk 被截断"));
    if (tag(wav, offset, "fmt ") && size >= 16) {
      valid_format = get16(wav, content) == 1 && get16(wav, content + 2) == 1 &&
                     get32(wav, content + 4) == 16000 && get16(wav, content + 14) == 16 &&
                     get32(wav, content + 8) == 32000 && get16(wav, content + 12) == 2;
    } else if (tag(wav, offset, "data")) {
      data_offset = content;
      data_size = size;
      break;
    }
    offset = content + size + (size & 1U);
  }
  if (!valid_format || data_offset == 0 || data_size == 0 || data_size % 2 != 0)
    return audio::Result<std::vector<std::int16_t>>(audio::Status(
        AudioError::kUnsupportedFormat, "WAV 必须是非空的 16kHz/单声道/PCM16"));
  std::vector<std::int16_t> samples(data_size / 2);
  for (std::size_t index = 0; index < samples.size(); ++index)
    samples[index] = static_cast<std::int16_t>(get16(wav, data_offset + index * 2));
  return audio::Result<std::vector<std::int16_t>>(std::move(samples));
}

void SseParser::processLine(const std::string& input, std::vector<SseEvent>& output) {
  std::string line = input;
  if (!line.empty() && line.back() == '\r') line.pop_back();
  if (line.empty()) {
    if (!event_data_.empty()) {
      if (event_data_.back() == '\n') event_data_.pop_back();
      output.push_back({std::move(event_data_)});
      event_data_.clear();
    }
    return;
  }
  if (line.rfind("data:", 0) == 0) {
    std::size_t start = 5;
    if (start < line.size() && line[start] == ' ') ++start;
    event_data_.append(line, start, std::string::npos);
    event_data_.push_back('\n');
  }
}

std::vector<SseEvent> SseParser::feed(const char* data, std::size_t size) {
  pending_.append(data, size);
  std::vector<SseEvent> output;
  std::size_t line_end = 0;
  while ((line_end = pending_.find('\n')) != std::string::npos) {
    processLine(pending_.substr(0, line_end), output);
    pending_.erase(0, line_end + 1);
  }
  return output;
}

std::vector<SseEvent> SseParser::finish() {
  std::vector<SseEvent> output;
  if (!pending_.empty()) processLine(pending_, output);
  pending_.clear();
  processLine({}, output);
  return output;
}

}  // namespace rootlink::voice
