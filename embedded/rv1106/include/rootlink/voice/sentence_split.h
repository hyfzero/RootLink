#pragma once

#include <cstddef>
#include <string>
#include <vector>

namespace rootlink::voice {

/** 按自然中文停顿拆分回答，完整保留输入字节且不拆 UTF-8 字符。 */
std::vector<std::string> splitSpeechSegments(const std::string& text,
                                             std::size_t max_codepoints = 45);

}  // namespace rootlink::voice
