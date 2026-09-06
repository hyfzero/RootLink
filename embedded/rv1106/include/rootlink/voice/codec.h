#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "rootlink/audio/status.h"

namespace rootlink::voice {

std::string base64Encode(const std::vector<std::uint8_t>& input);
std::vector<std::uint8_t> pcm16ToWav(const std::vector<std::int16_t>& samples);
audio::Result<std::vector<std::int16_t>> wavToPcm16(const std::vector<std::uint8_t>& wav, bool cosyvoice_stream_header = false);

struct SseEvent {
  std::string data;
};

/** @brief 可跨任意网络分包边界工作的 SSE 行解析器。 */
class SseParser {
 public:
  std::vector<SseEvent> feed(const char* data, std::size_t size);
  std::vector<SseEvent> finish();

 private:
  void processLine(const std::string& line, std::vector<SseEvent>& output);
  std::string pending_;
  std::string event_data_;
};

}  // namespace rootlink::voice
