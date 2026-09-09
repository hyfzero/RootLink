#include "rootlink/voice/sentence_split.h"

#include <algorithm>

namespace rootlink::voice {
namespace {

std::size_t utf8Width(unsigned char byte) {
  if ((byte & 0x80U) == 0) return 1;
  if ((byte & 0xE0U) == 0xC0U) return 2;
  if ((byte & 0xF0U) == 0xE0U) return 3;
  if ((byte & 0xF8U) == 0xF0U) return 4;
  return 1;  // 保留无效 UTF-8 的原始字节，也保证循环推进。
}

bool isTerminal(const std::string& value) {
  return value == "。" || value == "！" || value == "？" || value == "!" ||
         value == "?" || value == "\n" || value == "\r";
}

bool isPause(const std::string& value) {
  return value == "，" || value == "、" || value == "；" || value == "：" ||
         value == "," || value == ";" || value == ":";
}

bool isAttachOnly(const std::string& text) {
  if (text.empty()) return true;
  for (std::size_t offset = 0; offset < text.size();) {
    const std::size_t begin = offset;
    offset += std::min(utf8Width(static_cast<unsigned char>(text[offset])), text.size() - offset);
    const std::string value = text.substr(begin, offset - begin);
    const bool ascii_space = value.size() == 1 &&
        (value[0] == ' ' || value[0] == '\t' || value[0] == '\n' || value[0] == '\r');
    const bool closing = value == "”" || value == "’" || value == "）" || value == "】" ||
        value == "》" || value == "」" || value == "』" || value == ")" || value == "]" ||
        value == "\"" || value == "'" || isTerminal(value) || isPause(value);
    if (!ascii_space && !closing) return false;
  }
  return true;
}

std::size_t codepointCount(const std::string& text, std::size_t begin, std::size_t end) {
  std::size_t count = 0;
  while (begin < end) {
    begin += std::min(utf8Width(static_cast<unsigned char>(text[begin])), end - begin);
    ++count;
  }
  return count;
}

}  // namespace

std::vector<std::string> splitSpeechSegments(const std::string& text,
                                             std::size_t max_codepoints) {
  if (text.empty()) return {};
  max_codepoints = std::max<std::size_t>(1, max_codepoints);
  std::vector<std::string> result;
  std::size_t segment_begin = 0, offset = 0, segment_codepoints = 0, last_pause = 0;
  while (offset < text.size()) {
    const std::size_t begin = offset;
    offset += std::min(utf8Width(static_cast<unsigned char>(text[offset])), text.size() - offset);
    const std::string character = text.substr(begin, offset - begin);
    ++segment_codepoints;
    if (isPause(character)) last_pause = offset;
    if (isTerminal(character)) {
      result.push_back(text.substr(segment_begin, offset - segment_begin));
      segment_begin = offset;
      segment_codepoints = 0;
      last_pause = 0;
    } else if (segment_codepoints >= max_codepoints) {
      const std::size_t split_at = last_pause > segment_begin ? last_pause : offset;
      result.push_back(text.substr(segment_begin, split_at - segment_begin));
      segment_begin = split_at;
      segment_codepoints = codepointCount(text, split_at, offset);
      last_pause = 0;
    }
  }
  if (segment_begin < text.size()) result.push_back(text.substr(segment_begin));

  std::vector<std::string> merged;
  std::string leading_attachment;
  for (auto& segment : result) {
    if (isAttachOnly(segment)) {
      if (merged.empty()) leading_attachment += segment;
      else merged.back() += segment;
    } else {
      if (!leading_attachment.empty()) {
        segment = std::move(leading_attachment) + segment;
        leading_attachment.clear();
      }
      merged.push_back(std::move(segment));
    }
  }
  // 纯空白或标点没有可合成的语音内容，不能发起空 TTS 请求。
  return merged;
}

}  // namespace rootlink::voice
